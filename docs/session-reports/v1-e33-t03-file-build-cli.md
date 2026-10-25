# Session report: v1-e33-t03-file-build-cli

| | |
|---|---|
| Task | `v1-e33-t03-file-build-cli` — `debate-research files` commands |
| Spec | [`plan_specs/v1/e33-file-builder/t03-file-build-cli.yaml`](../../plan_specs/v1/e33-file-builder/t03-file-build-cli.yaml) |
| Epic / release | `v1-e33-file-builder` / `v1.2` |
| Branch | `task/v1-e33-t03-file-build-cli` |
| Session status | COMPLETE, with one criterion only `validate-dev` can close (ac6). Phase left `InProgress`; merge with `--partial` |

## Summary

`debate-research files build <recipe>`, `files check <file>` and `files suggest` are three thin
commands over two new services in `debate_core.application`: `FileBuildService` (build and check)
and `FileSuggestService`. A build runs the PM's order: load the recipe, refuse a draft unless
`--allow-draft`, refuse a store another parser or fingerprint version made (once, before any card
is resolved, both versions and the re-parse named), refuse an output directory inside a git working
tree, resolve and list every `RecipeError`, name each card resolved to an unattributed occurrence,
fail a missing source with `SOURCE_MISSING` and its `store get`, write through t02's writer, then run
t04's `FileQualityService` as the container wires it. The resolver now prefers attributed
occurrences (a camp row with its release record counts) and asks `publish_plan.stored_row_hold` for
each disclosure record of a row. `files suggest` reads the landscape's own top-card counts through a
dry `LandscapeRunService` run and writes a `status: draft` recipe. All 21 targeted mutants are caught.
**Look first at the PM question** (below): a suggested pin names a school and team code when two
teams disclosed the same bytes, and I implemented my recommendation pending your ruling.

