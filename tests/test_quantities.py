"""Quantities: construction, dimensions, conversion, prefixes, incompatibility."""
from decimal import Decimal

import pytest

from academic_core.domain.engineering.units import (
    Quantity, UnitError, parse_quantity, parse_unit,
)


def test_parse_and_display():
    assert parse_quantity("5 V").format() == "5 V"
    assert parse_quantity("10 kΩ").unit.display == "kΩ"
    assert parse_quantity("2.2 µF").convert_to("nF").value == Decimal("2200")
    assert parse_quantity("1Mohm").convert_to("kohm").value == Decimal("1000")


def test_prefixes_and_exact_conversions():
    assert parse_quantity("1000 mV").convert_to("V").value == Decimal("1")
    assert parse_quantity("1 MHz").convert_to("Hz").value == Decimal("1000000")
    assert parse_quantity("1 pF").convert_to("F").value == Decimal("0.000000000001")
    assert parse_quantity("2 Gohm").convert_to("ohm").value == Decimal("2000000000")


def test_dimensions_named():
    assert parse_quantity("5 V").dim_name == "voltage"
    assert parse_quantity("2 A").dim_name == "current"
    assert parse_quantity("10 s").dim_name == "time"


def test_incompatible_operations_rejected():
    with pytest.raises(UnitError):
        parse_quantity("5 V") + parse_quantity("2 A")
    with pytest.raises(UnitError):
        parse_quantity("5 V") - parse_quantity("2 s")
    with pytest.raises(UnitError):
        parse_quantity("5 V").convert_to("A")


def test_derived_dimensions():
    assert (parse_quantity("5 V") / parse_quantity("2 A")).dim_name == "resistance"
    assert (parse_quantity("5 V") * parse_quantity("2 A")).dim_name == "power"
    assert (parse_quantity("5 V") ** 2).dim_name == "derived"
    with pytest.raises(UnitError):
        parse_quantity("5 V") / parse_quantity("0 A")
    with pytest.raises(UnitError):
        parse_quantity("5 V") ** Decimal("0.5")


def test_edges_and_invalid():
    assert parse_quantity("0 V").value == 0
    assert parse_quantity("-3.3 mV").value < 0  # negatives allowed generically
    for bad in ("", "V", "5 XX", "5 k", "abc"):
        with pytest.raises(UnitError):
            parse_quantity(bad)
    assert parse_quantity("5").dimension == (0, 0, 0, 0, 0, 0, 0)
    # internal precision kept; representation separate
    q = parse_quantity("1 V") / parse_quantity("3 A")
    assert q.value == Decimal(1) / Decimal(3)


def test_femto_and_tera_prefixes():
    """PR audit regression: newly-added f (1e-15) and T (1e12) prefixes.

    Covers exact factor/round-trip arithmetic and the two ambiguity
    concerns called out in review: f (femto) vs F (Farad), and
    T (tera, uppercase-only per SI) vs a hypothetical lowercase t.
    """
    # Parsing + exact factors
    ff = parse_quantity("1 fF")
    tw = parse_quantity("1 TW")
    assert ff.unit.prefix == "f" and ff.unit.base == "F"
    assert ff.unit.factor == Decimal("1E-15")
    assert tw.unit.prefix == "T" and tw.unit.base == "W"
    assert tw.unit.factor == Decimal("1E+12")

    # Exact Decimal round-trip conversion (no float drift)
    assert tw.convert_to("W").value == Decimal("1E+12")
    assert tw.convert_to("W").convert_to("TW").value == Decimal(1)
    assert ff.convert_to("F").value == Decimal("1E-15")
    assert ff.convert_to("F").convert_to("fF").value == Decimal(1)

    # compact()/parse_quantity round-trip preserves value and unit
    q = parse_quantity("2.5 TW")
    assert parse_quantity(q.compact()).to_base() == q.to_base()
    q2 = parse_quantity("3.75 fF")
    assert parse_quantity(q2.compact()).to_base() == q2.to_base()

    # f (femto) is not confusable with bare F (Farad)
    assert parse_quantity("1 fF").to_base() != parse_quantity("1 F").to_base()
    assert parse_quantity("1 F").unit.prefix == ""
    with pytest.raises(UnitError):
        parse_quantity("1 Ff")  # malformed case-flip must not silently misparse

    # T vs t: lowercase t is not a registered SI prefix (SI defines tera as
    # uppercase T only); "1 tW" must fail, not silently mean tera-watt.
    assert "t" not in __import__(
        "academic_core.domain.engineering.units", fromlist=["PREFIXES"]
    ).PREFIXES
    with pytest.raises(UnitError):
        parse_quantity("1 tW")

    # No genuine unit symbol collides with a hypothetical lowercase-tera
    # prefix (e.g. no "t" for tonne registered).
    from academic_core.domain.engineering.units import _BASE_UNITS
    assert "t" not in _BASE_UNITS

    # Unknown prefix -> clean UnitError, not a crash or silent misparse
    with pytest.raises(UnitError):
        parse_quantity("1 xW")

    # Stacked prefixes ("kilo-mega-watt") are invalid and must be rejected
    with pytest.raises(UnitError):
        parse_quantity("1 kMW")
