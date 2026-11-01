# Session report: v1-e32-t37-model-use-gate-reads-the-open-questions-table

| | |
|---|---|
| Task | `v1-e32-t37-model-use-gate-reads-the-open-questions-table` — The model-use gate reads open question 4 from the policy's open-questions table, not the first row numbered 4 |
| Spec | [`plan_specs/v1/e32-argument-landscape/t37-model-use-gate-reads-the-open-questions-table.yaml`](../../plan_specs/v1/e32-argument-landscape/t37-model-use-gate-reads-the-open-questions-table.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t37-model-use-gate-reads-the-open-questions-table` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`model_use_gate` (`debate_core/application/landscape_model_stage.py`) used to read the policy's
first line starting with `| 4 |`. In the real policy that is the clause register's rate-limit row,
so a live run or a recording would have gone through while open question 4 was open. The gate now
works in four steps: it finds the `## Open questions` heading, takes the first table under it
(before the next heading), finds that table's `Status` column by its header, and reads the row whose
first cell is `4`. It refuses when any of these is missing, and the refusal says which one. The
status rule still refuses an open or empty status, but "open" now has to be a whole word, where a
hyphen counts as part of a word. So `open-questions`, `open-source`, `OpenEv` and `OpenCaselist` no
longer refuse, while `**Open**`, `Still open.`, `_open_`, `Opened`, `Reopened` and `Re-opened` do.
The real policy (version 1.20) passes the gate. A policy shaped like the real one fails it when
question 4 is `**Open**` and passes it when question 4 is `**Resolved**`. 21 of the new tests failed
against the old gate. The PM should look first at one choice: a "reopened" status refuses (see
Decisions, and the question for the PM below).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `model-use-gate-reads-the-open-questions` (Policy gate row) | Done | Red tests committed at `779d744`; the gate fixed at `f62ac7f`; 12 mutants run, 12 caught. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — the gate refuses when open question 4's status is open and allows it when resolved, reading the open-questions table, with an earlier table's row 4 ignored, by tests shown failing first against today's gate | PASS | **Red**, at `779d744` (tests only, old gate): `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -p no:randomly -n 0 -q --tb=no -rfE packages/debate_core/tests/application/test_landscape_model_stage.py -k "gate or open" packages/debate_cli/tests/test_landscape_command.py` → `21 failed, 14 passed, 104 deselected in 0.62s`. The failures include the policy-shaped fixture with question 4 `**Open**`, which the old gate allowed in the core test, the live CLI run and the recording CLI run; the earlier-row-4 case; every missing-section case; and every open-word case. At red the live CLI run got past the gate and stopped at the test wiring's `assert mode is ModelMode.REPLAY` (`INTERNAL_ERROR`, exit 70), so no model could be reached. **Green**, at `f62ac7f`: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -q --tb=short packages/debate_core/tests/application/test_landscape_model_stage.py packages/debate_cli/tests/test_landscape_command.py` → `139 passed in 13.12s`. |
| Node criterion "Policy gate row tests pass": `uv run pytest packages/debate_cli/tests/test_landscape_command.py -k model_use` | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run pytest packages/debate_cli/tests/test_landscape_command.py -k model_use` → `5 passed in 5.46s`. The command selected nothing before this task. It now selects the five `test_model_use_gate_*` tests: live run refused with the fixture open, recording refused with it open, recording allowed with it resolved, recording refused with no `## Open questions` heading, and recording allowed under the policy in this checkout. |

### The tests, and what they failed on at red

Core tests, in `packages/debate_core/tests/application/test_landscape_model_stage.py`:

* **The real policy's shape.** `policy_shaped(status)` copies the real file's tables in their
  order: a clause register with rows 3, 4 and 5, then a permitted-uses table with a row 4, then
  `## Open questions` with an intro paragraph containing `**open**`, and questions 3, 4 and 5, then
  the next heading. With question 4 `**Open**` the gate refuses (red). With `**Resolved** 2026-11-01
  …` it allows. A row 4 whose status says `**Open**`, placed before the policy, does not refuse a
  resolved question 4 (red: the old gate refused on it).
* **The real file.** `docs/policies/caselist-data-use.md` as committed (version 1.20) is allowed.
  It also passed at red, because the old gate read the clause register's row, whose cells contain no
  "open". A policy edit selects this test (affected_tests follows the path), so a later version that
  reopens question 4 fails it, as it should.
* **The synthetic cases.** These are the existing rows (`OPEN`, `ANSWERED`, `OTHER`, the
  no-row and empty-status cases), placed under the heading and its table header. All passed at red.
  A whitespace-only status case was added.
* **Missing pieces.** Each refusal names the piece it could not find: no heading, a differently
  worded heading, a table only after the next heading, no table, no question 4, no `Status` column.
  All six were red.
* **The Status column is found by its header.** A table with its columns in another order allows
  when the `Status` cell is resolved and refuses when it is open (red).
* **Open words.** These statuses refuse (all nine red, because the old gate read the clause
  register): `**Open**`, `Open`, `OPEN — waiting…`, `Still open.`, `_open_`,
  `**Reopened** 2026-12-01`, `Re-opened when…`, `Opened 2026-11-05`, and
  `**Resolved** for the pilot; open for the V2 tub`.
* **Words that contain "open".** These statuses are allowed: a resolved status mentioning the
  open-questions table, one mentioning OpenEv and OpenCaselist, one mentioning open-source archives,
  `**Answered**`, and `**Accepted as a known gap**`. They passed at red for the wrong reason (the
  old gate read the clause register). The mutant that matches "open" as a substring is what shows
  they hold.

CLI tests, in `packages/debate_cli/tests/test_landscape_command.py`:

* Five new `test_model_use_gate_*` tests, listed under the node criterion above. Three were red:
  both refusals with question 4 open, and the refusal for a missing heading.
* The two existing CLI refusal tests (`test_live_is_refused_while_the_policy_leaves_question_four_open`
  and `test_evaluate_record_is_refused_while_the_policy_leaves_question_four_open`) keep their row,
  now under the heading and table header. A bare row would still be refused, but for a missing
  heading rather than an open status.

### Mutation run (agreement 8)

Script: `/private/tmp/claude-501/-Users-charlesclark-Documents-debate-debate-intelligence-tool-debate-intelligence-worktrees-v1-e32-t37-model-use-gate-reads-the-open-questions-table/5f6c151e-7cc6-44b5-9cec-43ade3ccab2b/scratchpad/mutants.py` (not committed). It applies one mutant at a time to
`landscape_model_stage.py` at `f62ac7f`, then runs the core file with `-k "gate or open"` and the
whole CLI test file under `-n 0 -p no:randomly`. Each run gets a fresh, empty
`HYPOTHESIS_STORAGE_DIRECTORY`. These tests use no Hypothesis, but the setting follows the agreement
anyway. The file is restored from `HEAD` at the end, and `git status` was clean afterwards. The
whole script ran under `hard_stop.py 115`. Every catch below is an assertion failure: no run errored
at collection or crashed.

| Mutant | Result | Caught by (first of them) |
|---|---|---|
| The PM's mutant 1: read the first `| 4 |` row again (the old body put back) | caught, 22 failed | the policy-shaped open fixture, the earlier-row-4 case, the missing-heading cases |
| The PM's mutant 2: allow a missing heading | caught, 3 failed | `no-heading`, `other-heading`, the CLI missing-heading test |
| The PM's mutant 3: match "open" as a substring (`"open" in status.casefold()`) | caught, 3 failed | the open-questions-table, OpenEv and open-source statuses |
| The PM's mutant 4: refuse a resolved status | caught, 9 failed | the resolved fixture, the real policy, the reordered-columns case |
| Status read as the third cell again | caught, 1 failed | the reordered-columns case |
| Table read past the next heading | caught, 1 failed | `table-after-the-next-heading` |
| Missing table allowed | caught, 2 failed | `no-table`, `table-after-the-next-heading` |
| Missing Status column allowed | caught, 1 failed | `no-status-column` |
| Missing row allowed | caught, 2 failed | `no-row`, the synthetic no-row case |
| Hyphen not part of a word | caught, 2 failed | the open-questions-table and open-source statuses |
| Only the bare word "open" (no `opened`, `reopened`, `re-opened`) | caught, 3 failed | `**Reopened**`, `Re-opened`, `Opened` |
| Underscore joins a word (`\w` in the boundary) | caught, 1 failed | `_open_` |

### Checks before the report

* **Affected set, not completed.** `uv run scripts/affected_tests.py` chose 219 of 642 test files
  (34.1%) from 5 changed files, in 23.2 s. `.venv/bin/python scripts/hard_stop.py 115 uv run
  scripts/affected_tests.py --run` was stopped at its 115-second limit (exit 124) at about 8% of the
  tests, with no failure up to that point. The set is well over two minutes, so under agreement 10
  it is left to the pull request's `ci` check. It is not handed to the operator.
* **Instead, within the limit:** the tests that import the changed module or drive the gate, plus
  the always-run list, run as
  `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -q -m "not slow and not live" tests/architecture/ tests/specs/ packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py packages/debate_cli/tests/test_landscape_cassettes.py packages/debate_cli/tests/test_landscape_command.py packages/debate_cli/tests/test_output.py packages/debate_core/tests/application/test_landscape_model_stage.py packages/debate_core/tests/application/test_position_classification.py`
  → `683 passed in 40.55s`.
* `uv run ruff format --check .` → `1774 files already formatted`; `uv run ruff check .` → `All checks passed!`
* `uv run pyright packages/debate_core packages/debate_cli` → `0 errors, 0 warnings, 0 informations` (60 s)
* `uv run lint-imports` → `Contracts: 20 kept, 0 broken.`; `uv run python scripts/check_thin_handlers.py` → `OK: 70 CLI command and API route handlers within 25 statements`
* `uv run scripts/validate_specs.py` → `OK: 567 files, 41 epics, 504 tasks, 22 releases`
* The spec was compared with `origin/dev` before the report: only `status.phase` differs, so the PM
  has not amended it.

## Files changed

* `packages/debate_core/src/debate_core/application/landscape_model_stage.py`: the gate reads
  heading, table, Status column and row, and `_STILL_OPEN` matches open words. The module docstring
  now describes the gate this way and records what it read before.
* `packages/debate_core/tests/application/test_landscape_model_stage.py`: the gate tests described
  above.
* `packages/debate_cli/tests/test_landscape_command.py`: five `test_model_use_gate_*` tests, and the
  two existing refusal tests' row placed under its table.
* `plan_specs/v1/e32-argument-landscape/t37-model-use-gate-reads-the-open-questions-table.yaml`:
  Goal `Succeeded`.
* This report.

## Deviations from the spec

* **The synthetic cases are unchanged in meaning, not byte for byte.** The PM context asked for
  "the synthetic cases the existing tests use, unchanged". Those tests passed bare rows with no
  heading, and the gate now refuses a policy with no `## Open questions` heading, as the spec
  requires. So the same rows now sit under the heading and its table header (`under_the_heading` in
  the core file, `OPEN_QUESTIONS_TABLE` in the CLI file). The open row still refuses, the answered
  row still allows, and the no-row and empty-status rows still refuse.

## Decisions and assumptions

* **What counts as open.** The PM asked me to state what I chose and test the edges. A status
  refuses when it is empty or whitespace, or when it contains, case-insensitively and as a whole
  word, one of `open`, `opened`, `reopen`, `reopened`, `re-open` or `re-opened`. The policy's
  `**Open**` marker is one of these. A word is letters, digits and hyphens, so `open-questions`,
  `open-source`, `open-ended`, `OpenEv` and `OpenCaselist` are not `open`. Underscores and asterisks
  are not word characters, so `_open_` and `**Open**` do count. Where the rule could fail either
  way, it fails toward refusing: `no longer open` and `open question 6` inside a resolved status
  would refuse.
* **"Reopened" refuses.** The PM context lists "reopened" among the words today's substring match
  wrongly refuses. I read that as an example of substring matching. In the policy, though, a
  reopened question is an open question, and allowing a live run on one is the failure this task
  exists to stop. So I kept the refusal and wrote it as a deliberate rule rather than a side effect
  of substring matching. If the PM wants "reopened" allowed, it is a one-word change to
  `_STILL_OPEN`, plus moving three test cases. The question is below.
* **The Status column is read by its header**, not as the third cell. The PM asked that the row be
  read by heading and then by number. The column was the remaining read-by-position, and the policy
  could add a column before Status without anyone thinking of the gate. A table with no `Status`
  column refuses.
* **"The table that follows the heading"** is the first table between `## Open questions` and the
  next heading of any level. Text between the heading and the table (the real policy's intro
  paragraph) is skipped. The heading may be at any level from 1 to 6, matched case-insensitively,
  and must be exactly "Open questions". `## Open Questions to come` refuses.
* **The fixture's second table.** The PM context described the real policy's tables as a clause
  register, then "a scope table with a row 4". The real `## Scope` section has no table. The second
  table with a row 4 is `## Permitted uses` (row 4: parsing, hashing, fingerprinting), so that is
  what the fixture copies.
* **Escaped pipes.** A `\|` inside a cell is kept in that cell rather than splitting it. The real
  policy has none in its open-questions table today. This only stops a later edit from shifting the
  columns.

### Question for the PM (paste-ready)

```text
v1-e32-t37 — one choice to confirm: does a "Reopened" status refuse a live run?

The gate now matches "open" as a whole word (hyphens joined), so "open-questions",
"open-source", "OpenEv" no longer refuse. Your context listed "reopened" among the
words the old substring match wrongly refused. I kept "Reopened" (and "Re-opened",
"Opened") refusing, on purpose.

Options:
  A. Keep it: Reopened / Re-opened / Opened refuse. (Recommended)
  B. Allow them: only the word "open" (and the **Open** marker) refuses.

Why A: in the policy a reopened question is an open one; letting a live run through on
it is the exact failure this task closes, and refusing costs one policy edit to clear.
B is a one-word change to _STILL_OPEN plus moving three test cases.
```

### What else reads the policy, or another document, by row number

I searched every tracked Python, shell, workflow, TypeScript and JavaScript file for:

* code that names `caselist-data-use.md` or `docs/policies`;
* `startswith("|…")` table-row reads;
* `split("|")` cell splits;
* f-string row patterns;
* "open question N".

**Nothing else reads the policy, or any other document, by a bare row number.** `model_use_gate`
was the only code outside the tests that reads the data-use policy's content. Every other mention in
`packages/`, `scripts/` and `ops/` is a citation in a docstring or a message: rule 4, E34 gate 4,
clause 12 and so on, in prose, not parsed. Code that does parse Markdown tables:

* `tests/docs/test_annual_purge_runbook.py::first_cells` reads the policy's `## Retention` table by
  heading and matches its rows by their first-cell text, not by number. It is fine.
* `packages/debate_core/src/debate_core/application/landscape_scan.py::_section` walks back to a
  heading and a known header line in the report this code generated, not in a document.
* `packages/debate_core/tests/evidence/test_style_profile.py::_first_column_identifiers` reads the
  CardMirror evaluation note's table by its `### Nodes` / `### Marks` heading and its first column,
  and guards against an empty read.
* `tests/fixtures/test_team_samples_scrubbed.py`, `tests/scripts/test_analyze_team_formatting.py`
  and `packages/debate_core/tests/arguments/landscape/test_render.py` read tables that the code or
  manifest under test produces, by header or first cell.
* `site/src/lib/results.ts` and `publishing-policy.ts` only cite `website-publishing.md` in error
  messages. They do not read it.

Every other `| … |` f-string the search found writes a table (the landscape renderer, the seeding
and plan-text sheets, `compare_cloud_run.py`, the file-check report) and does not read one.

## Operator follow-ups

None. The affected set, which is over two minutes, runs in the pull request's `ci` check, as
agreement 10 provides. The operator's live Policy evaluation (e32-t07), started from a dev checkout
today, reads the policy from that checkout, so it gets this gate only after the merge. Version 1.20
passes the new gate, as the old one passed it.

## Follow-up work

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
