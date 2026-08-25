"""Application status and its history.

Two rules are load-bearing and each has its own test here:

* a search never changes a status, and
* every change the user does make is recorded, so "when did I apply?" has an
  answer three months later.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from jobsheet.core.models import ApplicationStatus, Posting
from jobsheet.sheet.row import JobRow
from jobsheet.store.db import Database
from jobsheet.store.tracker import BOARD_ORDER, StatusChange, Tracker, merge_from_sheet

FOUND = date(2026, 8, 24)


def posting(number: int, **overrides: Any) -> Posting:
    data: dict[str, Any] = {
        "source_id": "rss",
        "title": f"Job {number}",
        "url": f"https://example.test/j/{number}",
        "company": f"Company {number}",
    }
    return Posting(**(data | overrides))


def job(number: int, **overrides: Any) -> JobRow:
    data: dict[str, Any] = {"posting": posting(number), "found_at": FOUND}
    return JobRow(**(data | overrides))


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "jobsheet.sqlite3")
    yield database
    database.close()


@pytest.fixture
def tracker(db: Database) -> Tracker:
    return Tracker(db)


def key(number: int) -> str:
    return posting(number).dedup_key


# ------------------------------------------------------------------- the board


class TestBoardOrder:
    def test_every_status_has_a_column(self) -> None:
        assert set(BOARD_ORDER) == set(ApplicationStatus)

    def test_new_leads_and_skipped_trails(self) -> None:
        assert BOARD_ORDER[0] is ApplicationStatus.NEW
        assert BOARD_ORDER[-1] is ApplicationStatus.SKIPPED

    def test_my_decision_is_not_filed_under_their_decision(self) -> None:
        """SKIPPED sits apart from REJECTED on purpose; they are different stories."""
        rejected = BOARD_ORDER.index(ApplicationStatus.REJECTED)
        skipped = BOARD_ORDER.index(ApplicationStatus.SKIPPED)
        assert skipped > rejected


# ---------------------------------------------------------------- reading back


class TestStatusOf:
    def test_an_untracked_job_reads_as_new(self, tracker: Tracker) -> None:
        assert tracker.status_of("nothing/here") is ApplicationStatus.NEW

    def test_a_saved_status_reads_back(self, db: Database, tracker: Tracker) -> None:
        db.save_row(job(1, status=ApplicationStatus.APPLIED))
        assert tracker.status_of(key(1)) is ApplicationStatus.APPLIED


# ------------------------------------------------------------------- moving on


class TestSetStatus:
    def test_moving_an_application_reports_the_change(
        self, db: Database, tracker: Tracker
    ) -> None:
        db.save_row(job(1))
        change = tracker.set_status(key(1), ApplicationStatus.APPLIED, note="sent CV")

        assert change is not None
        assert change.dedup_key == key(1)
        assert change.from_status is ApplicationStatus.NEW
        assert change.to_status is ApplicationStatus.APPLIED
        assert change.note == "sent CV"
        assert tracker.status_of(key(1)) is ApplicationStatus.APPLIED

    def test_moving_a_card_back_where_it_started_is_not_an_event(
        self, db: Database, tracker: Tracker
    ) -> None:
        db.save_row(job(1, status=ApplicationStatus.APPLIED))
        assert tracker.set_status(key(1), ApplicationStatus.APPLIED) is None
        assert tracker.history(key(1)) == []

    def test_the_change_is_persisted_not_just_returned(
        self, db: Database, tracker: Tracker, tmp_path: Path
    ) -> None:
        db.save_row(job(1))
        tracker.set_status(key(1), ApplicationStatus.OFFER)
        db.close()

        with Database(tmp_path / "jobsheet.sqlite3") as reopened:
            assert Tracker(reopened).status_of(key(1)) is ApplicationStatus.OFFER

    def test_updated_at_moves_with_the_status(self, db: Database, tracker: Tracker) -> None:
        db.save_row(job(1))
        before = db._connection.execute(
            "SELECT updated_at FROM applications WHERE dedup_key = ?", (key(1),)
        ).fetchone()[0]

        tracker.set_status(key(1), ApplicationStatus.INTERVIEW)
        after = db._connection.execute(
            "SELECT updated_at FROM applications WHERE dedup_key = ?", (key(1),)
        ).fetchone()[0]

        assert after >= before


class TestHistory:
    def test_it_is_empty_until_something_moves(self, db: Database, tracker: Tracker) -> None:
        db.save_row(job(1))
        assert tracker.history(key(1)) == []

    def test_every_step_is_kept_in_order(self, db: Database, tracker: Tracker) -> None:
        db.save_row(job(1))
        for status in (
            ApplicationStatus.APPLIED,
            ApplicationStatus.INTERVIEW,
            ApplicationStatus.OFFER,
        ):
            tracker.set_status(key(1), status)

        steps = tracker.history(key(1))
        assert [step.to_status for step in steps] == [
            ApplicationStatus.APPLIED,
            ApplicationStatus.INTERVIEW,
            ApplicationStatus.OFFER,
        ]
        assert [step.from_status for step in steps] == [
            ApplicationStatus.NEW,
            ApplicationStatus.APPLIED,
            ApplicationStatus.INTERVIEW,
        ]

    def test_two_moves_in_the_same_second_stay_in_order(
        self, db: Database, tracker: Tracker
    ) -> None:
        """Timestamps are second-resolution, so the tie-break has to be the row id."""
        db.save_row(job(1))
        tracker.set_status(key(1), ApplicationStatus.APPLIED)
        tracker.set_status(key(1), ApplicationStatus.REJECTED)

        assert [step.to_status for step in tracker.history(key(1))] == [
            ApplicationStatus.APPLIED,
            ApplicationStatus.REJECTED,
        ]

    def test_notes_are_kept(self, db: Database, tracker: Tracker) -> None:
        db.save_row(job(1))
        tracker.set_status(key(1), ApplicationStatus.REJECTED, note="no reply for 6 weeks")
        assert tracker.history(key(1))[0].note == "no reply for 6 weeks"

    def test_each_job_keeps_its_own_history(self, db: Database, tracker: Tracker) -> None:
        db.save_rows([job(1), job(2)])
        tracker.set_status(key(1), ApplicationStatus.APPLIED)
        tracker.set_status(key(2), ApplicationStatus.SKIPPED)

        assert len(tracker.history(key(1))) == 1
        assert tracker.history(key(2))[0].to_status is ApplicationStatus.SKIPPED

    def test_timestamps_come_back_as_datetimes(self, db: Database, tracker: Tracker) -> None:
        db.save_row(job(1))
        tracker.set_status(key(1), ApplicationStatus.APPLIED)
        assert isinstance(tracker.history(key(1))[0].at, datetime)

    def test_history_survives_the_ad_being_re_fetched(
        self, db: Database, tracker: Tracker
    ) -> None:
        db.save_row(job(1))
        tracker.set_status(key(1), ApplicationStatus.APPLIED)
        db.save_row(job(1))  # a later run sees the same ad again

        assert len(tracker.history(key(1))) == 1
        assert tracker.status_of(key(1)) is ApplicationStatus.APPLIED


# ------------------------------------------------------------------- the board


class TestBoard:
    def test_a_fresh_database_has_every_column_but_no_cards(
        self, tracker: Tracker
    ) -> None:
        board = tracker.board()
        assert list(board) == [str(status) for status in BOARD_ORDER]
        assert all(cards == [] for cards in board.values())

    def test_jobs_land_in_their_own_column(self, db: Database, tracker: Tracker) -> None:
        db.save_rows(
            [
                job(1),
                job(2, status=ApplicationStatus.APPLIED),
                job(3, status=ApplicationStatus.APPLIED),
                job(4, status=ApplicationStatus.OFFER),
            ]
        )
        board = tracker.board()
        assert len(board["new"]) == 1
        assert len(board["applied"]) == 2
        assert len(board["offer"]) == 1
        assert board["interview"] == []

    def test_counts_mirror_the_board(self, db: Database, tracker: Tracker) -> None:
        db.save_rows([job(1), job(2, status=ApplicationStatus.APPLIED)])
        assert tracker.counts() == {
            "new": 1,
            "applied": 1,
            "interview": 0,
            "offer": 0,
            "rejected": 0,
            "skipped": 0,
        }

    def test_moving_a_card_moves_it_on_the_board(
        self, db: Database, tracker: Tracker
    ) -> None:
        db.save_row(job(1))
        tracker.set_status(key(1), ApplicationStatus.INTERVIEW)

        board = tracker.board()
        assert board["new"] == []
        assert [row.dedup_key for row in board["interview"]] == [key(1)]


# --------------------------------------------------------------- user's columns


class TestUserValues:
    def test_values_are_replaced_wholesale(self, db: Database, tracker: Tracker) -> None:
        db.save_row(job(1, user_values={"Ticked": True, "Who": "Ana"}))
        tracker.set_user_values(key(1), {"Ticked": False})

        (row,) = db.all_rows()
        assert row.user_values == {"Ticked": False}

    def test_they_reach_the_next_read(self, db: Database, tracker: Tracker) -> None:
        db.save_row(job(1))
        tracker.set_user_values(key(1), {"Rating": 5})

        (row,) = db.all_rows()
        assert row.user_values == {"Rating": 5}


# ------------------------------------------------------- edits made in Excel


class TestMergeFromSheet:
    def test_a_status_typed_in_excel_reaches_the_database(
        self, db: Database, tracker: Tracker
    ) -> None:
        db.save_row(job(1))
        changes = merge_from_sheet(tracker, [job(1, status=ApplicationStatus.APPLIED)])

        assert [change.to_status for change in changes] == [ApplicationStatus.APPLIED]
        assert tracker.status_of(key(1)) is ApplicationStatus.APPLIED

    def test_the_change_is_labelled_as_coming_from_the_workbook(
        self, db: Database, tracker: Tracker
    ) -> None:
        db.save_row(job(1))
        merge_from_sheet(tracker, [job(1, status=ApplicationStatus.APPLIED)])
        assert "workbook" in tracker.history(key(1))[0].note

    def test_untouched_rows_produce_no_events(self, db: Database, tracker: Tracker) -> None:
        db.save_row(job(1, status=ApplicationStatus.APPLIED))
        assert merge_from_sheet(tracker, [job(1, status=ApplicationStatus.APPLIED)]) == []

    def test_notes_typed_into_a_user_column_come_back(
        self, db: Database, tracker: Tracker
    ) -> None:
        db.save_row(job(1))
        merge_from_sheet(tracker, [job(1, user_values={"Note to self": "call Ana"})])

        (row,) = db.all_rows()
        assert row.user_values == {"Note to self": "call Ana"}

    def test_an_empty_user_column_does_not_wipe_what_is_stored(
        self, db: Database, tracker: Tracker
    ) -> None:
        """A layout without user columns must not erase values it cannot see."""
        db.save_row(job(1, user_values={"Rating": 5}))
        merge_from_sheet(tracker, [job(1)])

        (row,) = db.all_rows()
        assert row.user_values == {"Rating": 5}

    def test_the_source_side_of_the_row_is_not_taken_from_the_sheet(
        self, db: Database, tracker: Tracker
    ) -> None:
        """Titles belong to the source. A typo in Excel must not become the record."""
        db.save_row(job(1))
        merge_from_sheet(
            tracker, [job(1, posting=posting(1, title="typed over by hand"))]
        )

        (row,) = db.all_rows()
        assert row.posting.title == "Job 1"

    def test_several_rows_are_merged_in_one_pass(
        self, db: Database, tracker: Tracker
    ) -> None:
        db.save_rows([job(1), job(2), job(3)])
        changes = merge_from_sheet(
            tracker,
            [
                job(1, status=ApplicationStatus.APPLIED),
                job(2),
                job(3, status=ApplicationStatus.SKIPPED),
            ],
        )
        assert {change.dedup_key for change in changes} == {key(1), key(3)}

    def test_a_row_the_sheet_knows_but_the_database_does_not_is_adopted(
        self, db: Database, tracker: Tracker
    ) -> None:
        """Someone pasted a row in by hand, or restored an old workbook."""
        changes = merge_from_sheet(tracker, [job(99, status=ApplicationStatus.APPLIED)])

        assert [change.to_status for change in changes] == [ApplicationStatus.APPLIED]
        assert tracker.status_of(key(99)) is ApplicationStatus.APPLIED
        assert [row.dedup_key for row in db.all_rows()] == [key(99)]

    def test_an_adopted_row_gets_a_dated_move_rather_than_a_silent_one(
        self, tracker: Tracker
    ) -> None:
        merge_from_sheet(tracker, [job(99, status=ApplicationStatus.INTERVIEW)])

        (step,) = tracker.history(key(99))
        assert step.from_status is ApplicationStatus.NEW
        assert step.to_status is ApplicationStatus.INTERVIEW


class TestUntrackedJobs:
    """`status_of` reports NEW for an unknown key, so moving one needs a guard."""

    def test_it_knows_what_it_has(self, db: Database, tracker: Tracker) -> None:
        db.save_row(job(1))
        assert tracker.knows(key(1)) is True
        assert tracker.knows(key(2)) is False

    def test_moving_an_untracked_job_is_none_rather_than_an_error(
        self, tracker: Tracker
    ) -> None:
        assert tracker.set_status(key(1), ApplicationStatus.APPLIED) is None

    def test_no_orphan_event_is_left_behind(self, db: Database, tracker: Tracker) -> None:
        tracker.set_status(key(1), ApplicationStatus.APPLIED)
        count = db._connection.execute("SELECT COUNT(*) FROM application_events").fetchone()[0]
        assert count == 0


class TestStatusChange:
    def test_it_carries_the_whole_story(self) -> None:
        change = StatusChange(
            dedup_key="example.test/j/1",
            at=datetime(2026, 8, 24, 9, 30),
            from_status=ApplicationStatus.NEW,
            to_status=ApplicationStatus.APPLIED,
        )
        assert change.note == ""
        assert change.to_status is ApplicationStatus.APPLIED
