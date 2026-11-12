# Session report: v1-e08-t21-a-shared-doi-overrules-differing-openalex-ids

| | |
|---|---|
| Task | `v1-e08-t21-a-shared-doi-overrules-differing-openalex-ids` — Two results sharing a DOI are one work, even under two OpenAlex work ids |
| Spec | [`plan_specs/v1/e08-research-workflows/t21-a-shared-doi-overrules-differing-openalex-ids.yaml`](../../plan_specs/v1/e08-research-workflows/t21-a-shared-doi-overrules-differing-openalex-ids.yaml) |
| Epic / release | `v1-e08-research-workflows` / `v1.4` |
| Branch | `task/v1-e08-t21-a-shared-doi-overrules-differing-openalex-ids` |
| Session status | COMPLETE |

## Summary

A shared normalized DOI now overrules differing OpenAlex work ids in federated dedupe, which fixes the
OpenAlex duplicate from v1-e08-t10's question 4 (the PM's ruling A): one DOI listed under two work
ids, one at a repository's PDF and one at its `doi.org` page. The two records become one work. It
keeps both records as members, so both locations, and holds both work ids. Its fields come from the
fuller record, and its open-access copy is chosen by the existing field precedence. Provider agreement
counts OpenAlex once, because it already counts distinct providers. Nothing else changes: records with
no DOI, or with different DOIs, never merge by this rule, and a shared DOI still does not overrule a
differing PMID, arXiv id or Semantic Scholar id. The red run had 10 failures, all at assertions. 16
mutants were all caught by the new tests at assertions. The affected set (262 files) is over two
minutes, so it is left to the pull request's `ci` (agreement 10). The PM should look first at the
definition of "fuller" and its tie-break, under Decisions.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `a-shared-doi-overrules-differing-openale` (Shared DOI) | Done | Tests first (red commit `7f93334`), then the rule (`1a78f4d`, simplified in `51f6423`), and one more test from the mutant runs (`3120c52`). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: two results with one normalized DOI and differing OpenAlex ids merge into one work with both locations, and works without a shared DOI stay apart, by tests on recorded fixtures shown failing first | PASS | **Red** on `7f93334`, before any code change: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/application/test_federated_dedupe_shared_doi.py packages/debate_core/tests/application/test_federated_dedupe.py -q --tb=line -rf` → `10 failed, 160 passed`. Every failure is an `AssertionError`: "expected one work, got 2" from the `one_work` helper, a grouping such as `[[0], [1], [2], [3], [4], [5]] == [[0, 1], [2], [3], [4], [5]]`, or a field value. **Green** on the final tree: the same two files → `171 passed`. |
| Node: Shared DOI tests pass (`uv run pytest packages/debate_core/tests -k "dedupe or doi"`) | PASS | Run as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests -k "dedupe or doi" -q` → `289 passed in 15.45s` (288 before the last test was added). |

**The tests** are in `packages/debate_core/tests/application/test_federated_dedupe_shared_doi.py` (14).
The main fixture, `packages/debate_core/tests/fixtures/discovery/openalex/works_one_doi_two_work_ids.body.json`,
is an OpenAlex `/works` body written by hand, with invented titles, people and `10.5555` DOIs.
Nothing in it comes from ac6's saved file. The tests read it through the adapter's own
`candidate_from_work`. It holds:

* works 1 and 2: one DOI, written as a bare lower-case DOI and as an upper-case `https://doi.org/`
  URL, under work ids `W7100000002` (the `doi.org` page, 7 fields with values) and `W7100000001`
  (a repository PDF, 10 fields). The fuller work comes second, so taking the earlier record would
  give a different answer from taking the fuller one;
* works 3 and 4: the same title, author and year with different DOIs;
* works 5 and 6: the same title, author, day and site with no DOI. Work 6's `doi` is a URL that is
  not a DOI, which the adapter drops.

Each case the brief asked for has a test:

* the DOI written two ways merges into one work with both locations;
* different DOIs stay two, and so do two works with no DOI;
* the fuller record's fields win, a field it lacks comes from the other copy, empty values do not
  make a record fuller, and between equally full records the earlier one wins in both input orders;
* provider agreement counts OpenAlex once: 0.0 with two providers answering, not the 1.0 that
  counting members gives, and 0.5 with Crossref among three;
* a DOI shared across OpenAlex and Crossref still merges, with Crossref's title.

Four more tests guard what must not change, or follow from the rule:

