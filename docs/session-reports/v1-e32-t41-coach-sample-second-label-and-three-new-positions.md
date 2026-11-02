# Session report: v1-e32-t41-coach-sample-second-label-and-three-new-positions

| | |
|---|---|
| Task | `v1-e32-t41-coach-sample-second-label-and-three-new-positions` — The coach's review applied: three new NHI positions, corrected descriptions, and a second accepted label in the coach sample |
| Spec | [`plan_specs/v1/e32-argument-landscape/t41-coach-sample-second-label-and-three-new-positions.yaml`](../../plan_specs/v1/e32-argument-landscape/t41-coach-sample-second-label-and-three-new-positions.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t41-coach-sample-second-label-and-three-new-positions` |
| Session status | COMPLETE (Goal left InProgress: ac3 is the operator's) <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The coach's review of `v1-e32-t40` is applied. `policy-2026-27-nhi` moves to 1.5.0 (minor: new
positions) with `health-profiteering-advantage`, `free-market-cp` and `federalism-cp`, whose aliases were
chosen from counts on the dev store taken first, and six corrected descriptions; `generic` moves to 1.1.2
(patch) with the other three. All nine read word for word as the spec gives them. The coach sample takes
an optional `also` column: an answer naming either label is correct, both labels are validated, the
breakdown counts the cards right on their second label, and the confusion table and label kinds stay on
the first. A sample without the column scores exactly as before, proved on t39's synthetic fixtures. For
the operator's check, `landscape evaluate --check-sample` reads the sample and counts it by label kind,
with no card read and no model asked. A `--breakdown` replay would stop at `MISSING_FIXTURE_ERROR`, because
1.5.0 changes the prompt's positions text. **The Goal stays InProgress:** ac3, the coach's relabelled sample
read without refusal, is the operator's and is recorded by the PM. The PM's three rulings of 2026-11-02
are recorded under Deviations 1 to 3 and the alias counts. **Look first** at Deviation 2: t40's
140-character cap on descriptions is now 240, because the coach's `trump-k` runs to 202.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `coach-sample-second-label-and-three-new` (Coach review applied) | Done | Alias counts first (read-only, dev store), then the taxonomy, then the second label red-first, then `--check-sample`, the smoke check and the docs. Its criterion passes (below) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the three positions exist with descriptions and aliases, the nine descriptions read as the coach corrected them, and the taxonomy validates at its new version, with the alias counts recorded first | PASS | **Counts first**, read-only on `~/.debate-research/dev` (hspolicy26 `2026.10.27-docx-7` through 2026-10-20: 3,825 sources, 126,681 cards): every heading near the new positions, then every item placed under 1.4.1 and under the proposed 1.5.0, in 40.0 s and 58.4 s ([below](#alias-counts)). **Validates:** `hard_stop.py 115 … pytest tests/config` → 81 passed at 1.5.0 / 1.1.2 (98 with the placement test). **Word for word:** a check parsing the spec's nine entries against both files → `9 of 9 word for word` (first letter compared case-insensitively, see Decisions). **Placement:** `packages/debate_core/tests/arguments/landscape/test_coach_review_positions.py` → 17 passed; red against the start commit's config (1.4.1) → 8 failed (7 heading paths unplaced and the three ids missing), the 9 "left where they are" rows passing |
| ac2: a coach sample with a second label column scores an answer naming either label correct, refuses an invalid or repeated second label, reports the second-label count in the breakdown, and scores a sample without the column exactly as before, by tests shown failing first | PASS | **Red, core:** against a skeleton with the column and API but no behaviour → 9 failed, 14 passed in `test_landscape_evaluation_breakdown.py` (each at an assertion or `DID NOT RAISE`; the two new tests passing on the skeleton are the column read and the "no column scores as t39's" guard). **Red, CLI and smoke:** the new CLI tests against the start commit's command → 9 failed (`No such option: --check-sample`, `USAGE_ERROR` ≠ `CHECK_SAMPLE_ASKS_NO_MODEL`); the smoke test → 1 failed, same cause. **Green:** core evaluation and model-stage tests 72 passed; `test_landscape_command.py -k evaluate` → 29 passed; `tests/smoke/test_landscape_evaluate_smoke.py` → 3 passed. **Mutants:** 20 of 20 caught ([below](#mutants)) |
| ac3: the coach's relabelled sample reads without refusal (operator, recorded by the PM) | NOT RUN | The coach relabels the coach's own CSV, then the operator runs the check in [Operator follow-ups](#operator-follow-ups); the PM records it. Before the relabel, the current CSV read at 1.5.0 with this branch's reader (read-only, counts only): 47 labelled, no `also` column, `advantage` 14, `cp` 4, `da` 5, `k` 10, `none` 7, `t` 7 |
| Node: coach review applied tests pass (`uv run pytest packages/debate_core/tests -k "taxonomy or coach_sample or evaluat"`) | PASS | `hard_stop.py 115 .venv/bin/python -m pytest -q packages/debate_core/tests -k "taxonomy or coach_sample or evaluat" -m "not slow and not live"` → 258 passed in 46.3 s |

### Alias counts

Counted before any edit to choose the aliases, then again with the edit to see what moves. A heading's
count is every card with it anywhere on its path; what moves is the cards it would place, since the
nearest placing heading wins and the coach's overrides are read before any alias. Each alias below is a
heading two or more teams use (the guide's rule).

| Position | Alias | Teams | Documents | Cards under it | Placed today |
|---|---|---|---|---|---|
| `health-profiteering-advantage` | `health profiteering` | 13 | 43 | 512 | 494 none, 11 `medicare-for-all-aff`, 5 `doctors-da`, 2 `global-budgets-aff` |
| | `healthcare profiteering advantage` | 7 | 24 | 431 | 290 none, 113 `single-payer-aff`, 22 `medicare-for-all-aff`, 6 `global-budgets-aff` |
| | `healthcare profiteering` | 6 | 11 | 47 | 41 none, 4 `doctors-da`, 1 `reproductive-health-aff`, 1 `medicare-for-all-aff` |
| | `adv health profiteering` | 5 | 5 | 43 | 43 none |
| | `adv healthcare profiteering` | 5 | 5 | 27 | 26 none, 1 `global-budgets-aff` |
| | `health profiteering adv` | 3 | 4 | 17 | 17 none |
| | `health profiteering advantage` | 2 | 6 | 31 | 16 `single-payer-aff`, 15 none |
| | `adv profiteering` | 2 | 2 | 21 | 21 none |
| `free-market-cp` | `free market cp` | 7 | 7 | 32 | 32 none |
| | `markets cp` | 4 | 7 | 55 | 50 none, 4 `disease-advantage`, 1 `voucher-aff` |
| | `market cp` | 3 | 3 | 25 | 12 none, 7 `midterms-da`, 3 `states-cp`, 3 `public-option-cp` |
| | `cp markets` | 2 | 5 | 34 | 33 none, 1 `value-based-reimbursement-aff` |
| `federalism-cp` | `federalism cp` | 4 | 7 | 34 | 30 none, 3 `ucf-cp`, 1 `states-cp` |
| | `cp federalism` | 2 | 2 | 28 | 28 none |

What moves, every item placed under 1.4.1 and under 1.5.0 (cards; sections beside them):

| Position | Cards it now places | From none | From another position | Sections |
|---|---|---|---|---|
| `health-profiteering-advantage` | 1,106 | 934 (65 documents, 24 teams) | 172: `single-payer-aff` 129 (9 documents, 5 teams), `medicare-for-all-aff` 34 (33, 10), `global-budgets-aff` 8, `reproductive-health-aff` 1 | 255 from none, 9 from `single-payer-aff` |
| `free-market-cp` | 114 | 112 (21 documents, 14 teams) | 2: `voucher-aff` 1, `value-based-reimbursement-aff` 1 | 70 from none |
| `federalism-cp` | 62 | 58 (7 documents, 4 teams) | 4: `ucf-cp` 3 (1 document), `states-cp` 1 (1 document, 1 team) | 27 from none, 1 from `ucf-cp`, 1 from `states-cp` |

Nothing moves from `cap-k`, `costs-advantage` or any DA. The cards under `doctors-da`, `midterms-da`,
`disease-advantage` and `public-option-cp` that carry one of these headings higher up stay where they
are. The 172 cards moving from an affirmative sit under the advantage's heading inside that aff's file,
nearer the card than the aff's own heading: that is how every other advantage is placed ("standalone
until the headings show which aff each belongs to"). The one `states-cp` card, and its section, sit
directly under a heading that is exactly `federalism cp`, in one team's file. By the coach's ruling that
the two are different mechanisms, I kept the alias. **The PM ruled on 2026-11-02 to keep the move**
(ruling 3). The count: 1 card and 1 section, in 1 document of 1 team, move from `states-cp` to
`federalism-cp`; no other `states-cp` card or section moves.

**Left out**, by kind (counts from the same pass; the placement test's "left where they are" rows hold one
of each, so an alias that took one fails it):

* For `federalism-cp`: the bare federalism heading (39 teams, 181 cards), which the coach's override of
  2026-10-24 already sends to `federalism-da`; three federalism net-benefit blocks inside the optional
  legislation CP (6, 5 and 4 teams, 62 cards, 49 placed under `optional-legislation-cp` today), one of
  which carries the words of the alias with a further word after them; the federalism-DA spillover block
  of the states CP (2 teams, 6 cards, 3 under `states-cp`); an affirmative federalism advantage (4 teams,
  42 cards); and three small turn, defense and autonomy blocks (2 teams each).
* For `free-market-cp`: the aff's markets-are-good answer to the cap K (7 teams, 24 cards), which is not
  a CP; a markets DA (2 teams, 18 cards), a markets turn read only under answers (2 teams, 21 cards) and
  markets uniqueness for the stocks and economy DAs (2 teams, 16 cards); and competition and
  competitiveness (10 and 4 teams), too broad: 13 of competition's 63 cards sit under `cap-k` or
  `taxes-pic`.
* For `health-profiteering-advantage`: the bare profiteering heading (3 teams, 15 cards, all unplaced),
  which a cap K link block could carry as easily as the advantage, so it is the coach's to add; a
  profiteering overview (2 teams, 6 cards); and private-equity and profits blocks (2 to 4 teams each),
  mostly unplaced or under the pharma DA and the costs advantage.

### Mutants

20 mutants, each a single replacement in the worktree, run against the tests that cover it
(`-p no:randomly -n 0 -x`), then restored with `git checkout HEAD --` (tree clean after). No Hypothesis
property is involved. **All 20 caught.** 19 failed at an assertion. "A sample without the column is
refused" failed on the refusal it adds, which is the behaviour under test (the sample must read).

| Mutant | Caught by | Time |
|---|---|---|
| An answer naming the second label scored wrong (outcome) | outcomes `correct` 1 ≠ 3 | 1.4 s |
| The same, in the evaluation's count | `(5, 1, 0.2)` ≠ `(5, 3, 0.6)` | 1.1 s |
| The second label not passed to the outcome | outcomes `correct` 1 ≠ 3 | 1.1 s |
| `none` accepted as a second label | refusal message, CLI and core | 1.9 s |
| `none` matched case-sensitively (`None` then refused as an unknown id instead) | `Regex pattern did not match` | 1.1 s |
| Equal labels accepted | CLI `--check-sample` exits 0 | 1.8 s |
| An inactive id accepted as a second label | CLI refusal message | 1.9 s |
| A card labelled `none` takes a second label | CLI `--check-sample` exits 0 | 1.9 s |
| A sample without the column refused | the reading test refuses (see above) | 1.1 s |
| A blank second label counts every answer correct | t39's outcomes `correct` 4 ≠ 1 | 0.9 s |
| Every correct card counted as correct on the second label | rows `{1, 2, 4}` ≠ `{2, 4}` | 1.1 s |
| Confusion table on the second label | the first-label pair missing | 1.1 s |
| Label kind from the second label | `aff` in place of `advantage` | 1.1 s |
| `--check-sample` reads the cards (calls `_prepared`) | the read is refused by the test, exit ≠ 0 | 1.7 s |
| Breakdown JSON's second-label count over the wrong cards | `{'cards': 1, …}` ≠ `{'cards': 2, …}` | 1.6 s |
| A `federalism-cp` alias taking the states CP's net-benefit heading | `federalism-cp` ≠ `states-cp` | 0.5 s |
| A `free-market-cp` alias taking the cap K's markets answer | `free-market-cp` ≠ `cap-k` | 0.5 s |
| A `health-profiteering-advantage` alias taking a costs-advantage block | ≠ `costs-advantage` | 0.6 s |
| A `federalism-cp` alias taking the optional legislation CP's net benefit | ≠ `optional-legislation-cp` | 0.6 s |
| A `free-market-cp` alias taking a cap K block on competition | ≠ `cap-k` | 0.6 s |

### Before the report

* **Affected set:** `uv run scripts/affected_tests.py` chose 193 of 661 test files from the branch's
  changes. `hard_stop.py 115 .venv/bin/python scripts/affected_tests.py --run` reached its limit twice,
  at loads of 9 and 7 shared with another session. The first run showed one failure before the stop, and
  I traced it to t40's 140-character description test (Deviation 2), now fixed. The second reached 64%
  with no failure. Per working agreement 10 the set is left to the pull request's `ci` check. Within the
  limit, run instead: the 39 affected files that read the taxonomy, the sample or `evaluate`, in three
  groups: 789 passed and 1 failed (the description cap; its file then 26 passed after the fix), 234
  passed, 59 passed (the three CI-workflow script tests among the 39 were left to CI); the always-run list (`tests/architecture/`, `tests/specs/`, `test_app.py`,
  `test_help_rendering.py`, `test_container_factories.py`) → 377 passed; the changed areas
  (`arguments/landscape/`, `integrations/landscape/`, the evaluation and landscape-run tests,
  `tests/config`, both landscape smoke files) → 1,459 passed.
* `ruff format --check .` → 1833 files already formatted; `ruff check .` → all passed;
  `pyright packages/debate_core packages/debate_cli` and the changed test files → 0 errors;
  `lint-imports` → 20 kept, 0 broken; `scripts/check_thin_handlers.py` → 72 handlers within 25
  (`landscape evaluate` is at 25); `scripts/check_command_blocks.py` and `scripts/check_links.py` → OK;
  `uv run scripts/validate_specs.py` → OK.

## Files changed

* **`config/landscape/`**: `policy-2026-27-nhi` 1.5.0 (three positions, six descriptions, header);
  `generic` 1.1.2 (three descriptions); `topics.yaml` names 1.5.0.
* **`debate_core.application.landscape_model_evaluation`**: `LabelledCard.also`, the `also` column read
  and validated (`SECOND_LABEL_COLUMN`), scoring on either label, `coach_sample_counts`, `CoachSampleCheck`
  and `LandscapeModelEvaluationService.check_sample` (the snapshot and taxonomy resolution split out of
  `_prepared`, unchanged).
* **`debate_core.arguments.landscape.evaluation_breakdown`**: `card_outcome(also=)`, `CardBreakdown.also`
  and `correct_on_second_label`, `second_label_counts`.
* **`debate_cli.commands.landscape`**: `--check-sample` (`sample_check_summary`), and
  `data.breakdown.second_label`, each card's `also` and a display line in `--breakdown`.
* **Tests**: t39's breakdown file (second label, the no-column proof, the reading rules); the model stage
  test's description cap; a new placement test over the committed taxonomy; the CLI's evaluate tests;
  the evaluate smoke check.
* **Docs**: [the taxonomy guide](../guides/landscape-taxonomy.md#your-labelled-sample-of-cards) gains the
  coach's sample, its `also` column and the check; [the evaluation's data page](../data/landscape-model-evaluation.md)
  records the review applied, with the counts.

## Deviations from the spec

1. **A smoke check outside the task's packages.** `tests/smoke/test_landscape_evaluate_smoke.py` gains one
   test for `--check-sample`, which is a new user-facing flag (working agreement 5); `tests/smoke` is not
   in `constraints.packages`. It ran against the checkout's script (red at the start commit, green
   after), not against an installed build. Accepted by the PM on 2026-11-02 (ruling 2).
2. **t40's description cap is 240 characters, not 140.** `test_every_position_the_policy_prompt_sends_has_its_side_and_a_one_line_description`
   refused the coach's `trump-k` (202 characters) and `antiblackness-k` (151), which the spec says to
   apply word for word. The spec and prompt ask for "one line", and 140 was t40's session's own bound, so
   the test keeps "no line break" and allows 240, saying why. **The PM ruled (a) on 2026-11-02**
   (ruling 1): one line is the rule, 240 characters stands, and the coach's wording stays word for word.
3. **The PM's suggested operator read is replaced.** The PM asked for a JSON-only `--breakdown` replay, or
   better a validation-only path if one existed or was small. None existed, so I added `--check-sample`
   (two statements in the handler, about 70 lines with its helpers). The replay would stop at
   `MISSING_FIXTURE_ERROR`: 1.5.0 changes the positions text and the taxonomy version, both of which are
   in every cassette's key. **Accepted by the PM on 2026-11-02** (ruling 2): the relabel's operator blocks
   end with `--check-sample`, and t40's re-record starts with it.

## Decisions and assumptions

1. **The column is `also`.** It is optional, and a blank cell means no second label.
2. **A row labelled `none` may not have a second label.** The spec does not say so. An answer naming
   any position is wrong for a `none` card, so a second label there would be silently ignored, and the
   reader refuses it by row. A row the coach marked `unsure`, or left blank, is not scored, so its
   `also` is not read.
3. **What stays on the first label:** the confusion table, the label's kind (`by_label_kind`), the
   `related` flag, a wrong answer's same-kind or other-kind outcome, and stage one's
   `placed_naming_the_label` count. Only correctness reads both labels.
4. **`landscape evaluate` without `--breakdown` keeps its JSON keys.** `correct` and `accuracy` now count
   either label, and the second-label count is in the breakdown only, as the spec asks. That keeps the
   key sets the CLI tests and the smoke check pin.
5. **Descriptions word for word,** with the first letter capitalized as every other description is. The
   two that contain ": " are quoted in the YAML. `federalism-cp`'s description is the spec's mechanism.
   The coach's ruling that it is a different mechanism from `states-cp` is a YAML comment above it, not
   description text.
6. **Labels:** "Health profiteering advantage", "Free market CP", "Federalism CP", in the file's sentence
   case. No tag keywords and no parent for the advantage, like the other advantages.
7. **Test headings are invented heading paths** built from the debate vocabulary I counted, such as
   "Cap K" over "Competition". Each is used by two or more teams, and none names a school, team or
   tournament.
8. **Expected counts after the relabel** come from t39's recorded answers (prompt 1.0.0): the two
   `multipayer-t` cards were answered with another T, `inequality-advantage` with `costs-advantage`,
   `growth-advantage` with `stagnation-advantage`, and `stagnation-advantage` with `economy-advantage`.
   So every answer-based relabel keeps its kind.

## Operator follow-ups

**ac3: the coach's relabel, then the check** (the PM records the result).

First, the coach edits `~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv`
and saves it as CSV at the same path (no command):

* add a column headed `also`, anywhere in the header row;
* in `position`: row 11 → `free-market-cp`; rows 30 and 59 → `health-profiteering-advantage`; row 31 →
  `federalism-cp`; rows 32, 38 and 47 → the model's answer for that row, from the replay;
* in `also`: rows 34 and 58 → the model's answer for that row, from the replay. Every other `also` cell
  stays empty.

The relabel ends with the check, which is also the first step of t40's re-record. Run it on the Mac that
holds the store, from this task's worktree until it merges (a worktree of `dev` after). Go to the
worktree:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t41-coach-sample-second-label-and-three-new-positions
```

Read and count the sample. It takes a few seconds, reads no card, asks no model and writes nothing:

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; else uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample ~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv --sample-rows ~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl --check-sample; fi
```

What success looks like: exit 0, and `data` has `taxonomy_version` `1.5.0`, `labelled` 47,
`by_label_kind` `{"advantage": 16, "cp": 6, "da": 5, "k": 10, "none": 3, "t": 7}` and `second_labels`
`{"rows": 2, "by_kind": {"advantage": 2}}`. Those are the counts if the coach's answers for rows 32, 38,
47, 34 and 58 are the ones t39's replay recorded (Decision 8). A different kind on one of those rows
moves one count, which is fine to paste back. Stop on a `STOP:` line, on `EVALUATION_REFUSED` (its
message names the row and the rule), or on `No such option: --check-sample` (a checkout without this
task). Paste back the whole JSON: it holds counts and taxonomy ids only.

## Follow-up work

1. **`v1-e32-t40`'s re-record follows this task, at 1.5.0, and starts with `--check-sample`** (the PM's
   ruling 2): the block in [Operator follow-ups](#operator-follow-ups) is its first step, and must exit 0
   with 47 labelled before anything is recorded. Its runbook's step 2 replay then stops at
   `MISSING_FIXTURE_ERROR` as it says. The PM amends t40's runbook steps in the next batch; this task does
   not edit them.
2. **The review-order model was trained under taxonomy 1.4.0.** It has not ordered the review queue
   since t40's 1.4.1, and still won't at 1.5.0 until `scripts/compare_local_classifier.py` trains it
   again (E32, the PM's call).
3. **`released.yaml`** gets 1.5.0 when the first report under it is published, as the guide's lock
   section says. Nothing extra is needed.
4. **For the coach's next review-queue pass:** the bare profiteering heading and the profiteering
   overview, left out above, are the coach's to place if they belong to the advantage.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-02

**Notes:**

The coach's review is applied as he gave it, and the alias choice is the strongest part: counted on
the dev store before any edit, with what moves shown position by position and every left-out heading
named with its count.

1. **ac1 passes.** 1.5.0 and generic 1.1.2 validate, the nine descriptions match the spec word for
   word (9 of 9), and the placement test failed 8 against 1.4.1 before passing 17. The PM read
   `federalism-cp` in the committed file: the description is the coach's mechanism, and the ruling
   that it differs from `states-cp` is a comment above it, as Decision 5 says.
2. **What moves is accepted.** 1,106 cards to the profiteering advantage (934 from none), 114 to
   `free-market-cp`, 62 to `federalism-cp`. The 172 cards leaving affirmatives sit under the
   advantage's own heading inside the aff's file, which is how every advantage is placed. Nothing
   moves from `cap-k`, `costs-advantage` or a DA, and the "left where they are" rows pin each
   exclusion.
3. **ac2 passes.** Red first in core, CLI and smoke; 20 of 20 mutants caught. A sample without the
   column scores exactly as t39's fixtures did. Decisions 2 to 4 are accepted: no second label on a
   `none` row, everything but correctness stays on the first label, and the non-breakdown JSON keys
   are unchanged.
4. **Deviations 1 to 3 are the PM's rulings of 2026-11-02:** the smoke check outside the packages, the
   240-character one-line cap (checked in `test_model_stage.py`), and `--check-sample` replacing the
   breakdown replay.
5. **ac3 is the operator's.** The coach relabels rows 11, 30, 31, 59, 32, 38 and 47 and adds the `also`
   column for rows 34 and 58, then runs `--check-sample` from this worktree. The PM records it, and
   the expected counts (advantage 16, cp 6, none 3; two second labels, both advantages) come from
   t39's recorded answers. A different kind on rows 32, 38, 47, 34 or 58 moves one count and is fine.
6. **Follow-ups the PM takes:** t40's re-record runbook starts with `--check-sample` (next batch); the
   review-order model's retraining at 1.5.0 is filed after the re-record; the bare profiteering
   heading and overview go on the coach's review-queue list.
7. **Closing checks:** the full affected set (193 files) hit its time limit under shared load and is
   left to `ci` (agreement 10). The 39 taxonomy, sample and evaluate files, the always-run list (377)
   and the changed areas (1,459) passed, with ruff, pyright, lint-imports, thin handlers and the specs
   clean.
8. **Merge:** `scripts/task pr --partial` once `ci` is green. The Goal stays `InProgress` until the PM
   records ac3.
