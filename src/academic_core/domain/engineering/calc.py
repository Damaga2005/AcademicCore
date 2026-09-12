"""Deterministic calculation engine (Phase 6) + equation library.

Calculation(inputs, equation) -> CalculationResult with full provenance:
inputs, units, equation source, engine version, timestamp, validation state.
Reproducible: a result hash covers inputs+equation+engine. New inputs =
new calculation, never a mutated one.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from academic_core.domain.engineering.equations import (
    ENGINE_VERSION, Equation, EquationError, evaluate, parse_equation,
)
from academic_core.domain.engineering.units import Quantity, UnitError


@dataclass(frozen=True)
class Calculation:
    inputs: dict  # name -> Quantity
    equation: Equation

    def __post_init__(self):
        missing = set(self.equation.variables) - set(self.inputs)
        if missing:
            raise EquationError(f"missing inputs: {sorted(missing)}")
        for k, v in self.inputs.items():
            if not isinstance(v, Quantity):
                raise EquationError(f"{k} is not a Quantity")


@dataclass(frozen=True)
class CalculationResult:
    name: str  # equation output name
    value: Quantity
    inputs: dict  # name -> {"value": str, "unit": str}
    equation_source: str
    engine: str
    timestamp: str
    digest: str

    def short(self) -> str:
        return f"{self.name} = {self.value.format()}"


def calculate(inputs: dict[str, Quantity], source: str,
              at: str | None = None) -> CalculationResult:
    eq = parse_equation(source) if isinstance(source, str) else source
    calc = Calculation(inputs, eq)
    value = evaluate(eq, dict(inputs))
    stamp = at or datetime.now(timezone.utc).isoformat()
    serial = json.dumps({
        "eq": eq.source, "engine": ENGINE_VERSION,
        "inputs": sorted((k, str(v.value), v.unit.display) for k, v in inputs.items()),
    }, sort_keys=True)
    digest = hashlib.sha256(serial.encode()).hexdigest()
    return CalculationResult(
        eq.output, value,
        {k: {"value": str(v.value), "unit": v.unit.display} for k, v in inputs.items()},
        eq.source, ENGINE_VERSION, stamp, digest)


# -- curated library (concepts re-derived; sources kept verbatim) ----------------
LIBRARY: dict[str, dict] = {
    "ohm-v": {"source": "V = I * R", "dim": "voltage"},
    "ohm-i": {"source": "I = V / R", "dim": "current"},
    "ohm-r": {"source": "R = V / I", "dim": "resistance"},
    "power-vi": {"source": "P = V * I", "dim": "power"},
    "power-i2r": {"source": "P = I ** 2 * R", "dim": "power"},
    "power-v2r": {"source": "P = V ** 2 / R", "dim": "power"},
    "charge-qcv": {"source": "Q = C * V", "dim": "charge"},
    "energy-cap": {"source": "E = 0.5 * C * V ** 2", "dim": "energy"},
    "energy-ind": {"source": "E = 0.5 * L * I ** 2", "dim": "energy"},
    "freq-period": {"source": "f = 1 / T", "dim": "frequency"},
    "voltage-divider": {"source": "Vout = Vi * R2 / (R1 + R2)", "dim": "voltage"},
    "pt100-cvd": {"source": "R = R0 * (1 + A * T + B * T ** 2)",
                  "dim": "resistance"},  # IEC 60751, T >= 0 C
    "ntc-beta": {"source": "R = R0 * exp(B * (1 / T - 1 / T0))",
                 "dim": "resistance"},  # T, T0 absolute (K)
    "ad620-rg": {"source": "Rg = 49.4 * kohm / (G - 1)", "dim": "resistance"},
    "wheatstone": {"source": "Vo = Vs * K * eps", "dim": "voltage"},
}

LIBRARY_DEFAULTS: dict[str, dict[str, str]] = {
    # reference inputs (with units) used by tests/docs, not hardcoded truth
    "pt100-cvd": {"R0": "100 ohm", "A": "3.9083e-3", "B": "-5.775e-7", "T": "100"},
    "ntc-beta": {"R0": "10 kohm", "B": "3950", "T": "298.15", "T0": "298.15"},
    "ad620-rg": {"G": "10"},
}
