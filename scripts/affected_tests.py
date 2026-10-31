"""Print the test files a branch's changes can affect, and optionally run them (v1-e01-t28).

Working agreement 10 has a session run the affected set once before its report, and CI run the
same selection on a pull request into dev (scripts/ci_test_selection.py, v1-e01-t38) and the whole
default selection on dev's push run. This script prints that affected set. It reads the
files the branch changed against its merge base with `--base` (origin/dev by default), plus the
working tree's uncommitted and untracked files, and selects every test file one of them can reach:

* **A changed test file** itself.
* **Imports.** Every test file that imports a changed module, directly or through any chain of
  modules. Between the workspace packages' own modules the edges come from grimp; test files,
  conftest files, shared test helpers (`tests/fixtures/...`, the scenario modules beside a test)
  and scripts are read with `ast`, and their imports resolved to files in this repository:
  package modules, `tests.fixtures.x` paths from the repository root, relative imports, and a bare
  `import check_links` to every `check_links.py` outside the packages (scripts put their own
  directory on `sys.path`). Importing `a.b.c` runs `a/__init__.py` and `a/b/__init__.py`, so a
  module depends on the packages that contain it.
* **conftest files.** pytest runs with `--import-mode=importlib` and fixtures come from conftest
  files, so a test depends on every `conftest.py` above it, and on everything those import. A
  changed conftest selects every test beneath it. Reaching the root `conftest.py` is the whole
  selection.
* **Runs.** A file that runs a console script (`debate-research`) or `-m <module>` runs that
  module, so it depends on it as if it imported it. A Python file's string literals are read one by
  one (v1-e01-t44), on the console script's own line: it runs where the string is the program
  alone, where the line starts with it, where it ends a path, and where the text before it is not
  a sentence (shell syntax such as `&&` or `X=1`, an option, or a program that runs its arguments,
  such as `uv run`). After a sentence, or inside a code span or quotes a sentence holds, it is
  prose: `"Fix: run `debate-research caselist parse` first"` runs nothing. A code span may open
  the line, as the fragments a message joins do. Part of another name (`~/.debate-research`), or a
  name a slash goes on from (a folder, the User-Agent's `debate-research/<version>`), is not the
  program. Any other file, such as a shell script, runs every console
  script it names, and `--every-mention-runs` reads every mention that way, as before.
* **Names.** A file read or run by path is found by its name, in the string literals of Python
  files (docstrings and comments describe files, they do not read them) and anywhere in a shell
  script. A changed data file (a fixture under `tests/fixtures/`, package data such as
  `style_profiles/*.yaml` or `templates/base.docx`, a workflow, Terraform) selects the files that
  name it: its file name, or the name of a folder it is in as a quoted or slash-separated path
  part, plus the Python files in those folders. The folders stop at a Python package, a folder
  holding tests or a conftest, or a generic one (`tests`, `fixtures`, `data`, ...); a name like
  `v1` is skipped. A file named that way counts as changed, so a helper module that opens the
  fixture carries the selection on to the tests importing it. A package module reads only its own
  package's files: naming a runbook in an error message is not reading it. A data file nothing
  names selects every test of the package it is in, or the whole selection when it is in none. A
  changed script or test helper outside the packages is also found by its file name, which is how
  a test that starts it with subprocess (`write_junk_beside_a_held_link_files.py`,
  `scripts/*.py`) is selected.
* **Paths, not words** (v1-e01-t32). A Python string that is a path names only what it denotes. A
  `Path(__file__)` join (`Path(__file__).parent / "fixtures" / "landscape"`) denotes the path it
  builds, so another package's folder of the same name is not named. A string with a slash
  denotes the existing paths it is the end of (`"card/select.md"` is `prompts/card/select.md`),
  or, when it starts with a slash, only one from the repository root or the file's own folder: a
  route (`"/account/email/verify"`) or an f-string's tail (`f"{CORE}/retrieval/identifiers.py"`)
  denotes nothing. A string with a wildcard denotes the folder before it; one with whitespace is
  prose or a command, and its words are searched. Any other string is a word: it names a file by
  its file name wherever it is, but a folder or a script by its bare name only where a path is
  built from it (an operand of `/`, an argument of `Path` or `joinpath`, an item a `for` walks)
  and only from four letters up. `"flow"` as a label and `"s3"` as boto3's service name name
  nothing.
* **The container and the app, by factory and by command** (v1-e01-t39). Every command module
  imports `debate_cli/container.py` through `debate_cli/context.py`, and `debate_cli/app.py`
  imports every command module through `command_registry.py`, so read as files they make any
  change reach every test that runs a command. They are read finer:
  * Each method of `ServiceContainer`, and each function and class beside it, is a part. An import
    inside one is that part's, and one at the top is the parts' whose code uses the name it binds.
    An import that module code uses (a constant, a base class, a decorator), or that nothing uses,
    is the whole module's. A part reaches the parts that call it (`self.X`).
  * A change to `container.py` itself is read part by part too (v1-e01-t43): both sides are parsed
    and compared, and a part whose code changed, or a new one, is where the walk starts, so it
    reaches what asks for that part and for the parts that call it. Anything that runs when the
    module is imported is the whole file's: an import, a module constant, the container's own
    attributes, docstring and dunder methods (`__init__`), a part's decorators, defaults or class
    body (a new part may add only `@property`, `@staticmethod`, `@classmethod` and literal
    defaults). So are a part removed, renamed or moved, a changed part that assigns a module name
    (`global`), a part module code uses, a part the graph's tree does not have, and a side that is
    missing or does not parse. A change to comments or layout alone reaches no part. A file that
    names the container module in a string is still reached by that name, unless it reads the
    container whole, which its edges to every part already say. `--whole-container` reads any
    change to the file as the whole file, as before.
  * A file that can hold a container (a `debate_cli` module, or a file that imports one) reaches
    each part it names, as an attribute or a quoted word: `cli.services.X`, `services.X` after
    `services = cli.services`, a helper handed the container that calls `services.X`, or a test's
    `container.X()`. One that reads the class by reflection (`getattr` with a name it computes,
    `vars`, `dir`, `inspect`) or names the container module in a string reaches every part. In a
    package module, only the functions that do so are counted: the post-install check's
    `wired_integrations` reads the container's imports, so a file that calls it, or runs the
    module, reaches every part, and `app.py`, which imports the module for its error message,
    does not.
  * `command_registry.py`'s `register_commands` says which commands each module is (`caselist
    remove`, `caselist unsuppress`). A command module reaches the app for those commands, and the
    app for a command reaches each file that runs the app, through an import, a fixture, a
    console script or a helper, if the literal arguments of that file, or of the helpers and
    conftests between it and the app, name the command. Arguments are read as runs of literal
    words a call, a list, a tuple or a constant holds, so `("caselist", "remove", "--team", t)`
    names `caselist remove`, a helper's `("caselist", *arguments)` with its caller's
    `("remove", ...)` does too, and prose, a dictionary key or a word in another command does
    not. A group alone names all its commands (its help lists them). A test whose runs hold no
    command's first word, or that asks for the root's `--help`, cannot be told apart and reaches
    every command, as before. A registry it cannot read, or a container with no `ServiceContainer`
    class, is read as a file, as before.
* **Source readers.** A test that walks a directory and parses the Python it finds there
  (`ast.parse` with a glob, `rglob`, `iterdir` or `walk`) reads source as data, so any changed
  Python file selects it.
* **Categories.** Any Markdown file, and anything under `docs/`, selects the documentation checks
  (`tests/docs/`, the command-block and docs-index tests), because they read every tracked
  Markdown file. `plan_specs/` selects `tests/specs/`. `infrastructure/` is checked by
  `scripts/terraform_checks.sh`, and `site/` and `web/` by their own pnpm checks; the script says
  so, and selects only the tests that name what changed.
* **Always run:** `tests/architecture/`, `tests/specs/` and the CLI's composition-root and
  command-registration tests (`test_app.py`, `test_help_rendering.py`, and
  `test_container_factories.py`, which builds every factory), which wiring reaches as much as
  imports do.

A change to **shared test ground** (any `pyproject.toml`, `uv.lock`, the root `conftest.py`,
`tests/pytest_plugins/`, `.github/workflows/ci.yml`) affects the whole selection. The script prints
one line saying so, and that CI runs it, and exits 0; `--run` then runs nothing, because a session
never runs the whole selection (working agreement 10). The one exception is a root `pyproject.toml`
change that touches only `[tool.importlinter]`, read by `tests/architecture/` alone, which selects
those (v1-e01-t32). It is read as TOML: a change to `[tool.pytest]`, the dependencies or any other
table, or only to comments, is still the whole selection.

It is conservative on purpose: a missed test is the failure that matters, and an extra one costs
seconds. When it cannot tell, it selects more and says why (`--explain`). It keeps no state between
runs: the graph is built from the files each time, in a few seconds.

`--diff REV` describes what one commit changed (REV against its first parent), and `--head REV`
a branch tip against its merge base with `--base`, both read from git without checking anything
out: the import graph is built from that commit's files, copied into a temporary directory.

`--graph REV2` builds the graph from REV2's files instead, whichever way the changes were named
(v1-e01-t30). It answers "what would this change select over that tree", which is how a task that
narrows imports is measured: t28's commits, each selected over the task's own graph. The test files
are REV2's, so a changed file REV2 does not have is reached only by name, and the script lists such
files. It cannot be combined with `--run`, which runs the working tree's tests.

Usage:
  uv run scripts/affected_tests.py                     # this branch against origin/dev, as printed paths
  uv run scripts/affected_tests.py --explain           # with the reason each file was selected
  uv run scripts/affected_tests.py --run               # and run pytest over them with CI's markers
  uv run scripts/affected_tests.py --diff REV          # what commit REV changed
  uv run scripts/affected_tests.py --base A --head B   # B against its merge base with A
  uv run scripts/affected_tests.py --diff REV --graph REV2   # REV's changes over REV2's imports
  uv run scripts/affected_tests.py --whole-container   # a container.py change read as the whole file
  uv run scripts/affected_tests.py --every-mention-runs   # any debate-research in a string read as a run
"""

from __future__ import annotations

import argparse
import ast
import bisect
import contextlib
import importlib
import importlib.util
import pkgutil
import posixpath
import re
import subprocess
import sys
import tempfile
import time
import tomllib
from collections import deque
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath

DEFAULT_BASE = "origin/dev"
CI_MARKERS = "not slow and not live"

# Shared test ground: a change to any of these can reach every test.
SHARED_TEST_GROUND_FILES = frozenset({"conftest.py", "uv.lock", ".github/workflows/ci.yml"})
SHARED_TEST_GROUND_DIRECTORIES = ("tests/pytest_plugins/",)
# The root pyproject.toml's tables that only some tests read: a change to these alone selects those
# tests, not the whole selection (v1-e01-t32). `[tool.pytest]`, the dependencies and every other
# table stay shared test ground.
ROOT_PYPROJECT = "pyproject.toml"
TABLES_READ_ONLY_BY = {"tool.importlinter": ("tests/architecture/",)}

# What imports cannot see: tests that read the whole repository, and the CLI's wiring.
ALWAYS_RUN = (
    "tests/architecture/",
    "tests/specs/",
    "packages/debate_cli/tests/test_app.py",
    "packages/debate_cli/tests/test_help_rendering.py",
    # Builds every factory, so that an integration that fails to import still fails (v1-e01-t39).
    "packages/debate_cli/tests/test_container_factories.py",
)
# The composition root and the app, read by factory and by command (v1-e01-t39).
CLI_SOURCE = "packages/debate_cli/src/debate_cli"
CONTAINER = f"{CLI_SOURCE}/container.py"
CONTAINER_CLASS = "ServiceContainer"
CONTAINER_MODULE = "debate_cli.container"
CONTEXT = f"{CLI_SOURCE}/context.py"
APP = f"{CLI_SOURCE}/app.py"
COMMAND_REGISTRY = f"{CLI_SOURCE}/command_registry.py"
REGISTERING_FUNCTION = "register_commands"
# A part of a file is named `<file>::<part>`: a container method, or the app for one command module.
PART = "::"
# A string naming one name of the container module, as a `monkeypatch.setattr` target does, and any
# mention of the module at all (v1-e41-t06).
CONTAINER_NAME = re.compile(rf"{re.escape(CONTAINER_MODULE)}\.([A-Za-z_]\w*)(?:\.([A-Za-z_]\w*))?")
NAMES_THE_CONTAINER = re.compile(rf"(?<![\w-])(?:{re.escape(CONTAINER_MODULE)}|container\.py)(?![\w-])")
# What reads a module's names by a name it computes, so that no reader of a name can be told apart.
COMPUTED_NAME_READS = frozenset({"globals", "vars", "locals", "eval", "exec", "__dict__", "__getattr__"})
# A workspace package's file, by its path below `src/`: what an import can load from this repository.
SOURCE_FILE = re.compile(r"^packages/[^/]+/src/(.+)$")
# What asks for help: before any command's word, the root's, which lists every command.
HELP_FLAGS = frozenset({"--help", "-h"})
# Calls that read the container by a name they compute, or as a whole.
REFLECTION_CALLS = frozenset({"vars", "dir", "getmembers", "getsource", "attrgetter", "methodcaller"})
# The tests that read every tracked Markdown file, or check docs/ as a whole.
DOCS_CHECK_TESTS = (
    "tests/docs/",
    "tests/scripts/test_check_command_blocks.py",
    "tests/scripts/test_docs_index.py",
)
SPEC_TESTS = ("tests/specs/",)
CHECKED_OUTSIDE_PYTEST = {
    "infrastructure/": "infrastructure/ changed: scripts/terraform_checks.sh is the real check for it.",
    "site/": "site/ changed: the site's own pnpm checks test it; pytest does not.",
    "web/": "web/ changed: the web app's own pnpm checks test it; pytest does not.",
}

# A folder name this generic is not evidence that a file mentioning it reads a particular file.
GENERIC_FOLDERS = frozenset({"tests", "fixtures", "data", "src", "packages", "scripts", "docs"})
# File names too common to search for; such a file is found through its path or module name.
GENERIC_FILE_NAMES = frozenset({"__init__.py", "__main__.py", "conftest.py", "py.typed", "README.md"})
# Python loads these by their name from a directory on its path; a test reaches them by the folder.
LOADED_BY_FOLDER = frozenset({"sitecustomize.py", "usercustomize.py"})
# A folder named like this (`v1`, `ab`) matches literals that have nothing to do with it.
VAGUE_FOLDER = re.compile(r"v\d+|.{1,2}")
# A quoted word shorter than this names a folder or a script only beside a slash: `"s3"` in
# `boto3.client("s3")` is not `tests/smoke/stand_ins/s3.py` (v1-e01-t32).
SHORTEST_QUOTED_WORD = 4
# A path segment holding one of these is a pattern or a placeholder, not a name: the path ends there.
WILDCARD = re.compile(r"[*?\[{<%]")
LARGEST_SEARCHED_FILE = 2_000_000

