"""F8-H nonlinear DC operating point: damped Newton around linear MNA.

Iteration layer over the certified system, not a parallel solver:

* unknown vector, topology, linear stamps, ground rules: ``mna.problem``
  (``build_mna_problem``), reused bit-for-bit. Diodes add NO unknowns;
  their companion stamp enters the residual/Jacobian only.
* linear algebra: ``math.linsolve`` HP path (``Decimal`` entries are
  first-class inputs of ``ComplexLinearProblem.from_sequences``; the
  Newton correction is read off the real parts). No second solver.
* entry/exit shapes mirror ``solve_linear_dc`` (in-band
  INVALID/UNSUPPORTED, ``Quantity`` outputs, provenance with digest).

Mathematics (per iterate ``xk``, all ``Decimal`` under the explicit
50-digit working context):

* ``F(x) = A0 x - b0 + D(x) = 0`` where ``(A0, b0)`` are the linear
  MNA stamps (R/V/I/E/G/H/F/O/T) and ``D(x)`` holds the diode
  companion currents (``+I`` leaving ``A``, ``-I`` leaving ``K``).
* ``J(x) = A0 + sum over diodes of g-stamps``
  (``+g`` on ``(A,A)``/``(K,K)``, ``-g`` on ``(A,K)``/``(K,A)``).
* ``J(xk) dx = -F(xk)`` via linsolve; ``x(k+1) = xk + a dx`` with
  deterministic bisection backtracking (strict residual decrease).

Frozen iteration policy (Q1), recorded in provenance:

* ``RTOL = 1E-9`` (relative), ``ATOL = 1E-12`` (absolute),
  ``STOL = 1E-12`` (step). Residual rows split into the KCL block
  (ampere) and the aux-constraint block (volt); each block passes
  iff ``max|F| <= ATOL + RTOL * max(1, max|x|)``. Convergence needs
  the residual AND the step small (a small step alone never
  certifies).
* ``MAX_ITER = 50`` Newton iterations, ``MAX_BACKTRACK = 10``
  halvings (``a_min = 1/1024``). Strict decrease per accepted step
  makes oscillation impossible; stagnation (no improving ``a``)
  is ``DIVERGED``, not a silent value.
* Non-finite diode evaluation (``exp`` overflow) during iteration
  is ``DIVERGED`` (cause: evaluation); non-finite/missing diode
  parameters are ``INVALID`` at validation (cause: input).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, Overflow
from enum import Enum

from academic_core.domain.engineering.circuit import Circuit
from academic_core.domain.engineering.mna.dependent import DEPENDENT_TYPES
from academic_core.domain.engineering.mna.diode import (
    DiodeParams,
    DiodeVariantParams,
    companion,
    extract_diode_params,
    extract_diode_variant_params,
    shockley_current,
    variant_companion,
    variant_conductance,
    variant_current,
)
from academic_core.domain.engineering.mna.mosfet import (
    MOSParams,
    extract_mosfet_params,
    mos_jacobian,
    mos_terminal_currents,
)
from academic_core.domain.engineering.mna.jfet import (
    JFETParams,
    extract_jfet_params,
    jfet_jacobian,
    jfet_terminal_currents,
)
from academic_core.domain.engineering.mna.bjt import (
    BJTParams,
    bjt_jacobian,
    bjt_terminal_currents,
    extract_bjt_params,
)
from academic_core.domain.engineering.mna.errors import (
    CircularControlError,
    DimensionalityError,
    FloatingCircuitError,
    InvalidCircuitError,
    MissingReferenceError,
    UnsupportedElementError,
)
from academic_core.domain.engineering.mna.problem import (
    MNAProblem,
    build_mna_problem,
)
from academic_core.domain.engineering.mna.result import (
    BranchCurrent,
    ConservationChecks,
    ElementPower,
    NodeVoltage,
)
from academic_core.domain.engineering.mna.solver import fundamental_cycle_chords
from academic_core.domain.engineering.math.linsolve import (
    ComplexLinearProblem,
    NumericMode,
    SolveStatus as LinearStatus,
    solve as linsolve,
)
from academic_core.domain.engineering.math.trig import make_context
from academic_core.domain.engineering.units import Quantity, parse_unit

ENGINE_VERSION = "f8h-nonlinear/1.0"

# Q1 — frozen iteration policy (see module docstring).
RTOL = Decimal("1E-9")
ATOL = Decimal("1E-12")
STOL = Decimal("1E-12")
MAX_ITER = 50
MAX_BACKTRACK = 10

_VOLT = parse_unit("V")
_AMP = parse_unit("A")
_WATT = parse_unit("W")
_SIEMENS = parse_unit("S")

_INVALID_ERRORS = (InvalidCircuitError, MissingReferenceError,
                   FloatingCircuitError, DimensionalityError,
                   CircularControlError)


class NonlinearStatus(Enum):
    """Solver verdicts for the nonlinear operating point.

    Separate enum by design: the certified linear ``SolveStatus`` is
    untouched. Only ``CONVERGED`` carries a solution.
    """

    CONVERGED = "converged"
    MAX_ITERATIONS = "max_iterations"
    DIVERGED = "diverged"
    SINGULAR_JACOBIAN = "singular_jacobian"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class NonlinearResult:
    """Structured F8-H result (mirrors ``AnalysisResult`` shapes)."""

    status: NonlinearStatus
    node_voltages: tuple[NodeVoltage, ...] = ()
    branch_currents: tuple[BranchCurrent, ...] = ()
    element_powers: tuple[ElementPower, ...] = ()
    system_summary: dict = field(default_factory=dict)
    conservation_checks: ConservationChecks | None = None
    provenance: dict = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "node_voltages": {nv.node: nv.voltage.format()
                              for nv in self.node_voltages},
            "branch_currents": {
                bc.ref: {"current": bc.current.format(),
                         "convention": bc.convention}
                for bc in self.branch_currents
            },
            "element_powers": {
                ep.ref: {"power": ep.power.format(), "absorbed": ep.absorbed}
                for ep in self.element_powers
            },
            "system_summary": self.system_summary,
            "conservation_checks": (
                None if self.conservation_checks is None else {
                    "kcl_max_residual":
                        self.conservation_checks.kcl_max_residual,
                    "kvl_max_residual":
                        self.conservation_checks.kvl_max_residual,
                    "power_balance_residual":
                        self.conservation_checks.power_balance_residual,
                    "tolerance": self.conservation_checks.tolerance,
                    "passed": self.conservation_checks.passed,
                }
            ),
            "provenance": self.provenance,
            "diagnostics": list(self.diagnostics),
        }


def _decimal_of(fr) -> Decimal:
    ctx = make_context()
    return ctx.divide(Decimal(fr.numerator), Decimal(fr.denominator))


def _block_ok(rows: list[Decimal], scale: Decimal) -> bool:
    if not rows:
        return True
    peak = max(abs(v) for v in rows)
    return peak <= ATOL + RTOL * max(Decimal(1), scale)


def _canonical_structure(circuit: Circuit,
                          diodes: dict[str, DiodeParams],
                          bjts: dict[str, BJTParams] | None = None,
                          mosfets: dict[str, MOSParams] | None = None,
                          jfets: dict[str, JFETParams] | None = None,
                          variants: dict[str, DiodeVariantParams] | None = None
                          ) -> dict:
    entries = []
    for c in circuit.components:
        entry = {
            "ref": c.ref,
            "type": c.type.upper(),
            "value_base_units": (str(c.value.to_base())
                                 if c.value is not None else None),
            "pins": dict(sorted(c.pins.items())),
        }
        if c.type.upper() in DEPENDENT_TYPES:
            entry["control"] = {
                k: str(v) for k, v in sorted(
                    dict(c.parameters or {}).items(), key=lambda kv: kv[0])
            }
        if c.type.upper() == "D":
            if variants and c.ref.upper() in variants:
                vp = variants[c.ref.upper()]
                entry["model"] = {
                    "kind": vp.kind,
                    "Is_A": str(vp.Is),
                    "n": str(vp.n),
                    "Vt_V": str(vp.Vt),
                    "Vz_V": str(vp.Vz) if vp.Vz is not None else None,
                    "nz": str(vp.nz) if vp.nz is not None else None,
                    "Iz_A": str(vp.Iz) if vp.Iz is not None else None,
                    "Iph_A": str(vp.Iph) if vp.Iph is not None else None,
                }
            else:
                p = diodes[c.ref.upper()]
                entry["model"] = {
                    "kind": "Shockley",
                    "Is_A": str(p.Is),
                    "n": str(p.n),
                    "Vt_V": str(p.Vt),
                }
        if c.type.upper() == "Q" and bjts and c.ref.upper() in bjts:
            bp = bjts[c.ref.upper()]
            entry["model"] = {
                "kind": "Ebers-Moll",
                "polarity": bp.polarity,
                "Is_A": str(bp.Is),
                "Bf": str(bp.Bf),
                "Br": str(bp.Br),
                "Nf": str(bp.Nf),
                "Nr": str(bp.Nr),
                "Vt_V": str(bp.Vt),
            }
        if c.type.upper() == "M" and mosfets and c.ref.upper() in mosfets:
            mp = mosfets[c.ref.upper()]
            entry["model"] = {
                "kind": "Shichman-Hodges-L1",
                "polarity": mp.polarity,
                "Kp_A_per_V2": str(mp.Kp),
                "Vto_V": str(mp.Vto),
                "Lambda_per_V": str(mp.Lambda),
                "Phi_V": str(mp.Phi),
                "Gamma_sqrtV": str(mp.Gamma),
            }
        if c.type.upper() == "J" and jfets and c.ref.upper() in jfets:
            jp = jfets[c.ref.upper()]
            entry["model"] = {
                "kind": "JFET-square-law",
                "polarity": jp.polarity,
                "Idss_A": str(jp.Idss),
                "Vp_V": str(jp.Vp),
                "Lambda_per_V": str(jp.Lambda),
            }
        entries.append(entry)
    formulation = ("MNA residual F(x) = A0 x - b0 + D(x) + Q(x) + M(x) + J(x); "
                   "J = A0 + diode/bjt/mosfet/jfet stamps; damped Newton")
    return {
        "solver": ENGINE_VERSION,
        "formulation": formulation,
        "tolerances": {"rtol": str(RTOL), "atol": str(ATOL),
                       "stol": str(STOL)},
        "max_iterations": MAX_ITER,
        "max_backtracking": MAX_BACKTRACK,
        "initial_guess": "zero-vector",
        "circuit_name": circuit.name,
        "components": sorted(entries, key=lambda d: d["ref"]),
    }


def _digest_for(structure: dict) -> str:
    return hashlib.sha256(
        json.dumps(structure, sort_keys=True, default=str).encode()
    ).hexdigest()


class _NewtonSystem:
    """Residual/Jacobian assembly over a fixed ``MNAProblem``."""

    def __init__(self, problem: MNAProblem,
                  diodes: dict[str, DiodeParams],
                  bjts: dict[str, BJTParams] | None = None,
                  mosfets: dict[str, MOSParams] | None = None,
                  jfets: dict[str, JFETParams] | None = None,
                  variants: dict[str, DiodeVariantParams] | None = None,
                  ) -> None:
        self.problem = problem
        self.ctx = make_context()
        self.n = problem.size
        self.n_nodes = len(problem.nodes)
        self.diode_list = sorted(
            (c for c in problem.circuit.components
              if c.type.upper() == "D" and
              c.ref.upper() not in (variants or {})),
            key=lambda c: c.ref.upper(),
        )
        # E0.2 observation logs: None (default) = inert; set to [] only when an
        # observer is attached. They record (ref, Vd, I) of each Shockley diode
        # evaluation in residual() and (ref, Vd, g) in jacobian(), never alter them.
        self.device_log = None
        self.jac_log = None
        # E0.3: same contract for Ebers-Moll BJTs. bjt_log records
        # (ref, polarity, VC, VB, VE, V_F, V_R, IF, IR, IC, IB, IE) from inside
        # bjt_terminal_currents; bjt_jac_log records (ref, polarity, VC, VB, VE,
        # V_F, V_R, gF, gR, J3x3) from inside bjt_jacobian. None = inert.
        self.bjt_log = None
        self.bjt_jac_log = None
        # E0.4: same contract for the F8-K devices (diode kinds, MOSFET L1,
        # JFET), captured inside variant_current / mos_operating_point /
        # jfet_operating_point. fk_log: ("D", ref, kind, branch, Vd, I) |
        # ("M", ref, pol, VD, VG, VS, VB, VGS, VDS, VSB, region, IDM, gm, gds,
        # gmb_num, Vth, Vov, ID, IS) | ("J", ref, pol, VD, VG, VS, VGS, VDS,
        # region, IDM, gm, gds, ID, IS). fk_jac_log: ("D", ref, kind, branch,
        # Vd, g) | ("M"|"J", ref, pol, region, J block). None = inert.
        self.fk_log = None
        self.fk_jac_log = None
        self.models = {c.ref.upper(): diodes[c.ref.upper()]
                       for c in self.diode_list}
        self.a_index = {c.ref.upper(): problem.node_index.get(c.pins["A"])
                        for c in self.diode_list}
        self.k_index = {c.ref.upper(): problem.node_index.get(c.pins["K"])
                        for c in self.diode_list}
        self.variant_list = sorted(
            (c for c in problem.circuit.components
              if c.type.upper() == "D" and
              c.ref.upper() in (variants or {})),
            key=lambda c: c.ref.upper(),
        )
        self.variant_models = {c.ref.upper(): (variants or {})[c.ref.upper()]
                               for c in self.variant_list}
        self.va_index = {c.ref.upper(): problem.node_index.get(c.pins["A"])
                         for c in self.variant_list}
        self.vk_index = {c.ref.upper(): problem.node_index.get(c.pins["K"])
                         for c in self.variant_list}

        self.bjt_list = sorted(
            (c for c in problem.circuit.components
             if c.type.upper() == "Q"),
            key=lambda c: c.ref.upper(),
        )
        self.bjt_models = {c.ref.upper(): bjts[c.ref.upper()]
                           for c in self.bjt_list} if bjts else {}
        self.c_index = {c.ref.upper(): problem.node_index.get(c.pins["C"])
                        for c in self.bjt_list}
        self.b_index = {c.ref.upper(): problem.node_index.get(c.pins["B"])
                        for c in self.bjt_list}
        self.e_index = {c.ref.upper(): problem.node_index.get(c.pins["E"])
                        for c in self.bjt_list}

        self.mos_list = sorted(
            (c for c in problem.circuit.components
              if c.type.upper() == "M"),
            key=lambda c: c.ref.upper(),
        )
        self.mos_models = {c.ref.upper(): (mosfets or {})[c.ref.upper()]
                           for c in self.mos_list}
        self.md_index = {c.ref.upper(): problem.node_index.get(c.pins["D"])
                         for c in self.mos_list}
        self.mg_index = {c.ref.upper(): problem.node_index.get(c.pins["G"])
                         for c in self.mos_list}
        self.ms_index = {c.ref.upper(): problem.node_index.get(c.pins["S"])
                         for c in self.mos_list}
        self.mb_index = {c.ref.upper(): problem.node_index.get(c.pins["B"])
                         for c in self.mos_list}

        self.jfet_list = sorted(
            (c for c in problem.circuit.components
              if c.type.upper() == "J"),
            key=lambda c: c.ref.upper(),
        )
        self.jfet_models = {c.ref.upper(): (jfets or {})[c.ref.upper()]
                            for c in self.jfet_list}
        self.jd_index = {c.ref.upper(): problem.node_index.get(c.pins["D"])
                         for c in self.jfet_list}
        self.jg_index = {c.ref.upper(): problem.node_index.get(c.pins["G"])
                         for c in self.jfet_list}
        self.js_index = {c.ref.upper(): problem.node_index.get(c.pins["S"])
                         for c in self.jfet_list}

        self.a0 = tuple(
            tuple(_decimal_of(v) for v in row) for row in problem.matrix)
        self.b0 = tuple(_decimal_of(v) for v in problem.rhs)

    def _x_of(self, x: tuple[Decimal, ...], idx: int | None) -> Decimal:
        return Decimal(0) if idx is None else x[idx]

    def residual(self, x: tuple[Decimal, ...]
                  ) -> tuple[Decimal, ...] | None:
        """``F(x)``; ``None`` if any device evaluation is non-finite."""
        ctx = self.ctx
        try:
            acc = []
            for i in range(self.n):
                total = Decimal(0)
                row = self.a0[i]
                for j in range(self.n):
                    total = ctx.add(total, ctx.multiply(row[j], x[j]))
                acc.append(ctx.subtract(total, self.b0[i]))
            if self.device_log is not None:
                self.device_log = []
            if self.bjt_log is not None:
                self.bjt_log = []
            if self.fk_log is not None:
                self.fk_log = []
            for ref in self.models:
                p = self.models[ref]
                vd = ctx.subtract(self._x_of(x, self.a_index[ref]),
                                  self._x_of(x, self.k_index[ref]))
                ival, _, _ = companion(vd, p, ctx)
                if not ival.is_finite():
                    return None
                if self.device_log is not None:
                    self.device_log.append((ref, vd, ival))
                ia, ik = self.a_index[ref], self.k_index[ref]
                if ia is not None:
                    acc[ia] = ctx.add(acc[ia], ival)
                if ik is not None:
                    acc[ik] = ctx.subtract(acc[ik], ival)
            for ref in self.variant_models:
                p = self.variant_models[ref]
                vd = ctx.subtract(self._x_of(x, self.va_index[ref]),
                                  self._x_of(x, self.vk_index[ref]))
                probe = [] if self.fk_log is not None else None
                ival, _, _ = variant_companion(vd, p, ctx, probe)
                if not ival.is_finite():
                    return None
                if probe:
                    self.fk_log.append(("D", ref, p.kind, probe[0], vd, ival))
                ia, ik = self.va_index[ref], self.vk_index[ref]
                if ia is not None:
                    acc[ia] = ctx.add(acc[ia], ival)
                if ik is not None:
                    acc[ik] = ctx.subtract(acc[ik], ival)
            for ref in self.bjt_models:
                bp = self.bjt_models[ref]
                vc = self._x_of(x, self.c_index[ref])
                vb = self._x_of(x, self.b_index[ref])
                ve = self._x_of(x, self.e_index[ref])
                probe = [] if self.bjt_log is not None else None
                ic, ib, ie = bjt_terminal_currents(vc, vb, ve, bp, ctx, probe)
                if not (ic.is_finite() and ib.is_finite() and ie.is_finite()):
                    return None
                if probe:
                    self.bjt_log.append((ref, bp.polarity, vc, vb, ve, *probe[0], ic, ib, ie))
                ic_idx = self.c_index[ref]
                ib_idx = self.b_index[ref]
                ie_idx = self.e_index[ref]
                if ic_idx is not None:
                    acc[ic_idx] = ctx.add(acc[ic_idx], ic)
                if ib_idx is not None:
                    acc[ib_idx] = ctx.add(acc[ib_idx], ib)
                if ie_idx is not None:
                    acc[ie_idx] = ctx.add(acc[ie_idx], ie)
            for ref in self.mos_models:
                mp = self.mos_models[ref]
                vd = self._x_of(x, self.md_index[ref])
                vg = self._x_of(x, self.mg_index[ref])
                vs = self._x_of(x, self.ms_index[ref])
                vb = self._x_of(x, self.mb_index[ref])
                probe = [] if self.fk_log is not None else None
                idc, ig, isc, ib = mos_terminal_currents(
                    vd, vg, vs, vb, mp, ctx, probe)
                if not all(v.is_finite() for v in (idc, ig, isc, ib)):
                    return None
                if probe:
                    vgs, vds, vsb, op = probe[0]
                    self.fk_log.append(("M", ref, mp.polarity, vd, vg, vs, vb, vgs, vds, vsb,
                                        *op, idc, isc))
                for idx, cur in ((self.md_index[ref], idc),
                                 (self.mg_index[ref], ig),
                                 (self.ms_index[ref], isc),
                                 (self.mb_index[ref], ib)):
                    if idx is not None:
                        acc[idx] = ctx.add(acc[idx], cur)
            for ref in self.jfet_models:
                jp = self.jfet_models[ref]
                vd = self._x_of(x, self.jd_index[ref])
                vg = self._x_of(x, self.jg_index[ref])
                vs = self._x_of(x, self.js_index[ref])
                probe = [] if self.fk_log is not None else None
                idc, ig, isc = jfet_terminal_currents(vd, vg, vs, jp, ctx, probe)
                if not all(v.is_finite() for v in (idc, ig, isc)):
                    return None
                if probe:
                    vgs, vds, op = probe[0]
                    self.fk_log.append(("J", ref, jp.polarity, vd, vg, vs, vgs, vds, *op, idc, isc))
                for idx, cur in ((self.jd_index[ref], idc),
                                 (self.jg_index[ref], ig),
                                 (self.js_index[ref], isc)):
                    if idx is not None:
                        acc[idx] = ctx.add(acc[idx], cur)
            if not all(v.is_finite() for v in acc):
                return None
            return tuple(acc)
        except (Overflow, InvalidOperation):
            return None

    def jacobian(self, x: tuple[Decimal, ...]
                  ) -> list[list[Decimal]] | None:
        """``J(x)``; ``None`` if any device evaluation is non-finite."""
        ctx = self.ctx
        try:
            rows = [list(r) for r in self.a0]
            if self.jac_log is not None:
                self.jac_log = []
            if self.bjt_jac_log is not None:
                self.bjt_jac_log = []
            if self.fk_jac_log is not None:
                self.fk_jac_log = []
            for ref in self.models:
                p = self.models[ref]
                vd = ctx.subtract(self._x_of(x, self.a_index[ref]),
                                  self._x_of(x, self.k_index[ref]))
                _, gval, _ = companion(vd, p, ctx)
                if not gval.is_finite():
                    return None
                if self.jac_log is not None:
                    self.jac_log.append((ref, vd, gval))
                ia, ik = self.a_index[ref], self.k_index[ref]
                if ia is not None:
                    rows[ia][ia] = ctx.add(rows[ia][ia], gval)
                if ik is not None:
                    rows[ik][ik] = ctx.add(rows[ik][ik], gval)
                if ia is not None and ik is not None:
                    rows[ia][ik] = ctx.subtract(rows[ia][ik], gval)
                    rows[ik][ia] = ctx.subtract(rows[ik][ia], gval)
            for ref in self.variant_models:
                p = self.variant_models[ref]
                vd = ctx.subtract(self._x_of(x, self.va_index[ref]),
                                  self._x_of(x, self.vk_index[ref]))
                probe = [] if self.fk_jac_log is not None else None
                _, gval, _ = variant_companion(vd, p, ctx, probe)
                if not gval.is_finite():
                    return None
                if probe:
                    self.fk_jac_log.append(("D", ref, p.kind, probe[0], vd, gval))
                ia, ik = self.va_index[ref], self.vk_index[ref]
                if ia is not None:
                    rows[ia][ia] = ctx.add(rows[ia][ia], gval)
                if ik is not None:
                    rows[ik][ik] = ctx.add(rows[ik][ik], gval)
                if ia is not None and ik is not None:
                    rows[ia][ik] = ctx.subtract(rows[ia][ik], gval)
                    rows[ik][ia] = ctx.subtract(rows[ik][ia], gval)
            for ref in self.bjt_models:
                bp = self.bjt_models[ref]
                vc = self._x_of(x, self.c_index[ref])
                vb = self._x_of(x, self.b_index[ref])
                ve = self._x_of(x, self.e_index[ref])
                probe = [] if self.bjt_jac_log is not None else None
                bjt_j = bjt_jacobian(vc, vb, ve, bp, ctx, probe)
                if bjt_j is None:
                    return None
                if probe:
                    self.bjt_jac_log.append((ref, bp.polarity, vc, vb, ve, *probe[0], bjt_j))
                c_idx = self.c_index[ref]
                b_idx = self.b_index[ref]
                e_idx = self.e_index[ref]
                nodes = (c_idx, b_idx, e_idx)
                for r_i in range(3):
                    n_r = nodes[r_i]
                    if n_r is None:
                        continue
                    for c_j in range(3):
                        n_c = nodes[c_j]
                        if n_c is None:
                            continue
                        rows[n_r][n_c] = ctx.add(rows[n_r][n_c], bjt_j[r_i][c_j])
            for ref in self.mos_models:
                mp = self.mos_models[ref]
                vd = self._x_of(x, self.md_index[ref])
                vg = self._x_of(x, self.mg_index[ref])
                vs = self._x_of(x, self.ms_index[ref])
                vb = self._x_of(x, self.mb_index[ref])
                probe = [] if self.fk_jac_log is not None else None
                mos_j = mos_jacobian(vd, vg, vs, vb, mp, ctx, probe)
                if mos_j is None:
                    return None
                if probe:
                    self.fk_jac_log.append(("M", ref, mp.polarity, probe[0][3][0], mos_j))
                mos_nodes = (self.md_index[ref], self.mg_index[ref],
                             self.ms_index[ref], self.mb_index[ref])
                for r_i in range(4):
                    n_r = mos_nodes[r_i]
                    if n_r is None:
                        continue
                    for c_j in range(4):
                        n_c = mos_nodes[c_j]
                        if n_c is None:
                            continue
                        rows[n_r][n_c] = ctx.add(rows[n_r][n_c],
                                                 mos_j[r_i][c_j])
            for ref in self.jfet_models:
                jp = self.jfet_models[ref]
                vd = self._x_of(x, self.jd_index[ref])
                vg = self._x_of(x, self.jg_index[ref])
                vs = self._x_of(x, self.js_index[ref])
                probe = [] if self.fk_jac_log is not None else None
                jfet_j = jfet_jacobian(vd, vg, vs, jp, ctx, probe)
                if jfet_j is None:
                    return None
                if probe:
                    self.fk_jac_log.append(("J", ref, jp.polarity, probe[0][2][0], jfet_j))
                jfet_nodes = (self.jd_index[ref], self.jg_index[ref],
                              self.js_index[ref])
                for r_i in range(3):
                    n_r = jfet_nodes[r_i]
                    if n_r is None:
                        continue
                    for c_j in range(3):
                        n_c = jfet_nodes[c_j]
                        if n_c is None:
                            continue
                        rows[n_r][n_c] = ctx.add(rows[n_r][n_c],
                                                 jfet_j[r_i][c_j])
            for r in rows:
                if not all(v.is_finite() for v in r):
                    return None
            return rows
        except (Overflow, InvalidOperation):
            return None

    def block_norms(self, f: tuple[Decimal, ...]
                    ) -> tuple[Decimal, Decimal]:
        """``(max|F_kcl|, max|F_aux|)`` over node rows / aux rows."""
        kcl = [abs(v) for v in f[:self.n_nodes]]
        aux = [abs(v) for v in f[self.n_nodes:]]
        zero = Decimal(0)
        return (max(kcl) if kcl else zero, max(aux) if aux else zero)

    def scale_of(self, x: tuple[Decimal, ...]) -> Decimal:
        peak = max([abs(v) for v in x] or [Decimal(0)])
        return max(Decimal(1), peak)


@dataclass(frozen=True)
class NewtonState:
    """Converged Newton state exposed for F8-M (R-01).

    ``system`` is the certified residual/Jacobian assembly
    (``residual(x)`` / ``jacobian(x)``), ``x`` the converged unknown
    vector (nodes, then aux currents in ``problem.vsource_index`` order).
    Read-only view: nothing here alters solver behaviour.
    """

    problem: MNAProblem
    system: "_NewtonSystem"
    x: tuple[Decimal, ...]


def _fk_parameters(system) -> tuple:
    """E0.4: the F8-K model parameters the solver uses (immutable snapshot)."""
    out = [("D", ref, p.kind, p.Is, p.n, p.Vt, p.Vz, p.nz, p.Iz, p.Iph)
           for ref, p in system.variant_models.items()]
    out += [("M", ref, p.polarity, p.Kp, p.Vto, p.Lambda, p.Phi, p.Gamma)
            for ref, p in system.mos_models.items()]
    out += [("J", ref, p.polarity, p.Idss, p.Vp, p.Lambda)
            for ref, p in system.jfet_models.items()]
    return tuple(out)


def solve_nonlinear_dc(circuit: Circuit, *,
                        max_iter: int = MAX_ITER,
                        x_init: "tuple[Decimal, ...] | None" = None,
                        observer=None,
                        ) -> NonlinearResult:
    """DC operating point with Shockley diodes (F8-H), Ebers-Moll BJTs
    (F8-I) and F8-K devices (MOSFET, JFET, diode-kind variants) via
    damped Newton.

    ``max_iter`` override exists for honest ``MAX_ITERATIONS``
    testing; provenance always records the effective value.

    ``x_init`` (F8-M R-02) is an optional warm-start vector (length
    ``n_unknowns``, finite ``Decimal`` entries). ``None`` (default) keeps
    the certified zero-vector start bit-for-bit. Convergence policy (Q1)
    is unchanged either way.

    ``observer`` (E0.1, optional, default None) is told the facts of the
    real iteration: ``newton_start(nodes, x, kcl, aux, scale, *, unknowns,
    residual)`` once and ``newton_iteration(it, alpha, halvings, step_peak,
    x, kcl, aux, scale, res_ok, step_ok, *, x_prev, residual_prev,
    jacobian, dx, residual, trials, reference, devices,
    device_conductances)`` after every accepted step (E0.1-R+: full
    vectors and the Jacobian actually used; E0.2: every backtracking trial
    as (α, trial residual norm or None, accepted), the norm to beat, and
    the Shockley evaluations (ref, Vd, I) at x_(k+1) and (ref, Vd, g) at
    x_k). ``newton_start`` also receives ``devices`` and
    ``diode_parameters`` (ref, Is, n, Vt); ``newton_failed(it, reason,
    trials)`` reports an in-loop failure. E0.3: ``newton_start`` also
    receives ``bjt_parameters`` (ref, polarity, Is, Bf, Br, Nf, Nr, Vt,
    alphaF, alphaR) and ``bjt_devices``; ``newton_iteration`` receives
    ``bjt_devices`` (Ebers-Moll evaluation at x_(k+1)) and ``bjt_jacobians``
    (gF, gR and the 3x3 block at x_k). E0.4: likewise ``fk_parameters`` /
    ``fk_devices`` (start, x_(k+1)) and ``fk_jacobians`` (x_k) for the F8-K
    devices (see ``_NewtonSystem.fk_log``). Every argument is an immutable
    snapshot (tuples of Decimal), built only when an observer is present.
    It never alters the solve.
    """
    return _solve_nonlinear_dc_impl(circuit, max_iter, x_init, None, observer)


def solve_nonlinear_dc_state(circuit: Circuit, *,
                              max_iter: int = MAX_ITER,
                              x_init: "tuple[Decimal, ...] | None" = None,
                              observer=None,
                              ) -> "tuple[NonlinearResult, NewtonState | None]":
    """Same solve as :func:`solve_nonlinear_dc`, additionally returning the
    converged :class:`NewtonState` (``None`` unless ``CONVERGED``).
    ``observer`` (E0.3, optional) has the :func:`solve_nonlinear_dc` contract."""
    capture: dict = {}
    result = _solve_nonlinear_dc_impl(circuit, max_iter, x_init, capture, observer)
    if result.status is NonlinearStatus.CONVERGED and capture:
        return result, NewtonState(capture["problem"], capture["system"],
                                    capture["x"])
    return result, None


def _solve_nonlinear_dc_impl(circuit: Circuit, max_iter: int,
                              x_init: "tuple[Decimal, ...] | None",
                              capture: "dict | None",
                              observer=None) -> NonlinearResult:
    if not isinstance(max_iter, int) or isinstance(max_iter, bool) \
            or max_iter < 0:
        return NonlinearResult(
            status=NonlinearStatus.INVALID,
            diagnostics=("max_iter must be a non-negative int",),
        )
    try:
        problem = build_mna_problem(circuit, allow_diodes=True,
                                    allow_bjts=True, allow_mosfets=True,
                                    allow_jfets=True,
                                    allow_diode_variants=True)
    except UnsupportedElementError as exc:
        return NonlinearResult(status=NonlinearStatus.UNSUPPORTED,
                                diagnostics=(str(exc),))
    except _INVALID_ERRORS as exc:
        return NonlinearResult(status=NonlinearStatus.INVALID,
                                diagnostics=(str(exc),))
    try:
        from academic_core.domain.engineering.mna.diode import PARAM_KIND
        diodes = {c.ref.upper(): extract_diode_params(c)
                  for c in circuit.components
                  if c.type.upper() == "D" and
                  PARAM_KIND not in (c.parameters or {})}
        variants = {c.ref.upper(): extract_diode_variant_params(c)
                    for c in circuit.components
                    if c.type.upper() == "D" and
                    PARAM_KIND in (c.parameters or {})}
        bjts = {c.ref.upper(): extract_bjt_params(c)
                for c in circuit.components if c.type.upper() == "Q"}
        mosfets = {c.ref.upper(): extract_mosfet_params(c)
                   for c in circuit.components if c.type.upper() == "M"}
        jfets = {c.ref.upper(): extract_jfet_params(c)
                 for c in circuit.components if c.type.upper() == "J"}
    except InvalidCircuitError as exc:
        return NonlinearResult(status=NonlinearStatus.INVALID,
                                diagnostics=(str(exc),))

    system = _NewtonSystem(problem, diodes, bjts, mosfets, jfets, variants)
    ctx = system.ctx
    n = system.n
    x: tuple[Decimal, ...] = tuple(Decimal(0) for _ in range(n))
    if x_init is not None:
        if (not isinstance(x_init, (tuple, list)) or len(x_init) != n
                or not all(isinstance(v, Decimal) and v.is_finite()
                           for v in x_init)):
            return NonlinearResult(
                status=NonlinearStatus.INVALID,
                diagnostics=(f"x_init must be a length-{n} sequence of "
                             f"finite Decimal",))
        x = tuple(x_init)
    diagnostics: list[str] = [
        f"engine={ENGINE_VERSION}",
        f"n_unknowns={n}",
        f"n_diodes={len(diodes)}",
        f"n_bjts={len(bjts)}",
        f"n_mosfets={len(mosfets)}",
        f"n_jfets={len(jfets)}",
        f"n_diode_variants={len(variants)}",
        ("initial_guess=zero-vector (deterministic)" if x_init is None
         else "initial_guess=x_init (warm-start, F8-M R-02)"),
        f"tolerances: rtol={RTOL} atol={ATOL} stol={STOL}",
        f"max_iter={max_iter} max_backtracking={MAX_BACKTRACK}",
    ]
    warnings: list[str] = []
    backtrack_uses = 0
    if observer is not None:
        system.device_log, system.jac_log = [], []
        system.bjt_log, system.bjt_jac_log = [], []
        system.fk_log, system.fk_jac_log = [], []

    def _failed(reason: str, trials=()) -> None:
        if observer is not None:
            observer.newton_failed(it, reason, tuple(trials))

    f0 = system.residual(x)
    if f0 is None:
        return NonlinearResult(
            status=NonlinearStatus.DIVERGED,
            system_summary=_summary(problem, diodes, bjts, mosfets, jfets,
                                      variants, 0),
            provenance=_provenance(problem, diodes, bjts, mosfets, jfets,
                                   variants, max_iter, 0,
                                   NonlinearStatus.DIVERGED, f0,
                                   backtrack_uses, warnings),
            diagnostics=tuple(diagnostics + [
                "initial residual non-finite: cannot start Newton",
            ]),
        )
    k0, a0n = system.block_norms(f0)
    scale = system.scale_of(x)
    if observer is not None:
        from academic_core.domain.engineering.mna.problem import unknown_labels
        observer.newton_start(problem.nodes, x[:system.n_nodes], k0, a0n, scale,
                              unknowns=unknown_labels(problem), residual=tuple(f0),
                              devices=tuple(system.device_log),
                              diode_parameters=tuple((ref, system.models[ref].Is, system.models[ref].n,
                                                      system.models[ref].Vt) for ref in system.models),
                              bjt_parameters=tuple((ref, b.polarity, b.Is, b.Bf, b.Br, b.Nf, b.Nr, b.Vt,
                                                    b.alphaF, b.alphaR)
                                                   for ref, b in system.bjt_models.items()),
                              bjt_devices=tuple(system.bjt_log),
                              fk_parameters=_fk_parameters(system),
                              fk_devices=tuple(system.fk_log))
    if _block_ok(list(f0[:system.n_nodes]), scale) and \
            _block_ok(list(f0[system.n_nodes:]), scale):
        if capture is not None:
            capture.update(problem=problem, system=system, x=x)
        return _warm_tag(_converged_result(
            problem, system, diodes, bjts, mosfets, jfets, variants,
            x, f0, 0, max_iter, backtrack_uses,
            warnings, diagnostics, initial=(k0, a0n)), x_init, n)

    it = 0
    final_f = f0
    final_pair = (k0, a0n)
    while it < max_iter:
        jac = system.jacobian(x)
        jac_devices = tuple(system.jac_log) if observer is not None and jac is not None else ()
        jac_bjts = tuple(system.bjt_jac_log) if observer is not None and jac is not None else ()
        jac_fk = tuple(system.fk_jac_log) if observer is not None and jac is not None else ()
        if jac is None:
            _failed("DIVERGED: Jacobian evaluation non-finite")
            return NonlinearResult(
                status=NonlinearStatus.DIVERGED,
                system_summary=_summary(problem, diodes, bjts, mosfets, jfets, variants, it),
                provenance=_provenance(problem, diodes, bjts, mosfets, jfets, variants, max_iter, it,
                                       NonlinearStatus.DIVERGED, final_f,
                                       backtrack_uses, warnings),
                diagnostics=tuple(diagnostics + [
                    f"iter {it}: Jacobian evaluation non-finite "
                    f"(exp overflow at current iterate)",
                ]),
            )
        try:
            lin = linsolve(
                ComplexLinearProblem.from_sequences(
                    jac, [ctx.minus(v) for v in final_f]),
                NumericMode.HIGH_PRECISION,
            )
        except Exception as exc:
            _failed("DIVERGED: linear-solve entry refused")
            return NonlinearResult(
                status=NonlinearStatus.DIVERGED,
                system_summary=_summary(problem, diodes, bjts, mosfets, jfets, variants, it),
                provenance=_provenance(problem, diodes, bjts, mosfets, jfets, variants, max_iter, it,
                                       NonlinearStatus.DIVERGED, final_f,
                                       backtrack_uses, warnings),
                diagnostics=tuple(diagnostics + [
                    f"iter {it}: linear-solve entry refused: {exc}",
                ]),
            )
        if lin.status in (LinearStatus.SINGULAR, LinearStatus.INCONSISTENT):
            _failed(f"SINGULAR_JACOBIAN: {lin.status.value}")
            return NonlinearResult(
                status=NonlinearStatus.SINGULAR_JACOBIAN,
                system_summary=_summary(problem, diodes, bjts, mosfets, jfets, variants, it),
                provenance=_provenance(problem, diodes, bjts, mosfets, jfets, variants, max_iter, it,
                                       NonlinearStatus.SINGULAR_JACOBIAN,
                                       final_f, backtrack_uses, warnings),
                diagnostics=tuple(diagnostics + [
                    f"iter {it}: Jacobian {lin.status.value} "
                    f"(rank {lin.rank_A}/{n}): Newton step undefined",
                ]),
            )
        if lin.status != LinearStatus.SOLVED or lin.solution is None:
            _failed("DIVERGED: Newton step not certified")
            return NonlinearResult(
                status=NonlinearStatus.DIVERGED,
                system_summary=_summary(problem, diodes, bjts, mosfets, jfets, variants, it),
                provenance=_provenance(problem, diodes, bjts, mosfets, jfets, variants, max_iter, it,
                                       NonlinearStatus.DIVERGED, final_f,
                                       backtrack_uses, warnings),
                diagnostics=tuple(diagnostics + [
                    f"iter {it}: Newton step not certified "
                    f"(linsolve: {lin.status.value})",
                ]),
            )
        dx = tuple(entry.re for entry in lin.solution)
        cur = max(final_pair)
        alpha = Decimal(1)
        halvings = 0
        accepted: tuple[Decimal, ...] | None = None
        accepted_f: tuple[Decimal, ...] | None = None
        trials: list = []  # E0.2: (alpha, trial residual norm or None, accepted), filled only with an observer
        devices_next: tuple = ()
        bjts_next: tuple = ()
        fk_next: tuple = ()
        for halvings in range(MAX_BACKTRACK + 1):
            trial = tuple(
                ctx.add(xv, ctx.multiply(alpha, dv))
                for xv, dv in zip(x, dx))
            ft = system.residual(trial)
            if ft is not None:
                kt, at = system.block_norms(ft)
                if max(kt, at) < cur:
                    accepted, accepted_f = trial, ft
                    if observer is not None:
                        trials.append((alpha, max(kt, at), True))
                        devices_next = tuple(system.device_log)
                        bjts_next = tuple(system.bjt_log)
                        fk_next = tuple(system.fk_log)
                    break
                # SOLVER-EXT-01 (F8-K): exact-flat-region standstill.
                # Piecewise devices (MOSFET/JFET cutoff, diode-kind
                # branches) can make the residual EXACTLY zero while the
                # Newton correction is not yet tolerance-small. Strict
                # decrease from exactly 0 is impossible, so the next
                # iterate would be misreported as stagnation. Accept a
                # non-increasing trial ONLY when it already satisfies the
                # certified block tolerances: the convergence certificate
                # below (res_ok AND step_ok, same RTOL/ATOL/STOL) is
                # unchanged, every state-changing step still strictly
                # decreases, and the iteration budget still bounds the
                # loop. D/Q-only paths are unaffected (their residuals
                # never hit exact zero through exp-based branches).
                scale_t = system.scale_of(trial)
                if max(kt, at) <= cur and \
                        _block_ok(list(ft[:system.n_nodes]), scale_t) and \
                        _block_ok(list(ft[system.n_nodes:]), scale_t):
                    accepted, accepted_f = trial, ft
                    if observer is not None:
                        trials.append((alpha, max(kt, at), True))
                        devices_next = tuple(system.device_log)
                        bjts_next = tuple(system.bjt_log)
                        fk_next = tuple(system.fk_log)
                    break
            if observer is not None:
                trials.append((alpha, None if ft is None else max(system.block_norms(ft)), False))
            alpha = ctx.divide(alpha, Decimal(2))
        if accepted is None or accepted_f is None:
            _failed("DIVERGED: backtracking exhausted", trials)
            return NonlinearResult(
                status=NonlinearStatus.DIVERGED,
                system_summary=_summary(problem, diodes, bjts, mosfets, jfets, variants, it),
                provenance=_provenance(problem, diodes, bjts, mosfets, jfets, variants, max_iter, it,
                                       NonlinearStatus.DIVERGED, final_f,
                                       backtrack_uses, warnings),
                diagnostics=tuple(diagnostics + [
                    f"iter {it}: backtracking exhausted "
                    f"({MAX_BACKTRACK + 1} halvings, no residual decrease): "
                    f"stagnation",
                ]),
            )
        x_prev, f_prev = x, final_f
        if alpha < 1:
            backtrack_uses += 1
        step_peak = max([abs(ctx.multiply(alpha, dv)) for dv in dx]
                        or [Decimal(0)])
        x = accepted
        final_f = accepted_f
        final_pair = system.block_norms(final_f)
        it += 1
        scale = system.scale_of(x)
        res_ok = _block_ok(list(final_f[:system.n_nodes]), scale) and \
            _block_ok(list(final_f[system.n_nodes:]), scale)
        step_ok = step_peak <= STOL + RTOL * scale
        if observer is not None:
            observer.newton_iteration(it, alpha, halvings, step_peak, x[:system.n_nodes], final_pair[0],
                                      final_pair[1], scale, res_ok, step_ok,
                                      x_prev=tuple(x_prev), residual_prev=tuple(f_prev),
                                      jacobian=tuple(tuple(r) for r in jac), dx=tuple(dx),
                                      residual=tuple(final_f), trials=tuple(trials), reference=cur,
                                      devices=devices_next, device_conductances=jac_devices,
                                      bjt_devices=bjts_next, bjt_jacobians=jac_bjts,
                                      fk_devices=fk_next, fk_jacobians=jac_fk)
        if res_ok and step_ok:
            if capture is not None:
                capture.update(problem=problem, system=system, x=x)
            return _warm_tag(_converged_result(
                problem, system, diodes, bjts, mosfets, jfets, variants,
                x, final_f, it, max_iter,
                backtrack_uses, warnings, diagnostics,
                initial=(k0, a0n)), x_init, n)
    return NonlinearResult(
        status=NonlinearStatus.MAX_ITERATIONS,
        system_summary=_summary(problem, diodes, bjts, mosfets, jfets,
                                  variants, it),
        provenance=_provenance(problem, diodes, bjts, mosfets, jfets,
                               variants, max_iter, it,
                               NonlinearStatus.MAX_ITERATIONS, final_f,
                               backtrack_uses, warnings),
        diagnostics=tuple(diagnostics + [
            f"iteration budget exhausted ({max_iter}): residual "
            f"kcl={final_pair[0]} aux={final_pair[1]}",
        ]),
    )


def _warm_tag(result: NonlinearResult, x_init, n: int) -> NonlinearResult:
    """Record a warm start in provenance (no-op for the default start)."""
    if x_init is not None:
        result.provenance["initial_guess"] = {
            "strategy": "x_init (warm-start)", "n_unknowns": n}
    return result


def _summary(problem: MNAProblem, diodes: dict[str, DiodeParams],
              bjts: dict[str, BJTParams] | None,
              mosfets: dict[str, MOSParams] | None,
              jfets: dict[str, JFETParams] | None,
              variants: dict[str, DiodeVariantParams] | None,
              iters: int) -> dict:
    summary = {
        "n_nodes": len(problem.nodes),
        "n_voltage_sources": len(problem.vsource_refs),
        "n_unknowns": problem.size,
        "reference_node": problem.ground,
        "iterations": iters,
    }
    if diodes:
        summary["diodes"] = [
            {"ref": c.ref, "anode": c.pins["A"], "cathode": c.pins["K"]}
            for c in sorted(
                (c for c in problem.circuit.components
                  if c.type.upper() == "D" and
                  c.ref.upper() not in (variants or {})),
                key=lambda c: c.ref.upper())
        ]
    if variants:
        summary["diode_variants"] = [
            {"ref": c.ref, "anode": c.pins["A"], "cathode": c.pins["K"],
             "kind": variants[c.ref.upper()].kind}
            for c in sorted(
                (c for c in problem.circuit.components
                  if c.type.upper() == "D" and
                  c.ref.upper() in variants),
                key=lambda c: c.ref.upper())
        ]
    if bjts:
        summary["bjts"] = [
            {"ref": c.ref, "collector": c.pins["C"], "base": c.pins["B"],
             "emitter": c.pins["E"], "polarity": bjts[c.ref.upper()].polarity}
            for c in sorted(
                (c for c in problem.circuit.components
                  if c.type.upper() == "Q"),
                key=lambda c: c.ref.upper())
        ]
    if mosfets:
        summary["mosfets"] = [
            {"ref": c.ref, "drain": c.pins["D"], "gate": c.pins["G"],
             "source": c.pins["S"], "bulk": c.pins["B"],
             "polarity": mosfets[c.ref.upper()].polarity}
            for c in sorted(
                (c for c in problem.circuit.components
                  if c.type.upper() == "M"),
                key=lambda c: c.ref.upper())
        ]
    if jfets:
        summary["jfets"] = [
            {"ref": c.ref, "drain": c.pins["D"], "gate": c.pins["G"],
             "source": c.pins["S"],
             "polarity": jfets[c.ref.upper()].polarity}
            for c in sorted(
                (c for c in problem.circuit.components
                  if c.type.upper() == "J"),
                key=lambda c: c.ref.upper())
        ]
    return summary


def _provenance(problem: MNAProblem, diodes: dict[str, DiodeParams],
                 bjts: dict[str, BJTParams] | None,
                 mosfets: dict[str, MOSParams] | None,
                 jfets: dict[str, JFETParams] | None,
                 variants: dict[str, DiodeVariantParams] | None,
                 max_iter: int, iters: int, status: NonlinearStatus,
                 final_f: tuple[Decimal, ...] | None, backtracks: int,
                 warnings: list[str]) -> dict:
    struct = _canonical_structure(problem.circuit, diodes, bjts, mosfets,
                                  jfets, variants)
    kf, af = (None, None)
    if final_f is not None:
        n_nodes = len(problem.nodes)
        kf = str(max([abs(v) for v in final_f[:n_nodes]]
                     or [Decimal(0)]))
        af = str(max([abs(v) for v in final_f[n_nodes:]]
                     or [Decimal(0)]))
    model_name = "+".join(
        name for present, name in (
            (bool(diodes), "Shockley"),
            (bool(bjts), "Ebers-Moll"),
            (bool(mosfets), "Shichman-Hodges-L1"),
            (bool(jfets), "JFET-square-law"),
            (bool(variants), "D-kind"),
        ) if present) or "linear-only"
    prov = {
        "engine": ENGINE_VERSION,
        "model": model_name,
        "diode_parameters": {
            ref: {"Is_A": str(p.Is), "n": str(p.n), "Vt_V": str(p.Vt)}
            for ref, p in sorted(diodes.items())
        },
        "initial_guess": {"strategy": "zero-vector",
                          "n_unknowns": problem.size},
        "tolerances": {"rtol": str(RTOL), "atol": str(ATOL),
                       "stol": str(STOL)},
        "max_iterations": max_iter,
        "max_backtracking": MAX_BACKTRACK,
        "iterations": iters,
        "backtracking_uses": backtracks,
        "final_status": status.value,
        "final_residual_kcl_A": kf,
        "final_residual_aux_V": af,
        "warnings": list(warnings),
        "topology_digest": _digest_for(struct),
        "solver_digest": _digest_for({
            "engine": ENGINE_VERSION,
            "tolerances": {"rtol": str(RTOL), "atol": str(ATOL),
                           "stol": str(STOL)},
            "max_iterations": max_iter,
            "iterations": iters,
            "status": status.value,
            "final_residual_kcl_A": kf,
            "final_residual_aux_V": af,
        }),
    }
    if bjts:
        prov["bjt_parameters"] = {
            ref: {
                "polarity": bp.polarity,
                "Is_A": str(bp.Is),
                "Bf": str(bp.Bf),
                "Br": str(bp.Br),
                "Nf": str(bp.Nf),
                "Nr": str(bp.Nr),
                "Vt_V": str(bp.Vt),
            }
            for ref, bp in sorted(bjts.items())
        }
    if variants:
        prov["diode_variant_parameters"] = {
            ref: {
                "kind": vp.kind,
                "Is_A": str(vp.Is),
                "n": str(vp.n),
                "Vt_V": str(vp.Vt),
                "Vz_V": str(vp.Vz) if vp.Vz is not None else None,
                "nz": str(vp.nz) if vp.nz is not None else None,
                "Iz_A": str(vp.Iz) if vp.Iz is not None else None,
                "Iph_A": str(vp.Iph) if vp.Iph is not None else None,
            }
            for ref, vp in sorted(variants.items())
        }
    if mosfets:
        prov["mosfet_parameters"] = {
            ref: {
                "polarity": mp.polarity,
                "Kp_A_per_V2": str(mp.Kp),
                "Vto_V": str(mp.Vto),
                "Lambda_per_V": str(mp.Lambda),
                "Phi_V": str(mp.Phi),
                "Gamma_sqrtV": str(mp.Gamma),
            }
            for ref, mp in sorted(mosfets.items())
        }
    if jfets:
        prov["jfet_parameters"] = {
            ref: {
                "polarity": jp.polarity,
                "Idss_A": str(jp.Idss),
                "Vp_V": str(jp.Vp),
                "Lambda_per_V": str(jp.Lambda),
            }
            for ref, jp in sorted(jfets.items())
        }
    return prov


def _converged_result(problem: MNAProblem, system: _NewtonSystem,
                       diodes: dict[str, DiodeParams],
                       bjts: dict[str, BJTParams] | None,
                       mosfets: dict[str, MOSParams] | None,
                       jfets: dict[str, JFETParams] | None,
                       variants: dict[str, DiodeVariantParams] | None,
                       x: tuple[Decimal, ...], f: tuple[Decimal, ...],
                       iters: int, max_iter: int, backtracks: int,
                       warnings: list[str], diagnostics: list[str],
                       initial: tuple[Decimal, Decimal]) -> NonlinearResult:
    ctx = system.ctx
    kfin, afin = system.block_norms(f)
    node_voltages = tuple(
        NodeVoltage(node=n, voltage=Quantity(x[problem.node_index[n]],
                                             _VOLT))
        for n in problem.nodes
    ) + (NodeVoltage(node=problem.ground,
                     voltage=Quantity(Decimal(0), _VOLT)),)

    def node_v(net: str) -> Decimal:
        idx = problem.node_index.get(net)
        return Decimal(0) if idx is None else x[idx]

    by_ref = {c.ref.upper(): c for c in problem.circuit.components}
    ctrl_memo: dict[str, Decimal] = {}

    def nctrl(ref_upper: str, active: tuple[str, ...] = ()) -> Decimal:
        if ref_upper in ctrl_memo:
            return ctrl_memo[ref_upper]
        if ref_upper in active:
            raise CircularControlError(
                f"circular current control involving {ref_upper}")
        c = by_ref[ref_upper]
        t = c.type.upper()
        if t in ("V", "E", "H"):
            value = x[problem.vsource_index[c.ref]]
        elif t == "O":
            value = ctx.minus(x[problem.vsource_index[c.ref]])
        elif t == "R":
            value = ctx.divide(
                ctx.subtract(node_v(c.pins["1"]), node_v(c.pins["2"])),
                c.value.to_base())
        elif t == "I":
            value = ctx.minus(c.value.to_base())
        elif t == "G":
            gm = c.value.to_base()
            value = ctx.minus(ctx.multiply(
                gm, ctx.subtract(node_v(c.parameters["cp"]),
                                 node_v(c.parameters["cn"]))))
        elif t == "F":
            beta = c.value.to_base()
            value = ctx.minus(ctx.multiply(
                beta, nctrl(str(c.parameters["control_ref"]).upper(),
                            active + (ref_upper,))))
        else:
            raise UnsupportedElementError(
                f"{c.ref}: type {t!r} cannot carry control current")
        ctrl_memo[ref_upper] = value
        return value

    branch_currents: list[BranchCurrent] = []
    element_powers: list[ElementPower] = []
    exact_i: dict[str, Decimal] = {}
    for c in sorted(problem.circuit.components, key=lambda c: c.ref.upper()):
        t = c.type.upper()
        if t == "D":
            vd = ctx.subtract(node_v(c.pins["A"]), node_v(c.pins["K"]))
            if variants and c.ref.upper() in variants:
                vp = variants[c.ref.upper()]
                ival = variant_current(vd, vp, ctx)
                convention = (f"A->K: {vp.kind} I(Vd), Vd = V(A) - V(K)")
            else:
                p = diodes[c.ref.upper()]
                ival = shockley_current(vd, p, ctx)
                convention = "A->K: Shockley I(Vd), Vd = V(A) - V(K)"
            v_drop, i_branch = vd, ival
        elif t == "Q":
            bp = (bjts or {})[c.ref.upper()]
            vc = node_v(c.pins["C"])
            vb = node_v(c.pins["B"])
            ve = node_v(c.pins["E"])
            ic, ib, ie = bjt_terminal_currents(vc, vb, ve, bp, ctx)
            exact_i[f"{c.ref}:C"] = ic
            exact_i[f"{c.ref}:B"] = ib
            exact_i[f"{c.ref}:E"] = ie
            branch_currents.append(BranchCurrent(
                ref=f"{c.ref}:C",
                current=Quantity(ic, _AMP),
                convention="into collector (terminal current)",
            ))
            branch_currents.append(BranchCurrent(
                ref=f"{c.ref}:B",
                current=Quantity(ib, _AMP),
                convention="into base (terminal current)",
            ))
            branch_currents.append(BranchCurrent(
                ref=f"{c.ref}:E",
                current=Quantity(ie, _AMP),
                convention="into emitter (terminal current)",
            ))
            vce = ctx.subtract(vc, ve)
            vbe = ctx.subtract(vb, ve)
            pw = ctx.add(ctx.multiply(vce, ic), ctx.multiply(vbe, ib))
            element_powers.append(ElementPower(
                ref=c.ref, power=Quantity(pw, _WATT), absorbed=pw >= 0))
            continue
        elif t == "M":
            mp = (mosfets or {})[c.ref.upper()]
            vd = node_v(c.pins["D"])
            vg = node_v(c.pins["G"])
            vs = node_v(c.pins["S"])
            vb = node_v(c.pins["B"])
            idc, ig, isc, ib = mos_terminal_currents(
                vd, vg, vs, vb, mp, ctx)
            exact_i[f"{c.ref}:D"] = idc
            exact_i[f"{c.ref}:G"] = ig
            exact_i[f"{c.ref}:S"] = isc
            exact_i[f"{c.ref}:B"] = ib
            for leg, cur in (("D", idc), ("G", ig), ("S", isc), ("B", ib)):
                branch_currents.append(BranchCurrent(
                    ref=f"{c.ref}:{leg}",
                    current=Quantity(cur, _AMP),
                    convention=f"into {leg} (terminal current)",
                ))
            vds = ctx.subtract(vd, vs)
            vgs = ctx.subtract(vg, vs)
            vbs = ctx.subtract(vb, vs)
            pw = ctx.add(ctx.add(ctx.multiply(vds, idc),
                                 ctx.multiply(vgs, ig)),
                         ctx.multiply(vbs, ib))
            element_powers.append(ElementPower(
                ref=c.ref, power=Quantity(pw, _WATT), absorbed=pw >= 0))
            continue
        elif t == "J":
            jp = (jfets or {})[c.ref.upper()]
            vd = node_v(c.pins["D"])
            vg = node_v(c.pins["G"])
            vs = node_v(c.pins["S"])
            idc, ig, isc = jfet_terminal_currents(vd, vg, vs, jp, ctx)
            exact_i[f"{c.ref}:D"] = idc
            exact_i[f"{c.ref}:G"] = ig
            exact_i[f"{c.ref}:S"] = isc
            for leg, cur in (("D", idc), ("G", ig), ("S", isc)):
                branch_currents.append(BranchCurrent(
                    ref=f"{c.ref}:{leg}",
                    current=Quantity(cur, _AMP),
                    convention=f"into {leg} (terminal current)",
                ))
            vds = ctx.subtract(vd, vs)
            vgs = ctx.subtract(vg, vs)
            pw = ctx.add(ctx.multiply(vds, idc), ctx.multiply(vgs, ig))
            element_powers.append(ElementPower(
                ref=c.ref, power=Quantity(pw, _WATT), absorbed=pw >= 0))
            continue
        elif t == "R":
            v_drop = ctx.subtract(node_v(c.pins["1"]), node_v(c.pins["2"]))
            i_branch = ctx.divide(v_drop, c.value.to_base())
            convention = "pin1->pin2: I = (V1 - V2) / R"
        elif t in ("V", "E", "H"):
            v_drop = ctx.subtract(node_v(c.pins["+"]), node_v(c.pins["-"]))
            i_branch = x[problem.vsource_index[c.ref]]
            convention = "+->-: MNA unknown current through the source"
        elif t in ("G", "F"):
            v_drop = ctx.subtract(node_v(c.pins["+"]), node_v(c.pins["-"]))
            i_branch = nctrl(c.ref.upper())
            convention = ("+->-: dependent output current (delivered into "
                          "'+', so I = -J)")
        elif t == "O":
            v_drop = node_v(c.pins["o"])
            i_branch = ctx.minus(x[problem.vsource_index[c.ref]])
            convention = "o->gnd (op-amp output leg; reported = -i_o)"
        elif t == "T":
            v1 = ctx.subtract(node_v(c.pins["1"]), node_v(c.pins["2"]))
            v2 = ctx.subtract(node_v(c.pins["3"]), node_v(c.pins["4"]))
            i1 = x[problem.vsource_index[f"{c.ref}:1"]]
            i2 = x[problem.vsource_index[f"{c.ref}:2"]]
            for leg, vv, ii in (("1", v1, i1), ("2", v2, i2)):
                pw = ctx.multiply(vv, ii)
                exact_i[f"{c.ref}:{leg}"] = ii
                branch_currents.append(BranchCurrent(
                    ref=f"{c.ref}:{leg}",
                    current=Quantity(ii, _AMP),
                    convention=f"winding {leg} "
                                f"(1->2 primary, 3->4 secondary): aux current"))
                element_powers.append(ElementPower(
                    ref=f"{c.ref}:{leg}", power=Quantity(pw, _WATT),
                    absorbed=pw >= 0))
            continue
        else:  # I
            v_drop = ctx.subtract(node_v(c.pins["+"]), node_v(c.pins["-"]))
            i_branch = ctx.minus(c.value.to_base())
            convention = "+->-: independent source (reported = -Is)"
        pw = ctx.multiply(v_drop, i_branch)
        exact_i[c.ref] = i_branch
        branch_currents.append(BranchCurrent(
            ref=c.ref, current=Quantity(i_branch, _AMP),
            convention=convention))
        element_powers.append(ElementPower(
            ref=c.ref, power=Quantity(pw, _WATT), absorbed=pw >= 0))

    # Sorted (E0.4): nets is a set; with hash order, max() below picked the
    # first of numerically equal zeros (e.g. 0E-51 vs 0E-52) by PYTHONHASHSEED.
    # Values are unchanged; only the reported representative is deterministic.
    net_kcl: dict[str, Decimal] = {net: Decimal(0)
                                   for net in sorted(problem.circuit.nets)}
    for c in problem.circuit.components:
        t = c.type.upper()
        if t == "T":
            i1 = exact_i[f"{c.ref}:1"]
            i2 = exact_i[f"{c.ref}:2"]
            net_kcl[c.pins["1"]] = ctx.add(net_kcl[c.pins["1"]], i1)
            net_kcl[c.pins["2"]] = ctx.subtract(net_kcl[c.pins["2"]], i1)
            net_kcl[c.pins["3"]] = ctx.add(net_kcl[c.pins["3"]], i2)
            net_kcl[c.pins["4"]] = ctx.subtract(net_kcl[c.pins["4"]], i2)
        elif t == "Q":
            ic = exact_i[f"{c.ref}:C"]
            ib = exact_i[f"{c.ref}:B"]
            ie = exact_i[f"{c.ref}:E"]
            net_kcl[c.pins["C"]] = ctx.add(net_kcl[c.pins["C"]], ic)
            net_kcl[c.pins["B"]] = ctx.add(net_kcl[c.pins["B"]], ib)
            net_kcl[c.pins["E"]] = ctx.add(net_kcl[c.pins["E"]], ie)
        elif t == "M":
            for leg in ("D", "G", "S", "B"):
                cur = exact_i[f"{c.ref}:{leg}"]
                net_kcl[c.pins[leg]] = ctx.add(net_kcl[c.pins[leg]], cur)
        elif t == "J":
            for leg in ("D", "G", "S"):
                cur = exact_i[f"{c.ref}:{leg}"]
                net_kcl[c.pins[leg]] = ctx.add(net_kcl[c.pins[leg]], cur)
        elif t == "D":
            ib = exact_i[c.ref]
            net_kcl[c.pins["A"]] = ctx.add(net_kcl[c.pins["A"]], ib)
            net_kcl[c.pins["K"]] = ctx.subtract(net_kcl[c.pins["K"]], ib)
        elif t == "O":
            ib = exact_i[c.ref]
            net_kcl[c.pins["o"]] = ctx.add(net_kcl[c.pins["o"]], ib)
            net_kcl[problem.ground] = ctx.subtract(
                net_kcl[problem.ground], ib)
        elif t == "R":
            ib = exact_i[c.ref]
            net_kcl[c.pins["1"]] = ctx.add(net_kcl[c.pins["1"]], ib)
            net_kcl[c.pins["2"]] = ctx.subtract(net_kcl[c.pins["2"]], ib)
        else:
            ib = exact_i[c.ref]
            net_kcl[c.pins["+"]] = ctx.add(net_kcl[c.pins["+"]], ib)
            net_kcl[c.pins["-"]] = ctx.subtract(net_kcl[c.pins["-"]], ib)
    kcl_peak = max([abs(v) for v in net_kcl.values()] or [Decimal(0)])
    kvl_peak = Decimal(0)
    for _a, _b, loop in fundamental_cycle_chords(problem.circuit,
                                                 problem.ground):
        run = Decimal(0)
        for u, v in zip(loop, loop[1:] + loop[:1]):
            run = ctx.add(run, ctx.subtract(node_v(u), node_v(v)))
        if abs(run) > abs(kvl_peak):
            kvl_peak = abs(run)
    total = Decimal(0)
    ppeak = Decimal(0)
    for c in problem.circuit.components:
        t = c.type.upper()
        refs = [f"{c.ref}:{leg}" for leg in ("1", "2")] if t == "T" \
            else [c.ref]
        for r in refs:
            pw = next(e.power.to_base() for e in element_powers
                      if e.ref == r)
            total = ctx.add(total, pw)
            if abs(pw) > abs(ppeak):
                ppeak = abs(pw)
    scale_i = max([abs(v) for v in exact_i.values()] or [Decimal(0)])
    bound = ATOL + RTOL * max(Decimal(1), scale_i, abs(ppeak))
    passed = kcl_peak <= bound and kvl_peak <= bound and \
        abs(total) <= bound
    checks = ConservationChecks(
        kcl_max_residual=str(kcl_peak),
        kvl_max_residual=str(kvl_peak),
        power_balance_residual=str(total),
        tolerance=f"ATOL + RTOL*max(1, |I|, |P|) = {bound} "
                  f"(ATOL={ATOL} RTOL={RTOL})",
        passed=passed,
    )
    if not passed:
        warnings.append(f"conservation outside tolerance: kcl={kcl_peak} "
                        f"kvl={kvl_peak} power={total} bound={bound}")
    return NonlinearResult(
        status=NonlinearStatus.CONVERGED,
        node_voltages=node_voltages,
        branch_currents=tuple(branch_currents),
        element_powers=tuple(element_powers),
        system_summary=_summary(problem, diodes, bjts, mosfets, jfets,
                                  variants, iters),
        conservation_checks=checks,
        provenance=_provenance(problem, diodes, bjts, mosfets, jfets,
                               variants, max_iter, iters,
                               NonlinearStatus.CONVERGED, f, backtracks,
                               warnings),
        diagnostics=tuple(diagnostics + [
            f"converged in {iters} iteration(s): residual "
            f"kcl={kfin} aux={afin}",
            f"initial residual kcl={initial[0]} aux={initial[1]}",
            f"conservation passed={passed}",
        ]),
    )

