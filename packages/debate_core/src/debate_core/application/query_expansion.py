"""Query expansion: a search's query turned into the queries a debate argument and need call for.

The federated search's first stage (v1-e08-t04-argument-need-expansion). A search that names an
argument and a need (:class:`~debate_core.application.federated_search_types.ExpansionRequest`)
asks its providers the taxonomy's queries for that pair instead of the bare query;
:class:`QueryExpansionStage` is the stage, and a search without them passes through unchanged.

## Templates

:func:`expand_with_templates` is deterministic: the same request, taxonomy and clock give the same
queries in the same order. It

1. resolves the argument and need by id or alias, refusing an unknown one with
   :class:`UnknownExpansionChoice`, which lists the valid choices;
2. fills the variables: `query` is the search's own, the topic preset's values and the request's
   own come next, and `topic` falls back to the query;
3. renders every template of the pair whose variables are all filled, in the taxonomy's order, and
   records the others as skipped (the taxonomy guarantees one per pair always renders);
4. gives each query a `since`: the search's own when a person set one, otherwise the template's
   window, or the need's, counted back from the search's `until` or from now.

Two templates that render the same query are asked once.

## A model's extra queries (`--expand-llm`)

Off unless the request asks for it (`ExpansionRequest.use_model`), and never needed. When asked, the
stage sends `search.expand` (:data:`EXPAND_PROMPT_ID`) through the
:class:`~debate_core.application.structured_output.StructuredOutputGuard` on the `high_volume`
route, with `fail_closed=False`: an expansion produces no evidence, so a failure degrades to the
templates rather than failing the search. The answer must validate as :class:`QueryExpansion` and
pass :func:`model_query_problems`, or it is repaired once and then refused. A refused answer, a
model that cannot be reached and a budget refusal all leave the template queries to be asked alone,
with a warning recorded on the expansion and logged. Nothing a model says reaches a provider
without that validation, and the model is only ever asked for query strings and a short reason,
never for evidence text.

The expansion is recorded on the stored :class:`~debate_core.domain.search.Search`, so a search
says what it asked and why.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Final

import yaml
from pydantic import Field, ValidationError

from debate_core.application.budget import BudgetExceededError
from debate_core.application.errors import DomainError, OutputProblem, ProviderError, error_code_of
from debate_core.application.federated_search_types import ExpansionRequest, SearchRequest, SearchState
from debate_core.application.model_errors import ModelOutputError, ValidationPolicy
from debate_core.application.ports.providers import Clock
from debate_core.application.settings import ConfigurationError
from debate_core.application.structured_output import StructuredOutputGuard
from debate_core.domain.argument_taxonomy import (
    Argument,
    ArgumentTaxonomy,
    Need,
    RecencyDays,
)
from debate_core.domain.base import DomainModel, NonEmptyText
from debate_core.domain.discovery import ProviderQuery
from debate_core.domain.model_contracts import ModelPrompt, TaskClass
from debate_core.domain.search import (
    ExpandedQuery,
    QueryOrigin,
    SearchExpansion,
    SearchFilters,
    WindowSource,
)

__all__ = [
    "ARGUMENT_TAXONOMY_PATH",
    "DEFAULT_MAX_MODEL_QUERIES",
    "EXPANSION_POLICY",
    "EXPANSION_TASK_CLASS",
    "EXPAND_PROMPT_ID",
    "EXPAND_PROMPT_VERSION",
    "MAX_MODEL_QUERY_WORDS",
    "InvalidArgumentTaxonomy",
    "QueryExpansion",
    "QueryExpansionStage",
    "SuggestedQuery",
    "UnknownExpansionChoice",
    "expand_with_templates",
    "load_argument_taxonomy",
    "model_query_problems",
    "parse_argument_taxonomy",
    "provider_queries",
]

logger = logging.getLogger(__name__)

ARGUMENT_TAXONOMY_PATH: Final = Path("config/argument_taxonomy.yaml")
"""The committed taxonomy, relative to the repository root (and to an installed build's bundled
`config/`, which `scripts/stamp_build.py` copies whole)."""

EXPAND_PROMPT_ID: Final = "search.expand"
"""The registered prompt model expansion runs (`prompts/search/expand.md`)."""

EXPAND_PROMPT_VERSION: Final = "1.0.0"
"""The version of :data:`EXPAND_PROMPT_ID` the stage runs unless it is built with another."""

EXPANSION_TASK_CLASS: Final = TaskClass.HIGH_VOLUME
"""The task class the prompt declares and is routed as: a short, cheap call."""

EXPANSION_POLICY: Final = ValidationPolicy(fail_closed=False)
"""An expansion writes no evidence, so a refused answer falls back to the templates."""

DEFAULT_MAX_MODEL_QUERIES: Final = 3
"""How many extra queries a model is asked for unless the stage is built with another number."""

MAX_MODEL_QUERY_WORDS: Final = 12
"""The longest query a model may suggest, in words: a search query, not a sentence of evidence."""

_MAX_SCHEMA_QUERIES: Final = 5
"""The most suggestions :class:`QueryExpansion` holds, whatever the stage asks for."""


class InvalidArgumentTaxonomy(ConfigurationError):
    """`config/argument_taxonomy.yaml` could not be read, or does not validate."""


class UnknownExpansionChoice(DomainError):
    """A search named an argument, need, topic or variable the taxonomy does not have.

    Carries the valid choices, so the CLI can print them rather than a bare refusal.
    """

    def __init__(self, kind: str, value: str, choices: Sequence[str]) -> None:
        self.kind = kind
        """`argument`, `need`, `topic` or `variable`."""
        self.value = value
        """What the search named, as given."""
        self.choices = tuple(choices)
        """Every valid id, in the taxonomy's order."""
        super().__init__(f"unknown {kind} {value!r}; the {kind}s are: {', '.join(self.choices)}")


