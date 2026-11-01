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
* **The resolutional plan's words** (`plan_texts/<topic id>.yaml`, `v1-e32-t09`) load with the
  taxonomies, and the same check runs over them: they came from the teams' plan texts, so a word
  shaped like a team code or naming a school is refused.
* **The CP texts' actors** (`analytic_texts/<topic id>.yaml`, `v1-e32-t11`) load with the taxonomies,
  and the same check runs over their phrases: an actor is a word the teams' CP texts hold.
* **The K-aff position and its K families** (`kritikal_affs/<topic id>.yaml`, `v1-e32-t17`) load with
  the taxonomies, and the same check runs over the families' labels and phrases: a phrase is a word the
  teams' headings hold.
* **The plan-mechanism words** (`plan_mechanisms/<topic id>.yaml`, `v1-e33-t14`) load with the
  taxonomies, and the same check runs over them: a word is one the teams' block headings hold.
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

from debate_core.application.plan_mechanism_words import PlanMechanismWords
from debate_core.arguments.landscape.analytic_texts import CounterplanActors
from debate_core.arguments.landscape.headings import normalize_heading
from debate_core.arguments.landscape.kritikal_aff import KritikalAffConfig, KritikalFamily
from debate_core.arguments.landscape.plan_text import ResolutionalPlanWords
from debate_core.domain.landscape import Position, Taxonomy
from debate_core.domain.landscape_classification import OverrideRules
from debate_core.integrations.landscape.released_ids import RELEASED_FILE
from debate_core.integrations.landscape.yaml_taxonomy_repository import (
    ANALYTIC_TEXT_DIRECTORY,
    KRITIKAL_AFF_DIRECTORY,
    OVERRIDE_DIRECTORY,
    PLAN_MECHANISM_DIRECTORY,
    PLAN_TEXT_DIRECTORY,
    TAXONOMY_DIRECTORY,
    TOPICS_FILE,
    YamlTaxonomyRepository,
    load_analytic_text_file,
    load_kritikal_aff_file,
    load_override_file,
    load_plan_mechanism_file,
    load_plan_text_file,
    load_taxonomy_file,
)

CONFIG = Path(__file__).resolve().parents[2] / "config" / "landscape"
TAXONOMY_FILES = sorted((CONFIG / TAXONOMY_DIRECTORY).glob("*.yaml"))
OVERRIDE_FILES = sorted((CONFIG / OVERRIDE_DIRECTORY).glob("*.yaml"))
PLAN_TEXT_FILES = sorted((CONFIG / PLAN_TEXT_DIRECTORY).glob("*.yaml"))
ANALYTIC_TEXT_FILES = sorted((CONFIG / ANALYTIC_TEXT_DIRECTORY).glob("*.yaml"))
KRITIKAL_AFF_FILES = sorted((CONFIG / KRITIKAL_AFF_DIRECTORY).glob("*.yaml"))
PLAN_MECHANISM_FILES = sorted((CONFIG / PLAN_MECHANISM_DIRECTORY).glob("*.yaml"))
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


def _forms(position: Position) -> tuple[str, ...]:
    """Every heading form a position's scenario list holds (`v1-e32-t22`)."""
    return (*(form for scenario in position.scenarios for form in scenario.forms), *position.not_scenarios)


def _label_findings(owner: str, label: str, *, sentence_case: bool = True) -> list[str]:
    """A label or a scenario name holding a team code's shape, or a label a capital after its first word.

    A scenario name may carry capitals after its first word, for a proper noun (`War with China`; the
    PM's ruling of 2026-10-26 on `v1-e32-t22`); a team code's shape and a school word are still refused.
    """
    findings: list[str] = []
    words = [word.strip("()[],.;:/") for word in label.split()]
    for index, word in enumerate(words):
        if _CAMEL_INITIALS.match(word) or (
            len(word) == 2 and word.isupper() and word not in SHORT_LABEL_ACRONYMS
        ):
            findings.append(f"{owner} holds {word!r}, shaped like a team code")
        elif sentence_case and index > 0 and _TITLE_WORD.match(word):
            findings.append(f"{owner} holds {word!r}, shaped like a name; labels are sentence case")
    return findings


