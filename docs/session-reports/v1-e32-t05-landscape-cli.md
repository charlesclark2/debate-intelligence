# Session report: v1-e32-t05-landscape-cli

| | |
|---|---|
| Task | `v1-e32-t05-landscape-cli` — `debate-research landscape` command |
| Spec | [`plan_specs/v1/e32-argument-landscape/t05-landscape-cli.yaml`](../../plan_specs/v1/e32-argument-landscape/t05-landscape-cli.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t05-landscape-cli` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

This task builds `debate-research landscape report`. The command is a thin adapter over
`LandscapeRunService` in `debate_core.application`, so E34's weekly run can call the same use case.
One run:
* resolves the caselist, snapshot and topic;
* classifies with t02's cache;
* builds t03's bundle, passing the staleness hook the sync run log (ruling 1);
* scans the bundle before sharing (ruling 2);
* writes it under `<data dir>/reports/landscape/<caselist>/<snapshot>/`;
* with `--publish`, uploads it to the same prefix in the dev bucket through the E29 blob-store port,
  skipping any object whose SHA-256 is unchanged.

`--model-mode none` is the only mode, so no run calls a model. Each affirmative round's aff comes
from t09's `AffAssignmentService`, which merged first and is wired here (the PM's condition 1).

**Status: the PM's three conditions are closed, and this needs another review before the PR.** The
PM's line was a re-review if the sync or the wiring changed a count or a rule. Both did, as
expected:
* **The sync** brought t09's heading normalizer, which now strips an advantage's number. That places
  32 more cards (Deviation 13).
* **The wiring** identifies affirmative rounds by plan text and team carry. On the real store, read
  only, aff rounds with no identified aff fall from 1,998 of 2,192 (91.1%) to 940 (42.9%). Coverage
  by rounds rises from 50.6% to 60.2% ([below](#the-wired-report-on-the-real-store)).

**Also changed, each with its test failing first:**
* the seam gained a `writes` flag, so a dry run writes no plan-text cache (Deviation 12);
* a dry run no longer reports the classification cache as written (Deviation 14).

The third block of questions asks for the re-review.

* **The coach's queue pass is applied** (the PM's item 4 and condition 2):
  * seven new positions (Deviation 9): five in the topic's taxonomy, now 1.1.0, and a generic K and
    generic theory position in `generic.yaml`, now 1.1.0;
  * 45 of the 50 decisions, `uq` included; the five left are each left for a reason (Deviation 10);
  * coverage measured before and after: cards 48.1% → 50.1%, negative documents with any placed
    position 35.8% → 42.4%.
* **t09's plan-text cache is valid under 1.1.0.** The pass added no aff position, and the
  vocabulary digest is the same under both versions. All 1,770 affirmative documents are cached under
  the current parser and vocabulary, so no plan-text block is needed before the first run.
* **NOT RUN, so the Goal stays `InProgress`:**
  * ac5 (the first dev run and the coach's review) comes after the merge, so the PR opens with
    `--partial`;
  * validate-dev's own run of the smoke check runs on the dev pre-release built from the merge.

**Look first at the scan before sharing** ([Decision 3](#decisions-and-assumptions)):
* how a hit stays accepted from one week to the next;
* the read-only dry run on the real store ([below](#the-dry-run-on-the-real-store)), which
  reproduces t03's preview count for count and finds 6 scan hits.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| run-service | Done | `application/landscape_run.py` (`LandscapeRunService`, typed errors, `LandscapeRunResult`), `application/landscape_scan.py` (the scan and the acceptance log), and `testing/landscape_run.py`, which plants the `synthetic26` store: manifests, the parsed store and its occurrence table, and `config/landscape/` |
| cli-command | Done | `commands/landscape.py`, registered as the `landscape` group's `report`. The composition root gains `landscape_run` |
| publish | Done | Through `EvidenceObjectStore`: `head` each key, upload where the recorded digest differs, check the stored digest. Tested against moto in the CLI and against a filesystem store in core |
| smoke-check | Done | `tests/smoke/test_landscape_smoke.py`, recorded tier, and a row in `tests/smoke/README.md` |
| first-dev-run | Partly done | The coach's queue pass is applied: seven positions (the topic's taxonomy and `generic.yaml`, both 1.1.0) and 44 decisions in `config/landscape/overrides/policy-2026-27-nhi.yaml`, `tests/config` 23 passed. `docs/data/landscape/first-run-policy.md` records coverage before and after. The dev run and the coach's review are operator follow-ups after the merge |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: on the synthetic fixture, `landscape report --caselist <fixture> --no-publish` writes report.md, positions.csv and top_cards.csv under the snapshot directory and exits 0; `--json` prints paths, counts, method totals and model calls (mode `none`, PM amendment 2026-10-22) | PASS | `test_report_writes_the_bundle_and_json_names_paths_counts_methods_and_model_calls`. The three paths exist, cards by method are `{"ALIAS": 7, "UNPLACED": 2}`, and model calls are 0. Every count was worked out by hand from the fixture table, before any run |
| ac2: an unknown caselist or snapshot exits 2 with the known values; a caselist and date without a `topics.yaml` mapping exits 2 naming the file to edit; exceeding max_model_items exits 1 after writing the review queue, without publishing | PASS, budget clause on the seam | `test_an_unknown_caselist_exits_2_with_the_known_caselists` gives `["synthetic26"]`. `test_an_unknown_snapshot_exits_2_with_the_known_snapshots` gives `["2026-09-08", "2026-09-15"]`. `test_a_caselist_topics_yaml_does_not_map_exits_2_naming_the_file` gives `NO_TOPIC_MAPPING`, `file_to_edit` and the hint `Edit <path>.` `test_publish_over_the_model_budget_exits_1_after_the_review_queue_without_publishing`: the queue file exists, there is no report directory, and the bucket is empty. No model stage exists yet, so the budget is tested with a stand-in classifier that reports 3 items against the run's limit of 0 (Deviation 3) |
| ac3: with `--publish` against moto, objects land under `reports/landscape/<caselist>/<snapshot>/`; a second identical run uploads nothing; `--dry-run` lists planned uploads without writing | PASS | `test_publish_puts_the_bundle_under_reports_landscape_in_the_dev_bucket` (prod bucket empty; bytes equal the local file); `test_publish_a_second_identical_run_uploads_nothing` (`uploaded []`, all three `UNCHANGED`); `test_publish_dry_run_lists_the_planned_uploads_and_writes_nothing` (bucket, `reports/` and `landscape/` all absent) |
| ac4: a smoke check in `tests/smoke/` runs the installed CLI on the synthetic fixture with `--no-publish` and passes in the validate-dev recorded tier | PASS locally; NOT RUN in validate-dev | Run with the recorded tier's markers against this checkout's console script: `.venv/bin/python -m pytest tests/smoke/test_landscape_smoke.py -m "not live and not in_process"` → `2 passed in 3.23s`. validate-dev runs it against the dev pre-release that the merge builds, so that run can only happen after the merge |
| ac5: operator-run in dev, the newest hspolicy26 snapshot generated and published, counts, coverage and queue size in the first-run note, the coach's review before 2026-11-07 | NOT RUN | After the merge ([Operator follow-ups](#operator-follow-ups)). The note exists with the before-pass numbers |
| run-service: `pytest …/test_landscape_run.py` | PASS | `26 passed in 3.13s` |
| cli-command: `pytest packages/debate_cli/tests/test_landscape_command.py` | PASS | `16 passed in 3.00s` |
| cli-command: `uv run debate-research landscape report --caselist synthetic26 --no-publish --model-mode none` | PASS, with a data directory and `--config-dir` | Run with the data directory and config of `synthetic26` planted in the scratchpad (Deviation 2) → exit 0, 1.2 s, three files written. The report was STALE, correctly: 2026-09-15 is 39 days before today |
| publish: `pytest …/test_landscape_command.py -k publish` | PASS | `9 passed in 2.70s` |
| smoke-check: `tests/smoke/test_landscape_smoke.py` exists, contains "landscape" | PASS | 9 matches |
| smoke-check: `uv run lint-imports` | PASS | `Contracts: 16 kept, 0 broken.` |
| first-dev-run: `docs/data/landscape/first-run-policy.md` contains "classification coverage" | PASS | The file exists with the before-pass coverage by cards and by rounds |
| first-dev-run: the coach reviews the first Policy report | NOT RUN | After the merge |

I ran each pytest command as `.venv/bin/python -m pytest …` under `perl -e 'alarm 110'`, which puts
the time limit on the interpreter (working agreement 10).

### Checks shown failing for their reason

* **Red run against a refuse-nothing skeleton:** **14 failed, 12 passed.** The skeleton was
  `landscape_run.py` with every rule and refusal removed:
  * no unknown caselist or snapshot;
  * no empty-store refusal and no model budget;
  * no dry-run read-only view;
  * no run log and no aff source;
  * accepted hits ignored, and no scan refusal;
  * a dry run that publishes, and every object uploaded.

  The 12 that passed hold no rule the skeleton removed. They are the counts and files of an
  ordinary run, the named snapshot, the cache, `--out`, the two topic-mapping refusals (left in),
  the scan's listing, and the two "without" cases. The file was restored byte for byte.
* **The scan's three cases, each failing first.**
  * A planted team code refused: `accept: no digest needed` fails 4, including
    `test_publish_with_a_planted_team_code_is_refused_printing_the_hit_and_its_digest`.
  * A matching digest accepted: `accept: only a wrong digest accepted` fails 5.
  * A stale digest refused: `accept: any digest accepted` fails 2.
* **22 mutants, all caught** (agreement 10's cap is about 20). Each ran in a fresh process with
  bytecode off and `__pycache__` cleared, and the file was restored byte for byte. No Hypothesis is
  used, so agreement 8's database rule does not arise.

  | Mutant (accept rule and unchanged skip, `landscape_run.py`) | Failed |
  |---|---|
  | No digest needed to accept | 4 |
  | Any digest accepted | 2 |
  | Only a wrong digest accepted | 5 |
  | Earlier acceptances ignored | 2 |
  | A refusal still publishes | 5 |
  | The acceptance never recorded | 3 |
  | A dry run publishes | 3 |
  | Equal digest uploads, different digest skips | 7 |
  | Never skips | 4 |
  | Any object present is unchanged, whatever its digest | 1 |
  | A missing object counts as unchanged | 6 |
  | Planned skips ignored at upload | 3 |
  | Digest of the wrong bytes | 10 |

  | Mutant (`landscape_scan.py`) | Failed |
  |---|---|
  | Key keeps the numbers in its line | 1 |
  | Key includes the line number | 1 |
  | Key leaves out the file | 1 |
  | Codes matched without case | 1 |
  | Codes matched as substrings | 1 |
  | Schools of three characters looked for | 1 |
  | Words found by the substring pre-check alone | 2 |
  | Digest depends on order | 1 |
  | Acceptances ignored | 2 |

### The dry run on the real store

Read-only, counts only, before the merge: `landscape report --caselist hspolicy26 --dry-run`
without `--publish`. That asks no bucket and makes no AWS call. Before it ran:
* no `DEBATE_*` variable was set;
* no `caselist pull` was running.

The classification cache and the review queue had the same checksums after the run as before, and
no `reports/landscape/` directory was created. **46 s, exit 0.**

The counts reproduce t03's preview of the same snapshot exactly:
* 68 positions and 318 top-card rows;
* rounds with a read: 2,201 of 4,352;
* set aside as answers: 4,734;
* affirmative rounds with no identified aff: 1,998 of 2,192;
* negative rounds with no placed negative position: 1,389 of 2,160.

The review queue has 1,433 rows. The newest snapshot, 2026-10-20, is current.

**The scan found 6 hits, all in `top_cards.csv`:** 3 school names, 2 team codes and 1 tournament.
I kept their kinds only, and the words are not in this report. The operator reads them in the dry
run. t03 counted 5 for the same file because it counted distinct terms; one code is in two lines.
`report.md` has no hit. t03's one hit there was the word "Disclosures", found by a substring match
on a tournament token, and this scan matches names as whole words (Decision 3).

### Coverage before the coach's pass

t02's measure (documents and teams by side and kind), read-only from its cache, 34.6 s, cache
checksum unchanged. The numbers are t02's to the digit: affirmative documents with a placed aff
159 of 1,770 (9.0%), negative documents with any of the five kinds 742 of 2,070 (35.8%). The full
table is in [the first-run note](../data/landscape/first-run-policy.md). The overrides digest the
header names today is `none`.

### The wired report on the real store

After the sync and the wiring: `landscape report --caselist hspolicy26 --dry-run`, read-only, without
`--publish` (no bucket, no AWS call). Before it ran, no `DEBATE_*` variable was set and no `caselist
pull` was running. **42 s, exit 0.** The classification cache, the plan-text cache and the review
queue had the same checksums after the run as before, and no report directory was created. Taxonomy
1.1.0, overrides digest `e1c2367c…`, 45 decisions.

| Count | Before the pass (t03's preview) | Now |
|---|---|---|
| Classification coverage by cards | 60,987 of 126,681 (48.1%) | 63,494 (50.1%) |
| Classification coverage by rounds | 2,201 of 4,352 (50.6%) | **2,622 (60.2%)** |
| Aff rounds with no identified aff | 1,998 of 2,192 (91.1%) | **940 (42.9%)** |
| How aff rounds are identified | placed card 194 | plan text 959, team carry 226, placed card 67 |
| Neg rounds with no placed negative position | 1,389 of 2,160 (64.3%) | 1,238 (57.3%) |
| Position-rounds set aside as answers | 4,734 | 4,965 |
| Positions read; top-card rows | 68; 318 | 75; 353 |
| Review queue | 1,433 rows | 1,340 rows |
| Scan | 6 hits in `top_cards.csv` | 6 hits in `top_cards.csv`: 3 school, 2 team code, 1 tournament |

## Before the report (working agreement 10)

* **The affected set is over two minutes.** `uv run scripts/affected_tests.py` lists 155 files. Run
  with CI's markers under a 115 s alarm on the interpreter, it was stopped at the alarm (load
  average 5). No worker was left running. So it is left to the pull request's `ci`, which runs the
  whole selection.
* **Within the two minutes, the tests of what changed and the always-run list:**
  * The landscape and classification tests (`test_landscape_run.py`, `test_landscape_scan.py`,
    `test_landscape_report.py`, `test_landscape_seeding.py`, `test_landscape_staleness.py`,
    `test_position_classification.py`), `packages/debate_core/tests/arguments/landscape`,
    `tests/scripts/test_classify_landscape_positions.py`, `tests/config`,
    `tests/smoke/test_landscape_smoke.py`, `tests/architecture` and `tests/specs` → **696 passed,
    2 skipped in 6.85s**. The 2 skips are t02's overrides-file checks, which have no file yet.
  * `packages/debate_cli/tests` → **897 passed in 30.16s**. Its first run failed 4 tests: the pinned
    list of wired integrations, which now has the two landscape adapters (17, not 15). See
    Files changed.
* `uv run --frozen ruff format --check .` → 1199 files already formatted.
* `uv run --frozen ruff check .` → all checks passed.
* `uv run --frozen pyright`, bare as CI runs it → 0 errors (15.9 s). Also
  `pyright packages/debate_core packages/debate_cli` → 0 errors.
* `uv run --frozen lint-imports` → 16 kept, 0 broken. `scripts/check_thin_handlers.py` → 48 handlers
  within 25 statements.
* `scripts/check_command_blocks.py --base origin/dev` → OK, this report included.
  `scripts/check_links.py` → OK. `scripts/docs_index.py --check-descriptions` → OK.
  `tests/architecture/test_single_interpreter_source.py` → 55 passed, for the note's percentages.
* `uv run scripts/validate_specs.py` → OK, 434 files.
* **After the coach's queue pass**, which changed only `config/landscape/`: the tests that read the
  real configuration (`packages/debate_core/tests/integrations/landscape`, `tests/config`, and the
  classify and seed scripts' tests) → **76 passed in 1.54s**. `tests/config` alone → 23 passed, its
  two overrides-file checks no longer skipped.
* **After the sync and the PM's conditions** (agreement 10: the tests of what changed, never the
  whole selection):
  * The landscape tests above plus t09's (`test_aff_assignment.py`, `test_plan_texts.py`,
    `tests/scripts/test_assign_landscape_affs.py`), `packages/debate_core/tests/integrations/landscape`,
    `tests/config`, the seed script's tests, the smoke check, `tests/architecture` and `tests/specs`
    → **898 passed in 6.60s**.
  * `packages/debate_cli/tests` → **898 passed in 30.63s**.
  * The smoke check in the recorded tier → 2 passed.
  * ruff format and check, bare `pyright` (0 errors), lint-imports (16 kept), thin handlers (48)
    and `validate_specs.py` (434 files) all pass.
  * **My one slip:** a commit chained its checks with `;`, so it went ahead past a ruff import-order
    finding in `container.py`. The next commit fixed it, with the checks chained by `&&`.
* No `pyproject.toml`, `uv.lock`, conftest or pytest-plugin change, so no whole-selection hand-off.

## Files changed

* **`debate_core/application/landscape_run.py`** (new): `LandscapeRunService` and everything it
  returns or raises:
  * the request and the result;
  * `LandscapeModelMode`;
  * the refusals `UnknownCaselist`, `UnknownSnapshot` and `NoTopicMapping` (as
    `LandscapeRequestRefused`), `NothingToReport`, `ModelBudgetExceeded` and
    `PublishedObjectMismatch`;
  * the `PositionClassifier` and `AffAssignmentSource` protocols;
  * the upload plan.
* **`debate_core/application/landscape_scan.py`** (new): `scan_report`, `ScanHit` and its key,
  `hits_digest` and `ScanAcceptanceLog`.
* **`debate_core/application/position_classification.py`**: `ClassificationCounts` gains
  `model_items` and `model_calls`, both defaulting to 0. t07 fills them.
* **`debate_core/testing/landscape_run.py`** (new): `plant_synthetic_run`, the `synthetic26` store
  and config. Shared by the core tests, the CLI tests and the smoke check.
* **`debate_core/application/aff_assignment.py`** (t09's): `AffAssignmentService.assignments`,
  this task's seam, which shares the plan-text step with t09's `run`.
  **`debate_core/application/plan_texts.py`** (t09's): `PlanTextService.without_writes`, for a dry
  run.
* **`debate_cli/commands/landscape.py`** (new), registered in `commands/__init__.py`.
* **`debate_cli/container.py`**: `landscape_run`, wiring `YamlTaxonomyRepository` and
  `LocalClassificationStore`, the run log, the acceptance log, the bucket, and t09's
  `AffAssignmentService` with its `PlanTextService` (`LocalPlanTextStore` and the parse worker pool).
* **Tests:**
  * `packages/debate_core/tests/application/test_landscape_run.py` (26) and
    `test_landscape_scan.py` (11);
  * `packages/debate_cli/tests/test_landscape_command.py` (16);
  * `packages/debate_cli/tests/test_installation.py` and `commands/test_doctor.py`: the hand-pinned
    list of wired integrations gains `landscape.classification_store` and
    `landscape.yaml_taxonomy_repository`, and after the wiring `landscape.plan_text_store`, so the
    count goes from 15 to 18;
  * `tests/config/test_landscape_taxonomies.py`: `uq` joins `SHORT_WORDS` (condition 2).
* **`tests/smoke/test_landscape_smoke.py`** (new) and its row in `tests/smoke/README.md`.
* **`config/landscape/`**, the coach's queue pass:
  * `taxonomies/policy-2026-27-nhi.yaml` and `topics.yaml` at 1.1.0, with five positions;
  * `taxonomies/generic.yaml` at 1.1.0, with two;
  * `overrides/policy-2026-27-nhi.yaml` (new), with 45 decisions.
* **`docs/data/landscape/first-run-policy.md`** (new): the first-run note, with the coverage
  before and after the coach's pass.

## Deviations from the spec

1. **Files outside `constraints.packages`:**
   * `debate_core.testing`, for the shared store fixture: test modules cannot import one another,
     and a conftest change would make the whole selection affected;
   * `packages/debate_core/tests` and `packages/debate_cli/tests`;
   * `docs/data/landscape/`;
   * `config/landscape/overrides/`, when the coach's pass is applied (the PM's item 4).

   Question 1.
2. **The `cli-command` node's command needs a data directory and a config directory.**
   `synthetic26` is a fixture. It is not in the repository's `config/landscape/topics.yaml`, nor in
   the operator's data directory, and should be in neither. I ran the command with
   `DEBATE_STORAGE__DATA_DIR` set to a planted scratch store and `--config-dir` set to its config.
3. **`max_model_items` is a seam until t07.** No model stage exists. The run refuses
   (`ModelBudgetExceeded`, exit 1) when its classifier reports more model items than the run's
   limit. That check runs after the review queue is written and before the report is, so nothing is
   published. The limit is 0 while the mode is `none`. `ClassificationCounts.model_items` is the new
   field t07 fills. ac2's clause is tested with a stand-in classifier. Question 3.
4. **`--model-mode` is the command's own option, with the one value `none`.** The shared option
   (`integrations/models/model_mode.py`) is an argparse helper for record, replay and live, with no
   `none`, and it reads `DEBATE_MODEL_MODE`. The landscape command ignores that variable until t07
   joins the two. Question 2.
5. **Two options the spec does not name:**
   * `--config-dir`, because an installed build does not bundle `config/landscape/`. It defaults to
     the checkout around the working directory and is a usage error when there is none;
   * `--confirm-prod`, as `caselist publish` and `store sync` have it.

   `--out` is refused inside a checkout, because a report holds real tags and cites. Question 7.
6. **t04's sections:** t04 is not built, so there is nothing to add. The bundle is t03's three
   files.
7. **I ran a dry run on the real store before the merge.** The PM's brief lists the first dev dry
   run as an operator follow-up. Mine was read-only, had no `--publish`, so it asked no bucket, and
   took 46 s. Agreement 2 lets a session run that. The operator's dry run, with `--publish`, is
   still the first follow-up. Question 6.
8. **"A failed weekly run shows as stale" is only half met** (ruling 4: the PM files the E34 task). The staleness hook now gets the run
   log, and a cap-bound run makes the report stale (tested). The hook is v1-e34-t03's, and it judges
   a failed run only by the snapshot's age, so a run that failed this week still reads as current
   for up to 8 days. I did not change the hook. Question 4.

9. **The taxonomy gains five positions here** (PM ruling 2026-10-24, (b)). The PM's brief asked
   only for decisions to be applied, but the coach's sheet named five positions the taxonomy did not
   have. The coach's ids, in the file's style: `debt-da`, `ai-da`, `democracy-da`,
   `sustainability-advantage` and `biotech-advantage`. Each has the PM's label and its queue heading
   as its one alias.
   * `taxonomy_version` 1.0.0 → 1.1.0, in the file (with a note of what was added) and in
     `topics.yaml`. Nothing has been released, so v1-e32-t08's rule is not engaged.
   * `tests/config` passes. Its alias checks fail on a planted bad alias (4 failed), and the file
     was restored byte for byte.
   * t09's ac3 bumps again on top of this. Whichever PR merges second rebases the taxonomy file.
   * **Two more, in `generic.yaml`** (PM ruling 2026-10-24, (a)): `generic-theory` ("Theory") with
     the coach's two theory headings as aliases, and `generic-k` ("Generic K") with his K heading.
     Both are Policy only. `generic.yaml` goes from 1.0.0 to 1.1.0, and the Policy topic stays at
     the unreleased 1.1.0.
10. **The pass applies 45 of the 50 decisions.** The rest:
    * **Two headings the coach's sheet flags** as possibly naming a school or tournament, though
      filled `None`, are left out: a `none` would still put the heading in a committed file.
    * **Two he left blank.**
    * **`pharma`**, read on both sides, stays blank. One heading takes one decision.
    * The two `Theory` headings and the `Kritiks` heading are applied under the generic
      positions (question 9).
    * **`uq`**, decided `none`, was first refused by the personal-data check
      (`test_no_override_names_a_team_a_school_or_a_person`) as shaped like a team code: the check
      working, a real-data red run. No hspolicy26 disclosure uses `UQ` as a team code (0 of 555
      team-code directories in 9,052 paths). The coach confirmed it is "uniqueness" (condition 2),
      so it joined `SHORT_WORDS` in `tests/config` in the same commit as its decision, as the check's
      rule asks. It moves no count: a `none` on a block label passes cards up to the heading above.
    * One typo was corrected on the coach's say-so (`disease-a` to `disease-advantage`), and his
      `-adv` ids map to `-advantage`.
    * The decisions file is outside the repository:
      `~/Documents/debate/landscape-seed/policy-2026-27-nhi-decisions-2026-10-24.csv`. It was
      written from the coach's Numbers sheet, exported to `…-queue-top-50-filled.csv`. The original
      CSV and the Numbers file are untouched.
11. **`framework` names no position: the coach's decision** (question 10). He first placed it under
    `framework-t`. Under a K's own block, though, the heading is the K's framework, and with that
    decision 96 cards moved from Ks to T. With `none` they stay with the K: K documents
    151 → 145 → 151 and T 138 → 209 → 138, measured before the generic K was added. No decision
    takes a placement from any card. A decided heading lower on a path wins over an alias above it,
    which is why three aff documents lose their placed aff to an advantage.

12. **t09's producer is wired through this task's seam, not its own protocol.** t09's
    `AffAssignmentSource.aff_assignments(caselist, through)` reads the caselist and classifies it
    again. On hspolicy26 that is about 30 s more. It also writes the classification cache and the
    review queue, which a dry run must not (Decision 5). So `AffAssignmentService` is passed as the
    PM asked, and the run calls a new method on it, `assignments`. That method takes the run's own
    reading and classifications and does only the plan-text read and t09's
    `build_aff_assignments`. Its `writes` flag is False in a dry run, which reads the plan-text
    cache through `PlanTextService.without_writes()`. t09's protocol, `run` and tests are unchanged
    and pass. My protocol is renamed `AffAssignmentsFromReading`, so the two names cannot be
    confused.
    * The wiring test, `test_the_command_identifies_each_aff_round_through_t09s_plan_texts`, runs
      through the real composition root. It fails with the seam unwired, together with ac1's test
      (2 failed).
    * Making the dry run write the plan-text cache fails
      `test_publish_dry_run_lists_the_planned_uploads_and_writes_nothing`.
    * `synthetic26`'s `aff-two` now holds a real `.docx` with a plan text naming single payer, so
      its round is identified by `PLAN_TEXT`. ac1's hand-worked count of unidentified aff rounds
      changes from 1 to 0 for that reason.
13. **The sync moved coverage counts.** It brought t09's heading normalizer, which strips an
    advantage's number before its name. Measured read-only at 44 decisions, before and after the
    sync:
    * cards placed 63,462 → 63,494;
    * aff documents with a placed advantage 1,161 → 1,164;
    * aff documents with either 1,199 → 1,202, by teams 381 → 384.

    Nothing else moved. This is t09's rule, merged and reviewed there. It is reported because the
    PM's condition asks for a re-review when a count changes.
14. **A dry run reported the classification cache as written.** Under 1.1.0 every key is new, so
    t02's counts said `cache_written: true`, although the read-only view had dropped the write and
    every checksum was unchanged. The run now reports `false` in a dry run. The new assertion in
    `test_a_dry_run_lists_the_planned_uploads_and_writes_nothing` failed first (`True is False`).
    Found by the dry run on the real store.

## Decisions and assumptions

1. **Known values.**
   * A known caselist is one with at least one weekly manifest in this machine's evidence store.
     `manifests/_suppression/` and complete archives are not caselists.
   * A known snapshot is one of the caselist's weekly manifest dates. The default is the newest,
     as the staleness check reads it.
2. **Exit codes.**
   * The three `LandscapeRequestRefused` errors are mapped to `USAGE_ERROR` (2) in the command,
     with `known` and `file_to_edit` in the details. A missing taxonomy names `topics.yaml` too,
     since that is where `taxonomy_version` is given.
   * `NothingToReport` (no parsed source on the topic, so an empty store is never a report) and
     `ModelBudgetExceeded` are domain failures (1).
   * A publish the scan holds back prints the full result first, then fails with exit 1:
     `SCAN_HITS_NOT_ACCEPTED`, or `SCAN_DIGEST_STALE` when a digest was given.
3. **The scan before sharing** (rulings 2 and the brief's item 3).
   * **What it looks for:** every school, team code and tournament the report's own disclosures
     name, and their paths:
     * codes case-sensitively, as whole words;
     * schools and tournaments over three characters, as whole words without case;
     * paths as substrings.
   * **A hit** is one term in one line.
   * **The digest** is 12 hex digits over the keys of the hits not yet accepted, in no order.
     `--accept-scan-hits` is accepted only while it equals the digest of this run's hits. A dry run
     records nothing.
   * **The key that makes next week's hit the same hit:** the file, the kind, the term, and the line
     with every run of digits written `#`. Counts and ranks change every week, and rows move. A key
     on line numbers or counts would ask the operator to accept the same words weekly, until
     accepting meant nothing. A changed tag or cite is a new hit. The tests pin both directions.
   * **Where acceptances are kept:**
     `<data dir>/landscape/scan-acceptances/<caselist>.jsonl`, one line per acceptance, with each
     hit's key, file, kind and term. A line that cannot be read accepts nothing.
   * **The run's JSON:** the `--json` envelope carries every hit with its line, the digest,
     `accepted_now` and the log's path. It also carries a `notice` that the lines are for the
     terminal only. No `run.json` goes in the bundle: it would change every run and defeat the
     unchanged-object skip.
4. **Publishing.**
   * Keys are `reports/landscape/<caselist>/<snapshot>/<file>`, uploaded in the order
     `positions.csv`, `top_cards.csv`, `report.md`, so the page a person opens goes last.
   * A file goes up unless the bucket's recorded SHA-256 for the key equals the local one. An object
     with no recorded digest is treated as changed, as `store sync` treats one.
   * The stored digest is checked after each upload.
   * Dev or prod only; prod needs `--confirm-prod`; `DEBATE_ENV` defaults to dev (tested). No
     presigned URL is generated anywhere.
5. **A dry run writes nothing anywhere:** not the cache (a read-only view of it), not the queue,
   the bundle, the acceptance log or the bucket. With `--publish` it reads the bucket to plan.
6. **The report date** is today in UTC, from the container's clock, which the tests pin.
7. **`generic-theory` is `side: both`.** The PM's ruling named its label and aliases and not a side.
   The taxonomy's theory positions are sided by who reads them (condo bad aff, ASPEC neg), and a
   generic one collects either side's theory, so neither side's reads are set aside as answers.
   `generic-k` is `side: neg`, like every K in the file.
8. **The aff seam** passes t09's producer the reading, `through`, the classifications and the
   taxonomy: what t09's `build_aff_assignments` takes, as its branch stood on 2026-10-24.

## Operator follow-ups

### After the merge: the first dev run (ac5)

These blocks run in this task's worktree after the pull request merges and before
`scripts/task finish --partial`, on dev's squash commit of this pull request (the PM's ruling 8).

