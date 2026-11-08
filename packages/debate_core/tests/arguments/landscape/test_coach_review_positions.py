"""The three positions of the coach's review (`v1-e32-t41`) place their own headings and take no other's.

The Policy taxonomy as committed, with the coach's overrides, places one invented card under each heading
path below. The new aliases are the headings two or more teams use for each position on the dev store;
the paths under another position hold the headings counted beside them and left out (the task's session
report), each under the heading that places it today, so an alias that took one of them moves its card.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from debate_core.arguments.landscape.matcher import PositionMatcher, read_items
from debate_core.arguments.landscape.seeding import SeedCard, SeedSource, SeedTeam
from debate_core.arguments.landscape.source_headings import CaselistNames
from debate_core.domain.caselist import Side
from debate_core.domain.landscape_classification import ItemKind
from debate_core.integrations.landscape.yaml_taxonomy_repository import YamlTaxonomyRepository

REPOSITORY = Path(__file__).resolve().parents[5]
TOPIC = "policy-2026-27-nhi"

PLACED: tuple[tuple[tuple[str, ...], str], ...] = (
    (("Adv Health Profiteering",), "health-profiteering-advantage"),
    (("Healthcare Profiteering Advantage",), "health-profiteering-advantage"),
    (("Single Payer", "Health Profiteering"), "health-profiteering-advantage"),
    (("1NC Free Market CP Shell",), "free-market-cp"),
    (("CP Markets",), "free-market-cp"),
    (("Federalism CP",), "federalism-cp"),
    (("CP Federalism",), "federalism-cp"),
    # Left where they are: the states CP and its net benefit,
    (("States CP",), "states-cp"),
    (("States",), "states-cp"),
    (("States CP", "Federalism DA Spillover"), "states-cp"),
    # the federalism DA, and the optional legislation CP's federalism net benefit,
    (("Federalism DA", "Federalism"), "federalism-da"),
    (("Optional Legislation CP", "Federalism CP Key"), "optional-legislation-cp"),
    (("Optional Legislation CP", "Federalism Impact"), "optional-legislation-cp"),
    # the cap K's answers about markets and competition, and the costs advantage's own blocks.
    (("Cap K", "Markets Good"), "cap-k"),
    (("Cap K", "Competition"), "cap-k"),
    (("Costs Advantage", "Profiteering"), "costs-advantage"),
)


@pytest.fixture(scope="module")
def placed() -> dict[tuple[str, ...], str | None]:
    repository = YamlTaxonomyRepository.load(REPOSITORY / "config" / "landscape")
    matcher = PositionMatcher(repository.taxonomy(TOPIC), repository.overrides(TOPIC))
    source = SeedSource(
        sha256="f" * 64,
        teams=(SeedTeam(identity="invented/zz", side=Side.NEG),),
        cards=tuple(
            SeedCard(tag=None, section_path=path, first_element_index=index)
            for index, (path, _) in enumerate(PLACED)
        ),
    )
    cards = [item for item in read_items(source, CaselistNames({})) if item.kind is ItemKind.CARD]
    return {path: matcher.place(item).position_id for (path, _), item in zip(PLACED, cards, strict=True)}


@pytest.mark.parametrize(("path", "position"), PLACED, ids=[" > ".join(path) for path, _ in PLACED])
def test_each_heading_path_is_placed_under_its_position(
    placed: dict[tuple[str, ...], str | None], path: tuple[str, ...], position: str
) -> None:
    assert placed[path] == position


def test_the_three_positions_are_active_with_their_kind_side_and_a_description() -> None:
    taxonomy = YamlTaxonomyRepository.load(REPOSITORY / "config" / "landscape").taxonomy(TOPIC)
    active = {one.id: one for one in taxonomy.active_positions}

    assert {
        position: (
            active[position].kind.value,
            active[position].side.value,
            bool(active[position].description),
        )
        for position in ("health-profiteering-advantage", "free-market-cp", "federalism-cp")
    } == {
        "health-profiteering-advantage": ("advantage", "aff", True),
        "free-market-cp": ("cp", "neg", True),
        "federalism-cp": ("cp", "neg", True),
    }
    assert taxonomy.taxonomy_version == "1.5.1"
