"""The click-through labeller (`scripts/prelabel_docx.py label`, v1-e31-t18).

Every key is driven through the page's handler, never a socket: `LabellerApp.handle` takes a
method, a path, headers and a body, and the server is a thin shell around it. The file is the
invented one `synthetic.py` builds. Expected labels and card numbers are written by hand from the
keys each test presses and the labeling guide's rules, not taken from a run of the labeller.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from tests.evals.parser.digests import text_digest
from tests.evals.parser.labeller import (
    CardState,
    LabellerApp,
    ProgressError,
    RowLabel,
    Session,
    progress_path_for,
    read_cards,
    serve,
    written_numbers,
)
from tests.evals.parser.labels_schema import (
    REPOSITORY_ROOT,
    CardLabel,
    Category,
    DebateFormat,
    FileLabelHeader,
    FileSamplingPlan,
    LabelFile,
    LabelStatus,
    Manifest,
    ManifestEntry,
    ParagraphLabel,
    ReviewerRole,
    SamplingPlan,
    SpanLabel,
    TemplateFamily,
    label_path_for,
    load_label_file,
)
from tests.evals.parser.synthetic import (
    CLOSING,
    OPENING,
    SECOND_BODY,
    TEST_DIGEST_KEY,
    UNDERLINED,
    build_synthetic_file,
)
from tests.evals.parser.worksheets import read_worksheet

from debate_core.domain.debate_files import CardCompleteness
from debate_core.domain.style_profile import StructuralUnit as U
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION
from debate_core.testing.docx_builder import build_styles_xml

sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

import prelabel_docx as prelabel  # noqa: E402

PLAN_ID = "abcdef0123456789"
PORT = 8123
HOST = {"Host": f"127.0.0.1:{PORT}"}

#: The synthetic file's paragraphs, in order, as `synthetic.py` writes them.
TEXTS = (
    "Maple Grove Negative",
    "Grid Reliability",
    "AT: Reserve Margin Turn",
    "Moratoria collapse the reserve margin",
    "Okonkwo 26, Grid Analyst, Fictional Energy Review",
    OPENING + UNDERLINED + CLOSING,
    "",
    "Their turn is non-unique",
    "Older plants fail first",
    "Lindqvist 25, Professor, Invented University",
    SECOND_BODY,
)


# --------------------------------------------------------------------------------------------
# A one-file evaluation in a scratch directory, pre-labeled by the parser
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Evaluation:
    options: list[str]
    digest: str
    labels: Path
    worksheets: Path

    @property
    def prefix(self) -> str:
        return self.digest[:16]

    @property
    def label_file(self) -> Path:
        return label_path_for(self.digest, self.labels)

    @property
    def csv(self) -> Path:
        return self.worksheets / f"{self.prefix}.csv"

    @property
    def progress(self) -> Path:
        return self.worksheets / f"{self.prefix}.progress.json"

    def run(self, *arguments: str) -> int:
        return prelabel.main([*self.options, *arguments])

    def app(self, *, blind: bool = False, clock: Any = None) -> LabellerApp:
        made = prelabel.labeller_for(
            self.prefix,
            manifest_path=Path(self.options[1]),
            plan_path=Path(self.options[3]),
            labels_dir=self.labels,
            out_dir=self.worksheets,
            blind=blind,
            **({"clock": clock} if clock is not None else {}),
        )
        made.port = PORT
        return made


@pytest.fixture
def evaluation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Evaluation:
    return _make_evaluation(tmp_path, monkeypatch)


def _make_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, styles_xml: str | None = None
) -> _Evaluation:
    """The synthetic file as a one-file evaluation, pre-labeled by the `prelabel` command."""
    synthetic = build_synthetic_file(LabelStatus.PRELABELED, styles_xml=styles_xml)
    private = tmp_path / "private"
    private.mkdir()
    (private / "digest.key").write_text(TEST_DIGEST_KEY.hex() + "\n", encoding="utf-8")
    monkeypatch.setenv("DEBATE_PARSER_EVAL_KEY_FILE", str(private / "digest.key"))
    docx = tmp_path / "corpus" / "invented.docx"
    docx.parent.mkdir()
    docx.write_bytes(synthetic.content)
    (private / "paths.json").write_text(json.dumps({synthetic.digest: str(docx)}), encoding="utf-8")
    monkeypatch.setenv("DEBATE_PARSER_EVAL_PATHS", str(private / "paths.json"))
    directory = tmp_path / "eval"
    labels = directory / "labels"
    labels.mkdir(parents=True)
    entry = ManifestEntry(
        digest=synthetic.digest,
        category=Category.TEAM,
        season="2025-26",
        debate_format=DebateFormat.LD,
        template_family=TemplateFamily.VERBATIM,
        pr_subset=True,
    )
    plan = SamplingPlan(
        plan_id=PLAN_ID,
        generated_on="2026-10-14",
        parser_version="test",
        files=(FileSamplingPlan(digest=synthetic.digest, paragraphs=11, blocks=((0, 10),), full=True),),
    )
    (directory / "manifest.json").write_text(Manifest(entries=(entry,)).model_dump_json(), encoding="utf-8")
    (directory / "sampling-plan.json").write_text(plan.model_dump_json(), encoding="utf-8")
    made = _Evaluation(
        options=[
            "--manifest",
            str(directory / "manifest.json"),
            "--plan",
            str(directory / "sampling-plan.json"),
            "--labels-dir",
            str(labels),
        ],
        digest=synthetic.digest,
        labels=labels,
        worksheets=tmp_path / "worksheets",
    )
    assert made.run("prelabel", made.prefix) == 0
    return made


def _state(app: LabellerApp) -> dict[str, Any]:
    response = app.handle("GET", "/state", {**HOST, "X-Labeller-Token": app.token}, b"")
    assert response.status == 200, response.body
    return json.loads(response.body)


def _press(app: LabellerApp, key: str, row: int | None = None) -> dict[str, Any]:
    """Press `key` on the row the page shows, or on `row` when a test means a stale page."""
    at = _state(app)["row"]["index"] if row is None else row
    response = app.handle(
        "POST",
        "/key",
        {**HOST, "X-Labeller-Token": app.token, "Content-Type": "application/json"},
        json.dumps({"key": key, "row": at}).encode(),
    )
    assert response.status == 200, response.body
    return json.loads(response.body)


def _keys(app: LabellerApp, *keys: str) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for key in keys:
        state = _press(app, key)
    return state


# --------------------------------------------------------------------------------------------
# ac1: the page, and every key through its handler
# --------------------------------------------------------------------------------------------


def test_the_page_shows_the_row_its_neighbours_its_block_its_pre_label_and_the_count(
    evaluation: _Evaluation,
) -> None:
    app = evaluation.app()
    _keys(app, "Enter", "Enter", "Enter", "Enter")

    state = _state(app)

    row = state["row"]
    assert row["index"] == 4
    assert row["paragraph"]["text"] == TEXTS[4]
    assert [p["text"] for p in row["before"]] == [TEXTS[2], TEXTS[3]]
    assert [p["text"] for p in row["after"]] == [TEXTS[5], TEXTS[6]]
    assert row["block"] == {"number": 1, "of": 1, "first": 0, "last": 10}
    assert row["prelabel"] == {"unit": "CITE", "card": "in a card", "completeness": None}
    assert state["progress"]["done"] == 4 and state["progress"]["left"] == 7


def test_a_paragraph_is_rendered_with_its_heading_bold_underline_and_highlight(
    evaluation: _Evaluation,
) -> None:
    app = evaluation.app()
    _keys(app, *["Enter"] * 4)

    state = _state(app)

    cite = state["row"]["paragraph"]
    assert cite["runs"][0] == {"text": "Okonkwo 26", "bold": False, "italic": False, "underline": False,
                               "highlight": None, "size": None}  # fmt: skip
    evidence = state["row"]["after"][0]
    assert [(run["text"], run["underline"], run["highlight"]) for run in evidence["runs"]] == [
        (OPENING, False, None),
        (UNDERLINED, True, "cyan"),
        (CLOSING, False, None),
    ]
    assert state["row"]["before"][1]["heading_level"] == 4


def test_accept_keeps_the_label_shown_checks_the_row_and_moves_on(evaluation: _Evaluation) -> None:
    app = evaluation.app()

    for key in ("Enter", " "):
        before = _state(app)["row"]
        state = _press(app, key)
        assert state["row"]["index"] == before["index"] + 1
        assert state["rows"][before["index"]] == {"unit": before["label"]["unit"], "checked": True}


@pytest.mark.parametrize(
    "key, unit",
    [("p", "POCKET"), ("h", "HAT"), ("b", "BLOCK"), ("t", "TAG"), ("c", "CITE"), ("e", "EVIDENCE"),
     ("a", "ANALYTIC"), ("u", "UNDERTAG"), ("o", "OTHER"), ("E", "EVIDENCE")],
)  # fmt: skip
def test_a_unit_key_sets_that_unit_checks_the_row_and_moves_on(
    evaluation: _Evaluation, key: str, unit: str
) -> None:
    app = evaluation.app()

    state = _press(app, key)

    assert state["rows"][0] == {"unit": unit, "checked": True}
    assert state["row"]["index"] == 1


def test_the_new_card_key_starts_a_card_on_this_row_and_neither_checks_nor_moves(
    evaluation: _Evaluation,
) -> None:
    app = evaluation.app()
    _keys(app, *["Enter"] * 7)

    state = _keys(app, "n", "t")

    assert state["rows"][7] == {"unit": "TAG", "checked": True}
    started = _press(app, "Backspace")["row"]
    assert started["index"] == 7 and started["label"]["starts_card"] is True
    after_n = _press(app, "n")
    assert after_n["row"]["index"] == 7 and after_n["row"]["label"]["starts_card"] is False
    assert after_n["rows"][7]["checked"] is True


def test_the_completeness_key_cycles_the_cards_completeness_and_offers_cut_at_a_blocks_edge(
    evaluation: _Evaluation,
) -> None:
    app = evaluation.app()
    _keys(app, *["Enter"] * 10)
    assert _state(app)["row"]["label"]["card_state"] == "FULL"

    seen = [_press(app, "k")["row"]["label"]["card_state"] for _ in range(4)]

    assert seen == ["ABBREVIATED", "CITE_ONLY", "CUT_BY_BLOCK_EDGE", "FULL"]
    assert _state(app)["row"]["index"] == 10 and _state(app)["rows"][10]["checked"] is False


def test_back_moves_to_the_row_before_and_checks_nothing(evaluation: _Evaluation) -> None:
    app = evaluation.app()
    _keys(app, "Enter", "Enter")

    for key in ("Backspace", "ArrowLeft"):
        before = [row["checked"] for row in _state(app)["rows"]]
        state = _press(app, key)
        assert [row["checked"] for row in state["rows"]] == before
    assert _state(app)["row"]["index"] == 0
    assert _press(app, "Backspace")["row"]["index"] == 0


def test_an_unknown_key_changes_nothing(evaluation: _Evaluation) -> None:
    app = evaluation.app()
    before = _state(app)

    after = _press(app, "z")

    assert after["rows"] == before["rows"] and after["row"]["index"] == 0
    assert "z" in after["message"]


# --------------------------------------------------------------------------------------------
# ac1: card numbers follow from the card starts, by the labeling guide's rules
# --------------------------------------------------------------------------------------------


def _rows(layout: str, first: int = 0) -> list[RowLabel]:
    """`TAG* CITE EVIDENCE`: one row per word, `*` marking a card start, indices from `first`."""
    return [
        RowLabel(index=first + n, unit=U(word.rstrip("*")), starts_card=word.endswith("*"), checked=True)
        for n, word in enumerate(layout.split())
    ]


def _membership(layout: str, blocks: tuple[tuple[int, int], ...] | None = None,
                states: dict[int, CardState] | None = None, first: int = 0) -> list[list[int]]:  # fmt: skip
    rows = _rows(layout, first)
    blocks = blocks or ((rows[0].index, rows[-1].index),)
    reading = read_cards(rows, blocks, states or {})
    return [list(card.members) for card in reading.cards if card.state is not CardState.CUT]


@pytest.mark.parametrize(
    "layout, expected",
    [
        ("TAG* CITE EVIDENCE", [[0, 1, 2]]),
        # A blank inside a card is not in it, and an analytic ends it.
        ("TAG* UNDERTAG CITE EVIDENCE OTHER EVIDENCE ANALYTIC TAG* CITE", [[0, 1, 2, 3, 5], [7, 8]]),
        # Wiki-converted: cards with no tag start at their cite.
        ("CITE* EVIDENCE CITE* EVIDENCE", [[0, 1], [2, 3]]),
        # A cite split over two paragraphs is two CITE rows in one card.
        ("TAG* CITE CITE EVIDENCE", [[0, 1, 2, 3]]),
        # A TAG nobody marked as a start ends the card before it and starts none.
        ("TAG* CITE EVIDENCE TAG CITE EVIDENCE", [[0, 1, 2]]),
        # A body with no cite and no tag above it in the block is a stray body, in no card.
        ("EVIDENCE EVIDENCE TAG* CITE EVIDENCE", [[2, 3, 4]]),
        # Any heading ends a card.
        ("TAG* CITE EVIDENCE BLOCK EVIDENCE", [[0, 1, 2]]),
        # A card ends at its last EVIDENCE; a cite-only card at its last CITE.
        ("TAG* CITE EVIDENCE UNDERTAG", [[0, 1, 2]]),
        ("TAG* CITE UNDERTAG", [[0, 1]]),
        # A start on anything but a TAG or a CITE starts nothing.
        ("EVIDENCE* CITE EVIDENCE", []),
    ],
)
def test_card_membership_follows_the_guide(layout: str, expected: list[list[int]]) -> None:
    assert _membership(layout) == expected


def test_a_card_never_crosses_a_block_edge() -> None:
    """Rows 0-2 and 3-5 are two blocks: the card open at row 2 closes there."""
    assert _membership("TAG* CITE EVIDENCE EVIDENCE CITE EVIDENCE", blocks=((0, 2), (3, 5))) == [[0, 1, 2]]


def test_a_card_cut_off_by_the_end_of_a_block_is_left_unnumbered() -> None:
    """The guide: number a card only when the whole of it, tag, cite and body, is in the block."""
    rows = _rows("TAG* CITE EVIDENCE TAG* CITE EVIDENCE")
    reading = read_cards(rows, ((0, 5),), {3: CardState.CUT, 0: CardState.FULL})

    assert [(card.members, card.ordinal) for card in reading.cards] == [((0, 1, 2), 1), ((3, 4, 5), None)]
    numbers = written_numbers(reading, ())
    assert numbers == {0: 0}


def test_cut_is_offered_only_for_the_first_and_last_card_of_a_block() -> None:
    rows = _rows("TAG* CITE EVIDENCE TAG* CITE EVIDENCE TAG* CITE EVIDENCE")
    session = Session(digest="d" * 64, blocks=((0, 8),), rows=rows, card_states={3: CardState.CITE_ONLY},
                      position=4, blind=False, prelabels_fingerprint="")  # fmt: skip

    session.press("k", 4)

    assert session.card_states[3] is CardState.FULL


def test_problems_with_a_card_are_named_on_its_rows() -> None:
    reading = read_cards(_rows("TAG* EVIDENCE TAG CITE EVIDENCE* CITE"), ((0, 5),), {})

    assert any("no CITE" in note for note in reading.notes[0])
    assert any("no completeness" in note for note in reading.notes[0])
    assert any("not marked as the start" in note for note in reading.notes[2])
    assert any("starts at its TAG" in note for note in reading.notes[4])


def test_written_card_numbers_keep_a_pre_label_cards_number_and_give_new_cards_unused_ones() -> None:
    """A card that starts where a pre-label card started keeps its number, so a row whose card did
    not change is not counted as changed; the number is never shown on the page."""
    rows = _rows("TAG* CITE EVIDENCE TAG* CITE EVIDENCE", first=40)
    reading = read_cards(rows, ((40, 45),), {40: CardState.FULL, 43: CardState.FULL})
    prelabel_cards = ((7, 40), (9, 44))

    assert written_numbers(reading, prelabel_cards) == {40: 7, 43: 10}


# --------------------------------------------------------------------------------------------
# ac2: a row is checked only by a key pressed on it; progress is saved and resumed
# --------------------------------------------------------------------------------------------


def test_a_key_sent_for_a_row_the_page_is_not_on_changes_nothing(evaluation: _Evaluation) -> None:
    app = evaluation.app()
    _keys(app, "Enter")
    before = _state(app)

    for key in ("Enter", "t", "n", "k"):
        state = _press(app, key, row=5)
        assert state["rows"] == before["rows"] and state["row"]["index"] == 1
        assert "not on" in state["message"]


def test_the_handler_has_no_route_that_checks_more_than_one_row(evaluation: _Evaluation) -> None:
    app = evaluation.app()
    headers = {**HOST, "X-Labeller-Token": app.token}

    assert set(app.routes) == {("GET", "/"), ("GET", "/state"), ("POST", "/key"), ("POST", "/goto")}
    for path in ("/accept-all", "/accept-block", "/accept-file", "/keys"):
        assert app.handle("POST", path, headers, b"{}").status == 404
    assert app.handle("POST", "/goto", headers, json.dumps({"row": 9}).encode()).status == 200
    assert not any(row["checked"] for row in _state(app)["rows"])


_KEYS = st.sampled_from(
    ["Enter", " ", "p", "h", "b", "t", "c", "e", "a", "u", "o", "n", "k", "Backspace", "x"]
)


@settings(max_examples=150, deadline=None)
@given(keys=st.lists(_KEYS, max_size=60), blind=st.booleans())
def test_each_key_checks_at_most_the_row_it_was_pressed_on(keys: list[str], blind: bool) -> None:
    rows = _rows("POCKET HAT BLOCK TAG* CITE EVIDENCE OTHER ANALYTIC TAG* CITE EVIDENCE")
    session = Session(digest="d" * 64, blocks=((0, 10),), rows=[replace(r, checked=False) for r in rows],
                      card_states={3: CardState.FULL, 8: CardState.FULL}, position=0, blind=blind,
                      prelabels_fingerprint="")  # fmt: skip
    if blind:
        session.rows = [replace(row, unit=None, starts_card=False) for row in session.rows]
        session.card_states = {}
    for key in keys:
        before = {row.index for row in session.rows if row.checked}
        pressed_on = session.current.index
        session.press(key, pressed_on)
        after = {row.index for row in session.rows if row.checked}
        assert after - before <= {pressed_on}
        assert before <= after


def test_progress_is_saved_after_every_key_and_holds_no_text(evaluation: _Evaluation) -> None:
    app = evaluation.app()

    for key in ("Enter", "h", "n", "k", "Backspace"):
        state = _press(app, key)
        saved = json.loads(evaluation.progress.read_text(encoding="utf-8"))
        assert saved["position"] == state["row"]["index"]
        assert [row["checked"] for row in saved["rows"]] == [row["checked"] for row in state["rows"]]
    raw = evaluation.progress.read_text(encoding="utf-8")
    assert not [text for text in TEXTS if text and text in raw]


def test_the_labeller_resumes_where_it_stopped_with_the_checked_rows_shown_checked(
    evaluation: _Evaluation,
) -> None:
    first = evaluation.app()
    _keys(first, "Enter", "h", "Enter")
    stopped = _state(first)

    resumed = _state(evaluation.app())

    assert resumed["row"]["index"] == 3
    assert resumed["rows"] == stopped["rows"]
    assert [row["checked"] for row in resumed["rows"]][:4] == [True, True, True, False]
    assert resumed["rows"][1]["unit"] == "HAT"


def test_a_progress_directory_inside_the_repository_is_refused(
    evaluation: _Evaluation, capsys: pytest.CaptureFixture[str]
) -> None:
    inside = REPOSITORY_ROOT / "build" / "labeller-progress"

    with pytest.raises(ProgressError, match="outside the repository"):
        progress_path_for(inside, evaluation.digest)
    assert evaluation.run("label", evaluation.prefix, "--out-dir", str(inside), "--no-browser") == 1
    assert "outside the repository" in capsys.readouterr().err
    assert not inside.exists()


def test_progress_saved_against_other_pre_labels_is_refused(evaluation: _Evaluation) -> None:
    _keys(evaluation.app(), "Enter")
    labels = load_label_file(evaluation.label_file)
    changed = replace(labels, paragraphs=(labels.paragraphs[0].model_copy(update={"unit": U.OTHER}),
                                          *labels.paragraphs[1:]))  # fmt: skip
    evaluation.label_file.write_text(changed.to_jsonl(), encoding="utf-8")

    with pytest.raises(ProgressError, match="pre-labels changed"):
        evaluation.app()


def test_a_worksheet_worked_on_in_a_spreadsheet_is_never_overwritten(evaluation: _Evaluation) -> None:
    assert evaluation.run("worksheet", evaluation.prefix, "--out-dir", str(evaluation.worksheets)) == 0
    evaluation.app()  # an untouched worksheet is fine: the labeller's replaces it at the end
    edited = evaluation.csv.read_bytes().replace(b",POCKET,", b",HAT,")
    evaluation.csv.write_bytes(edited)

    with pytest.raises(ProgressError, match="changed in a spreadsheet"):
        evaluation.app()
    (evaluation.worksheets / f"{evaluation.prefix}.numbers").mkdir()
    evaluation.csv.unlink()
    with pytest.raises(ProgressError, match="Numbers"):
        evaluation.app()


def test_a_corrected_file_is_not_labeled_again(evaluation: _Evaluation) -> None:
    labels = load_label_file(evaluation.label_file)
    header = labels.header.model_copy(
        update={"status": LabelStatus.CORRECTED, "corrected_by": ReviewerRole.COACH}
    )
    evaluation.label_file.write_text(replace(labels, header=header).to_jsonl(), encoding="utf-8")

    with pytest.raises(ProgressError, match="already CORRECTED"):
        evaluation.app()


# --------------------------------------------------------------------------------------------
# ac3: pre-label, keys, write, check, import, end to end
# --------------------------------------------------------------------------------------------

#: What the keys below say, written by hand: (unit, card) per paragraph.
_KEYED: tuple[tuple[U, int | None], ...] = (
    (U.POCKET, None),
    (U.HAT, None),
    (U.BLOCK, None),
    (U.TAG, 0),
    (U.CITE, 0),
    (U.EVIDENCE, 0),
    (U.OTHER, None),
    (U.TAG, 2),
    (U.UNDERTAG, 2),
    (U.CITE, 2),
    (U.EVIDENCE, 2),
)
#: Underline and highlight of every paragraph, from the markup `synthetic.py` writes.
_Ranges = tuple[tuple[int, int], ...]
_MARKED: _Ranges = ((len(OPENING), len(OPENING) + len(UNDERLINED)),)
_SPANS: dict[int, tuple[_Ranges, _Ranges]] = {
    **{index: ((), ()) for index in range(11)},
    5: (_MARKED, _MARKED),
    10: (((0, len(SECOND_BODY)),), ()),
}


def _expected_label_file(digest: str, sampled: list[int], *, blind: bool = False) -> LabelFile:
    return LabelFile(
        header=FileLabelHeader(
            digest=digest,
            paragraph_count=11,
            blocks=((0, 10),),
            plan_id=PLAN_ID,
            status=LabelStatus.CORRECTED,
            prelabel_parser_version=DOCX_PARSER_VERSION,
            corrected_by=ReviewerRole.COACH,
            rows_changed_from_prelabel=4,
            labeled_blind=blind,
        ),
        paragraphs=tuple(
            ParagraphLabel(
                index=index,
                length=len(TEXTS[index]),
                text_digest=text_digest(TEXTS[index], TEST_DIGEST_KEY),
                unit=unit,
                card=card,
            )  # fmt: skip
            for index, (unit, card) in enumerate(_KEYED)
        ),
        cards=(
            CardLabel(card=0, completeness=CardCompleteness.FULL),
            CardLabel(card=2, completeness=CardCompleteness.ABBREVIATED),
        ),
        spans=tuple(SpanLabel(index=i, underline=_SPANS[i][0], highlight=_SPANS[i][1]) for i in sampled),
    )


#: Accepted, changed, one new card (row 7), one completeness (card 2, ABBREVIATED).
_SHOWN_KEYS = (
    "Enter",
    "Enter",
    " ",
    "Enter",
    "Enter",
    "Enter",
    "o",
    "n",
    "t",
    "n",
    "u",
    "Enter",
    "k",
    "k",
    "Enter",
)
#: Blind, every unit is pressed; card 0's completeness is set by going back to its body.
_BLIND_KEYS = (
    "p",
    "h",
    "b",
    "n",
    "t",
    "c",
    "e",
    "Backspace",
    "k",
    "e",
    "o",
    "n",
    "t",
    "u",
    "c",
    "e",
    "k",
    "k",
)


@pytest.mark.parametrize("blind", [False, True], ids=["pre-label shown", "blind"])
def test_label_every_row_by_keys_then_check_and_import_take_the_worksheet_unchanged(
    evaluation: _Evaluation, capsys: pytest.CaptureFixture[str], blind: bool
) -> None:
    sampled = [span.index for span in load_label_file(evaluation.label_file).spans]
    app = evaluation.app(blind=blind)

    state = _keys(app, *(_BLIND_KEYS if blind else _SHOWN_KEYS))

    assert state["progress"]["left"] == 0
    assert state["finished"]["worksheet"] == f"{evaluation.prefix}.csv"
    assert state["finished"]["problems"] == []
    assert evaluation.csv.exists()
    capsys.readouterr()
    assert evaluation.run("check", evaluation.prefix, "--worksheet", str(evaluation.csv)) == 0
    assert "ready to import; 11 rows checked, 4 labeled differently" in capsys.readouterr().out
    imported = ["import", evaluation.prefix, "--worksheet", str(evaluation.csv), "--corrected-by", "coach"]
    assert evaluation.run(*imported, *(["--labeled-blind"] if blind else [])) == 0
    assert load_label_file(evaluation.label_file) == _expected_label_file(
        evaluation.digest, sampled, blind=blind
    )
    assert state["finished"]["commands"][-1].endswith("--labeled-blind" if blind else "--corrected-by coach")


def test_a_worksheet_the_page_wrote_with_a_problem_is_named_by_checks_own_words(
    evaluation: _Evaluation,
) -> None:
    app = evaluation.app()
    keys = list(_SHOWN_KEYS)
    keys[12:14] = []  # card 2 never gets a completeness

    state = _keys(app, *keys)

    assert state["progress"]["left"] == 0
    assert any("card 2 has no completeness" in problem for problem in state["finished"]["problems"])


def test_going_back_after_the_end_rewrites_the_worksheet(evaluation: _Evaluation) -> None:
    app = evaluation.app()
    _keys(app, *_SHOWN_KEYS)
    first = evaluation.csv.read_bytes()

    _press(app, "Backspace")
    _press(app, "k")

    assert evaluation.csv.read_bytes() != first
    assert b"CITE_ONLY" not in first and b"CITE_ONLY" in evaluation.csv.read_bytes()


# --------------------------------------------------------------------------------------------
# ac4: a span row shows the document's marks beside the pre-label's, and flags a difference
# --------------------------------------------------------------------------------------------


def test_a_span_row_shows_the_documents_marks_and_the_pre_labels(evaluation: _Evaluation) -> None:
    app = evaluation.app()
    labels = load_label_file(evaluation.label_file)
    assert 10 in {span.index for span in labels.spans}
    _keys(app, *["Enter"] * 10)

    spans = _state(app)["row"]["spans"]

    assert spans["document"] == {"underline": [[0, len(SECOND_BODY)]], "highlight": []}
    assert spans["prelabel"] == {"underline": [[0, len(SECOND_BODY)]], "highlight": []}
    assert spans["differs"] is False


def test_a_span_row_where_the_document_and_the_pre_label_disagree_is_flagged(evaluation: _Evaluation) -> None:
    """The parser reads highlight only where a run sets it; a highlight from a style is the
    document's all the same. Here the pre-label is edited to say what such a miss looks like."""
    labels = load_label_file(evaluation.label_file)
    spans = tuple(
        span.model_copy(update={"underline": ((0, 5),)}) if span.index == 10 else span
        for span in labels.spans
    )
    evaluation.label_file.write_text(replace(labels, spans=spans).to_jsonl(), encoding="utf-8")
    app = evaluation.app()
    _keys(app, *["Enter"] * 10)

    row = _state(app)["row"]

    assert row["spans"]["differs"] is True
    assert row["spans"]["document"]["underline"] == [[0, len(SECOND_BODY)]]
    assert row["spans"]["prelabel"]["underline"] == [[0, 5]]


