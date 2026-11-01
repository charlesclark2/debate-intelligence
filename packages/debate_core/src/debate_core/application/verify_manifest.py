"""Verifying a card manifest: every card in it, against the snapshots on this machine.

:class:`VerifyManifest` is what `debate-research verify <manifest.json>` runs
(`v1-e03-t06-verify-command`). It reads a :class:`~debate_core.evidence.manifest.CardManifest`,
hands each card to :meth:`EvidenceVerifier.verify
<debate_core.application.evidence_verifier.EvidenceVerifier.verify>`, and returns a
:class:`ManifestVerificationReport` with one :class:`CardVerdict` per card. Snapshots are resolved
the way the verifier always resolves them: the record through the article repository port, the
content through ``SnapshotService.load`` with every integrity check. Nothing here builds a
``LoadedSnapshot``, reaches the network or calls a model.

## Five outcomes

A run ends in exactly one of these, and the command maps each onto its own exit code:

* **Every card VERIFIED.** The report's :attr:`~ManifestVerificationReport.all_verified` is true.
* **Some card UNVERIFIED.** The report lists every card, verified or not, with its reasons. A card
  whose snapshot is not on this machine is UNVERIFIED with ``SNAPSHOT_MISSING``, never skipped.
* **The document is not a manifest** (:class:`InvalidManifest`): not JSON, or not valid against the
  published schema (``card_manifest.v1.json``, its cards checked against ``card.schema.json``), or
  written by a newer build (:class:`NewerManifestVersion`). Nothing is verified, and the error names
  the failing JSON path.
* **Verification could not run** (:class:`VerificationCouldNotRun`): a store could not be reached,
  or anything else the verifier lets propagate because it is not a verdict about the card
  (`v1-e03-t04`). It is never reported as a verdict, in either direction.
* **A .docx with no manifest** (:class:`NoManifest`): a document the platform did not export, such as
  a hand-cut team file. Nothing is verified; checking such files is V3's file intelligence, not this.

## Versions

Every version in :data:`~debate_core.evidence.manifest.READABLE_MANIFEST_VERSIONS` is read, and the
report says which one the document was. A version-2 manifest's ``snapshots`` are checked by the
schema and not otherwise used: each card is verified against the stored snapshot its own
``snapshot_id`` names, exactly as a version-1 card is.

A version above :data:`~debate_core.evidence.manifest.MANIFEST_VERSION` is refused before the schema
is consulted, as :class:`NewerManifestVersion`. Its fields are a newer build's, so the schema's
complaint about them (an unexpected key, a missing one) would describe the wrong problem; the
message says to install a newer build instead.

## Snapshot references (`v1-e06-t07`)

A version-2 manifest's ``snapshots`` say, for each snapshot its cards were cut from, its raw and
normalized hashes, its normalizer and extractor versions, when it was retrieved and from where. Each
card's reference is checked against the stored snapshot record: a field that differs, or a card whose
snapshot the manifest does not reference validly, is ``SNAPSHOT_REFERENCE_MISMATCH`` on that card,
for a JSON manifest and an embedded one alike (the PM's amendment of 2026-10-26). A record that is
not stored is left to the verifier, which reports ``SNAPSHOT_MISSING``. A version-1 manifest has no
references, so nothing is compared.

## A .docx (`v1-e06-t07`)

A document whose bytes begin as a zip package does is read as a .docx the platform exported: its
embedded manifest (:func:`~debate_core.evidence.docx_manifest_part.embedded_manifest_bytes`) is read
and verified exactly as a JSON manifest is, and then its body
(:func:`~debate_core.evidence.docx_reader.read_document_body`) is compared with each card under the
edit policy (:mod:`debate_core.evidence.docx_verify`). A card whose body changes its quoted words is
``MANUAL_EDIT``, and one the body does not hold at all ``BODY_CARD_MISSING``; a bracketed
interpolation is a warning (``INTERPOLATION_PRESENT``) on a card that stays VERIFIED. The body is read
in the format profile the cards name; a manifest whose cards name more than one profile, or one this
build does not have, describes no document this build can read, and is an :class:`InvalidManifest`.
So is a document whose manifest is damaged or whose body cannot be read. A body card no manifest card
claims (a card pasted in by hand) has no verdict: the report lists its position, and it changes no
card's status.

## A card that passes the schema but is not a Card

JSON Schema describes each field; it cannot relate one field to another. ADR-0018's length invariant
(the envelope minus the omissions is exactly as long as ``evidence_text``) is the plainest example,
so a card can pass the schema and still be refused by ``Card``'s own validation. Such a card gets a
verdict of its own, UNVERIFIED with ``CARD_INVALID``, and the rest of the manifest is verified as
usual. One tampered card must not hide the verdict on the others, which refusing the whole document
would do.

## Nothing here quotes evidence

Every message this module writes, in a reason detail or in an :class:`InvalidManifest`, is built
from field names, JSON paths, offsets, counts and values from the schema. None repeats a value read
from the manifest, which could be evidence text. That is why schema violations are described here
rather than with the validator's own message, which quotes the offending value, and why a card's
validation errors are reported by their location and message and never with their input.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from typing import Any, Final, Self, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as SchemaViolation
from jsonschema.exceptions import best_match  # pyright: ignore[reportUnknownVariableType]
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    computed_field,
    model_validator,
)
from referencing import Registry, Resource

from debate_core.application.errors import DomainError, NotFound
from debate_core.application.evidence_verifier import EvidenceVerifier
from debate_core.application.ports.persistence import ArticleRepository
from debate_core.domain import Card, VerificationStatus, render_schemas
from debate_core.domain.card import DEFAULT_FORMAT_PROFILE
from debate_core.domain.schema_export import JSON_SCHEMA_DIALECT
from debate_core.evidence.docx_manifest_part import (
    EmbeddedManifestError,
    NoEmbeddedManifest,
    embedded_manifest_bytes,
)
from debate_core.evidence.docx_reader import UnreadableDocument, read_document_body
from debate_core.evidence.docx_verify import (
    BodyCard,
    BodyComparison,
    CharacterRange,
    body_evidence,
    compare_body,
    match_body_cards,
)
from debate_core.evidence.format_profile import ResolvedFormatProfile
from debate_core.evidence.manifest import (
    CARD_SCHEMA_REFERENCE,
    MANIFEST_VERSION,
    READABLE_MANIFEST_VERSIONS,
    SNAPSHOTS_SINCE_VERSION,
    ManifestVersion,
    SnapshotReference,
    render_card_manifest_schema,
)
from debate_core.evidence.verification_types import (
    ReasonCode,
    VerificationCheck,
    VerificationReason,
    VerificationResult,
    WarningCode,
)

__all__ = [
    "INVALID_MANIFEST_CODE",
    "NO_MANIFEST_CODE",
    "UNVERIFIED_CODE",
    "VERIFICATION_COULD_NOT_RUN_CODE",
    "VERIFY_RESULT_SCHEMA_FILENAME",
    "CardVerdict",
    "DocumentCheck",
    "InvalidManifest",
    "ManifestDocument",
    "ManifestVerificationReport",
    "NewerManifestVersion",
    "NoManifest",
    "ReportedRange",
    "ReportedReason",
    "ReportedWarning",
    "VerificationCouldNotRun",
    "VerifyManifest",
    "read_manifest",
    "render_verify_result_schema",
]

VERIFY_RESULT_SCHEMA_FILENAME: Final = "verify_result.v1.json"
"""The committed schema of `debate-research --json verify`'s output, in ``packages/debate_core/schemas/``."""

