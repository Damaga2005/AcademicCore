"""Tests for F8-K: Additional semiconductors (MOSFET, JFET, diode kinds).

Coverage:
- Parameter validation (MOSFET/JFET/D-kind): presence, type, dimension,
  sign, finiteness, domain; zero silent defaults.
- Device physics: regions, boundaries, analytic currents, analytic
  derivatives vs central finite differences, companion equivalence,
  polarity symmetry, KCL per device.
- D-kind physics: Zener (forward/reverse/breakdown/continuity), LED,
  Schottky, photodiode (dark/illuminated).
- Circuit tests: minimal biased DC operating points per device/region.
- Mixed-device tests: D+M, D+J, M+Q, J+Q, M+J, M+D, Q+D.
- No-convergence tests: SINGULAR_JACOBIAN, MAX_ITERATIONS, INVALID,
  UNSUPPORTED (linear dispatch, Thevenin set, H/F control rejection).
- Boundary tests at derivative discontinuities.
- F8-J small-signal contract (gm/gds/gmb exposure, KCL, determinism).
- Determinism (repeated solves, insertion-order invariance).
- AST security + float-literal scans on new/edited engine files.
- Diagnostic benchmarks (no time asserts) for N = 1/10/32/64.
- ngspice 47 external cross-validation (skipped if binary absent).
"""

from __future__ import annotations

import ast
import subprocess
import tempfile
import time
from decimal import Decimal
from pathlib import Path

import pytest

from academic_core.domain.engineering.ac.small_signal import (
    solve_small_signal_ac,
)
from academic_core.domain.engineering.ac.solution import ACStatus
from academic_core.domain.engineering.circuit import (
    COMPONENT_PINS,
    Circuit,
    Component,
)
from academic_core.domain.engineering.math.trig import make_context
from academic_core.domain.engineering.mna import (
    NonlinearStatus,
    build_mna_problem,
    extract_diode_params,
    extract_diode_variant_params,
    extract_jfet_params,
    extract_mosfet_params,
    jfet_conductances,
    jfet_jacobian,
    jfet_region,
    jfet_terminal_currents,
    mos_conductances,
    mos_jacobian,
    mos_region,
    mos_terminal_currents,
    shockley_conductance,
    shockley_current,
    solve_linear_dc,
    solve_nonlinear_dc,
    variant_conductance,
    variant_current,
)
from academic_core.domain.engineering.mna.diode import (
    DiodeParams,
    DiodeVariantParams,
)
from academic_core.domain.engineering.mna.errors import (
    InvalidCircuitError,
    UnsupportedElementError,
)
from academic_core.domain.engineering.mna.jfet import JFETParams
from academic_core.domain.engineering.mna.mosfet import MOSParams
from academic_core.domain.engineering.mna.result import SolveStatus
from academic_core.domain.engineering.thevenin.port import (
    SUPPORTED_TYPES as THEVENIN_SUPPORTED,
)
from academic_core.domain.engineering.units import (
    Quantity,
    Unit,
    parse_quantity,
    parse_unit,
)

CTX = make_context()

V_UNIT = parse_unit("V")
A_UNIT = parse_unit("A")
KP_DIM = (-2, -4, 6, 3, 0, 0, 0)
LAM_DIM = (-1, -2, 3, 1, 0, 0, 0)
DIMLESS = (0, 0, 0, 0, 0, 0, 0)

NGSPICE_EXE = Path(
    r"C:\Users\dmart\Documents\ngspice-47_64\Spice64\bin\ngspice_con.exe")


def Q(text: str) -> Quantity:
    return parse_quantity(text)


def kp(qty: str) -> Quantity:
    return Quantity(Decimal(qty), Unit("A/V2", "A", "", KP_DIM, Decimal(1)))


def lam(qty: str) -> Quantity:
    return Quantity(Decimal(qty),
                    Unit("1/V", "V", "", LAM_DIM, Decimal(1)))


def gam(qty: str) -> Quantity:
    return Quantity(Decimal(qty),
                    Unit("1", "1", "", DIMLESS, Decimal(1)))


def dimless(qty: str) -> Quantity:
    return Quantity(Decimal(qty),
                    Unit("1", "1", "", DIMLESS, Decimal(1)))


def res(ref: str, n1: str, n2: str, value: str = "1 kohm") -> Component:
    return Component(ref, "R", Q(value), {"1": n1, "2": n2})


def vsrc(ref: str, np_: str, nm: str, value: str,
         **params) -> Component:
    return Component(ref, "V", Q(value), {"+": np_, "-": nm},
                     parameters=dict(params))


def mosfet(ref: str, d: str, g: str, s: str, b: str,
           polarity: str = "NMOS", kp_s: str = "0.0002",
           vto_s: str = "1 V", lam_s: str = "0.02",
           phi_s: str = "0.6 V", gam_s: str = "0.5") -> Component:
    return Component(ref, "M", None, {"D": d, "G": g, "S": s, "B": b},
                     parameters={"polarity": polarity, "Kp": kp(kp_s),
                                 "Vto": Q(vto_s), "Lambda": lam(lam_s),
                                 "Phi": Q(phi_s), "Gamma": gam(gam_s)})


def jfet(ref: str, d: str, g: str, s: str,
         polarity: str = "NCHAN", idss_s: str = "0.01 A",
         vp_s: str = "3 V", lam_s: str = "0.01") -> Component:
    return Component(ref, "J", None, {"D": d, "G": g, "S": s},
                     parameters={"polarity": polarity, "Idss": Q(idss_s),
                                 "Vp": Q(vp_s), "Lambda": lam(lam_s)})


def diode_kind(ref: str, a: str, k: str, kind: str,
               **over) -> Component:
    params: dict = {"kind": kind, "Is": Q("1e-14 A"), "n": Q("1"),
                    "Vt": Q("0.02585 V")}
    params.update(over)
    return Component(ref, "D", None, {"A": a, "K": k}, parameters=params)


def bjt(ref: str, c: str, b: str, e: str,
        polarity: str = "NPN") -> Component:
    return Component(ref, "Q", None, {"C": c, "B": b, "E": e},
                     parameters={"polarity": polarity, "Is": Q("1e-14 A"),
                                 "Bf": Q("100"), "Br": Q("1"),
                                 "Nf": Q("1"), "Nr": Q("1"),
                                 "Vt": Q("0.02585 V")})


def shockley_diode(ref: str, a: str, k: str) -> Component:
    return Component(ref, "D", None, {"A": a, "K": k},
                     parameters={"Is": Q("1e-14 A"), "n": Q("1"),
                                 "Vt": Q("0.02585 V")})


def node_v(sol, node: str) -> Decimal:
    for nv in sol.node_voltages:
        if nv.node == node:
            return nv.voltage.to_base()
    raise AssertionError(f"node {node} missing")


def std_mos_params(**kw) -> MOSParams:
    base = {"polarity": "NMOS", "Kp": Decimal("0.0002"),
            "Vto": Decimal(1), "Lambda": Decimal("0.02"),
            "Phi": Decimal("0.6"), "Gamma": Decimal("0.5")}
    base.update(kw)
    return MOSParams(**base)


def std_jfet_params(**kw) -> JFETParams:
    base = {"polarity": "NCHAN", "Idss": Decimal("0.01"),
            "Vp": Decimal(3), "Lambda": Decimal("0.01")}
    base.update(kw)
    return JFETParams(**base)


# --------------------------------------------------------------------------
# 1. Pinouts / dispatch surface
# --------------------------------------------------------------------------

class TestPinouts:
    def test_component_pins_m_j(self):
        assert COMPONENT_PINS["M"] == ("D", "G", "S", "B")
        assert COMPONENT_PINS["J"] == ("D", "G", "S")
        assert COMPONENT_PINS["Q"] == ("C", "B", "E")
        assert COMPONENT_PINS["D"] == ("A", "K")

    def test_linear_dispatch_rejects_m_j(self):
        c = Circuit("lin_m")
        c.add(vsrc("V1", "1", "0", "5 V"))
        c.add(res("R1", "1", "0"))
        c.add(mosfet("M1", "1", "1", "0", "0"))
        r = solve_linear_dc(c)
        assert r.status == SolveStatus.UNSUPPORTED
        with pytest.raises(UnsupportedElementError):
            build_mna_problem(c)

    def test_linear_dispatch_rejects_j(self):
        c = Circuit("lin_j")
        c.add(vsrc("V1", "1", "0", "5 V"))
        c.add(res("R1", "1", "0"))
        c.add(jfet("J1", "1", "1", "0"))
        r = solve_linear_dc(c)
        assert r.status == SolveStatus.UNSUPPORTED

    def test_linear_dispatch_rejects_d_kind(self):
        c = Circuit("lin_dk")
        c.add(vsrc("V1", "1", "0", "5 V"))
        c.add(res("R1", "1", "0"))
        c.add(diode_kind("D1", "1", "0", "ZENER", Vz=Q("5.1 V"),
                         nz=Q("1"), Iz=Q("1e-3 A")))
        r = solve_linear_dc(c)
        assert r.status == SolveStatus.UNSUPPORTED

    def test_thevenin_set_excludes_new_types(self):
        assert "M" not in THEVENIN_SUPPORTED
        assert "J" not in THEVENIN_SUPPORTED


