# Session report: v1-e06-t01-citation-service

| | |
|---|---|
| Task | `v1-e06-t01-citation-service` — CitationService with per-field provenance |
| Spec | [`plan_specs/v1/e06-card-cutting/t01-citation-service.yaml`](../../plan_specs/v1/e06-card-cutting/t01-citation-service.yaml) |
| Epic / release | `v1-e06-card-cutting` / `v1.3` |
| Branch | `task/v1-e06-t01-citation-service` |
| Session status | COMPLETE |

## Summary

`CitationService` (`debate_core.application.citation_service`) resolves a card's cite from an article
and a checked snapshot load. A pure harvester reads the stored raw HTML: JSON-LD, `citation_*`,
`article:*` and Dublin Core meta tags, the canonical link, OpenGraph, bylines and author bios, and
the URL's own heuristics. A Crossref `/works/{doi}` client, cached by DOI on this machine, supplies
the deposit, and the service merges everything by the spec's precedence. Every field is a
`CitationField(value, source, verified, raw)`. Only explicit sources of publisher-retrieved
snapshots verify; a heuristic never does, and nothing about USER_SUPPLIED text does. `format_cite`
writes "Lastname YY" and the full cite line and names every unverified and missing field.
`re_resolve` keeps a student's changed field unless it equals the derived value (ac5, shown failing
first). Every criterion passed and the Goal is `Succeeded`.

