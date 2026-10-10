# SPDX-License-Identifier: MIT
"""MATH_LAB ML-0: the step trace (traza de pasos) of §5.2 and §5.9.

Every operation the engine performs appends steps here. The format is the
contract of §5.9: *versioned, textual, key-value, with three levels of detail*,
so another laboratory (signals, circuits, digital) can embed the steps in its
own screen without rewriting them.

What a step carries
-------------------

=====================  ===========================================
field                  meaning
=====================  ===========================================
``index``              position in the trace
``kind``               ``regla`` | ``metodo`` | ``cambio`` | ``hipotesis``
                       | ``convencion`` | ``verificacion`` | ``aviso``
``rule``               stable identifier, e.g. ``derivada.producto``
``label``              the rule in Spanish, as it is shown
``before`` / ``after`` the affected piece, before and after
``piece``              which part of the expression the rule touched
``conditions``         hypotheses, e.g. ``x != 0``
``why``                **«por qué este método»** (§5.5b) — required
``alternatives``       methods considered and why they were not chosen
``detail``             ``resumen`` | ``paso`` | ``detallado``
``uses``               indices of earlier steps this one consumes
=====================  ===========================================

Three levels of detail (§5.2, §8.1):

- ``RESUMEN``   — one line per step: the rule and the result.
- ``PASO``      — the default: before, after, conditions and ``why``.
- ``DETALLADO``  — everything, including the alternatives and the formal note.

The ``why`` field is **not optional** (:func:`Trace.add` rejects an empty one
for ``kind="metodo"``): §5.5b makes justifying a method choice an acceptance
criterion of every phase (§11.2, criterion 10), and an unjustified step is a
step the engine should not have claimed.

Serialisation
-------------

:func:`to_text` writes the versioned key-value form of §5.9, and
:func:`from_text` reads it back, so a trace can be stored, sent between
laboratories and replayed. Fields are bounded; a longer value is refused rather
than silently truncated.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from academic_core.errors import ValidationError

#: contract version of §5.9; a consumer declares the one it was built against
TRACE_VERSION = "1.1"   # 1.1: values escaped (\\, \n, \r, \p for |, \e for =)

#: detail levels, coarse to fine (§5.2)
RESUMEN = "resumen"
PASO = "paso"
DETALLADO = "detallado"
LEVELS = (RESUMEN, PASO, DETALLADO)

MAX_STEPS = 2000
MAX_FIELD = 2000
#: tope de seguridad; con 8000 un cálculo legítimo de 67 pasos (campos v_dado) no se
#: podía mostrar. Los límites reales son MAX_STEPS y MAX_FIELD.
MAX_RENDERED = 1_000_000

#: the kinds of step the engine is allowed to record
REGLA = "regla"
METODO = "metodo"
CAMBIO = "cambio"          # a change of variable (§5.6)
HIPOTESIS = "hipotesis"    # a theorem's hypothesis, checked (§5.7)
CONVENCION = "convencion"  # a declared convention (§5.11)
VERIFICACION = "verificacion"
AVISO = "aviso"
KINDS = (REGLA, METODO, CAMBIO, HIPOTESIS, CONVENCION, VERIFICACION, AVISO)


_ESCAPES = (("\\", "\\\\"), ("\n", "\\n"), ("\r", "\\r"), ("|", "\\p"), ("=", "\\e"))


def _esc(value: str) -> str:
    """One line, no bare separators: a field survives any content (found 2026-10-06:
    a label ending in a space, or holding a newline, did not read back)."""
    for raw, escaped in _ESCAPES:
        value = value.replace(raw, escaped)
    return value


def _unesc(value: str) -> str:
    out, i = [], 0
    back = {"\\": "\\", "n": "\n", "r": "\r", "p": "|", "e": "="}
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value) and value[i + 1] in back:
            out.append(back[value[i + 1]])
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _invalid(reason: str, message: str) -> ValidationError:
    return ValidationError(f"{reason}: {message}")


@dataclass(frozen=True)
class Step:
    """One recorded step. Frozen: a trace never rewrites its own history."""

    index: int
    kind: str
    rule: str
    label: str
    before: str = ""
    after: str = ""
    piece: str = ""
    conditions: tuple[str, ...] = ()
    why: str = ""
    alternatives: tuple[tuple[str, str], ...] = ()  # (method, why not)
    detail: str = PASO
    uses: tuple[int, ...] = ()

    def at_level(self, level: str) -> bool:
        """Should this step be shown at ``level``? Detail is cumulative."""
        if level not in LEVELS:
            raise _invalid("BAD_LEVEL", f"nivel de detalle desconocido: {level!r}")
        return LEVELS.index(self.detail) <= LEVELS.index(level)

    def render(self, level: str = PASO) -> str:
        """One human line (or block) for this step at ``level``."""
        if not self.at_level(level):
            return ""
        head = f"{self.index + 1}. [{self.rule}] {self.label}"
        if level == RESUMEN:
            return head
        parts = [head]
        if self.piece:
            parts.append(f"   trozo: {self.piece}")
        if self.before or self.after:
            parts.append(f"   antes: {self.before}")
            parts.append(f"   después: {self.after}")
        if self.conditions:
            parts.append("   condiciones: " + "; ".join(self.conditions))
        if self.why and level != RESUMEN:
            parts.append(f"   por qué este método: {self.why}")
        if self.alternatives and level == DETALLADO:
            for method, reason in self.alternatives:
                parts.append(f"   no se eligió «{method}»: {reason}")
        if self.uses and level == DETALLADO:
            parts.append("   usa los pasos: " + ", ".join(str(u + 1) for u in self.uses))
        return "\n".join(parts)

    def to_pairs(self) -> list[tuple[str, str]]:
        pairs = [
            ("index", str(self.index)),
            ("kind", self.kind),
            ("rule", self.rule),
            ("label", _esc(self.label)),
            ("before", _esc(self.before)),
            ("after", _esc(self.after)),
            ("piece", _esc(self.piece)),
            ("conditions", "|".join(_esc(c) for c in self.conditions)),
            ("why", _esc(self.why)),
            ("alternatives", "|".join(f"{_esc(m)}={_esc(r)}" for m, r in self.alternatives)),
            ("detail", self.detail),
            ("uses", ",".join(str(u) for u in self.uses)),
        ]
        return pairs

    @classmethod
    def from_pairs(cls, pairs: Iterable[tuple[str, str]]) -> "Step":
        data = dict(pairs)
        try:
            alternatives = tuple(
                (_unesc(m), _unesc(r)) for part in data.get("alternatives", "").split("|") if part
                for m, r in [part.split("=", 1)]
            )
            return cls(
                index=int(data.get("index", "0")),
                kind=data.get("kind", REGLA),
                rule=data.get("rule", ""),
                label=_unesc(data.get("label", "")),
                before=_unesc(data.get("before", "")),
                after=_unesc(data.get("after", "")),
                piece=_unesc(data.get("piece", "")),
                conditions=tuple(_unesc(c) for c in data.get("conditions", "").split("|") if c),
                why=_unesc(data.get("why", "")),
                alternatives=alternatives,
                detail=data.get("detail", PASO),
                uses=tuple(int(u) for u in data.get("uses", "").split(",") if u),
            )
        except (ValueError, IndexError) as exc:
            raise _invalid("TRACE_CORRUPT", f"paso ilegible: {exc}") from exc


class Trace:
    """An ordered, bounded log of steps.

    The log only records; it never computes. A strategy that was tried and
    failed contributes nothing (the caller decides what to keep), which is what
    §5.5b means by «si el camino elegido no concluye, lo dice y cambia de
    método explicando el cambio»: the abandoned attempt is visible only if the
    caller records it as an ``aviso``.
    """

    def __init__(self, level: str = PASO) -> None:
        if level not in LEVELS:
            raise _invalid("BAD_LEVEL", f"nivel de detalle desconocido: {level!r}")
        self.level = level
        self.steps: list[Step] = []

    def __len__(self) -> int:
        return len(self.steps)

    def __iter__(self):
        return iter(self.steps)

    def at(self, level: str | None = None) -> list[Step]:
        want = level or self.level
        return [s for s in self.steps if s.at_level(want)]

    def add(
        self,
        kind: str,
        rule: str,
        label: str,
        *,
        before: str = "",
        after: str = "",
        piece: str = "",
        conditions: Iterable[str] = (),
        why: str = "",
        alternatives: Iterable[tuple[str, str]] = (),
        detail: str = PASO,
        uses: Iterable[int] = (),
    ) -> int:
        if kind not in KINDS:
            raise _invalid("BAD_STEP", f"tipo de paso desconocido: {kind!r}")
        if detail not in LEVELS:
            raise _invalid("BAD_LEVEL", f"nivel de detalle desconocido: {detail!r}")
        if not rule:
            raise _invalid("BAD_STEP", "todo paso necesita un identificador de regla")
        if not label:
            raise _invalid("BAD_STEP", "todo paso necesita su nombre en castellano")
        if kind == METODO and not why.strip():
            raise _invalid(
                "NO_WHY",
                "un paso de método necesita «por qué este método» (§5.5b)",
            )
        if len(self.steps) >= MAX_STEPS:
            raise _invalid("EXPRESSION_LIMIT", f"más de {MAX_STEPS} pasos")
        for name, value in (("rule", rule), ("label", label), ("before", before),
                            ("after", after), ("piece", piece), ("why", why)):
            if len(value) > MAX_FIELD:
                raise _invalid("EXPRESSION_LIMIT", f"campo «{name}» de más de {MAX_FIELD} caracteres")
        step = Step(
            index=len(self.steps),
            kind=kind,
            rule=rule,
            label=label,
            before=before,
            after=after,
            piece=piece,
            conditions=tuple(conditions),
            why=why,
            alternatives=tuple(alternatives),
            detail=detail,
            uses=tuple(u for u in uses if isinstance(u, int) and u >= 0),
        )
        self.steps.append(step)
        return step.index

    # -- shorthands, so the rules read as rules and not as bookkeeping

    def regla(self, rule: str, label: str, **kw) -> int:
        return self.add(REGLA, rule, label, **kw)

    def metodo(self, rule: str, label: str, why: str, **kw) -> int:
        return self.add(METODO, rule, label, why=why, **kw)

    def cambio(self, rule: str, label: str, why: str, **kw) -> int:
        return self.add(CAMBIO, rule, label, why=why, **kw)

    def hipotesis(self, rule: str, statement: str, verdict: str, **kw) -> int:
        """Record a theorem hypothesis *and its verdict* (§5.7)."""
        return self.add(HIPOTESIS, rule, statement, after=verdict, **kw)

    def convencion(self, rule: str, statement: str, **kw) -> int:
        return self.add(CONVENCION, rule, statement, **kw)

    def verificacion(self, rule: str, label: str, **kw) -> int:
        return self.add(VERIFICACION, rule, label, **kw)

    def aviso(self, rule: str, label: str, **kw) -> int:
        return self.add(AVISO, rule, label, **kw)

    def extend(self, other: "Trace") -> None:
        """Append another trace, renumbering (used when a strategy succeeded)."""
        if len(self.steps) + len(other.steps) > MAX_STEPS:
            raise _invalid("EXPRESSION_LIMIT", f"más de {MAX_STEPS} pasos")
        offset = len(self.steps)
        for s in other.steps:
            self.steps.append(replace(
                s, index=s.index + offset,
                uses=tuple(u + offset for u in s.uses),
            ))

    def render(self, level: str | None = None) -> str:
        want = level or self.level
        out = "\n".join(s.render(want) for s in self.at(want))
        if len(out) > MAX_RENDERED:
            raise _invalid("EXPRESSION_LIMIT", f"la traza supera {MAX_RENDERED} caracteres")
        return out

    def hypotheses(self) -> list[tuple[str, str]]:
        """Every hypothesis recorded, with its verdict (for the UI panel)."""
        return [(s.label, s.after) for s in self.steps if s.kind == HIPOTESIS]

    def conventions(self) -> list[str]:
        return [s.label for s in self.steps if s.kind == CONVENCION]

    def to_text(self, level: str | None = None) -> str:
        """The versioned key-value serialisation of §5.9."""
        want = level or self.level
        lines = [f"mathlab.trace {TRACE_VERSION}"]
        for s in self.at(want):
            for key, value in s.to_pairs():
                lines.append(f"{key}: {value}")
            lines.append("-")
        return "\n".join(lines)

    @classmethod
    def from_text(cls, text: str, level: str = PASO) -> "Trace":
        """Read back :meth:`to_text`; a malformed trace is refused, not patched."""
        lines = text.splitlines()
        if not lines or not lines[0].startswith("mathlab.trace "):
            raise _invalid("TRACE_CORRUPT", "no es una traza de mathlab")
        version = lines[0].split(" ", 1)[1].strip()
        if version.split(".")[0] != TRACE_VERSION.split(".")[0]:
            raise _invalid(
                "VERSION_MISMATCH",
                f"traza de versión {version}, el motor habla la {TRACE_VERSION}",
            )
        trace = cls(level=level)
        block: list[tuple[str, str]] = []
        for line in lines[1:]:
            if line == "-":
                if block:
                    trace.steps.append(Step.from_pairs(block))
                    block = []
                continue
            key, _, value = line.partition(":")
            # exactly one space follows the colon; the value keeps its own spaces
            block.append((key.strip(), value[1:] if value.startswith(" ") else value))
        if block:
            raise _invalid("TRACE_CORRUPT", "el último paso está incompleto")
        # to_text(nivel) omite los pasos de más detalle: los índices pueden saltar,
        # pero nunca repetirse ni retroceder
        for i, (a, b) in enumerate(zip(trace.steps, trace.steps[1:])):
            if not b.index > a.index:
                raise _invalid("TRACE_CORRUPT", f"pasos fuera de orden en la posición {i + 2}")
        if trace.steps and trace.steps[0].index < 0:
            raise _invalid("TRACE_CORRUPT", "índice de paso negativo")
        return trace


#: an empty trace, for functions that may not produce steps
EMPTY = Trace()
