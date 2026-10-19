"""Canonical URLs: one spelling for one article, whichever link reached it (v1-e04-t01).

ArticleService (v1-e04-t05) dedupes Articles by canonical URL, so one article reached through a
tracking link, an AMP page, a link wrapper or a mixed-case host has to come out as one string.
`canonicalize_url` is a pure function of the URL's text. It fetches nothing, follows no redirect
and resolves no DOI: a destination is used only when it is literally inside the URL.

**Syntax rules** never change what a URL names (RFC 3986 §6.2.2 and §6.2.3):

1. Surrounding whitespace is ignored. The scheme must be http or https, in any case, and becomes
   lower case; anything else raises `InvalidUrlError`, as does a URL with no host.
2. The host becomes lower case, an internationalized host its ASCII form (UTS #46,
   nontransitional; see `public_suffix.ascii_hostname`), and a trailing dot is dropped. An IPv6
   literal keeps its brackets in its compressed form.
3. The scheme's default port (80 for http, 443 for https) is dropped; any other port is kept.
4. Percent-encoding: hex digits become upper case, encoded unreserved characters (letters,
   digits, `-._~`) are decoded, and characters that may not appear raw are encoded as UTF-8.
   Reserved characters keep whatever form they had, so an encoded slash stays encoded.
5. `.` and `..` segments are removed, and an empty path becomes `/`.
6. The fragment is dropped, and so are empty query pieces (`?&a=1&&`).

Two things that look like syntax are deliberately left alone. **http is not upgraded to https**
and **`www.` is neither added nor removed**: either can name a different server. And **a trailing
slash is never added or removed**: `/reports/` and `/reports` resolve relative links differently
(RFC 3986 §5.2.3), so a server may serve different documents at them. Where they are one page,
its rel=canonical says so and `apply_rel_canonical` accepts it.

**Link wrappers.** A URL that is a known wrapper (`LINK_WRAPPERS`: Google, Google News, Facebook,
Outlook Safe Links, LinkedIn) or AMP cache (`AMP_CACHES`) whose destination is literally in it is
replaced by that destination, which is then canonicalized in turn, so nested wrappers unwind (at
most `MAX_LINK_WRAPPERS` deep; more raises `InvalidUrlError`). A wrapper whose destination is
encoded rather than literal, such as Google News `/articles/CBMi...` ids or `t.co` links, is kept
as it is. Decoding one would mean guessing at a format or following the link, and neither belongs
here.

**Content rules** can drop only what does not select content:

7. Parameters on the tracking deny list are removed (`query_parameters`). A parameter on no list
   is kept.
8. AMP variants become the article they render. In the query, `?amp`, `?amp=1` and
   `?outputType=amp`. In the path, an `amp` segment anywhere (`/amp/news/x`, `/news/amp/x`,
   `/x/amp/`), a `.amp` suffix on the last segment and `.amp.html` → `.html`. In the host, a
   leading `amp` label outside the registrable domain: `amp.theguardian.com` →
   `www.theguardian.com`, and `amp.news.example.co.uk` → `news.example.co.uk`. `amp.dev` keeps its
   name, because there the label *is* the registrable domain.
9. The remaining parameters are sorted by name. The sort is stable, so a repeated name keeps its
   values in their original order, since that order can matter.

The content rules repeat until nothing changes, so the result is a fixed point:
`canonicalize_url(canonicalize_url(u)) == canonicalize_url(u)`.
"""

from __future__ import annotations

import dataclasses
import ipaddress
import re
import string
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import unquote, urljoin, urlsplit

import idna

from debate_core.retrieval.public_suffix import ascii_hostname, registrable_domain
from debate_core.retrieval.query_parameters import is_amp_marker, is_tracking_parameter

__all__ = [
    "AMP_CACHES",
    "LINK_WRAPPERS",
    "MAX_LINK_WRAPPERS",
    "AmpCache",
    "InvalidUrlError",
    "LinkWrapper",
    "RelCanonicalDecision",
    "RelCanonicalRule",
    "apply_rel_canonical",
    "canonicalize_url",
]


class InvalidUrlError(ValueError):
    """The input is not an absolute http(s) URL with a usable host, so it has no canonical form."""


