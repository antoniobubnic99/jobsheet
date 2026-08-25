# The workbook

The spreadsheet is not an export. It is the thing JobSheet exists to maintain.

That has a consequence most job trackers avoid: the user is allowed to change
it. Add a column, rename a header, drag it somewhere else, recolour the table,
type notes in a free column — and the next run has to fit itself around all of
that without losing a character of it.

This document explains how that is arranged, and what it cost to learn.

---

## The 88 ticks

The predecessor to this project wrote nine hard-coded columns, three of them tick
boxes: *Applied*, *Interview*, *Not applied*. The user ticked them by hand, day
after day, for months.

One run sorted the sheet. The sort rewrote the sheet **column by column** —
reading each column into a list, sorting it, writing it back. Which means each
column was sorted correctly, and each column ended up in a different order.
Values slid up and down independently of the rows they belonged to. Eighty-eight
ticks now sat against the wrong jobs.

Nothing raised. Nothing looked wrong. The file opened cleanly, the colours were
right, the rows were sorted. It was noticed days later, and there was no way to
work out which ticks had been where.

Two structural rules came out of that, and they are the reason this module is
shaped the way it is:

> **1. Rows are sorted and written as whole objects. Cells are never moved.**
>
> **2. A save that cannot prove it preserved the user's work is not a save.**

Neither is a matter of being careful. Care is what failed the first time.

---

## Rule 1: rows are objects

Sorting happens over a list of `JobRow` objects, before a single cell is
touched — `layout.sort_by` names the fields, `sort_descending` says which way.
The writer then lays out whole rows, left to right, in the order it was given.

There is no code path anywhere that reads a column, transforms it, and writes it
back. There cannot be a repeat of the 88 ticks, because the operation that caused
it does not exist.

## Rule 2: the safety envelope

Every call to `writer.save()` does this, in this order:

1. **Refuse if the workbook is open.** Excel holds an exclusive lock and leaves a
   `~$name.xlsx` beside the file; writing now would either fail or lose the
   user's unsaved edits. The error says so in words: *close it and run again*.
2. **Count the user's own values** across every user-owned column.
3. **Back the file up**, timestamped, into `<home>/backups/`.
4. **Write** the new sheet.
5. **Read the file back from disk** — not from memory.
6. **Compare**: same number of rows, same number of user values.
7. **On any mismatch, restore the backup and raise.** The workbook on disk is
   left exactly as it was, and `VerificationFailedError` says what did not add
   up.

Backups are pruned to the most recent 20 (`keep_backups`). The predecessor
accumulated twenty-four in one folder with no ceiling.

There is also a hard row limit (`MAX_ROWS = 50_000`). Anything beyond that is a
runaway loop, not a job search.

---

## The layout is one object

The predecessor hard-coded nine columns and then restated that assumption in
seven places: the header list, the width list, a `range(1, 10)`, a `vals[:6]`
slice, the autofilter reference `A1:I{n}`, the conditional-formatting range
`A2:I500`, and a tuple of checkbox columns `("G", "H", "I")`.

Adding a column meant editing all seven in lockstep. Forgetting one produced a
workbook that looked fine and quietly misbehaved — the conditional formatting
really did stop at row 500 while the writer happily wrote to row 5000.

Here there is one `SheetLayout`, and everything is derived from it:

```python
SheetLayout(
    sheet_name="Jobs",
    theme="navy",
    columns=[ColumnSpec(...), ...],
    freeze_header=True,
    autofilter=True,
    zebra=False,
    rules=[ConditionalRule(...), ...],
    sort_by=["posted_at", "company"],
    sort_descending=True,
)
```

### Columns

```python
ColumnSpec(key="title", label="Position", kind=ColumnKind.TEXT, width=36, wrap=False)
```

`kind` drives cell formatting, the checkbox pass, the status dropdown, and how a
value is parsed on the way back in — so it is a data question, not a cosmetic
one:

| `kind` | Written as | Read back as |
|---|---|---|
| `text` | plain string | string |
| `note` | string, wraps by default | string |
| `date` | real date, `yyyy-mm-dd` | `datetime.date` |
| `url` | a real hyperlink | string |
| `number` | number | number |
| `tags` | list, joined for display | list |
| `checkbox` | native Excel checkbox | bool |
| `status` | constrained text with a dropdown | `ApplicationStatus` |

### The distinction that matters: `user_owned`

A **user-owned** column holds the user's own knowledge — did I apply, what did
they say, my note to self. The writer treats those values as read-only input: it
carries them across a rewrite, counts them before and after, and rolls the whole
file back if the counts differ.

