# Session report: v1-e32-t17-kritikal-affirmatives

| | |
|---|---|
| Task | `v1-e32-t17-kritikal-affirmatives` — Kritikal affirmatives identified, not left among the rounds with no identified aff |
| Spec | [`plan_specs/v1/e32-argument-landscape/t17-kritikal-affirmatives.yaml`](../../plan_specs/v1/e32-argument-landscape/t17-kritikal-affirmatives.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t17-kritikal-affirmatives` |
| Session status | COMPLETE: built and tested after the PM's rulings of 2026-10-25. The operator refilled the caches, and the dry run on the real store is recorded. The coach's edit to the K families comes back before the pull request <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**Built as ruled on 2026-10-25, and every criterion passes, so the Goal is Succeeded.** A kritikal
affirmative is now identified rather than left among the unidentified rounds.

* **The position.** Taxonomy **1.3.0** adds `kritikal-aff`, kind `aff`, side `aff`, with no alias. No
  new position kind was needed. The released-ids check passes.
* **The markers,** as approved:
  * t11's role-of-the-ballot labels, read by t11's own rule;
  * `Advocacy`, `Advocacy statement`, `Our advocacy (statement) is` and inline `Advocacy:`;
  * `The 1AC is`;
  * `Method`, `Our method is` and inline `Method:`.

  `Methods` is left out. The markers are read beside t09's plan texts, in the same pass and cache, and
  only their kind, form, place and unit are kept. Never a word.
* **Two new assignment methods:**
  * `KRITIKAL_AFF_MARKER`: a round nothing else identifies, with no plan text in any of its files and
    a marker in one;
  * `KRITIKAL_AFF_CARRY`: carried by t09's carry rule and guard, and never into a round whose own file
    reads an advantage (t15's placement). Those refusals are counted.
* **report.md's Kritikal affirmatives** comes after Advantages by affirmative, in the Affirmative part.
  It gives:
  * the K-aff rounds and teams, by own marker and by carry;
  * the rounds refused for an advantage;
  * one line of K families named in the K-aff files' headings, with files and teams;
  * the rounds still unidentified.

  The method table adds the refused rounds and the control. No other bundle file changes beyond the
  new position's row.
* **Tests were shown failing first** against skeletons, and the goldens are hand-written from a
  hand-written fixture.
  * 14 targeted mutants: 12 caught at once.
  * One survivor was an equivalent check, now removed.
  * One survivor needed a test, and is now caught.

**On hspolicy26 after the operator's refill** ([below](#the-real-store-after-the-refill-2026-10-25)):
* **40 affirmative rounds by 19 teams are kritikal affirmatives:** 31 by their own marker, 9 by carry.
* **Unidentified rounds fall from 709 to 669 of 2,192.** `PLAN_TEXT`, `TEAM_CARRY` and `PLACED_CARD`
  are unchanged (1,172, 254 and 57).
* **The advantage guard refused 17 rounds.**
* **The control is 5 rounds** (`PLAN_TEXT` 3, `TEAM_CARRY` 2), so **option (b) would move 2 rounds.**
* **5 K families** appear in the K-aff files' headings, 1 file each.
* **No scan hit is in the new section.**
* The dry run took 71.8 s and wrote nothing.

**What to look at first:**
* [the fixture's table](../../tests/fixtures/landscape/kritikal_affs/README.md) and its two goldens;
* [Decisions](#decisions-and-assumptions) 1 and 2: existing assignments are never moved, and the round
  rule asks for no plan text in any of the round's files;
* [the operator's refill](#operator-follow-ups), which the real store needs before a dry run, because
  1.3.0 re-keys three caches.

**The PM ruled on the build's three questions the same day** ([below](#the-questions-of-2026-10-25-on-the-build-answered)):
* `constraints.packages` is amended in the next PM batch;
* precedence (a) stands: no existing assignment moves;
* the K family list goes to the coach, and the session does not wait for it.

So the dry-run script now prints the method table and the K-aff group, with the control by method, so
that what option (b) would move is on record after the refill. The coach's edit to the families comes
back on this branch before the pull request. The session then runs `tests/config`, commits the edit
and notes it here.

**The affected set was too long for a session at load 14 to 38.** The test directories of what
changed and the always-run list ran instead
([below](#before-the-report-working-agreement-10)).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| kritikal-affs | Done | The counts (2026-10-25), the PM's rulings (2026-10-25), then the position, the reader, the rule, the cache, the config, the seam, the report's group and goldens, the script and the guide |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts before any rule, over affirmative rounds with no identified aff, of files with K-aff markers and no plan text, by marker and team, sent to the PM with the options | PASS | [The counts](#the-counts-hspolicy26-through-2026-10-20-taxonomy-120), sent 2026-10-25 with options (a) and (b). The PM ruled the same day ([below](#the-pms-rulings-applied)). Nothing was built before the ruling |
| ac2: after the ruling, on the synthetic fixture, the report shows kritikal affirmatives as their own group and the rounds still unidentified, matching a hand-written golden file; tests shown failing first; a taxonomy change passes the released-ids check | PASS | `test_kritikal_report_md_section_matches_the_hand_written_golden_file` against [`report_section.md`](../../tests/fixtures/landscape/kritikal_affs/report_section.md), and `test_kritikal_method_table_matches_the_hand_written_golden_file` against [`method_table.md`](../../tests/fixtures/landscape/kritikal_affs/method_table.md), both hand-written from the fixture's [README table](../../tests/fixtures/landscape/kritikal_affs/README.md). Red first: [below](#checks-shown-failing-for-their-reason). Released ids: `.venv/bin/python -m pytest tests/config/test_landscape_released_ids.py` → 25 passed, with 1.3.0 committed and the 1.1.0 and 1.2.0 locks unchanged; `tests/config` → 60 passed |
| kritikal-affs node: `uv run pytest packages/debate_core/tests/application/test_landscape_report.py` | PASS | `.venv/bin/python -m pytest packages/debate_core/tests/application/test_landscape_report.py -q -p no:randomly` under `perl -e 'alarm 100'` → 105 passed (96 before this task) |

## The PM's rulings, applied

The rulings are a PM-ruling comment above the spec's `acceptanceCriteria` (commit `f20adac`).

| Ruling | Where it is |
|---|---|
| 1. One generic `kritikal-aff` position (kind aff, side aff, no aliases), named by a marker in a file with no plan text, a new assignment method; its own group in the Affirmative part, placed as t15's section is | `config/landscape/taxonomies/policy-2026-27-nhi.yaml` (1.3.0) and `topics.yaml`; `KRITIKAL_AFF_MARKER` in `arguments/landscape/aff_assignment.py`; `_kritikal_section` in `render.py`, right after `_advantages_section` |
| 1. One line of K families named in the K-aff files' headings, with files and teams; counts only, never a placement, nothing from tags | `heading_families` in `arguments/landscape/kritikal_aff.py` (pocket, hat and block headings only); `application/landscape_kritikal.py` counts them over the K-aff rounds' files. The phrases are config, `config/landscape/kritikal_affs/policy-2026-27-nhi.yaml` |
| 1. 1.2.0 to 1.3.0 under t08's lock; the cache refill as one operator block; the publish waits for the cutover seed, the local dry run does not | [Operator follow-ups](#operator-follow-ups): the refill, then the dry run without `--publish`. No publish is proposed |
| 2. The markers as proposed, `Methods` left out; the control count kept in the method table | `read_kritikal_markers`, with t11's `role_of_the_ballot_form` made public for it (behaviour unchanged, its own commit `9b49789`). The control is the method table's last row |
| 3. Carry through t09's rule and guard, never into a round whose own file reads an advantage (t15's placement); the method table counts own marker, carry, and refused | `KRITIKAL_AFF_CARRY`. The advantage rounds come from t02's placements in `build_aff_assignments`: READS, at or above the review threshold, as t03 and t15 count a read. Refused rounds come back as `AssignmentCounts.refused_by_advantage` |
| 4. The unlabelled-plan policy affs are a follow-up task | Not built here ([Follow-up work](#follow-up-work)) |

## What was built

| Where | What |
|---|---|
| `arguments/landscape/kritikal_aff.py` (new) | The pure reader: the markers (kind, form, element index, unit; no words), the K families in headings with the longest phrase first, `KritikalAffConfig` with its checks, the rules for the digest, and `KritikalAffInputs`, what the report is given |
| `arguments/landscape/analytic_texts.py` | `role_of_the_ballot_form`, `label_form` and `TEXT_UNITS` made public. Behaviour unchanged: t11's 73 reader tests passed on the commit alone |
| `arguments/landscape/aff_assignment.py` | `KritikalSignals`; `KRITIKAL_AFF_MARKER` and `KRITIKAL_AFF_CARRY` after `PLAN_TEXT` and `TEAM_CARRY`, which they never change; `refused_by_advantage` |
| `arguments/landscape/plan_text.py` | `PlanTextVocabulary` takes the K-aff config, refuses one naming no active aff, and its digest covers it (rule `plan-text-3`) |
| `application/ports/plan_text_store.py`, `application/plan_texts.py` | The cache keeps each source's markers and heading families; `PlanTextRun.kritikal` |
| `application/aff_assignment.py` | `build_aff_assignments` reads the advantage rounds from t02's placements and returns the K-aff inputs; the seam returns `AffAssignmentsForReport` (assignments and K-aff inputs); the service passes the topic's K-aff config |
| `application/landscape_kritikal.py` (new), `application/landscape_report.py`, `domain/landscape_report.py` | The group's counts (`KritikalAffs`): rounds, teams, by marker, by carry, refused, families, control |
| `application/landscape_run.py` | Hands the seam's K-aff inputs to the report |
| `arguments/landscape/render.py` | The section and the method table's two rows |
| `application/ports/taxonomy_repository.py`, `integrations/landscape/yaml_taxonomy_repository.py` | `kritikal_affs/<topic id>.yaml` loaded and checked with the taxonomies; `kritikal_aff(topic)` |
| `config/landscape/kritikal_affs/policy-2026-27-nhi.yaml` (new) | The position id and 20 K families with their phrases |
| `scripts/landscape_dry_run_by_section.py` | After the build's rulings, the dry run prints the affirmative rounds by method, the K-aff group (by marker, by carry, refused), the control with its rounds by method, and the families by id. Counts only |
| `KritikalAffs.control_by_method` | The control's rounds by the method that identified them. The `TEAM_CARRY` share is what option (b) would move. report.md's row is unchanged |
| `scripts/assign_landscape_affs.py` | Its vocabulary takes the K-aff config, so it fills the same plan-text cache as the run; it prints the markers' and the K-aff rounds' counts |
| `docs/guides/landscape-taxonomy.md` | "Kritikal affirmatives": the markers, the carry and its guard, what report.md shows, how to edit the families, and the refill after a taxonomy bump |

### Checks shown failing for their reason

Each suite was run red before its code: against a skeleton that found nothing, or with the one line it
checks taken out and then restored byte for byte. Agreement 8: an attempt that failed at import was not
counted.

| Suite | Red |
|---|---|
| `arguments/landscape/test_kritikal_aff.py` (the reader) | 17 failed, 15 passed. The 15 are not-a-marker cases, the no-config case and the config checks, which a find-nothing skeleton passes by construction |
| `arguments/landscape/test_aff_assignment.py` (the rule) | 8 failed, 29 passed: t09's 24, and 5 cases where the K aff must not be assigned |
| `application/test_landscape_report.py -k kritikal` (the group and goldens) | 7 failed, 2 passed (the no-K-aff case and the position's row, which the given assignments decide). A first attempt had 8 failed: my no-K-aff case still handed in K assignments, which a run without the config never makes. I fixed the fixture loader before any code |
| `application/test_landscape_run.py`, the seam | Written after the wiring, so the seam test failed with the wiring line removed (1 failed) and passed after the line was restored byte for byte |
| `application/test_aff_assignment.py -k kritikal` (the advantage rounds, the inputs) | 3 failed, 1 passed (the no-config case) |
| `arguments/landscape/test_plan_text.py -k k_aff` (the vocabulary) | 4 failed |
| `application/test_plan_texts.py` (markers cached, no words) | 2 failed, 14 passed. The no-words test passes on a skeleton that writes nothing |
| The producer's K-aff test | 1 failed against the loader skeleton |
| `integrations/landscape/test_kritikal_aff_files.py` (the loader) | 11 failed, 3 passed (the constant, the no-file case and the no-taxonomy case) against the skeleton, then restored byte for byte |
| `tests/config`, the directory test | 1 failed, 55 passed, until the new directory was listed |
| `integrations/landscape/test_plan_text_store.py` | t09's field pin failed on the new cache fields. It now pins them and the marker's own four fields |
| `tests/scripts/test_assign_landscape_affs.py` | 1 failed, 8 passed against the committed script, swapped back byte for byte after |
| `tests/scripts/test_landscape_dry_run_by_section.py` (after the build's rulings) | 2 failed, 1 passed (the no-hit case) before the script printed the method table and the group |
| The control by method (the report test and the script test) | 2 failed, 107 passed, then 109 passed |

**The goldens.** The group's counts matched the fixture table on the first run.
* The section golden failed once, on its own last line. I had trimmed the blank line that ends a
  section sliced this way, and t15's golden ends with one too.
* The method-table golden matched on the first render.

### Mutants

There were 14 mutants on the rules this task adds, one of them run twice. Each:
* was applied to one file, after a check that its text occurs exactly once;
* ran the four covering suites (189 or 190 tests) in a fresh process, with bytecode writing off and
  `__pycache__` cleared;
* was restored from a copy and compared byte for byte.

No Hypothesis is used, so there is no example database to isolate (agreement 8). Each run took 3.7 to
9.1 s at load 16 to 18.

| Rule | Mutant | Failed |
|---|---|---|
| Advantage guard | the K aff carried into a round reading an advantage | 3 |
| Advantage guard | the guard applied to a round's own marker too | 2 |
| Advantage guard | an advantage placed below the review threshold refuses the carry | 2 |
| Marker | a marker names a round holding a plan text of its own | 1 |
| Marker | a marker taken before the policy carry, moving `TEAM_CARRY` rounds | 1 |
| Carry | the carry ignores t09's guard (every document `NONE`) | 1 |
| Carry | a team that names a policy aff carries the K aff (the identified check removed) | **survived**: equivalent, check removed |
| Carry | a disagreeing team carries the K aff | **survived**, then 2 |
| Reader | `Methods` counted as a method label | 1 |
| Reader | an advocacy label counted with no text under it | 1 |
| Families | not the longest phrase first | 2 |
| Families | read from every paragraph, a tag included | 1 |
| Families | counted over every affirmative file, not only the K-aff rounds' | 8 |
| Control | K-aff rounds counted as identified another way | 2 |

**The two survivors:**
1. **Removing the identified check could not be told from keeping it.** A team whose rounds name
   another aff has already carried it, by `TEAM_CARRY`, into every open round with no plan text before
   the K-aff step. So it has no marker round to carry from. The check was removed (agreement 8), and a
   comment says why.
2. **Removing the disagreeing check survived until a new test.** No test had a team that disagrees only
   through a conflicting round, which adds nothing to its identified affs. The new test,
   `test_a_team_with_a_conflicting_round_reads_the_k_aff_by_its_own_marker_and_carries_nothing`,
   catches it: 2 failed.

### Before the report (working agreement 10)

* **The affected set** (`uv run scripts/affected_tests.py`) is **210 test files**.
  * I ran it once, with `-n auto -m "not slow and not live"`, under a 115 s limit on the interpreter.
  * The limit stopped it at 69% (exit 142, load average 16). No test had failed by then.
  * Its xdist workers ended with their parent, and none was left running.
  * So the whole affected set is left to the pull request's `ci` check.
* **Within the limit,** the test directories of what changed and the always-run list:

  | Run | Result |
  |---|---|
  | `arguments/landscape`, `integrations/landscape`, `tests/config`, and the landscape scripts' tests (assign, read texts, dry run by section, classify) | 996 passed in 4.1 s |
  | The application's landscape, run, assignment, plan-text, analytic-text and classification tests, `domain`, `tests/architecture`, `tests/specs` | 1,501 passed in 9.8 s |
  | All of `packages/debate_core/tests/application` | 3,783 passed in 97.7 s (load 38) |
  | `debate_cli`'s landscape command, app and help wiring, and the two pinned integration lists (`test_installation.py`, `commands/test_doctor.py`); `tests/smoke/test_landscape_smoke.py` | 135 passed in 18.9 s |

* **All of `packages/debate_cli/tests`** was stopped twice by the limit, at 97%. The second run was
  verbose and named one failure,
  `bucket_mode/test_restore_run_state.py::test_the_copy_holds_the_runs_state_and_the_data_directory_and_the_bucket_are_left_as_they_were`.
  * That is v1-e40-t06's restore test. It imports no landscape code.
  * Alone, in one process (`-n 0 -p no:randomly`), its file passed: 17 passed in 49.9 s.
  * I read it as a failure under load, and CI will run it. t06's report already runs this file in one
    process because of its SQLite state.
* **The cheap checks:**
  * `ruff format --check .`: 1365 files already formatted;
  * `ruff check .`: all checks passed;
  * `pyright` (the project's configuration): 0 errors, in 63 s;
  * `lint-imports`: 16 kept, 0 broken;
  * `check_thin_handlers.py`: 55 handlers within 25 statements;
  * `docs_index.py --check-descriptions`: OK;
  * `check_command_blocks.py --base origin/dev`: OK;
  * `check_links.py`: OK;
  * `pre-commit run check-merge-conflict --all-files`: passed;
  * `validate_specs.py`: OK ([below](#files-changed)).
* **After the build's rulings:**
  * `pyright` (the project's configuration): 0 errors;
  * `arguments/landscape`, the application's report, assignment and run tests, `tests/scripts`,
    `tests/config`: 2,493 passed in 68.5 s.
* **No shared test ground changed:** no `pyproject.toml`, `uv.lock`, conftest or pytest plugin. So no
  whole-selection hand-off.

## The real store after the refill (2026-10-25)

hspolicy26, parser `2026.10.20-docx-6`, through 2026-10-20, taxonomy 1.3.0, with the K family list as
committed (the coach's edit has not come back yet).

**The operator's refill and dry run** ([Operator follow-ups](#operator-follow-ups) 2 and 3).
* `tests/config` passed first: 60 passed.
* No `DEBATE_*` variable was set and no `caselist pull` was running.

| Step | Result | Runtime |
|---|---|---|
| `classify_landscape_positions.py classify` | 3,825 sources, 126,681 cards. Counted 63,494 (50.1%), the same as under 1.2.0. Review queue 1,340 rows, as before. Cache: 107,187 keys, 0 hits (the version bump), written | 37.6 s |
| `assign_landscape_affs.py plan-texts` | 1,770 sources, 0 cached, 1,770 parsed, 0 refused, 0 unread. Verdicts as under 1.2.0: NAMES 950, CONFLICTING 7, UNNAMED 2, NONE 811. **K-aff markers: 28 documents hold one, 26 of them with no plan text, by 22 teams** | 221.7 s |
| `read_landscape_texts.py` | 3,825 sources parsed, 0 unread, cache written. Every kind's found and placed counts as t11's and t16's | 412.9 s |
| `landscape_dry_run_by_section.py`, no `--publish` | Nothing written, 7 files planned. The lines below | 71.8 s |

**How affirmative rounds are identified, 1.2.0 against 1.3.0:**

| Method | 1.2.0 | **1.3.0** |
|---|---|---|
| `PLAN_TEXT` | 1,172 | 1,172 |
| `TEAM_CARRY` | 254 | 254 |
| `PLACED_CARD` | 57 | 57 |
| `KRITIKAL_AFF_MARKER` | | **31** |
| `KRITIKAL_AFF_CARRY` | | **9** |
| Not identified | 709 of 2,192 | **669 of 2,192** (30.5%) |
| Of those, the K aff not carried in: the round's own file reads an advantage | | **17** |
| Identified another way, with a K-aff marker in a file (the control) | | **5 rounds, 5 files: `PLAN_TEXT` 3, `TEAM_CARRY` 2** |

* **No existing assignment moved** (ruling (a)). The three old methods have the same rounds.
* **The K-aff group:** 40 rounds by 19 teams. The 40 rounds come off the unidentified 709 exactly.
* **Option (b)'s size, on record:** the control's `TEAM_CARRY` share is **2 rounds**. Those are the
  rounds a round's own marker would take from its team's carry. The 3 `PLAN_TEXT` rounds would not move
  under (b), because a plan text naming an aff wins either way. (b) would also make those teams
  disagree, which could cost them other carried rounds; that knock-on was not measured.
* **The advantage guard refused 17 rounds,** against 9 carried. Most of the K-aff teams' other open
  rounds hold a card placed under an advantage, and the guard treats each as a policy aff with an
  unlabelled plan, the rounds ruling 4's follow-up task covers. Whether some are K affs reading an
  advantage was not measured.
* **The K families in the K-aff files' headings:** cap, settler colonialism, colonialism, feminism and
  Buddhism, 1 file and 1 team each. That is 5 of the 23 marker files, so the line is short, as the
  counts said it would be.
* **The scan:** 9 hits, 0 not yet accepted. 1 is in report.md's plank table (v1-e32-t16's), and 8 are
  in `top_cards.csv`. **None is in the Kritikal affirmatives section.**

**The 31 rounds against the counts' 28.** I ran two more read-only passes (49.0 s and 54.2 s): the same
landscape service as a dry run, with t11's texts off. Both had the guards checked first and a 115 s
limit on the interpreter. All 17 files under `landscape/` and `reports/` were checksummed before and
after each pass, and none changed. They printed counts only.

| | Files | Rounds |
|---|---|---|
| The counts (1.2.0's unidentified rounds, the proposed list) | 25 | 28 |
| **The build's `KRITIKAL_AFF_MARKER`** | **23** | **31** |
| Role of the ballot only / with an advocacy label | 13 / 2, as the counts | |
| `The 1AC is` | 6, against 5 | one of them disclosed in **6 rounds** |
| A method label | 2, against 5 | |

The difference comes from two places:
* **Method: 3 files fewer.** The counts' sentence pattern took `The`, `Our` or `My` with `method` or
  `methodology` and `is`, `will` or `should`. The approved list is `Our method is` only, and no file has
  that exact wording, so the build's 2 method files are the two `Method` labels.
* **`The 1AC is`: 1 file more, in 6 rounds.** The counts read that sentence only outside headings. The
  build reads it in any unit, as t11 reads `The role of the ballot is`. The extra file is disclosed in
  6 rounds; which unit holds its sentence was not checked.

28 − 3 + 6 = 31.

**What Decision 2's per-round rule leaves out: nothing today.** 26 files hold a marker and no plan text.
23 are in `KRITIKAL_AFF_MARKER` rounds. The other 3 are disclosed in:
* 1 `PLAN_TEXT` round, whose other file names an aff;
* 2 `TEAM_CARRY` rounds;
* 2 negative rounds.

No unidentified round holds a marker file beside a file with a plan text of its own.

### After the coach's K families (2026-10-25)

**The coach's edit** was committed on its own as "The coach's K families" (`bb2e248`), after
`uv run pytest tests/config` passed (60 passed).
* Families went from 20 to 19: colonialism was merged into settler colonialism, which took its phrases.
* Phrases went from 51 to 54: `wilderson` under antiblackness, `zizek` under psychoanalysis, and
  `heteronormativity` under queer theory.
* No school, team code or tournament word was added. The two new names are scholars, beside the Lacan
  and Nietzsche already listed.

**The operator then ran the two local blocks.** Both checked for a `DEBATE_*` variable and a `caselist
pull` first. Nothing was published or written to a bucket.

| Step | Result | Runtime |
|---|---|---|
| `assign_landscape_affs.py plan-texts --caselist hspolicy26 --snapshot 2026-10-20` | 1,770 sources, 0 cached, 1,770 parsed, 0 refused, 0 unread, cache written. The edit changed the cache's key. Verdicts unchanged: NAMES 950, CONFLICTING 7, UNNAMED 2, NONE 811. K-aff markers unchanged: 28 documents, 26 with no plan text, 22 teams | 304.7 s |
| `landscape_dry_run_by_section.py --caselist hspolicy26 --snapshot 2026-10-20` | Taxonomy 1.3.0, nothing written, 7 files planned | 79.2 s |

**The method table** is unchanged from the first dry run:

| Method | Aff rounds |
|---|---|
| `PLAN_TEXT` | 1,172 |
| `TEAM_CARRY` | 254 |
| `PLACED_CARD` | 57 |
| `KRITIKAL_AFF_MARKER` | 31 |
| `KRITIKAL_AFF_CARRY` | 9 |
| Not identified | 669 of 2,192 |
| Of those, the K aff not carried in: the round's own file reads an advantage | 17 |
| Identified another way, with a K-aff marker in a file (the control) | 5 rounds, 5 files: `PLAN_TEXT` 3, `TEAM_CARRY` 2 |

* **The K-aff group:** 40 rounds by 19 teams, 31 by their own marker and 9 by carry. Unchanged.
* **The families line, in the coach's terms:** settler colonialism 2 files (2 teams), cap 1 file (1
  team), feminism 1 file (1 team), Buddhism 1 file (1 team).
* **What moved from the earlier dry run:** only the families line. The file counted under colonialism
  before now counts under settler colonialism, which goes from 1 file and 1 team to 2 and 2. Colonialism
  is no longer a family.
  * Nothing else moved: rounds, methods, refusals, the control, the planks and the scan (9 hits, 0 not
    yet accepted, none in the Kritikal affirmatives section) are as before.
  * No K-aff file's heading names `wilderson`, `zizek` or `heteronormativity`.

## The counts (hspolicy26, through 2026-10-20, taxonomy 1.2.0)

### How they were read

**Guards.** Before every pass:
* no `DEBATE_*` variable was set and no `caselist pull` was running. Each command checked both and
  would have stopped otherwise;
* the load average was 4.4 to 6.8 on 11 cores, from other sessions.

**Time limits.** Each pass ran as `perl -e 'setpgrp(0,0); alarm 115; exec @ARGV' .venv/bin/python ...`.
* The limit sat on the interpreter, in its own process group.
* Inside, a 100 s `SIGALRM` raised in the parent. That closes the pool's generator, whose `finally`
  stops every worker.
* After every pass, `pgrep` found no worker or script process left. No pass reached either limit.

**The local store only.** The scripts built the services by hand over `~/.debate-research/dev`, as
`scripts/read_landscape_texts.py` does, so the container and the dev profile's bucket mode were never
involved. No bucket was built and nothing was published.

**Nothing was written.** The 17 files under `~/.debate-research/dev/landscape/` and `reports/` had
the same SHA-256 before the first pass and after the last.

**Counts only.** The scripts are scratch files outside the repository, and they printed counts only.
* Their scratch JSON holds source digests, t03's round ids, team keys, verdicts, position ids,
  placements, family ids and the normalized forms of short labels.
* A team key is a salted digest of the team, and the salt was never written.
* No paragraph, tag or cite text is in them. A grep of the files for `should`, `united states` and
  `school` found none.

**Reused, not rebuilt** (the PM's context):
* **The rounds and their affs** are t09's and t03's own.
  * Pass 1 ran `LandscapeRunService` as a dry run for snapshot 2026-10-20, with t09's
    `AffAssignmentService` and t11's texts left off, so it parsed nothing.
  * It captured the inputs handed to `LandscapeReportService` and called t03's `count()` on them.
  * A round has no identified aff when no aff position's reads include it. That is t03's rule:
    neither a `PLAN_TEXT` or `TEAM_CARRY` assignment nor a `PLACED_CARD`.
  * **The dry run gave 709 unidentified rounds of 2,192, the report's figure. Recomputed from the
    captured reads, it is 709 again.**
* **No plan text** is t09's verdict `NONE`, from the run's own plan-text reading, which came from
  the cache with no parse.
* **Roles of the ballot** are t11's `ROLE_OF_THE_BALLOT` readings from the analytic-text cache. All
  3,825 entries are current under this parser and these rules.
* **Placement** is t11's `heading_placement`: the nearest placed heading by t02's matcher, with the
  team's own names and the caselist's schools taken out. No second placement was written.
* **Card placements under a K** are t02's classifications from the same dry run.
* **The new labels** (advocacy, `The 1AC is`, method, K-aff headings) were read the way t11 reads its
  labels:
  * each source was parsed in memory from the blob store under a placeholder path (`blob_jobs`);
  * its paragraphs were read with `section_paragraphs_of`;
  * a label is a non-evidence paragraph of at most 8 words, normalized by t01's normalizer, or a
    sentence or inline opening.

**The families** are a word count, not a placement: whole-word phrases in a file's normalized headings
and in its card tags. They are listed under [the families](#the-k-families).

**The control.** The same reader read the 1,205 files of the identified affirmative rounds, to show
how specific each marker is.

### The files of the unidentified rounds

| | Files | Unidentified rounds | Teams |
|---|---|---|---|
| **All files of the 709 rounds** | **565** | **709** | **203** |
| t09 verdict `NONE`: no `should` plan text | **555** | 692 | 199 |
| `CONFLICTING` (two affs named) | 7 | 9 | 4 |
| `UNNAMED` (a plan text naming no aff) | 2 | 8 | 2 |
| `NAMES` (in a round whose other file conflicts) | 1 | 1 | 1 |
| Parsed again with no failure | 565 | | |

The 555 no-plan files, by what their headings place (t11's placement over each file's distinct
section paths):

| What the headings place | Files | Unidentified rounds | Teams |
|---|---|---|---|
| An advantage, READS | 256 | 304 | 93 |
| Nothing: no heading places anything | 224 | 312 | 124 |
| Negative positions only (DA, CP, K, T, theory), read or answered, and no advantage | 75 | 78 | 22 |

* 5 of the 555 files are also disclosed in a negative round.
* 90 no-plan files have a heading placed under a K, READS. 55 of them also have an advantage heading
  and 65 a DA or CP heading, so they are mostly aff answer files. Only 12 files (10 teams) hold K
  headings and no advantage, DA, CP or aff heading.

### K-aff markers

Over the 565 files, then the 555 with no plan text. A file counts once per marker:

| Marker | Files | Unidentified rounds | Teams | Of those, files with no plan text |
|---|---|---|---|---|
| Role of the ballot (t11's reader) | 15 | 16 | 11 | 15 |
| Advocacy-statement label | 2 | 4 | 2 | 2 |
| `The 1AC is` | 5 | 7 | 5 | 5 |
| Method label (`Method`, `Our method is`) | 5 | 5 | 5 | 5 |
| K-aff heading (`K aff`, `Kritikal aff`, `Critical aff`, `Performance aff`, `Method aff`) | **0** | 0 | 0 | 0 |
| **Any marker** | **25** | **28** | **21** | **25** |

* **Overlap:** 13 files hold a role of the ballot only, 5 a method label only and 5 `The 1AC is`
  only. The 2 advocacy files also hold a role of the ballot.
* **The forms found:**
  * role of the ballot: 12 sentences (`The role of the ballot is ...`), 3 inline, 2 labels;
  * advocacy: the label `Advocacy statement` twice. No `Advocacy` on its own, no `Our advocacy is`
    sentence and no inline `Advocacy:` in these files;
  * `The 1AC is`: 5 sentences;
  * method: `Our method is` in 4 paragraphs, `Method` alone in 2.
* **Left out: `Methods`.** It is in 11 paragraphs of the unidentified files, 8 of them under an
  advantage heading. In the control, all 8 files with the label have a plan text naming an aff.
  It is a policy aff's label, not a K aff's. With it, the method row would be 16 files and 15 teams.
* **Advocacy statements are counted, never shown** (data-use policy 1.13). No advocacy text was
  read into a scratch file or printed.

**Where the markers sit.** By t11's placement, in paragraphs:

| Marker | Headings place nothing | No heading | Placed under an advantage | Placed under a K |
|---|---|---|---|---|
| Role of the ballot (17) | 13 | 4 | 0 | 0 |
| Advocacy statement (2) | 2 | 0 | 0 | 0 |
| `The 1AC is` (5) | 3 | 1 | 1 | 0 |
| Method (6) | 3 | 2 | 0 | **1** (`Our method is`) |

**What else the 25 files hold:**
* 2 carry an advantage heading, READS, and none a DA or CP heading;
* 1 is also disclosed in a negative round, and every one has cards in the store;
* 1 holds a t11 K alternative reading.

**The control.** Of the 1,205 files of the identified rounds, 5 hold a K-aff marker under the
proposed list ([question 2](#questions-for-the-pm)), by 5 teams:
* a role of the ballot 3, an advocacy label 1, `The 1AC is` 1, a method label 0;
* 2 of the 5 have a plan text naming an aff.

The counting pass took any short label holding the word, so it also found two that the proposed list
does not match: a theory interpretation heading holding `advocacy`, and a method label naming its
method. They are left out of the 5. In the unidentified files every label found is on the list, so the
25 stand.

So a marker without a plan text is rare in a file whose round already has an aff (3 files). In the
unidentified rounds it holds in 25.

### Placed under a K by its alias

Of the 25 marker files with no plan text:

| | Files | Teams |
|---|---|---|
| The marker itself placed under a K (t11's placement) | **1** | 1 |
| Any heading of the file placed under a K, READS | 2 | 2 (cap-k, racial-capitalism-k, buddhism-k between them) |
| A card t02 placed under a K by `ALIAS` | 2 | 2 |

All 14 K positions of taxonomy 1.2.0 are on the negative side, and their aliases are `<name> k`
headings (`cap k`, `set col k`). A K aff's 1AC does not head itself that way, so the matcher seldom
places one.

### The K families

Whole-word phrases in the 25 files' normalized headings and card tags:

| Family | Files naming it in a heading | In a tag | Teams (heading or tag) |
|---|---|---|---|
| cap (capitalism, marxism) | 1 | 4 | 5 |
| biopolitics (biopower, necropolitics) | 0 | 4 | 4 |
| colonialism (coloniality, decolonial) | 1 | 6 | 3 |
| disability (ableism, crip, debility) | 0 | 3 | 3 |
| feminism | 1 | 3 | 3 |
| settler colonialism (set col) | 1 | 3 | 2 |
| antiblackness | 0 | 2 | 2 |
| pessimism | 0 | 2 | 2 |
| neoliberalism | 0 | 2 | 2 |
| afropessimism | 0 | 1 | 1 |
| racial capitalism, buddhism, nietzsche, ontology, deleuze | 1, 1, 1, 1, 0 | 0, 0, 1, 1, 1 | 1 each |

* **18 of the 25 files (15 teams) name a family somewhere. Only 4 name one in a heading.**
* A tag that names a family is weak evidence of which K an aff reads: an aff answer file names
  capitalism in tags as well.
* Over all 555 no-plan files, 118 name a family in a heading, but 90 of those headings are K
  headings in answer files ([above](#the-files-of-the-unidentified-rounds)).

### The teams behind each

* **Any marker:** 21 teams.
* **By marker:** role of the ballot 11, `The 1AC is` 5, method 5, advocacy statement 2.
* **Carry:** the 21 teams have 55 unidentified affirmative rounds in all. 28 of them hold a marker
  file.
* **Per family,** in the families table.
* No school or team code is in this report, the scratch files, or anything printed.

### Runtimes

| Pass | What it read | Wall-clock |
|---|---|---|
| Pass 1: the dry run, its inputs and the caches | the run (no parse) | 52.9 s for the dry run, 55.5 s in all |
| Pass 2 sample (1 shard of 20) | 29 files | 33.7 s (29.6 s reading the seed sources) |
| Pass 2, unidentified files, 2 shards, 7 workers | 565 files | 55.7 s and 56.0 s, each about 28 s of seed reading and 28 s of parsing |
| Pass 2, control, 4 shards, 7 workers | 1,205 files | 65.3, 63.8, 66.4 and 61.5 s |
| Tables | the scratch JSON | under 1 s |

**One rerun.** The first full pass 2 checked a file's negative disclosure against lower-case side
values, but `Side` is upper-case. So it found 0 negative files. I fixed the check and ran both
unidentified shards again. Every count above comes from those reruns and the control that followed.

## The options

**(a) One generic K-aff position per topic.** For example, `kritikal-aff`, labelled "Kritikal
affirmative": kind `aff`, side `aff`, no aliases.
* It is identified by the markers in a file with no plan text, as a new assignment method beside
  `PLAN_TEXT` and `TEAM_CARRY`.
* The report shows it as its own group in the Affirmative part.
* **Today it would take 28 rounds (21 teams).** That is 55 rounds if the identification carries to a
  team's other unidentified rounds as `TEAM_CARRY` does, with t09's guard.

**(b) K-aff positions named by the K they read,** as t09's mechanisms are.
* **They need new ids.** The 14 Ks are released with side `neg`, and t08's lock refuses a released id
  whose side changes. So these would be new `aff`-kind positions, such as `cap-kritikal-aff`.
* **The headings cannot name them:**
  * 1 marker is placed under a K;
  * 2 files have a heading placed under a K;
  * 4 files name a family in a heading.
* Naming them from tag words would be a second placement, which the PM's context rules out. Without
  it, almost every K aff falls back to an unnamed one.
* Spread by tag words, 15 families share 15 teams, and the largest, cap, has 5.

**Position kinds.** Neither option needs a new kind.
* A K aff is an affirmative case, and the `aff` kind already carries what the report needs:
  * t03's `_assignments` refuses an assignment to a position that is not an aff;
  * t15's advantages-by-aff section keys on aff positions.
* A new `PositionKind` would change the enum, the lock's recorded kinds and every kind switch in the
  report, for no count it would change.

**Either option is a taxonomy bump**, from 1.2.0 to 1.3.0. 1.2.0 is released, and the lock refuses a
position added at a released version. The bump changes the keys of three caches, so the first run
after it reads everything again. That is an operator block:
* t02's classifications;
* t09's plan texts, whose vocabulary digest covers the taxonomy (204 s on 2026-10-23);
* t11's analytic texts, whose rules digest covers it (551 s on 2026-10-24 under load).

## Files changed

* **`config/landscape`:**
  * `taxonomies/policy-2026-27-nhi.yaml` (1.3.0, `kritikal-aff`) and `topics.yaml` (1.3.0);
  * `kritikal_affs/policy-2026-27-nhi.yaml` (new).
* **`debate_core.arguments.landscape`:**
  * `kritikal_aff.py` (new);
  * `aff_assignment.py` (the two methods and the guard), `plan_text.py` (the vocabulary), `render.py`
    (the section and rows);
  * `analytic_texts.py` (three names made public, behaviour unchanged).
* **`debate_core.application`:**
  * `landscape_kritikal.py` (new);
  * `aff_assignment.py`, `plan_texts.py`, `landscape_report.py`, `landscape_run.py`;
  * `ports/plan_text_store.py`, `ports/taxonomy_repository.py`.
* **`debate_core.domain`:** `landscape_report.py` (`KritikalAffs`, `KritikalFamilyCount`).
* **`debate_core.integrations.landscape`:** `yaml_taxonomy_repository.py` (the loader).
* **Tests:**
  * `packages/debate_core/tests`: `arguments/landscape/test_kritikal_aff.py` and
    `integrations/landscape/test_kritikal_aff_files.py` (new);
  * `arguments/landscape/test_aff_assignment.py` and `test_plan_text.py`;
  * `application/test_landscape_report.py`, `test_aff_assignment.py`, `test_plan_texts.py` and
    `test_landscape_run.py`;
  * `integrations/landscape/test_plan_text_store.py`;
  * `tests/config/test_landscape_taxonomies.py`; `tests/scripts/test_assign_landscape_affs.py` and
    `test_landscape_dry_run_by_section.py`.
* **`tests/fixtures/landscape/kritikal_affs/`** (new, by hand): `README.md`, `taxonomy.yaml`,
  `rounds.yaml`, `report_section.md`, `method_table.md`.
* **`scripts/assign_landscape_affs.py`**, and **`scripts/landscape_dry_run_by_section.py`** with its test
  in `tests/scripts` (after the build's rulings).
* **`docs/guides/landscape-taxonomy.md`:** a section on kritikal affirmatives.
* **The spec:** the PM's rulings as a comment above `acceptanceCriteria`, and the Goal's phase.

`uv run scripts/validate_specs.py` after the phase was set: OK.

## Deviations from the spec

1. **Files outside `constraints.packages`,** each needed by a ruling or by the wiring, as for t09 and
   t11:
   * `debate_core.integrations` (the K-aff file's loader);
   * `scripts/assign_landscape_affs.py` and its test in `tests/scripts`. The script must read the same
     vocabulary as the run, or it would fill a plan-text cache the run never hits.

   The dry-run script (`scripts/landscape_dry_run_by_section.py`) and its test joined these after the
   build's rulings.

   **Ruled 2026-10-25: amended.** The PM adds `debate_core.integrations`, `scripts` and `tests/scripts`
   to `constraints.packages` in the next PM batch, with a ruling comment, as for t09 and t11. The
   session does not touch the spec for it.
2. **The control row counts rounds and names its files.** Ruling 2 asked for "marker files among
   identified rounds" in the method table, whose column is rounds. So the row gives the rounds, and its
   label gives the files ("a control: 2 files" in the fixture).

## Decisions and assumptions

1. **A K aff never moves an existing assignment.** `KRITIKAL_AFF_MARKER` and `KRITIKAL_AFF_CARRY` run
   after `PLAN_TEXT` and `TEAM_CARRY` and fill only rounds those leave open. A marker round of a team
   whose other rounds name a policy aff is that aff's `TEAM_CARRY`, as before.
   * This keeps the 1,483 identified rounds of 1.2.0 where they are.
   * The control counts how often a marker sits in such a round.
   * **Ruled 2026-10-25: (a).** A K aff never moves an existing assignment.
   * The control row from the dry run after the refill goes on record, by method. Its `TEAM_CARRY`
     share is the size of what (b) would move. The PM decides on (b) from that number, as a later
     task if at all.
2. **"A file with no plan text" is read per round.** Every file of the round must have t09's `NONE`
   verdict and one of them a marker, as t09's carry guard reads a round. A round whose other file holds
   an unnamed plan text is a policy round. **Measured after the refill: it leaves out no unidentified
   round** ([the real store](#the-real-store-after-the-refill-2026-10-25)).
3. **A round t02 placed under an aff** is left to the report's `PLACED_CARD`, whatever its markers, as
   t09 leaves it.
4. **The advantage guard reads t15's placement:** a card t02 placed under an advantage, READS, at or
   above the review threshold, in one of the round's own files. A card below the threshold refuses
   nothing, and a mutant checks that.
5. **The guard applies to the carry only,** as ruled. A round with its own marker reads the K aff even
   when it reads an advantage, and the K aff's advantages then show under it in Advantages by
   affirmative.
6. **The families count the files of the K-aff rounds,** own marker and carry alike, and only their
   pocket, hat and block headings:
   * ordered by files, then teams, then the config's order;
   * a longer phrase first, so `racial cap` is not also `cap`.

   The 20 families and their phrases are my proposal. The coach is editing them (ruling of 2026-10-25),
   and the report finishes with the list as it is. They are the 14 Ks of 1.2.0
   by their own words, and afropessimism, neoliberalism, feminism, Baudrillard, Deleuze, Nietzsche and
   anthropocentrism. `security` reads only `securitization`, because "security" heads health headings.
7. **A label counts only over a text,** as t11's labels do: `Advocacy` or `Method` over a heading or
   at the end of a file is no marker.
8. **No marker's words are kept or shown.** The cache keeps the kind (`ADVOCACY`), the form, the place
   and the unit. The report says that markers are counted, never quoted (policy 1.13).
9. **The seam's return type changed** from a sequence of assignments to `AffAssignmentsForReport`,
   assignments and K-aff inputs. One fake in `test_landscape_run.py` was updated.

## Operator follow-ups

The PM's ruling of 2026-10-25 on the build's questions set this order. The coach's list does not hold
up the refill or the dry run.

**Done on 2026-10-25:** steps 2 and 3, the refill (37.6 + 221.7 + 412.9 s) and the dry run (71.8 s),
with `tests/config` first (60 passed). The output is
[above](#the-real-store-after-the-refill-2026-10-25). **Step 1, the coach's edit, done the same day:**
`tests/config` passed, the edit was committed (`bb2e248`), and the plan-text step and the dry run were
run again ([after the coach's K families](#after-the-coachs-k-families-2026-10-25)).

1. **The coach's K families.** The file is
   `~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t17-kritikal-affirmatives/config/landscape/kritikal_affs/policy-2026-27-nhi.yaml`.
   It counts the K families named in the K-aff files' headings, in one line of report.md. It never
   places anything.

   **The coach may:**
   * rename a family (its `label`, or its `id` in lowercase kebab case);
   * merge two families into one, add one, or drop one;
   * change a family's heading words (`phrases`): lowercase words, each phrase in one family only, a
     longer phrase matched first.

   **He may not:**
   * write a school, a team code or a tournament word anywhere in the file;
   * change `schema_version`, `topic_id` or `position_id`.

   After his edit, from the task worktree:

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t17-kritikal-affirmatives
```

```bash
uv run pytest tests/config
```

   **Success looks like:** every test passed, with 0 failed. A failure names the file and the phrase.
   * The edit comes back on this branch before the pull request. The session then runs
     `tests/config`, commits it and records it in this report.
   * An edit to the file changes the plan-text cache's key. If it lands after the refill below, run
     the refill's `assign_landscape_affs.py plan-texts` step once more before the dry run (about 204
     s).

