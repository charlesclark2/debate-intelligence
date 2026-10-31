"""The function's app log: the index holder's `INFO` lines reach it, and nothing else's (`v1-e39-t10` ac5).

Each test starts from a root logger with none of this module's handler and puts back what it found,
since the root logger and the holder's level are shared by every test in a worker (working agreement
10). The handler writes to a buffer the test reads, as Lambda reads the process's stderr.

Every name, tag and word here is synthetic.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Iterator
from typing import Any, Final

import pytest

import debate_api.container
from debate_api.app import create_app
from debate_api.app_logging import configure_app_logging

HOLDER: Final = "debate_core.application.search_index_holder"


@pytest.fixture
def bare_logging() -> Iterator[None]:
    """The root logger without this module's handler, and every level as it was, before and after."""
    root, holder = logging.getLogger(), logging.getLogger(HOLDER)
    handlers, root_level, holder_level = list(root.handlers), root.level, holder.level
    yield
    for handler in root.handlers:
        if handler not in handlers:
            root.removeHandler(handler)
    root.setLevel(root_level)
    holder.setLevel(holder_level)


@pytest.fixture
def app_log(bare_logging: None) -> io.StringIO:
    stream = io.StringIO()
    configure_app_logging(stream)
    return stream


@pytest.fixture
def world(search_world: Any) -> Any:
    """This file's world: sign-in and the search pages (`v1-e39-t20`)."""
    return search_world


def test_the_holders_info_and_every_warning_reach_the_log_with_level_and_logger(app_log: io.StringIO) -> None:
    logging.getLogger(HOLDER).info("search index %s loaded in %.2f s", "0123456789abcdef", 1.5)
    logging.getLogger("debate_core.application.tub.access_audit").warning(
        "tub audit: a searched record was not written"
    )

    assert app_log.getvalue().splitlines() == [
        f"INFO {HOLDER}: search index 0123456789abcdef loaded in 1.50 s",
        "WARNING debate_core.application.tub.access_audit: tub audit: a searched record was not written",
    ]


@pytest.mark.parametrize(
    ("logger", "level"),
    [
        ("debate_core.application.evidence_search", logging.INFO),
        ("debate_core.application.card_download", logging.INFO),
        ("debate_api.search_pages", logging.INFO),
        ("botocore.credentials", logging.INFO),
        (HOLDER, logging.DEBUG),
    ],
)
def test_no_other_info_and_no_debug_reaches_it(app_log: io.StringIO, logger: str, level: int) -> None:
    logging.getLogger(logger).log(level, "a line that names Invented Invitational Round 4")

    assert app_log.getvalue() == ""


def test_configuring_twice_adds_one_handler(app_log: io.StringIO) -> None:
    configure_app_logging(io.StringIO())
    logging.getLogger(HOLDER).info("once")

    assert app_log.getvalue() == f"INFO {HOLDER}: once\n"


def test_the_functions_app_configures_it_and_a_tests_own_app_does_not(
    bare_logging: None, world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def ours() -> list[logging.Handler]:
        return [one for one in logging.getLogger().handlers if type(one).__name__ == "_AppLogHandler"]

    create_app(world.services)
    assert ours() == []

    monkeypatch.setattr(debate_api.container, "build_pilot_services", lambda environ: world.services)
    create_app()
    [handler] = ours()
    assert isinstance(handler, logging.StreamHandler)
    assert logging.getLogger(HOLDER).getEffectiveLevel() == logging.INFO


def test_a_search_through_the_app_logs_the_load_and_the_search_time_and_never_the_query(
    app_log: io.StringIO, world: Any
) -> None:
    world.signed_in_student()

    page = world.browser.get("/search", params={"q": "zephyr", "caselist": "hsld26"})

    assert page.status_code == 200
    lines = app_log.getvalue().splitlines()
    [loaded] = [line for line in lines if " loaded in " in line]
    assert loaded.startswith(f"INFO {HOLDER}: search index {world.index.index_id} loaded in ")
    assert " bytes in its directory" in loaded
    [answered] = [line for line in lines if "search answered in " in line]
    assert answered.startswith(f"INFO {HOLDER}: search answered in ")
    assert answered.endswith(" ms, by words")
    for word in ("zephyr", "hsld26", "Maple Grove", "debater.one", "q="):
        assert word not in app_log.getvalue(), word
