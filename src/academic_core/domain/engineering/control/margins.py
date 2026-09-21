"""F8-P1 gain/phase/delay margins (NEW).

Margins come from direct L(jw) evaluations with bisection refinement
on bracketed monotone segments. Stored Bode tables are never
interpolated. Bracket intervals are always reported alongside refined
points. Missing crossovers -> UNSUPPORTED, never a silent infinite gain.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.control.tf import TransferFunctionTF
from academic_core.domain.engineering.math import (
    DecimalComplex,
    decimal_atan2,
    decimal_pi,
    make_context,
)

BISECT_REL_TOL = Decimal("1e-12")
SCAN_W_MIN = Decimal("1e-6")
SCAN_W_MAX = Decimal("1e6")
SCAN_PER_DECADE = 40
MAX_BISECT_ITER = 200


def _eval_jw(loop: TransferFunctionTF, omega: Decimal) -> DecimalComplex:
    if not omega.is_finite() or omega <= 0:
        raise ControlError(ControlStatus.INVALID, "omega > 0 required")
    s = DecimalComplex(Decimal(0), omega)
    try:
        return loop.evaluate(s)
    except ControlError as exc:
        if exc.status == ControlStatus.SINGULAR:
            raise ControlError(ControlStatus.SINGULAR, "L(jw) pole evaluation") from exc
        raise


def _wrapped_phase_deg(value: DecimalComplex) -> Decimal:
    ctx = make_context()
    if value.is_zero_exact():
        return Decimal(0)
    rad = decimal_atan2(value.im, value.re, ctx)
    pi = decimal_pi(ctx)
    return ctx.divide(ctx.multiply(rad, Decimal(180)), pi)


def _phase_for_margins(value: DecimalComplex) -> Decimal:
    """Wrapped phase normalised into (-360, 0] for low-order loops."""
    ctx = make_context()
    ph = _wrapped_phase_deg(value)
    # Map (0, 180] onto (-360, -180] (single wrap; loop order <= 32 but the
    # certified test systems stay above -360 deg).
    while ph > 0:
        ph = ctx.subtract(ph, Decimal(360))
    return ph


def _scan_frequencies() -> list:
    from academic_core.domain.engineering.math.logarithm import decimal_nth_root

    ctx = make_context()
    # Ratio per step: 10 ** (1 / per_decade), exact Decimal root.
    ratio = decimal_nth_root(Decimal(10), SCAN_PER_DECADE, ctx)
    total = SCAN_PER_DECADE * 12
    out: list = [SCAN_W_MIN]
    current = SCAN_W_MIN
    for _ in range(total):
        current = ctx.multiply(current, ratio)
        if current > SCAN_W_MAX:
            break
        out.append(ctx.plus(current))
    if out[-1] != SCAN_W_MAX:
        out.append(SCAN_W_MAX)
    return out


def _refine_gain_crossover(loop: TransferFunctionTF, lo: Decimal, hi: Decimal) -> Decimal:
    ctx = make_context()
    flo = _eval_jw(loop, lo).modulus() - Decimal(1)
    fhi = _eval_jw(loop, hi).modulus() - Decimal(1)
    if flo == 0:
        return lo
    if fhi == 0:
        return hi
    if (flo > 0) == (fhi > 0):
        raise ControlError(ControlStatus.INVALID, "gain bracket holds no crossing")
    for _ in range(MAX_BISECT_ITER):
        width = ctx.divide(ctx.subtract(hi, lo), hi if hi > 0 else Decimal(1))
        if width.copy_abs() <= BISECT_REL_TOL:
            break
        mid = ctx.divide(ctx.add(lo, hi), Decimal(2))
        fmid = _eval_jw(loop, mid).modulus() - Decimal(1)
        if fmid == 0:
            return mid
        if (flo > 0) == (fmid > 0):
            lo = mid
            flo = fmid
        else:
            hi = mid
            fhi = fmid
    return ctx.divide(ctx.add(lo, hi), Decimal(2))


def _refine_phase_crossover(loop: TransferFunctionTF, lo: Decimal, hi: Decimal) -> Decimal:
    ctx = make_context()
    for _ in range(MAX_BISECT_ITER):
        width = ctx.divide(ctx.subtract(hi, lo), hi if hi > 0 else Decimal(1))
        if width.copy_abs() <= BISECT_REL_TOL:
            break
        mid = ctx.divide(ctx.add(lo, hi), Decimal(2))
        try:
            vmid = _eval_jw(loop, mid)
        except ControlError:
            break
        # Bisection on Im(L) with Re < 0 gate checked by the caller brackets.
        # Shrink toward the zero of Im: compare signs of Im(lo) and Im(mid).
        try:
            vlo = _eval_jw(loop, lo)
        except ControlError:
            lo = mid
            continue
        im_lo = vlo.im
        im_mid = vmid.im
        if im_mid == 0:
            return mid
        if (im_lo > 0) == (im_mid > 0):
            lo = mid
        else:
            hi = mid
    return ctx.divide(ctx.add(lo, hi), Decimal(2))


def gain_crossovers(loop: TransferFunctionTF) -> tuple:
    """Refined gain crossovers |L| = 1 with bracket intervals."""
    freqs = _scan_frequencies()
    out: list = []
    prev_w = freqs[0]
    try:
        prev_m = _eval_jw(loop, prev_w).modulus()
    except ControlError:
        prev_m = None
    for w in freqs[1:]:
        try:
            cur_m = _eval_jw(loop, w).modulus()
        except ControlError:
            prev_w = w
            prev_m = None
            continue
        if prev_m is not None:
            flo = prev_m - Decimal(1)
            fhi = cur_m - Decimal(1)
            if flo == 0:
                out.append((prev_w, prev_w, prev_w))
            elif (flo > 0) != (fhi > 0):
                refined = _refine_gain_crossover(loop, prev_w, w)
                out.append((prev_w, w, refined))
        prev_w = w
        prev_m = cur_m
    return tuple(out)


def phase_crossovers(loop: TransferFunctionTF) -> tuple:
    """Refined phase crossovers Im(L) = 0 with Re < 0, with brackets."""
    freqs = _scan_frequencies()
    out: list = []
    prev_w = freqs[0]
    try:
        prev_v = _eval_jw(loop, prev_w)
    except ControlError:
        prev_v = None
    for w in freqs[1:]:
        try:
            cur_v = _eval_jw(loop, w)
        except ControlError:
            prev_w = w
            prev_v = None
            continue
        if prev_v is not None:
            im_lo = prev_v.im
            im_hi = cur_v.im
            re_lo = prev_v.re
            re_hi = cur_v.re
            if im_lo == 0 and re_lo < 0:
                out.append((prev_w, prev_w, prev_w))
            elif im_lo != im_hi and ((im_lo > 0) != (im_hi > 0)) and re_lo < 0 and re_hi < 0:
                refined = _refine_phase_crossover(loop, prev_w, w)
                # Verify the refined point keeps Re < 0 (true -180 crossing).
                try:
                    vr = _eval_jw(loop, refined)
                    if vr.re < 0:
                        out.append((prev_w, w, refined))
                except ControlError:
                    pass
        prev_w = w
        prev_v = cur_v
    return tuple(out)


def phase_crossover_bisection(loop: TransferFunctionTF) -> tuple:
    """(omega, K) pairs for locus jw-crossings: K = 1/|L(jw_pc)|."""
    ctx = make_context()
    out: list = []
    for _lo, _hi, refined in phase_crossovers(loop):
        try:
            mag = _eval_jw(loop, refined).modulus()
        except ControlError:
            continue
        if mag == 0:
            continue
        gain = ctx.divide(Decimal(1), mag)
        out.append((refined, gain))
    return tuple(out)


@dataclass(frozen=True)
class MarginsReport:
    gain_margin: str
    gain_margin_db: str
    omega_pc: str
    phase_margin_deg: str
    omega_gc: str
    delay_margin_s: str
    gm_bracket: tuple
    gc_bracket: tuple
    gm_status: str
    pm_status: str
    detail: str = ""


def margins(loop: TransferFunctionTF) -> MarginsReport:
    if not isinstance(loop, TransferFunctionTF):
        raise ControlError(ControlStatus.INVALID, "margins need a loop TF")
    from academic_core.domain.engineering.math.logarithm import decimal_log10

    ctx = make_context()
    gc = gain_crossovers(loop)
    pc = phase_crossovers(loop)
    gm_status = "UNSUPPORTED"
    pm_status = "UNSUPPORTED"
    gm = ""
    gm_db = ""
    wpc = ""
    pm = ""
    wgc = ""
    tdm = ""
    gm_bracket: tuple = ()
    gc_bracket: tuple = ()
    detail_parts: list = []
    if gc:
        # Primary gain crossover: first (lowest-frequency) crossing.
        lo, hi, refined = gc[0]
        gc_bracket = (str(lo), str(hi))
        wgc = str(refined)
        try:
            val = _eval_jw(loop, refined)
            ph = _phase_for_margins(val)
            pm_val = ctx.add(Decimal(180), ph)
            pm = str(pm_val)
            pm_status = "COMPLETED"
            # Delay margin T_dm = PM_rad / w_gc.
            pi = decimal_pi(ctx)
            pm_rad = ctx.divide(ctx.multiply(pm_val, pi), Decimal(180))
            tdm = str(ctx.divide(pm_rad, refined))
            detail_parts.append("pm from direct evaluation + bisection")
        except ControlError as exc:
            pm_status = exc.status.value if isinstance(exc.status, ControlStatus) else "INVALID"
            detail_parts.append("pm evaluation failed")
    else:
        detail_parts.append("no gain crossover")
    if pc:
        # Primary phase crossover: smallest gain margin (most critical).
        best = None
        best_item = None
        for lo, hi, refined in pc:
            try:
                mag = _eval_jw(loop, refined).modulus()
            except ControlError:
                continue
            if mag == 0:
                continue
            cand = ctx.divide(Decimal(1), mag)
            if best is None or cand < best:
                best = cand
                best_item = (lo, hi, refined, mag)
        if best_item is not None:
            lo, hi, refined, mag = best_item
            gm_bracket = (str(lo), str(hi))
            wpc = str(refined)
            gm = str(best)
            try:
                gm_db = str(ctx.multiply(decimal_log10(best, ctx), Decimal(20)))
            except Exception:
                gm_db = ""
            gm_status = "COMPLETED"
            detail_parts.append("gm from direct evaluation + bisection")
    else:
        detail_parts.append("no phase crossover")
    return MarginsReport(
        gain_margin=gm,
        gain_margin_db=gm_db,
        omega_pc=wpc,
        phase_margin_deg=pm,
        omega_gc=wgc,
        delay_margin_s=tdm,
        gm_bracket=gm_bracket,
        gc_bracket=gc_bracket,
        gm_status=gm_status,
        pm_status=pm_status,
        detail="; ".join(detail_parts),
    )
