"""The `jobsheet` command.

Four things, and the first one is what most people ever use:

    jobsheet                 open the interface in a browser
    jobsheet run             search from a saved profile, without a browser
    jobsheet export          rewrite the workbook, or dump CSV/JSON
    jobsheet sources         list what is installed

`run` and `export` exist so the whole app is scriptable -- a scheduled task can
refresh a spreadsheet overnight with no window open. They are also what the
tests drive, which keeps the command surface honest.

Argparse rather than a CLI framework: this is a desktop app whose front door is
a double-clicked launcher, and a dependency to render four subcommands would be
a dependency the user pays to install for no benefit.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import socket
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any

from jobsheet import __version__
from jobsheet.config import DEFAULT_PORT, LOCALHOST, Settings
from jobsheet.core.matching import SearchProfile
from jobsheet.exporters.csv import to_csv
from jobsheet.exporters.jsonl import to_json, to_jsonl
from jobsheet.pipeline import SourceRequest, run_search
from jobsheet.sheet import writer
from jobsheet.sheet.layout import SheetLayout
from jobsheet.sources import registry
from jobsheet.store.db import Database
from jobsheet.store.tracker import Tracker, merge_from_sheet

__all__ = ["build_parser", "main"]

PORT_ATTEMPTS = 20


def _say(message: str) -> None:
    print(message, file=sys.stderr)


# ------------------------------------------------------------------ the parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jobsheet",
        description="Collect job ads from anywhere. Get a spreadsheet you actually own.",
    )
    parser.add_argument("--version", action="version", version=f"jobsheet {__version__}")
    parser.add_argument(
        "--home",
        type=Path,
        help="where JobSheet keeps its database, backups and workbook",
    )
    parser.add_argument("--workbook", type=Path, help="path to the .xlsx file")

    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="open the interface (the default)")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.add_argument("--host", default=LOCALHOST)
    serve.add_argument(
        "--no-browser", action="store_true", help="start the server but do not open a window"
    )

    run = sub.add_parser("run", help="search from a saved profile, without the interface")
    run.add_argument("sources", nargs="+", help="source ids, e.g. remotive hzz")
    run.add_argument("--profile", help="name of a saved search profile")
    run.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="SOURCE:NAME=VALUE",
        help="answer one source's parameter, e.g. hzz:county=8",
    )
    run.add_argument("--max-items", type=int, default=200)
    run.add_argument("--max-enrich", type=int, default=40)
    run.add_argument("--no-write", action="store_true", help="search but do not save")

    export = sub.add_parser("export", help="write the workbook or dump the data")
    export.add_argument(
        "format", nargs="?", default="xlsx", choices=["xlsx", "csv", "json", "jsonl"]
    )
    export.add_argument("--out", type=Path, help="where to write (default: standard output)")
    export.add_argument("--layout", help="name of a saved layout profile")
    export.add_argument("--status", action="append", default=[], help="only these statuses")

    sources = sub.add_parser("sources", help="list installed sources")
    sources.add_argument("--json", action="store_true", help="machine-readable output")

    return parser


def _settings_from(args: argparse.Namespace) -> Settings:
    fields: dict[str, Any] = {}
    if args.home:
        fields["home"] = args.home
    if args.workbook:
        fields["workbook"] = args.workbook
    return Settings(**fields).prepare()


# ------------------------------------------------------------------- `serve`


def free_port(host: str, wanted: int) -> int:
    """The first free port at or after `wanted`.

    A user who left JobSheet open in another window should get a second one that
    works, not a stack trace about an address already in use.
    """
    for offset in range(PORT_ATTEMPTS):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((host, wanted + offset))
            except OSError:
                continue
            return wanted + offset
    raise SystemExit(
        f"no free port between {wanted} and {wanted + PORT_ATTEMPTS - 1}. "
        "Close another JobSheet window, or pass --port."
    )


def command_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from jobsheet.api.app import create_app, web_is_built

    settings = _settings_from(args)
    settings = settings.model_copy(
        update={
            "host": args.host,
            "port": free_port(args.host, args.port),
            "open_browser": not args.no_browser,
        }
    )

    _say(f"JobSheet {__version__}")
    _say(f"  home      {settings.home}")
    _say(f"  workbook  {settings.workbook_path}")
    _say(f"  open      {settings.url}")
    if not web_is_built():
        _say("  note      the interface is not built; the API is at /docs")

    if settings.open_browser:
        # After a beat, so the browser does not race the server to the port.
        threading.Timer(0.8, lambda: webbrowser.open(settings.url)).start()

    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_level="warning",
        access_log=False,
    )
    return 0


# --------------------------------------------------------------------- `run`


def parse_params(pairs: list[str]) -> dict[str, dict[str, Any]]:
    """`hzz:county=8` -> `{"hzz": {"county": "8"}}`.

    Values stay strings; each source's own parameter spec knows what it wanted,
    and guessing types here would only produce a different set of surprises.
    """
    parsed: dict[str, dict[str, Any]] = {}
    for pair in pairs:
        if ":" not in pair or "=" not in pair.split(":", 1)[1]:
            raise SystemExit(f"--param must look like SOURCE:NAME=VALUE, not {pair!r}")
        source_id, rest = pair.split(":", 1)
        name, value = rest.split("=", 1)
        parsed.setdefault(source_id, {})[name] = value
    return parsed


def command_run(args: argparse.Namespace) -> int:
    settings = _settings_from(args)
    installed = set(registry.available())
    if unknown := [name for name in args.sources if name not in installed]:
        _say(f"not installed: {', '.join(unknown)}")
        _say(f"try: {', '.join(sorted(installed))}")
        return 2

    params = parse_params(args.param)
    started_at = datetime.now()

    with Database(settings.database_path) as db:
        profile = SearchProfile()
        if args.profile:
            saved = db.load_profile(args.profile, "search")
            if saved is None:
                _say(f"no saved search called {args.profile!r}")
                return 2
            profile = SearchProfile.model_validate(saved)

        report = asyncio.run(
            run_search(
                [
                    SourceRequest(source_id=name, params=params.get(name, {}))
                    for name in args.sources
                ],
                profile,
                existing=db.all_rows(),
                max_items=args.max_items,
                max_enrich=args.max_enrich,
                on_progress=_say,
            )
        )

        for source_id, message in report.errors.items():
            _say(f"  ! {source_id}: {message}")

        if args.no_write:
            _say(f"{report.new_count} new job(s) found; nothing written.")
            return 0

        db.save_rows(report.rows)
        db.record_run(
            fetched=report.fetched,
            added=report.new_count,
            duplicates=report.duplicates,
            rejected=len(report.rejected),
            errors=report.errors,
            started_at=started_at,
        )
        for source_id in args.sources:
            failure = report.errors.get(source_id)
            db.record_source_health(
                source_id,
                ok=failure is None,
                count=report.harvested.get(source_id, 0),
                message=failure or f"{report.harvested.get(source_id, 0)} ad(s)",
            )

    _say(f"{report.new_count} new job(s) saved.")
    return 0


# ------------------------------------------------------------------ `export`


def command_export(args: argparse.Namespace) -> int:
    settings = _settings_from(args)

    with Database(settings.database_path) as db:
        layout: SheetLayout | None = None
        if args.layout:
            saved = db.load_profile(args.layout, "layout")
            if saved is None:
                _say(f"no saved layout called {args.layout!r}")
                return 2
            layout = SheetLayout.model_validate(saved)

        if args.format == "xlsx":
            return _export_workbook(db, settings, layout, args.status)

        rows = _wanted(db, args.status)
        if args.format == "csv":
            text = to_csv(rows, layout or _layout_of(settings.workbook_path))
        elif args.format == "json":
            text = to_json(rows)
        else:
            text = to_jsonl(rows)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        _say(f"wrote {len(rows)} row(s) to {args.out}")
    else:
        sys.stdout.write(text)
    return 0


def _layout_of(path: Path) -> SheetLayout | None:
    return writer.read_layout(path) if path.exists() else None


def _wanted(db: Database, statuses: list[str]) -> list[Any]:
    rows = db.all_rows()
    if statuses:
        wanted = set(statuses)
        rows = [row for row in rows if str(row.status) in wanted]
    return rows


def _export_workbook(
    db: Database, settings: Settings, layout: SheetLayout | None, statuses: list[str]
) -> int:
    """Read the user's edits back first, then rewrite. Never the other way round."""
    path = settings.workbook_path

    if path.exists():
        try:
            existing, _ = writer.load(path)
        except Exception as error:
            _say(f"could not read {path.name}: {type(error).__name__}: {error}")
            return 1
        if changes := merge_from_sheet(Tracker(db), existing):
            _say(f"took back {len(changes)} edit(s) made in the workbook")

    try:
        report = writer.save(
            path,
            _wanted(db, statuses),
            layout or _layout_of(path),
            backup_dir=settings.backup_path,
            keep_backups=settings.keep_backups,
        )
    except writer.SheetLockedError as error:
        _say(str(error))
        return 1
    except writer.VerificationFailedError as error:
        _say(f"the file written did not match what went in ({error}).")
        _say("Your previous workbook has been restored and is untouched.")
        return 1

    _say(f"wrote {report.rows} row(s) to {path}")
    if report.backup:
        _say(f"backup: {report.backup}")
    return 0


# ----------------------------------------------------------------- `sources`


def command_sources(args: argparse.Namespace) -> int:
    manifests = sorted(registry.manifests(), key=lambda m: (m.country or "", m.name.lower()))
    if args.json:
        print(json.dumps([m.model_dump(mode="json") for m in manifests], indent=2))
        return 0

    width = max((len(m.id) for m in manifests), default=0)
    for manifest in manifests:
        where = manifest.country or "global"
        print(f"{manifest.id.ljust(width)}  {where:<7} {manifest.name} -- {manifest.homepage}")
    return 0


COMMANDS = {
    "serve": command_serve,
    "run": command_run,
    "export": command_export,
    "sources": command_sources,
}


def main(argv: list[str] | None = None) -> int:
    """Entry point. Bare `jobsheet` opens the interface, which is what a shortcut does."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        # Fill in the defaults `serve` would have parsed, so a double-clicked
        # launcher and `jobsheet serve` behave identically.
        args = parser.parse_args([*(argv or []), "serve"])

    try:
        return COMMANDS[args.command](args)
    except KeyboardInterrupt:
        _say("\nStopped.")
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
