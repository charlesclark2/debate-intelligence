"""The search pilot's query parser, cursor, filters, snippets, runs and provenance line (`v1-e39-t03`).

Every expected value is written by hand from the input beside it (working agreement 6). The
property tests here are structural: a prefix's column filter names only the column it was asked
for, and nothing a student types becomes an FTS5 operator. That the expression never raises an FTS5
syntax error is checked against a real index in
`tests/integrations/local/test_search_index_reader_sqlite_features.py`.

Every school, team code, tournament, camp and file title is invented (data-use policy, rule 5).
"""

from __future__ import annotations

import base64
import re
from datetime import date

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from debate_core.application.ports.parsed_store import OccurrenceRecord
from debate_core.domain.card_occurrence import ClusterMembership
from debate_core.domain.caselist import CampFile, Disclosure, Event, RoundLabel, Side
from debate_core.domain.debate_files import CardCompleteness
from debate_core.domain.evidence_search import (
    MAX_CURSOR_OFFSET,
    MAX_QUERY_CHARACTERS,
    MAX_QUERY_TERMS,
    RANKING_WEIGHTS,
    SNIPPET_CLOSE,
    SNIPPET_OPEN,
    CardRun,
    InvalidSearchCursor,
    ParsedQuery,
    QueryTerm,
    RankingWeights,
    SearchField,
    SearchFilters,
    SnippetSegment,
    card_runs,
    decode_search_cursor,
    encode_search_cursor,
    occurrence_provenance_line,
    parse_query,
    search_binding,
    snippet_segments,
)
from debate_core.domain.search_index import IndexedFontSizeSpan, IndexedFormattingSpan
from debate_core.domain.style_profile import RunEmphasis
from debate_core.integrations.docx_file_writer.writer import provenance_line

TAG, CITE = SearchField.TAG, SearchField.CITE

FTS5_SYNTAX = st.sampled_from(
    [
        "AND",
        "OR",
        "NOT",
        "NEAR",
        "NEAR(",
        "*",
        "^",
        "(",
        ")",
        '"',
        '""',
        ":",
        "{",
        "}",
        "-",
        "+",
        "tag:",
        "author:",
        "cite:",
        "text:",
        "read_aloud:",
        "school:",
        "team:",
        "{tag cite}:",
        "TAG:",
        "Author:",
        "\x00",
        "'",
        ",",
        "growth",
        "Okonkwo",
    ]
)
"""Pieces of FTS5's query language, the two prefixes and some words, for queries built to break it."""

QUERIES = st.one_of(
    st.text(max_size=80),
    st.lists(st.one_of(FTS5_SYNTAX, st.text(max_size=6)), max_size=14).map(" ".join),
    st.lists(st.one_of(FTS5_SYNTAX, st.text(max_size=4)), max_size=14).map("".join),
)


# ------------------------------------------------------------------------------------------------
# Parsing
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "terms"),
    [
        ("growth", [QueryTerm("growth")]),
        ("  economic   growth ", [QueryTerm("economic"), QueryTerm("growth")]),
        ('"economic growth" bad', [QueryTerm("economic growth", phrase=True), QueryTerm("bad")]),
        ("growth -recession", [QueryTerm("growth"), QueryTerm("recession", excluded=True)]),
        ('growth -"soft landing"', [QueryTerm("growth"), QueryTerm("soft landing", phrase=True, excluded=True)]),
        ("author:okonkwo", [QueryTerm("okonkwo", field=CITE)]),
        ("AUTHOR:Okonkwo Tag:growth", [QueryTerm("Okonkwo", field=CITE), QueryTerm("growth", field=TAG)]),
        ('tag:"growth bad"', [QueryTerm("growth bad", phrase=True, field=TAG)]),
        ("-author:okonkwo growth", [QueryTerm("okonkwo", excluded=True, field=CITE), QueryTerm("growth")]),
        ('"unclosed phrase', [QueryTerm("unclosed phrase", phrase=True)]),
        ("author: growth", [QueryTerm("author:"), QueryTerm("growth")]),
        ("author:", [QueryTerm("author:")]),
        ("school:Riverbend", [QueryTerm("school:Riverbend")]),
        ("text:growth", [QueryTerm("text:growth")]),
        ("NEAR(growth bad)", [QueryTerm("NEAR(growth"), QueryTerm("bad)")]),
        ("grow* AND bad OR", [QueryTerm("grow*"), QueryTerm("AND"), QueryTerm("bad"), QueryTerm("OR")]),
        ('say"what', [QueryTerm('say"what')]),
        ("- * ^ () growth", [QueryTerm("growth")]),
        ("--growth", [QueryTerm("-growth", excluded=True)]),
        ("gro\x00wth", [QueryTerm("gro"), QueryTerm("wth")]),
        ("", []),
    ],
)
def test_search_query_reads_words_phrases_exclusions_and_two_prefixes_only(
    raw: str, terms: list[QueryTerm]
) -> None:
    assert parse_query(raw) == ParsedQuery(tuple(terms))


