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

## What is imported, and what is not

The PM's ruling of 2026-10-25 (Q3): the four complete archives only, under policy 1.17, in this order
([docs/runbooks/caselist-backfiles.md](../runbooks/caselist-backfiles.md)). They are the profile's
`caselist.backfile_caselists`.

| Caselist | Season | Imported | Why |
|---|---|---|---|
| `hspolicy25` | 2025-26 | To import, first | Complete archive of 2026-06-30 |
| `hsld25` | 2025-26 | To import, second | Complete archive of 2026-06-30 |
| `hspolicy24` | 2024-25 | To import, third | Complete archive of 2025-05-06 |
| `hsld24` | 2024-25 | To import, fourth | Complete archive of 2025-07-01 |
| `hspf25`, `hspf24` | 2025-26, 2024-25 | **Not imported** | Weeklies only (36 and 41), no complete archive. Policy 1.17 imports backfiles from complete archives |
| `hsld23`, `hspf23`, `hspolicy23` | 2023-24 | **Not imported** | The downloads listing answers HTTP 500: the API serves no archive. Per-round files are not fetched |
| `hsld22`, `hspf22`, `hspolicy22` | 2022-23 | **Not imported** | The same: HTTP 500, no archive |
| `hsld21`, `hspf21`, `hspolicy21` | 2021-22 | **Not imported** | The same: HTTP 500, no archive |
| 20 high-school caselists | before 2021-22 | **Never imported** | Policy 1.17, Retention |

Whether the site could regenerate the 2021-22 to 2023-24 archives is a question Charlie may put to the
maintainer, outside this task.

## The dry run on the Mac

_Not yet run._

## Imports

_Not yet run._ The imports run in the cloud from Thursday 2026-11-05 at the earliest, one a day
outside the no-import window. Each import's counts go here, one row per caselist: members, stored,
suppressed, held, sources uploaded, parsed, unsupported, failed, cards, parsed objects uploaded, and
each step's seconds.
