# Session report: v1-e29-t05-evidence-sync-cli

| | |
|---|---|
| Task | `v1-e29-t05-evidence-sync-cli` — `debate-research store` sync commands |
| Spec | [`plan_specs/v1/e29-cloud-evidence-store/t05-evidence-sync-cli.yaml`](../../plan_specs/v1/e29-cloud-evidence-store/t05-evidence-sync-cli.yaml) |
| Epic / release | `v1-e29-cloud-evidence-store` / `v1.1` |
| Branch | `task/v1-e29-t05-evidence-sync-cli` |
| Session status | COMPLETE |

## Summary

`debate-research store sync | ls | get` moves evidence between the local evidence store and the
bucket `DEBATE_ENV` names, over the `EvidenceObjectStore` port on both sides. All of the deciding
is in `debate_core.application.evidence_sync`: it diffs the two stores, classifies each object,
verifies every transfer at the destination, and journals what landed so an interrupted run
resumes. The commands are thin — flags, guards, a Rich table and an exit code.

Three things are worth the PM's attention. **The sync covers two keyspaces, not one**: the local
store is two directories (`objects/` and `blobs/`) and the bucket is one namespace, so a
content-addressed blob needs the corpus prefix that says which archive it belongs to
(`--blob-prefix raw/caselist/hsld26`) and is refused rather than guessed at — see Deviations.
**The flags differ from the spec's wording** on the PM's instruction: dry run is the default
posture and `--apply` is what transfers, and the production guard is `--confirm-prod` rather than
`--yes`. **Two real defects were found and fixed on the way**, both of which ac4 turns on: a
missing SSO profile escaped as an untranslated `botocore.ProfileNotFound` (exit 70 and a
traceback), and the CLI ignored the `hint` the store errors carry for exactly this purpose.

