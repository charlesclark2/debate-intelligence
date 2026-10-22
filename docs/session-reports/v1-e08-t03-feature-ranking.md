# Session report: v1-e08-t03-feature-ranking

| | |
|---|---|
| Task | `v1-e08-t03-feature-ranking` — Explainable feature ranking |
| Spec | [`plan_specs/v1/e08-research-workflows/t03-feature-ranking.yaml`](../../plan_specs/v1/e08-research-workflows/t03-feature-ranking.yaml) |
| Epic / release | `v1-e08-research-workflows` / `v1.4` |
| Branch | `task/v1-e08-t03-feature-ranking` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`FederatedRankStage` is the rank stage of `FederatedSearchService`. It orders
`SearchState.merged_candidates` into a new `SearchState.ranked_candidates`. Each `RankedCandidate`
carries:

* seven named features, each between 0 and 1 or `None` for unknown: bm25, recency, source_type,
  peer_reviewed, open_access, citations, provider_agreement;
* each feature's contribution (weight × value);
* the total score;
* the raw BM25;
* an explanation such as "strong term match, published 3 months ago, scholarly source, open
  access".

Every number comes from `config/federated_ranking.yaml`. No model is called and nothing is fetched.
The ranking reads no publisher list: the only filters are the user's `source_types` and
`max_results`.

Storage follows the PM's option A:

* `search_result_for` builds the stored `SearchResult`;
* `SearchResult.source_quality_features` is now `dict[str, float | None]`, so an unknown feature is
  stored as unknown;
* `state.results` stays empty until v1-e08-t05 registers ranked candidates as Articles.

On the coach's labels, mean nDCG@10 is **0.711 ranked against 0.607 in raw provider order**, so ac4
passes. **Look first at the per-query line for LD**: there the ranking is very slightly lower
(0.579 against 0.583).

All four Goal criteria pass, and the Goal is **Succeeded** by the PM's ruling of 2026-10-22. ac4 is
read as the mean over the three queries. The coach's approving review of the pull request is the
merge condition for the custom criterion.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `features` | Done | `federated_ranking_features.py`: the seven features, BM25 over the result set, and a documented tokenizer that reuses dedupe's text normalization. |
| `scorer-explainer` | Done | `federated_ranking.py` and `config/federated_ranking.yaml`: the table loader and its refusals, the weighted score, the tie order, explanations, `FederatedRankStage` and `search_result_for`. |
| `relevance-check` | Done | `tests/fixtures/federated_ranking/labeled_queries.json` (path per the PM's FYI ruling) and `labelling_sheet.md`. The coach labelled all three queries in this session; the coach's approving review of the pull request is required before merge (PM ruling 2026-10-22). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: each ranked SearchResult carries rank, total score, the named feature vector (seven names) and an explanation | PASS | `test_score_search_result_for_carries_rank_scores_the_vector_the_explanation_and_providers`: all seven names in order, `peer_reviewed` None, raw BM25 as `lexical_score`. `test_score_search_result_for_a_stored_ranking_comes_back_as_built` round-trips through the in-memory repository. The new contract test `test_an_unknown_feature_comes_back_as_none_not_zero_or_missing` passes for `TestInMemorySearchRepository` and `TestSqliteSearchRepository`. Per the PM's ruling, real searches store results once v1-e08-t05 registers Articles. |
| ac2: deterministic; ties broken by published_at, then canonical URL | PASS | `test_score_identical_inputs_and_config_give_identical_order_whatever_the_input_order`; `..._ties_break_by_published_at_newest_first_with_undated_last`; `..._ties_then_break_by_canonical_url_ascending`; `..._ties_fall_back_to_the_url_when_there_is_no_canonical_form`. |
| ac3: changing a weight in config/federated_ranking.yaml changes ordering on a fixture set without code changes | PASS | `test_score_changing_a_weight_in_the_yaml_changes_the_order_without_code_changes` copies the committed table, edits one line (`recency: 0.15` → `0.6`), and the order of two results reverses. |
| ac4: on a coach-labelled fixture of 3 queries, nDCG@10 not lower than raw provider order | PASS (mean, as the PM ruled 2026-10-22; per-query values are reported, not gated) | `uv run pytest packages/debate_core/tests/application/test_federated_ranking.py -k relevance -s` → `3 passed`, printing the per-query table below. |
| Node `features`: feature tests pass | PASS | `uv run pytest packages/debate_core/tests/application/test_federated_ranking.py -k feature` → `60 passed in 1.96s` |
| Node `scorer-explainer`: scorer and explanation tests pass | PASS | `uv run pytest packages/debate_core/tests/application/test_federated_ranking.py -k "score or explain"` → `57 passed in 1.86s` |
| Node `relevance-check`: full ranking module passes | PASS | `uv run pytest packages/debate_core/tests/application/test_federated_ranking.py` → `128 passed in 1.82s` |
| Node `relevance-check`: coach labels relevance for the Policy, LD and PF current topics and approves it in the PR | PASS at merge | The coach's approving review of this pull request, naming `tests/fixtures/federated_ranking/labeled_queries.json`, is required before merge (PM ruling 2026-10-22). The labels were recorded on 2026-10-22 in commit `f237a0d`, before the ranking was run over the set. The queries are stand-ins for the current topics (Deviation 4). |

### ac4, per query (the coach's labels, by count)

| Query | Relevant | nDCG@10, raw provider order | nDCG@10, ranked |
|---|---|---|---|
| Policy: "carbon border adjustment trade retaliation" | 7 of 14 | 0.803 | 0.908 |
| LD: "universal basic income labor force participation" | 7 of 14 | 0.583 | 0.579 |
| PF: "nuclear power expansion grid reliability" | 3 of 13 | 0.437 | 0.645 |
| **Mean** | | **0.607** | **0.711** |

* **"Raw provider order"** is the merged candidates' first appearance in fan-out order (openalex,
  crossref, semantic_scholar, rss), per the PM's FYI ruling.
