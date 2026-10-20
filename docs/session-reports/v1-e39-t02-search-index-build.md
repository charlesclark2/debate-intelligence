# Session report: v1-e39-t02-search-index-build

| | |
|---|---|
| Task | `v1-e39-t02-search-index-build` — tub index build and publish: one searchable document per card cluster, from the parsed store |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t02-search-index-build.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t02-search-index-build.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t02-search-index-build` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`debate-research tub index build` now builds the student search pilot's index from the local parsed
store: one SQLite FTS5 file, one document per card cluster under `card-fingerprint-v4`, its gzip
object (level 6, mtime 0, no name) and a manifest validated by a committed JSON Schema. The same
store gives the same bytes for all three, under six orders of the store. `tub index publish --env
dev|prod` uploads the object, then the manifest, then `reports/tub/search/current.json` last. It
checks each against the manifest's digest as it lands, and refuses a parser, fingerprint or format
version mismatch before uploading anything. School, team code, tournament and round sit only in a
stored `occurrences` table that no FTS5 table covers. The SQLite 3.40.0 ceiling is proven two ways:
a traced-statement check in every run, and a slow test that opens a built index with the Lambda
image's own SQLite (3.40.0). Given an index that uses a 3.47 option, that image refuses it with
`unrecognized option: "locale"`. The phase stays **InProgress**: ac6, the operator's full-store build
with its time, peak memory and size, needs the operator's run (Operator follow-ups 1). **PM, look
first at** Deviation 2 (the camp file title is stored, against "never store a file name") and the
relay block under Decisions.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `index-build` — Search index build and publish | Done, but for ac6 | Every criterion but ac6 passes; ac6 is the operator's full-store build |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — one document per cluster with a surviving occurrence, representative by the stated order under five shuffles, by tests shown failing first | PASS | Red: the tests run against a refuse-nothing skeleton of the committed service (representative = first row listed, suppression and holds ignored, tag and cite blank): `uv run pytest packages/debate_core/tests/application/test_search_index_build.py -q -p no:randomly -n0` → `15 failed, 22 passed`. The failures include all six `test_search_index_representative_follows_the_order_under_five_shuffles[None, 1–5]` and `..._camp_representative_is_the_attributed_latest_release`. Green: same command on the real service → `37 passed`. One cluster per step of the order (completeness, attribution, recency, smallest key); expected representatives written by hand (`STANDARD_REPRESENTATIVES`) |
| ac2 — school, team code, tournament and round only in provenance columns; a full-text query for them matches nothing (E39 gate item 8) | PASS | `test_search_index_school_and_team_code_match_nothing`: the fixture's two schools, team codes, tournament and round are in `occurrences`, and `MATCH` for each, and for `Grove`, `Riverbend`, `Invitational`, gives 0 while `"invented hegemony"` gives 1. `test_search_index_searches_only_tag_cite_read_aloud_and_text`: the FTS5 table's columns are exactly the four. Mutants putting the school in `read_aloud`, and the team code and round in `cite`, are both killed by the first test |
| ac3 — a suppressed occurrence never appears; a cluster with none surviving is absent | PASS | `test_search_index_leaves_out_a_suppressed_occurrence_and_an_emptied_cluster` (whole-source and one-disclosure suppressions; the emptied cluster's text matches nothing; counts 4 documents, 3 suppressed, 1 left out) and `test_search_index_leaves_out_a_row_a_path_hold_covers`, red under the skeleton, green on the service; three suppression mutants killed |
| ac4 — byte-identical index and manifest; manifest validates against a committed schema with a drift test | PASS | `test_search_index_same_store_gives_identical_bytes_under_shuffles`: the SQLite file, gzip object and manifest are each one value across six builds, and so is the index id. `test_search_index_manifest_schema_committed_matches_the_models` (drift, as `v1-e33-t02`'s) and `test_search_index_manifest_validates_against_the_committed_schema` (jsonschema) pass. `uv run scripts/export_search_index_schema.py --check` → `OK` |
| ac5 — `publish` writes the pointer last and refuses a version mismatch, against the S3 test double; layout document and listing grant name `reports/tub/search/` | PASS | `uv run pytest packages/debate_core/tests/application/test_search_index_publish.py -q -n0` → `11 passed`, against moto through `S3EvidenceObjectStore`: write order object, manifest, `current.json`; a refused write at each of the three leaves the previous pointer; parser, fingerprint and format mismatches upload nothing; an object landing with another digest stops before the pointer. CLI, through the real app over moto: `uv run pytest packages/debate_cli/tests/test_tub_index.py -q -n0` → `6 passed`. Layout: `docs/architecture/evidence-store-layout.md` (prefix table, example keys, a `reports/tub/search/` section, the access table). Grant: `infrastructure/modules/evidence_bucket/operator_access.tf` `named_list_prefixes`; `terraform test` → `13 passed, 0 failed`, and with the expectation removed → `12 passed, 1 failed` (`operator_permission_set_reads_and_publishes_but_cannot_delete`) |
| ac6 — the operator's full-store build recorded in the report and docs/data: documents, size, build time, peak memory | **NOT RUN** | Operator-run by the spec's forbidden list. The command is Operator follow-ups 1; `docs/data/search-index.md` has the table, with a "Not yet run" row |
| ac7 — gzip byte-identical; manifest's two sha256, SQLite version and format version checked by test; a test opens the index with SQLite 3.40.0's feature set, by a check the report names | PASS | Identical gzip: as ac4. `test_search_index_manifest_records_both_digests_and_the_versions` and `test_search_index_gzip_header_has_no_time_and_no_name`. **The checks named:** in every run, `test_search_index_writer_runs_only_statements_sqlite_3_40_has` traces every statement against a hand-written list; `test_search_index_fts5_table_takes_only_options_3_40_has` and `test_search_index_file_is_the_schema_written_by_hand` check the options, schema and header. Marked slow: `test_search_index_opens_in_the_lambda_image_sqlite` opens a built index in `public.ecr.aws/lambda/python:3.12` by `docker run --network none`. `uv run pytest packages/debate_core/tests/integrations/local/test_search_index_sqlite_features.py -m "slow or not slow" -n0` → `4 passed` (the docker test 0.56 s). Shown failing: an FTS5 `locale=1` mutant → `3 failed, 1 passed`, and the image says `sqlite3.OperationalError: unrecognized option: "locale"`; a `journal_mode = WAL` mutant → `3 failed, 1 passed` |
| ac8 — tag and cite from the document record, `None` for no tag; no document for a source no occurrence row names, by tests shown failing first | PASS | `test_search_index_tag_and_cite_come_from_the_document_record` was red under the skeleton (tag and cite not taken from the record) and is green. `test_search_index_holds_nothing_from_a_source_no_occurrence_row_names` was red under a second skeleton that indexes every card of each source it reads (`1 failed`, `matches('"invented colonies"') == 1`) and is green |
| Node criterion — `uv run pytest packages/debate_core/tests packages/debate_cli/tests -k "tub_index or search_index"` | PASS | → `57 passed in 10.06s` |

## Files changed

* **`packages/debate_core/src/debate_core/domain/search_index.py`** (new): the manifest, pointer, format
  version, the 3.40.0 ceiling, the published keys, the schema renderer.
* **`packages/debate_core/src/debate_core/application/ports/search_index.py`** (new): the writer port
  and what it is handed (`SearchDocument`, `IndexedOccurrence`), with no field for a path or cutter mark.
* **`packages/debate_core/src/debate_core/application/search_index_build.py`** (new): which rows, the
  suppression and hold rules, the representative order, the read-aloud text, the cutter-mark strip,
  the manifest.
* **`packages/debate_core/src/debate_core/application/search_index_publish.py`** (new): the checks and
  the three writes in order.
* **`packages/debate_core/src/debate_core/integrations/local/search_index.py`** (new): the SQLite FTS5
  writer and the gzip step, in `local` so no import-linter list or `pyproject.toml` changes.
* **`packages/debate_cli/src/debate_cli/commands/tub_index.py`, `commands/__init__.py`, `container.py`**:
  the `tub index build|publish` commands, the `tub` group (`v1-e39-t05` adds `tub users` to it), and
  their wiring.
* **Tests**: `packages/debate_core/tests/application/test_search_index_build.py` (37),
  `.../test_search_index_publish.py` (11), `.../integrations/local/test_search_index_sqlite_features.py`
  (3 plus 1 slow), `packages/debate_cli/tests/test_tub_index.py` (6); the hand-written lists in
  `test_doctor.py`, `test_installation.py` and `test_app.py` gain the new adapter module and the two
  services.
* **`docs/data/search-index-manifest.schema.json`** (generated) and **`scripts/export_search_index_schema.py`**
  (Deviation 1).
* **Docs**: `docs/data/search-index.md` (the schema, manifest, pointer and the full-store build record),
  `docs/guides/search-index.md` (the operator's build and publish), `docs/architecture/evidence-store-layout.md`.
* **`infrastructure/modules/evidence_bucket/operator_access.tf` and its `tftest.hcl`**: the listing
  grant names `reports/tub/search/`.

## Deviations from the spec

1. **A file outside `constraints.packages`: `scripts/export_search_index_schema.py`.** ac4 asks for the
   committed schema "as v1-e33-t02's sidecar schema does", and that pattern is a generated file, a drift
   test, and an export script that writes it (`scripts/export_file_provenance_schema.py`). The new script
   is that script with the names changed. Without it the drift test's message would have no command to
   give. The PM may add `scripts/export_search_index_schema.py` to the spec's packages.
2. **The camp file title is stored, against "never stored: a file name".** The PM's notes and the spec
   both say never to store a file name. The data-use policy's Attribution rule 2 says a camp card's
   provenance line names "camp, year, event and file title", and E39 gate item 7 says the line is shown
   with every camp card. `CampFile.file_title` is the importer's title, the file name without its
   extension, camp, year and lab initials. It is not the file name, holds no school or team code, and
   is what `v1-e33-t06`'s writer prints. So `occurrences.camp_file_title` keeps it, stored and never
   searchable. No path, caselist file name or disclosure path is stored anywhere
   (`test_search_index_stores_no_path_or_file_name`). If the PM reads "file name" to include the camp
   title, the change is one line in `_occurrence` (`camp_file_title=None`). The pilot's camp lines then
   lack the title, which needs a policy note. Relay question 1.
3. **Every surviving occurrence is stored, not only the first `provenance_limit`.** The spec stores "the
   provenance of up to a configured number of occurrences". The index keeps that, and also each other
   occurrence's source sha256 and disclosure digest, with its provenance columns null. `v1-e39-t07` hides
   a newly suppressed occurrence at run time, and "a card left with no occurrence answers as not found".
   It can only do that knowing every occurrence's digests, and digests are what the suppression list
   itself holds. About 235,000 rows; the size shows in ac6.
4. **Path holds are applied as well as the suppression list's own entries.** The spec says "the
   suppression list applies". Holds live beside the list and govern the same rows, so the build asks
   `publish_plan.stored_row_hold` for each disclosure of a row, as `v1-e33-t03`'s PM amendment of
   2026-10-20 has the resolver ask it. A rebuilt occurrence table already excludes them; this catches a
   hold merged before the next `caselist parse`.
5. **`--env` confirms `DEBATE_ENV` rather than choosing the bucket.** Every CLI command takes its bucket
   from `DEBATE_ENV` and nothing else ("No flag overrides the bucket", `commands/store.py`). So `publish
   --env X` is refused (`ENVIRONMENT_MISMATCH`) unless `DEBATE_ENV` is `X`, and prod also needs
   `--confirm-prod`, as `caselist publish` does. Relay question 3.
6. **No smoke check.** `plan_specs/README.md` asks a task that adds a CLI command for a `tests/smoke/`
   node; this spec has none, and `tests/smoke` is not in its packages. Follow-up 1.

## Decisions and assumptions

* **The build is offline.** It reads this environment's local copy of the suppression list, as
  `caselist parse` without `--publish` and the importers do; it reaches no bucket. A removal recorded
  only in the bucket's copy reaches the function within five minutes anyway (`v1-e39-t07`, ADR-0019
  (c) 5), and the next build after `store sync --pull` leaves it out. Relay question 2.
* **A cluster is one cluster id in one store.** Each store's occurrence table is clustered on its own,
  and the PM's scale (hsld26 11,675, hspf26 10,365, hspolicy26 18,772, openev 5,846) is per store, so
  documents are keyed on (caselist, cluster id).
* **`--caselist` is required and repeatable.** The port has no listing of stores, and naming them makes
  what students can search the operator's explicit choice; the manifest records them.
* **External-content FTS5.** The searchable text is stored once, in `documents`; `highlight()`,
  `snippet()` and `bm25()` work over it in 3.40.0 (the docker check runs all three). Indexing is done at
  the end by FTS5's `rebuild` in `doc_id` order, then `optimize` and `VACUUM`, which is why insertion
  order plays no part in the bytes.
* **Read-aloud text** is the union of UNDERLINE and HIGHLIGHT spans, stretches joined by one space.
  EMPHASIS is inside underlining by convention, and BOLD and SHRUNK are not read aloud.
* **The cutter mark** is removed at any length. `extract_cutter_mark` drops a token over 16 characters
  "rather than truncated", and such a token would then have stayed in the stored cite.
  `cite_without_cutter_mark` keeps the URL-scheme exception and leaves a cite of nothing but a mark as
  it is. A cutter mark that does not follow the `//` convention is not recognised, here or anywhere.
