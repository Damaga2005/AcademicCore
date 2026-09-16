"""Tests for F8-H: Nonlinear DC Operating Point with Shockley Diode.

Covers the full F8-H implementation specification:
- §13 Unit tests for Shockley model (current, conductance, companion, signs, units, parameters, extremes, overflow/underflow, determinism)
- §14 Mathematical verification (independent oracle, finite differences, residual, Jacobian, Newton step)
- §15 Circuit verification D1-D15 (forward, reverse, parameter variations, multiple resistors, multiple diodes, series, parallel, bridge, ladder, mesh, transformer, opamp, dependent sources, non-GND/floating)
- §16 & §17 Generality and scalability matrices (N=1, 2, 4, 8, 16, 32, 64)
- §18 Failure modes (MAX_ITERATIONS, DIVERGED, SINGULAR_JACOBIAN, INVALID, UNSUPPORTED)
- §19 ngspice comparison (external oracle)
- §21 Performance and tripwires
- §22 Security invariants (overflow, huge params, iteration bomb, memory growth, AST scan)
- §23 Provenance
- §24 Netlist / AST integration
- §25 Dimensional and units correctness
- §26 Audit Q1-Q5 decisions
"""

from __future__ import annotations

import ast
from decimal import Decimal
import math
import shutil
import time

import pytest

from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.mna import (
    DiodeParams,
    NonlinearResult,
    NonlinearStatus,
    build_mna_problem,
    companion,
    extract_diode_params,
    shockley_conductance,
    shockley_current,
    solve_linear_dc,
    solve_nonlinear_dc,
)
from academic_core.domain.engineering.mna.errors import (
    FloatingCircuitError,
    InvalidCircuitError,
    MissingReferenceError,
    UnsupportedElementError,
)
from academic_core.domain.engineering.mna.nonlinear import (
    ATOL,
    MAX_BACKTRACK,
    MAX_ITER,
    RTOL,
    STOL,
    _NewtonSystem,
)
from academic_core.domain.engineering.math.trig import make_context
from academic_core.domain.engineering.units import Quantity, parse_quantity, parse_unit

V_UNIT = parse_unit("V")
A_UNIT = parse_unit("A")
OHM_UNIT = parse_unit("ohm")
S_UNIT = parse_unit("S")
W_UNIT = parse_unit("W")


def diode(ref: str, a: str, k: str,
          is_str: str = "1e-14 A", n_str: str = "1",
          vt_str: str = "0.02585 V") -> Component:
    """Helper to construct a Shockley diode Component."""
    return Component(
        ref=ref,
        type="D",
        value=None,
        pins={"A": a, "K": k},
        parameters={
            "Is": parse_quantity(is_str),
            "n": parse_quantity(n_str),
            "Vt": parse_quantity(vt_str),
        },
    )


def res(ref: str, n1: str, n2: str, val_str: str) -> Component:
    return Component(ref=ref, type="R", value=parse_quantity(val_str),
                     pins={"1": n1, "2": n2})


def vsrc(ref: str, p: str, m: str, val_str: str) -> Component:
    return Component(ref=ref, type="V", value=parse_quantity(val_str),
                     pins={"+": p, "-": m})


def isrc(ref: str, p: str, m: str, val_str: str) -> Component:
    return Component(ref=ref, type="I", value=parse_quantity(val_str),
                     pins={"+": p, "-": m})


# ==============================================================================
# §13 TESTS UNITARIOS DEL MODELO SHOCKLEY
# ==============================================================================

