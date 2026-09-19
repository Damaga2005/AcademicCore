"""Tests for F8-I: Nonlinear DC Operating Point with Bipolar Junction Transistor (BJT).

Comprehensive verification suite covering:
- B1-B15 canonical BJT circuits:
  * B1: NPN fixed bias (active forward)
  * B2: NPN self-bias / emitter resistor feedback
  * B3: NPN emitter follower (common collector)
  * B4: NPN common base
  * B5: PNP common emitter
  * B6: BJT saturation region
  * B7: BJT reverse active region
  * B8: Matched pair current mirror
  * B9: Differential pair
  * B10: Darlington pair
  * B11: Inverter / BJT switch (cutoff to saturation)
  * B12: BJT + Shockley diode
  * B13: BJT + dependent source (VCVS / VCCS)
  * B14: BJT + Op-Amp active circuit
  * B15: BJT + Ideal transformer
- Multi-BJT scalability (N = 1, 2, 4, 8, 16, 32, 64)
- ngspice 47 cross-validation (< 10^-4 relative error)
- Failure modes (SINGULAR_JACOBIAN, MAX_ITERATIONS, INVALID, UNSUPPORTED)
- Thevenin / Norton / Two-port rejection on BJT circuits
- Terminal current control rejection for H/F
- Conservation laws (KCL, KVL, Tellegen power balance)
- Provenance, system summary, and serialization
- AST security audit and float tripwires
"""

from __future__ import annotations

import ast
from decimal import Decimal
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.mna import (
    BJTParams,
    DiodeParams,
    NonlinearResult,
    NonlinearStatus,
    bjt_terminal_currents,
    build_mna_problem,
    extract_bjt_params,
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
)
from academic_core.domain.engineering.units import Quantity, parse_quantity, parse_unit

V_UNIT = parse_unit("V")
A_UNIT = parse_unit("A")
W_UNIT = parse_unit("W")


def bjt(ref: str, c: str, b: str, e: str,
        polarity: str = "NPN",
        is_str: str = "1e-14 A",
        bf_str: str = "100",
        br_str: str = "1",
        nf_str: str = "1",
        nr_str: str = "1",
        vt_str: str = "0.02585 V") -> Component:
    """Helper to construct a BJT Component."""
    return Component(
        ref=ref,
        type="Q",
        value=None,
        pins={"C": c, "B": b, "E": e},
        parameters={
            "polarity": polarity,
            "Is": parse_quantity(is_str),
            "Bf": parse_quantity(bf_str),
            "Br": parse_quantity(br_str),
            "Nf": parse_quantity(nf_str),
            "Nr": parse_quantity(nr_str),
            "Vt": parse_quantity(vt_str),
        },
    )


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


def vcvs(ref: str, p: str, m: str, cp: str, cn: str, gain: str) -> Component:
    return Component(ref=ref, type="E", value=parse_quantity(gain),
                     pins={"+": p, "-": m},
                     parameters={"cp": cp, "cn": cn})


def vccs(ref: str, p: str, m: str, cp: str, cn: str, gm: str) -> Component:
    return Component(ref=ref, type="G", value=parse_quantity(gm),
                     pins={"+": p, "-": m},
                     parameters={"cp": cp, "cn": cn})


def opamp(ref: str, noninv: str, inv: str, out: str) -> Component:
    return Component(ref=ref, type="O", value=None,
                     pins={"+": noninv, "-": inv, "o": out})


def transformer(ref: str, p1: str, p2: str, s1: str, s2: str, n_ratio: str) -> Component:
    return Component(ref=ref, type="T", value=parse_quantity(n_ratio),
                     pins={"1": p1, "2": p2, "3": s1, "4": s2})


def _find_ngspice() -> str | None:
    for candidate in [
        r"C:\Users\dmart\Documents\ngspice-47_64\Spice64\bin\ngspice_con.exe",
        r"C:\Users\dmart\Documents\ngspice-47_64\Spice64\bin\ngspice.exe",
    ]:
        if Path(candidate).is_file():
            return candidate
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


