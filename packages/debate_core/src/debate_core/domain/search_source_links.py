"""Where a card on the search pilot's card page came from, as a link out of the platform (`v1-e39-t11`).

The card page offers "Open on openCaselist" for a disclosed card, built only from what the index
already stores of the card's representative occurrence: its caselist, school and team code, and
"Open on OpenEv" for a camp card, from its stored OpenEv id. A team's
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

## A camp card links to its file on OpenEv (`v1-e39-t16`)

"Open on OpenEv" is built from the OpenEv id the index stores for a camp occurrence since format 3,
which the build reads from the release manifest's row for the file (`openev_id`, `v1-e30-t14`), and
from nothing else: never the camp, the year, the event or the file title. The title is the
importer's, with the camp, year and lab initials taken off the file name, so it names no OpenEv
address. A camp card whose row has no id (a file imported before `v1-e30-t14` and not named
`openev-<id>-…`, or any card of a format 1 or 2 index) has no link. The address's shape is
:data:`OPENEV_FILE_URL_TEMPLATE`'s, which the repository does not pin: see its note.

## Nothing here is the request's

The origin is fixed, and every part of the path is a stored value checked against the patterns
below, so no link is ever taken from a request (the task's forbidden "a redirect or link target taken
from the request"). The link opens in a new tab with no opener and no referrer, and is never logged
or audited: it leaves the platform.

## The landscape school view's team pages (`v1-e32-t18`)

The same rule gives each team in a landscape report's school view the link to its page
(:func:`team_page_url`), from the view's caselist, school and team code and nothing else: data-use
policy 1.14 allows exactly that link there. :func:`why_no_team_page` says which part kept a team from
having one, so the view can count them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from debate_core.domain.caselist import CASELIST_SLUG_PATTERN, TEAM_CODE_MAX_LENGTH
from debate_core.domain.evidence_search import OccurrenceProvenance
from debate_core.domain.file_recipe import CAMP_STORE

__all__ = [
    "OPENCASELIST_LABEL",
    "OPENCASELIST_ORIGIN",
    "OPENEV_FILE_URL_TEMPLATE",
    "OPENEV_LABEL",
    "NoTeamPage",
    "SourceLink",
    "openev_file_url",
    "source_link",
    "team_page_url",
    "why_no_team_page",
]

OPENCASELIST_ORIGIN: Final = "https://opencaselist.com"
"""The site a disclosed card's team page is on. A fixed origin: no part of a link is ever the request's."""

OPENCASELIST_LABEL: Final = "Open on openCaselist"

OPENEV_FILE_URL_TEMPLATE: Final = f"{OPENCASELIST_ORIGIN}/openev/{{openev_id}}"
"""Where a camp file is on OpenEv, by its id: OpenEv is openCaselist's section for camp files.

**Not pinned by anything the repository holds** (`v1-e39-t16`). The repository pins the API the pull
uses (`GET /openev`, and a download by the file's path through `GET /download?path=`), not a page a
browser opens, and the index stores the id, never the path. So the shape is this constant's, held by
a test, until the coach's check after the deploy to dev opens one link and confirms it or gives the
right one; changing it is this line and its test."""

OPENEV_LABEL: Final = "Open on OpenEv"

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


class NoTeamPage(StrEnum):
    """Why a team has no page link: the first part the rule refused, in the order it checks them."""

    UNREAD = "unread"
    """The parser could not read the school or the team code (`UNKNOWN`)."""
    CASELIST = "caselist"
    """The caselist is not a caselist slug."""
    SCHOOL = "school"
    """The school is not one address word: a display name with a space, say."""
    TEAM_CODE = "team_code"
    """The team code is not one address word of letters and digits."""


def why_no_team_page(caselist: str, school: str, team_code: str) -> NoTeamPage | None:
    """Why this team has no page link, or `None` when it has one."""
    if _UNREAD in (school, team_code):
        return NoTeamPage.UNREAD
    for reason, pattern, value in (
        (NoTeamPage.CASELIST, _CASELIST, caselist),
        (NoTeamPage.SCHOOL, _SCHOOL, school),
        (NoTeamPage.TEAM_CODE, _TEAM_CODE, team_code),
    ):
        if pattern.fullmatch(value) is None:
            return reason
    return None


def team_page_url(caselist: str, school: str, team_code: str) -> str | None:
    """The team's page on openCaselist, or `None` when :func:`why_no_team_page` gives a reason."""
    if why_no_team_page(caselist, school, team_code) is not None:
        return None
    return f"{OPENCASELIST_ORIGIN}/{caselist}/{school}/{team_code}"


def openev_file_url(openev_id: object) -> str | None:
    """A camp file's address on OpenEv, from its id, or `None` for a value that is no OpenEv id: one read
    from an index row is checked again here, a boolean, zero or a negative number refused."""
    if isinstance(openev_id, bool) or not isinstance(openev_id, int) or openev_id < 1:
        return None
    return OPENEV_FILE_URL_TEMPLATE.format(openev_id=openev_id)


def source_link(occurrence: OccurrenceProvenance) -> SourceLink | None:
    """The link to the page that publishes `occurrence`'s file, or `None` when none can be built."""
    if occurrence.caselist == CAMP_STORE:
        return _openev_link(occurrence)
    school, team_code = occurrence.school, occurrence.team_code
    if not occurrence.provenance or school is None or team_code is None:
        return None
    url = team_page_url(occurrence.caselist, school, team_code)
    return None if url is None else SourceLink(label=OPENCASELIST_LABEL, url=url)


def _openev_link(occurrence: OccurrenceProvenance) -> SourceLink | None:
    """A camp occurrence's file on OpenEv, from its stored id alone: never its title, camp or year."""
    if not occurrence.provenance or occurrence.openev_id is None:
        return None
    url = openev_file_url(occurrence.openev_id)
    return None if url is None else SourceLink(label=OPENEV_LABEL, url=url)
