# /// script
# requires-python = ">=3.11"
# ///
"""Check every relative Markdown link and `#anchor` in the repository, offline.

Replaces the ad-hoc `linkcheckmd` run used in v1-e01-t06, which walked one directory at a time and
did not look at anchors at all — so a link to a heading that had been renamed still passed.

What it checks, for every Markdown file `git ls-files` reports:
  * a relative link target (`../adr/0010-primary-aws-region.md`, `plan_specs/`) exists on disk
  * a `#anchor` matches a GitHub-style heading slug in the file it points at, including the
    `-1`, `-2` suffixes GitHub gives repeated headings
  * nothing resolves to a path outside the repository

What it deliberately does not check, because something else does or nothing can:
  * `http(s)://`, `mailto:` and other absolute URLs — that would need the network
  * root-absolute targets such as `/events/`, which are website routes rather than files; the
    site's own suite checks those against the published pages (site/tests/content.test.ts and
    site/tests/routes.test.ts)
  * targets holding a `{{PLACEHOLDER}}`, which are filled in when a template is used
  * links inside fenced code blocks, inline code spans and HTML comments, which are not links
  * anchors into files that are not Markdown, whose headings this script cannot read

Shortcut and collapsed reference links (`[text][label]`) are not resolved; no file in this
repository uses them. Reference *definitions* (`[label]: target`) are checked like inline links.

Usage:
  uv run scripts/check_links.py              # check the whole repository
  uv run scripts/check_links.py --root DIR   # check the Markdown under another root
  uv run scripts/check_links.py --list       # list the files that would be checked
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)
# Directories a fallback walk skips when git is not available to list the tracked files.
UNTRACKED_DIRS = {".git", ".venv", "node_modules", "dist", "build", ".next", "coverage", "__pycache__"}

FENCE = re.compile(r"^(?P<indent> {0,3})(?P<marker>`{3,}|~{3,})(?P<info>.*)$")
CODE_SPAN = re.compile(r"(?P<ticks>`+)(?P<body>.+?)(?P=ticks)")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
ATX_HEADING = re.compile(r"^ {0,3}(?P<hashes>#{1,6})\s+(?P<text>.*?)\s*#*\s*$")
HTML_ANCHOR = re.compile(r"<a\b[^>]*\b(?:name|id)=[\"'](?P<anchor>[^\"']+)[\"']", re.IGNORECASE)
# `[text](target)` and `![alt](target)`, with an optional "title" and an optional <> around target.
INLINE_LINK = re.compile(
    r"!?\[(?P<text>[^\]]*)\]\(\s*(?P<target><[^>]*>|[^\s)]*)(?:\s+[\"'][^)]*[\"'])?\s*\)"
)
REFERENCE_DEFINITION = re.compile(r"^ {0,3}\[(?P<label>[^\]]+)\]:\s*(?P<target><[^>]*>|\S+)", re.MULTILINE)
# Everything github-slugger strips: ASCII punctuation except `-` and `_`, plus Unicode punctuation.
ASCII_PUNCTUATION = re.compile(r"[\x00-\x1f!-,./:-@\[-^`{-~]")
# Inline markup that contributes no characters to a heading's slug.
MARKDOWN_EMPHASIS = re.compile(r"[*_]{1,3}(?P<text>[^*_]+)[*_]{1,3}")
HTML_TAG = re.compile(r"<[^>]+>")


def slugify(heading: str) -> str:
    """The anchor GitHub gives a heading: lowercase, punctuation dropped, spaces hyphenated."""
    text = ASCII_PUNCTUATION.sub("", heading.lower())
    text = "".join("" if is_unicode_punctuation(c) else c for c in text)
    return text.strip().replace(" ", "-")


def is_unicode_punctuation(char: str) -> bool:
    if char in "-_":
        return False
    return unicodedata.category(char).startswith("P") or " " <= char <= "⁯"


def heading_text(raw: str) -> str:
    """A heading line's visible text: links become their text, code and emphasis lose their marks."""
    text = INLINE_LINK.sub(lambda m: m["text"], raw)
    text = CODE_SPAN.sub(lambda m: m["body"], text)
    text = MARKDOWN_EMPHASIS.sub(lambda m: m["text"], text)
    return HTML_TAG.sub("", text).strip()


def without_code_blocks(text: str) -> str:
    """The text with fenced code blocks and HTML comments blanked out, line numbers intact.

    Code *spans* survive, because a span inside a heading still contributes its text to the
    heading's anchor: `## The \\`verify\\` command` is reached as `#the-verify-command`.
    """
    text = HTML_COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m[0]), text)
    lines = text.split("\n")
    open_fence: str | None = None
    for index, line in enumerate(lines):
        fence = FENCE.match(line)
        if open_fence is not None:
            lines[index] = ""
            closes = fence and fence["marker"][0] == open_fence[0] and len(fence["marker"]) >= len(open_fence)
            if closes:
                open_fence = None
            continue
        if fence:
            open_fence = fence["marker"]
            lines[index] = ""
            continue
    return "\n".join(lines)


