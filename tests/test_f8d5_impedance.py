"""F8-D5 AC impedance/admittance/frequency response.

D5-A: Siemens units + branch constitutive impedance/admittance +
operating ratios. Conventions: EXACT assertions are representation-exact;
HP carries explicit tolerances; closed forms are transcribed literals and
direct formulas evaluated here, never engine outputs.
"""
import ast
import json
import pathlib
from decimal import Decimal
from fractions import Fraction

import pytest

from academic_core.domain.engineering.ac import (
    ACStatus,
    build_ac_problem,
    solve_ac,
)
from academic_core.domain.engineering.ac.impedance import (
    BASIS_CONSTITUTIVE,
    BASIS_OPERATING_RATIO,
    BASIS_PORT_DIRECT,
    BASIS_PORT_TEST,
    METHOD_TEST,
    ImpedanceCategory,
    ImpedanceError,
    PortDefinition,
    branch_admittance,
    branch_impedance,
    deactivate_sources,
    measure_port,
    operating_admittance,
    operating_impedance,
)
from academic_core.domain.engineering.ac.response import (
    BASIS_NETWORK_TRANSFER,
    BASIS_OPERATING_POINT_RATIO,
    TransferKind,
    analyze_transfer,
    current_through,
    network_transfer,
    voltage_between,
)
from academic_core.domain.engineering.ac.response import (
    ResponseDefinition,
    SweepResult,
    frequency_response,
    linear_frequencies,
)
from academic_core.domain.engineering.ac.operating_point import ACOperatingPoint
from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.math import DecimalComplex, RationalComplex
from academic_core.domain.engineering.math import decimal_pi_value
from academic_core.domain.engineering.math.linsolve import NumericMode
from academic_core.domain.engineering.math.trig import make_context
from academic_core.domain.engineering.units import (
    ADMITTANCE,
    POWER,
    TIME,
    UnitError,
    parse_quantity,
    parse_unit,
)

CTX = make_context()
TOL = Decimal("1E-40")
PI50 = Decimal("3.14159265358979323846264338327950288419716939937510")


def Q(text):
    return parse_quantity(text)


def R_(ref, value, n1, n2):
    return Component(ref, "R", Q(value), {"1": n1, "2": n2})


def L_(ref, value, n1, n2):
    return Component(ref, "L", Q(value), {"1": n1, "2": n2})


def C_(ref, value, n1, n2):
    return Component(ref, "C", Q(value), {"1": n1, "2": n2})


def V_(ref, value, np_, nm, phase_=0, punit="deg"):
    params = {}
    if not (isinstance(phase_, int) and phase_ == 0):
        params["phase"] = phase_
    if punit != "deg":
        params["phase_unit"] = punit
    return Component(ref, "V", Q(value), {"+": np_, "-": nm}, dict(params))


def I_(ref, value, np_, nm, phase_=0, punit="deg"):
    params = {}
    if not (isinstance(phase_, int) and phase_ == 0):
        params["phase"] = phase_
    if punit != "deg":
        params["phase_unit"] = punit
    return Component(ref, "I", Q(value), {"+": np_, "-": nm}, dict(params))


def ckt(name, *comps):
    c = Circuit(name)
    for e in comps:
        c.add(e)
    return c


def solved(circuit, freq):
    sol = solve_ac(circuit, freq)
    assert sol.status == ACStatus.SOLVED, sol.diagnostics
    return sol


def problem_and_solution(circuit, freq, mode=None):
    from academic_core.domain.engineering.ac.topology import reference_net

    ground = reference_net(circuit.nets)
    op = ACOperatingPoint.from_frequency(Q(freq), ground)
    kwargs = {} if mode is None else {"mode": mode}
    prob = build_ac_problem(circuit, op, **kwargs)
    sol = solved(circuit, freq)
    return prob, sol


# -- D5-A units --------------------------------------------------------------------------------

def test_units_siemens_parse_and_dimension():
    for s in ("S", "mS", "uS", "nS", "kS", "Siemens", "siemens", "MS", "GS", "pS"):
        u = parse_unit(s)
        assert u.dimension == ADMITTANCE, s
    assert parse_unit("S").display == "S"
    assert parse_unit("mS").display == "mS"
    assert parse_unit("Siemens").display == "S"


def test_units_seconds_untouched_collision_pins():
    for s in ("s", "ms", "us", "ns", "ks"):
        assert parse_unit(s).dimension == TIME, s
    assert parse_quantity("5 ms").to_base() == Decimal("0.005")
    assert parse_quantity("5 mS").to_base() == Decimal("0.005")
    # Same base magnitude, DIFFERENT dimensions: the collision is resolved.
    assert parse_quantity("5 ms").dimension == TIME
    assert parse_quantity("5 mS").dimension == ADMITTANCE
    assert parse_quantity("5 mS").dimension != parse_quantity("5 ms").dimension


def test_units_dimensional_proofs():
    prod = parse_quantity("2 S") * parse_quantity("3 ohm")
    assert prod.dimension == (0, 0, 0, 0, 0, 0, 0)  # S x ohm = 1
    y = parse_quantity("2 A") / parse_quantity("1 V")
    assert y.dimension == ADMITTANCE  # A/V = S
    assert y.convert_to("mS").value == Decimal("2000")
    assert y.convert_to("S").value == Decimal(2)
    # 1/Y converts back to ohms through the engine (I/V dimension math).
    inv_base = Decimal(1) / parse_quantity("4 S").to_base()
    assert inv_base == Decimal("0.25")  # 0.25 ohm worth of impedance


def test_units_existing_behavior_unchanged():
    assert parse_quantity("1 kohm").to_base() == Decimal(1000)
    assert parse_quantity("10 V").convert_to("mV").value == Decimal(10000)
    assert parse_quantity("5 kvar").to_base() == Decimal(5000)
    assert parse_unit("W").dimension == POWER
    assert parse_unit("Hz").dimension == (0, 0, -1, 0, 0, 0, 0)
    for bad in ("SS", "SX", "Sv", "", "Siemenss"):
        with pytest.raises(UnitError):
            parse_unit(bad)


# -- D5-A branch constitutive --------------------------------------------------------------------

def test_branch_resistor_constitutive_exact():
    c = ckt("r", V_("V1", "10 V", "n", "0"), R_("R1", "2 kOhm", "n", "0"))
    prob, sol = problem_and_solution(c, "1 kHz")
    assert prob.kind == "rational"
    z = branch_impedance(prob, sol, "R1")
    assert z.category == ImpedanceCategory.FINITE
    assert z.basis == BASIS_CONSTITUTIVE and z.quantity == "impedance"
    assert z.value == RationalComplex(Fraction(2000), Fraction(0))
    y = branch_admittance(prob, sol, "R1")
    assert y.value == RationalComplex(Fraction(1, 2000), Fraction(0))
    assert y.unit == "S" and z.unit == "Ω"


def test_branch_inductor_constitutive_hp():
    # Z = jwL, wL from PI50 here (independent path).
    wl = CTX.multiply(CTX.multiply(CTX.multiply(Decimal(2), PI50), Decimal(1000)),
                      Decimal("0.01"))
    c = ckt("l", V_("V1", "10 V", "n", "0"), L_("L1", "10 mH", "n", "0"))
    prob, sol = problem_and_solution(c, "1000 Hz")
    z = branch_impedance(prob, sol, "L1")
    assert z.category == ImpedanceCategory.FINITE
    assert abs(CTX.subtract(z.value.re, Decimal(0))) <= TOL
    assert abs(CTX.subtract(z.value.im, wl)) <= Decimal("1E-40")
    y = branch_admittance(prob, sol, "L1")
    assert abs(CTX.subtract(y.value.im, CTX.minus(CTX.divide(Decimal(1), wl)))) <= TOL
    # Constitutive Y is D3's own admittance, not 1/Z.
    br = next(b for b in prob.branches if b.ref == "L1")
    assert y.value == br.admittance


def test_branch_capacitor_constitutive_hp():
    wc = CTX.multiply(CTX.multiply(CTX.multiply(Decimal(2), PI50), Decimal(1000)),
                      Decimal("0.000001"))
    c = ckt("c", V_("V1", "10 V", "n", "0"), C_("C1", "1 uF", "n", "0"))
    prob, sol = problem_and_solution(c, "1000 Hz")
    z = branch_impedance(prob, sol, "C1")
    assert abs(CTX.subtract(z.value.re, Decimal(0))) <= TOL
    assert abs(CTX.subtract(z.value.im, CTX.minus(CTX.divide(Decimal(1), wc)))) <= TOL
    y = branch_admittance(prob, sol, "C1")
    assert abs(CTX.subtract(y.value.im, wc)) <= TOL
    br = next(b for b in prob.branches if b.ref == "C1")
    assert y.value == br.admittance


def test_branch_sources_constitutive_undefined():
    c = ckt("s", V_("V1", "10 V", "a", "0"), I_("I1", "5 mA", "a", "b"),
            R_("R1", "1 kOhm", "b", "0"))
    prob, sol = problem_and_solution(c, "1 kHz")
    for ref in ("V1", "I1"):
        z = branch_impedance(prob, sol, ref)
        assert z.category == ImpedanceCategory.UNDEFINED and z.value is None
        y = branch_admittance(prob, sol, ref)
        assert y.category == ImpedanceCategory.UNDEFINED and y.value is None


def test_branch_constitutive_valid_unexcited():
    # Balanced bridge center: V=I=0 yet R5's constitutive Z is still 1k.
    c = ckt("u", V_("V1", "10 V", "t", "0"), R_("R1", "1 kOhm", "t", "a"),
            R_("R2", "1 kOhm", "t", "b"), R_("R3", "1 kOhm", "a", "0"),
            R_("R4", "1 kOhm", "b", "0"), R_("R5", "1 kOhm", "a", "b"))
    prob, sol = problem_and_solution(c, "1 kHz")
    z = branch_impedance(prob, sol, "R5")
    assert z.value == RationalComplex(Fraction(1000), Fraction(0))
    r = operating_impedance(sol, "R5")
    assert r.category == ImpedanceCategory.UNDEFINED and r.value is None


def test_operating_ratio_finite_and_zero():
    c = ckt("op", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "out"),
            R_("R2", "2 kOhm", "out", "0"))
    sol = solved(c, "1 kHz")
    z = operating_impedance(sol, "R2")
    assert z.category == ImpedanceCategory.FINITE
    assert z.basis == BASIS_OPERATING_RATIO
    assert z.value == RationalComplex(Fraction(2000), Fraction(0))
    y = operating_admittance(sol, "R2")
    assert y.value == RationalComplex(Fraction(1, 2000), Fraction(0))
    # 0V source carrying current: FINITE ZERO ratio (value exact zero).
    c2 = ckt("op0", V_("V1", "10 V", "a", "0"), V_("V2", "0 V", "a", "b"),
             R_("R1", "1 kOhm", "b", "0"))
    sol2 = solved(c2, "1 kHz")
    z0 = operating_impedance(sol2, "V2")
    assert z0.category == ImpedanceCategory.FINITE
    assert z0.value == RationalComplex(Fraction(0), Fraction(0))


