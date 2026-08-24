"""De-duplication keys.

The cases below are not decorative. Each of the first three encodes a bug that
actually shipped in the predecessor project, so they double as regression tests
for mistakes that are easy to reintroduce while "tidying up" URL handling.
"""

from __future__ import annotations

import pytest

from jobsheet.core.dedup import normalize_url, title_company_key


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Scheme, host case and www are noise.
        ("https://WWW.Example.com/jobs/1", "example.com/jobs/1"),
        ("http://example.com/jobs/1", "example.com/jobs/1"),
        ("HTTPS://Example.COM/Jobs/1", "example.com/jobs/1"),
        # Trailing slash and fragment are noise.
        ("https://example.com/jobs/1/", "example.com/jobs/1"),
        ("https://example.com/jobs/1#apply", "example.com/jobs/1"),
        # Tracking parameters are noise...
        ("https://example.com/j?utm_source=x&utm_campaign=y", "example.com/j"),
        ("https://example.com/j?gclid=abc", "example.com/j"),
        ("https://example.com/j?fbclid=abc&mc_cid=1", "example.com/j"),
        # ...but identifying parameters are the whole identity of the ad.
        # Cutting at "?" gives every ad on such a board the same key, so the
        # second ad ever seen is declared a duplicate and silently dropped.
        (
            "https://burzarada.example/RadnoMjesto_Ispis.aspx?WebSifra=987",
            "burzarada.example/radnomjesto_ispis.aspx?websifra=987",
        ),
        ("https://boards.example/embed/job?gh_jid=4012", "boards.example/embed/job?gh_jid=4012"),
        # Parameter order must not create a second identity for one ad.
        ("https://example.com/j?b=2&a=1", "example.com/j?a=1&b=2"),
        ("https://example.com/j?a=1&b=2", "example.com/j?a=1&b=2"),
        # Mixed: keep the identifier, drop the tracking.
        ("https://example.com/j?id=7&utm_medium=email", "example.com/j?id=7"),
        # Nothing in, nothing out.
        ("", ""),
        (None, ""),
        ("   ", ""),
    ],
)
def test_normalize_url(raw: object, expected: str) -> None:
    assert normalize_url(raw) == expected


def test_tracking_only_query_collapses_to_path() -> None:
    """A URL whose entire query is tracking must equal the bare URL."""
    assert normalize_url("https://example.com/j?utm_source=x") == normalize_url(
        "https://example.com/j"
    )


def test_identifying_query_does_not_collapse() -> None:
    """Two ads on the same path must keep two distinct keys."""
    first = normalize_url("https://example.com/ad.aspx?code=1")
    second = normalize_url("https://example.com/ad.aspx?code=2")
    assert first != second


def test_whitespace_inside_url_is_stripped() -> None:
    """Feeds wrap long links, which injects newlines into the middle of a URL."""
    assert normalize_url("https://example.com/jobs/\n  1") == "example.com/jobs/1"


@pytest.mark.parametrize(
    ("title", "company", "expected"),
    [
        ("Data Analyst", "Example d.o.o.", ("data analyst", "example d.o.o.")),
        ("  Data   Analyst ", "EXAMPLE", ("data analyst", "example")),
        (None, None, ("", "")),
    ],
)
def test_title_company_key(title: object, company: object, expected: tuple[str, str]) -> None:
    assert title_company_key(title, company) == expected
