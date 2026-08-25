"""The local HTTP interface: one process serving both the API and the pages."""

from __future__ import annotations

from jobsheet.api.app import create_app

__all__ = ["create_app"]
