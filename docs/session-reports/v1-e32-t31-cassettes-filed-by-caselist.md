# Session report: v1-e32-t31-cassettes-filed-by-caselist

| | |
|---|---|
| Task | `v1-e32-t31-cassettes-filed-by-caselist` — Model cassettes name their caselist, so one season's recordings can be deleted alone |
| Spec | [`plan_specs/v1/e32-argument-landscape/t31-cassettes-filed-by-caselist.yaml`](../../plan_specs/v1/e32-argument-landscape/t31-cassettes-filed-by-caselist.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t31-cassettes-filed-by-caselist` |
| Session status | COMPLETE |

## Summary

Each model cassette now carries a top-level `caselists` list naming the caselists it was recorded or
replayed for, and the list sits outside the replay key and the match. The landscape's model stage
files each call under the caselist it runs on (`filed_under`, a context variable in
`debate_core.application.cassette_filing`). Record mode writes that caselist beside the ones the file
at that key already named. Replay adds the caselist to a cassette that does not name it yet, through
the same atomic writer, and leaves every recorded value as it was. `caselist_cassettes` and
`delete_caselist_cassettes` list and delete one caselist's cassettes. A cassette only that caselist
names is deleted. A shared one loses only that name and is kept. An unattributed one (recorded before
this task) is reported and never deleted. Annual-purge step 4 now runs a guarded heredoc script that
does the same over the files, and a test checks it against the application delete byte for byte, in
place of the old `rm -r` of the whole cassette directory. The cassette format stays 1, and both
directions of compatibility with the Mac's build `v1.1.0-dev.200` were checked with that build's own
reader and writer. **Look first at** the PM question under Follow-up work: what to do with
unattributed cassettes at a purge.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `cassettes-filed-by-caselist` (Cassettes by caselist) | Done | Red run on a do-nothing skeleton (`18698ca`), implementation (`2343b11`), a withdrawal test the mutant list showed missing (`c8f9e1d`), runbook step and its tests (`69499b4`) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a cassette names its caselist, an older cassette still replays, and one caselist's cassettes can be listed and deleted alone, by tests shown failing first | PASS | **Red first:** at `18698ca`, `.venv/bin/python -m pytest -p no:randomly -n 0 -q --tb=line` over the two new test files and the new stage test → `28 failed, 5 passed`. Every failure is an assertion (13 `DID NOT RAISE ValueError`, 6 `KeyError: 'caselists'`, 2 `DID NOT RAISE FixtureFileError`, 1 `DID NOT RAISE MissingFixtureError`, 6 equality asserts), with no collection or fixture errors. The 5 that passed are invariants a do-nothing skeleton keeps: no caselist means no field, a replay for a caselist already named or for none writes nothing, a call with other parameters misses, an empty directory lists nothing. **Green:** the two new files and the whole stage test file → `47 passed` (16 router, 17 listing and delete, 14 in the stage file). The tests cover: a new recording names its caselist; a replay for a second caselist adds it with every other value unchanged; an old cassette (no `caselists`) replays unchanged and gains the caselist that replays it; the delete removes only the sole-owned cassette, keeps the shared one (it loses only the name and still replays for the other caselist), and keeps the unattributed one |
| Node: Cassettes by caselist tests pass (`uv run pytest packages/debate_core/tests -k cassette`) | PASS | Run as `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest packages/debate_core/tests -k cassette`, the same pytest with the time limit on the interpreter (agreement 10) → `70 passed in 38.43s` |

**Mutants** (agreement 8: each run had a new, empty `HYPOTHESIS_STORAGE_DIRECTORY`, though none of
these tests uses Hypothesis). There were 22, two over the cap of about 20: the three the PM named, 11
more in the code, and 8 in the runbook's script. Every one was caught by a failing assertion.

| Mutant | Caught by (example) |
|---|---|
| (1) The caselist added to the replay key (the key hashed with `filing_caselist()`) | 7 failures, `test_a_replay_for_a_second_caselist_adds_it_and_changes_no_recorded_value` and `test_a_new_cassette_is_the_format_one_shape_plus_its_caselists` among them. 16 tests also errored in the fixture, which replays for a second caselist. The 7 assertion failures are the catch |
| (2) A shared cassette deleted with one caselist | `test_a_shared_cassette_loses_only_the_deleted_caselists_name`, `test_a_caselists_delete_removes_only_the_cassettes_it_alone_names` (3 failed) |
| (3) An unattributed cassette deleted by a caselist | `test_an_unattributed_cassette_is_reported_and_never_deleted_by_a_caselist` (2 failed) |
| A replay adds no caselist | 7 failed |
| A replay rewrites a cassette that already names its caselist | `test_a_replay_for_a_caselist_the_cassette_names_writes_nothing` |
| A recording drops the caselists the file at its key named | `test_the_same_call_for_a_second_caselist_is_the_same_cassette` |
| A recording names no caselist | 14 failed |
| A malformed `caselists` read as none | `test_a_cassette_whose_caselists_are_not_slugs_is_a_fixture_file_error` |
| A withdrawal may leave a cassette unattributed | `test_a_cassette_never_loses_its_last_caselist_to_a_withdrawal` |
| The filing accepts any value | 5 failed (`../hsld26`, `Maple Grove`, …) |
| The delete accepts any caselist value | 4 failed |
| The stage files its calls under no caselist | `test_the_cassettes_a_stage_records_and_replays_name_each_caselist_it_ran_for` |
| A cassette directory deletes any name (`../outside.json`) | 4 failed |
| Shared cassettes listed as sole | 4 failed |
| Runbook: deletes a shared cassette, or an unattributed one, or withdraws nothing, or writes a withdrawn cassette in another layout | `test_the_cassette_delete_does_what_the_application_delete_does` (each) |
| Runbook: reads past a file it cannot read | `test_the_cassette_script_stops_on_a_file_it_cannot_read_and_changes_nothing` |
| Runbook: takes any caselist value | 3 failed |
| Runbook: counts a shared cassette as sole-owned | 2 failed |
| Runbook: step 4 back to `rm -r` of the whole directory | `test_step_4_deletes_cassettes_by_caselist_and_never_the_whole_directory` |

**Compatibility with the installed build.** `git archive v1.1.0-dev.200 packages/debate_core/src`
was exported into the scratchpad, with nothing fetched (the tag was already local). One script recorded
a cassette with one build and replayed it with the other, putting that build's source first on
`sys.path` and printing which `debate_core` it loaded:

```text
== this branch records for synthld26, build 200 replays
debate_core from: <worktree>/packages/debate_core/src
record answered: states-cp
cassette keys: ['call', 'caselists', 'cassette_format', 'key', 'request', 'response'] caselists: ['synthld26']
debate_core from: <scratchpad>/build-200/packages/debate_core/src
replay answered: states-cp
== build 200 records, this branch replays for synthld26
debate_core from: <scratchpad>/build-200/packages/debate_core/src
record answered: states-cp
cassette keys: ['call', 'cassette_format', 'key', 'request', 'response'] caselists: None
debate_core from: <worktree>/packages/debate_core/src
replay answered: states-cp
cassette keys: ['call', 'caselists', 'cassette_format', 'key', 'request', 'response'] caselists: ['synthld26']
```

Both directions hold. Build 200 checks the format, the call, the key, the request and the response,
and reads past `caselists`. This build replays build 200's cassette and adds the caselist. The
committed test `test_a_new_cassette_is_the_format_one_shape_plus_its_caselists` pins what that rests
on: the format is still 1, and a new cassette is the old shape plus `caselists` alone.

**Before the report** (agreement 10):

| Check | Result |
|---|---|
| `uv run scripts/affected_tests.py` | `246 of 580 test files (42.4%) chosen in 13.7 s from 10 changed files`. The root conftest imports `debate_core.integrations.models`, which imports `record_replay` |
| The affected set, run as `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -m "not slow and not live" -q $(cat list)` | **Over the two-minute line**: the alarm stopped it at 73%, with about 5,200 tests passed and none failed by then. Its orphaned xdist workers were stopped. Left to the pull request's `ci` check, which runs the same affected set (the PM's ruling of 2026-10-19), with no hand-off |
| Within two minutes instead: the test directories of what changed plus the always-run list. That is `tests/architecture`, `tests/specs`, the CLI's `test_app.py`, `test_help_rendering.py`, `test_container_factories.py` and `test_landscape_command.py`, `debate_core/tests/integrations/models`, `…/integrations/bedrock`, `…/contracts`, `…/evidence/test_selection_contract.py`, the application's landscape, position-classification, structured-output and cassette tests, and `tests/docs/test_annual_purge_runbook.py` | `1919 passed in 36.88s` |
| `uv run --frozen ruff format --check .` | `1629 files already formatted` |
| `uv run --frozen ruff check .` | `All checks passed!` |
| `uv run --frozen pyright packages/debate_core tests/docs/test_annual_purge_runbook.py` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 19 kept, 0 broken.` |
| `uv run --frozen python scripts/check_thin_handlers.py` | `OK: 68 CLI command and API route handlers within 25 statements` |
| `scripts/check_command_blocks.py`, `scripts/check_links.py`, `scripts/docs_index.py --check-descriptions` | `OK: no # comments in 588 shell code blocks`, `OK: 3008 relative links and anchors`, `All 59 indexed documents under docs/ have a description` |
| `uv run scripts/validate_specs.py` | `OK: 512 files, 40 epics, 450 tasks, 22 releases` |

## Files changed

* `packages/debate_core/src/debate_core/application/cassette_filing.py` (new): `filed_under` and
  `filing_caselist`, the `CassetteFiles` port, and `caselist_cassettes` and
  `delete_caselist_cassettes`.
* `packages/debate_core/src/debate_core/integrations/models/record_replay.py`: `caselists` is written
  on record (merged with the file at that key), added on replay, and validated on read.
  `CassetteDirectory` gains `filings`, `delete` and `withdraw`, which refuse any name that is not
  `<prompt>/<key>.json`. The module docstring has a new section on caselists.
* `packages/debate_core/src/debate_core/application/landscape_model_stage.py`: each guarded call runs
  inside `filed_under(caselist)`.
* `packages/debate_core/tests/…`: `integrations/models/test_cassette_caselists.py` and
  `application/test_cassette_filing.py` (new), and a stage test in `test_landscape_model_stage.py`.
* `docs/runbooks/annual-purge.md`: step 4's cassette dry run and delete are now a per-caselist
  heredoc script, and gap 4 now names only the unattributed cassettes. Step 1, step 9 and gap 6, which
  `v1-e40-t21` edits, are not touched.
* `tests/docs/test_annual_purge_runbook.py`: the script, taken from the runbook and run as the
  operator runs it.
* The spec: the Goal set to `Succeeded`.

## Deviations from the spec

* **`tests/docs/test_annual_purge_runbook.py` is outside `constraints.packages`.** It is where the
  runbook's scripts are tested (`v1-e30-t28`), and the step this task adds to `docs/runbooks` needed
  its tests there. The edit is a section of its own.
* **The runbook's step is a heredoc script over the files, not a command**, as the PM allowed: neither
  `debate_cli` nor the installed build can carry one in this task. It is a second copy of the delete
  rule, so `test_the_cassette_delete_does_what_the_application_delete_does` runs both on copies of
  one directory and requires identical trees, byte for byte.

## Decisions and assumptions

* **The caselist travels as a context variable, not a router parameter.** The `ModelRouter` port is
  unchanged. The stage already knows its caselist, and the record-and-replay router reads it, which is
  the same pattern as `received_answer`. That is why no `debate_cli` change was needed. The variable
  lives in `debate_core.application`, a layer below the integrations that read it.
* **The caselist is not in the key or the match.** `fixture_key` and the request comparison are
  untouched, and a call whose recorded values differ misses under any caselist
  (`test_a_call_whose_recorded_values_differ_misses_under_any_caselist`, plus mutant 1).
* **How the write stays whole.** Every write goes through `write_pretty_json`, the same writer as
  today. It writes a `.partial` file, fsyncs it, renames it into place and fsyncs the directory, so a
  reader sees the old file or the new one, never half of either. The runbook script writes the same way,
  in the same layout. A delete fsyncs the directory after the unlink. One limit: two processes adding
  different caselists to one cassette at the same moment could each read the old list, and the last
  write would win, dropping one name. The stage asks one batch at a time, and a landscape run is one
  process, so this needs two runs over identical cards at once. If it ever happened, the dropped
  caselist's later delete would miss the cassette. The other caselist's delete could then remove a
  cassette the first still replays. The cost is a re-recording: a replay misses with
  `MissingFixtureError`, and no wrong answer is ever replayed. No lock was added for this.
* **A re-recording keeps the names the file at its key had.** The key covers the prompt's variables,
  card excerpts included, so every caselist that named the old file holds the same cards. A file there
  that does not read is replaced, as record mode always did, and its names are lost.
* **A replay writes only when it has something to add.** Replay inside no caselist (every committed
  test cassette) writes nothing, and so does a replay for a caselist already named. Live mode writes
  nothing, as before.
* **A withdrawal never removes a cassette's last name.** `withdraw` refuses with "delete it instead",
  because a cassette with no names is unattributed and no caselist's delete would ever reach it.
* **Only a slug is written.** `filed_under`, the listing and the runbook script refuse anything that
  is not `CASELIST_SLUG_PATTERN` (`^[a-z]+[0-9]{2}$`), so no path, school or team name can get into the
  field. A cassette whose `caselists` holds anything else is a `FixtureFileError`.
* **An unreadable cassette stops the listing and the delete before anything changes**, both in
  `delete_caselist_cassettes` and in the runbook (`STOP: <prompt>/<key>.json …`). A file not named like
  a cassette also stops them.
* **Older builds and attribution.** The installed build never runs the landscape model stage: the
  stage needs `prompts/` from a source checkout, and `landscape_model_stage` refuses otherwise. So
  landscape cassettes are written only by checkout code. If an older checkout re-records a cassette,
  its writer leaves `caselists` out, and the cassette becomes unattributed: kept and reported, never
  deleted by a caselist.

## Operator follow-ups

None.

## Follow-up work

1. **A CLI command**, for example `debate-research landscape cassettes --caselist <slug>` with a
   `--delete` that takes a confirmation, over `delete_caselist_cassettes`. Annual-purge step 4 would
   then call it instead of its heredoc copy of the rule. It belongs in E32 or E30, and in a task that
   lists `debate_cli`.
2. **The model cassettes README** (`tests/fixtures/model_cassettes/README.md`) does not mention
   `caselists`. Committed cassettes never carry it, since they are recorded outside any caselist, so
   nothing there is wrong; one sentence could go in with item 1.
3. **A question for the PM: what happens to unattributed cassettes at a purge.** It is written up for
   relay below.

```text
PM question from v1-e32-t31 (cassettes filed by caselist), 2026-10-31.

Before this task, annual-purge step 4 deleted the whole model-cassettes directory when the purged
caselist had been classified on the Mac. Now it deletes only the cassettes that name that caselist
alone, as you specified, and never an unattributed one (recorded before this task). So an
unattributed cassette that holds a purged caselist's cards is now kept, and only reported (step 4
prints the count; "What has no command yet" item 4 names it).

Options:
  A. Keep it as built: report the count, and the PM decides each time. Friday's (2026-11-06) hsld26
     cassettes and everything after are attributed, so the unattributed set only shrinks.
  B. Add to step 4 a separate, explicit block: when the caselist was classified here and the count of
     unattributed cassettes is above zero, delete the unattributed ones too. That is the old
     behaviour, limited to the old cassettes.
  C. A one-off step now: list the Mac's unattributed cassettes (the step 4 script prints the count
     for any slug), and delete them or re-record them under their caselist before Friday, so there
     are none left.

Recommendation: C, then A. If the Mac holds no landscape cassettes yet, C costs nothing, the purge
never has to choose, and the rule stays the one you wrote. If it holds some, deleting them before
Friday's first attributed recording keeps the retention rule exact. B would bring back a delete that
also removes other caselists' cassettes.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-31

**Notes:**

A cassette now names the caselists it serves, outside the key and the match, and one caselist's
cassettes can be listed and deleted alone.
1. **ac1 passes.**
   * Red: 28 failed and 5 passed, the 5 being invariants a do-nothing skeleton keeps, and every
     failure an assertion. Green: 47 passed, and the node criterion 70.
   * The three PM mutants and 19 more were caught. For mutant 1 the seven assertion failures are the
     catch, not the fixture errors, as you said.
   * The heredoc copy of the delete rule is held byte for byte to the application's on one tree.
     That is the right guard for a second copy.
2. **Compatibility:** both directions were shown with dev.200's own reader and writer. A new cassette
   is format 1 plus `caselists` alone, and a test pins it.
3. **Deviations accepted:**
   * `tests/docs/test_annual_purge_runbook.py`, outside the packages but where the runbook's scripts
     are tested. The PM records it in the packages;
   * the heredoc script in place of a command, as allowed.
4. **Decisions accepted:**
   * the caselist as a context variable, so the router port is unchanged;
   * not in the key or the match;
   * one atomic writer;
   * a replay writing only when it adds a name;
   * a withdrawal never taking the last name;
   * slugs only;
   * an unreadable cassette stopping everything before a change.

   The two-writers race is accepted as stated. Its worst case is a re-recording, never a wrong answer.
5. **Your note that an installed build never runs the model stage** (it needs `prompts/` from a
   checkout) caught an error in the PM's own batch of today. The batch had told the landscape
   runbook's model run to use the installed build. The PM corrects it before that batch merges.
6. **The PM question: C, then A.**
   * The operator counts the Mac's unattributed landscape cassettes now. If there are none, as
     expected, there is nothing to do. If there are some, they are deleted before Friday's first
     attributed recording.
   * After that the purge reports the count and the PM decides, which only matters for cassettes an
     older checkout re-records. B is not taken.
7. **Follow-ups 1 and 2:** one p3 task, a `landscape cassettes` command over
   `delete_caselist_cassettes`, which step 4 then calls, plus the cassette README's sentence.
8. **Closing checks:** the affected set (246 files, through the root conftest) is left to the PR's
   `ci` under agreement 10. 1,919 passed within the two minutes, and the whole-repo checks pass.
9. **Merge:** once the PR's `ci` is green, by Wednesday, so Friday's LD cassettes are attributed. It is
   a plain `scripts/task pr`.

## PM record, 2026-11-01

Added by the PM. Nothing above is changed, and this section is not a review.

**Option C, read.** The operator counted the Mac's landscape cassettes on 2026-10-31: there is no
`~/.debate-research/dev/landscape/model-cassettes` directory, so there are no unattributed cassettes.
Friday's hsld26 recordings will be the first, attributed once this task is in the build that runs
them. Nothing is left to delete, and A governs from here. (Written into the worktree after the pull
request was opened, so it is recorded here instead.)