* **Camp documents have no first or last seen.** A release (`2026-policy`) has no date, so `first_seen`
  and `last_seen` are null for `openev`. `v1-e39-t03`'s "first seen on or after" filter needs a rule
  for them. Follow-up 2.
* **Not stored:** undertag and section headings. The spec does not list them, and headings are where
  names in document bodies turn up.
* **The index id** is the first 16 hex characters of the SQLite file's sha256, so a rebuild of an
  unchanged store has the same id and `<data_dir>/tub-index/<id>/` is replaced by identical bytes.
* **`<data_dir>/tub-index`** sits outside `<data_dir>/objects`, the only tree `store sync` moves by
  name, so an index reaches a bucket only through `publish`'s ordered writes.

**Relay prompt for the PM** (paste as is):

> v1-e39-t02 has three questions; each has a recommendation and works as built until you say otherwise.
>
> 1. **Camp file title.** The spec says never store a file name; Attribution rule 2 and E39 gate item 7
>    need a camp card's line to name its file title. Options: (a) store `CampFile.file_title` (the
>    importer's title, without extension, camp, year or lab initials), stored and never searchable, and
>    amend the spec's "never stored" to "a disclosure path or a caselist file name"; (b) store no title
>    and add a policy note that pilot camp lines omit it. **Recommend (a)**: it is what built files'
>    lines already print, and it holds no person.
> 2. **Suppression copy.** The build reads only this machine's suppression list, offline. Options: (a)
>    keep; (b) read the local and bucket copies together, as bucket-holding commands do, which makes the
>    build need an SSO session. **Recommend (a)**: `v1-e39-t07` hides a new removal within five minutes
>    whatever the index holds, and `v1-e39-t09`'s weekly stage runs after the sync that merges the copies.
> 3. **`--env`.** Built as a confirmation that must equal `DEBATE_ENV`, never an override. Options: (a)
>    keep; (b) let `--env` choose the bucket. **Recommend (a)**: it is the rule every other bucket command
>    keeps, and a typo cannot reach prod.