Sizing the hsld26 backfill, which the PM asked for, is in [Operator follow-ups](#operator-follow-ups).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `storage-settings` | Done | `storage.s3` group (`bucket`, `region`, `aws_profile`, `multipart_threshold_mb`), dev and prod values in the committed profiles, `test` naming no bucket at all. |
| `sync-service` | Done | `EvidenceSyncService` over `SyncKeyspace` pairs; plan, execute, verify. Tested against the real filesystem and S3 adapters on moto, with S3 calls counted on botocore's event system. |
| `resume-journal` | Done | `SyncJournal`, append-only JSONL per environment, flushed and `fsync`ed per object. Resume proved by injecting an interruption mid-run. |
| `cli-commands` | Done | Typer sub-app wired through `ServiceContainer.evidence_sync`, the first service the container actually composes. |
| `smoke-and-docs` | Done | `tests/smoke/test_store_cli.py` (read-only, targeted by `STORE_SMOKE_ENV`) and `docs/guides/evidence-store-cli.md`, both indexed. |

## Acceptance criteria

All commands run from the task worktree.

### Goal criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — dry run prints counts and bytes and performs no `PutObject`/`GetObject`; a real sync uploads exactly the planned objects; a repeat reports 0 new, 0 changed | PASS | `uv run pytest packages/debate_core/tests/application/test_evidence_sync.py` → `46 passed`. `TestPlanning::test_a_dry_run_moves_nothing` asserts `PutObject`/`GetObject`/`DeleteObject` are absent from the botocore call log; `TestExecuting::test_a_sync_uploads_exactly_what_the_plan_named` asserts the planned keys equal the bucket's keys; `…test_a_second_sync_of_an_unchanged_store_reports_nothing_to_do` asserts `new == 0, changed == 0`. End to end through the command: `uv run pytest packages/debate_cli/tests/commands/test_store.py` → `36 passed`, incl. `test_an_apply_uploads_exactly_what_was_planned_and_a_repeat_does_nothing`. |
| **ac2** — every upload verified against the S3 head metadata, every download re-hashed before its atomic rename; a mismatch fails the object and the command exits non-zero | PASS | `TestVerification` (5 tests) in `test_evidence_sync.py`: the upload path heads the store separately after `put_file` and fails the object when the head disagrees or records no digest; the download path fails when the landed bytes contradict either the recorded digest or the digest the key states, and asserts no file was left in the store. Non-zero exit: `test_store.py::TestFailures::test_a_blob_that_differs_from_the_bucket_fails_the_command` → `exit_code == 1`. |
| **ac3** — a sync interrupted after N objects resumes from its journal and transfers only the rest, proved by a test that injects a failure mid-run | PASS | `uv run pytest packages/debate_core/tests/application/test_evidence_sync.py -k resume` → `3 passed`. `RemoteStoreThatStopsAfter(after=2)` kills a 4-object run; the re-run plans `c` and `d` as new, `a` and `b` as `skipped (journaled at this digest)`, and makes **zero** `HeadObject` calls doing it. The other two assert the journal does *not* excuse an object the bucket no longer holds, or one that changed locally. |
| **ac4** — dev and prod resolve different buckets and SSO profiles; a prod push without the confirmation flag is refused; an expired SSO session gives a one-line hint, not a traceback | PASS | `uv run pytest packages/debate_core/tests/application/test_settings.py -k s3` → `8 passed` (incl. `test_the_committed_profiles_name_the_buckets_terraform_builds`, which reads the suffix back out of `infrastructure/envs/<env>/variables.tf`). Through the CLI: `TestEnvironments` (7 tests) → different buckets, `CONFIRMATION_REQUIRED` with nothing written to prod, `test` refused. Expiry: `test_an_expired_sso_session_is_one_line_and_not_a_traceback` asserts `aws sso login --profile debate-dev-evidence` is in stderr and `Traceback` is not. **Flag name is `--confirm-prod`, not `--yes`** — see Deviations. |
| **ac5** — `tests/smoke/` covers `store ls` and `store sync --dry-run`; `docs/guides/evidence-store-cli.md` documents usage, environments and resume | PASS | `tests/smoke/test_store_cli.py` exists and matches `--dry-run`; `uv run pytest tests/smoke/test_store_cli.py -m dev -rs` → `2 skipped, 2 deselected` with `STORE_SMOKE_ENV is not set`, i.e. collected and correctly inert off-target. `docs/guides/evidence-store-cli.md` matches `DEBATE_ENV` (7 occurrences) and has sections on environments, the production guard, verification and Resuming. Both indexed in `docs/README.md` and `tests/smoke/README.md`. |

### Node criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| `storage-settings` — Storage settings resolve per `DEBATE_ENV` | PASS | `uv run pytest packages/debate_core/tests/application/test_settings.py -k s3` → `8 passed` |
| `sync-service` — Sync planning, execution and checksum verification tests pass | PASS | `uv run pytest packages/debate_core/tests/application/test_evidence_sync.py` → `46 passed` |
| `resume-journal` — Interrupted sync resumes from the journal | PASS | `uv run pytest packages/debate_core/tests/application/test_evidence_sync.py -k resume` → `3 passed` |
| `cli-commands` — store command tests pass under moto | PASS | `uv run pytest packages/debate_cli/tests/commands/test_store.py` → `36 passed` |
| `cli-commands` — store sync help renders | PASS | `uv run debate-research store sync --help` → exit 0, usage with `--prefix`, `--blob-prefix`, `--pull`, `--apply/--dry-run` (`[default: dry-run]`), `--confirm-prod` |
| `smoke-and-docs` — Smoke check covers store sync dry-run (`tests/smoke/test_store_cli.py` matches `--dry-run`) | PASS | file exists; `grep -c -- "--dry-run"` → `3` |
| `smoke-and-docs` — Guide documents `DEBATE_ENV` (`docs/guides/evidence-store-cli.md`) | PASS | file exists; `grep -c "DEBATE_ENV"` → `7` |
| `smoke-and-docs` — Import boundaries hold | PASS | `uv run lint-imports` → `Contracts: 2 kept, 0 broken` |

### Whole-repository gates

| Gate | Status | Evidence |
|---|---|---|
| Full test suite | PASS | `uv run pytest` → `1203 passed in 20.77s` |
| Format | PASS | `uv run ruff format --check packages` → `105 files already formatted` |
| Lint | PASS | `uv run ruff check packages` → `All checks passed!` |
| Types | PASS | `uv run pyright packages` → `0 errors, 0 warnings, 0 informations` |
| Spec validation | PASS | `uv run scripts/validate_specs.py` → `OK: 281 files, 38 epics, 223 tasks, 20 releases` |

CI budget: the suite is 21 seconds and entirely offline (moto and the filesystem; no test opens a
socket). The four smoke checks are `live`-marked and excluded from the default run.

## Files changed

**`packages/debate_core/src/debate_core/application/evidence_sync.py`** (new) — the whole of the
sync: `SyncKeyspace`, `SyncPlan`/`SyncReport`, `SyncJournal` and `EvidenceSyncService`.

**`packages/debate_core/src/debate_core/application/settings.py`** — `S3StorageSettings` under
`storage.s3`, and the dev/prod bucket coordinates in `BUILTIN_PROFILES` so an installed build with
no profile files still resolves them.

**`config/profiles/{dev,prod,test}.toml`** — the `[storage.s3]` block for dev and prod, taken from
each environment root's Terraform outputs; a note in `test.toml` about why it has none.

**`packages/debate_core/src/debate_core/integrations/local/fs_object_store.py`** — an optional
`subdirectory` argument, so the blob tree can be listed and transferred through the same port as
the object tree. Additive; the default is unchanged.

**`packages/debate_core/src/debate_core/integrations/s3/client.py`** — `build_s3_client` now
translates what session construction raises (defect fix, below).

**`packages/debate_cli/src/debate_cli/commands/store.py`** (new) and `commands/__init__.py` — the
three commands and their registration.

**`packages/debate_cli/src/debate_cli/container.py`** — `evidence_sync(...)`, the first service the
container composes, with the AWS import inside the factory because boto3 is an optional dependency.

**`packages/debate_cli/src/debate_cli/output.py`** — `CommandFailure.from_exception` promotes an
exception's own `hint` (defect fix, below).

**`pyproject.toml`** — the AWS-SDK import contract split in two (deviation, below).

**Tests** — `test_evidence_sync.py` (46), `test_store.py` (36), 8 added to `test_settings.py`, one
assertion updated in `test_app.py` (`doctor` now reports one wired service instead of none).

**Docs** — `docs/guides/evidence-store-cli.md` (new), `tests/smoke/test_store_cli.py` (new), index
lines in `docs/README.md` and `tests/smoke/README.md`.

## Deviations from the spec

1. **`--confirm-prod`, not `--yes`** (spec description and constraint; ac4). On the PM's
   instruction, to match the confirmation convention used elsewhere so the operator learns one
   word. Everything the criterion asks for holds under the new name.

2. **Dry run is the default, and `--apply` transfers** (spec has `store sync [--dry-run]`). Also
   the PM's instruction: "dry run is the default posture … uploading happens only when asked."
   `--dry-run` is still accepted and is simply the default half of `--apply/--dry-run`, so every
   command line the spec writes still works and still means what it says.

3. **The sync has a second keyspace, and blobs need `--blob-prefix`.** The spec describes "a sync
   between two `EvidenceObjectStore` adapters", diffing by key — which is exactly right for named
   objects, where the local key and the bucket key are the same string. It does not hold for
   content-addressed blobs, for two reasons the spec could not have known:

   * `FsEvidenceObjectStore` is rooted at `<data_dir>/objects/` and cannot see
     `<data_dir>/blobs/`, so the local blob tree was not reachable through the port at all. Fixed
     with an additive `subdirectory` argument.
   * A local blob key is `sha256/ab/cd/<digest>` and its bucket key is
     `<corpus prefix>/sha256/ab/cd/<digest>`. Nothing on disk records which corpus a blob came
     from, so the prefix has to be an input. `store sync` refuses (`UNSYNCABLE_KEYSPACE`) when
     there are blobs to move and no `--blob-prefix`, naming `raw/caselist/hsld26` and
     `raw/openev/2026` as examples, rather than filing a season's disclosures under a guess.

   This is the only structural departure and it is the one worth a spec amendment. The
   alternative — leaving blobs out of `store sync` — would have left the corpus with no way into
   the bucket and made the backfill (`v1-e30-t06`) sizing question unanswerable.

4. **Two files outside the spec's stated packages were changed**, both to fix defects that ac4
   depends on:
   * `debate_core/integrations/s3/client.py`: `boto3.session.Session(profile_name=…)` resolves the
     profile *eagerly* and raises `botocore.exceptions.ProfileNotFound`, which was escaping
     untranslated. An operator who had not yet run `aws configure sso` got exit 70 and a full
     traceback — precisely what ac4 forbids — even though `integrations/s3/errors.py` already had
     the right translation and hint ready. Session construction is now wrapped like every other
     call, so nothing botocore raises leaves that package.
   * `debate_cli/output.py`: `CommandFailure.from_exception` discarded the `hint` that
     `StoreCredentialsExpired` and `StoreAccessDenied` carry. `errors.py` says in as many words
     that the adapter fills that field in "so the CLI prints one line (`v1-e29-t05` ac4)"; the CLI
     was not reading it. It is now promoted to the envelope's `hint` and removed from `details`
     so it renders once.

5. **`pyproject.toml`'s AWS-SDK import contract is now two contracts.** The original forbade
   `debate_cli` from reaching boto3 *including indirectly*, which makes it impossible for the
   composition root to construct the S3 adapter — the chain `debate_cli.container →
   debate_core.integrations.s3 → boto3` is the design, not a leak. The domain, the application
   layer, `integrations.local`, `debate_api` and `debate_workers` keep the strict form (not even
   indirectly); `debate_cli` is held to the direct form, so a `boto3.client(...)` in a command or
   a `botocore` exception caught outside the adapter is still a broken build. `v1-e02-t06` owns
   this section and the comment says so.

## Decisions and assumptions

* **The bucket cannot be overridden by a flag.** `DEBATE_ENV` alone decides, because a `--bucket`
  option is how a dev run eventually writes into prod. `DEBATE_STORAGE__S3__BUCKET` still works, as
  every setting does, which is what the CLI tests use.
* **`test` names no bucket** rather than pointing at a moto one, as the spec's node description
  suggested. A committed profile naming a moto bucket would be a real-looking bucket name in a
  real-looking place; refusing outright is the stronger guarantee, and the CLI tests get their moto
  bucket by writing their own profile directory — which is also how they exercise the dev/prod
  split without an AWS account.
* **No KMS key in settings.** Each bucket's *default* encryption is already the environment's
  customer-managed key (`v1-e29-t03`), so an upload that names no key is encrypted with the right
  one, and a key ARN would put the account id in a committed file. A test asserts no committed
  profile contains `arn:aws` or names a key.
* **`would_delete` is reported and never acted on**, per the PM: "if the sync ever wants to delete
  a remote object, it reports it and does not do it." A remote-only object gets its own action and
  byte total in the summary.
* **A content-addressed key whose two sides differ is `mismatched`**, not `changed`: it is never
  written over and it fails the run. That case means something already went wrong, and overwriting
  would destroy the evidence that it did.
* **Credentials and access failures abort the run; everything else is collected.** 2,300 copies of
  "your SSO session expired" is not a report, but one unreadable object should not abandon 2,299
  good ones.
* **The journal is never on its own a reason to skip.** An object is skipped only when it is both
  present in this run's listing *and* journaled at the digest this run would send, so a bucket
  someone emptied is re-filled whatever the journal says.
* **The journal's timestamp is the one clock read not injected through the `Clock` port** (it is
  injectable, and the tests inject `FixedClock`; it just has a default). A journal timestamp is
  operational bookkeeping, not evidence provenance, and there is no `SystemClock` adapter in the
  repository yet for the composition root to pass.
