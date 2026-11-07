"""The school view's cut into pages (`v1-e32-t57`, the PM's ruling of 2026-11-07, Q1).

A school is a `###` heading under "By school", and each `####` heading inside it is one of that school's
teams, on a page of its own: never a school page. A link in the school's list to a team's heading goes
to the team's page. Every view below is written by hand, with invented schools and team codes, and so is
every expectation (working agreement 6).
"""

from __future__ import annotations

from typing import Final

from debate_core.arguments.landscape.pages import render_school_view

TWO_SCHOOLS: Final = """# Positions by school: synthpolicy26 through 2026-10-20

## By school

The lead.

### Ab

| Team code | Side | Position | Rounds |
|---|---|---|---|
| AB | neg | `invented-da` | 3 |

Each team's rounds, on a page of its own:

- AB: [round by round](#ab-2), [openCaselist](https://opencaselist.com/synthpolicy26/Ab/AB)

#### AB

- `invented-da`
  - Imaginary Classic, R1, neg, reads

### Larkspur

| Team code | Side | Position | Rounds |
|---|---|---|---|
| AB | aff | `invented-aff` | 1 |

Each team's rounds, on a page of its own:

- AB: [round by round](#ab-3), no openCaselist page
- CD: [round by round](#cd), no openCaselist page
- Elsewhere: [another school's team](#ab-2)

#### AB

- `invented-aff`
  - Fictional Open, Octas, aff, reads

##### A deeper heading

Stays on AB's page.

#### CD

- `invented-da` (answers only)
  - Fictional Open, R2, neg, AT

## By position

### Disadvantages

#### `invented-da`

| School | Team code | Side | Rounds | Team page |
|---|---|---|---|---|
| Ab | AB | neg | 3 | none |
"""


def test_a_fourth_level_heading_is_a_team_of_its_school_and_never_a_school_page() -> None:
    view = render_school_view(TWO_SCHOOLS, "synthpolicy26")

    assert [(school.heading, school.path) for school in view.schools] == [
        ("Ab", "ab"),
        ("Larkspur", "larkspur"),
    ]
    assert view.school("ab-2") is None and view.school("cd") is None
    assert [(team.heading, team.path) for team in view.schools[0].teams] == [("AB", "ab")]
    assert [(team.heading, team.path) for team in view.schools[1].teams] == [("AB", "ab"), ("CD", "cd")]


def test_a_team_page_holds_that_teams_rounds_and_its_deeper_headings_and_the_school_page_none() -> None:
    view = render_school_view(TWO_SCHOOLS, "synthpolicy26")
    larkspur = view.school("larkspur")
    assert larkspur is not None
    ab, cd = view.team("larkspur", "ab"), view.team("larkspur", "cd")
    assert ab is not None and cd is not None

    assert ab.body_html == (
        "<ul>\n<li><code>invented-aff</code>\n<ul>\n"
        "<li>Fictional Open, Octas, aff, reads</li>\n</ul>\n</li>\n</ul>\n"
        '<h5 id="a-deeper-heading">A deeper heading</h5>\n<p>Stays on AB\'s page.</p>\n'
    )
    assert "Fictional Open, R2, neg, AT" in cd.body_html and "Octas" not in cd.body_html
    assert "<h4" not in larkspur.body_html and "Fictional Open" not in larkspur.body_html
    assert view.team("ab", "ab") is not None and view.team("ab", "cd") is None
    assert view.team("no-such-school", "ab") is None


def test_a_schools_link_to_its_teams_heading_goes_to_the_teams_page_and_any_other_is_text() -> None:
    view = render_school_view(TWO_SCHOOLS, "synthpolicy26")
    ab, larkspur = view.school("ab"), view.school("larkspur")
    assert ab is not None and larkspur is not None

    assert (
        '<li>AB: <a href="/landscape/synthpolicy26/schools/ab/ab">round by round</a>, '
        '<a href="https://opencaselist.com/synthpolicy26/Ab/AB" target="_blank" rel="noopener noreferrer">'
        'openCaselist<span class="new-tab"> (opens in a new tab)</span></a></li>'
    ) in ab.body_html
    assert '<li>AB: <a href="/landscape/synthpolicy26/schools/larkspur/ab">round by round</a>, ' in (
        larkspur.body_html
    )
    assert '<li>CD: <a href="/landscape/synthpolicy26/schools/larkspur/cd">round by round</a>, ' in (
        larkspur.body_html
    )
    # Ab's team is another school's: its anchor is not a link on Larkspur's page.
    assert "<li>Elsewhere: another school's team</li>" in larkspur.body_html


def test_a_fourth_level_heading_before_any_school_goes_to_the_front_page_and_makes_no_page() -> None:
    markdown = TWO_SCHOOLS.replace("The lead.\n", "The lead.\n\n#### Stray\n\nStray words.\n")
    view = render_school_view(markdown, "synthpolicy26")

    assert [school.heading for school in view.schools] == ["Ab", "Larkspur"]
    assert "Stray words." in view.by_school_lead_html
    assert all("Stray" not in school.body_html for school in view.schools)


def test_a_view_before_team_headings_keeps_every_school_and_no_team() -> None:
    """`v1-e32-t54`'s shape, bold team lines under the school's table: one page per school, as before."""
    markdown = (
        "# Positions by school: synthpolicy26 through 2026-10-20\n\n## By school\n\n### Ab\n\n"
        "**AB, round by round** (newest snapshot first)\n\n"
        "- `invented-da`\n  - Imaginary Classic, R1, neg, reads\n\n"
        "## By position\n"
    )
    view = render_school_view(markdown, "synthpolicy26")

    assert [(school.heading, school.teams) for school in view.schools] == [("Ab", ())]
    assert "Imaginary Classic, R1, neg, reads" in view.schools[0].body_html
