"""The name scan's third list scrubbed from what a model is sent (`v1-e32-t40`).

The scan's third list is every disclosing team's school, team code and tournament. `v1-e32-t39` found other
teams' tournaments and codes in the heading paths the model stage sent, which the scrub left in: it took
out the disclosing team's own names, the caselist's schools and its code words only. Every expected value
is written by hand. Every school, team code and tournament here is invented.
"""

from __future__ import annotations

from debate_core.arguments.landscape.headings import NormalizedHeading
from debate_core.arguments.landscape.model_stage import sent_headings
from debate_core.arguments.landscape.seeding import SeedSource, SeedTeam
from debate_core.arguments.landscape.source_headings import CaselistNames
from debate_core.arguments.landscape.tag_scrub import DisclosedNames, card_tag
from debate_core.domain.caselist import Side

MAPLE = SeedTeam(
    identity="maple/ab",
    side=Side.NEG,
    names=("Maple Grove", "AB", "Lakeside Invitational"),
    tournament="Lakeside Invitational",
)
CEDAR = SeedTeam(
    identity="cedar/kl",
    side=Side.AFF,
    names=("Cedar Ridge", "KL", "Harbor Classic"),
    tournament="Harbor Classic",
)
SOURCES = (
    SeedSource(sha256="a" * 64, teams=(MAPLE,), cards=()),
    SeedSource(sha256="b" * 64, teams=(CEDAR,), cards=()),
)
NAMES = DisclosedNames.of_sources(SOURCES)
CASELIST = CaselistNames({"Maple Grove": ("AB",), "Cedar Ridge": ("KL",)})
CODES = frozenset({"ab", "kl"})


def test_every_disclosing_teams_names_come_out_of_words_whole() -> None:
    assert NAMES.without("cliff harbor classic nears kl") == "cliff nears"
    assert NAMES.without("lakeside invitational maple grove ab cedar ridge link") == "link"


def test_a_word_that_only_starts_like_a_name_stays() -> None:
    assert NAMES.without("harbors classical kl2 lakesides harbor") == "harbors classical kl2 lakesides harbor"


def test_a_name_that_taking_another_out_brings_together_comes_out_too() -> None:
    assert NAMES.without("harbor kl classic cliff") == "cliff"


def test_no_names_take_nothing_out() -> None:
    assert DisclosedNames(()).without("harbor classic cliff") == "harbor classic cliff"


def test_the_names_never_show_in_a_repr() -> None:
    shown = repr(NAMES)
    for word in ("Harbor", "harbor", "Cedar", "cedar", "Lakeside", "lakeside", "kl"):
        assert word not in shown


def test_a_tag_cite_or_excerpt_loses_another_teams_tournament_as_the_model_reads_it() -> None:
    own = MAPLE.names
    assert card_tag("Harbor Classic: the cliff nears", own, CASELIST, CODES, NAMES) == "the cliff nears"
    assert card_tag("Okafor 26 (Harbor-Classic)", own, CASELIST, CODES, NAMES) == "okafor 26"


def test_the_local_classifiers_tag_keeps_its_rule_without_the_third_list() -> None:
    """`v1-e32-t21`'s features are read without it, as its proxy model was trained."""
    assert card_tag("Harbor Classic: the cliff nears", MAPLE.names, CASELIST, CODES) == (
        "harbor classic the cliff nears"
    )


def test_a_heading_loses_another_teams_tournament_and_one_left_empty_is_dropped() -> None:
    headings = (
        NormalizedHeading(text="harbor classic", answer=False),
        NormalizedHeading(text="harbor classic cliff da", answer=True),
        NormalizedHeading(text="link", answer=False),
    )
    assert sent_headings(headings, CODES, NAMES) == (
        NormalizedHeading(text="cliff da", answer=True),
        NormalizedHeading(text="link", answer=False),
    )