* **Transfers are serial.** One object at a time, in plan order, so an interrupted run and its
  resume walk the store the same way. See Follow-up work for what that costs at corpus scale.

## Operator follow-ups

### Sizing the first real sync of the hsld26 corpus

Measured against moto with a 250-blob corpus, then extrapolated to the PM's figures (~2,300 `.docx`
files, ~300 MB). The call profile is exact; the wall-clock is an estimate.

| | Requests | Notes |
|---|---|---|
| Dry run (plan) | ~11 `ListObjectsV2`, **0** `HeadObject` | 8 documented prefixes for the object tree plus the blob prefix, ~3 pages at 1,000 keys each. Nothing is headed because every object is new. |
| Apply | 2,300 `PutObject` + 4,600 `HeadObject` | 3.00 requests per object, measured. All single-part: the average file is ~130 KB against a 64 MiB multipart threshold. |
| Repeat sync, unchanged | ~11 `ListObjectsV2`, **0** `HeadObject`, **0** `PutObject` | Measured: a whole corpus re-plans for the cost of the listings alone. |

Cost is negligible — about **$0.02** in request charges, plus one KMS `GenerateDataKey` per upload
(~$0.007) and ~$0.007/month to store 300 MB. **Wall clock is the real cost: roughly 6–12 minutes**,
and it is latency-bound rather than bandwidth-bound — 6,900 serial round trips at 40–60 ms dominate
the ~2 minutes the 300 MB itself takes on a home connection. That is well over the two-minute rule,
so it is an operator step:

