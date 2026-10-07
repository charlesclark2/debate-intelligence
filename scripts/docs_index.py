"""Regenerate the document table in docs/README.md from the documents under docs/.

Everything between the BEGIN/END GENERATED markers in docs/README.md is rewritten; the hand-written
text around it is preserved. The output depends only on the files under docs/, so running it twice
in a row produces no second diff. Written by v1-e01-t16-generated-docs-index, on the model of
scripts/spec_index.py.

Where a row's description comes from: the document's own first line, which must be a single-line
HTML comment of exactly this form, invisible when the Markdown is rendered:

    <!-- docs-index: <one-line description> -->

The description is copied into the table verbatim, so it is Markdown, and a literal pipe must be
written `\\|` or it would split the table cell. Nothing in this script supplies or overrides a
description. A document whose first line is not such a comment fails the generator, and every
mode of it, with a message naming the file.

Which files get a row:

* Every `*.md` file under docs/ except docs/README.md itself, which is the index.
* A directory with its own README.md is indexed by that README alone, as one row linking
  `<dir>/` to it, and nothing beneath it is listed or needs a comment. That is how docs/adr/
  and docs/session-reports/ appear: each keeps its own index, and their individual records are
  not repeated here.
* Hidden files and directories (a leading `.`) are skipped; files that are not Markdown are not
  documents.

Rows are ordered by the path of the file they link to, so where a new document's row lands is
decided by its path and not by whoever adds it.

Who runs this: nobody in a task. .github/workflows/refresh-generated-files.yml runs it, with
scripts/spec_index.py, on every push to dev and opens or updates one pull request with the result,
so concurrent task PRs never touch docs/README.md and never conflict on it. A task that adds a
document gives it the comment above, and `--check-descriptions` in CI holds it to that on every
pull request. `--check` is required where spec_index.py's is, on pull requests into main.

Usage:
  uv run scripts/docs_index.py                       # rewrite docs/README.md
  uv run scripts/docs_index.py --check               # exit 1 if docs/README.md is stale, without writing
  uv run scripts/docs_index.py --check-descriptions  # exit 1 if a document has no description; never
                                                     # compares with the committed index
  uv run scripts/docs_index.py --root DIR            # work on DIR/docs instead of this repository's
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEGIN, END = "<!-- BEGIN GENERATED -->", "<!-- END GENERATED -->"
INDEX = "README.md"
DESCRIPTION = re.compile(r"<!-- docs-index: (?P<text>.*?) -->")
# A pipe not preceded by a backslash ends a table cell.
UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")


class MissingDescription(Exception):
    """One or more documents have no usable description; the message names every one of them."""


@dataclass(frozen=True)
class Row:
    label: str  # what the reader sees: the path, or `<dir>/` for a directory with a README
    target: str  # the file the row links to, relative to docs/
    description: str

    def render(self) -> str:
        return f"| [{self.label}]({self.target}) | {self.description} |"


def description_of(path: Path, shown_as: str) -> str:
    """The document's description, or a ValueError saying what is wrong with its first line."""
    lines = path.read_text(encoding="utf-8").splitlines()
    first = lines[0].strip() if lines else ""
    match = DESCRIPTION.fullmatch(first)
    if match is None:
        elsewhere = next((n for n, line in enumerate(lines, 1) if "<!-- docs-index:" in line), None)
        where = f"; it is on line {elsewhere}" if elsewhere else ""
        raise ValueError(
            f"{shown_as}: the first line must be `<!-- docs-index: <one-line description> -->`{where}"
        )
    text = match["text"].strip()
    if not text:
        raise ValueError(f"{shown_as}: the docs-index description is empty")
    if UNESCAPED_PIPE.search(text):
        raise ValueError(f"{shown_as}: write `|` as `\\|` in the description, or it splits the table")
    return text


def indexed_files(docs: Path) -> list[tuple[str, str, Path]]:
    """(label, target, file) for every row, before descriptions are read, in no particular order."""
    found: dict[str, tuple[str, str, Path]] = {}
    for path in docs.rglob("*.md"):
        relative = path.relative_to(docs)
        if any(part.startswith(".") for part in relative.parts) or relative.as_posix() == INDEX:
            continue
        # The outermost directory between docs/ and this file that has its own README stands for it.
        parents = list(reversed(relative.parents))[1:]  # outermost first, docs/ itself left out
        owner = next((d for d in parents if (docs / d / INDEX).is_file()), None)
        if owner is None:
            found[relative.as_posix()] = (relative.as_posix(), relative.as_posix(), path)
        else:
            target = (owner / INDEX).as_posix()
            found[target] = (f"{owner.as_posix()}/", target, docs / owner / INDEX)
    return list(found.values())


def rows(docs: Path) -> list[Row]:
    """Every row of the table, ordered by the path each one links to."""
    result, problems = [], []
    for label, target, path in sorted(indexed_files(docs), key=lambda found: found[1]):
        try:
            result.append(Row(label, target, description_of(path, f"docs/{path.relative_to(docs).as_posix()}")))
        except ValueError as exc:
            problems.append(str(exc))
    if problems:
        raise MissingDescription("\n".join(problems))
    return result


def render(root: Path) -> str:
    """The generated section, markers included."""
    table = ["| Where | What |", "|---|---|", *(row.render() for row in rows(root / "docs"))]
    return "\n".join([BEGIN, "", *table, "", END])


def rewritten(index: Path, root: Path) -> str:
    """The index text with the generated section replaced, raising if the markers are missing."""
    text = index.read_text(encoding="utf-8")
    for marker in (BEGIN, END):
        if marker not in text:
            raise LookupError(f"docs/{INDEX} has no {marker} marker")
    head, _, rest = text.partition(BEGIN)
    _, _, tail = rest.partition(END)
    return head + render(root) + tail


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="report staleness instead of rewriting")
    mode.add_argument(
        "--check-descriptions",
        action="store_true",
        help="only check that every document has a description; never compares with the index",
    )
    ap.add_argument("--root", type=Path, default=ROOT, help="repository root holding docs/")
    args = ap.parse_args(argv)

    root = args.root.resolve()
    if args.check_descriptions:
        try:
            count = len(rows(root / "docs"))
        except MissingDescription as exc:
            print(exc, file=sys.stderr)
            return 1
        print(f"All {count} indexed documents under docs/ have a description")
        return 0

    index = root / "docs" / INDEX
    if not index.exists():
        print(f"{index} does not exist", file=sys.stderr)
        return 2
    try:
        new = rewritten(index, root)
    except MissingDescription as exc:
        print(exc, file=sys.stderr)
        return 1
    except LookupError as exc:
        print(exc, file=sys.stderr)
        return 2

    current = index.read_text(encoding="utf-8")
    if args.check:
        if new != current:
            print(
                f"docs/{INDEX} is stale. On dev, merge the open 'Refresh generated files' pull request; "
                "outside a task, `uv run scripts/docs_index.py` rewrites it",
                file=sys.stderr,
            )
            print(stale_diff(current, new), file=sys.stderr, end="")
            return 1
        print(f"docs/{INDEX} is up to date")
        return 0
    if new == current:
        print(f"docs/{INDEX} is already up to date")
        return 0
    index.write_text(new, encoding="utf-8")
    print(f"docs/{INDEX} updated")
    return 0


def stale_diff(current: str, new: str) -> str:
    """The rows that differ, as a unified diff from the committed index to the generated one."""
    return "".join(
        difflib.unified_diff(
            current.splitlines(keepends=True),
            new.splitlines(keepends=True),
            f"docs/{INDEX} (committed)",
            f"docs/{INDEX} (generated)",
            n=0,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
