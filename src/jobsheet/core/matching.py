"""Deciding which postings the user actually wants.

Ported and generalised from the predecessor's `filtri.py`. Two phases, because the
expensive part of a fetch is opening each ad's own page:

1. `match` -- cheap keyword test over the title and description of every ad.
2. `rejection_for` -- hard filters over the detail fields, run only for ads that
   already passed phase one and have therefore been worth enriching.

Two rules earned through false positives and are kept deliberately:

* **Keywords are never matched against the source's own category.** National
  employment services staple broad categories onto every ad (one real example:
  "CIVIL ENGINEERS, ARCHITECTS, SURVEYORS"), which turns a bricklayer vacancy
  into a surveying match.
* **A hit found only in the description is weaker than a hit in the title.** The
  profile can demand extra evidence for those; see `description_match_requires`.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from jobsheet.core.dates import days_ago
from jobsheet.core.models import Posting, Workplace

__all__ = [
    "KeywordGroup",
    "Match",
    "Rejection",
    "SearchProfile",
    "flags_for",
    "fold",
    "location_matches",
    "match",
    "rejection_for",
    "sentence_case",
]

# Latin letters that NFKD does not decompose, so they need an explicit mapping.
# Without this, "č" survives folding and "GEODEZIJA"/"geodezija" stop comparing equal.
_TRANSLIT = str.maketrans(
    {
        "č": "c", "ć": "c", "ž": "z", "š": "s", "đ": "d",
        "Č": "c", "Ć": "c", "Ž": "z", "Š": "s", "Đ": "d",
        "ø": "o", "Ø": "o", "ł": "l", "Ł": "l", "ß": "ss",
    }
)


def fold(text: object) -> str:
    """Lower-case, strip diacritics: "GEODEZIJA" and "geodezija" become one term."""
    folded = str(text or "").translate(_TRANSLIT).lower()
    folded = unicodedata.normalize("NFKD", folded)
    return "".join(ch for ch in folded if not unicodedata.combining(ch))


_patterns: dict[str, re.Pattern[str]] = {}


def _pattern(term: str) -> re.Pattern[str]:
    """Compile a term into a word-boundary-anchored prefix match.

    The start is anchored so "gis" cannot hide inside "logistics". The end is
    deliberately *not* anchored, so a stem like "survey" covers surveyor,
    surveying and surveys without the user listing every inflection -- which
    matters a great deal in heavily inflected languages.
    """
    if term not in _patterns:
        _patterns[term] = re.compile(r"\b" + re.escape(fold(term)))
    return _patterns[term]


def _first_hit(text: str, terms: Iterable[str] | None) -> str:
    """The first term that occurs in `text`, or an empty string."""
    for term in terms or ():
        if _pattern(term).search(text):
            return term
    return ""


class KeywordGroup(BaseModel):
    """A named bundle of search terms.

    The name is what lands in the spreadsheet's category column, so groups are
    ordered: the first group that matches wins, letting the user express
    priority ("I would rather be told this is a GIS job than a Data job").
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    terms: list[str] = Field(default_factory=list)


class SearchProfile(BaseModel):
    """Everything the user is looking for, and everything they refuse."""

    model_config = ConfigDict(extra="forbid")

    keyword_groups: list[KeywordGroup] = Field(default_factory=list)

    # Where. Empty means "anywhere" -- location filtering is skipped entirely.
    locations: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    remote_terms: list[str] = Field(
        default_factory=lambda: ["remote", "work from home", "hybrid", "telecommute"]
    )

    # How old an ad may be when it carries no explicit deadline.
    max_age_days: int = 30

    excluded_employers: list[str] = Field(default_factory=list)
    excluded_employment_types: list[str] = Field(default_factory=list)
    excluded_schedules: list[str] = Field(default_factory=list)

    # Terms that override `excluded_employment_types`. This exists because of a
    # real trap: in Croatian, "na neodređeno" (permanent) literally contains
    # "određeno" (fixed-term), so blocking fixed-term contracts also blocks every
    # permanent one. Any allowlist hit wins over the blocklist.
    employment_type_allowlist: list[str] = Field(default_factory=list)

    # When the only keyword hit was in the description, demand that the ad's
    # education field contains one of these. Empty disables the rule.
    description_match_requires: list[str] = Field(default_factory=list)

    # label -> terms. These never reject an ad, they only annotate it, because a
    # regex cannot tell a hard requirement from a nice-to-have.
    flags: dict[str, list[str]] = Field(default_factory=dict)


class Match(BaseModel):
    """Why a posting was kept."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    group: str
    term: str
    field: Literal["title", "description"]


class Rejection(BaseModel):
    """Why a posting was dropped. `code` is stable; `detail` is for humans."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    detail: str = ""


