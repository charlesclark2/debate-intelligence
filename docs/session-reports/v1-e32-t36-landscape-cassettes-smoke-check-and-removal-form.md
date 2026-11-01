# Session report: v1-e32-t36-landscape-cassettes-smoke-check-and-removal-form

| | |
|---|---|
| Task | `v1-e32-t36-landscape-cassettes-smoke-check-and-removal-form` — landscape cassettes gains a smoke check and a removal form that reaches every copy |
| Spec | [`plan_specs/v1/e32-argument-landscape/t36-landscape-cassettes-smoke-check-and-removal-form.yaml`](../../plan_specs/v1/e32-argument-landscape/t36-landscape-cassettes-smoke-check-and-removal-form.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t36-landscape-cassettes-smoke-check-and-removal-form` |
| Session status | COMPLETE |

## Summary

`debate-research landscape cassettes` gains a removal form, `--for-removal`. It deletes every cassette
naming the caselist, sole and shared, and every unattributed one, and keeps only the cassettes of
other caselists. It sits behind a confirmation code of its own, with `--confirm-prod` in prod. The
check is in the application's delete (`delete_caselist_cassettes_for_removal`). A purge's code is
refused by the removal and a removal's by the purge, even on a directory where both would delete the
same cassettes. `caselist-removal.md`'s cassette paragraph is now its own section, which runs the
form as a dry run and then a delete with its code, and still tells the PM. `tests/smoke/test_landscape_smoke.py`
checks the command against the checkout's script and an offline stamped installed build, and fails
against planted breaks on both.

**Look at this first:** to make "the digest includes the form" something a test can catch, both
codes now digest one shape, `{form, deleted, withdrawn}`. That changes how the **purge's** code is
computed, though not what the purge deletes or how it checks the code. t34's tests pass unedited.
Decision 2 explains it, and the PM question below offers a way back. The affected set (252 files,
through the root conftest, as in t34) took over two minutes, so it is left to the PR's `ci` under
agreement 10 (Deviation 1).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `landscape-cassettes-smoke-check-and-remo` (Cassettes removal form) | Done | Skeleton and red run (`0bf550a`), the removal form (`c259726`), the smoke check (`5c3f371`), one code shape (`a8ec205`), the runbook (`66223da`), the annual purge's list of what nothing does (`053b350`). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the smoke check runs against the checkout's script and an installed build, and fails against a break | PASS | **Checkout's script:** `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest tests/smoke/test_landscape_smoke.py -k cassettes -n 0 -q` → `3 passed, 3 deselected`. Breaks 7a to 7d in the mutation table each fail it. **Installed build:** an offline stamped build of `a8ec205` (`git archive`, `stamp_build.py stamp --version 0.0.1.dev36`, `uv build --offline` for both wheels, `uv pip install --offline --no-deps` into a scratch venv, then `debate_core`/`debate_cli` `__file__` checked under the venv's site-packages with no `packages/` path on `sys.path`). `DEBATE_SMOKE_BIN=<venv>/bin/debate-research DEBATE_SMOKE_EXPECT_SHA=<sha> DEBATE_SMOKE_EXPECT_TAG=v0.0.1-dev.36 … pytest tests/smoke/test_landscape_smoke.py` → `6 passed in 8.03s`. Two breaks were then planted in the *installed* copies. Shared counted as sole: `1 failed` (`{'sole': 5, …} == {'sole': 2, …}`). The command creates the directory: `1 failed` (`[…/smoke-data/landscape/model-cassettes] == None`). Restored with `cmp`, then `3 passed`. |
| ac2: the removal form deletes sole, shared and unattributed behind its own code and keeps other caselists'; each form refuses the other's code; the runbook paragraph runs it; tests shown failing first | PASS | **Red:** against the skeleton (`--for-removal` routed to a delete that was the purge's, under the purge's code) the two test files gave `15 failed, 62 passed`, every failure at an assertion. The 62 are t34's 43 unchanged and 19 new tests a purge already satisfies: no code or a wrong code refused, an unreadable file, a non-slug, no name printed, a code that moves with the sole and shared cassettes. **Green:** `77 passed`, then `78` with the unattributed-only case. **Runbook:** `tests/docs/test_removal_runbook_cassettes.py` against the old paragraph → `3 failed, 1 passed`. The one that passed is "no block deletes by hand", since the old paragraph had no block; d1 below shows it failing. Green `4 passed`, and with the other runbook tests `79 passed`. |
| Node: `uv run pytest packages/debate_cli/tests -k cassette` | PASS | Run as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_cli/tests -k cassette -q` → `39 passed in 9.46s`. |

### Mutation runs

Each mutant was applied to the committed source by a script that saved the bytes, matched its text
exactly once (or reported "did not apply"), ran the selection, read the verdict from pytest's summary
line, and restored and compared the bytes. Selections: the two unit files (`test_cassette_filing.py`,
`test_landscape_cassettes.py`, about 3 s), or `tests/smoke/test_landscape_smoke.py -k cassettes`
against the checkout's script. No Hypothesis property is involved. The PM's seven mutants are 1 to 7.
The `s` rows are this session's own.

| Mutant | Result | Caught by |
|---|---|---|
| 1 the removal keeps shared cassettes | CAUGHT (5 failed) | `test_a_removal_deletes_the_caselists_sole_shared_and_unattributed_cassettes`, the re-recording test, the CLI delete test |
| 2 the removal keeps unattributed ones | CAUGHT (5 failed) | the same |
| 3 the removal deletes another caselist's sole cassette (every filing deleted) | CAUGHT (5 failed) | the same; `snapshot == {OTHER: …}` |
| 4a the removal accepts the purge's code as well as its own | CAUGHT (4 failed) | `test_a_purges_code_is_refused_by_a_removal_and_a_removals_by_a_purge[cassettes, coinciding]`, CLI `[coinciding]` |
| 4b the removal's code is the purge's | CAUGHT (7 failed) | the same, plus the code-moves-with-an-unattributed-cassette test |
| 4c the codes drop the form (first shape) | **SURVIVED**, before `a8ec205` | The removal's digest then differed from the purge's by its extra `unattributed` key, so the form key decided nothing. Acted on: Decision 2. |
| 4c the codes drop the form (one shape, `a8ec205`) | CAUGHT (2 failed) | `[coinciding]` in both files: there the form is the only difference |
| 4d the removal's code names the purge's form | CAUGHT (2 failed) | `[coinciding]` in both files |
| 5 the purge accepts the removal's code as well as its own | CAUGHT (4 failed) | the same pair of tests |
| 6a a shared cassette's name in the removal's text | CAUGHT (1 failed) | `test_no_removal_run_prints_or_logs_a_cassettes_content_its_name_or_a_path[text]` |
| 6b cassette names in the removal's `--json` | CAUGHT (1 failed) | the same, `[--json]` |
| 7a smoke: the command creates the cassette directory | CAUGHT (1 failed) | `test_landscape_cassettes_on_an_empty_data_directory_finds_none_and_creates_nothing` |
| 7b smoke: a shared cassette counted as sole | CAUGHT (1 failed) | `test_landscape_cassettes_counts_a_planted_directory_and_changes_nothing` |
| 7c smoke: an unattributed cassette counted as another caselist's | CAUGHT (2 failed) | the planted count and the removal smoke check |
| 7d smoke: the removal keeps shared cassettes | CAUGHT (1 failed) | `test_landscape_cassettes_for_removal_deletes_every_copy_with_its_own_code` |
| s1 the removal in prod skips `--confirm-prod` | CAUGHT (1 failed) | `test_a_removal_in_prod_also_needs_confirm_prod` |
| s2 `--for-removal --delete` routed to the purge's delete | CAUGHT (9 failed) | the CLI removal tests |
| s3 the removal's dry run prints the purge's code | CAUGHT (11 failed) | the CLI removal tests |
| s4 the dry run's code line ignores unattributed cassettes | CAUGHT (1 failed) | `test_an_unattributed_cassette_alone_is_something_for_the_removal_and_nothing_for_the_purge`, written before the run for this gap. Otherwise a directory holding only unattributed cassettes would read "a removal would delete nothing" and the delete would be skipped. |

Runbook mutants against `tests/docs/test_removal_runbook_cassettes.py`, applied to
`caselist-removal.md` the same way: d1 an `rm -r …/model-cassettes` line in the delete block; d2 the
dry run without `--for-removal`; d3 the delete inside the dry run's block; d4 prod without
`--confirm-prod`; d5 "tell the PM" dropped; d6 the delete block's `DEBATE_` guard dropped; d7 the
"Stop, and do not run the next block, if" sentence reworded. All 7 were caught, each by the test for
its reason.

### Before the report

| Check | Result |
|---|---|
| `uv run scripts/affected_tests.py` | `252 of 625 test files (40.3%) chosen in 17.7 s from 10 changed files`. The route is the root conftest → `integrations.models.fake_router` → `models/__init__` → `record_replay` → `application.cassette_filing`. |
| `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python scripts/affected_tests.py --run` | Stopped at its 115-second limit (exit 124) about 8% of the way through, with no failure or error in what had run. Left to the PR's `ci`: Deviation 1. |
| Always-run list + `tests/docs/` + `tests/smoke/test_landscape_smoke.py` (`-n auto -m "not slow and not live"`) | `552 passed in 29.82s` |
| `packages/debate_core/tests/integrations/models/`, `test_cassette_filing.py`, `test_landscape_cassettes.py`, `test_installation.py`, `commands/test_doctor.py`, `bucket_mode/test_bucket_mode_lock.py` | `755 passed in 31.35s` |
| `packages/debate_core/tests/application/` (`-p no:randomly`) | `4704 passed in 102.55s`, with load near 22 |
| `uv run --frozen ruff format --check .` / `ruff check .` | `1731 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright packages/debate_core packages/debate_cli tests/smoke/test_landscape_smoke.py tests/docs/test_removal_runbook_cassettes.py` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `check_thin_handlers.py` / `check_links.py` / `docs_index.py --check-descriptions` / `check_command_blocks.py` | `70 … handlers within 25 statements` / `OK: 3232 relative links and anchors` / `All 61 indexed documents … have a description` / `OK: no # comments in 637 shell code blocks` |
| `uv run scripts/validate_specs.py` | `OK: 549 files, 41 epics, 486 tasks, 22 releases` |

## Files changed

* `packages/debate_core/src/debate_core/application/cassette_filing.py`: `delete_caselist_cassettes_for_removal`,
  `CaselistCassettes.removal_confirmation`, and one digest shape for both codes (`_confirmation`,
  `PURGE_FORM`, `REMOVAL_FORM`). `delete_caselist_cassettes` is byte-identical.
* `packages/debate_cli/src/debate_cli/commands/landscape_cassettes.py`: the `--for-removal` flag, its
  rendering (`_removal_display`), and a `for_removal` key in the `--json` data of both forms.
* `packages/debate_core/tests/application/test_cassette_filing.py` and
  `packages/debate_cli/tests/test_landscape_cassettes.py`: new tests appended after t34's, which are
  unedited apart from one sentence added to each module docstring.
* `tests/smoke/test_landscape_smoke.py`: three cassette checks at the end of the existing landscape
  smoke file.
* `docs/runbooks/caselist-removal.md`: the cassette paragraph is now "### The model stage's cassettes
  (E32)", with a dry run block and a delete block. `docs/runbooks/annual-purge.md`: one clause in the
  list of what nothing does (item 4). Step 4 is unchanged.
* `tests/docs/test_removal_runbook_cassettes.py`: new, the section's shape.
* The spec's phase, and this report.

## Deviations from the spec

1. **The affected set was not run to completion.** It is 252 files, reached through the root conftest
   because `record_replay` imports `cassette_filing`, which is t34's route (250 files there). Under
   the 115-second limit it reached about 8% with no failure, and it was stopped. Under agreement 10
   it is left to the PR's `ci`, with no hand-off. The changed areas and the always-run list were run
   within the limit (above).

## Decisions and assumptions

1. **`--for-removal`, the PM's suggested name, kept.** It names the procedure that runs it, as
   `caselist-removal.md` and `caselist remove` name it, so nobody reaches for it in a purge. A name
   for the mechanism (`--every-copy`, `--shared-too`) would read as a stronger purge.
2. **One digest shape for both codes**: `sha256({"form", "deleted", "withdrawn"})[:12]`. The purge
   gives `deleted=sole, withdrawn=shared`, and the removal `deleted=sole+shared+unattributed,
   withdrawn=()`. A first version kept the purge's t34 digest byte-identical and put a `form` key in
   the removal's digest only. Mutant 4c, which drops that key, survived: the two digests already
   differed by the removal's `unattributed` key, so the form decided nothing, and a later reshaping
   could have made the codes agree. With one shape, a directory where both forms delete the same
   cassettes (`coinciding` in both test files, which is Friday's likely state) differs by the form
   alone, and dropping it or swapping it (4c, 4d) is caught.

   The cost is that the purge's code is computed differently. What the purge deletes, where it checks
   the code, and its tests are unchanged, and the forbidden list's "The purge's delete changed (it
   stays sole-owned only)" holds. A code printed by a t34 build's dry run would be refused by this
   build, which only matters if a dry run and its delete straddle an upgrade. The annual purge runs
   both from one checkout, and no cassette exists yet. The runbook's example code is illustrative.
   PM question 1 offers the way back.
3. **No caselist slug in the removal's code**, for t34's reason, which the PM accepted. Two
   caselists' removal codes agree only when neither has a sole cassette and they share the same ones
   and see the same unattributed ones. Then either code deletes exactly what the other would.
4. **A `for_removal` key in both forms' `--json` data.** Nothing pins the envelope's key set: t34's
   tests read keys one by one, and no smoke check read this command until now.
5. **The smoke check also runs the removal form end to end**: the purge's code refused, then a
   delete with the removal's own code. The spec asked for two cases, and agreement 5 asks a changed
   user-facing surface for its smoke check. Its planted counts (2, 3, 1, 4) differ from each other and
   from the unit tests' (3, 2, 1, 4), so a count reported under the wrong name shows.
6. **The runbook section** has its own heading, so a test can find it and a reader can link it. Its
   blocks set `CASELIST` and `REMOVAL_ENV` and refuse a shell with a leftover `DEBATE_` variable
   (agreement 11): a stray `DEBATE_STORAGE__DATA_DIR` would read another directory and print "No
   model cassettes", which is the "nothing there" that agreement 11 warns against. They do not check
   for a running `caselist pull`, because a pull records no cassette. A model stage recording during
   the window changes the listing, and the code then refuses the delete.
7. **Unattributed cassettes are deleted by the removal**, as the PM's context asked. The output says
   "since one may hold this caselist's text", and the runbook tells the PM the counts.
8. **annual-purge.md's item 4** (in the list of what nothing does, outside step 4) said no caselist's
   delete reaches an unattributed cassette. That is no longer true of a takedown, so it now says no
   purge reaches them and links the removal section.

## Operator follow-ups

None.

## Follow-up work

None.

```text
PM question from v1-e32-t36 (landscape cassettes removal form), 2026-10-31.

1. The purge's code. To make "the digest includes the form" testable, both codes now digest one
   shape, {form, deleted, withdrawn}. The purge's delete and its tests are unchanged, but its code
   is computed differently from t34's. With the purge's digest left byte-identical, a form key in
   the removal's code alone survived its mutant: the digests already differed by an extra key.
   Options: A. accept the shared shape (the form is load-bearing, and the mutant that drops it is
               caught on a directory where both forms delete the same cassettes);
            B. restore t34's purge digest byte for byte and keep the form key in the removal's
               code only, recording that key as an equivalent mutant.
   Recommendation: A. No cassette exists yet, and the purge's dry run and delete run from one
   checkout, so no printed code is invalidated in practice.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-31

**Notes:**

A takedown now reaches every copy, and it does so before Friday's LD run records the first cassette.
1. **ac1 passes.**
   * The smoke check runs against the checkout's script (3 passed), and the four planted breaks (7a
     to 7d) each fail it.
   * It also runs against an offline stamped installed build (6 passed). Two breaks planted in the
     installed copies each fail it, and the copies were restored with `cmp`. That goes further than
     agreement 5 asks.
2. **ac2 passes.**
   * Red over a skeleton that routed the removal to the purge's delete: 15 failed, all at
     assertions. The 62 passes are t34's tests plus cases a purge already satisfies, and the report
     says so.
   * Green: 78, and the runbook's tests pass (4, and 79 with the others).
   * All seven of the PM's mutants are caught, plus s1 to s4 and the seven runbook mutants.
   * s4 is a real find: a directory holding only unattributed cassettes would have read "nothing to
     delete", and the removal would have been skipped.
3. **Question 1: A, the shared digest shape.** The first shape's surviving 4c showed that the form
   key decided nothing. With one shape, the form is the only difference on the coinciding
   directory, and both dropping it and swapping it are caught. What the purge deletes, where it
   checks the code, and its tests are unchanged, so the forbidden entry holds. No cassette exists
   yet, and a purge's dry run and delete run from one checkout, so no printed code is invalidated.
4. **Decisions accepted:**
   * the name `--for-removal`, which names the procedure and so won't read as a stronger purge;
   * no slug in the code, for t34's reason;
   * `for_removal` in both forms' `--json`;
   * the removal smoke-checked end to end, with planted counts that differ from the unit tests';
   * the runbook section with its own heading, `CASELIST` and `REMOVAL_ENV`, and the `DEBATE_`
     guard;
   * unattributed cassettes deleted, with the reason in the output;
   * annual-purge item 4 corrected to "no purge".
5. **Closing checks:** the affected set (252 files through the root conftest, t34's route) is left
   to the PR's `ci` under agreement 10. The always-run list with docs and smoke (552), the model and
   cassette areas (755), all of core application (4,704), ruff, pyright, lint-imports, thin
   handlers, the doc checks and the specs are clean.
6. **Merge:** a plain `scripts/task pr` once `ci` is green. No operator step follows.
