"""A released position id is never deleted or reused (`v1-e32-t08-released-position-ids`).

`config/landscape/released.yaml` records, per topic and released version, each position id with its
kind and side. This suite checks the committed taxonomy files against it on every pull request, and
shows on synthetic configurations that the check refuses, naming the file, the id and the rule:

* a released id missing from the current file, when it is not retired (ac1);
* a released id whose kind or side changed (ac1);
* a file at a released version whose positions differ from that version's lock (ac1), or whose
  version has gone below a released one;
* a `merged_into` naming a retired position (the PM's ruling of 2026-10-24);
* a taxonomy file whose version is not `topics.yaml`'s (ac1; `v1-e32-t01`'s rule, which the check
  loads the configuration through).

A retirement, a merge into an active id, a new id and a label change pass (ac2), and with an empty
lock, as on the day this landed, every edit passes. The check reads the committed files only: no
network, no git history. Every topic, id and label here is invented.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from debate_core.application.ports.taxonomy_repository import TaxonomyConfigError
from debate_core.integrations.landscape.released_ids import (
    RELEASED_FILE,
    load_release_lock,
    released_id_findings,
    render_release_lock,
)

CONFIG = Path(__file__).resolve().parents[2] / "config" / "landscape"
TOPIC = "policy-sample-topic"

POSITIONS: list[dict[str, Any]] = [
    {"id": "spending-da", "label": "Spending DA", "kind": "da", "side": "neg", "aliases": ["spending da"]},
    {"id": "states-cp", "label": "States CP", "kind": "cp", "side": "neg", "aliases": ["states cp"]},
    {"id": "sample-aff", "label": "Sample aff", "kind": "aff", "side": "aff", "aliases": ["sample aff"]},
]
GENERIC_POSITIONS: list[dict[str, Any]] = [
    {
        "id": "condo-bad",
        "label": "Condo bad",
        "kind": "theory",
        "side": "both",
        "events": ["POLICY"],
        "aliases": ["condo bad"],
    },
]

EMPTY_LOCK = "schema_version: 1\nreleases: []\n"
LOCK_AT_1_0_0 = f"""\
schema_version: 1
releases:
  - topic_id: {TOPIC}
    taxonomy_version: 1.0.0
    positions:
      - {{id: spending-da, kind: da, side: neg}}
      - {{id: states-cp, kind: cp, side: neg}}
      - {{id: sample-aff, kind: aff, side: aff}}
      - {{id: condo-bad, kind: theory, side: both}}
"""
LOCK_AT_1_1_0 = LOCK_AT_1_0_0.replace("taxonomy_version: 1.0.0", "taxonomy_version: 1.1.0")


def write_config(
    root: Path,
    *,
    version: str | None = "1.0.0",
    topics_version: str | None = None,
    positions: list[dict[str, Any]] | None = None,
    generic: list[dict[str, Any]] | None = None,
    generic_version: str = "1.0.0",
    lock: str | None = LOCK_AT_1_0_0,
) -> Path:
    """A `config/landscape/` with one Policy topic at `version` (None: no taxonomy) and generic.yaml."""
    topic: dict[str, Any] = {
        "id": TOPIC,
        "event": "POLICY",
        "caselists": [{"caselist": "hspolicy99", "from": "2026-09-01", "to": "2027-06-30"}],
    }
    if version is not None:
        topic["taxonomy_version"] = topics_version or version
    (root / "taxonomies").mkdir(parents=True)
    (root / "topics.yaml").write_text(
        yaml.safe_dump({"schema_version": 1, "topics": [topic]}), encoding="utf-8"
    )
    if version is not None:
        own = {
            "topic_id": TOPIC,
            "taxonomy_version": version,
            "event": "POLICY",
            "positions": positions or POSITIONS,
        }
        (root / "taxonomies" / f"{TOPIC}.yaml").write_text(
            yaml.safe_dump(own, sort_keys=False), encoding="utf-8"
        )
    shared = {
        "topic_id": "generic",
        "taxonomy_version": generic_version,
        "event": None,
        "positions": GENERIC_POSITIONS if generic is None else generic,
    }
    (root / "taxonomies" / "generic.yaml").write_text(
        yaml.safe_dump(shared, sort_keys=False), encoding="utf-8"
    )
    if lock is not None:
        (root / RELEASED_FILE).write_text(lock, encoding="utf-8")
    return root


def edited(position_id: str, **fields: Any) -> list[dict[str, Any]]:
    """POSITIONS with one position's fields changed."""
    return [{**one, **fields} if one["id"] == position_id else dict(one) for one in POSITIONS]