def match(posting: Posting, profile: SearchProfile) -> Match | None:
    """First keyword group that matches, title before description.

    Returns `None` when nothing matches. A profile with no keyword groups matches
    everything -- "show me the whole feed" is a legitimate request.
    """
    if not profile.keyword_groups:
        return Match(group="", term="", field="title")

    title = fold(posting.title)
    for group in profile.keyword_groups:
        if term := _first_hit(title, group.terms):
            return Match(group=group.name, term=term, field="title")

    body = fold(posting.description)
    for group in profile.keyword_groups:
        if term := _first_hit(body, group.terms):
            return Match(group=group.name, term=term, field="description")
    return None


def location_matches(posting: Posting, profile: SearchProfile) -> bool:
    """Whether the workplace is somewhere the user will work.

    The place of work is the only trustworthy field, so it decides alone. A
    region is consulted *only* when no place is given at all. That ordering is
    not fussiness: on one government portal the region field holds the address of
    the publishing authority rather than the job, and 27% of its listings say
    "Zagreb" for work in Split, Osijek or on an island (measured 2026-08-24). Let
    region outrank place and the user is offered jobs halfway across the country.
    """
    if not profile.locations and not profile.regions:
        return True
    if posting.workplace is Workplace.REMOTE:
        return True

    if place := fold(posting.location):
        return bool(_first_hit(place, profile.locations) or _first_hit(place, profile.remote_terms))
    if region := fold(posting.region):
        return bool(_first_hit(region, profile.regions))

    # Nothing structured at all: fall back to the free text of the ad.
    text = fold(" ".join([posting.title, posting.company, posting.description]))
    return bool(_first_hit(text, profile.locations) or _first_hit(text, profile.remote_terms))


def rejection_for(
    posting: Posting,
    hit: Match,
    profile: SearchProfile,
    *,
    today: date | None = None,
) -> Rejection | None:
    """The reason to drop this posting, or `None` if it survives every hard filter."""
    today = today or date.today()

    employer = fold(posting.company)
    if employer and (bad := _first_hit(employer, profile.excluded_employers)):
        return Rejection(code="excluded_employer", detail=bad)

    contract = fold(posting.employment_type)
    allowed = _first_hit(contract, profile.employment_type_allowlist)
    banned = _first_hit(contract, profile.excluded_employment_types)
    if contract and banned and not allowed:
        return Rejection(code="employment_type", detail=posting.employment_type or banned)

    schedule = fold(posting.raw.get("schedule", ""))
    if schedule and (bad := _first_hit(schedule, profile.excluded_schedules)):
        return Rejection(code="schedule", detail=str(posting.raw.get("schedule") or bad))

    if hit.field == "description" and profile.description_match_requires:
        education = fold(posting.education)
        if not education:
            return Rejection(code="description_only_no_education")
        if not _first_hit(education, profile.description_match_requires):
            return Rejection(code="description_only_wrong_level", detail=posting.education)

    if posting.deadline and posting.deadline < today:
        return Rejection(code="deadline_passed", detail=posting.deadline.isoformat())

    # An explicit deadline is better evidence than an age cut-off: an open call is
    # open however old it is. The age rule therefore applies only when the ad does
    # not say when it closes.
    if not posting.deadline:
        age = days_ago(posting.posted_at, today=today)
        if age is not None and age > profile.max_age_days:
            return Rejection(code="too_old", detail=str(age))

    return None


def flags_for(posting: Posting, profile: SearchProfile, *, today: date | None = None) -> list[str]:
    """Soft warnings to show beside the ad. These never reject anything."""
    text = fold(" ".join([posting.title, posting.description, str(posting.raw.get("notes", ""))]))
    found = [label for label, terms in profile.flags.items() if _first_hit(text, terms)]

    age = days_ago(posting.posted_at, today=today or date.today())
    if not posting.deadline and age is not None and age > profile.max_age_days:
        found.append("older ad — check whether it is still open")
    return found


_ACRONYMS = frozenset(
    {
        "gis", "qgis", "arcgis", "sql", "cad", "bim", "uav", "gps", "gnss", "api",
        "it", "ict", "hr", "eu", "pdf", "erp", "crm", "aws", "ci", "cd", "qa",
    }
)


def sentence_case(text: str) -> str:
    """Turn SHOUTED source text into something readable.

    Some feeds publish every title, employer and place name in capitals. Text
    that is not entirely upper-case is left alone, because mixed case is a
    deliberate choice by whoever wrote it. Known acronyms stay capitalised.
    """
    text = (text or "").strip()
    if not text or not text.isupper():
        return text
    words = [w.upper() if w.strip(".,:;()/-") in _ACRONYMS else w for w in text.lower().split(" ")]
    joined = " ".join(words)
    return joined[:1].upper() + joined[1:]
