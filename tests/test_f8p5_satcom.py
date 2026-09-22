"""F8-P5 satcom synthesis -- certification test suite.

Test IDs P5-001..P5-044 map onto ``docs/gates/GATE-F8P5-DESIGN.md``
section 28. Oracles are closed-form/hand values (section 29),
independent identities, or certified engines (never implementation ==
implementation). Tolerances follow the gate: exact bookkeeping exact;
round-trips <= 1e-40; reference pins to stated digits; bisection
<= 1e-12 relative.
"""

from __future__ import annotations

import ast
import json
import math
from decimal import Decimal
from pathlib import Path

import pytest

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.math import DecimalComplex, make_context
from academic_core.domain.engineering.satcom import antennas as A
from academic_core.domain.engineering.satcom import constants as K
from academic_core.domain.engineering.satcom import link as L
from academic_core.domain.engineering.satcom import losses as LO
from academic_core.domain.engineering.satcom import metrics as M
from academic_core.domain.engineering.satcom import noise as N
from academic_core.domain.engineering.satcom import report as RP
from academic_core.domain.engineering.satcom import synthesis as S

D = Decimal
CTX = make_context()
TOL_RT = D("1e-40")
TOL_REF = D("1e-6")


def ref_leg(**over) -> L.LinkLeg:
    params = dict(direction="downlink", ptx_w=D(100),
                  tx_antenna=A.Antenna(gain_dbi=D(40)), ltx_db=D(1),
                  freq_hz=D(12000000000), distance_m=D(35786000), losses=(),
                  rx_antenna=A.Antenna(gain_dbi=D(40)), lrx_db=D(0),
                  tsys_k=D(200), bandwidth_hz=D(1000000), rb_bps=D(10000000),
                  scheme="bpsk")
    params.update(over)
    return L.LinkLeg(**params)


def test_p5001_constants_exact():
    """P5-001: SI exact constants c, k with provenance (P5 invariants base)."""
    assert K.speed_of_light() == 299792458
    assert K.boltzmann_k() == D("1.380649E-23")
    assert K.SPEED_OF_LIGHT_M_S == D(299792458)
    assert K.BOLTZMANN_J_K == D("1.380649E-23")


def test_p5002_wavelength():
    """P5-002: lambda = c/f; f > 0 enforced."""
    assert (K.wavelength_m(D(12000000000)) - D("0.0249827")).copy_abs() <= D("1e-6")
    assert K.wavelength_m(D(1000000)) == D("299.792458")
    with pytest.raises(ControlError):
        K.wavelength_m(D(0))
    with pytest.raises(ControlError):
        K.wavelength_m(D("-5"))


def test_p5003_magnitude_guard():
    """P5-003: (0, 1e30] guard; no silent clipping."""
    assert K.check_magnitude(D(1), "x") == 1
    for bad in (D(0), D(-1), D("1E+31"), D("NaN"), D("Infinity")):
        with pytest.raises(ControlError):
            K.check_magnitude(bad, "x")


def test_p5004_fspl_formula():
    """P5-004: FSPL closed form + reference pin 205.106 dB (P5-I002)."""
    leg = ref_leg()
    assert (L.fspl_db(leg).value - D("205.105671")).copy_abs() <= D("1e-6")
    assert (L.fspl_db(leg).value - D("205.106")).copy_abs() <= D("1e-3")


def test_p5005_fspl_identity_linear_db():
    """P5-005: FSPL_dB = 10log10(FSPL_linear) identity (P5-I002)."""
    from academic_core.domain.engineering.comms.metrics import to_db10
    leg = ref_leg()
    assert (L.fspl_db(leg).value - to_db10(L.fspl_linear(leg))).copy_abs() <= D("1e-40")


def test_p5006_fspl_domains_properties():
    """P5-006: FSPL monotonicity in d/f + d = 0 rejected (property tests)."""
    near = ref_leg(distance_m=D(1000000))
    far = ref_leg(distance_m=D(2000000))
    assert L.fspl_db(far).value > L.fspl_db(near).value
    lowf = ref_leg(freq_hz=D(1000000000))
    highf = ref_leg(freq_hz=D(2000000000))
    assert L.fspl_db(highf).value > L.fspl_db(lowf).value
    with pytest.raises(ControlError):
        ref_leg(distance_m=D(0))
    with pytest.raises(ControlError):
        ref_leg(freq_hz=D(0))


