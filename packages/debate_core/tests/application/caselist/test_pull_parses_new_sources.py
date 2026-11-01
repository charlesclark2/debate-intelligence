"""The weekly pull parses the sources it imported (`v1-e34-t17-pull-parses-new-sources`).

`caselist pull` has had a place for a parse stage since `v1-e34-t02` and nothing in it. This task
puts the parse pipeline of `v1-e31-t06` there, through a thin adapter,
:class:`~debate_core.application.caselist_pull_parse.PullParseStage`, and these tests hold the run
to what that must and must not do:

* ac1: a pull that imports a new snapshot parses only that snapshot's new sources, rebuilds the
  caselist's aggregates and publishes the parsed store; one that imports nothing parses nothing.
* ac2: a failed parse stage records the error code of what failed it, and the import and the raw
  publish stand whatever it was.
* ac3: the summary carries the stage's counts, as integers and nothing else.
* ac6: a run too small for its failure rate to mean anything reports its failures and does not fail.
* ac7: an object of the parsed store the bucket did not take is recorded under the publisher's code.
* What the stage does after a parser-version bump, over a directory a killed run left, and when the
  AWS session expires before or during the parsed store's publish.

Everything is real except the OpenCaselist source and the one thing each test breaks: the importers,
the manifests, the raw publisher, the status comparison, the parse pipeline, the parsed store and
its publisher, against moto, in the installation `test_inbox_retention.py` builds. The archives are
the fictional caselist of `tests/fixtures/parse_pipeline/build_parse_world.py`, whose documents hold
cards.

Every expected count is that fixture's hand-written table (working agreement 6). 09-01 and 09-08
hold six distinct sources: three parse (`verbatim` 1 card, `wiki` 2, `cardmirror` 1), a PDF and a
`.doc` are unsupported, and `broken` is not a zip. So a first parse attempts 6, tries 4 and fails 1,
which is 25%. 09-15 adds `direct`, one card. The parsed store holds one file per source, whatever
its outcome, and three aggregates: 9 objects after the first parse and 10 after the second.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast

import pytest
from tests.fixtures.caselist.interruptible_bucket import ScriptedBucket
from tests.fixtures.caselist.publish_expectations import FICTIONAL_IDENTIFIERS
from tests.fixtures.parse_pipeline.build_parse_world import build_week_zips, digest_of

from debate_core.application.caselist.parse_workers import (
    InProcessParseRunner,
    ParseJob,
    ParseResult,
    ProcessPoolParseRunner,
)
from debate_core.application.caselist.parsed_publish import ParsedStorePublisher
from debate_core.application.caselist.publish_service import SourceResult
from debate_core.application.caselist.suppression import LocalFallbackSuppressionList
from debate_core.application.caselist_card_stats import CaselistCardStatsService
from debate_core.application.caselist_parse import CaselistParseService
from debate_core.application.caselist_pull_parse import PullParseStage
from debate_core.application.caselist_sync import (
    PENDING_WORK_FILENAME,
    ParsedCaselist,
    ParseStageCounts,
    PendingSnapshot,
    PublishedParsedStore,
    RunSummary,
    StageOutcome,
    SyncStage,
    caselists_to_parse,
)
from debate_core.application.errors import (
    StoreCredentialsExpired,
    StoreProfileNotConfigured,
    StoreUnavailable,
)
from debate_core.application.ports.debate_files import DebateFileParser
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectKey
from debate_core.application.ports.parsed_store import version_directory_name
from debate_core.application.ports.suppression import SuppressionEntry, SuppressionList
from debate_core.application.sync_runs import PARSE_COMMAND, SyncRunOutcome
from debate_core.domain.caselist import SnapshotDate, SourceDocument
from debate_core.domain.debate_files import ParsedDocument, ParseFailure
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION, DebateDocxParser
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.s3 import S3EvidenceObjectStore
from debate_core.testing.fakes.caselist import build_fake_caselist_repository
from debate_core.testing.fakes.debate_files import MisbehavingDebateFileParser
from debate_core.testing.fakes.suppression import empty_suppression_list

from .test_inbox_retention import (
    CASELIST,
    ESTUARY,
    ESTUARY_BODY,
    WEEK_1,
    WEEK_2,
    WEEK_3,
    ExpiredBucket,
    FakeSource,
    Installation,
    outcome,
    stage_reason,
)
from .test_pull_stage_failure_codes import RefusingBucket, missing_grant, outage, owed, pull, stage

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

FIRST_TWO_WEEKS = ("verbatim", "wiki", "pdf", "cardmirror", "doc", "broken")
"""The six distinct sources 09-01 and 09-08 hold, by the fixture's short names."""

BUMPED_PARSER = "2099.01.01-docx-9"
"""A parser version later than the one the store was parsed under."""

PUBLISH_ONLY: Final = f"debate-research caselist parse --caselist {CASELIST} --publish-only"
"""What finishes a parse stage whose rebuild read every copy of the list and whose publish did not
finish (`v1-e34-t31`). This installation's list is one copy, read whole, so every rebuild here did."""

PUBLISH_ONLY_FIX: Final = (
    f"`{PUBLISH_ONLY}` publishes the parsed store as this run rebuilt it from every copy of the "
    "suppression list, and rebuilds nothing. The next pull does the same; "
    "`caselist pull --publish-pending` does not."
)

