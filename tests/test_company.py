"""Comparing employer names the way a person compares them.

The cases here are the ones that actually turn up in feeds: the same firm shouted
in capitals on one board and title-cased on another, a legal form that is
sometimes `d.o.o.` and sometimes `d. o. o.`, and the quotation marks Croatian
registries put around a trade name.
"""

from __future__ import annotations

import pytest

from jobsheet.core.company import normalize_company, same_company


class TestNormalising:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Ericsson Nikola Tesla d.d.", "ericsson nikola tesla"),
            ("ERICSSON NIKOLA TESLA", "ericsson nikola tesla"),
            ("Geodetski zavod  d.o.o.", "geodetski zavod"),
            ("Nešto d. o. o.", "nesto"),
            ("Firma j.d.o.o.", "firma"),
            ('Obrt "Zidar"', "zidar"),
            ("Zadruga Sunce", "sunce"),
            ("Acme Ltd", "acme"),
            ("Ured, d.o.o.", "ured"),
        ],
    )
    def test_the_name_a_person_would_say(self, raw: str, expected: str) -> None:
        assert normalize_company(raw) == expected

    def test_diacritics_stop_mattering(self) -> None:
        """`fold`, not `casefold`: the latter would leave Željko as Željko."""
        assert normalize_company("Žmergo") == normalize_company("Zmergo")

    def test_a_name_that_is_only_a_legal_form_normalises_to_nothing(self) -> None:
        assert normalize_company("d.o.o.") == ""
        assert normalize_company("  ") == ""

    def test_two_legal_forms_both_come_off(self) -> None:
        assert normalize_company("Firma d.o.o. obrt") == "firma"

    def test_a_legal_form_inside_the_name_is_left_alone(self) -> None:
        """Only the ends are trimmed, or "Zidarski obrt Zidar" would lose its middle."""
        assert normalize_company("Zidarski obrt Zidar") == "zidarski obrt zidar"


class TestComparing:
    def test_the_same_firm_written_two_ways(self) -> None:
        assert same_company("Ericsson Nikola Tesla d.d.", "ERICSSON NIKOLA TESLA")

    def test_different_firms_stay_different(self) -> None:
        assert not same_company("Geodetski zavod d.o.o.", "Geodetski institut d.o.o.")

    def test_nothing_matches_nothing(self) -> None:
        """Two names that are both only a legal form are not the same employer."""
        assert not same_company("d.o.o.", "d.o.o.")
        assert not same_company("", "")