UNVERIFIED_CODE: Final = "UNVERIFIED"
"""The `--json` error code when the manifest was read and some card is UNVERIFIED."""

INVALID_MANIFEST_CODE: Final = "INVALID_MANIFEST"
"""The `--json` error code when the document is not a manifest (:class:`InvalidManifest`)."""

VERIFICATION_COULD_NOT_RUN_CODE: Final = "VERIFICATION_COULD_NOT_RUN"
"""The `--json` error code when verification stopped before every card had a verdict."""

NO_MANIFEST_CODE: Final = "NO_MANIFEST"
"""The `--json` error code when a .docx holds no embedded manifest (:class:`NoManifest`)."""

_ZIP_SIGNATURE: Final = b"PK\x03\x04"
"""How every .docx begins: a zip package's first local file header. No JSON document begins so."""


# --------------------------------------------------------------------------------------------
# Outcomes that are not a report
# --------------------------------------------------------------------------------------------


class InvalidManifest(Exception):
    """The document is not a card manifest this code can read, so nothing in it was verified.

    Deliberately not a :class:`~debate_core.application.errors.DomainError`. The CLI reports a
    ``DomainError`` it does not handle with exit 1, which `verify` reserves for an UNVERIFIED card;
    a command that forgot to handle this should fail as a bug, not claim a verdict.
    """

    def __init__(self, json_path: str, problem: str, *, violations: int = 1) -> None:
        self.json_path = json_path
        """Where the document fails, e.g. ``$.cards[2].evidence_start_offset``; ``$`` for the whole."""
        self.problem = problem
        """What is wrong there, in words that never repeat a value from the document."""
        self.violations = violations
        """How many schema violations the document has; :attr:`json_path` is the most relevant."""
        more = f" ({violations - 1} more violation(s))" if violations > 1 else ""
        super().__init__(f"the manifest is invalid at {json_path}: {problem}{more}")


class NewerManifestVersion(InvalidManifest):
    """The manifest says it was written by a build newer than this one, which cannot read it.

    An :class:`InvalidManifest`, so the CLI reports it the same way (exit 2, nothing verified), with
    a problem that says what to do about it.
    """

    def __init__(self, manifest_version: int) -> None:
        self.manifest_version = manifest_version
        """The version the document claims."""
        readable = ", ".join(str(version) for version in READABLE_MANIFEST_VERSIONS)
        super().__init__(
            "$.manifest_version",
            f"manifest_version {manifest_version} is newer than this build reads ({readable}); "
            "install a newer build of debate-research to verify it",
        )