2. **Refill the three caches under taxonomy 1.3.0** (ruling 1). Expected runtime: about 6 to 14
   minutes.
   * The classifications are read again in process.
   * The plan texts parse every affirmative file: 204 s on 2026-10-23.
   * The analytic texts parse every on-topic file: 551 s under load on 2026-10-24, about 2 to 4 minutes
     idle.

   **Local only:**
   * it writes under `~/.debate-research/dev/landscape/` alone: the classification cache and the
     review queue, the plan-text cache, and the analytic-text cache;
   * nothing is published, and nothing is written to a bucket before the cloud cutover's seed;
   * it prints counts only.

   It refuses to start if a `DEBATE_*` variable is set or a `caselist pull` is running. From the task
   worktree (the `cd` above):

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run python scripts/classify_landscape_positions.py classify --caselist hspolicy26 --snapshot 2026-10-20 && uv run python scripts/assign_landscape_affs.py plan-texts --caselist hspolicy26 --snapshot 2026-10-20 && uv run python scripts/read_landscape_texts.py --caselist hspolicy26 --snapshot 2026-10-20; fi
```

   **Success looks like:**
   * a `Classified hspolicy26 on policy-2026-27-nhi 1.3.0` line, with `Sources` above zero;
   * `Plan texts: 1770 sources, 0 cached, 1770 parsed`, then a `K-aff markers:` line whose count is
     above zero;
   * `Analytic texts: 3825 sources, 0 cached, 3825 parsed, ... cache written`;
   * each script's `Runtime` line.

   A `STOP:` line means nothing ran. A failure stops at the script that failed (the `&&`). Paste every
   line back.

3. **Then the dry run, printing the counts and the method table, control row included.** It is the
   landscape service as a dry run without `--publish`, so it is read-only and takes no bucket lock.
   Expected runtime: about 75 s on the warm caches. It prints counts and ids only, never a text, team
   or school. The session can run it itself once the refill is done. Or paste, from the task worktree:

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run python scripts/landscape_dry_run_by_section.py --caselist hspolicy26 --snapshot 2026-10-20; fi
```

   **Success looks like:**
   * `Dry run of hspolicy26 through 2026-10-20, taxonomy 1.3.0: nothing written; 7 files planned.`;
   * `Affirmative rounds by method: ...`, with `KRITIKAL_AFF_MARKER` above zero, and `not identified N
     of 2192` with N below 1.2.0's 709;
   * the `Kritikal affirmatives (kritikal-aff): ...` line: rounds by own marker and by carry, and those
     refused by the advantage guard;
   * the `Control: ... by method: ...` line. Its `TEAM_CARRY` count is what option (b) would move, for
     the record;
   * the `K families in the K-aff files' headings: ...` line;
   * the scan lines, as before.

   Paste every line back. A `Refused:` line means the run did not start, and says why.
