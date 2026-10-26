"""Reading the HTTP cassettes, and replaying them to the real fetcher (v1-e04-t06).

A cassette (`cassettes/<name>.json`, written by `build_cassettes.py`) is every response one fixture
URL needs: its origin's robots.txt and the page itself. Bodies are not copied into the cassette: each
response names a sample file under `tests/fixtures/` (t03's access samples, t04's extraction samples)
or carries a short text such as a robots.txt, so the bytes a cassette serves are exactly the bytes
those tasks' hand-written expectations were written from.

:class:`ReplayTransport` is an `httpx` transport that answers from loaded cassettes and nothing else.
It is handed to :class:`~debate_core.integrations.http_fetcher.HttpArticleFetcher`, which keeps every
gate of its own (public address, robots.txt, the per-host interval, redirects, size limits). A request
no cassette recorded is never sent anywhere: it is listed in :attr:`ReplayTransport.unrecorded` and
answered with a transport failure, and a test that sees one fails on it.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import httpx

__all__ = [
    "CASSETTE_DIRECTORY",
    "FIXTURES_ROOT",
    "Cassette",
    "Interaction",
    "ReplayTransport",
    "UnrecordedRequest",
    "cassette_names",
    "load_cassette",
]

CASSETTE_DIRECTORY: Final = Path(__file__).parent / "cassettes"
FIXTURES_ROOT: Final = Path(__file__).parents[1]
"""`tests/fixtures/`: a response's `body_file` is relative to it."""


@dataclass(frozen=True, slots=True)
class Interaction:
    """One recorded request and the response it gets."""

    method: str
    url: str
    status_code: int
    headers: tuple[tuple[str, str], ...]
    body: bytes
    body_file: str | None
    """The sample the body was read from, relative to `tests/fixtures/`; None for an inline body."""


@dataclass(frozen=True, slots=True)
class Cassette:
    """One fixture URL: what it stands for, and every response fetching it takes."""

    name: str
    kind: str
    """What the page imitates: news, think-tank, government, open-access PDF, paywalled, ..."""
    url: str
    """The URL a test fetches."""
    made_from: str
    """How the fixture was made, for the README: never a real site."""
    interactions: tuple[Interaction, ...]

    @property
    def page(self) -> Interaction | None:
        """The interaction for `url` itself; None when robots.txt refuses it, so it is never asked for."""
        return next((interaction for interaction in self.interactions if interaction.url == self.url), None)


def cassette_names() -> list[str]:
    """Every committed cassette's name, sorted."""
    return sorted(path.stem for path in CASSETTE_DIRECTORY.glob("*.json"))


def load_cassette(name: str) -> Cassette:
    """The committed cassette `name`, with each response's body read from its sample."""
    document: dict[str, Any] = json.loads((CASSETTE_DIRECTORY / f"{name}.json").read_text(encoding="utf-8"))
    return Cassette(
        name=name,
        kind=document["kind"],
        url=document["url"],
        made_from=document["made_from"],
        interactions=tuple(_interaction(entry) for entry in document["interactions"]),
    )


def _interaction(entry: dict[str, Any]) -> Interaction:
    request, response = entry["request"], entry["response"]
    body_file = response.get("body_file")
    body = (
        (FIXTURES_ROOT / body_file).read_bytes() if body_file is not None else response["body_text"].encode()
    )
    return Interaction(
        method=request["method"],
        url=request["url"],
        status_code=response["status_code"],
        headers=tuple((name, value) for name, value in response["headers"].items()),
        body=body,
        body_file=body_file,
    )


class UnrecordedRequest(httpx.TransportError):
    """A request no loaded cassette answers. Nothing was sent."""


class ReplayTransport(httpx.AsyncBaseTransport):
    """Answers each request from the loaded cassettes, by method and exact URL; sends nothing."""

    def __init__(self, cassettes: Iterable[Cassette]) -> None:
        self._answers: dict[tuple[str, str], Interaction] = {}
        for cassette in cassettes:
            for interaction in cassette.interactions:
                self._answers[(interaction.method, interaction.url)] = interaction
        self.requested: list[str] = []
        """Every URL asked for, in order."""
        self.unrecorded: list[str] = []
        """Every URL asked for that no cassette answers."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requested.append(url)
        answer = self._answers.get((request.method, url))
        if answer is None:
            self.unrecorded.append(url)
            raise UnrecordedRequest(f"no cassette answers {request.method} {url}", request=request)
        return httpx.Response(
            answer.status_code, headers=list(answer.headers), content=answer.body, request=request
        )