COUNTS_OF_THE_FIRST_PARSE = (
    "1 caselist(s) parsed: 6 source(s) attempted, 0 skipped as parsed already, 2 unsupported, "
    "1 failed, 4 card(s); 1 of them parsed in full, into a version directory that held nothing"
)
"""The parse stage's sentence for a first pull of 09-01 and 09-08, before what it says of the bucket."""


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def installation(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> Installation:
    """An empty data directory, a moto bucket, and the fictional caselist's three weeklies to serve."""
    return Installation(
        data_dir=tmp_path / "evidence",
        bucket=S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
        archives=build_week_zips(tmp_path / "published"),
    )


@pytest.fixture
def parsed_keys(s3_client: S3Client, evidence_bucket: str) -> Iterator[Any]:
    """Reads the keys the bucket holds under `parsed/`."""

    def read() -> set[str]:
        listed = s3_client.list_objects_v2(Bucket=evidence_bucket, Prefix="parsed/").get("Contents", [])
        return {str(item.get("Key")) for item in listed}

    yield read


# ------------------------------------------------------------------------------------------------
# The stage under test, and what stands in for the world going wrong
# ------------------------------------------------------------------------------------------------


class CountingParser:
    """The real parser, recording the digest of every source it is asked to read."""

    def __init__(self, *, parser_version: str | None = None) -> None:
        self._inner = DebateDocxParser()
        self._parser_version = parser_version
        self.asked: list[str] = []

    @property
    def parser_version(self) -> str:
        return self._parser_version or self._inner.parser_version

    @property
    def profile_version(self) -> str:
        return self._inner.profile_version

    def parse(
        self,
        content: bytes,
        source: SourceDocument,
        *,
        source_path: str,
        snapshot: SnapshotDate | None = None,
        camp: str | None = None,
    ) -> ParsedDocument | ParseFailure:
        self.asked.append(source.sha256)
        result = self._inner.parse(content, source, source_path=source_path, snapshot=snapshot, camp=camp)
        if self._parser_version is None or not isinstance(result, ParsedDocument):
            return result
        # A document says which parser read it, and so does every card's provenance.
        return result.model_copy(
            update={
                "parser_version": self.parser_version,
                "cards": tuple(
                    card.model_copy(
                        update={
                            "provenance": card.provenance.model_copy(
                                update={"parser_version": self.parser_version}
                            )
                        }
                    )
                    for card in result.cards
                ),
            }
        )


class RecordingStage:
    """A :class:`PullParseStage` that says what the run asked of it, in the order it asked."""

    def __init__(self, inner: PullParseStage) -> None:
        self._inner = inner
        self.asked: list[tuple[str, str]] = []

    async def parse_new_sources(self, caselist: str) -> ParsedCaselist:
        self.asked.append(("parse", caselist))
        return await self._inner.parse_new_sources(caselist)

    async def publish(self, caselist: str, version: str) -> PublishedParsedStore:
        self.asked.append(("publish", caselist))
        return await self._inner.publish(caselist, version)


class RunnerThatDies:
    """A pool that cannot run at all: what a parse stage that crashes outright looks like."""

    workers = 1

    def run(self, parser: DebateFileParser, jobs: Any) -> Iterator[tuple[ParseJob, ParseResult]]:
        # The message is one no stage may repeat: an error this project did not write is recorded
        # by its class alone.
        raise RuntimeError("the pool died reading Maple Grove/QX/Maple Grove-QX-Aff-Round 1.docx")


def parsed_store_publisher(
    installation: Installation,
    *,
    remote: EvidenceObjectStore | None = None,
    suppression: SuppressionList | None = None,
) -> ParsedStorePublisher:
    """The parsed store's publisher as the composition root builds it, over this data directory."""
    local = FsEvidenceObjectStore(installation.data_dir, subdirectory=Path("parsed"))
    return ParsedStorePublisher(
        local=local,
        local_path_for=local.path_for,
        remote=remote or installation.bucket,
        suppression=suppression or installation.suppression or empty_suppression_list(),
        evidence=installation.local,
    )


def parse_service(
    installation: Installation,
    parser: DebateFileParser | None = None,
    *,
    threshold: float = 0.05,
    minimum: int = 100,
    runner: Any = None,
) -> CaselistParseService:
    """The parse pipeline over this data directory, at the settings' defaults unless a test says."""
    return CaselistParseService(
        local=installation.local,
        store=LocalParsedStore(installation.data_dir),
        parser=parser or DebateDocxParser(),
        runner=runner or InProcessParseRunner(),
        suppression=installation.suppression or empty_suppression_list(),
        card_placer=CaselistCardStatsService(build_fake_caselist_repository()).placer,
        failure_rate_threshold=threshold,
        failure_rate_minimum_sources=minimum,
    )


def parse_stage(
    installation: Installation,
    parser: DebateFileParser | None = None,
    *,
    publish_to: EvidenceObjectStore | None = None,
    **pipeline: Any,
) -> RecordingStage:
    """The pull's parse stage: the adapter over the real pipeline and the real publisher."""
    return RecordingStage(
        PullParseStage(
            parse=parse_service(installation, parser, **pipeline),
            publisher=parsed_store_publisher(installation, remote=publish_to),
        )
    )


def aggregate(installation: Installation, name: str, version: str = DOCX_PARSER_VERSION) -> list[Any]:
    path = installation.data_dir / "parsed" / CASELIST / version / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def parsed_tree(installation: Installation, version: str = DOCX_PARSER_VERSION) -> dict[str, bytes]:
    """Every file of one version directory of this machine's parsed store, by its bucket key."""
    root = installation.data_dir / "parsed"
    return {
        f"parsed/{path.relative_to(root).as_posix()}": path.read_bytes()
        for path in sorted((root / CASELIST / version).rglob("*"))
        if path.is_file()
    }


def counts(summary: RunSummary) -> dict[str, int]:
    """The stage's counts as `caselist pull --json` and the run-summary file carry them."""
    written = summary.as_json()["parse"]
    assert isinstance(written, dict), summary.stages
    return cast("dict[str, int]", written)


def source_key(body: str, version: str = DOCX_PARSER_VERSION) -> str:
    """Where the parsed store keeps one source's file in the bucket."""
    sha = digest_of(body)
    return f"parsed/{CASELIST}/{version}/sha256/{sha[0:2]}/{sha[2:4]}/{sha}.jsonl"


def assert_the_import_and_the_raw_publish_stand(installation: Installation, summary: RunSummary) -> None:
    """Forbidden item 1: both weeks imported, published, confirmed and owed by nothing."""
    weeks = [f"{CASELIST} {WEEK_1.isoformat()}", f"{CASELIST} {WEEK_2.isoformat()}"]
    assert list(summary.snapshots_imported) == weeks
    assert outcome(summary, SyncStage.IMPORT) is StageOutcome.COMPLETED
    assert outcome(summary, SyncStage.PUBLISH) is StageOutcome.COMPLETED
    assert outcome(summary, SyncStage.REPORT) is StageOutcome.COMPLETED
    assert outcome(summary, SyncStage.RETENTION) is StageOutcome.COMPLETED
    assert list(summary.pending_publish) == []
    assert owed(installation) == []
    assert not (installation.data_dir / PENDING_WORK_FILENAME).exists()
    assert installation.inbox_names() == set(), "confirmed in the bucket, so both zips left the inbox"
    # What decides the command's exit status (`v1-e34-t13`): no required stage failed.
    assert summary.succeeded
    assert summary.failure_codes == ()


# ------------------------------------------------------------------------------------------------
# ac1: a pull parses what it imported, rebuilds the aggregates and publishes them
# ------------------------------------------------------------------------------------------------


async def test_a_pull_parses_the_new_snapshots_new_sources_rebuilds_the_aggregates_and_publishes_them(
    installation: Installation, parsed_keys: Any
) -> None:
    """Two weeks, then a third. The second pull's parser is asked for the one source 09-15 adds.

    Nine objects go up after the first pull: six per-source files and three aggregates. After the
    second, three: `direct`'s file, and the index and the occurrence table it changes. The failures
    file is byte for byte what the bucket holds, so it is not sent again.
    """
    first_parser = CountingParser()
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    first = await installation.sync(source, parse=parse_stage(installation, first_parser)).run([CASELIST])

    assert sorted(first_parser.asked) == sorted(digest_of(body) for body in FIRST_TWO_WEEKS)
    assert outcome(first, SyncStage.PARSE) is StageOutcome.COMPLETED
    assert counts(first) == {
        "caselists": 1,
        "full_parses": 1,
        "attempted": 6,
        "skipped": 0,
        "unsupported": 2,
        "failed": 1,
        "cards": 4,
        "uploaded": 9,
        "not_published": 0,
    }
    assert parsed_keys() == set(parsed_tree(installation))
    assert len(parsed_keys()) == 9

    second_parser = CountingParser()
    source.weeks = [WEEK_1, WEEK_2, WEEK_3]
    second = await installation.sync(source, parse=parse_stage(installation, second_parser)).run([CASELIST])

    assert list(second.snapshots_imported) == [f"{CASELIST} {WEEK_3.isoformat()}"]
    assert second_parser.asked == [digest_of("direct")]
    assert outcome(second, SyncStage.PARSE) is StageOutcome.COMPLETED
    assert counts(second) == {
        "caselists": 1,
        "full_parses": 0,
        "attempted": 1,
        "skipped": 6,
        "unsupported": 0,
        "failed": 0,
        "cards": 1,
        "uploaded": 3,
        "not_published": 0,
    }
    # The aggregates were rebuilt over every source the caselist holds, and are what the bucket has.
    assert len(aggregate(installation, "index.jsonl")) == 7
    assert len(aggregate(installation, "occurrences.jsonl")) == 7
    assert {row["last_snapshot"] for row in aggregate(installation, "occurrences.jsonl")} == {"2026-09-15"}
    assert parsed_keys() == set(parsed_tree(installation))
    assert len(parsed_keys()) == 10
    assert stage_reason(second, SyncStage.PARSE) == (
        "1 caselist(s) parsed: 1 source(s) attempted, 6 skipped as parsed already, 0 unsupported, "
        "0 failed, 1 card(s); 3 object(s) of the parsed store uploaded"
    )


async def test_a_pull_that_imports_nothing_asks_nothing_of_the_stage(installation: Installation) -> None:
    """The same listing again: not a plan, not a rebuild, not a publish."""
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    await installation.sync(source, parse=parse_stage(installation)).run([CASELIST])
    before = {path: path.stat().st_mtime_ns for path in sorted((installation.data_dir / "parsed").rglob("*"))}
    parser = CountingParser()
    asked = parse_stage(installation, parser)

    again = await installation.sync(source, parse=asked).run([CASELIST])

    assert list(again.snapshots_imported) == []
    assert asked.asked == []
    assert parser.asked == []
    assert outcome(again, SyncStage.PARSE) is StageOutcome.SKIPPED
    assert stage_reason(again, SyncStage.PARSE) == "nothing new was imported"
    assert again.as_json()["parse"] is None
    assert {
        path: path.stat().st_mtime_ns for path in sorted((installation.data_dir / "parsed").rglob("*"))
    } == before


async def test_an_environment_with_no_bucket_parses_and_publishes_nothing(
    installation: Installation, parsed_keys: Any
) -> None:
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    asked = parse_stage(installation)

    summary = await installation.sync(source, bucket=False, parse=asked).run([CASELIST])

    assert asked.asked == [("parse", CASELIST)]
    assert outcome(summary, SyncStage.PARSE) is StageOutcome.COMPLETED
    assert counts(summary)["uploaded"] == 0
    assert counts(summary)["not_published"] == 0, "nothing is owed to a bucket this environment has not got"
    assert stage_reason(summary, SyncStage.PARSE) == COUNTS_OF_THE_FIRST_PARSE
    assert parsed_keys() == set()


def test_each_caselist_imported_into_is_parsed_once_and_a_complete_archive_names_none() -> None:
    """Two weeks of one caselist are one parse; a camp release is `openev`; `full/` is nothing."""
    imported = [
        PendingSnapshot("hsld26", "2026-10-07"),
        PendingSnapshot("hspf26", "2026-10-07"),
        PendingSnapshot("hsld26", "2026-10-14"),
        PendingSnapshot("openev", "2026-policy"),
        PendingSnapshot("hspolicy26", "full/2026-10-14"),
    ]

    assert caselists_to_parse(imported) == ("hsld26", "hspf26", "openev")
    assert caselists_to_parse([PendingSnapshot("hspolicy26", "full/2026-10-14")]) == ()
    assert caselists_to_parse([]) == ()


# ------------------------------------------------------------------------------------------------
# ac3: counts only
# ------------------------------------------------------------------------------------------------


async def test_the_summary_says_of_the_stage_nine_integers_and_nothing_else(
    installation: Installation,
) -> None:
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])

    summary = await installation.sync(source, parse=parse_stage(installation)).run([CASELIST])

    assert sorted(counts(summary)) == [
        "attempted",
        "cards",
        "caselists",
        "failed",
        "full_parses",
        "not_published",
        "skipped",
        "unsupported",
        "uploaded",
    ]
    assert all(type(value) is int for value in counts(summary).values())
    assert ParseStageCounts().as_json() == dict.fromkeys(counts(summary), 0)
    text = json.dumps(summary.as_json())
    for forbidden in (*FICTIONAL_IDENTIFIERS, ".docx", ".pdf"):
        assert forbidden not in text


