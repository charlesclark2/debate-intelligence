# Session report: v1-e32-t22-scenario-vocabulary

| | |
|---|---|
| Task | `v1-e32-t22-scenario-vocabulary` — A coach-edited scenario vocabulary per DA and advantage |
| Spec | [`plan_specs/v1/e32-argument-landscape/t22-scenario-vocabulary.yaml`](../../plan_specs/v1/e32-argument-landscape/t22-scenario-vocabulary.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t22-scenario-vocabulary` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**Complete. Every criterion passed, and the Goal is `Succeeded`.** The coach's edit is committed on its
own (`0fb8dc9`). The operator's refill and dry run under 1.4.0 read it
([the real store](#the-real-store-under-the-coachs-lists-2026-10-26)): every count landed where the
report said it would, and the scan found no hit in the scenario sections.

**What is built (ac1, PASS):**
* **The list.** A DA or advantage in the taxonomy may carry `scenarios` (each a `name` and its `forms`)
  and `not_scenarios`. The forms are written in normalized words, and t14's words are matched against
  them whole.
* **A position with a list** shows the coach's names and nothing else:
  * merged forms are one name, and their teams are counted together;
  * a dropped form names nothing, and a named heading of one is no scenario heading;
  * withholding by caselist words still applies, to the name that would be shown.
* **A position without a list** keeps t14's rule exactly.
* **Taxonomy 1.4.0** (from 1.3.0) holds the seed, and the released-ids check passes. On a copy with
  1.3.0 locked, the check refuses this seed at 1.3.0.

**How it was checked:**
* The goldens were written by hand and committed before any code (`a3d8cd2`), and matched on the first
  run.
* The tests ran red against a skeleton that changes nothing: 38 failed (`f3da863`).
* All 20 mutants were caught, the PM's three among them.

**The seed** is t14's table: 31 names that two or more teams use, on 11 DAs and advantages. Each name
is its own one form, with its teams and documents as a comment. A read-only screen against 5,126
hspolicy26 disclosures found none of the 31 holding a school, team code or tournament word.

**Before the coach's edit, the seed shows exactly t14's names.** Every name it lists is one t14
already showed, and it drops nothing. This is by construction, not measured: the real store needs the
refill first. One count does move: the names withheld. The Midterms DA's 2 and the Disease
advantage's 1 are words their lists do not hold, so they are no longer names those positions could
show. Only the Stagnation advantage's 1, which has no list, is still counted. The count goes from DA 2
/ advantage 2 to DA 0 / advantage 1 (question 3).

**The PM's rulings of 2026-10-26** ([below](#the-pms-rulings-2026-10-26)) are applied:
* a listed position shows only the coach's names, as built;
* the dry run now counts, per kind, the words two or more teams use under a listed position that its
  list does not hold, never printing them;
* a scenario name may carry capitals after its first word;
* the two Deviations stand, and the PM adds the packages in the next batch.

The new tests were run red first (6 failed, `2268e60`), and 7 more mutants were all caught.

## The PM's rulings (2026-10-26)

On [the questions](#questions-for-the-pm), as the PM wrote them:

1. **(a), as built.** A listed position shows only the coach's names, and a drop-only list shows
   nothing. **Add the follow-up count now, in this task:** one counts-only line per kind in
   `landscape_dry_run_by_section.py`, with the words two or more teams use as a scenario that no listed
   position's list holds (counted, never printed). Test it red first.
2. **Packages: yes.** The PM adds `debate_core.domain`, `scripts` and `tests/scripts` with a ruling
   comment in the next batch. Recorded under Deviations.
3. **FYIs accepted, with one change:** a scenario name may carry capitals after its first word (proper
   nouns such as `War with China`), and is still refused when it has a team-code shape or a school
   word. Update the `tests/config` check, its refusing cases and the guide.

**What changed for them:**
* **The count** (`2268e60` red, `fd22d2b` green). `ChainCoverage` gains `unlisted_words` and
  `unlisted_words_withheld`. Per listed position, these are t14's words, with its dropped forms
  skipped, that the list does not hold and two or more teams use, and how many of them hold a caselist
  word. Positions without a list count nothing.
  * The dry run prints, per kind, `Scenario words no list holds, <kind>: N that two or more teams use
    under a position with a list, M of them holding a caselist word.`
  * report.md and the CSVs are unchanged.
* **Capitals.** The scenario-name check in `tests/config` drops sentence case and keeps the team-code
  shapes and school words; labels keep sentence case.
  * The refusing case "a name in a scenario name" is gone.
  * New refusing case: "a school in a capitalized scenario name" (`Crash at Sample Academy`, refused
    for `academy` alone).
  * New passing names: `War with China`, `Golden Dome arms race`.
  * The guide says both changes.

**The PM's ruling on the coach's read (2026-10-26): proceed with the one-level edit.** The coach edits
the seed at one level. For the Midterms DA, the impacts are named and the branch words (`dems win`,
`republicans win`) go to `not_scenarios`. For the Economy DA, `decline` and `econ` go to
`not_scenarios`. The counts for branches and mechanisms become a new E32 task ([Follow-up
work](#follow-up-work)).

## The real store under the coach's lists (2026-10-26)

**What ran:** the operator's refill and dry run ([Operator follow-ups](#operator-follow-ups) 2 and 3),
on `2b24d43`, after [the sync](#the-sync-onto-dev-2026-10-26).
* The guards passed; nothing was published.
* The classification cache: 107,187 keys, 100% hits. The first, refused run had already written it
  under 1.4.0.
* The plan-text cache: 1,770 sources cached, 0 parsed. The analytic texts: 3,825 parsed, cache
  written, 376.2 s. The dry run: 70.9 s.

| Dry run line | Expected in this report | Measured |
|---|---|---|
| Taxonomy and writes | 1.4.0, nothing written | `taxonomy 1.4.0: nothing written; 7 files planned` |
| Impact rows, advantage / DA | above zero (t14: 43 / 44) | 43 / 44 |
| Rows with a scenario, advantage / DA | moved by the edit (t14: 0 / 13) | **0 / 9** |
| Names withheld, advantage / DA | 1 / 0 | **1 / 0** |
| Documents with no scenario heading and no role label | can only rise from 676 of 1,164 and 251 of 662 | **676 of 1,164; 253 of 662** |
| Scenario words no list holds, advantage / DA | at least 1 / 2, each holding a caselist word | **1 (1 holding) / 2 (2 holding)** |
| The scan in report.md's impact-card sections | no hit | **no hit.** 9 hits, all accepted earlier: 1 in a plank table, 8 in `top_cards.csv` |

**What the coach's edit moved:**
* **DA rows with a scenario fell from 13 to 9.** The dropped names (the Economy DA's `decline` and
  `econ`, the Medical devices DA's two, the Midterms DA's answers and branch words) no longer name a
  row. The merges keep `golden dome` on its rows.
* **Two more DA documents have no scenario heading** (251 to 253): their only scenario heading was a
  named heading the coach dropped.
* **The words no list holds** are exactly the 3 t14 withheld under the Midterms DA and the Disease
  advantage, each holding a caselist word. Nothing the coach dropped surfaced new words.

The dry run prints counts and ids only, so which rows the 9 are is not on record here. It shows in
report.md at the republish.

## The sync onto dev (2026-10-26)

**Why.** The operator's refill stopped at its second step with `Refused: line 1 of the hspolicy26
plan-text cache is not a reading: 1 errors`. The classification step had finished under 1.4.0:
3,825 sources, 63,494 cards counted, 41.2 s.
* v1-e32-t24 merged into `dev` (`b3273fb`) while this task was open, and it adds
  `transition_paragraphs` to a plan-text reading.
* At 00:56 a refill run with t24's code rewrote the shared cache,
  `~/.debate-research/dev/landscape/plan_texts/hspolicy26.jsonl` (1,770 lines), in that form.
* This branch's reader refuses a field it does not know, so it stopped at line 1. It parsed nothing
  and wrote nothing.
* I read only the cache's keys and times to find this, never its contents.

**The sync.** The operator ran `scripts/task sync v1-e32-t22-scenario-vocabulary`. It rebased the
branch onto `ad7f5a1` (dev with t24 and v1-e04-t06); the branch was never pushed, so nothing was
pushed.
* Two commits conflicted, in `scripts/landscape_dry_run_by_section.py` and its test. t24 added a "Plans
  under Thus" line, its test and an import at the same places as this task's scenario lines.
* Each conflict kept both sides, t24's first.
* The red commit (`2268e60`) still fails its two dry-run tests, for the same reason as before.
* Every commit id in this report is the rebased one. The task started from `af7052e` on dev.

**After it:**
* `uv sync --offline --all-packages` (dev added the CLI's `extraction` extra, already installed);
* `scripts/make_landscape_fixture.py` reproduces the committed fixtures byte for byte;
* the affected set is now 258 of 522 files, still over two minutes;
* the changed directories and the always-run list: **4,370 passed in 80.90s**, at load average 19.0;
* ruff format and check, pyright bare (0 errors), lint-imports (18 kept), the handler check (66),
  validate_specs and the command-block check are all clean.

**A hand-off I should have made.** To compare with dev I ran `git fetch` in the session. It only
updated the local `origin/dev` ref, but it is a network call, which the PM's rule of 2026-10-22 gives
to the operator even when it is read-only.

## The coach's edit, as committed (2026-10-26)

`0fb8dc9`, the coach's edit alone, at one level as the PM ruled:
* **Midterms DA.**
  * Merged: `golden dome` (`golden dome`, `dome`, `dome arms racing`) and `warming` (`warming`, and two
    forms the coach added, `global warming` and `climate change`).
  * Kept: `iran`, `polycrisis`, `china coop`, `corruption`, `democracy`.
  * Dropped: `dems win`, `dem win crushes trumpism`, `trump`, `trump steals`, `too early`,
    `other issues`.
  * `republicans win`, named in the ruling, is not dropped. It was never in the seed (fewer than two
    teams used it). If teams use it, the dry run's unlisted-words line counts it.
* **Economy DA.** `decline` and `econ` are dropped. The coach's first save edited the Economy
  advantage instead. Asked, the coach chose to keep that edit and have the session also move the DA's
  two, so that one change in the commit is the session's, at the coach's word.
* **Economy advantage.** `costs rising` and `contention the advantage` are dropped; `debt` is kept.
* **Medical devices DA.** Both names are dropped (`augmentation`, `augmentation innovation key`).
* **Disease advantage.** `clog` gains the form `court clog`; `court curbing` is kept.
* **Unchanged:** IRS, Pharma, Capital flight and Court clog DAs; Costs and Inequality advantages.

**In all:** 11 lists, 18 scenarios, 23 forms, 12 dropped. All names stay lowercase.

**Checks:**
* `tests/config`: 77 passed, before and after the Economy DA's move.
* A read-only screen of all 53 names and forms against 5,126 hspolicy26 disclosures: 0 hold a school,
  team code or tournament word.
* The landscape smoke and CLI tests, `tests/config` and the dry run's test: 124 passed.
* Some count comments no longer line up, or describe the seed's entry rather than the merged one. They
  are comments, read by nobody's code, and were committed as the coach left them.

## The coach's edit (step 3), as briefed

**The file**, in this worktree:

`~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t22-scenario-vocabulary/config/landscape/taxonomies/policy-2026-27-nhi.yaml`

The lists sit under each position that has one: the Midterms, IRS, Medical devices, Pharma, Economy,
Capital flight and Court clog DAs, and the Economy, Disease, Costs and Inequality advantages. Each entry
reads `- {name: dome, forms: [dome]}`, with its teams and documents beside it as a comment. The
[guide's "Your scenario lists"](../guides/landscape-taxonomy.md#your-scenario-lists) says the same at
more length.

**The coach may:**
* **Merge** forms that are one scenario under one name, in one entry. For example
  `- {name: Golden dome, forms: [dome, golden dome]}`, deleting the other entry. Their teams are then
  counted together.
* **Rename** a scenario by changing its `name`, in the words a debater uses. Capitals after the first
  word are allowed for proper nouns (`War with China`, by the PM's ruling of 2026-10-26).
* **Mark a non-scenario to drop:** move its form from `scenarios` to that position's `not_scenarios`
  list, for example `not_scenarios: [too early]`. On hspolicy26, t14's counts suggested `too early`,
  `trump steals` and `other issues` under the Midterms DA, and most of the advantages' names (`clog`,
  `dedev`, `court curbing`, `isolationism`), are answers rather than scenarios. That call is the coach's.
* Leave or delete the count comments: they are for reading only.

**The coach may not:**
* write a school, a team code or a tournament's word anywhere, in a name or a form;
* touch an `id`, or anything outside `scenarios` and `not_scenarios`: labels, aliases, kinds, sides,
  `taxonomy_version` (1.4.0 is not released, so this edit needs no bump);
* list one form twice on a position, in either list, or give two scenarios of one position the same
  name. `tests/config` refuses both.

**Then** the edit comes back to this branch. The session runs `tests/config`, commits the edit alone,
runs the affected tests, and gives the operator the refill and dry-run blocks drafted
[below](#operator-follow-ups).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| scenario-vocabulary | Done | In order:<br>1. hand-written fixture and goldens (`a3d8cd2`);<br>2. tests, red against a skeleton (`f3da863`);<br>3. the rule, the domain model and the service (`b5b379d`);<br>4. 20 mutants;<br>5. the seed at 1.4.0, the dry run's scenario lines and the guide (`ca3adea`);<br>6. the PM's rulings: the unlisted-words count and capitals in names, red (`2268e60`), then green (`fd22d2b`), then 7 mutants.<br>7. the coach's edit, committed alone (`0fb8dc9`).<br>8. the sync onto `ad7f5a1`, the operator's refill and dry run under 1.4.0 |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a position's scenario list merges heading forms under one name and drops listed non-scenarios; positions without a list keep t14's rule, matching hand-written golden files; the taxonomy bump passes the released-ids check; tests shown failing first | PASS | **Goldens:** `tests/fixtures/landscape/scenario_vocabulary/` (`a3d8cd2`, before any code): `test_the_impact_sections_match_the_hand_written_golden`, `test_impact_cards_csv_matches_the_hand_written_golden` and `test_the_rest_of_report_md_is_the_report_without_a_list` pass. **Merged:** `Rising costs` (`drug prices` + `debt crisis`, one team each) shows on ranks 2 and 3. **Dropped:** `economic collapse` names nothing, and `a5` becomes a document with no scenario heading (2 of 6). **Without a list:** the Spending DA keeps `recession` and 1 withheld. **The lock:** `test_the_committed_taxonomies_keep_every_released_id` passes at 1.4.0. The `scenario-list-added` and `form-dropped-as-no-scenario` cases are refused unbumped and pass bumped. On a scratch copy with 1.3.0 locked, the seed at 1.3.0 is refused (`changed-without-bump`) and at 1.4.0 passes. **Red:** [below](#checks-shown-failing-for-their-reason) |
| ac2: the coach's edited seed for policy-2026-27-nhi is committed and the next report uses it (operator for the coach's edit) | PASS | **Committed:** `0fb8dc9` ([the edit](#the-coachs-edit-as-committed-2026-10-26)). **The next report uses it:** the operator's dry run under 1.4.0 ([the real store](#the-real-store-under-the-coachs-lists-2026-10-26)). DA rows with a scenario 9, against t14's 13. Names withheld 1 and 0, and 1 and 2 words no list holds, as predicted from the lists. No scan hit in the scenario sections. The report is local: the republish follows the cloud cutover, by the PM's order |
| scenario-vocabulary: `uv run pytest packages/debate_core/tests/arguments/landscape` | PASS | **877 passed in 5.32s** (load average 8.1) |

### Checks shown failing for their reason

**The goldens before the code.** They were committed in `a3d8cd2`, worked out by hand in the fixture's
README from t14's README and goldens: no list, then the one list on the Costs advantage.
* The Costs advantage's three rows. Rank 1 shows no scenario (its only labelled copy is under
  `scenario 1 economic collapse`, which is dropped). Ranks 2 and 3 show `Rising costs` (`KK` and `VV`).
* The kind's "Impact rows: 3; with a scenario two or more teams name: 2".
* "Advantage documents with no scenario heading and no role label: 2 of 6".
* The DA section unchanged.
* The CSV's three `scenario` cells.

The base golden's How-to-read bullet was edited by hand in the same commit.

**Red against a skeleton** (`f3da863`). The skeleton has the fields, `Scenario`, `card_scenario`'s
`not_scenarios` parameter and `scenario_name`, and they do nothing. The run covered the domain, rule,
vocabulary and render tests and `tests/config`: **38 failed, 341 passed**. (The commit message says 13
rule and 8 service failures. The counts are 12 and 9.)

| Failing, grouped by reason | Count |
|---|---|
| Domain: a list loads but `has_scenario_list` is false (2); a CP, aff, K or T list accepted (8); a form twice accepted (4); a name twice in another case accepted (1); a scenario with no forms accepted (1) | 16 |
| Rule: a dropped form still names or heads (7); a listed form not given the coach's name, or unlisted words shown (3); a list of drops only shows words (1); a coach's capitalized name not withheld (1) | 12 |
| Service and goldens: both goldens, the rest of report.md (its bullet), and six one-list cases | 9 |
| t14's `report.md` golden: the How-to-read bullet | 1 |

**Already passing on the skeleton, and why:**
* Valid input accepted: `test_the_same_form_on_two_positions_is_allowed`.
* Refusals pydantic's types already make: no name, missing forms, a capital or two spaces in a form, an
  unknown key, an unnormalized dropped form.
* Must-not-flag cases: a form inside longer words; t14's rule with no drops; a position without a list;
  a name equal to its form; no words.
* No list anywhere: `test_with_no_list_every_position_keeps_t14s_names`,
  `test_a_list_on_one_position_leaves_the_others_alone`, and the unchanged CSVs and school view.
* `tests/config`'s new cases. The checks are functions in the test files, and the lock already digests
  every field (`exclude_defaults`). The mutants below show they bite.

**20 mutants, all caught.**
* Each was applied alone, with the tests in a fresh process and `PYTHONDONTWRITEBYTECODE=1`, and the
  file was restored and checked by SHA-256.
* The test files: `test_link_chains.py`, `test_scenario_vocabulary.py`, `test_render.py`,
  `application/test_landscape_report.py`, `domain/test_landscape_taxonomy.py` and `tests/config`: 485
  tests.
* No Hypothesis is used, so working agreement 8's database rule does not arise. Each run still set
  `HYPOTHESIS_STORAGE_DIRECTORY` to a new empty directory.
* `git status` was clean after both passes.

| Mutant | Failed | Caught by |
|---|---|---|
| Merge: only a scenario's first form names it (the PM's) | 4 | both goldens, `test_merged_forms_…`, `test_a_listed_position_shows_the_coachs_name_…` |
| Merge: a name with merged forms never shows | 3 | both goldens, `test_merged_forms_…` |
| Drop: a named heading of a dropped form is still a scenario (the PM's) | 5 | the report.md golden, `test_a_dropped_named_heading_is_no_scenario_heading`, the rule's cases |
| Drop: dropped words beside a label still name | 2 | the rule's cases |
| Drop: a numbered heading's dropped words still name | 2 | the rule's cases |
| Drop: the documents count ignores dropped forms | 2 | the report.md golden, `test_a_dropped_named_heading_…` |
| No list: a position without a list shows nothing (the PM's) | 10 | the vocabulary golden's DA section, t14's goldens and service tests, `test_a_position_without_a_list_shows_t14s_words` |
| No list: every position counts as listed | 205 | most suites (every aff then refuses its empty list) |
| A list of drops only is no list | 8 | the domain, rule and service cases for drop-only lists |
| A listed position shows words its list does not hold | 6 | `test_a_list_shows_its_names_and_no_words_it_does_not_hold` and five more |
| Withheld: a listed name is never withheld | 1 | `test_a_listed_name_holding_a_caselist_word_is_withheld_and_counted` |
| Withheld: a name's words are read with their case | 2 | the rule's and the service's withheld cases |
| Domain: any kind lists scenarios | 8 | `test_only_a_da_or_an_advantage_lists_scenarios` |
| Domain: a form may be listed twice | 4 | `test_a_form_listed_twice_on_one_position_is_refused` |
| Domain: names compared with their case | 1 | `test_a_scenario_name_used_twice_…_whatever_its_case` |
| Domain: a scenario with no forms | 1 | `test_a_scenario_without_a_name_or_a_form_…[no forms]` |
| Lock: the digest leaves the scenario lists out | 2 | `test_any_edit_at_a_released_version_…[scenario-list-added]`, `[form-dropped-as-no-scenario]` |
| Config check: forms not checked for team codes | 2 | `test_the_personal_data_check_refuses[a team code in a form]`, `[… dropped form]` |
| Config check: scenario names not checked like labels | 2 | `test_the_personal_data_check_refuses[camel initials …]`, `[a name in a scenario name]` |
| Config check: every form counts as reachable | 2 | `test_the_form_check_refuses_a_form_no_heading_reduces_to` |

### After the PM's rulings

**Red against a skeleton** (`2268e60`). The skeleton has `ChainCoverage`'s two fields, filled with 0,
the dry run with no line for them, and the config check unchanged. The run covered `tests/config`, the
vocabulary suite and the dry-run script's test: **6 failed, 91 passed**.

| Failing | Why |
|---|---|
| `test_words_two_teams_use_that_a_list_does_not_hold_are_counted_per_kind`, `test_a_drop_only_list_counts_the_words_it_does_not_hold` | the count was 0 (expected advantage 1, DA 1 with 1 holding a caselist word; and DA 1) |
| the dry run's two tests | no `Scenario words no list holds` line |
| `test_the_personal_data_check_passes_scenario_vocabulary` | `War with China` refused for sentence case |
| `test_the_personal_data_check_refuses[a school in a capitalized scenario name]` | refused for sentence case as well as for its school word |

`test_listed_and_dropped_words_are_not_unlisted` and `test_a_position_without_a_list_has_no_unlisted_words`
passed on the skeleton. They are must-not-count cases, and the mutants below show they bite. One red was
first for the wrong reason: a passing case reused a name already in its list, in another case, and the
domain refused it on load. I renamed that case and ran it again before the commit.

**7 mutants, all caught**, with the same runner (fresh process, fresh `HYPOTHESIS_STORAGE_DIRECTORY`,
bytes restored and checked, `git status` clean). The dry-run script's test was added to its files: 493
tests.

| Mutant | Failed | Caught by |
|---|---|---|
| Unlisted: one team's words count | 2 | `test_words_two_teams_use_…`, the dry run's count test |
| Unlisted: a position without a list counts its words | 4 | `test_a_position_without_a_list_has_no_unlisted_words`, `test_listed_and_dropped_…`, the drop-only case, the dry run's zeros |
| Unlisted: the count reads words with the drops kept | 2 | `test_listed_and_dropped_words_are_not_unlisted`, the drop-only case |
| Unlisted: the caselist-word share is not counted | 2 | `test_words_two_teams_use_…`, the dry run's count test |
| Dry run: the line prints the total as the caselist-word share | 1 | the dry run's count test |
| Config: scenario names held to sentence case again | 2 | the passing-vocabulary test, the capitalized school case |
| Config: labels freed from sentence case | 1 | `test_the_personal_data_check_refuses[a name in a label]` |

## Before the report (working agreement 10)

The first round ran on `ca3adea`. After the rulings, on `fd22d2b`:
* `uv run scripts/affected_tests.py` chose the same 253 of 515 files from 22 changed files, still over
  two minutes, so the pull request's `ci` runs them.
* The changed directories and the always-run list (the same 21 paths as below): **4,284 passed in
  76.38s**, load average 11.8, nothing failed.
* ruff format and check, lint-imports (18 kept) and the handler check are clean. Pyright on
  `packages/debate_core` and the script: 0 errors.

The first round:

* **The affected set is over two minutes.** `uv run scripts/affected_tests.py` chose 253 of 515 files
  (49.1%) from 21 changed files, in 9.0 s.
  * I ran them as `.venv/bin/python -m pytest -q -n 6 -m "not slow and not live" -p no:randomly
    <files>` under a 115 s alarm, at load average 7.9.
  * The alarm stopped it at 67%. Its progress lines up to then hold **5,112 passes and no failure or
    error**. The `OSError: cannot send` lines are xdist's workers losing their killed parent.
  * No process outlived it.
  * So the rest is left to the pull request's `ci`, which runs the whole selection.
* **Within the two minutes, the tests of what changed and the always-run list:**
  * the files run: the landscape, plan-text, analytic-text, aff-assignment and classification tests in
    `packages/debate_core/tests/application`; `packages/debate_core/tests/arguments/landscape`;
    `packages/debate_core/tests/domain`; `packages/debate_core/tests/integrations/landscape`;
    `packages/debate_cli/tests/test_landscape_command.py`; `tests/smoke/test_landscape_smoke.py`;
    `tests/config`, `tests/architecture`, `tests/specs` and `tests/scripts`;
  * the result: **1 failed, 4,278 passed in 80.32s**, at load average 11.8;
  * the failure was `tests/scripts/test_caselist_run_deploy.py::test_every_aws_call_is_made_as_the_deployer_profile_in_us_east_1`.
    This branch changes neither that script nor its test. It passed alone (1 passed), and on a second
    run of all of `tests/scripts` under `-n 6` (**1,472 passed in 71.94s**, load average 12.4). It
    looks load-dependent: see [Follow-up work](#follow-up-work).
* `uv run --frozen ruff format --check .` → 1,437 files already formatted. `uv run --frozen ruff check
  .` → all checks passed.
* `uv run --frozen pyright`, bare as CI runs it → 0 errors, 0 warnings.
* `uv run --frozen lint-imports` → 18 kept, 0 broken. `scripts/check_thin_handlers.py` → 65 handlers
  within 25 statements.
* `uv run scripts/validate_specs.py` → OK, 469 files.
* `scripts/check_command_blocks.py --base origin/dev` → no `#` comments, this report included.
  `scripts/docs_index.py --check-descriptions` → all 53 documents have a description.
* No `pyproject.toml`, `uv.lock`, conftest or pytest-plugin change, so no whole-selection hand-off.

## Files changed

* **`debate_core.domain.landscape`:** `Scenario`, and `Position.scenarios`, `.not_scenarios` and
  `.has_scenario_list`.
  * Its invariants: DAs and advantages only; a form once per position across both lists; a name once,
    whatever its case; at least one form.
  * The module docstring's new section. See Deviation 1.
* **`debate_core.arguments.landscape.link_chains`:**
  * `card_scenario` takes the position's `not_scenarios`;
  * `scenario_name` maps t14's words to the coach's name;
  * `is_withheld` reads a name's words as the caselist's are read: letters and digits, without case;
  * the docstring's section.
* **`debate_core.application.landscape_report`:** `_LinkChains._scenario` reads every card's scenario
  through both, for the names, the rows and the documents count; `_words` reads t14's words with the
  drops skipped, and `_names` counts the words a list does not hold; the docstring line.
* **`debate_core.domain.landscape_report`:** `ChainCoverage.unlisted_words` and
  `.unlisted_words_withheld` (the PM's ruling 1).
* **`debate_core.arguments.landscape.render`:** the How-to-read bullet.
* **`config/landscape/`:** the taxonomy at 1.4.0 with the seed and its version note; `topics.yaml` at
  1.4.0.
* **`scripts/landscape_dry_run_by_section.py`:** two counts-only lines per kind: the scenario section,
  and the words no list holds. See Deviation 2.
* **Tests:**
  * `arguments/landscape/test_scenario_vocabulary.py` (new): the goldens and nine one-list cases;
  * `test_link_chains.py`: dropped forms, `scenario_name`, withholding a coach's name;
  * `domain/test_landscape_taxonomy.py`: the list's shape and refusals;
  * `tests/config/test_landscape_taxonomies.py`: the personal-data check over names and forms, and the
    check that every form is one the normalizer reproduces, each with refusing cases;
  * `tests/config/test_landscape_released_ids.py`: two edit cases;
  * `tests/scripts/test_landscape_dry_run_by_section.py`: the two scenario lines, by hand.
* **`tests/fixtures/landscape/`:**
  * `scenario_vocabulary/`: `scenarios.yaml`, the README with the hand count, `impact_sections.md` and
    `impact_cards.csv`;
  * `golden/report.md`: the bullet.
* **`docs/guides/landscape-taxonomy.md`:** the field table, the bump table, and "Your scenario lists".

## Deviations from the spec

1. **`debate_core.domain` is outside `constraints.packages`, and the taxonomy's model is there.**
   * The spec puts the lists "in the taxonomy". `Position` is a frozen `extra="forbid"` model in
     `debate_core.domain.landscape`, so a taxonomy file holding a list cannot load without a field
     there.
   * I added the fields and their invariants there, and nothing else. The rule stays in
     `debate_core.arguments`.
   * **Ruled 2026-10-26: yes.** The PM adds `debate_core.domain` to the spec's packages, with a ruling
     comment, in the next batch. I have not edited the spec's constraints.
2. **`scripts/landscape_dry_run_by_section.py` and its test (`tests/scripts`) are outside
   `constraints.packages`.**
   * The PM's context asks for "the dry run printing the scenario section". Today's script prints the
     scan's hits by section, but no scenario count.
   * I added one line per kind: impact rows, rows with a scenario, names withheld, and documents with no
     scenario heading and no role label. Counts only, from the report's existing chain coverage.
   * The PM's ruling 1 added the unlisted-words line to the same script.
   * **Ruled 2026-10-26: yes.** The PM adds `scripts` and `tests/scripts` in the same batch.

## Decisions and assumptions

1. **A list governs its position** (built; ruled (a) on 2026-10-26).
   * The spec says "a name in the list replaces t14's words for that position; positions without a
     list keep t14's rule". I read that as: for a position with a list, the names shown are the list's,
     and words it does not hold show nothing.
   * A position with only `not_scenarios` has a list too.
   * This matches t25's order ("the coach's scenario name from this task, a labelled internal link,
     the impact card's own tag"). A row the list does not name falls through to the next item, rather
     than showing raw words.
2. **The two-team threshold stays,** applied to a name over all its forms. A merged name can show where
   no single form would. The coach's names are curated, but the threshold is t14's rule for showing a
   name, and the spec changes only the naming.
3. **Withholding reads the name that would be shown,** not its forms. The forms in a committed file
   hold no caselist word: the seed was screened, and the coach may not write one. The printed name is
   what could leak.
4. **Dropping, and where a drop applies.** A dropped form is skipped as t14's not-a-scenario list is:
   * a named heading of one is no scenario heading, and a heading further in, or the words beside an
     impact label, may still name the card;
   * a numbered heading (`Scenario 1: …`) stays a scenario heading, because the team marked it one,
     and names nothing.
5. **Forms are matched whole**, as t14's words are produced. `too early dome` is not `too early`.
6. **Scenario names get the label check** in `tests/config`, without sentence case: no team-code shapes
   and no school words, like aliases and labels. `War with China` passes. This was sentence case as
   first built; the PM's ruling of 2026-10-26 changed it.
10. **The unlisted-words count, per position.** The ruling says "no listed position's list holds". I
    count a listed position's words against its own list, summed per kind. A word under the Midterms DA
    is counted when the Midterms list lacks it, even if another DA's list holds it. Dropped forms are
    held by the list. Words holding a caselist word are counted, and also given apart, because the
    coach can never list them.
7. **The seed is t14's table, copied, not re-measured.** The PM asked for "t14's table": hspolicy26
   through 2026-10-20, as t14's session report records it. The 4 names t14 withheld are not in the
   seed. Stagnation advantage's only name was withheld, so it has no list.
8. **The fixture's taxonomy is overlaid, not regenerated.** The synthetic caselist's `taxonomy.yaml` is
   written by `scripts/make_landscape_fixture.py`, which is outside this task's packages. So the new
   goldens read it unchanged and add the list in the test, from `scenario_vocabulary/scenarios.yaml`.
   The overlay keeps version 1.2.0, so every header line is the base golden's.
9. **The screen's read of the store.**
   * `debate.sqlite3` was opened with `mode=ro`, and it only selected disclosures.
   * The database file's size and time are unchanged. Its `-shm` index file's time moved, as a
     read-only open does.
   * It printed counts and position ids only: 5,126 disclosures, 959 caselist words, 31 names, 0 hits.

## Operator follow-ups

**Steps 1 to 3 are done** (2026-10-26): the edit, then, after the sync, the refill (36.2 + 24.8 + 376.2
s) and the dry run (70.9 s). Results are [above](#the-real-store-under-the-coachs-lists-2026-10-26).
What remains is the pull request after the PM's review, and the republish after the cloud cutover.

1. **The coach's edit: done.** `tests/config` passed (77), and the edit is committed alone. For a later
   edit, from the task worktree:

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t22-scenario-vocabulary
```

```bash
uv run pytest tests/config
```

   **Success looks like:** every test passed, with 0 failed. A failure names the position and the form
   or name.

   Steps 2 and 3 run from the same worktree, after the `cd` above.

2. **Refill the three caches under taxonomy 1.4.0, again after the sync.** The bump re-keys t17's
   caches. The first run (2026-10-26) classified, then refused the plan-text cache t24's format had
   rewritten ([the sync](#the-sync-onto-dev-2026-10-26)); the whole block runs again.
   * Expected runtime: about 12 minutes (t17's refill: 37.6 + 221.7 + 412.9 s).
   * **Local only:** it writes under `~/.debate-research/dev/landscape/` alone: the classification cache
     and review queue, the plan-text cache, and the analytic-text cache. Nothing is published, and
     nothing is written to a bucket before the cloud cutover. It prints counts only.
   * It refuses to start if a `DEBATE_*` variable is set or a `caselist pull` is running. From the task
     worktree:

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run python scripts/classify_landscape_positions.py classify --caselist hspolicy26 --snapshot 2026-10-20 && uv run python scripts/assign_landscape_affs.py plan-texts --caselist hspolicy26 --snapshot 2026-10-20 && uv run python scripts/read_landscape_texts.py --caselist hspolicy26 --snapshot 2026-10-20; fi
```

   **Success looks like:**
   * a `Classified hspolicy26 on policy-2026-27-nhi 1.4.0` line, with `Sources` above zero;
   * `Plan texts: … sources, 0 cached, … parsed`, with sources above zero, then the `K-aff markers:` line;
   * `Analytic texts: … sources, 0 cached, … parsed, … cache written`, with sources above zero;
   * each script's `Runtime` line.

   A `STOP:` line means nothing ran. A failure stops at the script that failed (the `&&`). Paste every
   line back.

3. **Then the dry run, printing the scenario section.** It is the landscape service as a dry run
   without `--publish`, so it is read-only and takes no bucket lock. Expected runtime: about 75 s on the
   warm caches. It prints counts and ids only, never a name, text, team or school. From the task
   worktree:

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run python scripts/landscape_dry_run_by_section.py --caselist hspolicy26 --snapshot 2026-10-20; fi
```

   **Success looks like:**
   * `Dry run of hspolicy26 through 2026-10-20, taxonomy 1.4.0: nothing written; 7 files planned.`;
   * a `Scenarios, advantage (… positions): …` line and a `Scenarios, da (… positions): …` line, each
     with its impact rows above zero.
     * For comparison, t14's build had 43 advantage and 44 DA impact rows, 0 and 13 of them with a
       scenario, and 2 and 2 names withheld.
     * Under the coach's lists, **names withheld: advantage 1, DA 0.** The Stagnation advantage has no
       list and keeps its one. The Midterms DA's and Disease advantage's withheld words are not on their
       lists, so they are no names those positions show. No name or form on a list holds a caselist word.
     * Rows with a scenario move: merges can add rows (`golden dome`), and drops remove some (the
       Economy DA's, the Medical devices DA's). I give no expected number for them.
     * Documents with no scenario heading can only rise from t14's 676 of 1,164 (advantage) and 251 of
       662 (DA), since a dropped named heading is no scenario heading;
   * a `Scenario words no list holds, advantage: …` line and one for `da`.
     * At least advantage 1 and DA 2, every one of those holding a caselist word: the words t14
       withheld under the Disease advantage and the Midterms DA.
     * More only where a drop lets a heading further in name a card with words its list lacks;
   * the scan lines, with **no hit** in report.md's `Advantages: impact cards` or `Disadvantages: impact
     cards` sections: those hold the scenario names.

   Paste every line back. A `Refused:` line means the run did not start, and says why. The session then
   records the counts here for ac2.

4. **No publish.** The republish follows the cloud cutover.

5. **The pull request, after the PM's review.** The branch must not be behind `origin/dev`, and dev moves
   again after every merge (the docs-index refresh). So sync once more, then open the PR, from the task
   worktree:

```bash
scripts/task sync v1-e32-t22-scenario-vocabulary
```

```bash
scripts/task pr v1-e32-t22-scenario-vocabulary
```

## Follow-up work

* **The coach's two needs that scenarios do not cover** (the coach's read of the seed, 2026-10-26).
  The PM files them as a new E32 task in the next batch; nothing is built here.
  * **Branches.** The Midterms DA has two outcomes, Dems win and Republicans win, each with its own
    impacts. A scenario is one flat name per impact card, so a card under `dems win > dome impact`
    shows the branch (the named heading wins over the words beside an impact label) or, with the branch
    dropped, the impact. It never shows both.
  * **The mechanism.** For the Economy DA the coach wants what causes the decline from the DA's thesis
    (plan, link, internal link, impact), not `decline` or `econ`. That is the link chain (t14's chain
    table, t25's readable chains), not a scenario name. Some Economy DAs may be different DAs by link
    (taxes, stocks, debt), which is a taxonomy question.
  * **The new task, counts first** (working agreement 7), read-only, on hspolicy26 through 2026-10-20,
    counts only:
    * (a) per DA, the documents that nest an impact or named heading under another named heading below
      the position (branch over impact), and the outer headings two or more teams use;
    * (b) for the Economy DA, the documents that label a link or internal link, grouped by the link
      card's tag words, to see whether the mechanism can be read from labels or needs the model stage
      (v1-e32-t07).

    Then three options: a two-level scenario (branch, then impact) in the taxonomy; the mechanism as a
    named link per DA (with t25); or splitting DAs by link.

* **v1-e32-t25** names each impact rank by the coach's scenario name first. It reads
  `ImpactCard.scenario`, which now holds the coach's name where a list exists.
* **The deploy-script test that failed once under load:**
  `tests/scripts/test_caselist_run_deploy.py::test_every_aws_call_is_made_as_the_deployer_profile_in_us_east_1`.
  It failed once at load average 11.8 under `-n 6`, then passed alone and in a full re-run of
  `tests/scripts`. The failing line asserts that every recorded `aws` call starts `--region us-east-1`.
  It belongs to the caselist deploy script's owner. I did not investigate it further.

## Questions for the PM

Answered on 2026-10-26 ([the rulings](#the-pms-rulings-2026-10-26)). Kept as sent:

```text
v1-e32-t22 questions (session, 2026-10-26): built and checked, stopped for the coach

Built: scenario lists in the taxonomy (name + forms, plus not_scenarios), taxonomy
1.4.0 with t14's 31 names on 11 DAs/advantages as the seed, goldens by hand before
code, red run 38 failed against a skeleton, 20/20 mutants caught. ac1 PASS; ac2
waits for the coach's edit and the operator's refill + dry run. Goal InProgress.

1. Does a position WITH a list also show heading words its list does not hold?
   (a) No, as built: a listed position shows only the coach's names; unlisted
       words show nothing; a list of drops only shows nothing. Reads "a name in
       the list replaces t14's words for that position; positions without a list
       keep t14's rule" literally, and fits t25's order (the coach's name, then
       the internal link, then the card's own tag) because an unnamed row falls
       through rather than showing raw words.
   (b) Yes: unlisted words still show under t14's rule (two teams, not withheld);
       the list only merges, renames and drops. New names after the seed would
       show without the coach.
   Recommendation: (a). The coach's names are the point (t25), and the seed holds
   every name t14 shows today, so (a) changes nothing until the coach edits.
   The cost: a scenario teams start using later shows nothing until it is added;
   a follow-up count in the dry run (words 2+ teams use that no list holds) would
   flag it. Under (b), 6 test cases and the drop-only rule change; no golden.

2. Scope: debate_core.domain (Position's two fields and their checks: the
   taxonomy model lives there, so a file holding a list cannot load otherwise)
   and scripts/landscape_dry_run_by_section.py with tests/scripts (the dry run
   "printing the scenario section", which printed no scenario count) are outside
   constraints.packages. Both are built. Recommendation: add debate_core.domain,
   scripts and tests/scripts to the spec's packages, with a ruling comment.

3. FYI unless you say otherwise:
   - The two-team threshold stays, over all of a name's forms together.
   - Withholding reads the name that would be shown, not its forms. So under a
     list, words holding a caselist word are no name the position could show,
     and are not counted as withheld. The unedited seed's withheld count goes from
     DA 2 / advantage 2 (t14) to DA 0 / advantage 1 (Stagnation, which has no
     list). The names shown are unchanged.
   - A numbered "Scenario 1: X" heading whose X is dropped stays a scenario
     heading (the team marked it) and names nothing; a dropped named heading is
     no scenario heading.
   - Scenario names get the label rules in tests/config, including sentence
     case, so "war with china", not "War with China". Say if names should be
     allowed capitals after the first word.
   - The seed is t14's table copied (hspolicy26 through 2026-10-20), screened
     read-only against 5,126 disclosures: 0 of 31 hold a caselist word.

Reply with 1 (a) or (b), 2 yes/no, and any change to 3.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
