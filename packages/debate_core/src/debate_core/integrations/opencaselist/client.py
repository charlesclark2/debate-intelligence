"""`OpenCaselistClient`: the :class:`~debate_core.application.ports.caselist_source.CaselistArchiveSource`
over the OpenCaselist API.

The client is a thin composition: one
:class:`~debate_core.integrations.opencaselist.transport.OpenCaselistTransport`, shared by one small
module per resource group. V3 (v3-e24-t02) adds `schools`, `teams`, `rounds` and `cites` modules
beside these and hands them the same transport; nothing about auth, pacing or backoff changes.

## It refuses to exist unless the operator has turned it on

:meth:`OpenCaselistClient.from_settings` raises
:class:`~debate_core.application.ports.caselist_source.CaselistApiDisabled` unless
`caselist.api_enabled` is true (off by default: the data-use policy's E34 gate is the operator's
decision), and a :class:`~debate_core.application.settings.ConfigurationError` when
`allow_network` is false, which is what the `test` environment sets. No request is ever built by
a client that was refused.

## Where the token comes from

`providers.caselist_token` when it is set (an environment variable, for a machine where the store
is not the right place), otherwise the
:class:`~debate_core.integrations.opencaselist.token_store.CaselistTokenStore`. It is read when the
first authenticated request needs it, not at construction, so `caselist auth login` can build a
client before any token exists.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from types import TracebackType
from typing import Self

import httpx
from pydantic import SecretStr

from debate_core.application.ports.caselist_source import (
    ArchiveListing,
    CaselistApiDisabled,
    CaselistInfo,
    CaselistTokenMissing,
    DownloadedFile,
    OpenEvFile,
)
from debate_core.application.settings import ConfigurationError, Settings
from debate_core.integrations.opencaselist.auth import IssuedToken, LoginResource
from debate_core.integrations.opencaselist.caselists import CaselistsResource
from debate_core.integrations.opencaselist.downloads import ArchivesResource
from debate_core.integrations.opencaselist.openev import OpenEvResource
from debate_core.integrations.opencaselist.redaction import register_secret
from debate_core.integrations.opencaselist.token_store import CaselistTokenStore
from debate_core.integrations.opencaselist.transport import OpenCaselistTransport, TransportPolicy

__all__ = ["OpenCaselistClient", "NetworkDisallowed"]


class NetworkDisallowed(ConfigurationError):
    """`allow_network` is false for this environment, so the client will not be built."""

    def __init__(self) -> None:
        super().__init__(
            "this environment forbids outbound calls (allow_network is false), so the OpenCaselist "
            "client was not built",
            field="allow_network",
        )


class OpenCaselistClient:
    """Lists and downloads from OpenCaselist, politely, as the operator."""

    def __init__(self, transport: OpenCaselistTransport) -> None:
        self.transport = transport
        self.caselists = CaselistsResource(transport)
        self.archives = ArchivesResource(transport)
        self.openev = OpenEvResource(transport)
        self.auth = LoginResource(transport)

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        token_store: CaselistTokenStore,
        user_agent_version: str,
        http_client: httpx.AsyncClient | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> Self:
        """Build the client this installation is configured for, or refuse to.

        Raises :class:`CaselistApiDisabled` unless `caselist.api_enabled`, and
        :class:`NetworkDisallowed` when `allow_network` is false.
        """
        caselist = settings.caselist
        if not caselist.api_enabled:
            raise CaselistApiDisabled
        if not settings.allow_network:
            raise NetworkDisallowed
        configured_token = settings.providers.caselist_token

        def token_source() -> SecretStr:
            if configured_token is not None and configured_token.get_secret_value():
                register_secret(configured_token.get_secret_value())
                return configured_token
            stored = token_store.load()
            if stored is None:
                raise CaselistTokenMissing
            return stored.token

        def on_authenticated_success() -> None:
            if configured_token is None:
                token_store.record_validation()

        transport = OpenCaselistTransport(
            base_url=caselist.api_base_url,
            user_agent=settings.http.user_agent(user_agent_version),
            policy=TransportPolicy(
                min_interval_seconds=caselist.min_request_interval_seconds,
                downloads_per_minute=caselist.downloads_per_minute,
                max_attempts=caselist.max_attempts,
                backoff_base_seconds=caselist.backoff_base_seconds,
                max_retry_wait_seconds=caselist.max_retry_wait_seconds,
                max_download_bytes=caselist.max_archive_bytes,
            ),
            token_source=token_source,
            timeout=httpx.Timeout(
                settings.http.request_timeout_seconds, connect=settings.http.connect_timeout_seconds
            ),
            on_authenticated_success=on_authenticated_success,
            http_client=http_client,
            clock=clock,
            sleep=sleep,
        )
        return cls(transport)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self.transport.aclose()

    # --- CaselistArchiveSource ------------------------------------------------------------------

    async def list_caselists(self, *, archived: bool | None = None) -> list[CaselistInfo]:
        return await self.caselists.list(archived=archived)

    async def get_caselist(self, caselist: str) -> CaselistInfo:
        return await self.caselists.get(caselist)

    async def list_archives(self, caselist: str) -> list[ArchiveListing]:
        return await self.archives.list(caselist)

    async def list_openev(self, *, year: int | None = None) -> list[OpenEvFile]:
        return await self.openev.list(year=year)

    async def download_archive(self, archive: ArchiveListing, inbox: Path) -> DownloadedFile:
        return await self.archives.download(archive, inbox)

    async def download_openev(self, file: OpenEvFile, inbox: Path) -> DownloadedFile:
        return await self.openev.download(file, inbox)

    # --- Auth -----------------------------------------------------------------------------------

    async def login(self, username: str, password: SecretStr) -> IssuedToken:
        """Trade Tabroom credentials for a token. The caller stores the token; nothing here does."""
        return await self.auth.login(username, password)
