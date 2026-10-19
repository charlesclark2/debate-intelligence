"""Loading, hashing and resolving file recipes (`v1-e33-t01`).

A recipe (:class:`~debate_core.domain.file_recipe.FileRecipe`) is written by a coach in YAML. This
module turns the text into a validated recipe, gives it a stable hash, and maps each card it
references to the one place the file builder (`v1-e33-t02`) will copy the card from.

## Loading: every error, with its line

:func:`load_recipe` reads the text with PyYAML's safe loader, keeping the line of every key and list
item, and validates it. Everything wrong is reported in one pass, each :class:`RecipeError` with its
YAML line and its path in the recipe (`structure[0].hats[1].blocks[2].items[3].fingerprint`):
syntax, a key given twice in one mapping (which YAML itself would silently resolve to the last),
every field error and every structural one. Nothing in a message repeats a value the recipe gave,
because a rejected value can be a team code.

The reader is bounded: a recipe is at most :data:`RECIPE_MAX_BYTES`, and at most
:data:`RECIPE_MAX_NODES` nodes once its aliases are followed, so an alias bomb is refused before
anything is built from it.

## The hash

:func:`recipe_hash` is the SHA-256 of :func:`canonical_recipe_json`: the validated recipe as JSON
with sorted keys, no whitespace, ASCII escapes and no null fields. It is computed from the model,
never from the text, so key order, comments, quoting, flow or block style, anchors and aliases
leave it unchanged, while any card, pin, tag override, analytic, heading or order changes it.

## Resolving: one occurrence per card

:class:`RecipeResolver` reads three ports and nothing else: the parsed card store
(:class:`~debate_core.application.ports.parsed_store.ParsedStore`, whose `occurrences.jsonl` is the
E31 occurrence table), the caselist records
(:class:`~debate_core.application.ports.caselist.CaselistRepository`, for who disclosed each
occurrence) and the removal suppression list
(:class:`~debate_core.application.ports.suppression.SuppressionList`). No model is called and nothing
reaches the network.

* **Which rows.** The newest generation of the resolver's parser version, for the recipe's
  caselist and for each caselist a pin names. Rows must carry a fingerprint version in
  :data:`~debate_core.evidence.fingerprints.EXACT_FINGERPRINT_VERSIONS`; a store whose aggregates
  are missing (after a removal, until the next `caselist parse`) or stamped with another version
  is :class:`OccurrenceStoreNotReady`, never read as empty.
* **Who disclosed it.** An occurrence row names its disclosure only by digest. The resolver lists
  the source's disclosures in the caselist records and keeps the one whose
  :func:`~debate_core.application.ports.suppression.disclosure_digest` is the row's, the join
  `docs/data/parsed-card-store.md` describes. None is on record for a row the importer has not
  recorded; the card still resolves, without one.
* **Unpinned (AUTO).** Among the card's rows in the recipe's caselist that the suppression list
  does not stop: the latest `last_snapshot`, then the lowest source SHA-256, then the lowest first
  element index, then the lowest disclosure digest. Each key is a field of the stored row, so the
  choice is total and does not depend on the order the store lists rows in.
* **Pinned.** The rows at the pin's source and element index in the pin's caselist, holding the
  card the reference names, whose snapshot span and disclosure match every field the pin gives.
  Rows of the same disclosure attributes are one occurrence, as in
  :attr:`~debate_core.domain.card_occurrence.CardOccurrence.occurrence_key`; of those the one listed
  latest is taken. None, or two that differ in who disclosed them, is `PIN_MISMATCH`.

## The suppression list (PM amendment, 2026-10-18)

The resolver never chooses an occurrence the suppression list stops. It asks
:meth:`~debate_core.application.ports.suppression.SuppressionState.suppresses` with the row's source
SHA-256 and its disclosure digest, the same question the parse pipeline asks when it rebuilds the
occurrence table (`_live_disclosures` in :mod:`debate_core.application.caselist_parse`): a whole
source, or a disclosure withdrawn from that caselist path. The table already leaves both out once
it is rebuilt; the resolver asks again because a list merged from another machine can stop a row
before this machine's next rebuild. AUTO passes over such a row to the next by the rule above; a
card with none left is `SUPPRESSED_OCCURRENCE`. A pin to such an occurrence is refused with
`SUPPRESSED_OCCURRENCE`, never moved to another one, and so is a pin to a source suppressed as a
whole, which a rebuilt store no longer holds at all. Path holds (`v1-e30-t13`) stop new bytes at an
import and never reach the table, so the resolver has none to ask about.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any, Final, cast

import yaml
from pydantic import ValidationError

from debate_core.application.caselist.suppression import load_suppression_state
from debate_core.application.errors import DomainError
from debate_core.application.ports.caselist import CaselistRepository
from debate_core.application.ports.parsed_store import (
    OccurrenceRecord,
    ParsedStore,
    parse_version_directory,
    version_directory_name,
)
from debate_core.application.ports.suppression import SuppressionList, SuppressionState, disclosure_digest
from debate_core.domain.caselist import Disclosure
from debate_core.domain.file_recipe import (
    RECIPE_ITEM_TAGS,
    Analytic,
    Block,
    CardRef,
    FileRecipe,
    Hat,
    OccurrencePin,
    Pocket,
    RecipeLocation,
    TagOverride,
    render_location,
)
from debate_core.domain.schema_export import JSON_SCHEMA_DIALECT
from debate_core.evidence.fingerprints import EXACT_FINGERPRINT_VERSIONS

__all__ = [
    "RECIPE_MAX_BYTES",
    "RECIPE_MAX_NODES",
    "RECIPE_SCHEMA_FILENAME",
    "OccurrenceStoreNotReady",
    "RecipeError",
    "RecipeErrorCode",
    "RecipeLoadResult",
    "RecipeResolver",
    "Resolution",
    "ResolvedCard",
    "ResolvedRecipe",
    "canonical_recipe_json",
    "load_recipe",
    "recipe_hash",
    "render_recipe_schema",
]

RECIPE_SCHEMA_FILENAME: Final = "file-recipe.schema.json"
"""The published schema's file name, under `docs/data/`."""

