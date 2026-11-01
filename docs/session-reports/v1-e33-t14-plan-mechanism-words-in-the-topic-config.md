# Session report: v1-e33-t14-plan-mechanism-words-in-the-topic-config

| | |
|---|---|
| Task | `v1-e33-t14-plan-mechanism-words-in-the-topic-config` — A coach-edited list of plan-mechanism words in the topic config marks a CP draft's plan-dependent blocks |
| Spec | [`plan_specs/v1/e33-file-builder/t14-plan-mechanism-words-in-the-topic-config.yaml`](../../plan_specs/v1/e33-file-builder/t14-plan-mechanism-words-in-the-topic-config.yaml) |
| Epic / release | `v1-e33-file-builder` / `v1.2` |
| Branch | `task/v1-e33-t14-plan-mechanism-words-in-the-topic-config` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Each topic can now have a list of plan-mechanism words, `config/landscape/plan_mechanisms/<topic id>.yaml`.
The coach edits it. It loads and is checked with the rest of the landscape config, and the run result
carries it to `files suggest`. hspolicy26's topic (`policy-2026-27-nhi`) is seeded with `preempt`,
`preemption`, `waiver` and `waive`. t11's plank rule now also marks a kept CP-draft block whose heading
holds a listed word as a whole word, **or its plural with `s`/`es`**. The count showed the listed forms
alone were not enough: the coach's waiver block is headed with the plural, so `waiver` missed it (Decision 1).
Following the PM's amendment, a block kept because an aff or an advantage places it now has its own comment.
A block marked both ways gets one comment, the plank one. On hspolicy26, marked blocks go from 6 to 8, and
**both blocks the coach named (preemption and waiver, in the States CP draft) are now marked** by the plank
rule. A topic with no list is not refused and marks exactly what t11 and t13 marked. The affected set
(177 files) ran past the 115-second limit at 65% with no failures. It is left to the PR's CI under
agreement 10. Look first at Decision 1, the plural rule.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `plan-mechanism-words-in-the-topic-config` (Plan-mechanism words) | Done | Before count on the start code (`cb618c4`). Skeleton and tests red (`59f0668`). Implementation (`e38751e`) and guides (`9515379`). Then 8 mutants and the after count |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a topic's plan-mechanism words load with its config | PASS | `test_topic_config_plan_mechanism_files.py`: `test_the_file_loads_as_its_words_in_the_coachs_order`, plus 12 refusals, each naming the file (another topic's name, a topic with no taxonomy, capitals, a digit, a space, a doubled or leading hyphen, under 3 or over 32 characters, a word listed twice, an unknown key, `.yml`). `tests/config`: the committed config loads as one (`test_the_configuration_loads_as_one`), the new file passes the personal-data check, and the directory check allows `plan_mechanisms/` |
| ac1: a CP draft marks a kept block whose heading holds one | PASS | `test_file_suggest_service.py`'s t14 section, a hand-written world (its table is in the docstring). `test_a_block_whose_heading_holds_a_listed_word_or_its_plural_has_the_plank_comment`: `preemption` (listed) and `waivers` (plural of `waiver`) have the plank comment. `test_a_heading_holding_a_listed_word_only_inside_another_word_is_not_marked`: `preemptive federalism` does not. `test_a_listed_word_does_not_hold_in_a_longer_word_that_is_not_its_plural`: with only `waive` listed, `waivers` is unmarked. Also the unit tests in `test_topic_config_plan_mechanism_words.py` (10 that hold, 11 that do not) |
| ac1: a topic with no list behaves as before | PASS | `test_a_topic_with_no_file_loads_and_has_no_words` (the repository loads, and returns None). `test_a_topic_with_no_word_list_marks_only_what_t11_and_t13_marked`: the same world with no file marks only its two advantage blocks. Every t11 and t13 test world has no file, and all of them pass, t11's `test_blocks_naming_a_plank_or_mechanism_of_the_plan_are_marked_and_no_others` unchanged among them |
| ac1: the comments (PM amendment) | PASS | `test_an_advantages_block_has_the_affirmative_comment_and_not_the_plank_one`. `test_a_block_marked_both_ways_has_one_comment_the_plank_one`: `preempt advantage` places an advantage and holds `preempt`, and gets the plank comment with no second comment above it (3 plank comments and 1 aff comment in the file). t13's `test_each_kept_affirmative_side_block_has_the_check_against_the_affirmative_comment_directly_above_it` was changed on purpose, and its docstring says so (Decision 4) |
| ac1: hspolicy26's preemption and waiver blocks are marked, by counts | PASS | "Counts on hspolicy26" below. Before: both were in the states-cp draft and neither was marked. After: both are marked, by the plank rule |
| ac1: tests shown failing first | PASS | "Red run" below: 24 failed, 139 passed against the skeleton `59f0668`, each failure at an assertion |
| Node: Plan-mechanism words tests pass (`uv run pytest packages/debate_core/tests -k "suggest or topic_config"`) | PASS | Run bounded, as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests -k "suggest or topic_config" -q` → `110 passed in 59.82s`. Both new test files have `topic_config` in their names so this command selects them (Decision 5) |

## Counts on hspolicy26

Counted as t11 and t13 did, read-only. The landscape dry run was wired by hand with no plan-text or
analytic-text service, so neither cache is written. It covered hspolicy26 at top 10, through 2026-10-20
(the store's newest weekly), taxonomy 1.4.0, using the suggest service's own functions. **Before** ran on
the start code (`cb618c4`, t13 merged), **after** on the final code. Before each run I touched a marker
file, and after each `find ~/.debate-research/dev -newer <marker> | wc -l` printed `0`. Runs took 48.1 s
(before), and 60.4 s and 53.1 s (after, run twice: the second counted the mechanism reason with the
service's own rule instead of the script's listed-forms-only check). No heading text is quoted.

| Kept blocks in the 13 CP drafts (73) | Before | After |
|---|---|---|
| Marked by a plank label (`plank 2 ...`) | 0 | 0 |
| Marked by an affirmative's alias or tag keyword | 1 | 1 |
| Marked by the plan-mechanism words | (no list) | **2** (1 by a listed form, 1 by a plural) |
| **Marked by the plank rule** (any of the three) | **1** | **3** |
| Kept as affirmative side (t13) | 5 | 5 |
| Marked both ways | 0 | 0 |
| **Marked blocks** | **6** | **8** |
| ...with the plank comment | 6 (all: one comment for both) | 3 |
| ...with the affirmative comment | (none: no such comment) | 5 |

The coach's two blocks are probed as t11 probed them: a kept heading containing `preempt`, and one
containing `waive`, letters anywhere in a word. Each probe finds exactly one block, both in the
states-cp draft. Before: both **not marked**. After: both **marked, by the plank rule**. I also counted,
without printing either heading, what follows the probe inside the word holding it. The preemption
block's word is `preempt` + `ion`, the listed `preemption`. The waiver block's word is `waive` + `rs`,
the plural `waivers`, which no listed form matches as a whole word. Each heading is that one word. That
is why the listed forms alone mark only 1 of the 2 (the before run's "seed words would match: 1") and why
the rule takes plurals (Decision 1). The table's other blocks were neither added nor removed: drafts,
kept blocks and the five affirmative-side blocks are the same before and after.

The count scripts are in the session scratchpad:
`/private/tmp/claude-501/-Users-charlesclark-Documents-debate-debate-intelligence-tool-debate-intelligence-worktrees-v1-e33-t14-plan-mechanism-words-in-the-topic-config/236211df-b644-4add-8dea-1f991b619c6a/scratchpad/counts/cp_draft_marks.py`
(run as `... cp_draft_marks.py config/landscape <scratch> before|after`) and `probe_forms.py` beside it;
the outputs are `before.txt`, `after.txt` and `after2.txt` there.

## Red run

The skeleton (`59f0668`) has the plumbing for real: the model, the loader, the port method, the run
result's field and the new comment constant. But it refuses no word, its matcher returns False, and its
render puts the plank comment above every marked block. Against it:

`.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n 0 -p no:randomly -q -rf --tb=no packages/debate_core/tests/application/test_file_suggest_service.py packages/debate_core/tests/application/test_topic_config_plan_mechanism_words.py packages/debate_core/tests/integrations/landscape/test_topic_config_plan_mechanism_files.py tests/config`
→ `24 failed, 139 passed in 1.80s`. Every failure is an `AssertionError` or a `DID NOT RAISE`:

* the suggest service, 6: the t13 comment test (the plank comment where the aff comment belongs), the
  plank-comment test (no comment above `preemption`), the advantage-comment test, the both-ways test
  (`2 == 3` plank comments), the no-list test, and the `waive`-only test;
* the matcher, 10: every "holds" case;
* the loader, 8: each word refusal and the duplicate refusal.

The new tests that passed at red pin what must not change, or what the skeleton already does for real:
the world's block layout and counts, a word inside another word left unmarked, the DA's draft unchanged,
the draft validating, the loader's no-file and load cases, and the matcher's "does not hold" cases. A
first version of the non-CP test drafted an advantage. In these neg files an advantage has no cards, so it
was refused with `SuggestRefused`, not a failed assertion. I rebuilt it on a DA (`politics-da`, a
`Waivers` block below `Politics DA`) before the run quoted.

## Mutants

Each was applied alone to the final code, the four test paths above were run with
`HYPOTHESIS_STORAGE_DIRECTORY` set to a new empty directory (no Hypothesis test is involved), and the
file was restored from HEAD; the tree was clean after. Script and output:
`/private/tmp/claude-501/-Users-charlesclark-Documents-debate-debate-intelligence-tool-debate-intelligence-worktrees-v1-e33-t14-plan-mechanism-words-in-the-topic-config/236211df-b644-4add-8dea-1f991b619c6a/scratchpad/mutants.py`
(`mutants.txt`, `mutants_3_to_8.txt`).

| Mutant | Result | Caught by |
|---|---|---|
| 1. The word list ignored (`_naming_the_plan` matches against `()`) | 2 failed | the plank-comment test; the both-ways test |
| 2. A word matched inside another word (no word boundaries) | 9 failed | `..._only_inside_another_word_is_not_marked` (`preemptive`), `..._does_not_hold_in_a_longer_word_that_is_not_its_plural` (`waive` in `waivers`), the both-ways test, 6 matcher cases (`waive` in `waiver` among them) |
| 3. A topic without a list refused (the loader raises for a topic with no file) | 60 failed | every test whose world has no file, with `TaxonomyConfigError`, which is the refusal the mutant plants (not a crash elsewhere): `test_a_topic_with_no_file_loads_and_has_no_words`, `test_a_topic_with_no_word_list_marks_only_what_t11_and_t13_marked`, and every t03, t11 and t13 test |
| 4. An advantage block given the plank comment | 5 failed | the t13 comment test, the advantage-comment test, the both-ways test, the no-list test, the `waive`-only test |
| 5. A block marked both ways given two comments (`elif` → `if`) | 1 failed | `test_a_block_marked_both_ways_has_one_comment_the_plank_one` |
| 6. No plural: listed forms only | 8 failed | the plank-comment test (`waivers`), the both-ways test, 6 matcher cases |
| 7. A word listed twice not refused | 1 failed | the loader's duplicate case (`DID NOT RAISE`) |
| 8. The config directory check allows nothing new | 1 failed | `test_the_directory_holds_only_...`: the committed seed file is refused there |

## Checks before the report

* Affected set: `uv run scripts/affected_tests.py` chose **177 of 617 test files** from 14 changed
  files (15.6 s). The run, `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python scripts/affected_tests.py --run`,
  was **stopped at its 115-second limit at 65%** (exit 124), with 3,218 tests passed and none failed or
  errored before the stop. The machine's load was about 13 to 17 from other sessions. The set takes
  longer than two minutes here, so under agreement 10 it is left to the pull request's `ci` check, with no
  hand-off. Within the limit I ran:
  * the affected files in the changed areas (the 42 under `packages/debate_core/tests/application` and
    `integrations/landscape`) plus `tests/config`: `-n auto -m "not slow and not live"` → `1067 passed in 14.72s`;
  * the always-run list (`tests/architecture/`, `tests/specs/`, the CLI's `test_app.py`,
    `test_help_rendering.py` and `test_container_factories.py`) → `372 passed in 19.42s`;
  * every CLI and smoke test naming `files suggest` (`test_bucket_mode_lock.py`, `commands/test_files.py`,
    `test_app.py`, `test_files_suggest_presenter.py`, `tests/smoke/test_files_cli.py`) → `99 passed in 24.39s`.
* `ruff format --check .` → `1711 files already formatted`; `ruff check .` → `All checks passed!`
* `pyright packages/debate_core tests/config` → `0 errors, 0 warnings, 0 informations`
* `lint-imports` → `Contracts: 20 kept, 0 broken.`; `scripts/check_thin_handlers.py` → OK (68 handlers)
* `scripts/docs_index.py --check-descriptions` (61 documents), `scripts/check_links.py` (3191 links),
  `scripts/check_command_blocks.py` (625 blocks): all OK
* `uv run scripts/validate_specs.py` → `OK: 545 files, 41 epics, 482 tasks, 22 releases`

## Files changed

* `packages/debate_core/src/debate_core/application/plan_mechanism_words.py` (new): the file's model
  (`PlanMechanismWords`) and the rule `holds_a_mechanism_word`.
* `.../application/ports/taxonomy_repository.py`: the port's `plan_mechanism_words(topic_id)`.
* `.../integrations/landscape/yaml_taxonomy_repository.py`: `plan_mechanisms/` is read and checked
  with the rest of the config (`PLAN_MECHANISM_DIRECTORY`, `load_plan_mechanism_file`).
* `.../application/landscape_run.py`: the run result carries the topic's words, as it carries the
  taxonomy and overrides for `files suggest`. No count, cache key or digest reads them.
* `.../application/file_suggest_service.py`: the plank rule reads the words, there is a new
  `CHECK_AGAINST_THE_AFFIRMATIVE`, and the render writes one comment per block.
* `config/landscape/plan_mechanisms/policy-2026-27-nhi.yaml` (new): the seed, with a header saying how
  to edit it.
* Tests: `packages/debate_core/tests/application/test_file_suggest_service.py` (t14 section;
  `plant(mechanisms=...)`; t13's comment test changed on purpose),
  `.../application/test_topic_config_plan_mechanism_words.py` (new),
  `.../integrations/landscape/test_topic_config_plan_mechanism_files.py` (new),
  `tests/config/test_landscape_taxonomies.py` (the new directory and a personal-data check over the words).
* Guides: `docs/guides/file-recipes.md` ("Drafting a counterplan file": both comments, the list, where it
  lives, that the coach edits it, how a word matches) and `docs/guides/landscape-taxonomy.md` (a row in
  "Where things are").

## Deviations from the spec

None. The spec allowed a stem rule if I stated it, and Decision 1 states it.

## Decisions and assumptions

1. **Plurals match: a listed word, or the word with `s` or `es`, as a whole word.** The PM's context said
   listed-only was fine unless the count said otherwise, and it did. The coach's waiver block is headed
   with the plural `waivers`, which none of the four seed forms matches whole, so listed-only would have
   marked 1 of the coach's 2 blocks. Nothing else counts as a form of a word. `waive` does not match
   `waiver`, `preempt` does not match `preemption` or `preemptive`, and `waive` does not match `waived`.
   That keeps the PM's mutant 2 a real break, and a coach who wants another form lists it, as the seed
   already lists `preempt` and `preemption`. For a hyphenated word (`opt-out`), the plural attaches to its
   last part (`opt outs`).
2. **Matching uses the block heading as t11 already reads it**: the matcher's normalized form, lowercase
   letters and digits one space apart. A hyphen in a listed word becomes a space, as the normalizer turns
   a heading's hyphen into a space, so `pre-empt` matches a heading `Pre-empt` (`pre empt`).
3. **A word's limits:** lowercase letters with single hyphens between them, 3 to 32 characters. The
   minimum of 3 keeps out a two-letter word, which the config's personal-data check would read as a team
   code's shape anyway. **Duplicates are refused** with the word named (`a word is listed twice: preempt`),
   as the K-family file refuses a phrase listed twice, rather than folded. **An empty list loads**, as no
   words: a coach who clears the list should not break the config. A file still has to be named for its
   topic, be for a topic with a taxonomy, and end in `.yaml`, like its sibling files.
4. **t13's comment test changed on purpose.** It pinned `CHECK_AGAINST_THE_PLAN` above advantage-placed
   blocks. It is now `..._has_the_check_against_the_affirmative_comment_directly_above_it`, and its
   docstring cites the PM's amendment. The new comment is the PM's wording: `# Check this block against the
   affirmative's plan: its heading names an affirmative or one of its advantages.` t11's plank comment text
   is unchanged. t13's non-CP test now also asserts the new comment is absent.