class TestCanonicalBJTCircuits:

    def test_b1_npn_fixed_bias(self):
        """B1: NPN fixed bias circuit in forward active region."""
        c = Circuit("b1_fixed_bias")
        c.add(vsrc("V1", "vcc", "0", "12 V"))
        c.add(res("R1", "vcc", "b", "220 kohm"))
        c.add(res("R2", "vcc", "c", "1 kohm"))
        c.add(bjt("Q1", "c", "b", "0", polarity="NPN", bf_str="100"))

        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        assert sol.conservation_checks.passed

        nv = {n.node: n.voltage.to_base() for n in sol.node_voltages}
        bc = {b.ref: b.current.to_base() for b in sol.branch_currents}

        assert Decimal("0.60") < nv["b"] < Decimal("0.80")
        assert nv["c"] > nv["b"]
        ib = bc["Q1:B"]
        ic = bc["Q1:C"]
        ie = bc["Q1:E"]
        assert ib > 0
        assert ic > 0
        assert ie < 0
        assert abs(ic + ib + ie) < Decimal("1e-12")
        apparent_beta = ic / ib
        assert Decimal(95) < apparent_beta < Decimal(105)

    def test_b2_npn_self_bias(self):
        """B2: Voltage divider / self-bias with emitter resistor."""
        c = Circuit("b2_self_bias")
        c.add(vsrc("V1", "vcc", "0", "15 V"))
        c.add(res("R1", "vcc", "b", "47 kohm"))
        c.add(res("R2", "b", "0", "10 kohm"))
        c.add(res("R3", "vcc", "c", "3.3 kohm"))
        c.add(res("R4", "e", "0", "1 kohm"))
        c.add(bjt("Q1", "c", "b", "e", polarity="NPN", bf_str="120"))

        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        assert sol.conservation_checks.passed

        nv = {n.node: n.voltage.to_base() for n in sol.node_voltages}
        assert Decimal("1.8") < nv["b"] < Decimal("2.8")
        assert Decimal("1.2") < nv["e"] < Decimal("2.2")
        assert nv["c"] > nv["b"]

    def test_b3_npn_emitter_follower(self):
        """B3: Emitter follower (common collector)."""
        c = Circuit("b3_emitter_follower")
        c.add(vsrc("V1", "vcc", "0", "10 V"))
        c.add(vsrc("V2", "in", "0", "4 V"))
        c.add(res("R1", "in", "b", "1 kohm"))
        c.add(res("R2", "e", "0", "1 kohm"))
        c.add(bjt("Q1", "vcc", "b", "e", polarity="NPN", bf_str="100"))

        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        assert sol.conservation_checks.passed

        nv = {n.node: n.voltage.to_base() for n in sol.node_voltages}
        assert Decimal("3.0") < nv["e"] < Decimal("3.5")
        assert Decimal("3.7") < nv["b"] < Decimal("4.1")

    def test_b4_npn_common_base(self):
        """B4: Common base configuration with dual rail supplies."""
        c = Circuit("b4_common_base")
        c.add(vsrc("V1", "vcc", "0", "10 V"))
        c.add(vsrc("V2", "0", "vee", "5 V"))
        c.add(res("R1", "e", "vee", "1 kohm"))
        c.add(res("R2", "vcc", "c", "1.5 kohm"))
        c.add(bjt("Q1", "c", "0", "e", polarity="NPN", bf_str="100"))

        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        assert sol.conservation_checks.passed

        nv = {n.node: n.voltage.to_base() for n in sol.node_voltages}
        assert Decimal("-0.8") < nv["e"] < Decimal("-0.6")
        assert nv["c"] > Decimal("0")

    def test_b5_pnp_common_emitter(self):
        """B5: PNP transistor common emitter amplifier."""
        c = Circuit("b5_pnp_ce")
        c.add(vsrc("V1", "vcc", "0", "10 V"))
        c.add(res("R1", "b", "0", "100 kohm"))
        c.add(res("R2", "c", "0", "500 ohm"))
        c.add(bjt("Q1", "c", "b", "vcc", polarity="PNP", bf_str="80"))

        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        assert sol.conservation_checks.passed

        nv = {n.node: n.voltage.to_base() for n in sol.node_voltages}
        bc = {b.ref: b.current.to_base() for b in sol.branch_currents}

        assert Decimal("9.1") < nv["b"] < Decimal("9.5")
        assert Decimal("0.5") < nv["c"] < nv["b"]
        assert bc["Q1:B"] < 0
        assert bc["Q1:C"] < 0
        assert bc["Q1:E"] > 0
        assert abs(bc["Q1:B"] + bc["Q1:C"] + bc["Q1:E"]) < Decimal("1e-12")

    def test_b6_npn_saturation(self):
        """B6: BJT driven deeply into saturation."""
        c = Circuit("b6_saturation")
        c.add(vsrc("V1", "vcc", "0", "5 V"))
        c.add(res("R1", "vcc", "b", "10 kohm"))
        c.add(res("R2", "vcc", "c", "1 kohm"))
        c.add(bjt("Q1", "c", "b", "0", polarity="NPN", bf_str="100", br_str="1"))

        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        assert sol.conservation_checks.passed

        nv = {n.node: n.voltage.to_base() for n in sol.node_voltages}
        assert nv["b"] > nv["c"]
        vce = nv["c"]
        assert Decimal("0.01") < vce < Decimal("0.35")

    def test_b7_npn_reverse_active(self):
        """B7: BJT operating in reverse active mode."""
        c = Circuit("b7_reverse_active")
        c.add(vsrc("V1", "b", "0", "0.7 V"))
        c.add(vsrc("V2", "e", "0", "5 V"))
        c.add(res("R1", "0", "c_node", "100 ohm"))
        c.add(bjt("Q1", "c_node", "b", "e", polarity="NPN", bf_str="100", br_str="5"))

        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        assert sol.conservation_checks.passed

        bc = {b.ref: b.current.to_base() for b in sol.branch_currents}
        assert bc["Q1:C"] < 0

    def test_b8_matched_pair_current_mirror(self):
        """B8: Two matched NPN transistors in a current mirror."""
        c = Circuit("b8_current_mirror")
        c.add(vsrc("V1", "vcc", "0", "10 V"))
        c.add(res("R1", "vcc", "ref", "10 kohm"))
        c.add(res("R2", "vcc", "out", "4.7 kohm"))
        c.add(bjt("Q1", "ref", "ref", "0", polarity="NPN", bf_str="100"))
        c.add(bjt("Q2", "out", "ref", "0", polarity="NPN", bf_str="100"))

        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        assert sol.conservation_checks.passed

        bc = {b.ref: b.current.to_base() for b in sol.branch_currents}
        ic1 = bc["Q1:C"]
        ic2 = bc["Q2:C"]
        ratio = ic2 / ic1
        assert Decimal("0.90") < ratio < Decimal("1.05")

    def test_b9_differential_pair(self):
        """B9: Differential pair with shared emitter tail resistor."""
        c = Circuit("b9_diff_pair")
        c.add(vsrc("V1", "vcc", "0", "12 V"))
        c.add(vsrc("V2", "0", "vee", "12 V"))
        c.add(res("R1", "vcc", "c1", "5 kohm"))
        c.add(res("R2", "vcc", "c2", "5 kohm"))
        c.add(res("R3", "tail", "vee", "10 kohm"))
        c.add(bjt("Q1", "c1", "0", "tail", polarity="NPN", bf_str="100"))
        c.add(bjt("Q2", "c2", "0", "tail", polarity="NPN", bf_str="100"))

        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        assert sol.conservation_checks.passed

        nv = {n.node: n.voltage.to_base() for n in sol.node_voltages}
        bc = {b.ref: b.current.to_base() for b in sol.branch_currents}

        assert abs(nv["c1"] - nv["c2"]) < Decimal("1e-6")
        assert abs(bc["Q1:C"] - bc["Q2:C"]) < Decimal("1e-9")

    def test_b10_darlington_pair(self):
        """B10: Darlington pair configuration."""
        c = Circuit("b10_darlington")
        c.add(vsrc("V1", "vcc", "0", "12 V"))
        c.add(vsrc("V2", "in", "0", "3 V"))
        c.add(res("R1", "in", "b1", "100 kohm"))
        c.add(res("R2", "e2", "0", "1 kohm"))
        c.add(bjt("Q1", "vcc", "b1", "b2", polarity="NPN", bf_str="50"))
        c.add(bjt("Q2", "vcc", "b2", "e2", polarity="NPN", bf_str="50"))

        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        assert sol.conservation_checks.passed

        nv = {n.node: n.voltage.to_base() for n in sol.node_voltages}
        vbe_total = nv["b1"] - nv["e2"]
        assert Decimal("1.2") < vbe_total < Decimal("1.6")

    def test_b11_inverter_switch(self):
        """B11: BJT inverter / switch testing cutoff and saturation."""
        c_off = Circuit("b11_off")
        c_off.add(vsrc("V1", "vcc", "0", "5 V"))
        c_off.add(vsrc("V2", "in", "0", "0 V"))
        c_off.add(res("R1", "in", "b", "10 kohm"))
        c_off.add(res("R2", "vcc", "out", "1 kohm"))
        c_off.add(bjt("Q1", "out", "b", "0", polarity="NPN", bf_str="100"))

        sol_off = solve_nonlinear_dc(c_off)
        assert sol_off.status == NonlinearStatus.CONVERGED
        nv_off = {n.node: n.voltage.to_base() for n in sol_off.node_voltages}
        assert nv_off["out"] > Decimal("4.99")

        c_on = Circuit("b11_on")
        c_on.add(vsrc("V1", "vcc", "0", "5 V"))
        c_on.add(vsrc("V2", "in", "0", "5 V"))
        c_on.add(res("R1", "in", "b", "10 kohm"))
        c_on.add(res("R2", "vcc", "out", "1 kohm"))
        c_on.add(bjt("Q1", "out", "b", "0", polarity="NPN", bf_str="100"))

        sol_on = solve_nonlinear_dc(c_on)
        assert sol_on.status == NonlinearStatus.CONVERGED
        nv_on = {n.node: n.voltage.to_base() for n in sol_on.node_voltages}
        assert nv_on["out"] < Decimal("0.3")

    def test_b12_bjt_and_diode(self):
        """B12: Circuit containing both BJT and Shockley diode."""
        c = Circuit("b12_bjt_diode")
        c.add(vsrc("V1", "vcc", "0", "10 V"))
        c.add(res("R1", "vcc", "d_anode", "5 kohm"))
        c.add(diode("D1", "d_anode", "b"))
        c.add(res("R2", "b", "0", "20 kohm"))
        c.add(res("R3", "vcc", "c", "2 kohm"))
        c.add(bjt("Q1", "c", "b", "0", polarity="NPN", bf_str="100"))

        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        assert sol.conservation_checks.passed

        assert "diode_parameters" in sol.provenance
        assert "D1" in sol.provenance["diode_parameters"]
        assert "bjt_parameters" in sol.provenance
        assert "Q1" in sol.provenance["bjt_parameters"]

    def test_b13_bjt_and_dependent_sources(self):
        """B13: BJT coupled with VCVS and VCCS."""
        c = Circuit("b13_dep_sources")
        c.add(vsrc("V1", "in", "0", "2 V"))
        c.add(vcvs("E1", "v1", "0", "in", "0", "2"))
        c.add(res("R1", "v1", "b", "50 kohm"))
        c.add(vsrc("V2", "vcc", "0", "12 V"))
        c.add(res("R2", "vcc", "c", "1 kohm"))
        c.add(bjt("Q1", "c", "b", "0", polarity="NPN", bf_str="80"))

        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        assert sol.conservation_checks.passed

        nv = {n.node: n.voltage.to_base() for n in sol.node_voltages}
        assert abs(nv["v1"] - Decimal("4.0")) < Decimal("1e-6")

    def test_b14_bjt_and_opamp(self):
        """B14: Op-Amp driving BJT in active current booster / regulator."""
        c = Circuit("b14_opamp_bjt")
        c.add(vsrc("V1", "vref", "0", "3 V"))
        c.add(vsrc("V2", "vcc", "0", "15 V"))
        c.add(opamp("O1", "vref", "e", "b"))
        c.add(bjt("Q1", "vcc", "b", "e", polarity="NPN", bf_str="100"))
        c.add(res("R1", "e", "0", "100 ohm"))
        c.add(res("R2", "b", "e", "1 kohm"))

        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        assert sol.conservation_checks.passed

        nv = {n.node: n.voltage.to_base() for n in sol.node_voltages}
        assert abs(nv["e"] - Decimal("3.0")) < Decimal("1e-5")
        assert Decimal("3.6") < nv["b"] < Decimal("3.9")

    def test_b15_bjt_and_ideal_transformer(self):
        """B15: Ideal transformer with BJT in DC operating point."""
        c = Circuit("b15_transformer_bjt")
        c.add(vsrc("V1", "vcc", "0", "10 V"))
        c.add(res("R1", "vcc", "b", "100 kohm"))
        c.add(bjt("Q1", "c", "b", "0", polarity="NPN", bf_str="100"))
        c.add(transformer("T1", "vcc", "c", "sec1", "0", "2"))
        c.add(res("R2", "sec1", "0", "1 kohm"))

        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        assert sol.conservation_checks.passed


