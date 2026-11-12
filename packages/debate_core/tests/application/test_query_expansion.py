"""Query expansion by debate argument and need: the taxonomy, its templates and a model's extra queries.

The tests are grouped by the plan nodes' selectors: `-k taxonomy` (ac1: the file validates, every
pair has a template, an unknown choice is a typed error with the valid ones), `-k template` (ac2:
deterministic queries with their windows, recorded on the stored search) and `model` (ac3: model
expansion is off by default, appends validated queries with rationale and prompt metadata, and
falls back to the templates with a warning).

Behaviour is tested against :data:`SMALL_TAXONOMY`, written here, so the coach's edits to
`config/argument_taxonomy.yaml` never move a model fixture's key. The committed file is tested for
what it must hold whatever the coach changes, and for ac2's own example. Every expected value is
written by hand from the YAML beside it (working agreement 6).
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from debate_core.application.budget import BudgetExceededError
from debate_core.application.errors import ProviderUnavailable
from debate_core.application.federated_search import FederatedSearchService
from debate_core.application.federated_search_types import ExpansionRequest, SearchRequest, SearchState
from debate_core.application.ports.persistence import SearchRepository
from debate_core.application.query_expansion import (
    ARGUMENT_TAXONOMY_PATH,
    EXPAND_PROMPT_ID,
    EXPAND_PROMPT_VERSION,
    InvalidArgumentTaxonomy,
    QueryExpansionStage,
    UnknownExpansionChoice,
    expand_with_templates,
    load_argument_taxonomy,
    parse_argument_taxonomy,
    provider_queries,
)
from debate_core.application.structured_output import StructuredOutputGuard
from debate_core.domain import SearchFilters
from debate_core.domain.argument_taxonomy import (
    MAX_QUERIES_PER_SEARCH,
    ArgumentKind,
    ArgumentTaxonomy,
    ReviewStatus,
)
from debate_core.domain.caselist.values import Event
from debate_core.domain.model_contracts import ModelProvider, TaskClass
from debate_core.domain.search import ExpandedQuery, QueryOrigin, SearchExpansion, WindowSource
from debate_core.integrations.discovery.openalex import MAX_SEARCH_CHARS, works_requests
from debate_core.integrations.local import SqliteDatabase, SqliteSearchRepository
from debate_core.integrations.models.fake_router import FAKE_MODEL_ID, FakeModelRouter
from debate_core.integrations.models.prompt_registry import PromptRegistry
from debate_core.testing.fakes.clock_and_ids import FixedClock, SequentialIdGenerator
from debate_core.testing.fakes.model_router import ScriptedModelRouter
from debate_core.testing.fakes.persistence import InMemorySearchRepository
from debate_core.testing.fakes.providers import FakeSearchProvider

REPOSITORY = Path(__file__).resolve().parents[4]
MODEL_OUTPUTS = REPOSITORY / "tests" / "fixtures" / "model_outputs"

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
"""The clock every test reads: the day the task ran."""

SMALL_TAXONOMY = """
schema_version: 2
taxonomy_version: 0.1.0
variables:
  query: The query.
  topic: The topic.
  bill: The agenda item.
families:
  - id: test-scenario
    label: Test scenarios
    kinds: [da]
    needs:
      - {id: uniqueness, label: Uniqueness, description: Where things stand now., aliases: [uq],
         recency_days: 14}
      - {id: impact, label: Impact, description: What happens in the end., aliases: [i], recency_days: any}
  - id: test-framing
    label: Test framing
    kinds: [framework]
    needs:
      - {id: framework-good, label: Framework good, description: Why to use it., aliases: [fw-good],
         recency_days: any}
      - {id: answers, label: Answers, description: Why not., aliases: [at], recency_days: any}
arguments:
  - id: test-da
    label: Test DA
    kind: da
    formats: [POLICY]
    aliases: [tda, test]
    review: awaiting_coach_review
    templates:
      uniqueness:
        - {text: "{query} now"}
        - {text: "{bill} vote", recency_days: 7}
        - {text: "{topic} polling", recency_days: 3}
      impact:
        - {text: "{query} impact"}
        - {text: "{topic} impact"}
  - id: test-framework
    label: Test framework
    kind: framework
    formats: [LD]
    review: awaiting_coach_review
    templates:
      framework-good:
        - {text: "{topic} framework good"}
      answers:
        - {text: "framework critique"}
topics:
  - {id: test-topic, format: POLICY, review: awaiting_coach_review, variables: {topic: preset subject}}
"""


def small_taxonomy(**changes: Any) -> dict[str, Any]:
    """SMALL_TAXONOMY as a mapping, with top-level keys replaced."""
    document: dict[str, Any] = yaml.safe_load(SMALL_TAXONOMY)
    document.update(changes)
    return document


def parsed(document: dict[str, Any]) -> ArgumentTaxonomy:
    return parse_argument_taxonomy(yaml.safe_dump(document), source="test taxonomy")


def first_argument_with(**changes: Any) -> dict[str, Any]:
    """SMALL_TAXONOMY with its first argument changed."""
    document = small_taxonomy()
    document["arguments"][0].update(changes)
    return document


def framework_with(**templates: list[dict[str, Any]]) -> dict[str, Any]:
    """SMALL_TAXONOMY with the framing argument's templates replaced."""
    document = small_taxonomy()
    document["arguments"][1]["templates"] = templates
    return document


def family_with(index: int, **changes: Any) -> dict[str, Any]:
    """SMALL_TAXONOMY with one family changed."""
    document = small_taxonomy()
    document["families"][index].update(changes)
    return document


def need_with(family: int, need: int, **changes: Any) -> dict[str, Any]:
    """SMALL_TAXONOMY with one need of one family changed."""
    document = small_taxonomy()
    document["families"][family]["needs"][need].update(changes)
    return document


def topic_with(**changes: Any) -> dict[str, Any]:
    """SMALL_TAXONOMY with `country` declared and its topic preset changed."""
    document = small_taxonomy()
    document["variables"]["country"] = "The country."
    document["topics"][0].update(changes)
    return document


def plan_mechanism(name: str, phrase: str | None = None) -> dict[str, str]:
    return {"landscape_id": f"{name}-aff", "label": name.capitalize(), "phrase": phrase or f"{name} plan"}


def mechanism_taxonomy() -> dict[str, Any]:
    """SMALL_TAXONOMY with a link need for its DA family, an advantage in that family, a topic naming
    two plan mechanisms (the second already naming the country) and a topic naming none."""
    document = topic_with(
        variables={"topic": "preset subject", "country": "Testland"},
        mechanisms=[plan_mechanism("alpha"), plan_mechanism("beta", "beta plan in Testland")],
    )
    document["topics"].append(
        {
            "id": "bare-topic",
            "format": "POLICY",
            "review": "awaiting_coach_review",
            "variables": {"topic": "bare"},
        }
    )
    family = document["families"][0]
    family["kinds"] = ["da", "advantage"]
    family["needs"].append(
        {"id": "link", "label": "Link", "description": "How it starts.", "aliases": ["l"], "recency_days": 30}
    )
    document["arguments"][0]["templates"]["link"] = [
        {"text": "{bill} link"},
        {"text": "{query} link", "recency_days": 90},
        {"text": "{topic} second link"},
    ]
    document["arguments"].append(
        {
            "id": "test-advantage",
            "label": "Test advantage",
            "kind": "advantage",
            "formats": ["POLICY"],
            "review": "awaiting_coach_review",
            "templates": {
                "uniqueness": [{"text": "{query} now"}],
                "impact": [{"text": "{query} impact"}],
                "link": [{"text": "{query} link"}],
            },
        }
    )
    return document


TAXONOMY = parse_argument_taxonomy(SMALL_TAXONOMY, source="SMALL_TAXONOMY")


@pytest.fixture(scope="module")
def committed() -> ArgumentTaxonomy:
    return load_argument_taxonomy(REPOSITORY / ARGUMENT_TAXONOMY_PATH)


@pytest.fixture(scope="module")
def mechanisms() -> ArgumentTaxonomy:
    return parsed(mechanism_taxonomy())


@pytest.fixture(scope="module")
def prompts() -> PromptRegistry:
    return PromptRegistry.load(REPOSITORY / "prompts")


def request_for(
    query: str = "community clinic funding",
    *,
    argument: str = "test-da",
    need: str = "uniqueness",
    filters: SearchFilters | None = None,
    **expansion: Any,
) -> SearchRequest:
    return SearchRequest(
        query=query,
        filters=SearchFilters() if filters is None else filters,
        expansion=ExpansionRequest(argument=argument, need=need, **expansion),
    )


def expand(request: SearchRequest, taxonomy: ArgumentTaxonomy = TAXONOMY) -> SearchExpansion:
    return expand_with_templates(taxonomy, request, now=NOW)


def run_stage(stage: QueryExpansionStage, request: SearchRequest) -> SearchState:
    return asyncio.run(stage.run(SearchState.start("0SRCH000000000000000000001", request)))


def template_query(
    text: str,
    template_id: str,
    template: str,
    *,
    days: int | None,
    window: WindowSource,
    since: datetime | None,
) -> ExpandedQuery:
    return ExpandedQuery(
        query=text,
        origin=QueryOrigin.TEMPLATE,
        template_id=template_id,
        template=template,
        since=since,
        recency_days=days,
        window=window,
    )


# =============================================================================================
# The taxonomy (ac1)
# =============================================================================================


FAMILY_NEEDS = {
    "da-and-advantage": ["uniqueness", "link", "internal-link", "impact", "answers"],
    "framing": ["framework-good", "answers"],
    "theory": ["interpretation", "standards", "voters", "answers"],
    "counterplan": ["solvency", "net-benefit", "competition", "answers"],
    "kritik": ["link", "impact", "alternative", "framework", "answers"],
}
"""Each family's needs in order: the PM's list of 2026-11-02, from the coach's review of v1-e08-t04."""

KIND_FAMILY = {
    "da": "da-and-advantage",
    "advantage": "da-and-advantage",
    "framework": "framing",
    "theory": "theory",
    "cp": "counterplan",
    "k": "kritik",
}

ADDED_COUNTERPLANS = {"process-cp", "states-cp", "courts-cp", "delay-cp", "advantage-cp"}
"""The Policy landscape's counterplans that are not about the NHI topic's mechanism (v1-e08-t08)."""

ADDED_KRITIKS = {
    "cap-k",
    "racial-capitalism-k",
    "security-k",
    "biopolitics-k",
    "settler-colonialism-k",
    "colonialism-k",
    "antiblackness-k",
    "psychoanalysis-k",
    "queer-k",
    "buddhism-k",
}
"""generic.yaml's named kritiks; generic-k, its catch-all for a card that fits none, is not an argument."""

