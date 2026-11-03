"""The function's app log (`v1-e39-t10`): what reaches `debate-<env>-tub-app`, and in what words.

Lambda sends the process's stderr to the function's log group. uvicorn configures its own loggers,
which do not propagate, and leaves the root logger without a handler, so until this module a record
from `debate_core` met Python's last-resort handler: a `WARNING` printed as its bare message, an
`INFO` dropped. The index holder's load lines never reached the log, and with them the numbers
ADR-0019 (c) 6 and 7 are measured by.

:func:`configure_app_logging` gives the root logger one handler on stderr, `<LEVEL> <logger>: <message>`:

* **Every `WARNING` and above**, from any logger, as before: the refusals the evidence-search runbook
  lists ("What a refusal looks like in the app log") keep their words, now with their level and
  logger in front.
* **`INFO` from the index holder alone** (:data:`INFO_LOGGERS`): `search index <id> loaded in ...`
  with its time and its bytes on `/tmp`, `... closed and deleted`, and `search answered in <n> ms`.
  They name an index id, a time and a size, never a query, a card or a user (gate item 4,
  :mod:`debate_core.application.search_index_holder`).

No other logger's `INFO` is let through. `INFO` is opened one logger at a time, each named here once
what it logs at that level has been read, so a later `INFO` line elsewhere that named a card or a
student would stay out of the log rather than depend on a test to notice it.

Only uvicorn's factory, :func:`~debate_api.container.create_app_from_environment`, calls this. A
test that builds the app with its own services leaves logging as pytest set it.
"""

from __future__ import annotations

import logging
from typing import Final, TextIO

__all__ = ["APP_LOG_FORMAT", "INFO_LOGGERS", "configure_app_logging"]

APP_LOG_FORMAT: Final = "%(levelname)s %(name)s: %(message)s"
"""One line a record. CloudWatch adds the time; the Text log format adds nothing else."""

INFO_LOGGERS: Final = ("debate_core.application.search_index_holder",)
"""The loggers whose `INFO` lines reach the app log. Each holds no query, card or user."""


class _AppLogHandler(logging.StreamHandler[TextIO]):
    """The one handler this module adds, told apart from any other by its class."""


def configure_app_logging(stream: TextIO | None = None) -> None:
    """Send `WARNING` and above, and :data:`INFO_LOGGERS`' `INFO`, to `stream` (stderr by default).

    Calling it again changes nothing, so a second app in one process does not double every line.
    """
    root = logging.getLogger()
    if any(isinstance(handler, _AppLogHandler) for handler in root.handlers):
        return
    handler = _AppLogHandler(stream)
    handler.setFormatter(logging.Formatter(APP_LOG_FORMAT))
    root.addHandler(handler)
    root.setLevel(logging.WARNING)
    for name in INFO_LOGGERS:
        logging.getLogger(name).setLevel(logging.INFO)
