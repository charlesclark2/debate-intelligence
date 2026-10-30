"""The search pages in Chromium, as a Chromebook's Chrome and a phone show them (`v1-e39-t06`).

The criteria: ac1 (search, filter, page, open and copy a card at each size, axe clean), ac2 (a pasted
copy keeps every span), ac3 (no other origin, no inline script, the edge's CSP) and ac5 (long cards).

Chromium is Playwright's build, run as Chrome's own headless mode (`channel="chromium"`), so the
Clipboard API and the CSP behave as in Chrome. The pages come from the app in this process: every
request the browser makes is answered through Starlette's test client by the routing below, which
puts on each answer the Content-Security-Policy CloudFront sends (read from
`infrastructure/modules/evidence_search/distribution.tf`, so the test enforces the deployed
policy) and refuses, and records, any request for another origin. Nothing reaches a network.

The one other origin is `EDITOR_ORIGIN`, a fixture page standing in for Google Docs: two editable
regions Copy card is pasted into, one taking the browser's own paste and one reading the
clipboard's `text/html` in its paste event, as Docs does. It is not one of the pilot's pages.

axe-core is injected by these tests from axe-playwright-python's copy, never served by the app.

Marked `slow`: browser suites run outside the PR path (working agreement 1). Run them with
`uv run pytest -m slow packages/debate_api/tests/browser`, after `uv run playwright install chromium`.
"""

from __future__ import annotations

import io
import json
import logging
import re
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final
from urllib.parse import parse_qs, urlsplit

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Browser, BrowserContext, Page, Route, expect, sync_playwright

from debate_api.cookies import SESSION_COOKIE
from debate_api.copy_card import copied_card
from debate_core.domain.file_provenance import formatting_sha256

pytestmark = pytest.mark.slow

REPOSITORY: Final = Path(__file__).resolve().parents[4]
DISTRIBUTION: Final = REPOSITORY / "infrastructure" / "modules" / "evidence_search" / "distribution.tf"
EDITOR_ORIGIN: Final = "https://editor.example.test"

VIEWPORTS: Final = {
    "chromebook 1366x768": {"viewport": {"width": 1366, "height": 768}},
    "chromebook 1280x800": {"viewport": {"width": 1280, "height": 800}},
    "phone 390x844": {
        "viewport": {"width": 390, "height": 844},
        "device_scale_factor": 3,
        "is_mobile": True,
        "has_touch": True,
    },
}

FEATURED_LINE: Final = (
    "[Disclosed: hsld26 2026-09-15 — Maple Grove QX, Neg vs. Invented Invitational Round 4]"
)

RECORDER: Final = """
(() => {
  window.__violations = [];
  document.addEventListener("securitypolicyviolation", (event) => {
    window.__violations.push(event.violatedDirective + " " + event.blockedURI);
  });
  window.__copyEvents = [];
  let inClick = false;
  document.addEventListener("click", () => {
    inClick = true;
    window.__copyEvents.push("click");
    setTimeout(() => { inClick = false; }, 0);
  }, true);
  if (navigator.clipboard) {
    const write = navigator.clipboard.write.bind(navigator.clipboard);
    navigator.clipboard.write = (items) => {
      const values = items.length === 1 ? items[0].types.join(",") : "";
      window.__copyEvents.push("write called " + (inClick ? "in the click" : "after the click") +
        (navigator.userActivation.isActive ? " with activation " : " without activation ") + values);
      return write(items).then(
        (done) => { window.__copyEvents.push("write done"); return done; },
        (error) => { window.__copyEvents.push("write refused " + error.name); throw error; });
    };
  }
  const fetchFirst = window.fetch.bind(window);
  window.fetch = (...args) => fetchFirst(...args).then((answer) => {
    window.__copyEvents.push("fetch answered");
    return answer;
  });
})();
"""
"""Init script (CDP, outside the page's CSP): the CSP violations a page reports, and Copy card's order."""

