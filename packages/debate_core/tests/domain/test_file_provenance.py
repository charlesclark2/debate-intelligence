"""The provenance sidecar's model refuses what a sidecar must never say (`v1-e33-t02`)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from debate_core.domain.debate_files import FontSizeSpan, FormattingSpan
from debate_core.domain.file_provenance import (
    FileProvenanceEntry,
    FileProvenanceManifest,
    camp_path_sidecar_name,
    formatting_sha256,
    text_sha256,
)
from debate_core.domain.file_recipe import RecipeStatus
from debate_core.domain.style_profile import RunEmphasis, StyleMatchSource

DIGEST = "a" * 64


def entry(**changes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "position": 1,
        "recipe_path": "structure[0].blocks[0].items[0]",
        "section_path": ("Pocket", "Block"),
        "fingerprint": DIGEST,
        "fingerprint_version": "card-fingerprint-v3",
        "resolution": "AUTO",
        "caselist": "hspolicy26",
        "snapshot": "2026-09-15",
        "last_snapshot": "2026-09-22",
        "disclosure_digest": DIGEST,
        "school": "Maple Grove",
        "team_code": "QX",
        "source_sha256": DIGEST,
        "first_element_index": 3,
        "last_element_index": 5,
        "completeness": "FULL",
        "evidence_sha256": DIGEST,
        "cite_sha256": DIGEST,
        "formatting_sha256": DIGEST,
        "tag_overridden": False,
        "provenance_line": "[Disclosed: hspolicy26 2026-09-15 — Maple Grove QX]",
        "forbidden_characters_replaced": 0,
    }
    values.update(changes)
    return values


def manifest(cards: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "title": "File",
        "topic": "topic",
        "format": "POLICY",
        "caselist": "hspolicy26",
        "position": "position",
        "side": "AFF",
        "recipe_hash": DIGEST,
        "builder_version": "builder",
        "parser_version": "parser",
        "style_profile_version": "profile",
        "fingerprint_version": "card-fingerprint-v3",
        "built_at": datetime(2026, 10, 19, tzinfo=UTC),
        "docx_sha256": DIGEST,
        "cards": cards,
    }


def test_a_well_formed_entry_and_manifest_validate() -> None:
    FileProvenanceManifest.model_validate(manifest([entry(), entry(position=2)]))


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"tag_overridden": True}, "only an overridden one"),
        ({"tag_authored_by": "COACH"}, "only an overridden one"),
        ({"original_tag_sha256": DIGEST}, "only for an overridden tag"),
        ({"school": None}, "with its school"),
        ({"first_element_index": 6}, "precedes"),
        ({"verification_status": "VERIFIED"}, "UNVERIFIED"),
        ({"provenance_mode": "FETCH"}, "FILE_IMPORT"),
    ],
    ids=[
        "override-not-the-coachs",
        "coach-without-override",
        "hash-without-override",
        "team-without-school",
        "range",
        "verified",
        "mode",
    ],
)
def test_an_entry_that_says_what_a_sidecar_must_not_is_refused(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        FileProvenanceEntry.model_validate(entry(**changes))


def test_an_overridden_tag_is_the_coachs_with_or_without_an_original() -> None:
    FileProvenanceEntry.model_validate(
        entry(tag_overridden=True, tag_authored_by="COACH", original_tag_sha256=DIGEST)
    )
    FileProvenanceEntry.model_validate(entry(tag_overridden=True, tag_authored_by="COACH"))


@pytest.mark.parametrize("positions", [[2], [1, 1], [2, 1], [1, 3]])
def test_card_positions_run_one_two_three_in_file_order(positions: list[int]) -> None:
    with pytest.raises(ValidationError, match="card positions run"):
        FileProvenanceManifest.model_validate(manifest([entry(position=position) for position in positions]))


def _span(
    emphasis: RunEmphasis, start: int, end: int, rule: str, colour: str | None = None
) -> FormattingSpan:
    return FormattingSpan(
        emphasis=emphasis,
        start_offset=start,
        end_offset=end,
        highlight_color=colour,
        rule_id=rule,
        match_source=StyleMatchSource.VERBATIM,
    )


def test_the_formatting_digest_reads_coverage_not_how_spans_were_split_or_found() -> None:
    split = [_span(RunEmphasis.UNDERLINE, 0, 4, "alias"), _span(RunEmphasis.UNDERLINE, 4, 9, "style")]
    whole = [_span(RunEmphasis.UNDERLINE, 0, 9, "style")]
    assert formatting_sha256(split, ()) == formatting_sha256(whole, ())


def test_the_formatting_digest_tells_apart_what_a_reader_would_see_differently() -> None:
    base = formatting_sha256([_span(RunEmphasis.UNDERLINE, 0, 9, "style")], ())
    assert formatting_sha256([_span(RunEmphasis.UNDERLINE, 0, 8, "style")], ()) != base
    assert formatting_sha256([_span(RunEmphasis.EMPHASIS, 0, 9, "style")], ()) != base
    cyan = formatting_sha256([_span(RunEmphasis.HIGHLIGHT, 0, 9, "h", "cyan")], ())
    assert formatting_sha256([_span(RunEmphasis.HIGHLIGHT, 0, 9, "h", "green")], ()) != cyan
    sized = formatting_sha256([], [FontSizeSpan(start_offset=0, end_offset=9, half_points=16)])
    assert formatting_sha256([], [FontSizeSpan(start_offset=0, end_offset=9, half_points=22)]) != sized


def test_text_digests_are_sha256_of_utf8() -> None:
    assert text_sha256("") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


# -- camp (OpenEv) cards, `v1-e33-t06` -----------------------------------------------------------

CAMP_LINE = "[OpenEv: Lanternfield Institute 2031 — Policy, Synthetic Grid Reliability CP]"


def camp_entry(**changes: Any) -> dict[str, Any]:
    """A camp card's entry: the camp, its release and file title, and no disclosure."""
    values = entry(
        caselist="openev",
        camp="Lanternfield Institute",
        snapshot="2031-policy",
        last_snapshot="2031-policy",
        disclosure_digest=None,
        school=None,
        team_code=None,
        camp_year=2031,
        camp_event="POLICY",
        camp_file_title="Synthetic Grid Reliability CP",
        provenance_line=CAMP_LINE,
    )
    values.update(changes)
    return values