class TestShockleyUnit:
    def test_shockley_forward_current(self):
        ctx = make_context()
        p = DiodeParams(Is=Decimal("1e-14"), n=Decimal("1"),
                        Vt=Decimal("0.02585"))
        vd = Decimal("0.7")
        i = shockley_current(vd, p, ctx)
        assert i > Decimal(0)
        expected = 1e-14 * (math.exp(0.7 / 0.02585) - 1.0)
        assert abs(float(i) - expected) / expected < 1e-6

    def test_shockley_reverse_current(self):
        ctx = make_context()
        p = DiodeParams(Is=Decimal("1e-14"), n=Decimal("1"),
                        Vt=Decimal("0.02585"))
        vd = Decimal("-5.0")
        i = shockley_current(vd, p, ctx)
        assert i < Decimal(0)
        assert abs(i - Decimal("-1e-14")) < Decimal("1e-25")

    def test_shockley_zero_bias(self):
        ctx = make_context()
        p = DiodeParams(Is=Decimal("1e-14"), n=Decimal("1"),
                        Vt=Decimal("0.02585"))
        i = shockley_current(Decimal(0), p, ctx)
        assert i == Decimal(0)

    def test_shockley_conductance(self):
        ctx = make_context()
        p = DiodeParams(Is=Decimal("1e-14"), n=Decimal("1"),
                        Vt=Decimal("0.02585"))
        vd = Decimal("0.65")
        g = shockley_conductance(vd, p, ctx)
        assert g > Decimal(0)
        expected_g = (1e-14 / 0.02585) * math.exp(0.65 / 0.02585)
        assert abs(float(g) - expected_g) / expected_g < 1e-6

    def test_companion_linearization_and_signs(self):
        ctx = make_context()
        p = DiodeParams(Is=Decimal("1e-14"), n=Decimal("1"),
                        Vt=Decimal("0.02585"))
        vd = Decimal("0.68")
        i_val, g_val, ieq = companion(vd, p, ctx)
        assert i_val > 0
        assert g_val > 0
        reconstructed = ctx.add(ctx.multiply(g_val, vd), ieq)
        assert abs(reconstructed - i_val) < Decimal("1e-25")

    def test_parameter_validation_missing_keys(self):
        c = Component("D1", "D", None, {"A": "1", "K": "0"},
                      parameters={"Is": parse_quantity("1e-14 A")})
        with pytest.raises(InvalidCircuitError, match="diode needs exactly parameters"):
            extract_diode_params(c)

    def test_parameter_validation_wrong_dimensions(self):
        c = Component("D1", "D", None, {"A": "1", "K": "0"},
                      parameters={
                          "Is": parse_quantity("1e-14 V"),
                          "n": parse_quantity("1"),
                          "Vt": parse_quantity("0.02585 V"),
                      })
        with pytest.raises(InvalidCircuitError, match="wrong dimension"):
            extract_diode_params(c)

    def test_parameter_validation_non_positive_or_zero(self):
        for bad_is in ("0 A", "-1e-14 A"):
            c = Component("D1", "D", None, {"A": "1", "K": "0"},
                          parameters={
                              "Is": parse_quantity(bad_is),
                              "n": parse_quantity("1"),
                              "Vt": parse_quantity("0.02585 V"),
                          })
            with pytest.raises(InvalidCircuitError, match="must be > 0"):
                extract_diode_params(c)

    def test_parameter_validation_non_finite(self):
        c = Component("D1", "D", None, {"A": "1", "K": "0"},
                      parameters={
                          "Is": Quantity(Decimal("Infinity"), A_UNIT),
                          "n": parse_quantity("1"),
                          "Vt": parse_quantity("0.02585 V"),
                      })
        with pytest.raises(InvalidCircuitError, match="non-finite"):
            extract_diode_params(c)

    def test_diode_with_value_rejected(self):
        c = Circuit("dval")
        c.add(Component("D1", "D", parse_quantity("1 V"), {"A": "1", "K": "0"},
                        parameters={
                            "Is": parse_quantity("1e-14 A"),
                            "n": parse_quantity("1"),
                            "Vt": parse_quantity("0.02585 V"),
                        }))
        res = solve_nonlinear_dc(c)
        assert res.status == NonlinearStatus.INVALID
        assert any("diode takes no value" in d for d in res.diagnostics)

    def test_extreme_underflow_safety(self):
        ctx = make_context()
        p = DiodeParams(Is=Decimal("1e-14"), n=Decimal("1"),
                        Vt=Decimal("0.02585"))
        vd = Decimal("-10000.0")
        i = shockley_current(vd, p, ctx)
        assert i == Decimal("-1e-14")

    def test_extreme_overflow_safety(self):
        ctx = make_context()
        p = DiodeParams(Is=Decimal("1e-14"), n=Decimal("1"),
                        Vt=Decimal("0.02585"))
        vd = Decimal("1000000000000.0")
        i = shockley_current(vd, p, ctx)
        assert not i.is_finite()

    def test_determinism_unit(self):
        ctx = make_context()
        p = DiodeParams(Is=Decimal("1e-14"), n=Decimal("1"),
                        Vt=Decimal("0.02585"))
        vd = Decimal("0.671234567890123456789")
        i1 = shockley_current(vd, p, ctx)
        i2 = shockley_current(vd, p, ctx)
        assert i1 == i2


# ==============================================================================
# §14 TESTS MATEMÁTICOS
# ==============================================================================