* **The ranking uses the committed table unchanged.** I did not tune a weight after seeing these
  numbers.
* **The set is weak evidence.** It is synthetic, and I wrote both the candidates and the ranker,
  though the candidates and each provider's order were written before the ranker was run over
  them. The records follow each provider's plausible order: the indexes by their own relevance,
  feeds newest first. Citation counts follow popularity, not relevance, so the most cited records
  are off-topic.
* **One label line to confirm.** The coach's PF line ended in a trailing comma (`F02, F04, F06, `).
  It was recorded as those three items. **Confirmed by the coach on 2026-10-22: the PF line is F02,
  F04 and F06 and nothing more.**

### Red run, then green

* **Red** (commit `831dfe0`) ran against a skeleton with the real signatures that measures nothing,
  keeps input order, validates no table and explains nothing: `82 failed, 22 passed`.
  * The failures were missing values (None, 0, an empty explanation), tables not refused
    (`DID NOT RAISE`), filters not applied, and `KeyError`s from the empty feature dictionary.
  * The 22 passes are what such a skeleton satisfies: the unknown and zero cases, an empty filter,
    the committed table loading, the storage round trip, and the import and literal guards.
  * The peer-review tests also passed, because "unknown" is what the skeleton returns. Mutants 19
    and 20 below are their evidence.
* **First green run:** 104 passed. Seven scorer tests had names containing "feature", which put
  them in the `features` node's `-k feature` selection; they were renamed.
* **Citations and the open-access flag** went red after the sync: `10 failed, 9 passed` on the new
  tests, then green.
* **Coverage:** `federated_ranking_features.py` 100% of lines and branches.
  `federated_ranking.py` 98%; the two uncovered lines are the defensive "no phrase for feature"
  branch. I deleted the "peer-reviewed" phrase instead of keeping it untested, since no path can
  reach it while peer review is always unknown.

### Mutation run (20 mutants, the PM's four areas)

Each mutant was applied alone to the committed module, and `test_federated_ranking.py -k "not
relevance"` was run at `-n 0`. Every run had a fresh `HYPOTHESIS_STORAGE_DIRECTORY` (the file has no
properties) and `PYTHONDONTWRITEBYTECODE=1`. The modules were restored from saved bytes and checked
equal, and `git status` was clean after every batch.

| # | Area | Mutant | Result |
|---|---|---|---|
| 1 | weights | weight ignored (every known feature counts 1) | caught (21) |
| 2 | weights | bm25's weight used for every feature | caught (21) |
| 3 | weights | total leaves out the last feature | caught (1) |
| 4 | weights | unknown counts as 1 rather than nothing | caught (22) |
| 5 | weights | every source type valued 1 | caught (6) |
| 6 | weights | BM25 `k1` and `b` swapped | caught (1) |
| 7 | weights | half-life fixed at 90 days | **survived**, then caught (4) after the test below |
| 8 | ties | oldest first | caught (1) |
| 9 | ties | undated first | caught (1) |
| 10 | ties | URL instead of canonical URL | caught (1) |
| 11 | ties | no URL fallback | caught (1) |
| 12 | ties | lowest score first | caught (14) |
| 13 | ties | result cap applied before sorting | caught (1) |
| 14 | tokenizer | a hyphen joins words | caught (1) |
| 15 | tokenizer | possessive kept | caught (1) |
| 16 | tokenizer | no American spelling | caught (2) |
| 17 | tokenizer | abbreviation stops split words | caught (1) |
| 18 | tokenizer | document reads the title only | caught (1) |
| 19 | peer review | inferred from scholarship | caught (22) |
| 20 | peer review | unknown read as 0 ("not reviewed") | caught (8) |

