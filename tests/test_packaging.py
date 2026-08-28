"""The interface has to survive `pip install`.

`src/jobsheet/web/` is a build artifact, so it is gitignored -- and hatchling
honours `.gitignore`. Left alone, a wheel carries the `.gitkeep` and nothing
else: the installed server starts, answers the API, and serves the "interface
has not been built" placeholder. No step of the build fails. The release is
just quietly broken, and only a user finds out.

So these tests build real distributions and look inside them. They are the lock
on `[tool.hatch.build.targets.*] artifacts` in `pyproject.toml`; delete either
and the other stops meaning anything.
"""

from __future__ import annotations

import os
import tarfile
import zipfile
from pathlib import Path
from typing import NoReturn

import pytest

import jobsheet
from jobsheet.api.app import WEB_ROOT

PACKAGE_ROOT = Path(jobsheet.__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parents[1]

# Where the frontend has to land inside each kind of distribution. A wheel is
# rooted at the import package; an sdist keeps the source layout. Both are
# derived from where the server actually looks, rather than typed out again --
# renaming the directory should break the build, not silently pass the test.
WHEEL_PREFIX = f"{PACKAGE_ROOT.name}/{WEB_ROOT.name}"
SDIST_PREFIX = WEB_ROOT.relative_to(PROJECT_ROOT).as_posix()

# The file `web_is_built()` tests for. Without it the server shows the
# placeholder, so its absence from a distribution is the whole failure mode.
ENTRY_POINT = "index.html"

# Set in CI so "the frontend was never built" reports as a failure instead of a
# skip. Locally a skip is right: a developer who has not run `npm run build`
# has not broken packaging.
STRICT = "JOBSHEET_ASSERT_PACKAGED_WEB"


def _frontend_files(prefix: str) -> set[str]:
    """Every file of the built frontend, as paths inside a distribution.

    `.gitkeep` is left out: it exists to keep the empty directory in git and is
    the one thing that *does* get packaged with no configuration at all, so
    counting it would let a broken build look healthy.
    """
    return {
        f"{prefix}/{path.relative_to(WEB_ROOT).as_posix()}"
        for path in WEB_ROOT.rglob("*")
        if path.is_file() and path.name != ".gitkeep"
    }


def _missing(reason: str) -> NoReturn:
    """Skip, unless CI has asked for these tests to be non-negotiable.

    A developer who has not run `npm run build` has not broken packaging, so
    locally this is a skip. In CI a skip would be indistinguishable from a
    pass, which is exactly how the thing these tests guard gets released.
    """
    if os.environ.get(STRICT):
        pytest.fail(reason)
    pytest.skip(reason)


def _require_built_frontend() -> None:
    if not (WEB_ROOT / ENTRY_POINT).is_file():
        _missing("frontend is not built -- run `npm run build` in web/ before packaging")


def _build(kind: str, out: Path) -> str:
    """Build one distribution. hatchling reads the project from the cwd."""
    try:
        from hatchling import build as hatchling_build
    except ImportError:  # pragma: no cover - depends on the environment
        _missing("hatchling is not installed, so no distribution can be built")

    if not (PROJECT_ROOT / "pyproject.toml").is_file():
        # Reached when the tests run against an installed (non-editable)
        # jobsheet, where the import path says nothing about where the source
        # is. Better to say so than to have hatchling fail somewhere confusing.
        _missing(f"no pyproject.toml at {PROJECT_ROOT} -- run the tests from a source checkout")

    builder = getattr(hatchling_build, f"build_{kind}")
    cwd = Path.cwd()
    try:
        os.chdir(PROJECT_ROOT)
        name: str = builder(str(out))
    finally:
        os.chdir(cwd)
    return name


@pytest.fixture(scope="module")
def wheel_contents(tmp_path_factory: pytest.TempPathFactory) -> set[str]:
    """Build a wheel the way `pip install .` would, and list what is in it."""
    _require_built_frontend()
    out = tmp_path_factory.mktemp("wheel")
    with zipfile.ZipFile(out / _build("wheel", out)) as archive:
        return set(archive.namelist())


@pytest.fixture(scope="module")
def sdist_contents(tmp_path_factory: pytest.TempPathFactory) -> set[str]:
    """Same for the sdist: `pip install --no-binary` has to work too."""
    _require_built_frontend()
    out = tmp_path_factory.mktemp("sdist")
    with tarfile.open(out / _build("sdist", out)) as archive:
        # An sdist nests everything under `<name>-<version>/`; strip that so
        # the paths read like the project's own.
        return {member.name.split("/", 1)[1] for member in archive if "/" in member.name}


def test_wheel_carries_the_interface_entry_point(wheel_contents: set[str]) -> None:
    assert f"{WHEEL_PREFIX}/{ENTRY_POINT}" in wheel_contents


def test_wheel_carries_every_built_frontend_file(wheel_contents: set[str]) -> None:
    """Not just the entry point -- a page with no CSS or JS is still broken."""
    expected = _frontend_files(WHEEL_PREFIX)
    assert expected, "the built frontend is empty, which is itself a bug"
    assert expected <= wheel_contents


def test_wheel_carries_scripts_and_styles(wheel_contents: set[str]) -> None:
    """Stated apart so a bundler that stops emitting one of them is caught."""
    packaged = _frontend_files(WHEEL_PREFIX) & wheel_contents
    for suffix in (".js", ".css"):
        assert any(name.endswith(suffix) for name in packaged), f"no {suffix} in the wheel"


def test_sdist_carries_the_interface(sdist_contents: set[str]) -> None:
    """An sdist without the frontend builds a wheel without the frontend."""
    assert f"{SDIST_PREFIX}/{ENTRY_POINT}" in sdist_contents
    assert _frontend_files(SDIST_PREFIX) <= sdist_contents


# --- The version has to be one number, not two -------------------------------
#
# `pyproject.toml` is what the wheel is named after, and `release.yml` refuses
# to publish when the tag disagrees with it. But nothing was comparing either of
# them to `jobsheet.__version__`, which is typed out separately and is what the
# CLI's `--version`, `/api/health` and the outgoing User-Agent actually report.
# Bump one and forget the other and the release is a wheel called 0.1.0 that
# introduces itself as 0.1.0.dev0 everywhere it goes -- and no step of the
# release says a word about it.
#
# This lives in this file on purpose: `release.yml` runs *this file* before it
# publishes anything, so a mismatch stops the release rather than shipping.


def _declared_version() -> str:
    """The version in `pyproject.toml` -- the one the wheel is named after."""
    import tomllib

    pyproject = PROJECT_ROOT / "pyproject.toml"
    if not pyproject.is_file():
        _missing(f"no pyproject.toml at {PROJECT_ROOT} -- run the tests from a source checkout")
    with pyproject.open("rb") as handle:
        version: str = tomllib.load(handle)["project"]["version"]
    return version


def test_the_package_reports_the_version_it_was_built_with() -> None:
    declared = _declared_version()
    assert jobsheet.__version__ == declared, (
        f"jobsheet.__version__ is {jobsheet.__version__!r} but pyproject.toml says "
        f"{declared!r} -- both have to be changed, they are typed out separately"
    )


def test_the_wheel_is_named_after_that_same_version(wheel_contents: set[str]) -> None:
    """Belt and braces: prove it from the built artifact, not just the source."""
    expected = f"jobsheet-{_declared_version()}.dist-info/METADATA"
    assert expected in wheel_contents, (
        f"no {expected} in the wheel -- built version and declared version disagree"
    )
