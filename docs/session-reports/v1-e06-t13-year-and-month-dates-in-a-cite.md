# Session report: v1-e06-t13-year-and-month-dates-in-a-cite

| | |
|---|---|
| Task | `v1-e06-t13-year-and-month-dates-in-a-cite` — A cite can carry a year-only or year-and-month date without inventing a day |
| Spec | [`plan_specs/v1/e06-card-cutting/t13-year-and-month-dates-in-a-cite.yaml`](../../plan_specs/v1/e06-card-cutting/t13-year-and-month-dates-in-a-cite.yaml) |
| Epic / release | `v1-e06-card-cutting` / `v1.3` |
| Branch | `task/v1-e06-t13-year-and-month-dates-in-a-cite` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

A cite now carries a year-only or year-and-month date at its precision, and never adds a day or a
month. `Citation` gains `published_at_precision` and `Article` gains `date_precision` (`day`, `month`,
`year`). Both are left out of a stored row at `day`, so every row an older build wrote reads as a day,
and every day row is written byte for byte as before. `fetch --paste --date` takes `YYYY`, `YYYY-MM`
and `YYYY-MM-DD`, and refuses anything else, naming the three forms. A discovery candidate's year or
month is now stored on its Article, where v1-e07-t03's guard stored none. It reaches the cite through
the Crossref deposit its DOI names, but only when no source states a day. The cite prints `2026`,
`September 2026` or `September 14, 2026`, and the short cite's two digits are the year at any precision.
All three committed profiles print that text in the .docx.

**The PM ruled on both questions on 2026-11-13, both (a), as implemented**, and the Goal is
`Succeeded`. The month and year wording is `September 2026` and `2026`, with the short cite
unchanged. A cite's date comes from the Crossref record looked up by the Article's DOI, and
`Article.published_at` is not read into a cite. No code or expected value changed after the rulings.

## Questions for the PM, and the rulings

1. **The month and year rule in the cite (the stop you asked for).** A profile sizes the cite and
   never words it (`config/format_profiles/*.yaml`). The wording is `format_cite`'s alone, so all three
   profiles print the same line. Its day style is `September 14, 2026` in the full cite and `YY` in the
   short cite, and it has no rule for a month or a year. Proposed and implemented: **(a) the day's style
   with the missing parts left out**, so `September 2026` and `2026`, with the short cite `YY`
   unchanged (`Smith 26`). The alternatives are (b) the ISO forms `2026-09` and `2026`, which
   `search`'s table already prints for a discovery date (v1-e07-t03), or (c) another style, which
   you would give. I recommend (a). It reads like the day form beside it, and the short cite needs no
   change. Changing it is one function, `_date_at` in `citation_service.py`, plus the hand-written
   expectations.

   **PM ruling, 2026-11-13: (a).** The day style with the missing parts left out, the short cite
   unchanged, because it reads like the day form beside it. The hand-written expected cite lines stay
   as they are.
