"""The landscape pages (`v1-e39-t17` ac2): the caselists, the report and the school view, for members.

Over the hand-written bundles in `fixtures/landscape/`, a signed-in student and a coach each see the
list of caselists; the newest report's front page, its header and one contents list, and one page per
`#` part with an anchor on every heading (the PM's review of 2026-10-26); and the school view's front
page, school pages and position pages. Every expectation below is written by
hand from those files (working agreement 6). The authorization matrix
(`test_auth_authorization_matrix.py`) refuses every other session on every landscape route.

Each page is private and never cached, loads only the pilot's own script and stylesheet with nothing
inline, offers no search, download or share link in its body (the header is the site's, Search link
and cart included), and weighs under ADR-0019's 150 KB with a bundle as large as hspolicy26's, part
by part, its largest part leaving at least a quarter of the line free. Since `v1-e32-t57`, the largest
school page and team page stay under it at today's size and at the size projected for the season's last
snapshot, and every school-view page's frame is within the report check's allowance.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final

import pytest

from debate_api.app import PRIVATE_NO_STORE
from debate_core.application.landscape_page_sizes import measure_school_view
from debate_core.application.landscape_report import LandscapeReportService
from debate_core.arguments.landscape.render import render_schools_markdown
from debate_core.domain.landscape_pages import PAGE_FRAME_ALLOWANCE, LandscapePage, heading_anchor
from debate_core.domain.landscape_schools import RoundStance, SchoolRound, SchoolRow, SchoolSide
from debate_core.testing.landscape_report import read_synthetic_caselist, synthetic_staleness

PAGE_BUDGET: Final = 150 * 1024
"""ADR-0019 (b) 1, as `test_search_pages.py` holds every search page to it: the page, its script and
its stylesheet."""

REPORT: Final = "/landscape/synthpolicy26"
PARTS: Final = (
    "/landscape/synthpolicy26/report/affirmative",
    "/landscape/synthpolicy26/report/negative",
    "/landscape/synthpolicy26/report/neither-side",
)
SCHOOL_VIEW: Final = "/landscape/synthpolicy26/schools"
LANDSCAPE_PAGES: Final = (
    "/landscape",
    REPORT,
    *PARTS,
    SCHOOL_VIEW,
    "/landscape/synthpolicy26/schools/ashgrove",
    "/landscape/synthpolicy26/schools/birch-hollow",
    "/landscape/synthpolicy26/schools/birch-hollow-2",
    "/landscape/synthpolicy26/schools/birch-hollow-2/ef",
    "/landscape/synthpolicy26/positions/invented-da",
    "/landscape/synthpolicy26/positions/invented-aff",
    "/landscape/synthld26",
    "/landscape/synthld26/schools",
)


@pytest.fixture
def world(landscape_world: Any) -> Any:
    """This file's world: sign-in and the landscape pages (`v1-e39-t20`)."""
    return landscape_world


@pytest.fixture
def make_world(make_landscape_world: Any) -> Any:
    return make_landscape_world


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


def test_the_reports_front_page_holds_its_header_and_one_contents_list_linking_to_its_parts(
    member: Any,
) -> None:
    report = main_of(page(member, REPORT))
    contents = report.split('<nav class="landscape-contents"', 1)[1].split("</nav>", 1)[0]
    body = report.split('<div class="landscape-body">', 1)[1]

    assert "<h1>Argument landscape: synthpolicy26 through 2026-10-20</h1>" in report
    assert links_in(contents) == [
        ("#about-this-report", "About this report"),
        ("/landscape/synthpolicy26/report/affirmative", "Affirmative"),
        ("/landscape/synthpolicy26/report/affirmative#affirmative-positions", "Affirmative positions"),
        ("/landscape/synthpolicy26/report/negative", "Negative"),
        ("/landscape/synthpolicy26/report/negative#negative-positions", "Negative positions"),
        ("/landscape/synthpolicy26/report/negative#counterplan-texts", "Counterplan texts"),
        ("/landscape/synthpolicy26/report/neither-side", "Neither side"),
        ("/landscape/synthpolicy26/report/neither-side#overviews", "Overviews"),
        ("/landscape/synthpolicy26/report/neither-side#unclassified", "Unclassified"),
    ]
    # The parts nest their sections: one list item per part, About this report on its own.
    assert contents.count("<ul>") == 4
    # The header alone: no part's sections, and not the bundle's own contents list.
    assert heading_ids(body) == ["about-this-report"]
    assert "<td>Caselist</td>\n<td>synthpolicy26</td>" in body
    assert report.count(">Contents</h2>") == 1
    assert "(#affirmative)" not in body and "[Affirmative]" not in body
    assert "Invented DA" not in body and "Invented aff" not in body


