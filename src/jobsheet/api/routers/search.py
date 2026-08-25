"""Starting a search, and watching it happen.

`POST /api/search` returns as soon as the run has an id. Progress arrives on
`GET /api/search/{id}/stream` as server-sent events, which is what lets the
interface print "fetching HZZ… 218 ads…" while the run is still going.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from jobsheet.api.serialize import rows_json
from jobsheet.api.state import CurrentState
from jobsheet.core.matching import SearchProfile
from jobsheet.pipeline import SourceRequest
from jobsheet.sources import registry

router = APIRouter(prefix="/api/search", tags=["search"])


class SourceChoice(BaseModel):
    """One source the user picked, with the answers to its own form."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    params: dict[str, Any] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[SourceChoice] = Field(min_length=1)
    profile: SearchProfile = Field(default_factory=SearchProfile)
    today: date | None = None

    # Ceilings the user can lower but not raise past what the pipeline allows;
    # they exist to protect other people's servers as much as our own patience.
    max_items: int = Field(default=200, ge=1, le=1000)
    max_enrich: int = Field(default=40, ge=0, le=200)


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def start_search(body: SearchRequest, state: CurrentState) -> dict[str, Any]:
    """Begin a search. Returns immediately; watch `/stream` for what happens."""
    installed = set(registry.available())
    if unknown := [c.source_id for c in body.sources if c.source_id not in installed]:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"not installed: {', '.join(sorted(unknown))}",
        )

    run = state.runs.start(
        [SourceRequest(source_id=c.source_id, params=c.params) for c in body.sources],
        body.profile,
        today=body.today,
        max_items=body.max_items,
        max_enrich=body.max_enrich,
    )
    return run.summary()


@router.get("")
async def list_runs(state: CurrentState) -> list[dict[str, Any]]:
    """Searches this session has started, newest first."""
    return [run.summary() for run in state.runs.recent()]


@router.get("/{run_id}")
async def get_run(run_id: str, state: CurrentState) -> dict[str, Any]:
    run = state.runs.get(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such search")
    return run.summary()


@router.get("/{run_id}/results")
async def get_results(run_id: str, state: CurrentState) -> dict[str, Any]:
    """What a finished run found, including what it turned away and why.

    Rejections are returned rather than dropped: a user who expected an ad to
    appear deserves to be told which rule removed it.
    """
    run = state.runs.get(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such search")
    report = run.report
    if report is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "that search has not finished")

    return {
        "id": run.id,
        "rows": rows_json(report.rows),
        "rejected": [
            {
                "title": posting.title,
                "company": posting.company,
                "url": posting.url,
                "source": posting.source_id,
                "code": rejection.code,
                "detail": rejection.detail,
            }
            for posting, rejection in report.rejected
        ],
    }


def _sse(event: str, data: str) -> str:
    """One server-sent event. Every line of a multi-line payload needs its own prefix."""
    body = "".join(f"data: {line}\n" for line in data.splitlines() or [""])
    return f"event: {event}\n{body}\n"


@router.get("/{run_id}/stream")
async def stream_run(run_id: str, state: CurrentState) -> StreamingResponse:
    """Live commentary as server-sent events, then one closing `end` event."""
    run = state.runs.get(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such search")

    async def events() -> AsyncIterator[str]:
        async for line in run.listen():
            yield _sse("progress", line)
        yield _sse("end", str(run.phase))

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Without this a reverse proxy will buffer the whole stream and the
            # commentary arrives all at once, at the end, which defeats it.
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str, state: CurrentState) -> dict[str, Any]:
    if state.runs.get(run_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such search")
    stopped = await state.runs.cancel(run_id)
    return {"stopped": stopped, "run": state.runs.get(run_id).summary()}  # type: ignore[union-attr]
