"""Tests for `scripts/tub_deploy.sh`, the operator's deploy path for the student search pilot.

As for the website's deploy script, the script runs against a throwaway checkout in `tmp_path`,
and every tool it calls (`git`, `docker`, `uv`, `aws`, `curl`) is a stub that appends its argv to a
log. Nothing here builds an image, reaches a registry, an AWS account or the network.

`PATH` is a sandbox: the stubs, plus links to the handful of ordinary utilities the script uses.
So a test can take Docker away and see what the operator would see, on a machine where Docker is
installed.

What is worth asserting, and why:

* the script refuses to run without Docker, and says so, before it does anything else (PM notes);
* the image is built for linux/arm64 with provenance attestations off, from the Python that
  `requires-python` allows and no other (ADR-0019 (a) 1, (f) 3);
* the function is pointed at the pushed image by digest, never by tag, then waited for, then
  checked through CloudFront at the origin the function's configuration names;
* an environment's first deploy, before the function exists, pushes and stops with the next step;
* `--dry-run` builds and makes no AWS call at all; the prod guard runs before anything is built.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "tub_deploy.sh"
DOCKERFILE = REPO_ROOT / "packages" / "debate_api" / "Dockerfile"
PYTHON_DECLARATION = REPO_ROOT / "packages" / "debate_core" / "pyproject.toml"
PILOT_MODULE_MAIN = REPO_ROOT / "infrastructure" / "modules" / "evidence_search" / "main.tf"

HEAD_SHA = "1111111111111111111111111111111111111111"
ACCOUNT_ID = "111122223333"
DIGEST = "sha256:" + "ab" * 32
DEV_ORIGIN = "https://tub.dev.wfbdebate.com"

# The utilities the script and the stubs use besides the stubbed tools, linked into the sandbox PATH.
ORDINARY_UTILITIES = (
    "bash",
    "env",
    "dirname",
    "basename",
    "cat",
    "sed",
    "head",
    "tr",
    "grep",
    "mktemp",
    "rm",
    "mkdir",
    "touch",
    "date",
)


def declared_python_minor() -> str:
    """The one Python `requires-python` allows, read the way a person would read the declaration."""
    text = PYTHON_DECLARATION.read_text(encoding="utf-8")
    match = re.search(r'^requires-python\s*=\s*">=(\d+)\.(\d+),\s*<(\d+)\.(\d+)"', text, re.MULTILINE)
    assert match, "packages/debate_core/pyproject.toml's requires-python is not of the >=X.Y,<X.Z form"
    return f"{match.group(1)}.{match.group(2)}"


@dataclass(frozen=True)
class DeployRun:
    returncode: int
    stdout: str
    stderr: str
    calls: list[list[str]]

    @property
    def output(self) -> str:
        return self.stdout + self.stderr

    def calls_to(self, tool: str) -> list[list[str]]:
        return [call[1:] for call in self.calls if call[0] == tool]

    def calls_starting(self, tool: str, *prefix: str) -> list[list[str]]:
        return [call for call in self.calls_to(tool) if tuple(call[: len(prefix)]) == prefix]


STUB_PREAMBLE = """#!/usr/bin/env bash
set -euo pipefail
{
  printf '%s' "$(basename "$0")"
  for argument in "$@"; do printf '\\t%s' "${argument}"; done
  printf '\\n'
} >> "${STUB_CALL_LOG}"
"""


def _write_stub(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(STUB_PREAMBLE + body, encoding="utf-8")
    path.chmod(0o755)


@dataclass
class World:
    root: Path
    stub_dir: Path
    call_log: Path
    profile_log: Path

    branch: str = "main"
    porcelain: str = ""
    docker_installed: bool = True
    docker_daemon_running: bool = True
    function_exists: bool = True
    health_reply: str = '{"status":"ok"}'
    requires_python: str | None = None
    environment_overrides: dict[str, str] = field(default_factory=dict)

    def write_stubs(self) -> None:
        state = self.root / ".stub-state"

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

        if self.docker_installed:
            _write_stub(
                self.stub_dir,
                "docker",
                f"""
