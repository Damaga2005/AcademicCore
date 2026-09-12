"""Generic results model (Phase 4, REWRITE — no 0–10 Float equivalent existed).

Separation: Grade (one recorded evaluation) → WeightedGrade (grade × weight
in a common 0..1 ratio space) → SubjectResult (deterministic aggregate).
- Scales: numeric(min,max) covers 0–10/0–20/0–100; letter(map) covers A–F
  style systems via explicit ratios; pass_fail covers apto/no-apto.
- Everything Decimal; invalid weights/scales/values raise; optional
  activities excluded unless scored; unscored required activities make the
  result partial (never silently projected to 100%).
- Rounding: explicit `quantize` with HALF_UP at the boundary only; internals
  keep full precision. Reproducible: same inputs → same outputs, no floats,
  no wall-clock, no iteration-order dependence (inputs sorted by key).

No Qt. No SQLite. No I/O. (ADR-0016)
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

RESULT_STATES = ("sin_evaluar", "en_progreso", "aprobada", "suspendida")


@dataclass(frozen=True)
class Scale:
    """A grading scale. `ratio(value)` maps any in-scale value to 0..1."""
    kind: str  # numeric|letter|pass_fail
    low: Decimal = Decimal(0)
    high: Decimal = Decimal(10)
    letters: tuple = ()  # ((letter, ratio_str), ...) for kind == letter

    def __post_init__(self):
        if self.kind not in ("numeric", "letter", "pass_fail"):
            raise ValueError(f"scale kind: {self.kind}")
        if self.kind == "numeric" and not self.low < self.high:
            raise ValueError("numeric scale needs low < high")
        if self.kind == "letter" and not self.letters:
            raise ValueError("letter scale needs a mapping")

    def ratio(self, value) -> Decimal:
        if self.kind == "numeric":
            v = Decimal(str(value))
            if not self.low <= v <= self.high:
                raise ValueError(f"value {v} outside [{self.low},{self.high}]")
            return (v - self.low) / (self.high - self.low) if self.high > self.low else Decimal(0)
        if self.kind == "letter":
            table = {k.upper(): Decimal(r) for k, r in self.letters}
            key = str(value).strip().upper()
            if key not in table:
                raise ValueError(f"letter {value!r} not in scale")
            return table[key]
        key = str(value).strip().lower()
        if key in ("pass", "apto", "aprobado", "1", "true"):
            return Decimal(1)
        if key in ("fail", "no apto", "suspenso", "0", "false"):
            return Decimal(0)
        raise ValueError(f"pass_fail value: {value!r}")


N_10 = Scale("numeric", Decimal(0), Decimal(10))
N_20 = Scale("numeric", Decimal(0), Decimal(20))
N_100 = Scale("numeric", Decimal(0), Decimal(100))
LETTERS_ES = Scale("letter", letters=(("MH", "1"), ("SB", "0.9"), ("NT", "0.75"),
                                      ("AP", "0.6"), ("SS", "0.25")))
PASS_FAIL = Scale("pass_fail")


@dataclass(frozen=True)
class Grade:
    key: str  # stable activity key within the subject (component/exam/…)
    value: str  # raw recorded value (Decimal text or letter token)
    scale: Scale
    weight: Decimal  # 0..100, shares of the result
    optional: bool = False
    date: str = ""
    notes: str = ""

    def __post_init__(self):
        if not self.key:
            raise ValueError("grade key required")
        if not Decimal(0) <= Decimal(self.weight) <= Decimal(100):
            raise ValueError("weight must be 0..100")
        self.scale.ratio(self.value)  # validate now, fail fast

    def ratio(self) -> Decimal:
        return self.scale.ratio(self.value)


@dataclass(frozen=True)
class SubjectResult:
    ratio: Decimal | None  # 0..1 over EVALUATED weight; None when nothing scored
    evaluated_weight: Decimal
    total_weight: Decimal
    state: str
    complete: bool  # required weight fully evaluated

    def percent(self, places: int = 2) -> Decimal | None:
        if self.ratio is None:
            return None
        q = Decimal(1).scaleb(-places)
        return (self.ratio * 100).quantize(q, rounding=ROUND_HALF_UP)


def compute(grades: list[Grade], planned_required_weight: Decimal | None = None,
              pass_ratio: Decimal = Decimal("0.5")) -> SubjectResult:
    """Deterministic aggregate, sorted by key (order-independent).

    Grade records exist only for EVALUATED activities. When the caller knows
    required weight still unevaluated, it passes `planned_required_weight`
    (the full required pie): the result is then honestly partial
    (`en_progreso`, never projected to 100%).
    """
    ordered = sorted(grades, key=lambda g: g.key)
    required = [g for g in ordered if not g.optional]
    scored = sum((Decimal(g.weight) for g in required), Decimal(0))
    total = Decimal(planned_required_weight) if planned_required_weight is not None else scored
    if total < scored:
        raise ValueError("planned weight below recorded weight")
    if not required or scored <= 0:
        return SubjectResult(None, scored, total, "sin_evaluar", total == 0)
    ratio = sum((g.ratio() * Decimal(g.weight) for g in required), Decimal(0)) / scored
    complete = scored >= total and total > 0
    state = ("aprobada" if ratio >= pass_ratio else "suspendida") if complete else "en_progreso"
    return SubjectResult(ratio, scored, total, state, complete)