def personal_data_findings(taxonomy: Taxonomy) -> list[str]:
    """Everything in `taxonomy` shaped like a team code, a school or a person's name."""
    findings: list[str] = []
    for position in taxonomy.positions:
        for alias in (
            *position.aliases,
            *(keyword.casefold() for keyword in position.tag_keywords),
            *_forms(position),
        ):
            findings += _heading_findings(position.id, alias)
        findings += _label_findings(f"{position.id}: its label", position.label)
        for scenario in position.scenarios:
            findings += _label_findings(
                f"{position.id}: its scenario {scenario.name!r}", scenario.name, sentence_case=False
            )
            findings += _heading_findings(
                f"{position.id}: its scenario {scenario.name!r}", scenario.name.casefold()
            )
        text = " ".join(
            (
                position.label,
                position.description,
                *position.aliases,
                *position.tag_keywords,
                *(scenario.name for scenario in position.scenarios),
                *_forms(position),
            )
        )
        for word in re.findall(r"[a-z]+", text.casefold()):
            if word in SCHOOL_WORDS:
                findings.append(f"{position.id}: {word!r} names a school")
    return findings


def unreachable_form_findings(taxonomy: Taxonomy) -> list[str]:
    """Every scenario form no heading normalizes to, so `v1-e32-t14`'s words can never be it."""
    findings: list[str] = []
    for position in taxonomy.positions:
        for form in _forms(position):
            normalized = normalize_heading(form)
            if (normalized.text, normalized.answer) != (form, False):
                findings.append(f"{position.id}: the form {form!r} normalizes to {normalized.text!r}")
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


def plan_text_findings(words: ResolutionalPlanWords) -> list[str]:
    """Every word of a plan-text file shaped like a team code or naming a school."""
    findings: list[str] = []
    for word in (*words.frame_words, *words.resolutional_words):
        findings += _heading_findings(f"the plan-text words of {words.topic_id}", word)
        if word in SCHOOL_WORDS:
            findings.append(f"the plan-text words of {words.topic_id}: {word!r} names a school")
    return findings


def analytic_text_findings(actors: CounterplanActors) -> list[str]:
    """Every actor phrase of an analytic-text file shaped like a team code or naming a school."""
    findings: list[str] = []
    for phrase in actors.cp_text_actors:
        findings += _heading_findings(f"the CP text actors of {actors.topic_id}", phrase)
        findings += [
            f"the CP text actors of {actors.topic_id}: {word!r} names a school"
            for word in phrase.split()
            if word in SCHOOL_WORDS
        ]
    return findings


def kritikal_aff_findings(config: KritikalAffConfig) -> list[str]:
    """Every family label or phrase of a K-aff file shaped like a team code or naming a school."""
    findings: list[str] = []
    where = f"the K families of {config.topic_id}"
    for family in config.families:
        for phrase in family.phrases:
            findings += _heading_findings(where, phrase)
        findings += [
            f"{where}: {word!r} names a school"
            for word in re.findall(r"[a-z]+", " ".join((family.label, *family.phrases)).casefold())
            if word in SCHOOL_WORDS
        ]
    return findings


def plan_mechanism_findings(words: PlanMechanismWords) -> list[str]:
    """Every plan-mechanism word shaped like a team code or naming a school, a hyphen read as a space."""
    findings: list[str] = []
    where = f"the plan-mechanism words of {words.topic_id}"
    for word in words.words:
        findings += _heading_findings(where, word.replace("-", " "))
        findings += [f"{where}: {part!r} names a school" for part in word.split("-") if part in SCHOOL_WORDS]
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
def test_every_scenario_form_is_heading_words_the_normalizer_can_produce(path: Path) -> None:
    assert unreachable_form_findings(load_taxonomy_file(path)) == []


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


