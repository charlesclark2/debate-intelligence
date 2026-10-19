"""Print the test files a branch's changes can affect, and optionally run them (v1-e01-t28).

Working agreement 10 has a session run the affected set once before its report, and CI run the
whole default selection on the pull request. This script prints that affected set. It reads the
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
* **Runs.** A file that mentions a console script (`debate-research`) or `-m <module>` runs that
  module, so it depends on it as if it imported it.
* **Names.** A file read or run by path is found by its name. A changed data file (a fixture under
  `tests/fixtures/`, package data such as `style_profiles/*.yaml` or `templates/base.docx`, a
  workflow, Terraform) selects the files that name it: its file name anywhere in their text, or
  the name of a folder it is in (up to the first Python package or a generic folder such as
  `tests/` or `fixtures/`) as a quoted or slash-separated path part, plus the Python files beside
  it. A file named that way counts as changed, so a helper module that opens the fixture carries
  the selection on to the tests importing it. A data file nothing names selects every test of the
  package it is in, or the whole selection when it is in none. A changed script or test helper
  outside the packages is also found by its file name, which is how a test that starts it with
  subprocess (`write_junk_beside_a_held_link_files.py`, `scripts/*.py`) is selected.
* **Source readers.** A test that walks a directory and parses the Python it finds there
  (`ast.parse` with a glob, `rglob`, `iterdir` or `walk`) reads source as data, so any changed
  Python file selects it.
* **Categories.** Any Markdown file, and anything under `docs/`, selects the documentation checks
  (`tests/docs/`, the command-block and docs-index tests), because they read every tracked
  Markdown file. `plan_specs/` selects `tests/specs/`. `infrastructure/` is checked by
  `scripts/terraform_checks.sh`, and `site/` and `web/` by their own pnpm checks; the script says
  so, and selects only the tests that name what changed.
* **Always run:** `tests/architecture/`, `tests/specs/` and the CLI's composition-root and
  command-registration tests (`test_app.py`, `test_help_rendering.py`), which wiring reaches as
  much as imports do.

A change to **shared test ground** (any `pyproject.toml`, `uv.lock`, the root `conftest.py`,
`tests/pytest_plugins/`, `.github/workflows/ci.yml`) affects the whole selection. The script prints
one line saying so, and that CI runs it, and exits 0; `--run` then runs nothing, because a session
never runs the whole selection (working agreement 10).

It is conservative on purpose: a missed test is the failure that matters, and an extra one costs
seconds. When it cannot tell, it selects more and says why (`--explain`). It keeps no state between
runs: the graph is built from the files each time, in a few seconds.

`--diff REV` describes what one commit changed (REV against its first parent), and `--head REV`
a branch tip against its merge base with `--base`, both read from git without checking anything
out: the import graph is built from that commit's files, copied into a temporary directory.

Usage:
  uv run scripts/affected_tests.py                     # this branch against origin/dev, as printed paths
  uv run scripts/affected_tests.py --explain           # with the reason each file was selected
  uv run scripts/affected_tests.py --run               # and run pytest over them with CI's markers
  uv run scripts/affected_tests.py --diff REV          # what commit REV changed
  uv run scripts/affected_tests.py --base A --head B   # B against its merge base with A
"""

from __future__ import annotations

import argparse
import ast
import bisect
import contextlib
import importlib
import re
import subprocess
import sys
import tempfile
import time
import tomllib
from collections import deque
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

DEFAULT_BASE = "origin/dev"
CI_MARKERS = "not slow and not live"

# Shared test ground: a change to any of these can reach every test.
SHARED_TEST_GROUND_FILES = frozenset({"conftest.py", "uv.lock", ".github/workflows/ci.yml"})
SHARED_TEST_GROUND_DIRECTORIES = ("tests/pytest_plugins/",)

