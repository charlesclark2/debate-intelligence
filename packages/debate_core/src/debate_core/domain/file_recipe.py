"""The file recipe: what an evidence file holds, written by a coach, built by the file builder (E33).

A recipe is a YAML file in the evidence workspace (`settings.files_dir`, under
`files/recipes/<topic>/<name>.yaml`) that says which cards go into a Verbatim file and where. It
names the file (title, topic, format, caselist, position, side) and lays out its headings as a tree
that follows Verbatim's own levels:

    pocket > hat > block > item

An item is a :class:`CardRef`, a card named by its E31 exact fingerprint, or an :class:`Analytic`,
the coach's own words. `v1-e33-t02` copies each referenced card's cite and evidence from its source
document's runs; `v1-e33-t03` builds a file from a recipe; `docs/guides/file-recipes.md` is the
coach's description and `docs/data/file-recipe.schema.json` the published schema.

## Rules these models carry

**A recipe never holds evidence or cite text.** No field can: a card is its fingerprint, and the
only text a recipe carries is the coach's own (headings, :class:`TagOverride`, :class:`Analytic`),
each bounded so that a pasted card does not fit (the task's first forbidden item).

**The tree is Verbatim's, with no level skipped.** Items sit in blocks, blocks in hats or straight
in a pocket, hats in pockets. Hats are optional for a recipe as a whole: when any pocket declares
hats, every block is inside one. No section is empty. Unknown keys are refused at every level, as
on every :class:`~debate_core.domain.base.DomainModel`.

**A fingerprint is E31's.** :attr:`CardRef.fingerprint` is typed exactly as
:attr:`~debate_core.domain.card_occurrence.CardFingerprint.exact_fingerprint`. The recipe also names
the `fingerprint_version` it was written under; which versions share today's digests is
:data:`~debate_core.evidence.fingerprints.EXACT_FINGERPRINT_VERSIONS`, which the domain layer cannot
import, so `debate_core.application.file_recipes` checks it.

**Every structural error is reported, not the first.** The checks that span sections (a side the
format does not debate, a pocket without hats beside one with them, a pocket with both or neither)
run on the input as given and are reported beside the field errors of the same pass.

**A camp card is named by its release (`v1-e33-t06`).** A pin's `caselist` may be `openev`, the
store camp (OpenEv) files are parsed into, and its `snapshot` is then the release the file came in,
`<year>-<event>` such as `2031-policy`, as `caselist publish --caselist openev --snapshot` names it.
The release is required: the same camp file in two releases is two occurrences. A camp file has no
disclosure, so a camp pin names no school, team code, side, tournament or round. The recipe's own
`caselist` may be `openev` too, for a file of camp cards, and AUTO then chooses among camp
occurrences. Both are additions: every recipe valid before stays valid, with the same hash.

**A pin names who disclosed a card, which is personal data.** A recipe lives in the evidence
workspace, which the data-use policy allows to hold a school and team code
(`docs/policies/caselist-data-use.md`, personal data). The pin's school, team code, tournament and
round are kept off its `repr`, so a recipe that reaches a log line does not carry them there.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Any, Final, Literal, LiteralString, cast

from pydantic import (
    BeforeValidator,
    Discriminator,
    Field,
    ModelWrapValidatorHandler,
    PlainSerializer,
    Strict,
    StringConstraints,
    Tag,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_core import InitErrorDetails, PydanticCustomError

from debate_core.domain.base import DomainModel, NonEmptyText, Sha256Hex
from debate_core.domain.caselist.values import (
    CASELIST_SLUG_PATTERN,
    Event,
    Side,
    TeamCodeText,
    sides_for_event,
)

__all__ = [
    "ANALYTIC_MAX_LENGTH",
    "CAMP_RELEASE_PATTERN",
    "CAMP_STORE",
    "FILE_RECIPE_SCHEMA_VERSION",
    "HEADING_MAX_LENGTH",
    "RECIPE_ID_PATTERN",
    "RECIPE_ITEM_TAGS",
    "RECIPE_STORE_PATTERN",
    "TAG_OVERRIDE_MAX_LENGTH",
    "Analytic",
    "Block",
    "CardRef",
    "FileRecipe",
    "Hat",
    "OccurrencePin",
    "Pocket",
    "RecipeItem",
    "RecipeLocation",
    "RecipeStatus",
    "TagAuthor",
    "TagOverride",
    "render_location",
]

FILE_RECIPE_SCHEMA_VERSION: Final = 1
"""The recipe shape these models read. Bumped by a change an existing recipe would break on."""

RECIPE_ID_PATTERN: Final = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
"""A topic or position id: kebab-case, as the E32 taxonomy (`v1-e32-t01`) writes its ids."""

HEADING_MAX_LENGTH: Final = 200
"""Longest title, pocket, hat or block heading. A heading is a line, not a paragraph."""

TAG_OVERRIDE_MAX_LENGTH: Final = 600
"""Longest coach-written tag. Long enough for a three-sentence tag; too short for a card."""

ANALYTIC_MAX_LENGTH: Final = 2000
"""Longest analytic: a coach's paragraph of argument, not a pasted card."""

