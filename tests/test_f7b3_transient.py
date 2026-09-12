"""Tests for F7-B3 Transient Analysis: domain model, netlist building, parser, and real ngspice execution."""

import math
from decimal import Decimal
from pathlib import Path
import pytest

from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.simulation import (
    Signal,
    SimulationJob,
    SimulationResult,
    TransientAnalysis,
    parse_spice_number,
)
from academic_core.domain.engineering.units import parse_quantity
from academic_core.infrastructure.cas import FileBlobStore
from academic_core.infrastructure.ngspice import (
    NgSpiceBackend,
    SimulationExecution,
)
from academic_core.infrastructure.ngspice_parser import parse_ngspice_output
from academic_core.infrastructure.database import Database
from academic_core.infrastructure.engineering import EngineeringRepository
from academic_core.application.engineering import EngineeringService


# ==============================================================================
# 1. parse_spice_number tests
# ==============================================================================

def test_parse_spice_number_standard():
    assert parse_spice_number("0") == Decimal("0")
    assert parse_spice_number("123.45") == Decimal("123.45")
    assert parse_spice_number("-5.2e-3") == Decimal("-0.0052")
    assert parse_spice_number(Decimal("3.14")) == Decimal("3.14")
    assert parse_spice_number(42) == Decimal("42")
    assert parse_spice_number(0.001) == Decimal("0.001")


def test_parse_spice_number_engineering_suffixes():
    assert parse_spice_number("10u") == Decimal("0.000010")
    assert parse_spice_number("5m") == Decimal("0.005")
    assert parse_spice_number("1k") == Decimal("1000")
    assert parse_spice_number("2MEG") == Decimal("2000000")
    assert parse_spice_number("100n") == Decimal("0.000000100")
    assert parse_spice_number("15p") == Decimal("0.000000000015")
    assert parse_spice_number("1G") == Decimal("1000000000")


def test_parse_spice_number_invalid():
    with pytest.raises(ValueError):
        parse_spice_number("")
    with pytest.raises(ValueError):
        parse_spice_number("invalid_text")


# ==============================================================================
# 2. TransientAnalysis domain model tests
# ==============================================================================

def test_transient_analysis_valid_basic():
    tran = TransientAnalysis(tstep=Decimal("1e-5"), tstop=Decimal("0.005"))
    assert tran.tstep == Decimal("0.00001")
    assert tran.tstop == Decimal("0.005")
    assert tran.tstart == Decimal("0")
    assert tran.tmax is None
    assert tran.uic is False
    assert tran.to_spice_card() == ".tran 0.00001 0.005"


def test_transient_analysis_with_all_options():
    tran = TransientAnalysis(
        tstep="10u",
        tstop="5m",
        tstart="1m",
        tmax="10u",
        uic=True,
    )
    assert tran.tstep == Decimal("0.000010")
    assert tran.tstop == Decimal("0.005")
    assert tran.tstart == Decimal("0.001")
    assert tran.tmax == Decimal("0.000010")
    assert tran.uic is True
    assert tran.to_spice_card() == ".tran 0.000010 0.005 0.001 0.000010 uic"


def test_transient_analysis_validation_errors():
    # tstep <= 0
    with pytest.raises(ValueError, match="transient step must be positive"):
        TransientAnalysis(tstep="0", tstop="5m")
    with pytest.raises(ValueError, match="transient step must be positive"):
        TransientAnalysis(tstep="-1u", tstop="5m")

    # tstop <= 0
    with pytest.raises(ValueError, match="transient stop must be positive"):
        TransientAnalysis(tstep="10u", tstop="0")

    # tstart < 0
    with pytest.raises(ValueError, match="transient start must be non-negative"):
        TransientAnalysis(tstep="10u", tstop="5m", tstart="-1m")

    # tstop <= tstart
    with pytest.raises(ValueError, match="must be greater than start"):
        TransientAnalysis(tstep="10u", tstop="1m", tstart="2m")
    with pytest.raises(ValueError, match="must be greater than start"):
        TransientAnalysis(tstep="10u", tstop="1m", tstart="1m")

    # tmax <= 0
    with pytest.raises(ValueError, match="transient tmax must be positive"):
        TransientAnalysis(tstep="10u", tstop="5m", tmax="0")


def test_transient_analysis_from_string():
    tran1 = TransientAnalysis.from_string(".tran 10u 5m")
    assert tran1.tstep == Decimal("0.000010")
    assert tran1.tstop == Decimal("0.005")
    assert tran1.uic is False

    tran2 = TransientAnalysis.from_string("tran 10u 5m 1m uic")
    assert tran2.tstep == Decimal("0.000010")
    assert tran2.tstop == Decimal("0.005")
    assert tran2.tstart == Decimal("0.001")
    assert tran2.tmax is None
    assert tran2.uic is True

    tran3 = TransientAnalysis.from_string(".tran 10u 5m 0 10u uic")
    assert tran3.tmax == Decimal("0.000010")
    assert tran3.uic is True

    with pytest.raises(ValueError, match="malformed transient directive"):
        TransientAnalysis.from_string(".tran 10u")


