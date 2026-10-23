"""The coach's overrides files, read and checked with the taxonomies (`v1-e32-t02` ac4).

`config/landscape/overrides/<topic id>.yaml` holds the decisions from the review queue. The
repository reads each with the rest of the configuration and refuses a file named for another
topic, one for a topic with no taxonomy, a decision naming no position the merged taxonomy counts
under, and a `.yml` file it would otherwise skip. A topic with no file has no overrides, and a file
written by `render_override_file` reads back as the same rules.

Every topic, caselist slug, heading and position here is invented.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from textwrap import dedent

import pytest

from debate_core.application.ports.taxonomy_repository import NoTaxonomyForTopic, TaxonomyConfigError
from debate_core.domain.landscape_classification import HeadingOverride, OverrideRules
from debate_core.integrations.landscape.yaml_taxonomy_repository import (
    YamlTaxonomyRepository,
    load_override_file,
    render_override_file,
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
  - {id: spending-da, label: Spending DA, kind: da, side: neg, aliases: [spending da]}
  - {id: states-cp, label: States CP, kind: cp, side: neg, aliases: [states cp]}
  - {id: fed-cp, label: Fed CP, kind: cp, side: neg, deprecated: true, merged_into: states-cp}
"""

GENERIC = """\
schema_version: 1
topic_id: generic
taxonomy_version: 1.0.0
event: null
positions:
  - {id: condo-bad, label: Condo bad, kind: theory, side: aff, events: [POLICY], aliases: [condo bad]}
"""

OVERRIDES = """\
schema_version: 1
topic_id: policy-sample-topic
overrides:
  - {heading: fed key, position_id: fed-cp, decided: 2026-10-24}
  - {heading: condo, position_id: condo-bad}
  - {heading: link, position_id: null}
"""


def config(tmp_path: Path, overrides: dict[str, str] | None = None) -> Path:
    (tmp_path / "taxonomies").mkdir(parents=True)
    (tmp_path / "topics.yaml").write_text(TOPICS, encoding="utf-8")
    (tmp_path / "taxonomies" / "policy-sample-topic.yaml").write_text(TAXONOMY, encoding="utf-8")
    (tmp_path / "taxonomies" / "generic.yaml").write_text(GENERIC, encoding="utf-8")
    if overrides:
        (tmp_path / "overrides").mkdir()
    for name, text in (overrides or {}).items():
        (tmp_path / "overrides" / name).write_text(dedent(text), encoding="utf-8")
    return tmp_path


def test_a_topic_with_no_overrides_file_has_no_overrides(tmp_path: Path) -> None:
    repository = YamlTaxonomyRepository.load(config(tmp_path))
    assert repository.overrides("policy-sample-topic") == OverrideRules(topic_id="policy-sample-topic")


def test_overrides_load_and_may_name_generic_merged_and_no_positions(tmp_path: Path) -> None:
    repository = YamlTaxonomyRepository.load(config(tmp_path, {"policy-sample-topic.yaml": OVERRIDES}))
    found = repository.overrides("policy-sample-topic")
    assert [(one.heading, one.position_id) for one in found.overrides] == [
        ("fed key", "fed-cp"),
        ("condo", "condo-bad"),
        ("link", None),
    ]
    assert found.overrides[0].decided == date(2026, 10, 24)


def test_overrides_of_a_topic_with_no_taxonomy_are_asked_for_in_vain(tmp_path: Path) -> None:
    repository = YamlTaxonomyRepository.load(config(tmp_path))
    with pytest.raises(NoTaxonomyForTopic):
        repository.overrides("ld-sample-early")


@pytest.mark.parametrize(
    ("case", "name", "text", "expected"),
    [
        (
            "a file named for another topic",
            "policy-other-topic.yaml",
            OVERRIDES,
            "named for policy-other-topic",
        ),
        (
            "a topic with no taxonomy",
            "ld-sample-early.yaml",
            OVERRIDES.replace("policy-sample-topic", "ld-sample-early"),
            "gives ld-sample-early a taxonomy",
        ),
        (
            "a decision naming no position",
            "policy-sample-topic.yaml",
            OVERRIDES.replace("fed-cp", "medicaid-da"),
            "medicaid-da, which is not a position",
        ),
        (
            "a heading not written as a normalized heading",
            "policy-sample-topic.yaml",
            OVERRIDES.replace("fed key", "Fed Key"),
            "normalized heading",
        ),
        ("a .yml file", "policy-sample-topic.yml", OVERRIDES, "ends in .yaml"),
        (
            "a heading given twice",
            "policy-sample-topic.yaml",
            OVERRIDES.replace("heading: link", "heading: fed key"),
            "overridden twice",
        ),
    ],
    ids=lambda value: value if isinstance(value, str) and " " in value else "",
)
def test_a_bad_overrides_file_is_refused_naming_it(
    tmp_path: Path, case: str, name: str, text: str, expected: str
) -> None:
    directory = config(tmp_path)
    (directory / "overrides").mkdir()
    (directory / "overrides" / name).write_text(text, encoding="utf-8")
    with pytest.raises(TaxonomyConfigError, match=expected) as refused:
        YamlTaxonomyRepository.load(directory)
    assert refused.value.path.endswith(name), case


def test_a_rendered_file_reads_back_as_the_same_rules(tmp_path: Path) -> None:
    rules = OverrideRules(
        topic_id="policy-sample-topic",
        overrides=(
            HeadingOverride(heading="fed key", position_id="states-cp", decided=date(2026, 10, 24)),
            HeadingOverride(heading="link", position_id=None),
        ),
    )
    text = render_override_file(rules)
    assert text.startswith("# The coach's decisions")
    path = tmp_path / "policy-sample-topic.yaml"
    path.write_text(text, encoding="utf-8")
    assert load_override_file(path) == rules
    assert "position_id: null" in text
