"""What `caselist remove` prints names no path on this machine (`v1-e30-t20`, PM amendment 2026-10-18).

The removal runbook asks the operator to read the plan and keep its output. It printed the inbox
as `DOWNLOAD INBOX (<absolute path>)`, `--json` carried `inbox_directory` as an absolute path, and
the refusal when a pull held the run lock said `it holds <lock path>`; both paths are under the
home directory. As `v1-e34-t16` ruled for `summary_written_to`, `inbox_directory` keeps its key and
its type and is now a path relative to the data directory.

Each test runs the real application and composition root against moto, with the data directory
under :data:`DATA_PROBE` and `HOME` set to a directory under :data:`HOME_PROBE`: `v1-e34-t16`'s
probe, kept apart so that a string built from `Path.home()` is told from one built from the data
directory. It looks for either probe, the test's temporary directory, the user's name and any
absolute path, in stdout and stderr, as text with `--verbose` and as JSON, in every output a
removal has: the dry run, the execution, the run a pull's lock stopped, the re-run, the refusal
without the takedown profile and `caselist unsuppress`. Then in the records the removal wrote, here
and in the bucket.

The weeks are the invented ones from `tests/fixtures/caselist/`; nothing here is real caselist
content (`docs/policies/caselist-data-use.md`). Nothing reaches AWS: moto answers in-process.
"""

from __future__ import annotations

import getpass
import json
import os
import re
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

import boto3
import pytest
from moto import mock_aws
from tests.fixtures.caselist.build_synthetic_archives import (
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    build_snapshot_zips,
)
from tests.fixtures.identity_center_roles import EVERYDAY_ROLE, TAKEDOWN_ROLE, sign_in
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist_sync import LOCK_FILENAME, RunLock

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

runner = CliRunner()

BUCKET = "debate-dev-evidence-remove-probe-moto"
AWS_PROFILE_NAME = "debate-dev-evidence"
REMOVAL_PROFILE = "debate-dev-evidence-removal"
TEAM = f"{SYNTHETIC_CASELIST}/Maple Grove/QX"
REMOVE = ("caselist", "remove", "--team", TEAM, "--request", "RM-2026-01", "--reason", "REQUESTED_BY_TEAM")
NEXT_MONDAY = date(2026, 9, 22)

DATA_PROBE = "Zqxdataprobe"
"""In the path of the data directory, and so of the inbox inside it. Searched for case-insensitively."""

HOME_PROBE = "Zqxhomeprobe"
"""In the path `HOME` is set to, apart from the data directory. Searched for case-insensitively."""

ABSOLUTE_PATH = re.compile(r"(?<![\w.:/~-])(?:~/|/(?:Users|home|private|var|tmp|Volumes|opt|etc)/)")
"""The start of a path on a machine, as `v1-e34-t16`'s probe finds one. Not after a word, a dot, a
colon or a slash, so that a URL's path and the `docs/runbooks/…` a hint cites are not taken for one."""

WIDE = {"COLUMNS": "1000"}
"""Wide enough that Rich wraps nothing, so that a path is never split across two lines."""


@dataclass(frozen=True)
class Probe:
    root: Path
    data_dir: Path
    home: Path

    @property
    def inbox(self) -> Path:
        return self.data_dir / "inbox"

    def found_in(self, text: str) -> list[str]:
        """What of this machine `text` names, by what it is; empty when it names nothing."""
        found = [
            what
            for what, needle in (
                ("the data directory's probe", DATA_PROBE),
                ("the home directory's probe", HOME_PROBE),
                ("the temporary directory", str(self.root)),
                ("the temporary directory, resolved", str(self.root.resolve())),
            )
            if needle.casefold() in text.casefold()
        ]
        user = getpass.getuser()
        if len(user) >= 3 and re.search(rf"(?<![A-Za-z0-9]){re.escape(user)}(?![A-Za-z0-9])", text, re.I):
            found.append("the user's name")
        if match := ABSOLUTE_PATH.search(text):
            around = text[max(match.start() - 60, 0) : match.end() + 60]
            found.append(f"an absolute path at {match.start()}: {around!r}")
        return found


