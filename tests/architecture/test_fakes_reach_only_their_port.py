"""A fakes module reaches only its own port, and the ports package re-exports nothing (`v1-e01-t30`).

Importing a module imports everything it imports. `debate_core/testing/fakes.py` imported every
port, so a test that needed `FixedClock` reached caselist suppression and the parsed store, and a
change to either selected it (`scripts/affected_tests.py`). `application/ports/__init__.py`
re-exported every port, so importing one port module ran all of them, and `ports/providers.py`
re-exported four values it no longer defined. This test keeps all three from growing back:

* **A fakes module reaches only its own port.** `testing/fakes/<name>.py` fakes the port module
  `application/ports/<name>.py`. It may import that port module, and the port modules that one
  imports itself, since importing the port reaches those anyway. A fakes module named for no port
  is a shared helper and imports no port. `all_ports` is the one exception, named below. Imports of
  another fakes module count as reaching what that module reaches, so a port cannot be laundered
  through a neighbour.
* **The two package modules hold only a docstring:** `application/ports/__init__.py` and
  `testing/fakes/__init__.py` define nothing and import nothing.
* **A port module's `__all__` names only what it defines,** so no caller is invited to import a
  value from a port that merely uses it.

import-linter cannot say the first rule: it forbids named modules, and here the allowed set differs
per module and follows from the port's own imports. So this test reads the files with `ast`, as
`test_package_inits_import_nothing.py` does, and sees lazy imports inside functions and
`import_module` calls too.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CORE = REPO_ROOT / "packages/debate_core/src/debate_core"
PORTS = "debate_core.application.ports"
FAKES = "debate_core.testing.fakes"
PORTS_DIRECTORY = CORE / "application/ports"
FAKES_DIRECTORY = CORE / "testing/fakes"

# The one fakes module that assembles several ports: `FakePorts` annotates each of its ten fields
# with the Protocol, which is where pyright checks that the fakes still conform. A test needing
# one fake imports that fake's own module and never reaches this one.
ASSEMBLY_MODULES = {"all_ports": frozenset({"persistence", "providers", "model_router"})}
DYNAMIC_IMPORT_CALLS = {"__import__", "import_module"}


def imported_modules(source: str, importer: str) -> list[tuple[int, str]]:
    """Every module `source` imports, as `(line, dotted name)`; `from a import b` gives `a.b` too.

    `importer` is the importing module's dotted name, to resolve relative imports. A name after
    `from a import` may be a value rather than a module; listing `a.b` anyway is harmless, because
    only names that are modules of the ports or fakes packages are ever looked up.
    """
    package = importer.rpartition(".")[0]
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                anchor = package
                for _ in range(node.level - 1):
                    anchor = anchor.rpartition(".")[0]
                base = f"{anchor}.{base}" if base else anchor
            found.append((node.lineno, base))
            found.extend((node.lineno, f"{base}.{alias.name}") for alias in node.names)
        elif isinstance(node, ast.Call) and node.args:
            called = node.func
            name = called.attr if isinstance(called, ast.Attribute) else getattr(called, "id", None)
            argument = node.args[0]
            if (
                name in DYNAMIC_IMPORT_CALLS
                and isinstance(argument, ast.Constant)
                and isinstance(argument.value, str)
            ):
                found.append((node.lineno, argument.value))
    return found


def submodule_of(dotted: str, package: str) -> str | None:
    """`persistence` for `debate_core.application.ports.persistence.Page`; None outside the package."""
    if not dotted.startswith(package + "."):
        return None
    return dotted[len(package) + 1 :].split(".")[0]


def modules_in(directory: Path) -> list[str]:
    return sorted(path.stem for path in directory.glob("*.py") if path.name != "__init__.py")


def ports_imported_by(source: str, importer: str) -> dict[str, int]:
    """The port modules `source` imports directly, each with the first line that imports it."""
    found: dict[str, int] = {}
    port_modules = set(modules_in(PORTS_DIRECTORY))
    for line, dotted in imported_modules(source, importer):
        port = submodule_of(dotted, PORTS)
        if port in port_modules:
            found.setdefault(port, line)
    return found


def fakes_imported_by(source: str, importer: str) -> set[str]:
    fake_modules = set(modules_in(FAKES_DIRECTORY))
    return {
        fake
        for _, dotted in imported_modules(source, importer)
        if (fake := submodule_of(dotted, FAKES)) in fake_modules
    }


def allowed_ports(fake: str) -> frozenset[str]:
    """The port modules `testing/fakes/<fake>.py` may reach."""
    if fake in ASSEMBLY_MODULES:
        return ASSEMBLY_MODULES[fake]
    port_file = PORTS_DIRECTORY / f"{fake}.py"
    if not port_file.is_file():
        return frozenset()  # a shared helper
    return frozenset({fake, *ports_imported_by(port_file.read_text(encoding="utf-8"), f"{PORTS}.{fake}")})


def ports_reached(fake: str, sources: dict[str, str]) -> dict[str, str]:
    """Each port module `fake` reaches, with how: `line N` or `through <other fakes module>`."""
    reached: dict[str, str] = {}
    pending = [(fake, None)]
    seen: set[str] = set()
    while pending:
        current, via = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        importer = f"{FAKES}.{current}"
        for port, line in ports_imported_by(sources[current], importer).items():
            reached.setdefault(port, f"line {line}" if via is None else f"through {via}")
        for other in fakes_imported_by(sources[current], importer):
            pending.append((other, via or other))
    return reached


def fake_sources() -> dict[str, str]:
    return {
        name: (FAKES_DIRECTORY / f"{name}.py").read_text(encoding="utf-8")
        for name in modules_in(FAKES_DIRECTORY)
    }


def ports_out_of_place(fake: str, sources: dict[str, str]) -> list[str]:
    allowed = allowed_ports(fake)
    return [
        f"{port} ({how})" for port, how in sorted(ports_reached(fake, sources).items()) if port not in allowed
    ]


def anything_but_a_docstring(source: str) -> list[str]:
    """Each statement in `source` other than a leading docstring, as `line N: <statement>`."""
    body = ast.parse(source).body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return [f"line {statement.lineno}: {ast.unparse(statement).splitlines()[0]}" for statement in body]


def names_listed_but_not_defined(source: str) -> list[str]:
    """The names in a module's `__all__` that the module imports rather than defines."""
    tree = ast.parse(source)
    listed: list[str] = []
    imported: set[str] = set()
    for statement in tree.body:
        if isinstance(statement, ast.Import | ast.ImportFrom):
            imported.update((alias.asname or alias.name).split(".")[0] for alias in statement.names)
        targets = statement.targets if isinstance(statement, ast.Assign) else []
        if any(isinstance(target, ast.Name) and target.id == "__all__" for target in targets):
            assert isinstance(statement, ast.Assign)
            listed = [str(value) for value in ast.literal_eval(statement.value)]
    return sorted(name for name in listed if name in imported)


