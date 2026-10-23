"""`debate-research tub index build | publish`, run the way an operator runs them (`v1-e39-t02`).

Through Typer's `CliRunner` against the real application and composition root: the local parsed store
on disk, the local caselist database, the local suppression list, the real SQLite writer, and the real
S3 adapter over moto. Dev and prod name different moto buckets, so the tests can see that `DEBATE_ENV`
picks the bucket and `--env` only confirms it. The store holds one invented card.

Nothing here reaches AWS: moto answers botocore in-process and sockets are disabled.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import boto3
import pytest
from moto import mock_aws
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.ports.parsed_store import (
    DocumentRecord,
    OccurrenceRecord,
    SourceEntry,
    SourceOutcome,
)
from debate_core.application.ports.suppression import (
    ReasonCode,
    SuppressionAction,
    SuppressionEntry,
    disclosure_digest,
)
from debate_core.domain.card_occurrence import ClusterMembership
from debate_core.domain.caselist import SourceFormat, SourceOrigin
from debate_core.domain.debate_files import CardCompleteness, FileImportProvenance, ParsedCard, ParsedDocument
from debate_core.domain.style_profile import StyleMatchSource
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION, card_fingerprint
from debate_core.integrations.docx_parser import DebateDocxParser
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.suppression_list import local_suppression_list_file

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

runner = CliRunner()

DEV_BUCKET: Final = "debate-dev-evidence-moto"
PROD_BUCKET: Final = "debate-prod-evidence-moto"
PROFILES: Final = {"dev": "debate-dev-evidence", "prod": "debate-prod-evidence"}
CASELIST: Final = "hsld26"
SOURCE: Final = "1" * 64
PARSER: Final = DebateDocxParser().parser_version
PROFILE: Final = DebateDocxParser().profile_version


@pytest.fixture(autouse=True)
def installation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """Dev and prod profiles naming different buckets and one data directory, and fake AWS."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    config = tmp_path / "aws-config"
    config.write_text(
        "".join(f"[profile {p}]\nregion = us-east-1\n" for p in PROFILES.values()), encoding="utf-8"
    )
    credentials = tmp_path / "aws-credentials"
    credentials.write_text(
        "".join(
            f"[{p}]\naws_access_key_id = testing\naws_secret_access_key = testing\n"
            for p in PROFILES.values()
        ),
        encoding="utf-8",
    )
    for name, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_EC2_METADATA_DISABLED": "true",
        "AWS_CONFIG_FILE": str(config),
        "AWS_SHARED_CREDENTIALS_FILE": str(credentials),
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    data_dir = tmp_path / "data"
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    for environment, bucket in (("dev", DEV_BUCKET), ("prod", PROD_BUCKET)):
        (profiles / f"{environment}.toml").write_text(
            f'[storage]\ndata_dir = "{data_dir}"\n'
            f'[storage.s3]\nbucket = "{bucket}"\nregion = "us-east-1"\n'
            f'aws_profile = "{PROFILES[environment]}"\n'
            f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 1.0\n',
            encoding="utf-8",
        )
    monkeypatch.setenv("DEBATE_PROFILE_DIR", str(profiles))
    monkeypatch.setenv("DEBATE_ENV", "dev")
    yield data_dir


@pytest.fixture
def buckets() -> Iterator[S3Client]:
    with mock_aws():
        client: S3Client = boto3.client("s3", region_name="us-east-1")  # pyright: ignore[reportUnknownMemberType]
        for bucket in (DEV_BUCKET, PROD_BUCKET):
            client.create_bucket(Bucket=bucket)
            client.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})
        yield client


