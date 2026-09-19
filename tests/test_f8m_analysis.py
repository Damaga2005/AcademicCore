"""F8-M advanced analysis verification suite (M-001 .. M-060).

Families: M1 DC sweep, M2 parameter sweep, M3 worst-case corners,
M4 DC sensitivity, M4-AC AC sensitivity (linear), M5 native Monte Carlo.

Oracles (validation only - never production algorithms):
* closed-form circuit solutions (divider, RC, diode-with-known-I, ...);
* central finite differences ``h = max(1E-6*|p|, 1E-12)``, match ``< 1E-4``
  relative (an absolute floor of ``1E-9 * |o/p|`` only guards derivatives
  that are exactly/numerically zero, e.g. reverse-junction terms);
* ngspice 47 (skipped if the binary is absent).

Diagnostic benchmarks record counts/metrics; nothing here asserts on
wall-clock time.
"""

from __future__ import annotations

import ast
import json
import random
import subprocess
import tempfile
import time
from decimal import Decimal as D
from decimal import localcontext
from fractions import Fraction
from pathlib import Path

import pytest

from academic_core.domain.engineering.ac.operating_point import ACOperatingPoint
from academic_core.domain.engineering.ac.solver import solve_ac
from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.math.linsolve import NumericMode
from academic_core.domain.engineering.math.trig import decimal_pi, make_context
from academic_core.domain.engineering.mna import analysis as an
from academic_core.domain.engineering.mna.analysis import (
    MAX_MC_ITERATIONS,
    MAX_SWEEP_POINTS,
    MAX_WORST_PARAMS,
    GridSpec,
    MCConfig,
    MCStatus,
    NormalDist,
    ObservableSpec,
    ParamAddress,
    ParamSweepConfig,
    SweepConfig,
    SweepStatus,
    UniformDist,
    WorstCaseConfig,
    WorstCaseStatus,
    build_mc_plan,
    expand_grid,
    native_statistics,
    observable_value,
    resolve_param,
    run_monte_carlo_native,
    solve_dc_sweep,
    solve_param_sweep,
    solve_point,
    solve_worst_case,
    substitute,
)
from academic_core.domain.engineering.mna.nonlinear import (
    NonlinearStatus,
    solve_nonlinear_dc,
    solve_nonlinear_dc_state,
)
from academic_core.domain.engineering.mna.sensitivity import (
    ACSensitivityConfig,
    SensitivityConfig,
    SensitivityStatus,
    dim_sub,
    solve_ac_sensitivity,
    solve_dc_sensitivity,
)
from academic_core.domain.engineering.units import (
    Quantity,
    Unit,
    parse_quantity,
)

CTX = make_context()
SRC = Path(__file__).resolve().parents[1] / "src/academic_core/domain/engineering/mna"
NGSPICE_EXE = Path(
    r"C:\Users\dmart\Documents\ngspice-47_64\Spice64\bin\ngspice_con.exe")

KP_DIM = (-2, -4, 6, 3, 0, 0, 0)
LAM_DIM = (-1, -2, 3, 1, 0, 0, 0)
DIMLESS = (0, 0, 0, 0, 0, 0, 0)


@pytest.fixture(autouse=True)
def _wide_ambient_context():
    """Test-side arithmetic runs at 60 digits; the engine must not care
    (it only uses explicit contexts)."""
    with localcontext() as ctx:
        ctx.prec = 60
        yield


# --------------------------------------------------------------------------
# builders
# --------------------------------------------------------------------------

def Q(text: str) -> Quantity:
    return parse_quantity(text)


def kp(v: str) -> Quantity:
    return Quantity(D(v), Unit("A/V2", "A", "", KP_DIM, D(1)))


def lam(v: str) -> Quantity:
    return Quantity(D(v), Unit("1/V", "V", "", LAM_DIM, D(1)))


def dl(v: str) -> Quantity:
    return Quantity(D(v), Unit("1", "1", "", DIMLESS, D(1)))


def R(ref, a, b, v="1 kohm"):
    return Component(ref, "R", Q(v), {"1": a, "2": b})


def V(ref, p, m, v, **params):
    return Component(ref, "V", Q(v), {"+": p, "-": m}, parameters=dict(params))


def diode(ref, a, k, kind=None, **over):
    params = {"Is": Q("1e-14 A"), "n": Q("1"), "Vt": Q("0.02585 V")}
    if kind:
        params["kind"] = kind
    params.update(over)
    return Component(ref, "D", None, {"A": a, "K": k}, parameters=params)


def bjt(ref, c, b, e, polarity="NPN"):
    return Component(ref, "Q", None, {"C": c, "B": b, "E": e},
                     parameters={"polarity": polarity, "Is": Q("1e-14 A"),
                                 "Bf": Q("100"), "Br": Q("1"), "Nf": Q("1"),
                                 "Nr": Q("1"), "Vt": Q("0.02585 V")})


def mos(ref, d, g, s, b, polarity="NMOS"):
    return Component(ref, "M", None, {"D": d, "G": g, "S": s, "B": b},
                     parameters={"polarity": polarity, "Kp": kp("0.0002"),
                                 "Vto": Q("1 V"), "Lambda": lam("0.02"),
                                 "Phi": Q("0.6 V"), "Gamma": dl("0.5")})


def jfet(ref, d, g, s, polarity="NCHAN"):
    return Component(ref, "J", None, {"D": d, "G": g, "S": s},
                     parameters={"polarity": polarity, "Idss": Q("0.01 A"),
                                 "Vp": Q("3 V"), "Lambda": lam("0.01")})


def build(name, *comps):
    c = Circuit(name)
    for x in comps:
        c.add(x)
    return c


def divider(v="10 V", r1="1 kohm", r2="2 kohm"):
    return build("div", V("V1", "in", "0", v), R("R1", "in", "out", r1),
                 R("R2", "out", "0", r2))


def obs_v(node):
    return ObservableSpec("node_voltage", node)


def addr(ref, fld="value"):
    return ParamAddress(ref, fld)


def close(a, b, rel=D("1e-30"), floor=D(0)):
    a, b = D(a), D(b)
    return abs(a - b) <= rel * max(abs(a), abs(b)) + floor


# ---- circuits used by the FD-oracle matrix --------------------------------

def c_diode():
    return build("d", V("V1", "in", "0", "5 V"), R("R1", "in", "a"),
                 diode("D1", "a", "0"))


def c_led():
    return build("led", V("V1", "in", "0", "5 V"), R("R1", "in", "a"),
                 diode("D1", "a", "0", kind="LED"))


def c_zener():
    return build("z", V("V1", "in", "0", "8 V"), R("R1", "in", "out"),
                 diode("D1", "0", "out", kind="ZENER", Vz=Q("5.1 V"),
                       nz=Q("1"), Iz=Q("1e-3 A")))


def c_photo():
    return build("ph", V("V1", "in", "0", "5 V"), R("R1", "in", "k"),
                 diode("D1", "0", "k", kind="PHOTO", Iph=Q("1e-3 A")))


def c_npn():
    return build("npn", V("V1", "vcc", "0", "10 V"), R("R4", "vcc", "b", "470 kohm"),
                 R("R5", "vcc", "c"), bjt("Q1", "c", "b", "0"))


def c_pnp():
    return build("pnp", V("V1", "vcc", "0", "10 V"), R("R4", "b", "0", "470 kohm"),
                 R("R5", "c", "0"), bjt("Q1", "c", "b", "vcc", "PNP"))


def c_nmos_sat():
    return build("ms", V("V1", "dd", "0", "5 V"), V("V2", "g", "0", "3 V"),
                 R("R1", "dd", "d", "2 kohm"), mos("M1", "d", "g", "0", "0"))


def c_nmos_triode():
    return build("mt", V("V1", "dd", "0", "5 V"), V("V2", "g", "0", "5 V"),
                 R("R1", "dd", "d", "20 kohm"), mos("M1", "d", "g", "0", "0"))


def c_nmos_body():
    return build("mb", V("V1", "dd", "0", "10 V"), V("V2", "g", "0", "3 V"),
                 R("R1", "dd", "d", "5 kohm"), R("R3", "s", "0"),
                 mos("M1", "d", "g", "s", "0"))


def c_pmos():
    return build("mp", V("V1", "dd", "0", "5 V"), V("V2", "g", "0", "2 V"),
                 R("R1", "d", "0", "5 kohm"),
                 mos("M1", "d", "g", "dd", "dd", "PMOS"))


def c_jfet():
    return build("jf", V("V1", "dd", "0", "10 V"), R("R1", "dd", "d"),
                 R("R3", "s", "0", "500 ohm"), jfet("J1", "d", "0", "s"))


def c_e():
    return build("e", V("V1", "in", "0", "1 V"),
                 Component("E1", "E", Q("2"), {"+": "out", "-": "0"},
                           {"cp": "in", "cn": "0"}),
                 R("R2", "out", "0"))


def c_g():
    return build("g", V("V1", "in", "0", "1 V"),
                 Component("G1", "G", Q("1 mS"), {"+": "out", "-": "0"},
                           {"cp": "in", "cn": "0"}),
                 R("R2", "out", "0"))


def c_h():
    return build("h", V("V1", "in", "0", "1 V"), R("R1", "in", "0"),
                 Component("H1", "H", Q("500 ohm"), {"+": "out", "-": "0"},
                           {"control_ref": "R1"}), R("R2", "out", "0"))


def c_f():
    return build("f", V("V1", "in", "0", "1 V"), R("R1", "in", "0"),
                 Component("F1", "F", Q("2"), {"+": "out", "-": "0"},
                           {"control_ref": "R1"}), R("R2", "out", "0"))


def c_t():
    return build("t", V("V1", "in", "0", "1 V"),
                 Component("T1", "T", Q("2"),
                           {"1": "in", "2": "0", "3": "out", "4": "0"}, {}),
                 R("R2", "out", "0"))


# --------------------------------------------------------------------------
# FD oracle (validation only)
# --------------------------------------------------------------------------

def fd_step(p):
    """Design contract ``h = max(1E-6*|p|, 1E-12)``. The absolute floor only
    makes sense for ``|p| >~ 1E-6``; for tiny physical parameters (Is ~ 1E-14)
    it would push ``p - h`` out of the parameter domain, so the purely
    relative step ``1E-6*|p|`` is used there (documented adaptation)."""
    h = max(D("1e-6") * abs(p), D("1e-12"))
    return h if h < abs(p) / 2 else D("1e-6") * abs(p)