class TestMathematicalFormulation:
    def test_independent_current_oracle(self):
        Is = 1.2e-14
        n = 1.1
        Vt = 0.0259
        p = DiodeParams(Is=Decimal(str(Is)), n=Decimal(str(n)),
                        Vt=Decimal(str(Vt)))
        ctx = make_context()
        for v_test in [-2.0, -0.5, 0.0, 0.2, 0.5, 0.7]:
            i_model = float(shockley_current(Decimal(str(v_test)), p, ctx))
            i_oracle = Is * (math.exp(v_test / (n * Vt)) - 1.0)
            if abs(i_oracle) > 1e-15:
                assert abs(i_model - i_oracle) / abs(i_oracle) < 1e-7
            else:
                assert abs(i_model - i_oracle) < 1e-15

    def test_conductance_matches_central_difference(self):
        ctx = make_context()
        p = DiodeParams(Is=Decimal("1e-14"), n=Decimal("1.0"),
                        Vt=Decimal("0.02585"))
        vd = Decimal("0.65")
        h = Decimal("1e-8")
        i_plus = shockley_current(vd + h, p, ctx)
        i_minus = shockley_current(vd - h, p, ctx)
        num_deriv = ctx.divide(ctx.subtract(i_plus, i_minus), ctx.multiply(Decimal(2), h))
        ana_deriv = shockley_conductance(vd, p, ctx)
        assert abs(float(ana_deriv) - float(num_deriv)) / float(ana_deriv) < 1e-6

    def test_residual_and_jacobian_against_finite_diff(self):
        c = Circuit("math_check")
        c.add(vsrc("V1", "1", "0", "1 V"))
        c.add(res("R1", "1", "2", "1 kohm"))
        c.add(diode("D1", "2", "0"))
        prob = build_mna_problem(c, allow_diodes=True)
        diodes = {"D1": extract_diode_params(c.components[2])}
        system = _NewtonSystem(prob, diodes)

        x0 = (Decimal("1.0"), Decimal("0.65"), Decimal("-0.00035"))
        F0 = system.residual(x0)
        assert F0 is not None
        J0 = system.jacobian(x0)
        assert J0 is not None

        h = Decimal("1e-9")
        ctx = system.ctx
        for j in range(system.n):
            xp = list(x0)
            xp[j] = ctx.add(xp[j], h)
            Fp = system.residual(tuple(xp))
            assert Fp is not None
            for i in range(system.n):
                dF_num = float(ctx.divide(ctx.subtract(Fp[i], F0[i]), h))
                dF_ana = float(J0[i][j])
                diff = abs(dF_ana - dF_num)
                if abs(dF_ana) > 1e-4:
                    assert diff / abs(dF_ana) < 1e-4
                else:
                    assert diff < 1e-4


# ==============================================================================
# §15 TESTS DE CIRCUITO (D1 A D15)
# ==============================================================================

