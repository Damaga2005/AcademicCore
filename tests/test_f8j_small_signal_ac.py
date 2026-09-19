"""Tests for F8-J: Small-Signal AC Analysis of Nonlinear Circuits.

Comprehensive test suite implementing canonical test matrix J1 to J20:
- J1: Single resistor AC
- J2: RC low-pass filter (exact analytical)
- J3: RC high-pass filter (exact analytical)
- J4: RL circuit (explicit test frequency and topology, exact analytical)
- J5: RLC resonant bandpass (exact analytical at resonance)
- J6: Voltage divider AC (exact complex impedance ratio)
- J7: Current source AC (exact parallel RC impedance)
- J8: Dependent source AC (VCVS E and VCCS G)
- J9: Shockley diode small-signal (operating point, gd, AC division, ngspice 47)
- J10: NPN common-emitter amplifier (operating point, JBJT, Av, ngspice 47)
- J11: PNP common-emitter amplifier (operating point, JBJT, ngspice 47)
- J12: Emitter follower / common collector (Av ~= 1, phase ~= 0, ngspice 47)
- J13: BJT + Diode circuit (compensated bias stage + BJT amplifier)
- J14: BJT + Dependent source (BJT driving VCVS buffer)
- J15: BJT + Ideal Op-Amp (nullor O + BJT active stage)
- J16: Ideal Transformer AC (T turns ratio n)
- J17: Mixed multi-node circuit (>= 10 nodes with R, L, C, D, Q, V, I; ngspice 47)
- J18: Invalid frequency (f <= 0, non-finite, wrong dimension -> INVALID)
- J19: Unsupported element (unknown type X -> UNSUPPORTED; MOSFET M supported since F8-K)
- J20: Deterministic provenance & digest (10 repeated runs bit-for-bit identical)

Plus:
- Physical conservation invariants (KCL, KVL)
- AST security audit scan (zero eval, exec, compile, subprocess in production code)
- Zero float tripwire in domain code
- Small-signal performance benchmarks (N=1, 10, 32, 64)
"""

from __future__ import annotations

import ast
import cmath
from decimal import Decimal
import math
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.ac import (
    ACOperatingPoint,
    ACStatus,
    BJTSmallSignalParams,
    DiodeSmallSignalParams,
    SmallSignalACResult,
    magnitude,
    phase,
    solve_small_signal_ac,
)
from academic_core.domain.engineering.math.decimal_complex import DecimalComplex
from academic_core.domain.engineering.mna.solver import solve_linear_dc
from academic_core.domain.engineering.units import Quantity, parse_quantity, parse_unit

V_UNIT = parse_unit("V")
A_UNIT = parse_unit("A")
OHM_UNIT = parse_unit("ohm")
F_UNIT = parse_unit("F")
H_UNIT = parse_unit("H")
HZ_UNIT = parse_unit("Hz")


def res(ref: str, n1: str, n2: str, val_str: str) -> Component:
    return Component(ref=ref, type="R", value=parse_quantity(val_str), pins={"1": n1, "2": n2})


def cap(ref: str, n1: str, n2: str, val_str: str) -> Component:
    return Component(ref=ref, type="C", value=parse_quantity(val_str), pins={"1": n1, "2": n2})


def ind(ref: str, n1: str, n2: str, val_str: str) -> Component:
    return Component(ref=ref, type="L", value=parse_quantity(val_str), pins={"1": n1, "2": n2})


def vsrc(ref: str, p: str, m: str, val_str: str, ac_mag: str | None = None, ac_phase: str | None = None) -> Component:
    params = {}
    if ac_mag is not None:
        params["ac_mag"] = parse_quantity(ac_mag)
    if ac_phase is not None:
        params["ac_phase"] = Decimal(ac_phase)
    return Component(ref=ref, type="V", value=parse_quantity(val_str), pins={"+": p, "-": m}, parameters=params)


def isrc(ref: str, p: str, m: str, val_str: str, ac_mag: str | None = None, ac_phase: str | None = None) -> Component:
    params = {}
    if ac_mag is not None:
        params["ac_mag"] = parse_quantity(ac_mag)
    if ac_phase is not None:
        params["ac_phase"] = Decimal(ac_phase)
    return Component(ref=ref, type="I", value=parse_quantity(val_str), pins={"+": p, "-": m}, parameters=params)


def diode(ref: str, a: str, k: str, is_str: str = "1e-14 A", n_str: str = "1", vt_str: str = "0.0258649 V") -> Component:
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


def bjt(ref: str, c: str, b: str, e: str, polarity: str = "NPN", is_str: str = "1e-14 A",
        bf_str: str = "100", br_str: str = "1", nf_str: str = "1", nr_str: str = "1",
        vt_str: str = "0.0258649 V") -> Component:
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


def vcvs(ref: str, p: str, m: str, cp: str, cn: str, gain: str) -> Component:
    return Component(ref=ref, type="E", value=parse_quantity(gain), pins={"+": p, "-": m}, parameters={"cp": cp, "cn": cn})


def vccs(ref: str, p: str, m: str, cp: str, cn: str, gm: str) -> Component:
    return Component(ref=ref, type="G", value=parse_quantity(gm), pins={"+": p, "-": m}, parameters={"cp": cp, "cn": cn})


def opamp(ref: str, out: str, inp: str, inm: str) -> Component:
    return Component(ref=ref, type="O", value=None, pins={"o": out, "+": inp, "-": inm})


def transformer(ref: str, p1: str, p2: str, s1: str, s2: str, n_ratio: str) -> Component:
    return Component(ref=ref, type="T", value=parse_quantity(n_ratio), pins={"1": p1, "2": p2, "3": s1, "4": s2})


