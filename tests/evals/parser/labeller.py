"""The click-through labeller: a file's sampled rows corrected one key per row, in a local page.

`scripts/prelabel_docx.py label <prefix> --out-dir <folder>` serves the page; this module is
everything behind it. A person sees one sampled paragraph at a time, rendered with its formatting
by :mod:`tests.evals.parser.docx_render`, with the two paragraphs either side, the sampling block
it belongs to and the parser's pre-label, and answers it with a key. When the last row is checked
the page writes the same worksheet a spreadsheet would, and `check` and `import` take it as they
take any other. **Every guarantee stays in `import`.** The labeller adds none of its own and
removes none: what it writes is only ever what the keys said, and `import` still refuses a
worksheet with a row nobody checked or a text that is not the document's.

## Keys

* **Enter** or **Space**: accept the row as shown, check it and move on.
* **p h b t c e a u o**: POCKET, HAT, BLOCK, TAG, CITE, EVIDENCE, ANALYTIC, UNDERTAG, OTHER. Set
  it, check the row and move on.
* **n**: start a card on this row, or stop one starting here. Checks nothing and stays.
* **k**: the card's completeness, FULL, ABBREVIATED, CITE_ONLY, and for the first and last card of
  a block, cut off by the block's edge. Checks nothing and stays.
* **Backspace** or **Left**: back one row. Checks nothing.

**A row is checked only by a key pressed on it** (ac2). There is no key or route that checks more
than one row, a key sent for a row the page is not on changes nothing, and a key that changes a
card (`n`, `k`) never checks a row.

## Cards

Card numbers follow from the card starts, by the labeling guide's rules
(`tests/fixtures/debate_files/eval/labels/README.md#cards`), inside one sampling block at a time:

* a card starts on a row marked as a start, which is its TAG, or its CITE when it has no tag;
* it takes the TAG, UNDERTAG, CITE and EVIDENCE rows after its start, and ends at its last
  EVIDENCE row, or at its last CITE when it has no body;
* a blank (`OTHER`) row inside it is not part of it and does not end it;
* any heading, an ANALYTIC, a TAG nobody marked as a start, the next start and the end of the
  block all end it;
* **a card cut off by the end of a block is left unnumbered.** Whether the card goes on past the
  block is in the paragraphs after it, which the page shows; the person marks it with `k`.

The page shows a card by its place in the file. The number written to the worksheet keeps the
pre-label's number for a card that starts where a pre-label card started, so `import`'s count of
rows changed from the pre-labels counts real changes and not renumbering. It is never shown, so
blind mode gives nothing away.

## Progress, and where things are written

Progress is saved after every key, outside the repository, to `<prefix>.progress.json` beside the
worksheet: units, card starts, completeness and which rows are checked, and no text. The labeller
resumes where it stopped, in the mode it started in. It never writes over a worksheet that was
changed in a spreadsheet, or labels a file whose `.numbers` file is beside it: that file is on the
spreadsheet route, which stays the fallback.

## The page

Served at `127.0.0.1` on a free port, and nowhere else. It is one inline page with its script and
styles in it: no fonts, scripts or styles from anywhere, and a Content-Security-Policy that lets it
call nothing but the server it came from. A request whose `Host` is not that address is refused,
which stops another site reaching it by DNS rebinding, and every request but the page itself needs
a token the page carries, which stops another tab sending keys.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import os
import secrets
import time
import webbrowser
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Final

from tests.evals.parser.docx_render import RenderedParagraph
from tests.evals.parser.labels_schema import CARD_UNITS, REPOSITORY_ROOT, Block, LabelFile
from tests.evals.parser.worksheets import WORKSHEET_COLUMNS, Worksheet, read_worksheet, render_markup

from debate_core.domain.style_profile import StructuralUnit

__all__ = [
    "ACCEPT_KEYS",
    "BACK_KEYS",
    "COMPLETENESS_KEY",
    "NEW_CARD_KEY",
    "UNIT_KEYS",
    "Card",
    "CardReading",
    "CardState",
    "LabellerApp",
    "ProgressError",
    "Response",
    "RowLabel",
    "Session",
    "csv_bytes",
    "labelled_worksheet",
    "load_or_begin",
    "prelabel_card_starts",
    "progress_path_for",
    "read_cards",
    "save_progress",
    "serve",
    "written_numbers",
]

UNIT_KEYS: Final[Mapping[str, StructuralUnit]] = {
    "p": StructuralUnit.POCKET,
    "h": StructuralUnit.HAT,
    "b": StructuralUnit.BLOCK,
    "t": StructuralUnit.TAG,
    "c": StructuralUnit.CITE,
    "e": StructuralUnit.EVIDENCE,
    "a": StructuralUnit.ANALYTIC,
    "u": StructuralUnit.UNDERTAG,
    "o": StructuralUnit.OTHER,
}
ACCEPT_KEYS: Final = frozenset({"Enter", " "})
BACK_KEYS: Final = frozenset({"Backspace", "ArrowLeft"})
NEW_CARD_KEY: Final = "n"
COMPLETENESS_KEY: Final = "k"

#: The units a card starts on: its TAG, or its CITE when it has no tag.
_CARD_STARTS: Final = frozenset({StructuralUnit.TAG, StructuralUnit.CITE})
#: Rows that end any card open above them.
_CARD_ENDERS: Final = frozenset(
    {StructuralUnit.POCKET, StructuralUnit.HAT, StructuralUnit.BLOCK, StructuralUnit.ANALYTIC}
)
_PROGRESS_VERSION: Final = 1
#: The largest request body the server reads: a key and a row number.
_LARGEST_BODY: Final = 4096
_PAGE: Final = Path(__file__).with_name("labeller_page.html")


class ProgressError(ValueError):
    """The labeller will not start, or resume, as asked. Says why and what to do."""


class CardState(StrEnum):
    """A card's completeness, or that it is cut off by the edge of its block and left unnumbered."""

    FULL = "FULL"
    ABBREVIATED = "ABBREVIATED"
    CITE_ONLY = "CITE_ONLY"
    CUT = "CUT_BY_BLOCK_EDGE"