# --------------------------------------------------------------------------------------------
# The rules, over the real files
# --------------------------------------------------------------------------------------------


def test_there_are_fakes_modules_to_check() -> None:
    """A moved or renamed directory would otherwise pass every rule below by checking nothing."""
    assert "persistence" in modules_in(FAKES_DIRECTORY)
    assert "persistence" in modules_in(PORTS_DIRECTORY)
    assert set(ASSEMBLY_MODULES) <= set(modules_in(FAKES_DIRECTORY))


@pytest.mark.parametrize("fake", modules_in(FAKES_DIRECTORY))
def test_a_fakes_module_reaches_only_its_own_port(fake: str) -> None:
    out_of_place = ports_out_of_place(fake, fake_sources())
    assert not out_of_place, (
        f"debate_core/testing/fakes/{fake}.py reaches the port modules {out_of_place}, but may reach "
        f"only {sorted(allowed_ports(fake)) or 'none'}. A test importing this fake would reach those "
        "ports too. Put the fake for another port in that port's fakes module (v1-e01-t30)."
    )


@pytest.mark.parametrize(
    "init",
    [
        "packages/debate_core/src/debate_core/application/ports/__init__.py",
        "packages/debate_core/src/debate_core/testing/fakes/__init__.py",
    ],
)
def test_the_package_module_holds_only_a_docstring(init: str) -> None:
    found = anything_but_a_docstring((REPO_ROOT / init).read_text(encoding="utf-8"))
    assert not found, (
        f"{init} holds {found}. Importing any module of the package runs this file first, so whatever "
        "it imports or re-exports, every caller of one module reaches. Import from the module that "
        "defines the name (v1-e01-t30)."
    )