**0. Switch to the merged commit** (seconds). It finds the squash commit on `origin/dev` and switches
to it only when it is an ancestor of `origin/dev` and its tree is the task branch's, so the blocks
run exactly the code that merged.

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t05-landscape-cli
git fetch origin
SQUASH=$(git log origin/dev --format=%H --grep='^v1-e32-t05-landscape-cli: ' -n 1)
echo "squash commit: ${SQUASH:-none}"
if [[ -n "$SQUASH" ]] && git merge-base --is-ancestor "$SQUASH" origin/dev && git diff --quiet task/v1-e32-t05-landscape-cli "$SQUASH"; then
  git switch --detach "$SQUASH"
  echo "on the merged commit"
else
  echo "STOP: no squash commit, not on origin/dev, or its tree differs from the task branch. Tell the session."
fi
```

Success looks like a commit id, `HEAD is now at … v1-e32-t05-landscape-cli: …` and `on the
merged commit`. A `STOP` line means nothing below runs yet.

No plan-text pass is needed first: t09's cache is whole under 1.1.0 (Summary).

**1. The dry run** (expected runtime about 1 min; 42 s measured without the bucket). It stops on a
leftover `DEBATE_*` variable or a running `caselist pull`.

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t05-landscape-cli
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
echo "running pull: ${PULL:-none}"
echo "DEBATE_ overrides: ${OVERRIDES:-none}"
if [[ -n "$PULL" || -n "$OVERRIDES" ]]; then
  echo "STOP: the line above that is not none says why. Wait for the pull to finish, or open a new window."
else
  aws sso login --profile debate-dev-evidence
  DEBATE_ENV=dev uv run debate-research landscape report --caselist hspolicy26 --publish --dry-run
fi
```