class VerificationCouldNotRun(Exception):
    """Verification stopped before every card had a verdict, for a reason that is not one.

    Raised when the verifier lets a ``DomainError`` propagate: a store that could not be reached
    (``StoreError``), a record that could not be read. Those say nothing about the card, so they
    are neither VERIFIED nor UNVERIFIED (`v1-e03-t04`). Not a ``DomainError`` itself, for the same
    reason as :class:`InvalidManifest`.
    """

    def __init__(self, *, card_id: str, position: int, cause: DomainError) -> None:
        self.card_id = card_id
        """The card being verified when the run stopped."""
        self.position = position
        """Its index in the manifest's ``cards``."""
        self.cause = cause
        """The failure the verifier let through."""
        self.hint: str | None = getattr(cause, "hint", None)
        """What to do about it, when the cause knows (``aws sso login --profile …``)."""
        super().__init__(
            f"verification could not run: cards[{position}] ({card_id}) could not be checked "
            f"against its snapshot: {cause}"
        )


class NoManifest(Exception):
    """The .docx holds no embedded manifest, so there is nothing to verify it against.

    A document the platform did not export: a hand-cut team file, or an export whose custom XML part
    was lost. Not an :class:`InvalidManifest` (there is no manifest to be invalid) and not a
    ``DomainError``, for the same reason as :class:`InvalidManifest`: a command that forgot to handle
    it must not report it as a verdict.
    """

    def __init__(self) -> None:
        super().__init__(
            "the document holds no embedded manifest; verify reads only .docx files debate-research exported"
        )


# --------------------------------------------------------------------------------------------
# The report
# --------------------------------------------------------------------------------------------


class ReportedRange(BaseModel):
    """``[start, end)`` in characters; empty where something was only added."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @classmethod
    def of(cls, character_range: CharacterRange) -> ReportedRange:
        return cls(start=character_range.start, end=character_range.end)


class ReportedReason(BaseModel):
    """One reason a card is UNVERIFIED, as the report carries it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: ReasonCode
    detail: str = Field(
        description="For people. Gives offsets, lengths and record values; never evidence text."
    )
    first_differing_offset: int | None = Field(
        default=None,
        description="For TEXT_MISMATCH only: the first index where the texts differ, in evidence_text.",
    )
    evidence_range: ReportedRange | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description="For MANUAL_EDIT only: the evidence_text range the body changed. Absent otherwise.",
    )
    body_range: ReportedRange | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description=(
            "For MANUAL_EDIT only: the range of the body's evidence (its paragraphs joined with a line "
            "feed) that replaced it. Absent otherwise."
        ),
    )

    @classmethod
    def of(cls, reason: VerificationReason) -> ReportedReason:
        return cls(
            code=reason.code, detail=reason.detail, first_differing_offset=reason.first_differing_offset
        )


class ReportedWarning(BaseModel):
    """Something about a card a reader should know that leaves it VERIFIED (`v1-e06-t07`)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: WarningCode
    detail: str = Field(description="For people. Gives offsets and lengths; never evidence or inserted text.")
    evidence_offset: int | None = Field(
        default=None, description="For INTERPOLATION_PRESENT: the evidence_text offset it is read before."
    )


class CardVerdict(BaseModel):
    """The verdict on one card of the manifest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    position: int = Field(ge=0, description="The card's index in the manifest's cards.")
    card_id: str
    tag: str
    status: VerificationStatus
    reasons: tuple[ReportedReason, ...] = Field(description="Every reason found, in check order.")
    snapshot_id: str | None = Field(description="The snapshot the card names, if it names one.")
    checks_run: tuple[VerificationCheck, ...] = Field(
        description="The verifier's checks that ran. Empty for a card that was never a valid Card."
    )
    verifier_version: str | None = Field(
        description="The verifier's rules version; null when the card never reached the verifier."
    )
    warnings: tuple[ReportedWarning, ...] = Field(
        default=(),
        exclude_if=lambda warnings: not warnings,
        description="What a reader should know that changes no status, in body order. Absent when none.",
    )

    @model_validator(mode="after")
    def _status_agrees_with_reasons(self) -> Self:
        """VERIFIED with no reason, anything else with at least one, as a VerificationResult must be.

        A reason found beside the verifier's (a snapshot reference, the document body) must not be
        carried by a card still marked VERIFIED, by this code or any later caller.
        """
        if (self.status is VerificationStatus.VERIFIED) == bool(self.reasons):
            raise ValueError("a card verdict is VERIFIED exactly when it carries no reason")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def reason_codes(self) -> tuple[ReasonCode, ...]:
        """The codes of :attr:`reasons`, in order, without repeats."""
        return tuple(dict.fromkeys(reason.code for reason in self.reasons))

    @classmethod
    def of_result(
        cls,
        position: int,
        card: Card,
        result: VerificationResult,
        *,
        more_reasons: Sequence[ReportedReason] = (),
        warnings: Sequence[ReportedWarning] = (),
    ) -> CardVerdict:
        """The verdict the verifier reached on ``card``, with ``more_reasons`` found beside it.

        VERIFIED only when the verifier says so and nothing else was found: a reason from the snapshot
        reference or the document body makes the card UNVERIFIED whatever the verifier said.
        """
        reasons = (*(ReportedReason.of(reason) for reason in result.reasons), *more_reasons)
        return cls(
            position=position,
            card_id=card.card_id,
            tag=card.tag,
            status=VerificationStatus.UNVERIFIED if reasons else result.status,
            reasons=reasons,
            snapshot_id=result.snapshot_id,
            checks_run=tuple(check for check in VerificationCheck if check in result.checks_run),
            verifier_version=result.verifier_version,
            warnings=tuple(warnings),
        )

    @classmethod
    def of_invalid_card(
        cls, position: int, entry: Mapping[str, Any], invalid: ValidationError
    ) -> CardVerdict:
        """The verdict on an entry that passed the schema and is not a valid ``Card``."""
        snapshot_id = entry.get("snapshot_id")
        return cls(
            position=position,
            card_id=str(entry["card_id"]),
            tag=str(entry["tag"]),
            status=VerificationStatus.UNVERIFIED,
            reasons=tuple(
                ReportedReason(
                    code=ReasonCode.CARD_INVALID,
                    detail=(
                        f"not a valid card at {_json_path(('cards', position, *error['loc']))}: "
                        f"{error['msg']}; it was not checked against its snapshot"
                    ),
                )
                for error in invalid.errors(include_url=False, include_input=False, include_context=False)
            ),
            snapshot_id=snapshot_id if isinstance(snapshot_id, str) else None,
            checks_run=(),
            verifier_version=None,
        )


