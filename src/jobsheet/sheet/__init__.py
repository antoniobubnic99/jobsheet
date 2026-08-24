"""The spreadsheet the user designs, and the writer that never loses their work."""

from __future__ import annotations

from jobsheet.sheet.layout import (
    ColumnKind,
    ColumnSpec,
    ConditionalRule,
    SheetLayout,
    classic_checkboxes_layout,
    default_layout,
    minimal_layout,
)
from jobsheet.sheet.row import JobRow, cell_value
from jobsheet.sheet.theme import THEMES, ExcelTheme, resolve_theme
from jobsheet.sheet.writer import (
    SaveReport,
    SheetLockedError,
    VerificationFailedError,
    create_empty,
    export_layout,
    is_locked,
    load,
    read_layout,
    save,
)

__all__ = [
    "THEMES",
    "ColumnKind",
    "ColumnSpec",
    "ConditionalRule",
    "ExcelTheme",
    "JobRow",
    "SaveReport",
    "SheetLayout",
    "SheetLockedError",
    "VerificationFailedError",
    "cell_value",
    "classic_checkboxes_layout",
    "create_empty",
    "default_layout",
    "export_layout",
    "is_locked",
    "load",
    "minimal_layout",
    "read_layout",
    "resolve_theme",
    "save",
]
