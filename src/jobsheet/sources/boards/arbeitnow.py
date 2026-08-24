"""Arbeitnow -- a European job board with an open, paginated API.

Useful counterweight to the mostly-American remote boards: a lot of its listings
are in Germany, Austria and the wider EU, including visa-sponsored roles.
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

__all__ = ["ArbeitnowSource"]

API = "https://www.arbeitnow.com/api/job-board-api"
MAX_PAGES = 10


class ArbeitnowSource(Source):
    manifest = SourceManifest(
        id="arbeitnow",
        name="Arbeitnow",
        homepage="https://www.arbeitnow.com/",
        description="European jobs, many in Germany and Austria, including visa-sponsored roles.",
        rate_limit=1.5,
        params=[
            ParamSpec(
                name="pages",
                label="How many pages to read",
                kind="number",
                default=3,
                help="Each page holds about 100 ads. More pages means a slower run.",
            ),
            ParamSpec(
                name="remote_only",
                label="Remote only",
                kind="boolean",
                default=False,
            ),
        ],
    )

    async def fetch(self, params: dict[str, Any], ctx: FetchContext) -> list[Posting]:
        pages = max(1, min(int(self.param(params, "pages") or 3), MAX_PAGES))
        remote_only = bool(self.param(params, "remote_only"))

        ctx.report("Reading Arbeitnow")
        postings: list[Posting] = []

        for page in range(1, pages + 1):
            payload = await ctx.http.get_json(f"{API}?page={page}")
            entries = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(entries, list):
                if page == 1:
                    raise SourceError("Arbeitnow returned no job list")
                break
            if not entries:
                break

            for job in entries:
                title = job.get("title") or ""
                link = job.get("url") or ""
                if not title or not link:
                    continue

                is_remote = bool(job.get("remote"))
                if remote_only and not is_remote:
                    continue

                postings.append(
                    Posting(
                        source_id="arbeitnow",
                        title=title,
                        url=link,
                        company=job.get("company_name") or "",
                        location=job.get("location") or "",
                        workplace=Workplace.REMOTE if is_remote else Workplace.ONSITE,
                        description=strip_html(job.get("description") or ""),
                        employment_type=", ".join(job.get("job_types") or []),
                        posted_at=_from_epoch(job.get("created_at")),
                        tags=tuple(job.get("tags") or []),
                        raw={"slug": job.get("slug")},
                    )
                )
                if len(postings) >= ctx.max_items:
                    break

            if len(postings) >= ctx.max_items:
                break

        ctx.report(f"  {len(postings)} from Arbeitnow")
        return postings


def _from_epoch(value: Any) -> Any:
    """Arbeitnow timestamps are epoch seconds."""
    if not isinstance(value, int | float):
        return None
    return datetime.fromtimestamp(value, tz=UTC).date()
