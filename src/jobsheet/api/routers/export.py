"""Getting the data out: the workbook, or a plain file.

Writing the workbook is the one operation in JobSheet that can destroy something
the user cannot get back, so it is also the one with a fixed order of steps:

1. **Read what is there first.** Whatever the user typed into Excel since the
   last run -- a status, a tick, a note in their own column -- is pulled back
   into the database before anything is written.
2. **Then write, from the database.** So the file is rebuilt from a record that
   already contains those edits, instead of from a snapshot that predates them.
3. **Then verify, and roll back if it does not match.** That lives in
   `sheet.writer.save`; this endpoint's job is to report the outcome honestly.

Skipping step 1 is exactly how the predecessor erased 88 hand-placed ticks.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from jobsheet.api.state import AppState, CurrentState
from jobsheet.exporters.csv import to_csv
from jobsheet.exporters.jsonl import to_json, to_jsonl
from jobsheet.sheet import writer
from jobsheet.sheet.layout import SheetLayout
from jobsheet.sheet.row import JobRow
from jobsheet.store.tracker import merge_from_sheet

router = APIRouter(prefix="/api/export", tags=["export"])


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Omitted means "keep using whatever the workbook already has", which is the
    # answer that respects a user who rearranged their columns by hand.
    layout: SheetLayout | None = None

    # Only the jobs the user is still interested in, if they say so.
    statuses: list[str] = Field(default_factory=list)


def _filename(stem: str, suffix: str) -> str:
    return f"{stem}-{date.today().isoformat()}.{suffix}"


def _rows(state: AppState, statuses: list[str]) -> list[JobRow]:
    rows = state.db.all_rows()
    if statuses:
        wanted = set(statuses)
        rows = [row for row in rows if str(row.status) in wanted]
    return rows


@router.post("/xlsx")
def export_xlsx(body: ExportRequest, state: CurrentState) -> dict[str, Any]:
    """Rewrite the workbook, having first taken back whatever was edited in it."""
    path = state.settings.workbook_path
    adopted: list[str] = []

    if path.exists():
        try:
            existing, _ = writer.load(path)
        except Exception as error:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"could not read {path.name}: {type(error).__name__}: {error}",
            ) from error
        adopted = [
            change.dedup_key for change in merge_from_sheet(state.tracker, existing)
        ]

    layout = body.layout or (writer.read_layout(path) if path.exists() else None)
    rows = _rows(state, body.statuses)

    try:
        report = writer.save(
            path,
            rows,
            layout,
            backup_dir=state.settings.backup_path,
            keep_backups=state.settings.keep_backups,
        )
    except writer.SheetLockedError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except writer.VerificationFailedError as error:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"the written file did not match what went in ({error}); "
            "your previous workbook has been restored and is untouched.",
        ) from error

    return {
        "path": str(path),
        "rows": report.rows,
        "user_values": report.user_values,
        "backup": str(report.backup) if report.backup else None,
        # Edits found in the workbook and taken back into the database. Shown to
        # the user because "I changed 3 statuses in Excel" and "JobSheet noticed
        # 3 changes" agreeing is the whole reassurance.
        "adopted_from_workbook": adopted,
    }


@router.post("/csv")
def export_csv(body: ExportRequest, state: CurrentState) -> Response:
    layout = body.layout or (
        writer.read_layout(state.settings.workbook_path)
        if state.settings.workbook_path.exists()
        else None
    )
    text = to_csv(_rows(state, body.statuses), layout)
    return Response(
        content=text.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{_filename("jobs", "csv")}"'},
    )


@router.post("/json")
def export_json(body: ExportRequest, state: CurrentState) -> Response:
    text = to_json(_rows(state, body.statuses))
    return Response(
        content=text.encode("utf-8"),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{_filename("jobs", "json")}"'},
    )


@router.post("/jsonl")
def export_jsonl(body: ExportRequest, state: CurrentState) -> Response:
    text = to_jsonl(_rows(state, body.statuses))
    return Response(
        content=text.encode("utf-8"),
        media_type="application/x-ndjson; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{_filename("jobs", "jsonl")}"'},
    )


@router.get("/workbook")
def workbook_state(state: CurrentState) -> dict[str, Any]:
    """Whether writing would work right now, asked before the user commits to it."""
    path = state.settings.workbook_path
    locked = writer.is_locked(path)
    return {
        "path": str(path),
        "exists": path.exists(),
        "locked": locked,
        "message": (
            f"{path.name} is open in Excel. Close it before exporting."
            if locked
            else "Ready."
        ),
        "backups": str(state.settings.backup_path),
    }
