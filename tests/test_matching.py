"""Keyword matching, location rules and hard filters.

Several tests here are named after the false positive or false negative they
prevent. Those cases were paid for in the predecessor project by ads that should
never have been shown, or good ads that were silently dropped.
"""

from __future__ import annotations

from datetime import date

import pytest

from jobsheet.core.matching import (
    DREAM_FLAG,
    UNSTATED_CONTRACT_FLAG,
    KeywordGroup,
    SearchProfile,
    flags_for,
    fold,
    location_matches,
    match,
    rejection_for,
    sentence_case,
)
from jobsheet.core.models import Posting, Workplace

TODAY = date(2026, 8, 24)


def posting(**kwargs: object) -> Posting:
    """A minimal valid posting; every test overrides only what it cares about."""
    base: dict[str, object] = {
        "source_id": "test",
        "title": "Data Analyst",
        "url": "https://example.test/j/1",
        "company": "Example d.o.o.",
        "posted_at": TODAY,
    }
    return Posting(**(base | kwargs))  # type: ignore[arg-type]


# --------------------------------------------------------------------- folding


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("GEODEZIJA", "geodezija"),
        ("Čakovec", "cakovec"),
        ("ŽUPANIJA", "zupanija"),
        ("Šibenik", "sibenik"),
        ("Đakovo", "dakovo"),
        ("Ćuprija", "cuprija"),
        ("Malmö", "malmo"),
        ("Łódź", "lodz"),
        (None, ""),
    ],
)
def test_fold(raw: object, expected: str) -> None:
    assert fold(raw) == expected


# -------------------------------------------------------------------- keywords


def test_title_hit_wins_over_description_hit() -> None:
    """Group order expresses priority, and the title is checked before the body."""
    profile = SearchProfile(
        keyword_groups=[
            KeywordGroup(name="GIS", terms=["gis"]),
            KeywordGroup(name="Data", terms=["data"]),
        ]
    )
    hit = match(posting(title="Data Analyst", description="works with GIS tools"), profile)
    assert hit is not None
    assert (hit.group, hit.field) == ("Data", "title")


def test_stem_matches_inflected_forms() -> None:
    """An unanchored suffix is the point: one stem covers a whole paradigm."""
    profile = SearchProfile(keyword_groups=[KeywordGroup(name="Geodesy", terms=["geodez"])])
    for title in ("Geodezija", "geodezije", "GEODEZIJU", "inženjer geodezije"):
        assert match(posting(title=title), profile) is not None


def test_gis_does_not_match_logistika() -> None:
    """The word boundary is load-bearing: "gis" hides inside "lo-gis-tika"."""
    profile = SearchProfile(keyword_groups=[KeywordGroup(name="GIS", terms=["gis"])])
    assert match(posting(title="Referent u logistika odjelu"), profile) is None


def test_source_category_is_never_searched() -> None:
    """Feeds staple broad categories onto ads; matching them invents false hits.

    A real example: a bricklayer vacancy carrying the category "CIVIL ENGINEERS,
    ARCHITECTS, SURVEYORS" must not read as a surveying job.
    """
    ad = posting(
        title="Zidar",
        description="Zidarski poslovi na gradilištu.",
        raw={"source_category": "GRAĐEVINARI, ARHITEKTI, GEODETE"},
    )
    profile = SearchProfile(keyword_groups=[KeywordGroup(name="Geodesy", terms=["geodet"])])
    assert match(ad, profile) is None


def test_empty_profile_matches_everything() -> None:
    """Show-me-the-whole-feed is a legitimate request."""
    assert match(posting(), SearchProfile()) is not None


# -------------------------------------------------------------------- location


def test_no_location_filter_accepts_everything() -> None:
    assert location_matches(posting(location="Vladivostok"), SearchProfile()) is True


def test_remote_always_passes() -> None:
    profile = SearchProfile(locations=["zagreb"])
    assert location_matches(posting(location="Berlin", workplace=Workplace.REMOTE), profile)


