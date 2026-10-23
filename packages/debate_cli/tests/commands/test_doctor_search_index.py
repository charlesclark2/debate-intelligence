"""`debate-research doctor --search-index`: each store the weekly index stage will index, parsed or not.

`v1-e34-t30`. The weekly run's search index stage (`v1-e39-t09`) indexes the configured caselists
plus `openev` from the version directory of the parser the installed build runs, and a store that
has none leaves the run without a current index: on a fresh installation, the first Wednesday.
With `--search-index`, `doctor` names each such store with the command that parses it and fails;
where the run has no stage, because `caselist.refresh_search_index` is off or the environment names
no bucket, it says the check does not apply and passes.

Plain `doctor` does none of this and loads no settings, because `scripts/install_channel.sh` and
`validate-dev` run it on machines with no installation at all.

Every installation here is a profile and a data directory under `tmp_path`, with version directories
laid out as `caselist parse` names them. Nothing reads an AWS config or reaches a network: the check
lists directories, and the one test that adds `--evidence-profiles` stubs the identity at its port.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.container import ServiceContainer
from debate_cli.exit_codes import ExitCode
from debate_core.integrations.docx_parser import DebateDocxParser

runner = CliRunner()

BUCKET = "debate-dev-evidence-doctor-search-index"
INSTALLED = DebateDocxParser().parser_version
"""The parser version this build runs: the version directory the stage reads."""
OLDER = "2026.01.01-docx-0"
assert OLDER < INSTALLED, "the older parser version must sort before this build's"

UNPARSED_CODE = "SEARCH_INDEX_STORE_NOT_READY"
TURNED_OFF = (
    "turned off by setting (caselist.refresh_search_index); `tub index build` and "
    "`tub index publish` do it by hand"
)
NO_BUCKET = "no search index stage is wired in: an environment that names no evidence bucket has none"


@pytest.fixture(autouse=True)
def data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """A dev profile naming a bucket and a data directory, following two caselists. No AWS config."""
    for name in list(os.environ):
        if name.startswith(("DEBATE_", "AWS_")):
            monkeypatch.delenv(name, raising=False)
    for name in ("AWS_CONFIG_FILE", "AWS_SHARED_CREDENTIALS_FILE"):
        monkeypatch.setenv(name, os.devnull)
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    data = tmp_path / "data"
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{data}"\n'
        f'[storage.s3]\nbucket = "{BUCKET}"\nregion = "us-east-1"\n'
        '[caselist]\nnotifier = "none"\nsync_caselists = ["hsld26", "hspolicy26"]\n'
        f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 1.0\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DEBATE_PROFILE_DIR", str(profiles))
    monkeypatch.setenv("DEBATE_ENV", "dev")
    yield data


def parsed(data_dir: Path, **stores: tuple[str, ...]) -> None:
    """Give each store named exactly the version directories listed, as `caselist parse` names them."""
    for store, versions in stores.items():
        for version in versions:
            (data_dir / "parsed" / store / version).mkdir(parents=True)


def doctor(*arguments: str) -> tuple[int, dict[str, Any]]:
    result: Result = runner.invoke(create_app(), ["--json", "doctor", *arguments])
    lines = result.stdout.splitlines()
    assert len(lines) == 1, f"expected one line of JSON on stdout, got {lines!r}\n{result.stderr}"
    envelope: dict[str, Any] = json.loads(lines[0])
    return result.exit_code, envelope


def report_of(envelope: dict[str, Any]) -> dict[str, Any]:
    report: dict[str, Any] = (
        envelope["data"] if envelope["data"] is not None else envelope["error"]["details"]
    )
    return report


def as_a_person_sees_it(*arguments: str) -> tuple[int, str]:
    """The table and any panel, on one line with the box drawn around them taken off."""
    result = runner.invoke(create_app(), ["doctor", *arguments])
    text = re.sub(r"[│┃┏┓┗┛━─┡┩╇╭╮╰╯┼┬┴├┤┌┐└┘╰╯]", " ", result.stdout + result.stderr)
    return result.exit_code, " ".join(text.split())


# ------------------------------------------------------------------------------------------------
# Plain doctor is as it was
# ------------------------------------------------------------------------------------------------


def test_plain_doctor_loads_no_settings_and_checks_no_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """What `install_channel.sh` and `validate-dev` run. Settings that would be loaded fail the
    test, and nothing is parsed, so a doctor that checked the stores would fail too."""

    def no_settings(self: ServiceContainer) -> Any:
        pytest.fail("plain doctor loaded settings")

    monkeypatch.setattr(ServiceContainer, "settings", property(no_settings))

    exit_code, envelope = doctor()

    assert exit_code == ExitCode.OK, envelope
    assert "search_index" not in envelope["data"]


# ------------------------------------------------------------------------------------------------
# Stores the stage would find unparsed fail the check
# ------------------------------------------------------------------------------------------------


def test_stores_with_no_version_directory_fail_doctor_each_named_with_its_parse_command(
    data_dir: Path,
) -> None:
    parsed(data_dir, hsld26=(INSTALLED,))

    exit_code, envelope = doctor("--search-index")

    assert exit_code == ExitCode.DOMAIN_FAILURE
    error = envelope["error"]
    assert error["code"] == UNPARSED_CODE
    assert error["message"] == (
        f"2 stores have not been parsed by this build's parser, {INSTALLED}: hspolicy26, openev. The "
        "weekly run's search index stage indexes them, so the next run will end without a current "
        "search index."
    )
    assert error["hint"] == (
        "Run `debate-research caselist parse --caselist hspolicy26` and "
        "`debate-research caselist parse --caselist openev` before the next weekly run."
    )
    assert report_of(envelope)["search_index"] == {
        "applies": True,
        "does_not_apply": None,
        "parser_version": INSTALLED,
        "caselists": ["hsld26", "hspolicy26"],
        "stores": [
            {"store": "hsld26", "parsed": True, "fix": None},
            {
                "store": "hspolicy26",
                "parsed": False,
                "fix": "debate-research caselist parse --caselist hspolicy26",
            },
            {"store": "openev", "parsed": False, "fix": "debate-research caselist parse --caselist openev"},
        ],
        "unparsed": ["hspolicy26", "openev"],
    }


def test_a_store_parsed_only_by_an_older_parser_fails_doctor(data_dir: Path) -> None:
    parsed(data_dir, hsld26=(INSTALLED,), hspolicy26=(OLDER,), openev=(INSTALLED,))

    exit_code, envelope = doctor("--search-index")

    assert exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope["error"]["code"] == UNPARSED_CODE
    assert envelope["error"]["message"].startswith(
        f"1 store has not been parsed by this build's parser, {INSTALLED}: hspolicy26. "
    )
    assert envelope["error"]["hint"] == (
        "Run `debate-research caselist parse --caselist hspolicy26` before the next weekly run."
    )


def test_the_caselists_are_the_ones_a_pull_without_caselist_follows(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`caselist.sync_caselists`, from the environment as `install.sh --check-launchd` sets it."""
    monkeypatch.setenv("DEBATE_CASELIST__SYNC_CASELISTS", '["ndtceda26"]')
    parsed(data_dir, hsld26=(INSTALLED,), hspolicy26=(INSTALLED,), openev=(INSTALLED,))

    exit_code, envelope = doctor("--search-index")

    assert exit_code == ExitCode.DOMAIN_FAILURE
    assert report_of(envelope)["search_index"]["unparsed"] == ["ndtceda26"]