COACH_REVIEWED_FILE = (
    REPOSITORY / "packages/debate_core/tests/fixtures/argument_taxonomy/coach_reviewed_1_5_0.yaml"
)


def test_the_committed_taxonomy_validates_and_every_argument_has_a_template_for_each_need_of_its_family(
    committed: ArgumentTaxonomy,
) -> None:
    assert committed.taxonomy_version == "1.6.0"
    assert {family.id: [need.id for need in family.needs] for family in committed.families} == FAMILY_NEEDS
    for argument in committed.arguments:
        family = committed.family_of(argument)
        assert family.id == KIND_FAMILY[argument.kind.value], argument.id
        assert list(argument.templates) == FAMILY_NEEDS[family.id], argument.id
        for need in FAMILY_NEEDS[family.id]:
            assert argument.templates[need], f"{argument.id}/{need}"


def test_the_committed_taxonomy_puts_the_frameworks_in_framing_and_theory_in_its_own_family(
    committed: ArgumentTaxonomy,
) -> None:
    def family(argument_id: str) -> str:
        found = committed.find_argument(argument_id)
        assert found is not None, argument_id
        return committed.family_of(found).id

    assert [family(name) for name in ("util", "deontology", "structural-violence", "cost-benefit")] == [
        "framing"
    ] * 4
    assert family("theory") == "theory"


def test_the_committed_taxonomy_gives_framing_evidence_no_window(committed: ArgumentTaxonomy) -> None:
    """Philosophy evidence doesn't go stale (the coach, 2026-11-02): no framing need or template has a
    window."""
    framing = next(family for family in committed.families if family.id == "framing")
    assert [(need.id, need.recency_days) for need in framing.needs] == [
        ("framework-good", "any"),
        ("answers", "any"),
    ]
    for argument in committed.arguments:
        if committed.family_of(argument).id == "framing":
            for need, templates in argument.templates.items():
                assert [t.recency_days for t in templates] == [None] * len(templates), f"{argument.id}/{need}"


