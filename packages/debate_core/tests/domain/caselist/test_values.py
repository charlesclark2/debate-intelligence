"""The caselist scalars, enums and round labels: what they accept and what they refuse.

The refusals carry most of the weight here. A caselist slug that is not a slug, a snapshot dated
tomorrow and a "team code" that is really a person's name are each a way for bad data to get into
the evidence store, and each has to fail at the model boundary rather than three tasks later.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import BaseModel, ValidationError

from debate_core.domain.caselist import (
    TEAM_CODE_MAX_LENGTH,
    Acquisition,
    CaselistSlug,
    CompetitionLevel,
    Event,
    NormalizedRound,
    RoundLabel,
    Season,
    Sha256Hex,
    Side,
    SnapshotDate,
    SourceFormat,
    SourceOrigin,
    TeamCodeText,
    normalize_round_token,
    sides_for_event,
)


class SlugHolder(BaseModel):
    """A one-field model, so a bare annotated scalar can be validated on its own."""

    value: CaselistSlug


class Sha256Holder(BaseModel):
    value: Sha256Hex


class SnapshotDateHolder(BaseModel):
    value: SnapshotDate


class TeamCodeHolder(BaseModel):
    value: TeamCodeText


class SeasonHolder(BaseModel):
    value: Season


# --------------------------------------------------------------------------------------------
# CaselistSlug
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("slug", ["hsld26", "hspolicy26", "hspf26", "ndtceda26", "opencaselist99"])
def test_a_real_caselist_slug_is_accepted(slug: str) -> None:
    assert SlugHolder(value=slug).value == slug


@pytest.mark.parametrize(
    "slug",
    [
        "hsld",  # no season year
        "hsld2026",  # four-digit year
        "HSLD26",  # uppercase
        "hs-ld26",  # punctuation
        "hs ld26",  # whitespace
        "26hsld",  # year first
        "",
    ],
)
def test_a_malformed_caselist_slug_is_rejected(slug: str) -> None:
    with pytest.raises(ValidationError):
        SlugHolder(value=slug)


def test_caselist_slugs_are_data_not_an_enum() -> None:
    """A slug for a season nobody has thought about yet still validates."""
    assert SlugHolder(value="hsld31").value == "hsld31"


# --------------------------------------------------------------------------------------------
# Sha256Hex
# --------------------------------------------------------------------------------------------


def test_a_lowercase_hex_digest_is_accepted() -> None:
    digest = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert Sha256Holder(value=digest).value == digest


@pytest.mark.parametrize(
    "digest",
    [
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b85",  # 63 characters
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b8555",  # 65 characters
        "E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855",  # uppercase
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b85z",  # not hex
        "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "",
    ],
)
def test_a_malformed_sha256_is_rejected(digest: str) -> None:
    with pytest.raises(ValidationError):
        Sha256Holder(value=digest)


# --------------------------------------------------------------------------------------------
# SnapshotDate
# --------------------------------------------------------------------------------------------


def test_a_past_snapshot_date_is_accepted() -> None:
    assert SnapshotDateHolder(value=date(2026, 9, 15)).value == date(2026, 9, 15)


def test_todays_snapshot_date_is_accepted() -> None:
    today = datetime.now(UTC).date()
    assert SnapshotDateHolder(value=today).value == today


def test_a_snapshot_date_in_the_future_is_rejected() -> None:
    tomorrow = datetime.now(UTC).date() + timedelta(days=1)
    with pytest.raises(ValidationError, match="in the future"):
        SnapshotDateHolder(value=tomorrow)


def test_a_snapshot_date_parses_from_an_iso_string() -> None:
    assert SnapshotDateHolder(value="2026-09-15").value == date(2026, 9, 15)


# --------------------------------------------------------------------------------------------
# TeamCodeText — the data-minimization scalar
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("code", ["RiOs", "AB", "SmithJones", "A-B", "Team1"])
def test_a_disclosed_team_code_is_accepted(code: str) -> None:
    assert TeamCodeHolder(value=code).value == code


def test_a_team_code_is_stripped_of_surrounding_whitespace() -> None:
    assert TeamCodeHolder(value="  RiOs  ").value == "RiOs"


def test_a_team_code_longer_than_the_limit_is_rejected() -> None:
    too_long = "A" * (TEAM_CODE_MAX_LENGTH + 1)
    with pytest.raises(ValidationError):
        TeamCodeHolder(value=too_long)


def test_a_team_code_at_the_limit_is_accepted() -> None:
    at_limit = "A" * TEAM_CODE_MAX_LENGTH
    assert TeamCodeHolder(value=at_limit).value == at_limit


@pytest.mark.parametrize("name_shaped", ["Jane Rivera", "Rivera Osei", "A B", "Jane\tRivera"])
def test_whitespace_separated_words_are_rejected_as_a_name(name_shaped: str) -> None:
    with pytest.raises(ValidationError, match="never whitespace-separated words"):
        TeamCodeHolder(value=name_shaped)


def test_an_empty_team_code_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TeamCodeHolder(value="   ")


# --------------------------------------------------------------------------------------------
# Season
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("season", ["2026-27", "2019-20", "1999-00"])
def test_a_season_spanning_two_consecutive_years_is_accepted(season: str) -> None:
    assert SeasonHolder(value=season).value == season


@pytest.mark.parametrize("season", ["2026-28", "2026-26", "2026-2027", "26-27", "2026", ""])
def test_a_malformed_or_inconsistent_season_is_rejected(season: str) -> None:
    with pytest.raises(ValidationError):
        SeasonHolder(value=season)


# --------------------------------------------------------------------------------------------
# Side and Event
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("event", "allowed"),
    [
        (Event.LD, {Side.AFF, Side.NEG, Side.UNKNOWN}),
        (Event.POLICY, {Side.AFF, Side.NEG, Side.UNKNOWN}),
        (Event.PF, {Side.PRO, Side.CON, Side.UNKNOWN}),
    ],
)
def test_each_event_allows_its_own_sides_plus_unknown(event: Event, allowed: set[Side]) -> None:
    assert sides_for_event(event) == allowed


def test_unknown_is_legal_for_every_event() -> None:
    assert all(Side.UNKNOWN in sides_for_event(event) for event in Event)


def test_pf_sides_are_not_legal_in_ld_or_policy() -> None:
    assert Side.PRO not in sides_for_event(Event.LD)
    assert Side.CON not in sides_for_event(Event.POLICY)


def test_aff_and_neg_are_not_legal_in_pf() -> None:
    assert Side.AFF not in sides_for_event(Event.PF)
    assert Side.NEG not in sides_for_event(Event.PF)


def test_every_event_has_a_side_table() -> None:
    """A new event must bring its own legal sides rather than silently inheriting none."""
    for event in Event:
        assert sides_for_event(event)


# --------------------------------------------------------------------------------------------
# Round labels
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("R1", NormalizedRound.R1),
        ("r1", NormalizedRound.R1),
        ("Round 3", NormalizedRound.R3),
        ("ROUND_3", NormalizedRound.R3),
        ("rd5", NormalizedRound.R5),
        ("9", NormalizedRound.R9),
        ("Doubles", NormalizedRound.DOUBLES),
        ("double octas", NormalizedRound.DOUBLES),
        ("Double-Octas", NormalizedRound.DOUBLES),
        ("Octas", NormalizedRound.OCTAS),
        ("octofinals", NormalizedRound.OCTAS),
        ("Quarters", NormalizedRound.QUARTERS),
        ("quarterfinals", NormalizedRound.QUARTERS),
        ("Semis", NormalizedRound.SEMIS),
        ("Semifinals", NormalizedRound.SEMIS),
        ("Finals", NormalizedRound.FINALS),
        ("  finals  ", NormalizedRound.FINALS),
    ],
)
def test_a_recognised_round_token_normalizes(raw: str, expected: NormalizedRound) -> None:
    assert normalize_round_token(raw) is expected


@pytest.mark.parametrize("raw", ["Prelims", "Elims", "Round Robin", "R10", "0", "Greenhill", "", "   "])
def test_an_unrecognised_round_token_normalizes_to_none(raw: str) -> None:
    assert normalize_round_token(raw) is None


def test_a_round_label_keeps_the_raw_token_and_the_normalized_round() -> None:
    label = RoundLabel.from_raw("Round 3")
    assert label.raw == "Round 3"
    assert label.normalized is NormalizedRound.R3
    assert label.is_recognised


def test_an_unrecognised_round_label_still_keeps_what_was_written() -> None:
    label = RoundLabel.from_raw("Round Robin")
    assert label.raw == "Round Robin"
    assert label.normalized is None
    assert not label.is_recognised


def test_a_round_label_round_trips_through_json() -> None:
    label = RoundLabel.from_raw("Semis")
    assert RoundLabel.model_validate_json(label.model_dump_json()) == label


def test_a_round_label_needs_a_raw_token() -> None:
    with pytest.raises(ValidationError):
        RoundLabel(raw="", normalized=None)


def test_the_normalized_rounds_are_the_nine_prelims_and_five_elims() -> None:
    assert {member.value for member in NormalizedRound} == {
        "R1",
        "R2",
        "R3",
        "R4",
        "R5",
        "R6",
        "R7",
        "R8",
        "R9",
        "DOUBLES",
        "OCTAS",
        "QUARTERS",
        "SEMIS",
        "FINALS",
    }


# --------------------------------------------------------------------------------------------
# The remaining closed vocabularies
# --------------------------------------------------------------------------------------------


def test_the_enum_values_are_the_tokens_the_specs_use() -> None:
    assert {member.value for member in Event} == {"LD", "POLICY", "PF"}
    assert {member.value for member in Side} == {"AFF", "NEG", "PRO", "CON", "UNKNOWN"}
    assert {member.value for member in SourceFormat} == {"DOCX", "DOC", "PDF", "OTHER"}
    assert {member.value for member in SourceOrigin} == {"CASELIST_ARCHIVE", "OPENEV"}
    assert {member.value for member in Acquisition} == {"MANUAL_DOWNLOAD", "API"}
    assert {member.value for member in CompetitionLevel} == {"HIGH_SCHOOL", "COLLEGE", "MIDDLE_SCHOOL"}


def test_every_caselist_enum_serializes_as_a_bare_string() -> None:
    for member in (Event.LD, Side.PRO, SourceFormat.PDF, SourceOrigin.OPENEV, Acquisition.API):
        assert member == member.value
