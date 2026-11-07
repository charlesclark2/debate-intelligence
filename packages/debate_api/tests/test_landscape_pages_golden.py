"""Every landscape page, byte for byte, as `fixtures/landscape_pages_golden/pages/` holds it (`v1-e32-t57`).

`v1-e32-t57` moved the Markdown cut and render of a bundle from `debate_api.landscape_markdown` into
`debate_core.arguments.landscape.pages`, unchanged, so that the report's page-size check and the pilot
measure the same bytes (the PM's ruling of 2026-11-07, Q4). These pages were written by the pilot
before the move, at the commit that added this file, and the test holds every page to them after it.
They are not expectations of what a page should say, which the other landscape tests write by hand
(working agreement 6), but of what the move must not change.

Three sets of bundles, every page of each, links followed from the front pages:

* the pilot's own fixtures (`fixtures/landscape/`), the newest snapshot of each caselist;
* `debate_core`'s golden bundle (`tests/fixtures/landscape/golden/`), as the report writes it;
* `fixtures/landscape_pages_golden/input/`: headings and text that test escaping, anchors and links.

The session's CSRF token and the digest in an asset's address are masked: neither is the renderer's.
A change that means to change a page writes the files again with `LANDSCAPE_PAGES_GOLDEN_WRITE=1`,
which always fails, and its diff is read in review.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Final

import pytest

HERE: Final = Path(__file__).resolve().parent
GOLDEN: Final = HERE / "fixtures" / "landscape_pages_golden"
CORE_GOLDEN: Final = HERE.parents[2] / "tests" / "fixtures" / "landscape" / "golden"
WRITE: Final = os.environ.get("LANDSCAPE_PAGES_GOLDEN_WRITE") == "1"
_CSRF: Final = re.compile(r'(<meta name="tub-csrf" content=")[^"]*(")')
_ASSET: Final = re.compile(r"/static/[0-9a-f]+/")
_LANDSCAPE_HREF: Final = re.compile(r'href="(/landscape/[^"#]*)"')


def _tricky() -> dict[str, bytes]:
    root = GOLDEN / "input"
    return {
        f"reports/landscape/{path.relative_to(root).as_posix()}": path.read_bytes()
        for path in sorted(root.rglob("*.md"))
    }


def _core() -> dict[str, bytes]:
    return {
        f"reports/landscape/synthpolicy26/2026-09-15/{name}": (CORE_GOLDEN / name).read_bytes()
        for name in ("report.md", "schools.md")
    }


BUNDLES: Final = {"fixtures": None, "core": _core, "tricky": _tricky}


def _masked(text: str) -> str:
    return _ASSET.sub("/static/<digest>/", _CSRF.sub(r"\1<masked>\2", text))


def _pages(world: Any) -> dict[str, str]:
    """Every page reached from `/landscape`, by path, with each school view and two pages not found."""
    seen: dict[str, str] = {}
    waiting = ["/landscape"]
    while waiting:
        path = waiting.pop(0)
        if path in seen:
            continue
        response = world.browser.get(path)
        seen[path] = f"{response.status_code}\n{_masked(response.text)}"
        waiting += [found for found in _LANDSCAPE_HREF.findall(response.text) if found not in seen]
    for caselist in sorted({path.split("/")[2] for path in seen if path.count("/") >= 2}):
        for missing in (
            f"/landscape/{caselist}/schools",
            f"/landscape/{caselist}/schools/no-such-school",
            f"/landscape/{caselist}/report/no-such-part",
        ):
            if missing in seen:
                continue
            response = world.browser.get(missing)
            seen[missing] = f"{response.status_code}\n{_masked(response.text)}"
    return seen


def _file(bundles: str, path: str) -> Path:
    return GOLDEN / "pages" / bundles / (path.strip("/").replace("/", "__") + ".html")


@pytest.mark.parametrize("bundles", sorted(BUNDLES))
def test_every_landscape_page_is_byte_for_byte_its_golden_page(
    make_landscape_world: Any, landscape_store: Any, bundles: str
) -> None:
    files = BUNDLES[bundles]
    world = (
        make_landscape_world()
        if files is None
        else make_landscape_world(landscape_objects=landscape_store(files()))
    )
    world.signed_in_student()
    try:
        pages = _pages(world)
    finally:
        world.services.search_index.close()
    if WRITE:
        directory = GOLDEN / "pages" / bundles
        directory.mkdir(parents=True, exist_ok=True)
        for old in directory.glob("*.html"):
            old.unlink()
        for path, text in pages.items():
            _file(bundles, path).write_text(text, encoding="utf-8")
        pytest.fail(
            f"wrote {len(pages)} golden pages for {bundles}; run again without LANDSCAPE_PAGES_GOLDEN_WRITE"
        )
    written = sorted(path.name for path in (GOLDEN / "pages" / bundles).glob("*.html"))
    assert sorted(_file(bundles, path).name for path in pages) == written
    for path, text in pages.items():
        assert text == _file(bundles, path).read_text(encoding="utf-8"), path