@pytest.fixture
def probe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Probe]:
    """A dev profile naming a moto bucket, its data directory under one probe and `HOME` under the other."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    home = tmp_path / HOME_PROBE / "operator"
    home.mkdir(parents=True)
    data = tmp_path / DATA_PROBE / ".debate-research" / "dev"
    config = tmp_path / "aws-config"
    config.write_text(
        "".join(f"[profile {name}]\nregion = us-east-1\n" for name in (AWS_PROFILE_NAME, REMOVAL_PROFILE)),
        encoding="utf-8",
    )
    credentials = tmp_path / "aws-credentials"
    credentials.write_text("", encoding="utf-8")
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{data}"\n'
        f'[storage.s3]\nbucket = "{BUCKET}"\nregion = "us-east-1"\naws_profile = "{AWS_PROFILE_NAME}"\n'
        # A dev profile would pick the macOS notifier on a Mac; no check may notify (v1-e34-t03).
        '[caselist]\nnotifier = "none"\n'
        f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 1.0\n',
        encoding="utf-8",
    )
    for name, value in {
        "HOME": str(home),
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_EC2_METADATA_DISABLED": "true",
        "AWS_CONFIG_FILE": str(config),
        "AWS_SHARED_CREDENTIALS_FILE": str(credentials),
        "DEBATE_PROFILE_DIR": str(profiles),
        "DEBATE_ENV": "dev",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    assert Path.home() == home
    yield Probe(root=tmp_path, data_dir=data, home=home)


@pytest.fixture
def bucket(probe: Probe) -> Iterator[S3Client]:
    with mock_aws():
        client: S3Client = boto3.client("s3", region_name="us-east-1")  # pyright: ignore[reportUnknownMemberType]
        client.create_bucket(Bucket=BUCKET)
        client.put_bucket_versioning(Bucket=BUCKET, VersioningConfiguration={"Status": "Enabled"})
        # Each profile is the role its name says: a takedown asks before it does anything (v1-e29-t08).
        sign_in(
            probe.root / "aws-credentials", {AWS_PROFILE_NAME: EVERYDAY_ROLE, REMOVAL_PROFILE: TAKEDOWN_ROLE}
        )
        yield client


@pytest.fixture
def published(probe: Probe, bucket: S3Client) -> dict[date, Path]:
    """The three synthetic weeks imported and published, as the dev environment has them."""
    weeks = build_snapshot_zips(probe.root / "downloads")
    for week in SNAPSHOTS:
        imported = invoke(
            "--json", "caselist", "import", str(weeks[week.snapshot]),
            "--caselist", SYNTHETIC_CASELIST, "--snapshot", week.snapshot.isoformat(),
        )  # fmt: skip
        assert imported.exit_code == ExitCode.OK, printed(imported)
    publish = invoke("--json", "caselist", "publish", "--caselist", SYNTHETIC_CASELIST)
    assert publish.exit_code == ExitCode.OK, printed(publish)
    return weeks


def stock_the_inbox(inbox: Path, weeks: dict[date, Path]) -> None:
    """The three weeks a pull downloaded, which the removal deletes, and next Monday's, which it rewrites."""
    inbox.mkdir(parents=True, exist_ok=True)
    for snapshot, archive in weeks.items():
        shutil.copyfile(archive, inbox / f"{SYNTHETIC_CASELIST}-weekly-{snapshot.isoformat()}.zip")
    shutil.copyfile(
        weeks[SNAPSHOTS[-1].snapshot], inbox / f"{SYNTHETIC_CASELIST}-weekly-{NEXT_MONDAY.isoformat()}.zip"
    )


def invoke(*arguments: str) -> Result:
    return runner.invoke(create_app(), list(arguments), env=WIDE)


def printed(result: Result) -> str:
    """Everything the command wrote, stdout and stderr."""
    return f"{result.stdout}\n{result.stderr}"


