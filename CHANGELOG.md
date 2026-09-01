# Changelog

All notable changes to this project are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-09-01

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

**Accounts**

- A username and a password on first run, then a wizard that asks the questions
  the search screen otherwise expects you to already know the answers to.
  Finishing it lands you on a search that is ready to run.
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

**The wizard**

- Seven steps, each one question. The keywords step says what a keyword actually
  matches — the start of a word, not a substring — offers words taken from the
  headline that you can wave away, and warns rather than refuses when you leave
  it empty.
- Croatian places to pick from: 21 counties, 128 towns and 427 municipalities in
  `jobsheet.data.places_hr`, served by `GET /api/places`. Suggestions only —
  typing your own still works, because not every source is Croatian. Choosing a
  county pre-ticks the matching HZZ feed on the sources step.
- Employers you have already seen, taken from your own rows, offered by
  `GET /api/postings/companies` and merged through a new `normalize_company`.
  Naming one as a dream employer raises a flag that writes a star into the note.
  It never rejects anything.
- The contract types you want, as tick boxes. An ad that does not say which
  contract it offers **passes** and carries a flag, because half the sources
  never say.
- Sources grouped by country, with "tick all", "Croatia only" and "untick all".
  Every route carries its default parameters, so HZZ cannot end up selected
  without the counties it requires.
- The last step picks the folder with the folder browser and checks the path as
  you type, instead of failing at the end.
- A saved search carries a version number and is migrated forward on load, so
  changing the model no longer breaks every search saved before it.

**A home screen**

- `/` is now a home screen: one large "run the search", a second button to the
  job list, and a read-only summary of the parameters. The form moved to
  `/search/edit` unchanged. The summary reads the same saved setup the editor is
  built from, so the two cannot drift apart.

**Search you can watch**

- A second channel alongside the running log: per-source progress with a phase,
  a count and a percentage, computed on the server in bands per phase (fetch
  0–40, filter 40–70, details 70–100), so a source that knows its own size moves
  inside its band instead of jumping between them.
- The log moved behind "show details", and a full-width button sits under the
  bar — including when the search fails, which until now produced no way out.
- `applications.run_id` (migration 3), `GET /api/postings?run=` and
  `GET /api/postings/runs`: two searches on the same morning can now be told
  apart, which `found_at` — a date — could not do.

**Results as sifting**

- A source column, and status off the row: an undecided ad offers Keep or
  Discard, a decided one states its status as a fact. Status is set in tracking
  from now on.
- Once the page is sifted, "continue to tracking" appears.

**Never the same job twice**

- Discarded ads stay in the database, where de-duplication finds them.
- A `forgotten` table: deleting an ad used to leave it free to return on the
  next search, which looked exactly like deletion not working.
- A `filtered_out` table: ads the filter rejected were remembered nowhere, so
  each one was fetched *and enriched* again on every run — one HTTP request per
  ad, against the same enrichment budget. The memory is tied to a fingerprint of
  the profile, so changing the search brings those ads back up for decision
  rather than burying them.
- `seen_pairs` no longer discards real jobs. The (title, employer) key was
  seeded from every existing row, so a second "Software Engineer" at the same
  employer never appeared again — silently, as a duplicate. It now works the way
  both comments in the code already claimed: rejecting within a run, and merely
  flagging across runs.
- An ad with no URL is reported as `no_url` instead of being counted a duplicate.

**Tracking**

- A profile menu in the bar at every width: who is signed in, my search,
  settings, and a sign-out that asks first. Below 768px the app used to say
  neither who was signed in nor how to leave — on a machine that can hold
  several separate job searches.
- A card is dragged from anywhere on it, not by a two-pixel handle. A click
  anywhere opens the details; 5px separates a click from a drag. The details
  dialog gained what it was missing: status, the link to the ad, the covering
  letter and Discard.
- Arrows above each column send the top card to the neighbouring column, off at
  the edges. The board scrolls sideways, so dragging between columns on a phone
  meant dragging a card past the edge of the screen and hoping the board would
  follow. It will not.
- The workbook path can be changed from settings, with a folder browser and a
  "move the existing spreadsheet there" tick box, which is on by default —
  without it you keep opening the old file while JobSheet writes elsewhere. The
  server refuses to move onto something that already exists, or while the file
  is open in Excel, and records the new path only after the move succeeded.

### Changed

- `Database.known_keys()` now means "the ads this account tracks" rather than
  "every ad ever seen". The ad table is shared, so it can no longer answer the
  older question for one account without answering it wrongly for the others.
- Upgrading a database written before accounts hands everything in it to a
  passwordless account, which the sign-in screen offers to claim. No data moves
  and no workbook path changes.
- "Skipped" is now "Discarded", and sits first on the board rather than beside
  "Rejected" — being rejected is the employer saying no, discarding is you. The
  status value, its colour token and the spreadsheet rule are untouched; only
  the label changed. The board also draws the order the server sends, so that
  order no longer lives in two places.
- Screen numbering comes from one place, so the bar and the screen title cannot
  disagree, and a screen outside the bar has no number instead of borrowing one
  that belongs to another.

### Fixed

- The wizard no longer vanishes when the gate re-renders. Four screens of typing
  went with it; the draft is now kept per account in `sessionStorage` and
  cleared on a successful finish.
- A duplicate no longer eats what you typed in a chip field: the text stays and
  the existing chip is briefly marked. Backspace now takes two presses — the
  first marks the last chip, the second deletes it.
- A source with nothing to enrich no longer reports 100% under a label saying
  details are being checked. Only sources with pages to open enter that phase.
- The folder browser survives a response that carries no folder list, which took
  the whole page down with it.
- The "sign in" button no longer appears and then disappears on a fresh install:
  the page waits for the door to answer instead of guessing.

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

[0.1.0]: https://github.com/antoniobubnic99/jobsheet/releases/tag/v0.1.0