# ---------------------------------------------------------------------------------------------
# Loading the taxonomy
# ---------------------------------------------------------------------------------------------


def parse_argument_taxonomy(text: str, *, source: str) -> ArgumentTaxonomy:
    """Read a taxonomy from YAML text; `source` names it in a refusal."""
    try:
        document: object = yaml.safe_load(text)
    except yaml.YAMLError:
        raise InvalidArgumentTaxonomy(f"{source} is not valid YAML", source=source) from None
    if not isinstance(document, dict):
        raise InvalidArgumentTaxonomy(f"{source} must be a mapping of sections", source=source)
    try:
        return ArgumentTaxonomy.model_validate(document)
    except ValidationError as invalid:
        problem = invalid.errors()[0]
        field = ".".join(str(part) for part in problem["loc"])
        where = f"{field}: " if field else ""
        raise InvalidArgumentTaxonomy(
            f"{source}: {where}{problem['msg']}", field=field or None, source=source
        ) from None


def load_argument_taxonomy(path: Path) -> ArgumentTaxonomy:
    """Load the taxonomy at `path` (the committed one is :data:`ARGUMENT_TAXONOMY_PATH`)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as unreadable:
        raise InvalidArgumentTaxonomy(
            f"{path} could not be read: {unreadable.strerror}", source=str(path)
        ) from None
    return parse_argument_taxonomy(text, source=str(path))


# ---------------------------------------------------------------------------------------------
# Template expansion
# ---------------------------------------------------------------------------------------------


def _resolve(
    taxonomy: ArgumentTaxonomy, wanted: ExpansionRequest, query: str
) -> tuple[Argument, Need, dict[str, str]]:
    """The argument and need `wanted` names, and the value of every variable it fills."""
    argument = taxonomy.find_argument(wanted.argument)
    if argument is None:
        raise UnknownExpansionChoice("argument", wanted.argument, [entry.id for entry in taxonomy.arguments])
    need = taxonomy.find_need(wanted.need)
    if need is None:
        raise UnknownExpansionChoice("need", wanted.need, [entry.id for entry in taxonomy.needs])
    values: dict[str, str] = {"query": query}
    if wanted.topic_id is not None:
        topic = taxonomy.find_topic(wanted.topic_id)
        if topic is None:
            raise UnknownExpansionChoice("topic", wanted.topic_id, [entry.id for entry in taxonomy.topics])
        values.update(topic.variables)
    for name in wanted.variables:
        if False:  # SKELETON: any variable
            settable = [variable for variable in taxonomy.variables if variable != "query"]
            raise UnknownExpansionChoice("variable", name, settable)
    values.update(wanted.variables)
    values.setdefault("topic", query)
    return argument, need, values


def _since(days: RecencyDays, filters: SearchFilters, now: datetime) -> tuple[datetime | None, bool]:
    """The `since` a window gives, and whether it is the search's own rather than the window's."""
    if filters.since is not None:
        return filters.since, True
    if days == "any":
        return None, False
    anchor = filters.until if filters.until is not None else now
    return anchor - timedelta(days=days), False


def _expanded(
    text: str,
    *,
    days: RecencyDays,
    source: WindowSource,
    filters: SearchFilters,
    now: datetime,
    template_id: str | None = None,
    template: str | None = None,
    rationale: str | None = None,
) -> ExpandedQuery:
    since, from_request = _since(days, filters, now)
    return ExpandedQuery(
        query=text,
        origin=QueryOrigin.MODEL if rationale is not None else QueryOrigin.TEMPLATE,
        template_id=template_id,
        template=template,
        rationale=rationale,
        since=since,
        recency_days=None if days == "any" else days,
        window=WindowSource.REQUEST if from_request else source,
    )


def _same_query(text: str) -> str:
    return " ".join(text.casefold().split())


def expand_with_templates(taxonomy: ArgumentTaxonomy, request: SearchRequest, *, now: datetime) -> SearchExpansion:
    """The template queries for the request's argument and need, each with its date window.

    Raises :class:`UnknownExpansionChoice` for an argument, need, topic or variable the taxonomy
    does not have, and `ValueError` for a request that names no argument and need.
    """
    wanted = request.expansion
    if wanted is None:
        raise ValueError("the request names no argument and need to expand by")
    argument, need, values = _resolve(taxonomy, wanted, request.query)
    queries: list[ExpandedQuery] = []
    skipped: list[str] = []
    seen: set[str] = set()
    for number, template in enumerate(argument.templates[need.id], start=1):
        template_id = f"{argument.id}/{need.id}/{number}"
        if not template.variables <= values.keys():
            skipped.append(template_id)
            continue
        text = template.render(values)
        if _same_query(text) in seen:
            continue
        seen.add(_same_query(text))
        own_window = template.recency_days is not None
        queries.append(
            _expanded(
                text,
                days=need.recency_days,  # SKELETON: the template's own window is ignored
                source=WindowSource.TEMPLATE if own_window else WindowSource.NEED,
                filters=request.filters,
                now=now,
                template_id=template_id,
                template=template.text,
            )
        )
    return SearchExpansion(
        taxonomy_version=taxonomy.taxonomy_version,
        argument=argument.id,
        need=need.id,
        topic_id=wanted.topic_id,
        variables=values,
        queries=tuple(queries),
        skipped_templates=tuple(skipped),
        model_requested=wanted.use_model,
    )


def provider_queries(expansion: SearchExpansion, filters: SearchFilters) -> tuple[ProviderQuery, ...]:
    """What every provider is asked: each expanded query under the search's filters and its own `since`."""
    return tuple(
        ProviderQuery(query=query.query, filters=filters.evolve(since=query.since)) for query in expansion.queries
    )


