"""A published built file's `metadata.json` and its keys under `files/` (`v1-e33-t05`, metadata contract).

Every expected key, list and refusal here is written by hand (working agreement 6). Every school and
team code is invented.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Final

import jsonschema
import pytest
from pydantic import ValidationError

from debate_core.domain.built_file_metadata import (
    BuiltFileMetadata,
    PublishedSource,
    built_file_keys,
    built_file_prefix,
    published_sources,
    render_built_file_metadata_schema,
)
from debate_core.domain.caselist import Side
from debate_core.domain.file_provenance import FileProvenanceEntry

SCHEMA_PATH: Final = Path(__file__).resolve().parents[4] / "docs" / "data" / "built-file-metadata.schema.json"

RECIPE_HASH: Final = "0123456789ab" + "c" * 52
SOURCE_A: Final = "a" * 64
SOURCE_B: Final = "b" * 64
DOCX: Final = "d" * 64
PREFIX: Final = "files/nhi/aff/politics-da/politics-da-answers/0123456789ab/"


def test_the_prefix_is_topic_side_position_slug_and_twelve_characters_of_the_recipe_hash() -> None:
    prefix = built_file_prefix(
        topic="nhi",
        side=Side.AFF,
        position="politics-da",
        slug="politics-da-answers",
        recipe_hash=RECIPE_HASH,
    )
    assert prefix == PREFIX


def test_the_five_keys_are_under_the_prefix_in_publish_order_metadata_last() -> None:
    keys = built_file_keys(PREFIX, "politics-da-answers")
    assert keys.in_order == (
        f"{PREFIX}politics-da-answers.docx",
        f"{PREFIX}politics-da-answers.docx.provenance.json",
        f"{PREFIX}politics-da-answers.docx.quality.json",
        f"{PREFIX}recipe.yaml",
        f"{PREFIX}metadata.json",
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"topic": "NHI"},
        {"position": "politics da"},
        {"slug": "Politics DA answers"},
        {"slug": "../escape"},
        {"slug": "a" * 101},
        {"side": Side.UNKNOWN},
        {"recipe_hash": "C" * 64},
        {"recipe_hash": "c" * 12},
    ],
)
def test_a_part_that_would_not_make_a_key_is_refused(changes: dict[str, Any]) -> None:
    parts: dict[str, Any] = {
        "topic": "nhi",
        "side": Side.NEG,
        "position": "politics-da",
        "slug": "politics-da-answers",
        "recipe_hash": RECIPE_HASH,
    }
    with pytest.raises(ValueError):
        built_file_prefix(**{**parts, **changes})


def entry(position: int, caselist: str, snapshot: str, source: str, **changes: Any) -> FileProvenanceEntry:
    values: dict[str, Any] = {
        "position": position,
        "recipe_path": f"structure[0].blocks[0].items[{position - 1}]",
        "section_path": ("Pocket", "Block"),
        "fingerprint": "e" * 64,
        "fingerprint_version": "card-fingerprint-v3",
        "resolution": "AUTO",
        "caselist": caselist,
        "snapshot": snapshot,
        "last_snapshot": snapshot,
        "source_sha256": source,
        "first_element_index": 0,
        "last_element_index": 2,
        "completeness": "FULL",
        "evidence_sha256": "1" * 64,
        "cite_sha256": "2" * 64,
        "formatting_sha256": "3" * 64,
        "tag_overridden": False,
        "provenance_line": "[Disclosed: hspolicy26 2026-09-15]",
        "forbidden_characters_replaced": 0,
    }
    values.update(changes)
    return FileProvenanceEntry.model_validate(values)


def test_sources_are_each_caselist_snapshot_and_sha256_once_sorted_and_name_no_school_or_team() -> None:
    cards = [
        entry(1, "hspolicy26", "2026-09-22", SOURCE_B, school="Maple Grove", team_code="QX"),
        entry(2, "hspolicy26", "2026-09-15", SOURCE_A, school="Cedar Hollow", team_code="ZaLu"),
        entry(3, "hspolicy26", "2026-09-22", SOURCE_B, school="Maple Grove", team_code="QX"),
        entry(4, "openev", "2031-policy", SOURCE_A, camp="Cascade Institute", provenance_line="[OpenEv: x]"),
    ]
    assert published_sources(cards) == (
        PublishedSource(caselist="hspolicy26", snapshot="2026-09-15", source_sha256=SOURCE_A),
        PublishedSource(caselist="hspolicy26", snapshot="2026-09-22", source_sha256=SOURCE_B),
        PublishedSource(caselist="openev", snapshot="2031-policy", source_sha256=SOURCE_A),
    )
    shown = json.dumps([one.model_dump(mode="json") for one in published_sources(cards)])
    assert "Maple Grove" not in shown and "QX" not in shown and "ZaLu" not in shown


def metadata(**changes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "key_prefix": PREFIX,
        "slug": "politics-da-answers",
        "title": "Politics DA answers",
        "topic": "nhi",
        "format": "POLICY",
        "caselist": "hspolicy26",
        "position": "politics-da",
        "side": "AFF",
        "card_count": 3,
        "recipe_hash": RECIPE_HASH,
        "recipe_status": "ready",
        "builder_version": "2026.10.24-file-writer-4",
        "parser_version": "2026.10.18-docx-5",
        "style_profile_version": "2026.09.20-verbatim-1",
        "fingerprint_version": "card-fingerprint-v3",
        "checker_version": "2026.10.22-file-checks-2",
        "quality_status": "PASS",
        "quality_warnings": 1,
        "warned_checks": ["cite-present"],
        "built_at": datetime(2026, 10, 24, 12, 0, tzinfo=UTC),
        "docx_sha256": DOCX,
        "objects": [
            {"name": "politics-da-answers.docx", "bytes": 10, "sha256": DOCX},
            {"name": "politics-da-answers.docx.provenance.json", "bytes": 11, "sha256": "4" * 64},
            {"name": "politics-da-answers.docx.quality.json", "bytes": 12, "sha256": "5" * 64},
            {"name": "recipe.yaml", "bytes": 13, "sha256": "6" * 64},
        ],
        "sources": [
            {"caselist": "hspolicy26", "snapshot": "2026-09-15", "source_sha256": SOURCE_A},
            {"caselist": "hspolicy26", "snapshot": "2026-09-22", "source_sha256": SOURCE_B},
            {"caselist": "openev", "snapshot": "2031-policy", "source_sha256": SOURCE_A},
        ],
        "caselists": ["hspolicy26", "openev"],
        "source_sha256s": [SOURCE_A, SOURCE_B],
    }
    values.update(changes)
    return values


def test_well_formed_metadata_validates_and_its_json_meets_the_committed_schema() -> None:
    model = BuiltFileMetadata.model_validate(metadata())
    document = json.loads(model.to_json_bytes())
    jsonschema.validate(document, json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    assert document["built_at"] == "2026-10-24T12:00:00.000000Z"
    assert document["provenance_mode"] == "FILE_IMPORT"


def test_the_same_metadata_always_serializes_to_the_same_bytes_whatever_the_timezone_given() -> None:
    later_zone = datetime(2026, 10, 24, 14, 0, tzinfo=timezone(timedelta(hours=2)))
    one = BuiltFileMetadata.model_validate(metadata()).to_json_bytes()
    other = BuiltFileMetadata.model_validate(metadata(built_at=later_zone)).to_json_bytes()
    assert one == other
    assert one.endswith(b"}\n")


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"key_prefix": "files/nhi/neg/politics-da/politics-da-answers/0123456789ab/"}, "key_prefix"),
        ({"caselists": ["hspolicy26"]}, "caselists are the sources'"),
        ({"source_sha256s": [SOURCE_A]}, "source_sha256s are the sources'"),
        ({"source_sha256s": [SOURCE_B, SOURCE_A]}, "source_sha256s are the sources'"),
        (
            {
                "sources": [
                    {"caselist": "hspolicy26", "snapshot": "2026-09-22", "source_sha256": SOURCE_B},
                    {"caselist": "hspolicy26", "snapshot": "2026-09-15", "source_sha256": SOURCE_A},
                    {"caselist": "openev", "snapshot": "2031-policy", "source_sha256": SOURCE_A},
                ]
            },
            "sources are sorted",
        ),
        ({"docx_sha256": "7" * 64}, "the .docx object"),
        ({"objects": metadata()["objects"][::-1]}, "objects are"),
        ({"objects": metadata()["objects"][:3]}, "objects are"),
        ({"recipe_status": "draft"}, "recipe_status"),
        ({"quality_status": "FAIL"}, "quality_status"),
        ({"side": "UNKNOWN"}, "AFF, NEG, PRO or CON"),
        ({"school": "Maple Grove"}, "Extra inputs are not permitted"),
    ],
)
def test_metadata_that_says_what_it_must_not_is_refused(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        BuiltFileMetadata.model_validate(metadata(**changes))


def test_the_committed_schema_is_what_the_model_renders() -> None:
    assert SCHEMA_PATH.is_file(), "missing; run: uv run scripts/export_built_file_metadata_schema.py"
    assert json.loads(SCHEMA_PATH.read_text(encoding="utf-8")) == render_built_file_metadata_schema(), (
        "stale; run: uv run scripts/export_built_file_metadata_schema.py"
    )
