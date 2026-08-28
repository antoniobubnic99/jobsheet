"""Accounts, sessions, and the line between two people's job searches.

The tests here divide into two kinds, and the second kind is the one that earns
its keep. The first checks that signing in works, which would fail loudly if it
did not. The second checks that one account cannot see another's rows -- and
that failure would be *silent*: no error, no crash, just somebody's spreadsheet
quietly filling up with a stranger's applications. So every table that gained a
`user_id` is tested from both sides, and the upgrade path from a database that
predates accounts is tested with a real v1 file rather than a mock of one.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from jobsheet.api.app import create_app
from jobsheet.api.state import SESSION_COOKIE, TOKEN_HEADER
from jobsheet.config import Settings, user_folder
from jobsheet.core.models import ApplicationStatus, Posting
from jobsheet.sheet.row import JobRow
from jobsheet.sources import registry
from jobsheet.store.db import MIGRATIONS, Database
from jobsheet.store.users import (
    LoginThrottle,
    UserError,
    UserStore,
    check_password,
    hash_password,
    normalise_username,
    verify_password,
)

BASE_URL = "http://127.0.0.1:8765"
FOUND = date(2026, 8, 24)
GOOD = "a-good-password"


def ad(number: int, **overrides: Any) -> Posting:
    data: dict[str, Any] = {
        "source_id": "rss",
        "title": f"Job {number}",
        "url": f"https://example.test/j/{number}",
        "company": f"Company {number}",
        "location": "Rijeka",
        "posted_at": FOUND,
    }
    return Posting(**(data | overrides))


def job(number: int, **overrides: Any) -> JobRow:
    return JobRow(**({"posting": ad(number), "found_at": FOUND} | overrides))


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    with Database(tmp_path / "jobsheet.sqlite3") as database:
        yield database


@pytest.fixture
def store(db: Database) -> UserStore:
    return UserStore(db)


# ----------------------------------------------------------------- passwords


class TestPasswords:
    def test_a_password_verifies_against_its_own_hash(self) -> None:
        assert verify_password(GOOD, hash_password(GOOD))

    def test_a_wrong_password_does_not(self) -> None:
        assert not verify_password("nearly-right", hash_password(GOOD))

    def test_the_same_password_hashes_differently_every_time(self) -> None:
        """Salted. Two people with the same password must not look the same."""
        assert hash_password(GOOD) != hash_password(GOOD)

    def test_the_cost_travels_with_the_hash(self) -> None:
        """So the parameters can be raised later without stranding old accounts."""
        scheme, n, r, p, _salt, _digest = hash_password(GOOD).split("$")
        assert scheme == "scrypt"
        assert (int(n), int(r), int(p)) == (2**14, 8, 1)

    @pytest.mark.parametrize(
        "stored", ["", "not-a-hash", "scrypt$oops", "bcrypt$1$2$3$abc$def", "$$$$$"]
    )
    def test_nonsense_in_the_column_is_a_refusal_not_a_crash(self, stored: str) -> None:
        assert not verify_password(GOOD, stored)

    def test_an_empty_hash_matches_nothing_at_all(self) -> None:
        """A claimable account has no password, so no password may open it."""
        assert not verify_password("", "")

    def test_a_short_password_is_refused_by_name(self) -> None:
        with pytest.raises(UserError) as caught:
            check_password("short")
        assert caught.value.code == "password_too_short"

    def test_a_password_equal_to_the_username_is_refused(self) -> None:
        with pytest.raises(UserError) as caught:
            check_password("Zeljko-Baric", username="zeljko-baric")
        assert caught.value.code == "password_is_username"


class TestUsernames:
    @pytest.mark.parametrize("name", ["ana", "ana.b", "ivo_2", "Željko", "user-1"])
    def test_reasonable_names_are_accepted(self, name: str) -> None:
        display, folded = normalise_username(name)
        assert display == name
        assert folded

    @pytest.mark.parametrize("name", ["", "ab", "_leading", ".dot", "a" * 33, "with space"])
    def test_unreasonable_names_are_refused(self, name: str) -> None:
        with pytest.raises(UserError) as caught:
            normalise_username(name)
        assert caught.value.code == "username_invalid"

    def test_folding_makes_accented_and_plain_the_same_account(self) -> None:
        """Two accounts a person could not tell apart on screen are one account."""
        assert normalise_username("Željko")[1] == normalise_username("zeljko")[1]


# ------------------------------------------------------------------ the store


class TestAccounts:
    def test_a_new_account_can_be_authenticated(self, store: UserStore) -> None:
        created = store.create("ana", GOOD)
        assert store.authenticate("ana", GOOD) == created

    def test_the_name_is_matched_case_insensitively(self, store: UserStore) -> None:
        store.create("Ana", GOOD)
        assert store.authenticate("ANA", GOOD) is not None

    def test_a_wrong_password_authenticates_to_nothing(self, store: UserStore) -> None:
        store.create("ana", GOOD)
        assert store.authenticate("ana", "wrong-password") is None

    def test_an_unknown_name_authenticates_to_nothing(self, store: UserStore) -> None:
        assert store.authenticate("nobody", GOOD) is None

    def test_a_taken_name_is_refused_by_name(self, store: UserStore) -> None:
        store.create("ana", GOOD)
        with pytest.raises(UserError) as caught:
            store.create("ANA", "another-good-one")
        assert caught.value.code == "username_taken"

    def test_the_hash_never_leaves_the_table(self, store: UserStore) -> None:
        user = store.create("ana", GOOD)
        assert "password" not in user.model_dump()
        assert user.has_password is True

    def test_changing_a_password_invalidates_the_old_one(self, store: UserStore) -> None:
        user = store.create("ana", GOOD)
        store.set_password(user.id, "a-different-password")
        assert store.authenticate("ana", GOOD) is None
        assert store.authenticate("ana", "a-different-password") is not None


class TestSessions:
    def test_a_token_resolves_to_its_account(self, store: UserStore) -> None:
        user = store.create("ana", GOOD)
        assert store.resolve(store.open_session(user.id)) == user

    def test_an_unknown_token_resolves_to_nobody(self, store: UserStore) -> None:
        store.create("ana", GOOD)
        assert store.resolve("made-up") is None
        assert store.resolve("") is None

    def test_the_raw_token_is_not_in_the_database(self, store: UserStore, db: Database) -> None:
        token = store.open_session(store.create("ana", GOOD).id)
        stored = db._connection.execute("SELECT token_hash FROM sessions").fetchone()[0]
        assert token not in stored

    def test_closing_a_session_ends_it(self, store: UserStore) -> None:
        token = store.open_session(store.create("ana", GOOD).id)
        assert store.close_session(token)
        assert store.resolve(token) is None

    def test_an_expired_session_resolves_to_nobody_and_is_swept(
        self, store: UserStore, db: Database
    ) -> None:
        token = store.open_session(store.create("ana", GOOD).id, days=-1)
        assert store.resolve(token) is None
        assert db._connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0

    def test_closing_all_sessions_leaves_none(self, store: UserStore) -> None:
        user = store.create("ana", GOOD)
        tokens = [store.open_session(user.id) for _ in range(3)]
        assert store.close_all(user.id) == 3
        assert all(store.resolve(token) is None for token in tokens)


class TestThrottle:
    def test_a_few_wrong_guesses_do_not_lock_anybody_out(self) -> None:
        throttle = LoginThrottle()
        for _ in range(3):
            throttle.failed("ana")
        assert throttle.locked_for("ana") == 0

    def test_enough_wrong_guesses_do(self) -> None:
        throttle = LoginThrottle()
        for _ in range(throttle.allowance):
            throttle.failed("ana")
        assert throttle.locked_for("ana") > 0

    def test_the_penalty_grows(self) -> None:
        throttle = LoginThrottle()
        for _ in range(throttle.allowance):
            throttle.failed("ana")
        first = throttle.locked_for("ana")
        throttle.failed("ana")
        assert throttle.locked_for("ana") > first

    def test_it_never_grows_past_the_ceiling(self) -> None:
        throttle = LoginThrottle()
        for _ in range(40):
            throttle.failed("ana")
        assert throttle.locked_for("ana") <= throttle.max_penalty.total_seconds()

    def test_signing_in_clears_the_record(self) -> None:
        throttle = LoginThrottle()
        for _ in range(throttle.allowance):
            throttle.failed("ana")
        throttle.succeeded("ana")
        assert throttle.locked_for("ana") == 0

    def test_it_locks_one_name_not_the_whole_install(self) -> None:
        throttle = LoginThrottle()
        for _ in range(throttle.allowance):
            throttle.failed("ana")
        assert throttle.locked_for("ivo") == 0

    def test_the_lock_lifts_when_its_time_is_up(self) -> None:
        throttle = LoginThrottle()
        now = datetime(2026, 8, 24, 12, 0, 0)
        for _ in range(throttle.allowance):
            throttle.failed("ana", now=now)
        assert throttle.locked_for("ana", now=now) > 0
        assert throttle.locked_for("ana", now=now + timedelta(hours=1)) == 0


# ----------------------------------------------------------------- isolation


class TestTwoAccounts:
    """The silent failure. Every one of these would pass if `user_id` were dropped."""

    @pytest.fixture
    def pair(self, db: Database, store: UserStore) -> tuple[Database, Database]:
        ana = db.as_user(store.create("ana", GOOD).id)
        ivo = db.as_user(store.create("ivo", "another-good-one").id)
        return ana, ivo

    def test_rows_do_not_cross(self, pair: tuple[Database, Database]) -> None:
        ana, ivo = pair
        ana.save_rows([job(1), job(2)])
        ivo.save_row(job(3))

        assert {row.dedup_key for row in ana.all_rows()} == {
            "example.test/j/1",
            "example.test/j/2",
        }
        assert {row.dedup_key for row in ivo.all_rows()} == {"example.test/j/3"}

    def test_the_same_ad_can_be_tracked_by_both_independently(
        self, pair: tuple[Database, Database]
    ) -> None:
        """One ad, two opinions of it. The shared posting is what makes this cheap."""
        ana, ivo = pair
        ana.save_row(job(1, status=ApplicationStatus.APPLIED))
        ivo.save_row(job(1, status=ApplicationStatus.SKIPPED))

        assert ana.all_rows()[0].status is ApplicationStatus.APPLIED
        assert ivo.all_rows()[0].status is ApplicationStatus.SKIPPED

    def test_deleting_a_job_leaves_the_other_account_untouched(
        self, pair: tuple[Database, Database]
    ) -> None:
        ana, ivo = pair
        ana.save_row(job(1))
        ivo.save_row(job(1))

        assert ana.delete_row("example.test/j/1")
        assert ana.all_rows() == []
        assert len(ivo.all_rows()) == 1

    def test_the_ad_itself_goes_when_the_last_account_lets_go(
        self, pair: tuple[Database, Database], db: Database
    ) -> None:
        ana, ivo = pair
        ana.save_row(job(1))
        ivo.save_row(job(1))
        ana.delete_row("example.test/j/1")
        ivo.delete_row("example.test/j/1")

        left = db._connection.execute("SELECT COUNT(*) FROM postings").fetchone()[0]
        assert left == 0

    def test_counting_and_paging_respect_the_account(
        self, pair: tuple[Database, Database]
    ) -> None:
        ana, ivo = pair
        ana.save_rows([job(number) for number in range(5)])
        ivo.save_row(job(99))

        assert ana.count_rows() == 5
        assert ivo.count_rows() == 1
        assert len(ivo.rows(limit=10)) == 1

    def test_a_search_query_cannot_reach_across(self, pair: tuple[Database, Database]) -> None:
        ana, ivo = pair
        ana.save_row(job(1, posting=ad(1, title="Surveyor in Rijeka")))
        assert ivo.rows(query="surveyor") == []

    def test_one_account_cannot_fetch_the_others_row_by_key(
        self, pair: tuple[Database, Database]
    ) -> None:
        ana, ivo = pair
        ana.save_row(job(1))
        assert ivo.row("example.test/j/1") is None

    def test_saved_profiles_do_not_cross(self, pair: tuple[Database, Database]) -> None:
        ana, ivo = pair
        ana.save_profile("mine", "search", {"locations": ["Rijeka"]})

        assert ana.list_profiles("search") == ["mine"]
        assert ivo.list_profiles("search") == []
        assert ivo.load_profile("mine", "search") is None
        assert not ivo.delete_profile("mine", "search")

    def test_two_accounts_can_use_the_same_profile_name(
        self, pair: tuple[Database, Database]
    ) -> None:
        ana, ivo = pair
        ana.save_profile("default", "search", {"locations": ["Rijeka"]})
        ivo.save_profile("default", "search", {"locations": ["Split"]})

        assert ana.load_profile("default", "search") == {"locations": ["Rijeka"]}
        assert ivo.load_profile("default", "search") == {"locations": ["Split"]}

    def test_run_history_does_not_cross(self, pair: tuple[Database, Database]) -> None:
        ana, ivo = pair
        ana.record_run(
            fetched=3, added=1, duplicates=0, rejected=2, errors={}, started_at=datetime.now()
        )
        assert len(ana.runs()) == 1
        assert ivo.runs() == []

    def test_status_history_does_not_cross(
        self, pair: tuple[Database, Database]
    ) -> None:
        from jobsheet.store.tracker import Tracker

        ana, ivo = pair
        ana.save_row(job(1))
        ivo.save_row(job(1))
        Tracker(ana).set_status("example.test/j/1", ApplicationStatus.APPLIED)

        assert Tracker(ivo).status_of("example.test/j/1") is ApplicationStatus.NEW
        assert Tracker(ivo).history("example.test/j/1") == []
        assert len(Tracker(ana).history("example.test/j/1")) == 1

    def test_the_board_only_shows_your_own_cards(
        self, pair: tuple[Database, Database]
    ) -> None:
        from jobsheet.store.tracker import Tracker

        ana, ivo = pair
        ana.save_rows([job(1), job(2)])
        assert sum(len(column) for column in Tracker(ivo).board().values()) == 0
        assert sum(len(column) for column in Tracker(ana).board().values()) == 2

    def test_a_handle_without_an_account_refuses_to_guess(self, db: Database) -> None:
        """Two accounts and no `user_id` is a question, not a default."""
        UserStore(db).create("ana", GOOD)
        UserStore(db).create("ivo", "another-good-one")
        with pytest.raises(LookupError, match="more than one account"):
            _ = Database(db.path).user_id


class TestPerAccountPaths:
    def test_the_first_account_keeps_the_original_layout(self, tmp_path: Path) -> None:
        """Upgrading an install must not appear to move somebody's spreadsheet."""
        settings = Settings(home=tmp_path / "home")
        with Database(settings.database_path) as db:
            ana = UserStore(db).create("ana", GOOD)
        assert settings.for_user(ana, primary=True).workbook_path == tmp_path / "home" / "jobs.xlsx"

    def test_later_accounts_get_their_own_folder(self, tmp_path: Path) -> None:
        settings = Settings(home=tmp_path / "home")
        with Database(settings.database_path) as db:
            store = UserStore(db)
            store.create("ana", GOOD)
            ivo = store.create("ivo", "another-good-one")

        scoped = settings.for_user(ivo, primary=False)
        assert scoped.workbook_path == tmp_path / "home" / "users" / "2-ivo" / "jobs.xlsx"
        assert scoped.backup_path == tmp_path / "home" / "users" / "2-ivo" / "backups"

    def test_the_database_stays_shared(self, tmp_path: Path) -> None:
        """One file, every account in it. That is what makes an ad shared."""
        settings = Settings(home=tmp_path / "home")
        with Database(settings.database_path) as db:
            ivo = UserStore(db).create("ivo", GOOD)
        assert settings.for_user(ivo, primary=False).database_path == settings.database_path

    def test_a_chosen_workbook_wins_over_the_default(self, tmp_path: Path) -> None:
        settings = Settings(home=tmp_path / "home")
        with Database(settings.database_path) as db:
            store = UserStore(db)
            ivo = store.create("ivo", GOOD)
            store.set_workbook(ivo.id, str(tmp_path / "Desktop" / "poslovi.xlsx"))
            ivo = store.by_id(ivo.id)  # type: ignore[assignment]

        assert settings.for_user(ivo, primary=False).workbook_path == (
            tmp_path / "Desktop" / "poslovi.xlsx"
        )

    def test_the_folder_name_survives_a_name_no_filesystem_wants(
        self, tmp_path: Path
    ) -> None:
        with Database(tmp_path / "jobsheet.sqlite3") as db:
            user = UserStore(db).create("Željko.B", GOOD)
        assert user_folder(user) == f"{user.id}-zeljko.b"


