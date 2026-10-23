"""What a landscape classification says about one section or card, and the coach's overrides.

E32 counts the positions a caselist's teams read. `v1-e32-t02-position-classification` places each
parsed section (a pocket, hat or block heading) and each card under one position of the topic's
taxonomy (:mod:`debate_core.domain.landscape`), or under none. This module is the contract every
stage writes and every report reads.

## A classification

:class:`PositionClassification` names the item (:class:`ItemKind`, the source's digest, and for a
card its first paragraph, which is how the occurrence table names it too), the position or none, the
:class:`PositionRole` (a team READS a position, or ANSWERS it under an `AT:` heading), a confidence
from 0 to 1, a short rationale, the :class:`ClassificationMethod` that placed it, and the taxonomy
version it was placed under.

* **The rationale never holds the item's own text.** It names the rule that fired and the alias,
  keyword or override heading that matched: text from the committed taxonomy and overrides, which
  the config test checks for personal data. A heading or tag as a team wrote it is never copied in.
* **A model result says which model.** `MODEL` is in the contract for `v1-e32-t07`, which writes
  it; a MODEL result carries `prompt_id`, a semver `prompt_version` and `model_id`. Every other
  method is deterministic and carries none of them, with `prompt_version` set to
  :data:`DETERMINISTIC_PROMPT_VERSION`, the literal `none` that the cache key and the report header
  use (the PM's amendment of 2026-10-22).
* **No method, no position.** An item nothing placed has `method` None, `position_id` None and
  confidence 0, and goes to the review queue. An item the coach ruled names no position has
  `method` OVERRIDE and `position_id` None, and does not.

## Only the taxonomy's own ids

:func:`classification_schema` builds, per taxonomy version, a model whose `position_id` is a
`Literal` of that taxonomy's active ids; it is the schema `v1-e32-t07` hands the model, and
:func:`checked_against` validates any result through it, so a retired id, an id from another topic
or a result stamped with another version is refused wherever a result is accepted.

## Overrides

`config/landscape/overrides/<topic id>.yaml` is an :class:`OverrideRules`: the coach's decisions from
the review queue, each a normalized heading and the position it names, or None for a heading that
names no position. The matcher reads an override before the aliases. Like an alias, an override's
heading is written as the normalizer leaves a heading.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from datetime import date
from enum import StrEnum
from typing import Annotated, Any, Final, Literal, Self

from pydantic import Field, create_model, model_validator

from debate_core.domain.base import DomainModel, NonEmptyText, Sha256Hex
from debate_core.domain.landscape import (
    POSITION_ID_PATTERN,
    TAXONOMY_VERSION_PATTERN,
    Alias,
    PositionId,
    Taxonomy,
    TaxonomyVersion,
)

__all__ = [
    "DETERMINISTIC_PROMPT_VERSION",
    "NO_OVERRIDE_DIGEST",
    "RATIONALE_LIMIT",
    "ClassificationMethod",
    "ClassificationResult",
    "HeadingOverride",
    "ItemKind",
    "OverrideRules",
    "PositionClassification",
    "PositionRole",
    "card_item_id",
    "checked_against",
    "classification_schema",
    "section_item_id",
]

DETERMINISTIC_PROMPT_VERSION: Final = "none"
"""The prompt version of every result no model wrote: the cache key's and the report header's `none`."""

RATIONALE_LIMIT: Final = 280
"""The longest rationale a classification may carry, in characters (ac2)."""

NO_OVERRIDE_DIGEST: Final = "none"
""":meth:`OverrideRules.digest_for` of headings no override names."""


class PositionRole(StrEnum):
    """Whether the item reads the position or answers it."""

    READS = "READS"
    """The team reads it: a plan, a DA shell, a K's blocks."""

    ANSWERS = "ANSWERS"
    """The team answers it, under an `AT:` or `A2` heading. A report never counts this as a read."""


class ClassificationMethod(StrEnum):
    """What placed an item. Every method but MODEL is deterministic."""

    ALIAS = "ALIAS"
    """The heading directly over the item is an alias of the position."""

    TAG_KEYWORD = "TAG_KEYWORD"
    """A card's tag holds one of the position's tag keywords."""

    INHERITED = "INHERITED"
    """A heading further up the path placed it: the nearest placed heading above the item."""

    OVERRIDE = "OVERRIDE"
    """The coach's decision on the heading directly over the item."""

    MODEL = "MODEL"
    """The model stage (`v1-e32-t07`); this task writes none."""


class ItemKind(StrEnum):
    """What was classified."""

    SECTION = "SECTION"
    """A pocket, hat or block heading path, as the cards under it record it."""

    CARD = "CARD"
    """One card."""


_PROMPT_VERSION: Final = TAXONOMY_VERSION_PATTERN
"""A model prompt's version is semver too, written as the taxonomy's is."""


