"""One takedown history that every build can be given, and what it leaves in the takedown's records.

`write_stored_suppression_lists.py` runs it against an older build's source to store what that
build wrote, and `test_suppression_list_is_read_by_every_build.py` runs it against this one. So it
uses nothing a build from before `v1-e30-t11` lacks: the three synthetic weeks and the camp download
of `conftest.py`, `--team`, `--source` and `unsuppress`.

## The history

At one fixed instant, in this order:

1. `caselist remove --team 'testcl26/Maple Grove/QX'` under `RM-2026-01`. Three files are the team's
   alone and are removed whole; one, the Round 1 affirmative, another team disclosed too, and is
   withdrawn from the team's two paths.
2. `caselist remove --source <seaside-finals-pro>` under `RM-2026-02`: one file of another team,
   held at one path in two weeks, with no other version there. Every build removes it whole and
   appends one line to the list for it.
3. `caselist unsuppress --sha256 <bayview-semis-neg>`, one of the team's three, as removed in error.

So the list ends with every kind of line it has: a whole-file suppression, a suppression of one
disclosure, and an un-suppress. Step 2 is the one this task changes: this build also appends a path
entry for it, beside the list.
"""

from __future__ import annotations

import dataclasses
import hashlib
from typing import Any, Final

from tests.fixtures.caselist.build_synthetic_archives import DOCUMENT_BODIES

from debate_core.application.caselist.removal_plan import SourceSelector, parse_team_selector
from debate_core.application.caselist.removal_service import TakedownAccess
from debate_core.application.ports.suppression import ReasonCode

from .conftest import REQUEST, TEAM, RemovalWorld

SECOND_REQUEST: Final = "RM-2026-02"
SUPPRESSION_PREFIX: Final = "manifests/_suppression/"

REMOVED_BY_SOURCE: Final = hashlib.sha256(DOCUMENT_BODIES["seaside-finals-pro"]).hexdigest()
UNSUPPRESSED: Final = hashlib.sha256(DOCUMENT_BODIES["bayview-semis-neg"]).hexdigest()
REMOVED_WITH_THE_TEAM: Final = tuple(
    hashlib.sha256(DOCUMENT_BODIES[body]).hexdigest()
    for body in ("grove-round-2-neg-first", "grove-round-2-neg-revised", "bayview-semis-neg")
)
WITHDRAWN_FROM_THE_TEAM: Final = hashlib.sha256(DOCUMENT_BODIES["grove-round-1-aff"]).hexdigest()

REMOVED_BY_SOURCE_PATH: Final = "Riverbend Academy/MnPr/Riverbend Academy-MnPr-Pro-Seaside Cup-Finals.docx"
"""Where `seaside-finals-pro` is held, first in the weekly of `2026-09-08`."""


def _takedown(world: RemovalWorld) -> TakedownAccess:
    """The takedown credential on moto, built for whichever build this runs against.

    `v1-e29-t08` gave :class:`TakedownAccess` the question of which role a credential is signed in
    as; a build from before it has no such field and asks nothing.
    """
    current = world.takedown() if _asks_who_it_is_signed_in_as() else None
    if current is not None:
        return current
    from debate_core.integrations.s3 import S3EvidenceVersionStore

    reach: dict[str, Any] = {
        "versions": S3EvidenceVersionStore(bucket=world.bucket_name, client=world.client),
        "objects": world.bucket,
        "profile": "debate-dev-evidence-removal",
        "bucket": world.bucket_name,
    }
    return TakedownAccess(**reach)


def _asks_who_it_is_signed_in_as() -> bool:
    return "caller" in {field.name for field in dataclasses.fields(TakedownAccess)}


async def a_team_removal_a_source_removal_and_an_unsuppress(world: RemovalWorld) -> None:
    """Carry out the history in the module docstring, through the services the commands run."""
    service = world.service(takedown=lambda: _takedown(world))
    team = await service.plan(
        parse_team_selector(TEAM), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM
    )
    assert (await service.execute(team)).completed
    source = await service.plan(
        SourceSelector(REMOVED_BY_SOURCE), request_id=SECOND_REQUEST, reason=ReasonCode.REQUESTED_BY_SCHOOL
    )
    assert (await service.execute(source)).completed
    lifted = await service.plan_unsuppress(
        UNSUPPRESSED, reason=ReasonCode.REMOVED_IN_ERROR, request_id=REQUEST
    )
    await service.unsuppress(lifted)


def takedown_records(world: RemovalWorld) -> dict[str, bytes]:
    """Every file under this machine's `suppression/` and every object under the bucket's prefix.

    Keyed `local/<file name>` and `bucket/<file name>`: what a build left in the two places the
    takedown's records are kept, byte for byte.
    """
    records: dict[str, bytes] = {}
    for path in sorted((world.data_dir / "suppression").iterdir()):
        records[f"local/{path.name}"] = path.read_bytes()
    listed = world.client.list_objects_v2(Bucket=world.bucket_name, Prefix=SUPPRESSION_PREFIX)
    for one in listed.get("Contents", []):
        key = str(one.get("Key"))
        body = world.client.get_object(Bucket=world.bucket_name, Key=key)["Body"].read()
        records[f"bucket/{key.removeprefix(SUPPRESSION_PREFIX)}"] = body
    return records
