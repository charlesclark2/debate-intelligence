"""`GET /openev`, and fetching an OpenEv camp file through `GET /download?path=`.

The path is the file's own (`openev/<year>/<camp>/<lab>/<file>`), which names a camp's file, so it
goes only into the request's query string — which the redaction filter scrubs from httpx's log
lines — and never into a log record or an error of this package's. Those name the file by its
`openev_id`.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from debate_core.application.ports.caselist_source import (
    DownloadedFile,
    OpenEvFile,
    UnexpectedCaselistResponse,
    UnsafeDownloadName,
    openev_inbox_name,
)
from debate_core.integrations.opencaselist.models import OpenEvRecord
from debate_core.integrations.opencaselist.redaction import logger
from debate_core.integrations.opencaselist.transport import OpenCaselistTransport

__all__ = ["OpenEvResource", "openev_inbox_name"]
"""`openev_inbox_name` moved to the port with `v1-e34-t02`, which needs it before a download;
it stays exported here because that is where it has been imported from since `v1-e34-t01`."""


class OpenEvResource:
    """OpenEv camp files."""

    def __init__(self, transport: OpenCaselistTransport) -> None:
        self._transport = transport

    async def list(self, *, year: int | None = None) -> list[OpenEvFile]:
        operation = "list OpenEv files" if year is None else f"list OpenEv files for {year}"
        params = {} if year is None else {"year": year}
        response = await self._transport.get_json("/openev", operation=operation, params=params)
        if not isinstance(response.body, list):
            raise UnexpectedCaselistResponse(operation, "expected a list")
        try:
            files = [
                OpenEvRecord.model_validate(raw).to_file()
                for raw in response.body  # type: ignore[reportUnknownVariableType]
            ]
        except ValidationError:
            raise UnexpectedCaselistResponse(operation, "an entry has no openev_id or no path") from None
        logger.info("OpenCaselist: listed %d OpenEv file(s)", len(files))
        return files

    async def download(self, file: OpenEvFile, inbox: Path) -> DownloadedFile:
        source_name = f"openev-{file.openev_id}"
        # The API refuses a path with `..` or a leading `/` (upstream getDownload.js); the listing
        # gives paths with a leading `/`, so it is removed, and `..` is refused here first.
        path = file.path.lstrip("/")
        if not path or ".." in path.split("/"):
            raise UnsafeDownloadName(source_name)
        downloaded = await self._transport.download(
            self._transport.api_url("/download"),
            operation=f"download OpenEv file {file.openev_id}",
            source_name=source_name,
            inbox=inbox,
            inbox_name=openev_inbox_name(file),
            params={"path": path},
        )
        logger.info(
            "OpenCaselist: %s OpenEv file %d, %d bytes, sha256 %s",
            "already had" if downloaded.already_present else "downloaded",
            file.openev_id,
            downloaded.byte_size,
            downloaded.sha256,
        )
        return downloaded