## Operator follow-ups

**1. The full-store build (ac6).** Expected runtime 15 to 40 minutes: it reads and validates about
7 GB of document records, one per source an occurrence row names. It reads the dev data directory,
where the `2026.10.18-docx-5` store lives, and writes about 0.5 GB under
`~/.debate-research/dev/tub-index/`. It reaches no bucket and calls no model. `/usr/bin/time -l` runs
the venv's `debate-research` itself, so its maximum resident set size is the build's peak memory.

Where: your Mac, in this task worktree.
```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e39-t02-search-index-build
uv sync --all-packages
DEBATE_ENV=dev /usr/bin/time -l .venv/bin/debate-research --json tub index build --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev > /tmp/tub-index-build.json 2> /tmp/tub-index-build.time
grep -E "real|maximum resident" /tmp/tub-index-build.time
python3 -c "import json; m = json.load(open('/tmp/tub-index-build.json'))['data']['manifest']; print(json.dumps({k: m[k] for k in ('index_id', 'sqlite_version', 'snapshot', 'counts', 'sqlite_file', 'gzip_object')}, indent=2))"
```
Success looks like: a `real` time, a `maximum resident set size` in bytes, and a JSON block with about
46,700 documents (`documents_by_store` near hsld26 11,675, hspf26 10,365, hspolicy26 18,772,
openev 5,846) and the two file sizes. It holds counts, versions and digests only. Paste all of it back.
A `SEARCH_INDEX_STORE_NOT_READY` error instead names the store and the `caselist parse` that fixes it.

