"""The card manifest model and its committed JSON Schema (`v1-e03-t06-verify-command`, `v1-e06-t05`).

If the drift test fails, run `uv run scripts/export_schemas.py` and commit the result alongside the
model change.

Version 2 (`v1-e06-t05-json-manifest-export`) adds the cards' snapshot references. Version 1 is still
read: `tests/fixtures/verify/manifest_version_1.json` is `all_verified.json` exactly as `v1-e03-t06`'s
build wrote it, before `v1-e06-t02` gave cards and citations three more fields.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from tests.fixtures.verification.verification_world import VerificationWorld
from tests.fixtures.verify.manifest_world import ALL_VERIFIED, MIXED, TAMPERED
from tests.fixtures.verify.published_schemas import violations

from debate_core.application.snapshot_service import LoadedSnapshot
from debate_core.domain import Card
from debate_core.evidence.manifest import (
    CARD_MANIFEST_SCHEMA_FILENAME,
    MANIFEST_VERSION,
    READABLE_MANIFEST_VERSIONS,
    CardManifest,
    SnapshotReference,
    render_card_manifest_schema,
)

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"
FIXTURE_DIR = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "verify"
VERSION_1_MANIFEST = FIXTURE_DIR / "manifest_version_1.json"
GENERATED_AT = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)

WELLS = "Wells across the invented basin ran dry in 2031.\n\nNobody planned for it."
FENN = "Reservoirs in the invented Fenn valley held water through 2040."

SNAPSHOT_REFERENCE_FIELDS = [
    "snapshot_id",
    "sha256",
    "normalized_text_hash",
    "normalizer_version",
    "extractor_version",
    "retrieved_at",
    "canonical_url",
]
"""What a manifest says about a snapshot, written out from the spec: ids, hashes, versions, when and where."""


def committed(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


class Sources:
    """Two snapshots in one verification world, and cards cut from them."""

    def __init__(self) -> None:
        self.world = VerificationWorld()
        self.wells = self.world.add_source(WELLS)
        self.fenn = self.world.add_source(FENN)

    def reference(self, source: LoadedSnapshot) -> SnapshotReference:
        return SnapshotReference.of(source.snapshot)


@pytest.fixture(scope="module")
def sources() -> Sources:
    return Sources()


@pytest.fixture(scope="module")
def cards(sources: Sources) -> tuple[Card, Card]:
    world, wells = sources.world, sources.wells
    return world.cut_card(wells, 0, 48), world.cut_card_from_ranges(wells, ((0, 5), (13, 48)))


def current(cards: tuple[Card, ...], references: tuple[SnapshotReference, ...]) -> CardManifest:
    return CardManifest(
        manifest_version=MANIFEST_VERSION, generated_at=GENERATED_AT, cards=cards, snapshots=references
    )


def manifest_document(cards: tuple[Card, Card], sources: Sources) -> dict[str, Any]:
    """A current-version manifest of ``cards``, written by the model and read back as plain JSON."""
    return json.loads(current(cards, (sources.reference(sources.wells),)).model_dump_json())


# --------------------------------------------------------------------------------------------
# The committed schema
# --------------------------------------------------------------------------------------------


def test_the_committed_manifest_schema_matches_the_model() -> None:
    path = SCHEMA_DIR / CARD_MANIFEST_SCHEMA_FILENAME
    assert path.is_file(), "card_manifest.v1.json is missing; run: uv run scripts/export_schemas.py"
    assert committed(CARD_MANIFEST_SCHEMA_FILENAME) == render_card_manifest_schema(), (
        "card_manifest.v1.json is stale; run: uv run scripts/export_schemas.py"
    )


def test_the_manifest_schema_refers_to_the_card_schema_rather_than_restating_it() -> None:
    schema = committed(CARD_MANIFEST_SCHEMA_FILENAME)

    assert schema["properties"]["cards"]["items"] == {"$ref": "card.schema.json", "required": ["card_id"]}
    assert "$defs" not in schema
    # Not one of the card's own fields appears in the manifest schema. (A snapshot reference names
    # its snapshot's id and text hash, so those two are no longer the card's alone.)
    text = json.dumps(schema)
    for field in ("evidence_text", "omitted_ranges", "spans", "generated_by", "citation", "owner_id"):
        assert field not in text


def test_the_manifest_schema_names_its_dialect_and_forbids_unknown_keys() -> None:
    schema = committed(CARD_MANIFEST_SCHEMA_FILENAME)

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["manifest_version", "generated_at", "cards"]
    assert schema["properties"]["manifest_version"]["enum"] == [1, 2]


def test_this_build_writes_version_2_and_reads_versions_1_and_2() -> None:
    """`v1-e06-t02`'s card and citation fields reached every manifest, so the version moved on."""
    assert MANIFEST_VERSION == 2
    assert READABLE_MANIFEST_VERSIONS == (1, 2)


