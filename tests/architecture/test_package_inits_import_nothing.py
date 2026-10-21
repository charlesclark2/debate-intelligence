"""`debate_core.testing` and `debate_core.evidence` import nothing in their `__init__` (`v1-e01-t29` ac1).

Importing any module of a package runs the package's `__init__` first, so whatever `__init__`
imports, every caller of every submodule imports too. `debate_core/testing/__init__.py` used to
re-export `fakes`, which reaches the caselist suppression code, and the root conftest imported it.
`debate_core/evidence/__init__.py` re-exported the style classifier. Between them they put a median
of 79% of the test files into a task's affected set (`scripts/affected_tests.py`, v1-e01-t28).
Callers now import from the submodule that defines a name, and these two modules hold only a
docstring.

import-linter says only part of this. A forbidden contract with `as_packages = false` can be
narrowed to the package module alone, but it forbids only the modules it names: a stdlib or
third-party import (`import pytest`) is outside its graph, and it does not see a dynamic import. So
this test reads both files with `ast` and fails on any import statement, anywhere in the module (a
lazy one inside a function as well), and on any call to `__import__` or `import_module`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
THIN_PACKAGE_INITS = (
    "packages/debate_core/src/debate_core/testing/__init__.py",
    "packages/debate_core/src/debate_core/evidence/__init__.py",
)
DYNAMIC_IMPORT_CALLS = {"__import__", "import_module"}


def imports_in(source: str) -> list[str]:
    """Each import in `source`, as `line N: <statement>`."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import | ast.ImportFrom):
            found.append(f"line {node.lineno}: {ast.unparse(node)}")
        elif isinstance(node, ast.Call):
            called = node.func
            name = called.attr if isinstance(called, ast.Attribute) else getattr(called, "id", None)
            if name in DYNAMIC_IMPORT_CALLS:
                found.append(f"line {node.lineno}: {ast.unparse(node)}")
    return sorted(found)


@pytest.mark.parametrize("init", THIN_PACKAGE_INITS)
def test_the_package_init_imports_nothing(init: str) -> None:
    found = imports_in((REPO_ROOT / init).read_text(encoding="utf-8"))
    assert not found, (
        f"{init} imports {found}. Every caller of every module in this package would import that "
        "too. Import the name from the submodule that defines it instead (v1-e01-t29)."
    )


@pytest.mark.parametrize(
    "source",
    [
        "from debate_core.testing.fakes import FixedClock\n",
        "from . import fakes\n",
        "import pytest\n",
        "from __future__ import annotations\n",
        "def __getattr__(name):\n    from . import fakes\n    return getattr(fakes, name)\n",
        "import importlib\n\nimportlib.import_module('debate_core.testing.fakes')\n",
        "__import__('debate_core.evidence.style_classifier')\n",
    ],
)
def test_the_check_finds_every_kind_of_import(source: str) -> None:
    assert imports_in(source)


def test_the_check_passes_a_docstring_and_a_plain_function() -> None:
    source = '"""A docstring."""\n\n\ndef __getattr__(name):\n    raise AttributeError(name)\n'
    assert imports_in(source) == []
