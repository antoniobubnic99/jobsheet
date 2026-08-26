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

## Why there is also a password

The token answers "did this request come from the page JobSheet served?". It
cannot answer "which of the people who use this laptop is at the keyboard?", and
once an install can hold several job searches, that is a different question with
a different answer. So requests carry both: the token, from the page, and a
session cookie, from signing in. Neither substitutes for the other -- the token
without a session is a stranger, and a session without the token is a page we
did not serve.

Everything below the sign-in line therefore depends on `require_user`, which
hands back a `UserSession`: the same database file, the same HTTP client and the
same run manager as everybody else, but narrowed to one account's rows and one
account's workbook. Routers ask for `CurrentState` and get that, so a router
cannot reach the unscoped database by accident -- it would have to go looking.
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING, Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Query, Request, status

from jobsheet.config import Settings
from jobsheet.core.http import HttpClient
from jobsheet.store.db import Database
from jobsheet.store.tracker import Tracker
from jobsheet.store.users import LoginThrottle, User, UserStore

if TYPE_CHECKING:  # pragma: no cover
    from datetime import date

    from jobsheet.api.runs import RunManager, SearchRun
    from jobsheet.core.matching import SearchProfile
    from jobsheet.pipeline import SourceRequest

__all__ = [
    "SESSION_COOKIE",
    "TOKEN_HEADER",
    "AppState",
    "CurrentDb",
    "CurrentState",
    "CurrentTracker",
    "CurrentUser",
    "TokenOnly",
    "UserSession",
    "get_state",
    "require_token",
    "require_user",
]

TOKEN_HEADER = "X-JobSheet-Token"  # noqa: S105 -- a header name, not a secret

# HttpOnly and SameSite=strict, set by the sign-in endpoint. Not `secure`: this
# is plain HTTP on loopback, and marking it secure would simply stop it working.
SESSION_COOKIE = "jobsheet_session"

ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]", "::1"})


class AppState:
    """The database, the settings and the shared HTTP client, opened once."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings.prepare()
        self.db = Database(self.settings.database_path)
        self.tracker = Tracker(self.db)
        self.http = HttpClient()
        self.users = UserStore(self.db)
        # In memory, deliberately: see `LoginThrottle`.
        self.throttle = LoginThrottle()
        self._primary_user_id: int | None = None
        self.users.purge_expired()
        # Imported here rather than at module scope: the run manager imports the
        # pipeline, which imports every source, and the routers do not all need
        # that cost.
        from jobsheet.api.runs import RunManager

        self.runs = RunManager(self)

    @property
    def primary_user_id(self) -> int | None:
        """The first account ever made here, which keeps the original file layout.

        Cached because it answers a question that cannot change while the process
        runs: accounts are only ever added, and the lowest id stays the lowest.
        """
        if self._primary_user_id is None:
            row = self.db._connection.execute("SELECT MIN(id) FROM users").fetchone()
            self._primary_user_id = int(row[0]) if row and row[0] is not None else None
        return self._primary_user_id

    def session_for(self, user: User) -> UserSession:
        return UserSession(self, user)

    async def aclose(self) -> None:
        await self.runs.cancel_all()
        await self.http.aclose()
        self.db.close()


class UserSession:
    """One account's view of the install, built fresh for each request.

    It wears the same attribute names as `AppState` -- `db`, `tracker`,
    `settings`, `runs`, `http` -- so a router reads the same either way. The
    difference is that every one of them is narrowed to this account, and the
    narrowing happens here rather than being remembered at thirty call sites.
    """

    def __init__(self, app: AppState, user: User) -> None:
        self.app = app
        self.user = user
        self.settings = app.settings.for_user(
            user, primary=user.id == app.primary_user_id
        ).prepare()
        self.db = app.db.as_user(user.id)
        self.tracker = Tracker(self.db)
        self.http = app.http
        self.users = app.users
        self.runs = UserRuns(app.runs, self.db, user.id)


class UserRuns:
    """The shared run manager, showing one account only its own searches.

    Runs live in memory for as long as the process does, and the interface polls
    them by id. An id is a random hex string, so guessing one is not a plausible
    attack -- but "not plausible" is a poor foundation, and filtering here costs
    a comparison.
    """

    def __init__(self, manager: RunManager, db: Database, user_id: int) -> None:
        self._manager = manager
        self._db = db
        self._user_id = user_id

    def start(
        self,
        requests: list[SourceRequest],
        profile: SearchProfile | None = None,
        *,
        today: date | None = None,
        max_items: int = 200,
        max_enrich: int = 40,
    ) -> SearchRun:
        return self._manager.start(
            requests,
            profile,
            db=self._db,
            user_id=self._user_id,
            today=today,
            max_items=max_items,
            max_enrich=max_enrich,
        )

    def get(self, run_id: str) -> SearchRun | None:
        run = self._manager.get(run_id)
        return run if run is not None and run.user_id == self._user_id else None

    def recent(self) -> list[SearchRun]:
        return [run for run in self._manager.recent() if run.user_id == self._user_id]

    async def cancel(self, run_id: str) -> bool:
        if self.get(run_id) is None:
            return False
        return await self._manager.cancel(run_id)


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


def require_user(
    state: Annotated[AppState, Depends(require_token)],
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> UserSession:
    """The account behind this request, or a 401 the interface knows to act on.

    The token check runs first, as a dependency, so a request from somewhere we
    did not serve is turned away before it learns anything about who is signed
    in -- including whether anybody is.
    """
    user = state.users.resolve(session or "")
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Sign in to JobSheet to use this.",
            headers={"X-JobSheet-Auth": "required"},
        )
    return state.session_for(user)


def current_user(session: Annotated[UserSession, Depends(require_user)]) -> User:
    return session.user


CurrentState = Annotated[UserSession, Depends(require_user)]
TokenOnly = Annotated[AppState, Depends(require_token)]
CurrentUser = Annotated[User, Depends(current_user)]


def get_db(state: CurrentState) -> Database:
    return state.db


def get_tracker(state: CurrentState) -> Tracker:
    return state.tracker


CurrentDb = Annotated[Database, Depends(get_db)]
CurrentTracker = Annotated[Tracker, Depends(get_tracker)]
