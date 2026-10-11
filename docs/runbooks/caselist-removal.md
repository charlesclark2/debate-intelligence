<!-- docs-index: Removing a caselist or OpenEv source on request -->
# Runbook: removing a caselist or OpenEv source on request

| | |
|---|---|
| Purpose | Honour a removal request under the [caselist and OpenEv data-use policy](../policies/caselist-data-use.md) |
| Who runs it | The operator (Charlie). Not an agent session, not CI |
| How long | 15–30 minutes of attention, spread over the 7-day response window |
| Destructive? | **Yes.** It deletes objects and all of their noncurrent versions in dev and prod |
| Tooling | `debate-research caselist remove` and `caselist unsuppress` (v1-e30-t07; the download inbox since v1-e30-t09; later uploads at the removed path since v1-e30-t11), and `caselist status`, which reports what a removal left in the bucket (v1-e30-t10) |

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

See what is in the store for this environment, and whether it matches S3:

```bash
DEBATE_ENV=dev uv run debate-research caselist status
```

Pick the selector that matches the request:

- **A specific file:** `--source <sha256>`.
- **Everything one team disclosed, across every snapshot:** `--team <caselist>/<school>/<team>`.

If the request names a tournament and round rather than a team, resolve it to a team selector with
`caselist status` output first. If the request is broader than one team (a whole school, a whole
caselist), run one `--team` removal per team so the register and the log stay legible.

**A removal covers later uploads at the same path.** A request to take a file down is not a request
to keep its revisions, so the plan for `--source <sha256>` also includes every later upload the
store holds at each path it takes that file from (`v1-e30-t11`). You name one version and confirm
one plan for all of them. `--team` needs nothing extra: it selects by the team's directories, so it
already names every version of every file there.

