# Session report: v1-e32-t60-the-bundle-scan-reads-the-reports-own-words-as-its-own

| | |
|---|---|
| Task | `v1-e32-t60-the-bundle-scan-reads-the-reports-own-words-as-its-own` — The bundle scan does not count the report's own fixed lines as a tournament's words |
| Spec | [`plan_specs/v1/e32-argument-landscape/t60-the-bundle-scan-reads-the-reports-own-words-as-its-own.yaml`](../../plan_specs/v1/e32-argument-landscape/t60-the-bundle-scan-reads-the-reports-own-words-as-its-own.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t60-the-bundle-scan-reads-the-reports-own-words-as-its-own` |
| Session status | COMPLETE |

## Summary

The bundle scan no longer counts a tournament found in one of the report's own fixed lines as a hit.
Every line report.md's template writes word for word is now named once in `render.py`. Each
circuit-wide CSV's first line and header row are named there too. `FIXED_LINES` gives both the
renderer and the scan the same text, keyed by file. A tournament found in a line that matches one of
its own file's fixed lines exactly, whole, is counted by file and tournament (`ExemptedLines`) and
is not a hit. Any line with something more in it is still a hit, as is a school or team code, a
fixed line in another file, or a fixed line with its case or spacing changed. The run and the
command report what was passed over, by count. Tests that fail if the template writes a line the
scan doesn't know: a static check of render.py's report.md functions, and a check of rendered
fixtures. Applying the rule to the template, it would have removed **71 of 2026-11-06's 76 hits**
(72 by the spec's figure of 73; see "How many of 2026-11-06's hits the rule removes"). **The PM
should look first at Deviations 2:** the note on withheld tags carries three counts. By the build's
rule that makes it a data line, so it stays a hit every week.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `the-bundle-scan-reads-the-reports-own-wo`: Scan the report's own lines | Done | Three commits: the fixed lines named once (331973e, output byte-identical), the scan's exemption with its tests (b32e8f1), the counts through the run and the command (66d28aa) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: The report's own fixed lines are not hits while every data line is scanned as before, by tests on invented tournament names shown failing first | PASS | **Red**, against a scan that exempted nothing (the `scan_bundle` skeleton returning `exempted=()`), run from the working tree before b32e8f1: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -q -n 0 --tb=line -p no:cacheprovider packages/debate_core/tests/application/test_landscape_scan_fixed_lines.py` → `20 failed, 53 passed`. Every failure was at an assertion: a fixed line still a hit (13 single lines, 4 colliding-word sweeps), a missing count, the digest and the rendered report. The 53 that passed are the "still a hit" tests and the template-registry tests, which a scan that exempts nothing cannot fail. **Green**: the same file plus `test_landscape_scan.py` → `87 passed`. **Mutants**: 16 of 16 caught, all at assertions (table below). Invented tournaments only: `Teams`, `Role`, `Rank`, `Cite`, `Uniqueness`, `Link Chain` |
| Node: Scan the report's own lines tests pass (`uv run pytest packages/debate_core/tests -k landscape_scan`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests -k landscape_scan -p no:cacheprovider` → `87 passed, 5 warnings in 21.65s`, exit 0 |

### Mutants and planted breaks

Each was applied to the committed code, run against `test_landscape_scan_fixed_lines.py`,
`test_landscape_scan.py`, `test_render.py` and `test_landscape_run.py` (`-n 4`), then restored with
`git checkout HEAD --`. The tree was clean afterwards. No Hypothesis is involved.

| Mutant | Caught by |
|---|---|
| The match strips spaces (`line.strip() in fixed`) | the changed-line tests (10 failed) |
| A line that begins with a fixed line | the changed-line tests (18 failed) |
| A line that holds a fixed line anywhere | the changed-line tests (23 failed) |
| Matched without regard to case | the upper/lower changed-line tests (9 failed) |
| The same words in any spacing | the doubled-space and other changed-line tests (14 failed) |
| A word list: every word of the line is some fixed line's word | the changed-line tests (22 failed) |
| Any kind passed over, a school or team code too | `test_only_a_tournament_is_passed_over_on_a_fixed_line` |
| Every file's fixed lines taken in every file | `test_a_fixed_line_is_passed_over_only_in_its_own_file` |
| Counted but still a hit | 22 failed, the run's acceptance test among them |
| A file's lines counted once | the count tests and the rendered-report test (6 failed) |
| Registry: a literal line written inline in the renderer | the static template test and the named-line test |
| Registry: the no-labelled-card family left out of `FIXED_LINES` | the rendered-line test and the single-line test |
| Registry: a family's text changed | the single-line test and the golden report.md |
| Registry: a named line the template never writes | `test_every_named_fixed_line_is_written_by_the_template` |
| Run: the scan's count dropped from `ScanResult` | both run tests |
| Run: an acceptance rebuilds `ScanResult` without the count | `test_an_acceptance_keeps_the_count_of_what_the_scan_passed_over` |

### How many of 2026-11-06's hits the rule removes

This is derived from the template and the scan's rules, not from the real bundle. It names no
tournament.

* The PM's note (v1-e40-t17's report, 2026-11-06) splits the 76 hits like this: 72 report.md lines of
  its own, one plan text, and two card tags with their cites in top_cards.csv. That is 75; the note
  doesn't say what the 76th is. 3 of the 76 were accepted in earlier runs. The spec's description
  gives 73 lines of the report's own instead of 72. I can't settle that difference of one without the
  bundle.
