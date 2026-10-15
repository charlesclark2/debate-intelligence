"""Camp files identified by their upstream record, and a camp path withdrawn, through the commands.

`v1-e30-t14`, end to end: `caselist pull` writes each camp row's OpenEv id and the digest of its
upstream path; `caselist publish` takes them to prod from the dev data directory; prod's
`caselist remove` dry run, with no delivery record and no manifest of its own, matches a later
upload by them and never says *matched by file name alone*; a camp file's later upload that another
release keeps is withdrawn from its camp path, and the plan's lines name the release and the id,
not the file; and `caselist reimport-openev-metadata` gives rows an older build wrote their
identity, `caselist status` names the rewritten manifest as a manifest mismatch, and a publish
clears it.

Runs in pytest's own process, where respx answers OpenCaselist and moto answers both buckets, so it
cannot run against an installed build: `ci` runs it, and validate-dev's recorded tier deselects it
(README.md). The camp files are the synthetic ones from `tests/fixtures/openev/`, and every
expected value is written out from what each test lists upstream.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import boto3
import httpx
import pytest
import respx
from moto import mock_aws
from tests.fixtures.caselist.build_synthetic_archives import SYNTHETIC_CASELIST
from tests.fixtures.identity_center_roles import EVERYDAY_ROLE, TAKEDOWN_ROLE, sign_in
from tests.fixtures.openev.build_synthetic_openev import DOCUMENT_BODIES
from typer.testing import CliRunner, Result

from debate_cli.app import create_app

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

runner = CliRunner()

# Runs in pytest's own process, where respx answers OpenCaselist and moto answers S3, so it cannot
# run against an installed build: `ci` runs it, and validate-dev's recorded tier deselects it.
pytestmark = pytest.mark.in_process

DEV_BUCKET = "debate-dev-evidence-camp-identity-moto"
PROD_BUCKET = "debate-prod-evidence-camp-identity-moto"
DEV_PROFILE = "debate-dev-evidence"
REMOVAL_PROFILE = "debate-dev-evidence-removal"
PROD_PROFILE = "debate-prod-evidence"
API = "https://api.opencaselist.example.invalid/v1"
RELEASE_KEY = "manifests/openev/2026-policy.jsonl"
NEXT_RELEASE_KEY = "manifests/openev/2027-policy.jsonl"
REMOVE_512 = ("caselist", "remove", "--source")
REQUEST = ("--request", "RM-2026-01", "--reason", "REQUESTED_BY_CAMP")

ESTUARY = DOCUMENT_BODIES["estuary-solvency"]
REVISED = DOCUMENT_BODIES["canal-counterplan-revised"]
OTHER_CAMP = DOCUMENT_BODIES["harbor-tariffs-aff"]
ESTUARY_SHA256 = hashlib.sha256(ESTUARY).hexdigest()
REVISED_SHA256 = hashlib.sha256(REVISED).hexdigest()
OTHER_CAMP_SHA256 = hashlib.sha256(OTHER_CAMP).hexdigest()

TAMARACK_PATH = "/openev/2026/Tamarack/TSF-Estuary Solvency Advocate.docx"
QUILLFEATHER_PATH = "/openev/2026/Quillfeather/TSF-Estuary Solvency Advocate.docx"
JUNIPER_PATH = "/openev/2027/Juniper/JDI-Canal Counterplan.docx"

#: Each row's `(openev_id, upstream_path_sha256)`: the digest of the path `GET /openev` listed.
EXPECTED_IDENTITY = {
    "openev-512-TSF-Estuary_Solvency_Advocate.docx": (
        512,
        hashlib.sha256(TAMARACK_PATH.encode()).hexdigest(),
    ),
    "openev-640-TSF-Estuary_Solvency_Advocate.docx": (
        640,
        hashlib.sha256(TAMARACK_PATH.encode()).hexdigest(),
    ),
    "openev-700-TSF-Estuary_Solvency_Advocate.docx": (
        700,
        hashlib.sha256(QUILLFEATHER_PATH.encode()).hexdigest(),
    ),
}

#: 640's camp path, as the suppression entry and the withdrawal record hold it.
CAMP_PATH_DISCLOSURE = hashlib.sha256(
    b"openev/2026-policy/openev-640-TSF-Estuary_Solvency_Advocate.docx"
).hexdigest()


def listed(openev_id: int, path: str, year: int = 2026) -> dict[str, Any]:
    """One OpenEv file as `GET /openev` lists it."""
    return {
        "openev_id": openev_id,
        "path": path,
        "filename": path.rsplit("/", 1)[-1],
        "year": year,
        "tags": {"policy": True},
    }


@pytest.fixture
def installation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """Dev, which pulls into its own data directory, and prod, with its own, each with its bucket."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    names = (DEV_PROFILE, REMOVAL_PROFILE, PROD_PROFILE)
    config = tmp_path / "aws-config"
    config.write_text("".join(f"[profile {name}]\nregion = us-east-1\n" for name in names), encoding="utf-8")
    credentials = tmp_path / "aws-credentials"
    credentials.write_text(
        "".join(
            f"[{name}]\naws_access_key_id = testing\naws_secret_access_key = testing\n" for name in names
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

    profiles = tmp_path / "profiles"
    profiles.mkdir()
    models = f'[models]\nrouting_file = "{tmp_path / "routing.yaml"}"\nbudget_usd_daily = 1.0\n'
    (profiles / "dev.toml").write_text(
        "allow_network = true\n"
        f'[storage]\ndata_dir = "{tmp_path / "dev"}"\n'
        f'[storage.s3]\nbucket = "{DEV_BUCKET}"\nregion = "us-east-1"\naws_profile = "{DEV_PROFILE}"\n'
        "[caselist]\n"
        "api_enabled = true\n"
        'notifier = "none"\n'
        f'api_base_url = "{API}"\n'
        f'sync_caselists = ["{SYNTHETIC_CASELIST}"]\n'
        "min_request_interval_seconds = 0.5\n"
        "[parse]\nworkers = 1\n" + models,
        encoding="utf-8",
    )
    (profiles / "prod.toml").write_text(
        f'[storage]\ndata_dir = "{tmp_path / "prod"}"\n'
        f'[storage.s3]\nbucket = "{PROD_BUCKET}"\nregion = "us-east-1"\naws_profile = "{PROD_PROFILE}"\n'
        + models,
        encoding="utf-8",
    )
    monkeypatch.setenv("DEBATE_PROFILE_DIR", str(profiles))
    monkeypatch.setenv("DEBATE_ENV", "dev")
    monkeypatch.setenv("DEBATE_PROVIDERS__CASELIST_TOKEN", "fixture-token-not-a-real-one")
    yield tmp_path


@pytest.fixture
def buckets(installation: Path) -> Iterator[S3Client]:
    with mock_aws():
        client: S3Client = boto3.client("s3", region_name="us-east-1")  # pyright: ignore[reportUnknownMemberType]
        for bucket in (DEV_BUCKET, PROD_BUCKET):
            client.create_bucket(Bucket=bucket)
            client.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})
        sign_in(
            installation / "aws-credentials",
            {DEV_PROFILE: EVERYDAY_ROLE, REMOVAL_PROFILE: TAKEDOWN_ROLE, PROD_PROFILE: EVERYDAY_ROLE},
        )
        yield client


