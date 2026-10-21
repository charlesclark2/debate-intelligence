"""Rendering the pilot's pages, and serving its one script and one stylesheet (ADR-0019 (a) 5 and (b) 1).

Pages are Jinja templates from this package, autoescaped. Every page loads exactly one script,
`/static/<digest>/app.js`, and one stylesheet, `/static/<digest>/app.css` (`v1-e39-t06`), where the
digest is the first 16 hex characters of the file's SHA-256: the path changes whenever the file
does, so each can be cached for a year (`public, max-age=31536000, immutable`) while every page stays
`private, no-store`. Neither holds data, and both are the same for every viewer, which is why
`/static/` needs no session.

The stylesheet is a file because the edge's `default-src 'self'` refuses inline styles as it
refuses inline script: no page carries a `style` attribute or a `<style>` element.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from importlib.resources import files
from typing import Final

import jinja2
import segno
from fastapi.responses import HTMLResponse

from debate_core.application.tub.sessions import PendingEnrolment, Session

__all__ = [
    "IMMUTABLE",
    "PageRenderer",
    "StaticAsset",
    "load_app_script",
    "load_app_stylesheet",
    "qr_code_svg",
]

IMMUTABLE: Final = "public, max-age=31536000, immutable"


@dataclass(frozen=True, slots=True)
class StaticAsset:
    """A static file and the content-hashed path it is served at."""

    name: str
    content: bytes
    media_type: str

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.content).hexdigest()[:16]

    @property
    def path(self) -> str:
        return f"/static/{self.digest}/{self.name}"


def load_app_script() -> StaticAsset:
    """The pilot's script, read from this package once."""
    content = files("debate_api").joinpath("static", "app.js").read_bytes()
    return StaticAsset(name="app.js", content=content, media_type="text/javascript; charset=utf-8")


def load_app_stylesheet() -> StaticAsset:
    """The pilot's stylesheet, read from this package once."""
    content = files("debate_api").joinpath("static", "app.css").read_bytes()
    return StaticAsset(name="app.css", content=content, media_type="text/css; charset=utf-8")


def qr_code_svg(uri: str) -> str:
    """`uri` as an inline SVG QR code: presentation attributes only, so the page's CSP allows it."""
    return segno.make(uri, error="m").svg_inline(scale=5, border=4, omitsize=False)


class PageRenderer:
    """Renders a template with what every page needs: the script and stylesheet, and who is signed in."""

    def __init__(self, *, app_script: StaticAsset, app_stylesheet: StaticAsset) -> None:
        self._environment = jinja2.Environment(
            loader=jinja2.PackageLoader("debate_api", "templates"),
            autoescape=jinja2.select_autoescape(["html"]),
            undefined=jinja2.StrictUndefined,
        )
        self._app_script = app_script
        self._app_stylesheet = app_stylesheet

    def render(
        self,
        template: str,
        *,
        holder: Session | PendingEnrolment | None = None,
        status_code: int = 200,
        **context: object,
    ) -> HTMLResponse:
        page = self._environment.get_template(template).render(
            app_js=self._app_script.path,
            app_css=self._app_stylesheet.path,
            csrf_token=holder.csrf_token if holder is not None else None,
            username=holder.username if holder is not None else None,
            role=holder.role.value if holder is not None else None,
            signed_in=isinstance(holder, Session),
            **context,
        )
        return HTMLResponse(page, status_code=status_code)