EDITOR_PAGE: Final = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Editor fixture</title><script src="/editor.js" defer></script></head><body><main>
<h1>Editor fixture</h1>
<div id="browser-paste" contenteditable="true" aria-label="The browser's own paste"></div>
<div id="docs-paste" contenteditable="true" aria-label="A paste read as Google Docs reads it"></div>
<div id="as-copied" aria-label="The copied HTML as written, not pasted"></div>
</main></body></html>"""

EDITOR_SCRIPT: Final = """
"use strict";
document.getElementById("docs-paste").addEventListener("paste", (event) => {
  event.preventDefault();
  const parsed = new DOMParser().parseFromString(event.clipboardData.getData("text/html"), "text/html");
  const region = event.currentTarget;
  const nodes = Array.from(parsed.body.childNodes, (node) => document.importNode(node, true));
  region.replaceChildren(...nodes);
  region.dataset.plain = event.clipboardData.getData("text/plain");
});
"""

READ_REGION: Final = """
(selector) => {
  const characters = [];
  const paragraphs = [];
  const walk = (node, styles) => {
    if (node.nodeType === Node.TEXT_NODE) {
      for (const character of node.data) characters.push([character, styles]);
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    const tag = node.tagName.toLowerCase();
    if (tag === "br") { characters.push(["\\n", styles]); return; }
    const style = node.getAttribute("style");
    const inner = tag === "span" && style ? styles.concat([style]) : styles;
    if (tag === "p") paragraphs.push({ style: style || "", start: characters.length });
    for (const child of node.childNodes) walk(child, inner);
    if (tag === "p") paragraphs[paragraphs.length - 1].end = characters.length;
  };
  walk(document.querySelector(selector), []);
  return { characters, paragraphs };
}
"""
"""Each character of an editable region with the `style` of every `span` above it, and its paragraphs."""

LOOK_OF_REGION: Final = """
(selector) => {
  const region = document.querySelector(selector);
  const looks = [];
  const lookOf = (element) => {
    const style = getComputedStyle(element);
    let underline = false;
    let background = "";
    for (let node = element; node && node !== region.parentElement; node = node.parentElement) {
      const own = getComputedStyle(node);
      if (own.textDecorationLine.includes("underline")) underline = true;
      if (!background && own.backgroundColor !== "rgba(0, 0, 0, 0)") background = own.backgroundColor;
    }
    return [Number(style.fontWeight) >= 600, underline, background, style.color, style.fontSize];
  };
  const walk = (node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      const look = lookOf(node.parentElement);
      for (const character of node.data) looks.push([character, ...look]);
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    if (node.tagName === "BR") { looks.push(["\\n", ...lookOf(node.parentElement)]); return; }
    for (const child of node.childNodes) walk(child);
  };
  walk(region);
  return looks;
}
"""
"""What each character of a region looks like: bold, underlined, its highlight, colour and size."""


@pytest.fixture
def world(every_surface_world: Any) -> Any:
    """This file's world: every surface at once (`v1-e39-t20`)."""
    return every_surface_world


def edge_content_security_policy(login_origin: str) -> str:
    """The CSP CloudFront's response headers policy sends, as `distribution.tf` writes it."""
    source = DISTRIBUTION.read_text()
    listed = re.search(r'content_security_policy = join\("; ", \[(.*?)\]\)', source, re.DOTALL)
    assert listed is not None, "distribution.tf no longer writes the CSP as join(...)"
    directives = re.findall(r'"([^"]+)"', listed.group(1))
    return "; ".join(directive.replace("${local.login_origin}", login_origin) for directive in directives)


@dataclass
class Exchange:
    """One request the browser made, and what was answered."""

    method: str
    url: str
    status: int
    content_type: str
    csp: str | None
    body: bytes = field(repr=False)


class Pilot:
    """A browser context on the app: every request served in-process, recorded, under the edge's CSP."""

    def __init__(self, world: Any, browser: Browser, viewport: dict[str, Any]) -> None:
        self.world = world
        self.origin = world.public_origin
        self.csp = edge_content_security_policy(world.login_origin)
        self.exchanges: list[Exchange] = []
        self.foreign: list[str] = []
        self.client = world.new_browser()
        # No clipboard permission is granted while Copy card writes: Chrome's own rule (a write inside
        # a user activation) decides, as on a Chromebook. Granting `clipboard-read` alone would deny
        # writes outright; :meth:`read_clipboard` grants it only to read the copy back.
        self.context: BrowserContext = browser.new_context(**viewport)
        self.context.add_init_script(RECORDER)
        self.context.route("**/*", self._serve)
        self.page: Page = self.context.new_page()

    def sign_in_as_student(self, username: str = "debater.one") -> None:
        self.world.login.add_account(username, "student")
        sealed = self.world.sealed_session(self.world.session_for(username))
        self.context.add_cookies(
            [
                {
                    "name": SESSION_COOKIE,
                    "value": sealed,
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
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin == EDITOR_ORIGIN:
            self._serve_editor(route, parts.path)
            return
        if origin != self.origin:
            self.foreign.append(request.url)
            route.abort()
            return
        self.client.cookies.clear()
        headers = {name: value for name, value in request.headers.items() if name.lower() != "host"}
        # Chrome's network stack adds Sec-Fetch-Site after Playwright intercepts the request, so it is
        # never here. Chrome sends `same-origin` for a request whose Origin is the page's own, and the
        # gate checks it on every POST (v1-e39-t07's sign-out); a request from another origin gets none.
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
        response_headers["content-security-policy"] = self.csp
        response_headers["x-content-type-options"] = "nosniff"
        self.exchanges.append(
            Exchange(
                method=request.method,
                url=request.url,
                status=answer.status_code,
                content_type=answer.headers.get("content-type", ""),
                csp=response_headers["content-security-policy"],
                body=answer.content,
            )
        )
        route.fulfill(status=answer.status_code, headers=response_headers, body=answer.content)

    @staticmethod
    def _serve_editor(route: Route, path: str) -> None:
        if path == "/editor.js":
            route.fulfill(status=200, content_type="text/javascript", body=EDITOR_SCRIPT)
        else:
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=EDITOR_PAGE)

    def read_clipboard(self) -> dict[str, Any]:
        """What the clipboard holds now, read after the copy with read permission granted."""
        self.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=self.origin)
        return self.page.evaluate(
            """async () => {
                const [item] = await navigator.clipboard.read();
                const html = await (await item.getType("text/html")).text();
                const text = await (await item.getType("text/plain")).text();
                return { types: item.types.slice().sort(), html, text };
            }"""
        )

    # Keyboard ------------------------------------------------------------------------------

    def tab_to(self, selector: str, *, backwards: bool = False, limit: int = 80) -> None:
        """Press Tab (or Shift+Tab) until the focus is on `selector`, as a keyboard user would."""
        for _ in range(limit):
            if self.page.evaluate(f"document.activeElement.matches({json.dumps(selector)})"):
                return
            self.page.keyboard.press("Shift+Tab" if backwards else "Tab")
        raise AssertionError(f"Tab never reached {selector}")

    # What every page must be ---------------------------------------------------------------

    def check_page(self) -> None:
        """No CSP violation, no horizontal scroll, and no serious or critical axe violation.

        The violations are read before axe runs and cleared after it: axe sets `style` attributes of
        its own while it checks, which the CSP refuses and reports, and those are not the page's.
        """
        assert self.page.evaluate("window.__violations") == [], self.page.url
        overflow = self.page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        assert overflow <= 0, (self.page.url, overflow)
        found = Axe().run(self.page).response["violations"]
        self.page.evaluate("window.__violations = []")
        serious = [(one["id"], one["impact"]) for one in found if one["impact"] in ("serious", "critical")]
        assert serious == [], (self.page.url, serious)

    def close(self) -> None:
        self.context.close()


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        launched = playwright.chromium.launch(channel="chromium")
        yield launched
        launched.close()


@pytest.fixture(params=list(VIEWPORTS), ids=list(VIEWPORTS))
def pilot(request: pytest.FixtureRequest, world: Any, browser: Browser) -> Iterator[Pilot]:
    made = Pilot(world, browser, VIEWPORTS[request.param])
    made.sign_in_as_student()
    yield made
    made.close()


@pytest.fixture
def chromebook(world: Any, browser: Browser) -> Iterator[Pilot]:
    made = Pilot(world, browser, VIEWPORTS["chromebook 1366x768"])
    made.sign_in_as_student()
    yield made
    made.close()


# ------------------------------------------------------------------------------------------------
# ac1: search, filter, page, open a card and copy it, by keyboard, at each size, axe clean
# ------------------------------------------------------------------------------------------------


def test_search_filter_page_open_and_copy_a_card_by_keyboard(pilot: Pilot) -> None:
    page = pilot.page
    page.goto(pilot.origin + "/")
    expect(page.locator("h1")).to_have_text("Search the team's evidence")
    pilot.check_page()

    pilot.tab_to("#q")
    page.keyboard.type("zephyr")
    page.keyboard.press("Enter")
    expect(page.locator("#results-heading")).to_be_visible()
    expect(page.locator(".result")).to_have_count(20)
    expect(page.locator(".result-count")).to_have_text("25 cards matched.")
    pilot.check_page()

    pilot.tab_to("a[rel=next]")
    page.keyboard.press("Enter")
    expect(page.locator(".result")).to_have_count(5)
    expect(page.get_by_role("link", name="First page")).to_be_visible()
    pilot.check_page()

    pilot.tab_to("#event", backwards=True)
    page.keyboard.type("Public")
    expect(page.locator("#event")).to_have_value("PF")
    pilot.tab_to("button[type=submit]:not(form[action='/auth/sign-out'] button)", backwards=True)
    page.keyboard.press("Enter")
    expect(page.locator(".result")).to_have_count(1)
    expect(page.locator(".result-tag a")).to_have_text("Zephyr tariffs help farmers")

    pilot.tab_to("#q", backwards=True)
    page.keyboard.press("ControlOrMeta+A")
    page.keyboard.type("granite costs")
    pilot.tab_to("#event")
    page.keyboard.type("Any")
    expect(page.locator("#event")).to_have_value("")
    pilot.tab_to("#q", backwards=True)
    page.keyboard.press("Enter")
    expect(page.locator(".result")).to_have_count(1)

    pilot.tab_to(".result-tag a")
    page.keyboard.press("Enter")
    expect(page.locator(".card-label")).to_have_text("Disclosed evidence, not platform-verified")
    expect(page.locator("h1")).to_have_text("Zephyr winds raise granite costs")
    pilot.check_page()

    pilot.tab_to("button[data-tub-copy]")
    page.keyboard.press("Enter")
    expect(page.locator("[data-tub-copy-message]")).to_have_text("Copied. Paste it into Google Docs or Word.")
    clipboard = pilot.read_clipboard()
    with pilot.world.services.search_index.lease() as search:
        card = search.card("hsld26", f"{1:064x}")
    expected = copied_card(card)
    assert clipboard["types"] == ["text/html", "text/plain"]
    assert expected.html in clipboard["html"]
    assert clipboard["text"] == expected.text
    # Chrome parses the HTML it writes in the page, and reports each inline style in it against the
    # page's CSP; it writes every one to the clipboard unchanged (read back above). Those reports are
    # the copy's, one per style attribute, and the page itself still carries none.
    styles = expected.html.count('style="')
    assert page.evaluate("window.__violations") == ["style-src-attr inline"] * styles
    page.evaluate("window.__violations = []")
    pilot.check_page()

    # v1-e39-t11: back to the same results by keyboard, with their count above them.
    pilot.tab_to("nav.back-link a", backwards=True)
    page.keyboard.press("Enter")
    expect(page.locator(".result")).to_have_count(1)
    expect(page.locator(".result-count")).to_have_text("1 card matched.")
    expect(page.locator("#q")).to_have_value("granite costs")
    pilot.check_page()


# ------------------------------------------------------------------------------------------------
# v1-e39-t13: search by passage, the student's choice, by keyboard, at each size, axe clean
# ------------------------------------------------------------------------------------------------

FEATURED_PASSAGE: Final = "The basalt holds when zephyr winds raise granite costs, and then prices tumble"
"""Nine content words, so a card must hold six: the featured card holds seven, no other card two."""


def test_search_by_passage_by_keyboard_pages_opens_a_card_and_comes_back(pilot: Pilot) -> None:
    page = pilot.page
    page.goto(pilot.origin + "/")
    expect(page.locator("#mode")).not_to_be_checked()

    pilot.tab_to("#q")
    page.keyboard.type(FEATURED_PASSAGE)
    pilot.tab_to("#mode")
    page.keyboard.press("Space")
    expect(page.locator("#mode")).to_be_checked()
    pilot.tab_to("button[type=submit]:not(form[action='/auth/sign-out'] button)", backwards=True)
    page.keyboard.press("Enter")
    expect(page.locator(".result")).to_have_count(1)
    expect(page.locator(".result-count")).to_have_text("1 card matched.")
    expect(page.locator(".result-tag a")).to_have_text("Zephyr winds raise granite costs")
    expect(page.locator("#mode")).to_be_checked()
    pilot.check_page()

    pilot.tab_to("#q", backwards=True)
    page.keyboard.press("ControlOrMeta+A")
    page.keyboard.type("zephyr")
    page.keyboard.press("Enter")
    expect(page.locator(".result")).to_have_count(20)
    expect(page.locator(".result-count")).to_have_text("25 cards matched.")
    expect(page.locator("#mode")).to_be_checked()

    pilot.tab_to("a[rel=next]")
    page.keyboard.press("Enter")
    expect(page.locator(".result")).to_have_count(5)
    expect(page.locator(".result-count")).to_have_text("25 cards matched.")
    pilot.check_page()

    pilot.tab_to(".result-tag a", backwards=True)
    page.keyboard.press("Enter")
    expect(page.locator(".card-label")).to_be_visible()
    pilot.tab_to("nav.back-link a", backwards=True)
    page.keyboard.press("Enter")
    expect(page.locator(".result")).to_have_count(5)
    expect(page.locator(".result-count")).to_have_text("25 cards matched.")
    expect(page.locator("#mode")).to_be_checked()
    pilot.check_page()

    pilot.tab_to("#mode", backwards=True)
    page.keyboard.press("Space")
    pilot.tab_to("button[type=submit]:not(form[action='/auth/sign-out'] button)", backwards=True)
    page.keyboard.press("Enter")
    expect(page.locator(".result")).to_have_count(20)
    expect(page.locator("#mode")).not_to_be_checked()
    assert "mode=" not in page.url, "unticked, the search is today's search again"


# ------------------------------------------------------------------------------------------------
# ac2: the copy pasted into an editable region keeps every span, and since policy 1.11 no line
# ------------------------------------------------------------------------------------------------


def test_a_pasted_copy_keeps_every_formatting_span_and_has_no_provenance_line(
    chromebook: Pilot, read_back: Any
) -> None:
    """ac2. Pasted as Google Docs and Word take a paste, the clipboard's HTML read in the paste event,
    every span reads back: the stored spans' `formatting_sha256` coverage, exactly.

    Changed in `v1-e39-t11`: the paste was four paragraphs, the provenance line third. Data-use policy
    version 1.11 (Attribution rule 2, gate item 6) takes the line out of a copy: tag, cite and text."""
    stored = next(one for one in chromebook.world.corpus if one.doc_id == chromebook.world.cards["featured"])
    page = chromebook.page
    page.goto(chromebook.origin + chromebook.world.card_path("featured"))
    page.get_by_role("button", name="Copy card").click()
    expect(page.locator("[data-tub-copy-message]")).to_have_text("Copied. Paste it into Google Docs or Word.")

    editor = chromebook.context.new_page()
    editor.goto(EDITOR_ORIGIN + "/")
    editor.focus("#docs-paste")
    editor.keyboard.press("ControlOrMeta+V")
    expect(editor.locator("#docs-paste p")).to_have_count(3)

    read = editor.evaluate(READ_REGION, "#docs-paste")
    characters = read["characters"]
    tag, cite, body = (
        "".join(character for character, _ in characters[one["start"] : one["end"]])
        for one in read["paragraphs"]
    )
    assert (tag, cite, body) == (stored.tag, stored.cite, stored.text)
    pasted = "".join(character for character, _ in characters)
    assert FEATURED_LINE not in pasted and "[Disclosed:" not in pasted
    last = read["paragraphs"][2]
    spans, sizes = read_back([styles for _, styles in characters[last["start"] : last["end"]]])
    assert formatting_sha256(spans, sizes) == formatting_sha256(
        stored.formatting_spans, stored.font_size_spans
    )
    assert editor.locator("#docs-paste").get_attribute("data-plain") == copied_card_text(chromebook)


def test_the_browsers_own_paste_keeps_how_every_character_of_the_copy_looks(chromebook: Pilot) -> None:
    """Chrome's own editing drops a declaration a parent already makes (`Emphasis`'s underline inside an
    underline), so emphasis names do not survive it; what each character looks like does."""
    page = chromebook.page
    page.goto(chromebook.origin + chromebook.world.card_path("featured"))
    page.get_by_role("button", name="Copy card").click()
    expect(page.locator("[data-tub-copy-message]")).to_have_text("Copied. Paste it into Google Docs or Word.")
    copied = chromebook.read_clipboard()["html"]

    editor = chromebook.context.new_page()
    editor.goto(EDITOR_ORIGIN + "/")
    editor.focus("#browser-paste")
    editor.keyboard.press("ControlOrMeta+V")
    expect(editor.locator("#browser-paste p")).to_have_count(3)
    editor.evaluate("(html) => { document.getElementById('as-copied').innerHTML = html; }", copied)

    pasted = editor.evaluate(LOOK_OF_REGION, "#browser-paste")
    written = editor.evaluate(LOOK_OF_REGION, "#as-copied")
    assert pasted == written
    assert {tuple(look[1:3]) for look in written} >= {(True, True), (False, True), (False, False)}
    assert len({look[3] for look in written}) >= 3 and len({look[5] for look in written}) >= 4
    lines = editor.evaluate(
        "Array.from(document.querySelectorAll('#browser-paste p'), (one) => one.textContent)"
    )
    # Changed in v1-e39-t11: the third paragraph was the provenance line; policy 1.11 leaves it out.
    assert lines[:2] == ["Zephyr winds raise granite costs", "Lindqvist 26, Invented Quarterly, 2026"]
    assert not any("[Disclosed:" in line for line in lines)


def copied_card_text(pilot: Pilot) -> str:
    with pilot.world.services.search_index.lease() as search:
        return copied_card(search.card("hsld26", f"{1:064x}")).text


def test_copy_card_writes_the_clipboard_inside_the_click_before_the_fetch_answers(chromebook: Pilot) -> None:
    """The way chosen: a ClipboardItem of Promises, written in the click, so its activation holds."""
    page = chromebook.page
    page.goto(chromebook.origin + chromebook.world.card_path("featured"))

    page.get_by_role("button", name="Copy card").click()
    expect(page.locator("[data-tub-copy-message]")).to_have_text("Copied. Paste it into Google Docs or Word.")

    assert page.evaluate("window.__copyEvents") == [
        "click",
        "write called in the click with activation text/html,text/plain",
        "fetch answered",
        "write done",
    ]

    button = page.get_by_role("button", name="Copy card").bounding_box()
    status = page.locator("[data-tub-copy-message]").bounding_box()
    bar = page.locator(".card-actions").bounding_box()
    text = page.locator(".card-text").bounding_box()
    assert button is not None and status is not None and bar is not None and text is not None
    assert status["y"] < button["y"] + button["height"] and button["y"] < status["y"] + status["height"]
    assert status["x"] > button["x"] + button["width"]
    # The bar holds Copy card's row and, since v1-e39-t08, the download's row below it; the card's
    # text starts directly under the bar.
    assert bar["y"] < button["y"] and button["y"] + button["height"] < bar["y"] + bar["height"]
    assert 0 < text["y"] - (bar["y"] + bar["height"]) < 40


def test_a_card_no_longer_in_the_index_is_not_copied_and_says_so(chromebook: Pilot) -> None:
    page = chromebook.page
    page.goto(chromebook.origin + chromebook.world.card_path("featured"))
    chromebook.world.services.search_index.close()
    chromebook.world.index_source.objects.clear()

    page.get_by_role("button", name="Copy card").click()

    expect(page.locator("[data-tub-copy-message]")).to_have_text(
        "The search could not be loaded. Try again in a minute."
    )


# ------------------------------------------------------------------------------------------------
# ac3: no other origin, no inline script, the edge's CSP on every response
# ------------------------------------------------------------------------------------------------


def test_no_page_requests_another_origin_or_runs_inline_script_under_the_edges_csp(chromebook: Pilot) -> None:
    page = chromebook.page
    world = chromebook.world
    paths = [
        "/",
        "/search?q=zephyr",
        "/search?q=zephyr&side=NEG&since=2026-09-01",
        world.card_path("featured"),
        world.card_path("long"),
        world.card_path("hostile"),
        world.card_path("camp"),
        world.card_path("linked"),
        world.card_path("featured") + "?q=zephyr&cursor=junk",
        "/account",
    ]
    for path in paths:
        page.goto(chromebook.origin + path)
        expect(page.locator("main")).to_be_visible()
        assert page.evaluate("window.__violations") == [], path
        assert page.evaluate("document.querySelectorAll('script:not([src])').length") == 0, path
        assert page.evaluate("Array.from(document.scripts).map((one) => one.src)") == [
            chromebook.origin + world.app.state.pilot.app_script.path
        ], path
    page.get_by_role("button", name="Copy card").count()
    page.goto(chromebook.origin + world.card_path("featured"))
    page.get_by_role("button", name="Copy card").click()
    expect(page.locator("[data-tub-copy-message]")).to_have_text("Copied. Paste it into Google Docs or Word.")

    assert chromebook.foreign == []
    assert chromebook.exchanges
    for exchange in chromebook.exchanges:
        assert exchange.url.startswith(chromebook.origin + "/"), exchange.url
        assert exchange.csp == chromebook.csp
    assert "default-src 'self'" in chromebook.csp and "script-src" not in chromebook.csp
    assert {urlsplit(exchange.url).path for exchange in chromebook.exchanges} >= {
        world.app.state.pilot.app_script.path,
        world.app.state.pilot.app_stylesheet.path,
        world.card_path("featured") + "/copy",
    }


def test_the_link_out_to_opencaselist_opens_a_new_tab_with_no_opener_or_referrer(pilot: Pilot) -> None:
    """`v1-e39-t11`. The link is read, never followed: following it would leave the test's network."""
    page = pilot.page
    page.goto(pilot.origin + pilot.world.card_path("linked"))

    link = page.get_by_role("link", name="Open on openCaselist (opens in a new tab)")
    expect(link).to_have_attribute("href", "https://opencaselist.com/hsld26/Cedarbrook/LM")
    expect(link).to_have_attribute("target", "_blank")
    expect(link).to_have_attribute("rel", "noopener noreferrer")
    pilot.check_page()
    assert pilot.foreign == []


def test_an_inline_script_would_be_refused_by_the_edges_csp(chromebook: Pilot) -> None:
    """The check above can fail: the same CSP refuses an inline script, and the recorder sees it."""
    page = chromebook.page
    page.goto(chromebook.origin + "/")

    page.evaluate(
        """() => {
            const script = document.createElement("script");
            script.textContent = "window.__ran = true";
            document.body.append(script);
        }"""
    )

    expect(page.locator("body")).to_be_visible()
    page.wait_for_timeout(100)
    assert page.evaluate("window.__ran === true") is False
    assert any(one.startswith("script-src") for one in page.evaluate("window.__violations"))


# ------------------------------------------------------------------------------------------------
# ac5: a card over 3,000 words, read-aloud text first, the rest behind <details>
# ------------------------------------------------------------------------------------------------


def test_a_long_card_shows_its_read_aloud_text_first_and_the_rest_on_request_by_keyboard(
    pilot: Pilot,
) -> None:
    page = pilot.page
    page.goto(pilot.origin + pilot.world.card_path("long"))

    expect(page.locator(".card-read-aloud")).to_have_text("Zephyr read aloud stretch")
    whole = page.locator("details.card-whole .card-text")
    expect(whole).to_be_hidden()
    pilot.check_page()

    pilot.tab_to("details.card-whole summary")
    page.keyboard.press("Enter")

    expect(whole).to_be_visible()
    expect(whole).to_contain_text("feldspar mica gneiss")
    assert page.evaluate("document.querySelector('details.card-whole').open") is True
    pilot.check_page()


# ------------------------------------------------------------------------------------------------
# v1-e39-t07: Copy card when the audit record cannot be written, and what the app logs
# ------------------------------------------------------------------------------------------------

EARLIER_CLIPBOARD: Final = "Synthetic text the student copied before"


def clipboard_now(pilot: Pilot) -> dict[str, Any]:
    """The clipboard's types and plain text, read with read permission granted."""
    pilot.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=pilot.origin)
    return pilot.page.evaluate(
        """async () => {
            const [item] = await navigator.clipboard.read();
            return { types: item.types.slice().sort(), text: await navigator.clipboard.readText() };
        }"""
    )


def test_audit_copy_card_whose_record_cannot_be_written_leaves_the_clipboard_alone_and_says_so(
    chromebook: Pilot,
) -> None:
    """The copy route's 503 rejects the ClipboardItem's promises, so nothing half-written is copied."""
    page = chromebook.page
    page.goto(chromebook.origin + chromebook.world.card_path("featured"))
    chromebook.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=chromebook.origin)
    page.evaluate(f"navigator.clipboard.writeText({json.dumps(EARLIER_CLIPBOARD)})")
    chromebook.context.clear_permissions()
    chromebook.world.audit.failing = True

    page.get_by_role("button", name="Copy card").click()

    expect(page.locator("[data-tub-copy-message]")).to_have_text(
        "The search could not be loaded. Try again in a minute."
    )
    copy = [one for one in chromebook.exchanges if one.url.endswith("/copy")]
    assert [one.status for one in copy] == [503]
    assert any(event.startswith("write refused") for event in page.evaluate("window.__copyEvents"))
    assert clipboard_now(chromebook) == {"types": ["text/plain"], "text": EARLIER_CLIPBOARD}
    assert [record.action.value for record in chromebook.world.audit.records] == ["card-viewed"]