class TestMultiBJTScale:

    @pytest.mark.parametrize("n", [1, 2, 4, 8, 16, 32, 64])
    def test_scaling_parallel_bjts(self, n: int):
        """N identical BJTs in parallel bias stages.

        Convergence and conservation are asserted; wall-clock is not
        (the historical dt<120 s tripwire was machine-specific, never a
        certification requirement — see GATE-F8I §8).
        """
        c = Circuit(f"bjt_scale_{n}")
        c.add(vsrc("V1", "vcc", "0", "12 V"))
        for i in range(n):
            b_node = f"b_{i}"
            c_node = f"c_{i}"
            c.add(res(f"R{2*i+1}", "vcc", b_node, "150 kohm"))
            c.add(res(f"R{2*i+2}", "vcc", c_node, "1.5 kohm"))
            c.add(bjt(f"Q{i+1}", c_node, b_node, "0", polarity="NPN", bf_str="100"))

        sol = solve_nonlinear_dc(c)

        assert sol.status == NonlinearStatus.CONVERGED
        assert sol.conservation_checks.passed
        assert sol.provenance["iterations"] <= 15

    @pytest.mark.parametrize("n", [1, 2, 4, 8, 16])
    def test_scaling_bjt_cascade(self, n: int):
        """N cascaded emitter follower stages."""
        c = Circuit(f"bjt_cascade_{n}")
        c.add(vsrc("V1", "vcc", "0", f"{max(12, n * 2)} V"))
        c.add(vsrc("V2", "node_0", "0", f"{n * 1.5} V"))
        for i in range(n):
            in_node = f"node_{i}"
            out_node = f"node_{i+1}"
            c.add(res(f"R{i+1}", out_node, "0", "2 kohm"))
            c.add(bjt(f"Q{i+1}", "vcc", in_node, out_node, polarity="NPN", bf_str="100"))

        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        assert sol.conservation_checks.passed


