# Session report: v1-e33-t05-file-publish

| | |
|---|---|
| Task | `v1-e33-t05-file-publish` — Publish built files to S3 |
| Spec | [`plan_specs/v1/e33-file-builder/t05-file-publish.yaml`](../../plan_specs/v1/e33-file-builder/t05-file-publish.yaml) |
| Epic / release | `v1-e33-file-builder` / `v1.2` |
| Branch | `task/v1-e33-t05-file-publish` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`debate-research files publish <built.docx|dir> --env dev|prod [--dry-run]` publishes built evidence
files to `files/<topic>/<side>/<position>/<slug>/<recipe hash 12>/` in the evidence bucket: the
`.docx`, its sidecar, a PASS quality report for those exact bytes, the recipe without any pin's
attribution, and `metadata.json`, last. The gate refuses a missing, stale or FAIL report, a file
built from a draft recipe (the sidecar now records the recipe's status), and a file that no longer
passes when checked again. A warning never blocks. Publishing is idempotent and checks each object
after it lands. In bucket mode it holds the run lock. A dry run builds no bucket client. The
takedown lookups are `find_by_source(source_sha256)`, over every published `metadata.json`, and,
since the PM's rulings of 2026-10-25, `find_by_disclosure(school, team_code)`, over every published
provenance sidecar. `metadata.json` holds no school or team code. The rulings and what they amend are
under Deviations.

The Goal stays **InProgress**: ac5 and the coach's approval are operator steps after merge (the PR
merges `--partial`).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `metadata-contract` | Done, as ruled | Model, key builder, generated schema, `docs/data/built-file-metadata.md`. No `school`/`team_code` in `sources[]` and no `schools`/`team_codes` arrays, by the PM's ruling on question 1 (B) |
| `publish-service` | Done, as ruled | Gate, upload, idempotence, checksums, dry run, `find_by_source(source_sha256)` over `metadata.json`, and `find_by_disclosure(school, team_code)` over the published sidecars (ruling Q1 B) |
| `publish-command` | Done | `files publish`, with `--env`, `--confirm-prod`, `--recipes`, `--json` (Decisions) |
| `smoke-checks` | Done | `tests/smoke/test_files_publish.py`, plus a row in `tests/smoke/README.md` |
| `operator-publish` | Not run | Operator, after merge: dev after the cutover's step 9, prod after the coach approves (Operator follow-ups) |

