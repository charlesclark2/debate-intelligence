"""`debate-research fetch` on the build under test, offline (v1-e04-t06).

The recorded tier cannot fetch: the network guard refuses every host, loopback included, and the
fetcher refuses a loopback stand-in by design, so retrieval over the recorded cassettes is checked in
pytest's process by `tests/integration/test_fetch_cli.py`. What the build is checked for here is
everything that needs no request: the command is installed with its help and exit codes, the
composition root builds the fetcher and both extractors on this build's own dependencies, pasted text
is stored as USER_SUPPLIED only after attestation, and a refusal stores nothing. The guard's log
staying empty is the proof that `--paste` fetches nothing.
"""

from __future__ import annotations

from pathlib import Path

from tests.smoke.installed_build import CliRun, InstalledCli

SOURCE_URL = "https://www.harborreview.example/politics/2026/10/inside-the-tariff-talks"
PASTED = "\n\n".join(
    ["Negotiators from two invented trading partners met for a fourth round of talks this week. " * 3] * 3
)
"""Three paragraphs of invented text, over the 500-character minimum for an article."""


def snapshot_files(installed_cli: InstalledCli) -> list[Path]:
    blobs = installed_cli.data_dir / "blobs"
    return sorted(path for path in blobs.rglob("*") if path.is_file()) if blobs.exists() else []


def paste(installed_cli: InstalledCli, *options: str) -> CliRun:
    return installed_cli.run(
        "--json", "fetch", "--paste", "-", "--source-url", SOURCE_URL, *options, stdin=PASTED
    )


def test_fetch_is_installed_with_its_exit_codes(installed_cli: InstalledCli) -> None:
    run = installed_cli.run("fetch", "--help")

    assert run.exit_code == 0, run.output
    for line in (
        "0  ACCESSIBLE and stored",
        "1  refused, nothing stored",
        "3  PAYWALLED",
        "--i-have-lawful-access",
    ):
        assert line in run.stdout


def test_pasted_text_without_the_attestation_is_refused_and_nothing_is_stored(
    installed_cli: InstalledCli,
) -> None:
    run = paste(installed_cli)

    assert run.exit_code == 1, run.output
    error = run.envelope()["error"]
    assert isinstance(error, dict)
    assert error["code"] == "USER_TEXT_NOT_ATTESTED"
    assert snapshot_files(installed_cli) == []


def test_attested_pasted_text_is_stored_as_user_supplied_without_a_fetch(installed_cli: InstalledCli) -> None:
    first = paste(installed_cli, "--i-have-lawful-access")
    again = paste(installed_cli, "--i-have-lawful-access")

    assert first.exit_code == 0, first.output
    data = first.envelope()["data"]
    assert isinstance(data, dict)
    assert (data["provenance_mode"], data["fetched"], data["canonical_url"]) == (
        "USER_SUPPLIED",
        False,
        SOURCE_URL,
    )
    snapshot = data["snapshot"]
    assert isinstance(snapshot, dict)
    assert (snapshot["provenance_mode"], snapshot["paragraph_count"], snapshot["reused"]) == (
        "USER_SUPPLIED",
        3,
        False,
    )
    assert len(snapshot_files(installed_cli)) == 2, "the raw text and the normalized text"
    again_data = again.envelope()["data"]
    assert isinstance(again_data, dict) and isinstance(again_data["snapshot"], dict)
    assert (again_data["snapshot"]["snapshot_id"], again_data["snapshot"]["reused"]) == (
        snapshot["snapshot_id"],
        True,
    )
    assert "Negotiators" not in first.output + again.output


def test_a_string_that_names_no_source_exits_one_and_a_bad_command_line_exits_two(
    installed_cli: InstalledCli,
) -> None:
    not_a_url = installed_cli.run("--json", "fetch", "mailto:desk@example.org")
    neither = installed_cli.run("fetch")

    assert not_a_url.exit_code == 1, not_a_url.output
    error = not_a_url.envelope()["error"]
    assert isinstance(error, dict) and error["code"] == "INVALID_SOURCE_URL"
    assert neither.exit_code == 2, neither.output
    assert snapshot_files(installed_cli) == []
