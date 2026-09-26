# SPDX-License-Identifier: MIT
"""F9 deterministic correction engine (domain, pure).

Contract::

    Question (D6, validated) + Answer (F9 payload) + AnswerSpec + Config
    -> Verdict (is_correct | None, ratio, reason, normalized given)

Rules (binding, see F9-ASSESSMENT.md):

- Only the seven D6 ``qtype`` values. No invented types, no invented
  tolerances, no invented penalties, no LLM, no executed content.
- Malformed answer payloads raise ``DomainError`` (structured); only
  well-formed-but-wrong answers yield ``is_correct=False``. Open answers
  without a deterministic criterion yield ``None`` (needs review) which
  scores like omitted via the certified ``GradingPolicy``.
- Numeric: exact ``Decimal`` arithmetic over ``engineering.units``
  (conversion + dimensions). ``tolerance``/``precision`` apply exactly
  the D6 contract (XOR); precision means significant decimal digits.
- Symbolic: certified ``symbolic`` engine (``equivalent`` proof, else
  exact-``Decimal`` agreement on fixed points, honestly labeled).
- Scoring itself stays in ``assessment.GradingPolicy``; this module
  returns verdict + ratio only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from academic_core.domain import question_bank as QB
from academic_core.domain.engineering.symbolic import expr as SX
from academic_core.domain.engineering.symbolic import normal as SN
from academic_core.domain.engineering.symbolic import numeric as SNUM
from academic_core.domain.engineering.units import UnitError, parse_unit
from academic_core.domain.entities import DomainError
from academic_core.errors import ValidationError

CORRECTION_ENGINE = "f9-correct/1"

REASONS = (
    "selected_match", "selected_mismatch",
    "boolean_match", "boolean_mismatch",
    "numeric_exact", "tolerance_match", "precision_match",
    "value_mismatch", "dimension_mismatch", "unit_mismatch",
    "symbolic_equivalent", "symbolic_numeric_agreement",
    "symbolic_mismatch", "symbol_mismatch",
    "text_match", "text_mismatch", "needs_review",
    "field_ratio", "field_set_mismatch",
    "quantity_match", "quantity_mismatch", "quantity_set_mismatch",
)

_NUM_POINTS = (Decimal("0.7"), Decimal("1.3"), Decimal("2.9"))


def _dom(msg: str) -> DomainError:
    return DomainError(msg, code="AC-DOM-001")


def _decimal(text: object, what: str) -> Decimal:
    if not isinstance(text, str):
        raise _dom(f"{what} must be a decimal string")
    try:
        d = Decimal(text.strip())
    except (InvalidOperation, ValueError, AttributeError):
        raise _dom(f"{what} must be a decimal string") from None
    if not d.is_finite():
        raise _dom(f"{what} must be finite")
    return d


def _round_sig(d: Decimal, p: int) -> Decimal:
    """Round to p significant decimal digits (ROUND_HALF_UP)."""
    if d.is_zero():
        return Decimal(0)
    exp = d.adjusted() - p + 1
    return d.quantize(Decimal(1).scaleb(exp), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Verdict:
    """Correction outcome for one answered question."""

    question_id: str
    qtype: str
    is_correct: bool | None
    ratio: Decimal | None
    reason: str
    normalized: str = field(compare=False)
    engine: str = CORRECTION_ENGINE

    def __post_init__(self) -> None:
        if self.reason not in REASONS:
            raise _dom(f"bad reason: {self.reason!r}")
        if self.is_correct is None and self.ratio is not None:
            raise _dom("needs_review carries no ratio")
        if self.ratio is not None and not (
                Decimal(0) <= self.ratio <= Decimal(1)):
            raise _dom("ratio must sit in 0..1")


def _as_question(q: object) -> QB.Question:
    if isinstance(q, QB.Question):
        return q
    if isinstance(q, dict):
        try:
            bank_slug = QB.bank_slug(q.get("bank_id", "bank:x"))
        except DomainError:
            bank_slug = "x"
        return QB.question_from_dict(bank_slug, q)
    raise _dom("question must be a Question or a canonical question dict")


def _strict(answer: object, keys: set[str], qtype: str) -> dict:
    if not isinstance(answer, dict) or set(answer) != keys:
        raise _dom(f"{qtype} answer needs exactly {sorted(keys)}")
    return answer


def correct_answer(question: object, answer: object) -> Verdict:
    """Correct one answer against a validated D6 question."""
    q = _as_question(question)
    spec = q.answer_spec
    if q.qtype == "multiple_choice":
        a = _strict(answer, {"selected"}, "multiple_choice")
        sel = a["selected"]
        if (not isinstance(sel, list) or not sel
                or any(not isinstance(i, int) or isinstance(i, bool)
                       for i in sel)):
            raise _dom("selected must be a non-empty list of integers")
        if any(not 0 <= i < len(spec["options"]) for i in sel):
            raise _dom("selected index out of range")
        if len(set(sel)) != len(sel):
            raise _dom("selected indices must be unique")
        ok = set(sel) == set(spec["correct"])
        return Verdict(q.question_id, q.qtype, ok, None,
                       "selected_match" if ok else "selected_mismatch",
                       QB.dumps_canonical({"selected": sorted(sel)}))
    if q.qtype == "true_false":
        a = _strict(answer, {"answer"}, "true_false")
        if not isinstance(a["answer"], bool):
            raise _dom("answer must be bool")
        ok = a["answer"] is spec["answer"]
        return Verdict(q.question_id, q.qtype, ok, None,
                       "boolean_match" if ok else "boolean_mismatch",
                       QB.dumps_canonical({"answer": a["answer"]}))
    if q.qtype == "numeric":
        return _correct_numeric(q, _strict(
            answer, {"value", "unit"} if "unit" in answer else {"value"},
            "numeric"))
    if q.qtype == "symbolic":
        a = _strict(answer, {"expression"}, "symbolic")
        if not isinstance(a["expression"], str) or not a["expression"].strip():
            raise _dom("expression must be non-empty text")
        return _correct_symbolic(q, a["expression"].strip())
    if q.qtype == "short_text":
        a = _strict(answer, {"text"}, "short_text")
        if not isinstance(a["text"], str):
            raise _dom("text must be a string")
        return _correct_text(q, a["text"])
    if q.qtype == "structured":
        a = _strict(answer, {"fields"}, "structured")
        if not isinstance(a["fields"], dict):
            raise _dom("fields must be a dict")
        return _correct_structured(q, a["fields"])
    if q.qtype == "circuit":
        a = _strict(answer, {"quantities"}, "circuit")
        if not isinstance(a["quantities"], dict):
            raise _dom("quantities must be a dict")
        return _correct_circuit(q, a["quantities"])
    raise _dom(f"unknown qtype: {q.qtype!r}")  # pragma: no cover


def _unit_of(symbol: str, what: str):
    try:
        return parse_unit(symbol)
    except (UnitError, ValueError):
        raise _dom(f"{what} unit unresolvable: {symbol!r}") from None


def _compare_numeric(expected: str, exp_unit: str, given: str,
                     given_unit: str) -> tuple[Decimal, Decimal, str]:
    """Return (given_in_expected_unit, expected_value, unit)."""
    exp_val = _decimal(expected, "expected value")
    giv_val = _decimal(given, "given value")
    if not exp_unit and not given_unit:
        return giv_val, exp_val, ""
    if exp_unit and not given_unit:
        return giv_val, exp_val, exp_unit  # unit assumed (documented)
    if not exp_unit and given_unit:
        gu = _unit_of(given_unit, "given")
        if gu.dimension != (0,) * len(gu.dimension):
            raise _dom("unit_mismatch: dimensionless expected")
        return giv_val, exp_val, ""
    eu = _unit_of(exp_unit, "expected")
    try:
        from academic_core.domain.engineering.units import Quantity
        conv = Quantity(giv_val, _unit_of(given_unit, "given"))
        giv_eu = conv.convert_to(exp_unit).value
    except (UnitError, ValueError):
        raise _dom("dimension_mismatch: incompatible dimensions") from None
    if eu.dimension != _unit_of(given_unit, "given").dimension:
        raise _dom("dimension_mismatch: incompatible dimensions") from None
    return giv_eu, exp_val, exp_unit


def _correct_numeric(q: QB.Question, a: dict) -> Verdict:
    spec = q.answer_spec
    if "unit" in a and (not isinstance(a["unit"], str) or not a["unit"]):
        raise _dom("unit must be a non-empty string")
    try:
        giv, exp, unit = _compare_numeric(
            spec["value"], spec.get("unit", ""), a["value"],
            a.get("unit", ""))
    except DomainError as e:
        if "dimension_mismatch" in str(e) or "unit_mismatch" in str(e):
            return Verdict(q.question_id, q.qtype, False, None,
                           "dimension_mismatch"
                           if "dimension" in str(e) else "unit_mismatch",
                           QB.dumps_canonical({"value": str(a.get("value")),
                                               "unit": a.get("unit", "")}))
        raise
    norm = QB.dumps_canonical({"value": str(giv), "unit": unit})
    if giv == exp:
        return Verdict(q.question_id, q.qtype, True, None,
                       "numeric_exact", norm)
    if "tolerance" in spec:
        tol = _decimal(spec["tolerance"], "tolerance")
        if tol < 0:
            raise _dom("tolerance must be >= 0")
        if abs(giv - exp) <= tol:
            return Verdict(q.question_id, q.qtype, True, None,
                           "tolerance_match", norm)
        return Verdict(q.question_id, q.qtype, False, None,
                       "value_mismatch", norm)
    if "precision" in spec:
        p = spec["precision"]
        if _round_sig(giv, p) == _round_sig(exp, p):
            return Verdict(q.question_id, q.qtype, True, None,
                           "precision_match", norm)
        return Verdict(q.question_id, q.qtype, False, None,
                       "value_mismatch", norm)
    return Verdict(q.question_id, q.qtype, False, None,
                   "value_mismatch", norm)


def _parse_expr(source: str, what: str):
    try:
        return SX.parse(source)
    except ValidationError as e:
        raise _dom(f"{what} expression not handled by the certified engine "
                   f"(>256 chars or unsupported syntax): {e}") from None


def _correct_symbolic(q: QB.Question, given: str) -> Verdict:
    spec = q.answer_spec
    exp_e = _parse_expr(spec["expression"], "expected")
    giv_e = _parse_expr(given, "given")
    sym_e, sym_g = SNUM.symbols(exp_e), SNUM.symbols(giv_e)
    if sym_g != sym_e:
        return Verdict(q.question_id, q.qtype, False, None,
                       "symbol_mismatch",
                       QB.dumps_canonical({"expression": given}))
    declared = set(spec.get("variables", []))
    if declared and not sym_e <= declared:
        raise _dom("expected expression uses undeclared variables "
                   "(assessment build error)")
    norm = QB.dumps_canonical({"expression": given})
    if not sym_e:
        ve, vg = SX.exact_value(exp_e), SX.exact_value(giv_e)
        if ve is None or vg is None:
            raise _dom("constant expressions not decidable by the engine")
        ok = ve == vg
        return Verdict(q.question_id, q.qtype, ok, None,
                       "symbolic_equivalent" if ok else "symbolic_mismatch",
                       norm)
    if len(sym_e) == 1:
        var = next(iter(sorted(sym_e)))
        if SN.equivalent(giv_e, exp_e, var):
            return Verdict(q.question_id, q.qtype, True, None,
                           "symbolic_equivalent", norm)
        if _agree_numeric(exp_e, giv_e, sorted(sym_e)):
            return Verdict(q.question_id, q.qtype, True, None,
                           "symbolic_numeric_agreement", norm)
        return Verdict(q.question_id, q.qtype, False, None,
                       "symbolic_mismatch", norm)
    if _agree_numeric(exp_e, giv_e, sorted(sym_e)):
        return Verdict(q.question_id, q.qtype, True, None,
                       "symbolic_numeric_agreement", norm)
    return Verdict(q.question_id, q.qtype, False, None,
                   "symbolic_mismatch", norm)


def _agree_numeric(exp_e, giv_e, variables: list[str]) -> bool:
    """Exact-Decimal agreement on fixed deterministic points."""
    if len(variables) <= 2:
        if len(variables) == 1:
            points = [{variables[0]: p} for p in _NUM_POINTS]
        else:
            points = [dict(zip(variables, combo))
                      for combo in ([a, b] for a in _NUM_POINTS
                                    for b in _NUM_POINTS)]
    else:
        points = [{v: _NUM_POINTS[(i + j) % 3]
                   for j, v in enumerate(variables)} for i in range(7)]
    for env in points:
        ve, vg = SNUM.value(exp_e, env), SNUM.value(giv_e, env)
        if ve is None or vg is None:
            raise _dom("expressions not decidable on the agreement grid")
        if ve != vg:
            return False
    return True


def _correct_text(q: QB.Question, given: str) -> Verdict:
    spec = q.answer_spec
    norm_given = given.strip()
    if "expected" not in spec:
        return Verdict(q.question_id, q.qtype, None, None, "needs_review",
                       QB.dumps_canonical({"text": norm_given}))
    exp = spec["expected"].strip()
    if not spec.get("case_sensitive", False):
        ok = norm_given.lower() == exp.lower()
    else:
        ok = norm_given == exp
    return Verdict(q.question_id, q.qtype, ok, None,
                   "text_match" if ok else "text_mismatch",
                   QB.dumps_canonical({"text": norm_given}))


def _correct_structured(q: QB.Question, fields: dict) -> Verdict:
    """Shape validation + needs_review.

    The D6 structured contract carries field names+types but no expected
    values, so content scoring would be invented. Well-formed payloads
    are preserved as evidence with ``needs_review``; malformed ones raise.
    """
    schema = q.answer_spec["schema"]
    if set(fields) != set(schema):
        return Verdict(q.question_id, q.qtype, False, None,
                       "field_set_mismatch",
                       QB.dumps_canonical({"fields": sorted(fields)}))
    norm = {}
    for name in sorted(schema):
        norm[name] = _field_normalized(schema[name], fields[name])
    return Verdict(q.question_id, q.qtype, None, None, "needs_review",
                   QB.dumps_canonical({"fields": norm}))


def _field_normalized(kind: str, value: object):
    if kind == "text":
        if not isinstance(value, str):
            raise _dom("text field must be a string")
        return value.strip()
    if kind == "boolean":
        if not isinstance(value, bool):
            raise _dom("boolean field must be bool")
        return value
    if kind in ("integer", "decimal"):
        if not isinstance(value, str) or isinstance(value, bool):
            raise _dom(f"{kind} field must be a decimal string")
        d = _decimal(value, f"{kind} field")
        if kind == "integer" and d != d.to_integral_value():
            raise _dom(f"integer field not integral: {value!r}")
        return str(d)
    raise _dom(f"unknown field kind: {kind!r}")  # pragma: no cover


def _correct_circuit(q: QB.Question, quantities: dict) -> Verdict:
    """Shape validation + needs_review.

    The D6 circuit contract carries quantity names+units but no expected
    values; full verification needs a simulation run off ``netlist_ref``,
    which F9 does not perform (documented). Well-formed answers are
    preserved as evidence with ``needs_review``; malformed ones raise.
    """
    spec_qs = {e["name"]: e.get("unit", "")
               for e in q.answer_spec.get("quantities", [])}
    if set(quantities) != set(spec_qs):
        return Verdict(q.question_id, q.qtype, False, None,
                       "quantity_set_mismatch",
                       QB.dumps_canonical({"quantities": sorted(quantities)}))
    norm = {}
    for name in sorted(spec_qs):
        entry = quantities[name]
        if (not isinstance(entry, dict) or set(entry) - {"value", "unit"}
                or "value" not in entry):
            raise _dom(f"quantity {name!r} needs {{value, unit?}}")
        value = _decimal(entry["value"], f"quantity {name!r}")
        unit = entry.get("unit", "")
        if unit != "" and (not isinstance(unit, str)):
            raise _dom(f"quantity {name!r} unit must be text")
        if spec_qs[name] and unit:
            if _unit_of(unit, "given").dimension != _unit_of(
                    spec_qs[name], "expected").dimension:
                return Verdict(q.question_id, q.qtype, False, None,
                               "quantity_mismatch",
                               QB.dumps_canonical({"at": name}))
        norm[name] = {"value": str(value), "unit": unit}
    return Verdict(q.question_id, q.qtype, None, None, "needs_review",
                   QB.dumps_canonical({"quantities": norm}))