5. **Test file names hold `topic_config`.** The node's criterion runs
   `-k "suggest or topic_config"`, which matches module names too, so both new test files are named
   `test_topic_config_plan_mechanism_*.py` to be selected by it. Their docstrings say why.
6. **Words reach the service on the landscape run's result**, beside `taxonomy` and `overrides`, rather
   than through a new `FileSuggestService` parameter. The service already reads its config that way, and
   a constructor change would have reached `debate_cli/container.py`, outside this task's packages.
7. **Nothing else reads the list**, so an edit needs no refill and no taxonomy bump, and the guides say so.

## Operator follow-ups

None. The affected set is left to the pull request's `ci` check under agreement 10 (it ran past the
two-minute line here), not handed over.

## Follow-up work

* `v1-e33-t15` also edits `docs/guides/file-recipes.md` ("Drafting a counterplan file"). Whichever of the
  two merges second rebases that paragraph, as the PM's context says.
* The command's table and `--json` count what was left out and what was kept as affirmative side, but not
  the blocks marked, or by which rule. If the coach wants to see how many blocks the word list marked
  without opening the draft, that would be a small presenter task in E33, in the files presenter, which
  t15 is in now.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-31

**Notes:**

The coach's two blocks are marked now. The count is what showed the seed alone would have missed one.
1. **ac1 passes.**
   * Red against a skeleton with real plumbing: 24 failed at assertions.
   * Green: the node criterion passes (110).
   * A topic with no file loads and marks exactly what t11 and t13 marked. Every t11 and t13 world
     passes, and t11's marking test is unchanged.
   * Eight mutants caught. Mutant 3, a topic without a list refused, fails 60 tests, which is the
     guard the forbidden item needed.