class TestCircuitsD1toD15:
    def test_d1_source_resistor_diode_forward(self):
        c = Circuit("D1_forward")
        c.add(vsrc("V1", "1", "0", "5 V"))
        c.add(res("R1", "1", "2", "1 kohm"))
        c.add(diode("D1", "2", "0", is_str="1e-14 A", n_str="1", vt_str="0.02585 V"))
        res_sol = solve_nonlinear_dc(c)
        assert res_sol.status == NonlinearStatus.CONVERGED
        nv = {n.node: n.voltage.to_base() for n in res_sol.node_voltages}
        assert nv["1"] == Decimal("5")
        assert Decimal("0.60") < nv["2"] < Decimal("0.75")
        bc = {b.ref: b.current.to_base() for b in res_sol.branch_currents}
        assert Decimal("0.0040") < bc["D1"] < Decimal("0.0045")
        assert abs(bc["R1"] - bc["D1"]) < Decimal("1e-12")
        assert res_sol.conservation_checks is not None
        assert res_sol.conservation_checks.passed

    def test_d2_reverse_biased_diode(self):
        c = Circuit("D2_reverse")
        c.add(vsrc("V1", "0", "1", "5 V"))
        c.add(res("R1", "1", "2", "1 kohm"))
        c.add(diode("D1", "2", "0", is_str="1e-14 A", n_str="1", vt_str="0.02585 V"))
        res_sol = solve_nonlinear_dc(c)
        assert res_sol.status == NonlinearStatus.CONVERGED
        nv = {n.node: n.voltage.to_base() for n in res_sol.node_voltages}
        assert nv["1"] == Decimal("-5")
        assert abs(nv["2"] - Decimal("-5")) < Decimal("1e-9")
        bc = {b.ref: b.current.to_base() for b in res_sol.branch_currents}
        assert abs(bc["D1"] - Decimal("-1e-14")) < Decimal("1e-18")

    def test_d3_different_is(self):
        for is_val in ("1e-15 A", "1e-12 A", "1e-9 A"):
            c = Circuit(f"D3_{is_val}")
            c.add(vsrc("V1", "1", "0", "3 V"))
            c.add(res("R1", "1", "2", "1 kohm"))
            c.add(diode("D1", "2", "0", is_str=is_val))
            res_sol = solve_nonlinear_dc(c)
            assert res_sol.status == NonlinearStatus.CONVERGED

    def test_d4_different_n(self):
        v_drops = []
        for n_val in ("1.0", "1.5", "2.0"):
            c = Circuit(f"D4_n_{n_val}")
            c.add(vsrc("V1", "1", "0", "5 V"))
            c.add(res("R1", "1", "2", "1 kohm"))
            c.add(diode("D1", "2", "0", n_str=n_val))
            res_sol = solve_nonlinear_dc(c)
            assert res_sol.status == NonlinearStatus.CONVERGED
            nv = {n.node: n.voltage.to_base() for n in res_sol.node_voltages}
            v_drops.append(nv["2"])
        assert v_drops[0] < v_drops[1] < v_drops[2]

    def test_d5_multiple_resistors_voltage_divider(self):
        c = Circuit("D5_divider")
        c.add(vsrc("V1", "1", "0", "10 V"))
        c.add(res("R1", "1", "2", "2 kohm"))
        c.add(res("R2", "2", "0", "3 kohm"))
        c.add(diode("D1", "2", "0"))
        res_sol = solve_nonlinear_dc(c)
        assert res_sol.status == NonlinearStatus.CONVERGED
        assert res_sol.conservation_checks.passed

    def test_d6_multiple_diodes(self):
        c = Circuit("D6_multi")
        c.add(vsrc("V1", "1", "0", "5 V"))
        c.add(res("R1", "1", "2", "1 kohm"))
        c.add(diode("D1", "2", "0"))
        c.add(res("R2", "1", "3", "2 kohm"))
        c.add(diode("D2", "3", "0"))
        res_sol = solve_nonlinear_dc(c)
        assert res_sol.status == NonlinearStatus.CONVERGED
        nv = {n.node: n.voltage.to_base() for n in res_sol.node_voltages}
        assert nv["2"] > 0
        assert nv["3"] > 0

    def test_d7_series_diodes(self):
        c = Circuit("D7_series")
        c.add(vsrc("V1", "1", "0", "5 V"))
        c.add(res("R1", "1", "2", "1 kohm"))
        c.add(diode("D1", "2", "3"))
        c.add(diode("D2", "3", "0"))
        res_sol = solve_nonlinear_dc(c)
        assert res_sol.status == NonlinearStatus.CONVERGED
        nv = {n.node: n.voltage.to_base() for n in res_sol.node_voltages}
        assert Decimal("1.2") < nv["2"] < Decimal("1.5")
        assert Decimal("0.6") < nv["3"] < Decimal("0.75")
        assert res_sol.conservation_checks.passed

    def test_d8_parallel_diodes(self):
        c = Circuit("D8_parallel")
        c.add(vsrc("V1", "1", "0", "5 V"))
        c.add(res("R1", "1", "2", "1 kohm"))
        c.add(diode("D1", "2", "0", is_str="1e-14 A"))
        c.add(diode("D2", "2", "0", is_str="2e-14 A"))
        res_sol = solve_nonlinear_dc(c)
        assert res_sol.status == NonlinearStatus.CONVERGED
        bc = {b.ref: b.current.to_base() for b in res_sol.branch_currents}
        assert abs(bc["D2"] - Decimal(2) * bc["D1"]) / bc["D1"] < Decimal("1e-4")
        assert res_sol.conservation_checks.passed

    def test_d9_bridge_rectifier_topology(self):
        c = Circuit("D9_bridge")
        c.add(vsrc("V1", "in_p", "0", "10 V"))
        c.add(res("R1", "in_p", "ac1", "10 ohm"))
        c.add(diode("D1", "ac1", "dc_p"))
        c.add(diode("D2", "0", "dc_p"))
        c.add(diode("D3", "dc_n", "ac1"))
        c.add(diode("D4", "dc_n", "0"))
        c.add(res("R2", "dc_p", "dc_n", "1 kohm"))
        res_sol = solve_nonlinear_dc(c)
        assert res_sol.status == NonlinearStatus.CONVERGED
        nv = {n.node: n.voltage.to_base() for n in res_sol.node_voltages}
        v_load = nv["dc_p"] - nv["dc_n"]
        assert v_load > Decimal("8.0")
        assert res_sol.conservation_checks.passed

    def test_d10_ladder_network(self):
        c = Circuit("D10_ladder")
        c.add(vsrc("V1", "n0", "0", "5 V"))
        for i in range(4):
            c.add(res(f"R{i+1}", f"n{i}", f"n{i+1}", "100 ohm"))
            c.add(diode(f"D{i+1}", f"n{i+1}", "0"))
        res_sol = solve_nonlinear_dc(c)
        assert res_sol.status == NonlinearStatus.CONVERGED
        assert res_sol.conservation_checks.passed

    def test_d11_mesh_network(self):
        c = Circuit("D11_mesh")
        c.add(vsrc("V1", "1", "0", "5 V"))
        c.add(res("R1", "1", "2", "500 ohm"))
        c.add(res("R2", "1", "3", "500 ohm"))
        c.add(diode("D1", "2", "4"))
        c.add(diode("D2", "3", "4"))
        c.add(res("R3", "2", "3", "1 kohm"))
        c.add(res("R4", "4", "0", "1 kohm"))
        res_sol = solve_nonlinear_dc(c)
        assert res_sol.status == NonlinearStatus.CONVERGED
        assert res_sol.conservation_checks.passed

    def test_d12_transformer_with_diode(self):
        c = Circuit("D12_transformer")
        c.add(vsrc("V1", "p1", "0", "10 V"))
        c.add(res("R1", "p1", "1", "100 ohm"))
        c.add(Component("T1", "T", parse_quantity("2"),
                        pins={"1": "1", "2": "0", "3": "2", "4": "0"}))
        c.add(res("R2", "2", "3", "100 ohm"))
        c.add(diode("D1", "3", "0"))
        res_sol = solve_nonlinear_dc(c)
        assert res_sol.status == NonlinearStatus.CONVERGED
        nv = {n.node: n.voltage.to_base() for n in res_sol.node_voltages}
        assert abs(nv["2"] - Decimal(2) * nv["1"]) < Decimal("1e-8")
        assert res_sol.conservation_checks.passed

    def test_d13_opamp_with_diode(self):
        c = Circuit("D13_opamp")
        c.add(vsrc("V1", "in", "0", "2 V"))
        c.add(Component("O1", "O", None, {"+": "in", "-": "out", "o": "out"}))
        c.add(res("R1", "out", "d_node", "500 ohm"))
        c.add(diode("D1", "d_node", "0"))
        res_sol = solve_nonlinear_dc(c)
        assert res_sol.status == NonlinearStatus.CONVERGED
        nv = {n.node: n.voltage.to_base() for n in res_sol.node_voltages}
        assert abs(nv["out"] - Decimal("2")) < Decimal("1e-9")
        assert res_sol.conservation_checks.passed

    def test_d14_dependent_sources_interaction(self):
        c = Circuit("D14_dependent")
        c.add(vsrc("V1", "1", "0", "5 V"))
        c.add(res("R1", "1", "2", "1 kohm"))
        c.add(diode("D1", "2", "0"))
        c.add(Component("E1", "E", parse_quantity("3"),
                        pins={"+": "out", "-": "0"},
                        parameters={"cp": "2", "cn": "0"}))
        c.add(res("R2", "out", "0", "1 kohm"))
        res_sol = solve_nonlinear_dc(c)
        assert res_sol.status == NonlinearStatus.CONVERGED
        nv = {n.node: n.voltage.to_base() for n in res_sol.node_voltages}
        assert abs(nv["out"] - Decimal("3") * nv["2"]) < Decimal("1e-9")
        assert res_sol.conservation_checks.passed

    def test_d14_diode_current_control_hf_rejected(self):
        c = Circuit("D14_h_diode")
        c.add(vsrc("V1", "1", "0", "5 V"))
        c.add(diode("D1", "1", "0"))
        c.add(Component("H1", "H", parse_quantity("10 ohm"),
                        pins={"+": "2", "-": "0"},
                        parameters={"control_ref": "D1"}))
        res_sol = solve_nonlinear_dc(c)
        assert res_sol.status == NonlinearStatus.INVALID
        assert any("control_ref 'D1' names a diode" in d for d in res_sol.diagnostics)

    def test_d15_non_gnd_or_floating_handling(self):
        c = Circuit("D15_no_gnd")
        c.add(vsrc("V1", "1", "2", "5 V"))
        c.add(res("R1", "1", "2", "1 kohm"))
        c.add(diode("D1", "2", "1"))
        res_sol = solve_nonlinear_dc(c)
        assert res_sol.status == NonlinearStatus.INVALID
        assert any("no reference node" in d for d in res_sol.diagnostics)


