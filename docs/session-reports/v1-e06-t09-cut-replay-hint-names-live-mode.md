# Session report: v1-e06-t09-cut-replay-hint-names-live-mode

| | |
|---|---|
| Task | `v1-e06-t09-cut-replay-hint-names-live-mode` — `cut` refused for an unrecorded model call says to set DEBATE_MODEL_MODE=live for a real cut |
| Spec | [`plan_specs/v1/e06-card-cutting/t09-cut-replay-hint-names-live-mode.yaml`](../../plan_specs/v1/e06-card-cutting/t09-cut-replay-hint-names-live-mode.yaml) |
| Epic / release | `v1-e06-card-cutting` / `v1.3` |
| Branch | `task/v1-e06-t09-cut-replay-hint-names-live-mode` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Built to the PM's amendment of 2026-11-14, which widens the spec from `cut` alone to every
`debate-research` command whose refusal comes from the replay default. On a real provider with
`DEBATE_MODEL_MODE` unset, a call nobody recorded is still refused with `MISSING_FIXTURE_ERROR` (same
code, same exit code, same fields), but the message now ends with a live-mode hint in place of the
record hint. This covers `cut`, `search --expand-llm`, and every refused cut in a `search --auto-cut` or
`daily --auto-cut` report. The CLI can tell the default from a chosen replay: none of these commands
has a `--model-mode` option, so the variable is the only way to choose. A replay chosen with
`DEBATE_MODEL_MODE=replay` keeps the record hint, and so do the `test` profile's fake, `landscape
evaluate` and every router a script builds itself. The default model mode is unchanged. A new guide
section, "Real model calls", is in `docs/guides/daily-digests.md`, and the CLI README links it.
Then the PM ruled B (2026-11-14), in this task: under the default, the `search --auto-cut` and
`daily --auto-cut` table now ends with one line counting the results refused that way ("4 results
were refused because replay is the default. For real model calls, export DEBATE_MODEL_MODE=live (see
"Real model calls" in docs/guides/daily-digests.md)."). It is never printed under a chosen replay or
with nothing refused, and never in `--json` or the report. AUTO_CUT_SHORT keeps its own hint.

## Measurement before any change (amendment step 1)

Measured on the start commit `71a8bc3`, on a real provider (`models.provider = bedrock`) with
`DEBATE_MODEL_MODE` unset and no cassette recorded. The `cut`, `--expand-llm` and `--auto-cut` rows
come from the red runs of this task's tests (below), and the `search --auto-cut` terminal from a
throwaway in-process run, which was deleted afterwards.

| Command or option | Model calls | How the refusal reaches the person | Hint before this task |
|---|---|---|---|
| `cut URL` and `cut --from-paste` | `card.select`, `card.markup` (the container's card router) | ends the command: exit 1, `MISSING_FIXTURE_ERROR`; the hint is the end of `error.message`, and `error.hint` is `null` | "Record it with DEBATE_MODEL_MODE=record and credentials, outside CI (tests/fixtures/model_cassettes/README.md); replay never calls a real model." |
| `search --expand-llm` | `search.expand` (the search router) | ends the command the same way: the expansion stage absorbs only `ModelOutputError`, `ProviderError` and `BudgetExceededError` ([`query_expansion.py`](../../packages/debate_core/src/debate_core/application/query_expansion.py)) | the same record hint |
| `search --auto-cut N` | the card router, once per result tried | each tried result is a `FAILED` entry with reasons `["MISSING_FIXTURE_ERROR"]` and the whole message in `details`, in `<bundle>.report.json` and under `--json`; the command ends `AUTO_CUT_SHORT`, exit 8 | the same record hint, **in the report only**. The terminal shows the code in the Reasons column and AUTO_CUT_SHORT's own hint, "Try a broader query, a larger --max-results, or cut a paywalled source from your own copy with fetch --paste and cut --from-paste." |
| `daily --auto-cut N` | the card router | as `search --auto-cut`, in `digests/<preset>-<date>.report.json` | as `search --auto-cut` |
| `daily` without `--auto-cut` | none: `DigestExpansionStage` is template-only, and the digest's search has no model router | | |
| `search --auto-cut --expand-llm` | the expansion first | read from the code, not run: the expansion's refusal ends the command before any cut | the record hint |
| `landscape evaluate` (checkout only; its own `--model-mode replay\|record`, replay by default) | `classify.position`, through `container.landscape_model_stage` | ends the command: exit 1, `MISSING_FIXTURE_ERROR` | the record hint (kept, below) |
| `landscape run --model-mode replay` (its default is `none`, which asks no model) | as above | as above | the record hint (kept) |
| any command on the `test` profile (`models.provider = fake`) | the fixture fake | as the command's own path | "Write the answer with FixtureDirectory.write (tests/fixtures/model_cassettes/README.md); the fake router never asks a real model." (kept) |

**What keeps the old hint:**

* `scripts/`: no script builds a model router (`git grep` for `build_model_router`,
  `RecordReplayModelRouter`, `resolve_model_mode` and `add_model_mode_option` finds none there).
* `tests/fixtures/caselist/synthetic_archive/record_landscape_cassette.py` builds a
  `RecordReplayModelRouter` itself, in record mode only, so it never raises this refusal.
* Eval runners: `landscape evaluate` (above) is the one that replays. `tests/evals/parser` makes no
  model call.
* Tests: debate_core's router and factory tests, the root `conftest.py`'s `model_router` fixture (the
  fake), and anything else that calls `build_model_router` or `RecordReplayModelRouter` directly. The
  live hint is given only by the CLI's composition root, so none of them sees it.
* Every other `debate-research` error's hint, AUTO_CUT_SHORT's and BUDGET_EXCEEDED's among them.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `cut-replay-hint-names-live-mode` (Live hint) | Done | Widened by the PM's amendment to `search` and `daily` (Deviations 1); guide section and smoke check added (Deviations 2 and 3). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: `cut` refused for an unrecorded call names DEBATE_MODEL_MODE=live in its hint, and another command's MISSING_FIXTURE_ERROR hint is unchanged, by tests shown failing first | PASS | Red run on commit `10587cf` (the tests alone, before the code): `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest <the five test files below> -k "replay_default or replay_chosen or fixture_fake or keeps_the_record_hint" -n 0 -q --tb=no -rA` → **5 failed, 5 passed**. The 5 failures are the live-hint tests (cut JSON, cut panel, `--expand-llm`, `search --auto-cut`, `daily --auto-cut`), each failing at `endswith(LIVE_MODE_HINT)` on a message ending "…Record it with DEBATE_MODEL_MODE=record and credentials, outside CI (…); replay never calls a real model.". The 5 that passed pin hints that must not change: a replay chosen for `cut` and for `--expand-llm`, the fixture fake, `landscape evaluate`, and a router a script builds. They cannot fail before a change, so each was shown failing under a mutant (below). Same command after `73c796c` → **10 passed**. Smoke check: **1 failed** against the pre-task `container.py`, at its `"set DEBATE_MODEL_MODE=live in this shell …" in message` assertion, and **passed** after. "Another command" is read under the amendment: `landscape evaluate`, a chosen replay, the fake and a script keep their hints. |
| Node: Live hint tests pass (`uv run pytest packages/debate_cli/tests/test_cut_command.py -k "replay or fixture"`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run pytest packages/debate_cli/tests/test_cut_command.py -k "replay or fixture"` → `4 passed in 3.20s` |
| Amendment step 4: mutants (one gives the live hint to an eval runner, one gives the record hint to cut) | PASS | Six mutants, below, each caught at an assertion line. |
| PM ruling B: the line under the auto-cut table, for both commands. It appears under the default with N counted, and is absent under an explicit replay, with nothing refused, and from `--json`. Tests shown failing first. | PASS | Red run on commit `798aa9a` (tests alone): `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_cli/tests/test_search_command.py packages/debate_cli/tests/test_daily_command.py packages/debate_cli/tests/test_batch_report_refused_line.py -k "refused_line or how_many_results or refused_result or chosen_mode" -n 0 -q --tb=no -rA` → **5 failed, 6 passed**. The two end-to-end "line appears" tests (`search`: N = 4, `daily`: N = 2) failed at their `refused_under_the_default_line(N) in printed` assertion. The three presenter tests failed with a `TypeError` (no `replay_is_the_default` parameter yet). That is an API-level red, not a catch, so their assertions are proven by mutants instead. The six absence tests (explicit replay, nothing refused, `--json` and report, for each command) passed at red, as absence must, and are proven by mutants too. Same command after `be1975c` → **11 passed**. |
| PM ruling B: a mutant that prints the line under an explicit replay | PASS | Three mutants, below: one per command, and one in the container. |

