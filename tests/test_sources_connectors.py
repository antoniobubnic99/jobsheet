"""Every connector, against a recorded shape of its real response.

These are contract tests with the network taken out. The payloads are trimmed
copies of what each service actually returns, so a parser that stops matching
reality fails here rather than in a user's spreadsheet.

Live checks against the real endpoints live in `test_sources_live.py` and are
marked `network`, so they run nightly rather than on every push.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx
import pytest
import respx

from jobsheet.core.models import Workplace
from jobsheet.sources.ats.ashby import AshbySource
from jobsheet.sources.ats.greenhouse import GreenhouseSource
from jobsheet.sources.ats.lever import LeverSource
from jobsheet.sources.ats.recruitee import RecruiteeSource
from jobsheet.sources.ats.smartrecruiters import SmartRecruitersSource
from jobsheet.sources.ats.workable import WorkableSource
from jobsheet.sources.base import FetchContext, SourceError
from jobsheet.sources.boards.arbeitnow import ArbeitnowSource
from jobsheet.sources.boards.remoteok import RemoteOkSource
from jobsheet.sources.boards.remotive import RemotiveSource
from jobsheet.sources.hr.hzz import HzzSource
from jobsheet.sources.hr.narodne_novine import NarodneNovineSource
from jobsheet.sources.hr.posao_hr import PosaoHrSource
from jobsheet.sources.hr.selekcija import SelekcijaSource
from jobsheet.sources.rss import RssSource

# ------------------------------------------------------------------ generic RSS


FEED = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item><title>Data Analyst</title><link>https://example.test/j/1</link>
<description>Work with data</description>
<pubDate>Mon, 24 Aug 2026 09:15:00 +0200</pubDate></item>
</channel></rss>"""


class TestRss:
    @respx.mock
    async def test_reads_a_feed(self, ctx: FetchContext) -> None:
        respx.get("https://example.test/feed.xml").mock(
            return_value=httpx.Response(200, text=FEED)
        )
        found = await RssSource().fetch(
            {"url": "https://example.test/feed.xml", "label": "Example", "company": "Example Ltd"},
            ctx,
        )
        assert len(found) == 1
        assert found[0].title == "Data Analyst"
        assert found[0].company == "Example Ltd"
        assert found[0].source_id == "rss:Example"
        assert found[0].posted_at == date(2026, 8, 24)

    @respx.mock
    async def test_employer_is_left_empty_rather_than_guessed(self, ctx: FetchContext) -> None:
        """On a job board the feed's author is the board, not the hiring company."""
        respx.get("https://example.test/feed.xml").mock(
            return_value=httpx.Response(200, text=FEED)
        )
        found = await RssSource().fetch({"url": "https://example.test/feed.xml"}, ctx)
        assert found[0].company == ""

    async def test_missing_url_is_an_error(self, ctx: FetchContext) -> None:
        with pytest.raises(SourceError):
            await RssSource().fetch({}, ctx)

    @respx.mock
    async def test_a_page_that_is_not_a_feed(self, ctx: FetchContext) -> None:
        respx.get("https://example.test/feed.xml").mock(
            return_value=httpx.Response(200, text="<html>nope</html>")
        )
        with pytest.raises(SourceError):
            await RssSource().fetch({"url": "https://example.test/feed.xml"}, ctx)


# ------------------------------------------------------------------------ ATS


class TestGreenhouse:
    PAYLOAD = {
        "jobs": [
            {
                "id": 4012,
                "title": "Data Analyst",
                "absolute_url": "https://job-boards.greenhouse.io/example/jobs/4012",
                "location": {"name": "Remote - Europe"},
                "updated_at": "2026-08-20T10:00:00Z",
                "content": "&lt;p&gt;Analyse things&lt;/p&gt;",
                "departments": [{"name": "Data"}],
            }
        ]
    }

    @respx.mock
    async def test_parses_a_board(self, ctx: FetchContext) -> None:
        respx.get(url__startswith="https://boards-api.greenhouse.io").mock(
            return_value=httpx.Response(200, json=self.PAYLOAD)
        )
        found = await GreenhouseSource().fetch({"board": "example", "company": "Example"}, ctx)
        assert len(found) == 1
        assert found[0].title == "Data Analyst"
        assert found[0].company == "Example"
        assert found[0].posted_at == date(2026, 8, 20)
        assert found[0].tags == ("Data",)

    @respx.mock
    async def test_content_is_unescaped_html(self, ctx: FetchContext) -> None:
        respx.get(url__startswith="https://boards-api.greenhouse.io").mock(
            return_value=httpx.Response(200, json=self.PAYLOAD)
        )
        found = await GreenhouseSource().fetch({"board": "example"}, ctx)
        assert found[0].description == "Analyse things"

    @respx.mock
    async def test_remote_is_inferred_from_the_location(self, ctx: FetchContext) -> None:
        respx.get(url__startswith="https://boards-api.greenhouse.io").mock(
            return_value=httpx.Response(200, json=self.PAYLOAD)
        )
        found = await GreenhouseSource().fetch({"board": "example"}, ctx)
        assert found[0].workplace is Workplace.REMOTE

    async def test_missing_board(self, ctx: FetchContext) -> None:
        with pytest.raises(SourceError):
            await GreenhouseSource().fetch({}, ctx)


