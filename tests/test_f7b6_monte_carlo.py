"""Tests for F7-B6 Monte Carlo and Statistical Parameter Propagation.

Covers:
- Domain models: ParameterDistribution, UniformDistribution, NormalDistribution
- MonteCarloAnalysis domain model and parameter validation (N <= 0 rejected, N = 1 permitted)
- Statistical engine: sample statistics, standard deviation (Bessel's N-1 correction), percentiles
- Netlist parameter substitution without directive corruption
- RNG determinism and seed reproducibility (identical seeds yield identical samples)
- Controlled partial failures and continue_on_error policy
- Cancellation support
- CAS artifact storage and execution provenance
- Real ngspice 47 scientific validations:
  1. Resistive divider (10V, R1=1k+-5%, R2=1k+-5% -> Vout distribution around 5V)
  2. RC low-pass filter (R=1k+-5%, C=1uF+-5% -> fc distribution around 159.2 Hz)
  3. Series RLC resonant circuit (R=10+-5%, L=1mH+-5%, C=1uF+-5% -> f0 distribution around 5033 Hz)
  4. Uniform vs Normal distributions
  5. Multiple simultaneous variable parameters
  6. Controlled iteration failure capture
  7. End-to-end integration via EngineeringService and Circuit domain model
"""

from __future__ import annotations

import math
import threading
from decimal import Decimal
import pytest

from academic_core.application.engineering import EngineeringService
from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.simulation import (
    ACAnalysis,
    MockSimulationBackend,
    MonteCarloAnalysis,
    MonteCarloIteration,
    MonteCarloResult,
    NormalDistribution,
    ParameterDistribution,
    Signal,
    SimulationResult,
    UniformDistribution,
    VariableStatistics,
    compute_statistics,
    run_monte_carlo,
    substitute_netlist_parameters,
)
from academic_core.domain.engineering.units import parse_quantity
from academic_core.infrastructure.cas import FileBlobStore
from academic_core.infrastructure.database import Database
from academic_core.infrastructure.engineering import EngineeringRepository
from academic_core.infrastructure.ngspice import NgSpiceBackend


def _get_real_backend() -> NgSpiceBackend | None:
    backend = NgSpiceBackend()
    if backend.detect().verified:
        return backend
    return None


# ==============================================================================
# 1. Distribution domain model tests
# ==============================================================================

def test_uniform_distribution_nominal_and_tolerance():
    dist = UniformDistribution(nominal=Decimal("1000"), tolerance_pct=Decimal("5"))
    assert dist.nominal == Decimal("1000")
    assert dist.low == Decimal("950")
    assert dist.high == Decimal("1050")
    assert dist.validate() == []


def test_uniform_distribution_explicit_bounds():
    dist = UniformDistribution(nominal=Decimal("1000"), low=Decimal("900"), high=Decimal("1100"))
    assert dist.low == Decimal("900")
    assert dist.high == Decimal("1100")
    assert dist.validate() == []


def test_uniform_distribution_validation_errors():
    with pytest.raises(ValueError, match="low .* cannot exceed high"):
        UniformDistribution(nominal=Decimal("1000"), low=Decimal("1100"), high=Decimal("900"))

    with pytest.raises(ValueError, match="tolerance_pct must be non-negative"):
        UniformDistribution(nominal=Decimal("1000"), tolerance_pct=Decimal("-5"))


def test_normal_distribution_nominal_and_std_dev():
    dist = NormalDistribution(nominal=Decimal("100"), std_dev=Decimal("2"))
    assert dist.nominal == Decimal("100")
    assert dist.std_dev == Decimal("2")
    assert dist.validate() == []


def test_normal_distribution_tolerance_pct_and_coverage():
    dist = NormalDistribution(nominal=Decimal("1000"), tolerance_pct=Decimal("5"), sigma_coverage=Decimal("3.0"))
    assert dist.std_dev is not None
    assert abs(float(dist.std_dev) - (50.0 / 3.0)) < 1e-6


def test_normal_distribution_clamping():
    import random
    rng = random.Random(42)
    dist = NormalDistribution(
        nominal=Decimal("100"),
        std_dev=Decimal("50"),
        min_val=Decimal("90"),
        max_val=Decimal("110"),
    )
    for _ in range(50):
        val = dist.sample(rng)
        assert Decimal("90") <= val <= Decimal("110")