@pytest.mark.parametrize(
    ("raw", "expression"),
    [
        ("growth", '"growth"'),
        ("economic growth", '"economic" AND "growth"'),
        ('"economic growth"', '"economic growth"'),
        ("author:okonkwo tag:growth", 'cite : "okonkwo" AND tag : "growth"'),
        ("growth -recession -tag:bad", '("growth") NOT "recession" NOT tag : "bad"'),
        ('say"what', '"say""what"'),
        ('author:"a "" b', 'cite : "a " AND " b"'),
        ("NEAR(growth", '"NEAR(growth"'),
        ("-growth", None),
        ("*** ---", None),
    ],
)
def test_search_query_becomes_quoted_fts5_phrases_joined_by_and_and_not(
    raw: str, expression: str | None
) -> None:
    assert parse_query(raw).fts5_expression() == expression


def test_search_query_keeps_thirty_two_terms_and_says_it_dropped_the_rest() -> None:
    parsed = parse_query(" ".join(f"word{number}" for number in range(40)))
    assert len(parsed.terms) == MAX_QUERY_TERMS == 32
    assert parsed.terms[-1] == QueryTerm("word31")
    assert parsed.shortened


def test_search_query_reads_five_hundred_twelve_characters_and_says_it_dropped_the_rest() -> None:
    parsed = parse_query("a" * 600)
    assert parsed.terms == (QueryTerm("a" * MAX_QUERY_CHARACTERS),)
    assert parsed.shortened
    assert not parse_query("a" * 512).shortened


_COLUMN_FILTER = re.compile(r'(?:^|[ (])([a-z_]+) : ""')


def _outside_strings(expression: str) -> str:
    """The expression with every FTS5 string's contents removed: what FTS5 reads as syntax."""
    return re.sub(r'"(?:[^"]|"")*"', '""', expression)


@settings(max_examples=400, deadline=None)
@given(QUERIES)
def test_search_query_prefix_names_the_only_column_a_term_searches(raw: str) -> None:
    """ac1: a column filter in the expression is `tag` or `cite`, one per prefixed term, in order."""
    parsed = parse_query(raw)
    expression = parsed.fts5_expression()
    if expression is None:
        assert not parsed.included
        return
    named = [term.field.value for term in (*parsed.included, *parsed.excluded) if term.field is not None]
    assert _COLUMN_FILTER.findall(_outside_strings(expression)) == named
    assert set(named) <= {"tag", "cite"}


@settings(max_examples=400, deadline=None)
@given(QUERIES)
def test_search_query_lets_no_typed_operator_through(raw: str) -> None:
    """Outside its strings, the expression is only the AND, NOT, parentheses and filters this module writes."""
    expression = parse_query(raw).fts5_expression()
    if expression is None:
        return
    syntax = _outside_strings(expression)
    assert re.fullmatch(r'(\()?((tag|cite) : )?""( AND ((tag|cite) : )?"")*(\))?( NOT ((tag|cite) : )?"")*', syntax)
    assert "\x00" not in expression


