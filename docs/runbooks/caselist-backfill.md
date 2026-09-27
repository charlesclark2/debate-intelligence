# Runbook: the initial caselist and camp-file backfill

The one-off job that fills the evidence store with this season's caselist history and the Policy
camp files already on hand, publishes it to dev, checks it, then publishes the same store to prod.
It is `v1-e30-t06-initial-backfill`. The results go in
[`docs/data/caselist-backfill-2026-09.md`](../data/caselist-backfill-2026-09.md).

| | |
|---|---|
| Runs on | Charlie's Mac, by hand, one sitting per day |
| Elapsed time | **Six days** of weekly archives, with one spare download on the last day. The complete archive is not part of this backfill: see [The complete archive](#the-complete-archive-not-part-of-this-backfill) |
| Hands-on time | About 15 minutes a day; day 1 about 45 minutes |
| Priority | **HS LD first**, finished on day 1. Policy and PF share the days after that |
| Local store | `~/.debate-research/dev`, **one store for both environments** |
| Commands | `caselist pull` for everything the site has to send; `caselist import` / `import-openev` only for files already on this Mac |

## Why the plan looks like this

**`pull` does the downloading.** `debate-research caselist pull` (`v1-e34-t02`) lists, downloads,
imports and publishes in one run. It budgets the site's **5 bulk downloads per user per day**
round-robin across caselists, oldest first within each, and writes a JSON summary per run
under `~/.debate-research/dev/caselist-sync-runs/`. `caselist runs` (`v1-e34-t03`) reads those
summaries back. Every archive this backfill downloads comes through `pull`, because that is
the only path that counts downloads against the daily cap before spending them.

**The manual commands handle what is already on this Mac.** `pull` has no way to take in a file
you already have: an archive sitting in its inbox is skipped (`already_in_inbox`) and never
imported. The three HS LD weeklies and the 105 Policy camp files already downloaded go in with
`caselist import` and `caselist import-openev`. That also saves three of the scarce downloads.

**Order is enforced, and it decides day 1.** The importer compares each weekly with the snapshot
immediately before it, and refuses an archive older than one already imported
(`SnapshotOutOfOrder`). `pull` skips any weekly dated on or before the newest snapshot held. So
the on-hand 09-01 archive can only go in once 08-11, 08-18 and 08-25 have been pulled. After that,
nothing older can be added. Day 1 is built around that sequence.

**One store, published twice.** The dev and prod profiles point at different data directories.
Everything is downloaded and imported once, into the dev profile's store. That store is published
to dev and checked, then published to prod with `DEBATE_STORAGE__DATA_DIR` naming it. The bytes in
both buckets are identical by construction.

## What is already there

The `v1-e34-t02` validation run on 2026-09-24 pulled the five oldest hsld26 weeklies into the dev
store and published 242 objects to the dev bucket:

| Caselist | Held already | Still wanted (dry run, 2026-09-25) | On this Mac already | Downloads needed |
|---|---|---|---|---|
| `hsld26` | 07-07, 07-14, 07-21, 07-28, 08-04 | 7: 08-11 → 09-22 | 09-01, 09-08, 09-15 | **4**: 08-11, 08-18, 08-25, 09-22 |
| `hspolicy26` | nothing | 11 | none | **11** |
| `hspf26` | nothing | 11 | none | **11** |
| OpenEv 2026 Policy | nothing | not pulled (below) | 105 `.docx` | **0** |

Plus one new weekly per caselist when the site publishes on **Tuesday 29 September**: 3 more.
That makes **29 downloads**, and six days of five is thirty.

Do not re-import the five held weeklies to get their numbers. A re-import is a no-op that writes
no new blobs. Their per-snapshot counts come from the manifests the run already wrote, with the
reporting command in [Recording the numbers](#recording-the-numbers), and are already in the
summary.

All three caselists list one complete archive (`<slug>-all-<date>.zip`) beside their weeklies:
12 or 13 archives each, one of them FULL, in the 2026-09-25 dry run. That confirms the assumption
in ADR-0017's last consequence; the next section says why none is fetched here.

## The complete archive: not part of this backfill

[ADR-0017's revision of 2026-09-26](../adr/0017-caselist-corpus-is-retrievable.md) takes the
complete archive out of this task: **the backfill is the dated weekly series alone, oldest
first.** No `<slug>-all-<date>.zip` is downloaded or imported, in any environment, until
`v1-e34-t04-full-archive-refresh` gives it a snapshot namespace of its own.

Why it cannot simply be imported with `caselist import`:

* **It collides with a weekly.** A snapshot is a caselist plus a date, and the complete archive
  carries the same date as that week's weekly. Both would claim
  `manifests/hsld26/2026-09-22.jsonl`.
* **It ruins the weekly counts after it.** Every import is compared with the snapshot before it.
  The next weekly would be compared with the whole corpus, and every file nobody edited that week
  would count as `REMOVED`.
* **It stops the back-catalogue.** `pull` skips any weekly dated on or before the newest snapshot,
  so importing a complete archive dated 09-22 before the weeklies would leave all of them
  unfetched.

`pull` never fetches one (`full_archive_not_pulled_weekly`), so the daily runs below cannot do so
by accident. **Never download a `-all-` archive by hand, and never pass one to `caselist
import`.** The withdrawal count, which needs one, is `v1-e34-t04`'s.

## Before day 1

Run these from a checkout of `dev` that includes `v1-e34-t03` (any worktree made from `dev` since
2026-09-25 will do). Every command here is `uv run debate-research …` from the repository root.

```bash
export DEBATE_ENV=dev
aws sso login --profile debate-dev-evidence                    # the publish stage needs it
uv run debate-research caselist auth status --check            # one request; token still valid?
env | grep '^DEBATE_CASELIST__'                                 # expect nothing (see below)
launchctl print gui/$UID/com.debate-intelligence.caselist-sync 2>/dev/null | head -1
```

* `auth status --check` must say the token works. If it has expired, run `caselist auth login`.
  If it fails straight after a fresh login, **stop**: that is a suspension, not something to
  retry (policy clause 10).
* **No `DEBATE_CASELIST__*` variables.** In particular `DEBATE_CASELIST__OPENEV_EVENT` must stay
  unset. With it unset, the 498 OpenEv files the API lists for 2026 are all
  `no_event_configured` and `pull` downloads none of them (every 2026-09-24 run summary says so).
  Set it, and the first `pull` would try to download all 498 under different names from the 105
  imported here.
* **The launchd agent must not be installed** (`launchctl print` prints nothing). It is
  `v1-e34-t05`'s, it is set up for the prod profile, and a scheduled run in the middle of this
  would spend the day's downloads into a different data directory.
* The on-hand downloads are where the spec says:

  ```bash
  SRC="$HOME/Documents/debate/2026-2027"
  ls "$SRC/LD Debate/Opencaselist"                 # hsld26-0901  hsld26-0908  hsld26-0915
  find "$SRC/Policy Debate/Camp Files" -type f -name '*.docx' | wc -l    # 105
  ```

`caselist runs --last 5` should show the three 2026-09-24 runs and nothing newer. If it shows a
newer one, someone has pulled since, and **What is already there** needs re-checking with a dry
run before going on.

## Day 1: finish HS LD, import the camp files

About 45 minutes, mostly waiting. The day's five downloads go **3 + 1 to hsld26, 1 to
hspolicy26**.

**Do day 1 in one sitting that does not cross midnight UTC** (8 pm EDT, 7 pm CDT, 5 pm PDT).
`pull`'s download ledger (`caselist-sync-downloads.json`) is keyed by the **UTC** date, although
its docstring says local time. Steps 2 and 5 share one day's allowance through that ledger. If the
UTC date changes between them, step 5 starts from a fresh five, and the site's own counter refuses
part way through.

### 1. Rehearse

```bash
uv run debate-research caselist pull --caselist hsld26 --caselist hspolicy26 --caselist hspf26 --dry-run
```

Seconds; listing calls only, writes nothing. Read the table and check it against **What is
already there**: hsld26 wants 7, hspolicy26 and hspf26 want 11 each, each has one
`full_archive_not_pulled_weekly`, and today's allowance is 5. Write the listed and wanted counts
into the summary's **Backlog** table. If the numbers differ, stop and work out why before
spending anything.

### 2. Pull the three hsld26 weeklies older than what is on hand

```bash
DEBATE_CASELIST__BULK_DOWNLOADS_PER_DAY=3 uv run debate-research caselist pull --caselist hsld26
```

Lowering the allowance to 3 for this one run is what stops `pull` going on to 09-01 and 09-08,
which are already on this Mac. The setting can be lowered but never raised above 5. Expect about
a minute: the 2026-09-24 run took 34 s for five weeklies and 255 files, including the publish.

Success is exit `0`, `3 archive(s) downloaded`, and `publish: completed`. Then:

```bash
ls ~/.debate-research/dev/objects/manifests/hsld26/     # newest must be 2026-08-25.jsonl
```

**Do not go on to step 3 unless the newest is `2026-08-25`.** If the site's limiter stopped the
run early, the rest is marked `deferred_by_rate_limit`. Wait for tomorrow and repeat step 2: the
on-hand archives cannot go in until 08-25 is there.

### 3. Import the three on-hand HS LD weeklies, in date order

```bash
OC="$SRC/LD Debate/Opencaselist"
LOG="$HOME/.debate-research/dev/backfill-imports"; mkdir -p "$LOG"
uv run debate-research --json caselist import "$OC/hsld26-0901" --caselist hsld26 --snapshot 2026-09-01 > "$LOG/hsld26-2026-09-01.json"
uv run debate-research --json caselist import "$OC/hsld26-0908" --caselist hsld26 --snapshot 2026-09-08 > "$LOG/hsld26-2026-09-08.json"
uv run debate-research --json caselist import "$OC/hsld26-0915" --caselist hsld26 --snapshot 2026-09-15 > "$LOG/hsld26-2026-09-15.json"
```

Estimated at under a minute each; 09-15 is the largest, 1,597 files and 209 MB. Each prints one
JSON object. `previous_snapshot` must be the week before (08-25, then 09-01, then 09-08). The JSON
files stay under the data directory. They name no school or team, but they are run output, not
something to commit.

If an import refuses with `SnapshotOutOfOrder`, **stop**. Do not pass `--allow-out-of-order`. It
means something newer is already held, and the counts would be computed against the wrong week.

### 4. Publish them to dev

```bash
uv run debate-research caselist publish --caselist hsld26
```

`pull` publishes only what it imported itself, so the manually imported weeks need this command.
It applies by default and skips anything already in the bucket. Estimated at a few minutes for
about 300 MB of uploads. Success is exit `0` and every snapshot `complete`.

### 5. Pull 09-22 and the first Policy weekly

```bash
uv run debate-research caselist pull --caselist hsld26 --caselist hspolicy26 --caselist hspf26
```

The ledger says 3 of 5 are spent, so this run gets 2. Round-robin hands one each to hsld26 (its
only remaining week, 09-22) and hspolicy26 (its oldest), and hspf26 waits. hsld26 is now
**complete as of the 09-22 listing**.

### 6. Import and publish the Policy camp files

```bash
CAMP="$SRC/Policy Debate/Camp Files"
uv run debate-research caselist import-openev "$CAMP" --year 2026 --event policy --dry-run
uv run debate-research --json caselist import-openev "$CAMP" --year 2026 --event policy > "$LOG/openev-2026-policy.json"
uv run debate-research caselist publish --caselist openev --snapshot 2026-policy
```

Estimated at about a minute to import (105 files, 55 MB) and a minute or two to publish. Read the
dry run's `UNKNOWN` camp count first. A camp missing from the alias table is imported with camp
`UNKNOWN`, which is not a failure, but the count goes in the summary. The `.DS_Store` is skipped
and counted.

### 7. Check dev

```bash
uv run debate-research caselist status
uv run debate-research caselist runs --last 5
```

`status` compares every caselist either side holds. Exit `0` with **Every snapshot agrees** is
what the summary records as `dev status: in sync`.

## Days 2 to 6: Policy and PF

One command a day, at roughly the same time each day or later, and on a new **UTC** date from the
previous run. The site's limiter may count a rolling 24 hours rather than a calendar day. If it
does, a run earlier than the previous day's gets refused part way, and `pull` records the rest as
`deferred_by_rate_limit` and still exits `0`.

```bash
export DEBATE_ENV=dev
aws sso login --profile debate-dev-evidence      # if the session has expired
uv run debate-research caselist pull --caselist hsld26 --caselist hspolicy26 --caselist hspf26
uv run debate-research caselist runs --last 3
```

A few minutes a day. hsld26 stays in the list so it picks up its new weekly after the site
publishes on Tuesday. Expected allocation, if day 1 is **Sunday 27 September** and the 09-29
weeklies are listed by the time day 3 runs:

| Day | Date | hsld26 | hspolicy26 | hspf26 | Left after the run (LD / Policy / PF) |
|---|---|---|---|---|---|
| 1 | Sun 27 Sep | 4 (08-11, 08-18, 08-25, 09-22) + 3 imported from disk | 1 | 0 | 0 / 10 / 11 |
| 2 | Mon 28 Sep | 0 | 3 | 2 | 0 / 7 / 9 |
| 3 | Tue 29 Sep | 1 (09-29, new) | 2 | 2 | 0 / 6 / 8 (after +1 each for 09-29) |
| 4 | Wed 30 Sep | 0 | 3 | 2 | 0 / 3 / 6 |
| 5 | Thu 1 Oct | 0 | 3 | 2 | 0 / 0 / 4 |
| 6 | Fri 2 Oct | 0 | 0 | 4 | 0 / 0 / 0, with one download spare |

Round-robin gives the odd download to whichever caselist is listed first on the command line
(hsld26, then hspolicy26). If 09-29 appears later than day 3, the new weeklies simply join the
queues a day later. The total is the same.

**What the tournament on 3 October gets.** All of HS LD, including 09-29, from day 3. All of
Policy by day 5. PF's newest weeks arrive last, on day 6, because each caselist is filled oldest
first; a missed day pushes them past the tournament. If PF's recent weeks matter for 3 October,
put `--caselist hspf26` before `hspolicy26` from day 2 on.

A day missed is a day late, not data lost: the site keeps the weekly back-catalogue (ADR-0017).
Do not work around the cap. Never run more than one `pull` a day beyond the ones above, and never
set the allowance above 5 (the setting refuses it).

**Done** is a dry run that wants nothing:

```bash
uv run debate-research caselist pull --caselist hsld26 --caselist hspolicy26 --caselist hspf26 --dry-run
```

Every weekly is `already_imported`, one `full_archive_not_pulled_weekly` per caselist, nothing to
fetch. Then run `caselist status` once more and record it.

## Recording the numbers

Aggregates only. The commands below print counts, caselist slugs and dates. Nothing they print is
a school, team code, name, path or filename, so their output can go into
`docs/data/caselist-backfill-2026-09.md` as it is. They read local files and write nothing.

```bash
DATA="$HOME/.debate-research/dev"

# One summary-table row per snapshot, from each manifest's trailing summary row and member rows.
snapshot_rows() {
  for f in "$DATA/objects/manifests/$1"/*.jsonl; do
    jq -rs --arg cl "$1" '
      (map(select(.kind == "summary"))[0]) as $s
      | (map(select(.kind == "member" and (.classification | IN("NEW","UNCHANGED","CHANGED","DUPLICATE"))))) as $m
      | def n($k): ($s.classifications[$k] // 0);
        def fmt($k): ($m | map(select(.format == $k)) | length);
        [$cl, $s.snapshot, ($s.previous_snapshot // "none"), $s.members,
         n("NEW"), n("UNCHANGED"), n("CHANGED"), n("DUPLICATE"), n("REMOVED"), n("SUPPRESSED"),
         ([$s.skipped[]] | add // 0), $s.distinct_sha256,
         fmt("DOCX"), fmt("DOC"), fmt("PDF"), fmt("OTHER"), $s.warnings]
      | "| " + (map(tostring) | join(" | ")) + " |"' "$f"
  done
}

# One dedupe row per caselist: stored members across all its weeklies, distinct files, the
# saving, and the bytes those distinct files hold.
dedupe_row() {
  jq -rs --arg cl "$1" '
    [.[] | select(.kind == "member" and (.classification | IN("NEW","UNCHANGED","CHANGED","DUPLICATE")))]
    | (unique_by(.sha256)) as $d
    | [$cl, length, ($d | length), ((1 - ($d | length) / length) * 1000 | round / 10 | tostring) + "%",
       ($d | map(.byte_size) | add)]
    | "| " + (map(tostring) | join(" | ")) + " |"' "$DATA/objects/manifests/$1"/*.jsonl
}

# One row per snapshot: distinct files it holds, and how many of them no earlier snapshot of the
# same caselist held. NEW cannot answer that question: it is measured against the week before only.
first_seen_rows() {
  jq -rn --arg cl "$1" '
    reduce inputs as $r ({}; .[input_filename] += [$r])
    | to_entries | sort_by(.key)
    | reduce .[] as $f ({seen: {}, rows: []};
        ($f.value | map(select(.kind == "summary"))[0].snapshot) as $snap
        | ([$f.value[] | select(.kind == "member" and (.classification | IN("NEW","UNCHANGED","CHANGED","DUPLICATE"))) | .sha256] | unique) as $d
        | .seen as $s
        | ([$d[] | select($s[.] | not)]) as $fresh
        | .rows += [[$cl, $snap, ($d | length), ($fresh | length)]]
        | .seen += ($fresh | map({(.): true}) | add // {}))
    | .rows[] | "| " + (map(tostring) | join(" | ")) + " |"' "$DATA/objects/manifests/$1"/*.jsonl
}

for cl in hsld26 hspolicy26 hspf26; do snapshot_rows $cl; done
for cl in hsld26 hspolicy26 hspf26; do first_seen_rows $cl; done
for cl in hsld26 hspolicy26 hspf26; do dedupe_row $cl; done
du -sk "$DATA/blobs"                                   # bytes on disk, every source kind together
```

**NEW is not "new to the store".** The weekly importer classifies each archive against the week
before only. A file that was in July, missing from the next few windows, and back in August is
NEW again. On backfill day 1, the three August weeks reported 25 NEW, but only 16 had never been
stored. `first_seen_rows` gives the number that means new evidence, and it matches the run's
`blobs_stored`.

All three functions were checked against the synthetic test archives
(`tests/fixtures/caselist/build_synthetic_archives.py`) and against the five weeklies already
held. For the five, their totals match the 2026-09-24 run summary: 255 imported, 12 duplicate,
242 new blobs.

For the camp files, the counts are in `$LOG/openev-2026-policy.json` (`members`, `counts`,
`skipped_total`, `unknown_camps`, `caselist_duplicates`, `newly_stored_blobs`).

Seconds each. The member count includes skipped junk, so NEW + UNCHANGED + CHANGED + DUPLICATE +
SUPPRESSED + skipped = members. The REMOVED column is **paths no longer present**, not files taken
down. See the note at the top of the summary. The withdrawal count needs the complete archive and
is deferred to `v1-e34-t04`.

## Spot check in dev

At least 20 random disclosures, compared by the coach against their own filenames. Take the
sample from the manifests `caselist status` has just confirmed are identical in the dev bucket:

```bash
cat "$DATA"/objects/manifests/{hsld26,hspolicy26,hspf26}/*.jsonl \
  | jq -c 'select(.kind == "member" and .skip_reason == null and .classification != "REMOVED")
           | {path, side, tournament, round, round_normalized, warnings}' \
  | jq -sc 'unique_by(.path)[]' | sort -R | head -n 20
```

**This prints real paths, which is the point: it goes to your terminal and nowhere else.** Don't
paste it into a session, an issue or a committed file. For each row, check that `side`,
`tournament` and `round` are what the filename in `path` says, or that a non-empty `warnings`
flags it. Record only the tallies in the summary: correct, flagged, wrong. Anything wrong goes to
the parser's owner as an issue described in your own words, with an invented school and team code.

## Publish the same store to prod

Only after dev shows `in sync` and the spot check has been accepted.

```bash
aws sso login --profile debate-prod-evidence
export DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev"
uv run debate-research caselist publish --caselist hsld26     --dry-run
uv run debate-research caselist publish --caselist hsld26     --confirm-prod
uv run debate-research caselist publish --caselist hspolicy26 --confirm-prod
uv run debate-research caselist publish --caselist hspf26     --confirm-prod
uv run debate-research caselist publish --caselist openev --snapshot 2026-policy --confirm-prod
uv run debate-research caselist status
uv run debate-research store ls manifests/hsld26/2026-09-15.jsonl
unset DEBATE_ENV DEBATE_STORAGE__DATA_DIR
```

`DEBATE_STORAGE__DATA_DIR` is the whole point of this block. Without it the prod profile reads
`~/.debate-research/prod`, which is empty, and publishes nothing. Check the dry run's upload count
before the real run: roughly the number of distinct files in the summary, **not zero**. Estimated
at 10 to 20 minutes for the whole store, depending on the uplink. Record the date, the upload
counts and `prod status: in sync`.

`unset` at the end matters. A shell left on `DEBATE_ENV=prod` with the dev data directory is how
the next `pull` would publish into prod unchecked.

HS LD may go to prod before Policy and PF are finished, if the coach wants it there for
3 October. Run the `hsld26` lines only, once hsld26 is in sync in dev and its part of the spot
check has passed.

## Resuming and recovering

| What happened | What to do |
|---|---|
| A `pull` exited `1` at **download** | `caselist runs --last 3` names the stage. Run the same command again. An archive already in the inbox is not fetched twice |
| A `pull` exited `1` at **import** | The archive is in `~/.debate-research/dev/inbox/` but has no manifest. A re-run will **not** import it: it is marked `already_in_inbox`, and `pull` imports only what it downloaded in the same run. Fix the cause, then import it by hand with the date from its name: `caselist import ~/.debate-research/dev/inbox/<slug>-weekly-<date>.zip --caselist <slug> --snapshot <date>`, then `caselist publish --caselist <slug>` |
| `pending_publish` is not empty | `aws sso login --profile debate-dev-evidence`, then `caselist pull --publish-pending` |
| `another caselist sync is already running` | Another `pull` holds the lock; wait for it. See the scheduled-sync runbook if none is running |
| `SnapshotOutOfOrder` on a manual import | Stop. Something newer is already held. Never pass `--allow-out-of-order` in this backfill |
| `caselist status` shows drift | Re-run the `caselist publish` for that caselist. A checksum mismatch needs a person |
| A day was missed | Carry on the next day. Nothing is lost; the plan just ends a day later |

## Related

* [`docs/data/caselist-backfill-2026-09.md`](../data/caselist-backfill-2026-09.md): where the numbers go
* [`docs/runbooks/caselist-scheduled-sync.md`](caselist-scheduled-sync.md): the weekly schedule
  that keeps the store current once this has built it
* [`docs/adr/0017-caselist-corpus-is-retrievable.md`](../adr/0017-caselist-corpus-is-retrievable.md):
  the complete archive, the weekly back-catalogue, and what `REMOVED` means
* [`docs/policies/caselist-data-use.md`](../policies/caselist-data-use.md): rules 4 and 5, and why
  nothing from the store is committed
* [`docs/data/caselist-sync-runs.md`](../data/caselist-sync-runs.md): the 2026-09-24 validation run
  and the 2026-09-25 cap measurement this plan is built on
