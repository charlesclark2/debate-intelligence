# Session report: v1-e08-t10-search-asks-each-provider-once

| | |
|---|---|
| Task | `v1-e08-t10-search-asks-each-provider-once` — One search asks each provider once, however many queries the expansion gives |
| Spec | [`plan_specs/v1/e08-research-workflows/t10-search-asks-each-provider-once.yaml`](../../plan_specs/v1/e08-research-workflows/t10-search-asks-each-provider-once.yaml) |
| Epic / release | `v1-e08-research-workflows` / `v1.4` |
| Branch | `task/v1-e08-t10-search-asks-each-provider-once` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**Draft, waiting on the PM's ruling (2026-11-04).** The feed half is built: an expanded search reads
each feed once and matches every query against it, so the politics DA's link search on the committed
eight-feed lists goes from 56 feed requests to 8 (7 queries) and from 96 to 8 on the NHI topic (12
queries), with the ranked results, explanations, stored expansion and per-query records identical.
The mechanism is a new optional port, `MultiQuerySearchProvider`, which the fan-out asks once with
every query and which still answers per query. The OpenAlex half is not built: joining the queries
needs facts about OpenAlex's `search=` syntax that neither the code nor the fixtures confirm, and
the PM's ruling says to ask. The looser feed match (amendment 1) is measured and not recommended.
The DOI duplicate (amendment 2) is not a DOI spelling problem: it is one DOI under two OpenAlex work
ids, kept apart by a dedupe rule this task may not change.

## Measurements so far

### Requests before and after, on the recorded fixtures

`packages/debate_cli/tests/test_search_command.py`'s seams, a temporary measuring test (never
committed) run on HEAD and then with the six pre-task source files restored from `ead7e72`. "Test
feed" is the fixture's one Courier feed; "committed lists" is the container building the registry
from `config/feeds/` (eight feeds), every feed answered with the Courier fixture.

| Search | Queries | OpenAlex before → after | Feed requests before → after (test feed) | Feed requests before → after (committed lists) |
|---|---|---|---|---|
| `midterm elections --since 2026-09-14` | 1 | 1 → 1 | 1 → 1 | 8 → 8 |
| `health insurance --argument politics-da --need link` | 7 | 7 → 7 | 7 → 1 | 56 → 8 |
| `national health insurance … --topic policy-2026-27-nhi` | 12 | 12 → 12 | 12 → 1 | 96 → 8 |

On all six runs the JSON's `results` (rank, score, features, explanation, identifiers, providers,
`provider_order`), `expansion`, `status`, `providers` and `provider_calls` (without `elapsed_ms`)
are identical before and after except `article_id`, a fresh ULID minted on every run.

### Amendment 1: what a looser feed match would add

Four rules, each "any query of the search keeps the entry": strict (today: every word of the query);
subject (every word of what the debater typed, the template's `{query}`); subject plus at least one
of the template's own words; half the query's words (stop words and "United States" left out). Feed
entries are counted once per link and inside each query's window.

| Feeds | Entries in window | Strict | Subject | Subject + a template word | Half the words |
|---|---|---|---|---|---|
| Fixtures, politics link on `health insurance` (7 queries) | 16 | 1 | 11 | 1 | 11 |
| Fixtures, politics link on NHI (12 queries) | 16 | 0 | 0 | 0 | 1 |
| Live feeds as cached on 2026-11-02 (7 of 8 feeds), the ac6 search's 7 queries | 115 | 0 | 0 | 0 | 0 |
| The same live feeds, today's 12 queries | 115 | 0 | 1 | 0 | 3 |

Precision on the fixtures, judged by hand for the politics DA's link (an item about the politics of
health insurance): strict keeps 1 item and it is a link ("Health insurance fight costs the president
political capital"). Subject keeps 11, of which 2 are links (that one and "Midterm elections tighten
as health insurance costs rise"); the other 9 are about health insurance and not its politics
(Nepal's budget, India's expansion, mergers, a glossary-like explainer, an enrollment drop). The live
cache was read for counts only; no title was printed. Four of its seven files were rewritten by the
LD search six minutes after the NHI search.

### Amendment 2: the DOI duplicate

`ArticleIdentifiers` reduces `https://doi.org/`, `http://doi.org/`, `https://dx.doi.org/`,
`http://dx.doi.org/` and `doi:` and any case to the bare lowercase DOI before dedupe reads it, so
dedupe never compares DOIs as written. The operator's saved NHI search
(`~/Desktop/search-policy-nhi.json`, read locally) has exactly one DOI twice: ranks 46 and 47, one
DOI under two OpenAlex work ids, at a repository PDF and at its `doi.org` URL. Its twelve results
with a `dx.doi.org` URL each appear once. Dedupe keeps the pair apart by its rule that different
values of one identifier (here the OpenAlex id) win over every other rule.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
