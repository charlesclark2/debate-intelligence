"""The scan's hits, field by field, and what the scrub does with the same words (`v1-e32-t39`).

Each case builds a card's prompt input as the model stage builds it (the scrub of `tag_scrub.card_tag`, the
headings of `model_stage.sent_headings`, the variables of `model_stage.prompt_variables`) and lists the
scan's hits in it, so a case says both what the scrub took out and what the scan still finds. Every
school, team code, tournament and word is invented.
"""

from __future__ import annotations

import json
from collections import Counter

import pytest

from debate_core.arguments.landscape.headings import NormalizedHeading
from debate_core.arguments.landscape.model_stage import (
    ModelCandidate,
    ModelItem,
    name_scan,
    prompt_variables,
    sent_headings,
)
from debate_core.arguments.landscape.scan_hits import (
    HitField,
    HitKind,
    ScanHit,
    ScanNames,
    cassette_hits,
    hit_counts,
    input_batch_hits,
    repair_cassette_hits,
)
from debate_core.arguments.landscape.source_headings import CaselistNames
from debate_core.arguments.landscape.tag_scrub import card_tag, code_words
from debate_core.domain.landscape import Taxonomy

CASELIST_NAMES = {"Maple Grove": ("US",), "Cedar Ridge": ("KL",)}
OWN = ("Maple Grove", "US", "Lakeside Invitational")
TOURNAMENTS = (*OWN, "Cedar Ridge", "KL", "Harbor Classic")
NAMES = CaselistNames(CASELIST_NAMES)
CODES = code_words(CASELIST_NAMES)
TAXONOMY = Taxonomy.model_validate(
    {
        "topic_id": "policy-sample-topic",
        "taxonomy_version": "1.0.0",
        "event": "POLICY",
        "positions": [
            {
                "id": "federalism-da",
                "label": "Federalism DA",
                "kind": "da",
                "side": "neg",
                "description": "Federal action in the us erodes the states",
            },
        ],
    }
)
POSITIONS = str(prompt_variables(TAXONOMY, ())["positions"])
SCAN_NAMES = ScanNames.of(CASELIST_NAMES, TOURNAMENTS, taxonomy_text=POSITIONS)


def items_sent(tag: str, headings: tuple[str, ...] = (), cite: str | None = None) -> str:
    """One card's `items` variable, its tag, cite and headings scrubbed as the stage scrubs them."""
    candidate = ModelCandidate(
        fingerprint="f" * 64,
        source_sha256="a" * 64,
        first_element_index=0,
        headings=sent_headings([NormalizedHeading(text=one, answer=False) for one in headings], CODES),
        tag=card_tag(tag, OWN, NAMES, CODES),
        short_cite=card_tag(cite, OWN, NAMES, CODES),
        own_names=OWN,
    )
    return str(prompt_variables(TAXONOMY, [ModelItem(candidate=candidate, excerpt=None)])["items"])


def shown(hits: list[ScanHit]) -> Counter[tuple[HitField, HitKind, str]]:
    return Counter((hit.where, hit.kind, hit.matched) for hit in hits)


def test_evaluation_scan_finds_nothing_where_the_scrub_took_a_school_and_a_code_out() -> None:
    """The scrub takes a school and every code word out of a tag, an ordinary word among them (`us`)."""
    sent = items_sent("Cedar Ridge says the US plan fails")

    assert json.loads(sent)[0]["tag"] == "says the plan fails"
    assert input_batch_hits("input batch 1", sent, SCAN_NAMES) == []
    assert name_scan([sent], CASELIST_NAMES, TOURNAMENTS).clean


def test_evaluation_scan_finds_another_teams_tournament_the_scrub_leaves_in_a_cite() -> None:
    """The scrub takes out the disclosing team's own tournament, not another team's: a cite naming a
    journal that shares its words is a hit, though it names no team."""
    sent = items_sent("Spending tradeoff", cite="Harbor Classic Review 2024")

    [hit] = input_batch_hits("input batch 1", sent, SCAN_NAMES)
    assert (hit.where, hit.kind, hit.matched, hit.after, hit.team_name) == (
        HitField.CITE,
        HitKind.TOURNAMENT,
        "harbor classic",
        "review 2024",
        False,
    )
    assert name_scan([sent], CASELIST_NAMES, TOURNAMENTS).other_names == 1


def test_evaluation_scan_finds_a_school_two_headings_spell_together() -> None:
    """Each heading is scrubbed alone, so a school split over two headings stays; the scan reads the path."""
    sent = items_sent("Spending tradeoff", headings=("Cedar", "Ridge budget"))

    assert shown(input_batch_hits("input batch 1", sent, SCAN_NAMES)) == {
        (HitField.HEADINGS, HitKind.SCHOOL, "cedar ridge"): 1,
        (HitField.HEADINGS, HitKind.TOURNAMENT, "cedar ridge"): 1,
    }
    found = name_scan([sent], CASELIST_NAMES, TOURNAMENTS)
    assert (found.schools, found.other_names) == (1, 1)