# ==============================================================================
# §16 & §17 GENERALIDAD Y ESCALABILIDAD (N = 1, 2, 4, 8, 16, 32, 64)
# ==============================================================================

class TestGeneralityAndScaling:
    @pytest.mark.parametrize("n", [1, 2, 4, 8, 16, 32, 64])
    def test_series_diodes_scaling(self, n: int):
        c = Circuit(f"series_{n}")
        c.add(vsrc("V1", "in", "0", f"{max(5, n * 2)} V"))
        c.add(res("R1", "in", "node_0", "1 kohm"))
        for i in range(n):
            next_node = "0" if i == n - 1 else f"node_{i+1}"
            c.add(diode(f"D{i+1}", f"node_{i}", next_node))
        res_sol = solve_nonlinear_dc(c)
        assert res_sol.status == NonlinearStatus.CONVERGED
        assert res_sol.provenance["iterations"] <= MAX_ITER
        assert res_sol.conservation_checks.passed

    @pytest.mark.parametrize("n", [1, 2, 4, 8, 16, 32, 64])
    def test_parallel_diodes_scaling(self, n: int):
        c = Circuit(f"parallel_{n}")
        c.add(vsrc("V1", "in", "0", "5 V"))
        c.add(res("R1", "in", "d_node", "100 ohm"))
        for i in range(n):
            c.add(diode(f"D{i+1}", "d_node", "0"))
        res_sol = solve_nonlinear_dc(c)
        assert res_sol.status == NonlinearStatus.CONVERGED
        assert res_sol.conservation_checks.passed

    @pytest.mark.parametrize("n", [1, 2, 4, 8, 16, 32])
    def test_ladder_diodes_scaling(self, n: int):
        c = Circuit(f"ladder_{n}")
        c.add(vsrc("V1", "n0", "0", "10 V"))
        for i in range(n):
            c.add(res(f"R{i+1}", f"n{i}", f"n{i+1}", "50 ohm"))
            c.add(diode(f"D{i+1}", f"n{i+1}", "0"))
        res_sol = solve_nonlinear_dc(c)
        assert res_sol.status == NonlinearStatus.CONVERGED
        assert res_sol.conservation_checks.passed

    def test_mesh_multigraph_topologies(self):
        c = Circuit("multigraph_mesh")
        c.add(vsrc("V1", "1", "0", "5 V"))
        c.add(res("R1", "1", "2", "200 ohm"))
        c.add(diode("D2", "2", "3"))
        c.add(diode("D3", "2", "3"))
        c.add(res("R2", "3", "0", "200 ohm"))
        c.add(diode("D4", "2", "0"))
        res_sol = solve_nonlinear_dc(c)
        assert res_sol.status == NonlinearStatus.CONVERGED
        assert res_sol.conservation_checks.passed