# --------------------------------------------------------------------------
# 2. MOSFET parameter validation
# --------------------------------------------------------------------------

class TestMOSValidation:
    def test_valid_extract(self):
        p = extract_mosfet_params(mosfet("M1", "d", "g", "s", "b"))
        assert isinstance(p, MOSParams)
        assert p.polarity == "NMOS" and p.Kp == Decimal("0.0002")

    def test_pmos_extract(self):
        p = extract_mosfet_params(mosfet("M1", "d", "g", "s", "b",
                                         polarity="PMOS"))
        assert p.polarity == "PMOS"

    def test_wrong_type(self):
        with pytest.raises(InvalidCircuitError):
            extract_mosfet_params(jfet("J1", "d", "g", "s"))

    def test_value_must_be_none(self):
        m = mosfet("M1", "d", "g", "s", "b")
        bad = Component("M1", "M", Q("1 V"), dict(m.pins),
                        parameters=dict(m.parameters))
        with pytest.raises(InvalidCircuitError):
            extract_mosfet_params(bad)

    def test_missing_param(self):
        m = mosfet("M1", "d", "g", "s", "b")
        pars = dict(m.parameters)
        del pars["Gamma"]
        bad = Component("M1", "M", None, dict(m.pins), parameters=pars)
        with pytest.raises(InvalidCircuitError):
            extract_mosfet_params(bad)

    def test_extra_param(self):
        m = mosfet("M1", "d", "g", "s", "b")
        pars = dict(m.parameters)
        pars["Rs"] = Q("10 ohm")
        bad = Component("M1", "M", None, dict(m.pins), parameters=pars)
        with pytest.raises(InvalidCircuitError):
            extract_mosfet_params(bad)

    def test_bad_polarity(self):
        m = mosfet("M1", "d", "g", "s", "b")
        pars = dict(m.parameters)
        pars["polarity"] = "NPN"
        bad = Component("M1", "M", None, dict(m.pins), parameters=pars)
        with pytest.raises(InvalidCircuitError):
            extract_mosfet_params(bad)

    def test_kp_wrong_dimension(self):
        m = mosfet("M1", "d", "g", "s", "b")
        pars = dict(m.parameters)
        pars["Kp"] = Q("0.0002 S")
        bad = Component("M1", "M", None, dict(m.pins), parameters=pars)
        with pytest.raises(InvalidCircuitError):
            extract_mosfet_params(bad)

    def test_kp_not_positive(self):
        m = mosfet("M1", "d", "g", "s", "b")
        pars = dict(m.parameters)
        pars["Kp"] = kp("0")
        bad = Component("M1", "M", None, dict(m.pins), parameters=pars)
        with pytest.raises(InvalidCircuitError):
            extract_mosfet_params(bad)

    def test_vto_not_positive(self):
        m = mosfet("M1", "d", "g", "s", "b")
        pars = dict(m.parameters)
        pars["Vto"] = Q("0 V")
        bad = Component("M1", "M", None, dict(m.pins), parameters=pars)
        with pytest.raises(InvalidCircuitError):
            extract_mosfet_params(bad)

    def test_lambda_negative_rejected_zero_allowed(self):
        m = mosfet("M1", "d", "g", "s", "b")
        pars = dict(m.parameters)
        pars["Lambda"] = lam("-0.01")
        bad = Component("M1", "M", None, dict(m.pins), parameters=pars)
        with pytest.raises(InvalidCircuitError):
            extract_mosfet_params(bad)
        pars["Lambda"] = lam("0")
        ok = Component("M1", "M", None, dict(m.pins), parameters=pars)
        assert extract_mosfet_params(ok).Lambda == 0

    def test_phi_gamma_negative_rejected(self):
        m = mosfet("M1", "d", "g", "s", "b")
        pars = dict(m.parameters)
        pars["Phi"] = Q("-0.1 V")
        with pytest.raises(InvalidCircuitError):
            extract_mosfet_params(
                Component("M1", "M", None, dict(m.pins), parameters=pars))
        pars = dict(m.parameters)
        pars["Gamma"] = gam("-0.1")
        with pytest.raises(InvalidCircuitError):
            extract_mosfet_params(
                Component("M1", "M", None, dict(m.pins), parameters=pars))

    def test_non_quantity_rejected(self):
        m = mosfet("M1", "d", "g", "s", "b")
        pars = dict(m.parameters)
        pars["Vto"] = Decimal("1.0")
        bad = Component("M1", "M", None, dict(m.pins), parameters=pars)
        with pytest.raises(InvalidCircuitError):
            extract_mosfet_params(bad)

    def test_non_finite_rejected(self):
        m = mosfet("M1", "d", "g", "s", "b")
        pars = dict(m.parameters)
        pars["Vto"] = Quantity(Decimal("NaN"), V_UNIT)
        bad = Component("M1", "M", None, dict(m.pins), parameters=pars)
        with pytest.raises(InvalidCircuitError):
            extract_mosfet_params(bad)


# --------------------------------------------------------------------------
# 3. JFET parameter validation
# --------------------------------------------------------------------------

class TestJFETValidation:
    def test_valid_extract(self):
        p = extract_jfet_params(jfet("J1", "d", "g", "s"))
        assert isinstance(p, JFETParams) and p.polarity == "NCHAN"

    def test_wrong_type(self):
        with pytest.raises(InvalidCircuitError):
            extract_jfet_params(mosfet("M1", "d", "g", "s", "b"))

    def test_value_must_be_none(self):
        j = jfet("J1", "d", "g", "s")
        bad = Component("J1", "J", Q("1 V"), dict(j.pins),
                        parameters=dict(j.parameters))
        with pytest.raises(InvalidCircuitError):
            extract_jfet_params(bad)

    def test_missing_param(self):
        j = jfet("J1", "d", "g", "s")
        pars = dict(j.parameters)
        del pars["Vp"]
        with pytest.raises(InvalidCircuitError):
            extract_jfet_params(
                Component("J1", "J", None, dict(j.pins), parameters=pars))

    def test_bad_polarity(self):
        j = jfet("J1", "d", "g", "s")
        pars = dict(j.parameters)
        pars["polarity"] = "NMOS"
        with pytest.raises(InvalidCircuitError):
            extract_jfet_params(
                Component("J1", "J", None, dict(j.pins), parameters=pars))

    def test_idss_vp_positive(self):
        j = jfet("J1", "d", "g", "s")
        pars = dict(j.parameters)
        pars["Idss"] = Q("0 A")
        with pytest.raises(InvalidCircuitError):
            extract_jfet_params(
                Component("J1", "J", None, dict(j.pins), parameters=pars))
        pars = dict(j.parameters)
        pars["Vp"] = Q("-2 V")
        with pytest.raises(InvalidCircuitError):
            extract_jfet_params(
                Component("J1", "J", None, dict(j.pins), parameters=pars))

    def test_lambda_zero_allowed_negative_rejected(self):
        j = jfet("J1", "d", "g", "s")
        pars = dict(j.parameters)
        pars["Lambda"] = lam("0")
        assert extract_jfet_params(
            Component("J1", "J", None, dict(j.pins),
                      parameters=pars)).Lambda == 0
        pars["Lambda"] = lam("-0.5")
        with pytest.raises(InvalidCircuitError):
            extract_jfet_params(
                Component("J1", "J", None, dict(j.pins), parameters=pars))

    def test_non_quantity_rejected(self):
        j = jfet("J1", "d", "g", "s")
        pars = dict(j.parameters)
        pars["Vp"] = 3.0
        with pytest.raises(InvalidCircuitError):
            extract_jfet_params(
                Component("J1", "J", None, dict(j.pins), parameters=pars))


# --------------------------------------------------------------------------
# 4. D-kind parameter validation
# --------------------------------------------------------------------------

