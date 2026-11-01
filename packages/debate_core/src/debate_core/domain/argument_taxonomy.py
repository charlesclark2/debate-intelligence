"""The argument/need taxonomy a federated search expands its query with (v1-e08-t04).

A debater looking for new evidence usually knows two things besides the words they type: which
argument the card is for (a politics DA, the economy advantage, a util framework) and which part of
that argument it has to prove (uniqueness, a link, an internal link, an impact, or an answer to the
other side's version). `config/argument_taxonomy.yaml` writes both down, with the search queries
each pair expands into and how recent the evidence for each need should be:

* :class:`Need` — one part of an argument, with its default **recency window**: uniqueness is about
  the status quo and wants the last week or two, while an impact card can be older scholarship.
* :class:`Argument` — one argument a debater researches, the events it is read in, and, for every
  need, at least one :class:`QueryTemplate`.
* :class:`QueryTemplate` — query text with variables such as `{query}`, `{topic}` and `{bill}`,
  and, when the need's default does not fit, a window of its own.
* :class:`TopicPreset` — the values a topic gives its variables, taken from what is committed
  (`config/landscape/topics.yaml`'s resolutions), never from memory.

:class:`ArgumentTaxonomy` validates the whole file when it loads. Every (argument, need) pair has at
least one template that needs only the variables a search always has (:data:`ALWAYS_GIVEN_VARIABLES`),
so any pair expands into at least one query whatever else the request gives. A template names only
variables the file declares, and never a hard-coded current event: what changes week to week is a
variable the request fills.

The ids of arguments that also exist in the Policy landscape taxonomy (`config/landscape/taxonomies/`)
are the landscape's own ids, and each says so in `landscape_id`. Nothing here reads the landscape
files: the shared names are what joins them.

Nothing in this module does I/O. The application layer reads the file
(:mod:`debate_core.application.query_expansion`).
"""

from __future__ import annotations

import re
import string
from collections import Counter
from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Annotated, Final, Literal, Self

from pydantic import AfterValidator, Field, PositiveInt, model_validator

from debate_core.domain.base import DomainModel, NonEmptyText
from debate_core.domain.caselist.values import Event

__all__ = [
    "ALWAYS_GIVEN_VARIABLES",
    "ARGUMENT_TAXONOMY_SCHEMA_VERSION",
    "Argument",
    "ArgumentKind",
    "ArgumentTaxonomy",
    "Need",
    "QueryTemplate",
    "RecencyDays",
    "ReviewStatus",
    "TopicPreset",
    "normalized_choice",
    "template_variables",
]

ARGUMENT_TAXONOMY_SCHEMA_VERSION: Final = 1
"""The shape of `config/argument_taxonomy.yaml` this module reads."""

ALWAYS_GIVEN_VARIABLES: Final = frozenset({"query", "topic"})
"""The variables every expansion has a value for: the search's own query, and its topic, which is
the request's or its topic preset's and otherwise the query itself."""

_ID_PATTERN: Final = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_VARIABLE_PATTERN: Final = re.compile(r"^[a-z][a-z0-9_]*$")
_SEMVER_PATTERN: Final = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def normalized_choice(value: str) -> str:
    """How a typed argument or need is compared with ids and aliases: trimmed, lower case, and with
    spaces and underscores read as hyphens, so `Politics DA`, `politics_da` and `politics-da` match."""
    return re.sub(r"[\s_]+", "-", value.strip().lower())


def _check_id(value: str) -> str:
    if not _ID_PATTERN.fullmatch(value):
        raise ValueError(f"{value!r} is not a lower-case id of letters, digits and single hyphens")
    return value


Slug = Annotated[str, AfterValidator(_check_id)]
"""An argument, need or topic id, or an alias: `politics-da`, `internal-link`."""

type RecencyDays = PositiveInt | Literal["any"]
"""How recent evidence should be: published in the last N days, or `any` age."""


def template_variables(text: str) -> frozenset[str]:
    """The variables a template names, refusing anything but plain `{name}` fields.

    `{{` and `}}` are literal braces. A positional field (`{}`, `{0}`), an attribute or index
    (`{bill.name}`, `{bill[0]}`), a conversion (`{bill!r}`) or a format spec (`{bill:>9}`) is refused.
    """
    try:
        parsed = list(string.Formatter().parse(text))
    except ValueError as malformed:
        raise ValueError(f"template {text!r} is not valid: {malformed}") from None
    names: set[str] = set()
    for _, field_name, format_spec, conversion in parsed:
        if field_name is None:
            continue
        if not _VARIABLE_PATTERN.fullmatch(field_name) or format_spec or conversion:
            raise ValueError(
                f"template {text!r} has the field {{{field_name}}}; a template names a variable as "
                "{name}, with nothing else inside the braces"
            )
        names.add(field_name)
    return frozenset(names)