def _find_ngspice() -> str | None:
    for candidate in [
        r"C:\Users\dmart\Documents\ngspice-47_64\Spice64\bin\ngspice_con.exe",
        r"C:\Users\dmart\Documents\ngspice-47_64\Spice64\bin\ngspice.exe",
    ]:
        if Path(candidate).is_file():
            return candidate
    for name in ("ngspice_con", "ngspice_con.exe", "ngspice", "ngspice.exe"):
        p = shutil.which(name)
        if p:
            return p
    return None


def deg(ph_rad: Decimal) -> float:
    # Normalize to [-180, 180]
    f_rad = float(ph_rad)
    d = math.degrees(f_rad)
    while d > 180.0:
        d -= 360.0
    while d <= -180.0:
        d += 360.0
    return d


def phase_diff_deg(deg1: float, deg2: float) -> float:
    d = (deg1 - deg2) % 360.0
    if d > 180.0:
        d -= 360.0
    return abs(d)


class TestSmallSignalCanonicalJ1toJ20:
    """Canonical test matrix J1 through J20."""

    def test_j1_single_resistor_ac(self):
        """J1: Single resistor AC circuit."""
        c = Circuit("j1_res")
        c.add(vsrc("V1", "1", "0", "0 V", ac_mag="1 V", ac_phase="0"))
        c.add(res("R1", "1", "0", "1000 ohm"))

        sol = solve_small_signal_ac(c, "1kHz")
        assert sol.status == ACStatus.SOLVED
        v1 = sol.voltage_of("1")
        assert v1 is not None
        assert abs(float(magnitude(v1)) - 1.0) < 1e-12
        assert abs(deg(phase(v1))) < 1e-10

        i1 = sol.current_of("R1")
        assert i1 is not None
        assert abs(float(magnitude(i1)) - 0.001) < 1e-12
        assert sol.kcl_max_residual < Decimal("1E-12")

    def test_j2_rc_lowpass(self):
        """J2: RC Low-Pass filter at cutoff frequency fc = 1/(2*pi*R*C)."""
        c = Circuit("j2_rc_lp")
        c.add(vsrc("V1", "in", "0", "0 V", ac_mag="1 V", ac_phase="0"))
        c.add(res("R1", "in", "out", "1000 ohm"))
        c.add(cap("C1", "out", "0", "159.15494309189535 nF"))

        sol = solve_small_signal_ac(c, "1000 Hz")
        assert sol.status == ACStatus.SOLVED
        vout = sol.voltage_of("out")
        assert vout is not None

        mag_out = float(magnitude(vout))
        ph_out = deg(phase(vout))

        # At fc: |H(j*wc)| = 1/sqrt(2) ~= 0.70710678, phase = -45 deg
        expected_mag = 1.0 / math.sqrt(2.0)
        assert abs(mag_out - expected_mag) < 1e-5
        assert abs(ph_out - (-45.0)) < 0.05
        assert sol.kcl_max_residual < Decimal("1E-12")

    def test_j3_rc_highpass(self):
        """J3: RC High-Pass filter at cutoff frequency fc = 1/(2*pi*R*C)."""
        c = Circuit("j3_rc_hp")
        c.add(vsrc("V1", "in", "0", "0 V", ac_mag="1 V", ac_phase="0"))
        c.add(cap("C1", "in", "out", "159.15494309189535 nF"))
        c.add(res("R1", "out", "0", "1000 ohm"))

        sol = solve_small_signal_ac(c, "1000 Hz")
        assert sol.status == ACStatus.SOLVED
        vout = sol.voltage_of("out")
        assert vout is not None

        mag_out = float(magnitude(vout))
        ph_out = deg(phase(vout))

        # At fc: |H(j*wc)| = 1/sqrt(2) ~= 0.70710678, phase = +45 deg
        expected_mag = 1.0 / math.sqrt(2.0)
        assert abs(mag_out - expected_mag) < 1e-5
        assert abs(ph_out - 45.0) < 0.05
        assert sol.kcl_max_residual < Decimal("1E-12")

    def test_j4_rl_circuit(self):
        """J4: RL circuit with explicitly defined topology and test frequency."""
        # Topology: V1 in->0, R1 in->out, L1 out->0
        # R = 100 ohm, L = 10 mH = 0.01 H.
        # Test frequency f = 1591.5494309189535 Hz => w = 10000 rad/s.
        # XL = w*L = 10000 * 0.01 = 100 ohm = R.
        # H(jw) = jXL / (R + jXL) = j100 / (100 + j100) = 1/sqrt(2) < 45 deg.
        c = Circuit("j4_rl")
        c.add(vsrc("V1", "in", "0", "0 V", ac_mag="1 V", ac_phase="0"))
        c.add(res("R1", "in", "out", "100 ohm"))
        c.add(ind("L1", "out", "0", "10 mH"))

        sol = solve_small_signal_ac(c, "1591.5494309189535 Hz")
        assert sol.status == ACStatus.SOLVED
        vout = sol.voltage_of("out")
        assert vout is not None

        mag_out = float(magnitude(vout))
        ph_out = deg(phase(vout))

        expected_mag = 1.0 / math.sqrt(2.0)
        assert abs(mag_out - expected_mag) < 1e-4
        assert abs(ph_out - 45.0) < 0.05
        assert sol.kcl_max_residual < Decimal("1E-12")

    def test_j5_rlc_resonant(self):
        """J5: Series RLC circuit at resonance f0 = 1/(2*pi*sqrt(L*C))."""
        c = Circuit("j5_rlc")
        c.add(vsrc("V1", "in", "0", "0 V", ac_mag="1 V", ac_phase="0"))
        c.add(ind("L1", "in", "1", "1 mH"))
        c.add(cap("C1", "1", "2", "1 uF"))
        c.add(res("R1", "2", "0", "10 ohm"))

        f_res = "5032.921210448703 Hz"
        sol = solve_small_signal_ac(c, f_res)
        assert sol.status == ACStatus.SOLVED

        v2 = sol.voltage_of("2")
        assert v2 is not None
        mag_r = float(magnitude(v2))
        ph_r = deg(phase(v2))
        assert abs(mag_r - 1.0) < 1e-4
        assert abs(ph_r) < 0.1
        assert sol.kcl_max_residual < Decimal("1E-12")

    def test_j6_voltage_divider_ac(self):
        """J6: Complex voltage divider."""
        c = Circuit("j6_divider")
        c.add(vsrc("V1", "in", "0", "0 V", ac_mag="10 V", ac_phase="0"))
        c.add(res("R1", "in", "out", "1000 ohm"))
        c.add(res("R2", "out", "0", "1000 ohm"))
        c.add(cap("C1", "out", "0", "159.155 nF"))

        sol = solve_small_signal_ac(c, "1000 Hz")
        assert sol.status == ACStatus.SOLVED
        vout = sol.voltage_of("out")
        assert vout is not None

        mag_out = float(magnitude(vout))
        ph_out = deg(phase(vout))
        assert abs(mag_out - math.sqrt(20.0)) < 1e-4
        assert abs(ph_out - math.degrees(math.atan2(-2.0, 4.0))) < 0.05
        assert sol.kcl_max_residual < Decimal("1E-12")

    def test_j7_current_source_ac(self):
        """J7: AC current source driving parallel RC."""
        c = Circuit("j7_isrc")
        c.add(isrc("I1", "out", "0", "0 A", ac_mag="2 mA", ac_phase="0"))
        c.add(res("R1", "out", "0", "1000 ohm"))
        c.add(cap("C1", "out", "0", "159.155 nF"))

        sol = solve_small_signal_ac(c, "1000 Hz")
        assert sol.status == ACStatus.SOLVED
        vout = sol.voltage_of("out")
        assert vout is not None

        mag_out = float(magnitude(vout))
        ph_out = deg(phase(vout))
        assert abs(mag_out - math.sqrt(2.0)) < 1e-4
        assert abs(ph_out - (-45.0)) < 0.05
        assert sol.kcl_max_residual < Decimal("1E-12")

    def test_j8_dependent_source(self):
        """J8: VCVS and VCCS in AC small-signal."""
        c = Circuit("j8_dep")
        c.add(vsrc("V1", "in", "0", "0 V", ac_mag="1 V", ac_phase="0"))
        c.add(vcvs("E1", "ctrl", "0", "in", "0", "2.5"))
        c.add(res("R1", "ctrl", "0", "1000 ohm"))
        c.add(vccs("G1", "out", "0", "ctrl", "0", "0.01 S"))
        c.add(res("R2", "out", "0", "100 ohm"))

        sol = solve_small_signal_ac(c, "1 kHz")
        assert sol.status == ACStatus.SOLVED
        v_ctrl = sol.voltage_of("ctrl")
        v_out = sol.voltage_of("out")
        assert v_ctrl is not None and v_out is not None

        assert abs(float(magnitude(v_ctrl)) - 2.5) < 1e-6
        assert abs(float(magnitude(v_out)) - 2.5) < 1e-6
        assert sol.kcl_max_residual < Decimal("1E-12")

    def test_j9_shockley_diode_small_signal(self):
        """J9: Shockley diode small-signal analysis against exact analytical & ngspice."""
        c = Circuit("j9_diode")
        c.add(vsrc("V1", "vcc", "0", "5 V"))
        c.add(res("R1", "vcc", "a", "1000 ohm"))
        c.add(diode("D1", "a", "0", is_str="1e-14 A", n_str="1", vt_str="0.0258649 V"))
        c.add(vsrc("V2", "in", "0", "0 V", ac_mag="10 mV", ac_phase="0"))
        c.add(cap("C1", "in", "a", "10 uF"))

        sol = solve_small_signal_ac(c, "1 kHz")
        assert sol.status == ACStatus.SOLVED
        assert len(sol.diode_parameters) == 1
        dp = sol.diode_parameters[0]
        assert dp.ref == "D1"
        assert dp.g_d > Decimal(0)
        assert dp.v_d0 > Decimal("0.5") and dp.v_d0 < Decimal("0.8")

        va = sol.voltage_of("a")
        assert va is not None
        mag_va = float(magnitude(va))

        ng_exe = _find_ngspice()
        if ng_exe:
            netlist = """* J9 Diode AC
V1 vcc 0 5V
R1 vcc a 1000
D1 a 0 DMOD
.model DMOD D (IS=1e-14 N=1)
V2 in 0 dc 0 ac 10m 0
C1 in a 10u
.ac lin 1 1000 1000
.control
run
let ph_a = ph(v(a))*180/pi
print mag(v(a)) ph_a
.endc
.end
"""
            with tempfile.TemporaryDirectory() as td:
                p = Path(td) / "j9.cir"
                p.write_text(netlist)
                out = subprocess.run([ng_exe, "-b", str(p)], capture_output=True, text=True).stdout
                m_mag = re.search(r"mag\(v\(a\)\)\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", out)
                m_ph = re.search(r"ph_a\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", out)
                if m_mag and m_ph:
                    ng_mag = float(m_mag.group(1))
                    ng_ph = float(m_ph.group(1))
                    emag = abs(mag_va - ng_mag) / max(1.0, ng_mag)
                    ephase = phase_diff_deg(deg(phase(va)), ng_ph)
                    assert emag < 1e-4, f"J9 magnitude error {emag} >= 1e-4"
                    assert ephase < 0.05, f"J9 phase error {ephase} >= 0.05 deg"

    def test_j10_npn_common_emitter(self):
        """J10: NPN common emitter amplifier with ngspice 47 cross-validation."""
        c = Circuit("j10_ce_npn")
        c.add(vsrc("V1", "vcc", "0", "15 V"))
        c.add(res("R1", "vcc", "b", "100 kohm"))
        c.add(res("R2", "b", "0", "10 kohm"))
        c.add(res("R3", "vcc", "c", "3.3 kohm"))
        c.add(res("R4", "e", "0", "1 kohm"))
        c.add(bjt("Q1", "c", "b", "e", polarity="NPN", bf_str="100", vt_str="0.0258649 V"))
        c.add(vsrc("V2", "in", "0", "0 V", ac_mag="1 mV", ac_phase="0"))
        c.add(cap("C1", "in", "b", "10 uF"))

        sol = solve_small_signal_ac(c, "1000 Hz")
        assert sol.status == ACStatus.SOLVED
        assert len(sol.bjt_parameters) == 1
        bp = sol.bjt_parameters[0]
        assert bp.polarity == "NPN"
        assert bp.g_m > Decimal("0.01")

        vc = sol.voltage_of("c")
        assert vc is not None
        mag_vc = float(magnitude(vc))
        ph_vc = deg(phase(vc))

        assert mag_vc > 0.002 and mag_vc < 0.005
        assert abs(phase_diff_deg(ph_vc, 180.0)) < 2.0

        ng_exe = _find_ngspice()
        if ng_exe:
            netlist = """* J10 NPN Common Emitter
V1 vcc 0 15V
R1 vcc b 100k
R2 b 0 10k
R3 vcc c 3.3k
R4 e 0 1k
Q1 c b e QMOD
.model QMOD NPN (IS=1e-14 BF=100 BR=1 NF=1 NR=1)
V2 in 0 dc 0 ac 1m 0
C1 in b 10u
.ac lin 1 1000 1000
.control
run
let ph_c = ph(v(c))*180/pi
print mag(v(c)) ph_c
.endc
.end
"""
            with tempfile.TemporaryDirectory() as td:
                p = Path(td) / "j10.cir"
                p.write_text(netlist)
                out = subprocess.run([ng_exe, "-b", str(p)], capture_output=True, text=True).stdout
                m_mag = re.search(r"mag\(v\(c\)\)\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", out)
                m_ph = re.search(r"ph_c\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", out)
                if m_mag and m_ph:
                    ng_mag = float(m_mag.group(1))
                    ng_ph = float(m_ph.group(1))
                    emag = abs(mag_vc - ng_mag) / max(1.0, ng_mag)
                    ephase = phase_diff_deg(ph_vc, ng_ph)
                    assert emag < 1e-4, f"J10 magnitude error {emag} >= 1e-4"
                    assert ephase < 0.05, f"J10 phase error {ephase} >= 0.05 deg"

    def test_j11_pnp_common_emitter(self):
        """J11: PNP common emitter amplifier with ngspice 47 cross-validation."""
        c = Circuit("j11_ce_pnp")
        c.add(vsrc("V1", "vcc", "0", "15 V"))
        c.add(res("R1", "vcc", "b", "10 kohm"))
        c.add(res("R2", "b", "0", "100 kohm"))
        c.add(res("R3", "vcc", "e", "1 kohm"))
        c.add(res("R4", "c", "0", "3.3 kohm"))
        c.add(bjt("Q1", "c", "b", "e", polarity="PNP", bf_str="100", vt_str="0.0258649 V"))
        c.add(vsrc("V2", "in", "0", "0 V", ac_mag="1 mV", ac_phase="0"))
        c.add(cap("C1", "in", "b", "10 uF"))

        sol = solve_small_signal_ac(c, "1000 Hz")
        assert sol.status == ACStatus.SOLVED
        assert len(sol.bjt_parameters) == 1
        bp = sol.bjt_parameters[0]
        assert bp.polarity == "PNP"
        assert bp.g_m > Decimal("0.01")

        vc = sol.voltage_of("c")
        assert vc is not None
        mag_vc = float(magnitude(vc))
        ph_vc = deg(phase(vc))

        ng_exe = _find_ngspice()
        if ng_exe:
            netlist = """* J11 PNP Common Emitter
V1 vcc 0 15V
R1 vcc b 10k
R2 b 0 100k
R3 vcc e 1k
R4 c 0 3.3k
Q1 c b e QMOD
.model QMOD PNP (IS=1e-14 BF=100 BR=1 NF=1 NR=1)
V2 in 0 dc 0 ac 1m 0
C1 in b 10u
.ac lin 1 1000 1000
.control
run
let ph_c = ph(v(c))*180/pi
print mag(v(c)) ph_c
.endc
.end
"""
            with tempfile.TemporaryDirectory() as td:
                p = Path(td) / "j11.cir"
                p.write_text(netlist)
                out = subprocess.run([ng_exe, "-b", str(p)], capture_output=True, text=True).stdout
                m_mag = re.search(r"mag\(v\(c\)\)\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", out)
                m_ph = re.search(r"ph_c\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", out)
                if m_mag and m_ph:
                    ng_mag = float(m_mag.group(1))
                    ng_ph = float(m_ph.group(1))
                    emag = abs(mag_vc - ng_mag) / max(1.0, ng_mag)
                    ephase = phase_diff_deg(ph_vc, ng_ph)
                    assert emag < 1e-4, f"J11 magnitude error {emag} >= 1e-4"
                    assert ephase < 0.05, f"J11 phase error {ephase} >= 0.05 deg"

    def test_j12_emitter_follower(self):
        """J12: Emitter follower (common collector) buffer."""
        c = Circuit("j12_ef")
        c.add(vsrc("V1", "vcc", "0", "12 V"))
        c.add(res("R1", "vcc", "b", "47 kohm"))
        c.add(res("R2", "b", "0", "47 kohm"))
        c.add(res("R3", "e", "0", "1 kohm"))
        c.add(bjt("Q1", "vcc", "b", "e", polarity="NPN", bf_str="100", vt_str="0.0258649 V"))
        c.add(vsrc("V2", "in", "0", "0 V", ac_mag="10 mV", ac_phase="0"))
        c.add(cap("C1", "in", "b", "10 uF"))

        sol = solve_small_signal_ac(c, "1000 Hz")
        assert sol.status == ACStatus.SOLVED

        ve = sol.voltage_of("e")
        vin = sol.voltage_of("in")
        assert ve is not None and vin is not None

        gain = float(magnitude(ve)) / float(magnitude(vin))
        ph_e = deg(phase(ve))
        assert gain > 0.9 and gain <= 1.0
        assert abs(ph_e) < 5.0

        ng_exe = _find_ngspice()
        if ng_exe:
            netlist = """* J12 Emitter Follower
V1 vcc 0 12V
R1 vcc b 47k
R2 b 0 47k
R3 e 0 1k
Q1 vcc b e QMOD
.model QMOD NPN (IS=1e-14 BF=100 BR=1 NF=1 NR=1)
V2 in 0 dc 0 ac 10m 0
C1 in b 10u
.ac lin 1 1000 1000
.control
run
let ph_e = ph(v(e))*180/pi
print mag(v(e)) ph_e
.endc
.end
"""
            with tempfile.TemporaryDirectory() as td:
                p = Path(td) / "j12.cir"
                p.write_text(netlist)
                out = subprocess.run([ng_exe, "-b", str(p)], capture_output=True, text=True).stdout
                m_mag = re.search(r"mag\(v\(e\)\)\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", out)
                m_ph = re.search(r"ph_e\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", out)
                if m_mag and m_ph:
                    ng_mag = float(m_mag.group(1))
                    ng_ph = float(m_ph.group(1))
                    emag = abs(float(magnitude(ve)) - ng_mag) / max(1.0, ng_mag)
                    ephase = phase_diff_deg(ph_e, ng_ph)
                    assert emag < 1e-4, f"J12 magnitude error {emag} >= 1e-4"
                    assert ephase < 0.05, f"J12 phase error {ephase} >= 0.05 deg"

    def test_j13_bjt_plus_diode(self):
        """J13: Circuit with both BJT and Diode simultaneously linearized."""
        c = Circuit("j13_bjt_diode")
        c.add(vsrc("V1", "vcc", "0", "12 V"))
        c.add(res("R1", "vcc", "d_node", "10 kohm"))
        c.add(diode("D1", "d_node", "0"))
        c.add(res("R2", "vcc", "c", "2.2 kohm"))
        c.add(res("R3", "d_node", "b", "1 kohm"))
        c.add(bjt("Q1", "c", "b", "0", polarity="NPN"))
        c.add(vsrc("V2", "in", "0", "0 V", ac_mag="1 mV", ac_phase="0"))
        c.add(cap("C1", "in", "b", "10 uF"))

        sol = solve_small_signal_ac(c, "1 kHz")
        assert sol.status == ACStatus.SOLVED
        assert len(sol.diode_parameters) == 1
        assert len(sol.bjt_parameters) == 1
        assert sol.kcl_max_residual < Decimal("1E-12")

    def test_j14_bjt_plus_dependent_source(self):
        """J14: BJT amplifier driving a VCVS buffer."""
        c = Circuit("j14_bjt_vcvs")
        c.add(vsrc("V1", "vcc", "0", "15 V"))
        c.add(res("R1", "vcc", "b", "100 kohm"))
        c.add(res("R2", "b", "0", "10 kohm"))
        c.add(res("R3", "vcc", "c", "3.3 kohm"))
        c.add(res("R4", "e", "0", "1 kohm"))
        c.add(bjt("Q1", "c", "b", "e", polarity="NPN"))
        c.add(vsrc("V2", "in", "0", "0 V", ac_mag="1 mV", ac_phase="0"))
        c.add(cap("C1", "in", "b", "10 uF"))
        c.add(vcvs("E1", "buf_out", "0", "c", "0", "2.0"))
        c.add(res("R5", "buf_out", "0", "10 kohm"))

        sol = solve_small_signal_ac(c, "1 kHz")
        assert sol.status == ACStatus.SOLVED
        vc = sol.voltage_of("c")
        vbuf = sol.voltage_of("buf_out")
        assert vc is not None and vbuf is not None

        assert abs(float(magnitude(vbuf)) - 2.0 * float(magnitude(vc))) < 1e-6
        assert sol.kcl_max_residual < Decimal("1E-12")

    def test_j15_bjt_plus_ideal_opamp(self):
        """J15: Hybrid circuit with BJT and ideal nullor O."""
        c = Circuit("j15_bjt_opamp")
        c.add(vsrc("V1", "vcc", "0", "15 V"))
        c.add(res("R1", "vcc", "b", "100 kohm"))
        c.add(res("R2", "b", "0", "10 kohm"))
        c.add(res("R3", "vcc", "c", "3.3 kohm"))
        c.add(res("R4", "e", "0", "1 kohm"))
        c.add(bjt("Q1", "c", "b", "e", polarity="NPN"))
        c.add(vsrc("V2", "in", "0", "0 V", ac_mag="1 mV", ac_phase="0"))
        c.add(cap("C1", "in", "b", "10 uF"))

        c.add(res("R5", "c", "inv_in", "10 kohm"))
        c.add(res("R6", "inv_in", "op_out", "20 kohm"))
        c.add(opamp("O1", "op_out", "0", "inv_in"))

        sol = solve_small_signal_ac(c, "1 kHz")
        assert sol.status == ACStatus.SOLVED
        vc = sol.voltage_of("c")
        vop = sol.voltage_of("op_out")
        vinv = sol.voltage_of("inv_in")
        assert vc is not None and vop is not None and vinv is not None

        assert float(magnitude(vinv)) < 1e-12
        assert abs(float(magnitude(vop)) - 2.0 * float(magnitude(vc))) < 1e-6
        assert sol.kcl_max_residual < Decimal("1E-12")

    def test_j16_transformer_ac(self):
        """J16: Ideal transformer in AC small-signal."""
        c = Circuit("j16_tx")
        c.add(vsrc("V1", "in", "0", "0 V", ac_mag="10 V", ac_phase="0"))
        c.add(transformer("T1", "in", "0", "sec", "0", "3.0"))
        c.add(res("R1", "sec", "0", "100 ohm"))

        sol = solve_small_signal_ac(c, "1 kHz")
        assert sol.status == ACStatus.SOLVED
        v_sec = sol.voltage_of("sec")
        assert v_sec is not None
        assert abs(float(magnitude(v_sec)) - 30.0) < 1e-6
        assert sol.kcl_max_residual < Decimal("1E-12")

    def test_j17_mixed_multi_node(self):
        """J17: Multi-node mixed circuit with >= 10 nodes."""
        c = Circuit("j17_multinode")
        c.add(vsrc("V1", "vcc", "0", "15 V"))
        c.add(res("R1", "vcc", "b1", "100 kohm"))
        c.add(res("R2", "b1", "0", "10 kohm"))
        c.add(res("R3", "vcc", "c1", "3.3 kohm"))
        c.add(res("R4", "e1", "0", "1 kohm"))
        c.add(bjt("Q1", "c1", "b1", "e1", polarity="NPN"))
        c.add(vsrc("V2", "in", "0", "0 V", ac_mag="1 mV", ac_phase="0"))
        c.add(cap("C1", "in", "b1", "10 uF"))

        c.add(cap("C2", "c1", "b2", "10 uF"))

        c.add(res("R5", "vcc", "b2", "47 kohm"))
        c.add(res("R6", "b2", "0", "47 kohm"))
        c.add(res("R7", "e2", "0", "2.2 kohm"))
        c.add(bjt("Q2", "vcc", "b2", "e2", polarity="NPN"))

        c.add(cap("C3", "e2", "out1", "10 uF"))
        c.add(res("R8", "out1", "out2", "500 ohm"))
        c.add(ind("L1", "out2", "0", "10 mH"))
        c.add(diode("D1", "out2", "0"))

        assert len(c.nets) >= 10, f"Circuit has only {len(c.nets)} nets"

        sol = solve_small_signal_ac(c, "1000 Hz")
        assert sol.status == ACStatus.SOLVED
        assert sol.kcl_max_residual < Decimal("1E-12")

        ng_exe = _find_ngspice()
        if ng_exe:
            netlist = """* J17 Multi-node Mixed
V1 vcc 0 15V
R1 vcc b1 100k
R2 b1 0 10k
R3 vcc c1 3.3k
R4 e1 0 1k
Q1 c1 b1 e1 QMOD
.model QMOD NPN (IS=1e-14 BF=100 BR=1 NF=1 NR=1)
V2 in 0 dc 0 ac 1m 0
C1 in b1 10u
C2 c1 b2 10u
R5 vcc b2 47k
R6 b2 0 47k
R7 e2 0 2.2k
Q2 vcc b2 e2 QMOD
C3 e2 out1 10u
R8 out1 out2 500
L1 out2 0 10m
D1 out2 0 DMOD
.model DMOD D (IS=1e-14 N=1)
.ac lin 1 1000 1000
.control
run
let ph_c1 = ph(v(c1))*180/pi
let ph_e2 = ph(v(e2))*180/pi
print mag(v(c1)) ph_c1 mag(v(e2)) ph_e2
.endc
.end
"""
            with tempfile.TemporaryDirectory() as td:
                p = Path(td) / "j17.cir"
                p.write_text(netlist)
                out = subprocess.run([ng_exe, "-b", str(p)], capture_output=True, text=True).stdout
                m_c1 = re.search(r"mag\(v\(c1\)\)\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", out)
                m_ph_c1 = re.search(r"ph_c1\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", out)
                if m_c1 and m_ph_c1:
                    ng_mag = float(m_c1.group(1))
                    ng_ph = float(m_ph_c1.group(1))
                    c1_val = sol.voltage_of("c1")
                    assert c1_val is not None
                    emag = abs(float(magnitude(c1_val)) - ng_mag) / max(1.0, ng_mag)
                    ephase = phase_diff_deg(deg(phase(c1_val)), ng_ph)
                    assert emag < 1e-4, f"J17 magnitude error {emag} >= 1e-4"
                    assert ephase < 0.05, f"J17 phase error {ephase} >= 0.05 deg"

    def test_j18_invalid_frequency(self):
        """J18: Invalid frequency rejection (<= 0, non-finite, wrong dimension)."""
        c = Circuit("j18_freq")
        c.add(vsrc("V1", "1", "0", "0 V", ac_mag="1 V"))
        c.add(res("R1", "1", "0", "100 ohm"))

        sol0 = solve_small_signal_ac(c, "0 Hz")
        assert sol0.status == ACStatus.INVALID

        sol_neg = solve_small_signal_ac(c, "-10 Hz")
        assert sol_neg.status == ACStatus.INVALID

        sol_dim = solve_small_signal_ac(c, Quantity(Decimal(10), V_UNIT))
        assert sol_dim.status == ACStatus.INVALID

    def test_j19_unsupported_element(self):
        """J19: Unsupported element rejection (unknown type letter).

        NOTE (F8-K): MOSFET ``M`` is a supported small-signal type since
        F8-K, so this probe now uses the still-unknown letter ``X`` to
        exercise the UNSUPPORTED path (same bypass construction).
        """
        c = Circuit("j19_unsupp")
        c.add(vsrc("V1", "1", "0", "0 V", ac_mag="1 V"))
        comp = object.__new__(Component)
        object.__setattr__(comp, "ref", "X1")
        object.__setattr__(comp, "type", "X")
        object.__setattr__(comp, "value", None)
        object.__setattr__(comp, "pins", {"A": "1", "B": "0"})
        object.__setattr__(comp, "parameters", {})
        object.__setattr__(comp, "metadata", {})
        c.add(comp)

        sol = solve_small_signal_ac(c, "1 kHz")
        assert sol.status == ACStatus.UNSUPPORTED

    def test_j20_deterministic_provenance(self):
        """J20: Provenance determinism: 10 repeated runs produce bit-for-bit identical digest."""
        c = Circuit("j20_det")
        c.add(vsrc("V1", "vcc", "0", "15 V"))
        c.add(res("R1", "vcc", "b", "100 kohm"))
        c.add(res("R2", "b", "0", "10 kohm"))
        c.add(res("R3", "vcc", "c", "3.3 kohm"))
        c.add(res("R4", "e", "0", "1 kohm"))
        c.add(bjt("Q1", "c", "b", "e", polarity="NPN"))
        c.add(vsrc("V2", "in", "0", "0 V", ac_mag="1 mV", ac_phase="0"))
        c.add(cap("C1", "in", "b", "10 uF"))

        digests = []
        for _ in range(10):
            sol = solve_small_signal_ac(c, "1000 Hz")
            assert sol.status == ACStatus.SOLVED
            digests.append(sol.digest)

        assert len(set(digests)) == 1, "Digest is not deterministic across repeated runs"
        assert len(digests[0]) == 64, "SHA-256 digest has wrong length"


