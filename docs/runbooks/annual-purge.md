<!-- docs-index: The annual purge each September: what ages out under the data-use policy's retention table, store by store, in dev and prod and on this Mac; each step's listing, delete and check; and the gaps no command covers yet -->
# Runbook: the annual purge

| | |
|---|---|
| Purpose | Delete what the [data-use policy's retention table](../policies/caselist-data-use.md#retention) says has aged out, and list the backfiles for the September review |
| Who runs it | The operator (Charlie). Not an agent session, not CI |
| When | Each September, for the season that aged out on 31 August. Never on a Wednesday, and never while a run holds the bucket's run lock |
| Where | Your Mac, in a checkout of this repository, with the installed `debate-research` build; one terminal window per environment |
| How long | About an hour of attention for each of dev and prod, most of it reading listings |
| Destructive? | **Yes**, in [Step 2](#step-2--landscape-school-views), [Step 4](#step-4--a-caselist-the-inventory-marks-purge) and [Step 5](#step-5--the-student-search-pilots-index): school views, a purged caselist's local classifier files and cassettes, and the search pilot's superseded index versions, every version included. Everything else here lists or checks |
| Tooling | `debate-research config show`, `store ls`, `tub index build`, `publish` and `prune` (the removal runbook's [P4](caselist-removal.md#p4--delete-the-superseded-index-versions-noncurrent-versions-included)), `landscape cassettes` from the checkout with `uv run` (step 4), and the AWS CLI under the everyday and takedown profiles |
| Spec | [`v1-e30-t28-annual-purge-runbook`](../../plan_specs/v1/e30-caselist-ingestion/t28-annual-purge-runbook.yaml) |

A season runs 1 August to 31 July. The policy keeps a season's data for that season and the following
one: the **two-season window**. A September purge in year *Y* works from one date, `WINDOW_START`,
1 August of year *Y* − 1. Everything dated on or after it is in the window. Everything dated before
it has aged out: in September 2027, `WINDOW_START` is `2026-08-01`, and the season leaving the window
is 2025-26.

Since data-use policy 1.17 an aged-out season from 2021-22 on is not deleted. It is kept as a
**backfile**, and only its per-school landscape views go. So in an ordinary year this runbook deletes
school views and superseded search-index versions, checks that the bucket's lifecycle has expired
what it should, checks that no restored working copy is left on this Mac, and lists the backfiles.
Its steps for a whole caselist to delete are there for a season before 2021-22, which should never
be found, because the policy never imported one.

## What the purge deletes, and what it keeps

One row per row of the policy's retention table, plus the stores the spec names besides.

| Store (retention row) | What ages out | What this runbook does | Step |
|---|---|---|---|
| Weekly caselist snapshots: source blobs and manifests, in each bucket, in the run-state bundle and in this Mac's data directory | Seasons before 2021-22. From 2021-22 on, an aged-out season becomes a backfile | Lists every caselist by season and setting. A caselist to delete has no command yet: counts go to the PM | [3](#step-3--the-inventory-what-each-store-holds-by-season), [4](#step-4--a-caselist-the-inventory-marks-purge) |
| Backfiles | Nothing. Kept indefinitely, reviewed each September | Lists each backfile's counts for the review | [8](#step-8--the-september-review-of-the-backfiles) |
| Parsed cards, fingerprints and classifications | With their sources | The inventory dates the parsed store and this Mac's landscape caches by their caselist; counts for a caselist to delete | [3](#step-3--the-inventory-what-each-store-holds-by-season), [4](#step-4--a-caselist-the-inventory-marks-purge) |
| The download inbox | With its caselist | The inventory dates every archive in this Mac's inbox. The cloud run's inbox lives in its task and is gone when the task stops | [3](#step-3--the-inventory-what-each-store-holds-by-season) |
| OpenEv camp files | The topic year they were cut for, plus the following season, by the same rule as disclosures | The inventory dates each camp release by its topic year | [3](#step-3--the-inventory-what-each-store-holds-by-season) |
| Per-school landscape views | When their season leaves the window, backfile or not | **Deleted**, every version, in the bucket and on this Mac | [2](#step-2--landscape-school-views) |
| Circuit-wide landscape reports | Nothing | Kept. Never listed for deletion | [2](#step-2--landscape-school-views) |
| The local classifier's files and the model cassettes (on this Mac only) | With a purged season | **Deleted** for a caselist the inventory marks `PURGE` | [4](#step-4--a-caselist-the-inventory-marks-purge) |
| Team files built from disclosed cards | Nothing. Kept indefinitely (team work product) | Counts them, and checks no card in them is from a purged season | [7](#step-7--built-files) |
| The student search pilot's index | Superseded versions, within 30 days | Checks the current index holds no purged caselist; deletes superseded versions with `tub index prune`, the removal runbook's P4 | [5](#step-5--the-student-search-pilots-index) |
| The pilot's access audit | After 400 days | Nothing: log retention deletes it | — |
| The weekly cloud run's and a backfile import's working copies | When the task stops | Nothing: Fargate deletes them. The container keeps nothing between runs | — |
| A working copy restored on this Mac (`caselist restore-run-state`) | At the end of the step that restored it | Checks none is left, at the start and at the end | [1](#step-1--no-working-copy-left-on-this-mac), [9](#step-9--the-end-of-the-environment) |
| The run-state bundle (`manifests/_run-state/`) | With the manifests it holds | Lists the caselists in its current version; its noncurrent versions are checked with every other prefix's | [3](#step-3--the-inventory-what-each-store-holds-by-season), [6](#step-6--expired-noncurrent-versions) |
| Removal log and suppression list | Nothing | Kept. Never touched | — |
| S3 noncurrent versions | 30 days in dev, 365 in prod, by the bucket's lifecycle rule | Checks the lifecycle left none past its age | [6](#step-6--expired-noncurrent-versions) |

**Which caselists are backfiles** is read from the build's `caselist.backfile_caselists` setting, as
`debate-research config show` prints it, never from a slug or a date ([caselist-backfiles.md, "What
is a backfile"](caselist-backfiles.md#what-is-a-backfile)). **Which season a thing is of** is read from
its date: a weekly or complete archive's snapshot date, a landscape bundle's snapshot, an inbox
archive's date, a camp release's topic year. Where a store holds a caselist with nothing that dates
it, the inventory stops rather than guess.

**OpenEv camp files** are read here as the policy's first row reads disclosures, which the PM's
list of what the purge deletes follows: topic years from 2021 on are kept once they leave the
window, and earlier ones are purged. The setting cannot name `openev`, so a camp release is judged
by its topic year alone.

## When

* **In September**, after the season ended on 31 July and aged out on 31 August. Dev first, then
  prod, each in a terminal window of its own, on the same day or on consecutive days.
* **Never on a Wednesday.** The cloud run runs Wednesdays at 06:00 America/Chicago. Every block that
  reads or writes a bucket checks the day first.
* **Never while a run holds the bucket's run lock** (`reports/sync/run-lock.json`): the cloud run, a
  removal's `--execute`, a `restore-run-state`, or a backfile import in one of its locked steps. Every
  such block reads the lock first. A backfile import is not locked while it downloads and parses, so
  do not start the purge on a day you started one.

## Before you start

* You can sign in with `debate-<env>-evidence` and `debate-<env>-evidence-removal` for the environment
  ([evidence-store.md](evidence-store.md)). The everyday profile lists and reads; it may list object
  versions under `raw/`, `parsed/`, `files/`, `manifests/` and `quarantine/`. The takedown profile
  lists and deletes versions under `reports/landscape/` (school views only) and
  `reports/tub/search/`. Neither profile may list versions anywhere else under `reports/`, or under
  `uploads/` or `exports/`.
* The installed build is the release the weekly run uses, so `config show` gives the profile's
  `caselist.backfile_caselists` as the run sees it.
* The PM knows the purge is on, and has no removal, republish or hand publish under way.

## The window for one environment

Open a new terminal window in a checkout of this repository. Set `PURGE_ENV` to `dev` (then, in a
second window, `prod`) and `WINDOW_START` to 1 August of last year. The block refuses a shell with a
`DEBATE_` override, an environment that is neither `dev` nor `prod`, a `WINDOW_START` that is not a
1 August, and a directory that is not a checkout. Then it reads the bucket's name from the profile,
signs in to both profiles, saves the build's settings for this environment, writes the inventory
script used in steps 3, 5 and 7 into a scratch directory of this window's own, and defines
`purge_guard`.

`purge_guard` is what every later block runs before it touches a bucket. It prints `STOP:` and
returns non-zero on a Wednesday, with a `DEBATE_` variable set, with a `caselist pull` or
`backfile-import` running on this Mac, when it cannot read the bucket, or when the run lock is
anything but free. In prod a bucket with no run lock is allowed: prod has none until the pilot's
promotion moves the run's home there. A block pasted into a window without it fails with *command
not found: purge_guard* and runs nothing.

**Operator command** (expected runtime ~1 min, most of it the two sign-ins)
Where: your Mac, a new terminal window, in a checkout of this repository
```bash
PURGE_ENV=dev
WINDOW_START=2026-08-01
PURGE="${TMPDIR:-/tmp}/annual-purge-${PURGE_ENV}-$$"
case "$PURGE_ENV" in dev) RETENTION_DAYS=30 ;; prod) RETENTION_DAYS=365 ;; *) RETENTION_DAYS= ;; esac
if env | grep -q '^DEBATE_'; then
  echo "STOP: a DEBATE_ variable is set in this shell; open a new window"
elif [ -z "$RETENTION_DAYS" ]; then
  echo "STOP: PURGE_ENV is ${PURGE_ENV}, neither dev nor prod"
elif [ -z "$(printf '%s' "$WINDOW_START" | grep -E '^20[0-9]{2}-08-01$')" ]; then
  echo "STOP: WINDOW_START is ${WINDOW_START}, not a 1 August"
elif [ -f "config/profiles/${PURGE_ENV}.toml" ]; then
  BUCKET=$(python3 -I -c 'import sys, tomllib; print(tomllib.load(open(sys.argv[1], "rb"))["storage"]["s3"]["bucket"])' "config/profiles/${PURGE_ENV}.toml")
  mkdir -p "$PURGE"
  purge_guard() {
    if [ "$(date +%A)" = "Wednesday" ]; then echo "STOP: it is Wednesday, the cloud run's day; run this on another day"; return 1; fi
    if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set in this shell; open a new window"; return 1; fi
    if pgrep -fl 'debate-research( --json)? caselist (pull|backfile-import)'; then echo "STOP: a caselist pull or backfile import is running on this Mac (above)"; return 1; fi
    LOCKS=$(aws s3api list-objects-v2 --profile "debate-${PURGE_ENV}-evidence" --bucket "$BUCKET" --prefix reports/sync/run-lock.json --query 'length(Contents || `[]`)' --output text) || { echo "STOP: could not list the ${PURGE_ENV} bucket; sign in to debate-${PURGE_ENV}-evidence again"; return 1; }
    if [ "$LOCKS" = "0" ] && [ "$PURGE_ENV" = "prod" ]; then echo "run lock: none in the prod bucket"; return 0; fi
    if [ "$LOCKS" = "0" ]; then echo "STOP: the ${PURGE_ENV} bucket holds no run lock, which it has since the cutover; tell the PM"; return 1; fi
    LOCK_STATE=$(aws s3 cp "s3://${BUCKET}/reports/sync/run-lock.json" - --profile "debate-${PURGE_ENV}-evidence" | python3 -I -c 'import json, sys; print(json.load(sys.stdin).get("state"))')
    if [ "$LOCK_STATE" = "free" ]; then echo "run lock: free"; return 0; fi
    echo "STOP: the run lock is ${LOCK_STATE:-unreadable}; wait for its holder (debate-research caselist runs --remote --last 1)"; return 1
  }
  cat > "$PURGE/inventory.py" <<'INVENTORY'
import json
import re
import sys
from collections import defaultdict
from datetime import date

settings = json.load(open(sys.argv[1]))["data"]["settings"]
window = date.fromisoformat(sys.argv[2])
label = sys.argv[3]
listed = [line.strip() for line in open(sys.argv[4]) if line.strip()]
dating = [line.strip() for name in sys.argv[5:] for line in open(name) if line.strip()]
backfiles = set(settings.get("caselist.backfile_caselists") or [])
first_backfile = date(2021, 8, 1)
slug = r"[a-z]+[0-9]{2}"
day = r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
dated = [
    re.compile(rf"manifests/(?P<caselist>{slug})/(full/)?(?P<date>{day})\.jsonl"),
    re.compile(rf"reports/landscape/(?P<caselist>{slug})/(?P<date>{day})(/.*)?"),
    re.compile(rf"inbox/(?P<caselist>{slug})-[a-z]+-(?P<date>{day})\.zip"),
]
camp = re.compile(r"manifests/openev/(?P<year>[0-9]{4})-[a-z]+\.jsonl")
undated = [
    re.compile(rf"parsed/(?P<caselist>{slug}|openev)(/.*)?"),
    re.compile(rf"landscape/[a-z_-]+/(?P<caselist>{slug}|openev)(\.[a-z]+)?(/.*)?"),
    re.compile(r"inbox/(?P<caselist>openev)-.+"),
]
passed_over = re.compile(r"manifests/_[a-z-]+/.*|debate\.sqlite3|landscape/model-cassettes(/.*)?|inbox/\.partial(/.*)?|(.*/)?\.DS_Store")


def read(lines):
    dates, years, present, unknown = defaultdict(list), defaultdict(int), defaultdict(int), []
    for line in lines:
        key = line.removeprefix("./").removeprefix("objects/")
        if passed_over.fullmatch(key):
            continue
        found = next((match for match in (pattern.fullmatch(key) for pattern in dated) if match), None)
        if found:
            try:
                dates[found["caselist"]].append(date.fromisoformat(found["date"]))
            except ValueError:
                unknown.append(key)
                continue
            present[found["caselist"]] += 1
            continue
        found = camp.fullmatch(key)
        if found:
            years[int(found["year"])] += 1
            continue
        found = next((match for match in (pattern.fullmatch(key) for pattern in undated) if match), None)
        if found:
            present[found["caselist"]] += 1
            continue
        unknown.append(key)
    return dates, years, present, unknown


dates, years, present, unknown = read(listed)
known_dates, known_years, _, _ = read(listed + dating)
counts = {"KEEP": 0, "PURGE": 0, "STOP": 0}


def say(verdict, name, why):
    counts[verdict] += 1
    print(f"{label}: {name} {verdict} {why}")


for caselist in sorted(set(present) - {"openev"}):
    found = sorted(known_dates[caselist])
    seen = f"{present[caselist]} item(s) here; " + (f"dated {found[0]} to {found[-1]}" if found else "nothing dates it")
    if caselist in backfiles:
        if found and found[0] < first_backfile:
            say("STOP", caselist, f"a backfile dated before 2021-22 ({seen})")
        else:
            say("KEEP", caselist, f"backfile ({seen})")
    elif not found:
        say("STOP", caselist, f"not a backfile, and no manifest, bundle or inbox archive dates it ({seen})")
    elif found[0] >= window:
        say("KEEP", caselist, f"in the window ({seen})")
    elif found[0] < first_backfile:
        say("PURGE", caselist, f"before 2021-22 ({seen})")
    else:
        say("STOP", caselist, f"aged out of the window from 2021-22 on, and not in caselist.backfile_caselists ({seen})")
for year in sorted(years):
    if year >= window.year:
        say("KEEP", f"openev {year}", f"in the window ({years[year]} release(s))")
    elif year >= first_backfile.year:
        say("KEEP", f"openev {year}", f"aged out, kept as a backfile ({years[year]} release(s))")
    else:
        say("PURGE", f"openev {year}", f"before 2021-22 ({years[year]} release(s))")
if present.get("openev"):
    if known_years:
        say("KEEP", "openev", f"{present['openev']} item(s) here, dated by the releases above or in the bucket")
    else:
        say("STOP", "openev", f"{present['openev']} item(s) here, and no camp release dates them")
for key in unknown:
    counts["STOP"] += 1
    print(f"{label}: STOP {key} is not a key this runbook knows")
print(f"{label}: {counts['KEEP']} kept, {counts['PURGE']} to purge, {counts['STOP']} stop(s)")
if not listed:
    print(f"{label}: INVENTORY EMPTY")
elif counts["PURGE"] or counts["STOP"]:
    print(f"{label}: INVENTORY STOPS")
else:
    print(f"{label}: INVENTORY OK")
INVENTORY
  aws sso login --profile "debate-${PURGE_ENV}-evidence"
  aws sso login --profile "debate-${PURGE_ENV}-evidence-removal"
  DEBATE_ENV="$PURGE_ENV" debate-research --json config show > "$PURGE/settings.json"
  python3 -I -c 'import json, sys; d = json.load(open(sys.argv[1]))["data"]; s = d["settings"]; print("environment:", d["environment"]); print("backfiles named:", len(s["caselist.backfile_caselists"] or [])); print("data directory:", s["storage.data_dir"])' "$PURGE/settings.json"
  echo "bucket: ${BUCKET}, window from ${WINDOW_START}, noncurrent versions kept ${RETENTION_DAYS} days"
  purge_guard
else
  echo "STOP: this is not a checkout of the repository; cd into one"
fi
```
Success looks like the two sign-ins, then `environment:` naming `PURGE_ENV`, `backfiles named:`
followed by the number of slugs the profile's `caselist.backfile_caselists` lists (above zero since
`v1-e34-t34`), the data directory, the `bucket:` line, and `run lock: free` (in prod, `run lock: none in
the prod bucket` until the pilot's promotion). A `STOP:` line means nothing after it ran: correct what it
says, open a new window, and paste the block again. `environment:` naming the other environment means
a profile override; stop and tell the PM.

Every block below runs in this window.

## Step 1 — No working copy left on this Mac

A working copy restored from a bucket (`caselist restore-run-state`, version 1.18 of the policy) is
deleted at the end of the step that restored it. Since `v1-e40-t21` the restore writes a marker,
`debate-research-restored-copy.json`, at the root of every copy it makes, before anything else, so a
restore that stopped part-way leaves one too. The marker holds the environment, the bucket, the time
of the restore and the build's tag, and never a school, a caselist or a path. The dev and prod data
directories never hold one. The block searches your home folder (outside `~/Library` and the Trash)
and `/tmp`, other than those two data directories, and prints two lists, each ending in its count:

* **restored copies**: every directory holding the marker, at any depth;
* **restored before the marker**: a directory holding `debate.sqlite3` three levels down or less with
  no marker. A build before `v1-e40-t21` wrote none, so this is how a copy it restored is seen, for
  example the hspolicy26 copy restored on dev.200. One restored deeper by such a build is not seen
  ([What has no command yet](#what-has-no-command-yet), item 6).

Reads only. The search walks your whole home folder: about a minute on the operator's Mac.

**Operator command** (expected runtime about a minute)
Where: your Mac, in the purge window
```bash
find -H "$HOME" /tmp \( -path "$HOME/Library" -o -path "$HOME/.Trash" \) -prune -o -type f -name debate-research-restored-copy.json -print 2>/dev/null | sed 's|/debate-research-restored-copy.json$||' | grep -vxF -e "$HOME/.debate-research/dev" -e "$HOME/.debate-research/prod" | awk '{ print } END { print "restored copies: " NR }'
find -H "$HOME" /tmp -maxdepth 3 \( -path "$HOME/Library" -o -path "$HOME/.Trash" \) -prune -o -name debate.sqlite3 -print 2>/dev/null | sed 's|/debate.sqlite3$||' | grep -vxF -e "$HOME/.debate-research/dev" -e "$HOME/.debate-research/prod" | while IFS= read -r FOUND; do [ -f "$FOUND/debate-research-restored-copy.json" ] || echo "$FOUND"; done | awk '{ print } END { print "restored before the marker: " NR }'
```
Success looks like `restored copies: 0` and `restored before the marker: 0`. Each line above a count is
a directory a step left behind; the marker in a restored copy says which environment and bucket it came
from, and when (`cat <directory>/debate-research-restored-copy.json`). A `prod-publish-<date>` copy is deleted with the cutover runbook's block,
[Deleting the copy](caselist-cutover.md#until-the-promotion-prod-is-published-by-hand); a copy another
runbook restored, with that runbook's own deleting block. A directory no runbook names: stop, and tell
the PM its last path part only. Run the block again until it prints `0`, then go on.

## Step 2 — Landscape school views

The school views (`schools.csv` and `schools.md`) of every landscape bundle whose snapshot is dated
before `WINDOW_START` are deleted, locally and in the bucket, every version included, under the
removal profile: the season leaving the window, and any earlier one a past purge missed. This is the
same whether the season is now a backfile or not, and it is the one deletion every September has.
Circuit-wide files are kept indefinitely (policy, "Retention") and are never deleted here. A removal
reaches school views by itself ([caselist-removal.md, Argument landscape bundles](caselist-removal.md#argument-landscape-bundles-e32));
this step is the purge's.

**The dry run** lists and writes the delete requests; nothing is deleted until the next block. It reads
the bucket with the removal profile, which since `v1-e32-t13` may list versions under
`reports/landscape/`, and this machine's data directory from the settings the window saved.

**Operator command** (expected runtime seconds; reads only)
Where: your Mac, in the purge window
```bash
if purge_guard; then
  DATA_DIR=$(python3 -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["data"]["settings"]["storage.data_dir"])' "$PURGE/settings.json")
  VIEWS="$PURGE/school-views"
  rm -rf "$VIEWS" && mkdir -p "$VIEWS"
  aws s3api list-object-versions --profile "debate-${PURGE_ENV}-evidence-removal" --bucket "$BUCKET" \
    --prefix reports/landscape/ --output json > "$VIEWS/versions.json"
  python3 -I - "$VIEWS" "$DATA_DIR" "$WINDOW_START" <<'SCHOOLVIEWS'
import json, sys
from datetime import date
from pathlib import Path

purge, data_dir = Path(sys.argv[1]), Path(sys.argv[2])
window = date.fromisoformat(sys.argv[3])
views = {"schools.csv", "schools.md"}
circuit_wide = {"report.md", "positions.csv", "top_cards.csv", "impact_cards.csv", "trends.csv"}

def purged(key):
    parts = key.removeprefix("reports/landscape/").split("/")
    if not len(parts) == 3 or parts[2] not in views | circuit_wide:
        sys.exit(f"STOP: {key} is neither a school view nor a circuit-wide file; nothing was written")
    return parts[2] in views and date.fromisoformat(parts[1]) < window

listing = json.loads((purge / "versions.json").read_text() or "{}")
versions = listing.get("Versions", []) + listing.get("DeleteMarkers", [])
doomed = [{"Key": one["Key"], "VersionId": one["VersionId"]} for one in versions if purged(one["Key"])]
root = data_dir / "reports" / "landscape"
local = sorted(path for path in root.glob("*/*/*") if purged(path.relative_to(data_dir).as_posix())) if root.is_dir() else []
bundles = {one["Key"].rsplit("/", 1)[0] for one in versions}
for key in sorted({one["Key"] for one in doomed}):
    print(f"would delete {sum(1 for one in doomed if one['Key'] == key)} version(s) of {key}")
for path in local:
    print(f"would delete local {path.relative_to(data_dir).as_posix()}")
for number, first in enumerate(range(0, len(doomed), 1000), 1):
    (purge / f"delete-{number}.json").write_text(json.dumps({"Objects": doomed[first:first + 1000], "Quiet": True}))
(purge / "local.txt").write_text("".join(f"{path}\n" for path in local))
print(f"{len(doomed)} bucket version(s) and {len(local)} local file(s) to delete, of {len(bundles)} bundle(s) listed in the bucket")
SCHOOLVIEWS
fi
```
Success looks like one `would delete` line per key and per local file, each a `schools.csv` or
`schools.md` of a snapshot dated before `WINDOW_START`, then the counts. The number of bundles listed
is above zero wherever a landscape report was ever published: `0 bundle(s)` with nothing to delete
means the listing found nothing at all, so check the bucket name before going on (in prod, where no
report may have been published yet, it can be right). `0 bucket version(s) and 0 local file(s)` with
bundles listed means there is nothing of an aged-out season to delete. A `STOP:` line means nothing
was written: do not go on, and tell the PM the key it names. A file left in a local bundle by hand, a
rendered page or an analysis tool's history file, stops it the same way: tell the PM its name, not
its contents.

**Then delete.** The same window, straight after the dry run.

**Operator command** (expected runtime seconds; deletes, and cannot be undone)
Where: your Mac, in the purge window
```bash
if purge_guard; then
  for REQUEST in "$VIEWS"/delete-*.json(N); do
    aws s3api delete-objects --profile "debate-${PURGE_ENV}-evidence-removal" --bucket "$BUCKET" \
      --delete "file://${REQUEST}" --query 'length(Errors || `[]`)' --output text
  done
  while IFS= read -r FILE; do rm -f -- "$FILE"; done < "$VIEWS/local.txt"
  echo "deleted; run the dry run again"
fi
```
Success looks like a `0` for each request file (no errors), then the `deleted` line. **The check:** run
the dry run again. It prints `0 bucket version(s) and 0 local file(s) to delete` and the same number of
bundles. The newest bundle of an aged-out caselist is republished without its school views only if
the PM wants it, as after a removal. Note the two counts for [Step 10](#step-10--record-the-counts).

## Step 3 — The inventory: what each store holds, by season

Every caselist each store holds, judged by the build's settings and its dates, one line each:

* `KEEP … in the window`: everything of it is dated on or after `WINDOW_START`.
* `KEEP … backfile`: `caselist.backfile_caselists` names it. Listed again in [Step 8](#step-8--the-september-review-of-the-backfiles).
* `KEEP openev <year> … aged out, kept as a backfile`: a camp release from 2021 on, read as above.
* `PURGE … before 2021-22`: something of it is dated before 1 August 2021. [Step 4](#step-4--a-caselist-the-inventory-marks-purge).
* `STOP … aged out of the window from 2021-22 on, and not in caselist.backfile_caselists`: the policy
  keeps it as a backfile, but the setting does not say so. Adding a slug to the setting is a reviewed
  profile change, and the weekly run must not still follow it.
* `STOP … nothing dates it`: a store holds the caselist, and neither a manifest nor an archive says
  which season it is of: a test store's leftovers, say.
* `STOP … is not a key this runbook knows`: a key outside every pattern here.

Each list ends with a count line and `INVENTORY OK`, `INVENTORY STOPS` or `INVENTORY EMPTY`. A `STOP`
line holds back [Step 4](#step-4--a-caselist-the-inventory-marks-purge) for that caselist, and goes
to the PM with the line itself (a slug, dates and counts, nothing else). The other steps go on.

**The bucket and its run-state bundle.** The bucket's manifests, with the everyday profile (`store
ls manifests/`: current objects), and the member names of the run-state bundle's current version,
read with `tar -t` and never unpacked, so nothing is restored here. The bundle's members are dated by
the bucket's manifests where they hold no date of their own.

**Operator command** (expected runtime ~1 to 2 min; the bundle is read through once; reads only)
Where: your Mac, in the purge window
```bash
if purge_guard; then
  DEBATE_ENV="$PURGE_ENV" debate-research --json store ls manifests/ > "$PURGE/manifests.json"
  python3 -I -c 'import json, sys; [print(one["key"]) for one in json.load(open(sys.argv[1]))["data"]["objects"]]' "$PURGE/manifests.json" > "$PURGE/bucket-keys.txt"
  BUNDLES=$(aws s3api list-objects-v2 --profile "debate-${PURGE_ENV}-evidence" --bucket "$BUCKET" --prefix manifests/_run-state/run-state.tar.gz --query 'length(Contents || `[]`)' --output text)
  if [ "$BUNDLES" = "1" ]; then
    aws s3 cp "s3://${BUCKET}/manifests/_run-state/run-state.tar.gz" - --profile "debate-${PURGE_ENV}-evidence" | tar -tzf - > "$PURGE/bundle-members.txt"
  else
    : > "$PURGE/bundle-members.txt"
  fi
  echo "run-state bundles: ${BUNDLES}, members: $(wc -l < "$PURGE/bundle-members.txt" | tr -d ' ')"
  python3 -I "$PURGE/inventory.py" "$PURGE/settings.json" "$WINDOW_START" bucket "$PURGE/bucket-keys.txt" | tee "$PURGE/inventory-bucket.txt"
  python3 -I "$PURGE/inventory.py" "$PURGE/settings.json" "$WINDOW_START" bundle "$PURGE/bundle-members.txt" "$PURGE/bucket-keys.txt" | tee "$PURGE/inventory-bundle.txt"
fi
```
Success looks like this, with your counts and the slugs your stores hold:

```text
run-state bundles: 1, members: 214
bucket: samplecl25 KEEP backfile (1 item(s) here; dated 2026-06-30 to 2026-06-30)
bucket: samplecl26 KEEP in the window (41 item(s) here; dated 2026-08-04 to 2027-07-27)
bucket: openev 2026 KEEP in the window (2 release(s))
bucket: 3 kept, 0 to purge, 0 stop(s)
bucket: INVENTORY OK
bundle: samplecl25 KEEP backfile (1 item(s) here; dated 2026-06-30 to 2026-06-30)
bundle: samplecl26 KEEP in the window (41 item(s) here; dated 2026-08-04 to 2027-07-27)
bundle: openev 2026 KEEP in the window (2 release(s))
bundle: 3 kept, 0 to purge, 0 stop(s)
bundle: INVENTORY OK
```

In dev, `run-state bundles: 1` and `members` above zero: the cloud run keeps its state there. In
prod, `0` and an empty bundle list (`bundle: INVENTORY EMPTY`) until the pilot's promotion; anywhere
else, `INVENTORY EMPTY` means the listing read nothing, so check the sign-in and the bucket before going
on. The bucket and the bundle should agree; a caselist in one and not the other goes to the PM.

**This Mac's data directory and download inbox.** Since the cutover the weekly run is the cloud's,
and this Mac's data directory holds what it held at the cutover plus what removals and hand steps
wrote. The listing reads its manifests, its parsed store, its landscape caches and bundles, and the
inbox (`caselist.inbox_dir`, or `inbox` in the data directory), dated by its own manifests and the
bucket's. File names in the inbox are read, never printed, except as a `STOP` line's key.

**Operator command** (expected runtime seconds; reads only)
Where: your Mac, in the purge window, after the bucket's block above
```bash
if purge_guard; then
  DATA_DIR=$(python3 -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["data"]["settings"]["storage.data_dir"])' "$PURGE/settings.json")
  INBOX=$(python3 -I -c 'import json, sys; s = json.load(open(sys.argv[1]))["data"]["settings"]; print(s["caselist.inbox_dir"] or s["storage.data_dir"] + "/inbox")' "$PURGE/settings.json")
  : > "$PURGE/local-paths.txt"
  if [ -d "$DATA_DIR" ]; then
    (cd "$DATA_DIR" && { find objects/manifests -name '*.jsonl'; find parsed -mindepth 1 -maxdepth 1; find landscape -mindepth 2 -maxdepth 2; find reports/landscape -mindepth 2 -maxdepth 2; } 2>/dev/null) >> "$PURGE/local-paths.txt"
  fi
  if [ -d "$INBOX" ]; then
    (cd "$INBOX" && find . -mindepth 1 -maxdepth 1 | sed 's|^\./|inbox/|') >> "$PURGE/local-paths.txt"
  fi
  echo "local paths read: $(wc -l < "$PURGE/local-paths.txt" | tr -d ' ')"
  python3 -I "$PURGE/inventory.py" "$PURGE/settings.json" "$WINDOW_START" local "$PURGE/local-paths.txt" "$PURGE/bucket-keys.txt" | tee "$PURGE/inventory-local.txt"
fi
```
Success looks like `local paths read:` and the same kind of lines, labelled `local:`, ending
`INVENTORY OK`. `INVENTORY EMPTY` is right for a data directory that holds no store (prod's, which
holds no manifests). The data directory's other files (the database, the suppression list and the
removal log beside it, the run log and the ledgers) are not dated by caselist and are not listed.

## Step 4 — A caselist the inventory marks PURGE

**Expected: none.** Seasons before 2021-22 were never imported (policy 1.17), and the setting refuses
one. If step 3 printed no `PURGE` line, there is nothing to do here: go to [Step 5](#step-5--the-student-search-pilots-index).

For each caselist a `PURGE` line names, the dry run is its counts, in the bucket and here. The blocks
refuse a caselist step 3 did not mark `PURGE`. Set `CASELIST` to the slug the line names; for a camp
year (`openev <year> PURGE`), see the paragraph after the gaps below.

**Operator command** (expected runtime seconds; reads only)
Where: your Mac, in the purge window
```bash
CASELIST=put-the-caselist-here
if grep -qE "^(bucket|bundle|local): ${CASELIST} PURGE" "$PURGE"/inventory-bucket.txt "$PURGE"/inventory-bundle.txt "$PURGE"/inventory-local.txt; then
  if purge_guard; then
    for PREFIX in "manifests/${CASELIST}/" "raw/caselist/${CASELIST}/" "parsed/${CASELIST}/" "reports/landscape/${CASELIST}/"; do
      DEBATE_ENV="$PURGE_ENV" debate-research --json store ls "$PREFIX" < /dev/null | python3 -I -c 'import json, sys; d = json.load(sys.stdin)["data"]; print(d["prefix"], d["count"], "current object(s),", d["bytes"], "bytes")'
    done
    for PREFIX in "manifests/${CASELIST}/" "raw/caselist/${CASELIST}/" "parsed/${CASELIST}/"; do
      aws s3api list-object-versions --profile "debate-${PURGE_ENV}-evidence" --bucket "$BUCKET" --prefix "$PREFIX" --output json < /dev/null | python3 -I -c 'import json, sys; t = sys.stdin.read(); d = json.loads(t) if t.strip() else {}; print(sys.argv[1], len(d.get("Versions", [])), "version(s),", len(d.get("DeleteMarkers", [])), "delete marker(s)")' "$PREFIX"
    done
    grep -E "^(bucket|bundle|local): ${CASELIST} " "$PURGE"/inventory-bucket.txt "$PURGE"/inventory-bundle.txt "$PURGE"/inventory-local.txt
  fi
else
  echo "STOP: step 3 marked no ${CASELIST} PURGE"
fi
```
Success looks like seven count lines and the caselist's inventory lines. **Send them to the PM.** They
are counts and a slug only.

**The delete has no command yet, except on this Mac's landscape side.** What a purged caselist leaves
is its sources and manifests, its disclosure records, its parsed store, its rows in the run-state
bundle and that bundle's noncurrent versions, its inbox archives, and this Mac's landscape caches
(`classifications`, `review`, `plan_texts`, `analytic_texts`, `scan-acceptances`). `caselist remove` is
a takedown: it suppresses what it removes, logs a request and holds paths, so it is not run for a
retention delete, and no hand `aws s3 rm` is run over any of these prefixes. The PM files the command
([What has no command yet](#what-has-no-command-yet)); until it exists, the caselist stays on the
PM's list, and the inventory goes on marking it `PURGE` each time it is run, which is the check.

**What is deleted now** (the spec's second amendment, as the removal runbook does it after a
removal): this Mac's local classifier files for the caselist, and the model stage's cassettes that
only this caselist names. First what they hold.

**One caselist's cassettes** (`v1-e32-t31`). A cassette is filed under its prompt and its call's key
in `<data dir>/landscape/model-cassettes/`, and names the caselists it was recorded or replayed for.
The caselist is not part of the key: an identical card in two caselists is one cassette, and names
both. `debate-research landscape cassettes` (`v1-e32-t34`) counts them three ways:

* **its alone**: only this caselist names it, and the delete removes it;
* **shared**: another caselist names it too, and the delete takes only this name off, keeping the
  cassette and everything it recorded for the other;
* **unattributed**: it names no caselist, because it was recorded before `v1-e32-t31`. No caselist's
  delete removes it; the count goes to the PM.

The command reads the directory the landscape model stage records to, from this environment's
`storage.data_dir`. It runs from the checkout, as the model stage does, with `uv run`: the window is
in one, and it must be up to date on `dev`, since the installed build may predate the command. It
prints counts, the slug and a confirmation code, never a cassette's content or name or a path. Without
`--delete` it changes nothing, and it stops, changing nothing, on a file it cannot read as a cassette.

**Operator command** (expected runtime seconds; reads only)
Where: your Mac, in the purge window, with `CASELIST` from the block above
```bash
if grep -qE "^(bucket|bundle|local): ${CASELIST} PURGE" "$PURGE"/inventory-bucket.txt "$PURGE"/inventory-bundle.txt "$PURGE"/inventory-local.txt; then
  DATA_DIR=$(python3 -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["data"]["settings"]["storage.data_dir"])' "$PURGE/settings.json")
  if [ -d "${DATA_DIR}/landscape/local-classifier/${CASELIST}" ]; then echo "local classifier files: $(find "${DATA_DIR}/landscape/local-classifier/${CASELIST}" -type f | wc -l | tr -d ' ')"; else echo "local classifier files: none"; fi
  if [ -f "${DATA_DIR}/landscape/classifications/${CASELIST}.jsonl" ]; then echo "classified here: yes"; else echo "classified here: no"; fi
  DEBATE_ENV="$PURGE_ENV" uv run debate-research landscape cassettes --caselist "$CASELIST"
else
  echo "STOP: step 3 marked no ${CASELIST} PURGE"
fi
```
Success looks like the two lines, then the cassette counts, for example:

```text
local classifier files: none
classified here: yes
Model cassettes of samplecl20 in dev, in the landscape model stage's directory, <data dir>/landscape/model-cassettes/:
  3 this caselist's alone: a delete removes them.
  1 shared with another caselist: kept, losing only this caselist's name, since another caselist still replays them.
  0 unattributed, naming no caselist (recorded before v1-e32-t31): kept, since no caselist's delete removes one. Send the PM the count.
  12 of other caselists only: untouched.
Dry run: nothing was changed. To carry it out, add: --delete --confirm 3f9a0c1d2e4b
```

A data directory the model stage never recorded in prints `No model cassettes in dev: …` and `Nothing
to delete.`; so does a Mac with no `landscape/model-cassettes` directory, today's state. That, or
`Dry run: nothing was changed, and a delete would change nothing.`, means the cassette delete below is
skipped. `CASSETTE_UNREADABLE` means a file there is not a cassette: tell the PM and delete nothing.
`No such command 'cassettes'` means the checkout predates `v1-e32-t34`: pull `dev` and paste the block
again. When `unattributed` is above zero and `classified here: yes`, an unattributed cassette may hold
this caselist's cards and nothing here deletes it: send the PM the counts.

**Then delete the local classifier files.**

**Operator command** (expected runtime seconds; deletes, and cannot be undone)
Where: your Mac, in the purge window, straight after the block above
```bash
if grep -qE "^(bucket|bundle|local): ${CASELIST} PURGE" "$PURGE"/inventory-bucket.txt "$PURGE"/inventory-bundle.txt "$PURGE"/inventory-local.txt; then
  DATA_DIR=$(python3 -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["data"]["settings"]["storage.data_dir"])' "$PURGE/settings.json")
  if [ -d "${DATA_DIR}/landscape/local-classifier/${CASELIST}" ]; then rm -r "${DATA_DIR}/landscape/local-classifier/${CASELIST}" && echo "deleted: the local classifier files of ${CASELIST}"; else echo "nothing to delete: no local classifier files of ${CASELIST}"; fi
else
  echo "STOP: step 3 marked no ${CASELIST} PURGE"
fi
```
Success looks like a `deleted:` or `nothing to delete:` line. The review queue's order model
(`v1-e32-t26`) is in that directory and goes with it; it is trained again with
`scripts/compare_local_classifier.py features` and then `train-queue-order` when that caselist's
landscape is next built.

**Then delete the cassettes**, unless the dry run said there is nothing to delete. Set `CASSETTES_CODE`
to the code after `--confirm` in the dry run's last line. The command lists again and deletes only if
that listing's code is the one given, so a cassette recorded since the dry run, or a code from another
caselist's dry run, is refused with `CONFIRMATION_MISMATCH` and nothing is changed: paste the dry run
block again and read it. In prod the command also takes `--confirm-prod`, which the block adds.

**Operator command** (expected runtime seconds; deletes, and cannot be undone)
Where: your Mac, in the purge window, after the block above
```bash
CASSETTES_CODE=
if [ -z "$CASSETTES_CODE" ]; then
  echo "STOP: set CASSETTES_CODE to the code the dry run printed"
elif grep -qE "^(bucket|bundle|local): ${CASELIST} PURGE" "$PURGE"/inventory-bucket.txt "$PURGE"/inventory-bundle.txt "$PURGE"/inventory-local.txt; then
  if [ "$PURGE_ENV" = "prod" ]; then
    DEBATE_ENV=prod uv run debate-research landscape cassettes --caselist "$CASELIST" --delete --confirm "$CASSETTES_CODE" --confirm-prod
  else
    DEBATE_ENV="$PURGE_ENV" uv run debate-research landscape cassettes --caselist "$CASELIST" --delete --confirm "$CASSETTES_CODE"
  fi
else
  echo "STOP: step 3 marked no ${CASELIST} PURGE"
fi
```
Success looks like `Deleted 3 cassette(s) only this caselist named.`, `Kept 1 shared cassette(s) …` and
`Kept 0 unattributed cassette(s) …`, with the counts the dry run printed. **The check:** the dry run
block again prints `local classifier files: none`, and `0 this caselist's alone` and `0 shared` for the
caselist, with the same `unattributed` count as before. Tell the PM when a cassette was deleted, since
the model evaluation of this caselist is then recorded again. A coach sample deleted this way is drawn
again with `scripts/compare_local_classifier.py features` and then `sample`; tell the PM if one was
waiting to be labelled.

**A camp year marked `PURGE`** (`openev <year> PURGE`) is counted with `DEBATE_ENV=<env>
debate-research store ls raw/openev/<year>/` and the release manifests `store ls manifests/openev/`
names for that year. It has no command either, and goes to the PM the same way.

## Step 5 — The student search pilot's index

**Which caselists the current index holds.** Read from the manifest `current.json` names, as the
removal runbook's P3 reads it, and judged like step 3. The weekly run indexes its own caselists only,
so an index holding a caselist step 3 would not keep is a finding. Reads only.

**Operator command** (expected runtime seconds; reads only)
Where: your Mac, in the purge window, after step 3
```bash
if purge_guard; then
  POINTERS=$(aws s3api list-objects-v2 --profile "debate-${PURGE_ENV}-evidence" --bucket "$BUCKET" --prefix reports/tub/search/current.json --query 'length(Contents || `[]`)' --output text)
  if [ "$POINTERS" = "1" ]; then
    MANIFEST_KEY=$(aws s3 cp "s3://${BUCKET}/reports/tub/search/current.json" - --profile "debate-${PURGE_ENV}-evidence" | python3 -I -c 'import json, sys; print(json.load(sys.stdin)["manifest_key"])')
    aws s3 cp "s3://${BUCKET}/${MANIFEST_KEY}" - --profile "debate-${PURGE_ENV}-evidence" | python3 -I -c 'import json, sys; [print("parsed/" + one["caselist"]) for one in json.load(sys.stdin)["stores"]]' > "$PURGE/index-stores.txt"
    python3 -I "$PURGE/inventory.py" "$PURGE/settings.json" "$WINDOW_START" index "$PURGE/index-stores.txt" "$PURGE/bucket-keys.txt" | tee "$PURGE/inventory-index.txt"
  else
    echo "no search index in this bucket: the pilot is not deployed here"
  fi
fi
```
Success looks like one `index:` line per store, each `KEEP`, ending `index: INVENTORY OK`; or, where the
pilot is not deployed, the `no search index` line. **A `PURGE` line** means the published index holds a
purged caselist. Rebuild and publish it without that store with the removal runbook's
[P3](caselist-removal.md#p3--rebuild-and-publish-the-index), its `STORES` less that caselist, then run
this block again: the line is gone. **A `STOP` line** goes to the PM.

**Then the superseded index versions**, noncurrent versions included, with `debate-research tub index
prune`, the command the removal runbook's
[P4](caselist-removal.md#p4--delete-the-superseded-index-versions-noncurrent-versions-included) runs
(`v1-e39-t15`): its dry run, then its delete, then its dry run again as the check, in this window after
`purge_guard`. The command keeps the current index's directory and the current `current.json`, lists
and deletes under the takedown profile this window signed in to, and refuses on its own on a Wednesday
and while the run lock is held; `purge_guard` checks the same first. P4 says what its table shows and
what each refusal means.

**Operator command** (expected runtime seconds; reads only)
Where: your Mac, in the purge window, after the block above
```bash
if purge_guard; then
  DEBATE_ENV="$PURGE_ENV" DEBATE_REMOVAL_PROFILE="debate-${PURGE_ENV}-evidence-removal" debate-research tub index prune --env "$PURGE_ENV"
fi
```
Success looks like P4's dry run: a title naming the current index by the first eight characters of
its id, that index's row `kept` and `current.json`'s `current kept, older would be deleted`, and a
line ending `To carry it out, add: --execute --confirm <code>`. Note its counts for step 10. `Dry run: nothing to delete` means
there is nothing to delete: skip the next block. **Stop** on a refusal, or on a row other than the
current index's and `current.json`'s that says `kept`, and tell the PM.

**Then delete.** Set `CODE` to the code the dry run printed. In prod the block adds `--confirm-prod`.

**Operator command** (expected runtime seconds; deletes, and cannot be undone)
Where: your Mac, in the purge window
```bash
CODE=put-the-code-the-dry-run-printed-here
if purge_guard; then
  if [ "$PURGE_ENV" = "prod" ]; then
    DEBATE_ENV=prod DEBATE_REMOVAL_PROFILE=debate-prod-evidence-removal debate-research tub index prune --env prod --execute --confirm "$CODE" --confirm-prod
  else
    DEBATE_ENV="$PURGE_ENV" DEBATE_REMOVAL_PROFILE="debate-${PURGE_ENV}-evidence-removal" debate-research tub index prune --env "$PURGE_ENV" --execute --confirm "$CODE"
  fi
fi
```
Success looks like a line beginning `Deleted N:`, N the dry run's versions and delete markers
together. **The check:** the dry run block again says `Dry run: nothing to delete`, under the same
current index. A refusal deleted nothing; P4's table says what to do.

**This Mac's own index builds.** Each build here writes `tub-index/<index id>/` in the data directory,
and only the next build here prunes them, keeping the newest two. Since the cutover the builds are the
cloud's, so the Mac's stay as they are. Count them:

**Operator command** (expected runtime seconds; reads only)
Where: your Mac, in the purge window
```bash
DATA_DIR=$(python3 -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["data"]["settings"]["storage.data_dir"])' "$PURGE/settings.json")
find "${DATA_DIR}/tub-index" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' '
```
Success looks like a number. Each directory holds card text with schools and team codes. No command
deletes them outside a build; note the number for step 10, and the PM decides
([What has no command yet](#what-has-no-command-yet)).

## Step 6 — Expired noncurrent versions

The bucket's lifecycle rule (`age-out-superseded-evidence-versions`) expires every noncurrent version
30 days (dev) or 365 days (prod) after it became noncurrent. This checks it has: it lists every
version under the prefixes the profiles may list, and counts the noncurrent versions and delete
markers older than that, with two days' grace for the rule's daily run. It deletes nothing: an
expired version left over means the rule is not doing its job, which is the PM's to look into, not a
hand delete's. Reads only.

The listing is of every version under `raw/`, `parsed/`, `files/`, `manifests/` and `quarantine/` (the
everyday profile), and `reports/landscape/` and `reports/tub/search/` (the takedown profile). It
cannot see the rest of `reports/`, `uploads/` or `exports/`: neither profile may list their versions.

**Operator command** (expected runtime a few minutes in dev, longer in prod; reads only)
Where: your Mac, in the purge window
```bash
if purge_guard; then
  rm -f "$PURGE"/versions-*.json
  for PREFIX in raw/ parsed/ files/ manifests/ quarantine/; do
    aws s3api list-object-versions --profile "debate-${PURGE_ENV}-evidence" --bucket "$BUCKET" --prefix "$PREFIX" --output json > "$PURGE/versions-${PREFIX%/}.json"
  done
  for PREFIX in reports/landscape/ reports/tub/search/; do
    aws s3api list-object-versions --profile "debate-${PURGE_ENV}-evidence-removal" --bucket "$BUCKET" --prefix "$PREFIX" --output json > "$PURGE/versions-$(printf '%s' "${PREFIX%/}" | tr / -).json"
  done
  python3 -I - "$PURGE" "$RETENTION_DAYS" <<'EXPIRED'
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

purge, retention = Path(sys.argv[1]), int(sys.argv[2])
now = datetime.fromisoformat(sys.argv[3]) if len(sys.argv) > 3 else datetime.now(timezone.utc)
limit = timedelta(days=retention + 2)


def when(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


keys = noncurrent = expired = 0
for listing in sorted(purge.glob("versions-*.json")):
    text = listing.read_text()
    body = json.loads(text) if text.strip() else {}
    by_key = defaultdict(list)
    for one in body.get("Versions", []) + body.get("DeleteMarkers", []):
        by_key[one["Key"]].append(one)
    late, oldest = 0, None
    for versions in by_key.values():
        versions.sort(key=lambda one: (bool(one.get("IsLatest")), when(one["LastModified"])), reverse=True)
        for newer, older in zip(versions, versions[1:]):
            noncurrent += 1
            since = when(newer["LastModified"])
            if now - since > limit:
                late += 1
                oldest = since if oldest is None or since < oldest else oldest
    keys += len(by_key)
    expired += late
    where = listing.stem.removeprefix("versions-")
    print(f"{where}: {len(by_key)} key(s), {late} noncurrent past {retention} days" + (f", the oldest noncurrent since {oldest.date()}" if late else ""))
print(f"{keys} key(s), {noncurrent} noncurrent version(s) and delete marker(s), {expired} past the lifecycle's {retention} days and two more")
print("EXPIRED EMPTY" if keys == 0 else "EXPIRED OK" if expired == 0 else "EXPIRED STOPS")
EXPIRED
fi
```
Success looks like one line per prefix, `raw` and `manifests` with keys above zero wherever the corpus
is published, then the totals and `EXPIRED OK`. `EXPIRED STOPS` names the prefix and the date the
oldest became noncurrent: send those lines to the PM and do not delete by hand. `EXPIRED EMPTY` means
nothing was listed at all: check the sign-ins and the bucket. An error from one listing (`AccessDenied`)
means a grant is not what [evidence-store.md](evidence-store.md) says: send it to the PM.

## Step 7 — Built files

Team files built from disclosed cards are kept indefinitely (policy, "Retention"), so nothing is
deleted here. Their count goes on the record, and their provenance sidecars are read for the
caselists their cards came from: a card from a caselist step 3 would purge is a finding for the PM.
The bucket's keys are the layout of [file-publish-log.md](../data/file-publish-log.md),
`files/<topic>/<side>/<position>/<slug>/<recipe hash 12>/`; this Mac's built files are under
`files/built/` in the data directory. Reads only.

**Operator command** (expected runtime seconds; reads only)
Where: your Mac, in the purge window, after step 3
```bash
if purge_guard; then
  DATA_DIR=$(python3 -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["data"]["settings"]["storage.data_dir"])' "$PURGE/settings.json")
  DEBATE_ENV="$PURGE_ENV" debate-research --json store ls files/ | python3 -I -c 'import json, sys; d = json.load(sys.stdin)["data"]; print("bucket files/:", d["count"], "object(s)")'
  find "${DATA_DIR}/files/built" -name '*.provenance.json' 2>/dev/null > "$PURGE/sidecars.txt"
  echo "built files on this Mac: $(wc -l < "$PURGE/sidecars.txt" | tr -d ' ')"
  python3 -I - "$PURGE/sidecars.txt" > "$PURGE/cited.txt" <<'SIDECARS'
import json
import sys


def cited(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "caselist" and isinstance(value, str):
                yield value
            else:
                yield from cited(value)
    elif isinstance(node, list):
        for value in node:
            yield from cited(value)


paths = [line.strip() for line in open(sys.argv[1]) if line.strip()]
for caselist in sorted({one for path in paths for one in cited(json.load(open(path)))}):
    print(f"parsed/{caselist}")
SIDECARS
  if [ -s "$PURGE/cited.txt" ]; then python3 -I "$PURGE/inventory.py" "$PURGE/settings.json" "$WINDOW_START" built "$PURGE/cited.txt" "$PURGE/bucket-keys.txt" "$PURGE/local-paths.txt"; else echo "built: no card cited"; fi
fi
```
Success looks like `bucket files/:` with a count, `built files on this Mac:` with a count, and either
`built: no card cited` or `built:` lines ending `INVENTORY OK`. A `PURGE` or `STOP` line goes to the
PM: the file is kept, and whether it is rebuilt is the PM's ruling.

## Step 8 — The September review of the backfiles

The policy reviews the backfiles each September at the purge. For each caselist the build's
`caselist.backfile_caselists` names: its manifests, its sources and its parsed objects in the bucket,
counted and sized, with the everyday profile. Reads only.

**Operator command** (expected runtime ~1 min; reads only)
Where: your Mac, in the purge window, after step 3
```bash
if purge_guard; then
  python3 -I -c 'import json, sys; [print(one) for one in json.load(open(sys.argv[1]))["data"]["settings"]["caselist.backfile_caselists"] or []]' "$PURGE/settings.json" > "$PURGE/backfiles.txt"
  while IFS= read -r CASELIST; do
    for PREFIX in "manifests/${CASELIST}/" "raw/caselist/${CASELIST}/" "parsed/${CASELIST}/"; do
      DEBATE_ENV="$PURGE_ENV" debate-research --json store ls "$PREFIX" < /dev/null | python3 -I -c 'import json, sys; d = json.load(sys.stdin)["data"]; print(d["prefix"], d["count"], "object(s),", d["bytes"], "bytes")'
    done
  done < "$PURGE/backfiles.txt"
  grep -hE ' KEEP (backfile|aged out)' "$PURGE"/inventory-bucket.txt "$PURGE"/inventory-local.txt
fi
```
Success looks like three lines for each backfile, then the inventory's backfile lines: the backfiles
and, from 2021 on, any camp year kept as one. A backfile not yet imported has `0` everywhere; in prod,
which receives backfiles by dev's hand publish, so may one that dev holds. The counts go to the
review in step 10. Nothing is deleted: a backfile goes by removal or a later policy version only.

## Step 9 — The end of the environment

**No working copy left.** Run [Step 1](#step-1--no-working-copy-left-on-this-mac)'s block again: it
prints `restored copies: 0` and `restored before the marker: 0`. This purge restored nothing, so a directory it
lists now was left by something else while the purge ran: deal with it as step 1 says.

**The window's scratch directory** holds listings of keys and counts (slugs, dates, digests and
version ids), no school, team code or card text. Once the counts of step 10 are written down, delete
it and close the window.

**Operator command** (expected runtime seconds)
Where: your Mac, in the purge window, last
```bash
case "$PURGE" in */annual-purge-dev-*|*/annual-purge-prod-*) rm -rf "$PURGE" && echo "removed the purge's scratch directory" ;; *) echo "STOP: PURGE is not this runbook's scratch directory" ;; esac
```
Success looks like `removed the purge's scratch directory`.

**Then prod.** A new window, the window block with `PURGE_ENV=prod` and the same `WINDOW_START`, and
steps 1 to 9 again. In prod: the run lock is none until the pilot's promotion, the bucket holds no
run-state bundle, prod's data directory holds no store, and the pilot's index and the landscape
bundles are there only once they have been published to prod.

## Step 10 — Record the counts

The policy asks for the purge's counts in `docs/data/`. Paste these into a session, which commits
them to `docs/data/annual-purge-<year>.md` (a new file each year, first line its `docs-index`
comment), counts only: no key, no path, no school, team code or name.

| Environment | What | From |
|---|---|---|
| dev, prod | Data directories besides dev's and prod's, at the start and at the end | Steps 1 and 9 |
| dev, prod | School-view bucket versions and local files deleted, and bundles listed | Step 2's dry run before and after |
| dev, prod | The inventory's count line for `bucket`, `bundle` and `local` | Step 3 |
| dev, prod | Each `PURGE` and `STOP` line, as printed (a slug, dates and counts), and what the PM ruled | Steps 3 and 4 |
| dev, prod | The index's count line; the prune's version, delete marker and key counts; this Mac's index builds | Step 5 |
| dev, prod | Keys, noncurrent versions and how many are past the lifecycle | Step 6 |
| dev, prod | Built files in the bucket and on this Mac; the `built:` count line | Step 7 |
| dev, prod | Each backfile's manifests, sources and parsed objects, with bytes | Step 8 |

## When something stops

| What you see | What it means | What to do |
|---|---|---|
| `STOP: it is Wednesday …` | The cloud run's day | Run the purge on another day |
| `STOP: the run lock is held …` | A run or a locked command is writing the bucket | Wait for it (`debate-research caselist runs --remote --last 1`), then run the block again |
| `STOP: … holds no run lock …` (dev) | The dev bucket should hold a lock since the cutover | Stop, and tell the PM |
| `STOP: a DEBATE_ variable is set …` | An override from another step is in this shell | Open a new window and paste the window block again |
| `command not found: purge_guard` | The block was pasted into a window without the window block | Paste it in the purge window |
| Step 2's `STOP: <key> is neither a school view …` | A bundle holds a file neither list names | Tell the PM the key; delete nothing |
| Step 3's `PURGE` line | A caselist or camp year from before 2021-22 | Step 4; the rest of it goes to the PM |
| Step 3's `STOP … not in caselist.backfile_caselists` | A season left the window and the setting does not name it a backfile | The PM: a reviewed profile change, before the next purge |
| Step 3's `STOP … nothing dates it`, or a key it does not know | A store holds something this runbook cannot place | The PM, with the line |
| `EXPIRED STOPS` | The lifecycle left versions past their age | The PM, with the lines; no hand delete |

## What has no command yet

Each of these is named in the session report of `v1-e30-t28` for the PM to file. None is worked
around by hand here.

1. **Purging a caselist of a season before 2021-22**: its sources, manifests and records, its parsed
   store, its rows in the run-state bundle and the bundle's noncurrent versions, its inbox archives,
   and this Mac's landscape caches, in each bucket and here, without suppressing it, logging a request
   or holding a path. `caselist remove` does each of these for a takedown only.
2. **The same for an OpenEv camp release** of a topic year before 2021.
3. **This Mac's own search-index builds** (`tub-index/`), which only the next local build prunes.
4. **The model cassettes recorded before `v1-e32-t31`**, which name no caselist: step 4 reports them
   as unattributed, and no caselist's purge reaches them; only a takedown's form
   ([caselist-removal.md](caselist-removal.md#the-model-stages-cassettes-e32), `v1-e32-t36`) deletes
   them. Every cassette recorded or replayed since names its caselists, and step 4 deletes one
   caselist's alone.
5. **Noncurrent versions under the rest of `reports/`, `uploads/` and `exports/`**, which no profile
   may list, so step 6 cannot check them.
6. **A working copy restored before the marker is found by its database file**, three levels down: a
   copy a build before `v1-e40-t21` restored deeper is not seen. Every copy restored since carries the
   marker, which step 1 finds at any depth.

## References

- [docs/policies/caselist-data-use.md](../policies/caselist-data-use.md): the policy, especially
  [Retention](../policies/caselist-data-use.md#retention) and permitted use 8, Backfiles.
- [caselist-removal.md](caselist-removal.md): the removal runbook, whose P3 and P4 this runbook uses,
  and whose school-view purge section moved here.
- [caselist-backfiles.md](caselist-backfiles.md): what a backfile is, and the setting that names one.
- [caselist-cutover.md](caselist-cutover.md): the run lock, the restored working copy and its deletion.
- [caselist-cloud-run.md](caselist-cloud-run.md): the cloud run's Wednesday schedule.
- [evidence-store.md](evidence-store.md) and
  [evidence-store-layout.md](../architecture/evidence-store-layout.md): the profiles, their grants and
  the bucket's prefixes.
- `plan_specs/v1/e32-argument-landscape/t13-removal-reaches-landscape-school-views.yaml`: the school
  views and the removal profile's grant to delete them.
