"""Where a card on the search pilot's card page came from, as a link out of the platform (`v1-e39-t11`).

The card page offers "Open on openCaselist" for a disclosed card, built only from what the index
already stores of the card's representative occurrence: its caselist, school and team code. A team's
page on openCaselist is `https://opencaselist.com/<caselist>/<school>/<team code>`, and it lists the
rounds the team disclosed with each file, so it is the page the file is published on.

## Only when the stored values are the address's own

The index's school and team code are the two directories a weekly archive files a disclosure under
(:mod:`debate_core.application.caselist.path_parser`). The link takes them to be the school's and the
team's names as openCaselist's own addresses spell them, one word each. That is what the archive's
directories look like: on the dev index of 2026-10-22, every one of 513 schools is one word of
letters, digits and inner hyphens (none has a space; nine have a hyphen), and every team code is
letters and digits. It was not checked against openCaselist itself, which a session does not call;
the coach's check after the deploy to dev opens one link and confirms it lands on the team's page.

A stored value that is not one such word cannot be an address's: a school with a space in it is a
display name, and a link built from it would land on the wrong page. Such a card, a card whose
disclosure is not on record, and one whose school or team code the parser could not read
(`UNKNOWN`) have no link.

## No camp card is linked

The index stores a camp card's camp, year, event and file title, and no OpenEv path or file id. The
title is the importer's, with the camp, year and lab initials taken off the file name, so it names no
OpenEv address either. A camp card has no link until the index stores one (the index's format
version 2 is `v1-e39-t13`'s).

## Nothing here is the request's

The origin is fixed, and every part of the path is a stored value checked against the patterns
below, so no link is ever taken from a request (the task's forbidden "a redirect or link target taken
from the request"). The link opens in a new tab with no opener and no referrer, and is never logged
or audited: it leaves the platform.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from debate_core.domain.caselist import CASELIST_SLUG_PATTERN, TEAM_CODE_MAX_LENGTH
from debate_core.domain.evidence_search import OccurrenceProvenance

__all__ = ["OPENCASELIST_ORIGIN", "SourceLink", "source_link"]

OPENCASELIST_ORIGIN: Final = "https://opencaselist.com"
"""The site a disclosed card's team page is on. A fixed origin: no part of a link is ever the request's."""

OPENCASELIST_LABEL: Final = "Open on openCaselist"

_SCHOOL_MAX_LENGTH: Final = 100
_CASELIST: Final = re.compile(CASELIST_SLUG_PATTERN)
_SCHOOL: Final = re.compile(rf"[A-Za-z0-9](?:[A-Za-z0-9-]{{0,{_SCHOOL_MAX_LENGTH - 2}}}[A-Za-z0-9])?")
_TEAM_CODE: Final = re.compile(rf"[A-Za-z0-9]{{1,{TEAM_CODE_MAX_LENGTH}}}")
"""Matched whole (`fullmatch`), so a trailing newline is no more part of an address than a slash is."""
_UNREAD: Final = "UNKNOWN"
"""What the archive parser records for a school or team code it could not read."""


@dataclass(frozen=True, slots=True)
class SourceLink:
    """A link out to where a card was published: the words to show, and the address."""

    label: str
    url: str


def source_link(occurrence: OccurrenceProvenance) -> SourceLink | None:
    """The link to the page that publishes `occurrence`'s file, or `None` when none can be built."""
    caselist, school, team_code = occurrence.caselist, occurrence.school, occurrence.team_code
    if not occurrence.provenance or school is None or team_code is None or _UNREAD in (school, team_code):
        return None
    if any(
        pattern.fullmatch(value) is None
        for pattern, value in ((_CASELIST, caselist), (_SCHOOL, school), (_TEAM_CODE, team_code))
    ):
        return None
    return SourceLink(label=OPENCASELIST_LABEL, url=f"{OPENCASELIST_ORIGIN}/{caselist}/{school}/{team_code}")