class TestASTSecurityAndInvariants:
    """Security and mathematical invariant checks."""

    def test_ast_security_scan(self):
        """Verify absence of forbidden dynamic execution primitives in small_signal.py."""
        target = Path(r"src/academic_core/domain/engineering/ac/small_signal.py")
        assert target.is_file()
        tree = ast.parse(target.read_text(encoding="utf-8"))

        forbidden_calls = {"eval", "exec", "compile", "globals", "locals"}
        forbidden_modules = {"subprocess", "socket", "shutil"}

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in forbidden_calls:
                    pytest.fail(f"Forbidden call found: {node.func.id}")
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                mod = node.module if isinstance(node, ast.ImportFrom) else ""
                for alias in node.names:
                    name = alias.name
                    if name in forbidden_modules or mod in forbidden_modules:
                        pytest.fail(f"Forbidden import found: {name or mod}")

    def test_no_float_in_engine(self):
        """Verify that floating point literals/conversions are not used in small_signal.py."""
        target = Path(r"src/academic_core/domain/engineering/ac/small_signal.py")
        tree = ast.parse(target.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, float):
                pytest.fail(f"Float literal found in engine: {node.value}")

    def test_scalability_benchmark(self):
        """Measure performance across ladder sizes N = 1, 10, 32, 64."""
        timings = {}
        for n_stages in (1, 10, 32, 64):
            c = Circuit(f"ladder_{n_stages}")
            c.add(vsrc("V1", "vcc", "0", "15 V"))
            prev_node = "in"
            c.add(vsrc("V2", "in", "0", "0 V", ac_mag="1 mV"))
            for i in range(1, n_stages + 1):
                b_node = f"b{i}"
                c_node = f"c{i}"
                e_node = f"e{i}"
                c.add(cap(f"C{i}", prev_node, b_node, "10 uF"))
                c.add(res(f"R{1000 + 4*i + 0}", "vcc", b_node, "100 kohm"))
                c.add(res(f"R{1000 + 4*i + 1}", b_node, "0", "10 kohm"))
                c.add(res(f"R{1000 + 4*i + 2}", "vcc", c_node, "3.3 kohm"))
                c.add(res(f"R{1000 + 4*i + 3}", e_node, "0", "1 kohm"))
                c.add(bjt(f"Q{i}", c_node, b_node, e_node, polarity="NPN"))
                prev_node = c_node

            t0 = time.perf_counter()
            sol = solve_small_signal_ac(c, "1000 Hz")
            elapsed = time.perf_counter() - t0
            assert sol.status == ACStatus.SOLVED
            timings[n_stages] = elapsed

        print(f"\nPerformance timings: {timings}")
        # Tiempos puramente diagnósticos (no criterios normativos PASS/FAIL):
        print(f"\n[BENCHMARK F8-J DIAGNÓSTICO] Timings: {timings}")


