<!-- docs-index: Earlier seasons' caselists as backfiles (`v1-e34-t34`): what the API serves from 2021-22 on, complete-archive sizes, and each import's counts; aggregates only -->
# Caselist backfiles: earlier seasons, from 2021-22 on

The recorded results of `v1-e34-t34-backfile-seasons-import`, under data-use policy 1.17
([Permitted uses](../policies/caselist-data-use.md#permitted-uses) 8 and
[Retention](../policies/caselist-data-use.md#retention)). **Aggregates only**: no school, team code,
debater, disclosure path or file name. Caselist slugs and archive dates are what object keys and run
summaries carry already.

Every number here was recorded from a run that happened. A figure not yet measured is left as _not
yet run_, never estimated (working agreements §6). Estimates, where this page gives any, are labelled
as estimates and say what they were computed from.

## What the API serves, surveyed 2026-10-25

`debate-research caselist backfile-survey`, run by the operator on 2026-10-25 against the dev
profile: two caselist listings, one downloads listing per high-school caselist, and a `HEAD` of each
newest complete archive for the size its file host declares. Nothing was downloaded. The first run
covered 2021-22 to 2025-26. The second, after the survey learned to keep the HTTP status, covered
2021-22 to 2023-24 with `--no-sizes`.

The API lists 65 caselists: 27 not high school, 20 high-school caselists of seasons before 2021-22
(never surveyed: policy 1.17 does not import them), 15 in the surveyed seasons, and 3 of the current
season. A slug's two digits are the year its season starts, and the API's `year` agrees for all 15.

| Season | Caselist | Event | Weeklies listed | Complete archives | Newest complete archive | Size (bytes) |
|---|---|---|---|---|---|---|
| 2025-26 | `hsld25` | ld | 40 | 1 | 2026-06-30 | 4,366,678,808 |
| 2025-26 | `hspf25` | pf | 36 | 0 | none | |
| 2025-26 | `hspolicy25` | cx | 40 | 1 | 2026-06-30 | 3,958,272,657 |
| 2024-25 | `hsld24` | ld | 51 | 1 | 2025-07-01 | 3,967,721,058 |
| 2024-25 | `hspf24` | pf | 41 | 0 | none | |
| 2024-25 | `hspolicy24` | cx | 42 | 1 | 2025-05-06 | 2,563,267,685 |
| 2023-24 | `hsld23`, `hspf23`, `hspolicy23` | ld, pf, cx | the downloads listing answered HTTP 500 | | | |
| 2022-23 | `hsld22`, `hspf22`, `hspolicy22` | ld, pf, cx | the downloads listing answered HTTP 500 | | | |
| 2021-22 | `hsld21`, `hspf21`, `hspolicy21` | ld, pf, cx | the downloads listing answered HTTP 500 | | | |

**Four complete archives, 14,855,940,208 bytes in all.** All four are LD and Policy, of 2024-25
and 2025-26. PF keeps weeklies for those seasons but no complete archive. For 2021-22 to 2023-24 the
downloads listing answers HTTP 500 for every caselist, both times, once each with no retry (500 is
not a status the client retries). Through the documented API those seasons serve no archive.

## Imports

_Not yet run._ Each import's counts go here, one row per caselist.