* The spec names four kinds of report.md line among them:
  * the impact tables' header row. The renderer writes it whole from one constant, once per advantage
    or DA with impact cards: a fixed line, **removed**;
  * the link chains' header row. Written whole, once per advantage or DA with a chain table: a fixed
    line, **removed**;
  * the line saying round titles are not read. Written whole, once: a fixed line, **removed**;
  * the note on withheld tags (`* **Tags left empty**: …`). Written once per report, in the header's
    reading guide. It interpolates three counts (impact cards, link chains, top_cards.csv), so by the
    build's rule it is a data line and **stays a hit**.
* A plan text and a card tag are data and stay hits.
* So, if every one of the 72 is one of those four kinds, as the spec says: the rule removes 72 − 1 =
  **71**, and **5** of the 76 hits remain (the withheld-tags note, the plan text, the two card tags and
  the hit the note doesn't classify). By the spec's 73: 72 removed, 4 remain. If any of the 72 is some
  other fixed line, it is removed too. If any is a line holding another value, it stays, and the
  count is lower.
* The same rule, run on the golden report.md with an invented tournament `Cite`, passes over 10 lines
  (3 impact headers, 6 chain headers, the titles line) and keeps 1 hit, the withheld-tags note
  (`test_the_rendered_report_keeps_only_its_data_lines_as_hits`).

The real count comes from the operator's republish after the 2026-11-11 run (Operator follow-ups),
and the PM records it.

## Files changed

* `packages/debate_core/src/debate_core/arguments/landscape/render.py`
  * Every report.md line written word for word moves, verbatim, into `_ReportLines`: 43 literals
    across 42 constants (one line is written in two places) and the titles line.
  * The lines built from the renderer's own tables alone come from one helper each, used by both the
    renderer and `FIXED_LINES`: part, side and kind headings, the impact-card headings, the quoted-text
    headings and their "nothing placed" lines, Rising/Falling, and a chain role with no labelled card.
  * `FIXED_LINES` holds 77 report.md lines and 2 lines (first line, header row) for each of the four
    circuit-wide CSVs.
  * `_csv` writes its first line and header row from the same helpers. The output is unchanged: the
    golden files pin every byte.
  * "1 round was not carried into …" is now written with its count interpolated, giving the same bytes
    (Decisions 3).
* `packages/debate_core/src/debate_core/application/landscape_scan.py`: `scan_bundle` returns
  `BundleScan` (hits and `ExemptedLines`), and `scan_report` keeps returning the hits. The module
  docstring gains "The report's own lines".
* `packages/debate_core/src/debate_core/application/landscape_run.py`: `ScanResult.exempted`, carried
  through a dry run and through a publish's acceptance (`dataclasses.replace`).
* `packages/debate_cli/src/debate_cli/commands/landscape.py`:
  * `--json` gains `scan.exempted` (`file`, `term`, `lines`);
  * the text output gains a "Passed over, the report's own fixed lines a tournament is in (no hit): …"
    line after the hits.
* Tests:
  * `packages/debate_core/tests/application/test_landscape_scan_fixed_lines.py` (new, 73 tests);
  * two run tests in `test_landscape_run.py`;
  * the CLI's pinned `scan` dict and one new CLI test in `test_landscape_command.py`.
* The spec: `debate_cli` and its tests added to `constraints.packages` (Deviations 1); phase
  `Succeeded`.

## Deviations from the spec

1. **`debate_cli` and `packages/debate_cli/tests` added to the spec's packages.** The build asks that
   "the scan's output says, by count only, how many lines it exempted and which configured tournament
   word matched them". The only way that output reaches the operator is through the command's text
   and `--json`. The CLI change is six lines. It pins one more key in the one test that pins the scan
   dict whole; no smoke test pins that dict. The spec carries a comment above `packages` saying why.
2. **The note on withheld tags stays a hit.** The spec's description lists it among "lines the report
   itself writes". It does write it, but with three counts in it (`{n} in the impact cards, {n} in
   the link chains and {n} in top_cards.csv`). The build's rule is that a line carrying a count is
   scanned as before, and the spec forbids "a data line exempted from the scan", so I followed the
   rule. Its key keeps it accepted week to week while each count keeps its number of digit groups:
   `1,234` becomes `#,#` where `999` was `#`. If the PM wants it gone, the clean way is to move its
   counts onto a line of their own, so the sentence becomes fixed. That changes report.md's text, so
   it is a separate task (Follow-up work).

## Decisions and assumptions

1. **Which tournament words the scan reads.** The bundle scan takes its tournament terms from each
   disclosure's tournament text, and has since `v1-e32-t05`. It does not read `topics.yaml`.
   `v1-e32-t06`'s `tournaments:` entries are read only by the topic resolver. So the spec's "a
   tournament name configured since v1-e32-t06" is, for the scan, the disclosures' tournament field.
   This changes nothing in the build.
2. **Only a tournament is passed over.** That follows the spec's title. A school or team code found in
   a fixed line is a hit as before. For example, a disclosed team code `AT` is still found in the
   bullet on `` `AT:` `` headings (tested). If the PM wants fixed lines exempt from every kind, it is a
   one-condition change, and the "any kind" mutant shows the test that would need to change.
3. **What counts as a fixed line.** A line the template writes from a literal or from its own tables
   alone, with no value interpolated. The rest follows from that:
   * "1 round was not carried into …" spells out a count, so it is written with the count
     interpolated and stays scanned;
   * the contents list's line per part is composed from whichever sections a week has, so it is not
     word for word and stays scanned;
   * a CSV's metadata lines carry values, so only its first line and header row are fixed.
   * The stale-data banner only prepends lines, so it doesn't disturb the match.
4. **The match is exact equality with a line of the same file.** Text before or after it, changed
   case, or doubled spaces make it a hit.
5. **How the tests find the template's lines.**
   * The static test walks `render_markdown` and every module function it reaches. In every list
     element and `.append` argument, including both branches of a conditional, it refuses a bare
     literal and requires a named one to be in `FIXED_LINES`.
   * The rendered test renders the synthetic and topic-change fixtures four ways (this week, first
     window, topic change, and each with no trends). Every line with letters, no digit and no value
     of the report's must then be a fixed line.
   * Its converse leaves out values that render.py's own source writes. The fixture's `Midterms DA`
     is also the example the template's bullet gives.
6. **The run tests stand a planted tag's line in for a fixed line.** They monkeypatch `FIXED_LINES`
   because the planted world's tournaments share no word with the template. The CLI test does the
   same.

## Tests run before the report

* The affected set: `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run`
  → stopped at the 115-second limit (exit 124, load ≈ 10). The selection was 143 of 729 test files.
  Agreement 10 leaves the whole run to the PR's `ci` check. Within the limit, I ran those same 143
  files in nine bounded batches (`.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest
  -q -n 6 -p no:cacheprovider <files>`), and every batch passed:
  * debate_core outside application/caselist: 37 files, `1359 passed`;
  * debate_core application/caselist: 17 files, `279 passed`;
  * debate_cli: 25 files in three batches, `355 passed`, `346 passed`, `38 passed`;
  * tests/architecture, specs, docs, cli and integration (the always-run list among them): 23 files,
    `701 passed`;
  * tests/scripts: 33 files, `648 passed`, `1210 passed`;
  * tests/smoke: 7 files, `54 passed`.
* `uv run ruff format --check .` → 2024 files already formatted. `uv run ruff check .` → All checks
  passed.
* `uv run pyright packages/debate_core packages/debate_cli` → 0 errors.
* `uv run lint-imports` → 20 kept, 0 broken.
* `uv run python scripts/check_thin_handlers.py` → OK, 73 handlers within 25 statements.
* `uv run scripts/validate_specs.py` → OK, after the phase was set.
* `uv run python scripts/check_command_blocks.py` → passes on this report.
* The spec against `origin/dev` (fetched 2026-11-07): it differs only in `status.phase`, so there was
  no PM amendment to merge.

## Operator follow-ups

**After the 2026-11-11 run's republish of hspolicy26: what the scan passed over, by count**
(a few seconds, once step 3 has run)

This only reads a file. Run the runbook's steps 1 to 3
([`docs/runbooks/landscape-report-from-the-cloud-run.md`](../runbooks/landscape-report-from-the-cloud-run.md)),
which write `/tmp/landscape-dry-run.json`. Then, in the same Terminal, from any folder, run the block
below.

The block stops if the shell has a `DEBATE_` override, if there is no dry run file, or if the build
that wrote it predates this task (no `scan.exempted` key). It prints a line per file and tournament
with the number of fixed lines passed over (`passed_over report.md N`), then the total, how many
tournaments, the scan's remaining hits and how many are not yet accepted. It never prints a
tournament or a line, so its output is safe to paste back.

```bash
DRY=/tmp/landscape-dry-run.json
```

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif [ ! -f "$DRY" ]; then echo "STOP: no dry run at ${DRY}, run the runbook's step 3 first"; else python3 -I -c 'import json, sys; e = json.load(open(sys.argv[1])); d = e.get("data") or (e.get("error") or {}).get("details") or {}; s = d.get("scan") or {}; x = s.get("exempted"); x is None and sys.exit("STOP: this build predates v1-e32-t60, its scan has no exempted key"); [print("passed_over", one["file"], one["lines"]) for one in x]; print("passed_over_lines", sum(one["lines"] for one in x), "tournaments", len({one["term"] for one in x}), "scan_hits", len(s.get("hits") or []), "not_yet_accepted", s.get("not_yet_accepted"))' "$DRY"; fi
```

Success looks like one or more `passed_over report.md <n>` lines, then the summary line. By the
template the scan_hits figure should fall by the passed-over count, compared with a week like
2026-11-06's. Paste the printed lines back; the PM records the count. On 2026-11-06 the installed
build refused `topics.yaml`'s `tournaments` key and step 3 ran from the main clone with `uv run`.
Whichever way it runs, the count appears only once this branch is in the build that writes the file.

## Follow-up work

* **The withheld-tags note's counts on a line of their own** (E32): it would make the note's sentence
  a fixed line and remove its weekly hit. It changes report.md's text and the golden file (Deviations 2).
* **The runbook's step 3 printout** (E32 or E40, runbook): it could print `scan.exempted` by count
  beside `scan_hits`, which would replace the follow-up block above. That is a runbook edit, outside
  this task's packages.
* **Fixed lines for every kind** (E32, PM's choice): Decisions 2.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