# ==============================================================================
# 3. SimulationJob deck generation tests
# ==============================================================================

def test_simulation_job_build_tran_card():
    netlist = "RC Circuit\nV1 in 0 5\nR1 in out 1k\nC1 out 0 1u\n.end\n"
    tran = TransientAnalysis(tstep="10u", tstop="5m")
    job = SimulationJob(netlist, analyses=(tran,))
    deck = job.build_netlist()

    assert ".tran 0.000010 0.005" in deck
    assert ".print tran" in deck
    assert "v(in)" in deck
    assert "v(out)" in deck
    assert "i(v1)" in deck
    assert deck.endswith(".end\n")


def test_simulation_job_preserves_existing_print_tran():
    netlist = "RC Circuit\nV1 in 0 5\nR1 in out 1k\nC1 out 0 1u\n.print tran v(out)\n.end\n"
    tran = TransientAnalysis(tstep="10u", tstop="5m")
    job = SimulationJob(netlist, analyses=(tran,))
    deck = job.build_netlist()

    # Should not duplicate .print tran
    assert deck.count(".print tran") == 1
    assert ".print tran v(out)" in deck


def test_simulation_job_string_tran_analysis():
    netlist = "RC Circuit\nV1 in 0 5\nR1 in out 1k\nC1 out 0 1u\n.end\n"
    job = SimulationJob(netlist, analyses=("tran 10u 5m",))
    deck = job.build_netlist()

    assert ".tran 0.000010 0.005" in deck
    assert ".print tran" in deck


# ==============================================================================
# 4. ngspice_parser transient table parsing & SimulationResult accessors
# ==============================================================================

MOCK_TRAN_OUTPUT = """
Circuit: RC Charging Circuit

Index   time            v(in)           v(out)          v1#branch       
--------------------------------------------------------------------------------
0	0.000000e+00	0.000000e+00	0.000000e+00	-5.00000e-03	
1	1.000000e-03	5.000000e+00	3.160603e+00	-1.83939e-03	
2	2.000000e-03	5.000000e+00	4.323324e+00	-6.76676e-04	
3	3.000000e-03	5.000000e+00	4.751065e+00	-2.48935e-04	
4	4.000000e-03	5.000000e+00	4.908422e+00	-9.15782e-05	
5	5.000000e-03	5.000000e+00	4.966310e+00	-3.36897e-05	
"""


def test_parse_ngspice_transient_table():
    execution = SimulationExecution(
        status="COMPLETED",
        backend_id="ngspice",
        backend_version="ngspice-47",
        executable_path="ngspice_con.exe",
        started_at="2026-09-12T20:00:00Z",
        finished_at="2026-09-12T20:00:01Z",
        duration_seconds=0.1,
        exit_code=0,
        stdout=MOCK_TRAN_OUTPUT,
        stderr="",
        workspace="",
        command_metadata=(),
        timeout_seconds=30.0,
        cancelled=False,
        input_hash="hash123",
    )

    result = parse_ngspice_output(execution, analyses=("tran",))

    assert result.status == "COMPLETED"
    assert result.points_count == 6

    # Verify time axis
    assert result.time_axis is not None
    assert result.time_axis.name == "time"
    assert result.time_axis.axis == "time"
    assert result.time_axis.unit == "s"
    assert len(result.time_axis.samples) == 6
    assert result.time_axis.samples[0] == Decimal("0.0")
    assert result.time_axis.samples[1] == Decimal("0.001")
    assert result.time_axis.samples[5] == Decimal("0.005")

    # Verify v(out)
    v_out = result.get_signal("v(out)")
    assert v_out is not None
    assert v_out.axis == "voltage"
    assert v_out.unit == "V"
    assert len(v_out.samples) == 6
    assert v_out.samples[0] == Decimal("0.0")
    assert v_out.samples[1] == Decimal("3.160603")
    assert v_out.samples[5] == Decimal("4.966310")

    # Verify IEEE float separation
    assert isinstance(v_out.samples[1], Decimal)
    assert isinstance(v_out.raw_samples[1], float)
    assert math.isclose(v_out.raw_samples[1], 3.160603)

    # Verify branch current
    i_v1 = result.get_signal("i(v1)")
    assert i_v1 is not None
    assert i_v1.axis == "current"
    assert i_v1.unit == "A"
    assert i_v1.samples[0] == Decimal("-0.005")
    assert i_v1.samples[1] == Decimal("-0.00183939")

    # Verify sample_at
    assert result.sample_at("v(out)", "1m") == Decimal("3.160603")
    assert result.sample_at("v(out)", Decimal("0.005")) == Decimal("4.966310")
    assert result.sample_at("i(v1)", "0") == Decimal("-0.005")


