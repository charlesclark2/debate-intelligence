# Session report: v1-e32-t35-cp-texts-shown-whole

| | |
|---|---|
| Task | `v1-e32-t35-cp-texts-shown-whole` — A CP text the landscape shows is whole: a text ending in a colon shows its planks, and a text split across paragraphs is joined |
| Spec | [`plan_specs/v1/e32-argument-landscape/t35-cp-texts-shown-whole.yaml`](../../plan_specs/v1/e32-argument-landscape/t35-cp-texts-shown-whole.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t35-cp-texts-shown-whole` |
| Session status | COMPLETE |

## Summary

The landscape report now shows a CP text whole. A text ending in a colon carries the planks `v1-e32-t16`
lists after it, by t16's own rules and caps. A text that stops on a word or a dash carries the analytics
right after it, which is the one continuation shape the count found: a plank list written without its
colon. Each line is a source paragraph, on a table row of its own under the text's rank in report.md.
The grouping digest covers every line, a line naming a school withholds the whole text, and the
analytic-text rules version moves to `3`, so the next report reads every on-topic source again once.
The count came first, over the Mac's hspolicy26 store, and found the shape behind the coach's rank 3: a
group tied 5 to 5 between copies ending `should:` and copies ending on a bare `should`.

**Look at first:** grouping by the whole text splits the Advantage CP's 12-team text into 24 one-team
texts (see "What the next republish will show differently"). That is what the spec asks for, but it
changes what the coach sees most, so there is a question for the PM below.

## The count (counts only; nothing quoted, nothing written)

Over `~/.debate-research/dev`, hspolicy26 parsed on `2026.10.27-docx-7`. The newest weekly snapshot
there is **2026-10-20**: 3,825 on-topic sources. I read it read-only:
* the seed reading;
* the analytic-text cache, through `AnalyticTextService(writes=False)`: 3,825 hits, 0 parsed, rules
  digest `919fe373a561`, matching this build before the change;
* the 138 sources holding a CP text the report would quote, parsed again in memory with
  `ProcessPoolParseRunner`.

The report's own `_read_range` and `_landscape_texts` gave exactly the texts a report shows (top 3 per
CP). No cache, report or manifest was written: before and after the session, the mtimes and sizes of the
analytic-text cache, the parsed manifests, `debate.sqlite3` and the reports were identical (11 files). The
scripts are in the session's scratchpad, not the repo: they print word classes and counts, never a word.

| What | Count |
|---|---|
| CP texts shown (8 CPs, top 3 each) | 22 |
| of those, ending in a colon | 7 (States CP ranks 1–3, Advantage CP ranks 1 and 3, Vouchers CP rank 3, Taxes PIC rank 1) |
| of those 7, with planks t16 already reads | **7** (3 to 6 list planks each, all read back) |
| shown texts ending on a word, no sentence end | 2, both followed directly by a card: no continuation |
| shown texts where the next paragraph continues them (no heading or card between) | **0** as shown (but see rank 3 below) |
| all CP text copies in range read back | 169: 95 end in a colon (every one with t16 planks), 42 in a sentence end, 27 on a word, 5 on an em dash |
| copies ending on a word or dash and followed by a paragraph outside a card | **26 copies in 5 groups** |
| copies ending on a word and followed by a card | 6 |

**The continuation shape, in Verbatim terms.** In all 26 copies, the paragraph after the stem is an
**analytic** in the stem's own style rule (`assembly-tag-without-cite-or-evidence` for both), at the next
element index. It is never an undertag, and never two halves of one paragraph: a `w:br` stays inside
one paragraph in the parser. The stems end at `should` itself (16), on another word (5), or on an em dash
(5). The analytics after them open with a hyphen (8), an en dash (7) or a capital (11), are short, and
run 1 to 6 paragraphs before the first card or heading. So this is a **second analytic per plank**:
a plank list with no colon.

**Rank 3's mid-phrase stop.** On this store the States CP's rank 3 (3 teams) is a group whose copies
are 5 ending `should:` and 5 ending on a bare `should`, both followed by the same plank analytics. Words
alone make the digest, so they are one group. `commonest_text` breaks the 5–5 tie by source digest, and
here the colon copy wins. With the cloud week behind the coach's 2026-10-30 republish, one more
bare-`should` copy, or a different tie-break, shows the text ending at `should`, which reads as a
mid-phrase stop. It is the continuation shape above. The cloud week itself (later than 2026-10-20) is not
on this Mac, so the exact rank 3 the coach read cannot be checked here.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `cp-texts-shown-whole` | Done | Count first. Then tests and fixtures, run red against a skeleton (`b152097`). Then the reader, read-back and render (`25cff2c`), three tests that mutants showed missing (`422de43`), and the guide (`4792697`). Last, the dashes in the continuation rule and its tests are spelt as `\u` escapes, as the module's other patterns are; the 117 tests of the four nearest modules passed and mutant 5 was caught again. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the counts recorded first | PASS | The count above, run before any code (scratch scripts over the store, 42.6 to 46.0 s each). |
| ac1: a CP text ending in a colon is shown with its planks | PASS | `test_a_cp_text_ending_in_a_colon_is_shown_with_the_planks_it_lists`, `test_a_listed_plank_is_a_line_by_t16s_rules_and_caps`, `test_an_inline_label_is_no_part_of_the_whole_text`, and the report section `test_the_cp_texts_part_matches_the_hand_written_section` |
| ac1: a text continued in the next paragraph is joined where the count found that shape | PASS | `test_a_cp_text_ending_with_no_sentence_end_is_joined_to_the_analytics_continuing_it`, `…_ending_in_a_dash_is_continued_too`, `…_continuation_ends_at_the_first_paragraph_that_is_not_an_analytic`, `…_ends_at_an_analytic_over_60_words`, `…_with_no_actor_is_not_continued`, and the 4 cases of `…_never_joined_across_a_heading_a_card_or_to_an_undertag`, `…_ending_in_a_sentence_end_is_not_joined`, `…_never_joined_to_the_next_cp_text` |
| ac1: a plank naming a school withholds the whole text | PASS | `test_a_text_any_plank_of_which_names_a_school_is_withheld_whole`; the report section's withheld b3 |
| ac1: the group's digest covers what is shown | PASS | `test_a_cp_text_with_its_planks_and_one_without_are_two_texts`, `test_a_text_with_its_planks_and_the_text_alone_are_two_ranked_texts`, `test_a_whole_text_whose_plank_reads_differently_now_is_not_quoted`, `test_a_whole_text_is_read_again_only_with_every_line_even_one_with_no_words` |
| ac1: synthetic fixtures, tests shown failing first | PASS | `tests/fixtures/landscape/cp_texts_shown_whole` (invented; expected section hand-written from its README). Red run against the skeleton: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n 0 -p no:randomly --tb=line -q <the two new modules>` → **13 failed, 7 passed**. The 7 were the "never joined" guards, which a skeleton that joins nothing passes. The report-level red showed today's behaviour: one States CP text of 6 teams, the stem alone. The three tests added in `422de43` were each shown failing against the mutant they were written for (6, 10, 11 below). |
| Node: CP texts shown whole tests pass (`uv run pytest packages/debate_core/tests -k analytic_text`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests -k analytic_text -n 4 -q` → **133 passed in 39.04s** (23 of them the new modules') |

### Mutants (agreement 8)

Each was applied alone to HEAD, and the covering suites ran with a fresh, empty
`HYPOTHESIS_STORAGE_DIRECTORY` (the suites have no property tests). The suites were the two new modules,
both `test_analytic_texts.py`, `test_cp_planks.py`, `test_landscape_report.py` and `test_render.py`.
Each file was restored with `git checkout HEAD --`, and the tree was clean after each run.

| Mutant | Result | Caught by |
|---|---|---|
| 1 the planks dropped (a colon text keeps no lines) | CAUGHT, 8 failed | the colon, caps, inline and two-texts tests, the docx plank test, the report section |
| 2 a plank naming a school shown (only the first line checked) | CAUGHT, 3 failed | the withheld-whole test, the two report tests |
| 3 the digest left over the first paragraph only (grouped and checked on the stem, shown whole) | CAUGHT, 6 failed | the colon, continuation, two-texts and reads-differently tests, the two report tests |
| 4 a continuation joined across a heading | CAUGHT, 3 failed | the never-joined test (heading case), the two report tests |
| 5 a continuation after a sentence end | CAUGHT, 2 failed | the sentence-end test and t11's own `test_the_first_should_analytic_of_a_block_under_a_placed_cp_is_its_text_by_place` |
| 6 a continuation without the actor guard | survived, then CAUGHT | `test_a_cp_text_with_no_actor_is_not_continued` (added) |
| 7 a continuation into an undertag | CAUGHT, 2 failed | the ends-at-first-non-analytic and never-joined tests |
| 8 a continuation into a card's paragraph | CAUGHT | never-joined (analytic in a card) |
| 9 a continuation into the next CP text | CAUGHT | `test_a_cp_text_is_never_joined_to_the_next_cp_text` |
| 10 a continuation line over 60 words | survived, then CAUGHT | `test_a_continuation_ends_at_an_analytic_over_60_words` (added) |
| 11 a missing line not checked on reading again | survived, then CAUGHT | `test_a_whole_text_is_read_again_only_with_every_line_even_one_with_no_words` (added). The check matters only for a line with no words (a lone dash), whose absence leaves the digest as it is. |
| 12 the lines on one row in report.md | CAUGHT | the report section |
| 13 lines in any order | CAUGHT | `test_only_a_cp_text_has_lines_after_it_in_file_order` |

### Before the report

| Check | Result |
|---|---|
| `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python scripts/affected_tests.py --run` | 143 of 605 test files chosen from 16 changed files. **Stopped at its 115-second limit at 70%: 3,456 passed, none failed** in what ran (load 4 to 17 from other sessions). Over about two minutes, so the rest is left to the pull request's CI, with no hand-off (the PM's rule of 2026-10-19). |
| Neighbouring suites (both analytic-text modules, planks, report, render, scan, the cache store, dry-run text caches, the new modules, `tests/testing`) | 335 passed |
| `uv run --frozen ruff format --check packages tests` / `ruff check packages tests` | 1202 files already formatted / All checks passed |
| `uv run --frozen pyright packages/debate_core` | 0 errors, 0 warnings |
| `uv run --frozen lint-imports` / `scripts/check_thin_handlers.py` | 19 contracts kept / 68 handlers within 25 statements |
| `scripts/check_links.py` / `scripts/check_command_blocks.py` | OK, 3,140 links and anchors / OK |
| `uv run scripts/validate_specs.py` | OK: 537 files, 41 epics, 474 tasks, 22 releases |

## Files changed

* `debate_core/arguments/landscape/analytic_texts.py`: the whole text. It adds `whole_text`; `_Planks`
  returns a CP text's lines (its list planks, or `_continuing`'s analytics) and rebuilds the reading with
  `lines` and a digest over the whole text; `read_back_texts` reads every line from its own paragraph and
  checks the whole; `_RULE_VERSION` moves to `analytic-texts-3`. The module docstring gains the rule.
* `debate_core/domain/landscape_texts.py`: `AnalyticTextReading.lines` (paragraph indices, never words),
  only on a CP text, after it and in file order.
* `debate_core/arguments/landscape/render.py`: a CP text's lines each go on a table row of their own
  under its rank row (`| | | line |`). Texts without lines render exactly as before.
* `debate_core/testing/landscape_report.py`, `tests/fixtures/landscape/synthetic_caselist/`: the
  hand-written fixture's b6 colon text carries its four plank lines, as the reader now keeps it. The golden
  report does not move, because b6's text is the States CP's "1 more text".
* `tests/fixtures/landscape/cp_texts_shown_whole/`: seven invented States CP blocks over the synthetic
  caselist's negative files, its README with the hand count, and the hand-written report section.
* Tests: two new modules. Two existing tests change as expected: the docx plank test now quotes the colon
  text whole, and the store's field pin gains `lines`.
* `docs/guides/landscape-taxonomy.md`: the CP text paragraph.

## Deviations from the spec

1. **A continuation may open with a capital.** The spec's description counts a continuation as "no
   capital, no heading, no card between". The PM's context says "no heading or card between". In the
   count, 11 of the 26 continuation copies open with a capital: imperative planks, in the same groups and
   the same shape as the dash-led ones. A rule that refused a capital would leave half of one group
   cut short. So the rule joins on the shape (the stem ends on a word or a dash; the next paragraph is an
   analytic outside a card) and does not look at the capital. If the PM agrees, the spec's "no capital"
   wants amending.

## Decisions and assumptions

* **The rule for a continuation**, stated and tested: a CP text that ends on a word or a dash and passes
  the actor guard is continued by the analytics right after it, outside a card and of at most 60 words
  each, up to the first paragraph that is not one. An advantage's alias alone is passed over, as t16's
  label is. The count found analytics only, so an undertag or an unstyled paragraph stops it.
* **Continuation lines are not planks.** The planks section and its counts are t16's, unchanged.
  Making a colon-less list's lines into planks would change t16's counts, and nothing asked for that
  (see Follow-up work).
* **Layout:** continuation rows in the existing table, not a quote block. The landscape pages render
  report.md with HTML off, so a cell cannot break a line. Extra rows keep the table, leave every text
  without lines exactly as it was, and put each plank on its own line. The split applies only to CP
  texts. On the store, no CP text without lines holds a line break of its own, so a soft break never
  becomes a row by accident.
* **Each line is collapsed to one line** (runs of spaces and breaks become one space) only when a text
  has lines, so each row is one paragraph. A text without lines is quoted exactly as before.
* **Nothing new is logged or cached as words.** A reading gains paragraph indices only. The cache test
  (`test_a_sources_planks_and_their_counts_are_read_and_cached`) still finds no plank word in the cache,
  and the field pin still refuses a `text` field.
* **The actor guard is unchanged.** A list's or continuation's actor is its CP text's, as t16 rules.

## What the next republish will show differently

Measured on the store above. The before side is the cache's readings. The after side has the 138 sources
holding a quoted CP text read again by this build in memory: their readings found the same paragraphs,
asserted per source, and only CP-text lines and digests changed. Both sides were ranked by
`_landscape_texts` (58.1 s). The cloud's newer week will move individual ranks; the shape of the change
will be the same.

| CP | Before (rank: teams) | After (rank: teams, lines under it) | Distinct texts |
|---|---|---|---|
| States CP | 9, 3, 3: stems only | 7 + 5 lines, 3 + 6 lines, 3 + 5 lines | 30 → 54 |
| Advantage CP | 12, 1, 1 | 1 + 0, 1 + 4, 1 + 3 | 5 → 28 |
| Taxes PIC | 1 | 1 + 4 lines | 1 → 1 |
| Public option, NHS, Vouchers CPs, Smokers PIC, Delay CP | unchanged | unchanged (no shown text has lines) | unchanged |

* Of the 169 CP text copies in range, **121 now carry lines**: 95 colon lists and 26 continuations, with
  1 to 13 lines (mostly 2 to 5).
* Coverage counts do not move: 235 found, 160 counted, 0 withheld, 0 unread. The planks section does
  not move.
* **The splits.** The Advantage CP's 12-team text becomes 24 one-team texts: every team's planks
  differ. Its top three are then 1-team ties broken by digest, and its first row is a copy that has no
  lines. The States CP's 9-team text splits 7 + 1 + 1 + 1 + 1. Its old rank-3 group (the 5–5 tie)
  splits into six 1-team texts, and a different 3-team group, with 5 plank lines, takes rank 3.
* **The cache must be refreshed, and the next report does it on its own.** The rules digest on
  hspolicy26's config moves from `919fe373a561…` to `54b853442079…`. The first dry run on a build
  carrying this task therefore reads every on-topic source again and keeps the new readings (`v1-e32-t30`),
  and the publish after it parses only the sources it quotes. The cloud-run landscape runbook's step 3
  already plans for that ("~5 to 12 min the first time this build reports the caselist"); with 4,342
  sources, expect the long end or a little over. No command changes.

## Operator follow-ups

None. The next republish of hspolicy26 (restored copy, cloud-run landscape runbook) is the operator's
after merge, as planned. Its step 3 dry run is the long one, as above.

## Follow-up work

* **Runbook wording** (`docs/runbooks/landscape-report-from-the-cloud-run.md`, step 3, outside this task's
  packages). It gives the first-report re-read's reason as "the caches hold only `2026.10.20-docx-6`
  readings". A rules-version bump such as this one causes the same re-read. One clause: "or readings of
  older rules".
* **A colon-less list's lines as planks** (E32, after t16): the 26 continuation copies' lines are plank
  lists, but the planks section does not count them. If the PM wants them there, t16's `listing` would
  also open on a continuation, and t16's plank counts would rise.

## PM questions

```text
v1-e32-t35 question for the PM (one, with a recommendation):

Grouping CP texts by the whole text (the spec's rule) splits shared stems. On the Mac's hspolicy26 store
the Advantage CP's top text, read by 12 teams as a stem, becomes 24 texts read by 1 team each, because
every team lists its own planks. The report's Advantage CP rows become three 1-team texts picked by digest
order. States CP rank 1 goes from 9 teams to 7.

Options:
A. Keep it as built. The planks section (t16) already shows which planks teams share, by advantage,
   and the CP-text rows show real whole texts.
B. Keep whole-text groups, and add one line per CP: "N teams read the first line of these texts", so
   the shared stem's reach still shows. Small follow-up, no change to grouping.
C. Group and rank by the first paragraph, and show the group's commonest whole text. This reverses the
   spec's "the digest covers what is shown".

Recommendation: A now, B as a follow-up if the coach misses the count. The planks section is where
an advantage CP's shared parts already show; C would bring back the cut-off texts this task exists
to fix.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
