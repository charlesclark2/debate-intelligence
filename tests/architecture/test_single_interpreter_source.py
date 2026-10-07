"""The supported Python is stated once: `debate_core`'s `requires-python` (`v1-e01-t14` ac4).

It is one decision because the evidence normalizer pins a Unicode database, and only some Pythons
ship it (`docs/evidence/normalization.md`). The installer reads the bound from the built wheel's
`Requires-Python`, `doctor` checks the database the build runs on, and every other mention of a
Python version either derives from the declaration or points at it. A second copy is a constant that
nobody will remember to update, which is how `install_channel.sh`'s old `PYTHON_VERSION` came about.

This test reads every tracked file and fails on a Python version anywhere else. What may still
name one:

* `debate_core`'s declaration, and every other workspace pyproject's `requires-python` when it
  **equals** it exactly. A TOML file cannot point at another file, so the copies are held equal
  here and count as derived.
* `.python-version` (which interpreter a checkout's `uv sync` uses), the CI matrix (a
  `python-version:` key in a workflow; today the workflows install from `.python-version`), and
  `uv.lock`, which uv writes.
* Records of what was decided: session reports, plan specs and the roadmap generated from them,
  and ADR-0001, a decision record that is not rewritten.
* Lockfiles of other ecosystems, whose `3.x` versions are JavaScript packages.
* The lines in :data:`EXEMPT_LINES`, each with its reason. An entry that matches nothing fails the
  test, so the list cannot keep a line alive after it is gone, and a changed line is a new line.
"""

from __future__ import annotations

import re
import subprocess
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DECLARATION = Path("packages/debate_core/pyproject.toml")

# A Python version: `3.9` to `3.19` (with or without a patch number, after `python`, `>=` or a
# space), or a tag such as `py312`/`cp313`. Not `13.12` or `0.3.12`, which are other versions.
PYTHON_VERSION = re.compile(
    r"(?<![\d.])3\.(?:[89]|1\d)(?!\d)"
    r"|(?<![A-Za-z0-9])(?:cp|py)3(?:[89]|1\d)(?!\d)",
    re.IGNORECASE,
)

PERMITTED_FILES = {
    ".python-version": "the interpreter a checkout's `uv sync` uses",
    "uv.lock": "written by uv from the requires-python lines",
    "ROADMAP.md": "generated from the plan specs",
    "tests/architecture/test_single_interpreter_source.py": "this test, which quotes the lines it exempts",
}
PERMITTED_DIRECTORIES = {
    "docs/session-reports/": "records of what each task found and decided",
    "plan_specs/": "the specs, which quote what they change",
}
OTHER_ECOSYSTEM_LOCKFILES = {"pnpm-lock.yaml", "package-lock.json", "yarn.lock"}
CI_MATRIX = re.compile(r"^\s*(?:-\s*)?python-version\s*:")

EXEMPT_LINES: dict[tuple[str, str], str] = {
    (
        "docs/adr/0001-python-domain-core.md",
        "3.12+ and depends only on the standard library, Pydantic, and other pure-Python domain",
    ): "ADR-0001 as decided; decision records are not rewritten",
    (
        "docs/evidence/normalization.md",
        "**v1 is pinned to Unicode 15.0.0**, the database of every Python 3.12 release. The pin is",
    ): "which CPython ships the pinned database: the fact the bound rests on, not a statement of support",
    (
        "docs/evidence/normalization.md",
        "Both tables were produced from Python 3.12's `unicodedata` (Unicode 15.0.0) and are checked",
    ): "where the policy's appendix tables came from",
    (
        "packages/debate_core/tests/evidence/test_normalization.py",
        'UNICODE_VERSION_OF_PYTHON = {"3.12": "15.0.0", "3.13": "15.1.0", "3.14": "16.0.0"}',
    ): "the hand-written CPython-to-Unicode table that ties the bound to the pin (v1-e03-t01)",
    (
        "packages/debate_cli/README.md",
        '"data": {"cli_version": "0.1.0", "python_version": "3.12.7"}, "error": null}',
    ): "a sample `--json` envelope",
    (
        "packages/debate_cli/tests/test_output.py",
        'rows=(("Python", "3.12.7"), ("Settings loaded", "no")),',
    ): "sample data for a rendering test",
    (
        "packages/debate_cli/tests/test_output.py",
        'captured.output.success("doctor", {"python_version": "3.12.7"}, display=DOCTOR_ROWS)',
    ): "sample data for a rendering test",
    (
        "packages/debate_cli/tests/test_output.py",
        'assert "3.12.7" in captured.out',
    ): "sample data for a rendering test",
    (
        "packages/debate_cli/tests/test_output.py",
        'assert envelope["data"] == {"python_version": "3.12.7"}',
    ): "sample data for a rendering test",
    # PEP 723 headers: each standalone script's own minimum, for the runners' system python3 that
    # launches some of them. Not the tool's interpreter; their values are left as they are.
    ("scripts/check_links.py", '# requires-python = ">=3.11"'): "PEP 723: the script's own minimum",
    (
        "scripts/check_promotion_source.py",
        '# requires-python = ">=3.11"',
    ): "PEP 723: the script's own minimum",
    ("scripts/check_thin_handlers.py", '# requires-python = ">=3.12"'): "PEP 723: the script's own minimum",
    ("scripts/spec_index.py", '# requires-python = ">=3.11"'): "PEP 723: the script's own minimum",
    ("scripts/task_helper.py", '# requires-python = ">=3.11"'): "PEP 723: the script's own minimum",
    ("scripts/validate_dev.py", '# requires-python = ">=3.11"'): "PEP 723: the script's own minimum",
    ("scripts/validate_specs.py", '# requires-python = ">=3.11"'): "PEP 723: the script's own minimum",
}


