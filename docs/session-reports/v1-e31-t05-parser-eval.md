# Session report: v1-e31-t05-parser-eval

| | |
|---|---|
| Task | `v1-e31-t05-parser-eval` — Parser accuracy evaluation |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t05-parser-eval.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t05-parser-eval.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t05-parser-eval` |
| Session status | PARTIAL |
| Updated | 2026-09-23, after spec amendments #72 (keyed digests) and #73 (sampled labeling) |

## Summary

All the machinery this evaluation needs is built, tested and committed. What's left is human work
that the spec reserves for Charlie: approving the file selection, correcting the labels, the coach
spot-check, establishing the baseline, and the full-corpus health run. **The Goal stays
`InProgress`**, because ac1, ac3 and ac5 cannot be met until that work is done. Nothing was
labeled in this session, and no pre-label was accepted as a label.

What's built:

- a proposed selection of 30 files, keyed by SHA-256, that meets every ac1 stratum;
- a label schema with a structural validator and a validator that fails when a file changes under
  its labels;
- a pre-labeling and correction workflow that cannot turn a pre-label into a label without a
  person checking every row;
- the ac2 metrics and ac3 targets;
- a baseline gate that fails rather than passing against nothing;
- an operator-run corpus health script;
- a labeling guide.

**No debate file, excerpt, file name, path, school or team code is committed — and no plain
SHA-256 either.** Every digest is an HMAC under a key kept beside the path map, outside the
repository; the tools refuse to write a plain digest of corpus content, and refuse to write the
key, the path map or a correction worksheet inside the repository.

**Since the PM review**, two amendments landed and are implemented (Deviations 6 and 7): digests
are keyed, and labeling is sampled to 1,876 rows rather than 5,788. The manifest was re-keyed over
the same thirty files, the sampling plan is generated and committed, and pre-labels and all thirty
worksheets were regenerated against the final shape, so labeling starts once.

On the work before the amendments, the PM should look at Deviation 1 first. The spec asks for the labeled subset to run "in the PR
`ci` check", but the policy says the real corpus never reaches a CI runner. The two cannot both
hold. The PR subset therefore runs in the default `pytest` run on the machine that holds the
files, and CI runs the whole harness on an invented file instead.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `collect-files` | DONE, awaiting coach approval | [`scripts/select_eval_files.py`](../../scripts/select_eval_files.py) proposed 30 files (5,788 paragraphs) from 1,827 candidates, reading bytes and style references only and printing counts only. Re-keyed in place on 2026-09-23 (`--rekey`): same thirty files, HMAC digests. [`manifest.json`](../../tests/fixtures/debate_files/eval/manifest.json) and [`MANIFEST.md`](../../tests/fixtures/debate_files/eval/MANIFEST.md) are committed. Approval is a hand-off (Operator follow-up 1). |
| `label-tooling` | DONE | [`labels_schema.py`](../../tests/evals/parser/labels_schema.py) and [`scripts/prelabel_docx.py`](../../scripts/prelabel_docx.py) (`prelabel`, `worksheet`, `import`, `mark-reviewed`). |
| `labeling` | Plan generated and committed; correction NOT STARTED (human work) | Sampling plan `792cad9c0f3fa456` ([`sampling-plan.json`](../../tests/fixtures/debate_files/eval/sampling-plan.json), [`scripts/plan_eval_sampling.py`](../../scripts/plan_eval_sampling.py)): 1,876 of 5,788 rows. The [labeling guide](../../tests/fixtures/debate_files/eval/labels/README.md) is written and awaits sign-off. Pre-labels for all 30 files are committed as `PRELABELED` (the evaluation refuses them until a person corrects them) and the 30 worksheets are written outside the repository. Correction and spot-checks are hand-offs (Operator follow-ups 2 and 3). |
| `metrics-and-gates` | DONE (code); baseline NOT ESTABLISHED | [`metrics.py`](../../tests/evals/parser/metrics.py), [`corpus.py`](../../tests/evals/parser/corpus.py), [`test_parser_eval.py`](../../tests/evals/parser/test_parser_eval.py) and [`scripts/run_parser_eval.py`](../../scripts/run_parser_eval.py). [`baseline parser.json`](../../tests/evals/baselines/parser.json) is committed as `NOT_ESTABLISHED`: no labels means no numbers, and a baseline number that was never measured would be exactly the kind of number working agreement 6 forbids. |
| `corpus-health-run` | Script DONE; run NOT RUN (operator-only) | [`scripts/parser_corpus_health.py`](../../scripts/parser_corpus_health.py), tested on an invented corpus. The spec forbids the real run in a session; the command is Operator follow-up 5. |

## Acceptance criteria

Commands run from the task worktree. The counts come from the named file with `--no-cov`.

### Goal criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 (amended) — at least 30 files labeled, none committed; the strata as before; manifest by **keyed digest**, category, season and format; labeling sampled (PR subset in full, ~25% of the rest in contiguous blocks); coach reviewed the labels | **NOT MET**: selection, re-keying and plan done; labeling not started | Selection: `uv run python scripts/select_eval_files.py …` → `selected 30 files, 6 in the PR subset`, no `SHORTFALL`, about 22 s. Re-key: `--rekey` → `re-keyed 30 files`, and a check over the corpus confirms all 30 manifest digests equal the HMAC and none equals a plain SHA-256. Plan: `uv run python scripts/plan_eval_sampling.py` → `sampling plan 792cad9c0f3fa456: 1876 of 5788 paragraphs (32.4%), 6 file(s) labeled in full`. `test_the_committed_manifest_meets_ac1` and `test_the_committed_plan_covers_every_manifest_file_and_samples_what_ac1_asks` pass. **0 of 30 files corrected; coach review not done.** |
| ac2 (amended) — JSON and Markdown reports with per-unit P/R/F1, card-boundary exact match, completeness accuracy and span F1, by source, template family and format, **each carrying the sampling rate and labeled-row count** | **PASS** (machinery); no real report yet | `uv run pytest tests/evals/parser/test_metrics.py` → `26 passed`. `test_reports_carry_every_breakdown_and_no_file_detail_in_markdown` checks every section and the sampling block; `test_a_score_records_the_rows_it_was_computed_over` and `test_group_sampling_counts_add_up` check the rate and counts per group; `test_the_harness_scores_a_sampled_file_over_its_blocks_only` runs the whole path from `.docx` to report on a sampled file. |
| ac3 — targets recorded and met or ticketed (Verbatim: TAG/CITE/EVIDENCE ≥ 0.97, POCKET/HAT/BLOCK ≥ 0.95, ANALYTIC ≥ 0.85, span ≥ 0.99; non-Verbatim and wiki-converted: TAG/CITE/EVIDENCE ≥ 0.90) | Targets recorded: PASS. Met or ticketed: **NOT RUN** | `test_the_targets_are_the_ones_ac3_states` pins all 11 targets as written. Whether they are met can only be known from corrected labels. |
| ac4 (amended) — real-file tiers run where the corpus is and skip elsewhere with a stated reason; CI runs the harness end to end over an invented file; both tiers fail on a unit F1 more than 0.01 below the baseline and when no baseline exists; the label validator fails when a file changes under its labels; the baseline records its sampling plan and the gate refuses when the plan differs | **PASS** (the amendment describes what was built). Real tiers: **NOT RUN** | The gate: `test_a_drop_within_tolerance_passes` (0.9749 against 0.98), `test_a_drop_of_more_than_one_point_fails` (0.96), `test_a_tier_with_no_baseline_fails_rather_than_passing_vacuously`, and end to end in `test_the_harness_gate_fails_when_the_labels_and_parser_disagree`. The fixture validator: `test_an_edited_paragraph_fails`, `test_different_bytes_fail`, `test_a_paragraph_added_or_lost_fails` and `test_the_harness_refuses_a_file_that_changed_under_its_labels`. The real tiers on this machine: `-m "eval and not slow"` → `1 skipped` ("6 of 6 pr-subset files are not yet corrected by a person"); `-m "eval and slow"` → `1 skipped` ("30 of 30"). The 30 s budget is asserted in the test but has not run against real labels. The plan guard: `test_a_different_sampling_plan_refuses_rather_than_comparing`, `test_a_baseline_with_no_plan_recorded_still_compares`, `test_the_gate_refuses_when_the_baseline_was_measured_over_another_plan` and `test_the_harness_refuses_labels_made_under_a_different_plan`. |
| ac5 — operator-run corpus health report committed under docs/data/ with parse success rate ≥ 0.98 and every failure reason counted | **NOT RUN** (operator-only) | `uv run pytest tests/scripts/test_parser_corpus_health.py` → `6 passed`, which covers counting, deduplication across snapshots, failures by reason, crashes by exception type, and no names or text in the report. `docs/data/parser-corpus-health.md` does not exist yet. |

### Node criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| `collect-files` — manifest lists caselist and camp files (`contentMatch: caselist`) | PASS | `grep -c caselist tests/fixtures/debate_files/eval/MANIFEST.md` → `17` |
| `collect-files` — **custom:** coach approves the file selection | **NOT RUN** (hand-off) | Operator follow-up 1 |
| `label-tooling` — label schema validation tests pass | PASS | `uv run pytest tests/evals/parser/test_labels_schema.py` → `26 passed`. Also `test_prelabel.py` → `21 passed` (pre-label, markup, worksheet refusals and the sampled shape), `test_digests.py` → `14 passed` and `test_sampling.py` → `14 passed`. |
| `labeling` — labeling guide exists (`contentMatch: labeling guide`) | PASS | `grep -c "labeling guide" tests/fixtures/debate_files/eval/labels/README.md` → `2`. The guide now covers the sampling plan, jumping row indices and the card-at-a-block-edge rule. |
| `labeling` — the sampling plan is generated once, before labeling, and committed | PASS | `uv run python scripts/plan_eval_sampling.py` → plan `792cad9c0f3fa456`, committed at `tests/fixtures/debate_files/eval/sampling-plan.json`. Pre-labels for all 30 files and all 30 worksheets regenerated against it; no file has been corrected yet, so nothing had to be relabeled. |
| `labeling` — **custom:** coach spot-checks at least 3 labeled files and signs off the guide | **NOT RUN** (hand-off) | Operator follow-ups 2 and 3 |
| `metrics-and-gates` — metric unit tests pass | PASS | `uv run pytest tests/evals/parser/test_metrics.py` → `20 passed in 1.45s` |
| `metrics-and-gates` — labeled PR subset passes against the baseline | **NOT RUN** | `uv run pytest tests/evals/parser -m "eval and not slow"` exits 0 but only because the one test skipped (`1 skipped`), so it is not recorded as a pass. It needs corrected labels and an established baseline. |
| `metrics-and-gates` — parser baseline committed (`contentMatch: parser_version`) | PASS (placeholder) | `grep -c parser_version tests/evals/baselines/parser.json` → `1`. The file is `"status": "NOT_ESTABLISHED"` with no scores, deliberately. |
| `corpus-health-run` — corpus health report committed (`contentMatch: parse success rate`) | **NOT RUN** | Operator follow-up 5 |

Also run, though not a criterion:

| Check | Result |
|---|---|
| Whole repository suite | `uv run pytest` → `2290 passed, 1 skipped in 23.41s` (the skip is the real PR-subset tier) |
| Lint and format | `uv run ruff check` and `ruff format --check` over every new file → `All checks passed!` |
| Spec validation | `uv run scripts/validate_specs.py` → `OK: 282 files, 38 epics, 224 tasks, 20 releases` |
| Pre-labeling works on the real selection | `prelabel --all` → all 30 files parse and pre-label over the plan's blocks, 1,876 rows in total, in under a second. Committed as `PRELABELED`; the evaluation refuses them until a person corrects them. |
| Worksheets regenerated | 30 worksheets, 1,876 rows, written to `~/parser-eval-worksheets/` (1.4 MB, outside the repository). |
| No plain digest of a corpus file is committed | `uv run pytest tests/evals/parser/test_digests.py` → `14 passed`, including the scan that hashes all 30 corpus files the way an outsider would and finds no match anywhere under `tests/fixtures/debate_files/eval/`. |
| Runner refusals | `run_parser_eval.py --tier pr-subset` → exit 1, "no label file" × 6. `--write-baseline --report docs/data/x.md` → exit 2, "0 file(s) are COACH_REVIEWED". |

## Files changed

**Evaluation library and tests (`tests/evals/parser/`)**: all new.

- `labels_schema.py`: manifest and label models, both validators, the ac1 coverage check.
- `metrics.py`: scoring, groups, targets, gate, reports.
- `corpus.py`: path map, loading a file by SHA-256, running a tier.
- `synthetic.py`: an invented file and its hand-written labels.
- Test modules: `test_labels_schema.py`, `test_prelabel.py`, `test_metrics.py`, `test_parser_eval.py`.

**Baseline**: `tests/evals/baselines/parser.json`, a `NOT_ESTABLISHED` placeholder.

**Manifest and guide (`tests/fixtures/debate_files/eval/`)**: `manifest.json`, `MANIFEST.md` and
`labels/README.md` (the labeling guide). There are no label files yet.

**Scripts**, all new:

- `select_eval_files.py`: proposes the selection and writes the path map outside the repository.
- `prelabel_docx.py`: pre-labels, worksheets and import.
- `run_parser_eval.py`: runs the evaluation and writes the baseline.
- `parser_corpus_health.py`: the operator-run health report.

**Other**: `tests/scripts/test_parser_corpus_health.py` (new), and one paragraph in
`tests/README.md` about `evals/`.

## Deviations from the spec

Deviations 1 and 2 were raised by the first session and have since been settled by amendment #72,
which rewrote ac4 to describe what was built. They are kept here because the PM review refers to
them. Deviations 6 and 7 are the amendments' own work.

1. **The labeled PR subset cannot run in the PR `ci` check.** *(Settled by amendment #72.)* The spec description says "a small
   labeled subset (about 6 files, marker `eval`) in the PR `ci` check within seconds", ac4 says
   "runs in the default PR pytest run", and the `metrics-and-gates` node's criterion runs it with
   `-m "eval and not slow"`. But the same spec, like ac1 and the policy, keeps every evaluation
   file on the operator's machine. `caselist-data-use.md`'s dev-environment exception, limit 4,
   says "the real corpus never reaches a CI runner". A CI runner has no files to parse.

   What I built instead:

   - the real PR-subset tier is marked `eval`, not `slow`, so it runs in the default `pytest` run
     wherever the path map and corrected labels exist, and asserts the 30 s budget;
   - everywhere else it **skips**, naming how many files are missing labels;
   - what CI runs on every PR is the label and manifest validation, plus the full harness end to
     end on an invented file with hand-written labels, covering the gate, the refusal of changed
     files and the refusal of pre-labels.

   ac4 is **FAIL as written, PASS as amended** — and ac4 now says exactly this, so the criterion
   and the code agree.

2. **The same applies to the full tier "in the validate-dev slow tier and nightly".** If
   validate-dev runs on a CI runner, it can't reach the corpus either. The full tier runs with
   `uv run pytest tests/evals/parser -m "eval and slow"` on the operator's machine, or through
   `scripts/run_parser_eval.py`. **Still open**: scheduling it nightly on Charlie's Mac, or
   deciding it runs only before a promotion, is a PM call that amendment #72 did not make.

3. **`manifest.json` sits beside `MANIFEST.md`.** The node lists only `MANIFEST.md` as output. The
   tools need a machine-readable manifest, so `MANIFEST.md` is its human summary, and
   `test_the_manifest_summary_table_matches_manifest_json` keeps the two identical.

4. **Two scripts the spec does not name**, both within the `scripts` package:
   `select_eval_files.py` (the `collect-files` node needs something to choose files without a
   person copying file names around) and `run_parser_eval.py` (the only path by which the
   baseline changes, and it enforces the coach-review rule). The evaluation library lives in
   `tests/evals/parser/` next to `metrics.py`, where the spec puts it.

5. **The baseline is a placeholder, not scores.** The node's criterion is met by the file's
   existence. Committing numbers before any label exists would have been inventing a measurement.

6. **Digests are keyed, and a plain one is refused** (amendment #72). The correction is wider than
   the first session's: it scoped the risk to short paragraph texts being confirmable by guessing
   and called the exposure low. The real problem is a **join**, and it applies to the file digests
   as much as the text ones — this repository is public, the OpenCaselist archives are public, so
   anyone could hash the same corpus and map every committed digest back to
   `<School>/<TeamCode>/<filename>` with no guessing at all. What is now in place:

   - file and paragraph digests are HMAC-SHA256 under a key at
     `~/.debate-intelligence/parser-eval-digest.key` (`$DEBATE_PARSER_EVAL_KEY_FILE` to move it),
     created mode 600, never committed, and never overwritten once it exists — overwriting would
     orphan every committed digest at once;
   - the tooling refuses a key inside the repository, refuses to write a plain digest of corpus
     content (`refuse_plain_digest`, the same shape of guard as refusing to write the path map
     inside the repository), and stops with a clear error rather than falling back to a plain
     digest when the key is missing;
   - `test_nothing_committed_holds_a_plain_digest_of_a_corpus_file` hashes all thirty files the way
     an outsider would and proves no result appears anywhere under the eval fixture directory;
   - the manifest was re-keyed in place with `select_eval_files.py --rekey`, keeping the same
     thirty files, the same PR subset and the same metadata, so the zero-card wiki-converted file
     the PM asked to keep is still in the subset.

   The cost is nothing CI needs: CI has no files to check digests against, and the
   fixture-changed validator still works because an HMAC over changed content differs. The cost to
   the operator is one file to keep beside the path map. **Losing it** means re-keying — the
   manifest, plan and labels are rewritten together — so it is worth a backup wherever the path map
   is backed up.

7. **Labeling is sampled** (amendment #73). Plan `792cad9c0f3fa456` labels **1,876 of 5,788
   paragraphs**: the six PR-subset files in full (435 rows) and 1,441 of the other 5,353 (26.9%) in
   contiguous blocks of at least 20 paragraphs. Blocks come from each file's keyed digest, so a
   re-run picks the same ones, and are weighted toward blocks holding `POCKET`, `UNDERTAG` or
   `ANALYTIC`. The weighting changes which blocks are picked, never how many: the number of blocks
   is fixed before any weight is read, and `test_weighting_does_not_change_how_many_rows_are_labeled`
   holds that. Three consequences worth knowing:

   - **A card is scored only where it lies wholly inside a labeled block.** A card the parser found
     in unlabeled text is not a false positive, it is unjudged, and counting it would invent a
     miss nobody can see. The labeler leaves such a card unnumbered and import refuses one that
     crosses a block edge.
   - **Every metric states the rows it was computed over**, in the JSON and in the Markdown.
   - **The gate refuses rather than compares when the plan differs**, because a metric over one
     sample and a metric over another are two measurements, not a regression. The baseline records
     its `sampling_plan_id`.

   A short file whose quarter would be under 20 paragraphs is labeled whole instead, which is why
   the overall rate is 32.4% rather than 25%.

## Decisions and assumptions

- **A pre-label can't become a label without a person.** The evaluation refuses `PRELABELED`
  files. `import` refuses a worksheet with any unchecked row, any edited text, or edited text
  under span markup. It records `rows_changed_from_prelabel`, so a file corrected with zero
  changes is at least visible. `test_an_uncorrected_worksheet_nobody_checked_is_refused` is the
  test that holds the line.
- **The baseline can't change without the coach.** `--write-baseline` refuses unless three files
  covering team, caselist and camp are `COACH_REVIEWED`, and unless a `--report` path under
  `docs/data/` is given. That path is recorded in the baseline.
- **The gate fails when there is no baseline**, instead of passing because there's nothing to
  compare against. It gates unit F1 overall and in the Verbatim and non-Verbatim groups
  separately, so a regression on the non-Verbatim minority can't hide in the average. A baseline
  recorded for an older `parser_version` still gates a newer parser; the report notes the
  mismatch.
- **Scores are micro-averaged** (counts summed, then divided). "Verbatim files" in ac3 means the
  `verbatim` and `cardmirror` families, and "non-Verbatim and wiki-converted" means the rest.
- **Card boundaries are compared as exact (first paragraph, last paragraph) ranges.** Card
  precision is reported beside boundary exact match so that a split card shows up in both.
  Completeness is scored only on cards whose boundaries matched.
- **Underline includes Verbatim's `Emphasis` style**, which is underlined as well as bold. The
  highlight colour is ignored. Both are written into the labeling guide.
- **Span sample**: a stable hash of (file digest, paragraph index) picks about 20% of the non-empty
  **labeled** paragraphs. The test measures 1,850 to 2,150 out of 10,000.
- **Blocks that touch are joined into one run.** Two windows picked side by side are one unbroken
  stretch, and every block edge is a place a card falls out of the sample.
- **Weighted sampling, not "take the densest blocks".** Efraimidis–Spirakis weighted sampling
  without replacement keeps every block reachable; always taking the rare-unit-heaviest blocks
  would measure the corpus's tail rather than the corpus. Measured over a hundred files, the block
  holding every rare unit is picked 75 times weighted against 20 unweighted.
- **Pre-labels are committed as `PRELABELED`.** They hold no text and the evaluation refuses them,
  so they are safe to keep in the repository while they are corrected, and it saves the operator a
  step before labeling. Nothing scores until a person has marked every row checked.
- **Selection details**:
  - Files over 600 paragraphs are passed over, except as a last resort for a stratum. Every
    2026-27 team file is long, and the shortest, 1,020 paragraphs, was taken.
  - Files under 20 paragraphs are passed over. My first run's shortest-first PR-subset pick chose
    a one-paragraph document; I caught this from the pre-label counts and re-ran.
  - Caselist and camp files take format and season only from the input folder, never from the
    school and team-code folders below it.
- **Digests are keyed** (was: plain SHA-256 text hashes, flagged here as a low exposure). Superseded
  by amendment #72 and Deviation 6: the exposure was a join, not a guess, and it covered the file
  digests too.
- **Team files are parsed as `OPENEV` with camp `team-files`**, because `SourceOrigin` has no value
  for a team's own file. Parsing doesn't depend on origin. See Follow-up work.
- **Worksheets open in Numbers or LibreOffice.** Excel rewrites some CSV text on import, and
  `import` would refuse the result, so the guide says so.

## Operator follow-ups

**1. Approve the file selection (coach, about 15 minutes).** Read
[`MANIFEST.md`](../../tests/fixtures/debate_files/eval/MANIFEST.md): 30 files, their strata, and
two caveats (caselist is all LD and camp all Policy, because that's what the corpus holds; 2026-27
team files are represented by one long file). To look at the six PR-subset files:

```bash
uv run python -c "
import json, subprocess, pathlib
m = json.load(open('tests/fixtures/debate_files/eval/manifest.json'))
p = json.load(open(pathlib.Path.home() / '.debate-intelligence/parser-eval-paths.json'))
for e in m['entries']:
    if e['pr_subset']: subprocess.run(['open', p[e['sha256']]])
