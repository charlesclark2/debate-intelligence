# Session report: v1-e30-t34-a-removal-keeps-the-parse-a-snapshot-is-owed

| | |
|---|---|
| Task | `v1-e30-t34-a-removal-keeps-the-parse-a-snapshot-is-owed` — A removal keeps the parse a snapshot is owed, now that nothing is rebuilt after it |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t34-a-removal-keeps-the-parse-a-snapshot-is-owed.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t34-a-removal-keeps-the-parse-a-snapshot-is-owed.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t34-a-removal-keeps-the-parse-a-snapshot-is-owed` |
| Session status | COMPLETE |

## Summary

A removal no longer clears the parse-owed entries of the snapshots whose manifests it rewrote (the
PM's ruling of 2026-11-08 on this task's proposal: stop clearing). `removal_service._clear_parses_owed`,
the service's `parse_owed` field, `ParseOwed.clear_snapshots` and its test are gone, with the
composition root's keyword argument. The proposal's finding, now shown by test: with the entry
cleared, the next parse stage chose nothing (`assert [] == ['testcl26']`, local and bucket mode),
because `full_parse_owed` asks only whether *a* directory of the running parser version exists. Kept,
the next run parses the owed caselist from the manifests the removal rewrote, and the removed file
is not parsed, published or named anywhere in the parsed store. A week whose only unparsed source
was the removed file is parsed with nothing to parse, published, and its entry cleared (ruling 4).
The removal's plan text and `--json` are unchanged. Look first at the two Deviations (files outside
`constraints.packages`, both ruled) and at the affected set, which is left to the pull request's `ci`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `a-removal-keeps-the-parse-a-snapshot-is` (Removal keeps the parse owed) | Done | Proposal, ruling, red tests (`fd5bc41`), change (`d44a567`), one test hardened after the mutants (`5d912b1`) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: after a removal, a snapshot owed a parse is still parsed by the next parse stage, its removed file left out, by a test shown failing first | PASS | Red at `fd5bc41` on the pre-task code (below). Green: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/application/caselist/test_removal_keeps_the_parse_owed.py packages/debate_core/tests/application/caselist/test_parse_owed_record.py packages/debate_cli/tests/bucket_mode/test_parse_owed.py -q -p no:cacheprovider -n 4 -W ignore` → `34 passed in 36.31s` |
| Node: Removal keeps the parse owed tests pass (`uv run pytest packages/debate_core/tests -k "removal and owed"`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests -k "removal and owed" -q -p no:cacheprovider -W ignore` → `4 passed in 90.48s` (collection is most of it, at load average 9.9). The four are this task's two and two of `test_status_reports_held_digests.py` that the words also match |

### The red run

Against the pre-task code, with the new tests alone (`fd5bc41`):

* **Core**, `test_removal_keeps_the_parse_owed.py` → `2 failed in 1.02s`. Each fails at the clearing:
  the byte comparison (`At index 228 diff`) and `assert () == (PendingSnapshot(caselist='testcl26', snapshot='2026-09-15'),)`.
  The test gives the service the parse-owed file wherever the service takes one, as the composition
  root did, so it held the pre-task build.
* **Command level**, `test_parse_owed.py -k keeps` (local and bucket mode on moto; `wiki`, another
  source of the owed week, and `direct`, its only unparsed source) → `4 failed in 11.61s`, every one
  at `kept: nothing is rebuilt after a removal` / `kept in the bucket: …`.
* **What the next run then does**: the same four with the two "kept" assertions taken out, a scratch
  edit restored from HEAD afterwards → `4 failed in 10.38s`, at `the owed caselist is parsed though
  the run imported nothing` (local) and `assert [] == ['testcl26']` (bucket). The proposal's answer:
  a cleared entry is not parsed anyway.

### Mutants on the rule

Each planted in the committed source, run against the core file and the four command-level cases
(`-k "keeps or removal"`, 6 tests), and restored with `git checkout HEAD --`; tree clean after.

| Mutant | Result | Where it failed |
|---|---|---|
| The pre-task code: the removal clears the reached snapshots | caught, 6 of 6 | the red run above |
| A bucket-mode removal deletes the parse-owed file before it saves the state files | caught, 2 of 6 | both bucket cases, `kept in the bucket` (local mode never saves state files: by design) |
| Every removal deletes the parse-owed file | caught, 6 of 6 | `kept`, `kept in the bucket`, core `the file is kept` and `assert () == (…)`. First run: the core byte test failed with `FileNotFoundError`, a crash, so it now asserts the file is there first (`5d912b1`) and the re-run fails at that assertion |
| The parse stage ignores what is owed (`owed_followed = ()`) | caught, 4 of 6 | `the owed caselist is parsed though the run imported nothing` / `assert [] == ['testcl26']` |
| A parse with nothing to parse is not cleared (`elif not unreadable and parsed.attempted:`) | caught, 2 of 6 | the two `direct` cases, `cleared once the parsed store was published complete` / `cleared in the bucket …` (ruling 4: never owed for ever) |
| Both removed-file guards off: local manifests not rewritten, and `live_disclosures` returns every disclosure | caught, 5 of 6 | local: `never the removed file` (the parse attempts `wiki` again); core: the enumerated sources; bucket: the removal command itself exits with `status: error` before the next run |
| Informational: only the local manifest rewrite off | 3 of 6 fail | the suppression list alone keeps `wiki` out of the local next run; core and bucket fail as above |
| Informational: only the suppression filter off | 0 of 6 fail | the rewritten manifests alone keep the removed file out: each guard holds without the other |

### Before the report

* **Affected set**: `uv run scripts/affected_tests.py` → `348 of 728 test files (47.8%) chosen in 30.6 s
  from 10 changed files` (`container.py` parts `_build_caselist_removal`, `parse_owed`; `caselist_sync.py`).
  That is well over two minutes, so, per working agreement 10 (the PM's ruling of 2026-10-19), it is not
  run here and not handed to the operator: the pull request's `ci` runs it. Run instead, within the limit:
  * the always-run list and the parse-owed smoke file: `tests/architecture tests/specs
    packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py
    packages/debate_cli/tests/test_container_factories.py tests/smoke/test_caselist_parses_owed.py` →
    `381 passed in 31.50s`;
  * the core removal files and the parse-owed record:
    `packages/debate_core/tests/application/caselist/test_removal*.py …/test_parse_owed_record.py` (25 files)
    → `362 passed in 41.25s`;
  * `packages/debate_cli/tests/bucket_mode` whole: stopped by `hard_stop.py` at its 115-second limit,
    about 51% through, with no failure before the stop. Its `test_parse_owed.py` passed whole (above).
    The rest is CI's.
* `uv run ruff check .` → `All checks passed!`; `uv run ruff format --check .` → `2022 files already formatted`.
* `.venv/bin/python scripts/hard_stop.py 115 uv run pyright packages/debate_core packages/debate_cli` →
  `0 errors, 0 warnings, 0 informations` (42 s).
* `uv run lint-imports` → `Contracts: 20 kept, 0 broken.`; `uv run python scripts/check_thin_handlers.py` →
  `OK: 73 CLI command and API route handlers within 25 statements`.
* Docs: `scripts/check_links.py` → `OK: 3723 relative links and anchors in 630 Markdown files`;
  `scripts/check_command_blocks.py --base origin/dev` → `OK: no # comments in 693 shell code blocks`;
  `scripts/docs_index.py --check-descriptions` → `All 69 indexed documents under docs/ have a description`.
* `uv run scripts/validate_specs.py` → `OK: 655 files, 41 epics, 592 tasks, 22 releases`.
* The spec against `origin/dev` (`2ef7655`, not fetched): only `status.phase` differs, so the PM's
  amendment of the packages and the node's command (ruling 2) has not landed yet.

## Files changed

* `packages/debate_core/src/debate_core/application/caselist/removal_service.py`: the clearing, its
  call in `execute`, the `parse_owed` field and three imports removed; the module docstring gains
  "The parse owed is kept".
* `packages/debate_core/src/debate_core/application/caselist_sync.py`: `ParseOwed.clear_snapshots`
  removed; "What is owed" says a removal keeps every entry.
* `packages/debate_cli/src/debate_cli/container.py`: the removal service's `parse_owed=` argument and
  its comment removed; `parse_owed()`'s docstring no longer says a removal clears from it (Deviation 2).
* `packages/debate_core/tests/application/caselist/test_removal_keeps_the_parse_owed.py` (new): the
  removal keeps the file byte for byte; the sources the next parse plans from leave out the removed file.
* `packages/debate_core/tests/application/caselist/test_parse_owed_record.py`: the `clear_snapshots`
  test removed with the method.
* `packages/debate_cli/tests/bucket_mode/test_parse_owed.py`: the two clearing tests became the two
  parametrized "keeps and parses" tests, local and bucket mode, each with the two removals (Deviation 1).
* `docs/runbooks/caselist-removal.md` step 5: the ruled sentence, a parse owed stays owed and the next
  cloud run makes it. `docs/runbooks/caselist-scheduled-sync.md` "What is owed": its "a removal that
  reaches a snapshot clears its entry: the rebuild that follows a removal parses the caselist" was
  wrong after this change, and is rewritten.

## Deviations from the spec

1. **`packages/debate_cli/tests/bucket_mode/test_parse_owed.py` is outside `constraints.packages`.**
   The end-to-end tests live there, and its two clearing tests changed, as ruled (2). The PM amends
   the spec's packages and the node's command in the next batch; the node's command as written
   (`packages/debate_core/tests -k "removal and owed"`) does not run them.
2. **`packages/debate_cli/src/debate_cli/container.py` is outside `constraints.packages`.** The one
   keyword argument and its comment are removed, as ruled (3), and the `parse_owed()` docstring's
   "a removal clears from" with them.
3. **`docs/runbooks/caselist-scheduled-sync.md`** is inside `docs/runbooks` but not one the ruling
   named; its sentence described the clearing, so it is rewritten to match.

## Decisions and assumptions

* **The core test gives the service the parse-owed file wherever the service takes one**
  (`service_of`): that is how it held the pre-task build red, and how it would hold a build that took
  the field again.
* **"Removed file left out"** is checked as no file of the parsed store, on this machine or in the
  bucket, naming the file's digest in its name or bytes after the next run, with the premise that
  `wiki` was named there before. Nothing parsed `direct` before the removal, so its premise is that
  nothing named it, and the parse's `attempted` count (0) carries that case.
* **A parser bump's full parse owed** is not given a new test. `clear_snapshots` always kept those
  entries, and it is gone now; any removal that touched the file at all fails the four command-level tests.
* **Test data**: the parse world's fictional `testcl26` and the synthetic `testcl26` weeks only;
  everything over moto and respx, no socket, nothing published.

## Operator follow-ups

None. The affected set (348 files) is the pull request's `ci`, per working agreement 10.

## Follow-up work

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
