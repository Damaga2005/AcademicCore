"""Pure grading mathematics (Phase 1).

Mirrors Gestion-Academica `calcular_resultado_componentes` semantics:
- peso_total: sum of all weights.
- peso_evaluado: weights with a score set.
- porcentaje_evaluado: evaluated/total*100, 2 decimals.
- media_ponderada: weighted mean over SCORED components ONLY (None when no
  scores yet) — never a projection over 100%. 4 decimals.
- Blocks count as one virtual component with the block's own aggregated
  score (same as original `componentes_efectivos`).
- Multi-scheme winner rule "maximo": highest media_ponderada among schemes
  with at least one score; single scheme always applies; none scored -> none.
- `final` override wins over any computation (TFG/rubric case).
- PASS_MARK = 5.0 (NOTA_MINIMA_APROBADO); evaluated only when evaluated
  weight covers total weight (raw comparison, not the rounded percentage).

DELIBERATE DIVERGENCE (§28, ADR-0011): the original uses float + Python
round() (banker's/half-even). Academic Core uses Decimal + ROUND_HALF_UP,
the standard academic rounding. Max deviation: 0.005 on porcentaje,
0.00005 on media — no pass/fail flip possible from rounding alone unless
the true value is within that epsilon of 5.0, which is reported explicitly.
Equivalence tests assert agreement within tolerance + exactness on typical
cases. No floats cross this boundary; weights/scores travel as strings.

No Qt. No SQLAlchemy. No I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

PASS_MARK = Decimal("5.0")
SCHEME_RULES = ("maximo",)


def _q2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _q4(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Scored:
    weight: Decimal
    score: Decimal | None  # None = not yet evaluated


@dataclass(frozen=True)
class Aggregate:
    peso_total: Decimal
    peso_evaluado: Decimal
    porcentaje_evaluado: Decimal  # 2dp
    media_ponderada: Decimal | None  # 4dp, None when nothing scored


def aggregate(items: list[Scored]) -> Aggregate:
    total = sum((i.weight for i in items), Decimal(0))
    scored = [i for i in items if i.score is not None]
    evaluated = sum((i.weight for i in scored), Decimal(0))
    pct = _q2(evaluated / total * 100) if total > 0 else Decimal("0.00")
    media = (_q4(sum((i.weight * i.score for i in scored), Decimal(0)) / evaluated)
             if scored and evaluated > 0 else None)
    return Aggregate(total, evaluated, pct, media)


def aggregate_block(block_weight: Decimal, members: list[Scored]) -> Scored:
    """A block contributes its weight with its own aggregated score
    (None when the block has no scores yet)."""
    inner = aggregate(members)
    return Scored(block_weight, inner.media_ponderada)


@dataclass(frozen=True)
class SchemeResult:
    name: str
    result: Aggregate
    applied: bool


def pick_winner(schemes: list[tuple[str, Aggregate]], rule: str = "maximo") -> list[SchemeResult]:
    if rule not in SCHEME_RULES:
        raise ValueError(f"rule must be one of {SCHEME_RULES}")
    if len(schemes) <= 1:
        return [SchemeResult(n, r, True) for n, r in schemes]
    scored = [(n, r) for n, r in schemes if r.media_ponderada is not None]
    winner = max(scored, key=lambda p: p[1].media_ponderada)[0] if scored else None
    return [SchemeResult(n, r, n == winner) for n, r in schemes]


@dataclass(frozen=True)
class FinalVerdict:
    grade: Decimal | None
    evaluated: bool  # True only when coverage is complete or final override
    state: str  # aprobada|suspendida|en_progreso|sin_evaluar


def final_verdict(schemes: list[tuple[str, Aggregate]], final_override: Decimal | None,
                  rule: str = "maximo") -> FinalVerdict:
    if final_override is not None:
        state = "aprobada" if final_override >= PASS_MARK else "suspendida"
        return FinalVerdict(final_override, True, state)
    picked = pick_winner(schemes, rule)
    applied = [p for p in picked if p.applied and p.result.media_ponderada is not None]
    if not applied:
        return FinalVerdict(None, False, "sin_evaluar")
    best = max(applied, key=lambda p: p.result.media_ponderada)
    r = best.result
    if r.peso_total > 0 and r.peso_evaluado >= r.peso_total:
        state = "aprobada" if r.media_ponderada >= PASS_MARK else "suspendida"
        return FinalVerdict(r.media_ponderada, True, state)
    return FinalVerdict(None, False, "en_progreso")
