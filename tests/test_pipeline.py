"""The search pipeline: fetch, de-duplicate, filter, enrich, build rows.

The ordering assertions matter as much as the results. Doing the expensive step
before the free ones still produces the right answer, but at a cost the user pays
in waiting and the source pays in traffic.
"""

from __future__ import annotations

from datetime import date
from typing import Any, ClassVar

import pytest

from jobsheet.core.matching import KeywordGroup, SearchProfile
from jobsheet.core.models import ApplicationStatus, Posting
from jobsheet.pipeline import (
    DUPLICATE_HINT,
    RunReport,
    SourceRequest,
    build_note,
    run_search,
)
from jobsheet.sheet.row import JobRow
from jobsheet.sources import registry
from jobsheet.sources.base import (
    PHASE_BANDS,
    FetchContext,
    Phase,
    Source,
    SourceManifest,
    percent_for,
)

TODAY = date(2026, 8, 24)


def ad(number: int, **overrides: Any) -> Posting:
    data: dict[str, Any] = {
        "source_id": "fake",
        "title": f"GIS Engineer {number}",
        "url": f"https://example.test/j/{number}",
        "company": f"Company {number}",
        "location": "Zagreb",
        "posted_at": TODAY,
    }
    return Posting(**(data | overrides))


class FakeSource(Source):
    """A source under the test's control, registered in-process."""

    manifest = SourceManifest(id="fake", name="Fake", homepage="https://example.test")
    postings: ClassVar[list[Posting]] = []
    fetch_calls: ClassVar[int] = 0

    async def fetch(self, params: dict[str, Any], ctx: FetchContext) -> list[Posting]:
        type(self).fetch_calls += 1
        return list(type(self).postings)


class EnrichingSource(Source):
    manifest = SourceManifest(
        id="enriching", name="Enriching", homepage="https://example.test", supports_enrich=True
    )
    postings: ClassVar[list[Posting]] = []
    enrich_calls: ClassVar[int] = 0

    async def fetch(self, params: dict[str, Any], ctx: FetchContext) -> list[Posting]:
        return list(type(self).postings)

    async def enrich(self, posting: Posting, ctx: FetchContext) -> Posting:
        type(self).enrich_calls += 1
        return posting.model_copy(update={"employment_type": "Permanent", "education": "MSc"})


class BrokenSource(Source):
    manifest = SourceManifest(id="broken", name="Broken", homepage="https://example.test")

    async def fetch(self, params: dict[str, Any], ctx: FetchContext) -> list[Posting]:
        raise RuntimeError("the server is on fire")


@pytest.fixture(autouse=True)
def _register() -> None:
    registry.register(FakeSource)
    registry.register(EnrichingSource)
    registry.register(BrokenSource)
    FakeSource.postings = []
    FakeSource.fetch_calls = 0
    EnrichingSource.postings = []
    EnrichingSource.enrich_calls = 0


GIS = SearchProfile(keyword_groups=[KeywordGroup(name="GIS", terms=["gis"])])


async def search(**kwargs: Any) -> RunReport:
    defaults: dict[str, Any] = {"profile": GIS, "today": TODAY}
    return await run_search([SourceRequest("fake")], **(defaults | kwargs))


class TestCollecting:
    async def test_matching_ads_become_rows(self) -> None:
        FakeSource.postings = [ad(1), ad(2)]
        report = await search()
        assert report.fetched == 2
        assert report.new_count == 2
        assert {r.posting.title for r in report.rows} == {"GIS Engineer 1", "GIS Engineer 2"}

    async def test_the_category_comes_from_the_matching_group(self) -> None:
        FakeSource.postings = [ad(1)]
        report = await search()
        assert report.rows[0].category == "GIS"

    async def test_non_matching_ads_are_dropped_quietly(self) -> None:
        FakeSource.postings = [ad(1, title="Pastry chef", description="")]
        report = await search()
        assert report.new_count == 0
        # Not a rejection: it never was a candidate, so there is nothing to explain.
        assert report.rejected == []

    async def test_found_at_is_todays_date(self) -> None:
        FakeSource.postings = [ad(1)]
        report = await search()
        assert report.rows[0].found_at == TODAY


