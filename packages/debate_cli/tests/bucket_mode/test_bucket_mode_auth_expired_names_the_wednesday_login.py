"""A cloud run refused for an expired login names the Wednesday login in its own output (`v1-e40-t35`).

`v1-e40-t33` gave a bucket-mode run OpenCaselist refused with 401 or 403 (`CASELIST_AUTH_EXPIRED`) the
cloud's cure in its notification and alert email. The command's own output still printed the error's
sentence, "Run `debate-research caselist auth login` again", and the run monitor kept it as the record's
`error_message`. So the cloud run's log, and `caselist runs --json` for it, told the operator to log in
by hand, which `caselist-cloud-run.md` forbids: it would be a second login that week.

In bucket mode the output gives what was refused and the cure as its hint, in `caselist_pull._hint_for`'s
idiom ("In bucket mode …"), and the record keeps what was refused without the Mac's login. The same goes
for a camp download a 401 fails, whose stage reason and hint the command prints, and for `caselist
backfile-import`, which the root handler reports. On the Mac every word stays, pinned here by its old
text.

Each run is the real command through Typer's `CliRunner`, against moto and the stand-in site of
`conftest.py`, with the site answering 401 where a test says. Every expected sentence is written out by
hand. Nothing here opens a socket.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any, Final

import pytest
from tests.fixtures.parse_pipeline.build_parse_world import CASELIST, WEEKS

from debate_cli.exit_codes import ExitCode

World = Any
"""`conftest.py`'s world, which a test module cannot import by name."""

API: Final = "https://api.opencaselist.example.invalid/v1"
WEEK_1, WEEK_2, WEEK_3 = (week.snapshot for week in WEEKS)
BACKFILE: Final = "testcl25"

# ------------------------------------------------------------------------------------------------
# What each output says, by hand
# ------------------------------------------------------------------------------------------------

THE_LISTING_REFUSED: Final = (
    f"OpenCaselist refused list archives for {CASELIST} with HTTP 401; the caselist_token has expired or "
    "been revoked."
)
"""What was refused and why: the error's first sentence, in either mode."""

THE_MACS_INSTRUCTION: Final = (
    " Run `debate-research caselist auth login` again. If it happens straight after a login, stop and "
    "tell the operator: access may have been suspended (policy clause 10)."
)
"""What the error's message goes on to say on the Mac, as before `v1-e40-t35`, word for word."""

THE_CURE_IN_THE_CLOUD: Final = (
    "In bucket mode the next Wednesday 03:00 login renews the caselist_token, and the run after it takes "
    "up what this run did not finish, from the run state saved in the bucket; a backfile import refused "
    'for it starts again after Thursday 00:00 (caselist-cloud-run.md, "A run refused for an expired '
    'login"); never a login by hand, which would be a second login.'
)
"""The bucket-mode hint: `v1-e40-t33`'s cure, in `_hint_for`'s "In bucket mode …" idiom."""

THE_UNFINISHED_RUN_CURE_IN_THE_CLOUD: Final = (
    "In bucket mode the next cloud run takes up what this run did not finish, from the run state saved in "
    'the bucket: the weekly run, or one started by hand (caselist-cloud-run.md, "A failed or stopped '
    "run\"); never a publish from the operator's Mac."
)
"""`v1-e40-t28`'s hint for any other failed download in bucket mode: unchanged."""

THE_DOWNLOAD_HINT_ON_THE_MAC: Final = (
    "Nothing that did download was lost: it is in the inbox and imported. Run the same command again — an "
    "archive already held is not fetched twice."
)
"""A failed download's hint on the Mac, as before, word for word."""

A_NEW_CAMP_FILE: Final = {
    "openev_id": 513,
    "path": "/openev/2026/Tamarack/TSF-Floodplain Permit Counterplan.docx",
    "filename": "TSF-Floodplain Permit Counterplan.docx",
    "year": 2026,
    "camp": "Tamarack",
    "tags": {"policy": True},
}
"""An invented camp file listed after the seed, so that the next run downloads it from the API host."""

