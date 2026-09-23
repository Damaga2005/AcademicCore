# SPDX-License-Identifier: MIT
"""E0 integration with the certified equation resolver (Phase 6 ``equations`` / ``calc``).

``explain_equation(inputs, source)`` runs the REAL resolver and records
what it does. The facts come from the engine itself:

- **INPUT** — the raw text inputs and the equation text, exactly as
  received. They are the replay inputs.
- **STEP "Analizar la ecuación"** — ``parse_equation``, the safe parser:
  output name and variables.
- **NORMALIZATION** — ``parse_quantity`` for each input: the exact
  Decimal, the unit and the SI dimension the engine will use.
- **VALUE / STEP** — the evaluator's own observer hook
  (``equations.evaluate(..., observer=...)``). Every literal, unit and
  operation is recorded in real evaluation order. Each carries the
  Quantity the engine computed and the sub-formula text, and refs the
  operand events. A variable read *references* its NORMALIZATION event;
  it is not copied.
- **RESULT** — the value the evaluator returned.
- **CHECK**:
  - dimension consistency against the declared output dimension, when
    one is given
  - equality with the certified ``calc.calculate`` entry point (the
    traced run must not differ from the official one)
- **ERROR** — any failure. It keeps its D2 code and says in which step
  execution stopped. The trace is still returned (outcome ``FAILED``).

Formulas are data (text spans of the parsed source); nothing is
executed from a trace. ``replay_equation`` re-runs the resolver from the
recorded inputs.

E0.1 pedagogical mode (``pedagogical=True``, off by default, so E0
traces are byte-identical) records the input ``e0.mode = pedagogical``
(the name cannot be an equation variable) and adds two kinds of STEP:

- **Unit conversions, exactly where the evaluator performs them**
  (E0.1-R+; E0.1 listed one per prefixed input even when the evaluator
  never converted it, e.g. R1 inside a sum). ``Quantity.to_base()`` of
  the operands of ``*``, ``/``, the base of ``**`` and function
  arguments, and ``convert_to`` of the right operand of ``+``/``-``
  whose unit differs. Each conversion is consumed (ref) by its
  operation.
- **"Sustitución"**: the equation with every variable the evaluator
  really read replaced by its received value (text substitution for
  display; the computation is the evaluator's).

The renderer then presents data → formula → substitution → calculation →
result → verification from these events.
"""

from __future__ import annotations

import re

from academic_core.domain.engineering.calc import calculate
from academic_core.domain.engineering.equations import ALLOWED_FUNCS, evaluate, parse_equation
from academic_core.domain.engineering.units import parse_quantity
from academic_core.domain.execution.model import (
    EventKind,
    ExecutionTrace,
    TraceRecorder,
    TraceValue,
    _invalid,
)

OPERATION = "engineering.equation"
EQUATION_INPUT = "equation"
DIMENSION_INPUT = "expected_dimension"
MODE_INPUT = "e0.mode"

_TO_BASE_FUNCS = ("sin", "cos", "tan", "exp", "log", "log10", "sqrt")  # equations._apply_func uses to_base()
_OP_TITLES = {
    "+": "Suma", "-": "Resta", "*": "Producto", "/": "Cociente", "**": "Potencia",
    "neg": "Cambio de signo",
}


