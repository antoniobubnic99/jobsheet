"""Job sources: one generic RSS reader, ATS connectors, boards, national services.

Every source -- built-in or third-party -- is discovered through the same
`jobsheet.sources` entry-point group. See `registry.py`.
"""

from __future__ import annotations

from jobsheet.sources.base import (
    Choice,
    FetchContext,
    ParamSpec,
    Source,
    SourceError,
    SourceManifest,
)
from jobsheet.sources.registry import available, get, load_all, manifests, register

__all__ = [
    "Choice",
    "FetchContext",
    "ParamSpec",
    "Source",
    "SourceError",
    "SourceManifest",
    "available",
    "get",
    "load_all",
    "manifests",
    "register",
]
