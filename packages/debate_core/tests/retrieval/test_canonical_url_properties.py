"""Properties of canonicalize_url over generated URLs (`v1-e04-t01-url-canonicalization`, ac1 and ac2).

The generated inputs are valid URLs: an http(s) scheme in any case, a host (ASCII labels,
Unicode labels, ACE labels, the labels the AMP rule looks for, IP literals, a trailing dot), any
port, a path of RFC 3986 path characters and percent triplets, a query of the parameter names the
rules single out mixed with arbitrary ones, and a fragment. A share of them are wrapped once or
twice in the link wrappers and AMP caches the canonicalizer unwraps, so unwrapping is inside the
idempotence claim rather than beside it. `event()` labels show in `--hypothesis-show-statistics`
how often each feature was generated.

Example count comes from `URL_PROPERTY_EXAMPLES` (default 300), so a deep run is
`URL_PROPERTY_EXAMPLES=20000 uv run pytest -n 0 <this file>`.
"""

from __future__ import annotations

import os
import string
from urllib.parse import quote, unquote, urlsplit

from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st
from pydantic import TypeAdapter

from debate_core.domain.base import HttpUrlStr
from debate_core.retrieval.canonical_url import canonicalize_url
from debate_core.retrieval.query_parameters import (
    AMP_QUERY_MARKERS,
    CONTENT_PARAMETERS,
    TRACKING_PARAMETERS,
    is_tracking_parameter,
)

PROPERTY_SETTINGS = settings(
    max_examples=int(os.environ.get("URL_PROPERTY_EXAMPLES", "300")),
    deadline=None,  # the first call loads the public suffix list
    suppress_health_check=[HealthCheck.too_slow],
)

HTTP_URL: TypeAdapter[str] = TypeAdapter(HttpUrlStr)

# ---------------------------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------------------------

UNRESERVED = string.ascii_letters + string.digits + "-._~"
PATH_CHARACTERS = UNRESERVED + "!$&'()*+,;=:@"
QUERY_NAME_CHARACTERS = UNRESERVED + "!$'()*+,;:@/?"
QUERY_VALUE_CHARACTERS = QUERY_NAME_CHARACTERS + "="

percent_triplet = st.tuples(st.integers(0, 255), st.booleans()).map(
    lambda pair: f"%{pair[0]:02X}" if pair[1] else f"%{pair[0]:02x}"
)

ascii_label = st.text(alphabet=string.ascii_lowercase + string.digits, min_size=1, max_size=6)
special_label = st.sampled_from(
    ["amp", "AMP", "www", "WWW", "news", "bücher", "BÜCHER", "例え", "faß", "xn--bcher-kva", "Xn--Bcher-Kva"]
)
public_suffix = st.sampled_from(
    ["com", "org", "gov", "co.uk", "de", "jp", "dev", "github.io", "ck", "テスト", "example", "COM"]
)


@st.composite
def hosts(draw: st.DrawFn) -> str:
    if draw(st.integers(0, 9)) == 0:
        return draw(st.sampled_from(["192.0.2.10", "[2001:DB8::1]", "[::1]"]))
    labels = draw(st.lists(st.one_of(ascii_label, special_label), min_size=1, max_size=3))
    host = ".".join([*labels, draw(public_suffix)])
    if not host.isascii():
        event("unicode host")
    if labels[0].lower() == "amp":
        event("amp label first")
    return host + ("." if draw(st.integers(0, 9)) == 0 else "")


path_piece = st.one_of(
    st.text(alphabet=PATH_CHARACTERS, max_size=6),
    percent_triplet,
    st.sampled_from(
        [
            "amp",
            "AMP",
            ".amp",
            "x.amp",
            "x.amp.amp",
            "a.amp.html",
            "..amp",
            ".",
            "..",
            "café",
            "%2F",
            "%7e",
            "%2E",
            "%2e%2E",
        ]
    ),
)
path_segment = st.lists(path_piece, max_size=3).map("".join)

tracking_names = [rule.name + ("source" if rule.prefix else "") for rule in TRACKING_PARAMETERS]
special_names = st.sampled_from(
    [
        *tracking_names,
        *(marker.name for marker in AMP_QUERY_MARKERS),
        *(rule.name for rule in CONTENT_PARAMETERS),
        "UTM_Source",
        "utm%5Fmedium",
        "outputType",
        "AMP",
    ]
)
query_name = st.one_of(special_names, st.text(alphabet=QUERY_NAME_CHARACTERS, max_size=5), percent_triplet)
query_value = st.one_of(
    st.none(),
    st.text(alphabet=QUERY_VALUE_CHARACTERS, max_size=6),
    st.sampled_from(["", "1", "true", "amp", "AMP", "café"]),
    percent_triplet,
)


