"""Feed and text parsing helpers.

The awkward cases here are all real: each one produced a visibly wrong cell in a
spreadsheet before it was understood.
"""

from __future__ import annotations

from datetime import date

import pytest

from jobsheet.sources._parse import labelled_fields, parse_feed, strip_html


class TestStripHtml:
    def test_tags_are_removed(self) -> None:
        assert strip_html("<p>Hello <b>world</b></p>") == "Hello world"

    def test_entities_are_resolved(self) -> None:
        assert strip_html("Caf&eacute; &amp; bar") == "Café & bar"

    def test_double_escaped_entities_are_resolved(self) -> None:
        """Some publishers escape their output more than once.

        A single unescape pass leaves `&AMP;NBSP;` sitting in the cell.
        """
        assert "&" not in strip_html("a&amp;amp;nbsp;b")

    def test_uppercase_entities_are_resolved(self) -> None:
        """`html.unescape` is case-sensitive; these feeds shout everything."""
        assert "&AMP;" not in strip_html("Sales &AMP; Marketing")

    def test_truncated_trailing_tag_is_dropped(self) -> None:
        """Descriptions are cut to a fixed length, often mid-tag."""
        assert strip_html("Some text <div class=") == "Some text"

    def test_whitespace_is_collapsed(self) -> None:
        assert strip_html("a\n\n   b\tc") == "a b c"

    def test_empty_input(self) -> None:
        assert strip_html(None) == ""
        assert strip_html("") == ""


RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>Example jobs</title>
  <item>
    <title>Data Analyst</title>
    <link>https://example.test/j/1</link>
    <description>&lt;p&gt;Work with data&lt;/p&gt;</description>
    <pubDate>Mon, 24 Aug 2026 09:15:00 +0200</pubDate>
    <category>Data</category>
  </item>
  <item>
    <title>GIS Engineer</title>
    <link>https://example.test/j/2</link>
    <description>Maps</description>
    <pubDate>Sun, 23 Aug 2026 08:00:00 +0200</pubDate>
  </item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Example</title>
  <entry>
    <title>Backend Engineer</title>
    <link rel="alternate" href="https://example.test/a/1"/>
    <link rel="edit" href="https://example.test/edit/1"/>
    <summary>Build things</summary>
    <published>2026-08-24T09:15:00Z</published>
    <author><name>Example Ltd</name></author>
    <category term="Engineering"/>
  </entry>
</feed>"""


class TestParseFeed:
    def test_rss(self) -> None:
        items = parse_feed(RSS)
        assert len(items) == 2
        assert items[0].title == "Data Analyst"
        assert items[0].link == "https://example.test/j/1"
        assert items[0].description == "Work with data"
        assert items[0].published == date(2026, 8, 24)
        assert items[0].categories == ["Data"]

    def test_atom(self) -> None:
        items = parse_feed(ATOM)
        assert len(items) == 1
        assert items[0].title == "Backend Engineer"
        assert items[0].published == date(2026, 8, 24)
        assert items[0].author == "Example Ltd"
        assert items[0].categories == ["Engineering"]

    def test_atom_prefers_the_alternate_link(self) -> None:
        """Atom offers several links; the readable page is `rel="alternate"`."""
        assert parse_feed(ATOM)[0].link == "https://example.test/a/1"

    def test_malformed_feed_returns_nothing_rather_than_raising(self) -> None:
        """One temporarily broken feed must cost one source, not the whole run."""
        assert parse_feed("<rss><channel><item>") == []
        assert parse_feed("not xml at all") == []
        assert parse_feed("") == []


class TestLabelledFields:
    LABELS = ("Opis posla", "Kategorija", "Rok za prijavu", "Mjesto rada", "Županija")

    def test_splits_on_labels(self) -> None:
        text = (
            "Opis posla: Vodi projekte, izrađuje elaborate, surađuje s uredima, "
            "Kategorija: GRAĐEVINARSTVO, Rok za prijavu: 12.09.2026, Mjesto rada: ZAGREB"
        )
        found = labelled_fields(text, self.LABELS)
        assert found["Kategorija"] == "GRAĐEVINARSTVO"
        assert found["Rok za prijavu"] == "12.09.2026"
        assert found["Mjesto rada"] == "ZAGREB"

    def test_commas_inside_values_do_not_split(self) -> None:
        """Splitting on the comma is the obvious approach and it is wrong.

        The job description below contains three commas of its own.
        """
        text = (
            "Opis posla: Vodi projekte, izrađuje elaborate, surađuje s uredima, "
            "Kategorija: GRAĐEVINARSTVO"
        )
        found = labelled_fields(text, self.LABELS)
        assert found["Opis posla"] == "Vodi projekte, izrađuje elaborate, surađuje s uredima"

    def test_missing_fields_are_simply_absent(self) -> None:
        found = labelled_fields("Mjesto rada: SPLIT", self.LABELS)
        assert found == {"Mjesto rada": "SPLIT"}
        assert "Kategorija" not in found

    @pytest.mark.parametrize("text", ["", "no labels here at all"])
    def test_nothing_to_find(self, text: str) -> None:
        assert labelled_fields(text, self.LABELS) == {}

    def test_no_labels_given(self) -> None:
        assert labelled_fields("Mjesto rada: SPLIT", ()) == {}
