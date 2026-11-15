"""`scripts/label_golden_card.py`: the coach's own runs as offsets into the snapshot, and the renders.

Built on the invented store and corpus of `tests/golden/snapshot_world.py`; nothing reads the
operator's files. Every expected offset is found by hand in the invented page (working agreement 6):
the card's two segments are `snapshot_world.SEGMENTS`, and each paragraph's underlined and
highlighted warrant is the invented page's own occurrence of `WARRANT`.
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import golden_snapshots as snaps  # noqa: E402
import import_golden_card as golden  # noqa: E402
import label_golden_card as label  # noqa: E402
from tests.golden.snapshot_world import (  # noqa: E402
    FILLER,
    PAGE,
    SEGMENTS,
    SENTINEL,
    WARRANT,
    World,
    build_world,
    card,
    envelope,
)

from debate_core.evidence.docx_manifest_part import read_embedded_manifest  # noqa: E402

LINKS = {
    "marked": "https://www.brookings.edu/articles/marked-grid",
    "unmarked": "https://www.reuters.com/world/unmarked-grid",
    "absent": "https://www.rand.org/pubs/absent-grid.html",
    "highlighted": "https://www.cfr.org/article/highlighted-grid",
    "spaced": "https://www.csis.org/analysis/spaced-grid",
    "emphasised": "https://www.heritage.org/report/emphasised-grid",
    "stray": "https://www.cato.org/study/stray-grid",
    "split": "https://www.aei.org/research/split-grid",
}

#: The card's body with its cut unmarked: the cutter dropped "words the cutter skipped" with no `…`.
UNMARKED_BODY = (
    f"Plain words {FILLER} {{warrant}} and more after the cut.",
    f"A second paragraph {FILLER} {{warrant}}.",
)
#: A body the invented page does not hold.
ABSENT_BODY = (f"Invented sentences {FILLER} that no page holds {{warrant}}.",)
#: The standard body with doubled spaces and a tab, and (below) its warrants underlined with the
#: spaces around them: the normalizer moves every offset after "Plain", and a span keeps no space.
SPACED_BODY = (
    f"Plain  words {FILLER}\t{{warrant}}and more … after the cut.",
    f"A second paragraph {FILLER}{{warrant}}.",
)
SPACED_WARRANTS = (f" {WARRANT} ", f" {WARRANT}")
#: A body whose last two words, "leaves out.", the page holds only in its closing line: two words
#: are too few to call the rest of the card found there.
STRAY_BODY = (f"A second paragraph {FILLER} {{warrant}} leaves out.",)
#: A body whose omission marker sits inside a word, with nothing of the page left out around it.
SPLIT_BODY = (f"Plain wo…rds {FILLER} {{warrant}} and more words the cutter skipped after the cut.",)

FIRST_WARRANT = [PAGE.index(WARRANT), PAGE.index(WARRANT) + len(WARRANT)]
SECOND_WARRANT = [PAGE.rindex(WARRANT), PAGE.rindex(WARRANT) + len(WARRANT)]


@pytest.fixture
def labelled_world(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> World:
    """Four invented cases, each page stored and recorded: the standard card, one cut unmarked, one
    whose words no page holds, and one whose warrants are highlighted but not underlined."""
    monkeypatch.setattr(snaps, "_checkouts", lambda repository: [REPO_ROOT.resolve()])
    layout = (
        (
            "2025-2026",
            "Policy",
            [card("marked", LINKS["marked"]), card("unmarked", LINKS["unmarked"], UNMARKED_BODY)],
        ),
        ("2024-2025", "LD", [card("absent", LINKS["absent"], ABSENT_BODY)]),
        (
            "2026-2027",
            "PF",
            [
                card("highlighted", LINKS["highlighted"], highlight_only=True),
                card("spaced", LINKS["spaced"], SPACED_BODY, underlined=SPACED_WARRANTS),
                card("emphasised", LINKS["emphasised"], emphasis=True),
                card("stray", LINKS["stray"], STRAY_BODY),
                card("split", LINKS["split"], SPLIT_BODY),
            ],
        ),
    )
    world = build_world(tmp_path, layout, LINKS)
    for name, link in LINKS.items():
        snapshot = world.store_page(link)
        world.report(name, envelope(link, "ACCESSIBLE", snapshot_id=snapshot.snapshot_id))
    assert world.record("--execute") == 0
    capsys.readouterr()
    return world


def _label(world: World, *extra: str) -> int:
    return label.main(["--snapshots", str(world.snapshots), "--fixtures", str(world.fixtures), *extra])


def _expected(world: World, name: str) -> dict[str, Any]:
    return json.loads(
        (world.fixtures / world.case_for(name) / golden.EXPECTED_NAME).read_text(encoding="utf-8")
    )


def _span(bounds: list[int], style: str) -> dict[str, Any]:
    return {"start": bounds[0], "end": bounds[1], "style": style, "purpose": None}


def test_the_coachs_underlines_and_highlights_become_snapshot_offsets(
    labelled_world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _label(labelled_world) == 1  # the absent, stray and split cards are not labelled

    out = capsys.readouterr().out
    tag = "Demand growth strains the marked reserve margin"
    assert _expected(labelled_world, "marked") == {
        "format": "golden-card-expected/1",
        "case_id": labelled_world.case_for("marked"),
        "tag": tag,
        "cite": {
            "short_cite": "Okonkwo 26",
            "full_cite": f"Okonkwo 26 [Ada Okonkwo, senior analyst, 3-4-2026, {LINKS['marked']}]",
        },
        "research_need": tag,
        "segments": SEGMENTS,
        "spans": [
            _span(FIRST_WARRANT, "highlight"),
            _span(FIRST_WARRANT, "underline"),
            _span(SECOND_WARRANT, "highlight"),
            _span(SECOND_WARRANT, "underline"),
        ],
    }
    assert (
        f"{labelled_world.case_for('marked')}: 2 segments (0 unmarked cuts), 2 underlines, 2 highlights, "
        "0 highlighted characters outside the underlining"
    ) in out
    assert "labelled 5, not labelled 3" in out


def test_a_cut_the_cutter_did_not_mark_is_found_and_counted(
    labelled_world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    _label(labelled_world)

    assert _expected(labelled_world, "unmarked")["segments"] == SEGMENTS
    assert f"{labelled_world.case_for('unmarked')}: 2 segments (1 unmarked cuts)" in capsys.readouterr().out


def test_a_card_the_snapshot_does_not_hold_is_not_labelled_and_no_text_is_printed(
    labelled_world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    _label(labelled_world)

    out = capsys.readouterr().out
    case_id = labelled_world.case_for("absent")
    assert (
        f"{case_id}: NOT LABELLED: a stretch of the card is not in the snapshot (stretch 1 of 1, 0 of " in out
    )
    assert not (labelled_world.fixtures / case_id / golden.EXPECTED_NAME).exists()
    assert SENTINEL not in out
    assert "Invented sentences" not in out
    assert WARRANT not in out


def test_a_highlight_outside_the_underlining_is_cut_back_and_counted(
    labelled_world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    _label(labelled_world)

    assert _expected(labelled_world, "highlighted")["spans"] == []
    case_id = labelled_world.case_for("highlighted")
    assert (
        f"{case_id}: 2 segments (0 unmarked cuts), 0 underlines, 0 highlights, "
        f"{2 * len(WARRANT)} highlighted characters outside the underlining"
    ) in capsys.readouterr().out


def test_spans_follow_the_normalizer_and_keep_no_space_at_their_edges(
    labelled_world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    _label(labelled_world)

    expected = _expected(labelled_world, "spaced")
    assert expected["segments"] == SEGMENTS
    assert expected["spans"] == _expected(labelled_world, "marked")["spans"]


def test_verbatims_emphasis_is_underlining(labelled_world: World, capsys: pytest.CaptureFixture[str]) -> None:
    _label(labelled_world)

    assert _expected(labelled_world, "emphasised")["spans"] == [
        _span(FIRST_WARRANT, "highlight"),
        _span(FIRST_WARRANT, "underline"),
        _span(SECOND_WARRANT, "highlight"),
        _span(SECOND_WARRANT, "underline"),
    ]


def test_a_few_words_found_elsewhere_do_not_finish_a_card(
    labelled_world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    _label(labelled_world)

    case_id = labelled_world.case_for("stray")
    found = len(f"A second paragraph {FILLER} {WARRANT}")
    whole = len(f"A second paragraph {FILLER} {WARRANT} leaves out.")
    assert (
        f"{case_id}: NOT LABELLED: a stretch of the card is not in the snapshot "
        f"(stretch 1 of 1, {found} of {whole} characters found)"
    ) in capsys.readouterr().out
    assert not (labelled_world.fixtures / case_id / golden.EXPECTED_NAME).exists()


def test_a_marker_that_leaves_nothing_out_is_refused(
    labelled_world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    _label(labelled_world)

    case_id = labelled_world.case_for("split")
    out = capsys.readouterr().out
    assert (
        f"{case_id}: NOT LABELLED: an omission marker leaves nothing of the snapshot out (after stretch 1)"
        in out
    )
    assert not (labelled_world.fixtures / case_id / golden.EXPECTED_NAME).exists()


def test_every_label_passes_the_operators_check_and_the_structure_test(
    labelled_world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    _label(labelled_world)
    for name in ("absent", "stray", "split"):
        golden.shutil.rmtree(labelled_world.fixtures / labelled_world.case_for(name))

    assert labelled_world.check() == 0
    assert "snapshots verified: 5 of 5\nevidence reproduced: 5 of 5" in capsys.readouterr().out
    for case_dir in sorted(p for p in labelled_world.fixtures.iterdir() if p.is_dir()):
        expected = json.loads((case_dir / golden.EXPECTED_NAME).read_text(encoding="utf-8"))
        assert snaps.expected_structure_problems(expected, case_dir.name) == []


def test_a_snapshot_copy_that_no_longer_verifies_is_not_labelled(
    labelled_world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    case_id = labelled_world.case_for("marked")
    raw = labelled_world.snapshots / case_id / snaps.RAW_NAME
    raw.write_bytes(raw.read_bytes() + b" ")

    _label(labelled_world)

    assert (
        f"{case_id}: NOT LABELLED: the snapshot copy does not verify "
        "(the raw bytes do not hash to the recorded SHA-256)"
    ) in capsys.readouterr().out


# ------------------------------------------------------------------------------------------------
# Expected renders
# ------------------------------------------------------------------------------------------------


@pytest.fixture
def rendered(labelled_world: World, capsys: pytest.CaptureFixture[str]) -> World:
    _label(labelled_world)
    for name in ("absent", "stray", "split"):
        golden.shutil.rmtree(labelled_world.fixtures / labelled_world.case_for(name))
    assert _label(labelled_world, "--render-expected") == 0
    capsys.readouterr()
    return labelled_world


def test_the_render_is_the_labelled_card_verified_against_the_copy(rendered: World) -> None:
    case_id = rendered.case_for("marked")
    manifest = read_embedded_manifest(rendered.fixtures / case_id / label.EXPECTED_RENDER_NAME)

    (card_rendered,) = manifest.cards
    assert card_rendered.format_profile == "team-default"
    assert (card_rendered.evidence_start_offset, card_rendered.evidence_end_offset) == (
        SEGMENTS[0][0],
        SEGMENTS[1][1],
    )
    assert [(o.start_offset, o.end_offset) for o in card_rendered.omitted_ranges] == [
        (SEGMENTS[0][1], SEGMENTS[1][0])
    ]
    # The evidence verifies; the cite is the team's, typed by hand, so no citation field is verified.
    assert card_rendered.verification_status.value == "UNVERIFIED"


def test_the_render_check_passes_on_the_renders_it_wrote(
    rendered: World, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _label(rendered, "--render-expected", "--check") == 0
    assert "rendered and compared 5, differ 0, not rendered 0" in capsys.readouterr().out


def test_the_render_check_fails_when_a_label_changes_or_a_render_is_missing(
    rendered: World, capsys: pytest.CaptureFixture[str]
) -> None:
    changed, missing = rendered.case_for("marked"), rendered.case_for("unmarked")
    path = rendered.fixtures / changed / golden.EXPECTED_NAME
    expected = json.loads(path.read_text(encoding="utf-8"))
    expected["spans"] = expected["spans"][:2]
    path.write_text(json.dumps(expected), encoding="utf-8")
    before = (rendered.fixtures / changed / label.EXPECTED_RENDER_NAME).read_bytes()
    (rendered.fixtures / missing / label.EXPECTED_RENDER_NAME).unlink()

    assert _label(rendered, "--render-expected", "--check") == 1

    out = capsys.readouterr().out
    assert f"{changed}: expected.docx differs" in out
    assert f"{missing}: expected.docx is missing" in out
    assert (rendered.fixtures / changed / label.EXPECTED_RENDER_NAME).read_bytes() == before
    assert not (rendered.fixtures / missing / label.EXPECTED_RENDER_NAME).exists()


def test_a_render_carries_only_the_renderers_own_name_and_check_accepts_it(
    rendered: World, capsys: pytest.CaptureFixture[str]
) -> None:
    render = (rendered.fixtures / rendered.case_for("marked") / label.EXPECTED_RENDER_NAME).read_bytes()

    # Read as a team file's excerpt, a render fails on its author and on the manifest it embeds.
    assert golden.metadata_problems(render) == [
        "customXml/_rels/item1.xml.rels is present",
        "customXml/item1.xml is present",
        "customXml/itemProps1.xml is present",
        "docProps/core.xml creator is set",
        "docProps/core.xml lastModifiedBy is set",
    ]
    assert golden.metadata_problems(render, rendered=True) == []
    assert golden.main(["check", "--fixtures", str(rendered.fixtures)]) == 0
    assert capsys.readouterr().out.endswith("clean\n")


def test_check_flags_a_person_named_in_a_render(rendered: World, capsys: pytest.CaptureFixture[str]) -> None:
    path = rendered.fixtures / rendered.case_for("marked") / label.EXPECTED_RENDER_NAME
    with zipfile.ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    parts["docProps/core.xml"] = parts["docProps/core.xml"].replace(
        golden.RENDERER_AUTHOR.encode(), b"Ottoline Fairweather", 1
    )
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in parts.items():
            archive.writestr(name, data)

    assert golden.main(["check", "--fixtures", str(rendered.fixtures)]) == 1
    assert "docProps/core.xml creator is set" in capsys.readouterr().out


# ------------------------------------------------------------------------------------------------
# The coach's review sheet
# ------------------------------------------------------------------------------------------------


def test_the_review_sheet_lists_every_case_and_the_sign_off_questions(
    rendered: World, capsys: pytest.CaptureFixture[str]
) -> None:
    sheet = rendered.root / "outside" / "review.md"

    assert golden.main(["review", "--output", str(sheet), "--fixtures", str(rendered.fixtures)]) == 0

    text = sheet.read_text(encoding="utf-8")
    marked = rendered.case_for("marked")
    assert (
        f"| `{marked}` | Policy | 2025-26 | think tank | Demand growth strains the marked reserve margin "
        f"| 2 | 2 | 2 | `{rendered.fixtures / marked}` |"
    ) in text
    assert "5 cases: Policy 2, LD 0, PF 3." in text
    assert text.endswith(f"3. {golden.REVIEW_QUESTIONS[2]}\n")
    assert capsys.readouterr().out == "review sheet: 5 cases\n"


def test_the_review_sheet_is_never_written_inside_the_repository(capsys: pytest.CaptureFixture[str]) -> None:
    inside = REPO_ROOT / "tests" / "fixtures" / "golden_cards" / "review.md"

    assert golden.main(["review", "--output", str(inside)]) == 2
    assert not inside.exists()
    assert "write it outside the repository" in capsys.readouterr().err