A **source-owned** column is refreshed from the feed on every run.

You rarely set this by hand. It is inferred:

* every `checkbox` and `status` column is user-owned by definition
* every column whose `key` is not in `SOURCE_KEYS` is user-owned — which is to
  say **any column you invent is yours**

`SOURCE_KEYS` is the set JobSheet knows how to fill: `found_at`, `posted_at`,
`deadline`, `title`, `company`, `url`, `location`, `region`, `workplace`,
`employment_type`, `education`, `salary`, `category`, `note`, `source`, `tags`.

So adding a column called `my_notes`, or `salary_i_asked_for`, or `contact` needs
no configuration at all. JobSheet creates it, never writes to it, and preserves
whatever you type there.

### Conditional rules

```python
ConditionalRule(when_column="status", equals="rejected", fill="D9D9D9", stop_if_true=True)
```

Colour a whole row when one column holds a given value. Rules apply in order and
the first `stop_if_true` match wins — which is how *"rejected greys the row out
even though I did apply"* is expressed. Six hex digits are fine; Excel's eighth
pair is added for you.

### Validation the layout does for you

* at least one column
* no duplicate keys
* no duplicate labels, case-insensitively — headers double as the fallback when
  matching a workbook the user rearranged by hand, so they have to stay
  distinguishable
* every rule points at a column that exists

A layout that cannot be loaded back is refused at save time, which is far kinder
than finding out three weeks later.

---

## Presets

| Preset | Shape |
|---|---|
| `default_layout()` | ten columns, one *Status* dropdown, coloured by state, plus an empty *My notes* column |
| `classic_checkboxes_layout()` | the predecessor's nine columns exactly: Applied / Interview / Not applied tick boxes, grey overriding green |
| `minimal_layout()` | four columns, no colour, for people who want a list rather than a system |

`classic_checkboxes_layout` is kept as a first-class preset on purpose: the
original workflow this project generalises still works, unchanged, including grey
taking priority over green.

---

## The layout lives in the file

`writer.save()` embeds the layout as JSON in the workbook's own custom document
properties (`JobSheetLayout`). Consequences:

* A workbook you rearranged in Excel still reads correctly on the next run.
* A column you added **directly in Excel** is picked up and preserved rather than
  wiped.
* You can hand the file to someone else and it carries its own design.

When the embedded layout is missing — a workbook from elsewhere, or one built by
hand — the reader falls back to matching header labels, which is why duplicate
labels are refused.

`writer.export_layout()` gives you the same JSON to save or share, and the
interface's *save this design* button is exactly that.

---

## Working with it from outside

```bash
jobsheet export                        # rewrite the workbook from the database
jobsheet export --layout "My design"   # …using a design saved under that name
jobsheet export csv --out jobs.csv     # or dump it elsewhere
jobsheet export json --status applied --status interview
```

`--layout` takes the *name* of a design you saved in the sheet designer, not a
preset name. With no `--layout`, the workbook's own embedded layout is used.

The order inside `export` is fixed and matters: **your edits are read back
first, then the file is rewritten.** `merge_from_sheet` takes what you changed
in Excel into the database — including rows you pasted in by hand, which are
adopted as `new` rather than rejected — and only then does the writer lay the
sheet out again.

So the database, not the spreadsheet, is the memory. Deleting a row in Excel
removes it from your view; the record that you applied for that job in June
survives, and the row reappears on the next export unless you filter it out with
`--status`.

---

## Things people hit

**"It refuses to write."** The workbook is open in Excel. That is the first step
of the envelope, and it is deliberate.

**"My notes disappeared."** They should not have — the verification step exists
precisely to make that impossible, and it restores the backup rather than let it
happen. If it ever does, `<home>/backups/` holds the last 20 versions and this is
a bug worth reporting with the file.

**"I renamed a header and now there are two columns."** The `key` is the
identity, the `label` is what you see. Renaming in Excel renames the label;
JobSheet matches on the embedded layout first and only falls back to labels.
Rename through the sheet designer if you want both to move together.

**"Checkboxes look like TRUE/FALSE."** Native Excel checkboxes are a recent Excel
feature. In older versions and in LibreOffice the underlying boolean is shown
instead; the data is the same and nothing is lost.

---

## Further reading

* [ARCHITECTURE.md](ARCHITECTURE.md) — how the workbook fits the rest
* [../CONTRIBUTING.md](../CONTRIBUTING.md) — running the tests that guard all this
