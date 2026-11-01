# Session report: v1-e39-t16-open-on-openev

| | |
|---|---|
| Task | `v1-e39-t16-open-on-openev` — Open on OpenEv: a camp card links to its camp file |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t16-open-on-openev.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t16-open-on-openev.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t16-open-on-openev` |
| Session status | COMPLETE |

## Summary

A camp card's page now shows **Open on OpenEv**, in a new tab with `rel="noopener noreferrer"`. The
link is built only from the OpenEv id the index stores for the card's representative occurrence. A
camp card without one shows no link, and disclosed cards are unchanged. `tub index build` reads each
camp file's id from its release manifest (`manifests/openev/<release>.jsonl`, the `openev_id`
`v1-e30-t14` writes on each row) into a new `occurrences.openev_id` column, which is in no FTS5
table. The index format moved once, from 2 to 3. The function reads formats 1, 2 and 3 and refuses any
other with *its format version is not one this build reads, 1, 2 or 3*. Both runbooks give the
deploy order: dev's function first, then the cloud run's image. The cloud-run runbook checks it before
every run image's digest line moves. Every criterion passed, so the Goal is `Succeeded`.

**Look at first.** [The count](#the-count-first): **0 of the 102** camp files with cards in the Mac's
store get an id, from the manifests or from anything else the repository has, so no camp card shows
the link until the pull imports a camp file. Also, the OpenEv page address is **not pinned by
anything in the repository**: it is a constant with a test, waiting on one check in a browser. Both
are in [the questions for the PM](#questions-for-the-pm).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `openev-link` | Done | Counted first, read-only. Then format 3, the reader, holder, build join and wiring, each under its tests, with the link's and the join's tests shown failing against skeletons first, then 15 mutants, then the data model and both runbooks |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a camp card's page links to its OpenEv file from the stored value, and a camp card without one shows none, by tests shown failing first | PASS | `packages/debate_api/tests/test_search_pages_open_on_openev.py`, through the real app: the camp card with stored id 4021 shows exactly `<a href="https://opencaselist.com/openev/4021" target="_blank" rel="noopener noreferrer">Open on OpenEv…</a>` below its provenance line. Id 777 with the same camp and title gives `/openev/777`. With no id, no link. On a format 2 index, no link. The disclosed card still shows its openCaselist link only. The results page shows none. No audit record holds the id. Domain rule: `test_search_source_links.py` (a title, camp or file name never makes a link; a boolean, zero or negative id makes none; a disclosed occurrence never links to OpenEv). [Red runs](#red-runs-before-the-code-they-test) below |
| ac2: the index format is bumped once and a holder given another format refuses it with a message; the deploy order is in the runbook | PASS | `SEARCH_INDEX_FORMAT_VERSION: Final = 3`, one bump. `test_holder_refuses_a_format_it_does_not_read_with_a_message` (format 4) asserts the refusal ends `its format version is not one this build reads, 1, 2 or 3`, and `test_holder_keeps_serving_when_a_format_it_does_not_read_is_published` shows the loaded index serving on with the warning logged. The order: `docs/runbooks/evidence-search.md`, [Moving the index to format 3](../runbooks/evidence-search.md#moving-the-index-to-format-3), and the check in `docs/runbooks/caselist-cloud-run.md`, [A new image, later](../runbooks/caselist-cloud-run.md#a-new-image-later) |
| Node `openev-link`: Pilot page tests pass (`uv run pytest packages/debate_api/tests`) | PASS | Run as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_api/tests -q -p no:randomly` → **1100 passed in 19.94s** |

### What dev's function, on the current deploy, does with a format 3 index

Measured on this branch's start commit, `6ea6688`, before any change: it reads formats 1 and 2, as
every build since `v1-e39-t13` does. Five of its tests already publish a format 3 index to it, and
all pass (**5 passed in 0.93s**):

* the pointer is refused before anything else is read (`UNKNOWN_FORMAT_VERSION`);
* a manifest naming format 3 is refused before the object is read;
* the refusal reads `its format version is not one this build reads, 1 or 2`;
* an environment already serving an index **keeps serving it** and logs the refusal, with no query text;
* the reader refuses a format 3 file: `format version 3; this build reads 1 and 2`.

So with the wrong order, a warm environment serves last week's format 2 index and a new environment
answers *Search is not available right now*, until the function is deployed. Deploying it ends it
within five minutes, and nothing needs rolling back. The runbook says so.

### Red runs, before the code they test

Each against a skeleton that had the plumbing and refused everything: `openev_ids_by_source`
returning `{}`, `openev_file_url` returning `None`, and `source_link` returning `None` for a camp
card.