def test_a_highlight_the_document_inherits_and_the_parser_does_not_read_is_flagged_and_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ac4 on an invented document with both kinds: the evidence's direct underline and highlight,
    and a yellow highlight every run inherits from the document defaults. The parser reads only a
    run's own highlight, so on every sampled row the two readings differ, and it is flagged."""
    defaults = (
        '<w:docDefaults><w:rPrDefault><w:rPr><w:highlight w:val="yellow"/></w:rPr></w:rPrDefault>'
        "</w:docDefaults>"
    )
    styles = build_styles_xml().replace("<w:style ", defaults + "<w:style ", 1)
    evaluation = _make_evaluation(tmp_path, monkeypatch, styles_xml=styles)
    sampled = [span.index for span in load_label_file(evaluation.label_file).spans]
    assert sampled, "the invented file has no span row, so this test would prove nothing"
    app = evaluation.app()
    headers = {**HOST, "X-Labeller-Token": app.token}

    for index in sampled:
        assert app.handle("POST", "/goto", headers, json.dumps({"row": index}).encode()).status == 200
        spans = _state(app)["row"]["spans"]
        assert spans["document"]["highlight"] == [[0, len(TEXTS[index])]]
        assert spans["prelabel"]["highlight"] != spans["document"]["highlight"]
        assert spans["differs"] is True
    app.handle("POST", "/goto", headers, json.dumps({"row": 0}).encode())
    _keys(app, *["Enter"] * 11)

    rows = {int(row["index"]): row for row in read_worksheet(evaluation.csv).rows}
    for index in sampled:
        assert rows[index]["highlight"] == f"⟦{TEXTS[index]}⟧"


