# SPDX-License-Identifier: MIT
"""F15 exercise application service (F15 §47).

load exercise -> validate input -> execute -> return result ->
translate errors. Coordinates the certified engineering library
(``EngineeringService.calculate``); no math here, no Qt. Testable
without Qt.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from academic_core.domain.engineering.units import parse_quantity
from academic_core.errors import ConfigurationError, ValidationError
from academic_core.logging_config import get_logger, log_event, new_correlation_id

logger = get_logger("academic_core.application.exercise")


@dataclass(frozen=True)
class ExerciseResult:
    key: str
    equation: str
    inputs: tuple
    text: str
    digest: str


class ExerciseService:
    def __init__(self, engineering):
        self.engineering = engineering

    def library_keys(self) -> tuple:
        return tuple(sorted(self.engineering.library()))

    def describe(self, key: str) -> dict:
        entry = self.engineering.library().get(key)
        if entry is None:
            raise ConfigurationError(f"unknown exercise: {key}")
        return {"key": key, "equation": entry.get("source", ""),
                "dimension": entry.get("dim", "")}

    def solve(self, key: str, inputs: dict[str, str],
              project: str = "", name: str = "") -> ExerciseResult:
        cid = new_correlation_id()
        entry = self.engineering.library().get(key)
        if entry is None:
            raise ConfigurationError(f"unknown exercise: {key}")
        parsed = {}
        for var, raw in inputs.items():
            try:
                parsed[var] = parse_quantity(raw)
            except ValueError as exc:
                log_event(logger, logging.WARNING, "AC-VAL-001",
                          "application.exercise", "solve",
                          f"invalid input {var} [cid={cid}]")
                raise ValidationError(f"invalid input {var}: {raw}") from exc
        log_event(logger, logging.INFO, "AC-OK-001", "application.exercise",
                  "solve", f"solve {key} [cid={cid}]")
        try:
            result = self.engineering.calculate(dict(inputs), entry["source"],
                                                project=project,
                                                circuit="", name=name or key)
        except (ValidationError, ConfigurationError):
            raise
        except ValueError as exc:
            log_event(logger, logging.ERROR, "AC-APP-001",
                      "application.exercise", "solve", f"solve failed [cid={cid}]")
            raise ValidationError(str(exc)) from exc
        return ExerciseResult(key=key, equation=entry["source"],
                              inputs=tuple(sorted(inputs.items())),
                              text=result.short(), digest=result.digest)
