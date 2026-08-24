"""Greenhouse job boards.

Greenhouse publishes every board it hosts through a documented, unauthenticated
API. The only thing the user needs is the board token, which is the slug in the
public board URL: `job-boards.greenhouse.io/<token>`.
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

__all__ = ["GreenhouseSource"]

API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"

_REMOTE_HINTS = ("remote", "anywhere", "distributed")


class GreenhouseSource(Source):
    manifest = SourceManifest(
        id="greenhouse",
        name="Greenhouse",
        homepage="https://www.greenhouse.io/",
        description="Jobs from any company whose careers page runs on Greenhouse.",
        params=[
            ParamSpec(
                name="board",
                label="Board name",
                kind="text",
                required=True,
                placeholder="examplecompany",
                help=(
                    "The last part of the company's board address, e.g. "
                    "job-boards.greenhouse.io/examplecompany -> examplecompany"
                ),
            ),
            ParamSpec(
                name="company",
                label="Employer name",
                kind="text",
                help="Optional. Shown in the spreadsheet instead of the board name.",
            ),
        ],
    )

    async def fetch(self, params: dict[str, Any], ctx: FetchContext) -> list[Posting]:
        board = str(self.param(params, "board") or "").strip().strip("/")
        if not board:
            raise SourceError("no board name given")
        company = str(self.param(params, "company") or "").strip() or board

        ctx.report(f"Reading Greenhouse board: {board}")
        payload = await ctx.http.get_json(API.format(token=board))
        jobs = payload.get("jobs") if isinstance(payload, dict) else None
        if not isinstance(jobs, list):
            raise SourceError(f"Greenhouse board {board!r} returned no job list")

        postings: list[Posting] = []
        for job in jobs[: ctx.max_items]:
            url = job.get("absolute_url") or ""
            title = job.get("title") or ""
            if not url or not title:
                continue

            location = (job.get("location") or {}).get("name", "")
            departments = [d.get("name", "") for d in job.get("departments") or [] if d.get("name")]

            postings.append(
                Posting(
                    source_id="greenhouse",
                    title=title,
                    url=url,
                    company=company,
                    location=location,
                    workplace=_workplace(location),
                    # `content` is HTML, escaped once by the API.
                    description=strip_html(job.get("content") or ""),
                    posted_at=parse_date(job.get("updated_at") or job.get("first_published")),
                    tags=tuple(departments),
                    raw={"board": board, "id": job.get("id"), "departments": departments},
                )
            )

        ctx.report(f"  {len(postings)} from {board}")
        return postings


def _workplace(location: str) -> Workplace:
    lowered = location.casefold()
    return Workplace.REMOTE if any(h in lowered for h in _REMOTE_HINTS) else Workplace.UNKNOWN
