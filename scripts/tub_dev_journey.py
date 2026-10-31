"""The student search pilot's signed-in journey on dev, run by the operator (`v1-e39-t10`).

validate-dev checks dev with no account (`tests/smoke/cloud`). What only a signed-in debater sees is
checked here, by the operator, in a Chromium window this script opens: sign in, search, open a card,
Copy card, download it, and, after a removal, the removed card gone. **The operator signs in by
hand**, on managed login's own page, with a dev account and the authenticator code the page asks
for. Nothing here holds a password, a TOTP seed or a session: the window's profile is a new one, and
it is deleted when the script ends.

Three commands. `docs/runbooks/evidence-search.md` ("The signed-in journey on dev") says when each
runs, and every block around them.

``seed --out <directory>``
    Writes the dev seed: one weekly archive of the synthetic caselist `testcl26`, three files from three
    invented schools, each a structural fixture the repository already holds
    (`tests/fixtures/debate_files/structural/`, synthetic, written by
    `scripts/generate_structural_fixtures.py`). No real disclosure is in it. The same bytes every time
    (stored, not compressed, with fixed dates), so importing it again is an import of the same week.
    It prints each file's sha256, and which one the journey's removal takes. It reaches nothing.
``journey [--base-url URL]``
    Opens Chromium on the pilot and waits for the operator to sign in. Then searches the seed's words
    in `testcl26`, opens the card only the removable file holds, checks its provenance line, copies it
    (the clipboard's HTML and text hold the tag and no provenance line, data-use policy 1.11), downloads
    it (a `.docx` whose text holds the tag; the file is deleted), and prints the card's path.
``removed --card-path /cards/testcl26/<cluster id> [--base-url URL]``
    After the removal: the card's page says it is not in the search, and searching its words in
    `testcl26` no longer lists it.

Each step prints `PASS <step>` or `FAIL <step>: <why>`, and the first failure ends the run with exit
status 1. What is printed is the seed's own synthetic words, paths and digests, and nothing else.

`packages/debate_api/tests/browser/test_tub_dev_journey.py` runs the journey and the removed check
against the app in-process, in Chromium, with a session planted in place of the sign-in.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import shutil
import sys
import tempfile
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import urlencode, urlsplit

if TYPE_CHECKING:  # pragma: no cover - Playwright is imported only by the commands that drive a browser
    from playwright.sync_api import BrowserContext, Page

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
STRUCTURAL: Final = REPO_ROOT / "tests" / "fixtures" / "debate_files" / "structural"
DEV_PILOT_URL: Final = "https://tub.dev.wfbdebate.com/"

SEED_CASELIST: Final = "testcl26"
"""A slug `tub index build` accepts (`testcl` is in `EVENTS_BY_SLUG_PREFIX`, v1-e39-t22), that no
weekly run follows (`caselist.sync_caselists`), so no run imports into it, indexes it or reports it."""

SEED_SNAPSHOT: Final = "2026-10-27"
"""After dev's newest `testcl26` week (2026-09-29, `RM-2026-90`'s), so the import is in order."""


@dataclass(frozen=True)
class SeedFile:
    path: str
    """Where the archive files it: `<school>/<team code>/<school>-<code>-<side>-<tournament>-<round>.docx`."""
    fixture: str
    """The structural fixture it is."""
    removed: bool = False
    """The file the journey's removal takes."""


SEED_FILES: Final = (
    SeedFile(
        "Quillfern Academy/QfAn/Quillfern Academy-QfAn-Aff-Lanternfield Invitational-Round 1.docx",
        "cardmirror-camp-file",
        removed=True,
    ),
    SeedFile(
        "Ostrander Vale/OvTe/Ostrander Vale-OvTe-Neg-Lanternfield Invitational-Round 2.docx",
        "team-verbatim-file",
    ),
    SeedFile(
        "Brindlecote High/BrHo/Brindlecote High-BrHo-Aff-Lanternfield Invitational-Round 3.docx",
        "cardmirror-caselist-upload",
    ),
)
"""Three invented schools, none of the names `RM-2026-90`'s synthetic `testcl26` used. The removed
file alone holds the card the journey opens; the other card is in all three files, so after the
removal it stays, without the removed team's line."""


@dataclass(frozen=True)
class JourneyCard:
    """What the journey searches for and expects to open."""

    words: str
    caselist: str
    tag: str


SEED_CARD: Final = JourneyCard(
    words="planning standard",
    caselist=SEED_CASELIST,
    tag="Reserve margins are already below the planning standard",
)
"""The second card of `cardmirror-camp-file`, written by hand from its `.expected.json`."""

