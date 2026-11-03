"""debate_core.retrieval reaches no network, now or on first use (`v1-e04-t01`, forbidden list).

The workspace's `--disable-socket` stops a test from opening a socket. This scan covers what that
cannot: code that would only reach the network outside a test, such as a public-suffix library
refreshing its list on first use. Fetching belongs to the adapter in debate_core.integrations
(v1-e04-t02), and the layers contract keeps retrieval from importing it.
"""

from __future__ import annotations

import ast
from importlib import resources

import pytest

NETWORK_MODULES = frozenset(
    {
        "socket",
        "ssl",
        "http",
        "urllib.request",
        "urllib3",
        "httpx",
        "requests",
        "aiohttp",
        "ftplib",
        "smtplib",
        "tldextract",
    }
)


def _imported_modules(source: str) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
            modules.update(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


def _reaches_network(module: str) -> bool:
    return any(module == banned or module.startswith(f"{banned}.") for banned in NETWORK_MODULES)


def _retrieval_sources() -> list[tuple[str, str]]:
    package = resources.files("debate_core.retrieval")
    return [
        (entry.name, entry.read_text(encoding="utf-8"))
        for entry in package.iterdir()
        if entry.name.endswith(".py")
    ]


def test_the_scan_sees_the_package() -> None:
    names = {name for name, _ in _retrieval_sources()}
    assert {"canonical_url.py", "identifiers.py", "public_suffix.py", "query_parameters.py"} <= names


@pytest.mark.parametrize(("name", "source"), _retrieval_sources(), ids=lambda value: str(value)[:40])
def test_no_retrieval_module_imports_a_network_library(name: str, source: str) -> None:
    assert not {module for module in _imported_modules(source) if _reaches_network(module)}, name


def test_the_scan_catches_each_import_form() -> None:
    assert _reaches_network("urllib.request")
    assert any(_reaches_network(m) for m in _imported_modules("from urllib import request"))
    assert any(_reaches_network(m) for m in _imported_modules("import http.client"))
    assert not any(_reaches_network(m) for m in _imported_modules("from urllib.parse import urlsplit"))