The PM ruled on the three open questions on 2026-10-26 (quoted under **Deviations** and
**Decisions**). The harvester and its test live in `debate_core.retrieval`, and the test was moved
to `packages/debate_core/tests/retrieval/test_citation_harvest.py`. One criterion is affected: the
`page-metadata` node's command, as the spec still writes it, names the test's old path. It passes at
the new path, and the PM amends the command in the next batch. The accessed date and the
retrieved-URL fallback are accepted as `heuristic` for this task, and a `retrieval` source goes to
`v1-e06-t02`. Organization authors and refilling an emptied field are also deferred to `v1-e06-t02`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `citation-model` | Done (already present) | `domain/citation.py` already held `CitationField[T]` (value, source, verified, raw), `Citation` and `is_fully_verified` from E02. Nothing was changed. |
| `page-metadata` | Done | `debate_core/retrieval/citation_harvest.py`, on the shared JSON-LD walk `retrieval/json_ld.py`; its test is `tests/retrieval/test_citation_harvest.py` (PM ruling; see Deviations). Red: 30 failed, 14 passed against a skeleton (`b5f3ff0`); green: 45 passed. |
| `crossref-doi` | Done | Port `application/ports/doi_metadata.py`; adapter `integrations/crossref_doi.py`; synthetic respx answer. Red: 22 failed, 3 passed (`4f0c32e`); green: 25 passed. |
| `merge-and-format` | Done | `application/citation_service.py`. Red: 74 failed, 7 passed (`602e565`). ac5 red with everything else implemented: 3 failed, 78 passed (`dfc7f31`); green: 81 passed (`82e339e`). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: each fixture page (news, think tank, government, journal) has every field's value, source and verified flag as its expected JSON | PASS | `uv run pytest packages/debate_core/tests/application/test_citation_service.py` → 81 passed. `test_every_cite_field_has_the_value_source_and_flag_the_fixture_expects` runs the four kinds plus an open-access PDF and a USER_SUPPLIED case, against `tests/fixtures/citation/<case>.expected.json`, written by hand before the service existed. |
| ac2: a DOI is fetched once, cached by DOI and preferred for title, container, date and authors; failures degrade without raising | PASS | Same run: `test_a_doi_is_looked_up_once_however_many_times_its_cite_is_resolved` (1 request for 3 resolutions over two snapshots), `test_crossref_is_preferred_to_the_pages_own_meta_tags`, `test_crossref_wins_over_every_page_source`, and degradation on ConnectError, ReadTimeout, 500, 429, non-JSON, a failed envelope and 404 (`PAGE_METADATA_OF_THE_JOURNAL`, written by hand). `test_crossref_doi.py` → 25 passed: the file cache outlives the client, an unreadable cache file is refetched, a failure caches nothing. |
| ac3: credentials only from an explicit bio, JSON-LD `jobTitle`/`affiliation` or Crossref affiliation; otherwise missing with no qualification in the cite | PASS | `tests/retrieval/test_citation_harvest.py` → 45 passed: no credential from a byline's job title (the news page's "Science Correspondent"), from `citation_author_institution`, from a `description`, or from a bio naming no author. `test_citation_service.py`: Crossref affiliations, Crossref over a bio, a deposit with no affiliation leaving the bio, and a news cite with no parenthetical. |
| ac4: `format_cite` gives the short cite ("Smith 26") and the full line with accessed date, and flags unverified fields | PASS | `test_each_fixture_cite_formats_as_the_fixture_expects` (six cases, hand-written lines), plus last-name, "et al.", "ND", no-author, stated-day and provenance-note cases. `FormattedCite.unverified_fields` / `missing_fields`. |
| ac5: a student's changed field is verified on re-resolution only when it equals the derived value; otherwise kept, unverified and marked | PASS | Run red first: with `keep_student_edits` overwriting, 3 failed, 78 passed (`dfc7f31`). Green: 81 passed (`82e339e`). Tested end to end through `CardEditService` and the edit log: a differing value kept and named in `student_fields`; a value equal to the derivation verified, after which the card verifies again; a value equal to a heuristic stays unverified; only changed fields kept; a never-edited card takes the derived cite whole. |
| Node `citation-model`: `artifact_exists` `domain/citation.py` contains `class CitationField` | PASS | `grep -c "class CitationField" packages/debate_core/src/debate_core/domain/citation.py` → 1 |
| Node `page-metadata`: harvester fixture tests pass | PASS at the path the PM ruled | `uv run pytest packages/debate_core/tests/retrieval/test_citation_harvest.py` → 45 passed in 2.16s. The command as the spec still writes it, with `tests/evidence/`, now names a moved file and finds nothing. It passed there (45 passed in 1.43s) before the PM's ruling of 2026-10-26 moved the file. The PM amends the command in the next batch. |
| Node `crossref-doi`: `uv run pytest packages/debate_core/tests/integrations/test_crossref_doi.py` | PASS | 25 passed in 1.37s |
| Node `merge-and-format`: `uv run pytest packages/debate_core/tests/application/test_citation_service.py` | PASS | 81 passed in 1.88s |
| Node `merge-and-format`: `uv run pyright packages/debate_core` | PASS | 0 errors, 0 warnings, 0 informations (17.7 s) |
| Forbidden: LLM-generated or LLM-guessed author, credential, publication or date values | Holds | No model is called anywhere in the path; every value is a harvested string or a Crossref field. |
| Forbidden: marking a field verified when its only source is a heuristic | Holds | `_chosen` verifies only non-heuristic sources, and the domain validator refuses a verified heuristic. Mutant "verified: heuristic counts" caught (8 failed). |
| Forbidden: live Crossref or publisher calls in CI | Holds | respx and `httpx.MockTransport` only; pytest runs with `--disable-socket`. |

### Mutation run (agreement 8)

22 mutants over `citation_service.py`, `citation_harvest.py` and `crossref_doi.py`. Each was planted
on a committed tree, run against the three test files (`-n 0 -p no:randomly`; the harvester's was
still at `tests/evidence/` then, with the same contents), and restored with
`git checkout`, with `git diff --quiet` confirming each restore. Every run set
`HYPOTHESIS_STORAGE_DIRECTORY` to a fresh empty directory. These suites have no Hypothesis
properties, so no catch here depends on a replayed example. All 22 were caught. One was at first
not planted, because ruff had reformatted its target; it was rewritten and run alone, and caught.

