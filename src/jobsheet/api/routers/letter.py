"""A covering-letter draft, filled in from one ad.

Template rendering, not writing. See `jobsheet.exporters.letter` for why that
line is drawn where it is.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from jobsheet.api.state import CurrentState
from jobsheet.exporters.letter import (
    DEFAULT_TEMPLATE,
    TEMPLATE_FILENAME,
    Applicant,
    LetterError,
    load_template,
    render_letter,
)

router = APIRouter(prefix="/api/letter", tags=["letter"])


class ApplicantBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="Your Name", max_length=200)
    email: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=60)
    pitch: str = Field(default="", max_length=5000)
    extra: dict[str, Any] = Field(default_factory=dict)


class LetterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dedup_key: str = Field(min_length=1)
    applicant: ApplicantBody = Field(default_factory=ApplicantBody)

    # A draft being edited in the browser, rendered without saving it anywhere.
    template: str | None = Field(default=None, max_length=20000)


@router.get("/template")
def get_template(state: CurrentState) -> dict[str, Any]:
    """The template in use, and where a user would put their own."""
    home = state.settings.home
    return {
        "path": str(home / TEMPLATE_FILENAME),
        "custom": (home / TEMPLATE_FILENAME).is_file(),
        "template": load_template(home),
        "builtin": DEFAULT_TEMPLATE,
    }


@router.post("")
def draft(body: LetterRequest, state: CurrentState) -> dict[str, Any]:
    """Render the letter for one job."""
    row = state.db.row(body.dedup_key)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such job")

    applicant = Applicant(
        name=body.applicant.name,
        email=body.applicant.email,
        phone=body.applicant.phone,
        **({"pitch": body.applicant.pitch} if body.applicant.pitch else {}),
        extra=body.applicant.extra,
    )
    try:
        text = render_letter(
            row,
            applicant,
            template=body.template,
            template_dir=state.settings.home,
        )
    except LetterError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error

    return {"dedup_key": row.dedup_key, "title": row.posting.title, "text": text}


@router.get("/preview")
def preview(
    dedup_key: Annotated[str, Query(min_length=1)], state: CurrentState
) -> dict[str, Any]:
    """The letter with placeholder details, for the "what would this look like" button."""
    return draft(LetterRequest(dedup_key=dedup_key), state)
