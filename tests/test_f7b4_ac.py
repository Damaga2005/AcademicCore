"""Tests for F7-B4 AC Analysis: domain model, complex signal, netlist building, parser, and real ngspice execution."""

import math
from decimal import Decimal
import pytest

from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.simulation import (
    ACAnalysis,
    ComplexSignal,
    Signal,
    SimulationJob,
    SimulationResult,
    parse_spice_number,
)
from academic_core.domain.engineering.units import parse_quantity
from academic_core.infrastructure.cas import FileBlobStore
from academic_core.infrastructure.database import Database
from academic_core.infrastructure.engineering import EngineeringRepository
from academic_core.infrastructure.ngspice import (
    NgSpiceBackend,
    SimulationExecution,
)
from academic_core.infrastructure.ngspice_parser import parse_ngspice_output
from academic_core.application.engineering import EngineeringService


# ==============================================================================
# 1. ACAnalysis domain model tests
# ==============================================================================

def test_ac_analysis_valid_dec():
    ac = ACAnalysis(sweep_type="dec", points=10, fstart="1", fstop="100k")
    assert ac.sweep_type == "DEC"
    assert ac.points == 10
    assert ac.fstart == Decimal("1")
    assert ac.fstop == Decimal("100000")
    assert ac.to_spice_card() == ".ac dec 10 1 100000"


def test_ac_analysis_valid_oct_and_lin():
    ac_oct = ACAnalysis(sweep_type="OCT", points=4, fstart=10, fstop=1000)
    assert ac_oct.to_spice_card() == ".ac oct 4 10 1000"

    ac_lin = ACAnalysis(sweep_type="lin", points=50, fstart="100", fstop="1MEG")
    assert ac_lin.sweep_type == "LIN"
    assert ac_lin.points == 50
    assert ac_lin.fstop == Decimal("1000000")
    assert ac_lin.to_spice_card() == ".ac lin 50 100 1000000"


def test_ac_analysis_validation_errors():
    # Invalid sweep type
    with pytest.raises(ValueError, match="invalid AC sweep type"):
        ACAnalysis(sweep_type="LOG", points=10, fstart=1, fstop=100)
    with pytest.raises(ValueError, match="AC sweep type must not be empty"):
        ACAnalysis(sweep_type="", points=10, fstart=1, fstop=100)

    # Non-positive points
    with pytest.raises(ValueError, match="AC points must be positive"):
        ACAnalysis(sweep_type="dec", points=0, fstart=1, fstop=100)
    with pytest.raises(ValueError, match="AC points must be positive"):
        ACAnalysis(sweep_type="dec", points=-5, fstart=1, fstop=100)

    # Non-positive start frequency
    with pytest.raises(ValueError, match="AC start frequency must be positive"):
        ACAnalysis(sweep_type="dec", points=10, fstart=0, fstop=100)
    with pytest.raises(ValueError, match="AC start frequency must be positive"):
        ACAnalysis(sweep_type="dec", points=10, fstart=-10, fstop=100)

    # Inverted or equal frequency range
    with pytest.raises(ValueError, match="must be greater than start frequency"):
        ACAnalysis(sweep_type="dec", points=10, fstart=100, fstop=10)
    with pytest.raises(ValueError, match="must be greater than start frequency"):
        ACAnalysis(sweep_type="dec", points=10, fstart=100, fstop=100)


def test_ac_analysis_from_string():
    ac1 = ACAnalysis.from_string(".ac dec 10 1 100k")
    assert ac1.sweep_type == "DEC"
    assert ac1.points == 10
    assert ac1.fstart == Decimal("1")
    assert ac1.fstop == Decimal("100000")

    ac2 = ACAnalysis.from_string("ac lin 100 10 1k")
    assert ac2.sweep_type == "LIN"
    assert ac2.points == 100
    assert ac2.fstop == Decimal("1000")

    with pytest.raises(ValueError, match="malformed AC directive"):
        ACAnalysis.from_string(".ac dec 10 1")


# ==============================================================================
# 2. ComplexSignal mathematics & accessors
# ==============================================================================