RECIPE_ITEM_TAGS: Final = ("card", "analytic")
"""The two kinds of item, as validation errors name them inside an item's location."""

CAMP_STORE: Final = "openev"
"""The store camp (OpenEv) files are parsed into, as `--caselist openev` names it (`v1-e33-t06`)."""

CAMP_RELEASE_PATTERN: Final = rf"^[0-9]{{4}}-(?:{'|'.join(sorted(event.value.lower() for event in Event))})$"
"""A camp release, `2031-policy`: the topic year and the event, as `manifests/openev/` names it."""

RECIPE_STORE_PATTERN: Final = (
    rf"^(?:{CASELIST_SLUG_PATTERN.removeprefix('^').removesuffix('$')}|{CAMP_STORE})$"
)
"""What a recipe's or a pin's `caselist` may be: a caselist slug, or :data:`CAMP_STORE`."""

RecipeId = Annotated[str, StringConstraints(pattern=RECIPE_ID_PATTERN, max_length=64)]
StoreName = Annotated[str, StringConstraints(pattern=RECIPE_STORE_PATTERN)]
CampRelease = Annotated[str, StringConstraints(pattern=CAMP_RELEASE_PATTERN)]
HeadingText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=HEADING_MAX_LENGTH)
]
CoachTagText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TAG_OVERRIDE_MAX_LENGTH)
]
AnalyticText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=ANALYTIC_MAX_LENGTH)
]

type RecipeLocation = tuple[str | int, ...]
"""Where something sits in a recipe: `("structure", 0, "hats", 1, "blocks", 2, "items", 3)`."""


def render_location(location: RecipeLocation) -> str:
    """`structure[0].hats[1].blocks[2].items[3]`: a location as the coach reads it; `""` for the root."""
    rendered = ""
    for part in location:
        if isinstance(part, int):
            rendered += f"[{part}]"
        else:
            rendered += f".{part}" if rendered else part
    return rendered


class RecipeStatus(StrEnum):
    """Whether a recipe is ready to build. `files suggest` (`v1-e33-t03`) writes drafts."""

    DRAFT = "draft"
    READY = "ready"


class TagAuthor(StrEnum):
    """Who wrote a tag that replaces a card's own. Only ever the coach: a tag is never generated."""

    COACH = "COACH"


class TagOverride(DomainModel):
    """A tag the coach wrote to replace a card's own, labeled as theirs.

    The built file's provenance records it as coach-authored beside the original tag's hash
    (`v1-e33-t02`). In YAML it is written as the tag's text alone.
    """

    text: CoachTagText = Field(description="The coach's tag, as it is to appear in the built file.")
    authored_by: Literal[TagAuthor.COACH] = Field(
        default=TagAuthor.COACH, description="Always COACH: the tag is the coach's words, not the card's."
    )