class TestDKindValidation:
    def test_rect_explicit_kind(self):
        p = extract_diode_variant_params(diode_kind("D1", "a", "k", "RECT"))
        assert isinstance(p, DiodeVariantParams) and p.kind == "RECT"

    def test_legacy_path_untouched(self):
        # D without kind still uses the exact F8-H triple.
        p = extract_diode_params(shockley_diode("D1", "a", "k"))
        assert isinstance(p, DiodeParams)
        with pytest.raises(InvalidCircuitError):
            extract_diode_params(diode_kind("D1", "a", "k", "LED"))

    def test_bad_kind(self):
        with pytest.raises(InvalidCircuitError):
            extract_diode_variant_params(diode_kind("D1", "a", "k", "TUNNEL"))

    def test_missing_kind(self):
        with pytest.raises(InvalidCircuitError):
            extract_diode_variant_params(shockley_diode("D1", "a", "k"))

    def test_zener_full_set(self):
        p = extract_diode_variant_params(
            diode_kind("D1", "a", "k", "ZENER", Vz=Q("5.1 V"), nz=Q("1"),
                       Iz=Q("1e-3 A")))
        assert (p.Vz, p.nz, p.Iz) == (Decimal("5.1"), Decimal(1),
                                      Decimal("0.001"))

    def test_zener_missing_vz(self):
        with pytest.raises(InvalidCircuitError):
            extract_diode_variant_params(
                diode_kind("D1", "a", "k", "ZENER", nz=Q("1"),
                           Iz=Q("1e-3 A")))

    def test_zener_nonpositive_rejected(self):
        with pytest.raises(InvalidCircuitError):
            extract_diode_variant_params(
                diode_kind("D1", "a", "k", "ZENER", Vz=Q("0 V"), nz=Q("1"),
                           Iz=Q("1e-3 A")))

    def test_led_schottky_sets(self):
        assert extract_diode_variant_params(
            diode_kind("D1", "a", "k", "LED")).kind == "LED"
        assert extract_diode_variant_params(
            diode_kind("D1", "a", "k", "SCHOTTKY")).kind == "SCHOTTKY"

    def test_photo_iph(self):
        p = extract_diode_variant_params(
            diode_kind("D1", "a", "k", "PHOTO", Iph=Q("1 mA")))
        assert p.Iph == Decimal("0.001")
        p0 = extract_diode_variant_params(
            diode_kind("D1", "a", "k", "PHOTO", Iph=Q("0 A")))
        assert p0.Iph == 0
        with pytest.raises(InvalidCircuitError):
            extract_diode_variant_params(
                diode_kind("D1", "a", "k", "PHOTO", Iph=Q("-1 mA")))

    def test_extra_param_rejected(self):
        with pytest.raises(InvalidCircuitError):
            extract_diode_variant_params(
                diode_kind("D1", "a", "k", "LED", Rs=Q("10 ohm")))


# --------------------------------------------------------------------------
# 5. MOSFET physics
# --------------------------------------------------------------------------

class TestMOSPhysics:
    def test_cutoff_zero_current(self):
        p = std_mos_params()
        cur = mos_terminal_currents(Decimal(5), Decimal("0.5"), Decimal(0),
                                    Decimal(0), p, CTX)
        assert cur[0] == 0 and cur[2] == 0
        assert cur[1] == 0 and cur[3] == 0
        assert mos_region(Decimal(5), Decimal("0.5"), Decimal(0),
                          Decimal(0), p, CTX) == "cutoff"

    def test_threshold_boundary_zero(self):
        p = std_mos_params(Gamma=Decimal(0))
        # VGS = Vth = 1 exactly -> cutoff branch gives ID = 0.
        cur = mos_terminal_currents(Decimal(5), Decimal(1), Decimal(0),
                                    Decimal(0), p, CTX)
        assert cur[0] == 0

    def test_saturation_analytic(self):
        p = std_mos_params(Gamma=Decimal(0), Lambda=Decimal(0))
        # VGS=3, Vth=1 -> Vov=2; VDS=5 -> saturation.
        # ID = Kp/2 * Vov^2 = 1e-4 * 4 = 4e-4.
        cur = mos_terminal_currents(Decimal(5), Decimal(3), Decimal(0),
                                    Decimal(0), p, CTX)
        assert abs(cur[0] - Decimal("0.0004")) < Decimal("1E-12")
        assert cur[0] + cur[2] == 0  # KCL per device
        assert mos_region(Decimal(5), Decimal(3), Decimal(0),
                          Decimal(0), p, CTX) == "saturation"

    def test_triode_analytic(self):
        p = std_mos_params(Gamma=Decimal(0), Lambda=Decimal(0))
        # Vov=2, VDS=1 -> ID = Kp*(Vov*VDS - VDS^2/2) = 2e-4*(2-0.5)=3e-4.
        cur = mos_terminal_currents(Decimal(1), Decimal(3), Decimal(0),
                                    Decimal(0), p, CTX)
        assert abs(cur[0] - Decimal("0.0003")) < Decimal("1E-12")
        assert mos_region(Decimal(1), Decimal(3), Decimal(0),
                          Decimal(0), p, CTX) == "triode"

    def test_vds_equals_vov_continuity(self):
        p = std_mos_params(Gamma=Decimal(0), Lambda=Decimal("0.02"))
        below = mos_terminal_currents(Decimal("1.999999"), Decimal(3),
                                      Decimal(0), Decimal(0), p, CTX)[0]
        above = mos_terminal_currents(Decimal("2.000001"), Decimal(3),
                                      Decimal(0), Decimal(0), p, CTX)[0]
        assert abs(below - above) < Decimal("1E-6")

    def test_lambda_modulation(self):
        p = std_mos_params(Gamma=Decimal(0))
        i5 = mos_terminal_currents(Decimal(5), Decimal(3), Decimal(0),
                                   Decimal(0), p, CTX)[0]
        i10 = mos_terminal_currents(Decimal(10), Decimal(3), Decimal(0),
                                    Decimal(0), p, CTX)[0]
        # (1+0.02*10)/(1+0.02*5) = 1.2/1.1
        assert abs(i10 / i5 - Decimal("1.2") / Decimal("1.1")) < Decimal("1E-9")

    def test_lambda_zero_gds_zero(self):
        p = std_mos_params(Gamma=Decimal(0), Lambda=Decimal(0))
        gm, gds, gmb = mos_conductances(Decimal(5), Decimal(3), Decimal(0),
                                        Decimal(0), p, CTX)
        assert gds == 0
        assert gm == Decimal("0.0004")  # Kp*Vov = 2e-4*2
        assert gmb == 0  # Gamma = 0

    def test_body_effect(self):
        p0 = std_mos_params(Gamma=Decimal(0))
        p1 = std_mos_params()
        # Hold VGS = 3 with VSB = 2 (vs=2, vg=5): Vth rises above Vto=1
        # under body effect, so ID falls but stays positive.
        i0 = mos_terminal_currents(Decimal(5), Decimal(5), Decimal(2),
                                   Decimal(0), p0, CTX)[0]
        i1 = mos_terminal_currents(Decimal(5), Decimal(5), Decimal(2),
                                   Decimal(0), p1, CTX)[0]
        assert i1 < i0 and i1 > 0
        gm, gds, gmb = mos_conductances(Decimal(5), Decimal(5), Decimal(2),
                                        Decimal(0), p1, CTX)
        assert gmb > 0  # NMOS: raising VB raises ID

    def test_pmos_symmetry(self):
        pn = std_mos_params()
        pp = std_mos_params(polarity="PMOS")
        # Mirror all terminal voltages: currents negate exactly
        # (negation via the explicit context: ambient-context unary minus
        # would round 50-digit values to 28 digits).
        cn = mos_terminal_currents(Decimal(1), Decimal(0), Decimal(4),
                                   Decimal(4), pn, CTX)
        cp = mos_terminal_currents(Decimal(7), Decimal(8), Decimal(4),
                                   Decimal(4), pp, CTX)
        for a, b in zip(cn, cp):
            assert a == CTX.minus(b)

    def test_derivatives_vs_finite_difference(self):
        p = std_mos_params()
        h = Decimal("1E-6")
        vd, vg, vs, vb = (Decimal(5), Decimal(3), Decimal(1), Decimal(0))
        jac = mos_jacobian(vd, vg, vs, vb, p, CTX)
        assert jac is not None
        base = mos_terminal_currents(vd, vg, vs, vb, p, CTX)
        vecs = [(vd + h, vg, vs, vb), (vd, vg + h, vs, vb),
                (vd, vg, vs + h, vb), (vd, vg, vs, vb + h)]
        for ci in range(4):
            for ri in (0, 2):  # D and S rows (G/B rows are zero)
                pert = [mos_terminal_currents(*v, p, CTX)[ri] for v in vecs]
                for cj, pv in enumerate(pert):
                    fd = (pv - base[ri]) / h
                    assert abs(fd - jac[ri][cj]) < Decimal("1E-4"), (ri, cj)
        # Gate/bulk rows identically zero.
        assert all(v == 0 for v in jac[1])
        assert all(v == 0 for v in jac[3])
        # Column sums vanish (reference invariance), rows D+S vanish (KCL).
        for cj in range(4):
            assert abs(jac[0][cj] + jac[2][cj]) < Decimal("1E-18")

    def test_jacobian_column_sum_zero(self):
        p = std_mos_params()
        jac = mos_jacobian(Decimal(4), Decimal(3), Decimal(1), Decimal(0),
                           p, CTX)
        assert jac is not None
        for cj in range(4):
            s = jac[0][cj] + jac[1][cj] + jac[2][cj] + jac[3][cj]
            assert abs(s) < Decimal("1E-18")

    def test_reverse_vds_triode(self):
        p = std_mos_params(Gamma=Decimal(0), Lambda=Decimal(0))
        cur = mos_terminal_currents(Decimal(-1), Decimal(3), Decimal(0),
                                    Decimal(0), p, CTX)
        assert cur[0] < 0  # reverse conduction, deterministic sign


