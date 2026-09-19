"""F8-E General linear dependent sources: VCVS/E, VCCS/G, CCVS/H, CCCS/F.

Conventions (verified sign table, §14):
  - R: current pin1->pin2; V/E/H: aux unknown +->- (leaving "+").
  - Independent I: delivered INTO "+" (physical -->+); reported +->-
    current is -Is (certified F8-B/D3 quirk, intentionally preserved).
  - G/F outputs mirror I exactly: J delivered into "+", reported +->-
    current is -J. KCL/power tests prove this (not Ax-z alone).
  - Power absorbed S = 1/2 V conj(I) for AC, P = V*I for DC; actives
    deliver (absorbed False) — P >= 0 is NEVER asserted on actives.
  - Gains real (dimensionless/S/ohm); complex responses emerge in AC.

ngspice 47 mapping (calibrated experimentally, see
test_ngspice_calibration_mapping):
  - E: direct (node-pair control, same polarity).
  - H/F sense: ngspice Vsense current (+->- through the named source)
    EQUALS the Academic Core aux unknown (same sign). Verified: H1
    sensing a delivering 10 mA source gives -1 V in both engines.
  - G/F OUTPUTS are opposite-reference (AC delivers INTO "+",
    ngspice flows +->-), reusing the certified D3-vs-ngspice
    I-mapping: oracle decks negate (or compare magnitudes with the
    documented sign). R-branch control uses a 0V series ammeter in
    BOTH the Academic Core circuit (no — Academic Core needs none)
    ... precisely: the ammeter exists only in the ngspice deck,
    oriented +->- along the R 1->2 direction; the hand expectation is
    computed on the same joint circuit.
Expected values are hand derivations (nodal, Cramer, closed forms) —
never implementation outputs. ngspice is never the sole oracle.
"""
import ast
import time
from decimal import Decimal
from fractions import Fraction

import pytest

from academic_core.domain.engineering.ac import (
    ACStatus,
    PortDefinition,
    analyze_ac_thevenin,
    solve_ac,
)
from academic_core.domain.engineering.ac.impedance import ImpedanceCategory
from academic_core.domain.engineering.ac.response import (
    ResponseDefinition,
    current_through,
    frequency_response,
    voltage_between,
)
from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.math import RationalComplex
from academic_core.domain.engineering.math.linsolve.problem import NumericMode
from academic_core.domain.engineering.mna import (
    build_mna_problem,
    describe_dependents,
    solve_linear_dc,
)
from academic_core.domain.engineering.mna.errors import CircularControlError
from academic_core.domain.engineering.mna.result import SolveStatus
from academic_core.domain.engineering.thevenin import analyze_norton, analyze_thevenin
from academic_core.domain.engineering.thevenin.port import TheveninPort
from academic_core.domain.engineering.thevenin.result import (
    EquivalentStatus,
    ResistanceKind,
)
from academic_core.domain.engineering.units import parse_quantity

CTX_DECIMALS = 28


def Q(text):
    return parse_quantity(text)


def R_(ref, value, n1, n2):
    return Component(ref, "R", Q(value), {"1": n1, "2": n2}, {})


def L_(ref, value, n1, n2):
    return Component(ref, "L", Q(value), {"1": n1, "2": n2}, {})


def C_(ref, value, n1, n2):
    return Component(ref, "C", Q(value), {"1": n1, "2": n2}, {})


def V_(ref, value, np_, nm):
    return Component(ref, "V", Q(value), {"+": np_, "-": nm}, {})


def I_(ref, value, np_, nm):
    return Component(ref, "I", Q(value), {"+": np_, "-": nm}, {})


def E_(ref, gain, np_, nm, cp, cn):
    return Component(ref, "E", Q(gain), {"+": np_, "-": nm},
                     {"cp": cp, "cn": cn})


def G_(ref, gain, np_, nm, cp, cn):
    return Component(ref, "G", Q(gain), {"+": np_, "-": nm},
                     {"cp": cp, "cn": cn})


def H_(ref, gain, np_, nm, ctrl):
    return Component(ref, "H", Q(gain), {"+": np_, "-": nm},
                     {"control_ref": ctrl})


def F_(ref, gain, np_, nm, ctrl):
    return Component(ref, "F", Q(gain), {"+": np_, "-": nm},
                     {"control_ref": ctrl})


def ckt(name, *comps):
    c = Circuit(name)
    for e in comps:
        c.add(e)
    return c


def assert_dc_solved(res):
    assert res.status == SolveStatus.SOLVED, res.diagnostics
    return res


def dc_voltages(res):
    return {n.node: n.voltage.to_base() for n in res.node_voltages}


def dc_currents(res):
    return {b.ref: b.current.to_base() for b in res.branch_currents}


# -- DC stamps ------------------------------------------------------------------