* **Mutant 7 survived** because every test used a 90-day half-life. Two tests now vary it (commit
  `f1643d9`). I saw them pass unmutated before the final batch, which caught all 20.
* **The first batch reported mutant 7 as caught (1).** Two re-runs, one applied by hand, showed it
  surviving, and six random-order runs of the clean suite found nothing flaky. A plausible cause is
  bytecode cached across same-second rewrites, which is why the final batch disabled bytecode. The
  counts above are the final batch's.

### Closing checks

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` | 369 test files. The `SearchResult` change reaches the root conftest's imports, so the affected set is past the two-minute line. It is left to the PR's `ci` (agreement 10). |
| Instead: the test directories of what changed and the always-run list, with the alarm on the interpreter: `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -n auto -q -m "not slow and not live" packages/debate_core/tests/application packages/debate_core/tests/domain packages/debate_core/tests/contracts packages/debate_core/tests/integrations/local packages/debate_core/tests/testing tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py` | `4514 passed in 101.43s`; no pytest process left (`pgrep`) |
| Docs checks, since this report changed: `.venv/bin/python -m pytest -q tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py` | `162 passed in 1.87s` |
| `uv run --frozen ruff format --check .` | `1058 files already formatted` |
| `uv run --frozen ruff check .` | `All checks passed!` |
| `.venv/bin/python -m pyright packages/debate_core` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 13 kept, 0 broken.` |
| `uv run scripts/validate_specs.py` | `OK: 404 files, 39 epics, 344 tasks, 21 releases`; re-run after the Goal was set `Succeeded`, below |
| `uv run python scripts/check_links.py` | `OK: 1940 relative links and anchors in 291 Markdown files` |
| After the PM's four conditions (2026-10-22): `uv run scripts/validate_specs.py`; `--require-succeeded v1-e08-t03-feature-ranking`; `check_links.py`; `check_command_blocks.py --base origin/dev`; `.venv/bin/python -m pytest -q tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py tests/specs` | `OK: 404 files, 39 epics, 344 tasks, 21 releases`; `v1-e08-t03-feature-ranking: Succeeded`; `OK: 1940 relative links and anchors in 291 Markdown files`; `OK: no # comments in 334 shell code blocks`; `244 passed in 2.96s` |
| `uv run python scripts/check_command_blocks.py --base origin/dev` | `OK: no # comments in 334 shell code blocks in 135 Markdown files (1 session reports changed since origin/dev)` |

## Files changed

* `packages/debate_core/src/debate_core/application/federated_ranking_features.py` (new): the seven
  features, BM25 and the tokenizer.
* `packages/debate_core/src/debate_core/application/federated_ranking.py` (new): the table loader
  and refusals, `RankedCandidate`, the score, the order, explanations, `FederatedRankStage` and
  `search_result_for`.
* `config/federated_ranking.yaml` (new): the weight table, each number with its reason.
* `packages/debate_core/src/debate_core/application/federated_search_types.py`: `SearchState`
  gains `ranked_candidates`, with a default, and `evolve` takes it. The orchestration is unchanged.
* `packages/debate_core/src/debate_core/application/federated_dedupe.py`:
  * `open_access` and `citation_count` become merged fields, with `FIELD_PRECEDENCE` rows (OpenAlex,
    then Semantic Scholar);
  * `plain_text` and `american_spelling` become public so the tokenizer reuses them.
* `packages/debate_core/src/debate_core/domain/search.py`: `source_quality_features` is
  `dict[str, float | None]`. `packages/debate_core/schemas/search_result.schema.json` is regenerated
  by `scripts/export_schemas.py`.
* `packages/debate_core/src/debate_core/testing/`: the builder takes the wider type, and
  `SearchRepositoryContract` gains the unknown-feature round trip.
* Tests:
  * `packages/debate_core/tests/application/test_federated_ranking.py` (new, 128 tests);
  * `test_federated_dedupe.py` gains the two precedence rows and the false-and-zero test;
  * `tests/domain/test_roundtrip.py` generates None feature values.
