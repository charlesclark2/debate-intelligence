<!-- docs-index: Importing earlier seasons' complete archives as backfiles (`caselist backfile-import`): when imports may run, the dry run and the import, the order, what each refusal means, what a removal does to a backfile, and its rebuild in the cloud after a parser bump -->
# Runbook: earlier seasons as backfiles

How an earlier season's caselist is imported once from its complete archive, parsed and published as
a **backfile** under data-use policy 1.17 ([Permitted uses](../policies/caselist-data-use.md#permitted-uses)
8, [Retention](../policies/caselist-data-use.md#retention)). Task:
[`v1-e34-t34`](../../plan_specs/v1/e34-caselist-sync/t34-backfile-seasons-import.yaml). The counts behind
it, and each import's results, are in
[docs/data/caselist-backfile-seasons.md](../data/caselist-backfile-seasons.md).

A backfile is searchable evidence for research and team files. It is never classified into
positions, never given a landscape or a per-school view, and never pulled by the weekly run. Removal,
the suppression list and path holds reach it exactly as they reach the current season.

## What is a backfile

A caselist named in `caselist.backfile_caselists` in the committed profile (`config/profiles/dev.toml`,
`prod.toml`). That list is the marker:

| Who asks | What it does with a backfile |
|---|---|
| `caselist pull`, by hand or as the weekly run | Refuses it, `BACKFILE_IS_NOT_PULLED`, before anything is listed. A profile naming a slug in both `sync_caselists` and `backfile_caselists` is refused at startup |
| `landscape report` | Refuses it, `BACKFILE_HAS_NO_LANDSCAPE`: no report and no per-school view |
| [The annual purge](annual-purge.md) (`v1-e30-t28`) | Keeps it, by the same setting (`CaselistSettings.is_backfile`), and lists it for the September review |
| `caselist remove`, the suppression list, path holds | Reach it as they reach any caselist |
| The student search pilot's index | Leaves it out until `v1-e39-t18` decides: the weekly run indexes its own caselists only |

The list holds the four complete archives OpenCaselist serves from 2021-22 on, in the PM's order:
`hspolicy25`, `hsld25`, `hspolicy24`, `hsld24`. PF keeps weeklies only for those seasons, and
2021-22 to 2023-24 serve no archive at all (HTTP 500), so neither is imported under policy 1.17.
Seasons before 2021-22 are never imported, and the setting refuses one.

## When an import may run

* **Never from Tuesday 06:00 to Thursday 00:00, America/Chicago.** That window holds the 24 hours
  the weekly run's download ledger counts back from Wednesday 06:00, the Wednesday 03:00 login, and
  the weekly run itself. The command refuses to start inside it (`INSIDE_NO_IMPORT_WINDOW`), and
  each locked step asks again. An import that the window catches part-way stops before its next
  locked step. Run it again after Thursday 00:00 and it resumes from what it left.
* **At most one complete archive a day**, over any 24 hours, counted in the bucket's own backfile
  ledger (`reports/sync/state/caselist-backfile-download-starts.json`). Every machine that runs the
  command reads the same ledger. The weekly run's ledger is never read or written, so the weekly
  run's five downloads a day are its own.
* **Not before the first scheduled cloud weekly run has succeeded** (the PM's ruling of 2026-10-25),
  so that no larger run-state bundle is in play during the cutover's first run. That run is
  Wednesday 2026-10-28; the cloud dry run follows it, and the imports wait for the operator's return
  after 2026-11-01 (the PM, 2026-10-27).
* **In bucket mode, on a seeded bucket.** The ledger and the lock are the bucket's: local mode is
  refused (`NOT_IN_BUCKET_MODE`), and so is a bucket the cutover has not seeded
  (`RUN_STATE_NOT_SEEDED`).

## Where it runs

**In the cloud**, as a one-off task of the weekly run's own task definition, started by hand with its
command overridden to this one, never on a schedule (`v1-e40-t09`, the PM's rulings of 2026-10-27):
[caselist-cloud-run.md, "Backfile imports"](caselist-cloud-run.md#backfile-imports) is how, with
`ops/caselist_run/start_backfile_import.py`. The command reads only settings, so the same build runs
it unchanged in the caselist image. The data directory, the inbox and the Tabroom token's backend
come from the task's environment, as the weekly run's do, and the run's 100 GiB volume holds the
largest import.

**Not on the Mac**, whose data volume had 12 GiB free on 2026-10-25. One import keeps, by its own
estimate, the archive in the inbox, its blobs and its parsed store (4 times its sources' bytes),
plus 25%: about 30 GB for `hspolicy25`. The command refuses before any download when the volume
cannot hold that (`NOT_ENOUGH_FREE_SPACE`), and prints both numbers. The Mac can run the dry run.

## The order

Newest season first, the smaller archive first within a season, one a day outside the window:

| Order | Caselist | Season | Complete archive | Size (bytes) |
|---|---|---|---|---|
| 1 | `hspolicy25` | 2025-26 | 2026-06-30 | 3,958,272,657 |
| 2 | `hsld25` | 2025-26 | 2026-06-30 | 4,366,678,808 |
| 3 | `hspolicy24` | 2024-25 | 2025-05-06 | 2,563,267,685 |
| 4 | `hsld24` | 2024-25 | 2025-07-01 | 3,967,721,058 |

Each takes an estimated 1.5 to 2.5 hours end to end: download, import, parse and publish.

## The dry run

Always first. In the cloud the script starts it with `--dry-run`, and its result is the task's log
([caselist-cloud-run.md, "The dry run"](caselist-cloud-run.md#the-dry-run-v1-e40-t09-ac2)); the block
below is the same command on a machine that has the room. It lists the caselist's downloads, asks the file host the size of its newest complete
archive with a `HEAD`, reads the bucket's backfile ledger and the data directory's volume, and
names every refusal the import would meet. It downloads nothing, writes nothing and takes no lock.

The block refuses to run if a `DEBATE_*` variable is set or a `caselist pull` is running, and names
which. It sets `DEBATE_ENV=dev` for the one command. Replace `hspolicy25` with the caselist due.

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ variables are set:"; env | grep '^DEBATE_' | cut -d= -f1; elif pgrep -fl 'debate-research( --json)? caselist pull'; then echo "STOP: a caselist pull is running (above)"; else DEBATE_ENV=dev debate-research caselist backfile-import --caselist hspolicy25; fi
```

**Read the table before going on.** Exit `0` means no refusal: the archive's date and size, `Already
imported no`, `Backfile downloads left (24 h) 1`, `No-import window outside`, and a free-space line
whose free bytes are above the bytes needed. Exit `1` names each refusal and changes nothing. Fix
what it names (the table below), or wait, then run the dry run again. Never go on to the import from
an exit `1`.

## The import

Only after a dry run that exited `0`, in the same place, the same day.

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ variables are set:"; env | grep '^DEBATE_' | cut -d= -f1; elif pgrep -fl 'debate-research( --json)? caselist pull'; then echo "STOP: a caselist pull is running (above)"; else DEBATE_ENV=dev debate-research caselist backfile-import --caselist hspolicy25 --execute; fi
```

What it does, in four steps, holding the bucket's run lock (the weekly run's) for three of them
and never through the download or the parse:

1. **Locked**: restore the working copy from the bucket, then record this download's start in the
   backfile ledger, before the download.
2. **Not locked**: download the complete archive (`v1-e34-t04`'s downloader, within the complete
   archive's 8 GiB ceiling), import it as the backfile's one dated snapshot,
   `manifests/<slug>/<date>.jsonl`, and parse it.
3. **Locked**: publish the sources and the manifest, then save the run-state bundle with the new
   manifest in it. Refused (`BUNDLE_CHANGED_SINCE_RESTORE`, nothing published) if the bucket's bundle
   changed since step 1, most likely because a removal ran in between. Run the import again: it
   restores the new bundle first.
4. **Locked**: publish the parsed store.

**Success looks like** exit `0` and a table with `Imported` members above zero, `Published` sources
uploaded above zero, `Bundle saved, …`, `Parsed` above zero with `0 failed`, and `Parsed store`
objects uploaded above zero. The archive leaves the inbox once its sources are confirmed. Record
the counts in [docs/data/caselist-backfile-seasons.md](../data/caselist-backfile-seasons.md), one row
per caselist, aggregates only. Exit `1` with `BACKFILE_IMPORT_INCOMPLETE` names the step that did not
finish. Run the dry run, then the import, again: an archive still in the inbox is imported without a
second download, and so without the day's budget.

## What each refusal means

| Code | Why | What to do |
|---|---|---|
| `NOT_A_BACKFILE` | The slug is not in `caselist.backfile_caselists` | Check the slug. A new backfile is a profile change, reviewed |
| `NOT_IN_BUCKET_MODE` | `caselist.run_state` is `local` | Run it where the profile is in bucket mode |
| `RUN_STATE_NOT_SEEDED` | The bucket holds no run lock yet | Wait for the cutover's seed ([caselist-cutover.md](caselist-cutover.md)) |
| `INSIDE_NO_IMPORT_WINDOW` | Tuesday 06:00 to Thursday 00:00 Chicago | Wait until the time it names |
| `NO_COMPLETE_ARCHIVE` | The site lists no complete archive for it | Nothing to import under policy 1.17 |
| `BACKFILE_BUDGET_SPENT` | A backfile download started in the last 24 hours | Wait until 24 hours after it |
| `NOT_ENOUGH_FREE_SPACE` | The volume cannot hold the estimate plus 25% | Run it where it can: the cloud task |
| `CONFIRMATION_REQUIRED` | `--execute` in prod without `--confirm-prod` | Prod receives each backfile by hand, once, before the run's home moves ([A parser bump](#a-parser-bump-the-rebuild-in-the-cloud)) |

## A removal rewrites a backfile's aggregates in the bucket, and nothing is rebuilt

Until `v1-e30-t33` a whole-file removal deleted the parsed store's aggregates of every caselist,
backfiles included, and each backfile then needed its import run again in the cloud to rebuild them
(estimated at about 2 h 10 min and 55.9 GB restored for all four). Since that task (the PM's ruling of
2026-11-05) a removal reaches only the version directories that hold a parsed file of what it removes,
and rewrites each of their aggregates in place without those rows, purging the older versions
([removal runbook, step 5](caselist-removal.md#step-5--execute-in-dev)). A backfile's parsed store is
in the bucket only, so its tables are rewritten there, and the removal's plan lists them with the
`bucket` side alone. Nothing is rebuilt: no import is run again for a removal, and the backfile
no-import window does not apply to one. A backfile that holds no parsed file of the removed file is
not touched at all.

## A parser bump: the rebuild in the cloud

The weekly run re-parses after a parser bump only the caselists it follows (`v1-e40-t08`), so a
backfile's parsed store stays at the version it was imported under. Nothing fails meanwhile: the
weekly index leaves backfiles out until `v1-e39-t18`, and a removal reaches every version directory
that holds a parsed file of what it removes. `hspolicy25` was parsed at `2026.10.27-docx-7` on
2026-11-02, and is the first case. The PM's ruling of 2026-11-06 (`v1-e40-t16`) says how a backfile follows:

* **In dev: the same import, run again, in the cloud.** On a backfile already imported it is a
  rebuild. It downloads nothing and spends no budget. The restore brings no parsed store of the new
  version, so it parses the backfile's sources from `raw/` and publishes the new version's
  directory under the lock. Start it as [caselist-cloud-run.md, "Backfile imports"](caselist-cloud-run.md#backfile-imports)
  says, dry run first. Run it on the run's task definition that carries the new parser's image (the
  dry run's `image digest` is the one `owner.auto.tfvars` names after that image's apply).
  * **When:** after the bump's first weekly run has recorded, so on Thursday at the earliest
    (2026-11-12 for `2026.11.03-docx-9`). Outside the no-import window, never on a Wednesday, and
    never during a prod hand publish ([caselist-cutover.md](caselist-cutover.md#until-the-promotion-prod-is-published-by-hand)):
    both take the dev lock.
  * **The dry run's success** is `"already_imported": true` and no `"code"` line. Its
    `"backfile_downloads_left"` does not matter, since a rebuild downloads nothing.
  * **The rebuild's success** is `"status": "ok"`, `"downloaded_bytes": 0`, and `"parsed"`, `"cards"`
    and `"parsed_uploaded"` above zero. For `hspolicy25` expect about 14,163 parsed and 14,343
    objects uploaded, its import's figures. It takes about 91 minutes, the import's restore, parse,
    publish and parsed-store publish (4.0, 4,882.3, 196.4 and 366.6 seconds).
  * **Untried across a bump.** A run again is tested at the same parser version only
    (`test_backfile_import.py`). The first one's counts go to the PM before the next backfile's, and
    a parse of the whole archive at the new version is the expected shape: `"parsed"` near the
    archive's stored sources, not zero.
  * **Afterwards:** record the counts in
    [docs/data/caselist-backfile-seasons.md](../data/caselist-backfile-seasons.md), then retire the
    backfile's old directory in dev by [the retention runbook](parsed-store-retention.md), never
    before the record.
* **In prod: once, at the version current then.** Prod receives each backfile by hand, once, before
  the run's home moves to prod. Its seed needs every manifest in the prod bucket
  ([At the pilot's promotion](caselist-cutover.md#at-the-pilots-promotion-the-runs-home-moves-to-prod),
  step 2). After the move, prod follows a bump with this same cloud rebuild. Those one-time steps are
  a follow-up tied to the promotion, not written yet. Nothing in prod reads a backfile until
  `v1-e39-t18`. What they need on the Mac, read on 2026-11-06 for `hspolicy25`:
  * 13,510,680,041 bytes of parsed store at `docx-7` (14,343 objects);
  * 3,672,747,197 bytes of raw sources (14,340 objects);
  * 200,800,631 bytes of `openev`'s parsed store, which every restore brings;
  * about 17.4 GB in all, with 56 GB free on the Mac that day.

## What it adds to every weekly run

Each backfile's manifest goes into the run-state bundle that every cloud weekly run restores and
saves. About 15 MB uncompressed per LD backfile, estimated from the dev manifests' 480 bytes per row,
less for Policy, and a few MB once compressed. The run restores only its own caselists' parsed stores,
so a backfile's parsed store never enters the weekly run's scratch storage.
