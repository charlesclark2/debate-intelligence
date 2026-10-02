# Session report: v1-e03-t06-verify-command

| | |
|---|---|
| Task | `v1-e03-t06-verify-command` — `debate-research verify` command |
| Spec | [`plan_specs/v1/e03-evidence-integrity/t06-verify-command.yaml`](../../plan_specs/v1/e03-evidence-integrity/t06-verify-command.yaml) |
| Epic / release | `v1-e03-evidence-integrity` / `v1.0` |
| Branch | `task/v1-e03-t06-verify-command` |
| Session status | COMPLETE |

## Summary

`debate-research verify <manifest.json>` checks every card in a card manifest against the snapshots
in this environment's data directory, and exits 0, 1, 2 or 3 as the PM decided. The work is in
`debate_core`: `CardManifest` (`evidence/manifest.py`, one model, each card the domain `Card`) and
the `VerifyManifest` use case (`application/verify_manifest.py`), which calls `EvidenceVerifier.verify`
per card. The command only reads the file, calls the use case and renders a Rich table or one
`--json` envelope; its handler is 16 statements. Every Goal criterion and node criterion passes, and
the Goal is `Succeeded`.

What the PM should look at first:

- **A new runtime dependency: `jsonschema`, on debate-core** (Decisions §1, Deviation 1). Your
  exit-2 rule needs a real JSON Schema check, and the repository had no validator. The operator
  approved it in this session. It was locked offline from the uv cache.
- **New reason code `CARD_INVALID`** for decision 3, rather than reusing `CARD_INCOMPLETE`
  (Decisions §2).
- **The spec's end-to-end command criterion cannot pass as literally written** (Deviation 2). Run
  bare, it reads the operator's dev data directory, which holds none of the fixture snapshots. I ran
  it against the fixture data directory, using environment variables.
- **The spec has no smoke-check node**, which working agreement 5 asks for. I did not add one
  outside the authorised paths (Deviation 3).
- **Mutation: 19 of 19 mutants caught** on the committed code, covering all four families you named.
  One mutant survived its first run, and the test it showed was missing is now added.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `manifest-schema`: Card manifest model and schema | Done | `evidence/manifest.py`: `CardManifest`, `render_card_manifest_schema`. Committed `schemas/card_manifest.v1.json`, whose items are `{"$ref": "card.schema.json", "required": ["card_id"]}`. Commit `6314e21`. |
| `verify-use-case`: VerifyManifest use case | Done | `application/verify_manifest.py`: `VerifyManifest`, `ManifestVerificationReport`, `CardVerdict`, `InvalidManifest`, `VerificationCouldNotRun`, `render_verify_result_schema`. `ReasonCode.CARD_INVALID`. Committed `schemas/verify_result.v1.json`. Fixture scenario and manifests in `tests/fixtures/verify/`. Commit `210390a`. |
| `cli-command`: verify command and rendering | Done | `commands/verify.py`, registered in `commands/__init__.py`, wired as `ServiceContainer.verify_manifest`. Help and the CLI README document the exit codes. Commit `b8b8aa6`. |
| `e2e-fixture`: End-to-end fixture run | Done | `tests/integration/test_verify_cli.py` runs the installed console script as a process against a data directory written by the real local adapters. Commit `53d6d12`. |

## Acceptance criteria

