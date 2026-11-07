"""The report's page-size check (`v1-e32-t57`, the PM's ruling of 2026-11-07, Q2 to Q4).

Every page the pilot cuts from `schools.md` is measured: the front page, each school, each team and each
position, its body's bytes and the frame allowance. A page that would send ADR-0019's budget or more is
over it. The views are hand-written with invented names, and each expected body is written by hand from
how the pilot renders Markdown (working agreement 6); `debate_api`'s tests hold the same bytes against
the pilot's own pages.
"""

from __future__ import annotations

from typing import Final

from debate_core.application.landscape_page_sizes import measure_school_view
from debate_core.domain.landscape_pages import (
    PAGE_BUDGET,
    PAGE_FRAME_ALLOWANCE,
    LandscapePage,
    PageSize,
)

SMALL: Final = """# Positions by school: synthpolicy26 through 2026-10-20

## By school

### Ab

Hi.

#### AB

- r

## By position

### Disadvantages

#### `invented-da`

P.
"""

SMALL_FRONT: Final = (
    "\n\n"
    '<h2 id="by-school">By school</h2>\n\n'
    '<ul class="landscape-index">\n'
    '<li><a href="/landscape/synthpolicy26/schools/ab">Ab</a></li>\n'
    "</ul>\n"
    '<h2 id="by-position">By position</h2>\n\n'
    '<h3 id="disadvantages">Disadvantages</h3>\n\n'
    '<ul class="landscape-index">\n'
    '<li><a href="/landscape/synthpolicy26/positions/invented-da"><code>invented-da</code></a></li>\n'
    "</ul>\n"
    "\n"
)
"""The front page's body as the pilot sends it, written out from its template's markup."""


def test_every_school_view_page_is_measured_by_kind_heading_and_body() -> None:
    sizes = measure_school_view(SMALL, "synthpolicy26")

    assert sizes.pages == (
        PageSize(LandscapePage.SCHOOL_VIEW, "", len(SMALL_FRONT.encode())),
        PageSize(LandscapePage.SCHOOL, "Ab", len("<p>Hi.</p>\n")),
        PageSize(LandscapePage.TEAM, "AB", len("<ul>\n<li>r</li>\n</ul>\n"), school="Ab"),
        PageSize(LandscapePage.POSITION, "invented-da", len("<p>P.</p>\n")),
    )
    assert sizes.pages[1].bytes == 11 + PAGE_FRAME_ALLOWANCE == 28_683
    assert (sizes.budget, sizes.over_budget) == (PAGE_BUDGET, ())
    assert sizes.largest == sizes.pages[0]
    assert sizes.largest_position == sizes.pages[3]


def test_a_body_counts_its_bytes_not_its_characters() -> None:
    sizes = measure_school_view(SMALL.replace("Hi.", "Écoles é."), "synthpolicy26")

    assert sizes.pages[1].body_bytes == len("<p>Écoles é.</p>\n".encode()) == 19


def test_a_page_at_the_budget_is_over_it_and_one_byte_under_is_not() -> None:
    """A page that would send the budget's bytes is over: the budget test holds a page under it."""
    budget = PAGE_FRAME_ALLOWANCE + len(f"<p>{'x' * 100}</p>\n")
    markdown = SMALL.replace("### Ab\n\nHi.", f"### Ab\n\n{'x' * 100}\n\n### Larch\n\n{'y' * 99}")
    sizes = measure_school_view(markdown, "synthpolicy26", budget=budget)

    schools = [page for page in sizes.pages if page.kind is LandscapePage.SCHOOL]
    assert [(page.page, page.bytes - budget) for page in schools] == [("Ab", 0), ("Larch", -1)]
    # The front page's 415 bytes of lists are over so small a budget too; the team and position are not.
    assert sizes.over_budget == (sizes.pages[0], schools[0])
    assert sizes.pages[0].body_bytes == len(SMALL_FRONT) + len(
        '<li><a href="/landscape/synthpolicy26/schools/larch">Larch</a></li>\n'
    )


def test_every_kind_of_page_over_the_budget_is_named_and_the_largest_position_is_kept() -> None:
    long_view = SMALL.replace("Hi.", "h" * 300).replace("- r", "- " + "t" * 300).replace("P.", "p" * 500)
    sizes = measure_school_view(long_view, "synthpolicy26", budget=PAGE_FRAME_ALLOWANCE + 210)

    assert [(page.kind, page.page) for page in sizes.over_budget] == [
        (LandscapePage.SCHOOL_VIEW, ""),
        (LandscapePage.SCHOOL, "Ab"),
        (LandscapePage.TEAM, "AB"),
        (LandscapePage.POSITION, "invented-da"),
    ]
    assert sizes.largest is not None and (sizes.largest.kind, sizes.largest.body_bytes) == (
        LandscapePage.POSITION,
        len(f"<p>{'p' * 500}</p>\n"),
    )
    assert sizes.largest_position == sizes.largest


def test_a_front_page_holding_every_school_is_measured_with_its_list() -> None:
    """The front page lists every school: many schools make it large, and it is named like any page."""
    schools = "".join(f"### School{number:04d}\n\nHi.\n\n" for number in range(2000))
    sizes = measure_school_view(SMALL.replace("### Ab\n\nHi.\n\n", schools), "synthpolicy26")

    front = sizes.pages[0]
    entry = len('<li><a href="/landscape/synthpolicy26/schools/school0000">School0000</a></li>\n')
    assert front.kind is LandscapePage.SCHOOL_VIEW
    assert (
        front.body_bytes
        == len(SMALL_FRONT)
        - len('<li><a href="/landscape/synthpolicy26/schools/ab">Ab</a></li>\n')
        + 2000 * entry
    )
    assert sizes.over_budget == (front,)


def test_a_view_in_no_shape_the_report_writes_is_its_front_page_alone() -> None:
    sizes = measure_school_view("# Positions by school\n\nWords.\n", "synthpolicy26")

    assert sizes.pages == (PageSize(LandscapePage.SCHOOL_VIEW, "", len("<p>Words.</p>\n\n")),)
