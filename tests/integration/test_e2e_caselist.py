"""The V1 caselist workflow end to end on a tiny invented weekly archive (`v1-e09-t05` ac4).

`caselist import` → `caselist parse` → `landscape report --model-mode replay` → `files build` →
`store sync --apply`, through the CLI's own entry point, in one data directory, over
`tests/fixtures/caselist/synthetic_archive/` (every school, team code, tournament and word invented;
that builder's docstring is the table every count below is worked out from by hand).

The environment is `dev`, read from a profile directory this test writes, as
`packages/debate_cli/tests/commands/test_store.py` does: its bucket is a moto bucket, its AWS profile
resolves to the credentials `testing`, and `store sync --apply` refuses every environment but dev and
prod. Two things are replaced, and nothing else:

* the evidence bucket is moto, in this process (`mock_aws`), so no request leaves it;
* `caselist parse`'s process pool is the in-process runner, so parsing runs where pytest-socket has
  disabled sockets rather than in spawned workers it cannot see into, and the suite pays no pool
  start-up.

The landscape's model stage replays the one cassette `record_landscape_cassette.py` writes (a request
and an answer written by hand), copied to where the stage reads cassettes. A request that differs finds
no cassette and the run stops with `MissingFixtureError`.

The built file goes under `<data dir>/objects/files/…`, the local side of the bucket's `files/`
prefix, so the sync carries it with the import's manifest and blobs.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import boto3
import docx
import pytest
from moto import mock_aws
from tests.fixtures.caselist.synthetic_archive.build_synthetic_archive import (
    AFFIRMATIVE,
    CARDS,
    CASELIST,
    NEGATIVE,
    SyntheticArchive,
    build_synthetic_archive,
)
from tests.fixtures.caselist.synthetic_archive.record_landscape_cassette import CASSETTES
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from tests.integration.e2e_harness import Cli

from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist.parse_workers import InProcessParseRunner

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.slow

BUCKET: Final = "debate-dev-evidence-e2e-moto"
AWS_PROFILE: Final = "debate-dev-evidence"
SNAPSHOT: Final = "2026-09-15"
FILE_KEY: Final = "files/synth/aff/grid-adv/synth-grid-adv"
"""Where the built file goes, under the local store's `objects/` and so under the bucket."""


@pytest.fixture
def dev(cli_environment: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """`dev`, from a profile directory of this test's own naming a moto bucket; returns the data dir."""
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        "allow_network = false\n"
        "[providers]\nenabled = []\n"
        f'[storage]\ndata_dir = "{cli_environment}"\n'
        f'[storage.s3]\nbucket = "{BUCKET}"\nregion = "us-east-1"\naws_profile = "{AWS_PROFILE}"\n'
        f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 0.0\n'
        '[caselist]\nnotifier = "none"\n',
        encoding="utf-8",
    )
    config = tmp_path / "aws-config"
    config.write_text(f"[profile {AWS_PROFILE}]\nregion = us-east-1\n", encoding="utf-8")
    credentials = tmp_path / "aws-credentials"
    credentials.write_text(
        f"[{AWS_PROFILE}]\naws_access_key_id = testing\naws_secret_access_key = testing\n", encoding="utf-8"
    )
    for name, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_EC2_METADATA_DISABLED": "true",
        "AWS_CONFIG_FILE": str(config),
        "AWS_SHARED_CREDENTIALS_FILE": str(credentials),
        "DEBATE_PROFILE_DIR": str(profiles),
        "DEBATE_ENV": "dev",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setattr("debate_cli.container.ProcessPoolParseRunner", lambda **_: InProcessParseRunner())
    return cli_environment


@pytest.fixture
def bucket() -> Iterator[S3Client]:
    with mock_aws():
        client: S3Client = boto3.client("s3", region_name="us-east-1")  # pyright: ignore[reportUnknownMemberType]
        client.create_bucket(Bucket=BUCKET)
        client.put_bucket_versioning(Bucket=BUCKET, VersioningConfiguration={"Status": "Enabled"})
        yield client


@pytest.fixture
def archive(tmp_path: Path) -> SyntheticArchive:
    return build_synthetic_archive(tmp_path / "corpus")


def sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def data_of(cli: Cli, *arguments: str) -> dict[str, Any]:
    result, envelope = cli.envelope(*arguments)
    assert result.exit_code == ExitCode.OK, result.output
    data: dict[str, Any] = envelope["data"]
    return data