SOURCE_READER = re.compile(r"\bast\.parse\(")
DIRECTORY_WALK = re.compile(r"\b(?:rglob|glob|iterdir|walk)\(")
MODULE_FLAG = re.compile(r"""(?:["']-m["']\s*,\s*["']|-m\s+)([A-Za-z_][\w.]*)""")
# How a string holds a console script's name as prose rather than as a run of it (v1-e01-t44).
PATH_SEPARATORS = ("/", "\\")
QUOTE_MARKS = ("'", '"', "\N{LEFT SINGLE QUOTATION MARK}", "\N{LEFT DOUBLE QUOTATION MARK}")
CODE_SPAN = re.compile(r"`[^`]*`")
# A word a sentence can put before a name: letters, an apostrophe or a hyphen inside, one closing mark.
SENTENCE_WORD = re.compile(
    r"[A-Za-z][A-Za-z'\N{RIGHT SINGLE QUOTATION MARK}-]*[.,:!?)]?|[\N{EM DASH}\N{EN DASH}]"
)
# Words after which a shell runs the next word: its own keywords, and programs that run their arguments.
RUNS_ITS_ARGUMENTS = frozenset(
    {
        *("if", "then", "else", "elif", "do", "while", "until", "time"),
        *("exec", "env", "command", "builtin", "eval", "sudo", "doas", "nohup", "nice", "timeout"),
        *("xargs", "watch", "caffeinate", "run", "uvx", "pipx", "sh", "bash", "zsh", "python", "python3"),
    }
)


# --------------------------------------------------------------------------------------------
# One version of the repository: the working tree, or a commit read from git
# --------------------------------------------------------------------------------------------


def git(root: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    completed = subprocess.run(["git", *args], cwd=root, input=input_bytes, capture_output=True, check=False)
    if completed.returncode != 0:
        message = completed.stderr.decode(errors="replace").strip()
        raise SystemExit(f"affected_tests: git {' '.join(args)} failed: {message}")
    return completed.stdout


def is_searched(path: str) -> bool:
    """Whether a file's text is read: Python and shell anywhere, and every script in scripts/."""
    return path.endswith((".py", ".sh")) or (
        path.startswith("scripts/") and "." not in PurePosixPath(path).name
    )


@dataclass
class Tree:
    root: Path
    revision: str | None
    paths: frozenset[str]
    texts: dict[str, str]

    @classmethod
    def working(cls, root: Path) -> Tree:
        listed = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard").decode()
        paths = frozenset(path for path in listed.split("\0") if path and (root / path).is_file())
        texts: dict[str, str] = {}
        for path in paths:
            if is_searched(path):
                text = decode((root / path).read_bytes())
                if text is not None:
                    texts[path] = text
        return cls(root, None, paths, texts)

    @classmethod
    def at(cls, root: Path, revision: str) -> Tree:
        listed = git(root, "ls-tree", "-r", "-z", "--name-only", revision).decode()
        paths = frozenset(path for path in listed.split("\0") if path)
        wanted = sorted(path for path in paths if is_searched(path))
        request = "".join(f"{revision}:{path}\n" for path in wanted).encode()
        output = git(root, "cat-file", "--batch", input_bytes=request)
        texts: dict[str, str] = {}
        position = 0
        for path in wanted:
            header_end = output.index(b"\n", position)
            size = int(output[position:header_end].split()[2])
            body = output[header_end + 1 : header_end + 1 + size]
            position = header_end + 1 + size + 1
            text = decode(body)
            if text is not None:
                texts[path] = text
        return cls(root, revision, paths, texts)

    def syntax(self, path: str) -> ast.Module | None:
        """A Python file's syntax tree, parsed once; None if it does not parse."""
        if path not in self._syntax:
            try:
                self._syntax[path] = ast.parse(self.texts.get(path, ""))
            except (SyntaxError, ValueError):
                self._syntax[path] = None
        return self._syntax[path]

    def literals(self, path: str) -> str:
        """The text a file can name another file with: a Python file's string literals, other files whole.

        Docstrings and other bare string statements, and comments, describe files rather than read
        them, so they are left out; `ast` gives the literals in source order, each in double quotes.
        """
        strings = self.strings(path)
        if strings is None:
            return self.texts.get(path, "")
        return ", ".join(f'"{string}"' for string in strings)

    def strings(self, path: str) -> list[str] | None:
        """A Python file's string literals, as :meth:`literals` reads them; None for any other file."""
        syntax = self.syntax(path) if path.endswith(".py") else None
        return None if syntax is None else strings_in(syntax)

    _syntax: dict[str, ast.Module | None] = field(default_factory=dict, repr=False)


def decode(data: bytes) -> str | None:
    if len(data) > LARGEST_SEARCHED_FILE or b"\0" in data:
        return None
    return data.decode("utf-8", errors="replace")


# --------------------------------------------------------------------------------------------
# What changed
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Change:
    path: str
    deleted: bool
    # For the root pyproject.toml: the tables that differ, `tool.<name>` for a tool's own (v1-e01-t32).
    # None when either version is missing or does not parse; empty when only comments or layout moved.
    tables: frozenset[str] | None = None
    # For container.py: what changed, part by part (v1-e01-t43). None reads it as the whole file.
    container: ContainerDiff | None = None


def changed_files(root: Path, base: str, head: str | None, diff: str | None) -> list[Change]:
    if diff is not None:
        parents = git(root, "rev-list", "--parents", "-n", "1", diff).decode().split()
        if len(parents) < 2:
            raise SystemExit(f"affected_tests: {diff} has no parent to compare with")
        listing = git(root, "diff", "--name-status", "--no-renames", "-z", parents[1], parents[0])
        return with_readings(root, parse_name_status(listing), parents[1], parents[0])
    tip = head or "HEAD"
    merge_base = git(root, "merge-base", base, tip).decode().strip()
    changes = {
        change.path: change
        for change in parse_name_status(
            git(root, "diff", "--name-status", "--no-renames", "-z", merge_base, tip)
        )
    }
    if head is None:
        for change in parse_name_status(git(root, "diff", "--name-status", "--no-renames", "-z", "HEAD")):
            changes[change.path] = change
        untracked = git(root, "ls-files", "-z", "--others", "--exclude-standard").decode()
        for path in untracked.split("\0"):
            if path:
                changes[path] = Change(path, deleted=False)
    ordered = sorted(changes.values(), key=lambda change: change.path)
    return with_readings(root, ordered, merge_base, head)


def with_readings(root: Path, changes: list[Change], before: str, after: str | None) -> list[Change]:
    """`changes`, with the tables a root pyproject.toml change touched and the parts a container.py
    change touched (`after` None: the working tree)."""
    read: list[Change] = []
    for change in changes:
        if change.path == ROOT_PYPROJECT and not change.deleted:
            change = replace(change, tables=changed_tables(root, before, after))
        elif change.path == CONTAINER and not change.deleted:
            change = replace(
                change,
                container=container_diff(
                    file_at(root, before, CONTAINER),
                    file_at(root, after, CONTAINER),
                    lambda: Modules.of(package_paths_at(root, before)),
                    lambda: Modules.of(package_paths_at(root, after)),
                ),
            )
        read.append(change)
    return read


def package_paths_at(root: Path, revision: str | None) -> frozenset[str]:
    """The files under packages/ at a commit, or in the working tree (v1-e41-t06)."""
    if revision is None:
        listed = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "packages")
        return frozenset(path for path in listed.decode().split("\0") if path and (root / path).is_file())
    listed = git(root, "ls-tree", "-r", "-z", "--name-only", revision, "--", "packages")
    return frozenset(path for path in listed.decode().split("\0") if path)


@dataclass(frozen=True)
class Modules:
    """Which dotted names are modules on one side of a change (v1-e41-t06).

    A workspace package's are its files and folders on that side; the standard library's are the
    running interpreter's, the same on both sides. Any other name cannot be told, and an import of it
    counts as loading it.
    """

    found: frozenset[str] = frozenset()
    tops: frozenset[str] = frozenset()

    @classmethod
    def of(cls, paths: Iterable[str]) -> Modules:
        found: set[str] = set()
        for path in paths:
            match = SOURCE_FILE.match(path)
            if match is None:
                continue
            *folders, name = match.group(1).split("/")
            found |= {".".join(folders[:depth]) for depth in range(1, len(folders) + 1)}
            if name.endswith(".py") and name != "__init__.py":
                found.add(".".join([*folders, name.removesuffix(".py")]))
        return cls(frozenset(found), frozenset(name.split(".")[0] for name in found))

    def is_module(self, name: str) -> bool | None:
        """Whether a dotted name is a module; None when it cannot be told."""
        top = name.split(".")[0]
        if top in self.tops:
            return name in self.found
        if top in sys.stdlib_module_names:
            return is_standard_module(name)
        return None


def is_standard_module(name: str) -> bool | None:
    """Whether a standard library name is a module: a top-level one, or a file in its package."""
    parent, _, child = name.rpartition(".")
    if not parent:
        return True
    try:
        spec = importlib.util.find_spec(parent)
    except (ImportError, ValueError):
        return None
    if spec is None:
        return None
    if spec.submodule_search_locations is None:
        return False  # a module that is not a package has no modules in it
    return any(module.name == child for module in pkgutil.iter_modules(spec.submodule_search_locations))


def changed_tables(root: Path, before: str, after: str | None) -> frozenset[str] | None:
    """The top-level tables of the root pyproject.toml that differ, and each `tool.<name>` on its own."""
    old = pyproject_at(root, before)
    new = pyproject_at(root, after)
    if old is None or new is None:
        return None
    tables: set[str] = set()
    for key in old.keys() | new.keys():
        old_tools, new_tools = old.get(key, {}), new.get(key, {})
        if key == "tool" and isinstance(old_tools, dict) and isinstance(new_tools, dict):
            tables |= {
                f"tool.{tool}"
                for tool in old_tools.keys() | new_tools.keys()
                if old_tools.get(tool) != new_tools.get(tool)
            }
        elif old.get(key) != new.get(key):
            tables.add(key)
    return frozenset(tables)


def file_at(root: Path, revision: str | None, path: str) -> str | None:
    """A file's text at a commit, or in the working tree; None if it is missing."""
    if revision is None:
        file = root / path
        return file.read_text(encoding="utf-8", errors="replace") if file.is_file() else None
    shown = subprocess.run(["git", "show", f"{revision}:{path}"], cwd=root, capture_output=True, check=False)
    if shown.returncode != 0:
        return None
    return shown.stdout.decode("utf-8", errors="replace")


def pyproject_at(root: Path, revision: str | None) -> dict[str, object] | None:
    """The root pyproject.toml at a commit, or in the working tree; None if missing or unreadable."""
    data = file_at(root, revision, ROOT_PYPROJECT)
    if data is None:
        return None
    try:
        return tomllib.loads(data)
    except tomllib.TOMLDecodeError:
        return None


def parse_name_status(listing: bytes) -> list[Change]:
    fields = listing.decode().split("\0")
    changes: list[Change] = []
    for status, path in zip(fields[0::2], fields[1::2], strict=False):
        if status and path:
            changes.append(Change(path, deleted=status.startswith("D")))
    return changes


# --------------------------------------------------------------------------------------------
# The repository's layout: workspace packages, test files, console scripts
# --------------------------------------------------------------------------------------------


PACKAGE_INIT = re.compile(r"^(packages/[^/]+/src)/([A-Za-z_]\w*)/__init__\.py$")


@dataclass
class Layout:
    tree: Tree
    packages: dict[str, str] = field(default_factory=dict)  # import name -> src directory
    module_paths: dict[str, str] = field(default_factory=dict)  # dotted module -> file
    path_modules: dict[str, str] = field(default_factory=dict)  # file -> dotted module
    test_files: frozenset[str] = frozenset()
    console_scripts: dict[str, str] = field(default_factory=dict)  # script name -> module
    test_folders: frozenset[str] = frozenset()  # folders holding a test file or a conftest.py
    python_files_in: dict[str, set[str]] = field(default_factory=dict)  # folder -> its Python files

    @classmethod
    def of(cls, tree: Tree) -> Layout:
        layout = cls(tree)
        for path in tree.paths:
            match = PACKAGE_INIT.match(path)
            if match:
                layout.packages[match.group(2)] = match.group(1)
        for name, src in layout.packages.items():
            prefix = f"{src}/{name}/"
            for path in tree.paths:
                if path.startswith(prefix) and path.endswith(".py"):
                    module = path[len(src) + 1 : -len(".py")].replace("/", ".")
                    module = module.removesuffix(".__init__")
                    layout.module_paths[module] = path
                    layout.path_modules[path] = module
        roots = test_roots(tree)
        layout.test_files = frozenset(path for path in tree.paths if is_test_file(path, roots))
        layout.test_folders = frozenset(
            str(PurePosixPath(path).parent)
            for path in tree.paths
            if path in layout.test_files or PurePosixPath(path).name == "conftest.py"
        )
        for path in tree.paths:
            if path.endswith(".py"):
                layout.python_files_in.setdefault(str(PurePosixPath(path).parent), set()).add(path)
        for path in tree.paths:
            if path.endswith("pyproject.toml") and path.startswith("packages/"):
                layout.console_scripts.update(read_console_scripts(tree, path))
        return layout

    def is_package_file(self, path: str) -> bool:
        return path in self.path_modules

    def show(self, path: str) -> str:
        module = self.path_modules.get(path)
        return f"{module} ({path})" if module else path


def test_roots(tree: Tree) -> tuple[str, ...]:
    configuration = read_toml(tree, "pyproject.toml")
    pytest_options = configuration.get("tool", {}).get("pytest", {}).get("ini_options", {})
    roots = pytest_options.get("testpaths") or ["."]
    return tuple("" if root in (".", "") else root.rstrip("/") + "/" for root in roots)


def is_test_file(path: str, roots: tuple[str, ...]) -> bool:
    name = PurePosixPath(path).name
    if not (name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))):
        return False
    return any(path.startswith(root) for root in roots)


def read_toml(tree: Tree, path: str) -> dict[str, dict]:  # type: ignore[type-arg]
    if tree.revision is None:
        file = tree.root / path
        data = file.read_bytes() if file.is_file() else b""
    else:
        data = git(tree.root, "show", f"{tree.revision}:{path}") if path in tree.paths else b""
    try:
        return tomllib.loads(data.decode())
    except tomllib.TOMLDecodeError:
        return {}


def read_console_scripts(tree: Tree, path: str) -> dict[str, str]:
    scripts = read_toml(tree, path).get("project", {}).get("scripts", {})
    return {name: str(target).split(":")[0] for name, target in scripts.items()}


# --------------------------------------------------------------------------------------------
# The dependency graph: which files each file depends on, and how
# --------------------------------------------------------------------------------------------

IMPORTS = "imports"
CONFTEST = "is beneath"
RUNS = "runs"
NAMES = "names"
HAS_A_PATH_TO = "has a path to"
READS_SOURCE = "reads the Python source of"
# v1-e01-t39: between the container's parts, the files that ask for them, and the app's commands.
CALLS = "calls"
USES = "uses"
ASKS = "asks for"
READS_EVERY_PART = "reads the container whole, by reflection or as source, so it has"
REGISTERS = "registers"
ROOT_CONFTEST = "conftest.py"
# The edges a conftest read fixture by fixture is reached by when its fixtures' own edges carry them.
FIXTURE_EDGES = frozenset({IMPORTS, RUNS})