class TestLever:
    PAYLOAD = [
        {
            "id": "abc-123",
            "text": "Backend Engineer",
            "hostedUrl": "https://jobs.lever.co/example/abc-123",
            "categories": {"location": "Zagreb", "team": "Platform", "commitment": "Full-time"},
            "descriptionPlain": "Build services",
            "createdAt": 1755036000000,
        }
    ]

    @respx.mock
    async def test_parses_a_board(self, ctx: FetchContext) -> None:
        respx.get(url__startswith="https://api.lever.co").mock(
            return_value=httpx.Response(200, json=self.PAYLOAD)
        )
        found = await LeverSource().fetch({"company": "example"}, ctx)
        assert found[0].title == "Backend Engineer"
        assert found[0].location == "Zagreb"
        assert found[0].employment_type == "Full-time"

    @respx.mock
    async def test_timestamps_are_milliseconds_not_seconds(self, ctx: FetchContext) -> None:
        """Reading these as seconds lands in 1970 and every ad looks ancient."""
        respx.get(url__startswith="https://api.lever.co").mock(
            return_value=httpx.Response(200, json=self.PAYLOAD)
        )
        found = await LeverSource().fetch({"company": "example"}, ctx)
        assert found[0].posted_at is not None
        assert found[0].posted_at.year == 2025


class TestAshby:
    PAYLOAD = {
        "jobs": [
            {
                "id": "x1",
                "title": "Product Designer",
                "location": "Berlin",
                "department": "Design",
                "employmentType": "FullTime",
                "jobUrl": "https://jobs.ashbyhq.com/example/x1",
                "publishedAt": "2026-08-22T00:00:00Z",
                "descriptionPlain": "Design things",
                "isRemote": True,
            }
        ]
    }

    @respx.mock
    async def test_parses_a_board(self, ctx: FetchContext) -> None:
        respx.get(url__startswith="https://api.ashbyhq.com").mock(
            return_value=httpx.Response(200, json=self.PAYLOAD)
        )
        found = await AshbySource().fetch({"board": "example"}, ctx)
        assert found[0].title == "Product Designer"
        # Ashby states this outright, so nothing is inferred from the text.
        assert found[0].workplace is Workplace.REMOTE


class TestWorkable:
    PAYLOAD = {
        "name": "Example d.o.o.",
        "jobs": [
            {
                "title": "QA Engineer",
                "url": "https://apply.workable.com/example/j/ABC/",
                "location": {"city": "Split", "country": "Croatia", "telecommuting": False},
                "created_at": "2026-08-21",
                "description": "<p>Test things</p>",
                "type": "Full-time",
                "department": "Engineering",
            }
        ],
    }

    @respx.mock
    async def test_parses_a_board(self, ctx: FetchContext) -> None:
        respx.get(url__startswith="https://apply.workable.com").mock(
            return_value=httpx.Response(200, json=self.PAYLOAD)
        )
        found = await WorkableSource().fetch({"account": "example"}, ctx)
        assert found[0].title == "QA Engineer"
        assert found[0].location == "Split, Croatia"

    @respx.mock
    async def test_employer_falls_back_to_the_account_name(self, ctx: FetchContext) -> None:
        respx.get(url__startswith="https://apply.workable.com").mock(
            return_value=httpx.Response(200, json=self.PAYLOAD)
        )
        found = await WorkableSource().fetch({"account": "example"}, ctx)
        assert found[0].company == "Example d.o.o."