def landscape_kinds() -> dict[str, str]:
    kinds: dict[str, str] = {}
    for path in sorted((REPOSITORY / "config" / "landscape" / "taxonomies").glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        kinds.update({position["id"]: position["kind"] for position in document["positions"]})
    return kinds


def test_the_committed_taxonomy_adds_the_landscapes_generic_counterplans_and_kritiks_under_its_ids(
    committed: ArgumentTaxonomy,
) -> None:
    by_kind = {
        kind: {argument.id for argument in committed.arguments if argument.kind.value == kind}
        for kind in ("cp", "k")
    }
    assert by_kind == {"cp": ADDED_COUNTERPLANS, "k": ADDED_KRITIKS}
    kinds = landscape_kinds()
    for argument in committed.arguments:
        if argument.id in ADDED_COUNTERPLANS | ADDED_KRITIKS:
            assert kinds.get(argument.id) == argument.kind.value, argument.id
            assert argument.landscape_id == argument.id, argument.id
            assert argument.formats == (Event.POLICY,), argument.id
    assert committed.find_argument("federalism-cp") is None
    assert committed.find_argument("free-market-cp") is None


def test_the_committed_taxonomy_keeps_every_coach_reviewed_entry_as_he_reviewed_it(
    committed: ArgumentTaxonomy,
) -> None:
    """The coach's reviewed entries (1.1.0's nine, the three he approved on 2026-11-02 and the seventeen
    he approved on 2026-11-04, and the six de-extinction arguments he approved on 2026-11-05: every
    argument) and the DA and advantage needs' windows are unchanged; an
    entry added or reshaped later waits for his review."""
    reviewed_file = yaml.safe_load(COACH_REVIEWED_FILE.read_text(encoding="utf-8"))
    reviewed = {
        entry["id"]: entry for entry in reviewed_file["arguments"] if entry["review"] == "coach_reviewed"
    }
    assert len(reviewed) == 35
    for argument in committed.arguments:
        entry = reviewed.get(argument.id)
        if entry is None:
            assert argument.review is ReviewStatus.AWAITING_COACH_REVIEW, argument.id
            continue
        assert argument.review is ReviewStatus.COACH_REVIEWED, argument.id
        assert argument.model_dump(mode="json", exclude_none=True) == entry, argument.id
    assert {argument.id for argument in committed.arguments} >= set(reviewed)
    scenario = next(family for family in committed.families if family.id == "da-and-advantage")
    assert [need.model_dump(mode="json", exclude_defaults=True) for need in scenario.needs] == [
        {key: value for key, value in need.items() if value != []}
        for need in next(
            family for family in reviewed_file["families"] if family["id"] == "da-and-advantage"
        )["needs"]
    ]


def test_the_committed_taxonomy_covers_policy_ld_and_pf(committed: ArgumentTaxonomy) -> None:
    ids = {argument.id for argument in committed.arguments}
    assert {"politics-da", "midterms-da", "economy-da", "spending-da", "federalism-da", "heg"} <= ids
    assert {"util", "deontology", "structural-violence", "theory"} <= ids
    by_format = {event: [a.id for a in committed.arguments if event in a.formats] for event in Event}
    assert by_format[Event.POLICY] and by_format[Event.LD] and by_format[Event.PF]
    for argument in committed.arguments:
        if argument.formats == (Event.PF,):
            assert argument.note is not None and "coach" in argument.note, argument.id


def test_the_committed_taxonomy_names_no_year_and_no_harms(committed: ArgumentTaxonomy) -> None:
    """No template hard-codes a dated event, and no label or template uses "harms" (the coach's ruling)."""
    for argument in committed.arguments:
        for need, templates in argument.templates.items():
            for template in templates:
                assert not re.search(r"\d{4}", template.text), f"{argument.id}/{need}: {template.text}"
                assert "harm" not in template.text.casefold(), f"{argument.id}/{need}: {template.text}"
    needs = [need for family in committed.families for need in family.needs]
    labels = [need.label for need in needs] + [argument.label for argument in committed.arguments]
    assert not [label for label in labels if "harm" in label.casefold()]


def landscape_position_ids() -> set[str]:
    ids: set[str] = set()
    for path in sorted((REPOSITORY / "config" / "landscape" / "taxonomies").glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        ids.update(position["id"] for position in document["positions"])
    return ids


def test_the_committed_taxonomy_shares_the_landscape_ids_it_maps(committed: ArgumentTaxonomy) -> None:
    """An argument the landscape also counts has the landscape's id and says so; no mapping dangles."""
    landscape = landscape_position_ids()
    assert {"politics-da", "midterms-da", "economy-da", "federalism-da"} <= landscape
    for argument in committed.arguments:
        if argument.id in landscape:
            assert argument.landscape_id == argument.id, argument.id
        if argument.landscape_id is not None:
            assert argument.landscape_id in landscape, argument.id


def test_the_committed_taxonomy_takes_topic_presets_word_for_word_from_committed_resolutions(
    committed: ArgumentTaxonomy,
) -> None:
    topics = yaml.safe_load((REPOSITORY / "config" / "landscape" / "topics.yaml").read_text(encoding="utf-8"))
    resolutions = {topic["id"]: topic.get("resolution") for topic in topics["topics"]}
    assert [topic.id for topic in committed.topics] == ["policy-2026-27-nhi", "ld-2026-nov-dec-de-extinction"]
    for topic in committed.topics:
        resolution = resolutions[topic.id]
        assert resolution is not None, f"{topic.id} has no committed resolution to take values from"
        flat = " ".join(resolution.casefold().split())
        for value in topic.variables.values():
            assert " ".join(value.casefold().split()) in flat, f"{topic.id}: {value}"


def test_the_committed_taxonomy_nhi_topic_names_four_landscape_aff_mechanisms_the_coach_reviewed(
    committed: ArgumentTaxonomy,
) -> None:
    """The PM's ruling on v1-e08-t14: the four mechanisms, in order, each an aff position of the topic's
    landscape taxonomy under its own label, searched with that label or one of the coach's tag keywords.
    The coach approved the four and the anchor rule on 2026-11-04 (v1-e08-t14's ac1)."""
    topic = next(topic for topic in committed.topics if topic.id == "policy-2026-27-nhi")
    assert topic.review is ReviewStatus.COACH_REVIEWED
    assert topic.variables == {"topic": "national health insurance", "country": "United States"}
    assert [(mechanism.landscape_id, mechanism.phrase) for mechanism in topic.mechanisms] == [
        ("single-payer-aff", "single payer"),
        ("medicare-for-all-aff", "Medicare for All"),
        ("public-option-aff", "public option"),
        ("aca-reform-aff", "Affordable Care Act"),
    ]
    landscape_file = REPOSITORY / "config" / "landscape" / "taxonomies" / f"{topic.id}.yaml"
    positions = {
        position["id"]: position
        for position in yaml.safe_load(landscape_file.read_text(encoding="utf-8"))["positions"]
    }
    for mechanism in topic.mechanisms:
        position = positions.get(mechanism.landscape_id)
        assert position is not None, mechanism.landscape_id
        assert (position["kind"], position["side"], position["label"]) == ("aff", "aff", mechanism.label)
        assert not position.get("deprecated", False), mechanism.landscape_id
        words = {position["label"].casefold(), *position.get("tag_keywords", [])}
        assert mechanism.phrase.casefold() in words, mechanism.landscape_id


def test_the_committed_taxonomy_resolves_the_spec_spellings_and_typed_variants(
    committed: ArgumentTaxonomy,
) -> None:
    def argument(name: str) -> str | None:
        found = committed.find_argument(name)
        return None if found is None else found.id

    def need(name: str, argument_id: str = "politics-da") -> str | None:
        found_argument = committed.find_argument(argument_id)
        assert found_argument is not None
        found = committed.find_need(found_argument, name)
        return None if found is None else found.id

    assert argument("ptx") == "politics-da"
    assert argument("Politics DA") == "politics-da"
    assert argument("econ-da") == "economy-da"
    assert argument("elections") == "midterms-da"
    assert need("AT") == "answers"
    assert need("internal link") == "internal-link"
    assert need("uq") == "uniqueness"
    assert need("Framework good", "util") == "framework-good"
    assert need("AT", "util") == "answers"
    assert need("interp", "theory") == "interpretation"
    assert need("net benefit", "process-cp") == "net-benefit"
    assert need("NB", "states-cp") == "net-benefit"
    assert need("alt", "cap-k") == "alternative"
    assert need("FW", "cap-k") == "framework"
    assert need("link", "cap-k") == "link"
    assert need("uq", "util") is None


@pytest.mark.parametrize(
    ("document", "words"),
    [
        pytest.param(
            first_argument_with(templates={"uniqueness": [{"text": "{query} now"}]}),
            ["argument test-da has no template for the need impact"],
            id="a need with no templates",
        ),
        pytest.param(
            first_argument_with(templates={"uniqueness": [{"text": "{query} now"}], "impact": []}),
            ["argument test-da has no template for the need impact"],
            id="a need with an empty template list",
        ),
        pytest.param(
            first_argument_with(
                templates={
                    "uniqueness": [{"text": "{query} now"}],
                    "impact": [{"text": "{query} impact"}],
                    "solvency": [{"text": "{query} solves"}],
                }
            ),
            ["solvency", "not a need"],
            id="templates for a need the file does not list",
        ),
        pytest.param(
            first_argument_with(
                templates={
                    "uniqueness": [{"text": "{query} now"}, {"text": "{agenda} vote"}],
                    "impact": [{"text": "{query} impact"}],
                }
            ),
            ["test-da/uniqueness", "'{agenda} vote' names agenda, which variables does not declare"],
            id="a template naming an undeclared variable",
        ),
        pytest.param(
            first_argument_with(
                templates={"uniqueness": [{"text": "{bill} vote"}], "impact": [{"text": "{query} x"}]}
            ),
            ["test-da/uniqueness", "query and topic"],
            id="a pair whose every template needs an optional variable",
        ),
        pytest.param(
            first_argument_with(
                templates={"uniqueness": [{"text": "{0} now"}], "impact": [{"text": "{query} x"}]}
            ),
            ["{0}"],
            id="a positional field",
        ),
        pytest.param(
            first_argument_with(
                templates={"uniqueness": [{"text": "{query:>9}"}], "impact": [{"text": "{query} x"}]}
            ),
            ["{query}"],
            id="a format spec",
        ),
        pytest.param(
            first_argument_with(
                templates={"uniqueness": [{"text": "{query"}], "impact": [{"text": "{query} x"}]}
            ),
            ["not valid"],
            id="an unclosed brace",
        ),
        pytest.param(
            first_argument_with(aliases=["test-framework"]), ["test-framework"], id="an alias that is an id"
        ),
        pytest.param(
            first_argument_with(landscape_id="politics-da"),
            ["landscape_id"],
            id="a landscape id unlike the id",
        ),
        pytest.param(first_argument_with(id="Test DA"), ["lower-case id"], id="an id that is not a slug"),
        pytest.param(
            first_argument_with(
                templates={"uniqueness": [{"text": "{query} now", "recency_days": 0}], "impact": []}
            ),
            ["recency_days"],
            id="a window of zero days",
        ),
        pytest.param(
            small_taxonomy(taxonomy_version="1.0"), ["MAJOR.MINOR.PATCH"], id="a version without patch"
        ),
        pytest.param(small_taxonomy(variables={"query": "q"}), ["topic"], id="topic not declared"),
        pytest.param(
            small_taxonomy(
                topics=[
                    {
                        "id": "t",
                        "format": "LD",
                        "review": "awaiting_coach_review",
                        "variables": {"query": "x"},
                    }
                ]
            ),
            ["query"],
            id="a topic setting query",
        ),
        pytest.param(small_taxonomy(unexpected=1), ["unexpected"], id="an unknown key"),
        pytest.param(small_taxonomy(schema_version=1), ["schema_version"], id="the old schema version"),
        pytest.param(
            framework_with(
                **{
                    "framework-good": [{"text": "{query} good"}],
                    "answers": [{"text": "{query} bad"}],
                    "uniqueness": [{"text": "{query} now"}],
                }
            ),
            [
                "test-framework",
                "uniqueness",
                "not a need of the test-framing family",
                "framework-good, answers",
            ],
            id="a framework given a uniqueness need",
        ),
        pytest.param(
            framework_with(**{"framework-good": [{"text": "{query} good"}], "answers": []}),
            ["argument test-framework has no template for the need answers"],
            id="a framing pair left empty",
        ),
        pytest.param(
            framework_with(**{"framework-good": [{"text": "{query} good"}]}),
            ["argument test-framework has no template for the need answers"],
            id="a framing pair left out",
        ),
        pytest.param(
            family_with(1, kinds=["framework", "da"]),
            ["two families take the kind da"],
            id="a kind in two families",
        ),
        pytest.param(
            first_argument_with(kind="cp"),
            ["argument test-da is a cp, which no family takes"],
            id="a kind no family takes",
        ),
        pytest.param(family_with(1, needs=[]), ["families.1.needs"], id="a family with no needs"),
        pytest.param(family_with(1, kinds=[]), ["families.1.kinds"], id="a family with no kinds"),
        pytest.param(
            family_with(1, id="test-scenario"),
            ["two families share the id test-scenario"],
            id="a family id twice",
        ),
        pytest.param(
            need_with(0, 1, aliases=["uq"]),
            ["two needs of the test-scenario family share the id or alias uq"],
            id="two needs of a family sharing a name",
        ),
        pytest.param(
            family_with(
                1,
                needs=[
                    {"id": "framework-good", "label": "Good", "description": "Why.", "recency_days": "any"},
                    {"id": "framework-good", "label": "Again", "description": "Why.", "recency_days": "any"},
                ],
            )
            | {
                "arguments": [
                    small_taxonomy()["arguments"][0],
                    {
                        **small_taxonomy()["arguments"][1],
                        "templates": {"framework-good": [{"text": "{query}"}]},
                    },
                ]
            },
            ["two needs of the test-framing family share the id or alias framework-good"],
            id="two needs of a family with one id",
        ),
        pytest.param(
            need_with(1, 0, aliases=["i"]),
            ["i means impact in test-scenario and framework-good in test-framing"],
            id="one name meaning two needs",
        ),
        pytest.param(
            topic_with(mechanisms=[plan_mechanism("alpha")]),
            ["topic test-topic names plan mechanisms, so it sets country"],
            id="plan mechanisms and no country",
        ),
        pytest.param(
            topic_with(variables={"country": "Testland"}, mechanisms=[plan_mechanism("alpha")]),
            ["topic test-topic names plan mechanisms, so it sets topic"],
            id="plan mechanisms and no topic",
        ),
        pytest.param(
            topic_with(
                variables={"topic": "preset subject", "country": "Testland"},
                mechanisms=[plan_mechanism("alpha"), plan_mechanism("alpha", "other words")],
            ),
            ["two plan mechanisms of topic test-topic share the landscape id alpha-aff"],
            id="two plan mechanisms with one landscape id",
        ),
        pytest.param(
            topic_with(
                variables={"topic": "preset subject", "country": "Testland"},
                mechanisms=[plan_mechanism("alpha"), plan_mechanism("beta", "Alpha  Plan")],
            ),
            ["two plan mechanisms of topic test-topic share the phrase alpha plan"],
            id="two plan mechanisms with one phrase",
        ),
        pytest.param(
            topic_with(
                variables={"topic": "preset subject", "country": "Testland"},
                mechanisms=[plan_mechanism("alpha", "alpha plan 3069")],
            ),
            ["topic test-topic: the phrase 'alpha plan 3069' has a digit", "names a mechanism in words"],
            id="a plan mechanism phrase with a digit",
        ),
        pytest.param(
            topic_with(review=None),
            ["topics.0.review"],
            id="a topic with no review status",
        ),
    ],
)
def test_a_taxonomy_that_breaks_a_rule_is_refused_when_it_loads(
    document: dict[str, Any], words: list[str]
) -> None:
    with pytest.raises(InvalidArgumentTaxonomy) as refused:
        parsed(document)
    message = str(refused.value)
    assert message.startswith("test taxonomy")
    for word in words:
        assert word in message


def test_a_taxonomy_file_that_is_not_yaml_or_cannot_be_read_is_refused(tmp_path: Path) -> None:
    with pytest.raises(InvalidArgumentTaxonomy, match="is not valid YAML"):
        parse_argument_taxonomy("needs: [", source="broken.yaml")
    with pytest.raises(InvalidArgumentTaxonomy, match="must be a mapping"):
        parse_argument_taxonomy("- a list", source="list.yaml")
    with pytest.raises(InvalidArgumentTaxonomy, match="could not be read"):
        load_argument_taxonomy(tmp_path / "missing.yaml")


def choices_of(expansion: dict[str, Any]) -> dict[str, Any]:
    return {"argument": "test-da", "need": "uniqueness"} | expansion


@pytest.mark.parametrize(
    ("expansion", "kind", "value", "choices"),
    [
        pytest.param({"argument": "heg"}, "argument", "heg", ("test-da", "test-framework"), id="argument"),
        pytest.param({"topic_id": "ld-topic"}, "topic", "ld-topic", ("test-topic",), id="topic"),
        pytest.param({"variables": {"agenda": "x"}}, "variable", "agenda", ("topic", "bill"), id="variable"),
    ],
)
def test_the_taxonomy_refuses_an_unknown_choice_with_a_typed_error_listing_the_valid_ones(
    expansion: dict[str, Any], kind: str, value: str, choices: tuple[str, ...]
) -> None:
    with pytest.raises(UnknownExpansionChoice) as refused:
        expand(
            SearchRequest(query="clinics", expansion=ExpansionRequest.model_validate(choices_of(expansion)))
        )
    assert (refused.value.kind, refused.value.value, refused.value.choices) == (kind, value, choices)
    assert str(refused.value) == f"unknown {kind} {value!r}; the {kind}s are: {', '.join(choices)}"


@pytest.mark.parametrize(
    ("argument", "need", "choices"),
    [
        pytest.param("test-da", "solvency", ("uniqueness", "impact"), id="a need no family has"),
        pytest.param(
            "test-framework", "uniqueness", ("framework-good", "answers"), id="another family's need"
        ),
        pytest.param("test-da", "at", ("uniqueness", "impact"), id="another family's alias"),
    ],
)
def test_the_taxonomy_refuses_a_need_outside_the_arguments_family_listing_its_needs(
    argument: str, need: str, choices: tuple[str, ...]
) -> None:
    with pytest.raises(UnknownExpansionChoice) as refused:
        expand(request_for(argument=argument, need=need))
    assert (refused.value.kind, refused.value.value, refused.value.choices) == ("need", need, choices)
    assert refused.value.argument == argument
    assert str(refused.value) == f"{argument} has no need {need!r}; its needs are: {', '.join(choices)}"


@pytest.mark.parametrize(
    ("argument", "need", "choices"),
    [
        ("util", "uniqueness", ("framework-good", "answers")),
        ("deontology", "internal-link", ("framework-good", "answers")),
        ("theory", "link", ("interpretation", "standards", "voters", "answers")),
        ("process-cp", "uniqueness", ("solvency", "net-benefit", "competition", "answers")),
        ("cap-k", "solvency", ("link", "impact", "alternative", "framework", "answers")),
        ("politics-da", "alternative", ("uniqueness", "link", "internal-link", "impact", "answers")),
    ],
)
def test_the_taxonomy_committed_refuses_each_familys_outside_needs(
    committed: ArgumentTaxonomy, argument: str, need: str, choices: tuple[str, ...]
) -> None:
    with pytest.raises(UnknownExpansionChoice) as refused:
        expand(request_for(argument=argument, need=need), committed)
    assert refused.value.choices == choices


def test_the_taxonomy_framing_expansion_sets_no_window(committed: ArgumentTaxonomy) -> None:
    for need in ("framework-good", "answers"):
        expansion = expand(request_for("de-extinction", argument="util", need=need), committed)
        assert expansion.queries, need
        assert {(q.since, q.recency_days, q.window) for q in expansion.queries} == {
            (None, None, WindowSource.NEED)
        }, need


def test_the_taxonomy_expands_counterplan_and_kritik_needs(committed: ArgumentTaxonomy) -> None:
    for argument, need in (("states-cp", "net benefit"), ("cap-k", "alt"), ("theory", "voters")):
        expansion = expand(request_for("health insurance", argument=argument, need=need), committed)
        assert expansion.argument == argument
        assert expansion.queries, f"{argument}/{need}"


def test_the_taxonomy_refuses_an_unknown_argument_before_any_provider_is_asked() -> None:
    provider = FakeSearchProvider("openalex")
    service = service_over(provider, QueryExpansionStage(TAXONOMY, clock=FixedClock(NOW)))
    with pytest.raises(UnknownExpansionChoice):
        asyncio.run(service.search(request_for(argument="politics-da")))
    assert provider.queries == []


def test_the_taxonomy_resolves_aliases_and_typed_spellings_of_its_ids() -> None:
    by_alias = expand(request_for(argument="TDA", need="UQ"))
    by_spelling = expand(request_for(argument="Test DA", need=" uniqueness "))
    assert (by_alias.argument, by_alias.need) == ("test-da", "uniqueness")
    assert by_spelling == by_alias


# =============================================================================================
# Template expansion (ac2)
# =============================================================================================


def test_template_expansion_of_politics_da_link_on_health_insurance(committed: ArgumentTaxonomy) -> None:
    """ac2's example, from config/argument_taxonomy.yaml's politics-da link templates.

    The coach's review of 2026-11-02 (taxonomy 1.1.0) gave links a five-year window, the need's own
    default, and added the four party-popularity templates.
    """
    expansion = expand(request_for("health insurance", argument="politics-da", need="link"), committed)
    since = NOW - timedelta(days=1826)
    assert expansion == SearchExpansion(
        taxonomy_version="1.6.0",
        argument="politics-da",
        need="link",
        variables={"query": "health insurance", "topic": "health insurance"},
        queries=(
            template_query(
                "health insurance political capital",
                "politics-da/link/1",
                "{query} political capital",
                days=1826,
                window=WindowSource.NEED,
                since=since,
            ),
            template_query(
                "health insurance partisan fight Congress",
                "politics-da/link/2",
                "{query} partisan fight Congress",
                days=1826,
                window=WindowSource.NEED,
                since=since,
            ),
            template_query(
                "health insurance unpopular with voters",
                "politics-da/link/3",
                "{query} unpopular with voters",
                days=1826,
                window=WindowSource.NEED,
                since=since,
            ),
            template_query(
                "health insurance popular with Republicans",
                "politics-da/link/4",
                "{query} popular with Republicans",
                days=1826,
                window=WindowSource.NEED,
                since=since,
            ),
            template_query(
                "health insurance unpopular with Republicans",
                "politics-da/link/5",
                "{query} unpopular with Republicans",
                days=1826,
                window=WindowSource.NEED,
                since=since,
            ),
            template_query(
                "health insurance popular with Democrats",
                "politics-da/link/6",
                "{query} popular with Democrats",
                days=1826,
                window=WindowSource.NEED,
                since=since,
            ),
            template_query(
                "health insurance unpopular with Democrats",
                "politics-da/link/7",
                "{query} unpopular with Democrats",
                days=1826,
                window=WindowSource.NEED,
                since=since,
            ),
        ),
    )


def test_template_expansion_is_deterministic(committed: ArgumentTaxonomy) -> None:
    request = request_for("health insurance", argument="ptx", need="link")
    assert expand(request, committed) == expand(request, committed)


def test_template_window_set_by_a_template_replaces_the_needs_default() -> None:
    """uniqueness defaults to 14 days; `{topic} polling` sets 3, and `{bill} vote` 7."""
    expansion = expand(request_for(variables={"bill": "clinic appropriations"}))
    assert [(q.query, q.since, q.recency_days, q.window) for q in expansion.queries] == [
        ("community clinic funding now", NOW - timedelta(days=14), 14, WindowSource.NEED),
        ("clinic appropriations vote", NOW - timedelta(days=7), 7, WindowSource.TEMPLATE),
        ("community clinic funding polling", NOW - timedelta(days=3), 3, WindowSource.TEMPLATE),
    ]


def test_template_window_of_any_age_sets_no_since() -> None:
    expansion = expand(request_for(need="impact", topic_id="test-topic"))
    assert [(q.query, q.since, q.recency_days, q.window) for q in expansion.queries] == [
        ("community clinic funding impact", None, None, WindowSource.NEED),
        ("preset subject impact", None, None, WindowSource.NEED),
    ]


def test_template_window_keeps_the_searchs_own_since() -> None:
    since = datetime(2026, 1, 1, tzinfo=UTC)
    expansion = expand(request_for(filters=SearchFilters(since=since)))
    assert [(q.since, q.recency_days, q.window) for q in expansion.queries] == [
        (since, 14, WindowSource.REQUEST),
        (since, 3, WindowSource.REQUEST),
    ]


def test_template_window_counts_back_from_the_searchs_until() -> None:
    until = datetime(2026, 6, 30, tzinfo=UTC)
    expansion = expand(request_for(filters=SearchFilters(until=until)))
    assert [q.since for q in expansion.queries] == [until - timedelta(days=14), until - timedelta(days=3)]


def test_template_naming_a_variable_the_search_lacks_is_skipped_and_recorded() -> None:
    expansion = expand(request_for())
    assert [q.template_id for q in expansion.queries] == ["test-da/uniqueness/1", "test-da/uniqueness/3"]
    assert expansion.skipped_templates == ("test-da/uniqueness/2",)


def test_template_topic_comes_from_the_request_then_the_preset_then_the_query() -> None:
    def polling(**expansion: Any) -> str:
        return expand(request_for(**expansion)).queries[-1].query

    assert polling(topic_id="test-topic", variables={"topic": "typed topic"}) == "typed topic polling"
    assert polling(topic_id="test-topic") == "preset subject polling"
    assert polling() == "community clinic funding polling"


def test_template_renderings_that_coincide_are_asked_once() -> None:
    """With no topic, `{query} impact` and `{topic} impact` are the same query."""
    expansion = expand(request_for(need="impact"))
    assert [q.query for q in expansion.queries] == ["community clinic funding impact"]


def test_template_variables_cannot_set_the_query() -> None:
    with pytest.raises(ValidationError, match="cannot set query"):
        ExpansionRequest(argument="test-da", need="link", variables={"query": "other"})


def test_template_stage_leaves_a_search_without_an_argument_unchanged() -> None:
    state = SearchState.start("0SRCH000000000000000000001", SearchRequest(query="as typed"))
    after = asyncio.run(QueryExpansionStage(TAXONOMY, clock=FixedClock(NOW)).run(state))
    assert after is state


# A DA's link on a topic's plan mechanisms (v1-e08-t14) ---------------------------------------

NHI = "policy-2026-27-nhi"
RESOLUTION = "national health insurance"
LINK_SINCE = NOW - timedelta(days=1826)


def nhi_link(query: str = RESOLUTION, argument: str = "politics-da", **expansion: Any) -> SearchRequest:
    return request_for(query, argument=argument, need="link", topic_id=NHI, **expansion)


NHI_SUBJECTS = (
    "resolution",
    "single-payer-aff",
    "medicare-for-all-aff",
    "public-option-aff",
    "aca-reform-aff",
)
"""The subjects every crossed template is asked on: the resolution's words, then the four mechanisms."""

NHI_POLITICS_CROSSED = [
    # The coach's own wording (2026-11-11), a crossing-only template of the NHI preset.
    (
        "national health insurance costs political capital Congress United States",
        "politics-da/link/policy-2026-27-nhi-1/resolution",
        "{query} costs political capital Congress",
    ),
    (
        "single payer costs political capital Congress United States",
        "politics-da/link/policy-2026-27-nhi-1/single-payer-aff",
        "{query} costs political capital Congress",
    ),
    (
        "Medicare for All costs political capital Congress United States",
        "politics-da/link/policy-2026-27-nhi-1/medicare-for-all-aff",
        "{query} costs political capital Congress",
    ),
    (
        "public option costs political capital Congress United States",
        "politics-da/link/policy-2026-27-nhi-1/public-option-aff",
        "{query} costs political capital Congress",
    ),
    (
        "Affordable Care Act costs political capital Congress United States",
        "politics-da/link/policy-2026-27-nhi-1/aca-reform-aff",
        "{query} costs political capital Congress",
    ),
    # Link template 2.
    (
        "national health insurance partisan fight Congress United States",
        "politics-da/link/2/resolution",
        "{query} partisan fight Congress",
    ),
    (
        "single payer partisan fight Congress United States",
        "politics-da/link/2/single-payer-aff",
        "{query} partisan fight Congress",
    ),
    (
        "Medicare for All partisan fight Congress United States",
        "politics-da/link/2/medicare-for-all-aff",
        "{query} partisan fight Congress",
    ),
    (
        "public option partisan fight Congress United States",
        "politics-da/link/2/public-option-aff",
        "{query} partisan fight Congress",
    ),
    (
        "Affordable Care Act partisan fight Congress United States",
        "politics-da/link/2/aca-reform-aff",
        "{query} partisan fight Congress",
    ),
    # Link template 4.
    (
        "national health insurance popular with Republicans United States",
        "politics-da/link/4/resolution",
        "{query} popular with Republicans",
    ),
    (
        "single payer popular with Republicans United States",
        "politics-da/link/4/single-payer-aff",
        "{query} popular with Republicans",
    ),
    (
        "Medicare for All popular with Republicans United States",
        "politics-da/link/4/medicare-for-all-aff",
        "{query} popular with Republicans",
    ),
    (
        "public option popular with Republicans United States",
        "politics-da/link/4/public-option-aff",
        "{query} popular with Republicans",
    ),
    (
        "Affordable Care Act popular with Republicans United States",
        "politics-da/link/4/aca-reform-aff",
        "{query} popular with Republicans",
    ),
    # Link template 5.
    (
        "national health insurance unpopular with Republicans United States",
        "politics-da/link/5/resolution",
        "{query} unpopular with Republicans",
    ),
    (
        "single payer unpopular with Republicans United States",
        "politics-da/link/5/single-payer-aff",
        "{query} unpopular with Republicans",
    ),
    (
        "Medicare for All unpopular with Republicans United States",
        "politics-da/link/5/medicare-for-all-aff",
        "{query} unpopular with Republicans",
    ),
    (
        "public option unpopular with Republicans United States",
        "politics-da/link/5/public-option-aff",
        "{query} unpopular with Republicans",
    ),
    (
        "Affordable Care Act unpopular with Republicans United States",
        "politics-da/link/5/aca-reform-aff",
        "{query} unpopular with Republicans",
    ),
    # Link template 6.
    (
        "national health insurance popular with Democrats United States",
        "politics-da/link/6/resolution",
        "{query} popular with Democrats",
    ),
    (
        "single payer popular with Democrats United States",
        "politics-da/link/6/single-payer-aff",
        "{query} popular with Democrats",
    ),
    (
        "Medicare for All popular with Democrats United States",
        "politics-da/link/6/medicare-for-all-aff",
        "{query} popular with Democrats",
    ),
    (
        "public option popular with Democrats United States",
        "politics-da/link/6/public-option-aff",
        "{query} popular with Democrats",
    ),
    (
        "Affordable Care Act popular with Democrats United States",
        "politics-da/link/6/aca-reform-aff",
        "{query} popular with Democrats",
    ),
    # Link template 7.
    (
        "national health insurance unpopular with Democrats United States",
        "politics-da/link/7/resolution",
        "{query} unpopular with Democrats",
    ),
    (
        "single payer unpopular with Democrats United States",
        "politics-da/link/7/single-payer-aff",
        "{query} unpopular with Democrats",
    ),
    (
        "Medicare for All unpopular with Democrats United States",
        "politics-da/link/7/medicare-for-all-aff",
        "{query} unpopular with Democrats",
    ),
    (
        "public option unpopular with Democrats United States",
        "politics-da/link/7/public-option-aff",
        "{query} unpopular with Democrats",
    ),
    (
        "Affordable Care Act unpopular with Democrats United States",
        "politics-da/link/7/aca-reform-aff",
        "{query} unpopular with Democrats",
    ),
]
"""The politics DA's 30 crossed link queries on NHI, written by hand from the preset (the PM's ruling
after the coach's answers, 2026-11-11): the coach's own wording, then templates 2, 4, 5, 6 and 7, each
on the resolution's words and then each mechanism. Not template 3, "unpopular with voters"."""


def test_template_expansion_of_politics_da_link_on_the_nhi_topic_crosses_the_coachs_templates(
    committed: ArgumentTaxonomy,
) -> None:
    """The ac6 search: the coach's seven link templates as he reviewed them, first and in order, then
    the six templates he chose crossed template-major with the resolution's words and the four
    mechanisms, each ending with the United States: 37 queries."""

    def link(text: str, template_id: str, template: str) -> ExpandedQuery:
        return template_query(
            text, template_id, template, days=1826, window=WindowSource.NEED, since=LINK_SINCE
        )

    expansion = expand(nhi_link(), committed)

    assert expansion == SearchExpansion(
        taxonomy_version="1.6.0",
        argument="politics-da",
        need="link",
        topic_id=NHI,
        variables={"query": RESOLUTION, "topic": RESOLUTION, "country": "United States"},
        queries=(
            link(
                "national health insurance political capital",
                "politics-da/link/1",
                "{query} political capital",
            ),
            link(
                "national health insurance partisan fight Congress",
                "politics-da/link/2",
                "{query} partisan fight Congress",
            ),
            link(
                "national health insurance unpopular with voters",
                "politics-da/link/3",
                "{query} unpopular with voters",
            ),
            link(
                "national health insurance popular with Republicans",
                "politics-da/link/4",
                "{query} popular with Republicans",
            ),
            link(
                "national health insurance unpopular with Republicans",
                "politics-da/link/5",
                "{query} unpopular with Republicans",
            ),
            link(
                "national health insurance popular with Democrats",
                "politics-da/link/6",
                "{query} popular with Democrats",
            ),
            link(
                "national health insurance unpopular with Democrats",
                "politics-da/link/7",
                "{query} unpopular with Democrats",
            ),
            *(link(text, template_id, template) for text, template_id, template in NHI_POLITICS_CROSSED),
        ),
    )
    assert len(expansion.queries) == 37


def test_template_mechanism_queries_keep_the_resolutions_words_as_one_query_per_crossed_template(
    committed: ArgumentTaxonomy,
) -> None:
    """The forbidden entry: every crossed template is asked once on the resolution's own words, whatever
    was typed, and its other queries are on the mechanisms."""
    for argument in ("politics-da", "midterms-da", "economy-da", "spending-da", "federalism-da"):
        expansion = expand(nhi_link("something else entirely", argument=argument), committed)
        crossed = [
            query for query in expansion.queries if query.template_id and query.template_id.count("/") == 3
        ]
        prefixes = list(
            dict.fromkeys(query.template_id.rsplit("/", 1)[0] for query in crossed if query.template_id)
        )
        assert len(crossed) == len(prefixes) * len(NHI_SUBJECTS), argument
        for prefix in prefixes:
            on_resolution = [query for query in crossed if query.template_id == f"{prefix}/resolution"]
            assert len(on_resolution) == 1, prefix
            assert on_resolution[0].query.startswith(f"{RESOLUTION} "), prefix
            assert "something else entirely" not in on_resolution[0].query, prefix


@pytest.mark.parametrize(
    ("argument", "expected"),
    [
        (
            "midterms-da",
            [
                ("national health insurance voters election impact", "midterms-da/link/1"),
                ("national health insurance issue swing voters", "midterms-da/link/2"),
                (
                    "national health insurance voters election impact United States",
                    "midterms-da/link/1/resolution",
                ),
                ("single payer voters election impact United States", "midterms-da/link/1/single-payer-aff"),
                (
                    "Medicare for All voters election impact United States",
                    "midterms-da/link/1/medicare-for-all-aff",
                ),
                (
                    "public option voters election impact United States",
                    "midterms-da/link/1/public-option-aff",
                ),
                (
                    "Affordable Care Act voters election impact United States",
                    "midterms-da/link/1/aca-reform-aff",
                ),
            ],
        ),
        (
            "economy-da",
            [
                ("national health insurance cost economy", "economy-da/link/1"),
                ("national health insurance economic impact", "economy-da/link/2"),
                ("national health insurance cost economy United States", "economy-da/link/1/resolution"),
                ("single payer cost economy United States", "economy-da/link/1/single-payer-aff"),
                ("Medicare for All cost economy United States", "economy-da/link/1/medicare-for-all-aff"),
                ("public option cost economy United States", "economy-da/link/1/public-option-aff"),
                ("Affordable Care Act cost economy United States", "economy-da/link/1/aca-reform-aff"),
            ],
        ),
        (
            "spending-da",
            [
                ("national health insurance cost federal budget", "spending-da/link/1"),
                ("national health insurance CBO cost estimate", "spending-da/link/2"),
                (
                    "national health insurance cost federal budget United States",
                    "spending-da/link/1/resolution",
                ),
                ("single payer cost federal budget United States", "spending-da/link/1/single-payer-aff"),
                (
                    "Medicare for All cost federal budget United States",
                    "spending-da/link/1/medicare-for-all-aff",
                ),
                ("public option cost federal budget United States", "spending-da/link/1/public-option-aff"),
                (
                    "Affordable Care Act cost federal budget United States",
                    "spending-da/link/1/aca-reform-aff",
                ),
            ],
        ),
        (
            "federalism-da",
            [
                ("national health insurance federal preemption states", "federalism-da/link/1"),
                (
                    "national health insurance federal government overrides state authority",
                    "federalism-da/link/2",
                ),
                (
                    "national health insurance federal preemption states United States",
                    "federalism-da/link/1/resolution",
                ),
                (
                    "single payer federal preemption states United States",
                    "federalism-da/link/1/single-payer-aff",
                ),
                (
                    "Medicare for All federal preemption states United States",
                    "federalism-da/link/1/medicare-for-all-aff",
                ),
                (
                    "public option federal preemption states United States",
                    "federalism-da/link/1/public-option-aff",
                ),
                (
                    "Affordable Care Act federal preemption states United States",
                    "federalism-da/link/1/aca-reform-aff",
                ),
            ],
        ),
    ],
)
def test_template_expansion_of_every_other_da_link_on_the_nhi_topic_adds_its_mechanisms(
    committed: ArgumentTaxonomy, argument: str, expected: list[tuple[str, str]]
) -> None:
    expansion = expand(nhi_link(argument=argument), committed)
    assert [(query.query, query.template_id) for query in expansion.queries] == expected
    assert {(query.since, query.window) for query in expansion.queries} == {(LINK_SINCE, WindowSource.NEED)}


@pytest.mark.parametrize(
    ("argument", "added"),
    [("politics-da", 30), ("midterms-da", 5), ("economy-da", 5), ("spending-da", 5), ("federalism-da", 5)],
)
def test_template_mechanism_queries_follow_the_reviewed_ones_which_are_asked_as_without_the_topic(
    committed: ArgumentTaxonomy, argument: str, added: int
) -> None:
    """The coach's reviewed queries are asked exactly as without the topic, first and in order; the
    politics DA crosses six templates with five subjects, every other DA its first template."""
    today = expand(request_for(RESOLUTION, argument=argument, need="link"), committed).queries
    on_topic = expand(nhi_link(argument=argument), committed).queries
    assert on_topic[: len(today)] == today
    assert len(on_topic) == len(today) + added


def test_template_mechanism_queries_ask_the_resolutions_words_whatever_was_typed(
    committed: ArgumentTaxonomy,
) -> None:
    """Typed as a mechanism, the reviewed queries are on what was typed; the added resolution query is
    still on the topic's own words, and the typed mechanism's query is asked once."""
    expansion = expand(nhi_link("Medicare for All"), committed)
    assert [query.query for query in expansion.queries] == [
        "Medicare for All political capital",
        "Medicare for All partisan fight Congress",
        "Medicare for All unpopular with voters",
        "Medicare for All popular with Republicans",
        "Medicare for All unpopular with Republicans",
        "Medicare for All popular with Democrats",
        "Medicare for All unpopular with Democrats",
        *(text for text, _, _ in NHI_POLITICS_CROSSED),
    ]


def test_template_mechanism_queries_are_added_only_to_a_das_link_on_a_topic_with_mechanisms(
    committed: ArgumentTaxonomy, mechanisms: ArgumentTaxonomy
) -> None:
    def count(taxonomy: ArgumentTaxonomy, argument: str, need: str, topic: str | None) -> int:
        request = request_for(RESOLUTION, argument=argument, need=need, topic_id=topic)
        return len(expand(request, taxonomy).queries)

    assert count(committed, "politics-da", "link", NHI) == 37
    assert count(committed, "politics-da", "link", None) == 7
    assert count(committed, "midterms-da", "link", NHI) == 7
    for argument, need in [
        ("politics-da", "uniqueness"),
        ("politics-da", "internal-link"),
        ("politics-da", "impact"),
        ("politics-da", "answers"),
        ("economy-advantage", "link"),
        ("cap-k", "link"),
        ("states-cp", "solvency"),
    ]:
        assert count(committed, argument, need, NHI) == count(committed, argument, need, None), (
            argument,
            need,
        )
    assert count(mechanisms, "test-da", "link", "test-topic") == 5
    assert count(mechanisms, "test-advantage", "link", "test-topic") == 1
    assert count(mechanisms, "test-da", "link", "bare-topic") == 2
    assert count(mechanisms, "test-da", "uniqueness", "test-topic") == 2


def test_template_mechanism_queries_come_from_the_first_link_template_a_search_always_renders(
    mechanisms: ArgumentTaxonomy,
) -> None:
    """`{bill} link` is skipped for the fan-out even when the request names a bill; the second template
    sets its own window; a phrase that already names the country does not name it twice."""
    expansion = expand(
        request_for("typed words", need="link", topic_id="test-topic", variables={"bill": "the bill"}),
        mechanisms,
    )
    own = NOW - timedelta(days=90)
    assert expansion.queries == (
        template_query(
            "the bill link",
            "test-da/link/1",
            "{bill} link",
            days=30,
            window=WindowSource.NEED,
            since=NOW - timedelta(days=30),
        ),
        template_query(
            "typed words link",
            "test-da/link/2",
            "{query} link",
            days=90,
            window=WindowSource.TEMPLATE,
            since=own,
        ),
        template_query(
            "preset subject second link",
            "test-da/link/3",
            "{topic} second link",
            days=30,
            window=WindowSource.NEED,
            since=NOW - timedelta(days=30),
        ),
        template_query(
            "preset subject link Testland",
            "test-da/link/2/resolution",
            "{query} link",
            days=90,
            window=WindowSource.TEMPLATE,
            since=own,
        ),
        template_query(
            "alpha plan link Testland",
            "test-da/link/2/alpha-aff",
            "{query} link",
            days=90,
            window=WindowSource.TEMPLATE,
            since=own,
        ),
        template_query(
            "beta plan in Testland link",
            "test-da/link/2/beta-aff",
            "{query} link",
            days=90,
            window=WindowSource.TEMPLATE,
            since=own,
        ),
    )


def test_template_mechanism_queries_keep_the_searchs_own_since(mechanisms: ArgumentTaxonomy) -> None:
    since = datetime(2026, 1, 1, tzinfo=UTC)
    expansion = expand(
        request_for(need="link", topic_id="test-topic", filters=SearchFilters(since=since)), mechanisms
    )
    added = [query for query in expansion.queries if query.template_id and query.template_id.count("/") == 3]
    assert [query.template_id for query in added] == [
        "test-da/link/2/resolution",
        "test-da/link/2/alpha-aff",
        "test-da/link/2/beta-aff",
    ]
    assert {(query.since, query.window) for query in added} == {(since, WindowSource.REQUEST)}


# The link templates a DA's mechanism queries cross (v1-e08-t16) ---------------------------------


def crossing_taxonomy(entries: list[dict[str, Any]] | None = None, **topic: Any) -> dict[str, Any]:
    """mechanism_taxonomy with a second DA (its first link template needs a bill, so its default is its
    second) and, on test-topic, `entries` as its crossed templates: by default a crossing-only one, then
    the DA's templates 3 and 2, in that order."""
    document = mechanism_taxonomy()
    document["arguments"].append(
        {
            "id": "second-da",
            "label": "Second DA",
            "kind": "da",
            "formats": ["POLICY"],
            "review": "awaiting_coach_review",
            "templates": {
                "uniqueness": [{"text": "{query} second now"}],
                "impact": [{"text": "{query} second impact"}],
                "link": [{"text": "{bill} second-da link"}, {"text": "{query} second-da link"}],
            },
        }
    )
    document["topics"][0]["mechanism_link_templates"] = (
        [
            {"argument": "test-da", "text": "{query} own crossing"},
            {"template_id": "test-da/link/3", "text": "{topic} second link"},
            {"template_id": "test-da/link/2", "text": "{query} link"},
        ]
        if entries is None
        else entries
    )
    document["topics"][0].update(topic)
    return document


@pytest.fixture(scope="module")
def crossing() -> ArgumentTaxonomy:
    return parsed(crossing_taxonomy())


def test_template_mechanism_queries_cross_the_chosen_templates_template_major_in_the_listed_order(
    crossing: ArgumentTaxonomy,
) -> None:
    """The reviewed queries first; then each chosen template, in the preset's order (not the DA's), on
    the resolution's words and each mechanism. A crossing-only template takes the need's window and an
    id of the topic's; a DA template keeps its own window and id."""
    expansion = expand(request_for("typed words", need="link", topic_id="test-topic"), crossing)
    need = NOW - timedelta(days=30)
    own = NOW - timedelta(days=90)

    def at_need(text: str, template_id: str, template: str) -> ExpandedQuery:
        return template_query(text, template_id, template, days=30, window=WindowSource.NEED, since=need)

    def at_own(text: str, template_id: str, template: str) -> ExpandedQuery:
        return template_query(text, template_id, template, days=90, window=WindowSource.TEMPLATE, since=own)

    assert expansion.skipped_templates == ("test-da/link/1",)
    assert expansion.queries == (
        at_own("typed words link", "test-da/link/2", "{query} link"),
        at_need("preset subject second link", "test-da/link/3", "{topic} second link"),
        at_need(
            "preset subject own crossing Testland",
            "test-da/link/test-topic-1/resolution",
            "{query} own crossing",
        ),
        at_need(
            "alpha plan own crossing Testland", "test-da/link/test-topic-1/alpha-aff", "{query} own crossing"
        ),
        at_need(
            "beta plan in Testland own crossing", "test-da/link/test-topic-1/beta-aff", "{query} own crossing"
        ),
        at_need("preset subject second link Testland", "test-da/link/3/resolution", "{topic} second link"),
        at_need("alpha plan second link Testland", "test-da/link/3/alpha-aff", "{topic} second link"),
        at_need("beta plan in Testland second link", "test-da/link/3/beta-aff", "{topic} second link"),
        at_own("preset subject link Testland", "test-da/link/2/resolution", "{query} link"),
        at_own("alpha plan link Testland", "test-da/link/2/alpha-aff", "{query} link"),
        at_own("beta plan in Testland link", "test-da/link/2/beta-aff", "{query} link"),
    )


def test_template_mechanism_queries_of_a_da_the_preset_does_not_name_cross_its_first_renderable_template(
    crossing: ArgumentTaxonomy,
) -> None:
    """second-da is not named: it crosses its second link template, the first that names only {query}
    and {topic}, and none of test-da's choices."""
    expansion = expand(
        request_for("typed words", argument="second-da", need="link", topic_id="test-topic"), crossing
    )
    assert [(query.query, query.template_id) for query in expansion.queries] == [
        ("typed words second-da link", "second-da/link/2"),
        ("preset subject second-da link Testland", "second-da/link/2/resolution"),
        ("alpha plan second-da link Testland", "second-da/link/2/alpha-aff"),
        ("beta plan in Testland second-da link", "second-da/link/2/beta-aff"),
    ]


def test_template_crossing_only_templates_are_never_asked_without_the_topic(
    crossing: ArgumentTaxonomy,
) -> None:
    without = expand(request_for("typed words", need="link"), crossing)
    assert [(query.query, query.template_id) for query in without.queries] == [
        ("typed words link", "test-da/link/2"),
        ("typed words second link", "test-da/link/3"),
    ]


def many_mechanisms(count: int) -> list[dict[str, str]]:
    """`count` distinct mechanisms whose names and phrases hold no digit."""
    letters = "abcdefghijklmnopqrstuvwxyz"
    return [plan_mechanism(f"m{letters[number // 26]}{letters[number % 26]}") for number in range(count)]


def test_the_taxonomy_takes_a_preset_whose_largest_da_link_search_is_the_most_a_search_asks() -> None:
    """test-da has 3 link templates; crossing one template with the resolution and 38 mechanisms gives
    3 + 39 = 42 queries, the maximum; five mechanisms, more than v1-e08-t14's four, load too."""
    at_the_edge = parsed(crossing_taxonomy([], mechanisms=many_mechanisms(38)))
    request = request_for("typed words", need="link", topic_id="test-topic", variables={"bill": "the bill"})
    assert len(expand(request, at_the_edge).queries) == 42
    assert len(parsed(crossing_taxonomy([], mechanisms=many_mechanisms(5))).topics[0].mechanisms) == 5
    document = crossing_taxonomy()
    document["arguments"][0]["templates"]["uniqueness"] = [
        {"text": "{query} now"},
        *({"text": f"{{query}} {entry['phrase']}"} for entry in many_mechanisms(41)),
    ]
    assert len(parsed(document).arguments[0].templates["uniqueness"]) == 42


@pytest.mark.parametrize(
    ("document", "words"),
    [
        pytest.param(
            crossing_taxonomy([], mechanisms=many_mechanisms(39)),
            ["topic test-topic: test-da's link search would ask 43 queries; a search asks at most 42"],
            id="a DA link search one query over the maximum",
        ),
        pytest.param(
            crossing_taxonomy(
                [
                    {"template_id": "test-da/link/2", "text": "{query} link"},
                    {"template_id": "test-da/link/3", "text": "{topic} second link"},
                ],
                mechanisms=many_mechanisms(19),
            ),
            ["topic test-topic: test-da's link search would ask 43 queries; a search asks at most 42"],
            id="two crossed templates one query over the maximum",
        ),
        pytest.param(
            crossing_taxonomy([{"template_id": "tda/link/2", "text": "{query} link"}]),
            ["topic test-topic: the mechanism link template tda/link/2 names tda, which is not a DA's id"],
            id="a crossed template named by an alias",
        ),
        pytest.param(
            crossing_taxonomy([{"template_id": "test-advantage/link/1", "text": "{query} link"}]),
            ["names test-advantage, which is not a DA's id"],
            id="a crossed template of an advantage",
        ),
        pytest.param(
            crossing_taxonomy([{"argument": "test-advantage", "text": "{query} own"}]),
            ["names test-advantage, which is not a DA's id"],
            id="a crossing-only template of an advantage",
        ),
        pytest.param(
            crossing_taxonomy([{"template_id": "test-da/uniqueness/1", "text": "{query} now"}]),
            ["the mechanism link template test-da/uniqueness/1 is not a link template"],
            id="a crossed template of another need",
        ),
        pytest.param(
            crossing_taxonomy([{"template_id": "test-da/link", "text": "{query} link"}]),
            ["the mechanism link template test-da/link is not a template id of the form <da>/link/<number>"],
            id="a crossed template id with no number",
        ),
        pytest.param(
            crossing_taxonomy([{"template_id": "test-da/link/4", "text": "{query} link"}]),
            ["the mechanism link template test-da/link/4: test-da has no link template 4"],
            id="a crossed template number past the DA's templates",
        ),
        pytest.param(
            crossing_taxonomy([{"template_id": "test-da/link/2", "text": "{query} links"}]),
            ["the template at test-da/link/2 reads '{query} link', not '{query} links'"],
            id="a crossed template whose text differs",
        ),
        pytest.param(
            crossing_taxonomy([{"template_id": "test-da/link/1", "text": "{bill} link"}]),
            [
                "the mechanism link template test-da/link/1 names bill; a crossed template names only "
                "query and topic"
            ],
            id="a crossed DA template naming a bill",
        ),
        pytest.param(
            crossing_taxonomy([{"argument": "test-da", "text": "{bill} own crossing"}]),
            [
                "the mechanism link template '{bill} own crossing' names bill; a crossed template names only "
                "query and topic"
            ],
            id="a crossing-only template naming a bill",
        ),
        pytest.param(
            crossing_taxonomy([{"argument": "test-da", "text": "{0} own crossing"}]),
            ["has the field {0}"],
            id="a crossing-only template with a positional field",
        ),
        pytest.param(
            crossing_taxonomy(
                [
                    {"template_id": "test-da/link/2", "text": "{query} link"},
                    {"argument": "test-da", "text": "{query}  Link"},
                ]
            ),
            ["topic test-topic crosses test-da's template '{query}  Link' twice"],
            id="one template crossed twice",
        ),
        pytest.param(
            crossing_taxonomy(
                [{"template_id": "test-da/link/2", "argument": "test-da", "text": "{query} link"}]
            ),
            ["names either a template_id or an argument, not both"],
            id="a crossed template with an id and an argument",
        ),
        pytest.param(
            crossing_taxonomy([{"text": "{query} link"}]),
            ["names either a template_id or an argument, not both"],
            id="a crossed template with neither an id nor an argument",
        ),
        pytest.param(
            crossing_taxonomy(mechanisms=[]),
            ["topic test-topic names mechanism link templates but no plan mechanisms"],
            id="crossed templates and no mechanisms",
        ),
    ],
)
def test_a_taxonomy_whose_mechanism_link_templates_break_a_rule_is_refused_when_it_loads(
    document: dict[str, Any], words: list[str]
) -> None:
    with pytest.raises(InvalidArgumentTaxonomy) as refused:
        parsed(document)
    message = str(refused.value)
    assert message.startswith("test taxonomy")
    for word in words:
        assert word in message


def test_a_taxonomy_with_more_templates_for_one_pair_than_a_search_asks_is_refused() -> None:
    document = crossing_taxonomy()
    document["arguments"][0]["templates"]["uniqueness"] = [
        {"text": "{query} now"},
        *({"text": f"{{query}} {entry['phrase']}"} for entry in many_mechanisms(42)),
    ]
    with pytest.raises(
        InvalidArgumentTaxonomy, match="test-da/uniqueness has 43 templates; a search asks at most 42"
    ):
        parsed(document)


def test_the_committed_taxonomy_nhi_topic_crosses_the_politics_templates_the_coach_chose(
    committed: ArgumentTaxonomy,
) -> None:
    """The coach's answers of 2026-11-11: his own wording, then his templates 2, 4, 5, 6 and 7, each as he
    reviewed it (checked against the reviewed record, not only the committed file); not 3."""
    topic = next(topic for topic in committed.topics if topic.id == "policy-2026-27-nhi")
    assert topic.review is ReviewStatus.COACH_REVIEWED
    assert [(entry.template_id, entry.argument, entry.text) for entry in topic.mechanism_link_templates] == [
        (None, "politics-da", "{query} costs political capital Congress"),
        ("politics-da/link/2", None, "{query} partisan fight Congress"),
        ("politics-da/link/4", None, "{query} popular with Republicans"),
        ("politics-da/link/5", None, "{query} unpopular with Republicans"),
        ("politics-da/link/6", None, "{query} popular with Democrats"),
        ("politics-da/link/7", None, "{query} unpopular with Democrats"),
    ]
    reviewed_file = yaml.safe_load(COACH_REVIEWED_FILE.read_text(encoding="utf-8"))
    reviewed_links = next(entry for entry in reviewed_file["arguments"] if entry["id"] == "politics-da")[
        "templates"
    ]["link"]
    for entry in topic.mechanism_link_templates:
        if entry.template_id is not None:
            number = int(entry.template_id.rsplit("/", 1)[1])
            assert reviewed_links[number - 1]["text"] == entry.text, entry.template_id


def test_every_da_link_search_on_a_committed_preset_is_the_fewest_openalex_requests_per_page(
    committed: ArgumentTaxonomy,
) -> None:
    """v1-e08-t16's pin, held against what OpenAlex was measured to refuse (v1-e08-t20, 2026-11-12): a
    search over 1,500 characters. The politics DA's 37 link queries on the NHI preset go as 24 and 13,
    because the operator's requests found the first 24 joined are 1,473 characters, answered, and the
    first 25 are 1,536, refused. Every other DA's link search there is seven or eight queries, one
    request. Every request fits both limits."""
    fewest = {("policy-2026-27-nhi", "politics-da"): [24, 13]}
    checked = 0
    for topic in committed.topics:
        if not topic.mechanisms:
            continue
        for argument in committed.arguments:
            if argument.kind is not ArgumentKind.DA:
                continue
            filters = SearchFilters(max_results=200)
            request = request_for(
                topic.variables["topic"],
                argument=argument.id,
                need="link",
                topic_id=topic.id,
                filters=filters,
            )
            expansion = expand(request, committed)
            requests = works_requests(provider_queries(expansion, filters))
            carried = [len(request.answers) for request in requests]
            expected = fewest.get((topic.id, argument.id), [len(expansion.queries)])
            assert carried == expected, (topic.id, argument.id, carried)
            assert all(len(request.query.query) <= MAX_SEARCH_CHARS for request in requests)
            if carried == [24, 13]:
                assert len(requests[0].query.query) == 1_473
            assert len(expansion.queries) <= MAX_QUERIES_PER_SEARCH, (topic.id, argument.id)
            checked += 1
    assert checked == 9


def service_over(
    provider: FakeSearchProvider, stage: QueryExpansionStage, searches: SearchRepository | None = None
) -> FederatedSearchService:
    class Providers:
        providers = (provider,)
        not_configured: dict[str, str] = {}  # noqa: RUF012 - read only, as the port's

        def health(self) -> tuple[()]:
            return ()

    return FederatedSearchService(
        Providers(),
        InMemorySearchRepository() if searches is None else searches,
        clock=FixedClock(NOW),
        ids=SequentialIdGenerator("SRCH"),
        expand=stage,
    )


@pytest.fixture(params=["in-memory", "sqlite"])
def searches(request: pytest.FixtureRequest, tmp_path: Path) -> SearchRepository:
    if request.param == "in-memory":
        return InMemorySearchRepository()
    database = SqliteDatabase.open(tmp_path)
    request.addfinalizer(database.close)
    return SqliteSearchRepository(database)


def test_template_expansion_is_asked_of_every_provider_and_recorded_on_the_stored_search(
    committed: ArgumentTaxonomy, searches: SearchRepository
) -> None:
    provider = FakeSearchProvider("openalex")
    service = service_over(provider, QueryExpansionStage(committed, clock=FixedClock(NOW)), searches)
    filters = SearchFilters(max_results=10)
    request = request_for("health insurance", argument="politics-da", need="link", filters=filters)

    outcome = asyncio.run(service.search(request))

    expected = expand(request, committed)
    assert outcome.search.expansion == expected
    since = NOW - timedelta(days=1826)
    asked = [(query.query, query.filters) for query in provider.queries]
    assert asked == [
        (f"health insurance {link}", SearchFilters(since=since, max_results=10))
        for link in (
            "political capital",
            "partisan fight Congress",
            "unpopular with voters",
            "popular with Republicans",
            "unpopular with Republicans",
            "popular with Democrats",
            "unpopular with Democrats",
        )
    ]
    stored = asyncio.run(searches.get(outcome.search.search_id))
    assert stored.expansion == expected
    statuses = asyncio.run(searches.list_provider_statuses(outcome.search.search_id))
    assert [status.query.query for status in statuses] == [query.query for query in expected.queries]


def test_template_mechanism_queries_are_asked_of_every_provider_and_recorded_on_the_stored_search(
    committed: ArgumentTaxonomy, searches: SearchRepository
) -> None:
    provider = FakeSearchProvider("openalex")
    service = service_over(provider, QueryExpansionStage(committed, clock=FixedClock(NOW)), searches)
    request = nhi_link(filters=SearchFilters(max_results=10))

    outcome = asyncio.run(service.search(request))

    filters = SearchFilters(since=LINK_SINCE, max_results=10)
    assert [(query.query, query.filters) for query in provider.queries][7:] == [
        (text, filters) for text, _, _ in NHI_POLITICS_CROSSED
    ]
    assert len(provider.queries) == 37
    stored = asyncio.run(searches.get(outcome.search.search_id))
    expected = expand(request, committed)
    assert stored.expansion == expected
    assert [query.template_id for query in expected.queries][7:] == [
        template_id for _, template_id, _ in NHI_POLITICS_CROSSED
    ]


def test_template_free_search_stores_no_expansion_key(searches: SearchRepository) -> None:
    provider = FakeSearchProvider("openalex")
    outcome = asyncio.run(
        service_over(provider, QueryExpansionStage(TAXONOMY, clock=FixedClock(NOW)), searches).search(
            SearchRequest(query="as typed")
        )
    )
    assert outcome.search.expansion is None
    assert "expansion" not in outcome.search.model_dump(mode="json")
    assert [query.query for query in provider.queries] == ["as typed"]


# =============================================================================================
# A model's extra queries (ac3)
# =============================================================================================

HAPPY_QUERY = "community clinic funding"
"""The query whose fixture (tests/fixtures/model_outputs/search.expand/) answers in the schema."""

MALFORMED_QUERY = "rural hospital staffing"
"""The query whose fixture and repair fixture both answer with an `evidence` key the schema refuses."""


def fixture_stage(prompts: PromptRegistry) -> tuple[QueryExpansionStage, FakeModelRouter]:
    router = FakeModelRouter(MODEL_OUTPUTS)
    return QueryExpansionStage(
        TAXONOMY, clock=FixedClock(NOW), guard=StructuredOutputGuard(router, prompts)
    ), router


def scripted_stage(
    prompts: PromptRegistry, *answers: Any, max_model_queries: int = 3
) -> tuple[QueryExpansionStage, ScriptedModelRouter]:
    router = ScriptedModelRouter(answers)
    guard = StructuredOutputGuard(router, prompts)
    stage = QueryExpansionStage(
        TAXONOMY, clock=FixedClock(NOW), guard=guard, max_model_queries=max_model_queries
    )
    return stage, router


def test_model_expansion_is_off_unless_the_request_asks_for_it(prompts: PromptRegistry) -> None:
    stage, router = scripted_stage(prompts, {"queries": [{"query": "never asked", "rationale": "r"}]})
    state = run_stage(stage, request_for(HAPPY_QUERY))
    assert router.calls == []
    assert state.expansion is not None
    assert (state.expansion.model_requested, state.expansion.model, state.expansion.warning) == (
        False,
        None,
        None,
    )
    assert ExpansionRequest(argument="test-da", need="link").use_model is False


def test_model_expansion_appends_validated_queries_with_rationale_and_prompt_metadata(
    prompts: PromptRegistry, searches: SearchRepository
) -> None:
    """The fixture answers three queries; the second repeats a template query and is asked once."""
    stage, _ = fixture_stage(prompts)
    provider = FakeSearchProvider("openalex")
    outcome = asyncio.run(
        service_over(provider, stage, searches).search(request_for(HAPPY_QUERY, use_model=True))
    )

    expansion = outcome.search.expansion
    assert expansion is not None
    model_since = NOW - timedelta(days=14)
    assert [(q.query, q.origin, q.rationale, q.since, q.window) for q in expansion.queries] == [
        ("community clinic funding now", QueryOrigin.TEMPLATE, None, model_since, WindowSource.NEED),
        (
            "community clinic funding polling",
            QueryOrigin.TEMPLATE,
            None,
            NOW - timedelta(days=3),
            WindowSource.TEMPLATE,
        ),
        (
            "community clinic funding state budget shortfall",
            QueryOrigin.MODEL,
            "Looks for reporting on current gaps in state budgets for clinics.",
            model_since,
            WindowSource.NEED,
        ),
        (
            "community clinic closures announced",
            QueryOrigin.MODEL,
            "Looks for news of clinics closing for lack of funds.",
            model_since,
            WindowSource.NEED,
        ),
    ]
    assert expansion.model is not None
    assert (expansion.model.prompt_id, expansion.model.prompt_version) == (
        EXPAND_PROMPT_ID,
        EXPAND_PROMPT_VERSION,
    )
    assert expansion.model.route.task_class is TaskClass.HIGH_VOLUME
    assert (expansion.model.route.provider, expansion.model.route.model_id) == (
        ModelProvider.FAKE,
        FAKE_MODEL_ID,
    )
    assert expansion.model_requested is True and expansion.warning is None
    assert [query.query for query in provider.queries] == [query.query for query in expansion.queries]
    assert asyncio.run(searches.get(outcome.search.search_id)).expansion == expansion


def test_model_expansion_of_a_malformed_output_falls_back_to_the_template_queries_with_a_warning(
    prompts: PromptRegistry, caplog: pytest.LogCaptureFixture
) -> None:
    stage, _ = fixture_stage(prompts)
    templates_only = expand(request_for(MALFORMED_QUERY))
    with caplog.at_level(logging.WARNING, logger="debate_core.application.query_expansion"):
        state = run_stage(stage, request_for(MALFORMED_QUERY, use_model=True))

    assert state.expansion is not None
    assert state.expansion.queries == templates_only.queries
    assert [query.query for query in state.queries] == [
        "rural hospital staffing now",
        "rural hospital staffing polling",
    ]
    assert state.expansion.model is None
    assert state.expansion.warning == (
        "the model's queries did not validate after one repair; searched with the template queries alone "
        "(INVALID_MODEL_OUTPUT)"
    )
    assert [record.getMessage() for record in caplog.records if record.name.endswith("query_expansion")] == [
        "query expansion used its templates alone"
    ]


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(
            {"queries": [{"query": "a b c d e f g h i j k l m", "rationale": "r"}]}, id="thirteen words"
        ),
        pytest.param({"queries": [{"query": "clinic\nfunding", "rationale": "r"}]}, id="two lines"),
        pytest.param({"queries": [{"query": "https://example.org/clinics", "rationale": "r"}]}, id="a link"),
        pytest.param({"queries": [{"query": "www.example.org clinics", "rationale": "r"}]}, id="a bare host"),
        pytest.param(
            {"queries": [{"query": f"query {n}", "rationale": "r"} for n in range(4)]}, id="more than asked"
        ),
        pytest.param({"queries": [{"query": "x" * 121, "rationale": "r"}]}, id="over 120 characters"),
        pytest.param({"queries": [{"query": "  ", "rationale": "r"}]}, id="blank"),
        pytest.param({"queries": [{"query": "clinic funding"}]}, id="no rationale"),
        pytest.param({"suggestions": ["clinic funding"]}, id="free text in another shape"),
    ],
)
def test_model_expansion_never_asks_a_query_that_fails_validation(
    prompts: PromptRegistry, answer: Any
) -> None:
    """Each answer is given twice, to the call and to its one repair, so both are refused."""
    stage, router = scripted_stage(prompts, answer, answer)
    state = run_stage(stage, request_for(use_model=True))
    assert len(router.calls) == 2
    assert [query.query for query in state.queries] == [
        "community clinic funding now",
        "community clinic funding polling",
    ]
    assert state.expansion is not None and state.expansion.warning is not None