RECIPE_MAX_BYTES: Final = 1_000_000
"""Largest recipe read, in UTF-8 bytes. A file of 500 pinned cards is about 150 kB."""

RECIPE_MAX_NODES: Final = 100_000
"""Most YAML nodes read once aliases are followed. Every node of a 500-card recipe is about 6,000."""

_DISCLOSURE_PAGE: Final = 500


# ------------------------------------------------------------------------------------------------
# Errors
# ------------------------------------------------------------------------------------------------


class RecipeErrorCode(StrEnum):
    """What is wrong with a recipe. Loading reports the first four, resolving the rest."""

    YAML_SYNTAX = "YAML_SYNTAX"
    """Not one readable YAML document."""

    DUPLICATE_KEY = "DUPLICATE_KEY"
    """A key given twice in one mapping. YAML would keep the last without a word."""

    TOO_LARGE = "TOO_LARGE"
    """Past :data:`RECIPE_MAX_BYTES`, or past :data:`RECIPE_MAX_NODES` once aliases are followed."""

    INVALID = "INVALID"
    """A field or a section the recipe models refuse, or a fingerprint version without today's digests."""

    PIN_MISMATCH = "PIN_MISMATCH"
    """A pin that matches no occurrence of its card, or more than one disclosure of it."""

    UNKNOWN_CARD = "UNKNOWN_CARD"
    """A fingerprint the recipe's caselist has no occurrence of."""

    DUPLICATE_REF = "DUPLICATE_REF"
    """The same fingerprint a second time in one recipe. Reported at each repeat."""

    SUPPRESSED_OCCURRENCE = "SUPPRESSED_OCCURRENCE"
    """A pin to an occurrence the removal suppression list stops, or a card it stops everywhere.

    PM amendment 2026-10-18 (`v1-e33-t01` ac6)."""


@dataclass(frozen=True, slots=True)
class RecipeError:
    """One thing wrong with a recipe: where it is, and what to do about it.

    `path` is the location in the recipe as the coach reads it, `""` for the recipe as a whole;
    `line` is the YAML line it is on, when the recipe was loaded from text. `message` never repeats
    a value the recipe gave.
    """

    code: RecipeErrorCode
    path: str
    line: int | None
    message: str

    def __str__(self) -> str:
        where = f"line {self.line}" if self.line is not None else "recipe"
        return f"{where}: {self.path or '(recipe)'}: {self.message} [{self.code}]"


@dataclass(frozen=True, slots=True)
class RecipeLoadResult:
    """A loaded recipe, or every reason it could not be loaded.

    `lines` maps each path in the text (`structure[0].blocks[1].items[2].pin`) to its YAML line,
    for errors found later, by the resolver.
    """

    recipe: FileRecipe | None
    errors: tuple[RecipeError, ...]
    lines: Mapping[str, int] = field(default_factory=lambda: {})
    recipe_hash: str | None = None

    @property
    def ok(self) -> bool:
        return self.recipe is not None and not self.errors