def test_operating_ratio_infinite():
    # 0A current source with nonzero terminal voltage: I=0, V!=0.
    c = ckt("oi", V_("V1", "10 V", "a", "0"), I_("I1", "0 A", "a", "b"),
            R_("R1", "1 kOhm", "b", "0"))
    sol = solved(c, "1 kHz")
    z = operating_impedance(sol, "I1")
    assert z.category == ImpedanceCategory.INFINITE and z.value is None
    assert "open" in z.diagnostic
    y = operating_admittance(sol, "I1")
    assert y.category == ImpedanceCategory.FINITE
    assert y.value == RationalComplex(Fraction(0), Fraction(0))


def test_orientation_invariance():
    c1 = ckt("o1", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "out"),
             R_("R2", "2 kOhm", "out", "0"))
    c2 = ckt("o2", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "out", "in"),
             R_("R2", "2 kOhm", "out", "0"))
    p1, s1 = problem_and_solution(c1, "1 kHz")
    p2, s2 = problem_and_solution(c2, "1 kHz")
    # Constitutive Z ignores orientation...
    assert (branch_impedance(p1, s1, "R1").value
            == branch_impedance(p2, s2, "R1").value)
    # ...and the operating ratio is jointly invariant (V and I flip together).
    assert (operating_impedance(s1, "R1").value
            == operating_impedance(s2, "R1").value)


def test_magnitude_phase_views_and_units():
    c = ckt("mp", V_("V1", "10 V", "n", "0"), L_("L1", "10 mH", "n", "0"))
    prob, sol = problem_and_solution(c, "1000 Hz")
    z = branch_impedance(prob, sol, "L1")
    assert abs(CTX.subtract(z.phase(), CTX.divide(PI50, Decimal(2)))) <= Decimal("1E-40")
    q = z.magnitude_in("ohm")
    assert q.dimension == (1, 2, -3, -2, 0, 0, 0)
    y = branch_admittance(prob, sol, "L1")
    qs = y.magnitude_in("mS")
    assert qs.dimension == ADMITTANCE
    expect_ms = CTX.multiply(CTX.divide(Decimal(1), z.magnitude()), Decimal(1000))
    assert abs(CTX.subtract(qs.value, expect_ms)) <= TOL
    # to_base() rounds through F6's ambient-context multiply (28 digits):
    # documented F6 boundary, asserted loosely here, not D5's precision.
    assert abs(qs.to_base() - CTX.divide(Decimal(1), z.magnitude())) <= Decimal("1E-27")
    with pytest.raises(ImpedanceError):
        branch_impedance(prob, sol, "V1").require_finite()


def test_impedance_misuse_errors():
    c = ckt("e", V_("V1", "10 V", "n", "0"), R_("R1", "1 kOhm", "n", "0"))
    prob, sol = problem_and_solution(c, "1 kHz")
    with pytest.raises(ImpedanceError):
        branch_impedance(prob, sol, "R9")
    bad = solve_ac(ckt("e2", V_("V1", "10 V", "n", "0"), V_("V2", "5 V", "n", "0")),
                   "1 kHz")
    assert bad.status.value == "inconsistent"
    with pytest.raises(ImpedanceError):
        branch_impedance(prob, bad, "R1")
    with pytest.raises(ImpedanceError):
        operating_impedance(bad, "V1")


def test_impedance_misuse_errors():
    c = ckt("e", V_("V1", "10 V", "n", "0"), R_("R1", "1 kOhm", "n", "0"))
    prob, sol = problem_and_solution(c, "1 kHz")
    with pytest.raises(ImpedanceError):
        branch_impedance(prob, sol, "R9")
    bad = solve_ac(ckt("e2", V_("V1", "10 V", "n", "0"), V_("V2", "5 V", "n", "0")),
                   "1 kHz")
    assert bad.status.value == "inconsistent"
    with pytest.raises(ImpedanceError):
        branch_impedance(prob, bad, "R1")
    with pytest.raises(ImpedanceError):
        operating_impedance(bad, "V1")


# -- D5-B ports ------------------------------------------------------------------------------------

def _divider():
    return ckt("div", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "out"),
               R_("R2", "2 kOhm", "out", "0"))


def test_port_definition_validation():
    assert PortDefinition("a", "0").to_dict() == {"A": "a", "B": "0"}
    assert PortDefinition("a", "b").swapped() == PortDefinition("b", "a")
    with pytest.raises(ImpedanceError):
        PortDefinition("a", "a")
    with pytest.raises(ImpedanceError):
        PortDefinition("", "0")
    with pytest.raises(ImpedanceError):
        PortDefinition("x", "")


def test_port_branch_direct_and_orientation():
    prob, sol = problem_and_solution(_divider(), "1 kHz")
    fwd = measure_port(prob, sol, PortDefinition("out", "0"))
    assert fwd.category == ImpedanceCategory.FINITE
    assert fwd.basis == BASIS_PORT_DIRECT
    assert fwd.value == RationalComplex(Fraction(2000), Fraction(0))
    rev = measure_port(prob, sol, PortDefinition("0", "out"))
    # Joint V/I flip leaves the ratio invariant: passive impedance has
    # no sign under port reversal (orientation lives in Vport/Iport,
    # not in their ratio).
    assert rev.value == RationalComplex(Fraction(2000), Fraction(0))
    # ...while the constitutive element value never involved orientation.
    assert (branch_impedance(prob, sol, "R2").value
            == RationalComplex(Fraction(2000), Fraction(0)))


def test_port_direct_vs_test_diverge_by_design():
    # Direct reads the branch property (R2 = 2k); test-source reads the
    # network impedance at those terminals (R2 || (R1 + Vshort) = 2k/3).
    # Different questions, different correct answers.
    prob, sol = problem_and_solution(_divider(), "1 kHz")
    d = measure_port(prob, sol, PortDefinition("out", "0"), method="direct")
    t = measure_port(prob, sol, PortDefinition("out", "0"), method="test")
    assert d.value == RationalComplex(Fraction(2000), Fraction(0))
    assert t.basis == BASIS_PORT_TEST
    assert t.value == RationalComplex(Fraction(2000, 3), Fraction(0))


def test_port_equivalence_series_current_loop():
    # V-R-I series loop, port across R1: deactivation leaves R1 as the
    # sole path, so direct and test-source MUST agree (proved equality).
    c = ckt("sl", V_("V1", "10 V", "a", "0"), R_("R1", "1 kOhm", "a", "b"),
            I_("I1", "5 mA", "b", "0"))
    prob, sol = problem_and_solution(c, "1 kHz")
    assert sol.status == ACStatus.SOLVED
    d = measure_port(prob, sol, PortDefinition("a", "b"), method="direct")
    t = measure_port(prob, sol, PortDefinition("a", "b"), method="test")
    assert d.value == t.value == RationalComplex(Fraction(1000), Fraction(0))


def test_port_arbitrary_no_branch():
    # Ladder V(n0,0)-R1(n0,n1)-R2(n1,n2)-R3(n2,0): (n0,n2) spans no branch.
    c = ckt("arb", V_("V1", "10 V", "n0", "0"), R_("R1", "1 kOhm", "n0", "n1"),
            R_("R2", "1 kOhm", "n1", "n2"), R_("R3", "2 kOhm", "n2", "0"))
    prob, sol = problem_and_solution(c, "1 kHz")
    with pytest.raises(ImpedanceError):
        measure_port(prob, sol, PortDefinition("n0", "n2"), method="direct")
    # ...ambiguous direct readout refused; test-source answers instead.
    t = measure_port(prob, sol, PortDefinition("n0", "n2"), method="test")
    assert t.category == ImpedanceCategory.FINITE
    # Hand nodal on the deactivated network (V->short across n0-0), 1A
    # n0->n2: Vn2 = -1000 V, Vport = Vn0-Vn2 = 1000 V. Cross-check:
    # (R1+R2)||R3 = 2k||2k = 1k from the grounded port end.
    assert t.value == RationalComplex(Fraction(1000), Fraction(0))


def test_port_cases_ground_and_reversed_and_source():
    prob, sol = problem_and_solution(_divider(), "1 kHz")
    gnd_b = measure_port(prob, sol, PortDefinition("out", "0"), method="test")
    assert gnd_b.value == RationalComplex(Fraction(2000, 3), Fraction(0))
    gnd_a = measure_port(prob, sol, PortDefinition("0", "out"), method="test")
    # Reciprocity (deactivated network is passive): same impedance.
    assert gnd_a.value == RationalComplex(Fraction(2000, 3), Fraction(0))
    # Port across an ideal source, live network: operating ratio V/I...
    live = measure_port(prob, sol, PortDefinition("in", "0"), method="direct")
    assert live.basis == BASIS_PORT_DIRECT  # single coincident branch V1
    # ...versus network input impedance with the source deactivated (short).
    zin = measure_port(prob, sol, PortDefinition("in", "0"), method="test")
    assert zin.value == RationalComplex(Fraction(0), Fraction(0))
    assert zin.category == ImpedanceCategory.FINITE  # zero, not undefined


def test_port_dead_network():
    # No independent sources: direct has nothing to observe (0/0)...
    c = ckt("dead", R_("R1", "1 kOhm", "a", "b"), R_("R2", "2 kOhm", "b", "0"),
            V_("V1", "0 V", "a", "0"))
    prob, sol = problem_and_solution(c, "1 kHz")
    d = measure_port(prob, sol, PortDefinition("a", "b"), method="direct")
    assert d.category == ImpedanceCategory.UNDEFINED
    # ...but the test source excites the dead network into answering.
    t = measure_port(prob, sol, PortDefinition("a", "b"), method="test")
    assert t.category == ImpedanceCategory.FINITE
    # Deactivated: V1->short across a-0; port sees R1 || R2 = 2k/3.
    assert t.value == RationalComplex(Fraction(2000, 3), Fraction(0))


def test_port_deactivation_and_immutability():
    c = _divider()
    before = c.to_netlist()
    params_before = {e.ref: (dict(e.parameters), str(e.value)) for e in c.components}
    prob, sol = problem_and_solution(c, "1 kHz")
    comp = deactivate_sources(c)
    # V shorted in place (ref/pins kept), I removed, R/L/C identical objects.
    kinds = {e.ref: e.type for e in comp}
    assert kinds == {"V1": "V", "R1": "R", "R2": "R"}
    assert next(e for e in comp if e.ref == "V1").value == parse_quantity("0 V")
    assert c.to_netlist() == before
    assert {e.ref: (dict(e.parameters), str(e.value)) for e in c.components} == params_before
    # Measuring never mutates the original circuit.
    measure_port(prob, sol, PortDefinition("in", "out"), method="test")
    assert c.to_netlist() == before


