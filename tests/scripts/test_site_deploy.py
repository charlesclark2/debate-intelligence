"""Tests for `scripts/site_deploy.sh`, the operator's publish path for the team website.

The script's whole job is to talk to AWS, so these tests give it a fake world to talk to and
assert on what it said. Every external tool it calls (`git`, `terraform`, `aws`, `pnpm`) is
replaced by a stub on `PATH` that appends its own argv to a log file, and the script runs against
a throwaway repository built in `tmp_path` rather than this checkout: nothing here touches an AWS
account, the network, or the real `site/out/`.

What is worth asserting, and why:

* the prod guard (`v1-e36-t05` ac1). Prod is whatever is on `main` (ADR-0013), so a dirty tree, a
  branch that is not `main`, and a `HEAD` that has drifted from `origin/main` each have to be
  refused before anything is uploaded;
* `--dry-run` making no `aws s3` and no `aws cloudfront` call at all, because that is the only
  reason to trust it as a rehearsal;
* the exact sync and invalidation calls: the bucket comes from Terraform, the cache headers differ
  by path, `--delete` names only this environment's bucket, and the deploy waits for the
  invalidation rather than assuming it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "site_deploy.sh"

DEV_BUCKET = "debate-dev-site-a7508de8"
DEV_DISTRIBUTION = "E2OSZZB3X6M1T0"
DEV_URL = "https://dev.wfbdebate.com/"
PROD_BUCKET = "debate-prod-site-a7508de8"
PROD_DISTRIBUTION = "E391JBUSDYT2GL"
PROD_URL = "https://wfbdebate.com/"

HEAD_SHA = "1111111111111111111111111111111111111111"
INVALIDATION_ID = "I3CDEFGHIJKLMN"


# --------------------------------------------------------------------------------------
# A fake repository, and stubs for every tool the script shells out to.
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class DeployRun:
    """One run of the script: what it printed, and every stubbed command it invoked."""

    returncode: int
    stdout: str
    stderr: str
    calls: list[list[str]]
    export_dir: Path

    @property
    def output(self) -> str:
        return self.stdout + self.stderr

    def calls_to(self, tool: str) -> list[list[str]]:
        return [call[1:] for call in self.calls if call[0] == tool]

    @property
    def aws_calls(self) -> list[list[str]]:
        return self.calls_to("aws")

    def aws_calls_starting(self, *prefix: str) -> list[list[str]]:
        return [call for call in self.aws_calls if tuple(call[: len(prefix)]) == prefix]


STUB_PREAMBLE = """#!/usr/bin/env bash
set -euo pipefail
{
  printf '%s' "$(basename "$0")"
  for argument in "$@"; do printf '\\t%s' "${argument}"; done
  printf '\\n'
} >> "${STUB_CALL_LOG}"
"""


def _write_stub(directory: Path, name: str, body: str, extra: str = "") -> None:
    path = directory / name
    path.write_text(STUB_PREAMBLE + extra + body, encoding="utf-8")
    path.chmod(0o755)


def _terraform_outputs(environment: str) -> str:
    bucket, distribution, url = (
        (DEV_BUCKET, DEV_DISTRIBUTION, DEV_URL)
        if environment == "dev"
        else (PROD_BUCKET, PROD_DISTRIBUTION, PROD_URL)
    )
    return json.dumps(
        {
            "site_bucket_name": {"value": bucket},
            "site_distribution_id": {"value": distribution},
            "site_url": {"value": url},
            "environment": {"value": environment},
        }
    )


@dataclass
class World:
    """The fake checkout the script runs in, plus the knobs each test turns."""

    root: Path
    stub_dir: Path
    call_log: Path

    branch: str = "main"
    porcelain: str = ""
    head_sha: str = HEAD_SHA
    origin_main_sha: str = HEAD_SHA
    fetch_succeeds: bool = True
    build_succeeds: bool = True
    #: Extra shell to run inside a named stub, for the things argv does not show (AWS_PROFILE).
    stub_extra: dict[str, str] = field(default_factory=dict)

    def write_stubs(self) -> None:
        # git: every read the guard makes, answered from files this test controls.
        _write_stub(
            self.stub_dir,
            "git",
            f"""