class DocumentCheck(BaseModel):
    """What was read of a .docx's body beside its manifest (`v1-e06-t07`)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    format_profile: str = Field(
        description="The format profile the body was read in: the one its cards name."
    )
    body_cards: int = Field(ge=0, description="How many cards (tag paragraphs) the body holds.")
    unclaimed_body_cards: tuple[int, ...] = Field(
        description=(
            "The positions, among the body's cards from 0, of those no manifest card claims, such as a "
            "card pasted in by hand. They have no verdict and change no card's status."
        )
    )


class ManifestVerificationReport(BaseModel):
    """Every card of one manifest, with its verdict, in manifest order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest_version: ManifestVersion = Field(description="The manifest's own manifest_version.")
    generated_at: AwareDatetime = Field(description="The manifest's own generated_at.")
    cards: tuple[CardVerdict, ...]
    document: DocumentCheck | None = Field(
        default=None,
        exclude_if=lambda document: document is None,
        description="For a .docx: what was read of its body. Absent for a JSON manifest.",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total(self) -> int:
        """How many cards the manifest lists."""
        return len(self.cards)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def verified(self) -> int:
        """How many of them are VERIFIED."""
        return sum(1 for verdict in self.cards if verdict.status is VerificationStatus.VERIFIED)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def unverified(self) -> int:
        """How many of them are not."""
        return self.total - self.verified

    @property
    def all_verified(self) -> bool:
        """True when every card is VERIFIED. A manifest lists at least one card, so this is never vacuous."""
        return self.verified == self.total


# --------------------------------------------------------------------------------------------
# The use case
# --------------------------------------------------------------------------------------------


class VerifyManifest:
    """Verifies every card of a manifest, or of a .docx's manifest and body, against the snapshots."""

    def __init__(
        self,
        *,
        verifier: EvidenceVerifier,
        articles: ArticleRepository,
        format_profiles: Callable[[], Mapping[str, ResolvedFormatProfile]] = dict,
    ) -> None:
        self._verifier = verifier
        self._articles = articles
        # Called only for a .docx, so a JSON manifest verifies on a build whose profiles do not load.
        self._format_profiles = format_profiles

    async def verify(self, document: bytes) -> ManifestVerificationReport:
        """Read ``document`` as a card manifest, or as a .docx holding one, and verify each card in order.

        Raises :class:`InvalidManifest` before verifying anything if the document is not a manifest (or
        a .docx whose manifest or body cannot be read), :class:`NoManifest` for a .docx with no
        manifest, and :class:`VerificationCouldNotRun` if the verifier lets a failure through.
        """
        if document.startswith(_ZIP_SIGNATURE):
            return await self._verify_docx(document)
        manifest = read_manifest(document)
        verdicts = [
            await self._verdict(position, entry, manifest.references)
            for position, entry in enumerate(manifest.cards)
        ]
        return ManifestVerificationReport(
            manifest_version=manifest.manifest_version,
            generated_at=manifest.generated_at,
            cards=tuple(verdicts),
        )

    async def _verify_docx(self, document: bytes) -> ManifestVerificationReport:
        try:
            manifest = read_manifest(embedded_manifest_bytes(document))
        except NoEmbeddedManifest as missing:
            raise NoManifest() from missing
        except EmbeddedManifestError as unreadable:
            raise InvalidManifest(
                "$", f"the document's embedded manifest cannot be read: {unreadable}"
            ) from None
        name, profile = self._profile_of(manifest.cards)
        try:
            body = read_document_body(document, profile.style_profile)
        except UnreadableDocument as unreadable:
            raise InvalidManifest("$", f"the document's body cannot be read: {unreadable}") from None
        matched, unclaimed = match_body_cards([str(entry.get("tag", "")) for entry in manifest.cards], body)
        verdicts = [
            await self._verdict(
                position,
                entry,
                manifest.references,
                _BodyCheck(matched[position], profile.profile.omission_marker),
            )
            for position, entry in enumerate(manifest.cards)
        ]
        return ManifestVerificationReport(
            manifest_version=manifest.manifest_version,
            generated_at=manifest.generated_at,
            cards=tuple(verdicts),
            document=DocumentCheck(
                format_profile=name,
                body_cards=len(body.cards),
                unclaimed_body_cards=tuple(card.position for card in unclaimed),
            ),
        )

    def _profile_of(self, entries: Sequence[Mapping[str, Any]]) -> tuple[str, ResolvedFormatProfile]:
        """The one format profile the cards name, which the body was rendered in, or InvalidManifest."""
        names = [entry.get("format_profile", DEFAULT_FORMAT_PROFILE) for entry in entries]
        first = names[0]
        for position, name in enumerate(names):
            if name != first:
                raise InvalidManifest(
                    f"$.cards[{position}].format_profile",
                    f"names format profile {_quoted(str(name))} where cards[0] names {_quoted(str(first))}; "
                    "a rendered document is written in one profile",
                )
        profiles = self._format_profiles()
        profile = profiles.get(str(first))
        if profile is None:
            known = ", ".join(sorted(profiles)) or "none"
            raise InvalidManifest(
                "$.cards[0].format_profile",
                f"names format profile {_quoted(str(first))}, which this build does not have ({known}), so "
                "its body cannot be read",
            )
        return str(first), profile

    async def _verdict(
        self,
        position: int,
        entry: Mapping[str, Any],
        references: Mapping[str, SnapshotReference | None] | None,
        body: _BodyCheck | None = None,
    ) -> CardVerdict:
        try:
            # JSON in, as a stored card is read back, so a card loads here exactly as it would there.
            card = Card.model_validate_json(json.dumps(entry))
        except ValidationError as invalid:
            return CardVerdict.of_invalid_card(position, entry, invalid)
        try:
            result = await self._verifier.verify(card)
            reasons = await self._reference_reasons(card, references)
        except DomainError as stopped:
            raise VerificationCouldNotRun(card_id=card.card_id, position=position, cause=stopped) from stopped
        warnings: list[ReportedWarning] = []
        if body is not None:
            body_reasons, warnings = body.check(position, card)
            reasons = (*reasons, *body_reasons)
        return CardVerdict.of_result(position, card, result, more_reasons=reasons, warnings=warnings)

    async def _reference_reasons(
        self, card: Card, references: Mapping[str, SnapshotReference | None] | None
    ) -> tuple[ReportedReason, ...]:
        """``SNAPSHOT_REFERENCE_MISMATCH`` when the manifest's reference is not the stored record."""
        if references is None or card.snapshot_id is None:
            return ()
        snapshot_id = card.snapshot_id
        if snapshot_id not in references:
            return (_reference_mismatch(f"the manifest lists no reference to snapshot {snapshot_id}"),)
        try:
            record = await self._articles.get_snapshot(snapshot_id)
        except NotFound:
            return ()  # The verifier has reported SNAPSHOT_MISSING: there is no record to compare with.
        reference = references[snapshot_id]
        if reference is None:
            return (
                _reference_mismatch(
                    f"the manifest's reference to snapshot {snapshot_id} is not one valid snapshot reference"
                ),
            )
        stored = SnapshotReference.of(record)
        differing = [
            name
            for name in SnapshotReference.model_fields
            if getattr(reference, name) != getattr(stored, name)
        ]
        if not differing:
            return ()
        return (
            _reference_mismatch(
                f"the manifest's reference to snapshot {snapshot_id} differs from the stored snapshot record "
                f"in {', '.join(differing)}"
            ),
        )


def _reference_mismatch(detail: str) -> ReportedReason:
    return ReportedReason(code=ReasonCode.SNAPSHOT_REFERENCE_MISMATCH, detail=detail)


@dataclass(frozen=True, slots=True)
class _BodyCheck:
    """One manifest card's body card in a .docx, if it has one, and the marker its cuts are drawn with."""

    body_card: BodyCard | None
    omission_marker: str

    def check(self, position: int, card: Card) -> tuple[tuple[ReportedReason, ...], list[ReportedWarning]]:
        if self.body_card is None:
            return (
                ReportedReason(
                    code=ReasonCode.BODY_CARD_MISSING,
                    detail=f"the document body holds no card for cards[{position}]: no tag matches it",
                ),
            ), []
        comparison = compare_body(card, body_evidence(card, self.body_card), self.omission_marker)
        return _manual_edits(comparison), _interpolation_warnings(comparison)


def _manual_edits(comparison: BodyComparison) -> tuple[ReportedReason, ...]:
    return tuple(
        ReportedReason(
            code=ReasonCode.MANUAL_EDIT,
            detail=(
                f"the document body changes evidence_text [{edit.evidence_range.start}, "
                f"{edit.evidence_range.end}) (body evidence [{edit.body_range.start}, "
                f"{edit.body_range.end})); "
                "only deletions of whole words, markup changes and bracketed interpolations leave the "
                "quotation intact"
            ),
            evidence_range=ReportedRange.of(edit.evidence_range),
            body_range=ReportedRange.of(edit.body_range),
        )
        for edit in comparison.manual_edits
    )


def _interpolation_warnings(comparison: BodyComparison) -> list[ReportedWarning]:
    return [
        ReportedWarning(
            code=WarningCode.INTERPOLATION_PRESENT,
            detail=(
                f"a bracketed interpolation of {item.length} character(s) is read before evidence_text "
                f"offset {item.anchor}; its words are the debater's, not the source's"
                + ("" if item.recorded else ", and the card does not record it")
            ),
            evidence_offset=item.anchor,
        )
        for item in comparison.interpolations
    ]


# --------------------------------------------------------------------------------------------
# Reading the document
# --------------------------------------------------------------------------------------------

_GENERATED_AT: Final[TypeAdapter[datetime]] = TypeAdapter(AwareDatetime)


@dataclass(frozen=True, slots=True)
class ManifestDocument:
    """A document known to be a manifest: its version, timestamp, card entries and snapshot references."""

    manifest_version: ManifestVersion
    generated_at: datetime
    cards: list[dict[str, Any]]
    """Plain entries: each is made a ``Card`` on its own, so one invalid card cannot refuse the others."""
    references: Mapping[str, SnapshotReference | None] | None
    """By snapshot id; None for a version-1 manifest, which has none. An entry that is not one valid
    reference (the model refuses it, or the id is listed twice) is None, so its cards are refused too."""


def read_manifest(document: bytes) -> ManifestDocument:
    """``document``'s version, timestamp, card entries and references, once it is known to be a manifest.

    Strict JSON (no duplicate keys, no ``NaN``), then a version newer than this build's refused
    (:class:`NewerManifestVersion`), then the published schema, then the timestamp, whose
    ``date-time`` format JSON Schema only annotates. The cards come back as plain entries: each is
    made a ``Card`` on its own, so one invalid card cannot refuse the others.
    """
    try:
        data: Any = json.loads(
            document, object_pairs_hook=_refuse_duplicate_keys, parse_constant=_refuse_constant
        )
    except _NotStrictJson as loose:
        raise InvalidManifest("$", str(loose)) from loose
    except json.JSONDecodeError as malformed:
        raise InvalidManifest(
            "$", f"not JSON: {malformed.msg} at line {malformed.lineno} column {malformed.colno}"
        ) from malformed
    except ValueError as undecodable:  # bytes that are not UTF-8 (or UTF-16/32) text at all
        raise InvalidManifest("$", "not JSON: the document is not Unicode text") from undecodable

    newer = _newer_version(data)
    if newer is not None:
        raise NewerManifestVersion(newer)

    worst, violations = _schema_violations(data)
    if worst is not None:
        raise InvalidManifest(worst.json_path, worst.description(), violations=violations)

    try:
        generated_at = _GENERATED_AT.validate_python(data["generated_at"])
    except ValidationError as invalid:
        raise InvalidManifest("$.generated_at", invalid.errors(include_url=False)[0]["msg"]) from invalid
    manifest_version = cast("ManifestVersion", data["manifest_version"])
    references = (
        _references(data.get("snapshots", [])) if manifest_version >= SNAPSHOTS_SINCE_VERSION else None
    )
    return ManifestDocument(manifest_version, generated_at, data["cards"], references)


def _references(entries: list[Any]) -> dict[str, SnapshotReference | None]:
    references: dict[str, SnapshotReference | None] = {}
    for entry in entries:
        snapshot_id = str(entry["snapshot_id"])
        try:
            reference: SnapshotReference | None = SnapshotReference.model_validate(entry)
        except ValidationError:
            reference = None
        references[snapshot_id] = None if snapshot_id in references else reference
    return references


@cache
def _manifest_validator() -> Draft202012Validator:
    """The manifest schema, with ``card.schema.json`` resolved from memory. Nothing is ever fetched."""
    card_schema: Resource[Any] = Resource.from_contents(render_schemas()[CARD_SCHEMA_REFERENCE])
    registry: Registry[Any] = Registry().with_resource(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType, reportUnknownArgumentType]
        CARD_SCHEMA_REFERENCE, card_schema
    )
    return Draft202012Validator(render_card_manifest_schema(), registry=registry)


