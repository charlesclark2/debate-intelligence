"""The chain-role and scenario rules (`v1-e32-t14`), as the PM ruled them on 2026-10-25, and the coach's
scenario lists (`v1-e32-t22`).

Every case is a heading or tag as the normalizer and `tag_words` write them, with the answer the
ruling gives, written by hand.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from debate_core.arguments.landscape.link_chains import (
    CardScenario,
    SubHeading,
    card_roles,
    card_scenario,
    caselist_words,
    heading_roles,
    is_withheld,
    scenario_name,
    tag_role,
)
from debate_core.domain.landscape import Position, PositionKind
from debate_core.domain.landscape_report import ChainRole
from debate_core.testing.landscape_report import read_synthetic_caselist

FIXTURE = Path(__file__).resolve().parents[5] / "tests" / "fixtures" / "landscape" / "synthetic_caselist"
DA, ADVANTAGE = PositionKind.DA, PositionKind.ADVANTAGE
U, L, IL, IMP = ChainRole.UNIQUENESS, ChainRole.LINK, ChainRole.INTERNAL_LINK, ChainRole.IMPACT
H, INH, S = ChainRole.HARMS, ChainRole.INHERENCY, ChainRole.SOLVENCY
NOTHING: frozenset[ChainRole] = frozenset()


def _sub(*texts: str, answers: tuple[int, ...] = ()) -> tuple[SubHeading, ...]:
    return tuple(SubHeading(text, index in answers) for index, text in enumerate(texts))


# ------------------------------------------------------------------------------------------------
# Headings
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("heading", "roles"),
    [
        ("u", {U}),
        ("u us lead", {U}),
        ("uq", {U}),
        ("uq costs", {U}),
        ("dems win uq", {U}),
        ("uniqueness", {U}),
        ("u s lead", NOTHING),
        ("u s", NOTHING),
        ("non unique", NOTHING),
        ("link", {L}),
        ("links", {L}),
        ("link single payer", {L}),
        ("jobs links", {L}),
        ("l", {L}),
        ("l single payer", {L}),
        ("single payer l", NOTHING),
        ("l t", NOTHING),
        ("lt", NOTHING),
        ("link turn", NOTHING),
        ("link turns", NOTHING),
        ("no link", NOTHING),
        ("link defense", NOTHING),
        ("internal link", {IL}),
        ("internal links", {IL}),
        ("internal", {IL}),
        ("dome internal", {IL}),
        ("internals", {IL}),
        ("il", {IL}),
        ("i l", {IL}),
        ("impact", {IMP}),
        ("dome impact", {IMP}),
        ("turns case", {IMP}),
        ("no impact", NOTHING),
        ("impact defense", NOTHING),
        ("impact turns", NOTHING),
        ("link impact", {L, IMP}),
        ("u and link", {U, L}),
        ("dome", NOTHING),
        ("overview", NOTHING),
    ],
)
def test_a_heading_labels_the_roles_the_ruling_lists(heading: str, roles: frozenset[ChainRole]) -> None:
    assert heading_roles(heading, DA) == roles
    assert heading_roles(heading, ADVANTAGE) == roles


@pytest.mark.parametrize(
    ("heading", "role"),
    [
        ("harms", H),
        ("harm", H),
        ("inherency", INH),
        ("inh", INH),
        ("solvency", S),
        ("contention solvency", S),
        ("solv", S),
    ],
)
def test_harms_inherency_and_solvency_label_an_advantages_cards_only(heading: str, role: ChainRole) -> None:
    assert heading_roles(heading, ADVANTAGE) == {role}
    assert heading_roles(heading, DA) == set()


def test_solves_and_harmful_are_not_role_words() -> None:
    assert heading_roles("solves case", ADVANTAGE) == set()
    assert heading_roles("harmful", ADVANTAGE) == set()


# ------------------------------------------------------------------------------------------------
# Tags
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tag", "role"),
    [
        ("Uniqueness: the midterms are close", U),
        ("UQ - Democrats lead now", U),
        ("The link: reform polls badly", L),
        ("Link: single payer is a tax", L),
        ("Links - the plan costs trillions", L),
        ("2. The link - reform is unpopular", L),
        ("Internal link: polls decide control", IL),
        ("IL - control decides the agenda", IL),
        ("I/L: control decides the agenda", IL),
        ("Internal: rates rise", IL),
        ("U: premiums are rising now", None),
        ("U - premiums rise", None),
        ("U.S. hospitals are closing", None),
        ("Link turn: reform is popular", None),
        ("Link turns - the plan is popular", None),
        ("Link defense: no spillover", None),
        ("No link: the plan is popular", None),
        ("Linkage politics fail", None),
        ("Extinction from economic collapse", None),
        ("Solvency: the plan works", None),
        ("Harms: people die", None),
        (None, None),
    ],
)
def test_a_tag_opening_labels_uniqueness_link_or_internal_link_and_never_by_u(
    tag: str | None, role: ChainRole | None
) -> None:
    assert tag_role(tag) is role


# ------------------------------------------------------------------------------------------------
# A card's roles
# ------------------------------------------------------------------------------------------------


def test_a_card_takes_its_sub_headings_roles_and_its_tags() -> None:
    assert card_roles(_sub("u"), ("spending da", "u"), "Spending is high now", DA) == {U}
    assert card_roles((), ("spending da",), "The link: the plan is a tax", DA) == {L}
    assert card_roles(_sub("link"), ("spending da", "link"), "Internal link: rates rise", DA) == {L, IL}


def test_an_answer_sub_heading_fills_no_role() -> None:
    assert card_roles(_sub("uniqueness", answers=(0,)), ("midterms da", "uniqueness"), "Polls", DA) == set()
    assert card_roles(_sub("dome", "link", answers=(1,)), ("midterms da", "dome", "link"), None, DA) == set()


def test_a_heading_holding_two_roles_labels_neither() -> None:
    assert card_roles(_sub("u and link"), ("spending da", "u and link"), "Rates", DA) == set()


def test_the_impact_role_is_t10s_impact_card_whatever_else_the_heading_holds() -> None:
    assert card_roles(_sub("link impact"), ("spending da", "link impact"), "Rates", DA) == {IMP}
    assert card_roles((), ("spending da",), "Extinction from debt", DA) == {IMP}
    assert card_roles((), ("costs advantage",), "2. Extinction from economic collapse", ADVANTAGE) == {IMP}
    assert card_roles(_sub("no impact"), ("midterms da", "no impact"), "Polls", DA) == set()


def test_an_advantages_roles_are_not_a_das() -> None:
    assert card_roles(_sub("solvency"), ("costs advantage", "solvency"), "Works", ADVANTAGE) == {S}
    assert card_roles(_sub("solvency"), ("spending da", "solvency"), "Works", DA) == set()


def test_only_the_sub_headings_label_a_role_not_the_headings_above_the_placing_one() -> None:
    # "link" here is a heading over the position's own heading: the card's sub-headings are none.
    assert card_roles((), ("link", "spending da"), "Rates", DA) == set()


# ------------------------------------------------------------------------------------------------
# Scenarios
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sub_headings", "scenario"),
    [
        (_sub("scenario 1 economic collapse"), CardScenario(True, "economic collapse")),
        (_sub("scenario 1 is debt"), CardScenario(True, "debt")),
        (_sub("sc 2 pandemics"), CardScenario(True, "pandemics")),
        (_sub("scenario two warming"), CardScenario(True, "warming")),
        (_sub("advantage 1 pandemics"), CardScenario(True, "pandemics")),
        (_sub("scenario 1"), CardScenario(True, None)),
        (_sub("sc 2"), CardScenario(True, None)),
        (_sub("dome"), CardScenario(True, "dome")),
        (_sub("golden dome"), CardScenario(True, "golden dome")),
        (_sub("dome impact"), CardScenario(False, "dome")),
        (_sub("impact golden dome"), CardScenario(False, "golden dome")),
        (_sub("dome internal"), CardScenario(False, "dome")),
        (_sub("recession", "recession impact"), CardScenario(True, "recession")),
        (_sub("dome", "iran impact"), CardScenario(True, "dome")),
        (_sub("link single payer"), CardScenario(False, None)),
        (_sub("u us lead"), CardScenario(False, None)),
        (_sub("impact"), CardScenario(False, None)),
        (_sub("impact turns case"), CardScenario(False, None)),
        (_sub("impact overview"), CardScenario(False, None)),
        (_sub("link impact"), CardScenario(False, None)),
        (_sub("dome", answers=(0,)), CardScenario(False, None)),
        (_sub("no link"), CardScenario(False, None)),
        (_sub("no impact"), CardScenario(False, None)),
        (_sub("lt"), CardScenario(False, None)),
        (_sub("l t"), CardScenario(False, None)),
    ],
)
def test_a_scenario_is_a_numbered_heading_a_named_one_or_the_words_beside_an_impact_or_il_label(
    sub_headings: tuple[SubHeading, ...], scenario: CardScenario
) -> None:
    assert card_scenario(sub_headings, DA) == scenario


@pytest.mark.parametrize(
    "heading",
    [
        "overview",
        "o v",
        "ov midterms",
        "kick",
        "extra",
        "extras",
        "defense",
        "turn",
        "wait times turn",
        "turns econ",
        "framing",
        "solves case",
        "dem win solves case",
        "da",
        "pharma da u",
        "disad",
        "new disease",
        "t c",
        "tc inequality",
        "t c costs",
        "k",
        "cap k central planning",
        "cp",
        "t",
        "theory",
        "counterplan",
        "kritik",
        "2ac",
        "2ac1",
        "1nc3",
        "2ac4 thumpers",
    ],
)
def test_the_not_a_scenario_list_names_nothing(heading: str) -> None:
    assert card_scenario(_sub(heading), DA) == CardScenario(False, None)


def test_a_heading_the_coach_ruled_names_no_position_names_no_scenario() -> None:
    assert card_scenario(_sub("polycrisis"), DA, no_position=("polycrisis",)) == CardScenario(False, None)


def test_a_role_heading_the_coach_ruled_names_no_position_still_labels_its_role() -> None:
    # The ruling: the coach's no-position rulings still label roles (`link`, `u`, `solvency` today).
    assert card_roles(_sub("link"), ("spending da", "link"), "Rates", DA) == {L}


def test_an_advantages_role_words_name_no_scenario() -> None:
    assert card_scenario(_sub("solvency"), ADVANTAGE) == CardScenario(False, None)
    assert card_scenario(_sub("harms"), ADVANTAGE) == CardScenario(False, None)


# ------------------------------------------------------------------------------------------------
# Withheld names
# ------------------------------------------------------------------------------------------------


def test_the_caselist_words_are_its_schools_tournaments_and_team_codes() -> None:
    words = caselist_words(read_synthetic_caselist(FIXTURE).disclosures)
    for word in ("ashgrove", "birchmoor", "cedarvale", "driftwood", "fictional", "invitational"):
        assert word in words
    for word in ("imaginary", "classic", "later", "tournament", "xx", "yy", "kk"):
        assert word in words


def test_a_name_holding_a_caselist_word_is_withheld() -> None:
    words = caselist_words(read_synthetic_caselist(FIXTURE).disclosures)
    assert is_withheld("cedarvale crash", words)
    assert is_withheld("crash at the invitational", words)
    assert is_withheld("qq surge", words)
    assert not is_withheld("recession", words)
    assert not is_withheld("economic collapse", words)


def test_a_short_word_of_a_school_or_tournament_is_not_a_caselist_word() -> None:
    disclosure = read_synthetic_caselist(FIXTURE).disclosures[0]
    short = disclosure.model_copy(update={"school": "Oak Fictional", "tournament": "Big Elm Open"})
    words = caselist_words([short])
    assert "oak" not in words and "elm" not in words and "big" not in words
    assert {"fictional", "open"} <= words
    assert disclosure.team_code.casefold() in words


# ------------------------------------------------------------------------------------------------
# The coach's scenario list (`v1-e32-t22`)
# ------------------------------------------------------------------------------------------------

DROPPED = ("too early", "economic collapse")


def _position(**fields: object) -> Position:
    return Position.model_validate(
        {"id": "sample-midterms-da", "label": "Midterms DA", "kind": "da", "side": "neg", **fields}
    )


LISTED = _position(
    scenarios=[
        {"name": "Golden dome", "forms": ["dome", "golden dome"]},
        {"name": "iran", "forms": ["iran"]},
    ],
    not_scenarios=list(DROPPED),
)


@pytest.mark.parametrize(
    ("sub_headings", "scenario"),
    [
        (_sub("too early"), CardScenario(False, None)),
        (_sub("too early", "dome impact"), CardScenario(False, "dome")),
        (_sub("dome", "too early"), CardScenario(True, "dome")),
        (_sub("economic collapse impact"), CardScenario(False, None)),
        (_sub("too early internal"), CardScenario(False, None)),
        (_sub("scenario 1 economic collapse"), CardScenario(True, None)),
        (_sub("scenario 1 economic collapse", "dome impact"), CardScenario(True, "dome")),
        (_sub("too early dome"), CardScenario(True, "too early dome")),
    ],
    ids=[
        "a named heading",
        "a named heading then an impact label beside a form",
        "an inner named heading under a named one",
        "beside an impact label",
        "beside an internal-link label",
        "a numbered heading stays one, with no name",
        "a numbered heading then an impact label beside a form",
        "a form inside longer words is not the form",
    ],
)
def test_a_form_the_coach_ruled_names_no_scenario_is_no_scenario_heading_and_names_nothing(
    sub_headings: tuple[SubHeading, ...], scenario: CardScenario
) -> None:
    assert card_scenario(sub_headings, DA, not_scenarios=DROPPED) == scenario


def test_without_forms_ruled_out_a_card_keeps_t14s_scenario() -> None:
    assert card_scenario(_sub("too early"), DA) == CardScenario(True, "too early")
    assert card_scenario(_sub("scenario 1 economic collapse"), DA) == CardScenario(True, "economic collapse")


@pytest.mark.parametrize(
    ("words", "name"),
    [
        ("dome", "Golden dome"),
        ("golden dome", "Golden dome"),
        ("iran", "iran"),
        ("polycrisis", None),
        (None, None),
    ],
    ids=["one form", "the merged form", "a name as its form", "words the list does not hold", "no words"],
)
def test_a_listed_position_shows_the_coachs_name_for_a_form_and_nothing_else(
    words: str | None, name: str | None
) -> None:
    assert scenario_name(LISTED, words) == name


def test_a_position_without_a_list_shows_t14s_words() -> None:
    plain = _position()
    assert scenario_name(plain, "polycrisis") == "polycrisis"
    assert scenario_name(plain, None) is None


def test_a_position_listing_only_forms_that_name_no_scenario_shows_no_name() -> None:
    assert scenario_name(_position(not_scenarios=["too early"]), "polycrisis") is None


def test_a_coachs_name_holding_a_caselist_word_is_withheld_whatever_its_case_or_punctuation() -> None:
    words = caselist_words(read_synthetic_caselist(FIXTURE).disclosures)
    assert is_withheld("Cedarvale crash", words)
    assert is_withheld("Crash (Cedarvale)", words)
    assert is_withheld("QQ-style surge", words)
    assert not is_withheld("Golden dome", words)
    assert not is_withheld("Rising costs", words)
