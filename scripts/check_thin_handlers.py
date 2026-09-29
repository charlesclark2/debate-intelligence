# /// script
# requires-python = ">=3.12"
# ///
"""Check that CLI commands and API routes stay thin: they call use cases, they do not hold them.

The architecture puts business logic in `debate_core` and keeps `debate_cli` and `debate_api` to
parsing input, calling an application service and rendering what comes back (§1). import-linter
(`uv run lint-imports`) enforces who may import what; it cannot see how much a handler does. This
script reads the handlers' source with `ast`, imports nothing, and reports two things:

  * a handler whose body holds more than the statement budget (default 25). Every statement at any
    depth counts, including those inside a nested function, a loop or an `if`; the docstring does
    not. The thickest handler that is not an exception below holds 20.
  * a module defining a handler that imports `debate_core.integrations` itself, anywhere in the
    module. Adapters are built by the front end's composition root (`debate_cli.container`); a
    handler that constructs one has taken over a decision that is not its to make.

What counts as a handler:
  * a CLI command: a function registered with `<group>.command(...)(function)` or
    `<group>.callback(...)(function)` (the way `debate_cli.commands.register_commands` does it),
    or decorated with `@<group>.command(...)` / `@<group>.callback(...)`, anywhere in debate_cli
  * an API route: a function decorated with `@<router>.get(...)`, `.post`, `.put`, `.patch`,
    `.delete`, `.head`, `.options`, `.api_route` or `.websocket`, or passed as the endpoint of
    `<router>.add_api_route(...)`, anywhere in debate_api

Handlers that were already over the line when this check was written are listed in
KNOWN_THICK_HANDLERS and KNOWN_INTEGRATIONS_IMPORTS, each by name, the thick ones with the count
they had. They may shrink but not grow, and an entry that no longer matches anything is itself
reported, so the lists only get shorter.

Usage:
  uv run scripts/check_thin_handlers.py              # check the repository
  uv run scripts/check_thin_handlers.py --budget 20  # try a different statement budget
  uv run scripts/check_thin_handlers.py --list       # list the handlers found and their sizes
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Iterator, Mapping, Set
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUDGET = 25
INTEGRATIONS = "debate_core.integrations"
DELIVERY_PACKAGES = ("debate_cli", "debate_api")
CLI_REGISTRATIONS = {"command", "callback"}
API_ROUTE_DECORATORS = {"get", "post", "put", "patch", "delete", "head", "options", "api_route", "websocket"}

# Handler -> the statement count it had when the check was written. It may go down, never up.
KNOWN_THICK_HANDLERS: Mapping[str, int] = {
    # Sequences --dry-run, --publish-pending and the run monitor itself; that choice of run mode
    # belongs in CaselistSyncService.
    "debate_cli.commands.caselist_pull.pull": 33,
}
# (handler module, imported adapter module) pairs, matching the ignore_imports entries of the
# "Delivery packages reach debate_core.integrations only through their composition root" contract
# in pyproject.toml. The fix for each is to have debate_cli.container build the adapter.
KNOWN_INTEGRATIONS_IMPORTS: Set[tuple[str, str]] = {
    ("debate_cli.commands.caselist", "debate_core.integrations.local.archive_reader"),
    ("debate_cli.commands.caselist", "debate_core.integrations.local.fs_object_store"),
    ("debate_cli.commands.caselist_auth", "debate_core.integrations.opencaselist"),
    ("debate_cli.commands.caselist_auth", "debate_core.integrations.opencaselist.auth"),
}


@dataclass(frozen=True)
class Module:
    name: str
    path: Path
    tree: ast.Module


@dataclass(frozen=True)
class Handler:
    module: Module
    function: ast.FunctionDef | ast.AsyncFunctionDef

    @property
    def name(self) -> str:
        return f"{self.module.name}.{self.function.name}"

    @property
    def statements(self) -> int:
        return statement_count(self.function)


@dataclass(frozen=True)
class AdapterImport:
    module: Module
    imported: str
    line: int


def statement_count(function: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Every statement in the function's body at any depth, not counting its docstring."""
    body = function.body
    if ast.get_docstring(function, clean=False) is not None:
        body = body[1:]
    return sum(1 for statement in body for node in ast.walk(statement) if isinstance(node, ast.stmt))


