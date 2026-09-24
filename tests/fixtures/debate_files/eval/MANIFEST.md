# Parser evaluation files

This is a manifest of files held elsewhere, not a fixture directory. **There is no `.docx` here,
and that is correct.** The thirty files the `v1-e31-t03` parser is measured on stay where they are
on the operator's machine. None of them is copied into this repository in any form, scrubbed or
otherwise.

Why: a team file routinely carries cards another program cut and disclosed, so "our own work
product" is not a category that can be separated out and committed. Scrubbing removes authorship
metadata; it does not remove somebody else's cards. The rulings behind `v1-e31-t02` and
`v1-e31-t03` and `docs/policies/caselist-data-use.md` prohibitions 1, 9 and 10 settle it, and the
policy's dev-environment exception adds that the real corpus never reaches a CI runner.

What the repository holds instead:

| File | What it is |
|---|---|
| [`manifest.json`](manifest.json) | Each evaluation file by [keyed digest](#why-the-digests-are-keyed), category, season, format and template family, and whether it is in the PR subset. The machine-readable manifest; the table below is its summary. |
| [`sampling-plan.json`](sampling-plan.json) | Which paragraphs of each file are labeled: the PR subset in full, contiguous blocks covering about a quarter of every other file. Generated once, before labeling. |
| [`labels/`](labels/) | One `<digest>.jsonl` per file once it is labeled: each labeled paragraph's unit and card, keyed by paragraph index and a [keyed digest](#why-the-digests-are-keyed) of its text. No text. The [labeling guide](labels/README.md) says how. |
| [`../../../evals/baselines/parser.json`](../../../evals/baselines/parser.json) | The scores the regression gate holds the parser to. |

**No file name, path, school or team code appears in any of them.** A caselist file name is
`<School>/<TeamCode>/<...>`, three prohibited things at once. Where each file is on the machine
that holds it is in the **path map**, `~/.debate-intelligence/parser-eval-paths.json` (or
`$DEBATE_PARSER_EVAL_PATHS`), which is outside the repository and which the tooling refuses to
write inside it.

### Why the digests are keyed

**No plain SHA-256 either.** A plain digest is not an anonymiser, it is a join key: this
repository is public and the OpenCaselist archives are public, so anyone could hash the same corpus
and read a committed digest straight back to `<School>/<TeamCode>/<filename>` — exactly what
leaving the names out was for. Every digest here is an **HMAC-SHA256** under a key kept beside the
path map at `~/.debate-intelligence/parser-eval-digest.key`, never committed. CI never checks these
digests (it has no files), the fixture-changed validator still works because an HMAC over changed
content differs, and the operator holds the key. See
[`digests.py`](../../../evals/parser/digests.py).

## How the files were chosen

[`scripts/select_eval_files.py`](../../../../scripts/select_eval_files.py) proposed the selection on
2026-09-21 from the operator's folders: the three team season folders (2024-2025, 2025-2026 and
2026-2027, with the caselist and camp folders inside them excluded), the `hsld26-0915` caselist
snapshot (the newest; the snapshots are cumulative) and the 2026-27 Policy camp files. It read
bytes and style references only, never text, and printed counts only.

* Candidates are ordered by their keyed digest, so the choice is reproducible and has nothing to do
  with who wrote a file or what it is called.
* Each category meets the strata Goal criterion ac1 names first, then fills across
  format × season × template family.
* Template family is `scripts/survey_docx_styles.py`'s classifier, the one the style survey used.
* Files over 600 paragraphs are passed over, because every paragraph is corrected by hand. The one
  exception: every 2026-27 team file is longer than that, so the shortest of them was taken to
  cover the season.
* Files under 20 paragraphs are passed over too: they have too little structure to measure, and
  the PR subset, which prefers short files, would otherwise pick a one-paragraph document.
* The PR subset is two files per category, the shortest, one Verbatim-family and one not where the
  category allows.

1,827 files were candidates (109 byte-identical duplicates, 24 files under 20 paragraphs, 1
unreadable file and 1 file with no season or format folder were skipped). The 30 selected files
hold 5,788 paragraphs, and all 30 parse.