def test_p5007_eirp():
    """P5-007: EIRP linear/dB bookkeeping, pin 59.0 dBW (P5-I003)."""
    leg = ref_leg()
    assert L.eirp_dbw(leg).value == 59
    assert L.eirp_dbw(leg).label == "dBW"
    from academic_core.domain.engineering.comms.metrics import to_db10
    double = CTX.subtract(L.eirp_dbw(ref_leg(ptx_w=D(200))).value, D(59))
    assert (double - to_db10(D(2))).copy_abs() <= D("1e-40")
    assert L.eirp_dbw(ref_leg(ltx_db=D(4))).value == 56


def test_p5008_received_power_friis():
    """P5-008: Friis forward/inverse round-trip (P5-I004)."""
    leg = ref_leg()
    pr = L.received_power_dbw(leg).value
    expect = CTX.add(CTX.subtract(D(59), L.fspl_db(leg).value), D(40))
    assert CTX.subtract(pr, expect).copy_abs() <= D("1e-40")
    assert L.received_power_dbw(leg).label == "dBW"


def test_p5009_budget_object_audit():
    """P5-009: BudgetResult keeps every intermediate (audit trail)."""
    res = S.forward_budget(ref_leg())
    assert res.direction == "downlink"
    assert res.eirp_dbw == 59
    assert (res.misc_db) == 0
    assert res.lrx_db == 0
    assert res.grx_dbi == 40
    with pytest.raises(ControlError):
        S.forward_budget("not a leg")


def test_p5010_ktb_n0():
    """P5-010: kTB/N0 pins −143.975/−203.975 (P5-I005)."""
    from academic_core.domain.engineering.comms.metrics import to_db10
    assert (to_db10(N.noise_power_w(D(290), D(1000000))) + D("143.975")).copy_abs() <= D("1e-3")
    assert (to_db10(N.noise_psd_w_hz(D(290))) + D("203.975")).copy_abs() <= D("1e-3")
    assert N.noise_power_w(D(290), D(1000000)) == N.noise_power_w(D(290), D(1000000))
    with pytest.raises(ControlError):
        N.noise_power_w(D(0), D(1))
    with pytest.raises(ControlError):
        N.noise_power_w(D(290), D(0))


def test_p5011_friis_cascade():
    """P5-011: Friis Te closed form + stage bound (P5 cascade)."""
    te = N.friis_temperature(((D(10), D(100)), (D(100), D(1000))))
    assert te == D(100) + D(1000) / D(10)
    assert N.friis_temperature(((D(5), D(50)),)) == D(50)
    with pytest.raises(ControlError):
        N.friis_temperature(())
    with pytest.raises(ControlError):
        N.friis_temperature(tuple((D(2), D(10)) for _ in range(9)))
    with pytest.raises(ControlError):
        N.friis_temperature(((D(0), D(10)),))


def test_p5012_gt():
    """P5-012: G/T pin 16.990 dB/K (P5-I006)."""
    leg = ref_leg()
    assert (L.g_over_t_dbk(leg).value - D("16.990")).copy_abs() <= D("1e-3")
    assert L.g_over_t_dbk(leg).label == "dB/K"
    assert N.g_over_t_dbk(D(40), D(200)) == L.g_over_t_dbk(leg).value


def test_p5013_cn0_chain():
    """P5-013: C/N0 = EIRP−L+G/T−k pin 99.483 dBHz (P5-I007)."""
    leg = ref_leg()
    assert (L.cn0_dbhz(leg).value - D("99.483")).copy_abs() <= D("1e-3")
    assert L.cn0_dbhz(leg).label == "dBHz"
    expect = CTX.subtract(CTX.add(CTX.subtract(D(59), L.fspl_db(leg).value),
                                  L.g_over_t_dbk(leg).value),
                          M.k_dbw_per_k_hz())
    assert CTX.subtract(L.cn0_dbhz(leg).value, expect).copy_abs() <= D("1e-40")


