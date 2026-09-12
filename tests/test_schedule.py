"""Schedule: normal cases + edge cases (anchor rule, fortnightly, coherence)."""
from datetime import date

import pytest

from academic_core.domain import schedule as S


def weekly_tue():
    return S.Series("subject:sdm", "teoria", 2, "09:00", "11:00",
                    date(2025, 9, 1), date(2025, 9, 30), 1, "A1")


def test_weekly_expansion():
    days = S.expand_sessions(weekly_tue())
    assert [d.isoformat() for d in days] == [
        "2025-09-02", "2025-09-09", "2025-09-16", "2025-09-23", "2025-09-30"]


def test_fortnightly_anchor_rule():
    # fecha_inicio Wed 2025-09-03, weekday Tue -> pattern anchors Tue 09-09.
    s = S.Series("subject:sdm", "laboratorio", 2, "15:00", "17:00",
                 date(2025, 9, 3), date(2025, 9, 30), 2)
    assert [d.isoformat() for d in S.expand_sessions(s)] == ["2025-09-09", "2025-09-23"]
    assert S.is_session_day(date(2025, 9, 23), s)
    assert not S.is_session_day(date(2025, 9, 16), s)  # off-pattern Tuesday


def test_is_session_day_matches_expansion():
    s = S.Series("subject:sdm", "teoria", 5, "09:00", "10:00",
                 date(2025, 9, 1), date(2025, 12, 19), 2)
    expanded = set(S.expand_sessions(s))
    d = date(2025, 9, 1)
    while d <= date(2025, 12, 19):
        assert S.is_session_day(d, s) == (d in expanded)
        d = date.fromordinal(d.toordinal() + 1)


def test_coherence_rejected():
    with pytest.raises(ValueError):
        S.Series("subject:sdm", "teoria", 2, "11:00", "09:00",
                 date(2025, 9, 1), date(2025, 9, 30))
    with pytest.raises(ValueError):
        S.Series("subject:sdm", "teoria", 2, "09:00", "11:00",
                 date(2025, 9, 30), date(2025, 9, 1))
    with pytest.raises(ValueError):
        S.Series("subject:sdm", "teoria", 0, "09:00", "11:00",
                 date(2025, 9, 1), date(2025, 9, 30))
    with pytest.raises(ValueError):
        S.Series("subject:sdm", "teoria", 2, "09:00", "11:00",
                 date(2025, 9, 1), date(2025, 9, 30), 3)


def test_overlap_half_open():
    assert S.intervals_overlap("09:00", "11:00", "10:00", "12:00")
    assert not S.intervals_overlap("09:00", "10:00", "10:00", "11:00")  # touching
    assert not S.intervals_overlap("10:00", "11:00", "09:00", "10:00")
