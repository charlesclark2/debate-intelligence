# Runbook: removing a caselist or OpenEv source on request

| | |
|---|---|
| Purpose | Honour a removal request under the [caselist and OpenEv data-use policy](../policies/caselist-data-use.md) |
| Who runs it | The operator (Charlie). Not an agent session, not CI |
| How long | 15–30 minutes of attention, spread over the 7-day response window |
| Destructive? | **Yes.** It deletes objects and all of their noncurrent versions in dev and prod |
| Tooling | `debate-research caselist remove` and `caselist unsuppress` (v1-e30-t07; the download inbox since v1-e30-t09) |

Removal is not a negotiation. A team asks, and their disclosure comes out. This runbook exists so
that it comes out *completely* — local store, both buckets, every noncurrent version, the parsed
cards, the archives and camp files `caselist pull` downloaded, and the built files that quoted it —
and so that next week's cumulative archive cannot put it back.

## Before you start

- [ ] The data-use policy is approved, or the removal is being run *because* something was
      imported outside the policy.
- [ ] You can sign in with the takedown SSO profiles `debate-dev-evidence-removal` and
      `debate-prod-evidence-removal` (`v1-e29-t03`; set up in
      [evidence-store.md](evidence-store.md)), **and** with the everyday `debate-dev-evidence` /
      `debate-prod-evidence` profiles. The dry run needs only the everyday one. `--execute` needs
      both: the takedown profile deletes and appends the suppression list, and the everyday one
      writes the rewritten manifests, because the takedown profile may write nowhere but
      `manifests/_suppression/`. The everyday one also reads the bucket's suppression list and
      removal log, because the takedown profile cannot list, so S3 refuses its read of one that
      does not exist yet instead of saying it is absent.
- [ ] You know which environment each command targets. `DEBATE_ENV` selects it; prod additionally
      requires `--confirm-prod`. `DEBATE_REMOVAL_PROFILE` names the takedown profile and is set
      only in the shell you run `--execute` from; no profile file sets it.
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

The command is a dry run by default. Nothing is written anywhere without `--execute`: no record, no
file, no object, no suppression or log line.

```bash
DEBATE_ENV=dev uv run debate-research caselist remove --team 'hsld26/<school>/<team>' \
    --request RM-2026-01 --reason REQUESTED_BY_TEAM
```

`--request` is the register id from step 1 and `--reason` its reason code; both are required, and
both are the only things besides sha256 values and dates that reach the suppression list and the
removal log. Quote the `--team` value: school names have spaces.

The plan prints, in order: **WILL BE REMOVED** (each file, every record of it, its local blob and
bucket objects with their version counts), **SHARED, KEPT** (files another team or a camp file also
holds: only this team's copies are withdrawn), **MANIFESTS REWRITTEN**, **DOWNLOAD INBOX** (every
file `caselist pull` downloaded that holds a removed file, and whether it is deleted or rewritten
without it; see step 8), the **SUPPRESSION ENTRIES** exactly as they will be written, **FOR THE
CONFIRMATION TO THE REQUESTER** (the facts for step 10: how many files, which weekly archives,
which tournament rounds, what was kept and what was not done), and **TO CARRY IT OUT**, the exact
`--execute` command. Add `--json` for the same plan as one
JSON object. With only the everyday profile signed in, the plan says *Versions not counted*: that
profile may not list object versions (session report v1-e30-t07, Operator follow-ups). `--execute`
lists and deletes every version with the takedown profile and reports how many.

Read the plan before going further. Confirm:

- [ ] The source count matches what the requester described.
- [ ] The listed disclosure records, manifest rows, local blobs and S3 objects (with their version
      counts) look right.
- [ ] **Shared references.** If the plan lists sources also disclosed by another team, or that are
      also a camp file, decide explicitly: without `--include-shared` only this team's `Disclosure`
      records and manifest rows are dropped and the shared blob stays, and each of this team's
      paths to it is suppressed on its own, so next week's archive cannot record it as theirs
      again; with it, the file goes for everyone. Default to *without*, and tell the requester what
      stayed and why (step 10).
