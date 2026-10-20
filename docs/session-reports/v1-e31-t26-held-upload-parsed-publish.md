# Session report: v1-e31-t26-held-upload-parsed-publish

| | |
|---|---|
| Task | `v1-e31-t26-held-upload-parsed-publish` — parse --publish sends nothing of a held upload |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t26-held-upload-parsed-publish.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t26-held-upload-parsed-publish.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t26-held-upload-parsed-publish` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

A held upload, bytes an earlier build imported at a path a removal holds, now reaches neither the
parsed store's aggregates nor the bucket. The parse pipeline asks the publisher's own rule for a
held row, `publish_plan.stored_row_hold`. Before this task that rule was the private body of
`_holds_of_stored_rows`, and now `held_rows`, `held_only_digests` and the parsed store all ask it.
The parse asks it of every disclosure:

* before it parses a source;
* before it writes the source's rows to `index.jsonl`, `failures.jsonl` and `occurrences.jsonl`, the
  local rows E39's index is built from;
* before `caselist parse --publish` sends a per-source file.

Bytes another live path discloses are parsed and published as before; only the held disclosure's
occurrence rows go. `caselist status` names an earlier build's parsed file of held-only bytes left in
the bucket, by caselist, digest prefix and request, under `removals_owed` and outside the exit code.
The same removal run again deletes it with every version; the removal needed no change for that.
Look first at **Deviations 1 and 2**: this needed `debate_cli` (one wiring line, and the status
output), which the spec's packages did not list. **This merges after A11** of v1-e31-t20's
after-merge list, as your notes say: until the agent is reinstalled, an older build's
`parse --publish` still publishes such a file, and status is how that would show.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `held-parse`: Held uploads not parsed out | Done | Rule extracted (refactor committed alone), skeleton and red run, implementation, status and CLI, docs, 21 mutants, cross-build check. Its criterion passes: `13 passed` |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: a held upload's parsed file and aggregate rows are not published, by test shown failing first; bytes another live path holds still are | PASS | `test_caselist_parse_held_uploads.py`, 8 tests. **Red** at the skeleton (`ecf43ae`, which withheld nothing), over this file and ac2's together (7 and 3 tests then): 7 failed, 3 passed. Each failure was for its reason: the held source parsed (`assert 'dcb67b…' not in [... CountingParser.parsed]`); its rows in `index.jsonl`, `failures.jsonl` and `occurrences.jsonl`; its parsed file in the PUTs; the held R5 row kept; the R1 row spanning past the hold's date; its failure listed; status naming nothing. The 3 passing at red were the ones that must not withhold, or did not need to: the shared bytes' publish, status's negative case, and the removal re-run. **Green**: `test_a_held_uploads_source_is_not_parsed_and_is_in_no_aggregate`; `test_an_earlier_builds_parse_of_a_held_upload_leaves_every_aggregate` (an earlier run parsed it, then the hold arrives; also store totals agree with the rows); `test_a_held_uploads_cards_are_never_clustered_with_the_live_ones`; `test_publish_sends_nothing_of_an_earlier_builds_parse_of_a_held_upload` (moto: no PUT names the digest, the file is reported `suppressed`, the aggregates are published and none in the bucket holds it); `test_a_held_upload_that_failed_is_in_no_failure_listing`. **Second half**: `test_bytes_another_live_path_discloses_are_parsed_and_published` (`verbatim` held at R5, live at R1: parsed, indexed, its file PUT, nothing suppressed); `test_only_the_held_disclosures_occurrence_rows_go`; `test_a_path_live_before_the_hold_dates_from_keeps_only_its_earlier_rows`. Final: `uv run pytest <the three new files>` → `14 passed` |
| **ac2**: an earlier build's parsed object for held-only bytes is named by status, and the removal run again takes it, by test | PASS | `caselist/test_status_names_a_held_uploads_parsed_file.py`, in t22's revised-path world with the real `--source` removal: an older build imports and publishes `2026-10-08` with an upload at the held path, and its parsed file is put in the bucket twice. `test_status_names_an_earlier_builds_parsed_file_of_a_held_upload`: `held_parsed_objects == (HeldParsedObject('testcl26', <digest>, 'RM-2026-01'),)`, the request in `removals_owed`, `in_sync` still true, no name, path, `.zip` or `.docx` in it. `test_status_does_not_name_a_parsed_file_of_bytes_another_live_path_discloses` (`2026-10-10`, the same bytes at the other team's path). `test_running_the_removal_again_takes_the_held_uploads_parsed_file_with_every_version`: both versions and the local file gone, then status names nothing and owes nothing. Red at the skeleton: the first failed (`assert () == (HeldParsedObject(...),)`); the re-run test passed at red, because the removal already deleted it. The CLI: `packages/debate_cli/tests/commands/test_caselist_status_held_parsed_files.py`, red against the previous commit's CLI source (`git archive` on `PYTHONPATH`): 2 failed (no line; `KeyError: 'held_parsed_objects'`), 1 passed (the core's `removals_owed`); green 3 passed |
| Node `held-parse`: `uv run pytest packages/debate_core/tests/application -k "parse and (held or suppress)"` | PASS | `13 passed in 3.74s`: the 11 new core tests and t06's two suppression tests |

**Before the report** (working agreement 10):

| Check | Result |
|---|---|
| `uv run scripts/affected_tests.py --run` | **Left to the pull request's `ci` check, by the PM's ruling of 2026-10-19** (Operator follow-up 1). The affected set is 270 of 316 test files, 7,692 of the selection's 9,627 tests, about 5 minutes here, measured by `pytest --collect-only` over its list (5.8 s). The ruling: when the affected set would take longer than about two minutes, the session neither runs it nor hands it to the operator, and CI runs it on the pull request. A CI failure comes back to the session under agreement 10 |
| `uv run ruff format --check .` / `uv run ruff check .` | `886 files already formatted` / `All checks passed!` |
| `uv run pyright packages/debate_core packages/debate_cli` | `0 errors, 0 warnings, 0 informations` (10 s) |
| `uv run lint-imports` | `Contracts: 12 kept, 0 broken.` |
| `uv run scripts/validate_specs.py` | `OK: 394 files, 39 epics, 334 tasks, 21 releases` |
| `uv run python scripts/check_command_blocks.py` | `OK: no # comments in 280 shell code blocks in 124 Markdown files` |
| While working | publish plan, held rows, held path, held skipped rows, store sync, status held digests after the refactor: `120 passed`; parse, file recipes, parsed-store removal, pull, refused store, status, held, publish plan, store sync, withdrawn copies, mismatch kinds after the implementation: `347 passed`; CLI status and publish: `59 passed` |