def test_place_decides_alone_and_region_never_overrides_it() -> None:
    """The region field on some portals is the authority's address, not the job's.

    Measured on one government portal on 2026-08-24: 27% of listings named the
    capital while the work was elsewhere. If region could outrank place, the user
    would be offered jobs halfway across the country.
    """
    profile = SearchProfile(locations=["zagreb"], regions=["grad zagreb"])
    away = posting(location="Split", region="Grad Zagreb")
    assert location_matches(away, profile) is False


def test_region_is_consulted_only_when_place_is_missing() -> None:
    profile = SearchProfile(locations=["zagreb"], regions=["karlovacka"])
    assert location_matches(posting(location="", region="Karlovačka"), profile) is True


def test_falls_back_to_free_text_when_nothing_structured() -> None:
    profile = SearchProfile(locations=["zagreb"])
    ad = posting(location="", region="", description="Mjesto rada: Zagreb, Trg bana Jelačića")
    assert location_matches(ad, profile) is True


# --------------------------------------------------------------- hard filters


def base_profile(**kwargs: object) -> SearchProfile:
    data: dict[str, object] = {"keyword_groups": [KeywordGroup(name="Data", terms=["data"])]}
    return SearchProfile(**(data | kwargs))  # type: ignore[arg-type]


def test_permanent_contract_is_not_caught_by_fixed_term_filter() -> None:
    """The trap: "na neodređeno" (permanent) contains "određeno" (fixed-term).

    Blocking the substring blocks every permanent contract too -- which is the
    exact opposite of what the user asked for. The allowlist wins.
    """
    profile = base_profile(
        excluded_employment_types=["određeno"],
        employment_type_allowlist=["neodređeno"],
    )
    ad = posting(employment_type="Na neodređeno vrijeme")
    hit = match(ad, profile)
    assert hit is not None
    assert rejection_for(ad, hit, profile, today=TODAY) is None


def test_fixed_term_contract_is_still_rejected() -> None:
    profile = base_profile(
        excluded_employment_types=["određeno"],
        employment_type_allowlist=["neodređeno"],
    )
    ad = posting(employment_type="Na određeno vrijeme")
    hit = match(ad, profile)
    assert hit is not None
    rejection = rejection_for(ad, hit, profile, today=TODAY)
    assert rejection is not None
    assert rejection.code == "employment_type"


def test_excluded_employer() -> None:
    profile = base_profile(excluded_employers=["example"])
    ad = posting(company="Example d.o.o.")
    hit = match(ad, profile)
    assert hit is not None
    rejection = rejection_for(ad, hit, profile, today=TODAY)
    assert rejection is not None
    assert rejection.code == "excluded_employer"


def test_expired_deadline_is_rejected() -> None:
    profile = base_profile()
    ad = posting(deadline=date(2026, 8, 1))
    hit = match(ad, profile)
    assert hit is not None
    rejection = rejection_for(ad, hit, profile, today=TODAY)
    assert rejection is not None
    assert rejection.code == "deadline_passed"


def test_old_ad_without_deadline_is_rejected() -> None:
    profile = base_profile(max_age_days=30)
    ad = posting(posted_at=date(2026, 6, 1))
    hit = match(ad, profile)
    assert hit is not None
    rejection = rejection_for(ad, hit, profile, today=TODAY)
    assert rejection is not None
    assert rejection.code == "too_old"


def test_old_ad_with_an_open_deadline_survives() -> None:
    """An explicit deadline is better evidence than an age cut-off.

    A public tender open until September is open, however long ago it was
    published. The age rule exists only for ads that do not say when they close.
    """
    profile = base_profile(max_age_days=30)
    ad = posting(posted_at=date(2026, 6, 1), deadline=date(2026, 9, 30))
    hit = match(ad, profile)
    assert hit is not None
    assert rejection_for(ad, hit, profile, today=TODAY) is None


