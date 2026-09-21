"""`GET /caselists` and `GET /caselists/{caselist}`."""

from __future__ import annotations

import re
from typing import Any, Final

from pydantic import ValidationError

from debate_core.application.ports.caselist_source import (
    CaselistInfo,
    InvalidCaselistSlug,
    UnexpectedCaselistResponse,
)
from debate_core.domain.caselist import CASELIST_SLUG_PATTERN
from debate_core.integrations.opencaselist.models import CaselistRecord
from debate_core.integrations.opencaselist.redaction import logger
from debate_core.integrations.opencaselist.transport import OpenCaselistTransport

__all__ = ["CaselistsResource", "checked_slug"]

_SLUG: Final = re.compile(CASELIST_SLUG_PATTERN)


def checked_slug(caselist: str) -> str:
    """`caselist` if it is a slug, refused before it is put into a URL path otherwise."""
    if not _SLUG.match(caselist):
        raise InvalidCaselistSlug(caselist)
    return caselist


class CaselistsResource:
    """The caselists themselves."""

    def __init__(self, transport: OpenCaselistTransport) -> None:
        self._transport = transport

    async def list(self, *, archived: bool | None = None) -> list[CaselistInfo]:
        operation = "list caselists"
        params = {} if archived is None else {"archived": archived}
        response = await self._transport.get_json("/caselists", operation=operation, params=params)
        if not isinstance(response.body, list):
            raise UnexpectedCaselistResponse(operation, "expected a list")
        infos: list[CaselistInfo] = []
        unreadable = 0
        for raw in response.body:  # type: ignore[reportUnknownVariableType]
            info = _info_or_none(raw)
            if info is None:
                unreadable += 1
            else:
                infos.append(info)
        if unreadable:
            logger.warning(
                "OpenCaselist: %d caselist(s) listed without a usable slug were left out", unreadable
            )
        logger.info("OpenCaselist: listed %d caselist(s)", len(infos))
        return infos

    async def get(self, caselist: str) -> CaselistInfo:
        slug = checked_slug(caselist)
        operation = f"get caselist {slug}"
        response = await self._transport.get_json(f"/caselists/{slug}", operation=operation)
        info = _info_or_none(response.body)
        if info is None:
            raise UnexpectedCaselistResponse(operation, "no usable caselist slug in the answer")
        return info


def _info_or_none(raw: Any) -> CaselistInfo | None:
    try:
        return CaselistRecord.model_validate(raw).to_info()
    except ValidationError:
        return None