def test_dc_vcvs_follower_exact():
    c = ckt("e1", V_("V1", "10 V", "in", "0"), E_("E1", "2", "out", "0", "in", "0"),
            R_("R1", "1 kOhm", "out", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["out"] == Decimal("20")
    assert r.conservation_checks.passed is True


def test_dc_vcvs_inverting_cramer():
    # Nodes a (driven 10V via Rs) — hand nodal, Fractions.
    # Va: fixed divider first: V1=10 s; R0 s-a 1k; R1 a-0 1k -> Va=5.
    # E1 b-0 = -3*V(a,0) = -15; R2 b-0 3k (load, draws nothing from E).
    c = ckt("e2", V_("V1", "10 V", "s", "0"), R_("R0", "1 kOhm", "s", "a"),
            R_("R1", "1 kOhm", "a", "0"), E_("E1", "-3", "b", "0", "a", "0"),
            R_("R2", "3 kOhm", "b", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    v = dc_voltages(r)
    assert v["a"] == Decimal("5")
    assert v["b"] == Decimal("-15")


def test_dc_vcvs_zero_is_zero_source():
    # E(μ=0) ≡ ideal 0V source: same nodes as explicit-0V circuit.
    mk = lambda tag, out_src: ckt(tag, V_("V1", "10 V", "in", "0"), out_src,
                                  R_("R1", "2 kOhm", "e", "0"))
    r_e = assert_dc_solved(solve_linear_dc(mk("z1", E_("E1", "0", "e", "0", "in", "0"))))
    r_v = assert_dc_solved(solve_linear_dc(mk("z2", V_("V2", "0 V", "e", "0"))))
    assert dc_voltages(r_e)["e"] == dc_voltages(r_v)["e"] == Decimal("0")


def test_dc_vccs_basic_and_reported_current():
    c = ckt("g1", V_("V1", "10 V", "in", "0"),
            G_("G1", "1 mS", "a", "0", "in", "0"), R_("R1", "1 kOhm", "a", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["a"] == Decimal("10")
    # Delivered into a: +10mA; reported +->- current is -10mA (I-mirror).
    assert dc_currents(r)["G1"] == Decimal("-0.01")
    assert r.conservation_checks.passed is True


def test_dc_vccs_zero_is_open():
    with_g = ckt("g0a", V_("V1", "10 V", "in", "0"),
                 G_("G1", "0 mS", "a", "0", "in", "0"), R_("R1", "1 kOhm", "a", "0"))
    # No drive at a: open G branch leaves a floating-looking 0V via R1.
    r = assert_dc_solved(solve_linear_dc(with_g))
    assert dc_voltages(r)["a"] == Decimal("0")
    assert dc_currents(r)["G1"] == Decimal("0")


def test_dc_ccvs_basic():
    c = ckt("h1", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "0"),
            H_("H1", "100 ohm", "out", "0", "R1"), R_("R2", "1 kOhm", "out", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["out"] == Decimal("1")
    assert dc_currents(r)["H1"] == Decimal("-0.001")
    assert r.conservation_checks.passed is True


def test_dc_ccvs_zero_is_zero_source():
    c = ckt("h0", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "0"),
            H_("H1", "0 ohm", "out", "0", "R1"), R_("R2", "1 kOhm", "out", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["out"] == Decimal("0")


def test_dc_cccs_basic():
    c = ckt("f1", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "0"),
            F_("F1", "3", "b", "0", "R1"), R_("R2", "1 kOhm", "b", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["b"] == Decimal("30")
    assert dc_currents(r)["F1"] == Decimal("-0.03")
    assert r.conservation_checks.passed is True


def test_dc_cccs_zero_is_open():
    c = ckt("f0", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "0"),
            F_("F1", "0", "b", "0", "R1"), R_("R2", "1 kOhm", "b", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["b"] == Decimal("0")


def test_dc_mixed_all_four_hand_nodal():
    # V1=10 s; R0 s-a 1k. At a: R1 a-0 2k; G1 a-0 1mS ctrl(s,0) [J=10mA in];
    # E1 b-0 = 2*V(a,0); R2 b-0 1k; F1 c-0 β=2 ctrl(R1); R3 c-0 1k;
    # H1 d-0 r=100 ctrl(R2); R4 d-0 1k.
    # KCL a: (Va-10)/1k + Va/2k - 10mA = 0 -> 3Va - 20 = 10... units V,mA,kΩ:
    # (Va-10) + Va/2 - 10 = 0 -> 1.5Va = 20 -> Va = 40/3.
    # Vb = 80/3. KCL c: Vc/1k - 2*I(R1) = 0; I(R1) = Va/2k = 20/3 mA
    # -> Vc = 2*20/3 = 40/3. I(R2) = Vb/1k = 80/3 mA; Vd = 100*80/3m = 8/3.
    c = ckt("mix", V_("V1", "10 V", "s", "0"), R_("R0", "1 kOhm", "s", "a"),
            R_("R1", "2 kOhm", "a", "0"), G_("G1", "1 mS", "a", "0", "s", "0"),
            E_("E1", "2", "b", "0", "a", "0"), R_("R2", "1 kOhm", "b", "0"),
            F_("F1", "2", "c", "0", "R1"), R_("R3", "1 kOhm", "c", "0"),
            H_("H1", "100 ohm", "d", "0", "R2"), R_("R4", "1 kOhm", "d", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    v = dc_voltages(r)
    assert v["a"] == Decimal(40) / Decimal(3)
    assert v["b"] == Decimal(80) / Decimal(3)
    assert v["c"] == Decimal(40) / Decimal(3)
    assert v["d"] == Decimal(8) / Decimal(3)
    assert r.conservation_checks.passed is True


def test_dc_cascaded_vcvs_gain_product():
    c = ckt("cas", V_("V1", "2 V", "in", "0"),
            E_("E1", "3", "m", "0", "in", "0"), E_("E2", "4", "out", "0", "m", "0"),
            R_("R1", "1 kOhm", "out", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["out"] == Decimal("24")


def test_dc_cross_coupled_chain():
    # E -> node -> G -> branch -> H (acyclic across kinds).
    c = ckt("xc", V_("V1", "5 V", "s", "0"),
            E_("E1", "2", "a", "0", "s", "0"), R_("R1", "1 kOhm", "a", "b"),
            G_("G1", "1 mS", "b", "0", "a", "0"),
            H_("H1", "500 ohm", "c", "0", "R1"), R_("R2", "1 kOhm", "c", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    v = dc_voltages(r)
    # Va=10; KCL b: (Vb-10)/1k - gm*10mA... J_G delivered = 10mA:
    # (Vb-10) - 10 = 0 -> Vb = 20. I(R1) 1->2 = (10-20)/1k = -10mA.
    # Vc = 500 * -0.01 = -5.
    assert v["a"] == Decimal("10")
    assert v["b"] == Decimal("20")
    assert v["c"] == Decimal("-5")
    assert r.conservation_checks.passed is True


def test_dc_cramer_two_node_with_g():
    # I1=5mA into a; R1 a-b 1k; R2 b-0 1k; G1 b-0 0.5mS ctrl(a,0).
    # Cramer on [[1,-1],[-1.5,2]] [Va,Vb] = [5,0] (V,mA,kΩ): det=0.5.
    # Va = (5*2)/0.5 = 20; Vb = (1.5*5)/0.5 = 15.
    c = ckt("cr", I_("I1", "5 mA", "a", "0"), R_("R1", "1 kOhm", "a", "b"),
            R_("R2", "1 kOhm", "b", "0"), G_("G1", "0.5 mS", "b", "0", "a", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    v = dc_voltages(r)
    assert v["a"] == Decimal("20")
    assert v["b"] == Decimal("15")


def test_dc_self_controlled_g_negative_resistance():
    # I1=5mA into a; R1 a-0 2k; G1 a-0 1mS ctrl(a,0).
    # KCL: Va/2k - 1m*Va - 5mA = 0 -> Va*(0.5-1) = 5 -> Va = -10.
    c = ckt("sg", I_("I1", "5 mA", "a", "0"), R_("R1", "2 kOhm", "a", "0"),
            G_("G1", "1 mS", "a", "0", "a", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["a"] == Decimal("-10")


# -- signs -----------------------------------------------------------------------

def test_sign_output_swap_negates():
    mk = lambda tag, p, m: ckt(tag, V_("V1", "10 V", "in", "0"),
                               E_("E1", "2", p, m, "in", "0"),
                               R_("R1", "1 kOhm", "out", "0"))
    r_ab = assert_dc_solved(solve_linear_dc(mk("s1", "out", "0")))
    r_ba = assert_dc_solved(solve_linear_dc(mk("s2", "0", "out")))
    assert dc_voltages(r_ab)["out"] == Decimal("20")
    assert dc_voltages(r_ba)["out"] == Decimal("-20")


def test_sign_control_swap_negates():
    mk = lambda tag, cp, cn: ckt(tag, V_("V1", "10 V", "in", "0"),
                                 E_("E1", "2", "out", "0", cp, cn),
                                 R_("R1", "1 kOhm", "out", "0"))
    assert dc_voltages(assert_dc_solved(solve_linear_dc(mk("c1", "in", "0"))))["out"] == Decimal("20")
    assert dc_voltages(assert_dc_solved(solve_linear_dc(mk("c2", "0", "in"))))["out"] == Decimal("-20")


def test_sign_gain_inversion_equals_control_swap():
    mk = lambda tag, g, cp, cn: ckt(tag, V_("V1", "10 V", "in", "0"),
                                    E_("E1", g, "out", "0", cp, cn),
                                    R_("R1", "1 kOhm", "out", "0"))
    a = dc_voltages(assert_dc_solved(solve_linear_dc(mk("g1", "-2", "in", "0"))))["out"]
    b = dc_voltages(assert_dc_solved(solve_linear_dc(mk("g2", "2", "0", "in"))))["out"]
    assert a == b == Decimal("-20")


def test_sign_r_control_terminal_swap_negates():
    # Control R7 x->0: I = +5mA -> H = +0.5V; swapped 0->x: I = -5mA.
    mk = lambda tag, n1, n2: ckt(tag, V_("V1", "10 V", "in", "0"),
                                 R_("R1", "1 kOhm", "in", "x"),
                                 R_("R7", "1 kOhm", n1, n2),
                                 H_("H1", "100 ohm", "out", "0", "R7"),
                                 R_("R2", "1 kOhm", "out", "0"))
    r_ab = assert_dc_solved(solve_linear_dc(mk("t1", "x", "0")))
    r_ba = assert_dc_solved(solve_linear_dc(mk("t2", "0", "x")))
    assert dc_voltages(r_ab)["out"] == Decimal("0.5")
    assert dc_voltages(r_ba)["out"] == Decimal("-0.5")


def test_sign_node_rename_digest_equal():
    c1 = ckt("n1", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "a"),
             E_("E1", "2", "b", "0", "a", "0"), R_("R2", "1 kOhm", "b", "0"))
    c2 = ckt("n2", V_("V1", "10 V", "src", "0"), R_("R1", "1 kOhm", "src", "x"),
             E_("E1", "2", "y", "0", "x", "0"), R_("R2", "1 kOhm", "y", "0"))
    r1, r2 = (assert_dc_solved(solve_linear_dc(c)) for c in (c1, c2))
    assert r1.provenance["digest"] != r2.provenance["digest"]  # names differ
    assert dc_voltages(r1)["b"] == dc_voltages(r2)["y"] == Decimal("20")


def test_sign_component_permutation_identical():
    comps = [V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "a"),
             E_("E1", "2", "b", "0", "a", "0"), R_("R2", "1 kOhm", "b", "0"),
             G_("G1", "1 mS", "a", "0", "b", "0")]
    # Same circuit name on both sides: the digest is name-sensitive by
    # design (test_sign_node_rename_digest_equal), so permutation-only
    # invariance requires holding the name fixed.
    r1 = assert_dc_solved(solve_linear_dc(ckt("perm", *comps)))
    r2 = assert_dc_solved(solve_linear_dc(ckt("perm", *reversed(comps))))
    assert r1.provenance["digest"] == r2.provenance["digest"]
    assert dc_voltages(r1) == dc_voltages(r2)


# -- singularities ------------------------------------------------------------------

def test_sing_contradictory_vcvs_inconsistent():
    c = ckt("cx", V_("V1", "5 V", "a", "0"), E_("E1", "2", "a", "0", "a", "0"))
    # E forces V(a) = 2*V(a) -> V(a) = 0, contradicting V1 = 5.
    r = solve_linear_dc(c)
    assert r.status == SolveStatus.INCONSISTENT


def test_sing_self_vcvs_unity_singular():
    c = ckt("sg1", V_("V1", "10 V", "s", "0"), R_("R1", "1 kOhm", "s", "a"),
            E_("E1", "1", "a", "0", "a", "0"))
    # V(a) = V(a): free variable -> singular but consistent.
    r = solve_linear_dc(c)
    assert r.status == SolveStatus.SINGULAR


def test_sing_self_vcvs_gain2_solved_zero():
    c = ckt("sg2", V_("V1", "10 V", "s", "0"), R_("R1", "1 kOhm", "s", "a"),
            E_("E1", "2", "a", "0", "a", "0"))
    # V(a) = 2V(a) -> V(a) = 0 uniquely.
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["a"] == Decimal("0")


def test_sing_incompatible_parallel_vcvs():
    c = ckt("pv", V_("V1", "10 V", "s", "0"), R_("R1", "1 kOhm", "s", "a"),
            E_("E1", "1", "a", "0", "s", "0"), E_("E2", "2", "a", "0", "s", "0"))
    r = solve_linear_dc(c)
    assert r.status == SolveStatus.INCONSISTENT


def test_sing_circular_ff_build_error_and_invalid_inband():
    c = ckt("cy", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "0"),
            F_("F1", "2", "a", "0", "F2"), F_("F2", "3", "a", "0", "F1"))
    with pytest.raises(CircularControlError):
        build_mna_problem(c)
    r = solve_linear_dc(c)
    assert r.status == SolveStatus.INVALID
    assert "circular" in r.diagnostics[0]


def test_sing_circular_self_f():
    c = ckt("cs", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "0"),
            F_("F1", "2", "a", "0", "F1"), R_("R2", "1 kOhm", "a", "0"))
    with pytest.raises(CircularControlError):
        build_mna_problem(c)


def test_sing_circular_via_h_chain():
    # H1 ctrl F1, F1 ctrl F2, F2 ctrl F1: cycle through H.
    c = ckt("ch", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "0"),
            F_("F1", "2", "a", "0", "F2"), F_("F2", "3", "a", "0", "F1"),
            H_("H1", "10 ohm", "b", "0", "F1"), R_("R2", "1 kOhm", "b", "0"))
    with pytest.raises(CircularControlError):
        build_mna_problem(c)


def test_sing_missing_control_ref():
    c = ckt("mc", V_("V1", "10 V", "in", "0"),
            H_("H1", "10 ohm", "a", "0", "RZZ"), R_("R1", "1 kOhm", "a", "0"))
    r = solve_linear_dc(c)
    assert r.status == SolveStatus.INVALID


def test_sing_missing_cp_cn():
    c = ckt("mn", V_("V1", "10 V", "in", "0"),
            E_("E1", "2", "a", "0", "ghost", "0"), R_("R1", "1 kOhm", "a", "0"))
    r = solve_linear_dc(c)
    assert r.status == SolveStatus.INVALID


def test_sing_gain_zero_all_valid():
    c = ckt("gz", V_("V1", "10 V", "s", "0"), R_("R1", "1 kOhm", "s", "a"),
            E_("E1", "0", "a", "0", "s", "0"), G_("G1", "0 mS", "a", "0", "s", "0"),
            H_("H1", "0 ohm", "b", "0", "R1"), F_("F1", "0", "b", "0", "R1"),
            R_("R2", "1 kOhm", "b", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["a"] == Decimal("0")
    assert dc_voltages(r)["b"] == Decimal("0")


# -- gain dimensions / malformed -------------------------------------------------------

def test_dim_e_rejects_siemens():
    c = ckt("de", V_("V1", "10 V", "in", "0"),
            E_("E1", "2 mS", "a", "0", "in", "0"), R_("R1", "1 kOhm", "a", "0"))
    assert solve_linear_dc(c).status == SolveStatus.INVALID


def test_dim_g_rejects_ohm():
    c = ckt("dg", V_("V1", "10 V", "in", "0"),
            G_("G1", "2 ohm", "a", "0", "in", "0"), R_("R1", "1 kOhm", "a", "0"))
    assert solve_linear_dc(c).status == SolveStatus.INVALID


def test_dim_h_rejects_dimensionless():
    c = ckt("dh", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "0"),
            H_("H1", "5", "a", "0", "R1"), R_("R2", "1 kOhm", "a", "0"))
    assert solve_linear_dc(c).status == SolveStatus.INVALID


def test_dim_f_rejects_siemens():
    c = ckt("df", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "0"),
            F_("F1", "5 mS", "a", "0", "R1"), R_("R2", "1 kOhm", "a", "0"))
    assert solve_linear_dc(c).status == SolveStatus.INVALID


def test_dim_gain_units_ok_variants():
    assert solve_linear_dc(ckt(
        "du", V_("V1", "10 V", "in", "0"),
        G_("G1", "1000 uS", "a", "0", "in", "0"),
        R_("R1", "1 kOhm", "a", "0"))).status == SolveStatus.SOLVED


# -- AC -------------------------------------------------------------------------------

def ac_solved(circuit, freq="1 kHz"):
    r = solve_ac(circuit, freq)
    assert r.status == ACStatus.SOLVED, r.diagnostics
    return r


def ac_voltage_map(res):
    return {n.node: n.phasor for n in res.node_voltages}


def test_ac_vcvs_follower_exact():
    # R-only + axis phases + exact gains -> EXACT eligible.
    c = ckt("ae", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "a"),
            E_("E1", "2", "a", "0", "in", "0"))
    r = ac_solved(c)
    assert r.numeric_mode.value == "exact"
    va = ac_voltage_map(r)["a"]
    assert isinstance(va, RationalComplex)
    assert va.re == Fraction(20) and va.im == Fraction(0)


def test_ac_vcvs_phase_control():
    c = ckt("ap", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "a"),
            E_("E1", "2", "b", "0", "a", "0"), R_("R2", "1 kOhm", "b", "0"),
            R_("R3", "1 kOhm", "a", "0"))
    r = ac_solved(c, "2 kHz")
    vb = ac_voltage_map(r)["b"]
    va = ac_voltage_map(r)["a"]
    assert abs(Decimal(str(vb.re)) - 2 * Decimal(str(va.re))) <= Decimal("1E-40")
    assert abs(Decimal(str(vb.im)) - 2 * Decimal(str(va.im))) <= Decimal("1E-40")


def test_ac_vccs_with_c_load_hand():
    # V1=10 in; G1 a-0 gm=1mS ctrl(in,0) [J=10mA in]; C1 a-0 1uF @1kHz.
    # KCL a: Va*Yc - J = 0 -> Va = J/Yc = 0.01/(j*2π*1000*1e-6).
    import cmath
    c = ckt("ag", V_("V1", "10 V", "in", "0"),
            G_("G1", "1 mS", "a", "0", "in", "0"), C_("C1", "1 uF", "a", "0"))
    r = ac_solved(c)
    va = ac_voltage_map(r)["a"]
    w = 2 * cmath.pi * 1000.0
    ref = 0.01 / complex(0, w * 1e-6)
    assert abs(float(va.re) - ref.real) / abs(ref) <= 1e-9
    assert abs(float(va.im) - ref.imag) / abs(ref) <= 1e-9
    assert r.kcl_max_residual is not None


def test_ac_ccvs_r_control():
    c = ckt("ah", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "0"),
            H_("H1", "100 ohm", "out", "0", "R1"), R_("R2", "1 kOhm", "out", "0"))
    r = ac_solved(c)
    vout = ac_voltage_map(r)["out"]
    assert abs(Decimal(str(vout.re)) - Decimal("1")) <= Decimal("1E-30")
    assert abs(Decimal(str(vout.im))) <= Decimal("1E-30")


def test_ac_ccvs_v_control_matches_ngspice_sign():
    # Aux +->- current of delivering V1 is -10mA -> H = -1V (calibrated).
    c = ckt("ahv", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "0"),
            H_("H1", "100 ohm", "out", "0", "V1"), R_("R2", "1 kOhm", "out", "0"))
    r = ac_solved(c)
    vout = ac_voltage_map(r)["out"]
    assert abs(Decimal(str(vout.re)) + Decimal("1")) <= Decimal("1E-30")


def test_ac_cccs_chain_g():
    # G1 a-0 gm=1mS ctrl(in): J_G delivered=10mA, reported -10mA.
    # F1 b-0 β=2 ctrl(G1): delivered = 2*(-10mA) = -20mA into b -> Vb=-20V.
    c = ckt("af", V_("V1", "10 V", "in", "0"),
            G_("G1", "1 mS", "a", "0", "in", "0"), R_("R1", "1 kOhm", "a", "0"),
            F_("F1", "2", "b", "0", "G1"), R_("R2", "1 kOhm", "b", "0"))
    r = ac_solved(c)
    vb = ac_voltage_map(r)["b"]
    assert abs(Decimal(str(vb.re)) + Decimal("20")) <= Decimal("1E-30")


def test_ac_mixed_lc_hp():
    c = ckt("am", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "a"),
            L_("L1", "10 mH", "a", "b"), C_("C1", "1 uF", "b", "0"),
            E_("E1", "3", "out", "0", "b", "0"), R_("R2", "1 kOhm", "out", "0"))
    r = ac_solved(c)
    assert r.numeric_mode.value == "high_precision"
    vout = ac_voltage_map(r)["out"]
    vb = ac_voltage_map(r)["b"]
    # 28-digit high_precision context: absolute error floor near these
    # magnitudes (~0.1-0.5) is ~1E-28, so 1E-30 was tighter than the
    # engine's own numeric mode promises. 1E-27 keeps 1-2 orders of
    # slack while still catching a real defect.
    assert abs(Decimal(str(vout.re)) - 3 * Decimal(str(vb.re))) <= Decimal("1E-27")
    assert r.kcl_max_residual is not None and r.kcl_max_residual <= Decimal("1E-20")


def test_ac_circular_invalid_inband():
    c = ckt("ac", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "0"),
            F_("F1", "2", "a", "0", "F2"), F_("F2", "3", "a", "0", "F1"))
    r = solve_ac(c, "1 kHz")
    assert r.status == ACStatus.INVALID


def test_ac_contradictory_e_inconsistent():
    c = ckt("ae2", V_("V1", "5 V", "a", "0"), E_("E1", "2", "a", "0", "a", "0"))
    r = solve_ac(c, "1 kHz")
    assert r.status == ACStatus.INCONSISTENT


# -- D4 power ----------------------------------------------------------------------------

def test_power_dc_delivering_and_tellegen():
    c = ckt("pw", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "0"),
            F_("F1", "3", "b", "0", "R1"), R_("R2", "1 kOhm", "b", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    pw = {e.ref: e for e in r.element_powers}
    assert pw["F1"].absorbed is False  # delivers 0.9 W
    assert pw["R2"].absorbed is True
    assert r.conservation_checks.passed is True


def test_power_ac_delivering_and_conservation():
    from academic_core.domain.engineering.ac.power import analyze_power
    c = ckt("pa", V_("V1", "10 V", "in", "0"),
            G_("G1", "1 mS", "a", "0", "in", "0"), R_("R1", "1 kOhm", "a", "0"))
    r = ac_solved(c)
    p = analyze_power(r)
    by_ref = {e.ref: e for e in p.elements}
    assert by_ref["G1"].regime == "delivering"
    assert by_ref["R1"].regime == "absorbing"
    assert p.conservation.passed is True


# -- D5 impedance / transfer ---------------------------------------------------------------

def test_d5_deactivation_keeps_dependents():
    from academic_core.domain.engineering.ac.impedance import deactivate_sources
    c = ckt("dk", V_("V1", "10 V", "in", "0"), I_("I1", "1 mA", "x", "0"),
            R_("R1", "1 kOhm", "in", "0"), E_("E1", "2", "a", "0", "in", "0"),
            G_("G1", "1 mS", "a", "0", "in", "0"),
            H_("H1", "10 ohm", "b", "0", "R1"), F_("F1", "2", "b", "0", "R1"))
    out = deactivate_sources(c)
    by_ref = {e.ref.upper(): e for e in out}
    assert by_ref["V1"].value.to_base() == Decimal("0")
    assert "I1" not in by_ref
    for dep in ("E1", "G1", "H1", "F1"):
        assert dep in by_ref, dep
        assert dict(by_ref[dep].parameters) == dict(
            next(e for e in c.components if e.ref == dep).parameters)


def test_d5_transfer_gain_gt1_negative_zero():
    # Closed-loop non-inverting amp, μ=100: Hv = 100/11 (hand nodal).
    def amp(mu):
        return ckt(f"amp{mu}", V_("V1", "1 V", "in", "0"),
                   E_("E1", str(mu), "out", "0", "in", "a"),
                   R_("R1", "1 kOhm", "a", "0"), R_("R2", "9 kOhm", "out", "a"))
    d = ResponseDefinition("transfer", (voltage_between("in", "0"),
                                       voltage_between("out", "0"), "V1"))
    r = frequency_response(amp(100), d, ["1 kHz"])
    h = r.points[0].value.require_defined()
    # R-only + E (real gain) circuit: EXACT eligible -> RationalComplex,
    # so compare Fractions directly (str(Fraction) like "100/11" is not
    # valid Decimal syntax).
    assert h.re == Fraction(100, 11)
    assert h.im == Fraction(0)


def test_d5_transfer_all_kinds_with_dependents():
    c = ckt("tk", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "out"),
            G_("G1", "1 mS", "out", "0", "in", "0"))
    grid = ["1 kHz"]
    defs = [
        ResponseDefinition("transfer", (voltage_between("in", "0"),
                                       voltage_between("out", "0"), "V1")),
        ResponseDefinition("transfer", (current_through("R1"),
                                       current_through("R1"), "V1")),
        ResponseDefinition("transfer", (current_through("R1"),
                                       voltage_between("out", "0"), "V1")),
        ResponseDefinition("transfer", (voltage_between("in", "0"),
                                       current_through("R1"), "V1")),
    ]
    for d in defs:
        sw = frequency_response(c, d, grid)
        assert sw.points[0].status == ACStatus.SOLVED
        assert sw.points[0].value.defined


def test_d5_port_impedance_active():
    # Port (a,0): R1 1k + G 1mS ctrl(in,0), driven via Rin 1k from 10V.
    # Deactivated (in shorted): control 0 -> J=0 -> Z = R1 = 1k.
    c = ckt("pz", V_("V1", "10 V", "in", "0"), R_("R0", "1 kOhm", "in", "a"),
            R_("R1", "1 kOhm", "a", "0"), G_("G1", "1 mS", "a", "0", "in", "0"))
    from academic_core.domain.engineering.ac.problem import build_ac_problem
    from academic_core.domain.engineering.ac.impedance import measure_port
    from academic_core.domain.engineering.ac.operating_point import ACOperatingPoint
    from academic_core.domain.engineering.ac.topology import reference_net
    op = ACOperatingPoint.from_frequency(Q("1 kHz"), reference_net(c.nets))
    prob = build_ac_problem(c, op, NumericMode.AUTO)
    sol = solve_ac(c, "1 kHz")
    z = measure_port(prob, sol, PortDefinition("a", "0"), quantity="impedance")
    assert z.category == ImpedanceCategory.FINITE
    # Live direct-method Z differs from deactivated (control live) — just
    # assert finiteness + KCL-certified parent here; D7 tests pin values.
    assert sol.status == ACStatus.SOLVED


def test_d5_frequency_response_with_e():
    c = ckt("fr", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "a"),
            E_("E1", "2", "a", "0", "in", "0"))
    d = ResponseDefinition("transfer", (voltage_between("in", "0"),
                                       voltage_between("a", "0"), "V1"))
    sw = frequency_response(c, d, ["100 Hz", "1 kHz", "10 kHz"])
    assert sw.status == "completed"
    for p in sw.points:
        h = p.value.require_defined()
        assert abs(Decimal(str(h.re)) - Decimal("2")) <= Decimal("1E-25")


# -- F8-C Thevenin/Norton ---------------------------------------------------------------------

def test_f8c_vth_with_e_and_zero_rth():
    c = ckt("th", V_("V1", "10 V", "in", "0"),
            E_("E1", "2", "out", "0", "in", "0"), R_("R1", "1 kOhm", "out", "0"))
    t = analyze_thevenin(c, TheveninPort("out", "0"))
    assert t.status == EquivalentStatus.VERIFIED
    assert t.v_th is not None and Fraction(t.v_th.to_base()) == Fraction(20)
    assert t.resistance_kind == ResistanceKind.ZERO
    n = analyze_norton(c, TheveninPort("out", "0"))
    assert n.status == EquivalentStatus.UNDEFINED  # zero Rth: no finite In


def test_f8c_rth_negative_active():
    # Port p: R1 p-m 1k; E1 m-0 μ=2 ctrl(p,0). Zin = -1k (hand nodal).
    c = ckt("nr", R_("R1", "1 kOhm", "p", "m"), E_("E1", "2", "m", "0", "p", "0"))
    # Needs a reference: tie via megohm? No — port-only net floats.
    # Add independent drive far away? Thevenin needs GND reachability:
    c2 = ckt("nr2", V_("V1", "1 V", "s", "0"), R_("R0", "1 MOhm", "s", "p"),
             R_("R1", "1 kOhm", "p", "m"), E_("E1", "2", "m", "0", "p", "0"))
    t = analyze_thevenin(c2, TheveninPort("p", "0"))
    assert t.status in (EquivalentStatus.SOLVED, EquivalentStatus.VERIFIED), t.diagnostics
    # Rth ≈ -1k dominated (1M sense lee-way): within 2 ohms of -1000.
    assert t.r_th is not None
    assert abs(Fraction(t.r_th.to_base()) + 1000) <= 2, t.r_th


def test_f8c_vth_rth_isc_consistent_active():
    # V1=10 s; R0 s-a 1k; R1 a-0 1k; G1 a-0 1mS ctrl(s,0).
    # Vth = 10; Rth = 500; Isc(A->B) = 20mA (hand KCL, §gate).
    c = ckt("cn", V_("V1", "10 V", "s", "0"), R_("R0", "1 kOhm", "s", "a"),
            R_("R1", "1 kOhm", "a", "0"), G_("G1", "1 mS", "a", "0", "s", "0"))
    t = analyze_thevenin(c, TheveninPort("a", "0"))
    assert t.status in (EquivalentStatus.SOLVED, EquivalentStatus.VERIFIED), t.diagnostics
    assert Fraction(t.v_th.to_base()) == Fraction(10)
    assert Fraction(t.r_th.to_base()) == Fraction(500)
    n = analyze_norton(c, TheveninPort("a", "0"))
    assert Fraction(n.i_n.to_base()) == Fraction(1, 50)  # 20 mA
    assert Fraction(t.v_th.to_base()) / Fraction(t.r_th.to_base()) == Fraction(n.i_n.to_base())


def test_f8c_nongnd_port_with_dependent():
    c = ckt("ng", V_("V1", "10 V", "t", "0"), R_("R1", "1 kOhm", "t", "a"),
            E_("E1", "3", "a", "b", "t", "0"), R_("R2", "1 kOhm", "b", "0"))
    t = analyze_thevenin(c, TheveninPort("a", "b"))
    assert t.status in (EquivalentStatus.SOLVED, EquivalentStatus.VERIFIED), t.diagnostics
    # Hand: Vt=10; Vb = Vt*R2/(R1+R2) = 5; Va = 3*10 + ... E across a-b:
    # Va - Vb = 30; KCL b: (Vb-Va)/... E supplies: nodal b: (Vb-0)/1k + I_E_out... use Va-Vb=30 + KCL a:
    # (Va-10)/1k + I_E_in = 0; KCL b: Vb/1k - I_E_in = 0 (E current circulates a-b):
    # Vb/1k = -(Va-10)/1k -> Vb = 10 - Va; Va - (10-Va) = 30 -> Va = 20, Vb = -10.
    assert Fraction(t.v_th.to_base()) == Fraction(30)


def test_f8c_singular_self_unity_port():
    c = ckt("sgp", V_("V1", "10 V", "s", "0"), R_("R1", "1 kOhm", "s", "a"),
            E_("E1", "1", "a", "0", "a", "0"))
    t = analyze_thevenin(c, TheveninPort("a", "0"))
    assert t.status in (EquivalentStatus.SINGULAR, EquivalentStatus.SOLVED,
                        EquivalentStatus.VERIFIED), t.diagnostics


def test_f8c_copy_preserves_parameters():
    from academic_core.domain.engineering.thevenin.analysis import (
        _copy_component,
        _deactivate_sources,
    )
    c = ckt("cp", V_("V1", "10 V", "in", "0"), I_("I1", "1 mA", "in", "0"),
            R_("R1", "1 kOhm", "in", "0"),
            E_("E1", "2", "a", "0", "in", "0"))
    e = next(x for x in c.components if x.ref == "E1")
    cp = _copy_component(e)
    assert dict(cp.parameters) == {"cp": "in", "cn": "0"}
    dead = _deactivate_sources(c)
    by_ref = {x.ref: x for x in dead.components}
    assert dict(by_ref["E1"].parameters) == {"cp": "in", "cn": "0"}
    assert "I1" not in by_ref  # independent I removed
    assert by_ref["V1"].value.to_base() == Decimal("0")  # V shorted


# -- D7 AC Thevenin/Norton ----------------------------------------------------------------------

def test_d7_vth_zth_with_e_exact():
    c = ckt("d7e", V_("V1", "10 V", "s", "0"), R_("R0", "1 kOhm", "s", "a"),
            R_("R1", "1 kOhm", "a", "0"), G_("G1", "1 mS", "a", "0", "s", "0"))
    r = analyze_ac_thevenin(c, PortDefinition("a", "0"), "1 kHz")
    assert r.status == ACStatus.SOLVED
    assert r.vth.re == Fraction(10) and r.vth.im == Fraction(0)
    assert r.zth.category == ImpedanceCategory.FINITE
    assert r.zth.value.re == Fraction(500) and r.zth.value.im == Fraction(0)
    # D7's own certified `inorton` convention (module docstring:
    # "port current entering A; MNA unknowns flow +->-, so entering-A
    # currents negate the unknown", invariant Vth + In*Zth = 0) is the
    # negation of F8-C's DC `i_n` (A->B short current). Both are
    # internally consistent within their own gates; D7 is certified
    # (16 bench/oracle/generality tests) and out of F8-E's authorized
    # scope to change (spec section 22), so this value follows D7's
    # sign, not F8-C's: -1/50, matching Vth + In*Zth = 10 + (-1/50)*500
    # = 0.
    assert r.inorton.re == Fraction(-1, 50) and r.inorton.im == Fraction(0)


def test_d7_negative_zth_active():
    # AC mirror of the DC negative-Rth cell (R-only -> EXACT).
    c = ckt("d7n", V_("V1", "1 V", "s", "0"), R_("R0", "1 MOhm", "s", "p"),
            R_("R1", "1 kOhm", "p", "m"), E_("E1", "2", "m", "0", "p", "0"))
    r = analyze_ac_thevenin(c, PortDefinition("p", "0"), "1 kHz")
    assert r.status == ACStatus.SOLVED
    assert r.zth.category == ImpedanceCategory.FINITE
    assert abs(r.zth.value.re + 1000) <= 2
    assert r.zth.value.im == Fraction(0)


def test_d7_dependents_change_zth():
    mk = lambda tag, extra: ckt(tag, V_("V1", "10 V", "s", "0"),
                                R_("R0", "1 kOhm", "s", "a"),
                                R_("R1", "1 kOhm", "a", "0"), *extra)
    r_off = analyze_ac_thevenin(mk("z0", []), PortDefinition("a", "0"), "1 kHz")
    r_on = analyze_ac_thevenin(
        mk("z1", [E_("E1", "2", "a", "0", "s", "0")]), PortDefinition("a", "0"), "1 kHz")
    assert r_off.zth.value.re == Fraction(500)
    assert r_on.zth.value.re == Fraction(0)  # ideal E output shorts the port
    assert r_on.vth.re == Fraction(20)


# -- transfer with dependents ----------------------------------------------------------------------

def test_transfer_negative_zero_gt1():
    c = ckt("tr", V_("V1", "1 V", "in", "0"), R_("R1", "1 kOhm", "in", "a"),
            E_("E1", "-4", "out", "0", "a", "0"), R_("R2", "1 kOhm", "out", "0"),
            R_("R3", "1 kOhm", "a", "0"))
    # Va = 1/2 (divider); Vout = -2. Hv = -2 < 0.
    d = ResponseDefinition("transfer", (voltage_between("in", "0"),
                                       voltage_between("out", "0"), "V1"))
    sw = frequency_response(c, d, ["1 kHz"])
    h = sw.points[0].value.require_defined()
    assert h.re == Fraction(-2) and h.im == Fraction(0)


def test_transfer_complex_emergent_ac():
    import cmath
    c = ckt("tc", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "a"),
            C_("C1", "1 uF", "a", "0"), E_("E1", "2", "out", "0", "a", "0"),
            R_("R2", "1 kOhm", "out", "0"))
    d = ResponseDefinition("transfer", (voltage_between("in", "0"),
                                       voltage_between("out", "0"), "V1"))
    sw = frequency_response(c, d, ["1 kHz"])
    h = sw.points[0].value.require_defined()
    w = 2 * cmath.pi * 1000.0
    va = 10.0 * (1 / complex(0, w * 1e-6)) / (1000.0 + 1 / complex(0, w * 1e-6))
    ref = 2.0 * va / 10.0
    got = complex(float(h.re), float(h.im))
    assert abs(got - ref) / abs(ref) <= 1e-9
    assert abs(got.imag) > 0.01  # genuinely complex emergent response


# -- ngspice ------------------------------------------------------------------------------------------

def _ng_backend():
    from academic_core.infrastructure.ngspice import NgSpiceBackend

    b = NgSpiceBackend()
    return b if b.detect().verified else None


NG = _ng_backend()


def _ng_version():
    import subprocess

    out = subprocess.run(
        ["C:\\Users\\dmart\\Documents\\ngspice-47_64\\Spice64\\bin\\ngspice_con.exe",
         "--version"], capture_output=True, text=True, timeout=60)
    return (out.stdout + out.stderr).splitlines()[2] if out.stdout else "unknown"


def _ng_op(deck):
    assert NG is not None
    res = NG.simulate(deck, analyses=("op",))
    assert res.status == "COMPLETED", res.raw_stderr
    return {n: float(s.samples[0]) for n, s in res.signals.items()}


def test_ngspice_calibration_mapping():
    # §9 MANDATORY calibration, pinned: H sense = aux +->- (same sign);
    # F/G outputs opposite-reference to ngspice (AC INTO "+" vs +->-).
    # H1 senses delivering V1 (aux = -10mA): both engines give -1V.
    sigs = _ng_op("* calib H\nV1 a 0 DC 10\nR1 a 0 1k\nH1 b 0 V1 100\n"
                  "R2 b 0 1k\n.op\n.end\n") if NG is not None else None
    if NG is None:
        pytest.skip("ngspice 47 verified backend unavailable")
    assert abs(sigs["v(b)"] + 1.0) <= 1e-6
    c = ckt("cal", V_("V1", "10 V", "a", "0"), R_("R1", "1 kOhm", "a", "0"),
            H_("H1", "100 ohm", "b", "0", "V1"), R_("R2", "1 kOhm", "b", "0"))
    assert dc_voltages(assert_dc_solved(solve_linear_dc(c)))["b"] == Decimal("-1")
    # F/G outputs: Academic Core = -1 × ngspice (certified I-opposition).
    assert abs(_ng_op("* calib F\nV1 a 0 DC 10\nR1 a 0 1k\nF1 c 0 V1 3\n"
                      "R3 c 0 1k\n.op\n.end\n")["v(c)"] - 30.0) <= 1e-6
    cf = ckt("calf", V_("V1", "10 V", "a", "0"), R_("R1", "1 kOhm", "a", "0"),
             F_("F1", "3", "c", "0", "V1"), R_("R3", "1 kOhm", "c", "0"))
    assert dc_voltages(assert_dc_solved(solve_linear_dc(cf)))["c"] == Decimal("-30")


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_e_dc():
    c = ckt("oe", V_("V1", "10 V", "s", "0"), R_("R0", "1 kOhm", "s", "a"),
            R_("R1", "2 kOhm", "a", "0"), E_("E1", "5", "b", "0", "a", "0"),
            R_("R2", "1 kOhm", "b", "0"))
    # Hand: Va = 10*2/3 = 20/3; Vb = 100/3.
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["a"] == Decimal(20) / Decimal(3)
    assert dc_voltages(r)["b"] == Decimal(100) / Decimal(3)
    deck = ("* E dc\nV1 s 0 DC 10\nR0 s a 1k\nR1 a 0 2k\nE1 b 0 a 0 5\n"
            "R2 b 0 1k\n.op\n.end\n")
    sigs = _ng_op(deck)
    assert abs(sigs["v(a)"] - float(Decimal(20) / Decimal(3))) <= 1e-4
    assert abs(sigs["v(b)"] - float(Decimal(100) / Decimal(3))) <= 1e-4


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_g_dc():
    c = ckt("og", V_("V1", "12 V", "s", "0"), R_("R0", "2 kOhm", "s", "a"),
            R_("R1", "3 kOhm", "a", "0"), G_("G1", "2 mS", "a", "0", "s", "0"))
    # Hand: J = 24mA into a. KCL: (Va-12)/2k + Va/3k - 24mA = 0
    # -> 3Va - 36 + 2Va - 144 = 0 (V,mA,kΩ scaled: (Va-12)*3 + Va*2 - 24*6 = 0)
    # 5Va = 36 + 144 = 180 -> Va = 36.
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["a"] == Decimal("36")
    deck = ("* G dc\nV1 s 0 DC 12\nR0 s a 2k\nR1 a 0 3k\nG1 a 0 s 0 0.002\n"
            "R9 a 0 1T\n.op\n.end\n")
    # NOTE: R9 1T grounding guard is inert (36/1T ≈ 0); hand value rules.
    # ngspice's G is opposite-reference to Academic Core's VCCS (module
    # docstring, calibrated in test_ngspice_calibration_mapping). Because
    # this network is NOT homogeneous in gm alone (Va = 7.2 + 14400*gm,
    # V1's independent 7.2 V term survives gm's sign flip), the raw
    # ngspice answer is NOT simply -36: it equals Academic Core's own
    # answer evaluated at -gm, i.e. Va(-0.002) = 7.2 - 28.8 = -21.6 V.
    # Verified against a live ngspice run (real backend, not assumed).
    sigs = _ng_op(deck)
    assert abs(sigs["v(a)"] - (-21.6)) <= 1e-2


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_h_dc_ammeter():
    # H senses the current through a 0V ammeter branch (adapter-only
    # element) in series with the R0/R7/R8 chain: total series R = 3k.
    # I(V2, aux +->- = m->k, entering-+ convention) = 10/3k = 10/3 mA.
    # H1 = 200 ohm * 10/3 mA = 2/3 V across R2.
    c = ckt("oh", V_("V1", "10 V", "s", "0"), R_("R0", "1 kOhm", "s", "a"),
            R_("R7", "1 kOhm", "a", "m"), V_("V2", "0 V", "m", "k"),
            R_("R8", "1 kOhm", "k", "0"), H_("H1", "200 ohm", "b", "0", "V2"),
            R_("R2", "1 kOhm", "b", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["b"] == Decimal(2) / Decimal(3)
    deck = ("* H dc\nV1 s 0 DC 10\nR0 s a 1k\nR7 a m 1k\nVam m k DC 0\n"
            "R8 k 0 1k\nH1 b 0 Vam 200\nR2 b 0 1k\n.op\n.end\n")
    sigs = _ng_op(deck)
    assert abs(sigs["v(b)"] - (2.0 / 3.0)) <= 1e-4


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_f_dc_ammeter():
    # Same ammeter chain as the H test: I(V2, aux +->- = m->k) = 10/3 mA.
    # F1 beta=4: Iout = 4 * 10/3 mA = 40/3 mA delivered into "+"=c;
    # R3 c-0: Vc = Iout*R3 = +40/3 V (delivered-into-+ convention, same
    # sign pattern as H's r*Icontrol -- Icontrol here is positive).
    # ngspice F output is opposite-reference (module docstring): its raw
    # v(c) is the negation, -40/3 V.
    c = ckt("of", V_("V1", "10 V", "s", "0"), R_("R0", "1 kOhm", "s", "a"),
            R_("R7", "1 kOhm", "a", "m"), V_("V2", "0 V", "m", "k"),
            R_("R8", "1 kOhm", "k", "0"), F_("F1", "4", "c", "0", "V2"),
            R_("R3", "1 kOhm", "c", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["c"] == Decimal(40) / Decimal(3)
    deck = ("* F dc\nV1 s 0 DC 10\nR0 s a 1k\nR7 a m 1k\nVam m k DC 0\n"
            "R8 k 0 1k\nF1 c 0 Vam 4\nR3 c 0 1k\n.op\n.end\n")
    sigs = _ng_op(deck)
    assert abs(sigs["v(c)"] + (40.0 / 3.0)) <= 1e-4


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_mixed_multi_dc():
    # E + G + R ladder, hand nodal in test via Fractions.
    # V1=6 s; R0 s-a 1k; R1 a-0 3k -> Va0 = 4.5 w/o deps.
    # G1 a-0 1mS ctrl(s,0): J=6mA in. E1 b-0 = 2*Va ctrl(a,0); R2 b-0 2k.
    # KCL a: (Va-6)/1k + Va/3k - 6mA = 0 -> 3Va-18 + Va - 18 = 0 -> Va = 9.
    # Vb = 18.
    c = ckt("om", V_("V1", "6 V", "s", "0"), R_("R0", "1 kOhm", "s", "a"),
            R_("R1", "3 kOhm", "a", "0"), G_("G1", "1 mS", "a", "0", "s", "0"),
            E_("E1", "2", "b", "0", "a", "0"), R_("R2", "2 kOhm", "b", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["a"] == Decimal("9")
    assert dc_voltages(r)["b"] == Decimal("18")
    deck = ("* mixed dc\nV1 s 0 DC 6\nR0 s a 1k\nR1 a 0 3k\nG1 a 0 s 0 0.001\n"
            "E1 b 0 a 0 2\nR2 b 0 2k\n.op\n.end\n")
    # Same opposite-reference G calibration as test_oracle_g_dc: this
    # network's Va = 4.5 + 4.5*gm(mS) is affine in gm, so ngspice's raw
    # answer (gm implicitly negated) is Va(-1mS) = 4.5 - 4.5 = 0 V, and
    # E1 (same polarity in both engines) gives Vb = 2*Va = 0 V too.
    # Verified against a live ngspice run.
    sigs = _ng_op(deck)
    assert abs(sigs["v(a)"] - 0.0) <= 1e-4
    assert abs(sigs["v(b)"] - 0.0) <= 1e-4


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_e_ac():
    import cmath
    # V1=10∠0 in; R1 in-a 1k; C1 a-0 1uF @1kHz; E1 out-0 = 2*V(a).
    c = ckt("oac", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "a"),
            C_("C1", "1 uF", "a", "0"), E_("E1", "2", "out", "0", "a", "0"),
            R_("R2", "1 kOhm", "out", "0"))
    r = solve_ac(c, "1 kHz")
    assert r.status == ACStatus.SOLVED
    w = 2 * cmath.pi * 1000.0
    va_ref = 10.0 * (1 / complex(0, w * 1e-6)) / (1000.0 + 1 / complex(0, w * 1e-6))
    got = {n.node: complex(float(n.phasor.re), float(n.phasor.im)) for n in r.node_voltages}
    assert abs(got["a"] - va_ref) / abs(va_ref) <= 1e-9
    assert abs(got["out"] - 2 * va_ref) / abs(2 * va_ref) <= 1e-9
    deck = ("* E ac\nV1 in 0 DC 0 AC 10\nR1 in a 1k\nC1 a 0 1u\nE1 out 0 a 0 2\n"
            "R2 out 0 1k\n.ac lin 2 1000 1001\n.print ac v(a) v(out)\n.end\n")
    from academic_core.domain.engineering.simulation import ACAnalysis
    res = NG.simulate(deck, analyses=(ACAnalysis(sweep_type="lin", points=2,
                                                fstart="1000", fstop="1001"),))
    assert res.status == "COMPLETED"
    va_ng = res.sample_complex_at("v(a)", "1000")
    assert abs(va_ng - va_ref) / abs(va_ref) <= 0.02


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_g_ac_and_transfer():
    # G AC values + Hv transfer with E>1.
    c = ckt("ogac", V_("V1", "10 V", "in", "0"),
            G_("G1", "1 mS", "a", "0", "in", "0"), R_("R1", "1 kOhm", "a", "0"))
    r = solve_ac(c, "1 kHz")
    assert r.status == ACStatus.SOLVED
    va = next(n.phasor for n in r.node_voltages if n.node == "a")
    assert abs(float(va.re) - 10.0) <= 1e-9 and abs(float(va.im)) <= 1e-9
    deck = ("* G ac\nV1 in 0 DC 0 AC 10\nG1 a 0 in 0 0.001\nR1 a 0 1k\n"
            ".ac lin 2 1000 1001\n.print ac v(a)\n.end\n")
    from academic_core.domain.engineering.simulation import ACAnalysis
    res = NG.simulate(deck, analyses=(ACAnalysis(sweep_type="lin", points=2,
                                                fstart="1000", fstop="1001"),))
    assert res.status == "COMPLETED"
    # ngspice G flows +->- (opposite reference): Va = -10 there.
    assert abs(res.sample_complex_at("v(a)", "1000") + 10.0) <= 0.2


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_hf_ac():
    # H AC: V1=10∠0 s; R1 s-0 1k (10mA); H1 out-0 r=100 ctrl(R1) -> 1V.
    c = ckt("ohac", V_("V1", "10 V", "s", "0"), R_("R1", "1 kOhm", "s", "0"),
            H_("H1", "100 ohm", "out", "0", "R1"), R_("R2", "1 kOhm", "out", "0"))
    r = solve_ac(c, "1 kHz")
    assert r.status == ACStatus.SOLVED
    vout = next(n.phasor for n in r.node_voltages if n.node == "out")
    assert abs(float(vout.re) - 1.0) <= 1e-9
    deck = ("* H ac\nV1 s 0 DC 0 AC 10\nR1 s m 1k\nVam m 0 DC 0\n"
            "H1 out 0 Vam 100\nR2 out 0 1k\n"
            ".ac lin 2 1000 1001\n.print ac v(out)\n.end\n")
    from academic_core.domain.engineering.simulation import ACAnalysis
    res = NG.simulate(deck, analyses=(ACAnalysis(sweep_type="lin", points=2,
                                                fstart="1000", fstop="1001"),))
    assert res.status == "COMPLETED"
    # Ammeter +->- along R 1->2 (s->m): sense agrees -> +1V both engines.
    assert abs(res.sample_complex_at("v(out)", "1000") - 1.0) <= 0.02


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_thevenin_active_dc():
    # Vth=10, Rth=500 (hand, §gate) vs ngspice .op + test-source deck.
    c = ckt("oth", V_("V1", "10 V", "s", "0"), R_("R0", "1 kOhm", "s", "a"),
            R_("R1", "1 kOhm", "a", "0"), G_("G1", "1 mS", "a", "0", "s", "0"))
    t = analyze_thevenin(c, TheveninPort("a", "0"))
    assert Fraction(t.v_th.to_base()) == Fraction(10)
    assert Fraction(t.r_th.to_base()) == Fraction(500)
    sigs = _ng_op("* th op\nV1 s 0 DC 10\nR0 s a 1k\nR1 a 0 1k\n"
                  "G1 a 0 s 0 0.001\n.op\n.end\n")
    # Same opposite-reference G calibration: Va = 5 + 5*gm(mS) here, so
    # ngspice's raw (gm-negated) answer is Va(-1mS) = 5 - 5 = 0 V.
    # Verified against a live ngspice run.
    assert abs(sigs["v(a)"] - 0.0) <= 1e-4
    # Test-source deck: deactivate V1 (short s), 1A into a.
    sigs2 = _ng_op("* th rth\nV1 s 0 DC 0\nR0 s a 1k\nR1 a 0 1k\n"
                   "G1 a 0 s 0 0.001\nItest a 0 DC 1\n.op\n.end\n")
    # Itest 1A INTO a (ngspice +->- = a->0?? Itest a 0 flows a->0 = AWAY).
    # KCL a: (Va-0)/1k + Va/1k - 0 (G ctrl s=0) + 1 (leaving via Itest) = 0
    # -> 2Va/1k = -1 -> Va = -500. |Va|/1A = 500 = Rth.
    assert abs(abs(sigs2["v(a)"]) - 500.0) <= 0.5


# -- metamorphic ------------------------------------------------------------------------

def test_meta_output_inversion_identity():
    # E(μ) with swapped output ≡ E(-μ): both give -20V here.
    a = ckt("m1", V_("V1", "10 V", "in", "0"), E_("E1", "2", "0", "out", "in", "0"),
            R_("R1", "1 kOhm", "out", "0"))
    b = ckt("m2", V_("V1", "10 V", "in", "0"), E_("E1", "-2", "out", "0", "in", "0"),
            R_("R1", "1 kOhm", "out", "0"))
    assert dc_voltages(assert_dc_solved(solve_linear_dc(a)))["out"] == Decimal("-20")
    assert dc_voltages(assert_dc_solved(solve_linear_dc(b)))["out"] == Decimal("-20")


def test_meta_gain_scaling_homogeneous():
    # VCVS outputs scale linearly with μ; VCCS with gm.
    mk = lambda tag, mu: ckt(tag, V_("V1", "7 V", "in", "0"),
                             E_("E1", mu, "out", "0", "in", "0"),
                             R_("R1", "3 kOhm", "out", "0"))
    assert dc_voltages(assert_dc_solved(solve_linear_dc(mk("k1", "3"))))["out"] == Decimal("21")
    assert dc_voltages(assert_dc_solved(solve_linear_dc(mk("k2", "6"))))["out"] == Decimal("42")


def test_meta_source_scaling_linear():
    # R1 is the a-0 load (matches test_dc_vccs_basic_and_reported_current's
    # topology): Va = gm*R1*Vin, linear in the source.
    mk = lambda tag, v: ckt(tag, V_("V1", v, "in", "0"), R_("R1", "1 kOhm", "a", "0"),
                            G_("G1", "2 mS", "a", "0", "in", "0"))
    assert dc_voltages(assert_dc_solved(solve_linear_dc(mk("s1", "10 V"))))["a"] == Decimal("20")
    assert dc_voltages(assert_dc_solved(solve_linear_dc(mk("s2", "5 V"))))["a"] == Decimal("10")


def test_meta_impedance_scaling():
    # Homogeneous scaling: R -> kR with gm -> gm/k leaves Va invariant.
    mk = lambda tag, rk, gm: ckt(tag, V_("V1", "10 V", "in", "0"),
                                 R_("R1", f"{rk} kOhm", "in", "a"),
                                 G_("G1", gm, "a", "0", "in", "0"),
                                 R_("R2", f"{rk} kOhm", "a", "0"))
    # k=1, gm=1mS: J = 10mA; (Va-10) + Va - 10 = 0 (mA) -> Va = 10.
    assert dc_voltages(assert_dc_solved(solve_linear_dc(mk("i1", "1", "1 mS"))))["a"] == Decimal("10")
    # k=10, gm=0.1mS: (Va-10)/10 + Va/10 - 1 = 0 -> 2Va - 10 - 10 = 0 -> Va=10.
    assert dc_voltages(assert_dc_solved(solve_linear_dc(mk("i2", "10", "0.1 mS"))))["a"] == Decimal("10")


def test_meta_degenerate_identities():
    # E(0)≡0V, G(0)≡open, H(0)≡0V(short), F(0)≡open — each vs R-only twin.
    base = [V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "a"),
            R_("R2", "1 kOhm", "a", "0")]
    r0 = dc_voltages(assert_dc_solved(solve_linear_dc(ckt("d0", *base))))["a"]
    assert r0 == Decimal("5")
    rE = dc_voltages(assert_dc_solved(solve_linear_dc(
        ckt("dE", *base, E_("E1", "0", "a", "0", "in", "0")))))["a"]
    assert rE == Decimal("0")  # 0V source dominates the divider node
    cG = ckt("dG", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "a"),
             R_("R2", "1 kOhm", "a", "0"), G_("G1", "0 mS", "a", "0", "in", "0"))
    assert dc_voltages(assert_dc_solved(solve_linear_dc(cG)))["a"] == Decimal("5")


def test_meta_deterministic_repeat():
    c = ckt("dr", V_("V1", "10 V", "s", "0"), R_("R0", "1 kOhm", "s", "a"),
            R_("R1", "2 kOhm", "a", "0"), G_("G1", "1 mS", "a", "0", "s", "0"),
            E_("E1", "2", "b", "0", "a", "0"), R_("R2", "1 kOhm", "b", "0"))
    r1, r2 = solve_linear_dc(c), solve_linear_dc(c)
    assert r1.provenance["digest"] == r2.provenance["digest"]
    # Determinism is about the canonical (timestamp-free) digest and
    # every other field; `provenance.timestamp` is real wall-clock by
    # design (§34: timestamp lives outside the canonical digest) and is
    # legitimately allowed to differ between two calls.
    d1, d2 = r1.to_dict(), r2.to_dict()
    d1["provenance"] = {k: v for k, v in d1["provenance"].items() if k != "timestamp"}
    d2["provenance"] = {k: v for k, v in d2["provenance"].items() if k != "timestamp"}
    assert d1 == d2


def test_meta_ac_deterministic():
    c = ckt("dra", V_("V1", "10 V", "in", "0"),
            G_("G1", "1 mS", "a", "0", "in", "0"), R_("R1", "1 kOhm", "a", "0"))
    r1, r2 = solve_ac(c, "1 kHz"), solve_ac(c, "1 kHz")
    assert r1.digest == r2.digest


# -- generality -----------------------------------------------------------------------------

def e_ladder(n):
    # Follower-per-section ladder: every follower output == Vin exactly.
    comps = [V_("V1", "7 V", "in", "0"), R_("R0", "1 kOhm", "in", "m1")]
    for i in range(1, n + 1):
        comps.append(E_(f"E{i}", "1", f"o{i}", "0", f"m{i}", "0"))
        comps.append(R_(f"R{i}", "1 kOhm", f"o{i}", "0"))
        if i < n:
            comps.append(R_(f"R{i + 100}", "1 kOhm", f"m{i}", f"m{i + 1}"))
    return ckt(f"elad{n}", *comps)


def test_generality_dc_ladder_scales():
    for n in (1, 2, 4, 8, 16, 32, 64):
        r = assert_dc_solved(solve_linear_dc(e_ladder(n)))
        v = dc_voltages(r)
        for i in range(1, n + 1):
            assert v[f"o{i}"] == Decimal("7"), (n, i)
            assert v[f"m{i}"] == Decimal("7"), (n, i)


def test_generality_ac_ladder_scales():
    for n in (1, 2, 4, 8, 16):
        c = e_ladder(n)
        r = solve_ac(c, "1 kHz")
        assert r.status == ACStatus.SOLVED, (n, r.diagnostics)
        for i in range(1, n + 1):
            ph = next(x.phasor for x in r.node_voltages if x.node == f"o{i}")
            assert abs(Decimal(str(ph.re)) - Decimal("7")) <= Decimal("1E-25"), (n, i)
            assert abs(Decimal(str(ph.im))) <= Decimal("1E-25")


def test_generality_topologies_with_dependents():
    # Bridge.
    bridge = ckt("gb", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "a"),
                 R_("R2", "2 kOhm", "in", "b"), R_("R3", "1 kOhm", "a", "0"),
                 R_("R4", "2 kOhm", "b", "0"), E_("E1", "2", "c", "0", "a", "b"),
                 R_("R5", "1 kOhm", "c", "0"))
    assert solve_linear_dc(bridge).status == SolveStatus.SOLVED
    # Mesh with G.
    mesh = ckt("gm", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "a"),
               R_("R2", "1 kOhm", "a", "b"), R_("R3", "1 kOhm", "b", "0"),
               R_("R4", "1 kOhm", "in", "b"), G_("G1", "1 mS", "a", "0", "b", "0"))
    assert solve_linear_dc(mesh).status == SolveStatus.SOLVED
    # Star with H.
    star = ckt("gs", V_("V1", "10 V", "c", "0"), R_("R1", "1 kOhm", "c", "a"),
               R_("R2", "1 kOhm", "c", "b"), R_("R3", "1 kOhm", "c", "d"),
               R_("R4", "1 kOhm", "a", "0"), R_("R5", "1 kOhm", "b", "0"),
               R_("R6", "1 kOhm", "d", "0"), H_("H1", "50 ohm", "e", "0", "R1"),
               R_("R7", "1 kOhm", "e", "0"))
    assert solve_linear_dc(star).status == SolveStatus.SOLVED
    # K3,3 with F.
    comps = [V_("V1", "10 V", "a1", "0")]
    kinds = ["R", "L", "C"]  # DC: only R allowed; use R + one F.
    k = 0
    for a in ("a1", "a2", "a3"):
        for b in ("b1", "b2", "b3"):
            k += 1
            comps.append(R_(f"R{k}", "1 kOhm", a, b))
    comps.append(F_("F1", "2", "c", "0", "R1"))
    comps.append(R_("R10", "1 kOhm", "c", "0"))
    k33 = ckt("gk", *comps)
    r = solve_linear_dc(k33)
    assert r.status == SolveStatus.SOLVED
    # Multigraph + high-degree + non-GND port target.
    multi = ckt("gx", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "x"),
                R_("R2", "2 kOhm", "in", "x"), R_("R3", "3 kOhm", "in", "x"),
                G_("G1", "1 mS", "x", "0", "in", "0"),
                F_("F1", "1", "x", "0", "R1"), E_("E1", "1", "y", "0", "x", "0"),
                R_("R4", "1 kOhm", "y", "0"))
    rm = assert_dc_solved(solve_linear_dc(multi))
    assert rm.conservation_checks.passed is True


# -- provenance / security / immutability -------------------------------------------------------

def test_provenance_dependent_graph():
    c = ckt("pg", V_("V1", "10 V", "s", "0"), R_("R1", "1 kOhm", "s", "a"),
            E_("E1", "2", "b", "0", "a", "0"), F_("F1", "3", "c", "0", "R1"),
            R_("R2", "1 kOhm", "c", "0"))
    g = describe_dependents(c)
    assert [e.ref for e in g.entries] == ["E1", "F1"]
    assert g.edges == (("F1", "R1"),)
    assert len(g.digest) == 64
    assert describe_dependents(c).digest == g.digest
    r = assert_dc_solved(solve_linear_dc(c))
    assert r.system_summary["dependent_digest"] == g.digest
    assert "timestamp" not in g.to_dict()


def test_provenance_rvi_untouched():
    c = ckt("pr", V_("V1", "10 V", "a", "0"), R_("R1", "1 kOhm", "a", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert "dependent_digest" not in r.system_summary
    assert set(r.system_summary) == {"n_nodes", "n_voltage_sources", "n_unknowns",
                                     "reference_node"}


def test_security_ast_gates():
    import pathlib
    roots = [pathlib.Path(__file__).parent.parent / "src" / "academic_core" /
             "domain" / "engineering" / p
             for p in ("mna/problem.py", "mna/solver.py", "mna/dependent.py",
                       "mna/errors.py", "ac/problem.py", "ac/solution.py",
                       "circuit.py", "thevenin/analysis.py",
                       "thevenin/verification.py", "thevenin/port.py")]
    forbidden = {"eval", "exec", "compile", "__import__", "open", "input",
                 "subprocess", "os", "sys", "socket", "http", "urllib",
                 "numpy", "scipy", "pickle", "marshal", "importlib"}
    for src in roots:
        tree = ast.parse(src.read_text(encoding="utf-8"))
        found_calls, found_imports = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                found_calls.add(node.func.id)
            if isinstance(node, ast.Import):
                for a in node.names:
                    found_imports.add(a.name.split(".")[0])
            if isinstance(node, ast.ImportFrom) and node.module:
                found_imports.add(node.module.split(".")[0])
        assert not (found_calls & forbidden), (src.name, found_calls & forbidden)
        assert not (found_imports & forbidden), (src.name, found_imports & forbidden)


def test_immutability_snapshot():
    c = ckt("im", V_("V1", "10 V", "s", "0"), R_("R1", "1 kOhm", "s", "a"),
            E_("E1", "2", "b", "0", "a", "0"), G_("G1", "1 mS", "b", "0", "a", "0"))
    before = [(e.ref, e.type, str(e.value.to_base()), dict(e.pins), dict(e.parameters))
              for e in c.components]
    solve_linear_dc(c)
    solve_ac(c, "1 kHz")
    from academic_core.domain.engineering.ac.impedance import measure_port
    from academic_core.domain.engineering.ac.problem import build_ac_problem
    from academic_core.domain.engineering.ac.operating_point import ACOperatingPoint
    from academic_core.domain.engineering.ac.topology import reference_net
    op = ACOperatingPoint.from_frequency(Q("1 kHz"), reference_net(c.nets))
    prob = build_ac_problem(c, op, NumericMode.AUTO)
    sol = solve_ac(c, "1 kHz")
    measure_port(prob, sol, PortDefinition("b", "0"))
    analyze_ac_thevenin(c, PortDefinition("b", "0"), "1 kHz")
    after = [(e.ref, e.type, str(e.value.to_base()), dict(e.pins), dict(e.parameters))
             for e in c.components]
    assert before == after


# -- performance -------------------------------------------------------------------------------------

def _ladder_e(n, ac=False):
    comps = [V_("V1", "7 V", "in", "0")]
    prev = "in"
    for i in range(1, n + 1):
        comps.append(R_(f"R{i}", "1 kOhm", prev, f"m{i}"))
        comps.append(E_(f"E{i}", "1", f"m{i}", "0", prev, "0"))
        prev = f"m{i}"
    return ckt(f"plead{n}", *comps)


def test_perf_dc_scales():
    # Timings diagnostic only (no wall-clock bound asserted by design).
    marks = {}
    for n in (16, 32, 64):
        t0 = time.perf_counter()
        r = assert_dc_solved(solve_linear_dc(_ladder_e(n)))
        dt = time.perf_counter() - t0
        marks[n] = round(dt, 2)
        assert dc_voltages(r)[f"m{n}"] == Decimal("7")
    print(f"\nF8-E DC perf seconds by N: {marks}")


def test_perf_ac_scales():
    # Timings diagnostic only (no wall-clock bound asserted by design).
    marks = {}
    for n in (16, 32, 64):
        t0 = time.perf_counter()
        r = solve_ac(_ladder_e(n), "1 kHz")
        dt = time.perf_counter() - t0
        marks[n] = round(dt, 2)
        assert r.status == ACStatus.SOLVED, (n, r.diagnostics)
    print(f"\nF8-E AC perf seconds by N: {marks}")


# -- audit closure: control-target matrix (§8 — pre-F8-F audit) -----------------
# Every control-target kind exercised at least once (hand values below).

def test_audit_h_controlled_by_e():
    # Vx=5 (divider); E1 e-0 = 3*5 = 15. E1 sources 7.5mA INTO e (R3
    # drains), so aux +->- current is -7.5mA; H1 = 100*(-0.0075) = -0.75V.
    c = ckt("ahe", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "x"),
            R_("R2", "1 kOhm", "x", "0"), E_("E1", "3", "e", "0", "x", "0"),
            R_("R3", "2 kOhm", "e", "0"), H_("H1", "100 ohm", "out", "0", "E1"),
            R_("R4", "1 kOhm", "out", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    v = dc_voltages(r)
    assert v["x"] == Decimal("5")
    assert v["e"] == Decimal("15")
    assert v["out"] == Decimal("-0.75")


def test_audit_f_controlled_by_e():
    # Same front end; E1 sources 7.5mA INTO e (R3 drains to ground), so the
    # aux +->- current is -7.5mA. F1 β=2: delivered 2*(-7.5mA) = -15mA
    # into f -> Vf = -15V. Tests RECONSTRUCTED (not delivered) control.
    c = ckt("afe", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "x"),
            R_("R2", "1 kOhm", "x", "0"), E_("E1", "3", "e", "0", "x", "0"),
            R_("R3", "2 kOhm", "e", "0"), F_("F1", "2", "f", "0", "E1"),
            R_("R4", "1 kOhm", "f", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["f"] == Decimal("-15")


def test_audit_h_controlled_by_h():
    # I(R1) = 10mA; H1 = 100*0.01 = 1V. H1 sources 1mA INTO h (R2 drains),
    # so aux +->- current is -1mA; H2 = 200*(-0.001) = -0.2V.
    c = ckt("ahh", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "0"),
            H_("H1", "100 ohm", "h", "0", "R1"), R_("R2", "1 kOhm", "h", "0"),
            H_("H2", "200 ohm", "out", "0", "H1"), R_("R3", "1 kOhm", "out", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    v = dc_voltages(r)
    assert v["h"] == Decimal("1")
    assert v["out"] == Decimal("-0.2")


def test_audit_f_controlled_by_h():
    # Front end as above (I(H1) aux = -1mA); F1 β=3 ctrl H1: delivered
    # 3*(-1mA) = -3mA into f; Rf 2k -> Vf = -6V.
    c = ckt("afh", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "0"),
            H_("H1", "100 ohm", "h", "0", "R1"), R_("R2", "1 kOhm", "h", "0"),
            F_("F1", "3", "f", "0", "H1"), R_("R3", "2 kOhm", "f", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["f"] == Decimal("-6")


def test_audit_h_controlled_by_independent_i():
    # I1 delivers 5mA into a; Va = 10V. Reconstructed I(I1) = -5mA (+->-).
    # H1 = 100 * (-0.005) = -0.5V. Tests the -Is control convention.
    c = ckt("ahi", I_("I1", "5 mA", "a", "0"), R_("R1", "2 kOhm", "a", "0"),
            H_("H1", "100 ohm", "out", "0", "I1"), R_("R2", "1 kOhm", "out", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    v = dc_voltages(r)
    assert v["a"] == Decimal("10")
    assert v["out"] == Decimal("-0.5")


def test_audit_f_controlled_by_independent_i():
    # F1 β=2 ctrl I1: delivered 2*(-5mA) = -10mA into f -> Vf = -10V.
    c = ckt("afi", I_("I1", "5 mA", "a", "0"), R_("R1", "2 kOhm", "a", "0"),
            F_("F1", "2", "f", "0", "I1"), R_("R2", "1 kOhm", "f", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["f"] == Decimal("-10")


def test_audit_h_self_control_deterministic():
    # H1 ctrl H1: Vout = 100*I(H1), KCL: Vout/1k + I(H1) = 0
    # -> 1.1*Vout = 0 -> Vout = 0 SOLVED (self-control, no false cycle).
    c = ckt("ahs", H_("H1", "100 ohm", "out", "0", "H1"),
            R_("R1", "1 kOhm", "out", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["out"] == Decimal("0")


def test_audit_ac_l_controlled_h():
    # I(L1) = 10/(j*2π*1000*0.01) = -j*0.15915A; H = 100*I -> -j*15.915V.
    import cmath
    c = ckt("ahl", V_("V1", "10 V", "in", "0"), L_("L1", "10 mH", "in", "0"),
            H_("H1", "100 ohm", "out", "0", "L1"), R_("R1", "1 kOhm", "out", "0"))
    r = solve_ac(c, "1 kHz")
    assert r.status == ACStatus.SOLVED, r.diagnostics
    w = 2 * cmath.pi * 1000.0
    ref = 100.0 * (10.0 / complex(0, w * 0.01))
    got = next(n.phasor for n in r.node_voltages if n.node == "out")
    assert abs(complex(float(got.re), float(got.im)) - ref) / abs(ref) <= 1e-9


def test_audit_ac_c_controlled_f():
    # I(C1) 1->2 = +j*6.283mA (reconstructed). F β=1: delivered J = -Irep
    # convention... precisely: reported F = -β*Irep = -j*6.283mA (+->-);
    # KCL at f: Vf/1k + (-j*6.283mA) = 0 -> Vf = +j*6.283V.
    import cmath
    c = ckt("acf", V_("V1", "10 V", "in", "0"), C_("C1", "1 uF", "in", "0"),
            F_("F1", "1", "f", "0", "C1"), R_("R1", "1 kOhm", "f", "0"))
    r = solve_ac(c, "1 kHz")
    assert r.status == ACStatus.SOLVED, r.diagnostics
    w = 2 * cmath.pi * 1000.0
    ref = (complex(0, w * 1e-6) * 10.0) * 1000.0
    got = next(n.phasor for n in r.node_voltages if n.node == "f")
    assert abs(complex(float(got.re), float(got.im)) - ref) / abs(ref) <= 1e-9