def test_complex_signal_math():
    # 3 + 4j  -> magnitude = 5, phase = atan2(4, 3) ~= 0.9273 rad ~= 53.13 deg
    # 0 - 1j  -> magnitude = 1, phase = -pi/2 rad = -90 deg, 0 dB
    # 0 + 0j  -> magnitude = 0, phase = 0, -Infinity dB
    re_s = (Decimal("3.0"), Decimal("0.0"), Decimal("0.0"))
    im_s = (Decimal("4.0"), Decimal("-1.0"), Decimal("0.0"))
    raw_c = (3.0 + 4.0j, 0.0 - 1.0j, 0.0 + 0.0j)

    csig = ComplexSignal(
        name="v(out)",
        unit="V",
        axis="voltage",
        real_samples=re_s,
        imag_samples=im_s,
        raw_complex_samples=raw_c,
    )

    assert csig.is_multi_point is True
    assert len(csig) == 3

    # Magnitude
    mags = csig.magnitude_samples
    assert math.isclose(float(mags[0]), 5.0, rel_tol=1e-6)
    assert math.isclose(float(mags[1]), 1.0, rel_tol=1e-6)
    assert float(mags[2]) == 0.0

    # Phase rad
    phases_rad = csig.phase_rad_samples
    assert math.isclose(float(phases_rad[0]), math.atan2(4.0, 3.0), rel_tol=1e-6)
    assert math.isclose(float(phases_rad[1]), -math.pi / 2, rel_tol=1e-6)

    # Phase deg
    phases_deg = csig.phase_deg_samples
    assert math.isclose(float(phases_deg[0]), math.degrees(math.atan2(4.0, 3.0)), rel_tol=1e-6)
    assert math.isclose(float(phases_deg[1]), -90.0, rel_tol=1e-6)

    # dB
    dbs = csig.db_samples
    assert math.isclose(float(dbs[0]), 20.0 * math.log10(5.0), rel_tol=1e-6)
    assert math.isclose(float(dbs[1]), 0.0, abs_tol=1e-6)
    assert dbs[2] == Decimal("-Infinity")

    # Scalar properties (first point)
    assert csig.value == 3.0 + 4.0j
    assert csig.real_value == Decimal("3.0")
    assert csig.imag_value == Decimal("4.0")
    assert math.isclose(float(csig.magnitude_value), 5.0, rel_tol=1e-6)
    assert math.isclose(float(csig.phase_deg_value), math.degrees(math.atan2(4.0, 3.0)), rel_tol=1e-6)


# ==============================================================================
# 3. SimulationJob deck generation tests
# ==============================================================================

def test_simulation_job_build_ac_card():
    netlist = "RC Circuit\nV1 in 0 ac 1\nR1 in out 1k\nC1 out 0 1u\n.end\n"
    ac = ACAnalysis(sweep_type="dec", points=10, fstart="10", fstop="100k")
    job = SimulationJob(netlist, analyses=(ac,))
    deck = job.build_netlist()

    assert ".ac dec 10 10 100000" in deck
    assert ".print ac" in deck
    assert "v(in)" in deck
    assert "v(out)" in deck
    assert "i(v1)" in deck
    assert deck.endswith(".end\n")


def test_simulation_job_preserves_existing_print_ac():
    netlist = "RC Circuit\nV1 in 0 ac 1\nR1 in out 1k\nC1 out 0 1u\n.print ac v(out)\n.end\n"
    ac = ACAnalysis(sweep_type="dec", points=5, fstart="10", fstop="1k")
    job = SimulationJob(netlist, analyses=(ac,))
    deck = job.build_netlist()

    assert deck.count(".print ac") == 1
    assert ".print ac v(out)" in deck


def test_simulation_job_string_ac_analysis():
    netlist = "RC Circuit\nV1 in 0 ac 1\nR1 in out 1k\nC1 out 0 1u\n.end\n"
    job = SimulationJob(netlist, analyses=("ac dec 5 10 10k",))
    deck = job.build_netlist()

    assert ".ac dec 5 10 10000" in deck
    assert ".print ac" in deck


# ==============================================================================
# 4. ngspice_parser AC table parsing & SimulationResult accessors
# ==============================================================================