class TestNgspiceCrossValidation:
    NG = _find_ngspice()

    @pytest.mark.skipif(NG is None, reason="ngspice backend not found on system")
    def test_ngspice_b1_fixed_bias(self):
        """Cross-validate Circuit B1 with ngspice 47."""
        netlist = """* BJT DC OP comparison B1 Fixed Bias
V1 vcc 0 12V
R1 vcc b 220k
R2 vcc c 2.2k
Q1 c b 0 QMOD
.model QMOD NPN (IS=1e-14 BF=100 BR=1 NF=1 NR=1)
.op
.control
run
print v(b) v(c)
.endc
.end
"""
        with tempfile.TemporaryDirectory() as td:
            cir = Path(td) / "b1.cir"
            cir.write_text(netlist, encoding="utf-8")
            proc = subprocess.run([self.NG, "-b", str(cir)], capture_output=True, text=True)
            assert proc.returncode == 0, f"ngspice failed:\n{proc.stderr}\n{proc.stdout}"
            stdout = proc.stdout

        m_vb = re.search(r"v\(b\)\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", stdout)
        m_vc = re.search(r"v\(c\)\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", stdout)
        assert m_vb is not None and m_vc is not None
        ng_vb = float(m_vb.group(1))
        ng_vc = float(m_vc.group(1))

        c = Circuit("b1_ng")
        c.add(vsrc("V1", "vcc", "0", "12 V"))
        c.add(res("R1", "vcc", "b", "220 kohm"))
        c.add(res("R2", "vcc", "c", "2.2 kohm"))
        c.add(bjt("Q1", "c", "b", "0", polarity="NPN", bf_str="100", vt_str="0.0258649 V"))
        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED

        nv = {n.node: float(n.voltage.to_base()) for n in sol.node_voltages}
        rel_err_vb = abs(nv["b"] - ng_vb) / abs(ng_vb)
        rel_err_vc = abs(nv["c"] - ng_vc) / abs(ng_vc)

        assert rel_err_vb < 1e-4, f"V(b) rel error {rel_err_vb} (got {nv['b']}, ngspice {ng_vb})"
        assert rel_err_vc < 1e-4, f"V(c) rel error {rel_err_vc} (got {nv['c']}, ngspice {ng_vc})"

    @pytest.mark.skipif(NG is None, reason="ngspice backend not found on system")
    def test_ngspice_b2_self_bias(self):
        """Cross-validate Circuit B2 with ngspice 47."""
        netlist = """* BJT DC OP comparison B2 Self Bias
V1 vcc 0 15V
R1 vcc b 47k
R2 b 0 10k
R3 vcc c 3.3k
R4 e 0 1k
Q1 c b e QMOD
.model QMOD NPN (IS=1e-14 BF=120 BR=1 NF=1 NR=1)
.op
.control
run
print v(b) v(c) v(e)
.endc
.end
"""
        with tempfile.TemporaryDirectory() as td:
            cir = Path(td) / "b2.cir"
            cir.write_text(netlist, encoding="utf-8")
            proc = subprocess.run([self.NG, "-b", str(cir)], capture_output=True, text=True)
            assert proc.returncode == 0, f"ngspice failed:\n{proc.stderr}\n{proc.stdout}"
            stdout = proc.stdout

        m_vb = re.search(r"v\(b\)\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", stdout)
        m_vc = re.search(r"v\(c\)\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", stdout)
        m_ve = re.search(r"v\(e\)\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", stdout)
        assert m_vb and m_vc and m_ve
        ng_vb, ng_vc, ng_ve = float(m_vb.group(1)), float(m_vc.group(1)), float(m_ve.group(1))

        c = Circuit("b2_ng")
        c.add(vsrc("V1", "vcc", "0", "15 V"))
        c.add(res("R1", "vcc", "b", "47 kohm"))
        c.add(res("R2", "b", "0", "10 kohm"))
        c.add(res("R3", "vcc", "c", "3.3 kohm"))
        c.add(res("R4", "e", "0", "1 kohm"))
        c.add(bjt("Q1", "c", "b", "e", polarity="NPN", bf_str="120", vt_str="0.0258649 V"))
        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED

        nv = {n.node: float(n.voltage.to_base()) for n in sol.node_voltages}
        assert abs(nv["b"] - ng_vb) / abs(ng_vb) < 1e-4
        assert abs(nv["c"] - ng_vc) / abs(ng_vc) < 1e-4
        assert abs(nv["e"] - ng_ve) / abs(ng_ve) < 1e-4

    @pytest.mark.skipif(NG is None, reason="ngspice backend not found on system")
    def test_ngspice_b5_pnp_ce(self):
        """Cross-validate Circuit B5 (PNP) with ngspice 47."""
        netlist = """* BJT DC OP comparison B5 PNP
V1 vcc 0 10V
R1 b 0 100k
R2 c 0 2k
Q1 c b vcc QPMOD
.model QPMOD PNP (IS=1e-14 BF=80 BR=1 NF=1 NR=1)
.op
.control
run
print v(b) v(c)
.endc
.end
"""
        with tempfile.TemporaryDirectory() as td:
            cir = Path(td) / "b5.cir"
            cir.write_text(netlist, encoding="utf-8")
            proc = subprocess.run([self.NG, "-b", str(cir)], capture_output=True, text=True)
            assert proc.returncode == 0, f"ngspice failed:\n{proc.stderr}\n{proc.stdout}"
            stdout = proc.stdout

        m_vb = re.search(r"v\(b\)\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", stdout)
        m_vc = re.search(r"v\(c\)\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", stdout)
        assert m_vb and m_vc
        ng_vb, ng_vc = float(m_vb.group(1)), float(m_vc.group(1))

        c = Circuit("b5_ng")
        c.add(vsrc("V1", "vcc", "0", "10 V"))
        c.add(res("R1", "b", "0", "100 kohm"))
        c.add(res("R2", "c", "0", "2 kohm"))
        c.add(bjt("Q1", "c", "b", "vcc", polarity="PNP", bf_str="80", vt_str="0.0258649 V"))
        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED

        nv = {n.node: float(n.voltage.to_base()) for n in sol.node_voltages}
        assert abs(nv["b"] - ng_vb) / abs(ng_vb) < 1e-4
        assert abs(nv["c"] - ng_vc) / abs(ng_vc) < 1e-4


