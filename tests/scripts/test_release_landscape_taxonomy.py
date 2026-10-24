"""`scripts/release_landscape_taxonomy.py` on a synthetic configuration (`v1-e32-t08` ac3).

The writer adds one topic's merged taxonomy to `released.yaml` at the version given, from the
committed files alone. Each expected lock below was written by hand from the fixture (working
agreement 6): the topic's own positions in file order, then generic.yaml's for its event. Each
refusal leaves the lock byte-for-byte as it was.

Every topic, id and label here is invented.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import release_landscape_taxonomy as script  # noqa: E402

TOPIC = "policy-sample-topic"

TOPICS = f"""\
schema_version: 1
topics:
  - id: {TOPIC}
    event: POLICY
    taxonomy_version: {{version}}
    caselists:
      - {{{{caselist: hspolicy99, from: 2026-09-01, to: 2027-06-30}}}}
"""

TAXONOMY = f"""\
schema_version: 1
topic_id: {TOPIC}
taxonomy_version: {{version}}
event: POLICY
positions:
  - {{{{id: spending-da, label: Spending DA, kind: da, side: neg, aliases: [spending da]}}}}
  - {{{{id: states-cp, label: States CP, kind: cp, side: neg, aliases: [states cp]}}}}
"""

GENERIC = """\
schema_version: 1
topic_id: generic
taxonomy_version: 1.0.0
event: null
positions:
  - {id: condo-bad, label: Condo bad, kind: theory, side: both, events: [POLICY], aliases: [condo bad]}
  - {id: sample-value, label: Sample value, kind: value, side: both, events: [LD], aliases: [sample value]}
"""

HEADER = """\
# The position ids published landscape reports have released, per topic and taxonomy version: each
# id with its kind and side, the topic's own positions and generic.yaml's for its event. Written by
# scripts/release_landscape_taxonomy.py when a report under a new version is first published; never
# edited by hand. tests/config/test_landscape_released_ids.py refuses a taxonomy that deletes one of
# these ids, changes its kind or side, or changes a released version's positions without a bump.
# docs/guides/landscape-taxonomy.md says when the operator writes it.
"""

EMPTY_LOCK = HEADER + "schema_version: 1\nreleases: []\n"

RELEASE_1_0_0 = f"""\
  - topic_id: {TOPIC}
    taxonomy_version: 1.0.0
    positions:
      - {{id: spending-da, kind: da, side: neg}}
      - {{id: states-cp, kind: cp, side: neg}}
      - {{id: condo-bad, kind: theory, side: both}}
"""

RELEASE_1_1_0 = f"""\
  - topic_id: {TOPIC}
    taxonomy_version: 1.1.0
    positions:
      - {{id: spending-da, kind: da, side: neg}}
      - {{id: states-cp, kind: cp, side: neg}}
      - {{id: medicaid-da, kind: da, side: neg}}
      - {{id: condo-bad, kind: theory, side: both}}
"""

MEDICAID_DA = "  - {id: medicaid-da, label: Medicaid DA, kind: da, side: neg, aliases: [medicaid da]}\n"


def write_config(root: Path, version: str, *, extra: str = "", lock: str = EMPTY_LOCK) -> Path:
    (root / "taxonomies").mkdir(parents=True, exist_ok=True)
    (root / "topics.yaml").write_text(TOPICS.format(version=version), encoding="utf-8")
    (root / "taxonomies" / f"{TOPIC}.yaml").write_text(
        TAXONOMY.format(version=version) + extra, encoding="utf-8"
    )
    (root / "taxonomies" / "generic.yaml").write_text(GENERIC, encoding="utf-8")
    (root / "released.yaml").write_text(lock, encoding="utf-8")
    return root


def run(root: Path, version: str, topic: str = TOPIC) -> int:
    return script.main(["--config-dir", str(root), "--topic", topic, "--version", version])


def test_it_writes_the_first_release(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = write_config(tmp_path, "1.0.0")
    assert run(root, "1.0.0") == 0
    assert (root / "released.yaml").read_text(encoding="utf-8") == (
        HEADER + "schema_version: 1\nreleases:\n" + RELEASE_1_0_0
    )
    assert (
        f"Released {TOPIC} 1.0.0: 3 position ids written to {root / 'released.yaml'}."
        in capsys.readouterr().out
    )


def test_a_later_version_is_added_after_the_first(tmp_path: Path) -> None:
    root = write_config(tmp_path, "1.0.0")
    assert run(root, "1.0.0") == 0
    write_config(root, "1.1.0", extra=MEDICAID_DA, lock=(root / "released.yaml").read_text(encoding="utf-8"))
    assert run(root, "1.1.0") == 0
    assert (root / "released.yaml").read_text(encoding="utf-8") == (
        HEADER + "schema_version: 1\nreleases:\n" + RELEASE_1_0_0 + RELEASE_1_1_0
    )


def refused(root: Path, version: str, capsys: pytest.CaptureFixture[str], topic: str = TOPIC) -> str:
    before = (root / "released.yaml").read_bytes()
    assert run(root, version, topic) == 2
    assert (root / "released.yaml").read_bytes() == before
    return capsys.readouterr().err


def test_a_version_the_file_is_not_at_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = write_config(tmp_path, "1.1.0", extra=MEDICAID_DA)
    assert f"{TOPIC} is at 1.1.0, not 1.0.0" in refused(root, "1.0.0", capsys)


def test_a_version_already_released_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = write_config(tmp_path, "1.0.0", lock=HEADER + "schema_version: 1\nreleases:\n" + RELEASE_1_0_0)
    assert f"{TOPIC} 1.0.0 is already released" in refused(root, "1.0.0", capsys)


def test_a_configuration_that_breaks_a_released_id_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lock = HEADER + "schema_version: 1\nreleases:\n" + RELEASE_1_0_0
    root = write_config(tmp_path, "1.1.0", lock=lock)
    taxonomy = root / "taxonomies" / f"{TOPIC}.yaml"
    taxonomy.write_text(
        "".join(
            line
            for line in taxonomy.read_text(encoding="utf-8").splitlines(keepends=True)
            if "states-cp" not in line
        ),
        encoding="utf-8",
    )
    error = refused(root, "1.1.0", capsys)
    assert "states-cp was released in" in error
    assert "Rule (released-id-missing)" in error


def test_a_topic_with_no_taxonomy_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = write_config(tmp_path, "1.0.0")
    assert "another-topic" in refused(root, "1.0.0", capsys, topic="another-topic")