# ------------------------------------------------------------------------------------------------
# ac2: a failed parse stage records what failed it, and what came before it stands
# ------------------------------------------------------------------------------------------------


async def test_a_failure_rate_over_the_threshold_fails_the_stage_and_nothing_before_it(
    installation: Installation, parsed_keys: Any
) -> None:
    """One of the four sources tried fails, in a run just large enough for 25% to be judged."""
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    service = installation.sync(source, parse=parse_stage(installation, threshold=0.2, minimum=4))

    watched = await pull(installation, service)

    parse = stage(watched.summary, SyncStage.PARSE)
    assert parse["outcome"] == "failed"
    assert parse["error_codes"] == ["PARSE_FAILURE_RATE_EXCEEDED"]
    assert parse["reason"] == (
        f"{COUNTS_OF_THE_FIRST_PARSE}; 9 object(s) of the parsed store uploaded; "
        f"{CASELIST}: 1 of the 4 source(s) tried failed, over the failure-rate threshold"
    )
    assert "caselist parse --caselist <slug> --failures" in str(parse["hint"])
    assert_the_import_and_the_raw_publish_stand(installation, watched.summary)
    # What parsed is published all the same, as `caselist parse --publish` publishes it.
    assert len(parsed_keys()) == 9
    assert watched.pulled.record is not None
    assert watched.pulled.record.outcome is SyncRunOutcome.INCOMPLETE
    # Running the pull again would import nothing and so parse nothing: the fix is the parse command.
    [notification] = watched.notifier.sent
    assert notification.title == "caselist pull finished with a failed stage"
    assert notification.fix_command == PARSE_COMMAND


