"""Narodne novine -- the Croatian official gazette, vacancy notices.

Where towns, municipalities, schools, courts and public institutions advertise.
It is also the most laborious source in the project, for three reasons:

* **The search matches whole words, not prefixes.** `geodet` returns nothing;
  `geodetski` returns dozens. Search terms must be full word forms, which is the
  opposite of how the local keyword filter works.
* **The title is never the job title.** It reads "KIND OF NOTICE - Institution",
  so the post itself has to be mined out of legal prose -- hence the anchor
  phrases below. The kind is kept because it separates an opening from a
  withdrawal, and withdrawals are dropped outright.
* **Every result page must be opened** to find the job title at all, so this
  source is capped harder than the others.

Notices that only point at Selekcija.gov.hr are dropped: state bodies publish a
stub here and the real competition there, and keeping both means every such job
appears twice. A quarter of all results say so in the heading -- they are the
kind "OBAVIJEST" -- and those are dropped without being opened at all.
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
# The result item was rebuilt at some point between 0.1.0 and 2026-09-03: the
# title moved out of `searchListItemTitle` into a `resultTitle` div wrapping the
# anchor, and it now reads "NOTICE TYPE - Institution" rather than the bare
# institution. The old pattern matched nothing at all, so every notice came back
# with an empty company and a title mined from prose.
_TITLE = re.compile(r'class="resultTitle".*?<a[^>]*>(.*?)</a>', re.S)
_DATE = re.compile(r"(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})")
# A hidden relevance score sits inside the title markup; leaving it in produces
# titles like "Grad Samobor 0". It carries a `style` attribute now, which the
# old exact-match pattern did not allow -- hence `[^>]*`.
_SCORE = re.compile(r'<span class="score"[^>]*>.*?</span>', re.S)
# "JAVNI NATJECAJ - Grad Rab" -> the institution is what comes after the kind of
# notice. The kind is upper case, which is what keeps this off the institution
# name itself; it is kept in `raw` because it says whether a notice is an opening
# or the withdrawal of one.
_NOTICE_KIND = re.compile(r"^([A-ZČĆŽŠĐ][A-ZČĆŽŠĐ\s]{2,40})\s-\s")
# A withdrawn competition is not a job. Measured over 250 live results on
# 2026-09-04, the withdrawal arrives under three different kinds -- "PONISTENJE
# NATJECAJA", "ODLUKA O PONISTENJU NATJECAJA" and "DJELOMICNO PONISTENJE
# NATJECAJA" -- so the stem is what is matched, not any one of them. The
# diacritic-free spelling is allowed as well because the heading is only ever
# read back from the wire.
_WITHDRAWN = re.compile(r"PONIŠT|PONIST")
# "OBAVIJEST - Ministarstvo ..." is not a competition but the announcement that
# one is running in the central system. Measured over 520 live results on
# 2026-09-04: 137 notices carry this kind (26%), across 30-plus institutions and
# three spellings of it, and every single one of the 137 turned out to be a stub
# whose body points at Selekcija.gov.hr -- nought exceptions. They were already
# being thrown away by `_POINTS_AT_SELEKCIJA` below, but only after the page had
# been fetched, so a quarter of the enrich budget went on notices that could
# never yield a job. The heading says as much before any request is made.
_ANNOUNCES_ELSEWHERE = re.compile(r"^OBAVIJEST")
_BODY = re.compile(r'<div class="og-content">(.*?)</div>', re.S)

# The phrases a Croatian vacancy notice puts in front of the post itself. Which
# one matches says nothing about quality -- what matters is WHERE it matches, so
# these are searched for all at once and taken in the order they appear in the
# text (see `_mine_job_title`).
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
    # An opening bracket starts a gloss, never the post: "ucitelj (m/z)",
    # "(strucni radnik u sustavu socijalne zastite 2)".
    r"|\s\("
    # A head count or an envelope instruction hung off the end of the post:
    # "referent - materijalni knjigovoda - jedan izvrsitelj", "odgojitelj - ne
    # otvaraj".
    r"|\s[-–—]\s*(?=jedan|jedna|jedne|jednog|dva|dvije|dvoje|tri|više|ne\s)"  # noqa: RUF001
)
# Between the anchor and the post sit a colon, a dash, or an ordinal: "za radno
# mjesto: - ucitelj", "na radno mjesto 1. odgajatelj". Left in place, `_STOP`
# cuts at the digit or the colon and the whole title comes back empty -- which is
# what happened to a fifth of all notices.
_LEADING_JUNK = re.compile(
    r"^[\s:\-–—»„\"']*(?:\d+[.)]\s*)?[\s:\-–—»„\"']*"  # noqa: RUF001
    r"(?:(?:u|na|pri|za|radi|i|a|s|sa|o|od|do|iz)\b\s*)*"
    # "za izbor I IMENOVANJE ravnatelja" -- the post is the head, not the act of
    # appointing to it.
    r"(?:(?:imenovanje|izbor)\b\s*(?:i\s*)?)*",
    re.IGNORECASE,
)
# Punctuation only. Quotation marks are left alone: an institution in the post
# ("ravnatelj Gimnazije »Matija Mesić«") otherwise loses its closing mark.
_TRAILING_JUNK = re.compile(r"[\s\-–—,;:(]+$")  # noqa: RUF001
# What an anchor catches when it lands in the legal apparatus rather than on the
# post. Every entry was measured against live notices: a head count, a contract
# type, a cross-reference ("pod rednim brojem"), an organisational unit, the list
# of required documents, the envelope instruction. When a candidate reads like
# one of these, the NEXT occurrence of an anchor is tried -- the real
# announcement usually sits further down.
_NOT_A_POST = re.compile(
    r"^(?:jedan|jedna|jedne|jednog|jednu|dva|dvije|dvoje|tri|četiri|više)\b"
    r"|^(?:izvršitelj|zaposlenik|kandidat|pripravnik|radnik[ea]?\b)"
    r"|^(?:neodređeno|određeno|puno|nepuno)\b"
    r"|^(?:pod|radno mjesto|radna mjesta|upravni odjel|odjel|služb[au]|ured)\b"
    r"|kvalifikacij|stručn[au] sprem|studij|dokument|prilož|uvjet|natječaj|oglas"
    r"|prijav|omotnic|otvara|klasa|urbroj|rbr\b|rednim brojem|kako slijedi"
    r"|vrijeme|slijedeć|sljedeć|pristupnic|pristupnik"
    # A post is a noun phrase; an auxiliary verb means a whole sentence was
    # caught ("sadržan je", "objavljene su", "suglasni ste").
    r"|\b(?:je|su|ste|smo|sam|bi|će|biti)\b",
    re.IGNORECASE,
)
# Notices that leave a blank line to be filled in produce "_____________".
_HAS_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)

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

        found: dict[str, tuple[str, Any, str]] = {}
        withdrawn = 0
        announcements = 0
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
                heading = (
                    re.sub(r"\s+", " ", strip_html(title_match.group(1))).strip()
                    if title_match
                    else ""
                )
                kind_match = _NOTICE_KIND.match(heading)
                kind = kind_match.group(1).strip() if kind_match else ""
                if _WITHDRAWN.search(kind):
                    # A competition being called off, offered to the reader as a
                    # job. Dropped here rather than after the page is opened, so
                    # that the enrich budget below goes to real openings.
                    withdrawn += 1
                    continue
                if _ANNOUNCES_ELSEWHERE.match(kind):
                    # A pointer at a competition running in the central system.
                    # The body would be dropped anyway; skipping it here spends
                    # the enrich budget on notices that can actually be a job.
                    announcements += 1
                    continue
                institution = _NOTICE_KIND.sub("", heading)
                date_match = _DATE.search(chunk)
                found[url] = (
                    institution,
                    parse_date(date_match.group(1)) if date_match else None,
                    kind,
                )

        if withdrawn:
            ctx.report(f"  {withdrawn} withdrawn competitions skipped")
        if announcements:
            ctx.report(f"  {announcements} pointers at the central system skipped")
        ctx.report(f"  {len(found)} notices found; opening up to {cap}")

        postings: list[Posting] = []
        for url, (institution, published, kind) in list(found.items())[:cap]:
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
                    raw={"institution": institution, "notice_kind": kind},
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

    The same phrases also appear in the apparatus around the announcement -- the
    list of documents to enclose, the instruction on how to label the envelope --
    so finding one is not enough. Two rules keep the search on the announcement:
    occurrences are tried in the order they appear in the text, earliest first,
    and one that reads like boilerplate rather than a post is passed over.

    Measured over 90 live notices: 71 come back with the post, against 51 before,
    and the roughly twenty that used to arrive as legal prose -- "kandidati
    moraju priložiti sljedeće dokumente" was one -- are gone. What cannot be
    mined returns empty, and the caller falls back to the institution: a plain
    "Dječji vrtić Tići" is honest, "sadržan je" is not.
    """
    lowered = text.casefold()
    # Every occurrence of every anchor, in the order the reader meets them. The
    # earlier version took the first anchor in the tuple and its first hit, which
    # is how a title once came from the envelope instruction 9 000 characters in.
    occurrences = sorted(
        (found.start(), anchor)
        for anchor in _ANCHORS
        for found in re.finditer(re.escape(anchor), lowered)
    )
    for position, anchor in occurrences:
        tail = _LEADING_JUNK.sub("", text[position + len(anchor) :]).strip()
        stop = _STOP.search(tail)
        candidate = _TRAILING_JUNK.sub("", (tail[: stop.start()] if stop else tail[:80]).strip())
        if len(candidate) < 4 or not _HAS_LETTER.search(candidate):
            continue
        if _NOT_A_POST.search(candidate):
            continue
        return candidate
    return ""
