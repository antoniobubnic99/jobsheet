"""How a row is handed to the interface.

`JobRow.dedup_key` is a property, so `model_dump` leaves it out -- and it is the
one field every screen needs, because it is what a status move, a letter draft
and a delete all address the job by. Adding it in one place keeps every endpoint
agreeing on the shape.
"""

from __future__ import annotations

from typing import Any

from jobsheet.sheet.row import JobRow

__all__ = ["row_json", "rows_json"]


def row_json(row: JobRow) -> dict[str, Any]:
    return {"dedup_key": row.dedup_key, **row.model_dump(mode="json")}


def rows_json(rows: list[JobRow]) -> list[dict[str, Any]]:
    return [row_json(row) for row in rows]