@pytest.mark.parametrize(
    ("path", "heading", "ids", "holds"),
    [
        (
            PARTS[0],
            "Affirmative",
            ["affirmative-positions", "affs"],
            "<td>Invented aff (<code>invented-aff</code>)</td>",
        ),
        (
            PARTS[1],
            "Negative",
            ["negative-positions", "disadvantages", "counterplan-texts", "counterplan-texts-2"],
            "<td>Invented DA (<code>invented-da</code>)</td>",
        ),
        (PARTS[2], "Neither side", ["overviews", "unclassified"], '<a href="#overviews">overviews</a>'),
    ],
)
def test_each_part_is_its_own_page_with_every_heading_anchored(
    member: Any, path: str, heading: str, ids: list[str], holds: str
) -> None:
    part = main_of(page(member, path))
    body = part.split('<div class="landscape-body">', 1)[1]

    assert f"<h1>{heading}</h1>" in part
    assert heading_ids(body) == ids
    assert holds in body
    assert links_in(part)[:4] == [
        ("/landscape/synthpolicy26", "Argument landscape: synthpolicy26 through 2026-10-20"),
        ("/landscape/synthpolicy26/report/affirmative", "Affirmative"),
        ("/landscape/synthpolicy26/report/negative", "Negative"),
        ("/landscape/synthpolicy26/report/neither-side", "Neither side"),
    ]
    assert part.count('aria-current="page"') == 1


def test_every_contents_link_lands_on_a_heading_of_its_part(member: Any) -> None:
    contents = (
        main_of(page(member, REPORT)).split('<nav class="landscape-contents"', 1)[1].split("</nav>", 1)[0]
    )
    landed = []
    for href, _ in links_in(contents):
        if "#" in href and not href.startswith("#"):
            path, anchor = href.split("#", 1)
            assert f'id="{anchor}"' in page(member, path), href
            landed.append(href)

    assert len(landed) == 5


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


def test_a_school_page_links_each_team_page_in_a_new_tab_and_shows_none_as_text(member: Any) -> None:
    """`v1-e32-t23`: the by-school table's team page column, checked as the position page's is."""
    ashgrove = main_of(page(member, "/landscape/synthpolicy26/schools/ashgrove"))
    hollow = main_of(page(member, "/landscape/synthpolicy26/schools/birch-hollow"))
    hyphenated = main_of(page(member, "/landscape/synthpolicy26/schools/birch-hollow-2"))

    new_tab = 'target="_blank" rel="noopener noreferrer"'
    team_page = f'<a href="https://opencaselist.com/synthpolicy26/Ashgrove/AB" {new_tab}>'
    assert re.findall(r"<a [^>]*>", ashgrove) == [
        '<a href="/landscape/synthpolicy26/schools">',
        team_page,
        team_page,
    ]
    assert ashgrove.count('openCaselist<span class="new-tab"> (opens in a new tab)</span></a>') == 2
    assert "<th>Team page</th>" in ashgrove
    assert re.findall(r"<a [^>]*>", hyphenated) == [
        '<a href="/landscape/synthpolicy26/schools">',
        f'<a href="https://opencaselist.com/synthpolicy26/Birch-Hollow/EF" {new_tab}>',
        '<a href="/landscape/synthpolicy26/schools/birch-hollow-2/ef">',
    ]
    assert "<td>CD</td>\n<td>neg</td>\n<td><code>invented-da</code></td>\n<td>2</td>\n<td>none</td>" in hollow
    assert "opencaselist.com" not in hollow


SYNTHETIC_CASELIST: Final = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "landscape" / "synthetic_caselist"
)


