"""F8-P4 Digital Communications -- certification test suite.

Test IDs P4-001..P4-040 map onto ``docs/gates/GATE-F8P4-DESIGN.md``
section 42. Oracles are closed-form/hand values, independent algebraic
derivations, or stdlib libm references in-test (never implementation ==
implementation). Tolerances are the ones justified in gate section 33
(exact combinatorics -> exact; round-trips <= 1e-40; BER mid-range
relative <= 1e-12; sinc truncation is the only truncation tolerance).
"""

from __future__ import annotations

import ast
import json
import math
from decimal import Decimal
from pathlib import Path

import pytest

from academic_core.domain.engineering.comms import bits as B
from academic_core.domain.engineering.comms import channel as CH
from academic_core.domain.engineering.comms import constellation as C
from academic_core.domain.engineering.comms import detection as DT
from academic_core.domain.engineering.comms import metrics as MT
from academic_core.domain.engineering.comms import modulation as MO
from academic_core.domain.engineering.comms import pulse as PU
from academic_core.domain.engineering.comms import report as RP
from academic_core.domain.engineering.comms import simulation as SI
from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.math import DecimalComplex, make_context

D = Decimal
CTX = make_context()
TOL_RT = D("1e-40")
TOL_BER = D("1e-12")


def rel_err(got: Decimal, ref: Decimal) -> Decimal:
    if ref == 0:
        return got.copy_abs()
    return (got - ref).copy_abs() / ref.copy_abs()


def test_p4001_bits_map_unmap_round_trip():
    """P4-001: bits/symbols/alphabet, MSB-first, exact round-trips (P4-I001/I002)."""
    assert B.validate_bits([0, 1, 1, 0]) == (0, 1, 1, 0)
    assert B.log2_int(2) == 1 and B.log2_int(256) == 8
    alpha = B.Alphabet.create(16)
    assert (alpha.order, alpha.bits_per_symbol) == (16, 4)
    bits = (0, 0, 1, 0, 1, 1, 1, 0)
    syms = B.map_bits(bits, 2)
    assert syms == (0, 2, 3, 2)
    assert B.unmap_symbols(syms, 2, 4) == bits
    assert B.bit_rate(D(1000), 2) == D(2000)
    with pytest.raises(ControlError):
        B.map_bits((0, 1, 0), 2)
    with pytest.raises(ControlError):
        B.log2_int(3)
    with pytest.raises(ControlError):
        B.validate_bits((0, 2))


def test_p4002_pad_explicit():
    """P4-002: explicit zero padding serializes pad_len; unpad recovers."""
    padded, need = B.pad_bits((0, 1, 1), 2)
    assert (padded, need) == ((0, 1, 1, 0), 1)
    assert B.unpad_bits(padded, need) == (0, 1, 1)
    clean, zero = B.pad_bits((0, 1, 1, 0), 2)
    assert (clean, zero) == ((0, 1, 1, 0), 0)
    with pytest.raises(ControlError):
        B.unpad_bits((0, 1, 1, 1), 1)


def test_p4003_alphabet_limits():
    """P4-003: M = 2^k <= 256 enforced; invalid orders rejected."""
    for order in (2, 4, 8, 16, 64, 256):
        assert B.Alphabet.create(order).bits_per_symbol == int(math.log2(order))
    for bad in (0, 1, 3, 5, 6, 12, 100, 257, 512):
        with pytest.raises(ControlError):
            B.Alphabet.create(bad)
    with pytest.raises(ControlError):
        B.validate_symbols((0, 4), 4)


def test_p4004_constellation_normalization_energy():
    """P4-004: unit average energy, recorded max energy (P4-I003/I004)."""
    for make in (C.bpsk_constellation, C.qpsk_constellation,
                 lambda: C.mqam_constellation(16), lambda: C.mpsk_constellation(8),
                 lambda: C.mask_constellation(4), C.ook_constellation):
        const = make()
        assert const.average_energy == 1
        total = D(0)
        for p in const.points:
            total = CTX.add(total, p.energy)
        mean = CTX.divide(total, D(const.order))
        assert (mean - 1).copy_abs() <= TOL_RT
        assert const.max_energy >= 1
    bpsk = C.bpsk_constellation()
    assert bpsk.points[0].coordinate.re == 1
    assert bpsk.points[1].coordinate.re == -1