def fd_derivative(circuit, a, spec):
    p = resolve_param(circuit, a).nominal
    h = fd_step(p)

    def val(x):
        res, st = solve_point(substitute(circuit, {a: x}))
        assert res.status is NonlinearStatus.CONVERGED, (a.key, x, res.diagnostics)
        return observable_value(spec, st)
    return (val(p + h) - val(p - h)) / (2 * h)


def check_against_fd(circuit, a, spec):
    res = solve_dc_sensitivity(circuit, SensitivityConfig((a,), (spec,)))
    assert res.status is SensitivityStatus.COMPLETED, res.diagnostics
    got = res.observables[spec.key]["sensitivities"][a.key]["derivative"]
    ref = fd_derivative(circuit, a, spec)
    val = res.observables[spec.key]["value"]
    p = resolve_param(circuit, a).nominal
    floor = D("1e-9") * abs(val / p) if p != 0 else D(0)
    assert close(got, ref, D("1e-4"), floor), (a.key, spec.key, got, ref)
    return got


# ==========================================================================
# M-001..M-006  grids
# ==========================================================================

class TestGrids:
    def test_m001_linear_exact_sequence_and_endpoint(self):
        assert expand_grid(GridSpec.linear(D(0), D(10), D(2))) == tuple(
            D(x) for x in (0, 2, 4, 6, 8, 10))
        # stop appended iff within half a step of the last generated point
        g = expand_grid(GridSpec.linear(D(0), D(1), D("0.3")))
        assert g == (D(0), D("0.3"), D("0.6"), D("0.9"), D(1))
        g = expand_grid(GridSpec.linear(D(0), D(1), D("0.4")))
        assert g[-1] == D(1) and len(g) == 4  # 0.2 <= 0.4/2 (inclusive)
        g = expand_grid(GridSpec.linear(D(0), D(1), D("0.45")))
        assert g == (D(0), D("0.45"), D("0.90"), D(1))  # rem 0.10 <= 0.225
        g = expand_grid(GridSpec.linear(D(0), D(1), D("0.7")))
        assert g == (D(0), D("0.7"), D(1))              # rem 0.30 <= 0.35
        g = expand_grid(GridSpec.linear(D(0), D("1.3"), D("0.5")))
        assert g == (D(0), D("0.5"), D("1.0"))          # rem 0.30 >  0.25

    def test_m002_log_ratios_and_exact_endpoints(self):
        g = expand_grid(GridSpec.log(D(1), D(1000), 4))
        assert g[0] == D(1) and g[-1] == D(1000)
        for got, want in zip(g, (1, 10, 100, 1000)):
            assert close(got, want, D("1e-40")), (got, want)
        g = expand_grid(GridSpec.log(D("0.001"), D(1), 7))
        ratios = [g[i + 1] / g[i] for i in range(6)]
        assert all(close(r, ratios[0], D("1e-40")) for r in ratios)

    def test_m003_list_order_preserved(self):
        vals = (D(5), D(1), D(5), D(-2), D(3))
        assert expand_grid(GridSpec.from_list(vals)) == vals

    def test_m004_sign_direction_and_domain_errors(self):
        bad = [GridSpec.linear(D(0), D(10), D(0)),
               GridSpec.linear(D(0), D(10), D(-1)),
               GridSpec.linear(D(10), D(0), D(1)),
               GridSpec.log(D(0), D(10), 3),
               GridSpec.log(D(1), D(-10), 3),
               GridSpec.log(D(1), D(10), 0),
               GridSpec.log(D(1), D(10), 1),
               GridSpec.linear(D("NaN"), D(1), D(1)),
               GridSpec.linear(0.0, D(1), D(1)),  # float refused
               GridSpec.from_list((D(1), D("Infinity")))]
        for g in bad:
            with pytest.raises(an.InvalidCircuitError):
                expand_grid(g)

    def test_m005_empty_single_reversed(self):
        with pytest.raises(an.InvalidCircuitError):
            expand_grid(GridSpec.from_list(()))
        assert expand_grid(GridSpec.linear(D(3), D(3), D(1))) == (D(3),)
        assert expand_grid(GridSpec.log(D(2), D(2), 1)) == (D(2),)
        assert expand_grid(GridSpec.linear(D(10), D(0), D(-5))) == (
            D(10), D(5), D(0))
        assert expand_grid(GridSpec.from_list((D(7),))) == (D(7),)

    def test_m006_point_budget_is_rejection_not_truncation(self):
        n = MAX_SWEEP_POINTS
        assert len(expand_grid(GridSpec.linear(D(0), D(n - 1), D(1)))) == n
        with pytest.raises(an.InvalidCircuitError, match="MAX_SWEEP_POINTS"):
            expand_grid(GridSpec.linear(D(0), D(n), D(1)))
        with pytest.raises(an.InvalidCircuitError, match="MAX_SWEEP_POINTS"):
            expand_grid(GridSpec.log(D(1), D(10), n + 1))
        with pytest.raises(an.InvalidCircuitError, match="MAX_SWEEP_POINTS"):
            expand_grid(GridSpec.from_list(tuple(D(i) for i in range(n + 1))))
        r = solve_dc_sweep(divider(), SweepConfig(
            addr("V1"), GridSpec.linear(D(0), D(n), D(1))))
        assert r.status is SweepStatus.INVALID and r.points == ()


# ==========================================================================
# M-007..M-010  M1 DC sweep
# ==========================================================================

class TestDCSweep:
    def test_m007_divider_closed_form_per_point(self):
        c = divider()
        r = solve_dc_sweep(c, SweepConfig(
            addr("V1"), GridSpec.linear(D(-5), D(10), D("2.5")),
            (obs_v("out"),)))
        assert r.status is SweepStatus.COMPLETED
        assert len(r.points) == 7
        for p in r.points:
            vin = dict(p.parameters)["V1.value"]
            expect = vin * D(2) / D(3)
            assert close(p.observables["node_voltage:out"], expect,
                         D("1e-40"), D("1e-45")), (vin, p.observables)
        vals = [dict(p.parameters)["V1.value"] for p in r.points]
        assert vals == sorted(vals)  # monotone grid -> monotone trace

    def test_m007b_current_source_sweep_and_target_rules(self):
        c = build("i", Component("I1", "I", Q("1 mA"), {"+": "a", "-": "0"}),
                  R("R1", "a", "0", "2 kohm"))
        r = solve_dc_sweep(c, SweepConfig(
            addr("I1"), GridSpec.from_list((D("0.001"), D("0.002"))),
            (obs_v("a"),)))
        for p, w in zip(r.points, (2, 4)):
            assert close(p.observables["node_voltage:a"], w, D("1e-40"))
        # target must be an independent source value
        bad = solve_dc_sweep(divider(), SweepConfig(
            addr("R1"), GridSpec.from_list((D(1000),))))
        assert bad.status is SweepStatus.INVALID

    def test_m008_warm_start_iterations_not_worse_and_recorded(self):
        c = c_diode()
        cfg = dict(target=addr("V1"),
                   grid=GridSpec.linear(D("0.5"), D(5), D("0.5")),
                   observables=(obs_v("a"),))
        warm = solve_dc_sweep(c, SweepConfig(**cfg))
        cold = solve_dc_sweep(c, SweepConfig(**cfg, warm_start=False))
        assert warm.status is cold.status is SweepStatus.COMPLETED
        assert sum(p.iterations for p in warm.points) <= sum(
            p.iterations for p in cold.points)
        assert warm.points[0].init_mode == "cold"
        assert all(p.init_mode == "warm" and p.warm_start_used
                   for p in warm.points[1:])
        assert all(p.init_mode == "cold" and not p.warm_start_used
                   for p in cold.points)
        for pw, pc in zip(warm.points, cold.points):
            assert close(pw.observables["node_voltage:a"],
                         pc.observables["node_voltage:a"], D("1e-15"))

    def test_m009_fallback_is_recorded_never_hidden(self, monkeypatch):
        real = an.solve_point

        def flaky(circuit, x_init=None):
            if x_init is not None:
                return an.NonlinearResult(
                    status=NonlinearStatus.DIVERGED,
                    diagnostics=("injected warm failure",)), None
            return real(circuit, x_init)

        monkeypatch.setattr(an, "solve_point", flaky)
        r = solve_dc_sweep(c_diode(), SweepConfig(
            addr("V1"), GridSpec.from_list((D(1), D(2), D(3))),
            (obs_v("a"),)))
        assert r.status is SweepStatus.COMPLETED
        assert [p.init_mode for p in r.points] == [
            "cold", "warm-fallback-cold", "warm-fallback-cold"]
        assert all(p.fallback_used and p.warm_start_used
                   for p in r.points[1:])
        assert r.provenance["n_fallback"] == 2
        assert all(p.status is NonlinearStatus.CONVERGED for p in r.points)

    def test_m010_point_failure_is_honest_and_sweep_continues(self):
        r = solve_dc_sweep(c_diode(), SweepConfig(
            addr("V1"), GridSpec.from_list((D(1), D("1e6"), D(2))),
            (obs_v("a"),)))
        assert r.status is SweepStatus.COMPLETED_WITH_POINT_FAILURES
        st = [p.status for p in r.points]
        assert st[0] is NonlinearStatus.CONVERGED
        assert st[1] is NonlinearStatus.DIVERGED
        assert st[2] is NonlinearStatus.CONVERGED
        assert r.points[1].observables == {} and r.points[1].diagnostic
        assert r.points[2].init_mode == "cold-after-failure"
        assert r.provenance["n_failed"] == 1


# ==========================================================================
# M-011..M-016  M2 parameter sweep
# ==========================================================================