Before the first node, a prerequisite the PM amendment of 2026-10-24 asked for: the sidecar did not
record the recipe's status, so the writer now writes `recipe_status` (commit `b3aa0bd`).

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a missing, stale or FAIL report is not uploaded, exit non-zero naming the failing checks | PASS | Service: `test_a_file_with_no_quality_report_is_refused_and_nothing_is_uploaded`, `test_a_quality_report_for_other_bytes_is_stale_and_refused`, `test_a_file_whose_report_fails_is_refused_naming_the_failing_checks` (`failing_checks == (suppression,)`), `test_a_fail_report_is_refused_even_when_a_check_run_now_would_pass`, and the exact-bytes re-check (`test_a_pass_report_that_no_longer_holds_for_the_exact_bytes_is_refused`). CLI: `test_files_publish_refuses_a_stale_or_failing_file_exit_1_naming_its_failing_checks`: exit 1, `QUALITY_REPORT_STALE`, then `QUALITY_FAILED` with `evidence-identity` in the message, the panel and `details.files[].refusal.failing_checks`; nothing in moto's bucket |
| ac2: five objects at `files/<topic>/<side>/<position>/<slug>/<hash12>/`; `metadata.json` validates against the schema | PASS | `test_a_pass_file_publishes_five_objects_under_its_prefix_metadata_last` (keys and put order written by hand), `test_the_metadata_validates_against_the_committed_schema_and_names_the_file` (`jsonschema.validate` against `docs/data/built-file-metadata.schema.json`) |
| ac3: idempotent (SKIPPED), checksums verified after upload, `--dry-run` calls no S3 (moto) | PASS | `test_publishing_an_unchanged_file_again_is_skipped_and_writes_nothing` (no new object version, no put); `test_an_object_that_lands_with_another_digest_stops_the_publish_before_the_metadata[lie_on_put, lie_on_head]`; `test_a_dry_run_lists_the_keys_and_never_builds_a_bucket_client` (bucket factory called 0 times), and the CLI dry run run without moto under the disabled socket |
| ac4: `docs/data/built-file-metadata.md`; `tests/smoke/test_files_publish.py` dry-run publish in validate-dev | PASS | The document is committed. `uv run pytest tests/smoke/test_files_publish.py` → `2 passed in 5.14s`, through the harness's installed CLI. validate-dev runs it on `dev` after the merge |
| ac5: operator publishes synthetic samples to dev and the first coach-approved files to prod, and records them in `docs/data/file-publish-log.md` | NOT RUN | Operator work after the merge (PM brief). The dev sequence was rehearsed here into a scratch data directory as far as a dry run, with a fake bucket name and no AWS config: 3 imports, 3 parses, 3 builds PASS, dry run `WOULD_PUBLISH`, 7 s |
| ac6: a lookup by source sha256 (over `metadata.json`) or a school or team code (over the published provenance sidecars) returns exactly the files with cards from it; every sidecar source is in `sources[]` (wording as the PM amends it, ruling Q1 B) | PASS | `uv run pytest …test_file_publish_service.py -k find_by_source` → `8 passed`. By source: exactly the right prefixes for three sources over two files, none for an unknown source, an unreadable `metadata.json` reported, the published sidecar's sources equal to `sources[]`. By school or team (three files, three teams, two schools): exactly the right prefixes by school, by team code and by both on one card, none for an unknown school or team or a mismatched pair, no case folding, an unreadable sidecar reported, a call naming neither refused, and no school or team code in any `metadata.json`. Red first: the four new tests failed (`no attribute 'find_by_disclosure'`); three mutants (`and`→`or`, the unreadable report dropped, case folding) each caught |
| ac7: the uploaded recipe holds no side, school, team code, tournament or round, every pin still names its card's source and element as the sidecar does, and it resolves to the same occurrences wherever no removed field was needed (wording as the PM amends it, ruling Q2 A and FYI 1) | PASS as amended | `test_the_uploaded_recipe_names_no_side_tournament_round_school_or_team_and_resolves_the_same`: no attribution in the uploaded YAML, which loads and resolves to the same source, element and disclosure for every card. `test_pins_inside_hats_lose_their_side_tournament_round_school_and_team_too`. An ad-hoc run of the case `files suggest` writes such fields for (two teams, same bytes, same side): the original pin resolves, the published one gives `PIN_MISMATCH`, which the amended wording allows. Before upload the service asserts every pin names the sidecar's source and element |
| ac8: a non-PASS file is refused before any upload, and a warning alone never blocks, by tests shown failing first | PASS | Red run against a scratch copy of the service whose gate refuses nothing: **8 failed** (every refusal test), 16 passed (layout, idempotence, lookup, recipe, and the warning test, which a refuse-nothing gate also passes). Then one mutant per gate step, each caught by a behaviour test (table under Decisions). `test_a_warning_never_blocks_and_is_recorded_in_the_metadata`: a real `cite-present` WARN, PUBLISHED, `quality_warnings: 1` |
| Node: metadata contract documented (`contentMatch: source_sha256s`) | PASS | `grep -c source_sha256s docs/data/built-file-metadata.md` → 2 |
| Node: metadata model and key builder tests | PASS | `uv run pytest packages/debate_core/tests/domain/test_built_file_metadata.py` → `26 passed in 1.34s` |
| Node: publish service tests (moto) | PASS | `uv run pytest packages/debate_core/tests/application/test_file_publish_service.py` → `32 passed in 4.08s` |
| Node: source reverse lookup (moto) | PASS | `… -k find_by_source` → `8 passed in 2.87s` (source sha256, school, team code) |
| Node: publish command tests | PASS | `uv run pytest packages/debate_cli/tests/commands/test_files.py -k publish` → `6 passed in 3.13s` |
| Node: pyright on debate_cli | PASS | `uv run pyright packages/debate_cli` → `0 errors, 0 warnings, 0 informations` |
| Node: publish smoke check | PASS | `uv run pytest tests/smoke/test_files_publish.py` → `2 passed in 5.14s` |
| Node: import boundaries | PASS | `uv run lint-imports` → `Contracts: 18 kept, 0 broken.` |
| Node: publish log records the prod publish | NOT RUN | `docs/data/file-publish-log.md` does not exist: the operator writes it with the first publish |
| Node: coach approves the first published real files | NOT RUN | A sign-off |