def test_the_schema_describes_a_snapshot_reference_by_ids_hashes_and_versions_only() -> None:
    snapshots = committed(CARD_MANIFEST_SCHEMA_FILENAME)["properties"]["snapshots"]
    reference = snapshots["items"]

    assert snapshots["type"] == "array"
    assert snapshots["minItems"] == 1
    assert reference["additionalProperties"] is False
    assert list(reference["properties"]) == SNAPSHOT_REFERENCE_FIELDS
    assert reference["required"] == SNAPSHOT_REFERENCE_FIELDS


def test_a_snapshot_reference_has_no_field_for_a_snapshots_text_or_bytes() -> None:
    assert list(SnapshotReference.model_fields) == SNAPSHOT_REFERENCE_FIELDS


def test_a_manifest_the_model_writes_passes_the_committed_schemas(
    cards: tuple[Card, Card], sources: Sources
) -> None:
    manifest = current(cards, (sources.reference(sources.wells),))
    document = json.loads(manifest.model_dump_json())

    assert violations(CARD_MANIFEST_SCHEMA_FILENAME, document) == []
    assert cards[1].omitted_ranges, "the second card should carry an omission through the round trip"
    assert CardManifest.model_validate_json(manifest.model_dump_json()) == manifest


def test_a_snapshot_reference_is_the_stored_records_ids_hashes_versions_time_and_url(
    sources: Sources,
) -> None:
    """Expected values from the fixture: VerificationWorld's constants and hashes of the text itself."""
    reference = sources.reference(sources.wells)

    assert reference.model_dump(mode="json") == {
        "snapshot_id": "0SNAP000000000000000000001",
        "sha256": hashlib.sha256(WELLS.encode("utf-8")).hexdigest(),
        "normalized_text_hash": hashlib.sha256(WELLS.encode("utf-8")).hexdigest(),
        "normalizer_version": "evidence-normalizer-v1",
        "extractor_version": "fake-extractor/1.0",
        "retrieved_at": "2026-09-30T12:05:00Z",
        "canonical_url": "https://example.org/water/invented-basin",
    }


def test_the_committed_schemas_refuse_a_card_without_an_id(
    cards: tuple[Card, Card], sources: Sources
) -> None:
    document = manifest_document(cards, sources)
    del document["cards"][1]["card_id"]

    assert violations(CARD_MANIFEST_SCHEMA_FILENAME, document) == [("$.cards[1]", "required")]


def test_the_committed_schemas_enforce_a_rule_only_the_card_schema_has(
    cards: tuple[Card, Card], sources: Sources
) -> None:
    """The reference is followed: a rule that exists only in card.schema.json is enforced."""
    document = manifest_document(cards, sources)
    document["cards"][0]["evidence_start_offset"] = -1

    assert violations(CARD_MANIFEST_SCHEMA_FILENAME, document) == [
        ("$.cards[0].evidence_start_offset", "anyOf")
    ]


