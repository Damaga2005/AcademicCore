"""AC power analysis over F8-D3 solutions (F8-D4).

Consumes :class:`ACSolution` read-only. Never solves circuits, never
models circuits, never duplicates phasors or topology.

Mathematics (peak phasors, ``e^(+jwt)``), uniform absorbed convention,
no source special-casing::

    S = 1/2 * V_branch * conjugate(I_branch),   S = P + jQ

with ``V_branch`` / ``I_branch`` exactly as F8-D3 orients them
(pin1->pin2 for R/L/C, +->- for V/I; V-source voltage is the
independent Vs phasor; current-source branch current is -Is). Negative
active power therefore means delivering; positive reactive power under
``e^(+jwt)`` means inductive behavior, negative means capacitive.

Representation split (D1 architecture):

* ``S``, ``P``, ``Q`` keep the solution's native numbers — exact
  ``RationalComplex``/``Fraction`` in EXACT mode, ``DecimalComplex`` /
  ``Decimal`` in HIGH_PRECISION mode. The 1/2 factor is ``Fraction(1,2)``
  / ``Decimal('0.5')``, never binary floating point.
* ``apparent = |S|``, ``pf = P / |S|`` and RMS magnitudes are ``Decimal``:
  roots and quotients cannot inhabit ``Fraction`` in general, so they
  are explicitly approximate (computed under the D1 working context),
  exactly as D1 documents for ``modulus``.
* ``pf`` is ``None`` (with diagnostic) when ``|S|`` is exactly zero —
  no division is executed, no epsilon converts zero into nonzero, and
  small-but-nonzero systems compute normally without clamping.

Conservation (Tellegen): ``sum over branches`` is accumulated in a
deterministic order (sorted references). In EXACT mode the total must
be exactly ``0 + 0j``. In HIGH_PRECISION mode the check is the derived
two-term bound ``|sum S| <= max|V| * N_nets * kcl_max + M * 64 * ulp *
max|S|``: the first term is the Tellegen identity defect from
``sum_b Vb conj(Ib) = sum_n Vn conj(KCL_n)``; the second is a fixed,
generous working-precision rounding account for the power products and
their accumulation (documented integer margin, never fitted to data).
``P`` and ``Q`` are covered by the same bound. Conservation is
necessary but NOT sufficient (a global sign flip preserves it);
element laws, closed forms and the external AC oracle provide
sufficiency (tested, not just asserted).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

from academic_core.domain.engineering.ac.solution import ACStatus
from academic_core.domain.engineering.math.decimal_complex import DecimalComplex
from academic_core.domain.engineering.math.linsolve.problem import NumericMode
from academic_core.domain.engineering.math.rational import RationalComplex
from academic_core.domain.engineering.math.trig import (
    WORKING_PRECISION,
    make_context,
)

ENGINE_VERSION = "f8d-ac-power/1.0"

#: Working-epsilon unit (one ulp at unit scale for the D1 precision).
#: Used only inside the derived HP conservation bound below.
_UNIT_ULP = Decimal(1).scaleb(-WORKING_PRECISION)

#: Rounding-account units per element in the HP bound. Counted basis:
#: each S = 1/2 V conj(I) performs a handful of working-precision
#: roundings (products, sum, final accumulation), each below half an
#: ulp relative; 64 units per element is a deliberately generous fixed
#: integer margin over that count — not fitted to any data. Typical
#: observed usage is below 1% of the resulting account.
_ROUNDING_UNITS_PER_ELEMENT = 64

POWER_CONVENTION = (
    "S = 1/2 * V_branch * conjugate(I_branch) with F8-D3 branch "
    "orientations (pin1->pin2 R/L/C, +->- V/I); S means ABSORBED "
    "(P<0 delivering); peak phasors; e^(+jwt)"
)

REGIME_ZERO = "zero"
REGIME_REACTIVE_ONLY = "reactive-only"
REGIME_ABSORBING = "absorbing"
REGIME_DELIVERING = "delivering"


class PowerAnalysisError(ValueError):
    """Raised when power analysis has no well-defined input.

    Power is computed for SOLVED AC solutions only: other statuses have
    no (or no certified) branch quantities, and analyzing them would be
    numerology rather than analysis.
    """


@dataclass(frozen=True)
class ElementPower:
    ref: str
    power: RationalComplex | DecimalComplex  # S (native numbers)
    active: Fraction | Decimal  # P = Re(S)
    reactive: Fraction | Decimal  # Q = Im(S)
    apparent: Decimal  # |S| (explicitly approximate when irrational)
    pf: Decimal | None  # P/|S|; None with diagnostic when |S| == 0
    regime: str  # zero | reactive-only | absorbing | delivering
    convention: str  # orientation note inherited from the branch

    def to_dict(self) -> dict:
        return {
            "ref": self.ref,
            "S": {"re": str(self.power.re), "im": str(self.power.im)},
            "P": str(self.active),
            "Q": str(self.reactive),
            "apparent": str(self.apparent),
            "pf": None if self.pf is None else str(self.pf),
            "regime": self.regime,
            "convention": self.convention,
        }


@dataclass(frozen=True)
class ConservationReport:
    total_S: RationalComplex | DecimalComplex
    total_P: Fraction | Decimal
    total_Q: Fraction | Decimal
    bound: Decimal | None
    passed: bool
    diagnostics: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "total_S": {"re": str(self.total_S.re), "im": str(self.total_S.im)},
            "total_P": str(self.total_P),
            "total_Q": str(self.total_Q),
            "bound": None if self.bound is None else str(self.bound),
            "passed": self.passed,
            "diagnostics": list(self.diagnostics),
        }


@dataclass(frozen=True)
class ACPowerAnalysis:
    elements: tuple[ElementPower, ...]
    conservation: ConservationReport
    numeric_mode: NumericMode
    working_precision: int | None
    frequency: str
    angular_frequency: str
    provenance: dict
    diagnostics: tuple[str, ...]
    digest: str

    def power_of(self, ref: str) -> ElementPower | None:
        for e in self.elements:
            if e.ref.upper() == ref.upper():
                return e
        return None

    def to_dict(self) -> dict:
        return {
            "elements": [e.to_dict() for e in self.elements],
            "conservation": self.conservation.to_dict(),
            "numeric_mode": self.numeric_mode.value,
            "working_precision": self.working_precision,
            "frequency": self.frequency,
            "angular_frequency": self.angular_frequency,
            "provenance": dict(self.provenance),
            "diagnostics": list(self.diagnostics),
            "digest": self.digest,
        }


def _half_for(voltage, current):
    if isinstance(voltage, DecimalComplex) or isinstance(current, DecimalComplex):
        return DecimalComplex(Decimal("0.5"), Decimal(0))
    return RationalComplex(Fraction(1, 2), Fraction(0))


def _as_decimal(value: Fraction | Decimal) -> Decimal:
    if isinstance(value, Decimal):
        return value
    ctx = make_context()
    return ctx.divide(Decimal(value.numerator), Decimal(value.denominator))


def compute_element_power(
    voltage, current, ref: str = "", convention: str = ""
) -> ElementPower:
    """Complex power absorbed by one branch: ``S = 1/2 V conj(I)``.

    Same formula for every element including sources (absorbed
    convention). ``pf`` is ``None`` when ``|S|`` is exactly zero.
    """
    half = _half_for(voltage, current)
    v = voltage
    if isinstance(v, RationalComplex) and isinstance(current, DecimalComplex):
        # Allowed exact -> approximate promotion (documented boundary);
        # D3 solutions are homogeneous, so this path is defensive only.
        v = v.to_decimal()
    i = current
    if isinstance(i, RationalComplex) and isinstance(v, DecimalComplex):
        i = i.to_decimal()
    s = half * v * i.conjugate()
    p = s.re
    q = s.im
    apparent = s.modulus()
    if not isinstance(apparent, Decimal):
        apparent = _as_decimal(apparent)
    if apparent == 0:
        # |S| exactly zero: PF undefined. No division is executed, no
        # epsilon converts zero into nonzero (the None is surfaced in
        # analyze_power diagnostics explicitly).
        pf = None
    else:
        ctx = make_context()
        pf = ctx.divide(_as_decimal(p), apparent)
    if s.re == 0 and s.im == 0:
        regime = REGIME_ZERO
    elif s.re == 0:
        regime = REGIME_REACTIVE_ONLY
    elif s.re > 0:
        regime = REGIME_ABSORBING
    else:
        regime = REGIME_DELIVERING
    return ElementPower(
        ref=ref, power=s, active=p, reactive=q, apparent=apparent, pf=pf,
        regime=regime, convention=convention,
    )


def _zero_like(sample):
    if isinstance(sample, DecimalComplex):
        return DecimalComplex.zero()
    return RationalComplex.zero()


def verify_conservation(
    elements: tuple[ElementPower, ...],
    *,
    exact: bool,
    kcl_max: Decimal | None,
    max_vmag: Decimal | None,
    n_nets: int,
) -> ConservationReport:
    """Check global power conservation (Tellegen).

    EXACT mode: the total must be exactly ``0 + 0j`` (algebraic identity
    of an exact KCL-satisfying solution). HIGH_PRECISION mode: the
    derived two-term bound (Tellegen identity defect plus a fixed
    working-precision rounding account — see module docstring); ``P``
    and ``Q`` are covered by the same bound. No calibrated epsilon
    anywhere.
    """
    notes: list[str] = []
    if not elements:
        raise PowerAnalysisError("no element powers to conserve")
    total = _zero_like(elements[0].power)
    total_p = elements[0].active - elements[0].active
    total_q = elements[0].reactive - elements[0].reactive
    for e in elements:
        total = total + e.power
        total_p = total_p + e.active
        total_q = total_q + e.reactive
    if exact:
        passed = total.re == 0 and total.im == 0
        notes.append(
            "exact mode: Tellegen identity requires total S == 0+0j exactly"
        )
        return ConservationReport(
            total_S=total, total_P=total_p, total_Q=total_q,
            bound=Decimal(0), passed=passed, diagnostics=tuple(notes),
        )
    if kcl_max is None or max_vmag is None:
        notes.append(
            "bound unavailable (missing kcl residual or voltage scale); "
            "conservation cannot be certified"
        )
        return ConservationReport(
            total_S=total, total_P=total_p, total_Q=total_q,
            bound=None, passed=False, diagnostics=tuple(notes),
        )
    ctx = make_context()
    kcl_term = ctx.multiply(ctx.multiply(max_vmag, Decimal(n_nets)), kcl_max)
    max_s = Decimal(0)
    for e in elements:
        m = e.apparent
        if m > max_s:
            max_s = m
    rounding_account = ctx.multiply(
        ctx.multiply(Decimal(len(elements) * _ROUNDING_UNITS_PER_ELEMENT), _UNIT_ULP),
        max_s,
    )
    bound = ctx.add(kcl_term, rounding_account)
    total_mod = total.modulus()
    if not isinstance(total_mod, Decimal):
        total_mod = _as_decimal(total_mod)
    passed = total_mod <= bound
    notes.append(
        f"derived bound |sum S| <= max|V| * N_nets * kcl_max "
        f"+ M*{_ROUNDING_UNITS_PER_ELEMENT}*ulp*max|S| = {bound}; "
        f"|sum S| = {total_mod}"
    )
    return ConservationReport(
        total_S=total, total_P=total_p, total_Q=total_q,
        bound=bound, passed=passed, diagnostics=tuple(notes),
    )


def analyze_power(ac_solution) -> ACPowerAnalysis:
    """Analyze power over a SOLVED :class:`ACSolution` (read-only).

    Raises :class:`PowerAnalysisError` for any non-SOLVED status:
    without (certified) branch quantities there is nothing physical to
    analyze.
    """
    if ac_solution.status != ACStatus.SOLVED:
        raise PowerAnalysisError(
            f"power analysis requires a SOLVED AC solution, got "
            f"{ac_solution.status}"
        )
    by_current = {c.ref.upper(): c for c in ac_solution.branch_currents}
    by_voltage = {v.ref.upper(): v for v in ac_solution.branch_voltages}
    if set(by_current) != set(by_voltage):
        raise PowerAnalysisError("branch current/voltage reference mismatch")
    elements: list[ElementPower] = []
    for ref in sorted(by_current):
        elements.append(compute_element_power(
            by_voltage[ref].voltage, by_current[ref].current, ref=ref,
            convention=by_current[ref].convention,
        ))
    elements_t = tuple(elements)
    ctx = make_context()
    max_vmag = Decimal(0)
    for nv in ac_solution.node_voltages:
        m = nv.phasor.modulus()
        if not isinstance(m, Decimal):
            m = _as_decimal(m)
        if m > max_vmag:
            max_vmag = m
    n_nets = len(ac_solution.node_voltages)
    exact = ac_solution.numeric_mode == NumericMode.EXACT
    conservation = verify_conservation(
        elements_t, exact=exact,
        kcl_max=ac_solution.kcl_max_residual,
        max_vmag=max_vmag, n_nets=n_nets,
    )
    op = ac_solution.operating_point
    diags: list[str] = list(ac_solution.diagnostics)[:4]
    diags.append(f"power_elements={len(elements_t)}")
    diags.append(f"conservation_passed={conservation.passed}")
    none_pf = sorted(e.ref for e in elements_t if e.pf is None)
    if none_pf:
        diags.append(
            f"undefined PF (|S| exactly zero, no division performed): "
            f"{', '.join(none_pf)}"
        )
    diagnostics = tuple(diags)
    provenance = {
        "engine": "f8d-ac-power",
        "version": "1.0",
        "frequency": op.frequency.format() if op is not None else "unknown",
        "frequency_base_hz": str(op.frequency.to_base()) if op is not None else "unknown",
        "angular_frequency_rad_per_s": str(op.omega) if op is not None else "unknown",
        "temporal_convention": op.time_convention if op is not None else "unknown",
        "amplitude_convention": op.amplitude_convention if op is not None else "unknown",
        "power_convention": POWER_CONVENTION,
        "numeric_mode": ac_solution.numeric_mode.value
        if ac_solution.numeric_mode is not None else "unknown",
        "working_precision": ac_solution.working_precision,
        "branch_refs": [e.ref for e in elements_t],
        "conservation_bound": None if conservation.bound is None
        else str(conservation.bound),
        "conservation_passed": conservation.passed,
        "solution_digest": ac_solution.digest,
    }
    digest = hashlib.sha256(json.dumps({
        "engine": ENGINE_VERSION,
        "elements": [e.to_dict() for e in elements_t],
        "conservation": conservation.to_dict(),
        "mode": provenance["numeric_mode"],
        "frequency_base_hz": provenance["frequency_base_hz"],
        "solution_digest": ac_solution.digest,
    }, sort_keys=True, default=str).encode()).hexdigest()
    return ACPowerAnalysis(
        elements=elements_t, conservation=conservation,
        numeric_mode=ac_solution.numeric_mode,
        working_precision=ac_solution.working_precision,
        frequency=provenance["frequency"],
        angular_frequency=provenance["angular_frequency_rad_per_s"],
        provenance=provenance, diagnostics=diagnostics, digest=digest,
    )