Then open the real index in the Lambda image's SQLite, as the slow test does with a synthetic one.
Expected runtime under a minute. Replace `INDEX_ID` with the `index_id` above.
```bash
docker run --rm --pull never --network none --platform linux/arm64 --entrypoint python3 -v "$HOME/.debate-research/dev/tub-index/INDEX_ID:/index:ro" public.ecr.aws/lambda/python:3.12 -c "import sqlite3; c = sqlite3.connect('file:/index/search-index.sqlite?mode=ro', uri=True); print(sqlite3.sqlite_version, c.execute('PRAGMA integrity_check').fetchone()[0], c.execute('SELECT count(*) FROM documents').fetchone()[0])"
```
Success looks like: `3.40.0 ok` and the document count. Paste it back.

**2. The listing grant in dev, after this PR merges into `dev`.** Apply from a checkout with every merged
task: the dev-preview worktree, whose `infrastructure/envs/dev/owner.auto.tfvars` is complete (two
`evidence_search` lines). If you use it for the site preview, run `pnpm install` after the pull as
usual. Expected runtime about 3 minutes.

Where: the dev-preview worktree.
```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/dev-preview
git pull --ff-only
aws sso login --sso-session debate
export AWS_PROFILE=debate-admin
grep -c evidence_search infrastructure/envs/dev/owner.auto.tfvars
terraform -chdir=infrastructure/envs/dev init
terraform -chdir=infrastructure/envs/dev plan -out=/tmp/search-listing-dev.tfplan
```
Read the plan before applying it. Success looks like: `2`, and then exactly
`Plan: 0 to add, 1 to change, 0 to destroy.` The one change is
`module.evidence_store.aws_ssoadmin_permission_set_inline_policy.evidence_operator[0]`, whose
`ListDocumentedEvidencePrefixes` statement's `s3:prefix` list gains `reports/tub/search/` and
`reports/tub/search/*`. If it shows anything else, above all an account assignment destroyed, stop and
paste the plan: that is a missing or stale `owner.auto.tfvars`.

