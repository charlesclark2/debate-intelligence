"""Where disclosed archives and OpenEv files come from: the boundary the scheduled pull reads across.

The scheduled sync (v1-e34-t02) asks a :class:`CaselistArchiveSource` what archives a caselist has
published and for their bytes, and hands what lands in the inbox to the importer (v1-e30-t03/t04).
The one implementation is :class:`~debate_core.integrations.opencaselist.OpenCaselistClient`, over
the documented API at `api.opencaselist.com/v1`, used only as
`docs/policies/caselist-data-use.md` permits.

## A download is a window, and a dropped one is gone

ADR-0016: an archive holds roughly the last seven days of modifications, nothing returns a complete
caselist, and consecutive weekly archives barely overlap. A download this port fails to deliver is
not retried later by anything — so every method here **fails loudly**. A partial file never reaches
the inbox, a byte count that does not match is an error rather than a warning, and a listing entry
whose name does not say what it is comes back marked :attr:`ArchiveKind.UNRECOGNISED` with no date
rather than with a guessed one.

## What the API actually lists

`GET /caselists/{caselist}/downloads` returns `{name, url}` pairs and nothing else: no size and no
date (the upstream OpenAPI `Download` schema). The date comes from the name, which the site builds
as `<caselist>-weekly-<YYYY-MM-DD>.zip` (files changed in the week before that date) or
`<caselist>-all-<YYYY-MM-DD>.zip` (every open-source file still attached to a round). The size is
unknown until the download's `Content-Length`, which is what the byte count is checked against.

## Errors

Everything raised across this port is a
:class:`~debate_core.application.errors.DomainError`. Transport failures that outlast the retries
arrive as :class:`~debate_core.application.errors.ProviderUnavailable` or
:class:`~debate_core.application.errors.ProviderRateLimited` with provider `"opencaselist"`; the
rest are below. No message carries the caselist_token, a Tabroom credential, a disclosure path or a
file name from inside an archive (`docs/policies/caselist-data-use.md`).
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Final, Protocol

from pydantic import Field

from debate_core.application.errors import DomainError
from debate_core.application.settings import ConfigurationError
from debate_core.domain import DomainModel, Sha256Hex
from debate_core.domain.caselist import CaselistSlug

__all__ = [
    "OPENCASELIST_PROVIDER",
    "ArchiveKind",
    "ArchiveListing",
    "ArchiveUnavailable",
    "CaselistApiDisabled",
    "CaselistArchiveSource",
    "CaselistAuthExpired",
    "CaselistInfo",
    "CaselistLoginRejected",
    "CaselistTokenMissing",
    "DownloadConflict",
    "DownloadIntegrityError",
    "DownloadedFile",
    "InvalidCaselistSlug",
    "OpenEvFile",
    "UnexpectedCaselistResponse",
    "UnsafeDownloadName",
]

OPENCASELIST_PROVIDER: Final = "opencaselist"
"""The provider name on every :class:`~debate_core.application.errors.ProviderError` from this port."""


# ------------------------------------------------------------------------------------------------
# Values
# ------------------------------------------------------------------------------------------------


class CaselistInfo(DomainModel):
    """One caselist as the API describes it."""

    slug: CaselistSlug = Field(description="What the API's `{caselist}` path takes: `hsld26`.")
    caselist_id: int | None = None
    display_name: str | None = None
    event: str | None = Field(default=None, description="The API's event code, e.g. `ld`, `cx`, `pf`.")
    level: str | None = None
    year: int | None = None
    archived: bool = False


class ArchiveKind(StrEnum):
    """Which of the site's two archive builds a download is, read from its name."""

    WEEKLY = "WEEKLY"
    """`<caselist>-weekly-<date>.zip`: open-source files changed in the week before `date`."""
    FULL = "FULL"
    """`<caselist>-all-<date>.zip`: every open-source file still attached to a round on `date`."""
    UNRECOGNISED = "UNRECOGNISED"
    """A name that follows neither pattern. Listed, never dated by guesswork."""


class ArchiveListing(DomainModel):
    """One downloadable archive of a caselist."""

    caselist: CaselistSlug
    name: str = Field(description="The archive's file name, e.g. `hsld26-weekly-2026-09-15.zip`.")
    kind: ArchiveKind
    archive_date: date | None = Field(
        description="The date in the name; `None` only for an UNRECOGNISED name."
    )
    url: str = Field(description="Where the bytes are. Not on the API host, and never sent the token.")
    size_bytes: int | None = Field(
        default=None,
        ge=0,
        description="Not in the API's listing; known only once a download's Content-Length arrives.",
    )


class OpenEvFile(DomainModel):
    """One OpenEv camp file as `GET /openev` lists it."""

    openev_id: int = Field(ge=1)
    path: str = Field(repr=False, description="What `GET /download?path=` takes. Never logged or shown.")
    filename: str | None = None
    title: str | None = None
    year: int | None = None
    camp: str | None = None
    lab: str | None = None
    tags: tuple[str, ...] = Field(default=(), description="The tag names set on the file.")


class DownloadedFile(DomainModel):
    """A file that is now whole, checked and in the inbox."""

    path: Path = Field(description="Its final place in the inbox, after the atomic rename.")
    sha256: Sha256Hex
    byte_size: int = Field(ge=1)
    source_name: str = Field(description="The archive's name, or `openev-<id>` for an OpenEv file.")
    already_present: bool = Field(
        default=False,
        description="True when an identical file was already in the inbox and was left untouched.",
    )


