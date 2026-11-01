"""`debate-research landscape cassettes`, through the real composition root (`v1-e32-t34`).

The cassette directory is written by :class:`~debate_core.integrations.models.record_replay.CassetteDirectory`
itself, under `<data dir>/landscape/model-cassettes/` as the landscape model stage files them, so the
files are the ones a run leaves; no router is built and no model is called. Every caselist is a
synthetic slug, and every prompt variable and answer is invented. The counts are distinct (3 sole, 2
shared, 1 unattributed, 4 of the other caselist only), so a count reported under another's name shows.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Final

import pytest
from pydantic import BaseModel
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.container import ServiceContainer
from debate_cli.exit_codes import ExitCode
from debate_core.application.cassette_filing import filed_under
from debate_core.application.settings import load_settings
from debate_core.domain.model_contracts import ModelPrompt, ModelRequest, TaskClass
from debate_core.integrations.models import factory
from debate_core.integrations.models.model_mode import ModelMode
from debate_core.integrations.models.record_replay import CassetteDirectory

runner = CliRunner()

PURGED: Final = "synthld21"
KEPT: Final = "synthld26"
PROMPT_ID: Final = "example.sort-card"
CARD_TEXT: Final = "QuotedCardText"
"""In every cassette's prompt variables: what a cassette's content would print if it were printed."""
ANSWER_TEXT: Final = "RecordedAnswer"
"""In every cassette's response."""
SCHOOLISH: Final = "Maple-Grove-MG"
"""A misfiled file's name, as a school and team code would read."""
SOLE: Final = ("first", "second", "third")
SHARED: Final = ("fourth", "fifth")
UNATTRIBUTED: Final = ("sixth",)
OTHER: Final = ("seventh", "eighth", "ninth", "tenth")
COUNTS: Final = {"sole": 3, "shared": 2, "unattributed": 1, "other_caselists": 4}
"""Counted by hand from the four tuples above."""
DIRECTORY: Final = "<data dir>/landscape/model-cassettes/"


class Sorted(BaseModel):
    position: str


