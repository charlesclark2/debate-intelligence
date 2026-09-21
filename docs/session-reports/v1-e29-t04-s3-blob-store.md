# Session report: v1-e29-t04-s3-blob-store

| | |
|---|---|
| Task | `v1-e29-t04-s3-blob-store` — S3 blob-store adapter |
| Spec | [`plan_specs/v1/e29-cloud-evidence-store/t04-s3-blob-store.yaml`](../../plan_specs/v1/e29-cloud-evidence-store/t04-s3-blob-store.yaml) |
| Epic / release | `v1-e29-cloud-evidence-store` / `v1.1` |
| Branch | `task/v1-e29-t04-s3-blob-store` |
| Session status | COMPLETE |

## Summary

`debate_core` can now read and write the evidence bucket, with boto3 confined to one adapter package.
`S3SnapshotStore` satisfies the existing `SnapshotStore` port over content-addressed, write-once keys
`<prefix>/sha256/<ab>/<cd>/<sha256>` — the same layout as `FsSnapshotStore` — and passes the E02
contract suite against moto unchanged. A new, deliberately smaller `EvidenceObjectStore` port covers the
evidence that is named rather than hashed (`manifests/*.jsonl`, `reports/*`), with S3 and filesystem
adapters that both pass one shared contract, which is what lets `t05` be a single diff over two stores.

Three things the PM may want to look at first. **The import boundary had no home yet:** `[tool.importlinter]`
did not exist in this repository and `v1-e02-t06-import-boundary-guard` is still `Pending`, so ac5 forced
this task to bootstrap the configuration and add `import-linter` to the dev group. It adds only the one
contract its own criterion names and says in a comment that t06 owns the section and extends it — the PM
should confirm that division. **A new error family:** `StoreError`, `StoreAccessDenied`,
`StoreCredentialsExpired` and `StoreUnavailable` went into `application/errors.py`, which the spec's
`constraints.packages` list does not name (see Deviations). **One judgement call the spec left open:** a
listing never states a digest, in either implementation, because promising digests would mean one
`HeadObject` per object and a caller walking 60,000 keys would pay for it without asking.

