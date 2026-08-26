"""Searches in flight, and the live commentary they produce.

A search takes tens of seconds and talks to a dozen strangers' servers, so the
HTTP request that starts one cannot be the request that waits for it. Starting a
search therefore returns an id immediately, and the interface subscribes to that
id for the running commentary.

Each subscriber gets its own queue, primed with whatever the run has already
said. That means a browser that connects late, reloads mid-search, or opens the
page in a second tab still sees the whole story rather than joining halfway.

One manager serves every account, because the runs are in memory and there is no
sense in a dictionary per person. Each run therefore carries the account it
belongs to and the database handle to write itself into; `UserRuns` in
`api.state` is what stops one account seeing another's searches.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from jobsheet.core.matching import SearchProfile
from jobsheet.pipeline import RunReport, SourceRequest, run_search
from jobsheet.sheet.row import JobRow
from jobsheet.store.db import Database

if TYPE_CHECKING:  # pragma: no cover
    from jobsheet.api.state import AppState

__all__ = ["RunManager", "RunPhase", "SearchRun"]

# Runs are kept so the interface can show what happened after the fact. Twenty is
# far more than anyone scrolls back through, and each is a few kilobytes.
KEEP_RUNS = 20

_SENTINEL = object()


class RunPhase(StrEnum):
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SearchRun:
    """One search, its commentary, and whatever it ended up with."""

    id: str
    started_at: datetime
    requests: list[SourceRequest]
    user_id: int
    # The account's own handle on the database. Held rather than looked up
    # again later: the run outlives the request that started it, and by the
    # time it finishes there is no signed-in user to ask.
    db: Database = field(repr=False)
    phase: RunPhase = RunPhase.RUNNING
    lines: list[str] = field(default_factory=list)
    report: RunReport | None = None
    error: str = ""
    task: asyncio.Task[None] | None = field(default=None, repr=False)
    _listeners: list[asyncio.Queue[Any]] = field(default_factory=list, repr=False)

    @property
    def finished(self) -> bool:
        return self.phase is not RunPhase.RUNNING

    def note(self, message: str) -> None:
        """Record one line of commentary and hand it to everyone listening."""
        self.lines.append(message)
        for queue in self._listeners:
            queue.put_nowait(message)

    def _close(self) -> None:
        for queue in self._listeners:
            queue.put_nowait(_SENTINEL)
        self._listeners.clear()

    async def listen(self) -> AsyncIterator[str]:
        """Every line this run has said, then every line it says next."""
        queue: asyncio.Queue[Any] = asyncio.Queue()
        for line in self.lines:
            queue.put_nowait(line)
        if self.finished:
            queue.put_nowait(_SENTINEL)
        else:
            self._listeners.append(queue)

        try:
            while True:
                item = await queue.get()
                if item is _SENTINEL:
                    return
                yield item
        finally:
            if queue in self._listeners:
                self._listeners.remove(queue)

    def summary(self) -> dict[str, Any]:
        """The shape the interface polls for, with or without a finished report."""
        report = self.report
        return {
            "id": self.id,
            "phase": str(self.phase),
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "sources": [request.source_id for request in self.requests],
            "lines": list(self.lines),
            "error": self.error,
            "fetched": report.fetched if report else 0,
            "duplicates": report.duplicates if report else 0,
            "new": report.new_count if report else 0,
            "rejected": len(report.rejected) if report else 0,
            "errors": dict(report.errors) if report else {},
            "harvested": dict(report.harvested) if report else {},
        }


class RunManager:
    """Starts searches, keeps the recent ones, and never leaves a task orphaned."""

    def __init__(self, state: AppState) -> None:
        self.state = state
        self._runs: dict[str, SearchRun] = {}

    # ------------------------------------------------------------- inspection

    def get(self, run_id: str) -> SearchRun | None:
        return self._runs.get(run_id)

    def recent(self) -> list[SearchRun]:
        return sorted(self._runs.values(), key=lambda run: run.started_at, reverse=True)

    # --------------------------------------------------------------- starting

    def start(
        self,
        requests: list[SourceRequest],
        profile: SearchProfile | None = None,
        *,
        db: Database,
        user_id: int,
        today: date | None = None,
        max_items: int = 200,
        max_enrich: int = 40,
    ) -> SearchRun:
        """Kick off a search and return before it has done anything."""
        run = SearchRun(
            id=uuid.uuid4().hex[:12],
            started_at=datetime.now(),
            requests=list(requests),
            user_id=user_id,
            db=db,
        )
        self._runs[run.id] = run
        self._forget_old()

        run.task = asyncio.create_task(
            self._drive(
                run,
                profile or SearchProfile(),
                today=today,
                max_items=max_items,
                max_enrich=max_enrich,
            )
        )
        return run

    def _forget_old(self) -> None:
        finished = [run for run in self.recent()[KEEP_RUNS:] if run.finished]
        for run in finished:
            self._runs.pop(run.id, None)

    async def _drive(
        self,
        run: SearchRun,
        profile: SearchProfile,
        *,
        today: date | None,
        max_items: int,
        max_enrich: int,
    ) -> None:
        try:
            report = await run_search(
                run.requests,
                profile,
                existing=run.db.all_rows(),
                http=self.state.http,
                today=today,
                max_items=max_items,
                max_enrich=max_enrich,
                on_progress=run.note,
            )
        except asyncio.CancelledError:
            run.phase = RunPhase.CANCELLED
            run.note("Search stopped.")
            run._close()
            raise
        except Exception as error:
            run.phase = RunPhase.FAILED
            run.error = f"{type(error).__name__}: {error}"
            run.note(f"Search failed: {run.error}")
            run._close()
            return

        self._record(run, report)
        run.phase = RunPhase.DONE
        run.report = report
        run.note(f"Saved {len(report.rows)} new job(s).")
        run._close()

    def _record(self, run: SearchRun, report: RunReport) -> None:
        """Everything a finished search leaves behind on disk."""
        run.db.save_rows(report.rows)
        run.db.record_run(
            fetched=report.fetched,
            added=report.new_count,
            duplicates=report.duplicates,
            rejected=len(report.rejected),
            errors=report.errors,
            started_at=run.started_at,
        )
        for request in run.requests:
            source_id = request.source_id
            failure = report.errors.get(source_id)
            # Source health is a fact about the source, not about the account,
            # so it is the one thing a run writes that everybody shares.
            self.state.db.record_source_health(
                source_id,
                ok=failure is None,
                count=report.harvested.get(source_id, 0),
                message=failure or f"{report.harvested.get(source_id, 0)} ad(s)",
            )

    # --------------------------------------------------------------- stopping

    async def cancel(self, run_id: str) -> bool:
        run = self._runs.get(run_id)
        if run is None or run.task is None or run.finished:
            return False
        run.task.cancel()
        # Awaiting a cancelled task re-raises whatever ended it. Both arms are
        # needed: `CancelledError` is a `BaseException`, so `Exception` alone
        # would not catch the ordinary case. Either way the run has already
        # recorded its own outcome, and there is nothing here to report.
        with suppress(asyncio.CancelledError, Exception):
            await run.task
        return True

    async def cancel_all(self) -> None:
        for run_id in list(self._runs):
            await self.cancel(run_id)


def rows_of(report: RunReport | None) -> list[JobRow]:
    """The rows a finished run produced, or none if it has not finished."""
    return list(report.rows) if report else []