@dataclass(frozen=True, slots=True)
class _SchemaViolation:
    """One schema violation, holding only what this module reads from jsonschema's error."""

    json_path: str
    rule: str
    """The schema keyword that failed: ``type``, ``required``, ``minimum``…"""
    expected: object
    """The schema's value for that keyword. Comes from the schema, never from the document."""
    keys: frozenset[str] | None
    """The failing value's own keys, when it is an object: the one thing read from the document."""
    allowed_keys: frozenset[str]
    """The properties the failing schema declares."""

    def description(self) -> str:
        """What is wrong at :attr:`json_path`, from the schema's side only.

        jsonschema's own message would quote the failing value, which may be evidence text. Property
        names are the one thing taken from the document, because naming a missing or unexpected key
        is the whole point of the message.
        """
        expected = self.expected
        if self.rule == "required" and self.keys is not None and isinstance(expected, list):
            names = cast("list[str]", expected)
            return "missing required " + _names([name for name in names if name not in self.keys])
        if self.rule == "additionalProperties" and self.keys is not None:
            return "properties the schema does not allow: " + _names(sorted(self.keys - self.allowed_keys))
        if self.rule == "not" and self.keys is not None:
            # The one negation in the manifest schema: a key that an older version does not have.
            keys = self.keys
            return "properties this manifest_version does not allow: " + _names(
                [name for name in _required_names(expected) if name in keys]
            )
        descriptions: Mapping[str, str] = {
            "type": f"must be of type {_alternatives(expected)}",
            "const": f"must be {json.dumps(expected)}",
            "enum": f"must be one of {_alternatives(expected)}",
            "minimum": f"must be at least {expected}",
            "exclusiveMinimum": f"must be greater than {expected}",
            "maximum": f"must be at most {expected}",
            "minLength": f"must be at least {expected} character(s) long",
            "maxLength": f"must be at most {expected} character(s) long",
            "pattern": f"must match the pattern {expected}",
            "minItems": f"must have at least {expected} item(s)",
            "anyOf": "matches none of the allowed forms: " + _forms(expected),
            "oneOf": "must match exactly one of the allowed forms: " + _forms(expected),
        }
        return descriptions.get(self.rule, f"fails the schema's {self.rule!r} rule")


