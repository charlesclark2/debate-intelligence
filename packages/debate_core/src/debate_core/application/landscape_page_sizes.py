"""How large each school-view page will be on the pilot, measured when the report is made (`v1-e32-t57`).

The PM's ruling of 2026-11-07: the dry run and the publish name every page the pilot cuts from the
bundle's `schools.md` that would send ADR-0019's budget or more, and go on (Q2): the view's front page,
each school, each team and each position (Q3). The pages are cut and rendered by
:mod:`debate_core.arguments.landscape.pages`, the pilot's own code since the move (Q4), so a page's body
is measured byte for byte as the pilot sends it; its frame is
:data:`~debate_core.domain.landscape_pages.PAGE_FRAME_ALLOWANCE`, which a `debate_api` test holds the
real frame of every page kind to.
"""

from __future__ import annotations

from debate_core.arguments.landscape.pages import render_school_view
from debate_core.domain.landscape_pages import PAGE_BUDGET, LandscapePage, PageSize, SchoolViewPageSizes

__all__ = ["measure_school_view"]


def measure_school_view(markdown: str, caselist: str, *, budget: int = PAGE_BUDGET) -> SchoolViewPageSizes:
    """Every page of `schools.md` as the pilot would cut it, by kind, heading and bytes: the front page,
    then each school followed by its teams, then each position, in the view's order."""
    view = render_school_view(markdown, caselist)
    pages = [PageSize(LandscapePage.SCHOOL_VIEW, "", _bytes(view.front_body_html))]
    for school in view.schools:
        pages.append(PageSize(LandscapePage.SCHOOL, school.heading, _bytes(school.body_html)))
        pages += [
            PageSize(LandscapePage.TEAM, team.heading, _bytes(team.body_html), school=school.heading)
            for team in school.teams
        ]
    pages += [
        PageSize(LandscapePage.POSITION, position.heading, _bytes(position.body_html))
        for kind in view.kinds
        for position in kind.positions
    ]
    return SchoolViewPageSizes(pages=tuple(pages), budget=budget)


def _bytes(html: str) -> int:
    return len(html.encode("utf-8"))