# ------------------------------------------------------------------------------------------------
# Hash and schema
# ------------------------------------------------------------------------------------------------


def canonical_recipe_json(recipe: FileRecipe) -> str:
    """The recipe as canonical JSON: sorted keys, no whitespace, ASCII escapes, no null fields."""
    return json.dumps(
        recipe.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def recipe_hash(recipe: FileRecipe) -> str:
    """SHA-256 of :func:`canonical_recipe_json`, as 64 lowercase hex characters."""
    return hashlib.sha256(canonical_recipe_json(recipe).encode("ascii")).hexdigest()


def render_recipe_schema() -> dict[str, Any]:
    """The JSON Schema of a recipe as written, for `docs/data/file-recipe.schema.json`.

    Generated from the models, with one addition the domain layer cannot make: the fingerprint
    versions a recipe may name, from :data:`EXACT_FINGERPRINT_VERSIONS`. The structural rules that
    span sections (a side the format debates, hats in every pocket or none) are the models' and are
    not expressed here; the loader applies them.
    """
    schema: dict[str, Any] = {
        "$schema": JSON_SCHEMA_DIALECT,
        **FileRecipe.model_json_schema(mode="validation"),
    }
    schema["properties"]["fingerprint_version"]["enum"] = sorted(EXACT_FINGERPRINT_VERSIONS)
    return schema


# ------------------------------------------------------------------------------------------------
# Loading
# ------------------------------------------------------------------------------------------------


def load_recipe(text: str) -> RecipeLoadResult:
    """Read, check and validate a recipe's YAML text, reporting every error with its line."""
    size = len(text.encode("utf-8"))
    if size > RECIPE_MAX_BYTES:
        return _refused(
            RecipeError(
                RecipeErrorCode.TOO_LARGE,
                "",
                None,
                f"a recipe is at most {RECIPE_MAX_BYTES:,} bytes; this is {size:,}",
            )
        )
    try:
        loader = yaml.SafeLoader(text)  # reads every character of the text before anything is parsed
    except yaml.reader.ReaderError as error:
        return _refused(_unreadable_character(text, error))
    try:
        try:
            root = loader.get_single_node()
        except yaml.MarkedYAMLError as error:
            return _refused(_syntax_error(error))
        if root is None:
            return _refused(RecipeError(RecipeErrorCode.INVALID, "", None, "the recipe is empty"))
        survey = _survey(root)
        if survey is None:
            return _refused(
                RecipeError(
                    RecipeErrorCode.TOO_LARGE,
                    "",
                    None,
                    f"the recipe expands to more than {RECIPE_MAX_NODES:,} YAML nodes through its aliases",
                )
            )
        try:
            data: object = loader.construct_document(root)  # pyright: ignore[reportUnknownMemberType]
        except yaml.MarkedYAMLError as error:
            return _refused(_syntax_error(error))
    finally:
        loader.dispose()

    lines = survey.lines
    if not isinstance(data, dict):
        return _refused(
            RecipeError(
                RecipeErrorCode.INVALID, "", lines.get(""), "a recipe is a YAML mapping of its fields"
            ),
            lines=lines,
        )
    fields = cast(dict[str, object], data)
    errors = list(survey.duplicates)
    errors += _version_errors(fields.get("fingerprint_version"), lines)
    recipe: FileRecipe | None = None
    try:
        recipe = FileRecipe.model_validate(data)
    except ValidationError as error:
        errors += [_field_error(issue, lines) for issue in error.errors()]
    if errors or recipe is None:
        return _refused(*sorted(errors, key=lambda one: (one.line or 0, one.path)), lines=lines)
    return RecipeLoadResult(recipe=recipe, errors=(), lines=lines, recipe_hash=recipe_hash(recipe))


def _refused(*errors: RecipeError, lines: Mapping[str, int] | None = None) -> RecipeLoadResult:
    return RecipeLoadResult(recipe=None, errors=errors, lines=lines or {})


def _syntax_error(error: yaml.MarkedYAMLError) -> RecipeError:
    """PyYAML's account of the problem, without the excerpt of the text it would print with it."""
    mark = error.problem_mark or error.context_mark
    described = "; ".join(part for part in (error.context, error.problem) if part)
    return RecipeError(
        RecipeErrorCode.YAML_SYNTAX,
        "",
        mark.line + 1 if mark is not None else None,
        described or "the text is not readable as YAML",
    )


def _unreadable_character(text: str, error: yaml.reader.ReaderError) -> RecipeError:
    """A character YAML does not allow, such as a control character pasted from another program."""
    line = text.count("\n", 0, error.position) + 1
    return RecipeError(
        RecipeErrorCode.YAML_SYNTAX,
        "",
        line,
        f"a character YAML does not allow (code point {error.character:#06x}); delete it",
    )


def _version_errors(version: object, lines: Mapping[str, int]) -> list[RecipeError]:
    """A fingerprint version whose exact fingerprints are not the digests E31 computes today."""
    if not isinstance(version, str) or not version.strip() or version.strip() in EXACT_FINGERPRINT_VERSIONS:
        return []
    known = ", ".join(sorted(EXACT_FINGERPRINT_VERSIONS))
    return [
        RecipeError(
            RecipeErrorCode.INVALID,
            "fingerprint_version",
            lines.get("fingerprint_version"),
            f"this build's exact fingerprints are those of {known}; recompute the recipe's fingerprints",
        )
    ]


@dataclass(frozen=True, slots=True)
class _Survey:
    lines: dict[str, int]
    duplicates: tuple[RecipeError, ...]


_MERGE_TAG: Final = "tag:yaml.org,2002:merge"


def _survey(root: yaml.Node) -> _Survey | None:
    """The line of every key and list item, and every key given twice; `None` past the node budget.

    Walks the composed nodes, before anything is constructed from them, following aliases (an
    alias is the anchored node itself) and merge keys, iteratively so a recursive alias meets the
    budget rather than the interpreter's recursion limit.
    """
    lines: dict[str, int] = {"": root.start_mark.line + 1}
    duplicates: list[RecipeError] = []
    stack: list[tuple[yaml.Node, RecipeLocation]] = [(root, ())]
    visited = 0
    while stack:
        node, location = stack.pop()
        visited += 1
        if visited > RECIPE_MAX_NODES:
            return None
        if isinstance(node, yaml.SequenceNode):
            for index, item in enumerate(node.value):  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
                child = (*location, index)
                lines[render_location(child)] = item.start_mark.line + 1  # pyright: ignore[reportUnknownMemberType]
                stack.append((item, child))  # pyright: ignore[reportUnknownArgumentType]
        elif isinstance(node, yaml.MappingNode):
            explicit: set[str] = set()
            for key_node, value_node in _pairs(node, merged=False):
                key = str(key_node.value)
                child = (*location, key)
                if key in explicit:
                    duplicates.append(
                        RecipeError(
                            RecipeErrorCode.DUPLICATE_KEY,
                            render_location(child),
                            key_node.start_mark.line + 1,
                            f"`{key}` is given twice in this mapping; give it once",
                        )
                    )
                explicit.add(key)
                lines[render_location(child)] = key_node.start_mark.line + 1
                stack.append((value_node, child))
            for key_node, value_node in _pairs(node, merged=True):
                key = str(key_node.value)
                if key in explicit:
                    continue  # an explicit key overrides a merged one; that is what a merge is for
                explicit.add(key)
                child = (*location, key)
                lines[render_location(child)] = key_node.start_mark.line + 1
                stack.append((value_node, child))
    return _Survey(lines=lines, duplicates=tuple(duplicates))


def _pairs(node: yaml.MappingNode, *, merged: bool) -> list[tuple[yaml.ScalarNode, yaml.Node]]:
    """A mapping's own scalar-keyed pairs, or with `merged` the pairs its `<<` keys bring in."""
    own: list[tuple[yaml.ScalarNode, yaml.Node]] = []
    sources: list[yaml.Node] = []
    for key_node, value_node in node.value:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(key_node, yaml.ScalarNode):
            continue  # a mapping or list as a key: the models refuse it by its value
        if key_node.tag == _MERGE_TAG:
            sources += value_node.value if isinstance(value_node, yaml.SequenceNode) else [value_node]  # pyright: ignore[reportUnknownMemberType]
        else:
            own.append((key_node, value_node))  # pyright: ignore[reportUnknownArgumentType]
    if not merged:
        return own
    brought: list[tuple[yaml.ScalarNode, yaml.Node]] = []
    for source in sources:
        if isinstance(source, yaml.MappingNode) and source is not node:
            brought += _pairs(source, merged=False) + _pairs(source, merged=True)
    return brought


def _location(loc: Sequence[int | str]) -> RecipeLocation:
    """A validation error's location without the item kind pydantic puts after an item's index."""
    kept: list[int | str] = []
    for index, part in enumerate(loc):
        if (
            part in RECIPE_ITEM_TAGS
            and index >= 2
            and isinstance(loc[index - 1], int)
            and loc[index - 2] == "items"
        ):
            continue
        kept.append(part)
    return tuple(kept)


def _line_of(location: RecipeLocation, lines: Mapping[str, int]) -> int | None:
    """The line of `location`, or of the nearest enclosing key or item when it is not written."""
    for end in range(len(location), -1, -1):
        line = lines.get(render_location(location[:end]))
        if line is not None:
            return line
    return None


_MODELS: Final[dict[str, type[Any]]] = {
    "recipe": FileRecipe,
    "pocket": Pocket,
    "hat": Hat,
    "block": Block,
    "card": CardRef,
    "analytic": Analytic,
    "pin": OccurrencePin,
}

_EMPTY_SECTIONS: Final = {
    "structure": "a recipe holds at least one pocket",
    "hats": "an empty section: a `hats:` list holds at least one hat (leave it out for a pocket of blocks)",
    "blocks": "an empty section: a `blocks:` list holds at least one block",
    "items": "an empty section: a block holds at least one item",
}

_PATTERNS: Final = {
    "fingerprint": "a fingerprint is an E31 exact fingerprint: 64 lowercase hex characters",
    "source_sha256": "a source SHA-256 is 64 lowercase hex characters",
    "topic": "a topic id is kebab-case: lowercase letters and digits joined by single hyphens",
    "position": "a position id is kebab-case: lowercase letters and digits joined by single hyphens",
    "caselist": "a caselist is its slug, letters and a two-digit year, such as hsld26",
}

_DIGESTS: Final = frozenset({"fingerprint", "source_sha256"})
_LENGTH_ERRORS: Final = frozenset({"string_too_short", "string_too_long"})

_HEADING_KEYS: Final = {
    "items": "items sit in a block",
    "blocks": "blocks sit in a hat or straight in a pocket",
    "hats": "hats sit in a pocket",
}


def _kind_at(raw: Sequence[int | str]) -> str:
    """Which part of a recipe the error location `raw` (item kind included) points into."""
    if not raw:
        return "recipe"
    last = raw[-1]
    if last in RECIPE_ITEM_TAGS and len(raw) >= 2 and isinstance(raw[-2], int):
        return str(last)
    if last == "pin":
        return "pin"
    if isinstance(last, int) and len(raw) >= 2:
        return {"structure": "pocket", "hats": "hat", "blocks": "block"}.get(str(raw[-2]), "item")
    return "recipe"


def _field_error(issue: Any, lines: Mapping[str, int]) -> RecipeError:
    """One validation error as a :class:`RecipeError`, in words a coach can act on."""
    raw: tuple[int | str, ...] = tuple(issue["loc"])
    location = _location(raw)
    kind: str = issue["type"]
    key = location[-1] if location else ""
    message = str(issue["msg"]).removeprefix("Value error, ")
    if kind == "extra_forbidden":
        container = _kind_at(raw[:-1])
        if key in _HEADING_KEYS:
            message = f"`{key}` here skips or repeats a heading level: {_HEADING_KEYS[str(key)]}"
        else:
            model = _MODELS.get(container)
            known = ", ".join(model.model_fields) if model is not None else ""
            article = "an" if container[0] in "aeiou" else "a"
            message = f"`{key}` is not a field of {article} {container}" + (
                f"; {article} {container} has {known}" if known else ""
            )
    elif kind == "too_short" and key in _EMPTY_SECTIONS:
        message = _EMPTY_SECTIONS[str(key)]
    elif (kind == "string_pattern_mismatch" and key in _PATTERNS) or (
        kind in _LENGTH_ERRORS and key in _DIGESTS
    ):
        message = _PATTERNS[str(key)]
    elif kind == "missing":
        message = f"`{key}` is required here"
    value = issue.get("input")
    if kind == "string_type" and isinstance(value, int | float) and not isinstance(value, bool):
        message += "; YAML read it as a number, so put it in quotes"
    if isinstance(value, str) and value:
        message = message.replace(repr(value), "the value given")
    return RecipeError(RecipeErrorCode.INVALID, render_location(location), _line_of(location, lines), message)


# ------------------------------------------------------------------------------------------------
# Resolving
# ------------------------------------------------------------------------------------------------


class OccurrenceStoreNotReady(DomainError):
    """The occurrence store a recipe needs cannot be read as it stands. Never read as empty.

    No version directory of the resolver's parser version, no `occurrences.jsonl` in it (a removal
    deletes the aggregates until the next `caselist parse`), or rows stamped with a fingerprint
    version whose exact fingerprints are not today's.
    """

    def __init__(self, caselist: str, reason: str) -> None:
        self.caselist = caselist
        self.reason = reason
        super().__init__(f"the occurrence store of {caselist} is not ready: {reason}")


class Resolution(StrEnum):
    """How a card's occurrence was chosen."""

    PINNED = "PINNED"
    """The recipe's pin named it."""

    AUTO = "AUTO"
    """Chosen by the rule: latest snapshot, then lowest source SHA-256 (see the module docstring)."""


@dataclass(frozen=True, slots=True)
class ResolvedCard:
    """A card reference and the occurrence its card is to be copied from.

    `disclosure` is who disclosed that occurrence, for the built file's provenance line and sidecar,
    or `None` when the caselist records hold no disclosure with the row's digest. It holds a school,
    a team code and a path, so it is kept off the `repr`.
    """

    path: str
    fingerprint: str
    tag_override: TagOverride | None
    resolution: Resolution
    occurrence: OccurrenceRecord
    disclosure: Disclosure | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class ResolvedRecipe:
    """A recipe, its hash, each card's occurrence in recipe order, and every resolution error.

    `versions` is the version directory read for each caselist. A recipe with errors resolves the
    cards it can, so every error is reported at once; it is not built until `errors` is empty.
    """

    recipe: FileRecipe
    recipe_hash: str
    versions: Mapping[str, str]
    cards: tuple[ResolvedCard, ...]
    errors: tuple[RecipeError, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(frozen=True, slots=True)
class _Store:
    """One caselist's occurrence rows, indexed the two ways a recipe asks for them."""

    version: str
    by_fingerprint: Mapping[str, tuple[OccurrenceRecord, ...]]
    by_position: Mapping[tuple[str, int], tuple[OccurrenceRecord, ...]]


type _Attribution = tuple[str, str, str, str, str] | None


def _auto_order(row: OccurrenceRecord) -> tuple[int, str, int, str]:
    """Latest snapshot first, then lowest source SHA-256, element index and disclosure digest."""
    return (
        -date.fromisoformat(row.last_snapshot).toordinal(),
        row.source_sha256,
        row.first_element_index,
        row.disclosure or "",
    )


def _attribution(disclosure: Disclosure | None) -> _Attribution:
    """Who disclosed an occurrence, as the fields that make two disclosures two occurrences."""
    if disclosure is None:
        return None
    round_raw = disclosure.round_label.raw if disclosure.round_label is not None else ""
    return (
        disclosure.school,
        disclosure.team_code,
        str(disclosure.side),
        disclosure.tournament or "",
        round_raw,
    )


def _pin_matches(pin: OccurrencePin, row: OccurrenceRecord, disclosure: Disclosure | None) -> bool:
    """Whether a row and its disclosure agree with every field the pin gives beyond its key."""
    if pin.snapshot is not None and not (
        date.fromisoformat(row.snapshot) <= pin.snapshot <= date.fromisoformat(row.last_snapshot)
    ):
        return False
    wanted = (pin.school, pin.team_code, pin.side, pin.tournament, pin.round)
    if all(one is None for one in wanted):
        return True
    if disclosure is None:
        return False
    round_raw = disclosure.round_label.raw if disclosure.round_label is not None else None
    held = (disclosure.school, disclosure.team_code, disclosure.side, disclosure.tournament, round_raw)
    return all(want is None or want == have for want, have in zip(wanted, held, strict=True))


def _pinned_fields(pin: OccurrencePin) -> str:
    named = [
        name
        for name in ("snapshot", "school", "team_code", "side", "tournament", "round")
        if getattr(pin, name)
    ]
    return ", ".join(named)


class RecipeResolver:
    """Maps each card reference of a recipe to one occurrence in the E31 occurrence store."""

    def __init__(
        self,
        *,
        parsed_store: ParsedStore,
        caselists: CaselistRepository,
        suppression: SuppressionList,
        parser_version: str,
    ) -> None:
        """`parser_version` is the running parser's: its newest generation is the directory read."""
        self._ports = _Ports(parsed_store, caselists, suppression, parser_version)

    async def resolve(self, recipe: FileRecipe, *, lines: Mapping[str, int] | None = None) -> ResolvedRecipe:
        """Resolve every card reference, collecting every error. `lines` places errors in the text.

        Raises :class:`OccurrenceStoreNotReady` when the recipe's own caselist cannot be read.
        """
        return await _Resolution(self._ports, recipe, lines or {}).resolve()


@dataclass(frozen=True, slots=True)
class _Ports:
    store: ParsedStore
    caselists: CaselistRepository
    suppression: SuppressionList
    parser_version: str

    async def read(self, caselist: str) -> _Store | None:
        """The newest generation of this parser version's directory; `None` when there is none."""
        generations = [
            generation
            for name in await self.store.version_directories(caselist)
            for named, generation in [parse_version_directory(name)]
            if named == self.parser_version
        ]
        if not generations:
            return None
        version = version_directory_name(self.parser_version, max(generations))
        rows = await self.store.read_occurrences(caselist, version)
        if rows is None:
            raise OccurrenceStoreNotReady(
                caselist,
                f"{version} has no occurrences.jsonl; rebuild it with "
                f"`debate-research caselist parse --caselist {caselist}`",
            )
        stale = sorted({row.fingerprint_version for row in rows} - EXACT_FINGERPRINT_VERSIONS)
        if stale:
            raise OccurrenceStoreNotReady(
                caselist,
                f"its rows carry fingerprint version {', '.join(stale)}, whose exact fingerprints this build "
                f"does not compute; rebuild it with `debate-research caselist parse --caselist {caselist}`",
            )
        by_fingerprint: dict[str, list[OccurrenceRecord]] = {}
        by_position: dict[tuple[str, int], list[OccurrenceRecord]] = {}
        for row in rows:
            by_fingerprint.setdefault(row.exact_fingerprint, []).append(row)
            by_position.setdefault((row.source_sha256, row.first_element_index), []).append(row)
        return _Store(
            version=version,
            by_fingerprint={key: tuple(value) for key, value in by_fingerprint.items()},
            by_position={key: tuple(value) for key, value in by_position.items()},
        )

    async def disclosures(self, caselist: str, source_sha256: str) -> tuple[Disclosure, ...]:
        """Every disclosure of `source_sha256` the caselist records hold, all pages."""
        found: list[Disclosure] = []
        cursor: str | None = None
        while True:
            page = await self.caselists.list_disclosures(
                caselist=caselist, source_sha256=source_sha256, limit=_DISCLOSURE_PAGE, cursor=cursor
            )
            found += page.items
            if page.next_cursor is None:
                return tuple(found)
            cursor = page.next_cursor


class _Resolution:
    """One resolve call: the stores and disclosures it has read, and what it has found."""

    def __init__(self, ports: _Ports, recipe: FileRecipe, lines: Mapping[str, int]) -> None:
        self._ports = ports
        self._recipe = recipe
        self._lines = lines
        self._stores: dict[str, _Store | None] = {}
        self._disclosures: dict[tuple[str, str], tuple[Disclosure, ...]] = {}
        self._errors: list[RecipeError] = []

    async def resolve(self) -> ResolvedRecipe:
        recipe = self._recipe
        digest = recipe_hash(recipe)
        version_errors = _version_errors(recipe.fingerprint_version, self._lines)
        if version_errors:
            return ResolvedRecipe(recipe, digest, {}, (), tuple(version_errors))
        own = await self._store_of(recipe.caselist)
        if own is None:
            raise OccurrenceStoreNotReady(
                recipe.caselist,
                f"no version directory of parser {self._ports.parser_version}; "
                f"run `debate-research caselist parse --caselist {recipe.caselist}`",
            )
        state = await load_suppression_state(self._ports.suppression)
        cards: list[ResolvedCard] = []
        first_seen: dict[str, str] = {}
        for location, ref in recipe.card_refs():
            path = render_location(location)
            if ref.fingerprint in first_seen:
                self._error(
                    RecipeErrorCode.DUPLICATE_REF,
                    f"{path}.fingerprint",
                    f"this card is already in the file at {first_seen[ref.fingerprint]}; "
                    "a file holds a card once",
                )
                continue
            first_seen[ref.fingerprint] = path
            if ref.pin is None:
                resolved = await self._auto(ref, path, own, state)
            else:
                resolved = await self._pinned(ref, ref.pin, path, state)
            if resolved is not None:
                cards.append(resolved)
        versions = {caselist: store.version for caselist, store in self._stores.items() if store is not None}
        return ResolvedRecipe(recipe, digest, versions, tuple(cards), tuple(self._errors))

    async def _auto(
        self, ref: CardRef, path: str, store: _Store, state: SuppressionState
    ) -> ResolvedCard | None:
        caselist = self._recipe.caselist
        rows = store.by_fingerprint.get(ref.fingerprint, ())
        if not rows:
            self._error(
                RecipeErrorCode.UNKNOWN_CARD,
                f"{path}.fingerprint",
                f"{caselist}'s occurrence store ({store.version}) has no card with this fingerprint",
            )
            return None
        live = [row for row in rows if not state.suppresses(row.source_sha256, disclosure=row.disclosure)]
        if not live:
            self._error(
                RecipeErrorCode.SUPPRESSED_OCCURRENCE,
                f"{path}.fingerprint",
                f"the removal suppression list stops every occurrence of this card in {caselist} "
                f"({len(rows)})",
            )
            return None
        row = min(live, key=_auto_order)
        return self._resolved(ref, path, Resolution.AUTO, row, await self._disclosure_of(row))

    async def _pinned(
        self, ref: CardRef, pin: OccurrencePin, path: str, state: SuppressionState
    ) -> ResolvedCard | None:
        where = f"{path}.pin"
        if state.suppresses_source(pin.source_sha256):
            self._error(
                RecipeErrorCode.SUPPRESSED_OCCURRENCE,
                where,
                "the pinned source is on the removal suppression list as a whole file; a pin to it is "
                "refused, never moved to another occurrence: pin another, or remove the pin",
            )
            return None
        store = await self._store_of(pin.caselist)
        if store is None:
            self._error(
                RecipeErrorCode.PIN_MISMATCH,
                where,
                f"this machine has no occurrence store of {pin.caselist} under parser "
                f"{self._ports.parser_version}",
            )
            return None
        at = store.by_position.get((pin.source_sha256, pin.element_index), ())
        if not at:
            message = (
                f"no card in {pin.caselist}'s occurrence store starts at element {pin.element_index} "
                f"of source {pin.source_sha256[:12]}"
            )
            if state.is_suppressed(pin.source_sha256):
                message += "; a disclosure of that source has been withdrawn, and a pin to it cannot be used"
            self._error(RecipeErrorCode.PIN_MISMATCH, where, message)
            return None
        same = [row for row in at if row.exact_fingerprint == ref.fingerprint]
        if not same:
            self._error(
                RecipeErrorCode.PIN_MISMATCH,
                where,
                f"the card at element {pin.element_index} of source {pin.source_sha256[:12]} is another card "
                f"(fingerprint {at[0].exact_fingerprint[:12]}); the pin and the fingerprint disagree",
            )
            return None
        matching: list[tuple[OccurrenceRecord, Disclosure | None]] = []
        for row in same:
            disclosure = await self._disclosure_of(row)
            if _pin_matches(pin, row, disclosure):
                matching.append((row, disclosure))
        if not matching:
            self._error(
                RecipeErrorCode.PIN_MISMATCH,
                where,
                f"{len(same)} disclosure(s) hold this card there, and none matches the pin's "
                f"{_pinned_fields(pin)}",
            )
            return None
        if len({_attribution(disclosure) for _, disclosure in matching}) > 1:
            self._error(
                RecipeErrorCode.PIN_MISMATCH,
                where,
                f"the pin matches {len(matching)} disclosures of this card that differ in school, team "
                "code, side, tournament or round; add the fields that say which one is meant",
            )
            return None
        if any(state.suppresses(row.source_sha256, disclosure=row.disclosure) for row, _ in matching):
            self._error(
                RecipeErrorCode.SUPPRESSED_OCCURRENCE,
                where,
                "the pinned disclosure has been withdrawn (removal suppression list); a pin to it is "
                "refused, never moved to another occurrence: pin another, or remove the pin",
            )
            return None
        row, disclosure = min(matching, key=lambda pair: _auto_order(pair[0]))
        return self._resolved(ref, path, Resolution.PINNED, row, disclosure)

    def _resolved(
        self,
        ref: CardRef,
        path: str,
        resolution: Resolution,
        row: OccurrenceRecord,
        disclosure: Disclosure | None,
    ) -> ResolvedCard:
        return ResolvedCard(
            path=path,
            fingerprint=ref.fingerprint,
            tag_override=ref.tag_override,
            resolution=resolution,
            occurrence=row,
            disclosure=disclosure,
        )

    async def _store_of(self, caselist: str) -> _Store | None:
        if caselist not in self._stores:
            self._stores[caselist] = await self._ports.read(caselist)
        return self._stores[caselist]

    async def _disclosure_of(self, row: OccurrenceRecord) -> Disclosure | None:
        """The latest disclosure record whose digest is the row's; `None` when none is on record."""
        if row.disclosure is None:
            return None
        key = (row.caselist, row.source_sha256)
        if key not in self._disclosures:
            self._disclosures[key] = await self._ports.disclosures(*key)
        matching = [
            disclosure
            for disclosure in self._disclosures[key]
            if disclosure_digest(row.caselist, disclosure.source_path) == row.disclosure
        ]
        return max(matching, key=lambda one: (one.snapshot, one.source_path)) if matching else None

    def _error(self, code: RecipeErrorCode, path: str, message: str) -> None:
        self._errors.append(RecipeError(code, path, self._lines.get(path), message))
