"""One search, end to end: fetch, de-duplicate, filter, enrich, build rows.

The order of the steps is the whole design, and it is chosen to spend as few
requests as possible on ads nobody wants:

1. **Fetch** every source concurrently. One failing source is reported and
   skipped; it never takes down the run.
2. **De-duplicate** against what is already in the spreadsheet *before* anything
   expensive happens. An ad already on the list needs no further attention.
3. **Filter on keywords and location**, which is free -- it reads text already in
   hand.
4. **Enrich** only what survived, and only for sources that have more to give.
   This is the one step that costs a request per ad, so it is last and capped.
5. **Apply the hard filters**, which need the enriched fields to mean anything.

Anything rejected is reported with its reason rather than silently dropped, so a
user who expected an ad to appear can see why it did not.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from jobsheet.core.http import HttpClient
from jobsheet.core.matching import (
    Match,
    Rejection,
    SearchProfile,
    flags_for,
    location_matches,
    match,
    rejection_for,
    sentence_case,
)
from jobsheet.core.models import Posting
from jobsheet.sheet.row import JobRow
from jobsheet.sources import registry
from jobsheet.sources.base import FetchContext

__all__ = ["RunReport", "SourceRequest", "build_note", "run_search"]


@dataclass
class SourceRequest:
    """One source to run, with the answers to its declared parameters."""

    source_id: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunReport:
    """What one search did, in enough detail to explain itself to the user."""

    fetched: int = 0
    duplicates: int = 0
    rows: list[JobRow] = field(default_factory=list)
    rejected: list[tuple[Posting, Rejection]] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def new_count(self) -> int:
        return len(self.rows)


def build_note(posting: Posting, hit: Match, profile: SearchProfile, *, today: date) -> str:
    """The one explanatory cell: where, until when, on what terms, and why shown.

    Kept to a single line because it lives in a spreadsheet cell that the user
    reads at a glance, not a report they sit down with.
    """
    parts: list[str] = []
    if posting.location:
        parts.append(sentence_case(posting.location))
    if posting.deadline:
        parts.append(f"closes {posting.deadline.isoformat()}")
    if posting.employment_type:
        parts.append(posting.employment_type.split(";")[0].strip().lower())
    parts.append(posting.source_id)
    if hit.term:
        parts.append(f'matched "{hit.term}" in the {hit.field}')
    parts.extend(flags_for(posting, profile, today=today))
    return " · ".join(part for part in parts if part)


async def _fetch_one(
    request: SourceRequest, ctx: FetchContext, report: RunReport
) -> list[Posting]:
    """Run one source, converting any failure into a reported error."""
    try:
        source = registry.get(request.source_id)()
    except KeyError as error:
        report.errors[request.source_id] = str(error)
        return []
    try:
        return await source.fetch(request.params, ctx)
    except Exception as error:
        report.errors[request.source_id] = f"{type(error).__name__}: {error}"
        ctx.report(f"  ! {request.source_id} failed: {type(error).__name__}")
        return []


async def run_search(
    requests: list[SourceRequest],
    profile: SearchProfile | None = None,
    *,
    existing: list[JobRow] | None = None,
    http: HttpClient | None = None,
    today: date | None = None,
    max_items: int = 200,
    max_enrich: int = 40,
    on_progress: Any = None,
) -> RunReport:
    """Collect, filter and turn into spreadsheet rows. Writes nothing to disk."""
    profile = profile or SearchProfile()
    existing = existing or []
    today = today or date.today()
    report = RunReport()

    seen_urls = {row.dedup_key for row in existing}
    seen_pairs = {row.posting.secondary_key for row in existing}

    owns_client = http is None
    client = http or HttpClient()
    ctx = FetchContext(
        http=client,
        today=today,
        max_items=max_items,
        max_enrich=max_enrich,
        on_progress=on_progress or (lambda message: None),
    )

    try:
        ctx.report(f"Searching {len(requests)} source(s)")
        harvests = await asyncio.gather(
            *(_fetch_one(request, ctx, report) for request in requests)
        )

        # Step 2: de-duplicate before any per-ad work.
        candidates: list[tuple[Posting, Match]] = []
        for harvest in harvests:
            for posting in harvest:
                report.fetched += 1
                key = posting.dedup_key
                if not key or key in seen_urls:
                    report.duplicates += 1
                    continue
                seen_urls.add(key)

                # Step 3: free filters.
                hit = match(posting, profile)
                if hit is None or not location_matches(posting, profile):
                    continue
                candidates.append((posting, hit))

        ctx.report(f"Reviewed {report.fetched}; {len(candidates)} match what you asked for")

        # Step 4: the expensive pass, only for survivors, only where it helps.
        enriched: list[tuple[Posting, Match]] = []
        budget = max_enrich
        for posting, hit in candidates:
            source_cls = registry.load_all().get(posting.source_id.split(":", 1)[0])
            if source_cls and source_cls.manifest.supports_enrich and budget > 0:
                budget -= 1
                ctx.report(f"  checking details ({max_enrich - budget}/{max_enrich})")
                posting = await source_cls().enrich(posting, ctx)
            enriched.append((posting, hit))

        # Step 5: hard filters, which need the enriched fields.
        for posting, hit in enriched:
            if rejection := rejection_for(posting, hit, profile, today=today):
                report.rejected.append((posting, rejection))
                continue

            # One vacancy can be published under several ad numbers, which gives
            # each copy its own URL. This catches those within a single run.
            pair = posting.secondary_key
            if pair in seen_pairs:
                report.rejected.append(
                    (posting, Rejection(code="duplicate_of_another_ad"))
                )
                continue
            seen_pairs.add(pair)

            report.rows.append(
                JobRow(
                    posting=posting.model_copy(
                        update={
                            "title": sentence_case(posting.title) or "(untitled)",
                            "company": sentence_case(posting.company),
                        }
                    ),
                    found_at=today,
                    category=hit.group,
                    note=build_note(posting, hit, profile, today=today),
                )
            )

        ctx.report(f"{report.new_count} new, {len(report.rejected)} filtered out")
        return report
    finally:
        if owns_client:
            await client.aclose()