class _Recorder:
    """Evaluator observer: turns the engine's own callbacks into events.

    The engine evaluates by recursive descent, so operands always arrive
    before the operation that consumes them. A stack of event ids
    therefore links each operation to its real operands.
    """

    def __init__(self, rec: TraceRecorder, variables: dict[str, str], pedagogical: bool = False):
        self.rec = rec
        self.variables = variables  # variable name -> its NORMALIZATION event id
        self.stack: list[str] = []
        self.values: list = []  # the Quantity of each stack entry (pedagogical conversions only)
        self.texts: list[str] = []
        self.read: set[str] = set()  # variables the evaluator actually read
        self.pedagogical = pedagogical

    def leaf(self, kind: str, text: str, quantity) -> None:
        self.values.append(quantity)
        self.texts.append(text)
        if kind == "variable" and text in self.variables:
            self.read.add(text)
            self.stack.append(self.variables[text])  # reference, not a copy
            return
        title = f"Constante {text}" if kind == "literal" else f"Unidad {text}"
        self.stack.append(self.rec.event(EventKind.VALUE, title, formula=text,
                                         result=TraceValue.of_quantity(quantity)))

    def _conversions(self, op: str, operands: tuple, quantities: tuple, texts: tuple) -> tuple:
        """E0.1-R+: exactly the unit conversions the evaluator performs inside this operation.

        - ``*`` / ``/`` and functions: ``Quantity.to_base()`` of every operand
          (``**``: of the base only); shown only when the factor is not 1
        - ``+`` / ``-``: the right operand ``convert_to`` the left operand's unit,
          shown only when the units differ
        Other operations convert nothing, and nothing is shown for them."""
        out = []
        if op in ("*", "/", "**") or op in _TO_BASE_FUNCS:
            chosen = range(1) if op == "**" else range(len(operands))
            for i in chosen:
                q = quantities[i]
                if q.unit.factor != 1:
                    symbol = {"ohm": "Ω"}.get(q.unit.base, q.unit.base)
                    base = q.to_base()
                    out.append(self.rec.event(
                        EventKind.STEP, f"Conversión a unidades SI: {texts[i]}", refs=(operands[i],),
                        formula=f"{texts[i]} = {q.value} {q.unit.display} = {base} {symbol}",
                        why=f"El evaluador pasa este operando a unidades base al calcular «{op}»: "
                            f"1 {q.unit.display} = {q.unit.factor} {symbol}.",
                        values=(("factor", TraceValue.of_number(q.unit.factor)),),
                        result=TraceValue.of_number(base, symbol, tuple(q.dimension))))
        elif op in ("+", "-") and len(quantities) == 2 and quantities[0].unit.display != quantities[1].unit.display:
            left, right = quantities
            converted = right.convert_to(left.unit.display)  # the engine's own conversion for + and -
            out.append(self.rec.event(
                EventKind.STEP, f"Conversión de unidades: {texts[1]}", refs=(operands[1],),
                formula=f"{texts[1]} = {right.value} {right.unit.display} = {converted.value} {left.unit.display}",
                why=f"Para «{op}» el evaluador expresa el operando derecho en la unidad del izquierdo.",
                result=TraceValue.of_quantity(converted)))
        return tuple(out)

    def operation(self, op: str, text: str, arity: int, quantity) -> None:
        operands = tuple(self.stack[-arity:])
        quantities, texts = tuple(self.values[-arity:]), tuple(self.texts[-arity:])
        del self.stack[-arity:], self.values[-arity:], self.texts[-arity:]
        if self.pedagogical:
            operands = operands + self._conversions(op, operands, quantities, texts)
        self.values.append(quantity)
        self.texts.append(text)
        title = _OP_TITLES.get(op, f"Función {op}")
        why = ("Se aplica la función de la lista blanca del motor." if op not in _OP_TITLES
               else "El evaluador aplica la operación con aritmética Decimal exacta y comprobación de unidades.")
        self.stack.append(self.rec.event(EventKind.STEP, title, refs=operands, formula=text, why=why,
                                         result=TraceValue.of_quantity(quantity)))


def _substitute(rhs: str, texts: dict[str, str]) -> str:
    """Replace whole-word variable names by their received text (display only)."""
    return re.sub(r"[A-Za-z_][A-Za-z0-9_]*", lambda m: f"({texts[m.group(0)]})" if m.group(0) in texts else m.group(0),
                  rhs)