def test_the_schema_requires_snapshot_references_at_version_2(
    cards: tuple[Card, Card], sources: Sources
) -> None:
    document = manifest_document(cards, sources)
    del document["snapshots"]

    assert violations(CARD_MANIFEST_SCHEMA_FILENAME, document) == [("$", "required")]

    document["snapshots"] = []
    assert violations(CARD_MANIFEST_SCHEMA_FILENAME, document) == [("$.snapshots", "minItems")]


def test_the_schema_refuses_snapshot_references_at_version_1(
    cards: tuple[Card, Card], sources: Sources
) -> None:
    document = manifest_document(cards, sources)
    document["manifest_version"] = 1

    assert violations(CARD_MANIFEST_SCHEMA_FILENAME, document) == [("$", "not")]

    del document["snapshots"]
    assert violations(CARD_MANIFEST_SCHEMA_FILENAME, document) == []


def test_the_schema_refuses_a_snapshot_reference_carrying_anything_more(
    cards: tuple[Card, Card], sources: Sources
) -> None:
    document = manifest_document(cards, sources)
    document["snapshots"][0]["normalized_text"] = WELLS

    assert violations(CARD_MANIFEST_SCHEMA_FILENAME, document) == [("$.snapshots[0]", "additionalProperties")]


# --------------------------------------------------------------------------------------------
# The prior version
# --------------------------------------------------------------------------------------------


def test_the_version_1_manifest_v1_e03_t06_wrote_still_loads_and_passes_the_schema() -> None:
    document = json.loads(VERSION_1_MANIFEST.read_bytes())
    assert document["manifest_version"] == 1
    assert "generated_by" not in document["cards"][0], "the fixture predates v1-e06-t02's card fields"

    manifest = CardManifest.model_validate_json(VERSION_1_MANIFEST.read_bytes())

    assert violations(CARD_MANIFEST_SCHEMA_FILENAME, document) == []
    assert [card.card_id for card in manifest.cards] == [
        "0CARD000000000000000000001",
        "0CARD000000000000000000002",
        "0CARD000000000000000000003",
    ]
    assert manifest.snapshots == ()
    assert all(card.generated_by == () for card in manifest.cards)


def test_the_verify_commands_own_manifests_stay_at_version_1() -> None:
    """They are the verify tests' fixtures and the prior version's; rewriting them would lose it."""
    for path in (ALL_VERIFIED, TAMPERED, MIXED):
        assert json.loads(path.read_bytes())["manifest_version"] == 1, path.name


def test_a_version_1_manifest_written_by_the_model_has_no_snapshots_key(cards: tuple[Card, Card]) -> None:
    manifest = CardManifest(manifest_version=1, generated_at=GENERATED_AT, cards=cards)
    document = json.loads(manifest.model_dump_json())

    assert list(document) == ["manifest_version", "generated_at", "cards"]
    assert violations(CARD_MANIFEST_SCHEMA_FILENAME, document) == []


# --------------------------------------------------------------------------------------------
# The model's own rules
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("manifest_version", 3),
        ("manifest_version", 0),
        ("generated_at", datetime(2026, 10, 1, 12, 0)),  # naive: refused
    ],
)
def test_the_model_refuses_another_version_and_a_naive_timestamp(
    field: str, value: object, cards: tuple[Card, Card], sources: Sources
) -> None:
    arguments: dict[str, Any] = {
        "manifest_version": 2,
        "generated_at": GENERATED_AT,
        "cards": cards,
        "snapshots": (sources.reference(sources.wells),),
    }
    arguments[field] = value

    with pytest.raises(ValidationError) as refused:
        CardManifest(**arguments)

    assert [error["loc"] for error in refused.value.errors()] == [(field,)]


def test_a_manifest_lists_at_least_one_card(cards: tuple[Card, Card], sources: Sources) -> None:
    """An empty manifest would let a gate on `verify`'s exit code pass having checked nothing."""
    with pytest.raises(ValidationError) as refused:
        CardManifest(manifest_version=1, generated_at=GENERATED_AT, cards=())
    assert [error["loc"] for error in refused.value.errors()] == [("cards",)]

    document = manifest_document(cards, sources)
    document["cards"] = []
    assert violations(CARD_MANIFEST_SCHEMA_FILENAME, document) == [("$.cards", "minItems")]