def _core_world(make_world: Any, landscape_store: Any) -> Any:
    """The pilot over schools.md as debate_core renders the synthetic caselist."""
    files = (
        LandscapeReportService()
        .bundle(read_synthetic_caselist(SYNTHETIC_CASELIST), synthetic_staleness())
        .files
    )
    world = make_world(
        landscape_objects=landscape_store(
            {
                f"reports/landscape/synthpolicy26/2026-09-15/{name}": files[name].encode()
                for name in ("report.md", "schools.md")
            }
        )
    )
    world.signed_in_student()
    return world


def test_a_school_page_lists_its_teams_each_linking_its_openCaselist_page_and_its_own_page(
    make_world: Any, landscape_store: Any
) -> None:
    """`v1-e32-t57` (the PM's ruling of 2026-11-07, Q1): the school's table, less its team page column,
    then its teams, each with its openCaselist link and a link to its own page. Its rounds are not here."""
    world = _core_world(make_world, landscape_store)
    birchmoor = main_of(page(world, "/landscape/synthpolicy26/schools/birchmoor"))
    ashgrove = main_of(page(world, "/landscape/synthpolicy26/schools/ashgrove-fictional"))

    new_tab = 'target="_blank" rel="noopener noreferrer"'
    assert links_in(birchmoor) == [
        ("/landscape/synthpolicy26/schools", "Positions by school: synthpolicy26 through 2026-09-15"),
        ("/landscape/synthpolicy26/schools/birchmoor/qq", "round by round"),
        ("https://opencaselist.com/synthpolicy26/Birchmoor/QQ", "openCaselist (opens in a new tab)"),
        ("/landscape/synthpolicy26/schools/birchmoor/zz", "round by round"),
        ("https://opencaselist.com/synthpolicy26/Birchmoor/ZZ", "openCaselist (opens in a new tab)"),
    ]
    assert f'<a href="https://opencaselist.com/synthpolicy26/Birchmoor/QQ" {new_tab}>' in birchmoor
    assert "<th>Team page</th>" not in birchmoor
    assert "<td>QQ</td>\n<td>aff</td>\n<td><code>condo-bad</code></td>\n<td>1</td>\n</tr>" in birchmoor
    assert (
        '<li>XX: <a href="/landscape/synthpolicy26/schools/ashgrove-fictional/xx">round by round</a>, '
        "no openCaselist page</li>"
    ) in ashgrove
    assert "Imaginary Classic" not in ashgrove and "<h4" not in ashgrove, "the rounds are on the team's page"
    world.services.search_index.close()


def test_a_team_page_lists_that_teams_rounds_under_its_positions_as_the_report_writes_them(
    make_world: Any, landscape_store: Any
) -> None:
    """`v1-e32-t54`'s lines, on the team's own page since `v1-e32-t57`, which links back to its school."""
    world = _core_world(make_world, landscape_store)
    xx = main_of(page(world, "/landscape/synthpolicy26/schools/ashgrove-fictional/xx"))
    yy = main_of(page(world, "/landscape/synthpolicy26/schools/ashgrove-fictional/yy"))

    assert "<h1>XX</h1>" in xx
    assert links_in(xx) == [
        ("/landscape/synthpolicy26/schools", "Positions by school: synthpolicy26 through 2026-09-15"),
        ("/landscape/synthpolicy26/schools/ashgrove-fictional", "Ashgrove Fictional"),
    ]
    assert "Ashgrove Fictional's team, in the synthpolicy26 view through 2026-09-15." in xx
    assert (
        "<li><code>spending-da</code> (answers only)\n<ul>\n"
        "<li>Imaginary Classic, R1, aff, AT (one file for 2 rounds)</li>\n"
        "<li>Fictional Invitational, R1, aff, AT (one file for 2 rounds)</li>\n</ul>\n</li>"
    ) in xx
    assert "<li>Fictional Invitational, R1, neg, AT</li>" in yy, "YY answers the Costs advantage"
    assert "Fictional Invitational, R1, neg, AT" not in xx and "<table>" not in xx
    world.services.search_index.close()