@pytest.mark.parametrize("port", modules_in(PORTS_DIRECTORY))
def test_a_port_module_lists_only_what_it_defines(port: str) -> None:
    found = names_listed_but_not_defined((PORTS_DIRECTORY / f"{port}.py").read_text(encoding="utf-8"))
    assert not found, (
        f"debate_core/application/ports/{port}.py lists {found} in __all__ but imports them. Callers "
        "import those from the module that defines them (v1-e01-t30)."
    )


# --------------------------------------------------------------------------------------------
# The checks find what they are for
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "from debate_core.application.ports.suppression import AppendOnlyRecord\n",
        "import debate_core.application.ports.suppression\n",
        "from debate_core.application.ports import suppression\n",
        "def later():\n    from debate_core.application.ports.suppression import AppendOnlyRecord\n",
        "import importlib\n\nimportlib.import_module('debate_core.application.ports.suppression')\n",
    ],
)
def test_the_check_finds_a_foreign_port_imported_by_a_fakes_module(line: str) -> None:
    sources = fake_sources()
    added_at = sources["card_edit_log"].count("\n") + 1 + line.count("\n") - 1
    sources["card_edit_log"] += line
    assert ports_out_of_place("card_edit_log", sources) == [f"suppression (line {added_at})"]


def test_the_check_finds_a_foreign_port_reached_through_another_fakes_module() -> None:
    sources = fake_sources()
    sources["card_edit_log"] += "from debate_core.testing.fakes.parsed_store import InMemoryParsedStore\n"
    assert ports_out_of_place("card_edit_log", sources) == ["parsed_store (through parsed_store)"]
    sources = fake_sources()
    sources["card_edit_log"] += "from .parsed_store import InMemoryParsedStore\n"
    assert ports_out_of_place("card_edit_log", sources) == ["parsed_store (through parsed_store)"]


def test_the_check_allows_the_ports_a_fakes_modules_own_port_imports() -> None:
    """`ports/caselist.py` imports `ports/persistence.py`, so the caselist fake may page with it."""
    assert allowed_ports("caselist") == {"caselist", "persistence"}
    assert allowed_ports("clock_and_ids") == frozenset()


@pytest.mark.parametrize(
    "source",
    [
        '"""Docstring."""\nfrom debate_core.application.ports.persistence import Page\n',
        '"""Docstring."""\n__all__ = ["Page"]\n',
        '"""Docstring."""\n\n\ndef helper() -> None:\n    pass\n',
        "from __future__ import annotations\n",
    ],
)
def test_the_check_finds_anything_beside_the_docstring(source: str) -> None:
    assert anything_but_a_docstring(source)


def test_the_check_passes_a_docstring_alone() -> None:
    assert anything_but_a_docstring('"""Only this."""\n') == []


def test_the_check_finds_a_re_export_in_a_port_modules_all() -> None:
    source = (
        "from debate_core.domain.discovery import ProviderQuery\n\n"
        '__all__ = ["Clock", "ProviderQuery"]\n\n\n'
        "class Clock:\n    pass\n"
    )
    assert names_listed_but_not_defined(source) == ["ProviderQuery"]