def envelope_of(result: Result) -> dict[str, Any]:
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected one line of JSON on stdout; got {lines!r}\n{result.stderr}"
    envelope: dict[str, Any] = json.loads(lines[0])
    return envelope


def both(*arguments: str) -> dict[str, Result]:
    """The command as a person reads it, with `--verbose` for the progress lines, and as JSON."""
    return {
        " ".join(arguments): invoke("--verbose", *arguments),
        " ".join(("--json", *arguments)): invoke("--json", *arguments),
    }


def records_left(probe: Probe, client: S3Client) -> dict[str, str]:
    """What the removal wrote beside the list, here and in the bucket: the list, the log and the rest."""
    here = probe.data_dir / "suppression"
    found = {
        f"this machine's {path.relative_to(probe.data_dir)}": path.read_text(encoding="utf-8")
        for path in sorted(here.rglob("*"))
        if path.is_file()
    }
    listed = client.list_objects_v2(Bucket=BUCKET, Prefix="manifests/_suppression/")
    for item in listed.get("Contents", []):
        key = str(item.get("Key"))
        found[f"the bucket's {key}"] = client.get_object(Bucket=BUCKET, Key=key)["Body"].read().decode()
    return found


def assert_names_nothing_of_this_machine(texts: dict[str, str], probe: Probe) -> None:
    named = {where: found for where, text in texts.items() if (found := probe.found_in(text))}
    assert not named, f"a path on this machine reached {json.dumps(named, indent=2)}"


def test_the_probe_finds_a_path_into_the_data_directory_or_the_home_directory(tmp_path: Path) -> None:
    """Without this a probe could pass by looking for a string that was never there."""
    probe = Probe(root=tmp_path, data_dir=tmp_path / DATA_PROBE / "dev", home=tmp_path / HOME_PROBE)
    assert probe.found_in(f"DOWNLOAD INBOX ({probe.data_dir / 'inbox'}): nothing in it holds a removed file.")
    assert probe.found_in(
        f"a caselist pull is running (it holds {probe.home}/.debate-research/dev/caselist-sync.lock)"
    )
    assert probe.found_in("it holds ~/.debate-research/dev/caselist-sync.lock")
    assert not probe.found_in(
        "DOWNLOAD INBOX (inbox in the data directory): nothing in it holds a removed file."
    )
    assert not probe.found_in('see docs/runbooks/caselist-removal.md, "A probe a preflight left behind"')


# ------------------------------------------------------------------------------------------------
# The dry run, the run a pull's lock stops, the execution and the re-run
# ------------------------------------------------------------------------------------------------


def test_a_dry_run_before_any_pull_names_the_inbox_by_its_place_in_the_data_directory(
    probe: Probe, published: dict[date, Path]
) -> None:
    """An environment that has never pulled has no inbox: the plan says so, and names it relatively."""
    outputs = both(*REMOVE)

    for result in outputs.values():
        assert result.exit_code == ExitCode.OK, printed(result)
    assert_names_nothing_of_this_machine({name: printed(result) for name, result in outputs.items()}, probe)
    text, as_json = outputs.values()
    assert (
        "DOWNLOAD INBOX (inbox in the data directory): does not exist, so there is nothing to check or "
        "change (an environment that has never pulled has none)."
    ) in text.stdout.splitlines()
    data = envelope_of(as_json)["data"]
    assert (data["inbox_directory"], data["inbox_exists"]) == ("inbox", False)


