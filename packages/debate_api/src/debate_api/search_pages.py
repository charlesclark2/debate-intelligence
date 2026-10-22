"""The search pages (`v1-e39-t06`): the search page, its results, a card's page and Copy card's copy.

Each handler reads the query string, calls
:class:`~debate_core.application.evidence_search.EvidenceSearchService` through the index holder,
and renders. What a query means, which cards a student sees and how a card is marked up are
`debate_core`'s; what is here is the form, the words on the page and the Copy card table
(:mod:`debate_api.copy_card`).

| Route | What it answers | Needs the index |
|---|---|---|
| `GET /` and `GET /search` with no words | the empty search page | no: it never waits for one |
| `GET /search?q=...` | a page of results | yes |
| `GET /cards/<caselist>/<cluster id>` | the card's page | yes |
| `GET /cards/<caselist>/<cluster id>/copy` | the card as Copy card puts it on the clipboard, as JSON | yes |

Every one is a `GET` and none changes anything, so none needs a CSRF token (ADR-0019 (d), CSRF).

## What is audited (`v1-e39-t07`)

* A card page and a copy write their `card-viewed` and `card-copied` records before the card is
  sent. A record that cannot be written answers 503 with no card (the PM's ruling of 2026-10-22);
  Copy card's script then shows its error and leaves the clipboard alone.
* A search's first page writes one `searched` record with the number of results on it. A next
  page, a refused form, a search with no search terms and an unavailable index write nothing, and a
  failed write leaves the search answering.

Every lease applies the suppression list the holder last read, so a removed card is gone from
results, its page and its copy within five minutes (:class:`~debate_core.application.
search_index_holder.ScreenedSearch`).

## Nothing here is logged

A search is a `GET`, so its words are in the URL. No handler logs, and nothing here passes the
query, a card id or card text to anything that does: the access log is off in the image, and the
index holder logs only index ids. A test reads every log record a search and a card view make.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Final, cast
from urllib.parse import urlencode

from fastapi import Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import ValidationError
from starlette.datastructures import QueryParams

from debate_api.copy_card import copied_card
from debate_api.state import PilotState, pilot_state
from debate_core.application.search_index_holder import SearchIndexUnavailable
from debate_core.application.tub.access_audit import AccessNotRecorded
from debate_core.application.tub.sessions import Session
from debate_core.domain.caselist import Event, Side
from debate_core.domain.evidence_search import (
    MAX_QUERY_CHARACTERS,
    Card,
    InvalidSearchCursor,
    SearchFilters,
    SearchHit,
    SearchNotice,
    SearchPage,
)
from debate_core.domain.file_recipe import CAMP_STORE, RECIPE_STORE_PATTERN
from debate_core.domain.search_card_html import render_card_html, render_snippet_html, render_text_html

__all__ = [
    "CAMP_LABEL",
    "EVENT_CHOICES",
    "LONG_CARD_WORDS",
    "SIDE_CHOICES",
    "SearchForm",
    "card_copy",
    "card_page",
    "search_page",
]

LONG_CARD_WORDS: Final = 3000
"""A card over this many words leads with its read-aloud text and shows the rest on request (ac5)."""

EVENT_CHOICES: Final = ((Event.LD, "LD"), (Event.POLICY, "Policy"), (Event.PF, "Public Forum"))
SIDE_CHOICES: Final = ((Side.AFF, "Aff"), (Side.NEG, "Neg"), (Side.PRO, "Pro"), (Side.CON, "Con"))
CAMP_LABEL: Final = "Camp cards (OpenEv)"

_CLUSTER_ID: Final = re.compile(r"^[0-9a-f]{64}$")
_STORE: Final = re.compile(RECIPE_STORE_PATTERN)
_CURSOR_LIMIT: Final = 64

_UNAVAILABLE_HEADING: Final = "Search is not available right now"
_UNAVAILABLE: Final = "The search could not be loaded. Try again in a minute."
_NOT_FOUND_HEADING: Final = "That card is not in the search"
_NOT_FOUND: Final = "It may have been removed, or the link may be wrong. Search for it again."


class SearchFormInvalid(ValueError):
    """A query string no form on these pages writes: a filter value outside its choices."""


@dataclass(frozen=True, slots=True)
class SearchForm:
    """What the search form sent, read strictly: a value outside a filter's choices is refused."""

    query: str = ""
    event: str = ""
    caselist: str = ""
    side: str = ""
    since: str = ""
    cursor: str | None = None

    @classmethod
    def from_query(cls, params: QueryParams) -> SearchForm:
        form = cls(
            query=params.get("q", "")[: MAX_QUERY_CHARACTERS * 2],
            event=params.get("event", ""),
            caselist=params.get("caselist", ""),
            side=params.get("side", ""),
            since=params.get("since", ""),
            cursor=params.get("cursor") or None,
        )
        if form.event and form.event not in {event.value for event, _ in EVENT_CHOICES}:
            raise SearchFormInvalid("event")
        if form.side and form.side not in {side.value for side, _ in SIDE_CHOICES}:
            raise SearchFormInvalid("side")
        if form.caselist and _STORE.match(form.caselist) is None:
            raise SearchFormInvalid("caselist")
        if form.cursor is not None and len(form.cursor) > _CURSOR_LIMIT:
            raise SearchFormInvalid("cursor")
        if form.since:
            try:
                date.fromisoformat(form.since)
            except ValueError:
                raise SearchFormInvalid("since") from None
        return form

    @property
    def has_words(self) -> bool:
        return bool(self.query.strip())

    def filters(self) -> SearchFilters:
        try:
            return SearchFilters(
                event=Event(self.event) if self.event else None,
                caselist=self.caselist or None,
                side=Side(self.side) if self.side else None,
                first_seen_on_or_after=date.fromisoformat(self.since) if self.since else None,
            )
        except ValidationError:
            raise SearchFormInvalid("filters") from None

    def page_link(self, cursor: str | None) -> str:
        """This search's URL, at `cursor` (the first page when `None`)."""
        fields = {
            "q": self.query,
            "event": self.event,
            "caselist": self.caselist,
            "side": self.side,
            "since": self.since,
        }
        if cursor is not None:
            fields["cursor"] = cursor
        return "/search?" + urlencode({name: value for name, value in fields.items() if value})


