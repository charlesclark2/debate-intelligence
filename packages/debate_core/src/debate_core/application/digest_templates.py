"""`config/daily_templates.yaml`: what `daily` asks in place of the taxonomy's templates (v1-e08-t25).

The PM's ruling of 2026-11-12. The feed provider keeps an item only when every word of a query is in
its title or summary, and on the operator's run of 2026-11-12 no filled uniqueness template of the
politics preset kept any of the 42 items of the day before. So a digest asks templates of its own,
two words each: the preset's query and one more word (`{query} Congress`). `search`, the feed
provider's every-word rule and every template in `config/argument_taxonomy.yaml` are unchanged.

## The file

One group per argument/need pair, by taxonomy id, each with its templates in order. A template is
`{query} <word>` or `<word> {query}` and nothing else; `queries`, when given, are the preset queries
it is asked for (the measured ones), and otherwise it is asked for every query of every preset with
the pair. :func:`load_digest_templates` reads and shapes the file; :func:`check_digest_templates`
checks every pair and every listed query against the taxonomy and the presets, so a mistake stops
every `daily` run when the file is loaded, naming the group.

## What a digest's search asks (:meth:`DigestTemplates.queries_for`)

* A pair with a group: each of its templates whose `queries` include the search's query, filled in,
  with the id `digest/<argument>/<need>/<n>`, its n-th template. When none is for that query the
  digest does not run that search (:class:`~debate_core.application.digest_service.DigestService`).
* A pair with no group: **the taxonomy's templates, exactly as before v1-e08-t25**, and the digest
  names the group as asked that way, so it is never silent (the PM's ruling C of 2026-11-12). The
  every-word rule is the feed provider's alone, and a reviewed template does its work against OpenAlex,
  Crossref and the government sources, so a pair is changed only once it has digest templates: today
  the politics preset's.

:class:`DigestExpansionStage` is the expand stage of the federated search `daily` runs: for a pair with
a group it records those queries as the search's expansion, for the search's own `since` and `until`;
for a pair without one it is the taxonomy's own stage,
:class:`~debate_core.application.query_expansion.QueryExpansionStage`.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, Self

import yaml
from pydantic import Field, ValidationError, field_validator, model_validator

from debate_core.application.federated_search_types import SearchState
from debate_core.application.ports.providers import Clock
from debate_core.application.query_expansion import QueryExpansionStage, provider_queries
from debate_core.domain.argument_taxonomy import ArgumentTaxonomy
from debate_core.domain.base import DomainModel, NonEmptyText
from debate_core.domain.daily_preset import DailyPresets
from debate_core.domain.search import ExpandedQuery, QueryOrigin, SearchExpansion, WindowSource

__all__ = [
    "DAILY_TEMPLATES_PATH",
    "DigestExpansionStage",
    "DigestQuery",
    "DigestTemplate",
    "DigestTemplateError",
    "DigestTemplateGroup",
    "DigestTemplates",
    "check_digest_templates",
    "load_digest_templates",
]

DAILY_TEMPLATES_PATH: Final = Path("config") / "daily_templates.yaml"
"""Where the digest templates are committed, relative to the repository root or an installed build's copy."""

QUERY_VARIABLE: Final = "{query}"

_TWO_WORDS: Final = re.compile(r"^(?:\{query\} [^\s{}]+|[^\s{}]+ \{query\})$")


class DigestTemplateError(ValueError):
    """The digest templates file could not be read, or names something that does not exist."""


class DigestTemplate(DomainModel):
    """One digest template: the preset's query and one word."""

    text: NonEmptyText = Field(description="`{query} <word>` or `<word> {query}`: two words, no more.")
    queries: tuple[NonEmptyText, ...] | None = Field(
        default=None,
        min_length=1,
        description="The preset queries it is asked for, as spelled in the presets; all when left out.",
    )

    @field_validator("text")
    @classmethod
    def _two_words(cls, value: str) -> str:
        if not _TWO_WORDS.fullmatch(value):
            raise ValueError(
                "a digest template is the query and one word, `{query} <word>` or `<word> {query}`"
            )
        return value

    def asked_for(self, query: str) -> bool:
        """Whether a search for `query` asks this template."""
        return self.queries is None or query in self.queries

    def render(self, query: str) -> str:
        return self.text.replace(QUERY_VARIABLE, query)


class DigestTemplateGroup(DomainModel):
    """One argument/need pair's digest templates, in the order a digest asks them."""

    argument: NonEmptyText = Field(description="The argument's taxonomy id, not an alias.")
    need: NonEmptyText = Field(description="The need's id in the argument's family.")
    templates: tuple[DigestTemplate, ...] = Field(min_length=1)

    @property
    def pair(self) -> str:
        return f"{self.argument}/{self.need}"


@dataclass(frozen=True, slots=True)
class DigestQuery:
    """One query a digest's search asks, and the template it was filled from."""

    template_id: str
    template: str
    query: str