def test_port_admittance_vtest():
    prob, sol = problem_and_solution(_divider(), "1 kHz")
    y = measure_port(prob, sol, PortDefinition("out", "0"), quantity="admittance",
                     method="test")
    assert y.category == ImpedanceCategory.FINITE
    assert y.quantity == "admittance" and y.unit == "S"
    # Y = 1/(R2||R1) = 3/2kS, measured with the 1V-test methodology.
    assert y.value == RationalComplex(Fraction(3, 2000), Fraction(0))
    yd = measure_port(prob, sol, PortDefinition("out", "0"), quantity="admittance")
    assert yd.basis == BASIS_PORT_DIRECT
    assert yd.value == RationalComplex(Fraction(1, 2000), Fraction(0))


def test_port_derived_inconsistent_stays_verdict():
    # V-test (1V) across a deactivated (0V) source branch is contradictory
    # by construction: the derived solve is INCONSISTENT, and that verdict
    # must surface in the diagnostic — never laundered into INFINITE.
    prob, sol = problem_and_solution(_divider(), "1 kHz")
    y = measure_port(prob, sol, PortDefinition("in", "0"), quantity="admittance",
                     method="test")
    assert y.category == ImpedanceCategory.UNDEFINED and y.value is None
    assert "inconsistent" in y.diagnostic


def test_port_open_behavior_vs_solver_status():
    # A floating parent cannot assemble at all: the topology guard fires
    # before any ratio category is even considered (INFINITE is open
    # behavior of a SOLVED system, never a topology/singularity verdict).
    from academic_core.domain.engineering.ac import FloatingCircuitError

    c = ckt("fl", V_("V1", "10 V", "a", "0"), R_("R1", "1 kOhm", "a", "0"),
            R_("R2", "1 kOhm", "x", "y"))
    with pytest.raises(FloatingCircuitError):
        problem_and_solution(c, "1 kHz")


# -- D5-C transfers ------------------------------------------------------------------------------

def _rc_lowpass():
    return ckt("lp", V_("V1", "5 V", "in", "0"), R_("R1", "1 kOhm", "in", "out"),
               C_("C1", "1 uF", "out", "0"))


def test_transfer_voltage_gain_network():
    prob, sol = problem_and_solution(_rc_lowpass(), "1000 Hz")
    h = network_transfer(prob, sol, "V1", voltage_between("in", "0"),
                         voltage_between("out", "0"))
    assert h.kind == TransferKind.VOLTAGE_GAIN
    assert h.defined and h.basis == BASIS_NETWORK_TRANSFER
    assert h.input_source == "V1" and h.unit == "1"
    # Independent closed form Vout/Vin = 1/(1+jwRC), wRC from PI50 here.
    wrc = CTX.multiply(CTX.multiply(CTX.multiply(Decimal(2), PI50), Decimal(1000)),
                       CTX.multiply(Decimal(1000), Decimal("0.000001")))
    den = CTX.add(Decimal(1), CTX.multiply(wrc, wrc))
    exp_re = CTX.divide(Decimal(1), den)
    exp_im = CTX.minus(CTX.divide(wrc, den))
    assert abs(CTX.subtract(h.value.re, exp_re)) <= Decimal("1E-40")
    assert abs(CTX.subtract(h.value.im, exp_im)) <= Decimal("1E-40")


def test_transfer_current_gain():
    prob, sol = problem_and_solution(_divider(), "1 kHz")
    h = network_transfer(prob, sol, "V1", current_through("V1"), current_through("R1"))
    assert h.kind == TransferKind.CURRENT_GAIN and h.defined
    assert h.value == RationalComplex(Fraction(-1), Fraction(0))
    assert h.unit == "1"


def test_transfer_transimpedance():
    prob, sol = problem_and_solution(_divider(), "1 kHz")
    h = network_transfer(prob, sol, "V1", current_through("V1"),
                         voltage_between("out", "0"))
    assert h.kind == TransferKind.TRANSIMPEDANCE and h.unit == "Ω"
    # Zt = Vout/Iin = (20/3)/(-10/3 mA) = -2000 ohm by hand.
    assert h.value == RationalComplex(Fraction(-2000), Fraction(0))


def test_transfer_transadmittance():
    prob, sol = problem_and_solution(_divider(), "1 kHz")
    h = network_transfer(prob, sol, "V1", voltage_between("in", "0"),
                         current_through("R2"))
    assert h.kind == TransferKind.TRANSADMITTANCE and h.unit == "S"
    # Yt = I_R2/Vin = (10/3 mA)/10 = 1/3000 S by hand.
    assert h.value == RationalComplex(Fraction(1, 3000), Fraction(0))


def test_transfer_zero_input_undefined():
    prob, sol = problem_and_solution(_divider(), "1 kHz")
    # 0V source branch as current input: Iin = 0 with... use a zero-valued
    # current source branch elsewhere as the input endpoint.
    c = ckt("zi", V_("V1", "10 V", "a", "0"), I_("I1", "0 A", "a", "b"),
            R_("R1", "1 kOhm", "b", "0"))
    p2, s2 = problem_and_solution(c, "1 kHz")
    h = analyze_transfer(s2, current_through("I1"), voltage_between("b", "0"))
    assert not h.defined and h.value is None
    assert "zero input" in h.diagnostic
    # Nominating the zero source itself: it survives deactivation, its
    # current stays 0, transfer still undefined.
    hn = network_transfer(p2, s2, "I1", current_through("I1"),
                          voltage_between("b", "0"))
    assert not hn.defined and hn.basis == BASIS_NETWORK_TRANSFER


def test_transfer_network_vs_operating_distinguished():
    # V2 injects through R3 into mid without clamping it: live Vmid = 5 V
    # (operating ratio 1/2), while the network transfer (V2 shorted to
    # ground at x) gives Vmid = 10/3 V (H = 1/3). Must differ.
    c = ckt("mx", V_("V1", "10 V", "in", "0"), V_("V2", "5 V", "x", "0"),
            R_("R1", "1 kOhm", "in", "mid"), R_("R2", "1 kOhm", "mid", "0"),
            R_("R3", "1 kOhm", "x", "mid"))
    prob, sol = problem_and_solution(c, "1 kHz")
    op = analyze_transfer(sol, voltage_between("in", "0"), voltage_between("mid", "0"))
    nt = network_transfer(prob, sol, "V1", voltage_between("in", "0"),
                          voltage_between("mid", "0"))
    assert op.basis == BASIS_OPERATING_POINT_RATIO
    assert nt.basis == BASIS_NETWORK_TRANSFER
    assert op.value != nt.value
    assert op.value == RationalComplex(Fraction(1, 2), Fraction(0))
    assert nt.value == RationalComplex(Fraction(1, 3), Fraction(0))
    assert "deactivation" in nt.diagnostic and nt.input_source == "V1"


def test_transfer_orientation_and_errors():
    prob, sol = problem_and_solution(_divider(), "1 kHz")
    with pytest.raises(ImpedanceError):
        network_transfer(prob, sol, "R9", voltage_between("in", "0"),
                         voltage_between("out", "0"))
    with pytest.raises(ImpedanceError):
        network_transfer(prob, sol, "R1", voltage_between("in", "0"),
                         voltage_between("out", "0"))
    with pytest.raises(ImpedanceError):
        analyze_transfer(sol, voltage_between("nope", "0"),
                         voltage_between("out", "0"))
    h = analyze_transfer(sol, voltage_between("out", "0"), voltage_between("in", "0"))
    assert h.value == RationalComplex(Fraction(3, 2), Fraction(0))  # inverted ratio
    assert h.magnitude() == Decimal("1.5") and h.phase() == Decimal(0)


# -- D5-D sweep --------------------------------------------------------------------------------------

def _lp_circuit():
    return ckt("lp", V_("V1", "5 V", "in", "0"), R_("R1", "1 kOhm", "in", "out"),
               C_("C1", "1 uF", "out", "0"))


def _h_transfer():
    return ResponseDefinition(
        "transfer",
        (voltage_between("in", "0"), voltage_between("out", "0"), "V1"),
    )


def test_sweep_explicit_list_transfer_shape():
    sw = frequency_response(_lp_circuit(), _h_transfer(), ["100 Hz", "1 kHz", "10 kHz"])
    assert sw.status == "completed"
    assert [p.status.value for p in sw.points] == ["solved"] * 3
    mags = [p.value.magnitude() for p in sw.points]
    assert mags[0] > mags[1] > mags[2]  # low-pass roll-off, physical shape
    assert all(p.digest is not None for p in sw.points)


def test_sweep_linear_grid_definition():
    freqs = linear_frequencies("100 Hz", "1000 Hz", 4)
    assert [str(f.to_base()) for f in freqs] == ["100", "400", "700", "1000"]
    ronly = ckt("ro", V_("V1", "5 V", "a", "0"), R_("R1", "1 kOhm", "a", "0"))
    sw = frequency_response(ronly, ResponseDefinition("branch-impedance", "R1"),
                            freqs)
    assert sw.status == "completed" and len(sw.points) == 4
    for p in sw.points:
        assert p.value.value == RationalComplex(Fraction(1000), Fraction(0))
    one = frequency_response(_lp_circuit(), _h_transfer(), linear_frequencies("5 Hz", "5 Hz", 1))
    assert len(one.points) == 1 and one.status == "completed"


def test_sweep_grid_validation():
    with pytest.raises(ImpedanceError):
        linear_frequencies("1 kHz", "100 Hz", 4)  # start > stop
    with pytest.raises(ImpedanceError):
        linear_frequencies("1 Hz", "2 Hz", 0)
    with pytest.raises(ImpedanceError):
        linear_frequencies("1 Hz", "2 Hz", 1)  # n=1 needs start == stop
    with pytest.raises(ImpedanceError):
        linear_frequencies("0 Hz", "10 Hz", 3)  # f = 0 rejected
    with pytest.raises(ImpedanceError):
        linear_frequencies("-5 Hz", "10 Hz", 3)
    with pytest.raises(ImpedanceError):
        linear_frequencies("10 V", "100 V", 3)  # wrong dimension
    with pytest.raises(ImpedanceError):
        frequency_response(_lp_circuit(), _h_transfer(), [])
    with pytest.raises(ImpedanceError):
        frequency_response(_lp_circuit(), "transfer", ["1 kHz"])
    with pytest.raises(ImpedanceError):
        frequency_response(_lp_circuit(), ResponseDefinition("nope", "R1"), ["1 kHz"])


