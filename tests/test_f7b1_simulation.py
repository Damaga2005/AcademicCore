"""F7-B1 tests: SimulationResult + Signal + DC Operating Point.

Covers:
- Signal and SimulationResult model contracts
- Structured parser for ngspice .op output
- Decimal (domain) vs float (solver) precision separation
- Error handling, empty/malformed results
- CAS raw artifact persistence
- Determinism and provenance
- Real DC operating point simulation against ngspice 47 (ngspice_con.exe)
- Full pipeline integration: Circuit -> Netlist -> SimulationJob -> NgSpiceBackend -> Parser -> SimulationResult
"""

from decimal import Decimal
from pathlib import Path

import pytest

from academic_core.application.engineering import EngineeringService
from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.simulation import (
    MockSimulationBackend, NullSimulationBackend, Signal, SimulationJob, SimulationResult,
)
from academic_core.domain.engineering.units import parse_quantity
from academic_core.infrastructure.cas import FileBlobStore
from academic_core.infrastructure.engineering import EngineeringRepository
from academic_core.infrastructure.ngspice import NgSpiceBackend, SimulationExecution
from academic_core.infrastructure.ngspice_parser import parse_ngspice_op

SAMPLE_NGSPICE_OP_OUTPUT = """******
** ngspice-47 : Circuit level simulation program
** Compiled with KLU Direct Linear Solver
******

Batch mode

Comments and warnings go to log-file: output.log

Note: No compatibility mode selected!

Circuit: * test voltage divider

Doing analysis at TEMP = 27.000000 and TNOM = 27.000000

Using SPARSE 1.3 as Direct Linear Solver

No. of Data Rows : 1
	Node                                  Voltage
	----                                  -------
	----	-------
	out                              5.000000e+00
	in                               1.000000e+01

	Source	Current
	------	-------

	v1#branch                        -5.00000e-03

Total analysis time (seconds) = 0.000854

ngspice-47 done
"""


def _make_fake_execution(
    stdout: str = SAMPLE_NGSPICE_OP_OUTPUT,
    stderr: str = "",
    status: str = "COMPLETED",
    exit_code: int = 0,
) -> SimulationExecution:
    return SimulationExecution(
        status=status,
        backend_id="ngspice",
        backend_version="47",
        executable_path="ngspice_con.exe",
        started_at="2026-09-12T22:00:00Z",
        finished_at="2026-09-12T22:00:01Z",
        duration_seconds=1.0,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        workspace="/tmp/ws",
        command_metadata=("ngspice_con.exe", "-b", "-o", "output.log", "input.cir"),
        timeout_seconds=30.0,
        cancelled=False,
        input_hash="abc123hash",
    )


# ==============================================================================
# 1. Domain Models (Signal, SimulationResult, SimulationJob)
# ==============================================================================

def test_signal_model_precision_and_accessors():
    sig = Signal(
        name="v(out)",
        unit="V",
        axis="voltage",
        samples=(Decimal("5.000000"),),
        raw_samples=(5.0,),
    )
    assert sig.name == "v(out)"
    assert sig.unit == "V"
    assert sig.axis == "voltage"
    assert sig.value == Decimal("5.000000")
    assert sig.raw_value == 5.0
    assert isinstance(sig.value, Decimal)
    assert isinstance(sig.raw_value, float)


def test_simulation_result_accessors_and_case_insensitivity():
    sig_v = Signal("v(out)", "V", "voltage", (Decimal("3.3"),), (3.3,))
    sig_i = Signal("i(v1)", "A", "current", (Decimal("-0.01"),), (-0.01,))

    res = SimulationResult(
        backend="ngspice",
        netlist_digest="deadbeef",
        analyses=("op",),
        data={"v(out)": "3.3", "i(v1)": "-0.01"},
        signals={"v(out)": sig_v, "i(v1)": sig_i},
    )

    # Case-insensitive get_signal
    assert res.get_signal("v(out)") == sig_v
    assert res.get_signal("V(OUT)") == sig_v
    assert res.get_signal("I(V1)") == sig_i
    assert res.get_signal("nonexistent") is None

    # Helper accessors
    assert res.voltage("out") == Decimal("3.3")
    assert res.voltage("v(out)") == Decimal("3.3")
    assert res.voltage("V(OUT)") == Decimal("3.3")
    assert res.voltage("ground") is None

    assert res.current("v1") == Decimal("-0.01")
    assert res.current("i(v1)") == Decimal("-0.01")
    assert res.current("v1#branch") == Decimal("-0.01")
    assert res.current("v2") is None


