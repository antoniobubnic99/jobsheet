"""Local SQLite storage.

The database is the memory; the spreadsheet is the view the user works in. That
split is deliberate. A workbook is easy to reason about and easy to edit, but it
cannot hold a history, and a user who deletes a row should not thereby lose the
record that they applied for that job in June.

Everything lives in one file, next to the workbook. Since accounts arrived that
one file can hold several job searches at once, and the split between them is
deliberate: an ad is an ad whoever found it, so `postings` is shared, while
everything a person knows or decides about an ad -- status, notes, saved
searches, run history -- is theirs alone. Every query below that touches those
tables states whose rows it means, because the failure mode of forgetting is not
an error, it is one person quietly reading another's job search.

Migrations are a plain list, applied in order, tracked by SQLite's own
`user_version`. That is enough for a single-file local database and avoids a
dependency whose whole job would be to manage four tables.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any

from jobsheet.core.models import ApplicationStatus, Posting, Workplace
from jobsheet.sheet.row import JobRow

__all__ = ["MIGRATIONS", "SOLO_USERNAME", "Database"]

# The account that owns everything on an install nobody has signed into: the
# rows the command line writes, and whatever predates accounts entirely. It
# carries no password, so it cannot be logged into -- only claimed.
SOLO_USERNAME = "local"

MIGRATIONS: list[str] = [
    # 1 -- the ads themselves, keyed by the same normalised URL used everywhere
    # else, so the spreadsheet and the database always agree on identity.
    """
    CREATE TABLE postings (
        dedup_key       TEXT PRIMARY KEY,
        source_id       TEXT NOT NULL,
        title           TEXT NOT NULL,
        url             TEXT NOT NULL,
        company         TEXT NOT NULL DEFAULT '',
        location        TEXT NOT NULL DEFAULT '',
        region          TEXT NOT NULL DEFAULT '',
        workplace       TEXT NOT NULL DEFAULT 'unknown',
        description     TEXT NOT NULL DEFAULT '',
        employment_type TEXT NOT NULL DEFAULT '',
        education       TEXT NOT NULL DEFAULT '',
        salary          TEXT NOT NULL DEFAULT '',
        posted_at       TEXT,
        deadline        TEXT,
        tags            TEXT NOT NULL DEFAULT '[]',
        raw             TEXT NOT NULL DEFAULT '{}',
        first_seen      TEXT NOT NULL,
        last_seen       TEXT NOT NULL
    );
    CREATE INDEX idx_postings_company ON postings(company);
    CREATE INDEX idx_postings_posted ON postings(posted_at);

    -- What the user knows. Separated from the ad so that re-fetching an ad can
    -- never touch it.
    CREATE TABLE applications (
        dedup_key   TEXT PRIMARY KEY REFERENCES postings(dedup_key) ON DELETE CASCADE,
        status      TEXT NOT NULL DEFAULT 'new',
        category    TEXT NOT NULL DEFAULT '',
        note        TEXT NOT NULL DEFAULT '',
        user_values TEXT NOT NULL DEFAULT '{}',
        link_text   TEXT NOT NULL DEFAULT '',
        found_at    TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    );
    CREATE INDEX idx_applications_status ON applications(status);

    CREATE TABLE application_events (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        dedup_key   TEXT NOT NULL REFERENCES postings(dedup_key) ON DELETE CASCADE,
        at          TEXT NOT NULL,
        from_status TEXT NOT NULL,
        to_status   TEXT NOT NULL,
        note        TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX idx_events_key ON application_events(dedup_key, at);

    CREATE TABLE runs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at  TEXT NOT NULL,
        finished_at TEXT,
        fetched     INTEGER NOT NULL DEFAULT 0,
        added       INTEGER NOT NULL DEFAULT 0,
        duplicates  INTEGER NOT NULL DEFAULT 0,
        rejected    INTEGER NOT NULL DEFAULT 0,
        errors      TEXT NOT NULL DEFAULT '{}'
    );

    -- Saved searches and saved sheet designs, both just named JSON.
    CREATE TABLE profiles (
        name       TEXT NOT NULL,
        kind       TEXT NOT NULL,
        payload    TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (name, kind)
    );

    -- Whether each source last worked. Third-party endpoints change without
    -- notice, and a user deserves to be told which one went quiet rather than
    -- silently getting fewer results.
    CREATE TABLE source_health (
        source_id  TEXT PRIMARY KEY,
        last_ok    TEXT,
        last_error TEXT,
        last_count INTEGER NOT NULL DEFAULT 0,
        message    TEXT NOT NULL DEFAULT ''
    );
    """,
    # 2 -- accounts. One install can now hold several job searches that never
    # see each other. The split is deliberate: an ad is an ad whoever found it,
    # so `postings` stays shared, while everything a person knows or decides
    # about an ad belongs to them and gains a `user_id`.
    """
    CREATE TABLE users (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        username        TEXT NOT NULL,
        -- Case-folded, and the unique one: nobody should be able to register
        -- "Ana" against an existing "ana" and then wonder whose data they see.
        username_folded TEXT NOT NULL UNIQUE,
        password_hash   TEXT NOT NULL,
        workbook        TEXT,
        created_at      TEXT NOT NULL,
        last_seen_at    TEXT,
        onboarded_at    TEXT
    );

    CREATE TABLE sessions (
        -- The hash, never the token. A stolen database should not hand over
        -- live sessions as well as everything else.
        token_hash TEXT PRIMARY KEY,
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    );
    CREATE INDEX idx_sessions_user ON sessions(user_id);

    -- Anything already here belongs to whoever has been using this install.
    -- It is handed to a placeholder account with no password, which the
    -- interface offers to claim on first launch, so upgrading never looks
    -- like data loss. A fresh database gets no such account.
    INSERT INTO users (id, username, username_folded, password_hash, created_at)
    SELECT 1, 'local', 'local', '', strftime('%Y-%m-%dT%H:%M:%S', 'now')
    WHERE EXISTS (SELECT 1 FROM applications)
       OR EXISTS (SELECT 1 FROM profiles)
       OR EXISTS (SELECT 1 FROM runs);

    -- `applications` and `profiles` change primary key, which SQLite can only
    -- do by rebuilding the table. The other two merely gain a column.
    CREATE TABLE applications_v2 (
        user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        dedup_key   TEXT NOT NULL REFERENCES postings(dedup_key) ON DELETE CASCADE,
        status      TEXT NOT NULL DEFAULT 'new',
        category    TEXT NOT NULL DEFAULT '',
        note        TEXT NOT NULL DEFAULT '',
        user_values TEXT NOT NULL DEFAULT '{}',
        link_text   TEXT NOT NULL DEFAULT '',
        found_at    TEXT NOT NULL,
        updated_at  TEXT NOT NULL,
        PRIMARY KEY (user_id, dedup_key)
    );
    INSERT INTO applications_v2 (user_id, dedup_key, status, category, note,
                                 user_values, link_text, found_at, updated_at)
    SELECT 1, dedup_key, status, category, note, user_values, link_text,
           found_at, updated_at
    FROM applications;
    DROP TABLE applications;
    ALTER TABLE applications_v2 RENAME TO applications;
    CREATE INDEX idx_applications_status ON applications(user_id, status);

    CREATE TABLE profiles_v2 (
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name       TEXT NOT NULL,
        kind       TEXT NOT NULL,
        payload    TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (user_id, name, kind)
    );
    INSERT INTO profiles_v2 (user_id, name, kind, payload, updated_at)
    SELECT 1, name, kind, payload, updated_at FROM profiles;
    DROP TABLE profiles;
    ALTER TABLE profiles_v2 RENAME TO profiles;

    ALTER TABLE application_events ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1;
    CREATE INDEX idx_events_user ON application_events(user_id, dedup_key, at);

    ALTER TABLE runs ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1;
    CREATE INDEX idx_runs_user ON runs(user_id, id);
    """,
]


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _as_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


class Database:
    """A single local SQLite file."""

    def __init__(self, path: Path | str, *, user_id: int | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        # The interface reads while a search writes; WAL is what makes that
        # comfortable without a lock dance.
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._user_id = user_id
        self._owns_connection = True
        self.migrate()

    def close(self) -> None:
        if self._owns_connection:
            self._connection.close()

    # ------------------------------------------------------------------ scope

    @property
    def user_id(self) -> int:
        """Whose rows this handle reads and writes.

        The interface always says so outright, because it serves several people.
        The command line and the tests usually do not, and for them the answer is
        worked out once, lazily: the only account on the install, or a
        placeholder created on the spot. That placeholder has no password, which
        the interface reads as "there is data here, claim it" rather than as an
        account somebody could sign into.
        """
        if self._user_id is None:
            self._user_id = self._solo_user()
        return self._user_id

    def as_user(self, user_id: int) -> Database:
        """A second handle on the same open file, reading another account's rows.

        The connection is shared rather than reopened. SQLite would give us a
        second one happily, but then two handles serving one request could sit on
        opposite sides of a transaction and disagree about what exists.
        """
        view = object.__new__(Database)
        view.path = self.path
        view._connection = self._connection
        view._user_id = user_id
        view._owns_connection = False
        return view

    def _solo_user(self) -> int:
        rows = self._connection.execute("SELECT id FROM users ORDER BY id LIMIT 2").fetchall()
        if len(rows) == 1:
            return int(rows[0][0])
        if len(rows) > 1:
            raise LookupError(
                "This JobSheet has more than one account, so a database handle cannot "
                "guess which one it means. Say so with `user_id=`, or `--user` on the "
                "command line."
            )
        with self.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO users (username, username_folded, password_hash, created_at)
                VALUES (?, ?, '', ?)
                """,
                (SOLO_USERNAME, SOLO_USERNAME, datetime.now().isoformat(timespec="seconds")),
            )
        return int(cursor.lastrowid or 0)

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------- migrations

    @property
    def version(self) -> int:
        return int(self._connection.execute("PRAGMA user_version").fetchone()[0])

    def migrate(self) -> int:
        """Apply any migrations this file has not seen. Safe to call repeatedly."""
        applied = self.version
        for number, script in enumerate(MIGRATIONS[applied:], start=applied + 1):
            with self._connection:
                self._connection.executescript(script)
                self._connection.execute(f"PRAGMA user_version = {number}")
        return self.version

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._connection:
            yield self._connection

    # ---------------------------------------------------------------- writing

    def upsert_posting(self, posting: Posting, *, seen_on: date) -> None:
        """Record an ad. Re-seeing one refreshes its fields but never its history."""
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO postings (
                    dedup_key, source_id, title, url, company, location, region,
                    workplace, description, employment_type, education, salary,
                    posted_at, deadline, tags, raw, first_seen, last_seen
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(dedup_key) DO UPDATE SET
                    title = excluded.title,
                    company = excluded.company,
                    location = excluded.location,
                    region = excluded.region,
                    workplace = excluded.workplace,
                    description = excluded.description,
                    employment_type = excluded.employment_type,
                    education = excluded.education,
                    salary = excluded.salary,
                    posted_at = COALESCE(excluded.posted_at, postings.posted_at),
                    deadline = COALESCE(excluded.deadline, postings.deadline),
                    tags = excluded.tags,
                    last_seen = excluded.last_seen
                """,
                (
                    posting.dedup_key,
                    posting.source_id,
                    posting.title,
                    posting.url,
                    posting.company,
                    posting.location,
                    posting.region,
                    str(posting.workplace),
                    posting.description,
                    posting.employment_type,
                    posting.education,
                    posting.salary,
                    _iso(posting.posted_at),
                    _iso(posting.deadline),
                    json.dumps(list(posting.tags)),
                    json.dumps(posting.raw, default=str),
                    seen_on.isoformat(),
                    seen_on.isoformat(),
                ),
            )

    def save_row(self, row: JobRow) -> None:
        """Store an ad together with what the user knows about it."""
        self.upsert_posting(row.posting, seen_on=row.found_at)
        now = datetime.now().isoformat(timespec="seconds")
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO applications (
                    user_id, dedup_key, status, category, note, user_values,
                    link_text, found_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(user_id, dedup_key) DO UPDATE SET
                    -- The app refreshes what it derived; it never touches status
                    -- or the user's own columns.
                    category = excluded.category,
                    note = excluded.note,
                    updated_at = excluded.updated_at
                """,
                (
                    self.user_id,
                    row.dedup_key,
                    str(row.status),
                    row.category,
                    row.note,
                    json.dumps(row.user_values, default=str),
                    row.link_text,
                    row.found_at.isoformat(),
                    now,
                ),
            )

    def save_rows(self, rows: list[JobRow]) -> int:
        for row in rows:
            self.save_row(row)
        return len(rows)

    def record_run(
        self,
        *,
        fetched: int,
        added: int,
        duplicates: int,
        rejected: int,
        errors: dict[str, str],
        started_at: datetime,
    ) -> int:
        with self.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO runs (user_id, started_at, finished_at, fetched,
                                  added, duplicates, rejected, errors)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    self.user_id,
                    started_at.isoformat(timespec="seconds"),
                    datetime.now().isoformat(timespec="seconds"),
                    fetched,
                    added,
                    duplicates,
                    rejected,
                    json.dumps(errors),
                ),
            )
        return int(cursor.lastrowid or 0)

    def record_source_health(
        self, source_id: str, *, ok: bool, count: int = 0, message: str = ""
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO source_health (source_id, last_ok, last_error, last_count, message)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    last_ok = CASE WHEN ? THEN ? ELSE source_health.last_ok END,
                    last_error = CASE WHEN ? THEN source_health.last_error ELSE ? END,
                    last_count = ?,
                    message = ?
                """,
                (
                    source_id,
                    now if ok else None,
                    None if ok else now,
                    count,
                    message,
                    ok,
                    now,
                    ok,
                    now,
                    count,
                    message,
                ),
            )

    # ---------------------------------------------------------------- reading

    def all_rows(self) -> list[JobRow]:
        cursor = self._connection.execute(
            """
            SELECT p.*, a.status, a.category, a.note, a.user_values, a.link_text, a.found_at
            FROM postings p
            JOIN applications a ON a.dedup_key = p.dedup_key
            WHERE a.user_id = ?
            ORDER BY a.found_at DESC, p.company
            """,
            (self.user_id,),
        )
        return [_row_from_record(record) for record in cursor.fetchall()]

    # The interface asks for a page of rows at a time, filtered by whatever the
    # user typed. Doing that in SQL rather than in Python keeps a search over a
    # few thousand ads instant and, more usefully, keeps the paging honest --
    # `total` counts what matches, not what happened to be loaded.
    def _filter(
        self, status: str | None, query: str, source: str | None
    ) -> tuple[str, list[Any]]:
        # The account comes first and is never optional. A missing `user_id`
        # here would not raise, it would show one person another person's search.
        clauses: list[str] = ["a.user_id = ?"]
        values: list[Any] = [self.user_id]
        if status:
            clauses.append("a.status = ?")
            values.append(status)
        if source:
            clauses.append("p.source_id LIKE ?")
            values.append(f"{source}%")
        if query:
            # LIKE is case-insensitive for ASCII in SQLite but not beyond it, so
            # both sides are folded first. Diacritics are left alone here; the
            # matching module owns that, and doing it twice differently would be
            # worse than not doing it.
            like = f"%{query.casefold()}%"
            clauses.append(
                "(LOWER(p.title) LIKE ? OR LOWER(p.company) LIKE ?"
                " OR LOWER(p.location) LIKE ? OR LOWER(a.note) LIKE ?"
                " OR LOWER(p.tags) LIKE ?)"
            )
            values.extend([like] * 5)
        return f" WHERE {' AND '.join(clauses)}", values

    def rows(
        self,
        *,
        status: str | None = None,
        query: str = "",
        source: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[JobRow]:
        """A page of tracked jobs, newest first."""
        where, values = self._filter(status, query, source)
        # The interpolation below is safe, and safe for a reason worth stating:
        # `_filter` builds `where` out of string literals only. Every value the
        # user supplied travels separately in `values`, as a bound parameter.
        sql = (
            "SELECT p.*, a.status, a.category, a.note, a.user_values, a.link_text,"  # noqa: S608
            " a.found_at FROM postings p JOIN applications a ON a.dedup_key = p.dedup_key"
            f"{where} ORDER BY a.found_at DESC, p.company"
        )
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            values.extend([limit, offset])
        cursor = self._connection.execute(sql, values)
        return [_row_from_record(record) for record in cursor.fetchall()]

    def count_rows(
        self, *, status: str | None = None, query: str = "", source: str | None = None
    ) -> int:
        where, values = self._filter(status, query, source)
        cursor = self._connection.execute(
            "SELECT COUNT(*) FROM postings p JOIN applications a"  # noqa: S608
            f" ON a.dedup_key = p.dedup_key{where}",
            values,
        )
        return int(cursor.fetchone()[0])

    def row(self, dedup_key: str) -> JobRow | None:
        """One tracked job, or `None` if it is not tracked."""
        cursor = self._connection.execute(
            "SELECT p.*, a.status, a.category, a.note, a.user_values, a.link_text,"
            " a.found_at FROM postings p JOIN applications a ON a.dedup_key = p.dedup_key"
            " WHERE a.user_id = ? AND p.dedup_key = ?",
            (self.user_id, dedup_key),
        )
        record = cursor.fetchone()
        return _row_from_record(record) if record else None

    def delete_row(self, dedup_key: str) -> bool:
        """Forget a job entirely, history included. Only the user asks for this.

        The ad itself only goes when the last account tracking it lets go.
        Deleting it outright would reach into somebody else's spreadsheet.
        """
        with self.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM applications WHERE user_id = ? AND dedup_key = ?",
                (self.user_id, dedup_key),
            )
            connection.execute(
                "DELETE FROM application_events WHERE user_id = ? AND dedup_key = ?",
                (self.user_id, dedup_key),
            )
            connection.execute(
                "DELETE FROM postings WHERE dedup_key = ?"
                " AND NOT EXISTS (SELECT 1 FROM applications WHERE dedup_key = ?)",
                (dedup_key, dedup_key),
            )
        return cursor.rowcount > 0

    def known_keys(self) -> set[str]:
        """The ads this account already tracks -- not every ad on the install."""
        cursor = self._connection.execute(
            "SELECT dedup_key FROM applications WHERE user_id = ?", (self.user_id,)
        )
        return {record[0] for record in cursor.fetchall()}

    def source_health(self) -> list[dict[str, Any]]:
        cursor = self._connection.execute("SELECT * FROM source_health ORDER BY source_id")
        return [dict(record) for record in cursor.fetchall()]

    def runs(self, limit: int = 20) -> list[dict[str, Any]]:
        cursor = self._connection.execute(
            "SELECT * FROM runs WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (self.user_id, limit),
        )
        return [dict(record) for record in cursor.fetchall()]

    # --------------------------------------------------------------- profiles

    def save_profile(self, name: str, kind: str, payload: dict[str, Any]) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO profiles (user_id, name, kind, payload, updated_at)
                VALUES (?,?,?,?,?)
                ON CONFLICT(user_id, name, kind) DO UPDATE SET
                    payload = excluded.payload, updated_at = excluded.updated_at
                """,
                (
                    self.user_id,
                    name,
                    kind,
                    json.dumps(payload, default=str),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )

    def load_profile(self, name: str, kind: str) -> dict[str, Any] | None:
        cursor = self._connection.execute(
            "SELECT payload FROM profiles WHERE user_id = ? AND name = ? AND kind = ?",
            (self.user_id, name, kind),
        )
        record = cursor.fetchone()
        return json.loads(record[0]) if record else None

    def list_profiles(self, kind: str) -> list[str]:
        cursor = self._connection.execute(
            "SELECT name FROM profiles WHERE user_id = ? AND kind = ? ORDER BY name",
            (self.user_id, kind),
        )
        return [record[0] for record in cursor.fetchall()]

    def delete_profile(self, name: str, kind: str) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM profiles WHERE user_id = ? AND name = ? AND kind = ?",
                (self.user_id, name, kind),
            )
        return cursor.rowcount > 0


def _row_from_record(record: sqlite3.Row) -> JobRow:
    return JobRow(
        posting=Posting(
            source_id=record["source_id"],
            title=record["title"],
            url=record["url"],
            company=record["company"],
            location=record["location"],
            region=record["region"],
            workplace=Workplace(record["workplace"]),
            description=record["description"],
            employment_type=record["employment_type"],
            education=record["education"],
            salary=record["salary"],
            posted_at=_as_date(record["posted_at"]),
            deadline=_as_date(record["deadline"]),
            tags=tuple(json.loads(record["tags"] or "[]")),
            raw=json.loads(record["raw"] or "{}"),
        ),
        found_at=_as_date(record["found_at"]) or date.today(),
        category=record["category"],
        note=record["note"],
        status=ApplicationStatus(record["status"]),
        user_values=json.loads(record["user_values"] or "{}"),
        link_text=record["link_text"],
    )
