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

Working, not yet packaged. The engine, the local API, the command line and the
interface are all in place; installers and CI are what remain.

```bash
pip install -e ".[dev]"          # the Python side
cd web && npm install && npm run build   # the interface, built into the package
jobsheet                         # opens http://127.0.0.1:8765
```

There is also a command line, so the whole thing is scriptable:

```bash
jobsheet sources                       # what is installed
jobsheet run remotive hzz --profile gis
jobsheet export                        # rewrite the workbook
jobsheet export csv --out jobs.csv
```

## What it looks like

Five screens: pick sources and say what you want; read what came back and why;
arrange the spreadsheet; track each application; see where your files are.

The **sheet designer** is the centre of it. Columns on the left, a live preview
on the right that is drawn to look like the workbook it will produce, and a
write button that reads your file before it touches it.

## Where things live

Everything is on your machine, in files you can open:

| What | Where |
|---|---|
| Workbook | `<home>/jobs.xlsx` |
| Database | `<home>/jobsheet.sqlite3` |
| Backups | `<home>/backups/` |

`<home>` is your platform's application-data directory, or whatever
`JOBSHEET_HOME` points at. The interface's Settings screen shows the real paths.

## Design notes

**The writer never loses your work.** Every save is: check the file is not open →
snapshot the invariants → back up → write → re-read → verify → roll back on any
mismatch. This is not paranoia. The predecessor once wiped 88 hand-placed ticks in
a single run, because re-sorting rewrote the sheet column by column instead of
moving whole rows. Rows are now sorted as objects and only ever written whole.

**The interface is served by the same process as the API.** One origin, no
proxy, no CORS. The server listens on `127.0.0.1`, checks the `Host` header so a
hostile domain cannot point its own DNS at loopback, and requires a per-process
token that it hands over by writing it into the page it serves. A page in another
tab can send requests to `127.0.0.1`; it cannot read that token.

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
