"""Source-neutral building blocks: the posting model, de-duplication, matching."""

from __future__ import annotations

from jobsheet.core.dates import days_ago, parse_date
from jobsheet.core.dedup import normalize_url, title_company_key
from jobsheet.core.matching import (
    KeywordGroup,
    Match,
    Rejection,
    SearchProfile,
    flags_for,
    fold,
    location_matches,
    match,
    rejection_for,
    sentence_case,
)
from jobsheet.core.models import ApplicationStatus, Posting, Workplace

__all__ = [
    "ApplicationStatus",
    "KeywordGroup",
    "Match",
    "Posting",
    "Rejection",
    "SearchProfile",
    "Workplace",
    "days_ago",
    "flags_for",
    "fold",
    "location_matches",
    "match",
    "normalize_url",
    "parse_date",
    "rejection_for",
    "sentence_case",
    "title_company_key",
]
