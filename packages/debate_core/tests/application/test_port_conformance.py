"""Every fake satisfies the port it stands for, and every port stays free of provider types.

Static conformance is the real check and it happens in `debate_core.testing.fakes`, where
`build_fake_ports` assigns each fake to a Protocol-annotated field: pyright strict fails there if
a fake drifts. This module adds the runtime half — that the methods are actually present under the
names the ports use — and guards the rule that makes the whole arrangement worth having: no port
signature mentions a provider's own types.
"""

from __future__ import annotations

import inspect

import pytest

from debate_core.application import ports
from debate_core.application.ports import (
    ArticleFetcher,
    ArticleRepository,
    CardRepository,
    Clock,
    ContentExtractor,
    IdGenerator,
    ModelRouter,
    SearchProvider,
    SearchRepository,
    SnapshotStore,
)
from debate_core.testing import build_fake_ports

THE_TEN_PORTS = (
    ArticleRepository,
    SnapshotStore,
    CardRepository,
    SearchRepository,
    SearchProvider,
    ArticleFetcher,
    ContentExtractor,
    ModelRouter,
    Clock,
    IdGenerator,
)


def test_the_task_declares_ten_ports_and_ten_ports_exist() -> None:
    assert len(THE_TEN_PORTS) == 10
    assert len({port.__name__ for port in THE_TEN_PORTS}) == 10


@pytest.mark.parametrize("port", THE_TEN_PORTS, ids=lambda port: port.__name__)
def test_each_port_is_a_protocol_that_can_be_checked_at_runtime(port: type) -> None:
    assert getattr(port, "_is_protocol", False), f"{port.__name__} is not a Protocol"
    assert getattr(port, "_is_runtime_protocol", False), f"{port.__name__} is not runtime_checkable"


def test_every_fake_is_an_instance_of_the_port_it_stands_for() -> None:
    fakes = build_fake_ports()
    supplied = (
        fakes.article_repository,
        fakes.snapshot_store,
        fakes.card_repository,
        fakes.search_repository,
        fakes.search_provider,
        fakes.article_fetcher,
        fakes.content_extractor,
        fakes.model_router,
        fakes.clock,
        fakes.id_generator,
    )
    assert len(supplied) == len(THE_TEN_PORTS)
    for port, fake in zip(THE_TEN_PORTS, supplied, strict=True):
        assert isinstance(fake, port), f"{type(fake).__name__} does not satisfy {port.__name__}"


FORBIDDEN_IN_A_PORT_MODULE = ("boto3", "botocore", "httpx", "sqlite3", "typer", "fastapi")


@pytest.mark.parametrize("module_name", ["persistence", "providers"])
def test_port_modules_import_nothing_from_a_provider_library(module_name: str) -> None:
    """The rule the ports exist for; v1-e02-t06-import-boundary-guard enforces it repo-wide."""
    source = inspect.getsource(getattr(ports, module_name))
    imports = [
        line
        for line in source.splitlines()
        if line.startswith(("import ", "from ")) and not line.startswith("from __future__")
    ]
    for line in imports:
        assert not any(forbidden in line for forbidden in FORBIDDEN_IN_A_PORT_MODULE), line
