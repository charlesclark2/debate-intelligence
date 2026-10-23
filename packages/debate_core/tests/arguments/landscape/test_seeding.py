"""Deterministic seeding of taxonomy candidates (`v1-e32-t01-position-taxonomy` ac4).

Seeding turns the headings over each parsed card into rows of a candidates CSV: the normalized
heading, its level, how many documents and how many distinct teams carry it, and a suggested
position id. Teams are counted from each source's disclosures, never from what a heading says, and
a heading fewer than two teams use is left out of the file, so no row can point at one team.

Every source, team and heading here is invented. A team's identity is an opaque string; its
`names` are placeholders shaped like a school and a team code, and must never reach the CSV.
"""

from __future__ import annotations

import io

import pytest

from debate_core.arguments.landscape.seeding import (
    CANDIDATE_COLUMNS,
    CandidateRow,
    HeadingLevel,
    SeedCard,
    SeedSource,
    SeedTeam,
    read_candidates_csv,
    review_sheet,
    seed_candidates,
    suggest_position,
    write_candidates_csv,
)
from debate_core.domain.caselist import Side
from debate_core.domain.landscape import Taxonomy

TEAM_ONE = SeedTeam(identity="team-one", side=Side.NEG, names=("School One", "Team One"))
TEAM_ONE_AFF = SeedTeam(identity="team-one", side=Side.AFF, names=("School One", "Team One"))
TEAM_TWO = SeedTeam(identity="team-two", side=Side.NEG, names=("School Two", "Team Two"))
TEAM_THREE = SeedTeam(identity="team-three", side=Side.AFF, names=("School Three", "Team Three"))


def card(*path: str, tag: str | None = "An invented claim") -> SeedCard:
    return SeedCard(tag=tag, section_path=tuple(path))


def source(name: str, teams: tuple[SeedTeam, ...], *cards: SeedCard) -> SeedSource:
    return SeedSource(sha256=name * 64, teams=teams, cards=tuple(cards))


def rows_by_heading(rows: tuple[CandidateRow, ...]) -> dict[tuple[str, bool], CandidateRow]:
    return {(row.normalized_heading, row.answer): row for row in rows}


# ------------------------------------------------------------------------------------------------
# Counting
# ------------------------------------------------------------------------------------------------


def test_documents_and_distinct_teams_are_counted_from_the_sources() -> None:
    seeding = seed_candidates(
        [
            source("a", (TEAM_ONE,), card("1NC", "Off", "1NC Spending DA Shell")),
            source("b", (TEAM_TWO,), card("Neg", "Spending DA", "Uniqueness")),
            source("c", (TEAM_ONE,), card("Spending DA - 2NC Blocks")),
        ]
    )
    row = rows_by_heading(seeding.rows)[("spending da", False)]
    assert (row.documents, row.teams, row.neg_teams, row.aff_teams) == (3, 2, 2, 0)


def test_one_team_is_one_team_however_its_headings_are_written() -> None:
    seeding = seed_candidates(
        [
            source("a", (TEAM_ONE,), card("Spending DA")),
            source("b", (TEAM_ONE,), card("Spending DA")),
            source("c", (TEAM_ONE,), card("Spending DA vs Team Two")),
        ],
        minimum_teams=1,
    )
    row = rows_by_heading(seeding.rows)[("spending da", False)]
    assert (row.documents, row.teams) == (3, 1)


def test_a_file_two_teams_disclosed_counts_for_both() -> None:
    seeding = seed_candidates([source("a", (TEAM_ONE, TEAM_TWO), card("Spending DA"))])
    row = rows_by_heading(seeding.rows)[("spending da", False)]
    assert (row.documents, row.teams) == (1, 2)


def test_a_heading_is_counted_once_per_document() -> None:
    seeding = seed_candidates(
        [
            source("a", (TEAM_ONE,), card("Spending DA", "Link"), card("Spending DA", "Impact")),
            source("b", (TEAM_TWO,), card("Spending DA")),
        ]
    )
    assert rows_by_heading(seeding.rows)[("spending da", False)].documents == 2


