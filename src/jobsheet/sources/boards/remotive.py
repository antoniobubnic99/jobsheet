"""Remotive -- a curated board of remote jobs.

Remotive asks API users to cache results and not to poll aggressively. JobSheet
runs on demand rather than on a timer, and the shared client rate-limits per
host, so a normal run is a single request.
"""

from __future__ import annotations

from typing import Any

from jobsheet.core.dates import parse_date
from jobsheet.core.models import Posting, Workplace
from jobsheet.sources._parse import strip_html
from jobsheet.sources.base import (
    Choice,
    FetchContext,
    ParamSpec,
    Source,
    SourceError,
    SourceManifest,
)

__all__ = ["RemotiveSource"]

API = "https://remotive.com/api/remote-jobs"

CATEGORIES = [
    "software-dev",
    "customer-support",
    "design",
    "marketing",
    "sales",
    "product",
    "business",
    "data",
    "devops",
    "finance-legal",
    "human-resources",
    "qa",
    "writing",
    "all-others",
]


class RemotiveSource(Source):
    manifest = SourceManifest(
        id="remotive",
        name="Remotive",
        homepage="https://remotive.com/",
        description="Remote jobs, mostly technology and mostly English-speaking.",
        rate_limit=2.0,
        params=[
            ParamSpec(
                name="search",
                label="Search words",
                kind="text",
                placeholder="data analyst",
                help="Leave empty to get everything and filter locally instead.",
            ),
            ParamSpec(
                name="category",
                label="Category",
                kind="select",
                choices=[Choice(value="", label="Any")]
                + [Choice(value=c, label=c.replace("-", " ").title()) for c in CATEGORIES],
            ),
            ParamSpec(
                name="limit",
                label="How many at most",
                kind="number",
                default=100,
            ),
        ],
    )

    async def fetch(self, params: dict[str, Any], ctx: FetchContext) -> list[Posting]:
        query: dict[str, str] = {}
        if search := str(self.param(params, "search") or "").strip():
            query["search"] = search
        if category := str(self.param(params, "category") or "").strip():
            query["category"] = category
        limit = min(int(self.param(params, "limit") or 100), ctx.max_items)
        query["limit"] = str(limit)

        url = API + "?" + "&".join(f"{k}={v}" for k, v in query.items())
        ctx.report("Reading Remotive")
        payload = await ctx.http.get_json(url)
        jobs = payload.get("jobs") if isinstance(payload, dict) else None
        if not isinstance(jobs, list):
            raise SourceError("Remotive returned no job list")

        postings: list[Posting] = []
        for job in jobs[:limit]:
            title = job.get("title") or ""
            link = job.get("url") or ""
            if not title or not link:
                continue

            postings.append(
                Posting(
                    source_id="remotive",
                    title=title,
                    url=link,
                    company=job.get("company_name") or "",
                    # Everything on Remotive is remote by definition; this field
                    # says which time zones or countries they will hire from.
                    location=job.get("candidate_required_location") or "",
                    workplace=Workplace.REMOTE,
                    description=strip_html(job.get("description") or ""),
                    employment_type=job.get("job_type") or "",
                    salary=job.get("salary") or "",
                    posted_at=parse_date(job.get("publication_date")),
                    tags=tuple(job.get("tags") or []),
                    raw={"id": job.get("id"), "category": job.get("category")},
                )
            )

        ctx.report(f"  {len(postings)} from Remotive")
        return postings
