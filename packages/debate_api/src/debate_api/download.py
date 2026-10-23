"""Download .docx (`v1-e39-t08`): the route that answers a card's or the cart's download.

| Route | What it answers |
|---|---|
| `POST /download` | the cards the body's `cards` field names as one Verbatim `.docx`, or why not |

`app.js` sends it as it sends every POST, with the session's CSRF token and the body's SHA-256, so the
gate has checked both before it gets here. The body is `cards=<caselist>/<cluster id>,...`: one
reference from a card page's *Download .docx*, or the cart the browser keeps in `sessionStorage`
(the PM's ruling of 2026-10-22: the session cookie holds no cart). What the references mean, and
every check on them, is :class:`~debate_core.application.card_download.CardDownloadService`'s; this
module reads the field and writes the words.

## The answer

* **A file**: `200`, the `.docx` as an attachment named for the day, never for a card. Its
  `cards-downloaded` record was written before it was returned.
* **A refusal**: JSON with a `message`, and for refused cards a `refused` list, each with the
  card's reference, its place in the request and a sentence. `app.js` shows them and offers to drop
  those cards from the cart and download the rest. A refused card that is still in the search is
  named by its tag or short cite, as its page shows them; one no longer in the search is named by its
  place alone.
* **Unavailable**: `503` when the index or the suppression list cannot be read, or the record cannot
  be written. No file goes out unaudited.

Nothing here logs. A reference names a card, and the request's body is never repeated in a message.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, cast
from urllib.parse import parse_qs

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from debate_api.state import pilot_state
from debate_core.application.card_download import (
    DownloadedFile,
    DownloadRefusal,
    DownloadRefused,
    RefusedCard,
    RefusedCardReason,
)
from debate_core.application.search_index_holder import SearchIndexUnavailable
from debate_core.application.tub.access_audit import AccessNotRecorded
from debate_core.application.tub.sessions import Session

__all__ = ["DOCX_MEDIA_TYPE", "card_download", "download_file_name", "refusal_answer"]

DOCX_MEDIA_TYPE: Final = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

_BODY_LIMIT: Final = 4096
"""A cart of thirty references is about 2,300 bytes urlencoded."""

_NAME_LIMIT: Final = 80
_UNAVAILABLE: Final = "The download could not be made right now. Try again in a minute."

_REFUSALS: Final[Mapping[DownloadRefusal, str]] = {
    DownloadRefusal.SWITCHED_OFF: (
        "Download is off until the search's next weekly update. Copy card still works."
    ),
    DownloadRefusal.UNREADABLE_CART: "That cart could not be read. Empty the cart and add the cards again.",
    DownloadRefusal.EMPTY_CART: "There is no card to download. Add a card to the cart from its page.",
    DownloadRefusal.CARDS_REFUSED: "Some cards cannot be downloaded.",
    DownloadRefusal.FILE_TOO_LARGE: (
        "These cards would make a file too large to download at once. Download fewer cards at a time."
    ),
    DownloadRefusal.SOURCES_TOO_LARGE: (
        "These cards come from files too large to read in one download. Download fewer cards at a time, "
        "or a card from a large file on its own."
    ),
}

_CARD_REASONS: Final[Mapping[RefusedCardReason, str]] = {
    RefusedCardReason.NOT_IN_SEARCH: "It is no longer in the search.",
    RefusedCardReason.NO_EVIDENCE_TEXT: (
        "It is a cite with no card text, so there is nothing to download. Copy card copies the cite."
    ),
    RefusedCardReason.ALREADY_IN_FILE: "It is the same card as one before it in the download.",
    RefusedCardReason.SOURCE_UNAVAILABLE: "Its file could not be read. Try again later.",
    RefusedCardReason.SOURCE_CHANGED: (
        "Its file no longer matches the search. It can be downloaded after the next weekly update."
    ),
    RefusedCardReason.UNSUPPORTED_CONTENT: (
        "It holds a picture, a table, a text box or a footnote that cannot be copied exactly. "
        "Copy card copies its text."
    ),
    RefusedCardReason.SOURCE_TOO_LARGE: "Its file is too large to download. Copy card still works.",
    RefusedCardReason.READBACK_MISMATCH: (
        "It did not come out exactly as it is in its file, so it was left out. Copy card copies its text."
    ),
}

_STATUS: Final[Mapping[DownloadRefusal, int]] = {
    DownloadRefusal.SWITCHED_OFF: 503,
    DownloadRefusal.UNREADABLE_CART: 400,
    DownloadRefusal.EMPTY_CART: 400,
}
"""A refusal's status; the rest are `409`, the cart as sent cannot be built."""


def download_file_name(request: Request) -> str:
    """`team-evidence-cards-2026-10-22.docx`: the day, in UTC, and nothing about the cards."""
    return f"team-evidence-cards-{pilot_state(request).services.clock():%Y-%m-%d}.docx"


def _name(card: RefusedCard) -> str | None:
    name = card.tag or card.short_cite
    if name is None:
        return None
    return name if len(name) <= _NAME_LIMIT else name[: _NAME_LIMIT - 1].rstrip() + "…"


def refusal_answer(refused: DownloadRefused) -> JSONResponse:
    """The JSON `app.js` shows for a download that was not built."""
    if refused.refusal is DownloadRefusal.TOO_MANY_CARDS:
        message = f"A download holds up to {refused.card_cap} cards. Remove some from the cart and try again."
    else:
        message = _REFUSALS[refused.refusal]
    answer: dict[str, object] = {"message": message}
    if refused.cards:
        answer["refused"] = [
            {
                "card": card.key.reference,
                "position": card.position,
                "name": _name(card),
                "reason": _CARD_REASONS[card.reason],
            }
            for card in refused.cards
        ]
    return JSONResponse(answer, status_code=_STATUS.get(refused.refusal, 409))


async def _cart(request: Request) -> str | None:
    """The body's `cards` field, or `None` for a body no page of the pilot sends."""
    body = await request.body()
    if len(body) > _BODY_LIMIT:
        return None
    try:
        fields = parse_qs(body.decode("utf-8", "replace"), max_num_fields=2)
    except ValueError:
        return None
    values = fields.get("cards", [""])
    return values[0] if len(values) == 1 else None


async def card_download(request: Request) -> Response:
    """The cards the body names as one `.docx`, or JSON saying why not."""
    cart = await _cart(request)
    if cart is None:
        return refusal_answer(DownloadRefused(DownloadRefusal.UNREADABLE_CART))
    session = cast(Session, request.state.holder)
    try:
        result = await pilot_state(request).services.card_download.download(session, cart)
    except (SearchIndexUnavailable, AccessNotRecorded):
        return JSONResponse({"message": _UNAVAILABLE}, status_code=503)
    if not isinstance(result, DownloadedFile):
        return refusal_answer(result)
    return Response(
        result.docx,
        media_type=DOCX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{download_file_name(request)}"'},
    )