**Operator command** (expected runtime ~6–12 min, dev)
Where: your Mac, in the task worktree `debate-intelligence-worktrees/v1-e29-t05-evidence-sync-cli`
```bash
aws sso login --profile debate-dev-evidence
DEBATE_ENV=dev uv run debate-research store sync --blob-prefix raw/caselist/hsld26
DEBATE_ENV=dev uv run debate-research --verbose store sync \
  --blob-prefix raw/caselist/hsld26 --apply
```
Run the first (dry) command and check the counts against what is on disk before running the
second. Success looks like `N object(s) transferred, … each verified at the destination.` and exit
0. If the SSO session expires part-way, log in again and re-run the same command: it resumes from
the journal and re-transfers nothing. Paste the summary table back into the session.

This is only worth running once `v1-e30` has put the corpus in the local store; **nothing needs it
to merge this task**, and the bulk load proper is `v1-e30-t06`'s to schedule.

### Smoke checks against a real bucket

Cannot be run here: they need an applied environment and an SSO session, and the acceptance
criterion for them is `artifact_exists`, which passed. Once `v1-e29-t03` has been applied:

**Operator command** (expected runtime <1 min, read-only)
Where: your Mac, in the task worktree
```bash
aws sso login --profile debate-dev-evidence
STORE_SMOKE_ENV=dev uv run pytest tests/smoke/test_store_cli.py -m dev
```
Success looks like `2 passed`. Both checks are read-only, so the same command with `prod` is safe.

