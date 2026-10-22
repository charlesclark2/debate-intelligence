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
  dates at midnight UTC, display names only, and `other` for the report.
* `works_empty.json` is a search with no results.
* `works_rate_limited.json` is a `429` with `Retry-After: 30` (the per-second limit), and
  `works_daily_budget_spent.json` a `429` with no `Retry-After` (a spent daily budget). Both must be
  `ProviderRateLimited`.
* `works_unavailable.json` is a `503` with `Retry-After: 120`, which must be `ProviderUnavailable`.
* `works_malformed.json` is a `200` whose JSON body is cut off part-way through, which must be
  `ProviderUnavailable`.
* `works_errors.expected.json` is the empty list the four failures expect.