async def test_a_parsed_store_the_bucket_does_not_answer_for_fails_the_stage_with_the_stores_code(
    installation: Installation, parsed_keys: Any
) -> None:
    """The raw publish went through; the parsed store's listing gets a `SlowDown`."""
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    asked = parse_stage(installation, publish_to=RefusingBucket(outage()))

    watched = await pull(installation, installation.sync(source, parse=asked))

    parse = stage(watched.summary, SyncStage.PARSE)
    assert parse["outcome"] == "failed"
    assert parse["error_codes"] == ["STORE_UNAVAILABLE"]
    assert parse["reason"] == (
        f"{COUNTS_OF_THE_FIRST_PARSE}; 0 object(s) of the parsed store uploaded; "
        "ListObjectsV2 on s3://debate-test-evidence-moto/manifests/testcl26/ failed: SlowDown; "
        f"the parsed store of {CASELIST} is not published"
    )
    assert str(parse["hint"]).endswith(PUBLISH_ONLY_FIX), "the rebuild is done: only the publish is owed"
    assert counts(watched.summary)["not_published"] == 1
    assert_the_import_and_the_raw_publish_stand(installation, watched.summary)
    # The parse itself is whole on this machine; only its copy in the bucket is missing.
    assert len(aggregate(installation, "index.jsonl")) == 6
    assert parsed_keys() == set()


async def test_a_bucket_that_refuses_the_parsed_store_fails_the_stage_and_names_the_grant(
    installation: Installation,
) -> None:
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    asked = parse_stage(installation, publish_to=RefusingBucket(missing_grant()))

    summary = await installation.sync(source, parse=asked).run([CASELIST])

    parse = stage(summary, SyncStage.PARSE)
    assert (parse["outcome"], parse["error_codes"]) == ("failed", ["STORE_ACCESS_DENIED"])
    assert "lacks a grant" in str(parse["hint"])
    assert str(missing_grant().hint) in str(parse["hint"]), "the adapter's sentence, read from the error"
    assert str(parse["hint"]).endswith(PUBLISH_ONLY_FIX)
    assert_the_import_and_the_raw_publish_stand(installation, summary)


class ParsesAndCannotPublish:
    """A parse stage that parses each caselist and is refused every publish with `error`."""

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.asked: list[tuple[str, str]] = []

    async def parse_new_sources(self, caselist: str) -> ParsedCaselist:
        self.asked.append(("parse", caselist))
        return ParsedCaselist(version=DOCX_PARSER_VERSION)

    async def publish(self, caselist: str, version: str) -> PublishedParsedStore:
        self.asked.append(("publish", caselist))
        raise self.error


async def test_a_profile_the_aws_config_lacks_stops_the_parsed_publish_at_the_first_caselist(
    installation: Installation,
) -> None:
    """True of every caselist still to publish, as a refusal is, so none after the first is tried.

    A weekly and a camp file make two caselists to parse: the weekly's and `openev` (`v1-e29-t09`
    ac1). Both are parsed; only the first is offered to the bucket.
    """
    missing = StoreProfileNotConfigured(
        "debate-dev-evidence-typo",
        setting="storage.s3.aws_profile",
        hint="set storage.s3.aws_profile to a profile this machine's AWS config defines",
    )
    asked = ParsesAndCannotPublish(missing)
    source = FakeSource(installation.archives, weeks=[WEEK_1], openev=[(ESTUARY, ESTUARY_BODY)])

    summary = await installation.sync(source, parse=asked).run([CASELIST])

    parsed = [caselist for kind, caselist in asked.asked if kind == "parse"]
    assert sorted(parsed) == sorted([CASELIST, "openev"])
    assert [one for one in asked.asked if one[0] == "publish"] == [("publish", parsed[0])]
    parse = stage(summary, SyncStage.PARSE)
    assert (parse["outcome"], parse["error_codes"]) == ("failed", ["STORE_PROFILE_NOT_CONFIGURED"])
    assert str(missing.hint) in str(parse["hint"])
    assert counts(summary)["not_published"] == 2