def test_sweep_partial_failure_statuses():
    # Source metadata pins "1 kHz": the 2 kHz point fails IN-BAND per
    # point (frequency-dependent INVALID), the sweep continues.
    c = Circuit("pf")
    c.add(Component("V1", "V", Q("10 V"), {"+": "n", "-": "0"},
                    {"frequency": "1 kHz"}))
    c.add(R_("R1", "1 kOhm", "n", "0"))
    sw = frequency_response(c, ResponseDefinition("branch-impedance", "R1"),
                            ["1 kHz", "2 kHz"])
    assert sw.status == "completed_with_point_failures"
    assert [p.status.value for p in sw.points] == ["solved", "invalid"]
    assert sw.points[0].value is not None and sw.points[1].value is None
    assert sw.provenance["n_failures"] == 1
    assert sw.provenance["per_point_status"] == ["solved", "invalid"]


def test_sweep_all_singular_points_recorded():
    c = ckt("sg", V_("V1", "10 V", "n", "0"), V_("V2", "10 V", "n", "0"),
            R_("R1", "1 kOhm", "n", "0"))
    sw = frequency_response(c, ResponseDefinition("branch-impedance", "R1"),
                            ["100 Hz", "1 kHz"])
    assert sw.status == "completed_with_point_failures"
    assert [p.status.value for p in sw.points] == ["singular", "singular"]
    assert all(p.value is None and p.digest is None for p in sw.points)


def test_sweep_determinism_and_digest():
    freqs = ["100 Hz", "500 Hz", "1 kHz", "5 kHz"]
    a = frequency_response(_lp_circuit(), _h_transfer(), freqs)
    b = frequency_response(_lp_circuit(), _h_transfer(), freqs)
    assert a.digest == b.digest
    assert [p.digest for p in a.points] == [p.digest for p in b.points]
    assert a.provenance["frequencies_hz"] == ["100", "500", "1000", "5000"]
    assert "timestamp" not in json.dumps(a.to_dict()).lower()
    assert len(a.digest) == 64


def test_sweep_port_and_branch_admittance():
    prob_freqs = ["500 Hz", "2 kHz"]
    sw = frequency_response(_lp_circuit(),
                            ResponseDefinition("port-admittance",
                                               PortDefinition("out", "0")),
                            prob_freqs)
    assert sw.status == "completed"
    for p in sw.points:
        assert p.value.quantity == "admittance"
        assert p.value.category == ImpedanceCategory.FINITE


def test_sweep_n_scales():
    import time as _time

    tiny = ckt("tn", V_("V1", "1 V", "n", "0"), R_("R1", "1 kOhm", "n", "0"))
    developer = ResponseDefinition("branch-impedance", "R1")
    timings = {}
    for n in (1, 2, 3, 4, 8, 16, 32, 64):
        freqs = (linear_frequencies("10 Hz", "10 Hz", 1) if n == 1
                 else linear_frequencies("10 Hz", "10 kHz", n))
        t0 = _time.time()
        sw = frequency_response(tiny, developer, freqs)
        timings[n] = _time.time() - t0
        assert sw.status == "completed" and len(sw.points) == n
        assert all(p.value.value == RationalComplex(Fraction(1000), Fraction(0))
                   for p in sw.points)
    assert timings[64] < 120, timings
    big = frequency_response(tiny, developer, linear_frequencies("10 Hz", "10 kHz", 1000))
    assert big.status == "completed" and len(big.points) == 1000
    assert big.provenance["n_points"] == 1000


# -- D5-E metamorphic ------------------------------------------------------------------------------

def test_meta_amplitude_invariance_exact():
    def build(v):
        return ckt("ma", V_("V1", f"{v} V", "in", "0"),
                   R_("R1", "1 kOhm", "in", "out"), R_("R2", "2 kOhm", "out", "0"))

    p1, s1 = problem_and_solution(build(10), "1 kHz")
    p2, s2 = problem_and_solution(build(25), "1 kHz")
    for ref in ("R1", "R2"):
        assert (branch_impedance(p1, s1, ref).value
                == branch_impedance(p2, s2, ref).value)
    assert (measure_port(p1, s1, PortDefinition("out", "0"), method="test").value
            == measure_port(p2, s2, PortDefinition("out", "0"), method="test").value)
    h1 = network_transfer(p1, s1, "V1", voltage_between("in", "0"),
                          voltage_between("out", "0"))
    h2 = network_transfer(p2, s2, "V1", voltage_between("in", "0"),
                          voltage_between("out", "0"))
    assert h1.value == h2.value == RationalComplex(Fraction(2, 3), Fraction(0))


def test_meta_amplitude_invariance_hp():
    def build(v, ph=30):
        return ckt("mah", V_("V1", f"{v} V", "in", "0", phase_=ph),
                   R_("R1", "1 kOhm", "in", "out"), C_("C1", "1 uF", "out", "0"))

    p1, s1 = problem_and_solution(build(10), "2 kHz")
    p2, s2 = problem_and_solution(build(40), "2 kHz")
    z1 = branch_impedance(p1, s1, "C1").value
    z2 = branch_impedance(p2, s2, "C1").value
    assert (z1 - z2).modulus() <= Decimal("1E-45")
    h1 = network_transfer(p1, s1, "V1", voltage_between("in", "0"),
                          voltage_between("out", "0"))
    h2 = network_transfer(p2, s2, "V1", voltage_between("in", "0"),
                          voltage_between("out", "0"))
    assert (h1.value - h2.value).modulus() <= Decimal("1E-40")


def test_meta_element_scaling():
    base = ckt("es", V_("V1", "10 V", "n", "0"), R_("R1", "1 kOhm", "n", "0"))
    scaled = ckt("es", V_("V1", "10 V", "n", "0"), R_("R1", "3 kOhm", "n", "0"))
    p1, s1 = problem_and_solution(base, "1 kHz")
    p2, s2 = problem_and_solution(scaled, "1 kHz")
    z1 = branch_impedance(p1, s1, "R1").value
    z2 = branch_impedance(p2, s2, "R1").value
    assert z2 == z1 * 3  # ZR -> kZR exactly
    assert (branch_admittance(p2, s2, "R1").value * 3
            == branch_admittance(p1, s1, "R1").value)  # YR -> YR/k
    cl = ckt("esl", V_("V1", "10 V", "n", "0"), L_("L1", "10 mH", "n", "0"))
    cl2 = ckt("esl", V_("V1", "10 V", "n", "0"), L_("L1", "30 mH", "n", "0"))
    q1, r1 = problem_and_solution(cl, "1 kHz")
    q2, r2 = problem_and_solution(cl2, "1 kHz")
    zl1 = branch_impedance(q1, r1, "L1").value
    zl2 = branch_impedance(q2, r2, "L1").value
    assert (zl2 - zl1 * 3).modulus() <= Decimal("1E-40") * zl2.modulus()
    cc = ckt("esc", V_("V1", "10 V", "n", "0"), C_("C1", "1 uF", "n", "0"))
    cc2 = ckt("esc", V_("V1", "10 V", "n", "0"), C_("C1", "4 uF", "n", "0"))
    m1, n1 = problem_and_solution(cc, "1 kHz")
    m2, n2 = problem_and_solution(cc2, "1 kHz")
    zc1 = branch_impedance(m1, n1, "C1").value
    zc2 = branch_impedance(m2, n2, "C1").value
    assert (zc2 * 4 - zc1).modulus() <= Decimal("1E-40") * zc1.modulus()


def test_meta_frequency_scaling_laws():
    def zl_at(f, l="10 mH"):
        c = ckt("fz", V_("V1", "10 V", "n", "0"), L_("L1", l, "n", "0"))
        p, s = problem_and_solution(c, f)
        return branch_impedance(p, s, "L1").value

    def zc_at(f):
        c = ckt("fzc", V_("V1", "10 V", "n", "0"), C_("C1", "1 uF", "n", "0"))
        p, s = problem_and_solution(c, f)
        return branch_impedance(p, s, "C1").value

    def zr_at(f):
        c = ckt("fzr", V_("V1", "10 V", "n", "0"), R_("R1", "1 kOhm", "n", "0"))
        p, s = problem_and_solution(c, f)
        return branch_impedance(p, s, "R1").value

    # f -> 2f: ZR unchanged (exact), ZL doubles, ZC halves (HP, tight tol).
    assert zr_at("1 kHz") == zr_at("2 kHz")
    zl1, zl2 = zl_at("1 kHz"), zl_at("2 kHz")
    assert (zl2 - zl1 * 2).modulus() <= Decimal("1E-40") * zl2.modulus()
    zc1, zc2 = zc_at("1 kHz"), zc_at("2 kHz")
    assert (zc1 - zc2 * 2).modulus() <= Decimal("1E-40") * zc1.modulus()


def test_meta_rename_permutation_conjugation():
    c1 = ckt("rn", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "out"),
             C_("C1", "1 uF", "out", "0"))
    c2 = ckt("rn", V_("V1", "10 V", "src", "0"), R_("R1", "1 kOhm", "src", "dst"),
             C_("C1", "1 uF", "dst", "0"))
    p1, s1 = problem_and_solution(c1, "1 kHz")
    p2, s2 = problem_and_solution(c2, "1 kHz")
    assert (branch_impedance(p1, s1, "R1").value
            == branch_impedance(p2, s2, "R1").value)
    c3 = ckt("rn", C_("C1", "1 uF", "out", "0"), V_("V1", "10 V", "in", "0"),
             R_("R1", "1 kOhm", "in", "out"))
    p3, s3 = problem_and_solution(c3, "1 kHz")
    assert (branch_impedance(p1, s1, "C1").value
            == branch_impedance(p3, s3, "C1").value)
    # Conjugation is algebraic only: conj(Z) identity on phasors, never
    # claimed as circuit invariance under e^(+jwt).
    z = branch_impedance(p1, s1, "C1").value
    assert (z.conjugate() - z.conjugate()).modulus() == Decimal(0)
    assert z.conjugate().re == z.re
    assert z.conjugate().im == CTX.minus(z.im)  # explicit ctx: unary - is global


# -- D5-E falsification ------------------------------------------------------------------------------

def test_falsify_open_short_undefined_ports():
    c = ckt("fs", V_("V1", "10 V", "a", "0"), I_("I1", "0 A", "a", "b"),
            R_("R1", "1 kOhm", "b", "0"))
    prob, sol = problem_and_solution(c, "1 kHz")
    # 0A source branch: V != 0, I == 0 -> INFINITE impedance...
    zi = operating_impedance(sol, "I1")
    assert zi.category == ImpedanceCategory.INFINITE and zi.value is None
    # ...FINITE ZERO admittance (dual, exact zero, not epsilon).
    yi = operating_admittance(sol, "I1")
    assert yi.category == ImpedanceCategory.FINITE
    assert yi.value == RationalComplex(Fraction(0), Fraction(0))
    # Zero-impedance port: test source across the deactivated V short.
    z0 = measure_port(prob, sol, PortDefinition("a", "0"), method="test")
    assert z0.category == ImpedanceCategory.FINITE
    assert z0.value == RationalComplex(Fraction(0), Fraction(0))