def _newer_version(data: Any) -> int | None:
    """The version ``data`` claims, when it is an integer above the one this build writes."""
    if not isinstance(data, Mapping):
        return None
    version = cast("Mapping[str, object]", data).get("manifest_version")
    if isinstance(version, int) and not isinstance(version, bool) and version > MANIFEST_VERSION:
        return version
    return None


def _required_names(subschema: object) -> list[str]:
    """The names a ``{"required": [...]}`` subschema lists; none for any other subschema."""
    if not isinstance(subschema, Mapping):
        return []
    names = cast("Mapping[str, object]", subschema).get("required")
    return [str(name) for name in cast("list[object]", names)] if isinstance(names, list) else []


def _schema_violations(data: Any) -> tuple[_SchemaViolation | None, int]:
    """The most relevant way ``data`` fails the manifest schema (jsonschema's ranking), and how many.

    The most relevant may be a sub-error of one of the violations, such as the alternative of an
    ``anyOf`` that came closest, so it is reported alongside the count rather than counted itself.
    """
    found = cast("list[SchemaViolation]", list(_manifest_validator().iter_errors(data)))  # pyright: ignore[reportUnknownMemberType]
    if not found:
        return None, 0
    return _typed(cast("SchemaViolation", best_match(found))), len(found)  # pyright: ignore[reportUnknownVariableType]


