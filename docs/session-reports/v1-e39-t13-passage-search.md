# Session report: v1-e39-t13-passage-search

| | |
|---|---|
| Task | `v1-e39-t13-passage-search` — Find a card that says something: passage search, word stems and prefixes |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t13-passage-search.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t13-passage-search.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t13-passage-search` |
| Session status | COMPLETE |

## Summary

A student can now tick **Search by passage**, paste a sentence, and find the cards that share most of
its content words in any order. The share is 66 percent, rounded up. Words are stemmed, so `grow`
finds `growing`, and `grow*` is a prefix. All of it goes through `v1-e39-t03`'s query parser, which
enforces the PM's limits: a prefix needs three characters before its `*`, a passage keeps 40 content
words, and the stop words are one constant. Each limit's tests were shown failing first. The index
format is now **2**: format 1 with FTS5's `porter` stemmer in front of `unicode61`.

The function reads formats 1 and 2, so it can be deployed first. On format 1 the page says that
stems and passages wait for the next weekly update. Any other format is refused with a message,
never by failing queries.

**Trigram is not adopted.** Measured on a sample of the dev store and scaled to its 50,434
documents, a trigram table would put the gzip object at about 1,030,000,000 bytes. That is 2.6 times
the 400,000,000 line, and it would bring the promotion list's item 12, the Lambda bandwidth quota,
forward. The SQLite file would be about 1,832,000,000 bytes, past the 1,700,000,000 warning. The
first PM question below asks for the ruling.

Every acceptance criterion passed, so the Goal is `Succeeded`. The post-merge moves (deploy, build
format 2, publish, time three searches, reinstall the agent) are operator follow-ups and are not
criteria.

**Look at first:** [the measurement](#the-trigram-measurement-ac3) and the
[questions for the PM](#questions-for-the-pm).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `passage-search` | Done | Parser, format 2, reader, holder, service and pages, in that order. Measured before adopting anything: format 1 built and timed before the first code change |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: passage mode finds a synthetic card from a sentence sharing most of its content words in another order, ranks it above cards sharing fewer, by tests shown failing first | PASS | `test_evidence_search_passage.py`: seven content words, a minimum of five. The card holding all seven ranks first, six ranks above five, and four or fewer are not found. Red first, against a skeleton whose passage kept no minimum (`HAVING count(*) >= 0`): **8 failed, 30 passed**. Green: 38 passed. Through the app, `test_search_pages_passage.py::test_a_passage_finds_the_card_holding_most_of_its_words`: the featured card from a sentence of nine content words that, typed as plain words, matches nothing |
| ac2: stemmed and prefix terms match, by test; every existing query test passes unchanged except where stemming is the point, each change named | PASS | `test_stemmed_word_matches_its_other_forms` (8 cases), `test_prefix_matches_every_word_it_starts` (6), and the page and browser tests. Existing tests changed: [the list below](#existing-tests-that-changed-ac2). No ranking, result or count expectation changed |
| ac3: the trigram measurement (bytes, bytes per document, build time) on the dev store is reported to the PM before any adoption | PASS | [The trigram measurement](#the-trigram-measurement-ac3), taken on a sample of the dev store as the PM's context of 2026-10-23 asked, plus the whole dev index for format 2. Nothing trigram is in the code or the index |
| ac4: the format version is 2; a holder given an index of another format refuses it with a message, by test; the p95 query time on the measurement index is recorded | PASS | `SEARCH_INDEX_FORMAT_VERSION: Final = 2`. `test_holder_refuses_a_format_it_does_not_read_with_a_message` asserts the message ends `its format version is not one this build reads, 1 or 2`. `test_holder_keeps_serving_when_a_format_it_does_not_read_is_published` shows the loaded index serving on and the warning logged. p95 on the format 2 measurement index (50,434 documents): plain **67.5 ms**, passage **335.0 ms**, prefix **146.8 ms** ([timings](#query-times-on-the-measurement-index)) |
| Node `passage-search`: Search tests pass (`uv run pytest packages/debate_core/tests -k "evidence_search or search_index"`) | PASS | Run as `.venv/bin/python -m pytest packages/debate_core/tests -k "evidence_search or search_index" -q` under a 115 s alarm → **545 passed in 7.77s** |

### Red runs, before the code they test

| What | Skeleton | Result |
|---|---|---|
| The parser's limits, `test_evidence_search_passage_query.py` | The new API with every limit off: no prefix minimum, no word cap, no one-character rule, an empty `PASSAGE_STOP_WORDS` | **19 failed, 40 passed**: every short-prefix, word-cap, stop-word and one-character test, and the short-prefix property (`assert 1 >= 3`) |
| Passage minimum, `test_evidence_search_passage.py -k passage` | The reader binding a minimum of 0 | **8 failed, 30 passed** |

In an earlier red run the short-prefix property happened to pass. That showed it rarely generated a
short prefix, so it got [boundary pieces](#hypothesis-statistics) before it was counted as evidence.

### Mutation runs

Twenty mutants, each run against only its covering test files with `-x`, and each with a new, empty
`HYPOTHESIS_STORAGE_DIRECTORY` (agreement 8). Every file was committed first and restored with
`git checkout`, and the worktree was checked clean after each batch. **20 of 20 caught**, none by an
error before running.

| # | Mutant | Caught by (first failure) | Time |
|---|---|---|---|
| 1 | `MIN_PREFIX_CHARACTERS` 3 → 2 | `test_search_query_prefix_needs_three_characters_before_its_star` | 1.0 s |
| 2 | `< MIN_PREFIX_CHARACTERS` → `<=` | `test_search_query_prefix_is_an_fts5_prefix_phrase[a-bcd*]` | 0.9 s |
| 3 | The prefix check never refuses | `test_search_query_with_a_shorter_prefix_is_refused_whole[gr*]` | 0.9 s |
| 4 | The prefix counted over the whole term, not its last word | `test_search_query_with_a_shorter_prefix_is_refused_whole[a-bc*]` | 0.8 s |
| 5 | The expression ignores a short prefix | `test_search_query_with_a_shorter_prefix_is_refused_whole[gr*]` | 0.8 s |
| 6 | A trailing `*` read as a literal | `test_search_query_reads_a_trailing_star_as_a_prefix_and_nothing_else[grow*]` | 1.0 s |
| 7 | `MAX_PASSAGE_WORDS` 40 → 41 | `test_search_passage_keeps_forty_content_words_and_says_it_dropped_the_rest` | 1.1 s |
| 8 | The cap's `==` → `>` | the same | 0.9 s |
| 9 | The cap does not say it shortened | the same | 0.9 s |
| 10 | Stop words not left out | `test_search_passage_keeps_its_content_words_in_order_once_each` | 0.9 s |
| 11 | One-character words kept | `test_search_passage_leaves_out_one_character_words_and_contraction_pieces` | 1.4 s |
| 12 | The share rounded down | `test_search_passage_keeps_its_content_words_in_order_once_each` | 1.2 s |
| 13 | Format 1 no longer read | `test_holder_serves_a_format_one_index_and_says_what_it_cannot_do` | 0.9 s |
| 14 | The reader reads any format | `test_search_index_reader_refuses_a_file_that_is_not_this_index` | 3.0 s |
| 15 | The holder reads any pointer format | `test_holder_keeps_serving_when_a_format_it_does_not_read_is_published` | 1.3 s |
| 16 | The holder reads any manifest format | `test_a_manifest_of_an_unknown_format_version_is_refused` | 1.2 s |
| 17 | The holder ignores a file of another format than its manifest | `test_holder_refuses_a_file_of_another_format_than_its_manifest_names` | 1.0 s |
| 18 | The holder ignores a pointer and manifest that disagree on format | `test_holder_refuses_a_pointer_and_manifest_that_name_different_formats[1-2]` | 0.9 s |
| 19 | The service treats format 1 as stemmed | `test_holder_serves_a_format_one_index_and_says_what_it_cannot_do` | 1.1 s |
| 20 | The service runs a passage on format 1 | the same | 1.1 s |

Mutant 1's first failure is the test that pins the constant. The behaviour tests that would also
catch it (`...refused_whole[gr*]`, `[ab**]`) are the ones the red run showed failing with no
check at all.

### Hypothesis statistics

Each was run with `--hypothesis-show-statistics` and a fresh database, over 400 examples:

* `test_search_query_prefix_never_shorter_than_three_reaches_fts5`: 59.50% a prefix under three
  characters (refused), 8.92% a prefix of three or more (searched, and its last word checked),
  23.11% no prefix.
* `test_search_passage_expression_is_only_strings_joined_by_or`: 64.76% 1 to 9 content words,
  26.77% none; ten or more is rare, so the 40-word cap rests on its example tests.

### Existing tests that changed (ac2)

Each changed because a prefix, the format or the port is the point. No expectation about which cards
a search finds, their order or their count changed.

| Test | Change | Why |
|---|---|---|
| `test_evidence_search_query.py::test_search_query_reads_words_phrases_exclusions_and_two_prefixes_only`, the row `grow* AND bad OR` | `QueryTerm("grow*")` → `QueryTerm("grow", prefix=True)` | A trailing `*` is now a prefix |
| `test_evidence_search_query.py::test_search_query_prefix_names_the_only_column_a_term_searches` | A query with no expression may also be a refused short prefix | `0*` is refused whole |
| `test_evidence_search_query.py::test_search_query_lets_no_typed_operator_through` | The allowed shape lets ` *` follow a string | The parser writes FTS5's prefix star |
| `test_search_index_sqlite_features.py`, `ALLOWED_STATEMENTS` and `ALLOWED_FTS5_OPTIONS` | `tokenize='porter unicode61 remove_diacritics 2'` | Format 2's tokenizer: stemming is the point |
| `test_search_index_reader_sqlite_features.py::test_search_index_reader_refuses_a_file_that_is_not_this_index` | `user_version = 2` → `3`, and the message `this build reads 1 and 2` | 2 is now readable |
| `test_search_index_holder.py`, the two unknown-format tests | Format 2 → 3 | The same |
| `test_search_index_publish.py::test_search_index_publish_refuses_another_fingerprint_or_format_version` | Edited format 2 → 1 | This build writes 2, so it must refuse to publish an old format 1 index |
| The two reader fakes in `test_evidence_search.py` and `test_evidence_search_result_count.py` | `format_version = SEARCH_INDEX_FORMAT_VERSION` added | The reader port gained `format_version` |

Added to existing files, not changed: the passage statements, queries and plan test in the reader's
SQLite test; a passage search in its property; the operator timings in
`test_evidence_search_scale.py`; and a keyboard journey in the Chromium suite.

## The trigram measurement (ac3)

Taken 2026-10-23 on the operator's Mac. Counts and sizes only, and every file went to the session's
scratch directory, none under `~/.debate-research/<env>/tub-index/`. The dev index was read
read-only.

**How.** `env DEBATE_ENV=dev debate-research tub index build --caselist hspf26 --caselist openev --out <scratch>`
built 16,759 documents (11,000 and 5,759) in **80.15 s** (790 MB resident), before any code changed.
Each variant was made from a copy of that file: drop `search`, create it with the variant's
tokenizer, then `rebuild`, `optimize`, `VACUUM` and gzip level 6, as the writer finishes. Made
that way with format 1's own tokenizer, the copy came back at exactly the build's 243,744,768 bytes
(gzip within 9 bytes), so the method adds nothing. The trigram variant adds a second
external-content FTS5 table, `tokenize='trigram'`, over the same four columns. Format 2 was also
made from a copy of the whole dev index, `f29b81c276dd67c5`, in 34 s, so it needs no
extrapolation.

| Variant | Documents | SQLite bytes | gzip bytes | Bytes per document (SQLite, gzip) | FTS5 rebuild, optimize, `VACUUM` | gzip |
|---|---|---|---|---|---|---|
| Format 1 as built, sample | 16,759 | 243,744,768 | 91,532,520 | 14,544 and 5,462 | (the build: 80.15 s) | |
| Format 2 (`porter`), sample | 16,759 | 240,345,088 | 89,503,957 | 14,341 and 5,341 | 3.0 s | 7.1 s |
| Format 2 and trigram, sample | 16,759 | 546,205,696 | 309,378,714 | 32,592 and 18,460 | 16.8 s | 22.8 s |
| Format 1, dev index `f29b81c276dd67c5` | 50,434 | 834,973,696 | 311,899,269 | 16,556 and 6,184 | (the PM's 305 s build) | |
| Format 2, made from it | 50,434 | 823,955,456 | 305,559,662 | 16,337 and 6,059 | 11.8 s | 20.9 s |

**Scaling to the dev index.** The dev index holds 3.01 times the sample's documents but 3.30 times
its indexed text (`sum(length(tag, cite, read_aloud, text))`: 349,981,600 against 106,194,483).
Scaled by text, the sample's format 1 to format 2 change predicts 823,769,485 bytes for the whole
format 2 file against 823,955,456 measured, within 0.03%. Scaled by documents, format 1's own size
comes out at 733,517,730, 12% short. So the text scaling is the one to trust. The sample's trigram
table, 305,860,608 bytes (219,874,757 gzipped), scales to about 1,008 MB (725 MB gzipped) on top of
format 2.

| At 50,434 documents | SQLite bytes | gzip bytes | Against 1,700,000,000 SQLite | Against 400,000,000 gzip | Two SQLite copies at a swap, of 4,294,967,296 |
|---|---|---|---|---|---|
| Format 1 today | 834,973,696 | 311,899,269 | 49% | 78% | 1,669,947,392 (38.9%) |
| Format 2, measured | 823,955,456 | 305,559,662 | 48% | 76% | 1,647,910,912 (38.4%) |
| Format 2 and trigram, scaled by text | ~1,831,970,000 | ~1,030,190,000 | **108%, past it** | **258%, past it** | ~3,663,940,000 (85.3%) |
| Format 2 and trigram, scaled by documents | ~1,643,730,000 | ~931,030,000 | 97% | **233%, past it** | ~3,287,470,000 (76.5%) |

**Said plainly:** the trigram variant pushes the gzip object past 400,000,000 bytes by either
scaling, to about 2.3 to 2.6 times the line. That brings forward the promotion list's item 12, the
Lambda bandwidth quota: about 13 s of download at the 625 Mbps cap instead of about 4 s. By text
scaling it also passes the 1,700,000,000-byte SQLite warning. A same-size swap would fill 85% of
`/tmp`, and at 2026-10-22's 11.6% a week a swap would no longer fit within two weekly updates. Format 2 alone is about 1.3%
smaller than format 1 on every count. A full trigram build is not needed to settle this: both
scalings land on the same side of every line that matters.

### Query times on the measurement index

From `test_evidence_search_scale.py`'s operator checks (timings and counts only), run read-only
with `DEBATE_TUB_SEARCH_INDEX` naming each index. The Mac was loaded by other work (load average
about 5 to 7), so these are upper bounds. The format 1 and format 2 plain rows were taken minutes
apart under the same load.

| Index | Queries | Warm p50 | Warm p95 | Warm max |
|---|---|---|---|---|
| Format 1, dev `f29b81c276dd67c5` | The twenty generic plain queries, 60 runs | 15.3 ms | 66.7 ms | 117.1 ms |
| Format 2 measurement copy | The same, 60 runs | 10.9 ms | **67.5 ms** | 157.7 ms (`the`, 50,163 matches) |
| The same | Eleven generic passages, the last at 40 content words, 33 runs | 86.9 ms | **335.0 ms** | 448.3 ms (the 40-word one) |
| The same | Twelve prefixes, down to `pro*` and `con*`, 36 runs | 10.6 ms | **146.8 ms** | 157.0 ms (`con*`) |

Stems widen matches a little: `economy` matched 9,459 documents on format 1 and 10,641 on format 2.
Before the passage statement kept FTS5's own sort, a prototype drove FTS5 one candidate at a time:
1,184 to 1,309 ms for an eight-word passage, against 35 to 38 ms after (both measured on the same
index). That is why `PASSAGE_MATCH_STATEMENT` writes `+d.doc_id IN shared`. A plan test pins it.

### The Lambda image's SQLite

The PM asked for the image's SQLite to be checked with the existing statement-shape test. The
image `public.ecr.aws/lambda/python:3.12` (on this Mac, built 7 days ago) was run with
`--pull never --network none`:

* `-m slow` on `test_search_index_reader_sqlite_features.py` and `test_search_index_sqlite_features.py`
  → **2 passed**. The replay runs every traced statement in the image's SQLite **3.40.0**, both
  passage statements included, over a format 2 (`porter`) index, and the rows must equal the local
  run's. The writer's check opens a format 2 file there with `integrity_check`, FTS5's own
  `integrity-check` and a `MATCH`. These replays run on validate-dev too.
* A one-off check in the image: `sqlite 3.40.0`, a `porter` table matching `escalating` against
  `escalated` (1 row), and a `trigram` table matching `scalat` (1 row). So the image has trigram,
  should it ever be adopted.

## Files changed

* `packages/debate_core/src/debate_core/domain/`: `evidence_search.py` has the prefix term, the
  passage parser, the three limits, the stop words and the new notices. `search_index.py` has
  format 2, the readable formats and `STEMMED_FORMAT_VERSION`.
* `packages/debate_core/src/debate_core/application/`: the reader port gained `format_version` and a
  passage's words. `evidence_search.py` gained passage mode, the format 1 behaviour and the configurable
  share. `search_index_holder.py` reads formats 1 and 2 and requires the pointer, manifest and file to agree.
* `packages/debate_core/src/debate_core/integrations/local/`: the writer's `porter` tokenizer, and the
  reader's format check and two passage statements.
* `packages/debate_core/src/debate_core/testing/search_index.py`: `format_one_index`, the format 1
  file of an index's rows, in memory ([Deviations](#deviations-from-the-spec)).
* `packages/debate_api/src/debate_api/`: the *Search by passage* checkbox, its styles and notices,
  the mode through pages and Back to results, and `TUB_PASSAGE_SHARE_PERCENT`.
* Tests: four new files (`test_evidence_search_passage_query.py`, `test_evidence_search_passage.py`,
  `test_search_index_holder_formats.py`, `test_search_pages_passage.py`), plus additions and the
  changes named above.
* `docs/data/search-index.md`: format 2, how a query, prefix and passage are read, the statement
  table naming `COUNT_STATEMENT` and its shared `_FILTERS` (the PM's amendment), and the measurement.
* `docs/runbooks/evidence-search.md`: *Moving the index to format 2* and the rollback rule
  ([Deviations](#deviations-from-the-spec)).
* `plan_specs/.../t13-passage-search.yaml`: the Goal's phase, `Succeeded`.

## Deviations from the spec

1. **`debate_core.testing` is not in `constraints.packages`.** `format_one_index` went into
   `debate_core/testing/search_index.py` beside `published_index`, because the core and API tests
   both need a format 1 file and test modules cannot import each other (importlib mode). It works
   in memory, so the package keeps its no-filesystem promise. The spec's list could add
   `debate_core.testing`.
2. **`docs/runbooks/evidence-search.md` is not in `constraints.packages`.** The PM's context of
   2026-10-23 (item 5) asked for the runbook's publishing and rollback sections, so I edited them.
   The list could add `docs/runbooks`.
3. **The holder checks more than the spec says.** It now requires the pointer, manifest and file to
   agree on a format. With one readable format they agreed by construction; with two, a format 2
   file published as format 1 would otherwise be served with the wrong behaviour. A disagreement is
   refused as `MANIFEST_DISAGREES` or `UNREADABLE_INDEX`, by tests and mutants 17 and 18.

## Decisions and assumptions

* **A short prefix refuses the whole query**, rather than being dropped. Dropping it would search
  for something the student did not ask for. The page says *A word ending in * needs at least 3
  letters before the *, like gro*. Nothing was searched.*, and no `searched` record is written.
* **A prefix's three characters are counted in its last word**, since `a-bc*` reaches FTS5 as the
  phrase `a bc*`. Letters, digits and private-use characters count; a combining mark is part of its
  word but not counted.
* **A prefix works on a format 1 index.** FTS5 prefixes need no stemmer, and the PM's ruling named
  only stems and passages as unavailable.
* **On format 1, every plain results page says words are matched exactly as typed.** That is the
  ruling's "say plainly"; the line goes when the index is format 2.
* **Passages read every operator as punctuation.** `"`, `-`, `*` and `author:` are plain words or
  separators, and the help text says so. A pasted sentence never trips the plain-search syntax.
