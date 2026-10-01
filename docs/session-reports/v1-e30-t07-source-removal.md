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
| **ac6** — `--execute` uses `DEBATE_REMOVAL_PROFILE`, failing clearly with no partial deletes if it is unset or lacks delete rights; `unsuppress --execute` appends both entries, the next import stores the file again, and the list is never rewritten | PASS | `test_unsuppress_and_removal_profile.py`, 10 passed: unset; everyday profile; lists-but-cannot-delete; signed out. All refused with bucket evidence, data dir, records and list unchanged. Unsuppress, then re-import stores the file again. Smoke: unset → refused; profile missing from the AWS config → refused with nothing changed; unsuppress end to end. Moto does not enforce IAM, so refusals are simulated by the stores; the everyday profile's real denial of `ListObjectVersions` was confirmed read-only against dev (see Decisions). |
| Node `suppression-list`: `uv run pytest packages/debate_core/tests/application/caselist/test_suppression_list.py` | PASS | `31 passed in 5.38s` |
| Node `importer-and-publisher-checks`: `uv run pytest packages/debate_core/tests/application/caselist -k suppress` | PASS | `72 passed in 7.70s` |
| Node `removal-planner`: `uv run pytest packages/debate_core/tests/application/caselist/test_removal_plan.py` | PASS | `20 passed in 6.72s` |
| Node `removal-executor`: `uv run pytest packages/debate_core/tests/application/caselist/test_removal_service.py` | PASS | `16 passed in 7.58s` |
| Node `unsuppress`: `uv run pytest packages/debate_core/tests/application/caselist -k "unsuppress or removal_profile"` | PASS | `13 passed in 6.63s` |
| Node `cli-and-smoke`: `uv run pytest tests/smoke/test_caselist_remove_smoke.py` | PASS | `6 passed in 8.42s` |
| Node `cli-and-smoke`: `uv run pyright packages/debate_core packages/debate_cli` | PASS | `0 errors, 0 warnings, 0 informations` |
| Node `cli-and-smoke`: `uv run lint-imports` | PASS | `Contracts: 10 kept, 0 broken.` |
| Whole Python suite, CI's selection (`pytest -m "not slow and not live" packages tests`) | PASS | `3330 passed, 1 skipped in 30.69s`. The skip is the pre-existing parser eval waiting on human corrections. Also clean: `ruff check .`, `ruff format --check .`, full `pyright`, the merge-conflict hook. |
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

## Operator follow-ups

None is required for this task's criteria. The first is **recommended before the first real
request, and before `v1-e34-t05` enables the schedule**: moto does not enforce IAM, so a real
delete under `EvidenceRemoval` has not yet happened. (Both removal profiles exist and are signed in;
I checked read-only with `sts get-caller-identity`.)

1. **Exercise the takedown end to end on the real dev bucket, with synthetic data** (about 5 min).
   This leaves a synthetic `testcl26` caselist in dev (dev holds synthetic and sample data), and
   **appends permanent synthetic entries under `RM-2026-90` to the dev suppression list and removal
   log**. Record `RM-2026-90` in the register as the exercise. A scratch local store keeps it off
   your real dev data directory.

   ```zsh
   cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e30-t07-source-removal
   git branch --show-current
   aws sso login --sso-session debate
   export DEBATE_ENV=dev
   export DEBATE_STORAGE__DATA_DIR="$(mktemp -d)/evidence"
   X="$(mktemp -d)"
   uv run python -m tests.fixtures.caselist.build_synthetic_archives "$X"
   uv run debate-research caselist import "$X/testcl26-0901.zip" --caselist testcl26 --snapshot 2026-09-01
   uv run debate-research caselist import "$X/testcl26-0908.zip" --caselist testcl26 --snapshot 2026-09-08
   uv run debate-research caselist import "$X/testcl26-0915.zip" --caselist testcl26 --snapshot 2026-09-15
   uv run debate-research caselist publish --caselist testcl26
   uv run debate-research caselist remove --team 'testcl26/Maple Grove/QX' --request RM-2026-90 --reason POLICY
   DEBATE_REMOVAL_PROFILE=debate-dev-evidence-removal uv run debate-research caselist remove \
       --team 'testcl26/Maple Grove/QX' --request RM-2026-90 --reason POLICY --execute
   uv run debate-research caselist status --caselist testcl26
   uv run debate-research caselist import "$X/testcl26-0915.zip" --caselist testcl26 --snapshot 2026-09-22
   uv run debate-research caselist publish --caselist testcl26
   uv run debate-research caselist status --caselist testcl26
   aws s3api list-object-versions --profile debate-dev-evidence-removal --bucket debate-dev-evidence-a7508de8 \
       --prefix raw/caselist/testcl26/ --query 'length(Versions)'
   unset DEBATE_ENV DEBATE_STORAGE__DATA_DIR X
   ```

   Success looks like:
   - The dry run prints 3 files to remove, 1 shared and kept, 6 manifest rewrites and 5 suppression
     entries, with "Versions not counted".
   - `--execute` prints `DONE in dev …: 12 record(s), 3 local file(s), …`.
   - Both `status` runs exit 0.
   - The 09-22 import reports `SUPPRESSED 4`.
   - The final count is `11` (14 synthetic bodies published, 3 removed with every version).

   Paste the `--execute` line and the last three outputs back. A preflight refusal here would mean
   the `EvidenceRemoval` grants differ from `operator_access.tf`. Stop and send the message.
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
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