@pytest.fixture(autouse=True)
def data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """Dev and prod profiles over one data directory; nothing here reaches a bucket."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    data = tmp_path / "data"
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    for environment in ("dev", "prod"):
        (profiles / f"{environment}.toml").write_text(
            f'[storage]\ndata_dir = "{data}"\n'
            f'[storage.s3]\nbucket = "debate-{environment}-evidence-test"\nregion = "us-east-1"\n'
            f'aws_profile = "debate-{environment}-evidence"\n'
            f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 1.0\n',
            encoding="utf-8",
        )
    (profiles / "test.toml").write_text(
        f'allow_network = false\n[providers]\nenabled = []\n[storage]\ndata_dir = "{data}"\n'
        f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 0.0\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DEBATE_PROFILE_DIR", str(profiles))
    monkeypatch.setenv("DEBATE_ENV", "dev")
    yield data


def cassette_root(data_dir: Path) -> Path:
    return data_dir / "landscape" / "model-cassettes"


def request(card: str) -> ModelRequest:
    prompt = ModelPrompt(
        prompt_id=PROMPT_ID, prompt_version="1.0.0", variables={"items": f"{CARD_TEXT} the {card} card"}
    )
    return ModelRequest.build(TaskClass.HIGH_VOLUME, prompt, Sorted)


def write(data_dir: Path, card: str, *caselists: str) -> Path:
    """The cassette of `card`, written once for each of `caselists` (once, unattributed, for none)."""
    directory = CassetteDirectory(cassette_root(data_dir))
    response = {"output": {"position": ANSWER_TEXT}, "model_id": "recorded-model"}
    if not caselists:
        return directory.write_structured(request(card), response)
    path = directory.structured_path(request(card))
    for caselist in caselists:
        with filed_under(caselist):
            path = directory.write_structured(request(card), response)
    return path


@pytest.fixture
def cassettes(data_dir: Path) -> dict[str, list[Path]]:
    return {
        "sole": [write(data_dir, card, PURGED) for card in SOLE],
        "shared": [write(data_dir, card, PURGED, KEPT) for card in SHARED],
        "unattributed": [write(data_dir, card) for card in UNATTRIBUTED],
        "other": [write(data_dir, card, KEPT) for card in OTHER],
    }


def invoke(*arguments: str) -> Result:
    return runner.invoke(create_app(), ["landscape", "cassettes", *arguments])


def envelope_of(result: Result) -> dict[str, Any]:
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected one line of JSON on stdout, got {lines!r}"
    parsed = json.loads(lines[0])
    assert isinstance(parsed, dict)
    return parsed


def flat(text: str) -> str:
    return " ".join(text.split())


def tree(data_dir: Path) -> dict[str, bytes]:
    root = cassette_root(data_dir)
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def confirmation_of(*arguments: str) -> str:
    dry_run = envelope_of(invoke("--caselist", PURGED, "--json", *arguments))
    code = dry_run["data"].get("confirmation")
    assert isinstance(code, str) and re.fullmatch(r"[0-9a-f]{12}", code), dry_run
    return code


# ------------------------------------------------------------------------------------------------
# The dry run: counts, and nothing changed
# ------------------------------------------------------------------------------------------------


def test_the_dry_run_counts_sole_shared_and_unattributed_cassettes_and_changes_nothing(
    data_dir: Path, cassettes: dict[str, list[Path]]
) -> None:
    before = tree(data_dir)

    result = invoke("--caselist", PURGED, "--json")

    assert result.exit_code == ExitCode.OK, result.output
    data = envelope_of(result)["data"]
    assert data.get("cassettes") == COUNTS
    assert data["caselist"] == PURGED
    assert data["environment"] == "dev"
    assert data["directory"] == DIRECTORY
    assert data["directory_found"] is True
    assert data["deleted"] is False
    assert re.fullmatch(r"[0-9a-f]{12}", data["confirmation"])
    assert tree(data_dir) == before


def test_the_dry_run_says_what_a_delete_would_do_to_each_kind_and_how_to_confirm_it(
    data_dir: Path, cassettes: dict[str, list[Path]]
) -> None:
    code = confirmation_of()

    result = invoke("--caselist", PURGED)

    assert result.exit_code == ExitCode.OK, result.output
    text = flat(result.stdout)
    assert f"Model cassettes of {PURGED} in dev, in the landscape model stage's directory, {DIRECTORY}" in text
    assert "3 this caselist's alone: a delete removes them." in text
    assert "2 shared with another caselist: kept, losing only this caselist's name" in text
    assert "1 unattributed, naming no caselist" in text
    assert "4 of other caselists only: untouched." in text
    assert f"Dry run: nothing was changed. To carry it out, add: --delete --confirm {code}" in text


def test_the_counts_follow_the_caselist_asked_about(data_dir: Path, cassettes: dict[str, list[Path]]) -> None:
    data = envelope_of(invoke("--caselist", KEPT, "--json"))["data"]

    assert data.get("cassettes") == {"sole": 4, "shared": 2, "unattributed": 1, "other_caselists": 3}


def test_where_the_model_stage_recorded_nothing_the_command_says_so_and_creates_nothing(data_dir: Path) -> None:
    listed = invoke("--caselist", PURGED, "--json")
    human = invoke("--caselist", PURGED)

    assert listed.exit_code == ExitCode.OK and human.exit_code == ExitCode.OK, human.output
    data = envelope_of(listed)["data"]
    assert data.get("directory_found") is False
    assert data["cassettes"] == {"sole": 0, "shared": 0, "unattributed": 0, "other_caselists": 0}
    assert (
        f"No model cassettes in dev: the landscape model stage has recorded none on this machine "
        f"(no {DIRECTORY} directory)." in flat(human.stdout)
    )
    deleted = invoke("--caselist", PURGED, "--delete", "--confirm", data["confirmation"], "--json")
    assert deleted.exit_code == ExitCode.OK, deleted.output
    assert envelope_of(deleted)["data"]["deleted"] is True
    assert not cassette_root(data_dir).exists()
    assert not data_dir.exists() or list(data_dir.rglob("*.json")) == []


# ------------------------------------------------------------------------------------------------
# The delete: sole-owned only, behind the dry run's code
# ------------------------------------------------------------------------------------------------


def test_the_delete_removes_only_the_caselists_own_and_keeps_shared_and_unattributed_ones(
    data_dir: Path, cassettes: dict[str, list[Path]]
) -> None:
    kept_whole = {path: path.read_bytes() for path in (*cassettes["unattributed"], *cassettes["other"])}
    shared_before = {path: json.loads(path.read_text(encoding="utf-8")) for path in cassettes["shared"]}
    code = confirmation_of()

    result = invoke("--caselist", PURGED, "--delete", "--confirm", code, "--json")

    assert result.exit_code == ExitCode.OK, result.output
    data = envelope_of(result)["data"]
    assert data["deleted"] is True
    assert data["cassettes"] == COUNTS
    assert [path.exists() for path in cassettes["sole"]] == [False, False, False]
    for path, before in shared_before.items():
        after = json.loads(path.read_text(encoding="utf-8"))
        assert after["caselists"] == [KEPT]
        assert {**after, "caselists": before["caselists"]} == before
    assert {path: path.read_bytes() for path in kept_whole} == kept_whole
    again = envelope_of(invoke("--caselist", PURGED, "--json"))["data"]["cassettes"]
    assert again == {"sole": 0, "shared": 0, "unattributed": 1, "other_caselists": 6}


def test_the_delete_says_how_many_it_deleted_and_how_many_it_kept_and_why(
    data_dir: Path, cassettes: dict[str, list[Path]]
) -> None:
    code = confirmation_of()

    result = invoke("--caselist", PURGED, "--delete", "--confirm", code)

    assert result.exit_code == ExitCode.OK, result.output
    text = flat(result.stdout)
    assert "Deleted 3 cassette(s) only this caselist named." in text
    assert (
        "Kept 2 shared cassette(s), taking only this caselist's name off: another caselist still replays them."
        in text
    )
    assert "Kept 1 unattributed cassette(s): it names no caselist, so no caselist's delete removes it" in text
    assert "4 of other caselists only: untouched." in text


@pytest.mark.parametrize("confirm", [[], ["--confirm", "0" * 12], ["--confirm", ""]])
def test_a_delete_without_the_dry_runs_code_changes_nothing(
    data_dir: Path, cassettes: dict[str, list[Path]], confirm: list[str]
) -> None:
    before = tree(data_dir)

    result = invoke("--caselist", PURGED, "--delete", *confirm, "--json")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    error = envelope_of(result)["error"]
    assert error["code"] == "CONFIRMATION_MISMATCH"
    assert error["details"]["cassettes"] == COUNTS
    assert tree(data_dir) == before


def test_a_code_from_before_the_directory_changed_deletes_nothing(
    data_dir: Path, cassettes: dict[str, list[Path]]
) -> None:
    code = confirmation_of()
    write(data_dir, "eleventh", PURGED)
    before = tree(data_dir)

    result = invoke("--caselist", PURGED, "--delete", "--confirm", code, "--json")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    assert envelope_of(result)["error"]["code"] == "CONFIRMATION_MISMATCH"
    assert tree(data_dir) == before


def test_a_code_from_another_caselists_dry_run_deletes_nothing(
    data_dir: Path, cassettes: dict[str, list[Path]]
) -> None:
    code = envelope_of(invoke("--caselist", KEPT, "--json"))["data"].get("confirmation", "")
    before = tree(data_dir)

    result = invoke("--caselist", PURGED, "--delete", "--confirm", code, "--json")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    assert tree(data_dir) == before


def test_a_delete_in_prod_also_needs_confirm_prod(
    data_dir: Path, cassettes: dict[str, list[Path]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_ENV", "prod")
    code = confirmation_of()
    before = tree(data_dir)

    refused = invoke("--caselist", PURGED, "--delete", "--confirm", code, "--json")

    assert refused.exit_code == ExitCode.DOMAIN_FAILURE, refused.output
    assert envelope_of(refused)["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert tree(data_dir) == before
    done = invoke("--caselist", PURGED, "--delete", "--confirm", code, "--confirm-prod", "--json")
    assert done.exit_code == ExitCode.OK, done.output
    assert [path.exists() for path in cassettes["sole"]] == [False, False, False]


# ------------------------------------------------------------------------------------------------
# What the command never prints: a cassette's content, a path, a cassette's name, a school
# ------------------------------------------------------------------------------------------------


def logged(caplog: pytest.LogCaptureFixture) -> str:
    """Every record's message and the extras it was given, as text."""
    standard = set(vars(logging.makeLogRecord({})))
    return "\n".join(
        record.getMessage() + repr({k: v for k, v in vars(record).items() if k not in standard})
        for record in caplog.records
    )