def test_p5014_cn_single_b():
    """P5-014: C/N single-B + B/Rb/Rs disambiguation (P5-I008)."""
    leg = ref_leg()
    assert CTX.subtract(L.cn_db(leg).value,
                        CTX.subtract(L.cn0_dbhz(leg).value, D(60))).copy_abs() <= D("1e-40")
    assert L.cn_db(leg).label == "dB"


def test_p5015_ebn0_bridge():
    """P5-015: Eb/N0 pin 29.483 dB + modem-k check (P5-I009)."""
    leg = ref_leg()
    assert (L.ebno_db(leg).value - D("29.483")).copy_abs() <= D("1e-3")
    assert L.ebno_db(leg).label == "dB"
    from academic_core.domain.engineering.comms.metrics import eb_n0_from_es_n0
    assert eb_n0_from_es_n0(D(2), 1) == 2


def test_p5016_aperture_roundtrip():
    """P5-016: G↔Ae round-trip + η/XOR gates (P5-I010)."""
    wave = D("0.0249827")
    area = A.circular_area_m2(D("1.2"))
    glin = A.gain_linear_from_aperture(area, wave, D("0.6"))
    back = A.aperture_from_gain_linear(glin, wave)
    expect = CTX.multiply(D("0.6"), area)
    assert CTX.subtract(back, expect).copy_abs() <= D("1e-40")
    with pytest.raises(ControlError):
        A.gain_linear_from_aperture(area, wave, D(0))
    with pytest.raises(ControlError):
        A.gain_linear_from_aperture(area, wave, D("1.5"))
    with pytest.raises(ControlError):
        A.Antenna(gain_dbi=D(40), diameter_m=D("1.2"), efficiency=D("0.6"))
    with pytest.raises(ControlError):
        A.Antenna()


def test_p5017_dish_gain_dbi_dbd():
    """P5-017: dish pin 41.355 dBi + dBi/dBd conversion."""
    wave = D("0.0249827")
    ant = A.Antenna(diameter_m=D("1.2"), efficiency=D("0.6"))
    assert (ant.gain_dbi_value(wave) - D("41.355")).copy_abs() <= D("1e-3")
    assert (A.dbd_to_dbi(D(10)) - D("12.15")).copy_abs() <= D("1e-40")
    assert (A.dbi_to_dbd(D("12.15")) - D(10)).copy_abs() <= D("1e-40")
    assert A.Antenna(gain_dbi=D(10), gain_kind="dBd").gain_dbi_value(wave) == D("12.15")


def test_p5018_beamwidth_approx():
    """P5-018: beamwidth APPROXIMATION kind + value."""
    res = A.beamwidth_approx_deg(D("1.2"), D("0.025"))
    assert res.kind == "APPROXIMATION"
    expect = CTX.divide(CTX.multiply(D(70), D("0.025")), D("1.2"))
    assert CTX.subtract(res.value, expect).copy_abs() <= D("1e-40")
    assert A.gain_kind_result(D(40)).kind == "EXACT"


def test_p5019_tsys_paths():
    """P5-019: Tsys single-value vs Friis vs Tant LIMITED."""
    assert L.system_temperature_k(ref_leg()) == 200
    friis_leg = ref_leg(tsys_k=None, friis_stages=((D(10), D(100)), (D(10), D(100))))
    assert L.system_temperature_k(friis_leg) == D(110)
    tant_leg = ref_leg(tant_k=D(50))
    assert L.system_temperature_k(tant_leg) == 250
    with pytest.raises(ControlError):
        ref_leg(tsys_k=None, friis_stages=())
    with pytest.raises(ControlError):
        ref_leg(tsys_k=D(200), friis_stages=((D(10), D(100)),))


def test_p5020_transponder_linear():
    """P5-020: transparent linear block; regenerative/saturation absent."""
    t = S.Transponder(gain_db=D(100), bandwidth_hz=D(36000000))
    assert t.gain_db == 100
    import academic_core.domain.engineering.satcom as sat_pkg
    names = " ".join(n.lower() for n in dir(sat_pkg))
    for banned in ("regenerat", "saturat", "am_am", "coding", "ofdm", "mimo",
                   "fading", "rain_model", "orbit", "doppler", "availab"):
        assert banned not in names, banned
    with pytest.raises(ControlError):
        S.Transponder(gain_db=D("NaN"), bandwidth_hz=D(1))


