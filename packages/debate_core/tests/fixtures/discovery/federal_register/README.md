# Federal Register fixtures

Hand-written, not recorded (v1-e07-t07, the PM's ruling of 2026-11-02): no request was sent to the
Federal Register. The answers follow the `GET /api/v1/documents.json` response the Register's API
spec documents (https://www.federalregister.gov/api/v1/documentation.json, read by the PM on
2026-11-02): `count`, `description`, `total_pages`, `next_page_url` and `results`, each result
holding the `fields[]` asked for. Document numbers are in the Register's `YYYY-NNNNN` form but past
any number a year has reached (`2025-90101` on), and every title and abstract is invented. The
agencies are real agency names, as the Register spells them.

Each expected result was written by hand from the body beside it (working agreement 6).

| Recording | What it holds |
|---|---|
| `documents_search.json` | The health insurance marketplace search, 2025-01-01 to 2026-06-30, five results asked for. Its body has five documents: a rule with two agencies, an abstract and both links; a proposed rule with only a PDF link and no abstract; one with no title (skipped); a notice with no agencies, a blank abstract and an impossible date (`2026-02-30`); and one with neither link (skipped). Three candidates. |
| `documents_empty.json` | A search the Register has nothing for, with no date window. |
| `documents_unavailable.json` | `503`. |
| `documents_rate_limited.json` | `429` with `Retry-After: 30`. The Register states no rate limit; this is what the wrapper would hold on if one were sent. |
| `documents_redirected.json` | `302` to `https://unblock.federalregister.gov/`, the block page the Register sends a request it takes for automated scraping. |
| `documents_malformed.json` | `200` with an HTML page instead of JSON. |

`documents_errors.expected.json` is the empty list every failing recording expects.
