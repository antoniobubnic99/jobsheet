"""The spreadsheet schema the user owns.

The predecessor hard-coded nine columns and then repeated that assumption in
seven places: the header list, the width list, `range(1, 10)`, the slice
`vals[:6]`, the autofilter reference `A1:I{n}`, the conditional-formatting range
`A2:I500`, and the tuple of checkbox columns `("G", "H", "I")`. Adding a column
meant editing all seven in lockstep, and forgetting one produced a workbook that
looked fine and quietly misbehaved -- the conditional formatting really did stop
at row 500 while the writer happily wrote to row 5000.

Here there is one object. Everything else is derived from it.

The distinction that matters most is `user_owned`. A user-owned column holds the
user's own knowledge -- did I apply, what did they say, my note to self -- and the
writer treats those values as read-only input: it carries them across a rewrite,
counts them before and after, and rolls the whole file back if the counts differ.
Source-owned columns are refreshed from the feed on every run.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "SOURCE_KEYS",
    "ColumnKind",
    "ColumnSpec",
    "ConditionalRule",
    "SheetLayout",
    "classic_checkboxes_layout",
    "default_layout",
    "minimal_layout",
]


class ColumnKind(StrEnum):
    """How a cell is written and read back.

    This drives cell formatting, the checkbox post-processing pass, the data
    validation dropdown for statuses, and how a value is parsed on the way back
    in -- so it is a data question, not a cosmetic one.
    """

    TEXT = "text"
    NOTE = "note"          # long free text; wraps by default
    DATE = "date"
    URL = "url"            # written as a real hyperlink
    NUMBER = "number"
    TAGS = "tags"          # a list, joined for display
    CHECKBOX = "checkbox"  # boolean, rendered as a native Excel checkbox
    STATUS = "status"      # constrained text with a dropdown


# Column keys the app knows how to fill from a posting. Anything else is a custom
# column: the app creates it, never writes to it, and preserves whatever the user
# types there.
SOURCE_KEYS: frozenset[str] = frozenset(
    {
        "found_at",
        "posted_at",
        "deadline",
        "title",
        "company",
        "url",
        "location",
        "region",
        "workplace",
        "employment_type",
        "education",
        "salary",
        "category",
        "note",
        "source",
        "tags",
    }
)


class ColumnSpec(BaseModel):
    """One column, exactly as the user arranged it."""

    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    kind: ColumnKind = ColumnKind.TEXT
    width: float = Field(default=18.0, gt=0, le=255)
    wrap: bool = False

    # True for anything the app must never overwrite: checkboxes, the status
    # column, and every custom column the user adds for their own notes.
    user_owned: bool = False

    @field_validator("key")
    @classmethod
    def _key_is_usable(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("column key must not be empty")
        return value

    @field_validator("label")
    @classmethod
    def _label_is_usable(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("column label must not be empty")
        return value

    @model_validator(mode="after")
    def _infer_ownership(self) -> ColumnSpec:
        """Checkboxes, statuses and unknown keys are the user's, by definition."""
        if self.kind in (ColumnKind.CHECKBOX, ColumnKind.STATUS) or self.key not in SOURCE_KEYS:
            object.__setattr__(self, "user_owned", True)
        return self


class ConditionalRule(BaseModel):
    """Colour a whole row when one column holds a given value.

    Rules are applied in order and the first `stop_if_true` match wins, which is
    how "rejected greys out the row even though I did apply" is expressed.
    """

    model_config = ConfigDict(extra="forbid")

    when_column: str
    equals: str | bool
    fill: str = Field(pattern=r"^(FF)?[0-9A-Fa-f]{6}$")
    stop_if_true: bool = False

    @property
    def argb(self) -> str:
        """Excel wants eight hex digits; users think in six."""
        value = self.fill.upper()
        return value if len(value) == 8 else f"FF{value}"


