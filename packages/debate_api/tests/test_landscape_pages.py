"""The landscape pages (`v1-e39-t17` ac2): the caselists, the report and the school view, for members.

Over the hand-written bundles in `fixtures/landscape/`, a signed-in student and a coach each see the
list of caselists, the newest report with one contents list and an anchor on every heading, and the
school view's front page, school pages and position pages. Every expectation below is written by
hand from those files (working agreement 6). The authorization matrix
(`test_auth_authorization_matrix.py`) refuses every other session on every landscape route.

Each page is private and never cached, loads only the pilot's own script and stylesheet with nothing
inline, offers no search, download or share link, and weighs under ADR-0019's 150 KB with a bundle
as large as hspolicy26's, measured on 2026-10-25 (the session report's counts).
"""

from __future__ import annotations

import re
from typing import Any, Final

import pytest

from debate_api.app import PRIVATE_NO_STORE

PAGE_BUDGET: Final = 150 * 1024
"""ADR-0019 (b) 1, as `test_search_pages.py` holds every search page to it: the page, its script and
its stylesheet."""

REPORT: Final = "/landscape/synthpolicy26"
SCHOOL_VIEW: Final = "/landscape/synthpolicy26/schools"
LANDSCAPE_PAGES: Final = (
    "/landscape",
    REPORT,
    SCHOOL_VIEW,
    "/landscape/synthpolicy26/schools/ashgrove",
    "/landscape/synthpolicy26/schools/birch-hollow",
    "/landscape/synthpolicy26/schools/birch-hollow-2",
    "/landscape/synthpolicy26/positions/invented-da",
    "/landscape/synthpolicy26/positions/invented-aff",
    "/landscape/synthld26",
    "/landscape/synthld26/schools",
)


@pytest.fixture(params=["student", "coach"])
def member(request: pytest.FixtureRequest, world: Any) -> Any:
    world.login.add_account(f"{request.param}.one", request.param)
    world.use_session(world.session_for(f"{request.param}.one"))
    return world


def page(world: Any, path: str, status: int = 200) -> str:
    response = world.browser.get(path)
    assert response.status_code == status, (path, response.status_code, response.text[:300])
    return response.text


def main_of(text: str) -> str:
    return text.split('<main id="main">', 1)[1].split("</main>", 1)[0]


def links_in(html: str) -> list[tuple[str, str]]:
    """Each link's address and its words, tags dropped, in order."""
    return [
        (href, re.sub(r"<[^>]+>", "", words).strip())
        for href, words in re.findall(r'<a href="([^"]*)"[^>]*>(.*?)</a>', html, re.DOTALL)
    ]


def heading_ids(html: str) -> list[str]:
    return re.findall(r'<h[1-6] id="([^"]+)"', html)


# --------------------------------------------------------------------------------------------
# What a member sees
# --------------------------------------------------------------------------------------------


def test_a_member_sees_each_caselists_newest_bundle_and_no_older_one(member: Any) -> None:
    listing = main_of(page(member, "/landscape"))

    assert links_in(listing) == [
        ("/landscape/synthld26", "the report"),
        ("/landscape/synthpolicy26", "the report"),
        ("/landscape/synthpolicy26/schools", "positions by school"),
    ]
    assert "<strong>synthld26</strong>, through 2026-10-19" in listing
    assert "<strong>synthpolicy26</strong>, through 2026-10-20" in listing
    assert "2026-10-13" not in listing


def test_a_member_reads_the_report_with_one_contents_list_of_its_parts_and_sections(member: Any) -> None:
    report = main_of(page(member, REPORT))
    contents = report.split('<nav class="landscape-contents"', 1)[1].split("</nav>", 1)[0]
    body = report.split('<div class="landscape-body">', 1)[1]

    assert "<h1>Argument landscape: synthpolicy26 through 2026-10-20</h1>" in report
    assert links_in(contents) == [
        ("#about-this-report", "About this report"),
        ("#affirmative", "Affirmative"),
        ("#affirmative-positions", "Affirmative positions"),
        ("#negative", "Negative"),
        ("#negative-positions", "Negative positions"),
        ("#counterplan-texts", "Counterplan texts"),
        ("#neither-side", "Neither side"),
        ("#overviews", "Overviews"),
        ("#unclassified", "Unclassified"),
    ]
    # The parts nest their sections: one list item per part, About this report on its own.
    assert contents.count("<ul>") == 4
    # Every heading is anchored, a repeat with -2, and the bundle's own contents list is left out.
    assert heading_ids(body) == [
        "about-this-report",
        "affirmative",
        "affirmative-positions",
        "affs",
        "negative",
        "negative-positions",
        "disadvantages",
        "counterplan-texts",
        "counterplan-texts-2",
        "neither-side",
        "overviews",
        "unclassified",
    ]
    assert report.count(">Contents</h2>") == 1
    assert "(#affirmative)" not in body and "[Affirmative]" not in body
    assert "<td>Invented DA (<code>invented-da</code>)</td>" in body
    assert '<a href="#overviews">overviews</a>' in body


