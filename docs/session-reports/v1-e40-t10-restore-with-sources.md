# Session report: v1-e40-t10-restore-with-sources

| | |
|---|---|
| Task | `v1-e40-t10-restore-with-sources` — A restored working copy that brings the raw sources a hand prod publish needs |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t10-restore-with-sources.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t10-restore-with-sources.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t10-restore-with-sources` |
| Session status | COMPLETE |

## Summary

`caselist restore-run-state --with-sources` restores the run's working copy under the dev lock as
before. It then fetches, still under the lock and into the same directory, exactly the `raw/` objects
the restored manifests name. `--caselist` and a new repeatable `--snapshot` narrow that to some
manifests. Each source lands in a temporary file inside the copy and is SHA-256 checked. It is then
fsynced and renamed into place, and the directory is fsynced. A mismatch is deleted and refused, and
no further fetch starts after it. A named source missing from the bucket stops the command non-zero
with the count, unless the restored suppression list holds it; then it is skipped and counted. Before
the first fetch the command prints the count and bytes. It refuses when the copy's filesystem has less
free space than those bytes plus 1 GiB. The rule lives in a new module,
`debate_core/application/caselist/run_state_sources.py`. The runbook's "Until the promotion" section
now has the hand prod publish: which weeks, room, the restore with sources, a dry run and a publish
per caselist (each signing in to prod first), and deleting the copy. Every criterion passed, and the
Goal is `Succeeded`. Look first at Deviations 1 and 2 (suppressed sources are never fetched;
`--snapshot` works without `--caselist`) and at the IAM finding below (a missing key answers `403`).

**The IAM the restore runs under** (read in `infrastructure/modules/evidence_bucket/`, no change made).
The operator's dev profile is `debate-dev-evidence`, the permission set `DebateDevEvidenceOperator`
(`operator_access.tf`). Its `ReadAndPublishEvidenceObjects` grants `s3:GetObject` on
`<bucket>/*`, which includes `raw/`. `UseEvidenceKey` grants `kms:Decrypt` on the evidence key, and
the key policy's `EnableAccountIamPoliciesForThisKey` delegates to IAM (`main.tf`). The bucket policy
has no deny on reads. No grant is missing. One consequence was built in: `s3:ListBucket` is granted
only with an `s3:prefix` condition, and a `GetObject` carries no prefix, so S3 answers a read of a
missing key with `403`, not `404` (as `run_lock_object.py` documents). A refused read therefore counts
as a missing source only when a listing whose prefix is that one key shows nothing. A refusal of a key
that is there stays a refusal. Both cases are tested.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `restore-with-sources` — Restore with sources | Done | Its criterion passes; built test-first against a refuse-nothing skeleton, then 22 mutants |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — against moto, `--with-sources` fetches exactly the sources the restored manifests name, refuses a sha256 mismatch, writes nothing outside the directory, and keeps the command's refusals; tests shown failing first | PASS | `.venv/bin/python -m pytest packages/debate_core/tests/application/test_caselist_run_state_sources.py packages/debate_cli/tests/bucket_mode/test_restore_run_state.py -q -p no:randomly -n 0` against the skeleton → `18 failed, 39 passed in 96.75s`; against the implementation the same two files plus the smoke file → `41 passed` (CLI and smoke) and `22 passed` (core). Mutants below: 22 of 22 caught |
| ac2 — the runbook's hand prod publish restores with sources, publishes and deletes the copy; check_command_blocks and check_links pass | PASS | `docs/runbooks/caselist-cutover.md`, "Until the promotion: prod is published by hand". `uv run python scripts/check_command_blocks.py` → `OK: no # comments in 513 shell code blocks in 188 Markdown files`; `uv run python scripts/check_links.py` → `OK: 2726 relative links and anchors in 419 Markdown files`. Drafted only: no operator ran the blocks, as the PM asked |
| Node `restore-with-sources`: Caselist tests pass (`uv run pytest packages/debate_core/tests/application -k run_state`) | PASS | after the sync onto `t12` → `46 passed in 6.84s` |

### The red run

The skeleton was `run_state_sources.py` with every rule taken out. It did not refuse an unmatched
snapshot, filter suppressed or held digests, or check room. It fetched each source straight into place
with no landing file, no SHA-256 check and no fsync, and passed over a missing one. The CLI options
and wiring were as built. Against it, 18 tests failed and 39 passed. Every failure was an assertion or
a `DID NOT RAISE`, except two that failed on the skeleton's own exception, and both are the refusal
the test asks for not being made. Those two were the 403 test (`StoreAccessDenied` raised) and the
store-digest mismatch (`BlobIntegrityError` raised where `RestoredSourcesIncomplete` was expected).
The tests that passed are the ones a refuse-nothing fetch also satisfies: the happy path, the
selection, every existing refusal and the smoke checks.

A first skeleton had a bug of its own (a `del` inside a loop), which errored 9 more tests. Those were
discarded and the run redone. Three CLI tests then failed by subscripting a missing `error`, so they
now assert the exit code first and fail at an assertion (commit `c5341c0`).

### Mutants (agreement 8; the PM's four first)

Each was one exact text substitution, run against the core test file and
`packages/debate_cli/tests/bucket_mode/test_restore_run_state.py` (57 tests, `-n 6`, about 25 s each,
a hard stop of 110 s on the interpreter, `HYPOTHESIS_STORAGE_DIRECTORY` a fresh empty directory). No
test in these files is a Hypothesis property, so no example database could replay a catch. The file
was restored from git after each, and `git status` was clean after every batch.

| Mutant | Caught by |
|---|---|
| (1) the sha256 check skipped | 3 tests: the core mismatch test, after-a-mismatch-no-further-fetch, the CLI mismatch test |
| (2) the copy's sources written into the default data directory (the container's `_local_evidence()` for the copy) | 4 CLI tests, through the guard that every path is inside the copy |
| (2b) the same, with the directory guard pointed at the data directory too | 2 CLI tests (the copy lacks its sources); with that assertion removed, the new inode check alone fails: `nothing was renamed into the data directory, even over equal bytes` |
| (3) the sources taken from a listing of `raw/` | 18 tests, among them `test_no_listing_of_raw_is_asked…`: `assert [('list', 'raw/')] == []` |
| (4) the landing file of a mismatch kept | both mismatch tests: `no file in the copy keeps a mismatched byte` |
| a suppressed source fetched | both suppression cases |
| a held-only digest fetched | the held-path test |
| the room check off / its margin dropped / `<` for `<=` | the room tests, at one byte short and at exactly enough |
| a missing source counted as fetched | the core and the CLI planted-store tests, and the counts-only test |
| a refused read never missing / always missing | the two 403 tests |
| a mismatch not stopping further fetches | `test_after_a_mismatch_no_further_fetch_starts` |
| an unmatched snapshot not refused | the core and the CLI unmatched-snapshot tests |
| the store's own digest refusal re-raised, not counted | the mismatch test where the bucket records the named digest |
| the directory not fsynced / renamed before the landing file is fsynced | the flush-order test |
| the CLI's environment guard skipped with `--with-sources` | the local-mode and prod `--confirm-prod` tests, with sources |
| the CLI's directory refusal skipped with `--with-sources` | 6 directory-refusal cases, with sources |
| sources fetched without `--with-sources` | the existing copy test, through its new `not (copy / "blobs").exists()` |
| the selection ignoring `--caselist` | 4 core tests |

That is 22 mutants and 23 runs (2b was run again after the inode check was added). This is above
agreement 10's "about 20", to include the PM's four plus a variant of (2).

### Before the report (agreement 10)

The affected set is 191 of 548 files (`uv run scripts/affected_tests.py`, 17.4 s). It is wide because
`container.py`, which every command test reaches, gained the copy's wiring. I ran it in parts by what
it reaches, each with `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest … -m "not slow and
not live"`:

* the always-run list and the docs checks (`tests/architecture`, `tests/specs`, `test_app.py`,
  `test_help_rendering.py`, `tests/docs`, `test_check_command_blocks.py`, `test_docs_index.py`) →
  `551 passed in 61.26s`;
* `packages/debate_cli/tests/bucket_mode` (the directory of the CLI change) → `129 passed in 98.55s`;
* the 41 affected files under `packages/debate_core/tests/application` → `1155 passed in 25.20s`;
* the other 128 affected files (`packages/debate_cli/tests/commands`, the integrations, the smoke
  suite and others) → stopped by the 115 s alarm unfinished, with no orphaned worker left. So the
  whole affected set takes over two minutes, and under agreement 10 it is left to the pull request's
  `ci`, with no operator hand-off.

The whole-repo checks: `uv run --frozen ruff check .` → `All checks passed!` (after fixing one long
line it found); `uv run --frozen ruff format --check .` → `1536 files already formatted`;
`uv run --frozen pyright packages/debate_core packages/debate_cli tests/smoke` → `0 errors`;
`uv run --frozen lint-imports` → `Contracts: 18 kept, 0 broken.`;
`scripts/check_thin_handlers.py` → `OK: 67 … handlers within 25 statements`;
`scripts/docs_index.py --check-descriptions` → `All 55 indexed documents … have a description`;
`uv run scripts/validate_specs.py` → `OK: 480 files, 40 epics, 418 tasks, 22 releases`.

**The sync.** `v1-e40-t12` merged on dev while I worked (it changes `run_state.py`, `suppression.py`
and the suppression port). `scripts/task sync` rebased the branch cleanly, and everything above was
run after it.

## Files changed

* `packages/debate_core/src/debate_core/application/caselist/run_state_sources.py` (new): the rule.
  It plans from the copy's manifests (`read_local_manifest`, `held_only_digests`, `source_key`) and
  refuses a disk without room. Its checked fetch uses a landing file, SHA-256, fsync, rename, then a
  directory fsync. It also translates a missing key and its `403`, and holds the counts-only errors
  `RestoredSourcesIncomplete`, `TooLittleRoomForSources` and `SnapshotsNotRestored`.
* `…/caselist/run_state_restore.py`: `RunStateRestore` takes `sources_in`. `restore(…, sources=…,
  on_sources_planned=…)` reconciles the copy's suppression list, then plans, announces, checks room and
  fetches; `RestoredCopy.sources` carries the counts.
* `packages/debate_cli/src/debate_cli/container.py`: the copy's `RestoredSources`, built over the
  directory named (bucket, the copy's `LocalEvidence`, the directory).
* `…/commands/caselist_restore.py`: `--with-sources` and `--snapshot` (a usage error without
  `--with-sources`, or when it names no snapshot of a caselist restored; both before the lock). It
  adds the announcement, a note after a stop that the directory is not a copy to publish from, and
  `sources` in the JSON (`null` without the flag) and a table row.
* Tests: `packages/debate_core/tests/application/test_caselist_run_state_sources.py` (new, 22).
  `packages/debate_cli/tests/bucket_mode/test_restore_run_state.py` gains 7 tests, and each existing
  refusal is run with and without `--with-sources`. `tests/smoke/test_caselist_restore_run_state.py`:
  the data-directory refusal with the flag, `--help`, and `--snapshot` alone as a usage error.
* `docs/runbooks/caselist-cutover.md`: "Until the promotion: prod is published by hand".
* The spec's Goal phase, `Succeeded`.

## Deviations from the spec

1. **A source the suppression list holds is never fetched, present or not.** The PM's note spoke of a
   missing one: skipped and counted. I skip it whether the bucket holds it or not. The publisher
   never uploads such bytes, so a copy for a publish has no use for them, and fetching a removed
   file's bytes onto the Mac would go against the removal. Digests that only rows at a held path name
   are treated the same way, since the publisher holds those back too. Both are counted in
   `suppressed`. If the PM wants suppressed-but-present sources fetched, it is a one-line change.
2. **`--snapshot` works without `--caselist`.** It then selects that snapshot's manifests in every
   caselist restored. That is what lets the runbook restore one week of all the run's caselists in one
   block. With `--caselist`, it narrows to those caselists as the PM wrote.
3. **The room check comes after the restore.** The manifests that give the bytes exist only once the
   bundle is restored, so the parsed store (about 10 GB) is already on the disk when the sources'
   room is checked. The runbook's `df` block, asking 20 GB free, covers that part.

## Decisions and assumptions

* **The margin is 1 GiB** (`FREE_SPACE_MARGIN_BYTES`), for the blocks and directories of some tens of
  thousands of files and for anything else writing meanwhile. The bytes are the manifests'
  `byte_size`.
* **A missing source does not stop the other fetches**, so that the count is whole. A mismatch or any
  other failure does stop them: no new fetch starts, and those already running finish before the
  command returns, so nothing is written after it exits.
* **Every path is checked to be inside the copy** before anything is written, in addition to the
  wiring. Mutant (2) is caught by that check.
* **The CLI test of "nothing outside" compares inodes too.** The data directory already holds the same
  bytes, so a content comparison cannot see a source renamed into it.
* **The runbook publishes raw sources and manifests only**, with `caselist publish --snapshot` per
  caselist, a `--json` dry run whose counts the operator reads, then `--confirm-prod`. I left
  `caselist status` out of the success check: its `in_sync` includes caselist-wide removal residue,
  which could stop a good publish for an unrelated reason. The parsed store and the search index are
  not published to prod from the copy in this step; the section says the prod re-parse split out of
  `v1-e31-t31` will add its blocks there.

## Operator follow-ups

None for this task. The runbook's blocks are for the next hand prod publish and are not run here.

## Follow-up work

* **The prod re-parse split out of `v1-e31-t31`** can restore with `--with-sources` and no
  `--snapshot`, which fetches every source the manifests name.
* **The data-use policy** (version 1.18) already names a working copy restored on the operator's
  machine for a hand publish, kept for the length of the step. The runbook deletes it in its last
  block. No policy change is proposed.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
