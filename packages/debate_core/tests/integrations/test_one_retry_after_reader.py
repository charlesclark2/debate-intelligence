"""One `Retry-After` reader in `debate_core.integrations`, and a failing test for a second (`v1-e07-t08`).

Three adapters read the header, and until `v1-e07-t08` OpenCaselist's transport had its own copy,
which measured an HTTP date from the wall clock instead of an injected one. Every module in the
package is parsed here, and it fails when:

* a function outside :mod:`debate_core.integrations.retry_after` has `retry_after` in its name (a
  re-added `_retry_after` or a second `retry_after_seconds`);
* the header's name, `Retry-After` in any case, appears in code anywhere but as an argument of a
  call to `retry_after_seconds`: the header's value goes straight into the shared reader;
* an HTTP date is parsed (`email.utils.parsedate_to_datetime`, `parsedate`, `parsedate_tz`) outside
  the shared reader and the modules listed in :data:`OTHER_HTTP_DATE_READERS` with their reason;
* the discovery mapping, the article fetcher or the transport stops calling the shared reader.

The checks run on synthetic copies first, so a check that can no longer fail is caught too.
"""

from __future__ import annotations

import ast
import importlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypeGuard

import pytest

import debate_core.integrations
from debate_core.integrations import retry_after

PACKAGE: Final = Path(debate_core.integrations.__file__).parent
SHARED_READER: Final = "debate_core.integrations.retry_after"
READER_NAME: Final = "retry_after_seconds"
HEADER: Final = "retry-after"
HTTP_DATE_PARSERS: Final = frozenset({"parsedate_to_datetime", "parsedate", "parsedate_tz"})

OTHER_HTTP_DATE_READERS: Final = {
    "debate_core.integrations.discovery.feed_parsing": "an RSS `pubDate` is an RFC 822 date, not a header",
}
"""Modules that parse an HTTP-style date for something other than `Retry-After`, and why."""

ADAPTERS: Final = (
    "debate_core.integrations.discovery.http_failures",
    "debate_core.integrations.http_fetcher",
    "debate_core.integrations.opencaselist.transport",
)
"""The three readers `v1-e07-t08` points at the shared one."""


@dataclass(frozen=True, slots=True)
class Violation:
    module: str
    line: int
    why: str

    def __str__(self) -> str:
        return f"{self.module}:{self.line}: {self.why}"


def violations(module: str, source: str) -> list[Violation]:
    """Every way `source` reads `Retry-After` other than through the shared reader."""
    if module == SHARED_READER:
        return []
    tree = ast.parse(source)
    found: list[Violation] = []
    docstrings = _docstring_ids(tree)
    for node, ancestors in _walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and "retry_after" in node.name.lower():
            found.append(
                Violation(module, node.lineno, f"defines {node.name}(), a second Retry-After reader")
            )
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.strip().lower() == HEADER
            and id(node) not in docstrings
            and not any(_calls_reader(ancestor) for ancestor in ancestors)
        ):
            found.append(
                Violation(module, node.lineno, f"reads {node.value!r} without passing it to {READER_NAME}()")
            )
        elif module not in OTHER_HTTP_DATE_READERS and _names_http_date_parser(node):
            found.append(Violation(module, node.lineno, "parses an HTTP date outside the shared reader"))
    return found


def _walk(
    node: ast.AST, ancestors: tuple[ast.AST, ...] = ()
) -> Iterator[tuple[ast.AST, tuple[ast.AST, ...]]]:
    yield node, ancestors
    for child in ast.iter_child_nodes(node):
        yield from _walk(child, (*ancestors, node))


def _docstring_ids(tree: ast.Module) -> set[int]:
    owners = [
        tree,
        *(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)),
    ]
    return {
        id(owner.body[0].value)
        for owner in owners
        if owner.body
        and isinstance(owner.body[0], ast.Expr)
        and isinstance(owner.body[0].value, ast.Constant)
    }


def _calls_reader(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    called = node.func
    return (isinstance(called, ast.Name) and called.id == READER_NAME) or (
        isinstance(called, ast.Attribute) and called.attr == READER_NAME
    )


def _names_http_date_parser(node: ast.AST) -> TypeGuard[ast.Name | ast.Attribute | ast.ImportFrom]:
    if isinstance(node, ast.Name):
        return node.id in HTTP_DATE_PARSERS
    if isinstance(node, ast.Attribute):
        return node.attr in HTTP_DATE_PARSERS
    if isinstance(node, ast.ImportFrom):
        return any(alias.name in HTTP_DATE_PARSERS for alias in node.names)
    return False


def _package_modules() -> dict[str, str]:
    modules: dict[str, str] = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        parts = path.relative_to(PACKAGE.parent.parent).with_suffix("").parts
        name = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
        modules[name] = path.read_text(encoding="utf-8")
    return modules


# ------------------------------------------------------------------------------------------------
# The checks fail on a copy
# ------------------------------------------------------------------------------------------------

COPIES: Final = {
    "the transport's old reader, re-added": """
import email.utils
def _retry_after(response):
    raw = response.headers.get("Retry-After")
    return email.utils.parsedate_to_datetime(raw)
""",
    "a second retry_after_seconds taking the value": """
from email.utils import parsedate_to_datetime
def retry_after_seconds(value, *, now):
    return (parsedate_to_datetime(value) - now).total_seconds()
""",
    "a reader under another name": """
def wait_from(headers):
    return float(headers["RETRY-AFTER"])
""",
    "the header read beside the shared reader, not into it": """
from debate_core.integrations.retry_after import retry_after_seconds
def wait(headers, now):
    raw = headers.get("retry-after")
    return retry_after_seconds(raw, now=now)
""",
    "an HTTP date parsed under another name": """
from email import utils
def when(value):
    return utils.parsedate_tz(value)
""",
}


@pytest.mark.parametrize("source", COPIES.values(), ids=COPIES.keys())
def test_the_guard_fails_on_a_second_reader(source: str) -> None:
    assert violations("debate_core.integrations.some_adapter", source)


def test_the_guard_passes_the_header_going_straight_into_the_shared_reader() -> None:
    source = '''
"""Mentions Retry-After in prose, which is not a read."""
from debate_core.integrations.retry_after import retry_after_seconds
def wait(response, clock):
    """Retry-After"""
    return retry_after_seconds(response.headers.get("Retry-After"), now=clock.now())
'''
    assert violations("debate_core.integrations.some_adapter", source) == []


# ------------------------------------------------------------------------------------------------
# The package itself
# ------------------------------------------------------------------------------------------------


def test_nothing_in_integrations_reads_retry_after_but_the_shared_reader() -> None:
    modules = _package_modules()
    assert {SHARED_READER, *ADAPTERS, *OTHER_HTTP_DATE_READERS} <= modules.keys(), "the package was not found"

    found = [str(v) for name, source in modules.items() for v in violations(name, source)]

    assert found == []


@pytest.mark.parametrize("adapter", ADAPTERS)
def test_each_adapter_reads_retry_after_through_the_shared_reader(adapter: str) -> None:
    module = importlib.import_module(adapter)
    calls = [
        node for node in ast.walk(ast.parse(Path(str(module.__file__)).read_text())) if _calls_reader(node)
    ]

    assert module.retry_after_seconds is retry_after.retry_after_seconds
    assert calls, f"{adapter} imports the shared reader but never calls it"
