"""`debate-research caselist auth login | status | logout`, run the way an operator runs them.

Through Typer's `CliRunner` against the real application and the real composition root, with
OpenCaselist answered by respx. Nothing here reaches the network (respx, and `--disable-socket`)
or the real keychain: every test pins `caselist.token_backend` to `file` under its own `tmp_path`.

The token, password and username are generated per test (`secrets`), so the assertions that they
never appear in output check strings that exist nowhere but in this process.
"""

from __future__ import annotations

import json
import os
import secrets
import stat
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import respx
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode

API = "https://api.opencaselist.example.invalid/v1"

runner = CliRunner()


@pytest.fixture
def token() -> str:
    return f"fixture-token-{secrets.token_hex(16)}"


@pytest.fixture
def password() -> str:
    return f"fixture-password-{secrets.token_hex(8)}"


@pytest.fixture
def username() -> str:
    return f"fixture-user-{secrets.token_hex(4)}@example.invalid"


@pytest.fixture
def data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """A `test` environment of this test's own, with the API on and the token in a file."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    data = tmp_path / "data"
    for name, value in {
        "DEBATE_ENV": "test",
        "DEBATE_STORAGE__DATA_DIR": str(data),
        "DEBATE_ALLOW_NETWORK": "true",
        "DEBATE_CASELIST__API_ENABLED": "true",
        "DEBATE_CASELIST__API_BASE_URL": API,
        "DEBATE_CASELIST__TOKEN_BACKEND": "file",
    }.items():
        monkeypatch.setenv(name, value)
    yield data


@pytest.fixture
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


def token_file(data_dir: Path) -> Path:
    return data_dir / "secrets" / "caselist_token"


def invoke(*args: str, stdin: str | None = None) -> Result:
    return runner.invoke(create_app(), list(args), input=stdin)


def envelope(result: Result) -> dict[str, Any]:
    """The `--json` envelope: stdout's last line.

    Only a prompted run has anything before it, and that is `CliRunner` echoing the simulated
    keystrokes of visible input onto stdout. A real terminal echoes typed characters to the terminal,
    not to the pipe, and the prompts themselves go to stderr (`err=True`). Hidden input is echoed as
    nothing, which `test_login_sends_the_credentials_once_and_never_prints_them_or_the_token` checks.
    """
    return json.loads(result.stdout.strip().splitlines()[-1])


def everything_printed(result: Result) -> str:
    return result.stdout + result.stderr + repr(result.exception)


def log_in(api: respx.MockRouter, token: str, username: str, password: str) -> Result:
    api.post(f"{API}/login").respond(
        201,
        json={"message": "Successfully logged in", "token": token, "expires": "2026-10-04T00:00:00.000Z"},
        headers={"Set-Cookie": f"caselist_token={token}; Path=/"},
    )
    return invoke("--json", "caselist", "auth", "login", stdin=f"{username}\n{password}\n")


# ------------------------------------------------------------------------------------------------
# login
# ------------------------------------------------------------------------------------------------


def test_login_prompts_and_stores_only_the_token_in_a_0600_file(
    data_dir: Path, api: respx.MockRouter, token: str, username: str, password: str
) -> None:
    result = log_in(api, token, username, password)

    assert result.exit_code == ExitCode.OK, everything_printed(result)
    data = envelope(result)["data"]
    assert data["stored"] is True and data["backend"] == "file"
    path = token_file(data_dir)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["token"] == token
    assert password not in path.read_text(encoding="utf-8")
    assert username not in path.read_text(encoding="utf-8")


def test_login_sends_the_credentials_once_and_never_prints_them_or_the_token(
    data_dir: Path, api: respx.MockRouter, token: str, username: str, password: str
) -> None:
    result = log_in(api, token, username, password)

    sent = json.loads(api.routes[0].calls.last.request.content)
    assert sent == {"username": username, "password": password, "remember": True}
    assert api.routes[0].call_count == 1
    printed = everything_printed(result)
    assert token not in printed
    assert password not in printed


def test_login_is_refused_before_prompting_when_the_api_is_disabled(
    data_dir: Path, api: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_CASELIST__API_ENABLED", "false")
    route = api.route()

    result = invoke("--json", "caselist", "auth", "login", stdin="someone\nsecret\n")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope(result)["error"]["code"] == "CASELIST_API_DISABLED"
    assert "password" not in result.stderr.lower()
    assert route.call_count == 0
    assert not token_file(data_dir).exists()


def test_the_api_is_disabled_unless_the_operator_turns_it_on(
    data_dir: Path, api: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEBATE_CASELIST__API_ENABLED")

    result = invoke("--json", "caselist", "auth", "login", "--username", "someone", stdin="secret\n")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope(result)["error"]["code"] == "CASELIST_API_DISABLED"


def test_a_rejected_login_stores_nothing_and_does_not_echo_the_password(
    data_dir: Path, api: respx.MockRouter, username: str, password: str
) -> None:
    api.post(f"{API}/login").respond(401, json={"message": "Invalid username or password"})

    result = invoke("--json", "caselist", "auth", "login", stdin=f"{username}\n{password}\n")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope(result)["error"]["code"] == "CASELIST_LOGIN_REJECTED"
    assert not token_file(data_dir).exists()
    assert password not in everything_printed(result)
    # The username is visible input, so CliRunner echoes the keystrokes onto stdout (see
    # `envelope`); what the command itself printed is stderr and the envelope.
    assert username not in result.stderr
    assert username not in json.dumps(envelope(result))


def test_login_takes_the_username_as_an_option(
    data_dir: Path, api: respx.MockRouter, token: str, username: str, password: str
) -> None:
    api.post(f"{API}/login").respond(201, json={"token": token})

    result = invoke("caselist", "auth", "login", "--username", username, stdin=f"{password}\n")

    assert result.exit_code == ExitCode.OK, everything_printed(result)
    assert "The password was not stored." in result.stdout
    assert json.loads(api.routes[0].calls.last.request.content)["username"] == username


# ------------------------------------------------------------------------------------------------
# status
# ------------------------------------------------------------------------------------------------


def test_status_with_nothing_stored_says_so_and_succeeds(data_dir: Path, api: respx.MockRouter) -> None:
    route = api.route()

    result = invoke("--json", "caselist", "auth", "status")

    assert result.exit_code == ExitCode.OK
    data = envelope(result)["data"]
    assert data["token_stored"] is False
    assert data["location"] == str(token_file(data_dir))
    assert route.call_count == 0, "status is local unless --check is given"


def test_status_after_login_reports_the_token_without_printing_it(
    data_dir: Path, api: respx.MockRouter, token: str, username: str, password: str
) -> None:
    log_in(api, token, username, password)

    as_json = invoke("--json", "caselist", "auth", "status")
    as_table = invoke("caselist", "auth", "status")

    data = envelope(as_json)["data"]
    assert data["token_stored"] is True
    assert data["expires_at"] == "2026-10-04T00:00:00+00:00"
    assert data["last_validated_at"] is not None
    for result in (as_json, as_table):
        assert result.exit_code == ExitCode.OK
        assert token not in everything_printed(result)
    assert "never shown" in as_table.stdout


def test_status_works_with_the_api_disabled(
    data_dir: Path, api: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_CASELIST__API_ENABLED", "false")

    result = invoke("--json", "caselist", "auth", "status")

    assert result.exit_code == ExitCode.OK
    assert envelope(result)["data"]["api_enabled"] is False


def test_status_check_makes_one_request_and_stamps_the_token(
    data_dir: Path, api: respx.MockRouter, token: str, username: str, password: str
) -> None:
    log_in(api, token, username, password)
    before = json.loads(token_file(data_dir).read_text(encoding="utf-8"))["last_validated_at"]
    route = api.get(f"{API}/caselists").respond(json=[])

    result = invoke("--json", "caselist", "auth", "status", "--check")

    assert result.exit_code == ExitCode.OK, everything_printed(result)
    assert route.call_count == 1
    assert route.calls.last.request.headers["Cookie"] == f"caselist_token={token}"
    data = envelope(result)["data"]
    assert data["checked_now"] is True
    assert data["last_validated_at"] >= before
    assert token not in everything_printed(result)


def test_status_check_with_an_expired_token_fails_after_one_request(
    data_dir: Path, api: respx.MockRouter, token: str, username: str, password: str
) -> None:
    log_in(api, token, username, password)
    route = api.get(f"{API}/caselists").respond(401)

    result = invoke("--json", "caselist", "auth", "status", "--check")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope(result)["error"]["code"] == "CASELIST_AUTH_EXPIRED"
    assert route.call_count == 1
    assert token not in everything_printed(result)


def test_status_check_is_refused_when_the_api_is_disabled(
    data_dir: Path, api: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_CASELIST__API_ENABLED", "false")
    route = api.route()

    result = invoke("--json", "caselist", "auth", "status", "--check")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope(result)["error"]["code"] == "CASELIST_API_DISABLED"
    assert route.call_count == 0


def test_a_token_from_the_environment_is_reported_and_not_printed(
    data_dir: Path, api: respx.MockRouter, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_PROVIDERS__CASELIST_TOKEN", token)

    result = invoke("--json", "caselist", "auth", "status")

    assert envelope(result)["data"]["token_in_settings"] is True
    assert token not in everything_printed(result)


def test_a_token_file_others_can_read_is_refused(
    data_dir: Path, api: respx.MockRouter, token: str, username: str, password: str
) -> None:
    log_in(api, token, username, password)
    os.chmod(token_file(data_dir), 0o644)

    result = invoke("--json", "caselist", "auth", "status")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope(result)["error"]["code"] == "INSECURE_TOKEN_FILE"
    assert token not in everything_printed(result)


# ------------------------------------------------------------------------------------------------
# logout
# ------------------------------------------------------------------------------------------------


def test_logout_deletes_the_token_and_a_second_logout_has_nothing_to_do(
    data_dir: Path, api: respx.MockRouter, token: str, username: str, password: str
) -> None:
    log_in(api, token, username, password)

    first = invoke("--json", "caselist", "auth", "logout")
    second = invoke("--json", "caselist", "auth", "logout")

    assert first.exit_code == ExitCode.OK and envelope(first)["data"]["deleted"] is True
    assert second.exit_code == ExitCode.OK and envelope(second)["data"]["deleted"] is False
    assert not token_file(data_dir).exists()
    assert envelope(invoke("--json", "caselist", "auth", "status"))["data"]["token_stored"] is False
