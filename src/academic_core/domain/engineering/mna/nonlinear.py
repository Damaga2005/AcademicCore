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
    companion,
    extract_diode_params,
    shockley_current,
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
                         bjts: dict[str, BJTParams] | None = None) -> dict:
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
        entries.append(entry)
    formulation = "MNA residual F(x) = A0 x - b0 + D(x) + Q(x); J = A0 + diode/bjt stamps; damped Newton"
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
                 bjts: dict[str, BJTParams] | None = None) -> None:
        self.problem = problem
        self.ctx = make_context()
        self.n = problem.size
        self.n_nodes = len(problem.nodes)
        self.diode_list = sorted(
            (c for c in problem.circuit.components
             if c.type.upper() == "D"),
            key=lambda c: c.ref.upper(),
        )
        self.models = {c.ref.upper(): diodes[c.ref.upper()]
                       for c in self.diode_list}
        self.a_index = {c.ref.upper(): problem.node_index.get(c.pins["A"])
                        for c in self.diode_list}
        self.k_index = {c.ref.upper(): problem.node_index.get(c.pins["K"])
                        for c in self.diode_list}

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

        self.a0 = tuple(
            tuple(_decimal_of(v) for v in row) for row in problem.matrix)
        self.b0 = tuple(_decimal_of(v) for v in problem.rhs)

    def _x_of(self, x: tuple[Decimal, ...], idx: int | None) -> Decimal:
        return Decimal(0) if idx is None else x[idx]

    def residual(self, x: tuple[Decimal, ...]
                 ) -> tuple[Decimal, ...] | None:
        """``F(x)``; ``None`` if any diode or BJT evaluation is non-finite."""
        ctx = self.ctx
        try:
            acc = []
            for i in range(self.n):
                total = Decimal(0)
                row = self.a0[i]
                for j in range(self.n):
                    total = ctx.add(total, ctx.multiply(row[j], x[j]))
                acc.append(ctx.subtract(total, self.b0[i]))
            for ref in self.models:
                p = self.models[ref]
                vd = ctx.subtract(self._x_of(x, self.a_index[ref]),
                                  self._x_of(x, self.k_index[ref]))
                ival, _, _ = companion(vd, p, ctx)
                if not ival.is_finite():
                    return None
                ia, ik = self.a_index[ref], self.k_index[ref]
                if ia is not None:
                    acc[ia] = ctx.add(acc[ia], ival)
                if ik is not None:
                    acc[ik] = ctx.subtract(acc[ik], ival)
            for ref in self.bjt_models:
                bp = self.bjt_models[ref]
                vc = self._x_of(x, self.c_index[ref])
                vb = self._x_of(x, self.b_index[ref])
                ve = self._x_of(x, self.e_index[ref])
                ic, ib, ie = bjt_terminal_currents(vc, vb, ve, bp, ctx)
                if not (ic.is_finite() and ib.is_finite() and ie.is_finite()):
                    return None
                ic_idx = self.c_index[ref]
                ib_idx = self.b_index[ref]
                ie_idx = self.e_index[ref]
                if ic_idx is not None:
                    acc[ic_idx] = ctx.add(acc[ic_idx], ic)
                if ib_idx is not None:
                    acc[ib_idx] = ctx.add(acc[ib_idx], ib)
                if ie_idx is not None:
                    acc[ie_idx] = ctx.add(acc[ie_idx], ie)
            if not all(v.is_finite() for v in acc):
                return None
            return tuple(acc)
        except (Overflow, InvalidOperation):
            return None

    def jacobian(self, x: tuple[Decimal, ...]
                 ) -> list[list[Decimal]] | None:
        """``J(x)``; ``None`` if any diode or BJT evaluation is non-finite."""
        ctx = self.ctx
        try:
            rows = [list(r) for r in self.a0]
            for ref in self.models:
                p = self.models[ref]
                vd = ctx.subtract(self._x_of(x, self.a_index[ref]),
                                  self._x_of(x, self.k_index[ref]))
                _, gval, _ = companion(vd, p, ctx)
                if not gval.is_finite():
                    return None
                ia, ik = self.a_index[ref], self.k_index[ref]
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
                bjt_j = bjt_jacobian(vc, vb, ve, bp, ctx)
                if bjt_j is None:
                    return None
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