class TestRecruitee:
    PAYLOAD = {
        "offers": [
            {
                "id": 77,
                "title": "Support Specialist",
                "careers_url": "https://example.recruitee.com/o/support-specialist",
                "city": "Rijeka",
                "country": "Croatia",
                "created_at": "2026-08-19 08:00:00 UTC",
                "description": "<p>Help people</p>",
                "employment_type_code": "fulltime",
                "remote": False,
                "department": "Support",
            }
        ]
    }

    @respx.mock
    async def test_parses_a_board(self, ctx: FetchContext) -> None:
        respx.get(url__startswith="https://example.recruitee.com").mock(
            return_value=httpx.Response(200, json=self.PAYLOAD)
        )
        found = await RecruiteeSource().fetch({"company": "example"}, ctx)
        assert found[0].title == "Support Specialist"
        assert found[0].location == "Rijeka, Croatia"


class TestSmartRecruiters:
    PAYLOAD = {
        "content": [
            {
                "id": "743999",
                "name": "Account Manager",
                "releasedDate": "2026-08-18T00:00:00.000Z",
                "location": {"city": "Vienna", "country": "at", "remote": False},
                "department": {"label": "Sales"},
                "typeOfEmployment": {"label": "Permanent"},
            }
        ]
    }

    @respx.mock
    async def test_parses_a_board(self, ctx: FetchContext) -> None:
        respx.get(url__startswith="https://api.smartrecruiters.com").mock(
            return_value=httpx.Response(200, json=self.PAYLOAD)
        )
        found = await SmartRecruitersSource().fetch({"company": "Example"}, ctx)
        assert found[0].title == "Account Manager"

    @respx.mock
    async def test_the_public_url_is_reconstructed(self, ctx: FetchContext) -> None:
        """This API returns no ad URL, so the public address is composed."""
        respx.get(url__startswith="https://api.smartrecruiters.com").mock(
            return_value=httpx.Response(200, json=self.PAYLOAD)
        )
        found = await SmartRecruitersSource().fetch({"company": "Example"}, ctx)
        assert found[0].url == "https://jobs.smartrecruiters.com/Example/743999"


# --------------------------------------------------------------------- boards


class TestRemotive:
    PAYLOAD = {
        "jobs": [
            {
                "id": 1,
                "url": "https://remotive.com/remote-jobs/data/analyst-1",
                "title": "Data Analyst",
                "company_name": "Example Ltd",
                "category": "data",
                "tags": ["sql", "python"],
                "job_type": "full_time",
                "publication_date": "2026-08-23T12:00:00",
                "candidate_required_location": "Europe",
                "salary": "50000 - 70000 EUR",
                "description": "<p>Analyse</p>",
            }
        ]
    }

    @respx.mock
    async def test_parses_the_board(self, ctx: FetchContext) -> None:
        respx.get(url__startswith="https://remotive.com/api").mock(
            return_value=httpx.Response(200, json=self.PAYLOAD)
        )
        found = await RemotiveSource().fetch({"search": "data"}, ctx)
        assert found[0].title == "Data Analyst"
        assert found[0].salary == "50000 - 70000 EUR"
        # Everything on this board is remote by definition.
        assert found[0].workplace is Workplace.REMOTE


class TestRemoteOk:
    PAYLOAD = [
        {"legal": "Data provided by RemoteOK. Please link back to the original post."},
        {
            "id": "9",
            "slug": "example-backend",
            "company": "Example",
            "position": "Backend Engineer",
            "tags": ["python", "django"],
            "description": "<p>Build</p>",
            "location": "Worldwide",
            "url": "https://remoteok.com/remote-jobs/9",
            "date": "2026-08-22T10:00:00+00:00",
            "salary_min": 60000,
            "salary_max": 90000,
        },
    ]

    @respx.mock
    async def test_the_legal_notice_is_not_a_job(self, ctx: FetchContext) -> None:
        """The first element is their terms; taking it produces a bogus row."""
        respx.get("https://remoteok.com/api").mock(
            return_value=httpx.Response(200, json=self.PAYLOAD)
        )
        found = await RemoteOkSource().fetch({}, ctx)
        assert len(found) == 1
        assert found[0].title == "Backend Engineer"

    @respx.mock
    async def test_tag_filter(self, ctx: FetchContext) -> None:
        respx.get("https://remoteok.com/api").mock(
            return_value=httpx.Response(200, json=self.PAYLOAD)
        )
        assert await RemoteOkSource().fetch({"tag": "python"}, ctx)
        assert not await RemoteOkSource().fetch({"tag": "cobol"}, ctx)

    @respx.mock
    async def test_salary_range(self, ctx: FetchContext) -> None:
        respx.get("https://remoteok.com/api").mock(
            return_value=httpx.Response(200, json=self.PAYLOAD)
        )
        found = await RemoteOkSource().fetch({}, ctx)
        assert found[0].salary == "60000-90000"


