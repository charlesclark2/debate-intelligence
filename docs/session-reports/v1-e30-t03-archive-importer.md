# Session report: v1-e30-t03-archive-importer

| | |
|---|---|
| Task | `v1-e30-t03-archive-importer` — Weekly archive importer |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t03-archive-importer.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t03-archive-importer.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t03-archive-importer` |
| Session status | COMPLETE |

## Summary

`debate-research caselist import <zip|dir> --caselist <slug> --snapshot <date>` turns one weekly
OpenCaselist archive into deduplicated source documents, disclosures and a JSONL manifest in the
local evidence store. Because the archives are cumulative, every member is classified against the
latest archive *strictly earlier* than the one being imported — NEW, UNCHANGED, CHANGED,
DUPLICATE, REMOVED or SUPPRESSED — so three overlapping weeks holding fourteen distinct files
store fourteen blobs rather than forty-one appearances.

The work is split the way the spec asks: a pure path parser and the import service in
`debate_core.application.caselist`, a safe zip/directory reader and the SQLite repository in
`debate_core.integrations.local`, and a `debate_cli` command that only wires and renders. The
archive vocabulary (`ArchiveMember`, `SkippedMember`, `SkipReason`) sits in
`application/ports/archive.py` so the service depends on it rather than on the adapter that
produces it; `lint-imports` and `pyright` both pass.

**Three things the PM should look at first**, all in [Deviations](#deviations-from-the-spec):
ac3's "zero NEW" and "identical manifest bytes" cannot both be literally true of the same number,
so the report carries `newly_stored_blobs` beside the classification counts; the manifest lands
at `<data_dir>/objects/manifests/…` rather than ac4's literal `<data_dir>/manifests/…`, because
that is where the shipped evidence object store roots named objects and therefore what
`store sync` will publish in t05; and ac6 asks for relative paths at INFO, which
`docs/policies/caselist-data-use.md` rule 4 forbids — the policy won, and a test asserts it.

Everything is synthetic. No real caselist file, school, team code or path is in the repository,
and real-corpus verification is an operator run ([Operator follow-ups](#operator-follow-ups)).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `synthetic-fixture` | Done | Three invented cumulative archives (`testcl26-0901/0908/0915`) built from literals in one module, plus `expected_summary.json` whose counts are hand-written, never derived from the importer. |
| `filename-parser` | Done | `parse_disclosure_path` anchors on the side token instead of counting hyphens, believes the directories over the filename, and never drops a file. 102 table cases. |
| `archive-reader` | Done | `read_archive` over a zip or a directory: zip-slip and symlink refusal, junk skipped with counted reasons, two size ceilings checked before anything is extracted, one member of memory at a time. |
| `import-service` | Done | `CaselistImportService` plus `SqliteCaselistRepository` on migration 2. The cumulative dedupe, the ordering refusal, and the idempotent re-import. |
| `manifest-and-cli` | Done | Deterministic schema-versioned JSONL, and the Typer command with `--dry-run`, `--allow-out-of-order`, `--event` and the global `--json`. |
| `smoke-and-gates` | Done | Offline smoke check over the installed command; `pyright`, `ruff` and `lint-imports` all clean. |

## Acceptance criteria

All commands were run in the task worktree. Timings are wall-clock from the run quoted.

### Goal criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — parser reads School/TeamCode/Side/Tournament/Round for the canonical pattern and every odd case; an unparseable name yields Side UNKNOWN and a warning, never a drop | PASS | `uv run pytest packages/debate_core/tests/application/caselist/test_path_parser.py` → **102 passed in 3.92s**. The table covers all twelve odd fixture members plus Pro/Con in PF, a bare side, an unrecognised round, a two-word elimination round, a school whose name contains a side word, and twelve deliberately unreadable paths that must still parse. `test_an_unreadable_filename_still_becomes_a_disclosure` checks the same end to end through the store. |
| **ac2** — three cumulative snapshots in order store each distinct file once and report counts matching the expected summary | PASS | `uv run pytest packages/debate_core/tests/application/caselist/test_import_service.py` → **39 passed in 3.70s**. `test_the_three_archives_report_exactly_the_expected_counts` compares every week against `expected_summary.json`; `test_each_distinct_file_is_stored_exactly_once` asserts the blob count on disk equals the 14 distinct digests. Confirmed through the CLI too (`test_importing_the_three_weeks_in_order_matches_the_expected_summary`). |
| **ac3** — re-import is a no-op (identical manifest bytes, zero NEW); an older snapshot is refused without `--allow-out-of-order` | PASS, with one interpretation | `uv run pytest packages/debate_cli/tests/test_caselist_import.py` → **36 passed in 3.00s**. `test_re_importing_a_week_writes_byte_identical_manifest_bytes` compares the file's bytes; `test_re_importing_a_week_stores_no_further_files` asserts `newly_stored_blobs == 0` and an unchanged blob tree; `test_an_older_archive_is_refused_with_a_domain_failure` and `..._is_imported_when_the_flag_is_given` cover the ordering rule. See Deviation 1 on "zero NEW". |
| **ac4** — `manifests/<caselist>/<snapshot>.jsonl` has one schema-versioned row per member, sorted by path, with a trailing summary row | PASS, at a different root | Same CLI run. `test_every_row_is_schema_versioned`, `test_there_is_one_member_row_per_archive_member_sorted_by_path`, `test_a_member_row_carries_everything_ac4_names` (path, sha256, byte_size, format, classification, school, team_code, side, tournament, round, round_normalized, warnings) and `test_the_last_row_is_the_summary`. See Deviation 2 on the path. |
| **ac5** — members outside the staging root, symlinks, `__MACOSX/`, `.DS_Store` and `~$` files are skipped with a counted reason; an oversized zip is rejected before unpacking | PASS | `uv run pytest packages/debate_core/tests/integrations/local/test_archive_reader.py` → **40 passed in 3.90s**. Seven shapes of escaping name, symlinks in both zip and directory form, a symlinked directory that is not descended into, each junk kind with its own reason, and both ceilings — `test_a_refused_archive_yields_no_member_at_all` drives the generator one step to prove the refusal happens before the first yield. Also exercised through the setting an operator would change (`test_an_archive_over_the_configured_ceiling_is_refused`). |
| **ac6** — Rich summary table (or JSON with `--json`), `--dry-run` writes nothing, and INFO logs carry only counts | PASS, logs stricter than asked | Same CLI run. `test_importing_one_week_succeeds_and_prints_a_summary_table`, `test_the_json_envelope_reports_every_classification`, `test_a_dry_run_writes_no_blob_and_no_manifest`. Logging: `test_the_import_logs_counts_and_never_a_path_school_or_team_code` asserts no school, team code or `.docx` reaches any log record, and `test_the_import_does_log_the_counts_an_operator_needs` asserts the counts are there. See Deviation 3. |

### Node criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| `synthetic-fixture` — Expected summary committed (`artifact_exists`, contains `testcl26`) | PASS | `tests/fixtures/caselist/expected_summary.json` exists and its `caselist` field is `testcl26`; pinned by `test_the_expected_summary_names_the_synthetic_caselist`. |
| `synthetic-fixture` — Fixture builder is deterministic | PASS | `uv run pytest tests/fixtures/caselist/test_build_synthetic_archives.py` → **15 passed in 1.39s**. |
| `filename-parser` — Filename parser table tests pass | PASS | `uv run pytest packages/debate_core/tests/application/caselist/test_path_parser.py` → **102 passed in 3.92s**. |
| `archive-reader` — Archive reader safety tests pass | PASS | `uv run pytest packages/debate_core/tests/integrations/local/test_archive_reader.py` → **40 passed in 3.90s**. |
| `import-service` — Cumulative import tests match expected summary | PASS | `uv run pytest packages/debate_core/tests/application/caselist/test_import_service.py` → **39 passed in 3.70s**. |
| `import-service` — SQLite caselist repository tests pass | PASS | `uv run pytest packages/debate_core/tests/integrations/local/test_sqlite_caselist_repository.py` → **39 passed in 3.21s**. |
| `manifest-and-cli` — Manifest and CLI tests pass | PASS | `uv run pytest packages/debate_cli/tests/test_caselist_import.py` → **36 passed in 3.00s**. |
| `manifest-and-cli` — Command is registered | PASS | `uv run debate-research caselist import --help` → exit 0, listing `--caselist`, `--snapshot`, `--event`, `--dry-run`, `--allow-out-of-order`. |
| `smoke-and-gates` — Caselist import smoke check passes | PASS | `uv run pytest tests/smoke/test_caselist_import_smoke.py` → **4 passed in 2.61s**. |
| `smoke-and-gates` — Type check passes | PASS | `uv run pyright packages/debate_core packages/debate_cli` → **0 errors, 0 warnings, 0 informations**. |
| `smoke-and-gates` — Import boundaries hold | PASS | `uv run lint-imports` → **Contracts: 2 kept, 0 broken** (101 files, 374 dependencies). |

### Whole-suite gates

| Check | Status | Evidence |
|---|---|---|
| Full default suite | PASS | `uv run pytest` → **1683 passed in 22.83s**, total coverage 98%. Comfortably inside the 5-minute CI budget (`docs/process/working-agreements.md` §1). |
| Lint and format | PASS | `uv run ruff check .` → All checks passed. `uv run ruff format --check .` → 239 files already formatted. |
| Spec validation | PASS | `uv run scripts/validate_specs.py` → `OK: 282 files, 38 epics, 224 tasks, 20 releases`. |
| Coverage of new modules | PASS | `sqlite_caselist_repository.py` 100%, `commands/caselist.py` 100%, `import_service.py` 99%, `archive_reader.py` 96%, `path_parser.py` 95%, `manifest.py` 95%. |

## Files changed

**`debate_core.application.caselist`** (new package) — `path_parser.py` reads one archive path
into school, team code, side, tournament, round and warnings; `import_service.py` classifies an
archive's members against the week before it and stores what is new; `manifest.py` renders and
writes the per-snapshot JSONL.

**`debate_core.application.ports`** — new `archive.py` holding `ArchiveMember`, `SkippedMember`,
`SkipReason` and the `ArchiveEntry` union, so the import service depends on the vocabulary rather
than on the adapter. Re-exported from `ports/__init__.py`.

**`debate_core.application.errors`** — `ArchiveTooLarge` and `UnreadableArchive`, so the reader
raises only from this hierarchy like every other adapter.

**`debate_core.application.settings`** — a `caselist` group with `max_archive_bytes` (2 GiB) and
`max_unpacked_bytes` (8 GiB), which is the "size limit from settings" the archive-reader node
asks for.

**`debate_core.integrations.local`** — `archive_reader.py` (safe zip/directory reading),
`sqlite_caselist_repository.py` (the t02 port on SQLite) and migration
`0002_caselist_records.sql` (four tables, ten indexes). Both new modules exported from the
package's `__init__.py`.

**`debate_cli`** — `commands/caselist.py` (the command, the slug→event table and the rendering),
`container.py` (a `database` property and the `caselist_import` service), `commands/__init__.py`
(the group registration).

**`tests/fixtures/caselist/`** (new) — the synthetic archive builder, its committed
`expected_summary.json` and the builder's own tests.

**`conftest.py`** (new, repository root) — puts the root on `sys.path` so the four suites in three
packages that need the fixture builder can import it rather than each keeping a copy. pytest runs
with `--import-mode=importlib`, which does not do this the way the legacy `prepend` mode did.

**Tests touched that this task does not own** — `packages/debate_core/tests/integrations/local/
test_sqlite_db.py` pins the exact set of tables and indexes, so migration 2 adds its own to both
lists; while there, `test_the_shipped_migrations_are_what_build_migrations_makes_of_them` now
reads every `.sql` file off disk instead of naming `0001` explicitly, so the next migration does
not have to edit the check that new migration files are well formed.
`packages/debate_cli/tests/test_app.py` pins the list of services the container can build, and
its own comment says a later epic adding one adds it there too. `tests/smoke/README.md` gained a
row and a paragraph on why the new check is not marked `live`.

## Deviations from the spec

### 1. ac3's "zero NEW" is reported as `newly_stored_blobs`, not as a NEW count of zero

ac3 asks for two things that cannot both be literally true of the same number:

* **identical manifest bytes** requires the classifications to be identical between runs, which
  requires the baseline to be identical — so the baseline must be the latest archive *strictly
  earlier* than the one being imported, and importing `0915` a second time must classify its two
  genuinely new files as NEW both times, exactly as the first run did;
* **zero NEW** would require the baseline to include the archive itself, which would make the
  second run's manifest differ from the first's.

Implemented as: classification counts describe **the archive**, against the week before it, and
never change between runs (so the manifest is byte-identical, and it deliberately carries no
timestamp, no `applied` flag and no stored count). What is zero on a second run is what the run
actually **wrote**, reported as `ImportReport.newly_stored_blobs` and in the `--json` envelope.
`test_re_importing_a_week_writes_byte_identical_manifest_bytes` and
`test_re_importing_a_week_stores_no_further_files` cover both halves.

**For the PM:** this reads as the intent behind ac3 rather than a change to it, but ac3's wording
would be clearer as "identical manifest bytes and nothing newly stored".

### 2. The manifest is at `<data_dir>/objects/manifests/<caselist>/<snapshot>.jsonl`

ac4 (and the PM's context note) says `<data_dir>/manifests/<caselist>/<snapshot>.jsonl`. The
shipped `FsEvidenceObjectStore` (v1-e02-t03, used by `store sync` in v1-e29-t05) roots named
objects under `<data_dir>/objects/` to keep them out of the content-addressed `blobs/` tree; its
own module docstring gives `manifests/hsld26/2026-09-15.jsonl` as an example **key**. Writing to
`<data_dir>/manifests/` literally would put the manifest outside the object store, and t05 could
not publish it with the sync that already exists.

So the **object key is exactly what ac4 names** — `manifests/<caselist>/<snapshot>.jsonl`, which
is also the bucket key — and only the local root differs. Nothing in t05 needs to change.

**For the PM:** ac4 (and t05's spec, if it repeats the path) would be right as
"`manifests/<caselist>/<snapshot>.jsonl` in the evidence object store".

### 3. INFO logs carry counts only — not relative paths

ac6 says the command "logs only counts and relative paths at INFO".
`docs/policies/caselist-data-use.md` rule 4, which Charlie approved, is stricter: *"Never in logs.
No school, team code, filename or disclosure path in application logs, error messages,
tracebacks, metrics labels or telemetry — in any environment."* A relative archive path is
`<School>/<TeamCode>/<filename>` — all three of the forbidden things at once.

The policy won. Logs carry counts, the caselist slug and the snapshot date; paths live in the
manifest and the local store, which the policy names as places they may live.
`test_the_import_logs_counts_and_never_a_path_school_or_team_code` asserts it rather than
trusting it. The same rule is applied to error messages: `ArchiveTooLarge` names the archive's own
filename and never a member's path, and the parser's warning about a rejected team-code directory
deliberately does not quote the value, because a whitespace-separated "code" is the case most
likely to be a real name.

**For the PM:** ac6 should drop "and relative paths".

### 4. The smoke check is not marked `live`

`tests/smoke/README.md` said every check there needs the network and is marked `live`. The
`smoke-and-gates` node's criterion is a plain `uv run pytest tests/smoke/
test_caselist_import_smoke.py`, which under the default options (`-m "not slow and not live"`)
would collect and skip a `live` test — so the check would never actually run, in CI or before a
promotion. It is unmarked and offline, and the README now states the rule ("marked `live` when it
needs a deployed environment, not because it lives here") rather than the previous blanket claim.

## Decisions and assumptions

**The side token is the anchor, not the hyphen count.** The canonical name is
`<School>-<TeamCode>-<Side>-<Tournament>-<Round>`, but tournaments contain hyphens, em dashes and
doubled hyphens, so counting separators shifts every field after the first odd one. The parser
finds the first token that is a side and splits there. This is what lets
`Neg-02----Ridgeline Round Robin-Round 6` come out as side NEG, copy index 2, tournament
"Ridgeline Round Robin", round R6.

**The directories are believed over the filename.** School and team code come from the two
directories above the file; a filename prefix naming neither is a warning, never an override.
Teams abbreviate their school in the filename far more often than they file under the wrong team,
so a prefix carrying the team code, or beginning with the school, is accepted without comment.

**The round is taken by position, recognised or not.** With two or more tokens after the side,
the last is the round — kept as `RoundLabel.raw` with `normalized=None` and a warning when the
platform does not recognise the spelling, rather than being swallowed into the tournament.
Two- and three-token elimination names (`Double Octas`) are tried first.

**An unusable team-code directory is `UNKNOWN`, and the warning does not quote it.** `TeamCodeText`
rejects whitespace and anything over 12 characters (v1-e30-t02). A directory like `Rivera and Osei`
is a pair of names, not a disclosed code, so it is not stored — and neither is it repeated back
into a manifest row or a console line.

**A wrapper directory is stripped only when the archive says twice over that it is one.** A
downloaded zip holds one directory named after itself. It is removed only when every nested member
shares that first component *and* it is either the archive's filename stem or removing it still
leaves every ordinary member at `<School>/<TeamCode>/<file>` depth. A zip containing one school's
directory is therefore left alone — stripping it would have deleted the school. Directory imports
never strip: the directory the operator points at *is* the archive root.

**The event is inferred from the caselist slug, and an unknown slug is refused.**
`EVENTS_BY_SLUG_PREFIX` maps `hsld`/`hspolicy`/`hspf`/`ndtceda`/`nfald` (and the synthetic
`testcl`) to their events. A slug the build does not know fails with a message naming `--event`,
because guessing would file a whole archive under a side the event does not debate. The slug
itself is never hardcoded — it is always the `--caselist` argument.

**The suppression list is an argument, defaulted to empty.** t07 owns the list and its
persistence. This task honours it: a member whose digest is in `suppressed_hashes` is counted
`SUPPRESSED`, is not stored and gets no disclosure, however many more times the cumulative
archives republish it.

**`ArchiveSnapshot.file_count` counts every member, junk included**, because the field's own
docstring says "how many member files the archive contained" and that is the number an operator
can check against `unzip -l`.

**A directory's archive digest is over its members, not its bytes.** A directory has no bytes of
its own, so `archive_digest` hashes the sorted (path, digest) pairs. A directory and the zip it
came out of therefore hash differently, which is honest: they are not the same download.

**Reading holds one member of memory at a time** and unpacks nothing to disk — the bytes go
straight to the caller. That is a stronger form of the zip-slip guarantee than a staging directory
would be: there is no path to escape onto.

## Operator follow-ups

### Verify the parser and the dedupe against the real corpus

This is the one thing the synthetic fixture cannot tell you: whether the parser copes with the
real 2,342 files and what the real deduplication rate is. It will take well over two minutes, so
it is yours to run.

**Operator command** (expected runtime ~10–25 min for all three weeks, mostly hashing)
Where: your Mac, in the task worktree `debate-intelligence-worktrees/v1-e30-t03-archive-importer`

```bash
# A scratch data directory, so this touches neither ~/.debate-research/dev nor prod.
export DEBATE_STORAGE__DATA_DIR=/tmp/caselist-real-corpus
rm -rf "$DEBATE_STORAGE__DATA_DIR"
CORPUS=~/Documents/debate/2026-2027/"LD Debate"/Opencaselist