* **A passage leaves out one-character words** as well as `PASSAGE_STOP_WORDS` (157 words: function
  words, forms of be, have and do, modals, and contraction pieces such as `doesn`). That rule means
  `a`, `I` and a contraction's `s` or `t` need no entry. `won` is kept, because it is a word. Words
  are deduplicated without regard to case; two words with one stem each count toward the minimum.
* **The share is 66 percent, rounded up** (`passage_minimum`): 2 of 3, 4 of 6, 6 of 9, 27 of 40.
  67 would round 3 words up to 3 of 3. The setting is `TUB_PASSAGE_SHARE_PERCENT`, 1 to 100, unset
  in Terraform like the other optional caps.
* **The passage SQL is a fixed shape.** The words go in as one bound string, split by a recursive CTE
  on a separator (`\x1f`) the parser never lets through, so the statement-shape test can list it by
  hand. The ranking keeps FTS5's own sort and filters afterwards (the 35 ms against 1.2 s above).
* **A passage cursor is refused by a plain search, and the reverse**, because the binding now holds
  the mode and the minimum. Cursors from before the deploy are refused once, with the existing *out
  of date* message, as an index swap already does.
* **The control is a checkbox after the search box** and before the filters, off by default. The
  Chromium journey drives it by keyboard at 1366×768, 1280×800 and a phone's 390×844, axe clean.
