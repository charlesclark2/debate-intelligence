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

| Run id | Environment | How it started | Caselists | Archives | OpenEv | Files imported | New blobs | Objects published | Duration | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| `20260924T042300Z` | dev | by hand | 1 | 5 of 12 wanted | 0 | 255 (12 duplicate, 0 skipped) | 242 | 242 | 34s | The validation run. 13 listed: 5 fetched, 7 deferred by the daily cap, 1 full archive not pulled weekly. No snapshots were held for this caselist beforehand |
| `20260924T042401Z` | dev | by hand | 1 | 0 of 11 wanted | 0 | 0 | 0 | 0 | 1s | Nothing fetched: the day's five were already spent. All 11 weeklies deferred, 1 full archive not pulled weekly |
| `20260924T042413Z` | dev | by hand | 1 | 0 of 11 wanted | 0 | 0 | 0 | 0 | 1s | As above, the third run of the same day |

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
