"""Generic results: scales, weights, optional, partial, rounding, edges."""
from decimal import Decimal

import pytest

from academic_core.domain import results as R


def g(key, value, scale=R.N_10, weight="100", optional=False):
    return R.Grade(key, value, scale, Decimal(weight), optional)


def test_numeric_scales_normalize():
    assert g("a", "7.5").ratio() == Decimal("0.75")
    assert g("a", "15", R.N_20).ratio() == Decimal("0.75")
    assert g("a", "75", R.N_100).ratio() == Decimal("0.75")
    with pytest.raises(ValueError):
        g("a", "11")
    with pytest.raises(ValueError):
        R.Grade("a", "5", R.N_10, Decimal(150))


def test_letter_and_pass_fail():
    assert g("a", "SB", R.LETTERS_ES).ratio() == Decimal("0.9")
    assert g("a", "sb", R.LETTERS_ES).ratio() == Decimal("0.9")  # case-insensitive
    with pytest.raises(ValueError):
        g("a", "Z", R.LETTERS_ES)
    assert g("a", "apto", R.PASS_FAIL).ratio() == 1
    assert g("a", "suspenso", R.PASS_FAIL).ratio() == 0


def test_weighted_compute_deterministic():
    grades = [g("final", "5.25", weight="60"), g("parcial", "7.5", weight="40")]
    r = R.compute(grades)
    assert (r.complete, r.state) == (True, "aprobada")
    assert r.percent() == Decimal("61.50")  # ratio 0.615 expressed 0-100
    # order-independent
    assert R.compute(list(reversed(grades))).ratio == r.ratio


def test_optional_excluded_and_partial_honest():
    grades = [g("req", "8", weight="60"), g("opt", "4", weight="40", optional=True)]
    r = R.compute(grades, planned_required_weight=Decimal(100))
    assert (r.state, r.complete) == ("en_progreso", False)
    assert r.total_weight == 100 and r.evaluated_weight == 60
    r2 = R.compute(grades)  # no plan known: complete over recorded weight
    assert (r2.state, r2.complete) == ("aprobada", True)


def test_edges():
    assert R.compute([]).state == "sin_evaluar"
    assert R.compute([g("a", "0", weight="0")]).state == "sin_evaluar"
    assert R.compute([g("a", "10", weight="100")]).percent() == Decimal("100.00")
    assert R.compute([g("a", "0", weight="100")]).state == "suspendida"
    with pytest.raises(ValueError):
        R.compute([g("a", "5", weight="60")], planned_required_weight=Decimal(50))
    with pytest.raises(ValueError):
        R.Scale("numeric", Decimal(10), Decimal(0))
    # custom pass mark: Spanish 5.0 over 10 == ratio 0.5 default
    assert R.compute([g("a", "4.9")]).state == "suspendida"
    assert R.compute([g("a", "4.9")], pass_ratio=Decimal("0.49")).state == "aprobada"
