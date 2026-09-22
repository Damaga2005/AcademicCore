"""F8-P4 pulse shaping (NEW).

Rectangular (exact), sinc (node-exact, truncated lobes), raised-cosine
and root-raised-cosine with closed analytic limits at every singularity
(t = 0 and t = +-Ts/(2*alpha) for RC; t = 0 and t = +-Ts/(4*alpha) for
RRC via L'Hopital). roll-off alpha in [0, 1]; alpha = 0 collapses to
sinc through the same code path (no second implementation).
"""

from __future__ import annotations

from decimal import Decimal

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.math import (
    decimal_cos,
    decimal_pi,
    decimal_sin,
    make_context,
)

MAX_LOBES = 5000


def _fail(status: ControlStatus, message: str) -> ControlError:
    return ControlError(status, message)


def _as_symbol_period(value: object) -> Decimal:
    if isinstance(value, bool):
        raise _fail(ControlStatus.INVALID, "symbol period rejects bool")
    if isinstance(value, Decimal):
        out = value
    elif isinstance(value, int):
        out = Decimal(value)
    elif isinstance(value, str):
        try:
            out = Decimal(value.strip())
        except Exception as exc:
            raise _fail(ControlStatus.INVALID, "bad symbol period string") from exc
    else:
        raise _fail(ControlStatus.INVALID, "symbol period must be Decimal/int/str")
    if not out.is_finite() or out <= 0:
        raise _fail(ControlStatus.INVALID, "symbol period Ts > 0 required")
    return out


def _as_time(value: object) -> Decimal:
    if isinstance(value, bool):
        raise _fail(ControlStatus.INVALID, "time rejects bool")
    if isinstance(value, Decimal):
        out = value
    elif isinstance(value, int):
        out = Decimal(value)
    elif isinstance(value, str):
        try:
            out = Decimal(value.strip())
        except Exception as exc:
            raise _fail(ControlStatus.INVALID, "bad time string") from exc
    else:
        raise _fail(ControlStatus.INVALID, "time must be Decimal/int/str")
    if not out.is_finite():
        raise _fail(ControlStatus.INVALID, "time must be finite")
    return out


def _as_rolloff(value: object) -> Decimal:
    if isinstance(value, bool):
        raise _fail(ControlStatus.INVALID, "roll-off rejects bool")
    if isinstance(value, Decimal):
        out = value
    elif isinstance(value, int):
        out = Decimal(value)
    elif isinstance(value, str):
        try:
            out = Decimal(value.strip())
        except Exception as exc:
            raise _fail(ControlStatus.INVALID, "bad roll-off string") from exc
    else:
        raise _fail(ControlStatus.INVALID, "roll-off must be Decimal/int/str")
    if not out.is_finite() or out < 0 or out > 1:
        raise _fail(ControlStatus.INVALID, "roll-off alpha in [0, 1] required")
    return out


def rectangular(time_s: object, symbol_period_s: object) -> Decimal:
    """p(t) = 1 on [0, Ts), else 0 (exact; energy Ts)."""
    moment = _as_time(time_s)
    period = _as_symbol_period(symbol_period_s)
    if moment >= 0 and moment < period:
        return Decimal(1)
    return Decimal(0)


def sinc_unit(offset: Decimal) -> Decimal:
    """sinc(u) = sin(pi*u)/(pi*u), sinc(0) = 1 (node-exact)."""
    if isinstance(offset, bool) or not isinstance(offset, Decimal):
        raise _fail(ControlStatus.INVALID, "sinc offset must be Decimal")
    if not offset.is_finite():
        raise _fail(ControlStatus.INVALID, "sinc offset must be finite")
    ctx = make_context()
    if offset == 0:
        return ctx.plus(Decimal(1))
    arg = ctx.multiply(decimal_pi(ctx), offset)
    return ctx.divide(decimal_sin(arg, ctx), arg)


def sinc_pulse(time_s: object, symbol_period_s: object) -> Decimal:
    """p(t) = sinc(t/Ts) with the node identity p(n*Ts) = delta[n]."""
    moment = _as_time(time_s)
    period = _as_symbol_period(symbol_period_s)
    ctx = make_context()
    return sinc_unit(ctx.divide(moment, period))


def raised_cosine(time_s: object, symbol_period_s: object, rolloff: object) -> Decimal:
    """RC: h(t) = sinc(t/Ts)*cos(pi*a*t/Ts)/(1-(2*a*t/Ts)^2).

    Closed limits: t = 0 -> 1; |2*a*t/Ts| = 1 (a > 0) ->
    (pi/4)*sinc(1/(2*a)) by L'Hopital (D-R1: the design-gate draft
    carried a spurious alpha factor; the alpha cancels in d/du of the
    denominator, proved numerically); a = 0 -> sinc branch.
    """
    moment = _as_time(time_s)
    period = _as_symbol_period(symbol_period_s)
    alpha = _as_rolloff(rolloff)
    ctx = make_context()
    if alpha == 0:
        return sinc_unit(ctx.divide(moment, period))
    if moment == 0:
        return ctx.plus(Decimal(1))
    scaled = ctx.divide(ctx.multiply(ctx.multiply(Decimal(2), alpha), moment), period)
    if scaled.copy_abs() == 1:
        half = ctx.divide(Decimal(1), ctx.multiply(Decimal(2), alpha))
        if scaled < 0:
            half = ctx.minus(half)
        limit = ctx.multiply(ctx.divide(decimal_pi(ctx), Decimal(4)),
                             sinc_unit(half))
        return limit
    unit = ctx.divide(moment, period)
    numer = ctx.multiply(sinc_unit(unit),
                         decimal_cos(ctx.multiply(ctx.multiply(decimal_pi(ctx), alpha),
                                                  unit), ctx))
    denom = ctx.subtract(Decimal(1), ctx.multiply(scaled, scaled))
    return ctx.divide(numer, denom)