for week in 0901 0908 0915; do
  uv run debate-research --json caselist import "$CORPUS/hsld26-$week" \
    --caselist hsld26 --snapshot "2026-09-${week:2:2}" | tee "/tmp/hsld26-$week.json"
done
```

Success looks like: three JSON objects with `"status": "ok"`, and counts in this shape —
09-01 almost all `NEW` (~64 files); 09-08 mostly `UNCHANGED` with ~680 `NEW`; 09-15 mostly
`UNCHANGED` with ~850 `NEW` and some `REMOVED`. What to check, and paste back into the PR:

1. `counts` and `skipped` for each week — **counts only, no paths**.
2. `warnings` per week as a fraction of `members`. If it is above roughly 10%, the parser is
   missing a real filename shape and that is worth a follow-up task rather than a silent
   acceptance.
3. `distinct_sha256` for 09-15 against the sum of `NEW` across the three weeks — they should
   agree, and that is the deduplication working.
4. That nothing was written outside `$DEBATE_STORAGE__DATA_DIR`.

To see *which* filename shapes are being warned about without quoting any of them:

```bash
jq -r 'select(.kind=="member") | .warnings[]' \
  /tmp/caselist-real-corpus/objects/manifests/hsld26/2026-09-15.jsonl \
  | sort | uniq -c | sort -rn