| Mutant | Caught by (first failure) |
|---|---|
| precedence: JSON-LD below meta tags | 2 failed: news fixture; `higher_source_wins[json_ld-meta_tag]` |
| precedence: meta tags below OpenGraph | 9 failed: journal page-metadata degradation |
| precedence: OpenGraph below byline | 1 failed: `higher_source_wins[opengraph-byline]` |
| precedence: byline below heuristic | 1 failed: `higher_source_wins[byline-heuristic]` |
| precedence: Crossref below JSON-LD | 1 failed: `crossref_wins_over_every_page_source[json_ld]` |
| precedence inverted (`max` for `min`) | 36 failed |
| Crossref answer ignored | 21 failed: journal and PDF fixtures |
| verified: a heuristic counts | 8 failed: government and PDF fixtures |
| verified: any provenance verifies | 4 failed: `no_field_is_verified_unless_the_platform_retrieved_the_source` |
| credentials: a Crossref author with no affiliation | 6 failed: journal and PDF fixtures |
| Crossref date: a partial date completed | 2 failed: `a_deposit_date_without_a_day_is_not_used` |
| student edit: a verified stored value kept | 1 failed: `keep_student_edits_never_keeps_a_value_marked_verified` |
| student edit: an equal value kept as the student's | 7 failed: `a_changed_field_equal_to_the_derived_value_is_verified` |
| student edit: an emptied field kept empty | 1 failed: `a_field_the_student_emptied_is_derived_again` |
| student edit: rule applied to never-edited cards | 1 failed: `a_card_never_cite_edited_takes_the_derived_cite_whole` |
| student edit: cite edits not recognised in the log | 2 failed |
| credentials: bio paragraphs not checked for an author | 3 failed |
| credentials: a byline read as a bio | 8 failed: news fixture |
| credentials: a JSON-LD author with nothing stated | 9 failed |
| credentials: the meta description | 5 failed: think-tank fixture |
| heuristic: a URL path date recorded as a meta tag | 4 failed |
| Crossref: cache not read | 3 failed: the fetched-once tests |

### Checks before the report (agreement 10)

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` (list only), then `pytest --collect-only` over it | 200 of 525 files, 5,644 tests. That is past the two-minute line, so it was not run and is left to the PR's `ci` check (PM ruling of 2026-10-19). After the last commit, which edits `pyproject.toml`, the whole selection counts as affected anyway. |
| `.venv/bin/python -m pytest -m "not slow and not live"` over the changed modules' tests and the always-run list: `tests/retrieval/`, `test_citation_harvest.py` (then under `tests/evidence/`), `test_citation_service.py`, `test_article_service.py`, `test_card_edit_service.py`, `test_port_conformance.py`, `test_snapshot_service.py`, `test_html_extractor.py`, `test_pdf_extractor.py`, `tests/integration/test_fetch_cli.py`, `tests/fixtures/test_cassette_hygiene.py`, `test_doctor.py`, `test_installation.py`, `test_app.py`, `test_help_rendering.py`, `tests/architecture/`, `tests/specs/` | 1620 passed in 23.79s |
| The httpx-logger suites in one process, `-n 0 -p no:randomly`: `integrations/discovery/`, `test_http_fetcher.py`, `integrations/opencaselist/`, then `test_crossref_doi.py`, `test_citation_service.py`; and again in the reverse order | 825 passed (3.83 s); 825 passed (1.92 s) |
| `uv run --frozen ruff check .` / `ruff format --check .` | All checks passed / 1461 files already formatted |
| `uv run --frozen pyright` (whole repo, as CI) | 0 errors, 0 warnings, 0 informations |
| `uv run --frozen lint-imports` | Contracts: 18 kept, 0 broken. Planted `import lxml` and `import keyring` in `crossref_doi.py` broke the two matching contracts, naming the module, and were removed. |
| `uv run --frozen python scripts/check_thin_handlers.py` | OK: 66 handlers within 25 statements |
| `uv run scripts/validate_specs.py` / `--require-succeeded v1-e06-t01-citation-service` | OK: 469 files, 40 epics, 407 tasks, 22 releases / Succeeded |
| `uv run --frozen python scripts/docs_index.py --check-descriptions` (after this report was written) | All 53 indexed documents under docs/ have a description |
| `uv run --frozen python scripts/check_command_blocks.py --base origin/dev` | OK: no `#` comments in 504 shell code blocks in 180 Markdown files (1 session report changed) |
| `pytest tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py` | 191 passed in 2.77s |
| After the PM's rulings (test moved, report updated): `pytest -m "not slow and not live" packages/debate_core/tests/retrieval tests/architecture tests/specs tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py`; `ruff check .`; `check_command_blocks.py --base origin/dev`; `docs_index.py --check-descriptions`; `validate_specs.py` | 1351 passed in 8.20s; all checks passed; OK (504 blocks); all 53 documents described; OK, and `--require-succeeded` Succeeded |