@pytest.fixture
def upstream() -> dict[str, tuple[dict[str, Any], bytes]]:
    """What OpenEv lists, by upstream path, and the bytes `/download` serves. A test changes it."""
    return {TAMARACK_PATH: (listed(512, TAMARACK_PATH), ESTUARY)}


@pytest.fixture
def site(upstream: dict[str, tuple[dict[str, Any], bytes]]) -> Iterator[respx.MockRouter]:
    """OpenCaselist listing no caselist archive, and the OpenEv files in `upstream`."""

    def download(request: httpx.Request) -> httpx.Response:
        # The client takes the leading `/` off a listed path before asking for it.
        return httpx.Response(200, content=upstream["/" + request.url.params["path"]][1])

    with respx.mock(assert_all_called=False) as router:
        router.get(f"{API}/caselists/{SYNTHETIC_CASELIST}/downloads").respond(200, json=[])
        router.get(f"{API}/openev").mock(
            side_effect=lambda _: httpx.Response(200, json=[entry for entry, _ in upstream.values()])
        )
        router.get(f"{API}/download").mock(side_effect=download)
        yield router


def run(*arguments: str, env: dict[str, str] | None = None) -> dict[str, Any]:
    """Run one command asking for JSON, and return its envelope with the exit code on it."""
    result: Result = runner.invoke(create_app(), ["--json", *arguments], env=env)
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected one line of JSON on stdout; got {lines!r}"
    envelope = json.loads(lines[0])
    envelope["exit_code"] = result.exit_code
    return envelope  # pyright: ignore[reportUnknownVariableType]