def test_falsify_singular_inconsistent_parents_raise():
    ps = solve_ac(ckt("sg", V_("V1", "10 V", "n", "0"), V_("V2", "10 V", "n", "0")),
                  "1 kHz")
    assert ps.status.value == "singular"
    prob, _ = problem_and_solution(ckt("sg0", V_("V1", "1 V", "n", "0"),
                                       R_("R1", "1 kOhm", "n", "0")), "1 kHz")
    with pytest.raises(ImpedanceError):
        branch_impedance(prob, ps, "R1")
    with pytest.raises(ImpedanceError):
        measure_port(prob, ps, PortDefinition("n", "0"))
    pi = solve_ac(ckt("ic", V_("V1", "10 V", "n", "0"), V_("V2", "5 V", "n", "0")),
                  "1 kHz")
    with pytest.raises(ImpedanceError):
        analyze_transfer(pi, voltage_between("n", "0"), voltage_between("n", "0"))


def test_falsify_floating_terminal_and_duplicates():
    from academic_core.domain.engineering.ac import FloatingCircuitError
    from academic_core.domain.engineering.circuit import CircuitError

    prob, sol = problem_and_solution(_divider(), "1 kHz")
    with pytest.raises(ImpedanceError):
        measure_port(prob, sol, PortDefinition("nope", "0"), method="test")
    c = Circuit("dup")
    c.add(V_("V1", "10 V", "a", "0"))
    with pytest.raises(CircuitError):
        c.add(V_("V1", "5 V", "b", "0"))


def test_falsify_current_only_net_is_singular():
    # A net hung only off current sources has vacuous KCL (0=0) and an
    # undetermined voltage: the parent classifies SINGULAR (correctly),
    # so D5 raises instead of analyzing numerology. Note: a SOLVED
    # parent can never yield a floating derived net (deactivation only
    # shorts V and removes I branches; a net surviving solely on removed
    # branches has vacuous KCL in the parent too), so derived-INVALID is
    # unreachable by construction; derived-INCONSISTENT (V-test against
    # a shorted source) covers the labeled-UNDEFINED path instead.
    c = ckt("dd", V_("V1", "10 V", "a", "0"), R_("R1", "1 kOhm", "a", "b"),
            I_("I1", "1 mA", "b", "c"), I_("I2", "1 mA", "c", "0"))
    assert solve_ac(c, "1 kHz").status == ACStatus.SINGULAR
    prob, _ = problem_and_solution(ckt("dd0", V_("V1", "1 V", "n", "0"),
                                       R_("R1", "1 kOhm", "n", "0")), "1 kHz")
    with pytest.raises(ImpedanceError):
        measure_port(prob, solve_ac(c, "1 kHz"), PortDefinition("a", "0"))


def test_falsify_near_zero_stays_finite():
    # 1e-30 A source: V/I is huge but FINITE — no epsilon coercion.
    c = ckt("nz", V_("V1", "10 V", "a", "0"), I_("I1", "1e-30 A", "a", "b"),
            R_("R1", "1 kOhm", "b", "0"))
    sol = solved(c, "1 kHz")
    z = operating_impedance(sol, "I1")
    assert z.category == ImpedanceCategory.FINITE
    assert z.value is not None and z.value.modulus() > Decimal("1E25")


def test_falsify_extreme_values():
    big = ckt("bg", V_("V1", "10 V", "n", "0"), R_("R1", "1e12 ohm", "n", "0"))
    p1, s1 = problem_and_solution(big, "1 kHz")
    assert branch_impedance(p1, s1, "R1").value == RationalComplex(
        Fraction(10) ** 12, Fraction(0))
    tiny = ckt("tn", V_("V1", "10 V", "n", "0"), C_("C1", "1 pF", "n", "0"))
    p2, s2 = problem_and_solution(tiny, "1 MHz")
    assert branch_impedance(p2, s2, "C1").category == ImpedanceCategory.FINITE


# -- D5-E multigraph -----------------------------------------------------------------------------------

def test_multigraph_parallel_branches_distinct():
    # Source remote from the port: V1(s,0), R1(s,n) feed, R2/R3/R4 shunt
    # at (n,0). Deactivation shorts s (not the port), so the test source
    # reads R1||R2||R3||R4 = 1/(1+1/2+1/3+1/4)k = 12k/25.
    c = ckt("mg", V_("V1", "10 V", "s", "0"), R_("R1", "1 kOhm", "s", "n"),
            R_("R2", "2 kOhm", "n", "0"), R_("R3", "3 kOhm", "n", "0"),
            R_("R4", "4 kOhm", "n", "0"))
    prob, sol = problem_and_solution(c, "1 kHz")
    assert (branch_impedance(prob, sol, "R1").value
            == RationalComplex(Fraction(1000), Fraction(0)))
    assert (branch_impedance(prob, sol, "R2").value
            == RationalComplex(Fraction(2000), Fraction(0)))
    # Direct port on a shared pair is ambiguous...
    with pytest.raises(ImpedanceError):
        measure_port(prob, sol, PortDefinition("n", "0"), method="direct")
    # ...test-source reads the parallel combination.
    t = measure_port(prob, sol, PortDefinition("n", "0"), method="test")
    assert t.value == RationalComplex(Fraction(12000, 25), Fraction(0))


def test_multigraph_parallel_rlc_admittance_sums():
    c = ckt("mrlc", V_("V1", "5 V", "s", "0"), R_("R1", "1 kOhm", "s", "n"),
            L_("L1", "10 mH", "n", "0"), C_("C1", "1 uF", "n", "0"))
    prob, sol = problem_and_solution(c, "1000 Hz")
    y = measure_port(prob, sol, PortDefinition("n", "0"), quantity="admittance",
                     method="test")
    parts = [branch_admittance(prob, sol, r).value for r in ("R1", "L1", "C1")]
    expect = parts[0] + parts[1] + parts[2]
    assert (y.value - expect).modulus() <= Decimal("1E-40")


def test_multigraph_parallel_sources():
    c = ckt("ms", I_("I1", "1 mA", "n", "0"), I_("I2", "2 mA", "n", "0"),
            R_("R1", "1 kOhm", "n", "0"))
    prob, sol = problem_and_solution(c, "1 kHz")
    assert sol.status == ACStatus.SOLVED
    # Each source branch keeps its own identity and current.
    assert sol.current_of("I1") == RationalComplex(Fraction(-1, 1000), Fraction(0))
    assert sol.current_of("I2") == RationalComplex(Fraction(-1, 500), Fraction(0))


# -- D5-E topologies -------------------------------------------------------------------------------------

def test_topo_series_sum_oracle():
    # Current-source parent (I deactivates to OPEN, no shorts): port
    # (s,0) test sees exactly the series chain R+L+C to ground.
    # Zeq = 100 + j(wL-1/wC), w-terms from PI50 here.
    wl = CTX.multiply(CTX.multiply(CTX.multiply(Decimal(2), PI50), Decimal(1000)),
                      Decimal("0.01"))
    xc = CTX.divide(Decimal(1), CTX.multiply(
        CTX.multiply(CTX.multiply(Decimal(2), PI50), Decimal(1000)),
        Decimal("0.000001")))
    c = ckt("se", I_("I1", "1 A", "s", "0"), R_("R1", "100 ohm", "s", "a"),
            L_("L1", "10 mH", "a", "b"), C_("C1", "1 uF", "b", "0"))
    prob, sol = problem_and_solution(c, "1000 Hz")
    t = measure_port(prob, sol, PortDefinition("s", "0"), method="test")
    assert abs(CTX.subtract(t.value.re, Decimal(100))) <= Decimal("1E-40")
    assert abs(CTX.subtract(t.value.im, CTX.subtract(wl, xc))) <= Decimal("1E-38")


def test_topo_divider_transfer_bridge():
    c = ckt("br", V_("V1", "10 V", "t", "0"), R_("R1", "1 kOhm", "t", "a"),
            R_("R2", "2 kOhm", "t", "b"), R_("R3", "1 kOhm", "a", "0"),
            R_("R4", "3 kOhm", "b", "0"), R_("R5", "1 kOhm", "a", "b"))
    prob, sol = problem_and_solution(c, "1 kHz")
    h = network_transfer(prob, sol, "V1", voltage_between("t", "0"),
                         voltage_between("a", "b"))
    # Hand nodal on the unbalanced bridge (R4 = 3k): 3Va - Vb = 10 and
    # -6Va + 11Vb = 30 (mA/kohm units) -> Va = 140/27, Vb = 50/9.
    va = sol.voltage_of("a")
    vb = sol.voltage_of("b")
    assert va - vb == RationalComplex(Fraction(-10, 27), Fraction(0))
    # ...and the transfer divides once more by Vin = 10 V.
    assert h.value == RationalComplex(Fraction(-1, 27), Fraction(0))


def test_topo_ladder_port():
    comps = [V_("V1", "12 V", "n0", "0")]
    for k in range(4):
        comps.append(R_(f"R{k + 1}", "1 kOhm", f"n{k}", f"n{k + 1}"))
        comps.append(C_(f"C{k + 1}", "100 nF", f"n{k + 1}", "0"))
    c = ckt("lad", *comps)
    prob, sol = problem_and_solution(c, "1 kHz")
    t = measure_port(prob, sol, PortDefinition("n2", "0"), method="test")
    assert t.category == ImpedanceCategory.FINITE and t.value is not None
    h = network_transfer(prob, sol, "V1", voltage_between("n0", "0"),
                         voltage_between("n4", "0"))
    assert h.defined and h.value is not None


def test_topo_mesh_star_k33():
    mesh = ckt("msh", V_("V1", "10 V", "a", "0"), R_("R1", "1 kOhm", "a", "b"),
               R_("R2", "1 kOhm", "b", "c"), R_("R3", "1 kOhm", "c", "a"),
               R_("R4", "1 kOhm", "b", "0"), L_("L1", "5 mH", "c", "0"))
    p1, s1 = problem_and_solution(mesh, "2 kHz")
    assert measure_port(p1, s1, PortDefinition("a", "c"), method="test").category \
        == ImpedanceCategory.FINITE
    star = ckt("str", V_("V1", "5 V", "ctr", "0"),
               *[R_(f"R{k + 1}", "1 kOhm", "ctr", f"e{k}") for k in range(6)],
               *[R_(f"R{k + 7}", "2 kOhm", f"e{k}", "0") for k in range(6)])
    p2, s2 = problem_and_solution(star, "1 kHz")
    assert measure_port(p2, s2, PortDefinition("ctr", "0"), method="test").category \
        == ImpedanceCategory.FINITE
    kcomps = [V_("V1", "10 V", "a", "0")]
    k = 1
    for u in ("a", "b", "c"):
        for v in ("x", "y", "z"):
            kcomps.append(R_(f"R{k}", "1 kOhm", u, v))
            k += 1
    kcomps += [R_("R10", "1 kOhm", "b", "0"), R_("R11", "1 kOhm", "c", "0"),
               R_("R12", "1 kOhm", "x", "0"), R_("R13", "1 kOhm", "y", "0"),
               R_("R14", "1 kOhm", "z", "0")]
    k33 = ckt("k33", *kcomps)
    p3, s3 = problem_and_solution(k33, "1 kHz")
    assert p3 is not None and s3.status == ACStatus.SOLVED
    assert measure_port(p3, s3, PortDefinition("a", "x"), method="test").category \
        == ImpedanceCategory.FINITE