# ------------------------------------------------------------------- upgrade


def _a_version_one_database(path: Path) -> None:
    """A real pre-accounts file: migration 1 only, with somebody's search in it."""
    connection = sqlite3.connect(path)
    connection.executescript(MIGRATIONS[0])
    connection.execute("PRAGMA user_version = 1")
    connection.execute(
        "INSERT INTO postings (dedup_key, source_id, title, url, first_seen, last_seen)"
        " VALUES ('example.test/j/1', 'rss', 'Surveyor', 'https://example.test/j/1',"
        " '2026-06-01', '2026-06-01')"
    )
    connection.execute(
        "INSERT INTO applications (dedup_key, status, found_at, updated_at)"
        " VALUES ('example.test/j/1', 'applied', '2026-06-01', '2026-06-01')"
    )
    connection.execute(
        "INSERT INTO application_events (dedup_key, at, from_status, to_status)"
        " VALUES ('example.test/j/1', '2026-06-02T09:00:00', 'new', 'applied')"
    )
    connection.execute(
        "INSERT INTO profiles (name, kind, payload, updated_at)"
        " VALUES ('mine', 'search', '{\"locations\": [\"Rijeka\"]}', '2026-06-01')"
    )
    connection.execute(
        "INSERT INTO runs (started_at, fetched, added) VALUES ('2026-06-01T09:00:00', 9, 1)"
    )
    connection.commit()
    connection.close()