### Mutants

Run by a scratch script that applied each mutant, ran the ten hint tests (`-n 0`), and restored the
file with `git checkout HEAD --`. `git status` was clean after. No Hypothesis property is involved,
so agreement 8's database rule does not apply. Every catch below is an `assert … endswith(…)` or
`assert … in …` line, never an import error or a crash.

| Mutant | Caught by |
|---|---|
| The eval runner gets the live hint: `landscape_model_stage` wraps its router too | `test_an_evaluation_refused_for_an_unrecorded_call_keeps_the_record_hint` (1 failed, 9 passed) |
| `cut` gets the record hint back: `_build_card_model_router` returns the bare router | both `cut` live-hint tests, `search --auto-cut`, `daily --auto-cut` (4 failed) |
| A chosen replay is treated as the default (`chosen = False`) | the chosen-replay tests for `cut` and `--expand-llm` (2 failed) |
| The fixture fake is not left out | `test_a_cut_refused_by_the_fixture_fake_keeps_the_fakes_own_hint` (1 failed) |
| `search --expand-llm` gets the record hint back: `_build_search_model_router` returns the bare router | `test_expand_llm_refused_under_the_replay_default_names_live_mode_in_its_hint` (1 failed) |
| A script gets the live hint: debate_core's record-and-replay `_HINT` set to the live text | the script test, `landscape evaluate`, both chosen-replay tests (4 failed) |