- **A request that is explicitly about one version** ("take down the copy from the first week; the
  corrected one can stay"): add `--only-named`. The plan then removes the file you named and lists
  the later uploads as left in place. Use it only when the requester said so. If they did not say,
  the request covers the later uploads.

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
holds: only this team's copies are withdrawn), **LATER UPLOADS AT A REMOVED PATH** and **EARLIER
VERSIONS AT A REMOVED PATH** (other files the store holds at the same paths; read them as described
below), **MANIFESTS REWRITTEN**, **DOWNLOAD INBOX** (every
file `caselist pull` downloaded that holds a removed file, and whether it is deleted or rewritten
without it; see step 8), the **SUPPRESSION ENTRIES** exactly as they will be written, **FOR THE
CONFIRMATION TO THE REQUESTER** (the facts for step 10: how many files, which weekly archives,
which tournament rounds, what was kept and what was not done), and **TO CARRY IT OUT**, the exact
`--execute` command. Add `--json` for the same plan as one
JSON object. The JSON carries no school, team code, path, camp, title or file name (`v1-e30-t11`):
a file is its sha256, a disclosure is the digest the suppression list uses for one, a `--team`
selector is its caselist, and an inbox file is a weekly archive's name or `openev-<id>`. So the JSON
can be saved or pasted where the text of the plan cannot. Check the plan against the request in
the text. The everyday profile may list object versions under the prefixes a takedown removes
from (`v1-e29-t06`), so the plan shows each object's version count. In an environment where that
grant has not been applied yet ([evidence-store.md, Later applies](evidence-store.md#later-applies)
records when it was), the plan says *Versions not counted* instead; everything else in it is still
right. Either way, `--execute` lists and deletes every version with the takedown profile and
reports how many.

**Reading the later uploads and the earlier versions.** Weekly archives are windows of about a
week's changes, not copies of the whole caselist, so a revision of a file is a row at the same path
in a later weekly, or only in a complete archive (`full/<date>`). The plan asks every snapshot the
store holds, weekly and complete, here and in the bucket:

- **LATER UPLOADS AT A REMOVED PATH, ADDED TO THIS PLAN.** Each entry is another file held at a
  path the removal takes a named file from, in a snapshot dated after the earliest snapshot that
  holds the named file there. It is listed by sha256, with the named file it follows, its caselist
  and the snapshots that hold it, then the same detail a named file gets. What happens to it is on
  its first line:
  - *removed everywhere*: no other path holds it, so it goes exactly as the named file does (blob,
    records, manifest rows, `raw/` and `parsed/` objects with every version, the inbox) and its
    sha256 is suppressed.
  - *withdrawn from this path only*: another path holds the same bytes, another team's or another
    of this team's. Its row and record at the removed path go and that path is suppressed for it,
    as for a shared file a team withdraws. The blob and the other path's rows stay.
    `--include-shared` does not change this: it is a decision about the files the request names.
  - *KEPT*: a camp file's later upload that another holder also has. The suppression list cannot
    stop one camp path of a file, so nothing is done. To remove it for everyone, run a second
    removal that names it, with `--include-shared`, under the same request id.
- **For an OpenEv camp file** a later upload is a higher OpenEv id at the same camp path: OpenEv
  changes a file only by deleting it and uploading it again, and the sync fetches the new id as a
  revision (`v1-e34-t08`). Its line names the release and the ids, and says how the two were
  matched. *The delivery record puts both ids at one upstream path* is certain. *Matched by file
  name alone* means this machine has no delivery record for both ids (prod never pulls, so it never
  has one). A release's rows do not keep the camp's folder, so two camps' files with one file name
  read alike. Compare that plan with the dev plan, and use `--only-named` if it lists a file the
  dev plan did not.
- **EARLIER VERSIONS AT A REMOVED PATH, NOT REMOVED.** Files held at the same path only in
  snapshots dated before the named file first appeared there. The request does not cover them and
  nothing is done to them. If the requester wants one gone, run a second removal that names it,
  under the same request id. A file listed here as *the same date* is in a weekly and a complete
  archive of one day that disagree, so the dates cannot say which came first. Decide it by hand
  the same way.
- **LATER UPLOADS AT A REMOVED PATH, LEFT IN PLACE (--only-named).** What `--only-named` leaves.
  Check it is what the requester asked to keep.

Above the command under *TO CARRY IT OUT* the plan says how many files the request names and how
many later uploads it adds. That sentence is the last thing to check before you run the command.

Read the plan before going further. Confirm:

- [ ] The source count matches what the requester described.
- [ ] **Later uploads.** The number the plan adds is what you expect, each one is a later version of
      the requester's file at the requester's path, and `--only-named` is on the command only if the
      request was explicitly about one version.
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
signed-out session, or the everyday profile named by mistake stops it there, with nothing removed
and nothing appended. The everyday profile may list versions and write (`v1-e29-t06`), so named by
mistake it is refused at the delete and leaves its probe, a few bytes that name nothing; the error
gives the probe's key.
It then appends the suppression entries first, deletes from the bucket, then from this machine — the
store, then the download inbox (step 8) — and writes one removal-log entry. The `DONE` output says
how many files the request named and how many later uploads the run covered; the removal log lists
every sha256 it removed or withdrew, later uploads included. If it stops part-way it
says so, logs `INCOMPLETE`, and the fix is to run the same command again, with the same flags. The inbox is changed only
while no `caselist pull` is running: if one holds the sync's lock, the removal stops `INCOMPLETE`
with *a caselist pull is running*, and you re-run it once the pull has finished.

**Then rebuild the parsed card store's aggregates.** The removal deletes the removed file's parsed
cards and, for every caselist it touches, the store's `index.jsonl`, `failures.jsonl` and
`occurrences.jsonl` (`v1-e31-t06`), here and in the bucket, because each of them can name the
file or one of the team's disclosures. Nothing else rebuilds them until the next parse, and until
then anything that reads the store finds no aggregates at all. The caselists to rebuild are the
ones whose `parsed/<caselist>/<version>/index.jsonl` the plan listed under *WILL BE REMOVED*; if it
listed none, the store was never built here and there is nothing to do. For each, with the everyday
profile (a few minutes each; nothing is parsed again, only the aggregates are rebuilt and
published):

```bash
aws sso login --profile debate-dev-evidence
DEBATE_ENV=dev uv run debate-research caselist parse --caselist hsld26 --publish
```

It exits 0 and prints the rebuilt counts. The new aggregates leave out every source and disclosure
the suppression list stops, which now includes this removal's.

## Step 6 — Verify dev

First, the store and S3 agree and the sources are gone:

```bash
DEBATE_ENV=dev uv run debate-research caselist status
```

Then re-import a snapshot that still contains the file. It reports the file as `SUPPRESSED`, stores
no blob and writes no manifest row. An archive older than the newest one imported needs
`--allow-out-of-order`.

```bash
DEBATE_ENV=dev uv run debate-research caselist import <archive> --caselist hsld26 --snapshot <date>
```

- [ ] `caselist status` is clean (exit 0, no drift). It now also treats as drift any local manifest
      row the suppression list stops, and any current bucket object of a suppressed file.
- [ ] Under its table it says *No version of a removed file is left under raw/ or parsed/*
      (`v1-e30-t10`). It lists the bucket's object versions with the everyday profile and counts
      what is left of every file on the suppression list, the later uploads this removal took down
      included. If it says *REMOVAL RESIDUE* or *NOT CHECKED* instead, go to
      [When `caselist status` reports removal residue](#when-caselist-status-reports-removal-residue).
- [ ] The `DONE` line counts the inbox files deleted and rewritten, and the dry run run again says
      *DOWNLOAD INBOX (…): nothing in it holds a removed file.*
- [ ] The re-import counts the file as `SUPPRESSED`.
- [ ] The parse in step 5 exited 0, and each `index.jsonl` key the plan listed is back:
      `DEBATE_ENV=dev uv run debate-research store ls <that key>` lists 1 object.
- [ ] No `raw/` or `parsed/` object for those sha256 values remains — **including noncurrent
      versions**. The line above is that check for every removed file at once. For one key, with
      the AWS CLI, if you want belt and braces:
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
      environment that pulls has its own inbox, and each environment's run purges its own. The
      *LATER UPLOADS* section should list the same sha256 values as dev's. For a camp file, prod
      says *matched by file name alone* where dev named the delivery record. That is expected, and
      it is why the sha256 values are what you compare. Pass `--only-named` in prod if you passed
      it in dev.
- [ ] `caselist status` is clean afterwards, and says *No version of a removed file is left under
      raw/ or parsed/*. Residue is reported per environment, so a clean dev says nothing about prod.

Then rebuild prod's parsed aggregates, for the same caselists as in step 5. The parsed store is
built on this machine in the dev data directory and published to both buckets from there, so this
runs against the dev data directory with the prod bucket, after the dev removal has put the entries
on that directory's suppression list:

```bash
aws sso login --profile debate-prod-evidence
DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research caselist parse --caselist hsld26 --publish --confirm-prod
```

- [ ] It exits 0. Each variable is set on the command line only, so nothing is left pointing the
      shell at prod.

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
        in progress, which the pull sweeps itself). That includes a camp's later upload of a removed
        file, a new OpenEv id at the same path, if it was downloaded before the removal and not yet
        imported: its bytes are new, so the list does not name them, but the pull holds it back as
        `same_path_as_a_removed_file` and does not import it (`v1-e34-t14`).
- [ ] **A later upload at a removed path: what covers it.** It depends on whether the store had
      imported it when you ran the removal.
      - **Already imported** (a caselist file or a camp file): the plan listed it under *LATER
        UPLOADS AT A REMOVED PATH* and the run removed it with the named file (`v1-e30-t11`). The
        copies of it in the inbox went with it.
      - **Not yet imported, a camp file:** a new OpenEv id at the removed camp path, listed upstream
        or already downloaded into the inbox, is held back by every later `caselist pull` as
        `same_path_as_a_removed_file` and is never imported (`v1-e34-t14`). So for a camp file the
        hold and the plan between them cover a later upload either way: whichever side of the
        removal it was imported on, it does not stay.
      - **Not yet imported, a caselist file:** nothing holds it back, and step 9 has the check. If
        the team revises the file after the removal, the weekly that carries the revision imports
        it: its bytes are new, and the list stops bytes and withdrawn disclosures, not paths.
      If you ran the removal with `--only-named`, none of this applies to the later uploads it left.
      That was the request.
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
- [ ] **No revision of it arrived at the same path** (caselist files; a camp file's is held by the
      pull, step 8). The plan covered the later uploads the store held when you ran it. A revision
      the team uploads afterwards is imported with the weekly that carries it. After a `--team`
      removal, run the same `--team` dry run again once that weekly is imported: it selects by the
      team's directories, so it lists anything new there, and `--execute` removes it under the same
      request id. After a `--source` removal a re-run cannot find it, because the removed file's
      path is recorded nowhere once its rows are gone. Ask the newest manifest instead, with the
      path from the request in your mailbox:

      ```bash
      jq -r --arg path '<the path, as the request gave it>' 'select(.kind == "member" and .path == $path and .sha256 != null) | .sha256' "$HOME/.debate-research/dev/objects/manifests/hsld26/<date>.jsonl"
      ```

      It prints nothing when the path is not in that week's window, and a sha256 when a file is
      there. If the request covers it, remove that sha256 with `--source`, under the same request
      id, in dev and then prod.

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

## When `caselist status` reports removal residue

`caselist status` also lists the bucket's object versions and reports, for each caselist, what the
bucket still holds of files the suppression list says were removed (`v1-e30-t10`). It runs with the
everyday profile, it only lists, and it never uses the takedown profile. Under its table it says
one of three things:

- *No version of a removed file is left under raw/ or parsed/ (N caselist(s) checked; noncurrent
  manifest versions are not read).* Nothing to do.
- *REMOVAL RESIDUE in `<caselist>`: N current object(s), N noncurrent version(s) and N delete
  marker(s) of N file(s) (sha256 `<twelve characters>`, …).* The command exits 1. The steps below
  clear it.
- *Removal residue NOT CHECKED for `<caselist>`.* The profile was refused the version listing. That
  is not a finding of none: see [Not checked](#not-checked) below.

Each file is one removed file, named by the first twelve characters of its sha256 and by counts.
The report prints no school, team code, path or file name, in the text or in `removal_residue` of
`--json`, so it can be pasted where a plan's text cannot.

| Count | What the bucket holds | How it gets there |
|---|---|---|
| current object(s) | An object that is the current version of its key | A takedown that stopped before that object, or among its versions: it deletes each version by id, and S3 then makes the next one current |
| noncurrent version(s) | A version under a newer one, or hidden under a delete marker | The same, or a delete made some other way than this command |
| delete marker(s) | A marker hiding an object whose versions are all still there | A delete made without a version id. `caselist remove` never leaves one |

Any of the three can still be read or restored by someone with access to the bucket. The file is
not removed until all three counts are gone.

**Later uploads are covered.** The report works from the suppression list, not from the request.
A later upload that the plan listed as *removed everywhere* (step 4) is suppressed whole, so what
is left of it is reported exactly as the named file's is. A later upload *withdrawn from this path
only*, or *KEPT*, is still held for its other holder: its object is meant to be in the bucket, and
it is not reported. Nor is a later upload that `--only-named` left in place, which is not on the
list.

**Who runs it:** the operator, as for the removal itself. Residue is reported per environment, so
clear it in the environment whose `caselist status` showed it, dev before prod if both do. The
commands below are dev's. For prod use `DEBATE_ENV=prod`, the `debate-prod-evidence-removal`
profile and `--confirm-prod`.

1. **Find the request.** Look the twelve characters up in that environment's suppression list.
   The line it prints holds the whole sha256, the request id and the reason code:

   ```bash
   grep '"sha256":"<the twelve characters>' "$HOME/.debate-research/dev/suppression/suppression-list.jsonl"
   ```

   If it prints nothing, the removal was made from another machine and the entry is only in the
   bucket's copy, `manifests/_suppression/suppression-list.jsonl`.

2. **Choose the command by what else `caselist status` said.**

   - **Snapshots differ too** (the failure is `CASELIST_DRIFT`, and the request's last line in
     `removal-log.jsonl` says `INCOMPLETE`). The removal stopped part-way. Run the same command
     again with the same flags, as step 5 says: the dry run, then `--execute`. It finishes the
     manifests, this machine and the inbox as well as the bucket.
   - **Every snapshot agrees** (the failure is `REMOVAL_RESIDUE`). The removal completed, and
     versions are in the bucket anyway. The original command may now say *Nothing is left to
     remove*: once a later upload's manifest rows are gone, nothing shows it at the removed path.
     Name each file the report lists by its own sha256, under the same request id and reason:

     ```bash
     DEBATE_ENV=dev uv run debate-research caselist remove --source <sha256> --request RM-2026-01 --reason REQUESTED_BY_TEAM
     ```

     That is the dry run, and it needs only the everyday profile. Check that it shows the file as
     *already suppressed by this request: finishing what a previous run left*, with a `bucket` line
     for each key and its version count (a delete marker counts as a version), and no new
     suppression entry. If it lists anything else, read it as in step 4 before going on. Then
     execute with the takedown profile:

     ```bash
     aws sso login --profile debate-dev-evidence-removal
     DEBATE_ENV=dev DEBATE_REMOVAL_PROFILE=debate-dev-evidence-removal uv run debate-research caselist remove \
         --source <sha256> --request RM-2026-01 --reason REQUESTED_BY_TEAM --execute
     ```

   Do not delete the versions by hand with the AWS CLI. The command deletes every version of the
   key, sweeps the noncurrent manifest versions that still name the file, and writes the removal
   log entry. A delete by hand does none of that, and one without a version id is how a delete
   marker gets there.

3. **Confirm it is gone.** Run the status again in that environment, with the everyday profile:

   ```bash
   DEBATE_ENV=dev uv run debate-research caselist status
   ```

   - [ ] It exits 0 and says *No version of a removed file is left under raw/ or parsed/*. With
         `--json`, every entry of `removal_residue` has `"checked": true` and `"files": []`.
   - [ ] If the plan you executed listed a `parsed/<caselist>/<version>/index.jsonl`, rebuild that
         caselist's aggregates as in step 5. Any executed removal deletes them.
   - [ ] The register entry for the request records that residue was found and cleared, with the
         counts and the date. Counts and codes only.

**What the report does not see.** It lists versions under `raw/` and `parsed/` and matches an
object by its key, which is the file's sha256. So:

- It does not read manifests. A noncurrent version of a manifest that still holds a removed row is
  not reported, because its key names no file and the check downloads nothing. Every executed
  removal sweeps those, a re-run included. The same goes for a noncurrent version of the parsed
  store's `index.jsonl`, `failures.jsonl` and `occurrences.jsonl`.
- It does not report a shared file that was withdrawn from one team and kept for another. That file
  is suppressed for one path, not whole, and the other holder's copy is the same object.

So *No version of a removed file is left* means what it says about `raw/` and `parsed/`, and no
more. The AWS CLI check in step 6 is still there for one key.

### Not checked

*Removal residue NOT CHECKED* means the everyday profile was refused `ListObjectVersions`. The
snapshot comparison is unaffected and the exit code does not change, but the residue is unknown,
not absent. `--json` gives `"checked": false` with `null` counts.

The grant was applied in dev and prod on 2026-10-08
([evidence-store.md, Later applies](evidence-store.md#later-applies)), so in either of them this
means something changed: check which profile the command ran with, then
[evidence-store.md, If something is wrong](evidence-store.md#if-something-is-wrong). In an
environment where the grant was never applied, every status says this. A `COMPLETED` removal there
still deleted every version, because `--execute` lists them itself with the takedown profile; what
is missing is the check afterwards.

## If you removed the wrong thing

The removal is destructive: noncurrent versions are purged, so there is no S3 version to restore
from, and the inbox no longer holds the archive as downloaded — an imported week's copy was deleted,
and one waiting to be imported was rewritten without the file. Recovery means re-importing the file
from the original weekly archive, fetched again from OpenCaselist (the site keeps its back-catalogue,
ADR-0017; it costs one of the day's five bulk downloads), which the suppression list refuses until
the suppression is lifted. It is lifted by **appending** an un-suppress entry,
never by editing the list. First the dry run, which changes nothing:

```bash
DEBATE_ENV=dev uv run debate-research caselist unsuppress --sha256 <sha256> \
    --reason REMOVED_IN_ERROR --request RM-2026-01
```

Then the same command with the takedown profile and `--execute`:

```bash
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
- `plan_specs/v1/e30-caselist-ingestion/t11-removal-covers-later-uploads.yaml` — later uploads at
  the removed path, and `--only-named`.
- `plan_specs/v1/e34-caselist-sync/t14-removed-path-hold-for-inbox-copies.yaml` — the pull's hold
  for a later upload that has not been imported.
- `plan_specs/v1/e30-caselist-ingestion/t10-removal-docstrings-and-residue.yaml` — the residue
  report in `caselist status`.
- `plan_specs/v1/e29-cloud-evidence-store/t06-removal-grant-scope-test.yaml` — the everyday
  profile's read-only version listing, which the dry run's version counts and the residue report
  both use.
- `plan_specs/v1/e29-cloud-evidence-store/t03-evidence-buckets.yaml` — bucket lifecycle and the
  `EvidenceOperator` and `EvidenceRemoval` permission sets.
- `plan_specs/v2/e35-debate-tub/t05-tub-access-and-removal.yaml` — the V2 takedown flow built on
  this suppression list.