All commands were run from the task worktree. Unless noted, they used the repository's default
pytest options (xdist, coverage, `--disable-socket`).

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a manifest JSON Schema (manifest_version 1) is published under `packages/debate_core/schemas/`, and invalid manifests exit 2 with the failing JSON path | PASS | `card_manifest.v1.json` is committed. `test_the_committed_manifest_schema_matches_the_model` holds it to the model, and `export_schemas.py --check` covers it. CLI: `test_a_manifest_that_fails_its_schema_exits_two_with_the_failing_json_path` has three cases: `$.manifest_version`, `$.cards[1]` (missing `card_id`), and `$.cards[2].spans[0].end_offset`. Each exits 2 with `error.details.json_path` and the path in the person-facing message. Use case: 11 schema cases and 6 strict-JSON cases, each with a hand-written path and problem. End to end: `test_a_manifest_that_fails_its_schema_exits_two_with_the_path` → `$.cards[2].omitted_ranges[0]`. |
| ac2: on a fixture manifest with two verified cards and one tampered card, the command prints all three rows with reasons and exits 1 | PASS | `tests/fixtures/verify/tampered.json` is `all_verified.json` with "had" changed to "has" in the third card. `test_two_verified_and_one_tampered_card_print_three_rows_with_reasons_and_exit_one` exists in the CLI tests (`CliRunner`) and in `tests/integration` (installed command). Each finds exactly three table rows, two VERIFIED and one UNVERIFIED, with `TEXT_MISMATCH at offset 22`, and exit 1. The offset was counted by hand ("Nobody in the basin " is 20 characters). |
| ac3: `--json` output validates against a result schema and has per-card status and reason codes | PASS | `verify_result.v1.json` describes the whole stdout document for exits 0, 1, 2 and 3. Every `--json` run in the CLI and integration tests is validated against the committed file, read the way a consumer reads it (`tests/fixtures/verify/published_schemas.py`). `test_json_reports_every_card_of_the_mixed_manifest_with_its_status_and_reason_codes` asserts all five `(card_id, status, reason_codes)` rows. `test_a_report_fits_the_result_schema_in_either_envelope` shows the schema refuses a card with no status (`("$", "oneOf")`). |
| ac4: exit codes are documented in `debate-research verify --help` and the CLI README | PASS | `test_the_help_documents_every_exit_code` checks the four lines in `--help`. `test_the_cli_readme_documents_every_exit_code` checks the table in the README's new `debate-research verify` section. `test_the_result_schema_uses_the_clis_exit_codes` ties the schema's numbers to `ExitCode`. |
| Node `manifest-schema`: artifact `packages/debate_core/schemas/card_manifest.v1.json` exists | PASS | `test -f packages/debate_core/schemas/card_manifest.v1.json` → exists. |
| Node `verify-use-case`: `uv run pytest packages/debate_core/tests/application/test_verify_manifest.py` | PASS | `34 passed in 7.31s`. `verify_manifest.py` is at 100% line and branch coverage. |
| Node `cli-command`: `uv run pytest packages/debate_cli/tests/test_verify_command.py` | PASS | `18 passed in 5.13s`. |
| Node `e2e-fixture`: `uv run debate-research --json verify tests/fixtures/verify/all_verified.json` exits 0 | PASS, as run in Deviation 2 | `DEBATE_ENV=test DEBATE_STORAGE__DATA_DIR=<scratchpad>/verify-data uv run debate-research --json verify tests/fixtures/verify/all_verified.json` → exit 0, `status ok`, 3 of 3 VERIFIED, in 0.32 s. The data directory was written by `build_fixture_data_dir` just before. |
| Node `e2e-fixture`: `uv run pytest tests/integration/test_verify_cli.py` | PASS | `6 passed in 3.92s`. |
| Forbidden: verification logic inside debate_cli | PASS | The command reads the file, calls `VerifyManifest.verify`, renders, and picks the exit code. `uv run scripts/check_thin_handlers.py` → `OK: 19 CLI command and API route handlers within 25 statements` (`verify`: 16). `lint-imports` → `Contracts: 11 kept, 0 broken.` |
| Forbidden: a card reported VERIFIED when its snapshot is missing locally | PASS | `mixed.json`'s fifth card was cut from a snapshot taken in a separate world, and is `SNAPSHOT_MISSING` at every level. `test_a_data_directory_without_the_snapshots_verifies_nothing` runs the installed command against an empty data directory: all three cards are `SNAPSHOT_MISSING`, exit 1. Mutants 10-12 are caught. Mutant 10, which reports a missing snapshot as VERIFIED, is also caught by t04's VERIFIED scan. |
| Forbidden: network access during verification | PASS | Every in-process test runs under pytest-socket's `--disable-socket`. The use case catches only `DomainError`, so a blocked connection would surface as an error. `jsonschema` is given only in-memory schemas through a `referencing.Registry` with no retrieve function, so a `$ref` is never fetched. The container builds `verify_manifest` from the SQLite file and the filesystem blob store only. |

