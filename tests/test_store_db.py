"""The local SQLite file.

The database is the memory behind the spreadsheet, so these tests are mostly
about *not forgetting*: a re-fetch must refresh what the source said without
touching what the user knows, and a row the user deletes from the workbook must
still be recoverable here.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from jobsheet.core.models import ApplicationStatus, Posting, Workplace
from jobsheet.sheet.row import JobRow
from jobsheet.store.db import MIGRATIONS, Database
from jobsheet.store.users import UserStore

FOUND = date(2026, 8, 24)


def posting(number: int, **overrides: Any) -> Posting:
    data: dict[str, Any] = {
        "source_id": "rss",
        "title": f"Job {number}",
        "url": f"https://example.test/j/{number}",
        "company": f"Company {number}",
        "location": "Zagreb",
        "region": "Grad Zagreb",
        "posted_at": date(2026, 8, 1),
        "deadline": date(2026, 9, 1),
        "tags": ("gis", "python"),
        "raw": {"id": number},
    }
    return Posting(**(data | overrides))


def job(number: int, **overrides: Any) -> JobRow:
    data: dict[str, Any] = {
        "posting": posting(number),
        "found_at": FOUND,
        "category": "GIS",
        "note": "found via feed",
    }
    return JobRow(**(data | overrides))


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "jobsheet.sqlite3")
    yield database
    database.close()


# ------------------------------------------------------------------ migrations


class TestMigrations:
    def test_a_fresh_file_lands_on_the_latest_version(self, db: Database) -> None:
        assert db.version == len(MIGRATIONS)

    def test_migrating_twice_changes_nothing(self, db: Database) -> None:
        assert db.migrate() == db.migrate() == len(MIGRATIONS)

    def test_reopening_an_existing_file_does_not_re_run_migrations(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "again.sqlite3"
        with Database(path) as first:
            first.save_row(job(1))
        # A second migrate() over the same file would raise "table already
        # exists" if the version were not honoured.
        with Database(path) as second:
            assert second.version == len(MIGRATIONS)
            assert len(second.all_rows()) == 1

    def test_the_parent_directory_is_created(self, tmp_path: Path) -> None:
        with Database(tmp_path / "nested" / "deeper" / "jobs.sqlite3") as database:
            assert database.path.parent.is_dir()

    def test_foreign_keys_are_enforced(self, db: Database) -> None:
        with pytest.raises(sqlite3.IntegrityError), db.transaction() as connection:
            connection.execute(
                "INSERT INTO applications (dedup_key, found_at, updated_at)"
                " VALUES ('nope', '2026-08-24', '2026-08-24')"
            )


# --------------------------------------------------------------------- writing


class TestSavingRows:
    def test_a_saved_row_reads_back_whole(self, db: Database) -> None:
        original = job(1, status=ApplicationStatus.APPLIED, user_values={"Ticked": True})
        db.save_row(original)

        (restored,) = db.all_rows()
        assert restored.posting == original.posting
        assert restored.found_at == original.found_at
        assert restored.status is ApplicationStatus.APPLIED
        assert restored.user_values == {"Ticked": True}
        assert restored.category == "GIS"
        assert restored.note == "found via feed"

    def test_tags_and_raw_survive_the_round_trip(self, db: Database) -> None:
        db.save_row(job(1))
        (restored,) = db.all_rows()
        assert restored.posting.tags == ("gis", "python")

    def test_workplace_survives_the_round_trip(self, db: Database) -> None:
        db.save_row(job(1, posting=posting(1, workplace=Workplace.REMOTE)))
        (restored,) = db.all_rows()
        assert restored.posting.workplace is Workplace.REMOTE

    def test_missing_dates_stay_missing(self, db: Database) -> None:
        db.save_row(job(1, posting=posting(1, posted_at=None, deadline=None)))
        (restored,) = db.all_rows()
        assert restored.posting.posted_at is None
        assert restored.posting.deadline is None

    def test_save_rows_reports_how_many_it_wrote(self, db: Database) -> None:
        assert db.save_rows([job(1), job(2), job(3)]) == 3
        assert len(db.all_rows()) == 3

    def test_rows_are_keyed_by_normalised_url(self, db: Database) -> None:
        db.save_row(job(1))
        db.save_row(job(1, posting=posting(1, url="https://example.test/j/1?utm_source=x")))
        assert len(db.all_rows()) == 1


class TestReSeeingAnAd:
    """A later run refreshes the source's fields and nothing else."""

    def test_the_sources_fields_are_refreshed(self, db: Database) -> None:
        db.save_row(job(1))
        db.save_row(job(1, posting=posting(1, title="Renamed", company="Bought Out")))

        (restored,) = db.all_rows()
        assert restored.posting.title == "Renamed"
        assert restored.posting.company == "Bought Out"

    def test_the_users_status_is_never_overwritten(self, db: Database) -> None:
        db.save_row(job(1, status=ApplicationStatus.INTERVIEW))
        db.save_row(job(1))  # a plain re-fetch, which always carries status NEW

        (restored,) = db.all_rows()
        assert restored.status is ApplicationStatus.INTERVIEW

    def test_the_users_own_columns_are_never_overwritten(self, db: Database) -> None:
        db.save_row(job(1, user_values={"Note to self": "call Ana"}))
        db.save_row(job(1))

        (restored,) = db.all_rows()
        assert restored.user_values == {"Note to self": "call Ana"}

    def test_the_first_found_date_is_kept(self, db: Database) -> None:
        db.save_row(job(1, found_at=date(2026, 6, 1)))
        db.save_row(job(1, found_at=date(2026, 8, 24)))

        (restored,) = db.all_rows()
        assert restored.found_at == date(2026, 6, 1)

    def test_first_seen_is_kept_and_last_seen_moves(self, db: Database) -> None:
        db.upsert_posting(posting(1), seen_on=date(2026, 6, 1))
        db.upsert_posting(posting(1), seen_on=date(2026, 8, 24))

        record = db._connection.execute("SELECT first_seen, last_seen FROM postings").fetchone()
        assert record["first_seen"] == "2026-06-01"
        assert record["last_seen"] == "2026-08-24"

    def test_a_date_a_later_run_lost_is_not_erased(self, db: Database) -> None:
        """Feeds drop fields. Losing a deadline we already knew is data loss."""
        db.upsert_posting(posting(1), seen_on=FOUND)
        db.upsert_posting(posting(1, posted_at=None, deadline=None), seen_on=FOUND)

        record = db._connection.execute("SELECT posted_at, deadline FROM postings").fetchone()
        assert record["posted_at"] == "2026-08-01"
        assert record["deadline"] == "2026-09-01"