class TestFailureModesAndRejections:

    def test_singular_jacobian_handling(self):
        """Conflicting ideal voltage sources cause a singular Jacobian."""
        c = Circuit("singular_jac")
        c.add(vsrc("V1", "1", "0", "5 V"))
        c.add(vsrc("V2", "1", "0", "5 V"))
        c.add(bjt("Q1", "1", "0", "0", polarity="NPN"))

        sol = solve_nonlinear_dc(c)
        assert sol.status in (NonlinearStatus.SINGULAR_JACOBIAN, NonlinearStatus.INVALID)

    def test_open_base_cutoff(self):
        """Open base terminal safely converges to cutoff operating point."""
        c = Circuit("floating_base")
        c.add(vsrc("V1", "vcc", "0", "10 V"))
        c.add(res("R1", "vcc", "c", "1 kohm"))
        c.add(bjt("Q1", "c", "b", "0", polarity="NPN"))

        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        nv = {n.node: n.voltage.to_base() for n in sol.node_voltages}
        # In cutoff with open base, V_B = V_T * ln(1 + Bf/Br) ~ 0.119 V
        assert Decimal("0.10") < nv["b"] < Decimal("0.15")
        assert abs(nv["c"] - Decimal("10")) < Decimal("1e-3")

    def test_max_iterations_exceeded(self):
        """Budget exhausted returns MAX_ITERATIONS status."""
        c = Circuit("max_iter")
        c.add(vsrc("V1", "vcc", "0", "10 V"))
        c.add(res("R1", "vcc", "b", "100 kohm"))
        c.add(res("R2", "vcc", "c", "1 kohm"))
        c.add(bjt("Q1", "c", "b", "0", polarity="NPN"))

        sol = solve_nonlinear_dc(c, max_iter=1)
        assert sol.status == NonlinearStatus.MAX_ITERATIONS
        assert sol.provenance["iterations"] == 1

    def test_unsupported_reactive_component_in_dc(self):
        """L and C components in DC return UNSUPPORTED."""
        for ctype in ("L", "C"):
            c = Circuit(f"unsupported_{ctype}")
            c.add(vsrc("V1", "vcc", "0", "10 V"))
            val = "1 mH" if ctype == "L" else "1 uF"
            c.add(Component(f"{ctype}1", ctype, parse_quantity(val), pins={"1": "vcc", "2": "b"}))
            c.add(bjt("Q1", "vcc", "b", "0", polarity="NPN"))

            sol = solve_nonlinear_dc(c)
            assert sol.status == NonlinearStatus.UNSUPPORTED
            assert any(f"component type '{ctype}' is NOT_SUPPORTED" in d for d in sol.diagnostics)

    def test_thevenin_norton_rejects_bjt_circuit(self):
        """Linear reduction algorithms must reject circuits containing BJTs."""
        c = Circuit("bjt_thevenin")
        c.add(vsrc("V1", "vcc", "0", "10 V"))
        c.add(res("R1", "vcc", "c", "1 kohm"))
        c.add(bjt("Q1", "c", "b", "0", polarity="NPN"))

        with pytest.raises(UnsupportedElementError, match="NOT_SUPPORTED by the linear DC solver"):
            build_mna_problem(c)

    def test_hf_source_controlled_by_bjt_terminal_rejected(self):
        """Current-controlled sources (H, F) controlled by BJT terminal raise InvalidCircuitError or INVALID."""
        c = Circuit("hf_bjt_ctrl")
        c.add(vsrc("V1", "vcc", "0", "10 V"))
        c.add(bjt("Q1", "c", "b", "0", polarity="NPN"))
        c.add(Component("F1", "F", parse_quantity("2"), pins={"+": "c", "-": "0"},
                        parameters={"control_ref": "Q1"}))

        with pytest.raises(InvalidCircuitError, match="control by BJT is not supported"):
            build_mna_problem(c, allow_bjts=True)

        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.INVALID
        assert any("control by BJT is not supported" in d for d in sol.diagnostics)

    def test_invalid_bjt_parameters(self):
        """Invalid BJT parameters (e.g. negative Is or Bf) return INVALID."""
        c = Circuit("bad_bjt_params")
        c.add(vsrc("V1", "vcc", "0", "10 V"))
        c.add(res("R1", "vcc", "b", "100 kohm"))
        c.add(res("R2", "vcc", "c", "1 kohm"))
        c.add(bjt("Q1", "c", "b", "0", polarity="NPN", is_str="-1e-14 A"))

        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.INVALID