| What | Result against the skeleton |
|---|---|
| The link's rule, `test_search_source_links.py` | **4 failed, 53 passed**: the three stored-id links and the "follows the stored id" test, each `assert None == SourceLink(...)`. The refusals pass, as a skeleton that refuses everything must |
| The join, `test_openev_ids_by_source.py` | **3 failed, 3 passed**: an id, the smaller of two, a hand import's id, each `assert {} == {...}` |
| The build, `test_search_index_build.py -k openev` | **4 failed**: the release's id, the caselist row, the provenance limit and the not-searchable test, each `None` where an id was expected |
| The pages, `test_search_pages_open_on_openev.py` | **3 failed, 4 passed**: the link, the stored id's address and the no-record test. A first run also failed two no-link tests on my own probe: card addresses are `/cards/openev/...`, so `"/openev/" not in page` was wrong. It became `"opencaselist.com/openev" not in page` before the run counted above |

### Mutation runs

Fifteen mutants. Each ran against only its covering test files with `-x`, each with a new, empty
`HYPOTHESIS_STORAGE_DIRECTORY` (agreement 8), and each file was restored with `git checkout HEAD --`.
The worktree was clean after every batch. **14 caught**, each by an assertion. One, 2b, cannot produce
the defect (below). Mutant 5's first form failed at collection, so it was replaced, not counted.

| # | Mutant | Caught by (first failure) | Time |
|---|---|---|---|
| 1 | **The link built from the title, not the stored value** | `test_a_camp_card_links_to_its_file_on_openev_from_the_stored_id[4021-…]` | 5.8 s |
| 2a | **The link shown on a disclosed card**: the rule tests the id before the caselist | `test_a_disclosed_card_never_links_to_openev_whatever_it_holds` | 3.6 s |
| 2b | The same at the build: a caselist row takes an id from any loaded release | not caught: equivalent, see below | 6.5 s |
| 3 | **A referrer sent**: `rel="noopener"` | `test_a_camp_card_links_to_its_file_on_openev_in_a_new_tab_with_no_referrer` | 1.6 s |
| 4a | **The holder accepting another format**: the pointer's format check off | `test_a_pointer_of_an_unknown_format_version_is_refused_before_anything_else_is_read` | 1.2 s |
| 4b | The readable formats take in 4 | the same | 1.3 s |
| 4c | The reader opens any format | `test_search_index_reader_refuses_a_file_that_is_not_this_index` | 2.0 s |
| 5 | **The column made searchable**: the build writes the id into the searchable cite | `test_search_index_openev_id_matches_nothing` (`AssertionError: 914273`) | 3.0 s |
| 6 | The container hands the build no manifests | `test_tub_index_build_gives_a_camp_occurrence_the_openev_id_its_release_manifest_records` | 1.1 s |
| 7 | The larger of a file's two ids | `test_a_file_at_two_paths_has_the_smaller_id_whatever_order_the_rows_are_in` | 0.8 s |
| 8 | A boolean id accepted by the join | `test_rows_that_carry_no_usable_id_give_none` | 1.2 s |
| 9 | A row that stored nothing gives its id | `test_a_row_that_stored_nothing_gives_no_id` | 1.6 s |
| 10 | The reader reads no id on format 3 | `test_a_camp_card_links_to_its_file_on_openev_in_a_new_tab_with_no_referrer` | 1.6 s |
| 11 | The link kept past the provenance limit | `test_a_camp_card_whose_stored_id_is_not_an_openev_id_has_no_link[past the provenance limit]` | 1.1 s |
| 12 | The build keeps the id past the provenance limit | `test_search_index_camp_occurrence_past_the_provenance_limit_keeps_no_openev_id` | 1.0 s |
| 13 | An unreadable manifest read as no ids | `test_search_index_unreadable_release_manifest_is_not_read_as_no_ids` | 1.0 s |

**Mutant 2b is equivalent.** The build joins one store at a time, with a fresh record cache per
store, and a caselist row's snapshot is a date: an id lookup for it reads
`manifests/openev/<date>.jsonl`, which no import writes. No camp release is loaded while a caselist
store's rows are joined. So a disclosed occurrence cannot be given an id by the build without a
second, deliberate change. `test_search_index_caselist_occurrence_never_has_an_openev_id` pins the
outcome, and mutant 2a shows the page rule guards it as well.

**Mutant 5, first form:** `SEARCHABLE_COLUMNS` with an `openev_id` added makes FTS5 name a column
that `documents` lacks, and the run errored at its first fixture. A crash is not a catch, so it was
replaced by the form above, which builds and searches, and fails on the assertion.