class TestParamSweep:
    def test_m011_value_sweep_closed_form(self):
        r = solve_param_sweep(divider(), ParamSweepConfig(
            mode="grid", target=addr("R2"),
            grid=GridSpec.log(D(100), D(10000), 5), observables=(obs_v("out"),)))
        assert r.status is SweepStatus.COMPLETED
        for p in r.points:
            r2 = dict(p.parameters)["R2.value"]
            assert close(p.observables["node_voltage:out"],
                         D(10) * r2 / (D(1000) + r2), D("1e-40"), D("1e-45"))

    @pytest.mark.parametrize("build_c,ref,fld,mono", [
        (c_diode, "D1", "Is", "dec"),        # bigger Is -> smaller Vd
        (c_nmos_sat, "M1", "Kp", "dec"),     # bigger Kp -> smaller Vd(node d)
        (c_jfet, "J1", "Idss", "inc"),       # bigger Idss -> bigger Vs
        (c_npn, "Q1", "Bf", "dec"),          # bigger Bf -> smaller Vc
    ])
    def test_m012_device_param_sweeps_monotone(self, build_c, ref, fld, mono):
        c = build_c()
        node = {"D1": "a", "M1": "d", "J1": "s", "Q1": "c"}[ref]
        nom = resolve_param(c, addr(ref, fld)).nominal
        r = solve_param_sweep(c, ParamSweepConfig(
            mode="grid", target=addr(ref, fld),
            grid=GridSpec.from_list((nom / 4, nom, nom * 4)),
            observables=(obs_v(node),)))
        assert r.status is SweepStatus.COMPLETED, [p.diagnostic for p in r.points]
        v = [p.observables[f"node_voltage:{node}"] for p in r.points]
        assert (v[0] > v[1] > v[2]) if mono == "dec" else (v[0] < v[1] < v[2])

    def test_m013_invalid_and_unsafe_addresses(self):
        c = c_zener()
        for a in (addr("R9"), addr("R1", "polarity"), addr("D1", "kind"),
                  addr("R1", "__class__"), addr("R1", "value.__class__"),
                  addr("V1", "Is"), addr("D1", "Iph"),
                  addr("R1", "parameters"), addr("R1", "pins")):
            with pytest.raises(an.InvalidCircuitError):
                resolve_param(c, a)
            r = solve_param_sweep(c, ParamSweepConfig(
                mode="grid", target=a, grid=GridSpec.from_list((D(1),))))
            assert r.status is SweepStatus.INVALID
        for bad in ("", "  ", 3, None):
            with pytest.raises(an.InvalidCircuitError):
                ParamAddress(bad, "value")
        assert resolve_param(c, addr("d1", "Vz")).nominal == D("5.1")
        # value outside the domain -> config INVALID (nothing executed)
        r = solve_param_sweep(divider(), ParamSweepConfig(
            mode="grid", target=addr("R1"), grid=GridSpec.from_list((D(0),))))
        assert r.status is SweepStatus.INVALID and r.points == ()
        # wrong dimension quantity
        with pytest.raises(an.InvalidCircuitError):
            an.coerce_value(Q("1 V"), resolve_param(
                divider(), addr("R1")).dimension, "pos", "x")

    def test_m014_multi_address_list_order_preserved(self):
        c = divider()
        pts = ({addr("R1"): D(1000), addr("R2"): D(3000)},
               {addr("R1"): D(500), addr("R2"): D(500)},
               {addr("R2"): D(1000)})
        r = solve_param_sweep(c, ParamSweepConfig(
            mode="list", points=pts, observables=(obs_v("out"),)))
        assert r.status is SweepStatus.COMPLETED
        assert [p.label for p in r.points] == ["point-0", "point-1", "point-2"]
        exp = [D(10) * D(3000) / D(4000), D(5), D(10) * 1000 / 2000]
        for p, e in zip(r.points, exp):
            assert close(p.observables["node_voltage:out"], e, D("1e-40"))
        r2 = solve_param_sweep(c, ParamSweepConfig(
            mode="list", points=pts[::-1], observables=(obs_v("out"),)))
        assert r2.digest != r.digest  # user order is significant

    def test_m015_corner_sampling_is_a_named_subset(self):
        c = divider()
        r = solve_param_sweep(c, ParamSweepConfig(
            mode="corners",
            corners=((addr("R2"), D(1800), D(2200)),
                     (addr("R1"), D(900), D(1100))),
            observables=(obs_v("out"),)))
        assert r.status is SweepStatus.COMPLETED
        assert [p.label for p in r.points] == [
            "all-low", "all-high", "R1.value:low", "R1.value:high",
            "R2.value:low", "R2.value:high"]  # 6 < 2^2 * ... subset, not 2^k
        assert close(r.points[2].observables["node_voltage:out"],
                     D(10) * 2000 / (900 + 2000), D("1e-40"))

    def test_m016_list_and_corner_config_errors(self):
        c = divider()
        assert solve_param_sweep(c, ParamSweepConfig(mode="list")).status \
            is SweepStatus.INVALID
        assert solve_param_sweep(c, ParamSweepConfig(mode="nope")).status \
            is SweepStatus.INVALID
        assert solve_param_sweep(c, ParamSweepConfig(
            mode="corners", corners=((addr("R1"), D(2), D(1)),))).status \
            is SweepStatus.INVALID
        assert solve_param_sweep(c, ParamSweepConfig(
            mode="corners", corners=((addr("R1"), D(1), D(2)),
                                     (addr("R1"), D(1), D(3))))).status \
            is SweepStatus.INVALID
        assert solve_param_sweep(c, ParamSweepConfig(
            mode="list", points=({},))).status is SweepStatus.INVALID
        assert solve_param_sweep(c, "not-a-config").status \
            is SweepStatus.INVALID


# ==========================================================================
# M-017..M-020  M3 worst case
# ==========================================================================

class TestWorstCase:
    def _wc(self):
        return solve_worst_case(divider(), WorstCaseConfig(
            ((addr("R1"), D(900), D(1100)), (addr("R2"), D(1800), D(2200))),
            (obs_v("out"),)))

    def test_m017_two_resistor_corners_extrema_and_arg_corners(self):
        w = self._wc()
        assert w.status is WorstCaseStatus.COMPLETED
        assert len(w.corners) == 4
        assert [c.label for c in w.corners] == [
            "R1.value=low|R2.value=low", "R1.value=low|R2.value=high",
            "R1.value=high|R2.value=low", "R1.value=high|R2.value=high"]
        ex = w.extrema["node_voltage:out"]
        assert close(ex["max"]["value"], D(10) * 2200 / 3100, D("1e-40"))
        assert ex["max"]["arg_corner"] == "R1.value=low|R2.value=high"
        assert close(ex["min"]["value"], D(10) * 1800 / 2900, D("1e-40"))
        assert ex["min"]["arg_corner"] == "R1.value=high|R2.value=low"
        # exhaustive reasoning: every corner value lies inside [min, max]
        for cpt in w.corners:
            assert ex["min"]["value"] <= cpt.observables["node_voltage:out"] \
                <= ex["max"]["value"]

    def test_m018_k_bounds(self):
        assert MAX_WORST_PARAMS == 10
        rs = [R(f"R{i}", f"n{i}", f"n{i + 1}") for i in range(1, 12)]
        c = build("ladder", V("V1", "n1", "0", "5 V"), *rs,
                  R("R12", "n12", "0"))
        params = tuple((addr(f"R{i}"), D(900), D(1100)) for i in range(1, 12))
        w = solve_worst_case(c, WorstCaseConfig(params, (obs_v("n6"),)))
        assert w.status is WorstCaseStatus.INVALID and w.corners == ()
        # k = 0: no range -> INVALID (documented)
        assert solve_worst_case(c, WorstCaseConfig(
            (), (obs_v("n6"),))).status is WorstCaseStatus.INVALID
        assert solve_worst_case(c, WorstCaseConfig(
            params[:1], ())).status is WorstCaseStatus.INVALID

    def test_m018b_k_equals_1_and_k_equals_10_enumerate_2k(self):
        w1 = solve_worst_case(divider(), WorstCaseConfig(
            ((addr("R1"), D(900), D(1100)),), (obs_v("out"),)))
        assert len(w1.corners) == 2
        rs = [R(f"R{i}", "in", "out") for i in range(1, 10)]
        c = build("par10", V("V1", "in", "0", "5 V"), *rs, R("R10", "out", "0"))
        params = tuple((addr(f"R{i}"), D(900), D(1100)) for i in range(1, 11))
        w = solve_worst_case(c, WorstCaseConfig(params, (obs_v("out"),)))
        assert w.status is WorstCaseStatus.COMPLETED
        assert len(w.corners) == 1024
        assert len({p.label for p in w.corners}) == 1024  # none skipped/duplicated
        ex = w.extrema["node_voltage:out"]
        # Vout = 5*R10/(R10 + Rpar): max when R10 high, all parallel R low
        picks = dict(kv.split("=") for kv in ex["max"]["arg_corner"].split("|"))
        assert picks.pop("R10.value") == "high"
        assert set(picks.values()) == {"low"} and len(picks) == 9

    def test_m019_ties_first_in_order_wins_and_are_reported(self):
        w = solve_worst_case(divider(), WorstCaseConfig(
            ((addr("R1"), D(900), D(1100)), (addr("R2"), D(1800), D(2200))),
            (obs_v("in"),)))  # 'in' is pinned by V1: all corners tie
        ex = w.extrema["node_voltage:in"]
        assert ex["min"]["arg_corner_index"] == 0
        assert ex["max"]["arg_corner_index"] == 0
        assert ex["max"]["tied_corner_indices"] == [0, 1, 2, 3]

    def test_m020_corner_extremum_is_not_global_optimum(self):
        c = build("mpt", V("V1", "in", "0", "10 V"), R("R3", "in", "n", "1 kohm"),
                  R("R2", "n", "0", "1 kohm"))
        spec = ObservableSpec("resistor_power", "R2")
        w = solve_worst_case(c, WorstCaseConfig(
            ((addr("R2"), D(200), D(3000)),), (spec,)))
        corner_max = w.extrema[spec.key]["max"]["value"]
        interior = solve_dc_sweep(c, SweepConfig(
            addr("V1"), GridSpec.from_list((D(10),)), (spec,)))
        best = interior.points[0].observables[spec.key]  # RL = RS: P = V^2/(4 RS)
        assert close(best, D("0.025"), D("1e-40"))
        assert best > corner_max  # the interior optimum beats every corner
        assert "NOT a proven global optimum" in w.scope
        assert "NOT a proven global optimum" in w.provenance["extremum_scope"]
        assert w.to_dict()["scope"] == w.scope

    def test_m020b_failed_corner_recorded_not_in_extremum(self):
        c = c_diode()
        w = solve_worst_case(c, WorstCaseConfig(
            ((addr("V1"), D(1), D("1e6")),), (obs_v("a"),)))
        assert w.status is WorstCaseStatus.COMPLETED_WITH_POINT_FAILURES
        assert w.failed_indices == (1,)
        assert w.extrema["node_voltage:a"]["max"]["arg_corner_index"] == 0


# ==========================================================================
# M-021..M-030  M4 DC sensitivity
# ==========================================================================