def root_raised_cosine(time_s: object, symbol_period_s: object,
                       rolloff: object) -> Decimal:
    """RRC: h(t) = [sin(pi*x*(1-a)) + 4*a*x*cos(pi*x*(1+a))]
    /[pi*x*(1-(4*a*x)^2)], x = t/Ts.

    Closed limits: t = 0 -> 1 + a*(4/pi - 1); |4*a*x| = 1 (a > 0) ->
    N'(x0)/D'(x0) by L'Hopital; a = 0 -> sinc branch.
    """
    moment = _as_time(time_s)
    period = _as_symbol_period(symbol_period_s)
    alpha = _as_rolloff(rolloff)
    ctx = make_context()
    if alpha == 0:
        return sinc_unit(ctx.divide(moment, period))
    if moment == 0:
        four_over_pi = ctx.divide(Decimal(4), decimal_pi(ctx))
        return ctx.add(Decimal(1), ctx.multiply(alpha, ctx.subtract(four_over_pi,
                                                                   Decimal(1))))
    unit = ctx.divide(moment, period)
    four_ax = ctx.multiply(ctx.multiply(Decimal(4), alpha), unit)
    if four_ax.copy_abs() == 1:
        return _rrc_singular_limit(unit, alpha, ctx)
    pi = decimal_pi(ctx)
    numer = ctx.add(
        decimal_sin(ctx.multiply(ctx.multiply(pi, unit),
                                 ctx.subtract(Decimal(1), alpha)), ctx),
        ctx.multiply(ctx.multiply(ctx.multiply(Decimal(4), alpha), unit),
                     decimal_cos(ctx.multiply(ctx.multiply(pi, unit),
                                              ctx.add(Decimal(1), alpha)), ctx)))
    denom = ctx.multiply(ctx.multiply(pi, unit),
                         ctx.subtract(Decimal(1), ctx.multiply(four_ax, four_ax)))
    return ctx.divide(numer, denom)


def _rrc_singular_limit(unit: Decimal, alpha: Decimal, ctx) -> Decimal:
    """L'Hopital limit of the RRC form at |4*a*x| = 1 (a > 0)."""
    pi = decimal_pi(ctx)
    one_minus_a = ctx.subtract(Decimal(1), alpha)
    one_plus_a = ctx.add(Decimal(1), alpha)
    arg1 = ctx.multiply(ctx.multiply(pi, unit), one_minus_a)
    arg2 = ctx.multiply(ctx.multiply(pi, unit), one_plus_a)
    deriv_n = ctx.subtract(
        ctx.add(ctx.multiply(ctx.multiply(pi, one_minus_a),
                             decimal_cos(arg1, ctx)),
                ctx.multiply(ctx.multiply(Decimal(4), alpha),
                             decimal_cos(arg2, ctx))),
        ctx.multiply(ctx.multiply(ctx.multiply(ctx.multiply(Decimal(4), alpha),
                                                unit),
                                  ctx.multiply(pi, one_plus_a)),
                     decimal_sin(arg2, ctx)))
    ax2 = ctx.multiply(ctx.multiply(alpha, alpha), ctx.multiply(unit, unit))
    deriv_d = ctx.multiply(pi, ctx.subtract(Decimal(1),
                                            ctx.multiply(Decimal(48), ax2)))
    return ctx.divide(deriv_n, deriv_d)


def occupied_bandwidth(symbol_rate_hz: Decimal, rolloff: Decimal) -> Decimal:
    """Occupied baseband bandwidth B = (1 + a)*Rs/2 = (1 + a)/(2*Ts).

    Rs, Ts > 0 Decimals; alpha in [0, 1]. Result in Hz (label).
    """
    if isinstance(symbol_rate_hz, bool) or not isinstance(symbol_rate_hz, Decimal):
        raise _fail(ControlStatus.INVALID, "symbol rate must be Decimal")
    if not symbol_rate_hz.is_finite() or symbol_rate_hz <= 0:
        raise _fail(ControlStatus.INVALID, "symbol rate Rs > 0 required")
    alpha = _as_rolloff(rolloff)
    ctx = make_context()
    return ctx.divide(ctx.multiply(ctx.add(Decimal(1), alpha), symbol_rate_hz),
                      Decimal(2))


def check_lobes(lobes: object) -> int:
    """Truncated-sinc lobe budget in [1, 5000]; violations rejected."""
    if isinstance(lobes, bool) or not isinstance(lobes, int):
        raise _fail(ControlStatus.INVALID, "lobe budget must be int")
    if lobes < 1:
        raise _fail(ControlStatus.INVALID, "lobe budget >= 1 required")
    if lobes > MAX_LOBES:
        raise _fail(ControlStatus.INVALID, "lobe budget exceeded")
    return lobes