# ------------------------------------------------------------------------------------------------
# Ranking weights
# ------------------------------------------------------------------------------------------------


def test_search_ranking_weights_are_one_bm25_call_in_column_order() -> None:
    assert RANKING_WEIGHTS.bm25() == "bm25(10.0, 6.0, 3.0, 1.0)"
    with pytest.raises(ValueError, match="positive"):
        RankingWeights(tag=1.0, cite=0.0, read_aloud=1.0, text=1.0).bm25()


# ------------------------------------------------------------------------------------------------
# Filters
# ------------------------------------------------------------------------------------------------


def test_search_filters_take_an_event_a_store_a_camp_a_side_and_a_day() -> None:
    filters = SearchFilters(
        event=Event.POLICY,
        caselist="openev",
        camp="Cascade Institute",
        first_seen_on_or_after=date(2026, 9, 1),
    )
    assert filters.model_dump(mode="json") == {
        "event": "POLICY",
        "caselist": "openev",
        "camp": "Cascade Institute",
        "side": None,
        "first_seen_on_or_after": "2026-09-01",
    }


@pytest.mark.parametrize(
    "values",
    [
        {"side": Side.UNKNOWN},
        {"caselist": "hsld26", "camp": "Cascade Institute"},
        {"caselist": "Not A Slug"},
        {"camp": ""},
        {"school": "Riverbend"},
        {"team_code": "QX"},
        {"debater": "anyone"},
    ],
)
def test_search_filters_refuse_what_the_index_cannot_filter_by(values: dict[str, object]) -> None:
    """There is no filter by school, team code or debater, and an unknown key is refused."""
    with pytest.raises(ValidationError):
        SearchFilters.model_validate(values)


# ------------------------------------------------------------------------------------------------
# Cursors
# ------------------------------------------------------------------------------------------------

INDEX = "0123456789abcdef"


def binding(query: str, filters: SearchFilters | None = None, index_id: str = INDEX) -> str:
    return search_binding(index_id, parse_query(query), filters or SearchFilters())


def test_search_cursor_round_trips_its_offset_for_its_own_binding() -> None:
    bound = binding("growth")
    for offset in (0, 20, 41, MAX_CURSOR_OFFSET):
        assert decode_search_cursor(encode_search_cursor(bound, offset), bound) == offset


def test_search_cursor_binding_is_the_parsed_query_so_spacing_does_not_matter() -> None:
    assert binding("economic   growth ") == binding("economic growth")
    assert binding("economic growth") != binding("growth economic")
    assert binding("growth") != binding('"growth"')
    assert binding("growth") != binding("tag:growth")
    assert binding("growth") != binding("growth", SearchFilters(event=Event.LD))
    assert binding("growth") != binding("growth", index_id="fedcba9876543210")


@pytest.mark.parametrize(
    "other",
    [
        binding("recession"),
        binding("growth", SearchFilters(side=Side.AFF)),
        binding("growth", index_id="fedcba9876543210"),
    ],
    ids=["another-query", "other-filters", "another-index"],
)
def test_search_cursor_from_another_ranking_is_refused(other: str) -> None:
    with pytest.raises(InvalidSearchCursor):
        decode_search_cursor(encode_search_cursor(other, 20), binding("growth"))


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


@pytest.mark.parametrize(
    "cursor",
    [
        "",
        "not a cursor",
        "MjA6" + "A" * 80,
        _b64("-20:" + binding("growth")[:32]),
        _b64("020:" + binding("growth")[:32]),
        _b64("1000000:" + binding("growth")[:32]),
        _b64(f"{MAX_CURSOR_OFFSET + 1}:" + binding("growth")[:32]),
        _b64("20:" + binding("growth")[:31]),
        _b64("20:" + binding("growth")[:32].upper()),
        _b64("20:" + binding("growth")[:32] + "0"),
        _b64("20;" + binding("growth")[:32]),
        "éééé",
    ],
)
def test_search_cursor_that_is_not_one_this_module_wrote_is_refused(cursor: str) -> None:
    with pytest.raises(InvalidSearchCursor):
        decode_search_cursor(cursor, binding("growth"))


