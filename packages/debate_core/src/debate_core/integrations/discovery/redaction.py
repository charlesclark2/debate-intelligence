"""Keeping discovery credentials and the contact email out of messages, exceptions and log lines.

Discovery adapters are handed an API key or two and a coach's contact email
(:class:`~debate_core.application.settings.ProviderSettings`). They send them to the provider, as a
header or as a query parameter (`mailto=` for the OpenAlex and Crossref polite pools), and they must
not appear anywhere else: not in an error, a health snapshot, a `repr` or a log line.

Two places they would otherwise leak from:

* **Messages and exceptions.** An adapter's error, or the transport exception under it, may quote
  the request URL. :func:`redact` and :func:`redact_exception_chain` remove every configured value,
  in its raw and URL-encoded spellings;
  :class:`~debate_core.integrations.discovery.resilience.ResilientProvider` runs both over every
  failure it records or raises.
* **httpx's own logging.** httpx logs `HTTP Request: GET <url>` at INFO, query string included, and
  httpcore logs at DEBUG. :func:`protect_logs` attaches one shared :class:`SecretLogFilter` to those
  loggers and to this package's, and adds the given values to it. The resilient wrapper calls it
  with the configured values, and an adapter that is handed a credential calls it in its
  constructor, so that the adapter's own tests, which run it unwrapped, see the same protection.

A filter on a logger sees only records logged on that logger, not those propagated from its
children, which is why httpcore's child loggers are named one by one, and why every module here,
an adapter included, logs on :data:`logger` rather than on a logger of its own.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterable
from typing import Final
from urllib.parse import quote, quote_plus

__all__ = [
    "LOGGER_NAME",
    "PROTECTED_LOGGERS",
    "REDACTED",
    "SecretLogFilter",
    "protect_logs",
    "redact",
    "redact_exception_chain",
]

LOGGER_NAME: Final = "debate_core.integrations.discovery"
"""The one logger every module in this package, adapters included, writes to.

One logger rather than one per module, because a filter sees only records logged on its own logger:
a record from `debate_core.integrations.discovery.openalex` would pass the package logger's filter by.
"""

logger: Final = logging.getLogger(LOGGER_NAME)
"""That logger."""

REDACTED: Final = "***"
"""What a credential or contact email becomes: the settings module's placeholder."""

PROTECTED_LOGGERS: Final = (
    LOGGER_NAME,
    "httpx",
    "httpcore",
    "httpcore.connection",
    "httpcore.http11",
    "httpcore.http2",
    "httpcore.proxy",
)
"""The loggers :func:`protect_logs` filters: this package's, and those httpx writes requests to."""


def redact(text: str, secrets: Iterable[str]) -> str:
    """`text` with every value in `secrets` replaced by :data:`REDACTED`.

    Each value is also removed in its URL-encoded spellings, because an adapter's error is as likely
    to quote the request URL (`mailto=coach%40example.org`) as the value itself. Longer spellings go
    first, so a value that contains another is not left half-replaced.
    """
    spellings = {
        spelling
        for secret in secrets
        if secret
        for spelling in (secret, quote(secret, safe=""), quote_plus(secret))
    }
    for spelling in sorted(spellings, key=len, reverse=True):
        text = text.replace(spelling, REDACTED)
    return text


def redact_exception_chain(error: BaseException, secrets: Iterable[str]) -> None:
    """Scrub `error` and every exception it was raised from, in place.

    An exception's message is its `args`, so replacing the string arguments changes what `str()`,
    a log line and a printed traceback show, while the exception keeps its type and attributes.
    """
    values = tuple(secrets)
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        current.args = tuple(redact(arg, values) if isinstance(arg, str) else arg for arg in current.args)
        current = current.__cause__ or current.__context__


class SecretLogFilter(logging.Filter):
    """Rewrites a record's message, and the exception it carries, with every registered value removed.

    The message is rendered with its arguments first and then scrubbed, because a value passed as a
    `%s` argument is only visible after rendering; the record's `args` are then cleared so that no
    handler renders the original a second time.
    """

    def __init__(self) -> None:
        super().__init__()
        self._secrets: set[str] = set()
        self._lock = threading.Lock()

    def add_secrets(self, values: Iterable[str]) -> None:
        """Scrub each of `values` from every record from now on."""
        with self._lock:
            self._secrets.update(value for value in values if value)

    def filter(self, record: logging.LogRecord) -> bool:
        with self._lock:
            secrets = tuple(self._secrets)
        if not secrets:
            return True
        record.msg = redact(record.getMessage(), secrets)
        record.args = None
        if record.exc_info is not None and record.exc_info[1] is not None:
            redact_exception_chain(record.exc_info[1], secrets)
            record.exc_text = None
        return True


_FILTER: Final = SecretLogFilter()


def protect_logs(secrets: Iterable[str]) -> None:
    """Remove `secrets` from every record on :data:`PROTECTED_LOGGERS`, from now on, in this process."""
    _FILTER.add_secrets(secrets)
    for name in PROTECTED_LOGGERS:
        target = logging.getLogger(name)
        if _FILTER not in target.filters:
            target.addFilter(_FILTER)
