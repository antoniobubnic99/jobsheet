"""Accounts: who uses this JobSheet, and how they prove it.

JobSheet listens on the loopback address and nothing else, so this is not a
login that keeps the internet out -- the network already does that. It keeps
*people* apart. One install can hold several job searches that never see each
other, which is the difference between a household sharing a laptop and a
household sharing a spreadsheet.

Two things follow from that, and both are worth being plain about:

* **A password here is not encryption.** Anyone with a shell on this machine can
  open the SQLite file directly, and the command line does exactly that. What
  the password protects is the browser interface, and therefore everything a web
  page in another tab could otherwise reach.
* **The predecessor's data is not orphaned.** An install that already had a
  search in it gets a placeholder account holding all of it, with no password.
  It cannot be signed into -- it can only be *claimed*, once, by whoever is at
  the keyboard on the next launch. Upgrading must never look like data loss.

Passwords are stored as scrypt hashes, salted per user, with the parameters
written into the record so they can be raised later without stranding anybody.
Session tokens are stored as SHA-256 digests: a database that leaks should not
also hand over live sessions.
"""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict

from jobsheet.core.matching import fold
from jobsheet.store.db import Database

__all__ = [
    "PASSWORD_MIN",
    "SESSION_DAYS",
    "LoginThrottle",
    "User",
    "UserError",
    "UserStore",
    "check_password",
    "hash_password",
    "normalise_username",
    "verify_password",
]

PASSWORD_MIN = 8
PASSWORD_MAX = 200  # scrypt happily hashes a megabyte; there is no reason to let it.
USERNAME_MIN = 3
USERNAME_MAX = 32
SESSION_DAYS = 30

# A letter or digit, then letters, digits, dots, hyphens or underscores. Unicode
# throughout: an app whose interface ships in Croatian should not tell someone
# their own name is not a valid username.
_USERNAME_OK = re.compile(rf"^[^\W_][\w.\-]{{{USERNAME_MIN - 1},{USERNAME_MAX - 1}}}$")

# scrypt at these parameters needs 128 * N * r = 16 MiB and about a tenth of a
# second. That is the point: it is the same tenth of a second for the person
# logging in and for anyone working through a password list.
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
SCRYPT_MAXMEM = 64 * 1024 * 1024


