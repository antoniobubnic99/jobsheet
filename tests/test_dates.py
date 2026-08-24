"""Date parsing across the formats real job feeds emit."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from jobsheet.core.dates import days_ago, parse_date, parse_dotnet_date


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # ISO, with and without a time part.
        ("2026-08-24", date(2026, 8, 24)),
        ("2026-08-24T00:00:00", date(2026, 8, 24)),
        ("2026-08-24 09:15:00", date(2026, 8, 24)),
        # European day-first, including the trailing dot Croatian uses.
        ("24.08.2026", date(2026, 8, 24)),
        ("24.08.2026.", date(2026, 8, 24)),
        ("4.8.2026", date(2026, 8, 4)),
        ("24/08/2026", date(2026, 8, 24)),
        # RFC 822, as used by every RSS <pubDate>.
        ("Mon, 24 Aug 2026 09:15:00 +0200", date(2026, 8, 24)),
        ("Sun, 02 Aug 2026 23:30:00 GMT", date(2026, 8, 2)),
        # Already a date or datetime.
        (date(2026, 8, 24), date(2026, 8, 24)),
        (datetime(2026, 8, 24, 9, 15, tzinfo=UTC), date(2026, 8, 24)),
        # Unparseable or absent must be None, never an exception: one bad date
        # must not take down a fetch of several hundred ads.
        ("", None),
        (None, None),
        ("nema datuma", None),
        ("2026-13-45", None),
    ],
)
def test_parse_date(raw: object, expected: date | None) -> None:
    assert parse_date(raw) == expected


def test_day_first_beats_month_first() -> None:
    """An ambiguous European date is read day-first, not month-first."""
    assert parse_date("05.06.2026") == date(2026, 6, 5)


class TestDotNetDates:
    """`/Date(ms+hhmm)/`, emitted by ASP.NET/Rhetos backends.

    The timezone offset is load-bearing. These endpoints publish local midnight,
    whose epoch lands on the *previous* day in UTC. Dropping the offset moves
    every publication date back by one, which is enough to push a brand-new ad
    outside a "last 30 days" window on the day it appears.
    """

    def test_offset_is_applied(self) -> None:
        with_offset = parse_dotnet_date("/Date(1755036000000+0200)/")
        without_offset = datetime.fromtimestamp(1755036000000 / 1000, tz=UTC).date()
        assert with_offset is not None
        assert with_offset != without_offset
        assert (with_offset - without_offset).days == 1

    def test_negative_offset(self) -> None:
        assert parse_dotnet_date("/Date(1755036000000-0500)/") == date(2025, 8, 12)

    def test_missing_offset_is_tolerated(self) -> None:
        assert parse_dotnet_date("/Date(1755036000000)/") is not None

    def test_routed_through_parse_date(self) -> None:
        assert parse_date("/Date(1755036000000+0200)/") == parse_dotnet_date(
            "/Date(1755036000000+0200)/"
        )

    def test_not_a_dotnet_date(self) -> None:
        assert parse_dotnet_date("/Date(nonsense)/") is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (date(2026, 8, 24), 0),
        (date(2026, 8, 23), 1),
        (date(2026, 7, 25), 30),
        (None, None),
    ],
)
def test_days_ago(value: date | None, expected: int | None) -> None:
    assert days_ago(value, today=date(2026, 8, 24)) == expected