# -- D5-E generality ---------------------------------------------------------------------------------------

def _seeded_r_circuit(seed: int, n: int):
    import random as _random

    rng = _random.Random(seed)
    nets = ["0"] + [f"n{i}" for i in range(n)]
    comps = [V_("V1", "10 V", nets[1], "0")]
    ref = 1
    for _ in range(2 * n):
        a, b = rng.sample(nets, 2)
        ref += 1
        comps.append(R_(f"R{ref}", f"{rng.choice([1, 2, 3, 4])} kOhm", a, b))
    for i in range(2, n + 1):
        ref += 1
        comps.append(R_(f"R{ref}", "5 kOhm", nets[i], "0"))
    return ckt(f"g{n}", *comps)


def test_generality_seeded_r_networks():
    # Passive-linear identity: operating ratio == constitutive Z for
    # every R branch (V = ZI exactly), over seeded random topologies.
    for n in (1, 2, 4, 8, 16, 32, 64):
        prob, sol = problem_and_solution(_seeded_r_circuit(1234, n), "1 kHz")
        checked = 0
        for br in prob.branches:
            if br.type != "R":
                continue
            zc = branch_impedance(prob, sol, br.ref).value
            assert zc * br.admittance == RationalComplex(Fraction(1), Fraction(0))
            zo = operating_impedance(sol, br.ref)
            if zo.category == ImpedanceCategory.FINITE:
                assert zc == zo.value, (n, br.ref)  # V = ZI: ratio == property
                checked += 1
            else:
                assert zo.category == ImpedanceCategory.UNDEFINED  # exact 0/0
        assert checked > 0, n


def test_generality_ladder_ports():
    for n in (1, 2, 4, 8, 16, 32, 64):
        comps = [V_("V1", "12 V", "n0", "0")]
        for k in range(n):
            comps.append(R_(f"R{k + 1}", "1 kOhm", f"n{k}", f"n{k + 1}"))
            comps.append(C_(f"C{k + 1}", "100 nF", f"n{k + 1}", "0"))
        c = ckt(f"gl{n}", *comps)
        prob, sol = problem_and_solution(c, "1 kHz")
        t = measure_port(prob, sol, PortDefinition(f"n{n}", "0"), method="test")
        assert t.category == ImpedanceCategory.FINITE, n


# -- D5-E immutability / idempotence -------------------------------------------------------------------

def test_immutability_across_all_operations():
    c = _divider()
    before_net = c.to_netlist()
    before_params = {e.ref: (dict(e.parameters), str(e.value)) for e in c.components}
    n_before = len(c.components)
    prob, sol = problem_and_solution(c, "1 kHz")
    before_sol = json.dumps(sol.to_dict(), sort_keys=True)
    branch_impedance(prob, sol, "R1")
    measure_port(prob, sol, PortDefinition("in", "out"), method="test")
    network_transfer(prob, sol, "V1", voltage_between("in", "0"),
                     voltage_between("out", "0"))
    frequency_response(c, ResponseDefinition("branch-impedance", "R1"), ["1 kHz"])
    assert c.to_netlist() == before_net
    assert {e.ref: (dict(e.parameters), str(e.value)) for e in c.components} == before_params
    assert len(c.components) == n_before  # no test source accumulated
    assert json.dumps(sol.to_dict(), sort_keys=True) == before_sol


def test_idempotence_repeated_measurement():
    prob, sol = problem_and_solution(_divider(), "1 kHz")
    first = measure_port(prob, sol, PortDefinition("out", "0"), method="test")
    for _ in range(5):
        rep = measure_port(prob, sol, PortDefinition("out", "0"), method="test")
        assert rep.to_dict() == first.to_dict()
    h1 = network_transfer(prob, sol, "V1", voltage_between("in", "0"),
                          voltage_between("out", "0"))
    h2 = network_transfer(prob, sol, "V1", voltage_between("in", "0"),
                          voltage_between("out", "0"))
    assert h1.to_dict() == h2.to_dict()


# -- D5-E provenance ------------------------------------------------------------------------------------------------------

def test_provenance_transfer_and_port():
    prob, sol = problem_and_solution(_divider(), "1 kHz")
    h = network_transfer(prob, sol, "V1", voltage_between("in", "0"),
                         voltage_between("out", "0"))
    d = h.to_dict()
    assert d["kind"] == "voltage_gain" and d["basis"] == BASIS_NETWORK_TRANSFER
    assert d["input_source"] == "V1" and d["defined"] is True
    assert d["input"] == {"kind": "voltage", "A": "in", "B": "0", "branch": ""}
    z = measure_port(prob, sol, PortDefinition("out", "0"), method="test")
    assert "test current" in z.diagnostic and "deactivation" in z.diagnostic


def test_provenance_sweep_keys():
    sw = frequency_response(_divider(), _h_transfer_div(), ["100 Hz", "1 kHz"])
    assert sw.provenance["engine"] == "f8d-ac-response/1.0"
    assert sw.provenance["definition"]["kind"] == "transfer"
    assert sw.provenance["n_points"] == 2 and sw.provenance["n_failures"] == 0
    assert sw.provenance["temporal_convention"] == "e^(+jwt)"
    assert sw.provenance["amplitude_convention"] == "peak"


def _h_transfer_div():
    return ResponseDefinition(
        "transfer", (voltage_between("in", "0"), voltage_between("out", "0"), "V1"))


# -- D5-E security -----------------------------------------------------------------------------------------------------------------

AC_DIR = pathlib.Path(__file__).resolve().parents[1] / "src" / "academic_core" / "domain" / "engineering" / "ac"


