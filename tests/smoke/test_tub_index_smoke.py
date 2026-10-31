"""`debate-research tub index build`, `publish` and `prune` end to end, against the installed build.

The search pilot's index is rebuilt, published and pruned by hand (`docs/runbooks/caselist-removal.md`,
P3 and P4), so a broken entry point would show up in the middle of a removal. Each check here runs the
commands the way the operator does, as a process, against the S3 stand-in (moto in server mode,
tests/smoke/stand_ins/), in bucket mode with the bucket's run lock, as dev has been since the cutover.

The parsed store is made by the build itself: two structural fixtures (`v1-e31-t03`), filed as two
weekly archives of the synthetic caselist `testcl26`, imported with `caselist import` and parsed with
`caselist parse`. What the index must hold is written by hand from those fixtures' `.expected.json`:

* **Week one**, `cardmirror-camp-file.docx` disclosed by one invented team: two FULL cards with cites
  (the Okonkwo card and the Ferreira card), so two documents of one occurrence each.
* **Week two** adds `wiki-converted-cite-entries.docx` from a second invented team: the Okonkwo card
  cut short (ABBREVIATED), which is the same card and joins its document as a third occurrence, and a
  cite-only entry, which is no card and is left out (`v1-e39-t12`). Still two documents, so the
  publish's shrink guard has nothing to say, but a new index id.

Publishing week one's index and then week two's leaves the bucket what P4 prunes: one superseded index
directory and an older version of `current.json`.

`tub index prune --execute` refuses on a Wednesday in Chicago, the cloud run's day, and the build's
clock is the machine's. Validate-dev runs nightly, so on that day the execute check sees the refusal,
and asserts it and that nothing was deleted, instead of the deletion; it never skips.

**Not marked `live`, and must not be.** The build's network guard allows the stand-in and nothing else.
"""

from __future__ import annotations

import configparser
import gzip
import hashlib
import json
import sqlite3
import zipfile
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import pytest
from tests.fixtures.identity_center_roles import EVERYDAY_ROLE, TAKEDOWN_ROLE, sign_in
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from tests.smoke.installed_build import InstalledCli
from tests.smoke.stand_ins.s3 import MOTO_TEST_CREDENTIALS, S3StandIn

from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist.run_lock import RUN_LOCK_KEY, LockBody, LockState
from debate_core.application.search_index_prune import is_cloud_run_day
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION
from debate_core.integrations.docx_parser import DebateDocxParser

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

STRUCTURAL: Final = Path(__file__).resolve().parents[1] / "fixtures" / "debate_files" / "structural"
CASELIST: Final = "testcl26"
BUCKET: Final = "debate-dev-evidence-smoke-moto"
OPERATOR_PROFILE: Final = "debate-dev-evidence"
REMOVAL_PROFILE: Final = "debate-dev-evidence-removal"
PREFIX: Final = "reports/tub/search/"
POINTER: Final = f"{PREFIX}current.json"
INDEX_FILES: Final = ("manifest.json", "search-index.sqlite", "search-index.sqlite.gz")

WEEKS: Final = (
    (
        "2026-09-01",
        {"Maple Grove/QX/Maple Grove-QX-Aff-Smoke Invitational-Round 1.docx": "cardmirror-camp-file"},
    ),
    (
        "2026-09-08",
        {
            "Maple Grove/QX/Maple Grove-QX-Aff-Smoke Invitational-Round 1.docx": "cardmirror-camp-file",
            "Bayview/ZT/Bayview-ZT-Neg-Smoke Invitational-Round 2.docx": "wiki-converted-cite-entries",
        },
    ),
)
"""Each week's archive: its snapshot, and each disclosed path with the structural fixture filed there."""

Version = tuple[str, str]
"""One version in the bucket: its key and version id."""


def expected_tags(fixture: str) -> list[str]:
    """The tags of a structural fixture's FULL and ABBREVIATED cards, from its hand-written expectations."""
    cards = json.loads((STRUCTURAL / f"{fixture}.expected.json").read_text(encoding="utf-8"))["cards"]
    return [card["tag"] for card in cards if card["completeness"] != "CITE_ONLY"]