# --------------------------------------------------------------------------
# 6. JFET physics
# --------------------------------------------------------------------------

class TestJFETPhysics:
    def test_cutoff(self):
        p = std_jfet_params()
        cur = jfet_terminal_currents(Decimal(5), Decimal(-4), Decimal(0),
                                     p, CTX)
        assert cur == (Decimal(0), Decimal(0), Decimal(0))
        assert jfet_region(Decimal(5), Decimal(-4), Decimal(0),
                           p, CTX) == "cutoff"

    def test_cutoff_boundary_zero(self):
        p = std_jfet_params()
        cur = jfet_terminal_currents(Decimal(5), Decimal(-3), Decimal(0),
                                     p, CTX)
        assert cur[0] == 0

    def test_saturation_analytic(self):
        p = std_jfet_params(Lambda=Decimal(0))
        # VGS=-1, Vp=3 -> (1-1/3)^2 = 4/9; ID = 0.01*4/9.
        cur = jfet_terminal_currents(Decimal(10), Decimal(-1), Decimal(0),
                                     p, CTX)
        assert abs(cur[0] - Decimal("0.01") * Decimal(4) / Decimal(9)) < Decimal("1E-12")
        assert cur[0] + cur[2] == 0
        assert jfet_region(Decimal(10), Decimal(-1), Decimal(0),
                           p, CTX) == "saturation"

    def test_triode_analytic(self):
        p = std_jfet_params(Lambda=Decimal(0))
        # VGS=0, VDS=1: a=1, b=1/3 -> ID=0.01*(2/3-1/9)=0.01*5/9.
        cur = jfet_terminal_currents(Decimal(1), Decimal(0), Decimal(0),
                                     p, CTX)
        assert abs(cur[0] - Decimal("0.01") * Decimal(5) / Decimal(9)) < Decimal("1E-12")
        assert jfet_region(Decimal(1), Decimal(0), Decimal(0),
                           p, CTX) == "triode"

    def test_saturation_boundary_continuity(self):
        p = std_jfet_params()
        # VGS=-1 -> edge VDS = 2.
        below = jfet_terminal_currents(Decimal("1.999999"), Decimal(-1),
                                       Decimal(0), p, CTX)[0]
        above = jfet_terminal_currents(Decimal("2.000001"), Decimal(-1),
                                       Decimal(0), p, CTX)[0]
        assert abs(below - above) < Decimal("1E-9")

    def test_near_cutoff_continuous(self):
        p = std_jfet_params()
        # Just above cutoff at macroscopic VDS -> saturation -> ~0.
        cur = jfet_terminal_currents(Decimal(5), Decimal("-2.999"), Decimal(0),
                                     p, CTX)[0]
        assert cur >= 0 and cur < Decimal("1E-6")

    def test_pchan_symmetry(self):
        pn = std_jfet_params()
        pp = std_jfet_params(polarity="PCHAN")
        cn = jfet_terminal_currents(Decimal(6), Decimal(-1), Decimal(0),
                                    pn, CTX)
        cp = jfet_terminal_currents(Decimal(-6), Decimal(1), Decimal(0),
                                    pp, CTX)
        for a, b in zip(cn, cp):
            assert a == CTX.minus(b)

    def test_lambda_zero_gds_zero(self):
        p = std_jfet_params(Lambda=Decimal(0))
        gm, gds = jfet_conductances(Decimal(10), Decimal(-1), Decimal(0),
                                    p, CTX)
        assert gds == 0
        # gm = Idss*2*(1+VGS/Vp)/Vp = 0.01*2*(2/3)/3.
        assert abs(gm - Decimal("0.01") * Decimal(2) * Decimal(2) / Decimal(9)) \
            < Decimal("1E-15")

    def test_derivatives_vs_finite_difference(self):
        p = std_jfet_params()
        h = Decimal("1E-6")
        vd, vg, vs = Decimal(6), Decimal(-1), Decimal(1)
        jac = jfet_jacobian(vd, vg, vs, p, CTX)
        assert jac is not None
        base = jfet_terminal_currents(vd, vg, vs, p, CTX)
        vecs = [(vd + h, vg, vs), (vd, vg + h, vs), (vd, vg, vs + h)]
        for ri in (0, 2):
            pert = [jfet_terminal_currents(*v, p, CTX)[ri] for v in vecs]
            for cj, pv in enumerate(pert):
                fd = (pv - base[ri]) / h
                assert abs(fd - jac[ri][cj]) < Decimal("1E-4"), (ri, cj)
        assert all(v == 0 for v in jac[1])


# --------------------------------------------------------------------------
# 7. D-kind physics
# --------------------------------------------------------------------------

