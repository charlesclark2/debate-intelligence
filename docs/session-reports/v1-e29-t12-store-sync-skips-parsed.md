# Session report: v1-e29-t12-store-sync-skips-parsed

| | |
|---|---|
| Task | `v1-e29-t12-store-sync-skips-parsed` — store sync stops moving the parsed store, which caselist parse --publish publishes |
| Spec | [`plan_specs/v1/e29-cloud-evidence-store/t12-store-sync-skips-parsed.yaml`](../../plan_specs/v1/e29-cloud-evidence-store/t12-store-sync-skips-parsed.yaml) |
| Epic / release | `v1-e29-cloud-evidence-store` / `v1.1` |
| Branch | `task/v1-e29-t12-store-sync-skips-parsed` |
| Session status | COMPLETE |

## Summary

`store sync` now plans every key under `parsed/` as `skipped`, of a new kind `parsed_store`, in both
directions and whatever is on either side. That includes a key that is only at the destination,
which used to be `would_delete`. A run that skipped any says so under the table:
`PARSED STORE: <n> object(s) under parsed/ left as they are on both sides. store sync never moves the
parsed store: caselist parse --publish is what publishes it.` `--json` counts them under
`skipped_reasons.parsed_store`. A dry run in either direction prints a note on stderr when
`<data_dir>/objects/parsed/` exists, giving the directory, its file count and the quoted `rm -r` that
removes it. The note never goes in the JSON payload or the journal, never names a file, and nothing
deletes the copy. Sync's call to the occurrence-table guard is removed and the guard itself stays.
e34-t29's seven sync tests are converted, not deleted (list below). What to look at first: the
deviation on `docs/guides/evidence-store-cli.md`, and the decision that a bucket-only `parsed/` key
is `skipped` rather than `would_delete`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `skip-parsed` (store sync skips parsed/) | Done | Commit ids are on `origin/dev` at `cd6f374`, after the sync below. Red first (`51d746e`), implementation (`b249766`), quoting test after a surviving mutant (`3400462`) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: `store sync --push` and `--pull` move nothing under `parsed/` and say so in the summary, by tests shown failing first; every other keyspace moves as before | PASS | **Red**, at `51d746e` against the unchanged code: `.venv/bin/python -m pytest packages/debate_core/tests/application/test_store_sync_skips_parsed.py -q -p no:randomly` → `24 failed`. Each failed on its own assertion: `parsed/` keys planned `new`/`changed` and transferred, or `AttributeError: 'EvidenceSyncService' object has no attribute 'stale_parsed_copy'`. `... packages/debate_cli/tests/commands/test_store.py -k TestTheParsedStoreIsNotSynced` → `6 failed, 1 passed`. The pass was `test_a_machine_with_no_stale_copy_hears_nothing_about_one`, a negative test that the old code also satisfies. **Green**: the same files plus the guard and skip-reason tests → `165 passed`. Other keyspaces: `test_every_other_keyspace_is_planned_and_moved_as_it_is_without_parsed[push/pull]` runs the same `manifests/`, `reports/`, `files/` and blob scene with and without `parsed/` objects. The non-parsed plan is equal object for object and the outcomes are equal. The two `*_plans_parsed_skipped_on_either_side_and_every_other_keyspace_as_written` tests write the expected actions by hand. |
| ac2: a stale `objects/parsed/` copy is reported by `--dry-run` with the command that removes it, and the per-source stamp line is in docs/data/parsed-card-store.md | PASS | `test_a_dry_run_reports_a_stale_copy_with_the_command_that_removes_it[push/pull]`: the whole line, the file left in place, no file name in the output. `test_the_stale_copy_is_reported_on_the_console_and_nowhere_else`: not in `--json`, not printed on `--apply`, the journal holds only the manifest's key. `test_the_command_quotes_a_data_directory_a_shell_would_split`: a path with a space and an apostrophe. `test_a_stale_copy_is_its_directory_and_its_file_count_and_is_left_where_it_is`. The doc line is in the "On a `source` or a `document`" bullet of [Fingerprint versions](../data/parsed-card-store.md#fingerprint-versions). |
| Node `skip-parsed`: Store sync tests pass (`uv run pytest packages/debate_core/tests/application -k sync`) | PASS | `uv run pytest packages/debate_core/tests/application -k sync` → `405 passed in 16.80s` |

### e34-t29's sync tests, converted

From `test_store_sync_newer_fingerprint_table.py`, renamed (`git mv`) to
`test_store_sync_skips_parsed.py`. Each keeps its scene, and each docstring names the test it was:

