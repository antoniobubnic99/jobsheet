"""Finding sources, including ones this project has never heard of.

Discovery goes through the `jobsheet.sources` entry-point group, which the
built-in connectors register in `pyproject.toml` exactly the way a third-party
package would. There is no privileged internal list: `pip install
jobsheet-source-something` and it appears in the interface beside the rest.

A source that fails to import is skipped with a warning rather than taking the
whole app down. A broken plugin is the plugin author's problem; the user still
needs their other fifteen sources.
"""

from __future__ import annotations

import logging
from importlib.metadata import entry_points
from typing import Any

from jobsheet.sources.base import Source, SourceManifest

__all__ = ["ENTRY_POINT_GROUP", "available", "get", "load_all", "manifests", "register"]

ENTRY_POINT_GROUP = "jobsheet.sources"

log = logging.getLogger(__name__)

# Sources registered in-process rather than through packaging metadata. Used by
# tests and by anyone embedding JobSheet as a library.
_extra: dict[str, type[Source]] = {}

_cache: dict[str, type[Source]] | None = None


def register(source: type[Source]) -> type[Source]:
    """Add a source at run time. Also usable as a decorator."""
    _extra[source.manifest.id] = source
    global _cache
    _cache = None
    return source


def load_all(*, refresh: bool = False) -> dict[str, type[Source]]:
    """Every source that can be imported, keyed by manifest id."""
    global _cache
    if _cache is not None and not refresh:
        return dict(_cache)

    found: dict[str, type[Source]] = {}
    for entry in entry_points(group=ENTRY_POINT_GROUP):
        try:
            loaded: Any = entry.load()
        except Exception as error:
            log.warning("source %r could not be loaded: %s", entry.name, error)
            continue
        if not (isinstance(loaded, type) and issubclass(loaded, Source)):
            log.warning("source %r is not a Source subclass; ignoring", entry.name)
            continue
        if not getattr(loaded, "manifest", None):
            log.warning("source %r has no manifest; ignoring", entry.name)
            continue
        found[loaded.manifest.id] = loaded

    found.update(_extra)
    _cache = found
    return dict(found)


def available() -> list[str]:
    return sorted(load_all())


def get(source_id: str) -> type[Source]:
    sources = load_all()
    if source_id not in sources:
        raise KeyError(f"no such source: {source_id!r} (have: {', '.join(sorted(sources))})")
    return sources[source_id]


def manifests() -> list[SourceManifest]:
    """Every manifest, sorted for a stable interface: global first, then by name.

    Global sources come first because they are the ones that work for any user
    without configuration; country-specific ones are useful to a minority and
    would otherwise crowd the top of the list.
    """
    found = [cls.manifest for cls in load_all().values()]
    return sorted(found, key=lambda m: (m.country or "", m.name.casefold()))
