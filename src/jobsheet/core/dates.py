"""Date parsing for whatever a source decides to send.

Job boards are a museum of date formats. This module holds one tolerant entry
point, `parse_date`, plus the two formats that needed their own handling because
getting them wrong shifts dates by a day or silently drops ads.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime

__all__ = ["days_ago", "parse_date", "parse_dotnet_date"]

# Formats tried in order. Day-first before month-first: European boards write
# 05.06.2026 meaning 5 June, and there is no way to tell from the value alone.
_FORMATS = (
    "%Y-%m-%d",
    "%d.%m.%Y",
    "%d.%m.%Y.",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y/%m/%d",
    "%d.%m.%y",
    "%Y%m%d",
)

# .NET's JSON date: /Date(<milliseconds since epoch><+|-><hhmm>)/
#
# The offset is not decoration. Croatian government endpoints emit midnight local
# time as an epoch that lands on the previous day in UTC, so ignoring the offset
# moves every publication date back by one -- enough to push an ad outside a
# "last 30 days" window on its first day.
_DOTNET = re.compile(r"/Date\((-?\d+)(?:([+-])(\d{2})(\d{2}))?\)/")

_ISO_LIKE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")

_RFC822_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def parse_dotnet_date(value: str) -> date | None:
    """Parse `/Date(1755036000000+0200)/` into a local calendar date."""
    match = _DOTNET.search(value)
    if not match:
        return None
    millis = int(match.group(1))
    moment = datetime.fromtimestamp(millis / 1000, tz=UTC)
    if match.group(2):
        sign = 1 if match.group(2) == "+" else -1
        offset = timedelta(hours=int(match.group(3)), minutes=int(match.group(4)))
        moment += sign * offset
    return moment.date()


def parse_date(value: object) -> date | None:
    """Best-effort conversion of anything date-shaped into a `date`.

    Returns `None` rather than raising: a missing or unparseable date must never
    take down a whole fetch, and downstream filters already treat `None` as
    "unknown, judge by other means".
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None

    if "/Date(" in text:
        return parse_dotnet_date(text)

    # RFC 822/2822, as used by every RSS <pubDate>.
    if "," in text and text[:3] in _RFC822_DAYS:
        try:
            return parsedate_to_datetime(text).date()
        except (TypeError, ValueError):
            pass

    # ISO 8601 with or without a time part.
    head = text.split("T", 1)[0].split(" ", 1)[0]
    for fmt in _FORMATS:
        try:
            return datetime.strptime(head, fmt).date()
        except ValueError:
            continue

    # Last resort: an ISO date embedded in a longer string.
    if match := _ISO_LIKE.search(text):
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    return None


def days_ago(value: date | None, *, today: date | None = None) -> int | None:
    """How many days old a date is. `None` in, `None` out."""
    if value is None:
        return None
    return ((today or date.today()) - value).days
