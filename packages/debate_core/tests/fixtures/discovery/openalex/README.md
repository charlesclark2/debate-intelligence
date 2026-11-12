# OpenAlex fixtures

Recordings for `OpenAlexProvider`
(`packages/debate_core/src/debate_core/integrations/discovery/openalex.py`), used by
`packages/debate_core/tests/integrations/discovery/test_openalex.py` and its binding of the shared
search provider contract kit.

Nothing here was captured from the live API. Every body was written by hand from OpenAlex's documented
Work object (help.openalex.org, read 2026-10-21), so the works, the venues and the people are
invented. DOIs use the `10.5555` test prefix, and the ORCIDs and institutions exist only to show that
the adapter drops them. Request URLs carry no key: the key travels in the `Authorization` header,
never in a URL.

* `works_search.json` records a `health insurance` search between 2020-01-01 and 2024-12-31 for
  three results. Its body, `works_search.body.json`, has three works:
  * an `article` with a DOI, a best open-access PDF, an inverted-index abstract whose keys are out of
    order and include one word at two positions, and three authorships that carry ORCIDs and
    affiliations;
  * a `report` with no DOI, no venue (`primary_location.source` is null), no open copy and no abstract;
  * a `book-chapter` whose only open copy is a repository landing page, with an empty abstract index
    and one authorship OpenAlex could not match to an author.
* `works_search.expected.json` is what that body must map to, written by hand: bare lowercase DOIs,
  dates at midnight UTC, display names only, `other` for the report, and each work's
  `cited_by_count` and `open_access.is_oa` as `citation_count` and `open_access` (42 and open, 3 and
  closed, 0 and open).
* `works_empty.json` is a search with no results.
* `works_rate_limited.json` is a `429` with `Retry-After: 30` (the per-second limit), and
  `works_daily_budget_spent.json` a `429` with no `Retry-After` (a spent daily budget). Both must be
  `ProviderRateLimited`.
* `works_unavailable.json` is a `503` with `Retry-After: 120`, which must be `ProviderUnavailable`.
* `works_malformed.json` is a `200` whose JSON body is cut off part-way through, which must be
  `ProviderUnavailable`.
* `works_errors.expected.json` is the empty list the four failures expect.
* `works_joined.body.json` (v1-e08-t10) answers one joined search of three queries, `carbon tax
  revenue`, `carbon tax unpopular voters` and `border adjustment`, with four works written so that
  attribution by words in the title and abstract has every case: the first matches only the first
  query; the second matches the first two (its abstract supplies "voters"); the third matches only
  the third; the fourth matches none ("Pricing emissions: a review", no abstract), so it goes to all
  three. By hand, the answers are: first query W5550000001, W5550000002, W5550000004; second
  W5550000002, W5550000004; third W5550000003, W5550000004.
* `works_one_doi_two_work_ids.body.json` (v1-e08-t21) is a `/works` body of six works that
  `packages/debate_core/tests/application/test_federated_dedupe_shared_doi.py` reads through
  `candidate_from_work` to test dedupe, not the adapter. The first two are OpenAlex's own duplicate:
  one DOI, written as a bare lower-case DOI and as an upper-case `doi.org` URL, under two work ids,
  one at the `doi.org` page (7 fields with values) and one at a repository's PDF (10, with the venue,
  an abstract and an open copy). The third and fourth agree on title, author and year but carry
  different DOIs. The fifth and sixth agree on title, author, day and site and carry no DOI (the
  sixth's `doi` is a URL that is not one, which the adapter drops).
