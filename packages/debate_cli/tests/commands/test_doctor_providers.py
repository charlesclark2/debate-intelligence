"""`debate-research doctor --providers`: each enabled provider's key or email, and never a failure (`v1-e41-t22`).

Plain `doctor` loads no settings (`scripts/install_channel.sh` and `validate-dev` run it on machines
with none), so the provider rows come with an option, as `--routing-file`'s does. A row says whether
the credential is set and which source set it, never its value; a blank counts as missing. The rows
and the JSON are written out by hand. Every home folder is under `tmp_path`, and the values are
short invented strings that each test asserts reach neither stream. Nothing reaches a network.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode
from debate_core.application import settings as settings_module

runner = CliRunner()

EMAIL = "dp-Em4il-j6V"
KEY = "dp-K3y-3Hs1"
SOURCE = "user-env:~/.debate-research/dev.env"
COMMITTED_ENABLED = '["openalex", "crossref", "rss", "federal_register", "govinfo"]'


@pytest.fixture(autouse=True)
def installation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """A dev profile enabling the committed profiles' five providers, a home folder, no AWS config."""
    for name in list(os.environ):
        if name.startswith(("DEBATE_", "AWS_")):
            monkeypatch.delenv(name, raising=False)
    for name in ("AWS_CONFIG_FILE", "AWS_SHARED_CREDENTIALS_FILE"):
        monkeypatch.setenv(name, os.devnull)
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{tmp_path / "data"}"\n'
        f"[providers]\nenabled = {COMMITTED_ENABLED}\n"
        f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 1.0\n',
        encoding="utf-8",
    )
    (profiles / "test.toml").write_text(
        f'allow_network = false\n[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 0.0\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DEBATE_PROFILE_DIR", str(profiles))
    monkeypatch.setenv("DEBATE_ENV", "dev")
    home = tmp_path / "home"
    (home / ".debate-research").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(settings_module, "user_credentials_directory", lambda: home / ".debate-research")
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    yield home


def per_user_file(home: Path, *lines: str, mode: int = 0o600) -> None:
    path = home / ".debate-research" / "dev.env"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(mode)


def doctor_json(*arguments: str) -> tuple[int, dict[str, Any], Result]:
    result = runner.invoke(create_app(), ["--json", "doctor", *arguments])
    lines = result.stdout.splitlines()
    assert len(lines) == 1, f"expected one line of JSON on stdout, got {lines!r}\n{result.stderr}"
    return result.exit_code, json.loads(lines[0]), result


def provider_rows() -> tuple[int, list[str], Result]:
    """The rows from "Credentials file" on, each as `Check Value` with the borders taken off."""
    result = runner.invoke(create_app(), ["doctor", "--providers"])
    lines = [" ".join(re.sub(r"[│┃┏┓┗┛━─┡┩╇╭╮╰╯┼┬┴├┤┌┐└┘]", " ", line).split()) for line in result.stdout.splitlines()]
    lines = [line for line in lines if line]
    start = next((index for index, line in enumerate(lines) if line.startswith("Credentials file")), len(lines))
    return result.exit_code, lines[start:], result


def assert_no_value(result: Result) -> None:
    assert EMAIL not in result.stdout + result.stderr
    assert KEY not in result.stdout + result.stderr


def test_with_nothing_set_each_provider_says_what_a_search_does_without_it() -> None:
    exit_code, rows, _ = provider_rows()

    assert exit_code == ExitCode.OK
    assert rows == [
        "Credentials file ~/.debate-research/dev.env: not there",
        "OpenAlex no OpenAlex key: keyless (a lower daily allowance)",
        "Crossref no contact email: Crossref's public pool",
        "RSS feeds no key needed",
        "Federal Register no key needed",
        "GovInfo no GovInfo key: GovInfo not asked",
    ]


def test_credentials_from_the_per_user_file_are_named_by_source_and_never_shown(installation: Path) -> None:
    per_user_file(
        installation,
        f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}",
        f"DEBATE_PROVIDERS__OPENALEX_API_KEY={KEY}",
        f"DEBATE_PROVIDERS__API_DATA_GOV_KEY={KEY}",
    )

    exit_code, rows, result = provider_rows()

    assert exit_code == ExitCode.OK
    assert rows == [
        "Credentials file ~/.debate-research/dev.env: read",
        f"OpenAlex API key set ({SOURCE}): with a key",
        f"Crossref contact email set ({SOURCE}): Crossref's polite pool",
        "RSS feeds no key needed",
        "Federal Register no key needed",
        f"GovInfo api.data.gov key set ({SOURCE})",
    ]
    assert_no_value(result)


