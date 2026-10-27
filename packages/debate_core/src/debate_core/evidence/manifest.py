"""The card manifest: a set of cards written down so that someone else can verify them.

A manifest is what `debate-research verify` reads (`v1-e03-t06-verify-command`) and what the JSON
export writes (`v1-e06-t05-json-manifest-export`). There is one manifest model, and it is this one.
The export extended it additively under a later ``manifest_version``; it did not define a second.

## The shape

::

    {"manifest_version": 2, "generated_at": "2026-10-01T12:00:00Z",
     "cards": [<Card>, ...], "snapshots": [<SnapshotReference>, ...]}

Each entry in ``cards`` is the domain :class:`~debate_core.domain.Card`, exactly as it serializes.
That way the manifest carries everything the verifier needs (the envelope, ``omitted_ranges``,
``spans``, ``snapshot_id``, ``normalized_text_hash``, ``normalizer_version``, ``article_id``,
``provenance_mode``) and the model calls that shaped the card (``generated_by``), and cannot drift
from the domain: a field added to ``Card`` is a field the manifest carries.

``snapshots`` holds one :class:`SnapshotReference` per snapshot the cards were cut from, in snapshot id
order: its id, the SHA-256 of its raw bytes and of its normalized text, the extractor and normalizer
versions, when it was retrieved and from where. A manifest references snapshots by id and hash and
never inlines one. It carries the card's ``evidence_text`` because that is the claim being checked:
verification cuts the evidence again from the stored snapshot and compares.

## Versions

This build writes :data:`MANIFEST_VERSION` and reads every version in :data:`READABLE_MANIFEST_VERSIONS`.

* **1** (`v1-e03-t06`): ``manifest_version``, ``generated_at`` and ``cards``.
* **2** (`v1-e06-t05`): adds ``snapshots``, which version 2 requires and version 1 never has. Cards
  written since `v1-e06-t02` also carry ``generated_by``, ``Citation.authors_are_organizations`` and
  ``Citation.cleared_by_student``. Each has a default, so a version-1 manifest written before them
  still reads; a build that reads only version 1 refuses them, which is why the version changed.

A newer build reads an older manifest. An older build does not read a newer one: it refuses the
version, and `debate-research verify` says that a newer build is needed
(:mod:`debate_core.application.verify_manifest`). The writer therefore writes every field, defaults
included.

## The published schema

:func:`render_card_manifest_schema` gives the JSON Schema committed as
``packages/debate_core/schemas/card_manifest.v1.json``. The one file describes every version this
build reads. Its name is the one `v1-e03-t06` published: consumers and the CLI's documentation name
it, and two files would be two manifest schemas.

It does not restate the card's fields. Each item of ``cards`` is ``{"$ref": "card.schema.json"}``,
the domain's own committed schema, so the two files cannot disagree about what a card is. A consumer
resolves the reference against the file beside it; :mod:`debate_core.application.verify_manifest`
resolves it against the card schema it renders in memory and never fetches anything. A snapshot
reference is the manifest's own type, so its definition is written out in place.

The item adds one rule to the card schema: ``card_id`` is required. The domain gives a card without
an id a fresh one, which is right for a card being created and wrong for one being checked, because
a report about a card nobody can name is no report at all. A serialized card always has its id, so
the rule refuses nothing a writer produces.

A manifest lists at least one card. A run that checked nothing should not be able to report that
everything it checked verified, which is what an empty manifest would let `verify` say to a script
that gates on its exit code.

## What the schema cannot say

JSON Schema describes each field. It cannot express the rules that relate fields to one another,
such as ADR-0018's length invariant (the envelope minus the omissions is exactly as long as
``evidence_text``). A card can therefore pass the schema and still not be a valid ``Card``.
`debate-research verify` reports such a card as ``CARD_INVALID`` and verifies the rest of the
manifest; see :mod:`debate_core.application.verify_manifest`.

The rules :class:`CardManifest` adds at version 2 are of the same kind: every card names a snapshot
and no two cards share an id, and ``snapshots`` lists exactly the snapshots the cards name, once
each, in id order. A writer of the model cannot break them; the schema does not check them, and
`verify` checks each card against the stored snapshot it names, not against its reference.
"""

from __future__ import annotations

import json
from typing import Any, Final, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from debate_core.domain import Card, SourceSnapshot
from debate_core.domain.base import HttpUrlStr, NonEmptyText, Sha256Hex, Ulid, UtcDatetime
from debate_core.domain.schema_export import JSON_SCHEMA_DIALECT, schema_filename

__all__ = [
    "CARD_MANIFEST_SCHEMA_FILENAME",
    "CARD_SCHEMA_REFERENCE",
    "MANIFEST_VERSION",
    "READABLE_MANIFEST_VERSIONS",
    "SNAPSHOTS_SINCE_VERSION",
    "CardManifest",
    "ManifestVersion",
    "SnapshotReference",
    "render_card_manifest_schema",
    "serialize_manifest",
]

ManifestVersion = Literal[1, 2]
"""A manifest version this code reads."""

MANIFEST_VERSION: Final = 2
"""The manifest version this code writes."""

READABLE_MANIFEST_VERSIONS: Final = (1, 2)
"""Every manifest version this code reads, oldest first; the last is :data:`MANIFEST_VERSION`."""

SNAPSHOTS_SINCE_VERSION: Final = 2
"""The first manifest version that lists the cards' snapshot references, and requires them."""

CARD_MANIFEST_SCHEMA_FILENAME: Final = "card_manifest.v1.json"
"""The committed schema of every readable version, in ``packages/debate_core/schemas/``."""