### Checks run before the report

After the rulings (commit `f806c9f`, the lookup by school or team code), which changed
`file_publish_service.py`, its tests and two documents: `test_file_publish_service.py` → `32
passed in 4.08s`, `-k find_by_source` → `8 passed`, `test_built_file_metadata.py` → `26 passed`,
`test_files.py -k publish` with `tests/smoke/test_files_publish.py` → `8 passed`, ruff and pyright on
the changed files clean, `lint-imports` 18 kept, the schema `--check` up to date, links and docs
descriptions OK. The affected set was already past two minutes and is the PR's `ci` check. The runs
below are the first round's.

* `uv run scripts/affected_tests.py` selects **211 files**. Run as one pytest under
  `perl -e 'alarm 115'` on the interpreter, it reached the alarm (`1:55.04 total`), so under
  agreement 10 the affected set is the PR's `ci` check, not a hand-off. No orphaned worker was
  left (`pgrep` found only another session's unrelated run).
* Within two minutes each, the test directories of what changed and the always-run list:
  * `tests/architecture`, `tests/specs`, `test_app.py`, `test_installation.py`,
    `debate_core/tests/domain`, `debate_core/tests/integrations/docx_file_writer` → `1588 passed in 13.83s`;
  * `test_help_rendering.py`, `tests/docs`, `tests/scripts/test_check_command_blocks.py`,
    `tests/scripts/test_docs_index.py`, the six `test_file_*` files of `debate_core/tests/application`,
    `debate_core/tests/evidence/file_checks`, `tests/smoke/test_files_publish.py`,
    `tests/smoke/test_files_cli.py` → `539 passed in 22.79s`;
  * `debate_cli/tests/commands` and `debate_cli/tests/bucket_mode` → `538 passed in 50.15s`;
  * the rest of `debate_cli/tests` → `503 passed in 26.22s`.
* `uv run ruff format --check .` → `1393 files already formatted`; `uv run ruff check .` → `All checks passed!`
* `uv run pyright packages/debate_core packages/debate_cli scripts/export_built_file_metadata_schema.py tests/smoke/test_files_publish.py` → `0 errors` (16.8 s)
* `uv run lint-imports` → 18 kept; `uv run python scripts/check_thin_handlers.py` → `OK: 62 … within 25 statements`
* `uv run scripts/validate_specs.py` → `OK: 464 files, 40 epics, 402 tasks, 22 releases`
* `uv run python scripts/docs_index.py --check-descriptions` → all 50 described; `uv run scripts/check_links.py` → OK;
  `uv run scripts/check_command_blocks.py --base origin/dev` → `OK: no # comments in 491 shell code
  blocks in 167 Markdown files (1 session reports changed since origin/dev)`
* Coverage of the new modules from their own tests: `built_file_metadata.py` 100%,
  `file_publish_service.py` 99%, from 97%. The first measurement found three untested paths (pins
  inside hats, `SLUG_INVALID`, an unreadable report or a missing sidecar); each now has a test, and a
  mutant that skips the hats is caught. Left uncovered: `PublishResult.refused`, which the CLI
  tests use, and a sidecar that exists but does not validate, which the re-check fails as `sidecar`.

## Files changed

* **`debate_core.domain`**: `built_file_metadata.py` (new: model, key builder, sources, schema);
  `file_provenance.py` (`recipe_status`).
* **`debate_core.application`**: `file_publish_service.py` (new).
* **`debate_core.integrations.docx_file_writer`**: `writer.py`, one line writing `recipe_status`
  (Deviations).
* **`debate_cli`**: `commands/files.py` (`publish`), `commands/__init__.py` (registration),
  `presenters/files_presenter.py` (`publish_rendered`), `container.py` (`file_publish`, `SERVICE_NAMES`).
* **Tests**: `debate_core/tests/domain/test_built_file_metadata.py`,
  `debate_core/tests/application/test_file_publish_service.py` (new);
  `test_file_provenance.py`, `docx_file_writer/test_draft_header.py`,
  `docx_file_writer/test_built_files_without_the_line.py` (the sidecar's new line, by hand);
  `debate_cli/tests/commands/test_files.py`, `test_app.py`,
  `bucket_mode/test_bucket_mode_lock.py` (classification and lock cases).
* **`docs/data`**: `built-file-metadata.md`, `built-file-metadata.schema.json` (new);
  `file-provenance.schema.json` (regenerated).
* **`tests/smoke`**: `test_files_publish.py` (new), `README.md` (one row).
* **`scripts`**: `export_built_file_metadata_schema.py` (new; Deviations).

## Deviations from the spec

### The PM's rulings of 2026-10-25, quoted

* **Q1: B.** "No policy change. Build the lookup by school or team code over the published
  .provenance.json objects in files/, beside find_by_source(source_sha256) over metadata.json. Test
  it with moto: exactly the right files, none for an unknown school or team, and an unreadable sidecar
  reported. metadata.json keeps the source fields only. The PM amends ac6 in the next batch to: 'a
  source sha256 (over metadata.json) or a school or team code (over the published provenance
  sidecars)'." Built: `find_by_disclosure(school, team_code)`, commit `f806c9f`. ac6 is PASS as amended.
* **Q2: A.** "Amend ac7's wording as you proposed, in the next batch. What's built and tested stands."
* **FYI 1** (accepted): "Policy 1.15 governs, so side goes too, and the PM adds it to ac7."
* **FYIs 2 and 3** (accepted): `--env`, `--confirm-prod`, `--recipes`, and `RECIPE_STATUS_UNRECORDED`.
* **The evidence-store layout document's `files/` examples:** "the PM fixes them in the next
  batch. Leave them." Left as they are.

The spec still carries ac6's and ac7's old wording until the PM's next batch; this session does not
edit acceptance criteria.

### What differs from the spec as written

1. **A published pin also loses its `side`.** The PM amendment of 2026-10-19 names `school`,
   `team_code`, `tournament` and `round`. Data-use policy version 1.15, approved 2026-10-24, says a
   published recipe "loses every such field", and its list is "a pin's side, tournament, round, and
   school and team code". The policy is later, stricter, and governs (agreement 7), so `side` goes
   too (commit `c15dabb`). Accepted (FYI 1); the PM adds it to ac7.
2. **No `school`/`team_code` in `metadata.json`; the lookup by them reads the sidecars.** The spec's
   description, the `metadata-contract` node and ac6 put them in `metadata.json`; the policy does not
   cover that, and the PM ruled B (Q1).
3. **Outside `constraints.packages`:**
   * `debate_core.integrations.docx_file_writer/writer.py` (one line) and its tests: the PM
     amendment of 2026-10-24 says this task adds the recipe status to the sidecar, and the writer
     is what writes the sidecar;
   * `scripts/export_built_file_metadata_schema.py`: the node says the schema is "generated", and
     the repository generates its three sibling schemas this way.
4. **The command has more options than `files publish <path> [--dry-run]`.** `--env` (required) and
   `--confirm-prod` follow `tub index publish`, the precedent for a command that writes a bucket:
   `DEBATE_ENV` picks the bucket and `--env` confirms it. `--recipes` exists because a built file does
   not record where its recipe is (Decisions). `--json` follows the other `files` commands.
   Accepted (FYIs 2 and 3).
5. **ac7's "still resolves to the same occurrences"** holds only where no removed field was needed to
   tell two disclosures apart. Ruled Q2 A: the wording is amended, what is built stands.

## Decisions and assumptions

* **The gate's order** is report present → for these bytes → recipe status → report PASS →
  re-check of the exact bytes PASS → slug → recipe. The draft check comes before the quality status so
  a draft is refused "whatever its quality status". A sidecar without `recipe_status` (built before
  this task) is refused as `RECIPE_STATUS_UNRECORDED` until it is rebuilt, since "ready" cannot be
  assumed. No file has been published yet, so no published file is affected.
* **The report uploaded is the one the re-check wrote for the bytes uploaded**, not the file on disk,
  and the on-disk report must still be PASS (ac1). Each gate step was disabled in turn:

  | Step disabled | Caught by |
  |---|---|
  | report present | the missing-report, dry-run and directory tests |
  | report for these bytes | the stale test |
  | recipe status (draft and unrecorded) | the draft and unrecorded tests |
  | unrecorded status only | the unrecorded test |
  | report status PASS | at first only a message assertion, since the re-check fails too; then `test_a_fail_report_is_refused_even_when_a_check_run_now_would_pass` (report FAIL, cause lifted since), added for it |
  | the exact-bytes re-check | the "no longer holds" test |
  | skip-if-unchanged | the idempotence test |

  Each run used a scratch copy of `src` first on `PYTHONPATH`, the module's `__file__` printed. No
  Hypothesis is involved.
* **The recipe is found** at `<files dir>/recipes/<topic>/<slug>.yaml`, where `files suggest`
  writes, or `--recipes <dir>/<slug>.yaml`. It must hash to the sidecar's `recipe_hash`
  (`RECIPE_CHANGED` otherwise). The sidecar records no path, and should not, since a path names a team.
* **The published recipe is rendered from the model**, not edited from the text, so the coach's
  comments, which can name anything, are dropped too. Before upload, every pin is checked to name the
  sidecar's source and first element for its card (an assertion: the hash already ties them).
* **Keys**: the side is lower case (`aff`); a slug must be kebab-case, at most 100 characters
  (`SLUG_INVALID`), rather than rewritten. A directory publishes its own `*.docx`, not its
  subdirectories.
* **The lock is held for the whole non-dry run**, gate included, as `tub index publish` holds it
  over its check. So a run that refuses every file still takes and releases it, which is what the
  classification test's stand-in case does. Every key written is under `files/`; the CLI test asserts
  that nothing else lands.
* **No builder version bump**: the `.docx` bytes are unchanged and the sidecar's new key describes
  itself. The byte-for-byte sidecar test expects the one added line, by hand.
* **IAM**: the publish signs with the everyday evidence profile, through the container's
  `_evidence_bucket`, the same client as `tub index publish`. `DebateDevEvidenceOperator` and
  `DebateProdEvidenceOperator` allow `s3:PutObject`, `GetObject`, `GetObjectVersion` on `bucket/*`,
  list `files/` (`local.evidence_prefixes`) and use the key
  (`infrastructure/modules/evidence_bucket/operator_access.tf`). The bucket policy's denies are about
  TLS and encryption headers, which the adapter already sets. **No grant is needed.**
* **Bucket mode**: dev is in bucket mode, so a publish there takes the run lock and its client is
  fenced. `files publish` is in `BUCKET_WRITING`, with its lock cases. Both were shown failing:
  unclassified (`unclassified: ['files publish']`), and run without the lock (`files publish never
  took the lock`; `'QUALITY_REPORT_MISSING' == 'RUN_LOCK_HELD'`).
* **No school or team code reaches anything this task writes except the sidecar**: a test reads
  every published object for the invented names and finds them in `.provenance.json` alone.

## Operator follow-ups

All after this task's PR is merged into `dev` (`--partial`), from a checkout of `dev` that includes
it. None of them is run by a session.

### Synthetic samples to dev, after the cutover's step 9

The first block makes the three t01 example files from synthetic sources, in a scratch data directory
of their own in your home folder (never a git working tree). It writes nothing outside that directory
and reaches no bucket. Each command sets its overrides with `env`, so none is left set. Expected
runtime: under a minute.

**Operator command** (expected runtime under a minute)
Where: the root of a checkout of `dev` that includes this task
```bash
SAMPLES="${HOME}/e33-publish-samples"
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
echo "DEBATE_ overrides: ${OVERRIDES:-none}"
if [[ -n "$OVERRIDES" || -e "$SAMPLES" ]]; then
  echo "STOP: a DEBATE_ override is set, or ${SAMPLES} already exists. Open a new window, or move it aside."
else
  mkdir -p "${SAMPLES}/recipes"
  uv run python -c 'import sys; from pathlib import Path; from tests.fixtures.file_builder.example_corpus import EXAMPLES, example_corpus; [print(c.caselist, c.snapshot.isoformat(), c.archive, c.recipe) for c in (example_corpus(r, Path(sys.argv[1]) / r.stem) for r in sorted(EXAMPLES.glob("*.yaml")))]' "${SAMPLES}" > "${SAMPLES}/corpora.txt"
  while read -r caselist snapshot archive recipe; do
    env DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="${SAMPLES}/data" DEBATE_CASELIST__RUN_STATE=local uv run debate-research caselist import "${archive}" --caselist "${caselist}" --snapshot "${snapshot}" < /dev/null
    env DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="${SAMPLES}/data" DEBATE_CASELIST__RUN_STATE=local uv run debate-research caselist parse --caselist "${caselist}" < /dev/null
    env DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="${SAMPLES}/data" DEBATE_CASELIST__RUN_STATE=local uv run debate-research files build "${recipe}" < /dev/null
    cp "${recipe}" "${SAMPLES}/recipes/"
  done < "${SAMPLES}/corpora.txt"
  echo "built: $(ls "${SAMPLES}"/data/files/built/*/*.docx | wc -l | tr -d ' ')"
fi
```
Success looks like three builds whose check table ends PASS, and `built: 3`. Stop at a `STOP` line,
or if any build is refused or FAILs, and paste the output back.

The second block is the dry run: it checks each file again and prints the keys it would write. It
needs no AWS session and reaches no bucket.

**Operator command** (expected runtime under a minute)
Where: the same checkout
```bash
SAMPLES="${HOME}/e33-publish-samples"
for topic in "${SAMPLES}"/data/files/built/*/; do
  env DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="${SAMPLES}/data" uv run debate-research files publish --env dev "${topic}" --dry-run --recipes "${SAMPLES}/recipes" < /dev/null
done
```
Read three tables, each titled `Dry run: would publish to the dev evidence bucket
debate-dev-evidence-a7508de8`, each with one `WOULD_PUBLISH` row: prefixes starting
`files/data-center-moratorium/con/`, `files/nhi/aff/politics-da/` and
`files/space-colonization/neg/`. **Stop** on a `REFUSED` row, on another bucket name, or on fewer
than three tables, and paste the output back. Nothing has been written.

The third block publishes them. In bucket mode it takes the dev bucket's run lock, so it refuses
while the cloud run holds it.

**Operator command** (expected runtime under a minute)
Where: the same checkout
```bash
SAMPLES="${HOME}/e33-publish-samples"
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
echo "running pull: ${PULL:-none}"
echo "DEBATE_ overrides: ${OVERRIDES:-none}"
if [[ -n "$PULL" || -n "$OVERRIDES" ]]; then
  echo "STOP: the line above that is not none says why. Wait for the pull to finish, or open a new window."
else
  aws sso login --profile debate-dev-evidence
  for topic in "${SAMPLES}"/data/files/built/*/; do
    env DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="${SAMPLES}/data" uv run debate-research files publish --env dev "${topic}" --recipes "${SAMPLES}/recipes" < /dev/null
  done
  DEBATE_ENV=dev uv run debate-research store ls files/
fi
```
Success looks like three tables titled `Published to the dev evidence bucket
debate-dev-evidence-a7508de8`, each `1 PUBLISHED`, then a `store ls files/` listing of 15 objects
(five per file), every key under `files/`. Run the block again: each table then says `1 SKIPPED`
and the listing is unchanged. A `RUN_LOCK_HELD` refusal means the cloud run is running; wait for it to
finish. Paste both runs' output back, and the session writes `docs/data/file-publish-log.md` from it
(keys, counts and statuses; no team codes). Then remove `~/e33-publish-samples`.

### The first real files to prod, after the coach approves them

Real files never go to dev (forbidden). The coach reviews two or three built files, their
`.provenance.json` and `.quality.md`, and says which. The publish checks each again against the blob
store of the data directory it was built in, so `DATA` below is that directory, and its sources must
still be there. Replace `TOPIC/NAME` with each approved file. **Ask the PM first** if the files were
built from a restored working copy (the cutover runbook's "Until the promotion"), which holds no raw
sources: the re-check would fail. Prod is in local mode until the promotion, so this takes no lock.

**Operator command** (expected runtime under a minute)
Where: the same checkout
```bash
DATA="${HOME}/.debate-research/dev"
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
echo "DEBATE_ overrides: ${OVERRIDES:-none}"
if [[ -n "$OVERRIDES" ]]; then
  echo "STOP: a DEBATE_ override is set. Open a new window."
else
  for docx in "${DATA}/files/built/TOPIC/NAME.docx"; do
    env DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="${DATA}" uv run debate-research files publish --env prod "${docx}" --dry-run < /dev/null
  done
fi
```
Read one `WOULD_PUBLISH` row per approved file, in a table titled `Dry run: would publish to the
prod evidence bucket …`. **Stop** on any `REFUSED` row and paste it back; nothing has been written.
A `RECIPE_NOT_FOUND` means the recipe is elsewhere: add `--recipes <its directory>`.

**Operator command** (expected runtime under a minute)
Where: the same checkout
```bash
DATA="${HOME}/.debate-research/dev"
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
echo "DEBATE_ overrides: ${OVERRIDES:-none}"
if [[ -n "$OVERRIDES" ]]; then
  echo "STOP: a DEBATE_ override is set. Open a new window."
else
  aws sso login --profile debate-prod-evidence
  for docx in "${DATA}/files/built/TOPIC/NAME.docx"; do
    env DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="${DATA}" uv run debate-research files publish --env prod "${docx}" --confirm-prod < /dev/null
  done
  env DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="${DATA}" uv run debate-research store ls files/
fi
```
Success looks like one `PUBLISHED` per file, then five objects per file under `files/` in the
listing. Paste the output back for the log (no team codes go into it). The coach confirms the
listing matches the files approved: the node's custom criterion.

## Follow-up work

* **`docs/architecture/evidence-store-layout.md`'s example keys for `files/`** predate this layout:
  the PM fixes them in the next batch (ruling of 2026-10-25), so they are left here.
* **ac6's and ac7's wording**: the PM's next batch, as ruled.
* **A published recipe as a rebuild input** (question 2, not chosen): if the PM wants a published recipe to
  rebuild the same file, the pin needs something that tells disclosures apart without naming them.
  A plain `disclosure_digest` would not do: it is an unkeyed digest of `<caselist>/<path>`, and the
  path names the team.

## PM questions (relay prompt)

Answered on 2026-10-25; the rulings are quoted under Deviations. The prompt as it was sent:

```text
v1-e33-t05-file-publish: two questions, and three things I will proceed on unless told otherwise.
The work is committed on task/v1-e33-t05-file-publish; the Goal stays InProgress.

QUESTION 1 (policy; blocks half of ac6). Your brief asked me to check before writing any school or
team code into metadata.json. docs/policies/caselist-data-use.md, "Where personal data is allowed to
live", names "the provenance sidecar of a built file" and "a file recipe under the data directory's
files/", and not a metadata.json beside a built file in the bucket's files/ prefix. So I built
sources[] as {caselist, snapshot, source_sha256} with flattened caselists and source_sha256s, and no
school, team_code, schools or team_codes; find_by_source takes a source_sha256 only.

Options:
A. Amend the policy (version 1.19), then add the fields and find_by_source(school | team_code).
   ac6 passes as written. It loosens the policy, so it needs the coach's approval. Proposed sentence,
   after "the provenance sidecar of a built file,": "the metadata.json published beside it in the
   private buckets' files/ prefix, which repeats each source's school and team code as disclosed so
   that a takedown finds every file built from them (version 1.19),". Proposed row for "What a
   report may show": "Published built file's metadata.json (E33, v1-e33-t05) | School and team code
   per source, as disclosed, and the lists of them, inside the team only, in the private buckets. No
   tournament, round, debater or path (version 1.19)."
B. No policy change. The lookup by school or team code reads the published .provenance.json objects
   in files/, which the policy already allows and which Attribution rule 3 already makes "what a
   removal request is matched against". metadata.json keeps the source fields only. ac6 amended to:
   "Given a source sha256 (over metadata.json) or a school or team code (over the published
   provenance sidecars), a lookup returns exactly ...". Same number of object reads as A. The V2 tub
   (v2-e35-t02) would index school and team from the sidecars, which it reads anyway to show
   provenance (tub gate item 7).
C. Keyed digests of school and team code in metadata.json. Not personal data in the clear, but it
   needs a key the takedown and the tub share, which is more machinery than either A or B.

Recommendation: B. The policy already names the sidecar as the record removals are matched against.
B adds no new place a school or team code lives, so it needs no new policy version and no coach
approval. It costs no more reads than A, and it keeps the object the tub indexes free of other
schools' names.

QUESTION 2 (ac7). ac7 says the uploaded recipe "still resolves to the same occurrences". It does
when the removed fields were not needed. But files suggest adds side, then tournament, then round,
then school and team code only when the same bytes were disclosed by more than one team, so a pin
that has them needed them. With them removed it no longer resolves: an ad-hoc run (two teams, same
bytes, same side, pin naming the second team) gives PIN_MISMATCH for the published pin, where the
original resolves. Before upload the service checks that every published pin still names the
sidecar's source and first element for its card, and the sidecar beside it names the disclosure.
Options:
A. Amend ac7 to: "... holds none of those fields in any pin; every pin still names the card's source
   and element as the sidecar records them, and the recipe resolves to the same occurrences wherever
   no removed field was needed to tell two disclosures apart, by test." This is what is built and
   tested. (Recommended: the published recipe is a record of the file. The sidecar beside it is what
   identifies each occurrence, and the policy forbids the fields that would make it a rebuild input.)
B. Make the published recipe a rebuild input: a new pin field that tells disclosures apart without
   naming them. A plain disclosure digest would not do, because it is an unkeyed sha256 of
   <caselist>/<path> and the path names the team. That is a recipe-format change (t01's domain),
   outside this task.

FYI, proceeding unless told otherwise:
1. A published pin also loses its side. Your amendment of 2026-10-19 named school, team_code,
   tournament and round. Policy 1.15 (2026-10-24) says a published recipe "loses every such field",
   and its list is "a pin's side, tournament, round, and school and team code". I followed the
   policy (agreement 7). ac7's wording would want "side" added.
2. files publish takes --env (required) and --confirm-prod, as tub index publish does, and
   --recipes <dir>, because a built file does not record where its recipe is (default
   <data dir>/files/recipes/<topic>/<slug>.yaml, hash checked against the sidecar). The spec's
   signature was "files publish <path> [--dry-run]".
3. A sidecar written before this task records no recipe status, and is refused as
   RECIPE_STATUS_UNRECORDED until the file is rebuilt. Nothing has been published yet, so no
   published file is affected.

IAM: no grant needed. The everyday evidence permission sets allow PutObject on bucket/* and list
files/, and the publish uses that profile.

Please reply with: Q1 A, B or C; Q2 A or B; and any FYI you want changed.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
