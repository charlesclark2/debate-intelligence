"""The K-aff position and its K families, read and checked with the taxonomies (`v1-e32-t17`).

`config/landscape/kritikal_affs/<topic id>.yaml` names the topic's generic K-aff position and the K
families the report's K-aff group counts in headings (the PM's ruling 1 of 2026-10-25): config, beside
t09's and t11's files, never in Python. The repository reads each with the rest of the configuration and
refuses a file named for another topic, one for a topic with no taxonomy, a position that is not an
active aff, a family listed twice, a phrase in two families or not in lowercase words, and a `.yml` file
it would otherwise skip. A topic with no file reads no K aff.

Every topic, caselist slug and phrase here is invented.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from debate_core.application.ports.taxonomy_repository import NoTaxonomyForTopic, TaxonomyConfigError
from debate_core.arguments.landscape.kritikal_aff import KritikalAffConfig, KritikalFamily
from debate_core.integrations.landscape.yaml_taxonomy_repository import (
    KRITIKAL_AFF_DIRECTORY,
    YamlTaxonomyRepository,
)

TOPICS = """\
schema_version: 1
topics:
  - id: policy-sample-topic
    event: POLICY
    taxonomy_version: 1.0.0
    caselists:
      - {caselist: hspolicy99, from: 2026-07-01, to: 2027-06-30}
  - id: ld-sample-early
    event: LD
    caselists:
      - {caselist: hsld99, from: 2026-09-01, to: 2026-10-31}
"""

TAXONOMY = """\
schema_version: 1
topic_id: policy-sample-topic
taxonomy_version: 1.0.0
event: POLICY
positions:
  - {id: sample-plan-aff, label: Sample plan, kind: aff, side: aff, aliases: [sample plan]}
  - {id: sample-kritikal-aff, label: Sample kritikal aff, kind: aff, side: aff}
  - {id: retired-kritikal-aff, label: Retired kritikal aff, kind: aff, side: aff, deprecated: true}
  - {id: sample-cap-k, label: Sample cap K, kind: k, side: neg, aliases: [sample cap k]}
"""

KRITIKAL = """\
schema_version: 1
topic_id: policy-sample-topic
position_id: sample-kritikal-aff
families:
  - {id: cap, label: Capitalism, phrases: [cap, capitalism]}
  - {id: set-col, label: Settler colonialism, phrases: [set col]}
"""


def config(tmp_path: Path, files: dict[str, str] | None = None) -> Path:
    (tmp_path / "taxonomies").mkdir(parents=True)
    (tmp_path / "topics.yaml").write_text(TOPICS, encoding="utf-8")
    (tmp_path / "taxonomies" / "policy-sample-topic.yaml").write_text(TAXONOMY, encoding="utf-8")
    if files:
        (tmp_path / KRITIKAL_AFF_DIRECTORY).mkdir()
    for name, text in (files or {}).items():
        (tmp_path / KRITIKAL_AFF_DIRECTORY / name).write_text(text, encoding="utf-8")
    return tmp_path


def test_the_directory_is_kritikal_affs() -> None:
    assert KRITIKAL_AFF_DIRECTORY == "kritikal_affs"


def test_a_topic_with_no_file_reads_no_k_aff(tmp_path: Path) -> None:
    assert YamlTaxonomyRepository.load(config(tmp_path)).kritikal_aff("policy-sample-topic") is None


def test_the_file_loads_as_its_position_and_families(tmp_path: Path) -> None:
    repository = YamlTaxonomyRepository.load(config(tmp_path, {"policy-sample-topic.yaml": KRITIKAL}))
    assert repository.kritikal_aff("policy-sample-topic") == KritikalAffConfig(
        topic_id="policy-sample-topic",
        position_id="sample-kritikal-aff",
        families=(
            KritikalFamily(id="cap", label="Capitalism", phrases=("cap", "capitalism")),
            KritikalFamily(id="set-col", label="Settler colonialism", phrases=("set col",)),
        ),
    )


def test_a_topic_with_no_taxonomy_is_asked_for_in_vain(tmp_path: Path) -> None:
    repository = YamlTaxonomyRepository.load(config(tmp_path))
    with pytest.raises(NoTaxonomyForTopic):
        repository.kritikal_aff("ld-sample-early")


@pytest.mark.parametrize(
    ("case", "name", "text", "expected"),
    [
        (
            "a file named for another topic",
            "policy-other-topic.yaml",
            KRITIKAL,
            "named for policy-other-topic",
        ),
        (
            "a topic with no taxonomy",
            "ld-sample-early.yaml",
            KRITIKAL.replace("policy-sample-topic", "ld-sample-early"),
            "gives ld-sample-early a taxonomy",
        ),
        (
            "a position that is a K, not an aff",
            "policy-sample-topic.yaml",
            KRITIKAL.replace("sample-kritikal-aff", "sample-cap-k"),
            "no active aff",
        ),
        (
            "a retired aff",
            "policy-sample-topic.yaml",
            KRITIKAL.replace("sample-kritikal-aff", "retired-kritikal-aff"),
            "no active aff",
        ),
        (
            "a position the taxonomy does not have",
            "policy-sample-topic.yaml",
            KRITIKAL.replace("sample-kritikal-aff", "missing-kritikal-aff"),
            "no active aff",
        ),
        (
            "a family listed twice",
            "policy-sample-topic.yaml",
            KRITIKAL.replace("id: set-col", "id: cap"),
            "listed twice",
        ),
        (
            "a phrase in two families",
            "policy-sample-topic.yaml",
            KRITIKAL.replace("[set col]", "[set col, cap]"),
            "names two families",
        ),
        (
            "a phrase in capitals",
            "policy-sample-topic.yaml",
            KRITIKAL.replace("[set col]", "[Set Col]"),
            "phrases",
        ),
        ("an unknown key", "policy-sample-topic.yaml", KRITIKAL + "markers: [advocacy]\n", "markers"),
        ("a .yml file", "policy-sample-topic.yml", KRITIKAL, "ends in .yaml"),
    ],
    ids=lambda value: value if isinstance(value, str) and " " in value and "\n" not in value else "",
)
def test_a_bad_file_is_refused_naming_it(
    tmp_path: Path, case: str, name: str, text: str, expected: str
) -> None:
    del case
    with pytest.raises(TaxonomyConfigError, match=expected) as raised:
        YamlTaxonomyRepository.load(config(tmp_path, {name: text}))
    assert name in str(raised.value)
