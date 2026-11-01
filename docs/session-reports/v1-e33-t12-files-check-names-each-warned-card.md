# Session report: v1-e33-t12-files-check-names-each-warned-card

| | |
|---|---|
| Task | `v1-e33-t12-files-check-names-each-warned-card` — files check and files build name each warned or failed card, its check and why, as the quality report does |
| Spec | [`plan_specs/v1/e33-file-builder/t12-files-check-names-each-warned-card.yaml`](../../plan_specs/v1/e33-file-builder/t12-files-check-names-each-warned-card.yaml) |
| Epic / release | `v1-e33-file-builder` / `v1.2` |
| Branch | `task/v1-e33-t12-files-check-names-each-warned-card` |
| Session status | COMPLETE |

## Summary

`files check` and `files build` now print, after the checks table, a `Failures and warnings:` heading
and one line per WARN or FAIL result, in the `.quality.md`'s words and order:
`WARN cite-present card 2 (b8eb1aed33eb): the card has no short cite`, and a result about the whole
file without the card part (`FAIL sidecar: the sidecar describes a file with SHA-256 …`). The wording
is not a second copy: `render_markdown` and the CLI now share one place-wording helper in
`debate_core.evidence.file_checks.report` (new public `finding_line` and `FileQualityReport.findings`),
and the Markdown's bytes are unchanged (its hand-written expectation in `test_report.py` still passes).
`--json` carries the same results under one new key, **`quality.findings`**, each entry shaped exactly
as `.quality.json`'s `results` entries are. A file with no WARN or FAIL prints exactly what it printed
before, held by a test that compares against the old table written out by hand. The PM should look
first at **Deviations**: one module outside `constraints.packages` was edited (to share the wording,
as the PM context asked), and the JSON entries carry the full fingerprint, not the 12-character one.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `files-check-names-each-warned-card` (Warned cards named) | Done | Red tests committed first (`1d2106a`), implementation in `70a864e`; 7 mutants, all caught. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: `files check` and `files build` list each WARN and FAIL result with its card position, short fingerprint, check and message, and `--json` carries them under one new key, by tests shown failing first | PASS | Red run at `1d2106a` (new tests only, code unchanged): `pytest packages/debate_cli/tests/test_files_check_findings_presenter.py packages/debate_cli/tests/commands/test_files.py -k "…" -n 0` → **10 failed**, each for the missing feature: 6 × `assert [] == ['Failures and warnings:', …]` / `assert 0 == 5` / `'card 2 (' in …` (no lines after the table), 4 × `KeyError: 'findings'` or the quality key list lacking `findings`. The two clean-file tests failed only at their `findings == []` line; their "prints as before" parts passed. Green at `70a864e`: the same tests plus `test_report.py`, `test_output.py`, `test_files_suggest_presenter.py` → **142 passed in 5.64 s**. |
| Node: Warned cards named tests pass (`uv run pytest packages/debate_cli/tests -k files`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_cli/tests -k files -q` → **86 passed in 18.15 s** (the spec's command, through the venv's Python so uv does not sync). |

### What a person sees (before and after)

A built file with card 2's short cite blanked and its tag and cite replaced by invented words
(the test's own fixture), `files check`, the lines below the table. Before: nothing. After:

```text
Failures and warnings:
  FAIL sidecar: the sidecar describes a file with SHA-256 6dcae41ff134…, and this file is 0335fea1cf43…
  FAIL evidence-identity card 2 (b8eb1aed33eb): the built card's cite differs from the source card's (built 0ad4ba573a4a…, source 6cef145454f2…)
  FAIL evidence-identity card 2 (b8eb1aed33eb): the built card's tag differs from the source card's, and the sidecar records no override
  WARN cite-present card 2 (b8eb1aed33eb): the card has no short cite
```

The `.quality.md` of the same file lists the same four, in the same order:
`` * **WARN** `cite-present` card 2 (`b8eb1aed33eb`): the card has no short cite ``, and so on.

A clean file: `files check`'s stdout before and after is byte-identical (`diff` printed nothing);
`files build`'s differs only in the pytest temp directory's number inside the wrapped title.

### The `--json` envelope (before and after)

`files check --json` on that file, keys only (an `error` envelope, since it FAILs):

* before: envelope `schema_version, status, command, data, error`; `error`: `code, message, exit_code,
  details, hint`; `details`: `file, quality, reports, notes`; `details.quality`: `status, checks,
  failing_checks`.
* after: the same, and `details.quality`: `status, checks, failing_checks, findings`. Removing
  `findings` from the after-envelope's `quality` leaves it equal to the before-envelope's (checked for
  the clean and the warned file).

One entry of `quality.findings`:

```json
{"check": "cite-present", "status": "WARN", "card_position": 2, "fingerprint": "b8eb1aed33eb63cf223aa8378ca4bca44054f4fa69ed5acd3ebb075ec5ae54a0", "section_path": null, "paragraph_index": null, "message": "the card has no short cite"}
```

A clean file's `quality.findings` is `[]`. `files build` carries the same key in `data.quality` (and in
`error.details.quality` when a check FAILs).

### No card text

`test_no_named_line_or_finding_holds_the_warned_cards_tag_cite_or_evidence` plants card 2's tag as
`Quillmarsh zephyr tag` and its cite as `… Brindlewick Observatory, …` in the built file, checks that
card 2 is named (`card 2 (` in the lines, `"card_position": 2` in the JSON), and finds neither planted
phrase, nor `Synthetic Institute`, `synthetic claim` or `Synthetic evidence` (every card's cite, tag
and evidence wording), in the human stdout or stderr or the JSON stdout or stderr. The messages are
the checks' fixed sentences, naming fields and digest prefixes; section paths hold only the coach's
pocket/hat/block headings the sidecar records, never a tag (`structure.check_headings`).

### Mutants (agreement 8; each run used a fresh `HYPOTHESIS_STORAGE_DIRECTORY`, though none of these tests uses Hypothesis)

Applied one at a time to the committed code, run against this task's new tests only (not
`test_report.py`, so a change to the shared wording must be caught here), restored with
`git checkout HEAD --`; the tree was clean afterwards. Every catch is an assertion failure.

| Mutant | Result |
|---|---|
| 1a. The lines not printed: the presenter passes no `lines_below` | caught, 6 tests |
| 1b. The lines not printed: `CliOutput.success` ignores `lines_below` | caught, 6 tests |
| 2. A PASS result printed: the lines read `report.results`, not `report.findings` | caught, 4 tests |
| 3. The card number off by one (`card_position - 1` in the shared place-wording) | caught, 6 tests |
| 4. The JSON key dropped (`findings` removed from the quality payload) | caught, 7 tests |
| 5a. A clean file prints the heading (the empty-findings guard removed) | caught, 2 tests |
| 5b. A clean file prints an empty line (`[""]` for no findings) | caught, 1 test (`test_a_file_with_no_warn_or_fail_prints_exactly_the_table_it_printed_before`; the CLI test ignores blank lines) |

### Before the report

* Affected set: `uv run scripts/affected_tests.py` → **200 of 609 test files** (`output.py` reaches
  every CLI command; `report.py` the file-check and build services). Run with `--run` under
  `scripts/hard_stop.py 115`: stopped at its limit at about 19% of the tests, none failing (load
  average 9.6). Over two minutes, so under agreement 10 it is left to the pull request's `ci`, which
  runs the same set; no hand-off.
* Within the two minutes, the changed areas and the always-run list: `tests/architecture/`,
  `tests/specs/`, `test_app.py`, `test_help_rendering.py`, `test_container_factories.py`,
  `packages/debate_core/tests/evidence/file_checks/`, `packages/debate_core/tests/application/test_file_*.py`,
  `packages/debate_cli/tests/test_output.py`, `test_files_*.py`, `commands/test_files.py`
  (16 paths, each checked with `ls -d`) → **865 passed in 23.52 s**.
* The whole `packages/debate_cli/tests` directory under the same limit: stopped at about 96%, every
  test that ran passing. Not a complete result; CI's affected set covers it.
* `uv run --frozen ruff format --check .` → `1690 files already formatted`; `ruff check .` → `All
  checks passed!`; `pyright packages/debate_cli packages/debate_core` → `0 errors, 0 warnings`;
  `lint-imports` → `Contracts: 19 kept, 0 broken`; `scripts/check_thin_handlers.py` → `OK: 68 CLI
  command and API route handlers within 25 statements`; `uv run scripts/validate_specs.py` → `OK: 539
  files, 41 epics, 476 tasks, 22 releases`.

## Files changed

* `packages/debate_core/src/debate_core/evidence/file_checks/report.py`: the Markdown's per-result
  place-wording moved into `_place`, shared by `render_markdown` and the new public `finding_line`
  (the same line without Markdown); `FileQualityReport.findings` (every non-PASS result, in order),
  which `render_markdown` now reads. A plain property: the model, its JSON and its schema are unchanged.
* `packages/debate_cli/src/debate_cli/output.py`: `TableSpec.lines_below` (default empty), printed
  after the table as written, one per line, with no markup or wrapping.
* `packages/debate_cli/src/debate_cli/presenters/files_presenter.py`: the checks table carries the
  heading and lines when there are findings; `_quality_payload` (shared by `files check` and `files
  build`) gains `findings`. `files suggest`'s `other_positions_left_out` and `files publish`'s "Warned,
  not blocked" caption are untouched.
* `packages/debate_cli/tests/test_files_check_findings_presenter.py` (new): presenter tests over a
  hand-built report.
* `packages/debate_cli/tests/commands/test_files.py`: four CLI tests over the planted world.
* The spec's phase, and this report.

## Deviations from the spec

* **A module outside `constraints.packages` was edited.** `constraints.packages` lists `debate_cli`,
  `debate_core.application` and the two test directories; the shared wording lives in
  `debate_core.evidence.file_checks.report`. The PM context asks for "the same source the `.quality.md`
  writer uses … Don't build a second wording", and the only way to print the Markdown's words without
  copying them is to give that module one function both use. The change is a refactor plus one
  function and one property; the Markdown's bytes are held by `test_report.py`'s hand-written
  expectation, which passes unchanged. The PM may want `debate_core.evidence.file_checks` added to the
  spec's packages.
* **The JSON entries carry the full fingerprint, not the 12-character one.** The PM context lists
  "short fingerprint" for each entry. Every other `fingerprint` key in these envelopes (`card_problems`,
  `unattributed`, `files suggest`'s cards) is the full 64-character digest, recipes name cards by the
  full digest (`CardRef.fingerprint`), and the entries are shaped exactly as `.quality.json`'s
  `results`, so a program can find the card in the recipe and match the two reports. The printed line
  carries the 12-character prefix. If the PM wants the short one in the JSON too, it is one added key.

## Decisions and assumptions

* **The key is `quality.findings`**, not `results`: in `.quality.json`, `results` is every result,
  PASSes included, and these are only the WARNs and FAILs; `report.py` already called them findings.
  It sits inside `quality`, beside `failing_checks`, because both commands share that payload, so each
  envelope gains exactly one key.
* **A heading, `Failures and warnings:`**, the `.quality.md`'s own section name, then each line
  indented two spaces, as `files build`'s unattributed-card lines are. Nothing at all for a clean file.
* **A result about the whole file prints `FAIL sidecar: <message>`.** The Markdown writes
  `` `sidecar` <message> `` with no colon, the code span separating them; in plain text a colon reads
  better. This is the only wording difference besides the Markdown's bold and code spans, and it is
  in `finding_line`, beside the Markdown's.
* **Paragraph and section parts are printed too** (`FAIL heading-structure paragraph 7, under Politics
  DA > Link: …`), as the Markdown prints them, since the PM asked for the report's own words.
* **Lines go to stdout after the table**, through a new `TableSpec` field rather than `note()`
  (stderr): they are part of the result, and `--json` mode already reserves stdout for the envelope.
* **No smoke check change.** The spec has no smoke node and the PM context says `tests/smoke` is
  v1-e39-t26's; the CLI tests above run the commands end to end.

## Operator follow-ups

None. The affected set (200 files, over two minutes) runs in the pull request's `ci` check.

## Follow-up work

* The QUALITY_FAILED panel's hint still says "Read the .quality.md beside the file for each card's
  finding." It is still true, but the findings are now on the screen just above it; a wording follow-up
  could say so (E33, or the next wording pass).
* The PM's planned follow-up (a quality WARN for an unreplaced CP text slot) will print through
  `finding_line` with no change here.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
