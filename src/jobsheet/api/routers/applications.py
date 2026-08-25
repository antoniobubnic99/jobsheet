"""The tracker board: where each application stands, and how it got there.

Status moves are the one thing in JobSheet the user owns outright, so every one
of them is recorded with a timestamp. "When did I apply?" is answerable here and
nowhere else -- a spreadsheet column only ever holds the latest answer.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from jobsheet.api.serialize import rows_json
from jobsheet.api.state import CurrentState
from jobsheet.core.models import ApplicationStatus
from jobsheet.store.tracker import BOARD_ORDER

router = APIRouter(prefix="/api/applications", tags=["applications"])


class StatusMove(BaseModel):
    """One card dragged from one column to another."""

    model_config = ConfigDict(extra="forbid")

    dedup_key: str = Field(min_length=1)
    status: ApplicationStatus
    note: str = Field(default="", max_length=2000)


class UserValues(BaseModel):
    """Whatever the user typed into their own columns for one job."""

    model_config = ConfigDict(extra="forbid")

    dedup_key: str = Field(min_length=1)
    values: dict[str, Any] = Field(default_factory=dict)


@router.get("/board")
def board(state: CurrentState) -> dict[str, Any]:
    """Every tracked job, grouped into the board's columns, in board order."""
    columns = state.tracker.board()
    return {
        "order": [str(status) for status in BOARD_ORDER],
        "counts": {name: len(rows) for name, rows in columns.items()},
        "columns": {
            name: rows_json(rows) for name, rows in columns.items()
        },
    }


@router.get("/counts")
def counts(state: CurrentState) -> dict[str, int]:
    return state.tracker.counts()


@router.post("/status")
def move(body: StatusMove, state: CurrentState) -> dict[str, Any]:
    """Move one application. A move to where it already is changes nothing."""
    if not state.tracker.knows(body.dedup_key):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such job")

    change = state.tracker.set_status(body.dedup_key, body.status, note=body.note)
    return {
        "dedup_key": body.dedup_key,
        "status": str(body.status),
        "changed": change is not None,
        "from_status": str(change.from_status) if change else None,
        "at": change.at.isoformat(timespec="seconds") if change else None,
    }


@router.post("/values")
def set_values(body: UserValues, state: CurrentState) -> dict[str, Any]:
    """Replace the user's own column values for one job."""
    if not state.tracker.knows(body.dedup_key):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such job")
    state.tracker.set_user_values(body.dedup_key, body.values)
    return {"dedup_key": body.dedup_key, "values": body.values}


@router.get("/history")
def history(
    dedup_key: Annotated[str, Query(min_length=1)], state: CurrentState
) -> list[dict[str, Any]]:
    """Every move this application has made, oldest first."""
    return [
        {
            "at": change.at.isoformat(timespec="seconds"),
            "from_status": str(change.from_status),
            "to_status": str(change.to_status),
            "note": change.note,
        }
        for change in state.tracker.history(dedup_key)
    ]
