"""What one running JobSheet holds open, and who is allowed to ask for it.

Everything the routers need hangs off a single object stored on the app, so a
test can build one over a temporary directory and get an entirely independent
JobSheet without patching anything global.

## Why there is a token at all

The server listens on `127.0.0.1`, and it is tempting to conclude that this is
already private. It is not. Any web page in any tab can send a request to
`http://127.0.0.1:8765`, and the browser will happily deliver it. Without a
check, a page you visited while job hunting could read your applications or
overwrite your workbook.

Two things stop that, and both are needed:

* **A per-process token.** It is minted at start-up and handed to the interface
  by embedding it in the page JobSheet itself serves. A cross-origin page cannot
  read that page -- no CORS headers are sent, deliberately -- so it cannot learn
  the token.
* **A host check.** A hostile domain can point its own DNS at `127.0.0.1`, which
  makes the browser treat our server as same-origin for that domain. Rejecting
  any request whose `Host` is not loopback closes that door.

The token is also accepted as a query parameter, because `EventSource` -- the
browser API behind the live progress stream -- cannot send custom headers. On a
loopback-only server with no third-party requests that is an acceptable trade,
and it is confined to this one mechanism.
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, Request, status

from jobsheet.config import Settings
from jobsheet.core.http import HttpClient
from jobsheet.store.db import Database
from jobsheet.store.tracker import Tracker

__all__ = [
    "TOKEN_HEADER",
    "AppState",
    "CurrentDb",
    "CurrentState",
    "CurrentTracker",
    "get_state",
    "require_token",
]

TOKEN_HEADER = "X-JobSheet-Token"  # noqa: S105 -- a header name, not a secret

ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]", "::1"})


class AppState:
    """The database, the settings and the shared HTTP client, opened once."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings.prepare()
        self.db = Database(self.settings.database_path)
        self.tracker = Tracker(self.db)
        self.http = HttpClient()
        # Imported here rather than at module scope: the run manager imports the
        # pipeline, which imports every source, and the routers do not all need
        # that cost.
        from jobsheet.api.runs import RunManager

        self.runs = RunManager(self)

    async def aclose(self) -> None:
        await self.runs.cancel_all()
        await self.http.aclose()
        self.db.close()


def get_state(request: Request) -> AppState:
    state: AppState | None = getattr(request.app.state, "jobsheet", None)
    if state is None:  # pragma: no cover -- only reachable if the app is misbuilt
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "JobSheet is not ready")
    return state


def _host_is_loopback(request: Request) -> bool:
    host = request.headers.get("host", "")
    # Strip the port, taking care not to split an IPv6 literal at its colons.
    name = host.rsplit(":", 1)[0] if not host.startswith("[") else host.split("]")[0] + "]"
    return name.lower() in ALLOWED_HOSTS


def require_token(
    request: Request,
    state: Annotated[AppState, Depends(get_state)],
    header_token: Annotated[str | None, Header(alias=TOKEN_HEADER)] = None,
    query_token: Annotated[str | None, Query(alias="token")] = None,
) -> AppState:
    """Reject anything that did not come from the interface JobSheet served."""
    if not _host_is_loopback(request):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "JobSheet only answers requests addressed to localhost.",
        )

    supplied = header_token or query_token or ""
    if not secrets.compare_digest(supplied, state.settings.token):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Missing or wrong session token. Open JobSheet from its own window.",
        )
    return state


CurrentState = Annotated[AppState, Depends(require_token)]


def get_db(state: CurrentState) -> Database:
    return state.db


def get_tracker(state: CurrentState) -> Tracker:
    return state.tracker


CurrentDb = Annotated[Database, Depends(get_db)]
CurrentTracker = Annotated[Tracker, Depends(get_tracker)]