def text_of(*arguments: str, env: dict[str, str] | None = None) -> str:
    result: Result = runner.invoke(create_app(), list(arguments), env=env)
    assert result.exit_code == 0, result.stdout
    return result.stdout


def prod_from(installation: Path) -> dict[str, str]:
    """`DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR=<dev data directory>`: how prod is published."""
    return {"DEBATE_ENV": "prod", "DEBATE_STORAGE__DATA_DIR": str(installation / "dev")}


def rows(client: S3Client, bucket: str, key: str = RELEASE_KEY) -> list[dict[str, Any]]:
    body = client.get_object(Bucket=bucket, Key=key)["Body"].read().decode()
    return [row for row in map(json.loads, body.splitlines()) if row["kind"] == "member"]


def identities(members: list[dict[str, Any]]) -> dict[str, tuple[object, object]]:
    return {row["path"]: (row.get("openev_id"), row.get("upstream_path_sha256")) for row in members}


def pulled_then_uploaded_again(
    upstream: dict[str, tuple[dict[str, Any], bytes]], *also: tuple[str, dict[str, Any], bytes]
) -> None:
    """512 pulled; then deleted upstream and uploaded again at its path as 640, and `also` listed."""
    assert run("caselist", "pull")["exit_code"] == 0
    upstream.clear()
    upstream[TAMARACK_PATH] = (listed(640, TAMARACK_PATH), REVISED)
    for path, entry, body in also:
        upstream[path] = (entry, body)
    assert run("caselist", "pull")["exit_code"] == 0


def test_each_camp_row_carries_its_upstream_identity_in_dev_and_in_prod_published_from_dev(
    installation: Path,
    buckets: S3Client,
    site: respx.MockRouter,
    upstream: dict[str, tuple[dict[str, Any], bytes]],
) -> None:
    pulled_then_uploaded_again(upstream, (QUILLFEATHER_PATH, listed(700, QUILLFEATHER_PATH), OTHER_CAMP))
    local = (installation / "dev" / "objects" / RELEASE_KEY).read_text().splitlines()
    assert identities([row for row in map(json.loads, local) if row["kind"] == "member"]) == EXPECTED_IDENTITY
    assert identities(rows(buckets, DEV_BUCKET)) == EXPECTED_IDENTITY

    published = run(
        "caselist", "publish", "--caselist", "openev", "--snapshot", "2026-policy", "--confirm-prod",
        env=prod_from(installation),
    )  # fmt: skip

    assert published["exit_code"] == 0
    assert identities(rows(buckets, PROD_BUCKET)) == EXPECTED_IDENTITY


def test_the_prod_dry_run_matches_the_later_upload_by_upstream_path_and_never_by_name_alone(
    installation: Path,
    buckets: S3Client,
    site: respx.MockRouter,
    upstream: dict[str, tuple[dict[str, Any], bytes]],
) -> None:
    pulled_then_uploaded_again(upstream, (QUILLFEATHER_PATH, listed(700, QUILLFEATHER_PATH), OTHER_CAMP))
    run("caselist", "publish", "--caselist", "openev", "--snapshot", "2026-policy", "--confirm-prod",
        env=prod_from(installation))  # fmt: skip

    shown = text_of(*REMOVE_512, ESTUARY_SHA256, *REQUEST, env={"DEBATE_ENV": "prod"})

    assert not (installation / "prod" / "caselist-sync-openev-deliveries.json").exists()
    assert (
        f"     later upload of sha256 {ESTUARY_SHA256[:12]} in openev 2026-policy as openev-640 (matched by "
        "upstream path: both ids were uploaded at one upstream path): removed everywhere"
    ) in shown
    assert "file name alone" not in shown
    assert OTHER_CAMP_SHA256 not in shown, "the other camp's file of the same name is not in the plan"