def test_a_credential_from_a_variable_is_named_by_its_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEBATE_PROVIDERS__CONTACT_EMAIL", EMAIL)

    _, rows, result = provider_rows()

    assert "Crossref contact email set (env:DEBATE_PROVIDERS__CONTACT_EMAIL): Crossref's polite pool" in rows
    assert_no_value(result)


def test_a_blank_value_counts_as_missing(installation: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    per_user_file(installation, f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}", "DEBATE_PROVIDERS__API_DATA_GOV_KEY=  ")
    monkeypatch.setenv("DEBATE_PROVIDERS__CONTACT_EMAIL", "")

    _, rows, _ = provider_rows()

    assert "Crossref no contact email: Crossref's public pool" in rows
    assert "GovInfo no GovInfo key: GovInfo not asked" in rows


def test_providers_this_build_has_no_adapter_for_say_so_and_keyless_ones_need_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEBATE_PROVIDERS__ENABLED", '["govinfo", "gdelt", "google_news", "semantic_scholar"]')

    _, rows, _ = provider_rows()

    assert rows == [
        "Credentials file ~/.debate-research/dev.env: not there",
        "Semantic Scholar no adapter in this build",
        "Google News no key needed",
        "GDELT no adapter in this build",
        "GovInfo no GovInfo key: GovInfo not asked",
    ]


def test_with_no_provider_enabled_one_row_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEBATE_PROVIDERS__ENABLED", "[]")

    _, rows, _ = provider_rows()

    assert rows == [
        "Credentials file ~/.debate-research/dev.env: not there",
        "Providers none enabled (providers.enabled)",
    ]


def test_the_test_environment_reads_no_per_user_file(installation: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    per_user_file(installation, f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}")
    monkeypatch.setenv("DEBATE_ENV", "test")

    exit_code, rows, result = provider_rows()

    assert exit_code == ExitCode.OK
    assert rows == ["Credentials file not read in the test environment", "Providers none enabled (providers.enabled)"]
    assert_no_value(result)


def test_the_json_carries_the_rows_under_providers(installation: Path) -> None:
    per_user_file(installation, f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}")

    exit_code, envelope, result = doctor_json("--providers")

    assert exit_code == ExitCode.OK
    assert envelope["data"]["providers"] == {
        "credentials_file": {"path": "~/.debate-research/dev.env", "state": "read"},
        "enabled": [
            {
                "provider": "openalex",
                "label": "OpenAlex",
                "credential": "DEBATE_PROVIDERS__OPENALEX_API_KEY",
                "set": False,
                "source": "default",
                "summary": "no OpenAlex key: keyless (a lower daily allowance)",
            },
            {
                "provider": "crossref",
                "label": "Crossref",
                "credential": "DEBATE_PROVIDERS__CONTACT_EMAIL",
                "set": True,
                "source": SOURCE,
                "summary": f"contact email set ({SOURCE}): Crossref's polite pool",
            },
            {
                "provider": "rss",
                "label": "RSS feeds",
                "credential": None,
                "set": None,
                "source": None,
                "summary": "no key needed",
            },
            {
                "provider": "federal_register",
                "label": "Federal Register",
                "credential": None,
                "set": None,
                "source": None,
                "summary": "no key needed",
            },
            {
                "provider": "govinfo",
                "label": "GovInfo",
                "credential": "DEBATE_PROVIDERS__API_DATA_GOV_KEY",
                "set": False,
                "source": "default",
                "summary": "no GovInfo key: GovInfo not asked",
            },
        ],
    }
    assert_no_value(result)


def test_plain_doctor_has_no_providers_key_and_reads_no_per_user_file(installation: Path) -> None:
    """A refused per-user file would stop any settings load; plain doctor loads none, so it passes."""
    per_user_file(installation, f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}", mode=0o644)

    exit_code, envelope, result = doctor_json()

    assert exit_code == ExitCode.OK
    assert "providers" not in envelope["data"]
    assert_no_value(result)


def test_a_refused_per_user_file_stops_doctor_providers_as_it_stops_every_command(installation: Path) -> None:
    per_user_file(installation, f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}", mode=0o644)

    exit_code, envelope, result = doctor_json("--providers")

    assert exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope["error"]["message"] == (
        "~/.debate-research/dev.env has permissions -rw-r--r--, so someone other than its owner can read or "
        "change it, and it was not read. Run: chmod 600 ~/.debate-research/dev.env"
    )
    assert_no_value(result)