# ------------------------------------------------------------------------------------------------
# And pass
# ------------------------------------------------------------------------------------------------


def test_every_store_parsed_passes(data_dir: Path) -> None:
    parsed(
        data_dir,
        hsld26=(OLDER, INSTALLED),
        hspolicy26=(INSTALLED, f"{INSTALLED}_reparse-2"),
        openev=(INSTALLED,),
    )

    exit_code, envelope = doctor("--search-index")

    assert exit_code == ExitCode.OK, envelope
    found = envelope["data"]["search_index"]
    assert found["applies"] is True
    assert [(one["store"], one["parsed"]) for one in found["stores"]] == [
        ("hsld26", True),
        ("hspolicy26", True),
        ("openev", True),
    ]


def test_with_the_setting_off_the_check_does_not_apply_and_passes(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_CASELIST__REFRESH_SEARCH_INDEX", "false")

    exit_code, envelope = doctor("--search-index")

    assert exit_code == ExitCode.OK, envelope
    found = envelope["data"]["search_index"]
    assert (found["applies"], found["does_not_apply"], found["stores"]) == (False, TURNED_OFF, [])


def test_with_no_bucket_the_check_does_not_apply_and_passes(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`test` names no bucket, so its run has no search index stage, parsed or not."""
    monkeypatch.setenv("DEBATE_ENV", "test")
    monkeypatch.delenv("DEBATE_PROFILE_DIR")
    monkeypatch.setenv("DEBATE_STORAGE__DATA_DIR", str(data_dir))

    exit_code, envelope = doctor("--search-index")

    assert exit_code == ExitCode.OK, envelope
    found = envelope["data"]["search_index"]
    assert (found["applies"], found["does_not_apply"], found["stores"]) == (False, NO_BUCKET, [])


# ------------------------------------------------------------------------------------------------
# With the profile check
# ------------------------------------------------------------------------------------------------


class SignedInAs:
    async def assumed_role_name(self) -> str | None:
        return "AWSReservedSSO_DebateDevEvidenceOperator_fedcba9876543210"


def test_both_options_together_report_both_checks_and_fail_on_the_store(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_STORAGE__S3__AWS_PROFILE", "debate-dev-evidence")
    monkeypatch.setattr(
        ServiceContainer, "caller_identity_for", lambda self, profile: SignedInAs(), raising=False
    )
    parsed(data_dir, hsld26=(INSTALLED,), openev=(INSTALLED,))

    exit_code, envelope = doctor("--evidence-profiles", "--search-index")

    assert exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope["error"]["code"] == UNPARSED_CODE
    report = report_of(envelope)
    assert [one["permission_set"] for one in report["evidence_profiles"]] == ["DebateDevEvidenceOperator"]
    assert report["search_index"]["unparsed"] == ["hspolicy26"]


def test_an_unparsed_store_and_another_failed_check_are_reported_together(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(unicodedata, "unidata_version", "1.0.0")

    exit_code, envelope = doctor("--search-index")

    assert exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope["error"]["code"] == "INSTALLATION_CHECKS_FAILED"
    assert "Unicode database is 1.0.0" in envelope["error"]["message"]
    assert "3 stores have not been parsed" in envelope["error"]["message"]


# ------------------------------------------------------------------------------------------------
# For a person
# ------------------------------------------------------------------------------------------------


def test_a_person_sees_a_row_for_each_store_then_the_fix_and_no_path(data_dir: Path, tmp_path: Path) -> None:
    parsed(data_dir, hsld26=(INSTALLED,), hspolicy26=(OLDER,))

    exit_code, shown = as_a_person_sees_it("--search-index")

    assert exit_code == ExitCode.DOMAIN_FAILURE
    assert "Search index caselists hsld26, hspolicy26" in shown
    assert f"Search index store hsld26: parsed by {INSTALLED}" in shown
    assert f"Search index store hspolicy26: not parsed by this build's parser, {INSTALLED}" in shown
    assert f"Search index store openev: not parsed by this build's parser, {INSTALLED}" in shown
    assert UNPARSED_CODE in shown
    assert "debate-research caselist parse --caselist hspolicy26" in shown
    assert "debate-research caselist parse --caselist openev" in shown
    assert str(tmp_path) not in shown
    assert "parsed/" not in shown


def test_a_person_is_told_why_the_check_does_not_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEBATE_CASELIST__REFRESH_SEARCH_INDEX", "false")

    exit_code, shown = as_a_person_sees_it("--search-index")

    assert exit_code == ExitCode.OK, shown
    assert f"Search index stores does not apply: {TURNED_OFF}" in shown


def test_a_person_is_told_when_no_caselist_is_configured(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_CASELIST__SYNC_CASELISTS", "[]")
    parsed(data_dir, openev=(INSTALLED,))

    exit_code, shown = as_a_person_sees_it("--search-index")

    assert exit_code == ExitCode.OK, shown
    assert (
        "Search index caselists none configured (caselist.sync_caselists), so openev alone is checked"
        in shown
    )
    assert f"Search index store openev: parsed by {INSTALLED}" in shown
