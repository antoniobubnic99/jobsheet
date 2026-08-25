"""Where JobSheet keeps things, and how it is reached.

One object answers "where is my spreadsheet", "where is the database" and "what
port is the interface on", so the CLI, the API and the tests never have to agree
by coincidence.

The default home is the platform's own application-data directory rather than
the current working directory, because a desktop app launched from a shortcut
has no meaningful working directory. `JOBSHEET_HOME` overrides it, which is what
the portable Windows ZIP uses to keep everything beside the executable.
"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["HOME_ENV", "Settings", "default_home"]

HOME_ENV = "JOBSHEET_HOME"

# Loopback only, and stated in one place so it cannot drift. The interface is a
# local desktop window that happens to be rendered by a browser; binding it to
# 0.0.0.0 would put a user's job search on their office network.
LOCALHOST = "127.0.0.1"

DEFAULT_PORT = 8765


def default_home() -> Path:
    """The per-user directory JobSheet owns."""
    if override := os.environ.get(HOME_ENV):
        return Path(override).expanduser()
    # Read into a variable rather than testing `sys.platform` directly: mypy
    # narrows the literal to whichever platform it is running on and then calls
    # the other two branches dead code, which they are not.
    system: str = sys.platform
    if system == "win32":
        base = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        return Path(base) / "JobSheet"
    if system == "darwin":
        return Path.home() / "Library" / "Application Support" / "JobSheet"
    base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / "jobsheet"


class Settings(BaseModel):
    """Everything a running JobSheet needs to know about its own surroundings."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    home: Path = Field(default_factory=default_home)

    # Set explicitly to put the workbook somewhere the user actually looks --
    # their Desktop, usually. Left alone, everything sits together under `home`.
    workbook: Path | None = None
    database: Path | None = None
    backup_dir: Path | None = None

    host: str = LOCALHOST
    port: int = DEFAULT_PORT

    # How many backups of the workbook to keep before the oldest are pruned. The
    # predecessor accumulated twenty-four of them in one folder with no ceiling.
    keep_backups: int = 20

    # A secret minted per process. Every `/api` call must present it, which is
    # what stops a web page you happen to have open from driving your local
    # JobSheet: it can send requests to 127.0.0.1, but it cannot read this.
    token: str = Field(default_factory=lambda: secrets.token_urlsafe(32))

    open_browser: bool = True

    @property
    def workbook_path(self) -> Path:
        return self.workbook or self.home / "jobs.xlsx"

    @property
    def database_path(self) -> Path:
        return self.database or self.home / "jobsheet.sqlite3"

    @property
    def backup_path(self) -> Path:
        return self.backup_dir or self.home / "backups"

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def prepare(self) -> Settings:
        """Create the directories. Called once, at start-up."""
        self.home.mkdir(parents=True, exist_ok=True)
        self.workbook_path.parent.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_path.mkdir(parents=True, exist_ok=True)
        return self
