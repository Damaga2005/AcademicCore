"""F7-B2 tests: DC Sweep real con ngspice.

Covers:
- DCSweepAnalysis parameter validation (empty source, zero step, mismatched range/step signs)
- Deterministic SPICE deck generation for DC sweep (.dc and .print dc)
- Structured parser for multi-point DC transfer characteristic tables
- Multi-point Signal model and sweep axis representation
- Decimal (domain) vs float (solver) precision separation across all samples
- Error and malformed output handling
- CAS raw artifact persistence
- Determinism and provenance
- Real DC Sweep simulation against ngspice 47 (ngspice_con.exe):
  - Validation A: Resistive divider V1 = 0..10V, step = 1V (11 points, Vout = Vin / 2)
  - Validation B: Second range/step (-5..5V, step 0.5V, 21 points, extrema, current signal)
- Full pipeline integration: Circuit -> Netlist -> SimulationJob -> NgSpiceBackend -> Parser -> SimulationResult
"""

from decimal import Decimal
from pathlib import Path

import pytest

from academic_core.application.engineering import EngineeringService
from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.simulation import (
    DCSweepAnalysis, Signal, SimulationJob, SimulationResult,
)
from academic_core.domain.engineering.units import parse_quantity
from academic_core.infrastructure.cas import FileBlobStore
from academic_core.infrastructure.database import Database
from academic_core.infrastructure.engineering import EngineeringRepository
from academic_core.infrastructure.ngspice import NgSpiceBackend, SimulationExecution
from academic_core.infrastructure.ngspice_parser import parse_ngspice_output

SAMPLE_DC_SWEEP_OUTPUT = """******
** ngspice-47 : Circuit level simulation program
** Compiled with KLU Direct Linear Solver
******

Batch mode

Comments and warnings go to log-file: output.log

Note: No compatibility mode selected!

Circuit: * dc sweep fixture

Doing analysis at TEMP = 27.000000 and TNOM = 27.000000

Using SPARSE 1.3 as Direct Linear Solver

No. of Data Rows : 5
--------------------------------------------------------------------------------
Index   v-sweep         v(in)           v(out)          v1#branch       
--------------------------------------------------------------------------------
0	0.000000e+00	0.000000e+00	0.000000e+00	0.000000e+00	
1	2.500000e+00	2.500000e+00	1.250000e+00	-1.25000e-03	
2	5.000000e+00	5.000000e+00	2.500000e+00	-2.50000e-03	
3	7.500000e+00	7.500000e+00	3.750000e+00	-3.75000e-03	
4	1.000000e+01	1.000000e+01	5.000000e+00	-5.00000e-03	

Total analysis time (seconds) = 0.000867

ngspice-47 done
"""


def _make_dc_execution(
    stdout: str = SAMPLE_DC_SWEEP_OUTPUT,
    stderr: str = "",
    status: str = "COMPLETED",
    exit_code: int = 0,
) -> SimulationExecution:
    return SimulationExecution(
        status=status,
        backend_id="ngspice",
        backend_version="47",
        executable_path="ngspice_con.exe",
        started_at="2026-09-12T22:30:00Z",
        finished_at="2026-09-12T22:30:01Z",
        duration_seconds=1.0,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        workspace="/tmp/ws_dc",
        command_metadata=("ngspice_con.exe", "-b", "-o", "output.log", "input.cir"),
        timeout_seconds=30.0,
        cancelled=False,
        input_hash="dchash123",
    )


# ==============================================================================
# 1. Parameter Validation
# ==============================================================================

def test_dc_sweep_valid_parameters():
    sweep = DCSweepAnalysis(source="V1", start=Decimal("0"), stop=Decimal("10"), step=Decimal("1"))
    assert sweep.source == "V1"
    assert sweep.start == Decimal("0")
    assert sweep.stop == Decimal("10")
    assert sweep.step == Decimal("1")
    assert sweep.expected_points == 11
    assert sweep.to_spice_card() == ".dc V1 0 10 1"


def test_dc_sweep_negative_step_validation():
    # Decreasing range requires negative step
    sweep_dec = DCSweepAnalysis(source="v1", start=Decimal("10"), stop=Decimal("0"), step=Decimal("-2"))
    assert sweep_dec.source == "V1"
    assert sweep_dec.expected_points == 6
    assert sweep_dec.to_spice_card() == ".dc V1 10 0 -2"


def test_dc_sweep_invalid_parameters():
    # Empty source
    with pytest.raises(ValueError, match="source must not be empty"):
        DCSweepAnalysis(source="", start=0, stop=10, step=1)

    # Zero step
    with pytest.raises(ValueError, match="step cannot be 0"):
        DCSweepAnalysis(source="V1", start=0, stop=10, step=0)

    # Increasing range with negative step
    with pytest.raises(ValueError, match="increasing range"):
        DCSweepAnalysis(source="V1", start=0, stop=10, step=-1)

    # Decreasing range with positive step
    with pytest.raises(ValueError, match="decreasing range"):
        DCSweepAnalysis(source="V1", start=10, stop=0, step=1)