@pytest.fixture
def installation(installed_cli: InstalledCli, s3_stand_in: S3StandIn, tmp_path: Path) -> Iterator[Path]:
    """A dev profile naming the stand-in's bucket, in bucket mode, and both SSO profiles in an AWS config."""
    config = tmp_path / "aws-config"
    credentials = tmp_path / "aws-credentials"
    config.write_text(
        "".join(f"[profile {name}]\nregion = us-east-1\n" for name in (OPERATOR_PROFILE, REMOVAL_PROFILE)),
        encoding="utf-8",
    )
    credentials.write_text(
        "".join(
            f"[{name}]\naws_access_key_id = {MOTO_TEST_CREDENTIALS['aws_access_key_id']}\n"
            f"aws_secret_access_key = {MOTO_TEST_CREDENTIALS['aws_secret_access_key']}\n"
            for name in (OPERATOR_PROFILE, REMOVAL_PROFILE)
        ),
        encoding="utf-8",
    )
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{tmp_path / "data"}"\n'
        f'[storage.s3]\nbucket = "{BUCKET}"\nregion = "us-east-1"\naws_profile = "{OPERATOR_PROFILE}"\n'
        f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 1.0\n'
        "[parse]\nworkers = 2\n",
        encoding="utf-8",
    )
    installed_cli.configure(
        DEBATE_PROFILE_DIR=str(profiles),
        DEBATE_STORAGE__DATA_DIR=None,
        DEBATE_CASELIST__RUN_STATE="bucket",
        AWS_CONFIG_FILE=str(config),
        AWS_SHARED_CREDENTIALS_FILE=str(credentials),
    )
    yield tmp_path / "data"


@pytest.fixture
def bucket(installation: Path, s3_stand_in: S3StandIn, tmp_path: Path) -> S3Client:
    """The dev bucket, versioned, its run lock free as the cutover's seed leaves it, each profile its role."""
    client = s3_stand_in.versioned_bucket(BUCKET)
    client.put_object(
        Bucket=BUCKET,
        Key=RUN_LOCK_KEY,
        Body=LockBody(home_environment="dev", state=LockState.FREE).as_bytes(),
    )
    sign_in(
        tmp_path / "aws-credentials",
        {OPERATOR_PROFILE: EVERYDAY_ROLE, REMOVAL_PROFILE: TAKEDOWN_ROLE},
        iam=s3_stand_in.client("iam"),
        sts=s3_stand_in.client("sts"),
    )
    return client


def run(cli: InstalledCli, *arguments: str, env: Mapping[str, str | None] | None = None) -> dict[str, Any]:
    """One command with `--json`: its envelope, with the exit code on it."""
    result = cli.run("--json", *arguments, env=env)
    envelope = result.envelope()
    envelope["exit_code"] = result.exit_code
    return envelope


def ok(envelope: dict[str, Any]) -> dict[str, Any]:
    assert envelope["exit_code"] == ExitCode.OK, envelope
    assert envelope["status"] == "ok", envelope
    data = envelope["data"]
    assert isinstance(data, dict)
    return data


def parse_week(cli: InstalledCli, tmp_path: Path, week: int) -> None:
    """File week `week`'s archive, import it and parse the caselist, all through the build."""
    snapshot, files = WEEKS[week]
    archive = tmp_path / f"{CASELIST}-{snapshot}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as written:
        for path, fixture in files.items():
            written.writestr(
                f"{CASELIST}-{snapshot[5:].replace('-', '')}/{path}",
                (STRUCTURAL / f"{fixture}.docx").read_bytes(),
            )
    ok(run(cli, "caselist", "import", str(archive), "--caselist", CASELIST, "--snapshot", snapshot))
    ok(run(cli, "caselist", "parse", "--caselist", CASELIST))


def build_week(cli: InstalledCli, tmp_path: Path, week: int) -> dict[str, Any]:
    parse_week(cli, tmp_path, week)
    return ok(run(cli, "tub", "index", "build", "--caselist", CASELIST))


def listing(client: S3Client) -> set[Version]:
    """Every version and delete marker under the index prefix."""
    listed = client.list_object_versions(Bucket=BUCKET, Prefix=PREFIX)
    return {
        (str(one.get("Key")), str(one.get("VersionId")))
        for one in [*listed.get("Versions", []), *listed.get("DeleteMarkers", [])]
    }


def current_versions(client: S3Client) -> dict[str, str]:
    """The current version id of each key under the index prefix."""
    listed = client.list_object_versions(Bucket=BUCKET, Prefix=PREFIX).get("Versions", [])
    return {str(one.get("Key")): str(one.get("VersionId")) for one in listed if one.get("IsLatest")}


def body(client: S3Client, key: str) -> bytes:
    return client.get_object(Bucket=BUCKET, Key=key)["Body"].read()


def lock_state(client: S3Client) -> str:
    return json.loads(body(client, RUN_LOCK_KEY))["state"]


def access_key_of(credentials: Path, profile: str) -> str:
    """The access key `sign_in` wrote for `profile`: how the stand-in's record says who signed."""
    signed_in = configparser.ConfigParser()
    signed_in.read(credentials, encoding="utf-8")
    return signed_in[profile]["aws_access_key_id"]