# ---------------------------------------------------------------------------------------------
# Link wrappers and AMP caches whose destination is literally in the URL
# ---------------------------------------------------------------------------------------------

_GOOGLE_HOSTS = r"(?:www\.)?google\.(?:com|[a-z]{2}|com?\.[a-z]{2})"


@dataclass(frozen=True, slots=True)
class LinkWrapper:
    """A redirecting link whose destination is one of its query parameters, unencrypted.

    `host` and `path` must match the whole normalized host and path. `parameters` are tried in
    order; the first whose decoded value is an absolute http(s) URL is the destination.
    """

    name: str
    host: re.Pattern[str]
    path: re.Pattern[str]
    parameters: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AmpCache:
    """An AMP cache or viewer URL, which spells its origin out in its path.

    `/c/s/www.example.com/x` is `https://www.example.com/x`: the `s/` means https, its absence
    http. The cache URL's own query is the origin's query.
    """

    name: str
    host: re.Pattern[str]
    path: re.Pattern[str]


LINK_WRAPPERS: tuple[LinkWrapper, ...] = (
    LinkWrapper(
        "Google search, Docs and Gmail redirect", re.compile(_GOOGLE_HOSTS), re.compile(r"/url"), ("q", "url")
    ),
    LinkWrapper(
        "Google News legacy redirect",
        re.compile(r"news\.google\.com"),
        re.compile(r"/(?:news/)?url"),
        ("url",),
    ),
    LinkWrapper(
        "Facebook outbound link",
        re.compile(r"(?:l|lm)\.facebook\.com|l\.messenger\.com"),
        re.compile(r"/l\.php"),
        ("u",),
    ),
    LinkWrapper(
        "Microsoft Outlook Safe Links",
        re.compile(r"[a-z0-9-]+\.safelinks\.protection\.outlook\.com"),
        re.compile(r"/"),
        ("url",),
    ),
    LinkWrapper(
        "LinkedIn outbound link", re.compile(r"www\.linkedin\.com"), re.compile(r"/redir/redirect"), ("url",)
    ),
)

_AMP_ORIGIN_PATH = r"(?P<secure>s/)?(?P<location>[^/]+(?:/.*)?)"

AMP_CACHES: tuple[AmpCache, ...] = (
    AmpCache(
        "Google AMP Cache",
        re.compile(r"[a-z0-9-]+\.cdn\.ampproject\.org"),
        re.compile(r"/[cv]/" + _AMP_ORIGIN_PATH),
    ),
    AmpCache("Google AMP viewer", re.compile(_GOOGLE_HOSTS), re.compile(r"/amp/" + _AMP_ORIGIN_PATH)),
)

MAX_LINK_WRAPPERS = 8
"""Nesting deeper than this is refused rather than unwound: real chains are one or two deep."""

# ---------------------------------------------------------------------------------------------
# Parsing and the syntax rules
# ---------------------------------------------------------------------------------------------

_DEFAULT_PORTS = {"http": 80, "https": 443}
_HEX_DIGITS = frozenset(string.hexdigits)
_UNRESERVED = frozenset(string.ascii_letters + string.digits + "-._~")
_SUB_DELIMITERS = frozenset("!$&'()*+,;=")
_USERINFO_SAFE = _UNRESERVED | _SUB_DELIMITERS | {":"}
_PATH_SAFE = _USERINFO_SAFE | {"@", "/"}
_QUERY_SAFE = _PATH_SAFE | {"?"}
_HOST_NAME = re.compile(r"[a-z0-9_-]+(?:\.[a-z0-9_-]+)*")

_QueryPair = tuple[str, str | None]


@dataclass(frozen=True, slots=True)
class _Url:
    """A URL after the syntax rules: every field is already in its normalized form."""

    scheme: str
    userinfo: str | None
    host: str
    port: int | None
    path: str
    query: tuple[_QueryPair, ...]

    def render(self) -> str:
        userinfo = "" if self.userinfo is None else f"{self.userinfo}@"
        port = "" if self.port is None else f":{self.port}"
        query = "&".join(name if value is None else f"{name}={value}" for name, value in self.query)
        return f"{self.scheme}://{userinfo}{self.host}{port}{self.path}" + (f"?{query}" if query else "")