```bash
terraform -chdir=infrastructure/envs/dev apply /tmp/search-listing-dev.tfplan
```
Success looks like: `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.`

**3. The listing grant in prod, after the promotion to `main`.** The same steps from a `main` worktree
(prod applies run from `main`). Copy its `infrastructure/envs/prod/owner.auto.tfvars` from the checkout
that last applied prod if it has none, and check `owner` against the deployed `Owner` tag first, as
`docs/runbooks/evidence-search.md` "Before you start" gives it. Then run the block above with
`infrastructure/envs/prod` and `/tmp/search-listing-prod.tfplan`; success looks the same. No delete
grant is added: that is `v1-e39-t07`'s.

No publish is needed for this task. The first one, to dev, is `docs/guides/search-index.md`'s
"Publish" once a build exists.

## Follow-up work

1. **Smoke checks for `tub index build|publish`** (`v1-e39-t10`, or an amendment here): a dev smoke check
   that builds a synthetic index and publishes it to the dev bucket.
2. **Camp documents and the "first seen" filter** (`v1-e39-t03`): `first_seen` and `last_seen` are null
   for `openev` documents, whose releases have no date; t03 decides whether the filter keeps or drops them.
3. **A representative suppressed at run time** (`v1-e39-t07`): the index holds the representative's text
   only. When the function's newer list stops the representative but not the cluster, it either hides the
   card until the next build or shows the representative's text under another occurrence's line.
   Recommend hiding it until the rebuild, since the shown text would be the suppressed file's.