# ------------------------------------------------------------------------------------------------
# tub index build
# ------------------------------------------------------------------------------------------------


def test_tub_index_build_writes_the_parsed_cards_into_one_directory_and_its_json_says_what(
    installed_cli: InstalledCli, installation: Path, tmp_path: Path
) -> None:
    data = build_week(installed_cli, tmp_path, 0)

    assert set(data) == {"directory", "manifest", "not_cards_by_store"}
    manifest = data["manifest"]
    index_id = manifest["index_id"]
    directory = Path(data["directory"])
    assert directory == installation / "tub-index" / index_id
    assert sorted(path.name for path in directory.iterdir()) == list(INDEX_FILES)
    assert json.loads((directory / "manifest.json").read_text(encoding="utf-8")) == manifest
    sqlite_bytes = (directory / "search-index.sqlite").read_bytes()
    assert index_id == hashlib.sha256(sqlite_bytes).hexdigest()[:16]
    assert gzip.decompress((directory / "search-index.sqlite.gz").read_bytes()) == sqlite_bytes
    assert (manifest["parser_version"], manifest["fingerprint_version"]) == (
        DebateDocxParser().parser_version,
        FINGERPRINT_VERSION,
    )
    assert [store["caselist"] for store in manifest["stores"]] == [CASELIST]
    assert manifest["snapshot"] == WEEKS[0][0]
    counts = manifest["counts"]
    assert (counts["documents"], counts["documents_by_store"], counts["occurrences"]) == (2, {CASELIST: 2}, 2)
    assert data["not_cards_by_store"] == {CASELIST: {"cite_only": 0, "no_cite_few_words": 0}}
    with sqlite3.connect(f"file:{directory / 'search-index.sqlite'}?mode=ro", uri=True) as connection:
        tags = sorted(tag for (tag,) in connection.execute("SELECT tag FROM documents"))
    assert tags == sorted(expected_tags("cardmirror-camp-file"))

    second = build_week(installed_cli, tmp_path, 1)

    assert second["manifest"]["index_id"] != index_id
    counts = second["manifest"]["counts"]
    assert (counts["documents"], counts["occurrences"]) == (2, 3)
    assert second["not_cards_by_store"] == {CASELIST: {"cite_only": 1, "no_cite_few_words": 0}}
    assert sorted(path.name for path in (installation / "tub-index").iterdir()) == sorted(
        [index_id, second["manifest"]["index_id"]]
    )


# ------------------------------------------------------------------------------------------------
# tub index publish
# ------------------------------------------------------------------------------------------------


def test_tub_index_publish_writes_the_index_then_current_json_and_newest_replaces_it(
    installed_cli: InstalledCli, bucket: S3Client, s3_stand_in: S3StandIn, tmp_path: Path
) -> None:
    first = build_week(installed_cli, tmp_path, 0)
    first_id = first["manifest"]["index_id"]
    directory = Path(first["directory"])
    mark = len(s3_stand_in.requests())

    published = ok(run(installed_cli, "tub", "index", "publish", "--env", "dev", "--index", str(directory)))

    object_key = f"{PREFIX}{first_id}/search-index.sqlite.gz"
    manifest_key = f"{PREFIX}{first_id}/manifest.json"
    assert set(published) == {"index_id", "written", "pointer", "replaced", "allowed_shrink"}
    assert published["index_id"] == first_id
    assert published["written"] == [object_key, manifest_key, POINTER]
    assert (published["replaced"], published["allowed_shrink"]) == (None, None)
    puts = [
        one.key
        for one in s3_stand_in.requests_since(mark)
        if one.operation == "PutObject" and one.key and one.key.startswith(PREFIX)
    ]
    assert puts == [object_key, manifest_key, POINTER], "the pointer is written last, once"
    assert set(current_versions(bucket)) == {object_key, manifest_key, POINTER}
    assert body(bucket, object_key) == (directory / "search-index.sqlite.gz").read_bytes()
    assert body(bucket, manifest_key) == (directory / "manifest.json").read_bytes()
    pointer = json.loads(body(bucket, POINTER))
    assert pointer == published["pointer"]
    assert (pointer["index_id"], pointer["object_key"], pointer["manifest_key"]) == (
        first_id,
        object_key,
        manifest_key,
    )
    assert pointer["object_sha256"] == hashlib.sha256(body(bucket, object_key)).hexdigest()
    assert lock_state(bucket) == "free", "the publish held the run lock and released it"

    second_id = build_week(installed_cli, tmp_path, 1)["manifest"]["index_id"]
    newest = ok(run(installed_cli, "tub", "index", "publish", "--env", "dev", "--newest"))

    assert (newest["index_id"], newest["replaced"]) == (second_id, first_id)
    assert json.loads(body(bucket, POINTER))["index_id"] == second_id
    assert {key.removeprefix(PREFIX).split("/")[0] for key in current_versions(bucket)} == {
        first_id,
        second_id,
        "current.json",
    }, "a publish deletes nothing: the superseded index stays until P4"


