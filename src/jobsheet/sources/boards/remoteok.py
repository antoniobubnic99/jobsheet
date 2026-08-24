"""RemoteOK.

Two quirks worth knowing:

* The response is a bare array whose **first element is a legal notice**, not a
  job. Treating it as one produces a row with no title and a link to their terms.
* Their terms ask for a visible link back to the original posting when their data
  is displayed. Every row carries the real ad URL, which satisfies that.
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

__all__ = ["RemoteOkSource"]

API = "https://remoteok.com/api"


class RemoteOkSource(Source):
    manifest = SourceManifest(
        id="remoteok",
        name="RemoteOK",
        homepage="https://remoteok.com/",
        description="Remote jobs, technology-heavy. One request returns the whole board.",
        rate_limit=2.0,
        params=[
            ParamSpec(
                name="tag",
                label="Tag",
                kind="text",
                placeholder="python",
                help="Optional. Keeps only ads carrying this tag.",
            ),
        ],
    )

    async def fetch(self, params: dict[str, Any], ctx: FetchContext) -> list[Posting]:
        tag = str(self.param(params, "tag") or "").strip().casefold()

        ctx.report("Reading RemoteOK")
        payload = await ctx.http.get_json(API)
        if not isinstance(payload, list):
            raise SourceError("RemoteOK returned no job list")

        postings: list[Posting] = []
        for job in payload:
            if not isinstance(job, dict):
                continue
            # The legal notice element. It has no position and must be skipped
            # before anything else, or it becomes a row in the spreadsheet.
            if "legal" in job and "position" not in job:
                continue

            title = job.get("position") or ""
            link = job.get("url") or job.get("apply_url") or ""
            if not title or not link:
                continue

            tags = [str(t) for t in (job.get("tags") or [])]
            if tag and tag not in {t.casefold() for t in tags}:
                continue

            salary = ""
            low, high = job.get("salary_min"), job.get("salary_max")
            if low and high:
                salary = f"{low}-{high}"

            postings.append(
                Posting(
                    source_id="remoteok",
                    title=title,
                    url=link,
                    company=job.get("company") or "",
                    location=job.get("location") or "",
                    workplace=Workplace.REMOTE,
                    description=strip_html(job.get("description") or ""),
                    salary=salary,
                    posted_at=parse_date(job.get("date")),
                    tags=tuple(tags),
                    raw={"id": job.get("id"), "slug": job.get("slug")},
                )
            )
            if len(postings) >= ctx.max_items:
                break

        ctx.report(f"  {len(postings)} from RemoteOK")
        return postings
