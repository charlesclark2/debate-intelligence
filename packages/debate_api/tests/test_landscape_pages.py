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
by part, its largest part leaving at least a quarter of the line free.
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
    ]
    assert "<td>CD</td>\n<td>neg</td>\n<td><code>invented-da</code></td>\n<td>2</td>\n<td>none</td>" in hollow
    assert "opencaselist.com" not in hollow


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
HSPOLICY26_LARGEST_SCHOOL_ROWS: Final = 117
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
    assert world.browser.get("/landscape/synthpolicy26/positions/invented-position-0").text.count(
        "noopener"
    ) == (HSPOLICY26_LARGEST_POSITION_ROWS)
    assert world.browser.get("/landscape/synthpolicy26/schools/invented000").text.count("noopener") == (
        HSPOLICY26_LARGEST_SCHOOL_ROWS
    )
    assert all(weight < PAGE_BUDGET for weight in others.values()), others
    assert max(part_weights.values()) <= (1 - HEADROOM) * PAGE_BUDGET, part_weights
    world.services.search_index.close()
