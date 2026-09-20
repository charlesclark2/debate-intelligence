# Runbook: removing a caselist or OpenEv source on request

| | |
|---|---|
| Purpose | Honour a removal request under the [caselist and OpenEv data-use policy](../policies/caselist-data-use.md) |
| Who runs it | The operator (Charlie). Not an agent session, not CI |
| How long | 15–30 minutes of attention, spread over the 7-day response window |
| Destructive? | **Yes.** It deletes objects and all of their noncurrent versions in dev and prod |
| Tooling | `debate-research caselist remove` (v1-e30-t07). Until that ships, use the [manual procedure](#manual-procedure-until-v1-e30-t07-ships) |

Removal is not a negotiation. A team asks, and their disclosure comes out. This runbook exists so
that it comes out *completely* — local store, both buckets, every noncurrent version, the parsed
cards, and the built files that quoted it — and so that next week's cumulative archive cannot put
it back.

## Before you start

- [ ] The data-use policy is approved, or the removal is being run *because* something was
      imported outside the policy.
- [ ] You can sign in to the dev and prod AWS accounts with the SSO profiles from v1-e29-t01.
- [ ] You know which environment each command targets. `DEBATE_ENV` selects it; prod additionally
      requires `--confirm-prod`.
- [ ] You have the request in writing (email is fine).

## Response clock

| Step | Deadline from the request |
|---|---|
| Acknowledge (step 2) | 3 business days |
| Removed from dev and prod (steps 4–7) | 7 calendar days |
| Built files flagged and withdrawn or rebuilt (step 8) | 7 calendar days |
| Confirmation to the requester (step 10) | 7 calendar days |

## Step 1 — Record the request

Give the request an id and open a register entry at
`docs/data/caselist-removal-requests.md` (create the file on the first request). Record:

| Field | Example | Notes |
|---|---|---|
| Request id | `RM-2026-01` | `RM-<year>-<sequence>` |
| Received | `2026-09-19` | Date only |
| Requester category | `disclosing team` | One of: disclosing team, school or district, site administrator, camp, own coach |
| Reason code | `REQUESTED_BY_TEAM` | `REQUESTED_BY_TEAM`, `REQUESTED_BY_SCHOOL`, `REQUESTED_BY_SITE_ADMIN`, `REQUESTED_BY_CAMP`, `POLICY` (imported outside policy), `LEGAL` |
| Scope | `one team, all snapshots` | What the requester asked to have removed |
| Outcome | filled in at step 10 | |

**No school name, team code, filename or personal name goes in the register**, or in the commit
message, or in this repository at all. The register is a count-and-code record; the identifying
details stay in your mailbox. The machine-readable log (request id, date, reason code,
environment, sha256 values) is written by the `remove` command itself.

## Step 2 — Acknowledge

Reply within 3 business days. Something like:

> Thanks for reaching out — we've logged this as `RM-2026-01` and we're removing it. You don't need
> to explain why. We'll delete the files and everything we derived from them from both of our
> environments, and add them to a suppression list so next week's caselist archive can't bring them
> back, within 7 days. We'll confirm when it's done. One thing we can't do is remove the disclosure
> from OpenCaselist itself — that request goes to the site.

## Step 3 — Identify what to remove

```bash
# What is in the store for this environment, and does it match S3?
DEBATE_ENV=dev uv run debate-research caselist status
```

Pick the selector that matches the request:

- **A specific file:** `--source <sha256>`.
- **Everything one team disclosed, across every snapshot:** `--team <caselist>/<school>/<team>`.

If the request names a tournament and round rather than a team, resolve it to a team selector with
`caselist status` output first. If the request is broader than one team (a whole school, a whole
caselist), run one `--team` removal per team so the register and the log stay legible.

## Step 4 — Dry run in dev

The command is a dry run by default. Nothing is deleted without `--execute`.

```bash
DEBATE_ENV=dev uv run debate-research caselist remove --team hsld26/<school>/<team>
```

Read the plan before going further. Confirm:

- [ ] The source count matches what the requester described.
- [ ] The listed disclosure records, manifest rows, local blobs and S3 objects (with their version
      counts) look right.
- [ ] **Shared references.** If the plan lists sources also disclosed by another team, or that are
      also a camp file, decide explicitly: without `--include-shared` only this team's `Disclosure`
      records are dropped and the shared blob stays; with it, the blob goes for everyone. Default to
      *without*, and tell the requester what stayed and why (step 10).

## Step 5 — Execute in dev

```bash
DEBATE_ENV=dev uv run debate-research caselist remove --team hsld26/<school>/<team> --execute
```

## Step 6 — Verify dev

```bash
# 1. The store and S3 agree and the sources are gone.
DEBATE_ENV=dev uv run debate-research caselist status

# 2. Re-importing a snapshot that still contains the file reports it as SUPPRESSED,
#    stores no blob and writes no manifest row.
DEBATE_ENV=dev uv run debate-research caselist import <archive> --caselist hsld26 --snapshot <date>
```

- [ ] `caselist status` is clean (exit 0, no drift).
- [ ] The re-import counts the file as `SUPPRESSED`.
- [ ] No `raw/` or `parsed/` object for those sha256 values remains — **including noncurrent
      versions**. Check with the AWS CLI if you want belt and braces:
      `aws s3api list-object-versions --bucket <dev-evidence-bucket> --prefix raw/hsld26/<sha256>`
      returns nothing.

## Step 7 — Prod

Dry run first, every time. Prod needs `--confirm-prod` on top of `--execute`.

```bash
DEBATE_ENV=prod uv run debate-research caselist remove --team hsld26/<school>/<team>
DEBATE_ENV=prod uv run debate-research caselist remove --team hsld26/<school>/<team> --execute --confirm-prod
DEBATE_ENV=prod uv run debate-research caselist status
```

- [ ] The prod dry-run plan matches the dev one (a difference means the two environments had
      drifted — investigate before executing).
- [ ] `caselist status` is clean afterwards.

## Step 8 — Suppression and built files

- [ ] Confirm each sha256 is on the suppression list in both environments. The list is append-only
      JSONL, merged as a set union between local and S3 on every run, at
      `manifests/_suppression/suppression-list.jsonl`.
- [ ] Find every built file whose provenance sidecar cites a removed sha256 (E33). Withdraw it from
      use immediately and rebuild it without those cards before anyone reads it in a round.
- [ ] If the file was shared inside the team outside the evidence store — a copy in someone's
      Dropbox, a printout in a tub — retrieve and destroy it. Per policy there should be none; if
      there is, note it in the register as an incident.
- [ ] **V2 only:** mark the matching tub files `REMOVED` so they stop listing and presigning
      (v2-e35-t05). The tub takedown flow uses this same suppression list.

## Step 9 — Check nothing re-imports it

At the next weekly import (or immediately, if you have the next archive on hand):

- [ ] The importer reports the sha256 as `SUPPRESSED`.
- [ ] `caselist publish` does not upload it.

Once E34 is running, the scheduled download inherits this check because everything it downloads
goes through the same importer.

## Step 10 — Close it out

- [ ] Fill in the Outcome column of the register entry: sources removed, snapshots affected,
      whether anything was left in place as shared, and the date completed.
- [ ] Reply to the requester confirming completion, naming what was removed in their terms (their
      team, their rounds) and anything that was not, with the reason.
- [ ] Commit the register update. No personal data in the diff or the commit message.

## If you removed the wrong thing

The removal is destructive: noncurrent versions are purged, so there is no S3 version to restore
from. Recovery means re-importing the file from the original weekly archive — which will be
refused while its sha256 is on the suppression list. The suppression list is append-only and
v1-e30-t07 does not yet specify an un-suppress path; until it does, treat an erroneous removal as
an escalation:

1. Stop. Do not run more removals.
2. Keep the original archive; it is the only copy of the bytes.
3. Record the mistake in the register.
4. Un-suppressing requires a code change to v1-e30-t07 (a tombstone entry or a documented
   `--unsuppress`). Raise it as a spec change rather than hand-editing the JSONL, so dev and prod
   stay consistent.

This is the strongest argument for always running the dry run and reading it.

## Manual procedure (until v1-e30-t07 ships)

`caselist remove` does not exist yet, and neither do the importer (v1-e30-t03) or the publisher
(v1-e30-t05). If a removal request arrives before they do, the corpus is only in whatever the
operator has downloaded locally, and the procedure is:

1. **Register and acknowledge** — steps 1 and 2 above, unchanged.
2. **Local files.** Delete the matching files from the downloaded archives and from any unpacked
   copy on the laptop. The archives themselves are cumulative `.zip` files; keep the `.zip`
   (it is the source of truth for re-import) but record the sha256 values so they can be added to
   the suppression list the moment t07 ships. Keep that list of sha256 values somewhere outside the
   repository until there is a suppression list to put them in.
3. **S3.** If anything was already published, delete the `raw/` and `parsed/` objects **and all
   noncurrent versions** with `aws s3api delete-object --version-id` per version, in dev then prod,
   and rewrite the affected manifests.
   > **Permissions note.** The `EvidenceOperator` permission set from v1-e29-t03 deliberately has
   > **no `s3:DeleteObject`**. A manual deletion needs an administrator profile, and this is the
   > same gap that `caselist remove` will hit in t07 — see open question 8 in the policy. Resolve it
   > before promising a 7-day removal window in practice.
4. **Built files.** Same as step 8 above, by hand against the provenance sidecars.
5. **Backfill the machine log.** When t07 ships, add each sha256 to the suppression list with the
   original request id, date and reason code, and re-run `caselist status` in both environments.

## References

- [docs/policies/caselist-data-use.md](../policies/caselist-data-use.md) — the policy this runbook
  implements, especially [Removal](../policies/caselist-data-use.md#removal).
- `plan_specs/v1/e30-caselist-ingestion/t07-source-removal.yaml` — the `caselist remove` command
  and the suppression list.
- `plan_specs/v1/e29-cloud-evidence-store/t03-evidence-buckets.yaml` — bucket lifecycle and the
  `EvidenceOperator` permission set.
- `plan_specs/v2/e35-debate-tub/t05-tub-access-and-removal.yaml` — the V2 takedown flow built on
  this suppression list.