class TestDCSensitivity:
    def test_m021_divider_analytic_dvout_dr(self):
        c = divider()
        cfg = SensitivityConfig((addr("R1"), addr("R2"), addr("V1")),
                                (obs_v("out"),), normalized=True)
        s = solve_dc_sensitivity(c, cfg)
        assert s.status is SensitivityStatus.COMPLETED
        sens = s.observables["node_voltage:out"]["sensitivities"]
        r1, r2, v = D(1000), D(2000), D(10)
        assert close(sens["R1.value"]["derivative"],
                     -v * r2 / (r1 + r2) ** 2, D("1e-40"))
        assert close(sens["R2.value"]["derivative"],
                     v * r1 / (r1 + r2) ** 2, D("1e-40"))
        assert close(sens["V1.value"]["derivative"], r2 / (r1 + r2), D("1e-40"))
        # normalized S = (p/o) do/dp
        assert close(sens["R1.value"]["normalized"], -r1 / (r1 + r2), D("1e-40"))
        assert close(sens["V1.value"]["normalized"], D(1), D("1e-40"))

    def test_m021b_state_sensitivity_and_branch_current_thevenin(self):
        s = solve_dc_sensitivity(divider(), SensitivityConfig((addr("R1"),)))
        st = s.state["R1.value"]["values"]
        assert close(st["out"]["value"], -D(10) * 2000 / D(3000) ** 2, D("1e-40"))
        # aux current I(V1) = -V/(R1+R2) (MNA + -> - convention)
        assert close(st["I(V1)"]["value"], D(10) / D(3000) ** 2, D("1e-40"))
        assert st["out"]["dimension"] == dim_sub(
            (1, 2, -3, -1, 0, 0, 0), (1, 2, -3, -2, 0, 0, 0))
        assert st["I(V1)"]["dimension"] == dim_sub(
            (0, 0, 0, 1, 0, 0, 0), (1, 2, -3, -2, 0, 0, 0))

    @pytest.mark.parametrize("build_c,ref,fields,node", [
        (c_diode, "D1", ("Is", "n", "Vt"), "a"),
        (c_led, "D1", ("Is", "n", "Vt"), "a"),
        (c_zener, "D1", ("Is", "n", "Vt", "Vz", "nz", "Iz"), "out"),
        (c_photo, "D1", ("Is", "Iph"), "k"),
        (c_npn, "Q1", ("Is", "Bf", "Nf", "Vt"), "c"),
        (c_pnp, "Q1", ("Is", "Bf", "Nf", "Vt"), "c"),
        (c_nmos_sat, "M1", ("Kp", "Vto", "Lambda"), "d"),
        (c_nmos_triode, "M1", ("Kp", "Vto", "Lambda"), "d"),
        (c_nmos_body, "M1", ("Kp", "Vto", "Lambda", "Gamma", "Phi"), "s"),
        (c_pmos, "M1", ("Kp", "Vto", "Lambda"), "d"),
        (c_jfet, "J1", ("Idss", "Vp", "Lambda"), "s"),
    ])
    def test_m022_device_param_matches_fd_oracle(self, build_c, ref, fields, node):
        c = build_c()
        for f in fields:
            check_against_fd(c, addr(ref, f), obs_v(node))

    def test_m023_bjt_reverse_and_saturation_terms_match_fd(self):
        # saturation: both junctions forward -> Br/Nr/reverse terms matter
        c = build("sat", V("V1", "vcc", "0", "5 V"),
                  R("R4", "vcc", "b", "10 kohm"), R("R5", "vcc", "c", "4.7 kohm"),
                  bjt("Q1", "c", "b", "0"))
        for f in ("Bf", "Br", "Nf", "Nr", "Is", "Vt"):
            check_against_fd(c, addr("Q1", f), obs_v("c"))
        for f in ("Is", "Bf", "Br"):
            check_against_fd(c, addr("Q1", f), ObservableSpec(
                "device_current", "Q1:B"))

    def test_m024_gains_and_transformer_match_fd(self):
        for build_c, ref, node in ((c_e, "E1", "out"), (c_g, "G1", "out"),
                                   (c_h, "H1", "out"), (c_f, "F1", "out"),
                                   (c_t, "T1", "out")):
            check_against_fd(build_c(), addr(ref), obs_v(node))

    def test_m024b_gain_closed_forms(self):
        s = solve_dc_sensitivity(c_g(), SensitivityConfig((addr("G1"),), (obs_v("out"),)))
        # Vout = gm*Vin*R2 -> dVout/dgm = Vin*R2 = 1000
        assert close(s.observables["node_voltage:out"]["sensitivities"]
                     ["G1.value"]["derivative"], D(1000), D("1e-40"))
        s = solve_dc_sensitivity(c_e(), SensitivityConfig((addr("E1"),), (obs_v("out"),)))
        assert close(s.observables["node_voltage:out"]["sensitivities"]
                     ["E1.value"]["derivative"], D(1), D("1e-40"))

    def test_m024c_control_target_chain_matches_fd(self):
        # dVout/dR1 where H/F are current-controlled BY R1 (dform path)
        check_against_fd(c_h(), addr("R1"), obs_v("out"))
        check_against_fd(c_f(), addr("R1"), obs_v("out"))
        check_against_fd(c_h(), addr("V1"), obs_v("out"))
        check_against_fd(c_h(), addr("R2"), obs_v("out"))

    def test_m025_multi_parameter_and_observable_chain_rules(self):
        c = c_nmos_body()
        params = (addr("R1"), addr("R3"), addr("V2"), addr("M1", "Kp"))
        specs = (obs_v("d"), ObservableSpec("resistor_current", "R1"),
                 ObservableSpec("resistor_power", "R3"),
                 ObservableSpec("device_current", "M1:D"),
                 ObservableSpec("aux_current", "V1"))
        s = solve_dc_sensitivity(c, SensitivityConfig(params, specs, True))
        assert s.status is SensitivityStatus.COMPLETED
        for spec in specs:
            for a in params:
                got = s.observables[spec.key]["sensitivities"][a.key]["derivative"]
                ref = fd_derivative(c, a, spec)
                val = s.observables[spec.key]["value"]
                p = resolve_param(c, a).nominal
                assert close(got, ref, D("1e-4"), D("1e-9") * abs(val / p)), \
                    (spec.key, a.key, got, ref)

    def test_m026_normalized_zero_observable_is_null_not_zero(self):
        c = build("z", V("V1", "in", "0", "0 V"), R("R1", "in", "0"))
        s = solve_dc_sensitivity(c, SensitivityConfig(
            (addr("R1"),), (ObservableSpec("aux_current", "V1"),), True))
        assert s.status is SensitivityStatus.COMPLETED
        item = s.observables["aux_current:V1"]["sensitivities"]["R1.value"]
        assert item["normalized"] is None

    def test_m027_singular_jacobian_honest_status(self):
        c = build("sing", V("V1", "g", "0", "0 V"),
                  mos("M1", "d", "g", "0", "0"))  # 'd' has no conduction path
        s = solve_dc_sensitivity(c, SensitivityConfig(
            (addr("M1", "Kp"),), (obs_v("d"),)))
        assert s.status is SensitivityStatus.SINGULAR_JACOBIAN
        assert s.state == {} and s.observables == {}
        assert "pseudo-inverse" in s.diagnostics[0]

    def test_m028_boundary_branch_policy_documented_branch(self):
        # Vgs == Vto exactly (Gamma irrelevant at Vsb=0, but Vth=Vto+0):
        # Vov = 0 -> the model selects CUTOFF (Vov <= 0): every derivative is
        # the cutoff branch's (zero), never a smoothed/averaged value.
        c = build("bd", V("V1", "dd", "0", "5 V"), V("V2", "g", "0", "1 V"),
                  R("R1", "dd", "d", "2 kohm"), mos("M1", "d", "g", "0", "0"))
        s = solve_dc_sensitivity(c, SensitivityConfig(
            (addr("M1", "Kp"), addr("M1", "Vto"), addr("R1")),
            (obs_v("d"), ObservableSpec("device_current", "M1:D"))))
        assert s.status is SensitivityStatus.COMPLETED
        sens = s.observables["device_current:M1:D"]["sensitivities"]
        assert sens["M1.Kp"]["derivative"] == 0
        assert sens["M1.Vto"]["derivative"] == 0
        assert s.observables["node_voltage:d"]["sensitivities"]["R1.value"][
            "derivative"] == 0  # V(d) pinned at Vdd, no drain current
        # Zener exactly at Vd = 0 uses the forward (right-continuous) branch
        z = build("z0", V("V1", "in", "0", "0 V"), R("R1", "in", "a"),
                  diode("D1", "a", "0", kind="ZENER", Vz=Q("5.1 V"),
                        nz=Q("1"), Iz=Q("1e-3 A")))
        sz = solve_dc_sensitivity(z, SensitivityConfig(
            (addr("D1", "Iz"), addr("D1", "Vz")),
            (ObservableSpec("device_current", "D1"),)))
        assert sz.status is SensitivityStatus.COMPLETED
        for k in ("D1.Iz", "D1.Vz"):
            assert sz.observables["device_current:D1"]["sensitivities"][k][
                "derivative"] == 0

    def test_m029_units_carry_dimension_tuples(self):
        s = solve_dc_sensitivity(c_diode(), SensitivityConfig(
            (addr("D1", "Is"), addr("R1")), (obs_v("a"),)))
        amp = (0, 0, 0, 1, 0, 0, 0)
        volt = (1, 2, -3, -1, 0, 0, 0)
        ohm = (1, 2, -3, -2, 0, 0, 0)
        sens = s.observables["node_voltage:a"]["sensitivities"]
        assert sens["D1.Is"]["dimension"] == dim_sub(volt, amp)
        assert sens["R1.value"]["dimension"] == dim_sub(volt, ohm)
        assert dim_sub(volt, volt) == (0,) * 7

    def test_m030_config_and_point_errors_are_statuses(self):
        c = c_diode()
        cases = [
            (SensitivityConfig((), ()), SensitivityStatus.INVALID),
            (SensitivityConfig((addr("R1"), addr("R1")), ()),
             SensitivityStatus.INVALID),
            (SensitivityConfig((addr("D1", "polarity"),), ()),
             SensitivityStatus.INVALID),
            (SensitivityConfig((addr("R1"),), (obs_v("nope"),)),
             SensitivityStatus.INVALID),
            (SensitivityConfig((addr("R1"),), (ObservableSpec(
                "resistor_current", "D1"),)), SensitivityStatus.INVALID),
        ]
        for cfg, want in cases:
            assert solve_dc_sensitivity(c, cfg).status is want
        # non-converged point -> POINT_NOT_CONVERGED (no derivative numbers)
        bad = build("hv", V("V1", "in", "0", "1000000 V"), R("R1", "in", "a"),
                    diode("D1", "a", "0"))
        s = solve_dc_sensitivity(bad, SensitivityConfig((addr("R1"),), ()))
        assert s.status is SensitivityStatus.POINT_NOT_CONVERGED
        assert s.point_status == "diverged" and s.state == {}
        # MOS Phi = 0 with Gamma > 0: dVth/dPhi unbounded -> honest UNSUPPORTED
        m = build("phi0", V("V1", "dd", "0", "10 V"), V("V2", "g", "0", "3 V"),
                  R("R1", "dd", "d", "5 kohm"), R("R3", "s", "0"),
                  Component("M1", "M", None,
                            {"D": "d", "G": "g", "S": "s", "B": "0"},
                            {"polarity": "NMOS", "Kp": kp("0.0002"),
                             "Vto": Q("1 V"), "Lambda": lam("0.02"),
                             "Phi": Q("0 V"), "Gamma": dl("0.5")}))
        s = solve_dc_sensitivity(m, SensitivityConfig(
            (addr("M1", "Phi"),), (obs_v("d"),)))
        assert s.status is SensitivityStatus.UNSUPPORTED

    def test_m030b_dynamic_elements_map_to_dc_equivalent(self):
        c = build("rlc", V("V1", "in", "0", "9 V"), R("R1", "in", "a", "1 kohm"),
                  Component("L1", "L", Q("1 mH"), {"1": "a", "2": "b"}),
                  R("R2", "b", "c", "2 kohm"),
                  Component("C1", "C", Q("1 uF"), {"1": "c", "2": "0"}),
                  R("R3", "b", "0", "2 kohm"))
        s = solve_dc_sensitivity(c, SensitivityConfig(
            (addr("R1"),), (obs_v("b"),)))
        assert s.status is SensitivityStatus.COMPLETED
        # DC: V(b) = 9*R3/(R1+R3) (L short, C open, R2 dangling)
        assert close(s.observables["node_voltage:b"]["value"],
                     D(9) * 2000 / 3000, D("1e-40"))
        assert close(s.observables["node_voltage:b"]["sensitivities"]
                     ["R1.value"]["derivative"],
                     -D(9) * 2000 / D(3000) ** 2, D("1e-40"))
        # current control by a dynamic element: DC equivalent undefined
        bad = build("hc", V("V1", "in", "0", "1 V"), R("R1", "in", "a"),
                    Component("L1", "L", Q("1 mH"), {"1": "a", "2": "0"}),
                    Component("H1", "H", Q("1 kohm"), {"+": "o", "-": "0"},
                              {"control_ref": "L1"}), R("R2", "o", "0"))
        r = solve_dc_sweep(bad, SweepConfig(addr("V1"),
                                            GridSpec.from_list((D(1),))))
        assert r.status is SweepStatus.INVALID


