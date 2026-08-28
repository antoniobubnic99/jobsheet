"""Where this JobSheet keeps things, whether it is healthy, and how to move it.

Paths only, never the token: it is what authorises the call, so echoing it back
in a response would defeat the point of not putting it in the page twice.

Two of the routes here write rather than read. `PUT /workbook` exists because a
choice made once, in the wizard, on the first day, is exactly the sort of choice
people revise -- they buy a laptop, they reorganise their Documents folder, they
decide the spreadsheet belongs in Dropbox after all. Before it existed the only
way to change the answer was to make a new account.

`GET /folders` exists so that choice can be made by looking rather than by
typing a path correctly from memory. It lists folder names and nothing else: no
files, no sizes, no contents. That is a smaller window onto the disk than the
file dialog every other program on the machine opens, and this server answers
only the loopback interface, only with the page token, only to a signed-in
account.
"""

from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from jobsheet import __version__
from jobsheet.api.state import CurrentState, UserSession
from jobsheet.api.workbooks import validate_workbook
from jobsheet.config import Settings
from jobsheet.sheet import writer
from jobsheet.sources import registry

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Enough to fill a picker, few enough that a folder full of ten thousand
# subfolders cannot make the interface unusable.
MAX_FOLDERS = 500


def _roots() -> list[dict[str, str]]:
    """The places there is no walking up to: drive letters, or `/`.

    Without these a picker can go down and back up but never sideways, and
    somebody whose spreadsheets live on `D:` is stuck looking at `C:`.
    """
    if platform.system() != "Windows":
        return [{"name": "/", "path": "/"}]
    return [
        {"name": f"{letter}:", "path": f"{letter}:\\"}
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        if Path(f"{letter}:\\").is_dir()
    ]


class WorkbookMove(BaseModel):
    """A new home for the workbook, and whether to take the file along."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=4000)
    # Off by default: moving a file is the surprising half of this operation,
    # so it happens only when it was asked for in as many words.
    move: bool = False


def _workbook_facts(settings: Settings) -> dict[str, Any]:
    workbook = settings.workbook_path
    return {
        "workbook": str(workbook),
        "workbook_exists": workbook.exists(),
        "workbook_locked": writer.is_locked(workbook),
    }


def _settings_after_change(state: UserSession) -> Settings:
    """This account's settings, rebuilt from the row as it now stands.

    `state.settings` was computed when the request arrived and still points at
    the old workbook. Nothing is cached beyond the request, so the next one is
    already right -- but the answer to *this* one has to say where the workbook
    went, not where it was.
    """
    user = state.users.by_id(state.user.id)
    assert user is not None
    return state.app.session_for(user).settings


@router.get("")
def read_settings(state: CurrentState) -> dict[str, Any]:
    settings = state.settings
    return {
        "version": __version__,
        "python": sys.version.split()[0],
        "platform": platform.system(),
        "home": str(settings.home),
        **_workbook_facts(settings),
        "database": str(settings.database_path),
        "backups": str(settings.backup_path),
        "keep_backups": settings.keep_backups,
        "sources_installed": len(registry.available()),
    }


@router.get("/folders")
def read_folders(
    state: CurrentState,
    path: Annotated[str, Query(max_length=4000)] = "",
) -> dict[str, Any]:
    """The folders inside one folder, so a path can be chosen by clicking.

    An unreadable or missing folder is not an error. Somebody browsing a disk
    will walk into a Windows system folder sooner or later, and a red box every
    time they do would make the picker feel broken; it answers with an empty
    list and a sentence instead.
    """
    here = Path(path).expanduser() if path.strip() else state.settings.workbook_path.parent
    if not here.is_dir():
        here = Path.home()

    folders: list[dict[str, str]] = []
    message = ""
    try:
        for child in sorted(here.iterdir(), key=lambda item: item.name.lower()):
            if len(folders) >= MAX_FOLDERS:
                message = f"Showing the first {MAX_FOLDERS} folders."
                break
            # Dotted names are the tool directories of half the software on the
            # machine, and nobody keeps their job search in one.
            if child.name.startswith("."):
                continue
            try:
                if child.is_dir():
                    folders.append({"name": child.name, "path": str(child)})
            except OSError:  # pragma: no cover -- a dead symlink or a locked share
                continue
    except (PermissionError, OSError):
        message = "This folder cannot be opened."

    parent = here.parent
    return {
        "path": str(here),
        # At the root of a drive `parent` is the folder itself; there is no up.
        "parent": None if parent == here else str(parent),
        "home": str(Path.home()),
        "jobsheet_home": str(state.settings.home),
        "roots": _roots(),
        "writable": os.access(here, os.W_OK),
        "folders": folders,
        "message": message,
    }


@router.put("/workbook")
def set_workbook(body: WorkbookMove, state: CurrentState) -> dict[str, Any]:
    """Point this account at a different workbook, optionally taking it along.

    The order matters. The file is moved first and the row is written second,
    so a move that fails leaves the account pointing at the workbook that is
    still there. The other way round would record a path with nothing at it and
    lose sight of the file in the same breath.
    """
    wanted = validate_workbook(body.path)
    if wanted is None:  # pragma: no cover -- `min_length=1` catches the empty string
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"code": "workbook_required", "message": "Say where the workbook should be."},
        )

    target = Path(wanted)
    current = state.settings.workbook_path
    moved = False

    if target != current and body.move and current.exists():
        if writer.is_locked(current):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {
                    "code": "workbook_locked",
                    "message": f"{current.name} is open in Excel. Close it and try again.",
                },
            )
        if target.exists():
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {
                    "code": "workbook_in_the_way",
                    "message": f"There is already a workbook at {target}.",
                },
            )
        try:
            shutil.move(str(current), str(target))
        except OSError as error:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {"code": "workbook_move_failed", "message": str(error)},
            ) from error
        moved = True

    state.users.set_workbook(state.user.id, wanted)
    return _workbook_facts(_settings_after_change(state)) | {"moved": moved}