def test_dc_sweep_from_string():
    s1 = DCSweepAnalysis.from_string(".dc V1 0 10 1")
    assert (s1.source, s1.start, s1.stop, s1.step) == ("V1", Decimal("0"), Decimal("10"), Decimal("1"))

    s2 = DCSweepAnalysis.from_string("dc Vin -5 5 0.5")
    assert (s2.source, s2.start, s2.stop, s2.step) == ("VIN", Decimal("-5"), Decimal("5"), Decimal("0.5"))

    with pytest.raises(ValueError, match="malformed"):
        DCSweepAnalysis.from_string(".dc V1 0 10")


# ==============================================================================
# 2. Deterministic Deck Generation
# ==============================================================================

def test_simulation_job_deterministic_deck_generation():
    netlist = "* Resistive circuit\nV1 in 0 5\nR1 in out 1k\nR2 out 0 1k\n.end\n"
    sweep = DCSweepAnalysis(source="V1", start=Decimal("0"), stop=Decimal("10"), step=Decimal("1"))
    job = SimulationJob(netlist=netlist, analyses=(sweep,))
    deck = job.build_netlist()

    assert ".dc V1 0 10 1" in deck
    assert ".print dc" in deck
    assert "v(in)" in deck
    assert "v(out)" in deck
    assert "i(v1)" in deck
    assert deck.endswith(".end\n")

    # Re-running produces exact same deck
    deck2 = job.build_netlist()
    assert deck == deck2


# ==============================================================================
# 3. Parser Unit Tests (Multi-point tables, precision, axis, CAS, determinism)
# ==============================================================================

def test_parse_dc_sweep_multi_point_table():
    exec_info = _make_dc_execution()
    res = parse_ngspice_output(exec_info, netlist="V1 in 0 0\n.end")

    assert res.status == "COMPLETED"
    assert res.exit_code == 0
    assert res.points_count == 5

    # Sweep axis signal
    axis = res.sweep_axis
    assert axis is not None
    assert axis.name == "v-sweep"
    assert axis.unit == "V"
    assert axis.axis == "sweep"
    assert len(axis.samples) == 5
    assert axis.samples == (Decimal("0.000000"), Decimal("2.500000"), Decimal("5.000000"), Decimal("7.500000"), Decimal("10.00000"))

    # Multi-point response signals
    vout_samples = res.voltage_samples("out")
    assert len(vout_samples) == 5
    assert vout_samples == (Decimal("0.000000"), Decimal("1.250000"), Decimal("2.500000"), Decimal("3.750000"), Decimal("5.000000"))

    # Raw IEEE 754 float samples
    sig_out = res.get_signal("v(out)")
    assert sig_out.raw_samples == (0.0, 1.25, 2.5, 3.75, 5.0)

    # Current samples
    i_samples = res.current_samples("v1")
    assert len(i_samples) == 5
    assert i_samples[0] == Decimal("0.000000")
    assert abs(float(i_samples[-1]) - (-0.005)) < 1e-6


def test_parse_dc_sweep_errors_and_malformed():
    err_text = """******
** ngspice-47
******
Error: no circuits loaded.
"""
    exec_info = _make_dc_execution(stdout=err_text, exit_code=1, status="FAILED")
    res = parse_ngspice_output(exec_info)

    assert res.status == "FAILED"
    assert "no circuits loaded." in res.errors
    assert res.points_count == 0


def test_parse_dc_sweep_determinism_and_cas(tmp_path):
    cas = FileBlobStore(tmp_path / "cas")
    exec_info = _make_dc_execution()

    res1 = parse_ngspice_output(exec_info, cas_store=cas)
    res2 = parse_ngspice_output(exec_info, cas_store=cas)

    assert res1.signals == res2.signals
    assert res1.raw_artifact_hash == res2.raw_artifact_hash
    assert res1.provenance == res2.provenance

    # Confirm stored CAS content
    blob = cas.get_bytes(res1.raw_artifact_hash)
    assert SAMPLE_DC_SWEEP_OUTPUT.encode("utf-8") in blob


# ==============================================================================
# 4. Real Scientific Validation (ngspice 47 via ngspice_con.exe)
# ==============================================================================