@st.composite
def plain_urls(draw: st.DrawFn) -> str:
    scheme = draw(st.sampled_from(["http", "https", "HTTP", "Https"]))
    host = draw(hosts())
    port = draw(st.sampled_from(["", "", ":80", ":443", ":8080", ":"]))
    segments = draw(st.lists(path_segment, max_size=4))
    path = "".join("/" + segment for segment in segments) + draw(st.sampled_from(["", "", "/"]))
    if any(segment.lower() in {"amp", ".", ".."} for segment in segments):
        event("amp or dot segment")
    url = f"{scheme}://{host}{port}{path}"
    pairs = draw(st.lists(st.tuples(query_name, query_value), max_size=5))
    if pairs or draw(st.booleans()):
        pieces = [name if value is None else f"{name}={value}" for name, value in pairs]
        if any(is_tracking_parameter(unquote(name)) for name, _ in pairs):
            event("tracking parameter")
        url += "?" + "&".join(pieces)
    if draw(st.booleans()):
        url += "#" + draw(st.text(alphabet=PATH_CHARACTERS + "/?", max_size=6))
    return url


def _amp_cache_form(url: str, *, google_viewer: bool) -> str:
    parts = urlsplit(url)
    secure = "s/" if parts.scheme.lower() == "https" else ""
    location = parts.netloc + parts.path + (f"?{parts.query}" if parts.query else "")
    if google_viewer:
        return f"https://www.google.com/amp/{secure}{location}"
    return f"https://www-example-com.cdn.ampproject.org/c/{secure}{location}"


@st.composite
def wrapped(draw: st.DrawFn, inner: str) -> str:
    form = draw(st.sampled_from(["google", "facebook", "safelinks", "amp cache", "google amp viewer"]))
    event(f"wrapped: {form}")
    if form == "google":
        return f"https://www.google.com/url?q={quote(inner, safe='')}&sa=D&usg=AOvVaw"
    if form == "facebook":
        return f"https://l.facebook.com/l.php?u={quote(inner, safe='')}&h=AT0"
    if form == "safelinks":
        return (
            f"https://nam12.safelinks.protection.outlook.com/?url={quote(inner, safe='')}&data=05&reserved=0"
        )
    return _amp_cache_form(inner, google_viewer=form == "google amp viewer")


urls = st.one_of(
    plain_urls(),
    plain_urls().flatmap(wrapped),
    plain_urls().flatmap(wrapped).flatmap(wrapped),
)

# ---------------------------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------------------------


@PROPERTY_SETTINGS
@given(urls)
def test_canonicalization_is_idempotent(url: str) -> None:
    """canonicalize_url(canonicalize_url(u)) == canonicalize_url(u), ac1's first half."""
    canonical = canonicalize_url(url)
    assert canonicalize_url(canonical) == canonical


@PROPERTY_SETTINGS
@given(urls)
def test_a_canonical_url_is_a_valid_domain_url(url: str) -> None:
    """Article.canonical_url accepts every output: absolute http(s), a host, no whitespace."""
    canonical = canonicalize_url(url)
    assert HTTP_URL.validate_python(canonical) == canonical
    assert "#" not in canonical


@PROPERTY_SETTINGS
@given(urls)
def test_no_tracking_parameter_survives(url: str) -> None:
    query = urlsplit(canonicalize_url(url)).query
    names = [piece.partition("=")[0] for piece in query.split("&") if piece]
    assert not [name for name in names if is_tracking_parameter(unquote(name))]


content_value = st.text(alphabet=UNRESERVED, min_size=1, max_size=8)


@PROPERTY_SETTINGS
@given(
    plain_urls(),
    st.sampled_from([rule.name for rule in CONTENT_PARAMETERS] or ["placeholder"]),
    content_value,
    st.integers(0, 5),
)
def test_a_content_parameter_survives_with_its_value(url: str, name: str, value: str, position: int) -> None:
    """ac2: an allow-listed parameter is kept, whatever tracking or AMP parameters surround it."""
    base, _, fragment = url.partition("#")
    address, _, query = base.partition("?")
    pieces = [piece for piece in query.split("&") if piece]
    pieces.insert(min(position, len(pieces)), f"{name}={value}")
    canonical = canonicalize_url(f"{address}?{'&'.join(pieces)}" + (f"#{fragment}" if fragment else ""))
    assert f"{name}={value}" in urlsplit(canonical).query.split("&")
