"""Access classification: one AccessStatus for every retrieval outcome (v1-e04-t03).

SKELETON for the red run: the models and the rules loader are real, `classify` refuses nothing.
"""

from __future__ import annotations

import functools
from enum import StrEnum
from importlib import resources
from typing import Annotated, Final, Literal, Self

from pydantic import AfterValidator, Field, model_validator

from debate_core.domain import AccessStatus, DomainModel, NonEmptyText
from debate_core.retrieval.extraction import ExtractedContent, ExtractionError
from debate_core.retrieval.fetch_types import FetchResult

__all__ = [
    "PAYWALL_RULES_FILE",
    "AccessClassifier",
    "AccessDecision",
    "AccessEvidence",
    "AccessThresholds",
    "ClassOrIdMarker",
    "DeclaredLengthSource",
    "HeaderMarker",
    "InlineScriptMarker",
    "Marker",
    "MarkerCategory",
    "MatchedMarker",
    "MetaMarker",
    "PaywallRules",
    "ScriptSourceMarker",
    "TitleMarker",
    "VisibleTextMarker",
    "bundled_paywall_rules",
]

PAYWALL_RULES_FILE: Final = "paywall_rules.v1.json"


def _normalized(value: str) -> str:
    if value != " ".join(value.lower().split()):
        raise ValueError(f"{value!r} must be written lower-case, single-spaced, with no space at either end")
    return value


type Normalized = Annotated[NonEmptyText, AfterValidator(_normalized)]


class MarkerCategory(StrEnum):
    PAYWALL = "paywall"
    CHALLENGE = "challenge"


class _MarkerBase(DomainModel):
    id: Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
    description: NonEmptyText


class HeaderMarker(_MarkerBase):
    kind: Literal["header"] = "header"
    name: Normalized
    contains: Normalized


class ScriptSourceMarker(_MarkerBase):
    kind: Literal["script_src"] = "script_src"
    contains: Normalized


class InlineScriptMarker(_MarkerBase):
    kind: Literal["inline_script"] = "inline_script"
    contains: NonEmptyText


class ClassOrIdMarker(_MarkerBase):
    kind: Literal["class_or_id"] = "class_or_id"
    token: Normalized


class MetaMarker(_MarkerBase):
    kind: Literal["meta"] = "meta"
    name: Normalized
    content: Normalized


class TitleMarker(_MarkerBase):
    kind: Literal["title"] = "title"
    equals: Normalized


class VisibleTextMarker(_MarkerBase):
    kind: Literal["visible_text"] = "visible_text"
    phrase: Normalized


type Marker = Annotated[
    HeaderMarker
    | ScriptSourceMarker
    | InlineScriptMarker
    | ClassOrIdMarker
    | MetaMarker
    | TitleMarker
    | VisibleTextMarker,
    Field(discriminator="kind"),
]


class PaywallRules(DomainModel):
    version: NonEmptyText
    description: NonEmptyText
    challenge_markers: tuple[Marker, ...] = Field(min_length=1)
    paywall_markers: tuple[Marker, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_ids_are_unique(self) -> Self:
        ids = [marker.id for marker in (*self.challenge_markers, *self.paywall_markers)]
        duplicates = sorted({marker_id for marker_id in ids if ids.count(marker_id) > 1})
        if duplicates:
            raise ValueError(f"marker ids must be unique; repeated: {', '.join(duplicates)}")
        return self


@functools.cache
def bundled_paywall_rules() -> PaywallRules:
    text = resources.files("debate_core.retrieval").joinpath(PAYWALL_RULES_FILE).read_text(encoding="utf-8")
    return PaywallRules.model_validate_json(text)


class AccessThresholds(DomainModel):
    minimum_characters: int = Field(default=500, ge=1)
    truncation_ratio: float = Field(default=0.5, gt=0, le=1)


class DeclaredLengthSource(StrEnum):
    JSON_LD_WORD_COUNT = "json_ld_word_count"
    JSON_LD_ARTICLE_BODY = "json_ld_article_body"


class MatchedMarker(DomainModel):
    category: MarkerCategory
    marker_id: NonEmptyText
    pattern: NonEmptyText


class AccessEvidence(DomainModel):
    status_code: int | None = None
    fetch_error: str | None = None
    extraction_refusal: str | None = None
    marker: MatchedMarker | None = None
    extracted_characters: int | None = Field(default=None, ge=0)
    extracted_words: int | None = Field(default=None, ge=0)
    declared_words: int | None = Field(default=None, ge=1)
    declared_length_source: DeclaredLengthSource | None = None
    thresholds: AccessThresholds | None = None


class AccessDecision(DomainModel):
    status: AccessStatus
    reason: NonEmptyText
    evidence: AccessEvidence
    rules_version: NonEmptyText


class AccessClassifier:
    def __init__(self, *, rules: PaywallRules | None = None, thresholds: AccessThresholds | None = None) -> None:
        self._rules = rules if rules is not None else bundled_paywall_rules()
        self._thresholds = thresholds if thresholds is not None else AccessThresholds()

    @property
    def rules_version(self) -> str:
        return self._rules.version

    def classify(
        self, fetched: FetchResult, extraction: ExtractedContent | ExtractionError | None
    ) -> AccessDecision:
        return AccessDecision(
            status=AccessStatus.ACCESSIBLE, reason="skeleton", evidence=AccessEvidence(), rules_version="skeleton"
        )