def without(position_id: str) -> list[dict[str, Any]]:
    return [dict(one) for one in POSITIONS if one["id"] != position_id]


def topic_file(root: Path) -> str:
    return str(root / "taxonomies" / f"{TOPIC}.yaml")


def generic_file(root: Path) -> str:
    return str(root / "taxonomies" / "generic.yaml")


# ------------------------------------------------------------------------------------------------
# The committed files
# ------------------------------------------------------------------------------------------------


def test_the_committed_taxonomies_keep_every_released_id() -> None:
    assert released_id_findings(CONFIG) == []


def test_the_committed_lock_is_in_the_form_the_writer_writes() -> None:
    path = CONFIG / RELEASED_FILE
    assert render_release_lock(load_release_lock(path)) == path.read_text(encoding="utf-8")


# ------------------------------------------------------------------------------------------------
# The check refuses (synthetic)
# ------------------------------------------------------------------------------------------------


def only_finding(root: Path) -> str:
    findings = released_id_findings(root)
    assert len(findings) == 1, findings
    return findings[0]


def test_a_released_id_deleted_is_refused(tmp_path: Path) -> None:
    root = write_config(tmp_path, version="1.1.0", positions=without("states-cp"))
    finding = only_finding(root)
    assert finding.startswith(
        f"{topic_file(root)} (with generic.yaml merged in): "
        f"states-cp was released in {TOPIC} 1.0.0 and is missing"
    )
    assert "Rule (released-id-missing)" in finding


def test_a_released_generic_id_deleted_is_refused_naming_both_files(tmp_path: Path) -> None:
    root = write_config(tmp_path, version="1.1.0", generic=[], generic_version="1.1.0")
    finding = only_finding(root)
    assert finding.startswith(f"{topic_file(root)} (with generic.yaml merged in): condo-bad was released in")
    assert "Rule (released-id-missing)" in finding


def test_a_released_topic_left_without_a_taxonomy_is_refused(tmp_path: Path) -> None:
    root = write_config(tmp_path, version=None)
    finding = only_finding(root)
    assert finding.startswith(f"{topic_file(root)}: {TOPIC} was released in 1.0.0 and has no taxonomy now")
    assert "Rule (released-id-missing)" in finding


@pytest.mark.parametrize(
    ("position_id", "fields", "was", "now"),
    [
        ("states-cp", {"kind": "da"}, "kind cp, side neg", "kind da, side neg"),
        ("sample-aff", {"side": "both"}, "kind aff, side aff", "kind aff, side both"),
    ],
    ids=["kind", "side"],
)
def test_a_released_id_whose_kind_or_side_changed_is_refused(
    tmp_path: Path, position_id: str, fields: dict[str, Any], was: str, now: str
) -> None:
    root = write_config(tmp_path, version="1.1.0", positions=edited(position_id, **fields))
    finding = only_finding(root)
    assert finding.startswith(
        f"{topic_file(root)}: {position_id} was released in {TOPIC} 1.0.0 as {was} and is now {now}"
    )
    assert "Rule (kind-or-side-changed)" in finding


def test_a_released_generic_id_whose_side_changed_is_refused_naming_generic_yaml(tmp_path: Path) -> None:
    generic = [{**GENERIC_POSITIONS[0], "side": "neg"}]
    root = write_config(tmp_path, version="1.1.0", generic=generic, generic_version="1.1.0")
    finding = only_finding(root)
    assert finding.startswith(
        f"{generic_file(root)}: condo-bad was released in {TOPIC} 1.0.0 as kind theory, side both"
    )
    assert "Rule (kind-or-side-changed)" in finding


def test_a_position_added_at_a_released_version_is_refused(tmp_path: Path) -> None:
    added = {
        "id": "medicaid-da",
        "label": "Medicaid DA",
        "kind": "da",
        "side": "neg",
        "aliases": ["medicaid da"],
    }
    root = write_config(tmp_path, positions=[*POSITIONS, added])
    finding = only_finding(root)
    assert finding.startswith(f"{topic_file(root)}: medicaid-da is not in the lock of {TOPIC} 1.0.0")
    assert "Rule (changed-without-bump)" in finding


