"""The evidence search pilot's account-free checks, as validate-dev runs them against dev (`v1-e39-t10`).

Each check takes an `httpx.Client` whose base URL is the pilot's own origin, sends a handful of `GET`
requests that need no session, each with no cookie, and asserts on the answers. None signs in or
sends a secret: validate-dev holds no account and no TOTP seed for the pilot (the PM's
amendment of 2026-10-21). The signed-in journey is the operator's (`scripts/tub_dev_journey.py`).

What they hold, from what the pilot is built to answer:

* `/healthz` answers `{"status":"ok"}`, `private, no-store` (the deploy script's own check);
* a page asked for without a session is sent, `302`, to managed login's `/oauth2/authorize` on the
  login host, with the pilot's own callback as `redirect_uri` (`v1-e39-t05`);
* the page `/signed-out`, which needs no session, links `app.js` and `app.css` at content-hashed paths,
  `/static/<the first 16 hex of the file's sha256>/<name>`, each served
  `public, max-age=31536000, immutable`; a path whose digest is not the file's is `404` and not cached
  (`v1-e39-t06`);
* every answer carries CloudFront's Content-Security-Policy, exactly as the distribution sends it
  (`v1-e39-t04`). :func:`answer` checks it on each response the other checks read.

The expected values are written here by hand. `packages/debate_api/tests/test_cloud_smoke_checks.py`
runs every check against the real app behind the CSP that `distribution.tf` writes, and against
broken versions of it, so a check that cannot fail does not pass for long.
"""

from __future__ import annotations

import hashlib
import re
from typing import Final
from urllib.parse import parse_qs, urlsplit

import httpx

__all__ = [
    "BASE_URL_VARIABLE",
    "DEV_PILOT_URL",
    "IMMUTABLE",
    "PRIVATE_NO_STORE",
    "answer",
    "check_health",
    "check_pages_need_a_session",
    "check_static_assets_are_content_hashed",
    "expected_content_security_policy",
]

DEV_PILOT_URL: Final = "https://tub.dev.wfbdebate.com/"
"""What validate-dev checks. The pilot's own host, through CloudFront, never the function URL."""

BASE_URL_VARIABLE: Final = "TUB_SMOKE_BASE_URL"
"""Points the checks at another origin. Not a `DEBATE_*` name, which validate-dev's driver withholds."""

PRIVATE_NO_STORE: Final = "private, no-store"
IMMUTABLE: Final = "public, max-age=31536000, immutable"

PAGES_NEEDING_A_SESSION: Final = ("/", "/search?q=reserve+margin", "/account")
"""A page, a search and the account page: each is sent to sign-in, and none is answered."""

_ASSET_LINK: Final = re.compile(r'(?:href|src)="(/static/([0-9a-f]{16})/(app\.(?:css|js)))"')
_MEDIA_TYPES: Final = {"app.css": "text/css", "app.js": "text/javascript"}
_NOT_THE_DIGEST: Final = "0" * 16


def expected_content_security_policy(origin: httpx.URL) -> str:
    """CloudFront's CSP for the pilot at `origin`: `form-action` names its login host, `auth.<host>`."""
    return "; ".join(
        [
            "default-src 'self'",
            "frame-ancestors 'none'",
            "object-src 'none'",
            "base-uri 'none'",
            f"form-action 'self' https://auth.{origin.host}",
        ]
    )


def answer(client: httpx.Client, path: str) -> httpx.Response:
    """`GET path` as a new browser sends it, following no redirect; the answer must carry the edge's CSP.

    The client's cookie jar is emptied first: a `302` to sign-in sets a sign-in transaction cookie,
    and a check that sent it back would no longer be asking as someone without a session.
    """
    client.cookies.clear()
    response = client.get(path)
    assert response.headers.get_list("content-security-policy") == [
        expected_content_security_policy(client.base_url)
    ], f"GET {path}: {response.status_code}, CSP {response.headers.get_list('content-security-policy')}"
    return response


def check_health(client: httpx.Client) -> None:
    response = answer(client, "/healthz")

    assert response.status_code == 200, f"GET /healthz: {response.status_code} {response.text}"
    assert response.json() == {"status": "ok"}, f"GET /healthz: {response.text}"
    cache = response.headers.get("cache-control")
    assert cache == PRIVATE_NO_STORE, f"GET /healthz: Cache-Control {cache}"


def check_pages_need_a_session(client: httpx.Client) -> None:
    origin = client.base_url
    for path in PAGES_NEEDING_A_SESSION:
        response = answer(client, path)

        assert response.status_code == 302, f"GET {path}: {response.status_code}"
        cache = response.headers.get("cache-control")
        assert cache == PRIVATE_NO_STORE, f"GET {path}: Cache-Control {cache}"
        location = urlsplit(response.headers["location"])
        went_to = f"{location.scheme}://{location.netloc}{location.path}"
        assert went_to == f"https://auth.{origin.host}/oauth2/authorize", f"GET {path} went to {went_to}"
        query = parse_qs(location.query)
        assert query.get("response_type") == ["code"], (
            f"GET {path}: response_type {query.get('response_type')}"
        )
        callback = query.get("redirect_uri")
        assert callback == [f"https://{origin.host}/auth/callback"], f"GET {path}: redirect_uri {callback}"


def check_static_assets_are_content_hashed(client: httpx.Client) -> None:
    page = answer(client, "/signed-out")
    assert page.status_code == 200, f"GET /signed-out: {page.status_code}"
    linked = {name: (path, digest) for path, digest, name in _ASSET_LINK.findall(page.text)}
    assert set(linked) == {"app.css", "app.js"}, f"/signed-out links {sorted(linked)}"

    for name, (path, digest) in sorted(linked.items()):
        asset = answer(client, path)

        assert asset.status_code == 200, f"GET {path}: {asset.status_code}"
        cache = asset.headers.get("cache-control")
        assert cache == IMMUTABLE, f"GET {path}: Cache-Control {cache}"
        media_type = asset.headers.get("content-type", "").split(";")[0]
        assert media_type == _MEDIA_TYPES[name], f"GET {path}: Content-Type {media_type}"
        actual = hashlib.sha256(asset.content).hexdigest()[:16]
        assert actual == digest, f"{path} is not its content's digest, {actual}"

    stale = f"/static/{_NOT_THE_DIGEST}/app.js"
    answered = answer(client, stale)
    assert answered.status_code == 404, f"GET {stale}: {answered.status_code}"
    cache = answered.headers.get("cache-control")
    assert cache == PRIVATE_NO_STORE, f"GET {stale}: Cache-Control {cache}"