@pytest.fixture
def parsed(installation: Path) -> Path:
    """One parsed source of one invented card, and its occurrence row, in the local store."""
    card = ParsedCard(
        tag="Invented growth claim",
        full_cite="Okonkwo 26",
        evidence_text="Invented growth always ends badly",
        completeness=CardCompleteness.FULL,
        match_source=StyleMatchSource.HEURISTIC,
        confidence=0.9,
        provenance=FileImportProvenance(
            source_sha256=SOURCE,
            source_path="placeholder.docx",
            origin=SourceOrigin.CASELIST_ARCHIVE,
            caselist=CASELIST,
            snapshot=date(2026, 9, 1),
            first_element_index=0,
            last_element_index=2,
            parser_version=PARSER,
            profile_version=PROFILE,
        ),
    )
    fields: dict[str, Any] = {
        "caselist": CASELIST,
        "snapshot": "2026-09-01",
        "source_sha256": SOURCE,
        "parser_version": PARSER,
        "profile_version": PROFILE,
        "fingerprint_version": FINGERPRINT_VERSION,
    }
    store = LocalParsedStore(installation)
    document = ParsedDocument(
        source_sha256=SOURCE,
        source_path="placeholder.docx",
        parser_version=PARSER,
        profile_version=PROFILE,
        cards=(card,),
    )
    entry = SourceEntry.model_validate(
        {
            **fields,
            "source_format": SourceFormat.DOCX,
            "byte_size": 1,
            "outcome": SourceOutcome.PARSED,
            "cards": 1,
        }
    )
    record = DocumentRecord.from_parsed_document(
        document, caselist=CASELIST, snapshot="2026-09-01", fingerprint_version=FINGERPRINT_VERSION, camp=None
    )
    row = OccurrenceRecord.model_validate(
        {
            **fields,
            "last_snapshot": "2026-09-08",
            "disclosure": disclosure_digest(CASELIST, "Maple Grove/QX/invented.docx"),
            "first_element_index": 0,
            "last_element_index": 2,
            "exact_fingerprint": card_fingerprint(card).exact_fingerprint,
            "cluster_id": card_fingerprint(card).exact_fingerprint,
            "membership": ClusterMembership.NEAR_DUPLICATE,
            "completeness": CardCompleteness.FULL,
        }
    )
    asyncio.run(store.write_source(CASELIST, PARSER, entry, record))
    asyncio.run(store.write_aggregates(CASELIST, PARSER, index=(entry,), failures=(), occurrences=(row,)))
    return installation


def invoke(*arguments: str) -> Result:
    return runner.invoke(create_app(), list(arguments))


def envelope_of(result: Result) -> dict[str, Any]:
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected one line of JSON on stdout, got {lines!r}"
    parsed = json.loads(lines[0])
    assert isinstance(parsed, dict)
    return parsed


def keys_in(client: S3Client, bucket: str) -> set[str]:
    return {str(item.get("Key")) for item in client.list_objects_v2(Bucket=bucket).get("Contents", [])}


def built(parsed: Path) -> Path:
    result = invoke("--json", "tub", "index", "build", "--caselist", CASELIST)
    assert result.exit_code == ExitCode.OK, result.stdout
    return Path(envelope_of(result)["data"]["directory"])


def test_tub_index_build_writes_one_directory_under_the_data_directory(parsed: Path) -> None:
    result = invoke("--json", "tub", "index", "build", "--caselist", CASELIST)

    assert result.exit_code == ExitCode.OK, result.stdout
    data = envelope_of(result)["data"]
    manifest = data["manifest"]
    directory = Path(data["directory"])
    assert directory == parsed / "tub-index" / manifest["index_id"]
    assert sorted(path.name for path in directory.iterdir()) == [
        "manifest.json",
        "search-index.sqlite",
        "search-index.sqlite.gz",
    ]
    assert (manifest["counts"]["documents"], manifest["parser_version"]) == (1, PARSER)
    with sqlite3.connect(directory / "search-index.sqlite") as connection:
        assert connection.execute("SELECT tag, event FROM documents").fetchall() == [
            ("Invented growth claim", "LD")
        ]


def test_tub_index_build_says_what_it_left_out_as_no_card_by_store(parsed: Path) -> None:
    """`v1-e39-t12`: the count is in the envelope and the table, since the manifest does not hold it."""
    as_json = invoke("--json", "tub", "index", "build", "--caselist", CASELIST)
    as_table = invoke("tub", "index", "build", "--caselist", CASELIST)

    assert as_json.exit_code == ExitCode.OK, as_json.stdout
    data = envelope_of(as_json)["data"]
    assert data["not_cards_by_store"] == {CASELIST: {"cite_only": 0, "no_cite_few_words": 0}}
    assert "not_cards" not in json.dumps(data["manifest"])
    assert as_table.exit_code == ExitCode.OK, as_table.output
    assert "0 left out as no card (0 cite only, 0 with no cite and under 25 words)" in " ".join(
        as_table.stdout.split()
    )


def test_tub_index_build_refuses_a_caselist_with_no_parsed_store(parsed: Path) -> None:
    result = invoke("--json", "tub", "index", "build", "--caselist", "hspf26")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    error = envelope_of(result)["error"]
    assert error["code"] == "SEARCH_INDEX_STORE_NOT_READY"
    assert error["details"]["caselist"] == "hspf26"


def test_tub_index_publish_writes_the_dev_bucket_pointer_last(parsed: Path, buckets: S3Client) -> None:
    directory = built(parsed)

    result = invoke("--json", "tub", "index", "publish", "--env", "dev", "--index", str(directory))

    assert result.exit_code == ExitCode.OK, result.stdout
    data = envelope_of(result)["data"]
    index_id = data["index_id"]
    assert data["written"] == [
        f"reports/tub/search/{index_id}/search-index.sqlite.gz",
        f"reports/tub/search/{index_id}/manifest.json",
        "reports/tub/search/current.json",
    ]
    assert keys_in(buckets, DEV_BUCKET) == set(data["written"])
    assert keys_in(buckets, PROD_BUCKET) == set()


