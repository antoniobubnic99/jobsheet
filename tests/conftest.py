"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date

import pytest

from jobsheet.core.http import HttpClient
from jobsheet.sources.base import FetchContext

TODAY = date(2026, 8, 24)


@pytest.fixture
async def http() -> AsyncIterator[HttpClient]:
    """A client with the politeness delay removed, so tests do not sleep."""
    client = HttpClient(rate_limit=0.0, timeout=5.0)
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
def progress() -> list[str]:
    """Collects the lines a source reports, so tests can assert on them."""
    return []


@pytest.fixture
def ctx(http: HttpClient, progress: list[str]) -> FetchContext:
    return FetchContext(
        http=http,
        today=TODAY,
        max_items=200,
        max_enrich=10,
        on_progress=progress.append,
    )
