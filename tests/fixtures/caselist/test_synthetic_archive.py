"""The end-to-end suite's synthetic archive and its landscape cassette stay what they say (`v1-e09-t05`).

`synthetic_archive/build_synthetic_archive.py` must build the same bytes every time, with the three
members and two distinct bodies its docstring promises; the committed cassette must be exactly what
`record_landscape_cassette.py` writes, and hold nothing the model scrubber would remove.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from io import BytesIO
from pathlib import Path

from tests.fixtures.caselist.synthetic_archive.build_synthetic_archive import (
    AFFIRMATIVE,
    CARDS,
    NEGATIVE,
    archive_bytes,
)
from tests.fixtures.caselist.synthetic_archive.record_landscape_cassette import CASSETTES, record

from debate_core.integrations.models.redaction import redactions


def test_the_archive_is_the_same_bytes_every_build_with_three_members_and_two_bodies() -> None:
    first, second = archive_bytes(), archive_bytes()

    assert first == second
    with zipfile.ZipFile(BytesIO(first)) as archive:
        bodies = [archive.read(name) for name in archive.namelist()]
    assert len(bodies) == 3
    assert {hashlib.sha256(body).hexdigest() for body in bodies} == {
        hashlib.sha256(AFFIRMATIVE).hexdigest(),
        hashlib.sha256(NEGATIVE).hexdigest(),
    }


def test_every_card_is_written_whole_and_no_two_alike() -> None:
    assert [card.number for card in CARDS] == [1, 2, 3, 4]
    assert len({card.evidence for card in CARDS}) == 4
    assert all(card.evidence == card.small + card.underlined + card.closing for card in CARDS)


def test_the_committed_landscape_cassette_is_what_the_recording_script_writes(tmp_path: Path) -> None:
    committed = {path.relative_to(CASSETTES): path.read_bytes() for path in CASSETTES.rglob("*.json")}

    fresh = tmp_path / "cassettes"
    written = {path.relative_to(fresh): path.read_bytes() for path in record(fresh)}

    assert committed == written, (
        "run: uv run python -m tests.fixtures.caselist.synthetic_archive.record_landscape_cassette"
    )
    assert len(committed) == 1


def test_the_landscape_cassette_holds_nothing_redaction_would_remove() -> None:
    for path in CASSETTES.rglob("*.json"):
        assert redactions(json.loads(path.read_text(encoding="utf-8"))) == [], path
