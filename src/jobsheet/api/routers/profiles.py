"""Saved searches and saved sheet designs.

Both are named JSON, so they share one endpoint rather than two nearly identical
ones. `kind` is `search` or `layout`; anything else is refused, because a typo
that silently created a third namespace would be invisible until a profile went
missing.

Saving is validated against the real model. A profile that cannot be loaded back
is not worth storing, and finding that out at save time is far kinder than
finding out when the user reaches for it three weeks later.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from jobsheet.api.state import CurrentState
from jobsheet.core.matching import SearchProfile
from jobsheet.sheet.layout import SheetLayout

router = APIRouter(prefix="/api/profiles", tags=["profiles"])

KINDS: dict[str, type[BaseModel]] = {"search": SearchProfile, "layout": SheetLayout}

MAX_NAME = 80


class ProfileBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload: dict[str, Any] = Field(default_factory=dict)


def _model_for(kind: str) -> type[BaseModel]:
    model = KINDS.get(kind)
    if model is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"kind must be one of: {', '.join(sorted(KINDS))}"
        )
    return model


def _clean_name(name: str) -> str:
    name = name.strip()
    if not name or len(name) > MAX_NAME:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"a profile name must be 1-{MAX_NAME} characters",
        )
    return name


@router.get("/{kind}")
def list_profiles(kind: str, state: CurrentState) -> list[str]:
    _model_for(kind)
    return state.db.list_profiles(kind)


@router.get("/{kind}/{name}")
def load_profile(kind: str, name: str, state: CurrentState) -> dict[str, Any]:
    _model_for(kind)
    payload = state.db.load_profile(_clean_name(name), kind)
    if payload is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such profile")
    return {"name": name, "kind": kind, "payload": payload}


@router.put("/{kind}/{name}")
def save_profile(kind: str, name: str, body: ProfileBody, state: CurrentState) -> dict[str, Any]:
    model = _model_for(kind)
    name = _clean_name(name)
    try:
        validated = model.model_validate(body.payload)
    except ValidationError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            [
                {
                    "where": ".".join(str(part) for part in problem["loc"]),
                    "message": problem["msg"],
                }
                for problem in error.errors()
            ],
        ) from error

    payload = validated.model_dump(mode="json")
    state.db.save_profile(name, kind, payload)
    return {"name": name, "kind": kind, "payload": payload}


@router.delete("/{kind}/{name}")
def delete_profile(kind: str, name: str, state: CurrentState) -> dict[str, Any]:
    _model_for(kind)
    if not state.db.delete_profile(_clean_name(name), kind):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such profile")
    return {"deleted": name, "kind": kind}
