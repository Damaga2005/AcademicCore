"""F8-P2 digital margins on the unit circle (NEW, thin solver).

Gain crossover |L(e^{jθ})| = 1 and phase crossover ∠L = −180° are found
by direct evaluation plus bisection — the P1 margin contract
reimplemented for the z-plane contour (same mathematics, no shared
solver code: the contour, scan, and report are digital-native).
Brackets are always reported; absent crossovers are UNSUPPORTED, never
a silent infinite gain. Warping note: digital margins are NOT bilinear
images of analog margins.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.dsp.ztrans import TransferFunctionZ
from academic_core.domain.engineering.math import (
    DecimalComplex,
    decimal_atan2,
    decimal_cos,
    decimal_pi,
    decimal_sin,
    make_context,
)
from academic_core.domain.engineering.math.logarithm import decimal_log10

DSP_BISECT_REL_TOL = Decimal("1e-12")
DSP_MAX_BISECT_ITER = 200
DSP_SCAN_POINTS = 720
DSP_ENDPOINT_TOL = Decimal("1e-12")


def _point_on_circle(theta: Decimal, ctx) -> DecimalComplex:
    return DecimalComplex(decimal_cos(theta, ctx), decimal_sin(theta, ctx))


def _eval_circle(loop: TransferFunctionZ, theta: Decimal) -> DecimalComplex:
    ctx = make_context()
    if isinstance(theta, bool) or not isinstance(theta, Decimal):
        raise ControlError(ControlStatus.INVALID, "circle angle must be Decimal")
    if not theta.is_finite() or theta < 0:
        raise ControlError(ControlStatus.INVALID, "circle angle in [0, pi] required")
    if theta > decimal_pi(ctx):
        raise ControlError(ControlStatus.INVALID, "circle angle in [0, pi] required")
    try:
        return loop.evaluate(_point_on_circle(theta, ctx))
    except ControlError as exc:
        if exc.status == ControlStatus.SINGULAR:
            raise ControlError(ControlStatus.SINGULAR, "L(e^{jth}) pole evaluation") from exc
        raise


def _phase_for_margins(value: DecimalComplex) -> Decimal:
    """Wrapped phase normalised into (-360, 0] (P1 single-wrap rule)."""
    ctx = make_context()
    if value.is_zero_exact():
        return Decimal(0)
    raw = decimal_atan2(value.im, value.re, ctx)
    half = ctx.divide(decimal_pi(ctx), Decimal(180))
    deg = ctx.divide(raw, half)
    while deg > 0:
        deg = ctx.subtract(deg, Decimal(360))
    return deg


def _scan_grid() -> tuple:
    ctx = make_context()
    pi = decimal_pi(ctx)
    return tuple(ctx.divide(ctx.multiply(pi, Decimal(i)), Decimal(DSP_SCAN_POINTS))
                 for i in range(DSP_SCAN_POINTS + 1))


def _refine_gain(loop: TransferFunctionZ, lo: Decimal, hi: Decimal) -> Decimal:
    ctx = make_context()
    flo = _eval_circle(loop, lo).modulus() - Decimal(1)
    fhi = _eval_circle(loop, hi).modulus() - Decimal(1)
    if flo == 0:
        return lo
    if fhi == 0:
        return hi
    if (flo > 0) == (fhi > 0):
        raise ControlError(ControlStatus.INVALID, "gain bracket holds no crossing")
    for _ in range(DSP_MAX_BISECT_ITER):
        width = ctx.divide(ctx.subtract(hi, lo), hi if hi > 0 else Decimal(1))
        if width.copy_abs() <= DSP_BISECT_REL_TOL:
            break
        mid = ctx.divide(ctx.add(lo, hi), Decimal(2))
        fmid = _eval_circle(loop, mid).modulus() - Decimal(1)
        if fmid == 0:
            return mid
        if (flo > 0) == (fmid > 0):
            lo = mid
            flo = fmid
        else:
            hi = mid
            fhi = fmid
    return ctx.divide(ctx.add(lo, hi), Decimal(2))


def _refine_phase(loop: TransferFunctionZ, lo: Decimal, hi: Decimal) -> Decimal:
    ctx = make_context()
    for _ in range(DSP_MAX_BISECT_ITER):
        width = ctx.divide(ctx.subtract(hi, lo), hi if hi > 0 else Decimal(1))
        if width.copy_abs() <= DSP_BISECT_REL_TOL:
            break
        mid = ctx.divide(ctx.add(lo, hi), Decimal(2))
        try:
            vmid = _eval_circle(loop, mid)
            vlo = _eval_circle(loop, lo)
        except ControlError:
            break
        if vmid.im == 0:
            return mid
        if (vlo.im > 0) == (vmid.im > 0):
            lo = mid
        else:
            hi = mid
    return ctx.divide(ctx.add(lo, hi), Decimal(2))


def gain_crossovers_d(loop: TransferFunctionZ) -> tuple:
    """Refined |L| = 1 crossings with bracket intervals."""
    grid = _scan_grid()
    out: list = []
    prev_t = grid[0]
    try:
        prev_m = _eval_circle(loop, prev_t).modulus()
    except ControlError:
        prev_m = None
    for theta in grid[1:]:
        try:
            cur_m = _eval_circle(loop, theta).modulus()
        except ControlError:
            prev_t = theta
            prev_m = None
            continue
        if prev_m is not None:
            flo = prev_m - Decimal(1)
            fhi = cur_m - Decimal(1)
            if flo == 0:
                out.append((prev_t, prev_t, prev_t))
            elif (flo > 0) != (fhi > 0):
                out.append((prev_t, theta, _refine_gain(loop, prev_t, theta)))
        prev_t = theta
        prev_m = cur_m
    _append_gain_endpoint(loop, grid, out)
    return tuple(out)


def _append_gain_endpoint(loop: TransferFunctionZ, grid: tuple, out: list) -> None:
    """Endpoint rule: a crossover touching θ = 0 or θ = π has no interior
    bracket; accept |L| = 1 exactly there (exact Decimal equality)."""
    ctx = make_context()
    for end in (grid[0], grid[-1]):
        try:
            mag = _eval_circle(loop, end).modulus()
        except ControlError:
            continue
        _ = ctx
        if mag - Decimal(1) == 0 and not any(r == end for _, _, r in out):
            out.append((end, end, end))


def phase_crossovers_d(loop: TransferFunctionZ) -> tuple:
    """Refined Im(L) = 0 crossings with Re < 0, with brackets."""
    grid = _scan_grid()
    out: list = []
    prev_t = grid[0]
    try:
        prev_v = _eval_circle(loop, prev_t)
    except ControlError:
        prev_v = None
    for theta in grid[1:]:
        try:
            cur_v = _eval_circle(loop, theta)
        except ControlError:
            prev_t = theta
            prev_v = None
            continue
        if prev_v is not None:
            if prev_v.im == 0 and prev_v.re < 0:
                out.append((prev_t, prev_t, prev_t))
            elif (prev_v.im > 0) != (cur_v.im > 0) and prev_v.re < 0 and cur_v.re < 0:
                refined = _refine_phase(loop, prev_t, theta)
                try:
                    if _eval_circle(loop, refined).re < 0:
                        out.append((prev_t, theta, refined))
                except ControlError:
                    pass
        prev_t = theta
        prev_v = cur_v
    _append_phase_endpoint(loop, grid, out)
    return tuple(out)


def _append_phase_endpoint(loop: TransferFunctionZ, grid: tuple, out: list) -> None:
    """Endpoint rule: Im(L) vanishes at θ = 0/π up to trig dust for real
    loops; accept the crossover when Re < 0 and
    |Im| ≤ 1e-12·max(1, |L|) (documented endpoint tolerance)."""
    ctx = make_context()
    for end in (grid[0], grid[-1]):
        try:
            val = _eval_circle(loop, end)
        except ControlError:
            continue
        cap = Decimal(1) if val.modulus() < 1 else val.modulus()
        bound = ctx.multiply(DSP_ENDPOINT_TOL, cap)
        if val.re < 0 and val.im.copy_abs() <= bound:
            if not any(r == end for _, _, r in out):
                out.append((end, end, end))


@dataclass(frozen=True)
class DigitalMarginsReport:
    gain_margin: str
    gain_margin_db: str
    theta_pc: str
    phase_margin_deg: str
    theta_gc: str
    delay_margin_samples: str
    delay_margin_s: str
    gm_bracket: tuple
    gc_bracket: tuple
    gm_status: str
    pm_status: str
    detail: str = ""


def digital_margins(loop: TransferFunctionZ, period: object) -> DigitalMarginsReport:
    if not isinstance(loop, TransferFunctionZ):
        raise ControlError(ControlStatus.INVALID, "digital margins need a loop H(z)")
    if isinstance(period, bool):
        raise ControlError(ControlStatus.INVALID, "period rejects bool")
    t_step = period if isinstance(period, Decimal) else None
    if t_step is None:
        try:
            t_step = Decimal(str(period))
        except Exception as exc:
            raise ControlError(ControlStatus.INVALID, "period must be numeric") from exc
    if not t_step.is_finite() or t_step <= 0:
        raise ControlError(ControlStatus.INVALID, "period T > 0 required")
    ctx = make_context()
    gc = gain_crossovers_d(loop)
    pc = phase_crossovers_d(loop)
    gm_status = "UNSUPPORTED"
    pm_status = "UNSUPPORTED"
    gm = gm_db = wpc = pm = wgc = tdm_n = tdm_s = ""
    gm_bracket: tuple = ()
    gc_bracket: tuple = ()
    detail: list = []
    if gc:
        lo, hi, refined = gc[0]
        gc_bracket = (str(lo), str(hi))
        wgc = str(refined)
        try:
            val = _eval_circle(loop, refined)
            pm_val = ctx.add(Decimal(180), _phase_for_margins(val))
            pm = str(pm_val)
            pm_status = "COMPLETED"
            if refined == 0:
                detail.append("delay undefined at zero-frequency crossover")
            else:
                tau_n = ctx.divide(
                    ctx.divide(ctx.multiply(pm_val, decimal_pi(ctx)), Decimal(180)),
                    refined)
                tdm_n = str(tau_n)
                tdm_s = str(ctx.multiply(tau_n, t_step))
                detail.append("pm from direct evaluation + bisection")
        except ControlError as exc:
            pm_status = exc.status.value if isinstance(exc.status, ControlStatus) else "INVALID"
            detail.append("pm evaluation failed")
    else:
        detail.append("no gain crossover")
    if pc:
        best = None
        best_item = None
        for lo, hi, refined in pc:
            try:
                mag = _eval_circle(loop, refined).modulus()
            except ControlError:
                continue
            if mag == 0:
                continue
            cand = ctx.divide(Decimal(1), mag)
            if best is None or cand < best:
                best = cand
                best_item = (lo, hi, refined)
        if best_item is not None:
            lo, hi, refined = best_item
            gm_bracket = (str(lo), str(hi))
            wpc = str(refined)
            gm = str(best)
            try:
                gm_db = str(ctx.multiply(decimal_log10(best, ctx), Decimal(20)))
            except Exception:
                gm_db = ""
            gm_status = "COMPLETED"
            detail.append("gm from direct evaluation + bisection")
    else:
        detail.append("no phase crossover")
    return DigitalMarginsReport(
        gain_margin=gm, gain_margin_db=gm_db, theta_pc=wpc,
        phase_margin_deg=pm, theta_gc=wgc, delay_margin_samples=tdm_n,
        delay_margin_s=tdm_s, gm_bracket=gm_bracket, gc_bracket=gc_bracket,
        gm_status=gm_status, pm_status=pm_status, detail="; ".join(detail))