_COMPLETENESS_CYCLE: Final = (CardState.FULL, CardState.ABBREVIATED, CardState.CITE_ONLY)


@dataclass(frozen=True)
class RowLabel:
    """One sampled paragraph's label as the keys have left it."""

    index: int
    unit: StructuralUnit | None
    starts_card: bool = False
    checked: bool = False


# --------------------------------------------------------------------------------------------
# Cards, from the starts
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Card:
    start: int
    members: tuple[int, ...]
    state: CardState | None
    #: Its place among the file's numbered cards, from 1; None when it is cut off.
    ordinal: int | None
    first_in_block: bool
    last_in_block: bool


@dataclass(frozen=True)
class CardReading:
    cards: tuple[Card, ...]
    card_of: Mapping[int, Card]
    #: What the page says about a row's card, by paragraph index. Advice only: `check` decides.
    notes: Mapping[int, tuple[str, ...]]


def _close_card(
    start: RowLabel | None,
    candidates: Sequence[RowLabel],
    block: Block,
    found: list[tuple[int, tuple[int, ...], Block]],
    notes: dict[int, list[str]],
) -> None:
    """End the card open at `start`: it runs to its last EVIDENCE row, or its last CITE without a body."""
    if start is None:
        return
    members = [start, *candidates]
    units = [row.unit for row in members]
    if StructuralUnit.EVIDENCE in units:
        end = max(i for i, unit in enumerate(units) if unit is StructuralUnit.EVIDENCE)
    elif StructuralUnit.CITE in units:
        end = max(i for i, unit in enumerate(units) if unit is StructuralUnit.CITE)
    else:
        end = 0
    for row in members[end + 1 :]:
        notes.setdefault(row.index, []).append("after its card's last EVIDENCE (or last CITE), so in no card")
    found.append((start.index, tuple(row.index for row in members[: end + 1]), block))


