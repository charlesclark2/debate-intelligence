"""Every committed landscape taxonomy validates and names no person (`v1-e32-t01-position-taxonomy`).

`config/landscape/` is the coach's to edit, so this suite is what an edit must pass:

* **It loads.** `topics.yaml` and every file under `taxonomies/` pass the repository's checks as one
  configuration: ids, parents, merges, aliases, versions and events (ac1, ac2).
* **It is big enough to count against.** Each taxonomy file has at least twelve active positions (ac3).
* **Its aliases can be found.** Every alias is a heading the normalizer can produce, so the matcher
  (`v1-e32-t02`) normalizes a heading and looks it up, and an alias no heading can reach is refused.
* **It names no one** (the task's forbidden list; the PM's ruling of 2026-10-22). An alias holding a
  token shaped like a team code (two letters that are not debate vocabulary), a label holding one
  (`AB`, `RiOs`) or a capitalized name after its first word, and any field holding a word that names
  a school (`high`, `academy`) are refused. The synthetic cases below must each fail the check.
* **The coach's overrides** (`overrides/<topic id>.yaml`, `v1-e32-t02`) load with the taxonomies,
  each heading is one the normalizer can produce, and the same personal-data check runs over their
  headings (the PM's ruling of 2026-10-23): a decision copies a heading teams wrote into the
  repository, so it is held to what an alias is held to.
* **Nothing else is in the directory** but the release lock (`released.yaml`, `v1-e32-t08`, checked
  in `test_landscape_released_ids.py`), so the seeding CSV and the review queue, which hold real
  headings, cannot be committed beside the files by mistake.

No caselist slug or topic id is written here: the files are found by reading the directory.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from debate_core.arguments.landscape.headings import normalize_heading
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import OverrideRules
from debate_core.integrations.landscape.released_ids import RELEASED_FILE
from debate_core.integrations.landscape.yaml_taxonomy_repository import (
    OVERRIDE_DIRECTORY,
    TAXONOMY_DIRECTORY,
    TOPICS_FILE,
    YamlTaxonomyRepository,
    load_override_file,
    load_taxonomy_file,
)

CONFIG = Path(__file__).resolve().parents[2] / "config" / "landscape"
TAXONOMY_FILES = sorted((CONFIG / TAXONOMY_DIRECTORY).glob("*.yaml"))
OVERRIDE_FILES = sorted((CONFIG / OVERRIDE_DIRECTORY).glob("*.yaml"))
MINIMUM_ACTIVE_POSITIONS = 12

SHORT_WORDS = frozenset(
    {"at", "cp", "da", "no", "ai", "us", "of", "to", "on", "in", "or", "an", "do", "is", "by", "uq"}
)
"""Two-letter words an alias may hold. Any other two letters read as a team code's initials; a
coach adding a real two-letter word adds it here in the same change. `uq` is "uniqueness", confirmed
by the coach on 2026-10-24 for his first review-queue decisions (`v1-e32-t05`)."""

SHORT_LABEL_ACRONYMS = frozenset({"DA", "CP", "AI", "US"})
SCHOOL_WORDS = frozenset({"school", "high", "academy", "prep", "hs", "isd", "secondary", "middle"})
_CAMEL_INITIALS = re.compile(r"^[A-Z][a-z][A-Z][a-z]$")
_TITLE_WORD = re.compile(r"^[A-Z][a-z]+$")


def _heading_findings(owner: str, heading: str) -> list[str]:
    """A two-letter token that is not debate vocabulary, in an alias, keyword or override heading."""
    return [
        f"{owner}: {heading!r} holds {token!r}, shaped like a team code"
        for token in heading.split()
        if len(token) == 2 and token.isalpha() and token not in SHORT_WORDS
    ]


def personal_data_findings(taxonomy: Taxonomy) -> list[str]:
    """Everything in `taxonomy` shaped like a team code, a school or a person's name."""
    findings: list[str] = []
    for position in taxonomy.positions:
        for alias in (*position.aliases, *(keyword.casefold() for keyword in position.tag_keywords)):
            findings += _heading_findings(position.id, alias)
        words = [word.strip("()[],.;:/") for word in position.label.split()]
        for index, word in enumerate(words):
            if _CAMEL_INITIALS.match(word) or (
                len(word) == 2 and word.isupper() and word not in SHORT_LABEL_ACRONYMS
            ):
                findings.append(f"{position.id}: its label holds {word!r}, shaped like a team code")
            elif index > 0 and _TITLE_WORD.match(word):
                findings.append(
                    f"{position.id}: its label holds {word!r}, shaped like a name; labels are sentence case"
                )
        text = " ".join((position.label, position.description, *position.aliases, *position.tag_keywords))
        for word in re.findall(r"[a-z]+", text.casefold()):
            if word in SCHOOL_WORDS:
                findings.append(f"{position.id}: {word!r} names a school")
    return findings


def override_findings(rules: OverrideRules) -> list[str]:
    """Every override heading shaped like a team code or naming a school, as an alias would be refused."""
    findings: list[str] = []
    for rule in rules.overrides:
        findings += _heading_findings(f"the override of {rule.heading!r}", rule.heading)
        findings += [
            f"the override of {rule.heading!r}: {word!r} names a school"
            for word in rule.heading.split()
            if word in SCHOOL_WORDS
        ]
    return findings


# ------------------------------------------------------------------------------------------------
# The committed files
# ------------------------------------------------------------------------------------------------