class TestDKindPhysics:
    def test_rect_identical_to_shockley(self):
        vp = extract_diode_variant_params(diode_kind("D1", "a", "k", "RECT"))
        sp = DiodeParams(Is=Decimal("1E-14"), n=Decimal(1),
                         Vt=Decimal("0.02585"))
        for vd in (Decimal("-5"), Decimal("-0.2"), Decimal(0),
                   Decimal("0.3"), Decimal("0.8")):
            assert variant_current(vd, vp, CTX) == shockley_current(vd, sp, CTX)
            assert variant_conductance(vd, vp, CTX) == \
                shockley_conductance(vd, sp, CTX)

    def test_zener_forward_is_shockley(self):
        vp = extract_diode_variant_params(
            diode_kind("D1", "a", "k", "ZENER", Vz=Q("5.1 V"), nz=Q("1"),
                       Iz=Q("1e-3 A")))
        sp = DiodeParams(Is=Decimal("1E-14"), n=Decimal(1),
                         Vt=Decimal("0.02585"))
        for vd in (Decimal(0), Decimal("0.4"), Decimal("0.9")):
            assert variant_current(vd, vp, CTX) == shockley_current(vd, sp, CTX)
            assert variant_conductance(vd, vp, CTX) == \
                shockley_conductance(vd, sp, CTX)

    def test_zener_continuity_at_zero(self):
        vp = extract_diode_variant_params(
            diode_kind("D1", "a", "k", "ZENER", Vz=Q("5.1 V"), nz=Q("1"),
                       Iz=Q("1e-3 A")))
        assert variant_current(Decimal(0), vp, CTX) == 0
        # C0 from both sides.
        assert abs(variant_current(Decimal("1E-9"), vp, CTX)) < Decimal("1E-12")
        assert abs(variant_current(Decimal("-1E-9"), vp, CTX)) < Decimal("1E-12")
        # C1 up to the negligible exp(-Vz/(nz*Vt)) term.
        g_f = variant_conductance(Decimal("1E-9"), vp, CTX)
        g_r = variant_conductance(Decimal("-1E-9"), vp, CTX)
        assert abs(g_f - g_r) / g_f < Decimal("1E-6")

    def test_zener_pre_breakdown_leakage(self):
        vp = extract_diode_variant_params(
            diode_kind("D1", "a", "k", "ZENER", Vz=Q("5.1 V"), nz=Q("1"),
                       Iz=Q("1e-3 A")))
        i = variant_current(Decimal("-1"), vp, CTX)
        assert i < 0 and abs(i) < Decimal("1E-9")

    def test_zener_breakdown_growth(self):
        vp = extract_diode_variant_params(
            diode_kind("D1", "a", "k", "ZENER", Vz=Q("5.1 V"), nz=Q("1"),
                       Iz=Q("1e-3 A")))
        i_below = variant_current(Decimal("-4"), vp, CTX)
        i_knee = variant_current(Decimal("-5.1"), vp, CTX)
        i_deep = variant_current(Decimal("-6"), vp, CTX)
        assert i_knee < i_below < Decimal(0)
        assert i_deep < i_knee
        assert i_deep < Decimal("-0.01")  # strong conduction past knee
        g = variant_conductance(Decimal("-5.5"), vp, CTX)
        assert g > Decimal("0.01")  # low dynamic resistance in breakdown

    def test_led_forward_vf(self):
        lp = extract_diode_variant_params(
            diode_kind("D1", "a", "k", "LED", Is=Q("1e-27 A")))
        # At 1.6 V: 1e-27*exp(1.6/0.02585) ≈ 0.76 A (red-LED order).
        i16 = variant_current(Decimal("1.6"), lp, CTX)
        assert Decimal("0.1") < i16 < Decimal("10")
        # Reverse blocks (up to the exp underflow term).
        assert abs(variant_current(Decimal("-5"), lp, CTX) + lp.Is) < \
            lp.Is * Decimal("1E-6")

    def test_schottky_low_vf(self):
        sp = extract_diode_variant_params(
            diode_kind("D1", "a", "k", "SCHOTTKY", Is=Q("1e-8 A")))
        i = variant_current(Decimal("0.3"), sp, CTX)
        assert Decimal("1e-4") < i < Decimal("1")
        assert abs(variant_current(Decimal("-2"), sp, CTX) + sp.Is) < \
            sp.Is * Decimal("1E-6")

    def test_photo_dark_is_shockley(self):
        pp = extract_diode_variant_params(
            diode_kind("D1", "a", "k", "PHOTO", Iph=Q("0 A")))
        sp = DiodeParams(Is=Decimal("1E-14"), n=Decimal(1),
                         Vt=Decimal("0.02585"))
        for vd in (Decimal("-2"), Decimal("0.5")):
            assert variant_current(vd, pp, CTX) == shockley_current(vd, sp, CTX)
            assert variant_conductance(vd, pp, CTX) == \
                shockley_conductance(vd, sp, CTX)

    def test_photo_illuminated_shift(self):
        pp = extract_diode_variant_params(
            diode_kind("D1", "a", "k", "PHOTO", Iph=Q("1 mA")))
        i_dark_ref = shockley_current(Decimal("0.4"), pp.as_shockley(), CTX)
        i_lit = variant_current(Decimal("0.4"), pp, CTX)
        assert abs(i_lit - (i_dark_ref - Decimal("0.001"))) < Decimal("1E-12")
        # Photocurrent dominates in reverse: third-quadrant operation.
        assert variant_current(Decimal("-1"), pp, CTX) < Decimal("-0.0009")
        # Derivative independent of Iph.
        assert variant_conductance(Decimal("0.4"), pp, CTX) == \
            shockley_conductance(Decimal("0.4"), pp.as_shockley(), CTX)


# --------------------------------------------------------------------------
# 8. Circuit tests (biased DC operating points)
# --------------------------------------------------------------------------

def check_conservation(sol):
    assert sol.conservation_checks is not None
    assert sol.conservation_checks.passed


class TestCircuits:
    def test_m1_nmos_saturation_bias(self):
        c = Circuit("k_m1_sat")
        c.add(vsrc("V1", "dd", "0", "5 V"))
        c.add(vsrc("V2", "gg", "0", "3 V"))
        c.add(res("R1", "dd", "s", "2 kohm"))
        c.add(mosfet("M1", "s", "gg", "0", "0"))
        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        vs = node_v(sol, "s")
        # ID = (Kp/2)*Vov^2*(1+Lambda*VDS), Vs = 5 - ID*2k, Vov=2.
        # ID = 4.3307e-4 A -> Vs = 4.1339 V.
        assert abs(vs - Decimal("4.1339")) < Decimal("0.01")
        check_conservation(sol)

    def test_m2_pmos_bias(self):
        c = Circuit("k_m2_pmos")
        c.add(vsrc("V1", "ss", "0", "5 V"))
        c.add(vsrc("V2", "gg", "0", "2 V"))
        c.add(res("R1", "ss", "s", "2 kohm"))
        c.add(mosfet("M1", "0", "gg", "s", "ss", polarity="PMOS"))
        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        vs = node_v(sol, "s")
        # VSG = Vs-2 ≈ 2.55 > Vth ≈ 1.12, saturation; ID = (5-Vs)/2k.
        assert Decimal("4.4") < vs < Decimal("4.7")
        check_conservation(sol)

    def test_m3_cutoff(self):
        c = Circuit("k_m3_off")
        c.add(vsrc("V1", "dd", "0", "5 V"))
        c.add(vsrc("V2", "gg", "0", "0 V"))
        c.add(res("R1", "dd", "s", "2 kohm"))
        c.add(mosfet("M1", "s", "gg", "0", "0"))
        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        assert abs(node_v(sol, "s") - Decimal(5)) < Decimal("1E-9")
        check_conservation(sol)

    def test_m4_triode(self):
        c = Circuit("k_m4_tri")
        c.add(vsrc("V1", "dd", "0", "1 V"))
        c.add(vsrc("V2", "gg", "0", "5 V"))
        c.add(res("R1", "dd", "s", "100 ohm"))
        c.add(mosfet("M1", "s", "gg", "0", "0", lam_s="0", gam_s="0"))
        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        vs = node_v(sol, "s")
        # Triode, small drop: Vs slightly below 1 V.
        assert Decimal("0.5") < vs < Decimal("1")
        check_conservation(sol)

    def test_j1_nchan_bias(self):
        c = Circuit("k_j1")
        c.add(vsrc("V1", "dd", "0", "10 V"))
        c.add(vsrc("V2", "gg", "0", "-1 V"))
        c.add(res("R1", "dd", "d", "2 kohm"))
        c.add(jfet("J1", "d", "gg", "0"))
        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        vd = node_v(sol, "d")
        # ID = 0.01*(1-1/3)^2*(1+0.01*VDS); Vd = 10 - ID*2k ≈ 1.4 V.
        assert Decimal("0.5") < vd < Decimal("3")
        check_conservation(sol)

    def test_j2_cutoff(self):
        c = Circuit("k_j2_off")
        c.add(vsrc("V1", "dd", "0", "10 V"))
        c.add(vsrc("V2", "gg", "0", "-5 V"))
        c.add(res("R1", "dd", "d", "2 kohm"))
        c.add(jfet("J1", "d", "gg", "0"))
        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        assert abs(node_v(sol, "d") - Decimal(10)) < Decimal("1E-9")
        check_conservation(sol)

    def test_z1_regulator(self):
        c = Circuit("k_z1")
        c.add(vsrc("V1", "n1", "0", "10 V"))
        c.add(res("R1", "n1", "out", "1 kohm"))
        c.add(diode_kind("D1", "0", "out", "ZENER", Vz=Q("5.1 V"),
                         nz=Q("1"), Iz=Q("1e-3 A")))
        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        vout = node_v(sol, "out")
        assert Decimal("4.9") < vout < Decimal("5.4")
        check_conservation(sol)

    def test_l1_led_string(self):
        c = Circuit("k_l1")
        c.add(vsrc("V1", "n1", "0", "5 V"))
        c.add(res("R1", "n1", "out", "100 ohm"))
        c.add(diode_kind("D1", "out", "0", "LED", Is=Q("1e-30 A")))
        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        vout = node_v(sol, "out")
        assert Decimal("1.2") < vout < Decimal("2.2")
        check_conservation(sol)

    def test_s1_schottky(self):
        c = Circuit("k_s1")
        c.add(vsrc("V1", "n1", "0", "5 V"))
        c.add(res("R1", "n1", "out", "1 kohm"))
        c.add(diode_kind("D1", "out", "0", "SCHOTTKY", Is=Q("1e-8 A")))
        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        vout = node_v(sol, "out")
        assert Decimal("0.1") < vout < Decimal("0.6")
        check_conservation(sol)

    def test_p1_photodiode_dark_vs_lit(self):
        # Reverse orientation (A=0, K=out): photocurrent must be supplied
        # through R, pulling the node down under illumination.
        def build(iph: str):
            c = Circuit("k_p1")
            c.add(vsrc("V1", "n1", "0", "5 V"))
            c.add(res("R1", "n1", "out", "10 kohm"))
            c.add(diode_kind("D1", "0", "out", "PHOTO", Iph=Q(iph)))
            return c
        dark = solve_nonlinear_dc(build("0 A"))
        lit = solve_nonlinear_dc(build("0.1 mA"))
        assert dark.status == NonlinearStatus.CONVERGED
        assert lit.status == NonlinearStatus.CONVERGED
        assert abs(node_v(dark, "out") - Decimal(5)) < Decimal("0.01")
        assert abs(node_v(lit, "out") - Decimal(4)) < Decimal("0.05")
        assert node_v(lit, "out") < node_v(dark, "out")
        check_conservation(dark)
        check_conservation(lit)