* `tests/fixtures/federated_ranking/labeled_queries.json` and `labelling_sheet.md` (new).
* `plan_specs/v1/e08-research-workflows/t03-feature-ranking.yaml`: the PM's rulings of 2026-10-22,
  each with its comment.

## Deviations from the spec

1. **The spec now names `federated_ranking` paths throughout**, by the PM's naming ruling. The
   ruling named outputs, commands and packages. The Goal description, the forbidden entry, ac3 and
   the `scorer-explainer` description also named `config/ranking.yaml`, and I amended those under
   the same comment, so that no part of the spec names a file that does not exist.
2. **Unknown features.** An unknown feature contributes 0 to the score, the same as a known 0. It
   differs only in what is stored (None) and said (nothing). This follows the PM's ruling. Ranking
   an unknown above or below a known 0 would be a policy choice the spec does not make.
3. **Provider agreement is unknown when one provider or none answered.** With nothing to agree
   with, a 0 would read as disagreement. Like every unknown it contributes nothing.
4. **The three queries are stand-ins, not the current topics.** The custom criterion names the
   Policy, LD and PF current topics; the fixture's queries are debate-style stand-ins I wrote. The
   coach was offered the rewording and labelled them knowingly, and the PM accepted them (ruling 2,
   2026-10-22). The measurement on the current topics moves to v1-e08-t05, on real search results.

## Decisions and assumptions

* **The tokenizer** reuses dedupe's normalization for entities, markup, accents, case and British
  spelling, but differs in two ways:
  * a hyphen splits words (`pass-through` is `pass`, `through`) instead of joining them, so either
    half of a query matches;
  * a possessive `'s` is dropped.

  Nothing is stemmed and there are no stop words: inside a result set, BM25's inverse document
  frequency already discounts words every document has.
* **BM25 is scaled over the filtered set,** so a result the user's `source_types` filter removed
  never sets the scale. The raw value is kept as `lexical_score`. A query with no terms makes bm25
  unknown.
* **Recency:**
  * with a window (`since` set), it is the result's position between `since` and the reference;
  * without one, it decays with the configured half-life;
  * the reference is `until`, or the clock's now;
  * a future date counts as 1.
* **Open access:**
  * an open copy any provider named counts as 1, even when the provider trusted for the flag says
    there is none, since the copy is there to be read;
  * otherwise the flag decides;
  * with neither, open access is unknown.
* **Citations** count for scholarship only, as the spec says. A news story no index counts is not
  thereby uncited.
* **Weights** (committed table): bm25 0.45, recency 0.15, source_type 0.10, peer_reviewed 0.10,
  open_access 0.05, citations 0.10, provider_agreement 0.05. Source-type values: scholarly 1.0,
  government 1.0, think_tank 0.8, news 0.8, other 0.4. These are by category, never by outlet, and
  the YAML gives the reasons. They are starting values for the coach and PM to tune.
* **Table refusals:** a missing or unknown key, a negative weight, every weight 0, `b` outside 0–1,
  a non-positive half-life, a saturation below 1, a source-type value outside 0–1 or a missing
  source type. Each refusal names the key. A publisher's name as a source type is refused like any
  unknown key.
* **Labelling sheet:** items are numbered in alphabetical title order, so a number reveals neither
  the provider order nor the ranking. The records are synthetic: invented titles, authors and
  outlets on example domains.
* **Wiring is v1-e08-t05's.** `FederatedSearchService`'s rank default stays `PassThroughStage`.
  `FEDERATED_RANKING_CONFIG_PATH` names the committed table relative to the repository root, and
  `scripts/stamp_build.py` already bundles the whole `config/` directory into builds.

## Operator follow-ups

None. The affected set is left to the PR's `ci` under agreement 10, and no shared test ground
changed.

## Follow-up work

* **v1-e08-t05 (search command), by the PM's amendment:**
  * register each ranked candidate as an Article: `find_by_canonical_url`, else save a
    discovery-only Article with access `UNKNOWN`, never fetching;
  * then store `search_result_for(...)` results in `state.results`;
  * `SearchOutcome` should expose `ranked_candidates` for t05's table and JSON output (identifiers,
    provider sources, features);
  * pass `rank=FederatedRankStage(load_federated_ranking_config(...), clock=...)` and
    `normalize=DedupeStage()` in the container.
* **v1-e07-t05 (RSS / Google News), by the PM's note of 2026-10-22:** if this branch merges first,
  t05 adds `google_news` right after `rss` in the new `open_access` and `citation_count` rows of
  `FIELD_PRECEDENCE`, below OpenAlex and Semantic Scholar like the other news providers. At this
  session's last sync it had not merged.
