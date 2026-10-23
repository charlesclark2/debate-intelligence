"""A removed card leaves the pages within five minutes (`v1-e39-t07`, ac1 and ac7).

The data-use policy's E39 gate item 5, through the real app: the results page, the card page and
Copy card's copy all go through the index holder's lease, which applies the suppression list the
holder last read, and the holder re-reads it at most five minutes apart. The clock is the world's
own, so "four minutes fifty-nine" and "five minutes" are each a line.

Expected values are written by hand from `conftest.CORPUS`. The featured card (doc 1) has three
occurrences: 0 (Maple Grove QX, its representative), 1 (Riverbend ZT) and 2 (no provenance kept).
An occurrence's source digest is `f"{doc:032x}{ordinal:032x}"` and its disclosure digest
`f"{ordinal:032x}{doc:032x}"`. 25 cards hold `zephyr`, 20 to a page.
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any, Final

import pytest

from debate_core.application.ports.suppression import ReasonCode, SuppressionAction, SuppressionEntry

FEATURED: Final = 1
JUST_UNDER: Final = timedelta(minutes=5) - timedelta(seconds=1)
OTHER_LINE: Final = "Riverbend ZT"


def source_of(doc_id: int, ordinal: int) -> str:
    return f"{doc_id:032x}{ordinal:032x}"


def disclosure_of(doc_id: int, ordinal: int) -> str:
    return f"{ordinal:032x}{doc_id:032x}"


def suppress(world: Any, doc_id: int, ordinal: int, *, whole_source: bool = False) -> None:
    world.index_source.append_suppression(
        SuppressionEntry(
            action=SuppressionAction.SUPPRESS,
            sha256=source_of(doc_id, ordinal),
            disclosure=None if whole_source else disclosure_of(doc_id, ordinal),
            recorded_at=world.clock(),
            reason=ReasonCode.REQUESTED_BY_TEAM,
            request_id="RM-2026-07",
        )
    )


@pytest.fixture
def student(world: Any) -> Any:
    world.signed_in_student()
    return world


def results(world: Any, query: str = "zephyr") -> list[str]:
    """Every card path the search's two pages link to, without the search each link carries (`v1-e39-t11`)."""
    page = world.browser.get(f"/search?q={query}").text
    paths = re.findall(r'<h3 class="result-tag"><a href="([^"?]+)[^"]*">', page)
    following = re.search(r'<a href="([^"]+)" rel="next">', page)
    if following is not None:
        later = world.browser.get(following.group(1).replace("&amp;", "&")).text
        paths += re.findall(r'<h3 class="result-tag"><a href="([^"?]+)[^"]*">', later)
    return paths


def statuses(world: Any) -> tuple[bool, int, int]:
    """Whether the featured card is in the results, and its page's and its copy's status codes."""
    path = world.card_path("featured")
    return (
        path in results(world),
        world.browser.get(path).status_code,
        world.browser.get(path + "/copy").status_code,
    )


def test_suppression_hides_a_removed_card_from_results_its_page_and_its_copy_at_five_minutes(
    student: Any,
) -> None:
    assert statuses(student) == (True, 200, 200)

    suppress(student, FEATURED, 0, whole_source=True)
    student.clock.advance(JUST_UNDER)
    assert statuses(student) == (True, 200, 200)

    student.clock.advance(timedelta(seconds=1))
    assert statuses(student) == (False, 404, 404)
    assert len(results(student)) == 24


def test_suppression_reaches_an_environment_frozen_for_fifty_minutes_before_it_answers(student: Any) -> None:
    """Fifty minutes: well past the five, inside the session's hour of idleness."""
    assert statuses(student) == (True, 200, 200)

    suppress(student, FEATURED, 0)
    student.clock.advance(timedelta(minutes=50))

    path = student.card_path("featured")
    assert student.browser.get(path).status_code == 404


def test_suppression_of_another_teams_disclosure_leaves_the_card_without_that_line_or_a_team_count(
    student: Any,
) -> None:
    page = student.browser.get(student.card_path("featured")).text
    assert OTHER_LINE in page
    assert "In 3 files from 2 teams." in page

    suppress(student, FEATURED, 1)
    student.clock.advance(timedelta(minutes=5))

    page = student.browser.get(student.card_path("featured")).text
    assert OTHER_LINE not in page
    assert "In 2 files. The number of teams is not known until the next weekly update." in page
    copied = student.browser.get(student.card_path("featured") + "/copy").json()
    assert OTHER_LINE not in copied["text"]


def test_suppression_writes_no_access_record_for_a_card_it_hid(student: Any) -> None:
    suppress(student, FEATURED, 0, whole_source=True)

    student.browser.get(student.card_path("featured"))
    student.browser.get(student.card_path("featured") + "/copy")

    assert [record.action.value for record in student.audit.records] == []


def test_suppression_list_that_cannot_be_read_answers_every_search_page_as_unavailable(student: Any) -> None:
    student.index_source.write_suppression_list(b"not a suppression line\n")

    response = student.browser.get(student.card_path("featured"))
    assert response.status_code == 503
    assert "Search is not available right now" in response.text
    assert student.browser.get("/search?q=zephyr").status_code == 503
    assert student.browser.get(student.card_path("featured") + "/copy").status_code == 503
    assert student.browser.get("/search").status_code == 200