class TestArbeitnow:
    PAYLOAD = {
        "data": [
            {
                "slug": "example-dev",
                "company_name": "Example GmbH",
                "title": "Fullstack Developer",
                "description": "<p>Baue</p>",
                "remote": True,
                "url": "https://www.arbeitnow.com/jobs/companies/example/dev",
                "tags": ["laravel"],
                "job_types": ["full_time"],
                "location": "Berlin",
                "created_at": 1787000000,
            }
        ]
    }

    @respx.mock
    async def test_parses_a_page(self, ctx: FetchContext) -> None:
        respx.get(url__startswith="https://www.arbeitnow.com/api").mock(
            return_value=httpx.Response(200, json=self.PAYLOAD)
        )
        found = await ArbeitnowSource().fetch({"pages": 1}, ctx)
        assert found[0].title == "Fullstack Developer"
        assert found[0].workplace is Workplace.REMOTE

    @respx.mock
    async def test_remote_only_filter(self, ctx: FetchContext) -> None:
        onsite = {"data": [{**self.PAYLOAD["data"][0], "remote": False}]}
        respx.get(url__startswith="https://www.arbeitnow.com/api").mock(
            return_value=httpx.Response(200, json=onsite)
        )
        assert not await ArbeitnowSource().fetch({"pages": 1, "remote_only": True}, ctx)


# ------------------------------------------------------------------- Croatian


HZZ_FEED = """<?xml version="1.0" encoding="iso-8859-2"?>
<rss version="2.0"><channel>
<item>
  <title>VIŠI STRUČNI SURADNIK ZA GEODEZIJU</title>
  <link>http://burzarada.hzz.hr/RadnoMjesto_Ispis.aspx?WebSifra=123</link>
  <description>Opis posla: Izrada elaborata, vođenje postupaka, suradnja s uredima,
 Kategorija: GRAĐEVINARI, ARHITEKTI, GEODETE, Rok za prijavu: 12.09.2026,
 Mjesto rada: KARLOVAC, Općina: KARLOVAC, Županija: KARLOVAČKA</description>
  <pubDate>Mon, 24 Aug 2026 09:15:00 +0200</pubDate>
</item>
</channel></rss>"""


class TestHzz:
    @respx.mock
    async def test_reads_a_county_feed(self, ctx: FetchContext) -> None:
        respx.get("https://burzarada.hzz.hr/rss/rsszup6.xml").mock(
            return_value=httpx.Response(200, content=HZZ_FEED.encode("iso-8859-2"))
        )
        found = await HzzSource().fetch({"counties": [6]}, ctx)
        assert len(found) == 1
        assert found[0].location == "KARLOVAC"
        assert found[0].deadline == date(2026, 9, 12)

    @respx.mock
    async def test_the_flattened_description_is_split_on_labels(
        self, ctx: FetchContext
    ) -> None:
        """The job description itself contains commas."""
        respx.get("https://burzarada.hzz.hr/rss/rsszup6.xml").mock(
            return_value=httpx.Response(200, content=HZZ_FEED.encode("iso-8859-2"))
        )
        found = await HzzSource().fetch({"counties": [6]}, ctx)
        assert found[0].description.startswith("Izrada elaborata, vođenje postupaka")

    @respx.mock
    async def test_the_broad_source_category_is_kept_out_of_the_searchable_text(
        self, ctx: FetchContext
    ) -> None:
        """Matching this category turns a bricklayer into a surveyor."""
        respx.get("https://burzarada.hzz.hr/rss/rsszup6.xml").mock(
            return_value=httpx.Response(200, content=HZZ_FEED.encode("iso-8859-2"))
        )
        found = await HzzSource().fetch({"counties": [6]}, ctx)
        assert "GRAĐEVINARI" not in found[0].description
        assert found[0].raw["source_category"].startswith("GRAĐEVINARI")

    @respx.mock
    async def test_link_is_upgraded_to_https(self, ctx: FetchContext) -> None:
        respx.get("https://burzarada.hzz.hr/rss/rsszup6.xml").mock(
            return_value=httpx.Response(200, content=HZZ_FEED.encode("iso-8859-2"))
        )
        found = await HzzSource().fetch({"counties": [6]}, ctx)
        assert found[0].url.startswith("https://")

    @respx.mock
    async def test_a_broken_county_does_not_sink_the_others(self, ctx: FetchContext) -> None:
        respx.get("https://burzarada.hzz.hr/rss/rsszup6.xml").mock(
            return_value=httpx.Response(500)
        )
        respx.get("https://burzarada.hzz.hr/rss/rsszup4.xml").mock(
            return_value=httpx.Response(200, content=HZZ_FEED.encode("iso-8859-2"))
        )
        found = await HzzSource().fetch({"counties": [6, 4]}, ctx)
        assert len(found) == 1

    def test_the_feed_numbers_are_alphabetical_not_official_codes(self) -> None:
        """Karlovačka is officially county 04 but feed 6. Verified 2026-08-24."""
        from jobsheet.sources.hr.hzz import COUNTIES

        assert COUNTIES[4] == "Grad Zagreb"
        assert COUNTIES[6] == "Karlovačka"
        assert COUNTIES[21] == "Zagrebačka"
        assert len(COUNTIES) == 21