@dataclass(frozen=True)
class Mention:
    path: str
    line_number: int
    line: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line_number}: {self.line}"


def declared_requires_python(root: Path) -> str:
    return tomllib.loads((root / DECLARATION).read_text(encoding="utf-8"))["project"]["requires-python"]


def workspace_pyprojects(root: Path) -> list[Path]:
    """The root pyproject and every workspace member's, as the root's `[tool.uv.workspace]` lists them."""
    root_pyproject = root / "pyproject.toml"
    members = tomllib.loads(root_pyproject.read_text(encoding="utf-8"))["tool"]["uv"]["workspace"]["members"]
    found = [root_pyproject]
    for pattern in members:
        found.extend(
            sorted(
                path / "pyproject.toml" for path in root.glob(pattern) if (path / "pyproject.toml").is_file()
            )
        )
    return found


def tracked_files(root: Path) -> list[str]:
    listing = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True).stdout
    return [name for name in listing.decode().split("\0") if name]


def is_permitted_file(path: str) -> bool:
    return (
        path in PERMITTED_FILES
        or path.startswith(tuple(PERMITTED_DIRECTORIES))
        or Path(path).name in OTHER_ECOSYSTEM_LOCKFILES
    )


def is_derived(path: str, line: str, declared: str, pyprojects: set[str]) -> bool:
    """A workspace pyproject's requires-python line equal to the declaration, or a CI matrix key."""
    if path in pyprojects and line == f'requires-python = "{declared}"':
        return True
    return path.startswith(".github/workflows/") and CI_MATRIX.match(line) is not None


def mentions(root: Path, paths: Iterable[str]) -> list[Mention]:
    """Every line in `paths` naming a Python version that is neither permitted nor derived."""
    declared = declared_requires_python(root)
    pyprojects = {str(path.relative_to(root)) for path in workspace_pyprojects(root)}
    found: list[Mention] = []
    for path in paths:
        if is_permitted_file(path):
            continue
        try:
            text = (root / path).read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue
        for number, raw in enumerate(text.splitlines(), start=1):
            line = raw.strip()
            if PYTHON_VERSION.search(line) and not is_derived(path, line, declared, pyprojects):
                found.append(Mention(path, number, line))
    return found


# ---------------------------------------------------------------------------------------------
# The repository
# ---------------------------------------------------------------------------------------------


def test_the_declaration_is_where_this_test_looks_for_it() -> None:
    assert re.fullmatch(r"[0-9.,<>=!~ ]+", declared_requires_python(REPO_ROOT))
    assert PYTHON_VERSION.search(declared_requires_python(REPO_ROOT))


def test_every_workspace_requires_python_equals_debate_cores_exactly() -> None:
    declared = declared_requires_python(REPO_ROOT)
    differing = {
        str(path.relative_to(REPO_ROOT)): tomllib.loads(path.read_text(encoding="utf-8"))["project"].get(
            "requires-python"
        )
        for path in workspace_pyprojects(REPO_ROOT)
        if tomllib.loads(path.read_text(encoding="utf-8"))["project"].get("requires-python") != declared
    }

    assert len(workspace_pyprojects(REPO_ROOT)) >= 5
    assert differing == {}, (
        f"every workspace requires-python must equal {DECLARATION}'s {declared!r}, the one statement of "
        f"the supported interpreter: {differing}"
    )


