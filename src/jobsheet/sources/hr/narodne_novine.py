"""Narodne novine -- the Croatian official gazette, vacancy notices.

Where towns, municipalities, schools, courts and public institutions advertise.
It is also the most laborious source in the project, for three reasons:

* **The search matches whole words, not prefixes.** `geodet` returns nothing;
  `geodetski` returns dozens. Search terms must be full word forms, which is the
  opposite of how the local keyword filter works.
* **The title is never the job title.** It is always the institution, so the post
  has to be mined out of legal prose -- hence the anchor phrases below.
* **Every result page must be opened** to find the job title at all, so this
  source is capped harder than the others.

Notices that only point at Selekcija.gov.hr are dropped: state bodies publish a
stub here and the real competition there, and keeping both means every such job
appears twice.
"""

from __future__ import annotations

import re
import urllib.parse
from datetime import timedelta
from typing import Any

from jobsheet.core.dates import parse_date
from jobsheet.core.models import Posting
from jobsheet.sources._parse import strip_html
from jobsheet.sources.base import (
    FetchContext,
    ParamSpec,
    Source,
    SourceManifest,
)

__all__ = ["NarodneNovineSource"]

SEARCH = "https://narodne-novine.nn.hr/search.aspx"

_ITEM_SPLIT = 'class="searchListItem"'
_LINK = re.compile(r'href="(/clanci/oglasi/o\d+\.html)"')
_TITLE = re.compile(r'class="searchListItemTitle"[^>]*>(.*?)</', re.S)
_DATE = re.compile(r"(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})")
# A hidden relevance score sits inside the title markup; leaving it in produces
# titles like "Grad Samobor 0".
_SCORE = re.compile(r'<span class="score">.*?</span>', re.S)
_BODY = re.compile(r'<div class="og-content">(.*?)</div>', re.S)

# Ordered: the earlier the phrase, the more likely it introduces the real post.
_ANCHORS = (
    "na radno mjesto",
    "na radna mjesta",
    "za radno mjesto",
    "za radna mjesta",
    "za prijam u službu",
    "za prijam u državnu službu",
    "za prijam u radni odnos",
    "za popunu radnog mjesta",
    "za imenovanje",
    "za izbor",
)
_STOP = re.compile(
    r"\s+(?:u |na |pri |za |radi |koje |koji |te |i |a |s |sa |o |od |do |iz )\b|[.;:,]|\d"
)
_LEADING_JUNK = re.compile(r"^(?:u|na|pri|za|radi|i|a|s|sa|o|od|do|iz)\b\s*", re.IGNORECASE)

_POINTS_AT_SELEKCIJA = re.compile(r"selekcija\.gov\.hr|centralni\s+sustav", re.IGNORECASE)

_EMPLOYMENT = re.compile(
    r"\bna\s+(neodređeno|određeno)\s+vrijeme", re.IGNORECASE
)
_EDUCATION = re.compile(
    r"(sveučilišni\s+\w+\s+studij|stručni\s+\w+\s+studij|preddiplomski[^.,;]{0,40}"
    r"|diplomski[^.,;]{0,40}|magistar[^.,;]{0,30}|prvostupnik[^.,;]{0,30}"
    r"|srednja\s+stručna\s+sprema|VSS|VŠS|SSS)",
    re.IGNORECASE,
)


