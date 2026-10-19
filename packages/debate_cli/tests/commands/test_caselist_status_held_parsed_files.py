"""How `caselist status` shows a held upload's parsed file in the bucket (`v1-e31-t26`).

An earlier build's `caselist parse --publish` sent the parsed file of bytes that only a path a
removal holds discloses. The comparison names each such source
(`packages/debate_core/tests/application/caselist/test_status_names_a_held_uploads_parsed_file.py`);
here, what the command prints of it. Each report is built by hand, as in
`test_caselist_status_held_paths.py`.

What the line keeps, like every line about a hold: a source is named by the first twelve characters
of its sha256 and the request holding its path, never by the path, a school, a team code or a file
name; and it does not change whether the command succeeds.
"""

from __future__ import annotations

import json
from typing import Final

from debate_cli.commands.caselist import (
    _status_table,  # pyright: ignore[reportPrivateUsage]
    status_summary,
)
from debate_core.application.caselist.status_service import CaselistStatusReport, HeldParsedObject

from .test_caselist_remove_plan_output import CASELIST, IDENTIFYING, SETTINGS
from .test_caselist_status_held_paths import snapshot

PARSED: Final = "0a1b2c3d4e5f" + "4" * 52
REQUEST: Final = "RM-2026-08"


def report() -> CaselistStatusReport:
    return CaselistStatusReport(
        snapshots=(snapshot("2026-10-06"),),
        held_parsed_objects=(HeldParsedObject(caselist=CASELIST, sha256=PARSED, request_id=REQUEST),),
    )


def test_its_request_is_owed_and_the_command_still_succeeds() -> None:
    held = report()

    assert held.removals_owed == (REQUEST,)
    assert held.in_sync


def test_the_table_names_it_by_caselist_prefix_and_request_and_says_what_to_run() -> None:
    caption = _status_table(report(), SETTINGS).caption or ""
    told = " ".join(caption.split())

    assert (
        f"HELD UPLOADS PARSED IN THE BUCKET in {CASELIST}: 1 source(s) only a held path discloses, "
        f"whose parsed file an earlier build published (sha256 {PARSED[:12]}, {REQUEST})."
    ) in told
    assert (
        "A held row, a held upload in the inbox or a held upload's parsed file in the bucket means "
        f"{REQUEST} is owed again: run the same removal again"
    ) in told
    assert PARSED not in caption
    assert not [word for word in IDENTIFYING if word in caption]


def test_the_json_gives_one_entry_per_caselist_by_count_prefix_and_request() -> None:
    data = status_summary(report(), SETTINGS)

    assert data["held_parsed_objects"] == [
        {"caselist": CASELIST, "objects": 1, "sha256_prefixes": [PARSED[:12]], "requests": [REQUEST]}
    ]
    assert data["removals_owed"] == [REQUEST]
    assert PARSED not in json.dumps(data)