@dataclass
class Graph:
    layout: Layout
    dependents: dict[str, list[tuple[str, str]]] = field(default_factory=dict)  # target -> (who, how)
    notes: list[str] = field(default_factory=list)
    root_conftest_unread: bool = False
    # Conftests below the root read fixture by fixture: reaching one through a file it imports or
    # runs does not reach every test beneath it (v1-e01-t32).
    narrowed_conftests: set[str] = field(default_factory=set)
    # The app for each command module (`app.py::<module>`) -> the commands it registers, as words,
    # and each group's words -> the words beneath it, `()` holding the top-level ones (v1-e01-t39).
    app_commands: dict[str, tuple[tuple[str, ...], ...]] = field(default_factory=dict)
    command_children: dict[tuple[str, ...], set[str]] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)  # a part -> how --explain shows it
    # The container's parts, and the files that read it whole, by reflection or as source (v1-e01-t43).
    container_parts: frozenset[str] = frozenset()
    container_readers: set[str] = field(default_factory=set)
    # The files that name the container module only in `debate_cli.container.X` strings -> each X that
    # is not a part: a name it imports or defines, reached when an import rebinds it (v1-e41-t06).
    container_named: dict[str, frozenset[str]] = field(default_factory=dict)

    def add(self, dependent: str, how: str, target: str) -> None:
        if dependent != target:
            self.dependents.setdefault(target, []).append((dependent, how))


def build_graph(
    tree: Tree, layout: Layout, every_mention_runs: bool = False, whole_container: bool = False
) -> Graph:
    graph = Graph(layout)
    resolver = Resolver(layout, every_mention_runs)
    package_edges = grimp_edges(tree, layout, graph) or {}
    container = read_container(tree, resolver) if CONTAINER in tree.texts else None
    registered = read_registry(tree, layout) if COMMAND_REGISTRY in tree.texts else None
    if CONTAINER in tree.texts and container is None:
        graph.notes.append(f"{CONTAINER} has no {CONTAINER_CLASS} class to read; it was read as one file.")
    if COMMAND_REGISTRY in tree.texts and registered is None:
        graph.notes.append(
            f"{COMMAND_REGISTRY} could not be read command by command; every command reaches the app."
        )

    def imported_as_parts(path: str, target: str) -> bool:
        """An import the container's parts, or the app's commands, account for instead (v1-e01-t39)."""
        return (path == CONTAINER and container is not None) or (
            path == COMMAND_REGISTRY and registered is not None and target in registered
        )

    for path, module in layout.path_modules.items():
        parent = module.rpartition(".")[0]
        if parent in layout.module_paths:
            graph.add(path, IMPORTS, layout.module_paths[parent])
        for imported in package_edges.get(module, ()):
            target = layout.module_paths.get(imported)
            if target is not None and not imported_as_parts(path, target):
                graph.add(path, IMPORTS, target)
    for path in tree.texts:
        if not path.endswith(".py") or layout.path_modules.get(path) in package_edges:
            continue
        for target in resolver.imports_of(path):
            if not imported_as_parts(path, target):
                graph.add(path, IMPORTS, target)
    for path in tree.texts:
        if layout.is_package_file(path):
            continue  # package code names the CLI in its messages; it does not start it
        for target in resolver.runs_of(tree.literals(path), tree.strings(path)):
            graph.add(path, RUNS, target)
    conftests = sorted(path for path in tree.paths if PurePosixPath(path).name == "conftest.py")
    for test in layout.test_files:
        for conftest in conftests:
            folder = str(PurePosixPath(conftest).parent)
            if folder != "." and test.startswith(folder + "/"):
                graph.add(test, CONFTEST, conftest)
    if ROOT_CONFTEST in tree.texts:
        add_root_conftest_fixtures(tree, layout, resolver, graph, conftests)
    for conftest in conftests:
        if conftest != ROOT_CONFTEST and conftest in tree.texts:
            add_conftest_fixtures(tree, layout, resolver, graph, conftest, conftests)
    if container is not None:
        add_container_parts(tree, layout, graph, container)
        if not whole_container:
            add_container_names(tree, graph, container)
    if registered is not None:
        add_app_commands(layout, graph, registered)
    return graph


def add_root_conftest_fixtures(
    tree: Tree, layout: Layout, resolver: Resolver, graph: Graph, conftests: list[str]
) -> None:
    """Make the tests that use one of the root conftest.py's fixtures depend on what that fixture needs.

    Every test is beneath the root conftest.py, and its imports reach a third of debate_core, so
    counting them for every test would make nearly every change the whole selection. A module the
    root conftest imports can reach a test that does not import it in two ways. If it fails to
    import, the conftest fails and so does every test, the always-run ones included. Otherwise it
    can only change what a fixture gives a test, and that reaches the tests that use the fixture:
    a test or a conftest beneath it that names it. Autouse fixtures, and the conftest's module-level
    code, reach every test, so what they need is counted for every test.
    """
    reading = read_conftest(tree, resolver, ROOT_CONFTEST)
    if reading is None:
        graph.root_conftest_unread = True
        return
    for file in sorted(reading.files(reading.everywhere)):
        for test in layout.test_files:
            graph.add(
                test, "is beneath the root conftest.py, whose module code or autouse fixtures need", file
            )
    for name, used in sorted(reading.fixtures.items()):
        files = reading.files(used)
        if not files:
            continue
        users = fixture_users(tree, layout, ROOT_CONFTEST, name, set(layout.test_files), conftests)
        for file in sorted(files):
            for test in sorted(users):
                graph.add(test, f"uses the root conftest.py's {name} fixture, which needs", file)


def add_conftest_fixtures(
    tree: Tree, layout: Layout, resolver: Resolver, graph: Graph, conftest: str, conftests: list[str]
) -> None:
    """The same for a conftest below the root: a test beneath it reaches what its fixtures need (v1-e01-t32).

    `packages/debate_core/tests/application/caselist/conftest.py` imports the removal, publish and
    suppression services for its `removal_world` fixture; a test that uses only `local` reached
    them all. Now each file the conftest imports or runs reaches:

    * every test beneath it, when module code, an autouse fixture or a `pytest_*` hook needs it,
      or when nothing in the conftest does (an import that fails still fails every test beneath);
    * otherwise the tests beneath that use a fixture needing it, by name, directly or through a
      conftest further down that names it.

    An import inside a fixture's function counts for that fixture, as one at the top of the file
    does: what decides is which code uses the name. A file the conftest names (a fixture folder)
    still reaches every test beneath it, and so does a change to the conftest itself
    (:meth:`Walk.run`). A conftest that does not parse is read whole, as before.
    """
    reading = read_conftest(tree, resolver, conftest)
    if reading is None:
        return
    folder = str(PurePosixPath(conftest).parent) + "/"
    beneath = {test for test in layout.test_files if test.startswith(folder)}
    reached: dict[str, dict[str, str]] = {}  # file -> test -> how
    everywhere = (
        reading.files(reading.everywhere) | reading.runs(reading.everywhere) | reading.run_by.get("", set())
    )
    used_anywhere = reading.needs(reading.everywhere.union(*reading.fixtures.values()))
    unused = set(resolver.imports_of(conftest)) - reading.files(used_anywhere)
    for file in everywhere | unused:
        for test in beneath:
            reached.setdefault(file, {})[test] = (
                f"is beneath {conftest}, whose module code, hooks or imports need"
            )
    for name, used in sorted(reading.fixtures.items()):
        files = reading.files(used) | reading.runs(used)
        if not files:
            continue
        users = fixture_users(tree, layout, conftest, name, beneath, conftests)
        for file in files:
            for test in users:
                reached.setdefault(file, {}).setdefault(
                    test, f"uses the {name} fixture of {conftest}, which needs"
                )
    for file, tests in sorted(reached.items()):
        for test, how in sorted(tests.items()):
            graph.add(test, how, file)
    graph.narrowed_conftests.add(conftest)


def fixture_users(
    tree: Tree, layout: Layout, conftest: str, name: str, beneath: set[str], conftests: list[str]
) -> set[str]:
    """The tests beneath `conftest` that use its fixture `name`: by the word, or through a lower conftest."""
    word = re.compile(rf"\b{re.escape(name)}\b")
    users = {test for test in beneath if word.search(tree.texts.get(test, ""))}
    for other in conftests:
        if other != conftest and other != ROOT_CONFTEST and word.search(tree.texts.get(other, "")):
            folder = str(PurePosixPath(other).parent) + "/"
            users |= {test for test in beneath if test.startswith(folder)}
    return users


@dataclass
class ConftestReading:
    """Which names a conftest's module code and each of its fixtures use, and the files those bring.

    `everywhere` is what runs for every test beneath it: module-level statements, autouse fixtures
    and `pytest_*` hooks. `definitions` is what each top-level function, class or assignment uses,
    so a fixture's needs are followed through the helpers it calls.
    """

    imported: dict[str, set[str]]  # a name the conftest binds by importing -> the files that brings
    definitions: dict[str, set[str]]
    everywhere: set[str]
    fixtures: dict[str, set[str]]
    run_by: dict[str, set[str]]  # a top-level name, or "" for module code -> the modules it runs

    def needs(self, names: set[str]) -> set[str]:
        seen: set[str] = set()
        pending = list(names)
        while pending:
            name = pending.pop()
            if name not in seen:
                seen.add(name)
                pending.extend(self.definitions.get(name, ()))
        return seen

    def files(self, names: set[str]) -> set[str]:
        return {file for name in self.needs(names) for file in self.imported.get(name, ())}

    def runs(self, names: set[str]) -> set[str]:
        return {module for name in self.needs(names) for module in self.run_by.get(name, ())}


def read_conftest(tree: Tree, resolver: Resolver, conftest: str) -> ConftestReading | None:
    syntax = tree.syntax(conftest)
    if syntax is None:
        return None
    imported: dict[str, set[str]] = {}
    for node in ast.walk(syntax):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                imported.setdefault(local, set()).update(resolver.resolve(conftest, 0, alias.name, ()))
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                files = resolver.resolve(conftest, node.level, node.module or "", (alias.name,))
                imported.setdefault(alias.asname or alias.name, set()).update(files)
    reading = ConftestReading(imported, {}, set(), {}, {})
    for statement in syntax.body:
        if isinstance(statement, ast.Import | ast.ImportFrom):
            continue
        used = {node.id for node in ast.walk(statement) if isinstance(node, ast.Name)}
        runs = resolver.runs_of(literals_in(statement), strings_in(statement))
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef):
                used |= {
                    argument.arg for argument in ast.walk(statement.args) if isinstance(argument, ast.arg)
                }
            reading.definitions[statement.name] = used
            reading.run_by[statement.name] = runs
            fixture = fixture_of(statement)
            if fixture is not None:
                name, autouse = fixture
                if autouse:
                    reading.everywhere |= used | {statement.name}
                else:
                    reading.fixtures[name] = used | {statement.name}
            elif statement.name.startswith("pytest_"):
                reading.everywhere |= used | {statement.name}
        elif isinstance(statement, ast.Assign | ast.AnnAssign):
            targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
            for target in targets:
                for node in ast.walk(target):
                    if isinstance(node, ast.Name):
                        reading.definitions[node.id] = used
                        reading.run_by[node.id] = runs
            reading.everywhere |= used
            reading.run_by.setdefault("", set()).update(runs)
        else:
            reading.everywhere |= used
            reading.run_by.setdefault("", set()).update(runs)
    return reading


def literals_in(node: ast.AST) -> str:
    """The string literals of one statement as `Tree.literals` gives a file's: docstrings left out."""
    return ", ".join(f'"{string}"' for string in strings_in(node))


def strings_in(node: ast.AST) -> list[str]:
    """The string literals beneath a node in source order, without docstrings and other bare strings."""
    prose = {
        id(child.value)
        for child in ast.walk(node)
        if isinstance(child, ast.Expr) and isinstance(child.value, ast.Constant)
    }
    strings = [
        child
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str) and id(child) not in prose
    ]
    strings.sort(key=lambda child: (child.lineno, child.col_offset))
    return [str(child.value) for child in strings]


def fixture_of(definition: ast.stmt) -> tuple[str, bool] | None:
    """(name, autouse) if a module-level function is a pytest fixture."""
    if not isinstance(definition, ast.FunctionDef | ast.AsyncFunctionDef):
        return None
    for decorator in definition.decorator_list:
        call = decorator if isinstance(decorator, ast.Call) else None
        target = call.func if call is not None else decorator
        name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
        if name != "fixture":
            continue
        keywords = {keyword.arg: keyword.value for keyword in (call.keywords if call else [])}
        autouse = keywords.get("autouse")
        renamed = keywords.get("name")
        fixture_name = definition.name
        if isinstance(renamed, ast.Constant) and isinstance(renamed.value, str):
            fixture_name = renamed.value
        # Anything but a missing or literal False autouse counts as autouse: the safe reading.
        never_autouse = autouse is None or (isinstance(autouse, ast.Constant) and autouse.value is False)
        return fixture_name, not never_autouse
    return None


# --------------------------------------------------------------------------------------------
# The container by factory and the app by command (v1-e01-t39)
# --------------------------------------------------------------------------------------------


def part_of(path: str, part: str) -> str:
    return f"{path}{PART}{part}"


@dataclass
class ContainerReading:
    """`container.py` part by part: the container class's methods, and the functions and classes beside it.

    `module_files` is what module code needs, the code that runs when the module is imported: a
    top-level assignment, a base class, a decorator, a dunder method. An import nothing uses is
    counted there too, since one that fails fails the import. `module_parts` are the parts module
    code uses.
    """

    part_files: dict[str, set[str]]  # part -> the files the imports it uses bring
    part_calls: dict[str, set[str]]  # part -> the parts its code names
    module_files: set[str]
    module_parts: set[str]


def names_in(*nodes: ast.AST | None) -> set[str]:
    """Every name and attribute a piece of code mentions."""
    found: set[str] = set()
    for node in nodes:
        for child in ast.walk(node) if node is not None else ():
            if isinstance(child, ast.Name):
                found.add(child.id)
            elif isinstance(child, ast.Attribute):
                found.add(child.attr)
    return found


def evaluated_with_the_definition(definition: ast.stmt) -> list[ast.AST]:
    """What a `def` or `class` statement evaluates when it runs: decorators, defaults, bases."""
    if isinstance(definition, ast.ClassDef):
        return [*definition.decorator_list, *definition.bases, *definition.keywords]
    if isinstance(definition, ast.FunctionDef | ast.AsyncFunctionDef):
        defaults = [*definition.args.defaults, *(d for d in definition.args.kw_defaults if d is not None)]
        return [*definition.decorator_list, *defaults]
    return [definition]