```

That prints warning texts and counts, never a school, team code or path — safe to paste.

**Do not** copy any part of the corpus, any manifest, or any archive into the repository
(`docs/policies/caselist-data-use.md`; the spec's `forbidden` list). Aggregate counts only.

### Then remove the scratch directory

```bash
rm -rf /tmp/caselist-real-corpus /tmp/hsld26-09*.json
```

## Follow-up work

1. **`caselist status` / listing commands** — nothing yet shows what has been imported without
   reading the SQLite file. The repository supports it (`list_snapshots`, `list_sources`,
   `list_disclosures`); `v1-e30-t05` already owns a `caselist status` that compares local and S3,
   so it probably belongs there rather than in a new task.
2. **A `--suppression-list` flag.** The service takes `suppressed_hashes`; the CLI has no way to
   pass one yet, because the list's format and location are `v1-e30-t07`'s to define. t07 will
   need to add the flag (or the container wiring) when it does.
3. **No source-path filter on `CaselistRepository.list_disclosures`.** The importer reads a whole
   snapshot's disclosures into a dictionary to build its baseline, which is right at a weekly
   archive's scale (a few thousand short strings) but means "what is at this path?" is a listing
   plus a filter in Python. If E32's reports or t07's removal need that lookup, it is a port
   change for whichever task hits it first.
4. **Unrecognised round spellings.** `normalize_round_token` knows prelims and the usual
   elimination names; anything else is kept raw with a warning. The operator run above will show
   which real spellings come back unrecognised, and whether
   `ELIMINATION_ROUND_SPELLINGS` (v1-e30-t02) is worth extending before E32 aggregates by round.
5. **`uv sync --all-packages` in a fresh worktree.** This worktree's `.venv` had the four
   workspace packages missing, so `import debate_core` failed until `uv sync --all-packages` was
   run. If `scripts/task` creates worktrees, having it run that (or documenting it in
   `docs/process/task-workflow.md`) would save the next session the detour.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