class NarodneNovineSource(Source):
    manifest = SourceManifest(
        id="narodne_novine",
        name="Narodne novine (vacancy notices)",
        homepage="https://narodne-novine.nn.hr/",
        description="Public-sector vacancy notices in the Croatian official gazette.",
        country="HR",
        rate_limit=1.0,
        params=[
            ParamSpec(
                name="terms",
                label="Search words",
                kind="text",
                required=True,
                placeholder="geodetski, katastar, urbanizam",
                help=(
                    "Separate with commas. This search matches WHOLE WORDS, so use "
                    "full forms: 'geodet' finds nothing, 'geodetski' finds plenty."
                ),
            ),
            ParamSpec(
                name="days",
                label="How far back to look",
                kind="number",
                default=30,
            ),
            ParamSpec(
                name="max_pages",
                label="How many notices to open at most",
                kind="number",
                default=30,
                help="Each notice is a separate request, so this is the slowest source.",
            ),
        ],
    )

    async def fetch(self, params: dict[str, Any], ctx: FetchContext) -> list[Posting]:
        raw_terms = str(self.param(params, "terms") or "")
        terms = [t.strip() for t in raw_terms.replace(";", ",").split(",") if t.strip()]
        if not terms:
            return []

        days = max(1, int(self.param(params, "days") or 30))
        cap = min(int(self.param(params, "max_pages") or 30), ctx.max_enrich)
        since = ctx.today - timedelta(days=days)

        ctx.report(f"Reading Narodne novine ({len(terms)} search words)")

        found: dict[str, tuple[str, Any]] = {}
        for term in terms:
            query = urllib.parse.urlencode(
                {
                    "upit": term,
                    "naslovi": "ne",
                    "sortiraj": "1",
                    "kategorija": "3",  # the classified section
                    "ogvrsta": "26",  # vacancy notices
                    "od": since.strftime("%d.%m.%Y"),
                    "do": ctx.today.strftime("%d.%m.%Y"),
                    "rpp": "50",
                    "qtype": "3",
                    "pretraga": "da",
                }
            )
            try:
                page = await ctx.http.get_text(f"{SEARCH}?{query}")
            except Exception as error:
                ctx.report(f"  ! NN '{term}': {type(error).__name__}")
                continue

            for raw_chunk in page.split(_ITEM_SPLIT)[1:]:
                # The score span must go before the title is cut out, not after:
                # the title regex stops at the first "</", which is the score's
                # own closing tag, so the marker survives as a stray "0" and the
                # institution reads "Grad Samobor 0".
                chunk = _SCORE.sub("", raw_chunk)
                link = _LINK.search(chunk)
                if not link:
                    continue
                url = "https://narodne-novine.nn.hr" + link.group(1)
                if url in found:
                    continue
                title_match = _TITLE.search(chunk)
                institution = strip_html(title_match.group(1)) if title_match else ""
                date_match = _DATE.search(chunk)
                found[url] = (institution, parse_date(date_match.group(1)) if date_match else None)

        ctx.report(f"  {len(found)} notices found; opening up to {cap}")

        postings: list[Posting] = []
        for url, (institution, published) in list(found.items())[:cap]:
            try:
                page = await ctx.http.get_text(url)
            except Exception as error:
                ctx.report(f"  ! could not open {url} ({type(error).__name__})")
                continue

            body_match = _BODY.search(page)
            body = strip_html(body_match.group(1)) if body_match else ""
            if not body:
                continue
            if _POINTS_AT_SELEKCIJA.search(body):
                # A stub pointing at the central system; the real competition is
                # picked up by the Selekcija source, so keeping this duplicates it.
                continue

            employment = _EMPLOYMENT.search(body)
            education = _EDUCATION.search(body)

            postings.append(
                Posting(
                    source_id="narodne_novine",
                    title=_mine_job_title(body) or institution,
                    url=url,
                    company=institution,
                    description=body[:4000],
                    employment_type=employment.group(0) if employment else "",
                    education=education.group(0) if education else "",
                    posted_at=published,
                    raw={"institution": institution},
                )
            )

        ctx.report(f"  {len(postings)} from Narodne novine")
        return postings


def _mine_job_title(text: str) -> str:
    """Dig the actual post out of legal prose.

    Croatian vacancy notices read "... raspisuje natječaj za prijam u službu na
    radno mjesto viši stručni suradnik za prostorno uređenje ...". The post
    follows one of a small set of fixed phrases, and ends at the next
    preposition, punctuation mark or digit.
    """
    lowered = text.casefold()
    for anchor in _ANCHORS:
        position = lowered.find(anchor)
        if position < 0:
            continue
        tail = text[position + len(anchor) :].strip()
        stop = _STOP.search(tail)
        # RUF001: the en and em dashes are deliberate -- Croatian legal text uses
        # both, and a title that keeps a trailing dash reads as a typo.
        candidate = (tail[: stop.start()] if stop else tail[:80]).strip(" -–—,;:")  # noqa: RUF001
        candidate = _LEADING_JUNK.sub("", candidate).strip()
        if len(candidate) >= 4:
            return candidate
    return ""
