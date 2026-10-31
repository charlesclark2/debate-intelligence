"""`scripts/tub_dev_journey.py` against the app in-process, in Chromium (`v1-e39-t10` ac4).

The operator runs the journey against dev, signed in by hand. Here the same functions drive the same
pages, served by this checkout's app through Playwright's routing (every request answered by
Starlette's test client, as the search pages' browser suite answers them), with a session planted
in place of managed login. They must pass against it, and fail where the pilot would be wrong: a
copy that carries a provenance line, and a removed card still served.

The download world's `download` card stands in for the seed's: a disclosed `hsld26` card whose file
the world stores, so its download is built by the real E33 writer.

Marked `slow`, as every browser suite is (working agreement 1): validate-dev's slow tier runs it.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Route, sync_playwright

from debate_api.cookies import SESSION_COOKIE

REPOSITORY: Final = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPOSITORY / "scripts"))

import tub_dev_journey as journey  # noqa: E402

pytestmark = pytest.mark.slow

CARD: Final = journey.JourneyCard(
    words="gabbro ridges", caselist="hsld26", tag="Gabbro ridges slow upland erosion"
)
JOURNEY_STEPS: Final = [
    "PASS sign in",
    "PASS search",
    "PASS result count",
    "PASS open the card",
    "PASS provenance on the card page",
    "PASS back link",
    "PASS Copy card",
    "PASS the copy holds the card",
    "PASS no provenance line in the copy",
    "PASS download",
]

Alter = Callable[[str, int, dict[str, str], bytes], bytes]


def unchanged(path: str, status: int, headers: dict[str, str], body: bytes) -> bytes:
    return body


@pytest.fixture
def world(download_world: Any) -> Any:
    """Search, cards and the download (`v1-e39-t20`)."""
    return download_world


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        launched = playwright.chromium.launch(channel="chromium")
        yield launched
        launched.close()


class InProcess:
    """A Chromium context on the app, signed in, every request served in-process."""

    def __init__(self, world: Any, browser: Browser, alter: Alter = unchanged) -> None:
        self.world = world
        self.origin = world.public_origin
        self.client = world.new_browser()
        self.alter = alter
        self.context: BrowserContext = browser.new_context(
            viewport={"width": 1366, "height": 768}, accept_downloads=True
        )
        self.context.route("**/*", self._serve)
        self.page: Page = self.context.new_page()
        world.login.add_account("debater.one", "student")
        self.context.add_cookies(
            [
                {
                    "name": SESSION_COOKIE,
                    "value": world.sealed_session(world.session_for("debater.one")),
                    "url": self.origin + "/",
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "Lax",
                }
            ]
        )

    def _serve(self, route: Route) -> None:
        request = route.request
        parts = urlsplit(request.url)
        if f"{parts.scheme}://{parts.netloc}" != self.origin:
            route.abort()
            return
        self.client.cookies.clear()
        headers = {name: value for name, value in request.headers.items() if name.lower() != "host"}
        if headers.get("origin") == self.origin:
            headers["sec-fetch-site"] = "same-origin"
        answer = self.client.request(
            request.method,
            parts.path + (f"?{parts.query}" if parts.query else ""),
            headers=headers,
            content=request.post_data_buffer,
        )
        response_headers = {
            name: value for name, value in answer.headers.items() if name.lower() != "set-cookie"
        }
        cookies = answer.headers.get_list("set-cookie")
        if cookies:
            response_headers["set-cookie"] = "\n".join(cookies)
        body = self.alter(parts.path, answer.status_code, response_headers, answer.content)
        response_headers.pop("content-length", None)
        route.fulfill(status=answer.status_code, headers=response_headers, body=body)

    def close(self) -> None:
        self.context.close()


@pytest.fixture
def make_pilot(world: Any, browser: Browser) -> Iterator[Callable[..., InProcess]]:
    made: list[InProcess] = []

    def make(alter: Alter = unchanged) -> InProcess:
        made.append(InProcess(world, browser, alter))
        return made[-1]

    yield make
    for one in made:
        one.close()


def test_the_journey_signs_in_searches_opens_copies_and_downloads_and_names_the_card(
    world: Any, make_pilot: Callable[..., InProcess], tmp_path: Path
) -> None:
    pilot = make_pilot()
    said: list[str] = []

    journey.wait_for_sign_in(pilot.page, pilot.origin + "/", said.append, seconds=30)
    path = journey.run_journey(pilot.page, pilot.context, pilot.origin + "/", CARD, tmp_path, said.append)

    assert [line for line in said if line.startswith(("PASS", "FAIL"))] == JOURNEY_STEPS
    assert path == world.card_path("download")
    assert said[-1] == f"card path {path}"
    assert list(tmp_path.iterdir()) == [], "the downloaded file is deleted"
    assert len(world.built) == 1, "the real writer built the one file"


def with_provenance_in_the_copy(path: str, status: int, headers: dict[str, str], body: bytes) -> bytes:
    if not path.endswith("/copy"):
        return body
    copied = json.loads(body)
    copied["html"] = "<p>[Disclosed: hsld26 2026-09-15]</p>" + copied["html"]
    return json.dumps(copied).encode()


def test_the_journey_fails_on_a_copy_that_carries_a_provenance_line(
    make_pilot: Callable[..., InProcess], tmp_path: Path
) -> None:
    pilot = make_pilot(with_provenance_in_the_copy)
    said: list[str] = []

    with pytest.raises(journey.JourneyFailed):
        journey.run_journey(pilot.page, pilot.context, pilot.origin + "/", CARD, tmp_path, said.append)

    assert (
        said[-1]
        == "FAIL no provenance line in the copy: the copy carries a provenance line (data-use policy 1.11)"
    )


def test_the_journey_fails_when_the_card_is_not_found(
    make_pilot: Callable[..., InProcess], tmp_path: Path
) -> None:
    pilot = make_pilot()
    said: list[str] = []
    missing = journey.JourneyCard(words="gabbro ridges", caselist="hsld26", tag="A tag no card has")

    with pytest.raises(journey.JourneyFailed):
        journey.run_journey(pilot.page, pilot.context, pilot.origin + "/", missing, tmp_path, said.append)

    assert said == ["FAIL search: 0 results tagged 'A tag no card has' for 'gabbro ridges'"]


def test_the_removed_check_passes_for_a_card_gone_and_fails_for_one_still_served(
    world: Any, make_pilot: Callable[..., InProcess]
) -> None:
    pilot = make_pilot()
    gone, said = f"/cards/hsld26/{'e' * 64}", []

    journey.check_removed(pilot.page, pilot.origin + "/", gone, CARD, said.append)
    assert said == ["PASS the removed card's page", "PASS the removed card is not in the results"]

    still_there: list[str] = []
    with pytest.raises(journey.JourneyFailed):
        journey.check_removed(
            pilot.page, pilot.origin + "/", world.card_path("download"), CARD, still_there.append
        )
    assert still_there == [
        "FAIL the removed card's page: 200, 'Gabbro ridges slow upland erosion'",
    ]