Success looks like:
* `hspolicy26 through <date> on policy-2026-27-nhi 1.1.0 (overrides e1c2367c…`, naming the newest
  weekly snapshot, and `Sources N` with N above zero (3,825 on 2026-10-20);
* `Affirmative rounds with no identified aff: X of Y; aff assignments N`, with N above zero (940 of
  2,192 and 1,185 on 2026-10-20);
* `Current:`, not `STALE:`;
* `Dry run: nothing written`;
* `Publish to dev bucket …` with three `UPLOAD reports/landscape/hspolicy26/<date>/…` lines and
  `Nothing uploaded.`

**Read every `Scan:` line**, each with the report line it is in. Stop if any of them names a team,
and tell the session. When none does, copy the digest from `Scan: K hit(s), K not yet accepted
(digest …)`. A `0 hit(s)` scan needs no digest, and one given is then ignored.

**2. The publish**, with that digest in place of `DIGEST`:

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t05-landscape-cli
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
echo "running pull: ${PULL:-none}"
echo "DEBATE_ overrides: ${OVERRIDES:-none}"
if [[ -n "$PULL" || -n "$OVERRIDES" ]]; then
  echo "STOP: the line above that is not none says why. Wait for the pull to finish, or open a new window."
else
  aws sso login --profile debate-dev-evidence
  DEBATE_ENV=dev uv run debate-research landscape report --caselist hspolicy26 --publish --accept-scan-hits DIGEST
