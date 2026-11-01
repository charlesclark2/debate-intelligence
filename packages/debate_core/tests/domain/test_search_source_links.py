"""The card page's link out to where a card was published: a disclosed card's (`v1-e39-t11`) and,
since `v1-e39-t28`, a camp card's camp page on OpenEv, from the camp's OpenEv word in the alias
table and the year.

An openCaselist team page is `https://opencaselist.com/<caselist>/<school>/<team code>`, the school
and team code in the URL's own form: one word of letters, digits and hyphens. Every expected link
is written by hand (working agreement 6). Every school, team code, camp, OpenEv word and title is invented
(data-use policy, rule 5). The landscape school view links each team by the same rule, from its
caselist, school and team code (`v1-e32-t18`).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any, Final

import pytest

from debate_core.domain.evidence_search import OccurrenceProvenance
from debate_core.domain.search_source_links import (
    OPENCASELIST_ORIGIN,
    OPENEV_ARCHIVE_FIRST_YEAR,
    OPENEV_CAMP_PAGE_TEMPLATE,
    OPENEV_LABEL,
    NoTeamPage,
    SourceLink,
    source_link,
    team_page_url,
    why_no_team_page,
)

WORDS: Final = {"Cascade Institute": "CASCADE", "Ridgeline": "RDI7"}
"""An invented alias table's OpenEv words: one camp with a space in its name, one without."""
TODAY: Final = date(2026, 10, 31)
"""In the season that started on 1 August 2026, so the archive runs to 2027."""


def linked(
    occurrence: OccurrenceProvenance, *, words: Mapping[str, str] = WORDS, today: date = TODAY
) -> SourceLink | None:
    return source_link(occurrence, openev_words=words, today=today)


def disclosed(**changes: Any) -> OccurrenceProvenance:
    fields: dict[str, Any] = {
        "ordinal": 0,
        "caselist": "hsld26",
        "snapshot": "2026-09-15",
        "last_snapshot": "2026-10-13",
        "completeness": "FULL",
        "attributed": True,
        "provenance": True,
        "side": "NEG",
        "school": "Cedarbrook",
        "team_code": "LM",
        "tournament": "Invented Invitational",
        "round_label": "Round 4",
    }
    return OccurrenceProvenance(**(fields | changes))


def camp(**changes: Any) -> OccurrenceProvenance:
    fields: dict[str, Any] = {
        "ordinal": 0,
        "caselist": "openev",
        "snapshot": "2026-policy",
        "last_snapshot": "2026-policy",
        "completeness": "FULL",
        "attributed": True,
        "provenance": True,
        "camp": "Cascade Institute",
        "camp_year": 2026,
        "camp_event": "POLICY",
        "camp_file_title": "Invented Adv CP",
    }
    return OccurrenceProvenance(**(fields | changes))


def test_the_origin_is_opencaselists_own() -> None:
    assert OPENCASELIST_ORIGIN == "https://opencaselist.com"


@pytest.mark.parametrize(
    ("changes", "url"),
    [
        ({}, "https://opencaselist.com/hsld26/Cedarbrook/LM"),
        (
            {"caselist": "hspolicy26", "team_code": "AbCd"},
            "https://opencaselist.com/hspolicy26/Cedarbrook/AbCd",
        ),
        (
            {"school": "North-Cedarbrook", "team_code": "Ab12"},
            "https://opencaselist.com/hsld26/North-Cedarbrook/Ab12",
        ),
        ({"school": "Cedarbrook2"}, "https://opencaselist.com/hsld26/Cedarbrook2/LM"),
    ],
)
def test_a_disclosed_card_links_to_its_teams_page_on_opencaselist(changes: dict[str, Any], url: str) -> None:
    assert linked(disclosed(**changes)) == SourceLink(label="Open on openCaselist", url=url)


@pytest.mark.parametrize(
    "changes",
    [
        {"provenance": False, "side": None, "school": None, "team_code": None},
        {"school": None, "team_code": None},
        {"school": None},
        {"team_code": None},
        {"school": "UNKNOWN"},
        {"team_code": "UNKNOWN"},
        {"school": "Cedar Brook"},
        {"school": "Cedarbrook/../../raw"},
        {"school": "//example.test"},
        {"school": "-Cedarbrook"},
        {"school": "Cedarbrook-"},
        {"school": "Cedarbrook?x=1"},
        {"school": "Cedarbrook\n"},
        {"team_code": "LM\n"},
        {"caselist": "hsld26\n"},
        {"caselist": "openev"},
        {"school": "Cédarbrook"},
        {"school": ""},
        {"school": "C" * 101},
        {"team_code": "L M"},
        {"team_code": "LM/.."},
        {"team_code": "L" * 13},
        {"caselist": "HSLD26"},
        {"caselist": "hsld26/../x"},
        {"caselist": "https://example.test"},
    ],
    ids=lambda changes: ",".join(f"{key}={value!r}"[:40] for key, value in changes.items()),
)
def test_a_disclosed_card_whose_values_are_not_the_urls_form_has_no_link(changes: dict[str, Any]) -> None:
    """A school with a space is a display name, not the URL's form: the link would be wrong, so none."""
    assert linked(disclosed(**changes)) is None


