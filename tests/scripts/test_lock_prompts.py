"""scripts/lock_prompts.py: adds newly released prompt versions to the lock, and never rewrites one.

Run in-process on prompt trees written per test (v1-e05-t04-prompt-registry, ac4).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import lock_prompts  # noqa: E402

SCHEMA = "debate_core.testing.contracts.model_router.ContractPassage"
BODY = "Choose the passage that best supports this tag: {{ tag }}\n"
BODY_SHA256 = "feb58c2ecc3fad96a9727679ca876d7c217a634a3428848fbc51d84cef80cc95"
"""`printf 'Choose the passage that best supports this tag: {{ tag }}\\n' | shasum -a 256`"""


def write_prompt(directory: Path, name: str, *, version: str = "1.0.0", status: str = "released", body: str = BODY) -> None:
    (directory / name).write_text(
        "---\n"
        f"prompt_id: card.select\nversion: {version}\nstatus: {status}\ntask_class: high_volume\n"
        f"output_schema: {SCHEMA}\nowner: v1-e05-model-router\n"
        f"changelog:\n  - version: {version}\n    date: 2026-10-17\n    summary: Written by a test.\n"
        f"---\n{body}",
        encoding="utf-8",
    )


@pytest.fixture
def prompts(tmp_path: Path) -> Path:
    directory = tmp_path / "prompts"
    directory.mkdir()
    (directory / "prompts.lock.json").write_text('{\n  "format": 1,\n  "prompts": {}\n}\n', encoding="utf-8")
    return directory


def lock_entries(prompts: Path) -> dict[str, object]:
    return json.loads((prompts / "prompts.lock.json").read_text(encoding="utf-8"))["prompts"]


def test_check_fails_on_an_unlocked_release_and_writes_nothing(
    prompts: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_prompt(prompts, "select.md")
    before = (prompts / "prompts.lock.json").read_bytes()

    assert lock_prompts.main(["--check", "--prompts", str(prompts)]) == 1

    assert "card.select@1.0.0" in capsys.readouterr().err
    assert (prompts / "prompts.lock.json").read_bytes() == before


def test_locking_adds_the_release_and_check_then_passes(prompts: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_prompt(prompts, "select.md")
    write_prompt(prompts, "select@1.1.0.md", version="1.1.0", status="draft")

    assert lock_prompts.main(["--prompts", str(prompts)]) == 0

    assert "locked card.select@1.0.0" in capsys.readouterr().out
    assert lock_entries(prompts) == {
        "card.select": {"1.0.0": {"body_sha256": BODY_SHA256, "output_schema": SCHEMA, "task_class": "high_volume"}}
    }
    assert lock_prompts.main(["--check", "--prompts", str(prompts)]) == 0
    assert lock_prompts.main(["--prompts", str(prompts)]) == 0
    assert "is up to date" in capsys.readouterr().out


def test_locking_refuses_to_rehash_an_edited_release_and_leaves_the_lock_alone(
    prompts: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_prompt(prompts, "select.md")
    assert lock_prompts.main(["--prompts", str(prompts)]) == 0
    locked = (prompts / "prompts.lock.json").read_bytes()
    write_prompt(prompts, "select.md", body="Choose the best passage for: {{ tag }}\n")
    write_prompt(prompts, "select@1.1.0.md", version="1.1.0")

    assert lock_prompts.main(["--prompts", str(prompts)]) == 1

    assert "card.select@1.0.0" in capsys.readouterr().err
    assert (prompts / "prompts.lock.json").read_bytes() == locked


def test_a_bump_is_locked_beside_the_version_it_replaces(prompts: Path) -> None:
    write_prompt(prompts, "select.md")
    assert lock_prompts.main(["--prompts", str(prompts)]) == 0
    write_prompt(prompts, "select@1.1.0.md", version="1.1.0", body="Choose the best passage for: {{ tag }}\n")

    assert lock_prompts.main(["--prompts", str(prompts)]) == 0

    entries = lock_entries(prompts)["card.select"]
    assert isinstance(entries, dict)
    assert sorted(entries) == ["1.0.0", "1.1.0"]
    assert entries["1.0.0"]["body_sha256"] == BODY_SHA256


def test_a_prompt_tree_that_does_not_load_is_reported_not_raised(
    prompts: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (prompts / "stray.md").write_text("no front matter\n", encoding="utf-8")

    assert lock_prompts.main(["--prompts", str(prompts)]) == 1
    assert "stray.md" in capsys.readouterr().err


def test_the_repository_lock_is_up_to_date() -> None:
    assert lock_prompts.main(["--check"]) == 0
