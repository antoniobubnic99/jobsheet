"""What a source is, and the contract every connector honours.

The point of the manifest is that **adding a source touches no user-interface
code**. A source declares the questions it needs answered -- a feed URL, a company
slug, a county number -- and the app builds the form for it. That is what makes a
third-party source installable rather than something that has to be merged here.

A source does two things, and the split matters for politeness and speed:

* `fetch` gets the cheap listing. One request, or a handful.
* `enrich` opens one ad's own page for the fields the listing omits. It runs only
  for ads that already passed the keyword filter, because it is the expensive
  half and most ads never need it.
"""

from __future__ import annotations

import abc
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from jobsheet.core.http import HttpClient
from jobsheet.core.models import Posting

__all__ = ["Choice", "FetchContext", "ParamSpec", "Source", "SourceError", "SourceManifest"]


class SourceError(RuntimeError):
    """A source could not produce results. Never fatal to a whole search."""


class Choice(BaseModel):
    """One option in a select parameter."""

    model_config = ConfigDict(extra="forbid")

    value: str
    label: str


class ParamSpec(BaseModel):
    """One question a source needs answered before it can run.

    The user interface renders these directly, so `kind` is a rendering
    instruction as much as a type.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    label: str
    kind: Literal["text", "url", "number", "boolean", "select", "multiselect"] = "text"
    required: bool = False
    default: Any = None
    choices: list[Choice] = Field(default_factory=list)
    placeholder: str = ""
    help: str = ""


class SourceManifest(BaseModel):
    """Everything the app needs to know about a source without importing it."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    homepage: str
    description: str = ""

    # ISO 3166-1 alpha-2, or None for sources that are not country-specific.
    # Used only to group the list; it never filters anything out.
    country: str | None = None

    params: list[ParamSpec] = Field(default_factory=list)

    # Seconds between requests to this source's host. Raised for small servers.
    rate_limit: float = 0.7

    # Whether `enrich` does anything, so the pipeline can skip a pointless pass.
    supports_enrich: bool = False

    # True only for sources that cannot work without a credential. Every source
    # shipped with JobSheet is False: the app is usable without signing up for
    # anything, and that is a deliberate constraint rather than an accident.
    needs_credentials: bool = False

    @property
    def is_global(self) -> bool:
        return self.country is None


@dataclass
class FetchContext:
    """What a source is given at run time.

    Sources never make their own HTTP client, clock or limits -- that is how
    politeness, timeouts and test determinism stay enforceable from outside.
    """

    http: HttpClient
    today: date = field(default_factory=date.today)

    # Upper bound on ads returned from one run of one source. Protects both the
    # user's patience and the source's server.
    max_items: int = 200

    # Upper bound on detail pages opened per run. Enrichment is the expensive
    # half, and an unbounded pass over a busy feed is exactly what gets a scraper
    # blocked.
    max_enrich: int = 40

    # Progress reporting. The web interface streams these lines live.
    on_progress: Callable[[str], None] = lambda message: None

    def report(self, message: str) -> None:
        self.on_progress(message)


class Source(abc.ABC):
    """Base class for every connector."""

    manifest: ClassVar[SourceManifest]

    @abc.abstractmethod
    async def fetch(self, params: dict[str, Any], ctx: FetchContext) -> list[Posting]:
        """Return the cheap listing. Raise `SourceError` if it cannot be had."""

    async def enrich(self, posting: Posting, ctx: FetchContext) -> Posting:
        """Fill in fields the listing omitted, by opening the ad's own page.

        The default does nothing, so a source only implements this when its
        listing is genuinely incomplete. Returning the posting unchanged is
        always a valid answer -- including when the fetch failed, because losing
        the extra fields is better than losing the ad.
        """
        return posting

    def param(self, params: dict[str, Any], name: str) -> Any:
        """Read a parameter, falling back to the manifest's declared default."""
        if name in params and params[name] not in (None, ""):
            return params[name]
        for spec in self.manifest.params:
            if spec.name == name:
                return spec.default
        return None