# ------------------------------------------------------------------------------------------------
# Find on OpenEv (v1-e39-t28): a camp card links to its camp's page, the camp through the table's
# OpenEv word, and the year
# ------------------------------------------------------------------------------------------------


def test_the_openev_address_is_a_camps_page_by_year_and_word() -> None:
    """The operator confirmed `https://opencaselist.com/openev/<year>/<camp>` on 2026-10-31."""
    assert OPENEV_CAMP_PAGE_TEMPLATE == "https://opencaselist.com/openev/{year}/{word}"
    assert OPENEV_ARCHIVE_FIRST_YEAR == 2013
    assert OPENEV_LABEL == "Find on OpenEv"


@pytest.mark.parametrize(
    ("changes", "link"),
    [
        (
            {},
            SourceLink(
                label="Find on OpenEv: Cascade Institute 2026 camp page",
                url="https://opencaselist.com/openev/2026/CASCADE",
            ),
        ),
        (
            {"camp": "Ridgeline", "camp_year": 2019},
            SourceLink(
                label="Find on OpenEv: Ridgeline 2019 camp page",
                url="https://opencaselist.com/openev/2019/RDI7",
            ),
        ),
    ],
)
def test_a_camp_card_links_to_its_camps_page_through_the_tables_word(
    changes: dict[str, Any], link: SourceLink
) -> None:
    assert linked(camp(**changes)) == link


def test_the_link_is_the_tables_word_and_the_year_and_nothing_else() -> None:
    """Another title, event and OpenEv id: the same address. The stored camp is never the address."""
    first = linked(camp())
    retitled = linked(
        camp(camp_file_title="Another Invented Title", camp_event="LD", openev_id=4021, snapshot="2026-ld")
    )
    renamed = linked(camp(), words={"Cascade Institute": "CASC2"})
    one_word = linked(camp(camp="Ridgeline"))
    assert first is not None and retitled is not None and renamed is not None and one_word is not None
    assert (first.url, retitled.url, renamed.url, one_word.url) == (
        "https://opencaselist.com/openev/2026/CASCADE",
        "https://opencaselist.com/openev/2026/CASCADE",
        "https://opencaselist.com/openev/2026/CASC2",
        "https://opencaselist.com/openev/2026/RDI7",
    )


@pytest.mark.parametrize(
    ("changes", "words"),
    [
        ({"camp": "Ridgeline"}, {}),
        ({"camp": "Lakeshore"}, WORDS),
        ({"camp": "Lakeshore", "camp_file_title": "CASCADE"}, WORDS),
        ({"camp": None}, WORDS),
        ({"camp": "cascade institute"}, WORDS),
    ],
    ids=[
        "an empty table",
        "a camp the table has no word for",
        "a title that is a word",
        "no camp",
        "another case",
    ],
)
def test_a_camp_with_no_word_in_the_table_has_no_link(changes: dict[str, Any], words: dict[str, str]) -> None:
    """Never the stored camp itself, a title or another camp's word: no word, no link."""
    assert linked(camp(**changes), words=words) is None


@pytest.mark.parametrize(
    "words",
    [{"UNKNOWN": "UNKNOWN"}, {"UNKNOWN": "CASCADE"}, WORDS | {"UNKNOWN": "RDI7"}],
    ids=["its own word", "another camp's word", "beside other words"],
)
def test_unknown_never_links_whatever_the_table_says(words: dict[str, str]) -> None:
    """`UNKNOWN` is the importer's "could not read": one word, and never a camp's address."""
    assert linked(camp(camp="UNKNOWN"), words=words) is None


@pytest.mark.parametrize(
    "word",
    [
        "Cascade Inst",
        "CASCADE/..",
        "CASCADE?x=1",
        "CASCADE\n",
        "",
        "Cäscade",
        "https://example.test",
        "UNKNOWN",
    ],
    ids=lambda word: repr(word)[:20],
)
def test_a_word_that_is_not_one_address_word_has_no_link(word: str) -> None:
    """The table is checked when it is loaded; a word is checked again here, as a stored id was."""
    assert linked(camp(), words={"Cascade Institute": word}) is None