def test_a_member_sees_the_school_views_front_page_listing_every_school_and_position(member: Any) -> None:
    front = main_of(page(member, SCHOOL_VIEW))

    assert "<h1>Positions by school: synthpolicy26 through 2026-10-20</h1>" in front
    assert "<td>Schools</td>\n<td>3, with 3 team codes</td>" in front
    assert links_in(front) == [
        ("/landscape", "All landscape reports"),
        ("/landscape/synthpolicy26", "The report"),
        ("#by-school", "By school"),
        ("#by-position", "By position"),
        ("/landscape/synthpolicy26/schools/ashgrove", "Ashgrove"),
        ("/landscape/synthpolicy26/schools/birch-hollow", "Birch Hollow"),
        ("/landscape/synthpolicy26/schools/birch-hollow-2", "Birch-Hollow"),
        ("/landscape/synthpolicy26/positions/invented-da", "invented-da"),
        ("/landscape/synthpolicy26/positions/invented-aff", "invented-aff"),
    ]
    assert heading_ids(front) == [
        "contents-heading",
        "by-school",
        "by-position",
        "disadvantages",
        "affirmative-side-affs",
    ]
    assert "Under each, every team that read it, by rounds." in front
    # The front page holds no school's rows: those are on the school's own page.
    assert "<td>AB</td>" not in front


def test_a_school_page_shows_that_schools_rows_and_a_repeated_anchor_is_the_other_school(member: Any) -> None:
    hollow = main_of(page(member, "/landscape/synthpolicy26/schools/birch-hollow"))
    hyphenated = main_of(page(member, "/landscape/synthpolicy26/schools/birch-hollow-2"))

    assert "<h1>Birch Hollow</h1>" in hollow
    assert "<td>CD</td>" in hollow and "<td>EF</td>" not in hollow
    assert "<h1>Birch-Hollow</h1>" in hyphenated
    assert "<td>EF</td>" in hyphenated and "<td>CD</td>" not in hyphenated
    assert links_in(hollow) == [
        ("/landscape/synthpolicy26/schools", "Positions by school: synthpolicy26 through 2026-10-20")
    ]


def test_a_position_page_links_each_team_page_in_a_new_tab_and_shows_none_as_text(member: Any) -> None:
    position = main_of(page(member, "/landscape/synthpolicy26/positions/invented-da"))

    assert "<h1><code>invented-da</code></h1>" in position
    assert "Disadvantages, in the synthpolicy26 view through 2026-10-20." in position
    new_tab = 'target="_blank" rel="noopener noreferrer"'
    assert re.findall(r"<a [^>]*>", position) == [
        '<a href="/landscape/synthpolicy26/schools">',
        f'<a href="https://opencaselist.com/synthpolicy26/Ashgrove/AB" {new_tab}>',
        f'<a href="https://opencaselist.com/synthpolicy26/Birch-Hollow/EF" {new_tab}>',
    ]
    assert '<span class="new-tab"> (opens in a new tab)</span></a>' in position
    assert "<td>Birch Hollow</td>\n<td>CD</td>\n<td>neg</td>\n<td>2</td>\n<td>none</td>" in position


def test_a_report_with_no_school_view_says_so_and_links_to_none(member: Any) -> None:
    report = main_of(page(member, "/landscape/synthld26"))
    view = main_of(page(member, "/landscape/synthld26/schools"))

    assert "/landscape/synthld26/schools" not in report
    assert "<h1>No positions by school this week</h1>" in view
    assert "it has been removed. Older weeks' views are not shown." in view


@pytest.mark.parametrize(
    "path",
    [
        "/landscape/nocaselist26",
        "/landscape/not-a-caselist",
        "/landscape/synthpolicy26/schools/oldfield",
        "/landscape/synthpolicy26/schools/Ashgrove",
        "/landscape/synthpolicy26/positions/no-such-position",
        "/landscape/synthpolicy26/positions/invented-da%20",
        "/landscape/synthld26/schools/ashgrove",
    ],
)
def test_what_is_not_in_the_newest_bundle_is_not_found(member: Any, path: str) -> None:
    text = page(member, path, status=404)

    assert "Oldfield" not in text and "<td>" not in text


# --------------------------------------------------------------------------------------------
# What every landscape page is
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("path", LANDSCAPE_PAGES)
def test_every_landscape_page_is_private_and_never_cached(member: Any, path: str) -> None:
    response = member.browser.get(path)

    assert response.headers["cache-control"] == PRIVATE_NO_STORE
    assert "etag" not in response.headers and "last-modified" not in response.headers
    assert "expires" not in response.headers


@pytest.mark.parametrize("path", LANDSCAPE_PAGES)
def test_no_landscape_page_offers_search_download_or_share(member: Any, path: str) -> None:
    text = member.browser.get(path).text

    hrefs = re.findall(r'\shref="([^"]*)"', text)
    assert [
        href for href in hrefs if href in ("/", "/search") or href.startswith(("/search?", "/download"))
    ] == []
    assert re.findall(r"<form\b[^>]*>", text) == ['<form method="post" action="/auth/sign-out">']
    for hook in ("data-tub-cart", "data-tub-download", "data-tub-copy", 'role="search"'):
        assert hook not in text, (path, hook)
    # "Share of teams" is a report column; a share link would be a link, or a hook for one.
    assert [words for _, words in links_in(text) if "share" in words.lower()] == []
    assert "data-tub-share" not in text and "navigator.share" not in text