## Files changed

* **`debate_core.retrieval`**: `json_ld.py` is the one JSON-LD walk, shared by `access.py` (its copy
  removed) and the HTML extractor (its copy removed). That refactor is its own commit (`cac099f`);
  `tests/retrieval` and `test_html_extractor.py` passed after it with no expectation edited (867
  passed). `citation_harvest.py` is the page metadata harvester.
* **`debate_core.application`**: `citation_service.py` is the service, the merge, `keep_student_edits`
  and `format_cite`. `ports/doi_metadata.py` is the DOI lookup port and its values. One row was added
  to the table in `ports/__init__.py`'s docstring.
* **`debate_core.integrations`**: `crossref_doi.py` is the client, `FileDoiCache` and
  `InMemoryDoiCache`. In `html_extractor.py` the JSON-LD walk now calls `retrieval.json_ld`.
* **Tests**: `tests/retrieval/test_citation_harvest.py`, `tests/integrations/test_crossref_doi.py`,
  `tests/application/test_citation_service.py`, `tests/retrieval/test_json_ld.py`.
* **Fixtures** (`tests/fixtures/citation/`): one new synthetic page (`journal-article-landing.html`),
  one synthetic Crossref answer under `10.5555`, six hand-written `<case>.expected.json` files, the
  README saying how each was made, and `citation_world.py`, the wiring the service tests share.
  t04's three HTML pages and its PDF are used unchanged, at t06's addresses.
* **`pyproject.toml`**: `debate_core.integrations.crossref_doi` was added to the boto3, keyring,
  lxml/docx, extraction-library and defusedxml contracts, and kept off the httpx list (its comment
  names it as allowed).

## Deviations from the spec

1. **The harvester is `debate_core/retrieval/citation_harvest.py`, not
   `debate_core/evidence/citation_harvest.py`.** The PM's instruction was to share one JSON-LD walker
   in `debate_core.retrieval` rather than add a third copy. The layers contract makes `evidence` and
   `retrieval` independent (`"evidence | retrieval | arguments"`), so a harvester in `evidence` cannot
   import that walker, nor `retrieval.identifiers.detect_identifiers` for DOIs, nor
   `canonicalize_url`. `retrieval` ("the pure procedures that turn a URL and fetched bytes into an
   article") is where both already live. Both modules are outside the spec's
   `constraints.packages`; the walker's place was the PM's instruction, and the harvester follows it.
   **PM ruling, 2026-10-26:** "Yes. The harvester stays at retrieval/citation_harvest.py. git mv its
   test to packages/debate_core/tests/retrieval/ and use that path in the report's evidence. Record
   it under Deviations. The PM amends the node's output, its command and constraints.packages (adding
   debate_core.retrieval) in the next batch." The test was moved with `git mv` to
   `packages/debate_core/tests/retrieval/test_citation_harvest.py`, and its docstring says why. Until
   the amendment lands, the node's command as written names the old path; see Acceptance criteria.
2. **"Recorded fixture pages" are synthetic** (the E04 amendment of 2026-10-25 and the PM's note for
   this task). Three are t04's pages, unchanged. One page, a journal landing page with `citation_*`
   tags, was added, because t04's journal sample is a PDF and has no meta tags. The fixture README
   gives each one's origin. No existing page was edited, so t04's and t06's expectations are untouched.
3. **Two more cases than ac1 names**: t06's open-access PDF (Crossref plus a heuristic URL) and a
   USER_SUPPLIED snapshot. They pin the PM's provenance rule and the non-HTML path.

## Decisions and assumptions

