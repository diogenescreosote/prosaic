"""Span types reject nonsense at construction."""

from __future__ import annotations

import pytest

from prosaic.deadlines import CalendarDays, CourtDays


def test_calendar_span_rejects_negative_count() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        CalendarDays(-1)


def test_court_span_rejects_negative_count() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        CourtDays(-3)