def test_normal_distribution_validation_errors():
    with pytest.raises(ValueError, match="std_dev must be non-negative"):
        NormalDistribution(nominal=Decimal("100"), std_dev=Decimal("-2"))

    with pytest.raises(ValueError, match="sigma_coverage must be strictly positive"):
        NormalDistribution(nominal=Decimal("100"), tolerance_pct=Decimal("5"), sigma_coverage=Decimal("0"))

    with pytest.raises(ValueError, match="min_val .* cannot exceed max_val"):
        NormalDistribution(nominal=Decimal("100"), std_dev=Decimal("2"), min_val=Decimal("150"), max_val=Decimal("50"))


# ==============================================================================
# 2. MonteCarloAnalysis validation tests
# ==============================================================================

def test_monte_carlo_analysis_valid():
    mc = MonteCarloAnalysis(
        iterations=50,
        parameters={"R1": UniformDistribution(nominal=Decimal("1000"), tolerance_pct=Decimal("5"))},
        output_variables=("v(out)",),
        seed=123,
    )
    assert mc.iterations == 50
    assert mc.seed == 123
    assert mc.output_variables == ("v(out)",)


def test_monte_carlo_analysis_n_zero_rejected():
    with pytest.raises(ValueError, match="iterations must be positive"):
        MonteCarloAnalysis(
            iterations=0,
            parameters={"R1": UniformDistribution(nominal=Decimal("1000"), tolerance_pct=Decimal("5"))},
        )


def test_monte_carlo_analysis_n_negative_rejected():
    with pytest.raises(ValueError, match="iterations must be positive"):
        MonteCarloAnalysis(
            iterations=-10,
            parameters={"R1": UniformDistribution(nominal=Decimal("1000"), tolerance_pct=Decimal("5"))},
        )


def test_monte_carlo_analysis_n_one_permitted():
    mc = MonteCarloAnalysis(
        iterations=1,
        parameters={"R1": UniformDistribution(nominal=Decimal("1000"), tolerance_pct=Decimal("5"))},
    )
    assert mc.iterations == 1


def test_monte_carlo_analysis_empty_parameters_rejected():
    with pytest.raises(ValueError, match="parameters mapping cannot be empty"):
        MonteCarloAnalysis(iterations=10, parameters={})


def test_monte_carlo_analysis_empty_output_variables_rejected():
    with pytest.raises(ValueError, match="output_variables cannot be empty"):
        MonteCarloAnalysis(
            iterations=10,
            parameters={"R1": UniformDistribution(nominal=Decimal("1000"), tolerance_pct=Decimal("5"))},
            output_variables=(),
        )


# ==============================================================================
# 3. Statistical engine tests
# ==============================================================================

def test_compute_statistics_n_one():
    val = Decimal("42.5")
    stats = compute_statistics([val], "test_var")
    assert stats.count == 1
    assert stats.mean == val
    assert stats.median == val
    assert stats.min_val == val
    assert stats.max_val == val
    assert stats.std_dev == Decimal("0")
    assert stats.variance == Decimal("0")
    assert stats.coeff_of_variation == Decimal("0")
    for p in (1, 5, 25, 50, 75, 95, 99):
        assert stats.percentiles[p] == val


def test_compute_statistics_empty_raises():
    with pytest.raises(ValueError, match="empty values sequence"):
        compute_statistics([])


def test_compute_statistics_known_dataset():
    vals = [Decimal(str(x)) for x in (10, 20, 30, 40, 50)]
    stats = compute_statistics(vals, "metric")
    assert stats.count == 5
    assert stats.mean == Decimal("30")
    assert stats.median == Decimal("30")
    assert stats.min_val == Decimal("10")
    assert stats.max_val == Decimal("50")
    assert stats.variance == Decimal("250")
    assert abs(float(stats.std_dev) - math.sqrt(250)) < 1e-6
    assert abs(float(stats.coeff_of_variation) - (math.sqrt(250) / 30.0)) < 1e-6
    assert stats.percentiles[50] == Decimal("30")
    assert stats.percentiles[1] == Decimal("10") + Decimal("0.04") * Decimal("10")