def test_tub_index_publish_refuses_an_env_that_is_not_debate_env(parsed: Path, buckets: S3Client) -> None:
    directory = built(parsed)

    result = invoke("--json", "tub", "index", "publish", "--env", "prod", "--index", str(directory))

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope_of(result)["error"]["code"] == "ENVIRONMENT_MISMATCH"
    assert keys_in(buckets, DEV_BUCKET) == keys_in(buckets, PROD_BUCKET) == set()


def test_tub_index_publish_to_prod_needs_confirm_prod(
    parsed: Path, buckets: S3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = built(parsed)
    monkeypatch.setenv("DEBATE_ENV", "prod")

    refused = invoke("--json", "tub", "index", "publish", "--env", "prod", "--index", str(directory))
    assert refused.exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope_of(refused)["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert keys_in(buckets, PROD_BUCKET) == set()

    confirmed = invoke(
        "--json", "tub", "index", "publish", "--env", "prod", "--index", str(directory), "--confirm-prod"
    )
    assert confirmed.exit_code == ExitCode.OK, confirmed.stdout
    assert "reports/tub/search/current.json" in keys_in(buckets, PROD_BUCKET)
    assert keys_in(buckets, DEV_BUCKET) == set()


def test_tub_index_publish_refuses_an_index_of_another_parser_version(
    parsed: Path, buckets: S3Client
) -> None:
    directory = built(parsed)
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["parser_version"] = "2026.09.20-docx-1"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    result = invoke("--json", "tub", "index", "publish", "--env", "dev", "--index", str(directory))

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    error = envelope_of(result)["error"]
    assert (error["code"], error["details"]["field"]) == ("SEARCH_INDEX_VERSION_MISMATCH", "parser version")
    assert keys_in(buckets, DEV_BUCKET) == set()


# ------------------------------------------------------------------------------------------------
# `--newest`: the weekly stage's own rule picks the directory (v1-e39-t09, PM amendment, review)
# ------------------------------------------------------------------------------------------------


def built_again_with_a_later_snapshot(parsed: Path) -> Path:
    """A second real index of the same store: its one row seen a week later, so other bytes and another id."""
    store = LocalParsedStore(parsed)
    rows = asyncio.run(store.read_occurrences(CASELIST, PARSER))
    entries = asyncio.run(store.read_index(CASELIST, PARSER))
    assert rows is not None and entries is not None
    later = tuple(row.model_copy(update={"last_snapshot": "2026-09-15"}) for row in rows)
    asyncio.run(store.write_aggregates(CASELIST, PARSER, index=entries, failures=(), occurrences=later))
    return built(parsed)


@pytest.mark.parametrize("the_first_is_newest", [False, True])
def test_tub_index_publish_newest_publishes_the_index_the_weekly_stage_calls_newest(
    parsed: Path, buckets: S3Client, the_first_is_newest: bool
) -> None:
    first = built(parsed)
    second = built_again_with_a_later_snapshot(parsed)
    assert first.name != second.name
    older, newer = (second, first) if the_first_is_newest else (first, second)
    os.utime(older / "manifest.json", ns=(1_000_000_000, 1_000_000_000))
    os.utime(newer / "manifest.json", ns=(2_000_000_000, 2_000_000_000))
    (first.parent / ".building-abandoned").mkdir()

    result = invoke("--json", "tub", "index", "publish", "--env", "dev", "--newest")

    assert result.exit_code == ExitCode.OK, result.stdout
    assert envelope_of(result)["data"]["index_id"] == newer.name
    assert f"reports/tub/search/{newer.name}/manifest.json" in keys_in(buckets, DEV_BUCKET)
    assert f"reports/tub/search/{older.name}/manifest.json" not in keys_in(buckets, DEV_BUCKET)


def test_tub_index_publish_refuses_newest_together_with_index(parsed: Path, buckets: S3Client) -> None:
    directory = built(parsed)

    result = invoke(
        "--json", "tub", "index", "publish", "--env", "dev", "--newest", "--index", str(directory)
    )

    assert result.exit_code == ExitCode.USAGE_ERROR
    assert "--newest" in result.output and "--index" in result.output
    assert keys_in(buckets, DEV_BUCKET) == set()


def test_tub_index_publish_needs_newest_or_index(parsed: Path, buckets: S3Client) -> None:
    result = invoke("--json", "tub", "index", "publish", "--env", "dev")

    assert result.exit_code == ExitCode.USAGE_ERROR
    assert keys_in(buckets, DEV_BUCKET) == set()


def test_tub_index_publish_newest_with_nothing_built_names_the_build(parsed: Path, buckets: S3Client) -> None:
    result = invoke("--json", "tub", "index", "publish", "--env", "dev", "--newest")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    error = envelope_of(result)["error"]
    assert error["code"] == "NO_BUILT_SEARCH_INDEX"
    assert "tub index build" in error["hint"]
    assert keys_in(buckets, DEV_BUCKET) == set()


# ------------------------------------------------------------------------------------------------
# The shrink guard (v1-e39-t14): refused before any upload, and `--allow-shrink` for a real shrink
# ------------------------------------------------------------------------------------------------

REMOVAL_REASON: Final = "RM-2026-99, a synthetic whole-file removal"


def pointer_in(client: S3Client, bucket: str) -> dict[str, Any]:
    body = client.get_object(Bucket=bucket, Key="reports/tub/search/current.json")["Body"].read()
    parsed = json.loads(body)
    assert isinstance(parsed, dict)
    return parsed


def built_after_removing_the_one_source(parsed: Path) -> Path:
    """An index of the same store after a whole-file removal of its one source: 0 documents of hsld26."""
    entry = SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=SOURCE,
        recorded_at=datetime(2026, 10, 22, tzinfo=UTC),
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id="RM-2026-99",
    )
    asyncio.run(RecordedSuppressionList(local_suppression_list_file(parsed)).append([entry]))
    return built(parsed)


def test_tub_index_publish_refuses_an_index_that_drops_a_stores_documents(
    parsed: Path, buckets: S3Client
) -> None:
    first = built(parsed)
    assert invoke("--json", "tub", "index", "publish", "--env", "dev", "--index", str(first)).exit_code == 0
    removed = built_after_removing_the_one_source(parsed)

    result = invoke("--json", "tub", "index", "publish", "--env", "dev", "--index", str(removed))

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    error = envelope_of(result)["error"]
    assert error["code"] == "SEARCH_INDEX_WOULD_SHRINK"
    assert {key: error["details"][key] for key in ("store", "documents", "current_documents")} == {
        "store": CASELIST,
        "documents": 0,
        "current_documents": 1,
    }
    assert error["details"]["current_index_id"] == first.name
    assert f"current.json still names {first.name}" in error["message"]
    assert pointer_in(buckets, DEV_BUCKET)["index_id"] == first.name
    assert f"reports/tub/search/{removed.name}/manifest.json" not in keys_in(buckets, DEV_BUCKET)


def test_tub_index_publish_with_allow_shrink_publishes_and_prints_the_reason(
    parsed: Path, buckets: S3Client
) -> None:
    first = built(parsed)
    assert invoke("--json", "tub", "index", "publish", "--env", "dev", "--index", str(first)).exit_code == 0
    removed = built_after_removing_the_one_source(parsed)

    result = invoke(
        "--json",
        "tub",
        "index",
        "publish",
        "--env",
        "dev",
        "--index",
        str(removed),
        "--allow-shrink",
        REMOVAL_REASON,
    )

    assert result.exit_code == ExitCode.OK, result.output
    data = envelope_of(result)["data"]
    assert data["replaced"] == first.name
    assert data["allowed_shrink"] == {
        "reason": REMOVAL_REASON,
        "stores": [{"store": CASELIST, "documents": 0, "current_documents": 1}],
        "current_unreadable": None,
    }
    assert (
        f"--allow-shrink: hsld26 has 0 documents against 1 in index {first.name}; reason: {REMOVAL_REASON}"
        in (result.stderr)
    )
    assert pointer_in(buckets, DEV_BUCKET)["index_id"] == removed.name
    stored = buckets.get_object(Bucket=DEV_BUCKET, Key=f"reports/tub/search/{removed.name}/manifest.json")
    assert stored["Body"].read() == (removed / "manifest.json").read_bytes(), (
        "the reason is not in the manifest"
    )


def test_tub_index_publish_prints_the_reason_in_its_table_too(parsed: Path, buckets: S3Client) -> None:
    first = built(parsed)
    assert invoke("--json", "tub", "index", "publish", "--env", "dev", "--index", str(first)).exit_code == 0
    removed = built_after_removing_the_one_source(parsed)

    result = invoke(
        "tub", "index", "publish", "--env", "dev", "--index", str(removed), "--allow-shrink", REMOVAL_REASON
    )

    assert result.exit_code == ExitCode.OK, result.output
    assert REMOVAL_REASON in " ".join(result.stdout.split())


@pytest.mark.parametrize("reason", ["", "two\nlines"])
def test_tub_index_publish_refuses_an_allow_shrink_reason_that_is_not_one_line(
    parsed: Path, buckets: S3Client, reason: str
) -> None:
    directory = built(parsed)

    result = invoke(
        "--json",
        "tub",
        "index",
        "publish",
        "--env",
        "dev",
        "--index",
        str(directory),
        "--allow-shrink",
        reason,
    )

    assert result.exit_code == ExitCode.USAGE_ERROR
    assert "--allow-shrink" in result.output
    assert keys_in(buckets, DEV_BUCKET) == set()