MOCK_AC_OUTPUT = """
Circuit: RC AC Test

No. of Data Rows : 3
                                 RC AC Test
                                 AC Analysis  Sat Sep 12 23:00:00  2026
--------------------------------------------------------------------------------
Index   frequency       v(out)                          
--------------------------------------------------------------------------------
0\t1.000000e+01\t9.960677e-01,\t-6.25848e-02\t
1\t1.591549e+02\t7.071068e-01,\t-7.071068e-01\t
2\t1.000000e+04\t1.591150e-02,\t-1.591150e-01\t

                                 RC AC Test
                                 AC Analysis  Sat Sep 12 23:00:00  2026
--------------------------------------------------------------------------------
Index   frequency       v1#branch                       
--------------------------------------------------------------------------------
0\t1.000000e+01\t-3.93232e-06,\t-6.25848e-05\t
1\t1.591549e+02\t-2.92893e-04,\t-7.07107e-04\t
2\t1.000000e+04\t-9.84089e-04,\t-1.59115e-04\t
"""


def test_parse_ngspice_ac_tables():
    execution = SimulationExecution(
        status="COMPLETED",
        backend_id="ngspice",
        backend_version="ngspice-47",
        executable_path="ngspice_con.exe",
        started_at="2026-09-12T20:00:00Z",
        finished_at="2026-09-12T20:00:01Z",
        duration_seconds=0.1,
        exit_code=0,
        stdout=MOCK_AC_OUTPUT,
        stderr="",
        workspace="",
        command_metadata=(),
        timeout_seconds=30.0,
        cancelled=False,
        input_hash="hash_ac",
    )

    result = parse_ngspice_output(execution, analyses=("ac",))

    assert result.status == "COMPLETED"
    assert result.points_count == 3

    # Frequency axis
    f_ax = result.frequency_axis
    assert f_ax is not None
    assert f_ax.name == "frequency"
    assert f_ax.unit == "Hz"
    assert f_ax.axis == "frequency"
    assert len(f_ax.samples) == 3
    assert f_ax.samples[0] == Decimal("10.00000")
    assert f_ax.samples[1] == Decimal("159.1549")
    assert f_ax.samples[2] == Decimal("10000.00")

    # Complex signal v(out)
    v_out = result.get_complex_signal("v(out)")
    assert v_out is not None
    assert v_out.unit == "V"
    assert v_out.axis == "voltage"
    assert len(v_out.raw_complex_samples) == 3
    assert math.isclose(v_out.raw_complex_samples[0].real, 0.9960677, rel_tol=1e-5)
    assert math.isclose(v_out.raw_complex_samples[0].imag, -0.0625848, rel_tol=1e-5)

    # Cutoff point check (index 1: ~159.15 Hz)
    mag_fc = float(result.magnitude("v(out)")[1])
    phase_fc = float(result.phase_deg("v(out)")[1])
    db_fc = float(result.db("v(out)")[1])
    assert math.isclose(mag_fc, 1.0, rel_tol=1e-4)  # hypot(0.7071, -0.7071) = 1.0 in this mock fixture
    assert math.isclose(phase_fc, -45.0, abs_tol=0.1)

    # Complex current signal
    i_v1 = result.get_complex_signal("i(v1)")
    assert i_v1 is not None
    assert i_v1.unit == "A"
    assert i_v1.axis == "current"

    # Convenience sample_complex_at
    c_fc = result.sample_complex_at("v(out)", "159.1549")
    assert c_fc is not None
    assert math.isclose(c_fc.real, 0.7071068, rel_tol=1e-5)


def test_parse_ngspice_ac_cas_storage(tmp_path):
    store = FileBlobStore(tmp_path / "cas")
    execution = SimulationExecution(
        status="COMPLETED",
        backend_id="ngspice",
        backend_version="ngspice-47",
        executable_path="ngspice_con.exe",
        started_at="2026-09-12T20:00:00Z",
        finished_at="2026-09-12T20:00:01Z",
        duration_seconds=0.1,
        exit_code=0,
        stdout=MOCK_AC_OUTPUT,
        stderr="",
        workspace="",
        command_metadata=(),
        timeout_seconds=30.0,
        cancelled=False,
        input_hash="hash_ac",
    )

    result = parse_ngspice_output(execution, cas_store=store, analyses=("ac",))
    assert result.raw_artifact_hash
    stored = store.get_bytes(result.raw_artifact_hash)
    assert b"Index   frequency       v(out)" in stored


# ==============================================================================
# 5. Real ngspice runtime integration tests
# ==============================================================================