async def test_objects_the_bucket_did_not_take_are_recorded_under_the_publishers_codes(
    installation: Installation, parsed_keys: Any, tmp_path: Path
) -> None:
    """ac7's codes in the stage: one source file mismatched in the bucket, another answered 503.

    The other four source files go up; the aggregates are withheld, because an index must never
    name a file the bucket does not hold.
    """
    other_bytes = tmp_path / "not-what-this-machine-parsed.jsonl"
    other_bytes.write_text('{"not": "what this machine parsed"}\n', encoding="utf-8")
    await installation.bucket.put_file(source_key("verbatim"), other_bytes)

    def no_answer_for_the_wiki_file(key: ObjectKey, _: int) -> None:
        if key == source_key("wiki"):
            raise StoreUnavailable("PutObject", key, "simulated 503 SlowDown")

    assert isinstance(installation.bucket, S3EvidenceObjectStore)
    scripted = ScriptedBucket(installation.bucket, before_put=no_answer_for_the_wiki_file)
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])

    summary = await installation.sync(source, parse=parse_stage(installation, publish_to=scripted)).run(
        [CASELIST]
    )

    parse = stage(summary, SyncStage.PARSE)
    assert parse["outcome"] == "failed"
    assert sorted(cast("list[str]", parse["error_codes"])) == ["CHECKSUM_MISMATCH", "STORE_UNAVAILABLE"]
    assert f"{CASELIST}: 2 object(s) of the parsed store not confirmed in the bucket" in str(parse["reason"])
    assert counts(summary)["uploaded"] == 4
    assert counts(summary)["not_published"] == 1
    assert parse["hint"] == PUBLISH_ONLY_FIX, "the rebuild is done: only the publish is owed (`v1-e34-t31`)"
    assert not any(key.endswith(("index.jsonl", "occurrences.jsonl")) for key in parsed_keys())
    assert_the_import_and_the_raw_publish_stand(installation, summary)


async def test_a_parse_that_crashes_outright_fails_the_stage_by_its_class_and_the_run_finishes(
    installation: Installation, parsed_keys: Any
) -> None:
    """Whatever the pipeline raises, a bug included, the stages after it still run."""
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    asked = parse_stage(installation, runner=RunnerThatDies())

    watched = await pull(installation, installation.sync(source, parse=asked))

    parse = stage(watched.summary, SyncStage.PARSE)
    assert parse["outcome"] == "failed"
    assert parse["error_codes"] == ["INTERNAL_ERROR"]
    assert parse["reason"] == (
        "0 caselist(s) parsed: 0 source(s) attempted, 0 skipped as parsed already, 0 unsupported, "
        f"0 failed, 0 card(s); 0 object(s) of the parsed store uploaded; {CASELIST}: RuntimeError; "
        f"the parsed store of {CASELIST} is not published"
    )
    assert asked.asked == [("parse", CASELIST)], "a caselist whose parse failed is not published"
    assert parsed_keys() == set()
    assert_the_import_and_the_raw_publish_stand(installation, watched.summary)
    assert watched.pulled.summary_path is not None and watched.pulled.summary_path.is_file()
    for text in (watched.pulled.summary_path.read_text(encoding="utf-8"), watched.notified):
        for forbidden in FICTIONAL_IDENTIFIERS:
            assert forbidden not in text


async def test_a_worker_that_dies_on_one_source_is_a_failed_source_and_counts_toward_the_rate(
    installation: Installation,
) -> None:
    """The real pool: one worker killed mid-parse, and the run carries on with a new one.

    Two of the four sources tried fail now, `broken` and the one whose worker died: 50%, in a run
    large enough to be judged, so the stage fails on the rate.
    """
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    asked = parse_stage(
        installation,
        MisbehavingDebateFileParser(DebateDocxParser(), crash={digest_of("wiki")}),
        runner=ProcessPoolParseRunner(workers=1, timeout_seconds=60),
        threshold=0.2,
        minimum=4,
    )

    summary = await installation.sync(source, parse=asked).run([CASELIST])

    parse = stage(summary, SyncStage.PARSE)
    assert (parse["outcome"], parse["error_codes"]) == ("failed", ["PARSE_FAILURE_RATE_EXCEEDED"])
    assert f"{CASELIST}: 2 of the 4 source(s) tried failed" in str(parse["reason"])
    # `wiki` held two of the four cards.
    assert (counts(summary)["failed"], counts(summary)["cards"]) == (2, 2)
    failed = [row for row in aggregate(installation, "failures.jsonl") if row["outcome"] == "FAILED"]
    assert sorted(row["reason"] for row in failed) == ["NOT_A_ZIP", "WORKER_CRASHED"]
    assert_the_import_and_the_raw_publish_stand(installation, summary)


async def test_a_failed_parse_stage_beside_a_retryable_publish_failure_leaves_the_exit_to_the_publish(
    installation: Installation,
) -> None:
    """`v1-e34-t13`'s rule reads the required stages only: the run is one a retry may cure.

    The raw publish does not answer, so both weeks stay owed. The parse stage fails on the rate, a
    verdict, and contributes nothing to the codes the exit status is decided from.
    """
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    service = installation.sync(
        source,
        publish_to=RefusingBucket(outage()),
        parse=parse_stage(installation, threshold=0.2, minimum=4, publish_to=RefusingBucket(outage())),
    )

    summary = await service.run([CASELIST])

    assert stage(summary, SyncStage.PUBLISH)["error_codes"] == ["STORE_UNAVAILABLE"]
    assert stage(summary, SyncStage.PARSE)["outcome"] == "failed"
    assert sorted(cast("list[str]", stage(summary, SyncStage.PARSE)["error_codes"])) == [
        "PARSE_FAILURE_RATE_EXCEEDED",
        "STORE_UNAVAILABLE",
    ]
    assert not summary.succeeded
    assert summary.failure_codes == ("STORE_UNAVAILABLE",)
    assert owed(installation) == [f"{CASELIST} {WEEK_1.isoformat()}", f"{CASELIST} {WEEK_2.isoformat()}"]