def test_sides_come_from_the_disclosure() -> None:
    seeding = seed_candidates(
        [
            source("a", (TEAM_ONE_AFF,), card("Single Payer Aff")),
            source("b", (TEAM_THREE,), card("Single Payer Aff")),
            source("c", (TEAM_TWO,), card("Single Payer Aff")),
        ]
    )
    row = rows_by_heading(seeding.rows)[("single payer aff", False)]
    assert (row.teams, row.aff_teams, row.neg_teams) == (3, 2, 1)


def test_a_heading_fewer_than_two_teams_use_is_left_out_and_counted() -> None:
    seeding = seed_candidates(
        [
            source("a", (TEAM_ONE,), card("Spending DA"), card("Lonely CP")),
            source("b", (TEAM_TWO,), card("Spending DA")),
        ]
    )
    assert ("lonely cp", False) not in rows_by_heading(seeding.rows)
    assert seeding.counts.left_out_below_minimum_teams == 1
    assert seeding.counts.candidates == 1


def test_a_source_with_no_known_team_counts_documents_and_no_team() -> None:
    seeding = seed_candidates(
        [source("a", (), card("Spending DA")), source("b", (TEAM_ONE,), card("Spending DA"))],
        minimum_teams=1,
    )
    row = rows_by_heading(seeding.rows)[("spending da", False)]
    assert (row.documents, row.teams) == (2, 1)
    assert seeding.counts.sources_without_team == 1


def test_the_counts_say_what_was_read() -> None:
    seeding = seed_candidates(
        [
            source("a", (TEAM_ONE,), card("1NC", "Spending DA"), card("1NC", "Courts CP")),
            source("b", (TEAM_TWO,), card("Spending DA")),
        ]
    )
    counts = seeding.counts
    assert (counts.sources, counts.cards, counts.headings, counts.distinct_headings) == (2, 3, 3, 2)
    assert (counts.candidates, counts.left_out_below_minimum_teams) == (1, 1)


def test_no_sources_is_no_rows() -> None:
    seeding = seed_candidates([])
    assert seeding.rows == ()
    assert seeding.counts.sources == 0


def test_a_minimum_below_one_is_refused() -> None:
    with pytest.raises(ValueError, match="minimum"):
        seed_candidates([], minimum_teams=0)


# ------------------------------------------------------------------------------------------------
# Levels, answers and what is not a heading
# ------------------------------------------------------------------------------------------------


def test_a_full_path_gives_pocket_hat_and_block() -> None:
    seeding = seed_candidates(
        [
            source("a", (TEAM_ONE,), card("Spending DA", "Hospitals Link", "Courts CP")),
            source("b", (TEAM_TWO,), card("Spending DA", "Hospitals Link", "Courts CP")),
        ]
    )
    rows = rows_by_heading(seeding.rows)
    assert rows[("spending da", False)].level is HeadingLevel.POCKET
    assert rows[("hospitals link", False)].level is HeadingLevel.HAT
    assert rows[("courts cp", False)].level is HeadingLevel.BLOCK


def test_a_shortened_path_cannot_say_which_level_a_heading_is() -> None:
    seeding = seed_candidates(
        [source("a", (TEAM_ONE,), card("Spending DA")), source("b", (TEAM_TWO,), card("Spending DA", "Link"))]
    )
    assert rows_by_heading(seeding.rows)[("spending da", False)].level is HeadingLevel.UNKNOWN


def test_the_level_most_documents_show_wins_over_unknown() -> None:
    seeding = seed_candidates(
        [
            source("a", (TEAM_ONE,), card("Pocket", "Spending DA", "Block")),
            source("b", (TEAM_TWO,), card("Spending DA")),
            source("c", (TEAM_THREE,), card("Other", "Spending DA", "Block")),
        ]
    )
    assert rows_by_heading(seeding.rows)[("spending da", False)].level is HeadingLevel.HAT


