# Session report: v1-e31-t31-labelled-evaluation-gaps

| | |
|---|---|
| Task | `v1-e31-t31-labelled-evaluation-gaps` — Where the labelled evaluation's missed cites, tags and highlights go, counted before any rule |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t31-labelled-evaluation-gaps.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t31-labelled-evaluation-gaps.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t31-labelled-evaluation-gaps` |
| Session status | PARTIAL: phase 1 checkpoint. The re-measure (ac1) and the tallies (ac2) are done, and the PM's ruling is asked for below. No parser rule has changed. ac3 and ac4 wait for the ruling. The Goal stays `InProgress` <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Phase 1 of the PM's plan of 2026-10-27, stopped at its checkpoint. No parser rule has changed.

- **The re-measure (ac1).** The 2026-10-20 baseline's tiers on `2026.10.20-docx-6`, without
  `--write-baseline`: **every figure is unchanged.** The run took 2.9 s. CITE is still precision
  0.985, recall 0.623.
- **The tallies (ac2).** The PM asked to lead with cite recall.
  - **31 of the 135 judged labelled cards have no cite row read at all**: the gap students see.
  - 81 of 215 labelled cite rows are missed:
    - 46 are a later line of a cite, read as nothing;
    - 28 sit directly under a tag (19 of them read as nothing);
    - 11 are read as body and 4 as a tag.
  - The 14 missed tags: 4 are caused by a cite read as a second tag; 7 are wiki-converted bold
    lines.
  - **Highlight misses nothing.** All 707 wrong characters are added highlights, in one
    coach-reviewed PF file: cyan 449, green 71, white 187.
- **The proposals.** Four guarded cite shapes take 48 labelled cites and no other row. With all
  four:
  - cite precision 0.985 → 0.989, recall 0.623 → 0.847;
  - tag F1 0.935 → 0.959;
  - cards with no cite read 31 → 8;
  - non-Verbatim CITE F1 0.796 → 0.956, which meets its 0.90 target.

  These are what-if scores from the harness's own `score_file`. The "as read" what-if reproduces the
  published figures exactly.
