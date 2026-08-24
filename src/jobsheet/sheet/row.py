"""A row of the sheet: what the source said, plus what the user knows.

Keeping those two halves in one object -- rather than in two parallel lists -- is
the whole safety story. A row is sorted, moved and rewritten as a unit, so a
tick can never drift away from the job it belongs to.

`user_values` is deliberately open-ended. Any column the app does not recognise
is a column the user invented, and the app's only job there is to carry the value
through untouched.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from jobsheet.core.models import ApplicationStatus, Posting

__all__ = ["JobRow", "cell_value", "sort_key"]


class JobRow(BaseModel):
    """One tracked vacancy."""

    model_config = ConfigDict(extra="forbid")

    posting: Posting
    found_at: date

    # Derived by the app from the search, refreshed on every run.
    category: str = ""
    note: str = ""

    # The user's, never overwritten.
    status: ApplicationStatus = ApplicationStatus.NEW
    user_values: dict[str, Any] = Field(default_factory=dict)

    # A human-typed label in the link cell survives round-trips: some people
    # rename links to something they recognise, and losing that is data loss.
    link_text: str = ""

    @property
    def dedup_key(self) -> str:
        return self.posting.dedup_key

    def user_value_count(self) -> int:
        """How many pieces of the user's own knowledge this row carries.

        The writer snapshots this before a save and checks it after. If the
        total moves, something rewrote a column it had no business touching and
        the file is restored from backup.
        """
        total = sum(1 for value in self.user_values.values() if value not in (None, "", False))
        if self.status is not ApplicationStatus.NEW:
            total += 1
        return total


# Where each recognised column key gets its value. Anything absent from this map
# is a user column, read from `user_values`.
_SOURCE_FIELDS: dict[str, Callable[[JobRow], Any]] = {
    "found_at": lambda r: r.found_at,
    "posted_at": lambda r: r.posting.posted_at,
    "deadline": lambda r: r.posting.deadline,
    "title": lambda r: r.posting.title,
    "company": lambda r: r.posting.company,
    "url": lambda r: r.posting.url,
    "location": lambda r: r.posting.location,
    "region": lambda r: r.posting.region,
    "workplace": lambda r: str(r.posting.workplace),
    "employment_type": lambda r: r.posting.employment_type,
    "education": lambda r: r.posting.education,
    "salary": lambda r: r.posting.salary,
    "source": lambda r: r.posting.source_id,
    "tags": lambda r: ", ".join(r.posting.tags),
    "category": lambda r: r.category,
    "note": lambda r: r.note,
    "status": lambda r: str(r.status),
}


def cell_value(row: JobRow, key: str) -> Any:
    """The value for one column of one row, whoever owns that column."""
    if resolver := _SOURCE_FIELDS.get(key):
        return resolver(row)
    return row.user_values.get(key)


def sort_key(row: JobRow, keys: list[str]) -> tuple[Any, ...]:
    """Build a sort key that never raises on missing or mixed-type values.

    Dates, strings and `None` end up in one list, and Python refuses to compare
    those. Everything is therefore reduced to a string, with a leading flag so
    that empty values sort consistently instead of jumping around between runs.
    """
    parts: list[Any] = []
    for key in keys:
        value = cell_value(row, key)
        if value is None or value == "":
            parts.extend(("", ""))
        elif isinstance(value, date):
            parts.extend(("1", value.isoformat()))
        else:
            parts.extend(("1", str(value).casefold()))
    return tuple(parts)
