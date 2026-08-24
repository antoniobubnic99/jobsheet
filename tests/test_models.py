"""The canonical posting model."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from jobsheet.core.models import Posting, Workplace


def posting(**kwargs: object) -> Posting:
    base: dict[str, object] = {
        "source_id": "test",
        "title": "Data Analyst",
        "url": "https://example.test/j/1",
    }
    return Posting(**(base | kwargs))  # type: ignore[arg-type]


class TestNormalisation:
    def test_whitespace_is_collapsed(self) -> None:
        """Feed text arrives with newlines and tabs baked into it."""
        ad = posting(title="Data\n\t  Analyst  ", company="  Example   d.o.o. ")
        assert ad.title == "Data Analyst"
        assert ad.company == "Example d.o.o."

    def test_none_becomes_empty_string(self) -> None:
        assert posting(company=None).company == ""

    def test_unknown_fields_are_rejected(self) -> None:
        """A typo in a source must fail loudly, not vanish into an ignored field."""
        with pytest.raises(ValidationError):
            posting(titel="oops")

    def test_postings_are_immutable(self) -> None:
        ad = posting()
        with pytest.raises(ValidationError):
            ad.title = "changed"  # type: ignore[misc]


class TestKeys:
    def test_dedup_key_uses_normalised_url(self) -> None:
        assert posting(url="https://WWW.Example.test/j/1/").dedup_key == "example.test/j/1"

    def test_secondary_key(self) -> None:
        ad = posting(title="Data Analyst", company="Example")
        assert ad.secondary_key == ("data analyst", "example")


class TestMerge:
    """`merged_with` combines a cheap listing with an expensive detail fetch."""

    def test_blank_fields_are_filled_from_the_other(self) -> None:
        listing = posting(company="", location="")
        detail = posting(company="Example d.o.o.", location="Zagreb")
        merged = listing.merged_with(detail)
        assert merged.company == "Example d.o.o."
        assert merged.location == "Zagreb"

    def test_existing_values_win(self) -> None:
        """`self` is the more trusted sighting; `other` only fills blanks."""
        mine = posting(company="Correct Ltd")
        theirs = posting(company="Stale Ltd")
        assert mine.merged_with(theirs).company == "Correct Ltd"

    def test_unknown_workplace_is_treated_as_blank(self) -> None:
        """`Workplace.UNKNOWN` is a non-empty string, so falsiness is not enough."""
        listing = posting()
        assert listing.workplace is Workplace.UNKNOWN
        detail = posting(workplace=Workplace.REMOTE)
        assert listing.merged_with(detail).workplace is Workplace.REMOTE

    def test_known_workplace_is_not_overwritten(self) -> None:
        listing = posting(workplace=Workplace.ONSITE)
        detail = posting(workplace=Workplace.REMOTE)
        assert listing.merged_with(detail).workplace is Workplace.ONSITE

    def test_dates_are_filled(self) -> None:
        listing = posting()
        detail = posting(posted_at=date(2026, 8, 24), deadline=date(2026, 9, 12))
        merged = listing.merged_with(detail)
        assert merged.posted_at == date(2026, 8, 24)
        assert merged.deadline == date(2026, 9, 12)

    def test_raw_payloads_are_combined_without_losing_either(self) -> None:
        """Diagnosing a parser bug later depends on nothing being thrown away."""
        listing = posting(raw={"a": 1, "shared": "mine"})
        detail = posting(raw={"b": 2, "shared": "theirs"})
        merged = listing.merged_with(detail)
        assert merged.raw == {"a": 1, "b": 2, "shared": "mine"}

    def test_merge_returns_a_new_object(self) -> None:
        listing = posting(company="")
        merged = listing.merged_with(posting(company="Example"))
        assert listing.company == ""
        assert merged is not listing