def test_a_camp_entry_names_its_camp_year_event_and_file_title() -> None:
    parsed = FileProvenanceEntry.model_validate(camp_entry())
    assert (parsed.camp, parsed.camp_year, parsed.camp_event, parsed.camp_file_title) == (
        "Lanternfield Institute",
        2031,
        "POLICY",
        "Synthetic Grid Reliability CP",
    )
    FileProvenanceManifest.model_validate(manifest([entry(), camp_entry(position=2)]))


def test_a_camp_entry_without_a_release_record_names_no_file_title() -> None:
    FileProvenanceEntry.model_validate(camp_entry(camp_file_title=None))


@pytest.mark.parametrize(
    "changes",
    [
        {"camp": "Lanternfield Institute"},
        {"camp_year": 2031},
        {"camp_event": "POLICY"},
        {"camp_file_title": "Synthetic Grid Reliability CP"},
    ],
    ids=["camp", "year", "event", "file-title"],
)
def test_a_caselist_entry_names_no_camp(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="only a camp card"):
        FileProvenanceEntry.model_validate(entry(**changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"disclosure_digest": DIGEST},
        {"school": "Maple Grove"},
        {"school": "Maple Grove", "team_code": "QX"},
        {"side": "AFF"},
        {"tournament": "Invented Invitational"},
        {"round": "Round 4"},
    ],
    ids=["digest", "school", "team", "side", "tournament", "round"],
)
def test_a_camp_entry_names_no_disclosure_because_a_camp_file_has_none(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="a camp file has no disclosure"):
        FileProvenanceEntry.model_validate(camp_entry(**changes))


def test_a_sidecar_written_before_camp_cards_still_validates() -> None:
    """Every key `v1-e33-t02` wrote, and none of the camp keys this task added."""
    written_before = manifest([entry()])
    for key in ("camp_year", "camp_event", "camp_file_title"):
        assert key not in written_before["cards"][0]
    parsed = FileProvenanceManifest.model_validate(written_before)
    assert (parsed.cards[0].camp_year, parsed.cards[0].camp_event, parsed.cards[0].camp_file_title) == (
        None,
        None,
        None,
    )


def test_a_sidecar_written_before_the_recipe_status_validates_with_none_and_records_one_given() -> None:
    """`recipe_status` is an addition (`v1-e33-t05`): an older sidecar has no key, and reads as None."""
    older = FileProvenanceManifest.model_validate(manifest([entry()]))
    assert older.recipe_status is None
    draft = FileProvenanceManifest.model_validate({**manifest([entry()]), "recipe_status": "draft"})
    assert draft.recipe_status is RecipeStatus.DRAFT
    with pytest.raises(ValidationError):
        FileProvenanceManifest.model_validate({**manifest([entry()]), "recipe_status": "approved"})


# ------------------------------------------------------------------------------------------------
# A camp card's camp paths, beside the sidecar (`v1-e33-t07`)
# ------------------------------------------------------------------------------------------------

PATH_2031 = "a1" * 32
PATH_2031_SECOND = "a2" * 32

