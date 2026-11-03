"""The YAML taxonomy repository (`v1-e32-t01-position-taxonomy`, node yaml-repository; ac1, ac2).

`config/landscape/` holds `topics.yaml` and `taxonomies/*.yaml`. The repository reads every file
when it is built and checks them as one configuration: a file named for another topic, a taxonomy
whose version or event disagrees with `topics.yaml`, a topic whose taxonomy is missing, a file no
topic names and a key given twice are refused, each naming the file. Then a (caselist, snapshot)
resolves to one topic and its taxonomy, with generic.yaml's positions for its event merged in.

Every topic, caselist slug and position here is invented for the test.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from textwrap import dedent

import pytest

from debate_core.application.ports.taxonomy_repository import (
    NoTaxonomyForTopic,
    TaxonomyConfigError,
    TaxonomyRepository,
)
from debate_core.integrations.landscape.yaml_taxonomy_repository import (
    YamlTaxonomyRepository,
    load_topic_map,
)

TOPICS = """\
schema_version: 1
topics:
  - id: policy-sample-topic
    event: POLICY
    resolution: "Resolved: an invented resolution for the test."
    taxonomy_version: 1.0.0
    caselists:
      - {caselist: hspolicy99, from: 2026-07-01, to: 2027-06-30}
  - id: ld-sample-early
    event: LD
    caselists:
      - {caselist: hsld99, from: 2026-09-01, to: 2026-10-31}
"""

POLICY_TAXONOMY = """\
schema_version: 1
topic_id: policy-sample-topic
taxonomy_version: 1.0.0
event: POLICY
positions:
  - id: sample-plan-aff
    label: Sample Plan
    kind: aff
    side: aff
    aliases: [sample plan aff]
  - id: sample-spending-da
    label: Spending DA
    kind: da
    side: neg
    aliases: [spending da]
"""

GENERIC = """\
schema_version: 1
topic_id: generic
taxonomy_version: 1.0.0
event: null
positions:
  - id: condo-bad
    label: Condo bad
    kind: theory
    side: aff
    events: [POLICY, LD]
    aliases: [condo bad]
  - id: sample-ld-only-theory
    label: An LD-only theory shell
    kind: theory
    side: both
    events: [LD]
