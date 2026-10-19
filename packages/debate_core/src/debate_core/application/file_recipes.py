"""File recipes: skeleton for the red run. Loads, hashes and resolves without refusing anything."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final

import yaml
from pydantic import ValidationError

from debate_core.application.errors import DomainError
from debate_core.application.ports.caselist import CaselistRepository
from debate_core.application.ports.parsed_store import OccurrenceRecord, ParsedStore
from debate_core.application.ports.suppression import SuppressionList
from debate_core.domain.caselist import Disclosure
from debate_core.domain.file_recipe import FileRecipe, TagOverride, render_location

__all__ = [
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


class RecipeErrorCode(StrEnum):
    YAML_SYNTAX = "YAML_SYNTAX"
    DUPLICATE_KEY = "DUPLICATE_KEY"
    TOO_LARGE = "TOO_LARGE"
    INVALID = "INVALID"
    PIN_MISMATCH = "PIN_MISMATCH"
    UNKNOWN_CARD = "UNKNOWN_CARD"
    DUPLICATE_REF = "DUPLICATE_REF"
    SUPPRESSED_OCCURRENCE = "SUPPRESSED_OCCURRENCE"


@dataclass(frozen=True, slots=True)
class RecipeError:
    code: RecipeErrorCode
    path: str
    line: int | None
    message: str


@dataclass(frozen=True, slots=True)
class RecipeLoadResult:
    recipe: FileRecipe | None
    errors: tuple[RecipeError, ...]
    lines: Mapping[str, int] = field(default_factory=lambda: {})
    recipe_hash: str | None = None

    @property
    def ok(self) -> bool:
        return self.recipe is not None and not self.errors


def canonical_recipe_json(recipe: FileRecipe) -> str:
    return recipe.model_dump_json()


def recipe_hash(recipe: FileRecipe) -> str:
    return hashlib.sha256(canonical_recipe_json(recipe).encode()).hexdigest()


def load_recipe(text: str) -> RecipeLoadResult:
    data = yaml.safe_load(text)
    try:
        recipe = FileRecipe.model_validate(data)
    except ValidationError as error:
        first = error.errors()[0]
        return RecipeLoadResult(
            recipe=None,
            errors=(RecipeError(RecipeErrorCode.INVALID, render_location(first["loc"]), None, first["msg"]),),
        )
    return RecipeLoadResult(
        recipe=recipe, errors=(), recipe_hash=hashlib.sha256(text.encode()).hexdigest()
    )


def render_recipe_schema() -> dict[str, Any]:
    return FileRecipe.model_json_schema()


class OccurrenceStoreNotReady(DomainError):
    def __init__(self, caselist: str, reason: str) -> None:
        self.caselist = caselist
        self.reason = reason
        super().__init__(f"{caselist}: {reason}")


class Resolution(StrEnum):
    PINNED = "PINNED"
    AUTO = "AUTO"


@dataclass(frozen=True, slots=True)
class ResolvedCard:
    path: str
    fingerprint: str
    tag_override: TagOverride | None
    resolution: Resolution
    occurrence: OccurrenceRecord
    disclosure: Disclosure | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class ResolvedRecipe:
    recipe: FileRecipe
    recipe_hash: str
    versions: Mapping[str, str]
    cards: tuple[ResolvedCard, ...]
    errors: tuple[RecipeError, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


class RecipeResolver:
    def __init__(
        self,
        *,
        parsed_store: ParsedStore,
        caselists: CaselistRepository,
        suppression: SuppressionList,
        parser_version: str,
    ) -> None:
        self._store = parsed_store
        self._caselists = caselists
        self._suppression = suppression
        self._parser_version = parser_version

    async def resolve(self, recipe: FileRecipe, *, lines: Mapping[str, int] | None = None) -> ResolvedRecipe:
        rows: list[OccurrenceRecord] = []
        versions: dict[str, str] = {}
        for version in await self._store.version_directories(recipe.caselist):
            versions[recipe.caselist] = version
            rows.extend(await self._store.read_occurrences(recipe.caselist, version) or ())
        cards: list[ResolvedCard] = []
        for location, ref in recipe.card_refs():
            for row in rows:
                if row.exact_fingerprint == ref.fingerprint:
                    cards.append(
                        ResolvedCard(
                            path=render_location(location),
                            fingerprint=ref.fingerprint,
                            tag_override=ref.tag_override,
                            resolution=Resolution.AUTO,
                            occurrence=row,
                        )
                    )
                    break
        return ResolvedRecipe(
            recipe=recipe, recipe_hash=recipe_hash(recipe), versions=versions, cards=tuple(cards), errors=()
        )