def test_p4005_minimum_distance_hand_values():
    """P4-005: dmin pins — BPSK 2, QPSK sqrt(2) (P4-I005)."""
    assert C.minimum_distance(C.bpsk_constellation()) == 2
    dmin_q = C.minimum_distance(C.qpsk_constellation())
    assert CTX.subtract(CTX.multiply(dmin_q, dmin_q), D(2)).copy_abs() <= D("1e-40")
    dmin_8 = C.minimum_distance(C.mpsk_constellation(8))
    assert dmin_8 > 0 and dmin_8 < 1


def test_p4006_gray_exhaustive():
    """P4-006: Gray verified exhaustively on every scheme (P4-I006)."""
    consts = [C.bpsk_constellation(), C.qpsk_constellation(),
              C.mqam_constellation(4), C.mqam_constellation(16),
              C.mqam_constellation(64), C.mqam_constellation(256),
              C.mpsk_constellation(8), C.mpsk_constellation(16),
              C.mpsk_constellation(32), C.mpsk_constellation(64),
              C.mask_constellation(2), C.mask_constellation(4),
              C.mask_constellation(64), C.ook_constellation()]
    for const in consts:
        assert const.gray, const.scheme
        assert C.is_gray(const), const.scheme


def test_p4007_bpsk_frozen_map():
    """P4-007: BPSK 0->+1/1->-1, threshold demod, noiseless identity (P4-I007)."""
    const = C.bpsk_constellation()
    assert MO.modulate(const, (0, 1, 0))[0].re == 1
    assert MO.modulate(const, (0, 1, 0))[1].re == -1
    received = MO.modulate(const, (0, 1, 1, 0))
    assert MO.bpsk_demodulate(received) == (0, 1, 1, 0)
    assert MO.demodulate_ml(received, const) == (0, 1, 1, 0)


def test_p4008_qpsk_frozen_gray_eb_es():
    """P4-008: QPSK quadrants/labels/Gray/energy; Es = 2*Eb (P4-I008)."""
    const = C.qpsk_constellation()
    assert [p.label for p in const.points] == [(0, 0), (0, 1), (1, 1), (1, 0)]
    for p in const.points:
        assert (p.energy - 1).copy_abs() <= TOL_RT
    assert MO.qpsk_demodulate(MO.modulate(const, (0, 1, 2, 3))) == (0, 1, 2, 3)
    assert MT.eb_n0_from_es_n0(D(2), 2) == 1
    assert MT.es_n0_from_eb_n0(D(1), 2) == 2


def test_p4009_mod_demod_identity_all_schemes():
    """P4-009: noiseless mod/demod identity everywhere (P4-I007)."""
    cases = [C.bpsk_constellation(), C.qpsk_constellation(),
             C.mqam_constellation(16), C.mqam_constellation(64),
             C.mqam_constellation(256), C.mpsk_constellation(8),
             C.mpsk_constellation(64), C.mask_constellation(8),
             C.ook_constellation()]
    for const in cases:
        syms = tuple(range(const.order))
        assert DT.ml_decide(MO.modulate(const, syms), const) == syms
    assert MO.ask_demodulate(
        MO.modulate(C.mask_constellation(8), tuple(range(8))),
        C.mask_constellation(8)) == tuple(range(8))


def test_p4010_mpsk_ring_phi0():
    """P4-010: M-PSK ring, phi0 = 0 (first point 1+0j), unit circle."""
    for order in (8, 16, 32, 64):
        const = C.mpsk_constellation(order)
        first = const.points[0].coordinate
        assert first.re == 1 and first.im == 0
        for p in const.points:
            assert (p.energy - 1).copy_abs() <= D("1e-30")
    with pytest.raises(ControlError):
        C.mpsk_constellation(4)
    with pytest.raises(ControlError):
        C.mpsk_constellation(128)


