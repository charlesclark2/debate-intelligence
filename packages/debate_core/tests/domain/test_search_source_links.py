"""The card page's link out to where a disclosed card was published (`v1-e39-t11`).

An openCaselist team page is `https://opencaselist.com/<caselist>/<school>/<team code>`, the school
and team code in the URL's own form: one word of letters, digits and hyphens. Every expected link
is written by hand (working agreement 6). Every school, team code, camp and title is invented
(data-use policy, rule 5).
"""

from __future__ import annotations

from typing import Any

import pytest

from debate_core.domain.evidence_search import OccurrenceProvenance
from debate_core.domain.search_source_links import OPENCASELIST_ORIGIN, SourceLink, source_link


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


def test_a_camp_card_has_no_link_because_the_index_stores_no_openev_file_address() -> None:
    """The index keeps a camp card's camp, year, event and file title, and no OpenEv path or id."""
    assert source_link(camp()) is None
    assert source_link(camp(camp_file_title=None)) is None
