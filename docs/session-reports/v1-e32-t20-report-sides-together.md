# Session report: v1-e32-t20-report-sides-together

| | |
|---|---|
| Task | `v1-e32-t20-report-sides-together` — report.md in two halves: every affirmative section together, then every negative one |
| Spec | [`plan_specs/v1/e32-argument-landscape/t20-report-sides-together.yaml`](../../plan_specs/v1/e32-argument-landscape/t20-report-sides-together.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t20-report-sides-together` |
| Session status | COMPLETE |

## Summary

report.md now has its header (unchanged), then a three-line contents list, then three parts headed
`# Affirmative`, `# Negative` and `# Neither side`. **Affirmative** holds the aff side's positions,
including each advantage's impact cards, lead-ins and link chain, followed by Advantages by
affirmative. **Negative** holds the negative's positions, including each DA's impact block, followed by
the CP texts, alternatives and roles of the ballot. **Neither side** holds the positions either side
reads, Overviews, New this week, Rising, Falling and Unclassified.

No section's words or numbers changed. The pre-reorder golden is kept byte for byte as
`tests/fixtures/landscape/report_before_sides_together.md`. A new test cuts both the old and the new
report at every heading and compares them section by section. It runs against the hand-reordered
golden and against the rendered report. Both runs were shown failing first. Only report.md changed
among the bundle files.

The PM should look first at the two readings I made, under Decisions: "About this report" stays in
the header, and sections are moved whole at their `##` level. Also look at the proposed splits under
Follow-up work, which the PM asked for. One open question for t16's sync is in the relay block at the
end of Follow-up work. Goal phase: **Succeeded**. Nothing was published.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `report-sides` (Report sides together) | Done | Golden reordered by hand and tests red first, then the renderer, then the guide. Commits `917d63a`, `a0e8ca5`, `4fbd45d`. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: on the synthetic fixture, report.md reads header, contents, Affirmative, Negative, then neither side, matching a hand-written golden file. Each section's body is byte-identical to its body before the reorder, by a section-by-section test. No other bundle file changes. Tests shown failing first. | PASS | See the three runs below, the mutants, and `git diff --stat origin/dev -- tests/fixtures/landscape/golden` → `tests/fixtures/landscape/golden/report.md \| 30 +++++++++++++++++++++---------` and `1 file changed`. The other six goldens are untouched and their golden tests pass. |
| Node: Landscape render tests pass (`uv run pytest packages/debate_core/tests/arguments/landscape/test_render.py`) | PASS | `45 passed in 0.68s` (37 existing tests and 8 new). |

**Run 1: the tests alone, before any golden or renderer change.** The command was
`.venv/bin/python -m pytest packages/debate_core/tests/arguments/landscape/test_render.py -p no:randomly -q -n 0`,
with the before-file copied byte for byte (`cp`, then `cmp` and identical sha256 `3bc1d900…61b45d2`).
Result: `8 failed, 37 passed`. All eight new tests failed for the same reason: the report has no
contents list and no parts. For example, the identity test's `assert [] == ['## Contents...Neither side']`,
the order test's `At index 2 diff: '## Affirmative positions' != '## Contents'`, and
`IndexError`/`StopIteration` where a test looks for `# Neither side` or `## Contents`.

**Run 2: after reordering the golden by hand, renderer unchanged.** Result: `8 failed, 37 passed`.
The identity test now passes for the hand-written golden, so my reorder moved sections without
changing a byte of them. The failures are the golden match
(`test_rendering_the_fixture_matches_the_golden_file[report.md]`), the identity test against the
rendered report, and the six tests of the rendered structure. Committed red as `917d63a`.

**Run 3: after the renderer change.** Result: `45 passed in 0.68s`. The t15 section test
(`test_advantages_report_md_section_matches_the_hand_written_golden_file`) then failed. Its slice ran
on past the section into `+ # Negative`. I fixed the cut (see Decisions), and the landscape report,
run and CLI tests gave `157 passed`.

**Mutants.** Seven, each run against `test_render.py` alone and restored with `git checkout` from the
commit. All seven were caught:

| Mutant | Caught by |
|---|---|
| Golden: `Okafor 25` → `Okafor 24` in one impact row | identity test (hand-written golden), golden match |
| Golden: a blank line dropped under `### Theory` | identity test (hand-written golden), golden match |
| Renderer: Advantages by affirmative rendered in the Negative part | part-order test, golden match. The identity test passes, correctly: this mutant moves a section but changes no byte of it. |
| Renderer: the Overviews section dropped | identity test (rendered), part-order test, golden match |
| Renderer: anchors keep capitals | contents-links test, either-side test, golden match |
| Renderer: an empty part keeps its heading | empty-part test |
| Renderer: the no-positions line rendered in the Affirmative part | empty-part test |

**The contents anchors under GitHub's rules.** `scripts/check_links.py` reads the golden report.md
among the 356 tracked Markdown files. Command: `.venv/bin/python scripts/check_links.py` → `OK: 2380
relative links and anchors in 356 Markdown files`. With `(#neither-side)` changed to
`(#neither-sides)` in the golden, it reported
`tests/fixtures/landscape/golden/report.md:41: #neither-sides has no heading matching #neither-sides`
and exited 1. The file was restored afterwards.

### Checks before the report

* Affected set: `uv run scripts/affected_tests.py` listed **187 files**. I ran its command directly
  (`.venv/bin/python -m pytest -n auto -m "not slow and not live" <the 187>`) under
  `perl -e 'alarm 115'`. The alarm stopped it at 91% after 1:55 (exit 142). No `F` or `E` appeared in
  the progress lines up to there, and no worker was left running (`pgrep` found none). It is over
  the two-minute line, so under agreement 10 it is left to the pull request's `ci`, with no hand-off.
* Within the two minutes I ran the changed modules' test directories, the landscape application,
  CLI and smoke tests, the always-run list and the docs tests:
  `packages/debate_core/tests/arguments/landscape/ packages/debate_core/tests/application/test_landscape_*.py packages/debate_cli/tests/test_landscape_command.py tests/smoke/test_landscape_smoke.py tests/architecture/ tests/specs/ packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py tests/docs/`
  → `1341 passed in 16.34s`.
* `uv run --frozen ruff format --check .` → `1331 files already formatted`. `uv run --frozen ruff check .`
  → `All checks passed!`
* `.venv/bin/pyright packages/debate_core` → `0 errors, 0 warnings, 0 informations`.
* `uv run --frozen lint-imports` → `Contracts: 16 kept, 0 broken.` `scripts/check_thin_handlers.py` →
  `OK: 54 CLI command and API route handlers within 25 statements`.
* `scripts/docs_index.py --check-descriptions` → `All 47 indexed documents under docs/ have a description`.
* `uv run scripts/validate_specs.py` → `OK: 457 files, 40 epics, 395 tasks, 22 releases`.
* `uv run --frozen python scripts/check_command_blocks.py --base origin/dev` → `OK: no '#' comments in
  427 shell code blocks in 158 Markdown files (1 session reports changed since origin/dev)`. With
  this report written, `scripts/check_links.py` → `OK: 2380 relative links and anchors in 356 Markdown files`.

## Files changed

* `packages/debate_core/src/debate_core/arguments/landscape/render.py`: `render_markdown` builds the
  three parts and the contents list. `_positions_section` renders one side at a time, and the
  no-positions line is its own small section. The Overviews section is split out of
  `_texts_sections` unchanged. A part with no section gets no heading and no contents line. The
  module docstring describes the order.
* `packages/debate_core/tests/arguments/landscape/test_render.py`: eight new tests. They cover the
  section-by-section identity (golden and rendered), the part order, the contents links, an empty
  part, positions either side reads, and the parts on the fixture's first and third windows.
* `packages/debate_core/tests/application/test_landscape_report.py`: the t15 section test's slice ends
  at the next `#` or `##` heading, since the next heading can now be a part's. The golden
  `report_section.md` is unchanged.
* `tests/fixtures/landscape/golden/report.md`: reordered by hand, with the contents list and three
  part headings added.
* `tests/fixtures/landscape/report_before_sides_together.md`: the golden as it was, byte for byte.
* `docs/guides/landscape-taxonomy.md`: a short "How report.md is laid out" section. The line saying
  report.md "carries no link" now says no link out of the page, because the contents list links to
  its own headings.
* The spec's Goal phase and this report.

## Deviations from the spec

None.

## Decisions and assumptions

1. **"About this report" stays in the header.** It is one section: the facts table, then "How to read
   the numbers". The renderer's header has always included it. It carries the freshness and
   topic-change rows the report must show on its face, and the how-to-read notes explain the tables
   below them. The PM's brief lists "the coverage and how-to-read notes" under neither side, and the
   spec says "the coverage and method notes". I read both as Unclassified ("What this report could
   not count" and "How affirmative rounds were identified"), which is now the last section. Moving
   the whole About section to the end of Neither side would be a one-line change in `render_markdown`.
   Splitting the table from the notes is a content change, proposed below.
2. **Sections move whole, at their `##` level.** The texts section's shared policy paragraph sits
   under one `##` heading over the CP texts, alternatives and roles of the ballot. Putting CP texts
   directly under the Counterplans table, and K alternatives under the Kritiks table, would mean
   either repeating that paragraph or changing heading levels. Both are content changes, so the texts
   section follows the Negative positions as one block, still inside Negative. The interleave is
   proposed below.
3. **The part headings are `#`.** No section's heading level changed, so a `##` part heading would
   have been a sibling of the sections it groups, not their parent. As `#`, the outline reads title,
   part, section. Nothing parses report.md's first `#` line: the stale banner is prepended as a whole,
   and the circuit-wide scan and the CLI only search text.
4. **The contents list** has one line per part. Each line links the part and each of its `##`
   sections, using the anchors GitHub and most viewers generate. A part with no section, such as no
   aff positions and no t15 run, has no heading and no contents line. That keeps the rule of no new
   words beyond the headings and the contents.
5. **Positions either side reads** (`## Positions either side reads`) and the no-positions line
   (`## Positions`) go first in Neither side. The synthetic fixture has neither, so a test builds each.
6. **There is no plan-text section to place.** The brief lists "plan texts" in the Affirmative half,
   but report.md shows plan texts only as the method row "The round's plan text names the aff", in
   Unclassified's method table. Mechanisms appear under Advantages by affirmative, which is in
   Affirmative.
7. **t16 had not merged** (its spec is `Pending` on this base), so there is no plank section to
   place. On its sync, t16's section belongs in the Negative part, in `_texts_sections` or right after
   it in the `"Negative"` list. As a `##` section it gets a contents link with no further change.
8. **The identity test compares sections without the blank lines between them.** The last section
   of a file has no trailing blank line, so this lets a section compare equal wherever it lands.
   Within a section, every byte is compared, blank lines included, as the blank-line mutant shows.

## Operator follow-ups

None. The affected set is left to the pull request's `ci` (agreement 10). Republishing the Policy
report is the PM's to coordinate.

## Follow-up work

**Proposed splits for sections that mix sides.** The PM asked for these proposals; none was made.

* **The positions table and t14's per-kind coverage lines** need no split. The positions section was
  one renderer function across sides, but its output was already one `##` per side. t14's coverage
  lines sit under each kind's impact block, so the advantage lines are in Affirmative and the DA
  lines in Negative.
* **Unclassified.** Move "Aff rounds with no identified aff" and the "How affirmative rounds were
  identified" table to the end of Affirmative, and "Neg rounds with no placed negative position" to
  Negative. The cards, answers and coach's no-position lines would stay in Neither side. This needs
  two new headings, so it is a content change.
* **CP texts, alternatives and roles of the ballot.** Each kind's subsection would go under its
  kind's positions table. This needs the policy 1.13 paragraph once per kind (or once at the top of
  Negative) and the `###` subsections demoted to `####`.
* **About this report.** The facts table would stay in the header, and "How to read the numbers"
  would become its own `## How to read the numbers` section at the end of Neither side. This needs
  one new heading.
* **New this week, Rising, Falling.** Each list mixes both sides' positions. Each could split into
  an aff list and a neg list, placed in the halves. Each line already names its kind.
* **Overviews.** Its table mixes DA, advantage and CP rows. It stays in Neither side, as the brief
  says.

**For the PM, to paste to the t16 session or answer here:**

```text
Question for v1-e32-t20 / v1-e32-t16 (from the t20 session, 2026-10-25).

t20 keeps the pre-reorder report as tests/fixtures/landscape/report_before_sides_together.md, and
test_every_section_of_report_md_is_byte_identical_to_its_section_before_the_reorder holds every
section of report.md to its copy there. When t16 syncs after t20 merges, its new plank section is in
neither file's "before" copy, so that test fails until t16 does one of these:

(a) Recommended: add its plank section, byte for byte, to report_before_sides_together.md as well as
    to golden/report.md. The test then also proves t16 changed no other section of report.md, and
    every later report task gets the same check for one paste.
(b) Retire the before-file and the identity test once t20 has merged, since its job, proving this
    reorder, is done.

Either way t16's section goes in the Negative part, after the CP texts section; the contents list
links it with no further change.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-25

**Notes:**

The layout the coach asked for, with the content proven unchanged.
1. **ac1 passes, red first.**
   * The section-by-section identity test against a byte-for-byte copy of the old golden is the
     right proof. It passed on the hand-reordered golden before the renderer changed, which shows
     the reorder moved bytes without altering them.
   * 7 of 7 mutants were caught. The moved-section mutant passing the identity test and failing
     the order test is exactly the division of labour intended.
   * Only `report.md` changed among the bundle files. The contents anchors are checked by
     `check_links.py`, shown failing on a broken anchor.
2. **Accepted as made:**
   * decisions 1 to 8: "About this report" stays in the header; sections move whole at `##`;
     `#` part headings; one contents line per part; no heading for an empty part;
   * the t15 test's slice ending at the next `#` or `##`;
   * the guide's note that the contents links stay inside the page.
3. **The proposed splits are recorded and not filed yet.** These are Unclassified's aff and neg
   lines, the texts interleaved under each kind, "How to read" as its own section, and the trends
   split by side. The coach reads the republished report first. Whatever he asks for becomes one
   small task.
4. **The relay question, for whichever of t16 and t20 merges second:**
   * **If t20 merges second,** t20 adds t16's plank section byte for byte to both
     `report_before_sides_together.md` and `golden/report.md` on its sync. The identity proof is
     t20's, so t20 keeps it true.
   * **If t16 merges second,** t16 removes `report_before_sides_together.md` and the identity test
     on its sync. Its job, proving this reorder, is done at t20's merge, and `golden/report.md`
     still pins every byte. Keeping a second copy for every later report task would be upkeep
     without a new guarantee.
5. **The affected set** stopped at 91% with no failure, so it is left to the PR's `ci` under
   agreement 10. Everything that changed passed within the limit (1,341).

**After the merge:** the PM coordinates the Oct 30-31 republish with t14, t15, t18 and this layout,
plus t16 if it lands. No re-review is needed.