def _tag_override_from_text(value: object) -> object:
    """A YAML `tag_override:` is the tag's text; the model carries it as a labeled :class:`TagOverride`."""
    if value is None or isinstance(value, TagOverride):
        return value
    if not isinstance(value, str):
        raise ValueError("a tag override is the coach's tag, written as text")
    text = value.strip()
    if not text:
        raise ValueError("a tag override needs text; leave the key out to keep the card's own tag")
    if len(text) > TAG_OVERRIDE_MAX_LENGTH:
        raise ValueError(
            f"a tag override is at most {TAG_OVERRIDE_MAX_LENGTH} characters; this one is {len(text)}"
        )
    return TagOverride(text=text)


def _tag_override_text(value: TagOverride | None) -> str | None:
    return None if value is None else value.text


TagOverrideField = Annotated[
    TagOverride | None,
    BeforeValidator(_tag_override_from_text, json_schema_input_type=str | None),
    PlainSerializer(_tag_override_text, return_type=str | None),
]


_RELEASE: Final = re.compile(CAMP_RELEASE_PATTERN)
_RELEASE_LIKE: Final = re.compile(r"^[0-9]{4}-[A-Za-z]")
_DATE: Final = TypeAdapter(date)


def _snapshot_as_written(value: object) -> object:
    """A caselist's snapshot is a calendar date, `2026-09-15`, quoted or not; a camp's is its release.

    A release (`2031-policy`) is kept as text, and anything else is read as a date exactly as a date
    field reads it, so a caselist pin's snapshot is what it was before camp pins (`v1-e33-t06`). A
    number or a timestamp is neither. Which of the two a pin needs is the pin's own check.
    """
    if isinstance(value, datetime) or not isinstance(value, date | str):
        raise ValueError("a snapshot is a date written YYYY-MM-DD, or a camp release written <year>-<event>")
    if not isinstance(value, str):
        return value
    if _RELEASE.match(value) is not None:
        return value
    if _RELEASE_LIKE.match(value) is not None:
        raise ValueError("a camp release is <year>-<event>, the event policy, ld or pf: 2031-policy")
    try:
        return _DATE.validate_python(value)
    except ValidationError as error:
        first = error.errors()[0]
        raise _custom_error(first["type"], first["msg"]) from None


ElementIndex = Annotated[int, Strict(), Field(ge=0)]
PinSnapshot = Annotated[
    date | str, BeforeValidator(_snapshot_as_written, json_schema_input_type=date | CampRelease)
]


class OccurrencePin(DomainModel):
    """The one occurrence a card reference must come from, checked against the occurrence store.

    The store's own key for a card is its source's SHA-256 and the index of its first paragraph;
    those and the caselist whose store holds it are required. The same bytes disclosed by two teams
    are two occurrences there, so the rest narrow a pin to one disclosure: the snapshot it was seen
    in and who disclosed it, exactly as disclosed. A pin is never moved to another occurrence: one
    that matches none, or more than one, is an error (`v1-e33-t01` ac4).

    A camp pin (`caselist: openev`, `v1-e33-t06`) names the release instead, as its `snapshot`, and
    nothing else: a camp file is one occurrence per release and has no disclosure.
    """

    caselist: StoreName = Field(
        description="The caselist whose occurrence store holds the card, or `openev` for a camp file."
    )
    source_sha256: Sha256Hex = Field(description="SHA-256 of the file the card is read from.")
    element_index: ElementIndex = Field(description="Index of the card's first paragraph in that file.")
    snapshot: PinSnapshot | None = Field(
        default=None,
        description=(
            "For a caselist, a snapshot the disclosure was seen in, between its first and latest; for "
            "`openev`, the camp release, `<year>-<event>` such as 2031-policy, which a camp pin requires."
        ),
    )
    school: NonEmptyText | None = Field(default=None, repr=False, description="School, as disclosed.")
    team_code: TeamCodeText | None = Field(default=None, repr=False, description="Team code, as disclosed.")
    side: Side | None = Field(default=None, description="Side the disclosing file was read on.")
    tournament: NonEmptyText | None = Field(default=None, repr=False, description="Tournament, as disclosed.")
    round: NonEmptyText | None = Field(default=None, repr=False, description="Round, exactly as disclosed.")

    @model_validator(mode="wrap")
    @classmethod
    def _camp_or_caselist(
        cls, value: object, handler: ModelWrapValidatorHandler[OccurrencePin]
    ) -> OccurrencePin:
        given = _as_mapping(value)
        problems = _pin_problems(given) if given is not None else []
        return _validate_with_problems(value, handler, problems, cls.__name__)


