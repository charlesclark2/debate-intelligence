"""Tests for `scripts/caselist_run_deploy.sh` and `ops/caselist_run/check_image.sh` (`v1-e40-t03`).

As for the pilot's deploy script, the script runs against a throwaway checkout in `tmp_path`, and
every tool it calls (`git`, `gh`, `docker`, `aws`) is a stub that records its argv, one file per call.
Nothing here builds an image, reaches a registry, GitHub, an AWS account or the network. `python3`
is the real one: the script edits the task definition's JSON with it.

What is worth asserting, and why:

* the script refuses to run without Docker, and says so, before it does anything else;
* the image is built for linux/arm64, with provenance attestations off, from the release's wheels
  and the Python `requires-python` allows, and checked before anything is pushed (ADR-0020 (1));
* the check refuses an image whose environment names a credential, or whose SQLite is older than
  the pilot's index needs, and then nothing is pushed;
* prod takes a stable release only, from a clean main (ADR-0013);
* a push registers the current run task definition with its image changed and nothing else, by
  digest, refuses one that does not run as the run's roles, and prints the digest for the next
  apply; before apply B it stops after the push and says so;
* `--dry-run` builds and checks and makes no AWS call at all.

The image itself is built and run against stand-ins by validate-dev's image job; these tests are the
script's logic, on every pull request.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "caselist_run_deploy.sh"
CHECK_IMAGE = REPO_ROOT / "ops" / "caselist_run" / "check_image.sh"
DOCKERFILE = REPO_ROOT / "ops" / "caselist_run" / "Dockerfile"
INSTALLER = REPO_ROOT / "scripts" / "install_channel.sh"
PYTHON_DECLARATION = REPO_ROOT / "packages" / "debate_core" / "pyproject.toml"

HEAD_SHA = "1111111111111111111111111111111111111111"
ACCOUNT_ID = "111122223333"
DIGEST = "sha256:" + "cd" * 32
EARLIER_DIGEST = "sha256:" + "ef" * 32
DEV_TAG = "v1.2.0-dev.40"
STABLE_TAG = "v1.2.0"
REPOSITORY = f"{ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/debate-dev-caselist-run"

ORDINARY_UTILITIES = (
    "bash",
    "env",
    "dirname",
    "basename",
    "cat",
    "cp",
    "sed",
    "head",
    "tr",
    "grep",
    "sort",
    "mktemp",
    "rm",
    "mkdir",
    "touch",
)


def declared_python_minor() -> str:
    text = PYTHON_DECLARATION.read_text(encoding="utf-8")
    match = re.search(r'^requires-python\s*=\s*">=(\d+)\.(\d+),\s*<(\d+)\.(\d+)"', text, re.MULTILINE)
    assert match, "packages/debate_core/pyproject.toml's requires-python is not of the >=X.Y,<X.Z form"
    return f"{match.group(1)}.{match.group(2)}"


def run_task_definition(*, task_role: str = "debate-dev-caselist-run") -> dict[str, object]:
    """What `describe-task-definition` returns for the run's current revision, ECS's own fields too."""
    return {
        "taskDefinitionArn": f"arn:aws:ecs:us-east-1:{ACCOUNT_ID}:task-definition/debate-dev-caselist-run:3",
        "family": "debate-dev-caselist-run",
        "revision": 3,
        "status": "ACTIVE",
        "taskRoleArn": f"arn:aws:iam::{ACCOUNT_ID}:role/{task_role}",
        "executionRoleArn": f"arn:aws:iam::{ACCOUNT_ID}:role/debate-dev-caselist-run-execution",
        "networkMode": "awsvpc",
        "requiresCompatibilities": ["FARGATE"],
        "cpu": "8192",
        "memory": "16384",
        "runtimePlatform": {"operatingSystemFamily": "LINUX", "cpuArchitecture": "ARM64"},
        "ephemeralStorage": {"sizeInGiB": 100},
        "registeredAt": "2026-11-01T12:00:00Z",
        "registeredBy": "arn:aws:sts::111122223333:assumed-role/AWSReservedSSO_DebateBreakGlassAdmin_0/x",
        "compatibilities": ["EC2", "FARGATE"],
        "requiresAttributes": [{"name": "ecs.capability.execution-role-awslogs"}],
        "containerDefinitions": [
            {
                "name": "run",
                "image": f"{REPOSITORY}@{EARLIER_DIGEST}",
                "entryPoint": ["timeout", "--signal=TERM", "--kill-after=120s", "6h", "debate-research"],
                "command": ["--json", "caselist", "pull"],
                "environment": [{"name": "DEBATE_ENV", "value": "dev"}],
            }
        ],
    }


@dataclass(frozen=True)
class DeployRun:
    returncode: int
    stdout: str
    stderr: str
    calls: list[list[str]]
    registered: dict[str, object] | None

    @property
    def output(self) -> str:
        return self.stdout + self.stderr

    def calls_to(self, tool: str) -> list[list[str]]:
        return [call[1:] for call in self.calls if call[0] == tool]

    def calls_starting(self, tool: str, *prefix: str) -> list[list[str]]:
        return [call for call in self.calls_to(tool) if tuple(call[: len(prefix)]) == prefix]

    def aws_calls(self, *words: str) -> list[list[str]]:
        return [call for call in self.calls_to("aws") if all(word in call for word in words)]


# Each call is recorded in a file of its own, under the next call number free in STUB_CALL_DIR.
# The script pipes `aws ecr get-login-password` into `docker login`, so two stubs run at once, and
# when both appended to one log, a printf at a time, their words interleaved: under load a record
# read `aws --regiondocker us-east-1 ...` (`v1-e40-t14`). `mkdir` either creates a call number's
# directory or fails because another call has it, so no two calls share one, and a call made after
# another has finished always gets a higher number.
STUB_PREAMBLE = """#!/usr/bin/env bash
set -euo pipefail
shopt -s nullglob
call_number=0
for recorded in "${STUB_CALL_DIR}"/*; do call_number=$((call_number + 1)); done
until mkdir "${STUB_CALL_DIR}/${call_number}" 2> /dev/null; do call_number=$((call_number + 1)); done
{
  printf '%s' "$(basename "$0")"
  for argument in "$@"; do printf '\\t%s' "${argument}"; done
} > "${STUB_CALL_DIR}/${call_number}/argv"
"""


def _write_stub(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(STUB_PREAMBLE + body, encoding="utf-8")
    path.chmod(0o755)


@dataclass
class World:
    root: Path
    stub_dir: Path
    call_dir: Path
    registered_file: Path

    branch: str = "main"
    porcelain: str = ""
    docker_installed: bool = True
    image_environment: list[str] = field(
        default_factory=lambda: ["PATH=/usr/local/bin:/usr/bin", "HOME=/var/lib/debate-research"]
    )
    image_user: str = "10001:10001"
    sqlite_version: str = "3.40.1"
    # Minors no Python has, so that this file names no real one (`test_single_interpreter_source.py`).
    base_python: str = "3.98"
    tool_python: str = "3.98"
    task_definition: dict[str, object] | None = field(default_factory=run_task_definition)
    pushed_before: str | None = None

    def write_stubs(self) -> None:
        state = self.root / ".stub-state"
        state.mkdir(exist_ok=True)
        (state / "branch").write_text(f"{self.branch}\n", encoding="utf-8")
        (state / "porcelain").write_text(self.porcelain, encoding="utf-8")
        (state / "environment").write_text(
            "".join(f"{line}\n" for line in self.image_environment), encoding="utf-8"
        )
        if self.task_definition is not None:
            (state / "task-definition.json").write_text(json.dumps(self.task_definition), encoding="utf-8")
        else:
            (state / "task-definition.json").unlink(missing_ok=True)

        _write_stub(
            self.stub_dir,
            "git",
            f"""
for argument in "$@"; do
  case "${{argument}}" in
    status) cat "{state}/porcelain"; exit 0 ;;
    --abbrev-ref) cat "{state}/branch"; exit 0 ;;
    fetch) exit 0 ;;
    origin/main) echo "{HEAD_SHA}"; exit 0 ;;
    HEAD) echo "{HEAD_SHA}"; exit 0 ;;
  esac
done
exit 0
""",
        )

        _write_stub(
            self.stub_dir,
            "gh",
            """
previous=""
for argument in "$@"; do
  if [ "${previous}" = "--dir" ]; then
    mkdir -p "${argument}"
    echo "00  debate_core-1.2.0-py3-none-any.whl" > "${argument}/SHA256SUMS"
    touch "${argument}/debate_core-1.2.0-py3-none-any.whl" "${argument}/build-info.json"
  fi
  previous="${argument}"
done
exit 0
""",
        )

        if self.docker_installed:
            _write_stub(
                self.stub_dir,
                "docker",
                f"""
arguments="$*"
case "${{1:-}}" in
  login) cat > /dev/null ;;
  info|tag|push) ;;
  buildx) [ "${{2:-}}" = "version" ] && echo "github.com/docker/buildx v0.20.0" ;;
  image)
    case "${{arguments}}" in
      *".Os"*) echo "linux/arm64" ;;
      *"Config.User"*) echo "{self.image_user}" ;;
      *"Config.Entrypoint"*) echo '["debate-research"]' ;;
      *"Config.Env"*) cat "{state}/environment" ;;
      *"RepoDigests"*) image="${{@: -1}}"; echo "${{image%:*}}@{DIGEST}" ;;
    esac
    ;;
  run)
    case "${{arguments}}" in
      *"--version"*) echo '{{"data": {{"version": "1.2.0.dev40", "tag": "{DEV_TAG}", "channel": "dev"}}}}' ;;
      *"fts5"*) echo "{self.sqlite_version}" ;;
      *"/usr/local/bin/python3"*) echo "{self.base_python}" ;;
      *"version_info"*) echo "{self.tool_python}" ;;
    esac
    ;;
esac
exit 0
""",
            )
        else:
            (self.stub_dir / "docker").unlink(missing_ok=True)

        pushed = self.pushed_before or "None"
        _write_stub(
            self.stub_dir,
            "aws",
            f"""
arguments="$*"
case "${{arguments}}" in
  *"sts get-caller-identity"*) echo "{ACCOUNT_ID}" ;;
  *"ecr describe-images"*) echo "{pushed}" ;;
  *"ecr get-login-password"*) echo "stub-registry-password" ;;
  *"ecs describe-task-definition"*)
    if [ ! -f "{state}/task-definition.json" ]; then
      echo "An error occurred (ClientException) when calling the DescribeTaskDefinition operation:" \\
        "Unable to describe task definition." >&2
      exit 254
    fi
    cat "{state}/task-definition.json"
    ;;
  *"ecs register-task-definition"*)
    for argument in "$@"; do
      case "${{argument}}" in file://*) cp "${{argument#file://}}" "{self.registered_file}" ;; esac
    done
    echo "arn:aws:ecs:us-east-1:{ACCOUNT_ID}:task-definition/debate-dev-caselist-run:4"
    ;;
esac
exit 0
""",
        )

    def deploy(self, *arguments: str) -> DeployRun:
        self.write_stubs()
        shutil.rmtree(self.call_dir, ignore_errors=True)
        self.call_dir.mkdir()
        self.registered_file.unlink(missing_ok=True)
        environment = {
            "PATH": f"{self.stub_dir}:{self.root / '.sandbox-bin'}",
            "HOME": str(self.root),
            "TMPDIR": str(self.root / ".tmp"),
            "STUB_CALL_DIR": str(self.call_dir),
        }
        completed = subprocess.run(
            [
                str(self.root / ".sandbox-bin" / "bash"),
                str(self.root / "scripts" / "caselist_run_deploy.sh"),
                *arguments,
            ],
            capture_output=True,
            text=True,
            env=environment,
            cwd=self.root,
            timeout=60,
        )
        calls = [
            (call / "argv").read_text(encoding="utf-8").split("\t")
            for call in sorted(self.call_dir.iterdir(), key=lambda call: int(call.name))
        ]
        registered = (
            json.loads(self.registered_file.read_text(encoding="utf-8"))
            if self.registered_file.exists()
            else None
        )
        return DeployRun(completed.returncode, completed.stdout, completed.stderr, calls, registered)


@pytest.fixture
def world(tmp_path: Path) -> Iterator[World]:
    """A throwaway checkout with copies of the script, the check, the Dockerfile and the installer."""
    root = tmp_path / "checkout"
    for source, relative in (
        (DEPLOY_SCRIPT, "scripts/caselist_run_deploy.sh"),
        (INSTALLER, "scripts/install_channel.sh"),
        (CHECK_IMAGE, "ops/caselist_run/check_image.sh"),
        (DOCKERFILE, "ops/caselist_run/Dockerfile"),
        (PYTHON_DECLARATION, "packages/debate_core/pyproject.toml"),
    ):
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, root / relative)
    (root / ".tmp").mkdir()

    sandbox = root / ".sandbox-bin"
    sandbox.mkdir()
    for utility in (*ORDINARY_UTILITIES, "python3"):
        found = shutil.which(utility)
        assert found, f"{utility} is not on this machine's PATH"
        (sandbox / utility).symlink_to(found)

    stub_dir = tmp_path / "stub-bin"
    stub_dir.mkdir()
    yield World(
        root=root,
        stub_dir=stub_dir,
        call_dir=tmp_path / "calls",
        registered_file=tmp_path / "registered.json",
    )


# --------------------------------------------------------------------------------------
# Before anything is built
# --------------------------------------------------------------------------------------


def test_without_docker_the_script_refuses_and_says_so(world: World) -> None:
    world.docker_installed = False

    run = world.deploy("dev", DEV_TAG)

    assert run.returncode != 0
    assert "Docker is not installed or not on PATH" in run.stderr
    assert run.calls_to("gh") == [] and run.calls_to("aws") == []


def test_prod_refuses_a_dev_pre_release_before_anything_else(world: World) -> None:
    run = world.deploy("prod", DEV_TAG)

    assert run.returncode != 0
    assert "Prod runs a stable release" in run.stderr
    assert run.calls == []


def test_prod_refuses_a_checkout_that_is_not_main(world: World) -> None:
    world.branch = "task/v1-e40-t03-run-image-and-schedule"

    run = world.deploy("prod", STABLE_TAG)

    assert run.returncode != 0
    assert "not main" in run.stderr
    assert run.calls_to("gh") == [] and run.calls_starting("docker", "buildx", "build") == []


def test_a_tag_that_is_not_a_release_is_refused(world: World) -> None:
    run = world.deploy("dev", "v1.2")

    assert run.returncode != 0
    assert "is not a release tag" in run.stderr


def test_print_base_image_names_the_slim_python_of_requires_python_and_calls_nothing(world: World) -> None:
    run = world.deploy("--print-base-image")

    assert run.returncode == 0, run.output
    assert run.stdout.strip() == f"python:{declared_python_minor()}-slim-bookworm linux/arm64"
    assert run.calls == []


# --------------------------------------------------------------------------------------
# The build and its check
# --------------------------------------------------------------------------------------


def test_a_dry_run_builds_the_releases_image_for_arm64_checks_it_and_calls_no_aws(world: World) -> None:
    run = world.deploy("dev", DEV_TAG, "--dry-run")

    assert run.returncode == 0, run.output
    [download] = run.calls_starting("gh", "release", "download")
    assert download[2] == DEV_TAG and "--repo" in download and "SHA256SUMS" in download
    [build] = run.calls_starting("docker", "buildx", "build")
    assert build[build.index("--platform") + 1] == "linux/arm64"
    assert "--provenance=false" in build
    assert f"PYTHON_VERSION={declared_python_minor()}" in build
    assert f"RELEASE_TAG={DEV_TAG}" in build
    assert build[build.index("--file") + 1].endswith("ops/caselist_run/Dockerfile")
    assert build[build.index("--tag") + 1] == f"debate-dev-caselist-run:{DEV_TAG}"
    assert len(run.calls_starting("docker", "run")) == 6, "the check's six offline containers"
    assert all(
        "--network" in call and call[call.index("--network") + 1] == "none"
        for call in run.calls_starting("docker", "run")
    )
    assert "ok: the base image's Python is 3.98, the one debate-research runs on" in run.stdout
    assert "ok: SQLite 3.40.1 with FTS5" in run.stdout
    assert run.calls_to("aws") == []
    assert run.calls_starting("docker", "push") == []
    assert "Dry run complete" in run.stdout


def test_an_image_whose_environment_names_a_credential_is_never_pushed(world: World) -> None:
    world.image_environment = [*world.image_environment, "AWS_SECRET_ACCESS_KEY=AKIA-not-a-real-one"]

    run = world.deploy("dev", DEV_TAG)

    assert run.returncode != 0
    assert "environment names a credential: AWS_SECRET_ACCESS_KEY" in run.stderr
    assert "AKIA-not-a-real-one" not in run.output, "the value is never printed"
    assert run.calls_to("aws") == [] and run.calls_starting("docker", "push") == []


@pytest.mark.parametrize("name", ["DEBATE_PROVIDERS__CASELIST_TOKEN", "TABROOM_PASSWORD", "SOME_SECRET"])
def test_any_token_password_or_secret_in_the_image_environment_is_refused(world: World, name: str) -> None:
    world.image_environment = [*world.image_environment, f"{name}=x"]

    run = world.deploy("dev", DEV_TAG, "--dry-run")

    assert run.returncode != 0
    assert f"names a credential: {name}" in run.stderr


def test_an_image_with_sqlite_older_than_the_pilots_floor_is_refused(world: World) -> None:
    world.sqlite_version = "3.39.4"

    run = world.deploy("dev", DEV_TAG, "--dry-run")

    assert run.returncode != 0
    assert "SQLite is 3.39.4, older than 3.40.0" in run.stderr


def test_a_base_image_digest_of_another_python_than_debate_research_runs_on_is_refused(world: World) -> None:
    """`v1-e40-t06`: the base image is pinned by digest, which outlives a move of requires-python."""
    world.tool_python = "3.97"

    run = world.deploy("dev", DEV_TAG, "--dry-run")

    assert run.returncode != 0
    assert "base image has Python 3.98, and debate-research runs on 3.97" in run.stderr
    assert "--print-base-image" in run.stderr


def test_an_image_that_runs_as_root_is_refused(world: World) -> None:
    world.image_user = ""

    run = world.deploy("dev", DEV_TAG, "--dry-run")

    assert run.returncode != 0
    assert "runs as '', not 10001:10001" in run.stderr


# --------------------------------------------------------------------------------------
# The push and the task definition
# --------------------------------------------------------------------------------------


def test_a_push_registers_the_current_run_definition_with_only_its_image_changed(world: World) -> None:
    run = world.deploy("dev", DEV_TAG)

    assert run.returncode == 0, run.output
    assert run.calls_starting("docker", "push") == [["push", f"{REPOSITORY}:{DEV_TAG}"]]
    expected = run_task_definition()
    for added_by_ecs in (
        "taskDefinitionArn",
        "revision",
        "status",
        "registeredAt",
        "registeredBy",
        "compatibilities",
        "requiresAttributes",
    ):
        expected.pop(added_by_ecs)
    expected["containerDefinitions"][0]["image"] = f"{REPOSITORY}@{DIGEST}"  # type: ignore[index]
    assert run.registered == expected
    assert f'caselist_image_digest = "{DIGEST}"' in run.stdout
    assert "owner.auto.tfvars" in run.stdout


def test_every_aws_call_is_made_as_the_deployer_profile_in_us_east_1(world: World) -> None:
    run = world.deploy("dev", DEV_TAG)

    assert run.returncode == 0, run.output
    assert all(call[:2] == ["--region", "us-east-1"] for call in run.calls_to("aws"))


def test_docker_signs_in_with_the_registry_password_on_stdin_never_as_an_argument(world: World) -> None:
    """The script's one pipeline, so these two calls run at the same time (`v1-e40-t14`)."""
    run = world.deploy("dev", DEV_TAG)

    assert run.returncode == 0, run.output
    assert run.aws_calls("get-login-password") == [["--region", "us-east-1", "ecr", "get-login-password"]]
    assert run.calls_starting("docker", "login") == [
        ["login", "--username", "AWS", "--password-stdin", f"{ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com"]
    ]
    assert not [call for call in run.calls if "stub-registry-password" in call]


def test_before_apply_b_the_script_stops_after_the_push_and_says_which_apply_is_next(world: World) -> None:
    world.task_definition = None

    run = world.deploy("dev", DEV_TAG)

    assert run.returncode == 0, run.output
    assert run.calls_starting("docker", "push") != []
    assert run.registered is None
    assert run.aws_calls("register-task-definition") == []
    assert "before the environment's apply B" in run.stdout
    assert f'caselist_image_digest = "{DIGEST}"' in run.stdout


def test_a_tag_already_in_the_repository_is_not_pushed_again_and_its_digest_is_used(world: World) -> None:
    world.pushed_before = EARLIER_DIGEST

    run = world.deploy("dev", DEV_TAG)

    assert run.returncode == 0, run.output
    assert run.calls_starting("docker", "push") == []
    assert "tags are immutable" in run.stdout
    assert run.registered is not None
    assert run.registered["containerDefinitions"][0]["image"] == f"{REPOSITORY}@{EARLIER_DIGEST}"  # type: ignore[index]


def test_a_definition_that_runs_as_the_login_role_is_never_copied(world: World) -> None:
    world.task_definition = run_task_definition(task_role="debate-dev-caselist-login")

    run = world.deploy("dev", DEV_TAG)

    assert run.returncode != 0
    assert "its task role is not the run role" in run.stderr
    assert run.aws_calls("register-task-definition") == []


# --------------------------------------------------------------------------------------
# The Dockerfile, read as text
# --------------------------------------------------------------------------------------


def final_stage(dockerfile: str) -> str:
    return dockerfile[dockerfile.rindex("\nFROM ") :]


def test_the_image_installs_the_release_with_install_channel_on_the_slim_python_of_requires_python() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert re.findall(
        r"^FROM python:\$\{PYTHON_VERSION\}-slim-bookworm@sha256:[0-9a-f]{64} AS (\w+)$",
        dockerfile,
        re.MULTILINE,
    ) == ["install", "run"]
    assert 'sh /build/install_channel.sh --no-path-warning --dir /build/assets "${RELEASE_TAG}"' in dockerfile
    assert "ARG PYTHON_VERSION\n" in dockerfile, "no default: the version comes from requires-python"


PYTHON_INDEX_DIGEST = "sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70"
UV_INDEX_DIGEST = "sha256:240fb85ab0f263ef12f492d8476aa3a2e4e1e333f7d67fbdd923d00a506a516a"
"""The two index digests the registries gave for the base images' tags on 2026-10-26 (`v1-e40-t06`),
written here by hand from the operator's output, not read back from the Dockerfile."""


def test_both_base_images_are_pinned_by_the_digests_the_registries_gave() -> None:
    """A tag can be moved upstream; a digest cannot. Both stages build on one python image."""
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    froms = re.findall(r"^FROM (\S+)", dockerfile, re.MULTILINE)

    assert froms == [
        f"ghcr.io/astral-sh/uv:0.11.7@{UV_INDEX_DIGEST}",
        f"python:${{PYTHON_VERSION}}-slim-bookworm@{PYTHON_INDEX_DIGEST}",
        f"python:${{PYTHON_VERSION}}-slim-bookworm@{PYTHON_INDEX_DIGEST}",
    ]
    assert "https://hub.docker.com/_/python/tags" in dockerfile
    assert "https://github.com/astral-sh/uv/pkgs/container/uv" in dockerfile


def test_the_run_stage_puts_debate_research_on_path_and_runs_it_as_an_unprivileged_user() -> None:
    stage = final_stage(DOCKERFILE.read_text(encoding="utf-8"))

    assert "ln -s /opt/debate-research/bin/debate-research /usr/local/bin/debate-research" in stage
    assert "\nUSER 10001:10001\n" in stage
    assert stage.rstrip().endswith('ENTRYPOINT ["debate-research"]')


def test_no_build_argument_or_environment_variable_of_the_image_names_a_credential() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    declared = re.findall(r"^(?:ARG|ENV)\s+(.+?)$", dockerfile, re.MULTILINE)
    names = [part.split("=")[0] for line in declared for part in line.split() if part != "\\"]

    assert names, "the Dockerfile declares its build arguments and environment"
    assert not [name for name in names if re.search(r"TOKEN|PASSWORD|SECRET|CREDENTIAL|AWS_", name)]
