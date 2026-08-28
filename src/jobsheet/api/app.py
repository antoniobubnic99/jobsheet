"""The one process that serves both the API and the interface.

A user has no Node and no Python; they double-click a launcher and a browser
window opens. That constraint shapes this file: the built frontend is ordinary
static files inside the package, served from the same origin as the API, so
there is no second server, no proxy configuration and no CORS to get wrong.

The token is handed to the interface by writing it into the page itself. That is
the only place it appears, and a page on another origin cannot read this one --
no CORS headers are sent, on purpose.
"""

from __future__ import annotations

import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from jobsheet import __version__
from jobsheet.api.routers import (
    applications,
    auth,
    export,
    layouts,
    letter,
    places,
    postings,
    profiles,
    search,
    sources,
)
from jobsheet.api.routers import (
    settings as settings_router,
)
from jobsheet.api.state import AppState
from jobsheet.config import Settings

__all__ = ["WEB_ROOT", "create_app", "web_is_built"]

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"

# Windows resolves media types through the registry, where a stray installer can
# leave `.js` mapped to `text/plain`. A browser then refuses to run the module
# and the interface is a blank page -- with nothing in the server log to say so.
# Stating the types we serve removes a whole class of "it works on my machine".
for _suffix, _media_type_name in (
    (".js", "text/javascript"),
    (".mjs", "text/javascript"),
    (".css", "text/css"),
    (".json", "application/json"),
    (".svg", "image/svg+xml"),
    (".woff2", "font/woff2"),
):
    mimetypes.add_type(_media_type_name, _suffix)

ROUTERS = (
    # Auth first: its own routes are the only ones a signed-out browser can
    # reach, and registering them ahead of the rest keeps that visible here.
    auth.router,
    settings_router.router,
    sources.router,
    search.router,
    postings.router,
    places.router,
    applications.router,
    layouts.router,
    profiles.router,
    export.router,
    letter.router,
)

# The interface loads nothing from anywhere else, so it can say so. Anything
# that tries to reach the network from inside the page is a bug or an intrusion,
# and either way it should fail loudly rather than quietly succeed.
CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "form-action 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'"
)

PLACEHOLDER = """\
<!doctype html>
<meta charset="utf-8">
<title>JobSheet</title>
<style>
  body {{ font: 16px/1.6 system-ui, sans-serif; max-width: 40rem; margin: 4rem auto;
         padding: 0 1.5rem; color: #16202c; background: #f7f8fa; }}
  code {{ background: #e8ebef; padding: .1em .35em; border-radius: .25em; }}
  a {{ color: #1f4e79; }}
</style>
<h1>JobSheet {version}</h1>
<p>The API is running, but the interface has not been built into this install.</p>
<pre><code>cd web
npm install
npm run build</code></pre>
<p>The API itself is browsable at <a href="/docs">/docs</a>.</p>
"""


def web_is_built() -> bool:
    """Whether a built frontend is sitting in the package."""
    return (WEB_ROOT / "index.html").is_file()


def _index_html(token: str) -> str:
    """The interface, with this process's token written into it."""
    handshake = (
        f'<script>window.__JOBSHEET__={{"token":"{token}","version":"{__version__}"}};</script>'
    )
    if not web_is_built():
        return PLACEHOLDER.format(version=__version__) + handshake

    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    if "</head>" in html:
        return html.replace("</head>", f"{handshake}</head>", 1)
    return handshake + html


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    state: AppState = app.state.jobsheet
    try:
        yield
    finally:
        await state.aclose()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build an app around one home directory. Tests build their own."""
    settings = settings or Settings()

    app = FastAPI(
        title="JobSheet",
        version=__version__,
        summary="Collect job ads from anywhere. Get a spreadsheet you actually own.",
        lifespan=_lifespan,
    )
    app.state.jobsheet = AppState(settings)

    for router in ROUTERS:
        app.include_router(router)

    @app.middleware("http")
    async def _harden(request: Request, call_next: Any) -> Any:
        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    @app.get("/api/health", include_in_schema=False)
    async def health() -> JSONResponse:
        """Says nothing, needs no token: the launcher polls it to learn the port is up."""
        return JSONResponse({"status": "ok", "version": __version__})

    if web_is_built():
        # Mounted under a prefix rather than at "/" so that the index page keeps
        # going through the handler below, which is what injects the token.
        app.mount("/assets", StaticFiles(directory=WEB_ROOT / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    @app.get("/{path:path}", include_in_schema=False)
    async def index(path: str = "") -> HTMLResponse:
        """Serve the interface. Unknown paths fall through to it, as a SPA needs.

        A stray `/api/...` never lands here: those routes are registered first
        and FastAPI matches in order.
        """
        if path and not path.startswith("api/"):
            candidate = (WEB_ROOT / path).resolve()
            # `resolve()` then `is_relative_to` rather than trusting the path:
            # `../` in a URL is exactly how a static handler leaks a private key.
            if (
                web_is_built()
                and candidate.is_file()
                and candidate.is_relative_to(WEB_ROOT.resolve())
            ):
                return HTMLResponse(
                    candidate.read_bytes(),
                    media_type=_media_type(candidate),
                )
        return HTMLResponse(_index_html(app.state.jobsheet.settings.token))

    return app


_MEDIA_TYPES = {
    ".css": "text/css",
    ".js": "text/javascript",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".webmanifest": "application/manifest+json",
    ".woff2": "font/woff2",
}


def _media_type(path: Path) -> str:
    return _MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
