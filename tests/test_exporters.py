"""The ways out that are not the workbook."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from jobsheet.core.models import ApplicationStatus, Posting, Workplace
from jobsheet.exporters.csv import BOM, to_csv
from jobsheet.exporters.jsonl import to_json, to_jsonl, to_records
from jobsheet.exporters.letter import (
    DEFAULT_TEMPLATE,
    Applicant,
    LetterError,
    load_template,
    render_letter,
)
from jobsheet.sheet.layout import ColumnKind, ColumnSpec, SheetLayout, default_layout
from jobsheet.sheet.row import JobRow

FOUND = date(2026, 8, 24)


def posting(number: int = 1, **overrides: Any) -> Posting:
    data: dict[str, Any] = {
        "source_id": "rss",
        "title": f"GIS Engineer {number}",
        "url": f"https://example.test/j/{number}",
        "company": "Kartograf d.o.o.",
        "location": "Rijeka",
        "posted_at": date(2026, 8, 1),
        "deadline": date(2026, 9, 1),
        "tags": ("gis", "python"),
        "workplace": Workplace.HYBRID,
    }
    return Posting(**(data | overrides))


def job(number: int = 1, **overrides: Any) -> JobRow:
    data: dict[str, Any] = {
        "posting": posting(number),
        "found_at": FOUND,
        "category": "GIS",
        "note": "matched \"gis\" in the title",
    }
    return JobRow(**(data | overrides))


# ------------------------------------------------------------------------ CSV


class TestCsv:
    def test_the_header_is_the_users_own_labels(self) -> None:
        layout = SheetLayout(
            columns=[
                ColumnSpec(key="title", label="Role"),
                ColumnSpec(key="company", label="Firm"),
            ]
        )
        assert to_csv([job()], layout, bom=False).splitlines()[0] == "Role,Firm"

    def test_a_hidden_column_order_is_respected(self) -> None:
        """Whatever the designer arranged is what comes out."""
        layout = SheetLayout(
            columns=[
                ColumnSpec(key="company", label="Firm"),
                ColumnSpec(key="title", label="Role"),
            ]
        )
        assert to_csv([job()], layout, bom=False).splitlines()[1].startswith("Kartograf")

    def test_dates_are_iso_not_whatever_excel_decides(self) -> None:
        layout = SheetLayout(columns=[ColumnSpec(key="posted_at", label="Posted")])
        assert to_csv([job()], layout, bom=False).splitlines()[1] == "2026-08-01"

    def test_a_missing_date_is_an_empty_cell(self) -> None:
        layout = SheetLayout(
            columns=[
                ColumnSpec(key="title", label="Role"),
                ColumnSpec(key="deadline", label="Closes"),
            ]
        )
        row = job(posting=posting(deadline=None))
        assert to_csv([row], layout, bom=False).splitlines()[1] == "GIS Engineer 1,"

    def test_a_tick_reads_as_true_and_an_untick_as_nothing(self) -> None:
        """"FALSE" in every empty cell is noise; spreadsheets read blank as false."""
        layout = SheetLayout(
            columns=[
                ColumnSpec(key="title", label="Role"),
                ColumnSpec(key="applied", label="Applied", kind=ColumnKind.CHECKBOX),
            ]
        )
        ticked = to_csv([job(user_values={"applied": True})], layout, bom=False)
        unticked = to_csv([job(user_values={"applied": False})], layout, bom=False)

        assert ticked.splitlines()[1].endswith(",TRUE")
        assert unticked.splitlines()[1].endswith(",")

    def test_tags_are_joined(self) -> None:
        layout = SheetLayout(columns=[ColumnSpec(key="tags", label="Tags", kind=ColumnKind.TAGS)])
        assert "gis, python" in to_csv([job()], layout, bom=False)

    def test_a_user_column_carries_whatever_was_typed_there(self) -> None:
        layout = SheetLayout(columns=[ColumnSpec(key="Who", label="Who")])
        row = job(user_values={"Who": "Ana"})
        assert to_csv([row], layout, bom=False).splitlines()[1] == "Ana"

    def test_commas_in_a_value_do_not_break_the_row(self) -> None:
        layout = SheetLayout(columns=[ColumnSpec(key="company", label="Firm")])
        row = job(posting=posting(company="Kartograf, Geodezija i partneri"))
        assert '"Kartograf, Geodezija i partneri"' in to_csv([row], layout, bom=False)

    def test_it_leads_with_a_bom_by_default(self) -> None:
        """Without it, Windows Excel mangles every accented character."""
        assert to_csv([job()]).startswith(BOM)

    def test_accents_survive(self) -> None:
        row = job(posting=posting(company="Građevinar d.o.o."))
        assert "Građevinar" in to_csv([row], default_layout())

    def test_no_rows_still_produces_a_header(self) -> None:
        assert to_csv([], default_layout(), bom=False).strip().count("\n") == 0

    def test_a_semicolon_delimiter_is_available(self) -> None:
        """Croatian and German Excel installs expect one."""
        layout = SheetLayout(
            columns=[ColumnSpec(key="title", label="Role"), ColumnSpec(key="company", label="Firm")]
        )
        assert to_csv([job()], layout, delimiter=";", bom=False).splitlines()[0] == "Role;Firm"


# ----------------------------------------------------------------------- JSON


class TestJson:
    def test_a_record_carries_the_key_the_api_addresses_it_by(self) -> None:
        assert to_records([job()])[0]["dedup_key"] == job().dedup_key

    def test_the_whole_posting_is_there_regardless_of_the_layout(self) -> None:
        """A hidden column is a display choice, not a decision to drop the data."""
        record = to_records([job()])[0]
        assert record["workplace"] == "hybrid"
        assert record["tags"] == ["gis", "python"]

    def test_the_users_side_is_there_too(self) -> None:
        row = job(status=ApplicationStatus.APPLIED, user_values={"Rating": 5})
        record = to_records([row])[0]
        assert record["status"] == "applied"
        assert record["user_values"] == {"Rating": 5}

    def test_dates_are_strings(self) -> None:
        record = to_records([job()])[0]
        assert record["posted_at"] == "2026-08-01"
        assert record["found_at"] == "2026-08-24"

    def test_json_parses_back(self) -> None:
        assert len(json.loads(to_json([job(1), job(2)]))) == 2

    def test_jsonl_is_one_object_per_line(self) -> None:
        lines = to_jsonl([job(1), job(2)]).splitlines()
        assert len(lines) == 2
        assert all(json.loads(line)["dedup_key"] for line in lines)

    def test_jsonl_of_nothing_is_empty_rather_than_a_blank_line(self) -> None:
        assert to_jsonl([]) == ""

    def test_accents_are_not_escaped_into_gibberish(self) -> None:
        row = job(posting=posting(company="Građevinar d.o.o."))
        assert "Građevinar" in to_json([row])


# --------------------------------------------------------------------- letter


class TestLetter:
    def test_it_names_the_job_and_the_applicant(self) -> None:
        text = render_letter(job(), Applicant(name="Ana Horvat", email="ana@example.test"))
        assert "GIS Engineer 1" in text
        assert "Kartograf d.o.o." in text
        assert "Ana Horvat" in text
        assert "ana@example.test" in text

    def test_a_missing_company_does_not_leave_a_gap(self) -> None:
        text = render_letter(job(posting=posting(company="")))
        assert "To whom it may concern" in text
        assert " at ," not in text

    def test_the_closing_date_is_mentioned_when_there_is_one(self) -> None:
        assert "2026-09-01" in render_letter(job())

    def test_no_closing_date_means_no_sentence_about_one(self) -> None:
        text = render_letter(job(posting=posting(deadline=None)))
        assert "closing date" not in text

    def test_a_reference_number_is_quoted_back(self) -> None:
        """Public-sector employers expect to see their own ad number."""
        row = job(posting=posting(raw={"reference": "112-01/26-01/33"}))
        assert "112-01/26-01/33" in render_letter(row)

    def test_a_custom_template_replaces_the_builtin(self) -> None:
        text = render_letter(job(), template="{{ title }} at {{ company }}")
        assert text == "GIS Engineer 1 at Kartograf d.o.o."

    def test_a_template_on_disk_is_picked_up(self, tmp_path: Path) -> None:
        (tmp_path / "letter.txt").write_text("Re: {{ title }}", encoding="utf-8")
        assert render_letter(job(), template_dir=tmp_path) == "Re: GIS Engineer 1"

    def test_without_one_on_disk_the_builtin_is_used(self, tmp_path: Path) -> None:
        assert load_template(tmp_path) == DEFAULT_TEMPLATE

    def test_a_syntax_error_names_the_line(self) -> None:
        with pytest.raises(LetterError, match="line"):
            render_letter(job(), template="{% for %}")

    def test_an_unknown_variable_is_an_error_not_a_blank(self) -> None:
        """Silently rendering an empty space is how a letter goes out half-written."""
        with pytest.raises(LetterError):
            render_letter(job(), template="Dear {{ nobody_defined }}")

    def test_a_template_cannot_reach_into_python(self) -> None:
        """Templates get shared between people; the sandbox is not optional."""
        with pytest.raises(LetterError):
            render_letter(job(), template="{{ applicant.__class__.__mro__ }}")

    def test_extra_fields_are_available_to_a_custom_template(self) -> None:
        applicant = Applicant(name="Ana", extra={"portfolio": "https://ana.test"})
        assert render_letter(job(), applicant, template="{{ portfolio }}") == "https://ana.test"

    def test_the_date_can_be_pinned(self) -> None:
        assert "2026-08-24" in render_letter(job(), today=FOUND)
