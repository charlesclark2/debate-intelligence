# Session report: v1-e40-t11-run-home-moved-holder

| | |
|---|---|
| Task | `v1-e40-t11-run-home-moved-holder` — The dev lock held for good when the weekly run's home moves to prod |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t11-run-home-moved-holder.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t11-run-home-moved-holder.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t11-run-home-moved-holder` |
| Session status | COMPLETE |

## Summary

The proposed command is **`debate-research caselist move-run-home`**. It is a dry run by default. With
`--execute` it takes dev's run lock like every other command, so a run holding the lock refuses it with
`RUN_LOCK_HELD` and names the holder. It then rewrites the lock with `If-Match` on its own lease as held
for good by a `moved` holder naming `home_environment: prod`, when it was written, and who wrote it (the
kind of runner and the build tag, never a person). The holder has no lease and never expires. The new
refusal, `RunHomeMoved` (`RUN_HOME_MOVED`), lives in `BucketRunLock.take`, so every lock-taking command
says "the weekly run now runs from prod" and names the holder. Local mode, the seed's plan and the
backfile import's plan read the lock without taking it, and they now say the same. `--release`, then
`--release --execute`, undoes the move, only for a lock a move holds, again with `If-Match`. In prod the
command refuses before it reads anything, so it never needs `--confirm-prod`. **The PM should look first
at what older builds do.** dev.200 and dev.251 refuse the moved lock as a dev build and write nothing.
But either build, run as *prod* against dev's bucket, would take the lock over, because it reads a lock
with no lease as expired. The runbook now records this as a constraint (Decisions, item 4). Tests against
moto were shown red against a skeleton that refuses nothing, and the PM's five mutants (nine variants)
are each caught.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `moved-holder` (Moved holder) | Done | The command, the holder, the refusal on every lock-taking path, the release, the runbooks; tests red first, then green; nine mutants caught. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: against moto, the command writes the held-for-good holder under the lock, refuses while a run holds it, every lock-taking command's refusal names it, and the release undoes it; tests shown failing first | PASS | **Red** against the skeleton (commit `8ca25aa`, whose lock methods refuse nothing and write nothing): `pytest packages/debate_core/tests/application/test_run_state_home_moved.py -n 0` → `21 failed, 3 passed`. The reasons were `DID NOT RAISE RunHomeMoved` ×8, `RunLockWrongHome` raised where `RunHomeMoved` was expected ×3, `DID NOT RAISE RunHomeNotMoved` ×2, `DID NOT RAISE RunLockLost`/`RunLockHeld`/`LockObjectChanged` ×1 each, `BucketKeepsRunState` ×1, and body or count assertions ×4. The three that passed were the dry run's body, the prod refusal and "an ordinary lock has no moved refusal". The CLI tests (`-k "home_moved or move_run_home or release_is_refused or classified"`) → `18 failed, 5 passed, 1 error`. Every new test failed. The five passes were the classification test and four existing landscape tests the `-k` also matched. The error was a fixture clash from mixing directories, and that backfile test run alone → `1 failed`. **Green** (`863bac7` on): the core file → `24 passed`; the core file with `test_caselist_sync_run_lock.py` → `43 passed`; the CLI moved-holder tests → `17 passed`; backfile → `1 passed`; prune and landscape → `2 passed`. Full runs are below under "Commands run". |
| Node `moved-holder`, "Caselist tests pass": `uv run pytest packages/debate_core/tests/application -k run_state` | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/application -k run_state -n 8 -m "not slow and not live" -q` → `70 passed in 11.08s`, exit 0. The new file is named `test_run_state_home_moved.py` so this command selects it. |

### Every lock-taking path, and what now refuses it

Found from `bucket_lock.py`'s list, the command classification in `test_bucket_mode_lock.py`, and a grep of
`.take(`, `.held(`, `.create(`, `bucket_is_seeded` and `refuse_a_seeded_bucket` under `packages/*/src`.

| Path | How it meets the lock | Tested after the move |
|---|---|---|
| `caselist pull` (bucket mode) | `BucketRun.start` → `BucketRunLock.take` | `RUN_HOME_MOVED`, nothing listed or fetched, record kept local with `error_class` `RunHomeMoved` |
| `caselist publish` | `holding_the_bucket_lock` → `BucketWriteGuard.held` → `take` | yes (parametrized) |
| `caselist parse --publish`, `--publish-only` | same | yes, both |
| `caselist remove --execute`, `caselist unsuppress --execute` | same | yes, both |
| `caselist retire --bucket --execute` (and `--restore`) | same | `--execute` (`--restore` goes through the same call) |
| `caselist restore-run-state` | same | yes |
| `tub index publish` (v1-e39-t25's `--newest` included) | same | yes |
| `tub index prune --execute` | same | yes, with a moved lock written out by hand |
| `store sync --push --apply` | same | yes |
| `files publish` | same | yes |
| `landscape report --publish` | same | yes, with a moved lock written out by hand |
| `caselist backfile-import --execute` | `BucketWriteGuard.held` per step; its plan reads `home_moved()` first | plan and `--execute` both refused `RUN_HOME_MOVED` before any lock or download |
| `caselist seed-run-state` | its plan reads the lock (`bucket_is_seeded`, now also `home_moved()`); `--execute` uses `create` | `SEED_REFUSED` whose message is the moved refusal |
| Any of the above in local mode | `BucketWriteGuard.refuse_a_seeded_bucket` | `caselist publish` → `RUN_HOME_MOVED`, not `BUCKET_KEEPS_RUN_STATE` |
| `caselist move-run-home` itself | `check()`, then `take` | a second move → `RUN_HOME_MOVED`; while a run holds the lock → `RUN_LOCK_HELD` |
| A prod-environment runner pointed at dev's bucket | `take`: home matches, the lease never expires | `RunHomeMoved` at once, after a lease and its margin, and a year later |

### Mutants (agreement 8)

Each was run from a clean tree against the core file, the CLI moved-holder tests and the backfile test,
with a fresh `HYPOTHESIS_STORAGE_DIRECTORY` each time (these tests use no Hypothesis). Each was then
restored with `git checkout HEAD -- packages/`. Every catch failed at an assertion on the behaviour the
mutant breaks, never at collection.

| Mutant | Caught by | Reason |
|---|---|---|
| 1a. The move's write unconditional in effect: read the lock again and `If-Match` that fresh version (a blind overwrite) | `test_the_move_does_not_write_over_a_lock_that_changed_after_it_took_it` | `DID NOT RAISE RunLockLost`. **First run: survived.** That test's racing writer landed inside the write call, after the mutant's re-read. I moved it to land just after the take's write (and, for the release, just after its read), committed that alone (`3496fd6`), and re-ran: caught. |
| 1b. The write literally unconditional: `S3LockObject.replace` sends no `If-Match` | the bucket-deny fixture: 22 of 24 core tests | the hook that mirrors `v1-e40-t07`'s statement answers `AccessDenied` |
| 2. The command writes while a run holds the lock (no check, no take, `If-Match` on whatever it read) | `test_the_move_is_refused_while_a_run_holds_the_lock…` (core) and `test_move_run_home_is_refused_while_a_run_holds_the_lock_naming_it` (CLI), plus 4 more | `DID NOT RAISE RunLockHeld`; the CLI exits 0 |
| 3a. One command's refusal not naming the holder: the pull turns `RunHomeMoved` into the generic `RunLockWrongHome` | `test_a_pull_after_the_run_home_moved_is_refused_naming_the_move…` | `'RUN_LOCK_WRONG_HOME' == 'RUN_HOME_MOVED'` |
| 3b. Local mode's refusal not naming it (`BUCKET_KEEPS_RUN_STATE` again) | the core and CLI local-mode tests | `BucketKeepsRunState` raised; wrong code |
| 4a. The release unconditional in effect (re-read, `If-Match` the fresh version) | `test_the_release_does_not_write_over_a_lock_that_changed_after_it_read_it` | `DID NOT RAISE LockObjectChanged` |
| 4b. The release of any lock, moved or not | `test_the_release_is_refused_unless_a_move_holds_the_lock[free, held by a run]` and the CLI's `test_the_release_is_refused_when_no_move_holds_the_lock` | `DID NOT RAISE RunHomeNotMoved`; exit 0 |
| 5a. The holder expiring: `_expired` loses its "a moved holder never expires" rule | the three "prod pointed at dev's bucket" cases | `DID NOT RAISE RunHomeMoved`: prod took the lock over |
| 5b. The holder written with a lease (`lease_expires_at` = now + 30 min) and that rule gone | 11 core tests and the CLI body test | the hand-written body differs, and prod takes the lock over |

A dev runner's refusal does not depend on the expiry, because the home check comes first. Mutant 5
matters only to a runner whose environment is the new home. That is the case older builds get wrong
(below).

### What dev.200 and dev.251 do with the new holder

Both tags carry the same `run_lock.py`, `bucket_run.py` and `run_state_seed.py` as this branch's start
(`git diff --stat v1.1.0-dev.251 db94a47 -- …` is empty, and so is the diff between the two tags' `run_lock.py`). A scratch script
loaded each tag's `run_lock.py` (from `git show <tag>:…`). Under moto, it seeded a bucket, let this
branch's `RunHomeMove` write the moved holder, then drove the old lock against it. The output was the
same for both tags:

```text
reads the body: LockBody(home_environment='prod', state=HELD, holder=LockHolder(kind='moved', run_id='20261204T150000Z', command='caselist move-run-home', task=None), acquired_at=2026-12-04 15:00:00+00:00, renewed_at=None, lease_expires_at=None, took_over_from=None)
dev mac take, +0d: RunLockWrongHome: the bucket's run lock names prod as the run's home environment, and this is dev: nothing was done; versions 4 -> 4
dev cloud take, +400d: RunLockWrongHome: the bucket's run lock names prod as the run's home environment, and this is dev: nothing was done; versions 4 -> 4
prod mac take, +0d: TOOK THE LOCK; versions 4 -> 5: {'kind': 'mac', 'run_id': '20261204T150000Z', 'task': None, 'command': 'caselist pull'}
local mode: BucketKeepsRunState: this bucket keeps its run state (it holds reports/sync/run-lock.json); set caselist.run_state = bucket; versions 7 -> 7
bucket_is_seeded (the seed's plan): True
```

So an older build reads the new holder without crashing. It ignores the holder's `by` and `build` keys.
As a dev build, scheduled or by hand, cloud or Mac, it refuses and writes nothing, though its words are
the generic `RUN_LOCK_WRONG_HOME` rather than the move's. **An older build run as prod against dev's
bucket would take the lock over.** That needs `DEBATE_ENV=prod` with an override naming dev's bucket.
The pull it ran would then work in dev's bucket while calling itself prod. This is the
promotion-order constraint, now in the runbook: no such override, which every block checks for, and the
move run from a build that has the command, which the first block checks. The prod profile's role also
cannot write dev's bucket (ADR-0010 rule 4), so it would take a hand-made profile as well.

## Commands run

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` | 289 test files: `run_lock.py` and `container.py` are hubs. The `bucket_mode` directory alone takes 95 s, at a load average of 10 to 14, so the set is well past two minutes. Under agreement 10 it is left to the pull request's `ci` check; nothing was handed to the operator. |
| `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/application -k run_state -n 8 -m "not slow and not live" -q` | `70 passed in 11.08s` |
| `… pytest packages/debate_cli/tests/bucket_mode -n 8 -m "not slow and not live" -q` | `186 passed in 95.34s` |
| `… pytest tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py packages/debate_cli/tests/test_installation.py packages/debate_cli/tests/commands/test_doctor.py packages/debate_core/tests/application/test_caselist_sync_run_lock.py packages/debate_core/tests/application/test_caselist_backfile_rules.py tests/smoke/test_caselist_move_run_home.py tests/smoke/test_caselist_restore_run_state.py tests/docs/test_cutover_plan_checks.py -n 8 -m "not slow and not live" -q` (the always-run list, and the changed areas; every path checked with `ls -d` first) | `524 passed in 25.79s` |
| `… pytest packages/debate_cli/tests/test_tub_index_prune.py packages/debate_cli/tests/test_landscape_command.py -n 8 -m "not slow and not live" -q` | `101 passed in 10.58s` |
| `… pytest tests/smoke/test_caselist_move_run_home.py`, and the same with the prod refusal removed | `5 passed`; then `4 failed, 1 passed`: the build went on to `STORE_PROFILE_NOT_CONFIGURED`, reaching for prod's profile. The check fails for its reason. |
| `uv run --frozen ruff format --check .` | `1708 files already formatted` |
| `uv run --frozen ruff check .` | `All checks passed!` |
| `uv run --frozen pyright` (whole configuration, as CI runs it) | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `uv run --frozen python scripts/check_thin_handlers.py` | `OK: 69 CLI command and API route handlers within 25 statements` |
| `uv run --frozen python scripts/check_command_blocks.py` | `OK: no # comments in 630 shell code blocks in 203 Markdown files` |
| `uv run --frozen python scripts/check_links.py` | `OK: 3188 relative links and anchors in 499 Markdown files` |
| `uv run --frozen python scripts/docs_index.py --check-descriptions` | `All 61 indexed documents under docs/ have a description` |
| `uv run scripts/validate_specs.py` | `OK: 543 files, 41 epics, 480 tasks, 22 releases` |

Dev had moved two commits by the end, `v1-e41-t09` and a refresh. Neither touches a file changed here,
and this task's spec is unchanged on dev apart from its phase.

## Files changed

* `packages/debate_core/src/debate_core/application/caselist/run_lock.py`: the moved holder.
  * `LockHolder` gains `by` and `build`, written only for a moved holder, so every other body is
    byte-for-byte as before. `LockBody.moved` is new.
  * Two refusals are new: `RunHomeMoved` and `RunHomeNotMoved`.
  * Take's rules move into `_refuse_unless_takeable`, which raises `RunHomeMoved` from both the home
    check and the lease check. A moved holder never expires.
  * New methods: `check()` (a take's dry run), `home_moved()`, `moved_body()`, `hold_for_good()` (the
    conditional write under the held lease), and `check_home_move()`/`release_home_move()`.
  * Local mode's refusal names the move.
  * Rule 7 is added to the module docstring.
* `…/caselist/run_home_move.py` (new): `RunHomeMove`, with `plan`, `move`, `plan_release` and `release`,
  `RunHomeMoveRefused` for prod, and `MOVE_COMMAND`/`NEW_HOME`.
* `…/caselist/run_state_seed.py`: the plan's refusal names the move.
* `…/caselist/backfile_import.py`: the plan refuses `RUN_HOME_MOVED`. This comes through a new
  keyword-only `home_moved` argument whose default is `None`.
* `packages/debate_cli/src/debate_cli/commands/caselist_move_run_home.py` (new), `command_registry.py`
  and `container.py`: the command, `run_home_move()`, the backfile import's `home_moved`, and
  `_build_named()`. That last one gives the build's tag, or `source checkout <commit>`.
* Tests:
  * `packages/debate_core/tests/application/test_run_state_home_moved.py` (new, 24 tests against moto,
    with a hook that denies an unconditional lock write as the bucket does).
  * `packages/debate_cli/tests/bucket_mode/test_bucket_mode_lock.py`: the command is classified as
    bucket-writing. Added: the command end to end, the refusal for each of the 10 commands, the pull,
    the seed and local mode.
  * `test_backfile_import.py`, `test_tub_index_prune.py`, `test_landscape_command.py`: one test each.
  * `tests/smoke/test_caselist_move_run_home.py` (new).
* `docs/runbooks/caselist-cutover.md`: the promotion's step 3 runs the command. A new subsection, "The
  dev lock held for good", has the checks, the dry run, the move, a refused dev command, and the
  older-build constraint. Another, "Undoing the move", has the release's dry run and the release, after
  the coach confirms and with prod's schedule off. `docs/runbooks/evidence-search.md`: the promotion
  checklist's new item 13 names the command, its dry run, its success line and the release.

## Deviations from the spec

* **A smoke check outside `constraints.packages`.** I added `tests/smoke/test_caselist_move_run_home.py`.
  Agreement 5 asks every task that adds a user-facing surface to add its smoke checks, and the spec has
  no smoke node. The check runs offline: the installed build refuses prod before building a client, and
  `--help` names `--execute` and `--release`. If the PM rules smoke checks out of this task's scope, the
  file can be dropped without touching anything else.

## Decisions and assumptions

1. **The name and flags.** The command is `caselist move-run-home`, beside `seed-run-state` and
   `restore-run-state`. Without flags it is a dry run. `--execute` writes, `--release` gives the dry run
   of the undo, and `--release --execute` undoes.
2. **Prod: it never applies there, so there is no `--confirm-prod`.** The spec moves dev's lock. Prod's
   lock names prod from its seed, and ADR-0020 (7) moves the home one way only. So in prod both the move
   and the release raise `RUN_HOME_MOVE_REFUSED` before the lock is even built. The CLI's own guard
   requires dev or prod with a bucket, and bucket mode, as the seed's does.
3. **The holder.** It is written as follows:
   * `kind: moved`.
   * `run_id`: the UTC second it was written.
   * `command: caselist move-run-home`.
   * `task`: the ECS task, if any.
   * `by`: the runner's kind, `mac` or `cloud`.
   * `build`: the tag, or `source checkout <12-char commit>`. No person is named.
   * `acquired_at`: when it was written.
   * `renewed_at`, `lease_expires_at` and `took_over_from`: `null`.

   The move writes it with `If-Match` on its own lease, the version before it, so it is written under
   the lock (the forbidden item "a holder written without the lock").
4. **No lease, rather than a far-future one.** A `lease_expires_at` far in the future would make older
   builds refuse the "prod against dev's bucket" case with `RUN_LOCK_HELD` instead of taking the lock
   over. I did not do it, for three reasons. The brief says the holder "never expires on its own". The
   ADR body has no such field. And `9999-12-31` would crash older builds: their `lease_expires_at +
   5 minutes` overflows. If the PM wants that defence, a date such as `3000-01-01T00:00:00Z` works with
   both readers, and the moved-holder rule stays. It is one line in `moved_body`.
5. **`RunHomeMoved` is its own class (`RUN_HOME_MOVED`), not a subclass of `RunLockWrongHome`.** Nothing
   catches `RunLockWrongHome` by class, and a code of its own lets a script tell "moved" from a
   misconfigured environment. Its record stays local, as every lock refusal's does. A pull so refused is
   recorded `failed` with `error_class` `RunHomeMoved`, and gets the generic failure notification. After
   the move the dev schedule is deleted, so only a hand run on the Mac meets it.
6. **The release's coach confirmation is a runbook rule, not a code gate.** The runbook also says
   prod's schedule must be off first, since a release makes dev a home again. A mistaken move is undone
   only by the release: an older version of the lock cannot be copied back, because the bucket denies
   an unconditional write of the lock (`v1-e40-t07`). If the PM wants a code gate, `caselist retire`'s
   confirmation code is the pattern.
7. **v1-e39-t25's API is untouched.** `take`, `release`, `start_renewing`, `before_write`,
   `BucketWriteGuard.held`, `refuse_a_seeded_bucket` and `bucket_is_seeded` keep their signatures.
   `take` raises one more refusal. Everything else is new methods, plus one optional keyword argument on
   `BackfileImportService`.
8. **No new Terraform, and the deny statement stays.** No test reaches the network or AWS: everything
   runs in moto in-process, plus one read-only `git fetch origin dev` to compare the spec.

## Operator follow-ups

None for this task. The new blocks are used at the pilot's promotion, from the cutover runbook's "The
dev lock held for good" section, by a build that contains this merge.

## Follow-up work

* **A banner for a pull refused by the move.** Today such a pull gets the generic failed-run
  notification. A notification that says "the weekly run now runs from prod" and records `skipped`
  rather than `failed` would read better on the Mac. It is small, and belongs to E41 upkeep or a later
  E40 task. It matters only for a Mac hand run after the move.
* **The PM's choice on decision 4**: a far-future lease, as defence in depth for older builds.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-31

**Notes:**

The promotion's step 3 now has its command. The older-build finding is exactly the kind of thing the
runbook needed to know before the day.
1. **ac1 passes.**
   * Red against a skeleton that refuses nothing: 21 failed, every new test failing for its own reason.
   * Green: the core file (24), with the run-lock suite (43), and the CLI moved-holder tests (17).
   * The node criterion passes (70).
   * The lock-taking table lists 16 paths with how each meets the lock, and every one is tested after
     the move, local mode and a prod runner pointed at dev's bucket included.
2. **Mutants.** Nine variants of the five, all caught at assertions. 1a first survived because its
   racing writer landed after the mutant's re-read. Moving the race, committing that alone and
   re-running is the right fix, and it shows the conditional write is really what the test sees. 1b
   is caught by a hook that mirrors v1-e40-t07's bucket deny, which is the right stand-in.
3. **Older builds.** dev.200 and dev.251 run against the new holder by their own `run_lock.py`:
   * as dev, they refuse and write nothing (`RUN_LOCK_WRONG_HOME`);
   * as prod pointed at dev's bucket, they take the lock over.

   That needs `DEBATE_ENV=prod`, an override naming dev's bucket and a profile that can write it, which
   prod's role cannot (ADR-0010 rule 4). The runbook now names the constraint, and every block checks
   for the override.
4. **Decisions accepted:**
   * `caselist move-run-home`, a dry run by default, with `--execute`, `--release` and
     `--release --execute`;
   * refused in prod before anything is read, so no `--confirm-prod`;
   * the holder naming the runner kind and build, never a person, with no lease;
   * `RUN_HOME_MOVED` as its own code;
   * the coach's confirmation as a runbook rule;
   * e39-t25's API untouched.

   **Decision 4: no far-future lease.** The spec says the holder never expires, the case it would guard
   is already blocked by prod's role, and a year-3000 date would be a surprise for the next reader of
   the lock body. Leave it as built.
5. **Deviation accepted:** the smoke check, which agreement 5 asks for. The PM's next batch adds
   `tests/smoke` to the spec's packages, with the ruling.
6. **Follow-up:** the pull refused by the move getting its own banner and `skipped` rather than
   `failed`. One p3 E40 task in the PM's next batch. It matters only for a Mac hand run after the
   promotion.
7. **Closing checks:** the affected set (289 files, `run_lock.py` and `container.py` are hubs) is left
   to the PR's `ci` under agreement 10. The run-state selection (70), bucket_mode (186), the always-run
   list and changed areas (524), prune and landscape (101), the new smoke check, ruff, CI's pyright,
   lint-imports, thin handlers, the doc checks and the specs are clean.
8. **Merge:** a plain `scripts/task pr` once `ci` is green. Nothing here is used until the promotion.
