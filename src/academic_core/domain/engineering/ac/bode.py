"""Log-frequency (Bode) response analysis over D5 sweeps (F8-D6).

Pure post-processing of :class:`SweepResult`: no solves happen here, so
a second solver is impossible by construction. Consumes D5 values
read-only; never mutates circuits, solutions, sweeps or inputs.

Contents:

* log grids ``f_k = f_start * r^k``, ``r = 10**(1/ppd)`` (explicit
  Decimal ratio from ``math.logarithm``; repeated-multiply accumulation,
  documented and deterministic);
* dB magnitudes ``20*log10|H|`` with an explicit ``NEGATIVE_INFINITY_DB``
  category for exact-zero magnitude (no ``Decimal("Infinity")`` stored);
* deterministic phase unwrap (minimize |step|, integer offsets; exact
  tie-break chain; segments restart at every invalid point — never
  unwrapped across, never interpolated, never smoothed);
* cutoff brackets (index-adjacent valid samples straddling a threshold;
  exact hits reported, never interpolated, never root-found);
* bandwidth as an interval from flanking brackets, DEFINED only with
  two established boundaries (no 0 Hz anchoring: sweeps never include
  DC), all above-threshold bands reported (never silently dropped);
* observed discrete extrema (strict/flat/endpoint, never continuous
  claims) and reactance-zero brackets (candidates only);
* resonance verdicts, Q, poles/zeros, filters, Bode plots: NOT HERE.

Transfer kinds get the full level-metric treatment; impedance/
admittance kinds get dB/unwrap/extrema/reactance-brackets (bandwidth is
a transfer concept and is reported UNDEFINED for Z/Y with its reason).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN
from enum import Enum

from academic_core.domain.engineering.ac.impedance import ImpedanceError
from academic_core.domain.engineering.ac.phasors import (
    magnitude as phasor_magnitude,
)
from academic_core.domain.engineering.ac.phasors import phase as phasor_phase
from academic_core.domain.engineering.math.decimal_complex import DecimalComplex
from academic_core.domain.engineering.math.logarithm import (
    WORKING_PRECISION,
    decimal_log10,
    decimal_nth_root,
    make_context,
)
ENGINE_VERSION = "f8d-ac-bode/1.0"

_GUARD_DIGITS = 15


class BodeError(ValueError):
    """Misuse of the D6 Bode layer (bad grid params, wrong types, empty
    inputs where data is required). Physical/solver states travel as
    data on the result types, never as exceptions."""


# -- frequency handling -----------------------------------------------------

def _base_hz(quantity) -> Decimal:
    """Base-Hz value under an explicit context (never ambient rounding)."""
    ctx = make_context(_GUARD_DIGITS)
    return ctx.multiply(quantity.value, quantity.unit.factor)


def canonical_frequency_key(quantity) -> str:
    """Deterministic identity for one frequency: normalized base-Hz.

    ``1000 Hz``, ``1 kHz`` and ``1000.0 Hz`` share one key (same physics,
    same key); distinct values never collide. Normalization runs under an
    explicit guard context so long digit strings are never rounded by an
    ambient precision.
    """
    ctx = make_context(_GUARD_DIGITS)
    return format(_base_hz(quantity).normalize(ctx), "f")


def _hz_quantity(value: Decimal):
    from academic_core.domain.engineering.units import Quantity, parse_unit

    return Quantity(value, parse_unit("Hz"))


def log_frequencies(start, ppd: int, n: int) -> list:
    """Deterministic log grid: ``f_k = f_start * r^k``, ``r = 10**(1/ppd)``.

    ``start`` is Hz (Quantity|str, ``f > 0``); ``ppd >= 1`` integer points
    per decade; ``n >= 1`` integer count. ``n == 1`` yields ``[start]``.
    Ratio and accumulation use explicit contexts only. Strictly
    increasing (``r > 1`` always): no duplicates by construction.
    """
    from academic_core.domain.engineering.units import (
        FREQUENCY,
        Quantity,
        parse_quantity,
    )

    q = parse_quantity(start) if isinstance(start, str) else start
    if not isinstance(q, Quantity) or q.dimension != FREQUENCY:
        raise BodeError(f"log grid start must be Hz, got {start!r}")
    if q.to_base() <= 0:
        raise BodeError(f"log grid start must be f > 0, got {start!r}")
    if isinstance(ppd, bool) or not isinstance(ppd, int) or ppd < 1:
        raise BodeError(f"points-per-decade must be an integer >= 1, got {ppd!r}")
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise BodeError(f"point count must be an integer >= 1, got {n!r}")
    ctx = make_context()
    g = make_context(_GUARD_DIGITS)
    start_base = _base_hz(q)
    if n == 1:
        return [q]
    ratio = decimal_nth_root(Decimal(10), ppd, g)
    ratio = ctx.plus(ratio)
    out = [q]
    current = start_base
    for _ in range(n - 1):
        current = ctx.multiply(current, ratio)
        out.append(_hz_quantity(current))
    return out


# -- dB magnitude ------------------------------------------------------------

class DecibelCategory(Enum):
    FINITE = "finite"
    NEGATIVE_INFINITY_DB = "negative_infinity_db"


@dataclass(frozen=True)
class MagnitudeResult:
    category: DecibelCategory
    value: Decimal | None  # dB; None exactly when linear == 0
    linear: Decimal  # |H| >= 0 always

    def require_finite(self) -> Decimal:
        if self.category != DecibelCategory.FINITE or self.value is None:
            raise BodeError("dB value is negative-infinity (zero magnitude)")
        return self.value

    def to_dict(self) -> dict:
        return {
            "category": self.category.value,
            "value": None if self.value is None else str(self.value),
            "linear": str(self.linear),
        }


def magnitude_db(linear: Decimal | int) -> MagnitudeResult:
    """``20*log10|H|`` under an explicit context; exact zero maps to the
    ``NEGATIVE_INFINITY_DB`` category (never a stored infinity)."""
    from academic_core.domain.engineering.math.logarithm import _as_decimal

    mag = _as_decimal(linear)
    if mag < 0:
        raise BodeError(f"magnitude must be >= 0, got {linear!r}")
    if mag == 0:
        return MagnitudeResult(DecibelCategory.NEGATIVE_INFINITY_DB, None, mag)
    ctx = make_context()
    return MagnitudeResult(
        DecibelCategory.FINITE,
        ctx.multiply(Decimal(20), decimal_log10(mag, ctx)),
        mag,
    )


def half_power_threshold_db(reference_db: Decimal) -> Decimal:
    """Half-power (−3 dB family) threshold: ``ref − 10*log10(2)``.

    The constant is ``10*log10(2) ≈ 3.0103`` computed in Decimal — never
    a rounded ``3.0`` literal.
    """
    from academic_core.domain.engineering.math.logarithm import _as_decimal

    ctx = make_context()
    ref = _as_decimal(reference_db)
    return ctx.subtract(ref, ctx.multiply(Decimal(10), decimal_log10(Decimal(2), ctx)))


# -- phase unwrap --------------------------------------------------------------

def _two_pi(ctx=None):
    from academic_core.domain.engineering.math.trig import decimal_pi

    c = ctx or make_context(_GUARD_DIGITS)
    return c.multiply(Decimal(2), decimal_pi(c))


def unwrap_phases(phases: list[Decimal | None]) -> tuple[list, list]:
    """Deterministic unwrap of wrapped (−π,π] phases with invalid gaps.

    Rule: ``u_0`` equals the first valid phase (offset 0); each later
    valid ``φ`` takes ``φ + 2πn`` minimizing ``|φ + 2πn − u_prev|``
    (search over the rounded estimate ±2 always contains the true
    minimizer); exact ties break toward the smaller resulting cumulative
    offset, then toward smaller ``n``. Invalid (``None``) points stay
    ``None`` and open a new segment — never unwrapped across, never
    interpolated, never smoothed.

    Returns ``(unwrapped, segments)`` where segments are inclusive
    ``(start, end)`` index ranges of maximal valid runs.
    """
    g = make_context(_GUARD_DIGITS)
    two_pi = _two_pi(g)
    out: list = [None] * len(phases)
    segments: list[tuple[int, int]] = []
    prev_u: Decimal | None = None
    prev_off = 0
    seg_start: int | None = None
    for i, phi in enumerate(phases):
        if phi is None:
            if seg_start is not None:
                segments.append((seg_start, i - 1))
                seg_start = None
            prev_u = None
            continue
        if prev_u is None:
            out[i] = g.plus(phi)
            prev_u = out[i]
            prev_off = 0
            seg_start = i if seg_start is None else seg_start
            continue
        est = g.divide(g.subtract(prev_u, phi), two_pi)
        n0 = int(est.to_integral_value(rounding=ROUND_HALF_EVEN))
        best = None
        for n in (n0 - 2, n0 - 1, n0, n0 + 1, n0 + 2):
            cand = g.add(phi, g.multiply(two_pi, Decimal(n)))
            dist = abs(g.subtract(cand, prev_u))
            key = (dist, abs(prev_off + n), n)
            if best is None or (key[0] < best[0] or (
                    key[0] == best[0] and (key[1], key[2]) < (best[1], best[2]))):
                best = (dist, abs(prev_off + n), n, cand)
        assert best is not None
        out[i] = best[3]
        prev_u = best[3]
        prev_off = prev_off + best[2]
    if seg_start is not None:
        segments.append((seg_start, len(phases) - 1))
    return out, segments


# -- crossings / cutoffs ---------------------------------------------------------

@dataclass(frozen=True)
class CutoffBracket:
    label: str  # cutoff | reactance-zero-candidate
    lo_index: int
    hi_index: int  # == lo_index for an exact sample hit
    lo_freq: str  # canonical keys
    hi_freq: str
    lo_value: str
    hi_value: str
    threshold: str

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "lo_index": self.lo_index,
            "hi_index": self.hi_index,
            "lo_freq": self.lo_freq,
            "hi_freq": self.hi_freq,
            "lo_value": self.lo_value,
            "hi_value": self.hi_value,
            "threshold": self.threshold,
        }


def crossing_brackets(freq_keys: list[str], values: list[Decimal | None],
                       threshold: Decimal, label: str = "cutoff"
                       ) -> list[CutoffBracket]:
    """Brackets over index-adjacent VALID pairs straddling ``threshold``.

    A sample exactly equal to the threshold satisfies it: reported as a
    zero-width bracket ``(i, i)``. Pairs touching an invalid sample are
    never bridged. Nothing is interpolated; no root finding runs.
    """
    if len(freq_keys) != len(values):
        raise BodeError("frequencies and values must align")
    out: list[CutoffBracket] = []
    for i in range(len(values) - 1):
        a, b = values[i], values[i + 1]
        if a is None or b is None:
            continue
        da, db = a - threshold, b - threshold
        if da == 0 and db == 0:
            continue  # flat run on the threshold is not a crossing
        if da == 0:
            out.append(CutoffBracket(label, i, i, freq_keys[i], freq_keys[i],
                                     str(a), str(b), str(threshold)))
        elif db == 0:
            out.append(CutoffBracket(label, i + 1, i + 1, freq_keys[i + 1],
                                     freq_keys[i + 1], str(a), str(b),
                                     str(threshold)))
        elif (da > 0) != (db > 0):
            out.append(CutoffBracket(label, i, i + 1, freq_keys[i],
                                     freq_keys[i + 1], str(a), str(b),
                                     str(threshold)))
    return out


# -- bands / bandwidth -------------------------------------------------------------

@dataclass(frozen=True)
class PassBand:
    start_index: int
    end_index: int
    lo: CutoffBracket | None  # None -> open side, see reason
    hi: CutoffBracket | None
    bandwidth_lo: Decimal | None  # interval [lo, hi]; None unless defined
    bandwidth_hi: Decimal | None
    defined: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "start_index": self.start_index,
            "end_index": self.end_index,
            "lo": None if self.lo is None else self.lo.to_dict(),
            "hi": None if self.hi is None else self.hi.to_dict(),
            "bandwidth_lo": None if self.bandwidth_lo is None else str(self.bandwidth_lo),
            "bandwidth_hi": None if self.bandwidth_hi is None else str(self.bandwidth_hi),
            "defined": self.defined,
            "reason": self.reason,
        }


def _freq_base_decimals(freqs) -> list[Decimal]:
    return [_base_hz(f) for f in freqs]


def threshold_bands(freqs, values: list[Decimal | None],
                    threshold: Decimal) -> list[PassBand]:
    """All maximal above-threshold (``>=``) runs with boundary brackets.

    Bands are never silently dropped: every run is reported. Bandwidth
    is DEFINED only with two established flanking brackets, as the
    rigorous interval ``[hi.lo_f − lo.hi_f, hi.hi_f − lo.lo_f]``; a run
    touching a sweep edge or a validity gap stays UNDEFINED with its
    reason (never anchored to 0 Hz: sweeps never include DC).
    """
    from academic_core.domain.engineering.math.trig import make_context as _mc

    ctx = _mc()
    if len(freqs) != len(values):
        raise BodeError("frequencies and values must align")
    bases = _freq_base_decimals(freqs)
    n = len(values)
    runs: list[tuple[int, int]] = []
    i = 0
    while i < n:
        if values[i] is None or values[i] < threshold:
            i += 1
            continue
        j = i
        while j + 1 < n and values[j + 1] is not None and values[j + 1] >= threshold:
            j += 1
        runs.append((i, j))
        i = j + 1
    out: list[PassBand] = []
    for (a, b) in runs:
        lo = hi = None
        if a > 0 and values[a - 1] is not None:
            lo = CutoffBracket("cutoff", a - 1, a,
                               canonical_frequency_key(freqs[a - 1]),
                               canonical_frequency_key(freqs[a]),
                               str(values[a - 1]), str(values[a]), str(threshold))
        if b + 1 < n and values[b + 1] is not None:
            hi = CutoffBracket("cutoff", b, b + 1,
                               canonical_frequency_key(freqs[b]),
                               canonical_frequency_key(freqs[b + 1]),
                               str(values[b]), str(values[b + 1]), str(threshold))
        if lo is not None and hi is not None:
            blo = ctx.subtract(bases[hi.lo_index], bases[lo.hi_index])
            bhi = ctx.subtract(bases[hi.hi_index], bases[lo.lo_index])
            out.append(PassBand(a, b, lo, hi, blo, bhi, True,
                                "two flanking brackets established"))
        else:
            missing = "lower" if lo is None else "upper"
            if a == 0 or b + 1 >= n:
                why = (f"run touches the sweep edge ({missing} side open); "
                       f"no 0 Hz anchoring: sweeps never include DC")
            else:
                why = (f"{missing} boundary borders a validity gap; "
                       f"no interpolation across missing results")
            out.append(PassBand(a, b, lo, hi, None, None, False, why))
    return out


# -- extrema -------------------------------------------------------------------------

@dataclass(frozen=True)
class Extremum:
    index: int  # for runs: first index of the run
    end_index: int
    frequency: str  # canonical key of index
    value: str
    kind: str  # strict-maximum | strict-minimum | flat-maximum |
    # flat-minimum | endpoint-maximum | endpoint-minimum

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "end_index": self.end_index,
            "frequency": self.frequency,
            "value": self.value,
            "kind": self.kind,
        }


def observed_extrema(freq_keys: list[str], values: list[Decimal | None]
                     ) -> list[Extremum]:
    """Discrete-observed extrema only: strict, flat-run and endpoint kinds.

    A flat run reports its full span, never an arbitrary point. A sweep
    that is constant everywhere reports one flat-maximum AND one
    flat-minimum (both true). Nothing here claims a continuous extremum.
    """
    if len(freq_keys) != len(values):
        raise BodeError("frequencies and values must align")
    n = len(values)
    out: list[Extremum] = []

    def valid(i: int) -> bool:
        return 0 <= i < n and values[i] is not None

    if all(v is None for v in values):
        return out
    if n > 1 and all(v is not None and v == values[0] for v in values):
        out.append(Extremum(0, n - 1, freq_keys[0], str(values[0]), "flat-maximum"))
        out.append(Extremum(0, n - 1, freq_keys[0], str(values[0]), "flat-minimum"))
        return out
    # Strict interior + endpoint kinds (endpoints only when the neighbor
    # exists and the value is extremal against it).
    def at(i: int):
        return values[i] if 0 <= i < n else None

    for i in range(n):
        if not valid(i):
            continue
        v = values[i]
        assert v is not None
        left, right = at(i - 1), at(i + 1)
        if left is not None and right is not None:
            if v > left and v > right and v != left and v != right:
                # Flat runs handled below; skip run members here.
                out.append(Extremum(i, i, freq_keys[i], str(v), "strict-maximum"))
            elif v < left and v < right and v != left and v != right:
                out.append(Extremum(i, i, freq_keys[i], str(v), "strict-minimum"))
        elif left is not None or right is not None:
            other = left if left is not None else right
            assert other is not None
            if v > other:
                out.append(Extremum(i, i, freq_keys[i], str(v), "endpoint-maximum"))
            elif v < other:
                out.append(Extremum(i, i, freq_keys[i], str(v), "endpoint-minimum"))
    # Flat runs (length >= 2, maximal, equal values).
    i = 0
    while i < n:
        if not valid(i):
            i += 1
            continue
        j = i
        assert values[j] is not None
        while j + 1 < n and valid(j + 1) and values[j + 1] == values[i]:
            j += 1
        if j > i:
            assert values[i] is not None
            bounds = []
            if valid(i - 1):
                assert values[i - 1] is not None
                bounds.append(values[i - 1])
            if valid(j + 1):
                assert values[j + 1] is not None
                bounds.append(values[j + 1])
            assert values[i] is not None
            v = values[i]
            if bounds and all(v > w for w in bounds):
                out.append(Extremum(i, j, freq_keys[i], str(v), "flat-maximum"))
            elif bounds and all(v < w for w in bounds):
                out.append(Extremum(i, j, freq_keys[i], str(v), "flat-minimum"))
            elif not bounds:
                out.append(Extremum(i, j, freq_keys[i], str(v), "flat-maximum"))
        i = j + 1
    out.sort(key=lambda e: (e.index, e.end_index, e.kind))
    return out


def reactance_zero_brackets(freq_keys: list[str],
                              reactances: list[Decimal | None]
                              ) -> list[CutoffBracket]:
    """Observed reactance-zero brackets (candidates only, never verdicts).

    Sign changes (or exact hits) of a reactance sequence around zero,
    for impedance/admittance sweeps. A bracket is evidence of a nearby
    zero of the sampled reactance — it is NOT a resonance classification
    (a purely resistive network has none; a zero need not resonate).
    """
    return crossing_brackets(freq_keys, reactances, Decimal(0),
                             "reactance-zero-candidate")


# -- top-level analysis ----------------------------------------------------------

@dataclass(frozen=True)
class BodePoint:
    frequency: object  # Quantity (Hz)
    status: object  # ACStatus of the underlying D3 solve
    linear: Decimal | None  # |H| or |Z|/|Y|
    db: MagnitudeResult | None
    wrapped: Decimal | None  # (-pi, pi] via D1
    unwrapped: Decimal | None
    source_digest: str | None  # linked D5 point digest
    diagnostic: str

    def to_dict(self) -> dict:
        return {
            "frequency": canonical_frequency_key(self.frequency),
            "status": self.status.value,
            "linear": None if self.linear is None else str(self.linear),
            "db": None if self.db is None else self.db.to_dict(),
            "wrapped": None if self.wrapped is None else str(self.wrapped),
            "unwrapped": None if self.unwrapped is None else str(self.unwrapped),
            "source_digest": self.source_digest,
            "diagnostic": self.diagnostic,
        }

    def digest_dict(self) -> dict:
        """Hash-covered view: identical physics hashes identically.

        Excludes ``source_digest``: D5's own digests embed input spelling
        ("solved at 1 kHz" vs "solved at 1000 Hz"), so covering them
        would make physically identical analyses hash differently (§32).
        Traceability is preserved — ``source_digest`` stays in
        ``to_dict``/provenance as an exact link, outside hash coverage.
        """
        d = self.to_dict()
        del d["source_digest"]
        return d


@dataclass(frozen=True)
class BodeResult:
    definition: dict  # kind/target summary + source sweep digest link
    points: tuple[BodePoint, ...]
    segments: tuple[tuple[int, int], ...]
    cutoffs: tuple[CutoffBracket, ...]
    bands: tuple[PassBand, ...]
    extrema: tuple[Extremum, ...]
    reactance_brackets: tuple[CutoffBracket, ...]
    provenance: dict
    diagnostics: tuple[str, ...]
    digest: str

    def to_dict(self) -> dict:
        return {
            "definition": dict(self.definition),
            "points": [p.to_dict() for p in self.points],
            "segments": [list(s) for s in self.segments],
            "cutoffs": [c.to_dict() for c in self.cutoffs],
            "bands": [b.to_dict() for b in self.bands],
            "extrema": [e.to_dict() for e in self.extrema],
            "reactance_brackets": [r.to_dict() for r in self.reactance_brackets],
            "provenance": dict(self.provenance),
            "diagnostics": list(self.diagnostics),
            "digest": self.digest,
        }


def _point_phasor(value):
    """Extract the solved phasor or None (UNDEFINED/INFINITE/failed)."""
    from academic_core.domain.engineering.ac.impedance import ImpedanceCategory
    from academic_core.domain.engineering.ac.response import TransferFunction

    if value is None:
        return None
    if isinstance(value, TransferFunction):
        return value.value if value.defined else None
    category = getattr(value, "category", None)
    if category is not None:
        return value.value if category == ImpedanceCategory.FINITE else None
    return None


def _wrapped_phase(ph):
    """D1-authority phase for either complex type.

    Axis-aligned exact phasors keep their exact multiples of pi/2 via
    ``phasors.phase``; non-axis exact phasors (reachable in EXACT mode
    with several axis-mixed sources through a real network) take the
    documented D1-sanctioned path — explicit promotion to
    ``DecimalComplex`` (allowed direction) then ``.phase()``. Either way
    the result is a Decimal in (-pi, pi]; the only difference is whether
    its computation was exact or explicitly approximate.
    """
    from academic_core.domain.engineering.math.rational import RationalComplex

    if isinstance(ph, RationalComplex):
        try:
            return phasor_phase(ph)
        except ValueError:
            return DecimalComplex.from_rational(ph).phase()
    return phasor_phase(ph)


def _decimal_of(number) -> Decimal:
    from fractions import Fraction

    if isinstance(number, Decimal):
        return number
    if isinstance(number, Fraction):
        ctx = make_context(_GUARD_DIGITS)
        return ctx.divide(Decimal(number.numerator), Decimal(number.denominator))
    raise BodeError(f"cannot represent {type(number).__name__} as Decimal")


def analyze_bode(sweep, db_threshold: Decimal | None = None) -> BodeResult:
    """Bode analysis of one D5 sweep result (read-only post-processing).

    Per SOLVED point with a finite phasor: linear magnitude (D1
    modulus), dB (``NEGATIVE_INFINITY_DB`` iff exactly zero), wrapped
    phase (D1, (−π,π]). Unwrap runs over valid phases with segment
    breaks at every invalid point. Cutoffs use ``db_threshold`` (default
    half-power below the maximum valid dB); bands, bandwidth intervals
    and cutoffs apply to transfer kinds, while impedance/admittance
    kinds receive extrema plus reactance-zero brackets instead of
    bandwidth (bandwidth is a transfer concept). A sweep with zero valid
    points yields an empty result with its reason — never an exception.
    """
    from academic_core.domain.engineering.ac.solution import ACStatus

    if not hasattr(sweep, "points") or not hasattr(sweep, "definition"):
        raise BodeError(
            f"analyze_bode needs a D5 SweepResult, got {type(sweep).__name__}"
        )
    points_in = list(sweep.points)
    if not points_in:
        raise BodeError("cannot analyze an empty sweep")
    kind = sweep.definition.kind
    is_transfer = kind == "transfer"
    freqs = [p.frequency for p in points_in]
    keys = [canonical_frequency_key(f) for f in freqs]
    phasors = [_point_phasor(p.value) for p in points_in]
    solved_flags = [p.status == ACStatus.SOLVED for p in points_in]

    linear: list[Decimal | None] = []
    wrapped: list[Decimal | None] = []
    react: list[Decimal | None] = []
    for ph, ok in zip(phasors, solved_flags):
        if ph is None or not ok:
            linear.append(None)
            wrapped.append(None)
            react.append(None)
            continue
        linear.append(phasor_magnitude(ph))
        wrapped.append(_wrapped_phase(ph))
        react.append(_decimal_of(ph.im))
    dbs: list[MagnitudeResult | None] = [
        None if m is None else magnitude_db(m) for m in linear
    ]
    unwrapped, segments = unwrap_phases(wrapped)

    valid_db = [(i, d.value) for i, d in enumerate(dbs)
                if d is not None and d.category == DecibelCategory.FINITE]
    if db_threshold is not None and not isinstance(db_threshold, Decimal):
        raise BodeError("db_threshold must be a Decimal or None")
    threshold = db_threshold
    if threshold is None and valid_db:
        threshold = half_power_threshold_db(max(v for _, v in valid_db))
    db_series: list[Decimal | None] = [
        d.value if d is not None and d.category == DecibelCategory.FINITE else None
        for d in dbs
    ]
    cutoffs: list[CutoffBracket] = []
    bands: list[PassBand] = []
    if threshold is not None and is_transfer:
        cutoffs = crossing_brackets(keys, db_series, threshold, "cutoff")
        bands = threshold_bands(freqs, db_series, threshold)
    extrema = observed_extrema(keys, db_series)
    reactance: list[CutoffBracket] = []
    if not is_transfer:
        reactance = crossing_brackets(keys, react, Decimal(0),
                                      "reactance-zero-candidate")

    bode_points: list[BodePoint] = []
    for i, p in enumerate(points_in):
        # Canonical D6 diagnostic: D5's per-point strings embed the input
        # spelling ("solved at 1 kHz" vs "solved at 1000 Hz"), which would
        # make identical physics hash differently. The D5 original stays
        # reachable via source_digest; the digest only covers this text.
        key = keys[i]
        if p.status != ACStatus.SOLVED:
            diag = f"point {p.status.value}"
        elif linear[i] is None:
            diag = f"solved at {key}; no finite value"
        else:
            diag = f"solved at {key}"
        bode_points.append(BodePoint(
            frequency=p.frequency,
            status=p.status,
            linear=linear[i],
            db=dbs[i],
            wrapped=wrapped[i],
            unwrapped=unwrapped[i],
            source_digest=p.digest,
            diagnostic=diag,
        ))
    n_valid = sum(1 for m in linear if m is not None)
    diagnostics = [
        f"bode: {n_valid}/{len(points_in)} valid points, "
        f"{len(segments)} unwrap segment(s), {len(cutoffs)} cutoff "
        f"bracket(s), {len(bands)} band(s), {len(extrema)} extremum "
        f"observation(s), {len(reactance)} reactance bracket(s)",
    ]
    if n_valid == 0:
        diagnostics.append("no valid points: empty analysis with reason kept")
    provenance = {
        "engine": ENGINE_VERSION,
        "version": "1.0",
        "source_sweep_digest": sweep.digest,
        "definition": sweep.definition.to_dict(),
        "transfer_kind": kind,
        "frequencies": keys,
        "threshold_db": None if threshold is None else str(threshold),
        "threshold_rule": ("explicit" if db_threshold is not None
                           else "half-power below maximum valid dB"),
        "unwrap_rule": ("minimize |step| over integer 2pi offsets; ties to "
                        "smaller cumulative offset then smaller n; segments "
                        "restart at every invalid point"),
        "bandwidth_rule": ("interval from flanking brackets; UNDEFINED "
                           "without two boundaries; no 0 Hz anchoring"),
        "numeric_mode": "EXACT input phasors stay exact; dB/unwrap/grid "
                        "are Decimal working-precision approximations",
        "per_point_status": [p.status.value for p in points_in],
    }
    digest = hashlib.sha256(json.dumps({
        "engine": ENGINE_VERSION,
        "definition": {"kind": kind,
                       "target": sweep.definition.to_dict().get("target")},
        "points": [p.digest_dict() for p in bode_points],
        "segments": [list(s) for s in segments],
        "cutoffs": [c.to_dict() for c in cutoffs],
        "bands": [b.to_dict() for b in bands],
        "extrema": [e.to_dict() for e in extrema],
        "reactance": [r.to_dict() for r in reactance],
    }, sort_keys=True, default=str).encode()).hexdigest()
    return BodeResult(
        definition={"kind": kind,
                    "target": sweep.definition.to_dict().get("target"),
                    "source_sweep_digest": sweep.digest},
        points=tuple(bode_points), segments=tuple(segments),
        cutoffs=tuple(cutoffs), bands=tuple(bands), extrema=tuple(extrema),
        reactance_brackets=tuple(reactance), provenance=provenance,
        diagnostics=tuple(diagnostics), digest=digest,
    )
