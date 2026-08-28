"""The Croatian place table, and the lookups the wizard does against it.

Most of this file guards a checked-in list against a careless edit. The counts
are the article's own, the county names have to keep agreeing with the
employment service's feed numbers, and the prefix rule is the one piece of
judgement in the module: it decides whether typing three letters gives you the
town you meant or a screenful of everything containing those letters.
"""

from __future__ import annotations

import pytest

from jobsheet.data.places_hr import (
    CITIES,
    COUNTIES,
    COUNTY_OF,
    MUNICIPALITIES,
    PLACES,
    county_feed_number,
    search_places,
)
from jobsheet.sources.hr.hzz import COUNTIES as HZZ_COUNTIES


class TestTheTableItself:
    def test_there_are_twenty_one_counties(self) -> None:
        assert len(COUNTIES) == 21
        assert sorted(COUNTIES) == list(range(1, 22))

    def test_there_are_a_hundred_and_twenty_eight_cities(self) -> None:
        assert len(CITIES) == 128

    def test_there_are_four_hundred_and_twenty_seven_municipality_names(self) -> None:
        """428 municipalities, 427 names: Privlaka exists in two counties."""
        assert len(MUNICIPALITIES) == 427
        assert "Privlaka" in MUNICIPALITIES

    def test_everything_is_in_places(self) -> None:
        assert set(CITIES) <= set(PLACES)
        assert set(MUNICIPALITIES) <= set(PLACES)

    def test_the_lists_are_sorted_and_free_of_duplicates(self) -> None:
        for names in (CITIES, MUNICIPALITIES, PLACES):
            assert len(set(names)) == len(names)
            assert list(names) == sorted(names)

    def test_the_source_still_uses_this_table(self) -> None:
        """The move out of `hzz.py` has to leave the source working unchanged."""
        assert HZZ_COUNTIES is COUNTIES

    def test_the_feed_numbers_are_hzzs_own_index_not_the_official_codes(self) -> None:
        """The single easiest thing to get wrong here, so it is written down.

        Karlovačka is officially county 04 and is feed 6, because HZZ numbers its
        feeds by the Croatian alphabetical order of the names.
        """
        assert COUNTIES[6] == "Karlovačka"
        assert COUNTIES[4] == "Grad Zagreb"
        # Croatian alphabetical order, in which Š is its own letter after S --
        # which is why no `sorted()` in Python reproduces this list.
        assert COUNTIES[14] == "Sisačko-moslavačka"
        assert COUNTIES[15] == "Splitsko-dalmatinska"
        assert COUNTIES[16] == "Šibensko-kninska"


class TestWhichCountyAPlaceIsIn:
    @pytest.mark.parametrize(
        ("place", "county"),
        [
            ("Rijeka", "Primorsko-goranska"),
            ("Zagreb", "Grad Zagreb"),
            ("Split", "Splitsko-dalmatinska"),
            ("Velika Gorica", "Zagrebačka"),
        ],
    )
    def test_a_place_knows_its_county(self, place: str, county: str) -> None:
        assert COUNTY_OF[place] == county

    @pytest.mark.parametrize("ambiguous", ["Privlaka", "Novigrad", "Otok", "Sveta Nedelja"])
    def test_a_name_in_two_counties_has_none(self, ambiguous: str) -> None:
        """Guessing would pre-tick the wrong feed and look like knowledge."""
        assert ambiguous in PLACES
        assert ambiguous not in COUNTY_OF


class TestFindingTheFeedForACounty:
    @pytest.mark.parametrize(
        "written",
        [
            "Primorsko-goranska",
            "primorsko-goranska",
            "Primorsko-goranska županija",
            "PRIMORSKO-GORANSKA ŽUPANIJA",
            "Primorsko-goranska zupanija",
        ],
    )
    def test_the_name_is_matched_however_it_was_written(self, written: str) -> None:
        assert county_feed_number(written) == 13

    def test_something_that_is_not_a_county_gets_nothing(self) -> None:
        assert county_feed_number("Ljubljana") is None
        assert county_feed_number("") is None


class TestSuggesting:
    def test_a_prefix_finds_the_town(self) -> None:
        assert search_places("rij")[0]["name"] == "Rijeka"

    def test_a_later_word_counts_as_a_start(self) -> None:
        names = [place["name"] for place in search_places("gorica")]
        assert "Velika Gorica" in names

    def test_it_is_not_a_substring_search(self) -> None:
        """"rij" must not drag in Marija Bistrica -- that is what makes it useless."""
        names = [place["name"] for place in search_places("rij")]
        assert "Marija Bistrica" not in names

    def test_diacritics_do_not_have_to_be_typed(self) -> None:
        assert "Čakovec" in [place["name"] for place in search_places("cakovec")]
        assert "Šibenik" in [place["name"] for place in search_places("sib")]

    def test_a_city_outranks_a_municipality_that_starts_the_same_way(self) -> None:
        first = search_places("novigrad")[0]
        assert first["name"] == "Novigrad"
        assert first["kind"] == "city"

    def test_the_kind_narrows_the_pool(self) -> None:
        assert all(place["kind"] == "city" for place in search_places("", "city"))
        assert all(place["kind"] == "county" for place in search_places("", "county"))

    def test_every_county_fits_in_one_page_of_suggestions(self) -> None:
        """The picker shows them all at once, so the default limit has to cover it."""
        assert len(search_places("", "county")) == 21

    def test_an_empty_query_answers_rather_than_refusing(self) -> None:
        """It is what a field asks the moment it is focused."""
        assert len(search_places("")) == 20

    def test_the_limit_is_honoured(self) -> None:
        assert len(search_places("", limit=5)) == 5

    def test_nothing_matches_nothing(self) -> None:
        assert search_places("qqqq") == []