def test_there_are_taxonomy_files() -> None:
    assert TAXONOMY_FILES, f"no taxonomy under {CONFIG / TAXONOMY_DIRECTORY}"


def test_the_configuration_loads_as_one() -> None:
    repository = YamlTaxonomyRepository.load(CONFIG)
    for topic in repository.topic_map().topics:
        if topic.taxonomy_version is not None:
            assert repository.taxonomy(topic.id).taxonomy_version == topic.taxonomy_version


@pytest.mark.parametrize("path", TAXONOMY_FILES, ids=lambda path: path.stem)
def test_each_taxonomy_has_enough_active_positions_each_with_a_kind_and_a_side(path: Path) -> None:
    taxonomy = load_taxonomy_file(path)
    assert len(taxonomy.active_positions) >= MINIMUM_ACTIVE_POSITIONS
    for position in taxonomy.positions:
        assert position.kind.value and position.side.value


@pytest.mark.parametrize("path", TAXONOMY_FILES, ids=lambda path: path.stem)
def test_every_alias_is_a_heading_the_normalizer_can_produce(path: Path) -> None:
    for position in load_taxonomy_file(path).positions:
        for alias in position.aliases:
            normalized = normalize_heading(alias)
            assert (normalized.text, normalized.answer) == (alias, False), f"{position.id}: {alias!r}"


@pytest.mark.parametrize("path", TAXONOMY_FILES, ids=lambda path: path.stem)
def test_no_taxonomy_names_a_team_a_school_or_a_person(path: Path) -> None:
    assert personal_data_findings(load_taxonomy_file(path)) == []


@pytest.mark.parametrize("path", OVERRIDE_FILES, ids=lambda path: path.stem)
def test_every_override_heading_is_a_heading_the_normalizer_can_produce(path: Path) -> None:
    for rule in load_override_file(path).overrides:
        normalized = normalize_heading(rule.heading)
        assert (normalized.text, normalized.answer) == (rule.heading, False), rule.heading


@pytest.mark.parametrize("path", OVERRIDE_FILES, ids=lambda path: path.stem)
def test_no_override_names_a_team_a_school_or_a_person(path: Path) -> None:
    assert override_findings(load_override_file(path)) == []


def test_the_directory_holds_only_the_topic_map_taxonomies_overrides_and_release_lock() -> None:
    found = sorted(str(path.relative_to(CONFIG)) for path in CONFIG.rglob("*") if path.is_file())
    allowed = [
        TOPICS_FILE,
        RELEASED_FILE,
        *(f"{TAXONOMY_DIRECTORY}/{path.name}" for path in TAXONOMY_FILES),
        *(f"{OVERRIDE_DIRECTORY}/{path.name}" for path in OVERRIDE_FILES),
    ]
    assert found == sorted(allowed)


# ------------------------------------------------------------------------------------------------
# The check fails on what it is for (synthetic; every name and code is invented)
# ------------------------------------------------------------------------------------------------


def one_position(**fields: Any) -> Taxonomy:
    position: dict[str, Any] = {
        "id": "sample-spending-da",
        "label": "Spending DA",
        "kind": "da",
        "side": "neg",
    }
    position.update(fields)
    return Taxonomy.model_validate(
        {
            "topic_id": "policy-sample-topic",
            "taxonomy_version": "1.0.0",
            "event": "POLICY",
            "positions": [position],
        }
    )


@pytest.mark.parametrize(
    ("case", "fields", "expected"),
    [
        ("a team-code-shaped alias", {"aliases": ["spending da qx"]}, "team code"),
        ("a team-code-shaped tag keyword", {"tag_keywords": ["QX"]}, "team code"),
        ("camel initials in a label", {"label": "Spending DA (RiOs)"}, "team code"),
        ("two capitals in a label", {"label": "Spending DA QX"}, "team code"),
        ("a name in a label", {"label": "Spending DA Avery Quinlan"}, "name"),
        ("a school in an alias", {"aliases": ["sample high spending da"]}, "school"),
        ("a school in a description", {"description": "Read by the academy down the road."}, "school"),
    ],
    ids=lambda value: value if isinstance(value, str) and " " in value else "",
)
def test_the_personal_data_check_refuses(case: str, fields: dict[str, Any], expected: str) -> None:
    findings = personal_data_findings(one_position(**fields))
    assert findings, case
    assert all(expected in finding for finding in findings), findings


def test_the_personal_data_check_passes_debate_vocabulary() -> None:
    taxonomy = one_position(
        label="T-USFG / framework",
        aliases=["t no single payer", "adv cp", "theory at 50 state fiat bad", "irs da"],
    )
    assert personal_data_findings(taxonomy) == []


@pytest.mark.parametrize(
    ("heading", "expected"),
    [("fed key qx", "team code"), ("sample high fed key", "school"), ("qx", "team code")],
)
def test_the_override_check_refuses(heading: str, expected: str) -> None:
    rules = OverrideRules.model_validate(
        {"topic_id": "policy-sample-topic", "overrides": [{"heading": heading, "position_id": None}]}
    )
    findings = override_findings(rules)
    assert findings
    assert all(expected in finding for finding in findings), findings


def test_the_override_check_passes_debate_vocabulary() -> None:
    rules = OverrideRules.model_validate(
        {
            "topic_id": "policy-sample-topic",
            "overrides": [
                {"heading": "fed key", "position_id": None},
                {"heading": "da at link", "position_id": None},
            ],
        }
    )
    assert override_findings(rules) == []
