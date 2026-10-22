"""The one rule for an occurrence table a newer build stamped (`v1-e34-t29`).

:func:`~debate_core.application.caselist.occurrence_table_guard.refuse_newer_table` and the order
it judges by, on synthetic versions (PM notes, 2026-10-20): the real ones change with every bump,
and a test that named `card-fingerprint-v5` as "newer" would turn into one about an equal stamp the
day v5 ships. One test reads the real versions, to hold the order to the real list.

The paths that ask this rule, and the tests that fail if one of them bypasses it, are in
`test_caselist_parse_newer_fingerprint_table.py`, `test_pull_refuses_a_newer_fingerprint_table.py`,
`test_store_sync_newer_fingerprint_table.py` and the CLI's `test_caselist_parse_newer_fingerprint_table.py`.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Final

import pytest

from debate_core.application.caselist import occurrence_table_guard
from debate_core.application.caselist.occurrence_table_guard import (
    NewerFingerprintTable,
    fingerprint_stamps,
    is_newer_fingerprint_version,
    newer_stamp,
    occurrence_table_of,
    refuse_newer_table,
)
from debate_core.evidence.fingerprints import EXACT_FINGERPRINT_VERSIONS, FINGERPRINT_VERSION

BUILD: Final = "synthetic-fingerprint-v7"
NEWER: Final = "synthetic-fingerprint-v8"
OLDER: Final = "synthetic-fingerprint-v6"

SOURCE_ROOTS: Final = tuple(
    Path(__file__).resolve().parents[4] / package / "src" for package in ("debate_core", "debate_cli")
)


@pytest.fixture(autouse=True)
def synthetic_build(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(occurrence_table_guard, "FINGERPRINT_VERSION", BUILD)


# ------------------------------------------------------------------------------------------------
# The order
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stamped", "newer"),
    [
        (NEWER, True),
        ("synthetic-fingerprint-v10", True),
        (BUILD, False),
        (OLDER, False),
        ("synthetic-fingerprint-v1", False),
    ],
)
def test_a_stamp_is_newer_only_when_its_version_number_is_higher(stamped: str, newer: bool) -> None:
    """By number, not by string: `v10` sorts before `v7` as text and is three versions later."""
    assert is_newer_fingerprint_version(stamped, BUILD) is newer


@pytest.mark.parametrize(
    "stamped", ["other-fingerprint-v6", "synthetic-fingerprint", "synthetic-fingerprint-v07"]
)
def test_a_stamp_that_cannot_be_ordered_against_this_build_counts_as_newer(stamped: str) -> None:
    """Another family, no number, a number written another way: this build cannot vouch it is older."""
    assert is_newer_fingerprint_version(stamped, BUILD)


def test_every_version_the_real_list_names_orders_at_or_below_the_real_build() -> None:
    """The one test on real versions: the order agrees with `EXACT_FINGERPRINT_VERSIONS`.

    The list holds the build's own version and every one whose exact fingerprints are still today's,
    and none of them may count as newer, or a table this build wrote would be refused.
    """
    assert FINGERPRINT_VERSION in EXACT_FINGERPRINT_VERSIONS
    assert [
        is_newer_fingerprint_version(version, FINGERPRINT_VERSION) for version in EXACT_FINGERPRINT_VERSIONS
    ] == [False] * len(EXACT_FINGERPRINT_VERSIONS)


def test_the_newest_of_several_newer_stamps_is_the_one_named() -> None:
    assert newer_stamp([OLDER, BUILD, NEWER, "synthetic-fingerprint-v12", "synthetic-fingerprint-v9"]) == (
        "synthetic-fingerprint-v12"
    )
    assert newer_stamp([OLDER, BUILD]) is None
    assert newer_stamp([]) is None


# ------------------------------------------------------------------------------------------------
# The refusal
# ------------------------------------------------------------------------------------------------


def test_a_newer_stamp_is_refused_naming_both_versions_the_store_and_the_table() -> None:
    with pytest.raises(NewerFingerprintTable) as refused:
        refuse_newer_table(
            [BUILD, NEWER], caselist="testcl26", version="2099.01.01-docx-9", store="the bucket"
        )

    assert str(refused.value) == (
        f"the occurrence table of testcl26 2099.01.01-docx-9 in the bucket is stamped {NEWER}, newer "
        f"than this build's {BUILD}; it was left as it was"
    )
    assert refused.value.fix == (
        f"The occurrence table of testcl26 2099.01.01-docx-9 in the bucket is stamped {NEWER}, and this "
        f"build's fingerprint version is {BUILD}. Rebuild and publish it with a build at {NEWER} or later, "
        "and install that build for the weekly agent."
    )
    assert (refused.value.stamped, refused.value.build) == (NEWER, BUILD)


@pytest.mark.parametrize("stamps", [[BUILD], [OLDER], [OLDER, BUILD], []])
def test_an_equal_or_older_stamp_or_an_empty_table_passes(stamps: list[str]) -> None:
    refuse_newer_table(stamps, caselist="testcl26", version="2099.01.01-docx-9", store="the bucket")


# ------------------------------------------------------------------------------------------------
# Reading a table's stamps
# ------------------------------------------------------------------------------------------------


def test_stamps_are_read_from_each_rows_json_and_not_through_this_builds_model() -> None:
    """A newer build may add a field this build's model forbids: its stamp is still read."""
    lines = [
        json.dumps({"record": "occurrence", "fingerprint_version": NEWER, "a_field_from_later": 1}) + "\n",
        json.dumps({"record": "occurrence", "fingerprint_version": BUILD}) + "\n",
    ]
    assert fingerprint_stamps(lines) == {NEWER, BUILD}


