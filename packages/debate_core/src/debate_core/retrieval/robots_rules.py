"""Whether a site's robots.txt lets this crawler fetch a URL (v1-e04-t02).

The fetcher (`debate_core.integrations.http_fetcher`) requests robots.txt through its own client,
with its own User-Agent, timeouts and per-host spacing, and hands the answer here. Nothing in this
module touches the network: :meth:`RobotsRules.from_response` takes a status and the bytes.

## What a robots.txt answer means

| robots.txt answered | Reading |
|---|---|
| 2xx | its rules, read by RFC 9309 |
| 401, 403 | refuse everything (`ROBOTS_ACCESS_DENIED`); stricter than the RFC, on purpose |
| 404, 410, any other 4xx but 429 | allow everything: no rules were published (RFC 9309 §2.3.1.3) |
| 429, 5xx, timeout, failed connection, redirect loop | refuse everything (`ROBOTS_UNREACHABLE`) |

**401 and 403 are deliberately stricter than RFC 9309**, which counts them with the other 4xx as
"unavailable" and lets a crawler in. A site that answers its robots.txt with "you may not see this"
is read here as not wanting this crawler at all, as `urllib.robotparser.read()` reads it. The cost is
a site that protects everything by mistake; the platform accepts it (PM ruling 2026-10-21).

The last row is RFC 9309 §2.3.1.4's "assume complete disallow", the conservative reading of an
outage, and it is deliberate. A site whose robots.txt is down for an hour loses this crawler for
that hour, which costs a research tool nothing it cannot recover with a retry later; fetching
through an outage could fetch a page the site disallows. The fetcher retries robots.txt on the
same terms as any request before settling on this row.

## RFC 9309 alone decides

The rules are read as RFC 9309 §2.2 sets out, and nothing else has a say (PM ruling 2026-10-21):

* The group whose `User-agent` is the product token, matched whole and without regard to case, and
  every such group merged; failing that, the `*` groups; failing that, no rules at all.
* Of that group's rules, the one with the longest pattern matching the URL's path and query
  decides. Between an `Allow` and a `Disallow` of equal length, `Allow` wins. No match allows.
* `*` matches any run of characters and a final `$` anchors the end. Paths and patterns are
  compared in one percent-encoded form, so `/café` and `/caf%C3%A9` are one path.

`urllib.robotparser` is not used. It applies the first matching rule in file order rather than the
longest, does not know `*` or `$`, and matches a `User-agent` as a substring of the token, so it is
wrong in both directions: under `Allow: /` then `Disallow: /private` it allows `/private/x`, and
under the common allow-list `Disallow: /` then `Allow: /public/` it refuses `/public/a`.

## How long an answer lasts

RFC 9309 §2.4: a crawler should not use a cached robots.txt for more than 24 hours. The fetcher
keeps each origin's rules with the time it read them, from its injected clock, and reads robots.txt
again once :func:`robots_rules_expired` says they are :data:`ROBOTS_MAX_AGE` old.

`Crawl-delay` is not read. The per-host interval comes from settings (`http.per_host_interval_seconds`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Final
from urllib.parse import quote, unquote, urlsplit

from debate_core.retrieval.fetch_types import RobotsRefusalReason

__all__ = ["ROBOTS_MAX_AGE", "ROBOTS_MAX_BYTES", "RobotsRules", "robots_rules_expired"]

ROBOTS_MAX_BYTES: Final = 500 * 1024
"""How much of a robots.txt is read. RFC 9309 §2.5 asks crawlers to parse at least 500 KiB and lets
them ignore the rest; a longer file is cut at its last complete line."""

ROBOTS_MAX_AGE: Final = timedelta(hours=24)
"""How long one reading of an origin's robots.txt is used before it is read again (RFC 9309 §2.4)."""

_SAFE_IN_PATHS: Final = "/?=&;:@!$,'()*+~-._%"
"""Characters left as they are when a path or pattern is put in one percent-encoded form."""


def robots_rules_expired(read_at: datetime, *, now: datetime) -> bool:
    """Whether rules read at `read_at` are too old to use at `now`."""
    return now - read_at >= ROBOTS_MAX_AGE