def test_description_only_hit_can_be_required_to_prove_itself() -> None:
    """A keyword mentioned in passing is weaker evidence than one in the title."""
    profile = base_profile(description_match_requires=["university", "msc"])
    ad = posting(
        title="Warehouse operative", description="some data entry", education="High school"
    )
    hit = match(ad, profile)
    assert hit is not None
    assert hit.field == "description"
    rejection = rejection_for(ad, hit, profile, today=TODAY)
    assert rejection is not None
    assert rejection.code == "description_only_wrong_level"


def test_description_only_rule_is_off_by_default() -> None:
    profile = base_profile()
    ad = posting(title="Warehouse operative", description="some data entry")
    hit = match(ad, profile)
    assert hit is not None
    assert rejection_for(ad, hit, profile, today=TODAY) is None


# ------------------------------------------- the contract the user is asking for


class TestWantedEmploymentTypes:
    """The positive form of the contract filter, added in the wizard rewrite.

    A separate field from `excluded_employment_types` rather than a rename of it,
    because a rename would have broken every profile already saved -- see
    `store.profiles` and `test_profile_migration.py`. Both fields still work.
    """

    def test_an_empty_list_changes_nothing(self) -> None:
        profile = base_profile(wanted_employment_types=[])
        ad = posting(employment_type="Na određeno vrijeme")
        hit = match(ad, profile)
        assert hit is not None
        assert rejection_for(ad, hit, profile, today=TODAY) is None

    def test_the_contract_that_was_asked_for_is_kept(self) -> None:
        profile = base_profile(wanted_employment_types=["neodređeno"])
        ad = posting(employment_type="Na neodređeno vrijeme")
        hit = match(ad, profile)
        assert hit is not None
        assert rejection_for(ad, hit, profile, today=TODAY) is None

    def test_a_different_contract_is_rejected(self) -> None:
        profile = base_profile(wanted_employment_types=["puno radno vrijeme"])
        ad = posting(employment_type="Nepuno radno vrijeme")
        hit = match(ad, profile)
        assert hit is not None
        rejection = rejection_for(ad, hit, profile, today=TODAY)
        assert rejection is not None
        assert rejection.code == "employment_type_not_wanted"
        assert rejection.detail == "Nepuno radno vrijeme"

    def test_an_ad_that_names_no_contract_is_kept_and_flagged(self) -> None:
        """Fail open. Half the feeds omit the field, and refusing those would
        throw most of the search away to enforce a preference."""
        profile = base_profile(wanted_employment_types=["neodređeno"])
        ad = posting(employment_type="")
        hit = match(ad, profile)
        assert hit is not None
        assert rejection_for(ad, hit, profile, today=TODAY) is None
        assert UNSTATED_CONTRACT_FLAG in flags_for(ad, profile, today=TODAY)

    def test_nothing_is_flagged_when_no_contract_was_asked_for(self) -> None:
        profile = base_profile()
        assert UNSTATED_CONTRACT_FLAG not in flags_for(posting(employment_type=""), profile)

    def test_it_is_a_stem_like_every_other_term(self) -> None:
        """"praksa" has to find "Praksa/pripravništvo" without being spelled out."""
        profile = base_profile(wanted_employment_types=["praksa"])
        ad = posting(employment_type="Praksa/pripravništvo")
        hit = match(ad, profile)
        assert hit is not None
        assert rejection_for(ad, hit, profile, today=TODAY) is None

    def test_the_blocklist_still_works_beside_it(self) -> None:
        """Both fields are live; neither replaced the other."""
        profile = base_profile(
            wanted_employment_types=["određeno"],
            excluded_employment_types=["student"],
        )
        ad = posting(employment_type="Studentski ugovor na određeno")
        hit = match(ad, profile)
        assert hit is not None
        rejection = rejection_for(ad, hit, profile, today=TODAY)
        assert rejection is not None
        assert rejection.code == "employment_type"