class TestUpgradingAnOldInstall:
    def test_the_data_is_still_there_afterwards(self, tmp_path: Path) -> None:
        path = tmp_path / "jobsheet.sqlite3"
        _a_version_one_database(path)

        with Database(path) as db:
            assert db.version == len(MIGRATIONS)
            (row,) = db.all_rows()
            assert row.status is ApplicationStatus.APPLIED
            assert db.load_profile("mine", "search") == {"locations": ["Rijeka"]}
            assert len(db.runs()) == 1

    def test_it_is_held_by_an_account_waiting_to_be_claimed(self, tmp_path: Path) -> None:
        path = tmp_path / "jobsheet.sqlite3"
        _a_version_one_database(path)

        with Database(path) as db:
            waiting = UserStore(db).claimable()
            assert waiting is not None
            assert waiting.is_claimable
            assert not waiting.has_password

    def test_nobody_can_sign_into_it_before_claiming_it(self, tmp_path: Path) -> None:
        path = tmp_path / "jobsheet.sqlite3"
        _a_version_one_database(path)

        with Database(path) as db:
            store = UserStore(db)
            assert store.authenticate("local", "") is None
            assert store.authenticate("local", "anything") is None

    def test_claiming_it_hands_over_the_data(self, tmp_path: Path) -> None:
        path = tmp_path / "jobsheet.sqlite3"
        _a_version_one_database(path)

        with Database(path) as db:
            store = UserStore(db)
            waiting = store.claimable()
            assert waiting is not None
            ana = store.claim(waiting.id, "ana", GOOD)

            assert store.authenticate("ana", GOOD) is not None
            assert len(db.as_user(ana.id).all_rows()) == 1

    def test_an_account_can_only_be_claimed_once(self, tmp_path: Path) -> None:
        path = tmp_path / "jobsheet.sqlite3"
        _a_version_one_database(path)

        with Database(path) as db:
            store = UserStore(db)
            waiting = store.claimable()
            assert waiting is not None
            store.claim(waiting.id, "ana", GOOD)

            assert store.claimable() is None
            with pytest.raises(UserError, match="already has a password"):
                store.claim(waiting.id, "ivo", "another-good-one")

    def test_a_fresh_install_has_nothing_to_claim(self, tmp_path: Path) -> None:
        with Database(tmp_path / "jobsheet.sqlite3") as db:
            assert UserStore(db).count() == 0
            assert UserStore(db).claimable() is None

    def test_the_run_stamp_and_the_two_memories_arrive_on_a_file_with_data(
        self, tmp_path: Path
    ) -> None:
        """Migration 3 against a real old file, not an empty one.

        A migration that only ever runs on a fresh database is a migration that
        has not been tested. This one adds a column to a table that already has
        somebody's applications in it.
        """
        path = tmp_path / "jobsheet.sqlite3"
        _a_version_one_database(path)

        with Database(path) as db:
            # The row that predates the column is still there, and belongs to
            # no run -- which is the truth about it.
            (row,) = db.all_rows()
            assert db.count_rows() == 1
            assert db.count_rows(run="1") == 0

            # And both memories work on the upgraded file.
            db.remember_filtered([("example.test/j/9", "too_old")], profile_key="abc")
            assert db.filtered_out_keys("abc") == {"example.test/j/9"}
            assert db.delete_row(row.dedup_key)
            assert row.dedup_key in db.forgotten_keys()