def test_p4011_mqam_levels_spacing_qpsk_equivalence():
    """P4-011: square QAM levels/spacing/dmin; QPSK == 4-QAM."""
    qpsk = C.qpsk_constellation()
    qam4 = C.mqam_constellation(4)
    assert [p.label for p in qam4.points] == [p.label for p in qpsk.points]
    assert [p.coordinate for p in qam4.points] == [p.coordinate for p in qpsk.points]
    qam16 = C.mqam_constellation(16)
    levels = sorted({p.coordinate.re for p in qam16.points})
    assert len(levels) == 4
    gaps = [CTX.subtract(b, a) for a, b in zip(levels, levels[1:])]
    assert all((g - gaps[0]).copy_abs() <= D("1e-40") for g in gaps)
    dmin = C.minimum_distance(qam16)
    assert CTX.subtract(CTX.multiply(dmin, dmin), D("0.4")).copy_abs() <= D("1e-40")
    assert C.mqam_constellation(64).order == 64
    assert C.mqam_constellation(256).order == 256
    with pytest.raises(ControlError):
        C.mqam_constellation(8)
    with pytest.raises(ControlError):
        C.mqam_constellation(32)


def test_p4012_ask_ook_fsk_ideal():
    """P4-012: ASK/OOK/FSK coherent ideal paths + orthogonality + BFSK BER."""
    ask4 = C.mask_constellation(4)
    assert MO.ask_demodulate(MO.modulate(ask4, (0, 1, 2, 3)), ask4) == (0, 1, 2, 3)
    ook = C.ook_constellation()
    assert ook.points[0].coordinate.re == 0
    assert MO.ask_demodulate(MO.modulate(ook, (0, 1)), ook) == (0, 1)
    assert MO.ook_demodulate_noncoherent((D("0.1"), D("2")), D(1)) == (0, 1)
    scheme = MO.fsk_scheme(2, D(1000), D("0.001"))
    assert scheme.spacing_hz * D("0.001") == D("0.5")
    cross = MO.fsk_cross_integral(scheme.tone_freqs_hz[0],
                                  scheme.tone_freqs_hz[1], D("0.001"))
    assert cross.copy_abs() <= D("1e-40")
    assert MO.fsk_tone_of(1, scheme) == scheme.tone_freqs_hz[1]
    assert MT.ber_bfsk(D(1)).kind == MT.EXACT
    with pytest.raises(ControlError):
        MO.fsk_scheme(3, D(1000), D("0.001"))


def test_p4013_energy_sampling_rates():
    """P4-013: sps/oversample/budgets + P2 Nyquist reuse (P4-I009)."""
    from academic_core.domain.engineering.dsp.sampling import alias_of, nyquist_verdict
    assert MO.check_samples_per_symbol(8, 80) == 8
    with pytest.raises(ControlError):
        MO.check_samples_per_symbol(0, 8)
    with pytest.raises(ControlError):
        MO.check_samples_per_symbol(65, 65)
    const = C.bpsk_constellation()
    held = MO.oversample(MO.modulate(const, (0, 1)), 4)
    assert len(held) == 8 and held[0].re == 1 and held[4].re == -1
    assert nyquist_verdict(D(100), D(1000)) == "CLEAN"
    assert alias_of(D(1200), D(1000)) == D(200)
    assert B.bit_rate(D(1000), 1) == D(1000)


def test_p4014_passband_documentary():
    """P4-014: passband mapping frozen (fc explicit, phi0 = 0); rotation."""
    val = MO.passband_value(D(1), D(0), D(1000), D(0))
    assert val == 1
    with pytest.raises(ControlError):
        MO.passband_value(D(1), D(0), D(0), D(0))
    const = C.qpsk_constellation()
    syms = MO.modulate(const, (0,))
    back = MO.rotate_phase(MO.rotate_phase(syms, D("0.7")), D("-0.7"))
    assert (back[0] - syms[0]).modulus() <= D("1e-40")