def assert_names_nothing(text: str, data_dir: Path, cassettes: dict[str, list[Path]]) -> None:
    assert CARD_TEXT not in text and ANSWER_TEXT not in text, "a cassette's content was printed"
    assert str(data_dir) not in text and str(data_dir.parent) not in text, "a path was printed"
    for path in (path for paths in cassettes.values() for path in paths):
        assert path.stem not in text and path.stem[:12] not in text, "a cassette's name was printed"
    assert PROMPT_ID not in text


@pytest.mark.parametrize("json_flag", [[], ["--json"]])
def test_no_run_prints_or_logs_a_cassettes_content_its_name_or_a_path(
    data_dir: Path,
    cassettes: dict[str, list[Path]],
    caplog: pytest.LogCaptureFixture,
    json_flag: list[str],
) -> None:
    caplog.set_level(logging.DEBUG)
    code = confirmation_of()

    runs = [
        invoke("--caselist", PURGED, *json_flag),
        invoke("--caselist", PURGED, "--delete", *json_flag),
        invoke("--caselist", PURGED, "--delete", "--confirm", code, *json_flag),
    ]

    assert [run.exit_code for run in runs] == [ExitCode.OK, ExitCode.DOMAIN_FAILURE, ExitCode.OK]
    for run in runs:
        assert_names_nothing(run.stdout + run.stderr, data_dir, cassettes)
    assert_names_nothing(logged(caplog), data_dir, cassettes)