Commit ids below are on `dev` at `0ee0e95` (after `scripts/task sync`, which brought in
`v1-e32-t11`). `v1-e32-t13` was not yet on `dev`, so the runbook has not met its change.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| (resolver amendments, ac7 and ac9) | Done | `0e7466e`. Not a node of its own in the spec: the amendments of 2026-10-19 and 2026-10-20 change t01's resolver, which `build-service` resolves through |
| (writer DRAFT header, ac2) | Done | `7151930`. The writer is t02's; the header is the one place a built file can say DRAFT |
| `build-service` | Done | `4496dfa`, and the bucket-lock classification fix `360af68` |
| `suggest-service` | Done | `431f610` |
| `cli-commands` | Done | `ee18802` |
| `smoke-checks` | Done locally | `ee18802`. Runs in validate-dev only after the merge (ac6) |
| `quality-gates` | Done | Commands and results below |
| (removal runbook step 8) | Done | `f53813c`, the 2026-10-21 amendment |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: `files build` on an example recipe against the synthetic corpus writes a `.docx`, a `.provenance.json` and a PASS `.quality.json`, prints cards placed, sources used, tag overrides and warnings; exits non-zero listing every RecipeError when resolution fails | PASS | `test_files.py::test_files_build_writes_the_docx_sidecar_and_a_pass_report_for_each_example` builds all three of t01's examples (rewritten onto synthetic sources, Deviation 2), each counted by hand: policy 5 cards / 5 sources / 2 overrides, PF 4/4/1, LD 4/4/1, 0 warnings, PASS. `…prints_cards_sources_overrides_warnings_and_each_check` reads the Rich line "5 card(s) placed from 5 source(s), 2 tag override(s), 0 warning(s)". `…lists_every_recipe_error_and_exits_1`: exit 1, both `UNKNOWN_CARD` errors in the JSON and the panel. Service level: `test_every_resolution_error_is_listed_and_nothing_is_written`, `test_every_load_error_is_listed_and_nothing_is_resolved` |
| ac2: a draft is refused unless `--allow-draft`, and then the header analytic says DRAFT | PASS | `test_files_build_refuses_a_draft_without_allow_draft_and_builds_it_with`: exit 2 `DRAFT_NOT_ALLOWED` naming `--allow-draft`, nothing written; with the flag, exit 0 and the header starts `DRAFT: `. `test_draft_header.py`: red 1 failed, 1 passed (the ready header unchanged) before the writer change |
| ac3: `files suggest --caselist <slug> --position <p> --top 10` emits a recipe that validates against `docs/data/file-recipe.schema.json`, pins every card to an existing occurrence, orders cards by read count, holds no tag overrides or evidence text | PASS | `test_file_suggest_service.py` (19 passed): schema validation with `jsonschema`, every pin resolves `PINNED` to the hand-worked occurrence, ranks (1, 5), (2, 4), (3, 1) equal to the landscape report's `top_cards` rows for the position, comments `# rank N: read by K teams through <date>`, no `tag_override`, no tag, cite or path in the text. Order is read count within each block, blocks by their most-read card (Decision 6). CLI: `test_files_suggest_writes_a_draft_that_files_build_builds_with_allow_draft` |
| ac4: a missing source blob fails that card with `SOURCE_MISSING` and a hint to run `debate-research store get`, building no partial file | PASS | `test_files_build_with_a_missing_source_names_store_get_and_builds_nothing`: blob deleted, exit 1, the one card `SOURCE_MISSING` with `debate-research store get raw/caselist/hspolicy26/sha256/…`, no file written. Service level: two cards of one missing source, both named, the writer never called |
| ac5: `files build` exits non-zero naming the failing checks on a FAIL, and `files check` on a tampered built file reports the same FAIL without rebuilding | PASS | `test_files_build_runs_the_wired_quality_check_and_exits_1_naming_the_failing_checks`: exit 1 `QUALITY_FAILED`, `evidence-identity` named, files kept. `test_files_check_reports_a_tampered_built_file_as_fail_without_rebuilding`: one word of evidence changed inside `word/document.xml`, exit 1 naming `sidecar` and `evidence-identity`, the `.docx` and sidecar bytes unchanged afterwards |
| ac6: `tests/smoke/test_files_cli.py` covers build, check and suggest on synthetic data and runs in validate-dev | PASS locally; NOT RUN in validate-dev | `.venv/bin/python -m pytest tests/smoke/test_files_cli.py -m "not live and not in_process"` → `2 passed in 34.50s`, against this checkout's console script (import, parse with two workers, build, check PASS and a tampered copy FAIL, suggest and build the draft). validate-dev runs it on the pre-release the merge builds, so that run can only be recorded after the merge, as `v1-e32-t05`'s ac4 was |
| ac7: AUTO prefers attributed occurrences, `files build` names every card resolved to an unattributed one before building, by tests shown failing first; t01's guide states the rule | PASS | Red before the resolver change: 8 failed, 5 passed (the passes are the fallback and must-not-stop cases). `test_cards_resolved_to_unattributed_occurrences_are_named_before_the_writer_runs`: the events are `["unattributed:1", "writer"]` (red against the skeleton). CLI: `test_files_build_notes_each_unattributed_card_before_its_result`. Guide: `test_the_guide_puts_an_attributed_occurrence_first_in_the_auto_order`, red on the old guide (`assert 4 == 5`) |
| ac8: a store parsed by another parser or fingerprint version is refused once, before any card is resolved, naming both versions and the re-parse, by test shown failing first | PASS | `test_a_store_of_another_parser_version_is_refused_once_before_resolving` and `…fingerprint_version…`: `STORE_PARSED_BY_ANOTHER_VERSION`, both versions in the message, `debate-research caselist parse --caselist hspolicy26` in the hint, `read_occurrences` never called. Two caselists, one refusal: `test_every_caselist_a_recipe_reads_is_compared_and_named_in_one_refusal`. Red against the skeleton: the parser case raised the resolver's own `OccurrenceStoreNotReady` mid-resolve, the fingerprint case built. CLI: `test_files_build_refuses_a_store_another_parser_made_naming_both_versions` |
| ac9: an occurrence a hold stops is never resolved, by AUTO or by a pin, before a rebuild, through `stored_row_hold`; a camp occurrence with a release record counts as attributed for AUTO; each by test shown failing first | PASS | In the resolver red run above: `test_auto_passes_over_an_occurrence_at_a_held_path_and_takes_the_next`, `test_a_pin_to_an_occurrence_at_a_held_path_is_refused_not_repointed`, `test_one_held_record_of_a_row_stops_the_row`, `test_the_resolver_asks_stored_row_hold_for_each_record_of_a_row` (records every call to the function), `test_auto_counts_a_camp_occurrence_with_its_release_record_as_attributed`; each failed before the change |
| ac10: `files build` runs the wired quality check, refuses an output directory inside a git working tree, and the writer's highlighted-cite refusal is reached by a test on a constructed card, each shown failing first | PASS for the first two clauses; the last clause NOT APPLICABLE | Wired check: `test_files_build_runs_the_wired_quality_check…` replaces the container's `file_quality`, and the build runs it; mutant W1 (the build builds its own) is caught by it. Git tree: `test_an_output_directory_inside_a_git_working_tree_is_refused_before_resolving` (a `.git` directory and a worktree's `.git` file), red against the skeleton; CLI exit 2. The highlighted-cite clause is superseded by the PM amendment of 2026-10-22 (from `v1-e33-t08`'s review): t08 removed the refusal, so there is nothing to reach. The PM amends ac10's wording after the merge |
| Node `build-service`: `uv run pytest packages/debate_core/tests/application/test_file_build_service.py` | PASS | `22 passed in 2.40s` |
| Node `suggest-service`: `uv run pytest packages/debate_core/tests/application/test_file_suggest_service.py` | PASS | `19 passed in 4.97s` |
| Node `cli-commands`: `uv run pytest packages/debate_cli/tests/commands/test_files.py` | PASS | `19 passed in 12.19s` |
| Node `cli-commands`: `uv run debate-research files build --help` | PASS | exit 0; the help states exits 0, 1 and 2 by paragraph |
| Node `cli-commands`: `uv run pytest packages/debate_cli/tests/commands/test_files.py -k check` | PASS | `7 passed in 12.65s` |
| Node `smoke-checks`: `uv run pytest tests/smoke/test_files_cli.py` | PASS | `2 passed in 27.13s` |
| Node `quality-gates`: `uv run pyright packages/debate_cli` | PASS | `0 errors, 0 warnings, 0 informations` |
| Node `quality-gates`: `uv run pyright packages/debate_core` | PASS | `0 errors, 0 warnings, 0 informations` |
| Node `quality-gates`: `uv run lint-imports` | PASS | `Contracts: 16 kept, 0 broken.` |