def test_no_output_of_a_removal_names_a_path_on_this_machine(
    probe: Probe, published: dict[date, Path], bucket: S3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The dry run, the refusal without the takedown profile, two runs a pull's lock stops, the
    execution that finishes, the re-run planned and executed, and the records all of them wrote."""
    stock_the_inbox(probe.inbox, published)
    outputs = both(*REMOVE)
    outputs |= {f"{name}, no takedown profile": result for name, result in both(*REMOVE, "--execute").items()}
    monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", REMOVAL_PROFILE)
    with RunLock(probe.data_dir / LOCK_FILENAME):
        stopped = both(*REMOVE, "--execute")
    finished = both(*REMOVE, "--execute")
    rerun = both(*REMOVE)
    rerun_executed = both(*REMOVE, "--execute")

    for result in outputs.values():
        assert result.exit_code in (ExitCode.OK, ExitCode.DOMAIN_FAILURE), printed(result)
    for result in stopped.values():
        assert result.exit_code == ExitCode.DOMAIN_FAILURE, printed(result)
    for result in (*finished.values(), *rerun.values(), *rerun_executed.values()):
        assert result.exit_code == ExitCode.OK, printed(result)
    every_output = {
        **{name: printed(result) for name, result in outputs.items()},
        **{f"{name}, under a pull's lock": printed(result) for name, result in stopped.items()},
        **{f"{name}, finishing": printed(result) for name, result in finished.items()},
        **{f"{name}, re-run": printed(result) for name, result in rerun.items()},
        **{f"{name}, re-run": printed(result) for name, result in rerun_executed.items()},
    }
    assert_names_nothing_of_this_machine({**every_output, **records_left(probe, bucket)}, probe)

    dry_run, dry_run_json = outputs[" ".join(REMOVE)], outputs[" ".join(("--json", *REMOVE))]
    assert any(
        line.startswith("DOWNLOAD INBOX (inbox in the data directory): 4 file(s) hold removed files.")
        for line in dry_run.stdout.splitlines()
    ), dry_run.stdout
    assert envelope_of(dry_run_json)["data"]["inbox_directory"] == "inbox"
    _, stopped_json = stopped.values()
    message = envelope_of(stopped_json)["error"]["message"]
    assert (
        "a caselist pull is running (it holds the run lock, caselist-sync.lock in the data directory), so "
        "the inbox was left as it was"
    ) in message, message
    assert not (probe.inbox / f"{SYNTHETIC_CASELIST}-weekly-{SNAPSHOTS[0].snapshot.isoformat()}.zip").exists()


def test_an_inbox_a_profile_puts_outside_the_data_directory_is_named_by_its_setting(
    probe: Probe, published: dict[date, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`caselist.inbox_dir` may name any directory, here one under `HOME`: no path into the data
    directory names it, so the plan names the setting that does."""
    elsewhere = probe.home / "Downloads" / "caselist-inbox"
    stock_the_inbox(elsewhere, published)
    monkeypatch.setenv("DEBATE_CASELIST__INBOX_DIR", str(elsewhere))

    outputs = both(*REMOVE)

    for result in outputs.values():
        assert result.exit_code == ExitCode.OK, printed(result)
    assert_names_nothing_of_this_machine({name: printed(result) for name, result in outputs.items()}, probe)
    text, as_json = outputs.values()
    assert any(
        line.startswith(
            "DOWNLOAD INBOX (the directory caselist.inbox_dir names): 4 file(s) hold removed files."
        )
        for line in text.stdout.splitlines()
    ), text.stdout
    data = envelope_of(as_json)["data"]
    assert (data["inbox_directory"], data["inbox_exists"]) == ("caselist.inbox_dir", True)


def test_unsuppress_names_no_path_on_this_machine(
    probe: Probe, published: dict[date, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other command of the module: its dry run and its execution, after a removal."""
    monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", REMOVAL_PROFILE)
    removed = envelope_of(invoke("--json", *REMOVE, "--execute"))
    sha256 = json.loads(removed["data"]["log_entry"])["removed_sha256"][0]
    lift = (
        "caselist",
        "unsuppress",
        "--sha256",
        sha256,
        "--reason",
        "REMOVED_IN_ERROR",
        "--request",
        "RM-2026-01",
    )

    outputs = both(*lift)
    outputs[" ".join((*lift, "--execute"))] = invoke("--verbose", *lift, "--execute")

    for result in outputs.values():
        assert result.exit_code == ExitCode.OK, printed(result)
    assert_names_nothing_of_this_machine({name: printed(result) for name, result in outputs.items()}, probe)
