"""Where a card on the search pilot's card page came from, as a link out of the platform (`v1-e39-t11`).

The card page offers "Open on openCaselist" for a disclosed card, built only from what the index
already stores of the card's representative occurrence: its caselist, school and team code, and
"Find on OpenEv" for a camp card, from its camp and year (`v1-e39-t28`). A team's
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

## A camp card links to its camp's page on OpenEv (`v1-e39-t28`)

"Find on OpenEv" opens the camp's page, `https://opencaselist.com/openev/<year>/<word>`
(:data:`OPENEV_CAMP_PAGE_TEMPLATE`), which lists each of the camp's files with its download. The
operator confirmed that shape on 2026-10-31. It is not the file's own page: a file's address is the
API's download by path, which the index does not store and which refuses a browser not signed in. So
the label says it opens the camp's page, with the camp and year beside it.

The address is built from the occurrence's stored camp and year and from nothing else: never the file
title, the event, the OpenEv id or the request. The stored camp is the importer's canonical name from
the alias table (`camp_aliases.yaml`), which is not OpenEv's own word for the camp (the count of
`v1-e39-t28`: only one of three confirmed words is a stored value). So the word comes from the table's
`openev` section, which the caller passes in as `openev_words`, the camp's canonical name to its word,
filled only with words the operator confirmed by opening the page. A camp with no word there has no
link: the stored camp itself is never the address. Nor has `UNKNOWN`, the importer's "could not read",
whatever the table says, nor a word that is not one address word of letters and digits.

The year is the camp release's, and links only from :data:`OPENEV_ARCHIVE_FIRST_YEAR`, the oldest year
on OpenEv's sidebar, to the current season plus one by
:func:`~debate_core.domain.season.current_season_start`: a topic year's camp files arrive in June and
July, before its season starts on 1 August. An occurrence past the provenance limit has no link.

Until `v1-e39-t28` the link was built from the stored OpenEv id (`v1-e39-t16`), at
`https://opencaselist.com/openev/<id>`, which the operator found is OpenEv's page for a *year*. The id
is still stored on a format 3 index, for a later per-file link, and read for nothing here.

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
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Final

from debate_core.domain.caselist import CASELIST_SLUG_PATTERN, TEAM_CODE_MAX_LENGTH
from debate_core.domain.evidence_search import OccurrenceProvenance
from debate_core.domain.file_recipe import CAMP_STORE

__all__ = [
    "OPENCASELIST_LABEL",
    "OPENCASELIST_ORIGIN",
    "OPENEV_ARCHIVE_FIRST_YEAR",
    "OPENEV_CAMP_PAGE_TEMPLATE",
    "OPENEV_CAMP_WORD_PATTERN",
    "OPENEV_LABEL",
    "NoTeamPage",
    "SourceLink",
    "openev_camp_page_url",
    "source_link",
    "team_page_url",
    "why_no_team_page",
]

OPENCASELIST_ORIGIN: Final = "https://opencaselist.com"
"""The site a disclosed card's team page is on. A fixed origin: no part of a link is ever the request's."""

OPENCASELIST_LABEL: Final = "Open on openCaselist"

OPENEV_CAMP_PAGE_TEMPLATE: Final = f"{OPENCASELIST_ORIGIN}/openev/{{year}}/{{word}}"
"""A camp's page on OpenEv, OpenEv being openCaselist's section for camp files: the camp release's year
and OpenEv's own word for the camp. Confirmed by the operator for three 2026 camps on 2026-10-31."""

OPENEV_ARCHIVE_FIRST_YEAR: Final = 2013
"""The oldest year on OpenEv's sidebar. The newest linked is the current season plus one."""

OPENEV_CAMP_WORD_PATTERN: Final = r"[A-Za-z0-9]+"
"""One OpenEv address word, matched whole: the shape of the confirmed `HDC`, `UM7` and `UTNIF`."""

OPENEV_LABEL: Final = "Find on OpenEv"
"""It finds the file on its camp's page, which is what it opens: not the file itself."""

_SCHOOL_MAX_LENGTH: Final = 100
_CASELIST: Final = re.compile(CASELIST_SLUG_PATTERN)
_SCHOOL: Final = re.compile(rf"[A-Za-z0-9](?:[A-Za-z0-9-]{{0,{_SCHOOL_MAX_LENGTH - 2}}}[A-Za-z0-9])?")
_TEAM_CODE: Final = re.compile(rf"[A-Za-z0-9]{{1,{TEAM_CODE_MAX_LENGTH}}}")
"""Matched whole (`fullmatch`), so a trailing newline is no more part of an address than a slash is."""
_OPENEV_WORD: Final = re.compile(OPENEV_CAMP_WORD_PATTERN)
_UNREAD: Final = "UNKNOWN"
"""What the archive parser records for a school or team code it could not read, and the OpenEv
importer for a camp."""


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


def openev_camp_page_url(word: object, year: object, *, today: date) -> str | None:
    """A camp's page on OpenEv, from its OpenEv word and the release's year, or `None`."""
    return None


def source_link(
    occurrence: OccurrenceProvenance, *, openev_words: Mapping[str, str], today: date
) -> SourceLink | None:
    """The link to the page that publishes `occurrence`'s file, or `None` when none can be built.

    `openev_words` is the alias table's `openev` section, a canonical camp to its OpenEv word, and
    `today` the date the season is counted from: both are a camp card's only, and a disclosed card's
    link reads neither.
    """
    if occurrence.caselist == CAMP_STORE:
        return _openev_link(occurrence, openev_words, today)
    school, team_code = occurrence.school, occurrence.team_code
    if not occurrence.provenance or school is None or team_code is None:
        return None
    url = team_page_url(occurrence.caselist, school, team_code)
    return None if url is None else SourceLink(label=OPENCASELIST_LABEL, url=url)


def _openev_link(
    occurrence: OccurrenceProvenance, openev_words: Mapping[str, str], today: date
) -> SourceLink | None:
    """A camp occurrence's camp page on OpenEv, from its camp through the table and its year alone."""
    return None
