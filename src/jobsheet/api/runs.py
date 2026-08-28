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
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from jobsheet.core.matching import SearchProfile, profile_key
from jobsheet.pipeline import RunReport, SourceRequest, run_search
from jobsheet.sheet.row import JobRow
from jobsheet.sources.base import Phase, percent_for
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

    # The other half of the commentary: how far each source has got, as numbers
    # a bar can be drawn from. Kept beside the prose rather than parsed out of
    # it, because a log line is written for a person and reformatting it would
    # break the display.
    state: dict[str, dict[str, Any]] = field(default_factory=dict)

    report: RunReport | None = None
    error: str = ""
    # Which row in the `runs` table this became, once it finished. It is what
    # the results screen filters by when the user asks for one search's ads.
    recorded_id: str = ""
    task: asyncio.Task[None] | None = field(default=None, repr=False)
    _listeners: list[asyncio.Queue[Any]] = field(default_factory=list, repr=False)

    @property
    def finished(self) -> bool:
        return self.phase is not RunPhase.RUNNING

    def _emit(self, event: tuple[str, str]) -> None:
        for queue in self._listeners:
            queue.put_nowait(event)

    def note(self, message: str) -> None:
        """Record one line of commentary and hand it to everyone listening."""
        self.lines.append(message)
        self._emit(("progress", message))

    def step(self, source_id: str, phase: str, done: int = 0, total: int = 0) -> None:
        """Record how far one source has got, and hand that on too."""
        before = self.state.get(source_id, {})
        entry = {
            "source_id": source_id,
            "phase": phase,
            "done": done,
            "total": total,
            "percent": percent_for(
                phase, done, total, previous=int(before.get("percent", 0))
            ),
        }
        self.state[source_id] = entry
        self._emit(("state", json.dumps(entry)))

    def _close(self) -> None:
        for queue in self._listeners:
            queue.put_nowait(_SENTINEL)
        self._listeners.clear()

    async def listen(self) -> AsyncIterator[tuple[str, str]]:
        """Everything this run has said, then everything it says next.

        Both channels replay, and they have to replay differently. The prose is
        a history, so all of it goes; the bars are a position, so only where
        each source is *now* goes. A page reloaded mid-search must not come back
        to empty bars, which is the whole reason the backlog exists.
        """
        queue: asyncio.Queue[Any] = asyncio.Queue()
        for line in self.lines:
            queue.put_nowait(("progress", line))
        for entry in self.state.values():
            queue.put_nowait(("state", json.dumps(entry)))
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
            "state": {key: dict(value) for key, value in self.state.items()},
            "run_id": self.recorded_id,
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

        # A row per source before anything has happened, so the interface can
        # draw the whole list at once rather than growing it as sources report.
        for request in run.requests:
            run.step(request.source_id, Phase.WAITING)

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
        # What "already seen" means for this account, worked out before the run
        # so the pipeline never touches the database itself. The filtered-out
        # memory is scoped to the search that produced it: change what you are
        # looking for and the ads it turned away get another hearing, which is
        # the difference between remembering a decision and burying an ad.
        key = profile_key(profile)
        try:
            report = await run_search(
                run.requests,
                profile,
                existing=run.db.all_rows(),
                forgotten=run.db.forgotten_keys(),
                filtered_before=run.db.filtered_out_keys(key),
                http=self.state.http,
                today=today,
                max_items=max_items,
                max_enrich=max_enrich,
                on_progress=run.note,
                on_step=run.step,
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

        self._record(run, report, profile_key=key)
        run.phase = RunPhase.DONE
        run.report = report
        run.note(f"Saved {len(report.rows)} new job(s).")
        run._close()

    def _record(self, run: SearchRun, report: RunReport, *, profile_key: str) -> None:
        """Everything a finished search leaves behind on disk."""
        # The run row comes first, because its id is what stamps the ads. That
        # stamp is the only way to tell this morning's search from this
        # afternoon's: `found_at` is a date, and both happened today.
        recorded = run.db.record_run(
            fetched=report.fetched,
            added=report.new_count,
            duplicates=report.duplicates,
            rejected=len(report.rejected),
            errors=report.errors,
            started_at=run.started_at,
        )
        run.recorded_id = str(recorded)
        run.db.save_rows(report.rows, run_id=run.recorded_id)
        run.db.remember_filtered(
            [(posting.dedup_key, rejection.code) for posting, rejection in report.rejected],
            profile_key=profile_key,
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