@dataclass(frozen=True, slots=True)
class RobotsRules:
    """One origin's robots.txt, read: either its rules, or a blanket answer."""

    refusal: RobotsRefusalReason | None = None
    """Set when every URL is refused: robots.txt was unreachable or access to it was denied."""
    text: str = ""
    """The rules' text; empty with a refusal, or when no rules were published."""
    _groups: tuple[_Group, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_groups", tuple(_groups(self.text)))

    @classmethod
    def from_response(cls, status_code: int, body: bytes) -> RobotsRules:
        """The rules a robots.txt response sets, by the table in the module docstring.

        `status_code` is the final status after any redirects. A 3xx here means the redirects ran
        out, and is read as unreachable. 401 and 403 refuse everything, which is stricter than
        RFC 9309 on purpose (see the module docstring).
        """
        if 200 <= status_code < 300:
            return cls(text=_decode(body))
        if status_code in (401, 403):
            return cls(refusal=RobotsRefusalReason.ROBOTS_ACCESS_DENIED)
        if 400 <= status_code < 500 and status_code != 429:
            return cls()
        return cls.unreachable()

    @classmethod
    def unreachable(cls) -> RobotsRules:
        """robots.txt could not be read, so nothing on the origin is fetched (RFC 9309 §2.3.1.4)."""
        return cls(refusal=RobotsRefusalReason.ROBOTS_UNREACHABLE)

    def refusal_for(self, url: str, *, product_token: str) -> RobotsRefusalReason | None:
        """Why `url` may not be fetched, or `None` when it may.

        `product_token` is the User-Agent's first word (`debate-research`), which groups are
        matched against.
        """
        if self.refusal is not None:
            return self.refusal
        if not _rfc9309_allows(self._groups, url, product_token):
            return RobotsRefusalReason.DISALLOWED
        return None


def _decode(body: bytes) -> str:
    """robots.txt is UTF-8 (RFC 9309 §2.3); bytes past :data:`ROBOTS_MAX_BYTES` are dropped."""
    if len(body) > ROBOTS_MAX_BYTES:
        cut = body[:ROBOTS_MAX_BYTES]
        body = cut[: cut.rfind(b"\n") + 1]
    return body.decode("utf-8", errors="replace")


@dataclass(slots=True)
class _Group:
    agents: list[str] = field(default_factory=list[str])
    rules: list[tuple[bool, str]] = field(default_factory=list[tuple[bool, str]])
    """(allow, pattern) pairs, in file order."""


def _rfc9309_allows(groups: tuple[_Group, ...], url: str, product_token: str) -> bool:
    """RFC 9309's reading: the matching groups' longest matching rule decides; a tie allows."""
    token = product_token.lower()
    chosen = [group for group in groups if token in group.agents]
    if not chosen:
        chosen = [group for group in groups if "*" in group.agents]
    parts = urlsplit(url)
    target = _normalise(parts.path or "/") + (f"?{_normalise(parts.query)}" if parts.query else "")
    best_length = -1
    allowed = True
    for group in chosen:
        for allow, pattern in group.rules:
            if not _matches(pattern, target):
                continue
            length = len(pattern)
            if length > best_length or (length == best_length and allow):
                best_length, allowed = length, allow
    return allowed


def _groups(text: str) -> list[_Group]:
    """The file's groups: consecutive `User-agent` lines, then the rules under them (§2.1)."""
    groups: list[_Group] = []
    current: _Group | None = None
    in_rules = False
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        key, separator, value = line.partition(":")
        if not separator:
            continue
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            if current is None or in_rules:
                current = _Group()
                groups.append(current)
                in_rules = False
            current.agents.append(value.lower())
        elif key in ("allow", "disallow") and current is not None:
            in_rules = True
            if value:
                current.rules.append((key == "allow", _normalise(value)))
    return groups


def _normalise(text: str) -> str:
    """One percent-encoded spelling, so `/caf%C3%A9` and `/café` compare equal (§2.2.2)."""
    return quote(unquote(text), safe=_SAFE_IN_PATHS)


def _matches(pattern: str, target: str) -> bool:
    """Whether `pattern` matches the start of `target`: `*` is any run, a final `$` the end (§2.2.3)."""
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    expression = ".*".join(re.escape(piece) for piece in body.split("*"))
    return re.match(expression + ("$" if anchored else ""), target) is not None
