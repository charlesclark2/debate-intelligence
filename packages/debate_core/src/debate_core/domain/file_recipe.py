"""File recipe models: skeleton for the red run. Refuses nothing beyond the DomainModel base."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from enum import StrEnum
from typing import Annotated, Any, Final, Literal

from pydantic import BeforeValidator, Discriminator, PlainSerializer, Tag

from debate_core.domain.base import DomainModel
from debate_core.domain.caselist import Event, Side

__all__ = [
    "FILE_RECIPE_SCHEMA_VERSION",
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

type RecipeLocation = tuple[str | int, ...]


def render_location(location: RecipeLocation) -> str:
    return ".".join(str(part) for part in location)


class RecipeStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"


class TagAuthor(StrEnum):
    COACH = "COACH"


class TagOverride(DomainModel):
    text: str
    authored_by: Literal[TagAuthor.COACH] = TagAuthor.COACH


def _tag_from_text(value: object) -> object:
    return TagOverride(text=value) if isinstance(value, str) else value


def _tag_to_text(value: TagOverride | None) -> str | None:
    return None if value is None else value.text


class OccurrencePin(DomainModel):
    caselist: str
    source_sha256: str
    element_index: int
    snapshot: date | None = None
    school: str | None = None
    team_code: str | None = None
    side: Side | None = None
    tournament: str | None = None
    round: str | None = None


class CardRef(DomainModel):
    fingerprint: str
    tag_override: Annotated[
        TagOverride | None,
        BeforeValidator(_tag_from_text),
        PlainSerializer(_tag_to_text, return_type=str | None),
    ] = None
    pin: OccurrencePin | None = None


class Analytic(DomainModel):
    analytic: str


def _item_kind(value: Any) -> str | None:
    if isinstance(value, CardRef) or (isinstance(value, dict) and "fingerprint" in value):
        return "card"
    if isinstance(value, Analytic) or (isinstance(value, dict) and "analytic" in value):
        return "analytic"
    return None


RecipeItem = Annotated[
    Annotated[CardRef, Tag("card")] | Annotated[Analytic, Tag("analytic")],
    Discriminator(_item_kind),
]


class Block(DomainModel):
    block: str
    items: list[RecipeItem]


class Hat(DomainModel):
    hat: str
    blocks: list[Block]


class Pocket(DomainModel):
    pocket: str
    hats: list[Hat] | None = None
    blocks: list[Block] | None = None


class FileRecipe(DomainModel):
    schema_version: int
    title: str
    topic: str
    format: Event
    caselist: str
    position: str
    side: Side
    fingerprint_version: str
    status: RecipeStatus = RecipeStatus.READY
    structure: list[Pocket]

    def card_refs(self) -> Iterator[tuple[RecipeLocation, CardRef]]:
        for location, item in self.walk_items():
            if isinstance(item, CardRef):
                yield location, item

    def walk_items(self) -> Iterator[tuple[RecipeLocation, CardRef | Analytic]]:
        for p, pocket in enumerate(self.structure):
            for h, hat in enumerate(pocket.hats or ()):
                for b, block in enumerate(hat.blocks):
                    for i, item in enumerate(block.items):
                        yield ("structure", p, "hats", h, "blocks", b, "items", i), item
            for b, block in enumerate(pocket.blocks or ()):
                for i, item in enumerate(block.items):
                    yield ("structure", p, "blocks", b, "items", i), item
