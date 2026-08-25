# Examples

Two files, both plain JSON, both validated against the real models — the same
validation the app applies when you save them.

| File | What it is |
|---|---|
| `profile.example.json` | a search profile: what to look for, where, and what to refuse |
| `layout.example.json` | a sheet design: which columns, named what, coloured how |

They describe an invented person — someone looking for a junior data-analyst
role in Zagreb or remote — so read them as a shape to copy, not as advice.

---

## The search profile

The parts worth understanding before you edit it:

**Keyword groups are ordered, and the first match wins.** The group's name is
what lands in the spreadsheet's *Category* column, so the order expresses
priority: *"I would rather be told this is a Data analyst job than a SQL job."*

**Terms match from the start of a word, not the end.** `analy` covers analyst,
analytics and analysis; `sql` will not hide inside `mysqld`. You do not need to
list inflections — which matters much more in an inflected language than in
English.

**Terms are folded**: case and diacritics are ignored, so `vozacka` matches
`vozačka`.

**`locations` decides; `regions` is only consulted when an ad names no place at
all.** Some public sources put the *publishing authority's* address in the region
field, which is how you get offered a job 400 km away.

**`employment_type_allowlist` overrides `excluded_employment_types`.** It exists
because of a real trap: in Croatian, *na neodređeno* (permanent) contains the
substring *određeno* (fixed-term), so blocking fixed-term contracts also blocks
every permanent one. Any allowlist hit wins.

**`flags` never reject anything.** They only annotate the note column, because a
regular expression cannot tell a hard requirement from a nice-to-have.

**`description_match_requires`** applies only when the *sole* keyword hit was in
the description — a weaker signal than a hit in the title — and demands
corroboration from the education field. Leave it empty to switch the rule off.

---

## The sheet design

The interesting columns in `layout.example.json` are the last three:
`applied_on`, `contact` and `my_notes`. None of them is a key JobSheet knows how
to fill, so all three are **yours**: the app creates them, never writes to them,
and preserves whatever you type there across every future run.

Together with `status`, they are what the writer counts before and after a save —
and if the counts do not match afterwards, the whole save is rolled back. See
[../docs/EXCEL.md](../docs/EXCEL.md).

---

## Using them

The natural way is the interface: build a search on the *Search* screen or a
design in the *Sheet designer*, then save it under a name. These files are what
that produces.

To load one directly, either post it to the running app:

```bash
# The token is minted per process and written into the page the app serves.
TOKEN=$(curl -s http://127.0.0.1:8765/ | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

curl -X PUT http://127.0.0.1:8765/api/profiles/search/data-analyst \
     -H "X-JobSheet-Token: $TOKEN" \
     -H "Content-Type: application/json" \
     -d "{\"payload\": $(cat examples/profile.example.json)}"
```

…or write it straight into the database with the app closed:

```python
import json
from pathlib import Path

from jobsheet.config import Settings
from jobsheet.core.matching import SearchProfile
from jobsheet.store.db import Database

payload = json.loads(Path("examples/profile.example.json").read_text(encoding="utf-8"))
profile = SearchProfile.model_validate(payload)      # fail here, not in three weeks

with Database(Settings().database_path) as db:
    db.save_profile("data-analyst", "search", profile.model_dump(mode="json"))
```

Swap `SearchProfile` for `SheetLayout`, the file for `layout.example.json`, and
`"search"` for `"layout"` to do the same with the sheet design.

Then use both without opening a window at all:

```bash
jobsheet run remotive arbeitnow greenhouse --profile data-analyst
jobsheet export --layout my-design
```

`--profile` and `--layout` take the names you saved them under.