def test_p4015_pulse_limits():
    """P4-015: RC/RRC closed limits incl. D-R1 pi/4 correction (P4-I012)."""
    assert PU.raised_cosine(D(0), D(1), D("0.25")) == 1
    assert PU.root_raised_cosine(D(0), D(1), D(0)) == 1
    assert PU.raised_cosine(D("1.5"), D(1), D(0)) == PU.sinc_pulse(D("1.5"), D(1))
    assert PU.root_raised_cosine(D("0.3"), D(1), D(0)) == PU.sinc_pulse(D("0.3"), D(1))
    from academic_core.domain.engineering.math import decimal_sqrt
    rc_s = PU.raised_cosine(D("1.25"), D(1), D("0.4"))
    expected = CTX.divide(decimal_sqrt(D(2), CTX), D(-10))
    assert CTX.subtract(rc_s, expected).copy_abs() <= D("1e-40")
    rrc_s = PU.root_raised_cosine(D(1), D(1), D("0.25"))
    assert (rrc_s + D("0.06423716")).copy_abs() <= D("1e-6")
    assert PU.rectangular(D("0.5"), D(1)) == 1
    assert PU.rectangular(D(1), D(1)) == 0
    with pytest.raises(ControlError):
        PU.raised_cosine(D(0), D(1), D(2))
    with pytest.raises(ControlError):
        PU.raised_cosine(D(0), D(0), D("0.5"))


def test_p4016_nyquist_isi_sinc():
    """P4-016: Nyquist zero crossings, sinc nodes, lobe budget (P4-I012)."""
    for n in (-3, -2, -1, 1, 2, 3):
        assert PU.raised_cosine(D(n), D(1), D("0.5")).copy_abs() <= D("1e-40")
        assert PU.sinc_pulse(D(n), D(1)).copy_abs() <= D("1e-40")
    assert PU.sinc_pulse(D(0), D(1)) == 1
    assert PU.check_lobes(5000) == 5000
    with pytest.raises(ControlError):
        PU.check_lobes(5001)
    assert PU.occupied_bandwidth(D(1000), D("0.5")) == D(750)


def test_p4017_awgn_psd_noiseless_identity():
    """P4-017: PSD one-sided/two-sided closed; zero noise -> identity (P4-I014)."""
    assert CH.noise_variance_real(D(2)) == 1
    assert CH.noise_variance_complex(D(2)) == 2
    assert CH.two_sided_psd(D(2)) == 1
    const = C.qpsk_constellation()
    tx = MO.modulate(const, (0, 1, 2, 3))
    zeros = tuple(DecimalComplex(D(0), D(0)) for _ in tx)
    assert CH.apply_awgn(tx, zeros) == tx
    with pytest.raises(ControlError):
        CH.validate_n0(D(0))
    with pytest.raises(ControlError):
        CH.validate_n0(D("-1"))


def test_p4018_static_impairments_limited():
    """P4-018: LIMITED static transforms are deterministic + invertible."""
    const = C.bpsk_constellation()
    tx = MO.modulate(const, (0, 1, 0, 1))
    assert CH.apply_gain(tx, D(2))[0].re == 2
    back = CH.apply_gain(CH.apply_gain(tx, D(2)), D("0.5"))
    assert all((b - a).modulus() <= D("1e-40") for a, b in zip(tx, back))
    rot = CH.apply_phase_rotation(tx, D("0.3"))
    unrot = CH.apply_phase_rotation(rot, D("-0.3"))
    assert all((b - a).modulus() <= D("1e-40") for a, b in zip(tx, unrot))
    shifted = CH.timing_shift(tx, D(0), D(1))
    assert all((b - a).modulus() <= D("1e-30") for a, b in zip(tx, shifted))
    off = CH.apply_frequency_offset(tx, D(0), D(1))
    assert all((b - a).modulus() <= D("1e-40") for a, b in zip(tx, off))
    with pytest.raises(ControlError):
        CH.apply_gain(tx, D(-1))
    with pytest.raises(ControlError):
        CH.timing_shift(tx, D(1), D(1))


def test_p4019_channel_invalid():
    """P4-019: misaligned noise, bad shifts, non-finite ingress rejected."""
    const = C.bpsk_constellation()
    tx = MO.modulate(const, (0, 1))
    with pytest.raises(ControlError):
        CH.apply_awgn(tx, (DecimalComplex(D(0), D(0)),))
    with pytest.raises(ControlError):
        CH.apply_awgn((), ())