## The count first

Taken 2026-10-31 on the operator's Mac, read-only, counts only, by scripts in the session's scratch
directory. No name, path or title was printed.

| Source the PM named | What it holds for the `openev` store's camp files |
|---|---|
| The parsed store, `parsed/openev/2026.10.20-docx-6/` | 102 sources with cards, all in `2026-policy`, the `v1-e30-t06` hand import of 2026-09-26. The parse index has 104 entries: those 102 and 2 `2026-ld` files that parsed `UNSUPPORTED` with no card |
| The release manifests, `objects/manifests/openev/` | `2026-policy`: 106 member rows for the 102 files, **none with an `openev_id` key** (written before `v1-e30-t14`), none named `openev-<id>-...`. `2026-ld`: 2 rows, pulled 2026-10-14, named `openev-<id>-...`, no `openev_id` key yet |
| The delivery record, `caselist-sync-openev-deliveries.json` | 2 deliveries, the 2 `2026-ld` files; neither is a store file with cards |
| The sync's run records | 500 distinct ids listed (7,968 decisions `no_event_configured`, 2 `download`, 2 `already_imported`); no digest joins any to a store file |
| The inbox | empty |

**Without a re-parse: 0 of 102 get a value. Nor does any other means the repository has give them
one.** `caselist reimport-openev-metadata` takes the id from a row's name, and none of the 102 is
named with one. It would give the 2 `2026-ld` rows their ids, but they have no card. The cloud run's
store was seeded from this Mac's run-state bundle at the cutover and was not counted, since that
would be a read of the bucket.

**Where it is joined: at index build time, from the manifests.** The PM's preference was conditional
on that giving values for existing files, and it gives none. But a `CampFile` change gives none
either: the id would have to come from the same rows. The build join costs no `CampFile` field, no
caselist-database change, no parser or fingerprint version and no re-parse. It reaches every file the
pull imports from now on, which carries its id on its row since `v1-e30-t14`. It also reaches any
row a re-import later fills, without code in the importer. `CampFile` and the parser are untouched.

## Files changed

