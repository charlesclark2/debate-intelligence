# Session report: v1-e30-t25-store-sync-withholding

| | |
|---|---|
| Task | `v1-e30-t25-store-sync-withholding` — store sync pushes no manifest the publisher withholds, and junk beside a held link does not keep its row |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t25-store-sync-withholding.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t25-store-sync-withholding.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t25-store-sync-withholding` |
| Session status | COMPLETE. Every criterion passed; the Goal is `Succeeded` |

## Summary

A `store sync` push now asks the publisher, for each manifest it would send, whether a publish
withholds it. It asks the publisher's own one-snapshot plan (`SnapshotPlan.withholding_rows`), as
status does for its hint (`v1-e30-t19`). A withheld manifest is planned `skipped`, and its reason
is the publisher's own message, word for word. The rest of the push goes ahead. A pull is
unchanged. The question costs no request. Item (2) is one change to the shared rule,
`hold_on_skipped_member`: an `__MACOSX/<dir>/._<name>` member is now also asked about the file it
shadows, `<dir>/<name>`. The importer, the removal's manifest and inbox rewrites, status and the
publisher therefore agree, and `status_service.py` needed no edit.

**Four things to look at first:**

1. **A manifest the publisher cannot read is now skipped, not pushed** (Decision 4). A publish
   refuses it whole, so a push no longer sends it. The skip reason is the publisher's refusal,
   which names the key and the line number. Three older tests used `week one` as a stand-in
   manifest, and I gave them a manifest a publish could read (Deviation 1).
2. **The reason is on the plan, not in the JSON summary** (Decision 6, PM question 1). The summary
   counts a withheld manifest under `skipped`, as it did t22's held-only blobs. The guide's
   `skipped` row names the reason. No per-object reasons reach `--json` or the table, before or
   after this task.
3. **An earlier build's manifest with junk at a held path is now withheld by the publisher**
   (Decision 8). Status names it as a held skipped row. This follows from item (2) and your t23
   ruling, and the fix is the removal run again.
4. **Commit `edb6a11` landed with a lint error.** I chained `ruff check | tail -1 && git commit`,
   which is exactly what your notes warn against. `8a26f05` fixes the line. Every later check ran
   bare.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `sync-withholding`: Store sync withholding | Done | Both items, the guide, a smoke check, the cross-build check. Its criterion passes: `589 passed` |

## Acceptance criteria

"The start commit" is `c1bb09b`, this branch's first commit. Each build's source was exported with
`git archive <ref> packages/debate_core/src packages/debate_cli/src` into the scratch directory and
put first on `PYTHONPATH`. I checked that `debate_core.__file__` resolved to that copy. The tests
are this branch's. "The agent's build" is `v1.1.0-dev.18` (`0268cf7`), per your notes. Every test
uses moto, temporary data directories and a temporary `HOME`. No test or command read the
operator's `~/.debate-research`, `~/.aws` or LaunchAgents, and none touched AWS or the network.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: a push skips each manifest the publisher withholds, for each row kind, with its reason, and pushes the rest, by test shown failing first; the guide's `skipped` row names the reason | PASS | **The row kinds, counted from the code.** `withholding_rows` is the union of `suppressed_rows`, `held_rows` and `held_skipped_rows`. `suppressed_rows` fires on `suppresses(digest, disclosure=…)`, which is true for a whole file or for one disclosure (a caselist path, or a camp path under `camp_path_scope`). That makes four kinds: a suppressed file, a withdrawn disclosure, a held stored row and a held skipped row. They are tested as seven cases: *a suppressed file*, *a withdrawn disclosure*, *a withdrawn camp path*, *a held row*, *a held row in a complete archive*, *a held link*, and *junk at the held path*. **Red first**: `uv run --frozen pytest packages/debate_core/tests/application/caselist/test_store_sync_withholds_manifests.py` at `6e5407b` (tests only) → `12 failed, 2 passed`. Every failure was an assertion, such as `AssertionError: manifests/testcl26/2026-09-08.jsonl was planned new` and `assert [] == ['manifests/t...-09-22.jsonl']`. The two that passed are guards (a pull; a rewrite that withholds nothing). Through the composition root, `test_store.py::…::test_a_push_leaves_out_a_manifest_the_publisher_withholds` → `assert (2, 0) == (1, 1)`. The complete-archive kind, added after mutant S9, was red on the start commit's source: `manifests/testcl26/full/2026-10-09.jsonl was planned new`, `2 failed`. The unreadable-manifest test was red because the plan raised `UnreadableManifest` and the push stopped. **Green**: `test_a_push_skips_the_manifest_the_publisher_withholds_with_its_reason_and_pushes_the_rest[<kind>]`. For each kind, the manifest is planned `skipped` while `2026-09-22` beside it is `new`. After `execute` the run succeeds, the withheld key is absent from the bucket and the other is present. The reason **equals** the `manifest_error` of a real publish of that snapshot, and names no school, team, path, `.docx` or `__MACOSX`. Through the binary: `tests/smoke/test_caselist_remove_smoke.py::test_junk_beside_a_held_link_has_no_row_and_a_push_sends_no_manifest_the_publisher_withholds` (Deviation 2). **Cost**: `test_a_push_asks_only_about_manifests_it_would_send_and_makes_no_extra_request[<kind>]`. A counting wrapper on the bucket records the same listings and heads with the question as without it. The question is asked only of the two manifests the push would send. **Pull**: `test_a_pull_is_not_asked_about_withholding`. **The guide**: `docs/guides/evidence-store-cli.md`, the `skipped` row |
| **ac2**: an archive with `__MACOSX` junk beside a link at a held path imports with no row at that path, and the inbox rewrite agrees, by test shown failing first | PASS | **Red first**: `uv run --frozen pytest packages/debate_core/tests/application/caselist/test_junk_beside_a_held_link.py` at `8a03cb9` (tests only) → `5 failed, 4 passed`, all assertions. The import kept the junk row (`AssertionError: the junk's row names the held path`). The inbox rewrite dropped the link and kept the junk (`(REWRITE, ['Alder Point/KR/…Round 2.docx'], 2) != (REWRITE, [… , '__MACOSX/Alder Point/KR/._…Round 2.docx'], 1)`). Status counted one held skipped row, not two (`('RM-2026-01',) == ('RM-2026-01', 'RM-2026-01')`). Junk alone kept its row, and the re-run kept it too. The four that passed are guards: a path nothing holds, at import and in the inbox; the week the hold dates from; an earlier build's junk at a path nothing holds publishing. **Green** (`22f3914`): `9 passed`, and with `t21`'s and `t22`'s files `52 passed`. **They agree**: `test_running_the_removal_again_takes_the_junk_row_out_and_agrees_with_this_builds_import`. The week the removal rewrote and the same archive imported again by this build are the same file, byte for byte. Status and the publisher: `test_status_and_the_publisher_count_an_earlier_builds_junk_row_as_a_held_skipped_row` (`held_skipped_rows == (REQUEST, REQUEST)`, `WITHHELD`, message `2 skipped member row(s) at a path a removal holds (RM-2026-01)`, no path). No edit to `status_service.py` |
| Node `sync-withholding`: `uv run pytest packages/debate_core/tests/application -k "store or sync or held"` | PASS | `589 passed in 39.93s`, run as the spec writes it |
| **The cross-build check** (your notes: the agent's build reads every file this build writes) | PASS | `write_junk_beside_a_held_link_files.py` (run by path, not collected) writes this task's scenario. After the removal, an earlier build imports a week with a link and its junk at the held path, and a week with both waits in the inbox. This build publishes and pushes `manifests/` with `store sync --apply`. The removal is run again (which rewrites the waiting archive), and the week is imported again. I wrote one set with this build and one with the start commit, each with `t21`'s `write_held_path_files.py -k pull` for the `run/` part. Each set was read with `t21`'s `read_held_path_files.py` by this build, the start commit and the agent's build: **six reads, every one exit 0**, each identical to this build's read but the header. The two sets differ where they should. At the start commit, the push sent `2026-10-11.jsonl`, which the publisher withholds. The re-run then rewrote it in the bucket too: removal log `manifests_rewritten` 2 and `s3_versions_deleted` 1, against 1 and 0 here. That manifest kept the junk row, and the rewritten inbox archive kept its `__MACOSX` member. No new file, field or record: the same five records here and in the bucket |
| Full suite, eighths under load (`uv run --frozen pytest -n auto -m "not slow and not live" --part K/8`) | PASS (one known failure) | Parts 1 to 6 ran at `d1c50ee`: `1159 passed` (71 s); `1161 passed` (71 s); `1163 passed, 2 warnings` (99 s); `1155 passed, 1 warning` (82 s); `1151 passed` (66 s); `1163 passed, 1 xfailed` (121 s). Parts 7 and 8 failed there on two `test_retryable_store_failures.py` tests, which were mine (Deviation 1). After the fix they ran at `52d4da4`: `1160 passed, 1 failed` (71 s) and `1159 passed, 1 xfailed` (64 s). Only that file changed between the two commits. The one failure is `tests/evals/parser/test_parser_eval.py::test_the_labeled_pr_subset_holds_the_baseline`, which your notes list as known on this Mac until the baseline is written; not investigated. The load average was 8 to 28. Each part ran under a hard stop, and none hit it. The whole removal smoke file, run after the new check was added: `38 passed` |
| Lint, types, contracts, docs | PASS | `ruff format --check .`: 842 files formatted. `ruff check .`: clean. `uv run --frozen pyright`: `0 errors`. `lint-imports`: `12 kept, 0 broken`. `check_thin_handlers.py`: 22 within 25 statements. `docs_index.py --check-descriptions`: 36 described. `check_command_blocks.py --base origin/dev`: OK. `validate_specs.py`: `OK: 377 files, 38 epics, 319 tasks, 20 releases` |

### Mutation runs

Each run applied one textual change to committed source and ran 201 to 203 tests from ten files:
both new files, `t21`'s and `t22`'s, `test_import_paths_consult_suppression.py`,
`test_removal_purges_inbox.py`, `test_inbox_retention_of_junk_only_releases.py`,
`test_evidence_sync.py`, `test_store.py` and `test_os_error_text_in_results.py`. Flags:
`-p no:randomly -p no:cacheprovider --no-cov -n 4`. The driver refuses a mutant whose target does
not appear exactly once. It gives every run a new, empty `HYPOTHESIS_STORAGE_DIRECTORY` (working
agreement 8; none of these tests is a Hypothesis property). It restores the file from a byte copy
in a `finally`, then checks its sha256 and `git diff --quiet`. Rows 1 to 13 ran on `fa895ca`. Row
12 ran again on `d1c50ee`, and rows 14 and 15 on `b9387ce` against the smoke check alone. Every
catch below is a failing assertion.

| # | Mutation | Result | First failing test |
|---|---|---|---|
| 1 | **J1: junk is asked about its own path only** (the start commit's rule) | CAUGHT, 6 failed | `test_junk_beside_a_link_at_the_held_path_imports_with_no_row_at_either_path` |
| 2 | J2: the shadowed path loses its directory | CAUGHT, 6 failed | the same |
| 3 | J3: `_shadowed` (junk beside a *suppressed* file) no longer reads AppleDouble, which guards my refactor of the existing rule | CAUGHT, 1 failed, against `test_removal_plan.py` | `test_removal_plan.py::TestSharedFiles::test_junk_that_shadows_a_removed_file_goes_even_when_its_team_stays`. It survived the ten-file set, which has no such test. With `test_removal_plan.py` added, that set errors in setup with no mutant at all (`fixture 'removal_world' not found` when it runs beside `test_evidence_sync.py`). So I ran J3 against `test_removal_plan.py`, `test_held_path_inbox_copies.py` and the junk file instead |
| 4 | **S1: a push never skips a withheld manifest** | CAUGHT, 8 failed | `…pushes_the_rest[a held row]` |
| 5 | S2: a pull is asked too | CAUGHT, 3 failed | `test_a_pull_is_not_asked_about_withholding` |
| 6 | S3: every manifest is asked about, not only those a push would send | CAUGHT, 6 failed | `test_a_push_asks_only_about_manifests_it_would_send_and_makes_no_extra_request[a suppressed file]` |
| 7 | S4: every manifest a push would send is skipped | CAUGHT, 18 failed | `…pushes_the_rest[a held row]` |
| 8 | **S5: the reason is restated** (`withheld by caselist publish`) instead of the publisher's message | CAUGHT, 7 failed | the same |
| 9 | **S6: the rule is restated, suppressed rows only** | CAUGHT, 4 failed | the same |
| 10 | **S7: the rule is restated, suppressed and held stored rows only** | CAUGHT, 2 failed | `…[a held link]`, `…[junk at the held path]` |
| 11 | S8: an unreadable manifest ends the push | CAUGHT, 1 failed | `test_a_push_skips_a_manifest_the_publisher_cannot_read_and_carries_on` |
| 12 | S9: the push reads the weekly series only | **SURVIVED, then CAUGHT** | `…[a held row in a complete archive]` |
| 13 | S10: the composition root builds `store sync` without the question | CAUGHT, 1 failed | `test_store.py::…::test_a_push_leaves_out_a_manifest_the_publisher_withholds` |
| 14 | S1 against the smoke check | CAUGHT, 1 failed (`assert 2 == 1`, the `new` count) | `test_junk_beside_a_held_link_has_no_row_and_a_push_sends_no_manifest_the_publisher_withholds` |
| 15 | J1 against the smoke check | CAUGHT, 1 failed (`a row names the held path`) | the same |

Row 12's survivor was a missing test. None of my cases had a complete archive's manifest, which
sits a level further down (`manifests/<caselist>/full/<date>.jsonl`). I added that case
(`d1c50ee`), and the mutant was caught. I did not run two mutants that would be equivalent here.
One drops the `content_addressed` guard: a blob's remote key is never under `manifests/`. The
other drops the `manifests/` prefix guard: `read_local_manifest` returns `None` for any other key.

## Files changed

- **`debate_core.application`**
  - `caselist/pipeline.py`: `hold_on_skipped_member` also asks the hold on the file an AppleDouble
    member shadows. `_apple_double_target()` is the one mapping, now shared with `_shadowed`. One
    docstring sentence.
  - `caselist/publish_service.py`: `withheld_manifest_reason()`, the publisher's answer to "would a
    publish withhold this local manifest, and why". Its message is the one a withheld outcome
    carries, or the refusal of an unreadable manifest. One docstring sentence.
  - `caselist/evidence_listing.py`: `read_local_manifest()` reads one manifest from a listing entry.
    `read_local_snapshots` now uses the same per-manifest reader.
  - `caselist/publish_plan.py`: one docstring sentence ("Bytes only held rows name…").
  - `evidence_sync.py`: `WithheldManifests`, `EvidenceSyncService(withheld_manifests=)`, and a push
    plans a withheld manifest `skipped`. A docstring paragraph.
- **`debate_cli`**: `container.py` builds `store sync` with the question.
- **Tests**
  - New: `packages/debate_core/tests/application/caselist/test_junk_beside_a_held_link.py` (9) and
    `test_store_sync_withholds_manifests.py` (17).
  - Run by path, not collected: `write_junk_beside_a_held_link_files.py`.
  - `packages/debate_cli/tests/commands/test_store.py`: one composition-root test. `t22`'s test there
    now shares two helpers with it; its assertions are unchanged.
  - `packages/debate_cli/tests/test_os_error_text_in_results.py` and `test_retryable_store_failures.py`:
    stand-in manifest bodies (Deviation 1).
  - `tests/smoke/test_caselist_remove_smoke.py`: one check, and a clause in its `tests/smoke/README.md`
    row (Deviation 2).
- **Docs**: `docs/guides/evidence-store-cli.md`, the `skipped` row (Deviation 3).
- **Spec**: the Goal's phase.

## Deviations from the spec

1. **Three earlier tests now write a manifest a publish could read.** `v1-e29-t09`'s
   `test_store_sync_names_an_os_error_by_its_class_and_errno` and two of `v1-e01-t20`'s
   `test_retryable_store_failures.py` tests used `week one` as the body of a file under
   `manifests/`. Their point is how an upload failure is reported. The push now reads such a file
   before sending it, and skips it as the publisher would (Decision 4), so no upload was planned to
   fail. Their bodies are now `{"kind": "summary", …}` lines. No assertion changed. The `v1-e01-t20`
   test of a refused object directory still uses `week one` and passes, because the listing fails
   first.
2. **`tests/smoke/` is outside `constraints.packages`**, as it was for `v1-e30-t18`, `t21` and
   `t22`. Working agreement 5 asks for a smoke check when a user-facing surface changes, and
   `store sync --apply` and `caselist import` did. I added one check and a clause in its README row.
3. **The guide's `skipped` row said t22's held-only blobs are skipped "either way".** The code
   skips them on a push only (`direction is SyncDirection.PUSH`). I moved them to a "push only"
   sentence, beside this task's withheld manifests.

## Decisions and assumptions

1. **Only a manifest the push would send is asked about**: one planned `new` or `changed`, after
   the existing cheap checks. One already in the bucket, identical or journaled, is skipped for
   that reason as before, without being read. So a withheld manifest that is already in the bucket
   is reported `identical`, not withheld. Taking it out of the bucket is the removal's job, and
   status names it.
2. **The reason is the publisher's message, word for word**: `_withheld_for_rows`, the
   `manifest_error` of a withheld outcome. The tests compare it with a real publish of the same
   snapshot. It names rows by digest and held skipped rows by request id, never a path.
3. **What it costs per caselist: no request.** The plan is built one snapshot at a time from the
   push's own local listing entry and the suppression state the push already loaded. The manifest
   file is read once for each manifest the push would send. It gets no blob or bucket listing:
   `build_publish_plan(…, local_blobs=(), remote={})`. That works because `withholding_rows` is
   built from the manifest's rows and the list alone, and the plan's source actions are not read.
   The rule itself is not restated: mutants S6 and S7 restate it and are caught. If withholding
   ever came to depend on a listing, this call would need the listings passed in.
4. **A manifest the publisher cannot read is skipped, and the push carries on.** A publish refuses
   it whole (`UnreadableManifest`). The push cannot tell whether a publish would withhold it, so it
   does not send it. Before this task it was pushed. Now it is skipped with the refusal, which
   names the key and line number, never the line. A manifest this user may not open is different:
   `LocalStoreAccessDenied` from the reader is not caught. It now ends the plan, as it ends a
   publish and status. Before this task the push failed that one object at transfer and carried
   on (Follow-up 2).
5. **A pull is not affected.** It writes to this machine, and `test_a_pull_is_not_asked_about_withholding`
   shows the question is never asked on a pull.
6. **The summary is unchanged.** A withheld manifest counts under `skipped` in the JSON and the
   table, and its reason is on the plan's object (`PlannedObject.reason`), as t22's held-only blobs'
   reason is. The guide's `skipped` row lists it. I did not add a per-reason list to `--json`: it
   would be a new key on the payload `v1-e34-t02` reads, and neither the spec nor your notes asked
   for one (PM question 1).
7. **Junk with no link beside it is held too** (your question). `__MACOSX/<dir>/._<name>` names
   `<dir>/<name>` whether or not the archive holds that file. At a held path, in a snapshot the hold
   covers, it is withheld with no row (`test_junk_alone_at_the_held_path_imports_with_no_row`).
   Beside a real upload at a held path it was already withheld, because that upload is refused and
   the junk shadows a suppressed member. Now the hold catches it as well, with the same outcome.
8. **The publisher now withholds an earlier build's manifest that has junk at a held path.**
   `held_skipped_rows` counts the junk row, so such a publish now fails with
   `MANIFEST_NAMES_SUPPRESSED_SOURCE` where it succeeded before. The message counts the rows by
   request, and the fix is the removal run again. That follows your t23 ruling on held skipped rows.
9. **Only `__MACOSX/<dir>/._<name>` is treated as the link.** Two other kinds of junk can name a
   held file and are not covered here. A Word lock file `<dir>/~$<name less two characters>` is
   matched only against real members. AppleDouble written in place as `<dir>/._<name>` is not a
   shadow under either rule (Follow-up 1). Both are as they were before this task.

## Operator follow-ups

None. No command here runs over two minutes, needs a credential, or changes anything outside the
worktree.

## Follow-up work

1. **Other junk that names a held file** (E30). A Word lock file beside a link at a held path, and
   an in-place AppleDouble `<dir>/._<name>`, keep their rows (Decision 9). Both could go into
   `_shadowed` and `hold_on_skipped_member`, if real archives carry them.
2. **One manifest this user may not open now ends a push's plan** (E29). Before this task, it
   failed at transfer as a single object. Catching `LocalStoreAccessDenied` in
   `withheld_manifest_reason`, and planning that object as a failure, would need a plan-time
   failure that `SyncPlan` does not have (Decision 4).
3. **Skip reasons in `store sync --json`** (E29), if you want them (PM question 1).

### PM questions

```text
v1-e30-t25 asks the PM, 2026-10-19:

1. A push skips a withheld manifest under `skipped`, and the reason (the publisher's own message)
   is on the plan's object. The --json summary and the table show counts only, as they did for
   t22's held-only blobs. Options:
   (a) leave it: the count, plus the guide's `skipped` row, is the summary (done);
   (b) add a `skipped_reasons` breakdown to `store sync --json` (a new key on the payload
       v1-e34-t02 reads) and a caption line naming withheld manifests.
   Recommendation: (b), as a small E29 task. An operator whose push quietly leaves a manifest
   behind sees only a count, and the fix (the removal run again) is in the reason they cannot see.

2. A push now skips a manifest the publisher cannot read (Decision 4) instead of sending it.
   Options: (a) skip with the publisher's refusal (done); (b) push it as before; (c) fail the
   run. Recommendation: (a). A publish refuses it whole, and a push should not send what a
   publish refuses.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