| Was (refused) | Now (skipped) |
|---|---|
| `test_a_push_of_a_table_a_newer_build_stamped_is_refused_and_the_rest_goes_up` | `test_a_push_skips_a_table_a_newer_build_stamped_and_the_rest_goes_up` |
| `test_a_push_over_the_buckets_table_a_newer_build_stamped_is_refused_and_leaves_it` | `test_a_push_skips_a_table_over_the_buckets_newer_one_and_leaves_it` |
| `test_a_push_of_an_equal_or_older_table_over_an_equal_or_older_one_goes_up_as_before` (4 cases) | `test_a_push_of_an_equal_or_older_table_over_an_equal_or_older_one_moves_nothing` (same 4) |
| `test_a_push_reads_no_stamp_of_an_object_that_is_not_an_occurrence_table` | `test_a_push_skips_every_other_object_under_parsed_too` (index, failures, a per-source file) |
| `test_a_pull_over_this_machines_copy_a_newer_build_stamped_is_refused_and_leaves_it` | `test_a_pull_skips_the_table_over_this_machines_newer_copy_and_the_rest_comes_down` |
| `test_a_pull_over_an_equal_or_older_copy_or_none_comes_down_as_before` (4 cases) | `test_a_pull_of_any_table_over_any_copy_or_none_brings_nothing_down` (same 4) |
| `test_the_sync_takes_the_rules_answer_and_has_none_of_its_own` | `test_the_sync_asks_the_occurrence_table_rule_nothing` (a rule that refuses everything changes nothing, either way) |

Two existing tests changed with the behaviour:
* `test_every_path_that_moves_an_occurrence_table_asks_the_one_rule` in
  `caselist/test_occurrence_table_guard.py` no longer lists `evidence_sync.py` among the callers of
  `refuse_newer_table`.
* `test_at_most_three_distinct_key_prefixes_in_key_order` in `test_evidence_sync_skip_reasons.py`
  used a `parsed/` key as an ordinary identical object. It now uses an `uploads/` key, so the test
  still has four prefixes, of which three are shown.

### Mutants

There were 8, run on committed code and restored with `git checkout` after each (`git status` clean
afterwards). Hypothesis plays no part in these tests.

| Mutant | Result |
|---|---|
| Source-side `parsed/` check removed from `_classify` | caught, 11 failed |
| Destination-only `parsed/` key back to `would_delete` | caught, 5 failed |
| Planned under `SkipKind.IDENTICAL` instead of `PARSED_STORE` | caught, 11 failed |
| Stale copy counted one file short | caught, 1 failed |
| Stale note printed on `--apply` too | caught, 3 failed |
| `PARSED STORE` caption line dropped | caught, 2 failed |
| `rm -r <dir>/*` instead of `rm -r <dir>` | **survived** at first, because the test matched a substring. Now caught, 3 failed, after the line was pinned whole (`3400462`) |
| The path left unquoted | caught, 1 failed, by the new quoting test |

### Closing checks

The affected set is `211 of 380 test files (55.5%)` (`uv run scripts/affected_tests.py`). At about
six minutes for the whole selection that is past two minutes, and the load average was 11. Under the
PM's ruling of 2026-10-19 I did not run it. It is left to the pull request's `ci`, and I ran the
changed test directories and the always-run list, each with the alarm on the interpreter:

* `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest packages/debate_core/tests/application -q -m "not slow and not live"` → `3007 passed in 85.59s`
* `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest packages/debate_cli/tests/commands tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py tests/smoke/test_store_cli.py -q -m "not slow and not live"` → `788 passed in 34.42s`
* `uv run ruff format --check .` → `1059 files already formatted`; `uv run ruff check .` → `All checks passed!`
* `uv run pyright packages/debate_core packages/debate_cli` → `0 errors, 0 warnings, 0 informations`
* `uv run lint-imports` → `Contracts: 13 kept, 0 broken.`
* `uv run scripts/check_command_blocks.py` → `OK: no # comments in 334 shell code blocks in 134 Markdown files`
* `uv run scripts/validate_specs.py` → `OK: 404 files, 39 epics, 344 tasks, 21 releases`

## Files changed

* `packages/debate_core/src/debate_core/application/evidence_sync.py`: the third thing a sync never
  moves, in the docstring and the planner. Adds `PARSED_STORE_PREFIX`, `SkipKind.PARSED_STORE`,
  `StaleParsedCopy` and `EvidenceSyncService.stale_parsed_copy()`. Removes `_refuse_a_newer_table`
  and the guard imports.
* `packages/debate_core/src/debate_core/application/caselist/occurrence_table_guard.py`: drops
  `store sync` from "The paths" and drops `THIS_MACHINES_SYNCED_COPY`, which only sync used. The
  rule, `THE_BUCKET`, `fingerprint_stamps_of_file` and `occurrence_table_of` stay; parse, publish
  and caselist pull use them.
