# Session report: v1-e08-t28-an-auto-cut-bundle-that-verifies-clean-end-to-end

| | |
|---|---|
| Task | `v1-e08-t28-an-auto-cut-bundle-that-verifies-clean-end-to-end` — An end-to-end auto-cut bundle of VERIFIED cards only verifies with exit 0 |
| Spec | [`plan_specs/v1/e08-research-workflows/t28-an-auto-cut-bundle-that-verifies-clean-end-to-end.yaml`](../../plan_specs/v1/e08-research-workflows/t28-an-auto-cut-bundle-that-verifies-clean-end-to-end.yaml) |
| Epic / release | `v1-e08-research-workflows` / `v1.4` |
| Branch | `task/v1-e08-t28-an-auto-cut-bundle-that-verifies-clean-end-to-end` |
| Session status | COMPLETE |

## Summary

The architecture's §11 criterion 2 now has its end-to-end scenario. `--auto-cut 2` on the e2e
test's recorded search ("health insurance", politics DA link, OpenAlex) fills its two cards from the
think-tank report (rank 3) and the open-access PDF (rank 4). It stops before the bannered press
release at rank 5, and `verify bundle.docx` exits 0 on the whole bundle. I measured every size from
1 to 3 with no code change first (table below). Every card auto-cut produced before the press
release is VERIFIED. The press release fails for its known `CITATION_UNVERIFIED` alone, and no
card carries `HIDDEN_CUT`, `MANUAL_EDIT` or any other reason. So the regression guard found
nothing, and N = 2 is the largest size before the press release, not one chosen to avoid a defect.
The new test is in `tests/integration/test_e2e_research.py`, slow like its neighbours. The existing
`--auto-cut 3` test and the snapshot-missing test are untouched.

## Measurement before any change

I ran a scratch test (`tests/integration/test_zz_scratch_measure.py`, never committed, deleted
after the run) through the suite's own fixtures (`cli`, `boundaries`, `cli_environment`). It ran
the same search with `--auto-cut` 1, 2, 3 and also 4, then `verify` on each bundle. It recorded
only statuses, reason codes, ranks, hosts and ids, never card text. The four runs took 3.03 s
(`-n 0`).

Report entries (the same in every run, up to where the run stopped):

| Rank | Result | Report status | Reasons |
|---|---|---|---|
| 1 | closed-stacks.example | SKIPPED (ROBOTS_DISALLOWED) | SOURCE_NOT_ACCESSIBLE |
| 2 | harborreview.example | SKIPPED (PAYWALLED) | SOURCE_NOT_ACCESSIBLE |
| 3 | harwell-institute.example (think-tank report) | VERIFIED | none |
| 4 | journal.synthetic-conservation.example (open-access PDF) | VERIFIED | none |
| 5 | fosw.example.gov (press release) | UNVERIFIED, bannered section | CITATION_UNVERIFIED |
| 6 | dailymeridian.example (news article) | VERIFIED | none |

Per size:

| `--auto-cut` | Search exit | Ranks reached | Cards (verify outcome, reason codes) | wanted / verified / unverified, stop | `verify` exit |
|---|---|---|---|---|---|
| 1 | 0 | 1–3 | rank 3 VERIFIED [] | 1 / 1 / 0, COMPLETE | 0 |
| 2 | 0 | 1–4 | rank 3 VERIFIED [], rank 4 VERIFIED [] | 2 / 2 / 0, COMPLETE | 0 |
| 3 | 0 | 1–6 | ranks 3, 4, 6 VERIFIED []; rank 5 UNVERIFIED [CITATION_UNVERIFIED] | 3 / 3 / 1, COMPLETE | 1 |
| 4 (extra) | 8 | 1–6 | as for 3 | 4 / 3 / 1, CANDIDATES_EXHAUSTED | 1 |

Size 3 is the first to reach the press release. Every card each run cut and rendered ran all ten
of the verifier's checks (`checks_run`, `evidence-verifier-v2`), and the only reason code anywhere is
the press release's `CITATION_UNVERIFIED`. Its detail reads "required citation fields not
verified: authors, title". For every size, `document.body_cards` equals the manifest's card count
and `unclaimed_body_cards` is empty. That is the guard (PM item 2): no card is UNVERIFIED for
`HIDDEN_CUT`, `MANUAL_EDIT` or for any reason other than the press release's banner.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| Clean bundle end to end (`an-auto-cut-bundle-that-verifies-clean-e`) | Done | Measured first; `--auto-cut 2` scenario added; red run, mutant, green. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: an e2e auto-cut bundle of VERIFIED cards only verifies with exit 0, every card checked against its snapshot | PASS | `test_search_auto_cut_2_stops_before_the_press_release_and_verify_passes_the_whole_bundle`. Its search exits 0 with wanted/verified/unverified 2/2/0 and COMPLETE. The report lists only the two skipped results and the two verifying pages, so the press release is never reached. The manifest's cards are all VERIFIED and the body holds no UNVERIFIED section or banner. For each card the test checks, as the existing test does, the raw snapshot blob against the cassette body, the offsets against t04's hand-written paragraphs, the stored text slice and `evidence_text`. `verify` then exits 0, envelope `status` ok and `error` null, totals 2/2/0. Each verdict is VERIFIED with no reason codes, has the manifest's card and snapshot ids, and its `checks_run` includes the six snapshot checks. `document.body_cards` is 2 with nothing unclaimed. |
| Node: "Clean bundle end to end tests pass" (`uv run pytest tests/integration/test_e2e_research.py -m "slow or not slow"`) | PASS | `3 passed in 3.52s`; after the lint commit, `3 passed in 3.25s` (bounded run, same file and markers). |