state="{self.root}/.stub-state"
for argument in "$@"; do
  case "${{argument}}" in
    status) cat "${{state}}/porcelain"; exit 0 ;;
    --abbrev-ref) cat "${{state}}/branch"; exit 0 ;;
    fetch) exit "$(cat "${{state}}/fetch-status")" ;;
    origin/main) cat "${{state}}/origin-main-sha"; exit 0 ;;
    HEAD) cat "${{state}}/head-sha"; exit 0 ;;
  esac
done
exit 0
""",
            extra=self.stub_extra.get("git", ""),
        )

        # terraform: only `output -json` is ever asked for.
        _write_stub(
            self.stub_dir,
            "terraform",
            f"""
environment=dev
for argument in "$@"; do
  case "${{argument}}" in
    *envs/prod) environment=prod ;;
  esac
done
cat "{self.root}/.stub-state/terraform-outputs-${{environment}}.json"
""",
            extra=self.stub_extra.get("terraform", ""),
        )

        # pnpm: stands in for `next build`, writing the handful of files the script looks for.
        _write_stub(
            self.stub_dir,
            "pnpm",
            f"""
if [ "$(cat "{self.root}/.stub-state/build-status")" != "0" ]; then
  echo "stub build: failing on purpose" >&2
  exit 1
fi
export_dir="{self.root}/site/out"
mkdir -p "${{export_dir}}/_next/static/chunks"
echo '<!doctype html><title>home</title>' > "${{export_dir}}/index.html"
echo '<?xml version="1.0"?><urlset/>' > "${{export_dir}}/sitemap.xml"
echo 'chunk' > "${{export_dir}}/_next/static/chunks/main.js"
""",
            extra=self.stub_extra.get("pnpm", ""),
        )

        # aws: the log is the assertion; create-invalidation is the one call with a reply.
        _write_stub(
            self.stub_dir,
            "aws",
            f"""
if [ "${{1:-}}" = "cloudfront" ] && [ "${{2:-}}" = "create-invalidation" ]; then
  echo "{INVALIDATION_ID}"
