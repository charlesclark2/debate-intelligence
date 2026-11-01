# Session report: v1-e39-t28-openev-link-goes-to-the-camps-page

| | |
|---|---|
| Task | `v1-e39-t28-openev-link-goes-to-the-camps-page` — A camp card links to its camp's page on OpenEv, the address the operator confirmed |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t28-openev-link-goes-to-the-camps-page.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t28-openev-link-goes-to-the-camps-page.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t28-openev-link-goes-to-the-camps-page` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

A camp card's page now links to its camp's page on OpenEv, `https://opencaselist.com/openev/<year>/<word>`,
labelled *Find on OpenEv: <camp> <year> camp page*, in a new tab with no opener and no referrer. The
count came first (ac1). It showed the stored camp is the alias table's canonical name, not OpenEv's
word, so the session stopped and asked. The PM ruled the same evening, and the ruling is written into
the spec as a dated amendment. `camp_aliases.yaml` gains an `openev` section, a canonical camp to
OpenEv's word, filled only with words the operator confirmed. The link maps the stored camp through
it and takes the year, from 2013 to the current season plus one. The season rule moved into
`debate_core.domain.season`, and the backfile command imports it unchanged. **With the table as
committed (UTNIF alone), 2 of the 102 camp files with cards link.** The id-based address is gone,
and the format and the stored OpenEv id are unchanged. The tests were shown failing first (30, all at
assertions) and 18 mutants were caught. ac3, the coach's check on dev after the merge, is the
operator's, so the Goal stays `InProgress`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `openev-link-goes-to-the-camps-page` (Camp page link) | DONE | After the PM's ruling. Its criterion passes |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1, "Counts first: the distinct camp values, how many are one address word, and how many of the 102 camp files with cards get a link, recorded in the report with no camp named beyond the three confirmed" | PASS | [The count](#the-count-first). 15 distinct values, 12 one word besides `UNKNOWN`, 98 linkable under the first rule. Under the amended rule, with the committed table, **2 of 102** ([the link count](#how-many-link)). The PM's ruling: "ac1 stands as done" |
| ac2, "A camp card whose stored camp has an OpenEv word in `camp_aliases.yaml` and whose year is in OpenEv's archive links to `https://opencaselist.com/openev/<year>/<word>` … in a new tab with no opener and no referrer, with a label that says it opens the camp's page; any other camp card has none; the id-based address is gone; a disclosed card is unchanged; by tests shown failing first" | PASS | [Red](#red-first): 30 failed at assertions against a refuse-everything skeleton. Green: 246 passed. [Mutants](#mutants): 18 of 18 caught. `git grep -E "OPENEV_FILE_URL\|openev_file_url"` over `packages` finds nothing |
| ac3, "After dev's function is deployed with this task, the coach opens one camp card's link on dev and it lands on that camp's page, which lists the card's file (operator, recorded by the PM)" | NOT RUN | It needs this branch merged and dev's function deployed: [operator follow-up 1](#operator-follow-ups) |
| Node criterion "Camp page link tests pass" (`uv run pytest packages/debate_core/tests/domain -k source_link`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/domain -k source_link -q`: see [What was run](#what-was-run-before-this-report) |

## The count first

Taken 2026-10-31 on the operator's Mac, read-only (SQLite opened `mode=ro`), counts only. No camp
beyond the three confirmed, no title, no lab and no path was printed. Sources: the caselist database's
`caselist_camp_files`, the parsed store `parsed/openev/2026.10.20-docx-6/` (`index.jsonl`,
`occurrences.jsonl`), the release manifests `objects/manifests/openev/`, the four local indexes under
`tub-index/`, and the sync's run records. The published dev index is in the bucket and was not read,
because the local count answers the question.

| Question | Count |
|---|---|
| Camp files in the store | 104 (`caselist_camp_files`): 102 `2026-policy` and 2 `2026-ld`. All are year 2026 |
| Camp files with cards | 102, all `2026-policy`. Each has one `caselist_camp_files` row, and its occurrence rows carry one camp |
| Distinct stored camp values | **15**, the same in `caselist_camp_files`, in the parsed occurrence rows and in all four local indexes (three are format 1 and one is format 2, `camp_year` 2026 throughout) |
| Of those, one address word (letters and digits) | **12**, plus `UNKNOWN`, which is one word too but is the parser's "could not read" ([Decisions](#decisions-and-assumptions)). The other 2 values contain a space |
| Of the 102 with cards, linkable under the spec's rule as written (one word, not `UNKNOWN`, year from 2013 to 2026) | **98**. Of the other 4, 3 have a camp with a space and 1 is `UNKNOWN`. None is refused for its year |
| Years | 2026 only, so every file is inside OpenEv's archive (2013 to the current season, 2026) |
| **Is the stored camp the address's word?** | **No, not in general.** 14 of the 15 values are canonical names from `camp_aliases.yaml`, and the 15th is `UNKNOWN`. The importer records the canonical name, not the spelling the file used: for 9 of the 102 files, the stored camp is not a word of the file's own path |
| The three confirmed words | **UTNIF** is a stored value, with 2 files, and both paths name it. **HDC** and **UM7** are not stored values, and neither is a word of any of the 106 `2026-policy` manifest paths. The alias table spells neither one, so no file can be stored under either |
| Anything holding OpenEv's own folder word | Nothing for these files. The hand import's paths are `<folder>/<file>` (105 of 106 rows, all one folder, which is no camp's spelling and none of the three words) or a bare file name (1), so no path has a `<camp>` folder. The sync's run records keep `openev_id`, `year`, `event` and the inbox name of 7,972 listing decisions, but not the listing's `camp`. `OpenEvFile.camp`, the API listing's own camp field, is seen by the pull and stored nowhere |

**What this means for the link.** The address `https://opencaselist.com/openev/<year>/<camp>` takes
OpenEv's folder word. The store holds the word this repository's alias table chose. The two agree for
UTNIF, where the canonical name is also the confirmed word. For the other 11 one-word camps, which
hold 96 of the 98 linkable files, nothing the repository holds says whether they agree. And the two
confirmed camps that are not UTNIF cannot be reached by any stored value. The alias table also folds
several spellings into one canonical name, which OpenEv may file as more than one camp. A link built
from the stored value would be right for 2 files and unconfirmed for 96.

## The PM's ruling, and the amendment

The count's question went to the PM (option (a), the twelve addresses opened by the operator, then
(b), a word per camp in the alias table). Ruling, 2026-10-31: (b), filled by (a). Each canonical camp
gets an optional OpenEv word, and only words the operator confirms are filled. `UNKNOWN` never links.
The archive runs to the current season plus one, with the season rule moved into the domain and
`debate_cli` added to the packages. No format change. Written into the spec's description as a
dated "(PM amendment 2026-10-31, from the count.)" paragraph, with ac2's wording and the packages,
in `015f887`. `validate_specs.py` passed, and the parsed description was printed to check the
paragraph is text.

## The link

* **Address:** `https://opencaselist.com/openev/<year>/<word>` (`OPENEV_CAMP_PAGE_TEMPLATE`). The word
  is `camp_aliases.yaml`'s `openev` entry for the stored camp. The year is the occurrence's
  `camp_year`. Nothing else is read: not the title, the event, `openev_id` or the request.
* **No link** for:
  * a camp with no word;
  * `UNKNOWN`, whatever the table says;
  * a word that is not one address word (`[A-Za-z0-9]+`, matched whole) or is `UNKNOWN`;
  * a year that is not an integer, or is outside 2013 to `current_season_start(today) + 1`;
  * an occurrence past the provenance limit.
* **Today** is the app's clock, `services.clock().date()`, so tests set it.
* **Label:** *Find on OpenEv: <camp> <year> camp page*, with the stored camp, the name the card's
  provenance line already shows. It says the link opens the camp's page, not the file.
* **Disclosed cards** are unchanged: the camp branch is chosen by the `openev` store alone. The results
  page shows no link.
* **The table** refuses, at load, an `openev` section that is:
  * not a mapping;
  * naming something that is not a camp of the table, or `UNKNOWN` even when listed as a camp;
  * giving a word that is not one address word;
  * giving one word to two camps.

  The refusal stops the importer and the app's start, never a link. Matching never reads the
  section: the same path parses the same with or without it (a test).
* **The stored `openev_id`** is kept, unchanged, for a later per-file link, which would need the file's
  path too. The index format is unchanged, and t16's join still writes the id.

### How many link

Counted by the real rule (`source_link` over each of the 102 camp files with cards, from the Mac's
`caselist_camp_files`, read-only), with the packaged table: **2 of the 102 link, from 1 camp**
(UTNIF). The other 100 have no word yet.

## Red first

The tests were committed with a skeleton (`52ba2b9`) in which the camp link returns `None` and the
table reads no words, with every signature and field in place:

```text
.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -p no:randomly -n 0 -q --tb=line <the six test files>
30 failed, 152 passed in 6.13s
```

Every failure was at its assertion: 16 asserts, and 14 refusals that did not raise. None was an
error or a crash. The 152 that passed are the disclosed-card, season and existing tests, which the
skeleton does not touch. Green after `0b642af`: 246 passed in 3.13s (the same files plus
`test_camp_metadata.py`).

## Mutants

Run by a scratch script that applies one mutant, runs the four covering test files
(`test_search_source_links.py`, `test_camp_openev_words.py`, `test_search_pages_find_on_openev.py`,
`test_search_pages_follow_ups.py`) with `-n 0 -p no:randomly`, and restores the file from `HEAD`.
These tests use no Hypothesis, but each run still set `HYPOTHESIS_STORAGE_DIRECTORY` to a new empty
directory (agreement 8). The tree was clean after both halves.

| Mutant | Caught by | Failed |
|---|---|---|
| 1, the link built from the title | the domain link tests | 14 |
| 1b, the title's first word when it is one | the same | 27 |
| 2, the event in the address | the same | 13 |
| 3a, a word with a space linked (the link's check removed) | `test_a_word_that_is_not_one_address_word_has_no_link` | 6 |
| 3b, a word with a space accepted (the table's check removed) | `test_a_section_that_is_not_camps_to_words_is_refused` | 4 |
| 4a, a year past the season plus one linked | the year test, and the page's clock test | 3 |
| 4b, a year before 2013 linked | the year test (2012) | 1 |
| 4c, the season counted from the machine's date, not the app's clock | the year test, and the page's clock test | 3 |
| 4d, only the current season, not plus one | the year test | 4 |
| 5, the link kept past the provenance limit | `test_a_camp_card_past_the_provenance_limit_has_no_link[its camp still held]` | 1 |
| 6, a referrer sent (`rel="noopener"`) | the page tests' exact markup | 5 |
| 7, a disclosed card given an OpenEv link | `test_a_disclosed_card_never_links_to_openev_whatever_it_holds` | 1 |
| 8, a camp with no table word linked (`get(camp, camp)`) | `test_a_camp_with_no_word_in_the_table_has_no_link` | 3 |
| 9a, UNKNOWN linked (the link's check removed) | `test_unknown_never_links_whatever_the_table_says`, and its page test | 3 |
| 9b, UNKNOWN given a word (the table's check removed) | `test_unknown_gets_no_word_even_when_a_table_lists_it_as_a_camp` | 1 |
| 10, the stored camp used directly, bypassing the table | the domain link tests | 16 |
| 11, the page passes no words | the page tests | 5 |
| 12, two camps given one word (the table's check removed) | the refusal test's shared-word case | 1 |

All 18 failed at assertions (or a refusal not raised), none at collection. 9b was a survivor before
it had a test: the "not a camp of the table" check masked the `UNKNOWN` check, since no test table
listed `UNKNOWN` as a camp. Its test was added in `f8f1706`, before the counted run.

## Files changed

* `packages/debate_core/src/debate_core/domain/`:
  * `search_source_links.py`: the camp-page link, `OPENEV_CAMP_PAGE_TEMPLATE`,
    `OPENEV_ARCHIVE_FIRST_YEAR`, `OPENEV_CAMP_WORD_PATTERN`, `openev_camp_page_url`, and the docstring's
    t16 section rewritten. `OPENEV_FILE_URL_TEMPLATE` and `openev_file_url` are gone.
  * `season.py` (new): the season rule.
  * `evidence_search.py`, `search_index.py`: docstrings on what `openev_id` is still for.
* `packages/debate_core/src/debate_core/application/caselist/`:
  * `camp_metadata.py`: `CampAliases.openev_words` and the section's checks.
  * `camp_aliases.yaml`: the `openev` section, with UTNIF's word and how to add one.
* `packages/debate_api/src/debate_api/`: `state.py` (`PilotServices.openev_camp_words`), `container.py`
  (loads the packaged table), `search_pages.py` (passes the words and the clock's date).
* `packages/debate_cli/src/debate_cli/commands/caselist_backfile.py`: imports the season rule.
* Tests, new: `test_season.py`, `test_camp_openev_words.py`, `test_search_pages_find_on_openev.py`
  (t16's `test_search_pages_open_on_openev.py`, renamed and rewritten), and one CLI test. Changed: [the
  list below](#existing-tests-that-changed).
* Docs:
  * `docs/data/search-index.md`: the link and the count.
  * `docs/runbooks/evidence-search.md`: format 3's step 3 check is done, and camp cards link from the
    function's deploy.
  * `docs/runbooks/caselist-cloud-run.md`: the hold is removed.
* The spec: the PM's amendment.

### Existing tests that changed

| Test | Change | Why |
|---|---|---|
| `test_search_source_links.py`, t16's OpenEv section | Replaced by the camp-page tests | The id-based link is gone |
| The same file's disclosed-card tests | Call `source_link` through a `linked` helper passing the words and a date | Both arguments are required, so a missed wiring fails loudly |
| `test_search_pages_open_on_openev.py` | Renamed `test_search_pages_find_on_openev.py` and rewritten | The link, its label and its source changed |
| t16's `test_on_a_format_two_index_no_camp_card_links` | **Now `test_on_a_format_two_index_the_camp_card_links_too`, on purpose** | Camp and year are in every format, so format 2 shows the link |
| t16's `test_a_camp_card_whose_index_row_has_no_openev_id_shows_no_link` | Replaced by the no-word and `UNKNOWN` page tests | An id no longer decides the link |
| `test_search_pages_follow_ups.py`: the camp-card no-link test | Renamed `…without_an_openev_word_for_its_camp` | The default test world's table has no words, which is now the reason |
| `packages/debate_api/tests/conftest.py`: `PilotWorld` | Takes `openev_camp_words`, empty by default | `PilotServices` requires the field |
| `test_caselist_backfile_survey.py` | One test added: the command's rule is the domain's | The move keeps one copy |

## Deviations from the spec

1. **The session stopped at the count before the ruling**, as the spec said to. The PM's ruling is
   now the spec's amendment ([above](#the-pms-ruling-and-the-amendment)).
2. **The OpenEv words are one top-level `openev:` section** (`camp: word`), not a key inside each
   camp's entry, which is a list of spellings. That keeps the `camps` section's shape and the
   importer's reading of it unchanged. Each canonical camp still gets at most one optional word.
3. **Outside `constraints.packages`:** one test in `packages/debate_cli/tests/`, which pins that the
   backfile command reads the domain's rule. The amendment added `debate_cli`, not its tests
   directory.

## Decisions and assumptions

* **The label uses the stored camp** (the card's provenance line already shows it), and the address
  uses the table's word.
* **`today` is the app's clock**, passed in. The domain reads no clock, and a page test moves the
  clock to show the bound follows it (mutant 4c).
* **The table is loaded once, when the function starts**, through the same packaged
  `camp_aliases.yaml` the importer reads. It is already in the wheel and in the API's import graph,
  through `card_download` and `openev_manifest`. A malformed section stops the start.
* **No smoke check names the link.** t16 added none either. The link is checked live by ac3.
* **The affected set is 396 test files**, mostly because any edit to `camp_aliases.yaml` reaches every
  test that imports `camp_metadata` (328 for the yaml alone, measured). That is past two minutes, so it
  is left to the pull request's `ci` (agreement 10). [What was run](#what-was-run-before-this-report)
  instead.

## Operator follow-ups

1. **ac3, after the merge: deploy dev's function, then the coach opens one camp card's link.** The
   deploy is [Moving the index to format 3](../runbooks/evidence-search.md#moving-the-index-to-format-3),
   step 1, from `$WT`, the checkout on `dev` after the merge. First the rehearsal, which calls no AWS:

   **Operator command** (expected runtime ~3 min)
   Where: `$WT`
   ```bash
   cd "$WT"
   git pull --ff-only
   uv sync --all-packages
   scripts/tub_deploy.sh dev --dry-run
   ```
   Success looks like the image built and the script stopping before the push. Then the deploy:

   **Operator command** (expected runtime ~3 min; changes dev's function)
   Where: `$WT`
   ```bash
   cd "$WT"
   scripts/tub_deploy.sh dev
   ```
   Success looks like `{"status":"ok"}` and `Deployed <sha> to dev`, where `<sha>` holds this task's
   merge. Then the coach signs in on dev and opens a camp card from a camp the table has a word for
   (UTNIF's, as committed). They check that it shows *Find on OpenEv: <camp> 2026 camp page*, and they
   open it. **Report back to the PM:** whether it landed on that camp's OpenEv page and the page lists
   the card's file (yes or no, and what it showed if not).

## Follow-up work

* **Keeping the pull's `OpenEvFile.camp` on the manifest row** goes into the PM's next batch as a p3
  task (the PM's ruling). It is the exact source of the word for files the pull imports.
* **More words:** any camp whose page the operator confirms later is one line in `camp_aliases.yaml`'s
  `openev` section and the packaged-table test's expected value, in a small task.

## What was run before this report

Every test run was bounded with `.venv/bin/python scripts/hard_stop.py 115`, with CI's markers
(`-m "not slow and not live"`) and `-n auto` unless noted.

| Command | Result |
|---|---|
| The count scripts (`count_camps.py`, `count_confirmed.py`, `/usr/bin/python3 -I`) | [The count](#the-count-first), 0.46 s |
| `count_linked.py` (`source_link` over the 102 files, the packaged table, `.venv/bin/python -I`) | 2 linked, 100 not, 1 camp |
| `uv run scripts/affected_tests.py` (the list only) | **396 test files**: past two minutes, so not run and left to the pull request's `ci` (agreement 10). Within the limit instead: |
| The always-run list (`tests/architecture tests/specs`, the CLI's `test_app.py`, `test_help_rendering.py`, `test_container_factories.py`), plus `packages/debate_core/tests/domain` and `test_caselist_backfile_survey.py` | 1513 passed in 26.63s |
| `packages/debate_api/tests` | 1102 passed in 8.15s |
| `packages/debate_core/tests/application/caselist` | 1759 passed in 73.25s |
| `packages/debate_core/tests/application`, caselist apart | 2948 passed in 16.43s |
| The other tests that read the changed docs or the alias table: `packages/debate_cli/tests/bucket_mode`, `test_search_index_sqlite_features.py`, `test_camp_names_in_openev_files.py`, `tests/docs/test_backfile_import_plan_check.py` | 290 passed in 112.09s, at a load average near 16 |
| `tests/scripts/test_caselist_run_image_plan_check.py` | 41 passed in 1.48s |
| Two earlier batches that combined those runs | Stopped by `hard_stop` at 115 s, with no failure before the stop. Split and rerun as above |
| The node criterion, `pytest packages/debate_core/tests/domain -k source_link -q` | 77 passed in 3.88s |
| `uv run --frozen ruff check .`, `ruff format --check .` | All checks passed; 1732 files already formatted |
| `uv run --frozen pyright` (the whole repository) | 0 errors, 0 warnings |
| `uv run --frozen lint-imports`, `scripts/check_thin_handlers.py` | 20 kept, 0 broken; 70 handlers within 25 statements |
| `scripts/check_links.py`, `scripts/check_command_blocks.py --base origin/dev`, `scripts/docs_index.py --check-descriptions` | OK |
| `uv run scripts/validate_specs.py` | OK (after the amendment, and again at the end). The Goal stays `InProgress` for ac3 |

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-31

**Notes:**

The count paid for itself. A link built from the stored camp would have been right for 2 files and
a guess for 96. The mechanism now links only where the operator has confirmed the word.
1. **ac1 passes** as recorded at the stop. The PM's ruling said it stands.
2. **ac2 passes.**
   * Red: 30 failed against a refuse-everything skeleton, all at assertions or unraised refusals.
   * Green: 246, and the node criterion passes (77).
   * All 18 mutants are caught: the PM's ten, plus 1b, the 3/4/9 variants, 11 and 12. 9b was a
     survivor until it got its own test, before the counted run, and the report says so.
   * The id-based address is gone (`git grep` finds nothing), and the format and the stored id are
     unchanged.
3. **ac3 is the operator's**, after the merge and dev's function deploy. The Goal stays
   `InProgress` for it.
4. **Deviations accepted:**
   * **1:** stopping at the count, as the spec said.
   * **2:** one top-level `openev:` section, which leaves the `camps` section's shape and the
     importer's reading of it alone.
   * **3:** the CLI test outside the packages. The PM's next batch adds `packages/debate_cli/tests`.
5. **Decisions accepted:**
   * the label uses the stored camp and the address uses the table's word;
   * `today` comes from the app's clock, passed in, so the domain reads no clock (mutant 4c);
   * the season rule moved into the domain, with the backfile command's behaviour pinned by a test;
   * the table is loaded once at the function's start, and a malformed section stops the start,
     never a link;
   * the table's load-time refusals: not a mapping, not a camp, UNKNOWN, not one word, one word for
     two camps;
   * the stored id kept, for a later per-file link;
   * a format 2 index showing the link, with t16's test changed on purpose;
   * no smoke check, since ac3 checks the link live.
6. **More words:** as committed, 2 of the 102 files link (UTNIF). Every word the operator confirms
   is a one-line config change to `camp_aliases.yaml`'s `openev` section and the packaged-table
   test's expected value. The PM files those through the next batch, as a config change, once the
   operator reports which of the twelve pages open a camp's page.
7. **Closing checks:** the affected set (396 files, mostly through `camp_aliases.yaml`) is left to
   the PR's `ci` under agreement 10. Every area it reaches was run within the limit: always-run and
   domain (1,513), API (1,102), caselist (1,759), the rest of application (2,948), bucket mode and
   the other readers (290), the image-plan check (41). ruff, pyright over the whole repository,
   lint-imports, thin handlers, the doc checks and the specs are clean.
8. **Merge and order:**
   * A plain `scripts/task pr` once `ci` is green.
   * This merge removes the hold on run images carrying v1-e39-t16.
   * Then dev's function deploy (follow-up 1), never on a Wednesday, followed by the coach's check
     for ac3.

## Operator records (recorded by the PM, 2026-11-01)

Added by the PM. Nothing above is changed, and this section is not a review.

| Criterion | Was | Now | Record |
|---|---|---|---|
| ac3: after dev's function is deployed with this task, the coach opens one camp card's link on dev and it lands on that camp's page | NOT RUN | PASS | 2026-11-01: dev's function deployed from `tub-deploy-dev` at `babccae` (`scripts/tub_deploy.sh dev`, image `sha256:26a2da6c...`, `/healthz` ok through CloudFront), carrying this task and the 13 OpenEv words of the 2026-11-01 sweep batch. The operator opened camp cards on dev: a Michigan card showed no link, as the table holds no Michigan word, and a DDI card showed the link, which opened DDI's camp page on OpenEv |

Every criterion passes, so the Goal is `Succeeded`.
