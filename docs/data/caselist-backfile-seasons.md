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

## The dry run on the Mac, 2026-10-25

`DEBATE_ENV=dev uv run debate-research --json caselist backfile-import --caselist hspolicy25`, run by the
operator from the task worktree on 2026-10-25 (a Sunday, outside the no-import window), before the
cutover's seed. It made one downloads listing and one `HEAD`, read the bucket's backfile ledger, and
downloaded, wrote and locked nothing. Exit `1`, `BACKFILE_IMPORT_REFUSED`, as expected:

| | |
|---|---|
| Complete archive | 2026-06-30, 3,958,272,657 bytes (the survey's `HEAD` said the same) |
| Already imported | no |
| Backfile downloads left in 24 hours | 1 |
| Inside the no-import window | no |
| Free on the data directory's volume | 11,044,614,144 bytes |
| Estimate (archive, blobs, parsed store) | 23,749,635,942 bytes |
| Needed, with 25% headroom | 29,687,044,928 bytes |
| Refusals | `RUN_STATE_NOT_SEEDED`, `NOT_ENOUGH_FREE_SPACE` |

The Mac cannot hold one backfile import, so the imports run in the cloud (the PM's ruling Q4). The
window and budget refusals are shown by the tests (`packages/debate_cli/tests/bucket_mode/test_backfile_import.py`).

## Cloud imports (v1-e40-t09)

_Not yet run._ Each import runs as a task of the dev weekly run's task definition, started by hand
([caselist-cloud-run.md, "Backfile imports"](../runbooks/caselist-cloud-run.md#backfile-imports)), one a
day outside the no-import window, after the operator's return after 2026-11-01. Each row is filled
from the task's result line: counts only, never a school, team or file name. "Parsed" is parsed,
unsupported and failed sources; "Held" is the sources held by a removal request, summed; the steps are
restore, download, import, parse, publish and parsed publish, in seconds.

**The cloud dry run** (ac2), `hspolicy25`, 2026-10-31, task definition revision 8 (`v1.1.0-dev.164`):
`ok`, nothing applied, archive 3,958,272,657 bytes, not yet imported, outside the window. Free bytes on
the task's volume **105,463,214,080**, beside the 29,687,044,928 it needs.

| Caselist | Date (Chicago) | Revision | Downloaded bytes | Members | Stored | Suppressed | Held | Sources uploaded | Parsed | Cards | Parsed objects uploaded | Steps (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `hspolicy25` | not yet run | | | | | | | | | | | |
| `hsld25` | not yet run | | | | | | | | | | | |
| `hspolicy24` | not yet run | | | | | | | | | | | |
| `hsld24` | not yet run | | | | | | | | | | | |

**The weekly run after the first import** (ac3): not yet run. Its run id, outcome and minutes, and
the three weeks before it, go here.
