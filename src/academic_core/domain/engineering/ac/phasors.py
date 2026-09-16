"""Phasor views for F8-D3 (cartesian preserved, derivatives explicit).

Solution phasors are always stored cartesian (Re, Im) as D1 numbers.
Magnitude and phase are DERIVED on demand through the D1
implementations (``modulus`` / ``phase``) — never ``math.atan2`` or
``cmath.phase`` in this core. Phase follows the D1 convention
(-pi, pi].

RMS appears only as a magnitude-domain conversion
(``rms_from_peak``); D3 builds no RMS power subsystem.
"""

from __future__ import annotations

from decimal import Decimal

from academic_core.domain.engineering.math.decimal_complex import DecimalComplex
from academic_core.domain.engineering.math.rational import RationalComplex
from academic_core.domain.engineering.math.trig import make_context

Phasor = RationalComplex | DecimalComplex


def magnitude(z: Phasor) -> Decimal:
    """|z| as Decimal (exact 0 stays 0; otherwise working precision)."""
    m = z.modulus()
    if isinstance(m, Decimal):
        return m
    ctx = make_context()
    return ctx.divide(Decimal(m.numerator), Decimal(m.denominator))


def phase(z: Phasor) -> Decimal:
    """Angle in radians, (-pi, pi], via the D1 implementation."""
    return z.phase() if isinstance(z, DecimalComplex) else _rational_phase(z)


def _rational_phase(z: RationalComplex) -> Decimal:
    """Phase of an exact phasor, explicitly approximate.

    Only axis-aligned exact phasors can reach EXACT AC results, so this
    helper maps the four axes (and zero) to exact multiples of pi/2 and
    refuses anything else: a non-axis phase in EXACT mode is a mode
    error raised earlier, never a silent approximation here.
    """
    from academic_core.domain.engineering.math.trig import decimal_pi

    if z.is_zero_exact():
        return Decimal(0)
    if z.im == 0:
        return Decimal(0) if z.re > 0 else decimal_pi()
    if z.re == 0:
        half = make_context().divide(decimal_pi(), Decimal(2))
        return half if z.im > 0 else make_context().minus(half)
    raise ValueError("non-axis exact phasor has no exact phase (mode error)")


def to_polar(z: Phasor) -> tuple[Decimal, Decimal]:
    """Return (|z|, angle_rad); cartesian original is never lost."""
    return magnitude(z), phase(z)


def rms_from_peak(peak_magnitude: Decimal) -> Decimal:
    """Vrms = Vpeak / sqrt(2) under the explicit working context.

    Magnitude-domain conversion only. The solver never sees RMS.
    """
    ctx = make_context()
    return ctx.divide(peak_magnitude, ctx.sqrt(Decimal(2)))


def fmt_cartesian(z: Phasor) -> str:
    """Deterministic cartesian rendering for provenance/diagnostics."""
    if isinstance(z, RationalComplex):
        return f"{z.re}+j*{z.im}"
    return f"{format(z.re, 'f')}+j*{format(z.im, 'f')}"