@pytest.mark.parametrize("path", PLAN_TEXT_FILES, ids=lambda path: path.stem)
def test_no_plan_text_word_names_a_team_a_school_or_a_person(path: Path) -> None:
    assert plan_text_findings(load_plan_text_file(path)) == []


@pytest.mark.parametrize("path", ANALYTIC_TEXT_FILES, ids=lambda path: path.stem)
def test_no_cp_text_actor_names_a_team_a_school_or_a_person(path: Path) -> None:
    assert analytic_text_findings(load_analytic_text_file(path)) == []


@pytest.mark.parametrize("path", KRITIKAL_AFF_FILES, ids=lambda path: path.stem)
def test_no_k_family_names_a_team_a_school_or_a_person(path: Path) -> None:
    assert kritikal_aff_findings(load_kritikal_aff_file(path)) == []


@pytest.mark.parametrize("path", PLAN_MECHANISM_FILES, ids=lambda path: path.stem)
def test_no_plan_mechanism_word_names_a_team_a_school_or_a_person(path: Path) -> None:
    assert plan_mechanism_findings(load_plan_mechanism_file(path)) == []


def test_the_directory_holds_only_the_topic_map_taxonomies_overrides_plan_texts_and_release_lock() -> None:
    found = sorted(str(path.relative_to(CONFIG)) for path in CONFIG.rglob("*") if path.is_file())
    allowed = [
        TOPICS_FILE,
        RELEASED_FILE,
        *(f"{TAXONOMY_DIRECTORY}/{path.name}" for path in TAXONOMY_FILES),
        *(f"{OVERRIDE_DIRECTORY}/{path.name}" for path in OVERRIDE_FILES),
        *(f"{PLAN_TEXT_DIRECTORY}/{path.name}" for path in PLAN_TEXT_FILES),
        *(f"{ANALYTIC_TEXT_DIRECTORY}/{path.name}" for path in ANALYTIC_TEXT_FILES),
        *(f"{KRITIKAL_AFF_DIRECTORY}/{path.name}" for path in KRITIKAL_AFF_FILES),
        *(f"{PLAN_MECHANISM_DIRECTORY}/{path.name}" for path in PLAN_MECHANISM_FILES),
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
        (
            "camel initials in a scenario name",
            {"scenarios": [{"name": "Dome (RiOs)", "forms": ["dome"]}]},
            "team code",
        ),
        (
            "two capitals in a scenario name",
            {"scenarios": [{"name": "QX dome", "forms": ["dome"]}]},
            "team code",
        ),
        (
            "a team code in a lowercase name",
            {"scenarios": [{"name": "qx dome", "forms": ["dome"]}]},
            "team code",
        ),
        (
            "a school in a capitalized scenario name",
            {"scenarios": [{"name": "Crash at Sample Academy", "forms": ["crash"]}]},
            "school",
        ),
        (
            "a school in a scenario name",
            {"scenarios": [{"name": "the academy crash", "forms": ["crash"]}]},
            "school",
        ),
        ("a team code in a form", {"scenarios": [{"name": "dome", "forms": ["dome qx"]}]}, "team code"),
        ("a school in a form", {"scenarios": [{"name": "dome", "forms": ["sample high dome"]}]}, "school"),
        ("a team code in a dropped form", {"not_scenarios": ["qx too early"]}, "team code"),
        ("a school in a dropped form", {"not_scenarios": ["prep too early"]}, "school"),
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


def test_the_personal_data_check_passes_scenario_vocabulary() -> None:
    taxonomy = one_position(
        scenarios=[
            {"name": "Golden dome", "forms": ["dome", "golden dome"]},
            {"name": "AI arms race", "forms": ["ai arms race"]},
            {"name": "dem win crushes trumpism", "forms": ["dem win crushes trumpism"]},
            {"name": "War with China", "forms": ["war with china"]},
            {"name": "Golden Dome arms race", "forms": ["dome arms race"]},
        ],
        not_scenarios=["too early", "other issues"],
    )
    assert personal_data_findings(taxonomy) == []


@pytest.mark.parametrize(
    "fields",
    [{"scenarios": [{"name": "dome", "forms": ["1nc dome"]}]}, {"not_scenarios": ["a2 dome"]}],
    ids=["a speech name the normalizer takes off", "an answer marker"],
)
def test_the_form_check_refuses_a_form_no_heading_reduces_to(fields: dict[str, Any]) -> None:
    assert unreachable_form_findings(one_position(**fields)), fields


def test_the_form_check_passes_a_form_a_heading_reduces_to() -> None:
    assert (
        unreachable_form_findings(one_position(scenarios=[{"name": "dome", "forms": ["golden dome"]}])) == []
    )


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


@pytest.mark.parametrize(
    ("word", "expected"),
    [("qx", "shaped like a team code"), ("academy", "names a school")],
)
def test_the_plan_text_check_refuses(word: str, expected: str) -> None:
    words = ResolutionalPlanWords(
        topic_id="policy-sample-topic",
        position_id="sample-plan-aff",
        frame_words=("federal", "should"),
        resolutional_words=("national", word),
    )
    (finding,) = plan_text_findings(words)
    assert expected in finding


def test_the_plan_text_check_passes_debate_vocabulary() -> None:
    words = ResolutionalPlanWords(
        topic_id="policy-sample-topic",
        position_id="sample-plan-aff",
        frame_words=("federal", "should", "us"),
        resolutional_words=("national", "plan"),
    )
    assert plan_text_findings(words) == []


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [("qx states", "shaped like a team code"), ("the sample academy", "names a school")],
)
def test_the_cp_text_actor_check_refuses(phrase: str, expected: str) -> None:
    actors = CounterplanActors(topic_id="policy-sample-topic", cp_text_actors=("congress", phrase))
    (finding,) = analytic_text_findings(actors)
    assert expected in finding


