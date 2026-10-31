# Session report: v1-e41-t01-newer-build-messages

| | |
|---|---|
| Task | `v1-e41-t01-newer-build-messages` — When a newer build wrote the database or added a setting, the error says so |
| Spec | [`plan_specs/v1/e41-delivery-tooling-upkeep/t01-newer-build-messages.yaml`](../../plan_specs/v1/e41-delivery-tooling-upkeep/t01-newer-build-messages.yaml) |
| Epic / release | `v1-e41-delivery-tooling-upkeep` / `v1.8` |
| Branch | `task/v1-e41-t01-newer-build-messages` |
| Session status | COMPLETE |

## Summary

Three refusals now say which build to run when an installed build and a checkout drift apart.

1. **A database a newer build migrated** is refused as `DATABASE_FROM_NEWER_BUILD`, exit `1`, with a hint naming both schema versions and the fix: sync the checkout, or install the newer build. Before this it reached the CLI as an unmodelled `MigrationError`: exit `70`, a "this is a bug" hint, and its own sentence withheld.
2. **An unknown setting** is still refused. When its name matches one of two reserved patterns, `providers.*_api_key` and `providers.*_token`, the hint says a newer build may define it and how to get past it. For a `.env`, that means running from another folder or installing the newer build.
3. **`files build`** tells a store a newer parser wrote to install the newer build, not to re-parse, and keeps the re-parse hint for an older parser. A style profile that differs on its own gets a hint naming both profiles and saying the choice depends on which build is newer, without asserting either.

Worth looking at first:

