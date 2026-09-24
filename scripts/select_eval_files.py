#!/usr/bin/env python3
"""Propose the parser evaluation's file selection, from files that stay where they are.

`v1-e31-t05-parser-eval` labels about thirty real files: team files, caselist uploads and camp
files. **None of them enters the repository**, scrubbed or otherwise (`caselist-data-use.md`
prohibitions 1, 9 and 10). This script walks the folders that hold them, reads each `.docx`'s
bytes and style information (never its text), and proposes a stratified selection that meets
Goal criterion ac1. It writes two things:

* `tests/fixtures/debate_files/eval/manifest.json` — committed. Each file by **keyed digest**,
  category, season, format and template family, and whether it is in the six-file PR subset. **No
  file name, path, school or team code, and no plain SHA-256**: this repository is public and the
  caselist archives are public, so a plain digest is a join key straight back to
  `<School>/<TeamCode>/<filename>`. Digests are HMAC-SHA256 under a key kept beside the path map
  and never committed (`tests/evals/parser/digests.py`).
* the **path map** — keyed digest to local path, which is how the evaluation finds each file again.
  It names schools and team codes, so it is written outside the repository
  (`~/.debate-intelligence/parser-eval-paths.json`, or `$DEBATE_PARSER_EVAL_PATHS`) and the script
  refuses a location inside it.

What it prints is counts. It never prints a path or a file name.

**The selection is a proposal.** The coach approves it before anyone labels a file (the
`collect-files` node's manual criterion). Re-running it with the same folders, options and key
produces the same selection: candidates are ordered by their keyed digest, which is stable and has
nothing to do with who wrote a file or what it is called.

**`--rekey` re-keys the files already in the manifest** instead of choosing new ones: it reads the
existing manifest, finds each file through the old path map, and rewrites the manifest and the path
map under the digest key, keeping the same files, the same PR subset and the same metadata. That is
how a manifest written under plain SHA-256 is repaired without re-running the choice.

## How the fields are decided

* **category** — from the `CATEGORY=PATH` input the file was found under.
* **season** — from the nearest folder named like `2025-2026`.
* **format** — from the outermost folder whose name says LD, PF or Policy (`LD Debate`,
  `Public Forum`, `PFD`, `Policy Debate`, a caselist snapshot folder `hsld26-0915`). For caselist
  and camp files only the input folder and its parents are read: the folders below them are
  schools and team codes.
* **template family** — `scripts/survey_docx_styles.py`'s classifier, from style references.

A file whose season or format cannot be read from its folders is skipped and counted.

## Running it

    uv run python scripts/select_eval_files.py \\
      --input "team=$HOME/Documents/debate/2024-2025" \\
      --input "team=$HOME/Documents/debate/2025-2026" \\
      --input "team=$HOME/Documents/debate/2026-2027" \\
      --input "caselist=$HOME/Documents/debate/2026-2027/LD Debate/Opencaselist/hsld26-0915" \\
      --input "camp=$HOME/Documents/debate/2026-2027/Policy Debate/Camp Files" \\
      --exclude-dir Opencaselist --exclude-dir "Camp Files"

`--exclude-dir` keeps the caselist and camp folders that sit inside a season folder from being
counted as team files as well. Reading styles only, a few thousand files take seconds.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from zipfile import BadZipFile, ZipFile

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from survey_docx_styles import read_file_usage  # noqa: E402
from tests.evals.parser.corpus import path_map_location  # noqa: E402
from tests.evals.parser.digests import create_key, key_location, keyed_digest, load_key  # noqa: E402
from tests.evals.parser.labels_schema import (  # noqa: E402
    MANIFEST_PATH,
    PR_SUBSET_SIZE,
    Category,
    DebateFormat,
    Manifest,
    ManifestEntry,
    TemplateFamily,
    coverage_shortfalls,
)

__all__ = ["Candidate", "infer_format", "infer_season", "main", "propose_selection"]

_SEASON_FOLDER = re.compile(r"^(20\d\d)-(20\d\d)$")
_FORMAT_PATTERNS: tuple[tuple[re.Pattern[str], DebateFormat], ...] = (
    (re.compile(r"(^|[^a-z])(ld|lincoln)", re.IGNORECASE), DebateFormat.LD),
    (re.compile(r"^hsld\d", re.IGNORECASE), DebateFormat.LD),
    (re.compile(r"(^|[^a-z])(pf|pfd|public forum)([^a-z]|$)", re.IGNORECASE), DebateFormat.PF),
    (re.compile(r"^hspf\d", re.IGNORECASE), DebateFormat.PF),
    (re.compile(r"policy|^hspolicy\d", re.IGNORECASE), DebateFormat.POLICY),
)

#: What the manifest says about itself. One constant, so a re-key cannot carry a stale claim
#: ("keyed by SHA-256") forward into a manifest that is no longer keyed that way.
MANIFEST_DESCRIPTION = (
    "Parser evaluation files, held on the operator's machine and never committed. Keyed by an "
    "HMAC digest under the operator's key, never a plain SHA-256, which over a public corpus "
    "would join straight back to the file. No file name, school or team code. "
    "Written by scripts/select_eval_files.py."
)

#: Files longer than this are hard to label by hand in one sitting. Adjustable with --max-paragraphs.
DEFAULT_MAX_PARAGRAPHS = 600

#: A file shorter than this has too little structure to measure anything; a one-paragraph document
#: would otherwise be the first pick for the PR subset, which prefers short files.
DEFAULT_MIN_PARAGRAPHS = 20


def infer_season(folders: Sequence[str]) -> str | None:
    """`2025-2026` → `2025-26`, from the nearest folder that looks like a season."""
    for folder in reversed(folders):
        match = _SEASON_FOLDER.match(folder)
        if match and int(match.group(2)) == int(match.group(1)) + 1:
            return f"{match.group(1)}-{match.group(2)[2:]}"
    return None


def infer_format(folders: Sequence[str]) -> DebateFormat | None:
    """The event, from the outermost folder whose name says which one.

    Outermost, because the folder a coach sorts by event sits above topic folders whose names can
    contain anything.
    """
    for folder in folders:
        for pattern, debate_format in _FORMAT_PATTERNS:
            if pattern.search(folder):
                return debate_format
    return None


def _paragraph_count(path: Path) -> int | None:
    try:
        with ZipFile(path) as archive:
            data = archive.read("word/document.xml")
    except (BadZipFile, KeyError, OSError):
        return None
    return data.count(b"<w:p>") + data.count(b"<w:p ")


@dataclass(frozen=True)
class Candidate:
    """One file that could be selected. `path` never leaves this process except into the path map."""

    path: Path
    digest: str
    category: Category
    season: str
    debate_format: DebateFormat
    template_family: TemplateFamily
    paragraphs: int

    def entry(self, *, pr_subset: bool) -> ManifestEntry:
        return ManifestEntry(
            digest=self.digest,
            category=self.category,
            season=self.season,
            debate_format=self.debate_format,
            template_family=self.template_family,
            pr_subset=pr_subset,
        )


def iter_candidates(
    inputs: Sequence[tuple[Category, Path]],
    *,
    exclude_dirs: frozenset[str],
    skipped: Counter[str],
    key: bytes,
    min_paragraphs: int = DEFAULT_MIN_PARAGRAPHS,
) -> Iterator[Candidate]:
    seen: set[str] = set()
    for category, root in inputs:
        if not root.is_dir():
            raise SystemExit(f"input folder not found for category {category.value}")
        for path in sorted(root.rglob("*.docx")):
            if path.name.startswith("~$"):
                continue
            if exclude_dirs & set(path.relative_to(root).parts[:-1]):
                continue
            content = path.read_bytes()
            digest = keyed_digest(content, key)
            if digest in seen:
                skipped["duplicate bytes"] += 1
                continue
            seen.add(digest)
            # Below a caselist or camp root the folders are schools and team codes, which say
            # nothing about format and could mislead a pattern ("Lincoln"); only team folders count.
            ancestry = path.parent.parts if category is Category.TEAM else root.parts
            season, debate_format = infer_season(ancestry), infer_format(ancestry)
            if season is None or debate_format is None:
                skipped["season or format not readable from folders"] += 1
                continue
            family = read_file_usage(path, category.value).template_family
            if family == "unreadable":
                skipped["unreadable"] += 1
                continue
            paragraphs = _paragraph_count(path)
            if paragraphs is None or paragraphs == 0:
                skipped["no document body"] += 1
                continue
            if paragraphs < min_paragraphs:
                skipped[f"under {min_paragraphs} paragraphs"] += 1
                continue
            yield Candidate(
                path=path,
                digest=digest,
                category=category,
                season=season,
                debate_format=debate_format,
                template_family=TemplateFamily(family),
                paragraphs=paragraphs,
            )


Requirement = tuple[Callable[[Candidate], bool], int]


def _requirements(category: Category) -> tuple[int, list[Requirement]]:
    """How many files a category gets, and the strata it must reach first (ac1)."""

    def non_verbatim(candidate: Candidate) -> bool:
        return candidate.template_family not in (TemplateFamily.VERBATIM, TemplateFamily.CARDMIRROR)

    if category is Category.TEAM:
        requirements: list[Requirement] = [(non_verbatim, 3)]
        for debate_format in DebateFormat:
            requirements.append((lambda c, f=debate_format: c.debate_format is f, 1))
        for season in ("2024-25", "2025-26", "2026-27"):
            requirements.append((lambda c, s=season: c.season == s, 1))
        return 12, requirements
    if category is Category.CASELIST:
        return 12, [
            (lambda c: c.template_family is TemplateFamily.OTHER_HEURISTIC, 4),
            (lambda c: c.template_family is TemplateFamily.WIKI_CONVERTED, 2),
            (lambda c: c.template_family is TemplateFamily.CARDMIRROR, 3),
            (lambda c: c.template_family is TemplateFamily.VERBATIM, 2),
        ]
    return 6, [
        (lambda c: c.template_family is TemplateFamily.CARDMIRROR, 2),
        (lambda c: c.template_family is TemplateFamily.VERBATIM, 2),
    ]


def _select_category(
    candidates: Sequence[Candidate], category: Category, max_paragraphs: int
) -> list[Candidate]:
    """Meet each stratum first, then fill. Files over `max_paragraphs` are used only as a last
    resort, shortest first, for a stratum no shorter file can meet."""
    total, requirements = _requirements(category)
    in_category = [c for c in candidates if c.category is category]
    pool = sorted((c for c in in_category if c.paragraphs <= max_paragraphs), key=lambda c: c.digest)
    oversized = sorted((c for c in in_category if c.paragraphs > max_paragraphs), key=lambda c: c.paragraphs)
    chosen: list[Candidate] = []
    for predicate, count in requirements:
        have = sum(1 for c in chosen if predicate(c))
        for candidate in [*pool, *oversized]:
            if have >= count or len(chosen) >= total:
                break
            if candidate not in chosen and predicate(candidate):
                chosen.append(candidate)
                have += 1
    # Fill the rest, spreading over (format, season, family) so no stratum dominates.
    while len(chosen) < total:
        taken = Counter((c.debate_format, c.season, c.template_family) for c in chosen)
        remaining = [c for c in pool if c not in chosen]
        if not remaining:
            break
        chosen.append(
            min(remaining, key=lambda c: (taken[(c.debate_format, c.season, c.template_family)], c.digest))
        )
    return chosen


def _pr_subset(selected: Sequence[Candidate]) -> set[str]:
    """Two files per category, the shortest ones, one Verbatim-family and one not where possible."""
    subset: set[str] = set()
    per_category = PR_SUBSET_SIZE // len(Category)
    for category in Category:
        pool = sorted((c for c in selected if c.category is category), key=lambda c: (c.paragraphs, c.digest))
        verbatim = [
            c for c in pool if c.template_family in (TemplateFamily.VERBATIM, TemplateFamily.CARDMIRROR)
        ]
        others = [c for c in pool if c not in verbatim]
        picks = [*verbatim[:1], *others[:1]]
        picks += [c for c in pool if c not in picks][: per_category - len(picks)]
        subset.update(c.digest for c in picks[:per_category])
    return subset


def propose_selection(
    candidates: Sequence[Candidate], *, max_paragraphs: int = DEFAULT_MAX_PARAGRAPHS
) -> tuple[Manifest, dict[str, Path]]:
    selected = [c for category in Category for c in _select_category(candidates, category, max_paragraphs)]
    subset = _pr_subset(selected)
    manifest = Manifest(
        description=MANIFEST_DESCRIPTION,
        entries=tuple(c.entry(pr_subset=c.digest in subset) for c in selected),
    )
    return manifest, {c.digest: c.path for c in selected}


def _parse_input(value: str) -> tuple[Category, Path]:
    category, separator, path = value.partition("=")
    if not separator:
        raise argparse.ArgumentTypeError("--input takes CATEGORY=PATH")
    return Category(category), Path(path).expanduser()


def rekey_manifest(manifest_path: Path, old_path_map: Path, key: bytes) -> tuple[Manifest, dict[str, Path]]:
    """Rewrite an existing manifest under the digest key, keeping the same files and metadata.

    The old manifest may key its files by a plain SHA-256 (`sha256`) or by an earlier keyed digest
    (`digest`); either way the old path map says where each file is, and the new digest is computed
    from the bytes found there. A file the path map no longer locates is an error, not a dropped
    row: a manifest that quietly lost a file would fail ac1's counts with no explanation.
    """
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    locations: dict[str, str] = json.loads(old_path_map.read_text(encoding="utf-8"))
    entries: list[ManifestEntry] = []
    path_map: dict[str, Path] = {}
    missing: list[str] = []
    for row in raw["entries"]:
        old = row.get("sha256") or row["digest"]
        location = locations.get(old)
        if location is None or not Path(location).is_file():
            missing.append(old[:12])
            continue
        path = Path(location)
        digest = keyed_digest(path.read_bytes(), key)
        entries.append(
            ManifestEntry(
                digest=digest,
                category=Category(row["category"]),
                season=row["season"],
                debate_format=DebateFormat(row["debate_format"]),
                template_family=TemplateFamily(row["template_family"]),
                pr_subset=bool(row["pr_subset"]),
            )
        )
        path_map[digest] = path
    if missing:
        raise SystemExit(f"{len(missing)} file(s) in the manifest are no longer where the path map says")
    return Manifest(description=MANIFEST_DESCRIPTION, entries=tuple(entries)), path_map


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--input", action="append", type=_parse_input, default=[], help="CATEGORY=PATH")
    parser.add_argument(
        "--rekey",
        action="store_true",
        help="Re-key the existing manifest instead of choosing files: same files, new digests.",
    )
    parser.add_argument("--exclude-dir", action="append", default=[], help="Folder name to skip.")
    parser.add_argument("--max-paragraphs", type=int, default=DEFAULT_MAX_PARAGRAPHS)
    parser.add_argument("--min-paragraphs", type=int, default=DEFAULT_MIN_PARAGRAPHS)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--path-map", type=Path, default=None, help="Defaults to the evaluation's path map.")
    args = parser.parse_args(argv)
    if not args.input and not args.rekey:
        parser.error("give --input CATEGORY=PATH to choose files, or --rekey to re-key the manifest")

    path_map_path: Path = (args.path_map or path_map_location()).expanduser().resolve()
    try:
        path_map_path.relative_to(REPO_ROOT)
    except ValueError:
        pass
    else:
        raise SystemExit("the path map names schools and team codes; it must live outside the repository")

    key = load_key()
    if key is None:
        created = create_key()
        key = load_key()
        assert key is not None
        print(
            f"new digest key written to {created} (mode 600). "
            "It is never committed; keep it with the path map."
        )

    if args.rekey:
        manifest, path_map = rekey_manifest(args.manifest, path_map_path, key)
        labeling_rows = None
        oversized = 0
    else:
        skipped: Counter[str] = Counter()
        candidates = list(
            iter_candidates(
                args.input,
                exclude_dirs=frozenset(args.exclude_dir),
                skipped=skipped,
                key=key,
                min_paragraphs=args.min_paragraphs,
            )
        )
        manifest, path_map = propose_selection(candidates, max_paragraphs=args.max_paragraphs)
        by_digest = {c.digest: c for c in candidates}
        oversized = sum(1 for digest in path_map if by_digest[digest].paragraphs > args.max_paragraphs)
        labeling_rows = sum(by_digest[digest].paragraphs for digest in path_map)
        print(f"candidates: {len(candidates)}; skipped: {dict(sorted(skipped.items()))}")

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    path_map_path.parent.mkdir(parents=True, exist_ok=True)
    path_map_path.write_text(
        json.dumps({digest: str(p) for digest, p in path_map.items()}, indent=2), encoding="utf-8"
    )

    by_stratum = Counter(
        (e.category.value, e.template_family.value, e.debate_format.value, e.season) for e in manifest.entries
    )
    if args.rekey:
        print(f"re-keyed {len(manifest.entries)} files under the key at {key_location()}")
        print("labels and the sampling plan carry the same digests: regenerate them before labeling")
    else:
        print(
            f"selected {len(manifest.entries)} files, {len(manifest.pr_subset)} in the PR subset; "
            f"{labeling_rows} paragraphs in them; {oversized} over {args.max_paragraphs} paragraphs "
            "(taken only for a stratum no shorter file meets)"
        )
    for (category, family, debate_format, season), count in sorted(by_stratum.items()):
        print(f"  {category:8} {family:15} {debate_format:6} {season}: {count}")
    shortfalls = coverage_shortfalls(manifest)
    for shortfall in shortfalls:
        print(f"SHORTFALL: {shortfall}")
    print("manifest written; path map written outside the repository")
    return 1 if shortfalls else 0


if __name__ == "__main__":
    sys.exit(main())