### Red runs

Each recorded before the code it tests existed, by the method the PM asked for:

| Tests | Against | Result |
|---|---|---|
| `test_file_recipes_attributed_and_held.py` (13) | the start commit's resolver | 8 failed, 5 passed: the unattributed fallback, a withdrawn attributed row, two camp releases with records, a pin to an unattributed row, a hold dated after the disclosure; each a case the old rule already met and the new one must not break |
| `test_draft_header.py` (2) | the writer before the change | 1 failed (draft), 1 passed (ready, unchanged) |
| `test_file_build_service.py` (22) | a skeleton with every type and the happy path, refusing nothing | 12 failed, 10 passed: the passes are the happy paths and the error lists t01's loader and resolver already give |
| `test_file_suggest_service.py` (17 then) | a naive skeleton: one block, no pins, no comments | 13 failed, 4 passed (it loads, holds no override, card text or team, and a dry run writes nothing). A first attempt errored on my own fixture's taxonomy (`kind: other`); it was discarded, not counted |
| `test_files.py` (17 then) | the CLI with the `files` group unregistered | 17 failed; `commands/__init__.py` restored and checked by SHA-256 |
| the guide and runbook tests | the start commit's guide and runbook | 2 failed; both files restored and checked by SHA-256 |

### Mutants (21, each with a fresh Hypothesis database; every file restored and checked by SHA-256)