# ---------------------------------------------------------------------------------------------
# A model's extra queries
# ---------------------------------------------------------------------------------------------


class SuggestedQuery(DomainModel):
    """One extra query a model suggests, and why, in its own words."""

    query: NonEmptyText = Field(max_length=120, description="A search engine query of a few words.")
    rationale: NonEmptyText = Field(max_length=300, description="One short sentence on what it should find.")


class QueryExpansion(DomainModel):
    """`search.expand`'s output schema: extra queries for one argument and need, with reasons."""

    queries: tuple[SuggestedQuery, ...] = Field(
        max_length=_MAX_SCHEMA_QUERIES, description="Queries the template queries do not already ask."
    )


def model_query_problems(expansion: QueryExpansion, *, max_queries: int) -> list[OutputProblem]:
    """What a schema-valid answer must also satisfy before any of it is asked: no more queries than
    were asked for, each one line of at most :data:`MAX_MODEL_QUERY_WORDS` words and no link.

    The messages never quote the answer.
    """
    problems: list[OutputProblem] = []
    return problems  # SKELETON: no check beyond the schema
    if len(expansion.queries) > max_queries:
        problems.append(
            OutputProblem(
                loc=("queries",), type="too_many_queries", msg=f"at most {max_queries} queries were asked for"
            )
        )
    for index, suggestion in enumerate(expansion.queries):
        where = ("queries", index, "query")
        text = suggestion.query
        if any(not character.isprintable() for character in text):
            problems.append(OutputProblem(loc=where, type="not_one_line", msg="a query is one line of text"))
        if len(text.split()) > MAX_MODEL_QUERY_WORDS:
            problems.append(
                OutputProblem(
                    loc=where, type="query_too_long", msg=f"a query has at most {MAX_MODEL_QUERY_WORDS} words"
                )
            )
        if "://" in text or "www." in text.casefold():
            problems.append(OutputProblem(loc=where, type="query_is_a_link", msg="a query is words, not a link"))
    return problems