Wider checks:

- `uv run pytest -q --no-cov` (whole repository, default markers) → `3852 passed, 1 skipped in
  40.24s`. The skip is the existing `tests/evals/parser/test_parser_eval.py:279`.
- `uv run ruff check .` → clean. `uv run ruff format --check .` → `481 files already formatted`.
- `uv run pyright packages tests/fixtures/verify tests/integration/test_verify_cli.py` → `0 errors`.
- `uv run lint-imports` → `Contracts: 11 kept, 0 broken.`
- `uv run scripts/export_schemas.py --check` → `OK: 9 schemas in packages/debate_core/schemas are up to date`.
- `uv run python scripts/check_links.py` → `OK: 1205 relative links and anchors in 163 Markdown files`.
- `uv run scripts/validate_specs.py` (after setting the phase) → `OK: 302 files, 38 epics, 244 tasks, 20 releases`;
  `--require-succeeded v1-e03-t06-verify-command` → `Succeeded`.

**Checks shown failing.** Three changes, each reverted afterwards: `minItems` changed in the
committed manifest schema, an outcome title changed in the result schema, and one character changed
in `mixed.json`. `export_schemas.py --check` exited 1, naming both schema files. Four tests failed:
the manifest-schema drift test, the empty-manifest test, the committed-manifests drift test and the
result-schema drift test. After restoring, `git status` was clean and `--check` passed.

## Mutation testing

The runner is a scratchpad script and is not committed. For each mutant it:

- applies one exact-string replacement, and refuses if the pattern does not occur exactly once;
- runs the five affected test sets with `-n0 --no-cov` (69 tests):
  - `test_verify_manifest.py`
  - `test_manifest.py`
  - `test_verify_command.py`
  - `tests/integration/test_verify_cli.py`
  - t04's `test_verified_is_set_only_by_the_evidence_verifier`
- restores the original bytes in a `finally`.

**Every run set `HYPOTHESIS_STORAGE_DIRECTORY` to a new, empty directory** (working agreement 8).
None of these tests uses Hypothesis, so there are no property statistics to report. A pytest exit
other than 0 or 1 is reported as ERROR, never as a catch. `git status` was clean after every batch.

**Final run, against the committed code: 19 of 19 caught, each in about 3 s.**