def test_caselist_import_parse_landscape_files_build_and_store_sync_on_a_synthetic_archive(
    cli: Cli, dev: Path, bucket: S3Client, archive: SyntheticArchive, tmp_path: Path
) -> None:
    data_dir = dev
    affirmative, negative = sha256(AFFIRMATIVE), sha256(NEGATIVE)

    imported = data_of(
        cli,
        "caselist",
        "import",
        str(archive.archive),
        "--caselist",
        CASELIST,
        "--snapshot",
        SNAPSHOT,
        "--event",
        "POLICY",
    )

    assert imported["members"] == 3
    assert imported["counts"] == {
        "NEW": 2,
        "UNCHANGED": 0,
        "CHANGED": 0,
        "DUPLICATE": 1,
        "REMOVED": 0,
        "SUPPRESSED": 0,
    }
    assert (imported["distinct_sha256"], imported["newly_stored_blobs"]) == (2, 2)
    manifest = data_dir / "objects" / "manifests" / CASELIST / f"{SNAPSHOT}.jsonl"
    rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
    members = [row for row in rows if row["kind"] == "member"]
    assert sorted((row["sha256"], row["classification"]) for row in members) == sorted(
        [(affirmative, "NEW"), (affirmative, "DUPLICATE"), (negative, "NEW")]
    )

    parsed = data_of(cli, "caselist", "parse", "--caselist", CASELIST)

    assert (parsed["sources"], parsed["parsed"], parsed["cards"], parsed["failed"]) == (2, 2, 4, {})
    assert (parsed["store"]["cards"], parsed["store"]["occurrences"]) == (4, 6)

    shutil.copytree(CASSETTES, data_dir / "landscape" / "model-cassettes")
    report_dir = tmp_path / "landscape-report"
    landscape = data_of(
        cli,
        "landscape",
        "report",
        "--caselist",
        CASELIST,
        "--no-publish",
        "--model-mode",
        "replay",
        "--config-dir",
        str(archive.config_dir),
        "--out",
        str(report_dir),
    )

    assert (landscape["snapshot"], landscape["topic_id"], landscape["model_mode"]) == (
        SNAPSHOT,
        "synth",
        "replay",
    )
    assert landscape["model_calls"] == 1
    assert landscape["classification"]["cards_by_method"] == {"ALIAS": 3, "MODEL": 1}
    lines = (report_dir / "positions.csv").read_text(encoding="utf-8").splitlines()
    assert "# coverage_cards=4/4" in lines
    table = csv.DictReader(line for line in lines if not line.startswith("#"))
    positions = {
        row["position_id"]: (row["rounds"], row["teams"], row["aff_rounds"], row["neg_rounds"])
        for row in table
    }
    assert positions == {"grid-adv": ("1", "1", "1", "0"), "spending-da": ("1", "1", "0", "1")}

    built = data_of(cli, "files", "build", str(archive.recipe), "--out", str(data_dir / "objects" / FILE_KEY))

    assert built["status"] == "BUILT"
    assert (built["counts"]["cards_placed"], built["counts"]["sources_used"]) == (2, 1)
    assert built["quality"]["status"] == "PASS"
    sidecar = json.loads(Path(built["files"]["provenance"]).read_text(encoding="utf-8"))
    assert [
        (entry["fingerprint"], entry["source_sha256"], entry["evidence_sha256"]) for entry in sidecar["cards"]
    ] == [
        (archive.fingerprints[card.number], affirmative, sha256(card.evidence.encode("utf-8")))
        for card in CARDS[:2]
    ]
    body = [
        paragraph.text
        for paragraph in docx.Document(io.BytesIO(Path(built["files"]["docx"]).read_bytes())).paragraphs
    ]
    assert [card.evidence in body for card in CARDS] == [True, True, False, False]

    synced = data_of(cli, "store", "sync", "--blob-prefix", f"raw/caselist/{CASELIST}", "--apply")

    assert synced["bucket"] == BUCKET
    assert (synced["counts"]["new"], synced["transferred"], synced["failed"], synced["mismatched"]) == (
        7,
        7,
        [],
        [],
    )
    local = {
        f"manifests/{CASELIST}/{SNAPSHOT}.jsonl": manifest,
        **{
            f"raw/caselist/{CASELIST}/sha256/{digest[:2]}/{digest[2:4]}/{digest}": data_dir
            / "blobs"
            / "sha256"
            / digest[:2]
            / digest[2:4]
            / digest
            for digest in (affirmative, negative)
        },
        **{f"{FILE_KEY}/{Path(path).name}": Path(path) for path in built["files"].values()},
    }
    stored = {item.get("Key") for item in bucket.list_objects_v2(Bucket=BUCKET).get("Contents", [])}
    assert stored == set(local)
    for key, path in local.items():
        remote = bucket.get_object(Bucket=BUCKET, Key=key)
        body_bytes = remote["Body"].read()
        assert sha256(body_bytes) == sha256(path.read_bytes()) == remote["Metadata"]["sha256"], key

    again = data_of(cli, "store", "sync", "--blob-prefix", f"raw/caselist/{CASELIST}")

    assert (again["counts"]["new"], again["counts"]["changed"], again["counts"]["skipped"]) == (0, 0, 7)