fi
```

Success looks like:
* `Sources N` above zero;
* `Accepted K hit(s) under digest DIGEST; recorded in …`;
* `Wrote positions.csv, top_cards.csv, report.md to …/reports/landscape/hspolicy26/<date>`;
* `Uploaded 3, unchanged 0.` and exit 0.

A run of the same block again says `Uploaded 0, unchanged 3.` with `Sources` still above zero: that
is "nothing to do", not "nothing there". `SCAN_DIGEST_STALE` means the hits changed since the dry
run; run block 1 again. Paste both outputs' counts back, but not the scan's lines.

**3. The coach reads the report**, from the path block 2 printed:

```bash
open ~/.debate-research/dev/reports/landscape/hspolicy26
```

He lists any taxonomy or override fixes for the next run. His answer, with both runs' aggregate
counts, goes into `docs/data/landscape/first-run-policy.md`.

**4. Back to the task branch** before `scripts/task finish --partial`:

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t05-landscape-cli
git switch task/v1-e32-t05-landscape-cli
```

Success looks like `Switched to branch 'task/v1-e32-t05-landscape-cli'`.

## Follow-up work

* **A failed weekly run as stale** (E34): the PM files the task (ruling 4).
* **`--model-mode` and `max_model_items`** (v1-e32-t07): join the option to `resolve_model_mode`,
  and set the bound from settings.