# What imports cannot see: tests that read the whole repository, and the CLI's wiring.
ALWAYS_RUN = (
    "tests/architecture/",
    "tests/specs/",
    "packages/debate_cli/tests/test_app.py",
    "packages/debate_cli/tests/test_help_rendering.py",
)
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
GENERIC_FOLDERS = frozenset({"tests", "fixtures", "src", "packages", "scripts", "docs"})
# File names too common to search for; such a file is found through its path or module name.
GENERIC_FILE_NAMES = frozenset({"__init__.py", "__main__.py", "conftest.py", "py.typed", "README.md"})
# Python loads these by their name from a directory on its path; a test reaches them by the folder.
LOADED_BY_FOLDER = frozenset({"sitecustomize.py", "usercustomize.py"})
# A folder named like this (`v1`, `ab`) matches literals that have nothing to do with it.
VAGUE_FOLDER = re.compile(r"v\d+|.{1,2}")
LARGEST_SEARCHED_FILE = 2_000_000

SOURCE_READER = re.compile(r"\bast\.parse\(")
DIRECTORY_WALK = re.compile(r"\b(?:rglob|glob|iterdir|walk)\(")
MODULE_FLAG = re.compile(r"""(?:["']-m["']\s*,\s*["']|-m\s+)([A-Za-z_][\w.]*)""")


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
        if not path.endswith(".py"):
            return self.texts.get(path, "")
        syntax = self.syntax(path)
        if syntax is None:
            return self.texts.get(path, "")
        prose = {
            id(node.value)
            for node in ast.walk(syntax)
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
        }
        strings = [
            node
            for node in ast.walk(syntax)
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in prose
        ]
        strings.sort(key=lambda node: (node.lineno, node.col_offset))
        return ", ".join(f'"{node.value}"' for node in strings)

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


def changed_files(root: Path, base: str, head: str | None, diff: str | None) -> list[Change]:
    if diff is not None:
        parents = git(root, "rev-list", "--parents", "-n", "1", diff).decode().split()
        if len(parents) < 2:
            raise SystemExit(f"affected_tests: {diff} has no parent to compare with")
        listing = git(root, "diff", "--name-status", "--no-renames", "-z", parents[1], parents[0])
        return parse_name_status(listing)
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
    return sorted(changes.values(), key=lambda change: change.path)


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
READS_SOURCE = "reads the Python source of"
ROOT_CONFTEST = "conftest.py"


@dataclass
class Graph:
    layout: Layout
    dependents: dict[str, list[tuple[str, str]]] = field(default_factory=dict)  # target -> (who, how)
    notes: list[str] = field(default_factory=list)
    root_conftest_unread: bool = False

    def add(self, dependent: str, how: str, target: str) -> None:
        if dependent != target:
            self.dependents.setdefault(target, []).append((dependent, how))