THE_CAMP_DOWNLOAD_REFUSED: Final = (
    "OpenCaselist refused download OpenEv file 513 with HTTP 401; the caselist_token has expired or been "
    "revoked."
)

THE_LOGIN: Final = "auth login"


def flattened(text: str) -> str:
    """`text` as one line, with a panel's borders gone: Rich wraps a panel at the terminal's width."""
    return " ".join(text.replace("│", " ").split())


# ------------------------------------------------------------------------------------------------
# The installation, and the site refusing it
# ------------------------------------------------------------------------------------------------


def seeded_with_two_weeks(world: World) -> None:
    """Two weeks pulled on the Mac and seeded into the bucket; then a week later, a third listed."""
    world.listing(WEEK_1, WEEK_2)
    assert world.pull()["exit_code"] == ExitCode.OK
    world.seed()
    world.clock.advance(timedelta(days=7))
    world.listing(WEEK_1, WEEK_2, WEEK_3)


def pulled_on_the_mac(world: World) -> None:
    """Two weeks pulled on the Mac, in local mode; then a week later, a third listed."""
    world.listing(WEEK_1, WEEK_2)
    assert world.pull()["exit_code"] == ExitCode.OK
    world.clock.advance(timedelta(days=7))
    world.listing(WEEK_1, WEEK_2, WEEK_3)


def in_a_cloud_task(world: World, tmp_path: Path) -> Path:
    """The cloud run's own empty data directory, in bucket mode: it restores from the bucket."""
    world.mode("bucket")
    return world.use(tmp_path / "cloud-task")


def the_listing_answers(world: World, status: int) -> None:
    world.site.get(f"{API}/caselists/{CASELIST}/downloads").respond(status)


def a_new_camp_file_whose_download_answers(world: World, status: int) -> None:
    world.site.get(f"{API}/openev").respond(200, json=[A_NEW_CAMP_FILE])
    world.site.get(f"{API}/download").respond(status)


def the_record_of(world: World) -> dict[str, Any]:
    record, _ = world.last_record()
    return record


def what_the_bucket_holds_as_text(world: World) -> str:
    """Every JSON object the bucket holds under the run reports, as one text."""
    return "\n".join(
        world.body(key).decode("utf-8")
        for key in sorted(world.object_keys("reports/sync/"))
        if key.endswith((".json", ".jsonl"))
    )


# ------------------------------------------------------------------------------------------------
# `caselist pull` refused at the listing: the run stops on the error
# ------------------------------------------------------------------------------------------------


def test_a_bucket_mode_pull_refused_for_auth_expired_names_the_wednesday_login(
    world: World, tmp_path: Path
) -> None:
    seeded_with_two_weeks(world)
    in_a_cloud_task(world, tmp_path)
    the_listing_answers(world, 401)

    refused = world.pull()

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    error = refused["error"]
    assert error["code"] == "CASELIST_AUTH_EXPIRED"
    assert error["message"] == THE_LISTING_REFUSED
    assert error["hint"] == THE_CURE_IN_THE_CLOUD
    assert error["details"] == {"status_code": 401, "operation": f"list archives for {CASELIST}"}
    assert THE_LOGIN not in json.dumps(refused)


def test_a_bucket_mode_pull_refused_for_auth_expired_prints_no_login_in_its_panel(
    world: World, tmp_path: Path
) -> None:
    """What the cloud run's log keeps when the command is run without `--json`."""
    seeded_with_two_weeks(world)
    in_a_cloud_task(world, tmp_path)
    the_listing_answers(world, 401)

    result = world.invoke("caselist", "pull", "--caselist", CASELIST)

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    panel = flattened(result.output)
    assert THE_LISTING_REFUSED in panel
    assert THE_CURE_IN_THE_CLOUD in panel
    assert THE_LOGIN not in panel
    assert "debate-research" not in panel