@settings(max_examples=300, deadline=None)
@given(st.text(max_size=80))
def test_search_cursor_decoder_refuses_any_string_with_its_own_error(cursor: str) -> None:
    bound = binding("growth")
    try:
        offset = decode_search_cursor(cursor, bound)
    except InvalidSearchCursor:
        return
    assert 0 <= offset <= MAX_CURSOR_OFFSET


# ------------------------------------------------------------------------------------------------
# Snippets
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "segments"),
    [
        ("", []),
        ("plain", [SnippetSegment("plain", False)]),
        (
            f"Invented {SNIPPET_OPEN}growth{SNIPPET_CLOSE} ends",
            [SnippetSegment("Invented ", False), SnippetSegment("growth", True), SnippetSegment(" ends", False)],
        ),
        (
            f"{SNIPPET_OPEN}a{SNIPPET_CLOSE}{SNIPPET_OPEN}b{SNIPPET_CLOSE}",
            [SnippetSegment("ab", True)],
        ),
        (f"x{SNIPPET_CLOSE}y{SNIPPET_OPEN}z", [SnippetSegment("xy", False), SnippetSegment("z", True)]),
    ],
)
def test_search_snippet_splits_on_its_markers_and_keeps_none(raw: str, segments: list[SnippetSegment]) -> None:
    assert snippet_segments(raw) == tuple(segments)


# ------------------------------------------------------------------------------------------------
# Card runs
# ------------------------------------------------------------------------------------------------

U, H, B = RunEmphasis.UNDERLINE, RunEmphasis.HIGHLIGHT, RunEmphasis.BOLD


def test_search_card_runs_cut_at_every_span_edge_and_join_what_looks_the_same() -> None:
    text = "Invented growth always ends badly"
    #       0123456789012345678901234567890123
    runs = card_runs(
        text,
        (
            IndexedFormattingSpan(U, 9, 15),
            IndexedFormattingSpan(U, 15, 22),
            IndexedFormattingSpan(H, 9, 15, "cyan"),
            IndexedFormattingSpan(B, 28, 33),
        ),
        (IndexedFontSizeSpan(0, 9, 16), IndexedFontSizeSpan(9, 33, 22)),
    )
    assert runs == (
        CardRun("Invented ", font_sizes=(16,)),
        CardRun("growth", emphases=(U, H), highlight_colors=("cyan",), font_sizes=(22,)),
        CardRun(" always", emphases=(U,), font_sizes=(22,)),
        CardRun(" ends ", font_sizes=(22,)),
        CardRun("badly", emphases=(B,), font_sizes=(22,)),
    )
    assert "".join(run.text for run in runs) == text


def test_search_card_runs_keep_two_overlapping_colours_and_cut_a_span_at_the_text_end() -> None:
    runs = card_runs(
        "abcdef",
        (IndexedFormattingSpan(H, 0, 4, "cyan"), IndexedFormattingSpan(H, 2, 9, "yellow")),
        (),
    )
    assert runs == (
        CardRun("ab", emphases=(H,), highlight_colors=("cyan",)),
        CardRun("cd", emphases=(H,), highlight_colors=("cyan", "yellow")),
        CardRun("ef", emphases=(H,), highlight_colors=("yellow",)),
    )
    assert card_runs("", (), ()) == ()


# ------------------------------------------------------------------------------------------------
# The provenance line
# ------------------------------------------------------------------------------------------------

SOURCE = "1" * 64
DIGEST = "2" * 64
CLUSTER = "3" * 64


def caselist_row(snapshot: str = "2026-09-15") -> OccurrenceRecord:
    return OccurrenceRecord(
        caselist="hsld26",
        snapshot=snapshot,
        last_snapshot="2026-09-22",
        source_sha256=SOURCE,
        parser_version="2026.10.18-docx-5",
        profile_version="2026.09.20-verbatim-1",
        fingerprint_version="card-fingerprint-v4",
        disclosure=DIGEST,
        first_element_index=1,
        last_element_index=3,
        exact_fingerprint=CLUSTER,
        cluster_id=CLUSTER,
        membership=ClusterMembership.NEAR_DUPLICATE,
        completeness=CardCompleteness.FULL,
    )