def test_model_expansion_uses_a_repaired_answer(prompts: PromptRegistry) -> None:
    bad = {"queries": [{"query": "https://example.org/clinics", "rationale": "r"}]}
    good = {"queries": [{"query": "clinic funding cuts", "rationale": "Finds reporting on cuts."}]}
    stage, router = scripted_stage(prompts, bad, good)
    state = run_stage(stage, request_for(use_model=True))
    assert [call.prompt.prompt_id for call in router.calls] == [EXPAND_PROMPT_ID, "model.repair"]
    assert state.expansion is not None and state.expansion.model is not None
    assert state.expansion.model.repair_attempted is True
    assert state.queries[-1].query == "clinic funding cuts"


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        pytest.param(ProviderUnavailable("bedrock", "unreachable"), "PROVIDER_UNAVAILABLE", id="unreachable"),
        pytest.param(
            BudgetExceededError(
                limit_name="per-day", limit_usd=1.0, spent_usd=1.0, ceiling_usd=0.01, model_id="haiku"
            ),
            "BUDGET_EXCEEDED_ERROR",
            id="over budget",
        ),
    ],
)
def test_model_expansion_that_cannot_reach_a_model_searches_with_the_templates(
    prompts: PromptRegistry, failure: Exception, code: str
) -> None:
    stage, _ = scripted_stage(prompts, failure)
    state = run_stage(stage, request_for(use_model=True))
    assert state.expansion is not None
    assert [query.origin for query in state.expansion.queries] == [QueryOrigin.TEMPLATE, QueryOrigin.TEMPLATE]
    assert (
        state.expansion.warning
        == f"the model could not be asked; searched with the template queries alone ({code})"
    )


