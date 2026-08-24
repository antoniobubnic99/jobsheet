"""The layout the user designs, and the themes they colour it with."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from pydantic import ValidationError

from jobsheet.sheet.layout import (
    ColumnKind,
    ColumnSpec,
    ConditionalRule,
    SheetLayout,
    classic_checkboxes_layout,
    default_layout,
    minimal_layout,
)
from jobsheet.sheet.theme import THEMES, ExcelTheme, resolve_theme


class TestColumnSpec:
    def test_rejects_empty_key_or_label(self) -> None:
        with pytest.raises(ValidationError):
            ColumnSpec(key="   ", label="Something")
        with pytest.raises(ValidationError):
            ColumnSpec(key="title", label="  ")

    def test_rejects_absurd_width(self) -> None:
        with pytest.raises(ValidationError):
            ColumnSpec(key="title", label="Position", width=0)
        with pytest.raises(ValidationError):
            ColumnSpec(key="title", label="Position", width=9999)

    def test_known_source_column_is_app_owned(self) -> None:
        assert ColumnSpec(key="title", label="Position").user_owned is False

    def test_checkbox_is_always_user_owned(self) -> None:
        """Ownership is inferred, so a user cannot accidentally mark a tick box
        as app-owned and have the next run wipe it."""
        assert ColumnSpec(key="applied", label="Applied", kind=ColumnKind.CHECKBOX).user_owned

    def test_status_is_always_user_owned(self) -> None:
        assert ColumnSpec(key="status", label="Status", kind=ColumnKind.STATUS).user_owned

    def test_unknown_key_is_a_user_column(self) -> None:
        """Anything the app cannot fill is something the user invented."""
        assert ColumnSpec(key="my_notes", label="My notes").user_owned


class TestConditionalRule:
    def test_six_digit_hex_is_expanded_to_argb(self) -> None:
        rule = ConditionalRule(when_column="status", equals="applied", fill="c6efce")
        assert rule.argb == "FFC6EFCE"

    def test_eight_digit_hex_is_left_alone(self) -> None:
        rule = ConditionalRule(when_column="status", equals="applied", fill="FFC6EFCE")
        assert rule.argb == "FFC6EFCE"

    def test_rejects_nonsense_colour(self) -> None:
        with pytest.raises(ValidationError):
            ConditionalRule(when_column="status", equals="applied", fill="reddish")


class TestSheetLayout:
    def test_needs_at_least_one_column(self) -> None:
        with pytest.raises(ValidationError):
            SheetLayout(columns=[])

    def test_rejects_duplicate_keys(self) -> None:
        with pytest.raises(ValidationError, match="duplicate column keys"):
            SheetLayout(
                columns=[
                    ColumnSpec(key="title", label="Position"),
                    ColumnSpec(key="title", label="Role"),
                ]
            )

    def test_rejects_duplicate_labels(self) -> None:
        """Headers are the fallback for matching a hand-rearranged workbook, so
        two identical headers would make that matching ambiguous."""
        with pytest.raises(ValidationError, match="duplicate column labels"):
            SheetLayout(
                columns=[
                    ColumnSpec(key="title", label="Name"),
                    ColumnSpec(key="company", label="name"),
                ]
            )

    def test_rejects_rule_pointing_at_a_missing_column(self) -> None:
        with pytest.raises(ValidationError, match="unknown column"):
            SheetLayout(
                columns=[ColumnSpec(key="title", label="Position")],
                rules=[ConditionalRule(when_column="status", equals="applied", fill="C6EFCE")],
            )

    def test_index_of(self) -> None:
        layout = minimal_layout()
        assert layout.index_of("found_at") == 1
        assert layout.index_of("url") == 4
        assert layout.index_of("nonexistent") is None

    def test_user_owned_and_checkbox_keys(self) -> None:
        layout = classic_checkboxes_layout()
        assert layout.checkbox_keys == ("applied", "interview", "not_applied")
        assert set(layout.checkbox_keys) <= set(layout.user_owned_keys)

    def test_round_trips_through_json(self) -> None:
        """The layout is embedded in the workbook, so this is load-bearing."""
        original = default_layout()
        restored = SheetLayout.model_validate_json(original.model_dump_json())
        assert restored == original


class TestPresets:
    @pytest.mark.parametrize(
        "factory", [default_layout, classic_checkboxes_layout, minimal_layout]
    )
    def test_presets_are_valid(self, factory: Callable[[], SheetLayout]) -> None:
        layout = factory()
        assert layout.columns
        assert layout.theme in THEMES

    def test_classic_preserves_the_predecessor_shape(self) -> None:
        """The original user's nine columns must survive the generalisation."""
        layout = classic_checkboxes_layout()
        assert [c.key for c in layout.columns] == [
            "found_at",
            "company",
            "title",
            "url",
            "category",
            "note",
            "applied",
            "interview",
            "not_applied",
        ]

    def test_classic_greys_out_before_it_greens(self) -> None:
        """Did-not-apply must win over applied -- hence stop_if_true comes first."""
        rules = classic_checkboxes_layout().rules
        assert rules[0].when_column == "not_applied"
        assert rules[0].stop_if_true is True
        assert rules[1].when_column == "applied"
        assert rules[1].stop_if_true is False


class TestThemes:
    def test_every_preset_is_valid(self) -> None:
        for name, theme in THEMES.items():
            assert theme.header_fill.startswith("FF")
            assert len(theme.header_fill) == 8, name

    def test_six_digit_input_is_normalised(self) -> None:
        theme = ExcelTheme(name="Custom", header_fill="1f3864")
        assert theme.header_fill == "FF1F3864"

    def test_dark_header_wants_white_text(self) -> None:
        assert ExcelTheme(name="Dark", header_fill="1F3864").is_dark_header is True

    def test_pale_header_does_not(self) -> None:
        """A user picking a pale custom colour must not get white-on-cream."""
        assert ExcelTheme(name="Pale", header_fill="FFF3C4").is_dark_header is False

    def test_unknown_theme_falls_back_rather_than_raising(self) -> None:
        """A layout shared from a newer version must still open here."""
        assert resolve_theme("theme-from-the-future") is THEMES["navy"]

    def test_custom_theme_passes_through(self) -> None:
        custom = ExcelTheme(name="Mine", header_fill="123456")
        assert resolve_theme(custom) is custom
