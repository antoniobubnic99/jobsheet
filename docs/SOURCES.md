# Writing a source

A source is a small class that turns someone else's job listings into
`Posting` objects. That is the whole job. It does not open a socket, decide a
rate limit, touch the database, or know that a spreadsheet exists.

The important property: **adding a source touches no interface code.** A source
declares the questions it needs answered — a feed URL, a company slug, a county
number — and the app builds the form for it. That is what makes a third-party
source *installable* rather than something that has to be merged here.

---

## The contract

```python
class Source(abc.ABC):
    manifest: ClassVar[SourceManifest]

    async def fetch(self, params: dict[str, Any], ctx: FetchContext) -> list[Posting]: ...
    async def enrich(self, posting: Posting, ctx: FetchContext) -> Posting: ...
```

Three pieces:

| | What it is |
|---|---|
| `manifest` | a `SourceManifest`: identity, homepage, rate limit, and the parameters the source needs. Read without importing anything heavy. |
| `fetch` | the cheap listing. One request, or a handful. Required. |
| `enrich` | one ad's own page, for fields the listing omitted. Optional; the default returns the posting unchanged. |

The split between `fetch` and `enrich` is about politeness and speed, not tidiness.
`fetch` runs once per source; `enrich` runs once per *surviving* ad, after the
keyword filter has thrown most of them away, and only for sources whose manifest
sets `supports_enrich=True`. See the pipeline order in
[ARCHITECTURE.md](ARCHITECTURE.md#one-search-in-five-steps).

---

## A complete source, start to finish

This is a real, working shape — a JSON board with one endpoint. Nothing is
elided.

```python
"""Acme Jobs — a public JSON board."""

from __future__ import annotations

from typing import Any

from jobsheet.core.dates import parse_date
from jobsheet.core.models import Posting, Workplace
from jobsheet.sources._parse import strip_html
from jobsheet.sources.base import (
    Choice,
    FetchContext,
    ParamSpec,
    Source,
    SourceError,
    SourceManifest,
)

API = "https://api.acmejobs.example/v1/postings"


class AcmeSource(Source):
    manifest = SourceManifest(
        id="acme",
        name="Acme Jobs",
        homepage="https://acmejobs.example/",
        description="Open roles from the Acme public board.",
        rate_limit=1.0,
        params=[
            ParamSpec(
                name="team",
                label="Team",
                kind="select",
                default="all",
                choices=[
                    Choice(value="all", label="Every team"),
                    Choice(value="eng", label="Engineering"),
                ],
            ),
            ParamSpec(name="remote_only", label="Remote only", kind="boolean", default=False),
        ],
    )

    async def fetch(self, params: dict[str, Any], ctx: FetchContext) -> list[Posting]:
        team = self.param(params, "team")
        remote_only = bool(self.param(params, "remote_only"))

        ctx.report("Reading Acme Jobs")
        payload = await ctx.http.get_json(f"{API}?team={team}")
        entries = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            raise SourceError("Acme returned no job list")

        postings: list[Posting] = []
        for job in entries:
            title, link = job.get("title") or "", job.get("url") or ""
            if not title or not link:
                continue
            is_remote = bool(job.get("remote"))
            if remote_only and not is_remote:
                continue

            postings.append(
                Posting(
                    source_id="acme",
                    title=title,
                    url=link,
                    company=job.get("employer") or "",
                    location=job.get("city") or "",
                    workplace=Workplace.REMOTE if is_remote else Workplace.ONSITE,
                    description=strip_html(job.get("body") or ""),
                    posted_at=parse_date(job.get("published")),
                    raw={"id": job.get("id")},
                )
            )
            if len(postings) >= ctx.max_items:
                break

        ctx.report(f"  {len(postings)} from Acme Jobs")
        return postings
```

Then one line of packaging metadata, and it appears in the interface beside the
built-ins:

```toml
[project.entry-points."jobsheet.sources"]
acme = "my_package.acme:AcmeSource"
```

That is the same mechanism the built-in sources use — there is no privileged
internal list. `pip install jobsheet-source-acme` and the source is there.

---

## The manifest

```python
SourceManifest(
    id="acme",                  # stable; it lands in every Posting and in the sheet
    name="Acme Jobs",           # shown to the user
    homepage="https://...",     # linked from the source card
    description="...",          # one line, in the source list
    country=None,               # ISO 3166-1 alpha-2, or None for global
    params=[...],               # the form the interface builds
    rate_limit=0.7,             # seconds between requests to this host
    supports_enrich=False,      # set True only if enrich() does something
    needs_credentials=False,    # see the note below
)
```

`country` only *groups* the list — it never filters anything out. Global sources
sort first, because they work for anybody without configuration.

`needs_credentials` exists for third-party sources that genuinely cannot work
without a key. **Every source shipped with JobSheet has it `False`, and that is a
constraint rather than an accident**: the app is usable without signing up for
anything. A pull request adding a credentialed source to core will be turned
down; publish it as your own package instead.

### Parameters build the form

Each `ParamSpec` becomes one field in the interface. `kind` is a rendering
instruction as much as a type:

| `kind` | Rendered as | Notes |
|---|---|---|
| `text` | single-line input | the default |
| `url` | single-line input, validated | for feed addresses |
| `number` | numeric input | still arrives as a string from the CLI |
| `boolean` | checkbox | |
| `select` | dropdown | needs `choices=[Choice(value=…, label=…)]` |
| `multiselect` | multiple choice | value is a list |

Read them with `self.param(params, "name")`, which falls back to the manifest's
declared default — never with `params["name"]`, which is how a source ends up
raising `KeyError` on a run started from the CLI.

On the command line the same parameters are `--param source:name=value`:

```bash
jobsheet run acme --param acme:team=eng --param acme:remote_only=true
```

Values arrive as strings; your own `ParamSpec` knows what it wanted, so coerce
in the source.

---

## The `FetchContext`

Sources never make their own HTTP client, clock or limits. They receive one:

```python
ctx.http          # the shared, rate-limited, honestly-identified client
ctx.today         # the run's date — pass this around instead of date.today()
ctx.max_items     # ceiling on ads from one run of one source
ctx.max_enrich    # ceiling on detail pages opened per run
ctx.report("…")   # one line of progress; the interface streams these live
```

`ctx.http` offers `get_text`, `get_json` and `get_bytes`, all with a per-host
delay, a timeout, and a User-Agent that names the project and links to it. This
is why a carelessly written source still cannot be rude — it does not own the
socket.

Honour `ctx.max_items`. It protects both the user's patience and someone else's
server.

---

## Producing good `Posting`s

```python
Posting(
    source_id="acme",       # required; must match your manifest id
    title="…",              # required
    url="…",                # required, absolute — it is the identity of the ad
    company="", location="", region="", description="",
    employment_type="", education="", salary="",
    workplace=Workplace.UNKNOWN,   # ONSITE | HYBRID | REMOTE | UNKNOWN
    posted_at=None, deadline=None, # datetime.date or None
    tags=(),
    raw={},                 # anything with no home above
)
```

Rules that come up in review every time:

* **The URL is the identity.** It must be absolute and it must be the ad's own
  page. A URL that is the same for every ad on a board collapses the whole board
  onto one row.
* **Dates are `datetime.date`, converted in the source.** Feeds ship
  `dd.mm.yyyy`, RFC 822, ISO 8601 and .NET `/Date(1724500000000+0200)/`;
  `jobsheet.core.dates.parse_date` handles the common ones. Dropping a timezone
  offset moves every date a day backwards — that is a real bug this project has
  already had.
* **Put anything unmapped in `raw`.** A parser bug can then be diagnosed from
  stored data instead of by re-scraping a page that may no longer exist.
* **Region is not location.** If the service gives you the publishing
  authority's address, that is `region` at best, and often not even that. On one
  government portal, 27% of listings name the capital while the work is
  elsewhere. `location` must be where the job is.
* **`SourceError` for "I cannot produce results".** It is reported and the run
  continues with the other sources; it is never fatal.
* Whitespace is collapsed for you by the model — no need to `.strip()` every
  field.

### `enrich`, when the listing is incomplete

```python
async def enrich(self, posting: Posting, ctx: FetchContext) -> Posting:
    try:
        html = await ctx.http.get_text(posting.url)
    except Exception:
        return posting          # losing extra fields beats losing the ad
    return posting.merged_with(_parse_detail(html, posting))
```

Set `supports_enrich=True` in the manifest, or the pipeline will skip the pass
entirely. Returning the posting unchanged is always a valid answer — including
when the detail fetch failed.

---

## Tests: two of them, and the second is not optional

**1. A recorded test** in `tests/test_sources_connectors.py`, using `respx` to
replay a captured response. It proves your parser understands that shape. It is
fast, deterministic, and runs on every push.

**2. A live target** in `tests/test_sources_live.py`:

```python
Target("acme", {"team": "eng"}),
```

> **Every new source must add one.** This is the rule with the least room for
> negotiation in the project, and it was bought with a real failure.

A recorded fixture goes stale *with* the service it recorded. On 2026-08-25 the
first live run found that a government API had begun wrapping its array in a
`{"Records": […]}` envelope. The connector raised on a dict and returned **zero
results to every user** — for an unknown length of time — while all six recorded
tests stayed green. A green suite over a dead product is worse than no suite.

Live tests are shaped around what a service may legitimately change:

* **Counts are never asserted.** A board with 40 openings today may have 4
  tomorrow, and a test that fails for that is a test people learn to ignore.
* **Shape and meaning are asserted**: a URL that resolves, an identity that
  de-duplicates, a date that is a date and is not in the future.
* **One target, one test.** A dead board must not hide thirteen live ones.
* Third-party slugs are overridable — `JOBSHEET_LIVE_ACME=<slug>` — because
  companies stop hiring. Reach for that before deleting a test: a 404 from one
  board is a bad fixture, a 404 from all of them is news.

They run nightly, not on push:

```bash
pytest -m network                        # everything
pytest -m network -k acme -v             # just yours
```

If your source is broken against the live service and you know why, say so with
`broken="…"` rather than deleting the target. The test then `xfail`s, and the
day someone fixes it, the `xpass` announces itself.

---

## House rules

* **Public data only.** No logging in, no captcha solving, nothing behind an
  authentication wall.
* **Respect `robots.txt`** and the service's own terms.
* **Raise `rate_limit`** for small servers. The default of 0.7 s is aimed at
  boards that expect API traffic; a municipal notice board is not one of those.
* **Fail loudly on your own side, quietly on theirs.** A parse you cannot make
  sense of is a `SourceError`; a single malformed item is a `continue`.

---

## Checklist before opening the pull request

- [ ] `manifest` has a stable `id`, a real `homepage`, and a one-line description
- [ ] every parameter has a `label` a stranger would understand
- [ ] `rate_limit` suits the size of the service
- [ ] `fetch` honours `ctx.max_items` and reports progress
- [ ] dates are parsed into `date`, with the timezone offset respected
- [ ] `location` holds where the job is, not where the employer's head office is
- [ ] a recorded test in `tests/test_sources_connectors.py`
- [ ] **a live target in `tests/test_sources_live.py`**
- [ ] the entry point is registered in `pyproject.toml`
- [ ] `ruff check .` and `mypy` are clean