**Status: proposed, awaiting the coach's approval** (the `collect-files` node's manual criterion).
Until the coach approves it, nothing is labeled.

## The selection

`digest` is the first 16 hex digits of the keyed digest; `manifest.json` has the full value.

| digest | Category | Season | Format | Template family | PR subset |
|---|---|---|---|---|---|
| `93c9db239ccfd360` | team | 2024-25 | LD | other-heuristic |  |
| `569327e939db86f6` | team | 2024-25 | LD | verbatim |  |
| `b02c230aa4f3e1b9` | team | 2024-25 | LD | wiki-converted |  |
| `9d0a74b95ccf9269` | team | 2024-25 | PF | other-heuristic | yes |
| `a888a5db95488218` | team | 2024-25 | PF | verbatim | yes |
| `cfe852ee3f4e49d9` | team | 2025-26 | LD | other-heuristic |  |
| `1538bd64e454894e` | team | 2025-26 | LD | verbatim |  |
| `f2e5e7ea9706807a` | team | 2025-26 | LD | wiki-converted |  |
| `d52fdcceb45b789c` | team | 2025-26 | PF | other-heuristic |  |
| `90ee056b8f95296a` | team | 2025-26 | PF | verbatim |  |
| `4f9115e33c3dbad3` | team | 2025-26 | Policy | verbatim |  |
| `a8afd234413032f4` | team | 2026-27 | PF | verbatim |  |
| `4e5d4ca9ceb8217b` | caselist | 2026-27 | LD | cardmirror |  |
| `7847cb0097628fff` | caselist | 2026-27 | LD | cardmirror |  |
| `d493ea2573ca9a1d` | caselist | 2026-27 | LD | cardmirror |  |
| `3a4b7d4717904624` | caselist | 2026-27 | LD | other-heuristic |  |
| `56f3905d5fe679e3` | caselist | 2026-27 | LD | other-heuristic |  |
| `90fe3d84f2ba99e9` | caselist | 2026-27 | LD | other-heuristic |  |
| `f897900ef90160ac` | caselist | 2026-27 | LD | other-heuristic |  |
| `06e05b7abae54eb2` | caselist | 2026-27 | LD | verbatim | yes |
| `15be67df9cfaa272` | caselist | 2026-27 | LD | verbatim |  |
| `bcfba63d8d9d6a29` | caselist | 2026-27 | LD | verbatim |  |
| `0bf568786e7dc6bb` | caselist | 2026-27 | LD | wiki-converted |  |
| `4b11269583a94621` | caselist | 2026-27 | LD | wiki-converted | yes |
| `71ce5ee012203a7e` | camp | 2026-27 | Policy | cardmirror |  |
| `930a44726db76488` | camp | 2026-27 | Policy | cardmirror |  |
| `18346891306c5a9d` | camp | 2026-27 | Policy | other-heuristic |  |
| `a99a55d4d1d282f2` | camp | 2026-27 | Policy | other-heuristic | yes |
| `bad8c9119196b60a` | camp | 2026-27 | Policy | verbatim | yes |
| `f3442236bb398f4b` | camp | 2026-27 | Policy | verbatim |  |

### Against Goal criterion ac1

| Requirement | Selected |
|---|---|
| At least 30 files | 30 |
| At least 12 team files, all three formats | 12: LD 6, PF 5, Policy 1 |
| Team files across all three seasons | 2024-25 5, 2025-26 6, 2026-27 1 |
| At least 3 team files not on the Verbatim template | 6 (4 other-heuristic, 2 wiki-converted) |
| At least 12 caselist files, 4 non-Verbatim, 2 wiki-converted | 12: 4 other-heuristic, 2 wiki-converted, 6 Verbatim-family |
| At least 6 camp files | 6 |

`coverage_shortfalls()` in [`labels_schema.py`](../../../evals/parser/labels_schema.py) checks the
same list, and `test_labels_schema.py` runs it against `manifest.json` on every PR.

### The sampling plan

