"""The weekly run's parse stage over a table a newer build stamped (`v1-e34-t29`).

The installed agent is a build, and the operator's checkout another: when the checkout's
fingerprint version is ahead, the agent's next pull must not put its own clusters back. These run
`caselist pull` as the command does, in a real run monitor, over the real pipeline and publisher
against moto (`test_pull_parses_new_sources.py`'s installation), and hold the stage to:

* ac1: a parse stage over a table stamped newer than the build, here or in the bucket, is a failed
  stage. The table is left as it was in both places, and the import and the raw publish stand.
* ac2: an equal or older stamp is parsed and published as before. A refusal is in the run summary,
  its reason naming both versions and the store, and in the failure notification, its hint naming
  them too. (PM ruling 2026-10-20: ac2's "stale-data warning" is the run summary and the failure
  notification of `v1-e34-t03`, as for `v1-e39-t09` Q4.)
* The stage takes its answer from the one rule.

Every version is synthetic (PM notes, 2026-10-20).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import pytest

from debate_core.application import caselist_parse as caselist_parse_module
from debate_core.application.caselist import occurrence_table_guard
from debate_core.application.caselist_sync import StageOutcome, SyncStage
from debate_core.application.sync_runs import PARSE_COMMAND, SyncRunOutcome
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION

from .test_inbox_retention import CASELIST, WEEK_1, WEEK_2, WEEK_3, FakeSource, Installation, outcome
from .test_pull_parses_new_sources import (
    COUNTS_OF_THE_FIRST_PARSE,
    CountingParser,
    assert_the_import_and_the_raw_publish_stand,
    parse_stage,
    parsed_tree,
)
from .test_pull_parses_new_sources import installation as installation  # noqa: F401 - a fixture
from .test_pull_parses_new_sources import parsed_keys as parsed_keys  # noqa: F401 - a fixture
from .test_pull_stage_failure_codes import pull, stage

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

BUILD: Final = "synthetic-fingerprint-v7"
NEWER: Final = "synthetic-fingerprint-v8"
OLDER: Final = "synthetic-fingerprint-v6"
TABLE: Final = f"parsed/{CASELIST}/{DOCX_PARSER_VERSION}/occurrences.jsonl"
HERE: Final = "this machine's parsed store"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def always(newer: bool) -> Callable[[str, str], bool]:
    """A comparison that answers `newer` for every pair of versions."""

    def answer(stamped: str, build: str) -> bool:
        return newer

    return answer


@pytest.fixture
def as_build(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], None]:
    """Run as a build at a fingerprint version: what the pipeline stamps, and what the rule compares."""

    def at(version: str) -> None:
        monkeypatch.setattr(caselist_parse_module, "FINGERPRINT_VERSION", version)
        monkeypatch.setattr(occurrence_table_guard, "FINGERPRINT_VERSION", version)

    return at


def bucket_objects(s3_client: S3Client, name: str, prefix: str = "parsed/") -> dict[str, bytes]:
    listed = s3_client.list_objects_v2(Bucket=name, Prefix=prefix).get("Contents", [])
    return {
        str(item.get("Key")): s3_client.get_object(Bucket=name, Key=str(item.get("Key")))["Body"].read()
        for item in listed
    }


def table_stamps(installation: Installation) -> set[str]:
    table = parsed_tree(installation)[TABLE]
    return {json.loads(line)["fingerprint_version"] for line in table.decode("utf-8").splitlines()}


def refused_in(store: str) -> str:
    return (
        f"{CASELIST}: the occurrence table of {CASELIST} {DOCX_PARSER_VERSION} in {store} is stamped "
        f"{NEWER}, newer than this build's {BUILD}; it was left as it was"
    )


def fix_for(store: str) -> str:
    return (
        f"The occurrence table of {CASELIST} {DOCX_PARSER_VERSION} in {store} is stamped {NEWER}, and "
        f"this build's fingerprint version is {BUILD}. Rebuild and publish it with a build at {NEWER} "
        "or later, and install that build for the weekly agent."
    )


# ------------------------------------------------------------------------------------------------
# ac1 and ac2: a newer table on this machine
# ------------------------------------------------------------------------------------------------


async def test_a_pull_over_a_table_a_newer_build_stamped_fails_the_parse_stage_and_leaves_it(
    installation: Installation, as_build: Callable[[str], None], s3_client: S3Client, evidence_bucket: str
) -> None:
    """The newer build pulled 09-01 and 09-08; this one pulls 09-15, and parses none of it."""
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    as_build(NEWER)
    first = await pull(installation, installation.sync(source, parse=parse_stage(installation)))
    assert outcome(first.summary, SyncStage.PARSE) is StageOutcome.COMPLETED
    here, there = parsed_tree(installation), bucket_objects(s3_client, evidence_bucket)
    as_build(BUILD)
    source.weeks = [WEEK_1, WEEK_2, WEEK_3]
    parser = CountingParser()

    watched = await pull(installation, installation.sync(source, parse=parse_stage(installation, parser)))

    parse = stage(watched.summary, SyncStage.PARSE)
    assert (parse["outcome"], parse["error_codes"]) == ("failed", ["NEWER_FINGERPRINT_TABLE"])
    assert parse["reason"] == (
        "0 caselist(s) parsed: 0 source(s) attempted, 0 skipped as parsed already, 0 unsupported, "
        f"0 failed, 0 card(s); 0 object(s) of the parsed store uploaded; "
        f"{refused_in(HERE)}; the parsed store of {CASELIST} is not published"
    )
    assert str(parse["hint"]).startswith(fix_for(HERE))
    assert parser.asked == []
    assert parsed_tree(installation) == here
    assert bucket_objects(s3_client, evidence_bucket) == there
    assert list(watched.summary.snapshots_imported) == [f"{CASELIST} {WEEK_3.isoformat()}"]
    assert outcome(watched.summary, SyncStage.PUBLISH) is StageOutcome.COMPLETED
    assert watched.summary.succeeded, "the parse stage decides nothing about the exit"
    assert watched.pulled.record is not None
    assert watched.pulled.record.outcome is SyncRunOutcome.INCOMPLETE

    [notification] = watched.notifier.sent
    assert notification.title == "caselist pull finished with a failed stage"
    assert "the parse stage failed on NEWER_FINGERPRINT_TABLE" in notification.message
    assert notification.hint is not None and notification.hint.startswith(fix_for(HERE))
    assert notification.fix_command == PARSE_COMMAND


@pytest.mark.parametrize("stamped", [BUILD, OLDER])
async def test_a_pull_over_an_equal_or_older_table_parses_and_publishes_as_before(
    installation: Installation,
    as_build: Callable[[str], None],
    parsed_keys: Any,
    stamped: str,
) -> None:
    """`test_pull_parses_new_sources.py`'s second pull, with the first at `stamped`."""
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    as_build(stamped)
    await pull(installation, installation.sync(source, parse=parse_stage(installation)))
    as_build(BUILD)
    source.weeks = [WEEK_1, WEEK_2, WEEK_3]
    parser = CountingParser()

    watched = await pull(installation, installation.sync(source, parse=parse_stage(installation, parser)))

    assert outcome(watched.summary, SyncStage.PARSE) is StageOutcome.COMPLETED
    assert len(parser.asked) == 1
    assert table_stamps(installation) == {BUILD}
    assert parsed_keys() == set(parsed_tree(installation))
    assert watched.notifier.sent == []


