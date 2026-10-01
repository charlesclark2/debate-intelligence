# Session report: v1-e34-t07-suppressed-downloads

| | |
|---|---|
| Task | `v1-e34-t07-suppressed-downloads` — The sync does not re-download a file it has been told to remove |
| Spec | [`plan_specs/v1/e34-caselist-sync/t07-suppressed-downloads.yaml`](../../plan_specs/v1/e34-caselist-sync/t07-suppressed-downloads.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t07-suppressed-downloads` |
| Session status | COMPLETE |

## Summary

`caselist pull` no longer fetches an OpenEv camp file that a removal took out. A file whose every
member the removal suppression list stops is now decided `skipped_as_removed` before any request is
made. The run summary counts it (`openev_skipped_as_removed`), and the select stage's reason, which
the run log keeps, says "N OpenEv file(s) skipped as removed". Because the list is keyed by sha256
and the listing gives no digest, a small state file (`caselist-sync-openev-deliveries.json`)
remembers which digests each OpenEv id delivered. **It records no removal at all.** Whether an id is
removed is asked of the list (the union of the local and bucket copies) on every run, so
`unsuppress`, removals made on another machine and a lost record all come out right. The importer's
own refusal is unchanged and still stands alone (ac3).

**Read first:** "A camp file changed upstream" under Decisions, and the three findings under
Follow-up work. Two of them are questions for you: whether a removal covers a camp's re-upload of
the same file under a new id (held back by default here), and the fact that `v1-e34-t06`'s path
matching already treats *any* re-upload at the same path as imported, so revised camp files are
never fetched. The third is a measured regression from `v1-e30-t07`: with an expired SSO session,
the pull's import now fails.

**The reproduction found two kinds of waste, not one.** With the inbox copy gone, the removed file
was downloaded and refused. With the inbox copy still there (the normal state, since nothing clears
the inbox), it was imported from the inbox and refused on every run, and each such run reported
`openev 2026-policy` as imported and `nothing_new: false`. The skip covers both.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `reproduce` — Show the removed file being downloaded and refused | Done | Two tests against the code as it stood after `v1-e30-t07` (commit `69d21c1`), both red; output below under ac2. The removal is the real `CaselistRemovalService` against moto, not an imitation of it. |
| `skip` — Skip downloads the suppression list already covers | Done | `caselist_sync.py`: the new decisions, `OpenEvDeliveries`, `_judge_unrecorded`, the summary count and the select stage sentence. `CaselistSyncService` takes `suppression` as a required keyword argument with no default; the container passes the importers' own union list. 18 tests in `test_sync_skips_suppressed_downloads.py`, one end-to-end smoke check, one guard on the required argument. |
| `independence` — Prove the importer's refusal still stands alone | Done | Shown two ways: a permanent test that blinds the skip (empty list) while the importers read the real one, and the skip removed from the code, which brings back the fetch and the refusal (output under ac3). The skip is restored. |

## Acceptance criteria

Commands and results are from the final tree unless a row says otherwise.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — After a removal under the removal procedure, a pull over the same release downloads nothing for the file; no request reaches OpenCaselist; the run summary records skipped-as-removed rather than downloaded and refused | PASS | `test_a_removed_single_file_camp_release_is_skipped_as_removed[inbox-copy-gone, inbox-copy-kept]`: the fake source's fetch list stays `[512]` (the first pull only); decision `skipped_as_removed`; `openev_skipped_as_removed: 1` in the summary JSON; select reason contains "1 OpenEv file(s) skipped as removed"; `record_for_summary` (what `caselist runs` keeps) has `openev_downloaded 0` and the same sentence. End to end through the installed commands: `tests/smoke/test_caselist_pull.py::test_a_camp_file_removed_from_another_machine_is_not_requested_again`, pull → `caselist remove --source … --execute` → pull with this machine's copy of the list and the inbox copy deleted: respx counts **1** `/download` request before and after the second pull. The five cases you named: single file (above); zip with one member removed → `already_imported`, no fetch, with the inbox copy kept or gone; zip with every member removed → `skipped_as_removed`, kept or gone; unsuppress then pull → fetched again and stored (`blobs_stored 1`); removal only in the bucket's copy → `skipped_as_removed`. |
| **ac2** — Shown failing first: the same scenario issues the download and the importer refuses it, captured before the fix | PASS | Commit `69d21c1`, `uv run pytest packages/debate_core/tests/application/caselist/test_sync_skips_suppressed_downloads.py -n0` → `2 failed`. Inbox copy gone: `AssertionError: the removed file was fetched again: {'openev_fetches': [512, 512], 'decisions': ['download'], 'openev_downloaded': 1, 'blobs_stored': 0, 'release_classifications': {'SUPPRESSED': 1}, 'import_stage': "… reason='1 snapshot(s) imported, 0 new file(s) stored'"}`. Inbox copy kept: `{'openev_fetches': [512], 'decisions': ['already_in_inbox'], 'snapshots_imported': ('openev 2026-policy',), 'nothing_new': False, …}` → `assert ['already_in_inbox'] == ['skipped_as_removed']`. |
| **ac3** — With the sync's skip disabled, the file is downloaded and refused exactly as before | PASS | Permanent: `test_with_the_skip_blind_the_importer_still_refuses_the_removed_file`. The skip reads an empty list, the importers the real union: fetches `[512, 512]`, decision `download`, `blobs_stored 0`, `files_imported 0`, release manifest `{"SUPPRESSED": 1}`, no blob on disk. Literally: `_judge_unrecorded` short-circuited to `return None, None` and a scratch test run (not committed): `AC3 inbox_kept=False fetches: [512, 512] decision: {512: 'download'} … blobs_stored: 0 files_imported: 0 release classifications: {'SUPPRESSED': 1} blob on disk: False`, and `inbox_kept=True … decision: {512: 'already_in_inbox'} … blobs_stored: 0 … {'SUPPRESSED': 1} blob on disk: False` → `2 passed`. File restored with `git checkout`; the importer code is untouched by this task. |
| **ac4** — A removal in the list but absent from the sync's memory still results in no download; a memory entry with no corresponding suppression is reported, not trusted | PASS, as read in Deviation 1 | The record holds no removals, so every removal it can apply comes from the list, read each run. Record deleted, inbox copy present → `skipped_as_removed` (`test_a_removal_the_delivery_record_does_not_know_is_read_from_the_inbox_copy`). Removal only in the bucket's copy → skipped (above). A remembered id the list does not stop is fetched, with a `note`, a warning naming `OpenEv file 512`, and "1 fetched before and neither recorded nor suppressed now, so taken again (openev-512)" in the select reason (`test_a_remembered_id_the_list_does_not_suppress_is_reported_and_fetched_not_skipped`); after `unsuppress` the note says the suppression was lifted. **The case no design can close:** with neither the record nor the inbox copy, nothing on this machine knows the id's digest, so it is fetched once, refused, then skipped (`test_a_removal_nothing_on_this_machine_can_recognise_costs_one_download_and_no_more` pins this). |
| Node `reproduce` (custom): the wasted download shown before the fix | PASS | ac2 above. |
| Node `skip`: `uv run pytest packages/debate_core/tests -k "suppress and sync"` | PASS | `24 passed in 10.56s` (18 in the new module, the `CaselistSyncService` case of the required-argument guard, and 5 existing `…NeverSynced` tests the expression also selects). |
| Node `independence` (custom): the importer refuses with the skip removed; the skip restored | PASS | ac3 above. |
| Whole Python suite, CI's selection: `uv run pytest -m "not slow and not live" packages tests` | PASS | `3482 passed, 1 skipped in 56.82s`. The skip is the pre-existing parser eval waiting on human corrections. |
| `uv run pyright` / `uv run ruff check .` / `uv run ruff format --check .` / `uv run lint-imports` | PASS | `0 errors, 0 warnings, 0 informations` / `All checks passed!` / `448 files already formatted` / `Contracts: 10 kept, 0 broken.` |
| `uv run scripts/validate_specs.py` (after `set-phase … Succeeded`) | PASS | `OK: 296 files, 38 epics, 238 tasks, 20 releases` |

## Checks shown failing for their reason

Script in the session scratchpad (`mutate.py`): each mutation applied, its guarding tests run with
`-n0 -p no:cacheprovider` and **a fresh, empty `HYPOTHESIS_STORAGE_DIRECTORY` per run** (working
agreement 8; none of the guarding tests uses Hypothesis), then the file restored with
`git checkout`. Final run against `027d2ee`:

| Mutation | Result | Failing for its reason |
|---|---|---|
| The skip: `SKIPPED_AS_REMOVED` never returned | CAUGHT, 9 failed | `assert [512, 512] == [512]`, `[901, 901] == [901]`: the removed file is fetched again |
| Unsuppress handling: "mentioned by the list at all" instead of "suppressed now" | CAUGHT | `assert [512] == [512, 512]`: after `unsuppress` the file is never fetched again |
| The record trusted: an unaccounted remembered id skipped | CAUGHT, 3 failed | `assert [] == [512]` and the blinded-skip test's expected download does not happen |
| **Union read:** the container gives the pull's skip `local_suppression_list()` | CAUGHT (smoke) | `assert ['download'] == ['skipped_as_removed']` |
| A junk row counts as an imported download again | CAUGHT | zip with every member removed, inbox kept → `already_imported` |
| A re-upload at a removed file's path fetched | CAUGHT | `assert [512, 640] == [512]` |
| Unreadable list: a remembered id fetched on a guess | CAUGHT | decision `download` instead of `suppression_list_unreadable` |
| Unreadable list fails the selection | CAUGHT | `plan()` raises `StoreCredentialsExpired` |
| Inbox copy not read when the record is missing | CAUGHT | `already_in_inbox` instead of `skipped_as_removed` |
| Nothing recorded at import | CAUGHT, 11 failed | re-downloads (`[512, 512]`, `[901, 901]`); four tests also fail opening the absent record file |
| A partly removed release judged without the manifest's other rows | CAUGHT | `assert [901, 901] == [901]` (inbox copy gone) |
| The skip dropped from the select stage's reason | CAUGHT, 5 failed | reason lacks "skipped as removed" |
| The sync's `suppression` given a default | CAUGHT | `CaselistSyncService(suppression=...) has a default` |

**One survived at first, and it exposed an overlap.** In the first run, removing only the
`SKIPPED_AS_REMOVED` branch failed the tests on the *label* alone. The next check ("every member
recorded or suppressed → already imported") also matched a release whose members are *all*
suppressed, so the file was still not fetched. That would have labelled a fully removed file
"already imported" if the first branch ever broke. `027d2ee` requires at least one recorded member,
and the same mutation now brings back real downloads.

## Files changed

`git diff --stat 9e3ee71..HEAD`: 8 files.

- **`debate_core.application`**: `caselist_sync.py`. Three decisions (`skipped_as_removed`,
  `same_path_as_a_removed_file`, `suppression_list_unreadable`); `OpenEvDelivery` /
  `OpenEvDeliveries`; `_judge_unrecorded` and `_delivery_in_inbox`; a list read at most once per
  selection and only when a decision needs it; `_recorded_openev`'s docstring corrected (it
  described SUPPRESSED rows that no longer exist) and junk rows no longer counted as an imported
  download; a `note` on `OpenEvSelection`; `openev_skipped_as_removed` in the summary; the module
  docstring's new section "A camp file that was removed".
- **`debate_cli`** (outside `constraints.packages`, Deviation 2): `container.py`, one argument. The
  pull's skip gets the importers' own list.
- **Tests**: `packages/debate_core/tests/application/caselist/test_sync_skips_suppressed_downloads.py`
  (new, 18 tests); `test_import_paths_consult_suppression.py` (the sync added to the
  required-argument guard); `test_caselist_sync.py` (the builder passes the now-required list);
  `tests/smoke/test_caselist_pull.py` (the takedown profile in its AWS config, plus the end-to-end
  check).
- **`docs`**: `runbooks/caselist-scheduled-sync.md` (what the three decisions mean and what to do);
  `runbooks/caselist-removal.md` step 9 (the pull now skips a removed camp file; weekly archives are
  still fetched and filtered).

## Deviations from the spec

1. **ac4 is met by a memory that holds no removals, and one case cannot be met by any memory.** ac4
   is written for "a memory of removed OpenEv ids". I kept none: the record maps ids to the digests
   they delivered, which no removal or unsuppress changes, and the list is asked every run. So the
   record cannot disagree with the list, which is the forbidden item, by construction. The cost of
   that choice, and of the listing carrying no digest or size, is one case. An id this machine never
   imported, removed elsewhere, with no inbox copy, is fetched once; the importer refuses it and the
   next run skips it. A memory of removed ids would do no better, since it would have to learn the
   id the same way. Pinned by a test so it stays visible.
2. **Outside `constraints.packages`.** `debate_cli/container.py` (one line: without it the skip has
   no list to read) and `tests/smoke/test_caselist_pull.py` (the only place the union wiring can be
   tested, through the real composition root). No other package was needed to store the memory; it
   is a JSON file in the data directory beside the download ledger.
3. **Behaviour beyond the skip, each needed by a case you asked for.** (a) A junk row (`.DS_Store`)
   no longer makes its download count as imported. Without this, a zip whose every camp file was
   removed stayed `already_imported` while it sat in the inbox. (b) A release whose inbox copy is
   gone is `already_imported` when the record shows every member recorded or suppressed. Before
   this, any zip release whose inbox copy was deleted was downloaded again, removal or not. (c) Two
   decisions the spec does not name: `same_path_as_a_removed_file` (the policy default below) and
   `suppression_list_unreadable` (fail closed rather than fetch on a guess). (d) `note` and
   `openev_skipped_as_removed` were added to the summary JSON without bumping
   `RUN_SUMMARY_SCHEMA_VERSION`: both are additive and nothing reads summaries back.

4. **An expired AWS session reads this machine's copy of the list (after PM review; the PM
   authorised it).** The pull's list is now `LocalFallbackSuppressionList`: both copies, or this
   machine's copy alone when reading the bucket's raises `StoreCredentialsExpired` (the S3 adapter's
   error for credentials that are missing or expired). Every other failure still fails closed. It
   changes `v1-e30-t07`'s rule that a bucket-holding command reads the union, for the pull only, and
   lives in `debate_core.application.caselist.suppression` and `debate_cli/container.py`. The
   condition for revisiting it, the day a second machine imports, is in the class docstring and the
   container comment. See "Changes after PM review".

## Decisions and assumptions

- **A camp file changed upstream.** Read from the upstream source (`ashtarcommunications/caselist`
  at `fb2903e`, 2026-08-26), not inferred. The routes are `GET`/`POST /openev` and
  `DELETE /openev/{id}`, with no update route. `postFile` refuses a path that already exists
  ("File already exists"). The `openev` table's id is `AUTO_INCREMENT` and its `path` is `UNIQUE`.
  So OpenEv changes a file only by an admin deleting it (current year only) and someone uploading
  again: **a new id, normally at the same path.** The same id with new bytes can only happen out of
  band on the server, and nothing in the listing would show it: our listing has no size or date.
  The table's `updated_at` changes only when the row does, and no route touches the row. What the
  skip does:
  - *Same id:* skipped by id, so changed bytes under an id are never fetched while the old ones are
    suppressed. That is the default you asked for, and nothing could detect the change anyway.
  - *New id at a removed file's path:* `same_path_as_a_removed_file`, held back, logged as a
    warning with the id, and named in the select reason. **Question for the PM:** does a removal
    cover a camp's later upload of the same file? If it does, this default is the rule. If not,
    the decision should become a download, which the importer would store under its new sha256. The
    record keeps the path only as a SHA-256, so it holds no title.
- **One authority.** The record's only facts are the download digest, a path digest and member
  digests per id. Decisions come from the list via `SuppressionState.suppresses_source`, which is
  latest-entry-wins, so `unsuppress` is honoured. OpenEv imports honour only whole-source entries;
  a disclosure-scoped entry is about a team's copy and leaves camp files alone, as in the importer.
- **The pull's skip and its importers read the same list object.** Passing one variable in the
  container, rather than two lists that happen to agree, is what makes "neither relies on the
  other" (ac3) and "they cannot disagree" both true.
- **An unreadable list does not fail the selection.** The list is read lazily, at most once. If it
  cannot be read (expired SSO, a torn line), a remembered id or a re-upload is
  `suppression_list_unreadable`; a never-seen id is still fetched, because no possible answer
  depends on the list; a file in the inbox goes on to an import that fails with its own reason.
- **The record is written after each successful OpenEv import, never by a dry run.** An unreadable
  record is ignored with a warning; the worst outcome is one refused download per removed id.
- **Member digests include refused members.** They are what the id delivered, and the list decides
  what that means.

## Operator follow-ups

None. Nothing here needs credentials or runs longer than seconds. Once `v1-e34-t05` installs a build
with this change, the first scheduled run after any camp-file removal should show
`skipped_as_removed` in its `openev_selections`; the scheduled-sync runbook says so.

## Follow-up work

1. **Removed bytes stay in the inbox (`v1-e30-t07` / removal runbook).** `caselist remove` deletes
   the store's blobs, records and manifests, and the bucket's objects, but not `<inbox>/`. After a
   removal the inbox still holds the camp file (`openev-<id>-…`) and every weekly zip containing
   the removed disclosure. The skip never imports them again, but the bytes are on disk. Whether the
   policy's "deleted everywhere we store it" covers the inbox, and whether removal should purge it,
   is for you; I did not change the removal procedure. This change keeps working if it does: the
   record, not the inbox, carries the digests.
2. **With an expired SSO session the pull's import fails (`v1-e30-t07` wiring, `v1-e34-t02`'s
   promise).** Measured with a scratch test (not committed): the importers' union list reads the
   bucket's copy, the read raises `StoreCredentialsExpired`, and the run reports
   `import: failed — 0 imported; 1 refused: openev-512: no usable AWS credentials`,
   `succeeded: False`. The sync's docstring says the local stages need no AWS session; they have
   needed one since `v1-e30-t07`. Bytes are captured to the inbox and the next run imports them, so
   nothing is lost, but an expired session now fails the weekly run instead of pending its publish.
   Worth deciding before `v1-e34-t05` runs unattended.
3. **Revised camp files are never fetched (`v1-e34-t06` matching).** A re-upload arrives as a new id
   at the same path. The old row `openev-<old id>-…` names an id no longer listed, so `_held_openev_ids`
   matches it by path and the new id counts as `already_imported`. The revised bytes are never
   downloaded, whether or not anything was removed. Pinned, not changed, by
   `test_a_file_uploaded_again_where_nothing_was_removed_is_held_by_its_old_row_as_before`. It is
   the same question as the policy default above, from the other side.
4. **`caselist runs`' table shows no skipped count.** The record keeps it only in the select stage's
   reason, visible with `--json`. A column would mean a `SyncRunRecord` schema change (`debate_cli`
   and `sync_runs`), outside this task.

## Changes after PM review

Both requested changes are made. Commits `3cd23a5..56aa892` on top of `448f836`.

### An expired AWS session no longer fails the pull's import (required)

**Shown failing first** (`3cd23a5`, red against `448f836`). The scratch case is now
`tests/smoke/test_an_expired_session_still_imports_and_what_was_removed_here_stays_out`, through
the real commands and composition root. It pulls, runs `caselist remove --execute` on 512, lists 513
(512's bytes under another camp's path) and 514 (new), then makes every S3 call raise
`StoreCredentialsExpired`. Result: `import: failed — 0 imported; 2 refused: openev-513: no usable AWS
credentials … openev-514: no usable AWS credentials`, so `assert 'failed' == 'completed'`.

**The change.**
- `LocalFallbackSuppressionList` (`application/caselist/suppression.py`): `entries()` reads the
  union, and on `StoreCredentialsExpired` only, reads this machine's copy and records why
  (`fallbacks`, `local_only_reason`). `append()` never falls back.
- The container gives the pull this one object for both importers and the skip, so they fall back
  together. Publish and status keep the strict union.
- The run records it. The summary JSON has `suppression_list_local_copy_only` (the reason), and the
  select or import stage that fell back adds "this machine's copy of the suppression list alone was
  read: …". It is counted per stage, so a later run that reads no list reports nothing.
- The sync docstring's credentials section, line 131 on, says the local stages need no AWS session
  (true again) and now also says exactly how the list behaves when the session has expired. The
  revisit condition is in the class docstring and the container comment.

**Evidence, final tree.**

| Check | Result |
|---|---|
| Expired session, end to end (the reproduction, now green) | exit OK; import `completed`; 512 `skipped_as_removed`; 513 `download`, then refused (no row, `files_imported 1`); 514 imported (`blobs_stored 1`); publish `pending`; `suppression_list_local_copy_only` names `aws sso login`; the import reason carries the sentence |
| Access denied on the bucket's copy, end to end | import `failed`, exit non-zero, `blobs_stored 0`, no local-copy note |
| A torn line in the bucket's copy (written to moto), end to end | the same |
| Unit: missing or expired credentials | local entries, `fallbacks 1`, reason names the login |
| Unit: access denied, torn line | raise; `fallbacks 0` |
| Unit: append with an expired session | raises; nothing written locally |
| Run level: expired session | 512 skipped, 514 stored, summary and select and import reasons record it |
| Run level: a second run that reads no list | `suppression_list_local_copy_only` is `None` |

**Mutations** (`mutate_fallback.py` in the scratchpad; fresh `HYPOTHESIS_STORAGE_DIRECTORY` each run;
files restored byte for byte from a saved copy, and checked):

| Mutation | Result | Failing for its reason |
|---|---|---|
| **The fallback also covers access denial** | CAUGHT, 2 failed | unit: `DID NOT RAISE`; smoke: the pull exits OK where it must fail |
| **The fallback does not record itself** | CAUGHT, 4 failed | `assert 0 == 1`; `suppression_list_local_copy_only` is `None` |
| The fallback reads nothing instead of this machine's copy | CAUGHT, 3 failed | `assert [] == ['2b91…']`; 512 no longer skipped |
| An append falls back to one copy | CAUGHT | `DID NOT RAISE StoreCredentialsExpired` |
| The container does not wrap the pull's list | CAUGHT | import `failed`: no usable AWS credentials |

The original 13 mutations were re-run after the change: all CAUGHT.

**A mistake of mine, caught by the full suite.** I first ran these mutations before committing the
container change, and the script restored `container.py` with `git checkout`. That put the file
back to the previous *commit*, which deleted my uncommitted wrap. The script's "restored" check
compared the file with HEAD, so it passed. `0cac2b3` therefore went in without the container
change. CI's selection then failed the expired-session check, which passed in its own file only
because that run came before the mutations. The wrap is restored in `56aa892`, and the script now
refuses to start unless the files under mutation are committed, and restores them from a saved copy.
The mutation table above is from that corrected run.

### The removal runbook says what removal leaves in the inbox

`docs/runbooks/caselist-removal.md`:
- **Step 8** gains a manual step until `v1-e30-t09`. It says where each environment's inbox is,
  finds a removed camp file's `openev-<id>-…` copies by sha256, for single documents and for camp
  releases, and deletes them. I ran the block in zsh against a synthetic inbox: it named the removed
  document and a release holding one removed member, and left a kept file and an unrelated release
  alone. Weekly archives are left in place.
- **Step 10** records in the register entry that the weekly archives in the inbox still contain the
  removed files, pending `v1-e30-t09` (counts and codes only).

The scheduled-sync runbook explains `suppression_list_local_copy_only`, corrects what
`suppression_list_unreadable` now means (an expired session no longer causes it), and states the
same-path hold as your decision. The sync docstrings and the same-path test say the same. The pinned
re-upload test's docstring now says `v1-e34-t08` must invert it rather than delete it.

### Checks on the final tree (`56aa892`, report commit aside)

| Command | Result |
|---|---|
| `uv run pytest -m "not slow and not live" packages tests` | `3491 passed, 1 skipped in 56.93s` (the skip is the pre-existing parser eval) |
| `uv run pytest packages/debate_core/tests -k "suppress and sync"` | `30 passed in 11.19s` |
| `uv run pyright` | `0 errors, 0 warnings, 0 informations` |
| `uv run ruff check .` / `uv run ruff format --check .` | `All checks passed!` / `448 files already formatted` |
| `uv run lint-imports` | `Contracts: 10 kept, 0 broken.` |
| `uv run scripts/validate_specs.py` | `OK: 296 files, 38 epics, 238 tasks, 20 releases` |

Not pushed. Next, for the operator: `scripts/task sync v1-e34-t07-suppressed-downloads`, then
`scripts/task pr v1-e34-t07-suppressed-downloads`.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-01

**Notes:**

Accepted, phase `Succeeded`, with one required change and one runbook addition before the pull
request opens (the last two items below). I read the container change and the sync module's
docstring on the branch for the two claims that decide what happens next: the skip and the
importers do share one list object, and the docstring does still promise that the local stages need
no AWS session.

**Deviation 1 is better than the criterion it replaces.** ac4 was written for a memory of removed
ids, with a rule that the memory must never disagree with the list. You kept a memory that holds no
removals at all, only what each id delivered, which nothing about a removal or an unsuppress
changes. The forbidden disagreement is impossible by construction rather than guarded by a check. And
you named and pinned the one case no memory can close, which is honest about the design's limit.

**Reading the upstream source settled the changed-file question with facts.** No update route,
`UNIQUE` path, `AUTO_INCREMENT` id: a camp file changes only as a new id at the same path. That is
what made Follow-up 3 visible.

**The reproduction found a second waste nobody had described.** With the inbox copy kept, which is
the normal state, the removed file was re-imported and refused every run and the run reported
`nothing_new: false`. The fix covers both.

**The first-run survivor exposed a real overlap.** Removing the skip branch failed only on the
label, because the next rule also matched an all-suppressed release and would have called a removed
file "already imported". `027d2ee` requires a recorded member. That is mutation finding something a
reader would not.

**Deviations 2 and 3 are accepted.** One line in the container is the only way the union reaches
the skip, and passing the importers' own list object is what makes ac3 and "they cannot disagree"
both true. Junk rows no longer counting as an imported download, and a release with a deleted inbox
copy no longer being re-downloaded, are each needed by a case I asked for.

**On your policy question: the default stands.** A removal covers a camp's later upload at the same
path. A removal request is about the material, and a revised camp file normally still contains it;
holding it back costs at most a revision we never fetch, and `unsuppress` reverses it. Charlie owns
the data-use policy and may read it differently; if so, the decision becomes a download.

**Follow-ups 1 and 3 are filed as tasks.** Removed bytes left in the inbox are a gap in the policy's
"deleted everywhere we store it" and become `v1-e30-t09`. Revised camp files never being fetched is
a staleness defect in `v1-e34-t06`'s matching and becomes `v1-e34-t08`, which must keep your
removed-path hold. Neither gates `v1-e34-t05`. Follow-up 4, a skipped-count column in
`caselist runs`, is noted and not filed.

**Change 1 (required): an expired AWS session must not fail the pull's import.** This is your
Follow-up 2, and it decides whether `v1-e34-t05` is worth enabling. A weekly launchd run on the
coach's Mac will usually find the SSO session expired. `v1-e34-t02` built the run around exactly that:
local stages need no session, and publish pends. Since `v1-e30-t07` the importers read the union,
the union reads the bucket, and the import fails. So every unattended run would capture bytes and
import nothing, and the next one would fail the same way.

PM decision: when the bucket's copy cannot be read **because credentials are missing or expired**,
the pull's list falls back to this machine's local copy, and the run summary records that it did.
That is exactly as safe as `caselist import`, which reads only the local copy by design under
`v1-e30-t07` Deviation 7: on the one operator machine every command that writes the list writes both
copies, so the local copy is never behind the bucket's, and `publish`, which needs a session anyway,
still refuses suppressed sources from the union. Any other failure to read the bucket's copy (access
denied, a torn line, an append-only violation) still fails closed, as now. Revisit the fallback under
the same condition as Deviation 7: the day a second machine imports.

**Change 2: say in the removal runbook what removal leaves in the inbox.** Until `v1-e30-t09` lands,
add a manual step: delete the inbox copies of a removed camp file (`openev-<id>-…`), and record in the
register entry that weekly archives in the inbox still contain the removed files, pending that task.