# ==============================================================================
# 4. Netlist parameter substitution tests
# ==============================================================================

def test_substitute_netlist_parameters_passive_and_sources():
    deck = """* Test Netlist
V1 in 0 dc 10 ac 1
R1 in out 1000
C1 out 0 1u
L1 n1 out 1m
.param R_val = 500
.op
.print dc v(out)
.end"""

    params = {
        "R1": Decimal("1050.5"),
        "C1": Decimal("1.05e-6"),
        "V1": Decimal("12.0"),
        "L1": Decimal("2e-3"),
        "R_val": Decimal("470"),
    }
    substituted = substitute_netlist_parameters(deck, params)
    lines = substituted.splitlines()

    assert "V1 in 0 dc 12 ac 1" in lines
    assert "R1 in out 1050.5" in lines
    assert any("C1 out 0" in l and "1.05" in l for l in lines)
    assert any("L1 n1 out" in l and "2" in l for l in lines)
    assert ".param R_val = 470" in lines
    assert ".op" in lines
    assert ".print dc v(out)" in lines
    assert ".end" in lines


# ==============================================================================
# 5. Controlled failure, cancellation, and Mock backend
# ==============================================================================

def test_controlled_partial_failure_continue_on_error():
    class PartialFailureBackend(MockSimulationBackend):
        def simulate(self, netlist: str, analyses: tuple = ("op",)):
            for line in netlist.splitlines():
                if line.startswith("R1 "):
                    val = float(line.split()[3])
                    if val > 1020:
                        raise RuntimeError(f"Convergence failure at R1={val}")
            return super().simulate(netlist, analyses)

    backend = PartialFailureBackend(payload={"v(out)": "5.0"})
    nl = "* Circuit\nV1 in 0 10\nR1 in out 1000\n.op\n.end"
    mc = MonteCarloAnalysis(
        iterations=15,
        parameters={"R1": UniformDistribution(nominal=Decimal("1000"), low=Decimal("950"), high=Decimal("1050"))},
        output_variables=("v(out)",),
        continue_on_error=True,
        seed=101,
    )
    res = run_monte_carlo(nl, mc, backend)
    assert res.status == "PARTIAL"
    assert res.iterations_failed > 0
    assert res.iterations_completed > 0
    assert len(res.iterations) == 15
    assert "v(out)" in res.statistics


def test_controlled_partial_failure_abort_on_error():
    class ImmediateFailureBackend(MockSimulationBackend):
        def __init__(self):
            super().__init__(payload={"v(out)": "5.0"})
            self.calls = 0

        def simulate(self, netlist: str, analyses: tuple = ("op",)):
            self.calls += 1
            if self.calls >= 4:
                raise RuntimeError("Unrecoverable solver error")
            return super().simulate(netlist, analyses)

    backend = ImmediateFailureBackend()
    nl = "* Circuit\nV1 in 0 10\nR1 in out 1000\n.op\n.end"
    mc = MonteCarloAnalysis(
        iterations=20,
        parameters={"R1": UniformDistribution(nominal=Decimal("1000"), tolerance_pct=Decimal("5"))},
        output_variables=("v(out)",),
        continue_on_error=False,
        seed=42,
    )
    res = run_monte_carlo(nl, mc, backend)
    assert res.status == "FAILED"
    assert res.iterations_completed == 3
    assert res.iterations_failed == 1
    assert len(res.iterations) == 4


def test_cancellation_preserves_completed_trials():
    class CancellableBackend(MockSimulationBackend):
        def __init__(self):
            super().__init__(payload={"v(out)": "5.0"})
            self._cancel_requested = threading.Event()
            self.count = 0

        def simulate(self, netlist: str, analyses: tuple = ("op",)):
            self.count += 1
            if self.count >= 5:
                self._cancel_requested.set()
            return super().simulate(netlist, analyses)

    backend = CancellableBackend()
    nl = "* Circuit\nV1 in 0 10\nR1 in out 1000\n.op\n.end"
    mc = MonteCarloAnalysis(
        iterations=25,
        parameters={"R1": UniformDistribution(nominal=Decimal("1000"), tolerance_pct=Decimal("5"))},
        output_variables=("v(out)",),
        seed=888,
    )
    res = run_monte_carlo(nl, mc, backend)
    assert res.status == "CANCELLED"
    assert res.iterations_completed == 5
    assert len(res.iterations) == 5
    assert "v(out)" in res.statistics