# ------------------------------------------------------------------------------------------------
# ac6: a run too small for its failure rate to mean anything
# ------------------------------------------------------------------------------------------------


async def test_at_the_default_minimum_one_bad_file_in_a_small_week_is_reported_and_fails_nothing(
    installation: Installation,
) -> None:
    """Four sources tried and one failed is 25% against a 5% threshold, and far under 100 tried."""
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])

    summary = await installation.sync(source, parse=parse_stage(installation)).run([CASELIST])

    assert outcome(summary, SyncStage.PARSE) is StageOutcome.COMPLETED
    assert counts(summary)["failed"] == 1
    assert "1 failed" in stage_reason(summary, SyncStage.PARSE)


@pytest.mark.parametrize(
    ("minimum", "expected"),
    [
        (5, StageOutcome.COMPLETED),  # four tried, one short of the minimum: reported, not judged
        (4, StageOutcome.FAILED),  # exactly the minimum: judged, and 25% is over 20%
        (3, StageOutcome.FAILED),  # a small run over the minimum still fails on the rate
    ],
)
async def test_the_stage_judges_the_rate_from_the_minimum_number_of_sources_tried(
    installation: Installation, minimum: int, expected: StageOutcome
) -> None:
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    asked = parse_stage(installation, threshold=0.2, minimum=minimum)

    summary = await installation.sync(source, parse=asked).run([CASELIST])

    assert outcome(summary, SyncStage.PARSE) is expected
    assert counts(summary)["failed"] == 1, "reported either way"


# ------------------------------------------------------------------------------------------------
# After a parser-version bump, and over a directory a killed run left
# ------------------------------------------------------------------------------------------------


async def test_after_a_parser_version_bump_the_caselist_is_parsed_in_full_and_the_summary_says_so(
    installation: Installation, parsed_keys: Any
) -> None:
    """The plan is over the caselist, not the imported snapshot, so the new directory is whole.

    Parsing 09-15's one new source alone would leave the new version's directory holding one file
    and aggregates built from it. Instead all seven sources are parsed into it, the summary counts
    a full parse, and the old directory is left byte for byte.
    """
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    await installation.sync(source, parse=parse_stage(installation)).run([CASELIST])
    as_the_old_parser_left_it = parsed_tree(installation)
    bumped = CountingParser(parser_version=BUMPED_PARSER)
    source.weeks = [WEEK_1, WEEK_2, WEEK_3]

    summary = await installation.sync(source, parse=parse_stage(installation, bumped)).run([CASELIST])

    assert sorted(bumped.asked) == sorted(digest_of(body) for body in (*FIRST_TWO_WEEKS, "direct"))
    assert counts(summary) == {
        "caselists": 1,
        "full_parses": 1,
        "attempted": 7,
        "skipped": 0,
        "unsupported": 2,
        "failed": 1,
        "cards": 5,
        "uploaded": 10,
        "not_published": 0,
    }
    assert "1 of them parsed in full, into a version directory that held nothing" in stage_reason(
        summary, SyncStage.PARSE
    )
    assert len(aggregate(installation, "index.jsonl", BUMPED_PARSER)) == 7
    assert len(aggregate(installation, "occurrences.jsonl", BUMPED_PARSER)) == 7
    assert parsed_tree(installation) == as_the_old_parser_left_it
    assert parsed_keys() == set(as_the_old_parser_left_it) | set(parsed_tree(installation, BUMPED_PARSER))


async def test_a_caselist_reparsed_into_a_second_generation_is_parsed_and_published_there(
    installation: Installation, parsed_keys: Any
) -> None:
    """`caselist parse --reparse` starts a new generation of the same parser version.

    The pull's stage writes to the newest generation, as `caselist parse` does, and publishes that
    directory, not the first: the directory's name is not the parser version's.
    """
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    await installation.sync(source, parse=parse_stage(installation)).run([CASELIST])
    first_generation = set(parsed_keys())
    by_hand = parse_service(installation)
    await by_hand.run(await by_hand.plan(CASELIST, reparse=True))
    second = version_directory_name(DOCX_PARSER_VERSION, 2)
    parser = CountingParser()
    source.weeks = [WEEK_1, WEEK_2, WEEK_3]

    summary = await installation.sync(source, parse=parse_stage(installation, parser)).run([CASELIST])

    assert parser.asked == [digest_of("direct")]
    assert counts(summary)["full_parses"] == 0
    assert len(aggregate(installation, "index.jsonl", second)) == 7
    assert len(aggregate(installation, "index.jsonl")) == 6, "the first generation is never written again"
    # Seven source files and three aggregates, none of which the bucket held for this generation.
    assert counts(summary)["uploaded"] == 10
    assert parsed_keys() == first_generation | set(parsed_tree(installation, second))


async def test_a_version_directory_a_killed_run_left_partly_filled_is_completed(
    installation: Installation,
) -> None:
    """A run stopped before its rebuild leaves per-source files and no aggregates.

    Here one source's file is missing too. The next pull parses that source and the new week's,
    skips the five that are recorded, and rebuilds the aggregates over all seven. It is not a full
    parse, and the summary does not call it one.
    """
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    await installation.sync(source, parse=parse_stage(installation)).run([CASELIST])
    directory = installation.data_dir / "parsed" / CASELIST / DOCX_PARSER_VERSION
    for name in ("index.jsonl", "failures.jsonl", "occurrences.jsonl"):
        (directory / name).unlink()
    [never_written] = directory.rglob(f"{digest_of('cardmirror')}.*")
    never_written.unlink()
    parser = CountingParser()
    source.weeks = [WEEK_1, WEEK_2, WEEK_3]

    summary = await installation.sync(source, parse=parse_stage(installation, parser)).run([CASELIST])

    assert sorted(parser.asked) == sorted([digest_of("cardmirror"), digest_of("direct")])
    assert (counts(summary)["attempted"], counts(summary)["skipped"]) == (2, 5)
    assert counts(summary)["full_parses"] == 0
    assert len(aggregate(installation, "index.jsonl")) == 7
    assert len(aggregate(installation, "occurrences.jsonl")) == 7
    assert outcome(summary, SyncStage.PARSE) is StageOutcome.COMPLETED


