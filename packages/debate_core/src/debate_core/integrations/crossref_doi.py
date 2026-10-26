"""Crossref DOI lookups for cites (v1-e06-t01). Skeleton."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final, Protocol

import httpx
from pydantic import SecretStr

from debate_core.application.ports.doi_metadata import DoiWork
from debate_core.application.settings import HttpSettings, ProviderSettings

__all__ = [
    "CROSSREF_CACHE_DIRECTORY",
    "CROSSREF_WORKS_URL",
    "PROVIDER_NAME",
    "CrossrefDoiClient",
    "DoiCache",
    "FileDoiCache",
    "InMemoryDoiCache",
    "crossref_doi_client",
    "work_from_message",
]

PROVIDER_NAME: Final = "crossref"
CROSSREF_WORKS_URL: Final = "https://api.crossref.org/works/"
CROSSREF_CACHE_DIRECTORY: Final = "crossref"


class DoiCache(Protocol):
    def get(self, doi: str) -> DoiWork | None: ...

    def put(self, doi: str, work: DoiWork) -> None: ...


class InMemoryDoiCache:
    def get(self, doi: str) -> DoiWork | None:
        return None

    def put(self, doi: str, work: DoiWork) -> None:
        return None


class FileDoiCache:
    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def get(self, doi: str) -> DoiWork | None:
        return None

    def put(self, doi: str, work: DoiWork) -> None:
        return None


def work_from_message(message: Mapping[str, Any], *, requested_doi: str) -> DoiWork | None:
    return None


class CrossrefDoiClient:
    def __init__(self, client: httpx.AsyncClient, *, contact_email: SecretStr | None, cache: DoiCache) -> None:
        self._client = client

    async def aclose(self) -> None:
        await self._client.aclose()

    async def lookup(self, doi: str) -> DoiWork | None:
        return None


def crossref_doi_client(
    http: HttpSettings,
    providers: ProviderSettings,
    *,
    version: str,
    cache: DoiCache,
    transport: httpx.AsyncBaseTransport | None = None,
) -> CrossrefDoiClient:
    client = httpx.AsyncClient(transport=transport)
    return CrossrefDoiClient(client, contact_email=providers.contact_email, cache=cache)
