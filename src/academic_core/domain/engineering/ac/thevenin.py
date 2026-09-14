"""General AC Thevenin & Norton one-port equivalents (F8-D7).

Thin orchestration over certified infrastructure — no new solver, no new
MNA, no new circuit model, no new complex type:

* ``Vth``: open-circuit port voltage ``VA - VB`` from the live D3
  solution. "Open" means no external load; a branch already spanning
  A-B is internal circuitry and stays exactly where it is.
* ``Zth``: D5 test-source impedance on the deactivated network
  (V -> 0 V short, I -> removed). Always the test method — the direct
  operating ratio would answer a different question.
* ``In``: short-circuit current entering A, measured directly with a
  0 V source across the port in a FRESH derived circuit (never
  ``Vth/Zth``, which fails exactly where Norton gets interesting).
* ``Yn``: D5 test-source admittance (V-test) on the deactivated
  network — an independent measurement, never ``1/Zth``.

Conventions (D3/D5, unchanged): port current entering A; MNA unknowns
flow + -> -, so entering-A currents negate the unknown. With ``In``
entering A, the Thevenin-Norton invariant reads ``Vth + In*Zth = 0``
(the textbook ``Vth = Isc*Zth`` uses the A->B short current, i.e. the
negation); it is reported, never enforced. Statuses are
the parent ACStatus throughout; sub-measurement failures degrade single
fields to labeled UNDEFINED/None with diagnostics — solver verdicts are
preserved, never replaced. In particular an ideal voltage-source port
yields a valid ``(Vs, 0)`` Thevenin pair with UNDEFINED Norton (the
short is contradictory), which is the physically correct answer.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

from academic_core.domain.engineering.ac.impedance import (
    METHOD_TEST,
    ImpedanceCategory,
    ImpedanceError,
    ImpedanceValue,
    PortDefinition,
    deactivate_sources,
    measure_port,
)
from academic_core.domain.engineering.ac.solution import ACStatus
from academic_core.domain.engineering.math.decimal_complex import DecimalComplex
from academic_core.domain.engineering.math.linsolve.problem import NumericMode
from academic_core.domain.engineering.math.rational import RationalComplex
from academic_core.domain.engineering.math.trig import make_context
from academic_core.domain.engineering.units import Quantity, parse_unit

ENGINE_VERSION = "f8d-ac-thevenin-norton/1.0"

DEACTIVATION_SPEC = (
    "independent V -> 0 V short (MNA structure kept); "
    "independent I -> branch removed (open)"
)


def _free_ref(used: set[str], letter: str) -> str:
    # Local first-free allocator (D5 keeps its own private copy; depending
    # on another module's private helper would couple certified code).
    k = 1
    while f"{letter}{k}" in used:
        k += 1
    return f"{letter}{k}"


@dataclass(frozen=True)
class LoadCheck:
    """Resistive-load verification of one equivalent (F8-C parity)."""

    ref: str  # attached load branch ref in the derived circuit
    load: str  # load value as given, e.g. "1 kOhm"
    v_predicted: object | None  # Vth*ZL/(Zth+ZL) or None with reason
    v_measured: object | None  # port voltage of the loaded full solve
    i_predicted: object | None
    i_measured: object | None
    passed: bool
    diagnostic: str

    def to_dict(self) -> dict:
        def _ph(e):
            return None if e is None else e.to_dict() if hasattr(e, "to_dict") \
                else {"re": str(e.re), "im": str(e.im)}

        return {
            "ref": self.ref,
            "load": self.load,
            "v_predicted": _ph(self.v_predicted),
            "v_measured": _ph(self.v_measured),
            "i_predicted": _ph(self.i_predicted),
            "i_measured": _ph(self.i_measured),
            "passed": self.passed,
            "diagnostic": self.diagnostic,
        }


@dataclass(frozen=True)
class ACOnePortEquivalent:
    """AC Thevenin + Norton equivalent of one two-terminal port."""

    status: ACStatus
    port: PortDefinition
    vth: RationalComplex | DecimalComplex | None
    zth: ImpedanceValue | None
    inorton: RationalComplex | DecimalComplex | None
    yn: ImpedanceValue | None
    numeric_mode: object | None  # NumericMode
    working_precision: int | None
    operating_point: object | None  # ACOperatingPoint
    provenance: dict
    diagnostics: tuple[str, ...]
    digest: str

    def to_dict(self) -> dict:
        from academic_core.domain.engineering.ac.phasors import fmt_cartesian

        def _ph(e):
            return None if e is None else fmt_cartesian(e)

        return {
            "status": self.status.value,
            "port": self.port.to_dict(),
            "vth": _ph(self.vth),
            "zth": None if self.zth is None else self.zth.to_dict(),
            "inorton": _ph(self.inorton),
            "yn": None if self.yn is None else self.yn.to_dict(),
            "numeric_mode": None if self.numeric_mode is None
            else self.numeric_mode.value,
            "working_precision": self.working_precision,
            "operating_point": None if self.operating_point is None
            else self.operating_point.to_dict(),
            "provenance": dict(self.provenance),
            "diagnostics": list(self.diagnostics),
            "digest": self.digest,
        }


def _undefined_equivalent(status: ACStatus, port: PortDefinition,
                          diagnostics: tuple[str, ...],
                          operating_point=None, numeric_mode=None,
                          working_precision=None) -> ACOnePortEquivalent:
    digest = hashlib.sha256(json.dumps({
        "engine": ENGINE_VERSION,
        "status": status.value,
        "port": port.to_dict(),
        "diagnostics": list(diagnostics),
    }, sort_keys=True, default=str).encode()).hexdigest()
    return ACOnePortEquivalent(
        status=status, port=port, vth=None, zth=None, inorton=None,
        yn=None, numeric_mode=numeric_mode,
        working_precision=working_precision,
        operating_point=operating_point,
        provenance={"engine": ENGINE_VERSION, "version": "1.0",
                    "status": status.value},
        diagnostics=diagnostics, digest=digest,
    )


def _check_terminals(circuit, port: PortDefinition) -> None:
    nets = set(circuit.nets)
    for terminal in (port.node_a, port.node_b):
        if terminal not in nets:
            raise ImpedanceError(
                f"port terminal {terminal!r} is not a net of circuit "
                f"{circuit.name!r}"
            )


def analyze_ac_thevenin_problem(problem, solution,
                                port: PortDefinition) -> ACOnePortEquivalent:
    """Core analysis over a pre-built problem + SOLVED solution.

    Raises :class:`ImpedanceError` on misuse (non-SOLVED solution,
    unknown port terminals); the convenience API maps those to in-band
    statuses instead.
    """
    from academic_core.domain.engineering.ac.solver import solve_ac

    if solution.status != ACStatus.SOLVED:
        raise ImpedanceError(
            f"thevenin analysis requires a SOLVED AC solution, got "
            f"{solution.status}"
        )
    _check_terminals(problem.circuit, port)
    op = problem.operating_point
    va = solution.voltage_of(port.node_a)
    vb = solution.voltage_of(port.node_b)
    assert va is not None and vb is not None
    vth = va - vb

    zth = measure_port(problem, solution, port, "impedance", METHOD_TEST)
    yn = measure_port(problem, solution, port, "admittance", METHOD_TEST)

    # Norton short-circuit current: fresh derived circuit = original
    # components + one 0 V source across A-B (+ at A). Entering-A current
    # negates the MNA unknown (which flows + -> -, leaving A).
    from academic_core.domain.engineering.circuit import Circuit, Component

    used = {c.ref.upper() for c in problem.circuit.components}
    sref = _free_ref(used, "V")
    shorted = [c for c in problem.circuit.components]
    shorted.append(Component(
        sref, "V", Quantity(Decimal(0), parse_unit("V")),
        {"+": port.node_a, "-": port.node_b}, {},
    ))
    fresh = Circuit(f"{problem.circuit.name}+sc-{sref}")
    for c in shorted:
        fresh.add(c)
    sc = solve_ac(fresh, op.frequency, NumericMode.AUTO)
    inorton = None
    sc_diagnostic = f"short-circuit solve: {sc.status.value} (ref {sref})"
    if sc.status == ACStatus.SOLVED:
        i_unknown = sc.current_of(sref)
        assert i_unknown is not None
        inorton = -i_unknown

    diagnostics = [
        f"engine={ENGINE_VERSION}",
        f"port=({port.node_a},{port.node_b})",
        f"parent={solution.status.value}",
        f"zth-basis={zth.basis}",
        f"yn-basis={yn.basis}",
        sc_diagnostic,
    ]
    consistency = _consistency_note(vth, zth, inorton)
    if consistency is not None:
        diagnostics.append(consistency)
    lin = solution.solver_result
    provenance = {
        "engine": ENGINE_VERSION,
        "version": "1.0",
        "port": port.to_dict(),
        "frequency": op.frequency.format(),
        "frequency_base_hz": str(op.frequency.to_base()),
        "angular_frequency_rad_per_s": str(op.omega),
        "time_convention": op.time_convention,
        "amplitude_convention": op.amplitude_convention,
        "numeric_mode": solution.numeric_mode.value
        if solution.numeric_mode is not None else "unknown",
        "working_precision": solution.working_precision,
        "vth": _cart(vth),
        "zth_category": zth.category.value,
        "zth": _cart(zth.value),
        "inorton": _cart(inorton),
        "yn_category": yn.category.value,
        "yn": _cart(yn.value),
        "deactivation": DEACTIVATION_SPEC,
        "zth_test": "1A entering A on deactivated network",
        "yn_test": "1V (+ at A) on deactivated network",
        "isc_test": f"0V short {sref} (+ at A) on live network",
        "solver_status": solution.status.value,
        "sc_status": sc.status.value,
        "kcl_max_residual": None if solution.kcl_max_residual is None
        else str(solution.kcl_max_residual),
        "solver_digest": lin.digest if lin is not None else None,
        "backward_error": (None if lin is None else str(lin.backward_error)),
        "component_refs": sorted(c.ref.upper()
                                 for c in problem.circuit.components),
    }
    digest = hashlib.sha256(json.dumps({
        "engine": ENGINE_VERSION,
        "port": port.to_dict(),
        "frequency_base_hz": str(op.frequency.to_base()),
        "mode": provenance["numeric_mode"],
        "vth": _cart(vth),
        "zth": {"category": zth.category.value, "value": _cart(zth.value)},
        "inorton": _cart(inorton),
        "yn": {"category": yn.category.value, "value": _cart(yn.value)},
        "status": solution.status.value,
        "sc_status": sc.status.value,
        "deactivation": DEACTIVATION_SPEC,
    }, sort_keys=True, default=str).encode()).hexdigest()
    return ACOnePortEquivalent(
        status=solution.status, port=port, vth=vth, zth=zth,
        inorton=inorton, yn=yn, numeric_mode=solution.numeric_mode,
        working_precision=solution.working_precision,
        operating_point=op, provenance=provenance,
        diagnostics=tuple(diagnostics), digest=digest,
    )


def _cart(e):
    if e is None:
        return None
    return {"re": str(e.re), "im": str(e.im)}


def _consistency_note(vth, zth, inorton) -> str | None:
    """Report |Vth + In*Zth| when all three are finite (never gated).

    Sign: ``inorton`` follows the port convention (current ENTERING A),
    while the textbook identity ``Vth = Isc*Zth`` uses the A->B short
    current, i.e. the negation. Hence the invariant is
    ``Vth + In*Zth = 0``. Reported for audit, never used to alter data.
    """
    if inorton is None:
        return None
    if zth.category.value != "finite" or zth.value is None:
        return None
    try:
        delta = vth + inorton * zth.value
        return f"consistency |Vth + In*Zth| = {delta.modulus()}"
    except Exception as exc:  # defensive: report, never crash analysis
        return f"consistency check unavailable: {exc}"


def analyze_ac_thevenin(circuit, port: PortDefinition, frequency,
                        mode=NumericMode.AUTO) -> ACOnePortEquivalent:
    """One-port AC equivalent of ``circuit`` at ``port``/``frequency``.

    Validation failures are reported in-band (INVALID / UNSUPPORTED);
    mathematical states inherit the D2/D3 classification. Never raises
    for a merely out-of-domain or ill-posed circuit; misuse (bad port
    object type) still raises :class:`ImpedanceError`.
    """
    from academic_core.domain.engineering.ac.problem import build_ac_problem
    from academic_core.domain.engineering.ac.solver import solve_ac
    from academic_core.domain.engineering.mna.errors import (
        UnsupportedElementError,
    )

    if not isinstance(port, PortDefinition):
        raise ImpedanceError(
            f"port must be a PortDefinition, got {type(port).__name__}"
        )
    if not isinstance(mode, NumericMode):
        raise ImpedanceError(f"mode must be a NumericMode, got {mode!r}")
    sol = solve_ac(circuit, frequency, mode)
    if sol.status != ACStatus.SOLVED:
        status = sol.status
        return _undefined_equivalent(
            status, port,
            (f"parent solve: {status.value}; "
             f"{'; '.join(sol.diagnostics[:2])}",),
            sol.operating_point, sol.numeric_mode, sol.working_precision,
        )
    if sol.operating_point is None:  # unreachable: SOLVED implies present
        raise ImpedanceError("SOLVED solution without operating point")
    try:
        problem = build_ac_problem(circuit, sol.operating_point, mode)
    except UnsupportedElementError as exc:
        return _undefined_equivalent(ACStatus.UNSUPPORTED, port, (str(exc),),
                                     sol.operating_point, sol.numeric_mode,
                                     sol.working_precision)
    except ValueError as exc:
        return _undefined_equivalent(ACStatus.INVALID, port, (str(exc),),
                                     sol.operating_point, sol.numeric_mode,
                                     sol.working_precision)
    try:
        return analyze_ac_thevenin_problem(problem, sol, port)
    except ImpedanceError as exc:  # unknown port terminals
        return _undefined_equivalent(ACStatus.INVALID, port, (str(exc),),
                                     sol.operating_point, sol.numeric_mode,
                                     sol.working_precision)


def _parse_load_r(load) -> Decimal:
    from academic_core.domain.engineering.units import (
        RESISTANCE,
        Quantity,
        parse_quantity,
    )

    q = parse_quantity(load) if isinstance(load, str) else load
    if not isinstance(q, Quantity) or q.dimension != RESISTANCE:
        raise ImpedanceError(f"verify load must be a resistance, got {load!r}")
    if q.to_base() <= 0:
        raise ImpedanceError(f"verify load must be R > 0, got {load!r}")
    return q.to_base()


def verify_with_load(equiv: ACOnePortEquivalent, circuit, frequency,
                     load, tol: Decimal) -> LoadCheck:
    """Resistive-load verification (F8-C parity): attach R across the port.

    Predicts ``Vport = Vth*ZL/(Zth+ZL)`` from the equivalent and measures
    the loaded full solve; passes iff both voltages AND both currents
    agree within ``tol`` (required explicit argument, D4-style).
    """
    from academic_core.domain.engineering.circuit import Circuit, Component
    from academic_core.domain.engineering.units import Quantity, parse_unit

    if equiv.status != ACStatus.SOLVED:
        raise ImpedanceError(
            f"load verification needs a SOLVED equivalent, got {equiv.status}"
        )
    if equiv.vth is None or equiv.zth is None or equiv.zth.value is None \
            or equiv.zth.category.value != "finite":
        raise ImpedanceError("load verification needs finite Vth and Zth")
    if not isinstance(tol, Decimal) or isinstance(tol, bool) or tol < 0:
        raise ImpedanceError("tol must be an explicit non-negative Decimal")
    r_base = _parse_load_r(load)
    used = {c.ref.upper() for c in circuit.components}
    lref = _free_ref(used, "R")
    loaded = [c for c in circuit.components]
    loaded.append(Component(
        lref, "R", Quantity(r_base, parse_unit("ohm")),
        {"1": equiv.port.node_a, "2": equiv.port.node_b}, {},
    ))
    fresh = Circuit(f"{circuit.name}+load-{lref}")
    for c in loaded:
        fresh.add(c)
    from academic_core.domain.engineering.ac.solver import solve_ac as _solve

    full = _solve(fresh, frequency, NumericMode.AUTO)
    if full.status != ACStatus.SOLVED:
        return LoadCheck(lref, str(load), None, None, None, None, False,
                         f"loaded solve: {full.status.value}")
    va = full.voltage_of(equiv.port.node_a)
    vb = full.voltage_of(equiv.port.node_b)
    assert va is not None and vb is not None
    v_meas = va - vb
    i_meas = full.current_of(lref)
    assert i_meas is not None
    rl = _native_of(equiv.vth, r_base)
    v_pred = equiv.vth * rl / (equiv.zth.value + rl)
    i_pred = v_pred / rl
    dv = (v_pred - v_meas).modulus()
    di = (i_pred - i_meas).modulus()
    passed = dv <= tol and di <= tol
    return LoadCheck(
        lref, str(load), v_pred, v_meas, i_pred, i_meas, passed,
        f"|dV|={dv} |dI|={di} tol={tol}",
    )


def _native_of(sample, base: Decimal):
    """A base-unit resistance expressed in the sample's D1 numbers."""
    if isinstance(sample, DecimalComplex):
        ctx = make_context()
        return DecimalComplex(ctx.plus(base), Decimal(0))
    return RationalComplex(Fraction(base), Fraction(0))