class QueryExpansionStage:
    """The expand stage: the request's argument and need turned into the queries to ask."""

    def __init__(
        self,
        taxonomy: ArgumentTaxonomy,
        *,
        clock: Clock,
        guard: StructuredOutputGuard | None = None,
        prompt_version: str = EXPAND_PROMPT_VERSION,
        max_model_queries: int = DEFAULT_MAX_MODEL_QUERIES,
    ) -> None:
        """`guard` is what a model's extra queries are asked through; without one, a request that asks
        for them gets the template queries and a warning."""
        if not 1 <= max_model_queries <= _MAX_SCHEMA_QUERIES:
            raise ValueError(f"max_model_queries is 1 to {_MAX_SCHEMA_QUERIES}, got {max_model_queries}")
        self._taxonomy = taxonomy
        self._clock = clock
        self._guard = guard
        self._prompt_version = prompt_version
        self._max_model_queries = max_model_queries

    def __repr__(self) -> str:
        return f"QueryExpansionStage(taxonomy_version={self._taxonomy.taxonomy_version!r})"

    async def run(self, state: SearchState) -> SearchState:
        """Expand when the request names an argument and need; otherwise change nothing."""
        wanted = state.request.expansion
        if wanted is None:
            return state
        now = self._clock.now()
        expansion = expand_with_templates(self._taxonomy, state.request, now=now)
        if wanted.use_model:
            expansion = await self._with_model_queries(expansion, state.request, now)
        return state.evolve(queries=provider_queries(expansion, state.request.filters), expansion=expansion)

    async def _with_model_queries(
        self, expansion: SearchExpansion, request: SearchRequest, now: datetime
    ) -> SearchExpansion:
        """`expansion` with a model's validated suggestions after its template queries, or with a
        warning and nothing added when there are none to add."""
        if self._guard is None:
            return self._fell_back(expansion, "model expansion is not configured", code=None)
        argument = self._taxonomy.find_argument(expansion.argument)
        need = self._taxonomy.need(expansion.need)
        assert argument is not None  # the expansion was resolved against this taxonomy
        prompt = ModelPrompt(
            prompt_id=EXPAND_PROMPT_ID,
            prompt_version=self._prompt_version,
            variables={
                "argument": f"{argument.label} ({argument.kind.value})",
                "need": need.label,
                "need_description": need.description,
                "query": request.query,
                "topic": expansion.variables["topic"],
                "template_queries": "\n".join(f"- {query.query}" for query in expansion.queries),
                "max_queries": self._max_model_queries,
            },
        )
        try:
            result = await self._guard.generate(
                EXPANSION_TASK_CLASS,
                prompt,
                QueryExpansion,
                policy=EXPANSION_POLICY,
                check=partial(model_query_problems, max_queries=self._max_model_queries),
            )
        except ModelOutputError as refused:  # SKELETON: never caught
            raise
            return self._fell_back(
                expansion, "the model's queries did not validate after one repair", code=error_code_of(refused)
            )
        except (ProviderError, BudgetExceededError) as unavailable:  # SKELETON: never caught
            raise
            return self._fell_back(expansion, "the model could not be asked", code=error_code_of(unavailable))
        seen = {_same_query(query.query) for query in expansion.queries}
        added: list[ExpandedQuery] = []
        for suggestion in result.output.queries:
            text = " ".join(suggestion.query.split())
            if _same_query(text) in seen:
                continue
            seen.add(_same_query(text))
            added.append(
                _expanded(
                    text,
                    days=need.recency_days,
                    source=WindowSource.NEED,
                    filters=request.filters,
                    now=now,
                    rationale=suggestion.rationale,
                )
            )
        if not added:
            return self._fell_back(expansion, "the model suggested no query the templates do not ask", code=None)
        return expansion.evolve(queries=(*expansion.queries, *added), model=result.metadata)

    @staticmethod
    def _fell_back(expansion: SearchExpansion, reason: str, *, code: str | None) -> SearchExpansion:
        warning = f"{reason}; searched with the template queries alone" + (f" ({code})" if code else "")
        logger.warning(
            "query expansion used its templates alone",
            extra={"argument": expansion.argument, "need": expansion.need, "error_code": code},
        )
        return expansion.evolve(warning=warning)

