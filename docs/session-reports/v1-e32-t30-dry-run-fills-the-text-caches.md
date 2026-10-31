# Session report: v1-e32-t30-dry-run-fills-the-text-caches

| | |
|---|---|
| Task | `v1-e32-t30-dry-run-fills-the-text-caches` — A dry run fills the plan-text and analytic-text caches, so the first report after a parser bump reads sources once |
| Spec | [`plan_specs/v1/e32-argument-landscape/t30-dry-run-fills-the-text-caches.yaml`](../../plan_specs/v1/e32-argument-landscape/t30-dry-run-fills-the-text-caches.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t30-dry-run-fills-the-text-caches` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

As the PM ruled on 2026-10-31, a `landscape report --dry-run` now writes the plan-text and
analytic-text caches, and nothing else. `LandscapeRunService` asks both text seams to write in
every run, a dry run included. The classification cache, the review queue, the bundle, the scan
acceptances, the model cassettes and usage log, and the bucket stay unwritten, and a dry run still
calls no model. The entries go through the same seams and the same whole-file writers as a
publish, so the publish after a dry run on a new parser version parses none of the sources the dry
run parsed. On `synthetic26`, the dry run read `aff-two` once for each cache and the publish read
nothing. `--json` gains an additive `text_caches` key and the human output a line per cache.
Docstrings and `--help` now name the exception, and every test that pinned "a dry run writes
nothing" is narrowed to "nothing but the two text caches". **Look first at:**
* the one precision on ac1 under Deviations (texts the report quotes are still read again in
  memory on every run);
* the narrowed v1-e40-t17 smoke check, which is outside this task's packages.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `dry-run-fills-the-text-caches` (Text caches in a dry run) | Done | Tests written and shown red first, then the run service, the aff seam's counts, the CLI's JSON and human output, docstrings and `--help`. 7 mutants, all caught. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: as ruled, the publish after a dry run on a new parser version reads no source the dry run read, by tests shown failing first | PASS | **Red** before the change: `.venv/bin/python -m pytest packages/debate_core/tests/application/test_landscape_dry_run_text_caches.py -p no:randomly -n 0 -q --tb=line` → `5 failed`. The ac1 test failed on `AssertionError: the publish read no source: both caches held the dry run's readings`. The others failed with `{'2026.10.20-docx-6'} == {'2026.10.27-docx-7'}` (the cache was not refreshed), `set() == {…plan_texts…, …analytic_texts…}` (nothing written), a missing `plan_texts` result field, and a missing analytic-text cache file. CLI red: `pytest packages/debate_cli/tests/test_landscape_command.py -k "text_caches or tells_a_person or restored_copy_fills or parses_nothing"` → `7 failed` (`KeyError: 'text_caches'`, the listing checks, the old human line). The one pass in that run is an existing test the `-k` matched. **Green**: the same core file → `5 passed`. `test_landscape_command.py` with the core file → `76 passed` (now 90 with `test_file_suggest_service.py`). See Deviations for the quote read-back. |
| Node: Text caches in a dry run tests pass (`uv run pytest packages/debate_core/tests/application -k landscape`) | PASS | `.venv/bin/python -m pytest packages/debate_core/tests/application -k landscape -q` → `310 passed in 26.28s` (final run, at HEAD). |

**Mutants** (agreement 8; each run used a new, empty `HYPOTHESIS_STORAGE_DIRECTORY`, although none
of these tests uses Hypothesis). Each was applied to the committed tree, run against
`test_landscape_dry_run_text_caches.py`, `test_landscape_run.py` and `test_landscape_command.py`,
then restored with `git checkout HEAD --`. The tree was clean afterwards.

| Mutant | Result | Caught by (among others) |
|---|---|---|
| (1a) the dry run asks the aff seam not to write (`writes=not request.dry_run`) | CAUGHT, 11 failed | `test_the_publish_after_a_dry_run_on_a_new_parser_version_reads_no_source_the_dry_run_read`, `test_a_dry_run_over_a_restored_copy_fills_the_text_caches_here_and_writes_nothing_in_the_copy` |
| (1b) the dry run asks the analytic-text seam not to write | CAUGHT, 11 failed | the same, and `test_a_dry_run_tells_a_person_what_it_kept_in_the_text_caches` |
| (2a) the dry run classifies over the real store (cache and queue written) | CAUGHT, 6 failed | `test_a_dry_run_writes_nothing_but_the_two_text_caches`, `test_a_publishs_dry_run_writes_nothing_but_the_text_caches_in_any_model_mode[none/replay]` |
| (2b) the dry run's read-only view writes the review queue | CAUGHT, 6 failed | the same |
| (2c) the dry run's read-only view writes the classification cache | CAUGHT, 6 failed | the same |
| (3a) the plan-text cache key without the parser version | CAUGHT, 2 failed | `test_the_publish_after_a_dry_run_on_a_new_parser_version_reads_no_source_the_dry_run_read`, `test_every_text_cache_entry_after_the_dry_run_is_the_new_parser_versions` |
| (3b) the analytic-text cache key without the parser version | CAUGHT, 2 failed | the same |

I also showed the narrowed smoke check failing: with mutant (1a + 1b) applied,
`tests/smoke/test_landscape_smoke.py` gave `1 failed, 2 passed`
(`assert [] == ['analytic_te...etic26.jsonl']`), and it passes again after the restore.

**Before the report** (agreement 10):

* **Affected set:** `uv run scripts/affected_tests.py` chose `119 of 578 test files (20.6%) … from
  11 changed files`. I ran the command that `--run` builds (`python -m pytest -n auto -m "not slow
  and not live" <the 119 files>`) with the time limit on the interpreter (`perl -e 'alarm 115; exec
  @ARGV' .venv/bin/python -m pytest …`). It was stopped at 115 s at about 68%, with no failure up to
  that point, so the affected set takes longer than two minutes. As agreement 10 says, I leave it
  to the pull request's `ci` check and hand nothing over. The stop left the orphaned collect-only
  pytest processes of `tests/scripts/test_ci_workflow_test_job.py` behind, and I killed them.
* **Within the two minutes:** the always-run list (`tests/architecture/`, `tests/specs/`,
  `test_app.py`, `test_help_rendering.py`, `test_container_factories.py`), every
  `test_landscape_*.py` under `packages/debate_core/tests/application`, `test_aff_assignment.py`,
  `test_analytic_texts.py`, `test_plan_texts.py`, `test_file_suggest_service.py`,
  `test_landscape_command.py`, `commands/test_files.py`, `tests/smoke/test_landscape_smoke.py` and
  `tests/smoke/test_files_cli.py`: 24 paths, `-n auto -m "not slow and not live"` → `820 passed in
  51.26s`, at HEAD. The first pass of this set found the smoke pin (`1 failed, 819 passed`); see
  Deviations.
* `.venv/bin/ruff format --check packages` → `964 files already formatted`; `.venv/bin/ruff check
  packages` → `All checks passed!`; ruff format and check on `tests/smoke/test_landscape_smoke.py` →
  clean.
* `.venv/bin/pyright packages/debate_core packages/debate_cli` → `0 errors, 0 warnings, 0
  informations`.
* `lint-imports` → `Contracts: 19 kept, 0 broken.`; `uv run --frozen python
  scripts/check_thin_handlers.py` → `OK: 68 CLI command and API route handlers within 25 statements`.
* `uv run scripts/validate_specs.py` → `OK: 512 files, 40 epics, 450 tasks, 22 releases`, after
  `set-phase … Succeeded`. The spec on `origin/dev` differs from this branch's only in
  `status.phase`, checked again before this report.

## Files changed

* `packages/debate_core/src/debate_core/application/landscape_run.py`: both text seams are asked
  with `writes=True` in every run. The result carries `plan_texts` (the plan-text counts). The
  module docstring states the rule and its one exception.
* `packages/debate_core/src/debate_core/application/aff_assignment.py`: `AffAssignmentsForReport`
  carries the plan-text counts, so the run can report them. The docstrings now say a dry run writes
  this cache.
* `packages/debate_core/src/debate_core/application/{analytic_texts,plan_texts,file_suggest_service}.py`:
  docstrings only. The `without_writes` views are no longer what a dry run reads with, and
  `files suggest`'s landscape dry run now fills the two caches.
* `packages/debate_cli/src/debate_cli/commands/landscape.py`: the `--dry-run` section and `--help`;
  the additive `text_caches` JSON key; a human line per cache; the bundle line reads "Dry run: the
  bundle is not written; its 7 files would go to …".
* `packages/debate_core/tests/application/test_landscape_dry_run_text_caches.py` (new): the real
  services over the real parser under a version each test sets, counting the sources it is given.
* `packages/debate_core/tests/application/test_landscape_run.py`: the two seam tests that pinned
  `writes=False` in a dry run now pin `True`. The "writes nothing" test, whose world wires no text
  seam, now says why it still sees nothing.
* `packages/debate_cli/tests/test_landscape_command.py`: new tests through the container (restored
  copy, data-directory listings in `none` and `replay`, the publish after a dry run, the human
  lines, the JSON key), and the publish dry-run test narrowed to the two caches.
* `tests/smoke/test_landscape_smoke.py`: v1-e40-t17's restored-copy dry-run check narrowed (see
  Deviations).