Labeling all thirty files in full is about 5,800 rows of judgment work. Plan `792cad9c0f3fa456`
(generated 2026-09-23 by [`scripts/plan_eval_sampling.py`](../../../../scripts/plan_eval_sampling.py))
labels **1,876 of 5,788 paragraphs, 32.4%**: the six PR-subset files in full (435 rows, because they
gate every pull request and cannot be partial) and 1,441 of the other 5,353 rows, 26.9%, in
contiguous blocks.

Blocks are at least 20 paragraphs, chosen deterministically from each file's keyed digest, and
weighted toward blocks whose pre-labels hold `POCKET`, `UNDERTAG` or `ANALYTIC` — the sparsest units
and the ones the parser is weakest on. The weighting changes *which* blocks are picked, never how
many, so the rate does not move. A short file whose quarter would be under 20 paragraphs is labeled
whole instead; that is why some rates below are well above 25%.

| digest | Category | Paragraphs | Labeled | Rate | Blocks |
|---|---|---|---|---|---|
| `93c9db239ccfd360` | team | 62 | 22 | 35% | 40-61 |
| `569327e939db86f6` | team | 143 | 43 | 30% | 20-39, 120-142 |
| `b02c230aa4f3e1b9` | team | 96 | 20 | 21% | 20-39 |
| `9d0a74b95ccf9269` | team | 29 | 29 | 100% | whole file |
| `a888a5db95488218` | team | 31 | 31 | 100% | whole file |
| `cfe852ee3f4e49d9` | team | 128 | 48 | 38% | 80-127 |
| `1538bd64e454894e` | team | 49 | 20 | 41% | 0-19 |
| `f2e5e7ea9706807a` | team | 91 | 31 | 34% | 60-90 |
| `d52fdcceb45b789c` | team | 283 | 80 | 28% | 40-59, 100-139, 180-199 |
| `90ee056b8f95296a` | team | 550 | 140 | 25% | 0-55, 336-419 |
| `4f9115e33c3dbad3` | team | 196 | 56 | 29% | 20-39, 160-195 |
| `a8afd234413032f4` | team | 1020 | 255 | 25% | 0-50, 102-152, 459-560, 918-968 |
| `4e5d4ca9ceb8217b` | caselist | 119 | 40 | 34% | 0-19, 40-59 |
| `7847cb0097628fff` | caselist | 315 | 80 | 25% | 0-19, 60-79, 140-159, 220-239 |
| `d493ea2573ca9a1d` | caselist | 162 | 42 | 26% | 0-19, 140-161 |
| `3a4b7d4717904624` | caselist | 79 | 20 | 25% | 20-39 |
| `56f3905d5fe679e3` | caselist | 149 | 40 | 27% | 40-59, 80-99 |
| `90fe3d84f2ba99e9` | caselist | 178 | 40 | 22% | 0-19, 100-119 |
| `f897900ef90160ac` | caselist | 113 | 20 | 18% | 40-59 |
| `06e05b7abae54eb2` | caselist | 68 | 68 | 100% | whole file |
| `15be67df9cfaa272` | caselist | 77 | 20 | 26% | 0-19 |
| `bcfba63d8d9d6a29` | caselist | 129 | 49 | 38% | 0-19, 100-128 |
| `0bf568786e7dc6bb` | caselist | 62 | 20 | 32% | 0-19 |
| `4b11269583a94621` | caselist | 55 | 55 | 100% | whole file |
| `71ce5ee012203a7e` | camp | 466 | 120 | 26% | 0-23, 120-143, 168-191, 288-311, 408-431 |
| `930a44726db76488` | camp | 108 | 20 | 19% | 0-19 |
| `18346891306c5a9d` | camp | 321 | 80 | 25% | 100-119, 140-179, 280-299 |
| `a99a55d4d1d282f2` | camp | 198 | 198 | 100% | whole file |
| `bad8c9119196b60a` | camp | 54 | 54 | 100% | whole file |
| `f3442236bb398f4b` | camp | 457 | 135 | 30% | 0-22, 184-206, 230-252, 345-367, 414-456 |


Two things the coach may want to weigh when approving: the caselist files are all LD and the camp
files all Policy, because that is what the local corpus holds (hsld26 snapshots, Policy camp
files); ac1 asks for all three formats only among team files. And the 2026-27 team folders hold
only six `.docx` files, all long, so that season is represented by one file.