* **Nothing new is logged.** The holder logs only index ids and refusals. The API test reads every
  app record's message and extras after a passage, a prefix and a short prefix, and finds none of
  their words, `q=` or `passage`.

## Checks run before this report

| Check | Result |
|---|---|
| `uv run scripts/affected_tests.py` | **268 of 414 test files (64.7%) chosen in 5.7 s from 30 changed files**: past two minutes at about six for the whole selection, so not run (agreement 10). It is left to the PR's `ci` |
| Changed test directories and the always-run list, `-n auto -m "not slow and not live"`, under `alarm 118` on `.venv/bin/python -m pytest`: core `domain`, `application`, `integrations/local`; `packages/debate_api/tests`; the CLI's `test_doctor_search_index.py` and `test_tub_index.py`; `tests/architecture`, `tests/specs`, the CLI's `test_app.py` and `test_help_rendering.py`; `tests/docs` and the two docs-script tests | **5568 passed in 100.49s**. The first run caught one failure: two docstrings named SQLite versions the Python-version check reads, `3.9.0` and `3.8.3`. They now name years. Rerun clean |
| The suites asserting on loggers, in one process (`-n 0 -p no:randomly`) after their neighbours | holder, holder suppression, holder formats: 56 passed; search pages, access audit, passage pages: 88 passed |
| Slow tests touched: the image replays and the whole Chromium suite (`-m slow`) | **25 passed** |
| `ruff format --check .`, `ruff check .` | 1139 files already formatted; all checks passed |
| `pyright packages/debate_core packages/debate_api` | 0 errors, 0 warnings |
| `lint-imports`; `scripts/check_thin_handlers.py` | 16 contracts kept, 0 broken; 47 handlers within 25 statements |
| `scripts/check_command_blocks.py`, `scripts/check_links.py`, `scripts/docs_index.py --check-descriptions` | No `#` comments in 361 blocks; 2074 links and anchors OK; 43 documents described |
| `uv run scripts/validate_specs.py` | OK: 428 files, 40 epics, 366 tasks, 22 releases |

