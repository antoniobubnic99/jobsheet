"""Colour themes for the generated workbook.

Themes are data, not code, so the user interface can offer presets *and* a custom
picker without either side knowing about the other. A theme only ever describes
chrome -- header, links, gridline-ish zebra banding. Row colouring driven by
meaning (applied, rejected) belongs to `ConditionalRule` in `layout.py`, because
that is about the data rather than the decoration.

Colours are ARGB strings because that is what openpyxl expects. Users think in
six hex digits, so both forms are accepted on the way in.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = ["DEFAULT_THEME", "THEMES", "ExcelTheme", "resolve_theme"]

_HEX = r"^(FF)?[0-9A-Fa-f]{6}$"


def _argb(value: str) -> str:
    value = value.upper()
    return value if len(value) == 8 else f"FF{value}"


class ExcelTheme(BaseModel):
    """The chrome of a sheet: header, link and banding colours."""

    model_config = ConfigDict(extra="forbid")

    name: str
    header_fill: str = Field(pattern=_HEX)
    header_text: str = Field(default="FFFFFF", pattern=_HEX)
    link_text: str = Field(default="0563C1", pattern=_HEX)
    zebra_fill: str = Field(default="F2F2F2", pattern=_HEX)

    @field_validator("header_fill", "header_text", "link_text", "zebra_fill")
    @classmethod
    def _normalise(cls, value: str) -> str:
        return _argb(value)

    @property
    def is_dark_header(self) -> bool:
        """Whether white header text will actually be readable.

        Relative luminance per WCAG, so a user who picks a pale custom header
        does not end up with white-on-cream. The writer flips the header text to
        near-black when this is False.
        """
        red, green, blue = (int(self.header_fill[i : i + 2], 16) / 255 for i in (2, 4, 6))
        channels = [
            c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in (red, green, blue)
        ]
        luminance = 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
        return luminance < 0.45


THEMES: dict[str, ExcelTheme] = {
    "navy": ExcelTheme(name="Navy", header_fill="1F3864", zebra_fill="F2F5FA"),
    "slate": ExcelTheme(name="Slate", header_fill="334155", zebra_fill="F1F5F9"),
    "forest": ExcelTheme(name="Forest", header_fill="1B4332", zebra_fill="EFF6F1"),
    "plum": ExcelTheme(name="Plum", header_fill="4C1D95", zebra_fill="F5F1FE"),
    "mono": ExcelTheme(name="Mono", header_fill="111111", link_text="333333", zebra_fill="F5F5F5"),
    "contrast": ExcelTheme(
        name="High contrast", header_fill="000000", link_text="0000EE", zebra_fill="FFFFFF"
    ),
}

DEFAULT_THEME = "navy"


def resolve_theme(theme: str | ExcelTheme | None) -> ExcelTheme:
    """Accept a preset name, a full custom theme, or nothing.

    An unknown name falls back to the default rather than raising: a layout
    shared by someone running a newer version must still open here.
    """
    if isinstance(theme, ExcelTheme):
        return theme
    return THEMES.get(str(theme or DEFAULT_THEME), THEMES[DEFAULT_THEME])
