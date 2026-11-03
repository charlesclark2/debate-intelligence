# Session report: v1-e34-t37-listed-camp-file-with-a-hand-imported-name

| | |
|---|---|
| Task | `v1-e34-t37-listed-camp-file-with-a-hand-imported-name` — A listed camp file is not taken as already imported because a file of another camp shares its name |
| Spec | [`plan_specs/v1/e34-caselist-sync/t37-listed-camp-file-with-a-hand-imported-name.yaml`](../../plan_specs/v1/e34-caselist-sync/t37-listed-camp-file-with-a-hand-imported-name.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t37-listed-camp-file-with-a-hand-imported-name` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The count comes first (PM ruling 1). Over every sync run record on the Mac, 17 runs from
2026-09-24 to 2026-10-22, **no listed OpenEv file was decided `already_imported` by name**. Two were
decided `already_imported`, both matched by their own id (a row named `openev-<id>-…`), so **none
matched a row in another camp folder**. The zero is structural, not luck: no run configures
`caselist.openev_event`, so 498 of the 500 listed files stop at `no_event_configured` before the
matcher, and the two that carry an event tag (LD) meet a release manifest holding only the sync's
own rows. The 105 hand-imported rows are all in the Policy release, which no listed file reached.
The weekly run moved to the cloud on 2026-10-25. Its runs keep their per-file decisions only in
the run's CloudWatch log, so I wrote a counts-only operator block for them and am waiting for its
result. If it also shows none, the task stops here under ruling 2 with no rule change.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `listed-camp-file-with-a-hand-imported-na` (Same name, other camp) | IN PROGRESS | Mac count recorded; cloud count with the operator |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the count is recorded before any rule; if it finds any, tests shown failing first | IN PROGRESS | Mac count below; cloud count pending |
| Node: `uv run pytest packages/debate_core/tests -k openev` | NOT RUN yet | |

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

## Files changed

* `docs/session-reports/v1-e34-t37-listed-camp-file-with-a-hand-imported-name.md`: this report.

## Deviations from the spec

None.

## Decisions and assumptions

1. **"By name alone" is counted as "not by id".** The run records keep no listed path (policy rule
   4), so a by-name match cannot be seen directly. A listed file decided `already_imported` with no
   row named after its id is the most it can be. On the Mac that set is empty, so the folder
   question never arises. Had it not been empty, the folder comparison would have needed the
   listing's paths, which only the API has.

## Operator follow-ups

**The cloud run's count** (read-only, counts only; expected runtime ~30 s). Since the cutover the
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

None yet.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
