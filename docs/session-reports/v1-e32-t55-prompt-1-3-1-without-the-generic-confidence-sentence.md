# Session report: v1-e32-t55-prompt-1-3-1-without-the-generic-confidence-sentence

| | |
|---|---|
| Task | `v1-e32-t55-prompt-1-3-1-without-the-generic-confidence-sentence` — Prompt 1.3.1: 1.3.0 without the generic-confidence sentence |
| Spec | [`plan_specs/v1/e32-argument-landscape/t55-prompt-1-3-1-without-the-generic-confidence-sentence.yaml`](../../plan_specs/v1/e32-argument-landscape/t55-prompt-1-3-1-without-the-generic-confidence-sentence.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t55-prompt-1-3-1-without-the-generic-confidence-sentence` |
| Session status | PARTIAL (the Goal stays InProgress: ac2's re-record on `deep_audit` is the operator's) <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**The Goal stays InProgress, and the session ends PARTIAL.** ac2 is the operator's re-record of the 47 on
`deep_audit` under 1.3.1, which the PM records beside 1.3.0's. Its block is under
[Operator follow-ups](#operator-follow-ups). ac1 passes.

**What was built:**

* **Prompt 1.3.1** (`prompts/landscape/classify_position@1.3.1.md`): 1.3.0 with one sentence taken out of
  the confidence paragraph: "A generic position is never named by a tag or heading: give it 0.9 or more
  ...". Every other line of the body is 1.3.0's, byte for byte.
* **Its status:** released, locked in `prompts/prompts.lock.json`, and the stage's default
  (`CLASSIFY_POSITION_VERSION`).
* **Cassettes:** 1.3.1's are keyed by 1.3.1. 1.3.0's recordings replay unchanged when 1.3.0 is asked for.
* **Tests:** written first and shown failing against the tree before 1.3.1, then 15 mutants, all caught.

**What the PM should look at first:**

* The front matter differs from 1.3.0's in two places as well as the sentence. A prompt file must carry its
  own version and a changelog entry for it, or the registry refuses it. So "every other line is
  byte-identical" holds for the body, which is what the model is sent. The diff test allows exactly those
  two front-matter changes and the one removal ([decision 1](#decisions-and-assumptions)).
* The bar, the threshold, the coach's labels and every other bullet are untouched. No model was called, and
  the block's price is read from `config/model_pricing.yaml`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `prompt-1-3-1-without-the-generic-confide` (Prompt 1.3.1) | Done | Red tests (`4eb6702`), then the prompt, lock, default and the synthetic archive's cassette (`770a455`), then the runbook block and the evaluation's record (`89c8c76`). Its criterion passes (1,253 tests). ac2 waits on the operator |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: Prompt 1.3.1 differs from 1.3.0 by the one sentence, is locked and the default, its cassettes keyed by it and 1.3.0's replaying unchanged, by tests shown failing first | PASS | See [How ac1 was shown](#how-ac1-was-shown) below |
| ac2: the operator's re-record of the 47 on deep_audit under 1.3.1, its breakdown and scans, recorded beside 1.3.0's (operator, recorded by the PM) | NOT RUN (operator) | A live model call on the operator's Bedrock profile, which no session makes. The block is under [Operator follow-ups](#operator-follow-ups) and in [the record runbook's last section](../runbooks/landscape-model-evaluation-record.md#prompt-131-the-re-record-on-deep_audit-v1-e32-t55). The PM records the result |
| Node: Prompt 1.3.1 tests pass (`uv run pytest packages/debate_core/tests/arguments/landscape`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run pytest packages/debate_core/tests/arguments/landscape` → 1,253 passed in 7.6 s |

### How ac1 was shown

**The tests:**

* `packages/debate_core/tests/arguments/landscape/test_prompt_without_the_generic_confidence_sentence.py`
  (new), five tests:
  * the diff test reads both files as bytes and diffs them line by line. It allows exactly three changes:
    the version line, one inserted block before the front matter's closing fence starting
    `  - version: 1.3.1`, and the confidence line with " " + the sentence removed. The sentence must occur
    exactly once in 1.3.0;
  * the inserted block is one changelog entry for 1.3.1 after 1.3.0's history, and every other
    front-matter field is 1.3.0's;
  * the body, as the registry reads it, is 1.3.0's less the sentence;
  * 1.3.1 is released, in the stanced schema, `high_volume`, and its lock entry is what the lock script
    writes for it;
  * the stage runs 1.3.1 unless it is built with another, and 1.3.0 when built with 1.3.0.
* `packages/debate_core/tests/application/test_coach_sample_stance.py`, beside t49's:
  * the default asks 1.3.1 in the stanced schema; a stage built with 1.3.0 still asks 1.3.0;
  * 1.3.0's recordings replay unchanged (7 counted, 5 right, as recorded) and the default finds none of
    them (`MissingFixtureError` naming 1.3.1);
  * a default recording is keyed by 1.3.1, replays under the default, and 1.3.0 finds none of it;
  * t49's test that 1.2.0's recordings replay and 1.3.0 finds none now asks 1.3.0 by name rather than by
    the default.
* The version pins that follow the default move to 1.3.1: two in `packages/debate_cli/tests/test_landscape_command.py`
  and one in `tests/smoke/test_landscape_evaluate_smoke.py`.

**Red, against the tree before 1.3.1** (no 1.3.1 file, the default still 1.3.0), the new and changed tests
with the two CLI pins: **10 failed, 61 passed.** Each failed for its reason:

* 4 on the missing file (`FileNotFoundError`, or `UnknownPromptError`: "has no version '1.3.1'");
* 6 on the default still being 1.3.0 (`'1.3.0' == '1.3.1'`), one of them as `DID NOT RAISE
  MissingFixtureError`, because the default still replayed 1.3.0's recording.

The smoke pin was not in that run; mutant 13 below shows it failing on a 1.3.0 default.

**Green:**

* 1.3.1 is released and locked: `uv run scripts/lock_prompts.py` printed `locked
  landscape.classify_position@1.3.1`, and `--check` exits 0. The lock gains one entry and changes none.
* `diff` of the two files shows the version line, the 7-line changelog entry, and line 75 losing its last
  sentence, nothing else.
* The synthetic archive's one landscape cassette is keyed by the default, so it was rewritten offline by
  its own script (`uv run --frozen python -m tests.fixtures.caselist.synthetic_archive.record_landscape_cassette`,
  0.3 s, no model). Its diff is the key and the prompt version, nothing else (93% similar, renamed).

### Mutants

Each was applied by a script, run against its tests with `-n 0` and a fresh, empty
`HYPOTHESIS_STORAGE_DIRECTORY`, and restored with `git checkout HEAD --`. The tree was clean after. Prompt
mutants ran against the new test file (5 tests). Default mutants ran against it plus
`test_coach_sample_stance.py`, the two CLI pins, the evaluate smoke file and the synthetic archive's test
(78 tests). Every catch is an assertion failure, not a crash.

| Mutant (on 1.3.1's file unless named) | Caught by |
|---|---|
| 1. The sentence left in | the diff test, the body test, the lock test |
| 2. The sentence removed but its leading space kept | the same three |
| 3. Another bullet's sentence also removed ("Never answer null for such a card.") | the same three |
| 4. One word of the confidence paragraph changed (0.9 to 0.8) | the same three |
| 5. The confidence paragraph's 0.6 clause removed as well | the same three |
| 6. A trailing space on another body line | the same three |
| 7. One body line in CRLF | **the diff test only**: the registry reads `\n` line endings, so the body and the lock match |
| 8. A word of the user turn changed | the diff test, the body test, the lock test |
| 9. A blank line added at the end | the same three |
| 10. Another front-matter field changed (`owner`) | the diff test, the front-matter test |
| 11. An older changelog entry's summary edited | the diff test, the front-matter test |
| 12. 1.3.1's changelog entry placed before 1.3.0's | the diff test, the front-matter test |
| 13. `CLASSIFY_POSITION_VERSION` back to 1.3.0 (`landscape_model_stage.py`) | 8 tests: the default test in each file, both replay tests, both CLI pins, the smoke pin, the synthetic archive's cassette test |
| 14. The stage's parameter default hard-coded to 1.3.0 while the constant says 1.3.1 | 6 tests: the stage test, both replay tests, both CLI pins, the smoke pin |
| 15. 1.3.1 left a draft (so never locked) | the diff test, the front-matter test, the lock test |

Mutant 7 is why the diff test reads bytes rather than the registry's body. Mutant 14 misses
`test_the_stage_asks_prompt_1_3_1_by_default_in_the_stanced_schema`, which checks the constant and the
schema, not the version asked. The stage test and the replay tests catch it.

### Checks run before this report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` | 293 of 714 test files (41.0%) chosen in 17.8 s from 14 changed files |
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run` | Stopped at its 115-second limit (exit 124) before the run finished. Left to the pull request's `ci` (agreement 10) |
| The changed test directories and the always-run list: `packages/debate_core/tests/{arguments/landscape,integrations/models}`, every `test_landscape_*` and `test_coach_sample_*` and `test_position_classification.py` in `debate_core/tests/application`, `debate_cli/tests/test_landscape*.py`, `tests/smoke/test_landscape*.py`, `tests/integration/test_e2e_caselist.py`, `tests/fixtures/caselist/test_synthetic_archive.py`, `tests/architecture`, `tests/specs`, `test_app.py`, `test_help_rendering.py`, `test_container_factories.py`, with `-m "slow or not slow"`, bounded at 115 s | 2,876 passed in 41 s |
| `uv run ruff format --check .`, `uv run ruff check .` | 1,988 files already formatted; all checks passed (after `62619ed` shortened one line) |
| `uv run pyright packages/debate_core packages/debate_cli`, and `tests/smoke/test_landscape_evaluate_smoke.py` | 0 errors |
| `uv run lint-imports`, `uv run python scripts/check_thin_handlers.py` | 20 contracts kept, 0 broken; 72 handlers within 25 statements |
| `uv run scripts/lock_prompts.py --check`, `uv run scripts/check_command_blocks.py`, `uv run scripts/check_links.py` | OK; no `#` comments in 688 shell blocks; 3,667 links and anchors OK |
| `uv run scripts/validate_specs.py` (the Goal left InProgress: ac2 is the operator's) | OK: 643 files, 41 epics, 580 tasks, 22 releases |

## Files changed

* **`prompts/`**: `landscape/classify_position@1.3.1.md` (new, released), and its entry in
  `prompts.lock.json`.
* **`debate_core.application.landscape_model_stage`**: `CLASSIFY_POSITION_VERSION` is 1.3.1, and its
  docstring.
* **Tests:**
  * new: `packages/debate_core/tests/arguments/landscape/test_prompt_without_the_generic_confidence_sentence.py`;
  * `packages/debate_core/tests/application/test_coach_sample_stance.py`: the 1.3.1 default, 1.3.0 by
    name, and the two recording tests;
  * the version pins in `packages/debate_cli/tests/test_landscape_command.py` and
    `tests/smoke/test_landscape_evaluate_smoke.py`.
* **`tests/fixtures/caselist/synthetic_archive/cassettes/`**: the one landscape cassette, rewritten
  offline by its script under 1.3.1's key.
* **Docs:**
  * [the evaluation's record](../data/landscape-model-evaluation.md#prompt-131-130-less-the-generic-confidence-sentence-v1-e32-t55-2026-11-06):
    what 1.3.1 is and why, and where the PM records the re-record;
  * [the record runbook](../runbooks/landscape-model-evaluation-record.md#prompt-131-the-re-record-on-deep_audit-v1-e32-t55):
    the block, and a line in its introduction;
  * [the replay runbook](../runbooks/landscape-model-evaluation-replay.md): which checkout replays 1.3.0.

## Deviations from the spec

1. **The affected set** (293 files) was stopped at 115 seconds and is left to the pull request's `ci`
   (agreement 10). The changed test directories and the always-run list ran instead (2,876 passed).

Nothing else: every file changed is in the spec's packages, and no forbidden item was touched.

## Decisions and assumptions

1. **"Every other line is byte-identical" is held for the body; the front matter changes in exactly two
   places.** `PromptSpec` refuses a file whose changelog has no entry for its own version, and the registry
   refuses two files with the same version. So 1.3.1's `version:` line reads 1.3.1, and a changelog entry
   for it follows 1.3.0's. The diff test allows those two and the removal, and nothing else, and the
   front-matter test checks the entry is one entry for 1.3.1 with the history before it unchanged.
2. **The diff test reads raw bytes.** The registry normalizes line endings, so a test on its `body` would
   pass a CRLF line (mutant 7). The body test is kept too: it checks what the model is sent and the lock
   hashes.
3. **Where the tests live.** The file tests and the default test are in `arguments/landscape`, so the
   node's own criterion runs them. The recording tests sit beside t49's in `test_coach_sample_stance.py`,
   which holds the invented sample and the scripted router they need.
4. **1.3.1's changelog date is 2026-11-06**, the day it was written.
5. **The block's price** is read from `config/model_pricing.yaml` for Claude Sonnet 4.6, the model
   `config/model_routing.dev.yaml` routes `deep_audit` to. The tokens are 1.3.0's recorded 41,332 and 4,737,
   less 1.3.1's 215 characters in each of 3 calls (about 160 tokens at t49's 4 characters a token): about
   $0.19. The ceiling is the one 1.3.0's runbook section gives, since the guard prices it from the
   variables, which are unchanged.
6. **A landscape run asks again** about every card cached under 1.3.0, since results are cached by prompt
   version. The hold on live runs stands.

## Operator follow-ups

**ac2: the re-record of the 47 under 1.3.1 on `deep_audit`, then its breakdown.** It is also in
[the record runbook's last section](../runbooks/landscape-model-evaluation-record.md#prompt-131-the-re-record-on-deep_audit-v1-e32-t55),
with what to read. It follows v1-e32-t49's block: the same guards, the same route, the same three JSON
objects. It costs about $0.19, priced from `config/model_pricing.yaml` ($0.003 and $0.015 per 1,000 input
and output tokens for Claude Sonnet 4.6). It writes only local cassettes, beside 1.3.0's under their own
keys, and does not touch the bucket. **Expected runtime: 2 to 4 minutes.** Run it from this task's worktree
until it merges, or a checkout of `dev` after. Go to it:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t55-prompt-1-3-1-without-the-generic-confidence-sentence
```

Then the block. It refuses a set `DEBATE_` variable, a running caselist pull, a failed sample check and a
Bedrock profile that is not signed in, each before any model call:

```bash
SAMPLE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; elif ! uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --check-sample; then echo "STOP: the sample check failed; paste its JSON and record nothing"; elif ! aws sts get-caller-identity --profile debate-dev-bedrock >/dev/null; then echo "STOP: the Bedrock profile is not logged in; log in and paste again"; else uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --model-mode record --route deep_audit; uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --breakdown --route deep_audit; fi
```

Paste back **the three JSON objects**, nothing else.

* **Success:**
  * the sample check exits 0 with `labelled` 47 (`by_stance` answers 10, reads 35);
  * the recording shows `prompt_version` `1.3.1`, `route` `deep_audit`, `labelled`, `found` and `asked` 47,
    and `calls` 3 or 4;
  * the breakdown has `outcomes` summing to 47, a row per card in `breakdown.cards`, and `generic_answers`
    present.
* **Below the bar:** exit 1 `EVALUATION_BELOW_BAR` carries the counts in `error.details`. That is a result
  to record, not a failure of the block.
* **A stop before any answer:** nothing was recorded. Paste it and run nothing again before the PM reads
  it.

**Only if a `scan` count is above zero:** read the hits in the terminal, and **never paste or copy them**.
Report only each hit's number and whether it is an ordinary word:

```bash
SAMPLE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; else uv run debate-research landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --breakdown --route deep_audit; fi
```

## Follow-up work

* `test_coach_sample_stance.py`'s module docstring still calls 1.2.0 the stage's default (stale since
  t49). It is harmless and was left alone. A one-word fix for whoever next touches the file.
* As the PM ruled on t49: `v1-e32-t50`'s held-out sample is measured on 1.3.1, with rows 9 and 53 the ones
  to watch in its breakdown.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