fi
exit 0
""",
            extra=self.stub_extra.get("aws", ""),
        )

    def write_state(self) -> None:
        state = self.root / ".stub-state"
        state.mkdir(exist_ok=True)
        (state / "branch").write_text(f"{self.branch}\n", encoding="utf-8")
        (state / "porcelain").write_text(self.porcelain, encoding="utf-8")
        (state / "head-sha").write_text(f"{self.head_sha}\n", encoding="utf-8")
        (state / "origin-main-sha").write_text(f"{self.origin_main_sha}\n", encoding="utf-8")
        (state / "fetch-status").write_text("0\n" if self.fetch_succeeds else "1\n", encoding="utf-8")
        (state / "build-status").write_text("0\n" if self.build_succeeds else "1\n", encoding="utf-8")
        for environment in ("dev", "prod"):
            (state / f"terraform-outputs-{environment}.json").write_text(
                _terraform_outputs(environment), encoding="utf-8"
            )

    def deploy(self, *arguments: str) -> DeployRun:
        self.write_stubs()
        self.write_state()
        self.call_log.write_text("", encoding="utf-8")

        environment = dict(os.environ)
        environment["PATH"] = f"{self.stub_dir}:{environment['PATH']}"
        environment["STUB_CALL_LOG"] = str(self.call_log)
        # The script must not inherit a real profile from the operator's shell.
        for variable in ("AWS_PROFILE", "SITE_TERRAFORM_PROFILE", "SITE_PUBLISHER_PROFILE"):
            environment.pop(variable, None)

        completed = subprocess.run(
            [str(self.root / "scripts" / "site_deploy.sh"), *arguments],
            capture_output=True,
            text=True,
            env=environment,
            cwd=self.root,
            timeout=60,
        )
        calls = [
            line.split("\t")
            for line in self.call_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return DeployRun(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            calls=calls,
            export_dir=self.root / "site" / "out",
        )


@pytest.fixture
def world(tmp_path: Path) -> Iterator[World]:
    """A throwaway checkout holding a copy of the script, a site/ directory and the stubs."""
    root = tmp_path / "checkout"
    (root / "scripts").mkdir(parents=True)
    shutil.copy2(DEPLOY_SCRIPT, root / "scripts" / "site_deploy.sh")
    (root / "site" / "node_modules").mkdir(parents=True)
    (root / "infrastructure" / "envs" / "dev").mkdir(parents=True)
    (root / "infrastructure" / "envs" / "prod").mkdir(parents=True)

    stub_dir = tmp_path / "stub-bin"
    stub_dir.mkdir()

    yield World(root=root, stub_dir=stub_dir, call_log=tmp_path / "calls.log")


# --------------------------------------------------------------------------------------
# The prod guard: ADR-0013 says prod is a clean main that equals origin/main.
# --------------------------------------------------------------------------------------


def test_prod_is_refused_from_a_branch_other_than_main(world: World) -> None:
    world.branch = "task/v1-e36-t05-site-deploy"

    run = world.deploy("prod")

    assert run.returncode != 0
    assert "not main" in run.stderr
    assert run.aws_calls == []


def test_prod_is_refused_when_the_tree_is_dirty(world: World) -> None:
    world.porcelain = " M site/content/pages/home.md\n"

    run = world.deploy("prod")

    assert run.returncode != 0
    assert "uncommitted changes" in run.stderr
    assert run.aws_calls == []


def test_prod_is_refused_when_head_has_drifted_from_origin_main(world: World) -> None:
    world.origin_main_sha = "2222222222222222222222222222222222222222"

    run = world.deploy("prod")

    assert run.returncode != 0
    assert "is not origin/main" in run.stderr
    assert run.aws_calls == []


def test_prod_is_refused_when_origin_cannot_be_fetched(world: World) -> None:
    """A stale local main must not pass the comparison just because the network is down."""
    world.fetch_succeeds = False

    run = world.deploy("prod")

    assert run.returncode != 0
    assert "could not fetch origin/main" in run.stderr
    assert run.aws_calls == []


def test_dev_does_not_run_the_prod_guard(world: World) -> None:
    """The preview is for reviewing work in progress; requiring main of it would defeat it."""
    world.branch = "task/v1-e36-t05-site-deploy"
    world.porcelain = " M site/content/pages/home.md\n"

    run = world.deploy("dev")

    assert run.returncode == 0, run.output
    assert run.aws_calls_starting("s3", "sync")


def test_prod_proceeds_from_a_clean_main(world: World) -> None:
    run = world.deploy("prod")

    assert run.returncode == 0, run.output
    assert [call for call in run.aws_calls_starting("s3", "sync") if PROD_BUCKET in " ".join(call)]
    assert run.aws_calls_starting("cloudfront", "create-invalidation")


# --------------------------------------------------------------------------------------
# --dry-run
# --------------------------------------------------------------------------------------


def test_dry_run_makes_no_aws_call_at_all(world: World) -> None:
    run = world.deploy("dev", "--dry-run")

    assert run.returncode == 0, run.output
    assert run.aws_calls == []
    assert "dry run, not running: aws s3 sync" in run.stdout
    assert "dry run, not running: aws cloudfront create-invalidation" in run.stdout


def test_dry_run_still_builds_and_still_runs_the_prod_guard(world: World) -> None:
    """A rehearsal that skipped the build would not tell the operator the build is clean."""
    world.branch = "dev"

    run = world.deploy("prod", "--dry-run")

    assert run.returncode != 0
    assert "not main" in run.stderr

    world.branch = "main"
    ok = world.deploy("prod", "--dry-run")

    assert ok.returncode == 0, ok.output
    assert ok.calls_to("pnpm"), "the dry run should still build"
    assert ok.aws_calls == []


# --------------------------------------------------------------------------------------
# The build, and what it is told about the environment.
# --------------------------------------------------------------------------------------


def test_a_failed_build_uploads_nothing(world: World) -> None:
    world.build_succeeds = False

    run = world.deploy("prod")

    assert run.returncode != 0
    assert "build failed" in run.stderr
    assert run.aws_calls == []


def test_version_json_records_the_commit_and_the_environment(world: World) -> None:
    run = world.deploy("dev")

    assert run.returncode == 0, run.output
    version = json.loads((run.export_dir / "version.json").read_text(encoding="utf-8"))
    assert version["commit"] == HEAD_SHA
    assert version["environment"] == "dev"
    assert version["siteUrl"] == DEV_URL.rstrip("/")
    assert version["builtAt"].endswith("+00:00")


# --------------------------------------------------------------------------------------
# The upload and the invalidation.
# --------------------------------------------------------------------------------------


def test_dev_syncs_the_dev_bucket_with_cache_headers_by_path(world: World) -> None:
    run = world.deploy("dev")

    assert run.returncode == 0, run.output
    syncs = run.aws_calls_starting("s3", "sync")
    assert len(syncs) == 3, syncs

    hashed_assets, everything_else, prune = syncs

    # Pass 1: the hashed chunks, cached for a year, and no --delete, so a page is never served
    # before the chunks it references exist.
    assert hashed_assets[3] == f"s3://{DEV_BUCKET}/_next/static"
    assert "public, max-age=31536000, immutable" in hashed_assets
    assert "--delete" not in hashed_assets

    # Pass 2: everything else, revalidated every time, and --delete so a removed page leaves the
    # bucket in the same deploy.
    assert everything_else[3] == f"s3://{DEV_BUCKET}"
    assert "--delete" in everything_else
    assert "no-cache, must-revalidate" in everything_else
    assert "_next/static/*" in everything_else

    # Pass 3: prune the chunks nothing references any more.
    assert prune[3] == f"s3://{DEV_BUCKET}/_next/static"
    assert "--delete" in prune


def test_the_hashed_assets_go_up_before_the_html(world: World) -> None:
    run = world.deploy("dev")

    syncs = run.aws_calls_starting("s3", "sync")
    assert syncs[0][2].endswith("/site/out/_next/static")
    assert syncs[1][2].endswith("/site/out")


def test_delete_only_ever_names_this_environments_own_bucket(world: World) -> None:
    run = world.deploy("dev")

    for call in run.aws_calls_starting("s3", "sync"):
        if "--delete" in call:
            assert PROD_BUCKET not in " ".join(call)


def test_the_deploy_waits_for_the_invalidation_it_created(world: World) -> None:
    """The publishing policy's 24-hour removal clock is only honest if the wait happens."""
    run = world.deploy("dev")

    created = run.aws_calls_starting("cloudfront", "create-invalidation")
    assert created == [
        [
            "cloudfront",
            "create-invalidation",
            "--distribution-id",
            DEV_DISTRIBUTION,
            "--paths",
            "/*",
            "--query",
            "Invalidation.Id",
            "--output",
            "text",
        ]
    ]

    waited = run.aws_calls_starting("cloudfront", "wait", "invalidation-completed")
    assert waited == [
        [
            "cloudfront",
            "wait",
            "invalidation-completed",
            "--distribution-id",
            DEV_DISTRIBUTION,
            "--id",
            INVALIDATION_ID,
        ]
    ]


