# Session report: v1-e30-t02-caselist-domain-model

| | |
|---|---|
| Task | `v1-e30-t02-caselist-domain-model` — Caselist domain model |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t02-caselist-domain-model.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t02-caselist-domain-model.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t02-caselist-domain-model` |
| Session status | COMPLETE |

## Summary

`debate_core.domain.caselist` now holds the vocabulary that the weekly archive importer (t03), the
OpenEv importer (t04), the S3 publisher (t05), the source-removal command (t07), the E31 parser and
the E32 landscape reports will all read: seven frozen Pydantic models (`Caselist`, `School`,
`TeamCode`, `ArchiveSnapshot`, `SourceDocument`, `Disclosure`, `CampFile`) built on validated
scalars that refuse the bad data this area actually produces — a caselist slug that is not a slug,
a snapshot dated in the future, a "team code" that is really a person's name. `CaselistRepository`
joins the ports in `debate_core.application.ports`, keyed naturally throughout (snapshot by
`(caselist, date)`, source by `sha256`, disclosure by `(caselist, snapshot, path)`) because weekly
archives are cumulative and a re-import has to be a no-op rather than a duplicate;
`InMemoryCaselistRepository` implements it in the shared fakes module.

Two things are worth the PM's eye. First, the data-minimization guard
(`tests/domain/caselist/test_minimization.py`) pins every model's exact field set *and* bans
name-shaped field names, so a `debater_name` field cannot be added without a deliberate edit to a
file that explains why the rule exists. Second, `uv run lint-imports` — one of the
`minimization-and-gates` node's criteria — cannot run: import-linter is introduced by
`v1-e02-t06-import-boundary-guard`, which is still `Pending`. It is recorded below as NOT RUN with
an equivalent check run in its place, and it is the one criterion not satisfied as written.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `value-types` — Caselist value types and enums | COMPLETE | `values.py`: `CaselistSlug`, `Season`, `TeamCodeText`, `SnapshotDate`, the `Event`/`Side`/`SourceFormat`/`SourceOrigin`/`Acquisition`/`CompetitionLevel` enums, `RoundLabel` and the round-normalization table. |
| `entities` — Caselist entities | COMPLETE | `entities.py`: the seven frozen models, each carrying its own provenance and pinned to `ProvenanceMode.FILE_IMPORT`. |
| `repository-port` — CaselistRepository port and in-memory fake | COMPLETE | `application/ports/caselist.py` plus `InMemoryCaselistRepository` in `debate_core/testing/fakes.py`. Fake path differs from the spec's `outputs` — see Deviations. |
| `minimization-and-gates` — Data-minimization guard and quality gates | COMPLETE except `lint-imports` | Guard and `pyright` pass; `lint-imports` is not installable yet — see Deviations. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Goal ac1 — the seven entities are frozen Pydantic models in `debate_core.domain.caselist`, with docstrings, and round-trip through JSON | PASS | `uv run pytest packages/debate_core/tests/domain/caselist/test_entities.py` → `81 passed`. Covers `test_the_seven_entities_are_the_ones_the_spec_names`, `test_every_entity_is_frozen_and_forbids_unknown_fields`, `test_every_entity_has_a_docstring`, `test_every_entity_round_trips_through_json` (one populated instance of each of the seven). |
| Goal ac2 — validators reject a malformed sha256, a slug not matching `^[a-z]+[0-9]{2}$`, a future snapshot date, and a team code over 12 characters or containing whitespace-separated words | PASS | `uv run pytest packages/debate_core/tests/domain/caselist/test_values.py` → `85 passed`. Covers `test_a_malformed_sha256_is_rejected` (6 cases), `test_a_malformed_caselist_slug_is_rejected` (7 cases), `test_a_snapshot_date_in_the_future_is_rejected`, `test_a_team_code_longer_than_the_limit_is_rejected` and `test_whitespace_separated_words_are_rejected_as_a_name` (4 cases). |
| Goal ac3 — Side accepts AFF/NEG for LD and Policy and PRO/CON for PF, UNKNOWN for any event; RoundLabel keeps raw plus a normalized value or None | PASS | `test_values.py` (`test_each_event_allows_its_own_sides_plus_unknown`, `test_a_recognised_round_token_normalizes` — 17 cases, `test_an_unrecognised_round_token_normalizes_to_none` — 8 cases) and `test_entities.py` (`test_ld_and_policy_disclosures_accept_aff_neg_and_unknown`, `test_pf_disclosures_accept_pro_con_and_unknown`, `test_a_pf_side_in_an_ld_or_policy_disclosure_is_refused`, `test_an_aff_neg_side_in_a_pf_disclosure_is_refused`). Both suites pass. |
| Goal ac4 — a `CaselistRepository` port (upsert snapshot, get/put SourceDocument by sha256, record disclosures and camp files, list by caselist/snapshot/team, latest snapshot) in `debate_core.application.ports`, with an in-memory fake | PASS | `uv run pytest packages/debate_core/tests/application/test_caselist_fake_repository.py` → `33 passed`. Every named method has tests; `test_the_fake_satisfies_the_port_at_runtime_and_statically` checks conformance at runtime and (via the annotated `build_fake_caselist_repository`) under pyright strict. |
| Goal ac5 — no caselist model has a field for full names, and a test asserts the model field sets so that adding one fails CI | PASS | `uv run pytest packages/debate_core/tests/domain/caselist/test_minimization.py` → `20 passed`. `EXPECTED_FIELDS` pins all eight models' field sets exactly; `test_no_field_name_suggests_personal_data` bans 16 name-shaped fragments; `test_the_only_name_fields_are_an_institutions_name_and_a_caselist_label` allows only `School.name` and `Caselist.display_name`. |
| Node `value-types` — Value type validation tests pass | PASS | `uv run pytest packages/debate_core/tests/domain/caselist/test_values.py` → `85 passed in 1.73s`. |
| Node `entities` — Entities module defines `Disclosure` (`artifact_exists`, `contentMatch: "class Disclosure"`) | PASS | `grep -c "class Disclosure" packages/debate_core/src/debate_core/domain/caselist/entities.py` → `1`. |
| Node `entities` — Entity JSON round-trip tests pass | PASS | `uv run pytest packages/debate_core/tests/domain/caselist/test_entities.py` → `81 passed in 1.72s`. |
| Node `repository-port` — Fake repository behaves per the port | PASS | `uv run pytest packages/debate_core/tests/application/test_caselist_fake_repository.py` → `33 passed in 1.73s`. |
| Node `minimization-and-gates` — Data-minimization guard passes | PASS | `uv run pytest packages/debate_core/tests/domain/caselist/test_minimization.py` → `20 passed in 1.59s`. |
| Node `minimization-and-gates` — Type check passes for `debate_core` | PASS | `uv run pyright packages/debate_core` → `0 errors, 0 warnings, 0 informations`. |
| Node `minimization-and-gates` — Import boundaries hold (`uv run lint-imports`) | **NOT RUN** | `uv run lint-imports` → `error: Failed to spawn: lint-imports / No such file or directory (os error 2)`. import-linter is not a dependency yet: it is introduced by `v1-e02-t06-import-boundary-guard`, whose Goal is `Pending`. Equivalent check run instead: `test_port_conformance.py::test_port_modules_import_nothing_from_a_provider_library` was extended to the new `caselist` port module (`uv run pytest packages/debate_core/tests/application/test_port_conformance.py` → `15 passed`), and `uv run pyright packages/debate_core` passes with no import from `boto3`, `botocore`, `httpx`, `sqlite3`, `typer` or `fastapi` anywhere in the new modules. See Deviations. |
| Whole default suite still green | PASS | `uv run pytest` → `701 passed in 18.41s`, with 100% line and branch coverage on `domain/caselist/values.py`, `domain/caselist/entities.py` and `testing/fakes.py`. |
| Formatting and lint | PASS | `uv run ruff format --check .` → `155 files already formatted`; `uv run ruff check .` → `All checks passed!`. |
| Spec validation | PASS | `uv run scripts/validate_specs.py` → `OK: 281 files, 38 epics, 223 tasks, 20 releases`. |

## Files changed

**`packages/debate_core/src/debate_core/domain/caselist/`** (new subpackage) — `values.py` holds the
validated scalars, the closed vocabularies and `RoundLabel` with its normalization table;
`entities.py` holds the seven frozen models; `__init__.py` re-exports them and defines
`CASELIST_MODELS`, the tuple the minimization guard iterates so a new entity is covered the moment
it is added.

**`packages/debate_core/src/debate_core/application/ports/`** — new `caselist.py` declaring the
`CaselistRepository` Protocol; `__init__.py` re-exports it and adds its row to the port table (the
module heading no longer says "ten", since there are now eleven).

**`packages/debate_core/src/debate_core/testing/`** — `fakes.py` gains
`InMemoryCaselistRepository` and `build_fake_caselist_repository()`; `__init__.py` re-exports both.
The fake is deliberately *not* added to `FakePorts`, because a caselist repository is not one of the
ten ports every service takes — only the E30/E31/E32 code asks for it, and by name.

**`packages/debate_core/tests/`** — `domain/caselist/test_values.py` (85 tests),
`domain/caselist/test_entities.py` (81), `domain/caselist/test_minimization.py` (20) and
`application/test_caselist_fake_repository.py` (33). One line changed in
`application/test_port_conformance.py`: its provider-import guard now also covers the `caselist`
port module.

**`packages/debate_core/README.md`** — a section for `domain/caselist/` and rows for the new port
and fake, following the existing per-module tables.

**`plan_specs/v1/e30-caselist-ingestion/t02-caselist-domain-model.yaml`** — Goal `status.phase` set
to `Succeeded`.

## Deviations from the spec

1. **`uv run lint-imports` could not be run (node `minimization-and-gates`).** import-linter is not
   a workspace dependency and there is no `.importlinter` contract file: both are introduced by
   `v1-e02-t06-import-boundary-guard`, which is `Pending` and is not a prerequisite of this task.
   Installing import-linter and writing the repo-wide contracts here would take over that task's
   scope, so the criterion is reported NOT RUN. What the criterion is *for* is checked another way:
   `test_port_conformance.py`'s provider-import guard now covers the `caselist` port module, and
   nothing in the new code imports `boto3`, `botocore`, `httpx`, `sqlite3`, `typer` or `fastapi`.
   The criterion will pass unchanged once E02-t06 lands.

2. **The in-memory fake is in `debate_core/testing/fakes.py`, not
   `debate_core/application/fakes/caselist.py`.** The node's `outputs` name the second path, but
   the node's own description says "an in-memory fake in the shared fakes module", and the shared
   fakes module established by `v1-e02-t02-ports` is `debate_core.testing.fakes` — there is no
   `debate_core.application.fakes` package. Putting it where every other fake lives keeps
   `debate_core.testing` the single import for test doubles across `debate_cli`, `debate_api` and
   `debate_workers`. Suggested spec amendment: change that `outputs` entry to
   `packages/debate_core/src/debate_core/testing/fakes.py`.

3. **`Disclosure` carries an `event` field, which the spec's entity list does not name.** ac3
   requires that "Side accepts AFF/NEG for LD and Policy and PRO/CON for PF". Enforcing that on the
   model needs the event on the record; without it the rule could only live in a helper function
   that a caller may forget to call. A Public Forum disclosure marked `AFF` is now rejected where
   it is built. The cost is one denormalized enum per disclosure, which the manifest rows (t03 ac4)
   want anyway. Suggested spec amendment: add `event` to the `Disclosure` field list.

4. **`CampFile` carries `snapshot` and `parse_warnings`, which the spec's entity list does not
   name.** `snapshot` is the import date the release was recorded under — every other imported
   record names the snapshot it was seen in, and `SourceDocument` requires a first/last seen
   snapshot, so an OpenEv file needs one too. `parse_warnings` is what t04 ac1 asks for ("camp
   `UNKNOWN` and a warning, not a failure") and mirrors `Disclosure.parse_warnings`. Suggested spec
   amendment: add both to the `CampFile` field list.

5. **Two spec names collide, and were split.** The `value-types` node lists `TeamCode` as a value
   type while ac1 lists `TeamCode` as an entity. The constrained string is therefore `TeamCodeText`
   and the entity is `TeamCode`. Likewise the node lists `Sha256` as a value type; rather than
   define a second SHA-256 scalar, `debate_core.domain.caselist` re-exports the existing
   `Sha256Hex` from `debate_core.domain.base`, so both areas validate hashes the same way.

## Decisions and assumptions

* **The caselist models extend `DomainModel`, not `DomainEntity`.** Their identities are natural —
  a caselist is its slug, a source document is its SHA-256, a snapshot is its `(caselist, date)` —
  and an import re-states what a public archive says rather than recording an edit somebody made.
  So there is no ULID to mint, no `owner_id`/`organization_id` to fill in and no `revision` to race
  for. This also keeps the field sets small enough for the minimization guard to read at a glance.

* **`debate_core.domain.caselist` is not re-exported from `debate_core.domain`.** `Event` and
  `Side` are unambiguous inside caselist code and ambiguous outside it, so callers import from
  `debate_core.domain.caselist` explicitly. This also keeps the E02 domain namespace and its
  `__all__` untouched.

* **The caselist entities are not added to `EXPORTED_MODELS` / `packages/debate_core/schemas/`.**
  The published JSON Schemas are the contract for the web client and the V2 API; disclosed caselist
  data is internal to the import pipeline and the spec does not ask for schemas. Worth revisiting
  when E32's reports get a surface that serves this data.

* **`put_source` widens the first/last seen snapshot range in both directions.** Weekly archives
  are cumulative, and t03 allows `--allow-out-of-order`, so an older archive imported later must
  pull `first_seen_snapshot` back rather than overwrite the range. Contradictory bytes under one
  hash (a different size, format or origin) raise `Conflict` rather than overwriting the record
  that every disclosure and manifest row already points at.

* **An unrecognised round normalizes to `None`, not to a catch-all enum member.** `"Round Robin"`
  and `"Elims"` keep their raw text and no normalized value, so an aggregate in E32 counts what it
  actually recognised instead of silently bucketing the rest.

* **`SnapshotDate` compares against today in UTC.** A snapshot date is the day an archive was
  published; one in the future is a typo or a wrong clock, and letting it in would make
  `latest_snapshot` point at a phantom archive that every later import then refuses to precede.

* **`CaselistRepository` is not in `FakePorts`.** `FakePorts` is the E02 set of ten ports every
  service takes; this is an eleventh port that only E30/E31/E32 code reaches for, so it is built by
  its own `build_fake_caselist_repository()` — which carries the Protocol annotation that makes
  pyright check the fake's conformance inside the package.

## Operator follow-ups

None. Everything in this task runs in well under two minutes (`uv run pytest` takes 18 seconds).

## Follow-up work

* **`uv run lint-imports` (belongs to `v1-e02-t06-import-boundary-guard`).** Until that task lands,
  every later task carrying a `lint-imports` criterion — `v1-e30-t03`, `t05`, `v1-e08-t01`, `t05`,
  `t06`, `v1-e29-t04`, `t05` — will hit the same wall. Worth scheduling E02-t06 before the next one
  of those starts.

* **A repository contract suite for `CaselistRepository` (belongs to `v1-e30-t03-archive-importer`,
  which builds the SQLite adapter).** `v1-e02-t04-repo-contract-tests` establishes the pattern of
  running one suite against both the fake and the real adapter; the expectations asserted here
  against the fake — snapshot-range widening in both directions, `Conflict` on contradictory bytes,
  listing order, cursor rejection — are the ones that suite should carry, rather than being
  re-written against SQLite.

* **The `run()` coroutine helper is now duplicated** in `tests/application/test_fakes.py` and
  `tests/application/test_caselist_fake_repository.py`. Both say in their docstrings that it goes
  away when an async test plugin arrives; that is still the right fix, and it belongs with whichever
  task first needs genuine concurrency.

* **JSON Schemas for the caselist entities** if E32 or the V2 debate tub ends up serving them to the
  web client — a decision for the PM, not a gap in this task.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
