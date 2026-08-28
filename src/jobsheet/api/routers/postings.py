"""The collected jobs, as the results table reads them.

Paged and filtered in SQL rather than in the browser, so the results screen
stays instant whether the user has forty jobs or four thousand.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status

from jobsheet.api.serialize import row_json, rows_json
from jobsheet.api.state import CurrentDb, CurrentState
from jobsheet.core.company import normalize_company
from jobsheet.core.models import ApplicationStatus

router = APIRouter(prefix="/api/postings", tags=["postings"])

MAX_PAGE = 500


@router.get("")
def list_postings(
    db: CurrentDb,
    q: Annotated[str, Query(max_length=200)] = "",
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    source: Annotated[str | None, Query(max_length=100)] = None,
    run: Annotated[str | None, Query(max_length=40)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    """One page of jobs, plus how many matched in total."""
    if status_filter is not None and status_filter not in set(ApplicationStatus):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown status")

    rows = db.rows(
        status=status_filter, query=q, source=source, run=run, limit=limit, offset=offset
    )
    return {
        "total": db.count_rows(status=status_filter, query=q, source=source, run=run),
        "limit": limit,
        "offset": offset,
        "rows": rows_json(rows),
    }


@router.get("/one")
def get_posting(dedup_key: Annotated[str, Query(min_length=1)], db: CurrentDb) -> dict[str, Any]:
    """One job by its key.

    A query parameter rather than a path segment because a dedup key is a
    stripped URL, slashes and all, and burying that in a path invites every
    proxy between here and the browser to normalise it into something else.
    """
    row = db.row(dedup_key)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such job")
    return row_json(row)


@router.delete("/one")
def delete_posting(
    dedup_key: Annotated[str, Query(min_length=1)], state: CurrentState
) -> dict[str, Any]:
    """Forget a job, its history included.

    Deliberately explicit: nothing in JobSheet deletes a job on its own, because
    the whole design assumes the record outlives the ad.
    """
    if not state.db.delete_row(dedup_key):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such job")
    return {"deleted": dedup_key}


@router.get("/companies")
def list_companies(
    db: CurrentDb,
    q: Annotated[str, Query(max_length=200)] = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> dict[str, Any]:
    """The employers this account has actually seen, for the wizard to suggest.

    Suggestions come from the user's own rows rather than from a register of
    companies, and that is the whole point: the employer somebody wants to skip
    is one whose ad they are tired of seeing, so the list that matters is the
    list of ads they already have. It also means the wizard needs no credentials
    for anything -- no source in JobSheet does, and the employer field should not
    be the exception.

    Names that differ only in legal form or capitals collapse into one entry, the
    most complete spelling winning, because "Ericsson Nikola Tesla d.d." and
    "ERICSSON NIKOLA TESLA" are one employer to the person reading the list.
    """
    wanted = normalize_company(q) if q.strip() else ""

    best: dict[str, str] = {}
    counts: dict[str, int] = {}
    for row in db.all_rows():
        raw = row.posting.company.strip()
        key = normalize_company(raw)
        if not key or (wanted and wanted not in key):
            continue
        counts[key] = counts.get(key, 0) + 1
        # The longest spelling seen: it is the one that still has "d.o.o." on it,
        # which is what the user will recognise from the ad.
        if len(raw) > len(best.get(key, "")):
            best[key] = raw

    ranked = sorted(counts, key=lambda key: (-counts[key], key))
    return {
        "companies": [
            {"name": best[key], "normalized": key, "count": counts[key]} for key in ranked[:limit]
        ],
        "total": len(ranked),
    }


@router.get("/runs")
def list_runs(
    db: CurrentDb, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[dict[str, Any]]:
    """Past searches as recorded on disk, which outlive the process."""
    return db.runs(limit=limit)