4. **The publish with this group** waits for the cloud cutover's seed (ruling 1): no dev bucket writes
   before then.

## Follow-up work

* **The unlabelled-plan policy affs** (ruling 4): 256 files, 304 rounds, 93 teams in the counts, about
  43% of the 709. The PM files the task. The advantage guard keeps the K aff out of those rounds until
  then.
* **The real-store numbers** come after the refill: K-aff rounds by marker and by carry, the guard's
  refusals, the families, the control by method, and the rounds still unidentified. They are measured
  in the dry run ([Operator follow-ups](#operator-follow-ups) 3).
* **The method sentence.** The approved `Our method is` matches no file of hspolicy26. The counts'
  wider pattern (`The`, `Our` or `My` with `method` or `methodology`, then `is`, `will` or `should`)
  found 3 more K-aff files that way. Widening the sentence is the PM's to rule, with its own count.
* **Option (b),** a round's own marker beating its team's carry, is the PM's to decide from the
  control's `TEAM_CARRY` count, as a later task if at all.
* **The CLI's JSON** does not carry the group's counts yet. The run's report carries them
  (`LandscapeReport.kritikal_affs`), for `landscape report --json` to print if the PM wants them.

## Questions for the PM

None open.

### The questions of 2026-10-25 on the build, answered

The PM ruled the same day:
1. `constraints.packages` amended in the next PM batch (Deviations 1);
2. precedence (a), with the control row by method on record from the dry run (Decisions 1);
3. the K family list to the coach, not waited for ([Operator follow-ups](#operator-follow-ups) 1).

Kept as asked:

```text
v1-e32-t17 questions (session, 2026-10-25, after the build). Built as ruled:
kritikal-aff in taxonomy 1.3.0 (released-ids check passes), the approved
markers, KRITIKAL_AFF_MARKER and KRITIKAL_AFF_CARRY with t09's guard and the
advantage guard, report.md's Kritikal affirmatives group after Advantages by
affirmative, and the method table's refused and control rows. Tests red
first; 14 mutants, all caught (one equivalent check removed, one test added).
The real store needs the operator's cache refill first (one block in the
report), then the dry run.

1. Files outside constraints.packages: debate_core.integrations (the K-aff
   file's loader), scripts/assign_landscape_affs.py and its test in
   tests/scripts. The script's vocabulary must match the run's, or it fills
   a plan-text cache the run never hits. Amend the list with a PM-ruling
   comment?
   Recommendation: yes, as for t09 and t11.

2. Precedence: a K aff never moves an existing assignment. A marker round
   of a team whose other rounds name a policy aff stays that aff's
   TEAM_CARRY, and the control row counts such rounds. Options:
   (a) keep it: 1.2.0's 1,483 identified rounds do not move;
   (b) let a round's own marker beat the team's carry, and let a team with
       a K-aff round and a policy aff disagree, carrying neither.
   Recommendation: (a). The control row shows the size of what (b) would
   move, measured in the dry run after the refill, before deciding.

3. The 20 K families in config/landscape/kritikal_affs/policy-2026-27-nhi.yaml
   (the 14 Ks of 1.2.0 by their words, plus afropessimism, neoliberalism,
   feminism, Baudrillard, Deleuze, Nietzsche, anthropocentrism) are my list.
   Send it to the coach to edit, as the CP actors were?
   Recommendation: yes. tests/config checks his edit, and an edit re-reads
   the affirmative files once.
```

### The questions of 2026-10-25 on the counts, answered

The PM ruled the same day: (1) option (a); (2) the markers as proposed; (3) carry yes, with the advantage
guard; (4) a follow-up task. Kept as asked:

```text
v1-e32-t17 counts (session, 2026-10-25). Read-only, local store only,
nothing written (17 files checksummed before and after), counts only.
hspolicy26 through 2026-10-20, taxonomy 1.2.0. Rounds and affs are the
dry run's own (t03 count over t09's assignments): 709 of 2,192 affirmative
rounds have no identified aff; they disclose 565 files by 203 teams, and
555 of those files have no `should` plan text (t09 verdict NONE).

K-aff markers in those 555 files (t11's ROB reader; the new labels read
as t11 reads labels; placement is t11's heading_placement):
  role of the ballot          15 files, 16 rounds, 11 teams
  advocacy statement label     2 files,  4 rounds,  2 teams (both also ROB)
  "The 1AC is"                 5 files,  7 rounds,  5 teams
  method label                 5 files,  5 rounds,  5 teams
  K-aff headings               0
  any marker                  25 files, 28 rounds, 21 teams
Control: 5 of the 1,205 files of identified rounds hold a marker on the
list in question 2 (2 with a plan text naming an aff).
Placed under a K by its alias: the marker itself 1 file; any heading of
the file 2; a card t02 placed under a K by ALIAS 2.
Families: 4 of the 25 name a K family in a heading; 18 (15 teams) in a
tag, across 15 families, the largest cap with 5 teams.
The rest of the 555: 256 files (304 rounds, 93 teams) carry advantage
headings, so they are policy affs with an unlabelled plan; 224 (312
rounds) place nothing; 75 (78 rounds) place only neg positions.

1. Option (a) or (b)?
   (a) one generic K-aff position per topic (say `kritikal-aff`, kind
       aff, side aff, no aliases), identified by a marker in a file with
       no plan text, as a new assignment method beside PLAN_TEXT and
       TEAM_CARRY, shown as its own group in the Affirmative part
       (t15's advantages-by-aff section as the model for where it sits);
   (b) K-aff positions named by the K they read: new aff-kind ids (the
       released Ks are side neg and the lock refuses a side change),
       named from headings, which name a K in 2 of 25 files; naming from
       tag words would be a second placement.
   Neither needs a new position kind: `aff` fits, and t03 refuses an
   assignment to a non-aff. Either is a taxonomy bump 1.2.0 -> 1.3.0
   under t08's lock (1.2.0 is released), which re-keys three caches:
   the first run after it re-reads classifications, plan texts (204 s)
   and analytic texts (551 s under load) - one operator block.
   Recommendation: (a). The headings cannot name the K, and (b) would
   split 21 teams over 15 families, most of them one team's.

2. The markers that identify a K aff, in a file with no plan text:
   t11's role-of-the-ballot labels; `Advocacy`, `Advocacy statement`,
   `Our advocacy (statement) is`, inline `Advocacy:`; `The 1AC is`;
   `Method` on its own, `Our method is`, inline `Method:`. Left out:
   `Methods` (11 paragraphs, 8 under an advantage; in the control all
   8 files with it name an aff by plan text). Approve the list?
   Recommendation: yes. `Methods` belongs to policy affs.

3. Carry: should a K-aff identification carry to the same team's other
   unidentified rounds, as TEAM_CARRY does (never into a round whose
   own plan text names an aff)? Without carry 28 rounds; with it at
   most 55, the 21 teams' unidentified rounds in all.
   Recommendation: yes, through t09's carry rule and guard, so a K aff
   and a policy aff are carried alike; the method table counts K-aff
   rounds by own marker and by carry.

4. Out of scope, for a decision: 256 of the 555 no-plan files (304
   rounds, 93 teams) carry advantage headings, so they are policy affs
   whose plan text sits under no label t09 reads. That is about 43% of
   the 709, far more than K affs. A follow-up task (t09's plan-text
   rule, or an aff identified by its advantages)?
   Recommendation: yes, a follow-up task; t17 stays on K affs.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-25

**Notes:**

Built as ruled, measured on the real store, and honest about every count that moved between the
counts step and the build.
1. **ac1 and ac2 pass,** and so does the node's criterion.
   * The goldens are hand-written from a hand-written fixture.
   * Every suite was red for its reason, with the passes explained as controls.
   * The released-ids check passes, with the 1.1.0 and 1.2.0 locks unchanged.
2. **Mutants: 14.** The one equivalent check was removed with a comment saying why, and the other
   survivor got a test. That is agreement 8 applied exactly.
3. **The real store, after the operator's refill:**
   * 40 rounds by 19 teams are K affs, 31 by their own marker and 9 by carry;
   * unidentified rounds fall from 709 to 669 of 2,192;
   * `PLAN_TEXT`, `TEAM_CARRY` and `PLACED_CARD` are unchanged;
   * no scan hit is in the new section.

   The 28-to-31 difference is explained to the round: three fewer method files, because only the
   approved wording counts, and one more `The 1AC is` file, read in any unit, which is disclosed in six
   rounds.
4. **Option (b) is closed.** The control's `TEAM_CARRY` share is 2 rounds, which is not worth a rule
   that would also make teams disagree. No task is filed.
5. **The method sentence is not widened now.** The approved `Our method is` matches no file today, and
   the wider pattern's 3 files need their own control count. Revisit it with `v1-e32-t24`'s counts,
   which read the same no-plan files.
6. **The advantage guard's 17 refused rounds** are `v1-e32-t24`'s, as ruling 4 meant.
7. **Deviations 1 and 2 accepted.** The PM amends `constraints.packages` (`debate_core.integrations`,
   `scripts`, `tests/scripts`) in a PM batch. The control row gives rounds, with its files named in
   the label.
8. **Decisions 1 to 9 accepted,** including:
   * the per-round "no plan text" rule, which leaves out nothing today, as measured;
   * the guard on the carry only;
   * families from pocket, hat and block headings, longest phrase first;
   * `security` read as `securitization` only;
   * no marker's words kept.
9. **The affected set** (210 files) stopped at 69% with no failure, so it is left to the PR's `ci` under
   agreement 10.
   * The application suite passed in full: 3,783 tests.
   * One `debate_cli` failure under load, in `v1-e40-t06`'s `test_restore_run_state.py`, passed alone
     in one process. That matches t06's own note on that file's SQLite state. CI decides.
10. **Before the PR:** the coach's edit to the K families, `tests/config`, then the plan-text step once
    more (about 204 s) and the dry run, recorded here.
11. **The publish:** one republish after the cutover's step 9, never between the seed and step 8. It
    carries this group and `v1-e32-t23`'s team links together.

The Goal is `Succeeded`, and the PR merges in full after the coach's edit is committed. No re-review is
needed.
