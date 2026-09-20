# CardMirror round-trip harness (operator-run)

Round-trips debate `.docx` files through [CardMirror](https://github.com/ant981228/cardmirror)'s
public `fromDocx` / `toDocx` API at a pinned commit, so we can measure what a CardMirror
import-and-re-export changes in a Verbatim file. It exists for the CardMirror evaluation spike
([`plan_specs/v1/e31-debate-file-parsing/t01-cardmirror-evaluation.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t01-cardmirror-evaluation.yaml))
and the results go into [`docs/architecture/cardmirror-evaluation.md`](../../docs/architecture/cardmirror-evaluation.md).

## This is not run in CI

It is **not run in CI**, not part of the `uv` workspace, not in the `web/` pnpm workspace, and no
Python or TypeScript package in this repository imports it. Nothing here is a runtime dependency.
It is an operator tool: Charlie runs it on his own machine against files that stay on that machine.
ADR-0014 records this stance; if it ever changes, it changes there first.

The Python half, [`scripts/compare_docx_roundtrip.py`](../compare_docx_roundtrip.py), *is* covered
by a fast offline test (`uv run pytest tests/scripts/test_compare_docx_roundtrip.py`) that builds
its own synthetic `.docx` files. That test runs in CI; the round-trip itself does not.

## Never commit the files you run it on

Real team, caselist and camp files — and their round-tripped output — must never be committed. Two
guards back this up:

* `roundtrip.mjs` refuses to run when the `--output` directory is inside a git working tree.
* `.gitignore` in this directory ignores `*.docx`, manifests and summaries.

The aggregate summary that goes into the evaluation note identifies files by a short sha256 prefix
and carries no document text, file names or paths. The manifest that `roundtrip.mjs` writes *does*
contain local paths, so it stays on the operator's machine with the files.

## Setup

Node 20 or newer. From this directory:

```bash
npm install
```

That installs CardMirror straight from GitHub at the commit pinned in `package.json`
(`bc92e6bd99cb9b3ce97ddacfa2362100db96360e`, CardMirror 1.11.0) plus `tsx`, which is what lets a
plain `.mjs` script import CardMirror's TypeScript sources. CardMirror is not published to npm, so
the git URL is the pinned reference; `package-lock.json` pins everything underneath it. Expect
about 30 seconds and roughly 30 MB in `node_modules/`.

To run against a checkout you already have instead, point at it:

```bash
CARDMIRROR_DIR=~/src/cardmirror npm run roundtrip -- --input ... --output ...
```

## Running it

```bash
npm run roundtrip -- --input ~/debate-files --output ~/cardmirror-roundtrip-out
```

`--input` is a directory whose immediate subdirectories name the file categories. The evaluation
uses these five:

```
~/debate-files/
  team/                     # our own files, across Policy / LD / PF
  caselist/                 # hsld26 snapshot files that use Verbatim styles
  caselist-non-verbatim/    # caselist files that do not use Verbatim styles
  caselist-wiki/            # caselist files converted from wiki text
  camp/                     # OpenEv / camp files
```

Files sitting directly in the input directory take `--category` (default `unknown`).

For each file the harness writes `<output>/<category>/<sha256 prefix>.roundtripped.docx` and
records, in `<output>/roundtrip-manifest.json`, the import and export timings, the byte sizes, and
the node and mark counts of the imported ProseMirror document. A file that throws is recorded with
`"status": "failed"` and its error; the run continues. The exit code is 1 if any file failed.

Then compare:

```bash
cd <repo root>
uv run python scripts/compare_docx_roundtrip.py \
  --manifest ~/cardmirror-roundtrip-out/roundtrip-manifest.json \
  --output ~/cardmirror-roundtrip-out/summary.json
```

`summary.json` is the aggregate that goes into the evaluation note's "Round-trip results" section.
Paste the per-category counts and the difference categories; the per-file rows are keyed by sha256
prefix, so they are safe to paste as well.

## What the comparison counts as a difference

Per paragraph: the text, the structural unit (pocket / hat / block / tag / analytic / undertag /
body, from the paragraph style id or `w:outlineLvl`), and the underline, highlight, bold, cite and
font-size spans. Spans are character ranges over the paragraph text, not runs, because splitting
and merging runs changes nothing a debater can see.

Two things are recorded as *normalizations* rather than differences, because the rendered document
is unchanged: whitespace-only text changes, and a change in how an underline is encoded
(`StyleUnderline` character style, a direct `<w:u>`, or both) when the underlined range is
identical. CardMirror deliberately rewrites underline encoding per slot — the named style in body
text, a direct `<w:u>` in tags and headings — and writes both on body runs on export.

Empty unstyled paragraphs are ignored on both sides; empty *headings* are kept, because an empty
Heading 1 is how debate files separate two documents packed into one.
