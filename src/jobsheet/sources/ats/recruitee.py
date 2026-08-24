"""Recruitee job boards.

Widely used across central and southeastern Europe, so this one carries a lot of
weight for users outside the large English-language boards.
"""

from __future__ import annotations

from typing import Any

from jobsheet.core.dates import parse_date
from jobsheet.core.models import Posting, Workplace
from jobsheet.sources._parse import strip_html
from jobsheet.sources.base import (
    FetchContext,
    ParamSpec,
    Source,
    SourceError,
    SourceManifest,
)

__all__ = ["RecruiteeSource"]

API = "https://{company}.recruitee.com/api/offers/"


class RecruiteeSource(Source):
    manifest = SourceManifest(
        id="recruitee",
        name="Recruitee",
        homepage="https://recruitee.com/",
        description="Jobs from any company whose careers page runs on Recruitee.",
        params=[
            ParamSpec(
                name="company",
                label="Company name",
                kind="text",
                required=True,
                placeholder="examplecompany",
                help=(
                    "The first part of the company's careers address, e.g. "
                    "examplecompany.recruitee.com -> examplecompany"
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

        ctx.report(f"Reading Recruitee board: {slug}")
        payload = await ctx.http.get_json(API.format(company=slug))
        offers = payload.get("offers") if isinstance(payload, dict) else None
        if not isinstance(offers, list):
            raise SourceError(f"Recruitee board {slug!r} returned no offers")

        postings: list[Posting] = []
        for offer in offers[: ctx.max_items]:
            title = offer.get("title") or ""
            url = offer.get("careers_url") or offer.get("careers_apply_url") or ""
            if not title or not url:
                continue

            place = ", ".join(
                part for part in (offer.get("city"), offer.get("country")) if part
            ) or (offer.get("location") or "")

            postings.append(
                Posting(
                    source_id="recruitee",
                    title=title,
                    url=url,
                    company=company,
                    location=place,
                    workplace=Workplace.REMOTE if offer.get("remote") else Workplace.UNKNOWN,
                    description=strip_html(offer.get("description") or ""),
                    employment_type=offer.get("employment_type_code") or "",
                    education=offer.get("education_code") or "",
                    posted_at=parse_date(offer.get("published_at") or offer.get("created_at")),
                    tags=tuple(t for t in (offer.get("department"),) if t),
                    raw={"company": slug, "id": offer.get("id")},
                )
            )

        ctx.report(f"  {len(postings)} from {slug}")
        return postings