def _normalize_percent_encoding(text: str, safe: frozenset[str], original: str) -> str:
    """Rule 4: upper-case hex, decode unreserved characters, encode what may not appear raw."""
    output: list[str] = []
    index = 0
    while index < len(text):
        character = text[index]
        triplet = text[index + 1 : index + 3]
        if character == "%" and len(triplet) == 2 and set(triplet) <= _HEX_DIGITS:
            decoded = chr(int(triplet, 16))
            output.append(decoded if decoded in _UNRESERVED else f"%{triplet.upper()}")
            index += 3
            continue
        if character in safe:
            output.append(character)
        else:
            try:
                encoded = character.encode("utf-8")
            except UnicodeEncodeError as error:
                raise InvalidUrlError(f"URL contains a character with no UTF-8 form: {original!r}") from error
            output.extend(f"%{byte:02X}" for byte in encoded)
        index += 1
    return "".join(output)


def _remove_dot_segments(path: str) -> str:
    """Rule 5, RFC 3986 §5.2.4 for an absolute path."""
    segments = path.split("/")
    kept: list[str] = []
    for segment in segments:
        if segment == "..":
            if len(kept) > 1:
                kept.pop()
        elif segment != ".":
            kept.append(segment)
    if segments[-1] in (".", ".."):
        kept.append("")
    return "/".join(kept)


def _normalize_host_name(name: str, original: str) -> str:
    """Rule 2 for a registered name or IPv4 address."""
    try:
        host = ascii_hostname(unquote(name))
    except (idna.IDNAError, UnicodeError) as error:
        raise InvalidUrlError(f"URL host cannot be encoded: {original!r}") from error
    if not _HOST_NAME.fullmatch(host):
        raise InvalidUrlError(f"URL has no usable host: {original!r}")
    return host


def _split_host_and_port(host_and_port: str, original: str) -> tuple[str, str]:
    """Separate the host from the port text, normalizing the host (rule 2)."""
    if host_and_port.startswith("["):
        literal, bracket, rest = host_and_port[1:].partition("]")
        if not bracket or (rest and not rest.startswith(":")):
            raise InvalidUrlError(f"URL has a malformed IPv6 host: {original!r}")
        try:
            address = ipaddress.IPv6Address(literal)
        except ValueError as error:
            raise InvalidUrlError(f"URL has a malformed IPv6 host: {original!r}") from error
        return f"[{address.compressed}]", rest.removeprefix(":")
    name, _, port = host_and_port.partition(":")
    return _normalize_host_name(name, original), port


def _parse_port(text: str, scheme: str, original: str) -> int | None:
    """Rule 3: no port, or the scheme's default, is None; anything else must be a valid port."""
    if not text:
        return None
    if not (text.isascii() and text.isdigit()) or int(text) > 65535:
        raise InvalidUrlError(f"URL has an invalid port: {original!r}")
    port = int(text)
    return None if port == _DEFAULT_PORTS[scheme] else port


def _parse_query(query: str) -> tuple[_QueryPair, ...]:
    pairs: list[_QueryPair] = []
    for piece in query.split("&"):
        if not piece:
            continue
        name, equals, value = piece.partition("=")
        normalized_value = _normalize_percent_encoding(value, _QUERY_SAFE, query) if equals else None
        pairs.append((_normalize_percent_encoding(name, _QUERY_SAFE, query), normalized_value))
    return tuple(pairs)


def _parse(url: str) -> _Url:
    """Apply the syntax rules, 1 to 6."""
    text = url.strip()
    try:
        parts = urlsplit(text)
    except ValueError as error:
        raise InvalidUrlError(f"not a URL: {url!r}") from error
    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS:
        raise InvalidUrlError(f"URL must be absolute http or https: {url!r}")
    if not parts.netloc:
        raise InvalidUrlError(f"URL has no host: {url!r}")
    userinfo, at, host_and_port = parts.netloc.rpartition("@")
    host, port_text = _split_host_and_port(host_and_port, url)
    path = _remove_dot_segments(_normalize_percent_encoding(parts.path, _PATH_SAFE, url)) or "/"
    return _Url(
        scheme=scheme,
        userinfo=_normalize_percent_encoding(userinfo, _USERINFO_SAFE, url) if at else None,
        host=host,
        port=_parse_port(port_text, scheme, url),
        path=path,
        query=_parse_query(parts.query),
    )