* `plan_specs/…/t30-dry-run-fills-the-text-caches.yaml`: Goal `Succeeded`.

## Deviations from the spec

1. **ac1 holds for the caches. One read-back is outside any cache and happens in every run.**
   `v1-e32-t11`'s `AnalyticTextService.quote` reads again, in memory, each source holding a CP
   text, plank, alternative or role of the ballot placed under a position the team reads. It does
   this so the report can quote the text word for word, after checking its digest. That text is
   evidence text, so no cache may hold it, and a publish after a publish reads those sources again
   too. The publish after a dry run parses none of the sources the dry run parsed to fill the
   caches, and on `synthetic26`, where no source holds a text to quote, it reads no source at all
   (the ac1 test). In a real caselist it still reads the few sources with a quotable text. The
   docstrings and the `--dry-run` docs say so. I changed nothing about that read-back, because
   caching it would break the forbidden "evidence text written to a cache".
2. **`tests/smoke/test_landscape_smoke.py` is outside `constraints.packages`.** I narrowed it
   anyway. It was v1-e40-t17's restored-copy dry-run smoke check, and its last loop pinned
   `not (data_dir / "landscape").exists()`, so it fails under the ruled behaviour and would have
   failed the PR's `ci` and dev's push run. Only the dry-run pin changed. The check now pins
   exactly `analytic_texts/synthetic26.jsonl` and `plan_texts/synthetic26.jsonl` under the data
   directory's `landscape/`, still nothing in the copy, and no bundle in either place. It was
   renamed `…_and_writes_only_the_text_caches_on_a_dry_run`, and nothing referenced the old name.
   v1-e40-t17's refusal checks, the `would_ask` count and v1-e32-t32's exit codes are untouched.

