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
from collections.abc import Sequence
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
from jobsheet.sources.base import FetchContext, Phase, Source

__all__ = ["DUPLICATE_HINT", "RunReport", "SourceRequest", "build_note", "run_search"]

# What the note says when an ad looks like one already on the list but is not
# provably the same. It is a remark, never a reason to drop anything: see the
# long note in `run_search` about why the pair key cannot be trusted across runs.
DUPLICATE_HINT = "possible duplicate of an ad you already have"


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

    # How many ads each source handed over, before any filtering. Kept per
    # source because "you got fewer results today" is nearly always one source
    # having gone quiet, and a total cannot tell the user which one.
    harvested: dict[str, int] = field(default_factory=dict)

    @property
    def new_count(self) -> int:
        return len(self.rows)


def build_note(
    posting: Posting,
    hit: Match,
    profile: SearchProfile,
    *,
    today: date,
    remarks: Sequence[str] = (),
) -> str:
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
    parts.extend(remarks)
    return " · ".join(part for part in parts if part)


async def _fetch_one(
    request: SourceRequest, ctx: FetchContext, report: RunReport
) -> list[Posting]:
    """Run one source, converting any failure into a reported error."""
    ctx.step(request.source_id, Phase.FETCHING)
    try:
        source = registry.get(request.source_id)()
    except KeyError as error:
        report.errors[request.source_id] = str(error)
        ctx.step(request.source_id, Phase.FAILED)
        return []
    try:
        postings = await source.fetch(request.params, ctx)
    except Exception as error:
        report.errors[request.source_id] = f"{type(error).__name__}: {error}"
        ctx.report(f"  ! {request.source_id} failed: {type(error).__name__}")
        ctx.step(request.source_id, Phase.FAILED)
        return []
    report.harvested[request.source_id] = len(postings)
    ctx.step(request.source_id, Phase.FILTERING)
    return postings


def _enricher(posting: Posting) -> type[Source] | None:
    """The class that could open this ad's own page, if opening it would help."""
    source_cls = registry.load_all().get(posting.source_id.split(":", 1)[0])
    return source_cls if source_cls and source_cls.manifest.supports_enrich else None


def _step_all(
    ctx: FetchContext,
    requests: list[SourceRequest],
    report: RunReport,
    phase: str,
    *,
    per_source: dict[str, int] | None = None,
    done: int = 0,
    total: int = 0,
) -> None:
    """Move every source that is still going into the same phase.

    Steps 3 to 5 are one pass over everything rather than a pass per source, so
    from here on the sources advance together. A source that already failed is
    left alone: its bar has stopped where it stopped, and marching it to `done`
    would tell the user it finished.
    """
    for request in requests:
        if request.source_id in report.errors:
            continue
        count = (per_source or {}).get(request.source_id, total)
        ctx.step(request.source_id, phase, done, count)