# ==========================================================================
# M-031..M-034  M4-AC
# ==========================================================================

def c_rc():
    return build("rc", V("V1", "in", "0", "1 V"), R("R1", "in", "out"),
                 Component("C1", "C", Q("100 nF"), {"1": "out", "2": "0"}))


def c_rl_hp():
    return build("rl", V("V1", "in", "0", "1 V"),
                 Component("L1", "L", Q("10 mH"), {"1": "in", "2": "out"}),
                 R("R1", "out", "0"))


def ac_fd(circuit, a, node, f="1 kHz"):
    """Central-difference oracle of (|H|, phase, dB) - validation only."""
    p = resolve_param(circuit, a, dynamic=True).nominal
    h = fd_step(p)

    def hval(x):
        sol = solve_ac(substitute(circuit, {a: x}, dynamic=True), f,
                       NumericMode.HIGH_PRECISION)
        return sol.voltage_of(node)
    hp, hm = hval(p + h), hval(p - h)
    out = {}
    for name, fn in (
            ("mag", lambda z: z.modulus()),
            ("phase", lambda z: z.phase()),
            ("db", lambda z: D(20) * fn_log10(z.modulus()))):
        out[name] = (fn(hp) - fn(hm)) / (2 * h)
    return out


def fn_log10(x):
    return CTX.log10(x)


class TestACSensitivity:
    F = "1 kHz"

    def _omega(self):
        return ACOperatingPoint.from_frequency(self.F, "0").omega

    def test_m031_rc_lowpass_closed_form_magnitude_phase_db(self):
        c = c_rc()
        s = solve_ac_sensitivity(c, ACSensitivityConfig(
            self.F, (addr("R1"), addr("C1")), (obs_v("out"),)))
        assert s.status is SensitivityStatus.COMPLETED
        w, r, cc = self._omega(), D(1000), D("1e-7")
        m = CTX.multiply
        x = m(m(w, r), cc)
        one_x2 = CTX.add(D(1), m(x, x))
        p32 = CTX.power(one_x2, D("-1.5"))
        sens = s.observables["node_voltage:out"]["sensitivities"]
        # |H| = (1+x^2)^-1/2 ; phi = -atan(x) ; dB = -10 log10(1+x^2)
        dmag_dr = CTX.minus(m(m(x, m(w, cc)), p32))
        dmag_dc = CTX.minus(m(m(x, m(w, r)), p32))
        assert close(sens["R1.value"]["d_magnitude"], dmag_dr, D("1e-40"))
        assert close(sens["C1.value"]["d_magnitude"], dmag_dc, D("1e-40"))
        dphi_dc = CTX.minus(CTX.divide(m(w, r), one_x2))
        dphi_dr = CTX.minus(CTX.divide(m(w, cc), one_x2))
        assert close(sens["C1.value"]["d_phase_rad"], dphi_dc, D("1e-40"))
        assert close(sens["R1.value"]["d_phase_rad"], dphi_dr, D("1e-40"))
        deg = CTX.divide(D(180), decimal_pi(CTX))
        assert close(sens["C1.value"]["d_phase_deg"], m(dphi_dc, deg), D("1e-40"))
        k = CTX.divide(D(20), CTX.ln(D(10)))
        assert close(sens["R1.value"]["d_db"],
                     CTX.minus(m(k, CTX.divide(m(x, m(w, cc)), one_x2))),
                     D("1e-40"))
        assert s.observables["node_voltage:out"]["dimension"] == (
            1, 2, -3, -1, 0, 0, 0)

    @pytest.mark.parametrize("build_c,ref,node", [
        (c_rc, "R1", "out"), (c_rc, "C1", "out"), (c_rl_hp, "L1", "out"),
        (c_rl_hp, "R1", "out")])
    def test_m032_fd_oracle_rlc(self, build_c, ref, node):
        c = build_c()
        a = addr(ref)
        s = solve_ac_sensitivity(c, ACSensitivityConfig(
            self.F, (a,), (obs_v(node),)))
        it = s.observables[f"node_voltage:{node}"]["sensitivities"][a.key]
        fd = ac_fd(c, a, node, self.F)
        for got, want in ((it["d_magnitude"], fd["mag"]),
                          (it["d_phase_rad"], fd["phase"]),
                          (it["d_db"], fd["db"])):
            assert close(got, want, D("1e-4"), D("1e-9")), (ref, got, want)

    def test_m033_gains_transformer_and_control_chain_fd(self):
        def ac_chain(circ):
            return circ
        cases = [
            (build("ae", V("V1", "in", "0", "1 V"), R("R1", "in", "m"),
                   Component("C1", "C", Q("100 nF"), {"1": "m", "2": "0"}),
                   Component("E1", "E", Q("3"), {"+": "out", "-": "0"},
                             {"cp": "m", "cn": "0"}), R("R2", "out", "0")),
             "E1"),
            (build("ag", V("V1", "in", "0", "1 V"),
                   Component("G1", "G", Q("1 mS"), {"+": "out", "-": "0"},
                             {"cp": "in", "cn": "0"}),
                   R("R2", "out", "0"),
                   Component("C1", "C", Q("100 nF"), {"1": "out", "2": "0"})),
             "G1"),
            (build("ah", V("V1", "in", "0", "1 V"), R("R1", "in", "0"),
                   Component("H1", "H", Q("500 ohm"), {"+": "out", "-": "0"},
                             {"control_ref": "R1"}), R("R2", "out", "0"),
                   Component("C1", "C", Q("100 nF"), {"1": "out", "2": "0"})),
             "H1"),
            (build("af", V("V1", "in", "0", "1 V"), R("R1", "in", "0"),
                   Component("F1", "F", Q("2"), {"+": "out", "-": "0"},
                             {"control_ref": "R1"}), R("R2", "out", "0"),
                   Component("C1", "C", Q("100 nF"), {"1": "out", "2": "0"})),
             "F1"),
            (build("at", V("V1", "in", "0", "1 V"),
                   Component("T1", "T", Q("2"),
                             {"1": "in", "2": "0", "3": "out", "4": "0"}, {}),
                   R("R2", "out", "0"),
                   Component("C1", "C", Q("100 nF"), {"1": "out", "2": "0"})),
             "T1"),
        ]
        for circ, ref in cases:
            for a in (addr(ref),) + ((addr("R1"),) if ref in ("H1", "F1")
                                     else ()):
                s = solve_ac_sensitivity(circ, ACSensitivityConfig(
                    self.F, (a,), (obs_v("out"),)))
                assert s.status is SensitivityStatus.COMPLETED, s.diagnostics
                it = s.observables["node_voltage:out"]["sensitivities"][a.key]
                fd = ac_fd(circ, a, "out", self.F)
                assert close(it["d_magnitude"], fd["mag"], D("1e-4"), D("1e-9")), \
                    (ref, a.key)
                assert close(it["d_phase_rad"], fd["phase"], D("1e-4"), D("1e-9")), \
                    (ref, a.key)

    def test_m034_singular_and_out_of_scope_statuses(self):
        # conflicting ideal sources -> singular/inconsistent AC system
        bad = build("sing", V("V1", "a", "0", "1 V"), V("V2", "a", "0", "2 V"),
                    R("R1", "a", "0"))
        s = solve_ac_sensitivity(bad, ACSensitivityConfig(
            self.F, (addr("R1"),), (obs_v("a"),)))
        assert s.status is SensitivityStatus.SINGULAR_JACOBIAN
        assert s.observables == {}
        # nonlinear-device PARAMETER -> INVALID; nonlinear device in circuit
        # -> UNSUPPORTED (use F8-J small-signal)
        c = c_diode()
        s = solve_ac_sensitivity(c, ACSensitivityConfig(
            self.F, (addr("D1", "Is"),), (obs_v("a"),)))
        assert s.status is SensitivityStatus.INVALID
        s = solve_ac_sensitivity(c, ACSensitivityConfig(
            self.F, (addr("R1"),), (obs_v("a"),)))
        assert s.status is SensitivityStatus.UNSUPPORTED
        # AC source magnitude / non-'value' fields are not addressable
        s = solve_ac_sensitivity(c_rc(), ACSensitivityConfig(
            self.F, (addr("V1"),), (obs_v("out"),)))
        assert s.status is SensitivityStatus.INVALID
        for cfg in (ACSensitivityConfig("bad-freq", (addr("R1"),), (obs_v("out"),)),
                    ACSensitivityConfig(self.F, (addr("R1"),), ()),
                    ACSensitivityConfig(self.F, (addr("R1"),), (
                        ObservableSpec("resistor_power", "R1"),))):
            assert solve_ac_sensitivity(c_rc(), cfg).status \
                is SensitivityStatus.INVALID

    def test_m034b_zero_magnitude_guard(self):
        c = c_rc()
        s = solve_ac_sensitivity(c, ACSensitivityConfig(
            self.F, (addr("R1"),), (obs_v("0"),)))  # ground: identically 0
        it = s.observables["node_voltage:0"]["sensitivities"]["R1.value"]
        assert it["d_magnitude"] is None and it["d_db"] is None
        assert it["d_phase_rad"] is None


