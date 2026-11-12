"""The argument/need taxonomy a federated search expands its query with (v1-e08-t04).

A debater looking for new evidence usually knows two things besides the words they type: which
argument the card is for (a politics DA, the economy advantage, a util framework, the states CP) and
which part of that argument it has to prove (a DA's uniqueness or link, a framework's reasons it is
good, a counterplan's solvency, a kritik's alternative, or an answer to the other side's version).
`config/argument_taxonomy.yaml` writes both down, with the search queries each pair expands into and
how recent the evidence for each need should be:

* :class:`NeedFamily` — the needs one family of arguments has (v1-e08-t08): DAs and advantages have
  uniqueness, link, internal link, impact and answers; a framework has only "framework good" and
  answers; theory, counterplans and kritiks each have their own. The family is chosen by the
  argument's kind, so an argument names it by being a `da`, a `framework` or a `cp`.
* :class:`Need` — one part of an argument, with its default **recency window**: uniqueness is about
  the status quo and wants recent evidence, while an impact card or a philosophy card can be any age.
* :class:`Argument` — one argument a debater researches, the events it is read in, and, for every
  need of its family, at least one :class:`QueryTemplate`.
* :class:`QueryTemplate` — query text with variables such as `{query}`, `{topic}` and `{bill}`,
  and, when the need's default does not fit, a window of its own.
* :class:`TopicPreset` — the values a topic gives its variables, taken from what is committed
  (`config/landscape/topics.yaml`'s resolutions), never from memory, the plan mechanisms of its
  affirmatives (:class:`TopicMechanism`, v1-e08-t14) that a DA's link search names, and the link
  templates each DA's mechanism queries cross (:class:`MechanismLinkTemplate`, v1-e08-t16).

:class:`ArgumentTaxonomy` validates the whole file when it loads. Every argument has templates for
exactly its family's needs, and every (argument, need) pair has at least one template that needs
only the variables a search always has (:data:`ALWAYS_GIVEN_VARIABLES`), so any pair expands into at
least one query whatever else the request gives. A template names only variables the file declares,
and never a hard-coded current event: what changes week to week is a variable the request fills.

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
    "MAX_QUERIES_PER_SEARCH",
    "MECHANISM_NEED",
    "Argument",
    "ArgumentKind",
    "ArgumentTaxonomy",
    "MechanismLinkTemplate",
    "Need",
    "NeedFamily",
    "QueryTemplate",
    "RecencyDays",
    "ReviewStatus",
    "TopicMechanism",
    "TopicPreset",
    "normalized_choice",
    "template_variables",
]

ARGUMENT_TAXONOMY_SCHEMA_VERSION: Final = 2
"""The shape of `config/argument_taxonomy.yaml` this module reads: 2 since v1-e08-t08 gave each argument
family its own needs."""

ALWAYS_GIVEN_VARIABLES: Final = frozenset({"query", "topic"})
"""The variables every expansion has a value for: the search's own query, and its topic, which is
the request's or its topic preset's and otherwise the query itself."""

MAX_QUERIES_PER_SEARCH: Final = 42
"""The most template queries one search asks (the PM's ruling on v1-e08-t16).

Since v1-e08-t10 OpenAlex is asked every query of a search in one joined request per page, split
only when its URL passes 3,500 characters (`openalex.py`'s `MAX_URL_CHARS`). Measured on the
committed politics DA link templates at `--max-results 200`, 42 queries fit one request with room for
a typed query of about 100 characters, and 47 leave no room for a typed query or a model's extra
queries. A topic preset's mechanisms and crossed templates may not take any DA's link search past
it, and no (argument, need) pair has more templates than it. A model's extra queries
(`--expand-llm`, at most five) are not counted."""

MECHANISM_NEED: Final = "link"
"""The need whose queries a topic's plan mechanisms are crossed with: a DA's link (v1-e08-t14)."""

_ID_PATTERN: Final = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_VARIABLE_PATTERN: Final = re.compile(r"^[a-z][a-z0-9_]*$")
_SEMVER_PATTERN: Final = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_TEMPLATE_ID_PATTERN: Final = re.compile(
    r"^([a-z0-9]+(?:-[a-z0-9]+)*)/([a-z0-9]+(?:-[a-z0-9]+)*)/([1-9][0-9]*)$"
)


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

    COUNTERPLAN = "cp"
    """A policy the negative reads instead of the plan: the states CP, a process CP."""

    KRITIK = "k"
    """A K: a criticism of the affirmative's assumptions, with an alternative."""


class Need(DomainModel):
    """One part of an argument a card has to prove, and how recent its evidence should be."""

    id: Slug = Field(description="The need's id, as `--need` takes it: `uniqueness`, `internal-link`.")
    label: NonEmptyText = Field(description="The need as a debater says it.")
    description: NonEmptyText = Field(description="What a card for this need shows.")
    aliases: tuple[Slug, ...] = Field(default=(), description="Other spellings `--need` accepts: `uq`, `at`.")
    recency_days: RecencyDays = Field(
        description="The default window: evidence from the last N days, or `any` age."
    )


class NeedFamily(DomainModel):
    """The needs one family of arguments has, and the kinds of argument in it."""

    id: Slug = Field(description="The family's id: `da-and-advantage`, `framing`, `counterplan`.")
    label: NonEmptyText = Field(description="The family as a debater says it.")
    kinds: tuple[ArgumentKind, ...] = Field(min_length=1, description="The kinds of argument it holds.")
    needs: tuple[Need, ...] = Field(min_length=1, description="Its needs, in the order they are listed.")

    def find_need(self, name: str) -> Need | None:
        """The need of this family that `name` is the id or an alias of, compared as
        :func:`normalized_choice` says."""
        wanted = normalized_choice(name)
        return next((need for need in self.needs if wanted in (need.id, *need.aliases)), None)

    def need(self, need_id: str) -> Need:
        """The need of this family with exactly this id; `KeyError` when there is none."""
        for need in self.needs:
            if need.id == need_id:
                return need
        raise KeyError(need_id)


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
    kind: ArgumentKind = Field(
        description="DA, advantage, framework, theory, counterplan or kritik; it chooses the family."
    )
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
        description="Each need of the argument's family, and the templates it expands into, in order."
    )


class TopicMechanism(DomainModel):
    """One plan mechanism the topic's affirmatives use, which a DA's link search names (v1-e08-t14).

    The coach's rule: generic resolution links are fine, but links are usually to the mechanism of
    the plan text.
    """

    landscape_id: Slug = Field(
        description="The affirmative position's id in the topic's landscape taxonomy: `single-payer-aff`."
    )
    label: NonEmptyText = Field(description="That position's label in the landscape taxonomy.")
    phrase: NonEmptyText = Field(
        description="The words a search names the mechanism with, which the coach edits: `single payer`."
    )


class MechanismLinkTemplate(DomainModel):
    """One link template a DA's mechanism queries cross on a topic (v1-e08-t16).

    Either one of the DA's own link templates, named by its id (`politics-da/link/4`) with its text,
    which the loader checks so that a reordered entry is refused rather than silently crossing another
    template; or a crossing-only template of the preset's own, naming its DA by `argument`, which no
    search without the topic asks. Either names only `{query}` and `{topic}`.
    """

    template_id: NonEmptyText | None = Field(
        default=None,
        description="A DA link template's id, as a search records it: `politics-da/link/4`.",
    )
    argument: Slug | None = Field(
        default=None,
        description="For a crossing-only template, the id of the DA whose mechanism queries cross it.",
    )
    text: NonEmptyText = Field(
        description="The template: for a DA template its text word for word, otherwise the preset's own."
    )

    @model_validator(mode="after")
    def _check_fields(self) -> Self:
        if (self.template_id is None) == (self.argument is None):
            raise ValueError("a mechanism link template names either a template_id or an argument, not both")
        template_variables(self.text)
        return self

    @property
    def argument_id(self) -> str:
        """The DA this entry belongs to."""
        if self.argument is not None:
            return self.argument
        assert self.template_id is not None
        return self.template_id.split("/", 1)[0]


class TopicPreset(DomainModel):
    """The variable values one topic gives every expansion on it, and its affirmatives' mechanisms."""

    id: Slug = Field(description="The topic's id in `config/landscape/topics.yaml`.")
    format: Event = Field(description="The event the topic is debated in.")
    review: ReviewStatus = Field(description="Whether the coach has reviewed this preset.")
    variables: dict[str, NonEmptyText] = Field(
        min_length=1, description="Variable values, each taken word for word from the committed resolution."
    )
    mechanisms: tuple[TopicMechanism, ...] = Field(
        default=(),
        description=(
            "The plan mechanisms a DA's link search on the topic names, in order; none means its "
            "link searches are the templates' alone."
        ),
    )
    mechanism_link_templates: tuple[MechanismLinkTemplate, ...] = Field(
        default=(),
        description=(
            "The link templates each DA's mechanism queries cross, in order; a DA not named crosses "
            "its first link template that names only {query} and {topic}."
        ),
    )


def _repeated(values: Iterable[str]) -> list[str]:
    return sorted(value for value, count in Counter(values).items() if count > 1)


def _check_mechanisms(topic: TopicPreset) -> None:
    """A topic's mechanisms are distinct and in words, and, when it names any, it sets the topic and
    the country their queries are built on."""
    if not topic.mechanisms:
        return
    missing = [name for name in ("topic", "country") if name not in topic.variables]
    if missing:
        raise ValueError(f"topic {topic.id} names plan mechanisms, so it sets {' and '.join(missing)}")
    repeated = _repeated(mechanism.landscape_id for mechanism in topic.mechanisms)
    if repeated:
        raise ValueError(
            f"two plan mechanisms of topic {topic.id} share the landscape id {', '.join(repeated)}"
        )
    repeated = _repeated(" ".join(mechanism.phrase.casefold().split()) for mechanism in topic.mechanisms)
    if repeated:
        raise ValueError(f"two plan mechanisms of topic {topic.id} share the phrase {', '.join(repeated)}")
    for mechanism in topic.mechanisms:
        if any(character.isdigit() for character in mechanism.phrase):
            raise ValueError(
                f"topic {topic.id}: the phrase {mechanism.phrase!r} has a digit; a phrase names a "
                "mechanism in words"
            )


class ArgumentTaxonomy(DomainModel):
    """`config/argument_taxonomy.yaml`, validated whole when it loads."""

    schema_version: Literal[2] = Field(description="The file's shape: 2.")
    taxonomy_version: NonEmptyText = Field(description="MAJOR.MINOR.PATCH, raised on every reviewed change.")
    variables: dict[str, NonEmptyText] = Field(
        description="Every variable a template may name, with what fills it. Must declare query and topic."
    )
    families: tuple[NeedFamily, ...] = Field(
        min_length=1, description="Every argument family and its needs, in the order they are listed."
    )
    arguments: tuple[Argument, ...] = Field(min_length=1, description="Every argument, in the order listed.")
    topics: tuple[TopicPreset, ...] = Field(default=(), description="Topic presets, by landscape topic id.")

    @model_validator(mode="after")
    def _check_taxonomy(self) -> Self:
        if not _SEMVER_PATTERN.fullmatch(self.taxonomy_version):
            raise ValueError(f"taxonomy_version {self.taxonomy_version!r} is not MAJOR.MINOR.PATCH")
        self._check_variables()
        self._check_families()
        self._check_names()
        for argument in self.arguments:
            self._check_templates(argument, self._family_of_kind(argument))
        for topic in self.topics:
            unknown = sorted(set(topic.variables) - set(self.variables))
            if unknown or "query" in topic.variables:
                raise ValueError(
                    f"topic {topic.id} sets {', '.join(unknown) or 'query'}; a topic sets declared "
                    "variables other than query"
                )
            _check_mechanisms(topic)
            self._check_mechanism_links(topic)
        return self

    def _check_variables(self) -> None:
        bad = sorted(name for name in self.variables if not _VARIABLE_PATTERN.fullmatch(name))
        if bad:
            raise ValueError(f"variable names are lower-case words: {', '.join(bad)}")
        missing = sorted(ALWAYS_GIVEN_VARIABLES - set(self.variables))
        if missing:
            raise ValueError(f"variables must declare {', '.join(missing)}")

    def _check_families(self) -> None:
        repeated = _repeated(family.id for family in self.families)
        if repeated:
            raise ValueError(f"two families share the id {', '.join(repeated)}")
        repeated = _repeated(kind.value for family in self.families for kind in family.kinds)
        if repeated:
            raise ValueError(f"two families take the kind {', '.join(repeated)}")
        meanings: dict[str, tuple[str, str]] = {}
        for family in self.families:
            names = [name for need in family.needs for name in (need.id, *need.aliases)]
            repeated = _repeated(names)
            if repeated:
                raise ValueError(
                    f"two needs of the {family.id} family share the id or alias {', '.join(repeated)}"
                )
            for need in family.needs:
                for name in (need.id, *need.aliases):
                    first = meanings.setdefault(name, (need.id, family.id))
                    if first[0] != need.id:
                        raise ValueError(
                            f"{name} means {first[0]} in {first[1]} and {need.id} in {family.id}; a need's "
                            "name means the same need in every family"
                        )

    def _family_of_kind(self, argument: Argument) -> NeedFamily:
        family = next((family for family in self.families if argument.kind in family.kinds), None)
        if family is None:
            raise ValueError(f"argument {argument.id} is a {argument.kind.value}, which no family takes")
        return family

    def _check_names(self) -> None:
        names = [entry.id for entry in self.arguments] + [
            alias for entry in self.arguments for alias in entry.aliases
        ]
        repeated = _repeated(names)
        if repeated:
            raise ValueError(f"two arguments share the id or alias {', '.join(repeated)}")
        repeated = _repeated(topic.id for topic in self.topics)
        if repeated:
            raise ValueError(f"two topics share the id {', '.join(repeated)}")
        for argument in self.arguments:
            if argument.landscape_id is not None and argument.landscape_id != argument.id:
                raise ValueError(
                    f"argument {argument.id} names landscape_id {argument.landscape_id}; an argument "
                    "the landscape also counts takes the landscape's id"
                )

    def _check_templates(self, argument: Argument, family: NeedFamily) -> None:
        need_ids = [need.id for need in family.needs]
        unknown = sorted(set(argument.templates) - set(need_ids))
        if unknown:
            raise ValueError(
                f"argument {argument.id} has templates for {', '.join(unknown)}, which is not a need of "
                f"the {family.id} family; its needs are {', '.join(need_ids)}"
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
            if len(templates) > MAX_QUERIES_PER_SEARCH:
                raise ValueError(
                    f"{argument.id}/{need_id} has {len(templates)} templates; a search asks at most "
                    f"{MAX_QUERIES_PER_SEARCH}"
                )
            if not any(template.variables <= ALWAYS_GIVEN_VARIABLES for template in templates):
                raise ValueError(
                    f"{argument.id}/{need_id}: every template needs a variable a search may not have; "
                    f"at least one may name only {' and '.join(sorted(ALWAYS_GIVEN_VARIABLES))}"
                )

    def _da(self, argument_id: str) -> Argument | None:
        return next(
            (entry for entry in self.arguments if entry.id == argument_id and entry.kind is ArgumentKind.DA),
            None,
        )

    def _crossed_template(self, topic: TopicPreset, entry: MechanismLinkTemplate) -> QueryTemplate:
        """The template `entry` names, refusing one that is not a DA's link template as written, or that
        names a variable a search may not have."""
        where = f"topic {topic.id}: the mechanism link template"
        label = entry.template_id if entry.template_id is not None else repr(entry.text)
        if entry.template_id is None:
            template = QueryTemplate(text=entry.text)
            if self._da(entry.argument_id) is None:
                raise ValueError(f"{where} {label} names {entry.argument_id}, which is not a DA's id")
        else:
            parts = _TEMPLATE_ID_PATTERN.fullmatch(entry.template_id)
            if parts is None:
                raise ValueError(f"{where} {label} is not a template id of the form <da>/link/<number>")
            name, need_id, number = parts.group(1), parts.group(2), int(parts.group(3))
            argument = self._da(name)
            if argument is None:
                raise ValueError(f"{where} {label} names {name}, which is not a DA's id")
            if need_id != MECHANISM_NEED:
                raise ValueError(f"{where} {label} is not a link template")
            links = argument.templates.get(MECHANISM_NEED, ())
            if number > len(links):
                raise ValueError(f"{where} {label}: {name} has no link template {number}")
            template = links[number - 1]
            if template.text != entry.text:
                raise ValueError(
                    f"topic {topic.id}: the template at {label} reads {template.text!r}, not {entry.text!r}"
                )
        extra = sorted(template.variables - ALWAYS_GIVEN_VARIABLES)
        if extra:
            raise ValueError(
                f"{where} {label} names {', '.join(extra)}; a crossed template names only "
                f"{' and '.join(sorted(ALWAYS_GIVEN_VARIABLES))}"
            )
        return template

    def _check_mechanism_links(self, topic: TopicPreset) -> None:
        """Every crossed template is a DA's link template as written, or the preset's own, naming only
        {query} and {topic}, none twice; and no DA's link search on the topic passes the maximum."""
        if topic.mechanism_link_templates and not topic.mechanisms:
            raise ValueError(f"topic {topic.id} names mechanism link templates but no plan mechanisms")
        seen: set[tuple[str, str]] = set()
        for entry in topic.mechanism_link_templates:
            self._crossed_template(topic, entry)
            key = (entry.argument_id, " ".join(entry.text.casefold().split()))
            if key in seen:
                raise ValueError(
                    f"topic {topic.id} crosses {entry.argument_id}'s template {entry.text!r} twice"
                )
            seen.add(key)
        if not topic.mechanisms:
            return
        for argument in self.arguments:
            if argument.kind is not ArgumentKind.DA or MECHANISM_NEED not in argument.templates:
                continue
            asked = len(argument.templates[MECHANISM_NEED]) + len(
                self.mechanism_link_templates(topic, argument)
            ) * (1 + len(topic.mechanisms))
            if asked > MAX_QUERIES_PER_SEARCH:
                raise ValueError(
                    f"topic {topic.id}: {argument.id}'s link search would ask {asked} queries; a search asks "
                    f"at most {MAX_QUERIES_PER_SEARCH}"
                )

    def find_argument(self, name: str) -> Argument | None:
        """The argument `name` is the id or an alias of, compared as :func:`normalized_choice` says."""
        wanted = normalized_choice(name)
        return next(
            (argument for argument in self.arguments if wanted in (argument.id, *argument.aliases)), None
        )

    def family_of(self, argument: Argument) -> NeedFamily:
        """The family whose needs `argument` has: the one that takes its kind."""
        return self._family_of_kind(argument)

    def find_need(self, argument: Argument, name: str) -> Need | None:
        """The need of `argument`'s family that `name` is the id or an alias of; None for any other,
        including another family's need."""
        return self.family_of(argument).find_need(name)

    def mechanism_link_templates(
        self, topic: TopicPreset, argument: Argument
    ) -> tuple[tuple[str, QueryTemplate], ...]:
        """The link templates `argument`'s mechanism queries cross on `topic`, each with the template id
        its queries are recorded under, in order (v1-e08-t16).

        The preset's entries for `argument`: a DA template under its own id, a crossing-only template
        under `<argument>/link/<topic>-<n>`, numbered among that DA's crossing-only entries. A DA the
        preset does not name crosses its first link template that names only {query} and {topic}.
        """
        entries = [entry for entry in topic.mechanism_link_templates if entry.argument_id == argument.id]
        if not entries:
            number, template = next(
                (number, template)
                for number, template in enumerate(argument.templates[MECHANISM_NEED], start=1)
                if template.variables <= ALWAYS_GIVEN_VARIABLES
            )
            return ((f"{argument.id}/{MECHANISM_NEED}/{number}", template),)
        crossed: list[tuple[str, QueryTemplate]] = []
        own = 0
        for entry in entries:
            if entry.template_id is None:
                own += 1
                template_id = f"{argument.id}/{MECHANISM_NEED}/{topic.id}-{own}"
            else:
                template_id = entry.template_id
            crossed.append((template_id, self._crossed_template(topic, entry)))
        return tuple(crossed)

    def find_topic(self, topic_id: str) -> TopicPreset | None:
        """The topic preset with this id."""
        wanted = normalized_choice(topic_id)
        return next((topic for topic in self.topics if topic.id == wanted), None)
