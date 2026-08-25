#!/usr/bin/env sh
# Gives macOS and Linux the same thing the Windows ZIP gives: something to
# double-click.
#
# There is no embedded interpreter here and there does not need to be -- both
# platforms ship Python, and `pipx install jobsheet` puts a working command on
# PATH without disturbing the system one. What is missing is the double-click,
# because "open a terminal and type a command" is exactly the step that loses
# the people this project is for.
#
#   sh scripts/make-launcher.sh
#
# Safe to run again; it overwrites its own launcher and touches nothing else.

set -eu

APP="JobSheet"

fail() { printf '%s\n' "$*" >&2; exit 1; }

# Find the command rather than assuming it. A pipx install and a `pip install
# --user` put it in different places, and neither is guaranteed to be on PATH
# in the environment a desktop launcher runs under -- which is why the launcher
# gets an absolute path baked into it rather than the bare word `jobsheet`.
JOBSHEET=$(command -v jobsheet 2>/dev/null || true)
if [ -z "$JOBSHEET" ]; then
    for candidate in "$HOME/.local/bin/jobsheet" "/opt/homebrew/bin/jobsheet" "/usr/local/bin/jobsheet"; do
        [ -x "$candidate" ] && { JOBSHEET="$candidate"; break; }
    done
fi
[ -n "$JOBSHEET" ] || fail "jobsheet is not installed. Try:  pipx install jobsheet"

printf 'using %s\n' "$JOBSHEET"

case "$(uname -s)" in
    Darwin)
        # A .command file is the macOS double-click: Terminal runs it, and the
        # window stays open, which is what you want for a server you have to
        # stop by closing it.
        target="$HOME/Desktop/$APP.command"
        cat > "$target" <<EOF
#!/bin/sh
# Opens JobSheet. Close this window to stop it.
exec "$JOBSHEET"
EOF
        chmod +x "$target"
        printf 'Created %s -- double-click it.\n' "$target"
        ;;

    Linux)
        dir="$HOME/.local/share/applications"
        mkdir -p "$dir"
        target="$dir/jobsheet.desktop"
        cat > "$target" <<EOF
[Desktop Entry]
Type=Application
Name=$APP
Comment=Collect job ads from anywhere. Get a spreadsheet you actually own.
Exec=$JOBSHEET
Icon=text-x-spreadsheet
Terminal=true
Categories=Office;Utility;
Keywords=jobs;vacancies;spreadsheet;
EOF
        chmod +x "$target"
        # Some desktops cache the menu and will not show a new entry until told.
        if command -v update-desktop-database >/dev/null 2>&1; then
            update-desktop-database "$dir" >/dev/null 2>&1 || true
        fi
        printf 'Created %s -- look for "%s" in your applications menu.\n' "$target" "$APP"
        ;;

    *)
        fail "Unsupported system: $(uname -s). On Windows, use the ZIP -- see scripts/build-windows-zip.ps1."
        ;;
esac