class ReviewStatus(StrEnum):
    """Whether the coach has looked at an entry, as `config/feeds/` marks its feeds."""

    AWAITING_COACH_REVIEW = "awaiting_coach_review"
    COACH_REVIEWED = "coach_reviewed"


class ArgumentKind(StrEnum):
    """What sort of argument an entry is, in the words debaters use."""

    DA = "da"
    """A disadvantage: a reason the plan or action is bad."""

    ADVANTAGE = "advantage"
    """A reason the plan or action is good."""

    FRAMEWORK = "framework"
    """A way of weighing the round: util, deontology, structural violence, cost-benefit."""

    THEORY = "theory"
    """An argument about the rules of debate."""


class Need(DomainModel):
    """One part of an argument a card has to prove, and how recent its evidence should be."""

    id: Slug = Field(description="The need's id, as `--need` takes it: `uniqueness`, `internal-link`.")
    label: NonEmptyText = Field(description="The need as a debater says it.")
    description: NonEmptyText = Field(description="What a card for this need shows.")
    aliases: tuple[Slug, ...] = Field(default=(), description="Other spellings `--need` accepts: `uq`, `at`.")
    recency_days: RecencyDays = Field(
        description="The default window: evidence from the last N days, or `any` age."
    )


class QueryTemplate(DomainModel):
    """One query an (argument, need) pair expands into, with its variables still in braces."""

    text: NonEmptyText = Field(description="The query, naming variables as {query}, {topic}, {bill}.")
    recency_days: RecencyDays | None = Field(
        default=None, description="This template's own window; None takes the need's."
    )

    @model_validator(mode="after")
    def _check_fields(self) -> Self:
        template_variables(self.text)
        return self

    @property
    def variables(self) -> frozenset[str]:
        """The variables the template names."""
        return template_variables(self.text)

    def render(self, values: Mapping[str, str]) -> str:
        """The query with every variable filled from `values`, its spaces collapsed.

        Raises `KeyError` for a variable `values` does not have; :meth:`variables` says which.
        """
        parts: list[str] = []
        for literal, field_name, _, _ in string.Formatter().parse(self.text):
            parts.append(literal)
            if field_name is not None:
                parts.append(values[field_name])
        return " ".join("".join(parts).split())


class Argument(DomainModel):
    """One argument a debater researches, and what each of its needs expands into."""

    id: Slug = Field(description="The argument's id, as `--argument` takes it: `politics-da`.")
    label: NonEmptyText = Field(description="The argument as a debater names it.")
    kind: ArgumentKind = Field(description="DA, advantage, framework or theory.")
    formats: tuple[Event, ...] = Field(min_length=1, description="The events it is read in.")
    aliases: tuple[Slug, ...] = Field(default=(), description="Other spellings `--argument` accepts.")
    landscape_id: Slug | None = Field(
        default=None,
        description=(
            "The same argument's id in the landscape taxonomies, when it has one there; it is then "
            "also this entry's id. None for an argument the landscape does not count."
        ),
    )
    review: ReviewStatus = Field(description="Whether the coach has reviewed this entry.")
    note: NonEmptyText | None = Field(
        default=None, description="Anything the coach should know when reviewing."
    )
    templates: dict[Slug, tuple[QueryTemplate, ...]] = Field(
        description="Each need's id, and the templates it expands into, in order."
    )


class TopicPreset(DomainModel):
    """The variable values one topic gives every expansion on it."""

    id: Slug = Field(description="The topic's id in `config/landscape/topics.yaml`.")
    format: Event = Field(description="The event the topic is debated in.")
    variables: dict[str, NonEmptyText] = Field(
        min_length=1, description="Variable values, each taken word for word from the committed resolution."
    )


def _repeated(values: Iterable[str]) -> list[str]:
    return sorted(value for value, count in Counter(values).items() if count > 1)