# ==========================================================================
# M-035..M-040  M5 native Monte Carlo
# ==========================================================================

def mc_divider(n=30, seed=11, dist=None):
    dist = dist or UniformDist(D(900), D(1100))
    return run_monte_carlo_native(divider(), MCConfig(
        n, ((addr("R1"), dist),), seed, (obs_v("out"),)))


class TestMonteCarlo:
    def test_m035_same_seed_identical_different_seed_differs(self):
        a, b = mc_divider(), mc_divider()
        assert a.digest == b.digest and a.plan_digest == b.plan_digest
        assert a.to_dict() == b.to_dict()
        c = mc_divider(seed=12)
        assert c.plan_digest != a.plan_digest
        sa = [i.parameters for i in a.iterations]
        sc = [i.parameters for i in c.iterations]
        assert sa != sc
        # plan builder alone is a pure function of (dists, n, seed)
        d1 = ((addr("R1"), UniformDist(D(900), D(1100))),)
        assert build_mc_plan(d1, 5, 3) == build_mc_plan(d1, 5, 3)

    def test_m036_exact_fractions_and_distributions(self):
        ectx = an._exact_ctx()
        rng = random.Random(123)
        for _ in range(200):
            bits = rng.getrandbits(53)
            u = an._frac(bits, ectx)
            assert Fraction(u) * (2 ** 53) == bits  # binary -> Decimal EXACT
            assert 0 <= u < 1
        # uniform stays inside its range; Decimal-only samples
        row = build_mc_plan(((addr("R1"), UniformDist(D(10), D(20))),), 300, 5)
        vals = [r[0][2] for r in row]
        assert all(isinstance(v, D) and D(10) <= v <= D(20) for v in vals)
        # Box-Muller moments (deterministic seed): mean 5, std 2
        nd = NormalDist(D(5), D(2), D(-100), D(100))
        vals = [an._draw(nd, s) for s in range(2000)]
        st = native_statistics(vals)
        assert abs(st["mean"] - 5) < D("0.25")      # ~5 sigma of the mean
        assert abs(st["std"] - 2) < D("0.25")

    def test_m037_statistics_exact_vs_fraction_reference(self):
        r = mc_divider(n=40, seed=3)
        vals = [i.observables["node_voltage:out"] for i in r.iterations]
        st = r.statistics["node_voltage:out"]
        fv = [Fraction(v) for v in vals]
        n = len(fv)
        mean = sum(fv) / n
        var = sum((v - mean) ** 2 for v in fv) / (n - 1)
        assert st["n"] == n
        assert close(st["mean"], D(mean.numerator) / D(mean.denominator), D("1e-40"))
        assert close(st["variance"], D(var.numerator) / D(var.denominator), D("1e-38"))
        assert close(st["std"] ** 2, st["variance"], D("1e-40"))
        assert st["min"] == min(vals) and st["max"] == max(vals)
        vs = sorted(vals)
        assert close(st["percentiles"]["p50"], (vs[19] + vs[20]) / 2, D("1e-40"))
        assert native_statistics([D(1), D(2), D(3), D(4)])["percentiles"]["p25"] \
            == D("1.75")
        assert native_statistics([D(9)])["variance"] is None
        assert native_statistics([]) == {"n": 0}

    def test_m037b_moments_vs_analytic_divider(self):
        # Vout = V1 * 2/3 with V1 ~ U(0, 10): mean 10/3, std 10*(2/3)/sqrt(12)
        r = run_monte_carlo_native(divider(), MCConfig(
            120, ((addr("V1"), UniformDist(D(0), D(10))),), 99, (obs_v("out"),)))
        st = r.statistics["node_voltage:out"]
        assert abs(st["mean"] - D(10) / 3) < D("0.75")
        assert abs(st["std"] - D(20) / 3 / CTX.sqrt(D(12))) < D("0.4")
        assert r.status is MCStatus.COMPLETED

    def test_m038_cold_solves_never_reuse_state(self):
        c = c_diode()
        cfg = MCConfig(6, ((addr("D1", "Is"),
                            UniformDist(D("1e-15"), D("1e-13"))),), 7,
                       (obs_v("a"),))
        r = run_monte_carlo_native(c, cfg)
        assert r.status is MCStatus.COMPLETED
        for it in r.iterations:
            assert it.init_mode == "cold"
            samp = {addr("D1", "Is"): dict(it.parameters)["D1.Is"]}
            res, st = solve_point(substitute(c, samp))  # standalone cold solve
            assert it.observables["node_voltage:a"] == observable_value(
                obs_v("a"), st)  # bit-identical => no state carried over
            assert it.iterations == res.system_summary["iterations"]

    def test_m039_failures_recorded_completion_preserved(self):
        r = mc_divider(n=40, seed=5, dist=UniformDist(D(-500), D(500)))
        assert r.status is MCStatus.COMPLETED_WITH_FAILURES
        assert r.failure_count == len(r.failure_indices) > 0
        assert r.failure_statuses == {"invalid_sample": r.failure_count}
        bad = {i.index for i in r.iterations if i.status != "ok"}
        assert set(r.failure_indices) == bad
        assert all(r.iterations[i].observables == {} for i in bad)
        assert r.statistics["node_voltage:out"]["n"] == 40 - r.failure_count
        # solver failures too: overflow-prone diode sample stays recorded
        c = c_diode()
        rr = run_monte_carlo_native(c, MCConfig(
            8, ((addr("V1"), UniformDist(D(1), D("1e6"))),), 4, (obs_v("a"),)))
        assert rr.status is MCStatus.COMPLETED_WITH_FAILURES
        assert set(rr.failure_statuses) <= {"diverged", "max_iterations",
                                            "singular_jacobian"}
        assert rr.failure_count + rr.statistics["node_voltage:a"]["n"] == 8
        # normal distribution outside [min,max] -> FAILED sample, no clamping
        nn = mc_divider(n=30, seed=2, dist=NormalDist(
            D(1000), D(300), D(950), D(1050)))
        assert nn.failure_count > 0
        assert all(D(950) <= dict(i.parameters)["R1.value"] <= D(1050)
                   for i in nn.iterations if i.status == "ok")

    def test_m040_bounds_seed_and_config_validation(self):
        c = divider()
        d = ((addr("R1"), UniformDist(D(900), D(1100))),)
        obs = (obs_v("out"),)
        assert MAX_MC_ITERATIONS == 10000
        cases = {
            "missing seed": MCConfig(5, d, None, obs),
            "negative seed": MCConfig(5, d, -1, obs),
            "bool seed": MCConfig(5, d, True, obs),
            "float seed": MCConfig(5, d, 1.5, obs),
            "zero iterations": MCConfig(0, d, 1, obs),
            "budget overflow": MCConfig(MAX_MC_ITERATIONS + 1, d, 1, obs),
            "no distribution": MCConfig(5, (), 1, obs),
            "dup distribution": MCConfig(5, d + d, 1, obs),
            "low>=high": MCConfig(5, ((addr("R1"), UniformDist(D(2), D(1))),), 1, obs),
            "neg std": MCConfig(5, ((addr("R1"), NormalDist(
                D(1000), D(-1), D(0), D(2000))),), 1, obs),
            "bad dist": MCConfig(5, ((addr("R1"), "uniform"),), 1, obs),
            "unknown addr": MCConfig(5, ((addr("R9"), UniformDist(D(1), D(2))),), 1, obs),
            "categorical": MCConfig(5, ((addr("R1", "polarity"), UniformDist(D(1), D(2))),), 1, obs),
        }
        for name, cfg in cases.items():
            r = run_monte_carlo_native(c, cfg)
            assert r.status is MCStatus.INVALID, name
            assert r.iterations == () and r.diagnostics, name
        r = run_monte_carlo_native(c, MCConfig(5, d, 1, obs, base="transient"))
        assert r.status is MCStatus.UNSUPPORTED  # transient-base MC is out
        # seed edge cases: 0 and 2**200 are valid and reproducible
        for seed in (0, 2 ** 200):
            a = run_monte_carlo_native(c, MCConfig(3, d, seed, obs))
            b = run_monte_carlo_native(c, MCConfig(3, d, seed, obs))
            assert a.status is MCStatus.COMPLETED and a.digest == b.digest
        # budget boundary is accepted as a config (not run: cost) - N=1 runs
        assert run_monte_carlo_native(c, MCConfig(1, d, 1, obs)).status \
            is MCStatus.COMPLETED


# ==========================================================================
# M-041..M-044  determinism
# ==========================================================================

def permuted_divider():
    return build("div", R("R2", "out", "0", "2 kohm"),
                 R("R1", "in", "out", "1 kohm"), V("V1", "in", "0", "10 V"))