| Id | Mutant | Verdict | Caught by |
|---|---|---|---|
| A1 | AUTO ignores attribution | CAUGHT | 3 tests: attributed over a later unattributed one, latest among attributed, camp release record |
| A2 | AUTO prefers an unattributed row | CAUGHT | 4 tests |
| A3 | AUTO's order after attribution drops recency | CAUGHT | 5 tests, t01's own included |
| A4 | a camp row is never attributed | CAUGHT | `test_auto_counts_a_camp_occurrence_with_its_release_record_as_attributed` |
| A5 | a camp row is always attributed | CAUGHT | the same test |
| A6 | a camp row is attributed by its disclosure, as a caselist row is | CAUGHT | the same test |
| A7 | every caselist row is attributed | CAUGHT | 2 tests |
| H1 | no row is ever held | CAUGHT | 5 tests |
| H2 | AUTO does not ask about holds | CAUGHT | 4 tests |
| H3 | a pin does not ask about holds | CAUGHT | `test_a_pin_to_an_occurrence_at_a_held_path_is_refused_not_repointed` |
| H4 | a row is held only when every record of it is | CAUGHT | 34 tests (`all([])` holds every row with no record) |
| H5 | only the latest record of a row is asked about | CAUGHT, by the recording test alone | Equivalent in behaviour: a row's records share one path, and a hold covers every snapshot after its date, so the latest record is held whenever any is. Only `test_the_resolver_asks_stored_row_hold_for_each_record_of_a_row` tells them apart. Kept, because the search index build asks the same way (each record) and the amendment names the rule to ask |
| H6 | the hold asked of the state directly, not of `stored_row_hold` | CAUGHT, by the recording test alone | Equivalent in these cases: `stored_row_hold` adds the openev, undated-snapshot and already-suppressed exits, none of which a held caselist row reaches. The amendment's "through `stored_row_hold`" is what the recording test holds |
| V1 | no store is ever refused | CAUGHT | 6 tests |
| V2 | the parser version is not compared | CAUGHT | 4 tests |
| V3 | the fingerprint stamps are not compared | CAUGHT | `test_a_store_of_another_fingerprint_version_is_refused_once_before_resolving` |
| V4 | the oldest directory is taken as the store's version | CAUGHT | `test_a_store_parsed_by_a_newer_parser_too_is_refused` |
| V5 | only the recipe's own caselist is compared, not its pins' | CAUGHT | 2 tests |
| V6 | the version refusal comes after the git working tree refusal | CAUGHT | `test_the_version_refusal_comes_before_the_git_working_tree_refusal` |
| V7 | the version refusal comes after resolving | CAUGHT | 6 tests |
| W1 | the build builds its own quality check instead of the wired one | CAUGHT | `test_files_build_runs_the_wired_quality_check_and_exits_1_naming_the_failing_checks` |

### Before the report (working agreements 8 and 10)

* `uv run scripts/affected_tests.py` chose **201 of 472 test files (42.6%)** from 27 changed files. On
  this machine at a load average of 7 to 28 (other sessions), that is more than two minutes, so per
  agreement 10 the whole affected set is left to the pull request's `ci`. Within the limit, each
  under `perl -e 'alarm 115; …' .venv/bin/python -m pytest … -n auto -m "not slow and not live"`, I
  ran 155 of the 201 and every package test among them:
  * the always-run list and the docs checks (`tests/architecture`, `tests/specs`, `test_app.py`,
    `test_help_rendering.py`, `tests/docs`, the command-block and docs-index tests) → `481 passed`;
  * `packages/debate_cli/tests` in three parts: `commands/` → `441 passed`, `bucket_mode/` → `58 passed`
    (after the fix below), the rest → `501 passed`;
  * `packages/debate_core/tests/application` (top level) → `1976 passed`, and its affected subdirectory
    files → `474 passed`;
  * the writer, the quality checks, the recipe domain, the API's card download, the recipe schema
    script and the two smoke checks this touches (`test_files_cli.py`, `test_landscape_smoke.py`) →
    `459 passed`;
  * the other affected files under `packages/` (core integrations, retrieval, the API) → `1252 passed`.
  * **Left to `ci`:** 46 files under `tests/` (the smoke tier, `tests/scripts`, `tests/integration`,
    `tests/evals`), which start installed binaries and process pools. Two attempts at them ran past
    the limit; no worker was left behind.
