"""The log filter that keeps discovery credentials out of httpx's request lines and this package's logs.

Each test registers values no other test uses, because the filter is one per process, like the
loggers it sits on.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from debate_core.integrations.discovery.redaction import (
    LOGGER_NAME,
    PROTECTED_LOGGERS,
    SecretLogFilter,
    protect_logs,
    redact_exception_chain,
)
from debate_core.integrations.discovery.resilience import ResiliencePolicy, ResilientProvider
from debate_core.testing.fakes import FakeSearchProvider, FixedClock


def test_protected_loggers_drop_a_registered_value_from_a_rendered_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    protect_logs(("redaction-test-key-41",))
    logging.getLogger("httpx").info(
        'HTTP Request: %s %s "%s"', "GET", "https://api.example.org/s?api_key=redaction-test-key-41", "200 OK"
    )
    assert [record.getMessage() for record in caplog.records] == [
        'HTTP Request: GET https://api.example.org/s?api_key=*** "200 OK"'
    ]


def test_the_url_encoded_spelling_is_dropped_too(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    protect_logs(("redaction+test@example.net",))
    logging.getLogger("httpcore.http11").debug(
        "send_request_headers.started url=/s?mailto=redaction%2Btest%40example.net"
    )
    assert caplog.records[-1].getMessage() == "send_request_headers.started url=/s?mailto=***"


def test_an_exception_logged_with_the_record_is_scrubbed(caplog: pytest.LogCaptureFixture) -> None:
    """The value is built at run time: a traceback quotes source lines, and an adapter's never hold a key."""
    caplog.set_level(logging.DEBUG)
    key = "-".join(("redaction", "test", "key", "42"))
    protect_logs((key,))
    try:
        try:
            raise OSError(f"reset fetching ?key={key}")
        except OSError as transport:
            raise RuntimeError(f"search failed with {key}") from transport
    except RuntimeError:
        logging.getLogger(LOGGER_NAME).exception("discovery failed")
    assert "OSError: reset fetching ?key=***" in caplog.text
    assert "RuntimeError: search failed with ***" in caplog.text
    assert key not in caplog.text


def test_a_record_on_an_unprotected_logger_is_left_alone(caplog: pytest.LogCaptureFixture) -> None:
    """The filter is a backstop on named loggers, not a global rewrite of everything logged."""
    caplog.set_level(logging.DEBUG)
    protect_logs(("redaction-test-key-43",))
    logging.getLogger("tests.some_other_library").info("redaction-test-key-43")
    assert caplog.records[-1].getMessage() == "redaction-test-key-43"


def test_every_module_in_the_package_logs_on_the_one_protected_logger() -> None:
    """A child logger's records would pass the package logger's filter by, so nothing here uses one."""
    from debate_core.integrations.discovery import registry, resilience

    assert getattr(resilience, "logger") is logging.getLogger(LOGGER_NAME)  # noqa: B009
    for module in (resilience, registry):
        assert "getLogger(__name__)" not in Path(module.__file__ or "").read_text(encoding="utf-8")


def test_protecting_twice_attaches_one_filter_per_logger() -> None:
    protect_logs(("redaction-test-key-44",))
    protect_logs(("redaction-test-key-45",))
    for name in PROTECTED_LOGGERS:
        filters = [found for found in logging.getLogger(name).filters if isinstance(found, SecretLogFilter)]
        assert len(filters) == 1, name


def test_a_filter_with_nothing_registered_passes_records_through_unchanged() -> None:
    record = logging.makeLogRecord({"msg": "%s and %s", "args": ("a", "b")})
    assert SecretLogFilter().filter(record) is True
    assert (record.msg, record.args) == ("%s and %s", ("a", "b"))


def test_the_resilient_wrapper_protects_the_logs_for_the_values_it_is_given(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    ResilientProvider(
        FakeSearchProvider("openalex"),
        ResiliencePolicy(),
        clock=FixedClock(),
        secrets=("redaction-test-email@example.net",),
    )
    logging.getLogger("httpx").info(
        "GET https://api.example.org/works?mailto=redaction-test-email%40example.net"
    )
    assert caplog.records[-1].getMessage() == "GET https://api.example.org/works?mailto=***"


def test_redacting_a_chain_stops_at_a_cycle() -> None:
    first = RuntimeError("one redaction-test-key-46")
    second = RuntimeError("two redaction-test-key-46")
    first.__context__ = second
    second.__context__ = first
    redact_exception_chain(first, ("redaction-test-key-46",))
    assert (str(first), str(second)) == ("one ***", "two ***")