class DigestTemplates(DomainModel):
    """Every pair's digest templates: `config/daily_templates.yaml`."""

    schema_version: Literal[1] = 1
    groups: tuple[DigestTemplateGroup, ...] = ()

    @model_validator(mode="after")
    def _each_pair_once(self) -> Self:
        pairs = [group.pair for group in self.groups]
        twice = sorted({pair for pair in pairs if pairs.count(pair) > 1})
        if twice:
            raise ValueError(f"a pair has one group of templates; listed more than once: {', '.join(twice)}")
        return self

    def group(self, argument: str, need: str) -> DigestTemplateGroup | None:
        return next((g for g in self.groups if (g.argument, g.need) == (argument, need)), None)

    def asks_taxonomy(self, argument: str, need: str) -> bool:
        """Whether the pair has no digest templates, so its searches ask the taxonomy's, as before."""
        return self.group(argument, need) is None

    def queries_for(self, argument: str, need: str, query: str) -> tuple[DigestQuery, ...]:
        """The digest templates a search for `query` on the pair asks; none for a pair without a group,
        which asks the taxonomy's (:meth:`asks_taxonomy`)."""
        group = self.group(argument, need)
        if group is None:
            return ()
        return tuple(
            DigestQuery(f"digest/{group.pair}/{number}", template.text, template.render(query))
            for number, template in enumerate(group.templates, start=1)
            if template.asked_for(query)
        )


def load_digest_templates(path: Path) -> DigestTemplates:
    """Read and shape the file; :class:`DigestTemplateError` names the file and what is wrong."""
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise DigestTemplateError(f"{path}: cannot be read: {error}") from error
    try:
        return DigestTemplates.model_validate(document)
    except ValidationError as error:
        raise DigestTemplateError(f"{path}: {error}") from error


def check_digest_templates(
    templates: DigestTemplates, presets: DailyPresets, taxonomy: ArgumentTaxonomy, *, source: str
) -> DigestTemplates:
    """`templates`, once every group's pair is the taxonomy's and every listed query a preset's."""
    for group in templates.groups:
        problem = _pair_problem(group, taxonomy) or _query_problem(group, presets)
        if problem is not None:
            raise DigestTemplateError(f"{source}: group {group.pair}: {problem}")
    return templates


def _pair_problem(group: DigestTemplateGroup, taxonomy: ArgumentTaxonomy) -> str | None:
    argument = taxonomy.find_argument(group.argument)
    if argument is None or argument.id != group.argument:
        known = f"; did you mean {argument.id!r}" if argument is not None else ""
        return f"the taxonomy has no argument with the id {group.argument!r}{known}"
    needs = [need.id for need in taxonomy.family_of(argument).needs]
    if group.need not in needs:
        return f"{group.argument} has no need with the id {group.need!r}; its needs are {', '.join(needs)}"
    return None


def _query_problem(group: DigestTemplateGroup, presets: DailyPresets) -> str | None:
    asked: Collection[str] = {
        query
        for preset in presets.presets
        if any((pair.argument, pair.need) == (group.argument, group.need) for pair in preset.pairs)
        for query in preset.queries
    }
    for template in group.templates:
        for query in template.queries or ():
            if query not in asked:
                return (
                    f"template {template.text!r} is for the query {query!r}, which no preset with this "
                    "pair asks"
                )
    return None


class DigestExpansionStage:
    """`daily`'s expand stage: the digest templates' queries, never the taxonomy's (module docstring)."""

    def __init__(self, taxonomy: ArgumentTaxonomy, templates: DigestTemplates, *, clock: Clock) -> None:
        self._taxonomy = taxonomy
        self._templates = templates
        self._taxonomys = QueryExpansionStage(taxonomy, clock=clock)

    def __repr__(self) -> str:
        return f"DigestExpansionStage(groups={len(self._templates.groups)})"

    async def run(self, state: SearchState) -> SearchState:
        request = state.request
        wanted = request.expansion
        if wanted is None:
            raise ValueError("a digest's search is always for an argument and need; this one was not")
        if self._templates.asks_taxonomy(wanted.argument, wanted.need):
            return await self._taxonomys.run(state)
        asked = self._templates.queries_for(wanted.argument, wanted.need, request.query)
        if not asked:
            raise ValueError(
                f"no digest template of {wanted.argument}/{wanted.need} is for {request.query!r}; "
                "the digest does not ask that search"
            )
        expansion = SearchExpansion(
            taxonomy_version=self._taxonomy.taxonomy_version,
            argument=wanted.argument,
            need=wanted.need,
            topic_id=wanted.topic_id,
            variables={"query": request.query},
            queries=tuple(
                ExpandedQuery(
                    query=query.query,
                    origin=QueryOrigin.TEMPLATE,
                    template_id=query.template_id,
                    template=query.template,
                    since=request.filters.since,
                    window=WindowSource.REQUEST,
                )
                for query in asked
            ),
        )
        return state.evolve(queries=provider_queries(expansion, request.filters), expansion=expansion)