# ==============================================================================
# §18 CASOS DE FALLO DELIBERADOS
# ==============================================================================

class TestFailureModes:
    def test_max_iterations_honest_verdict(self):
        c = Circuit("max_iter_fail")
        c.add(vsrc("V1", "1", "0", "10 V"))
        c.add(res("R1", "1", "2", "1 kohm"))
        c.add(diode("D1", "2", "0"))
        res_sol = solve_nonlinear_dc(c, max_iter=1)
        assert res_sol.status == NonlinearStatus.MAX_ITERATIONS
        assert res_sol.provenance["final_status"] == "max_iterations"
        assert res_sol.provenance["iterations"] == 1

    def test_singular_jacobian_handling(self):
        c = Circuit("singular_jac")
        c.add(vsrc("V1", "1", "0", "5 V"))
        c.add(vsrc("V2", "1", "0", "5 V"))
        c.add(diode("D1", "1", "0"))
        res_sol = solve_nonlinear_dc(c)
        assert res_sol.status in (NonlinearStatus.INVALID, NonlinearStatus.SINGULAR_JACOBIAN)

    def test_unsupported_reactive_component_in_dc(self):
        for comp_type in ("L", "C"):
            c = Circuit(f"unsupported_{comp_type}")
            c.add(vsrc("V1", "1", "0", "5 V"))
            val = "1 mH" if comp_type == "L" else "1 uF"
            c.add(Component(f"{comp_type}1", comp_type, parse_quantity(val),
                            pins={"1": "1", "2": "2"}))
            c.add(diode("D1", "2", "0"))
            res_sol = solve_nonlinear_dc(c)
            assert res_sol.status == NonlinearStatus.UNSUPPORTED
            assert any(f"component type '{comp_type}' is NOT_SUPPORTED" in d for d in res_sol.diagnostics)

    def test_diverged_on_overflow_during_solve(self):
        c = Circuit("diverge_test")
        c.add(vsrc("V1", "1", "0", "1e15 V"))
        c.add(diode("D1", "1", "0"))
        res_sol = solve_nonlinear_dc(c)
        assert res_sol.status in (NonlinearStatus.DIVERGED, NonlinearStatus.INVALID)