The refactor for ruling B moved two of these targets: the "chosen replay ignored" and "fake not left
out" mutants now act on `_replay_is_the_default`. I reran the set on the new code. The eval runner,
`cut`, `--expand-llm` and script mutants were caught as before (1, 4, 1 and 4 failed). The fake mutant
(`return MODEL_MODE_VARIABLE not in os.environ`) was caught by
`test_a_cut_refused_by_the_fixture_fake_keeps_the_fakes_own_hint`, and the chosen-replay one is the
container row of the next table.

Mutants for ruling B's line, run against the line tests and the chosen-replay hint tests the same
way, each restored with `git checkout HEAD --` (clean after):

| Mutant | Caught by |
|---|---|
| **The line under an explicit replay, `search`**: `search_auto_cut.py` passes `default = True` | `search`'s `test_auto_cut_under_a_replay_chosen_with_debate_model_mode_prints_no_refused_line` (1 failed) |
| **The line under an explicit replay, `daily`**: `daily.py` passes `default = True` | `daily`'s `test_auto_cut_under_a_replay_chosen_with_debate_model_mode_prints_no_refused_line` (1 failed) |
| **The container takes a chosen replay for the default**: `_replay_is_the_default` ignores `DEBATE_MODEL_MODE` | both commands' explicit-replay line tests, and the chosen-replay hint tests for `cut` and `--expand-llm` (4 failed) |
| The line with nothing refused (`if replay_is_the_default:` alone) | both commands' "no refused cut" tests and the presenter's (3 failed) |
| Every FAILED entry counted, whatever its code | the presenter's singular test (it counted 2) and its "nothing refused" test (2 failed) |
| The line written into the JSON and the report (a `refused_note` payload key, both commands) | both commands' `--json` tests (2 failed) |