class TestConservationAndProvenance:

    def test_tellegen_power_balance_and_branch_currents(self):
        """Verify Tellegen power balance and branch currents for BJT."""
        c = Circuit("tellegen_bjt")
        c.add(vsrc("V1", "vcc", "0", "10 V"))
        c.add(res("R1", "vcc", "b", "100 kohm"))
        c.add(res("R2", "vcc", "c", "1 kohm"))
        c.add(bjt("Q1", "c", "b", "0", polarity="NPN", bf_str="100"))

        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        assert sol.conservation_checks.passed

        p_q1 = next(p for p in sol.element_powers if p.ref == "Q1")
        assert p_q1.absorbed
        assert p_q1.power.to_base() > 0

        bc_refs = {b.ref for b in sol.branch_currents}
        assert "Q1:C" in bc_refs
        assert "Q1:B" in bc_refs
        assert "Q1:E" in bc_refs

    def test_provenance_and_summary_serialization(self):
        """Provenance and summary serializability and reproducibility."""
        c = Circuit("prov_bjt")
        c.add(vsrc("V1", "vcc", "0", "10 V"))
        c.add(res("R1", "vcc", "b", "100 kohm"))
        c.add(res("R2", "vcc", "c", "1 kohm"))
        c.add(bjt("Q1", "c", "b", "0", polarity="NPN", bf_str="100"))

        r1 = solve_nonlinear_dc(c)
        r2 = solve_nonlinear_dc(c)

        assert r1.provenance["model"] == "Ebers-Moll"
        assert "Q1" in r1.provenance["bjt_parameters"]
        bp = r1.provenance["bjt_parameters"]["Q1"]
        assert bp["polarity"] == "NPN"
        assert bp["Bf"] == "100"

        assert r1.provenance["topology_digest"] == r2.provenance["topology_digest"]
        assert r1.provenance["solver_digest"] == r2.provenance["solver_digest"]

        assert "bjts" in r1.system_summary
        assert r1.system_summary["bjts"][0]["ref"] == "Q1"
        assert r1.system_summary["bjts"][0]["polarity"] == "NPN"

    def test_security_ast_inspection(self):
        """Audit source files for forbidden unsafe operations."""
        for rel in [
            "src/academic_core/domain/engineering/mna/bjt.py",
            "src/academic_core/domain/engineering/mna/nonlinear.py",
        ]:
            with open(rel, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), rel)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    assert node.func.id not in {"eval", "exec", "globals", "locals", "__import__"}

    def test_no_float_in_bjt_physics(self):
        """Ensure no float conversions exist in bjt.py physics calculation."""
        with open("src/academic_core/domain/engineering/mna/bjt.py", "r", encoding="utf-8") as f:
            content = f.read()
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "float", f"float() call found in bjt.py at line {node.lineno}"
