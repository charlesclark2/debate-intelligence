"""What `caselist runs` and `caselist status` say of the parses the runs owe (`v1-e40-t08`).

The parse-owed file (:class:`~debate_core.application.caselist_sync.ParseOwed`): this machine's, or
the bucket's copy, which is the cloud run's. Its entries for `--json`, and the sentence the tables'
captions end with.
"""

from __future__ import annotations

import asyncio
from typing import cast

from debate_cli.container import ServiceContainer
from debate_cli.output import JsonValue
from debate_core.application.caselist_sync import ParseOwedUnreadable, parses_owed_sentence

__all__ = ["parses_owed"]


def parses_owed(services: ServiceContainer, *, remote: bool) -> tuple[JsonValue, str | None]:
    """The entries and their sentence, this machine's or (`remote`) the bucket's.

    A file that cannot be read is `null` and said so, never taken for nothing owed.
    """
    try:
        owed = asyncio.run(services.run_state().parses_owed()) if remote else services.parse_owed().read()
    except ParseOwedUnreadable as unreadable:
        said = str(unreadable)
        return None, f"{said[:1].upper()}{said[1:]}."
    return cast("JsonValue", owed.as_json()), parses_owed_sentence(owed)