class TestUnreadableDates:
    """A hand-edited database file should degrade, not crash."""

    def test_a_nonsense_date_reads_back_as_missing(self, db: Database) -> None:
        db.save_row(job(1))
        with db.transaction() as connection:
            connection.execute("UPDATE postings SET posted_at = 'soon'")

        (restored,) = db.all_rows()
        assert restored.posting.posted_at is None

    def test_a_nonsense_found_date_falls_back_to_today(self, db: Database) -> None:
        db.save_row(job(1))
        with db.transaction() as connection:
            connection.execute("UPDATE applications SET found_at = 'last summer'")

        (restored,) = db.all_rows()
        assert restored.found_at == date.today()


class TestKnownKeys:
    def test_it_lists_every_url_this_account_tracks(self, db: Database) -> None:
        db.save_rows([job(1), job(2)])
        assert db.known_keys() == {"example.test/j/1", "example.test/j/2"}

    def test_an_ad_stored_without_being_tracked_does_not_count(self, db: Database) -> None:
        """The ad table is shared between accounts, so it cannot answer this.

        Before accounts, an ad merely seen counted as known. It cannot now: one
        shared row would tell every account on the install that it had already
        seen an ad only one of them had. What an account knows is what it tracks.
        """
        db.upsert_posting(posting(9), seen_on=FOUND)
        assert "example.test/j/9" not in db.known_keys()
        assert db.all_rows() == []

    def test_another_account_tracking_an_ad_does_not_make_it_known(
        self, db: Database
    ) -> None:
        db.save_row(job(1))
        other = db.as_user(UserStore(db).create("other", "a-good-password").id)
        assert other.known_keys() == set()
        assert other.all_rows() == []

    def test_it_is_empty_on_a_fresh_file(self, db: Database) -> None:
        assert db.known_keys() == set()


# ----------------------------------------------------------------- run history


