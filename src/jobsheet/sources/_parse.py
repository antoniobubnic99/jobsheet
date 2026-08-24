"""Shared parsing helpers: feeds in, readable text out.

Kept in one place because the awkward cases are not specific to any one site and
were all learned the same way -- by getting mojibake or half a tag into a
spreadsheet cell and going back to find out why.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from xml.etree import ElementTree

from jobsheet.core.dates import parse_date

__all__ = ["FeedItem", "labelled_fields", "parse_feed", "strip_html"]

_TAGS = re.compile(r"<[^>]+>")
_ENTITY = re.compile(r"&[A-Za-z]+;")
_UNCLOSED_TAG = re.compile(r"<[^>]*$")
_WHITESPACE = re.compile(r"\s+")

_ATOM = "{http://www.w3.org/2005/Atom}"


def strip_html(text: str | None) -> str:
    """HTML fragment -> one readable line.

    Two things here are not obvious:

    * **Unescaping runs up to four times.** Some publishers escape their output
      more than once, so a non-breaking space arrives as `&AMP;AMP;NBSP;`. One
      pass leaves `&AMP;NBSP;` sitting in the cell.
    * **`html.unescape` is case-sensitive**, and those same publishers shout
      their entities in capitals, so each entity is lower-cased before resolving.

    Feeds also truncate descriptions to a fixed length, which regularly cuts a
    tag in half, so a trailing unclosed tag is dropped rather than shown.
    """
    if not text:
        return ""
    for _ in range(4):
        resolved = _ENTITY.sub(lambda m: html.unescape(m.group(0).lower()), html.unescape(text))
        if resolved == text:
            break
        text = resolved
    text = _UNCLOSED_TAG.sub(" ", _TAGS.sub(" ", text))
    return _WHITESPACE.sub(" ", text).strip()


@dataclass
class FeedItem:
    """One entry of an RSS or Atom feed, before it becomes a `Posting`."""

    title: str = ""
    link: str = ""
    description: str = ""
    published: date | None = None
    author: str = ""
    categories: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


def _text(element: ElementTree.Element | None) -> str:
    return "" if element is None or element.text is None else element.text.strip()


def _atom_link(entry: ElementTree.Element) -> str:
    """Atom puts the URL in an attribute, and often offers several."""
    fallback = ""
    for link in entry.findall(f"{_ATOM}link"):
        relation = link.get("rel", "alternate")
        href = link.get("href", "")
        if relation == "alternate" and href:
            return href
        fallback = fallback or href
    return fallback


def parse_feed(xml_text: str) -> list[FeedItem]:
    """Parse RSS 2.0 or Atom. Returns an empty list rather than raising.

    A feed that has gone temporarily malformed should cost the user that one
    source for one run, not the whole search.
    """
    try:
        # S314: feed bodies are untrusted, but ElementTree has no external-entity
        # support, so the residual risk is entity expansion, which the size of a
        # normal feed response bounds in practice.
        root = ElementTree.fromstring(xml_text.strip())  # noqa: S314
    except ElementTree.ParseError:
        return []

    items: list[FeedItem] = []

    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        if tag == "item":
            items.append(
                FeedItem(
                    title=strip_html(_text(node.find("title"))),
                    link=_text(node.find("link")) or _text(node.find("guid")),
                    description=strip_html(_text(node.find("description"))),
                    published=parse_date(
                        _text(node.find("pubDate")) or _text(node.find("date"))
                    ),
                    author=strip_html(_text(node.find("author"))),
                    categories=[strip_html(_text(c)) for c in node.findall("category")],
                )
            )
        elif tag == "entry":
            content = _text(node.find(f"{_ATOM}content")) or _text(node.find(f"{_ATOM}summary"))
            author = node.find(f"{_ATOM}author")
            items.append(
                FeedItem(
                    title=strip_html(_text(node.find(f"{_ATOM}title"))),
                    link=_atom_link(node),
                    description=strip_html(content),
                    published=parse_date(
                        _text(node.find(f"{_ATOM}published"))
                        or _text(node.find(f"{_ATOM}updated"))
                    ),
                    author=strip_html(_text(author.find(f"{_ATOM}name")) if author else ""),
                    categories=[
                        c.get("term", "") for c in node.findall(f"{_ATOM}category") if c.get("term")
                    ],
                )
            )

    return items


def labelled_fields(text: str, labels: tuple[str, ...]) -> dict[str, str]:
    """Pull `Label: value` pairs out of a run-on string.

    Several feeds flatten a whole structured record into one description, as
    `Job description: ..., Category: ..., Deadline: ..., Location: ...`.

    Splitting on the comma is the obvious approach and it is wrong, because the
    values contain commas themselves -- a job description will happily run to
    three clauses. Splitting on the *known labels* is what actually works, so the
    caller passes the vocabulary in.
    """
    if not text or not labels:
        return {}

    alternatives = "|".join(re.escape(label) for label in labels)
    pattern = re.compile(rf"({alternatives})\s*:\s*", re.IGNORECASE)

    matches = list(pattern.finditer(text))
    found: dict[str, str] = {}
    for index, current in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        value = text[current.end() : end].strip().rstrip(",").strip()
        if value:
            found[current.group(1)] = value
    return found