# ------------------------------------------------------------------------------------------------
# tub index prune
# ------------------------------------------------------------------------------------------------


def test_tub_index_prune_dry_run_deletes_nothing_and_execute_deletes_only_the_superseded_versions(
    installed_cli: InstalledCli, bucket: S3Client, s3_stand_in: S3StandIn, tmp_path: Path
) -> None:
    first = build_week(installed_cli, tmp_path, 0)
    ok(run(installed_cli, "tub", "index", "publish", "--env", "dev", "--index", first["directory"]))
    superseded = listing(bucket)
    second = build_week(installed_cli, tmp_path, 1)
    ok(run(installed_cli, "tub", "index", "publish", "--env", "dev", "--index", second["directory"]))
    current_id = second["manifest"]["index_id"]
    current = listing(bucket) - superseded
    assert {key for key, _ in superseded} == {
        f"{PREFIX}{first['manifest']['index_id']}/search-index.sqlite.gz",
        f"{PREFIX}{first['manifest']['index_id']}/manifest.json",
        POINTER,
    }
    assert {key for key, _ in current} == {
        f"{PREFIX}{current_id}/search-index.sqlite.gz",
        f"{PREFIX}{current_id}/manifest.json",
        POINTER,
    }
    takedown = {"DEBATE_REMOVAL_PROFILE": REMOVAL_PROFILE}
    prune = ("tub", "index", "prune", "--env", "dev")

    # The dry run: the plan, and nothing deleted.
    mark = len(s3_stand_in.requests())
    planned = ok(run(installed_cli, *prune, env=takedown))
    assert planned["applied"] is False
    assert (planned["index_id"], planned["keeps"], planned["deleted"]) == (
        current_id,
        f"{PREFIX}{current_id}/",
        None,
    )
    assert {(one["key"], one["version_id"]) for one in planned["delete"]} == superseded
    assert planned["counts"] == {
        "versions": 3,
        "delete_markers": 0,
        "keys": 3,
        "superseded_directories": 1,
        "kept": 3,
    }
    assert listing(bucket) == superseded | current
    assert not [one for one in s3_stand_in.requests_since(mark) if one.operation.startswith("Delete")]
    code = planned["confirmation"]

    # --execute with a code the dry run did not print: refused, nothing deleted.
    started = datetime.now(UTC)
    wrong = run(installed_cli, *prune, "--execute", "--confirm", "0" * len(code), env=takedown)
    assert wrong["exit_code"] == ExitCode.DOMAIN_FAILURE, wrong
    assert wrong["error"]["code"] in {"CONFIRMATION_MISMATCH", "PRUNE_ON_CLOUD_RUN_DAY"}, wrong
    assert listing(bucket) == superseded | current

    # --execute --confirm with the dry run's code: only the superseded versions go.
    mark = len(s3_stand_in.requests())
    executed = run(installed_cli, *prune, "--execute", "--confirm", code, env=takedown)
    finished = datetime.now(UTC)
    on_cloud_run_day = {is_cloud_run_day(started), is_cloud_run_day(finished)}
    if (
        executed["exit_code"] == ExitCode.DOMAIN_FAILURE
        and executed["error"]["code"] == "PRUNE_ON_CLOUD_RUN_DAY"
    ):
        assert True in on_cloud_run_day, f"refused as the cloud run's day on another day: {executed}"
        assert listing(bucket) == superseded | current
        return
    assert False in on_cloud_run_day, "a Wednesday in Chicago, and --execute did not refuse"
    assert wrong["error"]["code"] == "CONFIRMATION_MISMATCH", wrong
    data = ok(executed)
    assert (data["applied"], data["deleted"], data["index_id"]) == (True, 3, current_id)
    assert listing(bucket) == current, "everything but the current index and the current current.json is gone"
    assert json.loads(body(bucket, POINTER))["index_id"] == current_id
    deletes = [one for one in s3_stand_in.requests_since(mark) if one.operation.startswith("Delete")]
    assert deletes, "the stand-in saw no delete"
    assert {one.access_key for one in deletes} == {
        access_key_of(tmp_path / "aws-credentials", REMOVAL_PROFILE)
    }
    assert lock_state(bucket) == "free", "the prune held the run lock and released it"

    again = ok(run(installed_cli, *prune, env=takedown))
    assert (again["index_id"], again["delete"], again["counts"]["kept"]) == (current_id, [], 3)
