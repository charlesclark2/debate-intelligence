# Session report: v1-e08-t02-normalize-dedupe

| | |
|---|---|
| Task | `v1-e08-t02-normalize-dedupe` — Normalization and deduplication |
| Spec | [`plan_specs/v1/e08-research-workflows/t02-normalize-dedupe.yaml`](../../plan_specs/v1/e08-research-workflows/t02-normalize-dedupe.yaml) |
| Epic / release | `v1-e08-research-workflows` / `v1.4` |
| Branch | `task/v1-e08-t02-normalize-dedupe` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`DedupeStage` is the normalize stage of `FederatedSearchService`. It collapses `SearchState.candidates`
into a new `SearchState.merged_candidates` field (default `()`), one `MergedCandidate` per source. It
matches in the spec's order:

1. DOI;
2. canonical URL (the E04 canonicalizer, used only as an identity key);
3. provider ids (arXiv, PMID, OpenAlex, Semantic Scholar);
4. title, gated by the first author's surname and the date.

Two groups whose identifiers disagree are never joined, which is what keeps a preprint apart from its
published version. Every merged field comes from one table, `FIELD_PRECEDENCE`, and `MergedCandidate`
refuses a value whose provider is missing or untrue. On the 51 hand-labelled pairs there are **0 false
merges out of 21** and **recall is 27/30 (90.0%)**. The three misses are the three pairs labelled as
known misses before any code was written.

**Look first at Deviation 1.** The title rule has no similarity threshold. Every threshold I measured,
token-set ratio included, either scores a different work at 1.000 or rejects a dropped subtitle. The
rule is equality after deterministic normalization, and the measurements are below. All four criteria
pass as written, so the Goal is `Succeeded`. The deviations change spec descriptions, not criteria.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `labeled-pairs` | Done | `tests/fixtures/dedupe/pairs.json`: 51 pairs (30 same, 21 different), every record and answer written by hand before the code (commit `3a725a5`). Synthetic records: no provider fixtures exist yet (Deviation 3). |
| `exact-keys` | Done | Union-find over DOI, canonical URL and provider ids, with the identifier guard. Module named `federated_dedupe.py` per the PM's naming ruling; spec amended (`d0c0a06`). |
| `fuzzy-match` | Done | Title agreement after normalization, gated by first-author surname and date (Deviation 1). Standard library only, no new dependency. |
| `merge-precedence` | Done | `FIELD_PRECEDENCE`, `merge_group`, the provenance validator, and `DedupeStage` in the normalize slot. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the same paper from OpenAlex, Crossref and Semantic Scholar merges into one MergedCandidate with three provider sources | PASS | `test_exact_the_same_paper_from_openalex_crossref_and_semantic_scholar_is_one_merged_candidate` over `tests/fixtures/dedupe/one_paper_three_providers.json`. Every merged value and its source are written out by hand. `providers == ("openalex", "crossref", "semantic_scholar")`, matched on DOI. |
| ac2: a story syndicated with utm_* and AMP paths merges by canonical URL; near-identical headlines by different authors do not | PASS | `test_exact_canonical_url_merges_a_story_shared_with_utm_parameters_and_an_amp_path` (three records, one merge, `matched_on == (CANONICAL_URL,)`). `test_fuzzy_title_needs_the_first_authors_surname_to_agree`. Eleven syndicated-news pairs and three near-identical-headline pairs in the labelled set. |
| ac3: each merged field records its source provider; precedence is table-driven and unit tested | PASS | `test_precedence_rule_picks_the_first_provider_in_its_row` (13 fields) and `..._falls_back_to_the_next_provider...` (11 fields) against a hand-written `EXPECTED_PRECEDENCE`. The table names every configured provider once per row. Five validator tests refuse a value with no source, a source with no value, a source that is not a member, a value the source did not supply, and an unknown field. |
| ac4: at least 40 labelled pairs, zero false merges, at least 90% recall | PASS | `uv run pytest packages/debate_core/tests/application/test_federated_dedupe.py -k labeled` → `4 passed`. Printed: `labelled pairs: 51 (30 same, 21 different)`, `false merges: 0 []`, `recall: 27/30 = 90.0%`. A batch test dedupes all 102 records at once and agrees with each pair alone. |
| Node `labeled-pairs`: dedupe pairs exist | PASS | `ls tests/fixtures/dedupe/pairs.json` → present. |
| Node `exact-keys`: exact-key dedupe tests pass | PASS | `uv run pytest packages/debate_core/tests/application/test_federated_dedupe.py -k exact` → `22 passed in 4.13s` |
| Node `fuzzy-match`: labelled pair precision/recall test passes | PASS | `uv run pytest packages/debate_core/tests/application/test_federated_dedupe.py -k labeled` → `4 passed in 1.85s` |
| Node `merge-precedence`: full dedupe module passes | PASS | `uv run pytest packages/debate_core/tests/application/test_federated_dedupe.py` → `134 passed in 2.37s` |

