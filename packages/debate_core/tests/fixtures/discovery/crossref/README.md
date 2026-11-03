# Crossref fixtures

Recordings for `CrossrefProvider`
(`packages/debate_core/src/debate_core/integrations/discovery/crossref.py`), used by
`packages/debate_core/tests/integrations/discovery/test_crossref.py` and its binding of the shared
search provider contract kit.

Nothing here was captured from the live API. Every body was written by hand from Crossref's
documented `/works` list response (a `work-list` envelope around `message.items`) and its work
record's fields, so the works, the venues and the people are invented. DOIs use Crossref's `10.5555`
test prefix; the ORCID and the affiliations exist only to show that the adapter drops them. Request
URLs carry `mailto=crossref-coach@example.org`, the contact email the binding configures for the
polite pool; the public-pool binding removes it.

* `works_query.json` records a `carbon capture subsidies` search between 2020-01-01 and 2024-12-31
  for six results, answered with the polite pool's headers (`x-rate-limit-limit: 3`,
  `x-rate-limit-interval: 1s`, `x-concurrency-limit: 3`). Its body, `works_query.body.json`, has six
  items:
  * a `journal-article` with a full date (`issued` 2022-05-17), face markup and a run of spaces in
    its title, two authors (one with an ORCID and an affiliation), a Creative Commons licence on the
    version of record since its publication, three `link` entries (an XML and a PDF for text mining,
    a PDF for similarity checking) and a JATS abstract with an entity;
  * a `report` dated by year alone (`issued` 2021), whose only author is an organisation, with no
    container title, no licence and one text-mining `link`;
  * a `book-chapter` dated by year and month (`issued` 2023-03);
  * a `posted-content` item with no authors and a publisher's own text-mining licence, not a
    Creative Commons one;
  * a `proceedings-article` whose `issued` date is `[[null]]` and whose online date is 2020-11-02,
    with one author deposited by family name alone, one with no name at all, and a Creative Commons
    licence on the accepted manuscript that starts in 2027;
  * a `journal-article` whose title list is empty.
* `works_query.expected.json` is what that body must map to, written by hand: bare lowercase DOIs,
  DOI resolver URLs, dates at the start of their period with their precision (day, year, month, day,
  day), names as "Given Family", the family name alone or the organisation's name, `other` for the
  report, the abstract without its markup or its "Abstract" heading, the licensed PDF as the first
  work's open copy, and open access unknown (`null`) for every work without a Creative Commons
  licence in force on the test clock's 2024-01-01. The sixth item has no title and is not a
  candidate.
* `works_empty.json` is a search with no results.
* `works_rate_limited.json` is a `429` with `Retry-After: 30` that also advertises a tighter limit
  (1 request every 2 seconds, 1 at a time). It must be `ProviderRateLimited` for 30 seconds.
* `works_rate_limited_without_retry_after.json` is a `429` with the rate-limit headers and no
  `Retry-After`, as Crossref documents it. It must be `ProviderRateLimited` with no stated wait, so
  the wrapper holds Crossref for its cool-down.
* `works_blocked.json` is a `403`, Crossref's answer to a caller it has blocked by hand. It must be
  `ProviderUnavailable` and is not retried.
* `works_errors.expected.json` is the empty list the failures expect.