CARD_SCHEMA_REFERENCE: Final = schema_filename(Card)
"""How the manifest schema refers to the card schema: its committed file name, ``card.schema.json``."""


class SnapshotReference(BaseModel):
    """A stored snapshot, named by id and hash: what a manifest says about it, and never its text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot_id: Ulid = Field(description="The snapshot's id.")
    sha256: Sha256Hex = Field(description="SHA-256 of the raw bytes retrieved.")
    normalized_text_hash: Sha256Hex = Field(description="SHA-256 of the normalized text, UTF-8, no BOM.")
    normalizer_version: NonEmptyText = Field(
        description="The normalizer version the text was produced under."
    )
    extractor_version: NonEmptyText = Field(description="The extractor version the text was produced under.")
    retrieved_at: UtcDatetime = Field(description="When the retrieval happened, in UTC.")
    canonical_url: HttpUrlStr = Field(description="The URL actually retrieved, after redirects.")

    @classmethod
    def of(cls, snapshot: SourceSnapshot) -> SnapshotReference:
        """The reference to a stored snapshot record."""
        return cls(
            snapshot_id=snapshot.snapshot_id,
            sha256=snapshot.sha256,
            normalized_text_hash=snapshot.normalized_text_hash,
            normalizer_version=snapshot.normalizer_version,
            extractor_version=snapshot.extractor_version,
            retrieved_at=snapshot.retrieved_at,
            canonical_url=snapshot.canonical_url,
        )


class CardManifest(BaseModel):
    """A versioned list of cards, as a file `debate-research verify` can check."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest_version: ManifestVersion = Field(
        description="The manifest format version. A reader refuses a version it does not know."
    )
    generated_at: AwareDatetime = Field(description="When the manifest was written (timezone-aware).")
    cards: tuple[Card, ...] = Field(
        min_length=1,
        description="The cards, each the domain Card exactly as it serializes (card.schema.json).",
    )
    snapshots: tuple[SnapshotReference, ...] = Field(
        default=(),
        exclude_if=lambda snapshots: not snapshots,
        description=(
            "From version 2: the snapshots the cards were cut from, once each, in snapshot id order. "
            "Ids and hashes only, never a snapshot's text. Absent from a version 1 manifest."
        ),
    )

    @model_validator(mode="after")
    def _check_snapshot_references(self) -> Self:
        """Version 1 has no references; version 2 references exactly the cards' snapshots, in order."""
        if self.manifest_version < SNAPSHOTS_SINCE_VERSION:
            if "snapshots" in self.model_fields_set:
                raise ValueError("a version 1 manifest has no snapshots; they arrived in version 2")
            return self
        card_ids = [card.card_id for card in self.cards]
        if len(set(card_ids)) != len(card_ids):
            raise ValueError("a card appears twice in the manifest; each card is listed once")
        unnamed = [card.card_id for card in self.cards if card.snapshot_id is None]
        if unnamed:
            raise ValueError(
                f"cards {', '.join(unnamed)} name no snapshot; every card in a manifest is cut from one"
            )
        referenced = [reference.snapshot_id for reference in self.snapshots]
        if referenced != sorted(set(referenced)):
            raise ValueError("snapshots must be listed once each, in snapshot id order")
        named = {card.snapshot_id for card in self.cards}
        if set(referenced) != named:
            missing = sorted(str(snapshot_id) for snapshot_id in named - set(referenced))
            unused = sorted(set(referenced) - named)
            raise ValueError(
                "snapshots must reference exactly the cards' snapshots; "
                f"missing {missing or 'none'}, named by no card {unused or 'none'}"
            )
        return self


def render_card_manifest_schema() -> dict[str, Any]:
    """The manifest's JSON Schema, with each card a reference to ``card.schema.json``.

    Rendered from :class:`CardManifest` in serialization mode, as the domain schemas are, and then
    the inlined card definitions are replaced by the reference and the snapshot reference's
    definition is written out in place. ``snapshots`` is required at version 2 and refused at
    version 1, which the model says in a validator and the schema in ``if``/``then``/``else``.

    Raises ``ValueError`` if anything in the result still points at an inlined definition, which
    would mean a manifest field other than ``cards`` had started using a domain type and the schema
    would no longer be self-contained.
    """
    schema: dict[str, Any] = {"$schema": JSON_SCHEMA_DIALECT}
    schema.update(CardManifest.model_json_schema(mode="serialization"))
    definitions: dict[str, Any] = schema.pop("$defs", {})
    properties = schema["properties"]
    properties["cards"]["items"] = {"$ref": CARD_SCHEMA_REFERENCE, "required": ["card_id"]}
    snapshots = properties["snapshots"]
    snapshots.pop("default", None)
    snapshots["items"] = definitions[SnapshotReference.__name__]
    snapshots["minItems"] = 1
    schema["if"] = {
        "properties": {"manifest_version": {"type": "integer", "minimum": SNAPSHOTS_SINCE_VERSION}},
        "required": ["manifest_version"],
    }
    schema["then"] = {"required": ["snapshots"]}
    schema["else"] = {"not": {"required": ["snapshots"]}}
    if "#/$defs/" in repr(schema):
        raise ValueError("the manifest schema still refers to an inlined definition: " + repr(schema))
    return schema


def serialize_manifest(manifest: CardManifest) -> bytes:
    """The manifest as the bytes a writer stores: keys sorted, two-space indent, UTF-8, final newline.

    Sorted keys and the model's own order of cards and snapshots make the same manifest the same
    bytes every time, so two exports of one set of cards diff to nothing.
    """
    document = manifest.model_dump(mode="json")
    return (json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
