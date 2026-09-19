"""Tests for F8-L: time-domain transient DAE analysis.

Coverage:
- Config/source/IC validation (presence, type, dimension, domain).
- Waveform evaluation (DC/step/pulse/sine) against closed forms.
- Analytic oracles: RC discharge/charge, RL step, RLC regimes.
- Method order (BE O(h), TR O(h^2)) via fixed-step halving.
- Adaptive controller: accept/reject/retry, dt shrink/grow, h_min
  termination, rollback history integrity.
- Initial conditions: zero, non-zero explicit, DC-derived, inconsistent.
- Nonlinear transients: diode rectifier, MOSFET inverter, BJT switch,
  Zener/JFET discontinuity handling.
- Determinism: repeated runs bit-identical (trajectories + stats).
- AST security + float-literal scans on the transient engine.
- Diagnostic benchmarks (no time asserts).
- ngspice 47 transient cross-check (skipped if binary absent).
"""

from __future__ import annotations

import ast
import subprocess
import tempfile
import time
from decimal import Decimal
from pathlib import Path

import pytest

from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.math.trig import (
    decimal_pi,
    decimal_sin,
    make_context,
)
from academic_core.domain.engineering.mna import (
    NonlinearStatus,
    TransientConfig,
    TransientStatus,
    build_mna_problem,
    extract_mosfet_params,
    mos_conductances,
    solve_nonlinear_dc,
    solve_transient,
)
from academic_core.domain.engineering.mna.errors import InvalidCircuitError
from academic_core.domain.engineering.mna.transient import (
    _bdf2_alphas,
    _validate_wave,
    _wave_value,
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
S_UNIT = parse_unit("s")
KP_DIM = (-2, -4, 6, 3, 0, 0, 0)
LAM_DIM = (-1, -2, 3, 1, 0, 0, 0)
DIMLESS = (0, 0, 0, 0, 0, 0, 0)

NGSPICE_EXE = Path(
    r"C:\Users\dmart\Documents\ngspice-47_64\Spice64\bin\ngspice_con.exe")


def Q(text: str) -> Quantity:
    return parse_quantity(text)


def res(ref: str, n1: str, n2: str, value: str = "1 kohm") -> Component:
    return Component(ref, "R", Q(value), {"1": n1, "2": n2})


def vsrc(ref: str, np_: str, nm: str, value: str,
         **params) -> Component:
    return Component(ref, "V", Q(value), {"+": np_, "-": nm},
                     parameters=dict(params))


def cap(ref: str, n1: str, n2: str, value: str = "1 uF",
        ic: str | None = None) -> Component:
    params: dict = {}
    if ic is not None:
        params["ic"] = Q(ic)
    return Component(ref, "C", Q(value), {"1": n1, "2": n2},
                     parameters=params)


def ind(ref: str, n1: str, n2: str, value: str = "10 mH",
        ic: str | None = None) -> Component:
    params: dict = {}
    if ic is not None:
        params["ic"] = Q(ic)
    return Component(ref, "L", Q(value), {"1": n1, "2": n2},
                     parameters=params)


def cfg(method: str = "TR", tstop: str = "0.005",
        h_init: str = "0.0001", h_min: str = "1E-7",
        h_max: str = "0.0005", reltol: str = "1E-4",
        abstol: str = "1E-7") -> TransientConfig:
    return TransientConfig(method=method, tstop=Decimal(tstop),
                           h_init=Decimal(h_init), h_min=Decimal(h_min),
                           h_max=Decimal(h_max), reltol=Decimal(reltol),
                           abstol=Decimal(abstol))


def step_cfg(method: str = "TR", tstop: str = "0.006") -> TransientConfig:
    """Tolerances for ideal-step excitations.

    A voltage step imposes an O(1) slope change: the LTE estimate scales
    as ~dSlope*h, so the controller must be allowed to shrink far below
    smooth-regime floors and the absolute tolerance must reflect the
    volt-scale signal (sub-microvolt abstol at y~0 is unresolvable).
    """
    return TransientConfig(method=method, tstop=Decimal(tstop),
                           h_init=Decimal("0.00005"),
                           h_min=Decimal("1E-12"),
                           h_max=Decimal("0.0005"),
                           reltol=Decimal("1E-4"),
                           abstol=Decimal("1E-6"))


def mosfet(ref: str, d: str, g: str, s: str, b: str,
           polarity: str = "NMOS") -> Component:
    return Component(
        ref, "M", None, {"D": d, "G": g, "S": s, "B": b},
        parameters={
            "polarity": polarity,
            "Kp": Quantity(Decimal("0.0002"),
                           Unit("A/V2", "A", "", KP_DIM, Decimal(1))),
            "Vto": Q("1 V"),
            "Lambda": Quantity(Decimal("0.02"),
                               Unit("1/V", "V", "", LAM_DIM, Decimal(1))),
            "Phi": Q("0.6 V"),
            "Gamma": Quantity(Decimal("0.5"),
                              Unit("1", "1", "", DIMLESS, Decimal(1))),
        })


def jfet(ref: str, d: str, g: str, s: str) -> Component:
    return Component(
        ref, "J", None, {"D": d, "G": g, "S": s},
        parameters={"polarity": "NCHAN", "Idss": Q("0.01 A"),
                    "Vp": Q("3 V"),
                    "Lambda": Quantity(Decimal("0.01"),
                                       Unit("1/V", "V", "", LAM_DIM,
                                            Decimal(1)))})


def bjt(ref: str, c: str, b: str, e: str) -> Component:
    return Component(ref, "Q", None, {"C": c, "B": b, "E": e},
                     parameters={"polarity": "NPN", "Is": Q("1e-14 A"),
                                 "Bf": Q("100"), "Br": Q("1"),
                                 "Nf": Q("1"), "Nr": Q("1"),
                                 "Vt": Q("0.02585 V")})


def diode(ref: str, a: str, k: str, **kw) -> Component:
    params: dict = {"Is": Q("1e-14 A"), "n": Q("1"),
                    "Vt": Q("0.02585 V")}
    params.update(kw)
    return Component(ref, "D", None, {"A": a, "K": k}, parameters=params)


def traj(sol, net: str):
    t = sol.node_trajectory(net)
    assert t is not None
    return t


# --------------------------------------------------------------------------
# 1. Config validation
# --------------------------------------------------------------------------

class TestConfig:
    def test_valid(self):
        c = cfg()
        assert c.method == "TR"

    def test_method_case(self):
        assert cfg("be").method == "BE"
        assert cfg("bdf2").method == "BDF2"

    def test_bad_method(self):
        with pytest.raises(InvalidCircuitError):
            cfg("RK4")

    def test_bad_times(self):
        with pytest.raises(InvalidCircuitError):
            cfg(tstop="0")
        with pytest.raises(InvalidCircuitError):
            cfg(h_min="0")
        with pytest.raises(InvalidCircuitError):
            cfg(h_init="1", h_max="0.5")
        with pytest.raises(InvalidCircuitError):
            cfg(h_init="1E-9", h_min="1E-7")

    def test_bad_tolerances(self):
        with pytest.raises(InvalidCircuitError):
            cfg(reltol="0")
        with pytest.raises(InvalidCircuitError):
            cfg(abstol="-1")

    def test_non_decimal_rejected(self):
        with pytest.raises(InvalidCircuitError):
            TransientConfig(method="BE", tstop=0.005,
                            h_init=Decimal("1E-4"), h_min=Decimal("1E-7"),
                            h_max=Decimal("1E-3"), reltol=Decimal("1E-4"),
                            abstol=Decimal("1E-7"))

    def test_bad_config_type_at_solve(self):
        c = Circuit("cfgx")
        c.add(vsrc("V1", "1", "0", "1 V"))
        c.add(res("R1", "1", "0"))
        sol = solve_transient(c, "BE")  # type: ignore[arg-type]
        assert sol.status == TransientStatus.INVALID


# --------------------------------------------------------------------------
# 2. Waveforms
# --------------------------------------------------------------------------

def _vcomp(**kw) -> Component:
    return Component("V1", "V", Q("5 V"), {"+": "a", "-": "0"}, parameters=kw)


class TestWaves:
    def test_no_wave_is_dc(self):
        assert _validate_wave(_vcomp()) is None
        assert _wave_value(None, Decimal(5), Decimal("3"), CTX) == 5

    def test_dc_wave(self):
        spec = _validate_wave(_vcomp(wave={"type": "dc"}))
        assert _wave_value(spec, Decimal(5), Decimal("9"), CTX) == 5

    def test_step(self):
        spec = _validate_wave(_vcomp(wave={"type": "step", "v1": Q("0 V"),
                                           "v2": Q("5 V"),
                                           "t0": Decimal("0.001")}))
        assert _wave_value(spec, Decimal(0), Decimal("0.0005"), CTX) == 0
        assert _wave_value(spec, Decimal(0), Decimal("0.001"), CTX) == 5
        assert _wave_value(spec, Decimal(0), Decimal("0.01"), CTX) == 5

    def test_pulse_shape(self):
        spec = _validate_wave(_vcomp(wave={
            "type": "pulse", "v1": Q("0 V"), "v2": Q("5 V"),
            "td": Decimal("0.001"), "tr": Decimal("0.001"),
            "tf": Decimal("0.001"), "width": Decimal("0.002"),
            "period": Decimal("0")}))
        f = lambda t: _wave_value(spec, Decimal(0), Decimal(t), CTX)
        assert f("0") == 0
        assert f("0.001") == 0
        assert f("0.0015") == Decimal("2.5")
        assert f("0.003") == 5
        assert f("0.0045") == Decimal("2.5")
        assert f("0.01") == 0

    def test_pulse_repeating(self):
        spec = _validate_wave(_vcomp(wave={
            "type": "pulse", "v1": Q("0 V"), "v2": Q("5 V"),
            "td": Decimal("0"), "tr": Decimal("0"),
            "tf": Decimal("0"), "width": Decimal("0.001"),
            "period": Decimal("0.002")}))
        f = lambda t: _wave_value(spec, Decimal(0), Decimal(t), CTX)
        assert f("0.0005") == 5
        assert f("0.0015") == 0
        assert f("0.0025") == 5

    def test_sine(self):
        spec = _validate_wave(_vcomp(wave={
            "type": "sine", "vo": Q("0 V"), "va": Q("2 V"),
            "freq": Decimal("1000"), "td": Decimal("0")}))
        f = lambda t: _wave_value(spec, Decimal(0), Decimal(t), CTX)
        assert abs(f("0")) < Decimal("1E-30")
        # Quarter period: sin(pi/2) = 1 -> 2 V.
        assert abs(f("0.00025") - Decimal(2)) < Decimal("1E-12")
        assert abs(f("0.0005")) < Decimal("1E-12")

    def test_wave_rejects_bad_type(self):
        with pytest.raises(InvalidCircuitError):
            _validate_wave(_vcomp(wave={"type": "sawtooth"}))

    def test_wave_rejects_missing_key(self):
        with pytest.raises(InvalidCircuitError):
            _validate_wave(_vcomp(wave={"type": "step", "v1": Q("0 V"),
                                        "v2": Q("5 V")}))

    def test_wave_rejects_bad_dim(self):
        with pytest.raises(InvalidCircuitError):
            _validate_wave(_vcomp(wave={"type": "step", "v1": Q("0 A"),
                                        "v2": Q("5 V"),
                                        "t0": Decimal("0.001")}))

    def test_wave_rejects_negative_time(self):
        with pytest.raises(InvalidCircuitError):
            _validate_wave(_vcomp(wave={"type": "step", "v1": Q("0 V"),
                                        "v2": Q("5 V"),
                                        "t0": Decimal("-1")}))

    def test_wave_on_resistor_rejected(self):
        r = Component("R1", "R", Q("1 kohm"), {"1": "a", "2": "0"},
                      parameters={"wave": {"type": "dc"}})
        with pytest.raises(InvalidCircuitError):
            _validate_wave(r)

    def test_ic_validation(self):
        from academic_core.domain.engineering.mna.transient import (
            _extract_ic,
        )
        assert _extract_ic(cap("C1", "a", "0", ic="2 V")) == Decimal(2)
        assert _extract_ic(ind("L1", "a", "0", ic="-3 mA")) == \
            Decimal("-0.003")
        assert _extract_ic(cap("C1", "a", "0")) is None
        with pytest.raises(InvalidCircuitError):
            _extract_ic(Component("C1", "C", Q("1 uF"), {"1": "a", "2": "0"},
                                  parameters={"ic": Q("2 A")}))
        with pytest.raises(InvalidCircuitError):
            _extract_ic(Component("C1", "C", Q("1 uF"), {"1": "a", "2": "0"},
                                  parameters={"ic": Decimal("2")}))


# --------------------------------------------------------------------------
# 3. BDF2 coefficients
# --------------------------------------------------------------------------

class TestBDF2Coeffs:
    def test_uniform_matches_design(self):
        h = Decimal("0.001")
        a0, a1, a2, uniform = _bdf2_alphas(h, h, CTX)
        assert uniform is True
        assert a0 == Decimal("1.5") / h
        assert a1 == Decimal("-2") / h
        assert a2 == Decimal("0.5") / h

    def test_startup_degenerates_to_be(self):
        h = Decimal("0.001")
        a0, a1, a2, uniform = _bdf2_alphas(h, None, CTX)
        assert uniform is False
        assert (a0, a1, a2) == (Decimal(1000), Decimal(-1000), Decimal(0))

    def test_variable_ratio(self):
        hn, hp = Decimal("0.002"), Decimal("0.001")  # r = 2
        a0, a1, a2, uniform = _bdf2_alphas(hn, hp, CTX)
        assert uniform is True
        # Consistency: a0 + a1 + a2 == 0 (exact for constants), checked
        # relatively with context-explicit ops (ambient-context arithmetic
        # would round the 50-digit coefficients to 28 digits).
        total = CTX.add(CTX.add(a0, a1), a2)
        scale = CTX.add(CTX.add(a0.copy_abs(), a1.copy_abs()),
                        a2.copy_abs())
        assert total.copy_abs() / scale < Decimal("1E-45")


# --------------------------------------------------------------------------
# 4. Analytic oracles: RC / RL / RLC
# --------------------------------------------------------------------------

def rc_discharge(method: str):
    c = Circuit("rc_dis")
    c.add(vsrc("V1", "n1", "0", "0 V"))
    c.add(res("R1", "n1", "out", "1 kohm"))
    c.add(cap("C1", "out", "0", "1 uF", ic="5 V"))
    return solve_transient(c, cfg(method, tstop="0.005", h_init="0.0001",
                                  h_min="1E-9", h_max="0.0005",
                                  reltol="1E-5", abstol="1E-8"))


class TestAnalyticRC:
    def test_discharge_all_methods(self):
        for method in ("BE", "TR", "BDF2"):
            sol = rc_discharge(method)
            assert sol.status == TransientStatus.COMPLETED, method
            v = traj(sol, "out")
            assert v[0] == 5
            expect = Decimal(5) * CTX.exp(Decimal(-5))
            assert abs(v[-1] - expect) / expect < Decimal("1E-2"), method

    def test_discharge_accuracy_tr(self):
        sol = rc_discharge("TR")
        v = traj(sol, "out")
        expect = Decimal(5) * CTX.exp(Decimal(-5))
        assert abs(v[-1] - expect) / expect < Decimal("1E-4")

    def test_charge_step(self):
        c = Circuit("rc_chg")
        c.add(vsrc("V1", "n1", "0", "5 V",
                   wave={"type": "step", "v1": Q("0 V"), "v2": Q("5 V"),
                         "t0": Decimal("0.001")}))
        c.add(res("R1", "n1", "out", "1 kohm"))
        c.add(cap("C1", "out", "0", "1 uF", ic="0 V"))
        sol = solve_transient(c, step_cfg("TR", tstop="0.006"))
        assert sol.status == TransientStatus.COMPLETED
        v = traj(sol, "out")
        times = sol.times
        # Before the step the capacitor rests at 0.
        assert v[0] == 0
        # End value: 5*(1 - exp(-5ms/1ms)) = 5*(1-e^-5).
        expect = Decimal(5) * (Decimal(1) - CTX.exp(Decimal(-5)))
        assert abs(v[-1] - expect) < Decimal("0.05")
        assert times[-1] == Decimal("0.006")


class TestAnalyticRL:
    def _rl(self, method: str):
        c = Circuit("rl_step")
        c.add(vsrc("V1", "n1", "0", "10 V",
                   wave={"type": "step", "v1": Q("0 V"), "v2": Q("10 V"),
                         "t0": Decimal("0")}))
        c.add(res("R1", "n1", "out", "100 ohm"))
        c.add(ind("L1", "out", "0", "10 mH", ic="0 A"))
        return solve_transient(c, cfg(method, tstop="0.0005",
                                      h_init="0.00001", h_min="1E-9",
                                      h_max="0.00005", reltol="1E-5",
                                      abstol="1E-8"))

    def test_step_all_methods(self):
        # i(t) = V/R*(1 - exp(-R/L*t)); tau = 0.1 ms, tstop = 5 tau.
        expect = Decimal("0.1") * (Decimal(1) - CTX.exp(Decimal(-5)))
        for method in ("BE", "TR", "BDF2"):
            sol = self._rl(method)
            assert sol.status == TransientStatus.COMPLETED, method
            il = sol.inductor_current("L1")
            assert il is not None
            assert il[0] == 0
            assert abs(il[-1] - expect) / expect < Decimal("1E-2"), method

    def test_inductor_current_trajectory_shape(self):
        sol = self._rl("TR")
        il = sol.inductor_current("L1")
        assert il is not None
        # Monotone rising toward 0.1 A.
        for a, b in zip(il, il[1:]):
            assert b >= a
        assert il[-1] > Decimal("0.09")


class TestAnalyticRLC:
    def _series(self, r: str, l: str = "10 mH", c: str = "1 uF"):
        circ = Circuit("rlc")
        circ.add(vsrc("V1", "n1", "0", "0 V"))
        circ.add(res("R1", "n1", "a", r))
        circ.add(ind("L1", "a", "b", l, ic="0 A"))
        circ.add(cap("C1", "b", "0", c, ic="5 V"))
        return circ

    def test_underdamped_period(self):
        # R=10: w0 = 1/sqrt(LC) = 10000, zeta = R/2*sqrt(C/L) = 0.05.
        # wd = w0*sqrt(1-z^2) -> T = 2*pi/wd.
        circ = self._series("10 ohm")
        sol = solve_transient(circ, cfg("TR", tstop="0.0015",
                                        h_init="0.00001", h_min="1E-8",
                                        h_max="0.00005", reltol="1E-4",
                                        abstol="1E-7"))
        assert sol.status == TransientStatus.COMPLETED
        v = traj(sol, "b")
        times = sol.times
        # Zero crossings of the decaying oscillation: find sign changes.
        crosses = [times[i] for i in range(1, len(v))
                   if (v[i - 1] > 0) != (v[i] > 0)]
        assert len(crosses) >= 4
        # Consecutive crossings are half a period apart.
        period = crosses[2] - crosses[0]
        w0 = Decimal(10000)
        zeta = Decimal("0.05")
        wd = w0 * CTX.sqrt(Decimal(1) - zeta * zeta)
        expect = CTX.divide(
            CTX.multiply(Decimal(2), decimal_pi(CTX)), wd)
        assert abs(period - expect) / expect < Decimal("0.02")

    def test_critically_damped_no_overshoot(self):
        # R = 2*sqrt(L/C) = 200 ohm: no oscillation, monotone decay.
        circ = self._series("200 ohm")
        sol = solve_transient(circ, cfg("TR", tstop="0.002",
                                        h_init="0.000005", h_min="1E-9",
                                        h_max="0.00002", reltol="1E-6",
                                        abstol="1E-9"))
        assert sol.status == TransientStatus.COMPLETED
        v = traj(sol, "b")
        assert v[0] == 5
        for a, b in zip(v, v[1:]):
            assert b <= a  # monotone, no ringing
        assert v[-1] < Decimal("0.5")

    def test_overdamped_slow_tail(self):
        circ = self._series("1000 ohm")
        sol = solve_transient(circ, cfg("BE", tstop="0.01",
                                        h_init="0.00002", h_min="1E-9",
                                        h_max="0.0001", reltol="1E-5",
                                        abstol="1E-8"))
        assert sol.status == TransientStatus.COMPLETED
        v = traj(sol, "b")
        for a, b in zip(v, v[1:]):
            assert b <= a
        # Both characteristic roots decayed (slow root tau ~ 1 ms):
        # v(10 ms) ~= 5*exp(-10.1) ~= 2e-4, no oscillation.
        assert v[-1] < Decimal("0.01")
        assert v[-1] > 0


# --------------------------------------------------------------------------
# 5. Method order (fixed-step halving)
# --------------------------------------------------------------------------

def _fixed_rc(method: str, h: str):
    c = Circuit("rc_ord")
    c.add(vsrc("V1", "n1", "0", "0 V"))
    c.add(res("R1", "n1", "out", "1 kohm"))
    c.add(cap("C1", "out", "0", "1 uF", ic="5 V"))
    return solve_transient(c, TransientConfig(
        method=method, tstop=Decimal("0.002"), h_init=Decimal(h),
        h_min=Decimal(h), h_max=Decimal(h), reltol=Decimal("1E-4"),
        abstol=Decimal("1E-7"), adaptive=False))


class TestMethodOrder:
    def _err(self, method: str, h: str) -> Decimal:
        sol = _fixed_rc(method, h)
        assert sol.status == TransientStatus.COMPLETED
        v = traj(sol, "out")
        expect = Decimal(5) * CTX.exp(Decimal("-2"))
        return abs(v[-1] - expect) / expect

    def test_be_first_order(self):
        e1 = self._err("BE", "0.0002")
        e2 = self._err("BE", "0.0001")
        assert Decimal("1.5") < e1 / e2 < Decimal("2.5")

    def test_tr_second_order(self):
        e1 = self._err("TR", "0.0002")
        e2 = self._err("TR", "0.0001")
        assert Decimal("3") < e1 / e2 < Decimal("5")

    def test_bdf2_second_order(self):
        e1 = self._err("BDF2", "0.0001")
        e2 = self._err("BDF2", "0.00005")
        assert Decimal("3") < e1 / e2 < Decimal("5")


# --------------------------------------------------------------------------
# 6. Adaptive controller
# --------------------------------------------------------------------------

class TestAdaptive:
    def _stiff_pulse(self):
        c = Circuit("ad_pulse")
        c.add(vsrc("V1", "n1", "0", "0 V",
                   wave={"type": "pulse", "v1": Q("0 V"), "v2": Q("5 V"),
                         "td": Decimal("0.001"), "tr": Decimal("0.00001"),
                         "tf": Decimal("0.00001"), "width": Decimal("0.001"),
                         "period": Decimal("0")}))
        c.add(res("R1", "n1", "out", "1 kohm"))
        c.add(cap("C1", "out", "0", "1 uF", ic="0 V"))
        return c

    def test_reject_and_retry_on_stiff_edge(self):
        sol = solve_transient(self._stiff_pulse(), cfg(
            "TR", tstop="0.004", h_init="0.0002", h_min="1E-9",
            h_max="0.0005", reltol="1E-5", abstol="1E-8"))
        assert sol.status == TransientStatus.COMPLETED
        assert sol.stats["rejected"] >= 1
        assert sol.stats["accepted"] > 10
        # History integrity: strictly increasing times, matching lengths.
        assert all(b > a for a, b in zip(sol.times, sol.times[1:]))
        assert len(sol.times) == sol.stats["accepted"] + 1

    def test_dt_grows_on_smooth_tail(self):
        sol = solve_transient(self._stiff_pulse(), cfg(
            "BE", tstop="0.01", h_init="0.00001", h_min="1E-9",
            h_max="0.002", reltol="1E-3", abstol="1E-6"))
        assert sol.status == TransientStatus.COMPLETED
        assert Decimal(sol.stats["h_last"]) > Decimal(sol.stats["h_first"])

    def test_timestep_too_small(self):
        sol = solve_transient(self._stiff_pulse(), cfg(
            "TR", tstop="0.004", h_init="0.0002", h_min="0.0001",
            h_max="0.0005", reltol="1E-12", abstol="1E-15"))
        assert sol.status == TransientStatus.TIMESTEP_TOO_SMALL
        # Rollback integrity on failure: no partial history leaks
        # (failure results carry no times/trajectories).
        assert sol.times == ()
        assert sol.node_trajectories == {}

    def test_rollback_history_integrity(self):
        sol = solve_transient(self._stiff_pulse(), cfg(
            "BDF2", tstop="0.004", h_init="0.0002", h_min="1E-9",
            h_max="0.0005", reltol="1E-5", abstol="1E-8"))
        assert sol.status == TransientStatus.COMPLETED
        assert sol.stats["rejected"] >= 1
        n = len(sol.times)
        for net, tr in sol.node_trajectories.items():
            assert len(tr) == n, net
        # Every committed state satisfies the DAE residual approximately:
        # spot-check KCL consistency via monotone-bound (no NaN blowup).
        v = traj(sol, "out")
        assert all(x.is_finite() for x in v)
        assert max(v) <= Decimal("5.5")


# --------------------------------------------------------------------------
# 7. Initial conditions
# --------------------------------------------------------------------------

class TestInitialConditions:
    def test_zero_ic(self):
        c = Circuit("ic0")
        c.add(vsrc("V1", "n1", "0", "5 V"))
        c.add(res("R1", "n1", "out", "1 kohm"))
        c.add(cap("C1", "out", "0", "1 uF", ic="0 V"))
        sol = solve_transient(c, cfg("BE", tstop="0.001"))
        assert sol.status == TransientStatus.COMPLETED
        assert traj(sol, "out")[0] == 0

    def test_dc_derived_ic(self):
        # No explicit IC: capacitor starts at the DC operating point (5 V).
        c = Circuit("icdc")
        c.add(vsrc("V1", "n1", "0", "5 V"))
        c.add(res("R1", "n1", "out", "1 kohm"))
        c.add(cap("C1", "out", "0", "1 uF"))
        sol = solve_transient(c, cfg("BE", tstop="0.001"))
        assert sol.status == TransientStatus.COMPLETED
        assert traj(sol, "out")[0] == 5

    def test_inductor_dc_derived_ic(self):
        # Inductor is a short at DC: full 10 mA through R+L at t=0.
        c = Circuit("icdl")
        c.add(vsrc("V1", "n1", "0", "10 V"))
        c.add(res("R1", "n1", "out", "1 kohm"))
        c.add(ind("L1", "out", "0", "10 mH"))
        sol = solve_transient(c, cfg("BE", tstop="0.001"))
        assert sol.status == TransientStatus.COMPLETED
        il = sol.inductor_current("L1")
        assert il is not None
        assert abs(il[0] - Decimal("0.01")) < Decimal("1E-9")

    def test_explicit_inductor_ic(self):
        c = Circuit("icil")
        c.add(vsrc("V1", "n1", "0", "0 V"))
        c.add(res("R1", "n1", "out", "100 ohm"))
        c.add(ind("L1", "out", "0", "10 mH", ic="50 mA"))
        sol = solve_transient(c, cfg("BE", tstop="0.0002"))
        assert sol.status == TransientStatus.COMPLETED
        il = sol.inductor_current("L1")
        assert il is not None
        assert il[0] == Decimal("0.05")

    def test_inconsistent_topology_rejected(self):
        # Two conflicting ideal voltage sources: DC init must fail loudly.
        c = Circuit("icbad")
        c.add(vsrc("V1", "1", "0", "5 V"))
        c.add(vsrc("V2", "1", "0", "3 V"))
        c.add(cap("C1", "1", "0", "1 uF", ic="4 V"))
        sol = solve_transient(c, cfg("BE", tstop="0.001"))
        assert sol.status == TransientStatus.INVALID


# --------------------------------------------------------------------------
# 8. Nonlinear transients
# --------------------------------------------------------------------------

class TestNonlinearTransient:
    def test_diode_rectifier(self):
        c = Circuit("nl_rect")
        c.add(vsrc("V1", "n1", "0", "0 V",
                   wave={"type": "sine", "vo": Q("0 V"), "va": Q("5 V"),
                         "freq": Decimal("50"), "td": Decimal("0")}))
        c.add(diode("D1", "n1", "out"))
        c.add(res("R1", "out", "0", "1 kohm"))
        c.add(cap("C1", "out", "0", "10 uF", ic="0 V"))
        sol = solve_transient(c, cfg("TR", tstop="0.04", h_init="0.0001",
                                     h_min="1E-8", h_max="0.001",
                                     reltol="1E-4", abstol="1E-7"))
        assert sol.status == TransientStatus.COMPLETED
        v = traj(sol, "out")
        # Half-wave rectified + filtered: stays non-negative, charges up.
        assert min(v) >= Decimal("-0.5")
        assert max(v) > Decimal("3")

    def test_mosfet_inverter(self):
        c = Circuit("nl_inv")
        c.add(vsrc("V1", "vdd", "0", "5 V"))
        c.add(vsrc("V2", "gg", "0", "0 V",
                   wave={"type": "step", "v1": Q("0 V"), "v2": Q("5 V"),
                         "t0": Decimal("0.001")}))
        c.add(res("R1", "vdd", "out", "2 kohm"))
        c.add(mosfet("M1", "out", "gg", "0", "0"))
        c.add(cap("C1", "out", "0", "100 pF", ic="5 V"))
        sol = solve_transient(c, step_cfg("BDF2", tstop="0.003"))
        assert sol.status == TransientStatus.COMPLETED
        v = traj(sol, "out")
        assert v[0] == 5
        # After the input step the NMOS pulls the output low (triode
        # steady state near 2.3 V for RD = 2 kohm).
        assert Decimal("1") < v[-1] < Decimal("2.5")

    def test_bjt_switch(self):
        c = Circuit("nl_bjt")
        c.add(vsrc("V1", "vcc", "0", "5 V"))
        c.add(vsrc("V2", "bb", "0", "0 V",
                   wave={"type": "step", "v1": Q("0 V"), "v2": Q("3 V"),
                         "t0": Decimal("0.0005")}))
        c.add(res("R1", "vcc", "cc", "1 kohm"))
        c.add(res("R2", "bb", "b", "10 kohm"))
        c.add(bjt("Q1", "cc", "b", "0"))
        sol = solve_transient(c, step_cfg("BE", tstop="0.002"))
        assert sol.status == TransientStatus.COMPLETED
        v = traj(sol, "cc")
        # Starts high (~5 V), driven toward saturation (< 0.5 V).
        assert v[0] > Decimal("4.5")
        assert v[-1] < Decimal("1")

    def test_f8k_gm_preserved_in_transient(self):
        # F8-K compatibility: the transient t=0 state coincides with the
        # certified DC operating point, and the MOSFET small-signal trio
        # there matches the certified conductance functions.
        c = Circuit("nl_gm")
        c.add(vsrc("V1", "dd", "0", "5 V"))
        c.add(vsrc("V2", "gg", "0", "3 V"))
        c.add(res("R1", "dd", "s", "2 kohm"))
        c.add(mosfet("M1", "s", "gg", "0", "0"))
        dc = solve_nonlinear_dc(c)
        assert dc.status == NonlinearStatus.CONVERGED
        vs_dc = next(n.voltage.to_base() for n in dc.node_voltages
                     if n.node == "s")
        mp = extract_mosfet_params(mosfet("M1", "s", "gg", "0", "0"))
        ctx = make_context()
        trio = mos_conductances(vs_dc, Decimal(3), Decimal(0), Decimal(0),
                                mp, ctx)
        assert trio is not None
        gm, gds, gmb = trio
        assert gm > 0 and gds > 0 and gmb > 0
        c.add(cap("C1", "s", "0", "1 nF", ic=f"{vs_dc} V"))
        sol = solve_transient(c, cfg("TR", tstop="0.00001"))
        assert sol.status == TransientStatus.COMPLETED
        # t=0 transient state == DC operating point (V-substitute at the
        # open-circuit voltage draws no current).
        assert abs(traj(sol, "s")[0] - vs_dc) < Decimal("1E-9")


# --------------------------------------------------------------------------
# 9. Discontinuity handling with F8-K devices
# --------------------------------------------------------------------------

class TestDiscontinuity:
    def _run(self, dev: Component, name: str):
        c = Circuit(name)
        c.add(vsrc("V1", "n1", "0", "0 V",
                   wave={"type": "step", "v1": Q("-5 V"), "v2": Q("5 V"),
                         "t0": Decimal("0.001")}))
        c.add(res("R1", "n1", "out", "1 kohm"))
        c.add(dev)
        c.add(cap("C1", "out", "0", "1 uF", ic="0 V"))
        return solve_transient(c, step_cfg("BDF2", tstop="0.004"))

    def test_zener_step(self):
        from academic_core.domain.engineering.units import parse_quantity as pq
        dev = Component("D1", "D", None, {"A": "out", "K": "0"},
                        parameters={"kind": "ZENER", "Is": pq("1e-14 A"),
                                    "n": pq("1"), "Vt": pq("0.02585 V"),
                                    "Vz": pq("5.1 V"), "nz": pq("1"),
                                    "Iz": pq("1e-3 A")})
        sol = self._run(dev, "dz_step")
        assert sol.status == TransientStatus.COMPLETED
        v = traj(sol, "out")
        assert all(x.is_finite() for x in v)
        # Forward clamps near +0.7 after the step.
        assert v[-1] < Decimal("1.5")

    def test_jfet_step(self):
        c = Circuit("dj_step")
        c.add(vsrc("V1", "dd", "0", "10 V"))
        c.add(vsrc("V2", "gg", "0", "-5 V",
                   wave={"type": "step", "v1": Q("0 V"), "v2": Q("-5 V"),
                         "t0": Decimal("0.001")}))
        c.add(res("R1", "dd", "d", "2 kohm"))
        c.add(jfet("J1", "d", "gg", "0"))
        sol = solve_transient(c, step_cfg("BDF2", tstop="0.004"))
        assert sol.status == TransientStatus.COMPLETED
        v = traj(sol, "d")
        assert all(x.is_finite() for x in v)

    def test_schottky_pulse(self):
        from academic_core.domain.engineering.units import parse_quantity as pq
        dev = Component("D1", "D", None, {"A": "out", "K": "0"},
                        parameters={"kind": "SCHOTTKY", "Is": pq("1e-8 A"),
                                    "n": pq("1"), "Vt": pq("0.02585 V")})
        sol = self._run(dev, "ds_pulse")
        assert sol.status == TransientStatus.COMPLETED

    def test_hf_control_by_c_rejected(self):
        c = Circuit("dj_hc")
        c.add(vsrc("V1", "a", "0", "5 V"))
        c.add(res("R1", "a", "b", "1 kohm"))
        c.add(cap("C1", "b", "0", "1 uF", ic="0 V"))
        c.add(Component("H1", "H", Q("10 ohm"), {"+": "e", "-": "0"},
                        parameters={"control_ref": "C1"}))
        c.add(res("R2", "e", "0", "1 kohm"))
        sol = solve_transient(c, cfg("BE", tstop="0.001"))
        assert sol.status == TransientStatus.INVALID


# --------------------------------------------------------------------------
# 10. Determinism
# --------------------------------------------------------------------------

class TestDeterminism:
    def _ckt(self) -> Circuit:
        c = Circuit("det_rc")
        c.add(vsrc("V1", "n1", "0", "0 V",
                   wave={"type": "pulse", "v1": Q("0 V"), "v2": Q("5 V"),
                         "td": Decimal("0.001"), "tr": Decimal("0.0001"),
                         "tf": Decimal("0.0001"), "width": Decimal("0.001"),
                         "period": Decimal("0")}))
        c.add(res("R1", "n1", "out", "1 kohm"))
        c.add(cap("C1", "out", "0", "1 uF", ic="0 V"))
        c.add(diode("D1", "out", "0"))
        return c

    def test_repeated_runs_identical(self):
        dicts = []
        for _ in range(3):
            sol = solve_transient(self._ckt(), cfg(
                "BDF2", tstop="0.004", h_init="0.00005", h_min="1E-9",
                h_max="0.0002", reltol="1E-4", abstol="1E-7"))
            assert sol.status == TransientStatus.COMPLETED
            dicts.append(sol.to_dict())
        assert dicts[0] == dicts[1] == dicts[2]

    def test_stats_reproducible(self):
        a = solve_transient(self._ckt(), cfg("TR", tstop="0.002"))
        b = solve_transient(self._ckt(), cfg("TR", tstop="0.002"))
        assert a.stats == b.stats
        assert a.times == b.times


# --------------------------------------------------------------------------
# 11. Security + float audits
# --------------------------------------------------------------------------

ENGINE_FILES = [
    "src/academic_core/domain/engineering/mna/transient.py",
    "src/academic_core/domain/engineering/mna/problem.py",
    "src/academic_core/domain/engineering/mna/nonlinear.py",
    "src/academic_core/domain/engineering/mna/mosfet.py",
    "src/academic_core/domain/engineering/mna/jfet.py",
    "src/academic_core/domain/engineering/mna/diode.py",
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
# 12. Diagnostic benchmarks (no time asserts)
# --------------------------------------------------------------------------

class TestBenchmarksDiagnostic:
    def test_rc_benchmark(self):
        c = Circuit("bk_rc")
        c.add(vsrc("V1", "n1", "0", "0 V",
                   wave={"type": "step", "v1": Q("5 V"), "v2": Q("0 V"),
                         "t0": Decimal("0")}))
        c.add(res("R1", "n1", "out", "1 kohm"))
        c.add(cap("C1", "out", "0", "1 uF", ic="5 V"))
        timings = {}
        for method in ("BE", "TR", "BDF2"):
            t0 = time.perf_counter()
            sol = solve_transient(c, cfg(method, tstop="0.005"))
            timings[method] = (time.perf_counter() - t0,
                               sol.stats["accepted"], sol.stats["rejected"],
                               sol.status.value)
            assert sol.status == TransientStatus.COMPLETED
        print(f"\n[BENCHMARK F8-L RC DIAGNÓSTICO] {timings}")

    def test_rlc_benchmark(self):
        c = Circuit("bk_rlc")
        c.add(vsrc("V1", "n1", "0", "0 V"))
        c.add(res("R1", "n1", "a", "10 ohm"))
        c.add(ind("L1", "a", "b", "10 mH", ic="0 A"))
        c.add(cap("C1", "b", "0", "1 uF", ic="5 V"))
        t0 = time.perf_counter()
        sol = solve_transient(c, cfg("BDF2", tstop="0.005",
                                     h_init="0.00002", h_min="1E-9",
                                     h_max="0.0002", reltol="1E-3",
                                     abstol="1E-6"))
        dt = time.perf_counter() - t0
        assert sol.status == TransientStatus.COMPLETED
        print(f"\n[BENCHMARK F8-L RLC DIAGNÓSTICO] elapsed={dt:.3f}s "
              f"accepted={sol.stats['accepted']} "
              f"rejected={sol.stats['rejected']} "
              f"newton={sol.stats['newton_total']}")

    def test_nonlinear_benchmark(self):
        c = Circuit("bk_nl")
        c.add(vsrc("V1", "n1", "0", "0 V",
                   wave={"type": "sine", "vo": Q("0 V"), "va": Q("5 V"),
                         "freq": Decimal("50"), "td": Decimal("0")}))
        c.add(diode("D1", "n1", "out"))
        c.add(res("R1", "out", "0", "1 kohm"))
        c.add(cap("C1", "out", "0", "10 uF", ic="0 V"))
        c.add(mosfet("M1", "out", "out", "0", "0"))
        t0 = time.perf_counter()
        sol = solve_transient(c, cfg("TR", tstop="0.04"))
        dt = time.perf_counter() - t0
        assert sol.status == TransientStatus.COMPLETED
        print(f"\n[BENCHMARK F8-L NO-LINEAL DIAGNÓSTICO] elapsed={dt:.3f}s "
              f"accepted={sol.stats['accepted']} "
              f"rejected={sol.stats['rejected']}")


# --------------------------------------------------------------------------
# 13. External validation (ngspice 47 or analytic cross-check)
# --------------------------------------------------------------------------

def run_ngspice_tran(netlist: str) -> dict:
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
        return {"stdout": proc.stdout, "log": log.read_text(encoding="utf-8")}


class TestExternal:
    def test_ngspice_rc_charging(self):
        # RC charging toward 5 V; compare several time samples parsed
        # from the ngspice batch log against the AcademicCore trajectory.
        out = run_ngspice_tran(
            "* F8-L RC charge\n"
            "V1 n1 0 PULSE(0 5 0 10u 10u 10m 20m)\n"
            "R1 n1 out 1k\n"
            "C1 out 0 1u\n"
            ".tran 0.1m 5m\n"
            ".control\nrun\nprint v(out)\n.endc\n.end\n")
        import re
        pairs = []
        for line in out["log"].splitlines():
            m = re.match(r"\s*(\d+)\s+([\d.eE+-]+)\s+([\d.eE+-]+)", line)
            if m:
                try:
                    pairs.append((float(m.group(2)), float(m.group(3))))
                except ValueError:
                    continue
        assert len(pairs) >= 5, out["log"][-1500:]
        c = Circuit("kx_rc")
        c.add(vsrc("V1", "n1", "0", "0 V",
                   wave={"type": "pulse", "v1": Q("0 V"), "v2": Q("5 V"),
                         "td": Decimal("0"), "tr": Decimal("0.00001"),
                         "tf": Decimal("0.00001"), "width": Decimal("0.01"),
                         "period": Decimal("0.02")}))
        c.add(res("R1", "n1", "out", "1 kohm"))
        c.add(cap("C1", "out", "0", "1 uF", ic="0 V"))
        sol = solve_transient(c, cfg("TR", tstop="0.005", h_init="0.00005",
                                     h_min="1E-12", h_max="0.0002",
                                     reltol="1E-4", abstol="1E-6"))
        assert sol.status == TransientStatus.COMPLETED
        for tn, vn in pairs[:: max(1, len(pairs) // 6)][:6]:
            mine = sol.value_at("out", Decimal(str(tn)))
            assert mine is not None
            assert abs(float(mine) - vn) < 0.15, (tn, vn, mine)
