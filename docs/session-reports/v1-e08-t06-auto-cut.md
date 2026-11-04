# Session report: v1-e08-t06-auto-cut

| | |
|---|---|
| Task | `v1-e08-t06-auto-cut` — `--auto-cut N` batch cutting |
| Spec | [`plan_specs/v1/e08-research-workflows/t06-auto-cut.yaml`](../../plan_specs/v1/e08-research-workflows/t06-auto-cut.yaml) |
| Epic / release | `v1-e08-research-workflows` / `v1.4` |
| Branch | `task/v1-e08-t06-auto-cut` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`debate-research search "<query>" --argument A --need N --auto-cut N --output bundle.docx` is built.
`BatchCutService` (in `debate_core.application`) walks the search's ranked results in rank order.
It skips any result an earlier retrieval recorded as inaccessible, or that this run's retrieval
finds inaccessible, and lists each one with its access status. Each attempt goes through
`ArticleFetch` and then `CardService`, both unchanged, with at most `--concurrency` attempts running
at once under a semaphore. The run stops when N cards are VERIFIED, when the results run out, or
when the budget guard refuses a model call. The output is one DOCX bundle: VERIFIED cards under a
single block heading named for the argument and need, then, only if there are any, the UNVERIFIED
cards in their own section headed "UNVERIFIED — not finished cards". Beside it go
`bundle.manifest.json` and `report.json`, and a Rich table prints. Every criterion passes on
recorded fixtures and the fake router. **The phase is Succeeded.**

Look at these first:

1. **The additive renderer change** (your Q1 ruling, option A). `render_cards_docx` gained
   `unverified_from`. Called without it, the renderer gives the bytes pinned in commit 282d90b,
   which was committed before the renderer changed (conditions 1 and 2 below).
2. **Deviation 2**: the manifest carries a card's section as its status plus its position, not as a
   key. A key would need manifest version 3, which every older `verify` refuses.
3. **Exit codes 8 and 9** are new rows in the CLI's public table (`exit_codes.py`, the CLI README,
   `search --help`). Both numbers were unused anywhere.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `batch-service`: BatchCutService with concurrency and skipping | Done | `application/batch_cut_service.py`. The walk, `SpendTally` (per-task cost), `batch_candidates`, `batch_need`. 25 tests. |