def test_the_worksheet_carries_the_documents_marks_not_the_pre_labels(evaluation: _Evaluation) -> None:
    labels = load_label_file(evaluation.label_file)
    spans = tuple(span.model_copy(update={"underline": ((0, 5),)}) if span.index == 10 else span
                  for span in labels.spans)  # fmt: skip
    evaluation.label_file.write_text(replace(labels, spans=spans).to_jsonl(), encoding="utf-8")
    app = evaluation.app()

    _keys(app, *["Enter"] * 11)

    text = evaluation.csv.read_text(encoding="utf-8-sig")
    assert f"⟦{SECOND_BODY}⟧" in text
    assert f"⟦{SECOND_BODY[:5]}⟧" not in text


# --------------------------------------------------------------------------------------------
# ac5: blind mode
# --------------------------------------------------------------------------------------------


def test_blind_mode_sends_no_pre_label_to_the_page(evaluation: _Evaluation) -> None:
    app = evaluation.app(blind=True)
    _keys(app, *["p", "h", "b"])

    for _ in range(8):
        state = _state(app)
        assert state["mode"] == "blind"
        assert "prelabel" not in state["row"]
        assert "prelabel" not in (state["row"].get("spans") or {}) and "differs" not in (
            state["row"].get("spans") or {}
        )
        assert state["row"]["label"]["unit"] is None
        _press(app, "o")


