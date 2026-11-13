# Session report: v1-e08-t26-the-end-to-end-auto-cut-test-follows-the-multi-query-ranking

| | |
|---|---|
| Task | `v1-e08-t26-the-end-to-end-auto-cut-test-follows-the-multi-query-ranking` — The end-to-end auto-cut tests follow v1-e08-t24's ranking, so validate-dev is green again |
| Spec | [`plan_specs/v1/e08-research-workflows/t26-the-end-to-end-auto-cut-test-follows-the-multi-query-ranking.yaml`](../../plan_specs/v1/e08-research-workflows/t26-the-end-to-end-auto-cut-test-follows-the-multi-query-ranking.yaml) |
| Epic / release | `v1-e08-research-workflows` / `v1.4` |
| Branch | `task/v1-e08-t26-the-end-to-end-auto-cut-test-follows-the-multi-query-ranking` |
| Session status | PARTIAL: the work is done and the two tests pass; the Goal stays `InProgress` because four slow-tier tests could not run here (ac1's "slow tier passes in full") <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

* **The cause is t24's recency rule, working as intended.** The e2e search's seven politics DA link
  queries all ask 1,826 days and set no `--since`, so `recency_counts` says age does not count.
  * The news article (dailymeridian.example, the mammoth story) loses its large recency lead: 0.7492
    × 0.15 = 0.1124.
  * The government press release (fosw.example.gov, grants) has about seven times its term match
    (BM25 0.2365 against 0.0346), and that now decides.
  * Totals: news article 0.2380 → 0.1256, press release 0.1969 → 0.1464. So the press release is
    fifth and `--auto-cut 3` cuts it before the third VERIFIED card.

  The rule exists for exactly this: inside a window over a year, newer is not better, and relevance
  comes first. t24 recorded the same reorder on the same OpenAlex fixture in its CLI tests
  (its Deviations 3), and the PM accepted it on 2026-11-11.
* **The two tests now pin what the bundle holds:** three VERIFIED cards, then the press release's
  UNVERIFIED card in the bannered section with `CITATION_UNVERIFIED`. Every snapshot and offset
  check now covers all four cards, the bannered card included. The second test pins every card's
  `(status, reasons)`.
* **Look first at Deviations 1.** `verify bundle.docx` cannot exit 0 any more. The bundle holds the
  bannered card, and `verify` fails a bundle with any UNVERIFIED card. The first test now pins
  exit 1 and every card's verdict, and it is renamed because "verify passes the bundle" is no longer
  true. `tests/integration/ACCEPTANCE.md` follows. The whole-bundle exit 0 is no longer shown end to
  end; [Questions for the PM](#questions-for-the-pm) asks whether you want it back as a separate
  scenario.
* **The slow tier, run here in parts:** 56 of 60 passed. Of the other four:
  * three were skipped, because this Mac has no LibreOffice and no `public.ecr.aws/lambda/python:3.12`
    image (validate-dev's job installs and pulls them);
  * one planted-break case needs about 123 s as a single test, over the 115-s bound. I ran it in
    three bounded steps instead, and its own check says the break is caught.

  So the Goal stays `InProgress`, and validate-dev's run after the merge is the evidence for those
  four.

## The cause

**The search:** `search "health insurance" --argument politics-da --need link --providers openalex`,
over v1-e08-t06's six recorded OpenAlex works (`openalex_auto_cut.body.json`), clock 2026-10-21
12:00 UTC. It expands into the seven `politics-da/link/1`…`/7` templates, each with
`recency_days` 1826, and the filters set no `since`. Under t24's rule `recency_counts` therefore
answers no: the windows are over `counts_within_days` (365), and nothing exempts the search.

**How I measured it.** A scratch test, not committed, ran that search through the e2e harness
(`tests/integration/e2e_harness.py`'s boundaries and CLI) twice:
* once as dev has it;
* once with `federated_ranking.recency_counts` patched to answer yes, which is the ranking before
  t24 (recency always counted).

Each run read the JSON's `score` and `features` per result. The weights are bm25 0.45, recency
0.15, source_type 0.10, citations 0.10, open_access 0.05, provider_agreement 0.05 and
peer_reviewed 0.10 (always unknown).

| Result | BM25 | recency (before) | source_type | citations | total before t24 | total since t24 |
|---|---|---|---|---|---|---|
| closed-stacks.example (robots-disallowed) | 1.0000 | 0.5766 | 1.0 | 0.2817 | 0.6647 (1st) | 0.5782 (1st) |
| harborreview.example (paywalled) | 0.5902 | 0.8807 | 1.0 | 0.2593 | 0.5236 (2nd) | 0.3915 (2nd) |
| harwell-institute.example (think tank) | 0.5628 | 0.1669 | 0.4 | unknown | 0.3183 (3rd) | 0.2933 (3rd) |
| journal.synthetic-conservation.example (open-access PDF) | 0.2250 | 0.2415 | 1.0 | 0.2007 | 0.2575 (4th) | 0.2213 (4th) |
| dailymeridian.example (news article, 2026-09-14) | 0.0346 | 0.7492 | 1.0 | 0.1003 | **0.2380 (5th)** | **0.1256 (6th)** |
| fosw.example.gov (press release, 2026-06-02) | 0.2365 | 0.3363 | 0.4 | unknown | **0.1969 (6th)** | **0.1464 (5th)** |

open_access is 0 for every result and provider_agreement unknown (one provider). I checked the two
rows that swap by hand from the weights:
* **News article:** before t24, 0.45 × 0.0346 + 0.15 × 0.7492 + 0.10 × 1.0 + 0.10 × 0.1003 = 0.2380.
  Without the recency term it is 0.1256.
* **Press release:** before t24, 0.45 × 0.2365 + 0.15 × 0.3363 + 0.10 × 0.4 = 0.1969. Without the
  recency term it is 0.1464.
* **The recency values are the 90-day half-life:**
  * the news article is 37.5 days old, and 0.5^(37.5/90) = 0.7492;
  * the press release is 141.5 days old, and 0.5^(141.5/90) = 0.3363.

**Which signal moved it.** Only recency. No other feature changed between the two runs, and t24
changed nothing else (`git show 982cc154`: the rule, its config key and the rank stage handing over
the expansion). Recency had kept the news article 0.0411 ahead of the press release. Without it, the
press release's term-match lead (0.45 × 0.2019 = 0.0909) is larger than the article's source-type
and citation lead (0.06 + 0.0100 = 0.0700). So the press release is now 0.0208 ahead.

**Whether t24 means this order here: yes.**
* The ruled rule (t24's report, "The PM's ruling (2026-11-11) and the build", item 1(a)) is that
  recency counts as unknown when every expanded query's window is longer than
  `counts_within_days` and there is no `--since`. This search meets every condition. It is the
  politics DA link need that the rule's config comment names: "a link … may be five years old".
* With age gone, the order is the term match first, which is what the weight table says:
  "Relevance comes first".
* t24 saw the same swap on the same fixture body through `packages/debate_cli/tests`'
  `search --auto-cut` budget tests: "its government grant notice … now ranks above a newer
  magazine story. `--auto-cut 3` therefore cuts four results for three verified cards". It changed
  those four tests, and the PM accepted that as Deviations 3. t24's pull request's `ci` runs
  `not slow`, so the two e2e tests here, on the same search, were never run before the merge.

## What the bundle holds now, and what the tests pin

These were read from a scratch run of the same `--auto-cut 3`, not committed. The expected values
below are written by hand from the fixtures:
* the press release's card is UNVERIFIED with `CITATION_UNVERIFIED` because the page names no
  author (`packages/debate_cli/tests/fixtures/search/README.md`);
* its evidence is paragraph 2 of v1-e04-t04's hand-written `gov-press-release.expected.json`, at
  offsets 174–401: the length of paragraph 1 plus 2, then the length of paragraph 2;
* the banner strings are as `packages/debate_cli/tests/test_search_command.py` writes them by hand.

* **`report.json`:** the entries in rank order are SKIPPED closed-stacks (`ROBOTS_DISALLOWED`),
  SKIPPED harborreview (`PAYWALLED`), VERIFIED harwell-institute, VERIFIED
  journal.synthetic-conservation, UNVERIFIED fosw.example.gov (section `unverified`, reasons
  `CITATION_UNVERIFIED`), then VERIFIED dailymeridian. The totals are wanted 3, verified 3,
  unverified 1, stop reason `COMPLETE`.
* **The manifest, embedded and beside the DOCX:** four cards, VERIFIED ×3 then UNVERIFIED (the
  press release).
* **The DOCX body:** the block heading, the three VERIFIED cards, then
  "UNVERIFIED — not finished cards", the tag, and "UNVERIFIED — not a finished card:
  CITATION_UNVERIFIED" over the press release's cite and evidence.
* **`verify bundle.docx`:** exit 1, `UNVERIFIED`, "1 of 4 card(s) could not be verified". The three
  are VERIFIED with no reasons, and the press release is UNVERIFIED with `CITATION_UNVERIFIED`.
* **`verify` against a data directory that never stored the snapshots:** exit 1. The three cards
  give `SNAPSHOT_MISSING`, and the press release `CITATION_UNVERIFIED, SNAPSHOT_MISSING`, because
  verify checks the citation before it looks for the snapshot.

**`test_search_auto_cut_3_writes_three_verified_cards_and_a_bannered_unverified_one_and_verify_agrees`**
was `…_cut_from_their_snapshots_and_verify_passes_the_bundle`. Kept unchanged:
* the exit code;
* `(wanted, verified, stop_reason) == (3, 3, "COMPLETE")`;
* the SKIPPED map;
* the embedded manifest equal to the file;
* `body[0] == BLOCK`;
* for every card: the raw blob equal to its cassette's bytes, the offsets worked out by hand, the
  stored text format and text at the offsets, the evidence text, and the evidence in the body.

Changed or added:
* `report["unverified"] == 1`, and the report's UNVERIFIED entries are exactly
  `{press release: ("unverified", ["CITATION_UNVERIFIED"])}`;
* the manifest's statuses are `["VERIFIED"] * 3 + ["UNVERIFIED"]`, where they were `["VERIFIED"] * 3`;
* the section heading is in the body, and the banner is two paragraphs below it;
* the per-card checks run over all four cards. Each card's page is VERIFYING's or UNVERIFYING's, and
  a card is VERIFIED exactly when its page is one of VERIFYING's. A VERIFIED card's evidence is above
  the section, and the UNVERIFIED card's evidence below it;
* `cut_from` is VERIFYING's pages plus the press release;
* `verify` exits `DOMAIN_FAILURE` (1) with `UNVERIFIED`, where it was `OK`. Every card's
  `(card_id, status, reason_codes)` is pinned in manifest order: `(id, "VERIFIED", [])` for the
  first three, `(id, "UNVERIFIED", ["CITATION_UNVERIFIED"])` for the fourth. Before, it was
  `(id, "VERIFIED")` for each of three.

**`test_the_bundle_does_not_verify_where_its_snapshots_are_not_stored`** keeps its exit codes, its
`UNVERIFIED` and its `SNAPSHOT_MISSING` in the printed table. Its verdict list is now
`[("UNVERIFIED", ["SNAPSHOT_MISSING"])] * 3 + [("UNVERIFIED", ["CITATION_UNVERIFIED", "SNAPSHOT_MISSING"])]`,
an exact list as before, and it adds `CITATION_UNVERIFIED` in the printed table.

**The tests fail for their reasons.** Each mutant was edited into the worktree, run with
`hard_stop.py 115 … pytest tests/integration/test_e2e_research.py -m "slow or not slow" -n 0
--tb=line`, and restored with `git checkout HEAD --` (the test changes were committed first, as
`f566ea3`). Each caught both tests at assertions, and nothing crashed.

| Mutant | First failing assertion |
|---|---|
| Age always counts (`recency_counts` returns True: the ranking before t24) | test 1 line 129 `report["unverified"] == 1` (0 == 1); test 2 line 207, the verdict list (three, not four) |
| The batch report's `unverified` is always empty | the same two lines |
| The bundle's DOCX and manifest leave the UNVERIFIED cards out; the report keeps them | test 1 line 144, the manifest statuses (three VERIFIED, no UNVERIFIED); test 2 line 207 |

Before the change, dev's tests failed exactly as the PM's run 43351384277 did: test 1 at line 121,
"Left contains one more item: 'UNVERIFIED'", and test 2 at line 170,
"Left contains one more item: ('UNVERIFIED', ['CITATION_UNVERIFIED', 'SNAPSHOT_MISSING'])".

## The slow tier, run here

The marker is validate-dev's: `-m "slow and not live and not eval and not operator_data"`. It
collects 60 tests in 11 files (`--collect-only`, 96 s at load 15). CI's run was 58 passed and 2
failed: 60.

Every part ran as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest <paths> -m
"slow and not live and not eval and not operator_data" -p no:cacheprovider --no-cov -rfEs -q`, with
xdist from `addopts`. Load was between 3 and 15 (v1-e39-t18's index build was running), so the times
are slow.

| Part | Paths | Result |
|---|---|---|
| 1 | `tests/integration` (the three e2e files) | 11 passed in 5.6 s |
| 2 | the five `packages/debate_core/tests` slow files (`test_evidence_search_scale.py`, `test_docx_renderer.py`, `test_structural_fixtures.py`, `test_search_index_reader_sqlite_features.py`, `test_search_index_sqlite_features.py`) | 2 passed, 3 skipped in 82.8 s |
| 3 | `packages/debate_api/tests/browser` | 30 passed in 29.8 s |
| 4a | `tests/scripts/test_affected_tests_planted_breaks.py`, cases 1–7 by node id | 7 passed in 70.3 s |
| 4b | the same file, cases 8–11 | 4 passed in 42.6 s |
| 4c | the same file, cases 13–14 (the import-linter rename, and the break no test reaches) | 2 passed in 40.3 s |
| 4d | the same file, case 12 alone ("a lazily imported integration names the wrong place, read through a command's factory") | stopped at its 115-s limit four times: within cases 8–14, within 12–14, and alone twice (the second at load 3.6) |

**Totals: 56 passed, 3 skipped, 1 over the bound, 0 failed.**

**The three skips** are environment gates:
* `test_docx_renderer.py:1000`: "LibreOffice (soffice) is not installed here; validate-dev's slow
  job installs it";
* `test_search_index_sqlite_features.py:235` and `test_search_index_reader_sqlite_features.py:503`:
  "public.ecr.aws/lambda/python:3.12 is not on this machine".

Installing LibreOffice or pulling the image is an install or a network fetch, so it is not this
session's, and the PM's brief gives the operator no command. None of the three reaches the ranking,
the batch cut or the e2e file.

**Case 12 in bounded steps.** I used a scratch script, not committed, that loads the test module by
path and uses its own `PLANTED_BREAKS`, `changed_names`, `names_any`, `nearest_tests`, `SelectedRun`
and `how_caught`. It runs the test's own commands one step at a time, each under `hard_stop.py 115`:
1. **Shared clone of HEAD and the planted commit:** 2.0 s.
2. **The clone's `affected_tests.py --diff HEAD --explain`:** 19.1 s. It chose 93 of 754 test files,
   78 traced to `version_directories.py`, and the nearest 10 ran.
3. **The test's pytest over those 10 (`-n 0 -x`, `PYTHONPATH` the clone's sources):** 101.7 s,
   "1 failed, 128 passed". The failure was
   `test_caselist_retire.py::test_the_dry_run_lists_each_directory_with_its_standing_and_changes_nothing`.
4. **`how_caught`:** "a selected test failed".

So the case passes its check, but as one test it needs about 123 s here, more than one 115-s run.
It plants its break in `version_directories.py` and tests `affected_tests.py`. Neither reaches this
task's change.

**The e2e file under both markers:**
`hard_stop.py 115 uv run pytest tests/integration/test_e2e_research.py -m "slow or not slow"` gave
2 passed in 3.97 s. That is the plan node's own command.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `the-end-to-end-auto-cut-test-follows-the` (End-to-end follows the ranking) | Done | The cause is named and the order is intended; the two tests pin the bundle as it is; commit `f566ea3` |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1, part 1: the cause is named | PASS | [The cause](#the-cause): t24's recency rule (every link query asks 1,826 days, no `--since`). News article 0.2380 → 0.1256, press release 0.1969 → 0.1464. Intended by t24's ruled rule. |
| ac1, part 2: the two tests pass against t24's ranking, with the bannered UNVERIFIED card pinned | PASS | `hard_stop.py 115 … pytest tests/integration/test_e2e_research.py -m "slow or not slow" -n 0` → 2 passed in 1.01 s. Before the change, on this branch's start: 2 failed, the same two assertions as CI. Three mutants each fail both tests at assertions. |
| ac1, part 3: the slow tier passes in full | NOT RUN in full | 56 passed, 0 failed ([The slow tier, run here](#the-slow-tier-run-here)). Three tests were skipped: no LibreOffice, no Lambda image on this Mac. One planted-break case needs about 123 s, over the 115-s bound; run in bounded steps it was caught. The full proof is validate-dev's slow job on dev after the merge. |
| Node: End-to-end follows the ranking tests pass (`uv run pytest tests/integration/test_e2e_research.py -m "slow or not slow"`) | PASS | `hard_stop.py 115 uv run pytest tests/integration/test_e2e_research.py -m "slow or not slow"` → 2 passed in 3.97 s |

**Checks before the report:**
* **`hard_stop.py 115 uv run scripts/affected_tests.py --run`:** 58 of 754 test files, chosen in
  17.4 s from 4 changed files. Result: "2447 passed in 94.30s", "pytest exited 0 after 96 s".
  hard_stop's 115-s stop came after that line, while the script was exiting (17 s of selection plus
  96 s).
* **`ruff format --check .`:** 2089 files already formatted. **`ruff check .`:** All checks passed.
* **`lint-imports`:** 20 kept, 0 broken.
* **`pyright`** (whole project, as CI runs it): 0 errors, 0 warnings, in 36 s.
* **`uv run scripts/validate_specs.py`:** "OK: 678 files, 41 epics, 615 tasks, 22 releases", with
  warnings about other tasks only. The Goal stays `InProgress`.
* **`scripts/check_command_blocks.py --base origin/dev`:** "OK: no `#` comments in 703 shell code
  blocks in 259 Markdown files (1 session reports changed since origin/dev)".

## Files changed

* `tests/integration/test_e2e_research.py`:
  * the module docstring says which pages are cut since t24, and why;
  * `PRESS_RELEASE`, `UNVERIFYING`, `UNVERIFIED_SECTION` and `PRESS_RELEASE_BANNER`, written by hand
    from the fixtures;
  * the first test is renamed and pins the four cards and verify's verdicts;
  * the second pins the bannered card's two reasons.
* `tests/integration/ACCEPTANCE.md`: the renamed test in its four rows; criterion 2's row says what
  the bundle and `verify` now give; criterion 3's rows cover the bannered card.
* `plan_specs/v1/e08-research-workflows/t26-…yaml`: the Goal is `InProgress`, from the start
  commit, and unchanged since.
* This report.

Nothing in `debate_core.application` or `packages/debate_core/tests` changed: the ranking is as t24
built it.

## Deviations from the spec

1. **One assertion could not be kept: `verify bundle.docx` exiting 0.**
   * **Why:** the spec says to keep every other assertion. But the bundle now holds the bannered
     UNVERIFIED card, which batch_cut_service's rule keeps there (the spec forbids changing it), and
     `verify` fails a bundle that holds any UNVERIFIED card.
   * **What the test does instead:** it pins exit 1 with `UNVERIFIED`, and every card's `(card_id,
     status, reason_codes)` in order. That is three VERIFIED with no reasons, so the three are still
     verified end to end, and the bannered one with `CITATION_UNVERIFIED`.
   * **The name:** the test is renamed, because "verify passes the bundle" is no longer true. Its
     docstring gives the old name. The two `ACCEPTANCE.md` rows that said "`verify bundle.docx`
     exit 0" now say what verify gives.
   * **What is lost:** an end-to-end exit 0 for a whole auto-cut bundle. Each single card's verify
     pass is still shown by `failures::test_cut_writes_each_kind_of_sources_card_from_its_snapshot_and_verify_agrees`.
2. **The slow tier was not shown passing in full** (ac1's last clause, and the brief's "all
   passing"). Three tests skip on this Mac for want of LibreOffice and the Lambda image. One
   planted-break case cannot finish inside one 115-s run here; in bounded steps it passes its own
   check. Hence the Goal stays `InProgress`.
3. **`tests/integration/ACCEPTANCE.md` changed.** It is in `tests/integration`, inside the
   packages list, and it names the renamed test. I note it only because the spec names the two test
   functions, not the map.

## Decisions and assumptions

* **"Before t24" was measured by patching `recency_counts` to answer yes**, not by checking out
  7b81d85e. t24 changed nothing else in the ranking (its diff: the rule, the config key and the
  stage passing the expansion), so this is the earlier ranking on today's code and fixtures. Its
  order matches what the PM's bisect describes for 7b81d85e: the news article ahead of the press
  release.
* **The first test checks the bannered card as strictly as the verified ones.** That covers its
  raw snapshot bytes, its offsets from the hand-written sample, the stored text and its evidence in
  the body. Evidence integrity does not depend on the card's status, and the fixture made those
  values available.
* **The verify verdicts are compared in manifest order**, which the test already pins as VERIFIED ×3
  then UNVERIFIED. So `cards[:3]` and `cards[3]` are those cards by an earlier assertion, not by
  assumption.
* **No test was added.** Whether a clean bundle's exit 0 deserves its own e2e scenario is the PM's
  call (Questions 1).

## Questions for the PM

Paste-ready for the PM:

> **v1-e08-t26 asks two things.**
>
> 1. **The whole-bundle `verify` exit 0 is no longer shown end to end.** Since t24 the `--auto-cut 3`
>    bundle holds the bannered press release card, so `verify bundle.docx` exits 1. It names that
>    card's `CITATION_UNVERIFIED` and passes the other three, and the test pins exactly that. Options:
>    (a) accept it: single-card verify passes are still covered by `failures::test_cut_writes_each_kind_of_sources_card_from_its_snapshot_and_verify_agrees`;
>    (b) file a follow-up for an e2e scenario whose bundle holds only VERIFIED cards and verifies with
>    exit 0, for example a smaller `--auto-cut` on the same search. I have not run that variant, so I
>    have no figures for it.
>    **Recommendation: (a) now, (b) as a p3 follow-up if §11's criterion 2 should keep a bundle-level
>    exit 0.** Why: this task is what validate-dev waits on, and (b) adds a scenario rather than
>    fixing one.
> 2. **The Goal stays `InProgress`.** 56 of the 60 slow tests passed here, and none failed. Three
>    skip on the operator's Mac (no LibreOffice, no `public.ecr.aws/lambda/python:3.12`). One
>    planted-break case (case 12, `version_directories.py`) needs about 123 s as one test, over the
>    115-s bound; in bounded steps it is caught. Options:
>    (a) merge `--partial`, and set `Succeeded` when validate-dev's slow job is green on the merge;
>    (b) rule that this evidence closes ac1 and set `Succeeded` in review.
>    **Recommendation: (a).** Why: validate-dev is the only place all 60 run, and its green is the
>    point of the task.

## Operator follow-ups

None.

## Follow-up work

* **For the PM, as the brief asks: should the pull request's `ci` run the slow tests its affected
  set reaches?** t24's change reached `tests/integration/test_e2e_research.py`, an imports-reachable
  slow file, and no pull request ran it, so dev's validate-dev was the first to see the break.
  Both e2e tests take about 2–6 s here. Whether every slow file an affected set reaches fits the PR
  budget is not measured: the planted-break and Chromium files are the heavy ones.
* **The slow tier cannot be run in full by a session under the 115-s bound.** Planted-break case 12
  needs about 123 s on its own at load 3–10 on the operator's Mac. A future "run the slow tier
  yourself" brief needs either a longer bound for that file or a hand-off. That belongs to E41
  (upkeep), or to whoever owns `test_affected_tests_planted_breaks.py` (v1-e01-t40).
* **t24's CLI-test deviation was the early warning.** t24's Deviations 3 described this exact
  reorder on the same fixture, but nothing pointed at the slow e2e tests over the same search. If
  (b) of the first follow-up is not taken, a session note on that would do: "when a ranking change
  moves a fixture search, grep `tests/integration` for the same query".

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-12

**Notes:**

Accepted for a partial merge (`scripts/task pr --partial`). The Goal stays `InProgress` until
validate-dev's slow job is green on dev after the merge, and the PM then records it `Succeeded`.

* **The cause is named exactly and is intended.** It is t24's recency rule: every politics DA link
  query asks 1,826 days with no `--since`, so age counts as unknown. The press release's term-match
  lead then beats the news article's source-type and citation lead. The arithmetic is checked by hand
  against the weights and the 90-day half-life, and no other feature moved. t24's own Deviations 3
  recorded the same swap on the same fixture, and the PM accepted it on 2026-11-11. So this is a test
  that never ran before the merge, not a ranking bug, and no stop was owed.
* **The tests are stronger, not weaker.**
  * Every snapshot, offset and evidence check now covers all four cards, the bannered one included.
  * The UNVERIFIED card is pinned with its section and its reason.
  * The second test's list is exact.
  * The three mutants (the old ranking, an empty `unverified`, and the card left out of the bundle)
    each fail both tests at assertions.
* **Deviation 1 is accepted.** `verify` exiting 0 on the whole bundle cannot hold while the bundle
  carries a bannered card, which is batch_cut_service's rule. Pinning exit 1 with every card's verdict
  is the honest replacement.
  * **Question 1: (a) now, and (b) as a p3 follow-up in the next PM batch.** The follow-up adds an
    e2e scenario whose bundle holds only VERIFIED cards and verifies with exit 0, so §11's criterion 2
    keeps a bundle-level exit 0. A smaller `--auto-cut` on the same search, which stops before the
    press release, is the likely shape; it is unmeasured, so it is measured first.
* **Deviation 2, Question 2: (a).** 56 of 60 slow tests passed here and none failed. The three skips
  are environment gates (LibreOffice, the Lambda image), and the one over the bound was shown caught in
  bounded steps. validate-dev is the only place all 60 run, so its green on dev closes ac1.
* **Deviation 3: accepted.** ACCEPTANCE.md follows the renamed test.
* **Follow-ups, into the next PM batch:**
  * whether a PR's `ci` should run the slow files its affected set reaches: an E41 task at p2, since
    this break went unseen for a day;
  * a longer bound, or a hand-off, for the planted-break file in a session's slow-tier run: a note on
    that task;
  * the session note to grep `tests/integration` when a ranking change moves a fixture search: added
    to the same E41 task's description.

`scripts/task pr --partial`