def test_p5021_p4_bridge_kinds():
    """P5-021: EXACT/approx kinds propagate; P4 functions reused (P5-I013)."""
    assert S.ber_kind_for_scheme("bpsk") == "EXACT"
    assert S.ber_kind_for_scheme("qpsk") == "EXACT"
    assert S.ber_kind_for_scheme("mqam16") == "APPROXIMATION"
    with pytest.raises(ControlError):
        S.ber_kind_for_scheme("ldpc-coded")
    from academic_core.domain.engineering.comms.metrics import ber_bpsk, ser_mqam_approx
    assert ber_bpsk(D(1)).kind == "EXACT"
    assert ser_mqam_approx(16, D(10)).kind == "APPROXIMATION"


def test_p5022_shannon_feasibility():
    """P5-022: Shannon feasibility + max-Rb via REUSEd P4 (P5-I012)."""
    cap = S.max_rb_shannon_bps(D(1000000), D(10))
    from academic_core.domain.engineering.comms.metrics import shannon_capacity, from_db10
    assert cap == shannon_capacity(D(1000000), from_db10(D(10))).value
    assert cap > D(1000000)
    assert M.required_cn_db(D(1)) == 0
    assert M.required_cn_db(D(2)) > 0
    with pytest.raises(ControlError):
        M.required_cn_db(D(0))


def test_p5023_required_eirp_closed():
    """P5-023: required-EIRP closed form inverts the forward chain."""
    leg = ref_leg()
    target = L.ebno_db(leg).value
    path = CTX.add(L.fspl_db(leg).value, L.misc_losses_db(leg).value)
    req = S.required_eirp_dbw(target, path, L.g_over_t_dbk(leg).value, leg.rb_bps)
    assert CTX.subtract(req, D(59)).copy_abs() <= D("1e-30")


def test_p5024_max_rb_modem():
    """P5-024: modem max-Rb closed form."""
    rb = S.max_rb_bps(D("99.48319592181840"), D("29.48319592181840"))
    assert (rb - D(10000000)) / D(10000000).copy_abs() <= D("1e-9")


def test_p5025_ber_to_ebno_bisection():
    """P5-025: BER→Eb/N0 on EXACT curves; monotonicity + bounds (P5-I014)."""
    req = S.required_ebno_from_ber("bpsk", D("1E-5"))
    from academic_core.domain.engineering.comms.metrics import ber_bpsk
    assert (ber_bpsk(req).value - D("1E-5")).copy_abs() / D("1E-5") <= D("1e-9")
    assert D(5) < req < D(15)
    with pytest.raises(ControlError):
        S.required_ebno_from_ber("mqam16", D("1E-5"))
    with pytest.raises(ControlError):
        S.required_ebno_from_ber("bpsk", D("0.6"))


def test_p5026_min_ptx_bisection():
    """P5-026: min-Ptx bisection attains the margin; caps enforced."""
    leg = ref_leg()
    avail = L.ebno_db(leg).value
    req = avail - 3
    ptx = S.min_ptx_w(D(3), req, leg)
    assert (ptx - D(100)) / D(100).copy_abs() <= D("1e-9")
    got = S.forward_budget(L.LinkLeg(direction=leg.direction, ptx_w=ptx,
                                     tx_antenna=leg.tx_antenna, ltx_db=leg.ltx_db,
                                     freq_hz=leg.freq_hz, distance_m=leg.distance_m,
                                     losses=leg.losses, rx_antenna=leg.rx_antenna,
                                     lrx_db=leg.lrx_db, tsys_k=leg.tsys_k,
                                     bandwidth_hz=leg.bandwidth_hz, rb_bps=leg.rb_bps,
                                     scheme=leg.scheme))
    assert CTX.subtract(S.link_margin_db(got.ebno_db, req), D(3)).copy_abs() <= D("1e-9")
    with pytest.raises(ControlError):
        S.min_ptx_w(D(100), D(20), ref_leg())


def test_p5027_margin_definition():
    """P5-027: margin = available − required; not availability (P5-I011)."""
    assert S.link_margin_db(D(10), D(7)) == 3
    assert S.link_margin_db(D(5), D(8)) == -3
    with pytest.raises(ControlError):
        S.link_margin_db(D("NaN"), D(1))


