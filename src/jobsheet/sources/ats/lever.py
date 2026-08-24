"""Lever job boards.

Lever's public postings endpoint needs no key and returns a plain list rather
than a wrapper object. Dates arrive as epoch milliseconds.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from jobsheet.core.models import Posting, Workplace
from jobsheet.sources._parse import strip_html
from jobsheet.sources.base import (
    FetchContext,
    ParamSpec,
    Source,
    SourceError,
    SourceManifest,
)

__all__ = ["LeverSource"]

API = "https://api.lever.co/v0/postings/{company}?mode=json"

_REMOTE_HINTS = ("remote", "anywhere", "distributed")


class LeverSource(Source):
    manifest = SourceManifest(
        id="lever",
        name="Lever",
        homepage="https://www.lever.co/",
        description="Jobs from any company whose careers page runs on Lever.",
        params=[
            ParamSpec(
                name="company",
                label="Company name",
                kind="text",
                required=True,
                placeholder="examplecompany",
                help=(
                    "The last part of the company's jobs address, e.g. "
                    "jobs.lever.co/examplecompany -> examplecompany"
                ),
            ),
            ParamSpec(
                name="display_name",
                label="Employer name",
                kind="text",
                help="Optional. Shown in the spreadsheet instead of the slug.",
            ),
        ],
    )

    async def fetch(self, params: dict[str, Any], ctx: FetchContext) -> list[Posting]:
        slug = str(self.param(params, "company") or "").strip().strip("/")
        if not slug:
            raise SourceError("no company name given")
        company = str(self.param(params, "display_name") or "").strip() or slug

        ctx.report(f"Reading Lever board: {slug}")
        payload = await ctx.http.get_json(API.format(company=slug))
        if not isinstance(payload, list):
            raise SourceError(f"Lever board {slug!r} returned no job list")

        postings: list[Posting] = []
        for job in payload[: ctx.max_items]:
            url = job.get("hostedUrl") or job.get("applyUrl") or ""
            title = job.get("text") or ""
            if not url or not title:
                continue

            categories = job.get("categories") or {}
            location = categories.get("location") or ""
            team = categories.get("team") or ""
            commitment = categories.get("commitment") or ""

            postings.append(
                Posting(
                    source_id="lever",
                    title=title,
                    url=url,
                    company=company,
                    location=location,
                    workplace=_workplace(f"{location} {categories.get('workplaceType', '')}"),
                    description=job.get("descriptionPlain")
                    or strip_html(job.get("description") or ""),
                    employment_type=commitment,
                    posted_at=_from_millis(job.get("createdAt")),
                    tags=tuple(t for t in (team, commitment) if t),
                    raw={"company": slug, "id": job.get("id"), "categories": categories},
                )
            )

        ctx.report(f"  {len(postings)} from {slug}")
        return postings


def _from_millis(value: Any) -> Any:
    """Lever timestamps are epoch milliseconds, not seconds."""
    if not isinstance(value, int | float):
        return None
    return datetime.fromtimestamp(value / 1000, tz=UTC).date()


def _workplace(text: str) -> Workplace:
    lowered = text.casefold()
    return Workplace.REMOTE if any(h in lowered for h in _REMOTE_HINTS) else Workplace.UNKNOWN
