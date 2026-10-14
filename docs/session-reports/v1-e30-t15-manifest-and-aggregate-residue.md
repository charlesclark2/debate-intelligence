# Session report: v1-e30-t15-manifest-and-aggregate-residue

| | |
|---|---|
| Task | `v1-e30-t15-manifest-and-aggregate-residue` — caselist status reports manifest and aggregate versions older than a removal |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t15-manifest-and-aggregate-residue.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t15-manifest-and-aggregate-residue.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t15-manifest-and-aggregate-residue` |
| Session status | COMPLETE. The Goal is `Succeeded`. Read Deviations 1 and 2 first |

## Summary

`caselist status` now reports, per caselist, the versions of the parsed store's aggregates and of
the manifests a removal rewrote that are older than the latest completed removal that touched that
caselist, by key role and count. It names the removal by request id and completion time. It still
only lists: the one thing it reads is the removal log, the same way it already reads the suppression
list. Every criterion passes, and the full suite passes on the synced branch.

**Three things to look at first.**

1. **The model holds for aggregates and for the manifests a removal rewrote, and for no other
   manifest (Deviation 1).** The takedown's sweep of a caselist's other manifests reads each
   noncurrent version and deletes only the ones that name what was removed. A version that never
   named it stays, older than the removal, and holds nothing removed. A test shows the takedown
   doing this, and `caselist reimport-openev-metadata` leaves such a version by design. So the check
   counts manifest versions only for keys the removal rewrote.
2. **The removal log could not say which caselists a removal touched or which manifests it rewrote,
   and its lines may not change (Deviation 2).** `v1-e30-t13` pinned the log's lines to what every
   installed build writes, and its test failed when I added two fields. So a removal now writes a
   record of its own beside the log, `removal-scopes.jsonl`, as t13 put the path holds beside the
   list. The consequence: a removal made by an earlier build has no scope, and status names it as
   *not checked* for as long as its entry is the request's. Dev's one logged removal is such an
   entry.
3. **The runbook's instruction to clear residue is proven at command level for both kinds.** For
   an old manifest version alone, the dry run says *Nothing is left to remove*, and `--execute`
   clears it anyway, because the sweep runs only at execution. The runbook says so.

## The model, and its evidence (ac1)

**The PM's ruling:** a removal's purge leaves no manifest or aggregate version older than its
completion, so in a caselist the removal touched, any such version is residue.

**What the takedown does** (`removal_service.py`, `removal_plan.py`), and the test that shows each:

| Takedown step | Effect | Model | Test (`test_manifest_and_aggregate_residue.py`) |
|---|---|---|---|
| Rewrite each manifest that held the file, then purge every other version of that key | The rewrite is the key's only version | **Holds**, except for the rewrite itself, which is older than the completion. The rewrite is told apart by its version id | `test_a_manifest_it_rewrites_keeps_no_version_but_the_rewrite`: three versions before, one after |
| Delete every version of every aggregate, in every version directory: of every caselist for a file removed whole, of each caselist a copy is withdrawn from | No version of any aggregate is left | **Holds** | `test_it_deletes_every_version_of_every_aggregate_in_every_version_directory`: two versions × three aggregates × two version directories × two caselists, then none, and no delete marker |
| Sweep every caselist's *other* manifests: read each noncurrent version, delete those naming a removed file | A version naming nothing removed stays | **Does not hold** | `test_a_manifest_it_did_not_rewrite_keeps_a_version_that_never_named_the_file`: two versions before, two after |
| Write the log entry last; its `recorded_at` is this machine's clock | The completion time | Holds; the margin covers the clocks (Decision 2) | — |

The three behaviour tests passed before any code changed, as they should: they describe the
takedown as it is. The fourth ac1 test, that the removal records its scope, is new behaviour and
was shown failing first.

The fixture taught me something along the way. A file that a later weekly drops leaves a `REMOVED`
row at its path, with no digest. The removal drops that row too, so it rewrites every manifest of
that caselist. Which manifests a removal rewrote therefore cannot be read off the file's digest,
which is one more reason the scope records them. The tests remove a file that only the third
synthetic week holds, so one manifest is rewritten and the others are not.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `older-versions`: Manifest and aggregate residue reported | Done | Its criterion passes: `269 passed in 20.54s`. All four Goal criteria pass. |

## Acceptance criteria

Commit ids are those on the branch after `scripts/task sync`, onto `origin/dev` at `45cc548`
(v1-e31-t11 and the generated-files refresh came in, and the rebase was clean). The red runs
were made before the sync, at the commits now called `61898fe` and `d1e2dbc`, whose content the
rebase did not change. The branch is not on origin.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: the report states the model the check relies on, and a moto test shows the takedown behaviour that makes it true | PASS, for aggregates and rewritten manifests (Deviation 1) | The model and its evidence are above. `uv run --frozen pytest packages/debate_core/tests/application/caselist/test_manifest_and_aggregate_residue.py -k TestWhatTheTakedownLeaves` → 4 passed. At the red commit: 3 passed, and the scope test failed. |
| **ac2**: a noncurrent manifest version and a noncurrent aggregate version older than a completed removal are reported per caselist, by role and count, and versions written after it are not; shown failing first | PASS | **Red**, commit `61898fe`: `11 failed, 10 passed`. Each failure was the missing behaviour: `assert () == (OlderVersions(role='manifest', versions=1), …)`, `older_than` was `None`, and `removals_not_checked` was `()`. **Green**, commit `796ecdd`: `21 passed`, then 25 with the tests the mutation runs called for. The tests: `test_a_manifest_and_an_aggregate_version_older_than_the_removal_are_reported_by_role` (manifest 1, index.jsonl 1, occurrences.jsonl 1, across both version directories); `test_versions_written_after_the_removal_are_not_reported` (aggregates rebuilt and a manifest republished afterwards); the margin test; `test_the_removals_own_rewrite_is_never_residue_however_long_the_run_took`; `test_a_current_aggregate_the_removal_did_not_delete_is_counted`; `test_the_latest_removal_that_touched_the_caselist_is_the_one_compared_with`. Through the command: `test_a_manifest_and_an_aggregate_version_older_than_the_removal_fail_status_by_role_and_count` (exit 1, `REMOVAL_RESIDUE`, the JSON and the text, everyday profile only, bucket unchanged, the only objects read are under `manifests/_suppression/`). |
| **ac3**: a caselist no removal has touched reports nothing, whatever versions it has; a refused listing is reported as not checked, never as none | PASS | `test_a_caselist_no_removal_touched_reports_nothing_whatever_versions_it_has`: OpenEv, with an old noncurrent release-manifest version and three old aggregates, reports `CaselistResidue(caselist="openev", checked=True)` and the status is in sync. `test_a_refused_listing_is_not_checked_and_never_none[raw/ \| parsed/ \| manifests/]`: refusing any one of the three listings gives `checked=False`, `STORE_ACCESS_DENIED` and `None` counts. The `manifests/` case was red first. Also: `test_a_manifest_the_removal_did_not_rewrite_is_not_reported_for_versions_it_kept`, `test_the_suppression_records_old_versions_are_never_residue`, `test_a_parsed_file_of_a_source_is_no_aggregate`, and a removal from an earlier build named as not checked, in core and through the command. In the JSON an unchecked caselist has `older_versions: null`, which `test_a_refused_version_listing_says_not_checked_and_never_that_nothing_is_left` holds. |
| **ac4**: the clean line drops 'noncurrent manifest versions are not read', and the runbook's *What the report does not see* is rewritten to match | PASS | **Red**, commit `d1e2dbc`: `uv run --frozen pytest -n auto tests/smoke/test_caselist_remove_smoke.py` → `9 failed, 18 passed`, all on the rendering (missing JSON keys and text). In the two clearing tests the status after the re-run already exited 0. **Green**, commit `665c7e3`: `27 passed in 15.31s`. The clean line is now *No version of a removed file is left under raw/ or parsed/, and no manifest or aggregate version is older than a removal that touched its caselist (N caselist(s) checked).* and the test asserts the old phrase is gone. Runbook commit `df2ecc6`: a new subsection *Versions older than a removal* (what, how found, the margin, how to clear, the two cases that do not clear), and *What the report does not see* rewritten. Steps 6 and 7 and the confirmation step were updated to the new line. `uv run scripts/check_command_blocks.py --base origin/dev` → OK. `uv run scripts/check_links.py` → `OK: 1519 relative links and anchors`. |
| Node: `uv run pytest packages/debate_core/tests/application -k "removal or status or residue"` | PASS | `269 passed in 20.54s`, on the synced branch. |

### How LastModified is controlled in moto

Moto keeps each version's `last_modified` as a plain attribute of its `FakeKey`, and computes
`IsLatest` by ordering on it. It serves the last-stored version as the current one, though,
whatever its time. So `backdate()` sets the attribute and then re-sorts moto's own stored list for
the key by that time. Without the re-sort, a backdated version put on top of a published manifest
became the version `GetObject` served, and the snapshot read as drift. That was my first openev
test failure, and it was a fixture error. The removal's clock is fixed at 2026-09-30 18:00 UTC,
and moto stamps writes with the time the test runs, which is later. So every "after the removal"
version needs no backdating, and every "before" version is backdated explicitly. The `removed`
fixture backdates each rewrite to two minutes before the completion, where a real run writes it.

### Mutation runs

24 mutants, each one textual change to committed source. The driver refuses a dirty tree and a
target that does not occur exactly once, and runs under `perl -e 'alarm …'`. It restores the file
from a byte copy and checks its sha256 and `git diff --quiet`. Each run had a new, empty
`HYPOTHESIS_STORAGE_DIRECTORY`. None of these tests is a Hypothesis property, so that is only to
follow working agreement 8. No mutant failed at collection. Core mutants ran the new file and
t10's `test_removal_residue.py` (42 or 43 tests, 6 to 14 s each); command-level mutants ran the
smoke file (27 tests, about 12 s each). There were five batches of up to seven, none over 65 s.
The runs were made before the sync, which changed none of the files involved.

| # | Mutation | Result | Caught by (first failing test) |
|---|---|---|---|
| **The time comparison** | | | |
| T1 | `<` becomes `<=` | CAUGHT, 1 failed | `test_the_margin_reports_a_version_before_it_and_nothing_at_or_inside_it` |
| T2 | Older becomes newer | CAUGHT, 9 failed | the same |
| T3 | A version whose store states no time counts as older | **SURVIVED, then CAUGHT** after a test was added | `test_a_version_whose_store_states_no_time_is_not_counted` |
| **The margin** | | | |
| M1 | No margin | CAUGHT, 1 failed | the margin test |
| M2 | 14 minutes | CAUGHT, 1 failed | the margin test |
| M3 | Added, not subtracted | CAUGHT, 1 failed | the margin test |
| **The scope rules** | | | |
| S1 | Any file under a version directory is an aggregate | **SURVIVED, then CAUGHT** after a code change | `test_a_parsed_file_of_a_source_is_no_aggregate` |
| S2 | A delete marker counts as a version | CAUGHT, 1 failed | `test_a_delete_marker_is_not_a_version_and_what_it_hides_is` |
| S3 | Every manifest of the caselist, not only the rewritten ones | CAUGHT, 1 failed | `test_a_manifest_the_removal_did_not_rewrite_is_not_reported_for_versions_it_kept` |
| S4 | The removal's own rewrite counts | CAUGHT, 1 failed | `test_the_removals_own_rewrite_is_never_residue_however_long_the_run_took` |
| S5 | Manifests are not listed | CAUGHT, 2 failed | `test_a_refused_listing_is_not_checked_and_never_none[manifests/]` |
| S6 | The rewrite's version id is not recorded | CAUGHT, 2 failed | `test_beside_its_log_entry_it_records_the_caselists_it_touched_and_the_manifests_it_rewrote` |
| **The caselist match** | | | |
| C1 | Any completion applies to every caselist | CAUGHT, 1 failed | `test_a_caselist_no_removal_touched_reports_nothing_whatever_versions_it_has` |
| C2 | The scope records every caselist the sweep covered, not those that held the file | CAUGHT, 2 failed | the scope test |
| C7 | The earliest removal is compared with, not the latest | CAUGHT, 1 failed | `test_the_latest_removal_that_touched_the_caselist_is_the_one_compared_with` |
| **Which log entries count** | | | |
| C3 | Another environment's removals count | CAUGHT, 1 failed | `test_only_this_environments_removals_are_compared` |
| C4 | An incomplete run counts as a completion | CAUGHT, 1 failed | `test_an_incomplete_run_is_no_completion_and_a_later_completed_one_of_the_request_is` |
| C5 | A removal with no scope is not named | CAUGHT, 2 failed | `test_a_removal_an_old_build_made_has_no_scope_and_is_named_as_not_checked` |
| C6 | A scope joins an entry of another request | CAUGHT, 1 failed | `test_another_requests_scope_is_not_this_ones` |
| **The refusal path, and what is reported** | | | |
| F1 | A refused manifest listing reads as empty | CAUGHT, 1 failed | `test_a_refused_listing_is_not_checked_and_never_none[manifests/]` |
| F2 | The removals not checked are dropped from the report | CAUGHT, 2 failed | the old-build test |
| F3 | The JSON gives an unchecked caselist `older_versions: []` | CAUGHT, 1 failed | `test_a_refused_version_listing_says_not_checked_and_never_that_nothing_is_left` |
| F4 | The old clean line | CAUGHT, 1 failed | `test_status_after_a_complete_removal_says_it_checked_and_nothing_is_left` |
| F5 | The text does not name a removal not checked | CAUGHT, 1 failed | `test_a_removal_an_older_build_made_is_named_as_not_checked_and_never_as_none` |

Three notes on those results:

- **S1 was a check made redundant by a second one.** The report emitted only the four known
  roles, so the aggregate-name rule could be removed and nothing changed. I kept the rule, the
  real definition, and made the report order whatever roles were found instead of filtering them
  (`1cb5383`). The mutant then failed the per-source test.
- **T3** is a branch S3 never takes, since it always states a time. The test pins the decision that
  an undated version is not counted.
- **S2 and C7 are caught only by tests I wrote for them in advance.** I expected both mutants and
  added the tests before the runs (`ea37687`). I did not run them against the suite without those
  tests.

### Checks CI runs

On the synced branch, with this report uncommitted. A load average of 109 from another session
made one early run time out, so every command after that ran under `perl -e 'alarm …'`, with the
load checked first.

| Command | Result |
|---|---|
| `uv run --frozen pytest -n auto -m "not slow and not live" --part 1/4` | `1675 passed in 36.28s` |
| `… --part 2/4` | `1684 passed, 1 xfailed in 33.19s` |
| `… --part 3/4` | `1687 passed, 1 skipped, 1 warning in 30.58s`. The skip is the parser eval waiting on human corrections |
| `… --part 4/4` | `1685 passed, 1 xfailed in 35.68s`. Both xfails are `v1-e31-t12`'s labelled small-print cite line |
| `uv run --frozen pyright` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen ruff check .` / `ruff format --check .` | `All checks passed!` / `651 files already formatted`. The first run found one long docstring line, rewrapped in `ef9bda5` |
| `uv run --frozen lint-imports` | `Contracts: 12 kept, 0 broken.` |
| `uv run scripts/check_thin_handlers.py` | `OK: 21 CLI command and API route handlers within 25 statements` |
| `uv run scripts/docs_index.py --check-descriptions` | `All 34 indexed documents under docs/ have a description` |
| `uv run scripts/validate_specs.py` | `OK: 347 files, 38 epics, 289 tasks, 20 releases`, after the phase was set |