| `bundle-export`: DOCX and manifest bundle export | Done | `ExportService.export_docx_bundle` and `export_json_bundle`; `unverified_from` in `evidence/docx_renderer.py` and the port; `UNVERIFIED_SECTION_HEADING` in `evidence/card_rendering.py`. 10 tests. |
| `cli-auto-cut`: --auto-cut flag and report output | Done | `commands/search.py` (the options, still 22 statements), `debate_cli/search_auto_cut.py`, `presenters/batch_report_presenter.py`, `container.py` (`batch_cutting`, `spend_tally`, `argument_taxonomy`), exit codes 8 and 9. 19 CLI tests and the smoke help check. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: `search "health insurance" --argument politics-da --need link --auto-cut 3` on fixtures produces a DOCX bundle with 3 verified cards under one block heading and a matching JSON manifest bundle | PASS | `test_auto_cut_writes_three_verified_cards_under_one_block_heading_and_a_matching_manifest`: exit 0. The bundle's first paragraph is `Politics DA — Link: health insurance`, which appears once. Three card tags come before any UNVERIFIED section. The embedded manifest's bytes equal `bundle.manifest.json`'s. Its first three cards are VERIFIED and match report.json's VERIFIED entries. Those entries' URLs are the three pages the fixtures say verify, a set written by hand from `fixtures/search/README.md`. The news article's evidence word `surrogate` is in neither stdout nor report.json. |
| ac2: paywalled or robots-disallowed results are skipped and listed in the report with their access status; the batch continues | PASS | CLI: `test_auto_cut_skips_paywalled_and_robots_disallowed_results_lists_them_and_goes_on` (`--auto-cut 4`, so every result is tried). The Harbor Review page is `SKIPPED`/`PAYWALLED` and the Closed Stacks page `SKIPPED`/`ROBOTS_DISALLOWED`, each `SOURCE_NOT_ACCESSIBLE` with no card. The three verifiable pages are still VERIFIED, and both statuses print in the table. `test_auto_cut_does_not_fetch_a_result_an_earlier_fetch_found_paywalled`: `fetched: false`, and no request reached the host. Service: `test_paywalled_and_robots_disallowed_results_are_skipped_and_the_batch_goes_on`, plus the ERROR-is-refetched, all-inaccessible and exhausted cases. |
| ac3: no more than `--concurrency` cuts run at once (instrumented fakes), and the run stops with a BUDGET_EXCEEDED entry when `--max-cost` is reached | PASS | Service, instrumented fetch and cut: `test_no_more_than_concurrency_cuts_run_at_once[1,2,3]`, where the peak equals the concurrency (6 cuts). `test_no_more_cuts_run_than_the_cards_still_wanted`: peak 2 at concurrency 5 and N=2. Budget: `test_the_budget_guard_stops_the_run_and_the_verified_cards_are_kept`, `test_after_the_budget_stops_a_run_no_waiting_candidate_starts_and_running_cuts_finish`, `test_a_run_the_budget_stops_short_of_n_is_not_complete`. CLI: `test_auto_cut_stops_at_the_budget_guard_exits_9_and_keeps_the_verified_card` (exit 9, last entry `BUDGET_EXCEEDED`, one card in the bundle) and `test_auto_cut_max_cost_is_the_commands_per_run_budget` (the container's `models.budget_usd_per_run` is 0.25). |
| ac4: the per-result report prints as a Rich table and is written as report.json beside the bundle; exit code is 0 only if N verified cards were produced | PASS | `test_auto_cut_report_prints_as_a_table_and_is_report_json_beside_the_bundle` covers the six columns, the title, `Report: <dir>/report.json`, and the settings and files in report.json. `test_auto_cut_json_output_carries_the_search_and_the_report`: `data.auto_cut` equals report.json. Exit codes: 8 for 3 of 4 and for 3 of 5 (`error.details.auto_cut` equals report.json), 9 for the budget, and 0 with N verified on a partial search (`test_auto_cut_exits_0_with_n_verified_when_the_search_was_partial_and_names_the_provider`, `partial_providers: ["rss"]`). A failed search keeps exit 3 and cuts nothing. |
| Node: batch service tests pass (`uv run pytest packages/debate_core/tests/application/test_batch_cut_service.py`) | PASS | `25 passed in 2.39s` |
| Node: bundle export tests pass (`uv run pytest packages/debate_core/tests/application/test_export_service.py -k bundle`) | PASS | `10 passed in 2.49s` |
| Node: auto-cut CLI tests pass offline (`uv run pytest packages/debate_cli/tests/test_search_command.py -k auto_cut`) | PASS | `19 passed in 3.56s` |
| Node: import boundaries hold (`uv run lint-imports`) | PASS | `Contracts: 20 kept, 0 broken.` |

### The PM's conditions on Q1 (2026-11-03)

1. **Byte-identical.** `test_bundle_renderer_called_as_before_writes_todays_bytes[flow, plain, team-default]`
   renders the committed news-article card twice through `render_cards_docx` without
   `unverified_from`: once VERIFIED, once filed UNVERIFIED with two codes, with pocket, hat and block
   headings. It compares the SHA-256 of the bytes. The three hashes were measured on the renderer at
   07039c0, read identically from two runs, and committed in 282d90b before the renderer changed.
   They pass unchanged after it. One fact found on the way: span ids are fresh ULIDs on every cut, so
   the test fixes them first. Without that, two runs of today's renderer already differed.
2. **Separation, in code.**
   - `test_bundle_refuses_an_unverified_card_among_the_verified` and
     `test_bundle_refuses_a_verified_card_in_the_unverified_section` (DOCX and JSON) both ran red
     first. The first failed at its `match`, because the misfiled card reached the renderer with no
     banner codes. The second failed with `DID NOT RAISE` on the JSON bundle. Each refusal happens
     before the renderer is called.
   - The renderer refuses a misfiled card, or an empty section, itself:
     `test_bundle_renderer_refuses_an_empty_unverified_section_or_a_card_in_the_wrong_one`.
   - Each UNVERIFIED card keeps its own banner, and the heading is exactly
     `UNVERIFIED — not finished cards`: `test_bundle_files_the_verified_cards_under_the_block_and_then_the_unverified_section`
     (two UNVERIFIED cards, two banners, each straight after its tag; both block headings in the
     block style).
   - The section comes after every VERIFIED tag, and is absent when there is no UNVERIFIED card
     (`test_bundle_with_no_unverified_card_has_no_unverified_section`).
3. **Manifests.** `test_bundle_manifests_list_every_verified_card_before_any_unverified_one`: the
   embedded manifest equals `export_json_bundle`'s bytes, its statuses read back as three VERIFIED
   then two UNVERIFIED, and its card ids are in bundle order. See Deviation 2 for "section".

### Red first

* **Service**, against a skeleton whose `cut` tried nothing: **19 failed, 5 passed**. The five that
  passed don't depend on the walk: empty input, the need text, two request validations and the
  tally-only test. 16 failed at an assertion and 3 at an empty unpack or index.
* **Unpriced model** (your FYI 3 check): `test_a_call_the_guard_cannot_price_under_a_limit_ends_the_run_before_any_card`
  against the service before the fix: `FAILED` then `VERIFIED` (the batch carried on). After the
  fix it stops with `BUDGET_EXCEEDED` and `UNPRICED_MODEL_ERROR`.
* **CLI**, against `auto_cut_options` returning None (the flags ignored): **15 failed, 4 passed**.
  The four that passed: `--help`, Typer's own range checks for `--concurrency 9` and `--auto-cut 0`,
  and the failed-search path, which this task leaves as it was. One test failed by crashing on the
  missing bundle, after its exit-code assertion had passed.
* **Smoke** help check on dev's `search.py`: failed at `'8  auto-cut short' in …`.

### Mutants

Each was planted in the committed tree, run against its test file (`-n 0 -p no:randomly`), and then
restored with `git checkout HEAD --`. No Hypothesis property is involved. 18 planted, 17 caught at
an assertion, 1 caught by the renderer's guard, and 1 survivor, removed as agreement 8 asks.

| Mutant | Result |
|---|---|
| UNVERIFIED counted toward N | caught: 2 tests |
| `verified` includes UNVERIFIED | caught: 2 |
| no semaphore bound (1000) | caught: 4 (peak 6 where 1, 2, 3) |
| budget refusal does not stop | caught: 3 |
| known-inaccessible fetched anyway | caught: 1 |
| gate ignores running cuts | caught: 2 (5 fetched where 2) |
| waiting candidate starts after the stop | caught: 1 |
| a fetched non-ACCESSIBLE report is cut | **survived**: ArticleFetch gives a snapshot only for ACCESSIBLE, so the status half of the check could not be told from its absence. Removed (07039c0); CardService still refuses any non-ACCESSIBLE snapshot. |
| renderer skips its section check | caught: 1 |
| section heading never written | caught: 2 |
| export always opens a section | caught by the renderer's own refusal (raised as `ExportRefused`), not an assertion |
| export's VERIFIED-in-UNVERIFIED check off | caught: 1 |
| heading words changed | caught: 2 |
| a short run exits 0 | caught: 5 |
| a budget stop exits 8 | caught: 2 |
| a partial search is not cut | caught: 1 |
| `--max-cost` not applied to the settings | caught: 1 |
| `section` missing from report.json | caught: 1 |

### Before the report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` | `230 of 683 test files (33.7%) chosen in 16.1 s from 21 changed files` (container.py and export_service.py are hub modules) |
| `hard_stop.py 115 uv run scripts/affected_tests.py --run` | Stopped at its 115-second limit at about 26%, with no failure up to then. Over two minutes, so the full set is left to the PR's `ci` (agreement 10), with no operator hand-off. |
| The always-run list and the changed areas, within the limit: `hard_stop.py 115 … pytest -m "not slow and not live" tests/architecture tests/specs` with `debate_cli` `test_app.py`, `test_help_rendering.py`, `test_container_factories.py`, `test_search_command.py`, `test_search_presenter.py`, `test_cut_command.py`, `test_installation.py`, `commands/test_doctor.py`, `test_usage_command.py`, `test_verify_command.py`, `test_recorded_failure_codes.py`; `debate_core` `test_batch_cut_service.py`, `test_export_service.py`, `test_export_docx.py`, `test_verify_docx.py`, `test_budget.py`, `evidence/test_docx_renderer.py`, `evidence/test_docx_verify.py`; `tests/smoke/test_search_smoke.py`, `test_usage_smoke.py` | First run: 1 failed, 873 passed. `test_a_command_module_imports_no_other_command_module[search]` caught `commands/search_auto_cut.py`, so the module moved to `debate_cli/search_auto_cut.py` (ec91908). Second run: **873 passed in 76.70s**. |
| `uv run --frozen ruff format --check .` / `ruff check .` | `1917 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright packages/debate_cli` and the changed `debate_core` modules, tests and fixtures | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` / `scripts/check_thin_handlers.py` | `20 kept, 0 broken` / `72 … handlers within 25 statements` (`search` 22) |
| `uv run scripts/validate_specs.py` | `OK: 608 files, 41 epics, 545 tasks, 22 releases` |
| `scripts/check_command_blocks.py --base origin/dev`, `check_links.py`, `docs_index.py --check-descriptions` | `OK: no # comments in 670 shell code blocks` (1 session report changed) / `OK: 3523 relative links and anchors` / `All 68 indexed documents under docs/ have a description` |

## Files changed

* **`packages/debate_core/src/debate_core/application/`**
  * `batch_cut_service.py` (new): the walk, `SpendTally`, candidates and need.
  * `export_service.py`: `export_docx_bundle`, `export_json_bundle`, and a shared `_docx`. `export_docx`'s renderer call is unchanged.
  * `ports/card_document.py`: the port's `unverified_from` keyword.
* **`packages/debate_core/src/debate_core/evidence/`** (added to the spec's packages by your ruling)
  * `docx_renderer.py`: `unverified_from`, the section heading and `_check_sections`.
  * `card_rendering.py`: `UNVERIFIED_SECTION_HEADING`.
* **`packages/debate_cli/src/debate_cli/`**
  * `commands/search.py`: the five options, help and exit codes; the search run moved into `_searched` to stay within the handler budget.
  * `search_auto_cut.py` (new): which options go together, the run, the files.
  * `presenters/batch_report_presenter.py` (new): table, report.json, failures, exit code.
  * `container.py`: `BatchCutting`, `batch_cutting()`, `spend_tally()`, `argument_taxonomy()` (also used by the search now), and a usage log that reports each record's cost to the tally.
  * `exit_codes.py`, `README.md`: `AUTO_CUT_SHORT` 8 and `BUDGET_EXCEEDED` 9.
* **Tests**
  * `packages/debate_core/tests/application/test_batch_cut_service.py` (new); the bundle section of `test_export_service.py`; `test_export_docx.py`'s recording renderer takes the new keyword (and asserts it is never given).
  * `packages/debate_cli/tests/test_search_command.py`: the auto-cut section; `Seams` gained optional article, card-router and Crossref seams. Existing tests keep today's wiring.
  * `packages/debate_cli/tests/fixtures/search/openalex_auto_cut.body.json` (new, synthetic) and its README entry.
  * `tests/fixtures/card/every_page_router.py` (new): one hand-written answer per prompt that fits every cassette page, so concurrent cuts need no call order.
  * `tests/smoke/test_search_smoke.py`: the help check names the new options and codes.
* **`plan_specs/…/t06-auto-cut.yaml`**: `debate_core.evidence` in `constraints.packages` with your dated note, and the phase.

## Deviations from the spec

1. **`debate_core.evidence` changed** (your Q1 ruling, option A). The spec said the renderer would be
   reused unchanged; it could not write a second section. `docx_renderer.py` and
   `ports/card_document.py` gained `unverified_from`, and `card_rendering.py` the heading constant.
   The spec's packages now list `debate_core.evidence`, with a YAML comment above the line naming
   the ruling and both files. The comment sits above the line because inside a folded description
   it would become text.
2. **A card's section is its status and its place, not a manifest key.** Your condition 3 asks the
   embedded manifest and `bundle.manifest.json` to give each card its status and section.
   `CardManifest` is `extra="forbid"`, and a build refuses any manifest version it does not know. A
   `section` key would therefore be manifest version 3, which every older `verify` refuses. That is
   a format change outside this task. Each card's status is in both manifests, and every card
   listed before the first non-VERIFIED one is VERIFIED (a test reads that back). `report.json`
   gives `section` (`verified` or `unverified`) on every entry explicitly. If you want the key in
   the manifest itself, it is a manifest-version task for E06.
3. **`--card-format PROFILE`**, not `--format` (your FYI 1): `search --format` already means table
   or JSON.
4. **Outside the first packages:** `tests/smoke/test_search_smoke.py` (agreement 5, your FYI 4) and
   test fixtures under `tests/fixtures/`.
5. **`--auto-cut` without `--argument` and `--need` is a usage error (2).** The spec cuts "using the
   search's argument/need as the research need", so without them there is no need to cut for.

## Decisions and assumptions

* **The research need** is the taxonomy's own words. The argument's label goes in `CutRequest.argument`
  (`Politics DA`). The need is `<need label> for <query>: <need description>`
  (`Link for health insurance: How the plan or action sets the argument off.`). The block heading is
  `Politics DA — Link: health insurance`.
* **The candidates** are the search's ranked results, so `--max-results` (default 20) bounds them.
  Each is fetched at the URL `search --json` shows, which is what `cut` would be given.
* **What counts as known-inaccessible**: an Article recorded PAYWALLED, BLOCKED, ROBOTS_DISALLOWED,
  NOT_FOUND or UNSUPPORTED_TYPE. ERROR is fetched again, because a failed fetch may answer. No paywalled-host
  list exists in E04, and none was added (ruling 3).
* **No over-cutting.** A candidate starts only while VERIFIED cards plus running cuts are fewer than
  N. Which candidates are cut is therefore the same whatever order cuts finish in, until a budget
  stop. Entries are reported in rank order.
* **Failures.** A `DomainError` from fetch or cut is a FAILED entry with its code, and the walk goes
  on. A budget refusal or an unpriced call ends the run (BUDGET_EXCEEDED, exit 9). Anything else is
  a bug and propagates.
* **Cost.** Each real call is recorded in the usage log in the asyncio task that made it, and the
  container's log reports that cost to `SpendTally`. Each entry's cost is therefore its own even
  under concurrency. Replay and fake calls record nothing (0). An unpriced call makes the entry, and
  the total, `null`.
* **Unpriced under `--max-cost`** (FYI 3): the existing guard refuses the call before it is made
  (`test_budget.py`'s two `test_an_unpriced_model_is_refused_…` tests). The batch now treats that
  refusal as a stop, pinned in the service and the CLI. Without a limit the guard isn't built, and
  `null` in the report is the only sign.
* **Files.** `report.json` is written whatever the outcome once cutting starts. The bundle and the
  manifest are written only when a card was cut. Each file is written atomically. report.json takes
  the spec's fixed name, so two runs into one directory replace it.
* **`--concurrency`** defaults to 2, with a maximum of 8. `--auto-cut` takes 1 to 50.

## Operator follow-ups

None are needed to merge.

**Optional, after the merge, once a dev pre-release containing it is installed: one small live
auto-cut**, for the PM to decide on. It makes live calls to OpenAlex and the publisher feeds, a
fetch of each page tried, and Bedrock calls on dev's route for `card.select` and `card.markup`
(`complex_reasoning`): Claude Haiku 4.5, at $0.001 per 1K input and $0.005 per 1K output tokens
(`config/model_pricing.yaml`, as of 2026-10-27), with an output cap of 8,192 tokens.

- **Expected cost:** two calls per card cut. At about 3–5K input and a few hundred output tokens
  each, that's roughly $0.005–0.01 per cut, so **about $0.02–0.06** for `--auto-cut 2`, including
  cuts that end UNVERIFIED.
- **Why `--max-cost 0.50`:** the budget guard admits a call by its ceiling, the 8,192-token cap plus
  its input (about $0.04–0.06 a call). A lower cap could stop the run before the second card.
- **What it touches:** dev's local data directory and a folder on your Desktop only. Under a few
  minutes.

**Operator command 1: check the installed build** (seconds)
Where: your Mac, any terminal
```bash
debate-research search --help | grep -c -- '9  budget exceeded'
```
Success looks like `1`. A `0` means the installed build has no `--auto-cut`.

**Operator command 2: the live auto-cut** (a few minutes; about $0.02–0.06)
Where: the same terminal, signed in to the AWS profile dev's models use
```bash
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; else mkdir -p "$HOME/Desktop/auto-cut-check" && cd "$HOME" && env DEBATE_ENV=dev DEBATE_MODEL_MODE=live debate-research --json search "health insurance" --argument politics-da --need link --auto-cut 2 --concurrency 2 --max-cost 0.50 --output "$HOME/Desktop/auto-cut-check/bundle.docx" > /tmp/auto-cut-check.json; echo "exit $?"; python3 -I -c 'import json, sys; r = json.load(open(sys.argv[1])); print("verified", r["verified"], "of", r["wanted"], "unverified", r["unverified"], "stop", r["stop_reason"]); print("search", r["search_status"], "partial", r["partial_providers"], "cost", r["cost_usd"]); print("entries", [(e["rank"], e["status"], e["access_status"], e["reasons"], e["cost_usd"]) for e in r["entries"]])' "$HOME/Desktop/auto-cut-check/report.json"; fi
```
Success looks like `exit 0`, `verified 2 of 2`, `stop COMPLETE`, and a `cost` above zero and under
0.50. `exit 8` (results ran out) or `exit 9` (budget) is an answer too: paste back the three lines.
The bundle and the full report stay on your Desktop.

## Follow-up work

* **One `--max-cost` for the whole command.** Each model router is its own budget "run"
  (`build_model_router` makes a new `run_id`). With `--expand-llm` and `--auto-cut` together, the
  search's router and the card router therefore each get the full `--max-cost`. Passing one
  `run_id` to every router the container builds for a command would make it one limit (E05 or E41).
* **A `section` key in the card manifest** (Deviation 2), if wanted: manifest version 3, with
  `verify` reading it (E06).
* **v1-e09-t05** can drive this from fixtures: `openalex_auto_cut.body.json`, the HTTP cassettes,
  `EveryPageRouter` and Crossref's recorded answer give a deterministic bundle, manifest and report.
* **Per-run report names.** `report.json` is replaced by the next run into the same directory. A
  `--report PATH` option, or `<name>.report.json`, would keep both (E08).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-03

**Notes:**

Built as ruled, with the separation of verified and unverified cards enforced in three places (the
service, the export and the renderer) rather than by convention.

1. **ac1 to ac4 pass** on recorded fixtures and the fake router, each red first (service 19 failed, CLI
   15 failed, the smoke help check failed), and the evidence word of an UNVERIFIED article absent from
   stdout and report.json.
2. **The Q1 conditions are met.** (1) Byte-identical: the three SHA-256 hashes were committed in
   `282d90b` before the renderer changed, and pass unchanged after; fixing the span ids first was right,
   since today's renderer already differed run to run. (2) The export refuses a card in the wrong section
   in both directions (red first), the renderer refuses on its own, each UNVERIFIED card keeps its
   banner, and the section is absent when empty. (3) The manifests read back verified first.
3. **Deviation 2 accepted.** A `section` key would be manifest version 3, which every older `verify`
   refuses: a format change for E06, not this task. Status and place in the manifests, and `section` in
   report.json, meet the condition's purpose. Not filed now; it becomes a task only if a reader needs the
   key.
4. **FYI checks met.** Exit codes 8 and 9 were unused and are in the public table, the README and the
   help. An unpriced model under `--max-cost` is refused by the existing guard and now stops the batch,
   pinned in the service and the CLI.
5. **Deviations 1, 3, 4 and 5 accepted:** the renderer change (the PM's ruling), `--card-format`, the
   smoke file and fixtures (agreement 5), and `--auto-cut` requiring the research need.
6. **The mutant survivor's removal is accepted.** The removed status check could not be told from its
   absence, because ArticleFetch gives a snapshot only for ACCESSIBLE, and CardService still refuses any
   other.
7. **Follow-ups the PM files:** one `--max-cost` for the whole command (E05, p2). Today a command with
   `--expand-llm` and `--auto-cut` gives each router the full limit, so it can spend up to twice what
   `--max-cost`'s help promises; at the default caps that is cents, but the help should be true. Also
   per-run report names (E08, p3). v1-e09-t05 is noted as unblocked, with this task's fixtures named.
8. **The optional live auto-cut** (about $0.02 to $0.06, the price read from the pricing file) waits
   until v1-e31-t32's "before" copy on Thursday 2026-11-05 is done, because it needs a dev build
   carrying this merge and no newer build is installed before that copy. The PM records it if run.
9. **Closing checks:** the affected set (230 files) is left to `ci` (agreement 10). The bounded run of
   the changed areas and the always-run list (873 passed, after moving `search_auto_cut.py` out of
   `commands/`), ruff, pyright, lint-imports, thin handlers (`search` at 22), the specs, links and
   command blocks are clean.
10. **Merge:** a plain `scripts/task pr` once `ci` is green. The Goal is `Succeeded`.
