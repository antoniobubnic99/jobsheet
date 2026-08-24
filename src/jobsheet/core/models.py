"""The canonical, source-neutral job posting.

Every source -- an RSS feed, an applicant tracking system, a national employment
service -- normalises whatever it scrapes into a `Posting`. Nothing downstream
(matching, storage, the spreadsheet writer, the API) knows which site a row came
from beyond the `source_id` string.

Dates are `datetime.date` in memory and `YYYY-MM-DD` on the wire. Sources hand us
every imaginable format -- `dd.mm.yyyy`, RFC 822, ISO 8601, .NET `/Date(...)/` --
and it is each source's job to convert; see `jobsheet.core.dates`.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator

from jobsheet.core.dedup import normalize_url, title_company_key

__all__ = ["ApplicationStatus", "Posting", "Workplace"]


class Workplace(StrEnum):
    """Where the work physically happens."""

    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNKNOWN = "unknown"


class ApplicationStatus(StrEnum):
    """Where the user is in the process for a given posting.

    `NEW` is the only status the app assigns by itself. Everything else is the
    user's claim about the world, so it is never overwritten by a later run --
    see `jobsheet.store.tracker`.
    """

    NEW = "new"
    APPLIED = "applied"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class Posting(BaseModel):
    """One vacancy, as collected from one source."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str
    title: str
    url: str
    company: str = ""
    location: str = ""
    region: str = ""
    workplace: Workplace = Workplace.UNKNOWN
    description: str = ""
    employment_type: str = ""
    education: str = ""
    salary: str = ""
    posted_at: date | None = None
    deadline: date | None = None
    tags: tuple[str, ...] = ()

    # Everything the source returned that has no home above. Kept so a parser bug
    # can be diagnosed from stored data instead of by re-scraping a page that may
    # no longer exist.
    raw: dict[str, Any] = Field(default_factory=dict, repr=False)

    @field_validator("title", "company", "location", "region", "description", mode="before")
    @classmethod
    def _clean(cls, value: object) -> str:
        """Collapse whitespace. Feed text arrives with newlines and tabs baked in."""
        if value is None:
            return ""
        return " ".join(str(value).split())

    @property
    def dedup_key(self) -> str:
        """Primary identity: the normalised URL."""
        return normalize_url(self.url)

    @property
    def secondary_key(self) -> tuple[str, str]:
        """Fallback identity for boards that republish one job under many URLs."""
        return title_company_key(self.title, self.company)

    def merged_with(self, other: Self) -> Posting:
        """Combine two sightings of the same vacancy, preferring filled fields.

        Used when a cheap listing fetch is later enriched by an expensive detail
        fetch, and when the same job turns up in two feeds. `self` wins on
        conflict; `other` only fills blanks. Never silently drops information --
        anything `other` knows that `self` does not is carried over.
        """
        updates: dict[str, Any] = {}
        for name in type(self).model_fields:
            if name == "raw":
                continue
            mine = getattr(self, name)
            theirs = getattr(other, name)
            # `Workplace.UNKNOWN` is a non-empty string, so "I know nothing here"
            # needs stating explicitly rather than relying on falsiness.
            mine_is_blank = mine is Workplace.UNKNOWN if name == "workplace" else not mine
            if mine_is_blank and theirs:
                updates[name] = theirs
        if other.raw:
            updates["raw"] = {**other.raw, **self.raw}
        return self.model_copy(update=updates)
