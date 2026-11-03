"""The access audit through the real app: card views, copies and searches (`v1-e39-t07`).

The data-use policy's E39 gate item 4 and ADR-0019 (e) 3, as the PM ruled them on 2026-10-22:

* a card page and Copy card each write one record naming the card, before the card goes out, and a
  record that cannot be written answers 503 with no card;
* a search's first page writes one `searched` record carrying the number of results on it and
  nothing else beyond the shape's own fields; a next page, a refused form, a search with no search
  terms and an unavailable index write nothing; a failed write logs one warning naming the action
  and the search still answers.

Every expected value is written by hand from `conftest.search_corpus`: 25 cards hold `zephyr`, so its first
page holds 20; the featured card is doc 1 in `hsld26`. The school, team code and words searched for
are the corpus's own synthetic ones.
"""

from __future__ import annotations

import html
import json
import logging
import re
from typing import Any, Final

import pytest

from debate_core.application.tub.audit import AuditAction

FEATURED_CLUSTER: Final = f"{1:064x}"
FEATURED_REFERENCE: Final = f"hsld26/{FEATURED_CLUSTER}"
FEATURED_TAG: Final = "Zephyr winds raise granite costs"

CARD_FIELDS: Final = {"format_version", "time", "action", "actor_role", "actor_subject", "cards"}
SEARCH_FIELDS: Final = {"format_version", "time", "action", "actor_role", "actor_subject", "count"}


@pytest.fixture
def world(search_world: Any) -> Any:
    """This file's world: sign-in and the search pages (`v1-e39-t20`)."""
    return search_world


@pytest.fixture
def student(world: Any) -> Any:
    world.student = world.signed_in_student("debater.audited")
    return world


def next_link(page: str) -> str:
    found = re.search(r'<a href="([^"]+)" rel="next">', page)
    assert found is not None, "no next page"
    return html.unescape(found.group(1))


def written(world: Any) -> list[dict[str, Any]]:
    return [json.loads(record.to_json()) for record in world.audit.records]


def accesses(world: Any) -> list[dict[str, Any]]:
    """The records this task adds, leaving out any account change a sign-in made."""
    ours = {
        AuditAction.SEARCHED,
        AuditAction.CARD_VIEWED,
        AuditAction.CARD_COPIED,
        AuditAction.CARDS_DOWNLOADED,
    }
    return [record for record in written(world) if record["action"] in {action.value for action in ours}]


# ------------------------------------------------------------------------------------------------
# A card page and a copy
# ------------------------------------------------------------------------------------------------


def test_audit_a_card_page_view_writes_one_record_naming_the_card_and_nothing_else(student: Any) -> None:
    assert student.browser.get(student.card_path("featured")).status_code == 200

    [record] = accesses(student)
    assert set(record) == CARD_FIELDS
    assert record == {
        "format_version": 1,
        "time": "2026-11-02T15:00:00Z",
        "action": "card-viewed",
        "actor_role": "student",
        "actor_subject": student.student.subject,
        "cards": [FEATURED_REFERENCE],
    }


def test_audit_a_copy_writes_one_card_copied_record(student: Any) -> None:
    assert student.browser.get(student.card_path("featured") + "/copy").status_code == 200

    [record] = accesses(student)
    assert set(record) == CARD_FIELDS
    assert (record["action"], record["cards"]) == ("card-copied", [FEATURED_REFERENCE])


def test_audit_a_camp_card_is_named_by_its_store(student: Any) -> None:
    student.browser.get(student.card_path("camp"))

    assert [record["cards"] for record in accesses(student)] == [[f"openev/{3:064x}"]]


def test_audit_a_card_not_found_writes_nothing(student: Any) -> None:
    assert student.browser.get(f"/cards/hsld26/{999:064x}").status_code == 404
    assert student.browser.get(f"/cards/hsld26/{999:064x}/copy").status_code == 404

    assert accesses(student) == []


def test_audit_a_card_page_whose_record_cannot_be_written_answers_503_without_the_card(student: Any) -> None:
    student.audit.failing = True

    response = student.browser.get(student.card_path("featured"))

    assert response.status_code == 503
    assert "Search is not available right now" in response.text
    assert FEATURED_TAG not in response.text
    assert "Lindqvist" not in response.text
    assert "Maple Grove" not in response.text