- **For the PM first:** [the relay prompt](#relay-prompt-for-the-pm). It holds the rules, the
  white-highlight question, the coach question on the cyan and green highlights, and the re-parse
  plan for the bucket-mode world.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `missed-units`: Missed units, counted then ruled | In progress: counted; waiting for the ruling | Re-measure and tallies done, relay sent. Rules, version and re-parse plan wait. `uv run pytest packages/debate_core/tests/integrations/docx_parser` → `979 passed, 2 xfailed in 10.88s` (parser unchanged) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the baseline's tiers re-measured on the `docx-6` store, recorded beside the 2026-10-20 figures in docs/data, without writing a baseline | PASS | `perl -e 'alarm 115; exec @ARGV' .venv/bin/python scripts/run_parser_eval.py --tier both` → `pr-subset: 6 files, gate PASSED`, `full: 30 files, gate PASSED`, 2.9 s. The run had no `--write-baseline`, and `tests/evals/baselines/parser.json` is unchanged. The report rendered from the run was diffed with `docs/data/parser-eval-2026-10.md`: only the version, gate and gate-note lines differ. Recorded side by side in [`docs/data/parser-eval-gaps-2026-10.md`](../data/parser-eval-gaps-2026-10.md#re-measured-on-docx-6-2026-10-27). Run by the session, not the operator ([Deviation 1](#deviations-from-the-spec)) |
| ac2: tallies of where missed CITE, TAG and highlight rows go, by caselist, template family and format, counts only, sent to the PM before any rule | PASS | `perl -e 'alarm 115; exec @ARGV' .venv/bin/python scripts/tally_missed_units.py --tier full` → exit 0, 3.0 s; `--tier pr-subset` the same. Tallies are in [the data document](../data/parser-eval-gaps-2026-10.md#where-the-misses-go-full-tier-docx-6), and the [relay prompt](#relay-prompt-for-the-pm) is below (2026-10-27). No file under `packages/` has changed on this branch (`git diff --stat origin/dev -- packages` prints nothing) |
| ac3: each ruled rule a synthetic fixture shown failing first; the pr-subset gate holds; tag and cite precision do not fall; before and after figures in the report | NOT RUN | Waits for the PM's ruling. The what-if scores give the expected effects |
| ac4: `parser_version` bumped once; the operator's re-parse written out in full | NOT RUN | Waits for the ruling. The spec's re-parse steps predate bucket mode: the plan for the cloud run is proposed in the relay, and no commands are drafted yet, as the PM asked ([Deviation 4](#deviations-from-the-spec)) |
| Node `missed-units`: `uv run pytest packages/debate_core/tests/integrations/docx_parser` | PASS (parser unchanged) | `979 passed, 2 xfailed in 10.88s` |
| `uv run scripts/validate_specs.py` | PASS | See [the checks](#the-checks-run-before-this-report) |

## The checks run before this report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py --run` | 47 test files, `2119 passed in 265.31s`, pytest exited 0 after 269 s. **Over the two-minute line**: I expected 47 files to take well under it and did not measure first. Agreement 10 would have left it to the pull request's `ci` |
| `.venv/bin/python -m pytest tests/evals/parser/test_missed_units.py` | `9 passed` |
| Two mutants of `missed_units.py` (the link-or-year guard removed; the demoted tag not given back), fresh `HYPOTHESIS_STORAGE_DIRECTORY` each, `-n 0` | Both caught by assertion (2 failed and 1 failed); the file restored and `cmp` clean after each |
| `uv run --frozen ruff format --check .` / `ruff check .` | `1527 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright scripts/tally_missed_units.py tests/evals/parser/missed_units.py tests/evals/parser/test_missed_units.py` | `0 errors, 0 warnings, 0 informations` (no package changed) |
| `uv run --frozen lint-imports` and `uv run python scripts/check_thin_handlers.py` | `Contracts: 18 kept, 0 broken.` and `67 ... handlers within 25 statements` |
| `uv run python scripts/docs_index.py --check-descriptions` / `scripts/check_command_blocks.py` | `All 56 indexed documents under docs/ have a description` / `OK` |
| `uv run scripts/validate_specs.py` | `OK` (phase `InProgress`) |

## What was counted, and how

**The re-measure.** `scripts/run_parser_eval.py --tier both` writes its reports to `build/eval-reports/`
(gitignored). The full report was rendered with `baseline_report_text`, the same function that wrote
`parser-eval-2026-10.md`, and the two were diffed. The only differences are the parser version
(`docx-5` → `docx-6`), the gate (`FAILED`: no baseline then; `PASSED` now) and the gate's note.

**The tallies.** `scripts/tally_missed_units.py` and
[`tests/evals/parser/missed_units.py`](../../tests/evals/parser/missed_units.py) read the same files
the same way the evaluation does: the path map, the key, the digest check, and the checkout's
parser. Its `ReadingParser` keeps each paragraph's description, the way `v1-e31-t24`'s count script
did. Nothing leaves it but counts:

- a rule is named by its family (the part before the first colon), because what follows can name a
  file's own style;
- a highlight colour is named only when the profile lists it;
- a file is named by its digest prefix, as `MANIFEST.md` does;
- `test_no_text_leaves_the_tally` checks this on the invented file.

**The what-if scores.** The what-ifs re-score the harness's own `Prediction` with a shape's
paragraphs read as cites:

- a tag that the assembly demoted only for want of a cite (`assembly-tag-without-cite-or-evidence`)
  is given back;
- card boundaries stay as the parser drew them, so these are unit and span scores only. ac3's
  before-and-after will be the real parser's.

The "as read" variant reproduces every published figure: CITE 0.9853/0.6233/0.7635, highlight F1
0.9731, span F1 0.9852, Verbatim CITE 0.751, non-Verbatim CITE 0.796.

**The index context** was counted read-only over the dev index the PM's note used
(`767b9c7c056b80cb`, opened `mode=ro`). Only `doc_id`, `cite`, `text` word counts and the
representative's `source_sha256` were read; no school or team column. Each source file was put in
its family with `scripts/survey_docx_styles.py`'s classifier, over the 2,679 blobs in the
operator's dev data directory: 10 s. Both of the note's totals reproduce (6,214 and 4,805). The
script stayed in the session's scratch directory and printed counts only.

**The tallies, the shapes and the what-if tables** are in the data document,
[`parser-eval-gaps-2026-10.md`](../data/parser-eval-gaps-2026-10.md). The relay below repeats what
the PM needs to rule.

## Relay prompt for the PM

```text
v1-e31-t31 (labelled evaluation gaps), phase 1 checkpoint, 2026-10-27. Counts only; nothing changed in the parser.

RE-MEASURE (ac1). The 2026-10-20 tiers on docx-6, no --write-baseline: every figure unchanged (whole report diffed). CITE precision 0.985, recall 0.623; Verbatim CITE F1 0.751, non-Verbatim 0.796; Verbatim span F1 0.971; PF highlight F1 0.759. Gate passes against the docx-5 baseline. Run by the session (read-only, 2.9 s).

TALLIES (ac2), full tier. Details: docs/data/parser-eval-gaps-2026-10.md.
- Cards: of 135 judged labelled cards, 72 have their whole cite read, 32 part of it, 31 none. The 31 are the gap students see.
- Cite rows: 81 of 215 missed. Read as nothing 64 (61 by no rule at all), as body 13, as a tag 4.
  Where they stand: 46 are a later line of a cite (36 directly under a line read as a cite, 10 further down); 28 directly under a tag; 4 under a tag the assembly demoted; 3 other.
  59 hold a link, 63 a year, only 12 a name and year at the head.
  By family: verbatim 46, other-heuristic 16, cardmirror 15, wiki-converted 4. By source: team 38, camp 35, caselist 8 (all hsld26, the eval's only caselist). By format: Policy 35, PF 28, LD 18.
- Tag rows: 14 of 173 missed. 4 are tags demoted to analytics because the cite below was read as a second tag. 7 are wiki-converted bold lines read as body (4 underlined). 1 is read as a hat, 1 as a cite, 1 as body in a CardMirror file.
- Highlight: nothing missed anywhere. All 707 wrong characters are ADDED highlight, all in one coach-reviewed team PF Verbatim file (a888a5db95488218, PR subset): cyan 449, green 71, white 187. No tracked change or hidden text explains them.
- Index context: the 6,214 no-cite documents by their representative's file family: other-heuristic 3,105 (2,375 with 100+ words), cardmirror 2,505 (1,941), verbatim 510 (422), wiki-converted 94 (67). hspf26 other-heuristic alone is 2,365. Both note totals reproduce.

PROPOSED RULES. Effects are the harness's own scores with the shape applied, full tier: cite P/R; "no cite" = cards with no cite read, as read 31. Each shape is counted over every labelled row; "other rows" is the precision cost.
(1) A line read as nothing, directly under a line read as a cite and directly over a body, holding a link or a year, is part of the cite. 23 cites, 0 other rows (22 Verbatim). P 0.987, R 0.730; no cite stays 31; cards with part of their cite 32 -> 11. Without the link-or-year guard it takes 3 body rows and 1 undertag (P 0.963), so the guard is part of the rule.
(1') The same for every line of a run of such lines between a cite and a body. 33 cites, 1 body row: P 0.982, R 0.777. It lowers cite precision, so it is a variant, not the recommendation.
(2) A line read as nothing, directly under a tag (or a tag demoted for want of a cite), directly over a body, holding a link or a year, is the card's cite. 19 cites, 0 other rows (other-heuristic 8, cardmirror 4, verbatim 4, wiki 3). P 0.987, R 0.712; no cite 31 -> 13. This is the shape of the index's other-heuristic and CardMirror gap.
(3) A line read as body, at most 400 characters, under a tag, over a body, with a link and no highlight, is the cite. 2 cites, 0 other rows. Too few to judge precision.
(4) A line read as a second tag, directly under a tag, over a body, with a name and year at its head, is the cite, and the tag above gets its tag reading back. 4 cites, 0 other rows. TAG P 0.952 -> 0.976, R 0.919 -> 0.942; ANALYTIC F1 0.789 -> 0.811.
(H) White highlight (the profile already marks it "not a reading colour") is not read as highlight. -187 added characters: highlight F1 0.973 -> 0.980, Verbatim span F1 0.971 -> 0.974, PR-subset Verbatim highlight 0.695 -> 0.756. Beyond the eval: search counts highlighted text as read aloud, so white text stops counting as read; the docx renderer and the search card HTML stop drawing an invisible white; the lossless writer copies a card's paragraphs from the source by their indices (v1-e33-t02), so it should be unaffected, and phase 2's writer tests would show it. No unit score moves.
Together, (1)+(2)+(3)+(4): cite P 0.985 -> 0.989, R 0.623 -> 0.847, F1 0.763 -> 0.912; tag F1 0.935 -> 0.959; no cite 31 -> 8. Verbatim CITE F1 0.751 -> 0.895 (P 0.979 -> 0.985); non-Verbatim CITE 0.796 -> 0.956 (target 0.90 met). PR subset: cite P 0.969 -> 0.973, R 0.705 -> 0.818; tag P 0.949 -> 0.974; no unit F1 falls.
(1)+(2)+(4) without (3): cite P 0.989, R 0.837, F1 0.907; no cite 10.
Left after all four: 33 cite rows (11 later lines the guard or the body test turns away, 10 third lines only (1') takes, 11 read as body) and 10 tag rows (8 read as body, 7 of them wiki-converted).
Not proposed: a tag rule for the 7 wiki-converted lines. Why t24's bold-tag rule does not take them is not counted here; the index has 94 wiki-converted no-cite documents, and the labelled rows are all in one source's wiki-converted files.

QUESTIONS
Q1. Which cite rules? (a) (1)+(2)+(4), (b) (a) plus (3), (c) (b) with (1') in place of (1), (d) other.
  Recommendation: (a). Each takes cites and nothing else, and together they meet the non-Verbatim cite target without lowering any precision. (3) rests on 2 rows. (1') lowers cite precision, which the spec forbids.
Q2. Count over the store before building? For each ruled shape, how many cards gain a cite, by caselist and family, and how many of the index's 6,214. That needs a re-parse of every source: t24's every-source count took 353 s, so it is the operator's. Options: (a) the operator, before 2026-11-01; (b) a before-and-after diff after the rule is built, in the session, one caselist at a time under two minutes each where it fits, as t24's diff was (175 s); (c) a coach sample of 20 lines of shape (2) as well.
  Recommendation: (b), plus (c) when the operator is back. (2) is the one shape whose non-cite neighbours the labels hardly cover.
Q3. White highlight (H)? (a) The parser stops reading white as highlight. (b) Leave it.
  Recommendation: (a), white only. It is invisible in Word, the profile already calls it not a reading colour, and today it counts as read aloud in search. lightGray and black are visible and stay.
Q4. Cyan (449) and green (71) characters in a888a5db95488218 that the coach labelled unhighlighted. The guide says any colour is highlight. Ask the coach to look at the file in Word. If they show as highlighted, a label correction needs your ruling (forbidden list); after (H) it would take PF highlight F1 to 1.000. If they don't, I'd look for what hides them.
  Recommendation: the coach looks; no parser rule either way.
Q5. The re-parse (ac4), rewritten for bucket mode. Proposed plan; no commands drafted yet.
  - The switch is the image, not the merge. The run's task definition pins its image by digest, so merging the bump into dev changes nothing until an image built from a release that carries it is pushed and applied. Coupling: ANY image applied after the merge, for any task, brings the full re-parse with it. So nobody applies a dev run image while the operator is away; or phase 2 merges after his return.
  - Dev, on his return:
    (i) a release with the bump; caselist_run_deploy.sh dry run, then push; the image-only apply, the PM reading the plan (caselist-cloud-run.md, "A new image, later").
    (ii) The full parse, as a run by hand: one-off run-task overrides per caselist, openev included, Thursday to Monday, under the bucket lock. Alternatively the next Wednesday run parses every imported caselist in full itself (full_parses > 0), but leaves openev on docx-6 until a camp file arrives. That is what the scheduled-sync runbook says of the Mac's agent; I assume the cloud run's parse stage does the same, which phase 2 would check. Recommend the by-hand run.
    (iii) The second run: the next scheduled Wednesday run, with full_parses 0 and only the week's imports parsed and uploaded.
    (iv) Clusters: compare_card_clusters.py against the docx-6 occurrence table, from a restore-run-state copy, not the Mac's data directory.
    (v) The search function and index together: a function deployed with the new parser turns card download off until an index built by the same parser is published (evidence-search runbook). So the tub deploy and the index publish go together.
  - Prod: published by hand from a copy restored from the dev bucket under the dev lock (caselist-cutover.md, "Until the promotion"), signed in to prod before each caselist. The copy holds the parsed store but no raw sources; whether a parsed-store publish needs them is v1-e40-t06's open question 2. That question decides whether prod's steps can be written.
  - Timing: the re-parse waits for the operator's return; dev and prod stay on docx-6 meanwhile.
  - The spec's ac4 wording ("dev, the second run, prod with a sign-in before each caselist, the cluster rebuild") predates bucket mode. Please amend it to this plan, or rule otherwise.
  Recommendation: this plan, with phase 2 merged but no run image applied until he is back.
Q6. ac1 says "(operator)"; the session ran it, read-only, in 2.9 s (working agreement 2). OK to leave as a Deviation?
```

## Files changed

- `scripts/tally_missed_units.py` (new): the thin script that prints the tallies as JSON.
- `tests/evals/parser/missed_units.py` (new): the counting module. It holds the missed rows, the
  candidate shapes, the highlight characters and the what-if scores.
- `tests/evals/parser/test_missed_units.py` (new): an invented file whose labels and expected
  counts are written by hand.
- `docs/data/parser-eval-gaps-2026-10.md` (new): the re-measure beside 2026-10-20's, the tallies,
  the shapes and what-ifs, and the index context.
- `docs/session-reports/v1-e31-t31-labelled-evaluation-gaps.md`: this report.

No label file, baseline or parser file changed.

## Deviations from the spec

1. **ac1 was run by the session, not the operator.** It is read-only over the operator's labelled
   files and took 2.9 s (working agreement 2; the PM's instruction of 2026-10-27).
2. **"By caselist" is by source.** The evaluation's caselist files all come from one caselist
   (`hsld26`), so the tallies break down by source (team, caselist, camp), as well as by template
   family and format.
3. **Highlight is counted by character, both ways.** The spec's "a highlight span ... that the
   parser read otherwise" is counted as labelled highlight characters the parser missed (0) and
   highlight characters it added that the labels do not hold (707). The harness scores highlight the
   same way.
4. **ac4's re-parse wording predates the cutover.** Since `v1-e40-t06` the weekly run is a cloud
   task in bucket mode. The plan is proposed in the relay (Q5) for the PM to amend the spec. No
   commands are drafted.

## Decisions and assumptions

- **Candidate shapes are judged as the parser sees the file:** by what neighbouring lines were read
  as, not by their labels. A rule can only see readings.
- **"Above" and "below" step over blank lines, table cells and text boxes**, as `line_above`
  (`v1-e31-t24`) and the assembly do.
- **A year is four digits from 1900, or an apostrophe and two digits; a link is `http(s)://` or
  `www.`.** Only their presence is counted.
- **The index is counted by the representative's source file.** The index stores one card per
  document; its siblings may come from files of other families.
- **The index used is the PM note's (`767b9c7c056b80cb`),** not the newer one on the Mac, so the
  note's totals could be checked.

## Operator follow-ups

None in phase 1. The re-parse is phase 2's, and waits for the ruling on Q5.

## Follow-up work

- The **7 wiki-converted tag rows** (bold lines read as body, 4 of them underlined) are not proposed
  for a rule here. If the PM wants them, they belong to a task with a store count of the shape.
- **`v1-e40-t06`'s question 2** (raw sources for prod's hand publish) decides whether prod's
  re-parse steps can be written.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