def test_a_team_heading_never_makes_a_school_page_and_a_team_is_found_only_under_its_school(
    make_world: Any, landscape_store: Any
) -> None:
    world = _core_world(make_world, landscape_store)
    front = main_of(page(world, SCHOOL_VIEW))

    assert [words for href, words in links_in(front) if "/schools/" in href] == [
        "Ashgrove Fictional",
        "Birchmoor",
        "Cedarvale Fictional",
        "Driftwood Fictional",
    ]
    assert "round by round" not in front, "the front page holds no school's teams"
    page(world, "/landscape/synthpolicy26/schools/xx", 404)
    page(world, "/landscape/synthpolicy26/schools/birchmoor/xx", 404)
    page(world, "/landscape/synthpolicy26/schools/no-such-school/xx", 404)
    world.services.search_index.close()


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
        "/landscape/synthpolicy26/report/no-such-part",
        "/landscape/synthpolicy26/report/Negative",
        "/landscape/synthld26/report/affirmative",
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
def test_no_landscape_page_body_offers_search_download_or_share(member: Any, path: str) -> None:
    body = main_of(member.browser.get(path).text)

    hrefs = re.findall(r'\shref="([^"]*)"', body)
    assert [
        href for href in hrefs if href in ("/", "/search") or href.startswith(("/search?", "/download"))
    ] == []
    assert re.findall(r"<form\b[^>]*>", body) == []
    for hook in ("data-tub-cart", "data-tub-download", "data-tub-copy", 'role="search"', "download="):
        assert hook not in body, (path, hook)
    # "Share of teams" is a report column; a share link would be a link, or a hook for one.
    assert [words for _, words in links_in(body) if "share" in words.lower()] == []
    assert "data-tub-share" not in body and "navigator.share" not in body


@pytest.mark.parametrize("path", LANDSCAPE_PAGES)
def test_every_landscape_page_has_the_sites_own_header_with_its_search_link_and_cart(
    member: Any, path: str
) -> None:
    header = member.browser.get(path).text.split('<main id="main">', 1)[0]

    assert '<p class="site-name"><a href="/">Team evidence search</a></p>' in header
    assert '<li><a href="/">Search</a></li>' in header
    assert '<li><a href="/landscape">Landscape</a></li>' in header
    assert "data-tub-cart " in header


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

HSPOLICY26_PART_HTML: Final = {"Affirmative": 45_095, "Negative": 56_893, "Neither side": 8_720}
"""Each `#` part's rendered size, from the newest hspolicy26 bundle as republished in `v1-e32-t20`'s
shape (2026-10-25 02:11), measured on 2026-10-26 through `render_bundle`."""
PART_ROWS: Final = {"Affirmative": 100, "Negative": 126, "Neither side": 18}
"""Rows per section that size each synthetic part just above its hspolicy26 figure."""
HEADROOM: Final = 0.25
"""The PM's review of 2026-10-26: the largest part leaves at least a quarter of the line free."""
HSPOLICY26_LARGEST_SCHOOL_ROWS: Final = 151
HSPOLICY26_LARGEST_SCHOOL_LINES: Final = 1_158
HSPOLICY26_LARGEST_SCHOOL_HTML: Final = 121_739
"""The largest school page in hspolicy26 with `v1-e32-t54`'s rounds under each position: its table's
rows, its round lines and its body's bytes, measured over the operator's landscape copy (snapshot
2026-11-03) through `render_bundle` on 2026-11-06. One school page of 185 was over 100 KB."""
HSPOLICY26_LARGEST_POSITION_ROWS: Final = 260
"""Above the largest position's rows in hspolicy26 (Affirmative side: Advantages held 810 over 16)."""
SCHOOLS: Final = 155