class ArgumentTaxonomy(DomainModel):
    """`config/argument_taxonomy.yaml`, validated whole when it loads."""

    schema_version: Literal[1] = Field(description="The file's shape: 1.")
    taxonomy_version: NonEmptyText = Field(description="MAJOR.MINOR.PATCH, raised on every reviewed change.")
    variables: dict[str, NonEmptyText] = Field(
        description="Every variable a template may name, with what fills it. Must declare query and topic."
    )
    needs: tuple[Need, ...] = Field(min_length=1, description="Every need, in the order they are listed.")
    arguments: tuple[Argument, ...] = Field(min_length=1, description="Every argument, in the order listed.")
    topics: tuple[TopicPreset, ...] = Field(default=(), description="Topic presets, by landscape topic id.")

    @model_validator(mode="after")
    def _check_taxonomy(self) -> Self:
        if not _SEMVER_PATTERN.fullmatch(self.taxonomy_version):
            raise ValueError(f"taxonomy_version {self.taxonomy_version!r} is not MAJOR.MINOR.PATCH")
        self._check_variables()
        self._check_names()
        need_ids = [need.id for need in self.needs]
        for argument in self.arguments:
            self._check_templates(argument, need_ids)
        for topic in self.topics:
            unknown = sorted(set(topic.variables) - set(self.variables))
            if unknown or "query" in topic.variables:
                raise ValueError(
                    f"topic {topic.id} sets {', '.join(unknown) or 'query'}; a topic sets declared "
                    "variables other than query"
                )
        return self

    def _check_variables(self) -> None:
        bad = sorted(name for name in self.variables if not _VARIABLE_PATTERN.fullmatch(name))
        if bad:
            raise ValueError(f"variable names are lower-case words: {', '.join(bad)}")
        missing = sorted(ALWAYS_GIVEN_VARIABLES - set(self.variables))
        if missing:
            raise ValueError(f"variables must declare {', '.join(missing)}")

    def _check_names(self) -> None:
        for what, entries in (("need", self.needs), ("argument", self.arguments)):
            names = [entry.id for entry in entries] + [alias for entry in entries for alias in entry.aliases]
            repeated = _repeated(names)
            if repeated:
                raise ValueError(f"two {what}s share the id or alias {', '.join(repeated)}")
        repeated = _repeated(topic.id for topic in self.topics)
        if repeated:
            raise ValueError(f"two topics share the id {', '.join(repeated)}")
        for argument in self.arguments:
            if argument.landscape_id is not None and argument.landscape_id != argument.id:
                raise ValueError(
                    f"argument {argument.id} names landscape_id {argument.landscape_id}; an argument "
                    "the landscape also counts takes the landscape's id"
                )

    def _check_templates(self, argument: Argument, need_ids: list[str]) -> None:
        unknown = sorted(set(argument.templates) - set(need_ids))
        if unknown:
            raise ValueError(
                f"argument {argument.id} has templates for {', '.join(unknown)}, which is not a need; "
                f"the needs are {', '.join(need_ids)}"
            )
        for need_id in need_ids:
            templates = argument.templates.get(need_id, ())
            if not templates:
                raise ValueError(f"argument {argument.id} has no template for the need {need_id}")
            for template in templates:
                undeclared = sorted(template.variables - set(self.variables))
                if undeclared:
                    raise ValueError(
                        f"{argument.id}/{need_id}: template {template.text!r} names "
                        f"{', '.join(undeclared)}, which variables does not declare"
                    )
            if not any(template.variables <= ALWAYS_GIVEN_VARIABLES for template in templates):
                raise ValueError(
                    f"{argument.id}/{need_id}: every template needs a variable a search may not have; "
                    f"at least one may name only {' and '.join(sorted(ALWAYS_GIVEN_VARIABLES))}"
                )

    def find_argument(self, name: str) -> Argument | None:
        """The argument `name` is the id or an alias of, compared as :func:`normalized_choice` says."""
        wanted = normalized_choice(name)
        return next(
            (argument for argument in self.arguments if wanted in (argument.id, *argument.aliases)), None
        )

    def find_need(self, name: str) -> Need | None:
        """The need `name` is the id or an alias of, compared as :func:`normalized_choice` says."""
        wanted = normalized_choice(name)
        return next((need for need in self.needs if wanted in (need.id, *need.aliases)), None)

    def find_topic(self, topic_id: str) -> TopicPreset | None:
        """The topic preset with this id."""
        wanted = normalized_choice(topic_id)
        return next((topic for topic in self.topics if topic.id == wanted), None)

    def need(self, need_id: str) -> Need:
        """The need with exactly this id; `KeyError` when there is none."""
        for need in self.needs:
            if need.id == need_id:
                return need
        raise KeyError(need_id)