_DISCLOSURE_FIELDS: Final = ("school", "team_code", "side", "tournament", "round")


def _is_a_date(value: object) -> bool:
    """Whether a pin's `snapshot`, as given, is a date that the field reads as one."""
    if isinstance(value, datetime):
        return False
    if isinstance(value, date):
        return True
    if not isinstance(value, str) or _RELEASE_LIKE.match(value) is not None:
        return False
    try:
        _DATE.validate_python(value)
    except ValidationError:
        return False
    return True


def _pin_problems(pin: Mapping[str, object]) -> list[InitErrorDetails]:
    """A camp pin names its release and no disclosure; a caselist pin's snapshot is not a release.

    Read on the input as given, beside the field errors, and only where the field itself is well
    formed, so one mistake is one error.
    """
    caselist, snapshot = pin.get("caselist"), pin.get("snapshot")
    if caselist != CAMP_STORE:
        if isinstance(caselist, str) and isinstance(snapshot, str) and _RELEASE.match(snapshot):
            return [
                _problem(
                    ("snapshot",),
                    "release_in_a_caselist_pin",
                    "a release names a camp file, which a pin reaches as `caselist: openev`; a caselist "
                    "pin's snapshot is a date written YYYY-MM-DD",
                    snapshot,
                )
            ]
        return []
    problems: list[InitErrorDetails] = []
    if snapshot is None:
        problems.append(
            _problem(
                ("snapshot",),
                "camp_pin_without_a_release",
                "a camp pin names its release as `snapshot`, <year>-<event> such as 2031-policy: the same "
                "camp file in two releases is two occurrences",
                pin,
            )
        )
    elif _is_a_date(snapshot):
        problems.append(
            _problem(
                ("snapshot",),
                "camp_pin_with_a_date",
                "a camp pin's snapshot is its release, <year>-<event> such as 2031-policy, not a date",
                snapshot,
            )
        )
    problems += [
        _problem(
            (name,),
            "camp_pin_with_a_disclosure",
            f"a camp pin names no {name}: a camp file has no disclosure to narrow it to",
            pin[name],
        )
        for name in _DISCLOSURE_FIELDS
        if pin.get(name) is not None
    ]
    return problems


class CardRef(DomainModel):
    """A card, by its E31 exact fingerprint. Its cite and evidence are copied from its source."""

    fingerprint: Sha256Hex = Field(
        description="The card's exact fingerprint (v1-e31-t04): 64 lowercase hex characters."
    )
    tag_override: TagOverrideField = Field(
        default=None, description="The coach's tag, replacing the card's own."
    )
    pin: OccurrencePin | None = Field(
        default=None, description="The occurrence to copy the card from; without one it is chosen (AUTO)."
    )


class Analytic(DomainModel):
    """The coach's own words, written into the file as an analytic."""

    analytic: AnalyticText = Field(description="The analytic's text.")


def _item_kind(value: Any) -> str | None:
    if isinstance(value, CardRef) or (isinstance(value, Mapping) and "fingerprint" in value):
        return "card"
    if isinstance(value, Analytic) or (isinstance(value, Mapping) and "analytic" in value):
        return "analytic"
    return None


