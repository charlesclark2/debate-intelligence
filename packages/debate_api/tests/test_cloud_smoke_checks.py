"""validate-dev's account-free pilot checks, run against the real app here, whole and broken (`v1-e39-t10`).

`tests/smoke/cloud` holds the checks validate-dev runs against dev, which no pull request can reach. So
here every one of them runs against this checkout's app, through Starlette's test client, behind a
stand-in for CloudFront that adds the Content-Security-Policy `distribution.tf` writes (read from
that file, as the browser suite reads it). They must pass against it, which also proves their
hand-written CSP is the one the distribution sends; and each must fail against an edge or an app
broken in the one way it is there to notice.

Nothing reaches a network: the checks' client has an `httpx.MockTransport` that hands each request to
the test client.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

import httpx
import pytest
from fastapi.testclient import TestClient
from tests.smoke.cloud import pilot_checks

REPOSITORY: Final = Path(__file__).resolve().parents[3]
DISTRIBUTION: Final = REPOSITORY / "infrastructure" / "modules" / "evidence_search" / "distribution.tf"
FAKE_DIGEST: Final = "abcdef0123456789"

Forward = Callable[[httpx.Request], httpx.Response]
Edge = Callable[[httpx.Request, Forward], httpx.Response]


def distribution_csp(login_origin: str) -> str:
    """The CSP CloudFront's response headers policy sends, as `distribution.tf` writes it."""
    listed = re.search(
        r'content_security_policy = join\("; ", \[(.*?)\]\)', DISTRIBUTION.read_text(), re.DOTALL
    )
    assert listed is not None, "distribution.tf no longer writes the CSP as join(...)"
    directives = re.findall(r'"([^"]+)"', listed.group(1))
    return "; ".join(directive.replace("${local.login_origin}", login_origin) for directive in directives)


def as_deployed(request: httpx.Request, forward: Forward) -> httpx.Response:
    return forward(request)


def checks_client(world: Any, edge: Edge = as_deployed) -> httpx.Client:
    """What the checks are given: a client of the pilot's origin, answered by the app behind the edge."""
    app = TestClient(world.app, base_url=world.public_origin, follow_redirects=False)
    csp = distribution_csp(world.login_origin)

    def through_cloudfront(request: httpx.Request) -> httpx.Response:
        answered = app.request(request.method, str(request.url), headers=request.headers)
        return httpx.Response(
            answered.status_code,
            headers=[*answered.headers.multi_items(), ("content-security-policy", csp)],
            content=answered.content,
        )

    def handle(request: httpx.Request) -> httpx.Response:
        return edge(request, through_cloudfront)

    return httpx.Client(
        transport=httpx.MockTransport(handle), base_url=world.public_origin + "/", follow_redirects=False
    )


@pytest.fixture
def world(auth_world: Any) -> Any:
    """Sign-in alone: these pages need no index (`v1-e39-t20`)."""
    return auth_world


CHECKS: Final = {
    "healthz": pilot_checks.check_health,
    "sign-in redirect": pilot_checks.check_pages_need_a_session,
    "hashed assets": pilot_checks.check_static_assets_are_content_hashed,
}


@pytest.mark.parametrize("name", CHECKS)
def test_every_check_passes_against_the_app_behind_the_distributions_csp(world: Any, name: str) -> None:
    with checks_client(world) as client:
        CHECKS[name](client)


def test_the_checks_hand_written_csp_is_the_distributions(world: Any) -> None:
    assert pilot_checks.expected_content_security_policy(httpx.URL(world.public_origin)) == distribution_csp(
        world.login_origin
    )


def test_the_checks_send_eight_gets_with_no_cookie_no_credential_and_no_body(world: Any) -> None:
    """ac4: nothing to sign in with, and nothing that changes anything on dev."""
    sent: list[httpx.Request] = []

    def recording(request: httpx.Request, forward: Forward) -> httpx.Response:
        sent.append(request)
        return forward(request)

    with checks_client(world, recording) as client:
        for check in CHECKS.values():
            check(client)

    assert [request.method for request in sent] == ["GET"] * 8
    for request in sent:
        assert request.content == b""
        assert {"cookie", "authorization", "x-csrf-token"}.isdisjoint(request.headers), request.headers


# ------------------------------------------------------------------------------------------------
# Each check fails against the breakage it is there for
# ------------------------------------------------------------------------------------------------


def with_headers(response: httpx.Response, **changes: str | None) -> httpx.Response:
    headers = [(k, v) for k, v in response.headers.multi_items() if k.replace("-", "_") not in changes]
    headers += [(name.replace("_", "-"), value) for name, value in changes.items() if value is not None]
    return httpx.Response(response.status_code, headers=headers, content=response.content)


