"""The resolutional plan's word sets, read and checked with the taxonomies (`v1-e32-t09` ac3).

`config/landscape/plan_texts/<topic id>.yaml` says when a plan text that names no aff names the
topic's resolutional aff (the PM's context for ac3, 2026-10-24): the frame words and the
resolutional words, as config and never in Python. The repository reads each with the rest of the
configuration and refuses a file named for another topic, one for a topic with no taxonomy, one
naming no active aff of the topic, a word that is not one lowercase word, and a `.yml` file it would
otherwise skip. A topic with no file has no resolutional plan.

Every topic, caselist slug, word and position here is invented.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from debate_core.application.ports.taxonomy_repository import NoTaxonomyForTopic, TaxonomyConfigError
from debate_core.arguments.landscape.plan_text import ResolutionalPlanWords
from debate_core.integrations.landscape.yaml_taxonomy_repository import (
    PLAN_TEXT_DIRECTORY,
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
  - {id: national-plan-aff, label: National plan, kind: aff, side: aff}
  - {id: old-plan-aff, label: Old plan, kind: aff, side: aff, deprecated: true}
  - {id: spending-da, label: Spending DA, kind: da, side: neg, aliases: [spending da]}
"""

WORDS = """\
schema_version: 1
topic_id: policy-sample-topic
position_id: national-plan-aff
frame_words: [establish, federal, government, should, states, united]
resolutional_words: [national, program]
"""


def config(tmp_path: Path, files: dict[str, str] | None = None) -> Path:
    (tmp_path / "taxonomies").mkdir(parents=True)
    (tmp_path / "topics.yaml").write_text(TOPICS, encoding="utf-8")
    (tmp_path / "taxonomies" / "policy-sample-topic.yaml").write_text(TAXONOMY, encoding="utf-8")
    if files:
        (tmp_path / PLAN_TEXT_DIRECTORY).mkdir()
    for name, text in (files or {}).items():
        (tmp_path / PLAN_TEXT_DIRECTORY / name).write_text(text, encoding="utf-8")
    return tmp_path


def test_the_directory_is_plan_texts() -> None:
    assert PLAN_TEXT_DIRECTORY == "plan_texts"


def test_a_topic_with_no_file_has_no_resolutional_plan(tmp_path: Path) -> None:
    assert (
        YamlTaxonomyRepository.load(config(tmp_path)).resolutional_plan_words("policy-sample-topic") is None
    )


def test_the_file_loads_as_its_word_sets(tmp_path: Path) -> None:
    repository = YamlTaxonomyRepository.load(config(tmp_path, {"policy-sample-topic.yaml": WORDS}))
    assert repository.resolutional_plan_words("policy-sample-topic") == ResolutionalPlanWords(
        topic_id="policy-sample-topic",
        position_id="national-plan-aff",
        frame_words=("establish", "federal", "government", "should", "states", "united"),
        resolutional_words=("national", "program"),
    )


def test_a_topic_with_no_taxonomy_is_asked_for_in_vain(tmp_path: Path) -> None:
    repository = YamlTaxonomyRepository.load(config(tmp_path))
    with pytest.raises(NoTaxonomyForTopic):
        repository.resolutional_plan_words("ld-sample-early")


@pytest.mark.parametrize(
    ("case", "name", "text", "expected"),
    [
        ("a file named for another topic", "policy-other-topic.yaml", WORDS, "named for policy-other-topic"),
        (
            "a topic with no taxonomy",
            "ld-sample-early.yaml",
            WORDS.replace("policy-sample-topic", "ld-sample-early"),
            "gives ld-sample-early a taxonomy",
        ),
        (
            "an aff the taxonomy does not have",
            "policy-sample-topic.yaml",
            WORDS.replace("national-plan-aff", "absent-plan-aff"),
            "absent-plan-aff, which is no active aff",
        ),
        (
            "a retired aff",
            "policy-sample-topic.yaml",
            WORDS.replace("national-plan-aff", "old-plan-aff"),
            "old-plan-aff, which is no active aff",
        ),
        (
            "a position that is not an aff",
            "policy-sample-topic.yaml",
            WORDS.replace("national-plan-aff", "spending-da"),
            "spending-da, which is no active aff",
        ),
        (
            "a word in capitals",
            "policy-sample-topic.yaml",
            WORDS.replace("[national, program]", "[National, program]"),
            "resolutional_words",
        ),
        (
            "two words as one",
            "policy-sample-topic.yaml",
            WORDS.replace("[national, program]", "[national program]"),
            "resolutional_words",
        ),
        ("an unknown key", "policy-sample-topic.yaml", WORDS + "words: [care]\n", "words"),
        ("a .yml file", "policy-sample-topic.yml", WORDS, "ends in .yaml"),
    ],
    ids=lambda value: value if isinstance(value, str) and " " in value and "\n" not in value else "",
)
def test_a_bad_file_is_refused_naming_it(
    tmp_path: Path, case: str, name: str, text: str, expected: str
) -> None:
    directory = config(tmp_path, {name: text})
    with pytest.raises(TaxonomyConfigError, match=expected) as refused:
        YamlTaxonomyRepository.load(directory)
    assert refused.value.path.endswith(name), case