def refusal(build: Any) -> str:
    with pytest.raises(ValidationError) as refused:
        build()
    (error,) = refused.value.errors()
    return str(error["msg"])


def test_version_2_needs_the_reference_of_every_snapshot_a_card_names(sources: Sources) -> None:
    world = sources.world
    wells_card, fenn_card = world.cut_card(sources.wells, 0, 6), world.cut_card(sources.fenn, 0, 10)

    assert refusal(lambda: current((wells_card, fenn_card), (sources.reference(sources.wells),))) == (
        "Value error, snapshots must reference exactly the cards' snapshots; "
        "missing ['0SNAP000000000000000000002'], named by no card none"
    )
    assert refusal(lambda: current((wells_card,), ())) == (
        "Value error, snapshots must reference exactly the cards' snapshots; "
        "missing ['0SNAP000000000000000000001'], named by no card none"
    )


def test_version_2_refuses_a_reference_no_card_names(sources: Sources) -> None:
    wells_card = sources.world.cut_card(sources.wells, 0, 6)
    both = (sources.reference(sources.wells), sources.reference(sources.fenn))

    assert refusal(lambda: current((wells_card,), both)) == (
        "Value error, snapshots must reference exactly the cards' snapshots; "
        "missing none, named by no card ['0SNAP000000000000000000002']"
    )


def test_version_2_lists_each_snapshot_once_in_id_order(sources: Sources) -> None:
    world = sources.world
    cards = (world.cut_card(sources.wells, 0, 6), world.cut_card(sources.fenn, 0, 10))
    wells, fenn = sources.reference(sources.wells), sources.reference(sources.fenn)

    assert current(cards, (wells, fenn)).snapshots == (wells, fenn)
    for listed in ((fenn, wells), (wells, wells, fenn)):
        assert refusal(lambda listed=listed: current(cards, listed)) == (
            "Value error, snapshots must be listed once each, in snapshot id order"
        )


def test_version_2_refuses_a_card_listed_twice(cards: tuple[Card, Card], sources: Sources) -> None:
    assert refusal(lambda: current((cards[0], cards[0]), (sources.reference(sources.wells),))) == (
        "Value error, a card appears twice in the manifest; each card is listed once"
    )


def test_version_2_refuses_a_card_that_names_no_snapshot(cards: tuple[Card, Card], sources: Sources) -> None:
    blank = Card(
        owner_id=cards[0].owner_id,
        article_id=cards[0].article_id,
        tag="A card with no evidence",
        provenance_mode=cards[0].provenance_mode,
    )

    message = refusal(lambda: current((cards[0], blank), (sources.reference(sources.wells),)))

    assert message == (
        f"Value error, cards {blank.card_id} name no snapshot; every card in a manifest is cut from one"
    )


def test_version_1_refuses_snapshot_references(cards: tuple[Card, Card], sources: Sources) -> None:
    assert (
        refusal(
            lambda: CardManifest(
                manifest_version=1,
                generated_at=GENERATED_AT,
                cards=cards,
                snapshots=(sources.reference(sources.wells),),
            )
        )
        == "Value error, a version 1 manifest has no snapshots; they arrived in version 2"
    )


def test_the_rendering_refuses_a_schema_that_still_points_at_an_inlined_definition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Were a header field to start using a domain type, dropping `$defs` would leave a dangling
    reference and a schema that no consumer could resolve."""
    rendered = CardManifest.model_json_schema(mode="serialization")
    rendered["properties"]["generated_at"] = {"$ref": "#/$defs/Citation"}

    def with_a_dangling_reference(**_: object) -> dict[str, Any]:
        return rendered

    monkeypatch.setattr(CardManifest, "model_json_schema", with_a_dangling_reference)

    with pytest.raises(ValueError, match="still refers to an inlined definition"):
        render_card_manifest_schema()
