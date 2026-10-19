"""The provenance sidecar of a built evidence file: one record per card, saying where it came from.

`v1-e33-t02`'s lossless writer copies each card of a recipe out of a disclosed source file. Beside the
`.docx` it writes `<file>.provenance.json`, a :class:`FileProvenanceManifest`, and
`docs/data/file-provenance.schema.json` is that model's published schema.

## What the sidecar is for

The data-use policy (`docs/policies/caselist-data-use.md`, Attribution rule 3) makes it the record a
removal request is matched against: every card's fingerprint, source SHA-256 and element range, at
`provenance_mode` FILE_IMPORT. It is also what `v1-e33-t04`'s checks re-read a built file against:
`evidence_sha256`, `cite_sha256` and `formatting_sha256` are taken from the source card as the E31
parser reads it, and a re-parse of the built file must give the same three.

## Personal data

The policy names the built file's provenance line and its sidecar as places a school and a team code
may appear, inside the team only. They are written here exactly as disclosed, never expanded to a
name, and kept off every `repr`.

## Never verified

A card read out of somebody else's file has not been through the platform's verification pipeline.
Every entry says `FILE_IMPORT` and `UNVERIFIED`, and neither field can hold anything else (ADR-0006).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any, Final, Literal

from pydantic import AwareDatetime, Field, field_serializer

from debate_core.domain.base import DomainModel, NonEmptyText, Sha256Hex
from debate_core.domain.debate_files import CardCompleteness, FontSizeSpan, FormattingSpan
from debate_core.domain.enums import ProvenanceMode, VerificationStatus
from debate_core.domain.file_recipe import TagAuthor
from debate_core.domain.schema_export import JSON_SCHEMA_DIALECT

__all__ = [
    "FILE_PROVENANCE_SCHEMA_FILENAME",
    "FILE_PROVENANCE_SCHEMA_VERSION",
    "PROVENANCE_SIDECAR_SUFFIX",
    "FileProvenanceEntry",
    "FileProvenanceManifest",
    "formatting_sha256",
    "provenance_sidecar_name",
    "render_file_provenance_schema",
    "text_sha256",
]

FILE_PROVENANCE_SCHEMA_VERSION: Final = 1
"""The sidecar's shape. Bumped by a change an existing reader would break on."""

FILE_PROVENANCE_SCHEMA_FILENAME: Final = "file-provenance.schema.json"
"""The published schema's file name, under `docs/data/`."""

PROVENANCE_SIDECAR_SUFFIX: Final = ".provenance.json"
"""What a built file's name is followed by to name its sidecar: `nhi-politics.docx.provenance.json`."""


def provenance_sidecar_name(docx_name: str) -> str:
    """The sidecar's file name for a built file's name: `<file>.provenance.json`."""
    return f"{docx_name}{PROVENANCE_SIDECAR_SUFFIX}"