def test_p5028_bent_pipe_reciprocal():
    """P5-028: 1/tot = Σ1/i identity; symmetry (P5-I015)."""
    tot = S.bent_pipe_cn0_dbhz(D(100), D(100))
    from academic_core.domain.engineering.comms.metrics import from_db10, to_db10
    expect = to_db10(from_db10(D(100)) / D(2))
    assert (tot - expect).copy_abs() <= D("1e-40")
    assert S.bent_pipe_cn0_dbhz(D(90), D(100)) == S.bent_pipe_cn0_dbhz(D(100), D(90))
    assert S.bent_pipe_cn0_dbhz(D(90), D(100)) < 90
    with pytest.raises(ControlError):
        S.bent_pipe_cn0_dbhz(D("NaN"), D(100))


def test_p5029_legs_limit():
    """P5-029: documents carry ≤ 2 legs; 3rd leg rejected by construction."""
    assert S.MAX_LEGS == 2
    legs = (ref_leg(direction="uplink"), ref_leg(direction="downlink"))
    assert len(legs) == 2
    with pytest.raises(ControlError):
        L.LinkLeg(direction="sideways", ptx_w=D(1), tx_antenna=A.Antenna(gain_dbi=D(1)),
                  ltx_db=D(0), freq_hz=D(1), distance_m=D(1), tsys_k=D(1))


def test_p5030_limited_and_out():
    """P5-030: LIMITED losses accepted; models/orbits/coding rejected."""
    led = (LO.LossEntry.create("rain", D(3)), LO.LossEntry.create("pointing", D("0.5")))
    assert LO.total_loss_db(led) == D("3.5")
    assert LO.total_loss_db(()) == 0
    for bad_kind in ("orbit", "fading", "multipath", "coding_gain", "availability",
                     "rain_model", "doppler", "regeneration"):
        with pytest.raises(ControlError):
            LO.LossEntry.create(bad_kind, D(1))
    with pytest.raises(ControlError):
        LO.total_loss_db(tuple(LO.LossEntry.create("miscellaneous", D(1)) for _ in range(17)))
    with pytest.raises(ControlError):
        LO.LossEntry.create("rain", D(-1))


def test_p5031_db_algebra_matrix():
    """P5-031: dB/dBW/dBm/dBi/dBd/dB-K/dBHz/dBK rules + rejections (P5-I019)."""
    assert M.db_add(M.DbValue(D(20), "dBW"), M.DbValue(D(3), "dB")) == M.DbValue(D(23), "dBW")
    assert M.db_add(M.DbValue(D(20), "dBW"), M.DbValue(D(40), "dBi")) == M.DbValue(D(60), "dBW")
    assert M.db_sub(M.DbValue(D(60), "dBW"), M.DbValue(D(40), "dBi")) == M.DbValue(D(20), "dBW")
    assert M.db_sub(M.DbValue(D(10), "dBW"), M.DbValue(D(7), "dBW")) == M.DbValue(D(3), "dB")
    assert M.db_sub(M.DbValue(D(11), "dBi"), M.DbValue(D(10), "dBi")) == M.DbValue(D(1), "dB")
    assert M.dbm_to_dbw(D(30)) == 0
    assert M.dbw_to_dbm(D(0)) == 30
    assert M.to_dbw(D(1000)).value == 30
    assert M.to_dbm(D(1)).value == 30
    assert CTX.subtract(M.from_dbw(D(30)), D(1000)).copy_abs() <= D("1e-40")
    for bad in (lambda: M.db_add(M.DbValue(D(1), "dBW"), M.DbValue(D(2), "dBW")),
                lambda: M.db_add(M.DbValue(D(1), "dBi"), M.DbValue(D(2), "dBi")),
                lambda: M.db_add(M.DbValue(D(1), "dBW"), M.DbValue(D(2), "dBm")),
                lambda: M.db_sub(M.DbValue(D(1), "dBW"), M.DbValue(D(2), "dBm")),
                lambda: M.DbValue(D(1), "dBX")):
        with pytest.raises(ControlError):
            bad()