2. **Should the cite also read an Article's discovery date?** Nothing read `Article.published_at` into
   a cite before this task (v1-e07-t03's report says so), and nothing does now. A discovery candidate's
   year or month reaches the cite through the Crossref deposit the cite looks up by the Article's DOI,
   which is the same deposit the candidate came from. (a) Keep it so (implemented). (b) Also take the
   Article's date as a last-resort, unverified `heuristic` candidate. That would date cites for
   discovered sources whose page and Crossref state none, including a Semantic Scholar year with no
   Crossref record. But it also changes cites that print `ND` today, day dates included, so it is more
   than this task's scope. I recommend (a), with (b) as a follow-up if you want it.

   **PM ruling, 2026-11-13: (a).** Not (b), because an unverified guess would change cites that print
   `ND` today, day dates included. No follow-up task: (b) goes on the PM's V1.x list.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `year-and-month-dates-in-a-cite` (Partial dates) | Done; its criterion passes | Red run against a skeleton (`c7cab96`), then the implementation and CLI README (`184998e`). Goal `Succeeded` after the PM's rulings of 2026-11-13. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a year or year-and-month date is stored at its precision, from `fetch --paste` | PASS | `--date 2026` stores `2026-01-01T00:00:00Z`, raw `2026`, `year`, `heuristic`, unverified; `2026-08` gives `month`; `2026-08-30` gives `day` (`test_paste_with_a_year_month_or_day_date_stores_and_reports_it_at_that_precision`). It is stored on the card and in the embedded manifest at its precision (`test_a_stated_date_is_stored_on_the_card_and_in_its_manifest_at_its_precision`). The SQLite card and snapshot rows hold `"published_at_precision":"year"` or `"month"`, hold no key for a day, and read back equal (`test_a_cards_date_and_a_snapshots_stated_date_are_stored_and_read_back_at_their_precision`). |
| ac1: … printed and exported at its precision, from `fetch --paste` | PASS | The .docx cite line, written by hand, in each of `team-default`, `flow` and `plain`: `Okonkwo-Lindqvist et al. 25 [Mara Okonkwo-Lindqvist and Teodor Brannigan; "Mammoth Money and the Elephants Left Waiting"; The Synthetic Science Weekly; 2025; <url>; accessed October 26, 2026; user-supplied text]` for `--date 2025`, and `… 24 […; November 2024; …]` for `2024-11` (9 cases, `test_a_stated_year_month_or_day_date_prints_at_its_precision_in_every_profiles_docx`). `fetch` prints `Stated date 2026`, and `--json` gives `"published_at": "2026", "date_precision": "year"`, which fits `fetch_result.v1.json`. `verify` finds the year card UNVERIFIED for `CITATION_UNVERIFIED` alone. |
| ac1: … stored, printed and exported at its precision, from a discovery candidate | PASS | A Crossref candidate dated `2021`/`year` (and `2021-03`/`month`) goes through the real dedupe, rank and `ArticleMatchingStage`. Its Article stores `(2021-01-01, year)`. The cite resolved from a page with no date takes Crossref's `issued [[2021]]` as `2021-01-01`, raw `2021`, `crossref`, verified, `year`. The card is VERIFIED, and the .docx from `ExportService` prints, by hand, `Haddad-Whitcombe 21 [Noor Haddad-Whitcombe; "Seed Banks and the Long Drought"; Synthetic Policy Review; 2021; <url>; accessed October 26, 2026]` in all three profiles (`March 2021` for the month). The SQLite Article row holds `"date_precision":"year"` and reads back equal. |
| ac1: a day date prints as today | PASS | Every day case of the new tests passed on the skeleton, as on the start commit, and passes now. Of the existing tests, only the three that pinned the old rule changed: `2026` and `2026-08` left t12's two refused-date lists, and v1-e07-t03's discovery test now expects the date kept. Every other line of every existing test is unchanged (the diff deletes 17 lines, all in those three tests). t01's fixtures, t12's `PASTED_FULL_CITE` and `STATED_FULL_CITE`, and every cut, fetch and verify test pass. A day row is byte-identical to the start commit's (below). |
| ac1: by tests shown failing first | PASS | Red against the skeleton `c7cab96`: **73 failed, 46 passed in 3.06s**, below. |
| Node: `uv run pytest packages/debate_core/tests packages/debate_cli/tests -k "date or cite"` | PASS | **1675 passed, 2 xfailed in 26.89s**, run as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests packages/debate_cli/tests -k "date or cite" -q`. The two xfails are `test_cite_detection.py`'s labelled small-print cite line, xfailed before this task. |
| Forbidden: inventing a day or a month | PASS | Mutants 1 to 15 below, each caught on an assertion. The domain refuses a `year` or `month` date that is not the first instant of its period, and a precision with no date (`test_citation.py`, `test_article.py`; mutants 16 and 17). |
| Forbidden: a stored row an older build can't read without saying so in the report | PASS (said here) | An older build **refuses** a row with a year or a month. It never reads one as the first of January. See "What an older build reads". |
| Forbidden: network or live model calls in tests | PASS | Crossref answers come from `CitationWorld`'s respx router and the cut tests' `CrossrefAnswers`; pages come from t06's replay transport; the model is the fixture router; the smoke check runs under the network guard. |

### Red run

The skeleton (`c7cab96`) added `Citation.published_at_precision` and `Article.date_precision`, both
`day` by default and left out at `day`, with no validator, and moved `DatePrecision` to
`domain.enums`. The application and the CLI were the start commit's, so nothing set, refused or
printed a precision. Command:
`.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest <the eight test files below> -k "precision or year or month or date or forms or first_instant or day" -n 6 -q --tb=line`
→ **73 failed, 46 passed in 3.06s**. The 119 selected are this task's 101 new or changed cases and 18
existing ones the `-k` also picks. Grouped by reason, counted from the run's failure lines:

* a year or a month refused as today: `InvalidStatedCite` in the application (7), and fetch's usage
  error where a store was expected, which the cut, fetch and smoke tests then assert on (14) (21);
* a refusal that does not name the three forms, `YYYY-MM-DD` alone (30);
* `DID NOT RAISE ValidationError`: the domain refusing nothing (9);
* the precision or the date not set: `day` where `year` or `month` was expected, a deposit's year not
  taken, a stated year not kept beside a derived first of January (11);
* the date printed as a day, `January 1, 2021` for `2021` (2).

The 28 new or changed cases that passed are behaviour the skeleton already had: every day case,
the fields' own JSON and SQLite round trips (the field existed), a derived precision carried through
`evolve`, a day winning over a deposit's year (the start never read one), and the old-row read.

### What each committed profile prints

A format profile sizes the cite and never words it, so the three committed profiles print one text.
The tests write it out by hand for each profile and precision. The date and the short cite, for
`--date` on a pasted copy (`test_cut_command.py`) and for a Crossref date
(`test_year_and_month_dates_in_a_cite.py`):

| Precision | Stated | `team-default` | `flow` | `plain` | Short cite |
|---|---|---|---|---|---|
| year | `--date 2025`, Crossref `[2021]` | `2025`, `2021` | `2025`, `2021` | `2025`, `2021` | `… 25`, `… 21` |
| month | `--date 2024-11`, Crossref `[2021, 3]` | `November 2024`, `March 2021` | the same | the same | `… 24`, `… 21` |
| day | `--date 2026-09-15` | `September 15, 2026`, as before | the same | the same | `… 26` |

The month and year rule is the PM's ruling 1 (2026-11-13), as proposed.

### What an older build reads

I wrote an Article, a pasted copy's SourceSnapshot and a Card with this build, at each precision,
and read each with the start commit's own models (`git archive 29f9d41`, first on `sys.path`; the
scripts are in the session scratchpad):

| Row | Day | Month | Year |
|---|---|---|---|
| Article | read, `2021-03-04` | refused: `extra_forbidden` at `date_precision` | refused, the same |
| SourceSnapshot | read | refused: `extra_forbidden` at `stated_citation.published_at_precision` | refused, the same |
| Card | read | refused: `extra_forbidden` at `citation.published_at_precision` | refused, the same |

Re-written by the start commit, each day row is **identical byte for byte** to this build's (Article
441 bytes, Card 1189, SourceSnapshot 1286). The start commit's `CardManifest` is `extra="forbid"` and
embeds the domain `Card`, so an older `verify` refuses a .docx whose card has a year or a month, and
reads a day one as before. No older reader misreads a year as January 1st, so I propose no guard:
the domain's `extra="forbid"` already is one. What a person sees is a refusal. An older build's
SQLite repository reports the whole row unreadable, an Article included: one that a search on this
build registered with a year date cannot be read by an older build on the same data directory. The
CLI README's `fetch` section says a year or a month needs this build or later.

### Mutants

21 mutants of the committed source, each run against the eight covering files
(`test_year_and_month_dates_in_a_cite.py`, `domain/test_citation.py`, `domain/test_article.py`,
`test_federated_search_articles.py`, `test_citation_service.py`, `test_fetch_command.py`,
`test_cut_command.py`, `tests/smoke/test_cut_smoke.py`). Each run had a new, empty
`HYPOTHESIS_STORAGE_DIRECTORY` (none of these files uses Hypothesis) and was restored with
`git checkout HEAD --` afterwards. The tree was clean after every batch. **All 21 were caught.** Where a
mutant also made other tests crash, I ran the targeted test alone and it failed on its assertion
(mutants 11, 18 and 19).

| Mutant | Result |
|---|---|
| PM, raise: a stated year recorded as a day | Caught, 10 failed |
| PM, raise: a stated month recorded as a day | Caught, 10 failed |
| PM, raise: a stated year recorded as a month | Caught, 10 failed |
| PM, raise: a discovery-only Article's year or month stored as a day | Caught, 4 failed |
| PM, raise: a deposit's year taken as a day | Caught, 4 failed |
| PM, raise: a deposit's month taken as a day | Caught, 3 failed |
| Raise: a deposit's year preferred to its month | Caught, 1 failed |
| PM, raise: a year printed as a month (`January 2021`) | Caught, 7 failed |
| PM, raise: a month printed as a day (`March 1, 2021`) | Caught, 6 failed |
| PM, raise: every date printed as a day | Caught, 13 failed |
| Raise: a kept stated year takes the derived day's precision | Caught, 13 failed; `test_a_stated_year_is_kept_beside_a_derived_first_of_january…` on its assertion |
| Raise: a stated year equal in value to a derived day is replaced by it | Caught, 23 failed |
| Raise: `fetch --json` reports every stated date to the day | Caught, 5 failed |
| Raise: `fetch --json` drops the precision | Caught, 3 failed |
| Lower: a deposit's year beats a page's day | Caught, 9 failed, t01's unchanged journal-PDF and fixture tests among them (that deposit's print date is a month) |
| Domain: a cite's year or month need not start its period | Caught, 4 failed (`DID NOT RAISE`) |
| Domain: an Article's year or month need not start its period | Caught, 2 failed (`DID NOT RAISE`) |
| PM, old row: a cite with no precision key reads as a year | Caught, 88 failed; `test_a_row_written_before_the_precision_existed_reads_as_a_day` on its assertion (`year` for `day`) |
| PM, old row: an Article with no precision key reads as a month | Caught, 137 failed; the same test on its assertion (`month` for `day`) |
| Old row: a cite's precision never written, so a year reads back as a day | Caught, 12 failed |
| Old row: an Article writes its `day` key, so day rows change and older builds refuse them | Caught, 6 failed |

### Checks before the report

* **Affected set**: `uv run scripts/affected_tests.py` chose **763 test files** of the repository's
  766. `domain/article.py` reaches the root `conftest.py` through `debate_core.domain`. That is the
  whole suite in all but name, well over two minutes, so it is **left to the pull request's `ci`**
  (agreement 10). Within two minutes, each run under `scripts/hard_stop.py 115`:
  * the always-run list (`tests/architecture`, `tests/specs`, `test_app.py`, `test_help_rendering.py`,
    `test_container_factories.py`): **379 passed in 22.09s**;
  * `packages/debate_core/tests/domain` and `evidence`: **3063 passed in 13.56s**;
  * `packages/debate_core/tests/application`: **5938 passed in 93.51s**;
  * the top-level files of `packages/debate_cli/tests`: **1124 passed in 40.18s**;
  * `tests/smoke/test_cut_smoke.py` and `test_fetch_smoke.py` on the checkout's console script:
    **13 passed in 6.03s**. Not run on a stamped, installed build.
* `uv run --frozen ruff format --check .` → 2106 files already formatted. `ruff check .` → All checks passed.
* `uv run --frozen pyright packages/debate_core packages/debate_cli tests/smoke/test_cut_smoke.py` → 0 errors.
* `uv run --frozen lint-imports` → 20 kept, 0 broken.
* `uv run --frozen python scripts/check_thin_handlers.py` → 74 handlers within 25 statements.
* `uv run --frozen python scripts/check_command_blocks.py` → no `#` comments in 703 blocks.
* `uv run --frozen python scripts/export_schemas.py --check` → 10 schemas up to date.
* `uv run scripts/validate_specs.py` → OK: 684 files, 41 epics, 621 tasks, 22 releases.
* `docx_verify.py` and its tests are untouched (`git diff 29f9d41 --stat` on them is empty).
* Dev has moved one commit past the branch point: `e39d700`, v1-e06-t16, local ref, not fetched. It
  changes `docx_verify.py` and its tests, which this branch does not touch, and no code file both
  change. `docx_verify` does not call `format_cite`. I did not sync.

## Files changed

* `debate_core.domain`:
  * `enums.py`: `DatePrecision`, moved here from `discovery.py`, so that `citation.py` can use it
    without an import cycle. `discovery.py` re-exports it, so `from debate_core.domain.discovery
    import DatePrecision` still works;
  * `citation.py`: `Citation.published_at_precision`, its validator, and `period_start`;
  * `article.py`: `Article.date_precision` and its validator.
* `debate_core.application`:
  * `citation_service.py`: `stated_citation` takes the three forms; Crossref's year or month is used
    when no source states a day; `keep_student_edits` compares precision; `format_cite` prints at
    precision; `STATED_DATE_FORMS`; the docstrings;
  * `federated_search_articles.py`: `discovery_article` keeps the date with its precision;
  * `article_fetch.py`: `StatedCite.published_at` at precision, and `date_precision`.
* `packages/debate_core/schemas`: `article`, `card`, `citation`, `source_snapshot` and
  `fetch_result.v1.json`, regenerated by `scripts/export_schemas.py`. Each gains one optional key.
  `card_manifest.v1.json` refers to `card.schema.json` and is unchanged; `verify_result.v1.json` has
  no cite field and is unchanged.
* `debate_cli`: `commands/fetch.py` (the `--date` help, the docstring and the exit-code line) and
  `README.md` (the `fetch` section).
* Tests: `test_year_and_month_dates_in_a_cite.py` (new, 40 cases), `domain/test_citation.py` (+11),
  `domain/test_article.py` (+6), `test_federated_search_articles.py` (4, changed),
  `test_citation_service.py` (7, changed), `test_fetch_command.py` (+13, and 6 changed),
  `test_cut_command.py` (+13), `tests/smoke/test_cut_smoke.py` (+1).

## Deviations from the spec

1. **The month and year rule was proposed, then ruled (question 1).** The PM's brief said to stop for
   this ruling only. I stopped with the rule implemented, and the PM ruled (a), as proposed, on
   2026-11-13. The phase was set to `Succeeded` after that.
2. **A discovery candidate's date reaches the cite through Crossref, not the Article (question 2).**
   The spec says a candidate's year or month reaches "the Article and the cite". It reaches the
   Article directly, and the cite through the deposit the cite already looks up by that Article's DOI.
   The PM ruled (a), keep it so, on 2026-11-13.
3. **The node's command was run under the hard stop.** I ran
   `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest …`, as working agreement 10
   asks, rather than `uv run pytest …`. The selection is the same.

## Decisions and assumptions

1. **The precision is a field beside the date** (`Citation.published_at_precision`,
   `Article.date_precision`), not a field inside `CitationField`. Moving it into the field would have
   needed a new field class for the date, and every existing construction of
   `CitationField[datetime]` for `published_at` would have had to change. `keep_student_edits` carries
   the precision with the date it keeps, and the domain refuses a pair that disagrees.
2. **Day is the default and is never written.** Old rows read as a day, which is what they were. Day
   rows, `fetch --json` for a day date, and every schema's required keys are unchanged.
3. **A cite's date is chosen at the finest precision stated.** A day from any source, by the old
   precedence, wins over Crossref's year or month. Among a deposit's dates without a day, its first
   month wins over its first year. So no cite that had a day loses it (mutant 15). Crossref's dates were
   already read in order and the first whole one taken; the partial ones follow the same order.
4. **A stated date is the same as a derived one only at the same precision.** A stated `2026` beside a
   derived `January 1, 2026` is kept, with its year, and named among `stated_fields`.
5. **`fetch --json`** prints `published_at` at its precision (`2026`, `2026-08`, `2026-08-30`). It adds
   `date_precision` only for a month or a year, so that a day report is byte-identical and t12's pinned
   `stated_cite` still holds.
6. **Refused `--date` forms** are anything but `YYYY`, `YYYY-MM` or `YYYY-MM-DD` naming a real
   period: `2026-13`, `2026-00`, `0000`, `2026-8`, `26`, `2026-08-`, `August 2026`, plus t12's list.
   The message is `'<text>' is not a date in the form YYYY, YYYY-MM or YYYY-MM-DD, such as 2026,
   2026-09 or 2026-09-14`.
7. **No fixture file added.** The two Crossref answers for the discovery test are written inline in
   the test, under the `10.5555` test prefix, so `tests/fixtures`, outside the packages, is unchanged.

## Operator follow-ups

None (the PM asked for no command). The affected set is left to the pull request's `ci`.

## Follow-up work

1. **A page's own year or month** (E06): `citation_harvest.parse_stated_date` still reads no
   `citation_publication_date` of `2021` or JSON-LD `datePublished` of `2021-05`. The function is in
   `debate_core.retrieval`, outside this task's packages. With it, a scholarly landing page that states
   only a year would cite that year without Crossref.
2. `search --json`'s `date_precision` is v1-e08-t12's and untouched here.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-14

**Notes:**

Accepted. ac1 and the node pass, and the Goal is `Succeeded`.

* **The rulings are built as given.** `2026` and `September 2026`, with the short cite unchanged (Q1,
  a). A cite's date comes only from the sources it already reads, with Crossref's year or month used
  only when no source states a day (Q2, a). No precision is ever raised, which the domain refuses at
  construction.
* **The old-row handling is the strongest part, and it meets the forbidden line by being said.**
  * Day is the default and is never written, so every day row is byte-identical to the start
    commit's (Article 441, Card 1189, SourceSnapshot 1286 bytes).
  * An older build refuses a year or month row (`extra_forbidden`) rather than misreading it as the
    first of January. So the domain's own `extra="forbid"` is the guard, and no new one is needed.
  * The cost, an older build unable to read such a row on the same data directory, is stated, and
    the CLI README says a year or month needs this build or later. Nothing in the cloud reads these
    rows: the weekly run reads the parsed store, and the pilot reads its index.
* **The evidence is thorough.**
  * The red run on a skeleton had 73 failed and 46 passed, the passes being every day case and the
    fields' own round trips.
  * 21 of 21 mutants were caught, each raise of a precision among them.
  * The diff deletes 17 lines, all in the three tests that pinned the old rule.
* **Deviations 1 to 3: accepted.** They are the PM's rulings, and the hard-stop form of the node
  command.
* **The branch is behind dev by v1-e06-t16** (`docx_verify.py` and its tests, untouched here). If
  `scripts/task pr` asks, `scripts/task sync`.
* **The affected set** (763 files) goes to `ci` under agreement 10.
* **Follow-ups:**
  1. A page's own year or month (`citation_harvest.parse_stated_date`) goes on the PM's V1.x list, as
     a p3 under the December rule.
  2. `search --json`'s precision is v1-e08-t12's.

`scripts/task pr`
