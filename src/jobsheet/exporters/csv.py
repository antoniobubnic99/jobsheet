"""The same table as the workbook, in the format everything else can read.

The layout decides the columns, so a CSV export and an Excel export of the same
search have identical headers in identical order. That is the point: a user who
spent time arranging their sheet should not have to re-derive it for the
importer at the other end.

Dates go out as `YYYY-MM-DD`, not as whatever the local Excel decides today, and
the file carries a UTF-8 BOM so that double-clicking it on Windows does not turn
every accented character into mojibake.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from typing import Any

from jobsheet.sheet.layout import ColumnKind, SheetLayout, default_layout
from jobsheet.sheet.row import JobRow, cell_value

__all__ = ["BOM", "to_csv"]

# Excel on Windows reads a BOM-less UTF-8 CSV as the local code page. Every
# Croatian, Polish or Turkish name in the file is mangled by that, so the BOM is
# not optional decoration.
BOM = "﻿"


def _text(value: Any, kind: ColumnKind) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        # Not `str(value)`: "TRUE"/"" is what spreadsheets expect back.
        return "TRUE" if value else ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if kind is ColumnKind.TAGS and isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value)
    return str(value)


def to_csv(
    rows: list[JobRow],
    layout: SheetLayout | None = None,
    *,
    delimiter: str = ",",
    bom: bool = True,
) -> str:
    """Render rows as CSV text, one line per job, header first."""
    layout = layout or default_layout()
    buffer = io.StringIO()
    # `lineterminator` is set explicitly because csv defaults to \r\n while
    # StringIO does not translate, which otherwise varies by platform.
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\n")

    writer.writerow([column.label for column in layout.columns])
    for row in rows:
        writer.writerow(
            [_text(cell_value(row, column.key), column.kind) for column in layout.columns]
        )

    return (BOM if bom else "") + buffer.getvalue()