# ------------------------------------------------------------------------------------------------
# ac1 and ac2: a newer table in the bucket
# ------------------------------------------------------------------------------------------------


async def test_a_pull_whose_bucket_holds_a_table_a_newer_build_stamped_parses_here_and_sends_nothing(
    installation: Installation,
    as_build: Callable[[str], None],
    s3_client: S3Client,
    evidence_bucket: str,
    tmp_path: Path,
) -> None:
    """Another machine at the newer version published first. This one parses its own store, and
    the stage fails on the publish it would have made over that machine's table."""
    other = Installation(
        data_dir=tmp_path / "newer-machine", bucket=installation.bucket, archives=installation.archives
    )
    as_build(NEWER)
    await pull(
        other, other.sync(FakeSource(other.archives, weeks=[WEEK_1, WEEK_2]), parse=parse_stage(other))
    )
    there = bucket_objects(s3_client, evidence_bucket)
    assert TABLE in there
    as_build(BUILD)

    watched = await pull(
        installation,
        installation.sync(
            FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2]), parse=parse_stage(installation)
        ),
    )

    parse = stage(watched.summary, SyncStage.PARSE)
    assert (parse["outcome"], parse["error_codes"]) == ("failed", ["NEWER_FINGERPRINT_TABLE"])
    assert parse["reason"] == (
        f"{COUNTS_OF_THE_FIRST_PARSE}; 0 object(s) of the parsed store uploaded; "
        f"{refused_in('the bucket')}; the parsed store of {CASELIST} is not published"
    )
    assert table_stamps(installation) == {BUILD}, "parsed on this machine as before"
    assert bucket_objects(s3_client, evidence_bucket) == there
    assert_the_import_and_the_raw_publish_stand(installation, watched.summary)
    [notification] = watched.notifier.sent
    assert "the parse stage failed on NEWER_FINGERPRINT_TABLE" in notification.message
    assert notification.hint is not None and notification.hint.startswith(fix_for("the bucket"))


# ------------------------------------------------------------------------------------------------
# The stage decides nothing for itself
# ------------------------------------------------------------------------------------------------


async def test_the_parse_stage_takes_the_rules_answer_and_has_none_of_its_own(
    installation: Installation, as_build: Callable[[str], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Told every stamp is newer, the stage fails over the table its own build wrote."""
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    as_build(BUILD)
    await pull(installation, installation.sync(source, parse=parse_stage(installation)))
    monkeypatch.setattr(occurrence_table_guard, "is_newer_fingerprint_version", always(True))
    source.weeks = [WEEK_1, WEEK_2, WEEK_3]

    watched = await pull(installation, installation.sync(source, parse=parse_stage(installation)))

    assert stage(watched.summary, SyncStage.PARSE)["error_codes"] == ["NEWER_FINGERPRINT_TABLE"]