class TestDeterminism:
    def test_m041_insertion_order_invariance(self):
        a, b = divider(), permuted_divider()
        assert an.circuit_digest(a) == an.circuit_digest(b)
        cfg1 = WorstCaseConfig(
            ((addr("R1"), D(900), D(1100)), (addr("R2"), D(1800), D(2200))),
            (obs_v("out"),))
        cfg2 = WorstCaseConfig(
            ((addr("R2"), D(1800), D(2200)), (addr("R1"), D(900), D(1100))),
            (obs_v("out"),))
        assert solve_worst_case(a, cfg1).digest == solve_worst_case(b, cfg2).digest
        d1 = ((addr("R1"), UniformDist(D(900), D(1100))),
              (addr("R2"), UniformDist(D(1800), D(2200))))
        m1 = run_monte_carlo_native(a, MCConfig(6, d1, 4, (obs_v("out"),)))
        m2 = run_monte_carlo_native(b, MCConfig(6, d1[::-1], 4, (obs_v("out"),)))
        assert m1.digest == m2.digest and m1.plan_digest == m2.plan_digest
        s1 = solve_dc_sensitivity(a, SensitivityConfig((addr("R1"), addr("R2")), (obs_v("out"),)))
        s2 = solve_dc_sensitivity(b, SensitivityConfig((addr("R1"), addr("R2")), (obs_v("out"),)))
        assert s1.to_dict()["observables"] == s2.to_dict()["observables"]

    def test_m042_three_identical_runs_all_families(self):
        c = c_diode()
        ac = c_rc()
        runs = []
        for _ in range(3):
            runs.append((
                solve_dc_sweep(c, SweepConfig(addr("V1"), GridSpec.linear(
                    D(1), D(5), D(1)), (obs_v("a"),))).digest,
                solve_param_sweep(c, ParamSweepConfig(
                    mode="corners", corners=((addr("R1"), D(900), D(1100)),
                                             (addr("D1", "Is"), D("1e-15"), D("1e-13"))),
                    observables=(obs_v("a"),))).digest,
                solve_worst_case(c, WorstCaseConfig(
                    ((addr("R1"), D(900), D(1100)),), (obs_v("a"),))).digest,
                json.dumps(solve_dc_sensitivity(c, SensitivityConfig(
                    (addr("R1"), addr("D1", "Is")), (obs_v("a"),), True)).to_dict(),
                    sort_keys=True),
                json.dumps(solve_ac_sensitivity(ac, ACSensitivityConfig(
                    "1 kHz", (addr("R1"), addr("C1")), (obs_v("out"),))).to_dict(),
                    sort_keys=True),
                run_monte_carlo_native(c, MCConfig(
                    5, ((addr("D1", "Is"), UniformDist(D("1e-15"), D("1e-13"))),),
                    9, (obs_v("a"),))).digest,
            ))
        assert runs[0] == runs[1] == runs[2]
        assert all(x for x in runs[0])

    def test_m043_provenance_deterministic_no_wall_clock(self):
        r = solve_dc_sweep(c_diode(), SweepConfig(
            addr("V1"), GridSpec.linear(D(1), D(3), D(1)), (obs_v("a"),)))
        blob = json.dumps(r.to_dict(), sort_keys=True).lower()
        for banned in ("timestamp", "wall", "elapsed", "datetime", "perf_counter"):
            assert banned not in blob
        prov = r.provenance
        for key in ("engine", "method", "config_digest", "circuit_digest",
                    "grid_digest", "n_points", "n_fallback", "n_failed"):
            assert key in prov
        assert prov["engine"] == "f8m-analysis/1.0"
        m = mc_divider()
        for key in ("seed", "plan_digest", "config_digest", "circuit_digest",
                    "init_mode"):
            assert key in m.provenance
        s = solve_dc_sensitivity(divider(), SensitivityConfig((addr("R1"),)))
        assert s.provenance["finite_differences_in_production"] is False
        assert s.provenance["point_solver_digest"]

    def test_m044_sequential_plan_and_input_never_mutated(self):
        c = divider()
        before = an.circuit_digest(c)
        solve_dc_sweep(c, SweepConfig(addr("V1"), GridSpec.from_list((D(3), D(4)))))
        solve_worst_case(c, WorstCaseConfig(((addr("R1"), D(1), D(2)),), (obs_v("out"),)))
        mc_divider()
        assert an.circuit_digest(c) == before
        assert c.components[0].value.to_base() == D(10)
        p = build_mc_plan(((addr("R1"), UniformDist(D(1), D(2))),
                           (addr("R2"), UniformDist(D(1), D(2)))), 4, 8)
        assert [[a.key for a, _, _ in row] for row in p] == [["R1.value", "R2.value"]] * 4


# ==========================================================================
# M-045..M-046  security / precision scans
# ==========================================================================

FILES = [SRC / "analysis.py", SRC / "sensitivity.py"]
FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__", "globals",
                   "locals", "getattr", "setattr", "delattr", "open",
                   "input", "vars"}
FORBIDDEN_MODULES = {"numpy", "scipy", "math", "cmath", "subprocess", "os",
                     "sys", "socket", "importlib", "requests", "urllib",
                     "http", "pickle", "marshal", "shutil", "ctypes"}


def _tree(path):
    return ast.parse(path.read_text(encoding="utf-8"))


class TestScans:
    def test_m045_security_ast_scan(self):
        for path in FILES:
            for node in ast.walk(_tree(path)):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    assert node.func.id not in FORBIDDEN_CALLS, (path.name, node.func.id)
                if isinstance(node, ast.Import):
                    for a in node.names:
                        assert a.name.split(".")[0] not in FORBIDDEN_MODULES, a.name
                if isinstance(node, ast.ImportFrom):
                    assert (node.module or "").split(".")[0] not in FORBIDDEN_MODULES
                if isinstance(node, ast.Attribute):
                    assert node.attr not in ("popen", "spawn", "Popen",
                                             "startfile"), node.attr
                    if isinstance(node.value, ast.Name):
                        assert (node.value.id, node.attr) != ("os", "system")

    def test_m046_float_free_and_context_explicit(self):
        for path in FILES:
            src = path.read_text(encoding="utf-8")
            assert "float(" not in src, path.name
            for node in ast.walk(_tree(path)):
                assert not (isinstance(node, ast.Constant)
                            and isinstance(node.value, float)), path.name
                # ambient-context trap class (P1): bare abs() on Decimal
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    assert node.func.id != "abs", (path.name, node.lineno)
                if isinstance(node, ast.Attribute):
                    assert node.attr not in ("getcontext", "localcontext")
        # nonlinear.py additions keep the float/eval scans clean as well
        nl = (SRC / "nonlinear.py").read_text(encoding="utf-8")
        assert "float(" not in nl and "eval(" not in nl


# ==========================================================================
# M-047..M-049  diagnostic benchmarks (metrics only, no timing gates)
# ==========================================================================

class TestBenchmarks:
    def test_m047_sweep_diagnostics(self):
        t0 = time.perf_counter()
        r = solve_dc_sweep(c_diode(), SweepConfig(
            addr("V1"), GridSpec.linear(D("0.5"), D(5), D("0.25")),
            (obs_v("a"),)))
        dt = time.perf_counter() - t0
        metrics = {"points": len(r.points),
                   "newton_iterations": sum(p.iterations for p in r.points),
                   "fallbacks": r.provenance["n_fallback"],
                   "failures": r.provenance["n_failed"], "seconds": round(dt, 3)}
        print("BENCH M1", metrics)
        assert metrics["points"] == 19 and metrics["failures"] == 0

    def test_m048_mc_diagnostics(self):
        t0 = time.perf_counter()
        r = mc_divider(n=50)
        dt = time.perf_counter() - t0
        print("BENCH M5", {"iterations": 50, "failures": r.failure_count,
                           "seconds": round(dt, 3)})
        assert r.failure_count == 0

    def test_m049_sensitivity_diagnostics(self):
        t0 = time.perf_counter()
        s = solve_dc_sensitivity(c_nmos_body(), SensitivityConfig(
            (addr("M1", "Kp"), addr("M1", "Gamma"), addr("R1")),
            (obs_v("d"),)))
        dt = time.perf_counter() - t0
        print("BENCH M4", {"linear_solves": s.provenance["n_linear_solves"],
                           "seconds": round(dt, 3)})
        assert s.provenance["n_linear_solves"] == 3
        ac = solve_ac_sensitivity(c_rc(), ACSensitivityConfig(
            "1 kHz", (addr("R1"), addr("C1")), (obs_v("out"),)))
        print("BENCH M4-AC", {"linear_solves": ac.provenance["n_linear_solves"]})
        assert ac.provenance["n_linear_solves"] == 2


# ==========================================================================
# M-050..M-052  ngspice 47 (external validation only)
# ==========================================================================

