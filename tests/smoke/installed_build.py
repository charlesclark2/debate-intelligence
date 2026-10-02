"""The build of debate-research a smoke check runs, and how it is run (v1-e01-t10).

validate-dev installs the pre-release for a commit and runs tests/smoke against that installed
binary, never against this checkout's code. :func:`resolve_build` decides which binary that is:

* ``DEBATE_SMOKE_BIN`` set (what ``scripts/validate_dev.py`` does): the binary is that file, and
  the build must report the commit in ``DEBATE_SMOKE_EXPECT_SHA``, the tag in
  ``DEBATE_SMOKE_EXPECT_TAG`` and channel ``dev``. The binary and its interpreter must live outside
  this checkout.
* ``DEBATE_SMOKE_BIN`` unset (``uv run pytest tests/smoke`` on a laptop, and the PR ``ci`` check):
  the binary is this workspace's own console script, which reports channel ``local`` and the
  checkout's commit.

:class:`InstalledCli` runs it as a process with a fresh ``HOME``, working directory and data
directory, in an environment built from scratch: no inherited ``DEBATE_*``, AWS or token
variables, the checkout's ``.venv`` taken off ``PATH``, ``DEBATE_ENV=dev`` and
``DEBATE_STORAGE__DATA_DIR`` pointing at the scratch data directory. Offline, it also puts
``network_guard/`` on the process's ``PYTHONPATH`` (see the module there).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

SMOKE_DIRECTORY = Path(__file__).resolve().parent
REPO_ROOT = SMOKE_DIRECTORY.parents[1]
NETWORK_GUARD = SMOKE_DIRECTORY / "network_guard"

SMOKE_BIN = "DEBATE_SMOKE_BIN"
EXPECT_SHA = "DEBATE_SMOKE_EXPECT_SHA"
EXPECT_TAG = "DEBATE_SMOKE_EXPECT_TAG"
NETWORK_LOG = "DEBATE_SMOKE_NETWORK_LOG"

INSTALLED_CHANNEL = "dev"
FULL_SHA = re.compile(r"[0-9a-f]{40}")

#: The only variables a smoke run inherits from pytest's environment.
INHERITED = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TZ", "SYSTEMROOT")

#: Console scripts written by uv start `#!/bin/sh` and re-exec their interpreter on line two.
SHELL_EXEC = re.compile(r"""^'''exec' '(?P<interpreter>[^']+)' "\$0" "\$@"$""")


class SmokeConfigurationError(Exception):
    """The environment does not describe a build this suite can test."""


@dataclass(frozen=True)
class SmokeBuild:
    """The binary under test and what it must report about itself."""

    binary: Path
    interpreter: Path
    installed: bool
    """True for a build validate-dev installed; False for this checkout's console script."""
    commit: str
    tag: str | None
    channel: str


def interpreter_of(binary: Path) -> Path:
    """The Python interpreter a console script runs under, read from the script itself."""
    lines = binary.read_text(encoding="utf-8", errors="replace").splitlines()[:3]
    if lines and lines[0].startswith("#!") and "python" in lines[0]:
        return Path(lines[0][2:].strip().split()[0])
    for line in lines[1:]:
        if match := SHELL_EXEC.match(line):
            return Path(match["interpreter"])
    raise SmokeConfigurationError(f"{binary} is not a Python console script; cannot tell its interpreter")


def resolve_build(environ: Mapping[str, str], *, repo_root: Path = REPO_ROOT) -> SmokeBuild:
    """The build the environment names, refusing one that is really this checkout."""
    named = environ.get(SMOKE_BIN, "").strip()
    if not named:
        binary = Path(sys.executable).parent / "debate-research"
        if not binary.is_file():
            raise SmokeConfigurationError(f"no console script at {binary}; run `uv sync --all-packages`")
        commit = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        return SmokeBuild(binary, interpreter_of(binary), False, commit, None, "local")

    binary = Path(named).expanduser().resolve()
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise SmokeConfigurationError(f"{SMOKE_BIN}={named} is not an executable file")
    interpreter = interpreter_of(binary)
    for label, path in (("binary", binary), ("interpreter", interpreter.resolve())):
        if path.is_relative_to(repo_root.resolve()):
            raise SmokeConfigurationError(
                f"the {label} {path} is inside this checkout; validate-dev tests an installed "
                "pre-release, never the source tree"
            )
    commit = environ.get(EXPECT_SHA, "").strip()
    tag = environ.get(EXPECT_TAG, "").strip()
    if not FULL_SHA.fullmatch(commit):
        raise SmokeConfigurationError(f"{EXPECT_SHA} must be the 40-character commit the build was made from")
    if not tag:
        raise SmokeConfigurationError(f"{EXPECT_TAG} must name the pre-release tag that was installed")
    return SmokeBuild(binary, interpreter, True, commit, tag, INSTALLED_CHANNEL)


@dataclass(frozen=True)
class CliRun:
    """One finished run of the binary."""

    arguments: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        return self.stdout + self.stderr

    def envelope(self) -> dict[str, object]:
        """The one JSON document a `--json` run printed on stdout."""
        lines = [line for line in self.stdout.splitlines() if line.strip()]
        assert len(lines) == 1, f"expected one line of JSON on stdout; got {lines!r}\n{self.stderr}"
        document = json.loads(lines[0])
        assert isinstance(document, dict)
        return document


class NetworkAttempted(AssertionError):
    """A process the smoke suite started tried to reach the network."""


def assert_no_network_attempts(log: Path) -> None:
    """Fail when the network guard logged any refused call, whatever the command did about it."""
    attempts = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    if attempts:
        raise NetworkAttempted(
            f"{len(attempts)} outbound network call(s) refused during an offline smoke check:\n  "
            + "\n  ".join(attempts)
        )


class InstalledCli:
    """The build under test, run as a process in a scratch home with a scratch data directory."""

    def __init__(self, build: SmokeBuild, root: Path, *, network: bool) -> None:
        self.build = build
        self.home = root / "smoke-home"
        self.workdir = root / "smoke-cwd"
        self.data_dir = root / "smoke-data"
        self.network_log = root / "smoke-network.log"
        self.network = network
        self._configured: dict[str, str | None] = {}
        for directory in (self.home, self.workdir):
            directory.mkdir(parents=True, exist_ok=True)

    def configure(self, **overrides: str | None) -> None:
        """Environment overrides for every later run, as a check's installation fixture sets up."""
        self._configured |= overrides

    def environment(self, overrides: Mapping[str, str | None] | None = None) -> dict[str, str]:
        """The process environment of a run; an override of None removes that variable."""
        environment = {name: os.environ[name] for name in INHERITED if name in os.environ}
        environment["PATH"] = os.pathsep.join(
            entry
            for entry in environment.get("PATH", "").split(os.pathsep)
            if entry and not Path(entry).resolve().is_relative_to(REPO_ROOT)
        )
        environment |= {
            "HOME": str(self.home),
            "DEBATE_ENV": "dev",
            "DEBATE_STORAGE__DATA_DIR": str(self.data_dir),
            "NO_COLOR": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHON_KEYRING_BACKEND": "keyring.backends.null.Keyring",
            "AWS_CONFIG_FILE": os.devnull,
            "AWS_SHARED_CREDENTIALS_FILE": os.devnull,
            "AWS_EC2_METADATA_DISABLED": "true",
        }
        if not self.network:
            environment |= {"PYTHONPATH": str(NETWORK_GUARD), NETWORK_LOG: str(self.network_log)}
        for name, value in (self._configured | dict(overrides or {})).items():
            if value is None:
                environment.pop(name, None)
            else:
                environment[name] = value
        return environment

    def run(
        self,
        *arguments: str,
        env: Mapping[str, str | None] | None = None,
        stdin: str | None = None,
        timeout: float = 120,
    ) -> CliRun:
        """`debate-research <arguments>`."""
        return self.run_program([str(self.build.binary), *arguments], env=env, stdin=stdin, timeout=timeout)

    def run_program(
        self,
        command: Sequence[str],
        *,
        env: Mapping[str, str | None] | None = None,
        stdin: str | None = None,
        timeout: float = 120,
    ) -> CliRun:
        """Any program (the build's own interpreter, say) in the same environment as the CLI.

        In a session of its own, so it has no controlling terminal: a prompt (getpass reads
        /dev/tty when there is one) then reads the stdin given here instead of waiting on the
        keyboard of whoever started the run.
        """
        completed = subprocess.run(
            list(command),
            start_new_session=True,
            cwd=self.workdir,
            env=self.environment(env),
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return CliRun(tuple(command[1:]), completed.returncode, completed.stdout, completed.stderr)
