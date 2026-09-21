"""Keeping the caselist_token, and the paths behind it, out of every log record.

Two things must never reach a log line from this package, in any environment
(`docs/policies/caselist-data-use.md`, E34 gate 3 and prohibited use 9):

* **The caselist_token.** It is a session credential for the operator's own Tabroom account. The
  client holds it as a :class:`~pydantic.SecretStr` and sends it only as a cookie to the API host,
  so it has no business in a message — but httpx and httpcore log requests of their own, and a
  filter that scrubs the value is what makes "never" true for code this project did not write.
* **A file's path.** `GET /download?path=…` carries the file it asks for in the query string, and
  httpx's own `HTTP Request: GET …` line prints the whole URL. For a disclosure that path names a
  school and a team code; for an OpenEv file it names a camp's file. Neither belongs in a log.

:class:`SecretRedactingFilter` does both, and :func:`install_redaction` attaches one shared
instance to this package's logger and to the httpx and httpcore loggers. A filter on a logger only
sees records logged *on that logger*, not ones propagated from its children, which is why httpcore's
child loggers are named one by one.

The filter is a backstop, not the mechanism. Nothing in this package formats a token or a path into
a message in the first place; the tests capture every record at DEBUG and assert that.
"""

from __future__ import annotations

import logging
import re
import threading
from typing import Final

__all__ = [
    "LOGGER_NAME",
    "REDACTED",
    "SecretRedactingFilter",
    "install_redaction",
    "logger",
    "redact",
    "register_secret",
]

LOGGER_NAME: Final = "debate_core.integrations.opencaselist"
"""The one logger every module in this package writes to."""

REDACTED: Final = "[REDACTED]"
"""What a scrubbed value becomes."""

_THIRD_PARTY_LOGGERS: Final = (
    "httpx",
    "httpcore",
    "httpcore.connection",
    "httpcore.http11",
    "httpcore.http2",
    "httpcore.proxy",
)
"""The loggers httpx and httpcore write request details to."""

_COOKIE_VALUE = re.compile(r"(caselist_token\s*[=:]\s*)[^;,\s\"']+", re.IGNORECASE)
"""`caselist_token=…` in a cookie header, a Set-Cookie line, or a JSON-ish dump of either."""

_QUERY_STRING = re.compile(r"(https?://[^\s\"'?#]+)\?[^\s\"'#]*")
"""Everything after the `?` of a URL: `/download?path=…` names the file it fetches."""

_PATH_PARAMETER = re.compile(r"([?&]path=)[^\s&\"'#]+")
"""A bare `?path=…` or `&path=…` that is not part of a full URL."""


def redact(text: str, secrets: frozenset[str] = frozenset()) -> str:
    """`text` with every known secret, token cookie and URL query string replaced."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, REDACTED)
    text = _COOKIE_VALUE.sub(rf"\g<1>{REDACTED}", text)
    text = _QUERY_STRING.sub(rf"\g<1>?{REDACTED}", text)
    return _PATH_PARAMETER.sub(rf"\g<1>{REDACTED}", text)


class SecretRedactingFilter(logging.Filter):
    """Rewrites a record's message, and its extra string fields, with secrets scrubbed.

    The message is rendered with its arguments first and then scrubbed, because a token passed as
    `%s` argument is only visible after rendering. The record's `args` are cleared so that no
    handler renders the original a second time.
    """

    def __init__(self) -> None:
        super().__init__()
        self._secrets: set[str] = set()
        self._lock = threading.Lock()

    def add_secret(self, value: str) -> None:
        """Scrub `value` from every record from now on."""
        if value:
            with self._lock:
                self._secrets.add(value)

    @property
    def secrets(self) -> frozenset[str]:
        with self._lock:
            return frozenset(self._secrets)

    def filter(self, record: logging.LogRecord) -> bool:
        secrets = self.secrets
        try:
            message = record.getMessage()
        except Exception:  # a malformed record is still scrubbed, never dropped
            message = str(record.msg)
        record.msg = redact(message, secrets)
        record.args = None
        for name, value in list(record.__dict__.items()):
            if isinstance(value, str) and name not in {"msg", "name", "levelname", "pathname"}:
                record.__dict__[name] = redact(value, secrets)
        if record.exc_text:
            record.exc_text = redact(record.exc_text, secrets)
        return True


_FILTER: Final = SecretRedactingFilter()

logger: Final = logging.getLogger(LOGGER_NAME)
"""This package's logger. Carries the redaction filter from import time on."""

_install_lock = threading.Lock()
_installed = False


def install_redaction() -> SecretRedactingFilter:
    """Attach the shared filter to this package's logger and to httpx's and httpcore's. Idempotent."""
    global _installed
    with _install_lock:
        if not _installed:
            for name in (LOGGER_NAME, *_THIRD_PARTY_LOGGERS):
                logging.getLogger(name).addFilter(_FILTER)
            _installed = True
    return _FILTER


def register_secret(value: str) -> None:
    """Add the token to what every record is scrubbed of.

    Not used for the Tabroom password, on purpose: registering it would keep it in a process-wide
    set for the life of the process, which is a way of storing it. The password is instead never
    formatted into anything, and the leak test checks it.
    """
    install_redaction().add_secret(value)


install_redaction()