Altogether 6,731 passed, 1 skipped and 2 xfailed.

**An older build reads this build's records.** I exported `v0.1.0-dev.122`, the build the weekly
agent is reinstalled from today, with `git archive` into my scratchpad. I then ran its own code
over `written_by_this_build/` with `check_an_older_build_reads_this_builds_files.py`, as t13's
README describes. It placed the eight files, the scope file in both places among them. It read the
list (3 whole files and 2 disclosures suppressed), imported the next week (`SUPPRESSED 4`,
completed), published and found the status in sync, in 7 s. The installed agent and its data
directory were not touched.

## Files changed

- **`debate_core.application`**
  - `ports/evidence_versions.py`: `ObjectVersion.last_modified`.
  - `ports/suppression.py`: `RemovalScopeEntry`, `ManifestRewriteRecord`, `RemovalScopeLog`, and
    the record's file name. `RemovalLogEntry` is unchanged.
  - `caselist/suppression.py`: `RecordedRemovalLog` finds the scope record beside each copy and
    appends the scope before the log entry.
  - `caselist/removal_plan.py`: `RemovalPlan.touched_caselists`.
  - `caselist/removal_service.py`: records each rewrite's version id, and writes the scope.
  - `caselist/removal_residue.py`: `completed_removals`, the older-version count, the margin, and
    the docstring.
  - `caselist/status_service.py`: reads the log and the scopes, and gives `removals_not_checked`.
