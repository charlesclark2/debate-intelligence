"""Skeleton for the red run of v1-e06-t02's request-result-types node: it checks nothing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from debate_core.application.article_fetch import SOURCE_NOT_ACCESSIBLE_CODE
from debate_core.application.errors import DomainError
from debate_core.domain import AccessStatus, Card, Ulid
from debate_core.domain.card import DEFAULT_FORMAT_PROFILE
from debate_core.domain.provenance import SourcedArtifactMetadata
from debate_core.evidence.verification_types import ReasonCode, VerificationResult


class CardFailureReason(StrEnum):
    MODEL_OUTPUT_INVALID = "MODEL_OUTPUT_INVALID"
    SPAN_MISMATCH = "SPAN_MISMATCH"
    CITATION_UNVERIFIED = "CITATION_UNVERIFIED"
    EVIDENCE_UNVERIFIED = "EVIDENCE_UNVERIFIED"


@dataclass(frozen=True, slots=True)
class CardFailure:
    reason: CardFailureReason
    detail: str
    fields: tuple[str, ...] = ()
    verifier_code: ReasonCode | None = None


@dataclass(frozen=True, slots=True)
class CutRequest:
    snapshot_id: Ulid
    need: str
    owner_id: Ulid
    argument: str | None = None
    format_profile: str = DEFAULT_FORMAT_PROFILE
    organization_id: Ulid | None = None

    @property
    def research_need(self) -> str:
        return self.need


@dataclass(frozen=True, slots=True)
class CutResult:
    card: Card
    verification: VerificationResult
    metadata: tuple[SourcedArtifactMetadata, ...]
    reasons: tuple[CardFailure, ...]


class SourceNotAccessibleError(DomainError):
    ERROR_CODE: ClassVar[str] = "X"

    def __init__(self, snapshot_id: Ulid, access_status: AccessStatus) -> None:
        self.snapshot_id = snapshot_id
        self.access_status = access_status
        super().__init__("")


__all__ = [
    "SOURCE_NOT_ACCESSIBLE_CODE",
    "CardFailure",
    "CardFailureReason",
    "CutRequest",
    "CutResult",
    "SourceNotAccessibleError",
]