* `packages/debate_cli/src/debate_cli/commands/store.py`: the `PARSED STORE` caption line and the
  dry-run `STALE PARSED COPY` note.
* Tests: `test_store_sync_skips_parsed.py` (renamed and converted), a new
  `TestTheParsedStoreIsNotSynced` in `debate_cli/tests/commands/test_store.py`, and the two existing
  tests above.
* `docs/data/parsed-card-store.md`: the per-source stamp line.
* `docs/runbooks/caselist-scheduled-sync.md`: under `NEWER_FINGERPRINT_TABLE`, the claim that
  `store sync` is refused by the same rule is replaced by "moves nothing under `parsed/`". Under
  `CHECKSUM_MISMATCH`, a Mac at another fingerprint version is named as a cause. Nothing else under
  `docs/runbooks/` implies `store sync` moves parsed data. Grep: `store sync`, `objects/parsed`,
  `--pull`.
* `docs/guides/evidence-store-cli.md`: see Deviations.

## Deviations from the spec

* **`docs/guides/evidence-store-cli.md` changed, outside `constraints.packages`.** It is the
  operator's guide to `store sync` and lists every skip kind and caption line, so leaving it alone
  would document the old behaviour. I added `parsed/` to the `skipped` row, a `parsed_store` row to
  the kinds table, the `PARSED STORE` line, and a short "A stale parsed copy" section with the
  removal command as a template. I did not edit the spec. If you accept this, the PM amendment is
  to add `docs/guides` to `constraints.packages`.

## Decisions and assumptions

* **A `parsed/` key only at the destination is `skipped`, not `would_delete`.** "Skipped whatever
  is on either side" read literally. Otherwise every push from a machine without a stale copy would
  report the whole bucket parsed store as `would_delete`. `manifests/_suppression/` still plans a
  destination-only key as `would_delete`, as before. Changing that was out of scope.
* **The rule goes by bucket key, in every keyspace.** Any key under `parsed/` is skipped, including
  one a misdirected `--blob-prefix parsed/...` would produce.
* **The stale note goes on stderr through `CliOutput.note`, not in the table caption.** Rich wraps
  captions at the table's width, which would break a long path and its `rm -r` across lines. A note
  is soft-wrapped, prints in both output modes, and stays out of the `--json` payload. It prints on
  a dry run only, as the spec and PM context say.
* **The count is objects, not raw files.** `list_objects` skips interrupted-download temp files.
  `rm -r` removes them with the rest of the directory.
* **`rm -r`, not `rm -rf`, and quoted with `shlex.quote`.**
* **Tests use moto in-process**, like every other sync test here. Sockets are disabled and nothing
  reaches AWS.

## Operator follow-ups

After this merges, Charlie removes the stale `objects/parsed/` copy on the operator's Mac, once.
The dry run is read-only, but the removal deletes files on that machine, so both steps are a
hand-off. First, from a checkout at or after the merge, run a dry run (seconds). It prints the
`STALE PARSED COPY` line with the directory, the file count and the exact command:

```bash
DEBATE_ENV=dev uv run debate-research store sync
```

Then paste the command that line ends with. With the default data directory it is:

```bash
rm -r ~/.debate-research/dev/objects/parsed
```

Success looks like this: a second dry run prints no `STALE PARSED COPY` line, and
`~/.debate-research/dev/parsed/` (the real parsed store) is untouched. Do the same with
`DEBATE_ENV=prod` if that data directory was ever pulled into.

## Follow-up work

* `manifests/_suppression/` keys only at the destination are still planned `would_delete`, while
  the module docstring says "skipped, whatever is on either side". This is harmless because nothing
  deletes, but it is inconsistent with `parsed/` now. It belongs to E29 if the PM wants it aligned.

## The PM's conditions, closed (2026-10-22)

All three were closed in this session after the ACCEPTED verdict below. Nothing came out
differently from the review's expectations.

1. **Spec.** `docs/guides` was added to `constraints.packages`, with the PM's ruling as a comment on
   the line above the flow list. The parsed node lists seven packages and no comment text, and
   `uv run scripts/validate_specs.py` reports `OK: 404 files, 39 epics, 344 tasks, 21 releases`.
