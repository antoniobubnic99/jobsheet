"""SmartRecruiters job boards.

The postings endpoint is public and paginated. Unlike the other connectors it
does not return an ad URL, so the public posting address is reconstructed from
the company identifier and the posting id -- documented and stable, but worth
knowing if the link format ever changes.
"""

from __future__ import annotations

from typing import Any

from jobsheet.core.dates import parse_date
from jobsheet.core.models import Posting, Workplace
from jobsheet.sources.base import (
    FetchContext,
    ParamSpec,
    Source,
    SourceError,
    SourceManifest,
)

__all__ = ["SmartRecruitersSource"]

API = "https://api.smartrecruiters.com/v1/companies/{company}/postings?limit={limit}&offset={offset}"
PUBLIC_URL = "https://jobs.smartrecruiters.com/{company}/{posting}"

PAGE_SIZE = 100


class SmartRecruitersSource(Source):
    manifest = SourceManifest(
        id="smartrecruiters",
        name="SmartRecruiters",
        homepage="https://www.smartrecruiters.com/",
        description="Jobs from any company whose careers page runs on SmartRecruiters.",
        params=[
            ParamSpec(
                name="company",
                label="Company identifier",
                kind="text",
                required=True,
                placeholder="ExampleCompany",
                help=(
                    "The part after the domain in the company's jobs address, e.g. "
                    "jobs.smartrecruiters.com/ExampleCompany -> ExampleCompany. "
                    "Capitalisation matters here."
                ),
            ),
            ParamSpec(
                name="display_name",
                label="Employer name",
                kind="text",
                help="Optional. Shown in the spreadsheet instead of the identifier.",
            ),
        ],
    )

    async def fetch(self, params: dict[str, Any], ctx: FetchContext) -> list[Posting]:
        identifier = str(self.param(params, "company") or "").strip().strip("/")
        if not identifier:
            raise SourceError("no company identifier given")
        company = str(self.param(params, "display_name") or "").strip() or identifier

        ctx.report(f"Reading SmartRecruiters board: {identifier}")
        postings: list[Posting] = []
        offset = 0

        while len(postings) < ctx.max_items:
            page = await ctx.http.get_json(
                API.format(company=identifier, limit=PAGE_SIZE, offset=offset)
            )
            content = page.get("content") if isinstance(page, dict) else None
            if not isinstance(content, list):
                if offset == 0:
                    raise SourceError(f"SmartRecruiters {identifier!r} returned no postings")
                break
            if not content:
                break

            for job in content:
                title = job.get("name") or ""
                posting_id = job.get("id") or ""
                if not title or not posting_id:
                    continue

                location = job.get("location") or {}
                place = ", ".join(
                    part for part in (location.get("city"), location.get("country")) if part
                )

                postings.append(
                    Posting(
                        source_id="smartrecruiters",
                        title=title,
                        url=PUBLIC_URL.format(company=identifier, posting=posting_id),
                        company=company,
                        location=place,
                        workplace=(
                            Workplace.REMOTE if location.get("remote") else Workplace.UNKNOWN
                        ),
                        employment_type=(job.get("typeOfEmployment") or {}).get("label", ""),
                        posted_at=parse_date(job.get("releasedDate")),
                        tags=tuple(
                            t for t in ((job.get("department") or {}).get("label", ""),) if t
                        ),
                        raw={"company": identifier, "id": posting_id, "ref": job.get("ref")},
                    )
                )

            if len(content) < PAGE_SIZE:
                break
            offset += PAGE_SIZE

        postings = postings[: ctx.max_items]
        ctx.report(f"  {len(postings)} from {identifier}")
        return postings