def test_parse_ngspice_transient_cas_storage(tmp_path):
    cas_dir = tmp_path / "cas"
    store = FileBlobStore(cas_dir)

    execution = SimulationExecution(
        status="COMPLETED",
        backend_id="ngspice",
        backend_version="ngspice-47",
        executable_path="ngspice_con.exe",
        started_at="2026-09-12T20:00:00Z",
        finished_at="2026-09-12T20:00:01Z",
        duration_seconds=0.1,
        exit_code=0,
        stdout=MOCK_TRAN_OUTPUT,
        stderr="",
        workspace="",
        command_metadata=(),
        timeout_seconds=30.0,
        cancelled=False,
        input_hash="hash123",
    )

    result = parse_ngspice_output(execution, cas_store=store, analyses=("tran",))
    assert result.raw_artifact_hash
    stored_bytes = store.get_bytes(result.raw_artifact_hash)
    assert b"Index   time            v(in)" in stored_bytes


# ==============================================================================
# 5. Real ngspice runtime integration tests (RC Transient)
# ==============================================================================

def _get_real_backend() -> NgSpiceBackend | None:
    backend = NgSpiceBackend()
    if backend.detect().verified:
        return backend
    return None


@pytest.mark.skipif(_get_real_backend() is None, reason="Real ngspice runtime not available/verified")
def test_real_ngspice_transient_case_a_rc_charging():
    """Scientific verification Case A: RC step charging.

    Circuit:
      V1 in 0 pulse(0 5 0 1n 1n 10m)  (5V step starting at t=0)
      R1 in out 1k                     (1000 Ohm)
      C1 out 0 1u                      (1 uF)
      .tran 10u 5m                     (tstep=10us, tstop=5ms)

    Theoretical equations:
      tau = R * C = 1000 * 1e-6 = 1 ms = 0.001 s
      Vc(t) = 5 * (1 - exp(-t / tau))

    Expected values:
      Vc(0) = 0.0 V
      Vc(1 ms) = 5 * (1 - 1/e) ~= 3.16060 V
      Vc(5 ms) = 5 * (1 - exp(-5)) ~= 4.96631 V

    Justified tolerances:
      At t=0: within 0.02 V (numerical step transition).
      At t=1 ms: within 0.02 V (< 0.6% relative error).
      At t=5 ms: within 0.02 V (< 0.4% relative error).
    """
    backend = _get_real_backend()
    assert backend is not None

    netlist = """* RC Step Charging Circuit
V1 in 0 pulse(0 5 0 1n 1n 10m)
R1 in out 1k
C1 out 0 1u
.end
"""
    tran = TransientAnalysis(tstep="10u", tstop="5m")
    result = backend.simulate(netlist, analyses=(tran,))

    assert result.status == "COMPLETED"
    assert result.mocked is False
    assert result.points_count > 100  # 5ms / 10us ~ 500 points

    # Verify time axis limits
    time_ax = result.time_axis
    assert time_ax is not None
    assert time_ax.samples[0] == Decimal("0.0")
    assert time_ax.samples[-1] == Decimal("0.005")

    # Sample V(out) at 0, 1ms, 5ms
    v_0 = float(result.sample_at("v(out)", "0"))
    v_1ms = float(result.sample_at("v(out)", "1m"))
    v_5ms = float(result.sample_at("v(out)", "5m"))

    # Theoretical values
    tau = 0.001
    theoretical_v1 = 5.0 * (1.0 - math.exp(-1.0))  # ~3.16060 V
    theoretical_v5 = 5.0 * (1.0 - math.exp(-5.0))  # ~4.96631 V

    assert abs(v_0 - 0.0) <= 0.02, f"Vc(0) = {v_0}, expected ~0.0 V"
    assert abs(v_1ms - theoretical_v1) <= 0.02, f"Vc(1ms) = {v_1ms}, expected ~{theoretical_v1} V"
    assert abs(v_5ms - theoretical_v5) <= 0.02, f"Vc(5ms) = {v_5ms}, expected ~{theoretical_v5} V"


