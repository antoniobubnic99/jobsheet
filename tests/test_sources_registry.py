"""Source discovery.

The registry's job is to be uninteresting: find everything installed, and refuse
to let one broken plugin matter.
"""

from __future__ import annotations

from typing import Any

import pytest

from jobsheet.core.models import Posting
from jobsheet.sources import registry
from jobsheet.sources.base import FetchContext, Source, SourceManifest

BUILT_IN = {
    "rss",
    "greenhouse",
    "lever",
    "ashby",
    "workable",
    "recruitee",
    "smartrecruiters",
    "remotive",
    "remoteok",
    "arbeitnow",
    "hzz",
    "posao_hr",
    "narodne_novine",
    "selekcija",
}


class TestDiscovery:
    def test_every_built_in_source_is_found(self) -> None:
        """Built-ins register through the same entry-point group as plugins."""
        assert set(registry.load_all(refresh=True)) >= BUILT_IN

    def test_get_returns_a_source_class(self) -> None:
        assert issubclass(registry.get("rss"), Source)

    def test_get_on_an_unknown_id_names_what_is_available(self) -> None:
        with pytest.raises(KeyError, match="no such source"):
            registry.get("definitely-not-a-source")

    def test_available_is_sorted(self) -> None:
        listed = registry.available()
        assert listed == sorted(listed)


class TestManifests:
    def test_one_manifest_per_source(self) -> None:
        assert len(registry.manifests()) == len(registry.load_all())

    def test_global_sources_are_listed_before_country_specific_ones(self) -> None:
        """Global sources work for anyone without configuration."""
        countries = [m.country or "" for m in registry.manifests()]
        assert countries == sorted(countries)

    def test_ids_are_unique(self) -> None:
        ids = [m.id for m in registry.manifests()]
        assert len(ids) == len(set(ids))

    def test_no_built_in_source_needs_credentials(self) -> None:
        """The app must be fully usable without signing up for anything."""
        for manifest in registry.manifests():
            if manifest.id in BUILT_IN:
                assert manifest.needs_credentials is False, manifest.id

    def test_required_params_have_no_default(self) -> None:
        """A required field with a default is a field the user never notices."""
        for manifest in registry.manifests():
            for spec in manifest.params:
                if spec.required and spec.kind not in ("multiselect", "select"):
                    assert spec.default is None, f"{manifest.id}.{spec.name}"

    def test_select_params_offer_choices(self) -> None:
        for manifest in registry.manifests():
            for spec in manifest.params:
                if spec.kind in ("select", "multiselect"):
                    assert spec.choices, f"{manifest.id}.{spec.name}"

    def test_manifests_serialise_for_the_interface(self) -> None:
        """The web interface builds its forms from these, so they must travel."""
        for manifest in registry.manifests():
            assert SourceManifest.model_validate_json(manifest.model_dump_json()) == manifest


class TestRegisteringAtRuntime:
    def test_a_source_can_be_added_in_process(self) -> None:
        class Extra(Source):
            manifest = SourceManifest(id="extra-test", name="Extra", homepage="https://x.test")

            async def fetch(self, params: dict[str, Any], ctx: FetchContext) -> list[Posting]:
                return []

        registry.register(Extra)
        try:
            assert registry.get("extra-test") is Extra
        finally:
            registry._extra.pop("extra-test", None)
            registry.load_all(refresh=True)

    def test_register_works_as_a_decorator(self) -> None:
        @registry.register
        class Decorated(Source):
            manifest = SourceManifest(id="decorated-test", name="D", homepage="https://x.test")

            async def fetch(self, params: dict[str, Any], ctx: FetchContext) -> list[Posting]:
                return []

        try:
            assert registry.get("decorated-test") is Decorated
        finally:
            registry._extra.pop("decorated-test", None)
            registry.load_all(refresh=True)


class TestSourceBase:
    def test_param_falls_back_to_the_declared_default(self) -> None:
        source = registry.get("arbeitnow")()
        assert source.param({}, "pages") == 3
        assert source.param({"pages": 7}, "pages") == 7

    def test_blank_input_falls_back_to_the_default(self) -> None:
        """An empty form field means "unanswered", not "zero"."""
        source = registry.get("arbeitnow")()
        assert source.param({"pages": ""}, "pages") == 3

    def test_unknown_param_is_none(self) -> None:
        assert registry.get("rss")().param({}, "no-such-param") is None

    async def test_enrich_defaults_to_a_no_op(self, ctx: FetchContext) -> None:
        """Returning the posting unchanged is always a valid answer."""
        posting = Posting(source_id="rss", title="X", url="https://example.test/1")
        assert await registry.get("rss")().enrich(posting, ctx) is posting


def test_every_shipped_source_has_a_live_check() -> None:
    """A new connector must come with a nightly check against the real service.

    Lives here rather than in `test_sources_live.py` because everything in that
    module is marked `network` and therefore skipped on push -- which is exactly
    when someone adds a source and forgets.

    Reads the entry points rather than `load_all()`: half the suite registers
    test doubles in process, and those neither need nor could have a live check.
    """
    from importlib.metadata import entry_points

    from tests.test_sources_live import TARGETS_BY_ID

    shipped = {entry.name for entry in entry_points(group=registry.ENTRY_POINT_GROUP)}
    assert shipped, "no sources are declared in pyproject.toml"
    missing = sorted(shipped - set(TARGETS_BY_ID))
    assert not missing, f"no live check for: {missing}"