# ------------------------------------------------------------------------------------------------
# The port
# ------------------------------------------------------------------------------------------------


class CaselistArchiveSource(Protocol):
    """Lists caselists, their archives and OpenEv files, and delivers their bytes to an inbox.

    The caselist slug is always an argument; nothing behind this port knows a slug of its own.
    Downloads happen one at a time and count against one shared rate limit, archives and OpenEv
    files together.
    """

    async def list_caselists(self, *, archived: bool | None = None) -> list[CaselistInfo]:
        """Every caselist the API lists, optionally only archived or only current ones."""
        ...

    async def get_caselist(self, caselist: str) -> CaselistInfo:
        """One caselist. Raises :class:`~debate_core.application.errors.NotFound` for an unknown slug."""
        ...

    async def list_archives(self, caselist: str) -> list[ArchiveListing]:
        """The archives a caselist has available for download now, oldest date first."""
        ...

    async def list_openev(self, *, year: int | None = None) -> list[OpenEvFile]:
        """The OpenEv camp files for `year`, or the API's current year when `None`."""
        ...

    async def download_archive(self, archive: ArchiveListing, inbox: Path) -> DownloadedFile:
        """Stream one archive into `inbox` under its own name, checked, renamed atomically."""
        ...

    async def download_openev(self, file: OpenEvFile, inbox: Path) -> DownloadedFile:
        """Stream one OpenEv file into `inbox` as `openev-<id>-<filename>`, the same way."""
        ...


# ------------------------------------------------------------------------------------------------
# Errors
# ------------------------------------------------------------------------------------------------


class CaselistApiDisabled(ConfigurationError):
    """`caselist.api_enabled` is false, so nothing may reach OpenCaselist."""

    def __init__(self) -> None:
        super().__init__(
            "the OpenCaselist API is disabled for this installation (caselist.api_enabled is "
            "false). Turning it on is the operator's decision under docs/policies/"
            "caselist-data-use.md (E34 gate); set DEBATE_CASELIST__API_ENABLED=true to make it",
            field="caselist.api_enabled",
        )


class InvalidCaselistSlug(ConfigurationError):
    """A caselist slug that is not letters then a two-digit year, refused before any request."""

    def __init__(self, slug: str) -> None:
        self.slug = slug
        super().__init__(
            f"{slug!r} is not a caselist slug (letters then a two-digit year, e.g. hsld26)",
            field="caselist",
        )


class CaselistTokenMissing(DomainError):
    """No caselist_token is stored, so no authenticated request can be made."""

    def __init__(self) -> None:
        super().__init__("no caselist_token is stored; run `debate-research caselist auth login` first")


class CaselistAuthExpired(DomainError):
    """The API answered 401 or 403. The run stops here; this is never retried (policy E34 gate 5)."""

    def __init__(self, status_code: int, operation: str) -> None:
        self.status_code = status_code
        self.operation = operation
        """What was being done, e.g. `list archives for hsld26`. Never a URL or a path."""
        super().__init__(
            f"OpenCaselist refused {operation} with HTTP {status_code}; the caselist_token has "
            "expired or been revoked. Run `debate-research caselist auth login` again. If it "
            "happens straight after a login, stop and tell the operator: access may have been "
            "suspended (policy clause 10)."
        )


class CaselistLoginRejected(DomainError):
    """`POST /login` refused the credentials. Names neither the username nor the password."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(
            f"OpenCaselist rejected the Tabroom login (HTTP {status_code}); check the username and "
            "password on tabroom.com. Nothing was stored."
        )


class ArchiveUnavailable(DomainError):
    """The file host answered 403 or 404 for an archive or file it had just listed."""

    def __init__(self, source_name: str, status_code: int) -> None:
        self.source_name = source_name
        self.status_code = status_code
        super().__init__(
            f"{source_name} could not be downloaded (HTTP {status_code}): the file host no longer "
            "serves it. Nothing was written. List the archives again; the site replaces its "
            "archives as it rebuilds them."
        )


class DownloadIntegrityError(DomainError):
    """A download did not arrive whole: its byte count disagrees with what the server declared."""

    def __init__(self, source_name: str, reason: str) -> None:
        self.source_name = source_name
        self.reason = reason
        super().__init__(f"{source_name} did not download intact: {reason}. Nothing was written.")


class DownloadConflict(DomainError):
    """The inbox already holds a *different* file under the same name. Neither is touched."""

    def __init__(self, destination: Path) -> None:
        self.destination = destination
        super().__init__(
            f"{destination.name} is already in the inbox with different contents; the download "
            "was discarded and the existing file left as it was. Import or move it, then pull again."
        )


class UnsafeDownloadName(DomainError):
    """A listed name that could not be written into the inbox safely (a separator, `..`, empty)."""

    def __init__(self, source_name: str) -> None:
        self.source_name = source_name
        super().__init__(f"refusing to write a download named {source_name!r} into the inbox")


class UnexpectedCaselistResponse(DomainError):
    """The API answered with a body this client cannot read as the documented shape."""

    def __init__(self, operation: str, reason: str) -> None:
        self.operation = operation
        super().__init__(f"OpenCaselist's answer to {operation} was not in the documented shape: {reason}")