def _get_real_backend() -> NgSpiceBackend | None:
    backend = NgSpiceBackend()
    if backend.detect().verified:
        return backend
    return None


@pytest.mark.skipif(_get_real_backend() is None, reason="Real ngspice runtime not available/verified")
def test_real_ngspice_ac_case_a_rc_low_pass():
    """Scientific verification Case A: RC Low-pass filter.

    Circuit:
      V1 in 0 dc 0 ac 1
      R1 in out 1k (1000 Ohm)
      C1 out 0 1u  (1 uF)
      .ac dec 10 1 100k

    Analytical equations:
      H(jw) = 1 / (1 + j*w*R*C)
      fc = 1 / (2 * pi * R * C) = 1 / (2 * pi * 1000 * 1e-6) ~= 159.1549 Hz

    Expected values:
      At low freq (10 Hz):
        w = 2*pi*10 ~= 62.83 rad/s
        |H| = 1 / sqrt(1 + (wRC)^2) ~= 1 / sqrt(1 + 0.003948) ~= 0.99803
        dB ~= -0.0171 dB
        phase = -atan(wRC) ~= -3.595 deg
      At cutoff fc (~159.1549 Hz):
        |H| = 1 / sqrt(2) ~= 0.707107
        dB = -3.0103 dB
        phase = -45.0 deg
      At high freq (10 kHz):
        wRC ~= 2*pi*10000 * 1e-3 = 62.8318
        |H| ~= 1 / 62.83 ~= 0.01591
        dB ~= -35.96 dB
        phase ~= -89.09 deg
    """
    backend = _get_real_backend()
    assert backend is not None

    netlist = """* RC Low-pass Filter
V1 in 0 dc 0 ac 1
R1 in out 1k
C1 out 0 1u
.end
"""
    ac = ACAnalysis(sweep_type="dec", points=10, fstart="1", fstop="100k")
    result = backend.simulate(netlist, analyses=(ac,))

    assert result.status == "COMPLETED"
    assert result.mocked is False
    assert result.points_count > 50

    # Low frequency (10 Hz)
    c_10hz = result.sample_complex_at("v(out)", "10")
    mag_10hz = abs(c_10hz)
    phase_10hz = math.degrees(math.atan2(c_10hz.imag, c_10hz.real))
    db_10hz = 20.0 * math.log10(mag_10hz)

    assert abs(mag_10hz - 0.99803) < 0.002
    assert abs(db_10hz - (-0.0171)) < 0.02
    assert abs(phase_10hz - (-3.595)) < 0.2

    # Cutoff frequency (~159.155 Hz)
    c_fc = result.sample_complex_at("v(out)", "158.489")  # nearest sample in 10 pts/dec
    mag_fc = abs(c_fc)
    phase_fc = math.degrees(math.atan2(c_fc.imag, c_fc.real))
    db_fc = 20.0 * math.log10(mag_fc)

    assert abs(mag_fc - 0.7071) < 0.02
    assert abs(db_fc - (-3.0103)) < 0.2
    assert abs(phase_fc - (-45.0)) < 1.0

    # High frequency (10 kHz)
    c_10k = result.sample_complex_at("v(out)", "10000")
    mag_10k = abs(c_10k)
    phase_10k = math.degrees(math.atan2(c_10k.imag, c_10k.real))
    db_10k = 20.0 * math.log10(mag_10k)

    assert abs(mag_10k - 0.01591) < 0.001
    assert abs(db_10k - (-35.96)) < 0.2
    assert abs(phase_10k - (-89.09)) < 0.5