def read_container(tree: Tree, resolver: Resolver) -> ContainerReading | None:
    """`container.py` read part by part; None when it has no single container class to read."""
    syntax = tree.syntax(CONTAINER)
    if syntax is None:
        return None
    classes = [
        node for node in syntax.body if isinstance(node, ast.ClassDef) and node.name == CONTAINER_CLASS
    ]
    if len(classes) != 1:
        return None
    container_class = classes[0]
    bound: dict[str, set[str]] = {}  # a name a top-level import binds -> the files it brings
    module_code: list[ast.AST] = []
    parts: dict[str, list[ast.stmt]] = {}

    def bind(statement: ast.Import | ast.ImportFrom) -> None:
        for alias in statement.names:
            if isinstance(statement, ast.Import):
                files = resolver.resolve(CONTAINER, 0, alias.name, ())
                bound.setdefault(alias.asname or alias.name.split(".")[0], set()).update(files)
            else:
                files = resolver.resolve(CONTAINER, statement.level, statement.module or "", (alias.name,))
                bound.setdefault(alias.asname or alias.name, set()).update(files)

    for statement in syntax.body:
        if isinstance(statement, ast.Import | ast.ImportFrom):
            bind(statement)
        elif statement is container_class:
            module_code.extend(evaluated_with_the_definition(container_class))
            for member in container_class.body:
                is_method = isinstance(member, ast.FunctionDef | ast.AsyncFunctionDef)
                if is_method and not (member.name.startswith("__") and member.name.endswith("__")):
                    parts.setdefault(member.name, []).append(member)
                    module_code.extend(evaluated_with_the_definition(member))
                else:
                    module_code.append(member)  # a class attribute, or a dunder every user runs
        elif isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            parts.setdefault(statement.name, []).append(statement)
            module_code.extend(evaluated_with_the_definition(statement))
        else:
            # Module code: an assignment, an `if TYPE_CHECKING:` block. Imports in it are bound
            # like any other top-level import, and read by what uses the names.
            for child in ast.walk(statement):
                if isinstance(child, ast.Import | ast.ImportFrom):
                    bind(child)
            module_code.append(statement)

    reading = ContainerReading({}, {}, set(), set())
    used_by_parts: set[str] = set()
    for part, definitions in parts.items():
        files: set[str] = set()
        names = names_in(*definitions)
        for definition in definitions:
            for child in ast.walk(definition):
                if isinstance(child, ast.Import):
                    for alias in child.names:
                        files |= resolver.resolve(CONTAINER, 0, alias.name, ())
                elif isinstance(child, ast.ImportFrom):
                    names_imported = tuple(alias.name for alias in child.names)
                    files |= resolver.resolve(CONTAINER, child.level, child.module or "", names_imported)
        for name in names & bound.keys():
            files |= bound[name]
        used_by_parts |= names
        reading.part_files[part] = files
        reading.part_calls[part] = (names & parts.keys()) - {part}
    module_names = names_in(*module_code)
    for name, files in bound.items():
        if name in module_names or name not in used_by_parts:
            reading.module_files |= files
    reading.module_parts = module_names & parts.keys()
    return reading


# What a new part may run on import and still be its own: `@property` and its kind, literal defaults.
INERT_DECORATORS = frozenset({"property", "staticmethod", "classmethod"})
INERT_NODES = (ast.Constant, ast.Expr, ast.Pass, ast.UnaryOp, ast.USub, ast.Load)


@dataclass(frozen=True)
class ContainerDiff:
    """A change to `container.py`, part by part, at the parts :func:`read_container` reads (v1-e01-t43).

    `parts` are the parts whose code changed, the new ones, and the parts that use a name the
    top-level imports rebind (v1-e41-t06), which `uses` maps to those names. `names` are the names
    rebound, for the files that import them from the container. `whole` says why the change is read
    as the whole file instead, as every change to it was before: it changed code that runs when the
    module is imported, or which modules the imports load, or removed or moved a part, or one side
    cannot be read.
    """

    parts: frozenset[str] = frozenset()
    whole: str | None = None
    names: frozenset[str] = frozenset()
    uses: dict[str, frozenset[str]] = field(default_factory=dict)


@dataclass
class ContainerOutline:
    """One side of `container.py`: the code that runs on import, and each part's code.

    `imports` are the imports at the top, read by what they load and bind (v1-e41-t06), and
    `module_code` the rest of `on_import`; `imports` is None when imports must be read as module
    code, as `on_import` holds them.
    """

    on_import: list[tuple[str, str]] = field(default_factory=list)  # (what it is, its syntax) in order
    code: dict[str, str] = field(default_factory=dict)  # part -> the syntax of its definitions
    run_on_import: dict[str, list[ast.AST]] = field(default_factory=dict)  # part -> what defining it runs
    places: list[tuple[str, str]] = field(default_factory=list)  # (the class or the module, part), in order
    rebinding: set[str] = field(default_factory=set)  # parts that assign a module name (`global`)
    imports: list[ast.stmt] | None = None
    module_code: list[tuple[str, str]] = field(default_factory=list)
    uses: dict[str, set[str]] = field(default_factory=dict)  # part -> every name its code mentions
    reads_on_import: set[str] = field(default_factory=set)  # names code run on import mentions
    # Module names a definition binds; module code's own are among the names it mentions.
    binds_on_import: set[str] = field(default_factory=set)
    computed_reads: bool = False  # it reads module names by a name it computes (`globals()`)


def outline_container(text: str | None) -> ContainerOutline | str:
    """One side of `container.py` outlined part by part; why it cannot be, as a string."""
    if text is None:
        return "it is missing on one side"
    try:
        syntax = ast.parse(text)
    except (SyntaxError, ValueError):
        return "one side does not parse"
    classes = [
        node for node in syntax.body if isinstance(node, ast.ClassDef) and node.name == CONTAINER_CLASS
    ]
    if len(classes) != 1:
        return f"one side has no single {CONTAINER_CLASS} class"
    postponed = any(
        isinstance(statement, ast.ImportFrom)
        and statement.module == "__future__"
        and any(alias.name == "annotations" for alias in statement.names)
        for statement in syntax.body
    )
    outline = ContainerOutline()
    definitions: dict[str, list[ast.stmt]] = {}

    def add_part(place: str, definition: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> None:
        definitions.setdefault(definition.name, []).append(definition)
        outline.places.append((place, definition.name))
        outline.run_on_import.setdefault(definition.name, []).extend(run_on_import(definition, postponed))

    container_class = classes[0]
    outline.imports = leading_imports(syntax)
    read_by_use = {id(statement) for statement in outline.imports or ()}
    runs: list[ast.AST] = []  # the code that runs on import, the imports read by use left out

    def runs_on_import(item: tuple[str, str], *code: ast.AST) -> None:
        outline.on_import.append(item)
        outline.module_code.append(item)
        runs.extend(code)

    for statement in syntax.body:
        if statement is container_class:
            header = evaluated_with_the_definition(container_class)
            runs_on_import((f"{CONTAINER_CLASS}'s bases and decorators", dump_all(header)), *header)
            for member in container_class.body:
                is_method = isinstance(member, ast.FunctionDef | ast.AsyncFunctionDef)
                if is_method and not (member.name.startswith("__") and member.name.endswith("__")):
                    add_part(CONTAINER_CLASS, member)
                else:
                    runs_on_import((what_runs(member, CONTAINER_CLASS), ast.dump(member)), member)
        elif isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            add_part("module", statement)
            outline.binds_on_import.add(statement.name)
        elif id(statement) in read_by_use:
            outline.on_import.append((what_runs(statement, None), ast.dump(statement)))
            if isinstance(statement, ast.If):
                runs.append(statement.test)  # `TYPE_CHECKING` itself is read on import
        else:
            runs_on_import((what_runs(statement, None), ast.dump(statement)), statement)
    outline.binds_on_import.add(CONTAINER_CLASS)
    for name, defined in definitions.items():
        outline.code[name] = dump_all(defined)
        outline.uses[name] = names_in(*defined)
        runs.extend(outline.run_on_import[name])
        if any(isinstance(node, ast.Global) for definition in defined for node in ast.walk(definition)):
            outline.rebinding.add(name)
    # A name in a string counts too: `__all__`'s, or a `getattr` with a literal name.
    outline.reads_on_import = names_in(*runs) | {
        string for node in runs for string in strings_in(node) if string.isidentifier()
    }
    outline.computed_reads = bool(COMPUTED_NAME_READS & (names_in(syntax) | definitions.keys()))
    return outline


def leading_imports(syntax: ast.Module) -> list[ast.stmt] | None:
    """The imports at the top of a module, after its docstring, read by what they load and bind (v1-e41-t06).

    They are the plain imports and the `if TYPE_CHECKING:` blocks of imports before any other
    statement; a `from __future__` import stays module code. None when an import is anywhere else
    at module level, or a star import binds names it does not list: then the imports are read as
    module code, in order, as before.
    """
    body = syntax.body
    start = 1 if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) else 0
    section: list[ast.stmt] = []
    end = start
    while end < len(body) and (
        isinstance(body[end], ast.Import | ast.ImportFrom) or is_typing_block(body[end])
    ):
        statement = body[end]
        if not (isinstance(statement, ast.ImportFrom) and statement.module == "__future__"):
            section.append(statement)
        end += 1
    if any(imports_at_module_level(statement) for statement in body[end:]):
        return None
    for statement in section:
        for node in statement.body if isinstance(statement, ast.If) else [statement]:
            if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
                return None
    return section


def is_typing_block(statement: ast.stmt) -> bool:
    """`if TYPE_CHECKING:` holding only imports, with no `else`: nothing in it runs."""
    if not isinstance(statement, ast.If) or statement.orelse or not statement.body:
        return False
    test = statement.test
    named = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute)
        and test.attr == "TYPE_CHECKING"
        and isinstance(test.value, ast.Name)
        and test.value.id == "typing"
    )
    return named and all(isinstance(node, ast.Import | ast.ImportFrom) for node in statement.body)


def imports_at_module_level(statement: ast.stmt) -> bool:
    """Whether a statement binds a module name by an import: in a function or a class body it does not."""
    if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return False
    if isinstance(statement, ast.Import | ast.ImportFrom):
        return True
    return any(
        imports_at_module_level(child)
        for child in ast.iter_child_nodes(statement)
        if isinstance(child, ast.stmt)
    )


def run_on_import(definition: ast.stmt, postponed: bool) -> list[ast.AST]:
    """What defining a part runs: decorators and defaults, a class's body but its methods' bodies,
    and annotations unless `from __future__ import annotations` postpones them."""
    found = list(evaluated_with_the_definition(definition))
    if isinstance(definition, ast.ClassDef):
        for member in definition.body:
            if isinstance(member, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                found.extend(run_on_import(member, postponed))
            else:
                found.append(member)
    elif isinstance(definition, ast.FunctionDef | ast.AsyncFunctionDef) and not postponed:
        arguments = definition.args
        every = [
            *arguments.posonlyargs,
            *arguments.args,
            *arguments.kwonlyargs,
            arguments.vararg,
            arguments.kwarg,
        ]
        found.extend(
            argument.annotation for argument in every if argument is not None and argument.annotation
        )
        if definition.returns is not None:
            found.append(definition.returns)
    return found


def dump_all(nodes: Iterable[ast.AST]) -> str:
    return "\n".join(ast.dump(node) for node in nodes)


def what_runs(statement: ast.stmt, within: str | None) -> str:
    """How a reader names a statement module code runs, for the reason a change is read whole."""
    if isinstance(statement, ast.Import | ast.ImportFrom):
        kind = "an import"
    elif isinstance(statement, ast.Assign | ast.AnnAssign | ast.AugAssign):
        kind = f"a class attribute of {within}" if within else "a module constant"
    elif isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        kind = f"{within}.{statement.name}" if within else statement.name
    elif isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant):
        kind = f"{within}'s docstring" if within else "the module docstring"
    elif isinstance(statement, ast.If):
        kind = "an `if` block"
    else:
        kind = "module code"
    return f"{kind} (line {statement.lineno})"


def is_inert(nodes: list[ast.AST]) -> bool:
    """Whether what defining a part runs can neither fail nor reach anything: literals and `@property`."""
    return all(
        isinstance(node, INERT_NODES) or (isinstance(node, ast.Name) and node.id in INERT_DECORATORS)
        for top in nodes
        for node in ast.walk(top)
    )


def container_diff(
    old_text: str | None,
    new_text: str | None,
    old_modules: Callable[[], Modules] = Modules,
    new_modules: Callable[[], Modules] = Modules,
) -> ContainerDiff:
    """Compare two sides of `container.py` part by part, failing toward the whole file.

    A part's code changing, or a new part, is that part's. The whole file is changed by anything
    that runs on import: a module constant, the container's own attributes, docstring and dunder
    methods, any part's decorators, defaults or class body (a new part may add only `@property`,
    `@staticmethod`, `@classmethod` and literal defaults); and by a part removed, renamed or moved,
    a changed part that assigns a module name, and a side that cannot be read.

    The imports at the top are read by use (v1-e41-t06): when they load the same modules in the same
    order on both sides, nothing new runs on import, and a name they rebind is the change of the
    parts that use it. A module loaded, or no longer loaded, is the whole file, and so is a rebound
    name that code run on import uses. `old_modules` and `new_modules` say which names are modules on
    each side, asked only when the imports differ.
    """
    old, new = outline_container(old_text), outline_container(new_text)
    if isinstance(old, str) or isinstance(new, str):
        return ContainerDiff(whole=old if isinstance(old, str) else str(new))
    by_use = old.imports is not None and new.imports is not None
    what = (
        first_difference(old.module_code, new.module_code)
        if by_use
        else first_difference(old.on_import, new.on_import)
    )
    if what is not None:
        return ContainerDiff(whole=f"it changes {what}, which runs when the module is imported")
    rebound: frozenset[str] = frozenset()
    if by_use:
        read = imports_by_use(old, new, old_modules, new_modules)
        if isinstance(read, str):
            return ContainerDiff(whole=read)
        rebound = read
    removed = sorted(old.code.keys() - new.code.keys())
    if removed:
        return ContainerDiff(whole=f"it removes or renames {removed[0]}")
    kept = old.code.keys() & new.code.keys()

    def order(outline: ContainerOutline) -> list[tuple[str, str]]:
        return [place for place in dict.fromkeys(outline.places) if place[1] in kept]

    if order(old) != order(new):
        return ContainerDiff(whole="it moves a part, and a class body runs in order")
    changed: set[str] = set()
    for part in sorted(kept):
        if dump_all(old.run_on_import[part]) != dump_all(new.run_on_import[part]):
            return ContainerDiff(
                whole=f"it changes what defining {part} runs on import: a decorator, a default, a class body"
            )
        if old.code[part] != new.code[part]:
            changed.add(part)
    for part in sorted(new.code.keys() - kept):
        if not is_inert(new.run_on_import[part]):
            return ContainerDiff(
                whole=f"the new {part} runs code on import: a decorator, a default or a class body"
            )
        changed.add(part)
    uses: dict[str, frozenset[str]] = {}
    for part in sorted(new.code.keys() - changed):
        used = rebound & (new.uses[part] | old.uses.get(part, set()))
        if used:
            uses[part] = frozenset(used)
    rebinding = sorted((changed | uses.keys()) & (old.rebinding | new.rebinding))
    if rebinding:
        return ContainerDiff(whole=f"{rebinding[0]} assigns a module name, which every part reads")
    return ContainerDiff(parts=frozenset(changed | uses.keys()), names=rebound, uses=uses)


def first_difference(old: list[tuple[str, str]], new: list[tuple[str, str]]) -> str | None:
    """What the first statement run on import that differs is; None when none does."""
    for index in range(max(len(old), len(new))):
        # Compared without the labels, whose line numbers move when a part above grows.
        before = old[index] if index < len(old) else None
        after = new[index] if index < len(new) else None
        if before is None or after is None or before[1] != after[1]:
            return (after or before or ("module code", ""))[0]
    return None


@dataclass
class ImportReading:
    """What one side's imports at the top do (v1-e41-t06): the modules they load, in the order they
    are first loaded, with the line that first loads each, and what each name is bound to, in order."""

    loads: dict[str, int] = field(default_factory=dict)
    binds: dict[str, list[str]] = field(default_factory=dict)