class SheetLayout(BaseModel):
    """A complete, shareable description of the workbook the user wants."""

    model_config = ConfigDict(extra="forbid")

    sheet_name: str = "Jobs"
    columns: list[ColumnSpec]
    theme: str = "navy"
    freeze_header: bool = True
    autofilter: bool = True
    zebra: bool = False
    rules: list[ConditionalRule] = Field(default_factory=list)

    # Sorted as whole row objects, never by rewriting cells column by column --
    # that mistake is what destroyed 88 of the user's ticks in the predecessor.
    sort_by: list[str] = Field(default_factory=lambda: ["posted_at", "company"])
    sort_descending: bool = True

    @field_validator("columns")
    @classmethod
    def _columns_are_sane(cls, value: list[ColumnSpec]) -> list[ColumnSpec]:
        if not value:
            raise ValueError("a layout needs at least one column")
        keys = [c.key for c in value]
        if len(keys) != len(set(keys)):
            duplicates = sorted({k for k in keys if keys.count(k) > 1})
            raise ValueError(f"duplicate column keys: {', '.join(duplicates)}")
        labels = [c.label.casefold() for c in value]
        if len(labels) != len(set(labels)):
            # Headers double as the fallback when matching a workbook the user
            # has rearranged by hand, so they have to stay distinguishable.
            repeats = sorted({left for left in labels if labels.count(left) > 1})
            raise ValueError(f"duplicate column labels: {', '.join(repeats)}")
        return value

    @model_validator(mode="after")
    def _rules_point_at_real_columns(self) -> SheetLayout:
        known = {c.key for c in self.columns}
        for rule in self.rules:
            if rule.when_column not in known:
                raise ValueError(f"rule refers to unknown column: {rule.when_column}")
        return self

    def index_of(self, key: str) -> int | None:
        """1-based column index, as Excel counts. `None` when the key is absent."""
        for position, column in enumerate(self.columns, start=1):
            if column.key == key:
                return position
        return None

    @property
    def user_owned_keys(self) -> tuple[str, ...]:
        return tuple(c.key for c in self.columns if c.user_owned)

    @property
    def checkbox_keys(self) -> tuple[str, ...]:
        return tuple(c.key for c in self.columns if c.kind is ColumnKind.CHECKBOX)


# --------------------------------------------------------------------- presets


def default_layout() -> SheetLayout:
    """What a new user gets: one status column instead of three booleans."""
    return SheetLayout(
        sheet_name="Jobs",
        theme="navy",
        columns=[
            ColumnSpec(key="found_at", label="Found", kind=ColumnKind.DATE, width=13),
            ColumnSpec(key="company", label="Company", width=28),
            ColumnSpec(key="title", label="Position", width=36),
            ColumnSpec(key="url", label="Link", kind=ColumnKind.URL, width=42),
            ColumnSpec(key="location", label="Location", width=20),
            ColumnSpec(key="deadline", label="Deadline", kind=ColumnKind.DATE, width=13),
            ColumnSpec(key="category", label="Category", width=18),
            ColumnSpec(key="status", label="Status", kind=ColumnKind.STATUS, width=14),
            ColumnSpec(key="note", label="Notes", kind=ColumnKind.NOTE, width=50, wrap=True),
            ColumnSpec(key="my_notes", label="My notes", kind=ColumnKind.NOTE, width=36, wrap=True),
        ],
        rules=[
            ConditionalRule(
                when_column="status", equals="rejected", fill="D9D9D9", stop_if_true=True
            ),
            ConditionalRule(
                when_column="status", equals="skipped", fill="D9D9D9", stop_if_true=True
            ),
            ConditionalRule(when_column="status", equals="offer", fill="FFE699"),
            ConditionalRule(when_column="status", equals="interview", fill="BDD7EE"),
            ConditionalRule(when_column="status", equals="applied", fill="C6EFCE"),
        ],
    )


def classic_checkboxes_layout() -> SheetLayout:
    """The predecessor's nine columns, tick boxes and colours, preserved exactly.

    Kept as a first-class preset so the original user's workflow survives the
    generalisation unchanged -- including grey (did not apply) taking priority
    over green (applied) via `stop_if_true`.
    """
    return SheetLayout(
        sheet_name="Jobs",
        theme="navy",
        columns=[
            ColumnSpec(key="found_at", label="Found", kind=ColumnKind.DATE, width=16),
            ColumnSpec(key="company", label="Company", width=26),
            ColumnSpec(key="title", label="Position", width=34),
            ColumnSpec(key="url", label="Link", kind=ColumnKind.URL, width=46),
            ColumnSpec(key="category", label="Category", width=18),
            ColumnSpec(key="note", label="Notes", kind=ColumnKind.NOTE, width=52, wrap=True),
            ColumnSpec(key="applied", label="Applied", kind=ColumnKind.CHECKBOX, width=12),
            ColumnSpec(key="interview", label="Interview", kind=ColumnKind.CHECKBOX, width=18),
            ColumnSpec(key="not_applied", label="Not applied", kind=ColumnKind.CHECKBOX, width=18),
        ],
        rules=[
            ConditionalRule(
                when_column="not_applied", equals=True, fill="D9D9D9", stop_if_true=True
            ),
            ConditionalRule(when_column="applied", equals=True, fill="C6EFCE"),
        ],
    )


def minimal_layout() -> SheetLayout:
    """Four columns, no colour. For people who want a list, not a system."""
    return SheetLayout(
        sheet_name="Jobs",
        theme="mono",
        columns=[
            ColumnSpec(key="found_at", label="Found", kind=ColumnKind.DATE, width=13),
            ColumnSpec(key="company", label="Company", width=30),
            ColumnSpec(key="title", label="Position", width=40),
            ColumnSpec(key="url", label="Link", kind=ColumnKind.URL, width=46),
        ],
    )
