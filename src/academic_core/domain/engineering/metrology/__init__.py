"""F8-O metrology & uncertainty layer (certified integration, no new engines).

Thin deterministic layer over certified ``gum`` (F7-B7), ``mna`` sensitivity
/ analysis (F8-M), lab value types (F8-N) and ``units``/``equations`` (F6).
Only significant-figures formatting, the traceability data model and the
report envelope are new (gate O9/O10); everything else is REUSE/WRAP/ADAPT.
"""

from academic_core.domain.engineering.metrology.errors import MetrologyError, MetrologyStatus
from academic_core.domain.engineering.metrology.o1_inputs import (
    MAX_METROLOGY_INPUTS,
    type_a,
    type_a_from_waveform,
    type_b_explicit,
    type_b_normal,
    type_b_rectangular,
    type_b_triangular,
    waveform_to_observations,
)
from academic_core.domain.engineering.metrology.o2_propagate import (
    DEFAULT_COVERAGE_PROBABILITY,
    MC_AGREEMENT_TOLERANCE,
    build_correlation,
    build_model,
    coverage_factor,
    evaluate_budget,
    sensitivity_of,
)
from academic_core.domain.engineering.metrology.o3_circuit import (
    ac_sensitivities,
    copula_marginal_stats,
    correlated_normal_samples,
    dc_sensitivities,
    mc_observable_values,
    mc_statistics,
    run_mc,
    validate_mc_vs_analytic,
)
from academic_core.domain.engineering.metrology.o4_significant import (
    display_decade,
    format_result,
    format_uncertainty,
)
from academic_core.domain.engineering.metrology.o5_traceability import (
    TRACE_TAG,
    TraceChain,
    TraceNode,
    canonical_json,
    chain_digest,
)
from academic_core.domain.engineering.metrology.report import (
    EQUIVALENT,
    INVALID_SERIALIZATION,
    MAX_SERIALIZED_BYTES,
    REPORT_TAG,
    RESULT_DIFFERENT,
    RESULT_DIFFERS,
    SCHEMA,
    SCHEMA_MISMATCH,
    VALID,
    VERSION_MISMATCH,
    MetrologyReport,
    compare,
    dumps,
    loads,
)

ENGINE_VERSION_METROLOGY = "f8o-metrology/1"

__all__ = [
    "ENGINE_VERSION_METROLOGY",
    "SCHEMA",
    "REPORT_TAG",
    "TRACE_TAG",
    "MAX_METROLOGY_INPUTS",
    "MAX_SERIALIZED_BYTES",
    "DEFAULT_COVERAGE_PROBABILITY",
    "MC_AGREEMENT_TOLERANCE",
    "MetrologyError",
    "MetrologyStatus",
    "MetrologyReport",
    "TraceChain",
    "TraceNode",
    "type_a",
    "type_a_from_waveform",
    "type_b_explicit",
    "type_b_normal",
    "type_b_rectangular",
    "type_b_triangular",
    "waveform_to_observations",
    "build_correlation",
    "build_model",
    "coverage_factor",
    "evaluate_budget",
    "sensitivity_of",
    "dc_sensitivities",
    "ac_sensitivities",
    "run_mc",
    "mc_observable_values",
    "mc_statistics",
    "validate_mc_vs_analytic",
    "correlated_normal_samples",
    "copula_marginal_stats",
    "format_result",
    "format_uncertainty",
    "display_decade",
    "canonical_json",
    "chain_digest",
    "dumps",
    "loads",
    "compare",
    "EQUIVALENT",
    "VALID",
    "RESULT_DIFFERS",
    "RESULT_DIFFERENT",
    "VERSION_MISMATCH",
    "SCHEMA_MISMATCH",
    "INVALID_SERIALIZATION",
]
