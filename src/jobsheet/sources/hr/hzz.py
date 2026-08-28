"""Croatian Employment Service (HZZ) -- Burza rada.

The national employment service publishes one static RSS feed per county. It is
the broadest source of vacancies in Croatia, and also the most awkward:

* the feed is **iso-8859-2**, and says so nowhere useful
* titles, employers and place names are in ALL CAPITALS
* entities are escaped more than once, so a non-breaking space arrives as
  `&AMP;AMP;NBSP;`
* the whole structured record is flattened into one `<description>` string
* the feed numbers are **HZZ's own alphabetical index, not the official county
  codes**, which is the single easiest thing to get wrong here

The listing has no employer, contract type or education level, so those come
from a second request per ad -- run only for ads that already passed the keyword
filter, and capped, because this is a small public server.
"""

from __future__ import annotations

import re
from typing import Any

from jobsheet.core.dates import parse_date
from jobsheet.core.models import Posting
from jobsheet.data.places_hr import COUNTIES
from jobsheet.sources._parse import labelled_fields, parse_feed, strip_html
from jobsheet.sources.base import (
    Choice,
    FetchContext,
    ParamSpec,
    Phase,
    Source,
    SourceManifest,
)

__all__ = ["COUNTIES", "HzzSource"]

FEED = "https://burzarada.hzz.hr/rss/rsszup{number}.xml"
ENCODING = "iso-8859-2"

# The feed numbers are HZZ's own alphabetical index and NOT the official county
# codes -- Karlovačka is officially 04 but feed 6 here. The table itself lives in
# `jobsheet.data.places_hr`, where the wizard can reach it without importing a
# source; feeds 4, 6 and 21 were verified against live data on 2026-08-24.

# The labels HZZ flattens into the description, in its own wording.
_FEED_LABELS = ("Opis posla", "Kategorija", "Rok za prijavu", "Mjesto rada", "Općina", "Županija")

# The labels on an individual ad's page.
_DETAIL_LABELS = (
    "Mjesto rada",
    "Vrsta zaposlenja",
    "Radno vrijeme",
    "Način rada",
    "Natječaj vrijedi od",
    "Natječaj vrijedi do",
    "Razina obrazovanja",
    "Radno iskustvo",
    "Poslodavac",
)

_TAGS = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


class HzzSource(Source):
    manifest = SourceManifest(
        id="hzz",
        name="HZZ Burza rada",
        homepage="https://burzarada.hzz.hr/",
        description="Every vacancy registered with the Croatian Employment Service, by county.",
        country="HR",
        rate_limit=0.8,
        supports_enrich=True,
        params=[
            ParamSpec(
                name="counties",
                label="Counties",
                kind="multiselect",
                required=True,
                default=[4],
                choices=[Choice(value=str(n), label=name) for n, name in COUNTIES.items()],
                help="Each county is a separate feed. Pick only the ones you would work in.",
            ),
        ],
    )

    async def fetch(self, params: dict[str, Any], ctx: FetchContext) -> list[Posting]:
        chosen = _as_numbers(self.param(params, "counties"))
        postings: list[Posting] = []

        # One step per county rather than one for the whole source: HZZ is the
        # slowest thing JobSheet does, and a bar that sits still for twenty
        # counties looks like a hang.
        for index, number in enumerate(chosen):
            ctx.step("hzz", Phase.FETCHING, index + 1, len(chosen))
            name = COUNTIES.get(number, str(number))
            try:
                text = await ctx.http.get_text(FEED.format(number=number), encoding=ENCODING)
            except Exception as error:
                ctx.report(f"  ! HZZ {name}: could not be read ({type(error).__name__})")
                continue

            found = 0
            for item in parse_feed(text):
                if not item.link:
                    continue
                fields = labelled_fields(item.description, _FEED_LABELS)
                postings.append(
                    Posting(
                        source_id="hzz",
                        title=item.title,
                        # The feed still advertises http; the site is https.
                        url=item.link.replace("http://", "https://", 1),
                        description=fields.get("Opis posla", item.description),
                        location=fields.get("Mjesto rada", ""),
                        region=fields.get("Županija", name),
                        posted_at=item.published,
                        deadline=parse_date(fields.get("Rok za prijavu", "")),
                        raw={
                            # Kept for reference but never matched against: HZZ
                            # staples very broad categories onto ads, so matching
                            # them turns a bricklayer into a surveyor.
                            "source_category": fields.get("Kategorija", ""),
                            "municipality": fields.get("Općina", ""),
                            "county_feed": number,
                        },
                    )
                )
                found += 1
                if len(postings) >= ctx.max_items:
                    break

            ctx.report(f"  HZZ {name}: {found}")
            if len(postings) >= ctx.max_items:
                break

        return postings

    async def enrich(self, posting: Posting, ctx: FetchContext) -> Posting:
        """Open one ad's page for the employer, contract type and education level.

        Returns the posting untouched on any failure. Losing these fields costs
        the user a little context; losing the ad costs them an opportunity.
        """
        try:
            page = await ctx.http.get_text(posting.url)
        except Exception:
            return posting

        lines = [line.strip() for line in _TAGS.sub("\n", page).splitlines()]
        lines = [strip_html(line) for line in lines if line.strip()]

        fields: dict[str, str] = {}
        for index, line in enumerate(lines):
            # A trailing colon is what separates a field label from a section
            # heading; without this check the heading is read as a label.
            if not line.endswith(":"):
                continue
            label = line[:-1].strip()
            if label in _DETAIL_LABELS and label not in fields and index + 1 < len(lines):
                fields[label] = _WHITESPACE.sub(" ", lines[index + 1]).strip()

        notes = _between(lines, "Ostale informacije:", "Poslodavac")

        updates: dict[str, Any] = {
            "company": fields.get("Poslodavac", "") or posting.company,
            "employment_type": fields.get("Vrsta zaposlenja", ""),
            "education": fields.get("Razina obrazovanja", ""),
            "location": fields.get("Mjesto rada", "") or posting.location,
            "raw": {
                **posting.raw,
                "schedule": fields.get("Način rada", ""),
                "hours": fields.get("Radno vrijeme", ""),
                "experience": fields.get("Radno iskustvo", ""),
                "notes": notes,
            },
        }
        if deadline := parse_date(fields.get("Natječaj vrijedi do", "")):
            updates["deadline"] = deadline
        if published := parse_date(fields.get("Natječaj vrijedi od", "")):
            updates["posted_at"] = published
        if not posting.title and (title := _before(lines, "Radno mjesto")):
            # A few feed items ship an empty <title>; the ad page is then the
            # only place the job title exists.
            updates["title"] = title

        return posting.model_copy(update=updates)


def _as_numbers(value: Any) -> list[int]:
    if value is None:
        return [4]
    if isinstance(value, int):
        return [value]
    numbers: list[int] = []
    for item in value if isinstance(value, list | tuple) else [value]:
        try:
            numbers.append(int(item))
        except (TypeError, ValueError):
            continue
    return numbers or [4]


def _between(lines: list[str], start: str, end: str) -> str:
    try:
        first = lines.index(start) + 1
        last = next(i for i in range(first, len(lines)) if lines[i] == end)
    except (ValueError, StopIteration):
        return ""
    return _WHITESPACE.sub(" ", " ".join(lines[first:last])).strip()


def _before(lines: list[str], marker: str) -> str:
    try:
        position = lines.index(marker)
    except ValueError:
        return ""
    return lines[position - 1] if position > 0 else ""