SIGN_IN_WAIT_SECONDS: Final = 300
STEP_TIMEOUT_MS: Final = 30_000
_ZIP_DATE: Final = (2026, 10, 27, 0, 0, 0)


class JourneyFailed(Exception):
    """A step did not see what it should; the message says what it saw."""


# --------------------------------------------------------------------------------------------
# seed
# --------------------------------------------------------------------------------------------


def seed_archive_name() -> str:
    return f"{SEED_CASELIST}-{SEED_SNAPSHOT}.zip"


def seed_archive_bytes(structural: Path = STRUCTURAL) -> bytes:
    """The weekly archive, the same bytes on every run: stored members, fixed dates, a fixed order."""
    folder = f"{SEED_CASELIST}-{SEED_SNAPSHOT[5:].replace('-', '')}"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for one in sorted(SEED_FILES, key=lambda seed: seed.path):
            member = zipfile.ZipInfo(f"{folder}/{one.path}", date_time=_ZIP_DATE)
            member.external_attr = 0o644 << 16
            archive.writestr(member, (structural / f"{one.fixture}.docx").read_bytes())
    return buffer.getvalue()


def write_seed(out: Path, structural: Path = STRUCTURAL) -> list[str]:
    """Write the archive into `out` and say what is in it."""
    out.mkdir(parents=True, exist_ok=True)
    archive = out / seed_archive_name()
    content = seed_archive_bytes(structural)
    archive.write_bytes(content)
    lines = [
        f"archive {archive}",
        f"archive sha256 {hashlib.sha256(content).hexdigest()}",
        f"caselist {SEED_CASELIST}, snapshot {SEED_SNAPSHOT}",
    ]
    for one in SEED_FILES:
        digest = hashlib.sha256((structural / f"{one.fixture}.docx").read_bytes()).hexdigest()
        lines.append(f"{'remove ' if one.removed else 'keep   '}{digest}  {one.path}")
    return lines


# --------------------------------------------------------------------------------------------
# journey and removed: a signed-in browser on the pilot
# --------------------------------------------------------------------------------------------

Say = Callable[[str], None]


def origin_of(base_url: str) -> str:
    parts = urlsplit(base_url)
    return f"{parts.scheme}://{parts.netloc}"


def search_url(origin: str, card: JourneyCard) -> str:
    return f"{origin}/search?{urlencode({'q': card.words, 'caselist': card.caselist})}"


def step(say: Say, name: str, passed: bool, why: str) -> None:
    if not passed:
        say(f"FAIL {name}: {why}")
        raise JourneyFailed(f"{name}: {why}")
    say(f"PASS {name}")


def wait_for_sign_in(page: Page, base_url: str, say: Say, *, seconds: int = SIGN_IN_WAIT_SECONDS) -> None:
    """Open the pilot and wait until the operator has signed in and is back on it."""
    origin = origin_of(base_url)
    page.goto(origin + "/")
    say(
        "Sign in in the Chromium window: your dev username, your password, then the code your "
        f"authenticator app shows. Waiting up to {seconds // 60} minutes."
    )
    page.wait_for_url(
        lambda url: url.startswith(origin + "/") and "/auth/" not in url, timeout=seconds * 1000
    )
    signed_in = page.get_by_text("Signed in as")
    signed_in.wait_for(timeout=STEP_TIMEOUT_MS)
    step(say, "sign in", signed_in.is_visible(), f"back on {page.url} without 'Signed in as'")