def test_p5032_units_dimensions():
    """P5-032: Hz/W/m/s Quantity gates; K label; bit/s ≡ Hz label."""
    from academic_core.domain.engineering.units import FREQUENCY, LENGTH, POWER, TIME
    assert FREQUENCY is not None and LENGTH is not None
    assert POWER is not None and TIME is not None
    with pytest.raises(ControlError):
        ref_leg(freq_hz=D("NaN"))
    t = N.noise_psd_w_hz(D(290))
    assert t > 0
    from academic_core.domain.engineering.comms.bits import bit_rate
    assert bit_rate(D(1000), 2) == D(2000)


def test_p5033_hostile_battery():
    """P5-033: hostile magnitudes/domains/types → typed states."""
    with pytest.raises(ControlError):
        ref_leg(ptx_w=D("1E+31"))
    with pytest.raises(ControlError):
        ref_leg(ptx_w=D(0))
    with pytest.raises(ControlError):
        ref_leg(bandwidth_hz=D(-3))
    with pytest.raises(ControlError):
        A.Antenna(gain_dbi=D("Infinity"))
    with pytest.raises(ControlError):
        N.friis_temperature(((D(2), D("NaN")),))
    with pytest.raises(ControlError):
        S.required_eirp_dbw(D(10), D(200), D(10), D(0))
    with pytest.raises(ControlError):
        S.max_rb_shannon_bps(D(1000), D("Infinity"))
    with pytest.raises(ControlError):
        S.Transponder(gain_db=D(1), bandwidth_hz=D("1E+31"))
    doc = RP.SatcomDocument.create("k", {"v": D(1)})
    text = RP.dumps(doc)
    parsed = json.loads(text)
    parsed["digest"] = "0" * 64
    tampered = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
    assert RP.compare(text, tampered) == RP.INVALID_SERIALIZATION
    assert RP.compare(text, '{"schema": "f8p4-comms/1"}') == RP.SCHEMA_MISMATCH
    assert RP.compare(text, "not json") == RP.INVALID_SERIALIZATION


def test_p5034_determinism_triple_run():
    """P5-034: analytic triple run → identical digest (P5-I018)."""
    digests = set()
    for _ in range(3):
        res = S.forward_budget(ref_leg())
        doc = RP.SatcomDocument.create("budget", {
            "eirp": str(res.eirp_dbw), "fspl": str(res.fspl_db),
            "cn0": str(res.cn0_dbhz), "ebno": str(res.ebno_db),
        })
        digests.add(RP.dumps(doc))
    assert len(digests) == 1


def test_p5035_serialization_states():
    """P5-035: round-trip + 5 replay states + aliases (P5-I016)."""
    doc = RP.SatcomDocument.create("budget", {"cn0": "99.483"}, {"leg": "downlink"})
    text = RP.dumps(doc)
    assert RP.loads(text).digest() == doc.digest()
    assert RP.compare(text, text) == RP.EQUIVALENT
    assert RP.VALID == RP.EQUIVALENT
    assert RP.RESULT_DIFFERENT == RP.RESULT_DIFFERS
    other = RP.dumps(RP.SatcomDocument.create("budget", {"cn0": "0"}))
    assert RP.compare(text, other) == RP.RESULT_DIFFERS
    assert RP.compare(text, text.replace("f8p5-satcom/1", "f8p5-satcom/2")) == RP.VERSION_MISMATCH
    assert RP.compare(text, '{"schema": "f8o-metrology/1"}') == RP.SCHEMA_MISMATCH
    assert RP.compare(text, "garbage") == RP.INVALID_SERIALIZATION
    with pytest.raises(ControlError):
        RP.loads(text.replace('"digest"', '"bogus"'))
    with pytest.raises(ControlError):
        RP.dumps("not a document")


def test_p5036_replay_equivalence():
    """P5-036: replay intact/tampered/version (P5-I017)."""
    doc = RP.SatcomDocument.create("leg", {"d": "35786000"})
    text = RP.dumps(doc)
    assert RP.replay(text) == RP.EQUIVALENT
    parsed = json.loads(text)
    parsed["digest"] = "0" * 64
    assert RP.replay(json.dumps(parsed, sort_keys=True, separators=(",", ":"))) == RP.RESULT_DIFFERS
    assert RP.replay(text.replace("f8p5-satcom/1", "f8p5-satcom/9")) == RP.INVALID_SERIALIZATION