def test_a_bucket_mode_run_refused_for_auth_expired_records_no_login(world: World, tmp_path: Path) -> None:
    """`error_message` keeps what was refused, a string as every build reads it, without the Mac's login."""
    seeded_with_two_weeks(world)
    in_a_cloud_task(world, tmp_path)
    the_listing_answers(world, 401)

    world.pull()

    record = the_record_of(world)
    assert record["outcome"] == "failed"
    assert record["error_class"] == "CaselistAuthExpired"
    assert record["error_message"] == THE_LISTING_REFUSED
    assert THE_LOGIN not in what_the_bucket_holds_as_text(world)
    listed = world.run("caselist", "runs")
    assert listed["exit_code"] == ExitCode.OK, listed
    assert THE_LISTING_REFUSED in json.dumps(listed)
    assert THE_LOGIN not in json.dumps(listed)


def test_a_mac_pull_refused_for_auth_expired_keeps_its_output_word_for_word(world: World) -> None:
    pulled_on_the_mac(world)
    the_listing_answers(world, 401)

    refused = world.pull()

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    error = refused["error"]
    assert error["code"] == "CASELIST_AUTH_EXPIRED"
    assert error["message"] == THE_LISTING_REFUSED + THE_MACS_INSTRUCTION
    assert error.get("hint") is None
    assert error["details"] == {"status_code": 401, "operation": f"list archives for {CASELIST}"}
    assert "Wednesday" not in json.dumps(refused)


def test_a_mac_pull_refused_for_auth_expired_keeps_its_panel_word_for_word(world: World) -> None:
    pulled_on_the_mac(world)
    the_listing_answers(world, 401)

    result = world.invoke("caselist", "pull", "--caselist", CASELIST)

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    panel = flattened(result.output)
    assert THE_LISTING_REFUSED + THE_MACS_INSTRUCTION in panel
    assert "Wednesday" not in panel


def test_a_mac_run_refused_for_auth_expired_keeps_its_record_word_for_word(world: World) -> None:
    pulled_on_the_mac(world)
    the_listing_answers(world, 401)

    world.pull()

    record = the_record_of(world)
    assert record["error_class"] == "CaselistAuthExpired"
    assert record["error_message"] == THE_LISTING_REFUSED + THE_MACS_INSTRUCTION


def test_a_bucket_mode_pull_stopped_by_another_code_than_auth_expired_names_no_wednesday_login(
    world: World, tmp_path: Path
) -> None:
    """A 404 at the listing is not an expired login: its output is as it was, with no cure added."""
    seeded_with_two_weeks(world)
    in_a_cloud_task(world, tmp_path)
    the_listing_answers(world, 404)

    refused = world.pull()

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    assert refused["error"]["code"] != "CASELIST_AUTH_EXPIRED"
    assert "Wednesday" not in json.dumps(refused)
    assert "Wednesday" not in (the_record_of(world)["error_message"] or "")


# ------------------------------------------------------------------------------------------------
# `caselist pull` refused on a camp download: the download stage fails
# ------------------------------------------------------------------------------------------------


def test_a_bucket_mode_download_refused_for_auth_expired_names_the_wednesday_login(
    world: World, tmp_path: Path
) -> None:
    seeded_with_two_weeks(world)
    in_a_cloud_task(world, tmp_path)
    a_new_camp_file_whose_download_answers(world, 401)

    incomplete = world.pull()

    assert incomplete["exit_code"] == ExitCode.DOMAIN_FAILURE, incomplete
    error = incomplete["error"]
    assert error["code"] == "CASELIST_PULL_INCOMPLETE"
    assert THE_CAMP_DOWNLOAD_REFUSED in error["message"]
    assert error["hint"] == THE_CURE_IN_THE_CLOUD
    assert THE_LOGIN not in json.dumps(incomplete)
    [download] = [stage for stage in the_record_of(world)["stages"] if stage["stage"] == "download"]
    assert download["outcome"] == "failed"
    assert THE_CAMP_DOWNLOAD_REFUSED in download["reason"]
    assert THE_LOGIN not in what_the_bucket_holds_as_text(world)


