"""Signing in, and the one-time setup that follows.

Three things happen on this router and nowhere else: an account is made, a
session is opened, and a first search is described. They sit together because
they are one path in the interface -- the door, the hallway, the room -- and
splitting them across three files would hide that.

Failures here answer in two registers at once. `message` is an English sentence
written for a person, which the interface will show if it has nothing better.
`code` is a short constant the interface translates, because "wrong password" is
the one error in this application that a user reads in a hurry, in their own
language, while wondering whether they have been locked out.

What the endpoints deliberately do *not* say:

* Whether a username exists. `login` answers the same way, in the same time, for
  a name that is not here and a password that is wrong.
* Anything at all, to a request without the page token. `require_token` runs
  first, so a page in another tab cannot even ask who lives here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Cookie, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field

from jobsheet.api.state import (
    SESSION_COOKIE,
    CurrentState,
    TokenOnly,
    UserSession,
)
from jobsheet.core.matching import fold
from jobsheet.core.setup import DEFAULT_SETUP, SearchSetup
from jobsheet.sources import registry
from jobsheet.store.users import SESSION_DAYS, User, UserError

router = APIRouter(prefix="/api/auth", tags=["auth"])

WORKBOOK_SUFFIX = ".xlsx"


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=500)


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current: str = Field(min_length=1, max_length=500)
    new: str = Field(min_length=1, max_length=500)


class Onboarding(BaseModel):
    """Everything the wizard collected, in one submission."""

    model_config = ConfigDict(extra="forbid")

    setup: SearchSetup = Field(default_factory=SearchSetup)

    # Where the spreadsheet should live. Empty means "wherever JobSheet keeps
    # yours", which is the honest default for somebody who has no opinion yet.
    workbook: str = ""


def _fail(error: UserError, code: int = status.HTTP_422_UNPROCESSABLE_ENTITY) -> HTTPException:
    return HTTPException(code, {"code": error.code, "message": error.message})


def _user_json(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "onboarded": user.is_onboarded,
        "has_password": user.has_password,
        "workbook": user.workbook,
        "created_at": user.created_at.isoformat(timespec="seconds"),
    }


def _sign_in(state: TokenOnly, response: Response, user: User) -> dict[str, Any]:
    """Open a session and put it in a cookie the interface cannot read.

    HttpOnly so that a script on the page -- ours or anybody's -- cannot copy the
    token out. SameSite=strict so that a request another site provokes arrives
    without it. Not `secure`, because this is http on loopback and a secure
    cookie would simply never be sent.
    """
    token = state.users.open_session(user.id)
    state.users.touch(user.id)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        samesite="strict",
        path="/",
    )
    fresh = state.users.by_id(user.id)
    return _user_json(fresh or user)


# ------------------------------------------------------------------ the door


@router.get("/status")
def read_status(state: TokenOnly) -> dict[str, Any]:
    """What the front page and the sign-in form need before anybody has typed.

    Whether to offer registration or a sign-in form, whether this install is
    holding data from before accounts that is waiting to be claimed, and what
    JobSheet can actually search -- the front page promises that out loud, and
    `/api/sources` cannot answer it, because that route is scoped to an account
    and tells a visitor 401.

    Names only. The full manifest is a form definition, and the door has no
    form to draw; a name is what a person outside recognises.
    """
    claimable = state.users.claimable()
    manifests = registry.manifests()
    return {
        "accounts": state.users.count(),
        "claimable": _user_json(claimable) if claimable else None,
        "sources": {"count": len(manifests), "names": [one.name for one in manifests]},
    }


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: Credentials, response: Response, state: TokenOnly) -> dict[str, Any]:
    """Make a new account and sign into it."""
    try:
        user = state.users.create(body.username, body.password)
    except UserError as error:
        code = (
            status.HTTP_409_CONFLICT
            if error.code == "username_taken"
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise _fail(error, code) from error
    return _sign_in(state, response, user)


@router.post("/claim")
def claim(body: Credentials, response: Response, state: TokenOnly) -> dict[str, Any]:
    """Take ownership of the data an install had before accounts existed.

    The claimed account is always the first one, so it keeps the original file
    layout and the workbook stays exactly where its owner left it. That is not a
    coincidence to rely on quietly -- it is why `Settings.for_user` treats the
    first account specially.
    """
    waiting = state.users.claimable()
    if waiting is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"code": "nothing_to_claim", "message": "There is no unclaimed data here."},
        )
    try:
        user = state.users.claim(waiting.id, body.username, body.password)
    except UserError as error:
        raise _fail(error) from error
    return _sign_in(state, response, user)


@router.post("/login")
def login(body: Credentials, response: Response, state: TokenOnly) -> dict[str, Any]:
    """Sign in. Says nothing about which half of a wrong answer was wrong."""
    folded = fold(body.username)
    if seconds := state.throttle.locked_for(folded):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            {
                "code": "too_many_attempts",
                "message": f"Too many attempts. Try again in {seconds} second(s).",
                "retry_after": seconds,
            },
            headers={"Retry-After": str(seconds)},
        )

    user = state.users.authenticate(body.username, body.password)
    if user is None:
        state.throttle.failed(folded)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            {"code": "bad_credentials", "message": "That username and password do not match."},
        )
    state.throttle.succeeded(folded)
    return _sign_in(state, response, user)


@router.post("/logout")
def logout(
    response: Response,
    state: TokenOnly,
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> dict[str, Any]:
    """Close this session. Safe to call when there is not one."""
    if session:
        state.users.close_session(session)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"signed_out": True}


# --------------------------------------------------------------- the hallway


@router.get("/me")
def me(state: CurrentState) -> dict[str, Any]:
    """Who is signed in, and whether they have been through the wizard yet."""
    return _user_json(state.user) | {
        "workbook_path": str(state.settings.workbook_path),
        "home": str(state.settings.home),
        "primary": state.user.id == state.app.primary_user_id,
    }


@router.post("/password")
def change_password(body: PasswordChange, state: CurrentState) -> dict[str, Any]:
    """Change a password, and sign every other session out while doing it.

    Other sessions go because the usual reason to change a password is the fear
    that somebody else has it. Leaving their session open would make the change
    a gesture.
    """
    if state.users.authenticate(state.user.username, body.current) is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            {"code": "bad_credentials", "message": "That is not the current password."},
        )
    try:
        state.users.set_password(state.user.id, body.new)
    except UserError as error:
        raise _fail(error) from error
    state.users.close_all(state.user.id)
    return {"changed": True, "signed_out_everywhere": True}


# ------------------------------------------------------------------ the room


def _workbook_for(session: UserSession, wanted: str) -> str | None:
    """Validate a workbook path the wizard offered, or fall back to the default."""
    if not wanted.strip():
        return None

    path = Path(wanted).expanduser()
    if path.suffix.lower() != WORKBOOK_SUFFIX:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {
                "code": "workbook_not_xlsx",
                "message": f"A workbook has to end in {WORKBOOK_SUFFIX}.",
            },
        )
    if path.is_dir():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"code": "workbook_is_a_folder", "message": f"{path} is a folder."},
        )
    if not path.parent.exists():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {
                "code": "workbook_folder_missing",
                "message": f"There is no folder at {path.parent}.",
            },
        )
    return str(path)


@router.post("/onboarding")
def finish_onboarding(body: Onboarding, state: CurrentState) -> dict[str, Any]:
    """Store what the wizard collected and let the account into the app.

    The setup is written before the account is marked as onboarded. Doing it the
    other way round would, if the write failed, leave somebody looking at an
    empty search screen with no wizard left to run.
    """
    workbook = _workbook_for(state, body.workbook)
    state.db.save_profile(DEFAULT_SETUP, "setup", body.setup.model_dump(mode="json"))
    state.users.set_workbook(state.user.id, workbook)
    state.users.mark_onboarded(state.user.id)

    user = state.users.by_id(state.user.id)
    assert user is not None
    refreshed = state.app.session_for(user)
    return _user_json(user) | {"workbook_path": str(refreshed.settings.workbook_path)}