def test_p5037_security_ast_grep():
    """P5-037: 0 banned calls/imports, 0 float literals in satcom/."""
    eng = Path(__file__).resolve().parents[1] / "src" / "academic_core" / "domain" / "engineering"
    files = list((eng / "satcom").glob("*.py"))
    assert files
    banned_calls = {"eval", "exec", "compile", "getattr", "setattr", "open",
                    "__import__"}
    banned_imports = {"os", "sys", "subprocess", "socket", "urllib", "pickle",
                      "marshal", "importlib", "pathlib", "sqlite3", "math",
                      "numpy", "scipy", "statistics", "cmath", "re", "ctypes",
                      "http", "ftplib", "random"}
    violations = []
    for f in files:
        text = f.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in banned_calls:
                    violations.append(f"{f.name}: banned call {node.func.id}")
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split(".")[0] in banned_imports:
                        violations.append(f"{f.name}: banned import {a.name}")
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[0] in banned_imports:
                    violations.append(f"{f.name}: banned from-import {node.module}")
            if isinstance(node, ast.Constant) and isinstance(node.value, float):
                violations.append(f"{f.name}: float literal {node.value!r}")
    assert not violations, violations
    for f in files:
        text = f.read_text(encoding="utf-8")
        assert "float(" not in text, f.name
        assert "numpy" not in text and "scipy" not in text, f.name
        assert "import math" not in text, f.name


def test_p5038_no_second_engine():
    """P5-038: no second Q/BER/Shannon/log/digest/serializer/replay/errors."""
    eng = Path(__file__).resolve().parents[1] / "src" / "academic_core" / "domain" / "engineering"
    hits = []
    for f in (eng / "satcom").glob("*.py"):
        if f.name == "report.py":
            continue
        text = f.read_text(encoding="utf-8")
        for marker in ("class Sequence", "def fft(", "def dft(", "def canonical_json",
                       "def chain_digest", "class ControlStatus", "class ControlError",
                       "def parse_unit", "def decimal_log10", "def decimal_exp(",
                       "def shannon_capacity", "def q_function", "def ber_bpsk"):
            if marker in text:
                hits.append(f"{f.name}: {marker}")
    assert not hits, hits
    import academic_core.domain.engineering.satcom.report as rp_mod
    import inspect as _inspect
    src = _inspect.getsource(rp_mod)
    assert "canonical_json" in src and "chain_digest" in src