def test_an_untagged_card_under_an_open_tag_does_not_make_the_tag_a_heading() -> None:
    claim = "An invented claim the tag makes"
    seeding = seed_candidates(
        [
            source("a", (TEAM_ONE,), card("Spending DA", tag=claim), card("Spending DA", claim, tag=None)),
            source("b", (TEAM_TWO,), card("Spending DA", tag=claim), card("Spending DA", claim, tag=None)),
        ]
    )
    assert [row.normalized_heading for row in seeding.rows] == ["spending da"]


def test_nothing_past_the_block_is_a_heading() -> None:
    seeding = seed_candidates(
        [
            source("a", (TEAM_ONE,), card("Pocket", "Hat", "Spending DA", "An orphan tag", tag=None)),
            source("b", (TEAM_TWO,), card("Pocket", "Hat", "Spending DA", "An orphan tag", tag=None)),
        ]
    )
    assert ("an orphan tag", False) not in rows_by_heading(seeding.rows)


def test_an_answer_is_its_own_row_in_the_cluster_of_what_it_answers() -> None:
    seeding = seed_candidates(
        [
            source("a", (TEAM_ONE,), card("Spending DA")),
            source("b", (TEAM_TWO,), card("Spending DA")),
            source("c", (TEAM_THREE,), card("AT: Spending DA")),
            source("d", (TEAM_ONE_AFF,), card("A2 Spending DA")),
        ]
    )
    rows = rows_by_heading(seeding.rows)
    answer = rows[("spending da", True)]
    assert (answer.documents, answer.teams, answer.aff_teams) == (2, 2, 2)
    assert answer.suggested_position_id == rows[("spending da", False)].suggested_position_id == "spending-da"
    assert answer.cluster_teams == 3


def test_a_teams_own_names_are_taken_out_of_its_headings() -> None:
    seeding = seed_candidates(
        [
            source("a", (TEAM_ONE,), card("School One Team One Neg", "Spending DA")),
            source("b", (TEAM_TWO,), card("school two - TEAM TWO", "Spending DA - School Two")),
        ],
        minimum_teams=1,
    )
    assert [row.normalized_heading for row in seeding.rows] == ["spending da"]


# ------------------------------------------------------------------------------------------------
# Suggested positions and clusters
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("heading", "position_id", "kind"),
    [
        ("spending da", "spending-da", "da"),
        ("spending disad", "spending-da", "da"),
        ("spending disadvantage", "spending-da", "da"),
        ("courts cp", "courts-cp", "cp"),
        ("courts counterplan", "courts-cp", "cp"),
        ("courts counter plan", "courts-cp", "cp"),
        ("cap k", "cap-k", "k"),
        ("cap kritik", "cap-k", "k"),
        ("t nhi", "nhi-t", "t"),
        ("topicality national health insurance", "national-health-insurance-t", "t"),
        ("condo bad", "condo-bad", "theory"),
        ("pics good", "pics-good", "theory"),
        ("vagueness theory", "vagueness-theory", "theory"),
        ("growth advantage", "growth-advantage", "advantage"),
        ("adv growth", "growth-advantage", "advantage"),
        ("single payer aff", "single-payer-aff", "aff"),
        ("hospitals", "hospitals", ""),
        ("da", "da", "da"),
    ],
)
def test_a_suggested_position_is_its_words_and_its_kind(heading: str, position_id: str, kind: str) -> None:
    assert suggest_position(heading) == (position_id, kind)


def test_a_long_heading_suggests_an_id_of_its_first_eight_words() -> None:
    assert suggest_position("one two three four five six seven eight nine ten") == (
        "one-two-three-four-five-six-seven-eight",
        "",
    )


