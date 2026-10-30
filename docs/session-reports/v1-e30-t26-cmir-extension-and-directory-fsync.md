# Session report: v1-e30-t26-cmir-extension-and-directory-fsync

| | |
|---|---|
| Task | `v1-e30-t26-cmir-extension-and-directory-fsync` — A .cmir file is imported as CMIR, and every rename-into-place writer fsyncs its directory |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t26-cmir-extension-and-directory-fsync.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t26-cmir-extension-and-directory-fsync.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t26-cmir-extension-and-directory-fsync` |
| Session status | COMPLETE |

## Summary

(1) The importer maps a `.cmir` file name to `SourceFormat.CMIR` (`path_parser._FORMATS_BY_EXTENSION`),
so the manifest records it under its own format, and `caselist parse`, which reads the format from
the manifest, counts it `unsupported {"CMIR": 1}` where it counted `OTHER` before. Before I committed
the mapping, both builds in service read a manifest this build wrote, each with its own code:
**`v1.1.0-dev.155` (`76b53e7`)**, the Mac's installed agent, and **`v1.1.0-dev.164` (`03b23e2`)**,
the cloud image from tonight. Each read the row as `CMIR`, its parse counted it unsupported under
`CMIR`, its `store sync` publish succeeded, and its `caselist status` said in sync.
(2) The inbox archive rewrite in `inbox_purge.py`, `FileTokenBackend.write` in `token_store.py`
and `write_pretty_json` in `_recorded_files.py` now fsync the file, rename it into place and fsync
the directory, and a failed directory fsync raises. `write_pretty_json` also fsyncs its file now,
which it never did before. They all use v1-e30-t23's helper, which I moved from `manifest.py` to a
new `debate_core/application/durable_files.py`, so the manifest writer uses it too. All 13 mutants
were caught. **First, PM:** the affected set is 365 of 565 test files. Editing `_recorded_files.py`
reaches the root conftest through `fake_router`. That is over two minutes, so the full run is left
to the pull request's `ci` check, under agreement 10. What I ran is under
[Affected set and checks](#affected-set-and-checks).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `cmir-and-fsync`: CMIR extension and directory fsync | Done | Part (1): red test `f97bd1a`, then the mapping and the cross-build scripts `19376ff`. Part (2): red test `ae97ef4`, then the helper and the three writers `df9a459`. Its criterion passes: `85 passed` |

## Acceptance criteria

"Red" means the new tests run against the branch's start commit code, before the change, with the
tests committed alone first (`f97bd1a`, `ae97ef4`).

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: a `.cmir` file in an archive is recorded as `CMIR` and counted unsupported, by test shown failing first; the report names the agent build that reads it | PASS | `test_a_cmir_file_is_imported_as_cmir.py` imports one synthetic weekly archive with the real importer. The archive holds a verbatim `.docx` and a gzip-and-JSON `.cmir`. **Red** (`uv run pytest <file> -q -n 0 -p no:randomly --tb=line`): `5 failed, 6 passed`. Failures: `assert <SourceFormat.OTHER: 'OTHER'> is <SourceFormat.CMIR: 'CMIR'>` for `.cmir`, `.CMIR` and `.Cmir`; the manifest row `('NEW', 'OTHER') != ('NEW', 'CMIR')`; and the parse run `(1, {'OTHER': 1}, {}) == (1, {'CMIR': 1}, {})`. The 6 that passed hold before and after: `.docx`, `.doc`, `.pdf`, `.cmir.txt`, `.cmirx` and a bare `cmir` keep their formats. **Green:** `11 passed`. The `.cmir` row is `"format": "CMIR"`, the SQLite source is `CMIR`, `report.unsupported == {"CMIR": 1}` with `parsed == 1` and `failed == {}`, and `failures.jsonl` has the one row `(digest, "UNSUPPORTED", "UNSUPPORTED_FORMAT", "CMIR")`. All expected values are written by hand from the two members. **The builds that read it:** `v1.1.0-dev.155` (`76b53e7`, the Mac's installed agent) and `v1.1.0-dev.164` (`03b23e2`, the cloud image). See [Every build reads a CMIR manifest](#every-build-reads-a-cmir-manifest) |
| **ac2**: each of the three writers fsyncs the file, renames, then fsyncs the directory, and a failed directory fsync raises, by recording test | PASS | `test_rename_into_place_writers_fsync_their_directory.py` wraps `os.open`, `os.fsync` and `os.replace` to record calls, as t23's manifest test does. It runs each writer through its public entry point: `purge_inbox` with a hand-made rewrite plan for a weekly archive, `FileTokenBackend(path).write`, and `write_pretty_json`. For each writer it asserts the exact sequence `fsync file (inode of the final file)`, `replace <path>`, `open <directory>`, `fsync directory <directory>`, plus the content read back. It also checks that a rewrite over an earlier file ends with the directory fsync, and that `EIO` from a directory fsync raises `OSError`. **Red:** `9 failed`, and each failure is the missing step: 6 sequence assertions with no `open`/`fsync directory` after the `replace` (for `write_pretty_json`, no `fsync file` either), and 3 `Failed: DID NOT RAISE OSError`. **Green:** `9 passed`, and t23's `test_manifest_write_fsyncs_its_directory.py` still passes (`4 passed`) after its helper moved |
| Node `cmir-and-fsync`: `uv run pytest packages/debate_core/tests -k "cmir or fsync or inbox_purge or token_store"` | PASS | Run as `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest packages/debate_core/tests -k "cmir or fsync or inbox_purge or token_store"` (the same interpreter, with agreement 10's hard stop) → `85 passed in 41.23s` |

### Every build reads a CMIR manifest

The PM asked for the method v1-e34-t31 used. I exported each tag with `git archive` into the
session's scratch directory and put its `debate_core` first on `PYTHONPATH`. Both tags were already
local, so nothing was fetched and no installed build was opened. Both tags define
`SourceFormat.CMIR` (from v1-e31-t15, `9877884`). In both, the one manifest reader that parses
`format` is `parse_sources._stored_rows`, which refuses an unknown format with `UnreadableManifest`.
`write_cmir_manifest_files.py` imports the week of the ac1 test with this build and writes its
manifest. `check_an_older_build_reads_a_cmir_manifest.py` copies that data directory to pytest's
temporary directory, then does what each build does with a manifest:

1. reads the row with `read_manifest_file`;
2. plans and runs `caselist parse` with that build's `DebateDocxParser`;
3. publishes to a moto bucket with `CaselistPublishService`, as `store sync` does;
4. asks `CaselistStatusService` whether the bucket and this machine agree.

`S` is the scratch directory, and `S/dev155` and `S/dev164` are the two exported sources:

```bash
WRITE_CMIR_MANIFEST_FILES="${S}/files" .venv/bin/python -m pytest packages/debate_core/tests/application/caselist/write_cmir_manifest_files.py -p no:cacheprovider --no-cov -n 0 -q -s
CMIR_MANIFEST_FILES="${S}/files" .venv/bin/python -m pytest packages/debate_core/tests/application/caselist/check_an_older_build_reads_a_cmir_manifest.py -p no:cacheprovider --no-cov -n 0 -q
PYTHONPATH="${S}/dev155/packages/debate_core/src" CMIR_MANIFEST_FILES="${S}/files" .venv/bin/python -m pytest packages/debate_core/tests/application/caselist/check_an_older_build_reads_a_cmir_manifest.py -p no:cacheprovider --no-cov -n 0 -q
PYTHONPATH="${S}/dev164/packages/debate_core/src" CMIR_MANIFEST_FILES="${S}/files" .venv/bin/python -m pytest packages/debate_core/tests/application/caselist/check_an_older_build_reads_a_cmir_manifest.py -p no:cacheprovider --no-cov -n 0 -q
```

The written manifest's `.cmir` row is
`{"byte_size":67,"classification":"NEW",…,"format":"CMIR","kind":"member",…}`. All three runs
passed (`1 passed`). After the `reader:` line, the three builds printed the same lines:

```text
manifest row read: format CMIR
caselist parse plan: 2 sources, formats ['CMIR', 'DOCX']
caselist parse run: parsed 1, unsupported {'CMIR': 1}, failed {}
store sync publish: succeeded True
caselist status: in sync True
```

**The check can fail.** I copied the dev.155 export and removed `CMIR` from its `SourceFormat`,
then ran the same check against that copy. It failed:
`UnreadableManifest: manifests/testcl26/2026-10-05.jsonl line 2 is not a usable manifest row: a
stored member with no size or format`, raised at `parse_sources.py:280`. A build that refused CMIR
is caught, and neither build in service is one.

### Mutants

There are 13 mutants: the PM's five kinds, with (2) to (4) applied to each writer, plus two in the
moved helper. The harness applied each one, ran the covering files with
`-n 0 -p no:randomly --no-cov`, and restored the file from `HEAD`. It ended on a clean tree. For
mutant 1 the covering file is the ac1 test. For the others it is the ac2 test plus t23's manifest
test, 13 tests in all. No property test covers this code. Every run still set
`HYPOTHESIS_STORAGE_DIRECTORY` to a new empty directory (agreement 8).

| Mutant | Result | First test to fail |
|---|---|---|
| 1 `.cmir` left on its old mapping (`OTHER`) | CAUGHT, 5 failed | `test_a_cmir_name_is_the_cmir_format[round-2.cmir]`; also the manifest and parse-count tests |
| 2a inbox rewrite: directory fsync dropped | CAUGHT, 3 failed | `test_the_file_is_fsynced_then_renamed_then_its_directory_is_fsynced[inbox_purge rewrite]` |
| 2b token store: directory fsync dropped | CAUGHT, 3 failed | `…[token_store FileTokenBackend.write]` |
| 2c `write_pretty_json`: directory fsync dropped | CAUGHT, 3 failed | `…[write_pretty_json]` |
| 3a inbox rewrite: directory fsync moved before the rename | CAUGHT, 2 failed | `test_the_file_is_fsynced_then_renamed_then_its_directory_is_fsynced[inbox_purge rewrite]` |
| 3b token store: directory fsync moved before the rename | CAUGHT, 2 failed | `…[token_store FileTokenBackend.write]` |
| 3c `write_pretty_json`: directory fsync moved before the rename | CAUGHT, 2 failed | `…[write_pretty_json]` |
| 4a inbox rewrite: a failed directory fsync swallowed | CAUGHT, 1 failed | `test_a_directory_fsync_that_fails_is_a_write_that_failed[inbox_purge rewrite]` |
| 4b token store: a failed directory fsync swallowed | CAUGHT, 1 failed | `…[token_store FileTokenBackend.write]` |
| 4c `write_pretty_json`: a failed directory fsync swallowed | CAUGHT, 1 failed | `…[write_pretty_json]` |
| 5 `write_pretty_json`: file fsync dropped | CAUGHT, 1 failed | `test_the_file_is_fsynced_then_renamed_then_its_directory_is_fsynced[write_pretty_json]` |
| 6 shared helper fsyncs nothing | CAUGHT, 13 failed | every writer's order test, the manifest's included |
| 7 shared helper swallows a failed fsync | CAUGHT, 4 failed | each writer's failure test and the manifest's |

My first version of 3b inserted a directory fsync before the rename and left the original one after
it, so it was not a move. That version was still caught (1 failed), but I redid it as a true move
before recording it. The row above is the redone mutant.

### Affected set and checks

`uv run scripts/affected_tests.py` selected **365 of 565 test files (64.6%)** from 12 changed files.
The script explained why: `_recorded_files.py` is imported by `fake_router`, which the root
`conftest.py` imports. The whole selection takes about six minutes, so this set is well over two
minutes. Under agreement 10 I did not hand it to the operator; I leave it to the pull request's
`ci` check. Instead I ran these, each under `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest … -m "not slow and not live"`:

| What | Result |
|---|---|
| The always-run list (`tests/architecture`, `tests/specs`, the CLI's `test_app.py`, `test_help_rendering.py`, `test_container_factories.py`), `tests/integrations/opencaselist`, `tests/integrations/models` and the ac2 test, `-n auto` | `1079 passed in 22.35s` |
| `packages/debate_core/tests/application/caselist` (path_parser, manifest, inbox_purge, the ac1 test), `-n auto` | `1659 passed in 106.33s` |
| `packages/debate_core/tests/application/test_caselist_parse.py` (reads the manifest's format) | `51 passed in 8.87s` |
| The node's command | `85 passed in 41.23s` |
| `uv run ruff format --check .` / `uv run ruff check .` | `1582 files already formatted` / `All checks passed!` |
| `uv run pyright` (the whole repository, as ci.yml runs it) | `0 errors, 0 warnings, 0 informations` |
| `uv run lint-imports` | `Contracts: 18 kept, 0 broken.` |
| `uv run python scripts/check_thin_handlers.py` | `OK: 67 CLI command and API route handlers within 25 statements` |
| `uv run scripts/validate_specs.py` | `OK: 492 files, 40 epics, 430 tasks, 22 releases` |

Before the report I compared this spec with `origin/dev`. The only difference is `status.phase`, so
the PM has not amended it. Dev moved by v1-e30-t28, an annual purge runbook, which touches none of
these files, so I did not sync.

## Files changed

* `packages/debate_core/src/debate_core/application/caselist/path_parser.py`: `.cmir` →
  `SourceFormat.CMIR`.
* `packages/debate_core/src/debate_core/application/durable_files.py` (new): `fsync_directory`,
  v1-e30-t23's helper moved out of `manifest.py`. Its docstring gives the order and names the four
  writers that end with it.
* `packages/debate_core/src/debate_core/application/caselist/manifest.py`: imports the helper and
  drops its own copy. No change in behaviour.
* `packages/debate_core/src/debate_core/application/caselist/inbox_purge.py`: the rewrite fsyncs the
  inbox directory after the rename. `purge_inbox`'s docstring now says that a failed directory
  fsync is the one failure that comes after the file has changed.
* `packages/debate_core/src/debate_core/integrations/opencaselist/token_store.py`:
  `FileTokenBackend.write` fsyncs the token directory after the rename.
* `packages/debate_core/src/debate_core/integrations/models/_recorded_files.py`: `write_pretty_json`
  fsyncs the partial file, renames it, then fsyncs the directory.
* `packages/debate_core/tests/application/caselist/test_a_cmir_file_is_imported_as_cmir.py` (ac1),
  `packages/debate_core/tests/application/test_rename_into_place_writers_fsync_their_directory.py`
  (ac2).
* `packages/debate_core/tests/application/caselist/write_cmir_manifest_files.py` and
  `check_an_older_build_reads_a_cmir_manifest.py`: the cross-build read. Neither is collected:
  their names are not test modules', as with t31's pair.
* The spec's Goal phase, and this report.

## Deviations from the spec

None. Two notes on how the criteria were run:

* I ran the node's command through `.venv/bin/python -m pytest` with agreement 10's `perl` alarm,
  not through `uv run pytest`. It is the same interpreter and the same environment.
* I did not run the affected set myself. Agreement 10 sends a set over two minutes to the pull
  request's `ci` check; see above.

## Decisions and assumptions

1. **The helper was moved, not copied.** The PM asked me to reuse t23's helper rather than write
   three copies. It was private to `manifest.py`, and the token store and the recordings writer
   would otherwise have to import a caselist module to reach it. So it lives in
   `debate_core.application.durable_files`, and the manifest writer imports it like the other
   three. The layers contract lets the integrations import the application layer, and
   `lint-imports` keeps all 18 contracts. The cost is a wider affected set, because `manifest.py`
   changed; most of the width comes from `_recorded_files.py` anyway, which the spec names.
2. **`caselist_sync.py` keeps its own `_fsync_directory`**, which is identical. Its writers already
   do the right thing, and an edit to that hub module would widen the selection further for no
   change in behaviour. It is listed under Follow-up work.
3. **Each writer calls the helper directly after its rename**, with no `replace_durably` wrapper.
   The order stays visible in each writer, and the PM's per-writer mutants have something to act on.
4. **Where a failed directory fsync is raised, and what is left.** In the token store it is raised
   after the `try` that removes the temporary file, because the rename has already happened. In the
   inbox rewrite it is raised inside the `try`, so the `finally` still removes the staging
   directory. `purge_inbox` lets the `OSError` through, as its docstring already said it lets an
   `OSError` through. The removal stops INCOMPLETE, and running it again finds the archive
   rewritten. For `write_pretty_json`, a failure leaves the `.partial` file behind, as a failed
   write always did.
5. **`.cmir` is matched without regard to case**, like every other extension (`suffix.lower()`).
   `.cmir.txt` and `.cmirx` stay `OTHER`. The test pins both.
6. **A file named `.cmir` is counted unsupported without its bytes being read.** With format
   `CMIR`, the parser refuses it on `is_parsable` before sniffing the content, as it does for
   `.doc` and `.pdf`. A real `.docx` renamed `.cmir` would therefore be counted `CMIR`, not
   parsed. Mapping by name is what the spec asks for. The reverse case, CardMirror bytes under a
   `.docx` name, is still named from its bytes (v1-e31-t15).
7. **The parser was not touched**, so the parser version stays `docx-7`.

## Operator follow-ups

None. Nothing in this task needs credentials, a device or a run over two minutes. CI's affected set
on the pull request covers the selection I did not run.

## Follow-up work

1. **Inbox deletions do not fsync the directory** (E30). `inbox_purge._carry_out` deletes a planned
   inbox file with `path.unlink()`, and the rewrite removes its staging directory, and neither
   fsyncs the inbox directory afterwards. After a power cut, a deleted archive that held removed
   bytes can come back, which is the same loss this task fixes for the rewrite. The spec names only
   the rename-into-place writers, so I left it. The fix would be `fsync_directory(path.parent)`
   after the unlink, with a recording test.
2. **`caselist_sync.py`'s private `_fsync_directory` duplicates the shared helper** (E30 or E34).
   It could import `durable_files.fsync_directory` the next time a task edits that module anyway.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
