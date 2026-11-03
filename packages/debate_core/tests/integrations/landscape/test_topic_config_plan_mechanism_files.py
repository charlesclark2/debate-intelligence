"""The coach's plan-mechanism words, read and checked with the taxonomies (`v1-e33-t14`).

`config/landscape/plan_mechanisms/<topic id>.yaml` lists the words a counterplan's draft marks a block by
when its heading holds one (`files suggest`). The repository reads each with the rest of the
configuration and refuses a file named for another topic, one for a topic with no taxonomy, a word that is
not lowercase letters and single hyphens, a word under 3 or over 32 characters, a word listed twice, an
unknown key and a `.yml` file it would otherwise skip. A topic with no file has no words and is not
refused: its drafts are marked as they were before the list.

The file name holds `topic_config` so the task's acceptance command (`-k "suggest or topic_config"`)
selects it. Every topic, caselist slug and word here is invented.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from debate_core.application.plan_mechanism_words import PlanMechanismWords
from debate_core.application.ports.taxonomy_repository import NoTaxonomyForTopic, TaxonomyConfigError
from debate_core.integrations.landscape.yaml_taxonomy_repository import (
    PLAN_MECHANISM_DIRECTORY,
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
  - {id: sample-states-cp, label: Sample states CP, kind: cp, side: neg, aliases: [sample states cp]}
"""

WORDS = """\
schema_version: 1
topic_id: policy-sample-topic
words: [preempt, waiver, opt-out]
"""


def config(tmp_path: Path, files: dict[str, str] | None = None) -> Path:
    (tmp_path / "taxonomies").mkdir(parents=True)
    (tmp_path / "topics.yaml").write_text(TOPICS, encoding="utf-8")
    (tmp_path / "taxonomies" / "policy-sample-topic.yaml").write_text(TAXONOMY, encoding="utf-8")
    if files:
        (tmp_path / PLAN_MECHANISM_DIRECTORY).mkdir()
    for name, text in (files or {}).items():
        (tmp_path / PLAN_MECHANISM_DIRECTORY / name).write_text(text, encoding="utf-8")
    return tmp_path


def test_the_directory_is_plan_mechanisms() -> None:
    assert PLAN_MECHANISM_DIRECTORY == "plan_mechanisms"


def test_a_topic_with_no_file_loads_and_has_no_words(tmp_path: Path) -> None:
    repository = YamlTaxonomyRepository.load(config(tmp_path))
    assert repository.plan_mechanism_words("policy-sample-topic") is None


def test_the_file_loads_as_its_words_in_the_coachs_order(tmp_path: Path) -> None:
    repository = YamlTaxonomyRepository.load(config(tmp_path, {"policy-sample-topic.yaml": WORDS}))
    assert repository.plan_mechanism_words("policy-sample-topic") == PlanMechanismWords(
        topic_id="policy-sample-topic", words=("preempt", "waiver", "opt-out")
    )


def test_an_empty_list_loads_as_no_words(tmp_path: Path) -> None:
    text = WORDS.replace("[preempt, waiver, opt-out]", "[]")
    repository = YamlTaxonomyRepository.load(config(tmp_path, {"policy-sample-topic.yaml": text}))
    found = repository.plan_mechanism_words("policy-sample-topic")
    assert found is not None and found.words == ()


def test_a_word_of_32_letters_and_one_of_3_load(tmp_path: Path) -> None:
    text = WORDS.replace("opt-out", "a" * 32).replace("waiver", "fee")
    repository = YamlTaxonomyRepository.load(config(tmp_path, {"policy-sample-topic.yaml": text}))
    found = repository.plan_mechanism_words("policy-sample-topic")
    assert found is not None and found.words == ("preempt", "fee", "a" * 32)


def test_a_topic_with_no_taxonomy_is_asked_for_in_vain(tmp_path: Path) -> None:
    repository = YamlTaxonomyRepository.load(config(tmp_path))
    with pytest.raises(NoTaxonomyForTopic):
        repository.plan_mechanism_words("ld-sample-early")


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
        ("a word in capitals", "policy-sample-topic.yaml", WORDS.replace("waiver", "Waiver"), "words.1"),
        ("a digit in a word", "policy-sample-topic.yaml", WORDS.replace("waiver", "waiver2"), "words.1"),
        (
            "two words with a space",
            "policy-sample-topic.yaml",
            WORDS.replace("waiver", "'state waiver'"),
            "words.1",
        ),
        ("a doubled hyphen", "policy-sample-topic.yaml", WORDS.replace("opt-out", "opt--out"), "words.2"),
        ("a leading hyphen", "policy-sample-topic.yaml", WORDS.replace("opt-out", "-out"), "words.2"),
        ("a word under 3 characters", "policy-sample-topic.yaml", WORDS.replace("waiver", "wa"), "words.1"),
        (
            "a word over 32 characters",
            "policy-sample-topic.yaml",
            WORDS.replace("waiver", "a" * 33),
            "words.1",
        ),
        (
            "a word listed twice",
            "policy-sample-topic.yaml",
            WORDS.replace("opt-out", "preempt"),
            "a word is listed twice: preempt",
        ),
        ("an unknown key", "policy-sample-topic.yaml", WORDS + "mechanisms: [waive]\n", "mechanisms"),
        ("a .yml file", "policy-sample-topic.yml", WORDS, "ends in .yaml"),
    ],
    ids=lambda value: value if isinstance(value, str) and " " in value and "\n" not in value else "",
)
def test_a_bad_file_is_refused_naming_it(
    tmp_path: Path, case: str, name: str, text: str, expected: str
) -> None:
    with pytest.raises(TaxonomyConfigError, match=expected) as raised:
        YamlTaxonomyRepository.load(config(tmp_path, {name: text}))
    assert raised.value.path.endswith(f"{PLAN_MECHANISM_DIRECTORY}/{name}"), case