* **The weekly scheduled run** (E34) calls `LandscapeRunService` directly. It must supply an
  accepted digest, or publish only when nothing is pending. A scheduled run should never accept
  hits by itself.

## Questions for the PM

**Answered by the PM, 2026-10-24:**
1. Yes: `constraints.packages` amended with a PM-ruling comment (Deviation 1).
2. Yes: the command keeps its own `--model-mode none` until t07 joins it to `resolve_model_mode`.
3. Yes: ac2's budget clause is met on the seam; t07 sets the bound.
4. (a): the PM files an E34 task so that a failed latest run makes the hook report stale. The
   cap-bound half is met here.
5. Yes: ac4 is recorded from the first validate-dev run after the merge, with ac5.
6. Yes, an agreement 2 run. Block 1 (`--publish --dry-run`) is still the operator's.
7. Yes to `--config-dir`, `--confirm-prod` and refusing `--out` inside a checkout. `DEBATE_ENV` never
   defaults to prod, and no prod publish happens before the promotion.
8. Yes, with the switch to dev's squash commit first, checked as an ancestor of `origin/dev` with a
   tree equal to the branch head, and the switch back before `finish --partial` (blocks 0 and 4).

Kept as asked:

```text
v1-e32-t05 questions (session, 2026-10-24)

1. Amend constraints.packages with debate_core.testing (the shared synthetic26
   store), packages/debate_core/tests, packages/debate_cli/tests,
   docs/data/landscape and config/landscape (the coach's overrides)?
   Recommendation: yes, as for t02 and t03; the brief already names the last two.

2. --model-mode is the landscape command's own option with the one value
   `none`, and ignores DEBATE_MODEL_MODE: the shared option has no `none` and is
   argparse-only. Keep it until t07 joins it to resolve_model_mode?
   Recommendation: yes; t07 owns replay and live.

3. max_model_items: the run refuses (exit 1, queue written, nothing published)
   when its classifier reports more model items than the run's limit, which is
   0 while the mode is `none`. Tested with a stand-in classifier. Accept ac2's
   budget clause as met on this seam, with t07 setting the bound?
   Recommendation: yes; there is no model stage to exceed it until t07.

4. Ruling 1 says a cap-bound or failed weekly run shows as stale. The hook now
   gets the run log and a cap-bound run is stale (tested), but the hook
   (v1-e34-t03's) judges a failed run only by the snapshot's age, up to 8 days.
   (a) File an E34 task: the latest run that listed the caselist failed -> stale.
   (b) Change the hook here.
   Recommendation: (a); it is E34's rule and tests, and the cap-bound half,
   which is the one the brief tests for, is met.

5. ac4: the smoke check passes in the recorded tier against this checkout's
   console script; validate-dev's run of it happens on the pre-release the merge
   builds. Record ac4 from the first validate-dev run after the merge?
   Recommendation: yes, together with ac5.

6. I ran `landscape report --dry-run` on the real store before the merge,
   read-only, without --publish (no bucket), 46 s; it reproduced t03's preview
   and found 6 scan hits, kinds only recorded. Accept as an agreement-2 run?
   Recommendation: yes; the operator's --publish --dry-run is still block 1.

7. Two options the spec does not name: --config-dir (an installed build does not
   bundle config/landscape/) and --confirm-prod (as caselist publish has it);
   and --out is refused inside a checkout. Accept?
   Recommendation: yes.

8. Where the first dev run is made: this task's worktree after the merge and
   before `scripts/task finish --partial`, so the code is exactly what merged.
   Recommendation: yes; dev-preview is kept for site deploys.
```

