"""The deterministic position matcher (`v1-e32-t02-position-classification` ac1).

The labeled set (`tests/fixtures/landscape/labeled_items.yaml`) holds at least 20 alias-carrying
cards per format, Policy, LD and PF, each labeled by hand with its position, role and method. The
matcher must get every one right, AT:/A2 headings must give ANSWERS, and no model is called: the
modules that classify import no model router at all, so there is no router to call.

The rules beside it are each pinned on their own: the nearest placed heading wins, an override is
read before an alias, an answer heading above the placing one makes the role ANSWERS, tag keywords
refine a parent and never choose between two children, a heading that matches nothing stays
unplaced, and a rationale never repeats a team's heading or tag.

Every taxonomy, heading, tag, school and team code here is invented.
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

from debate_core.arguments.landscape.matcher import (
    TAG_KEYWORD_ALONE_CONFIDENCE,
    MatchItem,
    PositionMatcher,
    read_items,
)
from debate_core.arguments.landscape.seeding import SeedCard, SeedSource, SeedTeam
from debate_core.arguments.landscape.source_headings import CaselistNames
from debate_core.domain.caselist import Side
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import (
    ClassificationMethod,
    ClassificationResult,
    ItemKind,
    OverrideRules,
    PositionRole,
    card_item_id,
)

REPO = Path(__file__).resolve().parents[5]
LABELED = REPO / "tests" / "fixtures" / "landscape" / "labeled_items.yaml"
CLASSIFYING_MODULES = (
    REPO / "packages/debate_core/src/debate_core/arguments/landscape/matcher.py",
    REPO / "packages/debate_core/src/debate_core/arguments/landscape/review_queue.py",
    REPO / "packages/debate_core/src/debate_core/application/position_classification.py",
)


# ------------------------------------------------------------------------------------------------
# The labeled set
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Labeled:
    event: str
    document: str
    index: int
    path: tuple[str, ...]
    carries_alias: bool
    expected: tuple[str | None, str | None, str | None]


@dataclass(frozen=True)
class Format:
    event: str
    matcher: PositionMatcher
    names: CaselistNames
    sources: tuple[SeedSource, ...]
    labels: dict[str, Labeled]


def load_formats() -> list[Format]:
    document = yaml.safe_load(LABELED.read_text(encoding="utf-8"))
    formats: list[Format] = []
    for block in document["formats"]:
        taxonomy = Taxonomy.model_validate(block["taxonomy"])
        overrides = OverrideRules.model_validate(
            {"topic_id": taxonomy.topic_id, "overrides": block["overrides"]}
        )
        sources: list[SeedSource] = []
        labels: dict[str, Labeled] = {}
        for number, planted in enumerate(block["documents"]):
            sha = f"{number + 1:x}{block['event'][0].lower()}".rjust(64, "0")
            cards: list[SeedCard] = []
            for index, card in enumerate(planted["cards"]):
                cards.append(
                    SeedCard(tag=card["tag"], section_path=tuple(card["path"]), first_element_index=index * 3)
                )
                expected = card["expect"]
                labels[card_item_id(sha, index * 3)] = Labeled(
                    event=block["event"],
                    document=planted["name"],
                    index=index,
                    path=tuple(card["path"]),
                    carries_alias=card["carries_alias"],
                    expected=(expected["position"], expected["role"], expected["method"]),
                )
            team = SeedTeam(identity=planted["name"], side=Side.AFF, names=tuple(planted["team_names"]))
            sources.append(SeedSource(sha256=sha, teams=(team,), cards=tuple(cards)))
        formats.append(
            Format(
                event=block["event"],
                matcher=PositionMatcher(taxonomy, overrides),
                names=CaselistNames(block["caselist_schools"]),
                sources=tuple(sources),
                labels=labels,
            )
        )
    return formats


FORMATS = load_formats()


def placed_cards(one: Format) -> dict[str, tuple[MatchItem, ClassificationResult]]:
    found: dict[str, tuple[MatchItem, ClassificationResult]] = {}
    for source in one.sources:
        for item in read_items(source, one.names):
            if item.kind is ItemKind.CARD:
                found[item.item_id] = (item, one.matcher.place(item))
    return found


def as_label(result: ClassificationResult) -> tuple[str | None, str | None, str | None]:
    return (
        result.position_id,
        None if result.role is None else result.role.value,
        None if result.method is None else result.method.value,
    )


def test_the_labeled_set_has_at_least_20_alias_carrying_items_per_format() -> None:
    counts = {one.event: sum(label.carries_alias for label in one.labels.values()) for one in FORMATS}
    assert set(counts) == {"POLICY", "LD", "PF"}
    assert all(count >= 20 for count in counts.values()), counts


@pytest.mark.parametrize("one", FORMATS, ids=lambda one: one.event)
def test_the_deterministic_stage_places_every_labeled_item_as_labeled(one: Format) -> None:
    placed = placed_cards(one)
    assert set(placed) == set(one.labels)
    wrong = [
        f"{label.document} card {label.index} {label.path}: expected {label.expected}, got {as_label(placed[item_id][1])}"
        for item_id, label in one.labels.items()
        if as_label(placed[item_id][1]) != label.expected
    ]
    assert wrong == []
    alias_items = [item_id for item_id, label in one.labels.items() if label.carries_alias]
    accuracy = sum(as_label(placed[item_id][1]) == one.labels[item_id].expected for item_id in alias_items)
    assert accuracy / len(alias_items) == 1.0


@pytest.mark.parametrize("one", FORMATS, ids=lambda one: one.event)
def test_answer_headings_give_answers_and_only_they_do(one: Format) -> None:
    placed = placed_cards(one)
    answers = [
        label for item_id, label in one.labels.items() if placed[item_id][1].role is PositionRole.ANSWERS
    ]
    assert answers, "each format's set holds answers"
    for label in answers:
        assert any(heading.upper().startswith(("AT", "A2")) for heading in label.path), label


def test_every_method_is_exercised_by_the_labeled_set() -> None:
    methods = Counter(label.expected[2] for one in FORMATS for label in one.labels.values())
    assert {"ALIAS", "INHERITED", "TAG_KEYWORD", "OVERRIDE", None} <= set(methods)


def test_no_module_that_classifies_imports_a_model_router() -> None:
    for path in CLASSIFYING_MODULES:
        imported: list[str] = []
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported += [node.module, *(f"{node.module}.{alias.name}" for alias in node.names)]
            elif isinstance(node, ast.Import):
                imported += [alias.name for alias in node.names]
        routers = [name for name in imported if "model_router" in name or name.endswith("ModelRouter")]
        assert routers == [], f"{path.name} imports {routers}"


# ------------------------------------------------------------------------------------------------
# The rules, one at a time
# ------------------------------------------------------------------------------------------------

SHA = "c" * 64


def taxonomy(*positions: dict[str, Any]) -> Taxonomy:
    return Taxonomy.model_validate(
        {
            "topic_id": "policy-sample-topic",
            "taxonomy_version": "1.0.0",
            "event": "POLICY",
            "positions": list(positions),
        }
    )


def position(position_id: str, *aliases: str, **fields: Any) -> dict[str, Any]:
    return {
        "id": position_id,
        "label": "Invented",
        "kind": "da",
        "side": "neg",
        "aliases": list(aliases),
        **fields,
    }


SAMPLE = taxonomy(
    position("spending-da", "spending da"),
    position("politics-da", "politics da"),
    position("states-cp", "states cp", kind="cp"),
    position("sample-aff", "sample plan", kind="aff", side="aff"),
    position("public-aff", kind="aff", side="aff", parent="sample-aff", tag_keywords=["Public Plan"]),
    position("rural-public-aff", kind="aff", side="aff", parent="public-aff", tag_keywords=["rural"]),
)


def matcher(*rules: tuple[str, str | None], on: Taxonomy = SAMPLE) -> PositionMatcher:
    return PositionMatcher(
        on,
        OverrideRules.model_validate(
            {
                "topic_id": on.topic_id,
                "overrides": [{"heading": heading, "position_id": target} for heading, target in rules],
            }
        ),
    )


def one_card(
    path: tuple[str, ...], tag: str | None = "An invented claim", *, names: tuple[str, ...] = ()
) -> MatchItem:
    source = SeedSource(
        sha256=SHA,
        teams=(SeedTeam(identity="one", side=Side.NEG, names=names),),
        cards=(SeedCard(tag=tag, section_path=path, first_element_index=7),),
    )
    (card,) = [item for item in read_items(source, CaselistNames({})) if item.kind is ItemKind.CARD]
    return card


def placed(
    path: tuple[str, ...], tag: str | None = "An invented claim", **kwargs: Any
) -> ClassificationResult:
    return matcher(*kwargs.pop("rules", ())).place(one_card(path, tag, **kwargs))


def test_the_nearest_placed_heading_wins() -> None:
    result = placed(("Spending DA", "Politics DA", "Link"))
    assert (result.position_id, result.method) == ("politics-da", ClassificationMethod.INHERITED)


def test_inheritance_reaches_the_outermost_heading() -> None:
    result = placed(("Spending DA", "Uniqueness", "Link"))
    assert (result.position_id, result.method, result.confidence) == (
        "spending-da",
        ClassificationMethod.INHERITED,
        0.9,
    )
    assert "heading 1 of 3" in result.rationale


def test_a_heading_directly_over_the_item_is_an_alias_match() -> None:
    result = placed(("Uniqueness", "Spending DA"))
    assert (result.position_id, result.method, result.confidence) == (
        "spending-da",
        ClassificationMethod.ALIAS,
        1.0,
    )


def test_an_override_is_read_before_an_alias() -> None:
    result = placed(("Spending DA",), rules=[("spending da", "politics-da")])
    assert (result.position_id, result.method) == ("politics-da", ClassificationMethod.OVERRIDE)


def test_an_override_further_up_is_inherited() -> None:
    result = placed(("Fed Key", "Link"), rules=[("fed key", "states-cp")])
    assert (result.position_id, result.method) == ("states-cp", ClassificationMethod.INHERITED)
    assert "override of 'fed key'" in result.rationale


def test_a_nearer_override_beats_an_alias_further_up() -> None:
    result = placed(("Spending DA", "Fed Key"), rules=[("fed key", "states-cp")])
    assert (result.position_id, result.method) == ("states-cp", ClassificationMethod.OVERRIDE)


def test_a_heading_ruled_no_position_is_passed_over() -> None:
    result = placed(("Spending DA", "Link"), rules=[("link", None)])
    assert (result.position_id, result.method) == ("spending-da", ClassificationMethod.INHERITED)


def test_an_item_under_only_headings_ruled_no_position_is_decided() -> None:
    result = placed(("Link", "Impact"), rules=[("link", None), ("impact", None)])
    assert (result.position_id, result.method, result.confidence) == (
        None,
        ClassificationMethod.OVERRIDE,
        1.0,
    )


def test_one_undecided_heading_leaves_the_item_unplaced() -> None:
    result = placed(("Fed Key", "Link"), rules=[("link", None)])
    assert (result.position_id, result.method, result.confidence) == (None, None, 0.0)


def test_an_answer_heading_above_the_placing_one_answers() -> None:
    result = placed(("AT: DAs", "Spending DA", "Link"))
    assert (result.position_id, result.role) == ("spending-da", PositionRole.ANSWERS)


def test_an_answer_heading_below_the_placing_one_reads() -> None:
    result = placed(("Spending DA", "AT: Link Turn"))
    assert (result.position_id, result.role) == ("spending-da", PositionRole.READS)


def test_the_placing_answer_heading_answers() -> None:
    for path in (
        ("AT: Spending DA",),
        ("A2 Spending DA",),
        ("A/T Spending DA",),
        ("Answers to Spending DA",),
    ):
        result = placed(path)
        assert (result.position_id, result.role) == ("spending-da", PositionRole.ANSWERS), path


def test_tag_keywords_refine_down_the_children() -> None:
    result = placed(("Sample Plan",), "A public plan reaches rural clinics")
    assert (result.position_id, result.method, result.confidence) == (
        "rural-public-aff",
        ClassificationMethod.TAG_KEYWORD,
        0.9,
    )


def test_tag_keywords_stop_at_the_parent_without_one() -> None:
    result = placed(("Sample Plan",), "Clinics close")
    assert (result.position_id, result.method) == ("sample-aff", ClassificationMethod.ALIAS)


def test_a_keyword_is_matched_as_whole_words() -> None:
    result = placed(("Sample Plan",), "Republican plans fail")
    assert result.position_id == "sample-aff"


def test_two_children_named_leave_the_card_with_the_parent() -> None:
    two = taxonomy(
        position("sample-aff", "sample plan", kind="aff", side="aff"),
        position("one-aff", kind="aff", side="aff", parent="sample-aff", tag_keywords=["vouchers"]),
        position("two-aff", kind="aff", side="aff", parent="sample-aff", tag_keywords=["public plan"]),
    )
    result = matcher(on=two).place(one_card(("Sample Plan",), "A public plan beats vouchers"))
    assert (result.position_id, result.method) == ("sample-aff", ClassificationMethod.ALIAS)


def test_tag_keywords_alone_place_below_the_review_threshold() -> None:
    result = placed(("Fiscal Cliff DA",), "A rural public plan")
    assert (result.position_id, result.method, result.confidence) == (
        "rural-public-aff",
        ClassificationMethod.TAG_KEYWORD,
        TAG_KEYWORD_ALONE_CONFIDENCE,
    )
    assert TAG_KEYWORD_ALONE_CONFIDENCE < 0.6


def test_tag_keywords_of_two_unrelated_positions_place_nothing() -> None:
    two = taxonomy(
        position("one-da", tag_keywords=["midterm"]),
        position("two-da", tag_keywords=["deficit"]),
    )
    result = matcher(on=two).place(one_card(("Fiscal Cliff DA",), "The deficit swings the midterm"))
    assert (result.position_id, result.method) == (None, None)
    assert matcher(on=two).candidates(one_card(("Fiscal Cliff DA",), "The deficit swings the midterm")) == (
        "one-da",
        "two-da",
    )


@pytest.mark.parametrize(
    "path",
    [("Fiscal Cliff DA",), ("Spendings DA",), ("Spending",), ("Sample School DA",), ("Sp DA",)],
)
def test_a_heading_matching_no_alias_stays_unplaced(path: tuple[str, ...]) -> None:
    result = placed(path, "No keyword here")
    assert (result.position_id, result.role, result.method) == (None, None, None)
    assert result.rationale == "no heading over it is an alias or an override"


def test_an_item_under_no_heading_is_unplaced() -> None:
    assert placed(("1NC",)).rationale == "it sits under no heading"


def test_a_retired_alias_counts_under_its_successor_and_one_with_none_places_nothing() -> None:
    retired = taxonomy(
        position("states-cp", "states cp", kind="cp"),
        position("fed-cp", "fed cp", kind="cp", deprecated=True, merged_into="states-cp"),
        position("old-k", "old k", kind="k", deprecated=True),
    )
    assert matcher(on=retired).place(one_card(("Fed CP",))).position_id == "states-cp"
    assert matcher(on=retired).place(one_card(("Old K",))).position_id is None


def test_an_override_naming_a_retired_position_counts_under_its_successor() -> None:
    retired = taxonomy(
        position("states-cp", "states cp", kind="cp"),
        position("fed-cp", kind="cp", deprecated=True, merged_into="states-cp"),
    )
    assert matcher(("fed key", "fed-cp"), on=retired).place(one_card(("Fed Key",))).position_id == "states-cp"


def test_the_matcher_refuses_overrides_naming_no_position() -> None:
    with pytest.raises(ValueError, match="not a position"):
        matcher(("fed key", "medicaid-da"))


def test_the_disclosing_teams_names_are_taken_out_before_matching() -> None:
    result = placed(("Harbor Point Spending DA",), names=("Harbor Point", "HP"))
    assert (result.position_id, result.method) == ("spending-da", ClassificationMethod.ALIAS)


# ------------------------------------------------------------------------------------------------
# Items, fingerprints and what a result may say
# ------------------------------------------------------------------------------------------------


def test_a_source_gives_one_section_per_heading_path_and_one_item_per_card() -> None:
    source = SeedSource(
        sha256=SHA,
        teams=(),
        cards=(
            SeedCard(tag="One", section_path=("1NC", "Spending DA"), first_element_index=3),
            SeedCard(tag="Two", section_path=("1NC", "Spending DA"), first_element_index=9),
            SeedCard(tag=None, section_path=("1NC", "Spending DA", "Two"), first_element_index=12),
            SeedCard(tag="Three", section_path=("1NC", "States CP"), first_element_index=15),
        ),
    )
    items = read_items(source, CaselistNames({}))
    kinds = [item.kind for item in items]
    assert kinds == [ItemKind.SECTION] * 3 + [ItemKind.CARD] * 4
    assert [item.first_element_index for item in items if item.kind is ItemKind.CARD] == [3, 9, 12, 15]
    sections = [matcher().place(item) for item in items if item.kind is ItemKind.SECTION]
    assert [(result.position_id, result.method) for result in sections] == [
        (None, None),
        ("spending-da", ClassificationMethod.ALIAS),
        ("states-cp", ClassificationMethod.ALIAS),
    ]


def test_a_card_with_no_first_paragraph_is_a_reader_bug() -> None:
    source = SeedSource(sha256=SHA, teams=(), cards=(SeedCard(tag="One", section_path=("Spending DA",)),))
    with pytest.raises(ValueError, match="first paragraph"):
        read_items(source, CaselistNames({}))


def test_items_read_alike_share_a_fingerprint() -> None:
    plain = one_card(("1NC", "Spending DA"), "Deficits rise!")
    assert one_card(("2NC — Spending DA Shell",), "deficits RISE").fingerprint == plain.fingerprint
    assert one_card(("Harbor Point Spending DA",), "Deficits rise", names=("Harbor Point",)).fingerprint == (
        plain.fingerprint
    )
    assert one_card(("AT: Spending DA",), "Deficits rise").fingerprint != plain.fingerprint
    assert one_card(("1NC", "Spending DA"), "Deficits fall").fingerprint != plain.fingerprint
    assert one_card(("1NC", "Spending DA"), None).fingerprint != plain.fingerprint


def test_an_item_withholds_its_headings_and_tag() -> None:
    shown = repr(one_card(("Harbor Point Spending DA",), "A secret claim"))
    assert "spending" not in shown.casefold() and "secret" not in shown.casefold()


@pytest.mark.parametrize("one", FORMATS, ids=lambda one: one.event)
def test_no_rationale_repeats_a_teams_heading_tag_or_name(one: Format) -> None:
    taxonomy = one.matcher.taxonomy
    committed = {alias for position in taxonomy.positions for alias in position.aliases}
    committed |= {keyword.casefold() for position in taxonomy.positions for keyword in position.tag_keywords}
    committed |= {rule.heading for rule in one.matcher.overrides.overrides}
    checked = 0
    for source in one.sources:
        names = [name.casefold() for team in source.teams for name in team.names]
        tags = {card.first_element_index: card.tag for card in source.cards}
        for item in read_items(source, one.names):
            rationale = one.matcher.place(item).rationale.casefold()
            for heading in one.matcher.undecided_headings(item):
                if heading.text not in committed:
                    assert f"'{heading.text}'" not in rationale
                    checked += 1
            for name in names:
                assert name not in re.findall(r"[0-9a-z]+", rationale), name
            tag = tags.get(item.first_element_index)
            if item.kind is ItemKind.CARD and tag is not None:
                assert tag.casefold() not in rationale
    assert checked


def test_candidates_share_a_word_that_is_not_a_kind_word() -> None:
    assert matcher().candidates(one_card(("Spending Tradeoff",))) == ("spending-da",)
    assert matcher().candidates(one_card(("Fiscal DA",))) == ()


def test_the_override_digest_names_only_the_items_headings() -> None:
    rules = matcher(("fed key", "states-cp"))
    assert rules.override_digest(one_card(("Spending DA",))) == "none"
    assert rules.override_digest(one_card(("Fed Key", "Link"))) != "none"
