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
)
from debate_core.application.structured_output import StructuredOutputGuard
from debate_core.domain import SearchFilters
from debate_core.domain.argument_taxonomy import ArgumentTaxonomy
from debate_core.domain.caselist.values import Event
from debate_core.domain.model_contracts import ModelProvider, TaskClass
from debate_core.domain.search import ExpandedQuery, QueryOrigin, SearchExpansion, WindowSource
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
schema_version: 1
taxonomy_version: 0.1.0
variables:
  query: The query.
  topic: The topic.
  bill: The agenda item.
needs:
  - {id: uniqueness, label: Uniqueness, description: Where things stand now., aliases: [uq], recency_days: 14}
  - {id: impact, label: Impact, description: What happens in the end., aliases: [i], recency_days: any}
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
      uniqueness:
        - {text: "{topic} trends"}
      impact:
        - {text: "framework justification"}
topics:
  - {id: test-topic, format: POLICY, variables: {topic: preset subject}}
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


TAXONOMY = parse_argument_taxonomy(SMALL_TAXONOMY, source="SMALL_TAXONOMY")


@pytest.fixture(scope="module")
def committed() -> ArgumentTaxonomy:
    return load_argument_taxonomy(REPOSITORY / ARGUMENT_TAXONOMY_PATH)


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


def test_the_committed_taxonomy_validates_and_every_argument_need_pair_has_a_template(
    committed: ArgumentTaxonomy,
) -> None:
    needs = [need.id for need in committed.needs]
    assert needs == ["uniqueness", "link", "internal-link", "impact", "answers"]
    for argument in committed.arguments:
        assert sorted(argument.templates) == sorted(needs), argument.id
        for need in needs:
            assert argument.templates[need], f"{argument.id}/{need}"


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
    labels = [need.label for need in committed.needs] + [argument.label for argument in committed.arguments]
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
    assert [topic.id for topic in committed.topics] == ["policy-2026-27-nhi"]
    for topic in committed.topics:
        resolution = resolutions[topic.id]
        assert resolution is not None, f"{topic.id} has no committed resolution to take values from"
        flat = " ".join(resolution.casefold().split())
        for value in topic.variables.values():
            assert " ".join(value.casefold().split()) in flat, f"{topic.id}: {value}"


def test_the_committed_taxonomy_resolves_the_spec_spellings_and_typed_variants(
    committed: ArgumentTaxonomy,
) -> None:
    def argument(name: str) -> str | None:
        found = committed.find_argument(name)
        return None if found is None else found.id

    def need(name: str) -> str | None:
        found = committed.find_need(name)
        return None if found is None else found.id

    assert argument("ptx") == "politics-da"
    assert argument("Politics DA") == "politics-da"
    assert argument("econ-da") == "economy-da"
    assert argument("elections") == "midterms-da"
    assert need("AT") == "answers"
    assert need("internal link") == "internal-link"
    assert need("uq") == "uniqueness"


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
            small_taxonomy(topics=[{"id": "t", "format": "LD", "variables": {"query": "x"}}]),
            ["query"],
            id="a topic setting query",
        ),
        pytest.param(small_taxonomy(unexpected=1), ["unexpected"], id="an unknown key"),
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
        pytest.param({"need": "solvency"}, "need", "solvency", ("uniqueness", "impact"), id="need"),
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
        taxonomy_version="1.1.0",
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


def service_over(
    provider: FakeSearchProvider, stage: QueryExpansionStage, searches: SearchRepository | None = None
) -> FederatedSearchService:
    class Providers:
        providers = (provider,)

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