def large_report() -> str:
    lines = ["# Argument landscape: synthpolicy26 through 2026-10-20", "", "## About this report", ""]
    for part, rows in PART_ROWS.items():
        lines += [f"# {part}", ""]
        for section in range(4):
            lines += [f"## {part} section {section}", "", f"### {part} kind {section}", ""]
            lines += ["| Position | Rounds | Teams | Share of teams |", "|---|---|---|---|"]
            lines += [
                f"| Invented position {section}-{row} (`invented-{section}-{row}`) | {row} | {row} | 12.5% |"
                for row in range(rows)
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
            "| Team code | Side | Position | Rounds | Team page |",
            "|---|---|---|---|---|",
        ]
        lines += [
            f"| T{row:03d} | neg | `invented-position-{row}` | {row} | "
            f"[openCaselist](https://opencaselist.com/synthpolicy26/Invented{school:03d}/T{row:03d}) |"
            for row in range(rows)
        ]
        lines.append("")
        if school == 0:
            lines += large_school_rounds()
    lines += ["## By position", "", "### Disadvantages", "", "#### `invented-position-0`", ""]
    lines += ["| School | Team code | Side | Rounds | Team page |", "|---|---|---|---|---|"]
    lines += [
        f"| Invented{row:03d} | T{row:03d} | neg | 3 | "
        f"[openCaselist](https://opencaselist.com/synthpolicy26/Invented{row:03d}/T{row:03d}) |"
        for row in range(HSPOLICY26_LARGEST_POSITION_ROWS)
    ]
    return "\n".join(lines) + "\n"


def large_school_rounds() -> list[str]:
    """The largest school's round lines, as schools.md writes them: up to six rounds under each position."""
    lines: list[str] = []
    for line in range(HSPOLICY26_LARGEST_SCHOOL_LINES):
        team, position, nth = line // 60, line // 6 % 10, line % 6
        if line % 60 == 0:
            lines += ["", f"**T{team:03d}, round by round** (newest snapshot first)", ""]
        if nth == 0:
            lines.append(
                f"- `invented-position-{team}-{position}`" + (" (answers only)" if position > 4 else "")
            )
        lines.append(
            f"  - Invented {team:02d}-{position}-{nth}, Quarters, neg, "
            + ("AT" if position > 4 else "reads")
            + (" (one file for 3 rounds)" if nth % 2 else "")
        )
    return [*lines, ""]


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
    part_paths = {
        part: f"/landscape/synthpolicy26/report/{part.lower().replace(' ', '-')}" for part in PART_ROWS
    }
    parts = {part: world.browser.get(path) for part, path in part_paths.items()}
    others = {
        path: len(world.browser.get(path).content) + assets
        for path in (
            REPORT,
            SCHOOL_VIEW,
            "/landscape/synthpolicy26/schools/invented000",
            "/landscape/synthpolicy26/positions/invented-position-0",
        )
    }
    part_weights = {part: len(response.content) + assets for part, response in parts.items()}

    for part, response in parts.items():
        body = main_of(response.text).split('<div class="landscape-body">', 1)[1]
        assert len(body.encode()) >= HSPOLICY26_PART_HTML[part], part
    largest = main_of(world.browser.get("/landscape/synthpolicy26/schools/invented000").text)
    assert largest.count("<li>") - largest.count("<li><code>") >= HSPOLICY26_LARGEST_SCHOOL_LINES
    body = largest.split('<div class="landscape-body">', 1)[1]
    assert len(body.encode()) >= HSPOLICY26_LARGEST_SCHOOL_HTML
    assert world.browser.get("/landscape/synthpolicy26/positions/invented-position-0").text.count(
        "noopener"
    ) == (HSPOLICY26_LARGEST_POSITION_ROWS)
    assert world.browser.get("/landscape/synthpolicy26/schools/invented000").text.count("noopener") == (
        HSPOLICY26_LARGEST_SCHOOL_ROWS
    )
    assert all(weight < PAGE_BUDGET for weight in others.values()), others
    assert max(part_weights.values()) <= (1 - HEADROOM) * PAGE_BUDGET, part_weights
    world.services.search_index.close()


# --------------------------------------------------------------------------------------------
# The largest school page and team page, today and at the season's last snapshot (v1-e32-t57)
# --------------------------------------------------------------------------------------------