def read_cards(
    rows: Sequence[RowLabel], blocks: Sequence[Block], states: Mapping[int, CardState]
) -> CardReading:
    """Which rows make up which card, from the card starts, one sampling block at a time."""
    notes: dict[int, list[str]] = {}
    found: list[tuple[int, tuple[int, ...], Block]] = []

    def note(index: int, message: str) -> None:
        notes.setdefault(index, []).append(message)

    for block in blocks:
        start: RowLabel | None = None
        candidates: list[RowLabel] = []
        for row in (row for row in rows if block[0] <= row.index <= block[1]):
            if row.starts_card:
                _close_card(start, candidates, block, found, notes)
                start, candidates = (row, []) if row.unit in _CARD_STARTS else (None, [])
                if start is None:
                    note(
                        row.index,
                        "a card starts at its TAG, or at its CITE when it has no tag: this start counts "
                        "for nothing",
                    )
                continue
            if row.unit is StructuralUnit.TAG:
                _close_card(start, candidates, block, found, notes)
                start = None
                note(
                    row.index,
                    "a TAG not marked as the start of a card, so in no card: press n here to start one",
                )
            elif row.unit in _CARD_ENDERS:
                _close_card(start, candidates, block, found, notes)
                start = None
            elif row.unit in CARD_UNITS and start is not None:
                candidates.append(row)
        _close_card(start, candidates, block, found, notes)

    cards: list[Card] = []
    ordinal = 0
    for position, (first, members, block) in enumerate(found):
        state = states.get(first)
        first_in_block = position == 0 or found[position - 1][2] != block
        last_in_block = position == len(found) - 1 or found[position + 1][2] != block
        if state is not CardState.CUT:
            ordinal += 1
        cards.append(
            Card(
                start=first,
                members=members,
                state=state,
                ordinal=None if state is CardState.CUT else ordinal,
                first_in_block=first_in_block,
                last_in_block=last_in_block,
            )
        )
    units = {row.index: row.unit for row in rows}
    for card in cards:
        if card.ordinal is None:
            continue
        member_units = [units[index] for index in card.members]
        name = f"card {card.ordinal}"
        if StructuralUnit.CITE not in member_units:
            note(card.start, f"{name} has no CITE: a card is a tag, its cite and its body")
        if card.state is None:
            note(card.start, f"{name} has no completeness: press k on any of its rows")
        elif card.state is CardState.CITE_ONLY and StructuralUnit.EVIDENCE in member_units:
            note(card.start, f"{name} is CITE_ONLY but has an EVIDENCE row")
        elif card.state is not CardState.CITE_ONLY and StructuralUnit.EVIDENCE not in member_units:
            note(card.start, f"{name} is {card.state.value} but has no EVIDENCE row")
    return CardReading(
        cards=tuple(cards),
        card_of={index: card for card in cards for index in card.members},
        notes={index: tuple(messages) for index, messages in notes.items()},
    )


def prelabel_card_starts(prelabels: LabelFile) -> tuple[tuple[int, int], ...]:
    """Each pre-label card's number and its first row."""
    return tuple((card, first) for card, (first, _) in sorted(prelabels.card_ranges().items()))


def written_numbers(reading: CardReading, prelabel_cards: Iterable[tuple[int, int]]) -> dict[int, int]:
    """The card number each numbered card is written with, by its first row.

    A card that starts where a pre-label card started keeps that card's number; any other gets a
    number no pre-label card uses. Cut-off cards get none.
    """
    by_first = {first: number for number, first in prelabel_cards}
    unused = max(by_first.values(), default=-1) + 1
    numbers: dict[int, int] = {}
    for card in reading.cards:
        if card.ordinal is None:
            continue
        if card.start in by_first:
            numbers[card.start] = by_first[card.start]
        else:
            numbers[card.start] = unused
            unused += 1
    return numbers


# --------------------------------------------------------------------------------------------
# A session: the rows, the keys, the progress
# --------------------------------------------------------------------------------------------


def _fingerprint(prelabels: LabelFile) -> str:
    """Which pre-labels a session was started from. A digest of the committed label file, not of text."""
    return hashlib.sha256(prelabels.to_jsonl().encode("utf-8")).hexdigest()[:16]


