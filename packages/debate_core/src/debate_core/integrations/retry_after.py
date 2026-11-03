"""The one reader of the `Retry-After` header, for every HTTP adapter in `debate_core.integrations`.

A server that refuses a request with 429 or 503 may say how long to wait, in one of two forms
(RFC 9110 §10.2.3): a number of seconds (`120`) or an HTTP date
(`Wed, 21 Oct 2026 07:28:00 GMT`). The discovery mapping
(:mod:`~debate_core.integrations.discovery.http_failures`), the article fetcher
(:mod:`~debate_core.integrations.http_fetcher`) and OpenCaselist's transport
(:mod:`~debate_core.integrations.opencaselist.transport`) all read it here, and
`packages/debate_core/tests/integrations/test_one_retry_after_reader.py` fails on a second reader
anywhere in the package (`v1-e07-t08`).

The date form is a distance from *now*, and *now* is the caller's injected
:class:`~debate_core.application.ports.providers.Clock`, read and passed in. Nothing here reads the
wall clock, so a test pins the wait to the second and a replay waits as the recording did.
"""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

__all__ = ["retry_after_seconds"]


def retry_after_seconds(value: str | None, *, now: datetime) -> float | None:
    """The wait a `Retry-After` header asks for, in seconds; `None` when absent or unreadable.

    The seconds form is ASCII digits only, as the RFC writes it (`1*DIGIT`): `1.5`, `-5`, `nan`, or a
    digit `str.isdigit()` accepts from another script (`²`, `١٢٠`), is unreadable, so the adapter
    falls back to its own backoff (the PM's rulings on `v1-e07-t08`). A date is measured from `now`;
    one in the past means "now", so it is `0.0`, never negative, and a date with no zone is read as
    UTC.
    """
    if value is None:
        return None
    text = value.strip()
    if text.isascii() and text.isdigit():
        return float(text)
    try:
        moment = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return max((moment - now).total_seconds(), 0.0)