def build_graph(tree: Tree, layout: Layout) -> Graph:
    graph = Graph(layout)
    resolver = Resolver(layout)
    package_edges = grimp_edges(tree, layout, graph) or {}
    for path, module in layout.path_modules.items():
        parent = module.rpartition(".")[0]
        if parent in layout.module_paths:
            graph.add(path, IMPORTS, layout.module_paths[parent])
        for imported in package_edges.get(module, ()):
            if imported in layout.module_paths:
                graph.add(path, IMPORTS, layout.module_paths[imported])
    for path in tree.texts:
        if not path.endswith(".py") or layout.path_modules.get(path) in package_edges:
            continue
        for target in resolver.imports_of(path):
            graph.add(path, IMPORTS, target)
    for path in tree.texts:
        if layout.is_package_file(path):
            continue  # package code names the CLI in its messages; it does not start it
        for target in resolver.runs_of(tree.literals(path)):
            graph.add(path, RUNS, target)
    conftests = sorted(path for path in tree.paths if PurePosixPath(path).name == "conftest.py")
    for test in layout.test_files:
        for conftest in conftests:
            folder = str(PurePosixPath(conftest).parent)
            if folder != "." and test.startswith(folder + "/"):
                graph.add(test, CONFTEST, conftest)
    if ROOT_CONFTEST in tree.texts:
        add_root_conftest_fixtures(tree, layout, resolver, graph, conftests)
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
    syntax = tree.syntax(ROOT_CONFTEST)
    if syntax is None:
        graph.root_conftest_unread = True
        return
    imported: dict[str, set[str]] = {}
    for node in ast.walk(syntax):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                imported.setdefault(local, set()).update(resolver.resolve(ROOT_CONFTEST, 0, alias.name, ()))
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                files = resolver.resolve(ROOT_CONFTEST, node.level, node.module or "", (alias.name,))
                imported.setdefault(alias.asname or alias.name, set()).update(files)
    definitions: dict[str, set[str]] = {}  # a module-level name -> the names its definition uses
    everywhere: set[str] = set()  # names module-level code and autouse fixtures use
    fixtures: dict[str, set[str]] = {}  # fixture name -> the names its function uses
    for statement in syntax.body:
        if isinstance(statement, ast.Import | ast.ImportFrom):
            continue
        used = {node.id for node in ast.walk(statement) if isinstance(node, ast.Name)}
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            definitions[statement.name] = used
            fixture = fixture_of(statement)
            if fixture is not None:
                name, autouse = fixture
                if autouse:
                    everywhere |= used
                else:
                    fixtures[name] = used
        elif isinstance(statement, ast.Assign | ast.AnnAssign):
            targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
            for target in targets:
                for node in ast.walk(target):
                    if isinstance(node, ast.Name):
                        definitions[node.id] = used
            everywhere |= used
        else:
            everywhere |= used

    def needs(names: set[str]) -> set[str]:
        seen: set[str] = set()
        pending = list(names)
        while pending:
            name = pending.pop()
            if name not in seen:
                seen.add(name)
                pending.extend(definitions.get(name, ()))
        return {file for name in seen for file in imported.get(name, ())}

    for file in sorted(needs(everywhere)):
        for test in layout.test_files:
            graph.add(
                test, "is beneath the root conftest.py, whose module code or autouse fixtures need", file
            )
    for name, used in sorted(fixtures.items()):
        files = needs(used)
        if not files:
            continue
        word = re.compile(rf"\b{re.escape(name)}\b")
        users = {test for test in layout.test_files if word.search(tree.texts.get(test, ""))}
        for conftest in conftests:
            if conftest != ROOT_CONFTEST and word.search(tree.texts.get(conftest, "")):
                folder = str(PurePosixPath(conftest).parent) + "/"
                users |= {test for test in layout.test_files if test.startswith(folder)}
        for file in sorted(files):
            for test in sorted(users):
                graph.add(test, f"uses the root conftest.py's {name} fixture, which needs", file)


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

    def __init__(self, layout: Layout) -> None:
        self.layout = layout
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

    def runs_of(self, text: str) -> set[str]:
        """The modules a file runs as a program: a console script it names, or `-m module`."""
        found: set[str] = set()
        for script, module in self.layout.console_scripts.items():
            if re.search(rf"(?<![\w-]){re.escape(script)}(?![\w-])", text):
                found |= self.in_packages(module, ())
        for module in MODULE_FLAG.findall(text):
            top = module.split(".")[0]
            if top in self.layout.packages:
                found |= self.in_packages(module, ("__main__",))
        return found


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


class Corpus:
    """Every searched file's text in one string, so a set of names is found in one pass."""

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

    def find(self, file_names: Iterable[str], path_parts: Iterable[str]) -> dict[str, set[str]]:
        """For each name, the files holding it: a file name anywhere, a path part between quotes or /."""
        names = sorted(set(file_names), key=len, reverse=True)
        parts = sorted(set(path_parts), key=len, reverse=True)
        alternatives: list[str] = []
        if names:
            alternatives.append(r"(?<![\w-])(?P<name>" + "|".join(map(re.escape, names)) + r")(?![\w-])")
        if parts:
            alternatives.append(
                r"(?<=[\"'/\\`])(?P<part>" + "|".join(map(re.escape, parts)) + r")(?=[\"'/\\`])"
            )
        found: dict[str, set[str]] = {}
        if not alternatives:
            return found
        for match in re.finditer("|".join(alternatives), self.text):
            key = match.group("name") if names and match.group("name") else match.group("part")
            path = self.paths[bisect.bisect_right(self.starts, match.start()) - 1]
            found.setdefault(key, set()).add(path)
        return found