@pytest.mark.skipif(_get_real_backend() is None, reason="Real ngspice runtime not available/verified")
def test_real_ngspice_transient_case_b_rc_current():
    """Scientific verification Case B: RC charging current.

    Theoretical equations:
      Ic(t) = (V0 / R) * exp(-t / tau) = 5 mA * exp(-t / 1ms)
    SPICE branch convention for source V1: current leaving V1 is negative in i(v1).
      Immediately after pulse rise (t >= 1ns):
      I(V1)(t) = -5 mA * exp(-t / 1ms)

    Expected values:
      I(0) = 0.0 A (source is at 0 V before pulse step)
      I(10 us) ~= -5 mA * exp(-0.01) ~= -4.95 mA = -0.00495 A
      I(1 ms) ~= -5 mA * exp(-1) = -1.8394 mA = -0.0018394 A
      I(5 ms) ~= -5 mA * exp(-5) = -0.0337 mA = -0.0000337 A

    Justified tolerance:
      0.0001 A for discrete timestep resolution.
    """
    backend = _get_real_backend()
    assert backend is not None

    netlist = """* RC Current Verification Circuit
V1 in 0 pulse(0 5 0 1n 1n 10m)
R1 in out 1k
C1 out 0 1u
.end
"""
    tran = TransientAnalysis(tstep="10u", tstop="5m")
    result = backend.simulate(netlist, analyses=(tran,))

    assert result.status == "COMPLETED"

    # Sample I(V1)
    i_0 = float(result.sample_at("i(v1)", "0"))
    i_10us = float(result.sample_at("i(v1)", "10u"))
    i_1ms = float(result.sample_at("i(v1)", "1m"))
    i_5ms = float(result.sample_at("i(v1)", "5m"))

    theoretical_i10us = -0.005 * math.exp(-0.01)  # ~ -0.004950 A
    theoretical_i1 = -0.005 * math.exp(-1.0)      # ~ -0.0018394 A
    theoretical_i5 = -0.005 * math.exp(-5.0)      # ~ -0.0000337 A

    assert abs(i_0 - 0.0) <= 0.0001, f"I(0) = {i_0}, expected ~0.0 A"
    assert abs(i_10us - theoretical_i10us) <= 0.0001, f"I(10us) = {i_10us}, expected ~{theoretical_i10us} A"
    assert abs(i_1ms - theoretical_i1) <= 0.0001, f"I(1ms) = {i_1ms}, expected ~{theoretical_i1} A"
    assert abs(i_5ms - theoretical_i5) <= 0.00005, f"I(5ms) = {i_5ms}, expected ~{theoretical_i5} A"


@pytest.mark.skipif(_get_real_backend() is None, reason="Real ngspice runtime not available/verified")
def test_real_ngspice_transient_uic_initial_condition():
    """Verify UIC (use initial conditions) with constant DC source."""
    backend = _get_real_backend()
    assert backend is not None

    netlist = """* RC with UIC
V1 in 0 5
R1 in out 1k
C1 out 0 1u ic=0
.end
"""
    tran = TransientAnalysis(tstep="10u", tstop="5m", uic=True)
    result = backend.simulate(netlist, analyses=(tran,))

    assert result.status == "COMPLETED"
    v_0 = float(result.sample_at("v(out)", "0"))
    v_1ms = float(result.sample_at("v(out)", "1m"))
    i_0 = float(result.sample_at("i(v1)", "0"))

    # With UIC, V(out) starts at 0V and I(V1) starts at -5mA
    assert abs(v_0 - 0.0) <= 0.02
    assert abs(v_1ms - 3.1606) <= 0.02
    assert abs(i_0 - (-0.005)) <= 0.0002


@pytest.mark.skipif(_get_real_backend() is None, reason="Real ngspice runtime not available/verified")
def test_engineering_service_transient_end_to_end(tmp_path):
    """End-to-end integration via EngineeringService and Circuit domain model."""
    repo = EngineeringRepository(Database(tmp_path / "eng.db"))
    service = EngineeringService(repo)
    backend = _get_real_backend()
    assert backend is not None

    # Create project and circuit
    service.create_project("RC_TRAN_PROJ")

    circuit = Circuit("RC_STEP")
    circuit.add(Component("V1", "V", parse_quantity("5 V"), {"+": "in", "-": "0"}))
    circuit.add(Component("R1", "R", parse_quantity("1 kOhm"), {"1": "in", "2": "out"}))
    circuit.add(Component("C1", "C", parse_quantity("1 uF"), {"1": "out", "2": "0"}))

    service.save_circuit("RC_TRAN_PROJ", circuit)

    tran = TransientAnalysis(tstep="10u", tstop="5m", uic=True)
    result = service.simulate_circuit("RC_TRAN_PROJ", "RC_STEP", analyses=(tran,), backend=backend)

    assert result.status == "COMPLETED"
    assert result.points_count > 100
    v_out_1ms = float(result.sample_at("v(out)", "1m"))
    assert abs(v_out_1ms - 3.1606) < 0.02