@pytest.mark.external
@pytest.mark.integration
def test_real_ngspice_dc_sweep_validation_a():
    """Validation A: Resistive divider V1 = 0..10V, step = 1V (11 points).

    Circuit:
      V1 in 0 0
      R1 in out 1k
      R2 out 0 1k
    Expected:
      Exact 11 points: 0, 1, 2, ..., 10 V
      V(out) = V1 / 2 across ALL 11 points
    """
    b = NgSpiceBackend()
    info = b.detect()
    if not info.available:
        pytest.skip("ngspice not available")

    netlist = """* DC Sweep Validation A: Resistive divider
V1 in 0 0
R1 in out 1k
R2 out 0 1k
.end
"""
    sweep = DCSweepAnalysis(source="V1", start=Decimal("0"), stop=Decimal("10"), step=Decimal("1"))
    res = b.simulate(netlist, analyses=(sweep,))

    assert res.status == "COMPLETED"
    assert res.exit_code == 0
    assert res.points_count == 11
    assert not res.errors

    sweep_samples = res.sweep_axis.samples
    vin_samples = res.voltage_samples("in")
    vout_samples = res.voltage_samples("out")

    assert len(sweep_samples) == 11
    assert len(vin_samples) == 11
    assert len(vout_samples) == 11

    for i in range(11):
        expected_v1 = Decimal(i)
        expected_vout = expected_v1 / Decimal(2)

        # Check precision and values
        assert abs(float(sweep_samples[i]) - float(expected_v1)) < 1e-6
        assert abs(float(vin_samples[i]) - float(expected_v1)) < 1e-6
        assert abs(float(vout_samples[i]) - float(expected_vout)) < 1e-6


@pytest.mark.external
@pytest.mark.integration
def test_real_ngspice_dc_sweep_validation_b():
    """Validation B: Non-standard range and step (-5V to +5V, step 0.5V, 21 points).

    Circuit:
      V1 in 0 0
      R1 in out 1k
      R2 out 0 1k
    Expected:
      Exact 21 points
      Extrema: Vstart = -5.0 V, Vstop = +5.0 V
      Current signal I(V1) = -V1 / 2k across all points
        At V1 = -5V: I(V1) = +2.5 mA (+0.0025 A)
        At V1 = 0V:  I(V1) = 0 mA
        At V1 = +5V: I(V1) = -2.5 mA (-0.0025 A)
    """
    b = NgSpiceBackend()
    info = b.detect()
    if not info.available:
        pytest.skip("ngspice not available")

    netlist = """* DC Sweep Validation B: Symmetric range and current check
V1 in 0 0
R1 in out 1k
R2 out 0 1k
.end
"""
    sweep = DCSweepAnalysis(source="V1", start=Decimal("-5"), stop=Decimal("5"), step=Decimal("0.5"))
    res = b.simulate(netlist, analyses=(sweep,))

    assert res.status == "COMPLETED"
    assert res.exit_code == 0
    assert res.points_count == 21
    assert not res.errors

    sweep_samples = res.sweep_axis.samples
    i_samples = res.current_samples("v1")

    assert len(sweep_samples) == 21
    assert len(i_samples) == 21

    # Check extrema
    assert abs(float(sweep_samples[0]) - (-5.0)) < 1e-6
    assert abs(float(sweep_samples[-1]) - 5.0) < 1e-6

    # Check current extrema and linear relationship I(V1) = -V1 / 2000
    assert abs(float(i_samples[0]) - 0.0025) < 1e-7  # +2.5 mA at -5V
    assert abs(float(i_samples[-1]) - (-0.0025)) < 1e-7  # -2.5 mA at +5V

    for v_pt, i_pt in zip(sweep_samples, i_samples):
        expected_i = -float(v_pt) / 2000.0
        assert abs(float(i_pt) - expected_i) < 1e-7


# ==============================================================================
# 5. Full Pipeline Integration via EngineeringService
# ==============================================================================

@pytest.mark.external
@pytest.mark.integration
def test_full_pipeline_dc_sweep_via_service(tmp_path):
    repo = EngineeringRepository(Database(tmp_path / "eng.db"))
    service = EngineeringService(repo)
    service.create_project("p_sweep")

    circuit = Circuit("c_sweep")
    circuit.add(Component("V1", "V", parse_quantity("0V"), {"+": "IN", "-": "0"}))
    circuit.add(Component("R1", "R", parse_quantity("2kOhm"), {"1": "IN", "2": "OUT"}))
    circuit.add(Component("R2", "R", parse_quantity("2kOhm"), {"1": "OUT", "2": "0"}))
    service.save_circuit("p_sweep", circuit)

    backend = NgSpiceBackend()
    info = backend.detect()
    if not info.available:
        pytest.skip("ngspice not available")

    sweep = DCSweepAnalysis(source="V1", start=Decimal("0"), stop=Decimal("12"), step=Decimal("2"))
    res = service.simulate_circuit("p_sweep", "c_sweep", analyses=(sweep,), backend=backend)

    assert res.status == "COMPLETED"
    assert res.points_count == 7  # 0, 2, 4, 6, 8, 10, 12 V
    vout_samples = res.voltage_samples("out")
    assert len(vout_samples) == 7
    assert abs(float(vout_samples[0]) - 0.0) < 1e-6
    assert abs(float(vout_samples[-1]) - 6.0) < 1e-6  # 12 * 2k / 4k = 6V
