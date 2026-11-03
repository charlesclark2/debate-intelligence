# GovInfo fixtures

Hand-written, not recorded (v1-e07-t07, the PM's ruling of 2026-11-02): no request was sent to
GovInfo. The answers follow GovInfo's search service as its documentation describes it
(https://www.govinfo.gov/features/search-service-overview, published 2023-08-15, and
https://github.com/usgpo/api, both read 2026-11-02): a `POST /search` answered with `count`,
`offsetMark` and `results`, each result holding `title`, `packageId`, an optional `granuleId`,
`lastModified`, `governmentAuthor`, `dateIssued`, `collectionCode`, `resultLink` and `download`.
Package ids follow GovInfo's forms (`BILLS-<congress><type><number><version>`, `CRPT-119hrpt212`,
`CHRG-119shrg58210`, `CPRT-119HPRT61022`); every number, title and date is invented. The authors are
committee names in GovInfo's `Congress. House. Committee on …` form.

A recording names only the method and URL, so the request body each search sends is tested in
`test_government.py`, not here. Each expected result was written by hand from the body beside it
(working agreement 6).

| Recording | What it holds |
|---|---|
| `search_results.json` | The single-payer search, 2025-01-01 to 2026-06-30, six results asked for. Its body has seven results: a House bill dated to the day; a committee report dated to its month, with two authors; a hearing granule dated to its year; a second granule of the same report (left out: one candidate per package); a bill whose package id names no Congress (skipped); a committee print with no title (skipped); and a print with no author and an impossible date (`2025-02-30`). Four candidates. |
| `search_empty.json` | A search GovInfo has nothing for, with no date window. |
| `search_unavailable.json` | `503`. |
| `search_rate_limited.json` | `429` with api.data.gov's `OVER_RATE_LIMIT` body and no `Retry-After`, as api.data.gov documents. |
| `search_key_refused.json` | `403` with api.data.gov's `API_KEY_INVALID` body. |
| `search_malformed.json` | `200` with an HTML page instead of JSON. |

`search_errors.expected.json` is the empty list every failing or empty recording expects.
