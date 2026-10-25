"""The rules of the search pilot's landscape pages (`v1-e39-t17`, data-use policy 1.16, E39 gate item 11).

The pilot shows the newest published landscape bundle of each caselist, `report.md` and its per-school
view `schools.md`, to signed-in members. What is decided here holds whatever renders the pages:

* **Which pages there are** (:class:`LandscapePage`): the caselists, a caselist's report, its school
  view's front page, and one page per school and per position (the PM's layout ruling of 2026-10-25:
  `report.md` measured 66 KB rendered, `schools.md` 568 KB, against ADR-0019's page of 150 KB). The
  page kind is all an audit record says of where a member was, never which school or position.
* **Which bundle is the newest** (:func:`bundle_file`): a bundle is
  `reports/landscape/<caselist>/<snapshot>/<file>`, and `v1-e32-t03`'s run uploads `report.md` last,
  so a snapshot holding it is complete. The newest such snapshot is the one shown; a school view that
  a removal (`v1-e32-t13`) deleted from it is gone, and no older snapshot's is shown instead.
* **A heading's anchor** (:func:`heading_anchor`, :class:`Anchors`): GitHub's rule, as the report's own
  contents list writes it (:mod:`debate_core.arguments.landscape.render`), with `-2`, `-3` for a
  repeat on one page. A school's page is addressed by its heading's anchor, a position's by its id.
* **Where a link may go** (:func:`landscape_link`): to a heading on the same page, or, in the school
  view only, to a team's openCaselist page that
  :func:`~debate_core.domain.search_source_links.team_page_url` would build itself from the bundle's
  own caselist and the school and team code in the link's path (policy 1.14). Anything else is text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from typing import Final

from debate_core.domain.caselist import CASELIST_SLUG_PATTERN
from debate_core.domain.landscape import POSITION_ID_PATTERN
from debate_core.domain.search_source_links import OPENCASELIST_ORIGIN, team_page_url

__all__ = [
    "LANDSCAPE_HOLD",
    "LANDSCAPE_PREFIX",
    "REPORT_FILE",
    "SCHOOL_VIEW_FILE",
    "Anchors",
    "BundleFile",
    "LandscapeLink",
    "LandscapePage",
    "bundle_file",
    "heading_anchor",
    "is_position_id",
    "landscape_link",
]

LANDSCAPE_HOLD: Final = timedelta(minutes=5)
"""The longest a function holds a bundle before reading the bucket again (gate item 11)."""

LANDSCAPE_PREFIX: Final = "reports/landscape/"
"""Where the bundles are, as `debate_core.application.landscape_bundle_files.REPORTS_PREFIX` says."""

REPORT_FILE: Final = "report.md"
SCHOOL_VIEW_FILE: Final = "schools.md"

_CASELIST: Final = re.compile(CASELIST_SLUG_PATTERN)
_POSITION_ID: Final = re.compile(POSITION_ID_PATTERN)
_SNAPSHOT: Final = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_NOT_IN_ANCHOR: Final = re.compile(r"[^\w\- ]")
_FRAGMENT: Final = re.compile(r"^#([\w-]+)$")
_TEAM_PAGE_PREFIX: Final = f"{OPENCASELIST_ORIGIN}/"
_UNNAMED_ANCHOR: Final = "section"


class LandscapePage(StrEnum):
    """Which landscape page a member opened: all an audit record says of where they were."""

    CASELISTS = "caselists"
    REPORT = "report"
    SCHOOL_VIEW = "school-view"
    SCHOOL = "school"
    POSITION = "position"


@dataclass(frozen=True, slots=True)
class BundleFile:
    """One file of a published bundle, read from its key."""

    caselist: str
    snapshot: date
    name: str


def bundle_file(key: str) -> BundleFile | None:
    """`reports/landscape/<caselist>/<snapshot>/<file>` read apart, or `None` for any other key."""
    if not key.startswith(LANDSCAPE_PREFIX):
        return None
    parts = key.removeprefix(LANDSCAPE_PREFIX).split("/")
    if len(parts) != 3:
        return None
    caselist, snapshot, name = parts
    if _CASELIST.match(caselist) is None or _SNAPSHOT.match(snapshot) is None or not name:
        return None
    try:
        return BundleFile(caselist=caselist, snapshot=date.fromisoformat(snapshot), name=name)
    except ValueError:
        return None


def heading_anchor(text: str) -> str:
    """A heading's anchor as GitHub writes it: lower case, punctuation dropped, spaces as hyphens."""
    return _NOT_IN_ANCHOR.sub("", text.strip().lower()).replace(" ", "-") or _UNNAMED_ANCHOR


class Anchors:
    """The anchors of one page: a heading's own, then `-2`, `-3` for each repeat (the PM's ruling)."""

    def __init__(self) -> None:
        self._taken: set[str] = set()

    def add(self, text: str) -> str:
        base = heading_anchor(text)
        anchor, repeat = base, 1
        while anchor in self._taken:
            repeat += 1
            anchor = f"{base}-{repeat}"
        self._taken.add(anchor)
        return anchor

    def __contains__(self, anchor: object) -> bool:
        return anchor in self._taken


def is_position_id(text: str) -> bool:
    """Whether `text` is a taxonomy position id, the only thing a position page is addressed by."""
    return _POSITION_ID.match(text) is not None


class LandscapeLink(StrEnum):
    """What a link in a bundle may be. Any other link is shown as its text."""

    SAME_PAGE = "same-page"
    """A heading on the page it is on."""
    TEAM_PAGE = "team-page"
    """A team's openCaselist page, in the school view, opened in a new tab with no opener or referrer."""


def landscape_link(href: str, *, caselist: str, anchors: Anchors, team_pages: bool) -> LandscapeLink | None:
    """What the link to `href` may be on a page of `caselist`'s bundle, or `None` to show it as text.

    A team page is allowed only where `team_pages` is (the school view), and only when the rule that
    builds one gives back exactly `href` from the bundle's own caselist and the link's school and team
    code: another caselist, another origin, a query, a fragment or an extra segment gives `None`.
    """
    fragment = _FRAGMENT.match(href)
    if fragment is not None:
        return LandscapeLink.SAME_PAGE if fragment.group(1) in anchors else None
    if not team_pages or not href.startswith(_TEAM_PAGE_PREFIX):
        return None
    parts = href.removeprefix(_TEAM_PAGE_PREFIX).split("/")
    if len(parts) != 3 or parts[0] != caselist:
        return None
    return LandscapeLink.TEAM_PAGE if team_page_url(caselist, parts[1], parts[2]) == href else None