"""


def write_config(
    root: Path,
    *,
    topics: str = TOPICS,
    taxonomies: dict[str, str] | None = None,
) -> Path:
    directory = root / "landscape"
    (directory / "taxonomies").mkdir(parents=True)
    (directory / "topics.yaml").write_text(topics, encoding="utf-8")
    files = {"policy-sample-topic": POLICY_TAXONOMY, "generic": GENERIC} if taxonomies is None else taxonomies
    for stem, text in files.items():
        (directory / "taxonomies" / f"{stem}.yaml").write_text(text, encoding="utf-8")
    return directory


def refusal(directory: Path) -> TaxonomyConfigError:
    with pytest.raises(TaxonomyConfigError) as caught:
        YamlTaxonomyRepository.load(directory)
    return caught.value


# ------------------------------------------------------------------------------------------------
# Loading and resolving
# ------------------------------------------------------------------------------------------------


def test_the_repository_is_a_taxonomy_repository(tmp_path: Path) -> None:
    assert isinstance(YamlTaxonomyRepository.load(write_config(tmp_path)), TaxonomyRepository)


def test_a_snapshot_resolves_to_its_topic_and_its_merged_taxonomy(tmp_path: Path) -> None:
    repository = YamlTaxonomyRepository.load(write_config(tmp_path))
    resolved = repository.resolve("hspolicy99", date(2026, 11, 7))
    assert resolved is not None
    assert resolved.topic.id == "policy-sample-topic"
    assert resolved.topic.taxonomy_version == "1.0.0"
    assert resolved.taxonomy is not None
    assert [one.id for one in resolved.taxonomy.positions] == [
        "sample-plan-aff",
        "sample-spending-da",
        "condo-bad",
    ]


def test_a_topic_with_no_taxonomy_resolves_with_none(tmp_path: Path) -> None:
    repository = YamlTaxonomyRepository.load(write_config(tmp_path))
    resolved = repository.resolve("hsld99", date(2026, 10, 31))
    assert resolved is not None
    assert resolved.topic.id == "ld-sample-early"
    assert resolved.taxonomy is None


@pytest.mark.parametrize(
    ("caselist", "snapshot"),
    [("hsld99", date(2026, 11, 1)), ("hspolicy99", date(2026, 6, 30)), ("hspf99", date(2026, 10, 1))],
)
def test_a_snapshot_no_range_covers_resolves_to_nothing(
    tmp_path: Path, caselist: str, snapshot: date
) -> None:
    assert YamlTaxonomyRepository.load(write_config(tmp_path)).resolve(caselist, snapshot) is None


def test_a_taxonomy_is_asked_for_by_topic_id(tmp_path: Path) -> None:
    repository = YamlTaxonomyRepository.load(write_config(tmp_path))
    assert repository.taxonomy("policy-sample-topic").resolve("condo-bad").label == "Condo bad"
    with pytest.raises(NoTaxonomyForTopic):
        repository.taxonomy("ld-sample-early")
    with pytest.raises(NoTaxonomyForTopic):
        repository.taxonomy("no-such-topic")


def test_the_topic_map_is_the_file(tmp_path: Path) -> None:
    directory = write_config(tmp_path)
    loaded = YamlTaxonomyRepository.load(directory).topic_map()
    assert [topic.id for topic in loaded.topics] == ["policy-sample-topic", "ld-sample-early"]
    assert load_topic_map(directory / "topics.yaml") == loaded


def test_generic_yaml_may_be_absent(tmp_path: Path) -> None:
    repository = YamlTaxonomyRepository.load(
        write_config(tmp_path, taxonomies={"policy-sample-topic": POLICY_TAXONOMY})
    )
    assert [one.id for one in repository.taxonomy("policy-sample-topic").positions] == [
        "sample-plan-aff",
        "sample-spending-da",
    ]


# ------------------------------------------------------------------------------------------------
# What the repository refuses, naming the file
# ------------------------------------------------------------------------------------------------


def test_overlapping_ranges_in_the_topic_map_are_refused(tmp_path: Path) -> None:
    topics = TOPICS + dedent(
        """\
          - id: ld-sample-late
            event: LD
            caselists:
              - {caselist: hsld99, from: 2026-10-15, to: 2026-12-31}
        """
    )
    error = refusal(write_config(tmp_path, topics=topics))
    assert error.path.endswith("topics.yaml")
    assert "overlap" in str(error)


def test_a_taxonomy_file_named_for_another_topic_is_refused(tmp_path: Path) -> None:
    error = refusal(
        write_config(
            tmp_path, taxonomies={"policy-sample-topic": POLICY_TAXONOMY, "policy-misnamed": POLICY_TAXONOMY}
        )
    )
    assert error.path.endswith("policy-misnamed.yaml")
    assert "policy-sample-topic" in str(error)


def test_a_taxonomy_version_topics_yaml_does_not_name_is_refused(tmp_path: Path) -> None:
    error = refusal(
        write_config(
            tmp_path,
            taxonomies={
                "policy-sample-topic": POLICY_TAXONOMY.replace(
                    "taxonomy_version: 1.0.0", "taxonomy_version: 1.1.0"
                )
            },
        )
    )
    assert error.path.endswith("policy-sample-topic.yaml")
    assert "1.1.0" in str(error)
    assert "1.0.0" in str(error)


def test_a_taxonomy_of_another_event_than_its_topic_is_refused(tmp_path: Path) -> None:
    error = refusal(
        write_config(
            tmp_path,
            taxonomies={"policy-sample-topic": POLICY_TAXONOMY.replace("event: POLICY", "event: LD")},
        )
    )
    assert error.path.endswith("policy-sample-topic.yaml")
    assert "LD" in str(error)


def test_a_topic_whose_taxonomy_file_is_missing_is_refused(tmp_path: Path) -> None:
    error = refusal(write_config(tmp_path, taxonomies={"generic": GENERIC}))
    assert "policy-sample-topic" in str(error)


def test_a_taxonomy_no_topic_gives_a_version_is_refused(tmp_path: Path) -> None:
    ld = POLICY_TAXONOMY.replace("policy-sample-topic", "ld-sample-early").replace("POLICY", "LD")
    error = refusal(
        write_config(tmp_path, taxonomies={"policy-sample-topic": POLICY_TAXONOMY, "ld-sample-early": ld})
    )
    assert error.path.endswith("ld-sample-early.yaml")


def test_a_taxonomy_no_topic_names_is_refused(tmp_path: Path) -> None:
    orphan = POLICY_TAXONOMY.replace("policy-sample-topic", "policy-orphan")
    error = refusal(
        write_config(tmp_path, taxonomies={"policy-sample-topic": POLICY_TAXONOMY, "policy-orphan": orphan})
    )
    assert error.path.endswith("policy-orphan.yaml")


def test_a_generic_alias_a_topic_also_claims_is_refused_naming_the_topic(tmp_path: Path) -> None:
    clashing = POLICY_TAXONOMY.replace("aliases: [spending da]", "aliases: [spending da, condo bad]")
    error = refusal(write_config(tmp_path, taxonomies={"policy-sample-topic": clashing, "generic": GENERIC}))
    assert error.path.endswith("policy-sample-topic.yaml")
    assert "condo bad" in str(error)


def test_a_key_given_twice_is_refused(tmp_path: Path) -> None:
    doubled = POLICY_TAXONOMY.replace(
        "    aliases: [spending da]\n", "    aliases: [spending da]\n    aliases: [tradeoff da]\n"
    )
    error = refusal(write_config(tmp_path, taxonomies={"policy-sample-topic": doubled}))
    assert error.path.endswith("policy-sample-topic.yaml")
    assert "twice" in str(error)


def test_a_taxonomy_that_breaks_a_model_rule_is_refused_naming_the_file(tmp_path: Path) -> None:
    broken = POLICY_TAXONOMY.replace("kind: da", "kind: disad")
    error = refusal(write_config(tmp_path, taxonomies={"policy-sample-topic": broken}))
    assert error.path.endswith("policy-sample-topic.yaml")
    assert "kind" in str(error)


def test_text_that_is_not_yaml_is_refused(tmp_path: Path) -> None:
    error = refusal(write_config(tmp_path, topics="topics: [unclosed\n"))
    assert error.path.endswith("topics.yaml")


def test_a_missing_topic_map_is_refused(tmp_path: Path) -> None:
    directory = write_config(tmp_path)
    (directory / "topics.yaml").unlink()
    assert refusal(directory).path.endswith("topics.yaml")


def test_a_yml_file_is_refused_rather_than_skipped(tmp_path: Path) -> None:
    directory = write_config(tmp_path)
    (directory / "taxonomies" / "policy-extra.yml").write_text(POLICY_TAXONOMY, encoding="utf-8")
    error = refusal(directory)
    assert error.path.endswith("policy-extra.yml")
    assert ".yaml" in str(error)
