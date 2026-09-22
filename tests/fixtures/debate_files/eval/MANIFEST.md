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
| [`manifest.json`](manifest.json) | Each evaluation file by SHA-256, category, season, format and template family, and whether it is in the PR subset. The machine-readable manifest; the table below is its summary. |
| [`labels/`](labels/) | One `<sha256>.jsonl` per file once it is labeled: each paragraph's unit and card, keyed by paragraph index and the SHA-256 of its text. No text. The [labeling guide](labels/README.md) says how. |
| [`../../../evals/baselines/parser.json`](../../../evals/baselines/parser.json) | The scores the regression gate holds the parser to. |

**No file name, path, school or team code appears in any of them.** A caselist file name is
`<School>/<TeamCode>/<...>`, three prohibited things at once. Where each file is on the machine
that holds it is in the **path map**, `~/.debate-intelligence/parser-eval-paths.json` (or
`$DEBATE_PARSER_EVAL_PATHS`), which is outside the repository and which the tooling refuses to
write inside it.

## How the files were chosen

[`scripts/select_eval_files.py`](../../../../scripts/select_eval_files.py) proposed the selection on
2026-09-21 from the operator's folders: the three team season folders (2024-2025, 2025-2026 and
2026-2027, with the caselist and camp folders inside them excluded), the `hsld26-0915` caselist
snapshot (the newest; the snapshots are cumulative) and the 2026-27 Policy camp files. It read
bytes and style references only, never text, and printed counts only.

* Candidates are ordered by SHA-256, so the choice is reproducible and has nothing to do with who
  wrote a file or what it is called.
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

`sha256` is the first 16 hex digits; `manifest.json` has the full value.

| sha256 | Category | Season | Format | Template family | PR subset |
|---|---|---|---|---|---|
| `654670a36839df3f` | team | 2024-25 | LD | other-heuristic |  |
| `02896227b5258b55` | team | 2024-25 | LD | verbatim |  |
| `0787bc76a18c2cc5` | team | 2024-25 | LD | wiki-converted |  |
| `002fe74ed9fb3376` | team | 2024-25 | PF | other-heuristic | yes |
| `20441979471f1404` | team | 2024-25 | PF | verbatim | yes |
| `2629a939544980b3` | team | 2025-26 | LD | other-heuristic |  |
| `033f0e75f4663b3f` | team | 2025-26 | LD | verbatim |  |
| `6cff3aec913a711e` | team | 2025-26 | LD | wiki-converted |  |
| `026411e2f9d8ff4a` | team | 2025-26 | PF | other-heuristic |  |
| `33f2b03c3f1ae8bc` | team | 2025-26 | PF | verbatim |  |
| `68330aca9c306e5e` | team | 2025-26 | Policy | verbatim |  |
| `08c20c5383b924a7` | team | 2026-27 | PF | verbatim |  |
| `0014a46118fad7e7` | caselist | 2026-27 | LD | cardmirror |  |
| `00541c0d85e81e49` | caselist | 2026-27 | LD | cardmirror |  |
| `007dd1116e1ac77c` | caselist | 2026-27 | LD | cardmirror |  |
| `00e1cfba1fed6be6` | caselist | 2026-27 | LD | other-heuristic |  |
| `05cd6b7e1a0e140a` | caselist | 2026-27 | LD | other-heuristic |  |
| `09cf114a0975a01f` | caselist | 2026-27 | LD | other-heuristic |  |
| `0b656206e0219bcb` | caselist | 2026-27 | LD | other-heuristic |  |
| `04e0dfabbb9234f1` | caselist | 2026-27 | LD | verbatim |  |
| `059de01874250837` | caselist | 2026-27 | LD | verbatim | yes |
| `05b52cfcd66b325b` | caselist | 2026-27 | LD | verbatim |  |
| `001c718fb904b558` | caselist | 2026-27 | LD | wiki-converted |  |
| `02469e600c35b35f` | caselist | 2026-27 | LD | wiki-converted | yes |
| `064cca568eabc8cb` | camp | 2026-27 | Policy | cardmirror |  |
| `0671fb02f4dc37b0` | camp | 2026-27 | Policy | cardmirror |  |
| `3640a41b4e6b6000` | camp | 2026-27 | Policy | other-heuristic |  |
| `cca8ddcc1cf1ac62` | camp | 2026-27 | Policy | other-heuristic | yes |
| `296384935261f77d` | camp | 2026-27 | Policy | verbatim | yes |
| `2f6060b31b5c57d0` | camp | 2026-27 | Policy | verbatim |  |

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

Two things the coach may want to weigh when approving: the caselist files are all LD and the camp
files all Policy, because that is what the local corpus holds (hsld26 snapshots, Policy camp
files); ac1 asks for all three formats only among team files. And the 2026-27 team folders hold
only six `.docx` files, all long, so that season is represented by one file.