def run_journey(
    page: Page, context: BrowserContext, base_url: str, card: JourneyCard, downloads: Path, say: Say
) -> str:
    """Search, open the card, Copy card, download. Returns the card's path, for the removed check."""
    origin = origin_of(base_url)

    # The results page by its address, as the form sends it. The empty search page never waits for the
    # index, so in an environment that has not loaded one yet its caselist list is empty.
    page.goto(search_url(origin, card))
    result = page.locator(".result-tag a", has_text=card.tag)
    count = page.locator(".result-count")
    step(
        say, "search", result.count() == 1, f"{result.count()} results tagged {card.tag!r} for {card.words!r}"
    )
    step(say, "result count", count.count() == 1, "no result count above the results")

    result.click()
    page.wait_for_url(lambda url: "/cards/" in url, timeout=STEP_TIMEOUT_MS)
    path = urlsplit(page.url).path
    tag = page.locator("h1#card-tag").inner_text()
    step(say, "open the card", tag == card.tag, f"the card page's tag is {tag!r}")
    provenance = page.locator("p.provenance")
    first_line = provenance.first.inner_text() if provenance.count() else ""
    step(
        say,
        "provenance on the card page",
        first_line.startswith(f"[Disclosed: {card.caselist} "),
        f"the provenance line reads {first_line!r}",
    )
    back = page.get_by_role("link", name="Back to results")
    step(say, "back link", back.count() == 1, "no 'Back to results' link")

    page.get_by_role("button", name="Copy card").click()
    message = page.locator("[data-tub-copy-message]")
    # app.js says "Copying the card" while the copy is fetched, then what happened.
    page.wait_for_function(
        """() => {
            const said = (document.querySelector("[data-tub-copy-message]") || {}).textContent || "";
            return said !== "" && !said.startsWith("Copying");
        }""",
        timeout=STEP_TIMEOUT_MS,
    )
    said = message.inner_text()
    step(say, "Copy card", said.startswith("Copied."), f"the page said {said!r}")
    context.grant_permissions(["clipboard-read", "clipboard-write"], origin=origin)
    clipboard: dict[str, Any] = page.evaluate(
        """async () => {
            const [item] = await navigator.clipboard.read();
            const html = await (await item.getType("text/html")).text();
            const text = await (await item.getType("text/plain")).text();
            return { html, text };
        }"""
    )
    step(say, "the copy holds the card", card.tag in clipboard["text"], "the copied text has no tag")
    step(
        say,
        "no provenance line in the copy",
        "[Disclosed" not in clipboard["html"] and "[Disclosed" not in clipboard["text"],
        "the copy carries a provenance line (data-use policy 1.11)",
    )

    with page.expect_download(timeout=STEP_TIMEOUT_MS) as downloading:
        page.get_by_role("button", name="Download .docx").click()
    saved = downloads / "downloaded.docx"
    downloading.value.save_as(saved)
    try:
        name = downloading.value.suggested_filename
        with zipfile.ZipFile(saved) as docx:
            document = docx.read("word/document.xml").decode("utf-8")
        words_found = all(word in document for word in card.tag.split())
    except (zipfile.BadZipFile, KeyError) as problem:
        name, words_found = downloading.value.suggested_filename, False
        say(f"the download is not a .docx: {type(problem).__name__}")
    finally:
        saved.unlink(missing_ok=True)
    step(
        say,
        "download",
        name.endswith(".docx") and words_found,
        f"{name!r}, the tag's words in it: {words_found}",
    )

    say(f"card path {path}")
    return path


def check_removed(page: Page, base_url: str, card_path: str, card: JourneyCard, say: Say) -> None:
    """The removed card's page says it is gone, and a search for its words lists it no more."""
    origin = origin_of(base_url)
    answer = page.goto(origin + card_path)
    heading = page.locator("h1").first.inner_text()
    step(
        say,
        "the removed card's page",
        answer is not None and answer.status == 404 and heading == "That card is not in the search",
        f"{answer.status if answer else 'no answer'}, {heading!r}",
    )
    page.goto(search_url(origin, card))
    listed = page.locator(f'.result-tag a[href^="{card_path}"]').count()
    step(say, "the removed card is not in the results", listed == 0, f"listed {listed} times")


@contextmanager
def chromium(*, headless: bool = False) -> Iterator[tuple[BrowserContext, Page, Path]]:
    """A new Chromium profile in a temporary directory, deleted afterwards, and a directory for downloads."""
    from playwright.sync_api import sync_playwright

    scratch = Path(tempfile.mkdtemp(prefix="tub-journey-"))
    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(scratch / "profile"), headless=headless, accept_downloads=True
            )
            try:
                yield context, context.pages[0] if context.pages else context.new_page(), scratch
            finally:
                context.close()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    seed = sub.add_parser("seed", help="write the dev seed's weekly archive of testcl26")
    seed.add_argument("--out", type=Path, required=True)
    journey = sub.add_parser("journey", help="sign in, search, open, copy and download the seed's card")
    journey.add_argument("--base-url", default=DEV_PILOT_URL)
    removed = sub.add_parser("removed", help="after the removal: the seed's card is gone")
    removed.add_argument("--card-path", required=True, help="what the journey printed as 'card path'")
    removed.add_argument("--base-url", default=DEV_PILOT_URL)
    return ap


def main(argv: list[str] | None = None, *, say: Say = print) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "seed":
        for line in write_seed(args.out):
            say(line)
        return 0
    if args.command == "removed" and not args.card_path.startswith(f"/cards/{SEED_CASELIST}/"):
        say(f"FAIL removed: {args.card_path!r} is not a card path in {SEED_CASELIST}")
        return 2
    try:
        with chromium() as (context, page, scratch):
            wait_for_sign_in(page, args.base_url, say)
            if args.command == "journey":
                run_journey(page, context, args.base_url, SEED_CARD, scratch, say)
            else:
                check_removed(page, args.base_url, args.card_path, SEED_CARD, say)
    except JourneyFailed:
        return 1
    say(f"{args.command}: every step passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