def test_a_kind_changed_at_a_released_version_is_refused_by_both_rules(tmp_path: Path) -> None:
    root = write_config(tmp_path, positions=edited("states-cp", kind="da"))
    findings = released_id_findings(root)
    assert [finding.split(". Rule (")[1].split(")")[0] for finding in findings] == [
        "kind-or-side-changed",
        "changed-without-bump",
    ]
    assert all(finding.startswith(f"{topic_file(root)}: states-cp ") for finding in findings)


def test_a_version_below_a_released_one_is_refused(tmp_path: Path) -> None:
    root = write_config(tmp_path, lock=LOCK_AT_1_1_0)
    finding = only_finding(root)
    assert finding.startswith(f"{topic_file(root)}: is at 1.0.0, below {TOPIC}'s released 1.1.0")
    assert "Rule (version-below-released)" in finding


def test_a_merge_into_a_retired_position_is_refused(tmp_path: Path) -> None:
    positions = [
        {**POSITIONS[0], "deprecated": True},
        {**POSITIONS[1], "deprecated": True, "merged_into": "spending-da"},
        POSITIONS[2],
    ]
    root = write_config(tmp_path, version="1.1.0", positions=positions)
    finding = only_finding(root)
    assert finding.startswith(f"{topic_file(root)}: states-cp is merged into spending-da, which is retired")
    assert "Rule (merged-into-retired)" in finding


def test_a_merge_into_a_retired_position_is_refused_before_anything_is_released(tmp_path: Path) -> None:
    generic = [
        {**GENERIC_POSITIONS[0], "deprecated": True},
        {
            **GENERIC_POSITIONS[0],
            "id": "condo-good",
            "aliases": [],
            "deprecated": True,
            "merged_into": "condo-bad",
        },
    ]
    root = write_config(tmp_path, generic=generic, lock=EMPTY_LOCK)
    finding = only_finding(root)
    assert finding.startswith(f"{generic_file(root)}: condo-good is merged into condo-bad, which is retired")


def test_a_taxonomy_version_unequal_to_topics_yaml_is_refused_naming_the_file(tmp_path: Path) -> None:
    root = write_config(tmp_path, version="1.1.0", topics_version="1.0.0")
    with pytest.raises(TaxonomyConfigError) as refused:
        released_id_findings(root)
    assert refused.value.path == topic_file(root)
    assert "is version 1.1.0, but topics.yaml names 1.0.0" in str(refused.value)


def test_a_missing_lock_file_is_refused_not_read_as_empty(tmp_path: Path) -> None:
    root = write_config(tmp_path, lock=None)
    with pytest.raises(TaxonomyConfigError) as refused:
        released_id_findings(root)
    assert refused.value.path == str(root / RELEASED_FILE)


# ------------------------------------------------------------------------------------------------
# What passes (ac2)
# ------------------------------------------------------------------------------------------------


def test_with_an_empty_lock_every_edit_passes(tmp_path: Path) -> None:
    positions = [{**POSITIONS[0], "kind": "cp"}, POSITIONS[2]]
    root = write_config(tmp_path, positions=positions, generic=[], lock=EMPTY_LOCK)
    assert released_id_findings(root) == []


def test_an_unchanged_released_version_passes(tmp_path: Path) -> None:
    assert released_id_findings(write_config(tmp_path)) == []


@pytest.mark.parametrize(
    "positions",
    [
        pytest.param(edited("states-cp", deprecated=True), id="retired"),
        pytest.param(
            edited("states-cp", deprecated=True, merged_into="spending-da"), id="merged-into-an-active-id"
        ),
        pytest.param(
            [*POSITIONS, {"id": "medicaid-da", "label": "Medicaid DA", "kind": "da", "side": "neg"}],
            id="new-id",
        ),
        pytest.param(
            [
                *edited("states-cp", deprecated=True, merged_into="state-action-cp", aliases=[]),
                {
                    "id": "state-action-cp",
                    "label": "State action CP",
                    "kind": "cp",
                    "side": "neg",
                    "aliases": ["states cp"],
                },
            ],
            id="renamed-to-a-new-id",
        ),
    ],
)
def test_a_retirement_a_merge_and_a_new_id_pass_with_the_version_bumped(
    tmp_path: Path, positions: list[dict[str, Any]]
) -> None:
    assert released_id_findings(write_config(tmp_path, version="1.1.0", positions=positions)) == []


def test_a_label_change_passes_even_at_the_released_version(tmp_path: Path) -> None:
    root = write_config(tmp_path, positions=edited("states-cp", label="Fifty states CP"))
    assert released_id_findings(root) == []