def test_the_invalidation_happens_after_the_last_sync(world: World) -> None:
    run = world.deploy("dev")

    order = [" ".join(call) for call in run.aws_calls]
    last_sync = max(index for index, call in enumerate(order) if call.startswith("s3 sync"))
    first_invalidation = min(
        index for index, call in enumerate(order) if call.startswith("cloudfront create-invalidation")
    )
    assert last_sync < first_invalidation


# --------------------------------------------------------------------------------------
# Arguments and profiles.
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("arguments", [(), ("staging",), ("dev", "prod"), ("dev", "--publish-now")])
def test_bad_arguments_are_refused(world: World, arguments: tuple[str, ...]) -> None:
    run = world.deploy(*arguments)

    assert run.returncode != 0
    assert run.aws_calls == []


def test_the_publisher_profile_is_used_for_aws_and_the_maintainer_profile_for_terraform(
    world: World,
) -> None:
    """The publisher cannot read Terraform state, so the two profiles are not interchangeable."""
    marker = world.root / "profiles.log"
    for tool in ("aws", "terraform"):
        world.stub_extra[tool] = f'echo "{tool} AWS_PROFILE=${{AWS_PROFILE:-unset}}" >> "{marker}"\n'

    run = world.deploy("dev")
    assert run.returncode == 0, run.output

    recorded = marker.read_text(encoding="utf-8").splitlines()
    assert "terraform AWS_PROFILE=debate-dev" in recorded
    assert "aws AWS_PROFILE=debate-dev-site" in recorded
    assert "aws AWS_PROFILE=debate-dev" not in recorded


def test_missing_site_dependencies_are_named_rather_than_failing_obscurely(world: World) -> None:
    (world.root / "site" / "node_modules").rmdir()

    run = world.deploy("dev")

    assert run.returncode != 0
    assert "pnpm --dir site install" in run.stderr