def cassette(items: str, rationale: str, *, metadata: str = "recorded-model") -> str:
    return json.dumps(
        {
            "call": "generate_structured",
            "caselists": ["hspolicy99"],
            "key": "0" * 64,
            "request": {
                "prompt": {
                    "prompt_id": "landscape.classify_position",
                    "variables": {"items": items, "positions": POSITIONS, "taxonomy_version": "1.0.0"},
                }
            },
            "response": {
                "output": {
                    "answers": [
                        {
                            "item": "item-1",
                            "position_id": "federalism-da",
                            "confidence": 0.8,
                            "rationale": rationale,
                        }
                    ]
                },
                "route": {"model_id": metadata},
            },
        },
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    )


def test_evaluation_scan_finds_a_code_word_in_the_committed_taxonomy_and_a_school_in_a_rationale() -> None:
    """A cassette holds the taxonomy the prompt sent, which the scrub never reads: an ordinary word that is
    also a team code's (`us`) is a hit there, and marked a taxonomy word. A rationale is the model's own."""
    text = cassette(items_sent("Spending tradeoff"), "as cedar ridge reads the us budget")

    hits = cassette_hits("cassette 1", text, SCAN_NAMES)

    assert shown(hits) == {
        (HitField.TAXONOMY, HitKind.TEAM_CODE, "us"): 1,
        (HitField.TAXONOMY, HitKind.TOURNAMENT, "us"): 1,
        (HitField.RATIONALE, HitKind.TEAM_CODE, "us"): 1,
        (HitField.RATIONALE, HitKind.TOURNAMENT, "us"): 1,
        (HitField.RATIONALE, HitKind.SCHOOL, "cedar ridge"): 1,
        (HitField.RATIONALE, HitKind.TOURNAMENT, "cedar ridge"): 1,
    }
    assert {hit.matched for hit in hits if hit.in_taxonomy} == {"us"}
    assert {hit.matched for hit in hits if hit.team_name} == {"us", "cedar ridge"}
    found = name_scan([text], CASELIST_NAMES, TOURNAMENTS)
    assert (found.schools, found.team_codes, found.other_names) == (1, 1, 1)


def test_evaluation_scan_finds_a_name_in_a_cassettes_metadata() -> None:
    text = cassette(items_sent("Spending tradeoff"), "a reason", metadata="kl-model")

    assert shown(
        [hit for hit in cassette_hits("cassette 1", text, SCAN_NAMES) if hit.where is not HitField.TAXONOMY]
    ) == {
        (HitField.METADATA, HitKind.TEAM_CODE, "kl"): 1,
        (HitField.METADATA, HitKind.TOURNAMENT, "kl"): 1,
    }


def test_evaluation_scan_lists_a_repair_cassettes_copy_of_the_failed_prompt() -> None:
    text = json.dumps(
        {
            "caselists": ["hspolicy99"],
            "request": {
                "prompt": {
                    "prompt_id": "model.repair",
                    "variables": {
                        "failed_prompt": "landscape.classify_position@1.0.0",
                        "failed_user": "Cards: the harbor classic survey shows",
                    },
                }
            },
            "response": {"output": {"answers": []}},
        }
    )

    assert shown(repair_cassette_hits("repair cassette 1", text, SCAN_NAMES)) == {
        (HitField.REPAIRED_PROMPT, HitKind.TOURNAMENT, "harbor classic"): 1,
    }


@pytest.mark.parametrize(
    "text",
    [
        '{"a": "maple", "grove": 1}',
        "a maple grove meeting",
        '["kl"]',
        "nothing named here",
        '{"items": "harbor\\nclassic"}',
    ],
)
def test_evaluation_scan_listing_has_a_hit_of_every_kind_the_scan_counts(text: str) -> None:
    """A match no field holds alone is listed across fields, so the listing never shows less than the scan."""
    counted = name_scan([text], CASELIST_NAMES, TOURNAMENTS)
    kinds = {hit.kind for hit in cassette_hits("cassette 1", text, SCAN_NAMES)}

    assert (HitKind.SCHOOL in kinds) >= bool(counted.schools)
    assert (HitKind.TEAM_CODE in kinds) >= bool(counted.team_codes)
    assert (HitKind.TOURNAMENT in kinds) >= bool(counted.other_names)


def test_evaluation_scan_lists_a_match_two_fields_make_together_across_fields() -> None:
    """The scan reads a cassette whole, so a key and a value can spell a school no field holds."""
    hits = cassette_hits("cassette 1", '{"a": "maple", "grove": 1}', SCAN_NAMES)

    assert shown(hits) == {
        (HitField.ACROSS_FIELDS, HitKind.SCHOOL, "maple grove"): 1,
        (HitField.ACROSS_FIELDS, HitKind.TOURNAMENT, "maple grove"): 1,
    }
    assert name_scan(['{"a": "maple", "grove": 1}'], CASELIST_NAMES, TOURNAMENTS).schools == 1


def test_evaluation_scan_hit_counts_are_by_kind_and_field_and_withhold_the_words() -> None:
    sent = items_sent("Spending tradeoff", headings=("Cedar", "Ridge budget"), cite="Harbor Classic Review")
    hits = input_batch_hits("input batch 1", sent, SCAN_NAMES)

    assert hit_counts(hits) == {
        "school": {"heading path": 1},
        "tournament": {"heading path": 1, "short cite": 1},
    }
    shown_repr = "".join(map(repr, hits)) + repr(SCAN_NAMES)
    assert "cedar" not in shown_repr and "harbor" not in shown_repr