def camp_row(release: str = "2026-policy") -> OccurrenceRecord:
    return caselist_row().model_copy(
        update={"caselist": "openev", "snapshot": release, "last_snapshot": release, "disclosure": None, "camp": "Cascade Institute"}
    )


def disclosure(side: Side, tournament: str | None, round_raw: str | None) -> Disclosure:
    return Disclosure(
        source_sha256=SOURCE,
        caselist="hsld26",
        snapshot=date(2026, 9, 15),
        event=Event.LD,
        school="Maple Grove",
        team_code="QX",
        side=side,
        tournament=tournament,
        round_label=RoundLabel.from_raw(round_raw) if round_raw else None,
        source_path="placeholder.docx",
    )


@pytest.mark.parametrize(
    ("side", "tournament", "round_raw", "line"),
    [
        (Side.AFF, "Invented Invitational", "Round 4", "[Disclosed: hsld26 2026-09-15 — Maple Grove QX, Aff vs. Invented Invitational Round 4]"),
        (Side.NEG, None, None, "[Disclosed: hsld26 2026-09-15 — Maple Grove QX, Neg]"),
        (Side.UNKNOWN, "Invented Invitational", None, "[Disclosed: hsld26 2026-09-15 — Maple Grove QX, Invented Invitational]"),
        (Side.UNKNOWN, None, None, "[Disclosed: hsld26 2026-09-15 — Maple Grove QX]"),
    ],
)
def test_search_provenance_line_is_the_writers_line_for_a_disclosed_card(
    side: Side, tournament: str | None, round_raw: str | None, line: str
) -> None:
    """The index's fields, mapped from the records as `search_index_build._occurrence` maps them."""
    record = disclosure(side, tournament, round_raw)
    assert provenance_line(caselist_row(), record) == line
    assert (
        occurrence_provenance_line(
            caselist="hsld26",
            snapshot="2026-09-15",
            provenance=True,
            side=record.side.value,
            school=record.school,
            team_code=record.team_code,
            tournament=record.tournament,
            round_label=record.round_label.raw if record.round_label else None,
        )
        == line
    )


def test_search_provenance_line_without_a_disclosure_or_past_the_limit() -> None:
    assert provenance_line(caselist_row(), None) == "[Disclosed: hsld26 2026-09-15]"
    assert occurrence_provenance_line(caselist="hsld26", snapshot="2026-09-15", provenance=True) == (
        "[Disclosed: hsld26 2026-09-15]"
    )
    assert occurrence_provenance_line(caselist="hsld26", snapshot="2026-09-15", provenance=False) is None


def test_search_provenance_line_is_the_writers_line_for_a_camp_card() -> None:
    camp_file = CampFile(
        source_sha256=SOURCE,
        camp="Cascade Institute",
        year=2026,
        event=Event.POLICY,
        file_title="Invented Adv CP",
        snapshot=date(2026, 7, 1),
    )
    recorded = "[OpenEv: Cascade Institute 2026 — Policy, Invented Adv CP]"
    unrecorded = "[OpenEv: Cascade Institute 2026 — Policy]"
    assert provenance_line(camp_row(), None, camp_file=camp_file) == recorded
    assert provenance_line(camp_row(), None) == unrecorded
    assert (
        occurrence_provenance_line(
            caselist="openev",
            snapshot="2026-policy",
            provenance=True,
            camp="Cascade Institute",
            camp_year=2026,
            camp_event="POLICY",
            camp_file_title="Invented Adv CP",
        )
        == recorded
    )
    assert (
        occurrence_provenance_line(
            caselist="openev", snapshot="2026-policy", provenance=True, camp="Cascade Institute", camp_year=2026, camp_event="POLICY"
        )
        == unrecorded
    )