@dataclass
class Session:
    """One file's labeling: the rows as the keys have left them, and where the page is."""

    digest: str
    blocks: tuple[Block, ...]
    rows: list[RowLabel]
    card_states: dict[int, CardState]
    #: Which row the page is on, as a position in `rows`.
    position: int
    blind: bool
    prelabels_fingerprint: str
    #: When each row was checked in this sitting, for the pace. Not saved.
    check_times: list[float] = field(default_factory=list[float])

    @classmethod
    def begin(cls, prelabels: LabelFile, *, blind: bool) -> Session:
        """A fresh session: the pre-labels shown and unchecked, or in blind mode nothing at all."""
        starts = {first: number for number, first in prelabel_card_starts(prelabels)}
        completeness = {card.card: card.completeness for card in prelabels.cards}
        return cls(
            digest=prelabels.digest,
            blocks=prelabels.blocks,
            rows=[
                RowLabel(
                    index=paragraph.index,
                    unit=None if blind else paragraph.unit,
                    starts_card=not blind and paragraph.index in starts,
                )
                for paragraph in prelabels.paragraphs
            ],
            card_states={}
            if blind
            else {
                first: CardState(completeness[number].value)
                for first, number in starts.items()
                if number in completeness
            },
            position=0,
            blind=blind,
            prelabels_fingerprint=_fingerprint(prelabels),
        )

    @property
    def current(self) -> RowLabel:
        return self.rows[self.position]

    @property
    def done(self) -> int:
        return sum(1 for row in self.rows if row.checked)

    @property
    def complete(self) -> bool:
        return all(row.checked for row in self.rows)

    def cards(self) -> CardReading:
        return read_cards(self.rows, self.blocks, self.card_states)

    def rows_per_minute(self) -> float | None:
        """Rows checked per minute between the first and the last row checked in this sitting."""
        if len(self.check_times) < 2 or self.check_times[-1] <= self.check_times[0]:
            return None
        minutes = (self.check_times[-1] - self.check_times[0]) / 60
        return round((len(self.check_times) - 1) / minutes, 1)

    def press(self, key: str, row: int, now: float | None = None) -> str:
        """Apply one key pressed on paragraph `row`. Returns what the page should say, or ""."""
        current = self.current
        if row != current.index:
            return (
                f"that key was for paragraph {row}, and the page is not on it (it is on "
                f"{current.index}): nothing changed"
            )
        name = key.lower() if len(key) == 1 else key
        if key in ACCEPT_KEYS:
            if current.unit is None:
                return "this row has no unit yet: press its unit's key"
            self._check(current, current.unit, now)
        elif name in UNIT_KEYS:
            self._check(current, UNIT_KEYS[name], now)
        elif name == NEW_CARD_KEY:
            starts = not current.starts_card
            self.rows[self.position] = replace(current, starts_card=starts)
            if not starts:
                self.card_states.pop(current.index, None)
        elif name == COMPLETENESS_KEY:
            card = self.cards().card_of.get(current.index)
            if card is None:
                return "this row is in no card, so it has no completeness"
            cycle = _COMPLETENESS_CYCLE + (
                (CardState.CUT,) if card.first_in_block or card.last_in_block else ()
            )
            following = cycle[(cycle.index(card.state) + 1) % len(cycle)] if card.state in cycle else cycle[0]
            self.card_states[card.start] = following
        elif key in BACK_KEYS:
            self.position = max(0, self.position - 1)
        else:
            return f"{key!r} is not one of the labeller's keys"
        return ""

    def goto(self, row: int) -> str:
        """Move the page to paragraph `row`, checking nothing: how a problem's row is reached."""
        for position, label in enumerate(self.rows):
            if label.index == row:
                self.position = position
                return ""
        return f"paragraph {row} is not one of this file's sampled rows"

    def _check(self, current: RowLabel, unit: StructuralUnit, now: float | None) -> None:
        self.rows[self.position] = replace(current, unit=unit, checked=True)
        if now is not None:
            self.check_times.append(now)
        self.position = min(self.position + 1, len(self.rows) - 1)

    def to_json(self) -> str:
        return json.dumps(
            {
                "version": _PROGRESS_VERSION,
                "digest": self.digest,
                "blind": self.blind,
                "prelabels": self.prelabels_fingerprint,
                "position": self.current.index,
                "rows": [
                    {
                        "index": row.index,
                        "unit": None if row.unit is None else row.unit.value,
                        "starts_card": row.starts_card,
                        "checked": row.checked,
                    }
                    for row in self.rows
                ],
                "cards": {str(start): state.value for start, state in sorted(self.card_states.items())},
            },
            indent=1,
        )