def module_name(path: Path, source_root: Path) -> str:
    parts = list(path.relative_to(source_root).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def delivery_modules(root: Path) -> list[Module]:
    """Every module of the delivery packages, parsed, in path order."""
    modules: list[Module] = []
    for package in DELIVERY_PACKAGES:
        source_root = root / "packages" / package / "src"
        for path in sorted((source_root / package).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            modules.append(Module(module_name(path, source_root), path, tree))
    return modules


def imported_names(module: Module) -> dict[str, str]:
    """Local name -> the module it is bound to, for `import a.b as c` and `from a import b`."""
    names: dict[str, str] = {}
    for node in ast.walk(module.tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    names[alias.asname] = alias.name
                else:
                    top = alias.name.split(".")[0]
                    names[top] = top
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for alias in node.names:
                names[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return names


def dotted(node: ast.expr, names: Mapping[str, str]) -> str | None:
    """`caselist.pull` -> `debate_cli.commands.caselist.pull`, through the module's own imports."""
    if isinstance(node, ast.Name):
        return names.get(node.id)
    if isinstance(node, ast.Attribute):
        owner = dotted(node.value, names)
        return f"{owner}.{node.attr}" if owner else None
    return None


def method_call(node: ast.expr, methods: Set[str]) -> bool:
    """`<anything>.<method>(...)` for one of `methods`."""
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in methods


def top_level_functions(module: Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in module.tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }


def registered_references(module: Module) -> Iterator[ast.expr]:
    """The function expressions a module registers: `g.command(...)(f)`, `r.add_api_route(p, f)`."""
    for node in ast.walk(module.tree):
        if not isinstance(node, ast.Call):
            continue
        if method_call(node.func, CLI_REGISTRATIONS) and node.args:
            yield node.args[0]
        elif method_call(node, {"add_api_route"}):
            endpoint = [kw.value for kw in node.keywords if kw.arg == "endpoint"] or node.args[1:2]
            yield from endpoint


def handlers(modules: list[Module]) -> list[Handler]:
    """Every CLI command and API route function defined in `modules`, in module and line order."""
    by_name = {module.name: module for module in modules}
    found: dict[str, Handler] = {}

    for module in modules:
        registrations = CLI_REGISTRATIONS if module.name.startswith("debate_cli") else API_ROUTE_DECORATORS
        for function in top_level_functions(module).values():
            if any(method_call(decorator, registrations) for decorator in function.decorator_list):
                handler = Handler(module, function)
                found[handler.name] = handler

        names = imported_names(module)
        local = top_level_functions(module)
        for reference in registered_references(module):
            if isinstance(reference, ast.Name) and reference.id in local:
                handler = Handler(module, local[reference.id])
                found[handler.name] = handler
                continue
            target = dotted(reference, names)
            owner_name, _, function_name = (target or "").rpartition(".")
            owner = by_name.get(owner_name)
            if owner and function_name in (defined := top_level_functions(owner)):
                handler = Handler(owner, defined[function_name])
                found[handler.name] = handler

    return sorted(found.values(), key=lambda h: (h.module.name, h.function.lineno))


def adapter_imports(module: Module) -> list[AdapterImport]:
    """Every import of debate_core.integrations or below in the module, at any depth."""
    found: list[AdapterImport] = []
    for node in ast.walk(module.tree):
        if isinstance(node, ast.Import):
            imported = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            # `from debate_core.integrations.local import x` names the adapter in the module part;
            # `from debate_core.integrations import local` and `from debate_core import
            # integrations` name it in the imported name.
            imported = [node.module]
            if not node.module.startswith(f"{INTEGRATIONS}."):
                imported = [f"{node.module}.{alias.name}" for alias in node.names]
        else:
            continue
        found += [
            AdapterImport(module, name, node.lineno)
            for name in imported
            if name == INTEGRATIONS or name.startswith(f"{INTEGRATIONS}.")
        ]
    return sorted(found, key=lambda i: i.line)


def check(
    root: Path,
    budget: int = DEFAULT_BUDGET,
    known_thick: Mapping[str, int] | None = None,
    known_imports: Set[tuple[str, str]] | None = None,
) -> list[str]:
    """Every thick handler, direct adapter import and stale exception under root, one message each.

    The known exceptions default to this repository's lists, read when called rather than when
    defined, so a test can substitute its own.
    """
    known_thick = KNOWN_THICK_HANDLERS if known_thick is None else known_thick
    known_imports = KNOWN_INTEGRATIONS_IMPORTS if known_imports is None else known_imports
    found = handlers(delivery_modules(root))
    problems: list[str] = []

    def where(module: Module, line: int) -> str:
        return f"{module.path.relative_to(root).as_posix()}:{line}"

    for handler in found:
        limit = max(budget, known_thick.get(handler.name, 0))
        if handler.statements > limit:
            allowance = f"the budget of {budget}" if limit == budget else f"its recorded {limit}"
            problems.append(
                f"{where(handler.module, handler.function.lineno)}: {handler.name} holds "
                f"{handler.statements} statements, more than {allowance}; move the logic into a "
                "debate_core.application service and call it"
            )

    handler_modules = {handler.module.name: handler.module for handler in found}
    seen_imports: set[tuple[str, str]] = set()
    for module in handler_modules.values():
        for adapter in adapter_imports(module):
            key = (module.name, adapter.imported)
            seen_imports.add(key)
            if key in known_imports:
                continue
            problems.append(
                f"{where(module, adapter.line)}: {module.name} defines a handler and imports "
                f"{adapter.imported} directly; get the adapter from the composition root "
                "(debate_cli.container) instead"
            )

    sizes = {handler.name: handler.statements for handler in found}
    for name, recorded in sorted(known_thick.items()):
        if name not in sizes:
            problems.append(f"KNOWN_THICK_HANDLERS: {name} is not a handler any more; remove its entry")
        elif sizes[name] <= budget:
            problems.append(
                f"KNOWN_THICK_HANDLERS: {name} holds {sizes[name]} statements, within the budget "
                f"of {budget}; remove its entry"
            )
        elif sizes[name] < recorded:
            problems.append(
                f"KNOWN_THICK_HANDLERS: {name} is down to {sizes[name]} statements from {recorded}; "
                "lower its entry to match"
            )
    for module_imported in sorted(known_imports - seen_imports):
        problems.append(
            "KNOWN_INTEGRATIONS_IMPORTS: no handler module has the import "
            f"{module_imported[0]} -> {module_imported[1]} any more; remove its entry"
        )

    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=ROOT, help="repository root to check")
    ap.add_argument("--budget", type=int, default=DEFAULT_BUDGET, help="most statements a handler may hold")
    ap.add_argument("--list", action="store_true", help="list the handlers found instead of checking")
    args = ap.parse_args(argv)

    root = args.root.resolve()
    if args.list:
        for handler in handlers(delivery_modules(root)):
            print(f"{handler.statements:4}  {handler.name}")
        return 0

    problems = check(root, args.budget)
    if problems:
        print("\n".join(problems))
        print(f"\n{len(problems)} thin-handler problem(s)", file=sys.stderr)
        return 1
    count = len(handlers(delivery_modules(root)))
    print(f"OK: {count} CLI command and API route handlers within {args.budget} statements")
    return 0


if __name__ == "__main__":
    sys.exit(main())