def solve_nonlinear_dc(circuit: Circuit, *,
                       max_iter: int = MAX_ITER) -> NonlinearResult:
    """DC operating point with Shockley diodes (F8-H) via damped Newton.

    ``max_iter`` override exists for honest ``MAX_ITERATIONS``
    testing; provenance always records the effective value.
    """
    if not isinstance(max_iter, int) or isinstance(max_iter, bool) \
            or max_iter < 0:
        return NonlinearResult(
            status=NonlinearStatus.INVALID,
            diagnostics=("max_iter must be a non-negative int",),
        )
    try:
        problem = build_mna_problem(circuit, allow_diodes=True, allow_bjts=True)
    except UnsupportedElementError as exc:
        return NonlinearResult(status=NonlinearStatus.UNSUPPORTED,
                                diagnostics=(str(exc),))
    except _INVALID_ERRORS as exc:
        return NonlinearResult(status=NonlinearStatus.INVALID,
                                diagnostics=(str(exc),))
    try:
        diodes = {c.ref.upper(): extract_diode_params(c)
                  for c in circuit.components if c.type.upper() == "D"}
        bjts = {c.ref.upper(): extract_bjt_params(c)
                for c in circuit.components if c.type.upper() == "Q"}
    except InvalidCircuitError as exc:
        return NonlinearResult(status=NonlinearStatus.INVALID,
                                diagnostics=(str(exc),))

    system = _NewtonSystem(problem, diodes, bjts)
    ctx = system.ctx
    n = system.n
    x: tuple[Decimal, ...] = tuple(Decimal(0) for _ in range(n))
    diagnostics: list[str] = [
        f"engine={ENGINE_VERSION}",
        f"n_unknowns={n}",
        f"n_diodes={len(diodes)}",
        f"n_bjts={len(bjts)}",
        "initial_guess=zero-vector (deterministic)",
        f"tolerances: rtol={RTOL} atol={ATOL} stol={STOL}",
        f"max_iter={max_iter} max_backtracking={MAX_BACKTRACK}",
    ]
    warnings: list[str] = []
    backtrack_uses = 0

    f0 = system.residual(x)
    if f0 is None:
        return NonlinearResult(
            status=NonlinearStatus.DIVERGED,
            system_summary=_summary(problem, diodes, bjts, 0),
            provenance=_provenance(problem, diodes, bjts, max_iter, 0,
                                   NonlinearStatus.DIVERGED, f0,
                                   backtrack_uses, warnings),
            diagnostics=tuple(diagnostics + [
                "initial residual non-finite: cannot start Newton",
            ]),
        )
    k0, a0n = system.block_norms(f0)
    scale = system.scale_of(x)
    if _block_ok(list(f0[:system.n_nodes]), scale) and \
            _block_ok(list(f0[system.n_nodes:]), scale):
        return _converged_result(
            problem, system, diodes, bjts, x, f0, 0, max_iter, backtrack_uses,
            warnings, diagnostics, initial=(k0, a0n))

    it = 0
    final_f = f0
    final_pair = (k0, a0n)
    while it < max_iter:
        jac = system.jacobian(x)
        if jac is None:
            return NonlinearResult(
                status=NonlinearStatus.DIVERGED,
                system_summary=_summary(problem, diodes, bjts, it),
                provenance=_provenance(problem, diodes, bjts, max_iter, it,
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
            return NonlinearResult(
                status=NonlinearStatus.DIVERGED,
                system_summary=_summary(problem, diodes, bjts, it),
                provenance=_provenance(problem, diodes, bjts, max_iter, it,
                                       NonlinearStatus.DIVERGED, final_f,
                                       backtrack_uses, warnings),
                diagnostics=tuple(diagnostics + [
                    f"iter {it}: linear-solve entry refused: {exc}",
                ]),
            )
        if lin.status in (LinearStatus.SINGULAR, LinearStatus.INCONSISTENT):
            return NonlinearResult(
                status=NonlinearStatus.SINGULAR_JACOBIAN,
                system_summary=_summary(problem, diodes, bjts, it),
                provenance=_provenance(problem, diodes, bjts, max_iter, it,
                                       NonlinearStatus.SINGULAR_JACOBIAN,
                                       final_f, backtrack_uses, warnings),
                diagnostics=tuple(diagnostics + [
                    f"iter {it}: Jacobian {lin.status.value} "
                    f"(rank {lin.rank_A}/{n}): Newton step undefined",
                ]),
            )
        if lin.status != LinearStatus.SOLVED or lin.solution is None:
            return NonlinearResult(
                status=NonlinearStatus.DIVERGED,
                system_summary=_summary(problem, diodes, bjts, it),
                provenance=_provenance(problem, diodes, bjts, max_iter, it,
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
        accepted: tuple[Decimal, ...] | None = None
        accepted_f: tuple[Decimal, ...] | None = None
        for _ in range(MAX_BACKTRACK + 1):
            trial = tuple(
                ctx.add(xv, ctx.multiply(alpha, dv))
                for xv, dv in zip(x, dx))
            ft = system.residual(trial)
            if ft is not None:
                kt, at = system.block_norms(ft)
                if max(kt, at) < cur:
                    accepted, accepted_f = trial, ft
                    break
            alpha = ctx.divide(alpha, Decimal(2))
        if accepted is None or accepted_f is None:
            return NonlinearResult(
                status=NonlinearStatus.DIVERGED,
                system_summary=_summary(problem, diodes, bjts, it),
                provenance=_provenance(problem, diodes, bjts, max_iter, it,
                                       NonlinearStatus.DIVERGED, final_f,
                                       backtrack_uses, warnings),
                diagnostics=tuple(diagnostics + [
                    f"iter {it}: backtracking exhausted "
                    f"({MAX_BACKTRACK + 1} halvings, no residual decrease): "
                    f"stagnation",
                ]),
            )
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
        if res_ok and step_ok:
            return _converged_result(
                problem, system, diodes, bjts, x, final_f, it, max_iter,
                backtrack_uses, warnings, diagnostics,
                initial=(k0, a0n))
    return NonlinearResult(
        status=NonlinearStatus.MAX_ITERATIONS,
        system_summary=_summary(problem, diodes, bjts, it),
        provenance=_provenance(problem, diodes, bjts, max_iter, it,
                               NonlinearStatus.MAX_ITERATIONS, final_f,
                               backtrack_uses, warnings),
        diagnostics=tuple(diagnostics + [
            f"iteration budget exhausted ({max_iter}): residual "
            f"kcl={final_pair[0]} aux={final_pair[1]}",
        ]),
    )


def _summary(problem: MNAProblem, diodes: dict[str, DiodeParams],
             bjts: dict[str, BJTParams] | None, iters: int) -> dict:
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
                 if c.type.upper() == "D"),
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
    return summary


def _provenance(problem: MNAProblem, diodes: dict[str, DiodeParams],
                bjts: dict[str, BJTParams] | None,
                max_iter: int, iters: int, status: NonlinearStatus,
                final_f: tuple[Decimal, ...] | None, backtracks: int,
                warnings: list[str]) -> dict:
    struct = _canonical_structure(problem.circuit, diodes, bjts)
    kf, af = (None, None)
    if final_f is not None:
        n_nodes = len(problem.nodes)
        kf = str(max([abs(v) for v in final_f[:n_nodes]]
                     or [Decimal(0)]))
        af = str(max([abs(v) for v in final_f[n_nodes:]]
                     or [Decimal(0)]))
    model_name = "Shockley+Ebers-Moll" if (diodes and bjts) else ("Ebers-Moll" if bjts else "Shockley")
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
    return prov


def _converged_result(problem: MNAProblem, system: _NewtonSystem,
                      diodes: dict[str, DiodeParams],
                      bjts: dict[str, BJTParams] | None,
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
            p = diodes[c.ref.upper()]
            vd = ctx.subtract(node_v(c.pins["A"]), node_v(c.pins["K"]))
            ival = shockley_current(vd, p, ctx)
            v_drop, i_branch = vd, ival
            convention = "A->K: Shockley I(Vd), Vd = V(A) - V(K)"
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

    net_kcl: dict[str, Decimal] = {net: Decimal(0)
                                   for net in problem.circuit.nets}
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
        system_summary=_summary(problem, diodes, bjts, iters),
        conservation_checks=checks,
        provenance=_provenance(problem, diodes, bjts, max_iter, iters,
                               NonlinearStatus.CONVERGED, f, backtracks,
                               warnings),
        diagnostics=tuple(diagnostics + [
            f"converged in {iters} iteration(s): residual "
            f"kcl={kfin} aux={afin}",
            f"initial residual kcl={initial[0]} aux={initial[1]}",
            f"conservation passed={passed}",
        ]),
    )

