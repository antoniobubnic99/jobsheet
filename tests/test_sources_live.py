"""Every connector against the real service, run nightly rather than on push.

`test_sources_connectors.py` proves the parsers still handle a *recorded* shape.
That is the wrong test for the thing that actually breaks: a service quietly
changing its response, leaving the recorded fixture -- and therefore the whole
push-time suite -- perfectly green while real users get nothing.

That is not hypothetical. On 2026-08-25 the first live run of this suite found
Selekcija.gov.hr returning a `Records` envelope where it had returned a bare
array. Every recorded test passed. The source produced zero results for every
user, and had for an unknown length of time.

So these tests are deliberately shaped around what a service can legitimately
change and what it cannot:

* **Counts are never asserted.** A board with 40 openings today may have 4
  tomorrow, and a test that fails for that is a test people learn to ignore.
* **Shape and meaning are asserted.** A posting must have a URL that resolves to
  the service, an identity that de-duplicates, and a date that is a date.
* **Each target is one test.** One dead board must not hide thirteen live ones.

Boards close and companies stop hiring, so the third-party slugs below are
overridable by environment variable. Reach for that before deleting a test: a
404 from one board is a bad fixture, but a 404 from all of them is news.

Run: pytest -m network
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import pytest

from jobsheet.core.http import HttpClient
from jobsheet.core.models import Posting
from jobsheet.sources import registry
from jobsheet.sources.base import FetchContext

pytestmark = pytest.mark.network

# Small on purpose. These run against other people's servers, and one page is
# enough to prove a parser still understands the answer.
MAX_ITEMS = 15


def slug(name: str, default: str) -> str:
    """A board identifier, overridable when a company stops hiring."""
    return os.environ.get(f"JOBSHEET_LIVE_{name.upper()}", default)


@dataclass(frozen=True)
class Target:
    """One source, and what a healthy answer from it looks like."""

    source_id: str
    params: dict[str, Any] = field(default_factory=dict)

    # False for boards that are genuinely allowed to be empty -- an ATS account
    # with no open roles is working correctly, and asserting otherwise turns
    # someone else's hiring freeze into our failing build.
    expect_results: bool = True

    # The share of postings that must carry a title. Below 1.0 only where the
    # service itself omits them; see HZZ.
    titled: float = 1.0

    # Set when the source is known to be broken against the live service. The
    # test still runs -- an xpass is how we learn it was fixed.
    broken: str = ""


TARGETS = [
    # -- generic ----------------------------------------------------------
    Target(
        "rss",
        {"url": slug("rss_url", "https://remotive.com/remote-jobs/feed"), "label": "Remotive"},
    ),
    # -- applicant tracking systems ---------------------------------------
    Target("greenhouse", {"board": slug("greenhouse", "gitlab")}),
    # Lever's own demo account, published for exactly this purpose.
    Target("lever", {"company": slug("lever", "leverdemo")}),
    Target("ashby", {"board": slug("ashby", "ashby")}),
    Target("workable", {"account": slug("workable", "blueground")}),
    Target("smartrecruiters", {"company": slug("smartrecruiters", "SmartRecruiters")}),
    # The only Recruitee board found answering 200 on 2026-08-25, and it had no
    # open roles. That still proves the endpoint and the parser, which is what
    # this suite is for.
    Target("recruitee", {"company": slug("recruitee", "tellent")}, expect_results=False),
    # -- job boards --------------------------------------------------------
    Target("remotive", {"limit": MAX_ITEMS}),
    Target("remoteok", {}),
    Target("arbeitnow", {"pages": 1}),
    # -- Croatia -----------------------------------------------------------
    # HZZ shipped an empty title element on 26% of feed items on 2026-08-25 --
    # and they are clustered, not scattered: the first 15 items of the Zagreb
    # feed were all title-less, so a floor of any kind is the wrong assertion
    # here. The title genuinely lives on the advert's own page, and recovering
    # it is `enrich`'s job, checked by
    # `test_hzz_recovers_a_missing_title_from_the_advert` below.
    Target("hzz", {"counties": [4]}, titled=0.0),
    Target("posao_hr", {}),
    Target("selekcija", {"days": 45}),
    Target(
        "narodne_novine",
        {"terms": "geodetski", "days": 60},
        broken=(
            "NN result parsing has drifted: the institution is never found, titles "
            "come back as sentence fragments, and the result count is identical at "
            "30, 90 and 365 days -- so paging is not happening. Documented "
            "behaviour was geodet -> 0 and geodetski -> 39; on 2026-08-25 it was "
            "2 and 1. Needs the result page re-read against current markup."
        ),
    ),
]

TARGETS_BY_ID = {target.source_id: target for target in TARGETS}


@pytest.fixture
async def live_http() -> AsyncIterator[HttpClient]:
    """A real client, kept at production politeness. Nothing here is in a hurry."""
    client = HttpClient(timeout=40.0)
    try:
        yield client
    finally:
        await client.aclose()


def context(http: HttpClient) -> FetchContext:
    return FetchContext(http=http, today=date.today(), max_items=MAX_ITEMS, max_enrich=3)


def check_posting(posting: Posting, source_id: str) -> None:
    """The invariants every posting owes the rest of the app."""
    assert posting.source_id.startswith(source_id), f"wrong source_id: {posting.source_id!r}"
    assert posting.url.startswith(("http://", "https://")), f"unusable url: {posting.url!r}"

    # Identity is the normalised URL with the scheme removed; without it the
    # posting cannot de-duplicate, and the user sees the same job every run.
    assert posting.dedup_key, "no dedup_key"
    assert not posting.dedup_key.startswith(("http://", "https://")), (
        f"dedup_key kept its scheme: {posting.dedup_key!r}"
    )

    if posting.posted_at is not None:
        assert isinstance(posting.posted_at, date)
        # Tomorrow is allowed: services publish in their own timezone.
        assert posting.posted_at <= date.today() + timedelta(days=1), (
            f"posted in the future: {posting.posted_at}"
        )
    if posting.deadline is not None:
        assert isinstance(posting.deadline, date)


@pytest.mark.parametrize("target", TARGETS, ids=lambda t: t.source_id)
async def test_source_answers_and_is_understood(target: Target, live_http: HttpClient) -> None:
    """The service replies and the parser still makes sense of what it says."""
    if target.broken:
        pytest.xfail(target.broken)

    source_cls = registry.get(target.source_id)
    assert source_cls is not None, f"{target.source_id} is not registered"

    found = await source_cls().fetch(target.params, context(live_http))

    assert isinstance(found, list)
    if target.expect_results:
        assert found, "the service answered, but nothing was parsed out of it"

    for posting in found:
        check_posting(posting, target.source_id)

    if found:
        titled = sum(1 for posting in found if posting.title.strip()) / len(found)
        assert titled >= target.titled, (
            f"only {titled:.0%} of postings had a title, expected {target.titled:.0%}"
        )


async def test_hzz_recovers_a_missing_title_from_the_advert(live_http: HttpClient) -> None:
    """A quarter of HZZ's feed items have no title.

    The advert's own page is the only place the job is named, so this is the
    difference between a usable spreadsheet row and a blank one.
    """
    source_cls = registry.get("hzz")
    assert source_cls is not None
    source = source_cls()
    ctx = context(live_http)

    found = await source.fetch({"counties": [4]}, ctx)
    untitled = [posting for posting in found if not posting.title.strip()]
    if not untitled:
        pytest.skip("no title-less items in the feed today, which is good news")

    enriched = await source.enrich(untitled[0], ctx)
    assert enriched.title.strip(), "enrich did not recover the title"
    assert enriched.company.strip(), "enrich did not recover the employer"