def read_imports(statements: list[ast.stmt], modules: Modules) -> ImportReading:
    """The modules a side's imports load, and what they bind.

    `import a.b` loads `a` and `a.b` and binds `a`; `from a.b import c` loads `a`, `a.b`, and
    `a.b.c` unless `c` is known not to be a module. An `if TYPE_CHECKING:` block loads nothing,
    since it never runs; its names are bound for the type checker only, and a change to them is read
    by the parts that use them like any other.
    """
    reading = ImportReading()

    def load(module: str, line: int) -> None:
        names = module.split(".")
        for depth in range(1, len(names) + 1):
            reading.loads.setdefault(".".join(names[:depth]), line)

    for statement in statements:
        typing_only = isinstance(statement, ast.If)
        kind = "for the type checker only, " if typing_only else ""
        for node in statement.body if isinstance(statement, ast.If) else [statement]:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if not typing_only:
                        load(alias.name, node.lineno)
                    bound = alias.asname or alias.name.split(".")[0]
                    target = alias.name if alias.asname else bound
                    reading.binds.setdefault(bound, []).append(f"{kind}the module {target}")
            elif isinstance(node, ast.ImportFrom):
                package = CONTAINER_MODULE.split(".")[: -node.level] if node.level else []
                module = ".".join([*package, *([node.module] if node.module else [])])
                if not typing_only:
                    load(module, node.lineno)
                for alias in node.names:
                    if not typing_only and modules.is_module(f"{module}.{alias.name}") is not False:
                        load(f"{module}.{alias.name}", node.lineno)
                    reading.binds.setdefault(alias.asname or alias.name, []).append(
                        f"{kind}{alias.name} from {module}"
                    )
    return reading


def imports_by_use(
    old: ContainerOutline,
    new: ContainerOutline,
    old_modules: Callable[[], Modules],
    new_modules: Callable[[], Modules],
) -> frozenset[str] | str:
    """The names two sides' imports at the top rebind; why the change is the whole file, as a string.

    It is the whole file when the imports load a module the other side's do not, or load the same
    modules in another order, or rebind a name that code run on import uses or that module code
    binds too, or when the module reads its names by a name it computes.
    """
    if dump_all(old.imports or ()) == dump_all(new.imports or ()):
        return frozenset()
    before, after = (
        read_imports(old.imports or [], old_modules()),
        read_imports(new.imports or [], new_modules()),
    )
    for module, line in after.loads.items():
        if module not in before.loads:
            return f"it loads {module}, which its imports did not load before (line {line})"
    for module, line in before.loads.items():
        if module not in after.loads:
            return f"it no longer loads {module}, which its imports loaded (line {line})"
    if list(before.loads) != list(after.loads):
        return "it changes the order in which its imports load modules"
    rebound = frozenset(
        name
        for name in before.binds.keys() | after.binds.keys()
        if before.binds.get(name) != after.binds.get(name)
    )
    for name in sorted(rebound):
        if name in old.reads_on_import | new.reads_on_import:
            return f"it rebinds {name}, which code run on import uses"
        if name in old.binds_on_import | new.binds_on_import:
            return f"it rebinds {name}, which module code binds too"
    if rebound and (old.computed_reads or new.computed_reads):
        return f"it rebinds {sorted(rebound)[0]}, and the module reads names by a name it computes"
    return rebound


def reads_the_container_whole(syntax: ast.AST) -> bool:
    """Whether a file reads the container class by reflection, or the container module as source.

    Reflection is a call such as `vars(...)`, `inspect.getmembers(...)` or a `getattr` with a name
    it computes, on something named for the container (`ServiceContainer`, `container`,
    `services`). Source is the container's module name, or path, in a string: what the post-install
    check reads its imports from.
    """
    holders = {CONTAINER_CLASS, "container", "services"}
    for node in ast.walk(syntax):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and (node.value == CONTAINER_MODULE or node.value.endswith("debate_cli/container.py"))
        ):
            return True
        if not isinstance(node, ast.Call) or not node.args:
            continue
        function = node.func
        name = function.attr if isinstance(function, ast.Attribute) else getattr(function, "id", "")
        computed = name in ("getattr", "hasattr") and not (
            len(node.args) > 1 and isinstance(node.args[1], ast.Constant)
        )
        if (name in REFLECTION_CALLS or computed) and names_in(node.args[0]) & holders:
            return True
    return False


def container_readers(syntax: ast.Module) -> set[str] | None:
    """A module's top-level names that read the container whole, and what uses them; None if module code does.

    `debate_cli/installation.py` reads the container's imports in `wired_integrations`, and
    `check_installation` and `main` call it, but `app.py` imports the module for
    `incomplete_installation_failure` alone. A file that uses a reading name has every part; one
    that imports the module for something else does not. An `if __name__ == "__main__":` block is
    left out: it runs only when the module is run, and a file that runs it has every part.
    """
    defined: dict[str, list[ast.stmt]] = {}
    module_code: list[ast.stmt] = []
    for statement in syntax.body:
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            defined.setdefault(statement.name, []).append(statement)
        elif isinstance(statement, ast.Assign | ast.AnnAssign):
            targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
            for target in targets:
                for node in ast.walk(target):
                    if isinstance(node, ast.Name):
                        defined.setdefault(node.id, []).append(statement)
        elif not isinstance(statement, ast.Import | ast.ImportFrom) and not runs_only_as_a_program(statement):
            module_code.append(statement)
    readers = {
        name for name, statements in defined.items() if any(map(reads_the_container_whole, statements))
    }
    while True:
        more = {name for name, statements in defined.items() if names_in(*statements) & readers} - readers
        if not more:
            break
        readers |= more
    if any(
        reads_the_container_whole(statement) or names_in(statement) & readers for statement in module_code
    ):
        return None
    return readers


def runs_only_as_a_program(statement: ast.stmt) -> bool:
    """`if __name__ == "__main__":`."""
    test = statement.test if isinstance(statement, ast.If) else None
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and any(isinstance(item, ast.Constant) and item.value == "__main__" for item in test.comparators)
    )


def add_container_parts(tree: Tree, layout: Layout, graph: Graph, reading: ContainerReading) -> None:
    """The container's parts as nodes, and each file that can hold a container reaching the parts it names.

    A file can hold one if it is a `debate_cli` module, which can be handed `cli.services`, or it
    imports one. It reaches a part it names as an attribute (`cli.services.removal()`), a name or
    a quoted word; one that reads the container whole reaches every part. A file that does not
    parse reaches every part too.
    """
    graph.container_parts = frozenset(reading.part_files)
    for part, files in sorted(reading.part_files.items()):
        node = part_of(CONTAINER, part)
        graph.labels[node] = f"{CONTAINER_MODULE}'s {part} ({CONTAINER})"
        for file in sorted(files):
            graph.add(node, IMPORTS, file)
        for called in sorted(reading.part_calls[part]):
            graph.add(node, CALLS, part_of(CONTAINER, called))
    for file in sorted(reading.module_files):
        graph.add(CONTAINER, IMPORTS, file)
    for part in sorted(reading.module_parts):
        graph.add(CONTAINER, USES, part_of(CONTAINER, part))
    cli_files = {path for path in layout.path_modules if path.startswith(f"{CLI_SOURCE}/")}
    holders = set(cli_files)
    for target in cli_files:
        holders |= {dependent for dependent, how in graph.dependents.get(target, ()) if how == IMPORTS}
    # The container's own parts import CLI modules too (`package_version`); they are what is held.
    holders = {holder for holder in holders if holder != CONTAINER and PART not in holder}
    every_part = sorted(reading.part_files)
    for holder in sorted(holders):
        syntax = tree.syntax(holder) if holder.endswith(".py") else None
        readers = container_readers(syntax) if syntax is not None else None
        if syntax is None or reads_the_container_whole(syntax):
            graph.container_readers.add(holder)
        if readers is None or (readers and holder not in layout.path_modules):
            for part in every_part:
                graph.add(holder, READS_EVERY_PART, part_of(CONTAINER, part))
            continue
        assert syntax is not None
        named = names_in(syntax) & reading.part_files.keys()
        named |= {
            node.value
            for node in ast.walk(syntax)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value in reading.part_files
        }
        for part in sorted(named):
            graph.add(holder, ASKS, part_of(CONTAINER, part))
        if not readers:
            continue
        # A module whose functions read the container whole: the files that call them, or run it, do.
        for dependent, how in list(graph.dependents.get(holder, ())):
            if PART in dependent:
                continue
            used = tree.syntax(dependent) if dependent.endswith(".py") else None
            if how == RUNS or (how == IMPORTS and (used is None or names_in(used) & readers)):
                for part in every_part:
                    graph.add(dependent, READS_EVERY_PART, part_of(CONTAINER, part))


def add_container_names(tree: Tree, graph: Graph, reading: ContainerReading) -> None:
    """A file naming the container module only in `debate_cli.container.X` strings asks for X (v1-e41-t06).

    Such a string is a `monkeypatch.setattr` target, or a module's name for `importlib`. When X is
    a part, or `ServiceContainer.X` is, the file asks for that part. Any other X is a name the
    container imports or defines at module level, which a change to the file's imports reaches if
    it rebinds X, and any other change only as the whole file. A file that names the module any
    other way, alone or as a path, is still reached by that name.
    """
    for path, text in tree.texts.items():
        if not path.endswith(".py") or ("container.py" not in text and CONTAINER_MODULE not in text):
            continue
        named = container_names(tree.strings(path))
        if not named:
            continue
        others: set[str] = set()
        for name, attribute in named:
            if name in reading.part_files:
                graph.add(path, ASKS, part_of(CONTAINER, name))
            elif name == CONTAINER_CLASS and attribute in reading.part_files:
                graph.add(path, ASKS, part_of(CONTAINER, attribute))
            else:
                others.add(name)
        graph.container_named[path] = frozenset(others)


def container_names(strings: list[str] | None) -> set[tuple[str, str | None]]:
    """The names a file's strings name as `debate_cli.container.X[.Y]`; none if they name it another way."""
    named: set[tuple[str, str | None]] = set()
    for string in strings or ():
        if not NAMES_THE_CONTAINER.search(string):
            continue
        match = CONTAINER_NAME.fullmatch(string)
        if match is None:
            return set()
        named.add((match.group(1), match.group(2)))
    return named


def read_registry(tree: Tree, layout: Layout) -> dict[str, list[tuple[str, ...]]] | None:
    """Each command module `register_commands` registers -> its commands, as their words; None if unreadable.

    It reads the function's statements one by one: a group made with a call whose first argument is
    its name, `<group>.command("<name>")(<module>.<function>)`, and `<parent>.add_typer(<group>)`.
    Any other statement, or a group never added, means it cannot tell, and the registry is read as
    a file: every command reaches the app whole.
    """
    syntax = tree.syntax(COMMAND_REGISTRY)
    if syntax is None:
        return None
    functions = [
        node
        for node in syntax.body
        if isinstance(node, ast.FunctionDef) and node.name == REGISTERING_FUNCTION
    ]
    if len(functions) != 1 or not functions[0].args.args:
        return None
    root = functions[0].args.args[0].arg
    modules: dict[str, str] = {}  # the name a module is imported as -> its file
    for node in syntax.body:
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            for alias in node.names:
                module = layout.module_paths.get(f"{node.module}.{alias.name}")
                if module is not None:
                    modules[alias.asname or alias.name] = module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname and alias.name in layout.module_paths:
                    modules[alias.asname] = layout.module_paths[alias.name]
    groups: dict[str, str] = {}  # variable -> the group's word
    parents: dict[str, str] = {}  # group variable -> the variable it is added to
    commands: list[tuple[str, str, str]] = []  # (group variable, word, module file)
    for statement in functions[0].body:
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant):
            continue  # the docstring
        value = statement.value if isinstance(statement, ast.Expr | ast.Assign) else None
        if (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and isinstance(value, ast.Call)
            and value.args
            and isinstance(value.args[0], ast.Constant)
            and isinstance(value.args[0].value, str)
        ):
            groups[statement.targets[0].id] = value.args[0].value
            continue
        if not isinstance(statement, ast.Expr) or not isinstance(value, ast.Call):
            return None
        function = value.func
        if (  # <group>.command("<word>")(<module>.<function>)
            isinstance(function, ast.Call)
            and isinstance(function.func, ast.Attribute)
            and function.func.attr == "command"
            and isinstance(function.func.value, ast.Name)
            and len(function.args) == 1
            and isinstance(function.args[0], ast.Constant)
            and isinstance(function.args[0].value, str)
            and len(value.args) == 1
            and isinstance(value.args[0], ast.Attribute)
            and isinstance(value.args[0].value, ast.Name)
            and value.args[0].value.id in modules
        ):
            commands.append((function.func.value.id, function.args[0].value, modules[value.args[0].value.id]))
        elif (  # <parent>.add_typer(<group>)
            isinstance(function, ast.Attribute)
            and function.attr == "add_typer"
            and isinstance(function.value, ast.Name)
            and len(value.args) == 1
            and isinstance(value.args[0], ast.Name)
            and value.args[0].id in groups
        ):
            parents[value.args[0].id] = function.value.id
        else:
            return None

    def words_of(variable: str, depth: int = 0) -> tuple[str, ...] | None:
        if variable == root:
            return ()
        if variable not in groups or variable not in parents or depth > len(groups):
            return None
        above = words_of(parents[variable], depth + 1)
        return None if above is None else (*above, groups[variable])

    registered: dict[str, list[tuple[str, ...]]] = {}
    for variable, word, module in commands:
        above = words_of(variable)
        if above is None:
            return None
        registered.setdefault(module, []).append((*above, word))
    return registered


def add_app_commands(layout: Layout, graph: Graph, registered: dict[str, list[tuple[str, ...]]]) -> None:
    """The app for each command module as a node, reached from that module and judged by who names it."""
    for module, commands in sorted(registered.items()):
        node = part_of(APP, layout.path_modules[module])
        graph.app_commands[node] = tuple(commands)
        shown = listed([f"`{' '.join(command)}`" for command in commands])
        graph.labels[node] = f"{layout.show(APP)} for {shown}"
        graph.add(node, REGISTERS, module)
        for command in commands:
            for depth, word in enumerate(command):
                graph.command_children.setdefault(command[:depth], set()).add(word)


def listed(items: list[str]) -> str:
    """`a`, `a and b`, `a, b and c`."""
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


@dataclass(frozen=True)
class Run:
    """Consecutive literal words a file passes or keeps together: an argument vector, or part of one.

    `open_end` is whether something that is not a literal follows them (`*arguments`, a name), so
    that a helper's `("tub", "users", *arguments)` can be finished by its caller's `("add", ...)`.
    """

    words: tuple[str, ...]
    open_end: bool

    def holds(self, sequence: tuple[str, ...]) -> bool:
        width = len(sequence)
        return any(
            self.words[start : start + width] == sequence for start in range(len(self.words) - width + 1)
        )


def argument_runs(tree: Tree, path: str, starters: frozenset[str]) -> frozenset[Run]:
    """The runs of literal words in a file: what its calls, lists, tuples and assigned constants hold.

    A string with whitespace is a command line when it starts with one of `starters` (the console
    script, a command's first word, an option); otherwise it is prose, and ends the run like any
    other value. A file that is not Python, or does not parse, gives each line's words.
    """
    syntax = tree.syntax(path) if path.endswith(".py") else None
    if syntax is None:
        lines = tree.texts.get(path, "").splitlines()
        return frozenset(Run(tuple(line.split()), True) for line in lines if line.split())
    sequences: list[list[ast.expr]] = []
    for node in ast.walk(syntax):
        if isinstance(node, ast.Call):
            sequences.append(list(node.args))
        elif isinstance(node, ast.List | ast.Tuple | ast.Set):
            sequences.append(list(node.elts))
        elif isinstance(node, ast.Assign | ast.AnnAssign) and isinstance(node.value, ast.Constant):
            sequences.append([node.value])
    runs: set[Run] = set()
    for elements in sequences:
        words: list[str] = []
        for element in elements:
            pieces = None
            if isinstance(element, ast.Constant) and isinstance(element.value, str):
                pieces = element.value.split() or [element.value]
                if len(pieces) > 1 and not (pieces[0] in starters or pieces[0].startswith("-")):
                    pieces = None
            if pieces is None:
                if words:
                    runs.add(Run(tuple(words), True))
                words = []
            else:
                words.extend(pieces)
        if words:
            runs.add(Run(tuple(words), False))
    return frozenset(runs)


