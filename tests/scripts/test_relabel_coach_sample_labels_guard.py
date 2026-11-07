"""`scripts/relabel_coach_sample.py` reads the labels file through its guard and writes it as a guarded
sitting (`v1-e32-t58`).

The store and the coach are stood in for: the container's evaluation answers each row's side, and the
sitting answers with the changes the test chose. The rules themselves are
`packages/debate_core/tests/application/test_coach_sample_labels_file.py`'s; these tests prove the script goes
through them. Every label is invented.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import relabel_coach_sample as script  # noqa: E402

INVENTED = b"sample_row,position\n1,invented-da\n2,made-up-cp\n"
NAME = "coach-sample-labelled.csv"
SIDECAR = "coach-sample-labelled.csv.sha256"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Sides:
    """The evaluation service's `sample_sides`, answering from the rows of the test's file only."""

    def __init__(self, built: list[str]) -> None:
        self.built = built

    def landscape_evaluation(self, **_: Any) -> Sides:
        self.built.append("evaluation")
        return self

    async def sample_sides(self, *_: Any, **__: Any) -> SimpleNamespace:
        rows = [SimpleNamespace(sample_row=1), SimpleNamespace(sample_row=2)]
        return SimpleNamespace(labelled=rows, sides={1: {"AFF"}, 2: {"NEG"}}, taxonomy=None)


@pytest.fixture
def built(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """What the script built of the container; the sitting answers row 2 with an invented `at:` label."""
    built: list[str] = []
    monkeypatch.setattr(script, "settings_loader", lambda: None)
    monkeypatch.setattr(script, "validating_routing", lambda loader: loader)
    monkeypatch.setattr(script, "ServiceContainer", lambda **_: Sides(built))
    monkeypatch.setattr(script, "shown_rows", lambda *_: {})
    monkeypatch.setattr(script, "run_sitting", lambda *_, **__: {2: "at:invented-da"})
    return built


def sit(tmp_path: Path) -> int:
    rows = tmp_path / "coach-sample.jsonl"
    rows.write_text('{"schema": "local-classifier-sample-1"}\n', encoding="utf-8")
    return script.main(
        [
            "--caselist",
            "hspolicy99",
            "--snapshot",
            "2026-09-15",
            "--sample",
            str(tmp_path / NAME),
            "--sample-rows",
            str(rows),
            "--rows",
            "2",
            "--seed",
            "1",
            "--controls",
            "1",
        ]
    )


def test_the_sitting_refuses_a_changed_labels_file_before_reading_the_store(
    tmp_path: Path, built: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    changed = INVENTED.replace(b"\n", b"\r\n")
    (tmp_path / NAME).write_bytes(changed)
    (tmp_path / SIDECAR).write_text(f"{sha256(INVENTED)}  {NAME}\n", encoding="ascii")

    assert sit(tmp_path) == 1

    error = capsys.readouterr().err
    assert error.startswith("Stopped: the labels file")
    assert sha256(changed)[:12] in error and sha256(INVENTED)[:12] in error
    assert str(tmp_path / SIDECAR) in error and "scripts/relabel_coach_sample.py" in error
    assert built == []
    assert (tmp_path / NAME).read_bytes() == changed
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted([NAME, SIDECAR, "coach-sample.jsonl"])


def test_the_sitting_refuses_a_labels_file_with_no_sidecar_and_gives_the_one_time_step(
    tmp_path: Path, built: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / NAME).write_bytes(INVENTED)

    assert sit(tmp_path) == 1

    error = capsys.readouterr().err
    assert "has no sidecar" in error and "scripts/record_coach_sample_digest.py --sample" in error
    assert built == []
    assert not (tmp_path / SIDECAR).exists()


def test_the_sitting_keeps_a_dated_labels_copy_and_records_the_new_digest(
    tmp_path: Path, built: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / NAME).write_bytes(INVENTED)
    (tmp_path / SIDECAR).write_text(f"{sha256(INVENTED)}  {NAME}\n", encoding="ascii")

    assert sit(tmp_path) == 0

    relabelled = b"sample_row,position\n1,invented-da\n2,at:invented-da\n"
    assert (tmp_path / NAME).read_bytes() == relabelled
    assert (tmp_path / SIDECAR).read_text("ascii") == f"{sha256(relabelled)}  {NAME}\n"
    copies = list(tmp_path.glob("coach-sample-labelled.before-sitting-*.csv"))
    assert len(copies) == 1 and copies[0].read_bytes() == INVENTED
    assert copies[0].name[len("coach-sample-labelled.before-sitting-") :][:-4].replace("-", "").isdigit()
    printed = capsys.readouterr().out.splitlines()
    assert printed[-1] == "Done. Listed: 1 changed, 0 unchanged. Control: 0 changed, 1 unchanged."
    assert f"The file this sitting replaced is kept at {copies[0]}." in printed
    assert built == ["evaluation"]


def test_a_sitting_stopped_by_ctrl_c_writes_no_labels_copy_and_no_sidecar(
    tmp_path: Path, built: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / NAME).write_bytes(INVENTED)
    (tmp_path / SIDECAR).write_text(f"{sha256(INVENTED)}  {NAME}\n", encoding="ascii")

    def interrupted(*_: Any, **__: Any) -> dict[int, str]:
        raise KeyboardInterrupt

    monkeypatch.setattr(script, "run_sitting", interrupted)

    assert sit(tmp_path) == 1

    assert (tmp_path / NAME).read_bytes() == INVENTED
    assert (tmp_path / SIDECAR).read_text("ascii") == f"{sha256(INVENTED)}  {NAME}\n"
    assert not list(tmp_path.glob("*.before-sitting-*"))