* `packages/debate_core/src/debate_core/domain/`: `search_index.py` (format 3, `OPENEV_ID_FORMAT_VERSION`, the readable set, `readable_formats_sentence`); `search_source_links.py` (Open on OpenEv, `OPENEV_FILE_URL_TEMPLATE`, `openev_file_url`); `evidence_search.py` (`OccurrenceProvenance.openev_id`).
* `packages/debate_core/src/debate_core/application/`: `caselist/openev_manifest.py` (`openev_ids_by_source`); `search_index_build.py` (the join, its `release_manifest_lines` port, the docstring); both index ports gained `openev_id`; `evidence_search.py` carries it to the card; `search_index_holder.py` names the readable formats.
* `packages/debate_core/src/debate_core/integrations/local/`: the writer's column; the reader's two occurrence statements, by format.
* `packages/debate_core/src/debate_core/testing/search_index.py`: `format_two_index`; `format_one_index` now drops the column too ([Deviations](#deviations-from-the-spec)).
* `packages/debate_cli/src/debate_cli/container.py`: hands the build `read_manifest_lines` of `evidence_object_path` ([Deviations](#deviations-from-the-spec)).
* Tests, new: `test_openev_ids_by_source.py`, `test_search_pages_open_on_openev.py`, six build tests, the domain link tests, one CLI build test. Changed: [the list below](#existing-tests-that-changed).
* `docs/data/search-index.md`: format 3, the column, the join, the count, never searchable.
* `docs/runbooks/evidence-search.md` and `docs/runbooks/caselist-cloud-run.md`: the order and its check ([Deviations](#deviations-from-the-spec)).
* `plan_specs/.../t16-open-on-openev.yaml`: the Goal's phase, `Succeeded`.

### Existing tests that changed

| Test | Change | Why |
|---|---|---|
| The holder's four unknown-format tests, in `test_search_index_holder.py` and `test_search_index_holder_formats.py` | Format 3 → 4, and the message `1 or 2` → `1, 2 or 3` | 3 is now read |
| `test_search_index_reader_sqlite_features.py`: `ALLOWED_STATEMENTS`, and the shape test traces a format 2 copy too | The card statement gains `openev_id`, and its formats 1 and 2 form (`NULL`) is added | Every allowed statement must be exercised, and the older one runs only on an older file |
| The same file's refusal test | `user_version` 3 → 4, `this build reads 1, 2 and 3` | The same |
| `test_evidence_search_passage.py::test_format_one_reader_says_its_format` | The running writer's file is format 3 | The bump |
| `test_search_pages_follow_ups.py`: the camp-card no-link test | Renamed `…shows_no_openev_link_without_a_stored_openev_id` | Its old reason, "the index has no OpenEv address", is no longer true |
| Every test that builds a `SearchIndexBuildService` (build, publish, shrink guard, stage, checked-against) | `release_manifest_lines=` added; the build test's `Store` keeps manifests by key | The argument is required, so a missed wiring cannot switch links off silently |

## Deviations from the spec

1. **The id is joined from the release manifests, not carried "through `CampFile`"**, as the spec's
   description words it. The PM's context of 2026-10-31 asked for the count and the choice, and
   preferred the build-time join. `CampFile`, the parser and both versions are unchanged ([the
   count](#the-count-first)).
2. **Outside `constraints.packages`:** `debate_cli` (the container's one line, and one test in
   `packages/debate_cli/tests/test_tub_index.py` that catches mutant 6), `debate_core.testing`
   (`format_two_index`, which core and API tests both need, as `v1-e39-t13`'s `format_one_index`), and
   `docs/runbooks` (both runbooks, as the PM's context asked). The list could add all three.

## Decisions and assumptions

* **The address is `https://opencaselist.com/openev/<id>`, one constant with a test, and unverified.**
  The repository pins the API the pull uses (`api.opencaselist.com/v1`, `GET /openev`, `GET
  /download?path=`), not a page a browser opens, and the index stores the id, never the path. Since
  `v1-e30-t14` the manifests also hold only the path's digest. The download address needs the path, so
  it cannot be built. A one-line hand-off checks the page shape ([follow-up 3](#operator-follow-ups)).
* **A file at two paths of a release takes the smaller id**, the first upload of those bytes, so the
  join does not depend on row order. A file from a zip carries the zip's id (`v1-e30-t14`), so its link
  opens the zip's entry.
* **The id is kept with the provenance** (the first `provenance_limit` occurrences), like the camp
  release's other columns, and only for the `openev` store.
* **An unreadable manifest stops the build** (`SEARCH_INDEX_STORE_NOT_READY`, naming key and line,
  never the line), as the build treats every store it cannot read. A missing manifest is no ids.
* **Formats 1, 2 and 3 stay readable.** No environment serves format 1, but dropping it would change
  what `v1-e39-t13` decided, for no gain here.
* **The manifests are not among the digests the index's manifest records** (see Q3).
* **The format check compares the format each commit writes.** A build reads the format it writes and
  every earlier one, as each has so far. The check's prose says that assumption.

## Questions for the PM

Paste-ready:

> **v1-e39-t16, three questions.**
>
> **Q1. No existing camp card gets the link.** On the Mac's store, 0 of 102 camp files with cards have
> an OpenEv id anywhere the repository looks: their manifest rows predate `v1-e30-t14`, their names
> carry no id, and no delivery or run record joins them. Links appear only for camp files the pull
> imports from now on. Options: (a) accept that, and no more work; (b) file a follow-up that measures,
> counts only and with an operator listing call, whether the 102 hand-imported files can be matched
> to the API listing's ids, and if so writes them into the manifest rows; (c) drop the link from the
> pilot until camp files carry ids. **Recommendation: (a) now, and (b) only if the coach wants links
> on this season's camp cards.** The feature costs nothing while it is dark, and (b) depends on how
> the hand import named its files, which only a count can say.
>
> **Q2. The OpenEv address is a constant nothing pins.** It is `https://opencaselist.com/openev/<id>`.
> Options: (a) keep it, and the operator opens one address in a browser (follow-up 3); if it is wrong,
> a small task changes the constant and its test before any card carries an id; (b) make it a function
> setting with no default, so no link shows until the address is configured, which is a Terraform
> change to the function's environment. **Recommendation: (a).** No card shows the link today (Q1),
> so there is time for the check, and the fix is one line.
>
> **Q3. The ids are not in the index's digests.** The weekly run rebuilds when a store's rows, the
> suppression list or a version changes. A re-import that only adds ids to manifest rows changes none
> of those, so the old index stays until something else changes. Options: (a) accept: nothing does
> that today, and a task that fills ids (Q1 (b)) can say "rebuild by hand"; (b) a follow-up adds a
> digest of the joined ids to the manifest. That is a manifest schema change, which the deployed
> function reads with `extra="forbid"`, so it needs its own deploy order. **Recommendation: (a).**

## What was run before this report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` (the list only) | **386 of 619 test files (62.4%)**, from 32 changed files, in 17.6 s. The container change is read by part (`_build_search_index_build`); most of the reach is `packages/debate_core/tests/application/caselist` (98 files). At about six minutes for the whole selection, 62% is past two minutes, so under agreement 10 it was **not run** and is left to the pull request's `ci`. Instead, within the limit: |
| The always-run list: `tests/architecture tests/specs packages/debate_cli/tests/test_app.py test_help_rendering.py test_container_factories.py` | 373 passed in 18.09s |
| `packages/debate_api/tests` | 1100 passed in 19.94s |
| `packages/debate_core/tests/domain packages/debate_core/tests/integrations/local packages/debate_cli/tests/test_tub_index.py test_tub_index_prune.py` | 1365 passed in 10.53s |
| `packages/debate_core/tests/application`, caselist apart | 2824 passed in 26.44s |
| `packages/debate_core/tests/application/caselist` | 1737 passed in 85.96s |
| The 11 test files that read `evidence-search.md` or `caselist-cloud-run.md` | 152 passed in 34.44s |
| `uv run --frozen ruff check .`, `ruff format --check .` | All checks passed; 1715 files already formatted |
| `uv run --frozen pyright` (the whole repository, as CI) | 0 errors, 0 warnings |
| `uv run --frozen lint-imports`, `scripts/check_thin_handlers.py` | 20 kept, 0 broken; 69 handlers within 25 statements |
| `scripts/docs_index.py --check-descriptions`, `scripts/check_links.py`, `scripts/check_command_blocks.py --base origin/dev` | All OK. The link check first caught the format 2 section's link to the renamed heading, fixed in `Point the format 2 runbook section…` |
| `uv run scripts/validate_specs.py` | OK: 545 files, 41 epics, 482 tasks, 22 releases |
| `scripts/spec_index.py --check` | `ROADMAP.md is stale`: from the base, since no commit here changes a spec but the phase. Not regenerated (CLAUDE.md); the refresh workflow does it after merge |

Every test run was bounded with `.venv/bin/python scripts/hard_stop.py 115`. The format check's
Python was also run offline against real commits: base `6ea6688` as the function and this branch as
the image gives `STOP: … reads 2 at most`, the reverse and the same commit give `OK`, and an unknown
commit gives `STOP: cannot read the format …`.

## Operator follow-ups

None of these is a criterion. They are the post-merge moves, in this order.

1. **Deploy dev's function with this task**, after the merge, as
   [Moving the index to format 3](../runbooks/evidence-search.md#moving-the-index-to-format-3), step 1
   says. First the rehearsal, which calls no AWS:

   **Operator command** (expected runtime ~3 min)
   Where: `$WT`, the checkout on `dev` after the merge
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
   Success looks like `{"status":"ok"}` and `Deployed <sha> to dev`, and a search on dev with a count
   above zero.

2. **Only then, the cloud run's image that carries this task**, by
   [A new image, later](../runbooks/caselist-cloud-run.md#a-new-image-later), whose new format check
   must print `OK: the image writes index format 3 and dev's function, at <commit>, reads it` before the
   digest line moves. Monday's image, `v1.1.0-dev.251`, does not carry this task. For it the check
   prints `OK: … format 2 …` whichever function is deployed, so it is unaffected. The first Wednesday
   run on the new image builds and publishes format 3.

3. **Check the OpenEv address once**, in a browser signed in to openCaselist. This prints one address
   from an id the Mac's run records list, and nothing else:

   **Operator command** (expected runtime under a second)
   Where: your Mac, anywhere
   ```bash
   python3 -I -c 'import glob, json, os; ids = sorted({one["openev_id"] for name in glob.glob(os.path.expanduser("~/.debate-research/dev/caselist-sync-runs/*.json")) for one in json.load(open(name)).get("openev_selections", [])}); print("https://opencaselist.com/openev/" + str(ids[-1]) if ids else "STOP: no OpenEv id in the run records")'
   ```
   Success looks like one `https://opencaselist.com/openev/<id>` line. Open it, and tell the PM
   whether it opens that file's page on OpenEv, or what it shows instead (Q2).

## Follow-up work

* **Matching the hand-imported camp files to OpenEv ids** (Q1 (b)), E30 or E39, if the PM wants it.
* **The joined ids in the index's digests** (Q3 (b)), E39, only if a task starts filling ids in
  existing rows.
* **The OpenEv address**, a one-line change to `OPENEV_FILE_URL_TEMPLATE` and its test, if follow-up 3
  shows the shape is wrong.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
