"""The one HTTP client every source shares.

Centralised so that politeness is not a per-source decision. Any source can be
written carelessly; none of them can be rude, because they do not own the socket.

Three things are enforced here rather than trusted to each connector:

* **A per-host delay.** Sources that fan out over many detail pages would
  otherwise hammer a single small server.
* **An honest User-Agent.** It names the project and links to it, so an
  administrator who sees the traffic can find out what it is and, if they object,
  who to tell.
* **A timeout on everything.** One unresponsive host must not hang a whole run.

Sources never construct their own client; they receive one on the `FetchContext`.
"""

from __future__ import annotations

import asyncio
import time
from types import TracebackType
from typing import Any, Self
from urllib.parse import urlsplit

import httpx

from jobsheet import __version__

__all__ = ["USER_AGENT", "HttpClient", "HttpError"]

USER_AGENT = (
    f"JobSheet/{__version__} (+https://github.com/antoniobubnic99/jobsheet) "
    "personal job-search tool"
)

ACCEPT_DOCUMENT = "application/rss+xml, application/xml, text/html;q=0.9, */*;q=0.8"
ACCEPT_JSON = "application/json, text/plain;q=0.9, */*;q=0.8"


class HttpError(RuntimeError):
    """A request failed in a way the source cannot recover from."""


class HttpClient:
    """A shared, rate-limited, honestly-identified HTTP client."""

    def __init__(
        self,
        *,
        timeout: float = 25.0,
        rate_limit: float = 0.7,
        user_agent: str = USER_AGENT,
        accept_language: str = "en,hr;q=0.8",
    ) -> None:
        self._rate_limit = rate_limit
        self._last_call: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": user_agent, "Accept-Language": accept_language},
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _wait_turn(self, url: str) -> None:
        """Hold back so that no single host is hit faster than the rate limit.

        The lock is per host, so unrelated sources still run concurrently -- the
        delay slows down one server's queue, not the whole search.
        """
        host = urlsplit(url).netloc
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            previous = self._last_call.get(host)
            if previous is not None:
                waited = time.monotonic() - previous
                if waited < self._rate_limit:
                    await asyncio.sleep(self._rate_limit - waited)
            self._last_call[host] = time.monotonic()

    async def get_bytes(self, url: str, *, accept: str = ACCEPT_DOCUMENT) -> bytes:
        await self._wait_turn(url)
        try:
            response = await self._client.get(url, headers={"Accept": accept})
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise HttpError(f"{url}: {error}") from error
        return response.content

    async def get_text(self, url: str, *, encoding: str | None = None) -> str:
        """Fetch text, optionally forcing an encoding.

        Some feeds are served with a wrong or missing charset -- a national
        employment service publishes iso-8859-2 and says nothing -- so the caller
        can override rather than receive mojibake.
        """
        payload = await self.get_bytes(url)
        if encoding:
            return payload.decode(encoding, errors="replace")
        return payload.decode("utf-8", errors="replace")

    async def get_json(self, url: str) -> Any:
        await self._wait_turn(url)
        try:
            response = await self._client.get(url, headers={"Accept": ACCEPT_JSON})
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as error:
            raise HttpError(f"{url}: {error}") from error
        except ValueError as error:
            raise HttpError(f"{url}: response was not JSON") from error