**The second block, answered by the PM, 2026-10-24:** 9 (a), generic-theory and generic-k added to
`generic.yaml`, 1.1.0, with the three decisions applied. 10: the coach chose `none` for `framework`,
recorded with its numbers (Deviation 11).

Second block, after the coach's queue pass (2026-10-24), kept as asked:

```text
v1-e32-t05, the coach's queue pass, applied (session, 2026-10-24)

Applied: taxonomy 1.1.0 with the five positions (your ruling (b)), and 41 of
the coach's 50 decisions; tests/config passes. Cards placed 48.1% -> 50.0%;
neg documents with any placed position 35.8% -> 40.9%; full table in
docs/data/landscape/first-run-policy.md.

9. For two `Theory` headings and one `Kritiks` heading the coach wants one
   generic theory position and a generic K (his words: "one theory id for those
   arguments", "a generic-k label"). generic.yaml holds Policy's other Ks and
   theory positions.
   (a) Add `generic-theory` ("Theory") and `generic-k` ("Generic K") to
       generic.yaml, Policy only, with those headings as aliases; generic.yaml
       1.0.0 -> 1.1.0, the Policy topic stays at the unreleased 1.1.0; then
       apply the three decisions.
   (b) Leave the three headings undecided for the first report.
   Recommendation: (a); the coach asked for both, they are format-level, and
   folding them into the unreleased 1.1.0 costs no second bump.

10. `framework` -> framework-t (the coach's decision) moves 96 cards from Ks to
    T, since under a K's own block "framework" is the K's framework. K
    documents 151 -> 145, T 138 -> 209. Keep it, or leave `framework` blank
    like `pharma` (read both ways)?
    Recommendation: ask the coach with that number in front of him; if he
    keeps it, keep it.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED, with conditions closed in-session
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-24

**Notes:**

A clean command over a tested service.
* The scan's accept rule makes next week's same hit the same hit: digits are masked, and line
  numbers and counts are kept out of the key. Without that, accepting would come to mean nothing.
* The unchanged-object skip is checked after upload. 22 mutants were caught.
* The real-store dry run reproduces t03's preview count for count.
* The coach's pass is applied with every exception explained. Leaving out the two flagged rows,
  even though he filled them `none`, is exactly right: a `none` would still put the heading in a
  committed file.

**Deviations 1 to 11 and Decisions 1 to 8 are accepted.** `generic-theory` as `side: both` is the
right reading of the ruling.

**Conditions, to close in this session before the PR:**

1. **Wire t09's producer now.** v1-e32-t09 merged before this task, so by the PM's rule this task
   wires it.
   * `scripts/task sync` first. t09 touched `render.py` and the golden report.
   * Pass `AffAssignmentService` as `aff_assignments` in `ServiceContainer.landscape_run`, with a
     test on the synthetic store. Bring the pinned integration list into agreement with what t09
     added.
   * Check whether t09's local plan-text cache is still valid under taxonomy 1.1.0. Its key holds
     a vocabulary digest, so say whether this pass changed it. If the cache is no longer valid, the
     first full plan-text pass (about 3.5 min) becomes an operator block between blocks 0 and 1.
   * The first dev run then publishes with the aff identified, and block 5 is no longer needed.
2. **`uq`: the coach confirms it is "uniqueness"** (the PM relayed it, 2026-10-24). Add it to
   `SHORT_WORDS` in `tests/config` in the same change, as the check's own rule requires. Apply the
   decision (45 of 50), and re-measure the coverage table.
3. **Remove the stale "Before the pull request" section** (the pass is applied). Then update the
   Summary, the counts, the first-run note and Operator follow-ups for conditions 1 and 2. No
   re-review is needed unless condition 1's sync or wiring changes a count or a rule.

**The PR:** opened with `--partial`. ac4 (validate-dev's run) and ac5 (the first dev run and the
coach's review) follow the merge, and the PM records them. Blocks 0 to 4, on dev's squash commit,
are accepted as written. Paste the counts back, but not the scan's lines.

**Follow-up work:**
* The E34 failed-run staleness task is filed by the PM.
* `--model-mode` and the budget belong to t07.
* The weekly scheduled run never accepts hits by itself. That is recorded for E34's integration.

If anything comes out differently, stop and ask for another review.

## After the PM review of 2026-10-24: conditions closed

The PM's review above accepted the task with three conditions, closed in this session:
1. t09's producer is wired (Deviation 12), and the pinned list has 18 entries. t09's plan-text cache
   is valid under 1.1.0, so no plan-text block is needed.
2. `uq` is in `SHORT_WORDS` and applied, 45 of 50, with coverage measured again.
3. The stale section is removed, and the Summary, counts, first-run note and follow-ups are updated.

Third block, for the re-review the conditions ask for (2026-10-24):

```text
v1-e32-t05 after the PM's conditions (session, 2026-10-24)

