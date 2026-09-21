# Session report: v1-e30-t05-caselist-publish

| | |
|---|---|
| Task | `v1-e30-t05-caselist-publish` — Publish sources and manifests to S3 |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t05-caselist-publish.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t05-caselist-publish.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t05-caselist-publish` |
| Session status | COMPLETE |

## Summary

`debate-research caselist publish` and `caselist status` now exist. `publish` uploads the sources
each local snapshot manifest names to `raw/caselist/<slug>/sha256/ab/cd/<digest>` and then the
manifest to `manifests/<caselist>/<snapshot>.jsonl`, in the bucket that `DEBATE_ENV` selects. Its
central rule is a single check in `CaselistPublishService._publish_snapshot`: a manifest is written
only when every source key it names has been confirmed in the bucket during this run. A source
counts as confirmed when it was uploaded and its recorded SHA-256 read back, or when it was already
present with that digest recorded. A publish killed between the sources and the manifest leaves a
snapshot that `caselist status` reports as drift. Re-running the publish completes that snapshot and
uploads no source a second time. Both properties are tested against moto: between uploads at
concurrency 1 and 8, and between the last source and the manifest. The PM should look first at
three things: the OpenEv key prefix and the policy's older key wording under **Deviations**, and the
separate local data directories for dev and prod under **Follow-up work**, which affects how v1-e30-t06
publishes to prod.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `key-layout-and-plan` — Key layout and publish plan | Done | `application/caselist/publish_plan.py`: key layout, manifest reading, pure `build_publish_plan`. Expected values hand-written in `tests/fixtures/caselist/expected_publish.json`. |
| `publisher` — Idempotent sources-first publisher | Done | `application/caselist/publish_service.py`, plus `evidence_listing.py`, which the publisher and status services share for reading both sides. Mutation check: with the manifest gate disabled, 7 of 21 tests fail. |
| `status-compare` — Local vs S3 status comparison | Done | `application/caselist/status_service.py`. |
| `cli-and-smoke` — `caselist publish` / `caselist status` with smoke checks | Done | `debate_cli/commands/caselist.py`, container wiring, `packages/debate_cli/tests/test_caselist_publish.py`, `tests/smoke/test_caselist_publish_smoke.py` (unmarked, runs in the default suite). |

## Acceptance criteria

All runs are local, from the task worktree, on 2026-09-20.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Node `key-layout-and-plan`: key layout and plan tests pass | PASS | `uv run pytest packages/debate_core/tests/application/caselist/test_publish_plan.py` → `41 passed in 4.64s` |
| Node `publisher`: publisher tests pass against moto | PASS | `uv run pytest packages/debate_core/tests/application/caselist/test_publish_service.py` → `21 passed in 8.41s` |
| Node `status-compare`: status comparison tests pass | PASS | `uv run pytest packages/debate_core/tests/application/caselist/test_status_service.py` → `13 passed in 6.22s` |
| Node `cli-and-smoke`: publish smoke check passes | PASS | `uv run pytest tests/smoke/test_caselist_publish_smoke.py` → `1 passed in 5.30s` under the default `-m "not slow and not live"`: passed, not skipped |
| Node `cli-and-smoke`: type check passes | PASS | `uv run pyright packages/debate_core packages/debate_cli` → `0 errors, 0 warnings, 0 informations` |
| Node `cli-and-smoke`: import boundaries hold | PASS | `uv run lint-imports` → `Contracts: 3 kept, 0 broken.` |
| Goal ac1 — each distinct source written once under `raw/caselist/<slug>/sha256/ab/cd/<hash>` with a SHA-256 checksum, one manifest per snapshot under `manifests/<caselist>/` | PASS | `test_publish_service.py::TestFirstPublish`: the bucket's keys equal the 14 hand-derived source keys plus 3 manifests; exactly 17 `PutObject` requests, counted at botocore's event hook; one version per source key; each source has `ChecksumSHA256` and metadata `{sha256: <digest>}` and nothing else |
| Goal ac2 — second publish uploads nothing and reports all skipped; an interrupted publish resumes without re-uploading | PASS | `TestIdempotentAndResumable`: a second run makes 0 `PutObject` requests and reports every source and manifest `skipped`. A run killed on the seventh upload, at concurrency 1 and 8, resumes with no key uploaded twice. A run killed at the second week's manifest resumes with exactly 4 uploads, derived by hand. `test_status_service.py::TestInterruptedPublishIsNeverClean` shows that snapshot reported as drift until the re-run completes it |
| Goal ac3 — any failed source upload withholds the manifest, and the command exits non-zero naming the failed sha256 | PASS | `TestFailedSourcesWithholdTheManifest`: upload failure, size mismatch, recorded-digest mismatch, missing recorded digest, a corrupt local blob and a missing local blob each withhold the manifest. Through the CLI, `test_caselist_publish.py::test_a_failed_upload_exits_non_zero_naming_the_sha256_and_withholds_the_manifest` exits `1` with `PUBLISH_INCOMPLETE` and the digest in `error.message` and `failed_sha256` |
| Goal ac4 — `caselist status` reports per snapshot local files, published sources, missing sources, manifest yes/no and checksum mismatches; exits 0 only when both sides agree; supports `--json` | PASS | `test_status_service.py` (13 tests) and `test_caselist_publish.py::TestStatus`: exit `1` with `CASELIST_DRIFT` before a publish, exit `0` after it; `--json` field set asserted |
| Goal ac5 — `DEBATE_ENV` selects the bucket; prod requires `--confirm-prod`; `--dry-run` lists planned uploads without writing | PASS | `test_caselist_publish.py::TestEnvironments`: dev writes only the dev moto bucket and prod only the prod one; prod without `--confirm-prod` is refused with `CONFIRMATION_REQUIRED` and writes nothing; `--dry-run` lists the planned uploads per snapshot and writes nothing; `test` is refused |
| Data-use policy rules 3 and 4, from the operator brief | PASS | `test_publish_service.py::test_no_school_team_code_or_filename_reaches_a_key_metadata_log_or_error` checks bucket keys, object metadata, `debate_core` logs at DEBUG, and every error message from a failing run and a clean one. `test_caselist_publish.py::test_the_rendered_output_names_nothing_identifying` checks rich, `--verbose` and `--json` output. `test_status_service.py::test_a_drift_report_names_digests_and_keys_and_nothing_identifying`. Each asserts the absence of every fictional school, team code, tournament and filename fragment in `FICTIONAL_IDENTIFIERS` |
| Regression across the touched trees | PASS | `uv run pytest packages/debate_core/tests/application packages/debate_core/tests/integrations packages/debate_core/tests/contracts packages/debate_cli/tests tests/smoke tests/fixtures --no-cov -q` → `1306 passed in 15.23s` |
| Lint and format | PASS | `uv run ruff check packages tests` → `All checks passed!`; `uv run ruff format --check packages tests` → `164 files already formatted` |
| Spec validation | PASS | `uv run scripts/validate_specs.py` → `OK: 282 files, 38 epics, 224 tasks, 20 releases`; `--require-succeeded v1-e30-t05-caselist-publish` → `Succeeded` |
| Whole-repository `uv run pytest` | NOT RUN | Left to the operator under working agreement §2; see **Operator follow-ups**. The trees it adds (domain, API, workers, `tests/integration`, `tests/scripts`) are not touched here |

## Files changed

- **`packages/debate_core/src/debate_core/application/caselist/`**: new modules.
  - `publish_plan.py`: key layout, manifest reading and the pure plan.
  - `evidence_listing.py`: reads the local store and the bucket through the port only.
  - `publish_service.py`: the sources-first publisher.
  - `status_service.py`: the comparison.

  None imports boto3; `lint-imports` holds.
- **`packages/debate_cli/`**:
  - `commands/caselist.py`: the `publish` and `status` commands, their guards and their rendering.
  - `commands/__init__.py`: registration.
  - `container.py`: `caselist_publish`, `caselist_status`, and one shared bucket store per run.
  - `tests/test_caselist_publish.py`: new.
  - `tests/test_app.py`: the `doctor` service list now includes the two new services.
- **`packages/debate_core/tests/application/caselist/`**:
  - `conftest.py`: imports the three synthetic weeks with the real importer, plus the shared `local` and `bucket` fixtures.
  - `test_publish_plan.py`, `test_publish_service.py`, `test_status_service.py`: new.
- **`tests/fixtures/caselist/`**:
  - `expected_publish.json`: hand-written expectations, with each snapshot's sources named by synthetic body.
  - `publish_expectations.py`: turns body names into keys from the fixture's own bytes, and lists the fictional identifiers the privacy tests check for.
  - `interruptible_bucket.py`: the S3 wrapper that fails or simulates a kill part-way through a publish.
- **`tests/smoke/`**:
  - `test_caselist_publish_smoke.py`: new, offline.
  - `README.md`: a row for the new check, and why it is unmarked.
- **`plan_specs/.../t05-caselist-publish.yaml`**: Goal phase set to `Succeeded`.

## Deviations from the spec

1. **OpenEv sources go under `raw/openev/<year>/`, not `raw/caselist/openev/`.** The spec gives one
   source layout, `raw/caselist/<caselist-slug>/sha256/…`, for `--caselist <slug|openev>`. But
   `docs/architecture/evidence-store-layout.md`, which the E29 adapters cite as the key contract,
   files camp files at `raw/openev/2026/sha256/…`. I followed the layout document
   (`publish_plan.source_prefix`), and read the year from the manifest name `manifests/openev/<year>-<event>.jsonl`.
   Nothing publishes OpenEv yet, because v1-e30-t04 is `Pending`, so the PM can pick either form
   before t04 lands. Changing it means editing one function and two tests.
2. **The data-use policy's key example is out of date.** Personal-data rule 3 in
   `docs/policies/caselist-data-use.md` writes the key as `raw/<caselist>/<sha256>.<ext>`. The spec,
   the layout document and this code use `raw/caselist/<slug>/sha256/ab/cd/<digest>` with no
   extension. The substance of the rule is unchanged (no school, team code or filename in a key or
   in metadata), so this code follows the spec. The policy wording needs a PM or owner edit. Under
   the policy's own change control, a tightening like this takes effect on merge.
3. **`--json` is the global flag** (`debate-research --json caselist status`), not a per-command
   option. The spec's `cli-and-smoke` node lists `--json` among the command's flags; every existing
   command, `caselist import` included, takes it globally, so this follows that convention.

## Decisions and assumptions

- **A snapshot's sources are its distinct digests in rows classified `NEW`, `UNCHANGED`, `CHANGED`
  or `DUPLICATE`.** These are the importer's `STORED_CLASSIFICATIONS`. `REMOVED` rows (the previous
  archive's paths) and `SUPPRESSED` rows are neither uploaded nor allowed to hold a manifest back.
  Sources are selected through manifests, not by walking the blob tree, because the local
  `blobs/` tree is shared by every caselist. `store sync --blob-prefix raw/caselist/hsld26` would
  file every local blob under hsld26, OpenEv included.
- **"Matching sha256 checksum" means the digest the bucket recorded.** A listed object is headed. It
  is skipped only if the recorded digest equals the digest in its key and the size matches. A
  present object with a different size, a different recorded digest, or no recorded digest is a
  `CHECKSUM_MISMATCH` failure. It is never overwritten, and a person decides what happened.
- **Local blobs are re-hashed before upload.** A blob that no longer matches its key fails with
  `BLOB_INTEGRITY_ERROR` and is never uploaded under that key. After each upload the bucket is asked
  separately for the digest it recorded. So a first publish makes about two HeadObject calls per
  PutObject, the adapter's own head plus the verification head.
- **A manifest already in the bucket** is skipped when its recorded digest equals the local file's,
  and otherwise re-uploaded: manifests are named, versioned objects. The same gate applies either
  way.
- **Concurrency**: 8 sources in flight, and snapshots processed in date order. When one task raises
  a `BaseException` or a credential error, the other tasks are cancelled and awaited before the
  error propagates.
- **`publish` applies by default**, as the spec's `[--dry-run]` form implies. This is the opposite of
  `store sync`. The publisher cannot overwrite a content-addressed key and cannot write an
  incomplete manifest, so a plan-first default would protect nothing. Prod still needs
  `--confirm-prod`. A dry run whose plan is already blocked (a mismatch, a missing local blob)
  exits `1` with `PUBLISH_BLOCKED`, as a `store sync` dry run does for a mismatch.
- **`caselist status` with no `--caselist`** compares every caselist that either side holds a
  manifest for. A caselist neither side holds is refused with `NO_CASELIST_EVIDENCE`, so a
  mistyped slug cannot exit 0. A manifest only the bucket holds counts as drift.
- **The suppression list** is a constructor argument on both services, `suppressed=`, and its
  semantics are tested. The container passes nothing until v1-e30-t07 supplies the list, as the
  spec's boundaries require.
- **Log capture in the privacy test is scoped to the `debate_core` loggers.** botocore's own DEBUG
  wire logging, which is off by default, can include request bodies, and a manifest body names
  schools. Rule 4 governs this application's output, so the test does not capture botocore. It
  follows that nobody should run a real publish with botocore DEBUG logging enabled; see
  **Follow-up work**.

## Operator follow-ups

1. **Optional: the whole-repository suite**, which I did not run myself (working agreement §2). The
   touched trees pass (1,306 tests in 16 s).

   **Operator command** (expected runtime ~1–2 min)
   Where: your Mac, in the task worktree `debate-intelligence-worktrees/v1-e30-t05-caselist-publish`
   ```bash
   uv run pytest
   ```
   Success looks like: a final `N passed` line with no failures; paste the last 20 lines back.

2. **The first real publish belongs to v1-e30-t06, not to this task.** Nothing here was published to
   a real bucket, and this session holds no AWS credentials. For sizing when t06 runs it: ADR-0016
   records 2,107 distinct files across the three windows, so a first publish to dev should make
   about 2,110 PutObject calls (2,107 sources plus 3 manifests) and about twice that many
   HeadObject calls. The brief's figures of ~2,300 puts and ~4,600 heads are a safe upper bound.
   Expect roughly 6–12 minutes and a few cents. The sequence t06 would run:

   **Operator command** (expected runtime ~6–12 min for the publish; seconds for the dry run and status)
   Where: your Mac, in a checkout with this branch merged, `uv sync --all-packages --extra aws` done
   ```bash
   aws sso login --profile debate-dev-evidence
   DEBATE_ENV=dev uv run debate-research caselist publish --caselist hsld26 --dry-run
   DEBATE_ENV=dev uv run debate-research --json caselist publish --caselist hsld26 > /tmp/publish-dev.json; echo "exit $?"
   DEBATE_ENV=dev uv run debate-research caselist status --caselist hsld26; echo "exit $?"
   ```
   Success looks like: the dry run lists three snapshots; the publish exits `0`, and
   `failed_sha256` in `/tmp/publish-dev.json` is `[]`; `status` shows `yes` in the In sync column for all
   three snapshots and exits `0`. If the publish is interrupted, run the same command again: confirmed
   sources are skipped and the manifests follow. Paste back only the counts. The JSON contains
   digests and no identifying fields, but keep the file out of the repository anyway.

## Follow-up work

- **v1-e30-t06: prod reads a different local store from dev.** `config/profiles/dev.toml` sets
  `data_dir = "~/.debate-research/dev"` and `prod.toml` sets `~/.debate-research/prod`. So `DEBATE_ENV`
  selects the local evidence store as well as the bucket. If the September windows were imported
  only under dev, `DEBATE_ENV=prod caselist publish` finds no manifests and refuses with
  `NOTHING_TO_PUBLISH`, or publishes a different store if prod has one. t06 needs to choose between
  importing again under `DEBATE_ENV=prod`, which is deterministic and yields byte-identical manifests,
  and pointing prod's `data_dir` at the dev store for the run. Given ADR-0016, the choice matters:
  the local store is the archive of record.
- **Owner or PM: data-use policy personal-data rule 3.** Update the key example to
  `raw/caselist/<slug>/sha256/ab/cd/<digest>`, with no extension (Deviation 2).
- **PM: the OpenEv source prefix** (Deviation 1), to settle before v1-e30-t04 is implemented.
- **v1-e30-t07: pass the suppression list into the container.** The container needs
  `suppressed=` on `caselist_publish()` and `caselist_status()`. The services already honour it.
- **v1-e30-t06 or the runbooks: a warning about botocore DEBUG logging.** Real publishes should not
  run with botocore DEBUG logging on, because it can print manifest bodies, which name schools.
  A line in the t06 procedure, or in `docs/guides/evidence-store-cli.md`, would cover it.
- **validate-dev, after t06: a live `caselist status --caselist hsld26` check.** It would be
  read-only, in the style of `tests/smoke/test_store_cli.py` (marked `live` and `dev`/`prod`,
  since it needs a deployed bucket). It becomes useful once real manifests exist.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
