"""Making a saved profile survive a change to the model that describes it.

A profile -- a saved search, a sheet design, the setup the wizard wrote -- is
stored as raw JSON and read back through a Pydantic model configured with
`extra="forbid"`. That configuration is right: it catches a typo at save time
instead of quietly ignoring the field the user meant to set. But it also welds
the model to the JSON already on disk. Rename one field and every profile saved
before the rename stops loading, everywhere at once: the search screen, `jobsheet
run --profile`, the wizard's own setup.

There was no way out of that, so the last change to the model worked around it by
adding a field instead of renaming one. That workaround has a shelf life -- the
same wall waits for the next change, and by then nobody will remember why the
field is called what it is called.

So the payload now carries a version, and this module walks it forward. Two
functions, because they answer two different questions and belong in two
different places:

* `migrate_profile_payload` -- "what did this document become?" Version steps
  only, no knowledge of any model. `Database.load_profile` calls it, which is
  right, because the database is a store of named JSON and nothing more; it must
  hand back what was put in.
* `fit_to_model` -- "will this model accept it?" Drops fields the model has no
  place for. Called at each of the three points where a payload becomes a model,
  and nowhere else.

The step list is shaped after `MIGRATIONS` in `store.db`, which does the same job
for the schema. The difference is only that these are Python functions over a
dict rather than SQL, because what they migrate is a document.

**`extra="forbid"` stays.** Both of these run before validation, not instead of
it. A payload they have finished with is expected to be exactly right, and a
model that still refuses it is a bug worth hearing about.

## Adding a step

Append one function to the list for that kind and raise `CURRENT`. Keep it
small -- one rename, one default, one field dropped -- and give it a test beside
the others. A step only ever sees a payload at exactly the version below it, so
it never has to guess what it is looking at.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel

__all__ = [
    "CURRENT",
    "VERSION_KEY",
    "fit_to_model",
    "migrate_profile_payload",
    "stamp",
]

VERSION_KEY = "_v"

Step = Callable[[dict[str, Any]], dict[str, Any]]

# The version each kind of payload is written at today. A payload with no `_v` is
# version 1: that is what every profile written before this module existed is.
CURRENT: dict[str, int] = {"search": 1, "setup": 1, "layout": 1}

# STEPS[kind][n] takes a payload at version n+1 and returns one at version n+2.
# Empty for now, on purpose -- nothing has been renamed yet. The mechanism is
# here so that the next change is a five-line function rather than a stuck user.
STEPS: dict[str, list[Step]] = {"search": [], "setup": [], "layout": []}


def stamp(kind: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """The payload as it should be written: itself, plus the version it is at."""
    return {**payload, VERSION_KEY: CURRENT.get(kind, 1)}


def migrate_profile_payload(kind: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Bring a stored payload up to the shape the current code writes.

    Runs the steps registered for this kind, each one turning the version below
    it into the version above, and takes the version marker back off -- it is
    bookkeeping, not content, and no model has a field for it.

    Nothing here knows what a `SearchProfile` looks like, and that is deliberate:
    this runs inside the database layer, whose contract is that what you saved is
    what you get back. Fitting a payload to a model is `fit_to_model`, and it
    happens later, where a model is actually being built.
    """
    version = _version_of(payload)
    data = {key: value for key, value in payload.items() if key != VERSION_KEY}

    for step in STEPS.get(kind, [])[version - 1 :]:
        data = step(data)
    return data


def fit_to_model(model: type[BaseModel], payload: Mapping[str, Any]) -> dict[str, Any]:
    """The payload with anything the model has no field for removed.

    The last thing between a stored document and `model_validate`. What it exists
    for is the field that used to be there: a profile written by an older
    JobSheet, or by a newer one somebody has since rolled back from, carries a
    name this model does not have, and `extra="forbid"` would turn that into a
    wall the user cannot get past without deleting their own saved search.

    Dropping is quiet, and only ever loses a value the model has nowhere to put.
    It is not a licence to be careless at save time: the interface saves what a
    model produced, so a stray field arriving here means a much older install or
    a hand-edited file -- both of which should load rather than fail.
    """
    fields = frozenset(model.model_fields)
    return {key: value for key, value in payload.items() if key in fields}


def _version_of(payload: Mapping[str, Any]) -> int:
    """The version stamped on a payload. Anything unreadable counts as the first."""
    try:
        return max(1, int(payload.get(VERSION_KEY, 1)))
    except (TypeError, ValueError):
        return 1
