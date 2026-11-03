# Session report: v1-e39-t10-pilot-smoke-and-review

| | |
|---|---|
| Task | `v1-e39-t10-pilot-smoke-and-review` — Dev smoke checks, the coach's beta and the student pilot |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t10-pilot-smoke-and-review.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t10-pilot-smoke-and-review.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t10-pilot-smoke-and-review` |
| Session status | COMPLETE for the session's part. **The Goal stays `InProgress`**: ac1's run against dev, the journey's run and ac2, ac3, ac5's numbers, ac6 and ac7 are the operator's and the coach's |

## Summary

validate-dev now checks the pilot in dev with no account: a new `cloud` job runs
`tests/smoke/cloud -m "live and dev"` (`/healthz`; the `302` to managed login for `/`, a search and
`/account`; the content-hashed `app.js` and `app.css` served immutable, and a stale digest `404`; and
CloudFront's CSP on every answer). It holds no secret, token or AWS credential, and `conclude` needs it
green. The checks are proven against the real app, whole and broken in eleven ways, on every pull
request that changes them. The index holder's load line now carries its time, its bytes and the bytes
on `/tmp` (the peak, at a replacement), each search logs its time, and the function's app finally sends
those `INFO` lines to its app log. `scripts/tub_dev_journey.py` is the operator's signed-in journey
(the operator signs in by hand; nothing holds a seed) plus the synthetic `testcl26` seed, and
`docs/runbooks/evidence-search.md` gives the whole dev sequence, the Logs Insights queries and the
coach's beta checklist. **Look first at** the critical path to the pilot below, and at two findings
from the cutover that the PM needs to rule on: the seed's removal on dev, and promotion items 6 and 7.

## The critical path to the pilot

[Promoting the pilot to prod](../runbooks/evidence-search.md#promoting-the-pilot-to-prod) has 12 items,
and **none is done**: every row of the promotion table in
[`docs/data/evidence-search-pilot.md`](../data/evidence-search-pilot.md#the-promotion-to-prod) is
blank, the runbook's *What to record* prod column is empty, and `origin/main` (`5e51217`) does not yet
hold `v1-e39-t08` (`417c096`). In order, with who does each:

| Step | Who | What it needs first, or what this session found |
|---|---|---|
| This task merged into dev | Operator, `scripts/task pr` after PM review | Its app-log change reaches dev's function only with the next `scripts/tub_deploy.sh dev`; the `cloud` job starts with the next dev pre-release |
| Dev deployed with this task, dev's checks by hand, the journey J1 to J10 | Operator | The blocks below and in the runbook. J7 waits on the PM's ruling (question 2) |
| Decide whether `v1-e39-t23` (uvicorn factory, "in the same change as the next pilot image") and `v1-e39-t24` (download header and pocket) land before the promotion | PM | Both `Pending`. `v1-e39-t23` moves the call this task added to `create_app` (Follow-up 1) |
| 1. `dev` promoted to `main` | Operator, [branching and environments](../process/branching-and-environments.md) | validate-dev green on dev's head, the new `cloud` job included |
| 2. Prod's `owner.auto.tfvars` checked | Operator | Before any prod plan |
| 3. Step 11 in full (11a to 11e), nothing destroyed | Operator, plan read by the PM | Prod's function does not exist yet; 11b deploys from a `main` worktree |
| 4. `v1-e29-t08`'s prod plan | Operator | If step 3 did not cover it |
| 5. Prod's suppression list exists | Operator | The check block in *What the function fetches*; create it if absent |
| 6. Prod's parsed store current | Operator | **Question 3**: the item says "from the dev data directory", which since the cutover no longer holds the weeks the cloud ran; the cutover runbook's restored-copy publish is the current way |
| 7. Prod's first index | Operator | **Question 3** again: built from current stores, so from a restored copy |
| 8. `v1-e39-t07`'s prod removal exercise | Operator | Needs a synthetic source in prod; `tub_dev_journey.py seed` writes one, and prod is in local mode until the run's home moves |
| 9. Superseded parsed directories retired in prod | Operator | Counts into `docs/data/parsed-card-store.md` |
| 10. The request to school IT | Operator or coach, email | Prod's asset hosts confirmed first (step 12) |
| 11. The beta's prod accounts | Coach, `tub users add` | The two debaters of 2026-10-22 get new prod accounts |
| 12. The Lambda bandwidth-quota request | Operator | **Time-bound**: the gzip object was 314,054,035 bytes on 2026-10-22, growing about 11.6% a week, and passes 400,000,000 about three weeks after: around mid-November. Send it at the promotion or before |
| The coach's beta | Coach, with the operator for the app log | [The checklist](../runbooks/evidence-search.md#the-coachs-beta-v1-e39-t10); all 12 items ticked first |
| The student pilot, a week or more, and the decision | Coach, PM | The PM's go on the beta |

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `smoke-and-review` (Smoke, beta and pilot) | Session part done; operator and coach parts open | Its node criterion passes. The beta and pilot are after the promotion |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Node: Smoke checks collect | PASS | `uv run pytest tests/smoke --collect-only -q` → `163/175 tests collected (12 deselected) in 1.29s` (the default `not slow and not live` deselects the 3 cloud checks; `-m "live and dev"` over `tests/smoke/cloud` collects exactly those 3) |
| ac1: the dev smoke checks pass against dev (operator-run) and are wired into validate-dev, by the workflow's own test | **NOT RUN** (the wiring half PASS) | Wiring: `tests/scripts/test_validate_dev_workflow.py` (the `cloud` job runs the driver's `cloud` tier from the validated commit; `conclude` needs it and reports it) and `tests/scripts/test_validate_dev.py` (the tier, its refusal of another commit, a skip fails it, `conclude` fails on a red `cloud`) → `526 passed` with the always-run list. The checks themselves against the real app: `packages/debate_api/tests/test_cloud_smoke_checks.py` → `16 passed` (3 pass, the CSP literal equals `distribution.tf`'s, 8 GETs with no cookie or credential, 11 breakages each caught with its own message). The run against dev reaches the network, so it is the operator's (follow-up 1) |
| ac2: the coach's beta checklist complete on prod and recorded | NOT RUN | The coach's, after the promotion. The checklist is written ([runbook](../runbooks/evidence-search.md#the-coachs-beta-v1-e39-t10)) and its tables laid out ([data](../data/evidence-search-pilot.md#the-coachs-beta)) |
| ac3: the student pilot has run a week or more; tallies, themes and go or no-go recorded | NOT RUN | After the beta. Its tables are laid out |
| ac4: validate-dev's pilot checks need no account and no stored secret, by the workflow's own test; the signed-in journey is an operator-run script whose run is recorded in the report | **NOT RUN** (the first half PASS) | `test_the_cloud_job_holds_no_secret_no_token_and_no_aws_credential`, `test_no_job_in_validate_dev_reads_a_secret_or_asks_for_an_oidc_token`, `test_pr_ci_and_every_other_tier_select_none_of_the_cloud_checks_and_the_cloud_tier_all` pass. The script exists and its functions pass and fail in Chromium against the in-process app (`packages/debate_api/tests/browser/test_tub_dev_journey.py` → `4 passed`, run three times); its run against dev is the operator's (follow-up 2) |
| ac5: the index holder's load lines reach the app log with the index's bytes and the `/tmp` total; query time p50/p95, cold-start load and peak `/tmp` recorded | **NOT RUN** (the log half PASS) | `packages/debate_core/tests/application/test_search_index_holder_app_log.py` → `4 passed` (the load line word for word, the peak at a replacement equal to both files, the search time, no query word); `packages/debate_api/tests/test_app_logging.py` → `9 passed` (the function's `create_app` sends the holder's `INFO` and every `WARNING` to the stream, no other `INFO`, once; a search through the app logs both lines and no query). The numbers come from dev's and prod's app logs after a deploy (follow-up 3) |
| ac6: the beta records the Chromebook check, the first sign-in screenshots' answers and the Word paste, as yes or no and counts | NOT RUN | The coach's. Laid out as numbered testers, never names |
| ac7: the dev session of 2026-10-22 and the promotion checklist's completion recorded before the beta | NOT RUN | The 2026-10-22 counts are recorded (the PM's row, unchanged). The promotion's twelve rows are blank: see the critical path |

**Red runs, each restored byte for byte afterwards** (checks earn trust by failing):

* The holder's new tests against the holder as it was (the timer parameter stubbed in): `3 failed, 1 passed`, each on the missing words; the fourth guards against a card lease logging a search time, so it passes either way.
* `test_app_logging.py` with `create_app`'s call removed: `1 failed` (no handler); with the holder's level not opened: `4 failed`, each on the missing `INFO`.
* `test_validate_dev_workflow.py` with `GH_TOKEN` given to the `cloud` job: fails `AssertionError: GH_TOKEN`; with `live` dropped from the cloud checks: fails, the cloud tier selecting none; with an unmarked check added under `tests/smoke/cloud`: fails `AssertionError: not slow and not live`, PR CI's own expression.
* The request-recording self-test found a real fault before it passed: httpx kept the sign-in transaction cookie from the first `302` and sent it on, so the checks no longer asked as someone without a session. `answer` now empties the jar before each request.
* The journey test found the empty search page's caselist list is empty in an environment that has not loaded an index (it never waits for one), so the journey opens the results page by its address; and a race on Copy card's interim "Copying the card…" message.
* `test_search_pages_passage.py::test_a_passage_or_prefix_search_logs_none_of_its_words` caught the first search-time line, `… by passage`: a passage's own words may include "passage". The line now names no mode; that test passes unchanged.

**What was run before this report** (agreement 10):

* `uv run scripts/affected_tests.py --run`, bounded at 115 s: **118 files; stopped at its limit at 77%**, every test before it passing (load average 5 to 10). Over two minutes, so it is left to the pull request's `ci` check, which runs the same set.
* Within the limit, the changed areas and the always-run list:
  * `packages/debate_api/tests` without the browser suite → `1066 passed in 8.52s`;
  * the browser suite's exposure test and the journey tests, `-m slow -k "exposure or journey"` → `5 passed`;
  * the four holder test files → `60 passed`;
  * `tests/scripts/test_validate_dev.py`, `test_validate_dev_workflow.py`, `test_workflow_runners.py`, `test_tub_dev_journey_seed.py`, `tests/architecture`, `tests/specs` and the CLI's three always-run files → `526 passed in 18.24s`;
  * the affected set's 46 `debate_core` and `debate_cli` files → stopped at its limit at 99%, every test before it passing.
* `ruff format --check .` → `1667 files already formatted`; `ruff check .` → `All checks passed!`; `pyright packages/debate_core packages/debate_api` and the changed scripts and tests → `0 errors`; `lint-imports` → `19 kept, 0 broken`; `scripts/check_thin_handlers.py` → `68 … within 25 statements`; `uv run scripts/validate_specs.py` → `OK: 530 files, 41 epics, 467 tasks, 22 releases`; `check_command_blocks.py`, `check_links.py` (`3102 relative links and anchors`) and `docs_index.py --check-descriptions` → OK.
* The seed, measured offline in a scratch local store (no bucket): import 3 members, 3 first seen; parse 3 sources, 3 parsed, 4 cards; `tub index build --caselist testcl26` → 2 documents, 4 occurrences, in 5 s. The runbook's expected counts are these.

## Files changed

* **`packages/debate_core/src/debate_core/application/search_index_holder.py`**: the load line's time,
  bytes, object bytes and directory total; the search-time line; an injectable timer. Its tests:
  `packages/debate_core/tests/application/test_search_index_holder_app_log.py`.
* **`packages/debate_api`**: `app_logging.py` (new), called by `create_app` when it builds the
  function's own services; `search_pages.py`'s docstring. Tests: `test_app_logging.py`,
  `test_cloud_smoke_checks.py`, `browser/test_tub_dev_journey.py`.
* **`tests/smoke/cloud/`** (new): `pilot_checks.py`, `conftest.py`, `test_evidence_search_pilot_dev.py`;
  `tests/smoke/README.md` gains the tier.
* **`scripts/validate_dev.py`**: the `cloud` tier and subcommand; `slow` and `cloud` share
  `tier_from_source`; `run` runs it too; `conclude`'s words. **`.github/workflows/validate-dev.yml`**:
  the `cloud` job, `conclude`'s needs, the summary, the header. Tests: `tests/scripts/test_validate_dev.py`,
  `test_validate_dev_workflow.py`.
* **`scripts/tub_dev_journey.py`** (new): `seed`, `journey`, `removed`. Tests:
  `tests/scripts/test_tub_dev_journey_seed.py` and the browser test above.
* **`docs/runbooks/evidence-search.md`**: dev's smoke checks, the signed-in journey (J1 to J10), the app
  log's measurements, the coach's beta; the order table, the app log table's two rows, the
  "does not do" bullet. **`docs/data/evidence-search-pilot.md`**: the tables for dev's checks, the
  measurements, the beta and the pilot.

## Deviations from the spec

1. **`packages/debate_core` is changed, and is not in `constraints.packages`.** ac5 needs the holder's
   load line to carry the index's bytes and the `/tmp` total, and the PM's ruling on `v1-e39-t14`
   placed "the `/tmp` log line" with this task; the line is the holder's, in `debate_core`. Only
   `search_index_holder.py` and one new test file changed. Question 1 asks for the packages entry.
2. **The query time is a new `INFO` line of the holder's**, `search answered in <n> ms`, one per
   search. The spec says the query time is measured from the app log, and nothing in it timed a
   search; Lambda's `REPORT` lines cannot tell a search from a page or a script. It names no query,
   card, filter, mode or user.
3. **The seed is written by the script and loaded by the ordinary commands**, not "loaded by an
   idempotent script" (the first paragraph, superseded by the amendment that the seed goes in
   through the dev store by the normal path). The archive is the same bytes every run; importing it
   again is an import of the same week.
4. **The seed's index is built from a restored working copy**, not from the Mac's data directory: since
   the cutover the Mac no longer holds the weeks the cloud ran, so an index built there would publish
   stale stores to dev. J5 checks the new manifest against dev's current one (each store's
   `occurrences_sha256`, the suppression list's sha256, the seed's 2 documents) before anything is
   published.
5. **The journey's removal (J7) is gated on its dry run** and may not be possible as the spec imagines
   on dev: question 2.
6. **The dev cloud checks run from the validated commit's source**, in a job of their own, not against
   the installed pre-release as the recorded tier does: they test the deployed function, not the CLI.
   They check whatever commit dev runs, so a pilot down in dev turns validate-dev red, nightly too,
   which opens the validate-dev issue.
7. **The download step checks the file is a `.docx` whose `document.xml` holds the card's tag**, not a
   re-parse (the first paragraph, superseded). The operator confirmed Word with Verbatim and Google
   Docs on 2026-10-31, and the beta checks them again.

## Decisions and assumptions

* **The marker pair `live` and `dev`.** `live` keeps the checks out of the default selection, PR CI's
  `not slow and not live`, the recorded tier and the canary tier, and opens tests/smoke's socket guard
  for them; `dev` names the target. The workflow's test collects `tests/smoke/cloud` with each of those
  expressions, read from ci.yml and the driver, and finds none selected.
* **Assets are found from `/signed-out`**, the one page with the layout that needs no session, and their
  digests checked against the bytes served, so nothing depends on which commit dev runs.
* **Only the holder's `INFO` is opened**, logger by logger, and every `WARNING` keeps reaching the log as
  before (Python's last-resort handler printed them bare; now with level and logger).
* **The status description**: `… the run image built and checked, dev pilot up`, 136 characters with
  a tag as long as `v1.10.0-dev.999`, under the 140 the statuses API takes; a test pins it.
* **The seed's names**: Quillfern Academy, Ostrander Vale and Brindlecote High, at the invented
  Lanternfield Invitational; none of `RM-2026-90`'s synthetic schools, whose `Maple Grove/QX` path dev
  holds. Snapshot 2026-10-27, after dev's newest `testcl26` week. Not screened against the real
  caselists' words; the PM may want that check (`caselist_disclosures` and `caselist_words`, seconds).
* **Unverified, and guarded instead**: whether `caselist restore-run-state` puts the suppression list
  where `tub index build` reads it in the copy. If not, J5's check prints `STOP: the suppression list is
  not the one dev's index read` and nothing is published.
* **A `git fetch` of `origin/main` and `origin/dev`** was run to compare (read-only). Dev is two merges
  ahead (`v1-e41-t01`, `v1-e41-t06`), touching none of this task's files; this branch is not synced.

## PM questions

Paste-ready for the PM:

```text
v1-e39-t10, three questions.

Q1. packages/debate_core/src/debate_core/application/search_index_holder.py changed (the load line's
bytes, /tmp total and time; the search-time line), outside constraints.packages. Your v1-e39-t14 ruling
placed the /tmp log line here.
  (a) Add packages/debate_core to constraints.packages with "# PM ruling: the holder's log lines (ac5)".
  (b) Move the holder change to a small E39 task.
Recommendation: (a). The change is one module and its test; ac5 cannot pass without it.

Q2. The journey's removal on dev (runbook J7). Since the cutover, caselist remove restores the run-state
bundle before it plans, replacing the Mac's manifests and database whole. Only the cloud run saves that
bundle, and it never saw the seed's week (imported into a restored copy), so the removal's plan may
not find the seed's file, which it looks up in the database.
  (a) Keep J7 as written: the dry run decides; go on only if WILL BE REMOVED lists the seed's file with
      its raw/ and parsed/ keys, otherwise tear down (J9, J10) and stop.
  (b) Drop the removal from the dev journey; run "tub_dev_journey.py removed" in prod after promotion
      item 8's removal exercise, which prod (local mode until the run's home moves) supports as designed,
      with the same seed as its synthetic source.
  (c) A follow-up task that lets a hand import enter the run-state bundle.
Recommendation: (a), with (b) if the dry run does not find the file. (c) is real work for one exercise.

Q3. Promotion items 6 and 7 say "from the dev data directory". Since the cutover that directory no
longer holds the weeks the cloud ran (caselist-cutover.md, "Until the promotion"), so a publish-only
or an index built from it would send prod stale stores.
  (a) Amend items 6 and 7 to the cutover runbook's restored-copy publish, and an index built from that
      copy, checked against dev's current manifest as the journey's J5 checks it.
  (b) Leave them, and the operator follows the cutover runbook.
Recommendation: (a). The list is the one place the beta's prerequisites are read from.
```

## Operator follow-ups

Each after this task is merged into dev. The journey and the app-log measurement also need a dev
deploy of a build with it.

1. **Dev's cloud checks by hand** (ac1), the runbook's block:

   **Operator command** (expected runtime ~10 s)
   Where: `$WT`, a checkout with this task
   ```bash
   cd "$WT"
   uv run pytest tests/smoke/cloud -m "live and dev" -n 0 -p no:randomly
   ```
   Success looks like `3 passed`. Paste the summary line back. The first validate-dev run after the
   merge runs the same checks in its `cloud` job; its summary table lists `cloud success`.

2. **The deploy, then the journey** (ac4): `scripts/tub_deploy.sh dev` (runbook step 8), then
   [J1 to J10](../runbooks/evidence-search.md#the-signed-in-journey-on-dev) in order, each block's
   output read as it says before the next. J7 after the PM's answer to question 2. Paste back J5's
   check line, J6's and J8's `PASS` lines and card path, and J9's publish table.

3. **The app log's measurements** (ac5): after the journey on dev, the three Logs Insights queries in
   [Measuring the pilot from the app log](../runbooks/evidence-search.md#measuring-the-pilot-from-the-app-log-v1-e39-t10)
   over the journey's hour, into the *dev* row of the measurements table; prod's rows after the beta's
   and the pilot's weeks. The peak `/tmp` needs an index replacement in the range: J9's publish is one.

4. **The promotion's twelve items**, as the critical path above, ticked in the data document.

## Follow-up work

1. **`v1-e39-t23` moves `create_app`'s no-services branch** into a factory in the composition root.
   That factory must call `configure_app_logging()` before it builds the services, or the holder's lines
   stop reaching the app log again. `test_app_logging.py::test_the_functions_app_configures_it_and_a_tests_own_app_does_not`
   calls `create_app()` with no services and will fail until it is pointed at the new factory: that
   failure is the reminder, not a test to delete.
2. **The removal runbook's P1b after the cutover**: it says to rebuild the aggregates "from this Mac's
   own store", which a bucket-mode removal now restores from the bundle first, and the parse then
   fetches the sources the Mac lacks. Worth a read by whoever next touches `caselist-removal.md`, since
   the journey's J7 and promotion item 8 both lean on it.
3. **The seed's names screened against the real caselists' words**, if the PM wants it before the seed
   reaches dev.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-01

**Notes:**

validate-dev now watches the pilot in dev with no account, and the holder's numbers finally reach the
app log. The critical-path table is the most useful thing in this report; it becomes the promotion
plan.
1. **What passes:**
   * The node criterion passes.
   * The wiring halves of ac1 and ac4 pass. The workflow's own tests show three things:
     * the `cloud` job holds no secret, token or AWS credential, and the file has no `secrets.`;
     * PR CI and every other tier select none of the cloud checks;
     * `conclude` fails on a red or skipped `cloud`.
   * The log half of ac5 passes. `configure_app_logging` opens `INFO` one logger at a time, which is
     the right default for a log a student's search passes through.
   * The red runs are real. Two of them found real faults before passing:
     * the cookie jar carrying the sign-in transaction cookie;
     * the search-time line's mode word.
2. **Deviations accepted:** all seven.
   * 1: see Q1.
   * 2: the search-time line names no query, card, filter, mode or user, and a test pins that.
   * 3 and 4: the seed goes in through the normal path, and its index comes from a restored copy,
     checked against dev's manifest before any publish.
   * 5: J7 gated on its dry run.
   * 6: the cloud checks run from the validated commit's source.
   * 7: the download checked for its tag, not re-parsed.

   One consequence of 6: validate-dev's green now also means the dev pilot is up. If a release is red
   only on `cloud`, the PM rules on whether it can still be deployed as an image. It is not deployed
   by default.
3. **Q1: (a).** The spec's `constraints.packages` gains `debate_core.application` and
   `packages/debate_core/tests`, with `# PM ruling 2026-11-01: the holder's log lines (ac5)`. The
   change goes in the next PM batch, since no report or spec is edited here after review.
4. **Q2: (a), then (b) if the dry run does not list the seed's file.**
   * J7 runs only if the dry run's WILL BE REMOVED lists the seed's file with its raw/ and parsed/
     keys.
   * Otherwise tear down with J9 and J10, record "J7 not possible on dev after the cutover", and run
     `tub_dev_journey.py removed` in prod with promotion item 8.
   * (c) is not filed.
5. **Q3: (a).** The next PM batch amends promotion items 6 and 7:
   * prod's stores are published from a restored copy, as in the cutover runbook;
   * prod's first index is built from that copy and checked against dev's current manifest, as J5
     checks it.
6. **Promotion order.** Both v1-e39-t24 (download header and pocket) and v1-e39-t23 (uvicorn
   factory) land before step 1.
   * v1-e39-t24 starts now.
   * v1-e39-t23 starts after this task merges. It must call `configure_app_logging()` in the new
     factory, and the failing `test_app_logging` test is its reminder, as Follow-up 1 says.
7. **Item 12 does not wait for the promotion.** The gzip object passes 400,000,000 bytes around
   mid-November, and dev's function loads the same object. The operator sends the bandwidth-quota
   request this week, for dev's account and then prod's.
8. **Follow-ups:**
   * 1: carried into v1-e39-t23's context.
   * 2: a docs line in the next PM batch, after J7's outcome is known.
   * 3: yes. The seed's three school names and tournament are screened against the real caselists'
     words before J1, and the next PM batch adds that check to the runbook.
9. **Closing checks:** the affected set stopped at 77% at its limit, with nothing failing, and is
   left to the PR's `ci`. The changed areas and the always-run list pass. The whole-repo checks are
   clean.
10. **Merge:** `--partial` once `ci` is green. The Goal stays InProgress for the operator's and the
    coach's criteria:
    * ac1's run against dev;
    * the journey;
    * ac2, ac3, ac5's numbers, ac6 and ac7.

## Operator records (recorded by the PM, 2026-10-31)

Added by the PM. Nothing above is changed, and this section is not a review.

| Criterion | Was | Now | Record |
|---|---|---|---|
| ac1: the dev smoke checks pass against dev (operator-run) | NOT RUN | PASS, with a fault found | 2026-10-31, after the dev deploy of `66182c0`: run as the runbook gives it, `uv run pytest tests/smoke/cloud -m "live and dev"` gave `3 failed`, each `SocketBlockedError: A test tried to use socket.getaddrinfo`: the repository's `--disable-socket` blocks the checks' in-process HTTPS, and tests/smoke's conftest lets a `live` check skip only its own extra block. With `--force-enable-socket`: `3 passed in 3.84s`. validate-dev's `cloud` job runs the same command, and validate-dev has failed on every pre-release since; the fix is v1-e39-t26 (p1). Step 8's checks: `302 private, no-store` to managed login, the six headers, the function URL `{"Message":"Forbidden"} 403` |

ac1's run against dev is recorded. The Goal stays `InProgress` for the journey, ac2, ac3, ac5's numbers, ac6 and ac7.

## PM record, 2026-10-31: promotion item 12 requested

Added by the PM. Nothing above is changed, and this section is not a review.

The Lambda bandwidth quota (`L-14320ECE`, "Network bandwidth per execution environment", 625 Mbps,
adjustable) was requested at 1,250 Mbps on 2026-10-31, before the promotion as the PM ruled: request
`57c67e70…`, `PENDING`, then `CASE_OPENED`. One request covers dev and prod, which share one account.
The gzip object was 318,115,067 bytes that day, 1.3% above 2026-10-22's, so the growth the item feared
has not come.