* **A value no longer leaks through the exception chain.** When an unknown name is among the problems, the settings refusal now raises `from None`, because Pydantic's chained report quoted the raw value.
* **Mutant 5 first survived because of a weak test.** I fixed the test, and the mutant is now caught.
* **An existing gap I did not close:** a *top-level* unknown name in `.env` is silently dropped rather than refused (Follow-up 1).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `messages` (Newer-build messages) | Done | Red run first, then the implementation. 10 mutants, all caught (one only after a test fix, described below). Node criterion: 150 passed. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: a database at a newer schema version is refused with its own code and a hint naming both versions, by test shown failing first | **PASS** | **Red** (code skeleton: the class name exists, nothing raises it): `test_sqlite_db.py::test_a_database_from_a_newer_build_is_refused_naming_both_schema_versions_and_the_fix` failed with the old `MigrationError: <path>/debate.sqlite3 holds schema version 9999, bu…` (not the new class, and the message quoted the path). The CLI tests failed with `assert <ExitCode.INTERNAL_ERROR: 70> == <ExitCode.DOMAIN_FAILURE: 1>`. `test_recorded_failure_codes.py` failed with `assert 'INTERNAL_ERROR' == 'DATABASE_FROM_NEWER_BUILD'`. **Green:** the core test pins the message and hint whole, `database_version`/`build_version`, and that the path is in neither. `test_migration_from_a_newer_build.py` pins the whole `--json` error (code, message, `exit_code: 1`, details, hint) through `caselist cards`, and checks that `--verbose` prints no traceback, no "bug" and no path. `test_recorded_failure_codes.py` covers the code under `reported_error_code` and `error_code_for`, exit `1` from `exit_code_for`, and `exit_code_for_failure_codes`, alone and beside `STORE_UNAVAILABLE`. |
| **ac2**: an unknown setting is still refused, and one in a reserved pattern gets the newer-build hint, by tests shown failing first | **PASS** | **Red:** the 8 settings tests that read the hint failed with `AttributeError: 'ConfigurationError' object has no attribute 'hint'`. The CLI test failed on `{'hint': None} != {'hint': 'A newer build may define providers.core_api_key: …'}`. **Green:** `test_settings_newer_build_names.py` (10 tests) pins whole hints for a reserved name from `.env`, from the process environment (names the variable to unset) and from a profile file (names the file). It also pins several reserved names plus a typo in one refusal (only the reserved ones are hinted), and three near-misses that get no hint (`http.core_api_key`, `providers.openalex_apikey`, `providers.core_api_key_file`). A reserved spelling this build defines (`openalex_api_key`) loads normally, and the pattern tuple is pinned. Every refusal test asserts its value is absent from the message, the hint, `vars(error)` and the whole `traceback.format_exception` chain. `test_config_command.py` pins the whole `--json` error for a `.env` in the working directory, and shows the value reaches neither stream in rich, `--json`, `--verbose` and `--json --verbose`, while the name does. |
| **ac3**: a store read by a newer parser version gets a hint to install the newer build, an older one keeps the re-parse hint, and a store under another style profile gets a hint naming both without asserting which is newer; tests shown failing first | **PASS** | **Red:** the newer-parser, newer-dominates, profile-only and mixed-caselists tests failed, each showing the unconditional `'Re-parse wit... build again.'` against the expected hint. `test_a_store_an_older_parser_wrote_keeps_the_reparse_hint` passed at red, as it should: it pins the hint that stays. **Green:** `test_file_build_service.py`, 6 new tests, each hint pinned whole: older parser → re-parse; newer parser → install the newer build, and why a re-parse would be refused again; a newer parser decides the hint even when the fingerprint and profile also differ; profile only → both profiles, "which way to go depends on which build is newer", both ways given; profile plus fingerprint → re-parse; two caselists needing different fixes → each its own, in one hint. |
| Node `messages`: CLI tests pass (`uv run pytest packages/debate_cli/tests -k "config or migration or doctor"`) | **PASS** | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_cli/tests -k "config or migration or doctor" -q` → `150 passed in 17.70s`. This is the spec's command through the worktree venv, as agreement 10 asks (the bound goes on `.venv/bin/python`, which skips uv's sync). The new CLI test files are named so that `-k` reaches them. |

### Red run

`.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n 0 -p no:randomly -q --tb=line` over the six touched test files, against the skeleton: `17 failed, 99 passed in 18.33s`, each failing at its own assertion (reasons above). The first attempt, before the skeleton, errored at collection (`ImportError` on the new names), and I do not count it as a red run. One test of mine was wrong at red and I fixed it before recording: the older-parser test needed the fresh `SpyStore` the neighbouring tests use, because `world.add` had already published this build's version.

### Mutation runs

Each mutant was applied alone, then the test files covering its module were run (`-n 0 -p no:randomly`) with `HYPOTHESIS_STORAGE_DIRECTORY` set to a new empty directory. The file was restored with `git checkout HEAD --`. No Hypothesis property is involved here; the variable is set per agreement 8 regardless. All ten results below come from one final run, after the test fix described under mutant 5. I read each failing line: every catch is an assertion, and none is a crash.

| Mutant | Caught by | Reason |
|---|---|---|
| 1. An unknown, **unreserved** setting accepted: the loader drops unknown names outside the patterns and loads | 4 settings tests | `Failed: DID NOT RAISE ConfigurationError` |
| 2. The newer-database hint names one version only (`this build's {build_version}` → `this build's`) | core + CLI database tests | hint and envelope not equal to the pinned text |
| 3. `files build` says re-parse for a newer store (the newer branch disabled) | 3 file build tests | `'Re-parse wit... build again.' == 'hspolicy26 w...refuse again.'` |
| 4. The profile-only hint asserts a direction (profile-only treated as re-parse, that is, "this build is newer") | the profile-only test | `'Re-parse wit... build again.' == "hspolicy26's...ith that one."` |
| 5. The unknown-setting refusal chains Pydantic's report again (`from None` → `from error`) | 7 settings tests | `assert 'nwr-K3y-7Qx9' not in 'Traceback (…'` |
| 6. Reserved patterns matched as a prefix (`pattern + '*'`) | the `core_api_key_file` near-miss | a hint where none is due |
| 7. `DatabaseFromNewerBuild` not a `DomainError` | 4 database tests | exit `70`, `INTERNAL_ERROR` |
| 8. The newer database exits `3` (a retry) | 3 CLI tests | `RETRIEVAL_FAILURE: 3 == DOMAIN_FAILURE: 1` |
| 9. The newer-parser comparison flipped (`>` → `<`) | 7 file build tests | an older store told to install the newer build |
| 10. The `.env` hint drops "run the command from another folder" | 2 core + 1 CLI settings test | hint not equal to the pinned text |

**Mutant 5 first survived (39 passed).** The settings tests used a 50-character sentinel, and Pydantic's report shortens a long input to its two ends (`input_value='value-of-a-ne...st-never-be-printed'`). So the sentinel never appeared whole, even when the report was chained. I confirmed the leak by hand: with the mutant, a short value is in `traceback.format_exception(error)`. The sentinel is now `nwr-K3y-7Qx9`, with a comment saying why it is short (commit `e96d969`), and the re-run catches mutant 5 in 7 tests. The CLI streams check keeps its long sentinel. It reads stdout and stderr, which never carry the chain, and the core test now guards the chain.

### Before the report (agreement 10)

| Check | Result |
|---|---|
| `uv run scripts/affected_tests.py` (listing only) | `434 of 592 test files (73.3%) chosen in 22.3 s from 12 changed files`. The root conftest imports `ports.model_router`, which imports `application.settings`. At about six minutes for the whole selection, 73% runs well past two minutes, so per agreement 10 (PM ruling 2026-10-19) I did **not** run it and did not hand it over: the pull request's `ci` check runs it. |
| Test directories of what changed, plus the always-run list: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n auto -m "not slow and not live" -q tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py packages/debate_core/tests/application/test_*.py packages/debate_core/tests/integrations/local packages/debate_cli/tests/test_migration_from_a_newer_build.py packages/debate_cli/tests/test_recorded_failure_codes.py packages/debate_cli/tests/test_config_command.py packages/debate_cli/tests/commands/test_files.py` | `3332 passed in 53.99s` |
| `uv run --frozen ruff check .` / `ruff format --check .` | `All checks passed!` / `1656 files already formatted` |
| `uv run --frozen pyright packages/debate_core packages/debate_cli` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 19 kept, 0 broken.` |
| `uv run --frozen python scripts/check_thin_handlers.py` | `OK: 68 CLI command and API route handlers within 25 statements` |
| `uv run scripts/validate_specs.py` | `OK: 527 files, 41 epics, 464 tasks, 22 releases`; `--require-succeeded v1-e41-t01-newer-build-messages` → `Succeeded` |
| `uv run --frozen python scripts/check_command_blocks.py --base origin/dev`, `docs_index.py --check-descriptions`, `check_links.py` | `OK: no # comments …` (this report included), `All 60 indexed documents under docs/ have a description`, `OK: 3075 relative links and anchors in 477 Markdown files` |

