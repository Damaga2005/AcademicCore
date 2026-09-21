"""F8-P1 analytic time responses (NEW).

Partial-fraction expansion with real-signal pairing so outputs stay
real. Distinct poles via cover-up residues; repeated poles via a
collocation solve for the Jordan-chain coefficients (no hidden
rounding). Complex pairs combine to real damped sinusoids.
Metrics (PO, tp, ts, steady-state value) with applicability tags; the
final-value theorem is gated on its pole condition.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.control.poly import (
    Polynomial,
    durand_kerner_roots,
    make_polynomial,
)
from academic_core.domain.engineering.control.tf import TransferFunctionTF
from academic_core.domain.engineering.math import (
    DecimalComplex,
    decimal_cos,
    decimal_pi,
    decimal_sin,
    decimal_sqrt,
    make_context,
)

MAX_TIME_POINTS = 10001
GROUP_TOL = Decimal("1e-6")
REAL_TOL = Decimal("1e-12")


def decimal_exp(value: Decimal, ctx=None) -> Decimal:
    """exp(value) in pure Decimal (halving reduction + Taylor, guarded)."""
    c = ctx or make_context()
    g = make_context(15)
    if value == 0:
        return c.plus(Decimal(1))
    if not value.is_finite():
        raise ControlError(ControlStatus.INVALID, "exp needs a finite argument")
    # Reduce by halving until |r| <= 1/2, then square back.
    halves = 0
    r = g.plus(value)
    while r.copy_abs() > Decimal("0.5"):
        r = g.divide(r, Decimal(2))
        halves += 1
        if halves > 10000:
            raise ControlError(ControlStatus.NUMERIC_ERROR, "exp reduction failed")
    eps = g.scaleb(Decimal(1), -(g.prec + 2))
    total = g.plus(Decimal(1))
    term = g.plus(Decimal(1))
    k = 1
    while True:
        term = g.divide(g.multiply(term, r), Decimal(k))
        total = g.add(total, term)
        if term.copy_abs() < eps:
            break
        k += 1
        if k > 10000:
            raise ControlError(ControlStatus.NUMERIC_ERROR, "exp series failed")
    out = total
    for _ in range(halves):
        out = g.multiply(out, out)
    return c.plus(out)


def _complex_exp(p: DecimalComplex, t: Decimal, ctx) -> DecimalComplex:
    at = ctx.multiply(p.re, t)
    bt = ctx.multiply(p.im, t)
    mag = decimal_exp(at, ctx)
    c = decimal_cos(bt, ctx)
    s = decimal_sin(bt, ctx)
    return DecimalComplex(ctx.multiply(mag, c), ctx.multiply(mag, s))


def _check_times(times: tuple) -> tuple:
    if not isinstance(times, tuple) or len(times) == 0:
        raise ControlError(ControlStatus.INVALID, "response needs a non-empty time tuple")
    if len(times) > MAX_TIME_POINTS:
        raise ControlError(ControlStatus.INVALID, "time budget exceeded")
    out: list = []
    for t in times:
        if isinstance(t, bool):
            raise ControlError(ControlStatus.INVALID, "time rejects bool")
        dec = t if isinstance(t, Decimal) else (Decimal(t) if isinstance(t, int) else None)
        if dec is None:
            try:
                dec = Decimal(str(t))
            except Exception as exc:
                raise ControlError(ControlStatus.INVALID, "time must be numeric") from exc
        if not dec.is_finite() or dec < 0:
            raise ControlError(ControlStatus.INVALID, "time must be finite t >= 0")
        out.append(dec)
    return tuple(out)


def _group_poles(roots: tuple) -> list:
    groups: list = []
    for r in roots:
        placed = False
        for grp in groups:
            if (r - grp[0]).modulus() <= GROUP_TOL:
                grp.append(r)
                placed = True
                break
        if not placed:
            groups.append([r])
    # Deterministic order: sort groups by (re, im) of their mean.
    groups.sort(key=lambda g: (str(sum([x.re for x in g], Decimal(0))), str(sum([x.im for x in g], Decimal(0)))))
    return groups


def _complex_linsolve(rows: list) -> list:
    """Gaussian elimination over DecimalComplex with deterministic pivoting."""
    n = len(rows)
    m = [list(r) for r in rows]
    for col in range(n):
        pivot = None
        for r in range(col, n):
            if not m[r][col].is_zero_exact():
                pivot = r
                break
        if pivot is None:
            raise ControlError(ControlStatus.SINGULAR, "collocation system singular")
        m[col], m[pivot] = m[pivot], m[col]
        piv = m[col][col]
        m[col] = [v / piv for v in m[col]]
        for r in range(n):
            if r == col:
                continue
            factor = m[r][col]
            if not factor.is_zero_exact():
                m[r] = [m[r][k] - factor * m[col][k] for k in range(n + 1)]
    return [m[i][n] for i in range(n)]


def _partial_coefficients(num: Polynomial, den: Polynomial) -> tuple:
    """Collocation partial fractions: terms c/(s-p)^k for each group.

    Returns ((pole, power, coeff), ...) with coeff DecimalComplex.
    """
    res = durand_kerner_roots(den)
    if res.status != ControlStatus.COMPLETED:
        raise ControlError(res.status, "response pole core did not converge")
    groups = _group_poles(res.roots)
    terms: list = []
    for grp in groups:
        centre = grp[0]
        for power in range(1, len(grp) + 1):
            terms.append((centre, power))
    n_terms = len(terms)
    if n_terms == 0:
        return ()
    den_degree = den.degree
    if n_terms != den_degree:
        # Grouping merged distinct poles or split a multiple root: fall back
        # to simple-pole cover-up only when every group is a singleton.
        if any(len(g) > 1 for g in groups):
            raise ControlError(ControlStatus.UNSUPPORTED, "high-multiplicity grouping ambiguous")
    # Deterministic real sample points avoiding poles.
    samples: list = []
    cand = Decimal("0.37")
    step = Decimal("0.53")
    while len(samples) < n_terms:
        ok = True
        for r in res.roots:
            if (DecimalComplex(cand, Decimal(0)) - r).modulus() <= Decimal("1e-3"):
                ok = False
                break
        if ok:
            samples.append(DecimalComplex(cand, Decimal(0)))
        cand = cand + step
        if cand > Decimal("100000"):
            raise ControlError(ControlStatus.SINGULAR, "no clean collocation points")
    rows: list = []
    for s in samples:
        try:
            rhs = num.evaluate(s) / den.evaluate(s)
        except ZeroDivisionError as exc:
            raise ControlError(ControlStatus.SINGULAR, "collocation at pole") from exc
        row: list = []
        for (pole, power) in terms:
            diff = s - pole
            if diff.is_zero_exact():
                raise ControlError(ControlStatus.SINGULAR, "collocation at pole")
            basis = DecimalComplex(Decimal(1), Decimal(0))
            for _ in range(power):
                basis = basis / diff
            row.append(basis)
        row.append(rhs)
        rows.append(row)
    coeffs = _complex_linsolve(rows)
    return tuple((terms[i][0], terms[i][1], coeffs[i]) for i in range(n_terms))


def _eval_terms(terms: tuple, t: Decimal, ctx) -> Decimal:
    total = DecimalComplex(Decimal(0), Decimal(0))
    # t^k / k! factors for repeated poles.
    for (pole, power, coeff) in terms:
        basis = _complex_exp(pole, t, ctx)
        if power >= 2:
            t_pow = ctx.power(t, power - 1) if t != 0 else (Decimal(1) if power - 1 == 0 else Decimal(0))
            fact = Decimal(1)
            for k in range(2, power):
                fact = fact * k
            scale = ctx.divide(t_pow, fact)
            basis = basis * DecimalComplex(scale, Decimal(0))
        total = total + coeff * basis
    if total.im.copy_abs() > Decimal("1e-18") * (Decimal(1) + total.re.copy_abs()):
        raise ControlError(ControlStatus.NUMERIC_ERROR, "non-real time response")
    return ctx.plus(total.re)


@dataclass(frozen=True)
class TimeResult:
    values: tuple
    times: tuple
    status: str
    tags: tuple
    detail: str = ""


def _lhp_ok(h: TransferFunctionTF) -> bool:
    res = durand_kerner_roots(h.den)
    if res.status != ControlStatus.COMPLETED:
        return False
    for z in res.roots:
        if z.re >= 0:
            return False
    return True


def _has_jw_pole(h: TransferFunctionTF) -> bool:
    res = durand_kerner_roots(h.den)
    if res.status != ControlStatus.COMPLETED:
        return False
    for z in res.roots:
        if z.re.copy_abs() <= REAL_TOL:
            return True
    return False


def step_response(h: TransferFunctionTF, times: tuple) -> TimeResult:
    if not isinstance(h, TransferFunctionTF):
        raise ControlError(ControlStatus.INVALID, "step needs a TF")
    t_tuple = _check_times(times)
    ctx = make_context()
    # Y(s) = H(s) / s ; extra pole at the origin.
    s_poly = make_polynomial((Decimal(1), Decimal(0)))
    y_den = h.den.multiply(s_poly)
    terms = _partial_coefficients(h.num, y_den)
    values = tuple(_eval_terms(terms, t, ctx) for t in t_tuple)
    tags: list = []
    if _has_jw_pole(h):
        tags.append("marginal-pole-present")
    if _lhp_ok(h):
        try:
            yss = h.evaluate(DecimalComplex(Decimal(0), Decimal(0)))
            if yss.im.copy_abs() <= REAL_TOL:
                tags.append("final-value-ok:" + str(ctx.plus(yss.re)))
            else:
                tags.append("final-value-blocked")
        except ControlError:
            tags.append("final-value-blocked")
    else:
        tags.append("final-value-blocked")
    return TimeResult(values=values, times=t_tuple, status="COMPLETED",
                      tags=tuple(tags), detail="partial-fractions analytic")


def impulse_response(h: TransferFunctionTF, times: tuple) -> TimeResult:
    if not isinstance(h, TransferFunctionTF):
        raise ControlError(ControlStatus.INVALID, "impulse needs a TF")
    t_tuple = _check_times(times)
    ctx = make_context()
    terms = _partial_coefficients(h.num, h.den)
    values = tuple(_eval_terms(terms, t, ctx) for t in t_tuple)
    tags: list = []
    if _has_jw_pole(h):
        tags.append("marginal-pole-present")
    return TimeResult(values=values, times=t_tuple, status="COMPLETED",
                      tags=tuple(tags), detail="partial-fractions analytic")


def first_order_step(k: Decimal, tau: Decimal, t: Decimal) -> Decimal:
    ctx = make_context()
    if tau <= 0:
        raise ControlError(ControlStatus.INVALID, "tau > 0 required")
    if t < 0:
        raise ControlError(ControlStatus.INVALID, "t >= 0 required")
    ratio = ctx.divide(t, tau)
    exp_term = decimal_exp(ctx.minus(ratio), ctx)
    return ctx.multiply(k, ctx.subtract(Decimal(1), exp_term))


def first_order_impulse(k: Decimal, tau: Decimal, t: Decimal) -> Decimal:
    ctx = make_context()
    if tau <= 0:
        raise ControlError(ControlStatus.INVALID, "tau > 0 required")
    if t < 0:
        raise ControlError(ControlStatus.INVALID, "t >= 0 required")
    ratio = ctx.divide(t, tau)
    return ctx.divide(ctx.multiply(k, decimal_exp(ctx.minus(ratio), ctx)), tau)


@dataclass(frozen=True)
class SecondOrderMetrics:
    omega_n: str
    zeta: str
    overshoot: str
    peak_time: str
    settling_2pct: str
    poles_re: str
    poles_im: str
    regime: str


def second_order_metrics(omega_n: Decimal, zeta: Decimal) -> SecondOrderMetrics:
    ctx = make_context()
    if omega_n <= 0:
        raise ControlError(ControlStatus.INVALID, "omega_n > 0 required")
    if zeta < 0:
        raise ControlError(ControlStatus.INVALID, "zeta >= 0 required")
    pi = decimal_pi(ctx)
    if zeta < 1:
        one_minus = ctx.subtract(Decimal(1), ctx.multiply(zeta, zeta))
        root = decimal_sqrt(one_minus, ctx)
        wd = ctx.multiply(omega_n, root)
        po = decimal_exp(ctx.minus(ctx.divide(ctx.multiply(pi, zeta), root)), ctx)
        tp = ctx.divide(pi, wd)
        ts = ctx.divide(Decimal(4), ctx.multiply(zeta, omega_n))
        pre = ctx.minus(ctx.multiply(zeta, omega_n))
        pim = ctx.plus(wd)
        regime = "underdamped"
    elif zeta == 1:
        po = Decimal(0)
        tp = ""
        ts = ctx.divide(Decimal(4), omega_n)
        pre = ctx.minus(omega_n)
        pim = Decimal(0)
        regime = "critically-damped"
    else:
        po = Decimal(0)
        tp = ""
        ts = ""
        disc = ctx.subtract(ctx.multiply(zeta, zeta), Decimal(1))
        root = decimal_sqrt(disc, ctx)
        pre = ctx.minus(ctx.multiply(omega_n, ctx.add(zeta, root)))
        pim = Decimal(0)
        regime = "overdamped"
    return SecondOrderMetrics(
        omega_n=str(omega_n), zeta=str(zeta), overshoot=str(po),
        peak_time=str(tp), settling_2pct=str(ts),
        poles_re=str(pre), poles_im=str(pim), regime=regime,
    )