class TestRuns:
    def test_a_run_is_recorded_with_its_counts(self, db: Database) -> None:
        started = datetime(2026, 8, 24, 9, 0, 0)
        run_id = db.record_run(
            fetched=218,
            added=12,
            duplicates=200,
            rejected=6,
            errors={"hzz": "TimeoutError"},
            started_at=started,
        )
        assert run_id > 0

        (record,) = db.runs()
        assert record["fetched"] == 218
        assert record["added"] == 12
        assert record["duplicates"] == 200
        assert record["rejected"] == 6
        assert json.loads(record["errors"]) == {"hzz": "TimeoutError"}
        assert record["started_at"] == started.isoformat(timespec="seconds")
        assert record["finished_at"] is not None

    def test_the_newest_run_comes_first(self, db: Database) -> None:
        for fetched in (1, 2, 3):
            db.record_run(
                fetched=fetched,
                added=0,
                duplicates=0,
                rejected=0,
                errors={},
                started_at=datetime(2026, 8, 24, 9, 0, 0),
            )
        assert [record["fetched"] for record in db.runs()] == [3, 2, 1]

    def test_the_limit_is_honoured(self, db: Database) -> None:
        for _ in range(5):
            db.record_run(
                fetched=0,
                added=0,
                duplicates=0,
                rejected=0,
                errors={},
                started_at=datetime.now(),
            )
        assert len(db.runs(limit=2)) == 2


# --------------------------------------------------------------- source health


class TestSourceHealth:
    def test_a_success_is_recorded(self, db: Database) -> None:
        db.record_source_health("hzz", ok=True, count=218, message="218 ads")

        (record,) = db.source_health()
        assert record["source_id"] == "hzz"
        assert record["last_ok"] is not None
        assert record["last_error"] is None
        assert record["last_count"] == 218
        assert record["message"] == "218 ads"

    def test_a_failure_is_recorded(self, db: Database) -> None:
        db.record_source_health("hzz", ok=False, message="HTTP 451")

        (record,) = db.source_health()
        assert record["last_ok"] is None
        assert record["last_error"] is not None
        assert record["message"] == "HTTP 451"

    def test_a_later_failure_keeps_the_last_known_success(self, db: Database) -> None:
        db.record_source_health("hzz", ok=True, count=218)
        (before,) = db.source_health()

        db.record_source_health("hzz", ok=False, message="HTTP 451")
        (after,) = db.source_health()

        assert after["last_ok"] == before["last_ok"]
        assert after["last_error"] is not None

    def test_a_later_success_keeps_the_last_known_failure(self, db: Database) -> None:
        db.record_source_health("hzz", ok=False, message="HTTP 451")
        (before,) = db.source_health()

        db.record_source_health("hzz", ok=True, count=5)
        (after,) = db.source_health()

        assert after["last_error"] == before["last_error"]
        assert after["last_ok"] is not None

    def test_sources_are_listed_by_id(self, db: Database) -> None:
        db.record_source_health("remotive", ok=True)
        db.record_source_health("arbeitnow", ok=True)
        assert [record["source_id"] for record in db.source_health()] == [
            "arbeitnow",
            "remotive",
        ]


# -------------------------------------------------------------------- profiles


class TestProfiles:
    def test_a_profile_round_trips(self, db: Database) -> None:
        payload = {"keywords": ["gis", "geodet"], "location": "Rijeka"}
        db.save_profile("my search", "search", payload)
        assert db.load_profile("my search", "search") == payload

    def test_saving_again_replaces_the_payload(self, db: Database) -> None:
        db.save_profile("mine", "search", {"keywords": ["a"]})
        db.save_profile("mine", "search", {"keywords": ["b"]})
        assert db.load_profile("mine", "search") == {"keywords": ["b"]}
        assert db.list_profiles("search") == ["mine"]

    def test_the_same_name_in_two_kinds_are_two_profiles(self, db: Database) -> None:
        db.save_profile("mine", "search", {"a": 1})
        db.save_profile("mine", "layout", {"b": 2})
        assert db.load_profile("mine", "search") == {"a": 1}
        assert db.load_profile("mine", "layout") == {"b": 2}

    def test_an_unknown_profile_is_none_rather_than_an_error(self, db: Database) -> None:
        assert db.load_profile("never saved", "search") is None

    def test_profiles_are_listed_alphabetically_within_a_kind(self, db: Database) -> None:
        db.save_profile("zebra", "search", {})
        db.save_profile("alpha", "search", {})
        db.save_profile("elsewhere", "layout", {})
        assert db.list_profiles("search") == ["alpha", "zebra"]

    def test_deleting_reports_whether_anything_went(self, db: Database) -> None:
        db.save_profile("mine", "search", {})
        assert db.delete_profile("mine", "search") is True
        assert db.delete_profile("mine", "search") is False
        assert db.list_profiles("search") == []

    def test_a_date_in_a_profile_is_stored_rather_than_refused(self, db: Database) -> None:
        db.save_profile("dated", "search", {"since": date(2026, 8, 24)})
        assert db.load_profile("dated", "search") == {"since": "2026-08-24"}


