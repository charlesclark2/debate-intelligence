# Session report: v1-e32-t44-scan-marked-hits-leave-a-text-clean

| | |
|---|---|
| Task | `v1-e32-t44-scan-marked-hits-leave-a-text-clean` — A scan hit already marked as a JSON key's name or a taxonomy word does not make a text unclean |
| Spec | [`plan_specs/v1/e32-argument-landscape/t44-scan-marked-hits-leave-a-text-clean.yaml`](../../plan_specs/v1/e32-argument-landscape/t44-scan-marked-hits-leave-a-text-clean.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t44-scan-marked-hits-leave-a-text-clean` |
| Session status | COMPLETE |

## Summary

A scan hit marked as a JSON key's name or a taxonomy word no longer makes a text unclean, by the PM's
rulings of 2026-11-05. `marked_scan` (in `debate_core.arguments.landscape.scan_hits`) judges each text
the scan names by its hits' marks: the text is set aside when every hit carries a trusted mark
(`MARKS_THAT_SET_A_HIT_ASIDE`: `json_key`, `in_taxonomy`, the one place they are named) and no keeping mark
(`team_name`, `in_input`), and a listed hit answers for every kind the scan counted in it. `NameScan.clean`
reads the texts left. The evaluation's three scans (prompt inputs, cassettes, repair cassettes) use it,
so the bar reads it. Nothing is hidden: the scan's counts, `breakdown.scan_hits` and the terminal listing
are unchanged, and each `scan` entry of `landscape evaluate --json` gains `set_aside`, the texts and hits
set aside, by mark. Replayed offline at prompt 1.1.0, both kept recordings' scans now read clean: Haiku's
cassettes 27 hits (22 a JSON key, 5 a taxonomy word), Sonnet's 42 (38, 4), all set aside. The PM should
look first at the [Deviations](#deviations-from-the-spec): the CLI's source, the smoke check and the data
doc are outside `constraints.packages`, and the PM's rulings needed all three.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `scan-marked-hits-leave-a-text-clean` (Marked hits clean) | Done | Skeleton first (new fields, `marked_scan` excusing nothing), tests shown red against it, then the rule. The CLI, smoke pin, runbooks and data doc followed. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a text whose hits are all marked as a JSON key's name or a taxonomy word is clean, one with any unmarked or team-naming hit is not, and every hit is still counted by mark, by tests on invented words shown failing first | PASS | **Red, against a skeleton whose `marked_scan` set nothing aside:** `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/arguments/landscape/test_scan_marked_hits.py -n 0 -q --tb=line` → 11 failed, 10 passed, every failure an assertion (`clean` false, `texts_left` None, `set_aside` empty, `sets_aside` false). **Red, the application and CLI tests against the pre-task rule** (`clean` planted back to "no count", and the JSON key removed, on a commit, then restored with `git checkout HEAD --`): the evaluation's two "every hit marked → clean" tests and the CLI's two failed at assertions (`(False, 0) == (True, 0)`; the CLI's exit code and the JSON pin); the guard tests (unmarked, team-naming, in the cards sent) pass under the pre-task rule too, which refused every named text, and the mutants below show each catches a rule that sets too much aside. **Green:** below. **Mutants:** 12 of 12 caught at an assertion ([Mutants](#mutants)). Invented words only: a school `Confidence`/`Rationale` spelled like a cassette key, team codes `OR`/`AB` whose words a position description holds, a tournament `Pinecrest Open`. |
| Node: Marked hits clean tests pass (`uv run pytest packages/debate_core/tests -k scan`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests -k scan -q` → 143 passed in 47 s |
| PM ruling 5: the kept 1.1.0 recordings' scans, both routes, would now read clean (replayed offline, counts only) | PASS | A scratch script ([below](#the-kept-recordings-replayed)) through the evaluation service's own `break_down` at prompt 1.1.0, replay mode, 62 s, nothing written, no model called → `scans_clean` true on both routes |

### The checks before the report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` | 258 of 696 test files (37.1%) from 13 changed files. Over two minutes, so it is left to the pull request's `ci` (agreement 10); not run with `--run` |
| The always-run list: `tests/architecture/ tests/specs/` and the CLI's `test_app.py`, `test_help_rendering.py`, `test_container_factories.py` | 377 passed in 21 s |
| The landscape tests of every changed directory: `packages/debate_core/tests/arguments/landscape/`, `packages/debate_core/tests/application/test_landscape_*.py`, `packages/debate_cli/tests/test_landscape_*.py`, `tests/smoke/test_landscape_evaluate_smoke.py` | 1726 passed in 19 s |
| The other test files importing a changed module: `test_output.py`, `test_coach_sample_relabel.py`, `test_coach_sample_stance.py`, `test_position_classification.py` | 200 passed in 4 s |
| `uv run ruff format --check .`, `uv run ruff check .` | 1949 files formatted; all checks passed |
| `uv run pyright packages/debate_core packages/debate_cli tests/smoke/test_landscape_evaluate_smoke.py` | 0 errors |
| `uv run lint-imports`, `uv run python scripts/check_thin_handlers.py` | 20 contracts kept; 72 handlers within 25 statements |
| `uv run scripts/check_links.py`, `uv run scripts/check_command_blocks.py` | OK |
| `uv run scripts/validate_specs.py` | OK: 619 files |

Every test run was bounded by `scripts/hard_stop.py 115`.

### The kept recordings, replayed

`replay_kept_scans.py` in the session's scratchpad: the container's `landscape_evaluation` (replay, no
route and `deep_audit`) with its stage factory wrapped at prompt version 1.1.0, `break_down` on hspolicy26
at snapshot 2026-10-20 over the coach's sample, printing counts, marks and scores only. No `DEBATE_`
variable was set. Its output, written to [the evaluation's record](../data/landscape-model-evaluation.md#marked-hits-leave-a-text-clean-v1-e32-t44-2026-11-05):

| | Haiku 4.5 (`high_volume`) | Sonnet 4.6 (`deep_audit`) |
|---|---|---|
| Prompt inputs: texts, hits | 3, 0 | 3, 0 |
| Cassettes: texts naming a school / team code / tournament | 3 / 1 / 2 | 3 / 2 / 1 |
| Cassettes: hits; a JSON key, a taxonomy word; a team's name, in the cards sent | 27; 22, 5; 0, 0 | 42; 38, 4; 0, 0 |
| Cassettes set aside (`set_aside`) | texts 3, hits 27 | texts 3, hits 42 |
| Repair cassettes: texts | 0 | 0 |
| `clean`, every scan; `scans_clean` | true | true |

The marks match the recordings' as the PM recorded them (27: 22 and 5; 42: 38 and 4). The scores in the
same run differ from the recorded ones (pipeline 20 of 33 and 25 of 36, model alone 18 of 32 and 25 of 36)
because the coach's sample now carries the relabel: the CSV was modified at 23:51 on 2026-11-04, a minute
before the run, and 10 rows read `at:`. The scan does not read the labels; the scores are not this task's
and are not written into the record.

### Mutants

Each applied to the committed code, the three scan test files run (`-n 0 -x`), and restored with
`git checkout HEAD --`; each was caught by a FAILED assertion, none by an error.

| Mutant | Caught by |
|---|---|
| The keeping marks ignored | `test_scan_of_a_text_whose_marked_hit_names_a_team_is_not_clean` |
| `in_input` no longer keeps a hit | `test_scan_of_a_text_whose_marked_hit_its_cards_sent_is_not_clean` |
| `team_name` no longer keeps a hit | `test_scan_of_a_text_whose_marked_hit_names_a_team_is_not_clean` |
| `json_key` not trusted | `test_scan_of_a_text_whose_every_hit_is_a_json_key_or_a_taxonomy_word_is_clean` |
| `in_taxonomy` not trusted | the same |
| `in_input` trusted too | the same |
| Both trusted marks needed on one hit (`all` for `any`) | the same |
| No check that the listed hits cover every kind counted | `test_scan_of_a_named_text_with_no_hit_listed_is_not_clean` |
| One set-aside hit enough (`any` for `all`) | `test_scan_of_a_text_with_one_unmarked_hit_is_not_clean` |
| Each mark counted as every hit | `test_scan_of_a_text_whose_every_hit_is_a_json_key_or_a_taxonomy_word_is_clean` |
| A text naming nothing not skipped | `test_scan_counts_each_text_alone_one_set_aside_and_one_left` |
| An unjudged scan (`texts_left` None) read as clean | `test_scan_not_judged_by_marks_is_unclean_with_any_count` |

## Files changed

* **`debate_core.arguments.landscape`**: `scan_hits.py` names every mark (`MARKS`, now what `mark_counts`
  counts), the trusted ones (`MARKS_THAT_SET_A_HIT_ASIDE`) and the keeping ones (`MARKS_THAT_KEEP_A_HIT`),
  and adds `sets_aside` and `marked_scan`. `model_stage.py`'s `NameScan` gains `texts_left` and
  `set_aside`, a `named` property, and `clean` reads `texts_left` (None, an unjudged scan, keeps the old
  rule).
* **`debate_core.application.landscape_model_evaluation`**: the three scans are `marked_scan`s, each with
  its own hit listing (`input_batch_hits`, `cassette_hits`, `repair_cassette_hits`) over one `ScanNames`.
* **`debate_cli.commands.landscape`** (Deviation 1): each `scan` entry's `set_aside`; the display adds the
  set-aside count when there is one; the failure message says the names were ones no mark sets aside.
* **Tests**: `packages/debate_core/tests/arguments/landscape/test_scan_marked_hits.py` (new, 22 tests);
  three evaluation tests in `packages/debate_core/tests/application/test_landscape_model_stage.py`; one CLI
  test, one more exit-1 case and two pins in `packages/debate_cli/tests/test_landscape_command.py`; the
  smoke pin in `tests/smoke/test_landscape_evaluate_smoke.py` (Deviation 2).
* **Docs**: the record and replay runbooks say what `set_aside` is; `docs/data/landscape-model-evaluation.md`
  names the trusted marks and records the replay (Deviation 3).

## Deviations from the spec

1. **`debate_cli`'s source.** `constraints.packages` lists `packages/debate_cli/tests` but not its source.
   The PM's ruling 2 asks for the count of what `clean` set aside in the JSON, which
   `debate_cli.commands.landscape` writes. One key per scan entry, the display's suffix and the failure
   message changed there; nothing else.
2. **The smoke check.** `tests/smoke/test_landscape_evaluate_smoke.py` pins each scan entry whole, so the
   new key needed its pin (`set_aside` with zeros). It passes from the checkout (3 passed); the installed
   build was not built for it.
3. **The data doc.** The PM's ruling 3 names `docs/data/landscape-model-evaluation.md` for the trusted
   marks; `docs/data` is not in `constraints.packages` (`docs/runbooks` is). The section and the replay's
   counts went there.
4. **The session's own offline replay** of the kept cassettes (62 seconds, read-only, no model): ruling 5
   asked for it; a read-only command over files on the operator's Mac, which agreement 2 lets a session run.
5. **The affected set** (258 files) was not run: over two minutes, so it is the pull request's `ci`
   (agreement 10). The always-run list and the changed directories' landscape tests ran instead.

## Decisions and assumptions

* **Text by text.** The ruling is about a text: one unmarked hit leaves its text unclean whatever its other
  hits are, and only a text set aside whole counts in `set_aside`. A marked hit in a text that is left is
  counted where it always was and not as set aside.
* **Fail toward unclean.** A named text is set aside only when its listing has a hit of every kind the scan
  counted in it (the listing is built to, `v1-e32-t39`), so a scan count no listed hit answers for still
  makes the scan unclean. A `NameScan` built without judging (`texts_left` None) keeps the pre-task rule.
* **The prompt inputs are never set aside.** Every hit in a prompt input is marked `in_input` (it is in the
  cards it sends), so a taxonomy word in a sent tag still makes that scan unclean. That is the ruling read
  literally; a test pins it. The 1.1.0 inputs had no hit.
* **The trusted marks are a list, not a rule over "every mark but two".** A new mark on `ScanHit` sets
  nothing aside, and `test_scan_trusts_only_the_json_key_and_taxonomy_word_marks` fails until `MARKS`
  lists it, which puts the question in front of a reviewer.
* **The evaluation lists hits only for named texts**, so a clean run lists none and costs what it did.
  A `--breakdown` lists them twice, once for `clean` and once for the listing; three cassettes, seconds.
* **The terminal listing is unchanged** (ruling 2), so it does not mark which hits were set aside.

## Operator follow-ups

None. The 1.2.0 re-record, when it runs, reports `set_aside` beside its scan counts; reading the hits in
the terminal when a count is above zero is still step 5 of the record runbook.

## Follow-up work

* **The display's set-aside note is long.** It names the hits and both marks; the PM may prefer the count
  alone. E32, cosmetic.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
