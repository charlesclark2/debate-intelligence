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
**Look first at the PM question below:** under the default, a coach's `search --auto-cut` or
`daily --auto-cut` terminal shows no hint at all. It shows only the code in the Reasons column, and
AUTO_CUT_SHORT's unchanged "Try a broader query" hint. The live hint is in the report file and
`--json` only.

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
* The spec's Goal phase is now `Succeeded`.

## Deviations from the spec

1. **Scope: `search` and `daily` as well as `cut`.** This follows the PM's amendment of 2026-11-14,
   which the PM will record in the spec. It overrides the description's "In `cut`'s output only" and
   the forbidden entry "A change to another command's hint", for this one hint. `search --expand-llm`,
   `search --auto-cut` and `daily --auto-cut` get the live hint under the default. ac1's "another
   command's … hint is unchanged" is tested on what the amendment keeps: `landscape evaluate`, a
   chosen replay, the fake and a script.
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

## Operator follow-ups

None. The affected set is over the two-minute line, so the pull request's `ci` check runs it
(agreement 10); it is not a hand-off.

## Follow-up work

1. **PM question: the auto-cut terminal under the replay default.** The relay block is below.
2. `packages/debate_cli/README.md`'s `search --expand-llm` paragraph (the "`--expand-llm` also asks a
   model…" sentence) could link "Real model calls" as well. It is left as is, because the `cut`
   section is the mention the amendment names.
3. The guide's `docs-index` description does not mention real model calls. Changing it would change
   the generated index on dev, so I left it.

```text
PM question from v1-e06-t09 (cut replay hint names live mode):

Measured: under the replay default, a coach's `search --auto-cut N` or `daily --auto-cut N` prints a
table whose Reasons column says MISSING_FIXTURE_ERROR for every result tried, then the AUTO_CUT_SHORT
panel with its own, unchanged hint: "Try a broader query, a larger --max-results, or cut a paywalled
source from your own copy with fetch --paste and cut --from-paste." The live-mode hint this task adds
is in each entry of <bundle>.report.json and under --json only, so the terminal never says to set
DEBATE_MODEL_MODE=live.

Options:
  A. Leave it. The report and --json carry the hint, and the guide's "Real model calls" says what
     MISSING_FIXTURE_ERROR in the Reasons column means.
  B. One line under the auto-cut table when any entry was refused MISSING_FIXTURE_ERROR under the
     replay default, e.g. "N results were refused: replay is the default. For real calls, export
     DEBATE_MODEL_MODE=live (see "Real model calls" in docs/guides/daily-digests.md)." No error's hint
     changes.
  C. Give AUTO_CUT_SHORT the live hint when every failure was MISSING_FIXTURE_ERROR under the default.
     This changes another error's hint, which the amendment kept unchanged.

Recommendation: B, as a small follow-up task in debate_cli (the batch report presenter and the
container's knowledge of the default). Why: the coach's first auto-cut is the most likely first
contact with replay, and today the only sentence on screen points them at the query. B adds a fact
without touching any error's hint.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
