# Session report: v1-e39-t03-search-core

| | |
|---|---|
| Task | `v1-e39-t03-search-core` — Search core: safe queries, ranking, filters, pages and card rendering over the index |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t03-search-core.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t03-search-core.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t03-search-core` |
| Session status | COMPLETE |

## Summary

The search core is built in `debate_core` and reads the `v1-e39-t02` index read-only. A query parser
turns any string into quoted FTS5 phrases joined by `AND`/`NOT`, with only `author:` (the cite column)
and `tag:` (the tag column) as prefixes. The rest of the stack:

* **Filters:** event, caselist or camp, side and first seen. The first-seen filter carries the PM's
  caselist-cards-only notice.
* **Ranking:** weighted BM25. The weights live in one constant, tag 10, cite 6, read-aloud 3, text 1,
  chosen from a grid on a synthetic relevance set.
* **Pages and cursors:** 20-result pages behind an opaque cursor bound to the index, query and filters.
* **Suppression seam:** for `v1-e39-t07`. A card whose representative is suppressed is hidden, and
  any other suppressed occurrence drops out with the counts redone.
* **Time budget:** uses SQLite's progress handler.
* **Rendering:** an escaping HTML renderer with a fixed allow-list of tags and classes.

All five criteria pass. The two SQLite 3.40.0 checks pass too: the reader's traced statements against
a hand-written list in every run, and the slow replay of those statements in
`public.ecr.aws/lambda/python:3.12` with `--network none`. On a synthetic index of 250,000 documents
the warm p95 is **340.8 ms**. Three things to look at first:

* the relevance set and how its first version misled me (Decisions 4);
* the budget cannot cut into FTS5's own ranking sort (Decisions 6);
* the team count after a partial suppression (Decisions 8).

The operator's read-only timing block for the real dev index is under Operator follow-ups. It is not a
criterion, so the Goal is `Succeeded`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `search-core` | Done | Domain parser, filters, cursor, models and renderer; reader port and SQLite reader; service with the suppression seam and time budget; 171 tests in the default run and 3 marked slow. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: every input string becomes a safe FTS5 expression or a literal. A property test over arbitrary strings never raises an FTS5 syntax error, and a prefix never searches a field it did not name | PASS | `test_search_index_reader_never_raises_a_syntax_error_on_any_query`: 500 examples per run, through the real reader against a real FTS5 index. The examples are arbitrary text and strings built from `AND`, `OR`, `NOT`, `NEAR(`, `NEAR/2`, `*`, `^`, brackets, `"`, `{tag cite}:`, `text:`, `rank:`, `rowid:`, NUL, emoji and combining marks. Prefixes: `test_evidence_search_prefix_searches_only_the_field_it_names` (11 cases by hand: `tag:wombat` → {2, 7}, `author:wombat` → {3}, `text:wombat` → {7} because it is the phrase "text wombat" found in document 7's tag, not a column filter). Two structural properties (400 examples each) check that a column filter appears only for a prefixed term and that no typed operator gets through. Run red against a skeleton that hands the raw query to MATCH: the property, the prefix cases and the parser cases failed (red-run table below). |
| ac2: filters and pagination are right over a synthetic index, and a cursor from another query is refused, by tests shown failing first | PASS | `test_evidence_search.py`: 17 filter cases written by hand over 8 documents; pages of 20/20/5 that concatenate to the whole ranking; 20/3 under a side filter; a page filled past suppressed cards with nothing skipped; a cursor refused for another query, other filters, another index id and a tampered character. `test_evidence_search_query.py`: 12 malformed cursors refused, plus a 300-example property that any string is refused with `InvalidSearchCursor` or decodes into range. **Red first:** against the refuse-nothing skeleton, 16 of the 17 filter cases failed (the no-filter case passes on any implementation), and so did both paging-under-filter tests, every cursor-refusal test and the first-seen test. |
| ac3: a fixture card holding a script element, an event-handler attribute and a `javascript:` link renders inert, and rendered output uses only the allow-listed tags, by test | PASS | `test_search_card_html_renders_a_script_a_handler_and_a_javascript_link_as_text`: the output is read back by `html.parser`, which finds only `span`/`br`, only `class` attributes, every class on a hand-written list, and text equal to the input. A hostile snippet, plain text and an unknown highlight colour (`cyan" onclick=...` becomes `card-highlight-other`) are covered too, as is a 300-example property over markup-heavy text. Through the index: `test_evidence_search_card_renders_inert_with_the_stored_spans_coverage` (exact markup written by hand). Red: all failed against the unescaping skeleton. |
| ac4: a rendered card's formatting coverage equals the stored spans' (the reading `formatting_sha256` uses), by test | PASS | `test_search_card_html_coverage_equals_the_stored_spans_reading`: 400 examples of random text and overlapping spans of every emphasis, colour and size; `formatting_sha256` of the rendered HTML read back equals it over the stored spans. Also a fixture whose coverage was read off by hand, and the same check through the index. Red: failed against a skeleton that drops formatting. |
| ac5: on a synthetic index of 250,000 documents generated in the run (marked slow), the 95th-percentile query time is reported | PASS | `uv run pytest -n0 -s -q -m slow packages/debate_core/tests/application/test_evidence_search_scale.py -k synthetic` → `1 passed in 56.28s` (load average 16). Index 604,528,640 bytes, built in 44.4 s, SQLite 3.50.4. **Warm, 60 searches: p50 69.1 ms, p95 340.8 ms, max 421.0 ms.** Cold first pass: p50 71.7 ms, p95 374.8 ms, max 450.3 ms. Matches per query run from 90 to all 250,000. |
| Node: search core tests pass (`uv run pytest packages/debate_core/tests -k search`) | PASS | `314 passed in 10.75s` |
| SQLite 3.40.0 ceiling, in every run (PM note) | PASS | `test_search_index_reader_runs_only_statements_sqlite_3_40_has`: every traced statement, parameters expanded, matches a hand-written shape, each shape is exercised, and none uses JSON, `unixepoch`, `STRICT`, `RETURNING` or a write. `test_search_index_reader_plan_ranks_inside_fts5_and_joins_by_key`: the ranking is FTS5's own sort and the joins are key lookups. |
| SQLite 3.40.0 ceiling, slow, in the Lambda image (PM note) | PASS | `uv run pytest -q -m slow packages/debate_core/tests/integrations/local/test_search_index_reader_sqlite_features.py` → `1 passed in 2.33s`. In the image: `sqlite3.sqlite_version == "3.40.0"`, the same rows for every core query and the card lookup, the same FTS5 rank plan, and a progress handler stops a statement with `interrupted`. |
| PM amendment 2026-10-20 (first seen) | PASS | Written into the spec's description, with a comment. `test_evidence_search_first_seen_leaves_camp_cards_out_and_says_so`. |

**The red run.** I committed the implementation, applied a refuse-nothing skeleton, ran the five new
test files, recorded the result and restored the committed files with `git checkout`. The skeleton:

* the raw query is handed to MATCH;
* any cursor is accepted;
* filters and suppression are ignored, and the budget never expires;
* text is not escaped, and runs carry no formatting.

The run used an empty `HYPOTHESIS_STORAGE_DIRECTORY` and gave **92 failed, 67 passed in 7.44 s**.

The 67 that passed are the cases a skeleton satisfies by accident: the no-filter case; provenance
words that `v1-e39-t02`'s index never holds, so they match nothing either way; the snippet splitter;
the provenance line; and the filter model's own validation.

**Mutation run**, scoped to the four new modules and capped at 20 mutants. Each mutant ran the five
test files from an empty Hypothesis database (agreement 8).

| # | Mutant | Result |
|---|---|---|
| 1 | Quotes not doubled | killed |
| 2 | Control characters (NUL) kept | killed |
| 3 | Prefix case-sensitive | killed |
| 4 | `author:` searches the tag | killed |
| 5 | Wordless terms kept (empty phrase) | killed |
| 6 | Cursor binding unchecked | killed |
| 7 | Cursor offset cap ten times higher | killed |
| 8 | Binding ignores filters | killed |
| 9 | Exclusion becomes AND | killed |
| 10 | Runs joined whatever their formatting | killed |
| 11 | Card hidden only when every occurrence is suppressed | killed |
| 12 | Search shows suppressed representatives | killed |
| 13 | Teams recounted from partial provenance | killed |
| 14 | First-seen notice inverted | killed |
| 15 | Interrupt overwrites a found next position | survived; killed after `test_evidence_search_stopped_after_finding_the_next_hit_resumes_at_that_hit` (a fake reader) |
| 16 | Side matched unquoted in `instr` | survived: **equivalent**, since no side name (AFF, NEG, PRO, CON) contains another; the quotes stay as a guard |
| 17 | An interrupted batch counts as exhausted | survived; killed after `test_search_index_reader_stopped_by_the_budget_is_interrupted_and_not_exhausted` |
| 18 | Quotes not escaped in HTML | killed |
| 19 | Any highlight colour becomes a class | killed |
| 20 | Every class allowed | survived, because the tests used the module's own `is_allowed_class` as the oracle; killed after the tests got a hand-written allow-list and `test_search_card_html_refuses_a_class_off_the_list` |

Final: 19 killed, 1 equivalent.

**Checks before the report:**

* `uv run scripts/affected_tests.py --run` → 32 test files, `1314 passed in 43.20s`, exit 0. The
  first run found one failure, `test_no_python_version_is_named_outside_the_one_declaration`: my
  reader docstring named SQLite's `3.11.0`, which the test reads as a Python version. I reworded it
  and the second run passed.
* `uv run ruff format --check packages/debate_core` → `460 files already formatted`.
* `uv run ruff check packages/debate_core` → `All checks passed!`
* `uv run pyright packages/debate_core` → `0 errors, 0 warnings, 0 informations`.
* `uv run lint-imports` → `Contracts: 12 kept, 0 broken`.
* `uv run scripts/validate_specs.py` → `OK: 396 files, 39 epics, 336 tasks, 21 releases`.

## Files changed

* **`packages/debate_core/src/debate_core/domain/evidence_search.py`** (new): the query parser and
  its FTS5 expression, `SearchFilters`, `RankingWeights` and the one `RANKING_WEIGHTS`, the bound
  cursor, the notices, the result and card models, `card_runs`, and the provenance line from stored
  fields.
* **`packages/debate_core/src/debate_core/domain/search_card_html.py`** (new): the escaping renderer
  for a card's runs, a snippet and plain text, with the tag and class allow-list.
* **`packages/debate_core/src/debate_core/application/ports/search_index_reader.py`** (new): the
  reader port and its typed rows.
* **`packages/debate_core/src/debate_core/application/evidence_search.py`** (new):
  `EvidenceSearchService` (search, card lookup, suppression seam, time budget) and
  `surviving_counts`.
* **`packages/debate_core/src/debate_core/integrations/local/search_index_reader.py`** (new): the
  read-only, immutable SQLite reader with its three statements.
* **`packages/debate_core/tests/`** (six new files): parser, cursor and provenance line (`domain/`);
  renderer (`domain/`); service (`application/`); ranking set (`application/`); scale and operator
  timings, slow (`application/`); reader and the 3.40.0 checks (`integrations/local/`).
* **The spec:** the PM's first-seen amendment of 2026-10-20 in its description, with a comment; Goal
  set to `Succeeded`.

`debate_api`, `t02`'s writer, build and port modules, and the parser are untouched.

## Deviations from the spec

None.

## Decisions and assumptions

1. **The query grammar.** Four things are read: a word, a `"phrase"` (an unclosed quote runs to the
   end), a leading `-`, and `author:` or `tag:` in any case. Everything else is literal and becomes a
   quoted FTS5 phrase of its words, so `don't` and `x-ray` match as adjacent words, and `text:wombat`
   is the phrase "text wombat".
   * Terms with no letter or digit are dropped. Probing showed that FTS5 reads `""` as matching
     nothing, which would silently empty an `AND`.
   * Control characters and lone surrogates become spaces. A NUL inside an FTS5 string raises
     "unterminated string", which I measured before writing the parser.
   * A query of exclusions alone returns nothing, with the `NO_SEARCH_TERMS` notice, because FTS5's
     `NOT` takes two sides.
   * Queries are capped at 512 characters and 32 terms, with the `QUERY_SHORTENED` notice.
2. **No way to search a person.** There is no prefix or filter for school, team code or debater, and
   `SearchFilters` refuses unknown keys. A test shows that `school:maple`, `team:QX`, `debater:...`
   and the tournament, round, camp and camp file title all match nothing. The `occurrences` table is
   read only by document id.
3. **The cursor needs no secret key.** It is base64 of `<offset>:<first 128 bits of
   sha256(index id, parsed query, filters)>`. Anyone can compute a binding, but a forged cursor only
   pages through the results of the query it is bound to, which its holder could request directly.
   Offsets are capped at 100,000. So no key and no ruling are needed. The binding uses the parsed
   query, so `growth  ` and `growth` share cursors. It includes the index id, so a weekly rebuild
   invalidates old cursors rather than shifting them.
4. **The ranking weights, and how the first relevance set misled me.** The set in
   `test_evidence_search_ranking.py` has 12 queries over 36 invented documents, graded by hand (0, 1,
   2). It encodes three judgments: a tag word beats body repetition, a bare name is usually an author,
   and what is read aloud is the card. I scored mean nDCG@5 over a 168-point grid: tag
   {1,2,4,6,8,10,16} × cite {1,2,3,4,6,8} × read-aloud {1,2,3,4}, text 1.

   The first version used five-word cites. Its only perfect point was tag 8, cite 8, read-aloud 2,
   and every neighbour scored lower. That was an artefact of BM25's length normalisation on
   unrealistically short cites, so I rejected it. Real cites run 20 to 40 words. With realistic,
   varied cite (16 to 30 words) and tag (4 to 13 words) lengths, 10 grid points score 1.0, forming a
   plateau at tag 8 to 10, cite 6 to 8, read-aloud 2 to 4 (and tag 6, cite 4, read-aloud 2). I chose
   its most interior point: **tag 10, cite 6, read-aloud 3, text 1**.

   | Weights (tag, cite, read-aloud, text) | Mean nDCG@5 |
   |---|---|
   | **Chosen (10, 6, 3, 1)** | **1.0000** |
   | Cite as tag (8, 8, 2, 1) | 0.9831 |
   | No read-aloud boost (10, 6, 1, 1) | 0.9322 |
   | The t02 probe (4, 2, 2, 1) | 0.9231 |
   | Cite light (8, 3, 2, 1), my prior before measuring | 0.9133 |
   | Tag only heavy (10, 1, 1, 1) | 0.8395 |
   | Equal (1, 1, 1, 1) | 0.8148 |
   | Text heavy (1, 1, 1, 4) | 0.8087 |

   The caveat: the set is synthetic and built from three patterns, each repeated four times. It
   justifies the order of the weights (tag > cite > read-aloud > text, with cite well above text) and
   rules out the extremes. It cannot replace the coach's beta (`v1-e39-t10`), which is where real
   queries will test them. The test holds that the chosen weights score at least as well as every
   candidate and better than equal weights.
5. **Filters.** A side is matched by `instr` of the quoted name in the stored JSON array, because the
   reader may use no JSON function. A camp filter implies `openev`, and a camp with a caselist slug
   is refused. A first-seen filter leaves camp cards out (their `first_seen` is NULL) and adds
   `FIRST_SEEN_CASELIST_CARDS_ONLY`. A side filter also leaves camp cards out, since they have no
   sides. That needed no notice under the amendment; say if you want one.
6. **The time budget, and where it cannot reach.** The default is 2.0 s. The reader installs
   `sqlite3_progress_handler` (every 1,000 VM instructions) for each ranked statement. When the budget
   is spent, the statement stops and the page returns the rows fetched so far, with `partial` set and
   a cursor that resumes after them. A sweep test checks that whenever the budget runs out, the page
   is a prefix of the ranking and the cursor resumes exactly after it.

   **Limit:** FTS5 computes and sorts the whole ranking inside one VM step before the first row comes
   back, and the progress handler only runs between steps. So a query's overshoot past the budget is
   at most that sort. On 250,000 synthetic documents the slowest whole search was 421 ms, against a
   2 s budget. What the budget does stop is the work after the sort: filters that reject most
   matches, deep offsets, snippets. Nothing in SQLite 3.40.0 interrupts FTS5's sort.
7. **The suppression seam.** `search` and `card` take `is_suppressed(source_sha256,
   disclosure_digest)`, defaulting to `None`. A camp occurrence is asked with `None` as its digest.
   * A card whose representative (ordinal 0) is suppressed is hidden from search and is not found by
     card lookup, until the next build. That includes a card with every occurrence suppressed.
   * Search fills its page past hidden cards and still pages correctly.
   * Any other suppressed occurrence drops out of the card's occurrences, and the counts are redone
     (Decisions 8).
8. **Counts after a partial suppression.** Files are exact: the distinct sources among the survivors.
   Teams are exact when every survivor kept its provenance. Otherwise the index cannot say which team
   disclosed an occurrence past the provenance limit, so the stored count stands, capped at the number
   of survivors. The PM may prefer showing no team count in that case. It is one function,
   `surviving_counts`, for `v1-e39-t07` to change.
9. **Rendering.**
   * Tags are `span`, `mark` and `br`; the only attribute is `class`.
   * Classes are one per emphasis (`card-underline`, ...), `card-highlight-<colour>` for OOXML's 16
     highlight colours, and `card-size-<half points>`.
   * A colour off the list becomes `card-highlight-other`, never its own text.
   * Text goes through `html.escape(quote=True)`, and `\n` becomes `<br>`.
   * Overlapping highlight colours or sizes are both kept on a run, so a read-back is lossless.
10. **The provenance line** is composed in the domain from the index's stored fields. Tests check it
    equals the E33 writer's `provenance_line` for every case: disclosure with every field, side only,
    unknown side, no disclosure, camp with and without its release record.
11. **Synchronous service.** The reader is blocking SQLite, so the service is synchronous. It is safe
    across threads behind a lock, for FastAPI's thread pool (`v1-e39-t06`). The index opens with
    `mode=ro&immutable=1`; the function must swap indexes by path, never rewrite one in place.
12. **ac5 ran in the session.** It finished in 56 s under a hard 170 s stop, inside agreement 2's
    limit, so it was not handed over. The synthetic texts are 120 words, while the real average is
    about 5,000 characters, so posting lists per document are shorter than the real index's. The
    operator's block measures the real one.

## Operator follow-ups

**Read-only timings on the real dev index** (expected runtime under a minute). This is not an
acceptance criterion. It reads the index without changing it and prints timings (p50, p95, max, warm
and cold), the slowest query's number, the match count per query and the first-page size per query.
It prints no tag, cite, text or provenance. The twenty generic queries are `OPERATOR_QUERIES` in
`test_evidence_search_scale.py`: common words, phrases, both prefixes, exclusions, `the` as the worst
case, and every filter.

Where: your Mac.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e39-t03-search-core
DEBATE_TUB_SEARCH_INDEX="${HOME}/.debate-research/dev/tub-index/b9fd48d280ab1c71/search-index.sqlite" uv run pytest -n0 -s -q -m slow packages/debate_core/tests/application/test_evidence_search_scale.py -k operators_index
```

Success looks like six lines starting `operator's index:` and then `1 passed, 1 deselected`. Paste
those lines back. A `1 skipped` means the variable did not reach pytest.

## Follow-up work

* **`v1-e39-t06`: Copy card needs inline styles.** Google Docs and Word ignore classes on pasted
  HTML, so the clipboard's `text/html` needs `style` attributes. `Card.runs` is plain data (text,
  emphases, colours, sizes), so `debate_api` can render it with a fixed style table, without touching
  card text. Alternatively the PM can move a style renderer into `debate_core` with a spec change.
  The page itself styles the `card-*` classes in CSS.
* **`v1-e39-t07`:** wire `is_suppressed` to the live list. Decide whether Decisions 8's team count is
  wanted.
* **E33 (refactor):** the E33 writer's `provenance_line` and the domain's
  `occurrence_provenance_line` compose the same line from different records, held together by tests.
  The writer could call the domain function.
* **`v1-e39-t09` / ADR-0019:** if the operator's real-index timings put any query near the 2 s
  budget, the place to look is FTS5's sort for very common words (Decisions 6).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