- **`debate_core.integrations.s3`**: `version_store.py` passes S3's `LastModified` through.
- **`debate_cli`**: `container.py` gives status both copies of the log. `commands/caselist.py`
  renders the new lines and JSON keys and the new clean line.
- **Tests**:
  - `test_manifest_and_aggregate_residue.py` (25, new), plus `RemovalWorld.removal_log()` in the
    conftest.
  - `test_caselist_remove_smoke.py`: 4 new tests, and t10's exact shapes extended by hand. Its
    README row.
  - t13's `test_suppression_list_is_read_by_every_build.py`, `stored_suppression_lists/README.md`
    and `written_by_this_build/` (Deviation 3).
- **Docs**: `docs/runbooks/caselist-removal.md`.

## Deviations from the spec

1. **The check is narrower than the PM's model for manifests.** The spec says any noncurrent
   manifest or aggregate version older than a removal that touched the caselist is residue. For
   manifests the takedown makes that true only of the keys it rewrote (ac1's table). Counting every
   manifest would report a version that holds nothing removed, which running the removal again
   would not delete, and status would fail until lifecycle expiry. So manifests count only for the
   keys the removal rewrote, and their own rewrite does not count. A version of another manifest
   that does name a removed row is not seen. Seeing it would mean a download, which the ruling
   forbids. The runbook says so. **The spec's description should be amended to this rule; that is
   yours to do.**
2. **A new append-only record, `removal-scopes.jsonl`, beside the removal log in both places.** The
   log names no caselist and no rewritten manifest, so "a removal that touched that caselist" and
   "the keys it rewrote" could not be read from the listing and the log alone. Adding them to the
   log line broke t13's guard: `test_an_older_build_validates_a_line_with_the_model_this_build_validates_it_with`
   and three others failed. I followed t13's precedent and did not loosen the guard. One scope line
   per execution holds a date, a request id, the environment, caselist slugs and manifest keys with
   version ids (a key is a caselist and a date, or a camp release's year and event). It holds no
   school, team code or path. It is joined to its log entry by environment, request id and
   `recorded_at`. **What it costs:** a removal made by an earlier build has no scope. It is named as
   *not checked*, and stays so for as long as its log entry is the request's. In dev that is the
   one logged removal, the synthetic exercise of 2026-10-01, made before the parsed store existed.
3. **t13's compatibility test and stored files changed, additively.** `written_by_this_build/` was
   regenerated with the README's own command and now holds `removal-scopes.jsonl` in both places.
   The test of what this build adds now expects two files (it was renamed to say so). The
   byte-for-byte test masks the version ids in the scope file only, because moto assigns them at
   random, and it asserts it masked exactly five. Every other file is compared as written, and the
   list and the log are still the older builds' files byte for byte. The README records the
   `v0.1.0-dev.122` run above.
4. **Aggregate versions count whether current or not.** The ruling says noncurrent. A current
   aggregate older than the removal is one the takedown should have deleted and did not, which is
   the same leftover. A manifest's current version is its rewrite, or something newer, so this
   changes nothing for manifests.
5. **The residue line names the removal**, by request id and completion time, besides roles and
   counts. Clearing it needs the request id. Neither identifies anyone.

## Decisions and assumptions

1. **Which removal log decides: both copies, as one, then this environment's entries only.** Status
   reads this machine's copy and the bucket's as a set union, exactly as it reads the suppression
   list, with the scopes beside each. It keeps only entries whose `environment` is `DEBATE_ENV`.
   That filter is what makes prod right: prod's status runs against the dev data directory (step 7),
   whose local copy holds dev's removals. A dev removal is no completion in prod, which may not have
   run it yet. *The alternative*, the bucket's copy alone, would also be right in prod. In dev it
   would miss a removal whose bucket append failed (`RemovalCompletedUnlogged`), which the local
   copy holds. Tested: a removal recorded only in the bucket's copy is compared; dev's removal under
   `environment="prod"` is not. A refused read of the log raises, as a refused read of the
   suppression list already does in the same command. It is not "not checked": both are the same
   GetObject on the same prefix.
2. **Clock skew: 15 minutes, subtracted from the completion.** S3 stamps a version with its own
   clock, and the log takes this machine's. S3 refuses a signed request whose time is more than 15
   minutes from its own (`RequestTimeTooSkewed`), and a removal ends by writing its log entry to the
   bucket. So at the completion this machine's clock was within 15 minutes of S3's, and nothing S3
   wrote after the completion can read as more than 15 minutes before it. The margin therefore never
   counts a later write. What it costs is a version written in the 15 minutes before the completion
   and missed by the removal, which is not counted either. That is a publish made during the
   removal, not a version from before it. *The alternatives:* no margin, which trusts NTP and turns
   a skewed clock into a false finding that cannot be cleared; or an hour, which hides more for no
   gain. Both sides are tested: 15 minutes and 1 second before is counted, exactly 15 minutes and
   14:59 before are not. The removal's own manifest rewrite is told apart by its version id, not
   its time, so a long run (20 minutes, tested) cannot make it residue.
3. **Scope.**
   - **`manifests/_suppression/` is out.** The suppression list, the removal log, the path holds and
     the scopes are appended to, and each append leaves a version. Those old versions hold sha256
     values and request ids, never a name. They are the record of what was asked, and
     `refuse_protected_versions` stops any removal deleting them. Nothing lists the prefix as a
     caselist's (a slug cannot be `_suppression`). A test backdates a version of the list and finds
     nothing.
   - **Every version directory.** An aggregate is `parsed/<caselist>/<version>/<name>`, whatever the
     version, so `2026.10.10-docx-2` now and `2026.10.12-docx-3` after the re-parse are both
     covered. The tests use both names. A per-source file and any other name under a version
     directory are not aggregates (S1).
   - **Only caselists a removal touched**: one that held a file it removed or withdrew, in a
     manifest it rewrote, an object it deleted under `raw/` or `parsed/`, or a record it deleted.
     This is narrower than what the takedown deletes, since a whole-file removal deletes every
     caselist's aggregates, but only a caselist that held the file can hold a row of it.
4. **What the operator does: the takedown's purge again, under the same request.** Name one sha256
   from the request's `removed_sha256` with `--source`, the same `--request` and `--reason`, dry run
   then `--execute`. The plan lists every aggregate, old versions with new, and the execution's
   sweep deletes manifest versions that name the file. Then rebuild the aggregates (step 5). Two
   tests prove it through the command, one for a manifest version and an index together, and one
   for a manifest version alone, where the dry run says *Nothing is left to remove*. Two cases this
   does not clear go to you (Follow-ups 1 and 2), and the runbook says to stop there rather than
   delete by hand.
5. **One completion per request.** It completes at the latest of its `COMPLETED` runs, and touched
   the caselists of every scope joined to any of its runs. That is what lets a re-run that found
   nothing left to name a caselist by still stand for the request. Rewritten manifests are taken
   only from `COMPLETED` runs. A stopped run's rewrite may never have been purged, and its completed
   re-run's sweep rightly keeps versions that name nothing. A request any of whose runs has no scope
   is not checked. Per caselist, the latest completed request that touched it is compared with.
6. **What counts, and what does not.**
   - Delete markers do not count: they hold nothing, and the version under one does count (S2).
   - A version whose store states no time does not count (T3).
   - A refused listing of any of the three prefixes makes the whole caselist not checked.
   - Status lists `manifests/<caselist>/` only for a caselist a completed removal touched, so
     nothing else's listing cost changed, and t10's prefix test is unchanged.
7. **Nothing was run against a real bucket, a real data directory or an operator profile.** The
   listing's cost on the real corpus is not measured. It adds one listing of the manifests prefix,
   and only for a caselist a removal touched.

## Operator follow-ups

None is required for the merge. Two read-only commands check what the environments hold. Both use
your profiles, so they are yours to run, and they need nothing from this branch's merge: this
worktree has the change. Each adds at most one manifest listing per touched caselist to the usual
status. The runtime has not been measured, but expect it to be close to t10's status.

**Dev.** Where: your Mac, in this task's worktree.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e30-t15-manifest-and-aggregate-residue
aws sso login --profile debate-dev-evidence
DEBATE_ENV=dev uv run debate-research caselist status
```

What success looks like: exit 0, and under the table the new clean line. Expect also *Manifest and
aggregate versions NOT CHECKED against RM-2026-90*: that is the 2026-10-01 exercise, the
register's only entry, logged by an earlier build, and it is the expected result, not a fault (Deviation 2). If any other request id
is named there, or a *REMOVAL RESIDUE* line appears, paste the lines under the table back. They
hold caselists, roles, counts, digest prefixes and request ids only. A residue line is cleared as
the runbook's new subsection says.

**Prod**, against the dev data directory as the runbook's step 7 says:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e30-t15-manifest-and-aggregate-residue
aws sso login --profile debate-prod-evidence
DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research caselist status
```

What success looks like: the same. Dev's RM-2026-90 is *not* named, since only prod's own removals
are compared. If prod has removals logged by an earlier build, each is named as not checked.

## Follow-up work

1. **A rewritten manifest's older version that names nothing removed cannot be cleared** (E30).
   A completed run purges every version but its rewrite, so this should not arise. If it did, the
   check reports it, and the re-run's sweep keeps it, because the sweep deletes only versions that
   name a removed file. The runbook says to stop and tell you. A takedown step that purges a
   rewritten key's older versions again on a re-run would close it.
2. **A request that only withdrew shared files cannot have its aggregate residue cleared** (E30).
   Its re-run resolves the team's paths from records and manifest rows that the first run deleted,
   so it plans no aggregates. The runbook says to stop and tell you.
3. **The dry run says *Nothing is left to remove* when the execution would sweep a manifest
   version** (E30). The plan reads current manifests only, with the everyday profile. The runbook
   now says to execute anyway, but a plan line saying the sweep will run would read better.
4. **Removals logged before this build stay *not checked* for good** (E30; your call). Dev's
   RM-2026-90 is harmless: synthetic, and before the parsed store existed. If prod has such
   entries, a way to give one a scope by hand, with a reason, would be a task of its own. It is an
   append-only record, so nothing would be rewritten.
5. **The status's real-bucket cost is unmeasured** (E30). The operator runs above will show it.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-14

**Notes:**

Accepted in full, with the phase `Succeeded`. I have amended ac1 in this branch to the rule you
found, as Deviation 1 asked.

**Deviation 1: my ruling's model was too broad, and you proved where.** The takedown's sweep keeps
a version of a manifest it did not rewrite if that version never named the removed file. My rule
would have reported those versions, and no re-run can clear them, so status would have failed
until lifecycle expiry. Counting only the keys the removal rewrote, and telling its own rewrite
apart by version id rather than by time, is the right rule. It was shown by three behaviour tests
that passed before any code changed, because they describe the takedown as it already is.

**Deviation 2: the scope record follows `v1-e30-t13`'s precedent, and the guard did its job.**
Adding fields to the removal log broke the older-build tests. You put the scope beside the log
instead of loosening the guard. A removal from an earlier build being reported as "not checked"
is the honest cost. It touches only dev's synthetic RM-2026-90, and prod has had no removal.

**The work itself:**

* **The margin argument (Decision 2) is the best reasoning in this task.** S3 refuses a request
  more than 15 minutes off its own clock. A removal ends by writing its log entry to the bucket. So
  15 minutes is the most the clocks can disagree, and it is not a guess. Both sides of it are
  tested.
* **Union of both log copies, filtered to this environment (Decision 1),** is what makes prod
  right when status runs against the dev data directory.
* **The clearing instruction is proven through the command for both kinds of residue.** That
  includes the case where the dry run says nothing is left and `--execute` still clears it, and the
  runbook says so.
* **The mutation run:** 24 of 24 caught. Two of them came only after a test or a code change,
  which is what a mutation run is for.
* **Running `v0.1.0-dev.122`'s own code over this build's records,** from an export, shows the
  build installed today reads everything this one writes.

**Rulings:**

* **Deviations 1 to 5:** accepted.
* **Decisions 1 to 7:** accepted.
* **Your follow-up 4, giving an old removal a scope by hand:** no task. The only such entry is a
  synthetic exercise from before the parsed store existed, and prod has no removals. Revisit if a
  real one ever shows as "not checked".

**Follow-up work, filed by the PM in the next spec batch:**

* **One E30 p3 task, "residue clearing gaps", for your 1, 2 and 3:**
  * a rewritten key's older version that names nothing removed;
  * a withdrawal-only request whose aggregate residue cannot be re-planned;
  * the dry run saying nothing is left when the sweep would act.
* **Your 5:** measured by the operator runs below.

**Operator follow-ups:** your two status runs, in dev and in prod against the dev data directory,
any time after this merges. They run from the main checkout once it is on `dev`.
