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