def test_a_camp_path_withdrawn_through_the_command_names_its_release_and_id_and_records_openev(
    installation: Path,
    buckets: S3Client,
    site: respx.MockRouter,
    upstream: dict[str, tuple[dict[str, Any], bytes]],
) -> None:
    """640's bytes are released again in 2027-policy as 800, which keeps them."""
    pulled_then_uploaded_again(upstream, (JUNIPER_PATH, listed(800, JUNIPER_PATH, year=2027), REVISED))

    shown = text_of(*REMOVE_512, ESTUARY_SHA256, *REQUEST)
    plan = run(*REMOVE_512, ESTUARY_SHA256, *REQUEST)["data"]

    added = [
        line
        for line in shown.splitlines()
        if "withdraw openev" in line or "later upload of" in line or '"caselist":"openev"' in line
    ]
    assert "     withdraw openev  2026-policy openev-640" in added
    assert "     record   openev 2026-policy  the camp-file record of the withdrawn copy" in shown
    (record,) = [json.loads(line) for line in added if '"caselist":"openev"' in line]
    assert {key: value for key, value in record.items() if key != "recorded_at"} == {
        "caselist": "openev",
        "disclosure": CAMP_PATH_DISCLOSURE,
        "reason": "REQUESTED_BY_CAMP",
        "request_id": "RM-2026-01",
        "schema_version": 1,
        "sha256": REVISED_SHA256,
    }
    assert not [line for line in added for word in ("Tamarack", "TSF", "Estuary", ".docx") if word in line]
    (withdrawn,) = [source for source in plan["sources"] if source["sha256"] == REVISED_SHA256]
    assert (withdrawn["disposition"], withdrawn["kept_in"]) == ("withdraw", ["openev"])
    assert withdrawn["withdrawn_disclosures"] == [{"caselist": "openev", "disclosure": CAMP_PATH_DISCLOSURE}]

    done = run(
        *REMOVE_512, ESTUARY_SHA256, *REQUEST, "--execute", env={"DEBATE_REMOVAL_PROFILE": REMOVAL_PROFILE}
    )

    assert done["exit_code"] == 0
    assert rows(buckets, DEV_BUCKET) == []
    assert identities(rows(buckets, DEV_BUCKET, NEXT_RELEASE_KEY)) == {
        "openev-800-JDI-Canal_Counterplan.docx": (800, hashlib.sha256(JUNIPER_PATH.encode()).hexdigest())
    }
    assert run("caselist", "pull")["data"]["openev_skipped_as_removed"] == 1


def test_rows_an_older_build_wrote_are_re_derived_status_asks_for_a_publish_and_the_publish_clears_it(
    installation: Path,
    buckets: S3Client,
    site: respx.MockRouter,
    upstream: dict[str, tuple[dict[str, Any], bytes]],
) -> None:
    """The operator's follow-up for prod's rows, in dev's data directory and dev's bucket."""
    pulled_then_uploaded_again(upstream, (QUILLFEATHER_PATH, listed(700, QUILLFEATHER_PATH), OTHER_CAMP))
    manifest = installation / "dev" / "objects" / RELEASE_KEY
    older = [
        json.dumps(
            {
                key: value
                for key, value in json.loads(line).items()
                if key not in ("openev_id", "upstream_path_sha256")
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        for line in manifest.read_text().splitlines()
    ]
    manifest.write_text("".join(f"{line}\n" for line in older))
    buckets.put_object(Bucket=DEV_BUCKET, Key=RELEASE_KEY, Body=manifest.read_bytes())

    rederived = run("caselist", "reimport-openev-metadata", "--year", "2026", "--event", "policy")
    drifted = run("caselist", "status", "--caselist", "openev")
    published = run("caselist", "publish", "--caselist", "openev", "--snapshot", "2026-policy")
    agreed = run("caselist", "status", "--caselist", "openev")

    assert (
        rederived["exit_code"],
        rederived["data"]["identities_added"],
        rederived["data"]["rows_changed"],
    ) == (
        0,
        3,
        0,
    )
    assert identities(rows(buckets, DEV_BUCKET)) == EXPECTED_IDENTITY
    assert (drifted["exit_code"], drifted["error"]["code"]) == (1, "CASELIST_DRIFT")
    assert "openev 2026-policy (manifest mismatch)" in drifted["error"]["message"]
    assert drifted["error"]["hint"] == (
        "A manifest mismatch is this machine's copy rewritten since its last publish, by a camp metadata "
        "re-import or a removal. Run `caselist publish --caselist openev` to upload it."
    )
    assert (published["exit_code"], agreed["exit_code"]) == (0, 0)
