"""The collected jobs, as the results table reads them.

Paged and filtered in SQL rather than in the browser, so the results screen
stays instant whether the user has forty jobs or four thousand.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status

from jobsheet.api.serialize import row_json, rows_json
from jobsheet.api.state import CurrentDb, CurrentState
from jobsheet.core.models import ApplicationStatus

router = APIRouter(prefix="/api/postings", tags=["postings"])

MAX_PAGE = 500


@router.get("")
def list_postings(
    db: CurrentDb,
    q: Annotated[str, Query(max_length=200)] = "",
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    source: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    """One page of jobs, plus how many matched in total."""
    if status_filter is not None and status_filter not in set(ApplicationStatus):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown status")

    rows = db.rows(status=status_filter, query=q, source=source, limit=limit, offset=offset)
    return {
        "total": db.count_rows(status=status_filter, query=q, source=source),
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


@router.get("/runs")
def list_runs(
    db: CurrentDb, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[dict[str, Any]]:
    """Past searches as recorded on disk, which outlive the process."""
    return db.runs(limit=limit)
