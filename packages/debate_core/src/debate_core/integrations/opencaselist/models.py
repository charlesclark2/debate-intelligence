"""The API's response bodies as it sends them, and their translation into the port's values.

These are the *wire* models: they accept what OpenCaselist returns and nothing here is a domain
decision. Each one ignores fields it does not declare, because the API adds columns (its caselist
and OpenEv endpoints return `SELECT *`) and a new column must not stop a scheduled pull. What they
do not tolerate is a missing field the translation needs: that is
:class:`~debate_core.application.ports.caselist_source.UnexpectedCaselistResponse`, raised by the
resource module that asked.

The shapes follow the upstream OpenAPI definitions (`server/v1/routes/definitions/schemas/` in
`ashtarcommunications/caselist`) and the columns the controllers actually return; the fixtures in
`packages/debate_core/tests/fixtures/opencaselist/` record both, and their README says which is which.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from debate_core.application.ports.caselist_source import (
    ArchiveKind,
    ArchiveListing,
    CaselistInfo,
    OpenEvFile,
)
from debate_core.domain.caselist import CASELIST_SLUG_PATTERN

__all__ = [
    "ARCHIVE_NAME_PATTERN",
    "CaselistRecord",
    "DownloadRecord",
    "LoginResponse",
    "OpenEvRecord",
    "parse_archive_name",
]

ARCHIVE_NAME_PATTERN: Final = re.compile(
    r"^(?P<caselist>[a-z]+[0-9]{2})-(?P<kind>weekly|all)-(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})\.zip$"
)
"""How the site names its archives (`controllers/download/weeklyArchives.js` upstream)."""

_KINDS: Final = {"weekly": ArchiveKind.WEEKLY, "all": ArchiveKind.FULL}
_SLUG: Final = re.compile(CASELIST_SLUG_PATTERN)


class _WireModel(BaseModel):
    """Tolerant of unknown fields, frozen once read."""

    model_config = ConfigDict(extra="ignore", frozen=True)


class CaselistRecord(_WireModel):
    """`Caselist` as `GET /caselists` and `GET /caselists/{caselist}` return it."""

    name: str | None = None
    """The identifier the `{caselist}` path parameter is matched against: `hsld26`."""
    slug: str | None = None
    """Declared by the OpenAPI schema; the site's URL form, e.g. `/hsld26`."""
    caselist_id: int | None = None
    display_name: str | None = None
    event: str | None = None
    level: str | None = None
    year: int | None = None
    archived: bool = False

    @field_validator("archived", mode="before")
    @classmethod
    def _mysql_boolean(cls, value: object) -> object:
        # The list endpoint returns the column as stored (0/1); the single one converts it.
        return bool(value) if isinstance(value, int) else value

    def caselist_slug(self) -> str | None:
        """The slug, from `name`, or from `slug` without its leading `/`; `None` if neither is one."""
        for candidate in (self.name, (self.slug or "").strip("/")):
            if candidate and _SLUG.match(candidate):
                return candidate
        return None

    def to_info(self) -> CaselistInfo | None:
        slug = self.caselist_slug()
        if slug is None:
            return None
        return CaselistInfo(
            slug=slug,
            caselist_id=self.caselist_id,
            display_name=self.display_name,
            event=self.event,
            level=self.level,
            year=self.year,
            archived=self.archived,
        )


class DownloadRecord(_WireModel):
    """`Download` as `GET /caselists/{caselist}/downloads` returns it: a name and a URL."""

    name: str
    url: str

    def to_listing(self, caselist: str) -> ArchiveListing:
        kind, archive_date = parse_archive_name(self.name, caselist)
        return ArchiveListing(
            caselist=caselist, name=self.name, kind=kind, archive_date=archive_date, url=self.url
        )


def parse_archive_name(name: str, caselist: str) -> tuple[ArchiveKind, date | None]:
    """The archive's kind and date from its name, or UNRECOGNISED with no date.

    A name for a different caselist than the one asked about is UNRECOGNISED too: it is not an
    archive of this caselist, whatever else it is.
    """
    match = ARCHIVE_NAME_PATTERN.match(name)
    if match is None or match["caselist"] != caselist:
        return ArchiveKind.UNRECOGNISED, None
    try:
        archive_date = date.fromisoformat(match["date"])
    except ValueError:
        return ArchiveKind.UNRECOGNISED, None
    return _KINDS[match["kind"]], archive_date


class OpenEvRecord(_WireModel):
    """`File` as `GET /openev` returns it."""

    openev_id: int
    path: str = Field(repr=False)
    name: str | None = None
    filename: str | None = None
    title: str | None = None
    year: int | None = None
    camp: str | None = None
    lab: str | None = None
    tags: dict[str, Any] | str | None = None
    """An object in the OpenAPI schema; the JSON text the column stores in some responses."""

    def tag_names(self) -> tuple[str, ...]:
        """The tags set on the file, sorted. Unparseable tag text yields none rather than a guess."""
        tags: object = self.tags
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except ValueError:
                return ()
        if not isinstance(tags, dict):
            return ()
        return tuple(sorted(str(key) for key, value in tags.items() if value))  # type: ignore[reportUnknownVariableType]

    def to_file(self) -> OpenEvFile:
        return OpenEvFile(
            openev_id=self.openev_id,
            path=self.path,
            filename=self.filename or self.name,
            title=self.title,
            year=self.year,
            camp=self.camp,
            lab=self.lab,
            tags=self.tag_names(),
        )


class LoginResponse(_WireModel):
    """What `POST /login` answers with on 201. Only `token` and `expires` are used."""

    token: SecretStr | None = None
    """A SecretStr from the moment it is parsed, so the model's `repr` cannot show it."""
    expires: str | None = None