class TestDeduplication:
    async def test_ads_already_in_the_sheet_are_skipped(self) -> None:
        existing = [JobRow(posting=ad(1), found_at=TODAY)]
        FakeSource.postings = [ad(1), ad(2)]
        report = await search(existing=existing)
        assert report.duplicates == 1
        assert report.new_count == 1

    async def test_the_same_ad_twice_in_one_run_counts_once(self) -> None:
        FakeSource.postings = [ad(1), ad(1)]
        report = await search()
        assert report.new_count == 1

    async def test_tracking_parameters_do_not_create_a_second_copy(self) -> None:
        FakeSource.postings = [ad(1), ad(1, url="https://example.test/j/1?utm_source=x")]
        report = await search()
        assert report.new_count == 1

    async def test_one_vacancy_under_two_ad_numbers_is_caught(self) -> None:
        """Public bodies republish a post under several reference numbers."""
        FakeSource.postings = [
            ad(1, title="GIS Engineer", company="City of Example"),
            ad(2, title="GIS Engineer", company="City of Example"),
        ]
        report = await search()
        assert report.new_count == 1
        assert report.rejected[0][1].code == "duplicate_of_another_ad"


class TestFiltering:
    async def test_rejections_are_reported_with_a_reason(self) -> None:
        FakeSource.postings = [ad(1, deadline=date(2026, 8, 1))]
        report = await search()
        assert report.new_count == 0
        assert report.rejected[0][1].code == "deadline_passed"

    async def test_location_filter_applies(self) -> None:
        FakeSource.postings = [ad(1, location="Vladivostok")]
        report = await search(profile=GIS.model_copy(update={"locations": ["zagreb"]}))
        assert report.new_count == 0

    async def test_the_note_explains_why_the_ad_is_there(self) -> None:
        FakeSource.postings = [ad(1, deadline=date(2026, 9, 12))]
        report = await search()
        note = report.rows[0].note
        assert "Zagreb" in note
        assert "closes 2026-09-12" in note
        assert 'matched "gis"' in note


class TestEnrichment:
    async def test_details_are_fetched_only_for_survivors(self) -> None:
        """Two ads arrive; one is off-topic. Only the good one costs a request."""
        EnrichingSource.postings = [ad(1, source_id="enriching"), ad(2, source_id="enriching", title="Pastry chef")]
        await run_search([SourceRequest("enriching")], GIS, today=TODAY)
        assert EnrichingSource.enrich_calls == 1

    async def test_enrichment_is_capped(self) -> None:
        """The expensive pass must have a ceiling on a busy feed."""
        EnrichingSource.postings = [ad(n, source_id="enriching") for n in range(1, 21)]
        await run_search([SourceRequest("enriching")], GIS, today=TODAY, max_enrich=5)
        assert EnrichingSource.enrich_calls == 5

    async def test_enriched_fields_reach_the_hard_filters(self) -> None:
        """The contract type only exists after enrichment, so it must run first."""
        EnrichingSource.postings = [ad(1, source_id="enriching")]
        profile = GIS.model_copy(update={"excluded_employment_types": ["permanent"]})
        report = await run_search([SourceRequest("enriching")], profile, today=TODAY)
        assert report.new_count == 0
        assert report.rejected[0][1].code == "employment_type"

    async def test_sources_without_enrichment_are_not_asked(self) -> None:
        FakeSource.postings = [ad(1)]
        report = await search()
        assert report.new_count == 1


