<!-- docs-index: The register of caselist and OpenEv removal requests, one row per request id; no school, team code, filename or name -->
# Caselist removal requests

The register of takedown requests handled under the
[data-use policy](../policies/caselist-data-use.md#removal), kept by the operator as step 1 and step
10 of the [removal runbook](../runbooks/caselist-removal.md) say. One row per request id.

**No school name, team code, filename or personal name goes here**, or in the commit that changes
this file. The register is a count-and-code record: the identifying details stay in the operator's
mailbox. The machine-readable record (request id, date, reason code, environment, sha256 values and
counts) is the removal log the `remove` command writes, on the operator's machine at
`<data_dir>/suppression/removal-log.jsonl` and in each bucket at
`manifests/_suppression/removal-log.jsonl`.

Real requests are numbered from `RM-<year>-01`. Ids from `RM-<year>-90` up are kept for operator
exercises, so an exercise never takes a number a requester was given.

## Requests

| Request id | Received | Requester category | Reason code | Scope | Outcome |
|---|---|---|---|---|---|
| `RM-2026-90` | 2026-10-01 | None: an operator exercise, not a request | `POLICY` | One synthetic team, all snapshots, in the synthetic caselist `testcl26`; dev only | **Completed in dev on 2026-10-01** (v1-e30-t07 real-IAM exercise, on commit `9ede19e`); see the note below |

### `RM-2026-90`: the 2026-10-01 dev exercise on synthetic data

This proved the takedown end to end under the real `EvidenceRemoval` profile, which moto cannot
test (session report `docs/session-reports/v1-e30-t07-source-removal.md`). It used only the
repository's synthetic fixtures (`tests/fixtures/caselist/build_synthetic_archives.py`). No real
disclosure was involved, and no one is waiting for a confirmation.

- **Result.** The removal log holds one `COMPLETED` entry, which is the run whose counts are
  below. Everything was synthetic; nothing was left in place except as shared.
  - **Removed:** 3 sources, everywhere.
  - **Withdrawn, not removed:** 1 source shared with another synthetic team. Only this team's copies
    were withdrawn; the file was kept for the other holder.
  - **This machine:** 16 records and 3 files deleted.
  - **Bucket:** 7 object versions deleted.
  - **Manifests:** 8 rewritten without 42 rows.
  - **Suppression list:** 5 entries appended (3 whole-file, 2 for this team's paths to the shared
    file).
- **Snapshots affected:** 2026-09-01 to 2026-09-22 (4).
- **Prod:** not run. This is an exercise; the policy's dev-then-prod order applies to real requests.
- **The next archive:** the 2026-09-29 import reported `SUPPRESSED 4`. The publish that followed
  uploaded none of it, and `caselist status` agreed.
- **An earlier attempt the same day:** it stopped before changing anything. The takedown profile's
  read of a removal log that did not exist yet was refused; that was fixed in `d26cb32`. That
  attempt deleted nothing, appended nothing, and wrote no log entry. So the dev log holds only the
  completed run's entry.
- **Permanent entries.** The dev suppression list and removal log now hold these 5 entries and that
  1 entry permanently, because both are append-only. They name only synthetic sha256 values. No
  `unsuppress` is planned: the synthetic files have no reason to come back.
