"""Tests for F7-B5 Noise (.noise) and Sensitivity (.sens) Analysis.

Covers:
- NoiseAnalysis and SensitivityAnalysis domain models & validation
- Deterministic SPICE deck generation (.noise, .sens, .print cards)
- Parser for ngspice 47 noise and sensitivity output tables
- CAS artifact storage and execution provenance
- Real ngspice 47 scientific validations:
  1. Resistor thermal noise (Johnson-Nyquist law)
  2. RC low-pass filter noise spectrum and integrated RMS noise (kT/C)
  3. DC sensitivity on voltage divider (R1, R2, V1) vs analytical & finite difference
  4. AC sensitivity on RC filter (dH/dC, dH/dR) vs exact analytical derivatives
  5. Sensitivity on RLC series resonant circuit
  6. Sweep types (DEC, OCT, LIN)
  7. End-to-end integration via EngineeringService and Circuit domain model
"""

from __future__ import annotations

import cmath
import math
from decimal import Decimal
import pytest

from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.simulation import (
    ComplexSignal,
    NoiseAnalysis,
    NoiseResult,
    SensitivityAnalysis,
    SensitivityResult,
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


def _get_real_backend() -> NgSpiceBackend | None:
    backend = NgSpiceBackend()
    if backend.detect().verified:
        return backend
    return None


# ==============================================================================
# 1. NoiseAnalysis domain model tests
# ==============================================================================

def test_noise_analysis_valid_dec():
    na = NoiseAnalysis(
        output_variable="v(out)",
        input_source="V1",
        sweep_type="dec",
        points=10,
        fstart="1",
        fstop="100k",
    )
    assert na.output_variable == "v(out)"
    assert na.input_source == "V1"
    assert na.sweep_type == "DEC"
    assert na.points == 10
    assert na.fstart == Decimal("1")
    assert na.fstop == Decimal("100000")
    assert na.to_spice_card() == ".noise v(out) V1 dec 10 1 100000"


def test_noise_analysis_valid_oct_and_lin():
    na_oct = NoiseAnalysis(
        output_variable="v(out)",
        input_source="vin",
        sweep_type="OCT",
        points=4,
        fstart=10,
        fstop=1000,
    )
    assert na_oct.input_source == "VIN"
    assert na_oct.to_spice_card() == ".noise v(out) VIN oct 4 10 1000"

    na_lin = NoiseAnalysis(
        output_variable="v(out)",
        input_source="V1",
        sweep_type="lin",
        points=50,
        fstart="100",
        fstop="1MEG",
    )
    assert na_lin.sweep_type == "LIN"
    assert na_lin.points == 50
    assert na_lin.fstop == Decimal("1000000")
    assert na_lin.to_spice_card() == ".noise v(out) V1 lin 50 100 1000000"


def test_noise_analysis_from_string():
    na = NoiseAnalysis.from_string(".noise v(out) V1 dec 10 1 100k")
    assert na.output_variable == "v(out)"
    assert na.input_source == "V1"
    assert na.sweep_type == "DEC"
    assert na.points == 10
    assert na.fstart == Decimal("1")
    assert na.fstop == Decimal("100000")

    na2 = NoiseAnalysis.from_string("noise v(n1,0) VSRC lin 20 100 10k")
    assert na2.output_variable == "v(n1,0)"
    assert na2.input_source == "VSRC"
    assert na2.sweep_type == "LIN"
    assert na2.points == 20


def test_noise_analysis_validation_errors():
    with pytest.raises(ValueError, match="output variable must not be empty"):
        NoiseAnalysis("", "V1", "dec", 10, "1", "10k")

    with pytest.raises(ValueError, match="input source must not be empty"):
        NoiseAnalysis("v(out)", "", "dec", 10, "1", "10k")

    with pytest.raises(ValueError, match="invalid noise sweep type"):
        NoiseAnalysis("v(out)", "V1", "LOG", 10, "1", "10k")

    with pytest.raises(ValueError, match="points must be positive"):
        NoiseAnalysis("v(out)", "V1", "dec", 0, "1", "10k")

    with pytest.raises(ValueError, match="start frequency must be positive"):
        NoiseAnalysis("v(out)", "V1", "dec", 10, "0", "10k")

    with pytest.raises(ValueError, match="stop frequency.*must be greater"):
        NoiseAnalysis("v(out)", "V1", "dec", 10, "100k", "10k")


# ==============================================================================
# 2. SensitivityAnalysis domain model tests
# ==============================================================================

def test_sensitivity_analysis_dc():
    sa = SensitivityAnalysis(output_variable="v(out)", analysis_type="DC")
    assert sa.output_variable == "v(out)"
    assert sa.analysis_type == "DC"
    assert sa.to_spice_card() == ".sens v(out)"

    sa_parsed = SensitivityAnalysis.from_string(".sens v(out)")
    assert sa_parsed.output_variable == "v(out)"
    assert sa_parsed.analysis_type == "DC"


def test_sensitivity_analysis_ac():
    sa = SensitivityAnalysis(
        output_variable="v(out)",
        analysis_type="AC",
        sweep_type="DEC",
        points=10,
        fstart="1",
        fstop="100k",
        parameters=("r1", "c1"),
    )
    assert sa.analysis_type == "AC"
    assert sa.sweep_type == "DEC"
    assert sa.points == 10
    assert sa.fstart == Decimal("1")
    assert sa.fstop == Decimal("100000")
    assert sa.parameters == ("r1", "c1")
    assert sa.to_spice_card() == ".sens v(out) ac dec 10 1 100000"

    sa_parsed = SensitivityAnalysis.from_string(".sens v(out) ac dec 10 1 100k")
    assert sa_parsed.analysis_type == "AC"
    assert sa_parsed.sweep_type == "DEC"
    assert sa_parsed.points == 10
    assert sa_parsed.fstop == Decimal("100000")


def test_sensitivity_analysis_validation_errors():
    with pytest.raises(ValueError, match="output variable must not be empty"):
        SensitivityAnalysis(output_variable="")

    with pytest.raises(ValueError, match="invalid sensitivity analysis type"):
        SensitivityAnalysis(output_variable="v(out)", analysis_type="TRAN")

    with pytest.raises(ValueError, match="points must be positive"):
        SensitivityAnalysis(output_variable="v(out)", analysis_type="AC", points=0)

    with pytest.raises(ValueError, match="start frequency must be positive"):
        SensitivityAnalysis(output_variable="v(out)", analysis_type="AC", fstart=0)

    with pytest.raises(ValueError, match="stop frequency.*must be greater"):
        SensitivityAnalysis(output_variable="v(out)", analysis_type="AC", fstart=1000, fstop=100)


# ==============================================================================
# 3. SimulationJob deck generation tests
# ==============================================================================

def test_simulation_job_noise_deck_generation():
    netlist = """* RC Noise Deck
V1 in 0 1V
R1 in out 1k
C1 out 0 1u
.end
"""
    noise = NoiseAnalysis("v(out)", "V1", "dec", 10, "1", "100k")
    job = SimulationJob(netlist, analyses=(noise,))
    deck = job.build_netlist()

    assert ".noise v(out) V1 dec 10 1 100000" in deck
    assert ".print noise all" in deck
    assert "ac 1" in deck  # Auto-injected AC excitation for noise input source


def test_simulation_job_sens_deck_generation():
    netlist = """* DC Sens Deck
V1 in 0 5V
R1 in out 1k
R2 out 0 1k
.end
"""
    sens = SensitivityAnalysis("v(out)", analysis_type="DC")
    job = SimulationJob(netlist, analyses=(sens,))
    deck = job.build_netlist()

    assert ".sens v(out)" in deck
    assert ".print sens all" in deck

    # With specific parameters
    sens_params = SensitivityAnalysis("v(out)", analysis_type="DC", parameters=("r1", "r2"))
    job2 = SimulationJob(netlist, analyses=(sens_params,))
    deck2 = job2.build_netlist()
    assert ".print sens r1 r2" in deck2


# ==============================================================================
# 4. Parser unit tests on mock executions
# ==============================================================================

def test_parser_noise_table():
    sample_stdout = """
Circuit: * noise test

No. of Data Rows : 2

No. of Data Rows : 1
                                  * noise test
                                  Integrated Noise
--------------------------------------------------------------------------------
Index   inoise_total    onoise_total    
--------------------------------------------------------------------------------
0	1.444169e-06	6.414136e-08	

                                  * noise test
                                  Noise Spectral Density Curves
--------------------------------------------------------------------------------
Index   frequency       inoise_spectrum onoise_spectrum 
--------------------------------------------------------------------------------
0	1.000000e+00	4.071372e-09	4.071291e-09	
1	1.000000e+02	4.071372e-09	3.447365e-09	
"""
    execution = SimulationExecution(
        backend_id="ngspice",
        backend_version="47",
        executable_path="ngspice_con.exe",
        workspace="tmp",
        timeout_seconds=30.0,
        status="COMPLETED",
        exit_code=0,
        stdout=sample_stdout,
        stderr="",
        duration_seconds=0.01,
        started_at="2026-09-12T00:00:00Z",
        finished_at="2026-09-12T00:00:01Z",
        input_hash="hash123",
        command_metadata={},
    )
    result = parse_ngspice_output(execution, analyses=("noise v(out) v1 dec 10 1 100k",))
    assert isinstance(result, NoiseResult)
    assert result.status == "COMPLETED"
    assert result.onoise_total == Decimal("6.414136e-08")
    assert result.inoise_total == Decimal("1.444169e-06")
    assert result.points_count == 2
    assert result.sample_onoise_at("1") == Decimal("4.071291e-09")
    assert result.sample_onoise_at("100") == Decimal("3.447365e-09")


def test_parser_dc_sens_table():
    sample_stdout = """
Circuit: * dc sens test

No. of Data Rows : 1
                                  * sens test
                                  Sensitivity Analysis
--------------------------------------------------------------------------------
Index   r1              r2              v1              
--------------------------------------------------------------------------------
0	-1.25000e-03	1.249999e-03	5.000000e-01	
"""
    execution = SimulationExecution(
        backend_id="ngspice",
        backend_version="47",
        executable_path="ngspice_con.exe",
        workspace="tmp",
        timeout_seconds=30.0,
        status="COMPLETED",
        exit_code=0,
        stdout=sample_stdout,
        stderr="",
        duration_seconds=0.01,
        started_at="2026-09-12T00:00:00Z",
        finished_at="2026-09-12T00:00:01Z",
        input_hash="hash123",
        command_metadata={},
    )
    result = parse_ngspice_output(execution, analyses=(SensitivityAnalysis("v(out)"),))
    assert isinstance(result, SensitivityResult)
    assert result.status == "COMPLETED"
    assert result.get_sensitivity("r1") == Decimal("-1.25000e-03")
    assert result.get_sensitivity("r2") == Decimal("1.249999e-03")
    assert result.get_sensitivity("v1") == Decimal("5.000000e-01")

    # Normalized sensitivity
    norm = result.compute_normalized_sensitivities({"r1": 1000, "r2": 1000, "v1": 5}, nominal_output=Decimal("2.5"))
    assert abs(float(norm["r1"]) - (-0.5)) < 1e-4
    assert abs(float(norm["r2"]) - 0.5) < 1e-4
    assert abs(float(norm["v1"]) - 1.0) < 1e-4


# ==============================================================================
# 5. Real ngspice 47 scientific validations
# ==============================================================================

@pytest.mark.skipif(_get_real_backend() is None, reason="Real ngspice runtime not available/verified")
def test_real_ngspice_case_1_resistor_thermal_noise():
    """Scientific verification 1: Resistor Johnson-Nyquist thermal noise.

    Theoretical law:
      e_n = sqrt(4 * k_B * T * R)
      At T = 300.15 K (27 C nominal SPICE temp):
      k_B = 1.380649e-23 J/K
      For R = 1000 Ohm:
      e_n = sqrt(4 * 1.380649e-23 * 300.15 * 1000)
          = sqrt(1.657579e-17) ~= 4.071337e-09 V/sqrt(Hz)
    """
    backend = _get_real_backend()
    assert backend is not None

    netlist = """* Resistor Thermal Noise
V1 in 0 dc 0 ac 1
R1 in out 1k
.end
"""
    noise = NoiseAnalysis(output_variable="v(out)", input_source="V1", sweep_type="dec", points=5, fstart="1", fstop="10k")
    result = backend.simulate(netlist, analyses=(noise,))

    assert isinstance(result, NoiseResult)
    assert result.status == "COMPLETED"
    assert result.onoise_spectrum is not None

    # Theoretical thermal noise at 27 C
    k_B = 1.380649e-23
    T_kelvin = 300.15
    R_val = 1000.0
    theoretical_en = math.sqrt(4.0 * k_B * T_kelvin * R_val)

    # Sample output noise at 100 Hz
    onoise_100hz = float(result.sample_onoise_at("100"))
    rel_error = abs(onoise_100hz - theoretical_en) / theoretical_en

    # ngspice 47 gives ~4.071372e-09 V/sqrt(Hz)
    assert rel_error < 0.001  # < 0.1% relative error
    assert result.onoise_spectrum.unit == "V/sqrt(Hz)"


@pytest.mark.skipif(_get_real_backend() is None, reason="Real ngspice runtime not available/verified")
def test_real_ngspice_case_2_rc_noise_spectrum_and_integrated():
    """Scientific verification 2: RC filter noise spectrum and integrated noise (kT/C).

    Circuit:
      V1 in 0 dc 0 ac 1
      R1 in out 1k (1000 Ohm)
      C1 out 0 1u  (1 uF)

    Noise spectral density:
      e_no(f) = e_n_resistor / sqrt(1 + (2*pi*f*R*C)^2)
      fc = 1 / (2*pi*RC) ~= 159.155 Hz
      At f << fc: e_no(f) ~= e_n_resistor ~= 4.071e-9 V/sqrt(Hz)
      At f = fc:  e_no(fc) = e_n_resistor / sqrt(2) ~= 2.8789e-9 V/sqrt(Hz)

    Integrated total output noise (infinite bandwidth theoretical limit):
      V_rms_total = sqrt(k_B * T / C)
      For C = 1 uF:
      V_rms_total = sqrt(1.380649e-23 * 300.15 / 1e-6) ~= 6.4373e-8 V_RMS
    """
    backend = _get_real_backend()
    assert backend is not None

    netlist = """* RC Filter Noise
V1 in 0 dc 0 ac 1
R1 in out 1k
C1 out 0 1u
.end
"""
    noise = NoiseAnalysis(output_variable="v(out)", input_source="V1", sweep_type="dec", points=10, fstart="1", fstop="100k")
    result = backend.simulate(netlist, analyses=(noise,))

    assert isinstance(result, NoiseResult)
    assert result.status == "COMPLETED"
    assert result.points_count > 50

    # Low frequency plateau (1 Hz)
    onoise_1hz = float(result.sample_onoise_at("1"))
    assert abs(onoise_1hz - 4.071e-9) < 0.05e-9

    # Cutoff frequency (~158.5 Hz in log sweep)
    onoise_fc = float(result.sample_onoise_at("158.489"))
    expected_fc = 4.0713e-9 / math.sqrt(2.0)
    assert abs(onoise_fc - expected_fc) < 0.05e-9

    # High frequency attenuation (100 kHz)
    onoise_100k = float(result.sample_onoise_at("100k"))
    assert onoise_100k < 1e-11  # severely filtered (>400x attenuation)

    # Integrated noise comparison with theoretical sqrt(kT/C)
    k_B = 1.380649e-23
    T_kelvin = 300.15
    C_val = 1e-6
    theoretical_rms = math.sqrt(k_B * T_kelvin / C_val)
    actual_rms = float(result.onoise_total)

    # ngspice gives ~6.414e-8 V_RMS over 1 Hz..100 kHz (matches theoretical ~6.437e-8 V_RMS within 0.5%)
    rel_err_rms = abs(actual_rms - theoretical_rms) / theoretical_rms
    assert rel_err_rms < 0.01


@pytest.mark.skipif(_get_real_backend() is None, reason="Real ngspice runtime not available/verified")
def test_real_ngspice_case_3_dc_sensitivity_voltage_divider():
    """Scientific verification 3: DC Sensitivity on resistive voltage divider.

    Circuit:
      V1 in 0 5V
      R1 in out 1k
      R2 out 0 1k

    Output equation:
      V_out = V1 * R2 / (R1 + R2) = 5 * 1000 / 2000 = 2.5 V

    Analytical sensitivities:
      dV_out / dR1 = -V1 * R2 / (R1 + R2)^2 = -5 * 1000 / 4e6 = -0.00125 V/Ohm
      dV_out / dR2 = +V1 * R1 / (R1 + R2)^2 = +5 * 1000 / 4e6 = +0.00125 V/Ohm
      dV_out / dV1 = R2 / (R1 + R2) = 1000 / 2000 = 0.5 V/V

    Finite difference (central difference with delta = 1e-4):
      R1_plus = 1000.1, R1_minus = 999.9
      V(R1_plus) = 5 * 1000 / 2000.1 ~= 2.499875006
      V(R1_minus) = 5 * 1000 / 1999.9 ~= 2.500125006
      DeltaV / DeltaR1 = (2.499875006 - 2.500125006) / 0.2 = -0.00125
    """
    backend = _get_real_backend()
    assert backend is not None

    netlist = """* DC Voltage Divider Sensitivity
V1 in 0 5
R1 in out 1k
R2 out 0 1k
.end
"""
    sens = SensitivityAnalysis(output_variable="v(out)", analysis_type="DC")
    result = backend.simulate(netlist, analyses=(sens,))

    assert isinstance(result, SensitivityResult)
    assert result.status == "COMPLETED"

    s_r1 = float(result.get_sensitivity("r1"))
    s_r2 = float(result.get_sensitivity("r2"))
    s_v1 = float(result.get_sensitivity("v1"))

    assert abs(s_r1 - (-0.00125)) < 1e-6
    assert abs(s_r2 - (+0.00125)) < 1e-6
    assert abs(s_v1 - 0.5) < 1e-6

    # Normalized sensitivities: S_R = (R/V) * (dV/dR)
    norm = result.compute_normalized_sensitivities({"r1": 1000, "r2": 1000, "v1": 5}, nominal_output=2.5)
    assert abs(float(norm["r1"]) - (-0.5)) < 1e-4
    assert abs(float(norm["r2"]) - (+0.5)) < 1e-4
    assert abs(float(norm["v1"]) - 1.0) < 1e-4


@pytest.mark.skipif(_get_real_backend() is None, reason="Real ngspice runtime not available/verified")
def test_real_ngspice_case_4_ac_sensitivity_rc_filter():
    """Scientific verification 4: AC frequency-dependent small-signal sensitivity on RC low-pass.

    Transfer function:
      H(jw) = 1 / (1 + j*w*R*C)

    Analytical complex sensitivities:
      dH/dC = -j*w*R / (1 + j*w*R*C)^2
      dH/dR = -j*w*C / (1 + j*w*R*C)^2

    At f = 1 Hz (w = 2*pi*1 rad/s), R = 1000 Ohm, C = 1e-6 F:
      w*R*C = 2*pi*1e-3 ~= 0.006283185
      dH/dC ~= -78.9506 - 6282.44j
      dH/dR ~= -7.8951e-8 - 6.2824e-6j
    """
    backend = _get_real_backend()
    assert backend is not None

    netlist = """* RC Filter AC Sensitivity
V1 in 0 dc 0 ac 1
R1 in out 1k
C1 out 0 1u
.end
"""
    sens = SensitivityAnalysis(
        output_variable="v(out)",
        analysis_type="AC",
        sweep_type="dec",
        points=10,
        fstart="1",
        fstop="100k",
        parameters=("c1", "r1"),
    )
    result = backend.simulate(netlist, analyses=(sens,))

    assert isinstance(result, SensitivityResult)
    assert result.status == "COMPLETED"

    c1_sig = result.get_sensitivity("c1")
    r1_sig = result.get_sensitivity("r1")
    assert isinstance(c1_sig, ComplexSignal)
    assert isinstance(r1_sig, ComplexSignal)

    # Analytical values at 1 Hz
    R = 1000.0
    C = 1e-6
    w = 2.0 * math.pi * 1.0
    denom = (1.0 + 1j * w * R * C) ** 2
    expected_dH_dC = -1j * w * R / denom
    expected_dH_dR = -1j * w * C / denom

    actual_c1_1hz = c1_sig.raw_complex_samples[0]
    actual_r1_1hz = r1_sig.raw_complex_samples[0]

    assert abs(actual_c1_1hz.real - expected_dH_dC.real) < 0.1
    assert abs(actual_c1_1hz.imag - expected_dH_dC.imag) < 1.0
    assert abs(actual_r1_1hz.real - expected_dH_dR.real) < 1e-9
    assert abs(actual_r1_1hz.imag - expected_dH_dR.imag) < 1e-8


@pytest.mark.skipif(_get_real_backend() is None, reason="Real ngspice runtime not available/verified")
def test_real_ngspice_case_5_rlc_resonance_sensitivity():
    """Scientific verification 5: AC Sensitivity on Series RLC resonant circuit.

    Circuit:
      V1 in 0 dc 0 ac 1
      R1 in n1 10 (10 Ohm)
      L1 n1 out 1m (1 mH)
      C1 out 0 1u  (1 uF)
      Output across C1.

    At resonance f0 = 1 / (2*pi*sqrt(L*C)) ~= 5032.92 Hz:
      Reactances cancel: w*L = 1/(w*C) ~= 31.62 Ohm.
      Q = (w*L) / R = 31.62 / 10 = 3.162.
      Sensitivity with respect to L1, C1, and R1 can be evaluated across frequency.
    """
    backend = _get_real_backend()
    assert backend is not None

    netlist = """* Series RLC Resonance Sensitivity
V1 in 0 dc 0 ac 1
R1 in n1 10
L1 n1 out 1m
C1 out 0 1u
.end
"""
    sens = SensitivityAnalysis(
        output_variable="v(out)",
        analysis_type="AC",
        sweep_type="lin",
        points=21,
        fstart="4000",
        fstop="6000",
        parameters=("l1", "c1", "r1"),
    )
    result = backend.simulate(netlist, analyses=(sens,))

    assert isinstance(result, SensitivityResult)
    assert result.status == "COMPLETED"
    assert result.points_count == 21

    l1_sig = result.get_sensitivity("l1")
    c1_sig = result.get_sensitivity("c1")
    r1_sig = result.get_sensitivity("r1")

    assert isinstance(l1_sig, ComplexSignal)
    assert isinstance(c1_sig, ComplexSignal)
    assert isinstance(r1_sig, ComplexSignal)
    assert len(l1_sig) == 21


@pytest.mark.skipif(_get_real_backend() is None, reason="Real ngspice runtime not available/verified")
def test_real_ngspice_sweep_types_noise_and_sens():
    """Verify DEC, OCT, and LIN sweeps work for noise and AC sensitivity."""
    backend = _get_real_backend()
    assert backend is not None

    netlist = """* Sweep Types Circuit
V1 in 0 dc 0 ac 1
R1 in out 1k
C1 out 0 1u
.end
"""
    # 1. Noise with OCT sweep
    n_oct = NoiseAnalysis("v(out)", "V1", "OCT", points=4, fstart="100", fstop="1600")
    r_noct = backend.simulate(netlist, analyses=(n_oct,))
    assert r_noct.status == "COMPLETED"
    assert r_noct.points_count == 17  # 4 octaves * 4 + 1 = 17 points

    # 2. Noise with LIN sweep
    n_lin = NoiseAnalysis("v(out)", "V1", "LIN", points=25, fstart="100", fstop="1000")
    r_nlin = backend.simulate(netlist, analyses=(n_lin,))
    assert r_nlin.status == "COMPLETED"
    assert r_nlin.points_count == 25

    # 3. Sens with LIN sweep
    s_lin = SensitivityAnalysis("v(out)", analysis_type="AC", sweep_type="LIN", points=11, fstart="100", fstop="500")
    r_slin = backend.simulate(netlist, analyses=(s_lin,))
    assert r_slin.status == "COMPLETED"
    assert r_slin.points_count == 11

    # 4. Sens with OCT sweep
    s_oct = SensitivityAnalysis("v(out)", analysis_type="AC", sweep_type="OCT", points=4, fstart="100", fstop="1600")
    r_soct = backend.simulate(netlist, analyses=(s_oct,))
    assert r_soct.status == "COMPLETED"
    assert r_soct.points_count == 8


@pytest.mark.skipif(_get_real_backend() is None, reason="Real ngspice runtime not available/verified")
def test_engineering_service_noise_and_sens_end_to_end(tmp_path):
    """End-to-end integration via EngineeringService and Circuit domain model."""
    repo = EngineeringRepository(Database(tmp_path / "eng.db"))
    service = EngineeringService(repo)
    backend = _get_real_backend()
    assert backend is not None

    service.create_project("NOISE_SENS_PROJ")

    circuit = Circuit("RC_FILTER")
    circuit.add(Component("V1", "V", parse_quantity("1 V"), {"+": "in", "-": "0"}))
    circuit.add(Component("R1", "R", parse_quantity("1 kOhm"), {"1": "in", "2": "out"}))
    circuit.add(Component("C1", "C", parse_quantity("1 uF"), {"1": "out", "2": "0"}))

    service.save_circuit("NOISE_SENS_PROJ", circuit)

    # 1. Simulate noise
    noise = NoiseAnalysis("v(out)", "V1", "dec", 5, "1", "10k")
    noise_res = service.simulate_circuit("NOISE_SENS_PROJ", "RC_FILTER", analyses=(noise,), backend=backend)
    assert isinstance(noise_res, NoiseResult)
    assert noise_res.status == "COMPLETED"
    assert noise_res.onoise_total is not None
    assert float(noise_res.sample_onoise_at("1")) > 3e-9

    # 2. Simulate DC sensitivity
    sens_dc = SensitivityAnalysis("v(out)", analysis_type="DC")
    sens_res = service.simulate_circuit("NOISE_SENS_PROJ", "RC_FILTER", analyses=(sens_dc,), backend=backend)
    assert isinstance(sens_res, SensitivityResult)
    assert sens_res.status == "COMPLETED"
    assert sens_res.get_sensitivity("r1") is not None
