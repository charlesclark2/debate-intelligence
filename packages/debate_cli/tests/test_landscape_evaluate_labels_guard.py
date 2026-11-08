"""`landscape evaluate` refuses a labels file its sidecar does not record, in every mode (`v1-e32-t58`).

The replay, `--breakdown`, `--model-mode record` and `--check-sample` all read the coach's labels, so each is
refused, before the evaluation is built, when the file's SHA-256 is not the one its sidecar records or the
file has no sidecar: a refusal with its own code, exit 1, never an internal error. Every label is invented.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner, Result

import debate_cli.container as container_module
from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode

runner = CliRunner()

INVENTED = b"sample_row,position\n1,invented-da\n2,made-up-cp\n"
NAME = "coach-sample-labelled.csv"
SIDECAR = "coach-sample-labelled.csv.sha256"

MODES = [
    pytest.param((), id="replay"),
    pytest.param(("--breakdown",), id="breakdown"),
    pytest.param(("--model-mode", "record"), id="record"),
    pytest.param(("--check-sample",), id="check-sample"),
]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def built(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """Every evaluation the command builds; building one is reaching past the guard."""
    built: list[bool] = []

    def build(self: container_module.ServiceContainer, **_: Any) -> Any:
        built.append(True)
        raise AssertionError("the evaluation was built for a refused labels file")

    monkeypatch.setattr(container_module.ServiceContainer, "landscape_evaluation", build)
    return built


def evaluate(tmp_path: Path, *mode: str) -> Result:
    rows = tmp_path / "coach-sample.jsonl"
    rows.write_text('{"schema": "local-classifier-sample-1"}\n', encoding="utf-8")
    command = ["--json", "landscape", "evaluate", "--config-dir", str(tmp_path), "--caselist", "hspolicy99"]
    files = ["--sample", str(tmp_path / NAME), "--sample-rows", str(rows)]
    return runner.invoke(create_app(), [*command, *files, *mode])


@pytest.mark.parametrize("mode", MODES)
def test_every_evaluate_mode_refuses_a_changed_labels_file_naming_both_digests(
    tmp_path: Path, built: list[bool], mode: tuple[str, ...]
) -> None:
    changed = INVENTED.replace(b"made-up-cp", b"none")
    (tmp_path / NAME).write_bytes(changed)
    (tmp_path / SIDECAR).write_text(f"{sha256(INVENTED)}  {NAME}\n", encoding="ascii")

    result = evaluate(tmp_path, *mode)

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    error = json.loads(result.stdout)["error"]
    assert error["code"] == "LABELS_FILE_CHANGED"
    assert sha256(changed)[:12] in error["message"] and sha256(INVENTED)[:12] in error["message"]
    assert str(tmp_path / SIDECAR) in error["message"]
    assert "uv run python scripts/relabel_coach_sample.py" in error["message"]
    assert (error["details"]["found"], error["details"]["recorded"]) == (
        sha256(changed)[:12],
        sha256(INVENTED)[:12],
    )
    assert "spreadsheet" in error["hint"]
    assert built == []


@pytest.mark.parametrize("mode", MODES)
def test_every_evaluate_mode_refuses_a_labels_file_with_no_sidecar(
    tmp_path: Path, built: list[bool], mode: tuple[str, ...]
) -> None:
    (tmp_path / NAME).write_bytes(INVENTED)

    result = evaluate(tmp_path, *mode)

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    error = json.loads(result.stdout)["error"]
    assert error["code"] == "LABELS_DIGEST_MISSING"
    assert str(tmp_path / SIDECAR) in error["message"]
    assert "uv run python scripts/record_coach_sample_digest.py --sample" in error["hint"]
    assert built == []


def test_the_labels_refusal_panel_names_the_sidecar_and_the_hint(tmp_path: Path, built: list[bool]) -> None:
    (tmp_path / NAME).write_bytes(INVENTED + b"3,invented-k\n")
    (tmp_path / SIDECAR).write_text(f"{sha256(INVENTED)}  {NAME}\n", encoding="ascii")
    rows = tmp_path / "coach-sample.jsonl"
    rows.write_text('{"schema": "local-classifier-sample-1"}\n', encoding="utf-8")

    result = runner.invoke(
        create_app(),
        ["landscape", "evaluate", "--caselist", "hspolicy99", "--sample", str(tmp_path / NAME)]
        + ["--sample-rows", str(rows), "--check-sample"],
        env={"COLUMNS": "400"},
    )

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    flat = " ".join(result.output.replace("│", " ").split())
    assert "LABELS_FILE_CHANGED" in flat
    assert sha256(INVENTED)[:12] in flat
    assert "spreadsheet" in flat
    assert built == []