def test_blind_mode_will_not_accept_a_row_with_no_unit(evaluation: _Evaluation) -> None:
    app = evaluation.app(blind=True)

    state = _press(app, "Enter")

    assert state["row"]["index"] == 0 and state["rows"][0]["checked"] is False
    assert "unit" in state["message"]


@pytest.mark.parametrize("started_blind", [True, False])
def test_a_file_started_in_one_mode_is_not_resumed_in_the_other(
    evaluation: _Evaluation, started_blind: bool
) -> None:
    _keys(evaluation.app(blind=started_blind), "p")

    with pytest.raises(
        ProgressError, match="started blind" if started_blind else "started with the pre-labels shown"
    ):
        evaluation.app(blind=not started_blind)


# --------------------------------------------------------------------------------------------
# ac7: the pace
# --------------------------------------------------------------------------------------------


def test_the_page_shows_rows_per_minute(evaluation: _Evaluation) -> None:
    now = [1000.0]
    app = evaluation.app(clock=lambda: now[0])
    assert _state(app)["progress"]["rows_per_minute"] is None

    for _ in range(6):
        _press(app, "Enter")
        now[0] += 6.0
    _press(app, "Backspace")

    assert _state(app)["progress"]["rows_per_minute"] == 10.0


# --------------------------------------------------------------------------------------------
# The page: loopback only, nothing from the network, nothing out
# --------------------------------------------------------------------------------------------


