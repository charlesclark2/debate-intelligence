"""A command module imports no other command module (`v1-e01-t32`).

Importing a module imports everything it imports. `debate_cli/commands/__init__.py` used to import
every command module to register it, so a test of `verify` ran `caselist`, `landscape` and the rest,
and a change to any of them selected it (`scripts/affected_tests.py`). Registration now lives in
`debate_cli/command_registry.py`, which only the composition root imports, and the package module
holds only a docstring (`test_fakes_reach_only_their_port.py` checks that). Eight command modules
also imported `store`, `caselist` or `landscape` for a shared option or helper; those now live in
`debate_cli/options/` and `debate_cli/caselist_events.py`. This test keeps both from growing back:
a module in `debate_cli/commands/` imports no other module of the package, by any spelling.

It reads the files with `ast`, as `test_fakes_reach_only_their_port.py` does, so it sees relative
imports, lazy imports inside functions and `import_module` calls too.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS = "debate_cli.commands"
COMMANDS_DIRECTORY = REPO_ROOT / "packages/debate_cli/src/debate_cli/commands"
DYNAMIC_IMPORT_CALLS = {"__import__", "import_module"}


def command_modules() -> list[str]:
    return sorted(path.stem for path in COMMANDS_DIRECTORY.glob("*.py") if path.name != "__init__.py")


def commands_imported_by(source: str, command: str) -> dict[str, int]:
    """The other command modules `source` (the module `command`) imports, each with its first line.

    `from debate_cli.commands import store` and `from . import store` name the module after
    `import`; `from debate_cli.commands.store import X` and `from .store import X` name it in the
    module part. A name after `from debate_cli.commands import` that is not a command module still
    reaches the package module, so it is reported as the package itself.
    """
    modules = set(command_modules())
    found: dict[str, int] = {}

    def note(dotted: str, line: int) -> None:
        if dotted == COMMANDS:
            found.setdefault("the commands package itself", line)
        elif dotted.startswith(COMMANDS + "."):
            name = dotted[len(COMMANDS) + 1 :].split(".")[0]
            if name != command:
                found.setdefault(name if name in modules else "the commands package itself", line)

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                note(alias.name, node.lineno)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                anchor = COMMANDS
                for _ in range(node.level - 1):
                    anchor = anchor.rpartition(".")[0]
                base = f"{anchor}.{base}" if base else anchor
            if base == COMMANDS:
                for alias in node.names:
                    note(f"{COMMANDS}.{alias.name}", node.lineno)
            else:
                note(base, node.lineno)
        elif isinstance(node, ast.Call) and node.args:
            called = node.func
            name = called.attr if isinstance(called, ast.Attribute) else getattr(called, "id", None)
            argument = node.args[0]
            if (
                name in DYNAMIC_IMPORT_CALLS
                and isinstance(argument, ast.Constant)
                and isinstance(argument.value, str)
            ):
                note(argument.value, node.lineno)
    return found


def source_of(command: str) -> str:
    return (COMMANDS_DIRECTORY / f"{command}.py").read_text(encoding="utf-8")


# --------------------------------------------------------------------------------------------
# The rule, over the real files
# --------------------------------------------------------------------------------------------


def test_there_are_command_modules_to_check() -> None:
    """A moved or renamed directory would otherwise pass the rule below by checking nothing."""
    assert {"verify", "store", "caselist", "landscape"} <= set(command_modules())


@pytest.mark.parametrize("command", command_modules())
def test_a_command_module_imports_no_other_command_module(command: str) -> None:
    found = commands_imported_by(source_of(command), command)
    assert not found, (
        f"debate_cli/commands/{command}.py imports {found} (module: first line). A test of this "
        "command would run those commands' modules too, and a change to one of them would select it. "
        "Put what two commands share in debate_cli/options/ or another module outside the commands "
        "package (v1-e01-t32)."
    )


# --------------------------------------------------------------------------------------------
# The check finds what it is for
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "from debate_cli.commands.store import CONFIRM_PROD_FLAG\n",
        "from debate_cli.commands import store\n",
        "import debate_cli.commands.store\n",
        "from .store import CONFIRM_PROD_FLAG\n",
        "from . import store\n",
        "def later():\n    from debate_cli.commands.store import CONFIRM_PROD_FLAG\n",
        "import importlib\n\nimportlib.import_module('debate_cli.commands.store')\n",
    ],
)
def test_the_check_finds_another_command_module_imported_by_a_command_module(line: str) -> None:
    source = source_of("verify")
    added_at = source.count("\n") + 1 + line.count("\n") - 1
    assert commands_imported_by(source + line, "verify") == {"store": added_at}


@pytest.mark.parametrize(
    "line",
    [
        "from debate_cli.commands import register_commands\n",
        "import debate_cli.commands\n",
        "from . import command_group\n",
    ],
)
def test_the_check_finds_a_name_imported_from_the_commands_package_itself(line: str) -> None:
    source = source_of("verify")
    assert commands_imported_by(source + line, "verify") == {
        "the commands package itself": source.count("\n") + 1
    }


def test_the_check_passes_imports_from_outside_the_commands_package() -> None:
    source = (
        "from debate_cli.options.bucket_environment import CONFIRM_PROD_FLAG\n"
        "from debate_cli.context import cli_context\n"
        "import debate_cli.command_registry\n"
        "from debate_core.application.settings import Settings\n"
    )
    assert commands_imported_by(source, "verify") == {}