def test_a_mac_download_refused_for_auth_expired_keeps_its_output_word_for_word(world: World) -> None:
    pulled_on_the_mac(world)
    a_new_camp_file_whose_download_answers(world, 401)

    incomplete = world.pull()

    assert incomplete["exit_code"] == ExitCode.DOMAIN_FAILURE, incomplete
    error = incomplete["error"]
    assert error["code"] == "CASELIST_PULL_INCOMPLETE"
    assert THE_CAMP_DOWNLOAD_REFUSED + THE_MACS_INSTRUCTION in error["message"]
    assert error["hint"] == THE_DOWNLOAD_HINT_ON_THE_MAC
    [download] = [stage for stage in the_record_of(world)["stages"] if stage["stage"] == "download"]
    assert THE_CAMP_DOWNLOAD_REFUSED + THE_MACS_INSTRUCTION in download["reason"]


def test_a_bucket_mode_download_failed_on_another_code_than_auth_expired_keeps_the_next_cloud_run(
    world: World, tmp_path: Path
) -> None:
    seeded_with_two_weeks(world)
    in_a_cloud_task(world, tmp_path)
    a_new_camp_file_whose_download_answers(world, 404)

    incomplete = world.pull()

    error = incomplete["error"]
    assert error["code"] == "CASELIST_PULL_INCOMPLETE"
    assert "CASELIST_AUTH_EXPIRED" not in json.dumps(incomplete)
    assert error["hint"] == THE_UNFINISHED_RUN_CURE_IN_THE_CLOUD


# ------------------------------------------------------------------------------------------------
# `caselist backfile-import` refused at the listing
# ------------------------------------------------------------------------------------------------

THE_BACKFILE_LISTING_REFUSED: Final = (
    f"OpenCaselist refused list archives for {BACKFILE} with HTTP 401; the caselist_token has expired or "
    "been revoked."
)


def a_backfile_whose_listing_answers_401(world: World) -> None:
    world.monkeypatch.setenv("DEBATE_CASELIST__BACKFILE_CASELISTS", json.dumps([BACKFILE]))
    world.site.get(f"{API}/caselists/{BACKFILE}/downloads").respond(401)


@pytest.mark.parametrize("execute", [False, True], ids=["dry-run", "execute"])
def test_a_bucket_mode_backfile_import_refused_for_auth_expired_names_the_wednesday_login(
    world: World, tmp_path: Path, execute: bool
) -> None:
    in_a_cloud_task(world, tmp_path)
    a_backfile_whose_listing_answers_401(world)

    refused = world.run(
        "caselist", "backfile-import", "--caselist", BACKFILE, *(["--execute"] if execute else [])
    )

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    error = refused["error"]
    assert error["code"] == "CASELIST_AUTH_EXPIRED"
    assert error["message"] == THE_BACKFILE_LISTING_REFUSED
    assert error["hint"] == THE_CURE_IN_THE_CLOUD
    assert THE_LOGIN not in json.dumps(refused)


def test_a_bucket_mode_backfile_import_refused_for_auth_expired_prints_no_login_in_its_panel(
    world: World, tmp_path: Path
) -> None:
    in_a_cloud_task(world, tmp_path)
    a_backfile_whose_listing_answers_401(world)

    result = world.invoke("caselist", "backfile-import", "--caselist", BACKFILE, "--execute")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    panel = flattened(result.output)
    assert THE_BACKFILE_LISTING_REFUSED in panel
    assert THE_CURE_IN_THE_CLOUD in panel
    assert THE_LOGIN not in panel


def test_a_mac_backfile_import_refused_for_auth_expired_keeps_its_output_word_for_word(world: World) -> None:
    """In local mode the import lists before it returns its refusals, so the 401 ends it as before."""
    a_backfile_whose_listing_answers_401(world)

    refused = world.run("caselist", "backfile-import", "--caselist", BACKFILE)

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    error = refused["error"]
    assert error["code"] == "CASELIST_AUTH_EXPIRED"
    assert error["message"] == THE_BACKFILE_LISTING_REFUSED + THE_MACS_INSTRUCTION
    assert error.get("hint") is None
