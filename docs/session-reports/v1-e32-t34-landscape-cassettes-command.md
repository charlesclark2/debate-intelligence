# Session report: v1-e32-t34-landscape-cassettes-command

| | |
|---|---|
| Task | `v1-e32-t34-landscape-cassettes-command` — A command lists and deletes one caselist's model cassettes, and the annual purge calls it |
| Spec | [`plan_specs/v1/e32-argument-landscape/t34-landscape-cassettes-command.yaml`](../../plan_specs/v1/e32-argument-landscape/t34-landscape-cassettes-command.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t34-landscape-cassettes-command` |
| Session status | COMPLETE |

## Summary

`debate-research landscape cassettes --caselist <slug>` counts a caselist's model cassettes on this
machine as sole (this caselist alone), shared (this and others) and unattributed (no caselist, from
before `v1-e32-t31`), plus those of other caselists only. It reads `<data dir>/landscape/model-cassettes/`
through one container helper that the model stage and `landscape evaluate` now use too. It is a dry
run by default and prints a confirmation code. `--delete --confirm <code>` runs t31's
`delete_caselist_cassettes`, which now requires that code and refuses any other before changing
anything. In prod, `--confirm-prod` is required too: `caselist retire`'s pattern. The output is counts,
the slug, the environment and the code only. It never shows a cassette's content or name, a path, a
school or a team code. Annual-purge step 4 calls the command, and the heredoc script and its
byte-for-byte twin test are gone. **Look first at** Deviation 1: the PM context asks for "the directory
read" in the output, but the spec's forbidden list bans any path in it. The command names the
directory as the `<data dir>/landscape/model-cassettes/` template.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `landscape-cassettes-command` (Cassettes command) | Done | Red run on a refuse-nothing skeleton (commit `7f806c7`), then the command (`037bbce`), then one mutation finding acted on (`00e9b73`) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the command counts and, behind a confirmation, deletes only a caselist's sole-owned cassettes, keeping shared and unattributed ones; annual-purge step 4 calls it and the heredoc copy is gone; by tests shown failing first | PASS | Red, then green, below. `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_cli/tests/test_landscape_cassettes.py packages/debate_core/tests/application/test_cassette_filing.py tests/docs/test_annual_purge_runbook.py -q -n 0` → `66 passed in 2.07s` |
| Node: Cassettes command tests pass (`uv run pytest packages/debate_cli/tests -k cassette`) | PASS | Run as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_cli/tests -k cassette -q` (the same selection, without uv's sync) → `23 passed in 5.70s` |

**Red run, on a refuse-nothing skeleton** (commit `7f806c7`): the command was registered and printed
`{}`. `confirmation` was `""`, and the delete took a `confirmation` and ignored it. Run:
`pytest packages/debate_cli/tests/test_landscape_cassettes.py packages/debate_core/tests/application/test_cassette_filing.py -n 0 -p no:randomly`
→ `24 failed, 19 passed`, every failure an assertion. Of the first draft's failures, 11 were KeyErrors
from reading `{}`; those reads now use `.get` and fail at the assertion. The 19 passes are:

* t31's 17 application tests, which the skeleton keeps (it still deletes as t31 did);
* `test_the_command_reads_the_directory_the_model_stage_records_to`, since the container helper was
  written before the skeleton;
* `test_the_code_covers_what_the_delete_changes_and_not_what_it_keeps_whole`, an invariant a constant
  code keeps.

The three new runbook tests were run against HEAD's step 4: the new runbook was saved aside, HEAD's
put back, and the copy restored and checked with `cmp`. Result: `3 failed`, all assertions ("one block
lists the cassettes", "one block deletes the cassettes", and the heredoc still present). On the new
step 4: `23 passed`.

**Mutants** (agreement 8; no Hypothesis in these tests, but each run had a fresh
`HYPOTHESIS_STORAGE_DIRECTORY`). Each was applied to the committed tree and run against the two
cassette test files, then the file was restored with `git checkout HEAD --`; the tree was checked
clean afterwards. The first five are the PM's.

| Mutant | Result |
|---|---|
| 1. A shared cassette deleted (`withdraw` → `delete`) | Caught: 4 failed |
| 2. An unattributed cassette deleted | Caught: 3 failed |
| 3a. `--delete` without the code deleting (application check removed) | Caught: 12 failed |
| 3b. The same, the CLI passing the listing's own code | Caught: 7 failed |
| 4a. A cassette's content printed (in the human display) | Caught: 1 failed, the human-output case (the display is not shown under `--json`) |
| 4b. A cassette's content logged | Caught: 2 failed |
| 5. Counts swapped: sole and shared (JSON and display) | Caught: 6 failed |
| 5b. Counts swapped: shared shown as the unattributed count (display) | Caught: 1 failed |
| A shared cassette classified as sole (`== 1` → `>= 1`) | Caught: 12 failed |
| The code omits the shared cassettes | Caught: 1 failed |
| The code omits the sole cassettes | Caught: 2 failed |
| The code omits the caselist | **Survived**: acted on, see Decisions |
| The `--confirm-prod` guard removed | Caught: 1 failed |
| The CLI's slug check removed | Caught: 3 failed (assertions: the run ends `INTERNAL_ERROR`, not `NOT_A_CASELIST_SLUG`) |
| The unreadable-cassette catch removed | Caught: 1 failed, on `'Maple-Grove-MG' not in …`: the generic handler prints the misfiled file's path |
| `directory_found` always true | Caught: 1 failed |
| A spent code still printed after a delete | Survived the first run; a test now pins `confirmation` null after a delete, and the rerun caught it (1 failed) |

**Closing checks.** The affected set is 250 of 621 test files (`uv run scripts/affected_tests.py`, 14.5
s). It is reached through the root conftest: `fake_router` → `models` → `record_replay` →
`application.cassette_filing`. t31's set was the same, 246 files, about 2.6 minutes, so under agreement
10 it is left to the pull request's `ci`. A first bounded run of all of `packages/debate_cli/tests`
reached the 115-second limit and was stopped by `hard_stop.py`. Run within the limit instead:

* the CLI tests the change reaches by name: `test_landscape_cassettes.py`, `test_landscape_command.py`,
  `test_container_factories.py`, `test_installation.py`, `commands/test_doctor.py`,
  `bucket_mode/test_bucket_mode_lock.py`, `test_app.py` and `test_help_rendering.py` → `258 passed in 33.03s`;
* `packages/debate_core/tests/application/test_cassette_filing.py`, `packages/debate_core/tests/integrations/models`
  and `tests/docs` → `754 passed in 6.67s`;
* the always-run `tests/architecture` and `tests/specs` → `334 passed in 9.13s`;
* a first try that also included all of `packages/debate_core/tests/application` reached 99% and was
  stopped at the limit, so that directory was narrowed to the cassette file.

The whole-repo checks:

* `ruff format --check` and `ruff check` on the changed files: clean;
* `pyright packages/debate_cli` plus the changed core and docs files: `0 errors`;
* `lint-imports`: `20 kept, 0 broken`;
* `scripts/check_thin_handlers.py`: `70 … within 25 statements`;
* `scripts/check_command_blocks.py`: OK;
* `uv run scripts/validate_specs.py`: `OK: 545 files, 41 epics, 482 tasks, 22 releases`.

## Files changed

* `packages/debate_core/src/debate_core/application/cassette_filing.py`: `CaselistCassettes.confirmation`,
  a 12-hex-digit digest (the `CONFIRMATION_LENGTH` of `caselist retire` and `tub index prune`) of the
  sole and shared cassette names. Also `CassetteDeleteRefused`, and `delete_caselist_cassettes` takes
  a required keyword `confirmation` and refuses a mismatch after listing, before any change.
* `packages/debate_core/tests/application/test_cassette_filing.py`: t31's delete tests go through the
  listing's code. New tests cover the refusal, the code's stability, a stale code, and what the code
  ignores.
* `packages/debate_cli/src/debate_cli/commands/landscape_cassettes.py` (new) and `command_registry.py`:
  the command.
* `packages/debate_cli/src/debate_cli/container.py`: `landscape_cassettes()` and
  `_landscape_cassette_dir()`, which the model stage's default and the evaluation now use too.
* `packages/debate_cli/tests/test_landscape_cassettes.py` (new): the command over a synthetic cassette
  directory written by `CassetteDirectory` itself, with no router and no model.
* `packages/debate_cli/tests/bucket_mode/test_bucket_mode_lock.py`: `landscape cassettes` classified as
  never writing a bucket.
* `packages/debate_cli/tests/test_installation.py` and `commands/test_doctor.py`: the container now wires
  `models.record_replay`, so the pinned list gains it and the count goes from 33 to 34.
* `docs/runbooks/annual-purge.md`: step 4 runs the command's dry run, then the local classifier
  delete, then the cassette delete with `CASSETTES_CODE` (and `--confirm-prod` in prod). The heredoc
  script is gone, and the Tooling row names the command.
* `tests/docs/test_annual_purge_runbook.py`: the five script tests and the byte-for-byte twin are gone.
  Three tests check that step 4 lists with the command from the checkout, deletes only with the dry
  run's code (and `--confirm-prod` in prod), and keeps no copy of the rule and no whole-directory
  delete. The file no longer imports `debate_core`.
* `tests/fixtures/model_cassettes/README.md`: the sentence on `caselists`.

## Deviations from the spec

1. **"With the directory read" vs. "a … path in the command's output"** (forbidden). The PM context
   asks the output to give the directory read, while the spec forbids a path in the output. The
   forbidden list governs. The output names the directory as `<data dir>/landscape/model-cassettes/`,
   with the environment, and never this machine's path. `--json` carries the same template in
   `directory` and whether the directory exists in `directory_found`. If the PM wants the real path
   shown, that needs an amendment to the forbidden list.
2. **No smoke check.** Agreement 5 asks a new CLI command for a `tests/smoke` check, but the spec has no
   smoke node and `tests/smoke` is not among its packages, so none was added. The proposal is in the
   relay block below.
3. **The affected set (250 files, about 2.6 minutes) is left to the pull request's `ci`** under
   agreement 10, as t31's was. What was run within the limit is listed above.

## Decisions and assumptions

* **The confirmation follows `caselist retire`'s pattern** (and `tub index prune`'s): a dry run by
  default, a 12-hex-digit code, `--delete --confirm <code>` in place of `--execute --confirm`, and
  `--confirm-prod` to delete in prod. The code check lives in `delete_caselist_cassettes` itself, on
  the same listing the delete acts on, so no caller can delete without having seen it.
* **The code covers the sole and shared cassette names, not the caselist's slug.** A mutation run found
  the slug in the digest indistinguishable from its absence. Two caselists' codes agree only when
  neither names a cassette alone and both share the same cassettes, and then a delete with either code
  takes this caselist's name off those cassettes, which is what its own code does. So the slug was
  dropped (agreement 8), and the docstring says why. Unattributed and other caselists' cassettes are
  left out because the delete never touches them.
* **Its own module, `commands/landscape_cassettes.py`**, not `commands/landscape.py`, per the registry's
  "one module per command" and to keep the affected set of each smaller. It builds on t33's exit
  codes: `1` for a refusal or an unreadable cassette, `2` for a non-slug `--caselist`.
* **An unreadable cassette is caught as the listing's `DomainError`**, reported as
  `CASSETTE_UNREADABLE` with the class's code in `cause_code`, and never with its text: a
  `FixtureFileError`'s message holds the file's path, and a misfiled file's name could be a school's.
  The command could not import `FixtureFileError`. No command module imports `debate_core.integrations`
  (importing the app must load none, as `test_container_factories.py` checks), and
  `debate_core.integrations` is outside this task's packages. Within the listing nothing else raises a
  `DomainError`: an `OSError` goes to the generic handler, which names only its class.
* **A non-slug `--caselist` is refused without being repeated**, since a mistyped value could be a
  school's name.
* **It needs no checkout, and the runbook still runs it from one.** The command reads no `prompts/`, so
  the checkout that ran the model stage and an installed build read the same directory for the same
  `DEBATE_ENV` (both profiles give `~/.debate-research/<env>`). Step 4 runs it with `uv run` from the
  checkout the purge window is already in, because the installed build may predate the command. The
  step says what `No such command 'cassettes'` means.
* **Step 4's delete is two blocks.** The local classifier delete is unchanged. The cassette delete is
  skipped when the dry run says there is nothing to delete (it prints no code then), so an empty
  cassette directory never blocks the classifier delete.
* **No directory is today's state, and it is not an error:** the command prints `No model cassettes in
  <env>: the landscape model stage has recorded none on this machine (no <data dir>/landscape/model-cassettes/
  directory).` and `Nothing to delete.`, exits `0`, and creates nothing.

## Operator follow-ups

None.

## Follow-up work

1. **A smoke check for `landscape cassettes`** against the installed binary: an empty data directory
   exits `0` with `directory_found` false, and a planted synthetic directory counts by hand. It goes in
   `tests/smoke/test_landscape_smoke.py`, in an E32 task that lists `tests/smoke`.
2. **The removal runbook's cassette paragraph** (`caselist-removal.md`, "The model stage's cassettes")
   still says to delete a caselist's recordings by hand, and could call this command. But a takedown
   differs from a retention purge, because a shared cassette keeps the removed card's text for the
   other caselist. That is a policy question for the PM, below.

```text
PM questions from v1-e32-t34 (landscape cassettes command), 2026-10-31.

1. Smoke check. Agreement 5 asks a new command for a tests/smoke check; t34's packages do not
   include tests/smoke, so none was added.
   Options: A. a small E32 follow-up task adds it (empty data dir, planted synthetic directory);
            B. fold it into the next E32 task that touches tests/smoke.
   Recommendation: A. It is about 30 lines, and the command first matters on Friday 2026-11-06.

2. The directory in the output. Your context asked for "the directory read"; the spec forbids a path
   in the output. The command prints "<data dir>/landscape/model-cassettes/" with the environment,
   never this machine's path.
   Options: A. accept the template (no amendment);
            B. amend the forbidden list to allow the data directory's own path.
   Recommendation: A. The environment plus the template identifies the directory, and a home-folder
   path carries a username.

3. Takedowns and shared cassettes. caselist-removal.md says to delete a removed caselist's cassettes
   by hand. This command, used there, keeps a shared cassette, which still holds the removed card's
   text for the other caselist.
   Options: A. the removal runbook calls this command, and shared cassettes stay (as in a purge);
            B. a removal also deletes the shared cassettes that hold the removed source's cards, which
               needs a command keyed by source, not by caselist;
            C. leave the removal paragraph as it is.
   Recommendation: A for now, with B filed if the policy says a takedown must reach every copy. The
   cost of B for the other caselist is a re-recording, never a wrong answer.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-31

**Notes:**

The command is in place before Friday's LD run records the first real cassettes, which is why it was
picked now.
1. **ac1 passes.**
   * Red on a refuse-nothing skeleton: 24 failed, all at assertions. The first draft's KeyErrors
     were turned into assertion failures before the counted run, and the report says so.
   * The new runbook tests are red against HEAD's step 4 (3 failed) and green on the new one.
   * Green: 66, and the node criterion passes (23).
   * All five of the PM's mutants are caught, with 3 and 4 each split into two forms.
   * Of the session's own mutants, the two that survived were acted on:
     * the slug in the code was dropped, with the reasoning recorded;
     * the spent code is now pinned null after a delete.
2. **The confirmation: accepted.** It follows `caselist retire` and `tub index prune` (12 hex digits,
   a dry run by default, `--confirm-prod` in prod). The check lives inside
   `delete_caselist_cassettes`, on the same listing the delete acts on, so no caller can delete what
   it didn't list.
3. **Decisions accepted:**
   * its own command module;
   * t33's exit codes;
   * an unreadable cassette reported as `CASSETTE_UNREADABLE` with its class code and never its text,
     since the mutant that removed the catch would print a misfiled file's name;
   * a non-slug `--caselist` refused without being echoed;
   * one container helper for the cassette directory, now shared by the model stage and evaluate;
   * step 4's delete split in two, so an empty directory never blocks the classifier delete;
   * no directory treated as today's normal state, exiting 0 and creating nothing;
   * running it from the checkout, with the step saying what `No such command 'cassettes'` means.
4. **Deviation 1 / Q2: A.** The `<data dir>/landscape/model-cassettes/` template with the
   environment is enough, and a home-folder path carries a username. No amendment is needed.
5. **Deviation 2 / Q1: A, combined with Q3 below.** One p3 E32 task adds the smoke check.
6. **Deviation 3:** the affected set (250 files, through the root conftest) is left to the PR's
   `ci` under agreement 10, as t31's was. The CLI files the change reaches by name (258), the
   cassette, models and docs tests (754) and the always-run tests (334) were run within the limit.
7. **Q3, takedowns: the PM's ruling.** A removal has to reach every copy of the removed text, so it
   is not a purge. Until a command does it:
   * `caselist-removal.md`'s paragraph stays as written (C). "That caselist's recordings" means
     every cassette naming the caselist, shared ones included. The cost to the other caselist is a
     re-recording, never a wrong answer.
   * No unattributed cassette exists (there is no directory yet), and every cassette from Friday on
     names its caselists, so the paragraph reaches every copy.
   * The p3 E32 task above adds a removal form of this command: sole and shared, behind its own
     code. The removal runbook then calls it. Keying it by source is not needed for that.
8. **Merge:** a plain `scripts/task pr` once `ci` is green. No operator step follows. The command
   first has something to count after Friday 2026-11-06's LD run.
