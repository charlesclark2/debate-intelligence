# Session report: v1-e32-t05-landscape-cli

| | |
|---|---|
| Task | `v1-e32-t05-landscape-cli` — `debate-research landscape` command |
| Spec | [`plan_specs/v1/e32-argument-landscape/t05-landscape-cli.yaml`](../../plan_specs/v1/e32-argument-landscape/t05-landscape-cli.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t05-landscape-cli` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

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

`--model-mode none` is the only mode, so no run calls a model. t09's aff assignments plug in through
an optional `AffAssignmentSource`. Until then the report shows the unidentified share.

**Status: PARTIAL, waiting on one input.** Every node through the smoke check is done, and its
criteria pass. ac1 to ac3 pass, and ac4 passes in the recorded tier locally.

* **The coach's queue pass is applied** (the PM's item 4), as far as it can be today:
  * five new positions, as taxonomy 1.1.0 (PM ruling (b), Deviation 9);
  * 41 of the 50 decisions;
  * coverage measured before and after: cards 48.1% → 50.0%, negative documents with any placed
    position 35.8% → 40.9%.
* **Waiting on:** three headings need generic theory and K positions that do not exist (PM
  question 9), and one needs the coach's word that `uq` is debate vocabulary (Deviation 10).
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
| first-dev-run | Partly done | The coach's queue pass is applied: five positions (taxonomy 1.1.0) and 41 decisions in `config/landscape/overrides/policy-2026-27-nhi.yaml`, `tests/config` 23 passed. `docs/data/landscape/first-run-policy.md` records coverage before and after. The dev run and the coach's review are operator follow-ups after the merge |

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
* **`debate_cli/commands/landscape.py`** (new), registered in `commands/__init__.py`.
* **`debate_cli/container.py`**: `landscape_run`, wiring `YamlTaxonomyRepository` and
  `LocalClassificationStore`, the run log, the acceptance log and the bucket. The aff seam is left
  unwired, with the PM's rule for wiring it in the method's docstring.
* **Tests:**
  * `packages/debate_core/tests/application/test_landscape_run.py` (26) and
    `test_landscape_scan.py` (11);
  * `packages/debate_cli/tests/test_landscape_command.py` (16);
  * `packages/debate_cli/tests/test_installation.py` and `commands/test_doctor.py`: the hand-pinned
    list of wired integrations gains `landscape.classification_store` and
    `landscape.yaml_taxonomy_repository`, so the count goes from 15 to 17.
* **`tests/smoke/test_landscape_smoke.py`** (new) and its row in `tests/smoke/README.md`.
* **`docs/data/landscape/first-run-policy.md`** (new): the first-run note, with the before-pass
  coverage.

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
10. **The pass applies 41 of the 50 decisions.** The rest:
    * **Two headings the coach's sheet flags** as possibly naming a school or tournament, though
      filled `None`, are left out: a `none` would still put the heading in a committed file.
    * **Two he left blank.**
    * **`pharma`**, read on both sides, stays blank. One heading takes one decision.
    * **Two `Theory` headings and one `Kritiks` heading** wait on generic positions (question 9).
    * **`uq`**, decided `none`, is refused by the personal-data check
      (`test_no_override_names_a_team_a_school_or_a_person`) as shaped like a team code. It is the
      check working: a real-data red run. No hspolicy26 disclosure uses `UQ` as a team code (0 of 555
      team-code directories in 9,052 paths). The check's own rule is that a real two-letter word goes
      into `SHORT_WORDS` in `tests/config` in the same change, and I have not done that without the
      coach's word that it is "uniqueness".
    * Two typos were corrected on the coach's say-so (`disease-a` to `disease-advantage`,
      `framework` to `framework-t`), and his `-adv` ids map to `-advantage`.
    * The decisions file is outside the repository:
      `~/Documents/debate/landscape-seed/policy-2026-27-nhi-decisions-2026-10-24.csv`. It was
      written from the coach's Numbers sheet, exported to `…-queue-top-50-filled.csv`. The original
      CSV and the Numbers file are untouched.
11. **One decision moves cards between kinds.** `framework` → `framework-t` moves 96 cards from Ks
    to T, because under a K's own block the heading is the K's framework. That is most of why K
    documents fall from 151 to 145 and T rises from 138 to 209. No card loses a placement: 1,657 are
    newly placed, and 291 move to another position. Question 10.

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
7. **The aff seam** passes t09's producer the reading, `through`, the classifications and the
   taxonomy: what t09's `build_aff_assignments` takes, as its branch stood on 2026-10-24.

## Operator follow-ups

### Before the pull request: the coach's pass over the review queue

The sheet `~/Documents/debate/landscape-seed/policy-2026-27-nhi-queue-top-50.csv` has its
`decision` column empty in all 50 rows. When the coach has filled it, the session applies it with
t02's `apply-decisions`, which skips blank rows, so the two rows marked to leave blank stay blank.
It commits `config/landscape/overrides/policy-2026-27-nhi.yaml` with `tests/config` passing. It then
measures the coverage again, read-only, and records it with the new overrides digest.

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

**1. The dry run** (expected runtime about 1 min; 46 s measured without the bucket). It stops on a
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
* `hspolicy26 through <date>` naming the newest weekly snapshot, and `Sources N` with N above
  zero (3,825 on 2026-10-20);
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

**5. With t09's assignments.** When t09's producer is wired into `landscape_run` by whichever task
merges second, its first full plan-text pass is t09's own block (several minutes, in t09's report).
Blocks 1 and 2 then run again.

## Follow-up work

* **The aff seam** (v1-e32-t09, or this task if it merges second): pass t09's producer as
  `aff_assignments` in `ServiceContainer.landscape_run`, with a test. Merging also needs the pinned
  integration list (17) to agree with whatever t09 adds.
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

Second block, after the coach's queue pass (2026-10-24):

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

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