* **A check this run found:** `bucket_mode/test_bucket_mode_lock.py` fails a registered command no
  one has classified; the three `files` commands now are, as never writing a bucket (`360af68`).
* **And one the sync found:** `v1-e32-t11` and this task each added a wired integration and each
  moved the pinned count from 22 to 23; git merged both to 23 without a conflict. The real count is
  24, and `test_installation.py` and `test_doctor.py` now say so.
* Cheap whole-repo checks, as `ci.yml` runs them: `ruff format --check .` (1300 files formatted),
  `ruff check .` (all passed), `pre-commit run check-merge-conflict --all-files` (passed),
  `pyright` on both packages and on `tests/smoke` and `tests/fixtures/file_builder` (0 errors),
  `lint-imports` (16 kept), `scripts/check_thin_handlers.py` (54 handlers within 25 statements),
  `scripts/validate_specs.py` (`OK: 439 files, 40 epics, 377 tasks, 22 releases`),
  `scripts/docs_index.py --check-descriptions` (47 documents), `scripts/check_command_blocks.py`
  (426 blocks, no comments).
* No property test touches this task's code, so agreement 8's fresh database was set for form only.

## Files changed

* **`packages/debate_core/src/debate_core/application/`**: `file_build_service.py` and
  `file_suggest_service.py` (new); `file_recipes.py` (AUTO attributed first, holds through
  `stored_row_hold`); `landscape_run.py` (a `top_cards` on the request; the taxonomy and landscape
  cards on the result, for suggest).
* **`packages/debate_core/src/debate_core/integrations/docx_file_writer/writer.py`**: the DRAFT header
  and `FILE_BUILDER_VERSION` `2026.10.24-file-writer-4` (Deviation 3).
* **`packages/debate_cli/src/debate_cli/`**: `commands/files.py`, `presenters/` (new), the group's
  registration, and the container's `file_build`, `file_quality`, `file_suggest` and `files_dir`.
* **Tests**: the four new core test files and `test_draft_header.py`; `test_files.py`; the pinned
  integration, service and bucket-classification lists; t08's comparison test, which pins the running
  writer's version; `tests/smoke/test_files_cli.py`; `tests/fixtures/file_builder/example_corpus.py`.
* **Docs**: `docs/runbooks/caselist-removal.md` step 8; `docs/guides/file-recipes.md` (the AUTO rule,
  holds, where files live).
* **Spec**: the Goal's phase was set to `InProgress` by `scripts/task start`; nothing else changed.

## Deviations from the spec

1. **`settings.files_dir` is not a setting.** `StorageSettings` says every local path derives from
   `data_dir` "so one environment is one directory and nothing escapes it". The container derives it:
   `FILES_DIRECTORY = files` under the data directory, built files in `files/built/<topic>/` as the
   spec says, drafts in `files/recipes/<topic>/`, where t01's guide already put recipes.
2. **ac1 builds t01's examples rewritten, not as written.** Their fingerprints are invented, and a
   fingerprint is a digest of a card's text, so no corpus can hold them. As for t02's example files
   (your ruling of 2026-10-19), `tests/fixtures/file_builder/example_corpus.py` gives each card
   reference a synthetic source and rewrites the fingerprints and pins' hashes and indices, keeping
   every heading, analytic, override and pin field; the examples are unchanged. FAIL as written, PASS
   as so read.
3. **The writer's version moves to `2026.10.24-file-writer-4`.** Its comment says it is bumped
   whenever the bytes a recipe builds to change, and a draft's header now does. A ready recipe builds
   the same bytes as `-3`. t08's comparison test pins the running writer's version as text, so it and
   its fixture README now say so.
