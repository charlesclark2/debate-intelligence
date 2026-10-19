"""The file recipe models (`v1-e33-t01` ac1).

A recipe describes an evidence file to build: its title, topic, format, caselist, position and
side, and a pocket > hat > block > item tree whose items are card references (by E31 exact
fingerprint, with an optional coach-written tag and an optional occurrence pin) or coach-written
analytics. These tests hold the shape: unknown keys, skipped heading levels, empty sections and
blocks outside hats are refused, and nothing in it can carry evidence or cite text.

Every fingerprint, school and team code here is invented (`Maple Grove`, `QX`).
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from debate_core.domain.card_occurrence import CardFingerprint
from debate_core.domain.file_recipe import (
    Analytic,
    Block,
    CardRef,
    FileRecipe,
    Hat,
    OccurrencePin,
    Pocket,
    RecipeStatus,
    TagAuthor,
    TagOverride,
)

FINGERPRINT_A = "a0" * 32
FINGERPRINT_B = "b1" * 32
SOURCE = "c2" * 32


def recipe_data(**overrides: Any) -> dict[str, Any]:
    """A valid LD recipe with hats, as YAML would load it."""
    data: dict[str, Any] = {
        "schema_version": 1,
        "title": "Synthetic NC",
        "topic": "synthetic-topic",
        "format": "LD",
        "caselist": "hsld26",
        "position": "synthetic-position",
        "side": "NEG",
        "fingerprint_version": "card-fingerprint-v3",
        "structure": [
            {
                "pocket": "Framework",
                "hats": [
                    {
                        "hat": "Value",
                        "blocks": [
                            {
                                "block": "Value: morality",
                                "items": [
                                    {"analytic": "Our value comes first."},
                                    {
                                        "fingerprint": FINGERPRINT_A,
                                        "tag_override": "Morality outweighs",
                                        "pin": {
                                            "caselist": "hsld26",
                                            "source_sha256": SOURCE,
                                            "element_index": 12,
                                            "school": "Maple Grove",
                                            "team_code": "QX",
                                        },
                                    },
                                    {"fingerprint": FINGERPRINT_B},
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }
    data.update(overrides)
    return data


def without_hats() -> dict[str, Any]:
    """The same recipe with its block placed straight under the pocket."""
    data = recipe_data()
    pocket = data["structure"][0]
    pocket["blocks"] = pocket.pop("hats")[0]["blocks"]
    return data


def error_locations(data: object) -> list[tuple[str | int, ...]]:
    with pytest.raises(ValidationError) as caught:
        FileRecipe.model_validate(data)
    return [tuple(error["loc"]) for error in caught.value.errors()]


# ------------------------------------------------------------------------------------------------
# What a valid recipe holds
# ------------------------------------------------------------------------------------------------


def test_a_recipe_with_hats_validates_into_its_tree() -> None:
    recipe = FileRecipe.model_validate(recipe_data())

    assert recipe.schema_version == 1
    assert recipe.status is RecipeStatus.READY
    pocket = recipe.structure[0]
    assert isinstance(pocket, Pocket)
    assert pocket.blocks is None
    assert pocket.hats is not None
    hat = pocket.hats[0]
    assert isinstance(hat, Hat)
    block = hat.blocks[0]
    assert isinstance(block, Block)
    analytic, pinned, plain = block.items
    assert analytic == Analytic(analytic="Our value comes first.")
    assert isinstance(pinned, CardRef)
    assert pinned.fingerprint == FINGERPRINT_A
    assert pinned.pin == OccurrencePin(
        caselist="hsld26", source_sha256=SOURCE, element_index=12, school="Maple Grove", team_code="QX"
    )
    assert plain == CardRef(fingerprint=FINGERPRINT_B)


def test_a_recipe_without_hats_validates() -> None:
    recipe = FileRecipe.model_validate(without_hats())
    assert recipe.structure[0].hats is None
    assert recipe.structure[0].blocks is not None


def test_card_refs_are_listed_in_file_order_with_their_locations() -> None:
    recipe = FileRecipe.model_validate(recipe_data())
    assert [(location, ref.fingerprint) for location, ref in recipe.card_refs()] == [
        (("structure", 0, "hats", 0, "blocks", 0, "items", 1), FINGERPRINT_A),
        (("structure", 0, "hats", 0, "blocks", 0, "items", 2), FINGERPRINT_B),
    ]


def test_a_draft_says_so() -> None:
    assert FileRecipe.model_validate(recipe_data(status="draft")).status is RecipeStatus.DRAFT


def test_a_tag_override_is_labeled_coach_authored_and_written_as_its_text() -> None:
    recipe = FileRecipe.model_validate(recipe_data())
    ref = next(ref for _, ref in recipe.card_refs())

    assert ref.tag_override == TagOverride(text="Morality outweighs")
    assert ref.tag_override is not None
    assert ref.tag_override.authored_by is TagAuthor.COACH
    dumped = recipe.model_dump(mode="json")
    assert dumped["structure"][0]["hats"][0]["blocks"][0]["items"][1]["tag_override"] == "Morality outweighs"
    assert FileRecipe.model_validate(dumped) == recipe


# ------------------------------------------------------------------------------------------------
# Unknown keys and skipped heading levels
# ------------------------------------------------------------------------------------------------

BLOCK = ("structure", 0, "hats", 0, "blocks", 0)


@pytest.mark.parametrize(
    "where",
    [
        (),
        ("structure", 0),
        ("structure", 0, "hats", 0),
        BLOCK,
        (*BLOCK, "items", 0),
        (*BLOCK, "items", 1),
        (*BLOCK, "items", 1, "pin"),
    ],
    ids=["recipe", "pocket", "hat", "block", "analytic", "card", "pin"],
)
def test_an_unknown_key_is_refused_at_every_level(where: tuple[str | int, ...]) -> None:
    data = recipe_data()
    node: Any = data
    for part in where:
        node = node[part]
    node["colour"] = "blue"

    with pytest.raises(ValidationError) as caught:
        FileRecipe.model_validate(data)
    (error,) = caught.value.errors()
    assert error["type"] == "extra_forbidden"
    assert error["loc"][-1] == "colour"


HEADING_LEVELS_OUT_OF_PLACE: list[tuple[tuple[str | int, ...], str, object]] = [
    (("structure", 0), "items", [{"analytic": "skips hat and block"}]),
    (("structure", 0, "hats", 0), "items", [{"analytic": "skips the block"}]),
    (BLOCK, "blocks", [{"block": "a block in a block", "items": [{"analytic": "x"}]}]),
    (
        ("structure", 0, "hats", 0),
        "hats",
        [{"hat": "a hat in a hat", "blocks": [{"block": "b", "items": []}]}],
    ),
]


@pytest.mark.parametrize(
    ("where", "key", "value"),
    HEADING_LEVELS_OUT_OF_PLACE,
    ids=["items-in-a-pocket", "items-in-a-hat", "block-in-a-block", "hat-in-a-hat"],
)
def test_a_skipped_or_repeated_heading_level_is_refused(
    where: tuple[str | int, ...], key: str, value: object
) -> None:
    data = recipe_data()
    node: Any = data
    for part in where:
        node = node[part]
    node[key] = value

    assert (*where, key) in error_locations(data)


def test_a_block_beside_the_hats_of_its_own_pocket_is_refused() -> None:
    data = recipe_data()
    data["structure"][0]["blocks"] = [{"block": "outside any hat", "items": [{"analytic": "x"}]}]

    assert error_locations(data) == [("structure", 0, "blocks")]


def test_a_pocket_without_hats_in_a_recipe_that_declares_hats_is_refused() -> None:
    data = recipe_data()
    data["structure"].append(
        {"pocket": "Second", "blocks": [{"block": "no hat", "items": [{"analytic": "x"}]}]}
    )

    assert error_locations(data) == [("structure", 1, "blocks")]


def _no_pockets(data: dict[str, Any]) -> None:
    data["structure"] = []


def _pocket_with_nothing(data: dict[str, Any]) -> None:
    del data["structure"][0]["hats"]


def _empty_hats(data: dict[str, Any]) -> None:
    data["structure"][0]["hats"] = []


def _hat_without_blocks(data: dict[str, Any]) -> None:
    data["structure"][0]["hats"][0]["blocks"] = []


def _block_without_items(data: dict[str, Any]) -> None:
    data["structure"][0]["hats"][0]["blocks"][0]["items"] = []


EMPTY_SECTIONS: list[tuple[Callable[[dict[str, Any]], None], tuple[str | int, ...]]] = [
    (_no_pockets, ("structure",)),
    (_pocket_with_nothing, ("structure", 0)),
    (_empty_hats, ("structure", 0, "hats")),
    (_hat_without_blocks, ("structure", 0, "hats", 0, "blocks")),
    (_block_without_items, (*BLOCK, "items")),
]


@pytest.mark.parametrize(
    ("change", "expected"),
    EMPTY_SECTIONS,
    ids=["no-pockets", "pocket-with-nothing", "empty-hats", "hat-without-blocks", "block-without-items"],
)
def test_an_empty_section_is_refused(
    change: Callable[[dict[str, Any]], None], expected: tuple[str | int, ...]
) -> None:
    data = recipe_data()
    change(data)

    assert error_locations(data) == [expected]


def test_an_item_that_is_neither_card_nor_analytic_is_refused() -> None:
    data = recipe_data()
    data["structure"][0]["hats"][0]["blocks"][0]["items"].append({"heading": "not an item"})

    assert error_locations(data) == [(*BLOCK, "items", 3)]


# ------------------------------------------------------------------------------------------------
# Fields
# ------------------------------------------------------------------------------------------------


def test_the_fingerprint_is_e31_t04s_exact_fingerprint_type() -> None:
    """The recipe imports the definition the occurrence store uses, rather than restating it."""
    recipe_field = CardRef.model_fields["fingerprint"]
    e31_field = CardFingerprint.model_fields["exact_fingerprint"]
    assert recipe_field.annotation is e31_field.annotation
    assert recipe_field.metadata == e31_field.metadata


@pytest.mark.parametrize(
    "fingerprint",
    ["A0" * 32, "a0" * 31 + "a", "a0" * 33, "g0" * 32, "", 12345],
    ids=["uppercase", "63-characters", "66-characters", "not-hex", "empty", "a-number"],
)
def test_a_fingerprint_not_in_the_e31_format_is_refused(fingerprint: object) -> None:
    data = recipe_data()
    data["structure"][0]["hats"][0]["blocks"][0]["items"][2]["fingerprint"] = fingerprint

    assert error_locations(data) == [(*BLOCK, "items", 2, "card", "fingerprint")]


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("tag_override", ""),
        ("tag_override", "   "),
        ("tag_override", "x" * 601),
        ("tag_override", {"text": "a mapping, not the coach's tag"}),
        ("analytic", ""),
        ("analytic", "y" * 2001),
    ],
    ids=["empty-tag", "blank-tag", "tag-too-long", "tag-as-mapping", "empty-analytic", "analytic-too-long"],
)
def test_coach_text_is_bounded(field_name: str, value: object) -> None:
    data = recipe_data()
    items = data["structure"][0]["hats"][0]["blocks"][0]["items"]
    index = 1 if field_name == "tag_override" else 0
    items[index][field_name] = value

    kind = "card" if field_name == "tag_override" else "analytic"
    assert error_locations(data) == [(*BLOCK, "items", index, kind, field_name)]


def test_the_longest_coach_text_allowed_validates() -> None:
    data = recipe_data()
    items = data["structure"][0]["hats"][0]["blocks"][0]["items"]
    items[0]["analytic"] = "y" * 2000
    items[1]["tag_override"] = "x" * 600
    FileRecipe.model_validate(data)


@pytest.mark.parametrize(
    ("event", "side"),
    [("PF", "AFF"), ("PF", "NEG"), ("LD", "PRO"), ("POLICY", "CON"), ("LD", "UNKNOWN")],
)
def test_the_side_is_one_the_format_debates(event: str, side: str) -> None:
    assert error_locations(recipe_data(format=event, side=side)) == [("side",)]


@pytest.mark.parametrize(("event", "side"), [("PF", "PRO"), ("PF", "CON"), ("POLICY", "AFF"), ("LD", "NEG")])
def test_each_format_takes_its_own_sides(event: str, side: str) -> None:
    FileRecipe.model_validate(recipe_data(format=event, side=side))


@pytest.mark.parametrize("version", [2, 0, "1", True, 1.0, None])
def test_only_schema_version_1_is_read(version: object) -> None:
    assert error_locations(recipe_data(schema_version=version)) == [("schema_version",)]


def test_schema_version_is_required() -> None:
    data = recipe_data()
    del data["schema_version"]
    assert error_locations(data) == [("schema_version",)]


@pytest.mark.parametrize("field_name", ["topic", "position"])
@pytest.mark.parametrize("value", ["Not Kebab", "trailing-", "-leading", "two--hyphens", "under_score", ""])
def test_topic_and_position_are_kebab_case_ids(field_name: str, value: str) -> None:
    assert error_locations(recipe_data(**{field_name: value})) == [(field_name,)]


@pytest.mark.parametrize("caselist", ["openev", "HSLD26", "hsld2026", "hsld"])
def test_the_caselist_is_a_caselist_slug(caselist: str) -> None:
    assert error_locations(recipe_data(caselist=caselist)) == [("caselist",)]


@pytest.mark.parametrize("title", ["", "   "])
def test_a_title_is_required_text(title: str) -> None:
    assert error_locations(recipe_data(title=title)) == [("title",)]


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("element_index", -1),
        ("element_index", True),
        ("element_index", "12"),
        ("element_index", 1.5),
        ("source_sha256", "C2" * 32),
        ("caselist", "openev"),
        ("team_code", "Jane Rivera"),
        ("school", ""),
        ("snapshot", "last week"),
        ("side", "BOTH"),
        ("round", ""),
    ],
)
def test_a_pin_holds_only_what_an_occurrence_can_match(field_name: str, value: object) -> None:
    data = recipe_data()
    data["structure"][0]["hats"][0]["blocks"][0]["items"][1]["pin"][field_name] = value

    assert error_locations(data) == [(*BLOCK, "items", 1, "card", "pin", field_name)]


@pytest.mark.parametrize("missing", ["caselist", "source_sha256", "element_index"])
def test_a_pin_names_its_store_its_source_and_its_paragraph(missing: str) -> None:
    data = recipe_data()
    del data["structure"][0]["hats"][0]["blocks"][0]["items"][1]["pin"][missing]

    assert error_locations(data) == [(*BLOCK, "items", 1, "card", "pin", missing)]


def test_a_pin_takes_every_disclosure_field_it_can_be_narrowed_by() -> None:
    data = recipe_data()
    data["structure"][0]["hats"][0]["blocks"][0]["items"][1]["pin"].update(
        snapshot="2026-09-15", side="NEG", tournament="Invented Invitational", round="Round 4"
    )
    pin = next(ref for _, ref in FileRecipe.model_validate(data).card_refs()).pin
    assert pin is not None
    assert pin.snapshot is not None and pin.snapshot.isoformat() == "2026-09-15"
    assert (pin.side, pin.tournament, pin.round) == ("NEG", "Invented Invitational", "Round 4")


def test_a_pin_keeps_who_disclosed_the_card_out_of_its_repr() -> None:
    """A team code is personal data about a minor: never in a log line (caselist-data-use.md, rule 4)."""
    pin = OccurrencePin(
        caselist="hsld26",
        source_sha256=SOURCE,
        element_index=1,
        school="Maple Grove",
        team_code="QX",
        tournament="Invented Invitational",
        round="Round 4",
    )
    recipe = FileRecipe.model_validate(recipe_data())
    for text in (repr(pin), repr(recipe), str(recipe)):
        for word in ("Maple Grove", "'QX'", "Invented", "Round 4"):
            assert word not in text


# ------------------------------------------------------------------------------------------------
# Every error at once, and nothing that could hold evidence
# ------------------------------------------------------------------------------------------------


def test_every_error_in_the_tree_is_reported_together() -> None:
    data = recipe_data(format="PF", side="AFF", colour="blue")
    data["structure"][0]["hats"][0]["blocks"][0]["items"][2]["fingerprint"] = "nope"
    data["structure"][0]["hats"][0]["blocks"][0]["items"][1]["pin"]["element_index"] = -3
    data["structure"].append(
        {"pocket": "Second", "blocks": [{"block": "no hat", "items": [{"analytic": "x"}]}]}
    )
    data["structure"].append({"pocket": "Third", "hats": [{"hat": "empty", "blocks": []}]})

    assert sorted(error_locations(data), key=str) == sorted(
        [
            ("side",),
            ("colour",),
            (*BLOCK, "items", 2, "card", "fingerprint"),
            (*BLOCK, "items", 1, "card", "pin", "element_index"),
            ("structure", 1, "blocks"),
            ("structure", 2, "hats", 0, "blocks"),
        ],
        key=str,
    )


EVIDENCE_SHAPED_NAMES = {
    "evidence",
    "evidence_text",
    "card_text",
    "body",
    "text_of_card",
    "quote",
    "cite",
    "full_cite",
    "short_cite",
    "citation",
}


def _field_names(model: type[BaseModel], seen: set[type[BaseModel]]) -> set[str]:
    if model in seen:
        return set()
    seen.add(model)
    names = set(model.model_fields)
    for nested in (Pocket, Hat, Block, CardRef, Analytic, OccurrencePin, TagOverride):
        if nested is not model:
            names |= _field_names(nested, seen)
    return names


def test_no_recipe_field_can_carry_evidence_or_cite_text() -> None:
    """The task's first forbidden item: evidence and cites are copied from the source by t02."""
    assert _field_names(FileRecipe, set()) & EVIDENCE_SHAPED_NAMES == set()


def test_the_valid_fixture_is_not_mutated_by_validation() -> None:
    data = recipe_data()
    before = copy.deepcopy(data)
    FileRecipe.model_validate(data)
    assert data == before