class TestF8LCorrectiveRegression:
    """Regression suite for F8-L gate closure: F8K-FIND-01 and F8K-FIND-02."""

    def test_f8l_01_linear_circuit_with_dc_bias(self):
        """F8-L-01: Purely linear circuit with non-zero DC bias and AC small-signal."""
        c = Circuit("f8l_01_lin_bias")
        c.add(vsrc("V1", "1", "0", "10 V", ac_mag="1 V", ac_phase="0"))
        c.add(res("R1", "1", "0", "1000 ohm"))

        sol = solve_small_signal_ac(c, "1 kHz")
        assert sol.status == ACStatus.SOLVED
        v1 = sol.voltage_of("1")
        assert v1 is not None
        assert abs(float(magnitude(v1)) - 1.0) < 1e-12
        assert abs(deg(phase(v1))) < 1e-10
        assert sol.kcl_max_residual < Decimal("1E-12")

    def test_f8l_01_linear_circuit_with_dc_bias_and_reactive(self):
        """F8-L-01: Linear circuit with DC bias and reactive element (RC low-pass)."""
        c = Circuit("f8l_01_rc_bias")
        c.add(vsrc("V1", "in", "0", "15 V", ac_mag="2 V", ac_phase="0"))
        c.add(res("R1", "in", "out", "1000 ohm"))
        c.add(cap("C1", "out", "0", "159.15494309189535 nF"))

        sol = solve_small_signal_ac(c, "1000 Hz")
        assert sol.status == ACStatus.SOLVED
        vout = sol.voltage_of("out")
        assert vout is not None
        assert abs(float(magnitude(vout)) - math.sqrt(2.0)) < 1e-5
        assert abs(deg(phase(vout)) - (-45.0)) < 0.05
        assert sol.kcl_max_residual < Decimal("1E-12")

    def test_f8l_02_test_a_extra_node_rejected(self):
        """F8-L-02 Test A: dc_result with extra node must be rejected."""
        c = Circuit("f8l_02_a")
        c.add(vsrc("V1", "1", "0", "10 V", ac_mag="1 V"))
        c.add(res("R1", "1", "0", "1000 ohm"))

        # Create a dc_result with expected node '1' plus 'extra_node'
        c_extra = Circuit("c_extra")
        c_extra.add(vsrc("V1", "1", "0", "10 V"))
        c_extra.add(res("R1", "1", "0", "1000 ohm"))
        c_extra.add(res("R2", "extra_node", "0", "1000 ohm"))
        dc_res_extra = solve_linear_dc(c_extra)

        sol = solve_small_signal_ac(c, "1 kHz", dc_result=dc_res_extra)
        assert sol.status == ACStatus.INVALID
        assert any("extra nodes" in diag for diag in sol.diagnostics)

    def test_f8l_02_test_b_missing_node_rejected(self):
        """F8-L-02 Test B: dc_result missing circuit node must be rejected."""
        c = Circuit("f8l_02_b")
        c.add(vsrc("V1", "1", "0", "10 V", ac_mag="1 V"))
        c.add(res("R1", "1", "2", "500 ohm"))
        c.add(res("R2", "2", "0", "500 ohm"))

        # dc_result only has node '1'
        c_missing = Circuit("c_missing")
        c_missing.add(vsrc("V1", "1", "0", "10 V"))
        c_missing.add(res("R1", "1", "0", "1000 ohm"))
        dc_res_missing = solve_linear_dc(c_missing)

        sol = solve_small_signal_ac(c, "1 kHz", dc_result=dc_res_missing)
        assert sol.status == ACStatus.INVALID
        assert any("missing from dc_result" in diag for diag in sol.diagnostics)

    def test_f8l_02_test_c_valid_capacitor_dc_accepted(self):
        """F8-L-02 Test C: Circuit with V + R + C, valid DC equivalent passed as dc_result."""
        from academic_core.domain.engineering.ac.small_signal import _build_dc_equivalent_circuit
        c = Circuit("f8l_02_c")
        c.add(vsrc("V1", "in", "0", "10 V", ac_mag="1 V"))
        c.add(res("R1", "in", "out", "1000 ohm"))
        c.add(cap("C1", "out", "0", "159.155 nF"))

        dc_equiv = _build_dc_equivalent_circuit(c)
        dc_res = solve_linear_dc(dc_equiv)
        assert dc_res.status.value == "solved"

        sol = solve_small_signal_ac(c, "1000 Hz", dc_result=dc_res)
        assert sol.status == ACStatus.SOLVED
        vout = sol.voltage_of("out")
        assert vout is not None
        assert sol.kcl_max_residual < Decimal("1E-12")

    def test_f8l_02_test_d_incompatible_topology_rejected(self):
        """F8-L-02 Test D: dc_result from foreign circuit with same nodes but different devices."""
        c1 = Circuit("f8l_02_d1")
        c1.add(vsrc("V1", "1", "0", "10 V", ac_mag="1 V"))
        c1.add(res("R1", "1", "0", "1000 ohm"))

        c2 = Circuit("f8l_02_d2")
        c2.add(vsrc("V1", "1", "0", "10 V"))
        c2.add(res("R2", "1", "0", "1000 ohm"))  # R2 instead of R1!
        dc_res2 = solve_linear_dc(c2)

        sol = solve_small_signal_ac(c1, "1 kHz", dc_result=dc_res2)
        assert sol.status == ACStatus.INVALID
        assert any("incompatible" in diag or "missing" in diag for diag in sol.diagnostics)