### What an operator sees

`debate-research caselist cards …` against a data directory a newer build migrated (this build's migrations reach schema version 3):

```text
╭─ DATABASE_FROM_NEWER_BUILD ──────────────────────────────────────────────────────────────────────╮
│ this data directory's database is at schema version 9999, and this build reads schema versions   │
│ up to 3: a newer build migrated it                                                               │
│ database_version: 9999                                                                           │
│ build_version: 3                                                                                 │
│                                                                                                  │
│ Schema version 9999 is newer than this build's 3, and an older schema cannot read a newer        │
│ database safely. Sync this checkout (`scripts/task sync <task>`, or `git pull` and `uv sync      │
│ --all-packages`), or install the newer build, then run the command again.                        │
╰───────────────────────────────────────────────────────────────────────────────────────── exit 1 ─╯
```

## Files changed

* `packages/debate_core/src/debate_core/integrations/local/sqlite_db.py`, `…/local/__init__.py`: `DatabaseFromNewerBuild(MigrationError, DomainError)`, raised by `apply_migrations` for a newer schema. `apply_migrations` lost its `database_label` parameter, which only fed the old message's path. The module docstring now explains why this one migration failure is a `DomainError`.
* `packages/debate_core/src/debate_core/application/settings.py`: `RESERVED_SETTING_PATTERNS`, an optional `hint` on `ConfigurationError`, the hint built in `_configuration_error`, and `from None` when an unknown name is among the problems.
* `packages/debate_core/src/debate_core/application/file_build_service.py`: the store comparison returns what differs (`_VersionsThatDiffer`), and `_store_hint` gives each caselist its own way forward. The refusal's message and code are unchanged.
* Tests: `packages/debate_core/tests/integrations/local/test_sqlite_db.py`, `packages/debate_core/tests/application/test_settings_newer_build_names.py` (new), `packages/debate_core/tests/application/test_file_build_service.py`, `packages/debate_cli/tests/test_migration_from_a_newer_build.py` (new), `packages/debate_cli/tests/test_recorded_failure_codes.py`, `packages/debate_cli/tests/test_config_command.py`.
* `plan_specs/v1/e41-delivery-tooling-upkeep/t01-newer-build-messages.yaml`: Goal phase `Succeeded`.

## Deviations from the spec

None. The finding in Follow-up 1 is reported, not fixed: closing it is a scope change.

## Decisions and assumptions

1. **Exit codes.** `DATABASE_FROM_NEWER_BUILD` exits **`1`** (`DOMAIN_FAILURE`). Running the same command again meets the same database, so no retry cures it, and a script must not loop on it as it would on a `3`. The fix (sync, or install the newer build) is the operator's. The code is not on `RETRYABLE_STORE_FAILURES`, so a run that records it is a `1` even beside retryable codes (tested). The settings refusal keeps `CONFIGURATION_ERROR`, exit `1`, unchanged, so scripts that branch on it learn nothing new. Only the `hint` field is new.
2. **Where the database error lives, and why it is a `DomainError`.** It is in `sqlite_db.py`, beside `MigrationError`, and subclasses both. As a `MigrationError` it keeps the module's contract ("raises `MigrationError` if the database records a version this build does not ship"). As a `DomainError`, the CLI's existing handler gives it its own code (`error_code_of` reads the class name), prints its message and carried hint, and exits `1`, with no special case in `exit_codes.py` or `output.py`. The other `MigrationError`s (a broken migration file, an old SQLite) stay defects at exit `70`. `exit_codes.py` needed no change: the `DomainError` rule covers it, and `test_recorded_failure_codes.py` pins it.
3. **No path in the database message.** The CLI now prints this message, and the data directory's path carries the home directory (v1-e01-t25). The message says "this data directory's database".
4. **How the reserved patterns are defined.** `RESERVED_SETTING_PATTERNS = ("providers.*_api_key", "providers.*_token")` in `settings.py`: dotted globs, matched whole with `fnmatchcase`, against the dotted path of a name Pydantic refused as `extra_forbidden`. I kept them to two, each a spelling the providers group already uses for a credential (`openalex_api_key`, `semantic_scholar_api_key`; `caselist_token`). Credentials are what a `.env` carries (they are never committed to a profile), and a `.env` is read from the folder a command runs in, so that is how a newer checkout's setting reaches an older installed build. Matching is per group: `http.core_api_key` gets no hint. A test pins the tuple, so adding a pattern is a visible decision. The hint never changes the verdict: a reserved name is refused like any other.
5. **The hint follows the source.** `.env`: run from another folder, or install the newer build. Process environment: unset the named variable, or install. Profile file: remove it from that file, or install. Any other source: remove it from there, or install. Several reserved names share one hint, and each fix is said once.
6. **No value in the error.** The message lists Pydantic's `msg` per field, which never quotes the input. The hint uses names and sources only. Pydantic's chained `ValidationError` *does* quote every input, so a refusal that includes an unknown name now raises `from None`. Refusals of known fields still chain as before, which keeps their debugging detail. The CLI never printed the chain for a `DomainError`, so this closes a leak path (a log with `exc_info`, a future wrapper) rather than a visible one.
7. **What "newer" means for a parser version.** It is the store's own order: `parse_version_directory`'s plain string comparison, which is how the store lists directories and how `version_retention.standings` judges a directory `newer_than_this_build`. So "newer" is exactly "a re-parse here would write a directory that sorts below it".
8. **Which differences count as "profile only".** The parser version is this build's and the fingerprint stamp is this build's; only the profile differs. When the fingerprint differs too, the hint stays the re-parse (v1-e33-t03's rule for a fingerprint). A newer parser decides the hint whatever else differs.

## Operator follow-ups

None. The affected set (434 files) runs in the pull request's `ci` check.

## Follow-up work

1. **A top-level unknown name in `.env` is silently dropped, not refused** (found in this session, existing behaviour). `DEBATE_NOPE=x` or `DEBATE_CORE_API_KEY=x` in `.env` loads without error. pydantic-settings returns the extra under its prefixed key (`debate_nope`), and `_dotenv_layer` keeps only keys `_dotenv_keys` lists (`nope`), so the extra is dropped before validation. Nested names (`DEBATE_HTTP__NOPE`, every `providers.*`) are refused. A top-level unknown variable in the *process* environment is ignored too, by pydantic-settings' design. Refusing the `.env` case needs an allowlist of legitimate non-field `DEBATE_*` names (`DEBATE_ENV`, `DEBATE_PROFILE_DIR`, …), which is a scope change, so I left it alone. It touches the forbidden item "accepting an unknown setting", so I propose an E41 upkeep task.
2. **A newer fingerprint stamp still gets the re-parse hint in `files build`.** The spec covered parser and profile. A table stamped by a *newer* fingerprint version, at this build's parser version, is told to re-parse. That works for this build (a new generation sorts above), but it downgrades the store for the newer build. If fingerprint versions are ordered, the same "install the newer build" branch could apply. `test_caselist_parse_newer_fingerprint_table.py` suggests `caselist parse` already knows the case.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