def test_rows_are_ordered_by_their_cluster_then_their_own_teams() -> None:
    seeding = seed_candidates(
        [
            source("a", (TEAM_ONE,), card("Spending DA"), card("Courts CP")),
            source("b", (TEAM_TWO,), card("Spending Disad"), card("Courts CP")),
            source("c", (TEAM_THREE,), card("Spending DA"), card("Spending Disad")),
        ]
    )
    assert [
        (row.suggested_position_id, row.normalized_heading, row.cluster_teams, row.teams)
        for row in seeding.rows
    ] == [
        ("spending-da", "spending da", 3, 2),
        ("spending-da", "spending disad", 3, 2),
        ("courts-cp", "courts cp", 2, 2),
    ]


# ------------------------------------------------------------------------------------------------
# The CSV
# ------------------------------------------------------------------------------------------------

# Written by hand from the sources in the test below (working agreement 6), not by running the code.
EXPECTED_CSV = (
    "suggested_position_id,suggested_kind,cluster_teams,normalized_heading,answer,level,"
    "documents,teams,aff_teams,neg_teams\r\n"
    "spending-da,da,3,spending da,false,block,2,2,0,2\r\n"
    "spending-da,da,3,spending da,true,unknown,2,2,2,0\r\n"
    "courts-cp,cp,2,courts cp,false,hat,2,2,0,2\r\n"
)


def test_the_csv_holds_the_columns_and_counts_and_nothing_that_names_a_team() -> None:
    seeding = seed_candidates(
        [
            source("a", (TEAM_ONE,), card("School One Neg", "Courts CP", "Spending DA")),
            source("b", (TEAM_TWO,), card("1NC", "Courts CP", "Spending DA Shell")),
            source("c", (TEAM_THREE,), card("AT: Spending DA")),
            source("d", (TEAM_ONE_AFF,), card("2AC", "A2 Spending DA")),
        ]
    )
    stream = io.StringIO()
    write_candidates_csv(seeding.rows, stream)
    text = stream.getvalue()
    assert text == EXPECTED_CSV
    data_rows = text.split("\r\n", 1)[1]
    for name in ("school", "team", "one", "two", "three"):
        assert name not in data_rows.casefold()
    assert read_candidates_csv(io.StringIO(text)) == seeding.rows
    assert tuple(text.split("\r\n", 1)[0].split(",")) == CANDIDATE_COLUMNS


def test_a_csv_with_other_columns_is_refused() -> None:
    with pytest.raises(ValueError, match="columns"):
        read_candidates_csv(io.StringIO("heading,count\r\nspending da,3\r\n"))


def test_nothing_identifying_is_in_a_seed_values_repr() -> None:
    shown = repr(source("a", (TEAM_ONE,), card("Spending DA", tag="An invented claim")))
    for hidden in ("School One", "Team One", "team-one", "An invented claim"):
        assert hidden not in shown


# ------------------------------------------------------------------------------------------------
# The review sheet
# ------------------------------------------------------------------------------------------------


def test_the_review_sheet_lists_each_position_with_its_counts_and_the_top_unplaced_headings() -> None:
    rows = read_candidates_csv(io.StringIO(EXPECTED_CSV))
    taxonomy = Taxonomy.model_validate(
        {
            "topic_id": "policy-sample-topic",
            "taxonomy_version": "1.0.0",
            "event": "POLICY",
            "positions": [
                {
                    "id": "spending-da",
                    "label": "Spending DA",
                    "kind": "da",
                    "side": "neg",
                    "aliases": ["spending da"],
                },
                {"id": "unseen-cp", "label": "Unseen CP", "kind": "cp", "side": "neg"},
            ],
        }
    )
    sheet = review_sheet(rows, taxonomy, unplaced_limit=10)
    assert "Spending DA" in sheet
    assert "`spending da`: 2 documents, 2 teams (2 aff, answering it)" in sheet
    assert "`spending da`: 2 documents, 2 teams (2 neg)" in sheet
    assert "Unseen CP" in sheet
    assert "no alias yet" in sheet
    assert "| `courts cp` | 2 | 2 | hat | courts-cp |" in sheet
