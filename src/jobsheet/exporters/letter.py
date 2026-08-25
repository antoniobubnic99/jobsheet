"""A first draft of a covering letter, filled in from the ad.

This is a template engine, not a writer. JobSheet does not call a language model
and does not pretend the result is finished prose -- it fills in the parts that
are mechanical (who, what, where, which reference number) so the user starts
from a page with their name on it rather than from nothing.

The default template is deliberately plain and deliberately short. Anyone who
wants their own voice puts a `letter.txt` next to their workbook and it is used
instead; that file is Jinja2, with the same variables documented below.

Sandboxed on purpose: a template is a file on disk, but it may well have been
downloaded from someone else, and a template language that can reach into Python
attributes is a template language that can read your filesystem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from jinja2 import BaseLoader, StrictUndefined, TemplateSyntaxError
from jinja2.sandbox import SandboxedEnvironment

from jobsheet.sheet.row import JobRow

__all__ = ["DEFAULT_TEMPLATE", "Applicant", "LetterError", "render_letter", "template_context"]

TEMPLATE_FILENAME = "letter.txt"

DEFAULT_TEMPLATE = """\
{{ applicant.name }}
{% if applicant.email %}{{ applicant.email }}
{% endif %}{% if applicant.phone %}{{ applicant.phone }}
{% endif %}
{{ today }}

{% if company %}{{ company }}{% else %}To whom it may concern{% endif %}

Subject: Application for {{ title }}{% if reference %} (ref. {{ reference }}){% endif %}

Dear Sir or Madam,

I am writing to apply for the position of {{ title }}\
{% if company %} at {{ company }}{% endif %}\
{% if location %}, based in {{ location }}{% endif %}\
, which I saw advertised on {{ source }}.

{{ applicant.pitch }}

{% if deadline %}I am submitting this before the closing date of {{ deadline }}.
{% endif %}I would welcome the opportunity to discuss my application further, and I
have attached my CV for your consideration.

Yours faithfully,
{{ applicant.name }}
"""


class LetterError(RuntimeError):
    """The template could not be rendered."""


@dataclass
class Applicant:
    """The half of the letter that comes from the user, not from the ad."""

    name: str = "Your Name"
    email: str = ""
    phone: str = ""
    pitch: str = (
        "My background matches what the role asks for, and I would bring that "
        "experience to your team from day one."
    )
    extra: dict[str, Any] = field(default_factory=dict)


def template_context(
    row: JobRow, applicant: Applicant, *, today: date | None = None
) -> dict[str, Any]:
    """Every variable a template may use. Documented in `docs/`, so keep it stable."""
    posting = row.posting
    return {
        "applicant": applicant,
        "today": (today or date.today()).isoformat(),
        "title": posting.title,
        "company": posting.company,
        "location": posting.location,
        "region": posting.region,
        "url": posting.url,
        "source": posting.source_id,
        "workplace": str(posting.workplace),
        "employment_type": posting.employment_type,
        "education": posting.education,
        "salary": posting.salary,
        "description": posting.description,
        "tags": list(posting.tags),
        "category": row.category,
        "note": row.note,
        "posted_at": posting.posted_at.isoformat() if posting.posted_at else "",
        "deadline": posting.deadline.isoformat() if posting.deadline else "",
        # Public-sector ads are referenced by a number the employer expects to
        # see quoted back; sources stash it in `raw` under various names.
        "reference": str(
            posting.raw.get("reference")
            or posting.raw.get("ad_number")
            or posting.raw.get("id")
            or ""
        ),
        **applicant.extra,
    }


def load_template(directory: Path | str | None) -> str:
    """The user's own template if they wrote one, otherwise the built-in."""
    if directory is None:
        return DEFAULT_TEMPLATE
    candidate = Path(directory) / TEMPLATE_FILENAME
    if candidate.is_file():
        return candidate.read_text(encoding="utf-8")
    return DEFAULT_TEMPLATE


def render_letter(
    row: JobRow,
    applicant: Applicant | None = None,
    *,
    template: str | None = None,
    template_dir: Path | str | None = None,
    today: date | None = None,
) -> str:
    """Fill the template in from one job. Raises `LetterError` on a bad template."""
    source = template if template is not None else load_template(template_dir)
    environment = SandboxedEnvironment(
        loader=BaseLoader(),
        undefined=StrictUndefined,
        trim_blocks=False,
        keep_trailing_newline=True,
    )
    context = template_context(row, applicant or Applicant(), today=today)
    try:
        return environment.from_string(source).render(context)
    except TemplateSyntaxError as error:
        raise LetterError(f"line {error.lineno}: {error.message}") from error
    except Exception as error:  # undefined variables, bad filters, sandbox blocks
        raise LetterError(str(error)) from error