def test_audit_a_copy_whose_record_cannot_be_written_answers_503_without_the_card(student: Any) -> None:
    student.audit.failing = True

    response = student.browser.get(student.card_path("featured") + "/copy")

    assert response.status_code == 503
    assert response.json() == {"message": "The search could not be loaded. Try again in a minute."}


def test_audit_a_failed_card_record_logs_one_warning_naming_the_action_only(
    student: Any, caplog: pytest.LogCaptureFixture
) -> None:
    student.audit.failing = True
    with caplog.at_level(logging.WARNING, logger="debate_core.application.tub.access_audit"):
        student.browser.get(student.card_path("featured"))

    assert [record.getMessage() for record in caplog.records] == [
        "tub audit: a card-viewed record was not written, so the card was not sent"
    ]


# ------------------------------------------------------------------------------------------------
# Searches are counted, never recorded with their words
# ------------------------------------------------------------------------------------------------


def test_audit_a_first_page_search_writes_one_searched_record_with_its_result_count(student: Any) -> None:
    assert student.browser.get("/search?q=zephyr").status_code == 200

    [record] = accesses(student)
    assert set(record) == SEARCH_FIELDS
    assert record == {
        "format_version": 1,
        "time": "2026-11-02T15:00:00Z",
        "action": "searched",
        "actor_role": "student",
        "actor_subject": student.student.subject,
        "count": 20,
    }


def test_audit_a_search_for_a_school_and_team_code_records_none_of_its_words_filters_or_cards(
    student: Any,
) -> None:
    """The query names the corpus's school and team code; the filters and both pages are used."""
    first = student.browser.get(
        "/search?q=zephyr+Maple+Grove+QX&event=LD&side=NEG&caselist=hsld26&since=2026-09-01"
    )
    assert first.status_code == 200
    plain = student.browser.get("/search?q=zephyr&event=LD")
    assert student.browser.get(next_link(plain.text)).status_code == 200

    records = accesses(student)
    assert [set(record) for record in records] == [SEARCH_FIELDS, SEARCH_FIELDS]
    text = json.dumps(records).lower()
    for word in (
        "zephyr",
        "maple",
        "grove",
        "qx",
        "hsld26",
        "2026-09-01",
        "neg",
        '"ld"',
        "cursor",
        "q=",
        "/search",
    ):
        assert word not in text, word
    for doc_id in range(1, 26):
        assert f"{doc_id:064x}" not in text


def test_audit_a_next_page_writes_nothing(student: Any) -> None:
    page = student.browser.get("/search?q=zephyr").text
    student.audit.records.clear()

    assert student.browser.get(next_link(page)).status_code == 200
    assert accesses(student) == []


@pytest.mark.parametrize(
    "path",
    [
        pytest.param("/search", id="no words"),
        pytest.param("/search?q=zephyr&event=Debate", id="a filter outside its choices"),
        pytest.param("/search?q=zephyr&cursor=bogus", id="a cursor that is not this search's"),
        pytest.param("/search?q=%22%22", id="no search terms"),
    ],
)
def test_audit_a_search_that_searched_nothing_writes_nothing(student: Any, path: str) -> None:
    student.browser.get(path)

    assert accesses(student) == []


def test_audit_a_search_the_index_cannot_answer_writes_nothing(student: Any) -> None:
    student.index_source.objects.clear()

    assert student.browser.get("/search?q=zephyr").status_code == 503
    assert accesses(student) == []


def test_audit_a_search_whose_record_cannot_be_written_still_answers_and_logs_one_warning(
    student: Any, caplog: pytest.LogCaptureFixture
) -> None:
    student.audit.failing = True
    with caplog.at_level(logging.DEBUG):
        response = student.browser.get("/search?q=zephyr+Maple+Grove+QX")

    assert response.status_code == 200
    warnings = [record for record in caplog.records if record.levelno >= logging.WARNING]
    assert [record.getMessage() for record in warnings] == ["tub audit: a searched record was not written"]