def test_p4020_detection_matched_correlator_ml():
    """P4-020: threshold/correlator/matched == ML identity (P4-I013)."""
    assert DT.threshold_decide((D("-1"), D("0.5")), (D(0),)) == (0, 1)
    wave = (DecimalComplex(D(1), D(0)), DecimalComplex(D(0), D(1)))
    filt = DT.matched_filter(wave)
    assert filt == (DecimalComplex(D(0), D(-1)), DecimalComplex(D(1), D(0)))
    assert DT.inner_product(wave, wave) == DecimalComplex(D(2), D(0))
    const = C.bpsk_constellation()
    pts = tuple((p.coordinate,) for p in const.points)
    assert DT.correlator_decide((const.points[1].coordinate,), pts) == (1,)
    assert DT.ml_decide(MO.modulate(const, (1, 0)), const) == (1, 0)


def test_p4021_ml_map_separation():
    """P4-021: ML == MAP under uniform priors; MAP needs declared priors."""
    const = C.bpsk_constellation()
    rx = MO.modulate(const, (0, 1))
    uni = DT.MapPriors((D("0.5"), D("0.5")))
    assert DT.map_decide(rx, const, uni, D(1)) == DT.ml_decide(rx, const)
    skewed = DT.MapPriors((D("0.99"), D("0.01")))
    assert DT.map_decide(rx, const, skewed, D(1)) == (0, 0)
    with pytest.raises(ControlError):
        DT.MapPriors((D(0), D(1)))


def test_p4022_noncoherent_limited():
    """P4-022: LIMITED energy detection works; coherent stays normative."""
    assert DT.energy_detect((D("0.2"), D("3")), D(1)) == (0, 1)
    with pytest.raises(ControlError):
        DT.energy_detect((D(-1),), D(1))


def test_p4023_ber_exact_manual():
    """P4-023: EXACT BPSK/QPSK/BFSK/OOK vs manual 0 dB = 0.0786496 (P4-I010)."""
    manual = D("0.07864960352514255")
    for fun in (MT.ber_bpsk, MT.ber_qpsk):
        got = fun(D(1))
        assert got.kind == MT.EXACT
        assert rel_err(got.value, manual) <= TOL_BER
    assert MT.ber_bfsk(D(1)).kind == MT.EXACT
    assert MT.ber_ook(D(1)).kind == MT.EXACT
    assert MT.decimal_erfc(D(1)) == MT.decimal_erfc(D(1))
    assert (MT.decimal_erfc(D(1)) - D(str(math.erfc(1.0)))).copy_abs() <= D("1e-12")


def test_p4024_ber_curve_libm_oracle():
    """P4-024: BPSK curve Eb/N0 -2..10 dB vs independent libm oracle."""
    for db in (-2, 0, 2, 4, 6, 8, 10):
        lin = float(10) ** (db / 10.0)
        ref = D(str(0.5 * math.erfc(math.sqrt(lin))))
        got = MT.ber_bpsk(D(str(lin))).value
        assert rel_err(got, ref) <= TOL_BER, db


def test_p4025_q_erfc_battery():
    """P4-025: Q/erfc small/mid/large/extreme/negative/clamp."""
    assert MT.q_function(D(0)) == D("0.5")
    assert MT.decimal_erfc(D(0)) == 1
    assert (MT.q_function(D(-1)) + MT.q_function(D(1)) - 1).copy_abs() <= D("1e-40")
    mirror = CTX.subtract(D(2), MT.decimal_erfc(D(2)))
    assert CTX.subtract(MT.decimal_erfc(D(-2)), mirror).copy_abs() <= D("1e-40")
    assert MT.q_function(D(41)) == 0
    assert MT.decimal_erfc(D(41)) == 0
    for x in ("0.5", "1", "2", "3", "6"):
        ref = D(str(0.5 * math.erfc(float(x) / math.sqrt(2.0))))
        assert rel_err(MT.q_function(D(x)), ref) <= TOL_BER, x
    with pytest.raises(ControlError):
        MT.q_function(D("NaN"))
    with pytest.raises(ControlError):
        MT.decimal_erfc(float("inf"))