# ==============================================================================
# 6. Real ngspice 47 scientific tests
# ==============================================================================

@pytest.mark.skipif(_get_real_backend() is None, reason="Real ngspice runtime not available/verified")
def test_real_ngspice_case1_resistive_divider():
    backend = _get_real_backend()
    assert backend is not None

    netlist = """* F7-B6 Case 1: Resistive Divider
V1 in 0 10
R1 in out 1000
R2 out 0 1000
.op
.print dc v(out)
.end"""

    mc = MonteCarloAnalysis(
        iterations=20,
        parameters={
            "R1": UniformDistribution(nominal=Decimal("1000"), tolerance_pct=Decimal("5")),
            "R2": UniformDistribution(nominal=Decimal("1000"), tolerance_pct=Decimal("5")),
        },
        output_variables=("v(out)",),
        base_analysis="op",
        seed=12345,
    )

    res = backend.simulate(netlist, (mc,))
    assert isinstance(res, MonteCarloResult)
    assert res.status == "COMPLETED"
    assert res.iterations_requested == 20
    assert res.iterations_completed == 20
    assert res.iterations_failed == 0

    stats = res.statistics["v(out)"]
    assert Decimal("4.75") <= stats.min_val <= Decimal("5.25")
    assert Decimal("4.75") <= stats.max_val <= Decimal("5.25")
    assert abs(float(stats.mean) - 5.0) < 0.15
    assert float(stats.std_dev) > 0.05
    assert stats.percentiles[50] is not None
    assert Decimal("4.75") <= stats.percentiles[50] <= Decimal("5.25")


@pytest.mark.skipif(_get_real_backend() is None, reason="Real ngspice runtime not available/verified")
def test_real_ngspice_case2_rc_lowpass_cutoff():
    backend = _get_real_backend()
    assert backend is not None

    netlist = """* F7-B6 Case 2: RC Low-Pass Filter
V1 in 0 dc 0 ac 1
R1 in out 1000
C1 out 0 1e-6
.end"""

    ac = ACAnalysis(sweep_type="dec", points=50, fstart=10, fstop=10000)
    mc = MonteCarloAnalysis(
        iterations=15,
        parameters={
            "R1": UniformDistribution(nominal=Decimal("1000"), tolerance_pct=Decimal("5")),
            "C1": UniformDistribution(nominal=Decimal("1e-6"), tolerance_pct=Decimal("5")),
        },
        output_variables=("fc",),
        base_analysis=ac,
        seed=42,
    )

    res = backend.simulate(netlist, (mc,))
    assert isinstance(res, MonteCarloResult)
    assert res.status == "COMPLETED"
    assert res.iterations_completed == 15

    stats = res.statistics["fc"]
    assert abs(float(stats.mean) - 159.155) < 10.0
    assert 140.0 <= float(stats.min_val) <= 180.0
    assert 140.0 <= float(stats.max_val) <= 180.0
    assert float(stats.std_dev) > 1.0


@pytest.mark.skipif(_get_real_backend() is None, reason="Real ngspice runtime not available/verified")
def test_real_ngspice_case3_rlc_resonance():
    backend = _get_real_backend()
    assert backend is not None

    netlist = """* F7-B6 Case 3: Series RLC Resonant Circuit
V1 in 0 dc 0 ac 1
R1 in n1 10
L1 n1 out 1e-3
C1 out 0 1e-6
.end"""

    ac = ACAnalysis(sweep_type="lin", points=300, fstart=4500, fstop=5500)
    mc = MonteCarloAnalysis(
        iterations=15,
        parameters={
            "R1": UniformDistribution(nominal=Decimal("10"), tolerance_pct=Decimal("5")),
            "L1": UniformDistribution(nominal=Decimal("1e-3"), tolerance_pct=Decimal("5")),
            "C1": UniformDistribution(nominal=Decimal("1e-6"), tolerance_pct=Decimal("5")),
        },
        output_variables=("f0", "max_current"),
        base_analysis=ac,
        seed=999,
    )

    res = backend.simulate(netlist, (mc,))
    assert isinstance(res, MonteCarloResult)
    assert res.status == "COMPLETED"
    assert res.iterations_completed == 15

    f0_stats = res.statistics["f0"]
    assert abs(float(f0_stats.mean) - 5032.92) < 150.0
    assert 4700.0 <= float(f0_stats.min_val) <= 5350.0
    assert 4700.0 <= float(f0_stats.max_val) <= 5350.0

    i_stats = res.statistics["max_current"]
    assert abs(float(i_stats.mean) - 0.1000) < 0.01


