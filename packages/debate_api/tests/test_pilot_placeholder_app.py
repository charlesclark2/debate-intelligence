"""The pilot's placeholder app (v1-e39-t04): `/healthz`, one page, and ADR-0019's caching rule.

The app runs in-process through Starlette's test client: no socket, no uvicorn, no Lambda.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from debate_api.app import PRIVATE_NO_STORE, create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_healthz_answers_ok_for_the_readiness_check(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_the_placeholder_page_is_html(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>Team evidence search</title>" in response.text


@pytest.mark.parametrize("path", ["/", "/healthz", "/no-such-page"])
def test_every_response_is_private_and_not_stored(client: TestClient, path: str) -> None:
    """ADR-0019 (a) 5: nothing the app sends may be cached at the edge or kept by the browser."""
    response = client.get(path)

    assert response.headers["cache-control"] == PRIVATE_NO_STORE


def test_the_page_carries_no_script_and_no_inline_style(client: TestClient) -> None:
    """The edge sends `default-src 'self'`: an inline script or style would be refused anyway."""
    page = client.get("/").text

    assert "<script" not in page.lower()
    assert "<style" not in page.lower()
    assert re.search(r"\sstyle=", page, re.IGNORECASE) is None


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_there_is_no_interactive_api_documentation(client: TestClient, path: str) -> None:
    """FastAPI's documentation pages load scripts from a third-party CDN; the pilot loads none."""
    assert client.get(path).status_code == 404


def test_a_post_to_the_page_is_not_allowed(client: TestClient) -> None:
    """The placeholder changes nothing, so it accepts nothing that could."""
    assert client.post("/", content=b"").status_code == 405


def test_importing_the_module_builds_no_app() -> None:
    """uvicorn runs `debate_api.app:create_app --factory`; a module-level app would be a second one."""
    import debate_api.app as module

    assert not any(type(value).__name__ == "FastAPI" for value in vars(module).values())
