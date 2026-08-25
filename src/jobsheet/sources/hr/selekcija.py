"""Selekcija.gov.hr -- Croatian central civil-service recruitment.

The public site is an Angular application, but the Rhetos REST backend beneath it
serves published competitions without a login or a key (verified 2026-08-24). The
backend address is discoverable at `selekcija.gov.hr/assets/environment.json`
under `rhetos.url`, which is where to look if it ever moves.

Two things here are easy to get wrong and both were paid for:

* **`ZupanijaNaziv` is the publishing authority's seat, not the workplace.** On
  2026-08-24, 149 of 558 listings (27%) named the capital while the work was in
  Split, Osijek or on an island. Only `MjestoRada` says where the job is.
* **Dates are .NET `/Date(ms+hhmm)/`.** Dropping the offset moves every
  publication date back by a day.
* **The envelope is not stable.** Rhetos answered with a bare JSON array until
  some point before 2026-08-25, and with `{"Records": [...]}` after. Both are
  accepted here, because a wrapper appearing again is far cheaper to tolerate
  than to notice: the source simply returns nothing and no request fails.

There is no per-advert URL, so the link points at the list page with the
competition code, which is what a person would use to find it by hand.
"""

from __future__ import annotations

import json
import urllib.parse
from datetime import timedelta
from typing import Any

from jobsheet.core.dates import parse_date
from jobsheet.core.models import Posting
from jobsheet.sources._parse import strip_html
from jobsheet.sources.base import (
    FetchContext,
    ParamSpec,
    Source,
    SourceError,
    SourceManifest,
)

__all__ = ["SelekcijaSource"]

REST = "https://selekcija.gov.hr/MPUCSZ_Backend_Prod/rest/Natjecaji"
PUBLIC_LIST = "https://selekcija.gov.hr/natjecaji/objavljeni-natjecaji"


def _endpoint(entity: str, since: str) -> str:
    filters = json.dumps(
        [
            {
                "Property": "DatumObjaveNatjecaja",
                "Operation": "GreaterEqual",
                "Value": f"{since}T00:00:00",
            }
        ]
    )
    query = urllib.parse.urlencode({"filters": filters, "sort": "DatumObjaveNatjecaja desc"})
    return f"{REST}/{entity}/?{query}"


def _records(payload: Any) -> list[dict[str, Any]] | None:
    """The rows out of whichever envelope Rhetos used this time.

    Returns None when the payload is neither shape, so the caller can tell
    "no results" apart from "we no longer understand the answer".
    """
    if isinstance(payload, dict):
        payload = payload.get("Records")
    if not isinstance(payload, list):
        return None
    return [row for row in payload if isinstance(row, dict)]


class SelekcijaSource(Source):
    manifest = SourceManifest(
        id="selekcija",
        name="Selekcija.gov.hr",
        homepage="https://selekcija.gov.hr/natjecaji/objavljeni-natjecaji",
        description="Public competitions for Croatian civil-service posts.",
        country="HR",
        rate_limit=1.0,
        params=[
            ParamSpec(
                name="days",
                label="How far back to look",
                kind="number",
                default=45,
                help=(
                    "These competitions always state a deadline, so a wider window "
                    "does not drag in closed ones -- expired ones are filtered out."
                ),
            ),
        ],
    )

    async def fetch(self, params: dict[str, Any], ctx: FetchContext) -> list[Posting]:
        days = max(1, int(self.param(params, "days") or 45))
        since = (ctx.today - timedelta(days=days)).isoformat()

        ctx.report("Reading Selekcija.gov.hr")
        listing = _records(await ctx.http.get_json(_endpoint("ObjavljeniNatjecajiList", since)))
        if listing is None:
            raise SourceError("Selekcija returned no competition list")

        # A second request carries the job description. Joined on ID rather than
        # fetched per advert, so this stays two requests however many results.
        details: dict[str, dict[str, Any]] = {}
        try:
            detail_rows = _records(await ctx.http.get_json(_endpoint("NatjecajDetail", since)))
            if detail_rows is not None:
                details = {row.get("ID", ""): row for row in detail_rows}
        except Exception as error:
            ctx.report(f"  ! Selekcija details unavailable ({type(error).__name__})")

        postings: list[Posting] = []
        for row in listing[: ctx.max_items]:
            title = row.get("RadnoMjestoNaziv") or ""
            code = row.get("SifraNatjecaja") or ""
            if not title or not code:
                continue

            detail = details.get(row.get("ID", ""), {})
            workplace = detail.get("LokacijaRadnogMjesta") or row.get("MjestoRada") or ""

            postings.append(
                Posting(
                    source_id="selekcija",
                    title=title,
                    # No per-advert page exists; this is how a person finds it.
                    url=f"{PUBLIC_LIST}?sifra={urllib.parse.quote(str(code))}",
                    company=row.get("DrzavnoTijeloNaziv") or "",
                    location=workplace,
                    # Deliberately NOT ZupanijaNaziv -- see the module docstring.
                    region="",
                    description=strip_html(detail.get("OpisPoslova") or ""),
                    employment_type=row.get("VrstaRadnogOdnosa") or "",
                    education=row.get("StrucnaSprema") or "",
                    posted_at=parse_date(row.get("DatumObjaveNatjecaja")),
                    deadline=parse_date(
                        row.get("RokZaPrijavuISO8601") or row.get("RokZaPrijavu")
                    ),
                    raw={
                        "code": code,
                        "unit": row.get("UstrojstvenaJedinicaNaziv", ""),
                        "experience": detail.get("TrazeneGodineIskustva", ""),
                        "field": detail.get("Polje", ""),
                        # Kept for reference only: this is the authority's seat.
                        "authority_county": row.get("ZupanijaNaziv", ""),
                    },
                )
            )

        ctx.report(f"  {len(postings)} from Selekcija.gov.hr")
        return postings