@pytest.mark.skipif(_get_real_backend() is None, reason="Real ngspice runtime not available/verified")
def test_real_ngspice_normal_and_uniform_distributions():
    backend = _get_real_backend()
    assert backend is not None

    netlist = """* Distribution Test
V1 in 0 10
R1 in out 1000
R2 out 0 1000
.op
.print dc v(out)
.end"""

    mc_normal = MonteCarloAnalysis(
        iterations=10,
        parameters={
            "R1": NormalDistribution(nominal=Decimal("1000"), tolerance_pct=Decimal("5"), sigma_coverage=Decimal("3.0")),
            "R2": NormalDistribution(nominal=Decimal("1000"), tolerance_pct=Decimal("5"), sigma_coverage=Decimal("3.0")),
        },
        output_variables=("v(out)",),
        seed=333,
    )
    res_norm = backend.simulate(netlist, (mc_normal,))
    assert res_norm.status == "COMPLETED"
    assert float(res_norm.statistics["v(out)"].std_dev) > 0

    mc_uniform = MonteCarloAnalysis(
        iterations=10,
        parameters={
            "R1": UniformDistribution(nominal=Decimal("1000"), tolerance_pct=Decimal("5")),
            "R2": UniformDistribution(nominal=Decimal("1000"), tolerance_pct=Decimal("5")),
        },
        output_variables=("v(out)",),
        seed=333,
    )
    res_unif = backend.simulate(netlist, (mc_uniform,))
    assert res_unif.status == "COMPLETED"
    assert float(res_unif.statistics["v(out)"].std_dev) > 0


@pytest.mark.skipif(_get_real_backend() is None, reason="Real ngspice runtime not available/verified")
def test_real_ngspice_multiple_parameters():
    backend = _get_real_backend()
    assert backend is not None

    netlist = """* Multi-parameter Test
V1 in 0 12
R1 in n1 1000
R2 n1 out 500
R3 out 0 1500
.op
.print dc v(out)
.end"""

    mc = MonteCarloAnalysis(
        iterations=10,
        parameters={
            "V1": UniformDistribution(nominal=Decimal("12"), tolerance_pct=Decimal("2")),
            "R1": UniformDistribution(nominal=Decimal("1000"), tolerance_pct=Decimal("5")),
            "R2": UniformDistribution(nominal=Decimal("500"), tolerance_pct=Decimal("5")),
            "R3": UniformDistribution(nominal=Decimal("1500"), tolerance_pct=Decimal("5")),
        },
        output_variables=("v(out)",),
        seed=555,
    )
    res = backend.simulate(netlist, (mc,))
    assert res.status == "COMPLETED"
    assert res.iterations_completed == 10
    assert abs(float(res.statistics["v(out)"].mean) - 6.0) < 0.3


@pytest.mark.skipif(_get_real_backend() is None, reason="Real ngspice runtime not available/verified")
def test_real_ngspice_seed_reproducibility():
    backend = _get_real_backend()
    assert backend is not None

    netlist = """* Seed Test
V1 in 0 10
R1 in out 1000
R2 out 0 1000
.op
.print dc v(out)
.end"""

    def run_with_seed(s: int):
        mc = MonteCarloAnalysis(
            iterations=8,
            parameters={
                "R1": UniformDistribution(nominal=Decimal("1000"), tolerance_pct=Decimal("5")),
                "R2": UniformDistribution(nominal=Decimal("1000"), tolerance_pct=Decimal("5")),
            },
            output_variables=("v(out)",),
            seed=s,
        )
        return backend.simulate(netlist, (mc,))

    res1 = run_with_seed(12345)
    res2 = run_with_seed(12345)
    res3 = run_with_seed(54321)

    vals1 = [it.output_values["v(out)"] for it in res1.iterations]
    vals2 = [it.output_values["v(out)"] for it in res2.iterations]
    vals3 = [it.output_values["v(out)"] for it in res3.iterations]

    assert vals1 == vals2
    assert vals1 != vals3


