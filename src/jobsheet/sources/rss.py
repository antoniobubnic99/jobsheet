"""Any RSS or Atom feed the user can find.

This is the source that makes JobSheet useful to someone the maintainers have
never met. Most job boards, company blogs and government notice pages still
publish a feed; one connector covers all of them without anyone writing code.

It stays deliberately dumb. It does not guess which part of a description is the
employer or the location, because guessing wrong is worse than leaving a field
empty -- the keyword filter reads the description anyway, and a wrong employer in
the spreadsheet is a lie the user has to notice and correct.
"""

from __future__ import annotations

from typing import Any

from jobsheet.core.models import Posting
from jobsheet.sources._parse import parse_feed
from jobsheet.sources.base import (
    FetchContext,
    ParamSpec,
    Source,
    SourceError,
    SourceManifest,
)

__all__ = ["RssSource"]


class RssSource(Source):
    manifest = SourceManifest(
        id="rss",
        name="RSS or Atom feed",
        homepage="https://en.wikipedia.org/wiki/RSS",
        description=(
            "Paste the address of any job feed. Works with most job boards, "
            "company career pages and public notice boards."
        ),
        params=[
            ParamSpec(
                name="url",
                label="Feed address",
                kind="url",
                required=True,
                placeholder="https://example.com/jobs/feed.xml",
                help="Look for an RSS or Atom link on the site's jobs page.",
            ),
            ParamSpec(
                name="label",
                label="Name for this feed",
                kind="text",
                placeholder="Example Ltd careers",
                help="Shown in the source column so you can tell your feeds apart.",
            ),
            ParamSpec(
                name="company",
                label="Employer",
                kind="text",
                help=(
                    "Fill this in when the feed belongs to one company. "
                    "Leave empty for a job board covering many employers."
                ),
            ),
            ParamSpec(
                name="encoding",
                label="Text encoding",
                kind="text",
                placeholder="utf-8",
                help="Only needed if the feed shows garbled characters.",
            ),
        ],
    )

    async def fetch(self, params: dict[str, Any], ctx: FetchContext) -> list[Posting]:
        url = str(self.param(params, "url") or "").strip()
        if not url:
            raise SourceError("no feed address given")

        label = str(self.param(params, "label") or "").strip()
        company = str(self.param(params, "company") or "").strip()
        encoding = str(self.param(params, "encoding") or "").strip() or None

        ctx.report(f"Reading feed: {label or url}")
        text = await ctx.http.get_text(url, encoding=encoding)
        items = parse_feed(text)
        if not items:
            raise SourceError(f"{url} returned nothing that looks like a feed")

        source_id = f"rss:{label}" if label else "rss"
        postings: list[Posting] = []
        for item in items[: ctx.max_items]:
            if not item.link or not item.title:
                continue
            postings.append(
                Posting(
                    source_id=source_id,
                    title=item.title,
                    url=item.link,
                    # Only the user knows whether this feed belongs to one
                    # employer. The feed's own author field is the publisher,
                    # which on a job board is the board, not the company hiring --
                    # so it is kept for reference but never presented as the
                    # employer.
                    company=company,
                    description=item.description,
                    posted_at=item.published,
                    tags=tuple(item.categories),
                    raw={"feed": url, "categories": item.categories, "author": item.author},
                )
            )

        ctx.report(f"  {len(postings)} from {label or url}")
        return postings