# ------------------------------------------------------------------------------------------------
# A session that expires before, or during, the parsed store's publish
# ------------------------------------------------------------------------------------------------


async def test_with_no_session_the_stage_parses_here_sends_nothing_and_is_pending(
    installation: Installation, parsed_keys: Any
) -> None:
    """The usual weekly run: the SSO session expired overnight.

    The raw publish pends and both weeks are owed, as before this task. The parse runs, because it
    needs no session, and the bucket is not asked for anything on the parsed store's account. The
    pending-work file holds the two snapshots and nothing about a parsed store.
    """
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    parser = CountingParser()
    asked = parse_stage(installation, parser, publish_to=ExpiredBucket())
    service = installation.sync(source, publish_to=ExpiredBucket(), compare_with=ExpiredBucket(), parse=asked)

    watched = await pull(installation, service)

    summary = watched.summary
    assert outcome(summary, SyncStage.PUBLISH) is StageOutcome.PENDING
    assert len(parser.asked) == 6
    assert asked.asked == [("parse", CASELIST)], "no publish is asked for once a login is known to be missing"
    parse = stage(summary, SyncStage.PARSE)
    assert parse["outcome"] == "pending"
    assert parse["error_codes"] == []
    # This installation's list is one copy, read whole, so the rebuild read every copy and only the
    # publish is owed (`v1-e34-t31`). The pull's own list, whose bucket copy needs the login too, is
    # read from this machine's copy alone on such a day, and the stage then names `--publish`:
    # `test_aggregates_rebuilt_from_this_machines_copy_of_the_list_alone_are_not_published` below.
    assert parse["reason"] == (
        f"{COUNTS_OF_THE_FIRST_PARSE}; 0 object(s) of the parsed store uploaded; the parsed store of "
        f"{CASELIST} is not published, for want of an AWS login (the publish stage found no AWS "
        f"session): {PUBLISH_ONLY_FIX}"
    )
    assert counts(summary)["not_published"] == 1
    assert len(aggregate(installation, "index.jsonl")) == 6
    assert parsed_keys() == set()
    # The import stands, and what is owed is exactly what was owed before this task.
    weeks = [f"{CASELIST} {WEEK_1.isoformat()}", f"{CASELIST} {WEEK_2.isoformat()}"]
    assert list(summary.snapshots_imported) == weeks
    assert owed(installation) == weeks
    pending_file = json.loads((installation.data_dir / PENDING_WORK_FILENAME).read_text(encoding="utf-8"))
    assert sorted(pending_file) == ["publish"]
    assert summary.succeeded
    assert watched.pulled.record is not None
    assert watched.pulled.record.outcome is SyncRunOutcome.PUBLISH_PENDING
    # One notification, for the login, and it says the parsed store waits on it too.
    [notification] = watched.notifier.sent
    assert notification.title == "caselist publish waiting for an AWS login"
    assert f"The parsed store waits too; after the login: {PUBLISH_ONLY}" in notification.message
    # The run log keeps the stage's whole sentence, which is where `caselist runs` reads the counts
    # and the command from: it is longer than the 500 characters other stages are cut to.
    [recorded] = [one for one in watched.pulled.record.stages if one.stage == "parse"]
    assert recorded.reason == parse["reason"]
    assert recorded.reason is not None and len(recorded.reason) > 500


async def test_a_session_that_expires_during_the_parsed_stores_publish_leaves_the_raw_publish_whole(
    installation: Installation, parsed_keys: Any
) -> None:
    """The raw publish and its confirmation went through; the session ran out before the next call.

    Nothing is owed in the pending-work file, because every snapshot is confirmed, and the stage is
    pending and says which command finishes it.
    """
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    asked = parse_stage(installation, publish_to=ExpiredBucket())

    watched = await pull(installation, installation.sync(source, parse=asked))

    summary = watched.summary
    assert asked.asked == [("parse", CASELIST), ("publish", CASELIST)]
    parse = stage(summary, SyncStage.PARSE)
    assert parse["outcome"] == "pending"
    assert "is not published, for want of an AWS login" in str(parse["reason"])
    assert str(parse["reason"]).endswith(PUBLISH_ONLY_FIX)
    assert counts(summary)["not_published"] == 1
    assert parsed_keys() == set()
    assert_the_import_and_the_raw_publish_stand(installation, summary)
    assert watched.pulled.record is not None
    assert watched.pulled.record.outcome is SyncRunOutcome.PUBLISH_PENDING
    assert any(f"after the login: {PUBLISH_ONLY}" in one.message for one in watched.notifier.sent)


async def test_publish_pending_does_not_publish_the_parsed_store_and_caselist_parse_publish_does(
    installation: Installation, parsed_keys: Any
) -> None:
    """How the operator finishes it after `aws sso login`, as the runbook states.

    `caselist pull --publish-pending` drains the snapshots and leaves the parsed store alone: the
    pending-work file names snapshots, and a parsed store is not one. `caselist parse --publish`,
    which is a plan, a run and a publish, parses nothing again and uploads all nine objects.
    """
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    without_a_session = installation.sync(
        source,
        publish_to=ExpiredBucket(),
        compare_with=ExpiredBucket(),
        parse=parse_stage(installation, publish_to=ExpiredBucket()),
    )
    await without_a_session.run([CASELIST])

    asked = parse_stage(installation)
    drained = await pull(installation, installation.sync(source, parse=asked), publish_pending=True)

    assert owed(installation) == []
    assert asked.asked == []
    assert stage(drained.summary, SyncStage.PARSE) == {
        "stage": "parse",
        "outcome": "skipped",
        "reason": "publish-pending runs no derived stages",
        "error_codes": [],
        "hint": None,
        "earlier_findings": [],
        "drift": [],
        "not_compared": [],
    }
    assert parsed_keys() == set()

    parser = CountingParser()
    by_hand = parse_service(installation, parser)
    plan = await by_hand.plan(CASELIST)
    await by_hand.run(plan)
    published = await parsed_store_publisher(installation).publish(CASELIST, plan.version)

    assert parser.asked == []
    assert published.succeeded
    assert published.count(SourceResult.UPLOADED) == 9
    assert parsed_keys() == set(parsed_tree(installation))