def without_code(text: str) -> str:
    """The text with code blocks, code spans and HTML comments blanked out, line numbers intact."""
    return CODE_SPAN.sub(lambda m: " " * len(m[0]), without_code_blocks(text))


def anchors_in(text: str) -> set[str]:
    """Every anchor a Markdown file offers: heading slugs (deduplicated as GitHub does) and <a id>."""
    found: set[str] = set()
    seen: dict[str, int] = {}
    for line in without_code_blocks(text).split("\n"):
        heading = ATX_HEADING.match(line)
        if heading:
            slug = slugify(heading_text(heading["text"]))
            if not slug:
                continue
            count = seen.get(slug, 0)
            seen[slug] = count + 1
            found.add(slug if count == 0 else f"{slug}-{count}")
    found.update(m["anchor"] for m in HTML_ANCHOR.finditer(text))
    return found


@dataclass(frozen=True)
class Link:
    line: int
    target: str


def links_in(text: str) -> list[Link]:
    """Every link in the file, with the line it starts on.

    The scan is over the whole document rather than line by line, because Markdown lets a link's
    text wrap across lines; what it may not contain is a blank line, so a match holding one is a
    stray bracket rather than a link.
    """
    stripped = without_code(text)
    found: list[Link] = []
    for match in INLINE_LINK.finditer(stripped):
        if "\n\n" in match["text"]:
            continue
        found.append(Link(stripped.count("\n", 0, match.start()) + 1, match["target"].strip("<>")))
    for match in REFERENCE_DEFINITION.finditer(stripped):
        found.append(Link(stripped.count("\n", 0, match.start()) + 1, match["target"].strip("<>")))
    return sorted(found, key=lambda link: link.line)


def is_checkable(target: str) -> bool:
    if not target or target.startswith(("#", "/")):
        return bool(target.startswith("#"))
    return not (SCHEME.match(target) or "{{" in target or "}}" in target)


def tracked_markdown(root: Path) -> list[Path]:
    """Every tracked Markdown file, or every Markdown file found by walking if git cannot say."""
    try:
        listed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--", "*.md", "*.markdown"],
            capture_output=True,
            check=True,
            text=True,
        ).stdout
        return sorted(root / name for name in listed.split("\0") if name)
    except (OSError, subprocess.CalledProcessError):
        return sorted(
            p for p in root.rglob("*.md") if not UNTRACKED_DIRS.intersection(p.relative_to(root).parts)
        )


def check_file(path: Path, root: Path, anchor_cache: dict[Path, set[str]]) -> list[str]:
    where = path.relative_to(root).as_posix()
    problems: list[str] = []
    for link in links_in(path.read_text(encoding="utf-8")):
        if not is_checkable(link.target):
            continue
        location, _, anchor = link.target.partition("#")
        target = (path.parent / unquote(location)).resolve() if location else path
        prefix = f"{where}:{link.line}: {link.target}"
        if not target.exists():
            problems.append(f"{prefix} does not exist")
            continue
        if root not in target.parents and target != root:
            problems.append(f"{prefix} resolves outside the repository")
            continue
        if not anchor or target.suffix.lower() not in {".md", ".markdown"}:
            continue
        if target not in anchor_cache:
            anchor_cache[target] = anchors_in(target.read_text(encoding="utf-8"))
        if unquote(anchor) not in anchor_cache[target]:
            problems.append(f"{prefix} has no heading matching #{anchor}")
    return problems


def check(root: Path, paths: list[Path] | None = None) -> list[str]:
    """Every broken link under root, as one message per link, in file and line order."""
    files = paths if paths is not None else tracked_markdown(root)
    anchor_cache: dict[Path, set[str]] = {}
    return [problem for path in files for problem in check_file(path, root, anchor_cache)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=ROOT, help="repository root to check")
    ap.add_argument("--list", action="store_true", help="list the Markdown files instead of checking")
    args = ap.parse_args(argv)

    root = args.root.resolve()
    files = tracked_markdown(root)
    if args.list:
        print("\n".join(p.relative_to(root).as_posix() for p in files))
        return 0

    problems = check(root, files)
    if problems:
        print("\n".join(problems))
        print(f"\n{len(problems)} broken link(s) in {len(files)} Markdown files", file=sys.stderr)
        return 1
    checked = sum(
        1
        for path in files
        for link in links_in(path.read_text(encoding="utf-8"))
        if is_checkable(link.target)
    )
    print(f"OK: {checked} relative links and anchors in {len(files)} Markdown files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
