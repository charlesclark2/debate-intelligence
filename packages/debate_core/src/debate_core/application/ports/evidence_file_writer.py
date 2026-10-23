"""The evidence file writer: a resolved recipe in, a Verbatim `.docx` and its provenance sidecar out.

`v1-e33-t01` resolves each card of a recipe to one occurrence in the E31 occurrence store. This port
turns that resolution into a file (`v1-e33-t02`): every card's tag, cite and evidence paragraphs are
copied as OOXML runs from the source file's own bytes, and the only text the writer adds is the
coach's (headings, tag overrides, analytics) and one header line saying the cards are disclosed and
unverified. A built file carries no provenance line (data-use policy version 1.11, `v1-e33-t08`);
each card's provenance is in the sidecar.

## No card text goes in

:class:`FileBuildRequest` holds the resolved recipe and the time of the request, and nothing else.
The resolved recipe names each card by fingerprint and occurrence, and carries the coach's text and
who disclosed the card, or for a camp card its release record (`v1-e33-t06`); no field of it, or of
this request, can carry evidence or cite text. The
writer reads a card's text only from its source's bytes, which it takes from the blob store by the
occurrence's SHA-256 (the task's first forbidden item).

## Nothing partial

A card the writer cannot copy losslessly refuses the whole file. :class:`FileBuildRefusal` lists every
such card, with what it holds that cannot be copied, and no `.docx` is produced: a file built with a
card missing, or with half a card, is worse than none.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from debate_core.application.file_recipes import ResolvedRecipe
from debate_core.domain.file_provenance import FileProvenanceManifest

__all__ = [
    "BuiltEvidenceFile",
    "CardRefusal",
    "CardRefusalCode",
    "EvidenceFileWriter",
    "FileBuildRefusal",
    "FileBuildRequest",
    "UnsupportedContentKind",
]


class UnsupportedContentKind(StrEnum):
    """Content inside a card that cannot be copied losslessly into a built file."""

    IMAGE = "IMAGE"
    """A picture (`w:drawing` or `w:pict` holding an image)."""

    TEXT_BOX = "TEXT_BOX"
    """A text box (`w:txbxContent`): its paragraphs are not the card's, and its shape is a drawing."""

    EMBEDDED_OBJECT = "EMBEDDED_OBJECT"
    """An embedded or linked object, a chart, a shape, a control or an alternative-format chunk."""

    FOOTNOTE = "FOOTNOTE"
    """A footnote or endnote reference: its text lives in a part the writer does not copy."""

    TABLE = "TABLE"
    """A table inside the card's paragraphs. Not in the spec's list; refused rather than guessed."""


class CardRefusalCode(StrEnum):
    """Why a card refused its file."""

    UNSUPPORTED_CONTENT = "UNSUPPORTED_CONTENT"
    """The card holds content the writer cannot copy losslessly (task ac4)."""

    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    """The source's bytes are not in the blob store, or no longer hash to their name."""

    SOURCE_UNREADABLE = "SOURCE_UNREADABLE"
    """The parser refuses the source's bytes."""

    OCCURRENCE_MISMATCH = "OCCURRENCE_MISMATCH"
    """No card of the occurrence's fingerprint starts and ends at its element indices in the source."""

    READBACK_MISMATCH = "READBACK_MISMATCH"
    """Re-parsing the built file does not give the source card's cite, evidence or formatting."""


@dataclass(frozen=True, slots=True)
class CardRefusal:
    """One card that stopped its file from being built, and why.

    `detail` names element indices, parts and kinds of content only: never card text, a school, a
    team code or a path.
    """

    path: str
    fingerprint: str
    code: CardRefusalCode
    detail: str
    content_kinds: tuple[UnsupportedContentKind, ...] = ()

    def __str__(self) -> str:
        kinds = f" ({', '.join(self.content_kinds)})" if self.content_kinds else ""
        return f"{self.path}: {self.code}{kinds}: {self.detail}"


@dataclass(frozen=True, slots=True)
class FileBuildRefusal:
    """A file that was not built, with every card that stopped it."""

    refusals: tuple[CardRefusal, ...]


@dataclass(frozen=True, slots=True)
class FileBuildRequest:
    """What to build: a resolved recipe with no errors, and when the build was asked for.

    `built_at` is the request's, never the writer's clock, so the same request builds the same bytes.
    It goes into the sidecar only; the `.docx` carries no time at all.
    """

    resolved: ResolvedRecipe
    built_at: datetime

    def __post_init__(self) -> None:
        if self.built_at.tzinfo is None or self.built_at.utcoffset() is None:
            raise ValueError("built_at is a time with its zone: a naive time names no instant")
        if not self.resolved.ok:
            raise ValueError("a recipe with resolution errors is not built; report them first")


@dataclass(frozen=True, slots=True)
class BuiltEvidenceFile:
    """A built file: the `.docx` bytes, its provenance sidecar, and what the writer warned about."""

    docx: bytes
    manifest: FileProvenanceManifest
    manifest_json: bytes
    warnings: tuple[str, ...] = field(default=())


@runtime_checkable
class EvidenceFileWriter(Protocol):
    """Builds one evidence file from a resolved recipe, or refuses it whole."""

    async def build(self, request: FileBuildRequest) -> BuiltEvidenceFile | FileBuildRefusal:
        """Copy every card from its source into a new file, or list every card that cannot be."""
        ...
