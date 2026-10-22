"""Whether a site's robots.txt lets this crawler fetch a URL (v1-e04-t02).

The fetcher (`debate_core.integrations.http_fetcher`) requests robots.txt through its own client,
with its own User-Agent, timeouts and per-host spacing, and hands the answer here. Nothing in this
module touches the network: :meth:`RobotsRules.from_response` takes a status and the bytes, and
`urllib.robotparser` is only ever given text (`parse`), never a URL to read itself.

## What a robots.txt answer means

| robots.txt answered | Reading |
|---|---|
| 2xx | its rules |
| 401, 403 | refuse everything (`ROBOTS_ACCESS_DENIED`), as `urllib.robotparser.read()` does |
| 404, 410, any other 4xx but 429 | allow everything: no rules were published (RFC 9309 §2.3.1.3) |
| 429, 5xx, timeout, failed connection, redirect loop | refuse everything (`ROBOTS_UNREACHABLE`) |

The last row is RFC 9309 §2.3.1.4's "assume complete disallow", the conservative reading of an
outage, and it is deliberate. A site whose robots.txt is down for an hour loses this crawler for
that hour, which costs a research tool nothing it cannot recover with a retry later; fetching
through an outage could fetch a page the site disallows. The fetcher retries robots.txt on the
same terms as any request before settling on this row.

## Two readings, and a URL needs both

`urllib.robotparser` is the reference reading, as the spec asks. It predates RFC 9309, and differs
from it in two ways that both make it *more permissive* than the site meant:

* It applies the first rule whose path is a prefix of the URL, in file order. RFC 9309 §2.2.2
  applies the longest. Under `Allow: /` followed by `Disallow: /private`, the stdlib allows
  `/private/x`; the RFC does not.
* It does not know the `*` and `$` wildcards (§2.2.3), so `Disallow: /*.pdf$` matches nothing.

So a URL is fetched only when the stdlib allows it **and** an RFC 9309 longest-match reading of the
same text allows it (:func:`_rfc9309_allows`). The second reading can only add refusals; it never
lets through anything the stdlib refuses. The price is the mirror case: an allow-list written
disallow-first (`Disallow: /`, then `Allow: /public/`) refuses `/public/a` too, because the stdlib
stops at the first rule. A refused article can still be pasted in by its reader, so the platform
pays that price rather than risk fetching a disallowed one.

The stdlib also matches a group's `User-agent` as a substring of the product token, where the RFC
matches the whole token; requiring both means a group naming either way applies.

`Crawl-delay` is not read. The per-host interval comes from settings (`http.per_host_interval_seconds`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final
from urllib.parse import quote, unquote, urlsplit
from urllib.robotparser import RobotFileParser

from debate_core.retrieval.fetch_types import RobotsRefusalReason

__all__ = ["ROBOTS_MAX_BYTES", "RobotsRules"]

ROBOTS_MAX_BYTES: Final = 500 * 1024
"""How much of a robots.txt is read. RFC 9309 §2.5 asks crawlers to parse at least 500 KiB and lets
them ignore the rest; a longer file is cut at its last complete line."""

_SAFE_IN_PATHS: Final = "/?=&;:@!$,'()*+~-._%"
"""Characters left as they are when a path or pattern is put in one percent-encoded form."""


@dataclass(frozen=True, slots=True)
class RobotsRules:
    """One origin's robots.txt, read: either its rules, or a blanket answer."""

    refusal: RobotsRefusalReason | None = None
    """Set when every URL is refused: robots.txt was unreachable or access to it was denied."""
    text: str = ""
    """The rules' text; empty with a refusal, or when no rules were published."""
    _stdlib: RobotFileParser = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        parser = RobotFileParser()
        parser.parse(self.text.splitlines())
        object.__setattr__(self, "_stdlib", parser)

    @classmethod
    def from_response(cls, status_code: int, body: bytes) -> RobotsRules:
        """The rules a robots.txt response sets, by the table in the module docstring.

        `status_code` is the final status after any redirects. A 3xx here means the redirects ran
        out, and is read as unreachable.
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

    def refusal_for(self, url: str, *, user_agent: str, product_token: str) -> RobotsRefusalReason | None:
        """Why `url` may not be fetched, or `None` when it may.

        `user_agent` is the whole header, which the stdlib takes; `product_token` is its first
        word (`debate-research`), which RFC 9309 groups are matched against.
        """
        if self.refusal is not None:
            return self.refusal
        if not self._stdlib.can_fetch(user_agent, url):
            return RobotsRefusalReason.DISALLOWED
        if not _rfc9309_allows(self.text, url, product_token):
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


def _rfc9309_allows(text: str, url: str, product_token: str) -> bool:
    """RFC 9309's reading: the matching groups' longest matching rule decides; a tie allows."""
    groups = _groups(text)
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
