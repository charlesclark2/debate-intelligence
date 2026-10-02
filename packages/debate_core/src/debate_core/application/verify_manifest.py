"""Verifying a card manifest: every card in it, against the snapshots on this machine.

:class:`VerifyManifest` is what `debate-research verify <manifest.json>` runs
(`v1-e03-t06-verify-command`). It reads a :class:`~debate_core.evidence.manifest.CardManifest`,
hands each card to :meth:`EvidenceVerifier.verify
<debate_core.application.evidence_verifier.EvidenceVerifier.verify>`, and returns a
:class:`ManifestVerificationReport` with one :class:`CardVerdict` per card. Snapshots are resolved
the way the verifier always resolves them: the record through the article repository port, the
content through ``SnapshotService.load`` with every integrity check. Nothing here builds a
``LoadedSnapshot``, reaches the network or calls a model.

## Four outcomes

A run ends in exactly one of these, and the command maps each onto its own exit code:

* **Every card VERIFIED.** The report's :attr:`~ManifestVerificationReport.all_verified` is true.
* **Some card UNVERIFIED.** The report lists every card, verified or not, with its reasons. A card
  whose snapshot is not on this machine is UNVERIFIED with ``SNAPSHOT_MISSING``, never skipped.
* **The document is not a manifest** (:class:`InvalidManifest`): not JSON, or not valid against the
  published schema (``card_manifest.v1.json``, its cards checked against ``card.schema.json``).
  Nothing is verified, and the error names the failing JSON path.
* **Verification could not run** (:class:`VerificationCouldNotRun`): a store could not be reached,
  or anything else the verifier lets propagate because it is not a verdict about the card
  (`v1-e03-t04`). It is never reported as a verdict, in either direction.

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
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from typing import Any, Final, Literal, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as SchemaViolation
from jsonschema.exceptions import best_match  # pyright: ignore[reportUnknownVariableType]
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, computed_field
from referencing import Registry, Resource

from debate_core.application.errors import DomainError
from debate_core.application.evidence_verifier import EvidenceVerifier
from debate_core.domain import Card, VerificationStatus, render_schemas
from debate_core.domain.schema_export import JSON_SCHEMA_DIALECT
from debate_core.evidence.manifest import CARD_SCHEMA_REFERENCE, render_card_manifest_schema
from debate_core.evidence.verification_types import (
    ReasonCode,
    VerificationCheck,
    VerificationReason,
    VerificationResult,
)

__all__ = [
    "INVALID_MANIFEST_CODE",
    "UNVERIFIED_CODE",
    "VERIFICATION_COULD_NOT_RUN_CODE",
    "VERIFY_RESULT_SCHEMA_FILENAME",
    "CardVerdict",
    "InvalidManifest",
    "ManifestVerificationReport",
    "ReportedReason",
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


# --------------------------------------------------------------------------------------------
# The report
# --------------------------------------------------------------------------------------------


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

    @classmethod
    def of(cls, reason: VerificationReason) -> ReportedReason:
        return cls(
            code=reason.code, detail=reason.detail, first_differing_offset=reason.first_differing_offset
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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def reason_codes(self) -> tuple[ReasonCode, ...]:
        """The codes of :attr:`reasons`, in order, without repeats."""
        return tuple(dict.fromkeys(reason.code for reason in self.reasons))

    @classmethod
    def of_result(cls, position: int, card: Card, result: VerificationResult) -> CardVerdict:
        """The verdict the verifier reached on ``card``."""
        return cls(
            position=position,
            card_id=card.card_id,
            tag=card.tag,
            status=result.status,
            reasons=tuple(ReportedReason.of(reason) for reason in result.reasons),
            snapshot_id=result.snapshot_id,
            checks_run=tuple(check for check in VerificationCheck if check in result.checks_run),
            verifier_version=result.verifier_version,
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


class ManifestVerificationReport(BaseModel):
    """Every card of one manifest, with its verdict, in manifest order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest_version: Literal[1]
    generated_at: AwareDatetime = Field(description="The manifest's own generated_at.")
    cards: tuple[CardVerdict, ...]

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
    """Verifies every card of a manifest against the snapshots the verifier can reach."""

    def __init__(self, *, verifier: EvidenceVerifier) -> None:
        self._verifier = verifier

    async def verify(self, document: bytes) -> ManifestVerificationReport:
        """Read ``document`` as a card manifest and verify each card in it, in order.

        Raises :class:`InvalidManifest` before verifying anything if the document is not a
        manifest, and :class:`VerificationCouldNotRun` if the verifier lets a failure through.
        """
        manifest_version, generated_at, entries = read_manifest(document)
        verdicts = [await self._verdict(position, entry) for position, entry in enumerate(entries)]
        return ManifestVerificationReport(
            manifest_version=manifest_version, generated_at=generated_at, cards=tuple(verdicts)
        )

    async def _verdict(self, position: int, entry: Mapping[str, Any]) -> CardVerdict:
        try:
            # JSON in, as a stored card is read back, so a card loads here exactly as it would there.
            card = Card.model_validate_json(json.dumps(entry))
        except ValidationError as invalid:
            return CardVerdict.of_invalid_card(position, entry, invalid)
        try:
            result = await self._verifier.verify(card)
        except DomainError as stopped:
            raise VerificationCouldNotRun(card_id=card.card_id, position=position, cause=stopped) from stopped
        return CardVerdict.of_result(position, card, result)


# --------------------------------------------------------------------------------------------
# Reading the document
# --------------------------------------------------------------------------------------------

_GENERATED_AT: Final[TypeAdapter[datetime]] = TypeAdapter(AwareDatetime)


def read_manifest(document: bytes) -> tuple[Literal[1], datetime, list[dict[str, Any]]]:
    """``document``'s version, timestamp and card entries, once it is known to be a manifest.

    Strict JSON (no duplicate keys, no ``NaN``), then the published schema, then the timestamp,
    whose ``date-time`` format JSON Schema only annotates. The cards come back as plain entries:
    each is made a ``Card`` on its own, so one invalid card cannot refuse the others.
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

    worst, violations = _schema_violations(data)
    if worst is not None:
        raise InvalidManifest(worst.json_path, worst.description(), violations=violations)

    try:
        generated_at = _GENERATED_AT.validate_python(data["generated_at"])
    except ValidationError as invalid:
        raise InvalidManifest("$.generated_at", invalid.errors(include_url=False)[0]["msg"]) from invalid
    return 1, generated_at, data["cards"]


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
    a manifest; and the card the run stopped at when verification could not run. The exit codes
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
            "Exit 1: some card UNVERIFIED, report under error.details. Exit 2: usage error or a "
            "manifest that fails its schema, with the failing JSON path. Exit 3: verification could "
            "not run."
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