RecipeItem = Annotated[
    Annotated[CardRef, Tag("card")] | Annotated[Analytic, Tag("analytic")],
    Discriminator(
        _item_kind,
        custom_error_type="recipe_item_kind",
        custom_error_message="an item is a card (`fingerprint:`) or an analytic (`analytic:`)",
    ),
]


class Block(DomainModel):
    """A block heading and the items under it."""

    block: HeadingText = Field(description="The block's heading.")
    items: list[RecipeItem] = Field(min_length=1, description="Cards and analytics, in file order.")


class Hat(DomainModel):
    """A hat heading and the blocks under it."""

    hat: HeadingText = Field(description="The hat's heading.")
    blocks: list[Block] = Field(min_length=1, description="The hat's blocks, in file order.")


def _as_mapping(value: object) -> Mapping[str, object] | None:
    """The input as a mapping, when it is one: what YAML or a caller gave before validation."""
    return cast(Mapping[str, object], value) if isinstance(value, Mapping) else None


def _section_has(section: object, key: str) -> bool:
    """Whether a pocket, as given or as built, declares `key` (`hats` or `blocks`) with a value."""
    given = _as_mapping(section)
    if given is not None:
        return given.get(key) is not None
    return getattr(section, key, None) is not None


def _custom_error(kind: str, message: str) -> PydanticCustomError:
    """An error of type `kind` reading `message`. Neither is a template: no context is given to fill."""
    return PydanticCustomError(cast(LiteralString, kind), cast(LiteralString, message))


def _problem(location: RecipeLocation, kind: str, message: str, value: object) -> InitErrorDetails:
    return InitErrorDetails(type=_custom_error(kind, message), loc=location, input=value)


def _validate_with_problems[ModelT](
    value: object,
    handler: ModelWrapValidatorHandler[ModelT],
    problems: Sequence[InitErrorDetails],
    title: str,
) -> ModelT:
    """Run the field validation and report its errors together with `problems`, found on the input.

    A model validator that runs after the fields only runs once they are all valid, so a
    cross-section error would wait for every field error to be fixed first. These checks read the
    input instead, and their errors join the field errors in one :class:`ValidationError`.
    """
    found: list[InitErrorDetails] = []
    result: ModelT | None = None
    try:
        result = handler(value)
    except ValidationError as error:
        found = [
            InitErrorDetails(
                type=_custom_error(issue["type"], issue["msg"]), loc=issue["loc"], input=issue["input"]
            )
            for issue in error.errors()
        ]
    if found or problems:
        raise ValidationError.from_exception_data(title, [*found, *problems])
    assert result is not None
    return result


class Pocket(DomainModel):
    """A pocket heading, holding either hats or blocks, never both and never neither."""

    pocket: HeadingText = Field(description="The pocket's heading.")
    hats: list[Hat] | None = Field(
        default=None, min_length=1, description="The pocket's hats, in file order."
    )
    blocks: list[Block] | None = Field(
        default=None, min_length=1, description="The pocket's blocks, for a recipe without hats."
    )

    @model_validator(mode="wrap")
    @classmethod
    def _hats_or_blocks(cls, value: object, handler: ModelWrapValidatorHandler[Pocket]) -> Pocket:
        problems: list[InitErrorDetails] = []
        has_hats, has_blocks = _section_has(value, "hats"), _section_has(value, "blocks")
        if has_hats and has_blocks:
            problems.append(
                _problem(
                    ("blocks",),
                    "block_outside_a_hat",
                    "a block outside a hat: this pocket has hats, so its blocks go inside them",
                    value,
                )
            )
        elif not has_hats and not has_blocks and _as_mapping(value) is not None:
            problems.append(
                _problem((), "empty_section", "an empty pocket: a pocket holds hats or blocks", value)
            )
        return _validate_with_problems(value, handler, problems, cls.__name__)