POSAO_FEED = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item>
  <title>Prodajni predstavnik</title>
  <link>https://www.posao.hr/oglas/1</link>
  <description>Poslodavac: Example d.o.o. Mjesto rada: Zagreb Rok za prijavu: 05.09.2026</description>
  <pubDate>Sat, 22 Aug 2026 08:00:00 +0200</pubDate>
</item>
</channel></rss>"""


class TestPosaoHr:
    @respx.mock
    async def test_parses_the_feed(self, ctx: FetchContext) -> None:
        respx.get("https://www.posao.hr/rss/").mock(
            return_value=httpx.Response(200, text=POSAO_FEED)
        )
        found = await PosaoHrSource().fetch({}, ctx)
        assert found[0].company == "Example d.o.o."
        assert found[0].location == "Zagreb"
        assert found[0].deadline == date(2026, 9, 5)


class TestSelekcija:
    LISTING = [
        {
            "ID": "id-1",
            "RadnoMjestoNaziv": "Viši stručni suradnik",
            "SifraNatjecaja": "123-456",
            "DrzavnoTijeloNaziv": "Ministarstvo primjera",
            "MjestoRada": "Split",
            "ZupanijaNaziv": "Grad Zagreb",
            "VrstaRadnogOdnosa": "Na neodređeno vrijeme",
            "StrucnaSprema": "Razina 7.1.st",
            "DatumObjaveNatjecaja": "/Date(1755036000000+0200)/",
            "RokZaPrijavuISO8601": "2026-09-30T00:00:00",
        }
    ]
    DETAIL = [{"ID": "id-1", "OpisPoslova": "<p>Obavlja poslove</p>", "LokacijaRadnogMjesta": ""}]

    @staticmethod
    def wrapped(rows: list[dict[str, Any]]) -> dict[str, Any]:
        """The envelope Rhetos serves today."""
        return {"Records": rows}

    @respx.mock
    async def test_joins_the_two_requests(self, ctx: FetchContext) -> None:
        respx.get(url__startswith="https://selekcija.gov.hr").mock(
            side_effect=[
                httpx.Response(200, json=self.wrapped(self.LISTING)),
                httpx.Response(200, json=self.wrapped(self.DETAIL)),
            ]
        )
        found = await SelekcijaSource().fetch({"days": 45}, ctx)
        assert found[0].title == "Viši stručni suradnik"
        assert found[0].description == "Obavlja poslove"

    @respx.mock
    async def test_a_bare_array_still_parses(self, ctx: FetchContext) -> None:
        """Rhetos served an unwrapped array until 2026; tolerate it going back.

        This is the shape every fixture here used before the live check of
        2026-08-25 found the wrapper -- which is the whole reason the recorded
        tests kept passing while the source returned nothing to real users.
        """
        respx.get(url__startswith="https://selekcija.gov.hr").mock(
            side_effect=[
                httpx.Response(200, json=self.LISTING),
                httpx.Response(200, json=self.DETAIL),
            ]
        )
        found = await SelekcijaSource().fetch({"days": 45}, ctx)
        assert found[0].title == "Viši stručni suradnik"
        assert found[0].description == "Obavlja poslove"

    @respx.mock
    async def test_an_unknown_envelope_is_an_error_not_an_empty_result(
        self, ctx: FetchContext
    ) -> None:
        """Silence is the dangerous failure: nothing raises, nothing is found."""
        respx.get(url__startswith="https://selekcija.gov.hr").mock(
            return_value=httpx.Response(200, json={"Something": "else"})
        )
        with pytest.raises(SourceError):
            await SelekcijaSource().fetch({"days": 45}, ctx)

    @respx.mock
    async def test_the_authority_seat_is_never_used_as_the_region(
        self, ctx: FetchContext
    ) -> None:
        """27% of listings name the capital for work elsewhere (2026-08-24).

        The job below is in Split while the authority sits in Zagreb.
        """
        respx.get(url__startswith="https://selekcija.gov.hr").mock(
            side_effect=[
                httpx.Response(200, json=self.wrapped(self.LISTING)),
                httpx.Response(200, json=self.wrapped(self.DETAIL)),
            ]
        )
        found = await SelekcijaSource().fetch({"days": 45}, ctx)
        assert found[0].location == "Split"
        assert found[0].region == ""
        assert found[0].raw["authority_county"] == "Grad Zagreb"

    @respx.mock
    async def test_descriptions_are_optional(self, ctx: FetchContext) -> None:
        """Losing the description must not lose the competition."""
        respx.get(url__startswith="https://selekcija.gov.hr").mock(
            side_effect=[
                httpx.Response(200, json=self.wrapped(self.LISTING)),
                httpx.Response(500),
            ]
        )
        found = await SelekcijaSource().fetch({"days": 45}, ctx)
        assert len(found) == 1


# Recorded from the live result page on 2026-09-03, trimmed to one item. The
# shape matters: the title lives in `resultTitle`, reads "KIND - Institution",
# and the score span carries a `style` attribute.
NN_RESULTS = """
<div class="searchListItem">
  <table><tr><td class="first">1.&nbsp;</td><td>
    <div class="resultTitle">
      <a href="/clanci/oglasi/o1234.html" target="_self">
        JAVNI NATJEČAJ - Grad Samobor <span class="score" style="display:none;">0</span>
      </a>
    </div>
  </td></tr>
  <tr><td class="first"></td><td>
    <div class="official-number-and-date">NN 96/2026, (5959), oglasni dio, natječaji za radna mjesta, 22.8.2026.</div>
    <span class="snippet">Klasa: 112-02/26-01/2 Na temelju članka 7. st...</span>
  </td></tr></table>
