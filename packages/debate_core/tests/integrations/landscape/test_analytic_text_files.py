"""The CP texts' actor list, read and checked with the taxonomies (`v1-e32-t11` ac2).

`config/landscape/analytic_texts/<topic id>.yaml` holds the actor phrases a CP text read by its place
must name before its `should` (the PM's ruling 1 of 2026-10-24): config, beside `v1-e32-t09`'s word
lists, never in Python. The repository reads each with the rest of the configuration and refuses a file
named for another topic, one for a topic with no taxonomy, a phrase that is not lowercase words, an
empty list, and a `.yml` file it would otherwise skip. A topic with no file has no actors, so no CP text
is read by its place there.

Every topic, caselist slug and phrase here is invented.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from debate_core.application.ports.taxonomy_repository import NoTaxonomyForTopic, TaxonomyConfigError
from debate_core.arguments.landscape.analytic_texts import CounterplanActors
from debate_core.integrations.landscape.yaml_taxonomy_repository import (
    ANALYTIC_TEXT_DIRECTORY,
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

ACTORS = """\
schema_version: 1
topic_id: policy-sample-topic
cp_text_actors: [fifty states, usfg, congress]
"""


def config(tmp_path: Path, files: dict[str, str] | None = None) -> Path:
    (tmp_path / "taxonomies").mkdir(parents=True)
    (tmp_path / "topics.yaml").write_text(TOPICS, encoding="utf-8")
    (tmp_path / "taxonomies" / "policy-sample-topic.yaml").write_text(TAXONOMY, encoding="utf-8")
    if files:
        (tmp_path / ANALYTIC_TEXT_DIRECTORY).mkdir()
    for name, text in (files or {}).items():
        (tmp_path / ANALYTIC_TEXT_DIRECTORY / name).write_text(text, encoding="utf-8")
    return tmp_path


def test_the_directory_is_analytic_texts() -> None:
    assert ANALYTIC_TEXT_DIRECTORY == "analytic_texts"


def test_a_topic_with_no_file_has_no_actors(tmp_path: Path) -> None:
    assert YamlTaxonomyRepository.load(config(tmp_path)).cp_text_actors("policy-sample-topic") is None


def test_the_file_loads_as_its_actor_phrases(tmp_path: Path) -> None:
    repository = YamlTaxonomyRepository.load(config(tmp_path, {"policy-sample-topic.yaml": ACTORS}))
    assert repository.cp_text_actors("policy-sample-topic") == CounterplanActors(
        topic_id="policy-sample-topic", cp_text_actors=("fifty states", "usfg", "congress")
    )


def test_a_topic_with_no_taxonomy_is_asked_for_in_vain(tmp_path: Path) -> None:
    repository = YamlTaxonomyRepository.load(config(tmp_path))
    with pytest.raises(NoTaxonomyForTopic):
        repository.cp_text_actors("ld-sample-early")


@pytest.mark.parametrize(
    ("case", "name", "text", "expected"),
    [
        ("a file named for another topic", "policy-other-topic.yaml", ACTORS, "named for policy-other-topic"),
        (
            "a topic with no taxonomy",
            "ld-sample-early.yaml",
            ACTORS.replace("policy-sample-topic", "ld-sample-early"),
            "gives ld-sample-early a taxonomy",
        ),
        (
            "a phrase in capitals",
            "policy-sample-topic.yaml",
            ACTORS.replace("usfg", "USFG"),
            "cp_text_actors",
        ),
        (
            "punctuation in a phrase",
            "policy-sample-topic.yaml",
            ACTORS.replace("usfg", "u.s.f.g."),
            "cp_text_actors",
        ),
        (
            "no phrase",
            "policy-sample-topic.yaml",
            ACTORS.replace("[fifty states, usfg, congress]", "[]"),
            "cp_text_actors",
        ),
        ("an unknown key", "policy-sample-topic.yaml", ACTORS + "actors: [states]\n", "actors"),
        ("a .yml file", "policy-sample-topic.yml", ACTORS, "ends in .yaml"),
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
