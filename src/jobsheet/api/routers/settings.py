"""Where this JobSheet keeps things, and whether it is healthy.

Paths only, never the token: it is what authorises the call, so echoing it back
in a response would defeat the point of not putting it in the page twice.
"""

from __future__ import annotations

import platform
import sys
from typing import Any

from fastapi import APIRouter

from jobsheet import __version__
from jobsheet.api.state import CurrentState
from jobsheet.sheet import writer
from jobsheet.sources import registry

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def read_settings(state: CurrentState) -> dict[str, Any]:
    settings = state.settings
    workbook = settings.workbook_path
    return {
        "version": __version__,
        "python": sys.version.split()[0],
        "platform": platform.system(),
        "home": str(settings.home),
        "workbook": str(workbook),
        "workbook_exists": workbook.exists(),
        "workbook_locked": writer.is_locked(workbook),
        "database": str(settings.database_path),
        "backups": str(settings.backup_path),
        "keep_backups": settings.keep_backups,
        "sources_installed": len(registry.available()),
    }