case "${{1:-}}" in
  login)
    # The real `docker login --password-stdin` reads the password the script pipes in. A stub
    # that exits without reading it races the `aws ecr get-login-password` writing it: if this
    # exits first, the writer gets SIGPIPE and `pipefail` fails the sign-in. CI hit that once.
    cat > /dev/null
    ;;
  info)
    [ "$(cat "{state}/daemon")" = "running" ] && exit 0
    echo "Cannot connect to the Docker daemon" >&2
    exit 1
    ;;
  image)
    image="${{@: -1}}"
    echo "${{image%:*}}@{DIGEST}"
    ;;
esac
exit 0
""",
            )
        else:
            (self.stub_dir / "docker").unlink(missing_ok=True)

        _write_stub(
            self.stub_dir,
            "uv",
            """
previous=""
for argument in "$@"; do
  case "${previous}" in
    --output-file) echo "fastapi==0.0.0 --hash=sha256:00" > "${argument}" ;;
    --out-dir) mkdir -p "${argument}" && touch "${argument}/stub-0.0.0-py3-none-any.whl" ;;
  esac
  previous="${argument}"
done
exit 0
""",
        )

        _write_stub(
            self.stub_dir,
            "aws",
            f"""
echo "${{AWS_PROFILE:-}}" >> "{self.profile_log}"
arguments="$*"
case "${{arguments}}" in
  *"sts get-caller-identity"*) echo "{ACCOUNT_ID}" ;;
  *"ecr get-login-password"*) echo "stub-registry-password" ;;
  *"get-function-configuration"*"--query FunctionName"*)
    if [ "$(cat "{state}/function")" != "exists" ]; then
      echo "An error occurred (ResourceNotFoundException) when calling" \
        "the GetFunctionConfiguration operation: Function not found" >&2
      exit 254
    fi
    echo "debate-dev-tub"
    ;;
  *"get-function-configuration"*"TUB_PUBLIC_ORIGIN"*) echo "{DEV_ORIGIN}" ;;
  *"update-function-code"*) echo "InProgress" ;;