@dataclass(frozen=True, slots=True)
class ResultView:
    """One result as the results page shows it."""

    href: str
    tag: str | None
    short_cite: str | None
    snippet_html: str
    counts: str
    provenance_line: str | None


def _counts(files: int, teams: int | None) -> str:
    """`In 3 files from 2 teams.`; with no team count, the files and a sentence with no number."""
    file_words = "1 file" if files == 1 else f"{files} files"
    if teams is None:
        return f"In {file_words}. The number of teams is not known until the next weekly update."
    if teams == 0:
        return f"In {file_words}."
    return f"In {file_words} from {'1 team' if teams == 1 else f'{teams} teams'}."


def _card_href(caselist: str, cluster_id: str) -> str:
    return f"/cards/{caselist}/{cluster_id}"


def _result(hit: SearchHit) -> ResultView:
    return ResultView(
        href=_card_href(hit.caselist, hit.cluster_id),
        tag=hit.tag,
        short_cite=hit.short_cite,
        snippet_html=render_snippet_html(hit.snippet),
        counts=_counts(hit.file_count, hit.team_count),
        provenance_line=hit.provenance_line,
    )


def _caselist_choices(state: PilotState, chosen: str) -> list[tuple[str, str]]:
    """The loaded index's stores, without waiting for one; the chosen one is always offered."""
    stores = list(state.services.search_index.loaded_caselists())
    if chosen and chosen not in stores:
        stores.append(chosen)
    return [(store, CAMP_LABEL if store == CAMP_STORE else store) for store in sorted(stores)]


def _render_search(
    request: Request,
    form: SearchForm,
    *,
    page: SearchPage | None = None,
    status_code: int = 200,
    problem: str | None = None,
) -> HTMLResponse:
    state = pilot_state(request)
    notices = set(page.notices) if page is not None else set()
    return state.renderer.render(
        "search.html",
        holder=_session(request),
        status_code=status_code,
        form=form,
        event_choices=[(event.value, label) for event, label in EVENT_CHOICES],
        side_choices=[(side.value, label) for side, label in SIDE_CHOICES],
        caselist_choices=_caselist_choices(state, form.caselist),
        searched=page is not None,
        results=[_result(hit) for hit in page.hits] if page is not None else [],
        next_link=form.page_link(page.next_cursor) if page is not None and page.next_cursor else None,
        first_link=form.page_link(None) if form.cursor else None,
        partial=page.partial if page is not None else False,
        query_shortened=SearchNotice.QUERY_SHORTENED in notices,
        no_search_terms=SearchNotice.NO_SEARCH_TERMS in notices,
        side_caselist_only=SearchNotice.SIDE_CASELIST_CARDS_ONLY in notices,
        since_caselist_only=SearchNotice.FIRST_SEEN_CASELIST_CARDS_ONLY in notices,
        problem=problem,
    )


