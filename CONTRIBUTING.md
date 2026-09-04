# Contributing

Thank you for looking. The most useful contributions to this project, roughly in
order:

1. **A source that stopped working.** This is the most common bug here and
   usually the easiest fix — a service changed its response and the connector has
   not caught up. There is an issue template for it.
2. **A new source.** Fourteen exist; there are many more. See
   [docs/SOURCES.md](docs/SOURCES.md).
3. **Everything else** — bugs, spreadsheet behaviour, the interface,
   documentation.

---

## Setting up

You need Python 3.11+ and Node 22+ (Node only for the interface).

```bash
git clone https://github.com/antoniobubnic99/jobsheet.git
cd jobsheet

python -m venv .venv
# Windows:  .venv\Scripts\activate
source .venv/bin/activate
pip install -e ".[dev]"

cd web && npm install && npm run build && cd ..
```

**Build the interface before running anything that packages or serves it.** The
order is always `npm run build` first, then Python. The reverse succeeds and
quietly produces a package whose interface is a placeholder page — see
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#packaging-the-trap-worth-knowing).

Then:

```bash
jobsheet                     # opens http://127.0.0.1:8765
jobsheet sources             # what is installed
```

While working on the interface itself, `cd web && npm run dev` gives you hot
reload against a `jobsheet` server running beside it.

---

## Running the checks

Everything CI runs, you can run:

```bash
export JOBSHEET_ASSERT_PACKAGED_WEB=1     # Windows: set JOBSHEET_ASSERT_PACKAGED_WEB=1
pytest -q                                 # the Python suite; no network
ruff check .
mypy

cd web
npm run lint                              # tsc
npx vitest run
```

`JOBSHEET_ASSERT_PACKAGED_WEB=1` turns "the frontend was never built" from a
skipped test into a failure. Without it, a packaging bug passes as green.

### The network tests

```bash
pytest -m network                       # every source against the real service
pytest -m network -k hzz -v             # one source
```

These hit other people's servers. Run them when you touch a connector; do not
run them in a loop. A plain `pytest` never calls anyone —
`addopts = "-m 'not network'"` sees to that.

They run nightly in CI, and they are *allowed* to fail: a third party's outage
must not block a pull request.

### A note on formatting

`ruff check` is used; **`ruff format` deliberately is not.** Comments in this
codebase are written to specific line breaks and a formatter reflows them into
mush. Match the surrounding style by hand — 100 columns, and prose that wraps
where it reads well.

---

## House rules

### Fix the connector *and* refresh the recording

When a live test fails and you fix the parser, update the recorded fixture in
`tests/test_sources_connectors.py` too.

A recorded fixture that went stale with the service it recorded is the worst test
in the codebase: green while the product is dead. That is how one government
source spent an unknown period returning **zero results to every user** with six
passing tests over it. Fixing the parser without refreshing the recording puts
the project straight back in that position.

### Every new source needs a live target

One entry in `tests/test_sources_live.py`. Non-negotiable, for the reason above.
[docs/SOURCES.md](docs/SOURCES.md#tests-two-of-them-and-the-second-is-not-optional)
has the details and the shape.

### Do not delete a test to make the list look clean

If a source is broken and you know why, mark it `broken="…"` with a real
explanation. It becomes an `xfail`, and the day it starts working the `xpass`
announces itself. An open, explained failure is a sign of a healthy project.

### Scope

JobSheet reads **public** data. No logging in, no credential storage, no captcha
solving, nothing behind an authentication wall. `robots.txt` and the service's
own terms are respected, requests are rate-limited per host, and the User-Agent
names the project honestly.

A pull request adding a credentialed source to core will be declined — publish it
as your own package instead, which the plugin system exists to support. This is a
constraint on the project, not a gap in it.

### Tests come with behaviour

New behaviour needs a test. Bug fixes need a test that fails before the fix. The
suite is fast and offline; there is no reason not to.

---

## Commits and pull requests

Conventional-commit subjects — `feat:`, `fix:`, `docs:`, `refactor:`, `test:`,
`chore:`, `ci:`, `perf:`.

The bodies in this repository are longer than average on purpose: they explain
*why*, and they name the trap that was hit. If your change came out of something
surprising, write that down — it is worth more than the diff.

Before opening a pull request:

- [ ] `pytest -q`, `ruff check .` and `mypy` are clean
- [ ] `npx vitest run` and `npm run lint` are clean, if you touched the interface
- [ ] `pytest -m network -k <source>` passes, if you touched a connector
- [ ] the recorded fixture is refreshed, if you fixed a connector
- [ ] documentation is updated when behaviour changed

### What CI runs

| Job | What it proves |
|---|---|
| `frontend` | the interface type-checks, tests, builds — and the build leaves the tree clean |
| `lint` | ruff and mypy |
| `test` | 3.11 / 3.12 / 3.13 × Ubuntu / Windows / macOS. The Windows row is not a formality: the `.js`-served-as-`text/plain` blank-page bug came from there |
| `package` | builds a wheel and an sdist, installs the wheel into a clean venv, starts the server and checks it is **not** serving the placeholder page |

Nightly runs the live sources. Releases are tag-driven and publish to PyPI
through trusted publishing — there is no token anywhere.

`release.yml` also builds the portable Windows ZIP on a Windows runner and
attaches it to the Release. That job is *not* gated on the tag, so it can be
proved before one exists:

```bash
gh workflow run release.yml --ref main -f dry_run=true
```

A dry run builds everything and publishes nothing.

---

## Reporting a bug

Templates exist for the three common shapes:

* **A source stopped working** — include the output of
  `pytest tests/test_sources_live.py -m network -k <source id>`; it is most of
  the answer.
* **Something else is broken**
* **Suggest a new source**

Questions about *using* JobSheet belong in Discussions rather than issues.

If your report involves your workbook, remember it contains your own job search.
Send a cut-down file, not your real one.

---

## Code of conduct

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