### Red run and mutant

* **Red run, expectation inverted.** I changed the new test's verify assertion to
  `== ExitCode.DOMAIN_FAILURE == 1` and ran it alone with `-n 0`: `1 failed in 0.63s`, at that line,
  `assert 0 == <ExitCode.DOMAIN_FAILURE: 1>`, with the envelope `status: ok` and two VERIFIED cards.
  It failed for its reason: verify exits 0 on this bundle. Restored with `git checkout HEAD --`.
* **Mutant: one UNVERIFIED card exits 0.** In `packages/debate_cli/src/debate_cli/commands/verify.py`,
  `if report.all_verified:` became `if report.all_verified or report.unverified == 1:`. Against the
  whole file with `-n 0`: `1 failed, 2 passed in 1.48s`. The existing
  `test_search_auto_cut_3_writes_three_verified_cards_and_a_bannered_unverified_one_and_verify_agrees`
  caught it at its exit assertion (line 221, got 0 where 1 was expected, envelope `status: ok` with
  `unverified: 1`). The new test passes under this mutant, as it must, since its bundle holds no
  UNVERIFIED card. The snapshot-missing test passes too: all four of its cards are UNVERIFIED, which
  the mutant does not touch. The two scenarios pin the two sides of verify's exit between them. The
  red run shows the new one fails when verify fails a clean bundle, and this mutant shows the old one
  fails when verify passes a bundle with one UNVERIFIED card. Restored with `git checkout HEAD --`,
  and the tree was clean afterwards.

### Checks before the report

| Command | Result |
|---|---|
| `uv run ruff format --check tests/integration/test_e2e_research.py` | `1 file already formatted` |
| `uv run ruff check tests/integration/test_e2e_research.py` | First run: one SIM300 (the subset comparison's order), fixed in its own commit; then `All checks passed!` |
| `uv run pyright` (whole project, as CI) | `0 errors, 0 warnings, 0 informations` (34 s) |
| `uv run lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `uv run scripts/validate_specs.py` | `OK: 685 files, 41 epics, 622 tasks, 22 releases` (warnings only, counted) |
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run --slow` | **Stopped at its 115-second limit** at about 94% of the fast tests of 59 affected files (load average ~5). Per agreement 10 this run goes to the pull request's `ci` check, which runs the same affected set and its slow tests; no hand-off. |
| Always-run list: `pytest tests/architecture/ tests/specs/ packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py -n auto -m "not slow and not live"` | `379 passed in 27.56s` |
| Changed test directory, slow tier: `pytest tests/integration/ -m "slow and not live" -n auto` | `12 passed in 7.95s` |

## Files changed

* `tests/integration/test_e2e_research.py`: the new scenario, and its constants
  `BEFORE_THE_PRESS_RELEASE` (the two expected cards, in rank order) and `SNAPSHOT_CHECKS` (the
  verifier's checks that read a card against its snapshot). Also a helper `auto_cut(cli, out,
  size)` and a paragraph in the module docstring.
* `plan_specs/v1/e08-research-workflows/t28-...yaml`: Goal phase Succeeded.
* This report.

## Deviations from the spec

None.

## Decisions and assumptions

* **The expectations are hand-written** (working agreement 6). The two cards, and their order, come
  from v1-e08-t26's report: think-tank report 3rd (0.2933) and open-access PDF 4th (0.2213), above
  the press release (0.1464). The evidence comes from t04's hand-written `expected.json` paragraphs,
  as in the existing test. The measurement only confirmed these values; it did not produce them.
* **The existing tests and `auto_cut_3` are byte for byte unchanged.** The new scenario has its
  own `auto_cut(cli, out, size)` helper instead of rewriting `auto_cut_3` to call it, so the diff
  touches no line of either existing test or its helper (`git diff origin/dev` shows additions only
  in that file). That leaves one duplicated argument list.
* **"Checked against its snapshot" gets two checks.** One is the test's own reading of each stored
  snapshot, as the existing test does. The other is an assertion that verify's `checks_run` for
  each card includes the six snapshot checks, so an exit 0 cannot come from a verifier that only
  read the citation.
* While confirming that the PM had not amended this spec on dev, I ran one `git fetch origin dev`.
  It was read-only. The spec diff against `origin/dev` is only the phase line.

## Operator follow-ups

None. The affected set ran over the two-minute bound, so it is left to the pull request's `ci`
check (agreement 10), with no hand-off.

## Follow-up work

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
