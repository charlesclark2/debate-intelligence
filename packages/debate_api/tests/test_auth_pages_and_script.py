"""The pages and the one script (ADR-0019 (a) 3 and 5, (b) 1).

* Every page loads exactly one script, the first-party `/static/<digest>/app.js`, and holds no inline
  script or style, which the edge's `default-src 'self'` would refuse anyway.
* Every state-changing form is a `method="post"` form, which `app.js` sends with `fetch`, the body's
  SHA-256 in `x-amz-content-sha256` and the CSRF token in `X-CSRF-Token`. CloudFront's origin
  access control refuses a POST without the hash.
* Pages are `private, no-store`; the script, at its content-hashed path, is cacheable for a year.
* `/healthz` answers the Lambda Web Adapter's readiness check, and there are no API docs.
"""

from __future__ import annotations

import re
from importlib.resources import files
from typing import Any

import pytest

from debate_api.app import PRIVATE_NO_STORE
from debate_api.pages import IMMUTABLE

SCRIPT = files("debate_api").joinpath("static", "app.js").read_text()


@pytest.fixture
def pages(world: Any) -> dict[str, str]:
    """Every page the app renders, for a coach (who sees every link) and a pending enrolment."""
    world.login.add_account("coach.one", "coach")
    world.login.add_account("debater.two", "student", has_authenticator=False)
    world.use_session(world.session_for("coach.one"))
    rendered = {
        path: world.browser.get(path).text for path in ["/", "/account", "/coach", "/account/authenticator"]
    }
    rendered["/signed-out"] = world.new_browser().get("/signed-out").text
    rendered["/auth/callback (refused)"] = world.new_browser().get("/auth/callback?code=x&state=y").text
    enrolling = world.new_browser()
    world.sign_in("debater.two", browser=enrolling)
    rendered["/account/authenticator (enrolling)"] = enrolling.get("/account/authenticator").text
    return rendered


def test_every_page_loads_the_one_first_party_script_and_nothing_inline(
    world: Any, pages: dict[str, str]
) -> None:
    script_path = world.app.state.pilot.app_script.path
    for path, page in pages.items():
        scripts = re.findall(r"<script\b[^>]*>", page)
        assert scripts == [f'<script src="{script_path}" defer>'], path
        assert re.findall(r"<script\b[^>]*>(.*?)</script>", page, re.DOTALL) == [""], path
        assert "<style" not in page.lower(), path
        assert re.search(r"\sstyle=", page, re.IGNORECASE) is None, path
        assert re.search(r"\son[a-z]+=", page, re.IGNORECASE) is None, path
        assert "http://" not in page and "//cdn" not in page, path


def test_every_form_that_changes_something_is_a_post_form(pages: dict[str, str]) -> None:
    forms = [form for page in pages.values() for form in re.findall(r"<form\b[^>]*>", page)]

    assert forms
    assert all('method="post"' in form for form in forms)
    actions = {re.search(r'action="([^"]+)"', form).group(1) for form in forms}  # type: ignore[union-attr]
    assert actions <= {
        "/auth/sign-out",
        "/account/email",
        "/account/email/verify",
        "/account/email/remove",
        "/account/authenticator",
    }


def test_the_script_sends_every_post_with_the_body_hash_and_the_csrf_token() -> None:
    assert 'crypto.subtle.digest("SHA-256", body)' in SCRIPT
    assert '"x-amz-content-sha256": digest' in SCRIPT
    assert '"X-CSRF-Token": csrfToken()' in SCRIPT
    assert 'meta[name="tub-csrf"]' in SCRIPT
    assert 'method: "POST"' in SCRIPT and 'credentials: "same-origin"' in SCRIPT
    assert 'form.method.toLowerCase() !== "post"' in SCRIPT and "event.preventDefault()" in SCRIPT


def test_the_script_reaches_no_other_origin() -> None:
    """Its one request goes to the form's own action; the one URL prefix in it checks where to go next."""
    code = SCRIPT.split('"use strict";', 1)[1]
    assert re.findall(r"[a-z]+://[^\s\"']*", code) == ["https://"]
    assert 'location.startsWith("https://")' in code
    assert re.findall(r"fetch\(([^,]+),", code) == ["form.action"]
    assert "eval(" not in SCRIPT and "innerHTML" not in SCRIPT and "document.write" not in SCRIPT


def test_the_script_is_served_at_its_hash_and_cached_for_a_year(world: Any) -> None:
    script = world.app.state.pilot.app_script

    response = world.browser.get(script.path)

    assert response.status_code == 200
    assert response.content == SCRIPT.encode()
    assert response.headers["cache-control"] == IMMUTABLE
    assert response.headers["content-type"].startswith("text/javascript")
    assert world.browser.get("/static/0000000000000000/app.js").status_code == 404


@pytest.mark.parametrize(
    "path", ["/", "/account", "/coach", "/account/authenticator", "/signed-out", "/healthz"]
)
def test_every_page_is_private_and_not_stored(world: Any, path: str) -> None:
    world.login.add_account("coach.one", "coach")
    world.use_session(world.session_for("coach.one"))

    assert world.browser.get(path).headers["cache-control"] == PRIVATE_NO_STORE


def test_a_redirect_to_sign_in_is_not_stored_either(world: Any) -> None:
    assert world.browser.get("/account").headers["cache-control"] == PRIVATE_NO_STORE


def test_healthz_answers_ok_for_the_readiness_check(world: Any) -> None:
    response = world.browser.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_there_is_no_interactive_api_documentation(world: Any, path: str) -> None:
    """FastAPI's documentation pages load scripts from a third-party CDN; the pilot loads none."""
    world.login.add_account("coach.one", "coach")
    world.use_session(world.session_for("coach.one"))

    assert world.browser.get(path).status_code == 404


def test_importing_the_module_builds_no_app() -> None:
    """uvicorn runs `debate_api.app:create_app --factory`; a module-level app would be a second one."""
    import debate_api.app as module

    assert not any(type(value).__name__ == "FastAPI" for value in vars(module).values())


def test_the_templates_and_the_script_ship_in_the_package() -> None:
    package = files("debate_api")
    for name in [
        "base.html",
        "home.html",
        "account.html",
        "authenticator.html",
        "coach.html",
        "signed_out.html",
        "sign_in_failed.html",
        "refused.html",
    ]:
        assert package.joinpath("templates", name).is_file(), name
    assert package.joinpath("static", "app.js").is_file()
