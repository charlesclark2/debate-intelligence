"""The backfile commands against the installed build, offline (`v1-e34-t34`).

Both reach OpenCaselist, so where the data-use policy's E34 gate is not turned on (`caselist.api_enabled`
off) each refuses before a request is built: the gate covers a backfile as it covers the weekly run.
The test turns the gate off itself: the bundled dev profile turns it on (`v1-e40-t06`), and the
installed build runs with `DEBATE_ENV=dev` (PM batch 2026-10-27u, after validate-dev's smoke tier
read the dev profile's gate as on). This checkout's script reads the same profile (`v1-e01-t41`), so
without that pin the check fails in the pull request's tier too. The import's own rules, its lock
and its publish are checked in process against moto and a stand-in site
(`packages/debate_cli/tests/bucket_mode/test_backfile_import.py`).
"""

from __future__ import annotations

import pytest
from tests.smoke.installed_build import InstalledCli

from debate_cli.exit_codes import ExitCode


@pytest.mark.parametrize(
    "command",
    [
        ("caselist", "backfile-survey"),
        ("caselist", "backfile-import", "--caselist", "testcl25"),
        ("caselist", "backfile-import", "--caselist", "testcl25", "--execute"),
    ],
)
def test_without_the_api_gate_a_backfile_command_is_refused_before_any_request(
    installed_cli: InstalledCli, command: tuple[str, ...]
) -> None:
    refused = installed_cli.run(
        "--json",
        *command,
        env={"DEBATE_CASELIST__API_ENABLED": "false", "DEBATE_CASELIST__BACKFILE_CASELISTS": '["testcl25"]'},
    )

    assert refused.exit_code == ExitCode.DOMAIN_FAILURE, refused.output
    envelope = refused.envelope()
    assert envelope["status"] == "error"
    error = envelope["error"]
    assert isinstance(error, dict)
    assert error["code"] == "CASELIST_API_DISABLED", error