# ----------------------------------------------------------------- endpoints


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(home=tmp_path / "home", open_browser=False)


@pytest.fixture
def api(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings), base_url=BASE_URL) as client:
        client.headers[TOKEN_HEADER] = settings.token
        yield client


def register(client: TestClient, username: str = "ana", password: str = GOOD) -> Any:
    return client.post("/api/auth/register", json={"username": username, "password": password})


class TestTheDoor:
    def test_a_fresh_install_reports_no_accounts(self, api: TestClient) -> None:
        body = api.get("/api/auth/status").json()
        assert body["accounts"] == 0
        assert body["claimable"] is None

    def test_the_door_says_where_jobsheet_can_look(self, api: TestClient) -> None:
        """The front page names the sources, and it does so before signing in.

        No exact count is asserted: half of this suite registers its own sources
        in-process, so the number here is whatever the run happens to hold. What
        must be true is that the door and the registry agree.
        """
        sources = api.get("/api/auth/status").json()["sources"]
        assert sources["count"] == len(registry.manifests())
        assert sources["names"] == [one.name for one in registry.manifests()]
        assert all(isinstance(name, str) and name for name in sources["names"])

    def test_registering_signs_you_in(self, api: TestClient) -> None:
        response = register(api)
        assert response.status_code == 201
        assert response.json()["username"] == "ana"
        assert api.cookies.get(SESSION_COOKIE)
        assert api.get("/api/auth/me").json()["username"] == "ana"

    def test_the_session_cookie_is_not_readable_by_a_script(self, api: TestClient) -> None:
        header = register(api).headers["set-cookie"].lower()
        assert "httponly" in header
        assert "samesite=strict" in header

    def test_a_new_account_has_not_been_through_the_wizard(self, api: TestClient) -> None:
        assert register(api).json()["onboarded"] is False

    def test_a_taken_name_is_a_conflict_with_a_code(self, api: TestClient) -> None:
        register(api)
        response = register(api, "ANA")
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "username_taken"

    def test_a_weak_password_is_refused_with_a_code(self, api: TestClient) -> None:
        response = register(api, "ivo", "short")
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "password_too_short"

    def test_signing_out_and_back_in(self, api: TestClient) -> None:
        register(api)
        assert api.post("/api/auth/logout").status_code == 200
        assert api.get("/api/auth/me").status_code == 401

        signed_in = api.post(
            "/api/auth/login", json={"username": "ana", "password": GOOD}
        )
        assert signed_in.status_code == 200
        assert api.get("/api/auth/me").json()["username"] == "ana"

    def test_a_wrong_password_says_nothing_useful(self, api: TestClient) -> None:
        register(api)
        api.post("/api/auth/logout")

        wrong = api.post("/api/auth/login", json={"username": "ana", "password": "nope-nope"})
        missing = api.post("/api/auth/login", json={"username": "ghost", "password": "nope-nope"})

        assert wrong.status_code == missing.status_code == 401
        assert wrong.json()["detail"]["code"] == missing.json()["detail"]["code"]
        assert wrong.json() == missing.json()

    def test_guessing_repeatedly_gets_you_locked_out(self, api: TestClient) -> None:
        register(api)
        api.post("/api/auth/logout")

        last = None
        for _ in range(12):
            last = api.post("/api/auth/login", json={"username": "ana", "password": "wrong-one"})
        assert last is not None
        assert last.status_code == 429
        assert last.json()["detail"]["code"] == "too_many_attempts"
        assert last.headers["retry-after"]

    def test_a_stale_session_cookie_is_not_a_way_in(self, api: TestClient) -> None:
        register(api)
        api.cookies.set(SESSION_COOKIE, "a-token-that-never-existed")
        assert api.get("/api/auth/me").status_code == 401

    def test_signing_out_twice_is_not_an_error(self, api: TestClient) -> None:
        register(api)
        assert api.post("/api/auth/logout").status_code == 200
        assert api.post("/api/auth/logout").status_code == 200


