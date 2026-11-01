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

import ast
import re
from importlib.resources import files
from pathlib import Path
from typing import Any

import pytest

from debate_api.app import PRIVATE_NO_STORE
from debate_api.pages import IMMUTABLE

SCRIPT = files("debate_api").joinpath("static", "app.js").read_text()


@pytest.fixture
def world(auth_world: Any) -> Any:
    """This file's world: sign-in alone: no index, no sources and no landscape bundles (`v1-e39-t20`)."""
    return auth_world


@pytest.fixture
def pages(world: Any) -> dict[str, str]:
    """Every page the app renders, for a coach (who sees every link) and a pending enrolment."""
    world.login.add_account("coach.one", "coach")
    world.login.add_account("debater.two", "student", has_authenticator=False)
    world.use_session(world.session_for("coach.one"))
    rendered = {path: world.browser.get(path).text for path in ["/", "/account", "/coach"]}
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
    """The one other form is the search form, a `GET` to `/search` that changes nothing (v1-e39-t06)."""
    forms = [form for page in pages.values() for form in re.findall(r"<form\b[^>]*>", page)]
    searches = [form for form in forms if 'role="search"' in form]
    forms = [form for form in forms if form not in searches]

    assert searches == ['<form class="search-form" method="get" action="/search" role="search">']
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


def test_the_script_answers_only_with_a_place_to_go_or_a_message() -> None:
    """No route answers a POST with a page since *Start* was withdrawn (PM ruling (d), 2026-10-20)."""
    assert "DOMParser" not in SCRIPT and "replaceWith" not in SCRIPT


def test_the_script_reaches_no_other_origin() -> None:
    """Its requests go to the form's own action, to Copy card's path, which must be the pilot's own,
    and to the pilot's own `/download` (`v1-e39-t08`).

    The one URL prefix in it checks where to go next.
    """
    code = SCRIPT.split('"use strict";', 1)[1]
    assert re.findall(r"[a-z]+://[^\s\"']*", code) == ["https://"]
    assert 'location.startsWith("https://")' in code
    assert re.findall(r"fetch\(([^,]+),", code) == ["form.action", "path", '"/download"']
    assert 'path.startsWith("/") && !path.startsWith("//")' in code
    assert "if (!isOwnPath(path)" in code
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
    """uvicorn builds the app with `debate_api.container`'s factory; a module-level one would be a second."""
    import debate_api.app as module

    assert not any(type(value).__name__ == "FastAPI" for value in vars(module).values())


class _Imports(ast.NodeVisitor):
    """Every module a file imports, at any depth.

    A visitor because, until v1-e41-t11, `scripts/affected_tests.py` read a test that parses Python
    and calls `ast.walk` as one that reads every Python file. It no longer does.
    """

    def __init__(self) -> None:
        self.names: set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        self.names |= {alias.name for alias in node.names}

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.names.add(node.module or "")


def test_the_app_module_never_imports_the_composition_root() -> None:
    """Not even inside a function (`v1-e39-t23`): to the test selector, every test that builds the app
    would then reach every adapter the function wires, the parser, the writer, Cognito and S3 among them.
    Since v1-e41-t11 a lint-imports contract holds every other debate_api module to the same rule."""
    import debate_api.app as module

    imports = _Imports()
    imports.visit(ast.parse(Path(str(module.__file__)).read_text(encoding="utf-8")))

    assert "debate_api.routes" in imports.names
    assert not {name for name in imports.names if name.endswith("container")}


def test_the_templates_and_the_script_ship_in_the_package() -> None:
    package = files("debate_api")
    for name in [
        "base.html",
        "search.html",
        "card.html",
        "account.html",
        "authenticator.html",
        "coach.html",
        "signed_out.html",
        "sign_in_failed.html",
        "refused.html",
    ]:
        assert package.joinpath("templates", name).is_file(), name
    assert package.joinpath("static", "app.js").is_file()
    assert package.joinpath("static", "app.css").is_file()