### Red run, then green

* **Red** (commit `84559f1`). The skeleton keeps every candidate alone, validates nothing, has an
  empty precedence table, and its title and surname helpers return nothing. Result: `93 failed, 33
  passed`.
  * The 33 passes are explained: the must-not-merge and must-disagree cases (a skeleton that merges
    nothing cannot merge wrongly), the empty-title and unreadable-name cases, the labelled file's
    shape, first-record-wins within one provider, and the two network guards.
  * Two failures were bad test data (`10.1/x` is not a DOI). I fixed them before recording the red.
* **First green run.** It found a real gap that the hand-written case caught: "organisational" ends in
  `-isational`, which the spelling table did not cover. That was also the one unlabelled miss in the
  pairs. Two test cases contradicted the design and were corrected:
  * "Reply to critics" has 3 words, the minimum, so it now reads "Book review";
  * a title can never be absent, so the title fallback case was invalid, as the url one already was.
* **Coverage** of `federated_dedupe.py`: 100% of lines and branches (`--cov-branch`). An unreachable
  `published_at` guard became reachable once each gate lived in one place (see the next section).

### Mutation run (21 mutants, capped as asked)

Each mutant ran `test_federated_dedupe.py` alone (`-n 0`, fresh `HYPOTHESIS_STORAGE_DIRECTORY`, though
the file has no properties). The runner restored the module from saved bytes and checked them.

Mutating first found something about the code. The year was checked twice, by the block key
`(surname, year)` and again in the date gate, so a fault in either was hidden by the other. I
restructured so each gate lives in one place before counting mutants (commit `6f6c85a`).

| # | Mutant | Result |
|---|---|---|
| 1 | Author gate: every record in one block | caught (4) |
| 2 | Author gate: records with no author share a block | caught (2) at first, by canonical-URL tests only; caught (4) after the change below, including `..._never_merges_on_title_alone[both-records-no-author]` |
| 3 | Surname: comma form reads the given name | caught (11) |
| 4 | Surname: first word instead of last | caught (13) |
| 5 | Surname: initials kept ("Rivera AM") | caught (1) |
| 6 | Date gate: scholarly year not compared | caught (2) |
| 7 | Date gate: day not compared outside scholarship | caught (2) |
| 8 | Date gate: site not compared outside scholarship | caught (3) |
| 9 | Date gate: either record scholarly is enough for the year rule | caught (2) |
| 10 | Precedence: title row in the indexes-first order | caught (2) |
| 11 | Precedence: `published_at` prefers the feed to Crossref | caught (1) |
| 12 | Precedence: `url` prefers Crossref to the feed | caught (1) |
| 13 | Precedence: a provider outside the table ranks first | caught (1) |
| 14 | Precedence: the later record of one provider wins | caught (1) |
| 15 | Precedence: source type `other` counts as a value | caught (2) |
| 16 | Canonical URL: raw URL used as the key | caught (6) |
| 17 | Canonical URL: provider's own canonical URL ignored | caught (1) |
| 18 | Canonical URL: a front page is a key | caught (2) |
| 19 | Canonical URL: a front page with a query is not a key either | **survived**, then caught (1) after the change below |
| 20 | Identifier guard: disagreeing identifiers joined | caught (8) |
| 21 | Identifier guard: an arXiv-only record carries no arXiv DOI | caught (2) |