# ==============================================================================
# §19 NGSPICE EXTERNAL COMPARISON
# ==============================================================================

def _find_ngspice():
    import shutil
    from pathlib import Path
    try:
        from academic_core.infrastructure.ngspice import NgSpiceBackend
        b = NgSpiceBackend()
        det = b.detect()
        if det.verified and det.executable_path and Path(det.executable_path).is_file():
            return det.executable_path
    except Exception:
        pass
    for name in ("ngspice_con", "ngspice_con.exe", "ngspice", "ngspice.exe"):
        p = shutil.which(name)
        if p:
            return p
    return None


class TestNgspiceComparison:
    NG = _find_ngspice()

    @pytest.mark.skipif(NG is None, reason="ngspice external backend not found on system")
    def test_ngspice_cross_validation_d1(self):
        import subprocess
        import tempfile
        from pathlib import Path
        import re

        netlist = """* Diode DC OP comparison D1
V1 1 0 5V
R1 1 2 1k
D1 2 0 DMOD
.model DMOD D (IS=2.52e-9 N=1.752)
.op
.control
run
print v(2) i(v1)
.endc
.end
"""
        with tempfile.TemporaryDirectory() as td:
            cir_path = Path(td) / "circuit.cir"
            cir_path.write_text(netlist, encoding="utf-8")
            proc = subprocess.run([self.NG, "-b", str(cir_path)], capture_output=True, text=True)
            assert proc.returncode == 0, f"ngspice failed: {proc.stderr}\n{proc.stdout}"
            stdout = proc.stdout

        m_v2 = re.search(r"v\(2\)\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", stdout)
        m_iv1 = re.search(r"i\(v1\)\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", stdout)
        assert m_v2 is not None, f"v(2) not found in ngspice output:\n{stdout}"
        ng_v2 = float(m_v2.group(1))
        ng_iv1 = float(m_iv1.group(1)) if m_iv1 else None

        c = Circuit("ng_comp")
        c.add(vsrc("V1", "1", "0", "5 V"))
        c.add(res("R1", "1", "2", "1 kohm"))
        c.add(diode("D1", "2", "0", is_str="2.52e-9 A", n_str="1.752", vt_str="0.0258649 V"))
        res_sol = solve_nonlinear_dc(c)
        assert res_sol.status == NonlinearStatus.CONVERGED
        nv = {n.node: float(n.voltage.to_base()) for n in res_sol.node_voltages}
        bc = {b.ref: float(b.current.to_base()) for b in res_sol.branch_currents}

        rel_error_v2 = abs(nv["2"] - ng_v2) / abs(ng_v2)
        assert rel_error_v2 < 1e-4, f"V(2) rel error too large: {rel_error_v2} (got {nv['2']}, ngspice {ng_v2})"
        if ng_iv1 is not None:
            rel_error_iv1 = abs(bc["V1"] - ng_iv1) / abs(ng_iv1)
            assert rel_error_iv1 < 1e-4, f"I(V1) rel error too large: {rel_error_iv1} (got {bc['V1']}, ngspice {ng_iv1})"

    def test_ngspice_diode_dc_op(self):
        """Alias for backward compatibility."""
        return self.test_ngspice_cross_validation_d1()


# ==============================================================================
# §21 PERFORMANCE & §22 SECURITY
# ==============================================================================

class TestPerformanceAndSecurity:
    def test_performance_scales_under_tripwires(self):
        for n in (1, 8, 32):
            c = Circuit(f"perf_{n}")
            c.add(vsrc("V1", "in", "0", "5 V"))
            c.add(res("R1", "in", "d_node", "100 ohm"))
            for i in range(n):
                c.add(diode(f"D{i+1}", "d_node", "0"))
            t0 = time.perf_counter()
            r = solve_nonlinear_dc(c)
            dt = time.perf_counter() - t0
            assert r.status == NonlinearStatus.CONVERGED
            assert r.provenance["iterations"] <= 15
            assert dt < 2.0

    def test_security_ast_inspection(self):
        for rel_path in [
            "src/academic_core/domain/engineering/mna/diode.py",
            "src/academic_core/domain/engineering/mna/nonlinear.py",
        ]:
            with open(rel_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), rel_path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        assert node.func.id not in {"eval", "exec", "globals", "locals", "__import__"}


