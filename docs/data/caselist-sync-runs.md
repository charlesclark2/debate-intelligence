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
| _none recorded yet_ | | | | | | | | | | |

Two rows are owed before this epic's `v1-e34-t02` is complete, and neither can be written by
anyone but the operator:

1. **The dev validation run** — one manual `DEBATE_ENV=dev debate-research caselist pull
   --caselist <slug>`, which is what the agent may be installed after.
2. **The first scheduled run**, started by launchd rather than by hand ("How it started" =
   `scheduled`), with its summary checked against the S3 manifests
   (`debate-research caselist status`).