| # | Family | Mutant | Failed / 69 | One test that caught it |
|---|---|---|---|---|
| 0 | exit 0 | `all_verified` is "any card verified" | 8 | `test_one_tampered_card_is_a_text_mismatch_and_the_other_two_still_verify` |
| 1 | exit 0 | the command takes the success path whatever the report says | 7 | `test_two_verified_and_one_tampered_card_print_three_rows_with_reasons_and_exit_one` |
| 2 | exit 1 | UNVERIFIED reported with the usage-error code | 7 | same |
| 3 | exit 2 | an invalid manifest reported with the UNVERIFIED code | 5 | `test_a_manifest_that_fails_its_schema_exits_two_with_the_failing_json_path` |
| 4 | exit 3 | could-not-run reported with the UNVERIFIED code | 2 | `test_a_store_that_cannot_be_read_exits_three_and_gives_no_verdict` |
| 5 | exit 3 | the use case lets the `StoreError` through, so the root handler gives exit 1 | 5 | `test_a_store_that_cannot_be_reached_stops_the_run_instead_of_giving_a_verdict` |
| 6 | exit 3 | a store failure becomes an UNVERIFIED verdict | 5 | same |
| 7 | isolation | an invalid card refuses the whole manifest (exit 2) | 7 | `test_the_mixed_manifest_gives_every_card_its_own_verdict` |
| 8 | isolation | the whole manifest is validated as a `CardManifest` first | 8 | same |
| 9 | isolation | verification stops at the first invalid card | 5 | same, and `test_an_invalid_card_does_not_stop_the_cards_after_it_being_verified` |
| 10 | missing snapshot | a card whose snapshot is missing is reported VERIFIED | 7 | `test_a_card_whose_snapshot_is_not_here_is_unverified_never_skipped`, and t04's VERIFIED scan |
| 11 | missing snapshot | the use case skips a card whose snapshot is missing | 6 | same, and `test_a_data_directory_without_the_snapshots_verifies_nothing` |
| 12 | missing snapshot | the table leaves out rows whose snapshot is missing | 1 | `test_a_person_sees_a_row_for_every_card_of_the_mixed_manifest` |
| 13 | schema path | every schema failure reported at `$` | 14 | `test_a_manifest_that_fails_the_schema_names_the_failing_path_and_verifies_nothing` |
| 14 | schema path | the CLI drops the path from the JSON details | 4 | `test_a_manifest_that_fails_its_schema_exits_two_with_the_failing_json_path` |
| 15 | schema path | the first violation found instead of the most relevant | 1 | `...names_the_failing_path...[$.cards[0].evidence_start_offset-must be at least 0]` |
| 16 | schema path | a card's index rendered as `.3` instead of `[3]` in its CARD_INVALID path | 3 | `test_the_mixed_manifest_gives_every_card_its_own_verdict` |
| 17 | never quote | a CARD_INVALID detail carries pydantic's `input` | 4 | `test_a_card_invalid_detail_never_quotes_the_cards_text`, `test_the_output_never_contains_evidence_text` |
| 18 | never quote | a schema violation described with the failing value | 11 | `test_a_manifest_that_fails_the_schema_names_the_failing_path_and_verifies_nothing` |

Notes:

- **Mutant 12 survived its first run.** Every table test used the tampered manifest, which has no
  missing snapshot, so a table that silently dropped SNAPSHOT_MISSING rows passed. I added
  `test_a_person_sees_a_row_for_every_card_of_the_mixed_manifest` (commit `b8c0093`). The final run
  above is after it.
- **Mutant 5 errored at collection on its first attempt.** Removing the `except` clause left a bare
  `try`. That proves nothing, so I did not count it. I redid it by replacing the whole `try` block
  with the bare call, and the redone mutant is caught.
- Mutants 4 and 12 are caught by few tests, by design. Only the CLI picks the exit code, and only
  the table renders rows; each has its own test.
- No check was removed. One defensive check had no test at first:
  `render_card_manifest_schema`'s refusal of a dangling `#/$defs/` reference. It now has one,
  `test_the_rendering_refuses_a_schema_that_still_points_at_an_inlined_definition`.

## Files changed

- `packages/debate_core/src/debate_core/evidence/manifest.py` (new): `CardManifest`,
  `MANIFEST_VERSION`, `render_card_manifest_schema`.
- `packages/debate_core/src/debate_core/application/verify_manifest.py` (new): the use case, the
  report types, `read_manifest`, the two non-report outcomes, and the result-schema rendering.
- `packages/debate_core/src/debate_core/evidence/verification_types.py`: `ReasonCode.CARD_INVALID`.
- `packages/debate_core/schemas/card_manifest.v1.json`, `verify_result.v1.json` (new, generated).
- `packages/debate_core/pyproject.toml`, `uv.lock`: `jsonschema>=4.23`. It brings `referencing`,
  `jsonschema-specifications`, `rpds-py` and `attrs`.
- `scripts/export_schemas.py`: also writes the two new schemas. Its `--check` covers them.
- `packages/debate_cli/src/debate_cli/commands/verify.py` (new): the command.
- `packages/debate_cli/src/debate_cli/commands/__init__.py`: registers `verify`.
- `packages/debate_cli/src/debate_cli/container.py`: `verify_manifest`, a `_PortIdGenerator`, and
  `"verify_manifest"` in `SERVICE_NAMES`.