def test_simulation_job_deck_building():
    base_netlist = "* Test circuit\nV1 1 0 5V\nR1 1 0 1k\n.end\n"
    job = SimulationJob(netlist=base_netlist, analyses=("op",))
    deck = job.build_netlist()

    assert ".op" in deck
    assert deck.endswith(".end\n")
    # Verify .op appears before .end
    op_pos = deck.find(".op")
    end_pos = deck.find(".end")
    assert 0 < op_pos < end_pos

    # If .op is already present, do not duplicate
    job2 = SimulationJob(netlist=deck, analyses=("op",))
    assert job2.build_netlist().count(".op") == 1


# ==============================================================================
# 2. Output Parser Unit Tests
# ==============================================================================

def test_parse_valid_ngspice_op_output():
    exec_info = _make_fake_execution()
    res = parse_ngspice_op(exec_info, netlist="V1 in 0 10\n.end")

    assert res.status == "COMPLETED"
    assert res.exit_code == 0
    assert len(res.signals) >= 3  # v(out), v(in), i(v1) / v1#branch

    # Verify voltages
    assert res.voltage("in") == Decimal("10.000000")
    assert res.voltage("out") == Decimal("5.000000")
    assert res.signals["v(out)"].unit == "V"
    assert res.signals["v(out)"].axis == "voltage"
    assert res.signals["v(out)"].raw_value == 5.0

    # Verify currents
    assert res.current("v1") == Decimal("-0.0050000") or res.current("v1") == Decimal("-5.00000e-03")
    assert res.signals["i(v1)"].unit == "A"
    assert res.signals["i(v1)"].axis == "current"
    assert res.signals["i(v1)"].raw_value == -0.005


def test_parse_output_with_errors():
    error_output = """******
** ngspice-47
******
Circuit: * bad circuit
Error: no circuits loaded.
Error: matrix is singular
"""
    exec_info = _make_fake_execution(stdout=error_output, exit_code=1, status="FAILED")
    res = parse_ngspice_op(exec_info)

    assert res.status == "FAILED"
    assert "no circuits loaded." in res.errors
    assert "matrix is singular" in res.errors
    assert len(res.signals) == 0


def test_parse_malformed_or_empty_output():
    exec_info = _make_fake_execution(stdout="some random unparseable text", exit_code=0)
    res = parse_ngspice_op(exec_info)
    # No signals extracted
    assert len(res.signals) == 0
    assert res.voltage("out") is None


def test_parse_partial_row_loss_is_not_silent_completed():
    """Regression: a table where SOME rows parse and OTHERS are silently
    dropped must not be reported as a clean, unqualified COMPLETED.

    V1 and V3 use the standard grammar and parse fine; V2 uses an
    engineering-suffix value ("1.234u") that the strict numeric parser
    rejects. Before the fix, this returned status=COMPLETED with
    signals={v(v1), v(v3)} and no indication V2 was ever dropped.
    """
    partial_loss_output = """******
** ngspice-47
******
Circuit: * partial row loss

Node Voltage
v1                               1.500000e+00
v2                               1.234u
v3                               2.500000e+00

Total analysis time (seconds) = 0.000854
"""
    exec_info = _make_fake_execution(stdout=partial_loss_output)
    res = parse_ngspice_op(exec_info)

    # The rows that DID parse must still be present -- data that succeeded
    # should not be thrown away just because a sibling row failed.
    assert res.voltage("v1") == Decimal("1.500000e+00")
    assert res.voltage("v3") == Decimal("2.500000e+00")
    assert res.voltage("v2") is None

    # But the overall result must not claim a clean, unqualified success:
    # status must not be a bare "everything is fine" COMPLETED, and the
    # dropped value must be named somewhere in errors.
    assert res.status != "COMPLETED"
    assert res.errors, "dropped row must be surfaced in errors/diagnostics"
    assert any("v2" in e for e in res.errors)