4. **`v1-e39-t09`** can tell "the store changed" from the manifest's `stores[].occurrences_sha256` and
   `suppression.sha256`, which change exactly when the rows or the list do.

## Checks run before the report

* `uv run scripts/affected_tests.py --run` → 128 of 330 test files (38.8%), 3,339 tests. It hit the
  two-minute stop (`perl -e 'alarm 115'`) at about 93%, with one failure:
  `packages/debate_cli/tests/test_app.py::test_doctor_reports_the_environment_as_json`, whose hand-written
  service list lacked the two new services. Fixed in `c65802c`. Re-running it does not fit in two minutes
  on this machine (load average 13 to 31 from other work), so by working agreement 10 the PR's `ci`
  runs it. Within the limit:
  * `uv run pytest packages/debate_cli/tests tests/architecture tests/specs -q` → `1 failed, 926 passed`;
    that one was the `test_app.py` list, then `test_app.py` → `31 passed` after the fix;
  * `uv run pytest packages/debate_core/tests/integrations/local packages/debate_core/tests/application/test_search_index_build.py packages/debate_core/tests/application/test_search_index_publish.py packages/debate_core/tests/application/test_evidence_sync.py packages/debate_core/tests/application/test_file_recipes.py packages/debate_core/tests/domain -q`
    → `1064 passed`.
* `uv run ruff format --check .` → `927 files already formatted`; `uv run ruff check .` → `All checks passed!`
* `uv run pyright packages/debate_core packages/debate_cli scripts/export_search_index_schema.py` → `0 errors`
* `uv run lint-imports` → `Contracts: 12 kept, 0 broken.`; `uv run scripts/check_thin_handlers.py` → `OK`
* `scripts/terraform_checks.sh` → fmt, validate and tflint `ok` for every root and module. Its test phase
  hit the two-minute stop after `domain_redirect` `ok`. `terraform test` in `modules/evidence_bucket` on
  its own → `13 passed, 0 failed`; the modules it did not reach are unchanged here.
* `uv run scripts/check_command_blocks.py`, `uv run scripts/check_links.py`,
  `uv run scripts/docs_index.py --check-descriptions` → OK.
* **Mutation, 20 mutants** over the representative order, privacy, suppression, determinism, the manifest
  and publish: 19 killed at first, one survivor ("publish: landed digest not checked"). A test was added
  for it (`test_search_index_publish_stops_before_the_pointer_when_the_object_lands_with_another_digest`)
  and it was killed on the re-run: 20 of 20.
* `uv run scripts/validate_specs.py` → `OK: 396 files, 39 epics, 336 tasks, 21 releases`; the task Goal stays `InProgress` (ac6).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