def test_the_cp_text_actor_check_passes_actors() -> None:
    actors = CounterplanActors(
        topic_id="policy-sample-topic", cp_text_actors=("fifty states", "50 states", "usfg", "hhs", "cms")
    )
    assert analytic_text_findings(actors) == []


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [("qx", "shaped like a team code"), ("sample academy", "names a school")],
)
def test_the_k_family_check_refuses(phrase: str, expected: str) -> None:
    config = KritikalAffConfig(
        topic_id="policy-sample-topic",
        position_id="sample-kritikal-aff",
        families=(KritikalFamily(id="cap", label="Capitalism", phrases=("cap", phrase)),),
    )
    (finding,) = kritikal_aff_findings(config)
    assert expected in finding


def test_the_k_family_check_passes_k_vocabulary() -> None:
    config = KritikalAffConfig(
        topic_id="policy-sample-topic",
        position_id="sample-kritikal-aff",
        families=(
            KritikalFamily(id="cap", label="Capitalism", phrases=("cap", "capitalism")),
            KritikalFamily(id="settler-colonialism", label="Settler colonialism", phrases=("set col",)),
        ),
    )
    assert kritikal_aff_findings(config) == []


@pytest.mark.parametrize(
    ("word", "expected"),
    [("qx-waiver", "shaped like a team code"), ("academy-waiver", "names a school")],
)
def test_the_plan_mechanism_check_refuses(word: str, expected: str) -> None:
    words = PlanMechanismWords(topic_id="policy-sample-topic", words=("preempt", word))
    (finding,) = plan_mechanism_findings(words)
    assert expected in finding


def test_the_plan_mechanism_check_passes_mechanism_vocabulary() -> None:
    words = PlanMechanismWords(
        topic_id="policy-sample-topic", words=("preempt", "preemption", "waiver", "waive", "opt-out")
    )
    assert plan_mechanism_findings(words) == []