def test_parse_all_rows_valid_reports_clean_completed():
    """Sanity check: when every candidate row parses, status stays COMPLETED
    with no fabricated errors -- the partial-loss detection must not produce
    false positives on a fully successful table."""
    all_valid_output = """******
** ngspice-47
******
Circuit: * all rows valid

Node Voltage
v1                               1.500000e+00
v2                               1.700000e+00
v3                               2.500000e+00

Total analysis time (seconds) = 0.000854
"""
    exec_info = _make_fake_execution(stdout=all_valid_output)
    res = parse_ngspice_op(exec_info)

    assert res.status == "COMPLETED"
    assert res.errors == ()
    assert res.voltage("v1") == Decimal("1.500000e+00")
    assert res.voltage("v2") == Decimal("1.700000e+00")
    assert res.voltage("v3") == Decimal("2.500000e+00")


def test_parse_all_rows_corrupted_reports_failed_not_silent_completed():
    """Regression: a recognized table where EVERY candidate row is
    unparseable (e.g. all values use engineering-suffix notation) must be
    reported as FAILED, not as a bare COMPLETED with an empty signals dict
    that hides the fact rows existed but nothing could be read."""
    all_corrupt_output = """******
** ngspice-47
******
Circuit: * all rows corrupted

Node Voltage
v1                               1.234u
v2                               5.678n

Total analysis time (seconds) = 0.000854
"""
    exec_info = _make_fake_execution(stdout=all_corrupt_output)
    res = parse_ngspice_op(exec_info)

    assert res.status == "FAILED"
    assert len(res.signals) == 0
    assert res.voltage("v1") is None
    assert res.voltage("v2") is None
    assert res.errors, "candidate rows that all failed to parse must be surfaced in errors"
    assert any("v1" in e for e in res.errors)
    assert any("v2" in e for e in res.errors)


def test_parse_empty_stdout_is_sane_completed_not_crash():
    """A completely empty stdout (0 bytes) with a clean exit must not crash
    the parser and must not be misreported as a parse failure -- there are
    no candidate rows to have dropped, so this is a legitimately empty
    result, not a hidden partial/total data loss."""
    exec_info = _make_fake_execution(stdout="", stderr="")
    res = parse_ngspice_op(exec_info)

    assert res.status == "COMPLETED"
    assert res.signals == {}
    assert res.errors == ()


def test_parse_determinism():
    exec_info = _make_fake_execution()
    res1 = parse_ngspice_op(exec_info)
    res2 = parse_ngspice_op(exec_info)

    assert res1.signals == res2.signals
    assert res1.data == res2.data
    assert res1.status == res2.status
    assert res1.provenance == res2.provenance
    assert res1.raw_artifact_hash == res2.raw_artifact_hash


def test_parse_with_cas_store(tmp_path):
    cas = FileBlobStore(tmp_path / "cas")
    exec_info = _make_fake_execution()
    res = parse_ngspice_op(exec_info, cas_store=cas)

    assert res.raw_artifact_hash
    # Confirm blob exists in CAS and can be retrieved
    stored_bytes = cas.get_bytes(res.raw_artifact_hash)
    assert SAMPLE_NGSPICE_OP_OUTPUT.encode("utf-8") in stored_bytes


# ==============================================================================
# 3. Real DC Operating Point Simulation (ngspice 47 via ngspice_con.exe)
# ==============================================================================

@pytest.mark.external
@pytest.mark.integration
def test_real_ngspice_dc_operating_point_voltage_divider():
    """Scientific verification of a known voltage divider with real ngspice 47:

    Vin = 10 V, R1 = 1 kΩ, R2 = 1 kΩ
    Expected:
      V(in) = 10.0 V
      V(out) = 5.0 V
      I(V1) = -5.0 mA (-0.005 A)
    """
    b = NgSpiceBackend()
    info = b.detect()
    if not info.available:
        pytest.skip("ngspice not available")

    netlist = """* Known voltage divider test
V1 in 0 10
R1 in out 1k
R2 out 0 1k
.end
"""
    res = b.simulate(netlist, analyses=("op",))

    assert res.status == "COMPLETED"
    assert res.exit_code == 0
    assert res.backend == "ngspice"
    assert res.provenance["backend_version"] == "47"
    assert not res.errors

    v_in = res.voltage("in")
    v_out = res.voltage("out")
    i_v1 = res.current("v1")

    assert v_in is not None and abs(float(v_in) - 10.0) < 1e-6
    assert v_out is not None and abs(float(v_out) - 5.0) < 1e-6
    assert i_v1 is not None and abs(float(i_v1) - (-0.005)) < 1e-7

    # Precision separation checks
    sig_out = res.get_signal("v(out)")
    assert isinstance(sig_out.value, Decimal)
    assert isinstance(sig_out.raw_value, float)
    assert sig_out.unit == "V"
    assert sig_out.axis == "voltage"