@pytest.mark.skipif(_get_real_backend() is None, reason="Real ngspice runtime not available/verified")
def test_real_ngspice_controlled_failure_in_iteration():
    backend = _get_real_backend()
    assert backend is not None

    netlist = """* Controlled Failure
V1 in 0 10
R1 in out 1000
R2 out 0 1000
.op
.end"""

    def failing_extractor(res: SimulationResult, params: dict[str, Decimal]) -> Decimal:
        if params["R1"] > Decimal("1020"):
            raise ValueError("Artificial physical breakdown condition simulated")
        return res.voltage("out") or Decimal("0")

    mc = MonteCarloAnalysis(
        iterations=10,
        parameters={"R1": UniformDistribution(nominal=Decimal("1000"), low=Decimal("950"), high=Decimal("1050"))},
        output_variables=("v(out)",),
        metric_extractors={"v(out)": failing_extractor},
        continue_on_error=True,
        seed=42,
    )
    res = backend.simulate(netlist, (mc,))
    assert res.status == "PARTIAL"
    assert res.iterations_failed > 0
    assert res.iterations_completed > 0
    failed_iters = [it for it in res.iterations if it.status == "FAILED"]
    assert len(failed_iters) == res.iterations_failed
    assert "Artificial physical breakdown condition" in failed_iters[0].errors[0]


@pytest.mark.skipif(_get_real_backend() is None, reason="Real ngspice runtime not available/verified")
def test_real_ngspice_cas_and_provenance(tmp_path):
    backend = _get_real_backend()
    assert backend is not None

    cas = FileBlobStore(tmp_path / "cas")
    netlist = """* CAS Test
V1 in 0 10
R1 in out 1000
R2 out 0 1000
.op
.end"""

    mc = MonteCarloAnalysis(
        iterations=5,
        parameters={"R1": UniformDistribution(nominal=Decimal("1000"), tolerance_pct=Decimal("5"))},
        output_variables=("v(out)",),
        seed=777,
    )
    res = backend.simulate(netlist, (mc,), cas_store=cas)
    assert res.status == "COMPLETED"
    assert res.raw_artifact_hash != ""
    payload = cas.get_bytes(res.raw_artifact_hash)
    assert len(payload) > 0
    assert b"monte_carlo" in payload
    assert res.provenance["seed"] == 777
    assert res.provenance["iterations_completed"] == 5


@pytest.mark.skipif(_get_real_backend() is None, reason="Real ngspice runtime not available/verified")
def test_engineering_service_monte_carlo_end_to_end(tmp_path):
    backend = _get_real_backend()
    assert backend is not None

    repo = EngineeringRepository(Database(tmp_path / "eng.db"))
    service = EngineeringService(repo=repo)

    service.create_project("MC_PROJ")
    circuit = Circuit("VOLTAGE_DIVIDER")
    circuit.add(Component("V1", "V", parse_quantity("10 V"), {"+": "in", "-": "0"}))
    circuit.add(Component("R1", "R", parse_quantity("1 kOhm"), {"1": "in", "2": "out"}))
    circuit.add(Component("R2", "R", parse_quantity("1 kOhm"), {"1": "out", "2": "0"}))
    service.save_circuit("MC_PROJ", circuit)

    mc = MonteCarloAnalysis(
        iterations=8,
        parameters={
            "R1": UniformDistribution(nominal=Decimal("1000"), tolerance_pct=Decimal("5")),
            "R2": UniformDistribution(nominal=Decimal("1000"), tolerance_pct=Decimal("5")),
        },
        output_variables=("v(out)",),
        seed=111,
    )

    res = service.simulate_circuit("MC_PROJ", "VOLTAGE_DIVIDER", (mc,), backend=backend)
    assert isinstance(res, MonteCarloResult)
    assert res.status == "COMPLETED"
    assert res.iterations_completed == 8
    assert abs(float(res.statistics["v(out)"].mean) - 5.0) < 0.15