def test_p4026_ser_approx_labelled():
    """P4-026: SER APPROXIMATION kinds, (0,1) range, monotonic (P4-I011)."""
    assert MT.ser_qpsk_approx(D(2)).kind == MT.APPROXIMATION
    for order, fun in ((8, MT.ser_mpsk_approx), (16, MT.ser_mpsk_approx),
                       (16, MT.ser_mqam_approx), (64, MT.ser_mqam_approx),
                       (4, MT.ser_mask_approx)):
        got = fun(order, D(10))
        assert got.kind == MT.APPROXIMATION
        assert D(0) < got.value < 1
    low = MT.ser_mqam_approx(16, D(5)).value
    high = MT.ser_mqam_approx(16, D(20)).value
    assert high < low
    with pytest.raises(ControlError):
        MT.ser_mqam_approx(4, D(5))


def test_p4027_metric_consistency_db():
    """P4-027: Es/Eb/SNR triangle + dB round-trip (P4-I008/I009)."""
    assert MT.es_n0_from_eb_n0(D(3), 4) == D(12)
    assert MT.eb_n0_from_es_n0(D(12), 4) == 3
    assert MT.snr_from_es_n0(D(4), D(1000), D(1000)) == 4
    assert MT.snr_from_es_n0(D(4), D(1000), D(2000)) == 2
    assert MT.to_db10(D(10)) == 10
    assert MT.to_db20(D(10)) == 20
    assert CTX.subtract(MT.from_db10(D(10)), D(10)).copy_abs() <= D("1e-40")
    assert rel_err(MT.from_db10(D(3)), D(str(10.0 ** 0.3))) <= TOL_BER


def test_p4028_shannon():
    """P4-028: C = B*log2(1+SNR); zeros; C/B = 1 at 0 dB; ln2 limit."""
    assert MT.shannon_capacity(D(0), D(5)).value == 0
    assert MT.shannon_capacity(D(1000), D(0)).value == 0
    assert MT.spectral_efficiency(D(1)).value == 1
    assert MT.shannon_capacity(D(1000), D(1)).value == 1000
    lim = MT.shannon_limit_eb_n0()
    assert lim.kind == MT.EXACT
    assert (MT.to_db10(lim.value) + D("1.59")).copy_abs() <= D("0.01")
    with pytest.raises(ControlError):
        MT.shannon_capacity(D(-1), D(1))


def test_p4029_unsupported_absent():
    """P4-029: coding/sync/OFDM/MIMO/equalizer/fading/link-budget absent."""
    import academic_core.domain.engineering.comms as comms_pkg
    import academic_core.domain.engineering.comms.simulation as sim_mod
    names = " ".join(n.lower() for n in dir(comms_pkg))
    for banned in ("ldpc", "hamming", "reed", "solomon", "crc", "ofdm",
                   "mimo", "equaliz", "fading", "rayleigh", "pll",
                   "link_budget", "antenna", "quantiz", "sdrs", "viterbi"):
        assert banned not in names, banned
    assert "random" not in dir(sim_mod)


def test_p4030_hostile_battery():
    """P4-030: invalid/degenerate/hostile inputs -> typed states."""
    with pytest.raises(ControlError):
        B.validate_bits((0,) * (B.MAX_BITS + 1))
    with pytest.raises(ControlError):
        MO.check_samples_per_symbol(8, 70000)
    with pytest.raises(ControlError):
        SI.validate_seed(-1)
    with pytest.raises(ControlError):
        SI.validate_seed(True)
    with pytest.raises(ControlError):
        SI.uniform_stream(3, 0)
    with pytest.raises(ControlError):
        MT.ber_bpsk(D(-1))
    with pytest.raises(ControlError):
        MT.to_db10(D(0))
    with pytest.raises(ControlError):
        C.mqam_constellation(512)
    with pytest.raises(ControlError):
        B.Alphabet(order=4, bits_per_symbol=3)
    doc = RP.CommsDocument.create("k", {"v": D(1)})
    text = RP.dumps(doc)
    parsed = json.loads(text)
    parsed["digest"] = "0" * 64
    tampered = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
    assert RP.compare(text, tampered) == RP.INVALID_SERIALIZATION
    assert RP.compare(text, '{"schema": "f8p2-dsp/1"}') == RP.SCHEMA_MISMATCH
    assert RP.compare(text, "not json") == RP.INVALID_SERIALIZATION


