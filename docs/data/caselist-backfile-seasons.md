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
| `hspolicy25` | 2025-26 | **Imported** 2026-11-02 | Complete archive of 2026-06-30 |
| `hsld25` | 2025-26 | **Imported** 2026-11-07 | Complete archive of 2026-06-30 |
| `hspolicy24` | 2024-25 | **Imported** 2026-11-08 | Complete archive of 2025-05-06 |
| `hsld24` | 2024-25 | **Imported** 2026-11-09 | Complete archive of 2025-07-01 |
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

**All four imported, 2026-11-02 to 2026-11-09.** Each import runs as a task of the dev weekly run's task definition, started by hand
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
| `hspolicy25` | 2026-11-02, after the 2026-10-31 attempt killed for memory (below) | 13 | 3,958,272,657 | 16,059 | 14,340 | 0 | none | 14,340 | 14,163 (176 unsupported, 1 failed) | 408,460 | 14,343 | restore 4.0, download 65.8, import 207.3, parse 4,882.3, publish 196.4, publish parsed 366.6 |
| `hsld25` | 2026-11-06 to 07, overnight | 15 | 4,366,678,808 | 26,174 | 23,657 | 0 | none | 23,657 | 22,898 (757 unsupported, 2 failed) | 339,559 | 23,660 | restore 4.2, download 108.6, import 320.9, parse 3,797.1, publish 307.0, publish parsed 592.6 |
| `hspolicy24` | 2026-11-08 | 15 | 2,563,267,685 | 13,638 | 12,309 | 0 | none | 12,309 | 12,164 (140 unsupported, 5 failed) | 340,132 | 12,312 | restore 5.7, download 37.4, import 168.0, parse 3,817.9, publish 156.6, publish parsed 310.3 |
| `hsld24` | 2026-11-09, started 02:05 | 15 | 3,967,721,058 | 26,255 | 23,973 | 0 | none | 23,973 | 23,261 (708 unsupported, 4 failed) | 338,279 | 23,976 | restore 5.5, download 126.9, import 312.3, parse 3,248.4, publish 310.1, publish parsed 611.7 |

**The first attempt, 2026-10-31.** `hspolicy25` on revision 10 (8 vCPU, 16 GB, 8 parse workers) was
killed at 71 minutes: ECS recorded `OutOfMemoryError`, exit 137. It logged nothing first and published
nothing. It is started again after `v1-e40-t30` gives the run task 32 GB.

**The import, 2026-11-02.** Revision 13 (`v1.1.0-dev.323`, 8 vCPU, 32 GB, 8 parse workers), started
03:20 Chicago, exit 0 in about 95 minutes. Every source was parsed by 2,125 s; the aggregate rebuild
then held the main process for about 46 minutes without a progress line, as the parse stage writes
none during the rebuild. The main process's peak was 2.5 GB, for 408,460 cards (hspolicy26's whole
store, 126,681 cards, peaked at 1.03 GB under `v1-e40-t39`'s compact index): 3.2 times the cards in
2.4 times the memory. The container's figure, 24.4 GB, counts the page cache on cgroup v1.

**The other three, 2026-11-06 to 2026-11-09** (recorded by the PM, 2026-11-09). Each was a task of
revision 15 (`v1.1.0-dev.380`, parser `2026.11.03-docx-9`), started by hand after its dry run the same
day, one a day, outside the no-import window. Each exited 0 with `downloaded_bytes` equal to its dry
run's archive bytes, the archive out of the inbox and no code. The parsed objects uploaded were the
sources stored plus 3 every time, as hspolicy25's 14,343 of 14,340 were: one object per stored source,
unsupported and failed ones included, and three of the store's own. The LD archives hold more files
the parser does not read (757 and 708 unsupported, about 3%, against 1% for Policy), and fewer cards a
file: hsld24's 23,973 sources gave 338,279 cards, about as many as hspolicy24's 12,309. hsld24's parse
was the quickest a source, 0.14 s against 0.31 s for hspolicy24. With all four imported,
`v1-e39-t18` (backfiles in the pilot index) is no longer blocked.

**The weekly run after the first import** (ac3): `20261105T034547Z`, a hand run of the weekly run's
task definition (revision 11) after the scheduled launch was refused on 2026-11-04: completed,
03:45:47 to 05:12:57 UTC (87 minutes), recorded in `v1-e40-t09`'s report. **The run after the fourth
import**, `20261111T120101Z` (recorded by the PM, 2026-11-11): the scheduled run of 2026-11-11 on
revision 15, the first at `2026.11.03-docx-9`, completed in 113 minutes, 12:00:55 to 13:53:52 UTC. Its
restore took 6.7 s and brought back no parsed object, since no docx-9 directory existed; it parsed its
four caselists in full in 92 minutes (20,746 sources, 392,919 cards), left the lock free and saved its
bundle. The four backfiles, which the weekly run does not follow, changed none of its stages.

**hspolicy25 rebuilt at docx-9, 2026-11-12** (recorded by the PM, 2026-11-12). `v1-e39-t18`'s first
bucket check found hspolicy25's parsed store at `2026.10.27-docx-7` only, as its import of 2026-11-02
ran before the docx-9 image. It was rebuilt in the cloud by this runbook's procedure: a dry run
(`"already_imported": true`, 24.7 GB needed, 105.5 GB free, outside the window), then ECS task
`8e203907c93940a99ce84ea6dba01d9a`, revision 15 (`sha256:f1b0e903…`), started 00:53 Chicago. Result:
status ok, applied, `downloaded_bytes` 0 (no download budget spent), sources skipped 14,340 (all
stored), parsed 14,163 (176 unsupported, 1 failed), 408,335 cards, parsed objects uploaded 14,343;
restore 7.2 s, parse 4,080.9 s, publish 69.6 s, publish parsed 388.0 s, about 76 minutes. All four
backfiles now hold a docx-9 directory. hspolicy25's docx-7 directory remains until `caselist retire
--bucket` retires it, after `v1-e39-t18` has measured.