def test_the_page_loads_nothing_from_the_network_and_may_call_only_its_own_server(
    evaluation: _Evaluation,
) -> None:
    app = evaluation.app()

    response = app.handle("GET", "/", HOST, b"")

    page = response.body.decode()
    assert response.status == 200
    for reference in ("http:", "https:", "//", "<link", "@import", "url(", " src=", "<iframe", "<img"):
        assert reference not in page, reference
    policy = response.headers["Content-Security-Policy"]
    assert "default-src 'none'" in policy and "connect-src 'self'" in policy
    assert "form-action 'none'" in policy


def test_a_request_from_another_host_or_without_the_token_is_refused(evaluation: _Evaluation) -> None:
    app = evaluation.app()
    body = json.dumps({"key": "Enter", "row": 0}).encode()

    assert (
        app.handle(
            "POST", "/key", {"Host": "rebound.example:8123", "X-Labeller-Token": app.token}, body
        ).status
        == 403
    )
    assert app.handle("POST", "/key", HOST, body).status == 403
    assert app.handle("GET", "/state", {**HOST, "X-Labeller-Token": "guess"}, b"").status == 403
    assert not any(row["checked"] for row in _state(app)["rows"])


def test_the_server_binds_loopback_at_a_free_port_and_prints_only_its_address(
    evaluation: _Evaluation, capsys: pytest.CaptureFixture[str]
) -> None:
    bound: list[tuple[str, int]] = []

    class FakeServer:
        def __init__(self, address: tuple[str, int], handler: Any) -> None:
            bound.append(address)
            self.server_address = ("127.0.0.1", 50123)

        def serve_forever(self) -> None:
            raise KeyboardInterrupt

        def server_close(self) -> None:
            pass

    app = evaluation.app()
    serve(app, open_browser=False, server_class=FakeServer)

    assert bound == [("127.0.0.1", 0)]
    assert capsys.readouterr().out == "http://127.0.0.1:50123/\n"
    assert app.port == 50123
