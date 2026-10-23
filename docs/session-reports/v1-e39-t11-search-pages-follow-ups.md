# Session report: v1-e39-t11-search-pages-follow-ups

| | |
|---|---|
| Task | `v1-e39-t11-search-pages-follow-ups` — Search pages: a result count, a way back to the results, a link to the disclosed file, and Copy card without the provenance line |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t11-search-pages-follow-ups.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t11-search-pages-follow-ups.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t11-search-pages-follow-ups` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

All four of the coach's follow-ups are built and tested.

1. **Result count.** The results page shows how many cards matched, above the results. The reader
   counts with the same expression, filters and suppression list as the results, in the same lease.
   The count is exact up to a cap (1,000 by default, `TUB_RESULT_COUNT_CAP`) and reads
   `1,000+ cards matched.` past it.
2. **Back to results.** Each result links to its card with the search's words, filters and cursor.
   The card page validates them with t03's form, filters and cursor binding, and builds the link
   from the validated values. A tampered, stale or missing search gives "New search", which goes to
   `/search`.
3. **Open on openCaselist.** A disclosed card links to its team's page, in a new tab with
   `rel="noopener noreferrer"`. The link is built only when the stored school and team code are in
   the address's one-word form.
4. **Copy card.** It now copies the tag, the cite and the text, with no provenance line
   (policy 1.11).

**ac3 is amended by the PM's ruling of 2026-10-22 (option A).** As first written, ac3 also asked
for "a camp card to its OpenEv file". The index stores no OpenEv path or id, and neither does the
parsed store's `CampFile`, so I stopped and asked, as the brief said to. The ruling: a camp card
shows no link until the index stores an OpenEv address, and `v1-e39-t16` carries that address from
the import into the index, after `v1-e39-t13`'s format move. Every criterion passes as amended, and
the Goal is `Succeeded`. Look first at two things: the link-out rule
([`search_source_links.py`](../../packages/debate_core/src/debate_core/domain/search_source_links.py)),
and the count's budget handling in `EvidenceSearchService._count`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `pages` — Search page follow-ups | Done (ac3 as amended) | Red run first (commit `bbcf9e1`), then the behaviour (`16241b3`), the Chromium tests (`9f1a6de`), and the measurement (`ab3eb16`) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — a count for the query and filters, exact up to a cap and marked approximate above it; p95 on the measurement index within t03's budget with the count, by test and a recorded figure | PASS | Tests: `test_evidence_search_result_count.py` (exact per filter, the parsed query, the cap at 1/20/44/45/46, suppression, count equal to every result paged through, the budget), and `test_search_pages_follow_ups.py` (shown above the results on both pages, per filter, `10+` with a cap of 10, `1,000+`/`1,234` wording, none for no match). **Figure:** `.venv/bin/python -m pytest -n0 -s -q -m slow packages/debate_core/tests/application/test_evidence_search_scale.py -k synthetic` → `1 passed in 32.52s`. On 250,000 synthetic documents, warm p95 is **198.2 ms** counting to 1,000 and 194.3 ms counting to 1 in the same run. The budget is 2 s. See [Measurements](#measurements) |
| **ac2** — the card page links back with the same query, filters and page from validated parameters; tampered or stale lands on a fresh search page, by tests shown failing first | PASS | Red against the skeleton (the back link echoed the raw query string; `check_cursor` accepted everything; result links carried no search). 36 of these test cases failed (24 back-link, 12 cursor-check), among them all 15 tampered or missing cases, the stale cursors from another search and from a replaced index, and two of the six "outside the pilot" cases; see [Red run](#red-run). Green: `.venv/bin/python -m pytest packages/debate_api/tests` → `645 passed in 8.42s`. Mutants: 14 of 14 caught |
| **ac3**, as amended by the PM's ruling of 2026-10-22 (option A) — a disclosed card links to its file's page on openCaselist, in a new tab with no referrer; a camp card shows no link until the index stores an OpenEv address; a card whose link cannot be built shows none, by test | **PASS as amended** (as first written, "a camp card to its OpenEv file": FAIL, see Deviation 1) | Disclosed: `test_search_source_links.py` (31 cases) and `test_search_pages_follow_ups.py` (the link, `target="_blank" rel="noopener noreferrer"`, below the line; none for `Maple Grove`, whose space marks a display name; none for a camp card; no audit record). Chromium: `test_the_link_out_to_opencaselist_opens_a_new_tab_with_no_opener_or_referrer` at all three sizes. **Camp, as amended:** `test_a_camp_card_has_no_link_because_the_index_stores_no_openev_file_address` and `test_a_camp_card_shows_no_link_because_the_index_has_no_openev_address` (no link, no "Open on" on the page). Whether the openCaselist address is right on real data is the coach's post-deploy check, an operator follow-up, not this criterion |
| **ac4** — Copy card's HTML and text hold the tag, cite and text and no provenance line; the card page still shows the line; the copy writes the same audit record, by tests shown failing first | PASS | Red: 11 Copy card test cases failed against the old copy, because the line was still there (5 amended tests, and 6 cases of the new one). Green: `test_copy_card.py`, including `test_no_copy_holds_any_of_its_cards_provenance_lines_or_names` over six cards. The page still shows the line: t06's `test_the_card_page_shows_the_label_tag_cite_line_counts_copy_card_and_every_occurrence`, unchanged and passing. Audit record: `test_the_copy_writes_the_same_card_copied_record_as_before_policy_1_11` passed red **and** green, as it should, because the record did not change. Its proof is the "no audit record" mutant, which it caught. Chromium paste tests: 3 paragraphs, no line. Mutants: 8 of 8 caught |
| Node criterion — `uv run pytest packages/debate_api/tests` | PASS | `.venv/bin/python -m pytest packages/debate_api/tests` → `645 passed in 8.42s` (the alarm goes on the interpreter, per agreement 10) |

## Red run

Before the behaviour, the skeleton had every new name and signature but did nothing:

- the service counted nothing (`count=None`);
- `check_cursor` accepted every cursor;
- `source_link` returned `None`;
- the card page's way back was `"/search?" + str(request.query_params)`;
- result links carried no search;
- the configuration ignored `TUB_RESULT_COUNT_CAP`;
- Copy card still wrote the line.

`.venv/bin/python -m pytest -q -p no:randomly -n 4` over the six new and amended files →
**98 failed, 71 passed in 6.78s** (committed as `bbcf9e1`). Grouped by their `E` lines:

| What failed | Count | `E` line |
|---|---|---|
| The count, in core | 24 | `assert {None} == {ResultCount(...)}`, `assert None == ResultCount(matches=45, ...)` |
| The count, on the page, and the cap setting | 19 | `assert None == '25 cards matched.'`; `DID NOT RAISE ConfigurationMissing`; `where 1000 = PilotConfiguration(...)` |
| The back link and result links | 24 | `assert ('/search?q=z...k to results') == ('/search', 'New search')`, the outside-pointing and ordering cases |
| The cursor check | 12 | `Failed: DID NOT RAISE InvalidSearchCursor` |
| The link out | 6 | `where None = source_link(...)`; no `<p class="source-link">` |
| Copy card | 11 | `'[Disclosed: hsld26...vitational Round 4]' is contained here`; `too many values to unpack (expected 3)` |
| The reader's statement list | 1 | `every allowed statement was exercised`: the count statement is listed but the skeleton never sent it |
| The test's own fault (below) | 1 | `CountBatch(..., exhausted=True, interrupted=False).interrupted` |

**One failure was the test's fault, not a red.** `test_the_reader_count_stopped_by_the_budget...`
ran on the real reader against 45 rows. Those finish inside one progress-handler interval, so the
budget could never stop the statement. The test now builds 400 documents.

**Already passing at red, and why:**

- **Negatives the skeleton could not get wrong:** the 21 "no link" cases, the camp card's
  `source_link`, "no count for no match", "no count with nothing to search for", a stopped count
  being left out, and a cap outside its range being refused (the constructor's range check was
  real).
- **Unchanged behaviour:** 18 Copy card cases (the style table, the spans and the route), the
  copy's audit record, the reader's six other tests (its plans, read-only open, refusals, budget
  stop and the syntax-error property), and the reader's doc-id order test (the reader's `count` was
  real plumbing).
- **Four "outside the pilot" cases.** When a request holds only `q`, re-encoding the raw query string
  gives the same address as rebuilding it from the validated value. The mutants below prove these
  cases do something: "the raw query string echoed" is caught by the two cases with extra
  parameters.
- **A test of unchanged behaviour by design:** "the searched audit record still counts the first
  page".

## Mutants

All 24 runs below used a fresh `HYPOTHESIS_STORAGE_DIRECTORY` (agreement 8). None of the tests run
uses Hypothesis. Each runs its covering tests with `-x -n 0`, restores the file and compares its
bytes. Script:
`/private/tmp/claude-501/-Users-charlesclark-Documents-debate-debate-intelligence-tool-debate-intelligence-worktrees-v1-e39-t11-search-pages-follow-ups/fb787fbe-3421-45d3-a809-cbb1c07fcb54/scratchpad/mutants.py`.

**Back-link validation: 14 of 14 caught.**

- no word check;
- cursor never checked;
- a refused cursor still linked;
- the cursor checked without the filters;
- a refused form still linked (raw echo);
- the raw query string echoed;
- the page dropped;
- the fresh search at `/`;
- "Back to results" offered with no search;
- result links with no search;
- result links with no page;
- `check_cursor` ignoring the filters;
- `check_cursor` bound to no index;
- `check_cursor` accepting everything.

**Copy card's content: 8 of 8 caught.**

- the line back below the cite;
- the line back in the plain text;
- the line at the end of the HTML;
- no cite paragraph;
- no tag in the text;
- the read-aloud text in place of the text;
- the short cite in place of the cite;
- no `card-copied` record.

**The extended Chromium journey: 2 of 2 caught.**

- "the page dropped": the journey's `wait_for_url` back to page 2 timed out, in 32.8 s.
- "the line back below the cite": caught by
  `assert ('[Disclosed:...nal Round 4]' not in '<p style="f....</span></p>'`, that is, on the
  clipboard's HTML, which is its reason.

## Measurements

**The synthetic index, 250,000 documents (t03's ac5 index),** with the operator's Mac at load ~5.
The run times each query with the count capped at 1, which reads two rows, as the nearest thing to
no count.

| | p50 | p95 | max |
|---|---|---|---|
| Warm, 60 searches, counting to 1,000 | 45.9 ms | **198.2 ms** | 250.2 ms |
| Cold first pass, counting to 1,000 | 45.9 ms | 197.6 ms | 248.0 ms |
| Warm, 60 searches, counting to 1 | 40.8 ms | 194.3 ms | 247.9 ms |

- The counts shown: `1000+` for 17 queries, and exactly `334`, `509` and `90` for the three
  narrowest.
- t03's own figure on this index was p95 340.8 ms, measured at load 16. The two runs are not
  comparable, which is why the cap-1 column is measured in the same run.

**The count's worst cases (ad hoc, same index):**

| Query | Count | Warm median, cap 1,000 | Cap 1 |
|---|---|---|---|
| The commonest word with a filter that keeps 1 match in 84 | 1,000+ | 216 ms | 193 ms |
| The commonest word in a caselist no document is in | 0 | 524 ms | 527 ms |

In the second case the ranked search and the count both scan every match. Both cases stay within
the 2 s budget, and a count the budget stops is shown as no count.

**The dev index on this Mac** (`767b9c7c056b80cb`, 52,059 documents, read-only; t03's
`operators_index` test, which prints timings and counts only):

- warm p95: **19.7 ms**, then 18.8 ms on a second run;
- cold first pass: p95 299.1 ms on the first run, 18.7 ms on the second. The first run read an
  839 MB file that was not in the page cache.

## Before the report: what was run

- **Affected set.** `uv run scripts/affected_tests.py` → `62 of 400 test files (15.5%) chosen in
  4.9 s from 27 changed files`. I ran that list with CI's markers under the interpreter's alarm:
  `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -n auto -q -m "not slow and not live" <the 62 files>`
  → **2721 passed in 41.99s**.
- **Browser.** `.venv/bin/python -m pytest -q -m slow -p no:randomly packages/debate_api/tests/browser`
  → **17 passed in 9.90s**. The first run had 1 failure, the Copy card status on a second line,
  because my longer help text wrapped; the help text is now "Keeps its formatting.".
- **The Lambda image's SQLite 3.40.0.** `-m slow ... test_search_index_reader_sqlite_features.py -k lambda_image`
  → `1 passed`. The count statement is replayed with the others and gives the same rows.
- **Lint and types.** `ruff format --check .` → `1112 files already formatted`.
  `ruff check .` → `All checks passed!`.
  `pyright packages/debate_api packages/debate_core` → `0 errors` over 586 files.
- **Boundaries and specs.** `lint-imports` → `15 kept, 0 broken`.
  `scripts/check_thin_handlers.py` → `OK: 46 ... handlers within 25 statements`.
  `scripts/validate_specs.py` → `OK: 420 files, 40 epics, 358 tasks, 22 releases`.
- **dev moved** while I worked (#408 to #411). None of its new commits touches a file this branch
  changes.

## Files changed

- **`debate_core.domain`.**
  - `evidence_search.py`: `ResultCount`, `DEFAULT_RESULT_COUNT_CAP` and `SearchPage.count`.
  - New `search_source_links.py`: `source_link` and its rule.
- **`debate_core.application`.**
  - The reader port gains `CountRequest`, `CountBatch` and `count()`.
  - `EvidenceSearchService` gains the count (`count_cap`, under the search's budget) and
    `check_cursor`.
  - `ScreenedSearch.check_cursor` passes the check through, so the back link is checked in the
    lease, as the PM asked.
- **`debate_core.integrations.local`.** `COUNT_STATEMENT` shares `_FILTERS` with `MATCH_STATEMENT`,
  so the two cannot filter differently. Both run through one budgeted runner. `MATCH_STATEMENT`'s
  text is unchanged.
- **`debate_api`.**
  - `search_pages.py`: the count words, result links with their search, the validated back link,
    and the link out.
  - `copy_card.py`: no line; the docstring is rewritten for policy 1.11; `PROVENANCE_STYLE` is
    removed.
  - `configuration.py`: optional `TUB_RESULT_COUNT_CAP`.
  - `container.py`: wires the cap.
  - The two templates and `app.css`.
- **Tests.**
  - New: `test_evidence_search_result_count.py`, `test_evidence_search_cursor_check.py`,
    `test_search_source_links.py` and `test_search_pages_follow_ups.py`.
  - `conftest.py`: card 26, "linked", with school `Cedarbrook` and team `LM`, both synthetic and in
    URL form, holding no `zephyr`; and a `count_cap` option on `PilotWorld`.
  - Amended with reasons citing policy 1.11 or this task: `test_copy_card.py`, the Chromium paste
    tests, and `test_search_pages.py` (`results_of` drops the link's search; the other-origin
    check admits exactly the openCaselist link, which only the linked card's page has).
  - Also amended: `test_suppression_in_pages.py` (`results()` likewise), the reader's
    hand-written statement shapes plus a plan test, the fake reader in `test_evidence_search.py`
    (`count`), and the scale test, which reports the count.

## Deviations from the spec

1. **ac3's camp half is not met: "Open on OpenEv" cannot be built from what the index stores.**
   - What is stored: the index keeps a camp occurrence's camp, year, event and file title. The title
     is the importer's, with the camp, year and lab initials taken off the file name.
   - What is missing: the index keeps no OpenEv path or id, and neither does the parsed store's
     `CampFile` (`domain/caselist/entities.py`). `openev_id` exists only in the sync's run records
     and inbox names.
   - The PM's brief: "If a correct link needs a new stored column, stop and ask before changing the
     index format."
   - So camp cards show no link, which the brief also allows: "where a link can't be built, show
     none".
   - **Resolved by the PM's ruling of 2026-10-22, option A:** "a camp card shows no OpenEv link until
     the index stores an OpenEv address; v1-e39-t16 carries it from the import through CampFile
     into the index, after v1-e39-t13's format move." I amended ac3 in the spec as instructed, with
     that comment above the item; the parsed criterion was printed to check that the comment is
     not part of its text. The criterion is FAIL as first written, PASS as amended.
2. **"Links to its file's page on openCaselist" is the team's page.** As the PM's brief has it,
   "Open on openCaselist" goes to the disclosing team's page. openCaselist gives no file its own
   page; the team page lists each round with its file.

## Decisions and assumptions

- **Count wording** (accepted by the PM, 2026-10-22). `25 cards matched.` and `1 card matched.`;
  past the cap, `1,000+ cards matched.` with a thousands separator. I used "1,000+" rather than
  "About 1,000" because there is no estimate, only a floor. No line is shown when nothing matched (the page
  already says "No cards matched."). No line is shown when the budget stopped the search or the
  count: a part-count is never shown.
- **The count shares the search's budget.** It is checked before each batch and inside SQLite. A
  search that came back partial is not counted.
- **The cap.** It must be a whole number from 1 to `MAX_CURSOR_OFFSET` (100,000), so a count can
  never claim more pages than a cursor reaches. Unset means 1,000. Terraform does not set it, so
  no infrastructure change was needed.
- **Every page shows the count.** Page 2 shows the same total as page 1. The `searched` audit
  record is unchanged: the first page's results, 20, not 25 (tested).
- **Words of the back link** (accepted by the PM, 2026-10-22). "Back to results" when the search validates; otherwise "New search",
  linking to `/search`. A link that says "Back to results" and lands on an empty page would
  mislead. Both sit in a `<nav class="back-link">` above the card. Nothing rewrites history, so the
  browser's back button is untouched.
- **What counts as tampered.** Whatever the search page refuses: a filter outside its choices, a
  bad date, an over-long or foreign cursor, a cursor from another query, other filters or another
  index (a replaced index is tested by publishing one), or no words. Unknown parameters (`next=`,
  `return_to=`) are ignored. The link is always `/search?` plus `SearchForm.page_link`'s encoding.
- **The link out.**
  - The rule: caselist, school and team code must each be in the address's one-word form, matched
    whole with `fullmatch`, so a trailing newline fails too. `UNKNOWN`, a missing disclosure and no
    provenance give no link.
  - Measured on the dev index (counts only, nothing printed): 513 distinct schools, 0 with a space,
    9 with a hyphen and no other non-alphanumeric character; every team code is letters and digits
    (3 to 7 characters); 8 occurrences have the team `UNKNOWN`.
  - That supports reading the archive's directories as openCaselist's URL names, but it is not
    proof. I did not call openCaselist (live network goes to the operator). The coach's post-deploy
    check is what proves it.
  - The link is for the representative, the line shown below the cite. It is not repeated on every
    occurrence in "Where it was disclosed"; I kept to the brief.
- **The card URL now holds the query,** as the search URL already did. The edge keeps no log
  (`distribution.tf`, no `logging_config`), the image's access log is off, and every test of logs
  and audit records passes, the extended journey's among them.
- **Copy card's help text** changed from "Keeps its formatting and source line." to "Keeps its
  formatting." (accepted by the PM, 2026-10-22).
- **A pre-existing behaviour, left alone:** a cursor's binding keeps the query's case, so `WOMBAT`
  and `wombat` bind differently. The search and the check refuse it alike (tested).

## PM questions

One question was asked: ac3's camp half, "Open on OpenEv". The options were these:

- **A.** Amend ac3, and carry the OpenEv address into the index later.
- **B.** Link a camp card to OpenEv's listing for its year.
- **C.** Add the column in this task.

I recommended A.

**PM ruling, 2026-10-22: A.** The ruling's words: "a camp card shows no OpenEv link until the index
stores an OpenEv address; v1-e39-t16 carries it from the import through CampFile into the index,
after v1-e39-t13's format move." The disclosed-card link stands as built. The three wordings were
all accepted: the count's, "New search", and the help text. The ruling is applied in the spec's
ac3, in the acceptance criteria table, in Deviation 1, and in `search_source_links.py`'s docstring.

## Operator follow-ups

**After the merge into `dev`: deploy to dev.** The deploy publishes an image and points the
function at it, so it is two blocks (working agreement 11).

**Block 1, the dry run** (expected runtime ~3 min: it builds the image). It makes no AWS call. It
makes a throwaway worktree at `origin/dev` and syncs it.

Where: this task's worktree (the commands move to the new one).

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e39-t11-search-pages-follow-ups
git fetch origin dev
git worktree add --detach ../dev-deploy-v1-e39-t11 origin/dev
cd ../dev-deploy-v1-e39-t11
uv sync --all-packages
git log --oneline -1
scripts/tub_deploy.sh dev --dry-run
```

What to read before going on:

- `git log` names this task's merge commit, `v1-e39-t11-search-pages-follow-ups: ...`;
- the dry run ends after the build with no push.

If `git log` shows an older commit, the merge has not reached `origin/dev`: stop. If the build
fails: stop and paste it back.

**Block 2, the deploy** (expected runtime ~3 min). It refuses a window with a leftover `DEBATE_*`
override, or a running `caselist pull`.

Where: a new terminal window.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/dev-deploy-v1-e39-t11
OVERRIDES=$(env | grep -c '^DEBATE_')
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
echo "DEBATE_ overrides set: ${OVERRIDES}"
echo "running pull: ${PULL:-none}"
if [[ "$OVERRIDES" != "0" || -n "$PULL" ]]; then
  echo "STOP: open a new window with no DEBATE_ variable set, or wait for the pull to finish."
else
  aws sso login --profile debate-dev-tub-deployer
  scripts/tub_deploy.sh dev
fi
```

Success looks like this at the end:

```text
{"status":"ok"}
Deployed <sha> to dev
```

`<sha>` is the commit `git log` showed in Block 1. Then remove the throwaway worktree:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e39-t11-search-pages-follow-ups
git worktree remove ../dev-deploy-v1-e39-t11
```

**The coach's 2-minute check on dev** (`https://tub.dev.wfbdebate.com/`, signed in):

1. Search for a common word. A line such as `1,000+ cards matched.` or `37 cards matched.` shows
   above the results, and the same number on the next page.
2. Go to page 2 and open a card. "Back to results" returns to the same page 2, with the same results
   and filters.
3. On a disclosed card, "Open on openCaselist (opens in a new tab)" opens that team's page on
   openCaselist. **This is the check that proves the stored school is the address's form.** If it
   lands on a "not found" page, tell the session: the link rule then needs the school's URL name,
   which is a new column.
4. Copy card, then paste into Google Docs. The paste holds the tag, the cite and the card's text,
   and no `[Disclosed: ...]` line. The card page itself still shows the line under the cite.

Record yes or no for each, with the date.

## Follow-up work

- **"Open on OpenEv"** is `v1-e39-t16`'s, by the PM's ruling. That task carries the OpenEv address
  from the import through `CampFile` into the index, after `v1-e39-t13`'s format move. Once it is
  stored, `source_link` gains the camp case.
- **`docs/data/search-index.md`'s "How the index is read"** could name the count statement and this
  report's figures. `docs/data` is not in this task's packages, so I left it.
- **Dev smoke checks** for the pilot belong to `v1-e39-t10`. This task adds no `tests/smoke` check.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-22

**Notes:**

Accepted with no conditions. Open the pull request with no `--partial`.

**What the PM checked.**
* The branch is clean, 7 commits on origin/dev at `9949efb`, and the diff is the 27 files listed.
* ac3 carries the ruling's comment above the item.
* dev has since gained v1-e34-t28 (#409) and v1-e07-t08 (#411). Neither touches a file this
  branch changes, and the pull request's `ci` runs on the merge, so no sync is required.

**What is good.**
* **The count can never disagree with the results.** It shares `_FILTERS` with `MATCH_STATEMENT`,
  runs in the same lease and under the same budget, and never shows a part-count. Your measurement
  includes a cap-1 column in the same run, so the count's own cost is visible, and the worst case
  (524 ms) stays inside the 2-second budget.
* **The back link is rebuilt from validated values only.** Tampered, stale, foreign-index and
  outside-pointing cases are all red first, and all 14 mutants are caught. "New search" rather than
  a misleading "Back to results" is the right call.
* **The link-out rule is honest about what it knows.** A `fullmatch` on the address's one-word
  form, and counts measured on the dev index (513 schools, 0 with a space). You say it is not proof
  and hand the proof to the coach's check.
* **Stopping on the camp half** rather than widening into the importer was exactly the brief.

**Rulings.**

1. **Deviations 1 and 2 are accepted.** ac3 is amended by ruling A, and the team page is the
   file's page, since openCaselist gives no file a page of its own.
2. **Decisions are accepted:**
   * the cap's range;
   * every page showing the total;
   * the unchanged `searched` record;
   * the card URL holding the query, with no edge log, no access log, and the log tests green;
   * the link on the representative only.
3. **Follow-ups.**
   * "Open on OpenEv" is v1-e39-t16's.
   * The `docs/data/search-index.md` note on the count statement goes to v1-e39-t13, which rewrites
     that document for format 2. The PM adds it to that task's brief.
   * Dev smoke checks stay v1-e39-t10's.

**Operator follow-ups: accepted as written.**
* The deploy is two blocks, with the ambient-override and running-pull guard. That is working
  agreement 11, followed.
* The coach's four-point check carries one stop: if "Open on openCaselist" lands on a not-found
  page, the school's URL name needs its own column. That comes back to the PM, not to a new branch.