2. **Docstring.** The `manifests/_suppression/` bullet now says a key at both ends is planned
   `skipped`, and that a key only at the destination is reported `would_delete` and, like every
   `would_delete`, left alone. I added one clause the code also bears out: a key only at the source
   is `skipped` too, because `_classify` checks for the suppression prefix before anything else.
   This changed words only. `.venv/bin/python -m pytest packages/debate_core/tests/application/test_evidence_sync.py packages/debate_core/tests/application/test_evidence_sync_skip_reasons.py packages/debate_core/tests/application/test_store_sync_skips_parsed.py -q`
   → `89 passed in 6.70s`.
3. **Sync.** `scripts/task sync v1-e29-t12-store-sync-skips-parsed` rebased the 7 commits cleanly
   onto `origin/dev` at `cd6f374`, which includes v1-e07-t05 (#395). Nothing was pushed, because the
   branch is not on origin. `uv sync --all-packages` installed `defusedxml==0.7.1` and
   `types-defusedxml==0.7.0.20260504`. I then re-ran:
   * `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest packages/debate_core/tests/application -q -m "not slow and not live"` → `3007 passed in 76.25s`
   * `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest packages/debate_cli/tests/commands tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py tests/smoke/test_store_cli.py -q -m "not slow and not live"` → `792 passed in 31.31s`
   * `uv run ruff format --check .` → `1073 files already formatted`; `uv run ruff check .` → `All checks passed!`
   * `uv run pyright packages/debate_core packages/debate_cli` → `0 errors, 0 warnings, 0 informations`
   * `uv run lint-imports` → `Contracts: 15 kept, 0 broken.`
   * `uv run scripts/check_command_blocks.py --base origin/dev` → OK, including this report

   Two numbers moved because dev moved, not because of this branch. The second pytest command ran
   792 tests, up from 788, and lint-imports kept 15 contracts, up from 13. #395 added two
   import-linter contracts to `pyproject.toml` and their cases to
   `tests/architecture/test_import_contracts.py`. The affected set is now
   `212 of 385 test files (55.1%)`, still past two minutes, so it stays with the pull request's `ci`.

The operator follow-up stands, with the PM's addition: the dry run lists the bucket, so it needs a
current SSO session first.

```bash
aws sso login --profile debate-dev-evidence
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-22

**Notes:**

Accepted, on three conditions closed in this session before the pull request. Then open the pull
request with no `--partial`. If anything comes out differently from what is written here, stop and
ask for another review.

**What the PM checked.** The branch is clean, 5 commits on origin/dev at `e0f19eb`, and the diff
is the 13 files listed. The planner's destination-only branch skips `parsed/` and keeps
`would_delete` for everything else. `stale_parsed_copy` reads only the local side and acts on
nothing. The guard module keeps its other callers.

**Rulings.**

1. **The `docs/guides/evidence-store-cli.md` deviation is accepted.** Leaving the operator's guide
   describing the old behaviour would be worse than the scope edge. v1-e31-t30, running in
   parallel, may also edit `docs/guides`, but a different guide; whichever merges second resolves
   any conflict on sync.
2. **A destination-only `parsed/` key is `skipped`, not `would_delete`. Accepted.** It is the
   spec's "whatever is on either side", and otherwise every push would report the whole bucket
   parsed store as a pending deletion.
3. **`manifests/_suppression/` keeps `would_delete` for a destination-only key; no follow-up
   task.** There, the report is useful: it says the bucket holds a suppression list this machine
   does not. But the module docstring's "Planned as `skipped`, whatever is on either side" is then
   wrong for that case, so correct the words rather than the behaviour (condition 2).
4. **The moto, sockets-off tests** are the existing pattern for sync, and accepted.

**Conditions, all closed in this session:**

1. **Spec:** add `docs/guides` to `constraints.packages`, with
   `# PM ruling 2026-10-22: the operator's store sync guide documents the new skip kind.`
2. **Docstring:** in `evidence_sync.py`'s "Two things a sync never moves" section (now three), make
   the `manifests/_suppression/` bullet say that a key at both ends is `skipped`, and that a key
   only at the destination is reported `would_delete` and, like every `would_delete`, left alone.
   Docs only, no behaviour change. Re-run the module's tests.
3. **Sync onto origin/dev** (`scripts/task sync`). v1-e07-t05 (#395) merged after your base and
   changed `pyproject.toml` and `uv.lock`. Re-sync the venv, then re-run the two closing pytest
   commands, ruff, pyright and `lint-imports`, and record the results.

**Operator follow-up: accepted as written,** with one addition. The dry run lists the bucket, so
it needs a current SSO session (`aws sso login --profile` for the dev operator profile) first.
Charlie runs the removal himself, after the merge. The prod line applies only if that data
directory was ever pulled into.

**Noted, no action.** The surviving `rm -r <dir>/*` mutant, caught once the line was pinned
whole, is the right fix. A removal command is exactly where a substring match is too weak.