@pytest.mark.parametrize(
    ("year", "today", "url"),
    [
        (2013, TODAY, "https://opencaselist.com/openev/2013/CASCADE"),
        (2026, TODAY, "https://opencaselist.com/openev/2026/CASCADE"),
        (2027, TODAY, "https://opencaselist.com/openev/2027/CASCADE"),
        (2012, TODAY, None),
        (2028, TODAY, None),
        (2026, date(2026, 7, 31), "https://opencaselist.com/openev/2026/CASCADE"),
        (2027, date(2026, 7, 31), None),
        (2028, date(2027, 8, 1), "https://opencaselist.com/openev/2028/CASCADE"),
        (None, TODAY, None),
        (True, TODAY, None),
        ("2026", TODAY, None),
    ],
    ids=lambda value: repr(value)[:20],
)
def test_the_year_runs_from_2013_to_the_current_season_plus_one(
    year: object, today: date, url: str | None
) -> None:
    """OpenEv's sidebar starts at 2013, and a topic year's camp files arrive before its season starts."""
    link = linked(camp(camp_year=year), today=today)
    assert (link.url if link is not None else None) == url


@pytest.mark.parametrize(
    "changes",
    [
        {"provenance": False},
        {"provenance": False, "camp": None, "camp_year": None, "camp_event": None, "camp_file_title": None},
    ],
    ids=["its camp still held", "as the index keeps it"],
)
def test_a_camp_card_past_the_provenance_limit_has_no_link(changes: dict[str, Any]) -> None:
    assert linked(camp(**changes)) is None


def test_a_disclosed_card_never_links_to_openev_whatever_it_holds() -> None:
    """A disclosed occurrence given a camp, a year and an id still links to its team's page alone."""
    holding = {"camp": "Cascade Institute", "camp_year": 2026, "openev_id": 4021}
    assert linked(disclosed(**holding)) == SourceLink(
        label="Open on openCaselist", url="https://opencaselist.com/hsld26/Cedarbrook/LM"
    )
    assert linked(disclosed(**holding, school="Cedar Brook")) is None


@pytest.mark.parametrize(
    ("caselist", "school", "team_code", "url"),
    [
        ("hspolicy26", "Cedarbrook", "LM", "https://opencaselist.com/hspolicy26/Cedarbrook/LM"),
        (
            "hspolicy26",
            "North-Cedarbrook",
            "Ab12",
            "https://opencaselist.com/hspolicy26/North-Cedarbrook/Ab12",
        ),
    ],
)
def test_a_team_page_is_the_caselist_school_and_team_code_on_opencaselist(
    caselist: str, school: str, team_code: str, url: str
) -> None:
    assert why_no_team_page(caselist, school, team_code) is None
    assert team_page_url(caselist, school, team_code) == url


@pytest.mark.parametrize(
    ("caselist", "school", "team_code", "reason"),
    [
        ("hspolicy26", "UNKNOWN", "LM", NoTeamPage.UNREAD),
        ("hspolicy26", "Cedarbrook", "UNKNOWN", NoTeamPage.UNREAD),
        ("HSPolicy26", "Cedarbrook", "LM", NoTeamPage.CASELIST),
        ("hspolicy26", "Cedar Brook", "LM", NoTeamPage.SCHOOL),
        ("hspolicy26", "Cedarbrook/..", "LM", NoTeamPage.SCHOOL),
        ("hspolicy26", "Cédarbrook", "LM", NoTeamPage.SCHOOL),
        ("hspolicy26", "Cedar Brook", "L-M", NoTeamPage.SCHOOL),
        ("hspolicy26", "Cedarbrook", "L-M", NoTeamPage.TEAM_CODE),
        ("hspolicy26", "Cedarbrook", "L&M", NoTeamPage.TEAM_CODE),
        ("hspolicy26", "Cedarbrook", "L" * 13, NoTeamPage.TEAM_CODE),
    ],
)
def test_a_team_whose_values_are_not_the_urls_form_has_no_page_and_says_why(
    caselist: str, school: str, team_code: str, reason: NoTeamPage
) -> None:
    """The first part refused is the reason: the parser's `UNKNOWN`, then caselist, school and team code."""
    assert why_no_team_page(caselist, school, team_code) is reason
    assert team_page_url(caselist, school, team_code) is None


def test_the_card_page_and_the_school_view_link_a_team_alike() -> None:
    link = linked(disclosed(caselist="hspolicy26", school="North-Cedarbrook", team_code="Ab12"))
    assert link is not None
    assert link.url == team_page_url("hspolicy26", "North-Cedarbrook", "Ab12")