def test_p4031_determinism_triple_run():
    """P4-031: analytic triple run -> identical digest (P4-I016/I018)."""
    const = C.mqam_constellation(16)
    syms = tuple(range(16))
    digests = set()
    for _ in range(3):
        doc = RP.CommsDocument.create("modem", {
            "symbols": list(syms),
            "ber": str(MT.ber_bpsk(D(2)).value),
            "coords": [{"re": str(p.coordinate.re), "im": str(p.coordinate.im)}
                       for p in const.points],
        })
        digests.add(RP.dumps(doc))
    assert len(digests) == 1


def test_p4032_seeded_determinism():
    """P4-032: same seed -> same streams and same MC report (P4-I015)."""
    assert SI.uniform_stream(11, 64) == SI.uniform_stream(11, 64)
    assert SI.uniform_stream(11, 64) != SI.uniform_stream(12, 64)
    assert SI.gaussian_stream(5, 32) == SI.gaussian_stream(5, 32)
    first = SI.uniform_stream(9, 16, 0)
    second = SI.uniform_stream(9, 8, 0) + SI.uniform_stream(9, 8, 8)
    assert first == second
    rep1 = SI.simulate_bpsk(D(6), 2000, 21)
    rep2 = SI.simulate_bpsk(D(6), 2000, 21)
    assert rep1 == rep2


def test_p4033_serialization_states():
    """P4-033: round-trip + 5 replay states + aliases (P4-I016)."""
    doc = RP.CommsDocument.create("ber", {"value": str(MT.ber_qpsk(D(1)).value)},
                                  {"case": "manual"})
    text = RP.dumps(doc)
    assert RP.loads(text).digest() == doc.digest()
    assert RP.compare(text, text) == RP.EQUIVALENT
    assert RP.VALID == RP.EQUIVALENT
    assert RP.RESULT_DIFFERENT == RP.RESULT_DIFFERS
    other = RP.dumps(RP.CommsDocument.create("ber", {"value": "0.5"}))
    assert RP.compare(text, other) == RP.RESULT_DIFFERS
    assert RP.compare(text, text.replace("f8p4-comms/1", "f8p4-comms/2")) == RP.VERSION_MISMATCH
    assert RP.compare(text, '{"schema": "f8o-metrology/1"}') == RP.SCHEMA_MISMATCH
    assert RP.compare(text, "garbage") == RP.INVALID_SERIALIZATION
    with pytest.raises(ControlError):
        RP.loads(text.replace('"digest"', '"bogus"'))
    with pytest.raises(ControlError):
        RP.dumps("not a document")


def test_p4034_replay_equivalence():
    """P4-034: replay intact/tampered/version (P4-I017)."""
    doc = RP.CommsDocument.create("sim", {"seed": 7})
    text = RP.dumps(doc)
    assert RP.replay(text) == RP.EQUIVALENT
    parsed = json.loads(text)
    parsed["digest"] = "0" * 64
    tampered = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
    assert RP.replay(tampered) == RP.RESULT_DIFFERS
    assert RP.replay(text.replace("f8p4-comms/1", "f8p4-comms/9")) == RP.INVALID_SERIALIZATION


def test_p4035_security_ast_grep():
    """P4-035: 0 banned calls/imports, 0 float literals in comms/."""
    import re as _re

    eng = Path(__file__).resolve().parents[1] / "src" / "academic_core" / "domain" / "engineering"
    files = list((eng / "comms").glob("*.py"))
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