ENTRY_KEYS_EVERY_EARLIER_BUILD_READS = {
    "position",
    "recipe_path",
    "section_path",
    "fingerprint",
    "fingerprint_version",
    "resolution",
    "caselist",
    "camp",
    "camp_year",
    "camp_event",
    "camp_file_title",
    "snapshot",
    "last_snapshot",
    "disclosure_digest",
    "school",
    "team_code",
    "side",
    "tournament",
    "round",
    "source_sha256",
    "first_element_index",
    "last_element_index",
    "completeness",
    "evidence_sha256",
    "cite_sha256",
    "formatting_sha256",
    "tag_overridden",
    "tag_authored_by",
    "original_tag_sha256",
    "provenance_line",
    "forbidden_characters_replaced",
    "warnings",
    "provenance_mode",
    "verification_status",
}
"""The keys of a sidecar entry `v1.1.0-dev.200` and `v1.1.0-dev.251` read, written out from their model."""


def camp_manifest() -> FileProvenanceManifest:
    return FileProvenanceManifest.model_validate(
        manifest(
            [
                entry(),
                camp_entry(position=2, camp_path_disclosures=(PATH_2031, PATH_2031_SECOND)),
                camp_entry(position=3),
            ]
        )
    )


def test_a_camp_entry_carries_its_camp_paths_and_the_sidecar_keeps_the_keys_every_earlier_build_reads() -> (
    None
):
    built = camp_manifest()
    assert built.cards[1].camp_path_disclosures == (PATH_2031, PATH_2031_SECOND)
    written = json.loads(built.to_json_bytes())
    assert [set(card) for card in written["cards"]] == [ENTRY_KEYS_EVERY_EARLIER_BUILD_READS] * 3
    assert PATH_2031 not in built.to_json_bytes().decode()


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"camp_path_disclosures": (PATH_2031_SECOND, PATH_2031)}, "listed once each, sorted"),
        ({"camp_path_disclosures": (PATH_2031, PATH_2031)}, "listed once each, sorted"),
    ],
    ids=["unsorted", "repeated"],
)
def test_camp_paths_are_listed_once_each_sorted(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        FileProvenanceEntry.model_validate(camp_entry(**changes))


def test_a_caselist_entry_is_at_no_camp_path() -> None:
    with pytest.raises(ValidationError, match="only a camp card"):
        FileProvenanceEntry.model_validate(entry(camp_path_disclosures=(PATH_2031,)))


def test_the_camp_paths_file_names_each_camp_card_with_a_camp_path_and_the_sidecars_sha256() -> None:
    built = camp_manifest()
    sidecar = built.to_json_bytes()
    camp_paths = built.camp_path_sidecar(sidecar)
    assert camp_paths is not None
    assert json.loads(camp_paths.to_json_bytes()) == {
        "schema_version": 1,
        "sidecar_sha256": hashlib.sha256(sidecar).hexdigest(),
        "cards": [{"position": 2, "camp_path_disclosures": [PATH_2031, PATH_2031_SECOND]}],
    }
    assert camp_path_sidecar_name("grid.docx") == "grid.docx.camp-paths.json"


def test_a_sidecar_with_no_camp_path_has_no_camp_paths_file() -> None:
    built = FileProvenanceManifest.model_validate(manifest([entry(), camp_entry(position=2)]))
    assert built.camp_path_sidecar(built.to_json_bytes()) is None


def test_the_camp_paths_go_back_on_the_entries_of_the_sidecar_they_were_written_for() -> None:
    built = camp_manifest()
    sidecar = built.to_json_bytes()
    camp_paths = built.camp_path_sidecar(sidecar)
    assert camp_paths is not None
    read = FileProvenanceManifest.model_validate_json(sidecar)
    assert [card.camp_path_disclosures for card in read.cards] == [(), (), ()]
    joined = read.with_camp_paths(sidecar, camp_paths.to_json_bytes())
    assert [card.camp_path_disclosures for card in joined.cards] == [(), (PATH_2031, PATH_2031_SECOND), ()]


@pytest.mark.parametrize(
    "case",
    ["another-sidecar", "absent", "not-json", "a-caselist-card", "no-such-position"],
)
def test_camp_paths_that_are_not_this_sidecars_give_none(case: str) -> None:
    """Each camp card is then checked as before: a camp path suppression of its bytes flags it."""
    built = camp_manifest()
    sidecar = built.to_json_bytes()
    camp_paths = built.camp_path_sidecar(sidecar)
    assert camp_paths is not None
    document = json.loads(camp_paths.to_json_bytes())
    given: bytes | None
    if case == "another-sidecar":
        document["sidecar_sha256"] = hashlib.sha256(sidecar + b"\n").hexdigest()
        given = json.dumps(document).encode()
    elif case == "absent":
        given = None
    elif case == "not-json":
        given = b"{"
    else:
        position = 1 if case == "a-caselist-card" else 9
        document["cards"] = [{"position": position, "camp_path_disclosures": [PATH_2031]}]
        given = json.dumps(document).encode()
    read = FileProvenanceManifest.model_validate_json(sidecar)
    assert [card.camp_path_disclosures for card in read.with_camp_paths(sidecar, given).cards] == [(), (), ()]