class FileRecipe(DomainModel):
    """One evidence file to build: what it is for, and its headings, cards and analytics in order."""

    schema_version: Literal[1] = Field(description="The recipe shape: 1.")
    title: HeadingText = Field(description="The file's title.")
    topic: RecipeId = Field(description="The topic id, kebab-case, as the landscape taxonomy names it.")
    format: Event = Field(description="POLICY, LD or PF.")
    caselist: StoreName = Field(
        description=(
            "The caselist whose occurrence store unpinned cards come from, or `openev` for a file of "
            "camp cards."
        )
    )
    position: RecipeId = Field(description="The position id, kebab-case, as the landscape taxonomy names it.")
    side: Side = Field(description="The side the file is for: AFF or NEG, or PRO or CON for PF.")
    fingerprint_version: NonEmptyText = Field(
        description="The E31 fingerprint version the card fingerprints were taken under."
    )
    status: RecipeStatus = Field(default=RecipeStatus.READY, description="draft or ready.")
    structure: list[Pocket] = Field(min_length=1, description="The file's pockets, in order.")

    @field_validator("schema_version", mode="before")
    @classmethod
    def _schema_version_is_a_number(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError(f"schema_version is the number {FILE_RECIPE_SCHEMA_VERSION}")
        return value

    @model_validator(mode="wrap")
    @classmethod
    def _cross_section_checks(
        cls, value: object, handler: ModelWrapValidatorHandler[FileRecipe]
    ) -> FileRecipe:
        given = _as_mapping(value)
        problems = _side_problems(given) + _hat_problems(given) if given is not None else []
        return _validate_with_problems(value, handler, problems, cls.__name__)

    def walk_items(self) -> Iterator[tuple[RecipeLocation, CardRef | Analytic]]:
        """Every item with its location, in file order."""
        for p, pocket in enumerate(self.structure):
            for h, hat in enumerate(pocket.hats or ()):
                for b, block in enumerate(hat.blocks):
                    for i, item in enumerate(block.items):
                        yield ("structure", p, "hats", h, "blocks", b, "items", i), item
            for b, block in enumerate(pocket.blocks or ()):
                for i, item in enumerate(block.items):
                    yield ("structure", p, "blocks", b, "items", i), item

    def card_refs(self) -> Iterator[tuple[RecipeLocation, CardRef]]:
        """Every card reference with its location, in file order."""
        for location, item in self.walk_items():
            if isinstance(item, CardRef):
                yield location, item


def _side_problems(recipe: Mapping[str, object]) -> list[InitErrorDetails]:
    """A side the format debates, and one side: a file is built for AFF or NEG, or PRO or CON."""
    event, side = recipe.get("format"), recipe.get("side")
    if not isinstance(event, str) or not isinstance(side, str):
        return []
    if event not in Event.__members__.values() or side not in Side.__members__.values():
        return []
    legal = sides_for_event(Event(event)) - {Side.UNKNOWN}
    if Side(side) in legal:
        return []
    names = " or ".join(sorted(str(one) for one in legal))
    return [_problem(("side",), "side_for_format", f"a {event} file is {names}", side)]


def _hat_problems(recipe: Mapping[str, object]) -> list[InitErrorDetails]:
    """No block outside a hat when the recipe declares hats: a pocket of blocks beside one of hats."""
    structure = recipe.get("structure")
    if not isinstance(structure, list):
        return []
    pockets = cast(list[object], structure)
    if not any(_section_has(pocket, "hats") for pocket in pockets):
        return []
    return [
        _problem(
            ("structure", index, "blocks"),
            "block_outside_a_hat",
            "a block outside a hat: this recipe declares hats, so every pocket's blocks go inside one",
            pocket,
        )
        for index, pocket in enumerate(pockets)
        if _section_has(pocket, "blocks") and not _section_has(pocket, "hats")
    ]
