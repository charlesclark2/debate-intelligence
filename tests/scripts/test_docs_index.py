"""`scripts/docs_index.py`: the generator of docs/README.md's document table (v1-e01-t16).

The fixture is a small docs/ tree built in a temporary directory, and its expected table,
`EXPECTED_TABLE`, was written by hand from the documents in `DOCUMENTS` (working agreement 6).
Comparing the renderer with it is a real check; comparing it with its own earlier output would
only prove it is consistent.

The four drift cases (a document added, renamed, moved, deleted) are separate tests on purpose.
An index check that notices only additions is the failure the task exists to end, and one test
covering all four at once would stay green while any three of them broke.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import docs_index  # noqa: E402
import task_helper  # noqa: E402

Capture = pytest.CaptureFixture[str]

BEGIN, END = docs_index.BEGIN, docs_index.END

# Path under docs/ -> content. adr/0001-first-decision.md has no comment, and needs none, because
# adr/ has its own README. The .png and .json files are not documents.
DOCUMENTS: dict[str, str] = {
    "glossary.md": "<!-- docs-index: Terms the other documents use -->\n# Glossary\n",
    "adr/README.md": "<!-- docs-index: Architecture decision records -->\n# ADRs\n",
    "adr/0001-first-decision.md": "# ADR-0001: the first decision\n",
    "process/working-agreements.md": (
        "<!-- docs-index: Project rules: light CI, operator hand-off -->\n# Working agreements\n"
    ),
    "process/task-workflow.md": "<!-- docs-index: `scripts/task`: start → PR → finish -->\n# Task workflow\n",
    "runbooks/restore.md": "<!-- docs-index: Restoring the store from a backup -->\n# Restore\n",
    "guides/store-cli.md": "<!-- docs-index: Using `store sync\\|ls\\|get` -->\n# Store CLI\n",
}
OTHER_FILES = {"architecture/media/diagram.png": b"\x89PNG\r\n", "process/rulesets/dev.json": b"{}\n"}

EXPECTED_TABLE = """\
| Where | What |
|---|---|
| [adr/](adr/README.md) | Architecture decision records |
| [glossary.md](glossary.md) | Terms the other documents use |
| [guides/store-cli.md](guides/store-cli.md) | Using `store sync\\|ls\\|get` |
| [process/task-workflow.md](process/task-workflow.md) | `scripts/task`: start → PR → finish |
| [process/working-agreements.md](process/working-agreements.md) | Project rules: light CI, operator hand-off |
| [runbooks/restore.md](runbooks/restore.md) | Restoring the store from a backup |"""

HAND_WRITTEN_HEAD = "# Documentation index\n\nIntroduction, kept as written.\n\n"
HAND_WRITTEN_TAIL = "\n\nOutside `docs/`: the roadmap.\n"
COMMITTED_INDEX = f"{HAND_WRITTEN_HEAD}{BEGIN}\n\n{EXPECTED_TABLE}\n\n{END}{HAND_WRITTEN_TAIL}"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    for name, text in DOCUMENTS.items():
        (docs / name).parent.mkdir(parents=True, exist_ok=True)
        (docs / name).write_text(text, encoding="utf-8")
    for name, data in OTHER_FILES.items():
        (docs / name).parent.mkdir(parents=True, exist_ok=True)
        (docs / name).write_bytes(data)
    (docs / "README.md").write_text(COMMITTED_INDEX, encoding="utf-8")
    return tmp_path


def index_text(root: Path) -> str:
    return (root / "docs" / "README.md").read_text(encoding="utf-8")


def check(root: Path) -> int:
    return docs_index.main(["--check", "--root", str(root)])


# --------------------------------------------------------------------------------------------
# the rendered table
# --------------------------------------------------------------------------------------------


def test_render_matches_the_hand_written_expectation(root: Path) -> None:
    assert docs_index.render(root) == f"{BEGIN}\n\n{EXPECTED_TABLE}\n\n{END}"


def test_check_passes_on_the_committed_fixture_index(root: Path, capsys: Capture) -> None:
    assert check(root) == 0
    assert capsys.readouterr().out == "docs/README.md is up to date\n"


def test_a_document_inside_a_directory_with_a_readme_gets_no_row_of_its_own(root: Path) -> None:
    rendered = docs_index.render(root)
    assert "0001-first-decision" not in rendered
    assert rendered.count("adr/") == 2  # the label and the link of the one adr/ row


def test_a_readme_in_a_subdirectory_collapses_everything_beneath_it(root: Path) -> None:
    (root / "docs/runbooks/README.md").write_text("<!-- docs-index: Operational procedures -->\n")
    (root / "docs/runbooks/deep").mkdir()
    (root / "docs/runbooks/deep/undescribed.md").write_text("# no comment needed here\n")
    table = docs_index.render(root).splitlines()
    assert "| [runbooks/](runbooks/README.md) | Operational procedures |" in table
    assert not any("restore.md" in line or "undescribed" in line for line in table)


def test_hidden_files_are_not_documents(root: Path) -> None:
    (root / "docs/.drafts").mkdir()
    (root / "docs/.drafts/idea.md").write_text("# no comment\n")
    assert check(root) == 0


# --------------------------------------------------------------------------------------------
# --check catches every kind of drift, each on its own
# --------------------------------------------------------------------------------------------


def test_check_catches_an_added_document(root: Path, capsys: Capture) -> None:
    (root / "docs/runbooks/rotate-keys.md").write_text("<!-- docs-index: Rotating the keys -->\n# Rotate\n")
    assert check(root) == 1
    err = capsys.readouterr().err
    assert "docs/README.md is stale" in err
    assert "+| [runbooks/rotate-keys.md](runbooks/rotate-keys.md) | Rotating the keys |" in err
    assert index_text(root) == COMMITTED_INDEX


def test_check_catches_a_renamed_document(root: Path, capsys: Capture) -> None:
    docs = root / "docs"
    (docs / "process/task-workflow.md").rename(docs / "process/task-lifecycle.md")
    assert check(root) == 1
    err = capsys.readouterr().err
    assert "-| [process/task-workflow.md](process/task-workflow.md) |" in err
    assert "+| [process/task-lifecycle.md](process/task-lifecycle.md) |" in err
    assert index_text(root) == COMMITTED_INDEX


def test_check_catches_a_moved_document(root: Path, capsys: Capture) -> None:
    docs = root / "docs"
    (docs / "runbooks/restore.md").rename(docs / "process/restore.md")
    assert check(root) == 1
    err = capsys.readouterr().err
    assert "-| [runbooks/restore.md](runbooks/restore.md) |" in err
    assert "+| [process/restore.md](process/restore.md) |" in err
    assert index_text(root) == COMMITTED_INDEX


def test_check_catches_a_deleted_document(root: Path, capsys: Capture) -> None:
    (root / "docs/glossary.md").unlink()
    assert check(root) == 1
    err = capsys.readouterr().err
    assert "-| [glossary.md](glossary.md) | Terms the other documents use |" in err
    assert index_text(root) == COMMITTED_INDEX


def test_check_catches_a_changed_description(root: Path) -> None:
    (root / "docs/glossary.md").write_text("<!-- docs-index: Terms, defined -->\n# Glossary\n")
    assert check(root) == 1


def test_check_never_writes_the_index(root: Path) -> None:
    (root / "docs/glossary.md").unlink()
    before = (root / "docs/README.md").stat().st_mtime_ns
    assert check(root) == 1
    assert index_text(root) == COMMITTED_INDEX
    assert (root / "docs/README.md").stat().st_mtime_ns == before


# --------------------------------------------------------------------------------------------
# a document without a usable description fails every mode, naming the file
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("mode", [[], ["--check"], ["--check-descriptions"]])
def test_a_document_without_a_description_fails_naming_the_file(
    root: Path, capsys: Capture, mode: list[str]
) -> None:
    (root / "docs/runbooks/undescribed.md").write_text("# Undescribed\n\nBody.\n")
    assert docs_index.main([*mode, "--root", str(root)]) == 1
    err = capsys.readouterr().err
    assert "docs/runbooks/undescribed.md: the first line must be `<!-- docs-index:" in err
    assert index_text(root) == COMMITTED_INDEX


def test_every_document_without_a_description_is_named_in_one_run(root: Path, capsys: Capture) -> None:
    (root / "docs/one.md").write_text("# One\n")
    (root / "docs/process/two.md").write_text("")
    assert docs_index.main(["--root", str(root)]) == 1
    err = capsys.readouterr().err
    assert "docs/one.md:" in err
    assert "docs/process/two.md:" in err


def test_a_description_below_the_first_line_is_reported_where_it_is(root: Path, capsys: Capture) -> None:
    (root / "docs/late.md").write_text("# Late\n\n<!-- docs-index: Too late -->\n")
    assert docs_index.main(["--root", str(root)]) == 1
    assert "docs/late.md: the first line must be" in (err := capsys.readouterr().err)
    assert "it is on line 3" in err


def test_an_empty_description_fails(root: Path, capsys: Capture) -> None:
    (root / "docs/empty.md").write_text("<!-- docs-index:  -->\n# Empty\n")
    assert docs_index.main(["--root", str(root)]) == 1
    assert "docs/empty.md: the docs-index description is empty" in capsys.readouterr().err


def test_an_unescaped_pipe_fails_and_an_escaped_one_does_not(root: Path, capsys: Capture) -> None:
    (root / "docs/pipes.md").write_text("<!-- docs-index: `a|b` -->\n# Pipes\n")
    assert docs_index.main(["--root", str(root)]) == 1
    assert "docs/pipes.md: write `|` as `\\|`" in capsys.readouterr().err
    (root / "docs/pipes.md").write_text("<!-- docs-index: `a\\|b` -->\n# Pipes\n")
    assert docs_index.main(["--root", str(root)]) == 0


# --------------------------------------------------------------------------------------------
# --check-descriptions: what every pull request into dev runs
# --------------------------------------------------------------------------------------------


def test_check_descriptions_ignores_a_stale_index(root: Path, capsys: Capture) -> None:
    """A task adds a described document and leaves the index alone; that must pass on its PR."""
    (root / "docs/runbooks/rotate-keys.md").write_text("<!-- docs-index: Rotating the keys -->\n")
    assert docs_index.main(["--check-descriptions", "--root", str(root)]) == 0
    assert capsys.readouterr().out == "All 7 indexed documents under docs/ have a description\n"


def test_check_descriptions_needs_no_index_at_all(root: Path) -> None:
    (root / "docs/README.md").unlink()
    assert docs_index.main(["--check-descriptions", "--root", str(root)]) == 0


# --------------------------------------------------------------------------------------------
# rewriting docs/README.md
# --------------------------------------------------------------------------------------------


def test_rewrite_fixes_drift_and_keeps_the_hand_written_text(root: Path, capsys: Capture) -> None:
    (root / "docs/glossary.md").unlink()
    assert docs_index.main(["--root", str(root)]) == 0
    assert capsys.readouterr().out == "docs/README.md updated\n"
    expected_table = "\n".join(line for line in EXPECTED_TABLE.splitlines() if "glossary" not in line)
    assert index_text(root) == f"{HAND_WRITTEN_HEAD}{BEGIN}\n\n{expected_table}\n\n{END}{HAND_WRITTEN_TAIL}"


def test_rewrite_is_idempotent(root: Path, capsys: Capture) -> None:
    (root / "docs/glossary.md").unlink()
    assert docs_index.main(["--root", str(root)]) == 0
    after_first = index_text(root)
    assert docs_index.main(["--root", str(root)]) == 0
    assert capsys.readouterr().out.endswith("docs/README.md is already up to date\n")
    assert index_text(root) == after_first
    assert check(root) == 0


# --------------------------------------------------------------------------------------------
# an index that cannot be regenerated
# --------------------------------------------------------------------------------------------


def test_missing_index_exits_2(root: Path) -> None:
    (root / "docs/README.md").unlink()
    assert docs_index.main(["--root", str(root)]) == 2


@pytest.mark.parametrize("marker", [BEGIN, END])
def test_missing_marker_exits_2(root: Path, capsys: Capture, marker: str) -> None:
    (root / "docs/README.md").write_text(COMMITTED_INDEX.replace(marker, ""))
    assert docs_index.main(["--root", str(root)]) == 2
    assert f"docs/README.md has no {marker} marker" in capsys.readouterr().err


# --------------------------------------------------------------------------------------------
# the real repository
# --------------------------------------------------------------------------------------------


def test_every_document_in_this_repository_has_a_description() -> None:
    """What `--check-descriptions` enforces in CI; freshness of the index is deliberately not
    tested here, because a task PR into dev leaves docs/README.md stale by design."""
    assert docs_index.main(["--check-descriptions", "--root", str(REPO_ROOT)]) == 0


def test_render_is_deterministic_on_the_real_tree() -> None:
    assert docs_index.render(REPO_ROOT) == docs_index.render(REPO_ROOT)


def test_the_agreement_and_the_kickoff_prompt_ask_for_the_same_thing() -> None:
    """ac4: a session is not told one thing by working agreement 3 and another by its prompt."""
    agreement = (REPO_ROOT / "docs/process/working-agreements.md").read_text(encoding="utf-8")
    section = agreement.split("## 3.", 1)[1].split("\n## ", 1)[0]
    for text in (section, task_helper.PROMPT):
        assert "<!-- docs-index:" in text
        assert "v1-e01-t16" in text
        assert "gets a line in the index" not in text