## Follow-up work

* **Two `HeadObject` calls per upload instead of one** (`v1-e29-t04` or a small follow-up).
  `S3EvidenceObjectStore.put_file` already heads the object to get its version id, then returns
  the digest *it* computed rather than the one the head recorded, so the sync has to head again to
  satisfy ac2. Having `put_file` also return the recorded digest would take a third off the
  backfill's request count and a couple of minutes off its wall clock. Not changed here because it
  alters t04's documented contract.
* **Concurrency for the backfill** (`v1-e30-t06`, or a spec change here). Transfers are serial, so
  a 2,300-object sync is 6,900 sequential round trips. A bounded concurrent executor would cut
  that to a couple of minutes; it is out of this spec and the resume behaviour would need a second
  look (the journal is append-only and would be fine; the "interrupted run is a prefix of a
  finished one" property would not be).
* **`v1-e30-t05-caselist-publish` still specifies the older, flatter key form**
  (`raw/<caselist>/<sha256>.<ext>`), which `docs/architecture/evidence-store-layout.md` already
  flags for the PM. This task builds the layout document's form. Nothing is in either bucket yet,
  so it remains a spec edit rather than a migration.
* **`SystemClock` has no implementation** anywhere in the repository, though `container.py`'s
  docstring, `integrations/local/__init__.py` and `packages/debate_core/README.md` all use it as
  the worked example. Whichever task first needs an injected clock in a real run should add it.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