# ------------------------------------------------------------------- lifecycle


class TestLifecycle:
    def test_it_works_as_a_context_manager(self, tmp_path: Path) -> None:
        path = tmp_path / "ctx.sqlite3"
        with Database(path) as database:
            database.save_row(job(1))
        assert path.exists()

    def test_data_outlives_the_process(self, tmp_path: Path) -> None:
        path = tmp_path / "persist.sqlite3"
        with Database(path) as first:
            first.save_row(job(1, status=ApplicationStatus.APPLIED))
        with Database(path) as second:
            (restored,) = second.all_rows()
            assert restored.status is ApplicationStatus.APPLIED


class TestWhichSearchFoundIt:
    """`found_at` is a date, so it cannot separate two searches on one morning."""

    def test_a_row_remembers_the_run_that_found_it(self, db: Database) -> None:
        db.save_rows([job(1)], run_id="7")
        assert db.rows(run="7") != []
        assert db.rows(run="8") == []

    def test_the_filter_counts_what_matches_not_what_was_loaded(
        self, db: Database
    ) -> None:
        db.save_rows([job(1), job(2)], run_id="7")
        db.save_rows([job(3)], run_id="8")
        assert db.count_rows(run="7") == 2
        assert db.count_rows(run="8") == 1
        assert db.count_rows() == 3

    def test_seeing_an_ad_again_does_not_move_it_to_the_later_search(
        self, db: Database
    ) -> None:
        """The stamp says which search *found* it. A second sighting is not that."""
        db.save_rows([job(1)], run_id="7")
        db.save_rows([job(1)], run_id="8")
        assert db.count_rows(run="7") == 1
        assert db.count_rows(run="8") == 0

    def test_rows_from_before_the_column_existed_are_not_lost(
        self, db: Database
    ) -> None:
        """An unstamped row belongs to no run, but still belongs to the user."""
        db.save_rows([job(1)])
        assert db.count_rows() == 1
        assert db.count_rows(run="7") == 0


class TestNotBringingItBack:
    """Two memories, because they record two different decisions."""

    def test_deleting_a_job_leaves_a_tombstone(self, db: Database) -> None:
        db.save_rows([job(1)])
        key = job(1).dedup_key
        assert db.delete_row(key)
        assert db.row(key) is None
        assert key in db.forgotten_keys()

    def test_one_account_deleting_does_not_speak_for_another(
        self, db: Database
    ) -> None:
        store = UserStore(db)
        ana = store.create("ana", "a-good-password")
        ivo = store.create("ivo", "a-good-password")
        hers, his = db.as_user(ana.id), db.as_user(ivo.id)

        hers.save_rows([job(1)])
        his.save_rows([job(1)])
        hers.delete_row(job(1).dedup_key)

        assert hers.forgotten_keys() == {job(1).dedup_key}
        assert his.forgotten_keys() == set()

    def test_a_filtered_ad_is_remembered_against_the_search_that_refused_it(
        self, db: Database
    ) -> None:
        db.remember_filtered([("example.test/j/1", "deadline_passed")], profile_key="abc")
        assert db.filtered_out_keys("abc") == {"example.test/j/1"}

    def test_changing_the_search_gives_a_refused_ad_another_hearing(
        self, db: Database
    ) -> None:
        """The decision belonged to one search. It must not outlive it."""
        db.remember_filtered([("example.test/j/1", "employment_type")], profile_key="abc")
        assert db.filtered_out_keys("xyz") == set()

    def test_refusing_the_same_ad_twice_updates_rather_than_raises(
        self, db: Database
    ) -> None:
        db.remember_filtered([("example.test/j/1", "too_old")], profile_key="abc")
        db.remember_filtered([("example.test/j/1", "deadline_passed")], profile_key="abc")
        assert db.filtered_out_keys("abc") == {"example.test/j/1"}

    def test_an_ad_with_no_key_is_not_remembered(self, db: Database) -> None:
        """Nothing can be addressed by an empty key, so nothing should be stored."""
        db.remember_filtered([("", "no_url")], profile_key="abc")
        assert db.filtered_out_keys("abc") == set()