4. **Two files outside `constraints.packages`**, each required by a criterion:
   `tests/fixtures/file_builder/example_corpus.py` (ac1's "synthetic fixture corpus", beside the
   `recipes/` it names) and `docs/guides/file-recipes.md` (ac7: "t01's guide states the rule").
5. **ac10's last clause is not applicable** (the PM amendment of 2026-10-22); recorded, not edited.

## Decisions and assumptions

1. **The order of the checks** is the PM's, with the draft refusal first: it reads only the recipe,
   so it is not "resolving". Load, draft, store versions, git tree, resolve, unattributed, sources,
   write, quality.
2. **The store's version is its newest directory**, as the port lists them (parser version, then
   generation). A store of another parser version, older or newer, is refused, and so is an occurrence
   table stamped with any fingerprint version other than this build's. That is stricter than the
   resolver, which accepts every version in `EXACT_FINGERPRINT_VERSIONS`. The spec says "when they
   differ", and re-stamping the table is one `caselist parse`, which re-parses nothing. Every caselist
   the recipe reads is compared, its pins' too, and all of them go into one refusal. A caselist with
   no store, or whose aggregates a removal deleted, is `STORE_NOT_PARSED`, in the same refusal.
3. **An unattributed card is named, not refused.** t04's `provenance-complete` passes a caselist card
   with no disclosure on record, so the build goes on; the names reach the CLI through a callback
   before any source is read, and the command prints them to stderr.
4. **A held occurrence is `SUPPRESSED_OCCURRENCE`**, with its own message. A hold is kept beside the
   suppression list, and the coach's fix is the same: pin another or remove the pin.
5. **Suggest pins with the resolver's AUTO rule**, attributed first and then latest, rather than
   "the most recent occurrence" alone, so a suggestion and a build agree. A pin names the caselist,
   source and element index, and narrows only when the resolver refuses it as matching several
   disclosures: side, then tournament, then round, then school and team code (the PM question).
6. **"Orders cards by read count"** under the grouping the spec asks for: blocks in the order of
   their most-read card, cards by rank within a block. A strictly monotone file would need one block.
7. **Block headings are the landscape's normalized headings** (the innermost over each copy, the
   disclosing team's names taken out), not the raw text, which can name a team. They read in lower
   case; the coach edits a draft anyway.
8. **A draft is never written over**: one that exists may hold the coach's edits.
9. **Every quality check reads this machine's copy of the suppression list.** t04's follow-up
   suggested the local and bucket copies, but a build may not reach S3 (the forbidden list), so the
   check a build runs reads what it read. The runbook says to run `files check` after the removal's
   `--execute` on this machine.
10. **Exit 2** for what is refused before anything is read (a draft, a git tree; suggest's unknown
    names and taken or tracked paths), as `landscape report` exits 2 on its unknown names.
11. **`files check` writes its reports beside the file wherever it is**, and builds nothing. It is not
    refused inside a git tree: the reports hold digests and positions, and refusing would only hide
    a FAIL from whoever already put a built file there.
12. **`check` explains a file built by `2026.10.19-file-writer-1` or `-2`**: when its
    `provenance-complete` fails, the hint says the old writer wrote provenance lines and to rebuild
    over the same recipe (with its hash). The versions are listed in the application layer, which
    may not import the writer.

## PM question