2. **The count.** It used t11's read-only method, with `find -newer` printing 0.
   * Plank-rule marks go 1 → 3, affirmative-side 5, total 6 → 8.
   * The coach's preemption and waiver blocks were unmarked before and are marked by the plank rule
     after.
   * You found why the seed alone wasn't enough (the waiver heading is the plural) without printing
     either heading.
3. **Decision 1, plurals with `s` or `es`: accepted.** The count asked for it, and it is the narrowest
   rule that does it:
   * `waive` still does not match `waiver` or `waived`, so mutant 2 stays a real break;
   * a coach who wants another form lists it.
4. **Decisions accepted:**
   * matching on t11's normalized heading, with a hyphen read as a space;
   * words 3 to 32 characters;
   * duplicates refused;
   * an empty list loads;
   * t13's comment test changed on purpose, with the PM's wording;
   * test file names that let the node's `-k` select them;
   * the words carried on the run result, so no container change;
   * nothing else reading the list, so an edit needs no refill.
5. **Follow-ups:**
   * file-recipes.md: whichever of t14 and t15 merges second rebases it;
   * the marked-block counts in the presenter: not filed. The coach reads the draft, where the
     comments are.
6. **Closing checks:** the affected set (177 files) stopped at 65% at its limit with nothing failing,
   and is left to the PR's `ci` under agreement 10. The changed areas and `tests/config` (1,067), the
   always-run list (372), every CLI and smoke test naming `files suggest` (99), ruff, pyright,
   lint-imports, thin handlers, the doc checks and the specs are clean.
7. **Merge:** a plain `scripts/task pr` once `ci` is green. To add words, the coach edits
   `config/landscape/plan_mechanisms/policy-2026-27-nhi.yaml` through a task or a PM batch, as a
   config change.