def test_security_no_dangerous_calls_or_deps():
    forbidden_calls = {"eval", "exec", "compile", "__import__", "open", "input",
                       "breakpoint"}
    forbidden_roots = {"os", "sys", "pathlib", "sqlite3", "urllib", "socket",
                       "http", "ftplib", "subprocess", "pickle", "marshal",
                       "ctypes", "PySide6", "numpy", "scipy", "math", "cmath",
                       "requests"}
    for name in ("impedance.py", "response.py"):
        tree = ast.parse((AC_DIR / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_calls, (name, node.func.id)
            if isinstance(node, ast.Import):
                for al in node.names:
                    assert al.name.split(".")[0] not in forbidden_roots, (name, al.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden_roots, (name, node.module)
                assert not node.module.startswith("academic_core.infrastructure")


def test_security_no_float_complex_math_names():
    import json as _json  # local alias only; module under test untouched
    assert _json is not None
    for name in ("impedance.py", "response.py"):
        tree = ast.parse((AC_DIR / name).read_text(encoding="utf-8"))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        assert "float" not in names, name
        assert "complex" not in names, name
        assert "math" not in names and "cmath" not in names, name


# -- D5-E performance -----------------------------------------------------------------------------------------------------------------

def test_performance_single_and_sweep():
    import time as _time

    c = _rc_lowpass()
    pdef = ResponseDefinition(
        "transfer", (voltage_between("in", "0"), voltage_between("out", "0"), "V1"))
    t0 = _time.time()
    once = frequency_response(c, pdef, ["1 kHz"])
    t_single = _time.time() - t0
    assert once.status == "completed"
    t0 = _time.time()
    ten = frequency_response(c, pdef, linear_frequencies("100 Hz", "10 kHz", 10))
    t_ten = _time.time() - t0
    assert ten.status == "completed"
    t0 = _time.time()
    hund = frequency_response(c, pdef, linear_frequencies("100 Hz", "10 kHz", 100))
    t_hund = _time.time() - t0
    assert hund.status == "completed"
    # Documented cost shape (linear in N, no caching claimed); loose caps.
    assert t_single < 30 and t_ten < 60 and t_hund < 300, (t_single, t_ten, t_hund)
    print(f"\nD5 perf: single={t_single:.2f}s ten={t_ten:.2f}s hundred={t_hund:.2f}s")


# -- D5-E ngspice oracle -------------------------------------------------------------------------------------

def _ng_backend():
    from academic_core.infrastructure.ngspice import NgSpiceBackend

    b = NgSpiceBackend()
    return b if b.detect().verified else None


NG = _ng_backend()


def _spice_netlist(circuit):
    lines = [f"* D5 oracle {circuit.name}"]
    for e in sorted(circuit.components, key=lambda x: x.ref.upper()):
        t = e.type.upper()
        pins = " ".join(e.pins[p] for p in
                        (("1", "2") if t in ("R", "L", "C") else ("+", "-")))
        if t == "V":
            ph = e.parameters.get("phase", 0)
            unit = str(e.parameters.get("phase_unit", "deg")).lower()
            ph_d = Decimal(str(ph))
            deg = ph_d if unit == "deg" else ph_d * Decimal("57.295779513082320876798154814105")
            lines.append(f"{e.ref.upper()} {pins} dc 0 ac {format(e.value.to_base(), 'f')} {deg}")
        elif t == "I":
            # NOTE: ngspice current sources flow +->- through the source
            # while D5 delivers INTO + (opposite reference). Decks using
            # this helper with I sources are compared on node VOLTAGES
            # only (direction-free), never on branch currents.
            ph = e.parameters.get("phase", 0)
            unit = str(e.parameters.get("phase_unit", "deg")).lower()
            ph_d = Decimal(str(ph))
            deg = ph_d if unit == "deg" else ph_d * Decimal("57.295779513082320876798154814105")
            lines.append(f"{e.ref.upper()} {pins} dc 0 ac {format(e.value.to_base(), 'f')} {deg}")
        elif t in ("R", "L", "C"):
            lines.append(f"{e.ref.upper()} {pins} {format(e.value.to_base(), 'f')}")
        else:
            raise AssertionError("oracle netlists use V/I+R/L/C only")
    lines.append(".end")
    return "\n".join(lines) + "\n"


def _oracle(circuit, freq_hz):
    from academic_core.domain.engineering.simulation import ACAnalysis

    assert NG is not None
    ac = ACAnalysis(sweep_type="lin", points=2, fstart=str(freq_hz),
                    fstop=str(int(freq_hz) + 1))
    res = NG.simulate(_spice_netlist(circuit), analyses=(ac,))
    assert res.status == "COMPLETED"
    return res


def _oracle_voltages_only(deck, freq_hz, nodes):
    """Oracle run with an explicit voltage-only .print card.

    Required whenever the deck contains current sources: the auto-deck
    would request unprintable i() branch vectors and poison table
    parsing (established D3/D4 harness limit). Voltages are unambiguous.
    """
    from academic_core.domain.engineering.simulation import ACAnalysis

    assert NG is not None
    body = deck.replace(".end", "")
    body += ".print ac " + " ".join(f"v({n})" for n in nodes) + "\n.end\n"
    ac = ACAnalysis(sweep_type="lin", points=2, fstart=str(freq_hz),
                    fstop=str(int(freq_hz) + 1))
    res = NG.simulate(body, analyses=(ac,))
    assert res.status == "COMPLETED"
    return {n: res.sample_complex_at(f"v({n})", str(freq_hz)) for n in nodes}


def _wrap_deg(d):
    import math as _math

    while d > 180.0:
        d -= 360.0
    while d <= -180.0:
        d += 360.0
    return d


def _check_transfer(got, ref_c, tol_mag=0.01, tol_ph=1.0):
    import math as _math

    mag = abs(ref_c)
    ang = _math.degrees(_math.atan2(ref_c.imag, ref_c.real)) if mag > 0 else 0.0
    assert abs(float(got.magnitude()) - mag) <= tol_mag * max(1.0, mag)
    if mag > 1e-9:
        assert abs(_wrap_deg(float(got.phase()) * 57.29577951308232 - ang)) <= tol_ph


def _check_z(got_re_im, ref_c, tol=0.01):
    assert abs(got_re_im[0] - ref_c.real) <= tol * max(1.0, abs(ref_c.real))
    assert abs(got_re_im[1] - ref_c.imag) <= tol * max(1.0, abs(ref_c.imag))


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_r_branch():
    c = ckt("or", V_("V1", "10 V", "n", "0"), R_("R1", "1 kOhm", "n", "0"))
    prob, sol = problem_and_solution(c, "1000 Hz")
    res = _oracle(c, 1000)
    i = res.sample_complex_at("i(v1)", "1000")
    v = res.sample_complex_at("v(n)", "1000")
    # KCL at n: branch current (n->0) is the negation of the source
    # current (ngspice reports the +->- through-source direction).
    ibranch = complex(-i.real, -i.imag)
    z = branch_impedance(prob, sol, "R1").value
    _check_z((float(z.re), float(z.im)), complex(v.real, v.imag) / ibranch)
    assert abs(float(z.re) - 1000.0) <= 5.0 and abs(float(z.im)) <= 2.0


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_rc_gain_and_zin():
    # Source remote from the port (V at s, port at in): deactivation
    # shorts s, not the port, so Zin is nontrivial. A port coinciding
    # with a (deactivated) voltage source would read the short (0).
    c = ckt("orz", V_("V1", "5 V", "s", "0"), R_("R0", "100 ohm", "s", "in"),
            R_("R1", "1 kOhm", "in", "out"), C_("C1", "1 uF", "out", "0"))
    prob, sol = problem_and_solution(c, "1000 Hz")
    res = _oracle(c, 1000)
    vo = res.sample_complex_at("v(out)", "1000")
    vin = res.sample_complex_at("v(in)", "1000")
    vs = res.sample_complex_at("v(s)", "1000")
    h = network_transfer(prob, sol, "V1", voltage_between("s", "0"),
                         voltage_between("out", "0"))
    _check_transfer(h, vo / vs)
    # Zin oracle on the DEACTIVATED network (a live-circuit KCL current
    # is not a port current): mirror deactivation + 1A injection in SPICE.
    # Terminals swapped per the empirical I-direction mapping (ngspice
    # flows +->- through the source, D5 delivers INTO +).
    deck = ("* zin derived oracle\n"
            "V1 s 0 dc 0\n"
            "R0 s in 100\n"
            "R1 in out 1000\n"
            "C1 out 0 1e-6\n"
            "Itest 0 in dc 0 ac 1\n"
            ".end\n")
    got = _oracle_voltages_only(deck, 1000, ("in",))
    assert got["in"] is not None
    zin = measure_port(prob, sol, PortDefinition("in", "0"), method="test")
    assert abs(float(zin.value.re) - got["in"].real) <= 1.0
    assert abs(float(zin.value.im) - got["in"].imag) <= 1.0


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_rl_branch():
    c = ckt("orl", V_("V1", "10 V", "in", "0"), R_("R1", "100 ohm", "in", "a"),
            L_("L1", "10 mH", "a", "0"))
    prob, sol = problem_and_solution(c, "1000 Hz")
    res = _oracle(c, 1000)
    i = res.sample_complex_at("i(v1)", "1000")
    va = res.sample_complex_at("v(a)", "1000")
    # Series path: every branch current equals -i(v1) by KCL (source
    # current leaves the series nodes through the +->- convention).
    ib = complex(-i.real, -i.imag)
    _check_z((float(branch_impedance(prob, sol, "L1").value.re),
              float(branch_impedance(prob, sol, "L1").value.im)), va / ib, tol=0.02)
    vin = res.sample_complex_at("v(in)", "1000")
    _check_z((float(branch_impedance(prob, sol, "R1").value.re),
              float(branch_impedance(prob, sol, "R1").value.im)),
             (vin - va) / ib, tol=0.02)


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_rlc_gain():
    c = ckt("orlc", V_("V1", "10 V", "in", "0"), R_("R1", "100 ohm", "in", "a"),
            L_("L1", "10 mH", "a", "b"), C_("C1", "1 uF", "b", "0"))
    prob, sol = problem_and_solution(c, "1000 Hz")
    res = _oracle(c, 1000)
    h = network_transfer(prob, sol, "V1", voltage_between("in", "0"),
                         voltage_between("b", "0"))
    _check_transfer(h, res.sample_complex_at("v(b)", "1000")
                    / res.sample_complex_at("v(in)", "1000"))


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_divider_gain():
    prob, sol = problem_and_solution(_divider(), "500 Hz")
    res = _oracle(_divider(), 500)
    h = network_transfer(prob, sol, "V1", voltage_between("in", "0"),
                         voltage_between("out", "0"))
    _check_transfer(h, res.sample_complex_at("v(out)", "500")
                    / res.sample_complex_at("v(in)", "500"),
                    tol_mag=0.002, tol_ph=0.2)


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_bridge_gain():
    c = ckt("obr", V_("V1", "10 V", "t", "0"), R_("R1", "1 kOhm", "t", "a"),
            R_("R2", "2 kOhm", "t", "b"), R_("R3", "1 kOhm", "a", "0"),
            R_("R4", "3 kOhm", "b", "0"), R_("R5", "1 kOhm", "a", "b"))
    prob, sol = problem_and_solution(c, "500 Hz")
    res = _oracle(c, 500)
    va = res.sample_complex_at("v(a)", "500")
    vb = res.sample_complex_at("v(b)", "500")
    vin = res.sample_complex_at("v(t)", "500")
    h = network_transfer(prob, sol, "V1", voltage_between("t", "0"),
                         voltage_between("a", "b"))
    _check_transfer(h, (va - vb) / vin, tol_mag=0.002, tol_ph=0.2)


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_arbitrary_port_derived_deck():
    # The test-source METHOD itself, validated independently: mirror the
    # deactivation + 1A injection textually in SPICE and let ngspice solve
    # the derived circuit. D5 functions stay out of the oracle path.
    # Empirical mapping (probed 2026): ngspice current sources flow +->
    # - through the source while D5 test sources deliver INTO +; the deck
    # below swaps Itest terminals so both excitations coincide physically.
    deck = ("* derived port oracle\n"
            "V1 in 0 dc 0\n"
            "R1 in out 1000\n"
            "R2 out 0 2000\n"
            "Itest out in dc 0 ac 1\n"
            ".end\n")
    got = _oracle_voltages_only(deck, 1000, ("in", "out"))
    assert got["in"] is not None and got["out"] is not None
    prob, sol = problem_and_solution(_divider(), "1 kHz")
    t = measure_port(prob, sol, PortDefinition("in", "out"), method="test")
    # Port (in,out): Vport = Vin - Vout on both sides.
    ref = got["in"] - got["out"]
    assert abs(float(t.value.re) - ref.real) <= 2.0
    assert abs(float(t.value.im) - ref.imag) <= 2.0


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_nongnd_port():
    c = ckt("onp", V_("V1", "10 V", "t", "0"), R_("R1", "1 kOhm", "t", "a"),
            R_("R2", "2 kOhm", "t", "b"), R_("R3", "1 kOhm", "a", "0"),
            R_("R4", "3 kOhm", "b", "0"), R_("R5", "1 kOhm", "a", "b"))
    prob, sol = problem_and_solution(c, "500 Hz")
    res = _oracle(c, 500)
    va = res.sample_complex_at("v(a)", "500")
    vb = res.sample_complex_at("v(b)", "500")
    d = measure_port(prob, sol, PortDefinition("a", "b"), method="direct")
    assert d.category == ImpedanceCategory.FINITE
    # Differential port voltage agrees on both sides (branch R5 value).
    vbr = next(b.voltage for b in sol.branch_voltages if b.ref == "R5")
    assert abs(float(vbr.re) - (va.real - vb.real)) <= 0.02
    assert abs(float(vbr.im) - (va.imag - vb.imag)) <= 0.02
    assert abs(float(sol.voltage_of("a").re) - va.real) <= 0.02
    assert abs(float(sol.voltage_of("b").re) - vb.real) <= 0.02


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_current_source_nodes():
    # I-source branches are unprintable: voltage-only deck (auto-deck
    # i() vectors would poison parsing), node voltages compared.
    # Empirical mapping (probed twice: derived-deck port test + here):
    # ngspice current sources flow +->- through the source while D3
    # delivers INTO + (opposite reference), so oracle voltages negate.
    c = ckt("ocs", I_("I1", "2 mA", "n", "0"), R_("R1", "1 kOhm", "n", "0"))
    prob, sol = problem_and_solution(c, "1000 Hz")
    got = _oracle_voltages_only(_spice_netlist(c), 1000, ("n",))
    v = got["n"]
    assert v is not None
    assert abs(float(sol.voltage_of("n").re) + v.real) <= 0.01
    assert sol.voltage_of("n") == RationalComplex(Fraction(2), Fraction(0))


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_multi_source_nodes():
    c = ckt("oms", V_("V1", "10 V", "a", "0", phase_=30),
            V_("V2", "5 V", "b", "0", phase_=-45),
            R_("R1", "1 kOhm", "a", "b"), R_("R2", "2 kOhm", "b", "0"))
    prob, sol = problem_and_solution(c, "1000 Hz")
    res = _oracle(c, 1000)
    for node in ("a", "b"):
        v = res.sample_complex_at(f"v({node})", "1000")
        got = sol.voltage_of(node)
        assert abs(float(got.re) - v.real) <= 0.01 * max(1.0, abs(v.real))
        assert abs(float(got.im) - v.imag) <= 0.01 * max(1.0, abs(v.imag))


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_sweep_gain():
    # One exact single-frequency oracle run per point: the sampler
    # nearest-matches, so multi-point decks would compare misaligned
    # frequencies (established failure mode, avoided by construction).
    c = _rc_lowpass()
    freqs = ["100", "500", "1000", "5000", "10000"]
    defn = ResponseDefinition(
        "transfer", (voltage_between("in", "0"), voltage_between("out", "0"), "V1"))
    sw = frequency_response(c, defn, [f + " Hz" for f in freqs])
    assert sw.status == "completed"
    for p, f in zip(sw.points, freqs):
        res = _oracle(c, int(f))
        o = res.sample_complex_at("v(out)", f)
        i = res.sample_complex_at("v(in)", f)
        _check_transfer(p.value, o / i, tol_mag=0.01, tol_ph=1.0)


# -- D5-E independent benchmarks ---------------------------------------------------------------------------------

def test_bench_cramer2x2_port():
    # Divider port (out,0) network impedance by hand Cramer (Fractions,
    # no D5 functions): deactivated nodal (out): (V-0)/2k + (V-0)/1k... the
    # test-source KCL at out with 1A in: V(1/2k+1/1k) = 1A(mA units)...
    # 1A = 1000 mA: V(1/2 + 1)/1k... V*3/2 = 1000*1k mV? do it cleanly:
    # Vout[kV? no: V * (1/2000 + 1/1000) = 1 -> V = 2000/3 V.
    prob, sol = problem_and_solution(_divider(), "1 kHz")
    t = measure_port(prob, sol, PortDefinition("out", "0"), method="test")
    det = Fraction(1, 2000) + Fraction(1, 1000)
    assert t.value == RationalComplex(Fraction(1) / det, Fraction(0))


def test_bench_cramer3x3_port():
    # 3-node ladder port by hand 3x3 Cramer with Fractions (independent).
    c = ckt("c3", V_("V1", "10 V", "n0", "0"), R_("R1", "1 kOhm", "n0", "n1"),
            R_("R2", "1 kOhm", "n1", "n2"), R_("R3", "1 kOhm", "n2", "0"))
    prob, sol = problem_and_solution(c, "1 kHz")
    t = measure_port(prob, sol, PortDefinition("n1", "0"), method="test")
    # Deactivated (n0 shorted): from (n1,0): R1-to-short || (R2+R3).
    expect = Fraction(1, 1) / (Fraction(1, 1000) + Fraction(1, 2000))
    assert t.value == RationalComplex(expect, Fraction(0))


def test_bench_rc_rlc_closed_forms():
    wl = CTX.multiply(CTX.multiply(CTX.multiply(Decimal(2), PI50), Decimal(1000)),
                      Decimal("0.01"))
    c = ckt("brl", V_("V1", "10 V", "n", "0"), R_("R1", "100 ohm", "n", "a"),
            L_("L1", "10 mH", "a", "0"))
    p1, s1 = problem_and_solution(c, "1000 Hz")
    h = network_transfer(p1, s1, "V1", current_through("V1"), current_through("R1"))
    # Series path: same current up to MNA sign; |Hi| = 1, angle 0... the
    # through-current equals the source current up to orientation.
    assert h.defined and abs(float(h.magnitude()) - 1.0) <= 1e-6
    c2 = ckt("brc", V_("V1", "5 V", "in", "0", phase_=45),
             R_("R1", "1 kOhm", "in", "out"), C_("C1", "1 uF", "out", "0"))
    p2, s2 = problem_and_solution(c2, "1000 Hz")
    h2 = network_transfer(p2, s2, "V1", voltage_between("in", "0"),
                          voltage_between("out", "0"))
    wrc = CTX.multiply(CTX.multiply(CTX.multiply(Decimal(2), PI50), Decimal(1000)),
                       CTX.multiply(Decimal(1000), Decimal("0.000001")))
    den = CTX.add(Decimal(1), CTX.multiply(wrc, wrc))
    assert abs(CTX.subtract(h2.magnitude(),
                            CTX.sqrt(CTX.divide(Decimal(1), den)))) <= Decimal("1E-40")


# -- D5-E historical hardening -----------------------------------------------------------------------------------

def test_hardening_f6_units_exactness():
    from academic_core.domain.engineering.units import UnitError

    assert parse_quantity("2 S").to_base() == Decimal(2)
    with pytest.raises(UnitError):
        parse_quantity("5 XX")
    with pytest.raises(UnitError):
        parse_quantity("5 dBm")  # no invented fallback units
    from academic_core.domain.engineering.units import Quantity

    with pytest.raises(Exception):
        parse_quantity("5 V") + parse_quantity("2 A")


def test_hardening_f8b_ground_multigraph_orientation():
    g0 = ckt("g0", V_("V1", "10 V", "a", "GND"), R_("R1", "1 kOhm", "a", "GND"))
    p0, s0 = problem_and_solution(g0, "1 kHz")
    assert p0.ground == "GND"
    assert branch_impedance(p0, s0, "R1").value == RationalComplex(
        Fraction(1000), Fraction(0))


def test_hardening_f8c_coexistence_thevenin():
    from academic_core.domain.engineering.thevenin import (
        TheveninPort,
        analyze_thevenin,
    )

    c = _divider()
    th = analyze_thevenin(c, TheveninPort("out", "0"))
    assert str(th.status) == "EquivalentStatus.VERIFIED"
    assert th.r_th.value == Decimal(2000) / Decimal(3)
    assert th.v_th.value == Decimal(20) / Decimal(3)
    prob, sol = problem_and_solution(c, "1 kHz")
    t = measure_port(prob, sol, PortDefinition("out", "0"), method="test")
    # D5 network impedance == F8-C Thevenin resistance (independent engines):
    # D5 is exact here, thevenin is 28-digit Decimal — compare loosely.
    assert t.value == RationalComplex(Fraction(2000, 3), Fraction(0))
    assert abs(th.r_th.value - Decimal(2000) / Decimal(3)) <= Decimal("1E-24")
    th_swap = analyze_thevenin(c, TheveninPort("0", "out"))
    assert th_swap.r_th.value == th.r_th.value
    assert th_swap.v_th.value == -th.v_th.value  # A/B polarity flips voltage


def test_hardening_d1_atan2_phase_edges():
    prob, sol = problem_and_solution(_divider(), "1 kHz")
    h = network_transfer(prob, sol, "V1", current_through("V1"),
                         current_through("V1"))
    assert h.value == RationalComplex(Fraction(1), Fraction(0))
    assert h.phase() == Decimal(0)
    hi = network_transfer(prob, sol, "V1", current_through("V1"),
                          current_through("R1"))
    assert hi.value == RationalComplex(Fraction(-1), Fraction(0))
    assert hi.phase() == decimal_pi_value()  # -1 maps to +pi, D1 convention
    assert hi.phase().is_finite()


def test_hardening_d2_statuses_propagate():
    from academic_core.domain.engineering.math.linsolve import SolveStatus

    assert SolveStatus.SOLVED.value == "solved"
    prob, _ = problem_and_solution(_divider(), "1 kHz")
    unc = solve_ac(ckt("uc", V_("V1", "10 V", "n", "0"), V_("V2", "5 V", "n", "0")),
                   "1 kHz")
    assert unc.status.value == "inconsistent"
    with pytest.raises(ImpedanceError):
        measure_port(prob, unc, PortDefinition("n", "0"))


def test_hardening_d3_conventions_peak_signs():
    prob, sol = problem_and_solution(
        ckt("hc", V_("V1", "10 V", "n", "0"), L_("L1", "10 mH", "n", "0")), "1 kHz")
    assert sol.voltage_of("n").modulus() == Decimal(10)  # peak preserved
    zl = branch_impedance(prob, sol, "L1").value
    assert zl.im > 0  # e^(+jwt): inductive reactance positive
    i = sol.current_of("V1")
    # Source delivers vars to the inductor: I_V = +j|I| (absorbed Q<0
    # in D4 terms), real part HP noise only.
    assert i.im > 0 and abs(i.re) <= Decimal("1E-40") * abs(i.im)


def test_hardening_d4_power_untouched():
    from academic_core.domain.engineering.ac import analyze_power

    sol = solved(_divider(), "1 kHz")
    pa = analyze_power(sol)
    assert pa.power_of("R1").active == RationalComplex(Fraction(1, 180), Fraction(0))
    assert pa.conservation.passed


def test_hardening_f8a_abstention_not_failure():
    # UNDEFINED (source constitutive) on a SOLVED parent: not-applicable
    # is reported as data, never raised, never a failure status.
    prob, sol = problem_and_solution(_divider(), "1 kHz")
    z = branch_impedance(prob, sol, "V1")
    assert z.category == ImpedanceCategory.UNDEFINED
    assert sol.status == ACStatus.SOLVED


# -- D5-E phase wrap -----------------------------------------------------------------------------------------------

def _wrap_diff(a_deg: Decimal, b_deg: Decimal) -> Decimal:
    from decimal import ROUND_HALF_UP as _R

    d = CTX.subtract(a_deg, b_deg)
    turns = (d / Decimal(360)).to_integral_value(rounding=_R)
    return CTX.subtract(d, CTX.multiply(Decimal(360), turns))


def test_phase_wrap_helper_and_edges():
    assert _wrap_diff(Decimal(179), Decimal(-181)) == Decimal(0)
    assert _wrap_diff(Decimal(-179), Decimal(181)) == Decimal(0)
    assert _wrap_diff(Decimal(10), Decimal(350)) == Decimal(20)
    c = ckt("pw", V_("V1", "5 V", "in", "0", phase_=45),
            R_("R1", "1 kOhm", "in", "out"), C_("C1", "1 uF", "out", "0"))
    prob, sol = problem_and_solution(c, "1000 Hz")
    h = network_transfer(prob, sol, "V1", voltage_between("in", "0"),
                         voltage_between("out", "0"))
    deg = CTX.multiply(h.phase(), CTX.divide(Decimal(180), decimal_pi_value()))
    assert Decimal(-90) < deg < Decimal(0)  # 4th quadrant, wrapped range
    assert h.phase() > CTX.minus(decimal_pi_value()) and h.phase() <= decimal_pi_value()
