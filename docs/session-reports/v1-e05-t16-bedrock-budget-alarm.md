# Session report: v1-e05-t16-bedrock-budget-alarm

| | |
|---|---|
| Task | `v1-e05-t16-bedrock-budget-alarm` — An AWS budget alarm on the account's model spend, $100 a month with a first notice at $50 |
| Spec | [`plan_specs/v1/e05-model-router/t16-bedrock-budget-alarm.yaml`](../../plan_specs/v1/e05-model-router/t16-bedrock-budget-alarm.yaml) |
| Epic / release | `v1-e05-model-router` / `v1.2` |
| Branch | `task/v1-e05-t16-bedrock-budget-alarm` |
| Session status | IN PROGRESS: stopped at the counts checkpoint (ac1), waiting for the operator's output and the PM's ruling <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

<!-- 3-6 sentences: what was built, how it fits the epic, anything the PM should look at first. -->

## Plan nodes

<!-- One row per Plan graph node, in the order they were completed. -->

| Node | Status | Notes |
|---|---|---|
| | | |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| | | |

## Files changed

<!-- Group by package or directory; one line on why each group changed. -->

## Deviations from the spec

None.

## Decisions and assumptions

<!-- Choices the spec left open, with the reasoning. -->

## Operator follow-ups

<!-- Commands the operator must run (anything over ~2 minutes), with where to run them, the exact
command, expected runtime and what success looks like. Also GitHub/AWS settings to change. -->

### The counts (ac1), read-only, before the filter is written

Where: any terminal on your Mac, signed in as `debate-admin` (`aws sso login --profile debate-admin`
first if the session has expired). Expected runtime: under a minute. It makes seven Cost Explorer
requests, all reads, and changes nothing. The first request only checks that Cost Explorer can be
read; if it cannot (not enabled, or the role may not read it), the block prints `STOP` and runs
nothing more. It prints no account id.

```bash
if ! aws ce get-cost-and-usage --profile debate-admin --time-period Start=2026-10-01,End=2026-10-02 --granularity MONTHLY --metrics UnblendedCost --query 'ResultsByTime[0].TimePeriod.Start' --output text; then
  echo "STOP: Cost Explorer could not be read as debate-admin (not enabled, or this role may not read it). Paste this output back and run nothing more."
else
  rows='(.ResultsByTime[].Groups[] | select((.Metrics.UnblendedCost.Amount | tonumber) != 0) | (.Keys | join("\t")) + "\t" + .Metrics.UnblendedCost.Amount), (if .NextPageToken then "INCOMPLETE: Cost Explorer returned more pages than this listing shows" else empty end)'
  for month_start month_end in 2026-09-01 2026-10-01 2026-10-01 "$(date +%F)"; do
    echo "== ${month_start} to ${month_end}, by service and usage type (USD, non-zero rows)"
    aws ce get-cost-and-usage --profile debate-admin --time-period Start=${month_start},End=${month_end} --granularity MONTHLY --metrics UnblendedCost --group-by Type=DIMENSION,Key=SERVICE Type=DIMENSION,Key=USAGE_TYPE --output json | jq -r "$rows" | sort
    echo "== ${month_start} to ${month_end}, by service and Project tag (USD, non-zero rows)"
    aws ce get-cost-and-usage --profile debate-admin --time-period Start=${month_start},End=${month_end} --granularity MONTHLY --metrics UnblendedCost --group-by Type=DIMENSION,Key=SERVICE Type=TAG,Key=Project --output json | jq -r "$rows" | sort
    echo "== ${month_start} to ${month_end}, by record type (USD, non-zero rows)"
    aws ce get-cost-and-usage --profile debate-admin --time-period Start=${month_start},End=${month_end} --granularity MONTHLY --metrics UnblendedCost --group-by Type=DIMENSION,Key=RECORD_TYPE --output json | jq -r "$rows" | sort
  done
fi
```

Success looks like: three listings for September and three for October so far, each a list of
tab-separated names and amounts, and no `INCOMPLETE` line. Paste the whole output back into the
session; the report records the names only.

## Follow-up work

<!-- Bugs, gaps or ideas outside this task's scope, each with the task or epic it belongs to.
The PM decides whether they become spec changes or new tasks. -->

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