# ---------------------------------------------------------------------------------------------
# Unwrapping
# ---------------------------------------------------------------------------------------------


def _is_web_url(candidate: str) -> bool:
    """True for an absolute http(s) URL whose host could be on the public web."""
    try:
        host = _parse(candidate).host
    except InvalidUrlError:
        return False
    return "." in host or host.startswith("[")


def _amp_cache_origin(url: _Url) -> str | None:
    """The origin URL an AMP cache or viewer URL spells out, if it is one."""
    for cache in AMP_CACHES:
        match = cache.path.fullmatch(url.path) if cache.host.fullmatch(url.host) else None
        if match is None:
            continue
        query = _Url("http", None, "x", None, "/", url.query).render().removeprefix("http://x/")
        scheme = "https" if match["secure"] else "http"
        candidate = f"{scheme}://{match['location']}{query}"
        if _is_web_url(candidate):
            return candidate
    return None


def _wrapped_destination(url: _Url) -> str | None:
    """The destination a link wrapper or AMP cache URL carries literally, if it is one."""
    for wrapper in LINK_WRAPPERS:
        if not (wrapper.host.fullmatch(url.host) and wrapper.path.fullmatch(url.path)):
            continue
        for parameter in wrapper.parameters:
            for name, value in url.query:
                if value and unquote(name) == parameter and _is_web_url(unquote(value)):
                    return unquote(value)
    return _amp_cache_origin(url)


# ---------------------------------------------------------------------------------------------
# The content rules
# ---------------------------------------------------------------------------------------------


def _without_amp_host_label(host: str) -> str:
    labels = host.split(".")
    if labels[0] != "amp":
        return host
    site = registrable_domain(host)
    if site is None or site == host:
        return host
    rest = ".".join(labels[1:])
    return f"www.{site}" if rest == site else rest


_AMP_SUFFIXES = ((".amp.html", ".html"), (".amp.htm", ".htm"), (".amp", ""))


def _without_amp_suffix(segment: str) -> str:
    lowered = segment.lower()
    for suffix, replacement in _AMP_SUFFIXES:
        if lowered.endswith(suffix):
            stripped = segment[: -len(suffix)] + replacement
            # `.amp` alone, or `..amp`, would become an empty or dot segment and change the path.
            return segment if stripped in ("", ".", "..") else stripped
    return segment


def _without_amp_path(path: str) -> str:
    segments = [segment for segment in path.split("/") if segment.lower() != "amp"]
    segments[-1] = _without_amp_suffix(segments[-1])
    return "/".join(segments) or "/"


def _apply_content_rules_once(url: _Url) -> _Url:
    kept = [
        (name, value)
        for name, value in url.query
        if not is_tracking_parameter(name) and not is_amp_marker(name, value)
    ]
    return dataclasses.replace(
        url,
        host=_without_amp_host_label(url.host),
        path=_without_amp_path(url.path),
        query=tuple(sorted(kept, key=lambda pair: pair[0])),
    )


def _apply_content_rules(url: _Url) -> _Url:
    """Rules 7 to 9, repeated until they change nothing (`amp.amp.` hosts, `x.amp.amp` paths)."""
    while (updated := _apply_content_rules_once(url)) != url:
        url = updated
    return url


def canonicalize_url(url: str) -> str:
    """The canonical form of an absolute http(s) URL, by the rules in this module's docstring.

    Raises `InvalidUrlError` (a `ValueError`) for anything that is not an absolute http(s) URL
    with a usable host, and for link wrappers nested more than `MAX_LINK_WRAPPERS` deep.
    """
    candidate = url
    for _ in range(MAX_LINK_WRAPPERS + 1):
        parsed = _parse(candidate)
        destination = _wrapped_destination(parsed)
        if destination is None:
            canonical = _apply_content_rules(parsed)
            # The content rules can turn a URL into a wrapper (`amp.google.com/url?q=...`).
            destination = _wrapped_destination(canonical)
            if destination is None:
                return canonical.render()
        candidate = destination
    raise InvalidUrlError(f"URL nests more than {MAX_LINK_WRAPPERS} link wrappers: {url!r}")


# ---------------------------------------------------------------------------------------------
# rel=canonical
# ---------------------------------------------------------------------------------------------