def test_a_line_with_no_readable_stamp_says_nothing_and_is_passed_over() -> None:
    lines = ["not json\n", "[1, 2]\n", '{"fingerprint_version": 8}\n', '{"fingerprint_version": ""}\n', "\n"]
    assert fingerprint_stamps([*lines, json.dumps({"fingerprint_version": OLDER})]) == {OLDER}


@pytest.mark.parametrize(
    ("key", "table"),
    [
        ("parsed/testcl26/2099.01.01-docx-9/occurrences.jsonl", ("testcl26", "2099.01.01-docx-9")),
        ("parsed/testcl26/2099.01.01-docx-9/index.jsonl", None),
        ("parsed/testcl26/2099.01.01-docx-9/sha256/ab/cd/occurrences.jsonl", None),
        ("manifests/testcl26/occurrences.jsonl", None),
        ("testcl26/2099.01.01-docx-9/occurrences.jsonl", None),
    ],
)
def test_an_occurrence_table_is_named_by_its_bucket_key(key: str, table: tuple[str, str] | None) -> None:
    assert occurrence_table_of(key) == table


# ------------------------------------------------------------------------------------------------
# Every path that writes a table is one that asks the rule
# ------------------------------------------------------------------------------------------------


def calls_in_source(attribute: str) -> set[str]:
    """Each source module that calls a method or function named `attribute`, by its path."""
    found: set[str] = set()
    for root in SOURCE_ROOTS:
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                called = node.func
                name = called.attr if isinstance(called, ast.Attribute) else getattr(called, "id", None)
                if name == attribute:
                    found.add(path.relative_to(root).as_posix())
    return found


def test_the_only_rebuild_of_an_occurrence_table_is_the_parse_pipelines_and_it_asks_the_rule() -> None:
    """A new caller of `write_aggregates` fails this until it is added here with its own refusal test."""
    assert calls_in_source("write_aggregates") == {"debate_core/application/caselist_parse.py"}


def test_every_path_that_moves_an_occurrence_table_asks_the_one_rule() -> None:
    """The parse pipeline, the parsed store's publisher and `store sync`, and no rule of their own.

    Each of their tests that patches the rule's comparison shows the path takes the rule's answer:
    `test_*_takes_the_rules_answer*` in the test files this module's docstring names.
    """
    assert calls_in_source("refuse_newer_table") == {
        "debate_core/application/caselist_parse.py",
        "debate_core/application/caselist/parsed_publish.py",
        "debate_core/application/evidence_sync.py",
    }
    assert calls_in_source("is_newer_fingerprint_version") == {
        "debate_core/application/caselist/occurrence_table_guard.py"
    }