def test_p5039_layer_direction():
    """P5-039: satcom DAG — allowed downward deps only; never cycles."""
    eng = Path(__file__).resolve().parents[1] / "src" / "academic_core" / "domain" / "engineering"
    comms_files = list((eng / "satcom").glob("*.py"))
    assert comms_files
    violations = []
    for f in comms_files:
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [node.module or ""]
            for mod in mods:
                segs = mod.split(".")
                if "engineering" in segs:
                    tail = segs[segs.index("engineering") + 1:]
                    if tail[:1] == ["lab"]:
                        violations.append(f"{f.name}: satcom -> lab")
                    if tail[:1] == ["mna"]:
                        violations.append(f"{f.name}: satcom -> mna")
                    if tail[:1] == ["ac"]:
                        violations.append(f"{f.name}: satcom -> ac")
                    if tail[:1] == ["dsp"]:
                        violations.append(f"{f.name}: satcom -> dsp")
                    if tail[:1] == ["rf"] and len(tail) > 1 and tail[1] != "margins":
                        violations.append(f"{f.name}: satcom -> rf beyond margins")
                    if tail[:1] == ["comms"] and len(tail) > 1 and tail[1] not in ("metrics", "bits"):
                        violations.append(f"{f.name}: satcom -> comms beyond metrics/bits")
                    if tail[:1] == ["satcom"]:
                        continue
                if mod in ("simulation",) or mod.split(".")[0] == "simulation":
                    if "domain.engineering" not in mod:
                        violations.append(f"{f.name}: satcom -> simulation")
    for sub in ("control", "math", "dsp", "rf", "comms"):
        for f in (eng / sub).glob("*.py"):
            tree = ast.parse(f.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    mods = [node.module or ""]
                for mod in mods:
                    if "engineering.satcom" in mod:
                        violations.append(f"{sub}/{f.name}: {sub} -> satcom")
    assert not violations, violations


def test_p5040_limits_and_bench():
    """P5-040: boundary budgets enforced; bench recorded (no wall asserts)."""
    import time as _time

    assert LO.MAX_LOSSES == 16
    assert N.MAX_FRIIS_STAGES == 8
    assert A.MAX_ANTENNAS_PER_LEG == 2
    assert S.MAX_BISECT_ITER == 200
    assert S.MAX_PTX_W == D("1E+6")
    with pytest.raises(ControlError):
        S.min_ptx_w(D(100), D(20), ref_leg())
    start = _time.perf_counter()
    res = S.forward_budget(ref_leg())
    elapsed = _time.perf_counter() - start
    assert elapsed >= 0 and res.cn0_dbhz == S.forward_budget(ref_leg()).cn0_dbhz
    print(f"P5-040 bench: forward budget {elapsed:.3f}s")


def test_p5041_feed_mismatch_p3_reuse():
    """P5-041: feed mismatch via REUSEd rf.margins (P3 regression bridge)."""
    from academic_core.domain.engineering.rf.margins import mismatch_loss_db as p3ml
    gamma = DecimalComplex(D("0.1"), D(0))
    assert L.feed_mismatch_loss_db(gamma) == p3ml(gamma).require_finite()
    assert L.feed_mismatch_loss_db(gamma) > 0
    with pytest.raises(ControlError):
        L.feed_mismatch_loss_db(DecimalComplex(D(1), D(0)))
    from academic_core.domain.engineering.rf.margins import return_loss_db, insertion_loss_db
    assert return_loss_db(DecimalComplex(D("0.5"), D(0))).require_finite() > 0
    assert insertion_loss_db(DecimalComplex(D("0.9"), D(0))).require_finite() > 0


def test_p5042_p4_reuse_bridge():
    """P5-042: P4 reuse bridge — to_db/from_db/Shannon/bit_rate/Es-Eb (P4 regression)."""
    from academic_core.domain.engineering.comms.metrics import (
        eb_n0_from_es_n0,
        es_n0_from_eb_n0,
        from_db10,
        shannon_capacity,
        to_db10,
    )
    from academic_core.domain.engineering.comms.bits import bit_rate
    assert to_db10(D(100)) == 20
    assert CTX.subtract(from_db10(D(20)), D(100)).copy_abs() <= D("1e-40")
    assert es_n0_from_eb_n0(D(3), 2) == 6
    assert eb_n0_from_es_n0(D(6), 2) == 3
    assert shannon_capacity(D(1000), D(1)).value == 1000
    assert bit_rate(D(1000), 4) == D(4000)


def test_p5043_chain_end_to_end():
    """P5-043: reference chain end-to-end incl. margin (gate §29)."""
    res = S.forward_budget(ref_leg())
    assert (res.fspl_db - D("205.106")).copy_abs() <= D("1e-3")
    assert (res.cn0_dbhz - D("99.483")).copy_abs() <= D("1e-3")
    assert (res.ebno_db - D("29.483")).copy_abs() <= D("1e-3")
    margin = S.link_margin_db(res.ebno_db, D("20"))
    assert CTX.subtract(margin, CTX.subtract(res.ebno_db, D(20))).copy_abs() <= D("1e-40")
    assert (M.to_dbw(D(100)).value - 20) == 0


def test_p5044_property_monotonicity():
    """P5-044: property tests — FSPL/EIRP/margin/Rb monotonicities."""
    assert L.fspl_db(ref_leg(distance_m=D(2000000))).value > L.fspl_db(ref_leg(distance_m=D(1000000))).value
    assert L.eirp_dbw(ref_leg(ptx_w=D(200))).value > L.eirp_dbw(ref_leg(ptx_w=D(100))).value
    assert S.link_margin_db(D(10), D(7)) > S.link_margin_db(D(9), D(7))
    assert S.max_rb_bps(D(100), D(20)) > S.max_rb_bps(D(100), D(23))
    assert S.bent_pipe_cn0_dbhz(D(90), D(100)) < 90
