"""The card manifest: a set of cards written down so that someone else can verify them.

A manifest is what `debate-research verify` reads (`v1-e03-t06-verify-command`) and what the JSON
export writes (`v1-e06-t05-json-manifest-export`). There is one manifest model, and it is this one.
The export extends it additively under a later ``manifest_version``; it does not define a second.

## The shape

::

    {"manifest_version": 1, "generated_at": "2026-10-01T12:00:00Z", "cards": [<Card>, ...]}

Each entry in ``cards`` is the domain :class:`~debate_core.domain.Card`, exactly as it serializes.
That way the manifest carries everything the verifier needs (the envelope, ``omitted_ranges``,
``spans``, ``snapshot_id``, ``normalized_text_hash``, ``normalizer_version``, ``article_id``,
``provenance_mode``) and cannot drift from the domain: a field added to ``Card`` is a field the
manifest carries.

A manifest references snapshots by id and hash and never inlines one. It carries the card's
``evidence_text`` because that is the claim being checked: verification cuts the evidence again
from the stored snapshot and compares.

## The published schema

:func:`render_card_manifest_schema` gives the JSON Schema committed as
``packages/debate_core/schemas/card_manifest.v1.json``. It does not restate the card's fields. Each
item of ``cards`` is ``{"$ref": "card.schema.json"}``, the domain's own committed schema, so the two
files cannot disagree about what a card is. A consumer resolves the reference against the file
beside it; :mod:`debate_core.application.verify_manifest` resolves it against the card schema it
renders in memory and never fetches anything.

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
"""

from __future__ import annotations

from typing import Any, Final, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from debate_core.domain import Card
from debate_core.domain.schema_export import JSON_SCHEMA_DIALECT, schema_filename

__all__ = [
    "CARD_MANIFEST_SCHEMA_FILENAME",
    "CARD_SCHEMA_REFERENCE",
    "MANIFEST_VERSION",
    "CardManifest",
    "render_card_manifest_schema",
]

MANIFEST_VERSION: Final = 1
"""The manifest version this code reads and writes."""

CARD_MANIFEST_SCHEMA_FILENAME: Final = "card_manifest.v1.json"
"""The committed schema for :data:`MANIFEST_VERSION`, in ``packages/debate_core/schemas/``."""

CARD_SCHEMA_REFERENCE: Final = schema_filename(Card)
"""How the manifest schema refers to the card schema: its committed file name, ``card.schema.json``."""


class CardManifest(BaseModel):
    """A versioned list of cards, as a file `debate-research verify` can check."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest_version: Literal[1] = Field(
        description="The manifest format version. A reader refuses a version it does not know."
    )
    generated_at: AwareDatetime = Field(description="When the manifest was written (timezone-aware).")
    cards: tuple[Card, ...] = Field(
        min_length=1,
        description="The cards, each the domain Card exactly as it serializes (card.schema.json).",
    )


def render_card_manifest_schema() -> dict[str, Any]:
    """The manifest's JSON Schema, with each card a reference to ``card.schema.json``.

    Rendered from :class:`CardManifest` in serialization mode, as the domain schemas are, and then
    the inlined card definitions are replaced by the reference. Raises ``ValueError`` if anything
    in the result still points at an inlined definition, which would mean a manifest field other
    than ``cards`` had started using a domain type and the schema would no longer be self-contained.
    """
    schema: dict[str, Any] = {"$schema": JSON_SCHEMA_DIALECT}
    schema.update(CardManifest.model_json_schema(mode="serialization"))
    schema.pop("$defs", None)
    cards = schema["properties"]["cards"]
    cards["items"] = {"$ref": CARD_SCHEMA_REFERENCE, "required": ["card_id"]}
    if "#/$defs/" in repr(schema):
        raise ValueError("the manifest schema still refers to an inlined definition: " + repr(schema))
    return schema
