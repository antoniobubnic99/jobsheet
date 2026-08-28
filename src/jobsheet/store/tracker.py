"""Where the user is with each application, and how they got there.

Status is the user's claim about the world, so two rules hold everywhere:

* **A search never changes a status.** Re-fetching an ad refreshes what the
  source said; it cannot un-apply the user from a job.
* **Every change is recorded.** "When did I apply?" and "when did they say no?"
  are the questions a spreadsheet alone cannot answer, and they are exactly the
  questions people have three months into a search.

The board columns are the statuses in order, which is what the kanban view draws.

Every statement here is scoped to `db.user_id`, the account the handle was
opened for. Status is a claim about one person's world, and two people on
one install must never be able to move each other's cards.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from jobsheet.core.models import ApplicationStatus
from jobsheet.sheet.row import JobRow
from jobsheet.store.db import Database

__all__ = ["BOARD_ORDER", "StatusChange", "Tracker", "merge_from_sheet"]

# Left to right on the board, and the board reads as a story told in that
# direction: the ones you threw out, the ones you have not looked at, then how
# far each of the rest got.
#
# `SKIPPED` leads because it is where most cards go and where nobody wants to
# look -- first column, off to the side, out of the way of the four that matter.
# It stays at the opposite end from `REJECTED` because "I decided against it" is
# a different story from "they decided against me", and a board that files them
# together loses something the person looking at it cares about.
BOARD_ORDER: tuple[ApplicationStatus, ...] = (
    ApplicationStatus.SKIPPED,
    ApplicationStatus.NEW,
    ApplicationStatus.APPLIED,
    ApplicationStatus.INTERVIEW,
    ApplicationStatus.OFFER,
    ApplicationStatus.REJECTED,
)


@dataclass
class StatusChange:
    """One movement of one application."""

    dedup_key: str
    at: datetime
    from_status: ApplicationStatus
    to_status: ApplicationStatus
    note: str = ""


class Tracker:
    """Reads and writes application status, keeping the history."""

    def __init__(self, database: Database) -> None:
        self.db = database

    def status_of(self, dedup_key: str) -> ApplicationStatus:
        cursor = self.db._connection.execute(
            "SELECT status FROM applications WHERE user_id = ? AND dedup_key = ?",
            (self.db.user_id, dedup_key),
        )
        record = cursor.fetchone()
        return ApplicationStatus(record[0]) if record else ApplicationStatus.NEW

    def knows(self, dedup_key: str) -> bool:
        """Whether this job is tracked at all.

        `status_of` cannot answer this: it reports `NEW` both for a job that is
        genuinely new and for one the database has never heard of.
        """
        cursor = self.db._connection.execute(
            "SELECT 1 FROM applications WHERE user_id = ? AND dedup_key = ?",
            (self.db.user_id, dedup_key),
        )
        return cursor.fetchone() is not None

    def set_status(
        self, dedup_key: str, status: ApplicationStatus, *, note: str = ""
    ) -> StatusChange | None:
        """Move an application. Returns `None` when nothing actually changed.

        Setting a status to what it already is is not an event: a user dragging a
        card back where it started should not litter their history.

        An untracked job is also `None` rather than an error. History hangs off
        the ad, so recording a move for an ad that was never stored would leave
        an event pointing at nothing -- and the foreign key would refuse it
        anyway. Callers that want the job adopted should store it first; see
        `merge_from_sheet`.
        """
        if not self.knows(dedup_key):
            return None

        previous = self.status_of(dedup_key)
        if previous is status:
            return None

        now = datetime.now()
        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE applications SET status = ?, updated_at = ?"
                " WHERE user_id = ? AND dedup_key = ?",
                (str(status), now.isoformat(timespec="seconds"), self.db.user_id, dedup_key),
            )
            connection.execute(
                """
                INSERT INTO application_events
                    (user_id, dedup_key, at, from_status, to_status, note)
                VALUES (?,?,?,?,?,?)
                """,
                (
                    self.db.user_id,
                    dedup_key,
                    now.isoformat(timespec="seconds"),
                    str(previous),
                    str(status),
                    note,
                ),
            )
        return StatusChange(dedup_key, now, previous, status, note)

    def history(self, dedup_key: str) -> list[StatusChange]:
        cursor = self.db._connection.execute(
            """
            SELECT dedup_key, at, from_status, to_status, note
            FROM application_events
            WHERE user_id = ? AND dedup_key = ? ORDER BY at, id
            """,
            (self.db.user_id, dedup_key),
        )
        return [
            StatusChange(
                dedup_key=record["dedup_key"],
                at=datetime.fromisoformat(record["at"]),
                from_status=ApplicationStatus(record["from_status"]),
                to_status=ApplicationStatus(record["to_status"]),
                note=record["note"],
            )
            for record in cursor.fetchall()
        ]

    def board(self) -> dict[str, list[JobRow]]:
        """Every tracked job, grouped into the board's columns."""
        columns: dict[str, list[JobRow]] = {str(s): [] for s in BOARD_ORDER}
        for row in self.db.all_rows():
            columns.setdefault(str(row.status), []).append(row)
        return columns

    def counts(self) -> dict[str, int]:
        return {name: len(rows) for name, rows in self.board().items()}

    def set_user_values(self, dedup_key: str, values: dict[str, Any]) -> None:
        """Replace the user's own column values for one job."""
        import json

        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE applications SET user_values = ?, updated_at = ?"
                " WHERE user_id = ? AND dedup_key = ?",
                (
                    json.dumps(values, default=str),
                    datetime.now().isoformat(timespec="seconds"),
                    self.db.user_id,
                    dedup_key,
                ),
            )


def merge_from_sheet(tracker: Tracker, rows: list[JobRow]) -> list[StatusChange]:
    """Pull the user's edits out of the workbook and back into the database.

    People change a status in Excel because Excel is open in front of them. If
    those edits only lived in the file, the next write would quietly revert them
    and the history would never know they happened.

    Only user-owned data moves in this direction. Titles, companies and dates
    belong to the source and are refreshed from it, not from the sheet.

    A row the database has never seen is adopted rather than dropped. That
    happens for real: someone pastes a job in by hand, or restores an old
    workbook next to a fresh database. It is stored as `NEW` first so that the
    status the sheet carries is recorded as a proper move, with a date, instead
    of appearing as though it had always been that way.
    """
    changes: list[StatusChange] = []
    for row in rows:
        if not tracker.knows(row.dedup_key):
            tracker.db.save_row(row.model_copy(update={"status": ApplicationStatus.NEW}))
        if change := tracker.set_status(row.dedup_key, row.status, note="edited in the workbook"):
            changes.append(change)
        if row.user_values:
            tracker.set_user_values(row.dedup_key, row.user_values)
    return changes