@dataclass(frozen=True)
class Keys:
    """How a file is named by the files that read or run it."""

    file_names: frozenset[str]
    path_parts: frozenset[str]
    neighbours: frozenset[str]


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
    while str(folder) != "." and not ends_folder_walk(folder, layout):
        if not VAGUE_FOLDER.fullmatch(folder.name):
            path_parts.add(folder.name)
        neighbours |= layout.python_files_in.get(str(folder), set())
        folder = folder.parent
    return Keys(frozenset(file_names), frozenset(path_parts), frozenset(neighbours - {path}))


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


def files_under(layout: Layout, prefixes: Iterable[str]) -> set[str]:
    prefixes = tuple(prefixes)
    return {
        test
        for test in layout.test_files
        if any(test == p or (p.endswith("/") and test.startswith(p)) for p in prefixes)
    }


def select(tree: Tree, changes: list[Change]) -> Selection:
    layout = Layout.of(tree)
    selection = Selection(total=len(layout.test_files))
    for change in changes:
        if shared_test_ground(change.path):
            selection.whole = f"{change.path} is shared test ground"
            return selection
    graph = build_graph(tree, layout)
    selection.notes.extend(graph.notes)
    walk = Walk(layout, graph, Corpus({path: tree.literals(path) for path in tree.texts}))
    for change in changes:
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

    def reach(self, path: str, how: str, via: str | None) -> None:
        if path not in self.why:
            self.why[path] = (how, via)
            self.queue.append(path)

    def start(self, change: Change) -> None:
        path = change.path
        self.why[path] = ("was deleted" if change.deleted else "changed", None)
        if not change.deleted:
            self.queue.append(path)
        lost_from = deleted_module_name(path, self.layout) if change.deleted else None
        if lost_from is not None:
            parent = lost_from.rpartition(".")[0]
            if parent in self.layout.module_paths:
                self.reach(self.layout.module_paths[parent], "contained", path)
        self.to_search[path] = keys_for(path, self.layout, change.deleted)
        if is_data_file(path):
            self.data_files.add(path)

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
                for dependent, how in self.graph.dependents.get(path, ()):
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
            mentioners = set(keys.neighbours)
            for key in (*keys.file_names, *keys.path_parts):
                mentioners |= mentions.get(key, set())
            mentioners.discard(path)
            mentioners = {mentioner for mentioner in mentioners if self.can_read(mentioner, path)}
            for mentioner in sorted(mentioners):
                self.reach(mentioner, NAMES, path)
            if path in self.data_files and not mentioners:
                tests, reason = fallback_for(path, self.layout)
                if tests is None:
                    return reason
                self.fallback_tests.update(dict.fromkeys(tests, reason))
        return None

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
            steps.append(how if via is None else f"{how} {self.layout.show(via)}")
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
    parser.add_argument("--explain", action="store_true", help="print why each test file was selected")
    parser.add_argument("--run", action="store_true", help="run pytest over the selection with CI's markers")
    arguments = parser.parse_args(argv)
    if arguments.run and (arguments.head or arguments.diff):
        parser.error("--run runs the working tree's tests, so it cannot be combined with --head or --diff")
    if arguments.head and arguments.diff:
        parser.error("--head and --diff are two ways to name a commit; give one")

    root = repository_root()
    started = time.monotonic()
    changes = changed_files(root, arguments.base, arguments.head, arguments.diff)
    revision = arguments.diff or arguments.head
    tree = Tree.at(root, revision) if revision else Tree.working(root)
    selection = select(tree, changes)
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