class TestClaimingThroughTheApi:
    @pytest.fixture
    def upgraded(self, tmp_path: Path) -> Iterator[TestClient]:
        settings = Settings(home=tmp_path / "home", open_browser=False)
        settings.prepare()
        _a_version_one_database(settings.database_path)
        with TestClient(create_app(settings), base_url=BASE_URL) as client:
            client.headers[TOKEN_HEADER] = settings.token
            yield client

    def test_the_status_screen_offers_the_waiting_data(self, upgraded: TestClient) -> None:
        body = upgraded.get("/api/auth/status").json()
        assert body["accounts"] == 1
        assert body["claimable"]["username"] == "local"

    def test_claiming_signs_you_in_and_hands_over_the_rows(self, upgraded: TestClient) -> None:
        response = upgraded.post("/api/auth/claim", json={"username": "ana", "password": GOOD})
        assert response.status_code == 200
        assert response.json()["username"] == "ana"

        rows = upgraded.get("/api/postings").json()
        assert rows["total"] == 1

    def test_the_claimed_account_keeps_the_original_workbook_path(
        self, upgraded: TestClient
    ) -> None:
        upgraded.post("/api/auth/claim", json={"username": "ana", "password": GOOD})
        me = upgraded.get("/api/auth/me").json()
        assert me["primary"] is True
        assert me["workbook_path"].endswith("jobs.xlsx")
        assert "users" not in Path(me["workbook_path"]).parts

    def test_there_is_nothing_to_claim_twice(self, upgraded: TestClient) -> None:
        upgraded.post("/api/auth/claim", json={"username": "ana", "password": GOOD})
        again = upgraded.post("/api/auth/claim", json={"username": "ivo", "password": GOOD})
        assert again.status_code == 409
        assert again.json()["detail"]["code"] == "nothing_to_claim"