def test_p4036_no_second_engine():
    """P4-036: no second Sequence/FFT/DFT/digest/serializer/replay/errors."""
    eng = Path(__file__).resolve().parents[1] / "src" / "academic_core" / "domain" / "engineering"
    hits = []
    for f in (eng / "comms").glob("*.py"):
        if f.name == "report.py":
            continue
        text = f.read_text(encoding="utf-8")
        for marker in ("class Sequence", "def fft(", "def dft(", "def canonical_json",
                       "def chain_digest", "class ControlStatus", "class ControlError",
                       "def parse_unit"):
            if marker in text:
                hits.append(f"{f.name}: {marker}")
    assert not hits, hits
    import academic_core.domain.engineering.comms.report as rp_mod
    import inspect as _inspect
    src = _inspect.getsource(rp_mod)
    assert "canonical_json" in src and "chain_digest" in src


def test_p4037_layer_direction():
    """P4-037: comms DAG — allowed downward deps only; never rf/lab/mna/ac."""
    eng = Path(__file__).resolve().parents[1] / "src" / "academic_core" / "domain" / "engineering"
    comms_files = list((eng / "comms").glob("*.py"))
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
                    if tail[:1] == ["rf"]:
                        violations.append(f"{f.name}: comms -> rf")
                    if tail[:1] == ["lab"]:
                        violations.append(f"{f.name}: comms -> lab")
                    if tail[:1] == ["mna"]:
                        violations.append(f"{f.name}: comms -> mna")
                    if tail[:1] == ["ac"]:
                        violations.append(f"{f.name}: comms -> ac")
                    if tail[:1] == ["comms"]:
                        continue
                if mod in ("simulation",) or mod.split(".")[0] == "simulation":
                    if "domain.engineering" not in mod:
                        violations.append(f"{f.name}: comms -> simulation")
    for sub in ("control", "math", "dsp"):
        for f in (eng / sub).glob("*.py"):
            tree = ast.parse(f.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    mods = [node.module or ""]
                for mod in mods:
                    if "engineering.comms" in mod:
                        violations.append(f"{sub}/{f.name}: {sub} -> comms")
    assert not violations, violations


def test_p4038_limits_and_bench():
    """P4-038: boundary budgets enforced; bench recorded (no wall asserts)."""
    import time as _time

    assert B.Alphabet.create(256).order == 256
    with pytest.raises(ControlError):
        B.Alphabet.create(512)
    with pytest.raises(ControlError):
        B.validate_bits((0,) * (B.MAX_BITS + 1))
    assert MO.check_samples_per_symbol(1, 10) == 1
    assert MO.check_samples_per_symbol(64, 640) == 64
    with pytest.raises(ControlError):
        MO.check_samples_per_symbol(65, 65)
    with pytest.raises(ControlError):
        SI.simulate_bpsk(D(4), SI.MAX_MC_BITS + 1, 1)
    const = C.mqam_constellation(256)
    start = _time.perf_counter()
    syms = tuple(range(256))
    assert DT.ml_decide(MO.modulate(const, syms), const) == syms
    elapsed = _time.perf_counter() - start
    assert elapsed >= 0
    print(f"P4-038 bench: 256-QAM 256-symbol ML decision {elapsed:.3f}s")


def test_p4039_monte_carlo_within_bound():
    """P4-039: seeded BPSK MC agrees with analytic within 5-sigma; SIM kind."""
    rep = SI.simulate_bpsk(D(4), 20000, 7)
    assert rep.errors == 236
    assert rep.within_bound
    assert SI.simulation_metric(rep).kind == MT.SIMULATION
    assert D(0) <= rep.ber_sim <= 1


def test_p4040_bits_baseband_end_to_end():
    """P4-040: bits -> baseband -> AWGN(0) -> ML -> bits (chain identity)."""
    const = C.mqam_constellation(16)
    bits = tuple([0, 1, 1, 0] * 8)
    tx = MO.bits_to_baseband(bits, const)
    zeros = tuple(DecimalComplex(D(0), D(0)) for _ in tx)
    rx = CH.apply_awgn(tx, zeros)
    detected = DT.ml_decide(rx, const)
    assert B.unmap_symbols(detected, 4, 16) == bits