def names_command(runs: frozenset[Run], command: tuple[str, ...]) -> bool:
    """Whether runs of literal words name `command`.

    * All its words in one run: `("caselist", "remove", "--team", "T")`.
    * Its first words ending a run something else follows, and the rest in any run: a helper's
      `("tub", "users", *arguments)` and its caller's `("add", "--email", email)`.
    * Its group alone, ending a run: `("caselist",)` shows the group's help, which lists every
      command in it.
    """
    if any(run.holds(command) for run in runs):
        return True
    for depth in range(1, len(command)):
        group = command[:depth]
        ends = [run for run in runs if run.words[-depth:] == group]
        if any(not run.open_end for run in ends):
            return True
        if any(run.open_end for run in ends) and any(run.holds(command[depth:]) for run in runs):
            return True
    return False


def names_any_command(runs: frozenset[Run], top: set[str]) -> bool:
    """Whether a run holds any top-level command's word: otherwise nothing tells which command it runs."""
    return any(top.intersection(run.words) for run in runs)


def passes_help(runs: frozenset[Run], top: set[str]) -> bool:
    """Whether a run asks for the root's help, which lists every command: `--help` with no command before it.

    `("files", "build", "--help")` is `files build`'s own help, and names that command.
    """
    for run in runs:
        for position, word in enumerate(run.words):
            if word in HELP_FLAGS and not top.intersection(run.words[:position]):
                return True
    return False


def grimp_edges(tree: Tree, layout: Layout, graph: Graph) -> dict[str, set[str]] | None:
    """Direct imports between the workspace packages' modules, from grimp; None if it cannot read them."""
    if not layout.packages:
        return {}
    import grimp

    with contextlib.ExitStack() as stack:
        if tree.revision is None:
            src_directories = sorted({str(tree.root / src) for src in layout.packages.values()})
        else:
            copy = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="affected-tests-")))
            for path in layout.path_modules:
                target = copy / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(tree.texts.get(path, ""), encoding="utf-8")
            src_directories = sorted({str(copy / src) for src in layout.packages.values()})
        saved_path = list(sys.path)
        sys.path[:0] = src_directories
        importlib.invalidate_caches()
        try:
            built = grimp.build_graph(*sorted(layout.packages), cache_dir=None)
        except Exception as error:  # grimp refuses a package with a syntax error in it, among others
            graph.notes.append(
                f"grimp could not read the packages ({error}); their imports were read with ast."
            )
            return None
        finally:
            sys.path[:] = saved_path
    unknown = set(built.modules) - set(layout.module_paths)
    if unknown:
        graph.notes.append(
            "grimp found modules this tree does not have; the packages' imports were read with ast."
        )
        return None
    return {module: set(built.find_modules_directly_imported_by(module)) for module in built.modules}


class Resolver:
    """Turns an import statement in one file into the files of this repository it runs."""

    def __init__(self, layout: Layout, every_mention_runs: bool = False) -> None:
        self.layout = layout
        self.every_mention_runs = every_mention_runs
        self.paths = layout.tree.paths
        self.folders_by_top_name: dict[str, set[str]] = {}
        for path in self.paths:
            if not path.endswith(".py") or layout.is_package_file(path):
                continue
            pure = PurePosixPath(path)
            if pure.name == "__init__.py":
                self.folders_by_top_name.setdefault(pure.parent.name, set()).add(str(pure.parent.parent))
            else:
                self.folders_by_top_name.setdefault(pure.stem, set()).add(str(pure.parent))

    def imports_of(self, path: str) -> set[str]:
        syntax = self.layout.tree.syntax(path)
        found: set[str] = set()
        for level, module, names in imported_names(syntax) if syntax is not None else ():
            found |= self.resolve(path, level, module, names)
        return found

    def resolve(self, importer: str, level: int, module: str, names: tuple[str, ...]) -> set[str]:
        parts = [part for part in module.split(".") if part]
        if level:
            base = PurePosixPath(importer).parent
            for _ in range(level - 1):
                base = base.parent
            if self.layout.is_package_file(importer):
                package = self.layout.path_modules[importer]
                if PurePosixPath(importer).name != "__init__.py":
                    package = package.rpartition(".")[0]
                for _ in range(level - 1):
                    package = package.rpartition(".")[0]
                dotted = ".".join([package, *parts]) if parts else package
                return self.in_packages(dotted, names)
            return self.under(base, parts, names)
        if parts and parts[0] in self.layout.packages:
            return self.in_packages(module, names)
        found = self.under(PurePosixPath("."), parts, names)
        if found or not parts:
            return found
        for folder in sorted(self.folders_by_top_name.get(parts[0], ())):
            found |= self.under(PurePosixPath(folder), parts, names)
        return found

    def in_packages(self, module: str, names: tuple[str, ...]) -> set[str]:
        modules = self.layout.module_paths
        found = {
            modules[candidate]
            for candidate in (module, *(f"{module}.{name}" for name in names))
            if candidate in modules
        }
        prefix = module
        while not found and prefix:
            if prefix in modules:
                found.add(modules[prefix])
            prefix = prefix.rpartition(".")[0]
        return found

    def under(self, base: PurePosixPath, parts: list[str], names: tuple[str, ...]) -> set[str]:
        """The files `import parts` (or `from parts import names`) runs, relative to `base`."""
        found: set[str] = set()
        folder = base
        for part in parts[:-1]:
            folder = folder / part
            self.add_if_present(found, folder / "__init__.py")
        if parts:
            last = folder / parts[-1]
            module_file = self.present(last.with_suffix(".py")) or self.present(last / "__init__.py")
            if module_file is None and not self.is_folder(last):
                return set()
            if module_file is not None:
                found.add(module_file)
            folder = last
        else:
            self.add_if_present(found, folder / "__init__.py")
        for name in names:
            self.add_if_present(found, (folder / name).with_suffix(".py"))
            self.add_if_present(found, folder / name / "__init__.py")
        return found

    def present(self, path: PurePosixPath) -> str | None:
        text = str(path)
        return text if text in self.paths else None

    def add_if_present(self, found: set[str], path: PurePosixPath) -> None:
        present = self.present(path)
        if present is not None:
            found.add(present)

    def is_folder(self, path: PurePosixPath) -> bool:
        prefix = "" if str(path) == "." else str(path) + "/"
        return any(candidate.startswith(prefix) for candidate in self.paths)

    def runs_of(self, text: str, strings: list[str] | None = None) -> set[str]:
        """The modules a file runs as a program: a console script it runs, or `-m module`.

        `strings` are a Python file's string literals, and a console script runs only where one of
        them starts the program (:func:`starts_the_program`, v1-e01-t44). A file without them, such
        as a shell script, runs any console script it names, as does every file under
        `--every-mention-runs`.
        """
        found: set[str] = set()
        for script, module in self.layout.console_scripts.items():
            mention = re.compile(rf"(?<![\w-]){re.escape(script)}(?![\w-])")
            if strings is None or self.every_mention_runs:
                runs = mention.search(text) is not None
            else:
                runs = any(
                    starts_the_program(string, match.start(), match.end())
                    for string in strings
                    for match in mention.finditer(string)
                )
            if runs:
                found |= self.in_packages(module, ())
        for module in MODULE_FLAG.findall(text):
            top = module.split(".")[0]
            if top in self.layout.packages:
                found |= self.in_packages(module, ("__main__",))
        return found


def starts_the_program(string: str, start: int, end: int) -> bool:
    """Whether a console script's name at `string[start:end]` runs it, rather than mentioning it in prose.

    Read on the name's own line of the string, from the start of the line:

    * Another name, never a run: one the name ends (`~/.debate-research`), or one a slash goes on
      from: a folder (`/var/lib/debate-research/dev`), the User-Agent's `debate-research/<version>`.
    * A run: the program alone (an argument list's first word, `shutil.which`'s argument), a line
      that starts with it (a command line, a line of a script), or a path to it (`f"{bin}/..."`).
    * Prose, when a sentence comes before it: words, with no option, ending in a word a sentence
      ends a phrase with (`Fix:`, `installed`, `of`), and not a program that runs its arguments
      (`run`, `exec`, `env`). Around a code span or a quote that holds the name, the sentence is
      the text before its opening mark. A code span may also open the line, as a fragment a
      message joins into its sentence does (`` "`debate-research caselist parse`" ``).
    * Anything else is a run: shell syntax (`&&`, `X=1`), an option or a runner before the name.
    """
    lead = string[string.rfind("\n", 0, start) + 1 : start]
    if lead.endswith(".") or string[end : end + 1] in PATH_SEPARATORS:
        return False
    if string.strip() == string[start:end]:
        return True
    if not lead.strip():
        return True
    if lead.endswith(PATH_SEPARATORS):
        return True
    if lead.count("`") % 2:
        before = lead[: lead.rfind("`")]
        return bool(before.strip()) and not reads_as_a_sentence(before, runner_runs_it=False)
    if lead.endswith(QUOTE_MARKS):
        return not reads_as_a_sentence(lead[:-1], runner_runs_it=True)
    return not reads_as_a_sentence(lead, runner_runs_it=True)


def reads_as_a_sentence(lead: str, runner_runs_it: bool) -> bool:
    """Whether text before a name is a sentence's, not a command line's, by its words and its last word.

    `runner_runs_it` is whether a last word that runs its arguments (`run`, `exec`) runs the name.
    Before a code span it does not: a sentence holds the span (``Never run `...` ``).
    """
    words = CODE_SPAN.sub("code", lead).split()
    return bool(
        words
        and not any(word.startswith("-") for word in words)
        and SENTENCE_WORD.fullmatch(words[-1])
        and not (runner_runs_it and words[-1] in RUNS_ITS_ARGUMENTS)
    )


def imported_names(tree: ast.AST) -> Iterator[tuple[int, str, tuple[str, ...]]]:
    """Every import in a module, nested ones included, and `importlib.import_module("x")` calls."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield 0, alias.name, ()
        elif isinstance(node, ast.ImportFrom):
            yield node.level, node.module or "", tuple(alias.name for alias in node.names)
        elif isinstance(node, ast.Call) and node.args:
            function = node.func
            name = function.attr if isinstance(function, ast.Attribute) else getattr(function, "id", "")
            argument = node.args[0]
            if name in ("import_module", "__import__") and isinstance(argument, ast.Constant):
                value = argument.value
                if isinstance(value, str):
                    yield 0, value, ()


# --------------------------------------------------------------------------------------------
# Mentions: who names a file
# --------------------------------------------------------------------------------------------


class Haystack:
    """Many files' texts in one string, so a set of names is found in one pass."""

    def __init__(self, texts: dict[str, str]) -> None:
        self.paths = sorted(texts)
        self.starts: list[int] = []
        pieces: list[str] = []
        offset = 0
        for path in self.paths:
            self.starts.append(offset)
            pieces.append(texts[path])
            offset += len(texts[path]) + 1
        self.text = "\0".join(pieces)

    def holder(self, position: int) -> str:
        return self.paths[bisect.bisect_right(self.starts, position) - 1]


class Corpus:
    """Every searched file's words, searched for file names, and its path segments, for folder names.

    `texts` holds the words a file names other files with; `segments`, the ones it builds paths
    from (v1-e01-t32), which default to all of them. `denoting` maps an existing file or folder to
    the files whose path literals denote it (:class:`PathIndex`); those literals are in neither.
    """

    def __init__(
        self,
        texts: dict[str, str],
        denoting: dict[str, set[str]] | None = None,
        segments: dict[str, str] | None = None,
    ) -> None:
        self.words = Haystack(texts)
        self.segments = self.words if segments is None else Haystack(segments)
        self.denoting = denoting or {}

    def find(self, file_names: Iterable[str], path_parts: Iterable[str]) -> dict[str, set[str]]:
        """For each name, the files holding it: a file name anywhere, a path part between quotes or /.

        A path part shorter than :data:`SHORTEST_QUOTED_WORD` counts only beside a slash: `"s3"` in
        `boto3.client("s3")` is not the stand-in `tests/smoke/stand_ins/s3.py` (v1-e01-t32).
        """
        names = sorted(set(file_names), key=len, reverse=True)
        parts = sorted(set(path_parts), key=len, reverse=True)
        long_parts = [part for part in parts if len(part) >= SHORTEST_QUOTED_WORD]
        short_parts = [part for part in parts if len(part) < SHORTEST_QUOTED_WORD]
        part_alternatives: list[str] = []
        if long_parts:
            part_alternatives.append(
                r"(?<=[\"'/\\`])(?P<part>" + "|".join(map(re.escape, long_parts)) + r")(?=[\"'/\\`])"
            )
        if short_parts:
            short = "|".join(map(re.escape, short_parts))
            part_alternatives.append(
                rf"(?:(?<=/)(?P<short>{short})(?=[\"'/\\`])|(?<=[\"'/\\`])(?P<short_before>{short})(?=/))"
            )
        found: dict[str, set[str]] = {}
        searches: list[tuple[Haystack, str]] = []
        if names:
            searches.append(
                (self.words, r"(?<![\w-])(?P<name>" + "|".join(map(re.escape, names)) + r")(?![\w-])")
            )
        if part_alternatives:
            searches.append((self.segments, "|".join(part_alternatives)))
        for haystack, pattern in searches:
            for match in re.finditer(pattern, haystack.text):
                key = next(value for value in match.groupdict().values() if value)
                found.setdefault(key, set()).add(haystack.holder(match.start()))
        return found

    def denoters(self, path: str, keys: Keys) -> set[str]:
        """The files whose path literals denote `path`, or a folder it is read through."""
        found = set(self.denoting.get(path, ()))
        for folder in keys.folders:
            found |= self.denoting.get(folder, set())
        return found


# --------------------------------------------------------------------------------------------
# Path literals: a quoted string names a file only if it denotes one that exists (v1-e01-t32)
# --------------------------------------------------------------------------------------------