class RelCanonicalRule(StrEnum):
    """Which rule decided what to do with a page's rel=canonical.

    The values are stable strings for a later task to store beside the Article (v1-e04-t05); a
    new rule is a new member, and an existing value never changes meaning.
    """

    ABSENT = "absent"
    """The page declares no rel=canonical, or an empty one; the fetched URL stands."""

    UNUSABLE = "unusable"
    """The declared canonical is not an absolute http(s) URL even after resolving it against the
    fetched URL (`javascript:`, `mailto:`, a malformed host); the fetched URL stands."""

    SAME_SITE = "same_site"
    """The declared canonical has the fetched URL's registrable domain, so the site is speaking for
    itself; accepted."""

    AMP_CACHE_ORIGIN = "amp_cache_origin"
    """The page was fetched from an AMP cache or viewer (`AMP_CACHES`) and the declared canonical
    has the registrable domain of the origin the cache URL names; accepted. This is the one
    cross-site allow rule."""

    CROSS_SITE_REFUSED = "cross_site_refused"
    """The declared canonical is on another site and no allow rule covers it (a syndication
    partner, a mirror, a wrapper's own page); refused, and the fetched URL stands."""


_ACCEPTING_RULES = frozenset({RelCanonicalRule.SAME_SITE, RelCanonicalRule.AMP_CACHE_ORIGIN})


@dataclass(frozen=True, slots=True)
class RelCanonicalDecision:
    """The URL to keep for a fetched page, and the rule that chose it.

    `declared_url` is the page's rel=canonical resolved and canonicalized, kept even when refused
    so a log or a reviewer can see what the page claimed; None when it was absent or unusable.
    """

    canonical_url: str
    rule: RelCanonicalRule
    declared_url: str | None

    @property
    def accepted(self) -> bool:
        """True if the page's own rel=canonical became the canonical URL."""
        return self.rule in _ACCEPTING_RULES


def _site(host: str) -> str:
    """The registrable domain, or the host itself where there is none (an IP address)."""
    return registrable_domain(host) or host


def _resolve_reference(base: str, reference: str) -> str:
    """RFC 3986 §5.2.2: a reference with a scheme is absolute and is used as it is.

    `urljoin` follows the older RFC 1808 here and treats `https://` or `https:x`, on a base of the
    same scheme, as relative, which would turn a declared `https://` into the fetched URL itself.
    """
    if urlsplit(reference).scheme:
        return reference
    return urljoin(base, reference)


def apply_rel_canonical(fetched_url: str, html_canonical: str | None) -> RelCanonicalDecision:
    """Decide between the URL a page was fetched from and the rel=canonical it declares.

    `fetched_url` is the URL the bytes came from, after redirects (v1-e04-t02's final URL), and
    `html_canonical` the href of the page's `<link rel="canonical">` as written, possibly relative.
    A same-site canonical is accepted; a cross-site one only under an allow rule
    (`RelCanonicalRule.AMP_CACHE_ORIGIN`). "Site" is the registrable domain of the host that served
    the page, before any AMP or wrapper rule, because it is that host's HTML making the claim.

    Raises `InvalidUrlError` if `fetched_url` itself has no canonical form.
    """
    fetched = _parse(fetched_url)
    fetched_canonical = canonicalize_url(fetched_url)
    if html_canonical is None or not html_canonical.strip():
        return RelCanonicalDecision(fetched_canonical, RelCanonicalRule.ABSENT, None)
    try:
        declared = canonicalize_url(_resolve_reference(fetched_url.strip(), html_canonical.strip()))
    except ValueError:
        return RelCanonicalDecision(fetched_canonical, RelCanonicalRule.UNUSABLE, None)
    declared_site = _site(_parse(declared).host)
    if _site(fetched.host) == declared_site:
        return RelCanonicalDecision(declared, RelCanonicalRule.SAME_SITE, declared)
    origin = _amp_cache_origin(fetched)
    if origin is not None and _site(_parse(origin).host) == declared_site:
        return RelCanonicalDecision(declared, RelCanonicalRule.AMP_CACHE_ORIGIN, declared)
    return RelCanonicalDecision(fetched_canonical, RelCanonicalRule.CROSS_SITE_REFUSED, declared)