def text_sha256(text: str) -> str:
    """SHA-256 of `text` as UTF-8: the evidence, cite and tag digests of the sidecar."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _merged(intervals: Iterable[tuple[int, int]]) -> list[list[int]]:
    """Touching or overlapping half-open intervals joined, in order."""
    merged: list[list[int]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def formatting_sha256(
    formatting_spans: Sequence[FormattingSpan], font_size_spans: Sequence[FontSizeSpan]
) -> str:
    """SHA-256 of what a card's formatting looks like: which characters carry which emphasis, and sizes.

    Taken over the characters each emphasis covers, not over the spans as listed. The parser merges
    two touching spans only when the rule that found them is the same, so a stretch underlined with
    an alias of `StyleUnderline` and then with `StyleUnderline` itself is two spans; the writer
    re-maps the alias, and the built file has one. The text is underlined in both. So each emphasis
    (with its highlight colour) is reduced to the character ranges it covers, joined where they touch,
    and the sizes likewise per size. The rule ids and match sources are not part of it.
    """
    return text_sha256("")


class FileProvenanceEntry(DomainModel):
    """One card of a built file: which occurrence it was copied from, and what it was."""

    position: int = Field(ge=1, description="The card's place in the file, from 1, in file order.")
    recipe_path: NonEmptyText = Field(
        description="Where the card is in the recipe: `structure[0].hats[1].blocks[0].items[2]`."
    )
    section_path: tuple[NonEmptyText, ...] = Field(
        description="The pocket, hat and block headings above the card in the built file, outermost first."
    )
    fingerprint: Sha256Hex = Field(description="The card's E31 exact fingerprint, as the recipe names it.")
    fingerprint_version: NonEmptyText = Field(description="The fingerprint version of the occurrence row.")
    resolution: Literal["PINNED", "AUTO"] = Field(description="How the recipe chose the occurrence.")
    caselist: NonEmptyText = Field(description="Caselist slug, or `openev` for a camp file.")
    camp: NonEmptyText | None = Field(default=None, description="Camp for an OpenEv file; None otherwise.")
    snapshot: NonEmptyText = Field(description="The first snapshot listing the occurrence.")
    last_snapshot: NonEmptyText = Field(description="The latest snapshot listing the occurrence.")
    disclosure_digest: Sha256Hex | None = Field(
        default=None, description="Digest of `<caselist>/<path>` naming the disclosure; None for a camp file."
    )
    school: NonEmptyText | None = Field(
        default=None, repr=False, description="School, as disclosed; None with no disclosure on record."
    )
    team_code: NonEmptyText | None = Field(
        default=None,
        repr=False,
        description="Team code exactly as disclosed, never expanded to names; None with no disclosure.",
    )
    side: NonEmptyText | None = Field(default=None, description="Side as disclosed; None with no disclosure.")
    tournament: NonEmptyText | None = Field(
        default=None, repr=False, description="Tournament as disclosed; None when absent."
    )
    round: NonEmptyText | None = Field(
        default=None, repr=False, description="Round exactly as disclosed; None when absent."
    )
    source_sha256: Sha256Hex = Field(description="SHA-256 of the source file the card was copied from.")
    first_element_index: int = Field(ge=0, description="First paragraph of the card in its source.")
    last_element_index: int = Field(ge=0, description="Last paragraph of the card in its source.")
    completeness: CardCompleteness = Field(description="FULL, ABBREVIATED or CITE_ONLY, as parsed.")
    evidence_sha256: Sha256Hex = Field(description="SHA-256 of the source card's evidence text, UTF-8.")
    cite_sha256: Sha256Hex = Field(description="SHA-256 of the source card's full cite, UTF-8.")
    formatting_sha256: Sha256Hex = Field(
        description="SHA-256 of the source card's formatting (emphasis coverage and font sizes)."
    )
    tag_overridden: bool = Field(description="Whether the coach's tag replaced the card's own.")
    tag_authored_by: Literal[TagAuthor.COACH] | None = Field(
        default=None, description="COACH when the tag in the file is the coach's; None when it is the card's."
    )
    original_tag_sha256: Sha256Hex | None = Field(
        default=None,
        description="SHA-256 of the card's own tag when the coach replaced it; None otherwise or untagged.",
    )
    provenance_line: NonEmptyText = Field(
        repr=False, description="The line written below the cite (data-use policy, Attribution rule 2)."
    )
    forbidden_characters_replaced: int = Field(
        ge=0, description="Characters XML 1.0 forbids in the copied markup, each written as U+FFFD."
    )
    warnings: tuple[NonEmptyText, ...] = Field(
        default=(), description="What the writer could not carry over as it was: a style it does not know."
    )
    provenance_mode: Literal[ProvenanceMode.FILE_IMPORT] = Field(
        default=ProvenanceMode.FILE_IMPORT, description="Always FILE_IMPORT."
    )
    verification_status: Literal[VerificationStatus.UNVERIFIED] = Field(
        default=VerificationStatus.UNVERIFIED,
        description="Always UNVERIFIED: a disclosed card has not been verified by the platform.",
    )


class FileProvenanceManifest(DomainModel):
    """`<file>.provenance.json`: what a built file is, what built it, and one entry per card."""

    schema_version: Literal[1] = Field(default=1, description="The sidecar's shape: 1.")
    title: NonEmptyText = Field(description="The recipe's title.")
    topic: NonEmptyText = Field(description="The recipe's topic id.")
    format: NonEmptyText = Field(description="POLICY, LD or PF.")
    caselist: NonEmptyText = Field(description="The recipe's caselist.")
    position: NonEmptyText = Field(description="The recipe's position id.")
    side: NonEmptyText = Field(description="The side the file is for.")
    recipe_hash: Sha256Hex = Field(description="The recipe's canonical hash (v1-e33-t01).")
    builder_version: NonEmptyText = Field(description="Version of the writer that built the file.")
    parser_version: NonEmptyText = Field(description="Version of the parser that located the cards.")
    style_profile_version: NonEmptyText = Field(description="Version of the style profile it used.")
    fingerprint_version: NonEmptyText = Field(description="The recipe's fingerprint version.")
    built_at: AwareDatetime = Field(description="When the build was requested, from the build request; UTC.")
    docx_sha256: Sha256Hex = Field(description="SHA-256 of the built `.docx` this sidecar describes.")
    cards: tuple[FileProvenanceEntry, ...] = Field(description="One entry per card, in file order.")
    warnings: tuple[NonEmptyText, ...] = Field(default=(), description="Every card's warnings, prefixed.")
    provenance_mode: Literal[ProvenanceMode.FILE_IMPORT] = Field(
        default=ProvenanceMode.FILE_IMPORT, description="Always FILE_IMPORT: every card is disclosed."
    )

    @field_serializer("built_at")
    def _write_built_at(self, built_at: datetime) -> str:
        """Written in UTC with a `Z`, so the same instant always serializes the same."""
        return built_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def to_json_bytes(self) -> bytes:
        """The sidecar's bytes: two-space indented JSON, keys in model order, UTF-8, a final newline."""
        document = self.model_dump(mode="json")
        return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def render_file_provenance_schema() -> dict[str, Any]:
    """The sidecar's JSON Schema, for `docs/data/file-provenance.schema.json`."""
    return {"$schema": JSON_SCHEMA_DIALECT, **FileProvenanceManifest.model_json_schema(mode="serialization")}
