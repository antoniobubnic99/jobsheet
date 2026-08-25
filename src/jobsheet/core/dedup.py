"""URL normalisation for de-duplication.

Ported from the private tool this project grew out of.

The one rule worth carrying over verbatim: **the query string is not discarded.**
An earlier version cut every URL at the `?`, which looked tidy and was wrong --
several job boards identify an ad purely by a query parameter
(`RadnoMjesto_Ispis.aspx?WebSifra=12345`, `?gh_jid=...`, `?job=...`). Cutting
there collapses every ad from such a board onto one key, so the second ad ever
seen is declared a duplicate and silently dropped.

Only parameters that describe *how the user arrived* are stripped, never
parameters that describe *which ad this is*.
"""

from __future__ import annotations

import re

__all__ = ["TRACKING_PARAMS", "normalize_url", "title_company_key"]

# Parameters that identify the referral, not the ad.
TRACKING_PARAMS: frozenset[str] = frozenset(
    {
        "gclid",
        "fbclid",
        "msclkid",
        "mc_cid",
        "mc_eid",
        "igshid",
        "ref",
        "referrer",
        "trk",
        "trackingid",
    }
)

_SCHEME_AND_WWW = re.compile(r"^[a-z][a-z0-9+.-]*://(www\.)?")
_WHITESPACE = re.compile(r"\s+")


def _is_tracking(pair: str) -> bool:
    name = pair.split("=", 1)[0]
    return name.startswith("utm_") or name in TRACKING_PARAMS


def normalize_url(value: object) -> str:
    """Return a stable de-duplication key for an ad URL.

    Drops the scheme, a leading ``www.``, the fragment, a trailing slash and any
    tracking parameters. Sorts the surviving parameters so that a different
    ordering of the same query does not read as a different ad.

    >>> normalize_url("https://WWW.Example.com/jobs/1/?b=2&utm_source=x&a=1#top")
    'example.com/jobs/1?a=1&b=2'
    >>> normalize_url("http://example.com/jobs/1")
    'example.com/jobs/1'
    >>> normalize_url(None)
    ''
    """
    if not value:
        return ""
    text = _WHITESPACE.sub("", str(value)).strip().lower()
    if not text:
        return ""
    text = _SCHEME_AND_WWW.sub("", text).split("#", 1)[0]
    path, _, query = text.partition("?")
    path = path.rstrip("/")
    if not query:
        return path
    kept = sorted(p for p in query.split("&") if p and not _is_tracking(p))
    return f"{path}?{'&'.join(kept)}" if kept else path


def title_company_key(title: object, company: object) -> tuple[str, str]:
    """Secondary de-duplication key.

    Some boards republish one vacancy under several ad numbers, which gives each
    copy a distinct URL. Matching on ``(title, company)`` catches those. It is
    deliberately *secondary*: two genuinely different openings can share a title
    at the same employer, so this is only trusted within a single run, where the
    URL key has already done the heavy lifting.
    """
    return (
        _WHITESPACE.sub(" ", str(title or "")).strip().lower(),
        _WHITESPACE.sub(" ", str(company or "")).strip().lower(),
    )
