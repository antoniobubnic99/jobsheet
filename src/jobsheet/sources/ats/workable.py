"""Workable job boards."""

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

__all__ = ["WorkableSource"]

API = "https://apply.workable.com/api/v1/widget/accounts/{account}?details=true"


class WorkableSource(Source):
    manifest = SourceManifest(
        id="workable",
        name="Workable",
        homepage="https://www.workable.com/",
        description="Jobs from any company whose careers page runs on Workable.",
        params=[
            ParamSpec(
                name="account",
                label="Account name",
                kind="text",
                required=True,
                placeholder="examplecompany",
                help=(
                    "The first part of the company's jobs address, e.g. "
                    "apply.workable.com/examplecompany -> examplecompany"
                ),
            ),
            ParamSpec(
                name="company",
                label="Employer name",
                kind="text",
                help="Optional. Taken from the account if left empty.",
            ),
        ],
    )

    async def fetch(self, params: dict[str, Any], ctx: FetchContext) -> list[Posting]:
        account = str(self.param(params, "account") or "").strip().strip("/")
        if not account:
            raise SourceError("no account name given")

        ctx.report(f"Reading Workable board: {account}")
        payload = await ctx.http.get_json(API.format(account=account))
        if not isinstance(payload, dict):
            raise SourceError(f"Workable account {account!r} returned nothing usable")

        company = (
            str(self.param(params, "company") or "").strip() or payload.get("name") or account
        )
        jobs = payload.get("jobs")
        if not isinstance(jobs, list):
            raise SourceError(f"Workable account {account!r} returned no job list")

        postings: list[Posting] = []
        for job in jobs[: ctx.max_items]:
            title = job.get("title") or ""
            url = job.get("url") or job.get("application_url") or ""
            if not title or not url:
                continue

            location = job.get("location") or {}
            place = ", ".join(
                part
                for part in (location.get("city"), location.get("region"), location.get("country"))
                if part
            )
            telecommuting = bool(location.get("telecommuting") or job.get("telecommuting"))

            postings.append(
                Posting(
                    source_id="workable",
                    title=title,
                    url=url,
                    company=company,
                    location=place,
                    workplace=Workplace.REMOTE if telecommuting else Workplace.UNKNOWN,
                    description=strip_html(job.get("description") or ""),
                    employment_type=job.get("type") or "",
                    posted_at=parse_date(job.get("published_on") or job.get("created_at")),
                    tags=tuple(t for t in (job.get("department"),) if t),
                    raw={"account": account, "shortcode": job.get("shortcode")},
                )
            )

        ctx.report(f"  {len(postings)} from {account}")
        return postings