def progress_path_for(out_dir: Path, digest: str) -> Path:
    """Where a file's progress is saved: beside its worksheet, and never inside the repository."""
    directory = out_dir.expanduser().resolve()
    if directory.is_relative_to(REPOSITORY_ROOT):
        raise ProgressError(
            "the labeller's folder holds the worksheet and the progress, and must be outside the repository"
        )
    return directory / f"{digest[:16]}.progress.json"


def save_progress(session: Session, path: Path) -> None:
    """Write the progress whole, or not at all: a half-written file would lose the labeling."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f".{path.name}.partial")
    partial.write_text(session.to_json(), encoding="utf-8")
    os.replace(partial, path)


def load_or_begin(path: Path, prelabels: LabelFile, *, blind: bool) -> Session:
    """The saved session for this file, or a fresh one. Refuses one that cannot be resumed as asked."""
    if not path.exists():
        return Session.begin(prelabels, blind=blind)
    saved = json.loads(path.read_text(encoding="utf-8"))
    if saved.get("version") != _PROGRESS_VERSION or saved.get("digest") != prelabels.digest:
        raise ProgressError(f"{path.name} is not this file's progress; delete it to start again")
    if saved["prelabels"] != _fingerprint(prelabels):
        raise ProgressError(
            f"the pre-labels changed since {path.name} was saved (were they regenerated?), so its rows "
            f"may not be the ones shown. Delete {path.name} to start this file again"
        )
    if saved["blind"] and not blind:
        raise ProgressError(
            "this file was started blind, so its pre-labels stay hidden: run label with --blind"
        )
    if blind and not saved["blind"]:
        raise ProgressError(
            f"this file was started with the pre-labels shown, so it cannot be labeled blind now. Label "
            f"another file blind, or delete {path.name} to start this one again blind"
        )
    rows = [
        RowLabel(
            index=row["index"],
            unit=None if row["unit"] is None else StructuralUnit(row["unit"]),
            starts_card=row["starts_card"],
            checked=row["checked"],
        )
        for row in saved["rows"]
    ]
    if [row.index for row in rows] != [paragraph.index for paragraph in prelabels.paragraphs]:
        raise ProgressError(
            f"{path.name} holds other rows than the sampling plan's; delete it to start again"
        )
    positions = {row.index: position for position, row in enumerate(rows)}
    return Session(
        digest=prelabels.digest,
        blocks=prelabels.blocks,
        rows=rows,
        card_states={int(start): CardState(state) for start, state in saved["cards"].items()},
        position=positions.get(saved["position"], 0),
        blind=saved["blind"],
        prelabels_fingerprint=saved["prelabels"],
    )


# --------------------------------------------------------------------------------------------
# The worksheet the keys wrote
# --------------------------------------------------------------------------------------------


def labelled_worksheet(
    session: Session,
    prelabels: LabelFile,
    texts: Sequence[str],
    rendered: Sequence[RenderedParagraph],
) -> Worksheet:
    """The worksheet `check` and `import` read, holding exactly what the keys said.

    The span cells of a sampled row carry the marks the labeller's renderer read from the
    document, which the page showed. Where the renderer read a paragraph's text differently from
    the document's, it marks nothing and leaves both cells empty, and `check` names them.
    """
    reading = session.cards()
    numbers = written_numbers(reading, prelabel_card_starts(prelabels))
    sampled = {span.index for span in prelabels.spans}
    rows: list[dict[str, str]] = []
    for row in session.rows:
        card = reading.card_of.get(row.index)
        number = None if card is None else numbers.get(card.start)
        text = texts[row.index]
        completeness = ""
        if card is not None and number is not None and row.index == card.start and card.state is not None:
            completeness = card.state.value
        underline = highlight = ""
        paragraph = rendered[row.index] if row.index < len(rendered) else None
        if row.index in sampled and paragraph is not None and paragraph.text == text:
            underline = render_markup(text, paragraph.underline)
            highlight = render_markup(text, paragraph.highlight)
        rows.append(
            {
                "index": str(row.index),
                "checked": "y" if row.checked else "",
                "unit": "" if row.unit is None else row.unit.value,
                "card": "" if number is None else str(number),
                "completeness": completeness,
                "text": text,
                "underline": underline,
                "highlight": highlight,
            }
        )
    return Worksheet(columns=WORKSHEET_COLUMNS, rows=tuple(rows))


def csv_bytes(worksheet: Worksheet) -> bytes:
    """A worksheet as `scripts/prelabel_docx.py worksheet` writes one: UTF-8 with a byte-order mark."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(worksheet.columns)
    for row in worksheet.rows:
        writer.writerow([row.get(column, "") for column in worksheet.columns])
    return buffer.getvalue().encode("utf-8-sig")