* **Language filter:** `SearchFilters.language` belongs to the adapters, which pass it to the
  providers that support it (OpenAlex does). The rank stage does not apply it.
* **Peer review:** when an adapter can report it, `peer_reviewed` reads that field. The same change
  adds a merged field with its precedence row and the explanation's "peer-reviewed" phrase.
* **ac4 on real searches:** the synthetic set is weak evidence, and LD came out level-to-slightly
  lower. Once t05 runs real searches, the coach's labels on real results are the measurement worth
  having, taken in place under the corpus policy.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-22

**Notes:**

Accepted, on four conditions closed in this session before the pull request. Then set the Goal
`Succeeded`, set the session status COMPLETE, and open the pull request with no `--partial`, since
v1-e08-t05 depends on this task. If anything comes out differently from what is written here, stop
and ask for another review.

**What the PM checked.** The branch is clean and based on origin/dev at `2a96979`, 11 commits.
The diff is the 16 files listed, with nothing outside the spec's packages. The ac4 test asserts
the mean (`ranked_mean >= raw_mean`), and its docstring says so. The committed table matches the
weights reported. The labels in `labeled_queries.json` match the per-query counts (7, 7 and 3).
`scripts/task pr` without `--partial` needs `Succeeded`, which is why condition 3 is written as it
is.

**Rulings.**

1. **ac4 is read as the mean over the three queries.** The criterion speaks of the fixture as a
   whole, "at least as often as in raw provider order", and the test already asserts the mean.
   LD's 0.579 against 0.583 is one swapped pair at the bottom of the top ten on a synthetic set,
   and it is recorded, not ruled a failure. No weight is tuned on this set. Tuning waits for the
   coach's labels on real results (ruling 2).
2. **The three queries are stand-ins, not the current topics the custom criterion names**
   (Policy: national health insurance; LD and PF: the September–October resolutions). The PM
   accepts them for this task:
   * the candidates are synthetic, so a current-topic wording would add no realism;
   * the coach was offered the rewording, labelled the stand-ins knowingly, and approves them in
     the PR (condition 3);
   * rewriting them would mean new candidates and fresh labels, for evidence the report already
     calls weak.

   The measurement on current topics moves to real searches. The PM amends v1-e08-t05 in the next
   batch: once the search command runs, the coach labels real results for one query per format on
   the topics current then, and the report records nDCG@10 ranked against provider order. If
   ranking comes out lower, that opens a weight-tuning ticket rather than blocking t05.
3. **The coach approves in the PR, as the criterion says, and that approval is the merge
   condition.** Set the custom criterion's row to "PASS at merge: the coach's approving review of
   this pull request, naming `tests/fixtures/federated_ranking/labeled_queries.json`, is required
   before merge." Set the node `Done` and the Goal `Succeeded` on that basis. If the coach asks for
   changes in the PR instead, nothing merges, and the task comes back for review.
4. **Deviations 1 to 3 are accepted.**
   * The `federated_ranking` names throughout the spec follow the naming ruling; amending the
     description, the forbidden entry, ac3 and the node description is in scope.
   * Unknown contributes 0 and is stored as None and left unsaid, as ruled.
   * Provider agreement is unknown with one provider or none.

**Conditions, all closed in this session:**

1. **Spec.** Add a comment above ac4: `# PM ruling 2026-10-22: the mean nDCG@10 over the three
   queries; per-query values are reported, not gated.`
2. **Report, Deviations.** Add a fourth deviation: the queries are debate-style stand-ins rather
   than the current Policy, LD and PF topics; the coach labelled them knowingly; the PM accepted
   them, and the current-topic measurement moves to v1-e08-t05 on real results (ruling 2).
3. **The PF trailing comma.** The coach confirms in this session that the PF line is F02, F04 and
   F06 and nothing more. Record the confirmation, with its date, under "One label line to confirm".
4. **The custom criterion and the Goal**, as in ruling 3. Re-run `scripts/validate_specs.py` and
   the docs checks after the edits.

**Noted, no action.**

* The first mutation batch's false catch for mutant 7, and the bytecode explanation, are recorded
  well. Re-running with bytecode disabled and saved-byte restores was the right response.
* The peer-reviewed weight (0.10) is dead until an adapter reports peer review, so the highest
  score anything can reach today is 0.90. It does not change any order. Leave it in the table, as
  the YAML explains.
* The affected set (369 files) left to the PR's `ci` follows agreement 10.
* The `FIELD_PRECEDENCE` rows: whichever of this task and v1-e07-t05 merges second adds
  `google_news` after `rss` in the `open_access` and `citation_count` rows, per the PM's note of
  2026-10-22.
