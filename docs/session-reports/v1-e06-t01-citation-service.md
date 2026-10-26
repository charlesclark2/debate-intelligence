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

Three things to look at first, all in **Deviations** and **Decisions**: the harvester lives in
`debate_core.retrieval`, not `debate_core.evidence`, because the layers contract forces it; the
accessed date and the retrieved-URL fallback are recorded as `heuristic`, because no
`CitationFieldSource` names the platform's own retrieval record; and an organization-issued page
with no named author (the government fixture) can never have a fully verified cite under E02's
required fields.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `citation-model` | Done (already present) | `domain/citation.py` already held `CitationField[T]` (value, source, verified, raw), `Citation` and `is_fully_verified` from E02. Nothing was changed. |
| `page-metadata` | Done | `debate_core/retrieval/citation_harvest.py` (see Deviations for the package), on the shared JSON-LD walk `retrieval/json_ld.py`. Red: 30 failed, 14 passed against a skeleton (`b5f3ff0`); green: 45 passed. |
| `crossref-doi` | Done | Port `application/ports/doi_metadata.py`; adapter `integrations/crossref_doi.py`; synthetic respx answer. Red: 22 failed, 3 passed (`4f0c32e`); green: 25 passed. |
| `merge-and-format` | Done | `application/citation_service.py`. Red: 74 failed, 7 passed (`602e565`). ac5 red with everything else implemented: 3 failed, 78 passed (`dfc7f31`); green: 81 passed (`82e339e`). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: each fixture page (news, think tank, government, journal) has every field's value, source and verified flag as its expected JSON | PASS | `uv run pytest packages/debate_core/tests/application/test_citation_service.py` → 81 passed. `test_every_cite_field_has_the_value_source_and_flag_the_fixture_expects` runs the four kinds plus an open-access PDF and a USER_SUPPLIED case, against `tests/fixtures/citation/<case>.expected.json`, written by hand before the service existed. |
| ac2: a DOI is fetched once, cached by DOI and preferred for title, container, date and authors; failures degrade without raising | PASS | Same run: `test_a_doi_is_looked_up_once_however_many_times_its_cite_is_resolved` (1 request for 3 resolutions over two snapshots), `test_crossref_is_preferred_to_the_pages_own_meta_tags`, `test_crossref_wins_over_every_page_source`, and degradation on ConnectError, ReadTimeout, 500, 429, non-JSON, a failed envelope and 404 (`PAGE_METADATA_OF_THE_JOURNAL`, written by hand). `test_crossref_doi.py` → 25 passed: the file cache outlives the client, an unreadable cache file is refetched, a failure caches nothing. |
| ac3: credentials only from an explicit bio, JSON-LD `jobTitle`/`affiliation` or Crossref affiliation; otherwise missing with no qualification in the cite | PASS | `test_citation_harvest.py` → 45 passed: no credential from a byline's job title (the news page's "Science Correspondent"), from `citation_author_institution`, from a `description`, or from a bio naming no author. `test_citation_service.py`: Crossref affiliations, Crossref over a bio, a deposit with no affiliation leaving the bio, and a news cite with no parenthetical. |
| ac4: `format_cite` gives the short cite ("Smith 26") and the full line with accessed date, and flags unverified fields | PASS | `test_each_fixture_cite_formats_as_the_fixture_expects` (six cases, hand-written lines), plus last-name, "et al.", "ND", no-author, stated-day and provenance-note cases. `FormattedCite.unverified_fields` / `missing_fields`. |
| ac5: a student's changed field is verified on re-resolution only when it equals the derived value; otherwise kept, unverified and marked | PASS | Run red first: with `keep_student_edits` overwriting, 3 failed, 78 passed (`dfc7f31`). Green: 81 passed (`82e339e`). Tested end to end through `CardEditService` and the edit log: a differing value kept and named in `student_fields`; a value equal to the derivation verified, after which the card verifies again; a value equal to a heuristic stays unverified; only changed fields kept; a never-edited card takes the derived cite whole. |
| Node `citation-model`: `artifact_exists` `domain/citation.py` contains `class CitationField` | PASS | `grep -c "class CitationField" packages/debate_core/src/debate_core/domain/citation.py` → 1 |
| Node `page-metadata`: `uv run pytest packages/debate_core/tests/evidence/test_citation_harvest.py` | PASS | 45 passed in 1.43s (the file is at the spec's path; see Deviations) |
| Node `crossref-doi`: `uv run pytest packages/debate_core/tests/integrations/test_crossref_doi.py` | PASS | 25 passed in 1.37s |
| Node `merge-and-format`: `uv run pytest packages/debate_core/tests/application/test_citation_service.py` | PASS | 81 passed in 1.88s |
| Node `merge-and-format`: `uv run pyright packages/debate_core` | PASS | 0 errors, 0 warnings, 0 informations (17.7 s) |
| Forbidden: LLM-generated or LLM-guessed author, credential, publication or date values | Holds | No model is called anywhere in the path; every value is a harvested string or a Crossref field. |
| Forbidden: marking a field verified when its only source is a heuristic | Holds | `_chosen` verifies only non-heuristic sources, and the domain validator refuses a verified heuristic. Mutant "verified: heuristic counts" caught (8 failed). |
| Forbidden: live Crossref or publisher calls in CI | Holds | respx and `httpx.MockTransport` only; pytest runs with `--disable-socket`. |

### Mutation run (agreement 8)

22 mutants over `citation_service.py`, `citation_harvest.py` and `crossref_doi.py`. Each was planted
on a committed tree, run against the three test files (`-n 0 -p no:randomly`), and restored with
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
| `.venv/bin/python -m pytest -m "not slow and not live"` over the changed modules' tests and the always-run list: `tests/retrieval/`, `test_citation_harvest.py`, `test_citation_service.py`, `test_article_service.py`, `test_card_edit_service.py`, `test_port_conformance.py`, `test_snapshot_service.py`, `test_html_extractor.py`, `test_pdf_extractor.py`, `tests/integration/test_fetch_cli.py`, `tests/fixtures/test_cassette_hygiene.py`, `test_doctor.py`, `test_installation.py`, `test_app.py`, `test_help_rendering.py`, `tests/architecture/`, `tests/specs/` | 1620 passed in 23.79s |
| The httpx-logger suites in one process, `-n 0 -p no:randomly`: `integrations/discovery/`, `test_http_fetcher.py`, `integrations/opencaselist/`, then `test_crossref_doi.py`, `test_citation_service.py`; and again in the reverse order | 825 passed (3.83 s); 825 passed (1.92 s) |
| `uv run --frozen ruff check .` / `ruff format --check .` | All checks passed / 1461 files already formatted |
| `uv run --frozen pyright` (whole repo, as CI) | 0 errors, 0 warnings, 0 informations |
| `uv run --frozen lint-imports` | Contracts: 18 kept, 0 broken. Planted `import lxml` and `import keyring` in `crossref_doi.py` broke the two matching contracts, naming the module, and were removed. |
| `uv run --frozen python scripts/check_thin_handlers.py` | OK: 66 handlers within 25 statements |
| `uv run scripts/validate_specs.py` / `--require-succeeded v1-e06-t01-citation-service` | OK: 469 files, 40 epics, 407 tasks, 22 releases / Succeeded |
| `uv run --frozen python scripts/docs_index.py --check-descriptions` (after this report was written) | All 53 indexed documents under docs/ have a description |
| `uv run --frozen python scripts/check_command_blocks.py --base origin/dev` | OK: no `#` comments in 504 shell code blocks in 180 Markdown files (1 session report changed) |
| `pytest tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py` | 191 passed in 2.77s |

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
* **Tests**: `tests/evidence/test_citation_harvest.py`, `tests/integrations/test_crossref_doi.py`,
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
   **The test file stays at the spec's path**, `packages/debate_core/tests/evidence/test_citation_harvest.py`,
   so the `page-metadata` node's command runs as written. Its docstring says why. If the PM amends
   the node's output to `retrieval/citation_harvest.py`, the test belongs in `tests/retrieval/`, and
   moving it is a one-line `git mv`.
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
  cite has an unverified `canonical_url`, and a card cut from a PDF cannot reach VERIFIED. This is a
  question for the PM (Follow-up work 1).
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
  never resolved, so it is derived again. Saving and re-verifying the card is the caller's step
  (CardService, `v1-e06-t02`), as the service returns a `CitationResolution`.
* **Crossref caching.** Found works are cached in `<storage.data_dir>/crossref/<sha256(doi)>.json`.
  A 404 and a failure are not cached, so they are asked again next time. The contact email goes as
  `mailto=` and is registered with the discovery log filter, so httpx's request line carries it
  masked (`test_httpx_logs_the_request_without_the_contact_email`). Errors chain no exception.
* **Short cite.** The first author's last name, with " et al." for more than one author. Without an
  author it falls back to the publication, then the title, then `[no author]`; without a date it
  ends "ND". "Smith, Jane" and "Jane Smith Jr." both give Smith. Team conventions are `v1-e06-t03`'s.
* **No composition-root wiring.** No command uses the service yet, so `debate_cli.container` is
  unchanged, and so are the pinned integration lists in `test_doctor.py` and `test_installation.py`.
  `cut` (`v1-e06-t06`) or CardService (`v1-e06-t02`) builds `crossref_doi_client(...)` over a
  `FileDoiCache(data_dir / CROSSREF_CACHE_DIRECTORY)`.

## Operator follow-ups

None. No command in this session needed the network, credentials or more than two minutes.

## Follow-up work

1. **A source for the platform's own retrieval record** (PM; an E02 domain change). Add a
   `CitationFieldSource` such as `retrieval` for the accessed date and the retrieved URL. It would be
   verified for PUBLISHER_RETRIEVED snapshots, and a PDF's or a canonical-less page's URL would stop
   holding cards UNVERIFIED. It changes the enum, the schema export and ac1's list, so it is not
   this task's to make.
2. **Organization-issued sources** (PM, `v1-e06-t02`). A press release that names no person has
   `authors` missing, and `authors` is a required field (`REQUIRED_CITATION_FIELDS`), so its card can
   never be VERIFIED. Debate cites usually give the agency as the author. Whether a publication may
   stand in for an author is a domain decision.
3. **Wiring** (`v1-e06-t02` / `v1-e06-t06`): build the Crossref client and file cache in the
   composition root. The doctor and installation tests' pinned integration lists change then.
4. **Org names in the short cite** (`v1-e06-t03`). A JSON-LD or Crossref organization author ("Synthetic
   Consortium") gives "Consortium" as its last name, because the cite cannot tell a person from an
   organization. Format profiles may want the name whole.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
