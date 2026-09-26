# SPDX-License-Identifier: MIT
"""D6 neutral versioned question-bank contract (domain, pure).

Neutral, versioned, deterministic and extensible representation of
question banks, independent of any concrete subject. D6 covers
**data + contract + validation + versioning** only:

```text
D6 -> question bank (this module)
D7 -> ingestion -> Knowledge Core (not here)
F9 -> assessment / attempts / correction (not here)
```

Design notes (binding):

- Pure domain: stdlib + ``entities.DomainError`` + ``identity.slugify``.
  No Qt, no SQL, no network, no clock, no filesystem (see D5/arch gates).
- ``schema_version`` is the contract version (``1``); ``content_version``
  is the bank content revision (``>= 1``). Unknown ``schema_version``
  is rejected with ``AC-VER-001``; nothing is silently migrated.
- Canonical form mirrors the certified precedent
  (``lab/serialize.canonical`` + ``dumps_canonical`` + ``digest``):
  sorted dict keys, order-preserving lists, ``Decimal`` as ``str``,
  ``float`` always rejected, ``sha256(tag + 0x00 + canonical)``.
- Strict core + explicit extensions: unknown fields are rejected
  (``AC-SER-001``); extensions live under ``x-``-prefixed keys only.
- Formulas/expressions are inert data, never executed (``AC-SEC-001``
  boundary; AST-audited like the F13-ext/D4 contract).
- Numeric values travel as decimal *strings* (zero-float policy);
  the strings are preserved verbatim so the digest changes if and only
  if the semantic content changes. Numeric *equivalence* is F9's job.
- ``unit`` symbols are validated structurally here; semantic resolution
  via ``engineering.units.parse_unit`` is D7/F9's contract (cross-checked
  in tests, no domain->engineering import to keep this layer decoupled).
- D6 needs no persistence: banks travel as canonical JSON envelopes.
  No migration, no parallel store (see D6-QUESTION-BANK.md section 18).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from academic_core.domain.entities import DomainError
from academic_core.domain.identity import slugify

SCHEMA_TAG = "d6-question-bank/1"
SCHEMA_VERSION = 1

QUESTION_TYPES = (
    "multiple_choice",
    "true_false",
    "numeric",
    "symbolic",
    "short_text",
    "structured",
    "circuit",
)

DIFFICULTIES = ("easy", "medium", "hard", "unspecified")

KNOWLEDGE_REF_KINDS = ("concept", "formula", "section", "document", "topic")

STRUCTURED_FIELD_TYPES = ("text", "integer", "decimal", "boolean")

MAX_BANK_BYTES = 1024 * 1024
MAX_QUESTIONS = 1000
MAX_DEPTH = 6
MAX_STATEMENT_LEN = 8000
MAX_OPTIONS = 12
MAX_OPTION_LEN = 2000
MAX_TAGS = 16
MAX_EXPRESSION_LEN = 4000
MAX_NETLIST_REF_LEN = 2000
MAX_EXTENSIONS = 32

_BANK_RE = re.compile(r"^bank:[a-z0-9]+(?:-[a-z0-9]+)*$")
_QUESTION_RE = re.compile(
    r"^question:([a-z0-9]+(?:-[a-z0-9]+)*):q:(\d{5})$"
)
_TAG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_IDENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_LANG_RE = re.compile(r"^[a-z]{2,3}(?:-[A-Z]{2})?$")
_EXT_KEY_RE = re.compile(r"^x-[a-z0-9]+(?:-[a-z0-9]+)*$")
_DECIMAL_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_UNIT_RE = re.compile(
    "^[A-Za-z0-9 \u03a9\u00b5\u00b0/%^*.\u00b7\\-+]{1,32}$"
)
_REF_RE = re.compile(r"^[A-Za-z0-9:_.#/\-]{1,256}$")

_PROVENANCE_KEYS = (
    "source",
    "version",
    "stable_id",
    "resource_id",
    "content_hash",
    "adapter",
    "adapter_version",
)

_BANK_KEYS = (
    "bank_id",
    "title",
    "content_version",
    "questions",
    "description",
    "language",
    "domain",
    "extensions",
    "provenance",
)

_QUESTION_KEYS = (
    "question_id",
    "statement",
    "qtype",
    "answer_spec",
    "knowledge_refs",
    "concepts",
    "formulas",
    "unit",
    "difficulty",
    "estimated_time_s",
    "tags",
    "language",
    "provenance",
    "extensions",
)

_ENVELOPE_KEYS = ("bank", "integrity", "schema", "schema_version")


def _dom(msg: str) -> DomainError:
    return DomainError(msg, code="AC-DOM-001")


def _ser(msg: str) -> DomainError:
    return DomainError(msg, code="AC-SER-001")


def _ver(msg: str) -> DomainError:
    return DomainError(msg, code="AC-VER-001")


def _sec(msg: str) -> DomainError:
    return DomainError(msg, code="AC-SEC-001")


def bank_slug(bank_id: str) -> str:
    """Return the slug part of a validated ``bank:<slug>`` id."""
    if not isinstance(bank_id, str) or not _BANK_RE.match(bank_id):
        raise _dom(f"bad bank_id: {bank_id!r}")
    return bank_id.split(":", 1)[1]


def make_bank_id(name: str) -> str:
    """Mint a stable neutral bank id from a human name (deterministic)."""
    return f"bank:{slugify(name)}"


def make_question_id(bank_id: str, n: int) -> str:
    """Mint ``question:<slug>:q:NNNNN`` for the owning bank."""
    slug = bank_slug(bank_id)
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= 99999:
        raise _dom(f"bad question number: {n!r}")
    return f"question:{slug}:q:{n:05d}"


def _check_question_id(qid: str, owner_slug: str) -> str:
    if not isinstance(qid, str):
        raise _dom(f"bad question_id: {qid!r}")
    m = _QUESTION_RE.match(qid)
    if not m:
        raise _dom(f"bad question_id: {qid!r}")
    if m.group(1) != owner_slug:
        raise _dom(f"question {qid!r} does not belong to bank {owner_slug!r}")
    return qid


def _req_str(d: dict, key: str, lo: int, hi: int) -> str:
    v = d.get(key)
    if not isinstance(v, str) or not lo <= len(v.strip()) <= hi:
        raise _dom(f"{key} must be text with {lo}..{hi} chars")
    return v


def _opt_str(d: dict, key: str, hi: int) -> str:
    v = d.get(key, "")
    if not isinstance(v, str) or len(v) > hi:
        raise _dom(f"{key} must be text with at most {hi} chars")
    return v


def _check_decimal_text(v: object, key: str) -> str:
    if not isinstance(v, str) or not _DECIMAL_RE.match(v.strip()):
        raise _dom(f"{key} must be a decimal string")
    try:
        d = Decimal(v.strip())
    except (InvalidOperation, ValueError):
        raise _dom(f"{key} must be a decimal string") from None
    if not d.is_finite():
        raise _dom(f"{key} must be finite")
    return v.strip()


def _check_unit(v: object, key: str) -> str:
    if not isinstance(v, str) or not _UNIT_RE.match(v):
        raise _dom(
            f"{key} must be a unit symbol (1..32 chars, "
            "structural check; D7/F9 resolve via parse_unit)"
        )
    return v


def _check_provenance(v: object) -> dict:
    if not isinstance(v, dict):
        raise _dom("provenance must be a dict")
    for k, val in v.items():
        if k not in _PROVENANCE_KEYS:
            raise _dom(f"unknown provenance key: {k!r}")
        if not isinstance(val, str) or not val.strip():
            raise _dom(f"provenance[{k}] must be non-empty text")
    ch = v.get("content_hash")
    if ch is not None and not _HEX64_RE.match(ch):
        raise _dom("provenance content_hash must be sha256 hex")
    return dict(v)


def _check_json_value(v: object, depth: int, where: str) -> None:
    if depth > MAX_DEPTH:
        raise _sec(f"{where}: structure too deep")
    if v is None or isinstance(v, (bool, int, str)):
        if isinstance(v, float):  # pragma: no cover - bool/int guard above
            raise _dom(f"{where}: float not allowed")
        return
    if isinstance(v, float):
        raise _dom(f"{where}: float not allowed (decimal strings only)")
    if isinstance(v, (Decimal, bytes, set, frozenset)):
        raise _ser(f"{where}: unsupported value type")
    if isinstance(v, (list, tuple)):
        for i, item in enumerate(v):
            _check_json_value(item, depth + 1, f"{where}[{i}]")
        return
    if isinstance(v, dict):
        for k, item in v.items():
            if not isinstance(k, str):
                raise _ser(f"{where}: keys must be strings")
            _check_json_value(item, depth + 1, f"{where}.{k}")
        return
    raise _ser(f"{where}: unsupported value type {type(v).__name__}")


def _check_extensions(v: object) -> dict:
    if not isinstance(v, dict):
        raise _dom("extensions must be a dict")
    if len(v) > MAX_EXTENSIONS:
        raise _dom(f"extensions limited to {MAX_EXTENSIONS} entries")
    for k, val in v.items():
        if not isinstance(k, str) or not _EXT_KEY_RE.match(k):
            raise _dom(
                f"extension keys must match x-<slug>, got {k!r}"
            )
        _check_json_value(val, 0, f"extensions[{k}]")
    return {k: _plain(v[k]) for k in sorted(v)}


def _plain(v: object) -> object:
    if isinstance(v, dict):
        return {k: _plain(v[k]) for k in sorted(v)}
    if isinstance(v, (list, tuple)):
        return [_plain(i) for i in v]
    return v


def _check_tags(v: object) -> tuple:
    if not isinstance(v, (list, tuple)):
        raise _dom("tags must be a list")
    if len(v) > MAX_TAGS:
        raise _dom(f"tags limited to {MAX_TAGS}")
    seen: set[str] = set()
    for t in v:
        if not isinstance(t, str) or not _TAG_RE.match(t):
            raise _dom(f"bad tag: {t!r}")
        if t in seen:
            raise _dom(f"duplicate tag: {t!r}")
        seen.add(t)
    return tuple(v)


def _check_refs(v: object, key: str) -> tuple:
    if not isinstance(v, (list, tuple)):
        raise _dom(f"{key} must be a list")
    out = []
    for r in v:
        if not isinstance(r, str) or not _REF_RE.match(r):
            raise _dom(f"bad {key} entry: {r!r}")
        out.append(r)
    return tuple(out)


def _check_knowledge_refs(v: object) -> tuple:
    if not isinstance(v, (list, tuple)):
        raise _dom("knowledge_refs must be a list")
    if len(v) > 64:
        raise _dom("knowledge_refs limited to 64 entries")
    out = []
    for e in v:
        if not isinstance(e, dict) or set(e) != {"kind", "ref"}:
            raise _dom("knowledge_refs entries need {kind, ref}")
        if e["kind"] not in KNOWLEDGE_REF_KINDS:
            raise _dom(f"bad knowledge_ref kind: {e['kind']!r}")
        if not isinstance(e["ref"], str) or not _REF_RE.match(e["ref"]):
            raise _dom(f"bad knowledge_ref ref: {e['ref']!r}")
        out.append({"kind": e["kind"], "ref": e["ref"]})
    return tuple(out)


def _check_language(v: object) -> str:
    if not isinstance(v, str):
        raise _dom("language must be text")
    if v == "":
        return ""
    if not _LANG_RE.match(v):
        raise _dom(f"bad language: {v!r}")
    return v


def _check_answer_spec(qtype: str, spec: object) -> dict:
    if not isinstance(spec, dict):
        raise _dom("answer_spec must be a dict")
    if qtype == "multiple_choice":
        if set(spec) != {"options", "correct"}:
            raise _dom("multiple_choice needs {options, correct}")
        opts = spec["options"]
        if (
            not isinstance(opts, list)
            or not 2 <= len(opts) <= MAX_OPTIONS
        ):
            raise _dom("options needs 2..12 entries")
        for o in opts:
            if not isinstance(o, str) or not 1 <= len(o.strip()) <= MAX_OPTION_LEN:
                raise _dom("each option must be 1..2000 chars")
        if len({o.strip() for o in opts}) != len(opts):
            raise _dom("options must be unique")
        correct = spec["correct"]
        if not isinstance(correct, list) or not 1 <= len(correct) <= len(opts):
            raise _dom("correct needs 1..len(options) indices")
        for c in correct:
            if not isinstance(c, int) or isinstance(c, bool):
                raise _dom("correct indices must be integers")
            if not 0 <= c < len(opts):
                raise _dom(f"correct index out of range: {c!r}")
        if len(set(correct)) != len(correct):
            raise _dom("correct indices must be unique")
        return {"options": [o for o in opts], "correct": [c for c in correct]}
    if qtype == "true_false":
        if set(spec) != {"answer"} or not isinstance(spec["answer"], bool):
            raise _dom("true_false needs {answer: bool}")
        return {"answer": spec["answer"]}
    if qtype == "numeric":
        allowed = {"value", "unit", "tolerance", "precision"}
        if not set(spec) <= allowed or "value" not in spec:
            raise _dom("numeric needs value + optional unit/tolerance/precision")
        out: dict = {"value": _check_decimal_text(spec["value"], "value")}
        if "unit" in spec:
            out["unit"] = _check_unit(spec["unit"], "unit")
        has_tol = "tolerance" in spec
        has_prec = "precision" in spec
        if has_tol and has_prec:
            raise _dom("numeric accepts tolerance XOR precision, not both")
        if has_tol:
            t = _check_decimal_text(spec["tolerance"], "tolerance")
            if Decimal(t) < 0:
                raise _dom("tolerance must be >= 0")
            out["tolerance"] = t
        if has_prec:
            p = spec["precision"]
            if not isinstance(p, int) or isinstance(p, bool) or not 1 <= p <= 28:
                raise _dom("precision must be an integer 1..28")
            out["precision"] = p
        return out
    if qtype == "symbolic":
        if not set(spec) <= {"expression", "variables"} or "expression" not in spec:
            raise _dom("symbolic needs expression + optional variables")
        expr = spec["expression"]
        if not isinstance(expr, str) or not 1 <= len(expr.strip()) <= MAX_EXPRESSION_LEN:
            raise _dom("expression must be 1..4000 chars")
        out = {"expression": expr}
        if "variables" in spec:
            vs = spec["variables"]
            if not isinstance(vs, list) or len(vs) > 32:
                raise _dom("variables limited to 32 identifiers")
            for name in vs:
                if not isinstance(name, str) or not _IDENT_RE.match(name):
                    raise _dom(f"bad variable: {name!r}")
            out["variables"] = list(vs)
        return out
    if qtype == "short_text":
        if not set(spec) <= {"expected", "max_length", "case_sensitive"}:
            raise _dom("short_text allows {expected, max_length, case_sensitive}")
        out = {}
        if "expected" in spec:
            e = spec["expected"]
            if not isinstance(e, str) or not 1 <= len(e.strip()) <= MAX_OPTION_LEN:
                raise _dom("expected must be 1..2000 chars")
            out["expected"] = e
        if "max_length" in spec:
            m = spec["max_length"]
            if not isinstance(m, int) or isinstance(m, bool) or not 1 <= m <= 8000:
                raise _dom("max_length must be an integer 1..8000")
            out["max_length"] = m
        cs = spec.get("case_sensitive", False)
        if not isinstance(cs, bool):
            raise _dom("case_sensitive must be bool")
        out["case_sensitive"] = cs
        return out
    if qtype == "structured":
        if set(spec) != {"schema"} or not isinstance(spec["schema"], dict):
            raise _dom("structured needs {schema: {...}}")
        sch = spec["schema"]
        if not 1 <= len(sch) <= 32:
            raise _dom("structured schema needs 1..32 fields")
        for k, t in sch.items():
            if not isinstance(k, str) or not _IDENT_RE.match(k):
                raise _dom(f"bad structured field: {k!r}")
            if t not in STRUCTURED_FIELD_TYPES:
                raise _dom(f"bad structured field type: {t!r}")
        return {"schema": {k: sch[k] for k in sorted(sch)}}
    if qtype == "circuit":
        if not set(spec) <= {"netlist_ref", "quantities"} or "netlist_ref" not in spec:
            raise _dom("circuit needs netlist_ref + optional quantities")
        ref = spec["netlist_ref"]
        if not isinstance(ref, str) or not 1 <= len(ref.strip()) <= MAX_NETLIST_REF_LEN:
            raise _dom("netlist_ref must be 1..2000 chars")
        out = {"netlist_ref": ref}
        if "quantities" in spec:
            qs = spec["quantities"]
            if not isinstance(qs, list) or len(qs) > 32:
                raise _dom("quantities limited to 32 entries")
            norm = []
            for q in qs:
                if not isinstance(q, dict) or not set(q) <= {"name", "unit"}:
                    raise _dom("quantity needs {name, unit?}")
                if not isinstance(q.get("name"), str) or not _IDENT_RE.match(q["name"]):
                    raise _dom(f"bad quantity name: {q.get('name')!r}")
                nq: dict = {"name": q["name"]}
                if "unit" in q:
                    nq["unit"] = _check_unit(q["unit"], "unit")
                norm.append(nq)
            out["quantities"] = norm
        return out
    raise _dom(f"unknown qtype: {qtype!r}")  # pragma: no cover


@dataclass(frozen=True)
class Question:
    """One neutral question. The owner-bank slug is part of the id."""

    question_id: str
    statement: str
    qtype: str
    answer_spec: dict = field(compare=False)
    knowledge_refs: tuple = ()
    concepts: tuple = ()
    formulas: tuple = ()
    unit: str = ""
    difficulty: str = "unspecified"
    estimated_time_s: int | None = None
    tags: tuple = ()
    language: str = ""
    provenance: dict = field(default_factory=dict, compare=False)
    extensions: dict = field(default_factory=dict, compare=False)
    owner_slug: str = field(default="", compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.owner_slug, str) or not self.owner_slug:
            raise _dom("owner_slug is required (bank slug)")
        _check_question_id(self.question_id, self.owner_slug)
        if not isinstance(self.statement, str) or not (
            1 <= len(self.statement.strip()) <= MAX_STATEMENT_LEN
        ):
            raise _dom("statement must be 1..8000 chars")
        if self.qtype not in QUESTION_TYPES:
            raise _dom(f"unknown qtype: {self.qtype!r}")
        clean = _check_answer_spec(self.qtype, self.answer_spec)
        object.__setattr__(self, "answer_spec", clean)
        object.__setattr__(
            self, "knowledge_refs", _check_knowledge_refs(self.knowledge_refs)
        )
        object.__setattr__(self, "concepts", _check_refs(self.concepts, "concepts"))
        object.__setattr__(self, "formulas", _check_refs(self.formulas, "formulas"))
        if self.unit != "":
            _check_unit(self.unit, "unit")
        if self.difficulty not in DIFFICULTIES:
            raise _dom(f"bad difficulty: {self.difficulty!r}")
        if self.estimated_time_s is not None:
            e = self.estimated_time_s
            if not isinstance(e, int) or isinstance(e, bool) or not 1 <= e <= 86400:
                raise _dom("estimated_time_s must be an integer 1..86400")
        object.__setattr__(self, "tags", _check_tags(self.tags))
        _check_language(self.language)
        object.__setattr__(self, "provenance", _check_provenance(self.provenance))
        object.__setattr__(self, "extensions", _check_extensions(self.extensions))


@dataclass(frozen=True)
class Bank:
    """Neutral question bank container (no subject scope)."""

    bank_id: str
    title: str
    content_version: int
    questions: tuple = ()
    description: str = ""
    language: str = ""
    domain: str = ""
    extensions: dict = field(default_factory=dict, compare=False)
    provenance: dict = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        slug = bank_slug(self.bank_id)
        if not isinstance(self.title, str) or not 1 <= len(self.title.strip()) <= 400:
            raise _dom("title must be 1..400 chars")
        if (
            not isinstance(self.content_version, int)
            or isinstance(self.content_version, bool)
            or self.content_version < 1
        ):
            raise _dom("content_version must be an integer >= 1")
        if not isinstance(self.questions, (list, tuple)):
            raise _dom("questions must be a list")
        if len(self.questions) > MAX_QUESTIONS:
            raise _dom(f"questions limited to {MAX_QUESTIONS}")
        seen: set[str] = set()
        owned = []
        for q in self.questions:
            if not isinstance(q, Question):
                raise _dom("questions must hold Question items")
            if q.owner_slug != slug:
                raise _dom(f"question {q.question_id!r} not owned by {self.bank_id!r}")
            if q.question_id in seen:
                raise _dom(f"duplicate question_id: {q.question_id!r}")
            seen.add(q.question_id)
            owned.append(q)
        object.__setattr__(self, "questions", tuple(owned))
        if not isinstance(self.description, str) or len(self.description) > 2000:
            raise _dom("description limited to 2000 chars")
        _check_language(self.language)
        if not isinstance(self.domain, str) or len(self.domain) > 120:
            raise _dom("domain limited to 120 chars")
        object.__setattr__(self, "extensions", _check_extensions(self.extensions))
        object.__setattr__(self, "provenance", _check_provenance(self.provenance))


def question_to_dict(q: Question) -> dict:
    """Lossless plain-dict view (tuples become lists)."""
    return {
        "question_id": q.question_id,
        "statement": q.statement,
        "qtype": q.qtype,
        "answer_spec": _plain(q.answer_spec),
        "knowledge_refs": [dict(e) for e in q.knowledge_refs],
        "concepts": list(q.concepts),
        "formulas": list(q.formulas),
        "unit": q.unit,
        "difficulty": q.difficulty,
        "estimated_time_s": q.estimated_time_s,
        "tags": list(q.tags),
        "language": q.language,
        "provenance": dict(q.provenance),
        "extensions": _plain(q.extensions),
    }


def bank_to_dict(bank: Bank) -> dict:
    """Lossless plain-dict view of the semantic content (no digest)."""
    return {
        "bank_id": bank.bank_id,
        "title": bank.title,
        "content_version": bank.content_version,
        "questions": [question_to_dict(q) for q in bank.questions],
        "description": bank.description,
        "language": bank.language,
        "domain": bank.domain,
        "extensions": _plain(bank.extensions),
        "provenance": dict(bank.provenance),
    }


def question_from_dict(owner_slug: str, d: dict) -> Question:
    """Validate a raw question mapping (strict keys) into a Question."""
    if not isinstance(d, dict):
        raise _ser("question must be a dict")
    unknown = set(d) - set(_QUESTION_KEYS)
    if unknown:
        raise _ser(f"unknown question fields: {sorted(unknown)}")
    for k in ("question_id", "statement", "qtype", "answer_spec"):
        if k not in d:
            raise _ser(f"question missing {k}")
    return Question(
        question_id=d["question_id"],
        statement=d["statement"],
        qtype=d["qtype"],
        answer_spec=d["answer_spec"],
        knowledge_refs=d.get("knowledge_refs", []),
        concepts=d.get("concepts", []),
        formulas=d.get("formulas", []),
        unit=d.get("unit", ""),
        difficulty=d.get("difficulty", "unspecified"),
        estimated_time_s=d.get("estimated_time_s"),
        tags=d.get("tags", []),
        language=d.get("language", ""),
        provenance=d.get("provenance", {}),
        extensions=d.get("extensions", {}),
        owner_slug=owner_slug,
    )


def bank_from_dict(d: dict) -> Bank:
    """Validate a raw bank-content mapping (strict keys) into a Bank."""
    if not isinstance(d, dict):
        raise _ser("bank must be a dict")
    unknown = set(d) - set(_BANK_KEYS)
    if unknown:
        raise _ser(f"unknown bank fields: {sorted(unknown)}")
    for k in ("bank_id", "title", "content_version", "questions"):
        if k not in d:
            raise _ser(f"bank missing {k}")
    slug = bank_slug(d["bank_id"])
    raw_qs = d["questions"]
    if not isinstance(raw_qs, list):
        raise _ser("questions must be a list")
    return Bank(
        bank_id=d["bank_id"],
        title=d["title"],
        content_version=d["content_version"],
        questions=tuple(question_from_dict(slug, q) for q in raw_qs),
        description=d.get("description", ""),
        language=d.get("language", ""),
        domain=d.get("domain", ""),
        extensions=d.get("extensions", {}),
        provenance=d.get("provenance", {}),
    )


def _canonical(node: object, depth: int = 0) -> object:
    if depth > MAX_DEPTH:
        raise _sec("structure too deep for canonical form")
    if node is None or isinstance(node, (bool, int, str)):
        if isinstance(node, bool):
            return node
        if isinstance(node, int):
            return node
        return node
    if isinstance(node, float):
        raise _dom("float not allowed in canonical form (decimal strings only)")
    if isinstance(node, Decimal):
        return str(node)
    if isinstance(node, (list, tuple)):
        return [_canonical(v, depth + 1) for v in node]
    if isinstance(node, dict):
        for k in node:
            if not isinstance(k, str):
                raise _ser("canonical keys must be strings")
        return {k: _canonical(node[k], depth + 1) for k in sorted(node)}
    raise _ser(f"unsupported value type: {type(node).__name__}")


def dumps_canonical(obj: object) -> str:
    """Stable JSON: sorted keys, compact separators, ASCII, no NaN."""
    return json.dumps(
        _canonical(obj),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def bank_digest(bank: Bank) -> str:
    """Reproducible digest of the semantic content (no timestamps/paths)."""
    raw = dumps_canonical(bank_to_dict(bank)).encode("utf-8")
    return hashlib.sha256(SCHEMA_TAG.encode("utf-8") + b"\x00" + raw).hexdigest()


def dumps_bank(bank: Bank) -> str:
    """Serialize a bank into its canonical envelope (with integrity digest)."""
    content = bank_to_dict(bank)
    envelope = {
        "bank": content,
        "integrity": {"digest": bank_digest(bank), "schema": SCHEMA_TAG},
        "schema": SCHEMA_TAG,
        "schema_version": SCHEMA_VERSION,
    }
    raw = dumps_canonical(envelope)
    if len(raw.encode("utf-8")) > MAX_BANK_BYTES:
        raise _sec(f"bank exceeds {MAX_BANK_BYTES} bytes")
    return raw


def _no_dupes(pairs: list) -> dict:
    out: dict = {}
    for k, v in pairs:
        if k in out:
            raise _ser(f"duplicate key: {k!r}")
        out[k] = v
    return out


def _reject_const(name: str) -> None:
    raise _ser(f"non-finite constant rejected: {name}")


def parse_bank(data: object) -> Bank:
    """Parse and fully validate an envelope (dict or JSON text/bytes)."""
    if isinstance(data, (str, bytes)):
        raw = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        if len(raw) > MAX_BANK_BYTES:
            raise _sec(f"bank exceeds {MAX_BANK_BYTES} bytes")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise _ser("bank is not valid UTF-8") from None
        try:
            data = json.loads(
                text,
                object_pairs_hook=_no_dupes,
                parse_constant=_reject_const,
            )
        except json.JSONDecodeError as e:
            raise _ser(f"bank is not valid JSON: {e}") from None
    if not isinstance(data, dict):
        raise _ser("bank envelope must be a dict")
    unknown = set(data) - set(_ENVELOPE_KEYS)
    if unknown:
        raise _ser(f"unknown envelope fields: {sorted(unknown)}")
    for k in _ENVELOPE_KEYS:
        if k not in data:
            raise _ser(f"envelope missing {k}")
    if data["schema"] != SCHEMA_TAG:
        raise _ser(f"unknown schema: {data['schema']!r}")
    if data["schema_version"] != SCHEMA_VERSION:
        raise _ver(
            f"unsupported schema_version: {data['schema_version']!r} "
            f"(this build reads {SCHEMA_VERSION})"
        )
    integrity = data["integrity"]
    if (
        not isinstance(integrity, dict)
        or set(integrity) != {"digest", "schema"}
        or not isinstance(integrity.get("digest"), str)
        or not _HEX64_RE.match(integrity["digest"])
        or integrity.get("schema") != SCHEMA_TAG
    ):
        raise _ser("integrity must hold {digest: sha256 hex, schema}")
    bank = bank_from_dict(data["bank"])
    if bank_digest(bank) != integrity["digest"]:
        raise _ser("integrity digest mismatch (tampered or reordered content)")
    return bank