esac
exit 0
""",
        )

        _write_stub(self.stub_dir, "curl", f'cat "{state}/health"\n')

    def write_state(self) -> None:
        state = self.root / ".stub-state"
        state.mkdir(exist_ok=True)
        (state / "branch").write_text(f"{self.branch}\n", encoding="utf-8")
        (state / "porcelain").write_text(self.porcelain, encoding="utf-8")
        (state / "daemon").write_text(
            "running" if self.docker_daemon_running else "stopped", encoding="utf-8"
        )
        (state / "function").write_text("exists" if self.function_exists else "missing", encoding="utf-8")
        (state / "health").write_text(self.health_reply, encoding="utf-8")
        if self.requires_python is not None:
            declaration = self.root / "packages" / "debate_core" / "pyproject.toml"
            declaration.write_text(
                re.sub(
                    r"^requires-python\s*=.*$",
                    f'requires-python = "{self.requires_python}"',
                    PYTHON_DECLARATION.read_text(encoding="utf-8"),
                    flags=re.MULTILINE,
                ),
                encoding="utf-8",
            )

    def deploy(self, *arguments: str) -> DeployRun:
        self.write_stubs()
        self.write_state()
        self.call_log.write_text("", encoding="utf-8")
        self.profile_log.write_text("", encoding="utf-8")

        environment = {
            "PATH": f"{self.stub_dir}:{self.root / '.sandbox-bin'}",
            "HOME": str(self.root),
            "TMPDIR": str(self.root / ".tmp"),
            "STUB_CALL_LOG": str(self.call_log),
            **self.environment_overrides,
        }
        completed = subprocess.run(
            [
                str(self.root / ".sandbox-bin" / "bash"),
                str(self.root / "scripts" / "tub_deploy.sh"),
                *arguments,
            ],
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
        return DeployRun(completed.returncode, completed.stdout, completed.stderr, calls)

    @property
    def profiles_used(self) -> set[str]:
        return {line for line in self.profile_log.read_text(encoding="utf-8").splitlines() if line}


@pytest.fixture
def world(tmp_path: Path) -> Iterator[World]:
    """A throwaway checkout with a copy of the script, the declaration and the Dockerfile."""
    root = tmp_path / "checkout"
    (root / "scripts").mkdir(parents=True)
    shutil.copy2(DEPLOY_SCRIPT, root / "scripts" / "tub_deploy.sh")
    (root / "packages" / "debate_core").mkdir(parents=True)
    shutil.copy2(PYTHON_DECLARATION, root / "packages" / "debate_core" / "pyproject.toml")
    (root / "packages" / "debate_api").mkdir(parents=True)
    shutil.copy2(DOCKERFILE, root / "packages" / "debate_api" / "Dockerfile")
    (root / ".tmp").mkdir()

    sandbox = root / ".sandbox-bin"
    sandbox.mkdir()
    for utility in ORDINARY_UTILITIES:
        found = shutil.which(utility)
        assert found, f"{utility} is not on this machine's PATH"
        (sandbox / utility).symlink_to(found)

    stub_dir = tmp_path / "stub-bin"
    stub_dir.mkdir()

    yield World(
        root=root, stub_dir=stub_dir, call_log=tmp_path / "calls.log", profile_log=tmp_path / "profiles.log"
    )


# --------------------------------------------------------------------------------------
# Docker, before anything else.
# --------------------------------------------------------------------------------------


def test_without_docker_the_script_refuses_and_says_so(world: World) -> None:
    world.docker_installed = False

    run = world.deploy("dev")

    assert run.returncode != 0
    assert "Docker is not installed or not on PATH" in run.stderr
    assert "Nothing has been built or pushed" in run.stderr
    assert run.calls_to("uv") == []
    assert run.calls_to("aws") == []


def test_with_docker_stopped_the_script_refuses_and_says_so(world: World) -> None:
    world.docker_daemon_running = False

    run = world.deploy("dev")

    assert run.returncode != 0
    assert "daemon is not answering" in run.stderr
    assert run.calls_starting("docker", "buildx", "build") == []
    assert run.calls_to("aws") == []


def test_without_an_environment_the_script_prints_its_usage(world: World) -> None:
    run = world.deploy()

    assert run.returncode != 0
    assert "Usage: scripts/tub_deploy.sh <dev|prod>" in run.stderr


# --------------------------------------------------------------------------------------
# The image.
# --------------------------------------------------------------------------------------


def test_the_image_is_built_for_arm64_without_provenance_from_the_declared_python(world: World) -> None:
    run = world.deploy("dev", "--dry-run")

    assert run.returncode == 0, run.output
    [build] = run.calls_starting("docker", "buildx", "build")
    assert build[build.index("--platform") + 1] == "linux/arm64"
    assert "--provenance=false" in build
    assert build[build.index("--build-arg") + 1] == f"PYTHON_VERSION={declared_python_minor()}"
    assert build[build.index("--file") + 1].endswith("packages/debate_api/Dockerfile")


def test_a_declaration_allowing_two_pythons_is_refused(world: World) -> None:
    """The base image's tag cannot be a guess: one minor, or the script stops."""
    major, minor = declared_python_minor().split(".")
    world.requires_python = f">={major}.{minor},<{major}.{int(minor) + 2}"

    run = world.deploy("dev", "--dry-run")

    assert run.returncode != 0
    assert "allows more than one Python minor" in run.stderr
    assert run.calls_starting("docker", "buildx", "build") == []


def test_print_base_image_names_the_image_and_platform_and_calls_nothing(world: World) -> None:
    """validate-dev's slow job pulls what this prints, on a runner (v1-e01-t34)."""
    world.docker_installed = False

    run = world.deploy("--print-base-image")

    assert run.returncode == 0, run.output
    assert run.stdout == f"public.ecr.aws/lambda/python:{declared_python_minor()} linux/arm64\n"
    assert run.calls == []


def test_print_base_image_refuses_a_declaration_allowing_two_pythons(world: World) -> None:
    major, minor = declared_python_minor().split(".")
    world.requires_python = f">={major}.{minor},<{major}.{int(minor) + 2}"

    run = world.deploy("--print-base-image")

    assert run.returncode != 0
    assert run.stdout == ""
    assert "allows more than one Python minor" in run.stderr