def _typed(violation: SchemaViolation) -> _SchemaViolation:
    instance: object = violation.instance
    schema: object = violation.schema
    properties: object = schema.get("properties", {}) if isinstance(schema, Mapping) else {}
    return _SchemaViolation(
        json_path=str(violation.json_path),
        rule=str(violation.validator),
        expected=cast("object", violation.validator_value),
        keys=frozenset(str(key) for key in cast("Mapping[object, object]", instance))
        if isinstance(instance, Mapping)
        else None,
        allowed_keys=frozenset(str(key) for key in cast("Mapping[object, object]", properties))
        if isinstance(properties, Mapping)
        else frozenset(),
    )


class _NotStrictJson(ValueError):
    pass


def _refuse_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Refuse an object that names a key twice: a reader of the file could see the other value."""
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise _NotStrictJson(f"not strict JSON: an object names the key {_quoted(key)} twice")
        seen[key] = value
    return seen


def _refuse_constant(name: str) -> Any:
    raise _NotStrictJson(f"not strict JSON: {name} is not a JSON number")


def _forms(subschemas: object) -> str:
    if not isinstance(subschemas, list):
        return "a subschema"
    forms: list[str] = []
    for subschema in cast("list[object]", subschemas):
        described: Mapping[str, object] = (
            cast("Mapping[str, object]", subschema) if isinstance(subschema, Mapping) else {}
        )
        forms.append(str(described.get("type") or described.get("$ref") or "a subschema"))
    return ", or ".join(forms)


def _alternatives(expected: object) -> str:
    if isinstance(expected, str):
        return expected
    if isinstance(expected, list):
        return ", ".join(json.dumps(item) for item in cast("list[object]", expected))
    return json.dumps(expected)


def _names(names: Sequence[str]) -> str:
    return ", ".join(_quoted(name) for name in names)


def _quoted(key: str, limit: int = 60) -> str:
    """A key from the document, shortened so a hostile manifest cannot use one as a carrier."""
    return repr(key if len(key) <= limit else key[:limit] + "…")


def _json_path(location: Iterable[str | int]) -> str:
    """``("cards", 2, "spans", 0)`` → ``$.cards[2].spans[0]``, the form jsonschema reports."""
    path = "$"
    for part in location:
        path += f"[{part}]" if isinstance(part, int) else f".{part}"
    return path


# --------------------------------------------------------------------------------------------
# The published result schema
# --------------------------------------------------------------------------------------------


def render_verify_result_schema() -> dict[str, Any]:
    """The JSON Schema of `debate-research --json verify`'s output, for every outcome but a bug.

    The output is the CLI's standard envelope (``debate_cli.output``, ``schema_version`` 1) with
    this command's payloads in it: the report under ``data`` when every card is VERIFIED; the same
    report under ``error.details`` when some card is not; the failing path when the document is not
    a manifest; the document's name when a .docx holds no manifest; and the card the run stopped at
    when verification could not run. The exit codes
    are written as numbers because ``debate_core`` cannot import the CLI's ``ExitCode``; the CLI's
    tests hold the two to each other. A bug (exit 70) has the CLI-wide envelope and is not
    described here.
    """
    report = ManifestVerificationReport.model_json_schema(mode="serialization")
    definitions: dict[str, Any] = report.pop("$defs")
    definitions["ManifestVerificationReport"] = report
    report_ref = {"$ref": "#/$defs/ManifestVerificationReport"}

    def failure(code: Any, exit_code: int, details: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["code", "message", "exit_code", "details", "hint"],
            "properties": {
                "code": code,
                "message": {"type": "string"},
                "exit_code": {"const": exit_code},
                "details": details,
                "hint": {"type": ["string", "null"]},
            },
        }

    def outcome(title: str, status: str, data: Mapping[str, Any], error: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "title": title,
            "properties": {"status": {"const": status}, "data": data, "error": error},
        }

    invalid_manifest_details = {
        "type": "object",
        "required": ["json_path", "problem", "violations", "manifest"],
        "properties": {
            "json_path": {"type": "string", "pattern": r"^\$"},
            "problem": {"type": "string"},
            "violations": {"type": "integer", "minimum": 1},
            "manifest": {"type": "string"},
        },
    }
    no_manifest_details = {
        "type": "object",
        "required": ["document"],
        "properties": {"document": {"type": "string"}},
    }
    could_not_run_details = {
        "type": "object",
        "required": ["card_id", "position", "cause"],
        "properties": {
            "card_id": {"type": "string"},
            "position": {"type": "integer", "minimum": 0},
            "cause": {"type": "string"},
        },
    }
    return {
        "$schema": JSON_SCHEMA_DIALECT,
        "title": "debate-research verify --json output",
        "description": (
            "One JSON object on stdout per run. Exit 0: every card VERIFIED, report under data. "
            "Exit 1: some card UNVERIFIED, report under error.details. Exit 2: usage error, a "
            "manifest that fails its schema, with the failing JSON path, or a .docx with no embedded "
            "manifest (NO_MANIFEST). Exit 3: verification could not run."
        ),
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "status", "command", "data", "error"],
        "properties": {
            "schema_version": {"const": 1},
            "status": {"enum": ["ok", "error"]},
            "command": {"type": ["string", "null"]},
            "data": True,
            "error": True,
        },
        "oneOf": [
            outcome("Every card VERIFIED (exit 0)", "ok", report_ref, {"type": "null"}),
            outcome(
                "Some card UNVERIFIED (exit 1)",
                "error",
                {"type": "null"},
                failure({"const": UNVERIFIED_CODE}, 1, report_ref),
            ),
            outcome(
                "Not a manifest (exit 2)",
                "error",
                {"type": "null"},
                failure({"const": INVALID_MANIFEST_CODE}, 2, invalid_manifest_details),
            ),
            outcome(
                "No manifest in the .docx (exit 2)",
                "error",
                {"type": "null"},
                failure({"const": NO_MANIFEST_CODE}, 2, no_manifest_details),
            ),
            outcome(
                "Usage error (exit 2)",
                "error",
                {"type": "null"},
                failure({"const": "USAGE_ERROR"}, 2, {"type": "object"}),
            ),
            outcome(
                "Verification could not run (exit 3)",
                "error",
                {"type": "null"},
                failure({"const": VERIFICATION_COULD_NOT_RUN_CODE}, 3, could_not_run_details),
            ),
        ],
        "$defs": definitions,
    }
