"""F8-P4 deterministic constellations (NEW).

Immutable symbol maps: (id, bit label, complex coordinate, energy) with
unit-average-energy normalisation, deterministic id ordering, unique
labels and Gray verification. QPSK is frozen per the design gate;
square 4-QAM is identical to QPSK by construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.comms.bits import log2_int
from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.math import (
    DecimalComplex,
    complex_from_polar,
    decimal_pi,
    decimal_sqrt,
    make_context,
)

MPSK_ORDERS = (8, 16, 32, 64)
MQAM_ORDERS = (4, 16, 64, 256)
MASK_MAX_M = 64


def _fail(status: ControlStatus, message: str) -> ControlError:
    return ControlError(status, message)


def gray_code(index: int, width: int) -> tuple:
    """Binary reflected Gray code of index over width bits (MSB-first)."""
    if width < 1:
        raise _fail(ControlStatus.INVALID, "gray width >= 1 required")
    gray = index ^ (index >> 1)
    out: list = []
    for pos in range(width - 1, -1, -1):
        out.append((gray >> pos) & 1)
    return tuple(out)


def _check_raw(order: int, raw: list) -> None:
    if len(raw) != order:
        raise _fail(ControlStatus.INVALID, "constellation point count must equal M")
    seen_labels: set = set()
    for sid, label, _re, _im in raw:
        if sid < 0 or sid >= order:
            raise _fail(ControlStatus.INVALID, "constellation id out of range")
        key = tuple(label)
        if key in seen_labels:
            raise _fail(ControlStatus.INVALID, "constellation labels must be unique")
        seen_labels.add(key)


@dataclass(frozen=True)
class ConstellationPoint:
    """One immutable constellation point."""

    sid: int
    label: tuple
    coordinate: DecimalComplex
    energy: Decimal


@dataclass(frozen=True)
class Constellation:
    """Immutable normalized constellation (validation-only post-init)."""

    scheme: str
    order: int
    bits_per_symbol: int
    points: tuple
    average_energy: Decimal
    max_energy: Decimal
    min_distance: Decimal
    gray: bool

    def __post_init__(self) -> None:
        if not isinstance(self.scheme, str) or not self.scheme.strip():
            raise _fail(ControlStatus.INVALID, "constellation scheme cannot be empty")
        if self.order != len(self.points):
            raise _fail(ControlStatus.INVALID, "constellation size must equal M")
        ids = [p.sid for p in self.points]
        if ids != list(range(self.order)):
            raise _fail(ControlStatus.INVALID, "constellation ids must be 0..M-1 in order")
        labels = [tuple(p.label) for p in self.points]
        if len(set(labels)) != len(labels):
            raise _fail(ControlStatus.INVALID, "constellation labels must be unique")
        for p in self.points:
            if not p.coordinate.re.is_finite() or not p.coordinate.im.is_finite():
                raise _fail(ControlStatus.INVALID, "constellation coordinates must be finite")
            if not p.energy.is_finite() or p.energy < 0:
                raise _fail(ControlStatus.INVALID, "constellation energies must be finite >= 0")

    def coordinate_of(self, sid: int) -> DecimalComplex:
        if isinstance(sid, bool) or not isinstance(sid, int):
            raise _fail(ControlStatus.INVALID, "symbol id must be int")
        if sid < 0 or sid >= self.order:
            raise _fail(ControlStatus.INVALID, "symbol id out of range")
        return self.points[sid].coordinate

    def label_of(self, sid: int) -> tuple:
        if isinstance(sid, bool) or not isinstance(sid, int):
            raise _fail(ControlStatus.INVALID, "symbol id must be int")
        if sid < 0 or sid >= self.order:
            raise _fail(ControlStatus.INVALID, "symbol id out of range")
        return self.points[sid].label


def _build(scheme: str, order: int, raw: list) -> Constellation:
    """Normalize raw (sid, label, re, im) to unit average energy."""
    k = log2_int(order)
    _check_raw(order, raw)
    ctx = make_context()
    coords: list = []
    for _sid, _label, re, _im in raw:
        if not isinstance(re, Decimal) or not isinstance(_im, Decimal):
            raise _fail(ControlStatus.INVALID, "raw coordinates must be Decimal")
        if not re.is_finite() or not _im.is_finite():
            raise _fail(ControlStatus.INVALID, "raw coordinates must be finite")
        coords.append(DecimalComplex(re, _im))
    if all(c.is_zero_exact() for c in coords):
        raise _fail(ControlStatus.INVALID, "degenerate all-zero constellation")
    total = Decimal(0)
    for c in coords:
        total = ctx.add(total, c.squared_modulus())
    mean = ctx.divide(total, Decimal(order))
    if mean <= 0:
        raise _fail(ControlStatus.INVALID, "degenerate zero-energy constellation")
    scale = ctx.divide(Decimal(1), decimal_sqrt(mean, ctx))
    points: list = []
    emax = Decimal(0)
    for (sid, label, _re, _im), coord in zip(raw, coords):
        scaled = DecimalComplex(ctx.multiply(coord.re, scale),
                                ctx.multiply(coord.im, scale))
        energy = scaled.squared_modulus()
        if energy > emax:
            emax = energy
        points.append(ConstellationPoint(sid=sid, label=tuple(label),
                                         coordinate=scaled, energy=energy))
    dmin: Decimal | None = None
    for i in range(order):
        for j in range(i + 1, order):
            dist = (points[i].coordinate - points[j].coordinate).modulus()
            if dmin is None or dist < dmin:
                dmin = dist
    if dmin is None:
        raise _fail(ControlStatus.INVALID, "order-1 constellations unsupported")
    gray = _verify_gray(points, dmin)
    return Constellation(scheme=scheme, order=order, bits_per_symbol=k,
                         points=tuple(points), average_energy=Decimal(1),
                         max_energy=emax, min_distance=dmin, gray=gray)


def _verify_gray(points: list, dmin: Decimal) -> bool:
    """True iff every minimum-distance pair differs in exactly one bit."""
    ctx = make_context()
    tol = ctx.multiply(dmin, Decimal("1e-30"))
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            dist = (points[i].coordinate - points[j].coordinate).modulus()
            diff = dist - dmin
            if diff.copy_abs() <= (tol if tol > 0 else Decimal(0)):
                lab_i = points[i].label
                lab_j = points[j].label
                flips = sum(1 for a, b in zip(lab_i, lab_j) if a != b)
                if flips != 1:
                    return False
    return True


def is_gray(constellation: Constellation) -> bool:
    """Independent Gray re-verification (exhaustive over dmin pairs)."""
    if not isinstance(constellation, Constellation):
        raise _fail(ControlStatus.INVALID, "is_gray needs a Constellation")
    return _verify_gray(list(constellation.points), constellation.min_distance)


def bpsk_constellation() -> Constellation:
    """Frozen BPSK: 0 -> +1, 1 -> -1 (unit energy)."""
    return _build("bpsk", 2, [
        (0, (0,), Decimal(1), Decimal(0)),
        (1, (1,), Decimal(-1), Decimal(0)),
    ])


def qpsk_constellation() -> Constellation:
    """Frozen QPSK Gray map: 00->Q1, 01->Q2, 11->Q3, 10->Q4 (unit energy)."""
    ctx = make_context()
    inv = ctx.divide(Decimal(1), decimal_sqrt(Decimal(2), ctx))
    pos = ctx.plus(inv)
    neg = ctx.minus(inv)
    return _build("qpsk", 4, [
        (0, (0, 0), pos, pos),
        (1, (0, 1), neg, pos),
        (2, (1, 1), neg, neg),
        (3, (1, 0), pos, neg),
    ])


def mpsk_constellation(order: int) -> Constellation:
    """M-PSK ring, phi0 = 0, reflected Gray; order in {8,16,32,64}."""
    if order not in MPSK_ORDERS:
        raise _fail(ControlStatus.INVALID, "M-PSK order must be one of 8/16/32/64")
    k = log2_int(order)
    raw: list = []
    for idx in range(order):
        angle = make_context().divide(
            make_context().multiply(Decimal(2), decimal_pi(make_context())),
            Decimal(order))
        angle = make_context().multiply(angle, Decimal(idx))
        point = complex_from_polar(Decimal(1), angle)
        raw.append((idx, gray_code(idx, k), point.re, point.im))
    return _build("mpsk" + str(order), order, raw)


def mqam_constellation(order: int) -> Constellation:
    """Square M-QAM, order in {4,16,64,256}.

    M = 4 is the frozen QPSK map by construction; larger orders use
    per-dimension reflected Gray over odd-integer levels.
    """
    if order not in MQAM_ORDERS:
        raise _fail(ControlStatus.INVALID, "M-QAM order must be one of 4/16/64/256")
    if order == 4:
        base = qpsk_constellation()
        return Constellation(scheme="qam4", order=base.order,
                             bits_per_symbol=base.bits_per_symbol,
                             points=base.points, average_energy=base.average_energy,
                             max_energy=base.max_energy,
                             min_distance=base.min_distance, gray=base.gray)
    k = log2_int(order)
    half = 0
    probe = order
    while probe > 1:
        probe //= 4
        half += 1
    side = 1
    for _ in range(half):
        side *= 2
    rows = half
    raw: list = []
    for li in range(side):
        for lj in range(side):
            level_i = Decimal(2 * li - side + 1)
            level_j = Decimal(2 * lj - side + 1)
            label = gray_code(li, rows) + gray_code(lj, rows)
            sid = li * side + lj
            raw.append((sid, label, level_i, level_j))
    return _build("qam" + str(order), order, raw)


def mask_constellation(order: int) -> Constellation:
    """M-ASK real levels, reflected Gray; order = 2^k <= 64."""
    k = log2_int(order)
    if order > MASK_MAX_M:
        raise _fail(ControlStatus.INVALID, "M-ASK order <= 64 required")
    raw: list = []
    for idx in range(order):
        level = Decimal(2 * idx - order + 1)
        raw.append((idx, gray_code(idx, k), level, Decimal(0)))
    return _build("ask" + str(order), order, raw)


def ook_constellation() -> Constellation:
    """OOK as ASK-2 degenerate: 0 -> 0, 1 -> sqrt(2) (mean energy 1)."""
    ctx = make_context()
    root2 = decimal_sqrt(Decimal(2), ctx)
    return _build("ook", 2, [
        (0, (0,), Decimal(0), Decimal(0)),
        (1, (1,), root2, Decimal(0)),
    ])


def minimum_distance(constellation: Constellation) -> Decimal:
    if not isinstance(constellation, Constellation):
        raise _fail(ControlStatus.INVALID, "minimum_distance needs a Constellation")
    return constellation.min_distance


def average_energy(constellation: Constellation) -> Decimal:
    if not isinstance(constellation, Constellation):
        raise _fail(ControlStatus.INVALID, "average_energy needs a Constellation")
    return constellation.average_energy
