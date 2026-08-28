"""A saved profile outliving a change to the model that describes it.

This is the one part of the wizard work that changes nothing anybody can see. It
is here because of what nearly happened instead: `SearchProfile` forbids unknown
fields, profiles are stored as raw JSON, and there was no way to rename a field
without breaking every search a user had already saved. The workaround was to
add a field rather than rename one, which works exactly once.

The test that matters most is the last class, which uses a real database file
rather than a dict -- the same approach as `TestUpgradingAnOldInstall` in
`test_auth.py`, and for the same reason: a migration that only works against a
payload a test just made up is not a migration.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jobsheet.core.matching import SearchProfile
from jobsheet.core.setup import SearchSetup
from jobsheet.sheet.layout import SheetLayout
from jobsheet.store.db import Database
from jobsheet.store.profiles import (
    CURRENT,
    STEPS,
    VERSION_KEY,
    fit_to_model,
    migrate_profile_payload,
    stamp,
)


class TestTheVersionMarker:
    def test_saving_stamps_the_version(self) -> None:
        assert stamp("search", {"locations": ["Rijeka"]}) == {
            "locations": ["Rijeka"],
            VERSION_KEY: 1,
        }

    def test_an_unknown_kind_is_stamped_as_the_first_version(self) -> None:
        assert stamp("something-else", {})[VERSION_KEY] == 1

    def test_migrating_takes_the_marker_back_off(self) -> None:
        """No model has a field for it: it is bookkeeping, not content."""
        migrated = migrate_profile_payload("search", {"locations": ["Rijeka"], VERSION_KEY: 1})
        assert migrated == {"locations": ["Rijeka"]}

    def test_a_payload_from_before_versions_counts_as_the_first(self) -> None:
        assert migrate_profile_payload("search", {"locations": ["Rijeka"]}) == {
            "locations": ["Rijeka"]
        }

    @pytest.mark.parametrize("nonsense", ["", None, "two", {}])
    def test_an_unreadable_version_is_treated_as_the_first(self, nonsense: object) -> None:
        """A hand-edited file should load, not raise."""
        assert migrate_profile_payload("search", {"a": 1, VERSION_KEY: nonsense}) == {"a": 1}

    def test_every_kind_that_can_be_stamped_can_be_migrated(self) -> None:
        assert set(CURRENT) == set(STEPS)

    def test_each_kind_has_as_many_steps_as_versions_above_the_first(self) -> None:
        """The invariant the whole mechanism rests on. Raise one, add the other."""
        for kind, version in CURRENT.items():
            assert len(STEPS[kind]) == version - 1


class TestRunningTheSteps:
    def test_a_step_runs_and_the_version_moves(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A rename, done the way a real one would be."""
        monkeypatch.setitem(CURRENT, "search", 2)
        monkeypatch.setitem(
            STEPS,
            "search",
            [lambda data: {"regions" if k == "counties" else k: v for k, v in data.items()}],
        )

        assert migrate_profile_payload("search", {"counties": ["Istarska"]}) == {
            "regions": ["Istarska"]
        }

    def test_a_payload_already_at_the_top_version_is_left_alone(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Running a rename twice would turn a good profile into a broken one."""
        monkeypatch.setitem(CURRENT, "search", 2)
        monkeypatch.setitem(STEPS, "search", [lambda data: {**data, "ran": data.get("ran", 0) + 1}])

        once = migrate_profile_payload("search", {VERSION_KEY: 1})
        assert once == {"ran": 1}
        assert migrate_profile_payload("search", {**once, VERSION_KEY: 2}) == {"ran": 1}


class TestFittingAPayloadToItsModel:
    def test_a_field_the_model_no_longer_has_is_dropped(self) -> None:
        """Without this, `extra="forbid"` turns an old profile into a dead end."""
        fitted = fit_to_model(SearchProfile, {"locations": ["Rijeka"], "gone_in_a_later_version": 1})
        assert fitted == {"locations": ["Rijeka"]}
        assert SearchProfile.model_validate(fitted).locations == ["Rijeka"]

    def test_the_version_marker_is_dropped_too(self) -> None:
        assert fit_to_model(SearchProfile, {VERSION_KEY: 1}) == {}

    @pytest.mark.parametrize("model", [SearchProfile, SearchSetup, SheetLayout])
    def test_every_stored_kind_can_be_fitted(self, model: type) -> None:
        assert fit_to_model(model, {"nonsense": True}) == {}

    def test_what_the_model_does_know_survives_untouched(self) -> None:
        payload = {"locations": ["Rijeka"], "max_age_days": 7}
        assert fit_to_model(SearchProfile, payload) == payload


class TestAgainstARealFile:
    """The proof: a profile written before the fields existed still loads."""

    @staticmethod
    def _saved(path: Path, payload: dict[str, object]) -> dict[str, object] | None:
        with Database(path) as db:
            db.save_profile("mine", "search", payload)
        with Database(path) as db:
            return db.load_profile("mine", "search")

    def test_a_profile_from_before_this_change_still_loads(self, tmp_path: Path) -> None:
        """No `_v`, and none of the fields the wizard added."""
        loaded = self._saved(tmp_path / "jobsheet.sqlite3", {"locations": ["Rijeka"]})
        assert loaded is not None

        profile = SearchProfile.model_validate(fit_to_model(SearchProfile, loaded))
        assert profile.locations == ["Rijeka"]
        # The new fields arrive empty, which is the same as "no opinion".
        assert profile.wanted_employment_types == []
        assert profile.dream_employers == []

    def test_a_profile_carrying_a_field_nobody_knows_still_loads(self, tmp_path: Path) -> None:
        loaded = self._saved(
            tmp_path / "jobsheet.sqlite3",
            {"locations": ["Split"], "salary_floor": 1200},
        )
        assert loaded is not None
        # The database hands back what was put in -- that is its contract.
        assert loaded == {"locations": ["Split"], "salary_floor": 1200}
        # The model is what refuses the stray field, and fitting is what stops it.
        with pytest.raises(ValueError, match="salary_floor"):
            SearchProfile.model_validate(loaded)
        assert SearchProfile.model_validate(fit_to_model(SearchProfile, loaded)).locations == [
            "Split"
        ]

    def test_the_database_still_round_trips_anything_it_is_given(self, tmp_path: Path) -> None:
        """`Database` is a store of named JSON. Migration must not make it opinionated."""
        payload: dict[str, object] = {"whatever": [1, 2, 3], "nested": {"a": True}}
        assert self._saved(tmp_path / "jobsheet.sqlite3", payload) == payload
