"""What JobSheet can search, and whether each one is still answering.

The interface draws every source's form from the manifest returned here, which
is the whole point of the plugin design: installing `jobsheet-source-something`
makes a new form appear without a line of frontend code being written.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from jobsheet.api.state import CurrentDb, CurrentState
from jobsheet.sources import registry

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("")
def list_sources(state: CurrentState) -> dict[str, Any]:
    """Every installed source, with the health record we have for it."""
    health = {record["source_id"]: record for record in state.db.source_health()}
    manifests = sorted(registry.manifests(), key=lambda m: (m.country or "", m.name.lower()))
    return {
        "sources": [
            {
                **manifest.model_dump(mode="json"),
                "is_global": manifest.is_global,
                "health": health.get(manifest.id),
            }
            for manifest in manifests
        ],
        # Handy for the country filter in the picker, and cheap to compute here
        # rather than having every client re-derive it.
        "countries": sorted({m.country for m in manifests if m.country}),
    }


@router.get("/health")
def source_health(db: CurrentDb) -> list[dict[str, Any]]:
    """Last known state of each source. Populated by real runs, not by guesses."""
    return db.source_health()