# --------------------------------------------------------------------------
# 9. Mixed-device tests
# --------------------------------------------------------------------------

def mixed_converges(builder) -> None:
    sol = solve_nonlinear_dc(builder())
    assert sol.status == NonlinearStatus.CONVERGED
    check_conservation(sol)


class TestMixed:
    def test_d_plus_m(self):
        def b():
            c = Circuit("km_dm")
            c.add(vsrc("V1", "dd", "0", "8 V"))
            c.add(vsrc("V2", "gg", "0", "3 V"))
            c.add(res("R1", "dd", "s", "1 kohm"))
            c.add(mosfet("M1", "s", "gg", "mid", "0"))
            c.add(shockley_diode("D1", "mid", "0"))
            return c
        mixed_converges(b)

    def test_d_plus_j(self):
        def b():
            c = Circuit("km_dj")
            c.add(vsrc("V1", "dd", "0", "12 V"))
            c.add(vsrc("V2", "gg", "0", "-1 V"))
            c.add(res("R1", "dd", "d", "2 kohm"))
            c.add(jfet("J1", "d", "gg", "mid"))
            c.add(shockley_diode("D1", "mid", "0"))
            return c
        mixed_converges(b)

    def test_m_plus_q(self):
        # M1 common-source stage driving R1; Q1 emitter-follower buffer.
        def b():
            c = Circuit("km_mq")
            c.add(vsrc("V1", "vcc", "0", "10 V"))
            c.add(vsrc("V2", "gg", "0", "3 V"))
            c.add(res("R1", "vcc", "d1", "10 kohm"))
            c.add(mosfet("M1", "d1", "gg", "0", "0"))
            c.add(bjt("Q1", "vcc", "d1", "out"))
            c.add(res("R2", "out", "0", "10 kohm"))
            return c
        mixed_converges(b)

    def test_j_plus_q(self):
        # J1 common-source stage; Q1 emitter-follower buffer.
        def b():
            c = Circuit("km_jq")
            c.add(vsrc("V1", "vcc", "0", "12 V"))
            c.add(vsrc("V2", "gj", "0", "-1 V"))
            c.add(res("R1", "vcc", "d1", "1 kohm"))
            c.add(jfet("J1", "d1", "gj", "0"))
            c.add(bjt("Q1", "vcc", "d1", "out"))
            c.add(res("R2", "out", "0", "2 kohm"))
            return c
        mixed_converges(b)

    def test_m_plus_j(self):
        def b():
            c = Circuit("km_mj")
            c.add(vsrc("V1", "vcc", "0", "10 V"))
            c.add(vsrc("V2", "gg", "0", "3 V"))
            c.add(vsrc("V3", "gj", "0", "-1 V"))
            c.add(res("R1", "vcc", "s", "1 kohm"))
            c.add(mosfet("M1", "s", "gg", "mid", "0"))
            c.add(jfet("J1", "mid", "gj", "0"))
            return c
        mixed_converges(b)

    def test_m_plus_zener(self):
        def b():
            c = Circuit("km_mz")
            c.add(vsrc("V1", "gg", "0", "6 V"))
            c.add(res("R1", "gg", "g2", "1 kohm"))
            c.add(diode_kind("D1", "0", "g2", "ZENER", Vz=Q("5.1 V"),
                             nz=Q("1"), Iz=Q("1e-3 A")))
            c.add(vsrc("V2", "dd", "0", "10 V"))
            c.add(res("R2", "dd", "s", "2 kohm"))
            c.add(mosfet("M1", "s", "g2", "0", "0"))
            return c
        mixed_converges(b)

    def test_q_plus_d_kind(self):
        def b():
            c = Circuit("km_qd")
            c.add(vsrc("V1", "vcc", "0", "10 V"))
            c.add(vsrc("V2", "bb", "0", "2 V"))
            c.add(res("R1", "vcc", "cc", "1 kohm"))
            c.add(bjt("Q1", "cc", "bb", "ee"))
            c.add(diode_kind("D1", "ee", "0", "LED", Is=Q("1e-18 A")))
            return c
        mixed_converges(b)


# --------------------------------------------------------------------------
# 10. No-convergence / error paths
# --------------------------------------------------------------------------

class TestNoConvergence:
    def test_singular_jacobian(self):
        c = Circuit("kn_sing")
        c.add(vsrc("V1", "1", "0", "5 V"))
        c.add(vsrc("V2", "1", "0", "3 V"))  # conflicting ideals
        c.add(mosfet("M1", "1", "1", "0", "0"))
        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.SINGULAR_JACOBIAN

    def test_max_iterations(self):
        c = Circuit("kn_maxit")
        c.add(vsrc("V1", "dd", "0", "5 V"))
        c.add(vsrc("V2", "gg", "0", "3 V"))
        c.add(res("R1", "dd", "s", "2 kohm"))
        c.add(mosfet("M1", "s", "gg", "0", "0"))
        sol = solve_nonlinear_dc(c, max_iter=0)
        assert sol.status == NonlinearStatus.MAX_ITERATIONS

    def test_invalid_params_at_solve(self):
        c = Circuit("kn_inv")
        c.add(vsrc("V1", "1", "0", "5 V"))
        c.add(res("R1", "1", "0"))
        m = mosfet("M1", "1", "1", "0", "0")
        pars = dict(m.parameters)
        del pars["Kp"]
        c.add(Component("M1", "M", None, dict(m.pins), parameters=pars))
        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.INVALID

    def test_unsupported_reactive_with_m(self):
        from academic_core.domain.engineering.units import parse_quantity as pq
        c = Circuit("kn_un")
        c.add(vsrc("V1", "1", "0", "5 V"))
        c.add(Component("C1", "C", pq("1 uF"), {"1": "1", "2": "0"}))
        c.add(mosfet("M1", "1", "1", "0", "0"))
        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.UNSUPPORTED

    def test_h_control_by_mosfet_rejected(self):
        c = Circuit("kn_hm")
        c.add(vsrc("V1", "a", "0", "5 V"))
        c.add(res("R1", "a", "b", "1 kohm"))
        c.add(mosfet("M1", "b", "a", "0", "0"))
        c.add(Component("H1", "H", Q("10 ohm"), {"+": "c", "-": "0"},
                        parameters={"control_ref": "M1"}))
        c.add(res("R2", "c", "0", "1 kohm"))
        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.INVALID

    def test_h_control_by_jfet_rejected(self):
        c = Circuit("kn_hj")
        c.add(vsrc("V1", "a", "0", "5 V"))
        c.add(res("R1", "a", "b", "1 kohm"))
        c.add(jfet("J1", "b", "a", "0"))
        c.add(Component("H1", "H", Q("10 ohm"), {"+": "c", "-": "0"},
                        parameters={"control_ref": "J1"}))
        c.add(res("R2", "c", "0", "1 kohm"))
        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.INVALID


# --------------------------------------------------------------------------
# 11. Boundary tests at derivative discontinuities
# --------------------------------------------------------------------------

