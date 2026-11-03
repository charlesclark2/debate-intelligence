<!-- docs-index: Counts from each weekly `caselist pull`, recorded by the operator; aggregates only -->
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
| `20261014T110006Z` | dev | `hsld26`, `hspolicy26`, `hspf26` | **scheduled** | 3 of 3 wanted | 2 | 2,478 | 1,575 | 0 (pending) | 47s | The first run the schedule made by itself, on build `0.1.0.dev60`, 06:00 CDT. 46 archives and 500 OpenEv files listed, 5 fetched, none deferred by the cap. Four snapshots imported: each caselist's 2026-10-13 weekly and one OpenEv release. The AWS session had expired, so the publish was left pending and the report stage with it: the capture-first design, not a failure. See below |
| `20261014T215249Z` | dev | the same four snapshots | by hand, `--publish-pending` | 0 | 0 | 0 | 0 | 1,575 | 275s | Published what the scheduled run left: 1,575 objects across 4 snapshots, all 4 confirmed in the bucket by its report stage |
| `20261022T052044Z` | dev | `hsld26`, `hspolicy26`, `hspf26` | launchd, kickstarted by hand | 4 | not read | not read | not read | 0 pending | about 2 h 40 min | On build `1.1.0.dev85`, after the `docx-6` re-parse. Parse stage: 3 caselists, 2,628 sources parsed, 12,597 skipped as parsed already, 264 unsupported, 0 failed, 51,998 cards, 2,637 parsed-store objects uploaded. Search index stage: built and published `767b9c7c056b80cb` (52,059 documents, 839,438,336 SQLite bytes, 314,054,035 gzip bytes, no warning), `current.json` names it; 1 superseded local index removed. `v1-e39-t09` ac4's evidence. Recorded by the PM, 2026-10-22 |

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

### The first scheduled run, 2026-10-14 (`v1-e34-t05` ac3)

The row owed here is `20261014T110006Z` above: started by launchd (`runs = 1`, last exit code 0),
on the installed build, reading the store the backfill built (`~/.debate-research/dev`). It
downloaded and imported everything it wanted, and none of it was deferred by the cap, so ac4 has no
truncated run to record. Its publish was pending because the operator's AWS session had expired by
06:00, which is how the run is designed to behave: it captures and imports, and leaves the publish
for a later run or for `caselist pull --publish-pending`.

After `--publish-pending` (`20261014T215249Z`), `caselist status` exited 0 for each caselist the
run covered, and the counts agree with the run's:

| Snapshot | Local files | Published | In sync |
|---|---|---|---|
| `hsld26` 2026-10-13 | 755 | 755 | yes |
| `hspolicy26` 2026-10-13 | 672 | 672 | yes |
| `hspf26` 2026-10-13 | 791 | 791 | yes |
| `openev` 2026-ld | 260, by difference (its row was not read) | | yes: `status --caselist openev` exited 0 |
| **Total** | **2,478** | | |

2,478 is the run's `files_imported`, and the 1,575 objects `--publish-pending` uploaded are its new
blobs. The same evening the agent was reinstalled from `v0.1.0-dev.122`
(`docs/runbooks/caselist-scheduled-sync.md`, "Reinstalling the agent"), so the next scheduled run is
the first on that build.

**A 06:00 run will usually find the AWS session expired.** An SSO session lasts hours, not a week.
Sign in the evening before (`aws sso login --profile debate-dev-evidence`) for the run to publish,
or run `caselist pull --publish-pending` after it; the runbook says the same.