- [ ] **`--source` on a shared file** is listed as *SHARED, SKIPPED* and nothing happens to it
      without `--include-shared`: there is no requesting team to withdraw it from.
- [ ] **The download inbox.** Each line under *DOWNLOAD INBOX* names a downloaded file, `delete` or
      `rewrite`, and why. An archive marked *waiting to be imported* must say `rewrite`: it is never
      deleted. A line starting `UNREADABLE` is a zip that cannot be opened, so it cannot be checked;
      move it out of the inbox before executing, or the run stops `INCOMPLETE` at it. A `NOTE` says
      an archive not yet imported holds files under the team's directory that the store has never
      seen, so nothing can select them yet: run `caselist pull` after this removal, then the same
      removal again (step 8).

## Step 5 — Execute in dev

```bash
aws sso login --profile debate-dev-evidence-removal
DEBATE_ENV=dev DEBATE_REMOVAL_PROFILE=debate-dev-evidence-removal uv run debate-research caselist remove \
    --team 'hsld26/<school>/<team>' --request RM-2026-01 --reason REQUESTED_BY_TEAM --execute
```

Before the first change the command proves the takedown profile can list, write and delete a
probe version under `manifests/_suppression/preflight/`. An unset `DEBATE_REMOVAL_PROFILE`, a
signed-out session, or the everyday profile named by mistake stops it there, with nothing changed.
It then appends the suppression entries first, deletes from the bucket, then from this machine — the
store, then the download inbox (step 8) — and writes one removal-log entry. If it stops part-way it
says so, logs `INCOMPLETE`, and the fix is to run the same command again. The inbox is changed only
while no `caselist pull` is running: if one holds the sync's lock, the removal stops `INCOMPLETE`
with *a caselist pull is running*, and you re-run it once the pull has finished.

## Step 6 — Verify dev

```bash
# 1. The store and S3 agree and the sources are gone.
DEBATE_ENV=dev uv run debate-research caselist status

# 2. Re-importing a snapshot that still contains the file reports it as SUPPRESSED,
#    stores no blob and writes no manifest row. An archive older than the newest one imported
#    needs --allow-out-of-order.
DEBATE_ENV=dev uv run debate-research caselist import <archive> --caselist hsld26 --snapshot <date>
```

- [ ] `caselist status` is clean (exit 0, no drift). It now also treats as drift any local manifest
      row the suppression list stops, and any current bucket object of a suppressed file.
- [ ] The `DONE` line counts the inbox files deleted and rewritten, and the dry run run again says
      *DOWNLOAD INBOX (…): nothing in it holds a removed file.*
- [ ] The re-import counts the file as `SUPPRESSED`.
- [ ] No `raw/` or `parsed/` object for those sha256 values remains — **including noncurrent
      versions**. Check with the AWS CLI if you want belt and braces:
      `aws s3api list-object-versions --bucket debate-dev-evidence-a7508de8 --prefix raw/caselist/hsld26/sha256/<ab>/<cd>/<sha256>`
      returns nothing. The key form is
      [docs/architecture/evidence-store-layout.md](../architecture/evidence-store-layout.md).

## Step 7 — Prod

Dry run first, every time. Prod needs `--confirm-prod` on top of `--execute`.

```bash
DEBATE_ENV=prod uv run debate-research caselist remove --team 'hsld26/<school>/<team>' \
    --request RM-2026-01 --reason REQUESTED_BY_TEAM
aws sso login --profile debate-prod-evidence-removal
DEBATE_ENV=prod DEBATE_REMOVAL_PROFILE=debate-prod-evidence-removal uv run debate-research caselist remove \
    --team 'hsld26/<school>/<team>' --request RM-2026-01 --reason REQUESTED_BY_TEAM --execute --confirm-prod
DEBATE_ENV=prod uv run debate-research caselist status
```

- [ ] The prod dry-run plan matches the dev one (a difference means the two environments had
      drifted — investigate before executing). The *DOWNLOAD INBOX* section may differ: each
      environment that pulls has its own inbox, and each environment's run purges its own.
- [ ] `caselist status` is clean afterwards.

## Step 8 — Suppression and built files