def _session(request: Request) -> Session:
    return cast(Session, request.state.holder)


def _refused(request: Request, status_code: int, heading: str, message: str) -> HTMLResponse:
    return pilot_state(request).renderer.render(
        "refused.html", holder=_session(request), status_code=status_code, heading=heading, message=message
    )


# --------------------------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------------------------


def search_page(request: Request) -> HTMLResponse:
    """The search page: empty with no words, which never waits for the index; results with them."""
    try:
        form = SearchForm.from_query(request.query_params)
        filters = form.filters()
    except SearchFormInvalid:
        return _render_search(
            request,
            SearchForm(),
            status_code=400,
            problem="That search could not be read. Choose the filters again.",
        )
    if not form.has_words:
        return _render_search(request, form)
    state = pilot_state(request)
    try:
        with state.services.search_index.lease() as search:
            page = search.search(form.query, filters, form.cursor)
    except SearchIndexUnavailable:
        return _refused(request, 503, _UNAVAILABLE_HEADING, _UNAVAILABLE)
    except InvalidSearchCursor:
        return _render_search(
            request,
            SearchForm(form.query, form.event, form.caselist, form.side, form.since),
            status_code=400,
            problem="That page of results is out of date. Search again from the first page.",
        )
    if form.cursor is None and SearchNotice.NO_SEARCH_TERMS not in page.notices:
        state.services.access_audit.searched(_session(request), len(page.hits))
    return _render_search(request, form, page=page)


def _card(request: Request, caselist: str, cluster_id: str) -> Card | None:
    """The card at this address, or `None`; :class:`SearchIndexUnavailable` passes through."""
    if _STORE.match(caselist) is None or _CLUSTER_ID.match(cluster_id) is None:
        return None
    with pilot_state(request).services.search_index.lease() as search:
        return search.card(caselist, cluster_id)


def card_page(caselist: str, cluster_id: str, request: Request) -> HTMLResponse:
    """A card: its label, tag, cite and provenance, Copy card, its text, and every occurrence's line."""
    try:
        card = _card(request, caselist, cluster_id)
    except SearchIndexUnavailable:
        return _refused(request, 503, _UNAVAILABLE_HEADING, _UNAVAILABLE)
    if card is None:
        return _refused(request, 404, _NOT_FOUND_HEADING, _NOT_FOUND)
    try:
        pilot_state(request).services.access_audit.card_viewed(
            _session(request), card.caselist, card.cluster_id
        )
    except AccessNotRecorded:
        return _refused(request, 503, _UNAVAILABLE_HEADING, _UNAVAILABLE)
    words = len(card.text.split())
    unattributed = sum(1 for one in card.occurrences if one.provenance_line is None)
    return pilot_state(request).renderer.render(
        "card.html",
        holder=_session(request),
        card=card,
        provenance_line=card.occurrences[0].provenance_line if card.occurrences else None,
        counts=_counts(card.file_count, card.team_count),
        copy_href=_card_href(card.caselist, card.cluster_id) + "/copy",
        long_card=words > LONG_CARD_WORDS,
        words=f"{words:,}",
        read_aloud_html=render_text_html(card.read_aloud),
        card_html=render_card_html(card.runs),
        occurrence_lines=[one.provenance_line for one in card.occurrences if one.provenance_line],
        unattributed=unattributed,
    )


def card_copy(caselist: str, cluster_id: str, request: Request) -> Response:
    """The card as Copy card writes it to the clipboard: `{"html": ..., "text": ...}`."""
    try:
        card = _card(request, caselist, cluster_id)
    except SearchIndexUnavailable:
        return JSONResponse({"message": _UNAVAILABLE}, status_code=503)
    if card is None:
        return JSONResponse({"message": "That card is not in the search any more."}, status_code=404)
    try:
        pilot_state(request).services.access_audit.card_copied(
            _session(request), card.caselist, card.cluster_id
        )
    except AccessNotRecorded:
        return JSONResponse({"message": _UNAVAILABLE}, status_code=503)
    copied = copied_card(card)
    return JSONResponse({"html": copied.html, "text": copied.text})
