"""`debate-research caselist auth status`, as `validate-dev` runs it, and one opt-in live check.

**The offline checks are unmarked and run in the default suite.** What they verify — that the
installed command resolves its token store from a profile, reports a stored token without ever
printing it, refuses a token file others can read, and refuses `login` while the API is disabled —
needs no network and no account. Marking them `live` would mean the check covering the command the
scheduled pull depends on was skipped in CI *and* before every promotion (see this directory's
README, and the trap v1-e30-t03 recorded: the default options are `-m "not slow and not live"`, so
a live-marked check is collected, skipped, and looks green).

**The live check needs the real API and the operator's real token**, so it is `live`, opt-in and
told what to look at: it runs only when `CASELIST_LIVE_SLUG` names a caselist, in an environment
where the operator has turned the API on and logged in. It only *lists* — `auth status --check` and
the archive listing for that slug — and never downloads, so it spends none of the maintainer's
10-per-minute allowance or the site's five bulk downloads a day::

    DEBATE_ENV=dev DEBATE_CASELIST__API_ENABLED=true CASELIST_LIVE_SLUG=hsld26 \\
        uv run pytest tests/smoke/test_caselist_auth.py -m live
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode
from debate_core.application.settings import load_settings
from debate_core.integrations.opencaselist import (
    CaselistTokenStore,
    OpenCaselistClient,
    default_secret_file,
)
from debate_core.integrations.opencaselist.token_store import FileTokenBackend

runner = CliRunner()

LIVE_SLUG = os.environ.get("CASELIST_LIVE_SLUG", "").strip()


@pytest.fixture
def installation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """A dev profile of this check's own that keeps the token in a file, and no inherited DEBATE_*."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{tmp_path / "data"}"\n'
        f'[models]\nrouting_file = "{tmp_path / "routing.yaml"}"\nbudget_usd_daily = 1.0\n'
        '[caselist]\ntoken_backend = "file"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DEBATE_PROFILE_DIR", str(profiles))
    monkeypatch.setenv("DEBATE_ENV", "dev")
    yield tmp_path / "data"


def status(*extra: str) -> Result:
    return runner.invoke(create_app(), ["--json", "caselist", "auth", "status", *extra])


def data_of(result: Result) -> dict[str, Any]:
    return json.loads(result.stdout)["data"]


def test_status_on_a_fresh_installation_reports_no_token_and_a_disabled_api(installation: Path) -> None:
    result = status()

    assert result.exit_code == ExitCode.OK, result.stdout + result.stderr
    data = data_of(result)
    assert data["token_stored"] is False
    assert data["api_enabled"] is False, "the API must be off until the operator turns it on"
    assert data["location"] == str(default_secret_file(installation))


def test_status_reports_a_stored_token_and_never_prints_it(installation: Path) -> None:
    token = f"smoke-token-{secrets.token_hex(16)}"
    CaselistTokenStore(FileTokenBackend(default_secret_file(installation))).save(
        SecretStr(token), expires_at=None
    )

    as_json = status()
    as_table = runner.invoke(create_app(), ["caselist", "auth", "status"])

    assert data_of(as_json)["token_stored"] is True
    for result in (as_json, as_table):
        assert result.exit_code == ExitCode.OK
        assert token not in result.stdout + result.stderr


def test_status_refuses_a_token_file_others_can_read(installation: Path) -> None:
    path = default_secret_file(installation)
    CaselistTokenStore(FileTokenBackend(path)).save(SecretStr(secrets.token_hex(8)), expires_at=None)
    path.chmod(0o644)

    result = status()

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert json.loads(result.stdout)["error"]["code"] == "INSECURE_TOKEN_FILE"


def test_login_is_refused_while_the_api_is_disabled(installation: Path) -> None:
    result = runner.invoke(
        create_app(), ["--json", "caselist", "auth", "login", "--username", "nobody"], input="x\n"
    )

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert json.loads(result.stdout.strip().splitlines()[-1])["error"]["code"] == "CASELIST_API_DISABLED"


# ------------------------------------------------------------------------------------------------
# Live, opt-in: the operator's real token against the real API. Lists only; never downloads.
# ------------------------------------------------------------------------------------------------


@pytest.mark.live
@pytest.mark.enable_socket
def test_live_the_stored_token_works_and_the_archives_list() -> None:
    if not LIVE_SLUG:
        pytest.skip("set CASELIST_LIVE_SLUG to the caselist to list, e.g. hsld26")

    checked = status("--check")
    assert checked.exit_code == ExitCode.OK, checked.stdout + checked.stderr
    assert data_of(checked)["checked_now"] is True

    settings = load_settings()
    from debate_cli import package_version

    async def listing() -> list[str]:
        async with OpenCaselistClient.from_settings(
            settings,
            token_store=CaselistTokenStore.for_settings(
                settings.caselist.token_backend,
                account=settings.environment.value,
                secret_file=settings.caselist.secret_file or default_secret_file(settings.storage.data_dir),
            ),
            user_agent_version=package_version(),
        ) as client:
            return [archive.name for archive in await client.list_archives(LIVE_SLUG)]

    names = asyncio.run(listing())
    assert names, f"OpenCaselist listed no archives for {LIVE_SLUG}"
    assert all(name.startswith(f"{LIVE_SLUG}-") for name in names)
