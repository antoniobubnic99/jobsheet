"""Everything the app knows, in a shape another program can consume.

Where the CSV export follows the user's layout, this one deliberately does not:
it emits the full record regardless of which columns happen to be visible. A
hidden column is a display choice, not a decision to throw the data away, and an
export that quietly dropped it would be a trap for anyone building on top.

Two shapes, same records: `to_json` for a document you open, `to_jsonl` for a
stream you pipe.
"""

from __future__ import annotations

import json
from typing import Any

from jobsheet.sheet.row import JobRow

__all__ = ["to_json", "to_jsonl", "to_records"]


def _record(row: JobRow) -> dict[str, Any]:
    posting = row.posting.model_dump(mode="json")
    return {
        "dedup_key": row.dedup_key,
        "found_at": row.found_at.isoformat(),
        "status": str(row.status),
        "category": row.category,
        "note": row.note,
        "link_text": row.link_text,
        "user_values": row.user_values,
        **posting,
    }


def to_records(rows: list[JobRow]) -> list[dict[str, Any]]:
    """The rows as plain dictionaries, JSON-ready."""
    return [_record(row) for row in rows]


def to_json(rows: list[JobRow], *, indent: int = 2) -> str:
    """One JSON document: an array of job objects."""
    return json.dumps(to_records(rows), indent=indent, ensure_ascii=False, default=str)


def to_jsonl(rows: list[JobRow]) -> str:
    """One job per line, for streaming into another tool."""
    lines = (
        json.dumps(record, ensure_ascii=False, default=str) for record in to_records(rows)
    )
    return "\n".join(lines) + ("\n" if rows else "")