class TestFailures:
    async def test_a_broken_source_is_reported_not_raised(self) -> None:
        FakeSource.postings = [ad(1)]
        report = await run_search(
            [SourceRequest("fake"), SourceRequest("broken")], GIS, today=TODAY
        )
        assert report.new_count == 1
        assert "broken" in report.errors
        assert "the server is on fire" in report.errors["broken"]

    async def test_an_unknown_source_is_reported_not_raised(self) -> None:
        report = await run_search([SourceRequest("does-not-exist")], GIS, today=TODAY)
        assert "does-not-exist" in report.errors

    async def test_progress_is_reported(self) -> None:
        lines: list[str] = []
        FakeSource.postings = [ad(1)]
        await search(on_progress=lines.append)
        assert any("Searching" in line for line in lines)


class TestBuildNote:
    def test_omits_what_is_not_known(self) -> None:
        posting = ad(1, location="", deadline=None, employment_type="")
        from jobsheet.core.matching import match as run_match

        hit = run_match(posting, GIS)
        assert hit is not None
        note = build_note(posting, hit, GIS, today=TODAY)
        assert note.startswith("fake")
        assert "closes" not in note

    def test_soft_flags_are_appended(self) -> None:
        profile = GIS.model_copy(update={"flags": {"mentions German": ["german"]}})
        posting = ad(1, description="German is a plus")
        from jobsheet.core.matching import match as run_match

        hit = run_match(posting, profile)
        assert hit is not None
        assert "mentions German" in build_note(posting, hit, profile, today=TODAY)

    def test_a_dream_employer_reaches_the_row(self) -> None:
        """The whole value of the star is that it is visible in the spreadsheet.

        Built with the model rather than `model_copy(update=...)`, which does not
        validate -- a field name typed wrong there fails as "the flag did not
        appear" rather than as the `ValidationError` it actually is.
        """
        profile = SearchProfile(
            keyword_groups=[KeywordGroup(name="GIS", terms=["gis"])],
            dream_employers=["Company 1"],
        )
        posting = ad(1, company="COMPANY 1 d.o.o.")
        from jobsheet.core.matching import DREAM_FLAG
        from jobsheet.core.matching import match as run_match

        hit = run_match(posting, profile)
        assert hit is not None
        assert DREAM_FLAG in build_note(posting, hit, profile, today=TODAY)

    def test_an_unstated_contract_is_said_out_loud_on_the_row(self) -> None:
        """The other half of `wanted_employment_types`: kept, but marked."""
        profile = SearchProfile(
            keyword_groups=[KeywordGroup(name="GIS", terms=["gis"])],
            wanted_employment_types=["neodređeno"],
        )
        posting = ad(1, employment_type="")
        from jobsheet.core.matching import UNSTATED_CONTRACT_FLAG
        from jobsheet.core.matching import match as run_match

        hit = run_match(posting, profile)
        assert hit is not None
        assert UNSTATED_CONTRACT_FLAG in build_note(posting, hit, profile, today=TODAY)