class TestBoundaries:
    def test_mos_vgs_sweep_crosses_vth(self):
        for vg in ("0.5 V", "1 V", "1.5 V", "3 V"):
            c = Circuit("kb_mos_vth")
            c.add(vsrc("V1", "dd", "0", "5 V"))
            c.add(vsrc("V2", "gg", "0", vg))
            c.add(res("R1", "dd", "s", "2 kohm"))
            c.add(mosfet("M1", "s", "gg", "0", "0"))
            sol = solve_nonlinear_dc(c)
            assert sol.status == NonlinearStatus.CONVERGED, vg
        check_conservation(sol)

    def test_mos_vds_sweep_crosses_vov(self):
        # Vov = 2 (VGS=3, Vth=1, Lambda=0): Vdd in {3, 4} (triode),
        # {7, 10} (saturation, identical ID).
        ids = []
        for vd in ("3 V", "4 V", "7 V", "10 V"):
            c = Circuit("kb_mos_vds")
            c.add(vsrc("V1", "dd", "0", vd))
            c.add(vsrc("V2", "gg", "0", "3 V"))
            c.add(res("R1", "dd", "s", "10 kohm"))
            c.add(mosfet("M1", "s", "gg", "0", "0", lam_s="0", gam_s="0"))
            sol = solve_nonlinear_dc(c)
            assert sol.status == NonlinearStatus.CONVERGED, vd
            ids.append((node_v(sol, "dd") - node_v(sol, "s")) / Decimal(10000))
        assert ids[0] < ids[1] < ids[2]
        assert abs(ids[3] - ids[2]) < Decimal("1E-12")

    def test_jfet_cutoff_boundary_sweep(self):
        for vg in ("-4 V", "-3 V", "-2 V", "0 V"):
            c = Circuit("kb_j_cut")
            c.add(vsrc("V1", "dd", "0", "10 V"))
            c.add(vsrc("V2", "gg", "0", vg))
            c.add(res("R1", "dd", "d", "2 kohm"))
            c.add(jfet("J1", "d", "gg", "0"))
            sol = solve_nonlinear_dc(c)
            assert sol.status == NonlinearStatus.CONVERGED, vg

    def test_zener_breakdown_transition(self):
        outs = []
        for vs in ("3 V", "6 V", "12 V"):
            c = Circuit("kb_z")
            c.add(vsrc("V1", "n1", "0", vs))
            c.add(res("R1", "n1", "out", "1 kohm"))
            c.add(diode_kind("D1", "0", "out", "ZENER", Vz=Q("5.1 V"),
                             nz=Q("1"), Iz=Q("1e-3 A")))
            sol = solve_nonlinear_dc(c)
            assert sol.status == NonlinearStatus.CONVERGED, vs
            outs.append(node_v(sol, "out"))
        # Below breakdown the output follows the rail; above it clamps.
        assert abs(outs[0] - Decimal(3)) < Decimal("0.01")
        assert Decimal("4.9") < outs[1] < Decimal("5.4")
        assert Decimal("4.9") < outs[2] < Decimal("5.6")

    def test_photo_dark_boundary(self):
        c = Circuit("kb_p")
        c.add(vsrc("V1", "n1", "0", "5 V"))
        c.add(res("R1", "n1", "out", "10 kohm"))
        c.add(diode_kind("D1", "out", "0", "PHOTO", Iph=Q("0 A")))
        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        # Darkness: same node as the legacy Shockley diode.
        c2 = Circuit("kb_p_ref")
        c2.add(vsrc("V1", "n1", "0", "5 V"))
        c2.add(res("R1", "n1", "out", "10 kohm"))
        c2.add(shockley_diode("D1", "out", "0"))
        ref = solve_nonlinear_dc(c2)
        assert ref.status == NonlinearStatus.CONVERGED
        assert node_v(sol, "out") == node_v(ref, "out")


# --------------------------------------------------------------------------
# 12. F8-J small-signal contract
# --------------------------------------------------------------------------

class TestACContract:
    def test_mos_ac_params_exposed(self):
        c = Circuit("ka_mos")
        c.add(vsrc("V1", "dd", "0", "5 V"))
        c.add(vsrc("V2", "gg", "0", "3 V", ac_mag="10 mV"))
        c.add(res("R1", "dd", "s", "2 kohm"))
        c.add(mosfet("M1", "s", "gg", "0", "0"))
        sol = solve_small_signal_ac(c, "1 kHz")
        assert sol.status == ACStatus.SOLVED
        assert len(sol.mosfet_parameters) == 1
        mp = sol.mosfet_parameters[0]
        assert mp.region == "saturation"
        trio = mos_conductances(node_v(sol.dc_operating_point, "s"),
                                node_v(sol.dc_operating_point, "gg"),
                                Decimal(0), Decimal(0),
                                extract_mosfet_params(
                                    next(x for x in c.components
                                         if x.ref == "M1")), make_context())
        assert trio is not None
        assert mp.g_m == trio[0] and mp.g_ds == trio[1] and mp.g_mb == trio[2]
        assert sol.kcl_max_residual < Decimal("1E-12")
        vout = sol.voltage_of("s")
        assert vout is not None

    def test_jfet_ac_params_exposed(self):
        c = Circuit("ka_j")
        c.add(vsrc("V1", "dd", "0", "10 V"))
        c.add(vsrc("V2", "gg", "0", "-1 V", ac_mag="10 mV"))
        c.add(res("R1", "dd", "d", "500 ohm"))
        c.add(jfet("J1", "d", "gg", "0"))
        sol = solve_small_signal_ac(c, "1 kHz")
        assert sol.status == ACStatus.SOLVED
        assert len(sol.jfet_parameters) == 1
        jp = sol.jfet_parameters[0]
        assert jp.region == "saturation" and jp.g_m > 0 and jp.g_ds > 0
        assert sol.kcl_max_residual < Decimal("1E-12")

    def test_zener_ac_conductance(self):
        c = Circuit("ka_z")
        c.add(vsrc("V1", "n1", "0", "10 V", ac_mag="10 mV"))
        c.add(res("R1", "n1", "out", "1 kohm"))
        c.add(diode_kind("D1", "0", "out", "ZENER", Vz=Q("5.1 V"),
                         nz=Q("1"), Iz=Q("1e-3 A")))
        sol = solve_small_signal_ac(c, "1 kHz")
        assert sol.status == ACStatus.SOLVED
        assert len(sol.diode_parameters) == 1
        assert sol.diode_parameters[0].kind == "ZENER"
        assert sol.diode_parameters[0].g_d > Decimal("0.001")
        assert sol.kcl_max_residual < Decimal("1E-12")

    def test_ac_digest_deterministic(self):
        c = Circuit("ka_det")
        c.add(vsrc("V1", "dd", "0", "5 V"))
        c.add(vsrc("V2", "gg", "0", "3 V", ac_mag="10 mV"))
        c.add(res("R1", "dd", "s", "2 kohm"))
        c.add(mosfet("M1", "s", "gg", "0", "0"))
        digests = set()
        for _ in range(3):
            sol = solve_small_signal_ac(c, "1 kHz")
            assert sol.status == ACStatus.SOLVED
            digests.add(sol.digest)
        assert len(digests) == 1


# --------------------------------------------------------------------------
# 13. Determinism
# --------------------------------------------------------------------------

class TestDeterminism:
    def _mos_circuit(self, order: str = "fwd") -> Circuit:
        c = Circuit("kd_mos")
        comps = [vsrc("V1", "dd", "0", "5 V"),
                 vsrc("V2", "gg", "0", "3 V"),
                 res("R1", "dd", "s", "2 kohm"),
                 mosfet("M1", "s", "gg", "0", "0")]
        if order == "rev":
            comps = list(reversed(comps))
        for comp in comps:
            c.add(comp)
        return c

    def test_repeated_solves_identical(self):
        sols = [solve_nonlinear_dc(self._mos_circuit()) for _ in range(5)]
        assert all(s.status == NonlinearStatus.CONVERGED for s in sols)
        first = sols[0].to_dict()
        for s in sols[1:]:
            assert s.to_dict() == first
        iters = {s.provenance["iterations"] for s in sols}
        assert len(iters) == 1

    def test_insertion_order_invariant(self):
        a = solve_nonlinear_dc(self._mos_circuit("fwd"))
        b = solve_nonlinear_dc(self._mos_circuit("rev"))
        assert a.status == b.status == NonlinearStatus.CONVERGED
        for na in a.node_voltages:
            assert node_v(b, na.node) == na.voltage.to_base()

    def test_jfet_repeated_identical(self):
        def build():
            c = Circuit("kd_j")
            c.add(vsrc("V1", "dd", "0", "10 V"))
            c.add(vsrc("V2", "gg", "0", "-1 V"))
            c.add(res("R1", "dd", "d", "2 kohm"))
            c.add(jfet("J1", "d", "gg", "0"))
            return c
        dicts = [solve_nonlinear_dc(build()).to_dict() for _ in range(3)]
        assert dicts[0] == dicts[1] == dicts[2]


# --------------------------------------------------------------------------
# 14. Security + float audits
# --------------------------------------------------------------------------

ENGINE_FILES = [
    "src/academic_core/domain/engineering/mna/mosfet.py",
    "src/academic_core/domain/engineering/mna/jfet.py",
    "src/academic_core/domain/engineering/mna/diode.py",
    "src/academic_core/domain/engineering/mna/nonlinear.py",
    "src/academic_core/domain/engineering/mna/problem.py",
    "src/academic_core/domain/engineering/mna/dependent.py",
    "src/academic_core/domain/engineering/mna/__init__.py",
    "src/academic_core/domain/engineering/ac/small_signal.py",
    "src/academic_core/domain/engineering/circuit.py",
    "src/academic_core/domain/engineering/models.py",
]