@pytest.mark.skipif(_get_real_backend() is None, reason="Real ngspice runtime not available/verified")
def test_real_ngspice_ac_case_b_rc_high_pass():
    """Scientific verification Case B: RC High-pass filter.

    Circuit:
      V1 in 0 dc 0 ac 1
      C1 in out 1u
      R1 out 0 1k
      .ac dec 10 1 100k

    Analytical equations:
      H(jw) = j*w*R*C / (1 + j*w*R*C)
      fc ~= 159.1549 Hz

    Expected values:
      At low freq (10 Hz): |H| ~= 0.06275, phase ~= +86.4 deg
      At cutoff fc (~159.155 Hz): |H| ~= 0.7071, dB ~= -3.01 dB, phase ~= +45.0 deg
      At high freq (10 kHz): |H| ~= 0.99987, phase ~= +0.91 deg
    """
    backend = _get_real_backend()
    assert backend is not None

    netlist = """* RC High-pass Filter
V1 in 0 dc 0 ac 1
C1 in out 1u
R1 out 0 1k
.end
"""
    ac = ACAnalysis(sweep_type="dec", points=10, fstart="1", fstop="100k")
    result = backend.simulate(netlist, analyses=(ac,))

    assert result.status == "COMPLETED"

    # Cutoff frequency (~159 Hz)
    c_fc = result.sample_complex_at("v(out)", "158.489")
    mag_fc = abs(c_fc)
    phase_fc = math.degrees(math.atan2(c_fc.imag, c_fc.real))

    assert abs(mag_fc - 0.7071) < 0.02
    assert abs(phase_fc - 45.0) < 1.0

    # Low frequency (10 Hz)
    c_10hz = result.sample_complex_at("v(out)", "10")
    mag_10hz = abs(c_10hz)
    phase_10hz = math.degrees(math.atan2(c_10hz.imag, c_10hz.real))
    assert abs(mag_10hz - 0.0628) < 0.005
    assert abs(phase_10hz - 86.4) < 0.5

    # High frequency (10 kHz)
    c_10k = result.sample_complex_at("v(out)", "10000")
    mag_10k = abs(c_10k)
    phase_10k = math.degrees(math.atan2(c_10k.imag, c_10k.real))
    assert abs(mag_10k - 1.0) < 0.005
    assert abs(phase_10k - 0.91) < 0.5


@pytest.mark.skipif(_get_real_backend() is None, reason="Real ngspice runtime not available/verified")
def test_real_ngspice_ac_case_c_rl_circuit():
    """Scientific verification Case C: RL impedance and response.

    Circuit:
      V1 in 0 dc 0 ac 1
      R1 in mid 1k (1000 Ohm)
      L1 mid 0 1m  (0.001 H)

    Analytical equations:
      Z(jw) = R + j*w*L
      I(jw) = -V1 / (R + j*w*L)  [source branch current]
      V(mid) = V1 * (j*w*L) / (R + j*w*L)

    At f = 100 kHz:
      w = 2 * pi * 100000 ~= 628318.5 rad/s
      w*L ~= 628.3185 Ohm
      |Z| = sqrt(1000^2 + 628.3185^2) ~= 1181.04 Ohm
      |I| = 1 / 1181.04 ~= 0.0008467 A ~= 0.8467 mA
      |V(mid)| = 628.3185 / 1181.04 ~= 0.5320 V
      phase(V(mid)) = 90 - atan(628.3185 / 1000) = 90 - 32.14 ~= 57.86 deg
    """
    backend = _get_real_backend()
    assert backend is not None

    netlist = """* RL Filter
V1 in 0 dc 0 ac 1
R1 in mid 1k
L1 mid 0 1m
.end
"""
    ac = ACAnalysis(sweep_type="dec", points=5, fstart="1k", fstop="1MEG")
    result = backend.simulate(netlist, analyses=(ac,))

    assert result.status == "COMPLETED"

    # Sample at 100 kHz
    c_vmid = result.sample_complex_at("v(mid)", "100k")
    c_iv1 = result.sample_complex_at("i(v1)", "100k")

    mag_vmid = abs(c_vmid)
    phase_vmid = math.degrees(math.atan2(c_vmid.imag, c_vmid.real))
    mag_iv1 = abs(c_iv1)

    assert abs(mag_vmid - 0.5320) < 0.01
    assert abs(phase_vmid - 57.86) < 0.5
    assert abs(mag_iv1 - 0.0008467) < 0.00002


