"""The seven caselist entities: their invariants and their JSON round-trip.

A repository writes these as JSON and reads them back, and a manifest row is the same JSON again,
so the round-trip is not a formality: a lossy one would silently rewrite provenance that a
removal request or a landscape report later depends on.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from debate_core.domain.caselist import (
    CASELIST_MODELS,
    IMPORTED_EVIDENCE_PROVENANCE_MODE,
    Acquisition,
    ArchiveSnapshot,
    CampFile,
    Caselist,
    CompetitionLevel,
    Disclosure,
    Event,
    NormalizedRound,
    RoundLabel,
    School,
    Side,
    SourceDocument,
    SourceFormat,
    SourceOrigin,
    TeamCode,
)
from debate_core.domain.enums import ProvenanceMode

SOURCE_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
ARCHIVE_SHA256 = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
OTHER_SHA256 = "5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03"

FIRST_SNAPSHOT = date(2026, 9, 1)
SECOND_SNAPSHOT = date(2026, 9, 8)


def make_caselist(**overrides: object) -> Caselist:
    """The HS LD caselist, for tests that vary one thing about it."""
    fields: dict[str, object] = {
        "slug": "hsld26",
        "event": Event.LD,
        "level": CompetitionLevel.HIGH_SCHOOL,
        "season": "2026-27",
    }
    fields.update(overrides)
    return Caselist.model_validate(fields)


def make_snapshot(**overrides: object) -> ArchiveSnapshot:
    fields: dict[str, object] = {
        "caselist": "hsld26",
        "snapshot": FIRST_SNAPSHOT,
        "archive_sha256": ARCHIVE_SHA256,
        "acquisition": Acquisition.MANUAL_DOWNLOAD,
        "file_count": 412,
    }
    fields.update(overrides)
    return ArchiveSnapshot.model_validate(fields)


def make_source(**overrides: object) -> SourceDocument:
    fields: dict[str, object] = {
        "sha256": SOURCE_SHA256,
        "byte_size": 48_512,
        "source_format": SourceFormat.DOCX,
        "origin": SourceOrigin.CASELIST_ARCHIVE,
        "caselist": "hsld26",
        "first_seen_snapshot": FIRST_SNAPSHOT,
        "last_seen_snapshot": FIRST_SNAPSHOT,
    }
    fields.update(overrides)
    return SourceDocument.model_validate(fields)


def make_disclosure(**overrides: object) -> Disclosure:
    fields: dict[str, object] = {
        "source_sha256": SOURCE_SHA256,
        "caselist": "hsld26",
        "snapshot": FIRST_SNAPSHOT,
        "event": Event.LD,
        "school": "Northside Academy",
        "team_code": "RiOs",
        "side": Side.AFF,
        "tournament": "Glenbrooks",
        "round_label": RoundLabel.from_raw("Round 3"),
        "source_path": "2026-09-01/Northside Academy/RiOs/Northside Academy-RiOs-Aff-Glenbrooks-R3.docx",
    }
    fields.update(overrides)
    return Disclosure.model_validate(fields)


def make_camp_file(**overrides: object) -> CampFile:
    fields: dict[str, object] = {
        "source_sha256": OTHER_SHA256,
        "camp": "DDI",
        "year": 2026,
        "event": Event.POLICY,
        "file_title": "Water Infrastructure Affirmative",
        "snapshot": FIRST_SNAPSHOT,
    }
    fields.update(overrides)
    return CampFile.model_validate(fields)


ALL_BUILDERS = (make_caselist, make_snapshot, make_source, make_disclosure, make_camp_file)


def make_school() -> School:
    return School(caselist="hsld26", name="Northside Academy")


def make_team_code() -> TeamCode:
    return TeamCode(caselist="hsld26", school="Northside Academy", code="RiOs")


# --------------------------------------------------------------------------------------------
# Every model: frozen, forbids extras, round-trips
# --------------------------------------------------------------------------------------------


def one_of_each() -> tuple[object, ...]:
    """One populated instance of each of the seven entities."""
    return (
        make_caselist(),
        make_school(),
        make_team_code(),
        make_snapshot(),
        make_source(),
        make_disclosure(),
        make_camp_file(),
    )


def test_the_seven_entities_are_the_ones_the_spec_names() -> None:
    assert [model.__name__ for model in CASELIST_MODELS] == [
        "Caselist",
        "School",
        "TeamCode",
        "ArchiveSnapshot",
        "SourceDocument",
        "Disclosure",
        "CampFile",
    ]


@pytest.mark.parametrize("model", CASELIST_MODELS, ids=lambda model: model.__name__)
def test_every_entity_is_frozen_and_forbids_unknown_fields(model: type) -> None:
    config = model.model_config  # type: ignore[attr-defined]
    assert config["frozen"] is True
    assert config["extra"] == "forbid"


@pytest.mark.parametrize("model", CASELIST_MODELS, ids=lambda model: model.__name__)
def test_every_entity_has_a_docstring(model: type) -> None:
    assert model.__doc__ and len(model.__doc__.strip()) > 40


@pytest.mark.parametrize("entity", one_of_each(), ids=lambda entity: type(entity).__name__)
def test_every_entity_round_trips_through_json(entity: object) -> None:
    model = type(entity)
    as_json = entity.model_dump_json()  # type: ignore[attr-defined]
    restored = model.model_validate_json(as_json)  # type: ignore[attr-defined]
    assert restored == entity
    assert restored.model_dump_json() == as_json


@pytest.mark.parametrize("entity", one_of_each(), ids=lambda entity: type(entity).__name__)
def test_an_unknown_field_is_refused(entity: object) -> None:
    payload = entity.model_dump()  # type: ignore[attr-defined]
    payload["debater_names"] = ["Jane Rivera"]
    with pytest.raises(ValidationError):
        type(entity).model_validate(payload)  # type: ignore[attr-defined]


@pytest.mark.parametrize("entity", one_of_each(), ids=lambda entity: type(entity).__name__)
def test_an_entity_cannot_be_mutated_in_place(entity: object) -> None:
    with pytest.raises(ValidationError):
        entity.caselist = "hspf26"  # type: ignore[attr-defined]


# --------------------------------------------------------------------------------------------
# Caselist, School, TeamCode
# --------------------------------------------------------------------------------------------


def test_a_caselist_carries_slug_event_level_and_season() -> None:
    caselist = make_caselist(display_name="HS LD 2026-27")
    assert caselist.slug == "hsld26"
    assert caselist.event is Event.LD
    assert caselist.level is CompetitionLevel.HIGH_SCHOOL
    assert caselist.season == "2026-27"
    assert caselist.display_name == "HS LD 2026-27"


def test_a_caselist_slug_is_validated_not_enumerated() -> None:
    assert make_caselist(slug="hspf26", event=Event.PF).slug == "hspf26"
    with pytest.raises(ValidationError):
        make_caselist(slug="HS LD 26")


def test_a_team_code_that_is_a_name_is_refused() -> None:
    with pytest.raises(ValidationError, match="never whitespace-separated words"):
        TeamCode(caselist="hsld26", school="Northside Academy", code="Jane Rivera")


def test_a_school_and_a_team_code_name_their_caselist() -> None:
    assert make_school().caselist == "hsld26"
    assert make_team_code().code == "RiOs"


# --------------------------------------------------------------------------------------------
# ArchiveSnapshot
# --------------------------------------------------------------------------------------------


def test_an_archive_snapshot_records_how_it_was_acquired() -> None:
    snapshot = make_snapshot(acquisition=Acquisition.API)
    assert snapshot.acquisition is Acquisition.API
    assert snapshot.file_count == 412
    assert snapshot.archive_sha256 == ARCHIVE_SHA256


def test_an_archive_snapshot_refuses_a_negative_file_count() -> None:
    with pytest.raises(ValidationError):
        make_snapshot(file_count=-1)


def test_an_archive_snapshot_refuses_a_malformed_archive_hash() -> None:
    with pytest.raises(ValidationError):
        make_snapshot(archive_sha256="not-a-hash")


# --------------------------------------------------------------------------------------------
# SourceDocument
# --------------------------------------------------------------------------------------------


def test_a_source_document_is_identified_by_its_hash() -> None:
    source = make_source()
    assert source.sha256 == SOURCE_SHA256
    assert source.byte_size == 48_512
    assert source.is_parsable


def test_a_pdf_source_is_stored_but_not_parsable() -> None:
    assert not make_source(source_format=SourceFormat.PDF).is_parsable
    assert not make_source(source_format=SourceFormat.DOC).is_parsable


def test_a_source_seen_again_widens_its_snapshot_range() -> None:
    source = make_source().evolve(last_seen_snapshot=SECOND_SNAPSHOT)
    assert source.first_seen_snapshot == FIRST_SNAPSHOT
    assert source.last_seen_snapshot == SECOND_SNAPSHOT


def test_a_source_cannot_last_be_seen_before_it_was_first_seen() -> None:
    with pytest.raises(ValidationError, match="precedes first_seen_snapshot"):
        make_source(first_seen_snapshot=SECOND_SNAPSHOT, last_seen_snapshot=FIRST_SNAPSHOT)


def test_a_caselist_source_must_name_its_caselist() -> None:
    with pytest.raises(ValidationError, match="must name its caselist"):
        make_source(caselist=None)


def test_an_openev_source_belongs_to_a_camp_not_a_caselist() -> None:
    camp_source = make_source(origin=SourceOrigin.OPENEV, caselist=None)
    assert camp_source.caselist is None
    with pytest.raises(ValidationError, match="belongs to a camp"):
        make_source(origin=SourceOrigin.OPENEV, caselist="hsld26")


# --------------------------------------------------------------------------------------------
# Disclosure
# --------------------------------------------------------------------------------------------


def test_a_disclosure_carries_what_the_archive_path_said() -> None:
    disclosure = make_disclosure()
    assert disclosure.school == "Northside Academy"
    assert disclosure.team_code == "RiOs"
    assert disclosure.side is Side.AFF
    assert disclosure.tournament == "Glenbrooks"
    assert disclosure.round_label is not None
    assert disclosure.round_label.raw == "Round 3"
    assert disclosure.round_label.normalized is NormalizedRound.R3
    assert disclosure.parse_warnings == ()


def test_an_unparseable_filename_yields_an_unknown_side_and_a_warning_not_a_drop() -> None:
    disclosure = make_disclosure(
        side=Side.UNKNOWN,
        tournament=None,
        round_label=None,
        parse_warnings=("no side token in filename", "no round token in filename"),
    )
    assert disclosure.side is Side.UNKNOWN
    assert disclosure.tournament is None
    assert disclosure.round_label is None
    assert len(disclosure.parse_warnings) == 2


def test_side_defaults_to_unknown_when_nothing_was_parsed() -> None:
    fields = make_disclosure().model_dump()
    del fields["side"]
    assert Disclosure.model_validate(fields).side is Side.UNKNOWN


@pytest.mark.parametrize("side", [Side.AFF, Side.NEG, Side.UNKNOWN])
def test_ld_and_policy_disclosures_accept_aff_neg_and_unknown(side: Side) -> None:
    assert make_disclosure(event=Event.LD, side=side).side is side
    assert make_disclosure(event=Event.POLICY, side=side).side is side


@pytest.mark.parametrize("side", [Side.PRO, Side.CON, Side.UNKNOWN])
def test_pf_disclosures_accept_pro_con_and_unknown(side: Side) -> None:
    assert make_disclosure(caselist="hspf26", event=Event.PF, side=side).side is side


@pytest.mark.parametrize(("event", "side"), [(Event.LD, Side.PRO), (Event.POLICY, Side.CON)])
def test_a_pf_side_in_an_ld_or_policy_disclosure_is_refused(event: Event, side: Side) -> None:
    with pytest.raises(ValidationError, match="is not one of its sides"):
        make_disclosure(event=event, side=side)


@pytest.mark.parametrize("side", [Side.AFF, Side.NEG])
def test_an_aff_neg_side_in_a_pf_disclosure_is_refused(side: Side) -> None:
    with pytest.raises(ValidationError, match="is not one of its sides"):
        make_disclosure(caselist="hspf26", event=Event.PF, side=side)


def test_a_disclosure_needs_the_path_it_was_filed_under() -> None:
    with pytest.raises(ValidationError):
        make_disclosure(source_path="")


# --------------------------------------------------------------------------------------------
# CampFile
# --------------------------------------------------------------------------------------------


def test_a_camp_file_carries_camp_year_event_and_title() -> None:
    camp_file = make_camp_file()
    assert camp_file.camp == "DDI"
    assert camp_file.year == 2026
    assert camp_file.event is Event.POLICY
    assert camp_file.file_title == "Water Infrastructure Affirmative"


def test_an_unresolved_camp_is_recorded_as_unknown_with_a_warning() -> None:
    camp_file = make_camp_file(camp="UNKNOWN", parse_warnings=("camp not in camp_aliases.yaml",))
    assert camp_file.camp == "UNKNOWN"
    assert camp_file.parse_warnings == ("camp not in camp_aliases.yaml",)


def test_a_camp_file_refuses_an_implausible_year() -> None:
    with pytest.raises(ValidationError):
        make_camp_file(year=1926)


# --------------------------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("entity", [make_source(), make_disclosure(), make_camp_file()])
def test_imported_evidence_is_always_file_import(entity: object) -> None:
    assert entity.provenance_mode is IMPORTED_EVIDENCE_PROVENANCE_MODE  # type: ignore[attr-defined]
    assert IMPORTED_EVIDENCE_PROVENANCE_MODE is ProvenanceMode.FILE_IMPORT


@pytest.mark.parametrize("builder", [make_source, make_disclosure, make_camp_file])
@pytest.mark.parametrize(
    "mode",
    [ProvenanceMode.PUBLISHER_RETRIEVED, ProvenanceMode.USER_SUPPLIED, ProvenanceMode.PASTED],
)
def test_no_other_provenance_mode_may_be_claimed(builder: object, mode: ProvenanceMode) -> None:
    with pytest.raises(ValidationError, match="always FILE_IMPORT"):
        builder(provenance_mode=mode)  # type: ignore[operator]


@pytest.mark.parametrize("entity", [make_source(), make_disclosure(), make_camp_file()])
def test_every_imported_record_names_its_snapshot_and_its_source_bytes(entity: object) -> None:
    dumped = entity.model_dump()  # type: ignore[attr-defined]
    snapshot_fields = {"snapshot", "first_seen_snapshot"}
    hash_fields = {"sha256", "source_sha256"}
    assert snapshot_fields & dumped.keys()
    assert hash_fields & dumped.keys()