class ClassificationResult(DomainModel):
    """Where an item was placed and why: everything a classification says except which item it is.

    The cache (`ClassificationStore`) keeps this per item fingerprint, since two items with the same
    headings and tag are placed alike.
    """

    position_id: PositionId | None = Field(description="The position, or None when none was placed.")
    role: PositionRole | None = Field(description="READS or ANSWERS; None exactly when no position is.")
    confidence: float = Field(ge=0.0, le=1.0, description="How sure the method is, from 0 to 1.")
    rationale: Annotated[NonEmptyText, Field(max_length=RATIONALE_LIMIT)] = Field(
        description="The rule that fired and what it matched; never the item's own heading, tag or text."
    )
    method: ClassificationMethod | None = Field(description="What placed it; None when nothing did.")
    taxonomy_version: TaxonomyVersion = Field(description="The taxonomy version it was placed under.")
    prompt_id: NonEmptyText | None = Field(default=None, description="MODEL only: the prompt's id.")
    prompt_version: str = Field(
        default=DETERMINISTIC_PROMPT_VERSION,
        description="MODEL: the prompt's semver. Every other method: `none`.",
    )
    model_id: NonEmptyText | None = Field(default=None, description="MODEL only: the model that answered.")

    @model_validator(mode="after")
    def _check_result(self) -> Self:
        if (self.position_id is None) != (self.role is None):
            raise ValueError("a role is given exactly when a position is")
        if self.method is None:
            if self.position_id is not None:
                raise ValueError("a placed item names the method that placed it")
            if self.confidence != 0.0:
                raise ValueError("an item nothing placed has confidence 0")
        if self.method is ClassificationMethod.MODEL:
            if self.prompt_id is None or self.model_id is None:
                raise ValueError("a MODEL result names its prompt_id and model_id")
            if not _is_semver(self.prompt_version):
                raise ValueError(f"a MODEL result's prompt_version is semver; got {self.prompt_version!r}")
        else:
            if self.prompt_id is not None or self.model_id is not None:
                raise ValueError("only a MODEL result names a prompt or a model")
            if self.prompt_version != DETERMINISTIC_PROMPT_VERSION:
                raise ValueError(
                    f"a result no model wrote has prompt_version {DETERMINISTIC_PROMPT_VERSION!r}; "
                    f"got {self.prompt_version!r}"
                )
        return self


def _is_semver(text: str) -> bool:
    return re.match(_PROMPT_VERSION, text) is not None


_CARD_ID: Final = "{sha}:card:{index}"
_SECTION_ID_DIGITS: Final = 16


def card_item_id(source_sha256: str, first_element_index: int) -> str:
    """`<source digest>:card:<first paragraph>`: the card as the occurrence table names it."""
    return _CARD_ID.format(sha=source_sha256, index=first_element_index)


def section_item_id(source_sha256: str, raw_path: Iterable[str]) -> str:
    """`<source digest>:section:<16 hex>`, the hex a digest of the heading path as the file wrote it.

    Two pockets one file writes alike are one section; the digest keeps the headings out of the id.
    """
    digest = hashlib.sha256(json.dumps(list(raw_path), ensure_ascii=False).encode()).hexdigest()
    return f"{source_sha256}:section:{digest[:_SECTION_ID_DIGITS]}"


class PositionClassification(ClassificationResult):
    """One item's classification, as the report (`v1-e32-t03`) reads it (ac2)."""

    item_id: NonEmptyText = Field(
        description="`<source digest>:card:<index>` or `<source digest>:section:<hex>`."
    )
    item_kind: ItemKind = Field(description="SECTION or CARD.")
    source_sha256: Sha256Hex = Field(description="The parsed source the item is in.")
    first_element_index: int | None = Field(
        ge=0, description="A card's first paragraph in its document; None for a section."
    )

    @model_validator(mode="after")
    def _check_item(self) -> Self:
        if self.item_kind is ItemKind.CARD:
            if self.first_element_index is None:
                raise ValueError("a card names its first paragraph")
            if self.item_id != card_item_id(self.source_sha256, self.first_element_index):
                raise ValueError(f"a card's item_id is <digest>:card:<index>; got {self.item_id!r}")
        else:
            if self.first_element_index is not None:
                raise ValueError("a section names no paragraph")
            prefix = f"{self.source_sha256}:section:"
            rest = self.item_id.removeprefix(prefix)
            if rest == self.item_id or len(rest) != _SECTION_ID_DIGITS or not _is_hex(rest):
                raise ValueError(f"a section's item_id is <digest>:section:<16 hex>; got {self.item_id!r}")
        return self

    @property
    def result(self) -> ClassificationResult:
        """The placement without the item: what the cache keeps."""
        return ClassificationResult.model_validate(
            self.model_dump(exclude={"item_id", "item_kind", "source_sha256", "first_element_index"})
        )


def _is_hex(text: str) -> bool:
    return all(character in "0123456789abcdef" for character in text)


# ------------------------------------------------------------------------------------------------
# Only the taxonomy's own ids
# ------------------------------------------------------------------------------------------------