async def run_search(
    requests: list[SourceRequest],
    profile: SearchProfile | None = None,
    *,
    existing: list[JobRow] | None = None,
    forgotten: set[str] | None = None,
    filtered_before: set[str] | None = None,
    http: HttpClient | None = None,
    today: date | None = None,
    max_items: int = 200,
    max_enrich: int = 40,
    on_progress: Any = None,
    on_step: Any = None,
) -> RunReport:
    """Collect, filter and turn into spreadsheet rows. Writes nothing to disk.

    Three kinds of memory decide what "already seen" means, and they are
    deliberately separate:

    * `existing` -- ads on the list right now, whatever their status. An ad the
      user skipped is still an ad they have looked at, so it stays here.
    * `forgotten` -- ads the user deleted outright. Without this the next search
      hands the same ad straight back, which reads as the delete not working.
    * `filtered_before` -- ads a hard filter already turned away. Re-fetching
      those is free; re-*enriching* them is a request each, every run, out of
      the same budget the ads the user wants are competing for.
    """
    profile = profile or SearchProfile()
    existing = existing or []
    today = today or date.today()
    report = RunReport()

    seen_urls = {row.dedup_key for row in existing} | (forgotten or set())
    skip_keys = filtered_before or set()

    # Two pair sets, doing two different jobs -- and the split is the fix for a
    # bug that had this reading as one.
    #
    # `(title, company)` is a strong signal *inside* one run: the URL key has
    # already separated the ads, so a repeat here really is one vacancy filed
    # under two ad numbers. Across runs it is nothing of the sort. Two genuine
    # openings for "Software Engineer" at one employer, months apart, share it --
    # and seeding the reject set from the whole spreadsheet meant the second one
    # was dropped, silently, for ever.
    #
    # So: reject within the run, remark across runs, and let the user decide.
    seen_pairs: set[tuple[str, str]] = set()
    known_pairs = {row.posting.secondary_key for row in existing}

    owns_client = http is None
    client = http or HttpClient()
    ctx = FetchContext(
        http=client,
        today=today,
        max_items=max_items,
        max_enrich=max_enrich,
        on_progress=on_progress or (lambda message: None),
        on_step=on_step or (lambda source_id, phase, done, total: None),
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
                # An ad with no link is not a duplicate of anything; it is an ad
                # nothing can address. Counting it as a duplicate inflated that
                # number and left the ad with no reason for going.
                if not key:
                    report.rejected.append((posting, Rejection(code="no_url")))
                    continue
                if key in seen_urls:
                    report.duplicates += 1
                    continue
                seen_urls.add(key)

                # Turned away by a hard filter on an earlier run, under the same
                # search. Re-deciding it would cost a detail request per ad and
                # reach the same answer.
                if key in skip_keys:
                    report.rejected.append(
                        (posting, Rejection(code="filtered_out_before"))
                    )
                    continue

                # Step 3: free filters.
                hit = match(posting, profile)
                if hit is None or not location_matches(posting, profile):
                    continue
                candidates.append((posting, hit))

        ctx.report(f"Reviewed {report.fetched}; {len(candidates)} match what you asked for")
        _step_all(ctx, requests, report, Phase.FILTERING, done=1, total=1)

        # Step 4: the expensive pass, only for survivors, only where it helps.
        enriched: list[tuple[Posting, Match]] = []
        budget = max_enrich
        # How many detail pages each source is about to be asked for, so its bar
        # can move per ad rather than sitting still through the slowest step.
        done_per_source: dict[str, int] = {}
        total_per_source: dict[str, int] = {}
        for posting, _hit in candidates:
            if _enricher(posting) is not None:
                source_id = posting.source_id
                total_per_source[source_id] = total_per_source.get(source_id, 0) + 1
        _step_all(ctx, requests, report, Phase.DETAILS, per_source=total_per_source, done=0)

        for posting, hit in candidates:
            source_cls = _enricher(posting)
            if source_cls is not None and budget > 0:
                budget -= 1
                ctx.report(f"  checking details ({max_enrich - budget}/{max_enrich})")
                posting = await source_cls().enrich(posting, ctx)
                seen = done_per_source.get(posting.source_id, 0) + 1
                done_per_source[posting.source_id] = seen
                ctx.step(
                    posting.source_id,
                    Phase.DETAILS,
                    seen,
                    total_per_source.get(posting.source_id, seen),
                )
            enriched.append((posting, hit))

        # Step 5: hard filters, which need the enriched fields.
        for posting, hit in enriched:
            if rejection := rejection_for(posting, hit, profile, today=today):
                report.rejected.append((posting, rejection))
                continue

            # One vacancy published under several ad numbers gets a URL per copy.
            # Within this run that is the only thing the pair key can mean.
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
                    note=build_note(
                        posting,
                        hit,
                        profile,
                        today=today,
                        remarks=[DUPLICATE_HINT] if pair in known_pairs else [],
                    ),
                )
            )

        ctx.report(f"{report.new_count} new, {len(report.rejected)} filtered out")
        _step_all(ctx, requests, report, Phase.DONE)
        return report
    finally:
        if owns_client:
            await client.aclose()
