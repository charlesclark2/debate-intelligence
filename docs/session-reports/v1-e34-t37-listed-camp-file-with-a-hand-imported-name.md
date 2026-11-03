# Session report: v1-e34-t37-listed-camp-file-with-a-hand-imported-name

| | |
|---|---|
| Task | `v1-e34-t37-listed-camp-file-with-a-hand-imported-name` — A listed camp file is not taken as already imported because a file of another camp shares its name |
| Spec | [`plan_specs/v1/e34-caselist-sync/t37-listed-camp-file-with-a-hand-imported-name.yaml`](../../plan_specs/v1/e34-caselist-sync/t37-listed-camp-file-with-a-hand-imported-name.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t37-listed-camp-file-with-a-hand-imported-name` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The count came first (PM ruling 1), and it is zero in every record read, so under ruling 2 there
is **no rule change** and the Goal is `Succeeded` on ac1's "count recorded". Over the Mac's 17 sync
run summaries (2026-09-24 to 2026-10-22) and the cloud run's 3 (2026-10-25 to 2026-10-28, read by
the operator from its log), **9,475 listed-file decisions** produced 7 `already_imported` files
(2 on the Mac, 5 in the cloud), **every one matched by its own id** (a row named `openev-<id>-…`).
None was held by name, so none matched a row in another camp folder. The zero comes from the
configuration: no run sets `caselist.openev_event`, so 498 listed files stop at
`no_event_configured` before the matcher in every run. Only the few with an event tag of their own
(LD) reach it, and the LD release holds only the sync's own rows. All 105 hand-imported rows are in
the Policy release, which no listed file reached. The PM may want to read Follow-up work first:
the case this task guards against becomes reachable the day an OpenEv event is configured.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `listed-camp-file-with-a-hand-imported-na` (Same name, other camp) | DONE | Counted on the Mac and in the cloud: zero, so no rule change (ruling 2) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the count is recorded before any rule; if it finds any, tests shown failing first | PASS | Recorded below, before any rule: 0 by name on the Mac (17 runs) and 0 in the cloud (3 runs). It found none, so its second half (tests failing first) does not apply, under ruling 2 |
| Node: Same name, other camp tests pass (`uv run pytest packages/debate_core/tests -k openev`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests -k openev -q -n auto -p no:randomly` → `242 passed in 52.22s`. No code changed, so these are the existing tests |

### The count, on the Mac

Read-only, from a scratch script that prints counts only (no path, file name or camp name),
about 0.1 s. It reads every record that can carry per-file decisions:

* `~/.debate-research/dev/caselist-sync-runs/*.json`: 17 run summaries, the only records with
  `openev_selections`. The first is 2026-09-24T04:23Z and the last 2026-10-22T05:20Z.
* `~/.debate-research/dev/caselist-sync-runs.jsonl` (16 lines) and
  `caselist-sync-run-details.jsonl` (3 lines): read, and neither carries per-file decisions.
* `~/.debate-research/reimport-working-copy/`: 21 records, none with per-file decisions.

For each listed file decided `already_imported`, it asks the release manifest
(`objects/manifests/openev/<year>-<event>.jsonl`) for a classified row whose file name starts
`openev-<that id>-`. A file with such a row was held by id (`_match_listed_openev`'s first rule).
One without it went by name, by an inbox digest or by the delivery record, and only those could be
a match across folders.

| | Count |
|---|---|
| Run records with per-file OpenEv decisions | 17 |
| Listed-file decisions in them | 7,972 |
| `no_event_configured` | 7,968 (498 in each of 16 runs) |
| `download` | 2 (2026-10-14T11:00Z; both tagged LD) |
| `already_imported` | 2 (2026-10-22T05:20Z; the same two LD files) |
| `already_imported` by id | 2 |
| **`already_imported` by name (not by id)** | **0** |
| **of those, matching a row in another camp folder** | **0** |

What the release manifests hold, counted the same way. `2026-ld`: 2 rows, both the sync's own
(`openev-<id>-…`). `2026-policy`: 105 hand-imported rows, each one folder deep (`<camp>/<file>`),
and no sync row.

### The count, in the cloud

Read by the operator with the block under Operator follow-ups (counts only, ~30 s): every
`caselist pull` summary line in the `debate-dev-caselist-run` log, and for each file decided
`already_imported`, whether the dev bucket's release manifest has a row named after its id. Since
the cutover the run's home is dev and prod is published by hand (ADR-0020 (7)), so dev's log is the
only cloud record. I tested the script offline beforehand: a fake `aws` on `PATH` served the Mac's
manifests, a synthetic log of the 2026-10-22 summary reproduced the Mac's counts, and the same
summary with its two ids shifted counted `2` not by id. Pasted back on 2026-11-02:

| Run | Decisions |
|---|---|
| 20261025T022701Z (dry run) | 498 `no_event_configured`, 3 `download` |
| 20261026T040426Z | 498 `no_event_configured`, 2 `already_imported`, 1 `download` |
| 20261028T110536Z | 498 `no_event_configured`, 3 `already_imported` |

| | Count |
|---|---|
| Summary lines read | 3 |
| Listed-file decisions | 1,503 |
| `already_imported` | 5 |
| `already_imported` by id | 5 |
| **`already_imported` not by id** | **0** |
| Release manifest unreadable | 0 |

Each cloud run lists 501 files, one more than the Mac's: a third LD-tagged file. It was downloaded
on 2026-10-26 and held by id on 2026-10-28, as the matcher's first rule says. One observation I
cannot explain from counts: the 2026-10-25 dry run decided all three LD files `download`, including
the two the Mac held by id three days earlier, although a bucket-mode dry run restores the run-state
bundle (`bucket_run.py`). Perhaps that bundle did not yet hold the LD release on the cutover day.
It concerns the id rule, not the name rule, and a dry run fetches nothing, so I leave it to the PM.

### Closing checks

| Check | Result |
|---|---|
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run` | 40 test files (the always-run list and the spec tests: only the spec and this report changed); `1901 passed in 89.62s`, exit 0 |
| `uv run ruff format --check .` | `1880 files already formatted` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `pyright` | Not run: no Python changed |
| `uv run python scripts/check_command_blocks.py --base origin/dev` | `OK: no # comments in 664 shell code blocks in 241 Markdown files (1 session reports changed since origin/dev)` |
| `uv run scripts/validate_specs.py` (after `set-phase … Succeeded`) | `OK: 585 files, 41 epics, 522 tasks, 22 releases` |

## Files changed

* `plan_specs/v1/e34-caselist-sync/t37-listed-camp-file-with-a-hand-imported-name.yaml`: Goal
  `Succeeded`.
* `docs/session-reports/v1-e34-t37-listed-camp-file-with-a-hand-imported-name.md`: this report.

No code and no test changed: the count found nothing, and ruling 2 stops the task there. PM ruling
4's tests and mutants and ruling 5's download estimate apply only to a rule change, so none were made.

## Deviations from the spec

1. **One network call besides `scripts/task sync` (ruling 6).** Before closing I ran
   `git fetch origin dev` to check whether the PM had amended this spec on dev. It was read-only and
   moved only `origin/dev`; the spec on dev differs from this branch only in its phase (`Pending`
   there, `InProgress` here before this report). I should have asked, or left the check to
   `scripts/task sync`.

## Decisions and assumptions

1. **"By name alone" is counted as "not by id".** The run records keep no listed path (policy rule
   4), so a by-name match cannot be seen directly. A listed file decided `already_imported` with no
   row named after its id is the most it can be. On the Mac that set is empty, so the folder
   question never arises. Had it not been empty, the folder comparison would have needed the
   listing's paths, which only the API has.
2. **The cloud's records were read, not argued away.** The configuration made a non-zero cloud
   count unlikely, since the cloud run sets no OpenEv event either. But a newly tagged upload could
   have reached the matcher, and one did (the third LD file), so the count was worth the
   operator's half minute (ruling 1).
3. **Dry runs are counted.** A dry run decides the same way and records its decisions; leaving it
   out would not change any count here (its decisions are `download` and `no_event_configured`).

## Operator follow-ups

**The cloud run's count**, run by the operator on 2026-11-02; the result is under "The count, in the cloud". Kept so the count can be repeated (read-only, counts only; expected runtime ~30 s). Since the cutover the
weekly run is dev's cloud run, and prod is published by hand (ADR-0020 (7)), so dev's run log is
the only other record. A cloud run keeps its per-file decisions nowhere in the bucket: its summary
file stays in the task's working copy, which is not among the saved state files. But the task runs
`debate-research --json caselist pull`, so every run's summary, `openev_selections` included, is one
JSON line in `debate-dev-caselist-run`, kept 90 days. The block reads those lines, and for each file
decided `already_imported` it reads that release's manifest from the dev bucket and asks whether a
row is named after the file's id. It prints run ids (timestamps) and counts, never a path or a
name. It writes nothing but a temporary file of log events, which it removes.

Where: your Mac, any shell with no `caselist pull` running.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e34-t37-listed-camp-file-with-a-hand-imported-name
BUCKET=$(AWS_PROFILE=debate-admin terraform -chdir=/Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence/infrastructure/envs/dev output -raw evidence_bucket_name)
T37_EVENTS=$(mktemp)
if [ -z "${BUCKET}" ]; then echo "STOP: terraform output gave no bucket name"; else aws logs filter-log-events --profile debate-dev-caselist-run-deployer --region us-east-1 --log-group-name debate-dev-caselist-run --filter-pattern '"caselist pull"' --output json > "${T37_EVENTS}" && python3 -I - "${BUCKET}" "${T37_EVENTS}" <<'COUNT'
import json, re, subprocess, sys
from collections import Counter
bucket, events_path = sys.argv[1], sys.argv[2]
named = re.compile(r"^openev-(\d+)-")
separators = re.compile(r"[\\/]+")
runs = []
for event in json.load(open(events_path))["events"]:
    try:
        body = json.loads(event["message"])
    except ValueError:
        continue
    if isinstance(body, dict) and body.get("command") == "caselist pull" and isinstance(body.get("data"), dict):
        runs.append(body["data"])
manifests = {}
def ids_with_rows(year, event):
    release = "%04d-%s" % (year, event.lower())
    if release not in manifests:
        got = subprocess.run(["aws", "s3", "cp", "s3://%s/manifests/openev/%s.jsonl" % (bucket, release), "-", "--profile", "debate-dev-evidence"], stdin=subprocess.DEVNULL, capture_output=True, text=True)
        ids = None
        if got.returncode == 0:
            ids = set()
            for line in got.stdout.splitlines():
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and row.get("classification") is not None and isinstance(row.get("path"), str):
                    match = named.match(separators.split(row["path"])[-1])
                    if match:
                        ids.add(int(match.group(1)))
        manifests[release] = ids
    return manifests[release]
totals = Counter()
for run in sorted(runs, key=lambda one: str(one.get("run_id"))):
    selections = run.get("openev_selections") or []
    totals["runs"] += 1
    totals["listed-file decisions"] += len(selections)
    print("run %s%s: %s" % (run.get("run_id"), " (dry run)" if run.get("dry_run") else "", dict(Counter(one.get("decision") for one in selections))))
    for one in selections:
        if one.get("decision") != "already_imported":
            continue
        totals["already_imported"] += 1
        held = ids_with_rows(one.get("year"), one.get("event") or "")
        if held is None:
            totals["already_imported, release manifest unreadable"] += 1
        elif one.get("openev_id") in held:
            totals["already_imported by id"] += 1
        else:
            totals["already_imported NOT by id"] += 1
print("summary lines read: %d" % totals["runs"])
for key in ("listed-file decisions", "already_imported", "already_imported by id", "already_imported NOT by id", "already_imported, release manifest unreadable"):
    print("%s: %d" % (key, totals[key]))
COUNT
fi
rm -f "${T37_EVENTS}"
```

Success looks like one `run <id>: {...}` line per cloud run, then `summary lines read:` above zero
and `already_imported, release manifest unreadable: 0`. The answer is `already_imported NOT by id`:
`0` means no cloud run held a listed file by name either. Paste the whole output back; it holds
counts only. `summary lines read: 0` means the log has no run summary to read, and that goes to the
PM rather than counting as zero.

## Follow-up work

1. **The guarded case becomes reachable when an OpenEv event is configured (E34).** Today 498 of
   about 500 listed files never reach `_match_listed_openev`, because `caselist.openev_event` is
   unset everywhere (Mac, cloud task definition, bundled profiles). Setting it to Policy would send
   all of them to a release whose 105 hand-imported rows are each `<camp>/<file>`. A listed file
   whose name equals one of those rows', with no listed file of that camp and name, would then be
   held by name from another camp, which is the case this task describes. How many would be cannot
   be counted from anything stored: it needs the listing's paths, which only the API has (a network
   call, the operator's). I suggest that whatever task configures an OpenEv event first runs this
   count again, plus a counts-only comparison of the listing's names with those rows' names, and
   reopens this rule if it is non-zero.
2. **A cloud run's per-file decisions live only in its log, for 90 days.** The summary file stays in
   the task's working copy and is not among the saved state files, so after 90 days no record says
   what a cloud run decided about a listed file. That was enough here. If counts like this one are
   expected again later in the season, the PM may want the summary kept (an E40 question).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-02

**Notes:**

The count settles it: zero by name in every record, Mac and cloud, so ruling 2 stops the task with no
rule change, and the report says exactly why the zero holds.

1. **ac1 passes.** 9,475 listed-file decisions over 20 runs (17 on the Mac, 3 in the cloud read by the
   operator's counts-only block); 7 `already_imported`, all by id; none by name, so none across camp
   folders. The cloud block was tested offline against a fake `aws` before it was handed over, which
   is why its first run could be trusted.
2. **Why it is zero:** `caselist.openev_event` is unset everywhere, so 498 of about 500 listed files
   stop at `no_event_configured` before the matcher. Follow-up 1 is right that the guarded case
   becomes reachable the day an event is configured. The PM asks the coach whether the weekly sync
   should import camp files by event; any task that configures one starts with this count again and
   a counts-only comparison of the listing's names with the 105 hand-imported rows.
3. **The dry run of 2026-10-25** deciding `download` for files the Mac held by id: it fetched nothing,
   and the next real run held them by id, which fits a run-state bundle without the LD release on the
   cutover day. Noted; no task.
4. **Deviation 1 (`git fetch origin dev`):** noted, and thank you for saying so. The rule stands:
   `scripts/task sync` is the only network call a session makes.
5. **Follow-up 2** (a cloud run's per-file decisions kept beyond the log's 90 days) is filed for E40
   at p3 in the next batch.
6. **Closing checks:** the affected set ran in full (40 files, 1,901 passed); ruff, lint-imports, the
   command blocks and the specs are clean; no Python changed.
7. **Merge:** a plain `scripts/task pr` once `ci` is green. The Goal is `Succeeded`.