TODAY_LINES: Final = HSPOLICY26_LARGEST_SCHOOL_LINES
TODAY_TEAM_LINES: Final = 257
"""hspolicy26's largest team's round lines on 2026-11-03 (`v1-e32-t54`'s counts: lines per team, max 257)."""
SEASON_END_LINES: Final = 3_474
"""The largest school's lines at the season's last snapshot, 2027-06-29: 1,158 + 34 snapshots of 68.1
(`config/landscape/topics.yaml` puts hspolicy26 on to 2027-06-30; the PM's ruling of 2026-11-07)."""
SEASON_END_TEAM_LINES: Final = 771
"""The largest team's 257 lines over 17 snapshots, at the same rate over 51."""
SEASON_END_ROWS: Final = 453
"""151 rows over 17 snapshots at the same rate over 51: an upper bound, since a team's positions repeat."""
REAL_BYTES_PER_LINE: Final = 69.4
"""`v1-e32-t54`'s estimate of a real round line's bytes on the old school page, its share of the position
and team lines included: the synthetic team page's lines are held at least that large."""
LINES_PER_TEAM: Final = 60
SIZES: Final = {
    "today": (HSPOLICY26_LARGEST_SCHOOL_ROWS, TODAY_LINES, TODAY_TEAM_LINES),
    "today-lines-season-end-rows": (SEASON_END_ROWS, TODAY_LINES, TODAY_TEAM_LINES),
    "season-end-lines-today-rows": (HSPOLICY26_LARGEST_SCHOOL_ROWS, SEASON_END_LINES, SEASON_END_TEAM_LINES),
    "season-end": (SEASON_END_ROWS, SEASON_END_LINES, SEASON_END_TEAM_LINES),
}


