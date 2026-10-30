"""`scripts/check_thin_handlers.py`: CLI commands and API routes stay thin.

Each test writes a small debate_cli / debate_api source tree under tmp_path, so a fixture can hold
a deliberately thick handler without touching the real packages. Statement counts and expected
messages are written by hand from the fixture source. The last section runs the check over the
real repository, to show it finds the handlers `register_commands` actually registers.
"""

from __future__ import annotations

import ast
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_thin_handlers as thin  # noqa: E402

CLI = "packages/debate_cli/src/debate_cli"
API = "packages/debate_api/src/debate_api"
MOVE_IT = "move the logic into a debate_core.application service and call it"
USE_THE_ROOT = "get the adapter from the composition root (debate_cli.container) instead"


@pytest.fixture(autouse=True)
def no_known_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    """The repository's own exception lists name modules the fixture trees do not have."""
    monkeypatch.setattr(thin, "KNOWN_THICK_HANDLERS", {})
    monkeypatch.setattr(thin, "KNOWN_INTEGRATIONS_IMPORTS", set())


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Empty delivery packages; each test adds the modules it needs."""
    root = tmp_path / "repo"
    for package in (CLI, API):
        (root / package).mkdir(parents=True)
        (root / package / "__init__.py").write_text("")
    return root


def write(root: Path, relative: str, source: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(source).lstrip())


def assignments(count: int, indent: str = "    ") -> str:
    """`count` one-statement lines, for a function body of an exact size."""
    return "\n".join(f"{indent}value_{n} = {n}" for n in range(count))


def function(name: str, statements: int, *, decorator: str = "", is_async: bool = False) -> str:
    """A top-level function of exactly `statements` statements, optionally decorated."""
    header = f"{'async ' if is_async else ''}def {name}(ctx):"
    return "\n".join(
        [decorator, header, assignments(statements)] if decorator else [header, assignments(statements)]
    )


def problems(root: Path, **kwargs: object) -> list[str]:
    return thin.check(root, **kwargs)  # type: ignore[arg-type]


def registry(*commands: str) -> str:
    """A commands/__init__.py registering `module.function` pairs the way debate_cli does."""
    modules = sorted({command.split(".")[0] for command in commands})
    lines = [f"from debate_cli.commands import {', '.join(modules)}", "", "def register_commands(app):"]
    lines += [f'    app.command("{c.split(".")[1]}")({c})' for c in commands]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------------------------
# counting statements
# --------------------------------------------------------------------------------------------


def test_every_statement_counts_at_any_depth_except_the_docstring() -> None:
    source = textwrap.dedent(
        '''
        def handler(items):
            """Not counted."""
            total = 0                      # 1
            for item in items:             # 2
                if item:                   # 3
                    total += item          # 4
                else:
                    continue               # 5

            def helper():                  # 6
                return total               # 7

            with open("x") as f:           # 8
                f.write(str(helper()))     # 9
            return total                   # 10
        '''
    )
    function = ast.parse(source).body[0]
    assert isinstance(function, ast.FunctionDef)

    assert thin.statement_count(function) == 10


def test_a_body_that_is_only_a_string_expression_after_code_counts_it() -> None:
    function = ast.parse("def f():\n    x = 1\n    'not a docstring'\n").body[0]
    assert isinstance(function, ast.FunctionDef)

    assert thin.statement_count(function) == 2


# --------------------------------------------------------------------------------------------
# the statement budget
# --------------------------------------------------------------------------------------------


def test_thin_handlers_pass(repo: Path) -> None:
    write(repo, f"{CLI}/commands/__init__.py", registry("doctor.doctor"))
    write(repo, f"{CLI}/commands/doctor.py", f"def doctor(ctx):\n    '''Help.'''\n{assignments(25)}\n")

    assert problems(repo) == []


def test_a_registered_command_over_the_budget_fails(repo: Path) -> None:
    write(repo, f"{CLI}/commands/__init__.py", registry("doctor.doctor", "store.sync"))
    write(repo, f"{CLI}/commands/doctor.py", f"def doctor(ctx):\n{assignments(3)}\n")
    write(
        repo,
        f"{CLI}/commands/store.py",
        f"import typer\n\n\ndef sync(ctx):\n    '''Help.'''\n{assignments(26)}\n",
    )

    assert problems(repo) == [
        f"{CLI}/commands/store.py:4: debate_cli.commands.store.sync holds 26 statements, "
        f"more than the budget of 25; {MOVE_IT}"
    ]


def test_the_budget_is_configurable(repo: Path) -> None:
    write(repo, f"{CLI}/commands/__init__.py", registry("doctor.doctor"))
    write(repo, f"{CLI}/commands/doctor.py", f"def doctor(ctx):\n{assignments(6)}\n")

    assert problems(repo, budget=6) == []
    assert problems(repo, budget=5) == [
        f"{CLI}/commands/doctor.py:1: debate_cli.commands.doctor.doctor holds 6 statements, "
        f"more than the budget of 5; {MOVE_IT}"
    ]


def test_a_command_registered_by_decorator_or_as_a_callback_is_a_handler(repo: Path) -> None:
    write(
        repo,
        f"{CLI}/app.py",
        "\n".join(
            [
                "import typer",
                "app = typer.Typer()",
                function("root", 4, decorator="@app.callback()"),
                function("hello", 5, decorator='@app.command("hello")', is_async=True),
            ]
        ),
    )

    assert problems(repo, budget=3) == [
        f"{CLI}/app.py:4: debate_cli.app.root holds 4 statements, more than the budget of 3; {MOVE_IT}",
        f"{CLI}/app.py:10: debate_cli.app.hello holds 5 statements, more than the budget of 3; {MOVE_IT}",
    ]


def test_a_function_registered_in_its_own_module_is_a_handler(repo: Path) -> None:
    write(
        repo,
        f"{CLI}/commands/local.py",
        "\n".join(['def register(group):\n    group.command("run")(run)', function("run", 4)]),
    )

    assert problems(repo, budget=3) == [
        f"{CLI}/commands/local.py:3: debate_cli.commands.local.run holds 4 statements, "
        f"more than the budget of 3; {MOVE_IT}"
    ]


def test_helpers_that_are_not_handlers_are_not_budgeted(repo: Path) -> None:
    write(repo, f"{CLI}/commands/__init__.py", registry("doctor.doctor"))
    write(
        repo,
        f"{CLI}/commands/doctor.py",
        f"def doctor(ctx):\n    return _report()\n\ndef _report():\n{assignments(40)}\n",
    )

    assert problems(repo) == []


@pytest.mark.parametrize("method", ["get", "post", "put", "patch", "delete", "api_route", "websocket"])
def test_an_api_route_over_the_budget_fails(repo: Path, method: str) -> None:
    write(
        repo,
        f"{API}/routes/cards.py",
        "\n".join(
            [
                "from fastapi import APIRouter",
                "router = APIRouter()",
                function("list_cards", 4, decorator=f'@router.{method}("/cards")', is_async=True),
            ]
        ),
    )

    assert problems(repo, budget=3) == [
        f"{API}/routes/cards.py:4: debate_api.routes.cards.list_cards holds 4 statements, "
        f"more than the budget of 3; {MOVE_IT}"
    ]


def test_an_endpoint_passed_to_add_api_route_is_a_route(repo: Path) -> None:
    write(
        repo,
        f"{API}/routes/cards.py",
        "\n".join(
            [
                function("list_cards", 4),
                function("get_card", 4),
                "def register(router):",
                '    router.add_api_route("/cards", list_cards)',
                '    router.add_api_route("/cards/{id}", endpoint=get_card)',
            ]
        ),
    )

    assert problems(repo, budget=3) == [
        f"{API}/routes/cards.py:1: debate_api.routes.cards.list_cards holds 4 statements, "
        f"more than the budget of 3; {MOVE_IT}",
        f"{API}/routes/cards.py:6: debate_api.routes.cards.get_card holds 4 statements, "
        f"more than the budget of 3; {MOVE_IT}",
    ]


def test_a_cli_function_named_like_an_http_method_is_not_a_route(repo: Path) -> None:
    write(repo, f"{CLI}/tools.py", f"@cache.get('k')\ndef fetch():\n{assignments(4)}\n")

    assert problems(repo, budget=3) == []


# --------------------------------------------------------------------------------------------
# direct imports of debate_core.integrations
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("statement", "imported"),
    [
        (
            "from debate_core.integrations.local.fs_object_store import FsStore",
            "debate_core.integrations.local.fs_object_store",
        ),
        ("import debate_core.integrations.s3", "debate_core.integrations.s3"),
        ("import debate_core.integrations.s3 as s3", "debate_core.integrations.s3"),
        ("from debate_core.integrations import opencaselist", "debate_core.integrations.opencaselist"),
        ("from debate_core import integrations", "debate_core.integrations"),
    ],
)
def test_a_handler_module_importing_an_adapter_fails(repo: Path, statement: str, imported: str) -> None:
    write(repo, f"{CLI}/commands/__init__.py", registry("store.sync"))
    write(repo, f"{CLI}/commands/store.py", f"{statement}\n\ndef sync(ctx):\n    return 1\n")

    assert problems(repo) == [
        f"{CLI}/commands/store.py:1: debate_cli.commands.store defines a handler and imports "
        f"{imported} directly; {USE_THE_ROOT}"
    ]


def test_an_adapter_imported_inside_the_handler_body_fails(repo: Path) -> None:
    write(repo, f"{CLI}/commands/__init__.py", registry("store.sync"))
    write(
        repo,
        f"{CLI}/commands/store.py",
        """
        def sync(ctx):
            from debate_core.integrations.s3 import build_s3_client
            return build_s3_client()
        """,
    )

    assert problems(repo) == [
        f"{CLI}/commands/store.py:2: debate_cli.commands.store defines a handler and imports "
        f"debate_core.integrations.s3 directly; {USE_THE_ROOT}"
    ]


def test_an_api_route_module_importing_an_adapter_fails(repo: Path) -> None:
    write(
        repo,
        f"{API}/routes/cards.py",
        """
        from debate_core.integrations.local import sqlite_db

        @router.get("/cards")
        def list_cards():
            return []
        """,
    )

    assert problems(repo) == [
        f"{API}/routes/cards.py:1: debate_api.routes.cards defines a handler and imports "
        f"debate_core.integrations.local directly; {USE_THE_ROOT}"
    ]


def test_the_composition_root_and_application_imports_are_allowed(repo: Path) -> None:
    write(repo, f"{CLI}/commands/__init__.py", registry("store.sync"))
    write(
        repo,
        f"{CLI}/commands/store.py",
        """
        from debate_core.application.evidence_sync import SyncReport
        from debate_cli.container import ServiceContainer

        def sync(ctx):
            return SyncReport
        """,
    )
    write(repo, f"{CLI}/container.py", "from debate_core.integrations.s3 import S3Store\n")

    assert problems(repo) == []


# --------------------------------------------------------------------------------------------
# known exceptions: they may shrink, never grow, and a stale one is reported
# --------------------------------------------------------------------------------------------


def thick_pull(repo: Path, statements: int) -> None:
    write(repo, f"{CLI}/commands/__init__.py", registry("caselist_pull.pull"))
    write(repo, f"{CLI}/commands/caselist_pull.py", f"def pull(ctx):\n{assignments(statements)}\n")


PULL = "debate_cli.commands.caselist_pull.pull"


def test_a_known_thick_handler_at_its_recorded_size_passes(repo: Path) -> None:
    thick_pull(repo, 33)

    assert problems(repo, known_thick={PULL: 33}) == []


def test_a_known_thick_handler_that_grows_fails(repo: Path) -> None:
    thick_pull(repo, 34)

    assert problems(repo, known_thick={PULL: 33}) == [
        f"{CLI}/commands/caselist_pull.py:1: {PULL} holds 34 statements, more than its recorded 33; {MOVE_IT}"
    ]


def test_a_known_thick_handler_that_shrinks_must_have_its_entry_lowered(repo: Path) -> None:
    thick_pull(repo, 30)

    assert problems(repo, known_thick={PULL: 33}) == [
        f"KNOWN_THICK_HANDLERS: {PULL} is down to 30 statements from 33; lower its entry to match"
    ]


def test_a_known_thick_handler_back_within_budget_must_lose_its_entry(repo: Path) -> None:
    thick_pull(repo, 25)

    assert problems(repo, known_thick={PULL: 33}) == [
        f"KNOWN_THICK_HANDLERS: {PULL} holds 25 statements, within the budget of 25; remove its entry"
    ]


def test_a_known_thick_handler_that_no_longer_exists_must_lose_its_entry(repo: Path) -> None:
    assert problems(repo, known_thick={PULL: 33}) == [
        f"KNOWN_THICK_HANDLERS: {PULL} is not a handler any more; remove its entry"
    ]


def test_a_known_adapter_import_passes_until_it_is_removed(repo: Path) -> None:
    known = {("debate_cli.commands.caselist", "debate_core.integrations.local.archive_reader")}
    write(repo, f"{CLI}/commands/__init__.py", registry("caselist.status"))
    write(
        repo,
        f"{CLI}/commands/caselist.py",
        "from debate_core.integrations.local.archive_reader import read_archive\n\n"
        "def status(ctx):\n    return 1\n",
    )
    assert problems(repo, known_imports=known) == []

    write(repo, f"{CLI}/commands/caselist.py", "def status(ctx):\n    return 1\n")
    assert problems(repo, known_imports=known) == [
        "KNOWN_INTEGRATIONS_IMPORTS: no handler module has the import debate_cli.commands.caselist -> "
        "debate_core.integrations.local.archive_reader any more; remove its entry"
    ]


def test_a_known_adapter_import_does_not_excuse_another_one(repo: Path) -> None:
    known = {("debate_cli.commands.caselist", "debate_core.integrations.local.archive_reader")}
    write(repo, f"{CLI}/commands/__init__.py", registry("caselist.status"))
    write(
        repo,
        f"{CLI}/commands/caselist.py",
        "from debate_core.integrations.local.archive_reader import read_archive\n"
        "from debate_core.integrations.local.sqlite_db import connect\n\n"
        "def status(ctx):\n    return 1\n",
    )

    assert problems(repo, known_imports=known) == [
        f"{CLI}/commands/caselist.py:2: debate_cli.commands.caselist defines a handler and imports "
        f"debate_core.integrations.local.sqlite_db directly; {USE_THE_ROOT}"
    ]


# --------------------------------------------------------------------------------------------
# the command line
# --------------------------------------------------------------------------------------------


def test_main_exits_non_zero_and_prints_each_problem(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(repo, f"{CLI}/commands/__init__.py", registry("doctor.doctor"))
    write(repo, f"{CLI}/commands/doctor.py", f"def doctor(ctx):\n{assignments(4)}\n")

    assert thin.main(["--root", str(repo), "--budget", "3"]) == 1
    out, err = capsys.readouterr()
    assert "debate_cli.commands.doctor.doctor holds 4 statements, more than the budget of 3" in out
    assert "1 thin-handler problem(s)" in err


def test_main_exits_zero_on_thin_handlers(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(repo, f"{CLI}/commands/__init__.py", registry("doctor.doctor"))
    write(repo, f"{CLI}/commands/doctor.py", "def doctor(ctx):\n    return 1\n")

    assert thin.main(["--root", str(repo)]) == 0
    assert capsys.readouterr().out == "OK: 1 CLI command and API route handlers within 25 statements\n"


# --------------------------------------------------------------------------------------------
# the real repository
# --------------------------------------------------------------------------------------------


def test_the_real_registry_is_read() -> None:
    """A sample of what register_commands registers, so a change in its shape is noticed."""
    found = {handler.name for handler in thin.handlers(thin.delivery_modules(REPO_ROOT))}

    assert {
        "debate_cli.app.root_callback",
        "debate_cli.commands.doctor.doctor",
        "debate_cli.commands.config.show",
        "debate_cli.commands.caselist.import_archive",
        "debate_cli.commands.caselist_auth.logout",
        "debate_cli.commands.caselist_pull.pull",
        "debate_cli.commands.store.sync",
    } <= found
    assert "debate_cli.commands.caselist_pull.pull_summary" not in found
