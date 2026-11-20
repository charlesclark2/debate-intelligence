"""The committed golden corpus has the structure E09 reads, and holds no evidence text.

CI cannot see a snapshot (the repository is public; the snapshots stay in the operator's local
folder, the PM's ruling of 2026-11-14, Q2 B), so this is what CI checks of each case:
`case.json` records the coach's attestation and a whole snapshot record (digests, URL, fetch date,
access status), and `expected.json` holds offsets, the team's tag, cite and research need, and no
key that names evidence text. The operator's `import_golden_card.py check --snapshots` is the
integrity check behind it. The validators are proved on invented cases first; every expected
problem is written by hand.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import golden_snapshots as snaps  # noqa: E402
import import_golden_card as golden  # noqa: E402

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "golden_cards"

GOOD_CASE: dict[str, Any] = {
    "case_id": "ld-003",
    "candidate_id": "ld-0a1b2c3d4e",
    "event": "LD",
    "season": "2025-2026",
    "source_type": "news",
    "length_band": "short",
    "omission_cut": False,
    "coach_cut_and_reviewed_for_names": True,
    "research_need": "An invented tag",
    "source_link": "https://www.example.org/a",
    "parser_version": "invented",
    "imported_on": "2026-11-14",
    "snapshot": {
        "url": "https://www.example.org/a",
        "canonical_url": "https://example.org/a",
        "final_url": "https://example.org/a",
        "fetched_on": "2026-11-14",
        "access_status": "ACCESSIBLE",
        "provenance_mode": "PUBLISHER_RETRIEVED",
        "raw_sha256": "a" * 64,
        "raw_byte_size": 1200,
        "normalized_text_sha256": "b" * 64,
        "normalized_document_sha256": "c" * 64,
        "normalizer_version": "evidence-normalizer-v1",
        "extractor_version": "invented/1",
        "content_type": "text/html",
        "paragraph_count": 9,
    },
}

GOOD_EXPECTED: dict[str, Any] = {
    "format": "golden-card-expected/1",
    "case_id": "ld-003",
    "tag": "An invented tag",
    "cite": {"short_cite": "Okonkwo 26"},
    "research_need": "An invented tag",
    "segments": [[10, 50], [60, 90]],
    "spans": [
        {"start": 12, "end": 40, "style": "underline", "purpose": None},
        {"start": 20, "end": 30, "style": "highlight", "purpose": "warrant"},
        {"start": 60, "end": 70, "style": "underline", "purpose": None},
    ],
}


def _with(base: dict[str, Any], path: tuple[str, ...], value: Any) -> dict[str, Any]:
    changed = copy.deepcopy(base)
    target = changed
    for key in path[:-1]:
        target = target[key]
    if value is KeyError:
        del target[path[-1]]
    else:
        target[path[-1]] = value
    return changed


def test_a_whole_invented_case_has_no_problems() -> None:
    assert snaps.case_structure_problems(GOOD_CASE, "ld-003") == []
    assert snaps.expected_structure_problems(GOOD_EXPECTED, "ld-003") == []


@pytest.mark.parametrize(
    ("path", "value", "problem"),
    [
        (("coach_cut_and_reviewed_for_names",), KeyError, "the coach's attestation is missing"),
        (("case_id",), "ld-004", "case_id is not the folder's name, or not <event>-<three digits>"),
        (("page_text",), "words", "unexpected keys: page_text"),
        (("snapshot",), KeyError, "no snapshot record"),
        (("snapshot", "raw_sha256"), KeyError, "snapshot record lacks: raw_sha256"),
        (("snapshot", "title"), "A page title", "snapshot record has unexpected keys: title"),
        (
            ("snapshot", "normalized_text_sha256"),
            "B" * 64,
            "snapshot normalized_text_sha256 is not a SHA-256",
        ),
        (("snapshot", "url"), "https://www.example.org/b", "snapshot url is not the case's source link"),
        (("snapshot", "canonical_url"), "example.org/a", "snapshot canonical_url is not an http(s) URL"),
        (("snapshot", "fetched_on"), "14 November", "snapshot fetched_on is not a date"),
        (("snapshot", "access_status"), "PAYWALLED", "snapshot access_status is not ACCESSIBLE"),
        (
            ("snapshot", "provenance_mode"),
            "USER_SUPPLIED",
            "snapshot provenance_mode is not PUBLISHER_RETRIEVED",
        ),
        (("snapshot", "raw_byte_size"), 0, "snapshot raw_byte_size is not a positive count"),
    ],
)
def test_each_gap_in_a_case_is_named(path: tuple[str, ...], value: Any, problem: str) -> None:
    assert problem in snaps.case_structure_problems(_with(GOOD_CASE, path, value), "ld-003")


@pytest.mark.parametrize(
    ("path", "value", "problem"),
    [
        (("format",), "golden-card-expected/0", "format is not golden-card-expected/1"),
        (
            ("evidence_text",),
            "the card's words",
            "a key names evidence text; expected.json holds offsets only",
        ),
        (
            ("cite", "quote"),
            "the card's words",
            "a key names evidence text; expected.json holds offsets only",
        ),
        (("tag",), " ", "tag is not a non-empty string"),
        (("segments",), [[10, 50], [50, 90]], "segments are not in order, separated by omitted text"),
        (("segments",), [[60, 90], [10, 50]], "segments are not in order, separated by omitted text"),
        (("segments",), [[10, 10]], "a segment is empty or reversed"),
        (("segments",), [[10, True]], "a segment is not a [start, end] pair of offsets"),
        (("spans", 0, "end"), 55, "a span is not inside one segment"),
        (("spans", 1, "start"), 5, "a span is not inside one segment"),
        (("spans", 1, "end"), 45, "a highlight is not inside the underlining"),
        (("spans", 2, "style"), "bold", "a span's style is not one of highlight, underline"),
        (("spans", 2, "purpose"), "evidence", "a span's purpose is not a SpanPurpose or null"),
    ],
)
def test_each_gap_in_an_expected_card_is_named(path: tuple[Any, ...], value: Any, problem: str) -> None:
    assert problem in snaps.expected_structure_problems(_with(GOOD_EXPECTED, path, value), "ld-003")


def test_overlapping_spans_of_one_style_are_named() -> None:
    spans = [*GOOD_EXPECTED["spans"], {"start": 30, "end": 45, "style": "underline", "purpose": None}]

    assert "underline spans overlap" in snaps.expected_structure_problems(
        _with(GOOD_EXPECTED, ("spans",), spans), "ld-003"
    )


# ------------------------------------------------------------------------------------------------
# The committed corpus
# ------------------------------------------------------------------------------------------------


def _committed() -> list[Path]:
    return sorted(path for path in FIXTURES.iterdir() if path.is_dir())


def test_every_committed_case_records_its_snapshot_and_attestation() -> None:
    problems = {
        case.name: snaps.case_structure_problems(
            json.loads((case / golden.CASE_NAME).read_text(encoding="utf-8")), case.name
        )
        for case in _committed()
    }
    assert {name: found for name, found in problems.items() if found} == {}


def test_every_committed_case_has_its_expected_card_and_no_evidence_text() -> None:
    problems = {
        case.name: (
            snaps.expected_structure_problems(
                json.loads((case / golden.EXPECTED_NAME).read_text(encoding="utf-8")), case.name
            )
            if (case / golden.EXPECTED_NAME).is_file()
            else ["no expected.json"]
        )
        for case in _committed()
    }
    assert {name: found for name, found in problems.items() if found} == {}


# ------------------------------------------------------------------------------------------------
# ac1's floor (the PM's ruling of 2026-11-20): at least 24 cases, and at least 8 in each event
# ------------------------------------------------------------------------------------------------


def _corpus(policy: int, ld: int, pf: int) -> list[dict[str, str]]:
    counts = {"Policy": policy, "LD": ld, "PF": pf}
    return [{"event": event, "source_type": "news"} for event, n in counts.items() for _ in range(n)]


@pytest.mark.parametrize(
    ("counts", "problems"),
    [
        ((8, 8, 8), []),
        # More than a third elsewhere is fine: a quarter rule would fail Policy here (8 of 36).
        ((8, 14, 14), []),
        ((7, 9, 8), ["Policy: 7 cases, fewer than 8"]),
        ((8, 8, 7), ["23 cases, fewer than 24", "PF: 7 cases, fewer than 8"]),
        ((0, 20, 20), ["Policy: 0 cases, fewer than 8"]),
        (
            (0, 0, 0),
            ["0 cases, fewer than 24", *(f"{e}: 0 cases, fewer than 8" for e in ("Policy", "LD", "PF"))],
        ),
    ],
)
def test_the_corpus_floor_is_24_cases_and_8_per_event(
    counts: tuple[int, int, int], problems: list[str]
) -> None:
    assert golden.corpus_size_problems(_corpus(*counts)) == problems


def test_the_count_lines_list_every_event_and_source_type_with_zeros() -> None:
    cases = [*_corpus(1, 0, 2), {"event": "LD", "source_type": "journal"}]

    assert golden.corpus_count_lines(cases) == [
        "4 cases.",
        "By event: Policy 1, LD 1, PF 2.",
        "By source type: news 3, think tank 0, government 0, journal 1, unknown 0.",
    ]


def test_the_committed_corpus_meets_the_floor_and_its_index_counts_it() -> None:
    cases = [json.loads((case / golden.CASE_NAME).read_text(encoding="utf-8")) for case in _committed()]

    assert golden.corpus_size_problems(cases) == []
    assert (FIXTURES / golden.INDEX_NAME).read_text(encoding="utf-8") == golden.render_index(FIXTURES)
