<div align="center">

# JobSheet

**Collect job ads from anywhere. Get a spreadsheet you actually own.**

A local-first desktop app that pulls vacancies from job boards, applicant tracking
systems and plain RSS feeds, then writes them into an Excel workbook *you* design —
your columns, your names, your colours — without ever destroying the notes and
ticks you added by hand.

No account. No API key. No data leaves your laptop.

</div>

---

## Why

Most job trackers want you to live inside their web app. This one assumes the
opposite: the spreadsheet is the product, and the app exists to keep it fed.

The workbook is a first-class, editable artefact. Add a column, rename a header,
drag it somewhere else, recolour the whole table, type your own notes in a free
column — the next run picks up exactly where you left off and merges new ads in
around your edits.

## Status

Early development. The core engine is being ported and generalised from a working
private predecessor that has been collecting Croatian public-sector and private
vacancies since June 2026.

## Design notes

**The writer never loses your work.** Every save is: check the file is not open →
snapshot the invariants → back up → write → re-read → verify → roll back on any
mismatch. This is not paranoia. The predecessor once wiped 88 hand-placed ticks in
a single run, because re-sorting rewrote the sheet column by column instead of
moving whole rows. Rows are now sorted as objects and only ever written whole.

**Sources are plugins.** A source declares a manifest describing its parameters,
and the user interface builds its own form from that manifest — adding a source
touches no frontend code. Third-party sources install as separate packages and
register through the `jobsheet.sources` entry-point group.

**Only public data.** JobSheet reads public RSS feeds and public job-board APIs,
respects `robots.txt`, rate-limits itself and identifies itself honestly. It does
not log in anywhere, does not solve captchas, and does not touch anything behind
an authentication wall.

## Licence

MIT — see [LICENSE](LICENSE).