```text
v1-e33-t03 (files commands): one question, with my recommendation. I implemented the
recommendation; changing it is small.

Your brief asked me to count what an occurrence pin carries. It has nine fields: caselist,
source_sha256, element_index, snapshot, and five that say who disclosed the card: school,
team_code, side, tournament, round. No field holds a path.

Where two teams disclosed the same bytes (common: squads share files), a pin of the key alone
matches both disclosures and the resolver refuses it (PIN_MISMATCH). So a suggested pin to such
a card must name more, and the school and team code are what finally tell two teams apart.

Options:
(a) Narrow only as far as needed, least personal first: side, then tournament, then round, then
    school and team code, stopping at the first that resolves; refuse a draft path inside a git
    working tree (as files build refuses its output) and never overwrite a draft.
    -> ac3 passes; a draft names a team only for a shared file. (Implemented.)
(b) Never name a school or team code: leave such a card unpinned, so a build resolves it by
    AUTO, and say so in a comment.
    -> no team in any draft; ac3's "pins every card" FAILS as written for shared files.
(c) Always write every disclosure field the occurrence has.
    -> simplest; a team in every draft that has disclosures on record.

Recommendation: (a). It is the least personal data that still pins every card, and a draft
lives in the evidence workspace (<data dir>/files/recipes/), where the policy allows a team
code, under the same git-tree refusal as a built file. In the synthetic tests, a file two
teams disclosed in different rounds is pinned by its round, with no team.

FYI, proceeding unless you say otherwise:
- FILE_BUILDER_VERSION is now 2026.10.24-file-writer-4 (a draft's header changes its bytes).
- files_dir is <data dir>/files, derived, not a setting.
- ac1 builds t01's examples rewritten onto synthetic sources, as for t02's example files.
- ac6 is recorded from the first validate-dev run after the merge.

Reply: a, b or c.
```

## Operator follow-ups

**After the merge, before `scripts/task finish`:** a draft for one CP on `hspolicy26` and a build of
it, over the dev data directory, printing counts only. Nothing is published: both commands read this
machine's stores and write under `~/.debate-research/dev/files/`, which is outside any git working
tree and is the evidence workspace a draft's pins and a sidecar may name a team in. Run it in a new
terminal window. Each block refuses a leftover `DEBATE_*` variable and a running `caselist pull`, and
sets `DEBATE_ENV` for its one command. Expected runtime: one to five minutes for the suggestion, which
runs the landscape dry over the whole caselist (a dry run took 54 s in `v1-e32-t09`, and `v1-e32-t11`'s
analytic texts may add to it); seconds for the build.

The suggestion first:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e33-t03-file-build-cli
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set in this window; open a new one"; elif pgrep -f 'debate-research caselist pull' >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else DEBATE_ENV=dev uv run debate-research --json files suggest --caselist hspolicy26 --position states-cp --top 10 | jq '{status, code: .error.code, cards: (.data.cards // [] | length), left_out: (.data.left_out // [] | length), pins_naming_a_disclosure: ([.data.cards // [] | .[] | select(.pin_names | length > 0)] | length)}'; fi
```

Read it before the next block. Success: `"status": "ok"` and `cards` above zero (up to 10). A
`code` of `UNKNOWN_CASELIST`, `NO_TOPIC_MAPPING` or the like means the landscape cannot run here;
paste it back and stop. Then the build of that draft:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e33-t03-file-build-cli
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set in this window; open a new one"; elif pgrep -f 'debate-research caselist pull' >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else DEBATE_ENV=dev uv run debate-research --json files build ~/.debate-research/dev/files/recipes/policy-2026-27-nhi/states-cp-neg-draft.yaml --allow-draft | jq '(.data // .error.details) as $r | {status, code: .error.code, cards_placed: $r.counts.cards_placed, sources: $r.counts.sources_used, warnings: $r.counts.warnings, unattributed: ($r.unattributed | length), quality: $r.quality.status, by_check: ([$r.quality.checks // [] | .[] | {(.check): .status}] | add)}'; fi
```

Success: `"status": "ok"`, `cards_placed` equal to the suggestion's `cards` and above zero, and
`quality` `"PASS"` with every check PASS or WARN. Paste both outputs back. A `code` of
`STORE_PARSED_BY_ANOTHER_VERSION` means the dev store needs `caselist parse --caselist hspolicy26`
with this build first; `QUALITY_FAILED` names its checks in `by_check`, and the files are kept for a
look.

## Follow-up work

1. **`v1-e33-t07`** (camp path on occurrence rows): when it lands, a camp-path withdrawal stops a camp
   row through the same resolver question; nothing here was built for it (your brief).
2. **`v1-e33-t05`** (publish): gate on the report's `status` PASS; `FileBuildResult.failing_checks`
   and `files check` give it what it needs. A draft (`status: draft`, header `DRAFT`) should be
   refused there too.