# ------------------------------------------------------- employers worth a star


class TestDreamEmployers:
    def test_a_dream_employer_is_flagged(self) -> None:
        profile = base_profile(dream_employers=["Ericsson Nikola Tesla"])
        ad = posting(company="ERICSSON NIKOLA TESLA d.d.")
        assert DREAM_FLAG in flags_for(ad, profile, today=TODAY)

    def test_the_legal_form_does_not_have_to_be_typed(self) -> None:
        profile = base_profile(dream_employers=["Geodetski zavod d.o.o."])
        assert DREAM_FLAG in flags_for(posting(company="GEODETSKI ZAVOD"), profile, today=TODAY)

    def test_part_of_a_name_is_enough(self) -> None:
        """Somebody who wrote "Ericsson" means every Ericsson."""
        profile = base_profile(dream_employers=["Ericsson"])
        assert DREAM_FLAG in flags_for(posting(company="Ericsson Nikola Tesla d.d."), profile)

    def test_it_comes_first_so_the_row_reads_as_worth_opening(self) -> None:
        profile = base_profile(
            dream_employers=["Example"], flags={"mentions German": ["german"]}
        )
        ad = posting(company="Example d.o.o.", description="German is a plus")
        assert flags_for(ad, profile, today=TODAY)[0] == DREAM_FLAG

    def test_another_employer_is_not_flagged(self) -> None:
        profile = base_profile(dream_employers=["Ericsson"])
        assert DREAM_FLAG not in flags_for(posting(company="Geodetski zavod d.o.o."), profile)

    def test_it_never_rejects_anything(self) -> None:
        """The whole point: it marks a row, it does not decide anything."""
        profile = base_profile(dream_employers=["Ericsson"])
        ad = posting(company="Somebody Else d.o.o.")
        hit = match(ad, profile)
        assert hit is not None
        assert rejection_for(ad, hit, profile, today=TODAY) is None

    def test_an_ad_with_no_employer_is_not_a_dream_job(self) -> None:
        profile = base_profile(dream_employers=["Ericsson"])
        assert DREAM_FLAG not in flags_for(posting(company=""), profile, today=TODAY)

    def test_a_wish_that_is_only_a_legal_form_matches_nothing(self) -> None:
        """"d.o.o." normalises to nothing, and nothing must not match everything."""
        profile = base_profile(dream_employers=["d.o.o."])
        assert DREAM_FLAG not in flags_for(posting(company="Example d.o.o."), profile)


# ------------------------------------------------------------------- soft flags


def test_flags_annotate_without_rejecting() -> None:
    """A regex cannot tell a hard requirement from a nice-to-have, so it warns."""
    profile = base_profile(flags={"mentions German": ["njemačk", "german"]})
    ad = posting(description="Poznavanje njemačkog jezika je prednost.")
    hit = match(ad, profile)
    assert hit is not None
    assert rejection_for(ad, hit, profile, today=TODAY) is None
    assert "mentions German" in flags_for(ad, profile, today=TODAY)


def test_old_open_ad_is_flagged_even_though_it_is_kept() -> None:
    profile = base_profile(max_age_days=30)
    ad = posting(posted_at=date(2026, 6, 1))
    assert any("older ad" in flag for flag in flags_for(ad, profile, today=TODAY))


# ---------------------------------------------------------------- sentence case


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("VODITELJ GIS ODJELA", "Voditelj GIS odjela"),
        ("ADMINISTRATOR SQL BAZA", "Administrator SQL baza"),
        # Mixed case is a deliberate choice by whoever wrote it: leave it alone.
        ("Tehnomehanik d.o.o. za trgovinu", "Tehnomehanik d.o.o. za trgovinu"),
        ("", ""),
    ],
)
def test_sentence_case(raw: str, expected: str) -> None:
    assert sentence_case(raw) == expected
