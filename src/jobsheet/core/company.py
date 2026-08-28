"""Employer names, compared the way a person compares them.

"Ericsson Nikola Tesla d.d.", "ERICSSON NIKOLA TESLA" and `Ericsson Nikola
Tesla  d.d.` are one company to anybody reading them and three different strings
to a computer. That matters twice in JobSheet: when the wizard offers employers
it has already seen, and when it checks that the one you just typed is among
them.

Legal forms come off because they are noise for this purpose -- nobody thinks of
their old employer as "d.o.o." -- and because feeds are inconsistent about them:
the same firm is `d.o.o.`, `D.O.O.` and `d. o. o.` across three ads.

The comparison is deliberately *not* used to filter. `excluded_employers` still
matches on the raw name through `matching.fold`, because the filter's job is to
be predictable, and a normaliser that quietly decided two names were the same
would be a filter that skipped an ad the user never named.
"""

from __future__ import annotations

import re

from jobsheet.core.matching import fold

__all__ = ["LEGAL_FORMS", "normalize_company", "same_company"]

# Croatian and the neighbours' legal forms, plus the English ones that turn up in
# ATS feeds. Ordered longest first so "j.d.o.o." is not left as a stray "j".
LEGAL_FORMS = (
    "j.d.o.o.", "d.o.o.", "d.d.", "d.n.o.", "k.d.", "obrt", "zadruga", "ustanova",
    "s.p.", "d.o.o.e.l.", "a.d.", "gmbh", "ltd", "llc", "inc", "plc", "s.a.", "b.v.",
    "n.v.", "oy", "ab", "as", "sp. z o.o.",
)

# The dots inside a legal form are optional in practice ("d o o" happens), so the
# pattern is built from the letters and tolerates whatever punctuation is between.
_FORMS = "|".join(
    r"\.?\s*".join(re.escape(ch) for ch in form.replace(".", "").replace(" ", ""))
    for form in sorted(LEGAL_FORMS, key=len, reverse=True)
)
_TRAILING_FORM = re.compile(rf"(?:^|[\s,\-]+)(?:{_FORMS})\.?\s*$", re.IGNORECASE)
# A few of them lead instead: "Obrt Zidar", "Zadruga Sunce". Only these, and only
# at the very front -- stripping "ab" or "as" from the head of a name would eat
# words. Croatian ads put the rest at the end.
_LEADING_FORM = re.compile(r"^\s*(?:obrt|zadruga|ustanova)\b[\s,\-]*", re.IGNORECASE)
# Spelled out rather than escaped: these are the quote marks feeds actually use,
# and a line of “ would be unreadable for no gain. RUF001 is about ambiguous
# characters in strings meant for people; here they are the subject.
_QUOTES = re.compile("[\"'“”„«»‘’`]")  # noqa: RUF001
_SPACES = re.compile(r"\s+")


def normalize_company(name: str) -> str:
    """An employer name reduced to what a person would call the company.

    Quotes go, punctuation runs collapse, legal forms come off the end -- more
    than one, because "Firma d.o.o. obrt" exists -- and what is left is folded,
    so accents and capitals stop mattering. An empty answer is possible and
    means "this was only a legal form", which no comparison should treat as a
    match with anything.
    """
    cleaned = _QUOTES.sub(" ", name or "")
    cleaned = _SPACES.sub(" ", cleaned).strip(" ,.-")

    # Repeatedly, not once: a name can end in two of them.
    while True:
        shorter = _LEADING_FORM.sub("", _TRAILING_FORM.sub("", cleaned)).strip(" ,.-")
        if shorter == cleaned:
            break
        cleaned = shorter

    return _SPACES.sub(" ", fold(cleaned)).strip()


def same_company(left: str, right: str) -> bool:
    """Whether two employer names name the same employer. Empty never matches."""
    normalised = normalize_company(left)
    return bool(normalised) and normalised == normalize_company(right)
