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

**Verdict:** CHANGES_REQUESTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-31

**Notes:**

The work is careful and almost all of it stands. The one change is to the grouping, a ruling against
my own spec line, and it is better made now than after a republish.
1. **What stands, accepted as built:**
   * **The count.** It was read-only, proven by unchanged mtimes, with no words quoted. It found that
     all 7 shown colon texts have t16 planks. The continuation shape (26 copies, a second analytic per
     plank, never an undertag or a split paragraph) explains rank 3: the 5–5 tie between `should:` and
     a bare `should`. That is exactly the finding the gate was for.
   * **Showing a text whole:**
     * colon lists by t16's rules and caps;
     * the continuation rule, which joins on shape and ignores a capital (Deviation 1, accepted; the
       PM amends the spec's "no capital");
     * every line read back and checked for a school, with one naming a school withholding the
       whole text;
     * paragraph indices only in the reading, no words cached;
     * one row per line in report.md.
   * **The evidence:** red at the skeleton; 13 mutants caught, three of them by tests you added after
     they survived; the node criterion passes (133).
2. **The change: group and rank by the opening paragraph, and show the group's commonest whole text.**
   Your measurement is why. Under whole-text grouping, the Advantage CP's 12-team text becomes 24
   one-team texts. Its rows are then three ties picked by digest order, and the first is a copy with no
   lines. The coach reads these rows to learn what the field runs. Here they would hide the most-read
   advantage CP behind random single copies. That is worse than the cut-off this task fixes.

   My spec line "the digest covers what is shown" wanted two things, and only one of them is right:
   * **Right:** the checks cover what is shown. Read-back and the school check apply to every line of
     the text quoted. Keep that exactly as built.
   * **Wrong:** grouping by the whole text.

   Build this:
   * **Group key:** the opening paragraph's digest, as before t35. Rank groups by distinct teams, as
     before.
   * **Shown text:** the group's commonest whole text, counted by distinct teams reading that exact
     whole text. Ties go to the existing tie-break.
   * **Read-back and withholding:** applied to the shown whole text's every line. If the commonest
     whole text cannot be read back or names a school, fall to the next whole text in that group,
     as the group falls through today.
   * **The rank row** says how many of the group's teams read the shown whole text, e.g. `12 teams;
     the planks shown are 1 team's`. Use your judgment on the words and keep them short. Put the count
     in the JSON as well.
   * **The cached reading** gains whatever grouping needs (the opening paragraph's digest) inside the
     same rules bump, `analytic-texts-3`. That means one re-read for the operator, not two. If
     `analytic-texts-3` is already the version you set, leave it and say so.
   * **Mutant 3** ("grouped and checked on the stem, shown whole") becomes two mutants: (3a) checked
     on the stem only, which must be caught; (3b) grouped on the whole text, which must now be caught
     too.
   * **Re-measure on the same store, read-only as before:** the before/after table, the Advantage CP's
     and States CP's rows (teams, and teams for the shown text), and distinct groups. Expect the
     Advantage CP back at 12 teams, showing one whole text with lines.
3. **The PM question:** answered by point 2, which is C with the checks kept on the whole text and
   with the shown text's own team count. B's extra line is not needed once the group count is the
   stem's.
4. **Follow-ups:**
   * **The runbook clause** ("or readings of older rules"): the PM's next batch.
   * **Colon-less lists as planks:** not filed. t16's counts stay as they are unless the coach asks.
5. **Then:** append the re-work to this report, not over it, and the PM reviews again. Run the
   affected set once more within the limit, leaving the rest to `ci`.

## Re-work after the PM review of 2026-10-31

**Session status:** COMPLETE again; the Goal stays `Succeeded`, every criterion passing under the ruling.

### What changed

The grouping now follows the PM's point 2. Everything else in the review's point 1 stands as built.

* **Group key:** a CP text's reading keeps its opening paragraph's digest
  (`AnalyticTextReading.opening_digest`: the stem's own digest, equal to `digest` when the text has no
  lines). The report keys a CP group on it and ranks groups by distinct teams, as before t35. A reading
  without it falls back to `digest`, which is the opening for any reading with no lines.
* **Shown text:** the report gives a CP group each source's teams (`TextGroup.source_teams`).
  `top_texts` then orders the group's whole texts (`whole_texts_by_teams`) by the distinct teams whose
  files hold that exact whole text, then by the existing tie-break (first copy by source and paragraph).
  It shows the first one that names no school. Each whole text passed over for naming a school counts as
  withheld; a group with none left is not shown. Read-back is unchanged: a whole text not read back as
  read has no copy to choose. Every other kind (alternatives, roles of the ballot, planks) keeps the
  commonest wording by copies, exactly as before.
* **The count:** `QuotedText.text_teams`, the group's teams whose files hold the shown whole text. It is
  never more than the group's teams, a rule the model enforces. The rank row says it only when the shown
  text has planks and fewer teams read them: `| 1 | 12 (1 with these planks) | ... |`. Texts without lines,
  and every golden row, render as before.
* **The rules version** was already `analytic-texts-3` (set in `25cff2c`), so I left it and the opening
  digest goes in under it. On hspolicy26's config the rules digest is still `54b853442079…`, and the
  operator re-reads once. No build carrying t35 has reported yet, so no cache holds t35 readings without
  the opening digest.
* **The guide's paragraph** says how a CP text is grouped and what the note means. The fixture, its README
  and its hand-written section were redone for the new rule (below).

**"The JSON".** The bundle has no JSON file: report.md and five CSVs. The CLI's `--json` output carries
counts and never a text. So the count is on the report model (`QuotedText.text_teams`), the JSON form of
the report that `LandscapeReport.model_dump_json` gives. If the PM meant a CLI field, it would have to be
a count with no text beside it; I did not add one.

### Commits

`c4b2c1b` tests and fixture, run red against a skeleton (fields with no rule);
`3e02d83` the grouping; `3a09102` the fixture README's mutant notes, as the runs found them;
`df8276f` the guide.

### Tests shown failing first

The skeleton has `opening_digest`, `source_teams` and `text_teams` as fields with no rule and no use.
Against it, the two new modules gave **11 failed, 17 passed**:
* the opening-digest assertions;
* the four `top_texts` group tests (most teams, tie-break, fall-through, all withheld);
* the two validators;
* both report tests. The report-level red shows the first build's whole-text grouping: rank 1 at 4 teams,
  where the colon list and the dash continuation share their words.

The 17 that passed are t35's first-round tests, whose rules did not change.

### The fixture, by hand

`tests/fixtures/landscape/cp_texts_shown_whole` now holds one opening paragraph read by 6 teams, in three
whole texts:
* a colon list with two planks: 3 teams, 2 copies;
* the same opening with a plank naming `Birchmoor`: 4 teams, 4 copies;
* a dash continuation: 1 team, 3 copies.

It also holds a Congress text read by 2 teams. The 4-team text is passed over for naming a school, so
the 3-team text shows as `6 (3 with these planks)`. The most-copies, 1-team text does not show. Rank 2
is the Congress text at 2 teams, and 1 text is withheld.

### Mutants (agreement 8)

The same harness, a fresh `HYPOTHESIS_STORAGE_DIRECTORY` per run, and the same suites plus the cache
store's test. Each file was restored from HEAD, and the tree was clean after the run.

| Mutant | Result | Caught by |
|---|---|---|
| 1 the planks dropped | CAUGHT, 9 failed | the colon, caps, inline, opening and read-back tests, the docx plank test, both report tests |
| 2 a plank naming a school shown (school check on the first line only) | CAUGHT, 4 failed | the fall-through and all-withheld tests, both report tests |
| **3a checked on the stem only** (read back against the opening digest, shown whole) | CAUGHT | `test_a_whole_text_whose_plank_reads_differently_now_is_not_quoted` |
| **3b grouped on the whole text** | CAUGHT, 2 failed | both report tests |
| 14 the shown whole text chosen by copies, not teams | CAUGHT, 3 failed | `test_a_group_shows_the_whole_text_the_most_of_its_teams_read_and_how_many`, both report tests |
| 15 no fall-through (a group withheld when its first whole text names a school) | CAUGHT, 4 failed | the fall-through and all-withheld tests, both report tests |
| 16 the group's teams given as the shown text's | CAUGHT, 5 failed | the most-teams, tie-break and fall-through tests, both report tests |
| 4 to 13 (the continuation's limits, the missing line, the rows, the line order) | all CAUGHT | as in the first round |

### The re-measure (the same store, read-only as before)

The same method and store (`~/.debate-research/dev`, hspolicy26, snapshot 2026-10-20, 3,825 sources).
The before side is the cache's readings, the after side the 138 sources holding a quoted CP text read
again in memory by this build, and both are ranked by the report's own `_landscape_texts`. It took 91.5 s
at a load of 11. The store's 11 files were unchanged afterwards (mtimes and sizes). The before side is
pre-t35 grouping by the opening. Its shown wording is chosen by this build's teams rule, which is why it
has a "shown" count at all; t35's first build had none.

| CP | Before: rank, teams (teams reading the shown text), lines | After: rank, teams (teams reading the shown text), lines | Distinct groups before → after |
|---|---|---|---|
| Advantage CP | 1: 12 (9), 0 · 2: 1 (1), 0 · 3: 1 (1), 0 | 1: **12 (1), 6 lines** · 2: 1 (1), 0 · 3: 1 (1), 4 lines | 5 → 5 |
| States CP | 1: 9 (9), 0 · 2: 3 (3), 0 · 3: 3 (2), 0 | 1: **9 (7), 5 lines** · 2: 3 (3), 6 lines · 3: 3 (1), 3 lines | 30 → 30 |
| Vouchers CP | 3: 1 (1), 0 | 3: 1 (1), 5 lines | 4 → 4 |
| Taxes PIC | 1: 1 (1), 0 | 1: 1 (1), 4 lines | 1 → 1 |
| Public option, NHS, Smokers PIC, Delay CP | unchanged | unchanged, no lines | unchanged |

* The Advantage CP is back at 12 teams, showing one whole text with lines, as the PM expected. Its row
  will read `12 (1 with these planks)`: every team's planks differ.
* The States CP keeps its ranks and team counts. Rank 1 shows the planks 7 of its 9 teams read.
  Rank 3 (the 5–5 tie group the coach read cut short) shows a whole text with 3 planks, read by 1 of its
  3 teams.
* Distinct groups, coverage (235 found, 160 counted, 0 withheld, 0 unread) and the planks section are all
  as before t35. 121 of the 169 copies in range carry lines, as in the first round.

**What the next republish will show differently**, replacing the first round's table: the same CPs, the
same ranks and team counts as before t35. Each CP text that has planks is shown whole, its rank row naming
how many of its teams read those planks when that is fewer. The cache refresh is as the first round said:
one re-read of every on-topic source at the first dry run on this build.

### Checks before this section

| Check | Result |
|---|---|
| `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests -k analytic_text -n 4 -q` (the node criterion) | **138 passed** in 13.98 s (28 of them the new modules') |
| Neighbouring suites (as in the first round, plus the store test) | 343 passed |
| `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python scripts/affected_tests.py --run` | 143 of 605 files from 18 changed files. **Stopped at the 115-second limit at 43%: 2,160 passed, none failed** (load 20 to 26 from other sessions). The rest is left to `ci`, as the review says. |
| `ruff format --check` / `ruff check` (packages, tests) | 1202 files formatted / All checks passed |
| `pyright packages/debate_core` / `lint-imports` | 0 errors / 19 contracts kept |
| `scripts/check_links.py` / `scripts/validate_specs.py` | OK / OK: 537 files |

### Deviations

2. **The spec's ac1 phrase "the group's digest covers what is shown"** is superseded by the PM's ruling
   (point 2). The checks cover what is shown; the group is the opening paragraph's. I did not edit the
   spec. It wants the PM's amendment, with Deviation 1's "no capital".

### Decisions

* **"That exact whole text" is the text word for word**, as `commonest_text` compares wordings. A colon
  list and a dash continuation with the same planks are two whole texts, each with its own teams. On the
  store, this matters only inside groups that mix the two shapes.
* **Withheld for a CP text** counts each whole text passed over for naming a school, and every whole text
  of a group none of which can be shown. A school-naming text ranked below the one shown is not shown and
  not counted, as a non-commonest copy never was.
* **The row's note** appears only when the shown text has planks and fewer of the group's teams read
  them. With no planks shown, the note would only count punctuation variants, and the golden report's
  rows would change for nothing.

## PM review (second, of the re-work)

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-31

**Notes:**

The re-work does what point 2 asked. The re-measure shows the coach will see the same CPs, ranks and
team counts as before t35, each now shown whole.
1. **The grouping.**
   * Groups are keyed on `opening_digest` and ranked by distinct teams.
   * The shown text is the whole text the most of the group's teams read, falling through past any
     that names a school.
   * The checks stay on every line shown: 3a, checked on the stem only, is caught by the read-back
     test.
   * `text_teams` is never more than the group's teams, and the model enforces it.
   * The note appears only when planks are shown and fewer teams read them, so the golden rows don't
     move.
2. **Red against a skeleton:** 11 failed, all on the new rules. The 17 first-round tests passed
   unchanged.
3. **Mutants:** 3a, 3b, 14, 15 and 16 were all caught, with first-round mutants 4 to 13 still caught.
4. **The re-measure.** The Advantage CP is back at 12 teams, showing one whole text with 6 planks
   (`12 (1 with these planks)`). States CP rank 1 keeps its 9 teams and shows the planks 7 of them
   read. Rank 3, the group the coach read cut short, now shows a whole text. Distinct groups and
   coverage are unchanged. The store was untouched (mtimes and sizes).
5. **Decisions accepted:**
   * the count on the report model, since the bundle has no JSON file and the CLI's `--json` carries
     counts only, so no field is added there;
   * "exact" meaning word for word;
   * the withheld counting;
   * the rules version left at `analytic-texts-3`, so the operator re-reads once.
6. **Deviations 1 and 2:** the PM's next batch amends the spec: "no capital" comes out, and ac1's
   "the group's digest covers what is shown" becomes "the checks cover what is shown; a CP group is its
   opening paragraph's". It also adds the runbook clause ("or readings of older rules").
7. **Closing checks:** the node criterion (138), the neighbours (343), ruff, pyright, lint-imports, the
   links and the specs are clean. The affected set (143 files) stopped at 43% at its limit with nothing
   failing, under heavy load, and is left to the PR's `ci` under agreement 10.
8. **Merge:** a plain `scripts/task pr` once `ci` is green. The next hspolicy26 republish, from a
   restored copy via the cloud-run landscape runbook, re-reads every on-topic source once at step 3's
   dry run, which takes the long end of its estimate. It is best run after Wednesday's run, when the
   stores are docx-7.

