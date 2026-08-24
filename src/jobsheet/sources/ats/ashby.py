"""Ashby job boards."""

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

__all__ = ["AshbySource"]

API = "https://api.ashbyhq.com/posting-api/job-board/{board}"


class AshbySource(Source):
    manifest = SourceManifest(
        id="ashby",
        name="Ashby",
        homepage="https://www.ashbyhq.com/",
        description="Jobs from any company whose careers page runs on Ashby.",
        params=[
            ParamSpec(
                name="board",
                label="Board name",
                kind="text",
                required=True,
                placeholder="examplecompany",
                help=(
                    "The last part of the company's board address, e.g. "
                    "jobs.ashbyhq.com/examplecompany -> examplecompany"
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

        ctx.report(f"Reading Ashby board: {board}")
        payload = await ctx.http.get_json(API.format(board=board))
        jobs = payload.get("jobs") if isinstance(payload, dict) else None
        if not isinstance(jobs, list):
            raise SourceError(f"Ashby board {board!r} returned no job list")

        postings: list[Posting] = []
        for job in jobs[: ctx.max_items]:
            url = job.get("jobUrl") or ""
            title = job.get("title") or ""
            if not url or not title:
                continue

            department = job.get("department") or ""
            team = job.get("team") or ""

            postings.append(
                Posting(
                    source_id="ashby",
                    title=title,
                    url=url,
                    company=company,
                    location=job.get("location") or "",
                    # Ashby states this outright, so there is nothing to infer.
                    workplace=Workplace.REMOTE if job.get("isRemote") else Workplace.UNKNOWN,
                    description=job.get("descriptionPlain")
                    or strip_html(job.get("descriptionHtml") or ""),
                    employment_type=job.get("employmentType") or "",
                    posted_at=parse_date(job.get("publishedAt") or job.get("updatedAt")),
                    tags=tuple(t for t in (department, team) if t),
                    raw={"board": board, "id": job.get("id")},
                )
            )

        ctx.report(f"  {len(postings)} from {board}")
        return postings
