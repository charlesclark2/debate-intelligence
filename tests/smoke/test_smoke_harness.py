"""The smoke harness itself: which binary it runs, and that an offline check stays offline.

`in_process`: these test tests/smoke's own machinery inside pytest's process, so they run in `ci`
and are not part of validate-dev's recorded tier. test_network_guard.py proves the guard against
the build under test.
"""

from __future__ import annotations

import socket
import stat
from pathlib import Path

import pytest
import pytest_socket
from tests.smoke.installed_build import (
    EXPECT_SHA,
    EXPECT_TAG,
    SMOKE_BIN,
    NetworkAttempted,
    SmokeConfigurationError,
    assert_no_network_attempts,
    interpreter_of,
    resolve_build,
)

pytestmark = pytest.mark.in_process

SHA = "0123456789abcdef0123456789abcdef01234567"


def console_script(path: Path, interpreter: str, *, shell_form: bool) -> Path:
    if shell_form:
        text = f"#!/bin/sh\n'''exec' '{interpreter}' \"$0\" \"$@\"\n' '''\nimport sys\n"
    else:
        text = f"#!{interpreter}\nimport sys\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


@pytest.mark.parametrize("shell_form", [True, False], ids=["uv-shell-exec", "plain-shebang"])
def test_the_interpreter_is_read_from_the_console_script(tmp_path: Path, shell_form: bool) -> None:
    script = console_script(
        tmp_path / "bin" / "debate-research", "/opt/tools/debate-cli/bin/python", shell_form=shell_form
    )

    assert interpreter_of(script) == Path("/opt/tools/debate-cli/bin/python")


def test_an_installed_build_is_described_by_the_variables_validate_dev_sets(tmp_path: Path) -> None:
    script = console_script(
        tmp_path / "tools" / "bin" / "debate-research", "/opt/py/bin/python", shell_form=True
    )

    build = resolve_build(
        {SMOKE_BIN: str(script), EXPECT_SHA: SHA, EXPECT_TAG: "v0.1.0-dev.9"}, repo_root=tmp_path / "checkout"
    )

    assert (build.installed, build.commit, build.tag, build.channel) == (True, SHA, "v0.1.0-dev.9", "dev")


@pytest.mark.parametrize("inside", ["binary", "interpreter"])
def test_a_binary_from_the_checkout_is_refused(tmp_path: Path, inside: str) -> None:
    """The forbidden case: validate-dev running the source tree instead of the installed build."""
    checkout = tmp_path / "checkout"
    interpreter = (
        str(checkout / ".venv" / "bin" / "python") if inside == "interpreter" else "/opt/py/bin/python"
    )
    where = checkout / ".venv" / "bin" if inside == "binary" else tmp_path / "tools" / "bin"
    script = console_script(where / "debate-research", interpreter, shell_form=True)

    with pytest.raises(SmokeConfigurationError, match=f"the {inside} .* is inside this checkout"):
        resolve_build(
            {SMOKE_BIN: str(script), EXPECT_SHA: SHA, EXPECT_TAG: "v0.1.0-dev.9"}, repo_root=checkout
        )


@pytest.mark.parametrize(
    ("expected_sha", "expected_tag", "problem"),
    [("", "v0.1.0-dev.9", EXPECT_SHA), ("abc1234", "v0.1.0-dev.9", EXPECT_SHA), (SHA, "", EXPECT_TAG)],
)
def test_an_installed_build_needs_the_commit_and_tag_it_must_report(
    tmp_path: Path, expected_sha: str, expected_tag: str, problem: str
) -> None:
    script = console_script(tmp_path / "tools" / "debate-research", "/opt/py/bin/python", shell_form=True)

    with pytest.raises(SmokeConfigurationError, match=problem):
        resolve_build(
            {SMOKE_BIN: str(script), EXPECT_SHA: expected_sha, EXPECT_TAG: expected_tag},
            repo_root=tmp_path / "checkout",
        )


def test_a_logged_attempt_fails_the_check_even_though_the_command_carried_on(tmp_path: Path) -> None:
    log = tmp_path / "network.log"
    assert_no_network_attempts(log)
    log.write_text("", encoding="utf-8")
    assert_no_network_attempts(log)

    log.write_text('{"pid": 1, "call": "connect", "target": "(\'192.0.2.1\', 443)"}\n', encoding="utf-8")

    with pytest.raises(NetworkAttempted, match="1 outbound network call"):
        assert_no_network_attempts(log)


def test_pytests_own_process_has_no_network_in_an_offline_check() -> None:
    """Holds even under `--force-enable-socket`: the conftest blocks sockets itself."""
    with pytest.raises(pytest_socket.SocketBlockedError):
        socket.create_connection(("192.0.2.1", 9), timeout=1)


def test_no_inherited_debate_or_aws_variable_reaches_the_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.smoke.installed_build import InstalledCli, SmokeBuild

    monkeypatch.setenv("DEBATE_PROVIDERS__CASELIST_TOKEN", "from-the-operators-shell")
    monkeypatch.setenv("AWS_PROFILE", "debate-dev-evidence")
    monkeypatch.setenv("GH_TOKEN", "from-the-runner")
    build = SmokeBuild(Path("/x/debate-research"), Path("/x/python"), True, SHA, "v0.1.0-dev.9", "dev")

    environment = InstalledCli(build, tmp_path, network=False).environment()

    assert set(environment) <= {
        *("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TZ", "SYSTEMROOT"),
        *("HOME", "DEBATE_ENV", "DEBATE_STORAGE__DATA_DIR", "NO_COLOR", "PYTHONNOUSERSITE"),
        *("PYTHON_KEYRING_BACKEND", "AWS_CONFIG_FILE", "AWS_SHARED_CREDENTIALS_FILE"),
        *("AWS_EC2_METADATA_DISABLED", "PYTHONPATH", "DEBATE_SMOKE_NETWORK_LOG"),
    }
    assert environment["DEBATE_ENV"] == "dev"
    assert environment["HOME"] == str(tmp_path / "smoke-home")
