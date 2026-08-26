# Changelog

All notable changes to this project are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

**Accounts**

- A username and a password on first run, then a wizard that asks the eight
  questions the search screen otherwise expects you to already know the answers
  to. Finishing it lands you on a search that is ready to run.
- One install can hold several job searches that never see each other. Ads are
  shared between accounts — an ad is an ad whoever found it — while everything a
  person knows or decides about one is theirs: status, notes, saved searches, run
  history, and their own workbook.
- Passwords are stored as salted scrypt hashes with the cost written into the
  record; session tokens are stored only as SHA-256 digests. Repeated wrong
  guesses are slowed down per username, in memory.
- The session cookie is HttpOnly and SameSite=strict, and does *not* replace the
  per-process page token — a request needs both.
- `jobsheet users` (list, add, set a password) and a global `--user`, which may
  be omitted whenever there is only one account.
- The first account keeps the original flat file layout; later ones get
  `home/users/<id>-<name>/`.
- A front page in front of the sign-in form: what JobSheet does, what the
  spreadsheet looks like, and the sources this install can actually reach —
  named from the registry, so a source plugin appears there by installing it.
  Two ways in from it, "find a job" and "sign in", and the one it offers first
  follows the install.

### Changed

- `Database.known_keys()` now means "the ads this account tracks" rather than
  "every ad ever seen". The ad table is shared, so it can no longer answer the
  older question for one account without answering it wrongly for the others.
- Upgrading a database written before accounts hands everything in it to a
  passwordless account, which the sign-in screen offers to claim. No data moves
  and no workbook path changes.

## [0.1.0] — unreleased

First public release.

### Added

**The spreadsheet you design**

- A `SheetLayout` model: columns, labels, widths, kinds, themes, conditional
  colour rules, and sort order — all derived from one object rather than
  restated in seven places.
- Eight column kinds, including native Excel checkboxes, dates, hyperlinks and a
  constrained status dropdown.
- User-owned columns: anything you invent is created, never written to, and
  preserved across every run.
- Three presets — *default*, *classic checkboxes*, *minimal*.
- A live sheet designer with drag-to-reorder and a preview drawn to look like the
  workbook it will produce.
- The layout is embedded in the workbook itself, so a file you rearranged by hand
  still reads correctly next time.

**A writer that cannot lose your work**

- Every save: refuse if the file is open → count the user's values → back up →
  write → read back → verify → roll back on any mismatch.
- Rows are sorted and written as whole objects; cells are never moved
  independently.
- Timestamped backups, pruned to the most recent 20.

**Sources as plugins**

- 14 connectors, none of which needs an API key or an account: RSS/Atom;
  Greenhouse, Lever, Ashby, Workable, Recruitee, SmartRecruiters; Remotive,
  RemoteOK, Arbeitnow; and for Croatia HZZ Burza rada, Posao.hr, Narodne novine
  and Selekcija.gov.hr.
- Discovery through the `jobsheet.sources` entry-point group — third-party
  sources install as ordinary packages and need no changes here.
- A manifest that describes each source's parameters, from which the interface
  builds its own form.
- One shared rate-limited HTTP client with an honest User-Agent, so politeness is
  not a per-source decision.

**Search and tracking**

- A five-step pipeline — fetch, de-duplicate, filter, enrich, reject — ordered to
  spend as few requests as possible on ads nobody wants.
- Keyword groups with priority, diacritic-insensitive matching, and word-start
  anchoring that handles inflected languages.
- Rejections are reported with a reason rather than silently dropped.
- Local SQLite storage: every posting ever seen, status history, run history and
  source health.
- A kanban tracker: new → applied → interview → offer → rejected / skipped, with
  every change timestamped.
- Covering-letter drafts from a sandboxed template you can replace with your own.

**Interface and command line**

- Five screens (search, results, sheet designer, tracker, settings) in English
  and Croatian, light and dark.
- Served by the same process as the API — one origin, no CORS — bound to
  loopback, with a `Host` check, a per-process token and a strict CSP.
- `jobsheet`, `jobsheet run`, `jobsheet export` and `jobsheet sources`, so the
  whole thing is scriptable from a scheduled task with no window open.
- CSV, JSON and JSONL exporters.

**Packaging**

- Wheel and sdist with the built interface inside, proven by a test that builds
  both and looks in them.
- A portable Windows ZIP carrying its own Python: unpack, double-click, nothing
  installed.
- Launchers for macOS and Linux.
- CI across Python 3.11–3.13 on Ubuntu, Windows and macOS; nightly live checks
  against every source; tag-driven releases to PyPI through trusted publishing.

### Known issues

- **Narodne novine** result parsing has drifted against the site's current
  markup: the institution is never found, titles come back as sentence fragments,
  and the result count is identical at 30, 90 and 365 days, so paging is not
  happening. The live test is marked `xfail` with the full measurement rather
  than removed — see [docs/SOURCES.md](docs/SOURCES.md).
- **Recruitee** has no live target with open roles; its contract test proves the
  endpoint and the parser but not a populated board. Override with
  `JOBSHEET_LIVE_RECRUITEE=<slug>` if you know one.
- **HZZ** ships an empty title on about a quarter of its feed items, in runs. The
  title is recovered by `enrich`, but the keyword filter runs *before*
  enrichment, so such ads can only be matched through their description.

[Unreleased]: https://github.com/antoniobubnic99/jobsheet/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/antoniobubnic99/jobsheet/releases/tag/v0.1.0