Conditions 1 to 3 are closed. Your line was a re-review if the sync or the
wiring changed a count or a rule; both did:

11. The sync brought t09's normalizer (an advantage's number stripped): cards
    placed 63,462 -> 63,494, aff documents with a placed advantage 1,161 ->
    1,164, aff teams with either 381 -> 384. Nothing else moved. Accept?
    Recommendation: yes; it is t09's reviewed rule.

12. The wiring: t09's own aff_assignments(caselist, through) reads and
    classifies the caselist again (~30 s) and writes the cache and queue,
    which a dry run must not. So AffAssignmentService is passed as you asked,
    but the run calls a new method on it, assignments(reading, through,
    classifications, taxonomy, writes), sharing t09's plan-text step; a dry run
    reads the plan-text cache without writing it. On hspolicy26, read-only:
    aff rounds unidentified 1,998 -> 940 of 2,192 (plan text 959, team carry
    226, placed card 67); rounds with a read 50.6% -> 60.2%. Accept?
    Recommendation: yes; it keeps Decision 5 and t09's tests unchanged.

13. Found on the real store: a dry run reported the classification cache as
    written (cache_written: true) while every checksum was unchanged; it now
    reports false in a dry run, test shown failing first. Accept?
    Recommendation: yes.

Then: scripts/task pr --partial, and blocks 0 to 4 after the merge.
```

**Criteria still open**, so the pull request opens with `--partial` and the Goal stays `InProgress`:

| Criterion | Status | Why |
|---|---|---|
| ac4: the smoke check passes in the validate-dev recorded tier | NOT RUN | It passes in the recorded tier locally (2 passed after the sync). validate-dev runs it on the pre-release the merge builds, and the PM records it with ac5 |
| ac5: the first dev run published, its counts in the first-run note, the coach's review before 2026-11-07 | NOT RUN | Blocks 0 to 4 run after the merge, on dev's squash commit |
| first-dev-run: the coach reviews the first Policy report | NOT RUN | With ac5 |

## PM review, second

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-24

**Notes:**

11. **Accepted.** The movement is v1-e32-t09's reviewed normalizer rule: 32 more cards placed, and
    3 more aff documents and teams with a placed advantage. Nothing else moved.
12. **Accepted.** Calling a new `assignments(reading, through, classifications, taxonomy, writes)`
    keeps a dry run truly read-only, which is right (Decision 5), and it shares t09's plan-text step
    without changing t09's tests. On hspolicy26 the first report now identifies the aff in 1,252
    of 2,192 aff rounds (940 unidentified, against 1,998 before), and rounds with a read rise from
    50.6% to 60.2%.
13. **Accepted.** A dry run reporting `cache_written: true` was a real bug, and the test was shown
    failing first.

**The PR:** `scripts/task pr --partial`. After the merge, run blocks 0 to 4 on dev's squash commit.
**Block 2's `--publish` waits until v1-e32-t08 has merged.** Right after the publish, the operator
runs t08's lock writer for 1.1.0 (the PM's ruling on t08, 2026-10-24), and the PM commits the lock
in a PM batch.

## PM record, 2026-10-24

Added by the PM. Nothing above is changed, and this section is not a review.

* **ac5 and the first-dev-run node: done.** Blocks 0 to 4 ran on dev after the merge: the dry run,
  the scan's 6 hits read and accepted (`ae969d4918b6`), the publish, and the release of taxonomy
  1.1.0 (recorded in the PM batch of 2026-10-24 (i)). The coach reviewed the Policy report on
  2026-10-24, before 2026-11-07, with no fixes; his review is in
  [the first-run note](../data/landscape/first-run-policy.md#the-coachs-review).
* **ac4 is still to be recorded:** the PM records validate-dev's result for the recorded tier, which
  runs the landscape smoke check, and then sets the Goal `Succeeded`.