First pass: 20 of 21. Both weak spots got a test (commit `2544656`):

* **Mutant 19** survived because no test had a front page whose query names the article. WordPress
  serves posts at `/?p=1234`. `test_exact_canonical_url_of_a_front_page_whose_query_selects_the_article_is_a_key`
  now catches it.
* **Mutant 2** was caught only by accident. The forbidden "title alone" test stripped the author from
  one record, never both. It now runs with the field missing on one record and on both, and its
  `both-records-no-author` case fails alone against mutant 2. I checked that by applying the mutant by
  hand.

Final count: 21 of 21 caught.

### Closing checks

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` | `30 of 373 test files (8.0%) chosen in 5.7 s from 7 changed files` |
| The same selection with CI's markers. `--run` starts pytest as a child, so I ran its exact command with the alarm on the interpreter (agreement 10): `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -n auto -m "not slow and not live" <the 30 files> -q -p no:randomly` | `1423 passed in 39.07s` |
| `uv run --frozen ruff format --check .` | `1037 files already formatted` |
| `uv run --frozen ruff check .` | `All checks passed!` |
| `.venv/bin/python -m pyright packages/debate_core` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 13 kept, 0 broken.` |
| `uv run scripts/validate_specs.py` (after `set-phase ... Succeeded`) | `OK: 404 files, 39 epics, 344 tasks, 21 releases`; `--require-succeeded v1-e08-t02-normalize-dedupe` → `Succeeded` |
| `uv run python scripts/check_links.py` | `OK: 1929 relative links and anchors in 286 Markdown files` |
| `uv run python scripts/check_command_blocks.py --base origin/dev` | `OK: no # comments in 333 shell code blocks in 133 Markdown files (1 session reports changed since origin/dev)` |
| `packages/debate_core/tests/application/test_federated_search.py` (t01's suite, since `SearchState` changed) | `40 passed` |

## Files changed

* `packages/debate_core/src/debate_core/application/federated_dedupe.py` (new): matching, title and
  surname normalization, `FIELD_PRECEDENCE`, `MergedCandidate`, `merge_group`, `merge_candidates` and
  `DedupeStage`.
* `packages/debate_core/src/debate_core/application/federated_search_types.py`: `SearchState`
  gains `merged_candidates` (default `()`) and `evolve` takes it, per the spec's amendment. Nothing
  else in t01's orchestration changed. The `MergedCandidate` import is for type checking only, which
  avoids an import cycle.
* `packages/debate_core/tests/application/test_federated_dedupe.py` (new): 134 tests.
* `tests/fixtures/dedupe/pairs.json` and `one_paper_three_providers.json` (new): hand-written
  fixtures.
* `plan_specs/v1/e08-research-workflows/t02-normalize-dedupe.yaml`: the PM's naming ruling and the
  standard-library ruling, each with a `PM ruling 2026-10-21` comment, then the Goal phase.

## Deviations from the spec

1. **No similarity threshold in the title rule.** The Goal description says "fuzzy title similarity
   (normalized token-set ratio above a threshold)", and the `fuzzy-match` node says "threshold tuned
   on the labeled pairs". Instead, titles agree when their normalized words are equal, in order:
   * the normalization absorbs case, accents, HTML entities and JATS markup, punctuation, `&`,
     in-word hyphens and apostrophes, abbreviation stops, and British spellings (fixed table);
   * a subtitle may be dropped on one side only;
   * there must be at least 3 words (`MIN_TITLE_TOKENS`, the one tuned number).

   The reason is measured. Using stdlib implementations of rapidfuzz's definitions:

   | | Pair | token-set | token-sort |
   |---|---|---|---|
   | same | Trade Wars and U.S. Farm Income / Trade wars and US farm income | 0.949 | 0.949 |
   | same | Arctic methane feedbacks: a review of the evidence / Arctic methane feedbacks | 1.000 | 0.658 |
   | same | Migration & Labour Markets in the European Union / Migration and labour markets in the European Union | 1.000 | 0.958 |
   | same | Organisational behaviour and climate adaptation in coastal cities / Organizational behavior and ... | 0.977 | 0.977 |
   | different | The case for a carbon tax / The case for a carbon tax in Canada | 1.000 | 0.833 |
   | different | Carbon tax effects on employment / ... on emissions in British Columbia | 0.893 | 0.893 |
   | different | Tariff pass-through to consumer prices, 2018-2020 / ..., 2018-2022 | 0.979 | 0.979 |
   | different | Nuclear deterrence after the Cold War: Part 1 / ...: Part 2 | 0.977 | 0.977 |
   | different | Immigration policy in Europe / Emigration policy in Europe | 0.945 | 0.727 |
   | different | Election security in Georgia / Selection security in Georgia | 0.982 | 0.667 |
   | different | Man bites dog in Ohio / Dog bites man in Ohio | 1.000 | 1.000 |

   No token-set threshold keeps the lowest "same" pair (0.949) and refuses the "different" ones
   (up to 1.000). The spec's measure scores any title 1.000 against a longer one that contains it. A
   per-word ratio for spelling variants fails the same way: police/policy 0.83, immigration/emigration
   0.857. Every difference I found between two providers' copies of one title is one of the
   normalizations above, so equality after them loses no labelled positive, and the bar is zero
   false merges. The gates still apply, the forbidden case is tested (a title alone never merges),
   and no dependency was added. **The PM should amend the Goal description and the node's
   "threshold tuned" wording, or rule otherwise.**
2. **The date gate is stricter than "year" outside scholarship.** Two scholarly records need the
   same year. Any other pair needs the same UTC day and the same site (registrable domain).
   * The day: recurring headlines ("Live updates: midterm election results", a yearly preview
     column) repeat within a year.
   * The site: the same wire story on two outlets is two sources. A card cites the outlet it was
     read at, and each outlet's page is reached, and may be paywalled, on its own.
   * A paper and a news piece with its title never title-match, because the site rule applies
     unless both records are scholarly.
3. **The labelled pairs are not "from recorded provider fixtures".** The `labeled-pairs` node asks
   for that, but no adapter has merged yet (v1-e07-t02 is running) and there are none to take.
   Every record is a hand-written `CandidateResult` in the shape each adapter's spec describes, as
   the PM's note asked ("written by hand, with expected answers by hand"), and synthetic, as the
   corpus policy requires.
4. **No citation-count row in the precedence table.** The spec's example lists "OpenAlex/S2 for
   citation counts", but `CandidateResult` has no citation-count field, so there is nothing to merge.
   Adding one is a change to `debate_core.domain.discovery`, outside this task's packages and in the
   adapters' path. See Follow-up work, since t03 needs it.

## Decisions and assumptions

* **Where `MergedCandidate` lives: the application layer**, in `federated_dedupe.py`, because it
  lives only in memory. A search stores its raw per-provider results (`ProviderStatus`) and its
  ranking (`SearchResult`). Merged candidates are a pure function of the first: replaying the stored
  results through `DedupeStage` gives them back. Storing them as well would keep a second copy that
  could disagree with the rules that made them. If a later task persists them, the model moves to
  `debate_core.domain.discovery`, as `ProviderStatus` did.
* **Preprints and published versions stay apart** whenever the records can tell them apart. They are
  different versions: text, pagination and peer-review status differ, and a card cites the version it
  was read from. Merging would let one version's venue, date and peer-reviewed status stand for the
  other in ranking.
  * A record with an arXiv id and no DOI carries its arXiv DOI (`10.48550/arxiv.<id>`) for the
    identifier guard. So an arXiv preprint never joins a record with a journal DOI, even when
    Semantic Scholar's published record lists the preprint's arXiv id.
  * bioRxiv, medRxiv and SSRN mint their own DOIs, which differ from the journal's.
  * When one record has no identifier at all, the versions cannot be told apart, and the title rule
    may join them.
* **The identifier guard** applies to every rule. Two groups never join while they hold different
  DOIs, arXiv ids, PMIDs, OpenAlex ids or Semantic Scholar ids. A missing identifier is not a
  different one. This also covers a journal-issue PDF shared by two articles.
* **A site's front page is not a URL key** (path `/` and no query): a local feed that links every item
  to its home page names the site. A front page whose query names the article (`/?p=1234`) is a key.
* **Identifiers are never read out of URLs.** A news story's URL can carry the DOI of the study it
  reports, and that would merge the story with the study.
* **Field precedence**: one table, every configured provider once per row. Precedence matters only for
  the provider a field is credited to: inside a group the identifiers cannot differ.

  | Field | Order | Why |
  |---|---|---|
  | title, authors, publication, source_type, DOI | crossref, openalex, semantic_scholar, rss, gdelt | Crossref holds what the publisher deposited; the indexes rebuild it. For news, the publisher's feed before GDELT's crawl. |
  | published_at | crossref, rss, openalex, semantic_scholar, gdelt | The spec's "Crossref for dates, publisher feed for news dates". GDELT's date is when GDELT saw the story. |
  | url | rss, crossref, openalex, semantic_scholar, gdelt | The publisher's own link: a feed item's link, then the DOI resolver, then OpenAlex's landing page. Semantic Scholar's URL is its own index page, and GDELT's is whatever it crawled, AMP and tracking included. |
  | snippet, open_access_url, PMID, OpenAlex id | openalex, semantic_scholar, crossref, rss, gdelt | The spec's "OpenAlex/S2 for OA links": abstracts and open copies are what the indexes add. |
  | Semantic Scholar id, arXiv id | semantic_scholar, openalex, crossref, rss, gdelt | Each index first for its own id; Semantic Scholar lists arXiv ids. |

  Rules around the table:
  * `canonical_url` is the canonical form of the merged `url`, from the same provider.
  * A provider outside the table ranks after all five.
  * Between two records from one provider, the earlier wins.
  * Empty values give way to the next record: `None`, no authors, a blank snippet, source type
    `other`.
* **Surnames.** The key is the last word of the surname. "Rivera, Ana", "Ana Rivera", "A. Rivera",
  "Rivera AM" and "RIVERA, ANA" all give `rivera`; "Hanna-Attisha" gives `attisha`; "van Beethoven"
  gives `beethoven`. Known limits:
  * a given-name-first double surname ("Ana María Rivera Gómez" gives `gomez`) is a labelled miss;
  * a surname written in capitals after the given name ("Wei LI") reads as initials.
* **The orchestration is unchanged.** `FederatedSearchService`'s `normalize` default stays
  `PassThroughStage`, and a test plugs `DedupeStage` in through the constructor. Making it the default
  is wiring, which is t05's (the container).
* **Known limit:** a 3-word generic title ("Reply to critics") by one first author in one year, with
  no identifiers on either record, would merge. Shorter generic titles ("Introduction", "Book review")
  are below the minimum.

## Operator follow-ups

None. The affected set ran in 39 s, and no shared test ground changed.

## Follow-up work

* **E07 adapters (v1-e07-t02 OpenAlex, v1-e07-t04 Semantic Scholar):** both specs map citation counts,
  but `CandidateResult` has no field for them, and none for peer review or open-access status. t03
  needs all three. When one is added, `FIELD_PRECEDENCE` gains a row (OpenAlex, then Semantic
  Scholar), and the precedence tests gain a row in `EXPECTED_PRECEDENCE`.
* **v1-e08-t03 (ranking):** reads `state.merged_candidates`. `SearchOutcome` does not carry them, and
  `SearchResult` holds only an `article_id`. Somewhere between t03 and t05, a merged candidate has to
  become an `Article` (ArticleService registers by canonical URL) before its result can be stored. t03
  ties are broken by `canonical_url`, which can be `None` for a URL with no canonical form. Fall back
  to `url`.
* **v1-e08-t05 (search command):** pass `normalize=DedupeStage()` when building
  `FederatedSearchService` in the container.
* **Google News RSS (v1-e07-t05):** its encoded `/rss/articles/CBMi...` links and its
  " - Publisher" title suffix leave a Google News item unmatchable to the publisher's own item (a
  labelled miss). If the adapter can take the publisher URL from the feed's `<source url>` element or
  the item itself, the canonical-URL rule will merge them.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