class TestSecurity:
    def test_ast_no_dynamic_execution(self):
        forbidden_calls = {"eval", "exec", "compile", "globals", "locals",
                           "__import__"}
        forbidden_mods = {"subprocess", "socket", "shutil", "os", "sys",
                          "importlib", "requests", "urllib"}
        for rel in ENGINE_FILES:
            target = Path(rel)
            assert target.is_file(), rel
            tree = ast.parse(target.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and \
                            node.func.id in forbidden_calls:
                        pytest.fail(f"{rel}: forbidden call {node.func.id}")
                    if isinstance(node.func, ast.Attribute) and \
                            node.func.attr in ("system", "popen", "run",
                                               "call", "check_output"):
                        pytest.fail(f"{rel}: forbidden call attr "
                                    f"{node.func.attr}")
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    mod = node.module if isinstance(node, ast.ImportFrom) \
                        else ""
                    for alias in node.names:
                        if alias.name.split(".")[0] in forbidden_mods or \
                                (mod or "").split(".")[0] in forbidden_mods:
                            pytest.fail(f"{rel}: forbidden import "
                                        f"{alias.name or mod}")

    def test_no_float_literals_or_calls(self):
        for rel in ENGINE_FILES:
            target = Path(rel)
            tree = ast.parse(target.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and \
                        isinstance(node.value, float):
                    pytest.fail(f"{rel}: float literal {node.value!r}")
                if isinstance(node, ast.Call) and \
                        isinstance(node.func, ast.Name) and \
                        node.func.id == "float":
                    pytest.fail(f"{rel}: float(...) call")


# --------------------------------------------------------------------------
# 15. Diagnostic benchmarks (no time asserts)
# --------------------------------------------------------------------------

class TestBenchmarksDiagnostic:
    @staticmethod
    def _ladder(kind: str, n: int) -> Circuit:
        c = Circuit(f"kb_{kind}_{n}")
        c.add(vsrc("V1", "vdd", "0", "5 V"))
        gbias = "3 V" if kind == "mos" else "-1 V"
        prev = "vdd"
        for i in range(1, n + 1):
            s = f"s{i}"
            g = f"g{i}"
            c.add(res(f"R{i}", prev, s, "2 kohm"))
            c.add(vsrc(f"V{500 + i}", g, "0", gbias))
            if kind == "mos":
                c.add(mosfet(f"M{i}", s, g, "0", "0"))
            else:
                c.add(jfet(f"J{i}", s, g, "0"))
            prev = s
        return c

    def test_mosfet_ladder_timings(self):
        timings = {}
        iters = {}
        for n in (1, 10, 32, 64):
            t0 = time.perf_counter()
            sol = solve_nonlinear_dc(self._ladder("mos", n))
            timings[n] = time.perf_counter() - t0
            assert sol.status == NonlinearStatus.CONVERGED
            iters[n] = sol.provenance["iterations"]
        print(f"\n[BENCHMARK F8-K MOS DIAGNÓSTICO] timings={timings} "
              f"iters={iters}")

    def test_jfet_ladder_timings(self):
        timings = {}
        for n in (1, 10, 32, 64):
            t0 = time.perf_counter()
            sol = solve_nonlinear_dc(self._ladder("jfet", n))
            timings[n] = time.perf_counter() - t0
            assert sol.status == NonlinearStatus.CONVERGED
        print(f"\n[BENCHMARK F8-K JFET DIAGNÓSTICO] timings={timings}")

    def test_mixed_ladder_timings(self):
        c = Circuit("kb_mixed")
        c.add(vsrc("V1", "vdd", "0", "8 V"))
        c.add(vsrc("V2", "gg", "0", "3 V"))
        c.add(res("R1", "vdd", "s1", "1 kohm"))
        c.add(mosfet("M1", "s1", "gg", "m1", "0"))
        c.add(jfet("J1", "m1", "gg", "m2"))
        c.add(shockley_diode("D1", "m2", "0"))
        t0 = time.perf_counter()
        sol = solve_nonlinear_dc(c)
        dt = time.perf_counter() - t0
        assert sol.status == NonlinearStatus.CONVERGED
        print(f"\n[BENCHMARK F8-K MIXTO DIAGNÓSTICO] elapsed={dt:.3f}s "
              f"iters={sol.provenance['iterations']}")


# --------------------------------------------------------------------------
# 16. External validation (ngspice 47 or analytic oracles)
# --------------------------------------------------------------------------

def run_ngspice(netlist: str) -> dict[str, float]:
    if not NGSPICE_EXE.is_file():
        pytest.skip("ngspice 47 binary absent")
    with tempfile.TemporaryDirectory() as tmp:
        cir = Path(tmp) / "ck.cir"
        log = Path(tmp) / "out.log"
        cir.write_text(netlist, encoding="utf-8")
        proc = subprocess.run([str(NGSPICE_EXE), "-b", "-o", str(log),
                               str(cir)], capture_output=True, text=True,
                              timeout=120)
        assert proc.returncode == 0, proc.stderr[-2000:]
        vals: dict[str, float] = {}
        for line in log.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" not in line:
                continue
            name, _, raw = line.partition("=")
            name, raw = name.strip().lower(), raw.strip().split()
            if not name or not raw:
                continue
            try:
                vals[name] = float(raw[0])
            except ValueError:
                continue  # batch-log statistics lines, not print vectors
        return vals


class TestExternal:
    def test_ngspice_mosfet_bias(self):
        got = run_ngspice(
            "* F8-K MOSFET NMOS bias\n"
            "Vdd dd 0 5\n"
            "Vgg gg 0 3\n"
            "R1 dd s 2k\n"
            "M1 s gg 0 0 nmos1\n"
            ".model nmos1 nmos(level=1 kp=200u vto=1 lambda=0.02 "
            "phi=0.6 gamma=0.5)\n"
            ".op\n"
            ".control\nrun\nprint v(s)\n.endc\n.end\n")
        c = Circuit("kx_mos")
        c.add(vsrc("V1", "dd", "0", "5 V"))
        c.add(vsrc("V2", "gg", "0", "3 V"))
        c.add(res("R1", "dd", "s", "2 kohm"))
        c.add(mosfet("M1", "s", "gg", "0", "0"))
        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        mine = float(node_v(sol, "s"))
        assert abs(mine - got["v(s)"]) / got["v(s)"] < 1e-3, (mine, got)

    def test_ngspice_zener_regulator(self):
        got = run_ngspice(
            "* F8-K Zener regulator\n"
            "V1 n1 0 10\n"
            "R1 n1 out 1k\n"
            "D1 0 out zener1\n"
            ".model zener1 D(is=1e-14 n=1 bv=5.1 ibv=1e-3)\n"
            ".op\n"
            ".control\nrun\nprint v(out)\n.endc\n.end\n")
        c = Circuit("kx_z")
        c.add(vsrc("V1", "n1", "0", "10 V"))
        c.add(res("R1", "n1", "out", "1 kohm"))
        c.add(diode_kind("D1", "0", "out", "ZENER", Vz=Q("5.1 V"),
                         nz=Q("1"), Iz=Q("1e-3 A")))
        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        mine = float(node_v(sol, "out"))
        # ngspice D breakdown knee formulation differs from the F8-K
        # piecewise-exponential branch: loose convention-tolerance check.
        assert abs(mine - 5.1) < 0.1, mine
        assert abs(got["v(out)"] - 5.1) < 0.4, got

    def test_analytic_jfet_bias_oracle(self):
        # Closed-form check independent of the solver path. With
        # VGS=-1, Vp=3 the saturation hypothesis (Vd=1.11) violates its own
        # region predicate (VDS >= VGS+Vp = 2), so the device is in triode;
        # the solver node must satisfy the triode identity exactly:
        #   Vd = Vdd - R*Idss*(2*a*b - b^2), a=1+VGS/Vp, b=Vd/Vp.
        c = Circuit("kx_j_oracle")
        c.add(vsrc("V1", "dd", "0", "10 V"))
        c.add(vsrc("V2", "gg", "0", "-1 V"))
        c.add(res("R1", "dd", "d", "2 kohm"))
        c.add(jfet("J1", "d", "gg", "0", lam_s="0"))
        sol = solve_nonlinear_dc(c)
        assert sol.status == NonlinearStatus.CONVERGED
        vd = node_v(sol, "d")
        assert vd < Decimal(2)  # triode region predicate holds
        vdd, r, idss = Decimal(10), Decimal(2000), Decimal("0.01")
        a = Decimal(1) + Decimal(-1) / Decimal(3)
        b = vd / Decimal(3)
        ident = vdd - r * idss * (Decimal(2) * a * b - b * b)
        assert abs(vd - ident) < Decimal("1E-9")
