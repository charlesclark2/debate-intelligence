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

**The re-record came back on 2026-11-06 scored against the wrong labels file**, which had been replaced
with its 2026-11-02 copy. The recording is sound, but it has to be re-scored once the coach's stance-labelled
file is back. The repair cassettes' scan also failed on a rule gap. See
[the re-record, as returned](#the-re-record-as-the-operator-returned-it-2026-11-06) and the PM's questions.

**The PM ruled on 2026-11-06** ([the ruling](#the-pms-ruling-on-the-re-record-2026-11-06)): search for the stance-labelled
file first, then re-sit t46's stance rows if none turns up. Microsoft Excel wrote the live file at 19:15:33
(its quarantine mark, set that second). `.before-stance-relabel.csv` holds t41's review, and the relabel
script keeps no record of the coach's answers. The search, restore and re-sit blocks are written and tested
on invented files. The session stops there, as ruled.

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

## The re-record, as the operator returned it (2026-11-06)

The operator ran the block above from this worktree and pasted the three JSON objects. **It is not a
result the PM can record yet, and ac2 stays NOT RUN.** The recording is good, but it was scored against the
wrong labels file. The figures below come from the pasted JSON, and the file facts from read-only checks
of metadata and checksums (no label or card was read).

**1. The labels file is not the one 1.3.0 was scored on.**

* The sample check gave by kind advantage 14, cp 4, da 5, k 10, none 7, t 7, and by stance answers 0 and
  reads 40, with no second labels. The block's success line expected answers 10 and reads 35, as the PM
  recorded after the coach's stance sitting: advantage 15, cp 7, da 6, k 10, none 2, t 7, two second labels.
* `policy-2026-27-nhi-coach-sample-labelled.csv` was last written on 2026-11-05 at 19:15, after 1.3.0's
  re-record. It is byte for byte `policy-2026-27-nhi-coach-sample-labelled.before-relabel.csv` (SHA-256
  `cf35398e…`): the copy from 2026-11-02, before the coach's review (`v1-e32-t41`) and before the stance
  sitting (`v1-e32-t46`). No repository command writes or restores that copy. The stance-labelled file is
  not in that folder or anywhere else under the home folder by that name.
* The block did not stop on it. It stopped only on a failed sample check, and gave the expected counts in
  the prose alone. That was this session's gap. The runbook's block now refuses any other counts before a
  model call, and so does the re-score block below.
* What still holds: the rows file (`policy-2026-27-nhi-coach-sample.jsonl`) is unchanged since 2026-10-25,
  so the same 47 cards were sent. The model is never sent a label, so the 5 new cassettes are a sound 1.3.1
  recording. Re-scoring is a replay with no model call, once the right file is back.

**2. The repair cassettes' scan was not clean, and the reason is the scan rule.**

* Two of the three batches were repaired, each for `string_too_long` (a rationale over 280 characters), so
  there were 5 calls. 1.3.0's recording had none.
* Prompt inputs: clean, 0 hits. Cassettes: 50 hits (44 a JSON key's name, 6 taxonomy words), all 3 texts
  set aside, clean.
* Repair cassettes: 63 hits (repaired prompt 45, model rationale 17, cassette metadata 1). Every one carries
  a trusted mark (53 a JSON key's name, 10 a taxonomy word), and none is a team's name. But every one also
  carries `in_input`, which `MARKS_THAT_KEEP_A_HIT` keeps whatever else a hit carries. So neither text is
  set aside and `clean` is false.
* Why every hit is `in_input`: a repair cassette's input is the failed call, and that includes the model's own
  failed answer. So each word of its rationales is "in the input", although the mark is meant for words the
  cards sent. t44's marks were ruled on the kept 1.1.0 recordings, which had no repairs, so this is the first
  repaired recording they meet. It is the PM's rule, and this session did not change it (question 2 below).
* The scan's hits have not yet been judged in the terminal.

**What the pasted figures say, for the record only (scored against the 2026-11-02 labels):**

* Pipeline 22 of 38 (0.579, bar 0.85), below the threshold 9, placed though labelled none 6, coverage
  0.809, weighted 0.481. These are not comparable with 1.3.0's 24 of 32, which was scored against the stance
  labels.
* Tokens: 43,165 input and 5,235 output over the 5 calls, which is **$0.208** at `config/model_pricing.yaml`'s
  $0.003 and $0.015 per 1,000 (estimated about $0.19 before the two repairs).

**Answers that do not depend on the labels** (the model's answer, stance and confidence, against 1.3.0's in
v1-e32-t49's report):

* Row 26 is now `kritikal-aff`, reads, 0.72. Under 1.3.0 it was `at:generic-k` at 0.62, the wrong generic
  answer that removed the sentence.
* The answers naming a generic position: 4 (rows 16, 37, 50 and 60), 1 above the threshold (row 60,
  `generic-k`, 0.62). In both label files row 60 is labelled `generic-k`, and it is not one of the stance
  file's `at:` rows, so on the right labels it should count right. The replay will say.
* Rows 12 and 55 are still `cap-k`, reads (0.82 and 0.72).
* Row 53 is `single-payer-t` at 0.72, above the threshold again (0.55 under 1.3.0). Row 9 is `rates-da` at
  0.55, still below.

### For the PM (a relay)

```text
v1-e32-t55: the operator's 1.3.1 re-record on deep_audit came back, but it cannot be recorded yet.

1. The labels file. On 2026-11-05 at 19:15 (after 1.3.0's re-record) the live
   policy-2026-27-nhi-coach-sample-labelled.csv became byte for byte the .before-relabel.csv copy of
   2026-11-02: no t41 review, no t46 stance sitting (sample check: none 7, answers 0, reads 40, no
   second labels; expected none 2, answers 10, reads 35, two second labels). The stance-labelled file is not
   on disk under that name. The 1.3.1 recording is sound (same 47 cards; the model never sees labels), so it
   needs re-scoring, not re-recording.
   Options:
   (A) The operator restores the stance-labelled file from a backup, and runs the re-score block (no model
       call, about a minute; it refuses any other counts).
   (B) Re-sit the stance rows with the coach from .before-stance-relabel.csv, through
       scripts/relabel_coach_sample.py as in t46.
   (C) Rebuild the file by hand from the recorded sittings. Not recommended: that changes the coach's
       labels outside a sitting.
   Recommendation: (A), and (B) if no backup has it. Why: the labels are the coach's, and only a copy
   of his own file or his own sitting keeps them his.

2. The repair cassettes' scan. Two batches were repaired (string_too_long), and the repair cassettes'
   63 hits each carry a trusted mark (53 JSON key, 10 taxonomy word, 0 a team's name). But all 63 are
   also in_input, which keeps a hit, because a repair cassette's input includes the model's own failed
   answer. So clean is false, a first since t44's marks (the 1.1.0 recordings had no repairs).
   Options:
   (A) A follow-up that marks a repair cassette's hit in_input only when its words come from the cards
       the failed call sent, not from the failed answer.
   (B) Keep the rule, and the operator judges each repaired recording's hits in the terminal.
   Recommendation: (A), filed under E32, with (B) for this recording in the meantime. Why: in_input exists
   to keep copied card text, and here it keeps the model's own words.

3. For the record: 43,165 input and 5,235 output tokens in 5 calls, $0.208 at config/model_pricing.yaml.
   On the wrong labels, pipeline 22 of 38, not comparable with 1.3.0's 24 of 32. Answers, whatever
   the labels: row 26 left at:generic-k (now kritikal-aff, 0.72); 1 generic answer above the threshold
   (row 60, generic-k, 0.62, labelled generic-k in both files); rows 12 and 55 still cap-k; row 53
   above the threshold again.
   The Goal stays InProgress, ac2 NOT RUN.
```

### The blocks, once the labels file is back

Go to the worktree:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t55-prompt-1-3-1-without-the-generic-confidence-sentence
```

The re-score: it replays the 1.3.1 recording with no model call, and stops unless the labels show the stance
sitting's counts. Expected runtime: about a minute. Paste back the two JSON objects, nothing else. Success
is the sample check with by stance answers 10 and reads 35, and the breakdown with `prompt_version` `1.3.1`,
`calls` 5 and `outcomes` summing to 47.

```bash
SAMPLE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; elif ! CHECK=$(uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --check-sample); then echo "$CHECK"; echo "STOP: the sample check failed; paste its JSON and record nothing"; elif ! printf '%s\n' "$CHECK" | grep -qF '"by_label_kind": {"advantage": 15, "cp": 7, "da": 6, "k": 10, "none": 2, "t": 7}' || ! printf '%s\n' "$CHECK" | grep -qF '"by_stance": {"answers": 10, "reads": 35}'; then echo "$CHECK"; echo "STOP: these are not the labels 1.3.0 was scored on; paste this JSON and nothing else"; else echo "$CHECK"; uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --breakdown --route deep_audit; fi
```

The scan's hits, label-independent, to read in the terminal only. **Never paste or copy its output.**
Report only each hit's number and whether it is an ordinary word:

```bash
SAMPLE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; else uv run debate-research landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --breakdown --route deep_audit; fi
```

## The PM's ruling on the re-record (2026-11-06)

1. **The labels file: (A), searched for properly first, then (B) if no copy turns up. Never (C).** 1.3.0's
   24 of 32 stands, because it was scored before 19:15.
2. **The repair cassettes' scan: (A) as a follow-up (E32, p3), and (B) for this recording.** The operator reads
   the 63 hits in the terminal. They report only whether each is an ordinary word, a JSON key or a taxonomy
   word, and whether any names a team.
3. **Recorded as given:** 5 calls, 43,165 input and 5,235 output tokens, $0.208 at `config/model_pricing.yaml`.
   The answers that do not depend on the labels are in [the section above](#the-re-record-as-the-operator-returned-it-2026-11-06).
   The score waits for 1.

ac2 stays NOT RUN until the re-score runs on the coach's labels.

### What wrote the live labels file at 19:15 on 2026-11-05: Microsoft Excel

Found from the file system's metadata only: inode numbers, times and extended attributes, read with `stat`
and `xattr`. No row, tag or label was read.

* **The live file's inode was born at 22:51:26 on 2026-11-04.** That is the stance sitting's own write:
  `relabel_coach_sample.py` writes `.<name>.incoming` and moves it into place with `os.replace`, so each
  sitting gives the file a new inode. At **19:15:33 on 2026-11-05 that same inode was written again**, with
  the bytes of `.before-relabel.csv`.
* **The writer was Microsoft Excel.** The live file carries a `com.apple.quarantine` mark whose agent is
  `Microsoft Excel`. Its timestamp field decodes to **2026-11-05 19:15:33 CST, the same second as the write**.
  macOS puts that mark on a file a sandboxed app like Excel saves. Excel's own preferences folder
  (`~/Library/Containers/com.microsoft.Excel/Data/Library/Preferences`) was also modified at 19:15.
  * Excel's save keeps the file's identity, which fits the inode surviving.
  * Neither backup copy names an agent: `.before-stance-relabel.csv` carries a mark without one (set when
    the sitting copied the file at 22:44:37 on 2026-11-04), and `.before-relabel.csv` has no mark at all.
* **Not a script.** The relabel script always makes a new inode, and refuses to start when its
  `.before-stance-relabel.csv` copy differs from the sample. No script, runbook block or test in the
  repository, on any branch, names `.before-relabel.csv`; only this report does. `cp -p` is ruled out too,
  as it would have kept the copy's 2026-11-02 time. So by the ruling (1b) no script fix is filed.
* **What Excel had open** (the Nov 2 copy opened and saved under the live name, or a window left open since
  before t41's review) is the operator's to say. **Excel is running on this Mac now:** the restore and
  sitting blocks below refuse to run while it is.

### Whether `.before-stance-relabel.csv` holds t41's review: yes

The session ran the sample check on both backup copies, from this worktree. It is read-only, took about a
second each, printed counts only, and made no model call:

| Copy | Size, modified | By kind | By stance | Second labels |
|---|---|---|---|---|
| `.before-stance-relabel.csv` | 7,891 bytes, 2026-11-02 17:09:21 | advantage 16, cp 6, da 5, k 10, none 3, t 7 | answers 0, reads 44 | 2 |
| `.before-relabel.csv` (= the live file now) | 7,725 bytes, 2026-11-02 00:00:22 | advantage 14, cp 4, da 5, k 10, none 7, t 7 | answers 0, reads 40 | 0 |

The first row is t41's relabel exactly as the PM recorded it in docs/data: advantage 16, cp 6, da 5, k 10,
none 3, t 7, two second labels, both advantages. So if no stance-labelled copy is found, **the coach
re-sits only t46's stance rows**, from that copy.

### Whether `relabel_coach_sample.py` keeps a record of the coach's answers: no

The sitting holds the changed labels in memory and writes them into the CSV once, at the end
(`relabelled_sample`, then `os.replace`). Before that it keeps only the copy of the CSV it started from.
It logs nothing, and its last line is counts only ("Nothing is logged or written but the coach's labels", in
its docstring). So the only record of the coach's stance decisions was the file Excel overwrote. There is no
record to replay, and rebuilding the labels from the counts and row numbers in docs/data would be (C).

### The blocks, in order

Go to the worktree first:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t55-prompt-1-3-1-without-the-generic-confidence-sentence
```

**Before anything, while Excel is still open:** look at Excel's open windows. If one holds the labels
file, close it with **Don't Save**. Then list what Excel keeps in its own folder. This is an exception to
the ruling's "~/Library excluded", proposed because Excel wrote the file: its AutoRecovery copies live
there, and quitting can clear them. It prints paths, sizes and times only, in seconds:

```bash
if [ -d "$HOME/Library/Containers/com.microsoft.Excel" ]; then find "$HOME/Library/Containers/com.microsoft.Excel" -type f \( -iname '*coach-sample*' -o -iname '*autorecover*' \) -exec stat -f '%N  %z bytes  modified %Sm' -t '%Y-%m-%d %H:%M:%S' {} + 2>/dev/null; echo "--- Done"; else echo "Excel keeps no folder here"; fi
```

Then quit Excel (Don't Save if asked).

**1a and 1b: the search, read-only.** It looks by name for anything with `coach-sample` in its name under
the home folder, `/tmp` and `TMPDIR`. The Trash, every worktree, `~/.claude` and the session scratch folders
under `/tmp` are all covered; `~/Library` is left out. It also looks by content, for any other CSV whose
header has `sample_row` and `position`, leaving out `tests/`, `fixtures/` and `node_modules`.
* For each candidate it prints its path, size, modification time and the sample check's counts: none,
  answers, reads, second labels. Nothing else.
* It then lists Time Machine's destination, its local snapshots and its last backups (read-only), and the
  shell history lines naming the labels file or its folder, with their times.
* Expected runtime: 2 to 4 minutes. Two passes over the home folder take about a minute each, and each
  candidate about a second.

```bash
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
small=0
counts() { uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$1" --sample-rows "$ROWS" --check-sample 2>/dev/null | python3 -c 'import sys,json; lines=[l for l in sys.stdin.read().splitlines() if l.startswith("{")]; d=json.loads(lines[-1]) if lines else {}; x=d.get("data") or {}; s=x.get("by_stance") or {}; print("    check:", d.get("status", "no JSON"), (d.get("error") or {}).get("code") or "", "| none", (x.get("by_label_kind") or {}).get("none"), "| answers", s.get("answers"), "| reads", s.get("reads"), "| second labels", (x.get("second_labels") or {}).get("rows"))'; }
candidate() { if [ "$(stat -f %z "$1")" -lt 1000 ]; then small=$((small + 1)); return; fi; stat -f '%N  %z bytes  modified %Sm' -t '%Y-%m-%d %H:%M:%S' "$1"; case "$1" in *.csv) counts "$1" ;; *) echo "    check: not a CSV" ;; esac; }
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else
echo "--- Excel's own folder"
if [ -d "$HOME/Library/Containers/com.microsoft.Excel" ]; then find "$HOME/Library/Containers/com.microsoft.Excel" -type f \( -iname '*coach-sample*' -o -iname '*autorecover*' \) -exec stat -f '%N  %z bytes  modified %Sm' -t '%Y-%m-%d %H:%M:%S' {} + 2>/dev/null; else echo "    Excel keeps no folder here"; fi
echo "--- By name: home folder (Trash, worktrees, ~/.claude included; ~/Library left out), /tmp, TMPDIR"
ls "$HOME/.Trash" >/dev/null 2>&1 || echo "    the Trash is not readable from this terminal: look in it in Finder for a name with coach-sample"
{ find "$HOME" -path "$HOME/Library" -prune -o -type f -iname '*coach-sample*' -print0 2>/dev/null; find /private/tmp "${TMPDIR:-/private/tmp}" -type f -iname '*coach-sample*' -print0 2>/dev/null; } | while IFS= read -r -d '' f; do candidate "$f"; done
echo "--- By content: other CSVs whose header has sample_row and position (tests, fixtures and node_modules left out)"
{ find "$HOME" -path "$HOME/Library" -prune -o -type f -iname '*.csv' -not -iname '*coach-sample*' -not -path '*/tests/*' -not -path '*/fixtures/*' -not -path '*/node_modules/*' -print0 2>/dev/null; find /private/tmp "${TMPDIR:-/private/tmp}" -type f -iname '*.csv' -not -iname '*coach-sample*' -print0 2>/dev/null; } | while IFS= read -r -d '' f; do head -1 "$f" 2>/dev/null | grep -q 'sample_row' && head -1 "$f" | grep -q 'position' && candidate "$f"; done
echo "    files under 1,000 bytes left out (test fixtures; the labels file is about 7,700): $small"
echo "--- Time Machine"
tmutil destinationinfo 2>&1 | grep -E '^(Name|Kind)' || echo "    no destination set up"
tmutil listlocalsnapshots / 2>&1
tmutil listbackups 2>&1 | tail -5
echo "--- Shell history lines naming the labels file or its folder, from 2026-11-04 on"
for h in ~/.zsh_history ~/.bash_history; do [ -f "$h" ] && python3 -c 'import sys,re,datetime; since=datetime.datetime(2026,11,4).timestamp(); hits=[l for l in open(sys.argv[1], encoding="utf-8", errors="replace").read().splitlines() if "coach-sample" in l or "landscape-review" in l]; stamp=lambda l: re.match(r": (\d+):\d+;", l); new=[l for l in hits if stamp(l) and int(stamp(l).group(1)) >= since]; [print("   ", datetime.datetime.fromtimestamp(int(stamp(l).group(1))).strftime("%Y-%m-%d %H:%M:%S"), re.sub(r"^: \d+:\d+;", "", l)[:200]) for l in new]; print("    in", sys.argv[1], len(hits), "lines in all,", len(new), "from 2026-11-04 on")' "$h"; done
echo "--- Done"
fi
```

**The first run of this block (2026-11-06) was too loud.** It listed every pytest fixture under `TMPDIR`, each
32 to 535 bytes. Pasted, that output passed 50,000 characters and was cut at both ends, so its home-folder,
Time Machine and history sections never arrived. Every candidate in the part that did arrive was one of
those fixtures, and none read the stance counts. The block above replaces it. It lists only files of 1,000
bytes or more and counts the rest (the labels file is about 7,700 bytes). It prints history only from
2026-11-04 on, with a count of the earlier lines, and it now includes the Excel-folder listing.

Paste back its whole output. It holds paths, sizes, times, counts and command lines, no row or label text.

**What the search found (the operator's second run, 2026-11-06):**

* **No copy reads the stance counts.** The labels files found are the three in `landscape-review`:
  * the live file: none 7, answers 0, reads 40, no second labels;
  * `.before-relabel.csv`: the same;
  * `.before-stance-relabel.csv`: none 3, answers 0, reads 44, two second labels (t41's review).
* **The other candidates are not this sample's labels:**
  * the cite-shape sample `coach-sample-20261031` under `parser-eval/` (refused, not this sample);
  * the unlabelled `policy-2026-27-nhi-coach-sample.csv` (refused) and its rows file;
  * copies of t41's report and spec in worktrees and old build folders;
  * the session's own invented test files in its scratch folder.
  * 386 files under 1,000 bytes were left out.
* **Excel's own folder:** AutoRecovery copies of other workbooks and of `coach-sample-20261031` (2026-10-31),
  none of this labels file.
* **Time Machine:** no destination set up, and no local snapshots of `/`.
* **Shell history:** 10 lines name the file or its folder, none from 2026-11-04 on. That fits Excel's own
  save, not a shell command.
* **The Trash** is not readable from the terminal, so the operator looks in it in Finder.

**1d's set-up, run by the operator (2026-11-06).** The Trash was empty in Finder, and Excel was quit first.
* The block printed `Restored.` and a sample check of advantage 16, cp 6, da 5, k 10, none 3, t 7; answers 0,
  reads 44; two second labels (both advantages).
* The session confirmed by checksum only:
  * the live file is now byte for byte `.before-stance-relabel.csv` (t41's review);
  * `.regressed-2026-11-05.csv` is byte for byte the file Excel wrote, which is `.before-relabel.csv`;
  * no `.incoming` file is left in the folder.
* Next is the coach's sitting.

* **The stance-labelled file is a candidate reading `none 2 | answers 10 | reads 35 | second labels 2`.**
  If one does, go to 1c.
* **If none does**, but Time Machine lists a local snapshot or a backup between 2026-11-04 22:51 and
  2026-11-05 19:15, stop and paste it: the copy is inside it, and taking it out is the next ruling's step.
* **Otherwise**, go to 1d.

**1c: if a copy reads the stance counts.** First the check, read-only: it confirms that copy's counts again
and that nothing is in the way. Set `FOUND` on its first line to the path the search printed, in the
single quotes:

```bash
FOUND='paste here the path the search printed'
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
LIVE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
REGRESSED=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.regressed-2026-11-05.csv
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; elif [ ! -f "$FOUND" ]; then echo "STOP: FOUND is not a file; set it to the path the search printed"; elif [ "$FOUND" -ef "$LIVE" ]; then echo "STOP: FOUND is the live file itself"; elif [ -e "$REGRESSED" ]; then echo "STOP: the .regressed copy already exists; paste this line only"; elif ! CHECK=$(uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$FOUND" --sample-rows "$ROWS" --check-sample 2>/dev/null); then echo "STOP: the sample check failed on that copy; nothing was changed"; elif ! printf '%s\n' "$CHECK" | grep -qF '"by_label_kind": {"advantage": 15, "cp": 7, "da": 6, "k": 10, "none": 2, "t": 7}' || ! printf '%s\n' "$CHECK" | grep -qF '"by_stance": {"answers": 10, "reads": 35}' || ! printf '%s\n' "$CHECK" | grep -qF '"second_labels": {"rows": 2,'; then echo "STOP: that copy is not the stance-labelled file; nothing was changed"; else echo "OK: the stance-labelled file. It can be restored with the next block."; fi
```

Only after `OK:`, the restore. It refuses while Excel runs. It keeps the current file beside it as
`policy-2026-27-nhi-coach-sample-labelled.regressed-2026-11-05.csv` and checks that copy byte for byte, then
copies `FOUND` into place, checks that byte for byte too, and runs the sample check. Set `FOUND` as before:

```bash
FOUND='paste here the path the search printed'
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
LIVE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
REGRESSED=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.regressed-2026-11-05.csv
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; elif pgrep -x "Microsoft Excel" >/dev/null; then echo "STOP: Microsoft Excel is running; quit it first, so it cannot save over the labels file again"; elif [ ! -f "$FOUND" ]; then echo "STOP: FOUND is not a file; set it to the path the search printed"; elif [ "$FOUND" -ef "$LIVE" ]; then echo "STOP: FOUND is the live file itself"; elif [ -e "$REGRESSED" ]; then echo "STOP: the .regressed copy already exists; paste this line only"; elif ! CHECK=$(uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$FOUND" --sample-rows "$ROWS" --check-sample 2>/dev/null); then echo "STOP: the sample check failed on that copy; nothing was changed"; elif ! printf '%s\n' "$CHECK" | grep -qF '"by_label_kind": {"advantage": 15, "cp": 7, "da": 6, "k": 10, "none": 2, "t": 7}' || ! printf '%s\n' "$CHECK" | grep -qF '"by_stance": {"answers": 10, "reads": 35}' || ! printf '%s\n' "$CHECK" | grep -qF '"second_labels": {"rows": 2,'; then echo "STOP: that copy is not the stance-labelled file; nothing was changed"; elif ! cp -p "$LIVE" "$REGRESSED" || ! cmp -s "$LIVE" "$REGRESSED"; then echo "STOP: the copy of the current file did not match; nothing was replaced"; elif ! cp "$FOUND" "$LIVE" || ! cmp -s "$FOUND" "$LIVE"; then echo "STOP: the restore did not match; the current file is kept at the .regressed path"; else echo "Restored."; uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$LIVE" --sample-rows "$ROWS" --check-sample; fi
```

Success: `Restored.`, then a sample check with none 2, answers 10, reads 35 and two second labels. Then
run the re-score, which makes no model call (about a minute). Paste back its two JSON objects only:

```bash
SAMPLE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; elif ! CHECK=$(uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --check-sample); then echo "$CHECK"; echo "STOP: the sample check failed; paste its JSON and record nothing"; elif ! printf '%s\n' "$CHECK" | grep -qF '"by_label_kind": {"advantage": 15, "cp": 7, "da": 6, "k": 10, "none": 2, "t": 7}' || ! printf '%s\n' "$CHECK" | grep -qF '"by_stance": {"answers": 10, "reads": 35}'; then echo "$CHECK"; echo "STOP: these are not the labels 1.3.0 was scored on; paste this JSON and nothing else"; else echo "$CHECK"; uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --breakdown --route deep_audit; fi
```

**1d: if no copy turns up.** First the set-up. It puts t41's review back in place from
`.before-stance-relabel.csv`, keeping the current file as `.regressed-2026-11-05.csv`, checked the same way.
It refuses unless that copy reads t41's counts:

```bash
FOUND=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.before-stance-relabel.csv
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
LIVE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
REGRESSED=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.regressed-2026-11-05.csv
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; elif pgrep -x "Microsoft Excel" >/dev/null; then echo "STOP: Microsoft Excel is running; quit it first, so it cannot save over the labels file again"; elif [ ! -f "$FOUND" ]; then echo "STOP: FOUND is not a file; set it to the path the search printed"; elif [ "$FOUND" -ef "$LIVE" ]; then echo "STOP: FOUND is the live file itself"; elif [ -e "$REGRESSED" ]; then echo "STOP: the .regressed copy already exists; paste this line only"; elif ! CHECK=$(uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$FOUND" --sample-rows "$ROWS" --check-sample 2>/dev/null); then echo "STOP: the sample check failed on that copy; nothing was changed"; elif ! printf '%s\n' "$CHECK" | grep -qF '"by_label_kind": {"advantage": 16, "cp": 6, "da": 5, "k": 10, "none": 3, "t": 7}' || ! printf '%s\n' "$CHECK" | grep -qF '"by_stance": {"answers": 0, "reads": 44}' || ! printf '%s\n' "$CHECK" | grep -qF '"second_labels": {"rows": 2,'; then echo "STOP: that copy does not hold t41's review; nothing was changed"; elif ! cp -p "$LIVE" "$REGRESSED" || ! cmp -s "$LIVE" "$REGRESSED"; then echo "STOP: the copy of the current file did not match; nothing was replaced"; elif ! cp "$FOUND" "$LIVE" || ! cmp -s "$FOUND" "$LIVE"; then echo "STOP: the restore did not match; the current file is kept at the .regressed path"; else echo "Restored."; uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$LIVE" --sample-rows "$ROWS" --check-sample; fi
```

Success: `Restored.`, then a sample check with none 3, answers 0, reads 44 and two second labels. Then
**the coach's sitting**, with the coach at the terminal. It uses the rows and seed the PM ruled for t46's
(2026-11-05): the 13 listed rows and 6 controls drawn by the seed 20261105, so the coach sees the same 19
cards in the same order he saw on 2026-11-04. It refuses unless the labels file reads t41's counts, and
while Excel runs. The relabel script's own copy check passes, because its `.before-stance-relabel.csv`
copy is then the sample itself:

```bash
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
LIVE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
REGRESSED=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.regressed-2026-11-05.csv
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; elif pgrep -x "Microsoft Excel" >/dev/null; then echo "STOP: Microsoft Excel is running; quit it first, so it cannot save over the labels file again"; elif ! CHECK=$(uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$LIVE" --sample-rows "$ROWS" --check-sample 2>/dev/null); then echo "STOP: the sample check failed; run nothing more"; elif ! printf '%s\n' "$CHECK" | grep -qF '"by_label_kind": {"advantage": 16, "cp": 6, "da": 5, "k": 10, "none": 3, "t": 7}' || ! printf '%s\n' "$CHECK" | grep -qF '"by_stance": {"answers": 0, "reads": 44}' || ! printf '%s\n' "$CHECK" | grep -qF '"second_labels": {"rows": 2,'; then echo "STOP: the labels file is not t41's review; run the set-up block first"; elif ! uv run python scripts/relabel_coach_sample.py --caselist hspolicy26 --snapshot 2026-10-20 --sample "$LIVE" --sample-rows "$ROWS" --rows 5,11,13,16,20,21,25,26,31,33,41,57,59 --seed 20261105; then echo "STOP: the sitting stopped; paste its last line only"; else uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$LIVE" --sample-rows "$ROWS" --check-sample; fi
```

Paste back the sitting's last line (counts only) and the JSON object. Then run the re-score above.
* Its guard expects the sitting's 2026-11-05 counts (none 2, answers 10, reads 35). If the coach decides any
  row differently this time, it stops with the new counts. That is the coach's decision, and it goes to the
  PM before anything is scored.

**2(B): the scan's hits, any time.** They do not depend on the labels. Read them in the terminal only and
never paste or copy them. For each of the 63 repair-cassette hits, report only whether it is an ordinary
word, a JSON key or a taxonomy word, and whether any names a team:

```bash
SAMPLE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; else uv run debate-research landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --breakdown --route deep_audit; fi
```

## The coach's sitting of 2026-11-06 (1d)

The coach re-sat t46's stance rows through `relabel_coach_sample.py`, from t41's review. It used the same 13
listed rows, 6 controls and seed 20261105 as on 2026-11-04, so the same 19 cards came in the same order.
The operator pasted the sitting's last line and the sample check:

* `Done. Listed: 9 changed, 4 unchanged. Control: 1 changed, 5 unchanged.` These are the same numbers of
  changes as on 2026-11-04.
* The sample check: labelled 47; by kind advantage 16, aff 1, cp 7, da 5, k 9, none 2, t 7; by stance
  answers 9, reads 36; two second labels, both advantages. The 2026-11-04 sitting had given advantage
  15, cp 7, da 6, k 10, none 2, t 7, and answers 10, reads 35.
* The file: written by the script (a new inode, 294172968, at 2026-11-06 23:05:46, and no Excel mark), 7,929
  bytes, SHA-256 `553374704519fd29f13a43e279a08537b28c87fbfc58372be845bc0de2b0a922`. t41's copy beside it is
  unchanged.

**Where the two sittings differ.** The session compared today's labels with t41's copy, reading only the
row number and label columns (taxonomy ids), and the `at:` rows with docs/data's record of 2026-11-04. The
2026-11-04 labels themselves are gone with the overwritten file, so only which rows took `at:` can be
compared:

| Row | 2026-11-04 | 2026-11-06 |
|---|---|---|
| 5, 11, 20, 26, 31, 41, 59 (listed) | changed to `at:` | changed to `at:`, the same rows |
| 40 (control) | changed to `at:` | changed: `none` to `at:delay-cp` |
| 21 (listed) | changed to `at:` | kept (t41's label, reads) |
| 25 (listed) | changed to `at:` | kept (t41's label, reads) |
| 16 (listed) | kept | `inequality-advantage` to `at:inequality-advantage` |
| 57 (listed) | kept (`cap-k`) | `cap-k` to `kritikal-aff` |
| 13, 33 (listed) | kept | kept |

* 4 of the 19 cards came out differently between the two sittings.
* Rows 16 and 57 are two of the three rows the PM's ruling 3 on t49 sends to the coach alongside
  `v1-e32-t50` (16, 33 and 57). Today the coach gave row 16 an `at:` label, and row 57 `kritikal-aff`, the
  position that reads a kritik's theory on the affirmative: the possibility that ruling named. Row 33 he kept.
* The re-score's guard expects the 2026-11-04 counts, so it refuses this file, as written, until the PM
  rules.

### For the PM (a relay)

```text
v1-e32-t55: the coach re-sat t46's stance rows (1d), from t41's review, on the same 19 cards, order
and seed as 2026-11-04. No stance-labelled copy was found anywhere (search, Excel's folder, the
Trash, Time Machine: none set up), and Microsoft Excel wrote the bad file (quarantine mark at the
second of the write).

Result: the same numbers of changes (listed 9, control 1), but not the same labels.
  2026-11-04: by kind advantage 15, cp 7, da 6, k 10, none 2, t 7; answers 10, reads 35; 2 second labels.
  2026-11-06: by kind advantage 16, aff 1, cp 7, da 5, k 9, none 2, t 7; answers 9, reads 36; 2 second labels.
Row by row (only the at: rows of 2026-11-04 are on record):
  rows 21 and 25 took at: on 11-04 and were kept today;
  row 16 was kept on 11-04 and is at:inequality-advantage today;
  row 57 was kept on 11-04 (cap-k) and is kritikal-aff today;
  the other 7 listed changes and the control (row 40, now at:delay-cp) agree.
So 4 of 19 cards differ between the coach's two sittings. Rows 16 and 57 are two of your ruling 3
rows on t49 (16, 33, 57).

Question: which labels does 1.3.1 get scored on?
  (A) Today's file, the coach's current decisions. To compare like with like, also replay 1.3.0's kept
      cassettes on today's labels (read-only, from a checkout before t55's merge, no model call,
      about a minute). 1.3.0's 24 of 32 stays on record as scored on the 11-04 labels.
  (B) First a short sitting on rows 16, 21, 25 and 57 alone, the coach choosing between his two
      answers (shown unmarked, without saying which sitting gave which), then (A) on that file.
  (C) Score today's file against 1.3.0's 24 of 32 as is. Not recommended: that mixes a prompt
      change with a label change.
Recommendation: (A). Why: today's file is a complete sitting, made the way the 11-04 one was, and the
like-for-like replay keeps the prompt comparison clean. (B) asks the coach to referee himself, with
nothing new to show him. The 4-in-19 disagreement is worth recording either way: it is the first
measure of how far the coach's own stance labels hold between sittings.
On rows 16 and 57 under ruling 3: today's labels may be taken as the coach's answer for those two
(an at: label for 16, kritikal-aff for 57). Row 33 is still open.

The re-score block's guard expects the 11-04 counts and refuses today's file. Once you rule, I give
the operator a block guarded on the counts you choose. The scan hits (2(B)) do not depend on the
labels and can be judged now. ac2 stays NOT RUN; the Goal stays InProgress.
```

### The scan's hits (2(B)), in progress

The operator ran the hit-listing block on 2026-11-06 and pasted only its closing `EVALUATION_BELOW_BAR`
panel: counts, taxonomy ids and row numbers, no hit text. The hit listing prints above that panel,
numbered across the three scans in order: prompt inputs 0, cassettes 1 to 50, repair cassettes 51 to 113.
Each line shows its marks: a team's name, a taxonomy word, a JSON key, in the cards sent. The operator
judges hits 51 to 113 in the terminal and reports only the verdicts.

That replay also scores the 1.3.1 recording on today's labels. The session has not recorded those figures
and has kept them out of the relay above, so that the PM chooses which labels to score on before seeing
which choice scores better. They are recorded once the PM rules.

## Follow-up work

* `test_coach_sample_stance.py`'s module docstring still calls 1.2.0 the stage's default (stale since
  t49). It is harmless and was left alone. A one-word fix for whoever next touches the file.
* **E32, p3, as ruled (2(A)):** a repair cassette's hit counts as `in_input` only when its words come from the
  cards the failed call sent, not from the model's own failed answer (`scan_hits.repair_cassette_hits`).
* **The labels file: no script follow-up (1b).** Excel wrote it, not a script. A suggestion for the PM, not
  filed: `--check-sample` could print the labels file's SHA-256, and each sitting record the one it wrote, so
  a block refuses a file no sitting wrote. The coach's guide could also say the labels CSV is written only
  by a sitting, never saved from Excel.
* As the PM ruled on t49: `v1-e32-t50`'s held-out sample is measured on 1.3.1, with rows 9 and 53 the ones
  to watch in its breakdown.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
