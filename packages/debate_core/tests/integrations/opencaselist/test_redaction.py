"""The log filter that keeps the caselist_token and file paths out of every record.

A backstop behind code that never formats either in the first place; see
`test_client.py::test_no_token_or_password_reaches_a_log_or_an_exception` for the end-to-end check.
"""

from __future__ import annotations

import logging

import pytest

from debate_core.integrations.opencaselist.redaction import (
    LOGGER_NAME,
    REDACTED,
    install_redaction,
    redact,
    register_secret,
)


def test_redact_scrubs_a_registered_secret_a_cookie_and_a_download_path(fake_token: str) -> None:
    text = (
        f"token {fake_token}; Cookie: caselist_token={fake_token}; "
        "GET https://api.example.invalid/v1/download?path=openev/2026/CampA/ZZ/File.docx done; "
        "bare &path=weekly/x.zip"
    )
    scrubbed = redact(text, frozenset({fake_token}))

    assert fake_token not in scrubbed
    assert "File.docx" not in scrubbed
    assert "weekly/x.zip" not in scrubbed
    assert scrubbed.count(REDACTED) >= 4
    assert "https://api.example.invalid/v1/download?" in scrubbed


@pytest.mark.parametrize("logger_name", [LOGGER_NAME, "httpx", "httpcore.http11", "httpcore.connection"])
def test_a_registered_token_is_redacted_from_records_on_every_covered_logger(
    logger_name: str, fake_token: str, caplog: pytest.LogCaptureFixture
) -> None:
    install_redaction()
    register_secret(fake_token)

    with caplog.at_level(logging.DEBUG, logger=logger_name):
        logging.getLogger(logger_name).debug("sent %s with extra", fake_token, extra={"cookie": fake_token})

    record = caplog.records[-1]
    assert fake_token not in record.getMessage()
    assert fake_token not in caplog.text
    assert fake_token not in str(record.__dict__)


def test_httpx_request_lines_lose_their_query_string(caplog: pytest.LogCaptureFixture) -> None:
    install_redaction()
    with caplog.at_level(logging.INFO, logger="httpx"):
        logging.getLogger("httpx").info(
            'HTTP Request: %s %s "%s"',
            "GET",
            "https://api.example.invalid/v1/download?path=openev/2026/CampA/ZZ/File.docx",
            "HTTP/1.1 200 OK",
        )
    assert "File.docx" not in caplog.text
    assert "HTTP/1.1 200 OK" in caplog.text
