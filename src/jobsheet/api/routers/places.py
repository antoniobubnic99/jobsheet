"""The list of places the wizard offers instead of a blank field.

It is a static table read out of `jobsheet.data.places_hr`, served over HTTP for
one reason: the interface should not carry five hundred place names in its
bundle to save a request to a server running on the same machine.

Behind the sign-in like everything except `auth`, not because the names of
Croatian towns are a secret, but because a route that answers a stranger is a
route somebody has to think about later. This one does not have to be.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query

from jobsheet.api.state import CurrentState
from jobsheet.data.places_hr import COUNTIES, county_feed_number, search_places

router = APIRouter(prefix="/api/places", tags=["places"])

MAX_SUGGESTIONS = 20


@router.get("")
def list_places(
    state: CurrentState,
    q: str = "",
    kind: Annotated[Literal["", "city", "county"], Query()] = "",
) -> dict[str, Any]:
    """Suggestions for a place field: counties, cities, or everything.

    `state` is here for the sign-in check and nothing else -- the answer is the
    same for every account, which is why nothing about the user reaches the
    lookup.

    Counties come back with the employment service's feed number attached, so
    that picking a county can tick the right feed on the sources step. That
    number is HZZ's own index and not the official county code; see
    `data.places_hr`.
    """
    matches = search_places(q, kind, limit=MAX_SUGGESTIONS)
    return {
        "places": [
            {**place, "feed": county_feed_number(place["county"]) if place["county"] else None}
            for place in matches
        ],
        # The full county list every time: there are 21 of them, the picker wants
        # to show them all the moment the field is focused, and a second request
        # for a fixed list of twenty-one strings would be silly.
        "counties": [
            {"name": name, "feed": number} for number, name in sorted(COUNTIES.items())
        ],
    }
