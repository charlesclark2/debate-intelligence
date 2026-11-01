"""The card page's link out to where a card was published: a disclosed card's (`v1-e39-t11`) and,
since `v1-e39-t16`, a camp card's file on OpenEv, from its stored OpenEv id.

An openCaselist team page is `https://opencaselist.com/<caselist>/<school>/<team code>`, the school
and team code in the URL's own form: one word of letters, digits and hyphens. Every expected link
is written by hand (working agreement 6). Every school, team code, camp and title is invented
(data-use policy, rule 5). The landscape school view links each team by the same rule, from its
caselist, school and team code (`v1-e32-t18`).
"""

from __future__ import annotations

from typing import Any

import pytest

from debate_core.domain.evidence_search import OccurrenceProvenance
from debate_core.domain.search_source_links import (
    OPENCASELIST_ORIGIN,
    OPENEV_FILE_URL_TEMPLATE,
    OPENEV_LABEL,
    NoTeamPage,
    SourceLink,
    openev_file_url,
    source_link,
    team_page_url,
    why_no_team_page,
)


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
    assert source_link(disclosed(**changes)) == SourceLink(label="Open on openCaselist", url=url)


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
    assert source_link(disclosed(**changes)) is None


# ------------------------------------------------------------------------------------------------
# Open on OpenEv (v1-e39-t16): a camp card links to its file, from the stored OpenEv id alone
# ------------------------------------------------------------------------------------------------


def test_the_openev_address_is_the_constant_this_task_set() -> None:
    """The repository pins no OpenEv page address: the shape is this constant's, until the coach's
    check on dev confirms or replaces it (`v1-e39-t16`'s report, follow-up 1)."""
    assert OPENEV_FILE_URL_TEMPLATE == "https://opencaselist.com/openev/{openev_id}"
    assert OPENEV_LABEL == "Open on OpenEv"


@pytest.mark.parametrize(
    ("openev_id", "url"),
    [
        (4021, "https://opencaselist.com/openev/4021"),
        (1, "https://opencaselist.com/openev/1"),
        (987654321, "https://opencaselist.com/openev/987654321"),
    ],
)
def test_a_camp_card_links_to_its_file_on_openev_from_the_stored_id(openev_id: int, url: str) -> None:
    assert source_link(camp(openev_id=openev_id)) == SourceLink(label="Open on OpenEv", url=url)
    assert openev_file_url(openev_id) == url


@pytest.mark.parametrize(
    "changes",
    [
        {"camp_file_title": "4021"},
        {"camp_file_title": "openev-4021 Invented Adv CP"},
        {"camp_file_title": "Invented Adv CP", "camp": "4021"},
        {"camp_file_title": None},
    ],
    ids=["a title that is a number", "a title naming an id", "a camp that is a number", "no title"],
)
def test_a_camp_card_without_a_stored_id_has_no_link_whatever_its_title_says(changes: dict[str, Any]) -> None:
    """The link is the stored value's or nothing: never read out of a title, a camp or a file name."""
    assert source_link(camp(**changes)) is None


def test_the_link_follows_the_stored_id_and_nothing_else() -> None:
    """Two cards of one file title and camp, two ids: two addresses. One id, two titles: one address."""
    first = source_link(camp(openev_id=4021, camp_file_title="Invented Adv CP"))
    second = source_link(camp(openev_id=4022, camp_file_title="Invented Adv CP"))
    renamed = source_link(camp(openev_id=4021, camp_file_title="Another Invented Title", camp="Other Camp"))
    assert first is not None and second is not None and renamed is not None
    assert (first.url, second.url, renamed.url) == (
        "https://opencaselist.com/openev/4021",
        "https://opencaselist.com/openev/4022",
        "https://opencaselist.com/openev/4021",
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"provenance": False, "camp": None, "camp_year": None, "camp_event": None, "camp_file_title": None},
        {"openev_id": 0},
        {"openev_id": -4021},
        {"openev_id": True},
    ],
    ids=["past the provenance limit", "zero", "negative", "a boolean"],
)
def test_a_camp_card_whose_stored_id_is_not_an_openev_id_has_no_link(changes: dict[str, Any]) -> None:
    assert source_link(camp(**{"openev_id": 4021} | changes)) is None


def test_a_disclosed_card_never_links_to_openev_whatever_it_holds() -> None:
    """A disclosed occurrence has no OpenEv id; given one, it still links to its team's page alone."""
    assert source_link(disclosed(openev_id=4021)) == SourceLink(
        label="Open on openCaselist", url="https://opencaselist.com/hsld26/Cedarbrook/LM"
    )
    assert source_link(disclosed(openev_id=4021, school="Cedar Brook")) is None


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
    link = source_link(disclosed(caselist="hspolicy26", school="North-Cedarbrook", team_code="Ab12"))
    assert link is not None
    assert link.url == team_page_url("hspolicy26", "North-Cedarbrook", "Ab12")
