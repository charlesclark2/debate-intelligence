# Session report: v1-e40-t17-landscape-report-from-the-cloud-runs-state

| | |
|---|---|
| Task | `v1-e40-t17-landscape-report-from-the-cloud-runs-state` — A landscape report counts the weeks the cloud run pulled, from a copy restored from the bucket |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t17-landscape-report-from-the-cloud-runs-state.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t17-landscape-report-from-the-cloud-runs-state.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t17-landscape-report-from-the-cloud-runs-state` |
| Session status | PARTIAL: built and tested; the operator's hspolicy26 proof publish (ac3) waits for the merge |

## Summary

`debate-research landscape report --restored-copy <copy>` builds a caselist's report from a copy restored
from the dev bucket, which holds the cloud run's weeks. It reads the copy's manifests, parsed store
(including the model stage's card texts), suppression list, run log and raw sources. Every piece of the
landscape's own state stays in the dev data directory: the classification cache, the review queue, the
plan-text and analytic-text caches, the scan acceptances, the cassettes, the usage log and the bundle.
That is the PM's ruling of 2026-10-30, Q1 to Q4. It refuses a copy that is the data directory, lies
inside it or holds it, lies inside a checkout, or is no directory (exit `2`). It also refuses a copy whose
newest parsed directory is not this build's parser version (exit `2`). In bucket mode a publish without a
copy is refused (exit `1`), with the hint naming the new runbook. Every dry run now says how many cards it
would ask the model about (`classification.model.would_ask`).

**Q5, the parser version: the cloud's weeks are in `2026.10.20-docx-6` directories.** The run image
deployed on 2026-10-29 is `03b23e2`, whose `DOCX_PARSER_VERSION` is `"2026.10.20-docx-6"`, and
`f8e51f1` (the bump to `docx-7`) is not its ancestor (`git merge-base --is-ancestor f8e51f1 03b23e2`
fails). That was checked in code, not by listing the bucket, which needs AWS. An optional read-only
listing is under Operator follow-ups, and on the day the runbook's restore prints `parsed_objects` for
this build's version anyway. So the runbook parses the copy with this build, into the copy, before the
report (its step 2).

**The PM should look first at** Deviation 1 (the parse step sets `DEBATE_STORAGE__DATA_DIR` for one
command), and at the data-use policy sentence proposed in Follow-up work.

The Goal stays **InProgress**: ac3's operator publish of hspolicy26's newest snapshot through the
runbook can only run after the merge. It is also `v1-e32-t29`'s republish, with `--model-mode none`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `report-from-restored-copy` | Done | Counts and relay (ac1), the PM's ruling, red tests against a skeleton, the build, 20 mutants all caught, the runbook. Its criterion passes |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts first, by path, which a copy holds, and a proposal before building | PASS | The table under [Counts](#counts-what-landscape-report-reads-and-writes-ac1-2026-10-30), committed in `61fcd55` before any code, and the relay with Q1 to Q4. The PM ruled on 2026-10-30 and added Q5 |
| ac2: a report over a copy counts its newest snapshot and keeps the state in the data directory, so a second report classifies nothing already classified; tests on a synthetic store, red first; the dry run prints what it would classify | PASS | Red: `511ea41`, 27 failed and 14 passed against a skeleton that refuses nothing; the 14 are the go-ahead cases and tests that already existed ([Red run](#red-run)). Green: `.venv/bin/python -m pytest packages/debate_core/tests/application/test_landscape_restored_copy.py packages/debate_cli/tests/test_landscape_command.py` → `78 passed`, then 80 with the two tests added in `9b453e9`. In particular `test_a_report_over_a_restored_copy_counts_its_newest_snapshot_and_keeps_the_state_here` (the stale data directory says 2026-09-08 and the copy 2026-09-15), `test_a_second_report_over_a_fresh_copy_classifies_nothing_already_classified` (replay: 2 asked, the copy deleted, a new copy restored, 0 asked, 2 cached, cache misses 0) and `test_every_dry_run_says_how_many_cards_it_would_ask_the_model_about`. Mutants: 20 of 20 caught ([Mutants](#mutants)) |
| ac3: the runbook's blocks (restore, dry run with its counts, publish, the copy deleted) | PASS (blocks) | [`docs/runbooks/landscape-report-from-the-cloud-run.md`](../runbooks/landscape-report-from-the-cloud-run.md): the checks, restore, parse dry run, parse, report dry run (with `would_ask`), hits read in the terminal, publish, publish with an accepted digest, and the copy deleted. Every block refuses a Wednesday or a `DEBATE_` override, and the restore and the publish take the run lock. `zsh -n` passes on all 9 blocks and each Python one-liner compiles. The dry run's one-liner was run against a real dry run over a synthetic copy and against a refusal. `scripts/check_command_blocks.py` → `OK`; `tests/docs` → `146 passed` |
| ac3: the operator's publish of hspolicy26's newest snapshot to dev through the blocks, recorded as counts | NOT RUN | The operator's, after the merge (it needs the release carrying this task, AWS and the dev lock). Under Operator follow-ups |
| Node: Landscape CLI tests pass (`uv run pytest packages/debate_cli/tests -k landscape`) | PASS | `62 passed in 13.73s` |

## Red run

Against `511ea41`, where every new name existed and nothing was wired or refused:
`.venv/bin/python -m pytest packages/debate_core/tests/application/test_landscape_restored_copy.py
packages/debate_cli/tests/test_landscape_command.py -k "<the new and changed tests>"` → `27 failed, 14
passed`. Grouped, the failures were the refusal functions returning `None` (9), `DID NOT RAISE
ParsedVersionNotInStore` (2) plus one `SeedingCannotStart`, a report reading the stale data directory
(snapshot 2026-09-08 and 1 card asked instead of 2), and `KeyError` on the new `would_ask` and
`restored_copy` keys. One test of mine failed for a reason of its own: the container test's glob picked
the occurrence table. It was fixed and then failed for its intended reason (`{}`, no text read from the
copy). The 14 that passed were the five go-ahead cases of the two refusal functions, the three service
cases that need no check, the two bucket-mode lock tests (which ignore the option either way), the two
"a dry run or a report kept here needs no copy" cases, and two older tests whose names matched the
filter.

The suppression-list and run-log tests (`9b453e9`) were written after the build, when tracing the wiring
showed nothing would catch those two lines reading the data directory. Their mutants, below, show each
failing for its reason.

## Mutants

20 mutants of the refusals and the wiring, in three batches of under two minutes
(`scratchpad/mutants.py`). Each ran both test files with `-x -n 4` and was restored with `git checkout
HEAD --`, with the tree clean after each. No Hypothesis property is involved. Batch one's verdict line
read the exit code, which is 2 for a failure under `-x` with xdist. Each of its seven summaries names the
intended test failing on an assertion, and the script read the summary from then on.

| Mutant | Caught by |
|---|---|
| copy: no directory check | `test_a_path_that_is_no_directory_is_refused` |
| copy: the data directory itself accepted | `test_the_data_directory_itself_is_refused` |
| copy: inside the data directory accepted | `test_a_directory_inside_the_data_directory_is_refused` |
| copy: holding the data directory accepted | `test_a_directory_holding_the_data_directory_is_refused` |
| copy: inside a checkout accepted | `test_a_directory_inside_a_checkout_is_refused` |
| copy: links not resolved | `test_a_link_to_the_data_directory_is_the_data_directory` |
| publish: local mode refused too | `test_everything_else_goes_ahead[local mode, publish]` |
| publish: a dry run refused | `test_everything_else_goes_ahead[bucket mode, a publish's dry run]` |
| publish: a copy does not satisfy it | `test_everything_else_goes_ahead[bucket mode, publish from a copy]` |
| publish: never refused | `test_a_publish_in_bucket_mode_without_a_copy_is_refused_naming_the_runbook` |
| version: never checked | `test_a_copy_parsed_only_by_an_older_build_is_refused_before_anything_is_written` |
| version: the oldest directory compared | `test_a_copy_whose_newest_directory_is_a_later_builds_is_refused` |
| version: any directory of this version will do | the same |
| CLI: the copy refusals never asked | `test_a_copy_that_is_not_one_is_refused_with_exit_2_and_nothing_is_written` |
| container: no parser version given | `test_a_copy_no_build_of_this_version_parsed_is_refused_naming_caselist_parse` |
| container: the data directory's suppression list | `test_a_source_the_copys_suppression_list_holds_is_not_counted` |
| container: the data directory's run log | `test_the_status_line_reads_the_copys_run_log` |
| container: the model stage's card texts from the data directory | `test_a_second_report_over_a_fresh_copy_classifies_nothing_already_classified` |
| model stage: `parsed_dir` ignored | `test_the_container_reads_the_model_stages_card_texts_from_the_directory_it_is_given` |
| CLI: `would_ask` counted in a run that writes | `test_a_run_that_writes_has_no_would_ask_count` |

The smoke check was also shown failing: with the CLI not passing the copy to the container, it read
`2026-09-08`, not `2026-09-15`.

## Files changed

* `packages/debate_core/src/debate_core/application/landscape_restored_copy.py` (new): the two refusals
  and the runbook's path.
* `packages/debate_core/src/debate_core/application/landscape_run.py`: `parser_version` and
  `ParsedVersionNotInStore`, the check of the store's newest parsed directory.
* `packages/debate_cli/src/debate_cli/container.py`: `landscape_run(restored_copy=)` wires the cards
  side to the copy and the state side to the data directory; `landscape_model_stage(parsed_dir=)`.
* `packages/debate_cli/src/debate_cli/commands/landscape.py`: `--restored-copy`, the refusals, `--json`'s
  `restored_copy` and `classification.model.would_ask`, the dry run's line, and the module docstring.
* `packages/debate_core/tests/application/test_landscape_restored_copy.py` (new), and
  `packages/debate_cli/tests/test_landscape_command.py`: the tests. The two bucket-mode lock tests now
  publish from a copy, as Q3 requires.
* `packages/debate_cli/tests/test_container_factories.py`: values for the two new parameters.
* `tests/smoke/test_landscape_smoke.py`: the installed build's dry run over a copy (Deviation 2).
* `docs/runbooks/landscape-report-from-the-cloud-run.md` (new): the operator's steps.

## Deviations from the spec

1. **The parse step sets `DEBATE_STORAGE__DATA_DIR`, for one command.** Q1 says "No
   DEBATE_STORAGE__DATA_DIR override anywhere in this path", and Q5 asks for `caselist parse` into the
   copy. `caselist parse` writes the parsed store and its card statistics (the database) into the data
   directory it runs over, and takes no directory option. So step 2's two blocks run it as `env
   DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="$COPY" debate-research ... caselist parse` (as `v1-e31-t31`'s
   and the cutover's blocks do), without `--publish`, after refusing any `DEBATE_` override already set.
   The report, its dry run and its publish set none. I read Q1 as being about the report. If the PM wants
   none at all, the alternative is a `--restored-copy` on `caselist parse`, which would also need a
   database over the copy. That is more surface than this task's deadline allows, and I did not build it.
2. **`tests/smoke/` is outside `constraints.packages`.** `plan_specs/README.md` asks a task that changes
   a user-facing surface to add its smoke check, so `test_landscape_smoke.py` gained one test. Pyright
   covers it since `v1-e01-t35`; it passes.
3. **No landscape publish steps existed in `docs/runbooks/`** to put the blocks beside. They are a new
   runbook, `landscape-report-from-the-cloud-run.md`.

## Decisions and assumptions

### Counts: what `landscape report` reads and writes (ac1, 2026-10-30)

Traced in code at `cddb5f0` (`ServiceContainer.landscape_run`, `landscape_model_stage`,
`LandscapeRunService.run`, the stores under `debate_core.integrations.landscape`), with sizes measured
read-only on the operator's dev data directory. Paths are under the data directory unless marked.

| Path | Report (dry run) | Report (`--publish`) | A restored copy holds it? |
|---|---|---|---|
| `objects/manifests/<caselist>/<date>.jsonl` | read: caselists, snapshots, disclosures, staleness | same | **Yes**, every week the cloud ran |
| `parsed/<caselist>/<parser version>/` | read: cards, occurrences; the model stage's card texts | same | **Yes**, this build's version (`2026.10.27-docx-7`); the data dir holds `2026.10.20-docx-6` only |
| `blobs/sha256/…` (raw sources) | read: plan texts and analytic texts parse what their caches lack, and the quoted CP texts, planks, alternatives and roles of the ballot are re-read from raw bytes on every run | same | **Only with `--with-sources`**, for the `--snapshot` weeks named; the data dir holds everything through 2026-10-20 (4.0 GB, all caselists) |
| `suppression/` | read | same | **Yes**, reconciled with the bucket's |
| `caselist-sync-runs.jsonl` (run log) | read: the failed-run line of staleness | same | **Yes**, the cloud's; the data dir's stops on 2026-10-25 |
| `debate.sqlite3` | not read | not read | Yes (unused here) |
| `config/landscape/` (checkout) | read | read | n/a: the checkout |
| `landscape/classifications/<caselist>.jsonl` (47 MB) | read | read, written | **No**: data dir only |
| `landscape/review/<caselist>/<topic>-review-queue.csv` | not written | written | **No** |
| `landscape/plan_texts/<caselist>.jsonl` (0.9 MB) | read | read, written | **No** |
| `landscape/analytic_texts/<caselist>.jsonl` (1.7 MB) | read | read, written | **No** |
| `landscape/scan-acceptances/<caselist>.jsonl` | read | read, written on an accept | **No** |
| `landscape/model-cassettes/<prompt>/` | read under `replay` | read under `replay`; `live` passes through and records nothing | **No** (absent today: no model run yet) |
| `usage/<day>.jsonl` (model usage, the budget) | not written | written per live call | **No** (absent today) |
| `reports/landscape/<caselist>/<snapshot>/` (7 files) | not written | written; read later by removal residue and the annual purge | **No** |
| `landscape/local-classifier/<caselist>/` (47 MB) | not read | not read (`scripts/compare_local_classifier.py` only) | **No** |
| bucket `reports/landscape/<caselist>/<snapshot>/` | `head` per file (with `--publish --dry-run`) | `head`, `put` | n/a |
| bucket run lock | not taken | taken (dev is in bucket mode) | n/a |

Three facts the proposal rests on:

1. **The plan-text and analytic-text caches key on the running build's parser version**, and hold
   `2026.10.20-docx-6` only. A `docx-7` build's next report re-parses every on-topic hspolicy26
   source for both, from raw bytes, whichever store it reads. The analytic texts' first fill took
   551 s on 2026-10-24. The classification cache keys on card fingerprints and taxonomy, not parser
   version.
2. **Raw bytes are read on every run**, not only on a cache miss: the quoted texts are re-read. So a
   copy restored with the newest week's sources alone lacks the bytes of every older quoted source.
3. **`DEBATE_STORAGE__DATA_DIR=<copy>` would move all of the "No" rows into the copy**: the
   classification cache, the review queue, the text caches, the scan acceptances, the bundle, and the
   usage log the model budget is counted from. Each would be lost when the copy is deleted.

### Choices made while building

* **The copy's suppression list alone**, not merged with the data directory's. The restore reconciles
  the copy's list with the bucket's, and every removal records in the bucket. That is the list a hand
  publish from a copy reads too.
* **The version check compares the newest parsed directory** of the caselist with this build's parser
  version. The report reads that newest directory anyway, so a copy holding `docx-7` beside `docx-6`
  reads `docx-7`, and one holding a later build's is refused. It runs after the caselist and the
  snapshot are resolved, so an unknown caselist is refused as before, with the known ones.
* **The refusals name no path.** The operator typed the copy's path, and the restore never logs it.
* **`would_ask` is `null` in a run that writes**, so a program reading `--json` cannot mistake what was
  asked for what would be. In a dry run under `none` it is 0, and the line says `--model-mode none
  asks it nothing`.
* **The runbook's copy is `~/.debate-research/landscape-copy-<caselist>`.** Step 5 deletes only a path
  of that form, then counts the copies left, which must be 0.
* **The runbook's dry run is `--publish --dry-run`,** which also plans the uploads and asks the bucket,
  so it signs in first. The first dry run on a `docx-7` build reads every on-topic source again for
  the text caches, and keeps none of it, so the publish reads them again. The block's expected runtime
  says so.

## Checks run before the report

* `uv run scripts/affected_tests.py` → `206 of 572 test files (36.0%) chosen in 20.1 s from 11 changed
  files`. The whole default selection takes about six minutes on this Mac, and the load average was 6
  to 13 from other sessions, so the 206 files would take well over two minutes. Under agreement 10 that
  run is left to the pull request's `ci`, which runs the same set, and was not handed to the operator.
* Within two minutes instead: the always-run list (`tests/architecture`, `tests/specs`, `test_app.py`,
  `test_help_rendering.py`, `test_container_factories.py`), every `test_landscape_*` file in
  `packages/debate_core/tests/application`, `test_file_suggest_service.py`,
  `packages/debate_cli/tests/test_landscape_command.py`, `commands/test_files.py`,
  `packages/debate_cli/tests/bucket_mode/` and `tests/smoke/test_landscape_smoke.py` →
  `1 failed, 880 passed in 95.16s`. The failure was `test_container_factories.py` asking for values
  for the two new parameters, added in `266f9c6`; that file then gave `6 passed`.
* `uv run --frozen ruff check .` → `All checks passed!`; `uv run --frozen ruff format --check .` →
  `1605 files already formatted`.
* `.venv/bin/pyright packages/debate_core packages/debate_cli tests/smoke/test_landscape_smoke.py` →
  `0 errors, 0 warnings, 0 informations`.
* `uv run --frozen lint-imports` → `Contracts: 18 kept, 0 broken`;
  `scripts/check_thin_handlers.py` → `OK: 68 CLI command and API route handlers within 25 statements`.
* `uv run --frozen python scripts/docs_index.py --check-descriptions` → `All 59 indexed documents under
  docs/ have a description`; `scripts/check_command_blocks.py` → `OK`; `tests/docs` → `146 passed`.
* `uv run scripts/validate_specs.py` → `OK: 494 files, 40 epics, 432 tasks, 22 releases`.

## Operator follow-ups

1. **ac3, after the merge: hspolicy26's newest snapshot published to dev through the runbook.** Install
   the dev release that carries this task. Then run
   [`docs/runbooks/landscape-report-from-the-cloud-run.md`](../runbooks/landscape-report-from-the-cloud-run.md)
   from "Before you start" to step 5 with `CASELIST=hspolicy26`, not on a Wednesday. Expected runtime,
   end to end, about 35 to 55 minutes:
   * the restore, 3 to 10 min;
   * the parse, 12 to 15 min;
   * the dry run, 5 to 12 min;
   * the publish, about as long as the dry run.

   Send the PM step 1's grep lines, step 2's two sets of lines, step 3's lines (before the publish),
   step 4's lines and step 5's `0`. They hold counts, versions and a digest only. This is also
   `v1-e32-t29`'s republish (Harms under Impact), with no model spend.

2. **Optional: what the dev bucket's parsed store holds, per caselist and version** (Q5, read-only,
   about a minute). The restore's `parsed_objects` says the same for this build's version on the day,
   so this is only for an answer before then.

   **Operator command** (expected runtime ~1 min)
   Where: your Mac
   ```bash
   aws sso login --profile debate-dev-evidence
   cd "$HOME" && BUCKET=$(env -u DEBATE_STORAGE__DATA_DIR DEBATE_ENV=dev debate-research --json config show | python3 -I -c 'import json, sys; print(json.load(sys.stdin)["data"]["settings"]["storage.s3.bucket"])') && aws s3 ls "s3://${BUCKET}/parsed/" --recursive --profile debate-dev-evidence | awk '{ print $4 }' | cut -d/ -f2-3 | sort | uniq -c
   ```
   Success looks like one line per caselist and version with its object count, such as `15000
   hspolicy26/2026.10.20-docx-6`. The answer above predicts `2026.10.20-docx-6` directories for
   `hsld26`, `hspolicy26`, `hspf26` and `openev`, and no `2026.10.27-docx-7`.

## Follow-up work

* **The data-use policy's restored copy names "a comparison or a hand publish"** (version 1.18,
  "Where personal data is allowed to live" and the retention table). A landscape report from a copy is
  a third purpose, kept for the same one step and deleted by the runbook. The policy is the PM's to
  change, so I changed only the runbook. A proposed sentence: "a working copy restored on the operator's
  machine from a bucket, for a comparison, a hand publish or a landscape report (`v1-e40-t17`), for the
  length of that step".
* **The prod re-parse and publish of `docx-7`** (`v1-e31-t31`'s blocks C3 to C9) has not run, so every
  week the cloud runs with the `docx-6` image needs step 2's full parse in each copy: about 12 to 15
  minutes for hspolicy26, and something similar for hsld26. Once the run image carries `docx-7` and the
  bucket holds its parsed directories, step 2 parses only what the copy lacks. That belongs to
  `v1-e31-t31`'s operator steps or `v1-e40-t08` (parse owed).
* **The text caches are re-read after every parser bump, and a dry run keeps none of it.** A dry run
  that wrote the plan-text and analytic-text caches, which hold derived fields and no evidence text,
  would halve the first report's time after a bump. That was not built, since a dry run writes nothing
  by `v1-e32-t05`'s rule. A candidate for E32.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-30

**Notes:**

A landscape report can now count the weeks the cloud run pulled, with nothing of the landscape's state
put at risk.
1. **ac1 passes.** The table traces every path the report reads and writes, which a copy holds and
   which only the data directory does, with sizes. Its three facts decided the design: the text caches
   key on parser version, raw bytes are read every run, and a data-directory override would strand the
   usage log and the classifications.
2. **ac2 passes.** Red: 27 failed against a refuse-nothing skeleton. Green: 80 passed.
   * The report over a copy counts the copy's week (09-15), not the stale directory's (09-08).
   * A second report over a fresh copy asks the model about 0 cards, with 2 cached. That is
     classify-once, shown.
   * Every dry run says how many cards it would ask about.
3. **Mutants:** 20, all caught: every refusal, each wiring line (the suppression list, run log and card
   texts each read from the copy), and the `would_ask` rule. The two tests you added after tracing
   showed nothing caught the suppression-list and run-log lines. That is agreement 8 working.
4. **Q5 is answered, in code:** the image deployed on 2026-10-29 (`03b23e2`) parses with
   `2026.10.20-docx-6`, so the copy is parsed with this build before the report. The version refusal is
   the guard.
5. **Deviation 1, `DEBATE_STORAGE__DATA_DIR` for the parse step alone: accepted.** Q1 meant the report,
   and the parse has no directory option and writes the copy's own database and parsed store. It is
   set inline on that one command, after refusing any override already in the shell, as v1-e31-t31's
   and the cutover's blocks do. The report, its dry run and its publish set none.
   **Deviations 2 (the smoke check) and 3 (a new runbook): accepted.** The PM's next batch adds
   `tests/smoke` to the packages.
6. **Decisions accepted:**
   * the copy's suppression list alone;
   * the newest parsed directory compared with this build's version;
   * refusals that name no path;
   * `would_ask` null in a run that writes;
   * the copy's fixed path form, and step 5 deleting only that form and counting 0;
   * `--publish --dry-run` as the read before the publish.
7. **Follow-up work:**
   * the data-use policy sentence (a landscape report as a third purpose for a restored copy): in
     policy 1.19's draft, for the coach's approval;
   * docx-7 in the cloud: the PM schedules v1-e31-t31's re-parse and a docx-7 image after the coach's
     trip, which drops step 2's full parse;
   * a dry run that writes the text caches: E32 p3, in the PM's next batch.
8. **The affected set** (206 files) is left to the PR's `ci`. The always-run list, every landscape test
   file, bucket mode and the smoke file pass (880, plus the container factories after `266f9c6`), as do
   ruff, pyright, lint-imports, the thin-handler check, the docs and the specs.
9. **Merge `--partial`.** The hspolicy26 proof is the operator's after the merge, on any day but
   Wednesday, about 35 to 55 minutes. It is v1-e32-t29's republish, with no model spend. It should run
   before Wednesday 2026-11-04, so Friday's LD run follows a path already proven.

## Operator records (recorded by the PM, 2026-10-31)

Added by the PM. Nothing above is changed, and this section is not a review.

| Criterion | Was | Now | Record |
|---|---|---|---|
| ac3, the restore (step 1) | NOT RUN | PASS | 2026-10-30, on the installed `v1.1.0-dev.200`, `CASELIST=hspolicy26`: `exit 0`, 54 manifests restored, `"parsed_version": "2026.10.27-docx-7"`, `"parsed_objects": 0` (as predicted: the cloud image parses with docx-6), 17 manifests naming 4,342 raw sources, all 4,342 fetched (1,226,448,803 bytes), 0 suppressed |
| ac3, the parse (step 2) | NOT RUN | PASS | Dry run: `exit 0`, parser `2026.10.27-docx-7`, 4,342 sources, 0 skipped, 0 suppressed, 4,342 to parse. Parse: `exit 0`, 4,342 attempted, 4,294 parsed, 139,491 cards, failure rate 0.0, threshold not exceeded, 980.9 s |
| ac3, the dry run (step 3) | NOT RUN | PASS | The first attempt stopped with `USAGE_ERROR` (exit 2): an installed build carries no `config/landscape/`, and the block runs from `$HOME`, so nothing named the configuration. Nothing was read or written. Run again with `--config-dir` naming the main checkout's `config/landscape` (on `dev`, unchanged since 2026-10-26): `exit 0`, snapshot `2026-10-27`, docx-7, not stale, 4,294 sources, 139,491 cards, 69,589 counted, 98 positions, `would_ask 0`, `held_back 0`, 0 model calls, 3 scan hits all accepted before (`not_yet_accepted 0`), 7 files planned, all `UPLOAD` |
| ac3, the publish (step 4) | NOT RUN | PASS | `exit 0`, snapshot `2026-10-27`, 0 model calls, 139,491 cards, 7 uploaded, 0 unchanged, nothing refused |
| ac3, the copy deleted (step 5) | NOT RUN | PASS | `removed …/landscape-copy-hspolicy26`, the five `/tmp` files deleted, 0 landscape copies left |

The runbook's missing `--config-dir` is fixed by the PM in the same batch as this record (2026-10-31), with the parse's measured time. Every criterion passes, so the Goal is `Succeeded`. This publish is also `v1-e32-t29`'s republish, which carries `v1-e32-t28`'s.