## Decisions and assumptions

* **How a dry run writes.** It goes through the existing seams with `writes=True`, so the dry run
  and the publish use one code path, one writer (`atomic_replacement`, each cache whole or not at
  all), and one key (digest, parser version, vocabulary or rules digest). I kept the `writes`
  parameter on the two seams and the `without_writes` views. No production caller passes `False`
  any more, but removing them would change two ports and their tests beyond the ruling (see Follow-up
  work). I added no test for a write killed partway: the stores' writer is shared with the publish,
  the integrations package is outside this task, and the stores' own tests cover whole-file
  replacement.
* **`--json`'s `text_caches`, in every run** (not only a dry run), so the step-3 and step-4 outputs
  can be compared. For each of `plan_texts` and `analytic_texts`: `sources` (asked for), `cached`
  (found under this parser and these rules), `read` (parsed now), `unread` (bytes missing or a
  worker failed; not cached, tried again next run), `entries_written` (the entries this run added
  when it wrote the cache, else 0) and `written` (whether the cache file was rewritten). A key is
  `null` when its seam is not wired. The key is additive, and no existing key changed.
* **Human output.** One line per cache, for example "Plan-text cache: 1 of 2 source(s) read, 0
  already cached, 1 entry written." The bundle line no longer says "nothing written", because that
  is no longer true of a dry run.
* **`files suggest`** (`v1-e33-t03`) runs the landscape as a dry run, so it now fills the two caches
  too. That is within the ruling: derived fields in the data directory, rebuildable. Its docstring
  says so. Its "the landscape run writes nothing" test still holds, since its world wires no text
  seam, so I left it as it is.
* **Where the tests live.** The read count and the "nothing else" listing are tested at the service,
  with the real services and parser. The restored-copy split (cards from the copy, caches in the
  data directory) is the container's wiring, so it is tested through the CLI, which also covers
  `--model-mode replay` (no cassette, no usage log, no model call).

## Operator follow-ups

None. The affected set ran past two minutes and is the pull request's `ci` check's to run
(agreement 10). The proof run on dev.200 today is not affected by this branch.

## Follow-up work

* **Runbook wording, for the PM to amend** (`docs/runbooks/landscape-report-from-the-cloud-run.md`,
  not in this task's packages). Once this ships, three sentences are wrong:
  * Step 3, its opening: "The report over the copy, writing nothing: not the classification cache,
    not the review queue, not the bundle, not the bucket." Proposed: "The report over the copy,
    writing nothing but the plan-text and analytic-text caches, in your data directory: not the
    classification cache, not the review queue, not the bundle, not the bucket, and nothing in the
    copy."
  * Step 3, its runtime note: "the first report on this build reads every on-topic source again, and
    a dry run keeps none of it; the analytic texts' first fill took 551 s on 2026-10-24". Proposed:
    "the first report on this build reads every on-topic source again, and the dry run keeps what it
    read in those two caches for step 4; the analytic texts' first fill took 551 s on 2026-10-24".
    Step 3's success check could also print `text_caches.plan_texts.read` and
    `text_caches.analytic_texts.read` (above zero the first time on a build).
  * Step 4's runtime: "(expected runtime about as long as the dry run, since it reads the same sources
    again and keeps them this time)". Proposed: "(expected runtime a few minutes: the dry run filled
    the plan-text and analytic-text caches, so it parses no source again but the few holding a text
    the report quotes)". Its success check could add `text_caches.*.read` equal to 0.

  The intro has no sentence about the dry run's writes. Its "What lives where" paragraph already
  puts both caches in the data directory, and that stays true.
* **The `writes=False` views** (`PlanTextService.without_writes`, `AnalyticTextService.without_writes`,
  and the `writes` parameter on `AffAssignmentsFromReading` and `AnalyticTextsFromReading`) have no
  production caller now. They could be removed in an E32 clean-up task, or kept for a future caller
  that must leave the caches as they are. That is the PM's call.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
