# Session report: v1-e30-t07-source-removal

| | |
|---|---|
| Task | `v1-e30-t07-source-removal` — Source removal and suppression list |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t07-source-removal.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t07-source-removal.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t07-source-removal` |
| Session status | COMPLETE |

## Summary

`debate-research caselist remove` and `caselist unsuppress` now exist, so the policy's 7-day promise
has a command behind it. The suppression list is an append-only JSONL kept on this machine and in
the bucket, merged as a set union, and its fields cannot hold a name.

**After the PM review, the first real-dev exercise found a defect moto cannot show** (see "After the
PM review: the real-dev exercise"). `--execute` stopped safely before deleting anything, because the
takedown profile cannot read a list that does not exist yet. That is fixed in `d26cb32` and
`e7406c4`, which the PM's verdict predates. The re-run on `9ede19e` then completed under real IAM,
and every number matched the moto rehearsal.

Consulting the list is structural rather than conventional. Every path that can store or publish
a source takes the list as a **required argument with no default**: the import pipeline, both
importers, the publisher, the status check, and `store sync`, which was a fourth unguarded write
path. The pipeline re-checks the list at the write itself, the manifest row renderer refuses a row
the list stops, and an architecture test fails if a module outside the pipeline writes caselist
records. Before this change the scheduled pull called both importers with no suppression at all, so
enabling `v1-e34-t05` would have reversed takedowns weekly. It can no longer do that.

The guarantee is proved by attacking it. After a removal, each of these brings nothing back:
re-importing every cumulative archive, importing next Monday's archive in order, the same bytes
renamed and filed by another team, the OpenEv import, publishing, `store sync` in either direction,
and a run cut short and re-run. The same holds for a shared file's withdrawn copy.

**Two of the spec's rules met reality** (Deviations 1 and 2). Both were decided mid-session by the
operator, Charlie, answering a question in this session's terminal, not by the PM; see the
provenance note under Deviations.
**Read first:** "Where the check sits", and the mutation table, where 29 of 30 deliberate breakages
are caught and the one survivor is explained.

## Where the check sits, and why there

You asked for the check at the point a blob or manifest row is stored. It is there:

| Write | Guard | What fails if someone opts out |
|---|---|---|
| A blob and its records, from any import | `SourceImportPipeline(blobs=…, suppression=…)`: required, no default. It is read once per run, and checked again in `_store`, the single place an import writes bytes and records (`SuppressedWriteRefused`) | pyright, at every call site, and a `TypeError` at runtime; `test_the_suppression_list_is_a_required_argument_with_no_default` |
| A record written by a module that bypasses the pipeline | `test_only_the_import_pipeline_writes_caselist_records`: an AST scan of every production module for `put_source`, `record_disclosure`, `record_camp_file` and `file_source` outside the pipeline and its two importers | That test, with a message saying what to do |
| A manifest row | `render_rows(rows, *, suppression, disclosure_scope)`: every manifest writer goes through it, and it refuses a row the list stops (`SuppressedRowRefused`) | pyright; `test_the_row_renderer_refuses_a_row_the_list_stops_whoever_built_it` |
| A source or manifest going to the bucket | `CaselistPublishService(…, suppression=…)`: a suppressed source is never uploaded, and a manifest still naming a suppressed row is **withheld** | pyright; publish and plan tests |
| `store sync`, either direction | `EvidenceSyncService(…, suppression=…)`: skips suppressed blobs, and anything under `manifests/_suppression/` | pyright; `TestTheSuppressionListIsNeverSynced` |

I did not put the check inside the SQLite repository. The `SUPPRESSED` count has to be decided
before the write, so it can be reported. The blob store is shared with article snapshots. And a
blob, its records and its manifest row are written by three different components. The pipeline is
the one place an import writes all three. Making it unconstructable without the list, plus the
scan for writes that bypass it, gives the "a fourth importer inherits it" property you asked for,
and the scan is the test you asked for in case that turned out not to be possible.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `suppression-list` — SuppressionList port and adapters | Done | Port and entry models in `application/ports/suppression.py`. Local `O_APPEND` file in `integrations/local/suppression_list.py`, under `<data_dir>/suppression/` and outside the synced `objects/` tree. Bucket copy over the object-store port, verifying every append kept every earlier byte. Union merge and an in-memory fake. |
| `importer-and-publisher-checks` — suppression checks in importers and publisher | Done | Required everywhere, as above. Suppressed members get no manifest row; the summary counts them. Junk rows that shadow a suppressed file are withheld too (Deviation 6). Status treats leftovers as drift. |
| `removal-planner` | Done | `RemovalPlanner`: resolves `--source` / `--team` from this machine's records **and** both copies of every manifest; finds shared holders; produces every record, rewritten manifest (exact text), local file, bucket object and version, and suppression entry. |
| `removal-executor` | Done | `CaselistRemovalService.execute`: suppress first; bucket objects and every version; rewritten bucket manifests with superseded versions purged; a sweep of noncurrent manifest versions; local files and manifests; **records last**; one log entry, `COMPLETED` or `INCOMPLETE`. |
| `unsuppress` — un-suppress and removal profile | Done | Un-suppress appends an entry and a log entry. A preflight proves the takedown profile can list, write and delete a probe version **before any change**. It lists versions first, so the everyday profile named by mistake writes nothing. |
| `cli-and-smoke` | Done | `caselist remove` / `caselist unsuppress` in `debate_cli/commands/caselist_remove.py`, plus `tests/smoke/test_caselist_remove_smoke.py` (6 checks), pyright and lint-imports. |

## Acceptance criteria

Commands and results below are from the final tree (`HEAD` after the last code commit).

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — Without `--execute` the plan prints sources, records, manifest rows, local and S3 objects with version counts and shared references, and changes nothing. With `--execute` against moto every listed object and version is gone and `caselist status` is clean | PASS | `test_removal_plan.py::test_a_dry_run_changes_nothing_anywhere` (data-dir bytes, bucket versions and DB records identical after two plans). `test_removal_service.py::test_every_listed_object_and_every_version_is_gone_and_status_is_clean`: a raw object given 2 versions and a manifest given 3; afterwards 0 versions per removed key, 1 per rewritten manifest, status `in_sync`. Smoke: dry run, then execute, then `caselist status` exit 0. Version counts are shown against moto. Under the real everyday profile they print as "not counted" (Deviation 2, your decision). |
| **ac2** — Re-importing snapshots that still contain the file reports SUPPRESSED, stores no blob and writes no row, for `import` and `import-openev`; `publish` never uploads a suppressed sha256 | PASS | `test_the_cumulative_archives_reimported_bring_back_nothing`: `SUPPRESSED` [2, 3, 4, 4] for 09-01, 09-08, 09-15, plus 09-15 re-arriving as 09-22. No blob, no record, no "Maple Grove" in any row, junk included. `test_the_openev_import_brings_back_none_of_it`; `test_a_publish_after_the_reimport_uploads_none_of_it`; `test_the_same_bytes_renamed_and_filed_by_another_team_are_still_refused`; smoke `…next_weeks_archive_does_not_bring_it_back` (`SUPPRESSED` 4, publish uploads none, status 0). |
| **ac3** — `--team` resolves across snapshots; shared sources are listed as shared; without `--include-shared` only this team's disclosures go and the blob stays; with it the blob goes | PASS | Hand-derived from the fixture tables (`test_removal_plan.py` docstring): 3 removed, 1 withdrawn (ZaLu plus a camp file hold it), 9 records, 15 rows per side. `test_the_records_go_last_and_only_the_teams`: ZaLu's disclosure and the camp file stay. `test_with_include_shared_the_shared_file_goes_for_everyone`: blob, records, `raw/openev` copy gone. `test_the_withdrawn_teams_copy_…_is_refused_and_the_other_teams_kept`. |
| **ac4** — Append-only JSONL of sha256, date, reason and request id, union-merged local/S3, readable through the port | PASS as amended (see note) | `test_suppression_list.py`, 31 passed: append-only (same inode, prefix kept, `O_APPEND`), every bucket version a prefix of the next, union merge, torn-line refusal, no free-text field, `isinstance(…, SuppressionList)`. As written, the timestamp field is named `recorded_at` not `removed_at` (an un-suppress entry is not a removal), and an entry may carry a `disclosure` digest. The digest is the amendment the operator approved in this session (not the PM), now in the spec's ac4. |
| **ac5** — One removal-log entry per execution (local and `manifests/_suppression/removal-log.jsonl`) with no names; prod refused without `--confirm-prod` | PASS | `test_one_log_entry_per_execution_in_both_copies_and_no_names`: 12 records, 30 rows (15 × 2 sides), bucket log equals local, no fixture school/team/tournament string in the list or the log. `test_a_run_cut_short_…`: an `INCOMPLETE` then a `COMPLETED` entry. Smoke `test_prod_is_refused_without_confirm_prod` → `CONFIRMATION_REQUIRED`, exit 1. |
| **ac6** — `--execute` uses `DEBATE_REMOVAL_PROFILE`, failing clearly with no partial deletes if it is unset or lacks delete rights; `unsuppress --execute` appends both entries, the next import stores the file again, and the list is never rewritten | PASS | `test_unsuppress_and_removal_profile.py`, 10 passed: unset; everyday profile; lists-but-cannot-delete; signed out. All refused with bucket evidence, data dir, records and list unchanged. Unsuppress, then re-import stores the file again. Smoke: unset → refused; profile missing from the AWS config → refused with nothing changed; unsuppress end to end. Moto does not enforce IAM, so refusals are simulated by the stores; the everyday profile's real denial of `ListObjectVersions` was confirmed read-only against dev (see Decisions). **Real IAM, 2026-10-01:** the first dev `--execute` passed the preflight under `debate-dev-evidence-removal`, then stopped before any delete on a 403 reading the not-yet-existing removal log. Nothing was deleted or appended anywhere. Fixed, with a test that reproduces the 403 (`TestTheFirstRemovalInABucketWithoutListBucket`). **The re-run on `9ede19e` completed under real IAM:** `DONE … 16 record(s), 3 local file(s), 7 bucket object version(s) deleted; 8 manifest(s) rewritten without 42 row(s)`, status clean, the next archive `SUPPRESSED 4`. I then verified the bucket read-only (see "After the PM review"). |
| Node `suppression-list`: `uv run pytest packages/debate_core/tests/application/caselist/test_suppression_list.py` | PASS | `31 passed in 5.38s` |
| Node `importer-and-publisher-checks`: `uv run pytest packages/debate_core/tests/application/caselist -k suppress` | PASS | `72 passed in 7.70s` |
| Node `removal-planner`: `uv run pytest packages/debate_core/tests/application/caselist/test_removal_plan.py` | PASS | `20 passed in 6.72s` |
| Node `removal-executor`: `uv run pytest packages/debate_core/tests/application/caselist/test_removal_service.py` | PASS | `20 passed` (16 at the verdict, 18 after the 403 fix, 20 after the PM addendum's change) |
| Node `unsuppress`: `uv run pytest packages/debate_core/tests/application/caselist -k "unsuppress or removal_profile"` | PASS | `13 passed in 6.63s` |
| Node `cli-and-smoke`: `uv run pytest tests/smoke/test_caselist_remove_smoke.py` | PASS | `7 passed` (6 at the verdict; the seventh is the PM addendum's CLI check) |
| Node `cli-and-smoke`: `uv run pyright packages/debate_core packages/debate_cli` | PASS | `0 errors, 0 warnings, 0 informations` |
| Node `cli-and-smoke`: `uv run lint-imports` | PASS | `Contracts: 10 kept, 0 broken.` |
| Whole Python suite, CI's selection (`pytest -m "not slow and not live" packages tests`) | PASS | `3335 passed, 1 skipped in 47.43s` after the PM addendum's changes (3330 at the verdict, 3332 after the 403 fix). The skip is the pre-existing parser eval waiting on human corrections. Also clean: `ruff check .`, `ruff format --check .`, full `pyright`, the merge-conflict hook. |
| `uv run scripts/validate_specs.py` | PASS | `OK: 292 files, 38 epics, 234 tasks, 20 releases` |

## Proving it by trying to defeat it

| Attack | Result | Test |
|---|---|---|
| Re-import all three cumulative archives (`--allow-out-of-order`) | `SUPPRESSED` 2/3/4; nothing of the team's in any blob, record or row | `test_the_cumulative_archives_reimported_bring_back_nothing` |
| Next Monday's archive, in order, still holding every removed file | `SUPPRESSED` 4 | same test; smoke check through the CLI |
| The removed bytes renamed and filed by a different team | `SUPPRESSED` 1, no blob | `test_the_same_bytes_renamed_and_filed_by_another_team_are_still_refused` |
| The OpenEv import of a camp file holding the removed bytes | `SUPPRESSED`, no source, no row | `test_the_openev_import_brings_back_none_of_it` |
| The withdrawn team's copy of a shared file, re-imported | That path `SUPPRESSED`; the other team's copy still recorded; blob kept | `test_the_withdrawn_teams_copy_…` |
| Finder `._` and Word `~$` junk that names the removed file | No row; still counted as skipped | `test_a_suppressed_file_is_counted_…_has_no_manifest_row`, `test_junk_that_shadows_a_removed_file_goes_even_when_its_team_stays` |
| Publish after the re-import | Uploads none of it; status clean | `test_a_publish_after_the_reimport_uploads_none_of_it` |
| A manifest written before the removal, published afterwards | Withheld, naming the digests | `test_a_suppressed_source_is_never_uploaded_and_a_manifest_naming_it_is_withheld` |
| `store sync` push or pull of a suppressed blob, or copying one list copy over the other | Skipped | `TestTheSuppressionListIsNeverSynced` (both directions) |
| A run cut short after two deletes | `INCOMPLETE` logged; already suppressed, so the in-between import is safe; the same command finishes it | `test_a_run_cut_short_is_logged_incomplete_and_the_same_command_finishes_it` |
| An older version of an untouched manifest still naming the file | Purged by the sweep, including on a re-run from an empty machine | `TestSupersededManifestVersions` |
| A removal made from another machine | The bucket's copy alone suppresses; the next write merges it here | `test_a_removal_made_on_another_machine_is_merged_into_this_ones_list` |

## Checks shown failing for their reason

Each mutation was applied, the guarding test run in CI's invocation (`pytest`, single test node),
and the file restored from git. Scripts are in the session scratchpad, not the repo.

| Mutation | Result |
|---|---|
| Importer's `suppression` given a default | CAUGHT (`1 failed`) |
| A new module calls `record_disclosure` directly | CAUGHT |
| Write-time re-check removed from the pipeline | CAUGHT |
| Row renderer's check removed | CAUGHT |
| Suppressed members written as manifest rows again | CAUGHT |
| Junk rows shadowing a suppressed file kept (import) | CAUGHT |
| Caselist importer ignores the disclosure scope | CAUGHT |
| OpenEv merge carries a suppressed recorded row forward | CAUGHT |
| Publisher uploads a manifest that names a suppressed row | CAUGHT |
| Publish plan ignores the list for sources | CAUGHT |
| Status ignores suppressed objects left in the bucket | CAUGHT |
| `store sync` copies the suppression list | CAUGHT (`2 failed`) |
| `store sync` pushes a suppressed blob | CAUGHT |
| Local copy opened without `O_APPEND` | CAUGHT, **after a fix**: it first *survived*, because the test counted lines and an offset-0 write happens to leave three. The test now asserts the exact lines. |
| Latest-entry-wins by file order instead of time | CAUGHT |
| Plan removes shared files without `--include-shared` | CAUGHT |
| Plan judges a withdrawn copy from local records only | CAUGHT. This was a real bug, found by `test_a_team_is_resolved_from_the_bucket_when_this_machine_has_nothing` and fixed. |
| Plan keeps junk that shadows a dropped file | CAUGHT, **after a fix**: it first survived, because only `--team` was tested and the team rule drops those rows anyway. Added the `--source` test. |
| Dry run fails instead of degrading when versions cannot be listed | CAUGHT |
| Sweep scoped to rewritten manifests only | CAUGHT, **after a fix**: it first survived, and it exposed a real gap. A re-run from a machine with no local copy rewrote nothing and so swept nothing. The sweep now covers every known caselist. |
| Suppression appended last instead of first | CAUGHT |
| **Local records deleted first instead of last** | **SURVIVED.** It is not equivalent in principle: records-last is defence in depth. A re-run also resolves from the request's own suppression entries and from both copies of the manifests, so no test I could write without disabling those makes it fail. Reported rather than tested around. |
| No preflight | CAUGHT (`2 failed`) |
| Superseded versions of rewritten manifests left | CAUGHT |
| Only the current version of a raw object deleted | CAUGHT |
| Sweep of noncurrent manifest versions skipped | CAUGHT |
| Guard on `manifests/_suppression/` removed | CAUGHT |
| Un-suppress written to the local copy only | CAUGHT |
| CLI prod guard removed | CAUGHT |
| CLI dry run executes | CAUGHT |

**Guarantees this change could have disarmed elsewhere.** `store sync` (handled). `caselist pull`'s
importers (now read both copies). The OpenEv download selection in `caselist_sync.py`, which used
SUPPRESSED rows to mean "already handled" (Follow-up work 1). The t05 publish and status tests,
whose expectations changed (Deviation 5). The runbook and the store guide (updated).

## Files changed

44 files (`git diff --stat b672241..HEAD`). The branch was rebased onto `dev` during the session,
after PRs #133 and #134; all commits listed are this task's.

- **`debate_core.application.ports`**: `suppression.py` (new: entries, state, `AppendOnlyRecord`,
  `SuppressionList`, `RemovalLog`), `evidence_versions.py` (new: `EvidenceVersionStore`),
  `caselist.py` (`delete_source`, `delete_disclosure`, `delete_camp_file`).
- **`debate_core.application.caselist`**: `suppression.py` (new: union merge, bucket copy),
  `removal_plan.py` and `removal_service.py` (new). Plus `pipeline.py`, `import_service.py`,
  `openev_import_service.py`, `manifest.py`, `openev_manifest.py`, `publish_plan.py`,
  `publish_service.py`, `status_service.py`, `evidence_listing.py`: the list is required, there are
  no suppressed rows, and residue counts as drift.
- **`debate_core.application`**: `evidence_sync.py` (consults the list, never syncs
  `_suppression/`); `settings.py` (`removal_profile` ← `DEBATE_REMOVAL_PROFILE`, unset everywhere).
- **`debate_core.integrations`**: `local/suppression_list.py`, `local/fs_version_store.py`,
  `s3/version_store.py` (new); `local/sqlite_caselist_repository.py` (deletes);
  `s3/__init__.py` (export).
- **`debate_core.testing.fakes`**: `InMemoryAppendOnlyRecord`, `empty_suppression_list()`, the fake
  repository's deletes.
- **`debate_cli`**: `commands/caselist_remove.py` (new), `commands/__init__.py` (registration),
  `container.py` (lists, removal service, takedown access built only on `--execute`).
- **Tests**: 5 new test modules and updates to 8, in `packages/debate_core/tests`;
  `packages/debate_cli/tests/test_app.py` (service list); `tests/smoke/test_caselist_remove_smoke.py`
  (new) and `tests/smoke/README.md`.
- **Docs**: `docs/runbooks/caselist-removal.md` (the real commands), `docs/guides/evidence-store-cli.md`
  (what sync skips).
- **Spec**: this task's `ac4` amended (Deviation 1); Goal set to `Succeeded`.

## Deviations from the spec

**Provenance of the two mid-session decisions.** I put Deviations 1 and 2 to the session as
questions with options. Charlie answered both in this session's terminal; neither went through the
PM conversation, and an earlier draft of this report wrongly said the PM had ruled. The PM has since
accepted both on their merits in the review below.

1. **Disclosure-scoped suppression entries (ac4 amended; the operator chose this option).** As written, ac3
   with sha256-only ac4 leaves a hole: without `--include-shared`, the team's copy of a shared file
   is still in every cumulative archive at the same path. The blob stays for the other holder, so
   the next import would record it as the team's disclosure again, every week. A `--team` withdrawal
   therefore appends one entry per withdrawn path, carrying `sha256(caselist + "/" + path)`, never
   the path. Reversing it needs the archive in hand, the same as reversing the file's own sha256.
2. **Version counts in the dry run (the operator chose "degrade and propose IAM").** `EvidenceOperator` has no
   `s3:ListBucketVersions`, which I confirmed read-only against dev. So the dry run cannot count
   versions with only the everyday profile, and it prints "Versions not counted". `--execute` lists
   and deletes every version under the takedown profile. A one-statement grant is proposed below; the
   code needs no change once it lands.
3. **`--execute` needs both profiles signed in.** `EvidenceRemoval` may write only under
   `manifests/_suppression/`, so rewritten manifests are written with the everyday profile and their
   superseded versions purged with the takedown profile. No IAM change was needed for this; the
   runbook says so.
4. **CLI flags and paths.** `--request` (required for `remove`, optional for `unsuppress`) is not in
   the node's flag list, but ac4 and ac5 need a request id. `--reason` is taken as text and checked
   against the command's own codes, so `remove` doesn't offer the reinstatement reasons.
   `unsuppress --execute` also needs `DEBATE_REMOVAL_PROFILE`, plus `--confirm-prod` in prod. Both
   commands refuse `test` (no bucket). The commands live in `commands/caselist_remove.py`, beside
   `caselist_cards.py` and `caselist_pull.py`, not in the spec's listed `commands/caselist.py`. The
   timestamp field is `recorded_at` (ac4 says `removed_at`).
5. **Behaviour of finished tasks changed (t03, t04, t05).** Suppressed members no longer get a
   manifest row; ac2 requires that, and a row would put the requester's path, school and team code
   back. The OpenEv summary counts `SUPPRESSED` from the latest import, since there are no rows to
   count from. A manifest that still names a suppressed row is **withheld** by `publish`, where t05's
   test had expected it published. `status` reports such rows, and suppressed objects left in the
   bucket, as drift; t05 had counted them as fine. The t03, t04 and t05 test changes are in
   `test_import_service.py`, `test_openev_import.py`, `test_publish_service.py`,
   `test_status_service.py` and `test_publish_plan.py`.
6. **Junk rows withheld.** A skipped member has no digest but its path can name the removed file and
   team: `__MACOSX/…/._<name>` and Word's `~$` lock file. Its row is withheld when it shadows a
   suppressed file, or when every real file in its directory is suppressed. Without this, a removed
   team's directory reappeared in every week's manifest through junk alone; my own test found it.
7. **Imports read only this machine's copy of the list.** The spec says the list is merged "on every
   run". `caselist import` is offline by design: its smoke test runs in `dev` with no bucket access
   and asserts nothing new appears in the data directory. So it reads the local copy. Every command
   that already holds the bucket reads the union: publish, status, sync, pull and remove. Every
   command that writes the list writes both copies, so on the machine that made a removal the local
   copy is never behind the bucket's. A second machine is covered by `publish` refusing suppressed
   sources from the union. If you want imports to read the bucket too, it is one line in
   `container.py`, but it makes `caselist import` need an SSO session.
8. **`store sync` consults the list.** The spec names three call sites. `store sync` is a fourth path
   that can put a removed blob back in the bucket, and could truncate the bucket's copy of the list.
   The forbidden list ("rewriting or truncating the suppression list") required covering it.
9. **Execution order.** The node says the executor deletes "then appends to the suppression list".
   It appends first, so a run that stops part-way still keeps next week's import out.
10. **Outside `constraints.packages`.** `debate_core.testing` (fakes the port contract needs),
    `docs/runbooks/caselist-removal.md` and `docs/guides/evidence-store-cli.md` (operators follow
    them for this command), `tests/smoke/README.md`, `packages/debate_cli/tests/test_app.py`. The
    policy links to the runbook's old section anchor; I kept the anchor rather than edit an approved
    policy.

## Decisions and assumptions

- **Entries hold nothing a name can go in.** Every field is a digest, a UTC timestamp, an enumerated
  reason code, or a request id matching `^RM-[0-9]{4}-[0-9]{2,4}$`. The models forbid extra keys.
  Reasons are the runbook's six codes plus `REMOVED_IN_ERROR` and `REQUEST_WITHDRAWN` for
  un-suppress. Log entries carry codes, counts and digests; an `INCOMPLETE` one carries an error
  *code* (`STORE_UNAVAILABLE`), never a message.
- **"Latest entry wins" is by `recorded_at`, not file position.** The two copies may hold the same
  lines in different orders. Ties break on the canonical line, so un-suppress wins over suppress at
  the same instant. One un-suppress lifts every scope of that sha256.
- **The append-only record is enforced by the adapters.** Locally: `O_APPEND`, no truncating flag,
  `0600`, a torn last line refused rather than repaired. In the bucket: read, append, write, then
  read back and check the old bytes are a prefix of the new. The bucket keeps every version, and
  nothing ever deletes under `manifests/_suppression/` except the preflight probe.
- **Rewritten manifests.** Kept rows are byte-for-byte originals. In a caselist summary, `members`
  and `skipped` stay the same (facts about the archive); each dropped member's classification moves
  to `SUPPRESSED`; `distinct_sha256` is recounted. The OpenEv summary is recounted the way the
  importer counts it. After a removal, local and bucket copies are byte-identical, which is why
  `status` is clean.
- **Preflight.** It lists versions, writes `manifests/_suppression/preflight/<uuid>.txt`, lists it,
  deletes every version, and checks none is left. Proving delete rights needs a real delete, as the
  evidence-store runbook's probe does. Listing comes first, so the everyday profile writes nothing.
- **A refused run logs nothing.** Nothing was done; the error says why.
- **The sweep covers every known caselist** whenever anything is removed or withdrawn. It reads only
  noncurrent manifest versions (one per re-published week at most).
- **The local parsed store (E31 t06) isn't built yet.** Removal deletes any file under
  `<data_dir>/parsed/<caselist>/` or `parsed/<caselist>/` in the bucket whose name is the digest,
  with or without an extension, matching `docs/architecture/evidence-store-layout.md`.
- **Real-environment check, read-only.** `DEBATE_ENV=dev debate-research --json caselist remove
  --source 000…0 --request RM-2026-99 --reason POLICY` ran against the real dev bucket in 6.5 s:
  `status ok`, `applied false`, `versions_counted false` (the real IAM denial), 0 manifests, 0
  objects, 1 entry planned. Nothing was written. A digest held nowhere is planned as a suppression
  only, which is the runbook's "hashes recorded before this command existed" backfill, and the dry
  run says so.

## After the PM review: the real-dev exercise

Charlie ran Operator follow-up 1 against the real dev bucket on 2026-10-01, after the PM's verdict.

**What happened.** The imports, the publish (14 sources, 3 manifests), the dry run and both `status`
runs behaved as expected. The dry run showed 3 removed, 1 shared and kept, 6 manifest rewrites, 5
suppression entries and "Versions not counted". `--execute` then stopped with:

```
STORE_ACCESS_DENIED: not allowed to HeadObject s3://debate-dev-evidence-a7508de8/manifests/_suppression/removal-log.jsonl
```

Nothing was deleted and nothing was appended. I checked read-only afterwards:
- The final `raw/caselist/testcl26/` version count was 14, so every source was still there.
- There was no object or version of any kind under `manifests/_suppression/`, and the probe was gone.
- The 09-22 re-import reported `SUPPRESSED 0`, since no entry had been written anywhere. Status was clean.

The "no partial deletes" half of ac6 held under real IAM. The rest of the exercise didn't happen.

**Why.** S3 answers a read of a key that does not exist with 404 only when the caller has
`s3:ListBucket`. Without it, S3 answers 403, because it will not say whether a key it will not list
exists. `EvidenceRemoval` has no `s3:ListBucket`, by design. Before appending, my code read the
bucket's copy of the suppression list, then the removal log, with the takedown profile. In an
environment that has never had a removal, neither exists yet. Moto answers 404 whatever the
credential, so no test could have seen this. I confirmed it read-only with `head-object` on the
missing log: `debate-dev-evidence-removal` gets `403 Forbidden`, and `debate-dev-evidence` gets
`404 Not Found`.

**Did the real grants match `operator_access.tf`?** Yes, in everything the run exercised, and
nothing contradicted the file. The preflight passed under `debate-dev-evidence-removal`, so these
are now observed for real:
- `s3:ListBucketVersions` under `manifests/` (`ListEvidenceObjectVersionsForTakedown`);
- `s3:PutObject` under `manifests/_suppression/`, with the KMS data key (`MaintainSuppressionList`,
  `UseEvidenceKeyForTakedown`);
- `s3:DeleteObjectVersion` and the check that nothing is left (`DeleteDisclosedMaterialOnRequest`).

The 403 is the file's own design: no `s3:ListBucket` for the takedown profile. Earlier I had
confirmed read-only that it is refused `ListObjectsV2`, and that the everyday profile is refused
`ListObjectVersions`. Deleting versions under `raw/` was still unobserved at this point. The re-run below observed it.

**The fix** (`d26cb32`):
- **Reads move to the everyday profile.** The bucket's copies of the list and the log are now read
  with the everyday profile, which can list and so gets an honest 404. The takedown profile still
  writes them, so the `MaintainSuppressionList` grant and CloudTrail's record of who appended are
  unchanged. `ObjectStoreAppendOnlyRecord` takes an optional `reader` for this. `--execute` already
  needed both profiles signed in (Deviation 3), so the operator does nothing new. No IAM change was
  needed.

The same read exposed two defects in how a stopped run reports itself, both also fixed:
- **A false message.** `RemovalIncomplete` always said "Every suppression entry was appended
  first". When the append is the step that failed, that is false. It now says nothing was deleted
  and that the entries may be on some copies of the list but not all.
- **A hidden failure.** When the log append also failed, its error replaced the run's own. The real
  run reported the log, when the first failure was the suppression list. The run's failure is now
  the one raised, and the log's is added to its message.

**Shown failing first.** Moto can't model the 403, so the new
`TestTheFirstRemovalInABucketWithoutListBucket` wraps the takedown store in one that answers a
missing key with `StoreAccessDenied`, as real S3 does. Before the fix, both its tests failed with
the same message the dev run printed. Then I broke each part of the fix in turn:

| Mutation | Caught by |
|---|---|
| Reads go back to the takedown store (`reader` dropped) | both new tests |
| `suppressed` set before the append | `…an_append_that_fails_says_nothing_was_deleted…` |
| The log's failure raised over the run's | the same |
| The log's failure left out of the message | the same |
| `suppressed` never set | **survived at first**: no test checked a run cut short *after* suppressing. `e7406c4` adds that check to `test_a_run_cut_short_…`, and it now fails |

**Before handing back the re-run**, I rehearsed it against moto through the installed command.
First a machine in the state the first exercise left the bucket in, then a fresh scratch store.
That gave the expected values in Operator follow-up 1.

**The re-run (`9ede19e`, 2026-10-01).** Charlie ran Operator follow-up 1 again from a fresh scratch
store. Every printed number matched the moto rehearsal:
- the four imports reported `NEW` 4, 7, 2, 0;
- the publish uploaded 0 sources across 4 of 4 snapshots, and `status` agreed;
- the dry run showed 3 removed, 1 shared and kept, 8 manifest rewrites (4 weeks × 2 sides) and 5
  suppression entries, with "Versions not counted";
- `--execute` printed `DONE in dev (debate-dev-evidence-a7508de8): 16 record(s), 3 local file(s),
  7 bucket object version(s) deleted; 8 manifest(s) rewritten without 42 row(s).`;
- `status` agreed, with 2/10/10/10 files per week;
- the 09-29 import reported `UNCHANGED 10` and `SUPPRESSED 4`, and its publish uploaded 0 sources;
- the final `status` agreed, the raw version count was `11`, and both records were listed.

Afterwards I checked the bucket read-only, removal profile for listing, everyday profile for
reading:
- **The three removed files:** under `raw/caselist/testcl26/`, each has 0 versions and 0 delete
  markers.
- **The shared file** `eea75cc2…` is still in the bucket, kept for the other team.
- **Each of the five `manifests/testcl26/` keys has exactly one version**, and there are no delete
  markers. I downloaded every version: none names a removed sha256 or the team ("Maple Grove").
- **Each record has exactly one version**, so neither was ever rewritten.
  `manifests/_suppression/suppression-list.jsonl` holds 5 lines, and `removal-log.jsonl` holds 1
  `COMPLETED` entry. That entry records 16 records, 42 rows, 8 manifests, 7 S3 versions, 3 removed
  and 1 withdrawn sha256.
- **No names in either record.** A case-insensitive search of both files for every fixture
  school, team code and tournament, and for `.docx`, finds nothing.

**Do the real grants match `operator_access.tf`? Yes.** This run used each `EvidenceRemoval`
statement for real, and nothing it was refused or allowed departed from the file:
- `ListEvidenceObjectVersionsForTakedown` listed versions under `raw/` and `manifests/`;
- `DeleteDisclosedMaterialOnRequest` deleted every version under `raw/` and the superseded
  `manifests/` versions;
- `MaintainSuppressionList` and `UseEvidenceKeyForTakedown` wrote both records.

The absence of `s3:ListBucket` showed up as the file intends: a 403 for a missing key. The code
now accounts for that, which closes ac6's real-IAM gap.

Two grants this run did not test:
- **`GetObjectVersion` under the takedown profile:** this run had no older manifest version to
  read, because none existed before it.
- **Whether the removal profile could delete from `reports/`:** IAM is meant to refuse that, and
  nothing here asked it to.

**For the PM.** The verdict above was given on `b4fe956`. These two commits change
`removal_service.py` and `suppression.py` after it, so the PR should not open on that verdict
without a look at them.

## The PM addendum's changes

The addendum (`bd8f610`) asked for two changes before the pull request.

**1. A removal that completed but could not be logged now says it completed** (`ec2f306`).
Before, when every step succeeded and the removal-log append then failed, `execute` re-raised the
bare store error. Through the CLI that was `INTERNAL_ERROR`, "This is a bug in debate-research",
exit 70, with nothing saying the removal had happened.

It now raises `RemovalCompletedUnlogged`, a distinct `DomainError` and not `RemovalIncomplete`. Its
CLI code is `REMOVAL_COMPLETED_UNLOGGED`, with exit 1. The message:
- says the removal completed;
- gives the report's counts: records, local files, bucket object versions, manifests rewritten and
  rows;
- names each copy of the log that lacks the entry.

The counts are also scalar fields in the `--json` error details. Neither the message nor the hint
says the removal failed or stopped part-way.

**What a re-run would log.** I checked this. A re-run finds nothing left to remove and logs a
`COMPLETED` entry with zero counts, as `test_running_it_again_after_it_finished_finds_nothing_left`
asserts. So it cannot reproduce the counts, and the message always says to record them in the
register from this output.

Which copy holds the entry depends on where the write failed:
- **If the bucket's write failed,** this machine's copy, written first, holds the entry. The message
  names it, and adds that the next removal-log write copies it across, because every append writes
  each copy the union's lines it lacks.
- **If this machine's write failed,** no copy has the entry, and the message says so.

**Shown failing first.** Two service tests make a log copy refuse the append after the deletes
succeed: the bucket's copy (`StoreUnavailable` on `PutObject`), and this machine's (`OSError`). A
CLI smoke test makes the local log file read-only. Before the fix, all three failed on the bare
error, and the smoke test printed `INTERNAL_ERROR … exit 70`. Then I broke the fix:

| Mutation | Result |
|---|---|
| The bare re-raise restored (`if failure is None: raise`) | caught by all three new tests |
| Every copy reported as missing the entry | caught (bucket-copy test) |
| Every copy reported as holding it | caught (both service tests) |

**2. The register is opened.** `docs/data/caselist-removal-requests.md` follows the runbook's step 1
fields and step 10 outcome. Its one entry, `RM-2026-90`, is the 2026-10-01 dev exercise on
synthetic data, with the `COMPLETED` counts from the `9ede19e` re-run. It notes the earlier attempt
that changed nothing, and that the entries are permanent. It contains no school, team code,
filename or name; a search for every fixture name finds none. I added one convention: ids from
`RM-<year>-90` up are for exercises, so an exercise never takes a number a requester was given.

**Seen, not changed.** `unsuppress --execute` has the same class of defect, outside what the
addendum asked for. If the un-suppress entry is appended and the log append then fails, the bare
error is raised. A re-run then stops with `NotSuppressed`, so it cannot log the reversal either.
Same fix, about ten lines and two tests, if you want it in this task or the next.

## Operator follow-ups

None is required for this task's criteria. The first is **recommended before the first real
request, and before `v1-e34-t05` enables the schedule**: moto does not enforce IAM, so a real
delete under `EvidenceRemoval` has not yet happened. (Both removal profiles exist and are signed in;
I checked read-only with `sts get-caller-identity`.)

1. **Done 2026-10-01 on `9ede19e`; results under "After the PM review".** `RM-2026-90` now has
   permanent synthetic entries in the dev suppression list (5 lines) and removal log (1 entry);
   record it in the register as the exercise. Kept for reference: **Exercise the takedown end to end
   on the real dev bucket, again** (about 5 min). The first
   run, on 2026-10-01, stopped before any delete. See "After the PM review" above. It left
   `testcl26` with four weeks published in dev (09-01, 09-08, 09-15 and 09-22), so this run imports
   the same four into a fresh scratch store first. Then it publishes, which changes nothing in the
   bucket, and removes. It **appends permanent synthetic entries under `RM-2026-90` to the dev
   suppression list and removal log**, so record `RM-2026-90` in the register as the exercise.

   ```zsh
   cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e30-t07-source-removal
   git branch --show-current
   git log --oneline -1
   aws sso login --sso-session debate
   export DEBATE_ENV=dev
   export DEBATE_STORAGE__DATA_DIR="$(mktemp -d)/evidence"
   X="$(mktemp -d)"
   uv run python -m tests.fixtures.caselist.build_synthetic_archives "$X"
   uv run debate-research caselist import "$X/testcl26-0901.zip" --caselist testcl26 --snapshot 2026-09-01
   uv run debate-research caselist import "$X/testcl26-0908.zip" --caselist testcl26 --snapshot 2026-09-08
   uv run debate-research caselist import "$X/testcl26-0915.zip" --caselist testcl26 --snapshot 2026-09-15
   uv run debate-research caselist import "$X/testcl26-0915.zip" --caselist testcl26 --snapshot 2026-09-22
   uv run debate-research caselist publish --caselist testcl26
   uv run debate-research caselist status --caselist testcl26
   uv run debate-research caselist remove --team 'testcl26/Maple Grove/QX' --request RM-2026-90 --reason POLICY
   DEBATE_REMOVAL_PROFILE=debate-dev-evidence-removal uv run debate-research caselist remove \
       --team 'testcl26/Maple Grove/QX' --request RM-2026-90 --reason POLICY --execute
   uv run debate-research caselist status --caselist testcl26
   uv run debate-research caselist import "$X/testcl26-0915.zip" --caselist testcl26 --snapshot 2026-09-29
   uv run debate-research caselist publish --caselist testcl26
   uv run debate-research caselist status --caselist testcl26
   aws s3api list-object-versions --profile debate-dev-evidence-removal --bucket debate-dev-evidence-a7508de8 \
       --prefix raw/caselist/testcl26/ --query 'length(Versions)'
   aws s3api list-object-versions --profile debate-dev-evidence-removal --bucket debate-dev-evidence-a7508de8 \
       --prefix manifests/_suppression/ --query 'Versions[].Key'
   unset DEBATE_ENV DEBATE_STORAGE__DATA_DIR X
   ```

   Success looks like this (rehearsed against moto from the same starting state):
   - `git branch` prints `task/v1-e30-t07-source-removal`, and `git log` shows `e7406c4` or later.
   - The four imports report `NEW` 4, 7, 2, 0. The publish says `4 of 4 snapshot(s) complete in the
     bucket; 0 source(s) uploaded`. The first `status` agrees.
   - The dry run prints 3 files to remove, 1 shared and kept, **8** manifest rewrites (4 weeks × 2
     sides) and 5 suppression entries, with "Versions not counted".
   - `--execute` prints `DONE in dev (debate-dev-evidence-a7508de8): 16 record(s), 3 local file(s),
     7 bucket object version(s) deleted; 8 manifest(s) rewritten without 42 row(s).`
   - The 09-29 import reports `UNCHANGED 10` and `SUPPRESSED 4`. The publish completes 5 of 5
     snapshots, uploading 0 sources, and both later `status` runs agree.
   - The raw version count is `11`, and the last command lists `removal-log.jsonl` and
     `suppression-list.jsonl`.

   If the bucket held versions moto's rehearsal did not, the version count in the `DONE` line may
   differ; every other number should match. Paste back everything from the dry run onwards. A
   preflight refusal or any `STORE_ACCESS_DENIED` means the real grants differ from
   `operator_access.tf` or from this account of them. Stop and send the message.
2. **Proposal: let the everyday profile count versions** (needs a `v1-e29-t03` spec change first, so
   this is the PM's call, then the evidence-store runbook's apply procedure as `debate-admin` in dev
   and prod). Add to `operator_policy` in `infrastructure/modules/evidence_bucket/operator_access.tf`:

   ```hcl
   {
     # Read-only: lets a removal's dry run count the noncurrent versions it would delete
     # (v1-e30-t07). Listing versions deletes nothing.
     Sid      = "ListEvidenceObjectVersionsForRemovalPlans"
     Effect   = "Allow"
     Action   = "s3:ListBucketVersions"
     Resource = aws_s3_bucket.evidence.arn
     Condition = { StringLike = { "s3:prefix" = local.removable_list_prefix_conditions } }
   },
   ```

   After the apply, the dry run shows version counts with no code change.

## Follow-up work

1. **E34 (`v1-e34-t02` scheduled sync): a removed camp file would be re-downloaded every week.**
   `_recorded_openev` in `caselist_sync.py` treated a manifest's SUPPRESSED row as "already
   handled". There are no such rows now (ac2), so the pull downloads the file again each week and the
   importer refuses it. No data comes back, but it spends the maintainer's download budget. The sync
   should remember suppressed downloads by OpenEv id in its own state.
2. **E31 (`v1-e31-t06` parse pipeline): the parsed store's index, occurrence table and failures file
   must be removal-aware.** Removal deletes the per-source parsed files by digest; aggregate files
   holding cards from a removed source need rebuilding after a removal, or the list consulted on read.
3. **E33: flag built files that quoted a removed card**, outside this task by the spec. The runbook's
   step 8 is still manual.
4. **Policy text (Charlie):** `docs/policies/caselist-data-use.md` still says "Until t07 ships, the
   runbook's manual section is the procedure" and links that section. The anchor still resolves (the
   runbook keeps it), but the sentence is out of date.
5. **`v1-e29-t03` spec change** for the `s3:ListBucketVersions` grant (Operator follow-up 2).
6. **`caselist status` sees current versions only**, under the everyday profile. Noncurrent leftovers
   are visible only to the takedown profile; `caselist remove` purges them, but no read-only command
   reports them.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED

**Reviewed by / date:** PM, 2026-10-01

**Notes:**

Accepted, phase `Succeeded`. The operator exercise under Operator follow-ups is required before
`v1-e34-t05` enables the schedule, and I am treating it as a condition on that task rather than on
this one.

**The structural placement is what I asked for and it found a path I did not know about.** I asked
for the check at the point a blob or manifest row is stored, so a fourth importer would inherit it
by construction. You put it on five write paths as a required argument with no default, re-checked
it at the write itself, and added an AST scan for modules that write caselist records outside the
pipeline. And `store sync` was a genuine fourth path I had not considered: it could put a removed
blob back in the bucket *and* truncate the bucket's copy of the suppression list. The forbidden
entry about rewriting the list is what led you there, which is the second time this fortnight a
forbidden list has turned out to carry the real requirement while the description carried only what
someone had noticed.

**You confirmed the dependency empirically, which I had only argued.** "Before this change the
scheduled pull called both importers with no suppression at all, so enabling `v1-e34-t05` would have
reversed takedowns weekly." I added that edge on reasoning about cumulative archives. It is better
to know.

**Three mutations survived at first and each exposed something real.** The `O_APPEND` test counted
lines, and an offset-zero write happens to leave three. The junk-row test only covered `--team`,
where the team rule drops those rows anyway. And the sweep, scoped to rewritten manifests, left a
re-run from a machine with no local copy sweeping nothing. That third one is a bug that would have
left noncurrent manifest versions naming a removed file in the bucket after a recovery run, and no
amount of reading would have found it. Mutation testing earns its cost in exactly these three
findings.

**The one survivor is reported honestly and I accept it as reported.** Deleting local records first
instead of last is defence in depth, and no test you could write without disabling the other
defences would fail. Saying so, rather than inventing a test that passes for the wrong reason or
quietly dropping the row, is the right handling of an unfalsifiable ordering property.

**On Deviations 1 and 2: I have no record of ruling on either.** The report says I chose both
mid-session. Those decisions did not come through the PM conversation. I am accepting both on their
merits below, so nothing needs redoing, but the provenance matters: a session that believes it has a
PM ruling it does not have will not re-raise the question, and the PM will not know a decision was
made. If a question is put to me and the answer arrives from anywhere else, say where it came from
in the report.

**Deviation 1, accepted on the merits.** Without disclosure scope, ac3 and a sha256-only ac4 leave a
real hole: the withdrawn team's copy of a shared file sits in every cumulative archive at the same
path, the blob legitimately stays for the other holder, and the next import records the disclosure
again every week. Keying on `sha256(caselist + "/" + path)` closes it. The digest is a deterministic
pseudonym for a team path, so anyone holding the public archive can reverse it by hashing every
path, but that is exactly as true of the file's own sha256, which is already stored. It adds no
exposure that the design did not already carry, and it is the difference between a withdrawal that
holds and one that is undone weekly.

**Deviation 2, accepted on the merits.** A dry run that fails because it lacks a read permission
would stop the operator seeing the plan at all, which is worse than a plan with one column missing,
and the mutation table shows you tested that it degrades rather than fails. Confirming the denial
read-only against the real dev bucket rather than assuming it from the policy file is the right kind
of check. I will decide the `s3:ListBucketVersions` grant separately as a `v1-e29-t03` amendment.

**Deviation 5 is the one with the longest reach.** Three Succeeded tasks now behave differently:
suppressed members get no manifest row, `publish` withholds a manifest that still names a suppressed
row, and `status` counts residue as drift. All three are right, and ac2 requires the first, since a
row would put the requester's path, school and team code back into the published manifest. But the
behaviour of a shipped guarantee has changed and the record of it lives in this task's report. I am
adding a line to `v1-e30-t05`'s spec rather than leaving it here, for the same reason the t05/t07
dependency is an edge and not a paragraph.

**Deviation 7 accepted, with a condition for revisiting.** Imports reading only the local copy is
right while there is one operator machine: `caselist import` is offline by design, the scheduled
path holds the bucket and reads the union, and `publish` refuses suppressed sources from the union
so nothing reaches the bucket. Revisit it the day a second machine imports, which is also the day
the one-line change in `container.py` stops costing `caselist import` its offline property for
nothing.

**Deviation 6 is a finding, not a deviation.** Junk rows that name a removed file and team through
`__MACOSX/._<name>` and Word's `~$` lock files would have reproduced the removed team's directory in
every week's manifest through junk alone. Your own test found it. That is the kind of thing a
takedown implementation gets wrong quietly and nobody notices until the requester does.

**Addendum, PM, 2026-10-01, after the real-dev exercise.** Verdict stands at ACCEPTED, with one
change to make before the pull request opens (the last item below). I read `c4402b2..75e927a`
rather than relying on this report's account of it, and specifically the diffs of `d26cb32` and
`e7406c4` to `removal_service.py` and `suppression.py`.

**The 403 is the finding of the exercise, and moto could never have shown it.** S3 answers a read
of a missing key with 403 for a principal that lacks `s3:ListBucket`, so the takedown profile could
not tell "no list yet" from "not allowed" in an environment that had never had a removal. Reading
with the everyday profile and writing with the takedown one is the right fix: no IAM change,
CloudTrail still attributes every append to the takedown credential, and the two failures stay
distinct, because only `NotFound` becomes an empty record and an access denial from the reader still
propagates as a failure. I checked that in the diff rather than taking it from the description.

**Both truthfulness fixes are right, and `e7406c4` is the method working.** The old message claimed
every suppression entry had been appended even when appending was the step that failed, and a
failed log append replaced the run's own error. You fixed both, and then a mutation (`suppressed`
never set) survived, showing nothing tested a run cut short *after* suppressing, and you added that
test instead of moving on. That is the standard.

**One path is still not truthful, and it is the same class of defect.** When every deletion
succeeds and the removal-log append then fails, `execute` re-raises the bare log error. The operator
sees a failure with nothing saying the removal itself completed. On a takedown that is the wrong
signal to send: it invites telling a requester the removal failed, and a re-run, which then logs a
`COMPLETED` entry with zero counts, so the real counts reach no record at all. Requested below.

**ac6's real-IAM half is closed, and so is the condition I put on `v1-e34-t05`.** The `9ede19e`
re-run deleted under `EvidenceRemoval` for real, every number matched the moto rehearsal, and the
read-only checks afterwards found no version, delete marker or manifest naming the removed files.
`v1-e34-t05` still waits on `v1-e34-t06` and on the new `v1-e34-t07` (from your Follow-up 1), but no
longer on an unobserved delete. `RM-2026-90` is now a permanent synthetic entry in the dev list and
log, so the register needs an entry saying what it is, before anyone has to ask.

**Operator follow-up 2 / Follow-up 5: granted, and a correction.** A read-only
`s3:ListBucketVersions` for `EvidenceOperator`, scoped to the removable prefixes, so a dry run shows
what an irreversible delete will remove. The profile can already read a version by id; it just
cannot list them, so the exposure is negligible and the operator's last look before deleting gets
better. Earlier today I recorded this item as already done. That was wrong: the existing grant is on
`EvidenceRemoval`, and I conflated the two permission sets. It is being filed into `v1-e29-t06`,
alongside the test-coverage gap found by looking at the same policy.

**Follow-ups 2 and 3 are filed as criteria, not left as prose.** `v1-e31-t06` (parse pipeline)
gains a dependency on this task and a criterion that its aggregates hold nothing from a removed
source, with the list as a required argument. `v1-e33-t04` (built-file quality checks) gains a
criterion to flag a built file quoting a removed card. Follow-up 6 becomes possible once the grant
lands and is noted there; it is code in `debate_core`, so it stays out of an infrastructure task.
Follow-up 4, the policy sentence, is Charlie's.

**And thank you for `47e73b8`.** Correcting the provenance of Deviations 1 and 2 in the report
itself, rather than leaving my verdict's complaint about it standing, is exactly the right response.

<!-- ACCEPTED / CHANGES_REQUESTED -->
