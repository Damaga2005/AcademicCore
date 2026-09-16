"""Quantities, units, dimensions (Phase 6): Decimal, dimensional, deterministic.

- `Dimension`: SI-base exponent tuple (M,L,T,I,Θ,N,J) + registry of named dims.
- `Unit`: symbol → (dimension, factor to SI base as Decimal).
- `Quantity(value: Decimal, unit)`: parsing ("5 V", "10 kΩ", "2.2 µF"),
  arithmetic with dimensional checking, conversions exact in Decimal.
- No floats cross this boundary. No UI/process/filesystem dependencies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

# SI base exponents: (mass, length, time, current, temp, amount, luminous)
DIMENSIONLESS = (0, 0, 0, 0, 0, 0, 0)
VOLTAGE = (1, 2, -3, -1, 0, 0, 0)
CURRENT = (0, 0, 0, 1, 0, 0, 0)
RESISTANCE = (1, 2, -3, -2, 0, 0, 0)
# F8-D5 additive only: siemens = A/V = 1/ohm (conductance/admittance).
ADMITTANCE = (-1, -2, 3, 2, 0, 0, 0)
POWER = (1, 2, -3, 0, 0, 0, 0)
CAPACITANCE = (-1, -2, 4, 2, 0, 0, 0)
INDUCTANCE = (1, 2, -2, -2, 0, 0, 0)
FREQUENCY = (0, 0, -1, 0, 0, 0, 0)
TIME = (0, 0, 1, 0, 0, 0, 0)
CHARGE = (0, 0, 1, 1, 0, 0, 0)
ENERGY = (1, 2, -2, 0, 0, 0, 0)
LENGTH = (0, 1, 0, 0, 0, 0, 0)

DIM_NAMES = {
    DIMENSIONLESS: "dimensionless", VOLTAGE: "voltage", CURRENT: "current",
    RESISTANCE: "resistance", ADMITTANCE: "admittance", POWER: "power", CAPACITANCE: "capacitance",
    INDUCTANCE: "inductance", FREQUENCY: "frequency", TIME: "time",
    CHARGE: "charge", ENERGY: "energy", LENGTH: "length",
}

PREFIXES = {"p": "-12", "n": "-9", "u": "-6", "µ": "-6", "m": "-3", "c": "-2",
            "": "0", "k": "3", "M": "6", "G": "9"}

# symbol -> (dimension, factor to base unit)
_BASE_UNITS = {
    "V": (VOLTAGE, "1"), "A": (CURRENT, "1"), "ohm": (RESISTANCE, "1"),
    "W": (POWER, "1"), "F": (CAPACITANCE, "1"), "H": (INDUCTANCE, "1"),
    "Hz": (FREQUENCY, "1"), "s": (TIME, "1"), "C": (CHARGE, "1"),
    "J": (ENERGY, "1"), "m": (LENGTH, "1"),
    # F8-D4 additive only: reactive (var) and apparent (VA) volt-ampere
    # labels share the POWER dimension (same physics, distinct role labels;
    # no new dimension, W behavior and ordering untouched).
    "var": (POWER, "1"), "VA": (POWER, "1"),
    # F8-D5 additive only: siemens, the SI unit of conductance/admittance
    # (A/V = 1/ohm). Appended last so existing base-unit match order — and
    # hence every previously valid parse — is untouched. NOTE: "mS"/"uS"/
    # "nS" previously fell through to *seconds* ("ms" is milliseconds and
    # stays so); they now correctly parse as millisiemens & co., which is
    # the SI-correct reading. Pinned by D5 regression tests.
    "S": (ADMITTANCE, "1"),
}
_ALIASES = {"Ω": "ohm", "Ω": "ohm", "Ωs": "ohm", "v": "V", "a": "A", "w": "W",
            "f": "F", "h": "H", "hz": "Hz", "HZ": "Hz", "sec": "s", "volt": "V",
            "volts": "V", "amp": "A", "amps": "A", "watt": "W", "watts": "W",
            "farad": "F", "henry": "H", "hertz": "Hz", "second": "s",
            "seconds": "s", "coulomb": "C", "joule": "J", "ohms": "ohm",
            "siemens": "S", "Siemens": "S"}


class UnitError(ValueError):
    pass


@dataclass(frozen=True)
class Unit:
    symbol: str  # canonical display symbol, e.g. "kΩ"? no — base+prefix split
    base: str  # canonical base symbol: V, A, ohm, W, F, H, Hz, s, C, J
    prefix: str  # one of PREFIXES
    dimension: tuple
    factor: Decimal  # value_in_base = value * factor

    @property
    def display(self) -> str:
        base = {"ohm": "Ω"}.get(self.base, self.base)
        pre = {"u": "µ"}.get(self.prefix, self.prefix)
        return f"{pre}{base}" if self.prefix else base


def parse_unit(symbol: str) -> Unit:
    s = (symbol or "").strip()
    if not s:
        raise UnitError("empty unit")
    if s == "1":
        return Unit("1", "1", "", DIMENSIONLESS, Decimal(1))
    s = s.replace("Ω", "ohm").replace("Ω", "ohm").replace("µ", "u")
    s = _ALIASES.get(s, s)
    s = _ALIASES.get(s.lower(), s) if s not in _BASE_UNITS else s
    for base in sorted(_BASE_UNITS, key=len, reverse=True):
        if s == base or s.endswith(base):
            pre = s[: len(s) - len(base)] if s != base else ""
            pre = {"µ": "u"}.get(pre, pre)
            if pre in PREFIXES:
                dim, _ = _BASE_UNITS[base]
                factor = (Decimal(10) ** int(PREFIXES[pre]))
                return Unit(s, base, pre, dim, factor)
    # prefixed alias like "kohm", "mV"
    low = s.lower()
    for base in sorted(_BASE_UNITS, key=len, reverse=True):
        if low.endswith(base.lower()) and len(low) > len(base):
            pre = s[: len(s) - len(base)]
            pre = {"µ": "u", "U": "u"}.get(pre, pre)
            if pre in PREFIXES:
                dim, _ = _BASE_UNITS[base]
                return Unit(s, base, pre, dim, (Decimal(10) ** int(PREFIXES[pre])))
    raise UnitError(f"unknown unit: {symbol!r}")


def _add_dim(a: tuple, b: tuple) -> tuple:
    return tuple(x + y for x, y in zip(a, b))


def _sub_dim(a: tuple, b: tuple) -> tuple:
    return tuple(x - y for x, y in zip(a, b))


@dataclass(frozen=True)
class Quantity:
    value: Decimal  # in the stated unit (internal full precision)
    unit: Unit

    def __post_init__(self):
        if not isinstance(self.value, Decimal):
            raise UnitError("Quantity value must be Decimal")

    @property
    def dimension(self) -> tuple:
        return self.unit.dimension

    @property
    def dim_name(self) -> str:
        return DIM_NAMES.get(self.dimension, "derived")

    def to_base(self) -> Decimal:
        return self.value * self.unit.factor

    def convert_to(self, symbol: str) -> "Quantity":
        if symbol == self.unit.display:
            # Converting to one's own display symbol is always a no-op --
            # short-circuit before re-parsing. Needed for derived dimensions
            # with no registered SI unit (e.g. conductance = 1/ohm), whose
            # display symbol (`_unit_for_dim`'s DIM_NAMES fallback) is not
            # itself a `parse_unit`-recognized string.
            return self
        target = parse_unit(symbol)
        if target.dimension != self.dimension:
            raise UnitError(f"cannot convert {self.unit.display} to {symbol}")
        return Quantity(self.to_base() / target.factor, target)

    def _check_same(self, other: "Quantity", op: str) -> None:
        if self.dimension != other.dimension:
            raise UnitError(
                f"incompatible dimensions for {op}: "
                f"{DIM_NAMES.get(self.dimension, '?')} vs "
                f"{DIM_NAMES.get(other.dimension, '?')}")

    def __add__(self, other: "Quantity") -> "Quantity":
        self._check_same(other, "+")
        other_c = other.convert_to(self.unit.display)
        return Quantity(self.value + other_c.value, self.unit)

    def __sub__(self, other: "Quantity") -> "Quantity":
        self._check_same(other, "-")
        other_c = other.convert_to(self.unit.display)
        return Quantity(self.value - other_c.value, self.unit)

    def __mul__(self, other) -> "Quantity":
        if isinstance(other, (int, Decimal)):
            return Quantity(self.value * Decimal(other), self.unit)
        if isinstance(other, Quantity):
            dim = _add_dim(self.dimension, other.dimension)
            base_val = self.to_base() * other.to_base()
            unit = _unit_for_dim(dim)
            return Quantity(base_val / unit.factor, unit)
        return NotImplemented

    def __truediv__(self, other) -> "Quantity":
        if isinstance(other, (int, Decimal)):
            if Decimal(other) == 0:
                raise UnitError("division by zero")
            return Quantity(self.value / Decimal(other), self.unit)
        if isinstance(other, Quantity):
            if other.to_base() == 0:
                raise UnitError("division by zero")
            dim = _sub_dim(self.dimension, other.dimension)
            base_val = self.to_base() / other.to_base()
            unit = _unit_for_dim(dim)
            return Quantity(base_val / unit.factor, unit)
        return NotImplemented

    def __pow__(self, exp) -> "Quantity":
        exp = Decimal(exp)
        if exp != int(exp):
            raise UnitError("only integer exponents")
        dim = self.dimension
        out = DIMENSIONLESS
        for _ in range(abs(int(exp))):
            out = _add_dim(out, dim) if exp > 0 else _sub_dim(out, dim)
        base_val = self.to_base() ** int(exp) if exp >= 0 else \
            Decimal(1) / (self.to_base() ** abs(int(exp)))
        if self.to_base() == 0 and exp < 0:
            raise UnitError("division by zero")
        unit = _unit_for_dim(out)
        return Quantity(base_val / unit.factor, unit)

    def __neg__(self) -> "Quantity":
        return Quantity(-self.value, self.unit)

    def format(self, figures: int = 6) -> str:
        """Representation (display only; internal value untouched)."""
        v = self.value.normalize()
        s = format(v, "f")
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return f"{s} {self.unit.display}"

    def compact(self) -> str:
        """Single-token ASCII form for netlists (parseable back)."""
        v = self.value.normalize()
        s = format(v, "f")
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        if self.unit.dimension == DIMENSIONLESS:
            # Bare number: a "1" suffix would not parse back (F8-G: "2"
            # must not serialize as "21").
            return s
        return f"{s}{self.unit.prefix}{self.unit.base}"


def _unit_for_dim(dim: tuple) -> Unit:
    if dim == DIMENSIONLESS:
        return Unit("1", "1", "", DIMENSIONLESS, Decimal(1))
    for sym, (d, _) in _BASE_UNITS.items():
        if d == dim:
            return Unit(sym, sym, "", dim, Decimal(1))
    # derived dimension without a named SI unit: real computed dimension,
    # display symbol only (e.g. V*s) — not a fabricated/unknown dimension
    name = DIM_NAMES.get(dim, "derived")
    return Unit(name, name, "", dim, Decimal(1))


_QTY_RE = re.compile(
    r"^\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?)\s*([a-zA-ZµΩΩ°%°/\s]*?)\s*$")


def parse_quantity(text: str) -> Quantity:
    m = _QTY_RE.match(text)
    if not m:
        raise UnitError(f"cannot parse quantity: {text!r}")
    try:
        value = Decimal(m.group(1))
    except InvalidOperation:
        raise UnitError(f"bad number: {text!r}")
    unit_s = m.group(2).strip()
    if not unit_s:
        return Quantity(value, Unit("1", "1", "", DIMENSIONLESS, Decimal(1)))
    return Quantity(value, parse_unit(unit_s))
