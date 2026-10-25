"""The landscape pages (`v1-e39-t17`): each caselist's newest landscape report and its school view.

Data-use policy 1.16 shows the newest published bundle's `report.md` and per-school view to the
team's signed-in members, students and coach alike, under the E39 gate's item 11.

| Route | What it answers |
|---|---|
| `GET /landscape` | the caselists with a published bundle, each with its newest snapshot |
| `GET /landscape/<caselist>` | the report, one page, with its contents list |
| `GET /landscape/<caselist>/schools` | the school view's front page: its header, its schools, its positions |
| `GET /landscape/<caselist>/schools/<school>` | one school, by its heading's anchor |
| `GET /landscape/<caselist>/positions/<position id>` | one position's teams |

Every one is a `GET` behind the gate, for any session, and changes nothing. The bundles come from
:class:`~debate_core.application.tub.landscape_pages.LandscapeShelf`, which reads the bucket again
when what it holds is five minutes old, rendered by :mod:`debate_api.landscape_markdown`.

## What a page holds, and what it never does

* **The newest snapshot only.** A path names a caselist and never a snapshot, so no older bundle can
  be asked for. A snapshot whose `schools.md` a removal deleted says so on its school view's pages,
  and no older view is shown in its place.
* **No search, no download and no share link.** These pages carry no search form, no download cart
  and no Search link in the header (`landscape=True` in `base.html`): the forbidden list names
  search links, so the pages' header leaves out even the way to the search page.
* **One link out**: a school view's team page, checked at render; everything else is text.

## What is audited

Each page writes one `landscape-viewed` record before it is sent, naming its kind and, but for the
list of caselists, its bundle's caselist and snapshot: never which school or position. A record that
cannot be written answers 503 with no page, as a card page does. A caselist, school or position not
in the newest bundle is a 404 and writes nothing, since nothing of a bundle was shown.

## Nothing here is logged

A school's anchor and a position's id are in these pages' paths. No handler logs, and nothing here
hands a path, a school or a position to anything that does: uvicorn's access log is off in the image
and the edge keeps no log. A test reads every log record these pages make, at every level.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Final, cast

from fastapi import Request
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

from debate_api.landscape_markdown import RenderedBundle
from debate_api.state import pilot_state
from debate_core.application.tub.access_audit import AccessNotRecorded
from debate_core.application.tub.landscape_pages import HeldBundle, LandscapeUnavailable
from debate_core.application.tub.sessions import Session
from debate_core.domain.landscape_pages import LandscapePage

__all__ = [
    "landscape_caselists",
    "landscape_position",
    "landscape_report",
    "landscape_school",
    "landscape_school_view",
]

_UNAVAILABLE_HEADING: Final = "The landscape reports are not available right now"
_UNAVAILABLE: Final = "They could not be loaded. Try again in a minute."
_NOT_FOUND_HEADING: Final = "That is not in the newest report"
_NOT_FOUND: Final = "It may have been removed or renamed in this week's report, or the link may be wrong."


def _session(request: Request) -> Session:
    return cast(Session, request.state.holder)


def _refused(request: Request, status_code: int, heading: str, message: str) -> HTMLResponse:
    return pilot_state(request).renderer.render(
        "refused.html",
        holder=_session(request),
        status_code=status_code,
        heading=heading,
        message=message,
        landscape=True,
    )


async def _bundles(request: Request) -> Mapping[str, HeldBundle[RenderedBundle]] | HTMLResponse:
    """Every newest bundle, or the page saying they could not be read."""
    try:
        return await pilot_state(request).services.landscape.bundles()
    except LandscapeUnavailable:
        return _refused(request, 503, _UNAVAILABLE_HEADING, _UNAVAILABLE)


async def _shown(
    request: Request,
    template: str,
    page: LandscapePage,
    bundle: RenderedBundle | None,
    *,
    status_code: int = 200,
    **context: object,
) -> HTMLResponse:
    """Write the page's record, then render it; 503 with no page if the record is not written."""
    state = pilot_state(request)
    caselist: str | None = None if bundle is None else bundle.caselist
    snapshot: date | None = None if bundle is None else bundle.snapshot
    try:
        await run_in_threadpool(
            state.services.access_audit.landscape_viewed, _session(request), page, caselist, snapshot
        )
    except AccessNotRecorded:
        return _refused(request, 503, _UNAVAILABLE_HEADING, _UNAVAILABLE)
    return state.renderer.render(
        template,
        holder=_session(request),
        status_code=status_code,
        landscape=True,
        bundle=bundle,
        **context,
    )


async def _bundle(request: Request, caselist: str) -> RenderedBundle | HTMLResponse:
    """`caselist`'s newest bundle, or the page saying why there is none."""
    bundles = await _bundles(request)
    if isinstance(bundles, HTMLResponse):
        return bundles
    held = bundles.get(caselist)
    if held is None:
        return _refused(request, 404, _NOT_FOUND_HEADING, _NOT_FOUND)
    return held.prepared


# --------------------------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------------------------


async def landscape_caselists(request: Request) -> HTMLResponse:
    """Every caselist with a published bundle, and its newest snapshot's date."""
    bundles = await _bundles(request)
    if isinstance(bundles, HTMLResponse):
        return bundles
    listed = [held.prepared for _, held in sorted(bundles.items())]
    return await _shown(request, "landscape.html", LandscapePage.CASELISTS, None, bundles=listed)


async def landscape_report(caselist: str, request: Request) -> HTMLResponse:
    """The newest report, whole, with its contents list."""
    bundle = await _bundle(request, caselist)
    if isinstance(bundle, HTMLResponse):
        return bundle
    return await _shown(request, "landscape_report.html", LandscapePage.REPORT, bundle, report=bundle.report)


async def landscape_school_view(caselist: str, request: Request) -> HTMLResponse:
    """The school view's front page, or the page saying the newest bundle has none."""
    bundle = await _bundle(request, caselist)
    if isinstance(bundle, HTMLResponse):
        return bundle
    return await _shown(
        request, "landscape_school_view.html", LandscapePage.SCHOOL_VIEW, bundle, view=bundle.school_view
    )


async def landscape_school(caselist: str, school: str, request: Request) -> HTMLResponse:
    """One school's positions, by the anchor of its heading in the view."""
    bundle = await _bundle(request, caselist)
    if isinstance(bundle, HTMLResponse):
        return bundle
    view = bundle.school_view
    if view is None:
        return await _shown(
            request, "landscape_school_view.html", LandscapePage.SCHOOL, bundle, status_code=404, view=None
        )
    piece = view.school(school)
    if piece is None:
        return _refused(request, 404, _NOT_FOUND_HEADING, _NOT_FOUND)
    return await _shown(request, "landscape_piece.html", LandscapePage.SCHOOL, bundle, view=view, piece=piece)


async def landscape_position(caselist: str, position_id: str, request: Request) -> HTMLResponse:
    """One position's teams, by its id."""
    bundle = await _bundle(request, caselist)
    if isinstance(bundle, HTMLResponse):
        return bundle
    view = bundle.school_view
    if view is None:
        return await _shown(
            request, "landscape_school_view.html", LandscapePage.POSITION, bundle, status_code=404, view=None
        )
    piece = view.position(position_id)
    if piece is None:
        return _refused(request, 404, _NOT_FOUND_HEADING, _NOT_FOUND)
    return await _shown(
        request, "landscape_piece.html", LandscapePage.POSITION, bundle, view=view, piece=piece
    )