def test_the_printed_base_image_is_the_one_the_dockerfile_builds_from(world: World) -> None:
    printed, platform = world.deploy("--print-base-image").stdout.split()
    [base] = [
        line.removeprefix("FROM ")
        for line in DOCKERFILE.read_text(encoding="utf-8").splitlines()
        if line.startswith("FROM ") and " AS " not in line
    ]

    assert base == "public.ecr.aws/lambda/python:${PYTHON_VERSION}"
    assert printed == base.replace("${PYTHON_VERSION}", declared_python_minor())
    assert platform == "linux/arm64"


def test_the_build_context_is_the_staged_lock_export_and_wheels(world: World) -> None:
    run = world.deploy("dev", "--dry-run")

    assert run.returncode == 0, run.output
    [export] = run.calls_starting("uv", "export")
    assert {"--package", "debate-api", "--frozen", "--no-dev", "--no-emit-workspace"} <= set(export)
    built = {call[call.index("--package") + 1] for call in run.calls_starting("uv", "build")}
    assert built == {"debate-core", "debate-api"}
    [build] = run.calls_starting("docker", "buildx", "build")
    assert build[-1] != str(world.root), "the build context must be the staging directory, not the checkout"


def test_dry_run_builds_and_makes_no_aws_call(world: World) -> None:
    run = world.deploy("dev", "--dry-run")

    assert run.returncode == 0, run.output
    assert run.calls_starting("docker", "buildx", "build")
    assert run.calls_to("aws") == []
    assert run.calls_starting("docker", "push") == []
    assert run.calls_to("curl") == []
    assert "nothing was pushed and no AWS call was made" in run.stdout


# --------------------------------------------------------------------------------------
# Push, update by digest, wait, and check through CloudFront.
# --------------------------------------------------------------------------------------


def test_a_deploy_points_the_function_at_the_pushed_digest(world: World) -> None:
    run = world.deploy("dev")

    assert run.returncode == 0, run.output
    repository = f"{ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/debate-dev-tub"
    assert run.calls_starting("docker", "push") == [["push", f"{repository}:{HEAD_SHA}"]]
    [update] = run.calls_starting("aws", "--region", "us-east-1", "lambda", "update-function-code")
    assert update[update.index("--function-name") + 1] == "debate-dev-tub"
    assert update[update.index("--image-uri") + 1] == f"{repository}@{DIGEST}"


def test_a_deploy_waits_for_the_update_then_checks_healthz_through_cloudfront(world: World) -> None:
    run = world.deploy("dev")

    assert run.returncode == 0, run.output
    order = [" ".join(call) for call in run.calls if call[0] in {"aws", "curl"}]
    update = next(i for i, call in enumerate(order) if "update-function-code" in call)
    wait = next(i for i, call in enumerate(order) if "wait function-updated" in call)
    health = next(i for i, call in enumerate(order) if call.startswith("curl"))
    assert update < wait < health
    [curl] = run.calls_to("curl")
    assert curl[-1] == f"{DEV_ORIGIN}/healthz"


def test_a_deploy_runs_as_the_environments_deployer_profile(world: World) -> None:
    run = world.deploy("dev")

    assert run.returncode == 0, run.output
    assert world.profiles_used == {"debate-dev-tub-deployer"}


def test_the_profile_can_be_overridden_for_the_first_deploy(world: World) -> None:
    world.environment_overrides = {"TUB_DEPLOY_PROFILE": "debate-admin"}

    run = world.deploy("dev")

    assert run.returncode == 0, run.output
    assert world.profiles_used == {"debate-admin"}


def test_the_first_deploy_pushes_and_stops_before_a_function_exists(world: World) -> None:
    world.function_exists = False

    run = world.deploy("dev")

    assert run.returncode == 0, run.output
    assert run.calls_starting("docker", "push")
    assert run.calls_starting("aws", "--region", "us-east-1", "lambda", "update-function-code") == []
    assert run.calls_to("curl") == []
    assert "does not exist yet" in run.stdout
    assert "run the full apply now" in run.stdout


