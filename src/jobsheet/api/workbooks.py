"""Whether a path is somewhere this account may keep its jobs.

The same three questions are asked in two places -- once by the wizard, when it
offers to put the workbook where the user already looks for spreadsheets, and
once by the settings screen, when they change their mind a month later. Asking
them in one place is what keeps the two answers the same: a path the wizard
would have refused must not become acceptable simply because it arrived through
a different door.

The refusals carry a `code` as well as a sentence, for the same reason the
sign-in ones do -- the interface has these translated, and somebody choosing a
folder is reading in a hurry.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, status

__all__ = ["WORKBOOK_SUFFIX", "validate_workbook"]

WORKBOOK_SUFFIX = ".xlsx"


def _refuse(code: str, message: str) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_ENTITY, {"code": code, "message": message}
    )


def validate_workbook(wanted: str) -> str | None:
    """The workbook path to store, or `None` for "wherever the default is".

    An empty string is not an error: it is how the wizard says the user did not
    choose, and the account then follows the layout in `Settings.for_user`.

    The folder must already exist. Creating it here would be the friendlier
    thing to do right up until somebody mistypes a drive letter and JobSheet
    silently invents a folder tree nobody will ever look in.
    """
    if not wanted.strip():
        return None

    path = Path(wanted).expanduser()
    if path.suffix.lower() != WORKBOOK_SUFFIX:
        raise _refuse("workbook_not_xlsx", f"A workbook has to end in {WORKBOOK_SUFFIX}.")
    if path.is_dir():
        raise _refuse("workbook_is_a_folder", f"{path} is a folder.")
    if not path.parent.exists():
        raise _refuse("workbook_folder_missing", f"There is no folder at {path.parent}.")
    return str(path)