- [ ] Confirm each sha256 is on the suppression list in both environments. The list is append-only
      JSONL at `<data_dir>/suppression/suppression-list.jsonl` on this machine and
      `manifests/_suppression/suppression-list.jsonl` in each bucket, merged as a set union whenever a
      command holds both. `store sync` never copies it either way. The removal log sits beside it
      (`removal-log.jsonl`), one line per execution.
- [ ] Find every built file whose provenance sidecar cites a removed sha256 (E33). Withdraw it from
      use immediately and rebuild it without those cards before anyone reads it in a round.
- [ ] If the file was shared inside the team outside the evidence store — a copy in someone's
      Dropbox, a printout in a tub — retrieve and destroy it. Per policy there should be none; if
      there is, note it in the register as an incident.
- [ ] **V2 only:** mark the matching tub files `REMOVED` so they stop listing and presigning
      (v2-e35-t05). The tub takedown flow uses this same suppression list.
- [ ] **The download inbox: what the command did.** `caselist pull` downloads into an inbox —
      `caselist.inbox_dir` in the environment's profile, or `<data_dir>/inbox` when it is not set —
      and never clears it. `caselist remove --execute` purges it in the environment it runs in
      (`v1-e30-t09`), so after a `COMPLETED` run no file there holds a removed file, as itself or as
      a member of an archive. What it did to each file is what the plan's *DOWNLOAD INBOX* section
      said:
      - **Deleted:** a removed camp document (`openev-<id>-…`); a camp release whose every file was
        removed; and every weekly archive (`<slug>-weekly-<date>.zip`) whose week is already imported,
        because the store holds everything else in it and the pull never fetches an imported week
        again. Before deleting a camp file's copy it records in
        `<data_dir>/caselist-sync-openev-deliveries.json` which bytes that download held (digests
        only), so the next pull recognises the file as removed without fetching it.
      - **Rewritten, never deleted:** an archive downloaded but not yet imported — a weekly newer than
        the last week imported, or a camp release no manifest records. The next pull imports it from
        the inbox; deleting it would make the pull download it again, from the maintainer's five a day,
        with the removed files back in it. The rewrite leaves out only what the suppression list
        stops — the removed files, this team's copies of shared ones, and the junk naming them (macOS
        `._` sidecars, Word `~$` lock files, which carry the name of whoever had the file open) — and
        keeps every other team's files byte for byte. When that archive is imported, its manifest
        records the rewritten file's digest; the removal log entry's `inbox_rewrites` pairs it with
        the digest of the archive as downloaded, and the zip's own comment names the request.
      - **Left alone:** everything holding nothing the list stops, and `<inbox>/.partial/` (downloads
        in progress, which the pull sweeps itself).
- [ ] **A removal made before `v1-e30-t09`** left its files in the inbox. Run the same command again
      — same `--team` or `--source`, same `--request` and `--reason` — dry run first, then
      `--execute`: it finds nothing left in the store or the buckets, appends nothing, and purges
      the inbox. Any removal also purges what earlier ones left, because it works from the whole
      list.
- [ ] **A `NOTE` in the plan** (files under the team's directory, in an archive not yet imported,
      that the store had never seen): those files are still in the rewritten archive, because no
      selector could resolve them. Run `caselist pull`, which imports them, then the same removal
      again, which now finds and removes them.