class UserError(ValueError):
    """Something the person at the keyboard can fix, with a code the interface knows."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class User(BaseModel):
    """One account. Never carries the password hash -- not even out to the API."""

    model_config = ConfigDict(extra="forbid")

    id: int
    username: str
    workbook: str | None = None
    created_at: datetime
    last_seen_at: datetime | None = None
    onboarded_at: datetime | None = None
    has_password: bool = True

    @property
    def is_onboarded(self) -> bool:
        return self.onboarded_at is not None

    @property
    def is_claimable(self) -> bool:
        """A passwordless account: data waiting for somebody to take ownership."""
        return not self.has_password


# ----------------------------------------------------------------- passwords


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str) -> str:
    """`scrypt$n$r$p$salt$hash`, with the cost written in so it can be raised."""
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
        maxmem=SCRYPT_MAXMEM,
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(derived)}"


def verify_password(password: str, stored: str) -> bool:
    """Whether `password` produced `stored`. Anything unparseable is a no."""
    if not stored:
        # A claimable account. There is no password, so nothing can match one --
        # returning False here is what stops `claim` becoming a way in.
        return False
    try:
        scheme, n, r, p, salt, expected = stored.split("$")
        if scheme != "scrypt":
            return False
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_unb64(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(_unb64(expected)),
            maxmem=SCRYPT_MAXMEM,
        )
    except (ValueError, TypeError):
        return False
    return secrets.compare_digest(derived, _unb64(expected))


def check_password(password: str, *, username: str = "") -> str:
    """Return the password, or say what is wrong with it."""
    if len(password) < PASSWORD_MIN:
        raise UserError(
            "password_too_short",
            f"A password needs at least {PASSWORD_MIN} characters.",
        )
    if len(password) > PASSWORD_MAX:
        raise UserError(
            "password_too_long", f"A password can be at most {PASSWORD_MAX} characters."
        )
    if username and fold(password) == fold(username):
        raise UserError(
            "password_is_username", "A password cannot be the same as the username."
        )
    return password


def normalise_username(username: str) -> tuple[str, str]:
    """Return the name as typed and the folded form uniqueness is judged on.

    Folding is the same one the matching module uses on job ads, so "Željko" and
    "zeljko" are one account rather than two. That costs a Croatian speaker the
    ability to have both, and buys everybody the certainty that the name on the
    screen is the account they think it is.
    """
    display = unicodedata.normalize("NFKC", username).strip()
    if not _USERNAME_OK.match(display):
        raise UserError(
            "username_invalid",
            f"A username is {USERNAME_MIN}-{USERNAME_MAX} characters: letters or digits "
            "to start, then letters, digits, dots, hyphens or underscores.",
        )
    return display, fold(display)


# ------------------------------------------------------------------ sessions


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def _at(value: Any) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


# --------------------------------------------------------------- the throttle


@dataclass
class _Attempts:
    count: int = 0
    locked_until: datetime | None = None


@dataclass
class LoginThrottle:
    """Slows down guessing, per username, in memory.

    In memory on purpose: a lockout that survived a restart would let a mistyped
    password lock somebody out of their own laptop until a file was edited by
    hand. Restarting JobSheet is not an attack, it is Tuesday.
    """

    allowance: int = 8
    first_penalty: timedelta = timedelta(seconds=30)
    max_penalty: timedelta = timedelta(minutes=15)
    _by_name: dict[str, _Attempts] = field(default_factory=dict, repr=False)

    def locked_for(self, folded_username: str, *, now: datetime | None = None) -> int:
        """Seconds still to wait, or zero."""
        record = self._by_name.get(folded_username)
        if record is None or record.locked_until is None:
            return 0
        remaining = (record.locked_until - (now or datetime.now())).total_seconds()
        return max(0, int(remaining + 0.999))

    def failed(self, folded_username: str, *, now: datetime | None = None) -> None:
        now = now or datetime.now()
        record = self._by_name.setdefault(folded_username, _Attempts())
        record.count += 1
        if record.count >= self.allowance:
            over = record.count - self.allowance
            penalty = min(self.first_penalty * (2**over), self.max_penalty)
            record.locked_until = now + penalty

    def succeeded(self, folded_username: str) -> None:
        self._by_name.pop(folded_username, None)


# ------------------------------------------------------------------ the store


class UserStore:
    """Accounts and sessions. The one part of the database that is not per-user."""

    def __init__(self, database: Database) -> None:
        self.db = database

    # -------------------------------------------------------------- reading

    def count(self) -> int:
        cursor = self.db._connection.execute("SELECT COUNT(*) FROM users")
        return int(cursor.fetchone()[0])

    def all(self) -> list[User]:
        cursor = self.db._connection.execute("SELECT * FROM users ORDER BY id")
        return [_user_from(record) for record in cursor.fetchall()]

    def by_id(self, user_id: int) -> User | None:
        cursor = self.db._connection.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        record = cursor.fetchone()
        return _user_from(record) if record else None

    def by_username(self, username: str) -> User | None:
        cursor = self.db._connection.execute(
            "SELECT * FROM users WHERE username_folded = ?", (fold(username),)
        )
        record = cursor.fetchone()
        return _user_from(record) if record else None

    def claimable(self) -> User | None:
        """The passwordless account, if this install has one waiting."""
        cursor = self.db._connection.execute(
            "SELECT * FROM users WHERE password_hash = '' ORDER BY id LIMIT 1"
        )
        record = cursor.fetchone()
        return _user_from(record) if record else None

    # -------------------------------------------------------------- writing

    def create(self, username: str, password: str) -> User:
        """Register a new account. The name has to be free."""
        display, folded = normalise_username(username)
        check_password(password, username=display)
        if self.by_username(folded) is not None:
            raise UserError("username_taken", f"The name {display!r} is already in use here.")

        with self.db.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO users (username, username_folded, password_hash, created_at)
                VALUES (?,?,?,?)
                """,
                (display, folded, hash_password(password), _iso(datetime.now())),
            )
        created = self.by_id(int(cursor.lastrowid or 0))
        assert created is not None
        return created

    def claim(self, user_id: int, username: str, password: str) -> User:
        """Put a name and a password on an account that has neither.

        This is the upgrade path, and the only way into the data an install had
        before accounts existed. It works exactly once per account: afterwards
        there is a password, and `claim` refuses.
        """
        existing = self.by_id(user_id)
        if existing is None:
            raise UserError("no_such_user", "That account no longer exists.")
        if not existing.is_claimable:
            raise UserError("already_claimed", "That account already has a password.")

        display, folded = normalise_username(username)
        check_password(password, username=display)
        clash = self.by_username(folded)
        if clash is not None and clash.id != user_id:
            raise UserError("username_taken", f"The name {display!r} is already in use here.")

        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE users SET username = ?, username_folded = ?, password_hash = ?"
                " WHERE id = ?",
                (display, folded, hash_password(password), user_id),
            )
        claimed = self.by_id(user_id)
        assert claimed is not None
        return claimed

    def authenticate(self, username: str, password: str) -> User | None:
        """The account, or `None`. Says nothing about which half was wrong."""
        cursor = self.db._connection.execute(
            "SELECT * FROM users WHERE username_folded = ?", (fold(username),)
        )
        record = cursor.fetchone()
        if record is None:
            # Hash anyway. Returning early here would answer "does this name
            # exist?" in a few microseconds, which is an answer worth hiding.
            hash_password(password)
            return None
        if not verify_password(password, record["password_hash"]):
            return None
        return _user_from(record)

    def set_password(self, user_id: int, password: str) -> None:
        user = self.by_id(user_id)
        if user is None:
            raise UserError("no_such_user", "That account no longer exists.")
        check_password(password, username=user.username)
        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (hash_password(password), user_id),
            )

    def touch(self, user_id: int) -> None:
        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE users SET last_seen_at = ? WHERE id = ?",
                (_iso(datetime.now()), user_id),
            )

    def mark_onboarded(self, user_id: int) -> None:
        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE users SET onboarded_at = ? WHERE id = ?",
                (_iso(datetime.now()), user_id),
            )

    def set_workbook(self, user_id: int, workbook: str | None) -> None:
        with self.db.transaction() as connection:
            connection.execute(
                "UPDATE users SET workbook = ? WHERE id = ?", (workbook or None, user_id)
            )

    # -------------------------------------------------------------- sessions

    def open_session(self, user_id: int, *, days: int = SESSION_DAYS) -> str:
        """Mint a session token. Only its digest is kept."""
        token = secrets.token_urlsafe(32)
        now = datetime.now()
        with self.db.transaction() as connection:
            connection.execute(
                "INSERT INTO sessions (token_hash, user_id, created_at, expires_at)"
                " VALUES (?,?,?,?)",
                (_digest(token), user_id, _iso(now), _iso(now + timedelta(days=days))),
            )
        return token

    def resolve(self, token: str) -> User | None:
        """Whose session this is, if it is a live one."""
        if not token:
            return None
        cursor = self.db._connection.execute(
            "SELECT user_id, expires_at FROM sessions WHERE token_hash = ?", (_digest(token),)
        )
        record = cursor.fetchone()
        if record is None:
            return None
        if datetime.fromisoformat(record["expires_at"]) <= datetime.now():
            self.close_session(token)
            return None
        return self.by_id(int(record["user_id"]))

    def close_session(self, token: str) -> bool:
        with self.db.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM sessions WHERE token_hash = ?", (_digest(token),)
            )
        return cursor.rowcount > 0

    def close_all(self, user_id: int) -> int:
        """Sign an account out everywhere -- what a password change should do."""
        with self.db.transaction() as connection:
            cursor = connection.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        return cursor.rowcount

    def purge_expired(self) -> int:
        with self.db.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM sessions WHERE expires_at <= ?", (_iso(datetime.now()),)
            )
        return cursor.rowcount


def _user_from(record: Any) -> User:
    return User(
        id=int(record["id"]),
        username=record["username"],
        workbook=record["workbook"],
        created_at=datetime.fromisoformat(record["created_at"]),
        last_seen_at=_at(record["last_seen_at"]),
        onboarded_at=_at(record["onboarded_at"]),
        has_password=bool(record["password_hash"]),
    )
