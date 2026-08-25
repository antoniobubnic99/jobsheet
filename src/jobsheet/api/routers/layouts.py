"""The sheet design: which columns, named what, coloured how.

This is the endpoint behind the designer screen, and the reason the whole
project exists. A layout is just data, so it can be previewed without touching a
file, saved under a name, and handed to someone else as JSON.

`/current` reads the layout back out of the workbook itself. That is how a user
who rearranged their columns in Excel finds the designer already agreeing with
them rather than offering to undo their work.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import ValidationError

from jobsheet.api.state import CurrentState
from jobsheet.sheet import writer
from jobsheet.sheet.layout import (
    SOURCE_KEYS,
    ColumnKind,
    SheetLayout,
    classic_checkboxes_layout,
    default_layout,
    minimal_layout,
)
from jobsheet.sheet.theme import DEFAULT_THEME, THEMES

router = APIRouter(prefix="/api/layouts", tags=["layouts"])

PRESETS = {
    "default": default_layout,
    "classic-checkboxes": classic_checkboxes_layout,
    "minimal": minimal_layout,
}

PRESET_NOTES = {
    "default": "Everything most people want, in the order most people want it.",
    "classic-checkboxes": (
        "Three tick boxes and a colour rule -- the shape the predecessor used "
        "for a year of real job hunting."
    ),
    "minimal": "Four columns. For people who want the list and nothing else.",
}


@router.get("/vocabulary")
def vocabulary(state: CurrentState) -> dict[str, Any]:
    """Everything the designer needs to offer, without hard-coding it in the UI."""
    return {
        "kinds": [
            {"value": str(kind), "label": kind.name.replace("_", " ").title()}
            for kind in ColumnKind
        ],
        # Keys the app can fill in by itself. Anything else the user types is
        # their own column: created, never written to, never cleared.
        "source_keys": sorted(SOURCE_KEYS),
        "themes": [
            {"value": name, "default": name == DEFAULT_THEME, **theme.model_dump(mode="json")}
            for name, theme in THEMES.items()
        ],
    }


@router.get("/presets")
def presets(state: CurrentState) -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "description": PRESET_NOTES[name],
            "layout": build().model_dump(mode="json"),
        }
        for name, build in PRESETS.items()
    ]


@router.get("/presets/{name}")
def preset(name: str, state: CurrentState) -> dict[str, Any]:
    build = PRESETS.get(name)
    if build is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such preset")
    return build().model_dump(mode="json")


@router.get("/current")
def current(state: CurrentState) -> dict[str, Any]:
    """The layout the workbook on disk is actually using.

    Missing file, or a workbook written before layouts were embedded, both mean
    "no opinion" rather than an error -- the designer opens on the default.
    """
    path = state.settings.workbook_path
    embedded = writer.read_layout(path) if path.exists() else None
    return {
        "workbook": str(path),
        "exists": path.exists(),
        "from_workbook": embedded is not None,
        "layout": (embedded or default_layout()).model_dump(mode="json"),
    }


@router.post("/validate")
def validate(layout: dict[str, Any], state: CurrentState) -> dict[str, Any]:
    """Check a design before it is used, and say plainly what is wrong with it.

    The designer calls this on every edit, so the user learns about a duplicate
    key or an empty label while they are still looking at the field -- not when
    an export fails half an hour later.
    """
    try:
        parsed = SheetLayout.model_validate(layout)
    except ValidationError as error:
        return {
            "valid": False,
            "problems": [
                {
                    "where": ".".join(str(part) for part in problem["loc"]),
                    "message": problem["msg"],
                }
                for problem in error.errors()
            ],
        }

    return {
        "valid": True,
        "problems": [],
        "layout": parsed.model_dump(mode="json"),
        "user_owned": list(parsed.user_owned_keys),
        "checkboxes": list(parsed.checkbox_keys),
    }