def explain_equation(inputs, source: str, expected_dimension: str | None = None, *,
                     pedagogical: bool = False) -> ExecutionTrace:
    """Run ``source`` on text ``inputs`` ({name: "5 V"}) and return its real ExecutionTrace."""
    if not isinstance(inputs, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in inputs.items()):
        raise _invalid("INVALID_INPUT", "inputs must be a {name: text} mapping")
    if not isinstance(source, str):
        raise _invalid("INVALID_INPUT", "equation source must be text")
    if {EQUATION_INPUT, DIMENSION_INPUT, MODE_INPUT} & set(inputs):
        raise _invalid("INVALID_INPUT", f"{EQUATION_INPUT!r}/{DIMENSION_INPUT!r}/{MODE_INPUT!r} are reserved input names")
    rec = TraceRecorder(OPERATION)
    src_id = rec.input(EQUATION_INPUT, TraceValue.of_text(source), "Ecuación recibida")
    if expected_dimension is not None:
        rec.input(DIMENSION_INPUT, TraceValue.of_text(expected_dimension), "Dimensión esperada del resultado")
    if pedagogical:
        rec.input(MODE_INPUT, TraceValue.of_text("pedagogical"), "Modo pedagógico")
    raw_ids = {name: rec.input(name, TraceValue.of_text(inputs[name]), f"Dato {name} recibido")
               for name in sorted(inputs)}
    observer = None
    try:
        eq = parse_equation(source)
        parse_id = rec.event(
            EventKind.STEP, "Analizar la ecuación", refs=(src_id,), formula=eq.source,
            why="El analizador propio del motor (sin eval) valida la sintaxis y extrae variables y unidades.",
            values=(("output", TraceValue.of_text(eq.output)),
                    ("variables", TraceValue.of_text(", ".join(eq.variables)))))
        env, variables = {}, {}
        for name in sorted(inputs):
            quantity = parse_quantity(inputs[name])
            env[name] = quantity
            variables[name] = rec.event(
                EventKind.NORMALIZATION, f"Normalizar {name}", refs=(raw_ids[name],), formula=name,
                why="El texto se convierte en una magnitud Decimal exacta con unidad y dimensión SI.",
                result=TraceValue.of_quantity(quantity))
        if pedagogical:
            rhs_text = eq.source.partition("=")[2].strip()
            # engine rule (equations._Eval.primary): a name present in the inputs is always read as that variable
            tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", rhs_text)) - set(ALLOWED_FUNCS)
            used = {n: inputs[n].strip() for n in sorted(tokens) if n in inputs}
            rec.event(EventKind.STEP, "Sustitución", refs=(parse_id, *(variables[n] for n in sorted(used))),
                      formula=f"{eq.output} = {_substitute(rhs_text, used)}"[:512],
                      why="Se sustituye cada variable de la fórmula por su dato; el cálculo lo hace el evaluador.")
        observer = _Recorder(rec, variables, pedagogical)
        value = evaluate(eq, env, observer=observer)  # unknown names fail here, inside the engine
        top = observer.stack[-1]
        unused = sorted(set(inputs) - observer.read)
        if unused:  # from the reads the evaluator really made
            rec.event(EventKind.WARNING, "Datos no usados por la ecuación", refs=(parse_id,),
                      values=tuple((n, TraceValue.of_text(inputs[n])) for n in unused))
        rhs = eq.source.partition("=")[2].strip()
        result_id = rec.event(EventKind.RESULT, f"Resultado {eq.output}", refs=(top,),
                              formula=f"{eq.output} = {rhs}", result=TraceValue.of_quantity(value))
        if expected_dimension is not None:
            rec.check("dimensión del resultado", TraceValue.of_text(value.dim_name),
                      TraceValue.of_text(expected_dimension), value.dim_name == expected_dimension,
                      refs=(result_id,), detail=f"exponentes SI {list(value.dimension)}",
                      title="Comprobación: consistencia de unidades")
        official = calculate(env, eq.source, at="execution-trace").value  # fixed stamp: no wall clock
        same = official.value == value.value and official.unit.display == value.unit.display
        rec.check("igual al cálculo certificado (calc.calculate)", TraceValue.of_quantity(value),
                  TraceValue.of_quantity(official), same, refs=(result_id,),
                  title="Comprobación: coincide con el motor certificado")
    except (ValueError, ArithmeticError) as exc:
        # the values that were ready when the engine stopped (operands of the failing step), else the last fact
        ready = tuple(dict.fromkeys(observer.stack))[-8:] if observer is not None and observer.stack else ()
        rec.fail(exc, "La ejecución se detuvo", refs=ready or tuple(r for r in (rec.last,) if r))
    return rec.finish()


def replay_equation(trace: ExecutionTrace) -> ExecutionTrace:
    """Re-run the resolver from the inputs recorded in ``trace``."""
    if not isinstance(trace, ExecutionTrace) or trace.operation != OPERATION:
        raise _invalid("INVALID_TRACE", f"not an {OPERATION} trace")
    recorded = dict(trace.inputs)
    source = recorded.pop(EQUATION_INPUT).text
    expected = recorded.pop(DIMENSION_INPUT).text if DIMENSION_INPUT in recorded else None
    mode = recorded.pop(MODE_INPUT).text if MODE_INPUT in recorded else None
    if mode not in (None, "pedagogical"):
        raise _invalid("INVALID_TRACE", f"unknown mode {mode[:32]!r}")
    return explain_equation({k: v.text for k, v in recorded.items()}, source, expected,
                            pedagogical=mode == "pedagogical")