def no_csp_on_redirects(request: httpx.Request, forward: Forward) -> httpx.Response:
    response = forward(request)
    return with_headers(response, content_security_policy=None) if response.status_code == 302 else response


def another_login_host_in_the_csp(request: httpx.Request, forward: Forward) -> httpx.Response:
    return with_headers(
        forward(request),
        content_security_policy=distribution_csp("https://auth.tub.elsewhere.test"),
    )


def health_failing(request: httpx.Request, forward: Forward) -> httpx.Response:
    response = forward(request)
    if request.url.path == "/healthz":
        csp = response.headers["content-security-policy"]
        return httpx.Response(503, json={"status": "starting"}, headers={"content-security-policy": csp})
    return response


def health_cached(request: httpx.Request, forward: Forward) -> httpx.Response:
    response = forward(request)
    return with_headers(response, cache_control="max-age=60") if request.url.path == "/healthz" else response


def search_open_without_a_session(request: httpx.Request, forward: Forward) -> httpx.Response:
    response = forward(request)
    if request.url.path == "/search":
        csp = response.headers["content-security-policy"]
        return httpx.Response(200, headers={"content-security-policy": csp}, text="<h1>Results</h1>")
    return response


def sign_in_on_another_host(request: httpx.Request, forward: Forward) -> httpx.Response:
    response = forward(request)
    if response.status_code == 302:
        location = response.headers["location"].replace("://auth.", "://login.", 1)
        return with_headers(response, location=location)
    return response


def callback_elsewhere(request: httpx.Request, forward: Forward) -> httpx.Response:
    response = forward(request)
    if response.status_code == 302:
        location = response.headers["location"].replace("%2Fauth%2Fcallback", "%2Fcallback", 1)
        return with_headers(response, location=location)
    return response


def assets_cached_privately(request: httpx.Request, forward: Forward) -> httpx.Response:
    response = forward(request)
    if request.url.path.startswith("/static/"):
        return with_headers(response, cache_control="private, no-store")
    return response


def assets_at_a_digest_that_is_not_theirs(request: httpx.Request, forward: Forward) -> httpx.Response:
    """An app that links and serves its files at a fixed path: cacheable for a year, never renamed."""
    if request.url.path.startswith(f"/static/{FAKE_DIGEST}/"):
        page = forward(httpx.Request("GET", request.url.copy_with(path="/signed-out")))
        name = request.url.path.rsplit("/", 1)[1]
        [real] = [
            one for one in re.findall(r'"(/static/[0-9a-f]{16}/[^"]+)"', page.text) if one.endswith(name)
        ]
        return forward(httpx.Request("GET", request.url.copy_with(path=real)))
    response = forward(request)
    if request.url.path == "/signed-out":
        text = re.sub(r"/static/[0-9a-f]{16}/", f"/static/{FAKE_DIGEST}/", response.text)
        return httpx.Response(response.status_code, headers=response.headers, content=text.encode())
    return response


def every_digest_served(request: httpx.Request, forward: Forward) -> httpx.Response:
    """A static route that ignores the digest: a stale link would be cached for a year as today's file."""
    if request.url.path == f"/static/{'0' * 16}/app.js":
        page = forward(httpx.Request("GET", request.url.copy_with(path="/signed-out")))
        [real] = re.findall(r'"(/static/[0-9a-f]{16}/app\.js)"', page.text)
        return forward(httpx.Request("GET", request.url.copy_with(path=real)))
    return forward(request)


@pytest.mark.parametrize(
    ("edge", "name", "says"),
    [
        (no_csp_on_redirects, "sign-in redirect", "CSP []"),
        (another_login_host_in_the_csp, "healthz", "auth.tub.elsewhere.test"),
        (another_login_host_in_the_csp, "hashed assets", "auth.tub.elsewhere.test"),
        (health_failing, "healthz", "starting"),
        (health_cached, "healthz", "max-age=60"),
        (search_open_without_a_session, "sign-in redirect", "GET /search?q=reserve+margin: 200"),
        (sign_in_on_another_host, "sign-in redirect", "went to https://login."),
        (callback_elsewhere, "sign-in redirect", "/callback"),
        (assets_cached_privately, "hashed assets", "private, no-store"),
        (assets_at_a_digest_that_is_not_theirs, "hashed assets", "is not its content's digest"),
        (every_digest_served, "hashed assets", "app.js: 200"),
    ],
    ids=lambda value: getattr(value, "__name__", value) if callable(value) else value,
)
def test_a_check_fails_against_the_breakage_it_is_there_for(
    world: Any, edge: Edge, name: str, says: str
) -> None:
    with checks_client(world, edge) as client, pytest.raises(AssertionError) as failed:
        CHECKS[name](client)

    assert says in str(failed.value), str(failed.value)