class TestOnboarding:
    def test_the_wizard_marks_the_account_and_saves_the_setup(self, api: TestClient) -> None:
        register(api)
        response = api.post(
            "/api/auth/onboarding",
            json={
                "setup": {
                    "headline": "GIS analyst",
                    "profile": {
                        "keyword_groups": [{"name": "GIS", "terms": ["gis", "geodet"]}],
                        "locations": ["Rijeka"],
                        "max_age_days": 21,
                    },
                    "sources": [{"source_id": "remotive", "params": {"search": "gis"}}],
                }
            },
        )
        assert response.status_code == 200
        assert response.json()["onboarded"] is True

        saved = api.get("/api/profiles/setup/default").json()["payload"]
        assert saved["headline"] == "GIS analyst"
        assert saved["profile"]["max_age_days"] == 21
        assert saved["sources"][0]["source_id"] == "remotive"

    def test_the_wizard_can_put_the_workbook_where_the_user_looks(
        self, api: TestClient, tmp_path: Path
    ) -> None:
        register(api)
        wanted = tmp_path / "poslovi.xlsx"
        api.post("/api/auth/onboarding", json={"setup": {}, "workbook": str(wanted)})

        assert api.get("/api/auth/me").json()["workbook_path"] == str(wanted)
        assert api.get("/api/settings").json()["workbook"] == str(wanted)

    def test_a_workbook_in_a_folder_that_does_not_exist_is_refused(
        self, api: TestClient, tmp_path: Path
    ) -> None:
        register(api)
        response = api.post(
            "/api/auth/onboarding",
            json={"setup": {}, "workbook": str(tmp_path / "nope" / "jobs.xlsx")},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "workbook_folder_missing"
        assert api.get("/api/auth/me").json()["onboarded"] is False

    def test_a_workbook_that_is_not_a_spreadsheet_is_refused(self, api: TestClient) -> None:
        register(api)
        response = api.post("/api/auth/onboarding", json={"setup": {}, "workbook": "notes.txt"})
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "workbook_not_xlsx"

    def test_a_setup_that_does_not_load_back_is_refused(self, api: TestClient) -> None:
        register(api)
        response = api.post(
            "/api/auth/onboarding", json={"setup": {"profile": {"max_age_days": "soon"}}}
        )
        assert response.status_code == 422


class TestPasswordChange:
    def test_the_current_password_has_to_be_right(self, api: TestClient) -> None:
        register(api)
        response = api.post("/api/auth/password", json={"current": "wrong-one", "new": "x" * 12})
        assert response.status_code == 401

    def test_changing_it_signs_the_other_windows_out(self, api: TestClient) -> None:
        register(api)
        changed = api.post(
            "/api/auth/password", json={"current": GOOD, "new": "a-brand-new-password"}
        )
        assert changed.status_code == 200
        # This window included: the change closes every session, so the cookie
        # in hand is now worth nothing.
        assert api.get("/api/auth/me").status_code == 401
        again = api.post(
            "/api/auth/login", json={"username": "ana", "password": "a-brand-new-password"}
        )
        assert again.status_code == 200


class TestTwoAccountsThroughTheApi:
    def test_one_browser_signed_in_as_each_sees_two_different_searches(
        self, settings: Settings
    ) -> None:
        """The end-to-end version of the isolation tests, cookies and all."""
        app = create_app(settings)
        with (
            TestClient(app, base_url=BASE_URL) as ana,
            TestClient(app, base_url=BASE_URL) as ivo,
        ):
            ana.headers[TOKEN_HEADER] = settings.token
            ivo.headers[TOKEN_HEADER] = settings.token
            register(ana, "ana", GOOD)
            register(ivo, "ivo", "another-good-one")

            state = app.state.jobsheet
            store = UserStore(state.db)
            ana_id = store.by_username("ana").id  # type: ignore[union-attr]
            ivo_id = store.by_username("ivo").id  # type: ignore[union-attr]
            state.db.as_user(ana_id).save_rows([job(1), job(2)])
            state.db.as_user(ivo_id).save_row(job(3))

            assert ana.get("/api/postings").json()["total"] == 2
            assert ivo.get("/api/postings").json()["total"] == 1

    def test_a_search_started_by_one_is_invisible_to_the_other(
        self, settings: Settings
    ) -> None:
        app = create_app(settings)
        with (
            TestClient(app, base_url=BASE_URL) as ana,
            TestClient(app, base_url=BASE_URL) as ivo,
        ):
            ana.headers[TOKEN_HEADER] = settings.token
            ivo.headers[TOKEN_HEADER] = settings.token
            register(ana, "ana", GOOD)
            register(ivo, "ivo", "another-good-one")

            started = ana.post("/api/search", json={"sources": [{"source_id": "rss"}]})
            run_id = started.json()["id"]

            assert ivo.get(f"/api/search/{run_id}").status_code == 404
            assert ivo.get("/api/search").json() == []
            assert ana.get(f"/api/search/{run_id}").status_code == 200