### Mutation runs (21, agreement 8)

Each was applied by a script and run against the new tests and the parse, parsed-store-removal and
held-row suites, then restored from git; the tree was clean after each batch. All 21 are caught. Two
survived at first, and each showed a test that asked too little:

| # | Planted bug | Caught by |
|---|---|---|
| 1 | a held disclosure counts as live | `test_a_held_uploads_source_is_not_parsed…` |
| 2 | only held disclosures count as live | the same |
| 3 | the rule restated in the parse, a hold from its own date (`>=`) | `test_a_path_live_before_the_hold_dates_from…` |
| 4 | the rule restated as a bare `path_hold`, no camp or suppressed-first guard | t06's `test_a_camp_release_is_parsed_with_its_camp_and_no_disclosure`, which crashes on a camp release's snapshot name. No held-row case tells it apart: a suppressed row is already out by the time it is asked |
| 5 | `held_only_sources`: a live disclosure does not save the source | `test_bytes_another_live_path_discloses…` |
| 6 | named by the removed file, not the request | `test_status_names_an_earlier_builds…` |
| 7 | the plan parses a held-only source | `test_a_held_uploads_source_is_not_parsed…` |
| 8 | the index keeps a held-only source | `test_an_earlier_builds_parse…leaves_every_aggregate` |
| 9 | the failures file keeps one | `test_a_held_upload_that_failed…` |
| 10 | a held-only source's cards are clustered | **survived twice**: the fixture's held card shares a cluster with a live one, so no count moved. Caught after `test_a_held_uploads_cards_are_never_clustered_with_the_live_ones`, which records what clustering is handed |
| 11 | a held disclosure's occurrence span kept | `test_only_the_held_disclosures_occurrence_rows_go` |
| 12 | the failure listing's own check removed | **survived**: the test asked after a rebuild had already dropped the row. Caught once it asks between the hold's arrival and the next run |
| 13 | the publisher sends a held-only file | `test_publish_sends_nothing…` |
| 14 | the publisher reads the manifests only when nothing is held | the same |
| 15 | the publisher asks another caselist's manifests | the same |
| 16 | status checks only when nothing is held | `test_status_names_an_earlier_builds…` |
| 17 | status names every parsed file | the same |
| 18 | a held parsed file owes no removal | CLI `test_its_request_is_owed_and_the_command_still_succeeds` (the core test's world also has a held row, which owes the same request) |
| 19 | `source_digest_of_key` takes an aggregate for a source file | `test_status_names_an_earlier_builds…` |
| 20 | the CLI prints no line | CLI `test_the_table_names_it…` |
| 21 | the CLI hint does not name the kind | the same |

The first run of 10 and 12 reported "caught" on an error in `test_publish_plan.py` that has nothing
to do with them (Follow-up work 2); I dropped that file from the set and ran them again.

### The cross-build check

`packages/debate_core/tests/application/check_an_older_build_reads_this_builds_parsed_store.py`, run
by its path in two steps. In the first, this build parses the parse world's three weeks, a removal
made elsewhere holds `cardmirror`'s only path and one of `verbatim`'s three, and this build parses
again. The copy then holds aggregates without the held source or the held disclosure, and that
source's per-source file beside them. This build wrote `2026.10.18-docx-5: 6 sources, 4 cards,
5 occurrences; 1 held or suppressed`. In the second step, each older build's `debate_core` source
(`git archive <tag> packages/debate_core/src`) goes first on `PYTHONPATH`. Its store reads every file
record by record, its publisher publishes the directory to moto, and its parse runs over the copy:

| Reader | Read | Publish | Its parse |
|---|---|---|---|
| this build (`c657ae7f937d`), the control | 7 per-source files, 4 documents, 6 index, 3 failure and 5 occurrence rows | succeeded, uploaded 9, suppressed 1 | `2026.10.18-docx-5` again, 0 parsed, 6 sources, 5 occurrences |
| `v1.1.0-dev.56` (`4867084212a0`), the newest dev tag | the same | succeeded, uploaded 10, suppressed 0 | `2026.10.18-docx-5` again, 0 parsed, **7 sources, 7 occurrences** |
| `v1.1.0-dev.18` (`0268cf782cdc`), the agent's | the same | succeeded, uploaded 10, suppressed 0 | `2026.10.12-docx-3`, new, 7 parsed, 7 sources, 7 occurrences |

Both older builds read every file this build writes. As expected, neither knows the rule: each
publishes the held-only file, and dev.56, whose parser version is this build's, puts the held rows
back into the directory when it rebuilds it. This is the earlier-build state that status now names
and the re-run clears (Operator follow-up 2).

## Files changed

* `debate_core.application.caselist.publish_plan`: `stored_row_hold`, the hold on one stored row,
  extracted from `_holds_of_stored_rows` as a refactor committed alone (`d7ceb3c`); `held_rows` and
  `held_only_digests` ask it as before.
* `debate_core.application.caselist.parse_sources`: `live_disclosures`, moved here from
  `caselist_parse` and asking `stored_row_hold` too; `held_only_sources`, which `parsed_publish` and
  `status_service` ask.
* `debate_core.application.caselist_parse`: uses `live_disclosures` at every point it decided
  liveness (plan, index, failures file, occurrences, failure listing); docstrings.
* `debate_core.application.caselist.parsed_publish`: the required `evidence` argument, and the
  per-source check.
* `debate_core.application.caselist.status_service`: `HeldParsedObject`,
  `CaselistStatusReport.held_parsed_objects` and `held_parsed_objects_of`, in `removals_owed`.
* `debate_core.application.ports.parsed_store`: `source_digest_of_key`, the inverse of
  `source_object_key`.
* `debate_core.application.file_recipes`: its docstring named the moved helper and said holds never
  reach the occurrence table.
* `debate_cli` (Deviations 1, 2): `container.py` passes this machine's evidence to the publisher;
  `commands/caselist.py` prints *HELD UPLOADS PARSED IN THE BUCKET*, the `--json` key
  `held_parsed_objects`, and the kind in the removals-owed hint.
* Tests: the three new files and the cross-build check above; four existing tests pass `evidence` to
  the publisher.
* `docs/data/parsed-card-store.md`: what the aggregates and the publish leave out, and what status
  says.
* The task spec: `constraints.packages` gains `debate_cli` and its tests, with a comment.

## Deviations from the spec

1. **`debate_cli/container.py`, one line.** The publisher cannot ask which sources only a held path
   discloses without this machine's manifests. I made that a required argument, as the suppression
   list is, so the composition root must pass it. The spec's packages did not list `debate_cli`, so
   I added it to `constraints.packages` with a comment saying why. Amend or revert as you see fit.
2. **`debate_cli/commands/caselist.py`, `caselist status`'s output.** ac2's "named by status" is
   met by the comparison's report, but the command would only have shown the request in the
   removals-owed hint, with no line saying what. I added a caption line and a `--json` key in the
   shape t24 gave *REFUSED AT IMPORT AT A HELD PATH*. The hint's existing wordings are unchanged
   byte for byte, and no exit code changes.

## Decisions and assumptions

1. **The one rule.** Your model was t25's push asking `SnapshotPlan.withholding_rows`. A plan
   answers per digest per snapshot; the occurrence table needs an answer per disclosure, for a
   source held at one path and live at another in the same week. So the parse asks the function the
   plan itself asks for each row, `stored_row_hold`, which I made public. That is now the one place
   the rule is written: what the publisher withholds and what the parse leaves out cannot part ways.
   Mutants 3 and 4 restate it and are caught.
2. **Per caselist.** A source is held-only when no disclosure in *its own caselist's* weekly
   manifests is live. A parsed file states a caselist and a snapshot, so another caselist's live copy
   does not make publishing this caselist's file safe. `store sync`'s `held_back_digests` is
   machine-wide, because a blob belongs to no caselist; that difference is deliberate.
3. **Where the parse is stricter than `caselist publish`.** t22's rule counts a withdrawn row as
   unheld, so the raw bytes of a source held at one path and withdrawn at every other are still
   uploaded. The parse counts no withdrawn or held disclosure as live, so it leaves such a source out
   and holds its file back. Status names it, and the re-run removes it whole. I found no reason to
   copy the looser rule into a store whose rows are disclosures.
4. **Reported `suppressed`.** A held-only file counts under the existing `suppressed` outcome. A new
   `SourceResult` would change both publish commands' counts and JSON. `ParsePlan.suppressed` counts
   held-only sources too, with no new field, so `caselist parse`'s output is unchanged.
5. **When status looks.** Only when the list holds a path, and then it lists `parsed/<caselist>/`
   only for a caselist with a held-only source. It needs no flag, so `caselist pull`'s comparison
   runs it too, outside its verdict. It names one entry per source, whatever the number of version
   directories holding its file. The JSON's `objects` counts sources.
6. **No parser version bump, no re-parse**, `docx_parser` untouched, and no aggregate's format
   changed: only which rows are written.
7. **The removal needed nothing.** A held row is a later upload held at no other path, so the
   re-run already removed it whole with every `parsed/` object; the test shows it.

## Operator follow-ups

1. **The affected set: waived, nothing to run.** By the PM's ruling of 2026-10-19 the pull
   request's `ci` check runs it, because here it would take about 5 minutes. If `ci` fails, the
   failing part's output comes back to the session.
2. **After this merges, which is after A11**: the status check in each environment, from the removal
   runbook (steps 3 and 9). Where: a checkout of `dev` at or after the merge, set up as the runbook
   says. Expect no *HELD UPLOADS PARSED IN THE BUCKET* line, since neither environment has had a
   `--source` removal with a hold. A line means an earlier build published such a file, and the
   request it names is the removal to run again.

   ```bash
   DEBATE_ENV=dev uv run debate-research caselist status
   ```

   ```bash
   DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research caselist status
   ```

## Follow-up work

1. **The file-recipe resolver does not ask about holds** (`file_recipes.py`, the evidence-files
   epic). It asks the suppression list again because a list merged from another machine can stop a
   row before this machine's next rebuild. A hold merged the same way is not asked about until the
   rebuild. An occurrence row carries its disclosure digest and snapshot span, which is what
   `held_paths` is keyed by, so it could. Probably worth asking before E39 reads recipes.
2. **An order-dependent fixture error, before this task.** `uv run pytest -n 0
   packages/debate_core/tests/application/caselist/test_held_rows_publish_nothing.py
   packages/debate_core/tests/application/test_caselist_parse.py
   packages/debate_core/tests/application/caselist/test_publish_plan.py` gives 2 errors:
   `fixture 'imported_data_dir' not found` in `test_publish_plan.py`. Every file is on `dev`; the
   fixture is in `caselist/conftest.py`. It happens only when the command line interleaves
   `caselist/` with its parent. CI and `affected_tests.py` pass sorted paths, which never do that, so
   neither is affected. Someone running a hand-picked list can be, as my first mutation run was.
3. **The agent's reinstall (A12).** Until the agent runs a build with this task, its weekly
   `parse --publish` publishes a held upload's parsed file and, on `docx-5`, puts the held rows back
   (the cross-build table). With no hold in either environment this is latent; status is how it
   would show.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-19

**Notes:**

Accepted. Before the pull request the session records the waiver below and sets the phase
`Succeeded`, in its own section above this review. The pull request needs no `--partial`, and it
merges after A11 of v1-e31-t20's list.

**The affected-set run is waived; CI runs it** (Operator follow-up 1). Here the affected set is
270 of 316 files, about 80% of the suite. Handing it to the operator moves the bottleneck agreement
10 removed from the session to the person, while CI runs the whole selection on the pull request
anyway. The rule from now on, which the PM writes into agreement 10 in the next batch: when the
affected set would take longer than about two minutes, the session does not hand it to the operator.
It says so in the report and lets the pull request's `ci` check run it. A CI failure comes back to
the session as agreement 10 already says.

**The work itself:**

* **One rule, made public rather than copied.** `stored_row_hold` was extracted in a commit of its
  own, and the publisher, the parse and status all ask it. Mutants 3 and 4 restate it and are caught.
* **Per disclosure, not per digest,** because the occurrence table needs it (Decision 1). That is the
  right reading of my note, which pointed at the plan.
* **The local aggregates leave held rows out too,** so v1-e39-t02's index never sees them, as I asked.
* **Two survivors became better tests:** what clustering is handed, and the window between a hold's
  arrival and the next run.
* **The cross-build check shows the latent risk plainly:** an older build republishes a held file and,
  on `docx-5`, puts the rows back. Status now names that state, and the re-run clears it.

**Rulings:**

1. **Deviations 1 and 2 are accepted.** The publisher needs this machine's manifests, so wiring them
   as a required argument is right, and status without a line saying what is owed would only half
   name it. The spec's packages already carry the session's addition.
2. **Decisions 1 to 7 are accepted.** Decision 3, a parse stricter than `caselist publish` for a
   source withdrawn everywhere and held at one path, is right for a store whose rows are disclosures.
3. **Follow-up 1** (the file-recipe resolver does not ask about holds) goes to `v1-e33-t03` by PM
   amendment in the next batch: resolve through `stored_row_hold`, as it does through the suppression
   list.
4. **Follow-up 2** (an order-dependent conftest error with interleaved paths) goes on the deferred
   tooling list. CI and `affected_tests.py` sort their paths, so neither meets it.
5. **Follow-up 3** is why the agent reinstall (A12) matters; it is already on the list. The status
   runs after merge fold into A13's, one per environment.