3. **The style profile version is not compared before a build** (ac8 names parser and fingerprint).
   A store whose newest generation was written under another profile, same parser version, would give
   `OCCURRENCE_MISMATCH` per card, as ac8's case did. Rare; it could join the same refusal.
4. **The landscape's dry run may re-read analytic texts every time** (`v1-e32-t11`): if the operator
   block above takes minutes, `files suggest` could ask for a run without them. For `v1-e32`.
5. **`pyproject.toml`'s contract "The CLI reaches lxml only through debate_core.integrations.docx_parser"**
   now also reaches it through `docx_file_writer`. It allows indirect imports, so nothing breaks; its
   name claims less than it allows. Renaming it is a `pyproject.toml` edit, which makes the whole
   selection affected, so it is left for a task that edits that file anyway.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-24

**Notes:**

A large task, built in the order ruled and tested where it matters.
1. **ac1 to ac5 and ac7 to ac9 pass, red first.** ac10's first two clauses pass, and its last clause
   is not applicable, as ruled (the PM's batch l amended ac10 on dev). The check order is load,
   draft, store versions, git tree, resolve, unattributed, sources, write, quality. It is pinned by
   mutants V6 and V7. 21 of 21 mutants were caught.
   * H5 and H6 are behaviourally equivalent and caught only by the recording test. Keeping them, and
     saying so, is right: the amendment names the rule to ask, `stored_row_hold` for each record.
2. **ac6 waits on validate-dev after the merge,** as with v1-e32-t05's ac4. It merges with
   `--partial`, phase `InProgress`. The PM records the run and sets the Goal `Succeeded` in a PM
   batch.
3. **The PM question: (a), as built, with one condition.** Narrowing least personal first (side,
   tournament, round, then school and team code) names a team only for a shared file, which is the
   least personal data that still pins every card. A draft never overwrites, and its path is refused
   inside a git working tree.
   * **The condition:** data-use policy 1.14 lists a built file's sidecar among the places personal
     data may live, but not a file recipe. The PM adds file recipes under the data directory's
     `files/` beside the sidecar, as policy 1.15, in a PM batch. Charlie's approval is the merge of
     that batch.
   * Until then, the operator's suggest-and-build block waits. The code needs no change.
4. **Accepted as made:**
   * Deviation 1: `files_dir` derived from `data_dir`, not a setting;
   * Deviation 2: t01's examples rewritten onto synthetic sources, as for t02;
   * Deviation 3: `FILE_BUILDER_VERSION` bumped to `-4` for the draft header;
   * Deviation 4: the corpus fixture and the guide;
   * Decision 2, which is stricter than the resolver (any other parser or fingerprint version is
     refused), since the fix is one `caselist parse`;
   * an unattributed card named rather than refused;
   * suggest pinning by the resolver's own AUTO rule, so a suggestion and a build agree;
   * normalized block headings, so no team's name reaches a draft through a heading;
   * `check` not refused in a git tree;
   * the local suppression list only, since a build may not reach S3;
   * the corrected pinned integration count of 24. The sync merged two edits to 23 without a
     conflict, and catching that was good work.
5. **The affected set:** 155 of 201 files ran within the limit and passed. The 46 smoke,
   integration and evals files are left to the PR's `ci` under agreement 10.
6. **Follow-ups the PM files in a PM batch:** the style-profile version in the store refusal
   (follow-up 3); t05's publish gate on PASS, refusing drafts (follow-up 2, into t05's spec); and the
   lxml contract's name, folded into the next task that edits `pyproject.toml`. Follow-up 4 (suggest's
   dry run re-reading texts) is not needed: v1-e32-t11's cache makes a warm run about a minute.
7. **Shared file:** v1-e32-t13 also edits `docs/runbooks/caselist-removal.md`. If the sync conflicts
   there, keep both sides.

**After the merge:** once policy 1.15 is merged, the operator's two blocks (suggest `states-cp`, then
build the draft with `--allow-draft`), counts only, before `scripts/task finish --partial`. No
re-review is needed.