_SCHEMAS: dict[tuple[str, str, tuple[str, ...]], type[ClassificationResult]] = {}


def classification_schema(taxonomy: Taxonomy) -> type[ClassificationResult]:
    """A result model whose `position_id` is one of `taxonomy`'s active ids, and whose version is its own.

    Built once per (topic, version, active ids). The JSON schema of the model it returns lists the
    ids as an enum, which is what a structured-output call is held to.
    """
    ids = tuple(position.id for position in taxonomy.active_positions)
    key = (taxonomy.topic_id, taxonomy.taxonomy_version, ids)
    found = _SCHEMAS.get(key)
    if found is None:
        literal: Any = Literal[ids] if ids else None  # pyright: ignore[reportInvalidTypeForm]
        position_type: Any = literal | None if ids else type(None)
        version_type: Any = Literal[taxonomy.taxonomy_version]  # pyright: ignore[reportInvalidTypeForm]
        found = create_model(
            f"PositionClassificationFor_{_identifier(taxonomy.topic_id)}_{_identifier(taxonomy.taxonomy_version)}",
            __base__=ClassificationResult,
            position_id=(
                position_type,
                Field(description="One of the taxonomy's active position ids, or None."),
            ),
            taxonomy_version=(version_type, Field(description="This taxonomy's version.")),
        )
        _SCHEMAS[key] = found
    return found


def _identifier(text: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in text)


def checked_against[ResultT: ClassificationResult](taxonomy: Taxonomy, result: ResultT) -> ResultT:
    """`result` when its position is one of `taxonomy`'s active ids and its version is the taxonomy's.

    Raises `pydantic.ValidationError` otherwise: a retired id, another topic's id, an invented one, or a
    result placed under another version.
    """
    classification_schema(taxonomy).model_validate(
        result.model_dump(include=set(ClassificationResult.model_fields))
    )
    return result


# ------------------------------------------------------------------------------------------------
# Overrides
# ------------------------------------------------------------------------------------------------


class HeadingOverride(DomainModel):
    """One coach decision: a normalized heading, and the position it names or None."""

    heading: Alias = Field(description="A heading as the normalizer leaves it, like an alias.")
    position_id: PositionId | None = Field(
        description="The position the heading names; None when the coach ruled it names none."
    )
    decided: date | None = Field(default=None, description="The day the decision was applied.")


class OverrideRules(DomainModel):
    """`config/landscape/overrides/<topic id>.yaml`: the coach's decisions on one topic's headings."""

    schema_version: Literal[1] = Field(default=1, description="Version of this file's shape.")
    topic_id: Annotated[str, Field(pattern=POSITION_ID_PATTERN)] = Field(
        description="The topic, as topics.yaml names it; also the file's stem."
    )
    overrides: tuple[HeadingOverride, ...] = Field(default=(), description="Every decision, in file order.")

    @model_validator(mode="after")
    def _check_overrides(self) -> Self:
        seen: set[str] = set()
        for one in self.overrides:
            if one.heading in seen:
                raise ValueError(f"the heading {one.heading!r} is overridden twice")
            seen.add(one.heading)
        return self

    def rule(self, heading: str) -> HeadingOverride | None:
        """The decision on `heading`, or None when the coach made none."""
        for one in self.overrides:
            if one.heading == heading:
                return one
        return None

    def rules_by_heading(self) -> dict[str, HeadingOverride]:
        return {one.heading: one for one in self.overrides}

    def check_against(self, taxonomy: Taxonomy) -> None:
        """Raise `ValueError` for a decision naming a position `taxonomy` does not count under.

        A retired id is accepted when its `merged_into` links end at an active position, which is the
        one the matcher places the heading under; one retired with nowhere to go is refused.
        """
        if self.topic_id != taxonomy.topic_id:
            raise ValueError(f"overrides for {self.topic_id} cannot apply to {taxonomy.topic_id}")
        for one in self.overrides:
            if one.position_id is None:
                continue
            try:
                resolved = taxonomy.resolve(one.position_id)
            except KeyError:
                raise ValueError(
                    f"the override of {one.heading!r} names {one.position_id}, which is not a position "
                    f"of {taxonomy.topic_id} {taxonomy.taxonomy_version}"
                ) from None
            if resolved.deprecated:
                raise ValueError(
                    f"the override of {one.heading!r} names {one.position_id}, which is retired with no "
                    "position to count under"
                )

    def digest_for(self, headings: Iterable[str]) -> str:
        """A digest of the decisions on `headings`, or :data:`NO_OVERRIDE_DIGEST` when there are none.

        A cached result is keyed by it, so a decision invalidates only the items under its heading.
        """
        rules = self.rules_by_heading()
        named = sorted({heading for heading in headings if heading in rules})
        if not named:
            return NO_OVERRIDE_DIGEST
        payload = [[heading, rules[heading].position_id] for heading in named]
        return hashlib.sha256(json.dumps(payload).encode()).hexdigest()
