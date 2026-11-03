"""`scripts/count_matching_recall.py`, on an invented parsed store built in a temporary directory.

The store holds one document of ten cards, the bodies of `test_recall_shapes.py`, each its own
cluster, all under one tag and one cite: a Kessler-shaped card with its one-word copy and two trims
sharing nothing, a Brannock-shaped card that is its two trims end to end, and a long card with a copy
holding neither of its ends and a passage of its end. Every expected figure is worked out by hand.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from tests.scripts.test_compare_card_clusters import CASELIST, _document, _fingerprint_of, _write_store

from debate_core.domain.debate_files import CardCompleteness

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import count_matching_recall as script  # noqa: E402


def _words(stem: str, start: int, stop: int) -> list[str]:
    return [f"{stem}{number}" for number in range(start, stop)]


KESSLER = _words("k", 0, 46)
LONG = _words("w", 0, 200)
BODIES = (
    KESSLER,
    [*KESSLER[:20], "kchanged", *KESSLER[21:]],
    KESSLER[:14],
    KESSLER[28:],
    _words("b", 0, 29),
    _words("b", 0, 13),
    _words("b", 13, 29),
    LONG,
    ["wfirst", *LONG[1:99], "wlast"],
    LONG[150:],
)
#: Words of the bodies and of the template's tag and cite: output meant to hold counts must not
#: contain them.
TELLTALE = ("k3", "kchanged", "b10", "w150", "wfirst", "Invented", "Fictional")
BANDS = {"0 to 299": 0, "300 to 999": 0, "1,000 to 2,999": 0, "3,000 or more": 0}


def write_recall_store(root: Path) -> None:
    """The invented store: one document of the ten bodies, each its own cluster."""
    cards = tuple(("Invented 26", CardCompleteness.FULL, " ".join(words)) for words in BODIES)
    alone = {_fingerprint_of(words): _fingerprint_of(words) for words in BODIES}
    _write_store(root, [_document("recall", cards)], alone)


@pytest.fixture
def store(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    write_recall_store(root)
    return root


def test_counts_each_shape_by_hand_and_prints_counts_only(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    saved = tmp_path / "out" / "candidates.jsonl"
    assert (
        script.main(["--data-dir", str(store), "--caselist", CASELIST, "--save-candidates", str(saved)]) == 0
    )
    output = capsys.readouterr().out
    assert not [word for word in TELLTALE if word in output]
    counts = json.loads(output)["caselists"][CASELIST]
    del counts["seconds"]
    assert counts == {
        "version_directory": counts["version_directory"],
        "fingerprint_version": "card-fingerprint-v2",
        "cards": 10,
        "full_texts": 10,
        "neither_end": {
            "bodies": 1,
            "long": 1,
            "short": 0,
            "by_container_clusters": {"one": 1, "two or more": 0},
            "by_share_of_the_container": {
                "under a tenth": 0,
                "a tenth to a quarter": 0,
                "a quarter to a half": 1,
                "half or more": 0,
            },
            "container_holds_another_passage": 1,
        },
        "trims_sharing_nothing": {
            "pairs": 2,
            "holders": 2,
            "by_beside": {
                "a card of each carries the same tag and the same cite": 2,
                "the same cite, never with the same tag": 0,
                "the same tag, never with the same cite": 0,
                "neither the same tag nor the same cite": 0,
            },
            "by_holder_words_in_neither": {"0": 1, "1 to 9": 0, "10 to 49": 1, "50 or more": 0},
            "same_tag_and_cite_by_holder_words_in_neither": {
                "0": 1,
                "1 to 9": 0,
                "10 to 49": 1,
                "50 or more": 0,
            },
            "same_tag_and_cite_by_holder_words": {**BANDS, "0 to 299": 2},
            "by_trims_with_the_holder": {"0": 2, "1": 0, "2": 0},
        },
        "witness_refusal": {
            "holders": 3,
            "by_holder_words": {**BANDS, "0 to 299": 3},
            "sharing_nothing_by_holder_words": {**BANDS, "0 to 299": 3},
            "under_300_words_refused_for": 6,
            "bodies_kept_out_by_smallest_container_words": {**BANDS, "0 to 299": 4},
        },
    }
    assert counts["version_directory"].startswith("2026.")


def test_the_candidates_are_positions_alone(store: Path, tmp_path: Path) -> None:
    saved = tmp_path / "out" / "candidates.jsonl"
    assert (
        script.main(["--data-dir", str(store), "--caselist", CASELIST, "--save-candidates", str(saved)]) == 0
    )
    text = saved.read_text(encoding="utf-8")
    assert not [word for word in TELLTALE if word in text]
    rows = [json.loads(line) for line in text.splitlines()]
    (source,) = {row.get("holder", row.get("cut"))[0] for row in rows}

    def at(*indices: int) -> list[list[object]]:
        """The positions of `BODIES[index]` (element 10 for the first card, 20 for the second),
        in the order of their fingerprints, as pairs and holders are written."""
        ordered = sorted(indices, key=lambda index: _fingerprint_of(BODIES[index]))
        return [[source, 10 * (index + 1)] for index in ordered]

    same = "a card of each carries the same tag and the same cite"
    # Kessler's trims are with the card or its one-word copy, whichever sorts first: one size.
    (kessler_holder, _) = at(0, 1)
    expected = [
        {
            "caselist": CASELIST,
            "shape": "neither-end",
            "group": "long",
            "cut": at(8)[0],
            "container": at(7)[0],
        },
        {
            "caselist": CASELIST,
            "shape": "trims",
            "group": same,
            "words_in_neither": "10 to 49",
            "holder": kessler_holder,
            "pieces": at(2, 3),
        },
        {
            "caselist": CASELIST,
            "shape": "trims",
            "group": same,
            "words_in_neither": "0",
            "holder": at(4)[0],
            "pieces": at(5, 6),
        },
        *(
            {
                "caselist": CASELIST,
                "shape": "refusing-holder",
                "group": "0 to 299",
                "sharing_nothing": True,
                "holder": holder,
            }
            for holder in at(0, 1, 4)
        ),
    ]
    assert sorted(map(json.dumps, rows)) == sorted(json.dumps(row, sort_keys=True) for row in expected)


def test_the_candidates_file_is_refused_inside_the_repository_or_the_data_directory(store: Path) -> None:
    inside = Path(script.__file__).resolve().parent / "candidates.jsonl"
    with pytest.raises(SystemExit, match="outside the repository"):
        script.main(["--data-dir", str(store), "--caselist", CASELIST, "--save-candidates", str(inside)])
    with pytest.raises(SystemExit, match="outside the data directory"):
        script.main(
            ["--data-dir", str(store), "--caselist", CASELIST, "--save-candidates", str(store / "c.jsonl")]
        )
    assert not inside.exists()
