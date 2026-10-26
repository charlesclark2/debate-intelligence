"""The landscape pages' rules (`v1-e39-t17`): bundle keys, the newest bundle, anchors and links.

Every expectation is written by hand. The pages' own tests, in `packages/debate_api/tests`, run the
same rules through the app over a moto bucket.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from debate_core.application.ports.evidence_store import ObjectInfo
from debate_core.application.tub.landscape_pages import newest_bundles
from debate_core.domain.landscape_pages import (
    Anchors,
    BundleFile,
    LandscapeLink,
    bundle_file,
    heading_anchor,
    is_position_id,
    landscape_link,
)

AT = datetime(2026, 10, 21, 6, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        (
            "reports/landscape/hspolicy26/2026-10-20/report.md",
            BundleFile("hspolicy26", date(2026, 10, 20), "report.md"),
        ),
        (
            "reports/landscape/hspolicy26/2026-10-20/schools.md",
            BundleFile("hspolicy26", date(2026, 10, 20), "schools.md"),
        ),
        ("reports/landscape/hspolicy26/2026-10-20/nested/report.md", None),
        ("reports/landscape/hspolicy26/report.md", None),
        ("reports/landscape/HSPolicy26/2026-10-20/report.md", None),
        ("reports/landscape/hspolicy26/2026-13-40/report.md", None),
        ("reports/landscape/hspolicy26/20261020/report.md", None),
        ("reports/landscape/hspolicy26/2026-10-20/", None),
        ("reports/tub/search/2026-10-20/report.md", None),
        ("xreports/landscape/hspolicy26/2026-10-20/report.md", None),
    ],
)
def test_a_bundle_file_is_read_from_its_key_or_not_at_all(key: str, expected: BundleFile | None) -> None:
    assert bundle_file(key) == expected


def info(key: str) -> ObjectInfo:
    return ObjectInfo(key=f"reports/landscape/{key}", size=10, last_modified=AT)


def test_the_newest_bundle_is_the_newest_snapshot_holding_a_report_and_its_own_school_view_only() -> None:
    listing = (
        info("hspolicy26/2026-10-13/report.md"),
        info("hspolicy26/2026-10-13/schools.md"),
        info("hspolicy26/2026-10-20/report.md"),
        info("hspolicy26/2026-10-27/schools.md"),
        info("hspolicy26/2026-10-27/positions.csv"),
        info("hsld26/2026-10-19/report.md"),
        info("hsld26/2026-10-19/schools.md"),
        info("pfapril26/2026-10-19/schools.md"),
        info("hsld26/unreadable/report.md"),
    )

    newest = newest_bundles(listing)

    assert sorted(newest) == ["hsld26", "hspolicy26"]
    # 2026-10-27 has no report.md, so its upload is not finished: 2026-10-20 is the newest bundle,
    # and 2026-10-13's school view is not shown in place of the one 2026-10-20 does not hold.
    assert newest["hspolicy26"].snapshot == date(2026, 10, 20)
    assert newest["hspolicy26"].school_view is None
    assert newest["hsld26"].school_view == info("hsld26/2026-10-19/schools.md")


@pytest.mark.parametrize(
    ("text", "anchor"),
    [
        ("Affirmative positions", "affirmative-positions"),
        (
            "Counterplan texts, alternatives and roles of the ballot",
            "counterplan-texts-alternatives-and-roles-of-the-ballot",
        ),
        ("Affirmative side: Affs", "affirmative-side-affs"),
        ("Birch-Hollow", "birch-hollow"),
        ("  St. Mary's  ", "st-marys"),
        ("Ashgrove <script>alert(3)</script>", "ashgrove-scriptalert3script"),
        ("Écoles Unies", "écoles-unies"),
        ("!!!", "section"),
    ],
)
def test_a_headings_anchor_is_githubs(text: str, anchor: str) -> None:
    assert heading_anchor(text) == anchor


def test_a_repeated_anchor_on_a_page_takes_two_then_three() -> None:
    anchors = Anchors()

    assert [anchors.add(text) for text in ("Birch Hollow", "Birch-Hollow", "birch hollow", "Oak")] == [
        "birch-hollow",
        "birch-hollow-2",
        "birch-hollow-3",
        "oak",
    ]
    assert "birch-hollow-2" in anchors and "birch-hollow-4" not in anchors


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("invented-da", True),
        ("cap-k", True),
        ("Cap-K", False),
        ("cap k", False),
        ("cap--k", False),
        ("", False),
    ],
)
def test_a_position_page_is_addressed_by_a_position_id_only(text: str, expected: bool) -> None:
    assert is_position_id(text) is expected


@pytest.mark.parametrize(
    ("href", "team_pages", "expected"),
    [
        ("#overviews", False, LandscapeLink.SAME_PAGE),
        ("#nowhere", False, None),
        ("https://opencaselist.com/hspolicy26/Ashgrove/AB", True, LandscapeLink.TEAM_PAGE),
        ("https://opencaselist.com/hspolicy26/Ashgrove/AB", False, None),
        ("https://opencaselist.com/hsld26/Ashgrove/AB", True, None),
        ("https://opencaselist.com/hspolicy26/Birch%20Hollow/CD", True, None),
        ("https://opencaselist.com/hspolicy26/Ashgrove/AB/", True, None),
        ("https://opencaselist.com/hspolicy26/Ashgrove/AB?next=x", True, None),
        ("https://opencaselist.com/hspolicy26/Ashgrove/AB#rounds", True, None),
        ("https://opencaselist.com/hspolicy26/UNKNOWN/AB", True, None),
        ("http://opencaselist.com/hspolicy26/Ashgrove/AB", True, None),
        ("https://opencaselist.com.evil.example/hspolicy26/Ashgrove/AB", True, None),
        ("https://evil.example/", True, None),
        ("/landscape/hspolicy26", True, None),
        ("javascript:alert(1)", True, None),
        ("", True, None),
    ],
)
def test_a_link_is_a_same_page_heading_a_checked_team_page_or_text(
    href: str, team_pages: bool, expected: LandscapeLink | None
) -> None:
    anchors = Anchors()
    anchors.add("Overviews")

    assert landscape_link(href, caselist="hspolicy26", anchors=anchors, team_pages=team_pages) is expected