* **The accessed date and the retrieved-URL fallback are `heuristic`, unverified.** ac1 requires
  every field's source to be one of `meta_tag | json_ld | opengraph | crossref | byline | heuristic |
  missing`. The accessed date is the snapshot's `retrieved_at`, the platform's own record, and none
  of those names it. Of the seven, `heuristic` is the only one that does not overclaim. `raw` holds
  the timestamp. The accessed date is not a required field, so it never holds a card back, but every
  cite lists it in `unverified_fields`. The same applies to the URL of last resort, when a page
  declares no canonical URL: the retrieved URL, canonicalized, is `heuristic`. So an open-access PDF
  cite has an unverified `canonical_url`, and a card cut from a PDF cannot reach VERIFIED.
  **PM ruling, 2026-10-26:** "Accepted as built for this task: the accessed date, and the retrieved
  URL when the page names no canonical one, are recorded as heuristic and unverified. The PM amends
  v1-e06-t02 to add a retrieval source, verified for publisher-retrieved snapshots. That covers the
  enum, the schema export and ac1's list. t02 is where VERIFIED is decided."
* **What "verified" means.** A value is verified when its source is anything but `heuristic` and the
  snapshot is PUBLISHER_RETRIEVED. Under any other provenance nothing is verified, Crossref
  included. The text could be anything, so a DOI in its URL proves nothing about it. The provenance
  mode is on `CitationResolution` and `FormattedCite`, and the full cite ends "user-supplied text",
  "pasted text" or "imported from a debate file" when the platform did not retrieve the text.
* **USER_SUPPLIED snapshots are never parsed as HTML.** Only their URL is read, plus the title the
  user gave the article (heuristic). The fixture's pasted text carries a typed `<meta>` tag and a
  byline, and neither is read.
* **Crossref dates are used only to the day.** The first whole date among `published`,
  `published-online`, `published-print` and `issued` is used. A year or a month alone is never
  completed with an invented day, so the page's date stands. Page dates follow the same rule
  (`parse_stated_date`), and a day-first or month-first all-number date is refused as ambiguous.
* **The cite prints the day the source named.** "2026-09-14T22:30:00-04:00" is stored as 02:30 UTC
  on the 15th, but printed "September 14, 2026": `format_cite` re-reads the field's `raw`.
* **Credentials are verbatim.** A bio's paragraphs are kept only when they name an author in full, on
  word boundaries. JSON-LD and Crossref give "Name, job title, affiliation" per author, joined by
  "; ". No sentence is shortened or reworded, so nothing is inferred.
* **Which re-resolved fields count as a student's (ac5).** The rule applies only to a card whose
  `CardEditLog` holds an `edit_cite` entry. A card never cite-edited takes the derived cite whole,
  so an older unverified value the service itself wrote is not mistaken for a student's. On an
  edited card, a stored field marked verified is an older derivation (a changed field cannot arrive
  verified), and the derivation replaces it. A field the student emptied cannot be told from one
  never resolved, so it is derived again. **PM ruling, 2026-10-26:** "accepted for t01. It conflicts
  with the intent of ac5, so the PM amends v1-e06-t02: clearing a field is recorded as a student
  edit, and re-resolution never refills it." `test_a_field_the_student_emptied_is_derived_again` pins
  this task's behaviour, so t02's change will show up as that test failing. Saving and re-verifying the card is the caller's step
  (CardService, `v1-e06-t02`), as the service returns a `CitationResolution`.
* **Crossref caching.** Found works are cached in `<storage.data_dir>/crossref/<sha256(doi)>.json`.
  A 404 and a failure are not cached, so they are asked again next time. The contact email goes as
  `mailto=` and is registered with the discovery log filter, so httpx's request line carries it
  masked (`test_httpx_logs_the_request_without_the_contact_email`). Errors chain no exception.
* **Short cite.** The first author's last name, with " et al." for more than one author. Without an
  author it falls back to the publication, then the title, then `[no author]`; without a date it
  ends "ND". "Smith, Jane" and "Jane Smith Jr." both give Smith. Team conventions are `v1-e06-t03`'s.
* **No composition-root wiring** (the PM agreed on 2026-10-26: "The CLI wiring stays for t02 or t06"). No command uses the service yet, so `debate_cli.container` is
  unchanged, and so are the pinned integration lists in `test_doctor.py` and `test_installation.py`.
  `cut` (`v1-e06-t06`) or CardService (`v1-e06-t02`) builds `crossref_doi_client(...)` over a
  `FileDoiCache(data_dir / CROSSREF_CACHE_DIRECTORY)`.

## Operator follow-ups

None. No command in this session needed the network, credentials or more than two minutes.

## Follow-up work

1. **A `retrieval` source for the platform's own retrieval record**: ruled into `v1-e06-t02` by the
   PM's amendment. It is verified for publisher-retrieved snapshots and covers the enum, the schema
   export and ac1's list. Then the accessed date, and a PDF's or a canonical-less page's URL, stop
   holding cards UNVERIFIED.
2. **Organization-issued sources**: deferred to `v1-e06-t02` by the PM's amendment. A press release
   that names no person has `authors` missing, and `authors` is a required field, so today its card
   can never be VERIFIED. **PM ruling:** "When a page names no person, the issuing organization may
   stand as the author, marked as an organization author. My lean is yes, because that is debate
   convention; t02 decides with a test."
3. **An emptied cite field is a student edit**: ruled into `v1-e06-t02` by the PM's amendment.
   Re-resolution never refills it (Decisions, ac5).
4. **Spec amendment, next batch (PM)**: the `page-metadata` node's output becomes
   `retrieval/citation_harvest.py`, its command `tests/retrieval/test_citation_harvest.py`, and
   `constraints.packages` adds `debate_core.retrieval`.
5. **Wiring** (`v1-e06-t02` / `v1-e06-t06`): build the Crossref client and file cache in the
   composition root. The doctor and installation tests' pinned integration lists change then.
6. **Org names in the short cite** (`v1-e06-t03`). A JSON-LD or Crossref organization author ("Synthetic
   Consortium") gives "Consortium" as its last name, because the cite cannot tell a person from an
   organization. Format profiles may want the name whole.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-26

**Notes:**

A careful first cut of the cite: every field carries where it came from, nothing is inferred, and
what the platform did not retrieve is never verified.
1. **ac1 to ac5 and every node pass.**
   * The expected JSON was written by hand before the service existed.
   * Each node was run red against a skeleton first. ac5 was red alone, with everything else built.
   * The `page-metadata` node passes at the path the PM ruled. The PM amends its output and command
     in the next batch.
2. **Mutants: 22, all caught.** They cover every precedence step, the verified rule, the credential
   rules, the student-edit rule and the cache. The one that was first left unplanted, after ruff
   reformatted its target, was rewritten and caught.
3. **The rulings of 2026-10-26 are applied as written.** The harvester and its test are in
   `debate_core.retrieval`. The accessed date and the canonical-less URL are `heuristic`. Organization
   authors and an emptied field go to `v1-e06-t02`, and
   `test_a_field_the_student_emptied_is_derived_again` is the test t02 will turn.
4. **The shared JSON-LD walk (`cac099f`) is accepted.** It is its own commit, removes two copies,
   and passed `tests/retrieval` and the HTML extractor's tests with no expectation edited. The PM
   adds `debate_core.retrieval` to `constraints.packages` in the next batch.
5. **Deviations 2 and 3 accepted.** The fixtures are synthetic, under the E04 amendment, with one
   new journal landing page and t04's pages unchanged. The PDF and USER_SUPPLIED cases pin the
   provenance rule.
6. **Decisions accepted:**
   * verification only for publisher-retrieved snapshots, Crossref included;
   * USER_SUPPLIED text never parsed as HTML;
   * dates used only to the day, never completed, with ambiguous all-number dates refused;
   * the cite prints the day the source named;
   * credentials verbatim;
   * the student-edit rule only on a card with an `edit_cite` entry;
   * found works cached and failures not, with the contact email masked in httpx's log line.
7. **Follow-up 6 (an organization's name in the short cite)** joins the PM's `v1-e06-t02`
   amendment on organization authors. Once an author is marked as an organization, the short cite
   can keep its name whole. `v1-e06-t03` keeps team conventions.
8. **Follow-up 5 (wiring)** stays with `v1-e06-t02` or `v1-e06-t06`, as agreed.
9. **The affected set** (200 files, and the whole selection after the `pyproject.toml` edit) is left
   to the PR's `ci` under agreement 10. The changed modules' tests and the always-run list passed
   (1,620), and the static checks are clean. The planted imports broke the matching contracts.

No re-review is needed. The Goal is `Succeeded`, so the PR merges in full.