class PathIndex:
    """The existing files and folders, to tell a path literal from a route, a bucket key or a word.

    `known` is the tree's files and the changed files, so a test that names a file the change
    deleted still names it.
    """

    def __init__(self, known: Iterable[str]) -> None:
        self.files = set(known)
        self.folders: set[str] = set()
        for path in self.files:
            for parent in PurePosixPath(path).parents:
                if str(parent) != ".":
                    self.folders.add(str(parent))
        self.by_tail: dict[str, set[str]] = {}
        for path in self.files | self.folders:
            parts = path.split("/")
            for start in range(len(parts)):
                self.by_tail.setdefault("/".join(parts[start:]), set()).add(path)

    def exists(self, path: str) -> bool:
        return path in self.files or path in self.folders

    def denoted(self, text: str, reader: str) -> set[str] | None:
        """The existing paths a string with a slash in `reader` denotes; None when it cannot tell.

        * One that starts with a slash is a route, a bucket key or the tail of an f-string
          (`f"{CORE}/retrieval/identifiers.py"`). It denotes a file only from the repository root
          or from the reader's own folder: `"/account/email/verify"` is not `tests/fixtures/verify/`.
        * Any other denotes every existing path it is the end of, which includes the root, the
          reader's folder and the folders above it, and a base the reader joins it to:
          `PROMPTS / "card/select.md"` is `prompts/card/select.md`.
        * Text after `=` or a `scheme:` is tried too (`--config=tests/x.yaml`). A segment with a
          wildcard or a placeholder ends the path; when the first one does, it cannot tell.

        It cannot tell, either, for text with whitespace in it: that is prose or a command, and its
        words are searched as before.
        """
        if "/" not in text or any(character.isspace() for character in text):
            return None
        candidates = [text]
        if "=" in text:
            candidates.append(text.rsplit("=", 1)[1])
        scheme, colon, rest = text.partition(":")
        if colon and "/" not in scheme and not rest.startswith("//"):
            candidates.append(rest)
        found: set[str] = set()
        for candidate in candidates:
            denoted = self.denoted_by(candidate, reader)
            if denoted is None:
                return None
            found |= denoted
        return found

    def denoted_by(self, text: str, reader: str) -> set[str] | None:
        segments: list[str] = []
        for segment in text.split("/"):
            if WILDCARD.search(segment):
                if not segments:
                    return None
                break
            if segment not in ("", "."):
                segments.append(segment)
        while segments and segments[0] == "..":
            segments.pop(0)
        if not segments or ".." in segments:
            return None
        relative = "/".join(segments)
        if not text.startswith("/"):
            return set(self.by_tail.get(relative, ()))
        folder = PurePosixPath(reader).parent
        beside = relative if str(folder) == "." else f"{folder}/{relative}"
        return {candidate for candidate in (relative, beside) if self.exists(candidate)}


def static_paths(syntax: ast.Module, reader: str) -> dict[int, str]:
    """The repository path each `Path(__file__)`-rooted join in a file builds, by its string's node id.

    `Path(__file__).resolve().parents[1] / "fixtures" / "cards"` in `tests/x/test_y.py` builds
    `tests/fixtures` at its first string and `tests/fixtures/cards` at its second. A base may be a
    name the file assigns once (`REPO_ROOT = Path(__file__).resolve().parents[2]`), `Path("x")`
    from the repository root, or `.joinpath(...)`. A join it cannot follow builds nothing here, and
    its strings are read as words.
    """
    assigned: dict[str, list[ast.expr]] = {}
    for node in ast.walk(syntax):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            assigned.setdefault(node.targets[0].id, []).append(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
            assigned.setdefault(node.target.id, []).append(node.value)
    bindings = {name: values[0] for name, values in assigned.items() if len(values) == 1}

    def joined(base: str | None, piece: str) -> str | None:
        if base is None or piece.startswith("/"):
            return None
        normal = posixpath.normpath(posixpath.join(base, piece))
        return None if normal == ".." or normal.startswith("../") else normal

    def evaluate(node: ast.expr, depth: int = 0) -> str | None:
        if depth > 20:
            return None
        if isinstance(node, ast.Name):
            return evaluate(bindings[node.id], depth + 1) if node.id in bindings else None
        if isinstance(node, ast.Attribute) and node.attr == "parent":
            inner = evaluate(node.value, depth + 1)
            return None if inner in (None, ".") else posixpath.dirname(inner) or "."
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "parents"
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, int)
        ):
            inner = evaluate(node.value.value, depth + 1)
            if inner is None:
                return None
            parents = [str(parent) for parent in PurePosixPath(inner).parents]
            return parents[node.slice.value] if 0 <= node.slice.value < len(parents) else None
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            right = node.right
            if isinstance(right, ast.Constant) and isinstance(right.value, str):
                return joined(evaluate(node.left, depth + 1), right.value)
            return None
        if isinstance(node, ast.Call):
            function = node.func
            name = function.attr if isinstance(function, ast.Attribute) else getattr(function, "id", "")
            if name == "Path" and len(node.args) == 1 and not node.keywords:
                argument = node.args[0]
                if isinstance(argument, ast.Name) and argument.id == "__file__":
                    return reader
                if isinstance(argument, ast.Name) and isinstance(bindings.get(argument.id), ast.Constant):
                    argument = bindings[argument.id]
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    return joined(".", argument.value)
                return None
            if isinstance(function, ast.Attribute) and name in ("resolve", "absolute") and not node.args:
                return evaluate(function.value, depth + 1)
            if isinstance(function, ast.Attribute) and name == "joinpath" and node.args:
                path = evaluate(function.value, depth + 1)
                for argument in node.args:
                    if not (isinstance(argument, ast.Constant) and isinstance(argument.value, str)):
                        return None
                    path = joined(path, argument.value)
                return path
        return None

    built: dict[int, str] = {}
    for node in ast.walk(syntax):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            right = node.right
            if isinstance(right, ast.Constant) and isinstance(right.value, str):
                path = evaluate(node)
                if path is not None:
                    built[id(right)] = path
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "joinpath"
            and node.args
        ):
            path = evaluate(node)
            last = node.args[-1]
            if path is not None and isinstance(last, ast.Constant):
                built[id(last)] = path
    return built


def naming_text(tree: Tree, path: str, index: PathIndex) -> tuple[str, str, set[str]]:
    """A file's words (`"a", "b"`), the words it builds paths from, and the existing paths it denotes.

    A string a `Path(__file__)` join builds into an existing path denotes that path; a string with
    a slash denotes what :meth:`PathIndex.denoted` says. Either way it is left out of the words, so
    `"verify"` in a route or `"landscape"` in another package's fixture folder names nothing. Any
    other string is a word, and names a file by its file name. It names a folder or a script by
    its bare name only from a path position (:func:`path_segments`): `"flow"` as a label, `"prod"`
    as an argument or `"synthetic"` as a dictionary key reads nothing. A file that is not Python,
    or does not parse, is all words and all segments.
    """
    syntax = tree.syntax(path) if path.endswith(".py") else None
    if syntax is None:
        return tree.literals(path), tree.literals(path), set()
    built = static_paths(syntax, path)
    segment_ids = path_segments(syntax)
    prose = {
        id(node.value)
        for node in ast.walk(syntax)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
    }
    words: list[ast.Constant] = []
    denoted: set[str] = set()
    for node in ast.walk(syntax):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)) or id(node) in prose:
            continue
        joined = built.get(id(node))
        if joined is not None and index.exists(joined):
            denoted.add(joined)
            continue
        from_slash = index.denoted(node.value, path)
        if from_slash is None:
            words.append(node)
        else:
            denoted |= from_slash
    words.sort(key=lambda node: (node.lineno, node.col_offset))
    segments = [node for node in words if id(node) in segment_ids]
    return (
        ", ".join(f'"{node.value}"' for node in words),
        ", ".join(f'"{node.value}"' for node in segments),
        denoted,
    )


PATH_CALLS = frozenset({"Path", "PurePath", "PurePosixPath", "joinpath", "join"})


def path_segments(syntax: ast.Module) -> set[int]:
    """The string nodes a file builds a path from, whatever the base: what a folder's name may be read in.

    An operand of `/`, an argument of `Path(...)`, `.joinpath(...)` or `os.path.join(...)`, and an
    item of a tuple or list a `for` walks (`for name in ("cards", "verify"): FIXTURES / name`).
    """
    found: set[int] = set()
    for node in ast.walk(syntax):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            found |= {id(node.left), id(node.right)}
        elif isinstance(node, ast.Call):
            function = node.func
            name = function.attr if isinstance(function, ast.Attribute) else getattr(function, "id", "")
            if name in PATH_CALLS:
                found |= {id(argument) for argument in node.args}
        elif isinstance(node, ast.For | ast.AsyncFor | ast.comprehension) and isinstance(
            node.iter, ast.Tuple | ast.List | ast.Set
        ):
            found |= {id(item) for item in node.iter.elts}
    return found


def naming_corpus(tree: Tree, changes: list[Change]) -> Corpus:
    index = PathIndex(tree.paths | {change.path for change in changes})
    texts: dict[str, str] = {}
    segments: dict[str, str] = {}
    denoting: dict[str, set[str]] = {}
    for path in tree.texts:
        texts[path], segments[path], denoted = naming_text(tree, path, index)
        for target in denoted:
            denoting.setdefault(target, set()).add(path)
    return Corpus(texts, denoting, segments)


@dataclass(frozen=True)
class Keys:
    """How a file is named by the files that read or run it.

    `folders` are the folders a reader may name to read it, the same walk as `path_parts` but as
    whole paths, for a path literal that denotes one of them.
    """

    file_names: frozenset[str]
    path_parts: frozenset[str]
    neighbours: frozenset[str]
    folders: frozenset[str] = frozenset()


def keys_for(path: str, layout: Layout, deleted: bool) -> Keys:
    pure = PurePosixPath(path)
    file_names: set[str] = set()
    path_parts: set[str] = set()
    neighbours: set[str] = set()
    module = layout.path_modules.get(path) or deleted_module_name(path, layout)
    if pure.name not in GENERIC_FILE_NAMES:
        if pure.suffix:
            file_names.add(pure.name)
        else:
            path_parts.add(pure.name)
    if module:
        file_names.add(module)
        return Keys(frozenset(file_names), frozenset(path_parts), frozenset())
    if pure.suffix == ".py" and pure.name not in LOADED_BY_FOLDER:
        path_parts.add(pure.stem)
        return Keys(frozenset(file_names), frozenset(path_parts), frozenset())
    folder = pure.parent
    folders: set[str] = set()
    while str(folder) != "." and not ends_folder_walk(folder, layout):
        if not VAGUE_FOLDER.fullmatch(folder.name):
            path_parts.add(folder.name)
        folders.add(str(folder))
        neighbours |= layout.python_files_in.get(str(folder), set())
        folder = folder.parent
    return Keys(
        frozenset(file_names), frozenset(path_parts), frozenset(neighbours - {path}), frozenset(folders)
    )


def ends_folder_walk(folder: PurePosixPath, layout: Layout) -> bool:
    """A folder a data file's readers are not found by: generic, a Python package, or a test folder.

    Within it, a file is read by name or through a folder below it; naming the folder itself names
    every test and helper beside it, not the data.
    """
    return (
        folder.name in GENERIC_FOLDERS
        or str(folder / "__init__.py") in layout.tree.paths
        or str(folder) in layout.test_folders
    )


def deleted_module_name(path: str, layout: Layout) -> str | None:
    for name, src in layout.packages.items():
        if path.startswith(f"{src}/{name}/") and path.endswith(".py"):
            return path[len(src) + 1 : -len(".py")].replace("/", ".").removesuffix(".__init__")
    return None


# --------------------------------------------------------------------------------------------
# Selection
# --------------------------------------------------------------------------------------------


@dataclass
class Selection:
    tests: dict[str, str] = field(default_factory=dict)  # test file -> why
    whole: str | None = None
    notes: list[str] = field(default_factory=list)
    total: int = 0

    def add(self, tests: dict[str, str]) -> None:
        for test, reason in sorted(tests.items()):
            self.tests.setdefault(test, reason)


def shared_test_ground(path: str) -> bool:
    return (
        path in SHARED_TEST_GROUND_FILES
        or PurePosixPath(path).name == "pyproject.toml"
        or path.startswith(SHARED_TEST_GROUND_DIRECTORIES)
    )


def tests_reading_tables(change: Change) -> tuple[str, ...] | None:
    """The test folders a root pyproject.toml change reaches, when it only touched tables they alone read.

    None for any other change, and for one that touched another table, only comments, or that
    cannot be read: those are the whole selection.
    """
    if change.path != ROOT_PYPROJECT or not change.tables:
        return None
    if not change.tables <= TABLES_READ_ONLY_BY.keys():
        return None
    return tuple(folder for table in sorted(change.tables) for folder in TABLES_READ_ONLY_BY[table])


def files_under(layout: Layout, prefixes: Iterable[str]) -> set[str]:
    prefixes = tuple(prefixes)
    return {
        test
        for test in layout.test_files
        if any(test == p or (p.endswith("/") and test.startswith(p)) for p in prefixes)
    }


def select(
    tree: Tree, changes: list[Change], every_mention_runs: bool = False, whole_container: bool = False
) -> Selection:
    layout = Layout.of(tree)
    selection = Selection(total=len(layout.test_files))
    read_by: dict[str, tuple[str, ...]] = {}
    for change in changes:
        folders = tests_reading_tables(change)
        if folders is not None:
            read_by[change.path] = folders
        elif shared_test_ground(change.path):
            if change.path == ROOT_PYPROJECT and change.tables:
                selection.notes.append(f"{change.path} changes {', '.join(sorted(change.tables))}.")
            selection.whole = f"{change.path} is shared test ground"
            return selection
    graph = build_graph(tree, layout, every_mention_runs, whole_container)
    selection.notes.extend(graph.notes)
    walk = Walk(layout, graph, naming_corpus(tree, changes))
    for change in changes:
        if change.path in read_by:
            tables = ", ".join(sorted(change.tables or ()))
            selection.add(
                dict.fromkeys(
                    files_under(layout, read_by[change.path]),
                    f"reads [{tables}] of {change.path}, the only table that changed",
                )
            )
            continue
        walk.start(change)
        selection.add(files_by_category(change.path, layout, selection.notes))
    selection.whole = walk.run()
    selection.notes.extend(walk.notes)
    if selection.whole is not None:
        return selection
    selection.add(walk.fallback_tests)
    if any(change.path.endswith(".py") for change in changes):
        selection.add(
            {
                test: f"{READS_SOURCE} the files it walks, and Python changed"
                for test in source_readers(tree, layout)
            }
        )
    for test in sorted(layout.test_files & set(walk.why)):
        selection.tests[test] = walk.explain(test)
    selection.add(dict.fromkeys(files_under(layout, ALWAYS_RUN), "is always run"))
    return selection


def files_by_category(path: str, layout: Layout, notes: list[str]) -> dict[str, str]:
    """The tests that read a kind of file wholesale rather than by name, and what pytest does not check."""
    tests: dict[str, str] = {}
    if path.endswith(".md") or path.startswith("docs/"):
        tests.update(
            dict.fromkeys(files_under(layout, DOCS_CHECK_TESTS), f"the documentation checks read {path}")
        )
    if path.startswith("plan_specs/"):
        tests.update(dict.fromkeys(files_under(layout, SPEC_TESTS), f"the spec tests read {path}"))
    for prefix, note in CHECKED_OUTSIDE_PYTEST.items():
        if path.startswith(prefix) and note not in notes:
            notes.append(note)
    return tests


def source_readers(tree: Tree, layout: Layout) -> set[str]:
    """Tests that walk a directory and parse the Python in it: they read source as data."""
    return {
        test
        for test in layout.test_files
        if SOURCE_READER.search(tree.texts.get(test, "")) and DIRECTORY_WALK.search(tree.texts.get(test, ""))
    }