def test_model_expansion_without_a_model_configured_searches_with_the_templates() -> None:
    stage = QueryExpansionStage(TAXONOMY, clock=FixedClock(NOW))
    state = run_stage(stage, request_for(use_model=True))
    assert state.expansion is not None
    assert len(state.queries) == 2
    assert (
        state.expansion.warning
        == "model expansion is not configured; searched with the template queries alone"
    )


def test_model_expansion_that_only_repeats_the_templates_adds_nothing(prompts: PromptRegistry) -> None:
    repeat = {"queries": [{"query": "Community  clinic funding NOW", "rationale": "Repeats a chosen query."}]}
    stage, _ = scripted_stage(prompts, repeat)
    state = run_stage(stage, request_for(use_model=True))
    assert state.expansion is not None
    assert len(state.expansion.queries) == 2 and state.expansion.model is None
    assert state.expansion.warning == (
        "the model suggested no query the templates do not ask; searched with the template queries alone"
    )


def test_model_expansion_sends_the_registered_prompt_on_the_high_volume_route(
    prompts: PromptRegistry,
) -> None:
    stage, router = scripted_stage(prompts, {"queries": []}, max_model_queries=2)
    run_stage(stage, request_for(use_model=True))
    [call] = router.calls
    assert call.task_class is TaskClass.HIGH_VOLUME
    assert (call.prompt.prompt_id, call.prompt.prompt_version) == (EXPAND_PROMPT_ID, EXPAND_PROMPT_VERSION)
    assert call.prompt.variables == {
        "argument": "Test DA (da)",
        "need": "Uniqueness",
        "need_description": "Where things stand now.",
        "query": "community clinic funding",
        "topic": "community clinic funding",
        "template_queries": "- community clinic funding now\n- community clinic funding polling",
        "max_queries": 2,
    }


def test_model_expansion_stage_takes_one_to_five_model_queries() -> None:
    for wrong in (0, 6):
        with pytest.raises(ValueError, match="max_model_queries"):
            QueryExpansionStage(TAXONOMY, clock=FixedClock(NOW), max_model_queries=wrong)


def test_the_committed_taxonomy_de_extinction_preset_names_its_topic_and_no_mechanisms(
    committed: ArgumentTaxonomy,
) -> None:
    """v1-e32-t06: the LD preset gives {topic} from the committed resolution, approved by the coach on
    2026-11-05; an LD resolution has no plan, so it lists no mechanisms."""
    topic = next(topic for topic in committed.topics if topic.id == "ld-2026-nov-dec-de-extinction")
    assert (topic.format, topic.review, topic.variables, topic.mechanisms) == (
        Event.LD,
        ReviewStatus.COACH_REVIEWED,
        {"topic": "de-extinction"},
        (),
    )