- [ ] **Copies outside the inbox.** The command reaches the store, the buckets and the inbox. Copies
      kept by hand elsewhere are not reached, so check each of these and delete the removed files from
      it by hand. Decided by Charlie, 2026-10-01:
      - **The CardMirror sample folders** (`cardmirror-sample/` and `cardmirror-roundtrip-out/` beside
        the coach's debate working folders): kept on purpose as small test inputs for the parser work,
        so they are always on this list.
      - **The unpacked caselist archives and the hand-downloaded camp files** in the coach's season
        folders: kept only until the parser evaluation (`v1-e31-t05`) no longer needs them, then deleted
        (its ac6). Until then, check them too. After that, they are no longer on this list.
      Any other copy you find is an incident under the policy: delete it in the same run and record it
      in the register.

## Step 9 — Check nothing re-imports it

At the next weekly import (or immediately, if you have the next archive on hand):

- [ ] The importer reports the sha256 as `SUPPRESSED`.
- [ ] `caselist publish` does not upload it.

Once E34 is running, the scheduled download inherits this check because everything it downloads
goes through the same importer. For an OpenEv camp file it does more: `caselist pull` reads the same
list before it fetches anything, and a camp file whose every member is suppressed is reported as
`skipped_as_removed` and never requested from OpenCaselist again (`v1-e34-t07`). Check for that
decision in the next run's `openev_selections`. A weekly archive is still downloaded, because it
holds every other team's disclosures too, and the importer refuses the removed files inside it.

## Step 10 — Close it out

- [ ] Fill in the Outcome column of the register entry: sources removed, snapshots affected,
      whether anything was left in place as shared, the inbox files deleted and rewritten in each
      environment (the `DONE` line), and the date completed. Counts and codes only, as for the rest
      of the entry — no filename.
- [ ] Reply to the requester confirming completion, naming what was removed in their terms (their
      team, their rounds) and anything that was not, with the reason.
- [ ] Commit the register update. No personal data in the diff or the commit message.

## If you removed the wrong thing

The removal is destructive: noncurrent versions are purged, so there is no S3 version to restore
from, and the inbox no longer holds the archive as downloaded — an imported week's copy was deleted,
and one waiting to be imported was rewritten without the file. Recovery means re-importing the file
from the original weekly archive, fetched again from OpenCaselist (the site keeps its back-catalogue,
ADR-0017; it costs one of the day's five bulk downloads), which the suppression list refuses until
the suppression is lifted. It is lifted by **appending** an un-suppress entry,
never by editing the list:

```bash
DEBATE_ENV=dev uv run debate-research caselist unsuppress --sha256 <sha256> \
    --reason REMOVED_IN_ERROR --request RM-2026-01                          # dry run
DEBATE_ENV=dev DEBATE_REMOVAL_PROFILE=debate-dev-evidence-removal uv run debate-research caselist unsuppress \
    --sha256 <sha256> --reason REMOVED_IN_ERROR --request RM-2026-01 --execute
```

Then prod, with `--confirm-prod`, and re-import the archive that holds the file (with
`--allow-out-of-order` if a newer one is already imported). `--reason` is `REMOVED_IN_ERROR` or
`REQUEST_WITHDRAWN`. One `unsuppress` lifts every suppression of that sha256, whole-file and
per-path. Record the mistake in the register.

This is the strongest argument for always running the dry run and reading it.

## Hashes recorded before `caselist remove` existed

<a id="manual-procedure-until-v1-e30-t07-ships"></a>
This section replaces the manual procedure that stood here until v1-e30-t07 shipped; the anchor is
kept because the data-use policy links to it.

If a request was handled by hand before v1-e30-t07 shipped, its sha256 values were kept outside the
repository to be put on the list later. Put each one on now, in dev and then prod, under the
original request id and reason code:

```bash
DEBATE_ENV=dev uv run debate-research caselist remove --source <sha256> --request <original id> --reason <code>
DEBATE_ENV=dev DEBATE_REMOVAL_PROFILE=debate-dev-evidence-removal uv run debate-research caselist remove \
    --source <sha256> --request <original id> --reason <code> --execute
```

A file held nowhere any more is reported as *held nowhere in this environment: it is only
suppressed*; one still held is removed, exactly as above. The entry carries today's date; the
register keeps the original one.

## References

- [docs/policies/caselist-data-use.md](../policies/caselist-data-use.md) — the policy this runbook
  implements, especially [Removal](../policies/caselist-data-use.md#removal).
- `plan_specs/v1/e30-caselist-ingestion/t07-source-removal.yaml` — the `caselist remove` command
  and the suppression list.
- `plan_specs/v1/e29-cloud-evidence-store/t03-evidence-buckets.yaml` — bucket lifecycle and the
  `EvidenceOperator` and `EvidenceRemoval` permission sets.
- `plan_specs/v2/e35-debate-tub/t05-tub-access-and-removal.yaml` — the V2 takedown flow built on
  this suppression list.
