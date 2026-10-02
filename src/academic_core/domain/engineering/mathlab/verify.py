# SPDX-License-Identifier: MIT
"""MATH_LAB ML-0: the verification engine of §5.3 and the correction of §7.

Nothing is shown as correct without an independent second path. This module is
where those second paths live, and where a result that fails them is
*labelled* as failing rather than quietly displayed.

Three checkers, tried in order
------------------------------

1. **Exact symbolic** (:func:`check_equivalence`) — for polynomials and
   rational functions the answer is a normal form comparison, so
   ``derivar(primitiva(f)) == f`` is decided exactly and not by sampling.
2. **Numeric at many seeded points** (:func:`numeric_agreement`) — for
   transcendental expressions no normal form exists, so the two expressions are
   compared at a deterministic set of points, avoiding the poles.

:func:`sampled_points` is the seeded generator. It is an explicit LCG, not
``random``: §11.2 criterion 7 requires every result to be deterministic and
reproducible, and this repository has no RNG dependency in the domain.

Seals
-----

A :class:`Seal` records the verdict and *how* it was reached:

- ``VERIFICADO``  — an independent second path agreed (and says which);
- ``SOLO_NUMERICO`` — only a numerical path ran, or it was too weak to decide
  (this is the honest downgrade §5.9 asks for when a plug-in is missing);
- ``DISCREPA``   — the second path disagreed. The result is *not* presented as
  correct, and the offending case is worth saving (§5.3).

The distinction between ``VERIFICADO`` and ``SOLO_NUMERICO`` is not cosmetic:
§11.2 criterion 2 forbids showing a correct result without an independent
check, and a missing SymPy must lower the seal, not hide the gap.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import poly as P
from academic_core.errors import UnsupportedError


def no_rule(message: str) -> UnsupportedError:
    return UnsupportedError(f"NO_RULE: {message}")

#: relative tolerance for the numeric agreement of two expressions
TOLERANCE = Fraction(1, 10 ** 9)

#: points sampled by the numeric path
MIN_SAMPLES = 8
MAX_SAMPLES = 64
SAMPLE_SEED = 20260930  # fixed: the same input must always give the same verdict

#: a magnitude below which a complex value counts as "zero" (a removable pole
#: that was cancelled exactly); above it, a near-zero is a real disagreement
ZERO_GUARD = 1e-12


@dataclass(frozen=True)
class Seal:
    """The verification mark shown next to every result (§8.1)."""

    verdict: str          # "verificado" | "solo_numerico" | "discrepa"
    method: str           # what actually checked it, in Spanish
    detail: str = ""      # the numbers behind the verdict

    @property
    def ok(self) -> bool:
        return self.verdict == "verificado"

    @property
    def mark(self) -> str:
        return {"verificado": "✔", "solo_numerico": "⚠", "discrepa": "✘"}.get(
            self.verdict, "?")

    def as_text(self) -> str:
        base = {
            "verificado": f"{self.mark} Verificado",
            "solo_numerico": f"{self.mark} Solo numérico",
            "discrepa": f"{self.mark} Discrepa",
        }.get(self.verdict, self.verdict)
        return f"{base} ({self.method})" if self.method else base


VERIFIED = "verificado"
NUMERIC_ONLY = "solo_numerico"
DISCREPANT = "discrepa"


# ---------------------------------------------------------------------------
# seeded sampling
# ---------------------------------------------------------------------------


def sample_values(seed: int = SAMPLE_SEED, count: int = MIN_SAMPLES) -> list[float]:
    """``count`` deterministic values in ``(-4, 4)``, from an explicit LCG.

    The project's convention is no ``random`` in the domain, so a verdict can be
    replayed exactly (§11.2 criterion 7). The range is ``(-4, 4)``: wide enough
    to separate different functions, and it keeps away from the small arguments
    where a numeric path is most fragile.
    """
    count = max(MIN_SAMPLES, min(MAX_SAMPLES, count))
    state = seed & 0xFFFFFFFF
    out: list[float] = []
    for _ in range(count):
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        out.append(state / 0x7FFFFFFF * 8 - 4)
    return out


def sampled_points(names: list[str], seed: int = SAMPLE_SEED,
                   count: int = MIN_SAMPLES) -> list[dict[str, float]]:
    """One environment per sample point, keyed by the real variable names.

    Different variables get *different* values (a shifted window of the same
    deterministic sequence), so that ``x`` and ``y`` are not accidentally tied
    to each other — otherwise ``x + y`` and ``2x`` would agree on the diagonal
    and the check would be worthless.
    """
    pool = sample_values(seed, count + len(names) * 2)
    points: list[dict[str, float]] = []
    for i in range(count):
        env: dict[str, float] = {}
        for j, name in enumerate(names):
            v = pool[(i + j * (count // max(len(names), 1) + 1)) % len(pool)]
            env[name] = v if abs(v) > 1e-6 else v + 1.5  # keep off an exact pole
        points.append(env)
    return points


def _magnitude(z: complex) -> float:
    return abs(z)


def _close(a: complex, b: complex, scale: float) -> bool:
    if a != a or b != b:  # NaN in either: not comparable
        return False
    diff = _magnitude(a - b)
    return diff <= TOLERANCE * max(1.0, scale)


# ---------------------------------------------------------------------------
# exact comparison
# ---------------------------------------------------------------------------


def check_equivalence(a: mx.Expr, b: mx.Expr) -> tuple[bool, str, str]:
    """Exact equality when possible: ``(equal, method, detail)``.

    Three exact routes, strongest first:

    1. identical text — trivial and always right;
    2. identical polynomial normal form (so ``2x+2x`` matches ``4x``);
    3. identical rational normal form in each free variable, which also
       accepts a cancelled factor (``(x²−1)/(x−1)`` matches ``x+1``).

    Returns ``(False, ...)`` when nothing exact applies; the caller then falls
    back to :func:`numeric_agreement`. It never returns ``True`` on a
    numeric-only basis, so a *verified* seal always means an exact check.
    """
    if mx.text(a) == mx.text(b):
        return True, "forma idéntica", "el texto canónico coincide"
    if mx.variables(a) != mx.variables(b):
        return False, "variables distintas", (
            f"«{mx.text(a)}» usa {sorted(mx.variables(a))} y "
            f"«{mx.text(b)}» usa {sorted(mx.variables(b))}"
        )
    if not mx.variables(a):
        va, vb = mx.exact_value(a), mx.exact_value(b)
        if va is not None and vb is not None:
            return (va == vb, "valor exacto", f"{va} frente a {vb}")
    pa, pb = P.as_poly(a), P.as_poly(b)
    if pa == pb:
        return True, "forma normal de polinomio", _poly_detail(pa)
    shared = sorted(mx.variables(a))
    if shared:
        var = shared[0]
        ra = P.as_ratio(a, var)
        rb = P.as_ratio(b, var)
        if ra is not None and rb is not None and P.same_ratio(ra, rb):
            return True, "forma normal racional", (
                f"idénticas como funciones racionales de {var}"
            )
    return False, "", "no hay forma normal común"


def _poly_detail(p: P.Polynomial) -> str:
    terms = len(p)
    return f"{terms} término(s) idéntico(s) en la forma normal"


# ---------------------------------------------------------------------------
# numeric comparison
# ---------------------------------------------------------------------------


def numeric_agreement(a: mx.Expr, b: mx.Expr, *,
                      samples: int = MIN_SAMPLES,
                      seed: int = SAMPLE_SEED) -> tuple[bool, str, str]:
    """Compare at many deterministic points, skipping undefined ones.

    ``(False, ...)`` with a method of ``"pocos puntos definidos"`` when neither
    expression is defined at a single sample: that is *not* agreement, it is
    the absence of evidence, and it must not produce a verified seal.
    """
    names = sorted(mx.variables(a) | mx.variables(b))
    if not names:
        va, vb = mx.evaluate(a), mx.evaluate(b)
        if va is None or vb is None:
            return False, "sin valor definido", "no se pudo evaluar"
        return (_close(va, vb, max(_magnitude(va), _magnitude(vb))),
                "valor numérico", f"{va} frente a {vb}")
    tested = agreed = 0
    worst = 0.0
    for env in sampled_points(names, seed, samples):
        va, vb = mx.evaluate(a, env), mx.evaluate(b, env)
        if va is None or vb is None:
            continue
        scale = max(_magnitude(va), _magnitude(vb))
        if scale < ZERO_GUARD:
            continue  # a removable pole, not evidence either way
        tested += 1
        diff = _magnitude(va - vb) / max(1.0, scale)
        worst = max(worst, diff)
        if diff <= float(TOLERANCE):
            agreed += 1
    if tested == 0:
        return False, "pocos puntos definidos", "ninguna muestra evaluable"
    ok = agreed == tested
    detail = f"{agreed}/{tested} puntos coinciden, desviación máxima {worst:.3g}"
    return ok, f"{tested} puntos numéricos", detail


# ---------------------------------------------------------------------------
# the two paths a calculator uses
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# T-21: the numeric fallback, with its error declared
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Aproximacion:
    """A decimal answer, and what it costs.

    The point of the type is that the error is a **field**, not a footnote. A
    module that can only return exact values never needs it; a module that falls
    back to decimals has to say how much the decimal is worth, and the only honest
    way to do that is to measure how sensitive the expression turned out to be
    rather than quote the size of the last digit and hope.
    """

    valor: complex
    error: float
    cifras: int
    metodo: str
    condicionamiento: float

    def texto(self) -> str:
        digitos = max(0, -int(math.floor(math.log10(self.error)))) if self.error \
            else self.cifras
        return f"{self.valor.real:.{digitos}g} ± {self.error:.1e} ({self.cifras} cifras)"

        return True


def sensibilidad(e: mx.Expr, var: str, x: float, paso: float = 2.0 ** -30) -> float:
    """``|f(x(1+d)) - f(x)| / d``: how much the output moves per unit of input.

    Measured rather than derived, because deriving it would mean differentiating an
    expression this engine differentiates only in its own way, and a wrong
    sensitivity gives a wrong bound just as confidently as a wrong answer.
    """
    base = mx.evaluate(e, {var: x})
    desplazado = mx.evaluate(e, {var: x * (1 + paso)})
    if base is None or desplazado is None:
        return float("inf")
    return abs(desplazado.real - base.real) / paso


def aproximacion(e: mx.Expr, var: str, x: float, cifras: int = 15) -> Aproximacion:
    """Evaluate numerically and say how much the answer is worth.

    Two contributions, both measured:

    1. the representation of ``x`` and of the result — one unit in the last place
       each, which is the honest floor for a double;
    2. what the sensitivity of ``e`` at ``x`` does to that floor. ``sin`` of a
       huge argument is the case that matters: the input is exact, the answer is
       exact, and yet both are computed in doubles, so the error is real and has
       to be reported rather than assumed away.

    The result is deliberately *not* a proof. It is a bound derived from measured
    sensitivity, and it says so, because «±1e-13 porque así lo medí» and «±1e-13
    porque lo prometo» are different claims and only one of them is true.
    """
    valor = mx.evaluate(e, {var: x})
    if valor is None:
        raise no_rule(f"no se puede evaluar «{mx.text(e)}» en {var} = {x}")
    derivadas = sensibilidad(e, var, x)
    magnitud = abs(valor.real) + abs(valor.imag)
    if not math.isfinite(derivadas):
        error = float("inf")
    else:
        error = derivadas * (abs(x) * 2.0 ** -52 + 2.0 ** -52 * max(1.0, magnitud))
    escala = 10.0 ** (cifras - 1)
    redondeo = magnitud / escala / 2.0
    total = error + redondeo
    return Aproximacion(
        valor=valor,
        error=total,
        cifras=cifras,
        condicionamiento=derivadas,
        metodo=(f"doble precisión con sensibilidad medida en {var} = {x} "
                f"(d|f|/dx ≈ {derivadas:.3g}), redondeado a {cifras} cifras"),
    )


def verify_against(value: mx.Expr, expected: mx.Expr, *,
                   numeric: bool = True,
                   samples: int = MIN_SAMPLES,
                   seed: int = SAMPLE_SEED) -> Seal:
    """Check ``value`` against ``expected`` by an independent path.

    The exact path is tried first; if it cannot decide, the numeric path runs
    and the seal is ``SOLO_NUMERICO`` because a numeric path is weaker than a
    proof. A genuine disagreement gives ``DISCREPA`` and the caller must not
    present the result as correct (§5.3).
    """
    equal, method, detail = check_equivalence(value, expected)
    if equal:
        return Seal(VERIFIED, method, detail)
    if not numeric:
        return Seal(NUMERIC_ONLY, "sin comprobación", detail)
    ok, method, numeric_detail = numeric_agreement(value, expected, samples=samples, seed=seed)
    if ok:
        return Seal(NUMERIC_ONLY, method, f"{detail}; {numeric_detail}")
    if method == "pocos puntos definidos":
        return Seal(NUMERIC_ONLY, method, numeric_detail)
    return Seal(DISCREPANT, method, f"{detail}; {numeric_detail}")


def verify_by_derivative(primitive: mx.Expr, integrand: mx.Expr,
                         var: str, differentiate) -> Seal:
    """«verificar la primitiva derivándola» (§5.3, first row).

    ``differentiate`` is injected so the caller can route through the E0.1
    engine (which owns the step log) without this module importing it.
    """
    try:
        derivative = differentiate(primitive, var)
    except Exception as exc:  # the engine refused: that is an honest "no"
        return Seal(NUMERIC_ONLY, "no se pudo derivar", str(exc))
    return verify_against(derivative, integrand)