def _ngspice(netlist):
    if not NGSPICE_EXE.is_file():
        pytest.skip("ngspice 47 binary absent")
    with tempfile.TemporaryDirectory() as tmp:
        cir = Path(tmp) / "ck.cir"
        log = Path(tmp) / "out.log"
        cir.write_text(netlist, encoding="utf-8")
        proc = subprocess.run([str(NGSPICE_EXE), "-b", "-o", str(log), str(cir)],
                              capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, proc.stderr[-2000:]
        return log.read_text(encoding="utf-8").splitlines()


def _table(lines):
    rows = []
    for ln in lines:
        parts = ln.split()
        if len(parts) >= 3 and parts[0].isdigit():
            try:
                rows.append(tuple(float(x) for x in parts[1:]))
            except ValueError:
                pass
    return rows


def _scalar(lines, name):
    for ln in lines:
        if "=" in ln:
            k, _, v = ln.partition("=")
            if k.strip().lower() == name:
                return float(v.split()[0])
    raise AssertionError(f"{name} not in ngspice log")


DIODE_MODEL = ".model d1 d(is=1e-14 n=1)\n.temp 26.83\n"


class TestNgspice:
    def test_m050_dc_sweep_trace_diode_clipper(self):
        lines = _ngspice(
            "* F8-M diode DC sweep\nV1 in 0 0\nR1 in a 1k\nD1 a 0 d1\n"
            + DIODE_MODEL + ".dc V1 0 5 0.5\n.control\nrun\nprint v(a)\n"
            ".endc\n.end\n")
        rows = _table(lines)
        assert len(rows) == 11
        r = solve_dc_sweep(c_diode(), SweepConfig(
            addr("V1"), GridSpec.linear(D(0), D(5), D("0.5")), (obs_v("a"),)))
        assert r.status is SweepStatus.COMPLETED and len(r.points) == 11
        for row, p in zip(rows, r.points):
            mine = float(p.observables["node_voltage:a"])
            assert abs(mine - row[1]) <= 2e-3 * max(abs(row[1]), 1e-3) + 1e-6, (
                mine, row)

    def test_m051_corner_spot_divider_op(self):
        w = solve_worst_case(divider(), WorstCaseConfig(
            ((addr("R1"), D(900), D(1100)), (addr("R2"), D(1800), D(2200))),
            (obs_v("out"),)))
        for corner in w.corners:
            r1 = dict(corner.parameters)["R1.value"]
            r2 = dict(corner.parameters)["R2.value"]
            lines = _ngspice(
                f"* corner\nV1 in 0 10\nR1 in out {r1}\nR2 out 0 {r2}\n.op\n"
                ".control\nrun\nprint v(out)\n.endc\n.end\n")
            got = _scalar(lines, "v(out)")
            mine = float(corner.observables["node_voltage:out"])
            # ngspice batch print carries 7 significant digits
            assert abs(mine - got) / got < 1e-6, (corner.label, mine, got)

    def test_m052_corner_spot_diode_is_extremes(self):
        w = solve_worst_case(c_diode(), WorstCaseConfig(
            ((addr("D1", "Is"), D("1e-15"), D("1e-13")),), (obs_v("a"),)))
        ex = w.extrema["node_voltage:a"]
        assert ex["max"]["arg_corner"] == "D1.Is=low"
        for corner in w.corners:
            isv = dict(corner.parameters)["D1.Is"]
            lines = _ngspice(
                f"* corner\nV1 in 0 5\nR1 in a 1k\nD1 a 0 d1\n"
                f".model d1 d(is={isv} n=1)\n.temp 26.83\n.op\n.control\nrun\n"
                f"print v(a)\n.endc\n.end\n")
            got = _scalar(lines, "v(a)")
            mine = float(corner.observables["node_voltage:a"])
            assert abs(mine - got) / got < 2e-3, (corner.label, mine, got)


# ==========================================================================
# M-053..M-056  regression contract for R-01 / R-02 (full suites run separately)
# ==========================================================================

class TestRegressionContract:
    def test_m053_default_path_is_bit_identical(self):
        c = c_diode()
        a = solve_nonlinear_dc(c).to_dict()
        b = solve_nonlinear_dc(c, x_init=None).to_dict()
        assert a == b
        assert a["provenance"]["initial_guess"]["strategy"] == "zero-vector"
        res, st = solve_nonlinear_dc_state(c)
        assert res.to_dict() == a and st is not None

    def test_m054_x_init_validation(self):
        c = c_diode()
        n = solve_nonlinear_dc_state(c)[1].problem.size
        for bad in ((D(0),) * (n + 1), (D(0),) * (n - 1), (0.0,) * n,
                    (D("NaN"),) * n, "abc", 5):
            r = solve_nonlinear_dc(c, x_init=bad)
            assert r.status is NonlinearStatus.INVALID

    def test_m055_warm_start_from_solution_is_zero_iterations(self):
        c = c_diode()
        res, st = solve_nonlinear_dc_state(c)
        warm = solve_nonlinear_dc(c, x_init=st.x)
        assert warm.status is NonlinearStatus.CONVERGED
        assert warm.system_summary["iterations"] == 0
        assert warm.provenance["initial_guess"]["strategy"] == "x_init (warm-start)"
        assert [nv.voltage.to_base() for nv in warm.node_voltages] == [
            nv.voltage.to_base() for nv in res.node_voltages]

    def test_m056_state_only_when_converged(self):
        bad = build("hv", V("V1", "in", "0", "1000000 V"), R("R1", "in", "a"),
                    diode("D1", "a", "0"))
        res, st = solve_nonlinear_dc_state(bad)
        assert res.status is NonlinearStatus.DIVERGED and st is None


# ==========================================================================
# M-057..M-060  edge cases / adversarial
# ==========================================================================

class TestEdges:
    def test_m057_zero_negative_extreme_values(self):
        c = divider()
        # negative source values are legal; zero source is a legal point
        r = solve_dc_sweep(c, SweepConfig(
            addr("V1"), GridSpec.from_list((D(-10), D(0), D(10))), (obs_v("out"),)))
        v = [p.observables["node_voltage:out"] for p in r.points]
        assert close(v[0], D(-20) / 3, D("1e-40")) and v[1] == 0
        # extreme resistor magnitudes stay honest and correct
        r = solve_param_sweep(c, ParamSweepConfig(
            mode="grid", target=addr("R2"),
            grid=GridSpec.from_list((D("1e-30"), D("1e30"))), observables=(obs_v("out"),)))
        assert r.status in (SweepStatus.COMPLETED,
                            SweepStatus.COMPLETED_WITH_POINT_FAILURES)
        lo, hi = r.points
        if lo.status is NonlinearStatus.CONVERGED:
            assert lo.observables["node_voltage:out"] < D("1e-25")
        if hi.status is NonlinearStatus.CONVERGED:
            assert close(hi.observables["node_voltage:out"], D(10), D("1e-20"))
        # tiny / huge device parameters never yield a fake success
        d = solve_param_sweep(c_diode(), ParamSweepConfig(
            mode="grid", target=addr("D1", "Is"),
            grid=GridSpec.from_list((D("1e-300"), D("1e300"))),
            observables=(obs_v("a"),)))
        for p in d.points:
            if p.status is NonlinearStatus.CONVERGED:
                assert p.observables and p.iterations is not None
            else:
                assert p.observables == {} and p.diagnostic

    def test_m058_disconnected_and_invalid_circuits(self):
        floating = build("f", V("V1", "in", "0", "1 V"), R("R1", "in", "0"),
                         R("R2", "x", "y"))
        for fn in (
            lambda: solve_dc_sweep(floating, SweepConfig(addr("V1"),
                                   GridSpec.from_list((D(1),)))),
            lambda: solve_worst_case(floating, WorstCaseConfig(
                ((addr("R1"), D(1), D(2)),), (obs_v("in"),))),
            lambda: run_monte_carlo_native(floating, MCConfig(
                2, ((addr("R1"), UniformDist(D(1), D(2))),), 1, (obs_v("in"),))),
        ):
            assert fn().status.value == "invalid"
        assert solve_dc_sensitivity(floating, SensitivityConfig(
            (addr("R1"),))).status is SensitivityStatus.INVALID
        noref = build("nr", V("V1", "a", "b", "1 V"), R("R1", "a", "b"))
        assert solve_dc_sweep(noref, SweepConfig(
            addr("V1"), GridSpec.from_list((D(1),)))).status is SweepStatus.INVALID
        empty = Circuit("empty")
        assert solve_dc_sweep(empty, SweepConfig(
            addr("V1"), GridSpec.from_list((D(1),)))).status is SweepStatus.INVALID
        # unsupported element kinds are UNSUPPORTED/INVALID, never numbers
        assert solve_dc_sweep(divider(), None).status is SweepStatus.INVALID

    def test_m059_degenerate_and_single_point_sweeps(self):
        r = solve_dc_sweep(divider(), SweepConfig(
            addr("V1"), GridSpec.linear(D(4), D(4), D(1)), (obs_v("out"),)))
        assert r.status is SweepStatus.COMPLETED and len(r.points) == 1
        assert r.points[0].init_mode == "cold"
        r = solve_dc_sweep(divider(), SweepConfig(
            addr("V1"), GridSpec.from_list((D(2), D(2), D(2))), (obs_v("out"),)))
        assert len(r.points) == 3
        vs = [p.observables["node_voltage:out"] for p in r.points]
        assert all(close(v, vs[0], D("1e-30")) for v in vs)
        # duplicate observable -> INVALID
        assert solve_dc_sweep(divider(), SweepConfig(
            addr("V1"), GridSpec.from_list((D(2),)),
            (obs_v("out"), obs_v("out")))).status is SweepStatus.INVALID
        # descending sweep with warm start
        r = solve_dc_sweep(c_diode(), SweepConfig(
            addr("V1"), GridSpec.linear(D(5), D(1), D(-1)), (obs_v("a"),)))
        assert r.status is SweepStatus.COMPLETED
        assert [p.observables["node_voltage:a"] for p in r.points] == sorted(
            (p.observables["node_voltage:a"] for p in r.points), reverse=True)

    def test_m060_duplicate_params_overflow_and_budget_paths(self):
        c = divider()
        assert solve_worst_case(c, WorstCaseConfig(
            ((addr("R1"), D(1), D(2)), (addr("r1"), D(1), D(2))),
            (obs_v("out"),))).status is WorstCaseStatus.INVALID  # case-folded dup
        # exp overflow at every point -> every point failed, none faked
        hv = c_diode()
        r = solve_dc_sweep(hv, SweepConfig(
            addr("V1"), GridSpec.from_list((D("1e5"), D("1e6"), D("1e7"))),
            (obs_v("a"),)))
        assert r.status is SweepStatus.COMPLETED_WITH_POINT_FAILURES
        assert all(p.status is NonlinearStatus.DIVERGED and p.observables == {}
                   for p in r.points)
        # budgets are rejections, never truncations
        assert solve_param_sweep(c, ParamSweepConfig(
            mode="list", points=tuple({addr("R1"): D(1000)} for _ in
                                      range(MAX_SWEEP_POINTS + 1)),
            observables=(obs_v("out"),))).status is SweepStatus.INVALID
        rs = tuple((addr("R1"), D(1), D(2)) for _ in range(MAX_WORST_PARAMS + 1))
        assert solve_param_sweep(c, ParamSweepConfig(
            mode="corners", corners=rs)).status is SweepStatus.INVALID
        # substituted-circuit purity: assignments are validated, never mutate
        with pytest.raises(an.InvalidCircuitError):
            substitute(c, {addr("R1"): D(-5)})
        with pytest.raises(an.InvalidCircuitError):
            substitute(c, {addr("R1"): 1.5})
        assert c.components[1].value.to_base() == D(1000)

    def test_m060b_singular_and_nonconvergent_points_are_statuses(self):
        # floating MOS drain: Jacobian singular at the very first iteration
        c = build("sing", V("V1", "g", "0", "0.5 V"),
                  mos("M1", "d", "g", "0", "0"))
        r = solve_dc_sweep(c, SweepConfig(addr("V1"), GridSpec.from_list(
            (D("0.5"), D("0.25"))), (obs_v("d"),)))
        assert r.status is SweepStatus.COMPLETED_WITH_POINT_FAILURES
        assert all(p.status is NonlinearStatus.SINGULAR_JACOBIAN
                   and p.observables == {} for p in r.points)
        # worst-case over the same circuit: every corner recorded as failed
        w = solve_worst_case(c, WorstCaseConfig(
            ((addr("V1"), D("0.25"), D("0.5")),), (obs_v("d"),)))
        assert w.failed_indices == (0, 1)
        assert w.extrema["node_voltage:d"]["max"] is None
        assert w.to_dict()["extrema"]["node_voltage:d"]["min"] is None

    def test_m060c_out_of_range_arithmetic_is_invalid_not_an_exception(self):
        # span/step ratio beyond the 50-digit working context
        with pytest.raises(an.InvalidCircuitError):
            expand_grid(GridSpec.linear(D(0), D("1e60"), D(1)))
        r = solve_dc_sweep(divider(), SweepConfig(
            addr("V1"), GridSpec.linear(D(0), D("1e60"), D(1))))
        assert r.status is SweepStatus.INVALID and r.points == ()
        with pytest.raises(an.InvalidCircuitError):
            expand_grid(GridSpec.log(D("1e-999990"), D("9e999990"), 5))
        # distribution whose sampling arithmetic overflows: INVALID, no crash
        huge = NormalDist(D("9E+999999"), D("9E+999999"),
                          D("-9E+999999"), D("9E+999999"))
        r = mc_divider(n=3, seed=1, dist=huge)
        assert r.status is MCStatus.INVALID and r.iterations == ()