def test_an_unhealthy_answer_through_cloudfront_fails_the_deploy(world: World) -> None:
    world.health_reply = '{"status":"starting"}'

    run = world.deploy("dev")

    assert run.returncode != 0
    assert "/healthz answered" in run.stderr


# --------------------------------------------------------------------------------------
# The prod guard: ADR-0013 says prod is a clean main that equals origin/main.
# --------------------------------------------------------------------------------------


def test_prod_is_refused_from_a_branch_other_than_main_before_anything_is_built(world: World) -> None:
    world.branch = "task/v1-e39-t04-pilot-infrastructure"

    run = world.deploy("prod", "--dry-run")

    assert run.returncode != 0
    assert "not main" in run.stderr
    assert run.calls_starting("docker", "buildx", "build") == []


def test_prod_is_refused_when_the_tree_is_dirty(world: World) -> None:
    world.porcelain = " M packages/debate_api/src/debate_api/app.py\n"

    run = world.deploy("prod")

    assert run.returncode != 0
    assert "uncommitted changes" in run.stderr
    assert run.calls_to("aws") == []


def test_dev_from_a_dirty_tree_is_tagged_as_uncommitted(world: World) -> None:
    world.branch = "task/v1-e39-t04-pilot-infrastructure"
    world.porcelain = " M packages/debate_api/src/debate_api/app.py\n"

    run = world.deploy("dev")

    assert run.returncode == 0, run.output
    [push] = run.calls_starting("docker", "push")
    assert re.search(rf":{HEAD_SHA}-uncommitted-\d{{8}}T\d{{6}}Z$", push[1])


# --------------------------------------------------------------------------------------
# The Dockerfile and the function's configuration agree.
# --------------------------------------------------------------------------------------


def test_the_web_adapter_is_pinned_by_digest_never_by_tag() -> None:
    adapter_lines = [
        line for line in DOCKERFILE.read_text(encoding="utf-8").splitlines() if "aws-lambda-adapter" in line
    ]
    from_lines = [line for line in adapter_lines if line.startswith("FROM ")]

    assert len(from_lines) == 1
    assert re.search(r"@sha256:[0-9a-f]{64}\s", from_lines[0])


def test_the_base_image_follows_requires_python_and_states_no_version() -> None:
    base_lines = [
        line
        for line in DOCKERFILE.read_text(encoding="utf-8").splitlines()
        if line.startswith("FROM public.ecr.aws/lambda/python")
    ]

    assert base_lines == ["FROM public.ecr.aws/lambda/python:${PYTHON_VERSION}"]


def test_uvicorn_serves_the_app_on_the_adapters_port_with_no_access_log() -> None:
    """Gate item 4: an access log line holds the client's address and the query string."""
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    module = PILOT_MODULE_MAIN.read_text(encoding="utf-8")
    [entrypoint] = [line for line in dockerfile.splitlines() if line.startswith("ENTRYPOINT ")]

    assert '"--no-access-log"' in entrypoint
    assert '"debate_api.app:create_app", "--factory"' in entrypoint
    port = re.search(r'"--port", "(\d+)"', entrypoint)
    assert port
    assert re.search(rf"lambda_web_adapter_port\s*=\s*{port.group(1)}\n", module)
    assert re.search(r'lambda_web_adapter_readiness\s*=\s*"/healthz"', module)


def test_the_script_names_the_resources_adr_0019_names() -> None:
    """The script derives debate-<env>-tub rather than reading state; the module must agree."""
    module = PILOT_MODULE_MAIN.read_text(encoding="utf-8")
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert 'resource_name="debate-${environment}-tub"' in script
    assert re.search(r"function_name\s*=\s*var\.name_prefix\n", module)
    assert re.search(r"repository_name\s*=\s*var\.name_prefix\n", module)
    root_call = (REPO_ROOT / "infrastructure" / "envs" / "dev" / "evidence_search.tf").read_text(
        encoding="utf-8"
    )
    assert 'name_prefix = "${var.name_prefix}-${var.environment}-tub"' in root_call
    assert os.access(DEPLOY_SCRIPT, os.X_OK)
