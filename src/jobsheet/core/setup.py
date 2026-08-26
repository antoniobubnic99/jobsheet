"""What somebody told JobSheet before their first search.

The wizard that runs after sign-in asks two different kinds of question -- what
you are looking for, and where to look for it -- and the answers have always
lived in two different places: `SearchProfile` for the first, a list of chosen
sources for the second. Storing them separately would mean a half-restored
setup is possible, where a profile comes back without the sources it was written
against. One object, saved once, cannot come apart like that.

It is kept in the ordinary profiles table under the `setup` kind, so the same
validation, the same versioning and the same "this does not load, so it is not
worth saving" rule apply to it as to a saved search.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from jobsheet.core.matching import SearchProfile

__all__ = ["DEFAULT_SETUP", "SearchSetup", "SourceChoice"]

# One setup per account, under a fixed name. A person can still save as many
# named searches as they like; this is the one the interface opens with.
DEFAULT_SETUP = "default"


class SourceChoice(BaseModel):
    """One source the user picked, with the answers to its own form."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    params: dict[str, Any] = Field(default_factory=dict)


class SearchSetup(BaseModel):
    """A whole search, ready to run: what to look for and where."""

    model_config = ConfigDict(extra="forbid")

    profile: SearchProfile = Field(default_factory=SearchProfile)
    sources: list[SourceChoice] = Field(default_factory=list)

    # Free text the wizard collects but nothing filters on: a job title in the
    # person's own words. It is what the letter writer opens with, and what makes
    # the summary screen read like a sentence rather than a list of terms.
    headline: str = ""
