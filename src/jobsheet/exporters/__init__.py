"""Ways out of JobSheet that are not the workbook.

The workbook is the main event; these are for everything else -- a CSV for the
importer at the other end, JSON for a script, a letter draft for the application
itself.
"""

from __future__ import annotations

from jobsheet.exporters.csv import to_csv
from jobsheet.exporters.jsonl import to_json, to_jsonl, to_records
from jobsheet.exporters.letter import Applicant, LetterError, render_letter

__all__ = [
    "Applicant",
    "LetterError",
    "render_letter",
    "to_csv",
    "to_json",
    "to_jsonl",
    "to_records",
]