def test_no_python_version_is_named_outside_the_one_declaration() -> None:
    found = mentions(REPO_ROOT, tracked_files(REPO_ROOT))

    unexplained = [mention for mention in found if (mention.path, mention.line) not in EXEMPT_LINES]
    assert unexplained == [], (
        f"a Python version is stated outside {DECLARATION}'s requires-python. Point at that declaration "
        "(or read it, as scripts/install_channel.sh reads the wheel's Requires-Python) instead:\n"
        + "\n".join(str(mention) for mention in unexplained)
    )


def test_every_exemption_still_matches_a_line() -> None:
    found = {(mention.path, mention.line) for mention in mentions(REPO_ROOT, tracked_files(REPO_ROOT))}

    stale = [f"{path}: {line}" for path, line in EXEMPT_LINES if (path, line) not in found]
    assert stale == [], "these exemptions match nothing any more; remove them:\n" + "\n".join(stale)


# ---------------------------------------------------------------------------------------------
# The scanner finds what it is for (versions built here, so this file states none)
# ---------------------------------------------------------------------------------------------

MINOR = 12
NEXT = MINOR + 1


@pytest.mark.parametrize(
    "line",
    [
        f"PYTHON_VERSION=3.{MINOR}",
        f'uv tool install --python "3.{NEXT}" debate-cli',
        f"Python 3.{MINOR}+ is required.",
        f"/opt/homebrew/bin/python3.{NEXT}",
        f'requires-python = ">=3.{MINOR}"',
        f'target-version = "py3{MINOR}"',
        f"a cp3{NEXT}-none-any wheel",
        f"FROM python:3.{MINOR}.7-slim",
        f"Python 3.{MINOR - 3} is the floor",
    ],
)
def test_the_scanner_finds_a_python_version(line: str) -> None:
    assert PYTHON_VERSION.search(line)


@pytest.mark.parametrize(
    "line",
    [
        f"boto3 1.43.{MINOR}",
        f"Unicode 1{MINOR // 4}.0.0",
        f"lxml 6.1.3 and 0.3.{MINOR}",
        "py3-none-any",
        "python_312",
        f"version 13.{MINOR}",
    ],
)
def test_the_scanner_ignores_other_versions(line: str) -> None:
    assert not PYTHON_VERSION.search(line)


def plant(tmp_path: Path, files: dict[str, str]) -> Path:
    declared = declared_requires_python(REPO_ROOT)
    tree = {
        "pyproject.toml": (
            f'[project]\nname = "root"\nrequires-python = "{declared}"\n'
            '[tool.uv.workspace]\nmembers = ["packages/*"]\n'
        ),
        str(DECLARATION): f'[project]\nname = "debate-core"\nrequires-python = "{declared}"\n',
        **files,
    }
    for name, text in tree.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    return tmp_path


def member_pyproject(requires_python: str) -> str:
    return f'[project]\nname = "debate-cli"\nrequires-python = "{requires_python}"\n'


def test_a_new_mention_in_a_tracked_file_is_found(tmp_path: Path) -> None:
    root = plant(tmp_path, {"scripts/install.sh": f"PYTHON_VERSION=3.{MINOR}\n", "docs/guide.md": "fine\n"})

    assert [str(mention) for mention in mentions(root, tracked_files(root))] == [
        f"scripts/install.sh:1: PYTHON_VERSION=3.{MINOR}"
    ]


def test_a_member_requires_python_that_differs_is_not_derived(tmp_path: Path) -> None:
    root = plant(
        tmp_path,
        {"packages/debate_cli/pyproject.toml": member_pyproject(f">=3.{MINOR}")},
    )

    assert [mention.path for mention in mentions(root, tracked_files(root))] == [
        "packages/debate_cli/pyproject.toml"
    ]


def test_the_declaration_and_equal_copies_are_derived_and_permitted_files_are_skipped(tmp_path: Path) -> None:
    declared = declared_requires_python(REPO_ROOT)
    root = plant(
        tmp_path,
        {
            "packages/debate_cli/pyproject.toml": member_pyproject(declared),
            ".python-version": f"3.{MINOR}\n",
            "docs/session-reports/old.md": f"we passed --python 3.{MINOR}\n",
            "site/pnpm-lock.yaml": f"js-yaml@3.{NEXT}.2:\n",
            ".github/workflows/ci.yml": f"        python-version: ['3.{MINOR}']\n",
        },
    )

    assert mentions(root, tracked_files(root)) == []


def test_a_requires_python_outside_the_workspace_is_not_derived(tmp_path: Path) -> None:
    declared = declared_requires_python(REPO_ROOT)
    root = plant(tmp_path, {"tools/other/pyproject.toml": f'[project]\nrequires-python = "{declared}"\n'})

    assert [mention.path for mention in mentions(root, tracked_files(root))] == ["tools/other/pyproject.toml"]