### Checks before the report

| Check | Result |
|---|---|
| Changed test files in full, plus the pins: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest test_cut_command.py test_search_command.py test_daily_command.py test_landscape_evaluate_route.py test_replay_default_hint_scope.py test_installation.py commands/test_doctor.py test_container_factories.py -n 8 -q` (all under `packages/debate_cli/tests/`) | `294 passed in 14.77s` |
| Their slow tests: the same files with `-m slow -n 0 --collect-only` | `no tests collected (294 deselected)`: they hold none |
| Affected set: `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run --slow` | **Stopped at its 115-second limit (exit 124), 15% through and no failure so far.** The selection is 247 test files: 94 under `packages/debate_cli/tests`, 56 under `packages/debate_core/tests`, plus smoke, docs, architecture and spec tests. Agreement 10 puts a run over about two minutes on the pull request's `ci` check, so there is no hand-off. |
| Always-run list and docs checks instead: `pytest tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py -n 8 -m "not slow and not live"` (`test_container_factories.py` is in the row above) | `729 passed in 24.93s` |
| Smoke: `pytest tests/smoke/test_cut_smoke.py -k "live_mode or verified_docx_from" -n 0` (the checkout's console script) | `2 passed` |
| `uv run --frozen ruff format --check .` / `uv run --frozen ruff check .` | `2127 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright` (whole project, as CI) | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `uv run --frozen python scripts/check_thin_handlers.py` | `OK: 74 CLI command and API route handlers within 25 statements` |
| `uv run --frozen python scripts/check_command_blocks.py` / `check_links.py` / `docs_index.py --check-descriptions` | OK: 721 blocks / 3889 links and anchors / 72 descriptions |
| `uv run scripts/validate_specs.py` | `OK: 685 files, 41 epics, 622 tasks, 22 releases` |
| After ruling B: the changed files in full, plus the pins and `test_presenters_configuration_gaps_named_with_their_cure.py` (`-n 8`) | `312 passed in 13.76s` |
| After ruling B: the always-run list, docs checks and `test_container_factories.py` | `735 passed in 24.11s` |
| After ruling B: `uv run --frozen pyright` / `lint-imports` / `check_thin_handlers.py` / `ruff check` | `0 errors` / `20 kept, 0 broken` / `74 … within 25 statements` / `All checks passed!` |
| After ruling B: the affected set | Not rerun. The container still changes, so it reaches the same selection that stopped at 115 seconds above, and it is left to the PR's `ci` check (agreement 10). |

## Files changed

* `packages/debate_cli/src/debate_cli/container.py`: adds `LIVE_MODE_HINT`
  ([container.py:687](../../packages/debate_cli/src/debate_cli/container.py#L687)). Adds
  `_naming_live_mode_under_the_replay_default`, which wraps a router only when the provider is not the
  fake and `DEBATE_MODEL_MODE` is unset. Adds `_LiveModeHintRouter`, which rebuilds a
  `MissingFixtureError` from its fields with the live hint and chains the original as its cause. The
  card and search router builders call the helper (lines 1705 and 1991). It lives in the container
  because the import contract lets only the composition root import `debate_core.integrations`.
* `packages/debate_cli/tests/`: new tests in `test_cut_command.py`, `test_search_command.py`,
  `test_daily_command.py` and `test_landscape_evaluate_route.py`, and the new
  `test_replay_default_hint_scope.py` (a router a script builds). `model_mode_hints.py` holds the three
  hint texts, written by hand. `test_installation.py` and `commands/test_doctor.py` pin
  `debate_core.integrations.models.errors` as a wired integration (45 → 46).
* `packages/debate_cli/README.md`: the `cut` section says when the refusal names live mode and who
  keeps the record hint, and links the guide.
* `docs/guides/daily-digests.md`: new section, "Real model calls".
* `tests/smoke/test_cut_smoke.py`: an installed build's first cut, with no cassette, names live mode.
* Ruling B: `ServiceContainer.replay_is_the_default()` and `_replay_is_the_default` in `container.py`.
  `batch_report_table` and `report_table` take `replay_is_the_default` and end the table with the
  counted line. `search_auto_cut.py` and `commands/daily.py` pass the container's answer. Tests: the new
  `packages/debate_cli/tests/test_batch_report_refused_line.py`, four tests each in
  `test_search_command.py` and `test_daily_command.py`, and the expected line in `model_mode_hints.py`.
  The guide shows the line.
* The spec's Goal phase is now `Succeeded`.

## Deviations from the spec

1. **Scope: `search` and `daily` as well as `cut`.** This follows the PM's amendment of 2026-11-14,
   which the PM will record in the spec. It overrides the description's "In `cut`'s output only" and
   the forbidden entry "A change to another command's hint", for this one hint. `search --expand-llm`,
   `search --auto-cut` and `daily --auto-cut` get the live hint under the default. ac1's "another
   command's … hint is unchanged" is tested on what the amendment keeps: `landscape evaluate`, a
   chosen replay, the fake and a script.
   **Under the same amendment, the PM's ruling B (2026-11-14):** the `search --auto-cut` and
   `daily --auto-cut` tables end with a line counting the results refused under the replay default.
   It is terminal output only, adds no JSON or report key, and changes no error's hint. The presenter
   ([batch_report_presenter.py](../../packages/debate_cli/src/debate_cli/presenters/batch_report_presenter.py))
   is told the mode by the container's new `ServiceContainer.replay_is_the_default()`, which both
   commands call.
2. **`docs/guides` joins the packages**, as the amendment says: `docs/guides/daily-digests.md`'s
   "Real model calls" section.
3. **`tests/smoke/test_cut_smoke.py` is outside `constraints.packages`.** Working agreement 5 asks
   every task that changes a user-facing surface to add or update its smoke checks. The refusal a
   coach's installed build prints is that surface, so I added one offline check (22 lines). The PM
   may rule it out, and it is in its own commit (`557fe36`) to make that easy.
4. **`packages/debate_cli/tests/test_installation.py` and `commands/test_doctor.py`** pin the
   container's integrations. They are inside the packages, but the change to them is a side effect:
   the wrapper's `MissingFixtureError` import adds `debate_core.integrations.models.errors` to the
   wired list.

## Decisions and assumptions

* **The hint text** (no price, no figure):
  "Replay is the default, and it answers only from calls recorded on this machine. For a real call, set
  DEBATE_MODEL_MODE=live in this shell (export DEBATE_MODEL_MODE=live) and run the command again: each
  call is then a model call on this environment's route, which the budget counts. "Real model calls" in
  docs/guides/daily-digests.md says more." The wording names no command, so the same text serves
  `cut`, `--expand-llm` and auto-cut.
* **The hint stays the end of the message, as before; `error.hint` stays `null`.** Every
  `MissingFixtureError` carries its hint that way. An auto-cut report entry has only the message, so
  a hint anywhere else would never reach it.
* **"Chosen" means `DEBATE_MODEL_MODE` is set, to any value.** For these commands that is the only
  control. `DEBATE_MODEL_MODE=replay` keeps the record hint, because a person who chose replay is
  recording or testing.
* **A refusal's optional detail is dropped from the rebuilt message.** The detail is "the cassette at
  this key recorded …; this call is …", given when a cassette at the same key recorded another
  request. The original refusal is the rebuilt one's `__cause__`, so `--verbose` still shows it. The
  detail can only appear where someone has recorded on that machine. It also prints the whole request,
  which carries the article's numbered text. Recovering it from the message would mean parsing text
  around debate_core's private hint.
* **The landscape's routers are left alone.** `landscape evaluate` and `landscape run` replay through
  their own `--model-mode` option, run from a checkout only, and are the operator's eval tooling.
* The guide gives no dollar figure: it names `--max-cost`, `models.budget_usd_daily`, the monthly
  limit and `debate-research usage`.
* **The line's wording is the PM's, except for one result.** The PM's text is "<N> results were
  refused because …". For N = 1 the line says "1 result was refused because …", and the rest of the
  sentence is the PM's word for word. Say if you want "1 results were refused" kept literally.
* **What the line counts:** entries with status `FAILED` whose reasons include `MISSING_FIXTURE_ERROR`.
  It is printed only when the container says replay is the default. Under the default, every such
  refusal comes from the card router this task wraps. The count is a presentation tally, read off the
  BatchReport the service built, so it decides no status.
* **"The default" for the line is the hint's rule:** a real provider with `DEBATE_MODEL_MODE` unset.
  It now lives in one function, `_replay_is_the_default`, which the router wrapper and
  `ServiceContainer.replay_is_the_default()` both use, so the line and the hint cannot disagree.
* The line is the last line under the table, after `Model cost:`, so it is the last thing on stdout
  before the AUTO_CUT_SHORT panel.

## Operator follow-ups

None. The affected set is over the two-minute line, so the pull request's `ci` check runs it
(agreement 10); it is not a hand-off.

## Follow-up work

1. `packages/debate_cli/README.md`'s `search --expand-llm` paragraph (the "`--expand-llm` also asks a
   model…" sentence) could link "Real model calls" as well. It is left as is, because the `cut`
   section is the mention the amendment names.
2. The guide's `docs-index` description does not mention real model calls. Changing it would change
   the generated index on dev, so I left it.

The PM question this report first raised (the auto-cut terminal under the replay default) was
answered by ruling B and is built in this task.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-14

**Notes:**

Accepted. ac1, the node and the amendment's steps pass, and the Goal is `Succeeded`.

* **The measurement is what the amendment asked for.** Every model-calling path is listed with how
  its refusal reaches a person, and so is what keeps the record hint: scripts (none builds a
  router), the one record-only fixture script, `landscape evaluate` and `run`, the fake and the
  tests. That is how the gap in the auto-cut terminal was found, which ruling B closed.
* **The design is sound.**
  * The live hint is given only at the CLI's composition root, by a wrapper on the card and search
    routers. It applies when the provider is real and `DEBATE_MODEL_MODE` is unset.
  * The code, the exit and the fields are unchanged, and the original refusal is kept as
    `__cause__`.
  * One function, `_replay_is_the_default`, decides both the hint and ruling B's line, so they
    cannot disagree.
  * The default model mode is unchanged.
* **The decisions are accepted.**
  * "Chosen" means the variable is set, which is the only control these commands have.
  * Dropping the optional cassette-mismatch detail from the rebuilt message is right for a coach.
    That detail prints the whole request, the article's numbered text included, and `--verbose`
    still shows it through the cause.
  * "1 result was refused" for N = 1 is accepted.
  * The line is placed last, before the AUTO_CUT_SHORT panel.
* **The evidence.**
  * The red runs: 5 of 10 and 5 of 11. The tests that must pass at red were proven by mutants
    instead, and so were the presenter tests whose red was an API `TypeError`.
  * All 12 mutants were caught at assertions, both PM-named ones among them, and the set was rerun
    after the refactor for ruling B.
* **Deviations 1 to 4: accepted.**
  * 1 and 2 are the amendment and ruling B, which the PM records in the spec, with `docs/guides`, in
    the next batch.
  * 3, the offline smoke check, is accepted under agreement 5; `tests/smoke` joins the packages.
  * 4, the wired-integration pin moving from 45 to 46, is accepted.
* **The checks.** The affected set (247 files) stopped at its bound with no failure and goes to `ci`
  under agreement 10. The changed files, the always-run list, pyright, the import contracts and the
  smoke check are green. If `scripts/task pr` asks, `scripts/task sync`.
* **Follow-ups 1 and 2** are PM doc edits in the next batch, not tasks: the README's `--expand-llm`
  paragraph links "Real model calls", and the guide's docs-index description mentions it.

`scripts/task pr`