@pytest.mark.external
@pytest.mark.integration
def test_real_ngspice_dc_single_resistor():
    """Scientific verification of Ohm's Law with real ngspice 47:

    Vin = 5 V, R1 = 2.5 kΩ
    Expected:
      V(in) = 5.0 V
      I(V1) = -2.0 mA (-0.002 A)
    """
    b = NgSpiceBackend()
    info = b.detect()
    if not info.available:
        pytest.skip("ngspice not available")

    netlist = """* Ohm's law test
V1 in 0 5
R1 in 0 2.5k
.end
"""
    res = b.simulate(netlist, analyses=("op",))

    assert res.status == "COMPLETED"
    assert res.exit_code == 0
    assert res.voltage("in") is not None and abs(float(res.voltage("in")) - 5.0) < 1e-6
    assert res.current("v1") is not None and abs(float(res.current("v1")) - (-0.002)) < 1e-7


# ==============================================================================
# 4. Full Pipeline Integration: Circuit -> Netlist -> SimulationJob -> Backend
# ==============================================================================

@pytest.mark.external
@pytest.mark.integration
def test_full_circuit_to_simulation_pipeline(tmp_path):
    from academic_core.infrastructure.database import Database
    repo = EngineeringRepository(Database(tmp_path / "eng.db"))
    service = EngineeringService(repo)
    service.create_project("test_proj")

    # Build circuit via domain API
    circuit = Circuit("div_circuit")
    circuit.add(Component("V1", "V", parse_quantity("12V"), {"+": "IN", "-": "0"}))
    circuit.add(Component("R1", "R", parse_quantity("3kOhm"), {"1": "IN", "2": "MID"}))
    circuit.add(Component("R2", "R", parse_quantity("1kOhm"), {"1": "MID", "2": "0"}))
    service.save_circuit("test_proj", circuit)

    backend = NgSpiceBackend()
    info = backend.detect()
    if not info.available:
        pytest.skip("ngspice not available")

    # Run simulation through service
    res = service.simulate_circuit("test_proj", "div_circuit", analyses=("op",), backend=backend)

    assert res.status == "COMPLETED"
    # V_mid = 12 * 1 / (3 + 1) = 3.0 V
    # V_in = 12.0 V
    # I_v1 = -12 / 4k = -0.003 A (-3 mA)
    assert res.voltage("in") is not None and abs(float(res.voltage("in")) - 12.0) < 1e-6
    assert res.voltage("mid") is not None and abs(float(res.voltage("mid")) - 3.0) < 1e-6
    assert res.current("v1") is not None and abs(float(res.current("v1")) - (-0.003)) < 1e-7


def test_service_simulate_circuit_with_mock_backend(tmp_path):
    from academic_core.infrastructure.database import Database
    repo = EngineeringRepository(Database(tmp_path / "eng.db"))
    service = EngineeringService(repo)
    service.create_project("mock_proj")

    circuit = Circuit("c1")
    circuit.add(Component("V1", "V", parse_quantity("5V"), {"+": "NET1", "-": "0"}))
    circuit.add(Component("R1", "R", parse_quantity("1kOhm"), {"1": "NET1", "2": "0"}))
    service.save_circuit("mock_proj", circuit)

    service.use_mock_backend({"v(net1)": "5.0", "i(v1)": "-0.005"})
    res = service.simulate_circuit("mock_proj", "c1", analyses=("op",))

    assert res.mocked is True
    assert res.voltage("net1") == Decimal("5.0")
    assert res.current("v1") == Decimal("-0.005")