class _Captured(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@contextmanager
def bare_loggers() -> Iterator[_Captured]:
    """Every logger stripped to nothing and sent to one handler at DEBUG; all of it restored after.

    A logger's own handlers, filters, level or `propagate` could hide a record from a test that
    reads the root's (working agreement 10, shared process-wide state).
    """
    loggers = [logging.getLogger()] + [
        one for one in logging.Logger.manager.loggerDict.values() if isinstance(one, logging.Logger)
    ]
    saved = [
        (one, one.level, one.handlers[:], one.filters[:], one.propagate, one.disabled) for one in loggers
    ]
    captured = _Captured()
    try:
        for one in loggers:
            one.handlers, one.filters, one.disabled = [], [], False
            one.setLevel(logging.NOTSET)
            one.propagate = True
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger().addHandler(captured)
        yield captured
    finally:
        for one, level, handlers, filters, propagate, disabled in saved:
            one.setLevel(level)
            one.handlers, one.filters, one.propagate, one.disabled = handlers, filters, propagate, disabled


_STANDARD_RECORD_FIELDS: Final = set(vars(logging.LogRecord("", 0, "", 0, "", None, None)))

JOURNEY_QUERY: Final = "zephyr Maple Grove QX"
"""The fixture school and team code, typed into the search box beside a word that finds cards."""


def test_exposure_a_whole_journey_logs_no_query_school_team_code_or_card_text(
    world: Any, browser: Browser
) -> None:
    """Sign in through the app's callback, search with the school and team code, filter, page, open a
    card from the second page and go back to it, copy, add two cards to the cart and download it
    (`v1-e39-t08`), visit the account page and sign out through managed login's `/logout`; the app's
    log records and audit records hold none of what was seen or typed, the copy and the downloaded
    file hold no provenance line (`v1-e39-t11`, `v1-e39-t08`), and signing out empties the cart.

    Playwright routes only the first request of a redirect chain, so the sign-in's redirects run
    in-process: the real `/` redirect, managed login's answer from `FakeManagedLogin` and the real
    `/auth/callback`, whose session cookie the browser is then given. Sign-out is the browser's own:
    `app.js` posts it and goes to `/logout`, which the stand-in answers with a refresh to the
    pilot's `/signed-out`.
    """
    world.login.add_account("debater.journey", "student")
    pilot = Pilot(world, browser, VIEWPORTS["chromebook 1366x768"])

    def managed_login_logout(route: Route) -> None:
        target = parse_qs(urlsplit(route.request.url).query)["logout_uri"][0]
        page_body = (
            f'<!doctype html><meta http-equiv="refresh" content="0;url={target}"><title>Signed out</title>'
        )
        route.fulfill(status=200, content_type="text/html; charset=utf-8", body=page_body)

    pilot.context.route(lambda url: url.startswith(world.login_origin + "/logout"), managed_login_logout)
    page = pilot.page
    try:
        with bare_loggers() as captured:
            signing_in = world.new_browser()
            assert world.sign_in("debater.journey", browser=signing_in).status_code == 303
            pilot.context.add_cookies(
                [
                    {
                        "name": SESSION_COOKIE,
                        "value": signing_in.cookies.get(SESSION_COOKIE),
                        "url": pilot.origin + "/",
                        "httpOnly": True,
                        "secure": True,
                        "sameSite": "Lax",
                    }
                ]
            )
            page.goto(pilot.origin + "/")
            page.locator("#q").fill(JOURNEY_QUERY)
            page.locator("#q").press("Enter")
            expect(page.locator("main")).to_contain_text("No cards matched.")
            page.locator("#q").fill("zephyr")
            page.locator("#event").select_option("LD")
            page.locator("#q").press("Enter")
            page.get_by_role("link", name="Next results").click()
            expect(page.get_by_role("link", name="First page")).to_be_visible()
            second_page = page.url
            expect(page.locator(".result")).to_have_count(3)
            expect(page.locator(".result-count")).to_have_text("23 cards matched.")
            page.locator(".result-tag a").first.click()
            expect(page.locator(".card-label")).to_have_text("Disclosed evidence, not platform-verified")
            page.get_by_role("link", name="Back to results").click()
            page.wait_for_url(second_page)
            expect(page.locator(".result")).to_have_count(3)
            page.goto(pilot.origin + world.card_path("featured"))
            expect(page.locator(".provenance").first).to_have_text(FEATURED_LINE)
            page.get_by_role("button", name="Copy card").click()
            expect(page.locator("[data-tub-copy-message]")).to_have_text(
                "Copied. Paste it into Google Docs or Word."
            )
            copied = pilot.read_clipboard()
            page.goto(pilot.origin + world.card_path("download"))
            page.get_by_role("button", name="Add to cart").click()
            expect(page.locator("[data-tub-cart-count]")).to_have_text("1 card")
            page.goto(pilot.origin + world.card_path("camp download"))
            page.get_by_role("button", name="Add to cart").click()
            expect(page.locator("[data-tub-cart-count]")).to_have_text("2 cards")
            with page.expect_download() as downloading:
                page.get_by_role("button", name="Download cart").click()
            downloaded = Path(downloading.value.path()).read_bytes()
            assert downloading.value.suggested_filename == "team-evidence-cards-2026-11-02.docx"
            expect(page.locator("[data-tub-cart-message]")).to_contain_text("Downloaded 2 cards.")
            page.goto(pilot.origin + "/account")
            page.get_by_role("button", name="Sign out").click()
            page.wait_for_url(pilot.origin + "/signed-out")
            cart_after = page.evaluate("window.sessionStorage.getItem('tub-download-cart')")
    finally:
        pilot.close()

    assert pilot.foreign == []
    actions = [record.action.value for record in world.audit.records]
    assert actions == [
        "searched",
        "searched",
        "card-viewed",
        "card-viewed",
        "card-copied",
        "card-viewed",
        "card-viewed",
        "cards-downloaded",
    ], actions
    assert cart_after is None, "signing out empties the cart"
    assert downloaded == world.built[-1]
    with zipfile.ZipFile(io.BytesIO(downloaded)) as archive:
        document = archive.read("word/document.xml").decode("utf-8")
    assert "Gabbro ridges slow upland erosion" in document and "Tuff walls shelter seedlings" in document
    for word in ("[Disclosed", "[OpenEv", "Maple Grove", "Invented Invitational", "Cascade Institute"):
        assert word not in document, word
    assert copied["types"] == ["text/html", "text/plain"]
    for part in (copied["html"], copied["text"]):
        assert FEATURED_LINE not in part and "Maple Grove" not in part and "[Disclosed:" not in part
    for record in world.audit.records:
        written = record.to_json()
        for word in (
            "zephyr",
            "Maple Grove",
            "QX",
            "Riverbend",
            "Invented Invitational",
            "Round 4",
            "q=",
            "Gabbro",
        ):
            assert word not in written, (word, written)
    assert world.login.revoked, "the sign-out revoked the refresh token"
    # httpx's records are the test's in-process client's requests: the app cannot log through httpx,
    # which an import contract keeps out of debate_api.
    logged = [
        " ".join(
            [record.name, record.getMessage(), record.exc_text or ""]
            + [f"{key}={value}" for key, value in vars(record).items() if key not in _STANDARD_RECORD_FIELDS]
        )
        for record in captured.records
        if not record.name.startswith(("httpx", "httpcore"))
    ]
    assert any(f"search index {world.index.index_id} loaded" in line for line in logged), logged
    for line in logged:
        for word in (
            "zephyr",
            "maple grove",
            "riverbend",
            "granite",
            "lindqvist",
            "invented",
            "debater.journey",
            "gabbro",
            "tuff",
            "thorvaldsen",
            "okafor",
            "team-evidence-cards",
        ):
            assert word not in line.lower(), (word, line)
        for exact in ("QX", "ZT", "q=", f"{1:064x}", f"{27:064x}", f"{30:064x}"):
            assert exact not in line, (exact, line)


# ------------------------------------------------------------------------------------------------
# v1-e39-t08: Download .docx and the cart, by keyboard, axe clean; a refused card is dropped
# ------------------------------------------------------------------------------------------------


def test_download_one_card_and_a_cart_by_keyboard_dropping_a_refused_card(pilot: Pilot) -> None:
    """A card's own download; then a cart with a card the writer refuses, named, dropped by its button,
    and the rest downloaded. Every page stays axe clean and inside the edge's CSP."""
    page = pilot.page
    world = pilot.world
    page.goto(pilot.origin + world.card_path("download"))
    expect(page.locator("[data-tub-cart]")).to_be_hidden()
    pilot.check_page()

    pilot.tab_to("button[data-tub-download]")
    with page.expect_download() as one:
        page.keyboard.press("Enter")
    assert Path(one.value.path()).read_bytes() == world.built[-1]
    expect(page.locator("[data-tub-download-message]")).to_have_text(
        "Downloaded 1 card. Open the file in Word."
    )

    pilot.tab_to("button[data-tub-cart-add]")
    page.keyboard.press("Enter")
    expect(page.locator("[data-tub-cart]")).to_be_visible()
    expect(page.locator("button[data-tub-cart-add]")).to_have_text("Remove from cart")
    pilot.check_page()
    page.goto(pilot.origin + world.card_path("picture"))
    page.get_by_role("button", name="Add to cart").click()
    expect(page.locator("[data-tub-cart-count]")).to_have_text("2 cards")

    pilot.tab_to("button[data-tub-cart-download]", backwards=True)
    page.keyboard.press("Enter")
    message = page.locator("[data-tub-cart-message]")
    expect(message).to_contain_text("Some cards cannot be downloaded.")
    expect(message.locator("li")).to_have_text(
        "Card 2, Andesite slopes hold snow: It holds a picture, a table, a text box or a footnote that "
        "cannot be copied exactly. Copy card copies its text."
    )
    pilot.check_page()
    with page.expect_download() as rest:
        message.get_by_role("button", name="Remove these from the cart and download the rest").click()
    assert Path(rest.value.path()).read_bytes() == world.built[-1]
    expect(page.locator("[data-tub-cart-count]")).to_have_text("1 card")
    expect(message).to_have_text("Downloaded 1 card. Open the file in Word.")

    page.get_by_role("button", name="Empty the cart").click()
    expect(page.locator("[data-tub-cart]")).to_be_hidden()
    assert pilot.foreign == []
    actions = [record.action.value for record in world.audit.records]
    assert actions.count("cards-downloaded") == 2, actions