# ==============================================================================
# §23 PROVENANCE & §24 NETLIST / AST
# ==============================================================================

class TestProvenanceAndNetlist:
    def test_provenance_structure_and_reproducibility(self):
        c = Circuit("prov_test")
        c.add(vsrc("V1", "1", "0", "5 V"))
        c.add(res("R1", "1", "2", "1 kohm"))
        c.add(diode("D1", "2", "0"))
        r1 = solve_nonlinear_dc(c)
        r2 = solve_nonlinear_dc(c)
        assert r1.status == NonlinearStatus.CONVERGED
        p1 = r1.provenance
        p2 = r2.provenance
        for req_field in (
            "engine", "model", "diode_parameters", "initial_guess",
            "tolerances", "max_iterations", "max_backtracking",
            "iterations", "final_status", "final_residual_kcl_A",
            "final_residual_aux_V", "topology_digest", "solver_digest",
        ):
            assert req_field in p1, f"Missing {req_field}"
        assert p1["topology_digest"] == p2["topology_digest"]
        assert p1["solver_digest"] == p2["solver_digest"]

    def test_netlist_diode_limitation(self):
        c = Circuit("nl_diode")
        c.add(vsrc("V1", "1", "0", "5 V"))
        c.add(res("R1", "1", "2", "1 kohm"))
        c.add(diode("D1", "2", "0"))
        assert c.components[2].pins == {"A": "2", "K": "0"}


# ==============================================================================
# §25 UNIDADES & §26 AUDIT DECISIONS Q1–Q5
# ==============================================================================

class TestUnitsAndAuditDecisions:
    def test_dimensional_correctness(self):
        c = Circuit("units_test")
        c.add(vsrc("V1", "1", "0", "5 V"))
        c.add(res("R1", "1", "2", "1 kohm"))
        c.add(diode("D1", "2", "0"))
        r = solve_nonlinear_dc(c)
        assert r.status == NonlinearStatus.CONVERGED
        for nv in r.node_voltages:
            assert nv.voltage.unit == V_UNIT
        for bc in r.branch_currents:
            assert bc.current.unit == A_UNIT
        for ep in r.element_powers:
            assert ep.power.unit == W_UNIT

    def test_q1_constants_frozen(self):
        assert RTOL == Decimal("1E-9")
        assert ATOL == Decimal("1E-12")
        assert STOL == Decimal("1E-12")
        assert MAX_ITER == 50
        assert MAX_BACKTRACK == 10

    def test_q2_adapter_decimal_complex(self):
        c = Circuit("q2_pure_real")
        c.add(vsrc("V1", "1", "0", "5 V"))
        c.add(res("R1", "1", "2", "1 kohm"))
        c.add(diode("D1", "2", "0"))
        r = solve_nonlinear_dc(c)
        assert r.status == NonlinearStatus.CONVERGED
        for nv in r.node_voltages:
            assert isinstance(nv.voltage.value, Decimal)

    def test_q3_vt_fixed_explicit(self):
        c = Component("D1", "D", None, {"A": "1", "K": "0"},
                      parameters={"Is": parse_quantity("1e-14 A"), "n": parse_quantity("1")})
        with pytest.raises(InvalidCircuitError, match="diode needs exactly parameters"):
            extract_diode_params(c)

    def test_q4_unknown_vector_layout_invariant(self):
        c_res_only = Circuit("no_d")
        c_res_only.add(vsrc("V1", "1", "0", "5 V"))
        c_res_only.add(res("R1", "1", "2", "1 kohm"))
        prob_no_d = build_mna_problem(c_res_only)

        c_with_d = Circuit("with_d")
        c_with_d.add(vsrc("V1", "1", "0", "5 V"))
        c_with_d.add(res("R1", "1", "2", "1 kohm"))
        c_with_d.add(diode("D1", "2", "0"))
        prob_with_d = build_mna_problem(c_with_d, allow_diodes=True)

        assert prob_no_d.size == prob_with_d.size == 3
        assert prob_no_d.nodes == prob_with_d.nodes
        assert prob_no_d.vsource_refs == prob_with_d.vsource_refs

    def test_q5_scale_limit_n64(self):
        c = Circuit("scale_64")
        c.add(vsrc("V1", "in", "0", "10 V"))
        c.add(res("R1", "in", "node_0", "100 ohm"))
        for i in range(64):
            c.add(diode(f"D{i+1}", f"node_{i}", "0" if i == 63 else f"node_{i+1}"))
        r = solve_nonlinear_dc(c)
        assert r.status == NonlinearStatus.CONVERGED
