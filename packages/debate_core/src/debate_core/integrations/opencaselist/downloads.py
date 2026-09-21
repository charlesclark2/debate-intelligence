"""`GET /caselists/{caselist}/downloads`, and fetching the archives it lists.

The listing names each archive and gives a URL on the site's object store; the bytes come from
there, not from `/download` (upstream `getBulkDownloads.js` lists `weekly/<caselist>/*.zip` in the
store, and `weeklyArchives.js` deletes each archive from the API server once it is uploaded). The
file host is not the API host, so the transport sends it no token.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from debate_core.application.ports.caselist_source import (
    ArchiveKind,
    ArchiveListing,
    DownloadedFile,
    UnexpectedCaselistResponse,
)
from debate_core.integrations.opencaselist.caselists import checked_slug
from debate_core.integrations.opencaselist.inbox_writer import safe_inbox_name
from debate_core.integrations.opencaselist.models import DownloadRecord
from debate_core.integrations.opencaselist.redaction import logger
from debate_core.integrations.opencaselist.transport import OpenCaselistTransport

__all__ = ["ArchivesResource"]


class ArchivesResource:
    """A caselist's downloadable archives."""

    def __init__(self, transport: OpenCaselistTransport) -> None:
        self._transport = transport

    async def list(self, caselist: str) -> list[ArchiveListing]:
        slug = checked_slug(caselist)
        operation = f"list archives for {slug}"
        response = await self._transport.get_json(f"/caselists/{slug}/downloads", operation=operation)
        if not isinstance(response.body, list):
            raise UnexpectedCaselistResponse(operation, "expected a list")
        try:
            listings = [
                DownloadRecord.model_validate(raw).to_listing(slug)
                for raw in response.body  # type: ignore[reportUnknownVariableType]
            ]
        except ValidationError:
            raise UnexpectedCaselistResponse(operation, "an entry has no name or no url") from None
        unrecognised = sum(1 for listing in listings if listing.kind is ArchiveKind.UNRECOGNISED)
        if unrecognised:
            logger.warning(
                "OpenCaselist: %d archive(s) for %s have names that follow neither archive pattern; "
                "they are listed undated",
                unrecognised,
                slug,
            )
        logger.info("OpenCaselist: listed %d archive(s) for %s", len(listings), slug)
        return sorted(listings, key=lambda item: (item.archive_date is None, item.archive_date, item.name))

    async def download(self, archive: ArchiveListing, inbox: Path) -> DownloadedFile:
        name = safe_inbox_name(archive.name, source_name=archive.name)
        downloaded = await self._transport.download(
            archive.url,
            operation=f"download {name}",
            source_name=name,
            inbox=inbox,
            inbox_name=name,
            expected_size=archive.size_bytes,
        )
        logger.info(
            "OpenCaselist: %s %s, %d bytes, sha256 %s",
            "already had" if downloaded.already_present else "downloaded",
            name,
            downloaded.byte_size,
            downloaded.sha256,
        )
        return downloaded