- `packages/debate_cli/tests/test_app.py`: `doctor`'s service list gains `verify_manifest`.
- `packages/debate_cli/README.md`: new `debate-research verify` section with the exit-code table.
- `docs/evidence/snapshot-text-format.md`: a paragraph on `CARD_INVALID` under the reason-code
  table.
- Tests, new:
  - `packages/debate_core/tests/evidence/test_manifest.py` (10 tests);
  - `packages/debate_core/tests/application/test_verify_manifest.py` (34);
  - `packages/debate_cli/tests/test_verify_command.py` (18);
  - `tests/integration/test_verify_cli.py` (6).
- Fixtures, new, in `tests/fixtures/verify/`:
  - `manifest_world.py`: the scenario, `build_fixture_data_dir`, and the manifest writer;
  - `published_schemas.py`: validation against the committed files;
  - `all_verified.json`, `tampered.json`, `mixed.json`.
- `plan_specs/v1/e03-evidence-integrity/t06-verify-command.yaml`: `constraints.packages` widened (on
  the PM's instruction, and for Deviation 1); phase `Succeeded`.

## Deviations from the spec

1. **Edits outside the package list, beyond the PM's widening.** All are now listed in
   `constraints.packages`, with a comment saying why.
   - `packages/debate_core/pyproject.toml` and `uv.lock`: the `jsonschema` dependency, approved by
     the operator in this session (Decisions §1).
   - `scripts/export_schemas.py`: the one exporter of committed schemas.
   - `debate_cli/container.py` and `debate_cli/commands/__init__.py`: the spec's own `cli-command`
     node says "wiring the use case from the composition root", and the command has to be
     registered.
   - `debate_cli/tests/test_app.py`: `doctor`'s service list. Its own comment asks each new service
     to be added there.
   - `docs/evidence/snapshot-text-format.md`: one paragraph, so a reader who meets `CARD_INVALID`
     finds it next to the verifier's codes.
2. **The `e2e-fixture` command criterion was run with environment variables.** As written,
   `uv run debate-research --json verify tests/fixtures/verify/all_verified.json` resolves to the
   `dev` environment and `~/.debate-research/dev`. That directory holds none of the fixture
   snapshots, so it would exit 1 with three `SNAPSHOT_MISSING` cards, which is correct behaviour.
   Opening that data directory would also create or migrate the operator's dev database. So I did
   not run it bare. I ran it with `DEBATE_ENV=test` and `DEBATE_STORAGE__DATA_DIR` pointing at a
   data directory written by `build_fixture_data_dir`, and it exits 0. Suggested rewording: point
   the criterion at `uv run pytest tests/integration/test_verify_cli.py -k verified_only`, which
   builds the data directory itself.
3. **No smoke check in `tests/smoke/`.** Working agreement 5 and `plan_specs/README.md` say a task
   that adds a CLI command adds a smoke-check node for `validate-dev`. This spec has none, and
   `tests/smoke/` is not on the authorised list. `tests/integration/test_verify_cli.py` already
   drives the installed command with no network and is in the default suite. A smoke check could
   reuse `build_fixture_data_dir` and two of its cases. PM to decide.
4. **The fixture data directory is built by code, not committed.** The spec says "Fixture data dir +
   manifest under tests/fixtures/verify/". Committing a SQLite file would be fragile:
   `SqliteDatabase.open` migrates it in place, and a later migration would change a committed
   binary. So the builder (`manifest_world.py`) and the three manifests are committed. Ids come from
   sequential generators, and timestamps and span ids are pinned, so a rebuild is byte-identical.
   `test_the_committed_manifests_are_what_the_scenario_builds` fails otherwise.

## Decisions and assumptions

1. **`jsonschema` validates the manifest, at runtime, in debate-core.** Decision 2 makes exit 2 "a
   manifest that fails the JSON Schema", so the check has to be the standard's, not an
   approximation. I offered the operator three options: `jsonschema`, a hand-written validator for
   the 20 keywords the schemas use, or Pydantic alone. They chose `jsonschema`.
   - The validator is given the schemas rendered in memory, the same functions the committed files
     are drift-tested against.
   - `card.schema.json` is resolved from a `referencing.Registry`, never fetched.
   - The use case does not read `packages/debate_core/schemas/` at runtime, because an installed
     wheel does not ship that directory.
2. **`CARD_INVALID` is a new reason code, not `CARD_INCOMPLETE`.** `CARD_INCOMPLETE` means
   something re-verification needs is missing. A card that breaks the length invariant has every
   field present, so that code would send a reader looking for an absent field: the same argument
   t04 made when it added `CARD_INCOMPLETE`.
   - The use case reports `CARD_INVALID`. The verifier never sees the card, and `VERIFIER_VERSION`
     is unchanged.
   - The detail gives the JSON path and pydantic's message, never the input. I read every validator a
     `Card` runs (the card, its spans and omissions, `Citation`, the base types). None quotes a value.
     The one domain validator that echoes its input, the URL check, is used only by `Article` and
     `SourceSnapshot`.
   - If several rules fail, there is one reason per pydantic error. In practice there is one,
     because the model's after-validators stop at the first.
3. **`InvalidManifest` and `VerificationCouldNotRun` are deliberately not `DomainError`s.** The root
   handler reports an unhandled `DomainError` as exit 1, which `verify` reserves for an UNVERIFIED
   card. If a future change forgot to handle one of these, the run would end as a bug (exit 70),
   never as a verdict. A test asserts it.
4. **Exit 3 covers any `DomainError` the verifier lets through, not only `StoreError`.** By t04's
   design, everything the verifier does not turn into a reason is "not a verdict about the card",
   and a corrupt SQLite record (`CorruptRecordError`) is just as much "could not run". Anything that
   is not a `DomainError` is a bug and propagates to exit 70. Both have tests.
   - The number is the CLI-wide `RETRIEVAL_FAILURE` (3), "may succeed later". The `--json` error
     code is `VERIFICATION_COULD_NOT_RUN`, with the card, its position and the cause's class name.
   - A cause that carries a hint (`aws sso login --profile …`) passes it through.
5. **The `--json` envelope follows the existing pattern** (`store sync`, `caselist status`). The
   report goes under `data` on exit 0 and under `error.details` on exit 1, so `status`, `error.code`
   and the exit code agree.
   - A person gets the table, then a short panel with counts. The full report would otherwise be
     printed a second time inside the panel.
   - `--verbose` adds each reason's detail on stderr.
6. **The result schema describes the whole stdout document.** It covers the envelope, with a `oneOf`
   for exits 0, 1, 2 (manifest), 2 (Typer usage error) and 3. It lives in `debate_core` as you
   asked, so it writes the exit codes as numbers, and a CLI test holds them to `ExitCode`. Exit 70
   uses the CLI-wide envelope and is not described.
7. **Schema-violation messages are written from the schema's side.** jsonschema's own messages quote
   the failing value: `'SECRET TEXT' is not of type 'object'`, measured. A manifest value could be
   evidence text. So the problem is built from the keyword and the schema's value. Property names
   are the one thing taken from the document (a missing or unexpected key), shortened to 60
   characters.
   - The path is jsonschema's `best_match`. The count of violations is reported alongside it.
   - Mutant 15 shows that `best_match` is load-bearing: for an `anyOf`, it reports the alternative
     that came closest ("must be at least 0") rather than the `anyOf` itself.
8. **Strict JSON.** A duplicated key is refused (exit 2), because a person viewing the file could
   be shown a different `evidence_text` from the one verified. `NaN` and `Infinity` are refused too.
9. **`generated_at` must be a timezone-aware date-time.** JSON Schema only annotates
   `format: date-time`, so the reader checks it with the model's own type, at `$.generated_at`.
10. **A manifest card must have a `card_id`, and a manifest must list at least one card.**
    - The domain mints a fresh id for a card without one: right when creating a card, wrong when
      reporting on one. A serialized card always has its id, so a writer is never refused.
    - An empty manifest would let a script that gates on `verify`'s exit code pass having checked
      nothing. Both rules are in the committed schema, so they are exit-2 failures.
11. **Each card loads with `Card.model_validate_json`**, the way a stored card is read back, so a card
    is judged by the same rules here as in a repository.
12. **The fixture builder reuses `verification_world.py` without changing it.** VerificationWorld's
    stores are typed as the in-memory fakes, and t04's tests depend on that
    (`world.blobs.corrupt(...)`), so it cannot be pointed at a data directory without breaking them.
    `manifest_world.py` reuses its constants and `run`, and makes cards the same production way:
    `SnapshotService.create`, `EvidenceExtractor`, `place_evidence_on_card`. It does no offset
    arithmetic. t07's whole-tree scan still passes.
13. **The fixtures.** All text is invented.
    - Two verified cards, one with an omission made by `place_evidence_on_card`.
    - One tampered card, same length: "had" to "has", `TEXT_MISMATCH` at 22.
    - One card ten characters longer than its envelope, which passes the schema and fails the length
      invariant (`CARD_INVALID`).
    - One card cut from a snapshot taken in a separate world (`SNAPSHOT_MISSING`).
    - `all_verified.json` exits 0. The store-unavailable case exits 3, through the container's
      override seam with the real command function.
14. **The manifest argument is `typer.FileBinaryRead`.** A missing or unreadable file is Typer's own
    usage error (exit 2), and `-` reads stdin.
15. **The container imports `SqliteArticleRepository` from `debate_core.integrations.local`**, which
    re-exports it, rather than from `local.sqlite_repos`. The post-install check reads the
    container's import statements, and a new module there would have changed its list for no
    reason.
16. **No snapshot cache.** Each card loads its snapshot through `EvidenceVerifier.verify`, as t04 does.
    That is fine for web articles (0.3 ms a load), but see Follow-up work for large PDFs.

## Operator follow-ups

None. Every command in this task finished in under 45 seconds and was run in the session. The
longest was the whole suite (40 s).

What remains is the usual step after review, run from the task worktree:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e03-t06-verify-command
scripts/task pr v1-e03-t06-verify-command
```

Once this merges, the next `uv run` in any checkout syncs the new `jsonschema` dependency.

## Follow-up work

- **`FsSnapshotStore.get` does not translate an operating-system refusal into `StoreAccessDenied`.**
  `StoreError`'s docstring says a filesystem store does that, but `get` catches only
  `FileNotFoundError`. So an unreadable blob directory reaches `verify` as a raw `PermissionError`,
  and the run exits 70 ("a bug") instead of 3. Owner: the local adapters (`v1-e02-t03` lineage).
  Once fixed, `verify` reports exit 3 with no change here.
- **CLI-wide, `exit_code_for` maps every `StoreError` to 1.** Exit 1's documented meaning is "running
  it again gives the same answer", which an unreachable store or an expired SSO session is not.
  `verify` sets 3 itself. `store sync` and the caselist commands still exit 1 for those. Owner: PM
  (`debate_cli.exit_codes`).
- **Smoke check for `verify`** in `tests/smoke/` (Deviation 3).
- **`v1-e06-t05-json-manifest-export`** (the PM is already amending it). As written, its spec:
  - says `schema_version "1.0"`, but the field is `manifest_version: 1`;
  - writes `schemas/card_manifest.v1.json` at the repository root, but the file is at
    `packages/debate_core/schemas/`;
  - expects reason codes `SPAN_MISMATCH` and `EVIDENCE_HASH_MISMATCH`, which do not exist. The
    codes are `TEXT_MISMATCH`, `SPAN_OUT_OF_RANGE` and `HASH_MISMATCH`.
  - Also, a writer must never produce an empty manifest (Decisions §10), and the drift test pattern
    in `test_manifest.py` is the one to extend.
- **Snapshot loads per card.** A manifest of many cards from one 50 MB PDF loads it once per card,
  at about 166 ms each (t02's measurement). A cache keyed by snapshot id, filled only through
  `SnapshotService.load`, would fix it. It needs an `EvidenceVerifier` API that accepts a loaded
  snapshot, so it belongs to whoever next touches the verifier.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