"
```

Where: your Mac, in the task worktree `debate-intelligence-worktrees/v1-e31-t05-parser-eval`.
Success looks like: you confirm the selection covers team, caselist (Verbatim, non-Verbatim,
wiki-converted) and camp formatting, or you name the files to swap. A re-run of
`scripts/select_eval_files.py` with different options produces a different proposal
deterministically.

**2. Correct the labels (human work).** **1,876 rows across 30 files**, not 5,788: the sampling plan
is generated and the worksheets are already written, so this starts immediately. The six PR-subset
files (435 rows) unblock the PR tier first. Follow the
[labeling guide](../../tests/fixtures/debate_files/eval/labels/README.md).

The worksheets are in `~/parser-eval-worksheets/`, one CSV per file, named by the first 16
characters of the file's keyed digest — the first column of the table in
[`MANIFEST.md`](../../tests/fixtures/debate_files/eval/MANIFEST.md). Open each beside its `.docx`
in Numbers or LibreOffice (not Excel, which rewrites some text and would be refused on import),
tick every row, then:

```bash
uv run python scripts/prelabel_docx.py import <digest-prefix> \
    --worksheet ~/parser-eval-worksheets/<digest16>.csv --corrected-by coach
```

Success looks like: `CORRECTED by coach; N of M labeled rows changed from the pre-labels`. Delete
each worksheet once its import succeeds. Commit only `labels/*.jsonl`.

Two things to expect: **row indices jump** where the plan samples blocks (a worksheet may run 0-19
then 100-128), and a **card cut off by the end of a block is left unnumbered** — label the units,
leave `card` blank. Both are in the guide.

**3. Coach spot-check and guide sign-off.** Check at least three corrected files end to end (one
team, one caselist, one camp) against the `.docx`, sign off the labeling guide, then:

```bash
uv run python scripts/prelabel_docx.py mark-reviewed <sha-prefix> --reviewer coach
```

**4. Establish the baseline (seconds).** It records the sampling plan it was measured over, so
after this the gate refuses to compare against a different plan.

```bash
uv run python scripts/run_parser_eval.py --write-baseline --report docs/data/parser-eval-2026-10.md
uv run pytest tests/evals/parser -m eval
```

Success looks like: `baseline written for parser 2026.09.20-docx-1`, then `2 passed`. The coach
reads `docs/data/parser-eval-2026-10.md` before it's committed with `tests/evals/baselines/parser.json`.
Every ac3 target marked MISSED gets a ticket against `v1-e31-t03`.

**5. Full-corpus health run** (the spec expects 10 to 20 minutes; operator-only by the spec's
forbidden list)

Where: your Mac, in the task worktree `debate-intelligence-worktrees/v1-e31-t05-parser-eval`

```bash
uv run python scripts/parser_corpus_health.py \
  --input "caselist=$HOME/Documents/debate/2026-2027/LD Debate/Opencaselist/hsld26-0901" \
  --input "caselist=$HOME/Documents/debate/2026-2027/LD Debate/Opencaselist/hsld26-0908" \
  --input "caselist=$HOME/Documents/debate/2026-2027/LD Debate/Opencaselist/hsld26-0915" \
  --input "camp=$HOME/Documents/debate/2026-2027/Policy Debate/Camp Files" \
  --output docs/data/parser-corpus-health.md
```

Success looks like: `parsed N of M distinct .docx files (parse success rate 0.98xx)` and exit 0.
It exits 1 below 0.98, after writing the report. Paste back the last 15 lines. Then:

- `grep -c "parse success rate" docs/data/parser-corpus-health.md` should return at least `1`;
- skim the report for anything that looks like a name (there should be none);
- commit it, with a line in `docs/README.md`'s data table;
- file each failure reason against `v1-e31-t03`.

**6. Close the task.** Once 1 to 5 are done: `uv run scripts/task_helper.py set-phase
v1-e31-t05-parser-eval Succeeded`, `uv run scripts/validate_specs.py`, and update this report's
ac1, ac3, ac4 and ac5 rows with the measured results.

**7. Back up the digest key.** `~/.debate-intelligence/parser-eval-digest.key` is the only thing
that ties a committed digest to a file. Keep it wherever the path map is kept. Without it the
labels still exist but can no longer be checked against the corpus, and everything has to be
re-keyed (`select_eval_files.py --rekey`, then regenerate the plan and labels).

## Follow-up work

- **For `v1-e31-t03` (to check during labeling, not yet a finding):** pre-labeling showed 4 of the
  30 selected files with **zero cards**, including a 55-paragraph wiki-converted caselist file in
  the PR subset (`02469e60…`). That may be correct (a file of analytics) or a missed card format.
  The labels will say which. Nothing in the parser was changed.
- **Domain model gap (the owner of `v1-e30-t02` / `v1-e31-t06`):** `SourceOrigin` has no value for
  a team's own file, so the evaluation parses team files under a placeholder `OPENEV` origin.
  Harmless here, but t06 or V3 uploads will need a real one.
- **`pyproject.toml` marker description:** `eval` is described as "LLM evaluation suite, run
  outside the PR CI path". This spec uses `eval` without `slow` for a tier that is in the default
  run. The description is outside this task's packages and was left alone; the owner of
  `v1-e01-t03` may want to reword it.
- **`tests/README.md`** still describes `golden_cards/` as "curated, scrubbed copies of team files",
  which predates the no-real-files ruling. Left as is; a PM wording fix.
- **Where the full `eval and slow` tier runs** (Deviation 2) is still open: nightly on Charlie's
  Mac, or only before a promotion.
- **The sampling rate is 32.4% overall rather than 25%**, because short files whose quarter would
  be under one block are labeled whole. If the PM wants a tighter budget, the knob is
  `--target-rate`/`--minimum-block`, and changing it means a new `plan_id` and a re-baseline.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-09-23

**Notes:**

Accepted as the session's work, which is complete. The Goal stays `InProgress`, correctly: ac1, ac3,
ac4 and ac5 all need a human with the corpus, and no session can close them.

**Two spec corrections, both mine** (`298f7ad`, `specs/parser-eval-keyed-digests`).

The first is the important one, and this session found the weaker form of it and proposed the right
fix. My earlier amendment said to list files "by sha256 ... never by file name, which carries a
school and a team code". Removing the name and leaving a plain SHA-256 achieves nothing: **this
repository is public and the OpenCaselist archives are public**, so anyone can hash the same corpus
and read the committed digests straight back to `<School>/<TeamCode>/<filename>`. That is a direct
join, not a brute-force guess at a short paragraph, and it publishes exactly what removing the names
was meant to withhold. The session scoped the concern to text hashes and called the exposure low; it
is neither confined to text nor low. File and paragraph digests become an HMAC under a key kept
beside the path map and never committed - which is the fix this report proposed, applied wider.

The second: ac4 asked for the labeled subset to run in the PR `ci` check while the same spec keeps
every real file off every runner. Those cannot both hold, and Deviation 1 resolves it the right way
round. ac4 now describes what was built.

**What is best here is what was refused.** `baseline parser.json` committed as `NOT_ESTABLISHED`
rather than a plausible number, a gate that fails when no baseline exists rather than passing
against nothing, a pre-label that cannot become a label until a person ticks every row, and edited
text refused outright. The vacuous-pass failure - a check reporting success because it had nothing
to check - is the same one found in `scripts/site_smoke.py` last week, caught here independently and
designed out rather than papered over. Catching the one-paragraph PR-subset pick from the pre-label
counts and re-running is the same instinct.

**Ordering matters for what comes next.** The manifest must be re-keyed before any labeling begins,
because labels carry the same digests: 435 corrected rows under plain SHA-256 would have to be
remapped afterwards. Re-key first, then label.

**Not a finding against the parser yet, and right not to be.** Four of thirty files pre-labeling to
zero cards, including a 55-paragraph wiki-converted file in the PR subset, is exactly what this task
exists to find out about - and it is unknowable until the labels say so. Keep that file in the PR
subset rather than swapping it for an easier one; it is the most informative file in the set.

Follow-ups accepted as filed. The `SourceOrigin` gap for a team's own file is real and goes to
whoever owns `v1-e30-t02`/`v1-e31-t06`. `tests/README.md` is corrected in the same commit above.