@pytest.mark.parametrize("path", LANDSCAPE_PAGES)
def test_every_landscape_page_loads_only_the_pilots_script_and_stylesheet_with_nothing_inline(
    member: Any, path: str
) -> None:
    state = member.app.state.pilot
    text = member.browser.get(path).text

    assert re.findall(r"<script\b[^>]*>", text) == [f'<script src="{state.app_script.path}" defer>']
    assert re.findall(r"<script\b[^>]*>(.*?)</script>", text, re.DOTALL) == [""]
    assert re.findall(r"<link\b[^>]*>", text) == [
        f'<link rel="stylesheet" href="{state.app_stylesheet.path}">'
    ]
    assert "<style" not in text.lower() and "<img" not in text.lower()
    for tag in re.findall(r"<[a-zA-Z][^>]*>", text):
        assert re.search(r"\s(?:style|on[a-z]+)=", tag, re.IGNORECASE) is None, (path, tag)
        for address in re.findall(r'\s(?:src|href|action)="([^"]*)"', tag):
            own = address.startswith(("/", "#")) and not address.startswith("//")
            assert own or address.startswith("https://opencaselist.com/synthpolicy26/"), (path, address)


# --------------------------------------------------------------------------------------------
# Page weight, with a bundle as large as hspolicy26's
# --------------------------------------------------------------------------------------------

HSPOLICY26_REPORT_HTML: Final = 66_015
"""report.md's rendered size, measured from the newest hspolicy26 bundle on 2026-10-25."""
HSPOLICY26_LARGEST_SCHOOL_ROWS: Final = 117
HSPOLICY26_LARGEST_POSITION_ROWS: Final = 260
"""Above the largest position's rows in hspolicy26 (Affirmative side: Advantages held 810 over 16)."""
SCHOOLS: Final = 155


def large_report() -> str:
    lines = ["# Argument landscape: synthpolicy26 through 2026-10-20", "", "## About this report", ""]
    for part in ("Affirmative", "Negative", "Neither side"):
        lines += [f"# {part}", ""]
        for section in range(4):
            lines += [f"## {part} section {section}", "", f"### {part} kind {section}", ""]
            lines += ["| Position | Rounds | Teams | Share of teams |", "|---|---|---|---|"]
            lines += [
                f"| Invented position {section}-{row} (`invented-{section}-{row}`) | {row} | {row} | 12.5% |"
                for row in range(48)
            ]
            lines.append("")
    return "\n".join(lines)


def large_school_view() -> str:
    lines = ["# Positions by school: synthpolicy26 through 2026-10-20", "", "## By school", ""]
    for school in range(SCHOOLS):
        rows = HSPOLICY26_LARGEST_SCHOOL_ROWS if school == 0 else 12
        lines += [
            f"### Invented{school:03d}",
            "",
            "| Team code | Side | Position | Rounds |",
            "|---|---|---|---|",
        ]
        lines += [f"| T{row:03d} | neg | `invented-position-{row}` | {row} |" for row in range(rows)]
        lines.append("")
    lines += ["## By position", "", "### Disadvantages", "", "#### `invented-position-0`", ""]
    lines += ["| School | Team code | Side | Rounds | Team page |", "|---|---|---|---|---|"]
    lines += [
        f"| Invented{row:03d} | T{row:03d} | neg | 3 | "
        f"[openCaselist](https://opencaselist.com/synthpolicy26/Invented{row:03d}/T{row:03d}) |"
        for row in range(HSPOLICY26_LARGEST_POSITION_ROWS)
    ]
    return "\n".join(lines) + "\n"


def test_every_landscape_page_of_a_bundle_as_large_as_hspolicy26s_is_under_the_page_budget(
    make_world: Any, landscape_store: Any
) -> None:
    world = make_world(
        landscape_objects=landscape_store(
            {
                "reports/landscape/synthpolicy26/2026-10-20/report.md": large_report().encode(),
                "reports/landscape/synthpolicy26/2026-10-20/schools.md": large_school_view().encode(),
            }
        )
    )
    world.signed_in_student()
    state = world.app.state.pilot
    assets = len(state.app_script.content) + len(state.app_stylesheet.content)
    report = world.browser.get(REPORT).text
    weights = {
        path: len(world.browser.get(path).content) + assets
        for path in (
            REPORT,
            SCHOOL_VIEW,
            "/landscape/synthpolicy26/schools/invented000",
            "/landscape/synthpolicy26/positions/invented-position-0",
        )
    }

    assert len(main_of(report).encode()) >= HSPOLICY26_REPORT_HTML
    assert world.browser.get("/landscape/synthpolicy26/positions/invented-position-0").text.count(
        "noopener"
    ) == (HSPOLICY26_LARGEST_POSITION_ROWS)
    assert all(weight < PAGE_BUDGET for weight in weights.values()), weights
    world.services.search_index.close()