def _write_whole(path: Path, content: bytes) -> None:
    partial = path.with_name(f".{path.name}.partial")
    partial.write_bytes(content)
    os.replace(partial, path)


# --------------------------------------------------------------------------------------------
# The page's handler, with no socket in it
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]
    body: bytes


def _policy(nonce: str) -> str:
    """Nothing loads from anywhere; the page talks only to the server that sent it."""
    return (
        f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; connect-src 'self'; "
        "img-src 'none'; font-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'"
    )


def _home_relative(path: Path) -> str:
    try:
        return "~/" + str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


class LabellerApp:
    """The page and its three requests, as a function from a request to a response."""

    def __init__(
        self,
        *,
        session: Session,
        prelabels: LabelFile,
        texts: Sequence[str],
        rendered: Sequence[RenderedParagraph],
        worksheet_path: Path,
        progress_path: Path,
        problems_of: Callable[[Worksheet], list[str]],
        clock: Callable[[], float] = time.monotonic,
        token: str | None = None,
    ) -> None:
        self.session = session
        self.prelabels = prelabels
        self.texts = list(texts)
        self.rendered = list(rendered)
        self.worksheet_path = worksheet_path
        self.progress_path = progress_path
        self.problems_of = problems_of
        self.clock = clock
        self.token = token or secrets.token_urlsafe(24)
        self.port: int | None = None
        self.message = ""
        self.finished: dict[str, Any] | None = None
        self._prelabel_rows = {paragraph.index: paragraph for paragraph in prelabels.paragraphs}
        self._prelabel_spans = {span.index: span for span in prelabels.spans}
        self._prelabel_starts = {first: number for number, first in prelabel_card_starts(prelabels)}
        self._prelabel_completeness = {card.card: card.completeness.value for card in prelabels.cards}
        self.routes: dict[tuple[str, str], Callable[[bytes], Response]] = {
            ("GET", "/"): self._page,
            ("GET", "/state"): self._state,
            ("POST", "/key"): self._key,
            ("POST", "/goto"): self._goto,
        }
        if session.complete:
            self._finish()

    # -- requests ----------------------------------------------------------------------------

    def handle(self, method: str, path: str, headers: Mapping[str, str], body: bytes) -> Response:
        lowered = {name.lower(): value for name, value in headers.items()}
        if self.port is None or lowered.get("host") != f"127.0.0.1:{self.port}":
            return self._text(403, "this page answers only at the address the labeller printed")
        route = self.routes.get((method, path.split("?", 1)[0]))
        if route is None:
            return self._text(404, "no such page")
        if path != "/" and not hmac.compare_digest(lowered.get("x-labeller-token", ""), self.token):
            return self._text(403, "reload the page the labeller printed")
        return route(body)

    def _page(self, _: bytes) -> Response:
        nonce = secrets.token_urlsafe(16)
        page = _PAGE.read_text(encoding="utf-8").replace("__TOKEN__", self.token).replace("__NONCE__", nonce)
        return Response(
            200,
            {
                "Content-Type": "text/html; charset=utf-8",
                "Content-Security-Policy": _policy(nonce),
                **self._common_headers(),
            },
            page.encode("utf-8"),
        )

    def _state(self, _: bytes) -> Response:
        return self._json(self.view())

    def _key(self, body: bytes) -> Response:
        request = self._request(body)
        if (
            request is None
            or not isinstance(request.get("key"), str)
            or not isinstance(request.get("row"), int)
        ):
            return self._text(400, "a key is sent as {key, row}")
        self.message = self.session.press(request["key"], request["row"], self.clock())
        return self._after_change()

    def _goto(self, body: bytes) -> Response:
        request = self._request(body)
        if request is None or not isinstance(request.get("row"), int):
            return self._text(400, "a move is sent as {row}")
        self.message = self.session.goto(request["row"])
        return self._after_change()

    def _after_change(self) -> Response:
        save_progress(self.session, self.progress_path)
        if self.session.complete:
            self._finish()
        return self._json(self.view())

    def _finish(self) -> None:
        """Write the worksheet the keys made, and read it back through `check`'s own checks."""
        worksheet = labelled_worksheet(self.session, self.prelabels, self.texts, self.rendered)
        self.worksheet_path.parent.mkdir(parents=True, exist_ok=True)
        _write_whole(self.worksheet_path, csv_bytes(worksheet))
        prefix, shown = self.session.digest[:16], _home_relative(self.worksheet_path)
        importing = (
            f"uv run python scripts/prelabel_docx.py import {prefix} --worksheet {shown} --corrected-by coach"
        )
        self.finished = {
            "worksheet": self.worksheet_path.name,
            "problems": self.problems_of(read_worksheet(self.worksheet_path)),
            "commands": [
                f"uv run python scripts/prelabel_docx.py check {prefix} --worksheet {shown}",
                importing + (" --labeled-blind" if self.session.blind else ""),
            ],
        }

    @staticmethod
    def _request(body: bytes) -> dict[str, Any] | None:
        if len(body) > _LARGEST_BODY:
            return None
        try:
            request = json.loads(body or b"{}")
        except ValueError:
            return None
        return request if isinstance(request, dict) else None

    @staticmethod
    def _common_headers() -> dict[str, str]:
        return {
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        }

    def _json(self, payload: Mapping[str, Any]) -> Response:
        return Response(
            200,
            {"Content-Type": "application/json", **self._common_headers()},
            json.dumps(payload).encode("utf-8"),
        )

    def _text(self, status: int, message: str) -> Response:
        return Response(
            status, {"Content-Type": "text/plain; charset=utf-8", **self._common_headers()}, message.encode()
        )

    # -- what the page shows -------------------------------------------------------------------

    def view(self) -> dict[str, Any]:
        session = self.session
        row = session.current
        reading = session.cards()
        card = reading.card_of.get(row.index)
        number, block = next(
            (number, block)
            for number, block in enumerate(session.blocks, start=1)
            if block[0] <= row.index <= block[1]
        )
        shown: dict[str, Any] = {
            "index": row.index,
            "position": session.position + 1,
            "block": {"number": number, "of": len(session.blocks), "first": block[0], "last": block[1]},
            "paragraph": self._paragraph(row.index),
            "before": [self._paragraph(i) for i in range(max(0, row.index - 2), row.index)],
            "after": [self._paragraph(i) for i in range(row.index + 1, min(len(self.texts), row.index + 3))],
            "label": {
                "unit": None if row.unit is None else row.unit.value,
                "starts_card": row.starts_card,
                "checked": row.checked,
                "card": None if card is None else card.ordinal,
                "card_start": None if card is None else card.start,
                "card_state": None if card is None or card.state is None else card.state.value,
                "notes": list(reading.notes.get(row.index, ())),
            },
        }
        if not session.blind:
            shown["prelabel"] = self._prelabel(row.index)
        spans = self._spans(row.index)
        if spans is not None:
            shown["spans"] = spans
        return {
            "mode": "blind" if session.blind else "shown",
            "prefix": session.digest[:16],
            "row": shown,
            "rows": [
                {"unit": None if label.unit is None else label.unit.value, "checked": label.checked}
                for label in session.rows
            ],
            "indices": [label.index for label in session.rows],
            "progress": {
                "done": session.done,
                "left": len(session.rows) - session.done,
                "total": len(session.rows),
                "rows_per_minute": session.rows_per_minute(),
            },
            "message": self.message,
            "finished": self.finished,
        }

    def _paragraph(self, index: int) -> dict[str, Any]:
        text = self.texts[index]
        rendered = self.rendered[index] if index < len(self.rendered) else None
        readable = rendered is not None and rendered.text == text
        runs = (
            [
                {
                    "text": run.text,
                    "bold": run.bold,
                    "italic": run.italic,
                    "underline": run.underline is not None,
                    "highlight": run.highlight,
                    "size": None if run.half_points is None else run.half_points / 2,
                }
                for run in rendered.runs
                if run.text
            ]
            if rendered is not None and readable
            else [
                {
                    "text": text,
                    "bold": False,
                    "italic": False,
                    "underline": False,
                    "highlight": None,
                    "size": None,
                }
            ]
        )
        label = next((row for row in self.session.rows if row.index == index), None)
        return {
            "index": index,
            "text": text,
            "runs": runs,
            "heading_level": rendered.heading_level if rendered is not None and readable else None,
            "readable": readable,
            "sampled": label is not None,
            "unit": None if label is None or label.unit is None else label.unit.value,
        }

    def _prelabel(self, index: int) -> dict[str, Any]:
        paragraph = self._prelabel_rows[index]
        completeness = None
        if paragraph.card is None:
            where = "no card"
        elif self._prelabel_starts.get(index) == paragraph.card:
            where = "starts a card"
            completeness = self._prelabel_completeness.get(paragraph.card)
        else:
            where = "in a card"
        return {"unit": paragraph.unit.value, "card": where, "completeness": completeness}

    def _spans(self, index: int) -> dict[str, Any] | None:
        prelabel = self._prelabel_spans.get(index)
        if prelabel is None:
            return None
        rendered = self.rendered[index] if index < len(self.rendered) else None
        readable = rendered is not None and rendered.text == self.texts[index]
        document = {
            "underline": [list(r) for r in rendered.underline] if rendered is not None and readable else [],
            "highlight": [list(r) for r in rendered.highlight] if rendered is not None and readable else [],
        }
        spans: dict[str, Any] = {"document": document, "readable": readable}
        if not self.session.blind:
            parser = {
                "underline": [list(r) for r in prelabel.underline],
                "highlight": [list(r) for r in prelabel.highlight],
            }
            spans["prelabel"] = parser
            spans["differs"] = not readable or parser != document
        return spans


# --------------------------------------------------------------------------------------------
# The server: a thin shell round the handler
# --------------------------------------------------------------------------------------------


def _handler_class(app: LabellerApp) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._answer("GET")

        def do_POST(self) -> None:
            self._answer("POST")

        def _answer(self, method: str) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if 0 < length <= _LARGEST_BODY else b""
            response = app.handle(method, self.path, dict(self.headers.items()), body)
            self.send_response(response.status)
            for name, value in response.headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(response.body)))
            self.end_headers()
            self.wfile.write(response.body)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - the base class's name
            """Print nothing: the address is the only thing the labeller prints."""

    return Handler


def serve(
    app: LabellerApp,
    *,
    open_browser: bool = True,
    server_class: Callable[..., Any] = HTTPServer,
) -> None:
    """Serve the page on 127.0.0.1 at a free port, print its address and nothing else, until Ctrl+C."""
    server = server_class(("127.0.0.1", 0), _handler_class(app))
    app.port = int(server.server_address[1])
    address = f"http://127.0.0.1:{app.port}/"
    print(address, flush=True)
    if open_browser:
        webbrowser.open(address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
