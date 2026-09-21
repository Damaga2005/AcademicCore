"""F8-O O6/O9/O10 reports, ``f8o-metrology/1`` serialisation and replay (NEW).

A :class:`MetrologyReport` is a closed, deterministic, content-addressed
view over one wrapped ``GUMResult`` plus optional traceability and Monte
Carlo validation payloads. Provenance carries no timestamp, UUID, object
address or environment fingerprint.

Digest construction (exactly as specified)::

    sha256(tag || 0x00 || canonical_json)

with canonical JSON per :mod:`o5_traceability` (sorted keys, ``Decimal``
via ``str()`` — never ``normalize()`` —, ``inf`` as ``"inf"``).

Replay states use the gate vocabulary (canonical): ``EQUIVALENT``,
``RESULT_DIFFERS``, ``VERSION_MISMATCH``, ``SCHEMA_MISMATCH``,
``INVALID_SERIALIZATION``. Aliases ``VALID == EQUIVALENT`` and
``RESULT_DIFFERENT == RESULT_DIFFERS`` cover the §23 wording of the
implementation mandate (documented, not silent).

Reuse: NEW envelope over WRAPPED ``gum.GUMResult`` (renderer, no physics
change); digests mirror the F8-N lab convention.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping

from academic_core.domain.engineering.gum import GUMResult

from academic_core.domain.engineering.metrology.errors import (
    MetrologyError,
    MetrologyStatus,
)
from academic_core.domain.engineering.metrology.o5_traceability import (
    canonical_json,
    chain_digest,
)

SCHEMA = "f8o-metrology/1"
REPORT_TAG = "f8o-report/1"
MAX_SERIALIZED_BYTES = 64 * 1024 * 1024

EQUIVALENT = "EQUIVALENT"
RESULT_DIFFERS = "RESULT_DIFFERS"
VERSION_MISMATCH = "VERSION_MISMATCH"
SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
INVALID_SERIALIZATION = "INVALID_SERIALIZATION"
# Aliases for the implementation-mandate §23 wording (explicit, tested).
VALID = EQUIVALENT
RESULT_DIFFERENT = RESULT_DIFFERS


def _clean_text(value: str, label: str) -> str:
    cleaned = value.strip() if isinstance(value, str) else ""
    if not cleaned:
        raise MetrologyError(MetrologyStatus.INVALID, f"report {label} cannot be empty")
    return cleaned


@dataclass(frozen=True)
class MetrologyReport:
    """Closed deterministic view over one GUM evaluation (validation-only post-init)."""

    measurand: str
    value: Decimal
    combined_standard_uncertainty: Decimal
    coverage_factor: Decimal
    coverage_probability: float
    expanded_uncertainty: Decimal
    effective_dof: str
    unit: str = ""
    display_value: str = ""
    display_uncertainty: str = ""
    budget_digest: str = ""
    inputs_digest: str = ""
    trace_digest: str = ""
    mc_digest: str = ""
    mc_agreement: str = ""
    seed: str = ""
    provenance: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.measurand.strip():
            raise MetrologyError(MetrologyStatus.INVALID, "report measurand cannot be empty")
        for label, item in (
            ("value", self.value),
            ("uc", self.combined_standard_uncertainty),
            ("k", self.coverage_factor),
            ("U", self.expanded_uncertainty),
        ):
            if isinstance(item, bool) or not isinstance(item, Decimal) or not item.is_finite():
                raise MetrologyError(
                    MetrologyStatus.INVALID, f"report {label} must be finite Decimal"
                )
        if self.combined_standard_uncertainty < 0 or self.expanded_uncertainty < 0:
            raise MetrologyError(MetrologyStatus.INVALID, "report uncertainties >= 0 required")
        if self.coverage_factor <= 0:
            raise MetrologyError(MetrologyStatus.INVALID, "report coverage factor k > 0 required")
        pf = self.coverage_probability
        if isinstance(pf, bool) or not isinstance(pf, (float, int)) or not (0.0 < float(pf) < 1.0):
            raise MetrologyError(MetrologyStatus.INVALID, "report coverage probability in (0, 1)")

    @staticmethod
    def from_gum_result(
        result: GUMResult,
        display_value: str = "",
        display_uncertainty: str = "",
        trace_digest: str = "",
        mc_digest: str = "",
        mc_agreement: str = "",
        seed: str = "",
        extra_provenance: Mapping[str, str] | None = None,
    ) -> "MetrologyReport":
        """Build the envelope from a wrapped ``GUMResult`` (renderer)."""
        if not isinstance(result, GUMResult):
            raise MetrologyError(MetrologyStatus.INVALID, "from_gum_result needs a GUMResult")
        budget = result.budget
        dof = budget.effective_degrees_of_freedom
        dof_text = "inf" if dof == float("inf") else str(dof)
        prov: dict[str, str] = {
            "engine": "f8o-metrology/1",
            "gum_engine": "gum/1.0",
            "coverage_factor_source": str(result.provenance.get("coverage_factor_source", "")),
            "measurand": result.measurand,
        }
        if extra_provenance:
            for key, val in extra_provenance.items():
                prov[str(key)] = str(val)
        raw_inputs = result.provenance.get("inputs", {})
        inputs_doc = {
            name: {
                "nominal": str(entry.get("nominal", "")),
                "u": str(entry.get("standard_uncertainty", "")),
                "unit": str(entry.get("unit", "")),
                "type": str(entry.get("type", "")),
                "distribution": str(entry.get("distribution", "")),
                "dof": str(entry.get("dof", "")),
            }
            for name, entry in sorted(raw_inputs.items(), key=lambda kv: kv[0])
        }
        rows_doc = [
            {
                "quantity": row.quantity,
                "c": str(row.sensitivity_coefficient),
                "method": row.sensitivity_method,
                "u": str(row.standard_uncertainty),
                "contribution": str(row.contribution),
                "variance": str(row.variance_contribution),
            }
            for row in sorted(budget.rows, key=lambda row: row.quantity)
        ]
        inputs_digest = chain_digest({"inputs": inputs_doc}, tag=REPORT_TAG)
        budget_digest = chain_digest({"rows": rows_doc}, tag=REPORT_TAG)
        ordered_prov = tuple(sorted(prov.items(), key=lambda kv: kv[0]))
        return MetrologyReport(
            measurand=result.measurand,
            value=result.measurand_value,
            combined_standard_uncertainty=result.combined_standard_uncertainty,
            coverage_factor=result.coverage_factor,
            coverage_probability=float(result.coverage_probability),
            expanded_uncertainty=result.expanded_uncertainty,
            effective_dof=dof_text,
            unit=result.measurand_unit,
            display_value=display_value,
            display_uncertainty=display_uncertainty,
            budget_digest=budget_digest,
            inputs_digest=inputs_digest,
            trace_digest=trace_digest,
            mc_digest=mc_digest,
            mc_agreement=mc_agreement,
            seed=seed,
            provenance=ordered_prov,
        )

    def _body(self) -> dict:
        """Report document without ``result_digest`` (digest input)."""
        return {
            "schema": SCHEMA,
            "measurand": self.measurand,
            "value": str(self.value),
            "combined_standard_uncertainty": str(self.combined_standard_uncertainty),
            "coverage_factor": str(self.coverage_factor),
            "coverage_probability": float(self.coverage_probability),
            "expanded_uncertainty": str(self.expanded_uncertainty),
            "effective_dof": self.effective_dof,
            "unit": self.unit,
            "display_value": self.display_value,
            "display_uncertainty": self.display_uncertainty,
            "budget_digest": self.budget_digest,
            "inputs_digest": self.inputs_digest,
            "trace_digest": self.trace_digest,
            "mc_digest": self.mc_digest,
            "mc_agreement": self.mc_agreement,
            "seed": self.seed,
            "provenance": {key: val for key, val in self.provenance},
        }

    def to_dict(self) -> dict:
        """Canonical-ordered report document (schema ``f8o-metrology/1``)."""
        doc = self._body()
        doc["result_digest"] = self.digest()
        return doc

    def digest(self) -> str:
        """Content digest over the document minus ``result_digest`` itself."""
        return chain_digest(self._body(), tag=REPORT_TAG)


def dumps(report: MetrologyReport) -> str:
    """Serialise deterministically; size-guarded (``<= 64 MiB``)."""
    if not isinstance(report, MetrologyReport):
        raise MetrologyError(MetrologyStatus.INVALID, "dumps needs a MetrologyReport")
    text = canonical_json(report.to_dict())
    if len(text.encode("utf-8")) > MAX_SERIALIZED_BYTES:
        raise MetrologyError(MetrologyStatus.INVALID, "serialised report exceeds 64 MiB")
    return text


def loads(text: str) -> MetrologyReport:
    """Parse + schema-validate + digest-verify (typed failures, no classes)."""
    if not isinstance(text, str) or not text:
        raise MetrologyError(MetrologyStatus.INVALID, "loads needs a non-empty string")
    if len(text.encode("utf-8")) > MAX_SERIALIZED_BYTES:
        raise MetrologyError(MetrologyStatus.INVALID, "serialised report exceeds 64 MiB")
    try:
        doc = json.loads(text)
    except Exception as exc:
        raise MetrologyError(MetrologyStatus.INVALID, f"bad JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise MetrologyError(MetrologyStatus.INVALID, "report document must be an object")
    known = {
        "schema", "measurand", "value", "combined_standard_uncertainty", "coverage_factor",
        "coverage_probability", "expanded_uncertainty", "effective_dof", "unit",
        "display_value", "display_uncertainty", "budget_digest", "inputs_digest",
        "trace_digest", "mc_digest", "mc_agreement", "seed", "provenance", "result_digest",
    }
    unknown = sorted(set(doc.keys()) - known)
    if unknown:
        raise MetrologyError(
            MetrologyStatus.INVALID, f"unknown report fields: {', '.join(unknown)}"
        )
    if doc.get("schema") != SCHEMA:
        raise MetrologyError(
            MetrologyStatus.INVALID, f"unsupported schema {doc.get('schema')!r}"
        )
    try:
        stated = str(doc["result_digest"])
        rebuilt = MetrologyReport(
            measurand=_clean_text(doc["measurand"], "measurand"),
            value=Decimal(str(doc["value"])),
            combined_standard_uncertainty=Decimal(str(doc["combined_standard_uncertainty"])),
            coverage_factor=Decimal(str(doc["coverage_factor"])),
            coverage_probability=float(doc["coverage_probability"]),
            expanded_uncertainty=Decimal(str(doc["expanded_uncertainty"])),
            effective_dof=str(doc["effective_dof"]),
            unit=str(doc.get("unit", "")),
            display_value=str(doc.get("display_value", "")),
            display_uncertainty=str(doc.get("display_uncertainty", "")),
            budget_digest=str(doc.get("budget_digest", "")),
            inputs_digest=str(doc.get("inputs_digest", "")),
            trace_digest=str(doc.get("trace_digest", "")),
            mc_digest=str(doc.get("mc_digest", "")),
            mc_agreement=str(doc.get("mc_agreement", "")),
            seed=str(doc.get("seed", "")),
            provenance=tuple(sorted(
                ((str(k), str(v)) for k, v in dict(doc.get("provenance", {})).items()),
                key=lambda kv: kv[0],
            )),
        )
    except MetrologyError:
        raise
    except Exception as exc:
        raise MetrologyError(MetrologyStatus.INVALID, f"bad report types: {exc}") from exc
    if rebuilt.digest() != stated:
        raise MetrologyError(MetrologyStatus.INCONSISTENT, "report digest mismatch (tampered?)")
    return rebuilt


def compare(first: str | MetrologyReport, second: str | MetrologyReport) -> str:
    """Structured comparison of two reports/documents.

    ``EQUIVALENT`` (alias ``VALID``): same digest. ``RESULT_DIFFERS``
    (alias ``RESULT_DIFFERENT``): both valid, digests differ.
    ``VERSION_MISMATCH``: schemas differ. ``SCHEMA_MISMATCH``: same schema
    family, incompatible shape. ``INVALID_SERIALIZATION``: either side
    unparsable / digest-broken.
    """
    try:
        raw_a = json.loads(first) if isinstance(first, str) else None
        raw_b = json.loads(second) if isinstance(second, str) else None
    except Exception:
        return INVALID_SERIALIZATION
    if raw_a is not None or raw_b is not None:
        try:
            schema_a = raw_a["schema"] if raw_a is not None else first.to_dict()["schema"]  # type: ignore[union-attr]
            schema_b = raw_b["schema"] if raw_b is not None else second.to_dict()["schema"]  # type: ignore[union-attr]
        except Exception:
            return INVALID_SERIALIZATION
        if schema_a != schema_b:
            family_a = str(schema_a).split("/")[0]
            family_b = str(schema_b).split("/")[0]
            if family_a != family_b:
                return SCHEMA_MISMATCH
            return VERSION_MISMATCH
    try:
        doc_a = loads(first) if isinstance(first, str) else first
        doc_b = loads(second) if isinstance(second, str) else second
    except MetrologyError:
        return INVALID_SERIALIZATION
    if not isinstance(doc_a, MetrologyReport) or not isinstance(doc_b, MetrologyReport):
        return INVALID_SERIALIZATION
    if doc_a.digest() == doc_b.digest():
        return EQUIVALENT
    return RESULT_DIFFERS