class TestNeverTwice:
    """The five ways the same job used to come back. Each one, once.

    Every case here is a complaint a user actually made: "I keep seeing this
    one". They are separate tests because they are five separate holes, and a
    single test that happened to cover all five would go green again the moment
    four of them were reopened.
    """

    async def test_an_ad_the_user_skipped_is_not_offered_again(self) -> None:
        """`skipped` is a decision, not a deletion. The row stays and dedups."""
        skipped = JobRow(posting=ad(1), found_at=TODAY, status=ApplicationStatus.SKIPPED)
        FakeSource.postings = [ad(1)]
        report = await search(existing=[skipped])
        assert report.new_count == 0
        assert report.duplicates == 1

    async def test_a_deleted_ad_does_not_come_back(self) -> None:
        """Deleting removes the row, so only a tombstone can hold the line."""
        FakeSource.postings = [ad(1)]
        report = await search(existing=[], forgotten={ad(1).dedup_key})
        assert report.new_count == 0
        assert report.duplicates == 1

    async def test_an_ad_already_filtered_out_is_not_enriched_again(self) -> None:
        """The point is the request not made, so that is what is asserted."""
        EnrichingSource.postings = [ad(1, source_id="enriching")]
        report = await run_search(
            [SourceRequest("enriching")],
            GIS,
            today=TODAY,
            filtered_before={ad(1).dedup_key},
        )
        assert EnrichingSource.enrich_calls == 0
        assert report.new_count == 0
        assert report.rejected[0][1].code == "filtered_out_before"

    async def test_an_ad_with_no_link_is_refused_not_called_a_duplicate(self) -> None:
        FakeSource.postings = [ad(1, url="")]
        report = await search()
        assert report.duplicates == 0
        assert report.rejected[0][1].code == "no_url"

    async def test_two_real_jobs_with_one_title_survive_two_searches(self) -> None:
        """The bug this exists for: the second "Software Engineer" at one
        employer was dropped for ever, silently, as a duplicate ad number."""
        first = ad(1, title="Software Engineer", company="Acme", description="gis")
        second = ad(2, title="Software Engineer", company="Acme", description="gis")

        FakeSource.postings = [first]
        one = await search()
        assert one.new_count == 1

        # Second search, a month later. Different ad, same title, same employer.
        FakeSource.postings = [second]
        two = await search(existing=one.rows)
        assert two.new_count == 1, "a genuine second opening must still arrive"
        assert DUPLICATE_HINT in two.rows[0].note, "and it must say why it looks familiar"

    async def test_the_hint_is_a_remark_and_not_a_rejection(self) -> None:
        """The user decides. A pair match across runs marks; it never removes."""
        existing = [JobRow(posting=ad(1, title="GIS Engineer", company="Acme"), found_at=TODAY)]
        FakeSource.postings = [ad(2, title="GIS Engineer", company="Acme")]
        report = await search(existing=existing)
        assert report.rejected == []
        assert report.new_count == 1

    async def test_one_vacancy_under_two_numbers_is_still_caught_in_one_run(self) -> None:
        """The other half: within a run the pair key is trustworthy, and stays used."""
        FakeSource.postings = [
            ad(1, title="GIS Engineer", company="City"),
            ad(2, title="GIS Engineer", company="City"),
        ]
        report = await search()
        assert report.new_count == 1
        assert report.rejected[0][1].code == "duplicate_of_another_ad"


class TestProgressPerSource:
    """The bars, which are a second channel beside the prose -- not parsed from it."""

    async def test_each_source_reports_a_phase_and_a_percentage(self) -> None:
        steps: list[tuple[str, str, int, int]] = []
        FakeSource.postings = [ad(1)]
        await search(on_step=lambda *args: steps.append(args))

        assert [s for s in steps if s[1] == Phase.FETCHING]
        assert [s for s in steps if s[1] == Phase.DONE]
        assert {s[0] for s in steps} == {"fake"}

    async def test_a_failed_source_stops_rather_than_finishing(self) -> None:
        """A bar that ran to 100% would say the source succeeded."""
        steps: list[tuple[str, str, int, int]] = []
        await run_search(
            [SourceRequest("broken")], GIS, today=TODAY, on_step=lambda *a: steps.append(a)
        )
        assert steps[-1][1] == Phase.FAILED
        assert Phase.DONE not in {phase for _, phase, _, _ in steps}

    async def test_a_percentage_only_ever_moves_forward_through_the_phases(self) -> None:
        FakeSource.postings = [ad(1)]
        seen: list[int] = []
        await search(
            on_step=lambda source, phase, done, total: seen.append(
                percent_for(phase, done, total)
            )
        )
        assert seen == sorted(seen)
        assert seen[-1] == 100

    def test_a_source_that_knows_its_own_size_lands_inside_the_phase(self) -> None:
        """Two counties of five is partway through fetching, not partway through
        the whole run."""
        low, high = PHASE_BANDS[Phase.FETCHING]
        assert percent_for(Phase.FETCHING, 0, 5) == low
        assert percent_for(Phase.FETCHING, 5, 5) == high
        assert low < percent_for(Phase.FETCHING, 2, 5) < high

    def test_a_failure_freezes_the_bar_where_it_got_to(self) -> None:
        assert percent_for(Phase.FAILED, 0, 0, previous=37) == 37