async def test_the_next_pull_that_imports_into_the_caselist_publishes_what_an_earlier_one_could_not(
    installation: Installation, parsed_keys: Any
) -> None:
    """Nothing has to be written down: the publisher sends whatever the bucket lacks of the directory."""
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    await installation.sync(source, parse=parse_stage(installation, publish_to=ExpiredBucket())).run(
        [CASELIST]
    )
    assert parsed_keys() == set()
    source.weeks = [WEEK_1, WEEK_2, WEEK_3]

    summary = await installation.sync(source, parse=parse_stage(installation)).run([CASELIST])

    assert outcome(summary, SyncStage.PARSE) is StageOutcome.COMPLETED
    assert counts(summary)["attempted"] == 1
    assert counts(summary)["uploaded"] == 10, "seven source files and three aggregates, all of them new there"
    assert counts(summary)["not_published"] == 0
    assert parsed_keys() == set(parsed_tree(installation))


class ListWhoseBucketCopyNeedsALogin:
    """Every copy of the suppression list read as one, on a day the bucket's needs a session."""

    async def entries(self) -> tuple[SuppressionEntry, ...]:
        raise StoreCredentialsExpired(hint="aws sso login --profile debate-dev-evidence")

    async def append(self, entries: Sequence[SuppressionEntry]) -> None:  # pragma: no cover - never written
        raise AssertionError("a pull never writes the suppression list")


async def test_aggregates_rebuilt_from_this_machines_copy_of_the_list_alone_are_not_published(
    installation: Installation, parsed_keys: Any
) -> None:
    """The parse read the suppression list without its bucket copy, so its aggregates stay here.

    The pull's list falls back to this machine's copy when the bucket's needs a login, so that the
    local stages need no session. An aggregate built from that copy alone may hold a source a
    removal made elsewhere took out, and a bucket that answers by the time the publish is reached
    must not be sent it. The stage sees the fallback and asks for no publish.
    """
    installation.suppression = LocalFallbackSuppressionList(
        ListWhoseBucketCopyNeedsALogin(), local=empty_suppression_list()
    )
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    asked = RecordingStage(
        PullParseStage(
            parse=parse_service(installation),
            publisher=parsed_store_publisher(installation, suppression=empty_suppression_list()),
        )
    )

    summary = await installation.sync(source, parse=asked).run([CASELIST])

    assert asked.asked == [("parse", CASELIST)]
    parse = stage(summary, SyncStage.PARSE)
    assert parse["outcome"] == "pending"
    assert "the suppression list's bucket copy needed an AWS login" in str(parse["reason"])
    assert "this machine's copy of the suppression list alone was read" in str(parse["reason"])
    # So the command named rebuilds first, and never publishes these aggregates (`v1-e34-t31`).
    assert f"`debate-research caselist parse --caselist {CASELIST} --publish`" in str(parse["reason"])
    assert "--publish-only" not in str(parse["reason"])
    assert summary.suppression_list_local_copy_only is not None
    assert counts(summary)["not_published"] == 1
    assert len(aggregate(installation, "index.jsonl")) == 6
    assert parsed_keys() == set()


# ------------------------------------------------------------------------------------------------
# The adapter itself
# ------------------------------------------------------------------------------------------------


async def test_the_adapter_plans_over_the_caselist_and_reports_the_pipelines_counts(
    installation: Installation,
) -> None:
    """`parse_new_sources` is `caselist parse --caselist <slug>`: no snapshot, no `--reparse`."""
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    await installation.sync(source, bucket=False).run([CASELIST])
    adapter = PullParseStage(parse=parse_service(installation, threshold=0.2, minimum=4), publisher=None)

    first = await adapter.parse_new_sources(CASELIST)
    again = await adapter.parse_new_sources(CASELIST)

    assert first == ParsedCaselist(
        version=DOCX_PARSER_VERSION,
        attempted=6,
        skipped=0,
        unsupported=2,
        failed=1,
        cards=4,
        tried=4,
        full_parse=True,
        failure_rate_exceeded=True,
    )
    # Nothing left to parse: not a full parse, and no rate to exceed.
    assert again == ParsedCaselist(version=DOCX_PARSER_VERSION, skipped=6)
    with pytest.raises(ValueError, match="names no evidence bucket"):
        await adapter.publish(CASELIST, DOCX_PARSER_VERSION)


async def test_the_stage_never_reads_the_full_archive_namespace(
    installation: Installation, tmp_path: Path
) -> None:
    """Forbidden item 3: a manifest under `full/` adds nothing to what the stage parses.

    The complete archive's manifest here lists a source no weekly holds. `v1-e31-t06`'s enumeration
    does not read that namespace, and the stage adds no enumeration of its own.
    """
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    await installation.sync(source, bucket=False).run([CASELIST])
    weekly = installation.data_dir / "objects" / "manifests" / CASELIST / f"{WEEK_2.isoformat()}.jsonl"
    assert weekly.is_file()
    only_in_the_complete_archive = "f" * 64
    full = weekly.parent / "full" / f"{WEEK_2.isoformat()}.jsonl"
    full.parent.mkdir(parents=True)
    full.write_text(
        weekly.read_text(encoding="utf-8").replace(digest_of("verbatim"), only_in_the_complete_archive),
        encoding="utf-8",
    )
    parser = CountingParser()

    parsed = await PullParseStage(
        parse=parse_service(installation, parser), publisher=None
    ).parse_new_sources(CASELIST)

    assert parsed.attempted == 6
    assert only_in_the_complete_archive not in parser.asked
    assert only_in_the_complete_archive not in {
        row["source_sha256"] for row in aggregate(installation, "index.jsonl")
    }