def _teams(lines: int, largest: int) -> list[int]:
    """Each team's round lines: the largest team first, then teams of sixty, then what is left."""
    rest = lines - largest
    return [
        largest,
        *[LINES_PER_TEAM] * (rest // LINES_PER_TEAM),
        *([rest % LINES_PER_TEAM] if rest % LINES_PER_TEAM else []),
    ]


def _largest_school_view(rows: int, lines: int, largest_team: int) -> str:
    """schools.md as debate_core writes it, for one invented school of `rows` rows and `lines` round lines,
    its largest team `largest_team` of them: lines as `v1-e32-t54`'s budget test wrote them, with a word
    more in the tournament so a line is no smaller than a real one."""
    bundle = LandscapeReportService().bundle(
        read_synthetic_caselist(SYNTHETIC_CASELIST), synthetic_staleness()
    )
    teams = _teams(lines, largest_team)
    round_lines: list[SchoolRound] = []
    for team, count in enumerate(teams):
        for line in range(count):
            position, nth = line // 6, line % 6
            round_lines.append(
                SchoolRound(
                    school="Invented000",
                    team_code=f"T{team:03d}",
                    position_id=f"invented-position-{team}-{position}",
                    stance=RoundStance.AT if position % 10 > 4 else RoundStance.READS,
                    side=SchoolSide.NEG,
                    tournament=f"Invented Open {team:02d}-{position % 10}-{nth}",
                    round_label="Quarters",
                    snapshot=bundle.schools.snapshot,
                    rounds_in_file=3 if nth % 2 else 1,
                    answers_only=position % 10 > 4,
                )
            )
    table = [
        SchoolRow(
            school="Invented000",
            team_code=f"T{row % len(teams):03d}",
            side=SchoolSide.NEG,
            position_id=f"invented-position-{row % len(teams)}-{row}",
            rounds=row + 1,
        )
        for row in range(rows)
    ]
    table.sort(key=lambda row: row.team_code)
    view = bundle.schools.model_copy(update={"rows": tuple(table), "round_lines": tuple(round_lines)})
    return render_schools_markdown(view, bundle.report)


@pytest.mark.parametrize("size", list(SIZES))
def test_the_largest_school_page_and_team_page_stay_under_the_budget_today_and_at_the_seasons_end(
    make_world: Any, landscape_store: Any, size: str
) -> None:
    """The PM's ruling of 2026-11-07: the largest school page, its table and its list of teams, and the
    largest team's page, at today's size and the size projected for 2027-06-29, rows at 151 and at 453."""
    rows, lines, largest_team = SIZES[size]
    markdown = _largest_school_view(rows, lines, largest_team)
    world = make_world(
        landscape_objects=landscape_store(
            {
                "reports/landscape/synthpolicy26/2026-09-15/report.md": large_report().encode(),
                "reports/landscape/synthpolicy26/2026-09-15/schools.md": markdown.encode(),
            }
        )
    )
    world.signed_in_student()
    state = world.app.state.pilot
    assets = len(state.app_script.content) + len(state.app_stylesheet.content)
    school = world.browser.get("/landscape/synthpolicy26/schools/invented000")
    team = world.browser.get("/landscape/synthpolicy26/schools/invented000/t000")
    assert (school.status_code, team.status_code) == (200, 200)
    school_main, team_main = main_of(school.text), main_of(team.text)

    assert school_main.count("<tr>") - 1 == rows
    assert school_main.count("round by round</a>") == len(_teams(lines, largest_team))
    assert team_main.count("<li>") - team_main.count("<li><code>") == largest_team
    team_body = team_main.split('<div class="landscape-body">', 1)[1]
    assert len(team_body.encode()) >= REAL_BYTES_PER_LINE * largest_team, "lines as large as real ones"
    weights = {"school": len(school.content) + assets, "team": len(team.content) + assets}
    assert all(weight < PAGE_BUDGET for weight in weights.values()), weights
    # The report's check measures the same two pages at no fewer bytes than the pilot sends.
    measured = {
        page.kind: page.bytes
        for page in measure_school_view(markdown, "synthpolicy26").pages
        if (page.kind, page.page) in ((LandscapePage.SCHOOL, "Invented000"), (LandscapePage.TEAM, "T000"))
    }
    assert (
        measured[LandscapePage.SCHOOL] >= weights["school"]
        and measured[LandscapePage.TEAM] >= weights["team"]
    )
    world.services.search_index.close()


LONG: Final = "Invented " * 18
"""A heading of 162 characters: three times the longest school name a real page is likely to carry."""


def _long_headings_view() -> str:
    return f"""# Positions by school: {LONG}through 2026-09-15

## By school

### {LONG}School

Each team's rounds, on a page of its own:

- {LONG}Team: [round by round](#{LONG.lower().replace(" ", "-")}team)

#### {LONG}Team

- `invented-da`
  - Invented Open, Quarters, neg, reads

## By position

### Disadvantages

#### `invented-da`

| School | Team code | Side | Rounds | Team page |
|---|---|---|---|---|
| {LONG}School | {LONG}Team | neg | 1 | none |
"""


def test_every_school_view_pages_frame_with_a_long_heading_is_within_the_allowance(
    make_world: Any, landscape_store: Any
) -> None:
    """The PM's ruling of 2026-11-07, Q4: what a page sends besides the body the report measures, its
    header, chrome and headings and the pilot's script and stylesheet, is at most the allowance, so the
    check never measures a page smaller than the pilot sends it."""
    markdown = _long_headings_view()
    world = make_world(
        landscape_objects=landscape_store(
            {
                "reports/landscape/synthpolicy26/2026-09-15/report.md": large_report().encode(),
                "reports/landscape/synthpolicy26/2026-09-15/schools.md": markdown.encode(),
            }
        )
    )
    world.signed_in_student()
    state = world.app.state.pilot
    assets = len(state.app_script.content) + len(state.app_stylesheet.content)
    school = heading_anchor(f"{LONG}School")
    paths = {
        LandscapePage.SCHOOL_VIEW: SCHOOL_VIEW,
        LandscapePage.SCHOOL: f"/landscape/synthpolicy26/schools/{school}",
        LandscapePage.TEAM: f"/landscape/synthpolicy26/schools/{school}/{heading_anchor(f'{LONG}Team')}",
        LandscapePage.POSITION: "/landscape/synthpolicy26/positions/invented-da",
    }
    measured = {page.kind: page for page in measure_school_view(markdown, "synthpolicy26").pages}

    frames = {}
    for kind, path in paths.items():
        response = world.browser.get(path)
        assert response.status_code == 200, path
        assert LONG.strip() in response.text, path
        frames[kind] = len(response.content) + assets - measured[kind].body_bytes
        assert measured[kind].bytes >= len(response.content) + assets, kind
    assert set(frames) == set(LandscapePage) - {
        LandscapePage.CASELISTS,
        LandscapePage.REPORT,
        LandscapePage.REPORT_PART,
    }
    assert max(frames.values()) <= PAGE_FRAME_ALLOWANCE, frames
    world.services.search_index.close()
