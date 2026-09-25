# Recorded caselist sync runs

Counts from the weekly `debate-research caselist pull` (`v1-e34-t02-scheduled-sync`), recorded by
the operator. **Aggregates only**: no school, no team code, no debater's initials, no disclosure
path, no file name from inside an archive — the same rule the run summaries themselves are built
to (`docs/policies/caselist-data-use.md` rule 4).

The numbers come from the run's own JSON summary, which is written to
`<data_dir>/caselist-sync-runs/<run id>.json` and, for a scheduled run, appended to
`~/Library/Logs/debate-research/caselist-sync.jsonl`:

```bash
jq -r '[.run_id, .archives_downloaded, .openev_downloaded, .files_imported, .blobs_stored,
        .objects_published, (.duration_seconds | floor)] | @tsv' \
    <data_dir>/caselist-sync-runs/<run id>.json
```

Installing and enabling the schedule is [`docs/runbooks/caselist-scheduled-sync.md`](../runbooks/caselist-scheduled-sync.md).

## Runs

The **Caselist** column names the slug. A caselist slug is not identifying information - it is the
same value the object keys carry (`raw/caselist/<caselist-slug>/...`, policy rule 3) and the same
value the run summaries log. Leaving it out made the three rows below look like one caselist's
history and produced a false bug report, which is why it is now the second column.

| Run id | Environment | Caselist | How it started | Archives | OpenEv | Files imported | New blobs | Objects published | Duration | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| `20260924T042300Z` | dev | `hsld26` | by hand | 5 of 12 wanted | 0 | 255 (12 duplicate, 0 skipped) | 242 | 242 | 34s | The validation run. 13 listed: 5 fetched, 7 deferred by the daily cap, 1 full archive not pulled weekly. No snapshots were held for this caselist beforehand |
| `20260924T042401Z` | dev | `hspolicy26` | by hand | 0 of 11 wanted | 0 | 0 | 0 | 0 | 1s | A different caselist from the row above, and the store held nothing for it. Nothing fetched because the day's five were already spent: all 11 weeklies deferred, 1 full archive not pulled weekly |
| `20260924T042413Z` | dev | `hspf26` | by hand | 0 of 11 wanted | 0 | 0 | 0 | 0 | 1s | As above |

### The cap measurement, 2026-09-25 (`v1-e34-t03` ac5)

A `--dry-run` of the three configured caselists with a full allowance, taken to choose the
notification thresholds. A dry run lists and plans without spending a download, so it shows what
each caselist wants and what the cap would defer. Nothing was fetched.

| Caselist | Listed | Already imported | Wanted | Granted | Deferred by the cap | Full archive |
|---|---|---|---|---|---|---|
| `hsld26` | 13 | 5 | 7 | 2 | 5 | 1 not pulled weekly |
| `hspolicy26` | 12 | 0 | 11 | 2 | 9 | 1 not pulled weekly |
| `hspf26` | 12 | 0 | 11 | 1 | 10 | 1 not pulled weekly |
| **Total** | 37 | 5 | **29** | **5** | 24 | 3 |

The round-robin worked as designed: an allowance of 5 split 2/2/1 across three caselists with
queues of 7, 11 and 11, oldest first within each, so what is deferred is always a caselist's
newest — the archive most certain to still be listed next week.

**The threshold the measurement supports.** A backlog alone is not a notification, because a
backfill backlog is normal and shrinks. A backlog that has *grown* two runs in a row is, because
in steady state it should never grow: three caselists publish about three weeklies a week against
an allowance of five, so an ordinary weekly run defers nothing.

**What the measurement also shows, and it is not this task's to fix.** The cap is five downloads a
*day*, and the schedule runs once a *week*, so one scheduled run can take at most five archives
while about three new ones arrive in the same week. The net drain on a backlog is roughly two a
week, which puts the current 29 at something like fifteen weeks if the weekly schedule were left to
clear it. It must not be: that is exactly why `v1-e30-t06-initial-backfill` is a separate operator
task that spans several days, and why the outstanding weeklies are not pulled ad hoc. The schedule
keeps a current store current; it cannot build one.

### What the validation run established, and what it found

The pipeline works end to end against the live site: list, download, import, publish and confirm,
with `parse` and `landscape` skipped for the reason they are designed to skip (`v1-e31-t06` and
`v1-e32-t05` have not shipped). Publish and report both completed, so the AWS path is proved too.
`files_skipped` was 0, so the importer dropped nothing; 255 files across five weeklies is what a
week's editing window actually holds, which is also why only 12 of them were duplicates.

It also found a defect. All three runs hit the 5-per-day bulk cap, and **none of them said so**.
The first reported "5 archive(s) downloaded" without mentioning the 7 it deferred; the second and
third reported *"Nothing new: none newer than what this machine already holds"* against a store
holding nothing at all for those caselists. `RunSummary.nothing_new` is true whenever nothing was
downloaded, imported or left pending, which is exactly what a cap-blocked run looks like, so a
truncated run is indistinguishable from a complete one in every surface except the JSON. Recorded
as `v1-e34-t03` ac5 and ac6. Until those ship, read the `selections` in the JSON summary rather
than the caption.

Because the cap was reached, **the dev store is not current**: 7 hsld26 weeklies and 11 each of
hspolicy26 and hspf26 are still outstanding. Those are not pulled ad hoc — they are
`v1-e30-t06-initial-backfill`'s, which is the task that measures and records them.

One row is still owed, and only the operator can write it: **the first scheduled run**, started by
launchd rather than by hand ("How it started" = `scheduled`), with its summary checked against the
S3 manifests (`debate-research caselist status`). That is `v1-e34-t05-enable-schedule`, which waits
on an installed `debate-research` from `v1-e01-t09`.