class Walk:
    """From the changed files, back along every edge of the graph and every mention, to the tests."""

    def __init__(self, layout: Layout, graph: Graph, corpus: Corpus) -> None:
        self.layout = layout
        self.graph = graph
        self.corpus = corpus
        self.why: dict[str, tuple[str, str | None]] = {}  # file -> (how it was reached, from which file)
        self.queue: deque[str] = deque()
        self.to_search: dict[str, Keys] = {}
        self.searched: set[str] = set()
        self.data_files: set[str] = set()
        self.fallback_tests: dict[str, str] = {}
        self.notes: list[str] = []
        self.runs: dict[str, frozenset[Run]] = {}
        self.runners: dict[str, list[tuple[str, str]]] = {}
        # A changed container.py walked from the parts it changed, until something reaches it whole.
        self.read_by_part: set[str] = set()
        self.conftests = sorted(
            path for path in layout.tree.paths if PurePosixPath(path).name == "conftest.py"
        )

    def reach(self, path: str, how: str, via: str | None) -> None:
        if path not in self.why:
            self.why[path] = (how, via)
            self.queue.append(path)
        elif path in self.read_by_part:
            # Module code uses a part that changed, or an import it runs did: the whole file after all.
            self.read_by_part.discard(path)
            self.queue.append(path)
            self.to_search[path] = keys_for(path, self.layout, deleted=False)
        elif self.reached_by_fixtures(path) and how not in FIXTURE_EDGES:
            # First reached through an import its fixtures carry, now by a name or a change: every
            # test beneath it is reached after all.
            self.why[path] = (how, via)
            self.queue.append(path)

    def reached_by_fixtures(self, path: str) -> bool:
        """A conftest read fixture by fixture, reached only through a file it imports or runs."""
        return path in self.graph.narrowed_conftests and self.why[path][0] in FIXTURE_EDGES

    def start(self, change: Change) -> None:
        path = change.path
        self.why[path] = ("was deleted" if change.deleted else "changed", None)
        parts = self.changed_parts(change)
        if parts is not None:
            reading = change.container or ContainerDiff()
            self.read_by_part.add(path)
            for part in sorted(parts):
                used = reading.uses.get(part)
                how = f"uses {listed(sorted(used))}, which an import rebinds" if used else "changed"
                self.why[part_of(path, part)] = (how, None)
                self.queue.append(part_of(path, part))
            for dependent, how in self.graph.dependents.get(path, ()):
                if how != IMPORTS:
                    self.reach(dependent, how, path)  # an importer asks for the parts it names
                elif reading.names:
                    # One that imports a rebound name from the container, or reads it off the module.
                    used = self.names_used(dependent, reading.names)
                    if used:
                        self.reach(dependent, f"uses {listed(used)}, which an import rebinds, from", path)
            for named, names in sorted(self.graph.container_named.items()):
                if names & reading.names:
                    self.reach(
                        named,
                        f"names {listed(sorted(names & reading.names))}, which an import rebinds, in",
                        path,
                    )
        elif not change.deleted:
            self.queue.append(path)
        lost_from = deleted_module_name(path, self.layout) if change.deleted else None
        if lost_from is not None:
            parent = lost_from.rpartition(".")[0]
            if parent in self.layout.module_paths:
                self.reach(self.layout.module_paths[parent], "contained", path)
        self.to_search[path] = keys_for(path, self.layout, change.deleted)
        if is_data_file(path):
            self.data_files.add(path)

    def changed_parts(self, change: Change) -> frozenset[str] | None:
        """The parts a change to container.py is walked from; None to walk the whole file (v1-e01-t43)."""
        reading = change.container
        if change.path != CONTAINER or reading is None:
            return None
        if reading.whole is not None:
            self.notes.append(f"{CONTAINER} is read as one file: {reading.whole}.")
            return None
        missing = sorted(reading.parts - self.graph.container_parts)
        if not self.graph.container_parts or missing:
            unread = f"has no {', '.join(missing)}" if self.graph.container_parts else "is not read by part"
            self.notes.append(f"{CONTAINER} is read as one file: this tree's container {unread}.")
            return None
        changed = ", ".join(sorted(reading.parts)) or "none: only comments or layout"
        self.notes.append(f"{CONTAINER} is read by part. Parts changed: {changed}.")
        if reading.names:
            self.notes.append(
                f"Its imports load the same modules and rebind {', '.join(sorted(reading.names))}, "
                "so the parts and files that use those names are walked from."
            )
        return reading.parts

    def names_used(self, path: str, names: frozenset[str]) -> list[str]:
        """The names a file mentions as a word, of those given; all of them when it cannot be read."""
        text = self.layout.tree.texts.get(path)
        if text is None:
            return sorted(names)
        return sorted(names & set(re.findall(r"[A-Za-z_]\w*", text)))

    def run(self) -> str | None:
        """Walk until nothing new is reached; the reason if the whole selection is affected."""
        while self.queue or self.to_search:
            while self.queue:
                path = self.queue.popleft()
                if path == ROOT_CONFTEST:
                    how = self.why[path][0]
                    if how != IMPORTS or self.graph.root_conftest_unread:
                        return f"the root conftest.py {self.explain(path)}"
                    self.notes.append(
                        f"The root conftest.py {self.explain(path)}: the tests that use its fixtures are "
                        "selected for that, and an import failure there would fail every test."
                    )
                    continue
                if path in self.graph.app_commands:
                    self.reach_runners(path)
                    continue
                through_fixtures = self.reached_by_fixtures(path)
                for dependent, how in self.graph.dependents.get(path, ()):
                    if not (through_fixtures and how == CONFTEST):
                        self.reach(dependent, how, path)
                if (
                    path not in self.searched
                    and path not in self.to_search
                    and runs_by_path(path, self.layout)
                ):
                    self.to_search[path] = keys_for(path, self.layout, deleted=False)
            whole = self.search()
            if whole is not None:
                return whole
        return None

    def search(self) -> str | None:
        batch, self.to_search = self.to_search, {}
        self.searched |= set(batch)
        names = {name for keys in batch.values() for name in keys.file_names}
        parts = {part for keys in batch.values() for part in keys.path_parts}
        mentions = self.corpus.find(names, parts)
        for path, keys in batch.items():
            denoters = self.corpus.denoters(path, keys)
            mentioners = set(keys.neighbours) | denoters
            for key in (*keys.file_names, *keys.path_parts):
                mentioners |= mentions.get(key, set())
            mentioners.discard(path)
            mentioners = {mentioner for mentioner in mentioners if self.can_read(mentioner, path)}
            if path in self.read_by_part:
                # Their reading is in the graph already, as edges to every part (v1-e01-t39), and
                # a `debate_cli.container.X` string's as an edge to part X, or by the names an
                # import rebinds (v1-e41-t06).
                mentioners -= self.graph.container_readers
                mentioners -= self.graph.container_named.keys()
            for mentioner in sorted(mentioners):
                self.reach(mentioner, HAS_A_PATH_TO if mentioner in denoters else NAMES, path)
            if path in self.data_files and not mentioners:
                tests, reason = fallback_for(path, self.layout)
                if tests is None:
                    return reason
                self.fallback_tests.update(dict.fromkeys(tests, reason))
        return None

    def reach_runners(self, node: str) -> None:
        """From the app for one command module, to each file that runs the app and names a command of it.

        A file runs the app through an import, a fixture, a console script or `-m`. It is reached
        when its runs of literal words (:func:`argument_runs`), with those of the conftests above it
        and the helpers between it and the app, name one of the module's commands
        (:func:`names_command`), or ask for the root's `--help`. A helper that names none is followed to the
        files that import or name it, carrying its runs. A test whose runs hold no command's first
        word cannot be told apart, and is reached, as is a conftest, which its fixtures then narrow
        as they always do.
        """
        commands = self.graph.app_commands[node]
        top = self.graph.command_children.get((), set())
        pending = [(runner, how, self.runs_in(runner)) for runner, how in self.graph.dependents.get(APP, ())]
        seen: set[tuple[str, frozenset[Run]]] = set()
        while pending:
            runner, how, runs = pending.pop()
            is_test = runner in self.layout.test_files
            if is_test:
                runs = runs.union(*(self.runs_in(conftest) for conftest in self.conftests_above(runner)))
            if (runner, runs) in seen:
                continue
            seen.add((runner, runs))
            named = passes_help(runs, top) or any(names_command(runs, command) for command in commands)
            if runner in self.graph.narrowed_conftests:
                # By its import, so that its fixtures go on narrowing it: their edges carry its tests.
                self.reach(runner, IMPORTS, node)
                continue
            if named or PurePosixPath(runner).name == "conftest.py":
                self.reach(runner, how, node)
                continue
            further = [] if is_test else self.runners_of(runner)
            if not further:
                if not names_any_command(runs, top):
                    # Nothing it passes names a command: it cannot be told apart.
                    self.reach(runner, how, node)
                continue
            for next_runner, next_how in further:
                chain = f"{next_how} {self.show(runner)}, which {how}"
                pending.append((next_runner, chain, runs | self.runs_in(next_runner)))

    def runs_in(self, path: str) -> frozenset[Run]:
        if path not in self.runs:
            starters = frozenset(
                self.graph.command_children.get((), set()) | self.layout.console_scripts.keys()
            )
            self.runs[path] = argument_runs(self.layout.tree, path, starters)
        return self.runs[path]

    def conftests_above(self, test: str) -> list[str]:
        return [
            conftest
            for conftest in self.conftests
            if conftest == ROOT_CONFTEST or test.startswith(str(PurePosixPath(conftest).parent) + "/")
        ]

    def runners_of(self, helper: str) -> list[tuple[str, str]]:
        """The files that import a helper that runs the app, and those that run it by its name."""
        if helper not in self.runners:
            found = list(self.graph.dependents.get(helper, ()))
            if runs_by_path(helper, self.layout):
                keys = keys_for(helper, self.layout, deleted=False)
                mentions = self.corpus.find(keys.file_names, keys.path_parts)
                denoters = self.corpus.denoters(helper, keys)
                mentioners = set(keys.neighbours) | denoters
                for key in (*keys.file_names, *keys.path_parts):
                    mentioners |= mentions.get(key, set())
                mentioners.discard(helper)
                found += [
                    (mentioner, HAS_A_PATH_TO if mentioner in denoters else NAMES)
                    for mentioner in sorted(mentioners)
                    if self.can_read(mentioner, helper)
                ]
            self.runners[helper] = found
        return self.runners[helper]

    def show(self, path: str) -> str:
        return self.graph.labels.get(path) or self.layout.show(path)

    def can_read(self, reader: str, path: str) -> bool:
        """A package module reads only its own package's files: one installed from a wheel has no others.

        Naming a runbook or a spec in an error message is not reading it.
        """
        module = self.layout.path_modules.get(reader)
        if module is None:
            return True
        top = module.split(".")[0]
        return path.startswith(f"{self.layout.packages[top]}/{top}/")

    def explain(self, path: str) -> str:
        """`imports a, which imports b, which changed`: the way the walk first reached a file."""
        steps: list[str] = []
        current: str | None = path
        seen: set[str] = set()
        while current is not None and current not in seen:
            seen.add(current)
            how, via = self.why[current]
            steps.append(how if via is None else f"{how} {self.show(via)}")
            current = via
        return ", which ".join(steps)


def is_data_file(path: str) -> bool:
    """A file read by its name, which a test may still read when nothing names it."""
    if path.endswith((".py", ".md")) or path.startswith(("docs/", "plan_specs/", ".github/")):
        return False
    return not path.startswith(tuple(CHECKED_OUTSIDE_PYTEST))


def runs_by_path(path: str, layout: Layout) -> bool:
    """A file outside the packages that a test may start by its path: a script or a test helper."""
    if layout.is_package_file(path) or path in layout.test_files:
        return False
    return is_searched(path)


def fallback_for(path: str, layout: Layout) -> tuple[set[str] | None, str]:
    """What a data file nothing names selects: its package's tests, or the whole selection."""
    parts = PurePosixPath(path).parts
    if len(parts) > 2 and parts[0] == "packages":
        tests = files_under(layout, (f"packages/{parts[1]}/tests/",))
        return tests, f"nothing names {path}, so every test of packages/{parts[1]} is selected"
    return None, f"nothing names {path} and no package owns it"


# --------------------------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------------------------


def repository_root() -> Path:
    return Path(git(Path.cwd(), "rev-parse", "--show-toplevel").decode().strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument(
        "--base", default=DEFAULT_BASE, help="compare against the merge base with this (origin/dev)"
    )
    parser.add_argument(
        "--head", help="describe this commit against its merge base with --base, read from git"
    )
    parser.add_argument(
        "--diff", metavar="REV", help="describe what commit REV changed against its first parent"
    )
    parser.add_argument(
        "--graph", metavar="REV", help="build the import graph from REV's files rather than the changes' own"
    )
    parser.add_argument(
        "--whole-container",
        action="store_true",
        help=f"read a change to {CONTAINER} as the whole file, as before v1-e01-t43",
    )
    parser.add_argument(
        "--every-mention-runs",
        action="store_true",
        help="read any mention of a console script in a string as running it, as before v1-e01-t44",
    )
    parser.add_argument("--explain", action="store_true", help="print why each test file was selected")
    parser.add_argument("--run", action="store_true", help="run pytest over the selection with CI's markers")
    arguments = parser.parse_args(argv)
    if arguments.run and (arguments.head or arguments.diff):
        parser.error("--run runs the working tree's tests, so it cannot be combined with --head or --diff")
    if arguments.head and arguments.diff:
        parser.error("--head and --diff are two ways to name a commit; give one")
    if arguments.run and arguments.graph:
        parser.error("--run runs the working tree's tests, so it cannot be combined with --graph")

    root = repository_root()
    started = time.monotonic()
    changes = changed_files(root, arguments.base, arguments.head, arguments.diff)
    if arguments.whole_container:
        changes = [replace(change, container=None) for change in changes]
    revision = arguments.graph or arguments.diff or arguments.head
    tree = Tree.at(root, revision) if revision else Tree.working(root)
    if arguments.graph:
        absent = [change.path for change in changes if not change.deleted and change.path not in tree.paths]
        if absent:
            print(
                f"{len(absent)} changed files are not in {arguments.graph}'s tree, so only a file naming "
                f"them reaches them: {', '.join(absent)}",
                file=sys.stderr,
            )
    selection = select(tree, changes, arguments.every_mention_runs, arguments.whole_container)
    elapsed = time.monotonic() - started

    for note in selection.notes:
        print(note, file=sys.stderr)
    if selection.whole is not None:
        print(
            f"The whole selection is affected: {selection.whole}. CI runs it on the pull request; "
            "a session does not (working agreement 10)."
        )
        print(f"Chose in {elapsed:.1f} s; {len(changes)} changed files.", file=sys.stderr)
        return 0
    for test, reason in sorted(selection.tests.items()):
        print(f"{test}  <- {reason}" if arguments.explain else test)
    share = 100 * len(selection.tests) / selection.total if selection.total else 0.0
    print(
        f"{len(selection.tests)} of {selection.total} test files ({share:.1f}%) chosen in {elapsed:.1f} s "
        f"from {len(changes)} changed files.",
        file=sys.stderr,
    )
    if not arguments.run:
        return 0
    if not selection.tests:
        print("Nothing to run.", file=sys.stderr)
        return 0
    command = [sys.executable, "-m", "pytest", "-n", "auto", "-m", CI_MARKERS, *sorted(selection.tests)]
    sys.stdout.flush()  # the selection above pytest's output, even when both go to a pipe
    run_started = time.monotonic()
    status = subprocess.run(command, cwd=root, check=False).returncode
    print(
        f"Affected set: {len(selection.tests)} test files, pytest exited {status} "
        f"after {time.monotonic() - run_started:.0f} s.",
        file=sys.stderr,
    )
    return 0 if status == 5 else status  # 5: every selected test was deselected by the markers


if __name__ == "__main__":
    sys.exit(main())