</div>
"""

# Same shape, but the notice is a competition being called off. Measured on
# 2026-09-04, the withdrawal reaches the reader under three different kinds, so
# all three are exercised.
NN_WITHDRAWN = """
<div class="searchListItem">
  <table><tr><td class="first">1.&nbsp;</td><td>
    <div class="resultTitle">
      <a href="/clanci/oglasi/o9001.html" target="_self">
        {kind} - Grad Samobor <span class="score" style="display:none;">0</span>
      </a>
    </div>
  </td></tr></table>
</div>
"""

NN_BODY = """
<div class="og-content">
Na temelju clanka 17. Zakona o sluzbenicima i namjestenicima u lokalnoj
samoupravi, procelnik raspisuje javni natjecaj za prijam u sluzbu na radno
mjesto visi strucni suradnik za prostorno uredenje u Upravnom odjelu, na
neodredeno vrijeme, uz uvjet zavrsen sveucilisni diplomski studij.
</div>
"""


class TestNarodneNovine:
    @respx.mock
    async def test_mines_the_post_out_of_legal_prose(self, ctx: FetchContext) -> None:
        """The title is always the institution, never the job."""
        respx.get(url__startswith="https://narodne-novine.nn.hr/search.aspx").mock(
            return_value=httpx.Response(200, text=NN_RESULTS)
        )
        respx.get("https://narodne-novine.nn.hr/clanci/oglasi/o1234.html").mock(
            return_value=httpx.Response(200, text=NN_BODY)
        )
        found = await NarodneNovineSource().fetch({"terms": "geodetski"}, ctx)
        assert len(found) == 1
        assert found[0].title.startswith("visi strucni suradnik")
        assert found[0].company == "Grad Samobor"

    @respx.mock
    async def test_the_hidden_relevance_score_is_stripped(self, ctx: FetchContext) -> None:
        """Leaving it in produces institutions called "Grad Samobor 0"."""
        respx.get(url__startswith="https://narodne-novine.nn.hr/search.aspx").mock(
            return_value=httpx.Response(200, text=NN_RESULTS)
        )
        respx.get("https://narodne-novine.nn.hr/clanci/oglasi/o1234.html").mock(
            return_value=httpx.Response(200, text=NN_BODY)
        )
        found = await NarodneNovineSource().fetch({"terms": "geodetski"}, ctx)
        assert found[0].company == "Grad Samobor"

    @respx.mock
    async def test_notices_that_only_point_at_selekcija_are_dropped(
        self, ctx: FetchContext
    ) -> None:
        """State bodies publish a stub here and the real competition there."""
        stub = '<div class="og-content">Prijave se podnose putem selekcija.gov.hr</div>'
        respx.get(url__startswith="https://narodne-novine.nn.hr/search.aspx").mock(
            return_value=httpx.Response(200, text=NN_RESULTS)
        )
        respx.get("https://narodne-novine.nn.hr/clanci/oglasi/o1234.html").mock(
            return_value=httpx.Response(200, text=stub)
        )
        assert not await NarodneNovineSource().fetch({"terms": "geodetski"}, ctx)

    @respx.mock
    async def test_the_kind_of_notice_is_split_off_the_institution(
        self, ctx: FetchContext
    ) -> None:
        """The heading reads "KIND - Institution"; the company is the second half.

        Splitting it off matters beyond tidiness: the kind is what the test
        below reads to throw a withdrawn competition away.
        """
        respx.get(url__startswith="https://narodne-novine.nn.hr/search.aspx").mock(
            return_value=httpx.Response(200, text=NN_RESULTS)
        )
        respx.get("https://narodne-novine.nn.hr/clanci/oglasi/o1234.html").mock(
            return_value=httpx.Response(200, text=NN_BODY)
        )
        (found,) = await NarodneNovineSource().fetch({"terms": "geodetski"}, ctx)
        assert found.company == "Grad Samobor"
        assert found.raw["notice_kind"] == "JAVNI NATJEČAJ"

    @pytest.mark.parametrize(
        "kind",
        [
            "PONIŠTENJE NATJEČAJA",
            "ODLUKA O PONIŠTENJU NATJEČAJA",
            "DJELOMIČNO PONIŠTENJE NATJEČAJA",
            "PONISTENJE NATJECAJA",
        ],
    )
    @respx.mock
    async def test_a_withdrawn_competition_is_not_a_job(
        self, ctx: FetchContext, kind: str
    ) -> None:
        """A competition being called off was reaching the reader as an opening."""
        respx.get(url__startswith="https://narodne-novine.nn.hr/search.aspx").mock(
            return_value=httpx.Response(200, text=NN_WITHDRAWN.format(kind=kind))
        )
        page = respx.get("https://narodne-novine.nn.hr/clanci/oglasi/o9001.html").mock(
            return_value=httpx.Response(200, text=NN_BODY)
        )
        assert not await NarodneNovineSource().fetch({"terms": "geodetski"}, ctx)
        # Dropped from the result list, not after the fact: opening it would
        # spend one of the few enrich slots on a job that does not exist.
        assert not page.called

    @respx.mock
    async def test_a_repeated_competition_is_still_a_job(self, ctx: FetchContext) -> None:
        """"PONOVLJENI NATJEČAJ" shares no stem with the withdrawal; it is an opening."""
        respx.get(url__startswith="https://narodne-novine.nn.hr/search.aspx").mock(
            return_value=httpx.Response(200, text=NN_WITHDRAWN.format(kind="PONOVLJENI NATJEČAJ"))
        )
        respx.get("https://narodne-novine.nn.hr/clanci/oglasi/o9001.html").mock(
            return_value=httpx.Response(200, text=NN_BODY)
        )
        (found,) = await NarodneNovineSource().fetch({"terms": "geodetski"}, ctx)
        assert found.company == "Grad Samobor"

    async def test_no_search_words_means_no_requests(self, ctx: FetchContext) -> None:
        assert await NarodneNovineSource().fetch({"terms": ""}, ctx) == []
