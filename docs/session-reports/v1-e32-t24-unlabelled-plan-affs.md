# Session report: v1-e32-t24-unlabelled-plan-affs

| | |
|---|---|
| Task | `v1-e32-t24-unlabelled-plan-affs` — Policy affs whose plan text has no label, identified by the plan or the advantages |
| Spec | [`plan_specs/v1/e32-argument-landscape/t24-unlabelled-plan-affs.yaml`](../../plan_specs/v1/e32-argument-landscape/t24-unlabelled-plan-affs.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t24-unlabelled-plan-affs` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**Built as ruled on 2026-10-26.** ac1 and ac2 pass, and so does the node's criterion. **ac3 is the
operator's dry run on hspolicy26 and is NOT RUN, so the Goal stays `InProgress`.** It needs one cache
re-read of about 205 to 305 s, then the dry run ([Operator follow-ups](#operator-follow-ups)).

* **The reader.** In every affirmative file, a plan text under `Thus the plan`, `Thus plan`, inline
  `Thus the plan:` or a bare `Thus` is read with t09's shape and vocabulary, the resolutional rule
  included. It is read beside t09's plan texts, in the same pass and cache, and kept apart from them, so
  no verdict of t09's changes. Card text is never read as one. `Therefore` is left out.
* **The methods** run after every existing one and move none of their rounds:
  * `TRANSITION_PLAN_TEXT`: an open round, every file `NONE` under t09, whose plan texts under `Thus`
    name one aff. Two affs are a conflict and get nothing.
  * `TRANSITION_PLAN_CARRY`: by t09's carry rule and guard.
* **t17's K-aff carry** (option (b), ruling 3) is refused into a round whose own file holds such a plan
  text naming a policy aff. The refusal comes after its advantage guard, and the round then falls to
  `TRANSITION_PLAN_TEXT`. `KRITIKAL_AFF_MARKER` and `TEAM_CARRY` rounds stay as they are.
* **The method table** counts the two methods with the others and adds two rows: the refused K-aff
  carries, and a control by method (rounds identified another way whose own file holds such a plan
  text naming another aff).
* **t17's method sentence** is widened to `The`, `Our` or `My` + `method` or `methodology` + `is`,
  `will` or `should`.
* **No taxonomy bump.** The plan-text rule version moves (`plan-text-4`, and t17's `kritikal-aff-2`),
  so the first run re-reads every affirmative file once.
* **Tests were shown failing first,** and the method table's golden is hand-written from a hand-written
  fixture that runs the real assignment.
  * 24 mutants: 23 caught at once.
  * The survivor was an equivalent check. It and its twin were removed, and the check beside them was
    mutated instead and caught.
* **The affected set** (235 files) was too long at load 16 to 29. The test directories of what changed
  and the always-run list ran instead ([below](#before-the-report-working-agreement-10)).

**What to look at first:**
* [the fixture's table](../../tests/fixtures/landscape/transition_plan_affs/README.md) and its golden;
* [Decisions](#decisions-and-assumptions) 3 and 4: the control counts any aff t09's rule calls
  different, and the carry treats a conflicting round as t09 does. Both can move the real numbers from
  the counts' simulation;
* [the operator block](#operator-follow-ups) for ac3.

### The counts that went to the PM (2026-10-26, before the build)

* **Most of these plan texts sit under one label that t09 does not read: `Thus the plan`.** Of t17's
  256 files (254 under taxonomy 1.3.0):
  * 180 hold a plan text under `Thus the plan` or `Thus plan`, or inline as `Thus the plan:`;
  * 52 more hold one under a bare `Thus` or `Therefore`.
  * In every case the plan text has t09's own shape: `should`, with a federal actor before it.
* **The advantages point to an aff no better than chance.**
  * Every advantage is read under 1 to 5 top-level affs, and single payer reads the most of all 16.
  * A rule that picks an advantage's majority aff names single payer for all 301 open rounds that
    read an advantage. In a control that leaves out each round's own team, it is right for 871 of
    935 plan-text rounds. That is the base rate: 871 of those 935 rounds are single payer anyway.
  * At the mechanism level the same rule is wrong in 204 of 720 control rounds.
* **The proposed rule** is a new method beside t09's and t17's. It reads a plan text under `Thus the
  plan`, `Thus plan`, inline `Thus the plan:` or a bare `Thus`, using t09's own shape and vocabulary.
  It applies only to rounds every existing method leaves open, and it has a carry.
  * Simulated over the counts, it identifies **327 rounds by their own plan text and 23 by carry (91
    teams)**.
  * That takes the rounds with no identified aff **from 669 to 319 of 2,192**.
  * All 17 rounds that t17's advantage guard refused get a policy aff.
  * No assignment moves, and no taxonomy bump is needed.
* **t17's method sentence** is in 3 no-plan files of the open rounds, 1 file of a K-aff round
  (already a K aff by another marker), and 0 of the 1,205 control files.
* **The PM's questions:** the label list, the method names, what happens to 9 K-aff rounds and 13
  `TEAM_CARRY` rounds whose own `Thus the plan` names a different aff, and the method sentence. The PM
  ruled on all four the same day ([below](#the-pms-rulings-applied)).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| unlabelled-plan-affs | Built; ac3 waits for the operator | The counts (2026-10-26), the PM's rulings (2026-10-26), then the reader, the method sentence, the rule, the cache, the report's rows, the scripts and the guide |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts before building, read-only: where the 256 files' plan texts sit, and which affs their advantages point to, sent to the PM with a proposed rule | PASS | [The counts](#the-counts-hspolicy26-through-2026-10-20-taxonomy-130), sent 2026-10-26 with the proposed rule. The PM ruled the same day ([below](#the-pms-rulings-applied)). Nothing was built before the ruling |
| ac2: after the ruling, on synthetic fixtures, the rule identifies an unlabelled plan's aff, refuses a round whose own plan text names another, and the method table counts the new method's rounds; tests shown failing first | PASS | `test_the_method_table_matches_the_hand_written_golden_file` against [`method_table.md`](../../tests/fixtures/landscape/transition_plan_affs/method_table.md), hand-written from the fixture's [README table](../../tests/fixtures/landscape/transition_plan_affs/README.md). The fixture's readings go through the real `build_aff_assignments`. It identifies three rounds by their own plan text and one by carry. It refuses EE (an unnamed t09 plan text of its own), HH and CC (t09's plan text, and t09's carry, naming another aff) and DD (two affs). The table counts `TRANSITION_PLAN_TEXT` 3 and `TRANSITION_PLAN_CARRY` 1. Red first: [below](#checks-shown-failing-for-their-reason) |
| ac3: the operator's dry run on hspolicy26 before and after: rounds with no identified aff, by method | NOT RUN | The operator's run. "Before" is on record: 669 of 2,192 by the method table in [the base](#the-base), from t17's dry run of 2026-10-25 and reproduced by this session's read-only pass of 2026-10-26. "After" needs the cache re-read and the dry run ([Operator follow-ups](#operator-follow-ups)) |
| unlabelled-plan-affs node: `uv run pytest packages/debate_core/tests/arguments/landscape` | PASS | `.venv/bin/python -m pytest packages/debate_core/tests/arguments/landscape` under `perl -e 'alarm 115'` → 916 passed in 9.99 s |

## The PM's rulings, applied

The rulings are a PM-ruling comment above the spec's `acceptanceCriteria` (commit `027c284`).

| Ruling | Where it is |
|---|---|
| 1. The rule as proposed: `Thus the plan`, `Thus plan`, inline `Thus the plan:`, a bare `Thus`, with t09's shape and vocabulary; only into open rounds, every file `NONE`; two affs are a conflict; a carry by t09's rule and guard. `Therefore` and unlabelled analytics left out, no advantage rule, no taxonomy bump, the rule version moves | `TRANSITION_PLAN_LABELS` and `read_transition_plan_texts` in `arguments/landscape/plan_text.py`, rule `plan-text-4`, with the label list in the vocabulary's digest. Steps 5 and 6 of `assign_affs` in `arguments/landscape/aff_assignment.py` |
| 2. `TRANSITION_PLAN_TEXT` and `TRANSITION_PLAN_CARRY`, two rows in the method table; `TEAM_CARRY`'s 254 do not change | The two method constants and their labels in `render.py`. The readings are kept apart from t09's, so t09's verdicts, and with them `PLAN_TEXT` and `TEAM_CARRY`, cannot change |
| 3. Option (b) for t17's K-aff carry only: refused into a round whose own file holds such a plan text naming a policy aff, which then falls to `TRANSITION_PLAN_TEXT`; marker rounds and `TEAM_CARRY` rounds stay, in a control row; the refusals on their own row, tested failing first | The `refused_by_transition_plan` branch of `KRITIKAL_AFF_CARRY`, after the advantage guard. `TransitionPlanInputs` carries the refused rounds and the control to the report (`TransitionPlans`), and the method table shows both rows |
| 4. t17's method sentence widened, riding the same re-read | `_METHOD_SENTENCE` in `arguments/landscape/kritikal_aff.py`, rule `kritikal-aff-2` |
| t22's 1.4.0 | Not merged when this report was written (`origin/dev` at `d0cc9c3`). If it merges first, the branch takes it in the sync, and the operator block adds the classification step |

## What was built

| Where | What |
|---|---|
| `arguments/landscape/plan_text.py` | `TRANSITION_PLAN_LABELS`; `read_transition_plan_texts`: the paragraph under a label of the list, or an inline `Thus the plan:`, read only with t09's shape and never from card text, named by t09's vocabulary. Rule `plan-text-4`; the label list is in the digest |
| `arguments/landscape/kritikal_aff.py` | The widened method sentence; rule `kritikal-aff-2` |
| `arguments/landscape/aff_assignment.py` | `TRANSITION_PLAN_TEXT` and `TRANSITION_PLAN_CARRY` (steps 5 and 6), the K-aff carry's refusal, the control, `TransitionPlanInputs`. New `AssignmentCounts` fields: `refused_by_transition_plan`, `transition_conflicting`, `transition_carry_refused`, `transition_control` |
| `application/ports/plan_text_store.py`, `application/plan_texts.py` | The cache keeps each source's `transition_paragraphs` (place, unit, shape, digest, ids: no words). `PlanTextRun.transition` holds each source's verdict over them |
| `application/aff_assignment.py` | `build_aff_assignments` takes the verdicts and returns `TransitionPlanInputs`. Both the producer and the run's seam pass the plan-text run's verdicts on |
| `application/landscape_run.py`, `application/landscape_report.py`, `domain/landscape_report.py` | The run hands the inputs to the report. `TransitionPlans` holds the refused K-aff carries and the control by method, affirmative rounds in range only |
| `arguments/landscape/render.py` | The two methods' labels and the two rows |
| `scripts/assign_landscape_affs.py` | `plan-texts` prints the transition verdicts. `assign` prints the K-aff carries refused for one, the conflicts, the carry's refusals and the control |
| `scripts/landscape_dry_run_by_section.py` | One line: the refused K-aff carries and the control by method |
| `docs/guides/landscape-taxonomy.md` | Steps 6 and 7, "Plan texts under `Thus`", the widened method sentence and the K-aff carry's refusal |
| `tests/fixtures/landscape/transition_plan_affs/` (new, by hand) | `README.md`, `taxonomy.yaml`, `rounds.yaml`, `method_table.md` |

### Checks shown failing for their reason

Each suite was run red before its code: against a skeleton that found nothing, or with its wiring line
taken out and then restored byte for byte. Agreement 8: an attempt that failed before its assertions is
not counted.

| Suite | Red |
|---|---|
| `arguments/landscape/test_transition_plan_text.py` (the reader, new) | 17 failed, 19 passed, against a reader returning nothing. The 19 are the not-read cases (`Therefore`, unshaped, card text, t09's labels), the label constant, and t09's own plan texts unchanged |
| `arguments/landscape/test_kritikal_aff.py` (the widened sentence) | 5 failed, 38 passed, against t17's sentence. The passes include the 6 forms that must stay unread |
| `arguments/landscape/test_aff_assignment.py` (the rule) | 16 failed, 43 passed, against a rule that ignored the readings. Before any code I corrected one test of my own: it expected a transition carry where t09's `TEAM_CARRY` already carries the resolutional aff. It now names the resolutional aff by a transition reading. One more failed after the first code, on the carry's refusal count. The test read t09's guard right (a round with its own t09 plan text is refused too), and I fixed the code |
| `application/test_plan_texts.py`, `integrations/landscape/test_plan_text_store.py` (the cache) | 3 failed, 23 passed, with the run's field as an empty skeleton. The refused-source case passes by construction |
| `application/test_landscape_transition_plans.py` (the report, new) | 2 failed, 4 passed: the golden and the rows, with no rows rendered and no `transition_plans` counted. The 4 check the rule, which had been built and shown red in its own suite. Two earlier attempts failed at setup (file names not hex, then YAML reading `01` as an integer) and are not counted |
| `application/test_landscape_run.py` (the seam) | 1 failed with the wiring line removed; passed with it restored byte for byte |
| `application/test_aff_assignment.py` (the producer and the seam's hand-off) | 2 failed with both hand-off lines removed; restored and checked with `cmp`. One more failure after restoring came from my test miscounting distinct files (identical plans share a digest). I fixed the test |
| `tests/scripts/test_assign_landscape_affs.py`, `test_landscape_dry_run_by_section.py` | 5 failed, 9 passed before the scripts printed the new lines |

**The golden** matched on the first render.

### Mutants

There were 24 mutants on the six rules the PM named. Each:
* was applied to one file, after a check that its text occurs exactly once;
* ran the seven covering suites (253 tests) in a fresh process, with bytecode writing off, every
  `__pycache__` cleared, and a new, empty `HYPOTHESIS_STORAGE_DIRECTORY` (no covering suite uses
  Hypothesis);
* was restored from a copy and compared byte for byte.

They ran in batches of eight under `perl -e 'alarm 110'`, with `git status --porcelain` empty after each.
Each run took 1.4 to 2.8 s at load 7 to 16.

| Rule | Mutant | Failed |
|---|---|---|
| Label list | bare `Thus` dropped | 6 |
| Label list | `Thus plan` dropped | 3 |
| Label list | inline `Thus the plan:` not read | 1 |
| Label list | no shape needed under a label | 3 |
| Label list | card text read as a plan text | 2 |
| Label list | a t09 label under a transition read as its plan | **survived**: equivalent, removed |
| Label list (after the removal) | t09's inline label under a transition read as its plan | 1 |
| `Therefore` left out | `therefore` added to the labels | 4 |
| `Therefore` left out | inline `Therefore the plan:` read | 1 |
| Conflicting round | two affs across files name one | 5 |
| Conflicting round | a conflicting file ignored | 2 |
| Conflicting round | a round with its own t09 plan text read | 3 |
| Carry and guard | carried into a round with its own `Thus` plan text | 3 |
| Carry and guard | carried into a round with its own t09 plan text | 1 |
| Carry and guard | a team naming two affs carries | 3 |
| Carry and guard | a conflicting round does not split the team | 1 |
| Carry and guard | t09's disagreeing teams carry | 1 |
| K-aff carry refusal | removed | 6 |
| K-aff carry refusal | refused for an unnamed `Thus` plan text too | 1 |
| K-aff carry refusal | before the advantage guard | 3 |
| Widened sentence | `My` dropped | 1 |
| Widened sentence | `should` dropped | 2 |
| Widened sentence | `methodology` dropped | 2 |
| Widened sentence | any word before `method` | 2 |
| Control | a round agreeing at another level counted | 2 |

**The survivor.** The reader refused a t09 label, and a transition label, as the paragraph under a
transition label. Neither can ever have t09's shape (a label is at most 6 words from a fixed list), so
the shape test already refuses both, and mutation could not tell the checks from their absence. Both
were removed, with a comment saying why (agreement 8, commit `06154ae`; behaviour unchanged, so no
rule-version bump). The check beside them, t09's inline label, is shaped and is load-bearing: its
mutant was caught.

### Before the report (working agreement 10)

* **The affected set** (`uv run scripts/affected_tests.py`) is **235 test files**. The load average
  was 16 to 29 from other sessions. t17's 210 files stopped at 69% of a 115 s limit at load 16, so I did
  not start it. The whole set is left to the pull request's `ci` check.
* **Within the limit,** each under `perl -e 'alarm 115'` on the interpreter, with `-n auto -m "not slow
  and not live"`:

  | Run | Result |
  |---|---|
  | `arguments/landscape`, `integrations/landscape`, `tests/config`, and the landscape scripts' tests (assign, dry run by section, read texts, classify) | 1,093 passed in 11.6 s |
  | The application's landscape, assignment, plan-text, analytic-text and classification tests, `domain`, `tests/architecture`, `tests/specs` | 1,708 passed in 26.4 s |
  | The other 61 test files at the top of `packages/debate_core/tests/application` | 1,925 passed in 33.8 s |
  | `debate_cli`'s landscape command, `test_app.py`, the two pinned integration lists (`test_installation.py`, `commands/test_doctor.py`), `tests/smoke/test_landscape_smoke.py` | 142 passed in 33.3 s |

  A first run of all of `application` with `domain` and the always-run list stopped at the limit at 81%
  (exit 142, load 17), with no failure by then. No worker was left running. Its parts are the second and
  third rows. The application's `caselist/` and `tub/` subdirectories, which the affected set reaches
  through imports, were not run.
* **The cheap checks:**
  * `ruff format --check .`: 1438 files already formatted;
  * `ruff check .`: all checks passed;
  * `pyright` (the project's configuration): 0 errors, in 83 s;
  * `lint-imports`: 18 kept, 0 broken;
  * `check_thin_handlers.py`: 65 handlers within 25 statements;
  * `docs_index.py --check-descriptions`: OK;
  * `check_command_blocks.py --base origin/dev`: OK;
  * `check_links.py`: OK;
  * `pre-commit run check-merge-conflict --all-files`: passed;
  * `validate_specs.py`: OK.
* **No shared test ground changed:** no `pyproject.toml`, `uv.lock`, conftest or pytest plugin. So no
  whole-selection hand-off.
* **One slip, corrected.** Commit `5a617a7` went in with 3 pyright errors, because its check chain piped
  pyright to `tail`. The next commit (`74eccf6`) fixed them, and every later check ran bare.

## The counts (hspolicy26, through 2026-10-20, taxonomy 1.3.0)

### How they were read

These are t17's passes, rerun under 1.3.0 with t17's scratch scripts adapted.

**Guards.**
* Before every pass, no `DEBATE_*` variable was set and no `caselist pull` was running.
* The load average was 6.5 to 11.8.
* Each pass ran as `perl -e 'setpgrp(0,0); alarm 115; exec @ARGV' .venv/bin/python -I ...`, with a
  100 s `SIGALRM` inside, as in t17. No pass reached either limit.
* `pgrep` found no script or worker left after any pass.

**The local store only.**
* The scripts built the services by hand over `~/.debate-research/dev`. The container and bucket mode
  were not involved, and nothing was published.
* **Nothing was written:** the 19 files under `~/.debate-research/dev/landscape/` and `reports/` had
  the same SHA-256 before the first pass and after the last.

**Counts only.**
* The scripts and their scratch JSON are in the session's scratchpad, outside the repository.
* The JSON holds:
  * source digests and t03's round ids;
  * salted team keys (the salt was never written);
  * verdicts, position ids and categories;
  * label forms made only of listed words (`thus the plan`, `therefore`). Any other form is recorded
    as "other short label".
* No paragraph, tag or cite text is in them. A grep for `should`, `united states` and `school` found
  only the position id `should-t`.

**What each pass read:**

| Pass | What it read | Wall-clock |
|---|---|---|
| Rounds | `LandscapeRunService` as a dry run, t11's texts off, t09's `AffAssignmentService` on its warm cache, with the report's inputs captured and t03's `count()` called on them | 73.3 s (dry run 64.6 s) |
| Plan texts, sample (1 of 20) | 27 files | 29.9 s |
| Plan texts, open rounds, 2 shards, 7 workers | 534 files | 61.5 s, 62.0 s |
| Plan texts, control, 4 shards, 7 workers | 1,205 files | 83.2, 76.9, 83.8, 84.0 s |
| Plan texts, K-aff rounds | 31 files | 34.5 s |
| Tables | the scratch JSON | under 1 s each |

**How the plan-text pass read each file:**
* Each file was parsed in memory from the blob store under a placeholder path (t09's `blob_jobs`).
* Its paragraphs came from t11's `section_paragraphs_of`, and t11's `heading_placement` placed them.
* For each paragraph holding `should`, the pass kept:
  * its unit, and its word-count bucket;
  * the actor class before `should`;
  * whether t09's shape holds (`_shaped`: a federal actor before `should`, not the fifty states);
  * what comes before it: a t09 label, a short label of at most 6 words, a longer heading, or other
    text;
  * an inline label before a colon;
  * its placement;
  * the affs t09's vocabulary names in it, by t09's `named` and resolutional rules.

### The base

The dry run reproduces t17's table after the coach's families exactly:

| Method | Aff rounds |
|---|---|
| `PLAN_TEXT` | 1,172 |
| `TEAM_CARRY` | 254 |
| `PLACED_CARD` | 57 |
| `KRITIKAL_AFF_MARKER` | 31 |
| `KRITIKAL_AFF_CARRY` | 9 |
| Not identified | **669 of 2,192**, 190 teams |
| Of those, refused by t17's advantage guard | 17 |

* **The 669 rounds disclose 534 files.** By t09's verdict: `NONE` 524, `CONFLICTING` 7, `UNNAMED` 2,
  `NAMES` 1. In 652 of the rounds, every file is `NONE`.
* **t17's 256 files under 1.3.0** (no-plan files with a heading placed under an advantage, READS) are
  **254 files, 302 rounds and 93 teams**. The other 2 are files of K-aff rounds now, the 2 marker files
  that t17's counts said carry an advantage heading.
* **301 open rounds (94 teams) read an advantage** by t15's rule, a card placed under it READS on the
  round's own side. 300 of them are rounds of the 254 files.

### Where the plan texts sit

Each file is counted once, under the first category in this order that it meets. The first three are
labels t09 does not read, over a paragraph with t09's shape that is not card text. A file's rounds can
fall under two categories through two files, so the rounds column does not sum.

| Where the plan text sits | t17's 256 (254): files | rounds | teams | All 524 no-plan files: files | rounds | teams |
|---|---|---|---|---|---|---|
| Under a label naming the plan that t09 does not read: `Thus the plan`, `Thus plan`, inline `Thus the plan:` | **180** | 211 | 65 | **260** | 303 | 82 |
| Under a transition label alone: `Thus`, `Therefore` | **52** | 67 | 17 | 68 | 86 | 22 |
| A federal `should` analytic of at most 80 words, under no label | 11 | 12 | 9 | 50 | 63 | 25 |
| A federal `should` sentence as a heading | 0 | | | 3 | 3 | 2 |
| A federal `should` sentence only as a card tag | 1 | 1 | 1 | 7 | 7 | 2 |
| A federal `should` sentence only inside card text | 9 | 10 | 6 | 58 | 90 | 31 |
| A `should` analytic of another federal actor (Congress, an agency, the President, a court) | 0 | | | 0 | | |
| No `should` sentence a plan could be | 1 | 1 | 1 | 78 | 100 | 45 |

**The labels, by form,** over the 524 no-plan files. Each form is in one paragraph per file.

| Label t09 does not read | Files |
|---|---|
| `Thus the plan` | 172 |
| `Thus` | 53 |
| `Thus plan` | 51 |
| `Thus the plan:` inline | 37 |
| `Therefore` | 15 |
| `Hence`, `So` | 0 |

* t09 reads `The plan`. The normalizer keeps `thus`, so `Thus the plan` misses
  `PLAN_TEXT_LABELS`.
* **The reader matches t09's.** No open `NONE` file has a t09 label over a shaped paragraph. In the
  control's `NAMES` files, the same reading of t09's own labels names t09's aff in 929 of 931
  paragraphs, the same top-level aff in 1, and another in 1.
* **No other actor is missed.** A `should` with Congress or an agency as its actor adds nothing to any
  count. t09's federal-actor shape holds for these plans.

**What those labels name** (`Thus the plan`, `Thus plan`, inline, `Thus`, `Therefore`), by t09's
vocabulary and resolutional rule:

| | t17's 256 (254) | All 524 |
|---|---|---|
| Names one aff | **199** | 289 |
| A plan text naming none | 33 | 39 |
| No such label | 22 | 196 |
| Of "names one", only the resolutional aff (`nhi-aff`) | 1 | 2 |

### The control: the same labels in files whose round already has an aff

* **The control is t17's: the 1,205 files of the rounds identified by `PLAN_TEXT`, `TEAM_CARRY` or
  `PLACED_CARD`.** These labels appear almost only where t09 reads no plan text: in 1 `NAMES` file,
  naming the same aff.
* **The test is the 254 `TEAM_CARRY` rounds,** whose aff came from the team's other rounds. 142 hold
  one of these labels in their own files. What the label's plan text names, against the carried aff:

| Label | The carried aff | The same top-level aff, another level | Another top-level aff | Names none |
|---|---|---|---|---|
| `Thus the plan`, `Thus plan`, inline (paragraphs) | 61 | 31 | 11 | 1 |
| `Thus` (paragraphs) | 5 | 22 | 0 | 13 |
| `Therefore` (paragraphs) | 0 | 3 | 3 | 0 |
| **By round** | **64** | **51** | **13** | **14** |

So where these labels name an aff, they agree with the team's carried aff at the top level in 115 of
128 rounds. `Therefore` is the weak one: it disagrees in 3 of its 6 paragraphs.

### What a rule would identify

This is a simulation over the counts. Each variant:
* runs after every existing method and moves no assignment;
* reads only files whose t09 verdict is `NONE`;
* takes a round whose files name two affs as conflicting, and assigns it nothing;
* carries by t09's rule: a team whose identified affs, existing and new, narrow to one carries it
  into its open rounds that hold no plan text of their own.

| Rule | Own plan text | Carried | Teams | Left conflicting | Carries refused (own plan text names none) | Unidentified after |
|---|---|---|---|---|---|---|
| Plan labels only (`Thus the plan`, `Thus plan`, inline) | 284 | 18 | 79 | 9 | 12 | 367 |
| **Plan labels and `Thus` (proposed)** | **327** | **23** | **91** | 9 | 14 | **319 of 2,192** |
| Plan labels, `Thus` and `Therefore` | 339 | 21 | 97 | 9 | 32 | 309 |
| As the last row, and federal `should` analytics of at most 80 words under no label | 385 | 14 | 115 | 9 | 36 | 270 |
| As the last row, and Congress or an agency as actor | 385 | 14 | 115 | 9 | 36 | 270 |

**The proposed rule's 350 rounds:**

| By top-level aff | Rounds |
|---|---|
| `single-payer-aff` | 324 |
| `nhi-aff` (11 of them by the resolutional rule) | 11 |
| `eco-nhi-aff` | 8 |
| `incarceration-aff` | 4 |
| `tiered-nhi-aff` | 3 |

* **By mechanism:** `single-payer-aff` itself 259, `global-budgets-aff` 29, `single-public-authority-aff`
  27, `prescription-drug-coverage-aff` 4.
* **All 17 rounds** that t17's advantage guard refused are among them.
* **Of the 301 open rounds that read an advantage, 231 are among them.** 70 stay open (26 teams):
  * 35 hold a plan text that names no aff;
  * 34 hold no plan text these labels mark;
  * 1 is conflicting.
* **Why `Therefore` is left out:** it adds 12 rounds of its own but blocks 18 carries, and it
  disagrees in 3 of its 6 control paragraphs.
* **Why the unlabelled analytics are left out:** they add 46 rounds, but the `TEAM_CARRY` control's
  "another top-level aff" goes from 13 to 21.

### Rounds that already have an aff and hold one of these plan texts

The PM's rules for the build keep these as they are. These are their sizes:

| Method | Rounds | Of those, the label names a policy aff |
|---|---|---|
| `KRITIKAL_AFF_CARRY` | 9 | **7** |
| `KRITIKAL_AFF_MARKER` | 31 | 2 |
| `TEAM_CARRY` | 254 | 13 name another top-level aff than the carried one ([the control](#the-control-the-same-labels-in-files-whose-round-already-has-an-aff)) |

t17's K-aff carry reads t09's `NONE`, so it could carry into a round whose plan text sits under `Thus
the plan`. 7 of its 9 carried rounds are such rounds.

### Which affs the advantages point to (t15's advantages by aff)

**t15's mapping is built from the 1,466 assigned rounds:** each advantage, under the top-level affs and
mechanisms whose assigned rounds read it. Teams are counted.

| Advantage | Top-level affs reading it | Teams | Single payer's teams |
|---|---|---|---|
| `costs-advantage` | 3 | 109 | 102 |
| `disease-advantage` | 2 | 86 | 85 |
| `economy-advantage` | 3 | 80 | 74 |
| `inequality-advantage` | 5 | 69 | 64 |
| `coverage-advantage` | 4 | 63 | 59 |
| `growth-advantage` | 3 | 41 | 39 |
| `access-advantage` | 1 | 32 | 32 |
| `bioterror-advantage` | 2 | 20 | 19 |
| `pandemics-advantage` | 2 | 20 | 17 |
| `budgets-advantage` | 3 | 19 | 17 |
| `stagnation-advantage` | 2 | 16 | 15 |
| `innovation-advantage` | 4 | 12 | 8 |
| `data-advantage` | 1 | 9 | 9 |
| `sustainability-advantage` | 1 | 8 | 8 |
| `pharma-advantage` | 1 | 7 | 7 |
| `biotech-advantage` | 2 | 6 | 5 |

**At the mechanism level,** each advantage is read under 3 to 9 affs. No advantage has a `parent` in
the taxonomy, so the advantages can point only through these reads.

**The 301 open rounds that read an advantage** read 1 advantage (100 rounds), 2 (163), 3 (33) or 4 (5).

| Rule over the round's advantages | One aff | Several | None |
|---|---|---|---|
| Any aff reading one of them (top level) | 9 rounds (4 teams) | 292 | 0 |
| Same, the K aff left out | 14 | 287 | 0 |
| An aff reading every one of them (top level) | 51 | 250 | 0 |
| Only affs with at least half an advantage's teams (top level) | **301, all `single-payer-aff`** | 0 | 0 |
| Only affs with at least half an advantage's teams (mechanism) | 194 | 0 | 107 |

**The control leaves out each round's own team,** then asks this of the 935 `PLAN_TEXT` rounds that
read an advantage:

| Rule | Right | Wrong | Several or none |
|---|---|---|---|
| Any aff reading one of them (top level) | 29 | 0 | 906 several |
| At least half an advantage's teams (top level) | **871** | **64** | 0 |
| At least two thirds (top level) | 866 | 64 | 5 none |
| At least half (mechanism) | 516 | **204** | 212 none, 3 several |

The majority rule's 871 equals the base rate: 871 of the 935 rounds are single payer. It never names
anything else, so it adds nothing an unconditional "single payer" would not. At the mechanism level it
is wrong in 28% of the rounds it names.

### t17's method sentence

The sentence is `The`, `Our` or `My` with `method` or `methodology`, then `is`, `will` or `should`.
t17's counting regex was read outside headings.

| Files | Hold it | Notes |
|---|---|---|
| The 524 no-plan files of the open rounds | **3** (3 rounds, 3 teams) | 2 in a tag, 1 in an unstyled paragraph. Placed: 1 under a K, 1 where the headings place nothing, 1 with no heading. None holds a K-aff marker, an advantage heading or read, or one of the plan labels above |
| The 31 files of the K-aff rounds | 1 | A `KRITIKAL_AFF_MARKER` round, already a K aff by another marker |
| The control (1,205) | **0** | |

Widening t17's sentence to this form would add at most 3 rounds by their own marker, before any carry.
Their teams' other open rounds were not counted.

## Files changed

All relative to `origin/dev` at `d0cc9c3`, which the branch was synced onto with `scripts/task sync`
before the build.

* **`debate_core.arguments.landscape`:** `plan_text.py` (the reader), `kritikal_aff.py` (the sentence),
  `aff_assignment.py` (the methods, the refusal, the control, `TransitionPlanInputs`), `render.py` (the
  labels and rows).
* **`debate_core.application`:** `plan_texts.py`, `ports/plan_text_store.py`, `aff_assignment.py`,
  `landscape_run.py`, `landscape_report.py`.
* **`debate_core.domain`:** `landscape_report.py` (`TransitionPlans` and the report's field).
* **Tests:**
  * in `packages/debate_core/tests`: `arguments/landscape/test_transition_plan_text.py` and
    `application/test_landscape_transition_plans.py` (new);
  * `arguments/landscape/test_aff_assignment.py` and `test_kritikal_aff.py`;
  * `application/test_plan_texts.py`, `test_aff_assignment.py` and `test_landscape_run.py`;
  * `integrations/landscape/test_plan_text_store.py` (the cache's field pin);
  * `tests/scripts/test_assign_landscape_affs.py` and `test_landscape_dry_run_by_section.py`.
* **`tests/fixtures/landscape/transition_plan_affs/`** (new, by hand).
* **`scripts/assign_landscape_affs.py`, `scripts/landscape_dry_run_by_section.py`.**
* **`docs/guides/landscape-taxonomy.md`.**
* **The spec:** the PM's rulings as a comment above `acceptanceCriteria`. The Goal's phase stays
  `InProgress` (ac3).
* This report.

## Deviations from the spec

1. **Files outside `constraints.packages`,** each needed by a ruling or by ac3, as for t17:
   * `debate_core.domain`: the report's `TransitionPlans` model, beside t17's `KritikalAffs`;
   * `scripts/assign_landscape_affs.py` and `scripts/landscape_dry_run_by_section.py`, with their tests
     in `tests/scripts`. The operator's re-read and dry run must print the new counts for ac3, and an
     exact-output test of each pins every line.

   I did not edit the spec's list; the PM amends it, as for t17. `debate_core.integrations` is not
   touched: only its test of the cache's fields, which is under `packages/debate_core/tests`.

## Decisions and assumptions

1. **The readings are kept apart from t09's.** They go in their own cache field and their own verdict
   per source (`PlanTextRun.transition`), never into t09's paragraphs. So no t09 verdict changes, and
   `PLAN_TEXT`, `TEAM_CARRY` and t09's carry guard read exactly what they read before. That is how
   `TEAM_CARRY`'s 254 stay (ruling 2). They are read in every file, and used only where the rule says.
2. **What the reader takes, as the counts read it:**
   * a label is a paragraph of at most 6 words that t01's normalizer reduces to `thus the plan`, `thus
     plan` or `thus`. So `Thus, the plan:` and `1AC Thus the plan` count, as in the counts;
   * the inline form is `Thus the plan:` (a comma allowed after `Thus`), colon only;
   * the plan text must have t09's shape and is never card text (evidence or cite);
   * a t09 inline label under a transition label is t09's to read.
3. **The control counts a round when t09's own rule calls the two affs different.** That is,
   `narrowest` of the round's aff and the plan text's ids keeps more than the round's aff: a sibling
   mechanism counts, a parent or child does not, and the resolutional aff gives way. The counts' 13
   `TEAM_CARRY` rounds were "another top-level aff". Two mechanisms of single payer also disagree under
   t09's rule, so the real control can be larger than 13 + 2. A conflicting plan text under `Thus` in
   such a round counts too.
4. **The carry follows t09's rule and guard exactly.** A team carries only if:
   * it has a `TRANSITION_PLAN_TEXT` round;
   * its assigned and placed affs, every method's, narrow to one, so a team that is also a K aff
     carries nothing;
   * its rounds neither disagree under t09 nor conflict under the new reading.

   It carries only into open rounds whose every file is `NONE` under both readers. The counts'
   simulation did not apply the disagreement part, so the real carry can come in below its 23.
5. **The K-aff carry's refusal comes after its advantage guard.** A round reading an advantage still
   counts under t17's guard, so t17's 17 are not recounted as transition refusals. It refuses a plan
   text that names an aff or conflicts. One that names nothing refuses nothing. t17's row "Of those, the
   kritikal affirmative not carried in: the round's own file reads an advantage" still counts only
   rounds that are unidentified. Its rounds now mostly fall to `TRANSITION_PLAN_TEXT`, so expect that
   row near 0 (the counts' simulation identified all 17).
6. **The widened method sentence is read where t17 reads its sentences:** any paragraph but card text,
   headings included. The counts read it outside headings, so the dry run may find one more.
7. **Two equivalent checks were removed** after their mutant survived (Mutants above).
8. **The rule versions:** `plan-text-4` (with the label list in the vocabulary's digest, so an edit to
   it re-reads every file) and `kritikal-aff-2`. Removing the equivalent checks changes no reading, so
   it bumped nothing.
9. **From the counts, unchanged:** the 256 are 254 under 1.3.0, and the other-actor row shows t09's
   federal-actor shape loses nothing.

## Operator follow-ups

**ac3: the cache re-read, then the dry run.** Local only: it writes under
`~/.debate-research/dev/landscape/` alone, publishes nothing and writes to no bucket. It prints counts
only. The taxonomy is unchanged (1.3.0), so the classification and analytic-text caches are still
current, and only the plan texts are read again.

**If `v1-e32-t22` (taxonomy 1.4.0) merges into `dev` before you run this,** tell the session first. It
syncs the branch and gives you this block with the classification step added.

From the task worktree:

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t24-unlabelled-plan-affs
```

**1. The re-read** (expected runtime 205 to 305 s, as t17's of 2026-10-25). It refuses to start if a
`DEBATE_*` variable is set or a `caselist pull` is running:

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run python scripts/assign_landscape_affs.py plan-texts --caselist hspolicy26 --snapshot 2026-10-20; fi
```

**Success looks like:**
* `Plan texts: 1770 sources, 0 cached, 1770 parsed, 0 refused by the parser, 0 unread; cache written.`
  The rule version changed, so nothing is cached;
* t09's verdicts unchanged from t17's: `NAMES: 950`, `CONFLICTING: 7`, `UNNAMED: 2`, `NONE: 811`
  documents;
* `Plan texts under Thus: NAMES N, ...` with **N above zero** (the counts expect a few hundred);
* a `K-aff markers:` line, 28 documents or a few more for the widened method sentence;
* a `Runtime` line.

A `STOP:` line means nothing ran. Paste every line back.

**2. The dry run** (expected runtime about 75 s on the warm caches). It is read-only and takes no
bucket lock. The session can run it once step 1 is done, or paste:

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run python scripts/landscape_dry_run_by_section.py --caselist hspolicy26 --snapshot 2026-10-20; fi
```

**Success looks like:**
* `Dry run of hspolicy26 through 2026-10-20, taxonomy 1.3.0: nothing written; 7 files planned.`;
* `Affirmative rounds by method: ...`. `PLACED_CARD 57`, `PLAN_TEXT 1172` and `TEAM_CARRY 254` are as
  before. `TRANSITION_PLAN_TEXT` is above zero (the counts' simulation: about 327) and
  `TRANSITION_PLAN_CARRY` up to about 23. `not identified N of 2192` has N well below 669 (the
  simulation: about 319);
* the `Kritikal affirmatives (kritikal-aff): ...` line. `KRITIKAL_AFF_CARRY` is expected to drop from 9,
  about 7 of them refused;
* the `Plans under Thus: the K-aff carry refused in R rounds; C rounds identified another way ...; by
  method: ...` line;
* the scan lines, as before.

Paste every line back. A `Refused:` line means the run did not start, and says why.

**The "before" for ac3** is already on record: t17's dry run of 2026-10-25 and this session's
read-only pass of 2026-10-26, both at 669 of 2,192 ([the base](#the-base)). A dry run of today's `dev`
code would need the old cache key, which step 1 replaces.

**The publish** waits for the cloud cutover. The republish carries t17, t23 and this task together,
after the cutover.

## Follow-up work

* **The 70 open rounds that read an advantage** (26 teams, the counts' simulation) stay unidentified.
  35 hold a plan text under `Thus` that names no aff, and 34 hold no plan text these labels mark. A
  plan text that names nothing might take an alias the coach adds. That is the coach's sheet
  (v1-e32-t09's), not a rule.
* **`Therefore`,** if the PM wants it later, is one word in `TRANSITION_PLAN_LABELS`. It would add about
  12 rounds and block about 18 carries.
* **The CLI's JSON** does not carry the transition rows yet, as t17's group did not. The run's report
  carries them (`LandscapeReport.transition_plans`).

## Questions for the PM

None open.

### The questions of 2026-10-26 on the counts, answered

The PM ruled the same day:
1. the rule as proposed;
2. the method names;
3. option (b) for t17's K-aff carry only, with the marker and `TEAM_CARRY` rounds kept in a control
   row;
4. the method sentence widened.

Kept as asked:

```text
v1-e32-t24 counts (session, 2026-10-26). Read-only, local store only, nothing
written (19 files checksummed before and after), counts only. hspolicy26
through 2026-10-20, taxonomy 1.3.0. The dry run reproduces t17's table:
669 of 2,192 aff rounds unidentified (190 teams), 17 refused by the
advantage guard. t17's 256 no-plan files with an advantage heading are 254
under 1.3.0 (302 rounds, 93 teams); the other 2 are K-aff rounds' files now.

Where their plan texts sit (each file once, first category that holds):
  under `Thus the plan` / `Thus plan` / inline `Thus the plan:`   180 files (211 rounds, 65 teams)
  under a bare `Thus` or `Therefore`                                52 files (67 rounds, 17 teams)
  a federal should analytic under no label                         11
  only inside card text 9; only as a tag 1; none 1; another actor (Congress, an agency) 0
Every one has t09's shape (should, a federal actor before it). t09 reads
`The plan`, but the normalizer keeps `thus`. Over all 524 no-plan files:
Thus the plan 172, Thus 53, Thus plan 51, inline 37, Therefore 15.
What they name: 199 of the 254 one aff, 33 none, 22 hold no such label.

Control (the 254 TEAM_CARRY rounds, aff from the team): 142 hold such a
label; it names the carried aff 64, the same top-level aff at another level
51, another top-level aff 13, none 14. Therefore: 3 of its 6 disagree.

Advantages (t15's advantages by aff): every advantage is read under 1-5
top-level affs, single payer the most of all 16. The majority-aff rule
names single payer for all 301 open rounds reading an advantage; with each
round's own team left out it is right in 871 of 935 PLAN_TEXT rounds, which
is the base rate (871 of 935 are single payer). By mechanism it is wrong in
204 of 720. Advantages do not identify an aff here.

1. The rule. A new method beside PLAN_TEXT, TEAM_CARRY, KRITIKAL_AFF_MARKER
   and KRITIKAL_AFF_CARRY: in a file t09 reads as NONE, a plan text under
   `Thus the plan`, `Thus plan`, inline `Thus the plan:` or a bare `Thus`,
   with t09's shape and vocabulary (resolutional rule included). Only into
   rounds every existing method leaves open, every file NONE; two affs
   named is conflicting, nothing assigned. A carry by t09's rule and guard.
   No advantage rule. No new ids, so no taxonomy bump; the plan-text rule
   version moves, so ac3 starts with one operator re-read (about 205-305 s).
   Simulated: 327 rounds by own plan text, 23 by carry, 91 teams; 669 ->
   319 unidentified; all 17 advantage-guard refusals get a policy aff.
   (With Therefore: 339 + 21 -> 309, but it blocks 18 carries and disagrees
   3 of 6. Adding federal should analytics under no label: -> 270, but the
   control's disagreements go from 13 to 21.)
   Recommendation: as written, Therefore and unlabelled analytics left out.

2. Names: TRANSITION_PLAN_TEXT for the round's own plan text and
   TRANSITION_PLAN_CARRY for the carry, two rows in the method table, as
   t17's two?
   Recommendation: yes; the carry kept apart so TEAM_CARRY's 254 do not
   change.

3. Rounds that keep their aff under "never move": 7 of t17's 9
   KRITIKAL_AFF_CARRY rounds and 2 of its 31 KRITIKAL_AFF_MARKER rounds hold
   a `Thus the plan` text naming a policy aff; 13 TEAM_CARRY rounds hold one
   naming another top-level aff. Options:
   (a) leave all of them, and count them in the method table as a control
       row (as t17's control);
   (b) let the new reading refuse t17's K-aff carry where the round's own
       file holds such a plan text (moves 7 rounds; changes t17's method).
   Recommendation: (a). The rules say t17's methods stay; the row puts the
   7 on record for a later ruling.

4. t17's method sentence (The|Our|My + method|methodology + is|will|should):
   3 no-plan files of the open rounds (3 rounds, 3 teams; 2 in tags, none
   with a plan label, a K marker or an advantage), 1 file of a K-aff round
   already a K aff, 0 of the 1,205 control files.
   Recommendation: widen it. It is specific (0 in the control) but small (at
   most 3 rounds before carry). It is a marker-list change in t17's reader,
   so it needs your ruling under "t17's K-aff methods stay".
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
