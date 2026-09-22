"""F8-P4 bits and symbols (NEW).

Immutable bit/symbol/alphabet/mapping layer. Bits are ints 0/1
(MSB-first convention everywhere in this package). Symbols are ints
0..M-1 with M = 2^k, M <= 256. Rates are Decimal Hz with Quantity
boundaries (Hz dimension).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.math import make_context
from academic_core.domain.engineering.units import FREQUENCY, Unit, parse_unit

MAX_BITS = 65536
MAX_SYMBOLS = 65536
MAX_ORDER_M = 256


def _fail(status: ControlStatus, message: str) -> ControlError:
    return ControlError(status, message)


def validate_bits(values: object) -> tuple:
    """Bits as a tuple of int 0/1 (bool rejected, empty rejected)."""
    if not isinstance(values, (tuple, list)):
        raise _fail(ControlStatus.INVALID, "bits must be a tuple/list")
    if len(values) == 0:
        raise _fail(ControlStatus.INVALID, "bits must be non-empty")
    if len(values) > MAX_BITS:
        raise _fail(ControlStatus.INVALID, "bit budget exceeded")
    out: list = []
    for b in values:
        if isinstance(b, bool) or not isinstance(b, int) or b not in (0, 1):
            raise _fail(ControlStatus.INVALID, "bits must be int 0/1")
        out.append(b)
    return tuple(out)


def log2_int(order: object) -> int:
    """k = log2(M) for M = 2^k, 2 <= M <= 256; else INVALID."""
    if isinstance(order, bool) or not isinstance(order, int):
        raise _fail(ControlStatus.INVALID, "alphabet order M must be int")
    if order < 2 or order > MAX_ORDER_M:
        raise _fail(ControlStatus.INVALID, "alphabet order M in [2, 256] required")
    k = 0
    probe = order
    while probe > 1:
        if probe % 2 != 0:
            raise _fail(ControlStatus.INVALID, "alphabet order M must be a power of 2")
        probe //= 2
        k += 1
    return k


def validate_symbols(values: object, order: int) -> tuple:
    """Symbols as a tuple of int in [0, M)."""
    if not isinstance(values, (tuple, list)):
        raise _fail(ControlStatus.INVALID, "symbols must be a tuple/list")
    if len(values) == 0:
        raise _fail(ControlStatus.INVALID, "symbols must be non-empty")
    if len(values) > MAX_SYMBOLS:
        raise _fail(ControlStatus.INVALID, "symbol budget exceeded")
    out: list = []
    for s in values:
        if isinstance(s, bool) or not isinstance(s, int) or s < 0 or s >= order:
            raise _fail(ControlStatus.INVALID, "symbol out of alphabet range")
        out.append(s)
    return tuple(out)


def map_bits(bits: object, bits_per_symbol: object) -> tuple:
    """MSB-first grouping of bits into symbols; ragged tail -> INVALID."""
    clean = validate_bits(bits)
    if isinstance(bits_per_symbol, bool) or not isinstance(bits_per_symbol, int):
        raise _fail(ControlStatus.INVALID, "bits_per_symbol must be int")
    if bits_per_symbol < 1 or bits_per_symbol > 8:
        raise _fail(ControlStatus.INVALID, "bits_per_symbol in [1, 8] required")
    if len(clean) % bits_per_symbol != 0:
        raise _fail(ControlStatus.INVALID, "bit length must be a multiple of bits_per_symbol")
    out: list = []
    for i in range(0, len(clean), bits_per_symbol):
        acc = 0
        for b in clean[i:i + bits_per_symbol]:
            acc = acc * 2 + b
        out.append(acc)
    return tuple(out)


def unmap_symbols(symbols: object, bits_per_symbol: object, order: int) -> tuple:
    """Symbols back to MSB-first bits (exact inverse of map_bits)."""
    if isinstance(bits_per_symbol, bool) or not isinstance(bits_per_symbol, int):
        raise _fail(ControlStatus.INVALID, "bits_per_symbol must be int")
    if bits_per_symbol < 1 or bits_per_symbol > 8:
        raise _fail(ControlStatus.INVALID, "bits_per_symbol in [1, 8] required")
    clean = validate_symbols(symbols, order)
    out: list = []
    for s in clean:
        chunk: list = []
        rest = s
        for _ in range(bits_per_symbol):
            chunk.append(rest % 2)
            rest //= 2
        out.extend(reversed(chunk))
    return tuple(out)


def pad_bits(bits: object, bits_per_symbol: object) -> tuple:
    """Explicit zero padding; returns (padded_bits, pad_len)."""
    clean = validate_bits(bits)
    if isinstance(bits_per_symbol, bool) or not isinstance(bits_per_symbol, int):
        raise _fail(ControlStatus.INVALID, "bits_per_symbol must be int")
    if bits_per_symbol < 1 or bits_per_symbol > 8:
        raise _fail(ControlStatus.INVALID, "bits_per_symbol in [1, 8] required")
    tail = len(clean) % bits_per_symbol
    if tail == 0:
        return clean, 0
    need = bits_per_symbol - tail
    return clean + (0,) * need, need


def unpad_bits(padded: object, pad_len: object) -> tuple:
    """Remove an explicit zero padding of recorded length."""
    clean = validate_bits(padded)
    if isinstance(pad_len, bool) or not isinstance(pad_len, int) or pad_len < 0:
        raise _fail(ControlStatus.INVALID, "pad_len must be int >= 0")
    if pad_len > len(clean):
        raise _fail(ControlStatus.INVALID, "pad_len exceeds bit length")
    if pad_len == 0:
        return clean
    if clean[len(clean) - pad_len:] != (0,) * pad_len:
        raise _fail(ControlStatus.INCONSISTENT, "padding region is not zero")
    return clean[:len(clean) - pad_len]


def _as_rate(value: object, label: str) -> Decimal:
    if isinstance(value, bool):
        raise _fail(ControlStatus.INVALID, label + " rejects bool")
    if isinstance(value, Decimal):
        out = value
    elif isinstance(value, int):
        out = Decimal(value)
    elif isinstance(value, str):
        try:
            out = Decimal(value.strip())
        except Exception as exc:
            raise _fail(ControlStatus.INVALID, label + " bad string") from exc
    else:
        raise _fail(ControlStatus.INVALID, label + " must be Decimal/int/str")
    if not out.is_finite() or out <= 0:
        raise _fail(ControlStatus.INVALID, label + " > 0 required")
    return out


def _as_unit(value: object, label: str) -> Unit:
    if isinstance(value, Unit):
        return value
    if isinstance(value, str):
        try:
            return parse_unit(value.strip())
        except Exception as exc:
            raise _fail(ControlStatus.INVALID, label + " bad unit string") from exc
    raise _fail(ControlStatus.INVALID, label + " must be Unit/str")


@dataclass(frozen=True)
class Alphabet:
    """Power-of-two alphabet (validation-only post-init)."""

    order: int
    bits_per_symbol: int

    def __post_init__(self) -> None:
        if isinstance(self.order, bool) or not isinstance(self.order, int):
            raise _fail(ControlStatus.INVALID, "alphabet order M must be int")
        expect = log2_int(self.order)
        if isinstance(self.bits_per_symbol, bool) or self.bits_per_symbol != expect:
            raise _fail(ControlStatus.INVALID, "bits_per_symbol must equal log2(M)")

    @staticmethod
    def create(order: int) -> "Alphabet":
        return Alphabet(order=order, bits_per_symbol=log2_int(order))


def bit_rate(symbol_rate_hz: object, bits_per_symbol: int,
             unit: object = "Hz") -> Decimal:
    """Rb = k * Rs (Decimal Hz, exact)."""
    rate = _as_rate(symbol_rate_hz, "symbol rate")
    runit = _as_unit(unit, "rate unit")
    if runit.dimension != FREQUENCY:
        raise _fail(ControlStatus.INVALID, "rate unit must be frequency")
    if isinstance(bits_per_symbol, bool) or not isinstance(bits_per_symbol, int):
        raise _fail(ControlStatus.INVALID, "bits_per_symbol must be int")
    if bits_per_symbol < 1 or bits_per_symbol > 8:
        raise _fail(ControlStatus.INVALID, "bits_per_symbol in [1, 8] required")
    return make_context().multiply(rate, Decimal(bits_per_symbol))