* a shared DOI does not overrule a differing PMID;
* two works with no DOI but one arXiv id stay two;
* a record naming either work id joins the merged work;
* two records of one work id that another rule joins still take the earlier record's values.

t10's pin `test_exact_doi_does_not_merge_two_openalex_works_that_share_it_under_different_work_ids`
pinned the old behaviour. It is inverted as `test_exact_doi_merges_two_openalex_works_that_share_it_under_different_work_ids`,
and it failed in the red run.

### Mutants

There were 16 mutants. Each was planted on the committed tree (`3120c52`) and run against
`test_federated_dedupe_shared_doi.py` and `test_federated_dedupe.py` with `-n 0`. Each run got a new
empty `HYPOTHESIS_STORAGE_DIRECTORY`, although neither file uses Hypothesis. Each mutant was restored
with `git checkout HEAD --`, and `git status --porcelain` was empty afterwards. Every mutant was caught
by at least one new test failing at an assertion.

| Mutant | Area | Caught by (new tests, all at assertions) |
|---|---|---|
| The DOI keeps its case (`_normalize_doi` drops the final `.lower()`) | DOI comparison: raw, not normalized | 7 new tests: the fixture mapping, the merge, the grouping, both agreement tests, the Crossref test, either-id. 6 older tests also fail (3 of them crash at tuple unpacking, which does not count). |
| The DOI keeps its resolver prefix (no prefix stripped) | DOI comparison: raw, not normalized | The fixture mapping, merge, grouping, agreement-once and either-id tests, at assertions: the adapter drops a DOI it cannot normalize, so the two works have none. Tests that build `ArticleIdentifiers` from a URL by hand crash with `ValidationError`, which does not count (t10's lesson). |
| The overrule is removed | Id overrule | 9 tests, among them the merge, the grouping, the tie-break, agreement, and t10's inverted pin |
| The overrule applies under every rule | Id overrule | The no-DOI pair in the grouping test (`[4, 5]` merged), the arXiv-only pair, and the older openalex-ids-differ parametrization |
| The overrule also applies under the title rule | Id overrule | The same three |
| The overrule also applies under the provider-id rule | Id overrule | The arXiv-only pair |
| A shared DOI overrules every identifier kind | Id overrule | The differing-PMID test |
| The group keeps one OpenAlex id, not both (`{**left, **right}`) | Id overrule | Either-id (`[[0, 1, 3], [2]]`) |
| Groups disagree when their id sets differ, not when they share none | Id overrule | Either-id |
| The fuller record never comes first | Fuller record | Fuller fields win, a lacking field comes from the other, empties, and the Crossref test |
| The fuller record comes first in every group | Fuller record | Two records of one work id joined by another rule |
| The thinner record comes first | Fuller record | The same four as "never first" |
| The tie-break takes the later record | Fuller record | The tie-break test |
| Fullness is compared before provider order | Fuller record | The Crossref test (the title would come from OpenAlex) |
| Fullness counts empty values (`()`, blank text, `other`) | Fuller record | The empty-values test. The first run had no such test, and this mutant **survived** (170 passed), so the test was added in `3120c52` and the mutant re-run. |
| Agreement counts members, not providers | Agreement count | Both agreement tests |

No live provider call: the tests read a local JSON body and build records in memory.

## Files changed

* `packages/debate_core/src/debate_core/application/federated_dedupe.py`: the rule.
  * `_Groups` keeps each group's identifier values as sets. A join by the DOI rule skips the
    OpenAlex kind (`_OVERRULED_BY_A_SHARED_DOI`).
  * `merge_group` orders one provider's members fuller first, only in a group holding two or more
    OpenAlex ids (`_fullness`, `_FULLNESS_FIELDS`).
  * `_openalex_key` is factored out of `_identity`.
  * The module docstring gains two paragraphs: the overrule, and the fuller record.
* `packages/debate_core/tests/application/test_federated_dedupe_shared_doi.py`: new, 14 tests.
* `packages/debate_core/tests/application/test_federated_dedupe.py`: t10's pin, inverted.
* `packages/debate_core/tests/fixtures/discovery/openalex/works_one_doi_two_work_ids.body.json` and
  that directory's `README.md`: the fixture, and a line describing it.
* The spec's Goal phase, set to `Succeeded`, and this report.

## Deviations from the spec

1. **The fixture lives with the OpenAlex adapter's fixtures**, under `packages/debate_core/tests`,
   which is inside the task's packages. It is read through `candidate_from_work`, so the dedupe test
   imports `debate_core.integrations.discovery.openalex` (the adapter's mapping, not its client).
   I chose this so that the records are the ones a real OpenAlex answer gives. The tests do not
   depend on adapter code beyond that mapping.
2. **t10's pin test is inverted, not kept.** It pinned the rule this task changes.
3. **The node's command was run as `.venv/bin/python -m pytest` under `scripts/hard_stop.py`**, as
   the session brief requires, rather than `uv run pytest`. The selection is the same.
4. **No smoke check was added.** The task adds no CLI command, API route or job, and its only visible
   effect is one result fewer where OpenAlex lists a duplicate.

## Decisions and assumptions

* **"Fuller", defined.** A record's fullness is how many of these 14 merged fields it gives a value:
  the five identifiers (DOI, arXiv id, PMID, OpenAlex id, Semantic Scholar id), `source_type`,
  `authors`, `publication`, `published_at`, `snippet`, `open_access_url`, `open_access` and
  `citation_count`.
  * `title`, `url` and `canonical_url` are not compared, because every record has them.
  * A value is judged by the emptiness test the precedence already uses. `None`, no authors, blank
    text and source type `other` are empty. `open_access = False` and `citation_count = 0` are values.
  * The fuller record comes first among one provider's members. Then each field takes the first value
    in that order, so the fuller record's values win wherever it has one, and a field it lacks comes
    from the other copy.
  * Provider order still comes before fullness (Crossref still gives the title), and for
    `published_at` so does date precision (v1-e07-t03).
* **The tie-break is input order:** the earlier record wins between two equally full ones. That is
  the order the provider returned them in, and the rule dedupe already applied between two records of
  one provider. It is deterministic for a given answer, and a stored search replays to the same
  merge. The test runs both orders.
* **Fullness decides only in a group holding two or more OpenAlex work ids**, which only the
  shared-DOI rule makes. Every other group keeps the earlier record first, as before (tested), so no
  other merge changes.
* **The overrule needs a DOI stated by both records.** Dedupe gives an arXiv record without a DOI its
  arXiv DOI for the identifier rule, but that does not count here, so works that state no DOI never
  merge by this rule (the spec's forbidden list).
* **The overrule is tied to the DOI rule's joins**, not to a DOI tracked per group. The DOI rule runs
  first. Two groups that both state one DOI and are still apart after it disagree on an identifier the
  DOI does not overrule, so a later rule would refuse them anyway. The first implementation tracked
  the DOI per group, which behaves the same, but every mutant of its bookkeeping would have been
  equivalent (`51f6423`).
* **A merged work holds both work ids.** A record carrying either id joins it by the provider-id rule.
  The merged `identifiers.openalex_id` is the fuller record's.
* **The open-access copy** is chosen by the existing `open_access_url` precedence (indexes first). The
  only new thing is the fuller-first order between the two OpenAlex copies. In the fixture it is the
  repository PDF, the only open copy.
* **Provider agreement needed no code change.** `provider_agreement` counts `len(candidate.providers)`,
  the distinct providers, and the footer's "found by N providers" counts the same tuple. The tests pin
  it, and a mutant that counts members fails them.

## Verification before the report

| Check | Result |
|---|---|
| `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python scripts/affected_tests.py --run` | **Stopped at its 115-second limit** (exit 124) at 39% with no failure. The selection is 262 of 744 test files, chosen in 20.3 s. Over two minutes, so it is left to the pull request's `ci`, which runs the same affected set (agreement 10, the PM's ruling of 2026-10-19). |
| The always-run list, the discovery adapters' tests (the fixture's directory) and `packages/debate_core/tests/application/test_federated_*.py`, `-m "not slow and not live"` | `1821 passed in 34.10s` |
| `ruff format --check .` / `ruff check .` | `2060 files already formatted` / `All checks passed!` |
| `pyright packages/debate_core` | `0 errors, 0 warnings, 0 informations` |
| `lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `scripts/check_thin_handlers.py` | `OK: 74 CLI command and API route handlers within 25 statements` |
| `uv run scripts/validate_specs.py` | `OK: 669 files, 41 epics, 606 tasks, 22 releases` |

## Operator follow-ups

None. The affected set runs in the pull request's `ci`.

## Follow-up work

* **The live NHI search's two copies were not re-checked.** Under this rule, the duplicate at ranks
  46 and 47 of ac6's saved results should be one result. Only a live search shows that, and t10's
  required live check (after its merge) would show it in passing. I did not add a second hand-off.
  The PM decides whether t10's check should also print the result count for that DOI.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
