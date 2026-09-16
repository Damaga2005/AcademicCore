"""Branch impedance/admittance for F8-D5 (constitutive vs operating ratio).

Two strictly separated concepts:

* Constitutive (element property): for R/L/C branches only, derived
  from the branch admittance already stamped by F8-D3 — ``Z = 1/Y`` for
  impedance, ``Y`` directly (never ``1/Z``) for admittance. Valid even
  when the branch carries no voltage or current in this solution.
  Ideal V/I sources have NO constitutive impedance/admittance
  (``UNDEFINED``): their V/I relation is load-imposed, not constitutive.
* Operating ratio: ``Zratio = Vbranch / Ibranch`` (resp. ``I/V``) from
  the solved branch quantities of any branch, sources included but
  labeled ``operating-ratio`` — never "source impedance". Categories
  ``FINITE`` (includes exact zero), ``INFINITE`` (I=0, V!=0 for Z;
  V=0, I!=0 for Y), ``UNDEFINED`` (0/0). No ``Decimal("Infinity")``,
  no ``float("inf")`` anywhere: infinity is a category with
  ``value=None``.

Zero tests are representation-exact (D1 ``is_zero_exact``): small but
nonzero values compute normally, never coerced by tolerance.

Orientation follows D3 exactly (pin1->pin2 R/L/C, +->- V/I); the
constitutive value is orientation-independent while the operating
ratio flips jointly with V and I (both tested).

Two-terminal ports (second half of this module):

* ``PortDefinition(A, B)`` with ``Vport = VA - VB`` and ``Iport``
  defined as the current ENTERING A (leaving through B).
* A port coinciding with exactly one physical branch can be read
  directly from the D3 solution (orientation-mapped). A port shared by
  several parallel branches, or spanning no physical branch at all, has
  no observable port current in a single solution — it requires the
  test-source method below.
* Test-source method: build a FRESH derived circuit (original never
  touched) with independent sources deactivated (V -> 0 V short keeping
  MNA structure, I -> branch removed) plus one test source across the
  port (1 A entering A for impedance, 1 V with + at A for admittance),
  solve it through the F8-D3 engine, and read ``Zport = Vport``
  (resp. ``Yport = Iport``). A non-SOLVED derived solve degrades to an
  explicitly labeled UNDEFINED value carrying the solver status —
  solver verdicts are never replaced, per the INFINITE-vs-SINGULAR rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from academic_core.domain.engineering.ac.phasors import magnitude, phase, to_polar
from academic_core.domain.engineering.ac.solution import ACStatus
from academic_core.domain.engineering.math.decimal_complex import DecimalComplex
from academic_core.domain.engineering.math.linsolve.problem import NumericMode
from academic_core.domain.engineering.math.rational import RationalComplex
from academic_core.domain.engineering.units import Quantity, parse_unit

OHM_SYMBOL = "Ω"
SIEMENS_SYMBOL = "S"

BASIS_CONSTITUTIVE = "constitutive"
BASIS_OPERATING_RATIO = "operating-ratio"


class ImpedanceError(ValueError):
    """Misuse of the D5 impedance layer (unknown ref, unsolved parent,
    mismatched problem/solution, value access on a non-finite result)."""


class ImpedanceCategory(Enum):
    FINITE = "finite"
    INFINITE = "infinite"
    UNDEFINED = "undefined"


@dataclass(frozen=True)
class ImpedanceValue:
    category: ImpedanceCategory
    value: RationalComplex | DecimalComplex | None
    basis: str  # constitutive | operating-ratio
    quantity: str  # impedance | admittance
    unit: str  # Ω | S (display label, validated against F6 units)
    ref: str
    diagnostic: str

    def require_finite(self):
        if self.category != ImpedanceCategory.FINITE or self.value is None:
            raise ImpedanceError(
                f"{self.ref}: no finite {self.quantity} "
                f"(category {self.category.value})"
            )
        return self.value

    def magnitude(self) -> Decimal:
        """|Z| / |Y| via the D1 authority (cartesian value preserved)."""
        return magnitude(self.require_finite())

    def phase(self) -> Decimal:
        """Angle in (-pi, pi] via the D1 authority."""
        return phase(self.require_finite())

    def polar(self) -> tuple[Decimal, Decimal]:
        return to_polar(self.require_finite())

    def magnitude_in(self, unit_symbol: str) -> Quantity:
        """Magnitude as an F6 Quantity (dimensional proof, UI/exam use).

        The D1 magnitude is in base units (ohm / siemens); it is divided
        by the requested unit's factor so ``to_base()`` round-trips.
        """
        from academic_core.domain.engineering.math.trig import make_context

        unit = parse_unit(unit_symbol)
        ctx = make_context()
        return Quantity(ctx.divide(self.magnitude(), unit.factor), unit)

    def to_dict(self) -> dict:
        from academic_core.domain.engineering.ac.phasors import fmt_cartesian

        return {
            "category": self.category.value,
            "value": None if self.value is None else fmt_cartesian(self.value),
            "basis": self.basis,
            "quantity": self.quantity,
            "unit": self.unit,
            "ref": self.ref,
            "diagnostic": self.diagnostic,
        }


def _one_like(sample):
    if isinstance(sample, DecimalComplex):
        return DecimalComplex.one()
    return RationalComplex.one()


def _zero_of(sample):
    if isinstance(sample, DecimalComplex):
        return DecimalComplex.zero()
    return RationalComplex.zero()


def _branch_of(problem, ref: str):
    for br in problem.branches:
        if br.ref.upper() == ref.upper():
            return br
    raise ImpedanceError(f"unknown branch ref {ref!r}")


def _check_pair(problem, solution) -> None:
    if solution.status != ACStatus.SOLVED:
        raise ImpedanceError(
            f"impedance analysis requires a SOLVED AC solution, got "
            f"{solution.status}"
        )
    p_refs = {br.ref.upper() for br in problem.branches}
    v_refs = {b.ref.upper() for b in solution.branch_voltages}
    i_refs = {b.ref.upper() for b in solution.branch_currents}
    if p_refs != v_refs or p_refs != i_refs:
        raise ImpedanceError("problem/solution branch mismatch")


def branch_impedance(problem, solution, ref: str) -> ImpedanceValue:
    """Constitutive impedance of an R/L/C branch (``Z = 1/Y``).

    Ideal sources are UNDEFINED by rule (no fictitious impedance).
    """
    _check_pair(problem, solution)
    br = _branch_of(problem, ref)
    if br.type not in ("R", "L", "C") or br.admittance is None:
        return ImpedanceValue(
            ImpedanceCategory.UNDEFINED, None, BASIS_CONSTITUTIVE,
            "impedance", OHM_SYMBOL, br.ref,
            f"{br.ref}: ideal {br.type} source has no constitutive impedance "
            f"(V/I relation is load-imposed, not a property)",
        )
    if br.admittance.is_zero_exact():
        # Unreachable for validated R/L/C (params > 0), kept as guard so
        # a corrupt zero admittance degrades to a category, never a crash.
        return ImpedanceValue(
            ImpedanceCategory.UNDEFINED, None, BASIS_CONSTITUTIVE,
            "impedance", OHM_SYMBOL, br.ref,
            f"{br.ref}: zero admittance cannot invert to an impedance",
        )
    z = _one_like(br.admittance) / br.admittance
    return ImpedanceValue(
        ImpedanceCategory.FINITE, z, BASIS_CONSTITUTIVE, "impedance",
        OHM_SYMBOL, br.ref,
        f"{br.ref}: constitutive Z = 1/Y from the D3 branch admittance",
    )


def branch_admittance(problem, solution, ref: str) -> ImpedanceValue:
    """Constitutive admittance of an R/L/C branch (D3's Y, never ``1/Z``).

    Ideal sources are UNDEFINED by rule.
    """
    _check_pair(problem, solution)
    br = _branch_of(problem, ref)
    if br.type not in ("R", "L", "C") or br.admittance is None:
        return ImpedanceValue(
            ImpedanceCategory.UNDEFINED, None, BASIS_CONSTITUTIVE,
            "admittance", SIEMENS_SYMBOL, br.ref,
            f"{br.ref}: ideal {br.type} source has no constitutive admittance",
        )
    return ImpedanceValue(
        ImpedanceCategory.FINITE, br.admittance, BASIS_CONSTITUTIVE,
        "admittance", SIEMENS_SYMBOL, br.ref,
        f"{br.ref}: constitutive Y taken directly from D3 assembly",
    )


def _v_i_of(solution, ref: str):
    v = next((b.voltage for b in solution.branch_voltages
              if b.ref.upper() == ref.upper()), None)
    i = solution.current_of(ref)
    if v is None or i is None:
        raise ImpedanceError(f"branch {ref!r} missing from solution")
    return v, i


def operating_impedance(solution, ref: str) -> ImpedanceValue:
    """Operating ratio ``Vbranch / Ibranch`` of any branch (labeled).

    Sources included but always ``operating-ratio`` basis, never
    "source impedance".
    """
    if solution.status != ACStatus.SOLVED:
        raise ImpedanceError(
            f"impedance analysis requires a SOLVED AC solution, got "
            f"{solution.status}"
        )
    v, i = _v_i_of(solution, ref)
    up = ref.upper()
    if not i.is_zero_exact():
        return ImpedanceValue(
            ImpedanceCategory.FINITE, v / i, BASIS_OPERATING_RATIO,
            "impedance", OHM_SYMBOL, up,
            f"{up}: operating ratio Vbranch/Ibranch at this operating point",
        )
    if not v.is_zero_exact():
        return ImpedanceValue(
            ImpedanceCategory.INFINITE, None, BASIS_OPERATING_RATIO,
            "impedance", OHM_SYMBOL, up,
            f"{up}: no branch current at nonzero voltage (open behavior)",
        )
    return ImpedanceValue(
        ImpedanceCategory.UNDEFINED, None, BASIS_OPERATING_RATIO,
        "impedance", OHM_SYMBOL, up,
        f"{up}: V = I = 0 admits no ratio",
    )


def operating_admittance(solution, ref: str) -> ImpedanceValue:
    """Operating ratio ``Ibranch / Vbranch`` of any branch (labeled)."""
    if solution.status != ACStatus.SOLVED:
        raise ImpedanceError(
            f"impedance analysis requires a SOLVED AC solution, got "
            f"{solution.status}"
        )
    v, i = _v_i_of(solution, ref)
    up = ref.upper()
    if not v.is_zero_exact():
        ratio = (_zero_of(i) if i.is_zero_exact()
                 else i / v)
        return ImpedanceValue(
            ImpedanceCategory.FINITE, ratio, BASIS_OPERATING_RATIO,
            "admittance", SIEMENS_SYMBOL, up,
            f"{up}: operating ratio Ibranch/Vbranch at this operating point",
        )
    if not i.is_zero_exact():
        return ImpedanceValue(
            ImpedanceCategory.INFINITE, None, BASIS_OPERATING_RATIO,
            "admittance", SIEMENS_SYMBOL, up,
            f"{up}: no branch voltage at nonzero current",
        )
    return ImpedanceValue(
        ImpedanceCategory.UNDEFINED, None, BASIS_OPERATING_RATIO,
        "admittance", SIEMENS_SYMBOL, up,
        f"{up}: V = I = 0 admits no ratio",
    )


BASIS_PORT_DIRECT = "port-direct"
BASIS_PORT_TEST = "port-test"

METHOD_AUTO = "auto"
METHOD_DIRECT = "direct"
METHOD_TEST = "test"


@dataclass(frozen=True)
class PortDefinition:
    """Two-terminal port: positive terminal A first, reference B second.

    ``Vport = VA - VB``; ``Iport`` is the current ENTERING A (and,
    by KCL at the port boundary, leaving through B). Bare names only —
    membership in a circuit is validated at measurement time, where the
    circuit is available.
    """

    node_a: str
    node_b: str

    def __post_init__(self) -> None:
        if not self.node_a or not str(self.node_a).strip():
            raise ImpedanceError("port terminal A must be a non-empty net name")
        if not self.node_b or not str(self.node_b).strip():
            raise ImpedanceError("port terminal B must be a non-empty net name")
        if self.node_a == self.node_b:
            raise ImpedanceError(
                f"degenerate port ({self.node_a!r}, {self.node_b!r}): "
                f"terminals must differ"
            )

    def swapped(self) -> "PortDefinition":
        return PortDefinition(self.node_b, self.node_a)

    def to_dict(self) -> dict:
        return {"A": self.node_a, "B": self.node_b}


def _coincident_branches(problem, port: PortDefinition) -> list:
    """Branches whose endpoint pair is exactly {A, B} (edge identity kept)."""
    out = []
    for br in problem.branches:
        if {br.node_a, br.node_b} == {port.node_a, port.node_b}:
            out.append(br)
    return out


def _free_test_ref(used: set[str], letter: str) -> str:
    k = 1
    while f"{letter}{k}" in used:
        k += 1
    return f"{letter}{k}"


def deactivate_sources(circuit, keep: str = ""):
    """Derived component list with independent sources deactivated.

    V -> 0 V short (same ref/pins/parameters/unit, MNA structure kept);
    I -> branch removed (open); R/L/C objects reused untouched (frozen).
    Dependent sources (E/G/H/F) are ALWAYS kept active with full control
    data: test-source and transfer measurements on active networks
    require dependents present (F8-E rule); deactivating them would
    answer a different (passive) network.     Ideal op-amps (O) are likewise
    ALWAYS kept (F8-F rule: the nullor constraint belongs to the network
    under measurement). Ideal transformers (T) are likewise ALWAYS kept
    (F8-G rule: the turns-ratio constraints belong to the network under
    measurement). ``keep`` (an independent V/I
    source ref, case-insensitive) preserves one source with its
    original excitation — used by network-transfer measurement.
    Returns a NEW list; the input circuit is only read.
    """
    from academic_core.domain.engineering.circuit import Component
    from academic_core.domain.engineering.units import Quantity

    out = []
    for c in circuit.components:
        if c.ref.upper() == keep.upper() and keep:
            out.append(c)
            continue
        t = c.type.upper()
        if t == "V":
            out.append(Component(
                c.ref, c.type,
                Quantity(Decimal(0), c.value.unit) if c.value is not None
                else c.value,
                dict(c.pins), dict(c.parameters), dict(c.metadata),
            ))
        elif t == "I":
            continue
        else:
            out.append(c)
    return out


def _port_ratio(vport, iport, PortDefinition, quantity: str, basis: str,
                extra: str) -> ImpedanceValue:
    """Shared V/I (resp. I/V) categorization for port measurements."""
    if quantity == "impedance":
        num, den = vport, iport
        unit = OHM_SYMBOL
    else:
        num, den = iport, vport
        unit = SIEMENS_SYMBOL
    tag = f"port({PortDefinition.node_a},{PortDefinition.node_b})"
    if not den.is_zero_exact():
        return ImpedanceValue(
            ImpedanceCategory.FINITE, num / den, basis, quantity, unit,
            tag, f"{tag}: {extra}",
        )
    if not num.is_zero_exact():
        return ImpedanceValue(
            ImpedanceCategory.INFINITE, None, basis, quantity, unit,
            tag, f"{tag}: zero denominator at nonzero numerator "
                 f"(open behavior, not a solver verdict){extra}",
        )
    return ImpedanceValue(
        ImpedanceCategory.UNDEFINED, None, basis, quantity, unit,
        tag, f"{tag}: 0/0 admits no ratio{extra}",
    )


def _direct_port(problem, solution, port: PortDefinition,
                 quantity: str) -> ImpedanceValue:
    coinc = _coincident_branches(problem, port)
    if len(coinc) != 1:
        raise ImpedanceError(
            f"direct port method needs exactly one coincident branch for "
            f"({port.node_a}, {port.node_b}), found {len(coinc)}"
        )
    br = coinc[0]
    v = next(b.voltage for b in solution.branch_voltages
             if b.ref.upper() == br.ref.upper())
    i = next(b.current for b in solution.branch_currents
             if b.ref.upper() == br.ref.upper())
    # D3 branch orientation is node_a -> node_b; flip jointly if the port
    # runs the other way so (Vport, Iport) keep entering-A convention.
    if (br.node_a, br.node_b) == (port.node_a, port.node_b):
        vport, iport = v, i
    else:
        vport, iport = -v, -i
    return _port_ratio(vport, iport, port, quantity, BASIS_PORT_DIRECT,
                       f" from unique branch {br.ref}")


def _test_port(problem, port: PortDefinition, quantity: str) -> ImpedanceValue:
    """Test-source measurement on a FRESH derived circuit.

    Impedance: independent sources deactivated + 1 A test current source
    (+ at A, i.e. entering A); ``Zport = Vport``. Admittance: 1 V test
    voltage source (+ at A); ``Yport = Iport`` where Iport (entering A)
    is the negation of the MNA unknown (which flows + -> -, leaving A).
    A non-SOLVED derived solve becomes an explicitly labeled UNDEFINED
    value carrying the solver status — never a silent fallback, never a
    replaced verdict.
    """
    from academic_core.domain.engineering.ac.solver import solve_ac
    from academic_core.domain.engineering.circuit import Circuit, Component
    from academic_core.domain.engineering.units import Quantity, parse_unit

    circuit = problem.circuit
    nets = set(circuit.nets)
    for terminal in (port.node_a, port.node_b):
        if terminal not in nets:
            raise ImpedanceError(
                f"port terminal {terminal!r} is not a net of circuit "
                f"{circuit.name!r}"
            )
    derived = deactivate_sources(circuit)
    used = {c.ref.upper() for c in derived}
    op = problem.operating_point
    if quantity == "impedance":
        tref = _free_test_ref(used, "I")
        derived.append(Component(
            tref, "I", Quantity(Decimal(1), parse_unit("A")),
            {"+": port.node_a, "-": port.node_b}, {},
        ))
        policy = (f"deactivation V->0V short/I->removed + test current "
                  f"{tref}=1A entering {port.node_a}")
    else:
        tref = _free_test_ref(used, "V")
        derived.append(Component(
            tref, "V", Quantity(Decimal(1), parse_unit("V")),
            {"+": port.node_a, "-": port.node_b}, {},
        ))
        policy = (f"deactivation V->0V short/I->removed + test voltage "
                  f"{tref}=1V (+ at {port.node_a})")
    fresh = Circuit(f"{circuit.name}+{tref}")
    for c in derived:
        fresh.add(c)
    res = solve_ac(fresh, op.frequency, NumericMode.AUTO)
    tag_extra = f" [{policy}; test ref {tref}]"
    if res.status != ACStatus.SOLVED:
        return ImpedanceValue(
            ImpedanceCategory.UNDEFINED, None, BASIS_PORT_TEST, quantity,
            OHM_SYMBOL if quantity == "impedance" else SIEMENS_SYMBOL,
            f"port({port.node_a},{port.node_b})",
            f"derived measurement solve: {res.status.value}{tag_extra}",
        )
    va = res.voltage_of(port.node_a)
    vb = res.voltage_of(port.node_b)
    assert va is not None and vb is not None
    vport = va - vb
    if quantity == "impedance":
        # Iport is forced to 1 A entering A by construction.
        return _port_ratio(vport, _one_like(vport), port, quantity,
                           BASIS_PORT_TEST, tag_extra)
    i_unknown = res.current_of(tref)
    assert i_unknown is not None
    # Vport is forced to 1 V; Iport (entering A) negates the MNA unknown
    # (which flows + -> -, i.e. leaving A).
    return _port_ratio(_one_like(vport), -i_unknown, port, quantity,
                       BASIS_PORT_TEST, tag_extra)


def _one_like(sample):
    from academic_core.domain.engineering.math.decimal_complex import (
        DecimalComplex as _DC,
    )
    from academic_core.domain.engineering.math.rational import (
        RationalComplex as _RC,
    )
    return _DC.one() if isinstance(sample, _DC) else _RC.one()


def measure_port(problem, solution, port: PortDefinition,
                 quantity: str = "impedance",
                 method: str = METHOD_AUTO) -> ImpedanceValue:
    """Measure a two-terminal port (impedance or admittance).

    ``method="auto"`` uses the direct solution readout when exactly one
    physical branch coincides with the port, else the test-source
    method. Explicit ``"direct"``/``"test"`` override (direct on a
    non-unique coincidence raises). INFINITE here is open behavior, and
    a failing derived solve surfaces as labeled UNDEFINED — solver
    verdicts (SINGULAR/...) are preserved in the diagnostic, never
    converted into infinities.
    """
    if quantity not in ("impedance", "admittance"):
        raise ImpedanceError(f"quantity must be impedance|admittance, got {quantity!r}")
    if method not in (METHOD_AUTO, METHOD_DIRECT, METHOD_TEST):
        raise ImpedanceError(f"method must be auto|direct|test, got {method!r}")
    _check_pair(problem, solution)
    if method == METHOD_DIRECT:
        return _direct_port(problem, solution, port, quantity)
    if method == METHOD_TEST:
        return _test_port(problem, port, quantity)
    coinc = _coincident_branches(problem, port)
    if len(coinc) == 1:
        return _direct_port(problem, solution, port, quantity)
    return _test_port(problem, port, quantity)