@pytest.mark.skipif(_get_real_backend() is None, reason="Real ngspice runtime not available/verified")
def test_real_ngspice_ac_case_d_rlc_resonance():
    """Scientific verification Case D: RLC Series Resonance.

    Circuit:
      V1 in 0 dc 0 ac 1
      R1 in n1 10
      L1 n1 n2 1m
      C1 n2 0 1u

    Resonance frequency:
      f0 = 1 / (2 * pi * sqrt(L * C))
      L = 1e-3 H, C = 1e-6 F
      f0 = 1 / (2 * pi * sqrt(1e-9)) = 1 / (2 * pi * 3.162277e-5) ~= 5032.92 Hz

    At resonance (f ~= 5033 Hz):
      Z_L + Z_C = j*w*L + 1/(j*w*C) ~= 0
      Z_total ~= R1 = 10 Ohm
      |I(V1)| is maximum ~= 1 V / 10 Ohm = 0.1 A
      Current phase with source branch convention is 180 deg (or 0 deg for loop current).
    """
    backend = _get_real_backend()
    assert backend is not None

    netlist = """* Series RLC Resonance
V1 in 0 dc 0 ac 1
R1 in n1 10
L1 n1 n2 1m
C1 n2 0 1u
.end
"""
    # Linear sweep around resonance: 4000 Hz to 6000 Hz
    ac = ACAnalysis(sweep_type="lin", points=101, fstart="4000", fstop="6000")
    result = backend.simulate(netlist, analyses=(ac,))

    assert result.status == "COMPLETED"
    assert result.points_count == 101

    # Find peak current across the frequency sweep
    curr_samples = result.current_complex_samples("v1")
    assert curr_samples is not None
    mags = [abs(c) for c in curr_samples]
    max_mag = max(mags)
    peak_idx = mags.index(max_mag)

    peak_freq = float(result.frequency_axis.samples[peak_idx])

    # Maximum current must be ~0.1 A (1V / 10 Ohm)
    assert abs(max_mag - 0.1) < 0.005, f"Peak current = {max_mag}, expected ~0.1 A"

    # Peak frequency must be within 20 Hz of theoretical 5032.92 Hz
    assert abs(peak_freq - 5032.92) < 25.0, f"Peak freq = {peak_freq}, expected ~5032.92 Hz"


@pytest.mark.skipif(_get_real_backend() is None, reason="Real ngspice runtime not available/verified")
def test_real_ngspice_ac_sweep_types_dec_oct_lin():
    """Verify DEC, OCT, and LIN sweeps against ngspice 47."""
    backend = _get_real_backend()
    assert backend is not None

    netlist = """* Sweep Types Test
V1 in 0 dc 0 ac 1
R1 in 0 1k
.end
"""
    # DEC
    r_dec = backend.simulate(netlist, analyses=(ACAnalysis(sweep_type="DEC", points=2, fstart="100", fstop="10k"),))
    assert r_dec.status == "COMPLETED"
    assert r_dec.points_count == 5  # 100, 316.2, 1k, 3.16k, 10k

    # OCT
    r_oct = backend.simulate(netlist, analyses=(ACAnalysis(sweep_type="OCT", points=2, fstart="100", fstop="800"),))
    assert r_oct.status == "COMPLETED"
    assert r_oct.points_count == 7  # 3 octaves * 2 pts + 1 = 7

    # LIN
    r_lin = backend.simulate(netlist, analyses=(ACAnalysis(sweep_type="LIN", points=21, fstart="100", fstop="500"),))
    assert r_lin.status == "COMPLETED"
    assert r_lin.points_count == 21


@pytest.mark.skipif(_get_real_backend() is None, reason="Real ngspice runtime not available/verified")
def test_engineering_service_ac_end_to_end(tmp_path):
    """End-to-end integration via EngineeringService and Circuit domain model."""
    repo = EngineeringRepository(Database(tmp_path / "eng.db"))
    service = EngineeringService(repo)
    backend = _get_real_backend()
    assert backend is not None

    service.create_project("AC_PROJ")

    circuit = Circuit("RC_LOW_PASS")
    circuit.add(Component("V1", "V", parse_quantity("1 V"), {"+": "in", "-": "0"}))
    circuit.add(Component("R1", "R", parse_quantity("1 kOhm"), {"1": "in", "2": "out"}))
    circuit.add(Component("C1", "C", parse_quantity("1 uF"), {"1": "out", "2": "0"}))

    service.save_circuit("AC_PROJ", circuit)

    ac = ACAnalysis(sweep_type="dec", points=10, fstart="1", fstop="100k")
    result = service.simulate_circuit("AC_PROJ", "RC_LOW_PASS", analyses=(ac,), backend=backend)

    assert result.status == "COMPLETED"
    assert result.points_count > 50
    assert result.frequency_axis is not None

    c_fc = result.sample_complex_at("v(out)", "158.489")
    assert abs(abs(c_fc) - 0.7071) < 0.02
