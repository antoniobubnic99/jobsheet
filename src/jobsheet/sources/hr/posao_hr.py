"""Posao.hr -- a Croatian commercial job board.

One official RSS feed covering the whole country. It offers the **30 newest ads
only**, with no pagination and no query parameters, so coverage depends entirely
on how often the user runs a search. That is a real limitation rather than a
configuration mistake, and it is surfaced in the interface rather than hidden.

The site's own pages are not scraped; only the feed it publishes is read.
"""

from __future__ import annotations

import re
from typing import Any

from jobsheet.core.dates import parse_date
from jobsheet.core.models import Posting
from jobsheet.sources._parse import parse_feed
from jobsheet.sources.base import FetchContext, Source, SourceError, SourceManifest

__all__ = ["PosaoHrSource"]

FEED = "https://www.posao.hr/rss/"

# The description is a fixed three-field run-on. Each field is optional, and the
# values themselves contain commas, so this is anchored on the labels.
_FIELDS = re.compile(
    r"Poslodavac:\s*(?P<company>.*?)"
    r"\s*(?:Mjesto rada:\s*(?P<location>.*?))?"
    r"\s*(?:Rok za prijavu:\s*(?P<deadline>.*?))?\s*$",
    re.S,
)


class PosaoHrSource(Source):
    manifest = SourceManifest(
        id="posao_hr",
        name="Posao.hr",
        homepage="https://www.posao.hr/",
        description="The 30 newest ads from a Croatian job board, whole country.",
        country="HR",
        params=[],
    )

    async def fetch(self, params: dict[str, Any], ctx: FetchContext) -> list[Posting]:
        ctx.report("Reading Posao.hr")
        text = await ctx.http.get_text(FEED)
        items = parse_feed(text)
        if not items:
            raise SourceError("Posao.hr returned nothing that looks like a feed")

        postings: list[Posting] = []
        for item in items[: ctx.max_items]:
            if not item.link or not item.title:
                continue
            found = _FIELDS.search(item.description)
            fields = found.groupdict() if found else {}

            postings.append(
                Posting(
                    source_id="posao_hr",
                    title=item.title,
                    url=item.link,
                    company=(fields.get("company") or "").strip(),
                    location=(fields.get("location") or "").strip(),
                    description=item.description,
                    posted_at=item.published,
                    deadline=parse_date((fields.get("deadline") or "").strip()),
                )
            )

        ctx.report(f"  {len(postings)} from Posao.hr")
        return postings