`dev` moved on while the task ran (to `a7fed2f`). None of its new commits touches a file this
branch changes.

## Operator follow-ups

After the merge, in this order. The blocks are in the runbook's
[Moving the index to format 2](../runbooks/evidence-search.md#moving-the-index-to-format-2), each a
dry run or comparison first, then the real run (agreement 11). Each refuses to run while a
`caselist pull` runs or a `DEBATE_*` override is set, and each success check needs a count above
zero.

1. **Deploy dev's function**: `scripts/tub_deploy.sh dev --dry-run`, then `scripts/tub_deploy.sh dev`
   (~3 min each). Success: `{"status":"ok"}`, then a signed-in dev search with a count above zero
   and the *matched exactly as typed* line, which shows the new function serving the format 1 index.
2. **Build format 2 and compare it with the published index** (~6 min). This builds every store
   `current.json`'s manifest names and prints both indexes' formats and per-store counts. It stops
   unless the new index is format 2, every store is kept, and the same rows give the same counts.
3. **A plain publish**, `tub index publish --env dev --index .../<INDEX_ID>` with no
   `--allow-shrink` (under a minute). Success: the table ending in `current.json`, and no shrink
   guard line.
4. **Time three searches on dev** from their `REPORT` lines: `nuclear war`; the passage `Nuclear war
   between great powers would cause human extinction`; and `deter*`. Paste the three durations back.
5. **Reinstall the agent with this build before its next Wednesday run**
   ([Reinstalling the agent](../runbooks/caselist-scheduled-sync.md#reinstalling-the-agent)). An agent
   still on the old build rebuilds format 1 and publishes it over format 2. That is safe, because
   the function reads both, but it undoes the move.

In prod, the same order at the promotion: the function first, then the index.

## Follow-up work

* **If substring search is wanted**, a trigram table over `tag` and `cite` alone could be measured.
  By the 2026-10-20 build's breakdown in `docs/data/search-index.md`, those two columns are 19.6 of
  the 321.8 MB of indexed text, about 6%, where `text` is 241.4 MB, about 75%. A follow-up task for
  E39, if the PM wants one.
* **`docs/guides/search-index.md`** says publish refuses "another index format". That is still true
  and needed no edit. A line naming format 2 could go there with the next guide change.
* **The query-time table** in `docs/data/search-index.md` takes the three dev `REPORT` durations from
  follow-up 4 when the operator has them.

## Questions for the PM

````text
v1-e39-t13 (passage search): questions for the PM, 2026-10-23

1. Trigram index: adopt or not?
   Measured on openev + hspf26 (16,759 documents), scaled to dev's 50,434:
   SQLite about 1,832,000,000 bytes (warning line 1,700,000,000), gzip about 1,030,000,000
   (line 400,000,000), two copies at a swap about 3,664,000,000 of /tmp's 4,294,967,296 (85%).
   Scaled by document count instead: 1,644,000,000 / 931,000,000 / 76%. Either way gzip is
   2.3 to 2.6 times the line and brings item 12 (Lambda bandwidth quota) forward.
   Options: (a) do not adopt; (b) adopt over all four columns, and request the quota now;
   (c) a follow-up measures trigram over tag and cite only.
   Recommendation: (a), with (c) only if the coach asks for substring search. Passage
   mode, stems and prefixes cover "find a card that says something", and format 2 is
   smaller than format 1 on every count.

2. Two paths outside constraints.packages: debate_core.testing (format_one_index, the
   format 1 test file, in memory) and docs/runbooks/evidence-search.md (the format 2 order
   and the rollback rule you asked for in item 5).
   Options: (a) amend the spec's packages to add both; (b) record them as deviations only.
   Recommendation: (a), so the spec says where the work went.

3. The holder now also refuses a pointer, manifest and file that disagree on the format
   (MANIFEST_DISAGREES / UNREADABLE_INDEX). With one readable format they could not disagree.
   Options: (a) keep it; (b) remove it as beyond the spec.
   Recommendation: (a). Without it, a format 2 file under a format 1 pointer would serve
   with the wrong notices; it is two lines, with tests and two caught mutants.

4. On a format 1 index every plain results page carries "Until the next weekly update of the
   search, words are matched exactly as typed: grow does not find growing."
   Options: (a) keep it, the ruling's "say plainly"; (b) say it only beside a passage refusal.
   Recommendation: (a). It lasts one week and tells a student why grow missed growing.
````

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