def test_an_unreadable_file_stops_the_command_names_no_file_and_changes_nothing(
    data_dir: Path, cassettes: dict[str, list[Path]]
) -> None:
    (cassette_root(data_dir) / PROMPT_ID / f"{SCHOOLISH}.json").write_text("{}", encoding="utf-8")
    before = tree(data_dir)

    for arguments in (["--json"], [], ["--delete", "--confirm", "0" * 12, "--json"]):
        result = invoke("--caselist", PURGED, *arguments)

        assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
        assert SCHOOLISH not in result.output and "Maple" not in result.output
        assert_names_nothing(result.output, data_dir, cassettes)
        if "--json" in arguments:
            assert envelope_of(result)["error"]["code"] == "CASSETTE_UNREADABLE"
    assert tree(data_dir) == before


@pytest.mark.parametrize("value", ["../synthld21", "Maple Grove", "synthld21/x"])
def test_a_caselist_that_is_no_slug_is_refused_without_being_echoed(
    data_dir: Path, cassettes: dict[str, list[Path]], value: str
) -> None:
    before = tree(data_dir)

    result = invoke("--caselist", value, "--delete", "--confirm", "0" * 12, "--json")

    assert result.exit_code == ExitCode.USAGE_ERROR, result.output
    assert envelope_of(result)["error"]["code"] == "NOT_A_CASELIST_SLUG"
    assert value not in result.output
    assert tree(data_dir) == before


class _RouterBuilt(Exception):
    pass


def test_the_command_reads_the_directory_the_model_stage_records_to(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The container hands the command and the model stage one directory, from `storage.data_dir`."""
    recorded_to: list[Path] = []

    def build_model_router(*_args: object, cassette_dir: Path, **_kwargs: object) -> None:
        recorded_to.append(cassette_dir)
        raise _RouterBuilt

    monkeypatch.setattr(factory, "build_model_router", build_model_router)
    container = ServiceContainer(settings_loader=load_settings)

    with pytest.raises(_RouterBuilt):
        container.landscape_model_stage(ModelMode.REPLAY, 1)
    assert recorded_to == [cassette_root(data_dir)]
    assert container.landscape_cassettes().root == cassette_root(data_dir)