No live AWS call happens anywhere in the suite. The whole repository suite is 1,111 tests in ~22 s, so the
CI budget is untouched, and nothing here is marked `slow` or `live`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `object-port-and-errors` | Complete | `EvidenceObjectStore`, `ObjectInfo`, `validate_object_key` (which is also the filesystem adapter's traversal guard), and the botocore→`application.errors` translation table. `BlobIntegrityError` already existed from E02 and was reused rather than redeclared. |
| `snapshot-adapter` | Complete | `S3SnapshotStore` bound to `SnapshotStoreContract` with a moto-backed `make_adapter`, plus the adapter-only half: key layout, head-before-put idempotency, checksums, metadata, error mapping. |
| `multipart` | Complete | `put_file`/`get_file` on the snapshot store, driven by `TransferConfig`. Tested with an 11 MiB fixture against a 5 MiB part size: three parts, the last one partial. |
| `named-object-adapters` | Complete | `S3EvidenceObjectStore` and `FsEvidenceObjectStore`, one shared contract module, plus each adapter's own tests. |
| `boundaries-and-types` | Complete | `aws` extra on `debate-core`; the import-linter contract; pyright clean; full offline adapter suite green. |

## Acceptance criteria

All commands were run from the task worktree. `uv run` is shown as the spec writes it.

### Goal criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: `S3SnapshotStore` passes the shared `SnapshotStore` contract under moto, including dedupe, immutability and `NotFound` | PASS | `uv run pytest packages/debate_core/tests/integrations/s3/test_s3_snapshot_store.py` → `29 passed`. 12 of those are `TestS3SnapshotStore`, the binding of `debate_core.testing.contracts.SnapshotStoreContract` — every test in the suite, including `test_putting_identical_bytes_twice_stores_one_blob`, `test_getting_a_key_nothing_was_stored_under_raises_not_found` and `test_a_blob_whose_bytes_no_longer_match_its_key_is_refused`, which the binding turns on by supplying `corrupt_blob`. Not one contract test was skipped or adapted. |
| ac2: a second put issues no `PutObject` and leaves one version; mismatched bytes for an existing key raise `BlobIntegrityError`; a read that does not hash to its key raises `BlobIntegrityError` | PASS | `uv run pytest packages/debate_core/tests/integrations/s3 -k "second_put or disagree or no_longer_match or did_not_write"` → `6 passed`. `test_a_second_put_of_identical_bytes_issues_no_put_object` counts `PutObject` through a botocore `before-call` hook (1 after two puts); `test_a_second_put_of_identical_bytes_leaves_one_version` reads `list_object_versions` (1 version); `test_bytes_that_disagree_with_a_stored_objects_recorded_digest_are_refused` asserts `BlobIntegrityError` with `actual_sha256`; the read case is both the contract's corruption test and `test_an_object_this_store_did_not_write_is_left_alone`. |
| ac3: files above the threshold are uploaded in parts and read back byte-identical, with the full-object sha256 in object metadata | PASS | `uv run pytest packages/debate_core/tests/integrations/s3/test_s3_multipart_upload.py -k "uploaded_in_parts or byte_identical or metadata"` → `3 passed`; whole module `12 passed`. The parts are counted from `CreateMultipartUpload`/`UploadPart`/`CompleteMultipartUpload` (1/3/1 for 11 MiB at 5 MiB), the round trip compares the files byte for byte, and the metadata test asserts `Metadata["sha256"] == sha256(file)`. |
| ac4: `EvidenceObjectStore` has S3 and filesystem adapters that both pass one shared contract (list by prefix, head with size and sha256, round trip, `NotFound`) | PASS | `uv run pytest packages/debate_core/tests/contracts -k evidence_object_store` → `42 passed` — 21 rules × 2 bindings, from one contract module, with no per-adapter exceptions. |
| ac5: `uv run lint-imports` passes with a contract forbidding boto3/botocore outside `debate_core.integrations.s3`, and pyright reports no errors for `debate_core` | PASS | `uv run lint-imports` → `Contracts: 1 kept, 0 broken` (exit 0). Checked the other way too: with `import boto3` appended to `debate_core/application/errors.py`, → `Contracts: 0 kept, 1 broken`, exit 1, naming `debate_core.domain`, `debate_core.application`, `debate_core.testing` and `debate_core.integrations.local`; the file was restored immediately (`git status` clean). `uv run pyright packages/debate_core` → `0 errors, 0 warnings, 0 informations`. |

### Node criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| `object-port-and-errors` — artifact: `application/ports/evidence_store.py` contains `class EvidenceObjectStore(Protocol)` | PASS | File exists; `grep -c "class EvidenceObjectStore(Protocol)"` → `1`. |
| `snapshot-adapter` — `uv run pytest packages/debate_core/tests/integrations/s3/test_s3_snapshot_store.py` | PASS | `29 passed in 2.82s`. |
| `multipart` — `uv run pytest packages/debate_core/tests/integrations/s3 -k multipart` | PASS | `12 passed in 3.12s`. |
| `named-object-adapters` — `uv run pytest packages/debate_core/tests/contracts -k evidence_object_store` | PASS | `42 passed in 3.40s`. |
| `boundaries-and-types` — `uv run lint-imports` | PASS | `Contracts: 1 kept, 0 broken`, exit 0. |
| `boundaries-and-types` — `uv run pyright packages/debate_core` | PASS | `0 errors, 0 warnings, 0 informations`. |
| `boundaries-and-types` — `uv run pytest packages/debate_core/tests/integrations/s3` | PASS | `78 passed in 4.81s`, offline throughout. |

### Repository gates

| Check | Status | Evidence |
|---|---|---|
| Whole test suite | PASS | `uv run pytest` → `1109 passed in 24.88s`, then `1111 passed in 22.18s` after the conformance-test addition. 98% total coverage. |
| Lint | PASS | `uv run ruff check .` → `All checks passed!` |
| Format | PASS | `uv run ruff format --check` over every tracked `.py` file in the repository → clean, nothing left to reformat. (Seven of this task's own files needed formatting; the first pass caught four, and a repo-wide re-check found the three that had already been committed.) |
| Specs | PASS | `uv run scripts/validate_specs.py` → `OK: 281 files, 38 epics, 223 tasks, 20 releases`. Goal `status.phase` is `Succeeded`; the Plan's phase is left `Pending`, matching every other completed task in `plan_specs/`. |

## Files changed

**The ports (`packages/debate_core/src/debate_core/application/`)**

* `ports/evidence_store.py` — new. `EvidenceObjectStore`, `ObjectInfo` (key, size, sha256, version_id),
  `OBJECT_KEY_PATTERN`, `MAX_OBJECT_KEY_BYTES` and `validate_object_key`. The key rules live in the port
  because they are the filesystem adapter's containment guard and both implementations need the same one.
* `errors.py` — `StoreError` and its three subclasses, so botocore's failures have somewhere to land.
* `ports/__init__.py` — re-exports, and the port table gains a row.

**The S3 adapters (`packages/debate_core/src/debate_core/integrations/s3/`)** — all new, and the only place
boto3 is imported.

* `__init__.py` — the package's write-up, the re-exports, and a `find_spec` check that turns a missing
  optional dependency into the command that installs it.
* `client.py` — `build_s3_client(region=…, profile=…)` on botocore's standard credential chain, the
  multipart defaults (64 MiB threshold, 16 MiB parts) and `build_transfer_config`, which refuses a part
  size below S3's 5 MiB minimum at construction rather than halfway through an upload.
* `errors.py` — the translation table, `S3Call` (the only facts a message is built from, none of which can
  be a secret), and `mapped_s3_errors`, which every S3 call in the package runs inside.
* `snapshot_store.py` — `S3SnapshotStore`: keys, idempotency, checksums, verification, `put_file`/`get_file`.
* `object_store.py` — `S3EvidenceObjectStore`: paginated listing, head, atomic transfers.

**The local adapters (`packages/debate_core/src/debate_core/integrations/`)**

* `file_streaming.py` — new, and a sibling of the two adapter packages rather than inside either:
  `sha256_of_file` (chunked) and `atomic_replacement` (write a temporary file, verify, rename), wanted by
  all three file-moving adapters.
* `local/fs_object_store.py` — new. `FsEvidenceObjectStore` over `<data_dir>/objects/`.
* `local/__init__.py` — re-exports and the data-directory diagram.

**The contract suite (`packages/debate_core/src/debate_core/testing/contracts/`)**

* `evidence_object_store.py` — new; the fifth contract class, and the first whose two bindings are a cloud
  service and a local directory.
* `__init__.py`, `README.md` — the new contract, and a note that a cloud binding opts in against a mock.

**Tests (`packages/debate_core/tests/`)**

* `conftest.py` — new. The moto fixtures, at the package-test root because both `integrations/s3/` and
  `contracts/` need the same bucket.
* `integrations/s3/` — new: `test_s3_snapshot_store.py` (the contract binding plus the adapter-only half),
  `test_s3_multipart_upload.py`, `test_s3_evidence_object_store.py`, `test_s3_error_mapping.py` (the
  translation table one response code at a time, no bucket needed).
* `contracts/test_evidence_object_store_contract.py` — new; the two bindings.
* `integrations/local/test_fs_object_store.py` — new; layout, containment, leftovers, atomicity.
* `application/test_port_conformance.py` — the new port module joins the forbidden-imports check, and the
  new port gets its own Protocol-shape test.

**Configuration and documentation**

* `packages/debate_core/pyproject.toml` — the `aws` extra (`boto3>=1.35`).
* `pyproject.toml` — `boto3`, `boto3-stubs[s3]`, `moto[s3]` and `import-linter` in the dev group, and the
  new `[tool.importlinter]` section.
* `uv.lock` — regenerated by `uv sync --all-packages --all-extras`.
* `packages/debate_core/README.md` — an `integrations/s3/` section, the `aws` extra, and rows for the new
  modules and errors.
* `plan_specs/…/t04-s3-blob-store.yaml` — Goal `status.phase` → `Succeeded`.

## Deviations from the spec

**1. Three files outside `constraints.packages`.** The spec lists `debate_core.integrations.s3`,
`debate_core.application.ports` and `debate_core.integrations.local`. Three things landed outside that list,
each because the spec's own text asks for it:

* `debate_core.application.errors` — the node asks for `StoreAccessDenied` and `StoreCredentialsExpired`,
  and `errors.py` is where the codebase states, emphatically, that every port error lives ("Every port in
  `debate_core.application.ports` raises from this hierarchy and nothing else"). Declaring port errors in a
  ports module instead would have broken that rule to satisfy a package list.
* `debate_core.integrations.file_streaming` — chunked hashing and atomic replacement are needed by the S3
  snapshot store and both object stores. Putting them in `integrations.s3` would have made the local
  adapter import the S3 package; putting them in `integrations.local` would have done the reverse. A
  sibling module inside `debate_core.integrations` is the only placement that couples neither.
* `debate_core.testing.contracts` — named in the `named-object-adapters` node's own `outputs`, so the list
  is indicative rather than exhaustive; noted here for completeness.

**2. This task bootstrapped `[tool.importlinter]`.** ac5 requires `uv run lint-imports` to pass, and neither
the configuration nor the `import-linter` dependency existed: `v1-e02-t06-import-boundary-guard`, which owns
them, is still `Pending`. The `boundaries-and-types` node does say to add the contract, so this is the spec
working as intended — but it means this task created the section, added the dev dependency, and had to
choose the shape. It adds **only** the AWS contract, with a comment saying t06 owns the section and extends
it with the rest (no httpx/typer/fastapi in the domain and application layers, the layers contract, the CI
job). `include_external_packages = true` is required for any contract that forbids a module from outside
the repository, so t06 inherits that too. **There is still no CI workflow in this repository** (`.github/`
does not exist; `v1-e01-t04-ci-pipeline` is `Pending`), so nothing runs `lint-imports` automatically yet.

Nothing in the spec's `forbidden` list was done: no boto3 in the domain or application layers, no botocore
type in a port signature, no overwrite or delete of a content-addressed object, no live AWS call in any
test, and nothing logs a credential, a token or an object's contents.

## Decisions and assumptions

**A listing never states a digest.** `list_objects` returns `sha256=None` from *both* adapters, and `head`
is what states a digest. S3's `ListObjectsV2` does not return checksums, so a listing that promised digests
would mean one `HeadObject` per object, and the local store would have to hash every file — a caller walking
60,000 keys would pay for it without having asked. Making the rule identical in both implementations is
what keeps a sync plan's cost visible in the code that chose it. `t05` will therefore `head` the objects it
is considering, which is one request per candidate rather than one per key in the store.

**`head` may answer `sha256=None`.** An object no adapter here wrote has no recorded digest, and the honest
answer is "you will have to read it to find out" rather than an error or a guess. The port documents it and
suggests `t05` treat such an object as changed.

**A `put` skips an object that records no digest, rather than overwriting it.** Replacing evidence this store
cannot vouch for with evidence it can — silently, in a versioned bucket — would be the wrong resolution of an
ambiguity. The mismatch is not ignored: `get` re-hashes every read and refuses the bytes.

**The full-object digest goes in object metadata, not in S3's `ChecksumSHA256`.** For a multipart object,
`ChecksumSHA256` is a composite of the part digests with a `-N` suffix, so it is not the SHA-256 of the file
and cannot be compared with a blob key. Uploads still set `ChecksumAlgorithm="SHA256"` so S3 rejects a part
that arrived damaged, and the metadata entry is what a `HeadObject` can compare.

**Blocking S3 calls run in a worker thread** (`asyncio.to_thread`), unlike the local adapters, which do their
I/O inline. A network round trip inside the event loop the CLI, API and workers share is the one case where
the thread hop pays for itself. `asyncio` specifically, because `debate_core.testing.contracts.harness`
pins the backend to asyncio and says why.

**`kms_key_id` is optional and defaults to the bucket's own encryption.** `v1-e29-t03` already configures
the bucket's default encryption with the environment's customer-managed key, so an upload inherits it
without the adapter naming it. A caller that wants the request to state the key passes the environment's
`evidence_kms_key_arn`; there is a test that it reaches the object.

**`prefix` is required on `S3SnapshotStore`, with no default.** `docs/architecture/evidence-store-layout.md`
is the contract for which prefixes exist and says a new one is a change to that document. The adapter
therefore makes the caller choose rather than inventing a default the layout document does not list.

**Bucket names.** No bucket name is compiled in anywhere, per the PM's note: the constructors take it, and
the docstrings say it comes from the environment root's `evidence_bucket_name` output. The tests use
`debate-test-evidence-moto`, which is obviously not a real bucket.

**Two narrow `pyright: ignore[reportUnknownMemberType]` comments**, on `Session.client("s3")` in `client.py`
and `boto3.client("s3")` in the test conftest. boto3-stubs types `client` with one overload per AWS service
and only the installed service stubs (`s3`) resolve, so strict mode reports the symbol as partly unknown
even though these calls resolve to `S3Client`. Narrowed to those two lines rather than turning the rule off
for the package.

## Operator follow-ups

Nothing is required to merge this task. Two things are worth knowing:

**After pulling this branch, re-sync the environment** — this task added dependencies (expected runtime
~1 min):

```bash
uv sync --all-packages --all-extras
```

Success looks like boto3, moto, boto3-stubs and import-linter installed; then `uv run pytest` → `1111
passed` and `uv run lint-imports` → `Contracts: 1 kept, 0 broken`.

**No AWS action is needed.** Nothing in this task touches an account, and no test can: moto answers
botocore in-process and the suite runs with `--disable-socket`. The first real call to the dev bucket will
come from `v1-e29-t05-evidence-sync-cli`, which resolves a bucket and a profile.

## Follow-up work

* **`v1-e02-t06-import-boundary-guard`** extends the `[tool.importlinter]` section this task created, rather
  than writing it: the remaining `forbidden` contracts, the layers contract, and the fixture-branch check
  its ac2 describes. Its spec says the CI job already exists ("already a CI job from E01-t04"), which is not
  true yet — `.github/` does not exist in this repository. Worth the PM's attention when t06 is scheduled.
* **`v1-e29-t05-evidence-sync-cli`** is unblocked and gets what its spec expects: two `EvidenceObjectStore`
  implementations to diff, `StoreCredentialsExpired.hint` already carrying the `aws sso login` command its
  ac4 asks for, and adapters that take a bucket and a profile. Its `storage-settings` node still owns the
  `storage.s3` settings group and the profile files.
* **No live smoke check exists for a real bucket.** The spec allows one as a `live`-marked opt-in and does
  not require it, and this task added none, because the thing worth smoke-testing is a resolved bucket for a
  resolved `DEBATE_ENV` — which is `t05`'s `smoke-and-docs` node.
* **`docs/architecture/evidence-store-layout.md`** still carries its "Two earlier specs that name `raw/`
  differently" note, for `v1-e30-t05-caselist-publish` and `docs/runbooks/caselist-removal.md`. This task
  builds the keys the layout document specifies, so that reconciliation is still the PM's, as that note says.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED

**Reviewed by / date:** PM (Claude, project chat), 2026-09-20

**Notes:**

- Conforms to the spec. Same content-addressed layout as the local store, idempotent put that issues
  no PutObject and leaves one version, sha256 re-hashed on read, multipart streaming for large camp
  files, botocore errors mapped to port errors, bucket and key ARNs as constructor arguments
  documented as coming from the Terraform outputs, and the E02 contract suite passing against moto
  with nothing skipped or adapted. Verifying that lint-imports actually fails when boto3 is added to
  the application layer is the check that makes the boundary real rather than declared.
- Storing the full-object sha256 in metadata because S3's own checksum is a composite on multipart
  uploads is the right call and worth keeping visible: without it a multipart blob could never be
  compared against its own key.
- The three out-of-package files are accepted: the port errors belong where every other port error
  lives, `integrations/file_streaming.py` avoids one adapter package importing another, and
  `testing/contracts/` is named by the task's own node outputs.
- `EvidenceObjectStore` is a good call. A small named-object port with S3 and filesystem adapters on
  one contract is what lets t05's sync be a single diff over two stores rather than two code paths.
- `list_objects` stating no digest, identically in both adapters, is accepted. S3 returns no
  checksums from a listing, so promising them would hide one HeadObject per object; t05 heads what it
  is actually considering, where the cost is visible.
- **PM action taken:** v1-e02-t06's spec claimed lint-imports was already a CI job from E01-t04.
  There is no .github/ in the repo, so that was wrong. Amended on branch `specs/import-guard-ci`:
  t06 owns and extends the [tool.importlinter] section this task bootstrapped, and adds the CI job
  only if v1-e01-t04 has landed, otherwise wiring the checks into pre-commit.
