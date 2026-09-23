# SPDX-License-Identifier: MIT
"""E0.1 integration with the certified F8-P margins engine (``control.margins``).

``explain_margins(numerator, denominator)`` builds L(s) with ``make_tf``
and runs ``margins(loop, observer=...)`` once. The trace records:

- **INPUT**: the coefficients of the numerator and the denominator,
  descending powers of s, as text. These are the replay inputs.
- **STEP "Función de lazo"**: L(s) as the engine built it.
- **STEP "Intervalo con cambio de signo"**: every bracket that the
  logarithmic scan found and handed to bisection (gain: |L(jω)| − 1;
  phase: Im L(jω)).
- **STEP "Bisección k"**: every midpoint the engine evaluated, with lo,
  hi, ω_mid and f(ω_mid), exactly as computed. E0.1-R+ adds f(lo) and
  f(hi) as the engine held them (f(hi) of the phase bisection is never
  computed, and the event says so), the sign condition taken, the new
  interval, and the relative width the engine tested.
- **DECISION "Parada de la bisección"**: the reason the engine stopped
  (relative width ≤ 1e-12, an exact zero, or the iteration budget) and
  the refined ω.
- **RESULT**: the margins report as the engine returned it (PM, ω_gc,
  GM, ω_pc, delay margin, statuses).
- **CHECK**:
  - |L(jω_gc)| = 1 at the reported ω_gc, when there is one. The engine's
    own evaluator is used; the tolerance is 1e-9 relative.
  - the reported ω_gc lies inside its bracket
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from academic_core.domain.engineering.control.margins import _eval_jw, margins
from academic_core.domain.engineering.control.tf import make_tf
from academic_core.domain.execution.model import EventKind, ExecutionTrace, TraceRecorder, TraceValue, _invalid

OPERATION = "control.margins"
MAX_COEFFS = 33
GC_TOL = Decimal("1e-9")


def _coeffs(text: str, name: str) -> tuple[Decimal, ...]:
    if not isinstance(text, str) or not text.strip():
        raise _invalid("INVALID_INPUT", f"{name}: coefficients such as '1, 2, 0'")
    parts = [p.strip() for p in text.split(",")]
    if len(parts) > MAX_COEFFS:
        raise _invalid("INVALID_INPUT", f"{name}: at most {MAX_COEFFS} coefficients")
    try:
        out = tuple(Decimal(p) for p in parts)
    except InvalidOperation:
        raise _invalid("INVALID_INPUT", f"{name}: coefficients must be decimal numbers") from None
    if not all(c.is_finite() for c in out):
        raise _invalid("INVALID_INPUT", f"{name}: coefficients must be finite")
    return out


def _poly_text(coeffs: tuple[Decimal, ...]) -> str:
    n = len(coeffs) - 1
    terms = []
    for i, c in enumerate(coeffs):
        p = n - i
        if c == 0:
            continue
        s = "" if p == 0 else "s" if p == 1 else f"s^{p}"
        terms.append(f"{c}{'*' + s if s else ''}" if c != 1 or not s else s)
    return " + ".join(terms) or "0"


class _Observer:
    def __init__(self):
        self.facts: list = []

    def bracket(self, kind, lo, hi):
        self.facts.append(("bracket", kind, lo, hi))

    def bisection(self, kind, k, lo, hi, mid, f_mid, *, f_lo=None, f_hi=None, new_lo=None, new_hi=None, width=None):
        self.facts.append(("bisection", kind, k, lo, hi, mid, f_mid, f_lo, f_hi, new_lo, new_hi, width))

    def refined(self, kind, omega, reason):
        self.facts.append(("refined", kind, omega, reason))


def explain_margins(numerator: str, denominator: str) -> ExecutionTrace:
    rec = TraceRecorder(OPERATION)
    n_id = rec.input("numerator", TraceValue.of_text(numerator if isinstance(numerator, str) else ""), "Numerador de L(s)")
    d_id = rec.input("denominator", TraceValue.of_text(denominator if isinstance(denominator, str) else ""),
                     "Denominador de L(s)")
    try:
        num, den = _coeffs(numerator, "numerator"), _coeffs(denominator, "denominator")
        loop = make_tf(num, den)
        tf_id = rec.event(EventKind.STEP, "Función de lazo", refs=(n_id, d_id),
                          formula=f"L(s) = ({_poly_text(num)}) / ({_poly_text(den)})",
                          why="Se construye L(s) con make_tf; los márgenes se obtienen evaluando L(jω) directamente.")
        obs = _Observer()
        report = margins(loop, observer=obs)
        last_decision = {"gain": None, "phase": None}
        bracket_id = tf_id
        prev = tf_id
        labels = {"gain": ("|L(jω)| − 1", "cruce de ganancia"), "phase": ("Im L(jω)", "cruce de fase")}
        for fact in obs.facts:
            kind = fact[1]
            f_name, label = labels[kind]
            if fact[0] == "bracket":
                _, _, lo, hi = fact
                bracket_id = prev = rec.event(
                    EventKind.STEP, f"Intervalo con cambio de signo ({label})", refs=(tf_id,),
                    formula=f"{f_name} cambia de signo en [{lo}, {hi}] rad/s",
                    why="El barrido logarítmico (40 puntos por década) encontró un cambio de signo; se refina por bisección.",
                    values=(("lo", TraceValue.of_number(lo, "rad/s")), ("hi", TraceValue.of_number(hi, "rad/s"))))
            elif fact[0] == "bisection":
                _, _, k, lo, hi, mid, f_mid, f_lo, f_hi, new_lo, new_hi, width = fact
                if new_lo == new_hi == mid:
                    kept = "f(ω_mid) = 0 exacto: la bisección termina en ω_mid"
                elif new_lo == mid:
                    kept = "signo(f(lo)) = signo(f(ω_mid)) → lo ← ω_mid"
                else:
                    kept = "signo(f(lo)) ≠ signo(f(ω_mid)) → hi ← ω_mid"
                values = [("lo", TraceValue.of_number(lo, "rad/s")), ("hi", TraceValue.of_number(hi, "rad/s")),
                          ("omega_mid", TraceValue.of_number(mid, "rad/s")), ("f_mid", TraceValue.of_number(f_mid)),
                          ("f_lo", TraceValue.of_number(f_lo) if f_lo is not None else TraceValue.of_text("no calculado")),
                          ("f_hi", TraceValue.of_number(f_hi) if f_hi is not None else
                           TraceValue.of_text("no calculado por el motor")),
                          ("sign_condition", TraceValue.of_text(kept))]
                if new_lo is not None:
                    values += [("new_lo", TraceValue.of_number(new_lo, "rad/s")),
                               ("new_hi", TraceValue.of_number(new_hi, "rad/s"))]
                if width is not None:
                    values.append(("relative_width", TraceValue.of_number(width)))
                prev = rec.event(
                    EventKind.STEP, f"Bisección {k} ({label})", refs=(prev,),
                    formula=f"ω_mid = (lo + hi)/2;  {f_name} en ω_mid;  nuevo intervalo [new_lo, new_hi]",
                    why=("Se conserva la mitad del intervalo donde la función sigue cambiando de signo. "
                         "relative_width = (hi − lo)/hi es el ancho que el motor comparó con 1e-12 antes de este paso."),
                    values=tuple(values))
            else:
                _, _, omega, reason = fact
                prev = last_decision[kind] = rec.event(
                    EventKind.DECISION, f"Parada de la bisección ({label})", refs=(prev, bracket_id),
                    why=f"Motivo: {reason}.", values=(("reason", TraceValue.of_text(reason)),),
                    result=TraceValue.of_number(omega, "rad/s"))
        summary = (f"PM = {report.phase_margin_deg or '-'}° en ω_gc = {report.omega_gc or '-'} rad/s; "
                   f"GM = {report.gain_margin or '-'} ({report.gain_margin_db or '-'} dB) en ω_pc = "
                   f"{report.omega_pc or '-'} rad/s; estados PM {report.pm_status}, GM {report.gm_status}")
        refs = tuple(r for r in (last_decision["gain"], last_decision["phase"]) if r) or (tf_id,)
        res_id = rec.event(EventKind.RESULT, "Márgenes de estabilidad", refs=refs, formula=summary[:512],
                           values=(("phase_margin_deg", TraceValue.of_text(report.phase_margin_deg or "-")),
                                   ("omega_gc", TraceValue.of_text(report.omega_gc or "-")),
                                   ("gain_margin", TraceValue.of_text(report.gain_margin or "-")),
                                   ("omega_pc", TraceValue.of_text(report.omega_pc or "-")),
                                   ("delay_margin_s", TraceValue.of_text(report.delay_margin_s or "-"))),
                           result=TraceValue.of_text(summary[:512]))
        if report.omega_gc:
            wgc = Decimal(report.omega_gc)
            mag = _eval_jw(loop, wgc).modulus()
            err = abs(mag - 1)
            rec.check("|L(jω_gc)| = 1", TraceValue.of_number(mag), TraceValue.of_number(Decimal(1)), err <= GC_TOL,
                      refs=(res_id,), tolerance=TraceValue.of_number(GC_TOL), title="Comprobación: cruce de ganancia")
            lo, hi = (Decimal(v) for v in report.gc_bracket)
            rec.check("ω_gc dentro de su intervalo", TraceValue.of_number(wgc), TraceValue.of_text(f"[{lo}, {hi}]"),
                      lo <= wgc <= hi, refs=(res_id,), title="Comprobación: intervalo de bisección")
        else:
            rec.check("|L(jω_gc)| = 1", TraceValue.of_text("-"), TraceValue.of_number(Decimal(1)), None, refs=(res_id,),
                      detail="no aplicable: el motor no encontró cruce de ganancia", title="Comprobación: cruce de ganancia")
    except (ValueError, ArithmeticError) as exc:
        rec.fail(exc, "La ejecución se detuvo", refs=tuple(r for r in (rec.last,) if r))
    return rec.finish()


def explain_margins_tf(loop) -> ExecutionTrace:
    """Trace a ``TransferFunctionTF`` through its exact coefficients (E0.1-R+ L7)."""
    from academic_core.domain.engineering.control.tf import TransferFunctionTF

    if not isinstance(loop, TransferFunctionTF):
        raise _invalid("INVALID_INPUT", "expected a TransferFunctionTF")
    return explain_margins(", ".join(str(c) for c in loop.num.coeffs), ", ".join(str(c) for c in loop.den.coeffs))


def replay_margins(trace: ExecutionTrace) -> ExecutionTrace:
    if not isinstance(trace, ExecutionTrace) or trace.operation != OPERATION:
        raise _invalid("INVALID_TRACE", f"not an {OPERATION} trace")
    inputs = dict(trace.inputs)
    return explain_margins(inputs["numerator"].text, inputs["denominator"].text)
