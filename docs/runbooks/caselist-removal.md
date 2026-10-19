<!-- docs-index: Removing a caselist or OpenEv source on request -->
# Runbook: removing a caselist or OpenEv source on request

| | |
|---|---|
| Purpose | Honour a removal request under the [caselist and OpenEv data-use policy](../policies/caselist-data-use.md) |
| Who runs it | The operator (Charlie). Not an agent session, not CI |
| How long | 15–30 minutes of attention, spread over the 7-day response window |
| Destructive? | **Yes.** It deletes objects and all of their noncurrent versions in dev and prod |
| Tooling | `debate-research caselist remove` and `caselist unsuppress` (v1-e30-t07; the download inbox since v1-e30-t09; later uploads at the removed path since v1-e30-t11; the hold on a removed caselist path since v1-e30-t13; a camp path withdrawn on its own, and camp rows that carry their upstream identity, since v1-e30-t14), and `caselist status`, which reports what a removal left in the bucket (v1-e30-t10) |

Removal is not a negotiation. A team asks, and their disclosure comes out. This runbook exists so
that it comes out *completely* — local store, both buckets, every noncurrent version, the parsed
cards, the archives and camp files `caselist pull` downloaded, and the built files that quoted it —
and so that no later archive puts it back. A weekly archive is a window of about a week's editing,
so it holds the file again only when its window carries it; the complete archive holds it until the
team takes it down on OpenCaselist. The suppression list stops it in both.

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
> environments, and add them to a suppression list so no later caselist archive can bring them
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

**It also covers what is uploaded there afterwards** (`v1-e30-t13`). A `--source` removal that
removes a file whole records each caselist path it takes the file from, as a *path entry* beside
the suppression list. From then on `caselist import` and `caselist pull` refuse a new upload at
that path, whatever its bytes. The plan also reads the archives in the download inbox, so a
revision that was downloaded and not yet imported is in the plan too. Step 9 says what you do when
one arrives. Three removals record no path:

- `--only-named`, because the request was about one version and the team's later uploads stay;
- a file the plan withdraws or skips, because it stays with another holder;
- `--team`, which holds no path. Run the same `--team` command again after a pull, as step 9 says.

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
bucket objects with their version counts), **SHARED, KEPT** (for `--team`, files another team or a
camp file also holds: only this team's copies are withdrawn; for `--source`, only what a stopped run
left withdrawn, and only its copies at the removed paths), **LATER UPLOADS AT A REMOVED PATH** and
**EARLIER VERSIONS AT A REMOVED PATH** (other files the store holds at the same paths; read them as described
below), **MANIFESTS REWRITTEN**, **DOWNLOAD INBOX** (every
file `caselist pull` downloaded that holds a removed file, and whether it is deleted or rewritten
without it; see step 8), the **SUPPRESSION ENTRIES** exactly as they will be written, the
**WITHDRAWALS** (when the plan withdraws a copy: the caselist each is withdrawn from, by slug,
exactly as written; see step 8), the **PATH ENTRIES** exactly as they will be written, or why there
are none, **FOR THE
CONFIRMATION TO THE REQUESTER** (the facts for step 10: how many files, which weekly archives,
which tournament rounds, what was kept and what was not done), and **TO CARRY IT OUT**, the exact
`--execute` command. Add `--json` for the same plan as one
JSON object. The JSON carries no school, team code, path, camp, title or file name (`v1-e30-t11`):
a file is its sha256, a disclosure is the digest the suppression list uses for one, a `--team`
selector is its caselist, and an inbox file is a weekly archive's name or `openev-<id>`. Its
`withdrawals` are the *WITHDRAWALS* lines, each by the file's sha256, the path's digest and the
caselist's slug, and `manifest_versions_swept` is the *MANIFEST VERSIONS SWEPT* count, in all and by
manifest key, or `"not counted"` where the line says so (`v1-e30-t20`). So the JSON
can be saved or pasted where the text of the plan cannot. Check the plan against the request in
the text. Neither the text nor the JSON names a path on this machine, so you can keep both: the
inbox is *inbox in the data directory* (`"inbox_directory": "inbox"`), or *the directory
caselist.inbox_dir names* when a profile puts it elsewhere, and a run a pull's lock stops names the
lock as *caselist-sync.lock in the data directory* (`v1-e30-t20`). The everyday profile may list object versions under the prefixes a takedown removes
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
  - *withdrawn from this path only*, for a camp file (`v1-e30-t14`): another release or a team
    holds the same bytes. Its row in that release's manifest goes, and so do that release's
    camp-file record and its year's `raw/openev/<year>/` copy, unless another row of that release
    or another release of that year still holds it. The suppression entry stops the file at that
    row of that release only. Its line reads `withdraw openev <release> openev-<id>`, and
    *WITHDRAWALS* names `openev`. The other release's row and record, a team's copy and the blob
    stay. To remove it for everyone instead, run a second removal that names it, with
    `--include-shared`, under the same request id.
  - *KEPT*: another holder has it, and the plan takes it from none of its paths. A later upload
    should not read this way since `v1-e30-t14`; if one does, stop and report it.
- **In the download inbox.** A later upload's line says *in the download inbox in `<snapshot>`, not
  in the store* when an archive `caselist pull` downloaded holds it at the removed path and no
  manifest does (`v1-e30-t13`). Either the archive has not been imported yet, or it was imported
  after the removal and the upload was refused. It is covered like any other later upload: its
  sha256 goes on the suppression list under this request, and the *DOWNLOAD INBOX* section says
  what happens to its archive, `rewrite` if it is still waiting to be imported and `delete` if it
  was imported. A line that says *held in … ; also in the download inbox in …* is one the store and
  a waiting archive both hold.
- **For an OpenEv camp file** a later upload is a higher OpenEv id at the same camp path: OpenEv
  changes a file only by deleting it and uploading it again, and the sync fetches the new id as a
  revision (`v1-e34-t08`). Its line names the release and the ids, and says how the two were
  matched. *Matched by upstream path* is certain: each row of a release manifest carries the
  OpenEv id it was downloaded as and the digest of that id's upstream path (`v1-e30-t14`), dev's
  delivery record says the same, and prod's manifests are published from dev's data directory, so
  the two environments match alike. *Matched by file name alone* means neither the rows nor a
  delivery record here knows both ids' upstream path: the release was published before
  `v1-e30-t14` and has not been re-derived since, or the weekly agent's build is older than that.
  A release's rows do not keep the camp's folder, so two camps' files with one file name read
  alike. Stop, and give the rows their identity first
  ([Camp rows that carry no upstream identity](#camp-rows-that-carry-no-upstream-identity)).
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
- [ ] **Path entries.** For `--source` without `--only-named`, *PATH ENTRIES* lists one line for
      each caselist path the named file is removed from. Each line is a caselist, two digests, the
      date of the first snapshot that held the file there (`after_snapshot`), the request id and the
      reason. With `--only-named` or `--team` it says *none* and why. A camp file has none: the pull
      holds a camp path (step 8).
- [ ] The listed disclosure records, manifest rows, local blobs and S3 objects (with their version
      counts) look right.
- [ ] **Other holders.** A file's line ends *also held by N other team(s)* or *N camp file(s)* only
      when someone besides the holder being removed has it (`v1-e30-t16`): for `--team` that is
      every other team and every camp file, and for `--source` every holder but one, the team whose
      file it is or, for a file no team holds, one camp file. A later upload withdrawn from the
      removed path counts the teams at its other paths less the team at the removed path, and its
      `kept in` line says *another path there still holds it*, which may be the same team's. A
      `--source` plan never says "this team's": no team asked. It says what happens at the removed
      path instead (*N path(s) a shared file is withdrawn from*, *the copy of a shared file at the
      path it was withdrawn from*). Nor does a `--team --include-shared` plan of a later upload it
      takes from another team's path, since it removes the shared file from that path too: it
      counts *N path(s) of another holder a later upload is withdrawn from*, and the list stops
      *another holder's copy of a later upload* there (`v1-e30-t20`).
- [ ] **Shared references.** If the plan lists sources also disclosed by another team, or that are
      also a camp file, decide explicitly: without `--include-shared` only this team's `Disclosure`
      records and manifest rows are dropped and the shared blob stays, and each of this team's
      paths to it is suppressed on its own, so no later archive can record it as theirs again;
      with it, the file goes for everyone. Default to *without*, and tell the requester what
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

Before the first change the command checks the takedown profile in two steps. First it asks the
account which role the profile is signed in as, and stops unless that is this environment's
`EvidenceRemoval` permission set (`v1-e29-t08`). Asking needs no grant and writes nothing. Then it
proves the profile can list, write and delete a probe version under
`manifests/_suppression/preflight/`. `caselist unsuppress --execute`
([If you removed the wrong thing](#if-you-removed-the-wrong-thing)) runs the same check, in the same
two steps, before it appends anything, and stops in the same ways.

Once its own probe is gone, a check that passed deletes every probe it found under
`manifests/_suppression/preflight/` before it wrote its own: what earlier checks left
(`v1-e29-t09`). It deletes them with the takedown profile, and nothing outside that prefix. This is
housekeeping: if the bucket refuses to delete one of them, the command still carries out the
request. The `DONE` output then ends with *N probe version(s) an earlier preflight left … could not
be deleted*, and `--json` gives the count and the keys under `data.preflight_probes_left`. Remove
them by hand afterwards ([A probe a preflight left behind](#a-probe-a-preflight-left-behind)).

An unset `DEBATE_REMOVAL_PROFILE`, one that names a profile your AWS config lacks, a signed-out
session, or the everyday profile named by mistake stops it at or before the first step: nothing
removed, nothing appended, nothing written to the bucket. The error says *nothing was deleted* and
what to correct. The everyday profile is told which permission set it is signed in as and which
profile to name instead; signing in again does not help, and the command exits 1. A signed-out
session exits 3 with the `aws sso login` line to run.

A probe is left behind only when the takedown role itself is refused the delete, which means its
grants are not what [evidence-store.md](evidence-store.md) says they are. The error gives the
probe's key. Once the grant is fixed, the next `--execute` removes it;
[A probe a preflight left behind](#a-probe-a-preflight-left-behind) says when to remove one by hand.

It then appends the suppression entries and the path entries first, deletes from the bucket, then
from this machine — the store, then the download inbox (step 8) — and writes one removal-log entry. The `DONE` output says
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
no blob and writes no manifest row.

```bash
DEBATE_ENV=dev uv run debate-research caselist import <archive> --caselist hsld26 --snapshot <date>
```

- [ ] `caselist status` is clean (exit 0, no drift). It now also treats as drift any local manifest
      row the suppression list stops, and any current bucket object of a suppressed file.
- [ ] Under its table it says *No version of a removed file is left under raw/ or parsed/, and no
      manifest or aggregate version is older than a removal that touched its caselist*
      (`v1-e30-t10`, `v1-e30-t15`). It lists the bucket's object versions with the everyday profile
      and counts what is left of every file on the suppression list, the later uploads this removal
      took down included, and the versions of the parsed store's aggregates and of the manifests
      this removal rewrote that are older than it. The aggregates the parse in step 5 rebuilt are
      newer, and are not counted. If it says *REMOVAL RESIDUE* or *NOT CHECKED* instead, go to
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
DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research caselist status
```

**In prod, compare against the dev data directory**, as the parse below does. With prod's own data
directory, which holds no manifests, every snapshot reads as drift and the command exits 1 whatever
the bucket holds. The line under the table about removal residue is right either way. (Measured on
2026-10-11: prod's own directory reported every snapshot as drift; the dev directory, in sync.)

- [ ] The prod dry-run plan matches the dev one (a difference means the two environments had
      drifted — investigate before executing). The *DOWNLOAD INBOX* section may differ: each
      environment that pulls has its own inbox, and each environment's run purges its own. A camp
      file's later uploads are matched in prod as in dev, by the upstream identity the release's
      rows carry (`v1-e30-t14`), so each of their lines says *matched by upstream path*. If one says
      *matched by file name alone*, prod's release manifest predates that: stop, and do
      [Camp rows that carry no upstream identity](#camp-rows-that-carry-no-upstream-identity)
      before executing. Pass `--only-named` in prod if you passed it in dev.
- [ ] `caselist status`, run against the dev data directory as above, is clean afterwards, and says
      *No version of a removed file is left under raw/ or parsed/, and no manifest or aggregate
      version is older than a removal that touched its caselist*. Residue is reported per
      environment, so a clean dev says nothing about prod. It compares prod's bucket with prod's own
      removals only: the dev data directory's copy of the removal log holds dev's, and those are
      left out.

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
- [ ] After a `--source` removal without `--only-named`, confirm the path entries are beside the
      list in both places (`v1-e30-t13`): `<data_dir>/suppression/path-holds.jsonl` on this machine
      and `manifests/_suppression/path-holds.jsonl` in each bucket, one line for each path the plan
      printed. It is append-only and merged like the list. It is a file of its own because a build
      from before `v1-e30-t13` refuses the whole suppression list at a line it does not know, and
      an import against a list it cannot read fails. Those builds never open this file, and read
      the list beside it exactly as before.
- [ ] If the plan printed *WITHDRAWALS*, confirm the same lines are beside the list in both places
      (`v1-e30-t16`): `<data_dir>/suppression/withdrawals.jsonl` on this machine and
      `manifests/_suppression/withdrawals.jsonl` in each bucket. Each says which caselist one
      suppressed disclosure was withdrawn from, by its slug, beside the entry's sha256, disclosure
      digest and request id. The suppression entry and the removal log hold only the digest, which
      hides the caselist with the path, so this is how a shared file withdrawn from one caselist and
      kept in another is attributed afterwards: find the sha256 in this file and read `caselist`. It
      is append-only and merged like the list, and a file of its own for the reason the path entries
      are. A removal made by a build from before `v1-e30-t16` wrote none, so its withdrawals have no
      caselist recorded. A camp path withdrawn on its own (`v1-e30-t14`) has a line here too, which
      names `openev`; its disclosure digest is of `openev/<release>/<row path>`.
- [ ] After running a `--source` removal again, if any import since refused an upload at a held
      path, confirm the same lines are beside the list in both places (`v1-e30-t23`):
      `<data_dir>/suppression/held-digests.jsonl` on this machine and
      `manifests/_suppression/held-digests.jsonl` in each bucket. Each is one upload the import
      refused: its sha256, the held path's digest and the request holding the path, and nothing
      else. The import writes this machine's copy, as it refuses the upload; the removal writes the
      bucket's. It is append-only and merged like the list, and a file of its own for the reason
      the path entries are.
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
      - **Deleted:** a removed camp document (`openev-<id>-…`); the download of a camp path the
        plan withdrew, *its camp path is withdrawn* (`v1-e30-t14`); a camp release whose every file was
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
      - **Already imported, a camp file another release or a team also holds:** the run withdrew it
        from its camp path (`v1-e30-t14`). Its entry stops it at that row of that release: the
        OpenEv importer refuses it there, and `caselist pull` reports the id as
        `skipped_as_removed` instead of fetching it again. The other holder's copy is untouched.
        Its download (`openev-<id>-…`) was deleted from the inbox, as a removed camp file's is.
      - **Not yet imported, a camp file:** a new OpenEv id at the removed camp path, listed upstream
        or already downloaded into the inbox, is held back by every later `caselist pull` as
        `same_path_as_a_removed_file` and is never imported (`v1-e34-t14`). So for a camp file the
        hold and the plan between them cover a later upload either way: whichever side of the
        removal it was imported on, it does not stay.
      - **Not yet imported, a caselist file, waiting in the inbox when you ran the removal:** the
        plan listed it under *LATER UPLOADS AT A REMOVED PATH* as *in the download inbox*, and the
        run put it on the list and rewrote its archive without it (`v1-e30-t13`).
      - **Not yet imported, a caselist file the team uploads after a `--source` removal:** the path
        entry holds it. The import of the weekly or the complete archive that carries it refuses it
        and counts it as `SUPPRESSED`, under the request id. Step 9 says how you finish it.
      - **After a `--team` removal:** nothing holds a new file of the team's. The same `--team`
        command, run again after the pull, finds it (step 9).
      If you ran the removal with `--only-named`, none of this applies to the later uploads it left
      or to what the team uploads at the path afterwards. That was the request.
- [ ] **Which build applies the hold.** The build that imports must have `v1-e30-t13`. A build from
      before it reads the suppression list and not the path entries, so it imports a new upload at
      a removed path, and nothing fails. If the weekly agent runs such a build
      (`debate-research --version` says which), treat every pull as one that may have imported a
      later upload, and do step 9 after each until the agent is updated. The same goes for a camp
      path withdrawn on its own (`v1-e30-t14`): a build from before it reads that entry and asks only
      whether the whole file is suppressed, so its pull may fetch the withdrawn id again and record
      its row. The same removal, run again with a build that has `v1-e30-t14`, finds that row by its
      entry and takes it, with that release's record and copy.
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

At the next import (or immediately, if you have the next archive on hand):

- [ ] Where the archive holds the file, the importer reports it as `SUPPRESSED`. A weekly holds it
      only when its window carries it, so the next weekly may not; a complete archive holds it
      until the team takes it down on OpenCaselist.
- [ ] `caselist publish` does not upload it.
- [ ] **A new upload at the removed path** (caselist files; a camp file's is held by the pull,
      step 8). After a `--source` removal the path entry refuses it at import (`v1-e30-t13`). The
      import's table then says, under its counts, *SUPPRESSED includes N new upload(s) at a removed
      path (N under RM-…), refused because that removal holds the path*, and `--json` gives
      `held_at_removed_paths` as request ids and counts. The upload is not in the store, the bucket
      or any manifest. Its sha256 is not on the suppression list yet, because only `caselist remove`
      writes the list. The import does write its sha256 and the request, and nothing else, to
      `held-digests.jsonl` beside the path entries on this machine (`v1-e30-t23`), so running the
      removal again lists it however long after, once the archive is gone too.
- [ ] **Where the upload is now** (`v1-e30-t21`). A weekly archive whose every member was removed or
      held leaves the inbox when `caselist pull` finishes importing it, and the import stage's
      reason says *N archive(s) taken out of the inbox, which held only files removed or held at a
      removed path*. Any other archive, and every complete archive, holds other teams' files as
      well, so it stays until retention removes it, once its snapshot is confirmed in the bucket
      (usually the same run). An archive you imported by hand with `caselist import` stays where it
      is either way.
- [ ] **`caselist status` says when the removal is owed again** (`v1-e30-t21`). Under its table:
      - *HELD UPLOADS IN THE DOWNLOAD INBOX for `<caselist>`*: an upload at a held path in an
        archive in the inbox, refused at import or waiting to be;
      - *HELD PATH ROWS in `<caselist>` `<snapshot>`: N row(s) at a path a removal holds*: a stored
        row at a held path, which a build from before `v1-e30-t13` imported. `caselist publish`
        withholds that snapshot's manifest, with the code `MANIFEST_NAMES_SUPPRESSED_SOURCE`, as it
        withholds one with a suppressed row. It does not upload the row's bytes either, unless
        another row names them, such as another team's copy at its own path (`v1-e30-t22`), and
        `store sync` does not push them. They stay in this machine's store until the re-run below.
        Bytes a build before `v1-e30-t22` published are in the bucket until then;
      - *HELD PATH ROWS in `<caselist>` `<snapshot>`: N skipped member row(s) at a path a removal
        holds*: the row of a symbolic link or other skipped member at a held path, which every build
        before `v1-e30-t22` wrote. Its body is often the removed file's name. This build's import
        gives such a member no row. `caselist publish` withholds a manifest that has one an earlier
        build wrote, with the code `MANIFEST_NAMES_SUPPRESSED_SOURCE`, as it withholds one with a
        held row (`v1-e30-t23`), so a publish that succeeded over it now fails until the re-run below
        drops the row. A manifest an earlier build published is in the bucket until then;
      - *REFUSED AT IMPORT AT A HELD PATH in `<caselist>`: N upload(s) the same removal has not yet
        listed* (`v1-e30-t24`): an upload this build refused at a held path, from
        `held-digests.jsonl` in either place, which the re-run below has not yet put on the list,
        whole or for the held path. It is named whether or not its archive is still in the inbox,
        so an upload that left with its archive is still said to be owed. An upload whose archive
        is still waiting is in the *HELD UPLOADS* line too;
      - then *RM-… is owed again*. Each file is named by the first twelve characters of its sha256
        and the request holding its path, a skipped member by the request alone, and `--json` gives
        the same as `held_in_inbox`, `refused_at_import`, each snapshot's `held_rows`,
        `held_row_prefixes`, `held_row_requests`, `held_skipped_rows` and
        `held_skipped_row_requests`, and `removals_owed`.
      None changes the exit code: the command still exits 0 when the bucket agrees.
- [ ] **Finish it by running the same removal again**, dry run first: the same `--source`, the same
      `--request` and `--reason`, in dev and then prod. Do this after any pull that reported a held
      upload or after which `caselist status` says the removal is owed, and after every pull while
      the agent runs a build from before `v1-e30-t13`.

      ```bash
      DEBATE_ENV=dev uv run debate-research caselist remove --source <sha256> --request RM-2026-01 --reason REQUESTED_BY_TEAM
      ```

      The removed file's own rows are gone, so the plan finds its path from the path entry. Under
      *LATER UPLOADS AT A REMOVED PATH* it lists whatever is at that path in a later snapshot:
      - *in the download inbox …, not in the store*: this build refused it. `--execute` puts its
        sha256 on the list under the request and deletes the imported archive from the inbox.
      - *held in `<snapshot>`*: a build from before `v1-e30-t13` imported it. `--execute` removes it
        from the store and the bucket as it removes any later upload, every version: its blob on
        this machine goes too, unless another team's row names the same bytes at its own path, when
        only its row at the held path goes. Its bytes are in the bucket only if a build before
        `v1-e30-t22` published them.
      - under its own heading, *REFUSED AT IMPORT AT A HELD PATH*: this build refused it, and its
        archive has since left the inbox. The plan finds it in `held-digests.jsonl` (`v1-e30-t23`)
        and names it by its sha256 and the caselist alone, since nothing else records its path.
        `--execute` puts its sha256 on the list under the request, so the same bytes are refused at
        any path from then on. Where another team's row names the same bytes at its own path, only
        the held path is suppressed, and their copy stays.
      - nothing, and *Nothing is left to remove*: nothing arrived.
      Then execute as in step 5, and verify as in step 6. The path stays held afterwards. A
      symbolic link or other skipped member at the held path, in an archive waiting to be
      imported, is taken out of it in the same rewrite (`v1-e30-t21`); its body is often the file's
      name. A row an earlier build wrote for one in a manifest is dropped from that manifest, here
      and in the bucket (`v1-e30-t22`). `caselist status` then says nothing is owed.
- [ ] **After a `--team` removal**, run the same `--team` dry run again once the next weekly is
      imported: it selects by the team's directories, so it lists anything new there, and
      `--execute` removes it under the same request id. A `--team` removal holds no path, so until
      you do, a new file of the team's is in the store.

Once E34 is running, the scheduled download inherits this check because everything it downloads
goes through the same importer. For an OpenEv camp file it does more: `caselist pull` reads the same
list before it fetches anything, and a camp file whose every member is suppressed is reported as
`skipped_as_removed` and never requested from OpenCaselist again (`v1-e34-t07`). Check for that
decision in the next run's `openev_selections`. A weekly archive is still downloaded, because it
holds other teams' disclosures too, and the importer refuses the removed files inside it.

## Step 10 — Close it out

- [ ] Fill in the Outcome column of the register entry: sources removed, snapshots affected,
      whether anything was left in place as shared, the inbox files deleted and rewritten in each
      environment (the `DONE` line), and the date completed. Counts and codes only, as for the rest
      of the entry — no filename.
- [ ] Reply to the requester confirming completion, naming what was removed in their terms (their
      team, their rounds) and anything that was not, with the reason. Take it from the run that
      removed it: a run of the same command again that finds nothing left says *Removed from this
      environment: nothing; this run found nothing left to remove* (`v1-e30-t20`).
- [ ] Commit the register update. No personal data in the diff or the commit message.

## Camp rows that carry no upstream identity

Every row of a camp release manifest that `caselist pull` writes carries the OpenEv id it was
downloaded as and the SHA-256 of that id's upstream path, never the path (`v1-e30-t14`). A plan in
either environment matches a camp file's later upload by them, so prod, which never pulls and has
no delivery record, matches as dev does. Rows written before `v1-e30-t14`, or since by a weekly
agent on an older build, carry neither, and a plan over them says *matched by file name alone*. A
hand-imported row carries the id only if its name gives one, and never the path; it is never a later
upload, so nothing needs it.

Give the rows their identity in the dev data directory, from this machine's delivery record, with
a build that has `v1-e30-t14` (`uv run` in a checkout of `dev` after it merges). Do it for each
release under `manifests/openev/`; today that is `2026-policy`. First the dry run, which writes
nothing:

```bash
DEBATE_ENV=dev uv run debate-research caselist reimport-openev-metadata --year 2026 --event policy --dry-run
```

Its caption says how many rows it would give their upstream identity: every member row of a
release published before `v1-e30-t14`. The camps before and after should be the same, and titles
changed 0, unless the alias table changed since the release was last re-derived. Then apply it and
publish it to dev:

```bash
aws sso login --profile debate-dev-evidence
DEBATE_ENV=dev uv run debate-research caselist reimport-openev-metadata --year 2026 --event policy
DEBATE_ENV=dev uv run debate-research caselist status --caselist openev
DEBATE_ENV=dev uv run debate-research caselist publish --caselist openev --snapshot 2026-policy
DEBATE_ENV=dev uv run debate-research caselist status --caselist openev
```

The first `status` exits 1 with `CASELIST_DRIFT`, naming `openev 2026-policy (manifest mismatch)`,
and its hint says a manifest mismatch is this machine's copy rewritten since its last publish and
to run `caselist publish --caselist openev`. That is the re-derive, not a fault (`v1-e30-t12`). The
publish uploads the manifest and no source, and the second `status` exits 0. Then prod, from the same
data directory:

```bash
aws sso login --profile debate-prod-evidence
DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research caselist publish --caselist openev --snapshot 2026-policy --dry-run
DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research caselist publish --caselist openev --snapshot 2026-policy --confirm-prod
DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research caselist status --caselist openev
```

The prod dry run plans 0 uploads and the manifest; the real run uploads the manifest and no source;
`status` exits 0. A removal planned in prod then says *matched by upstream path*.

Until the weekly agent runs a build with `v1-e30-t14`, each camp file it pulls adds a row without
the two keys. Run the re-derive and the two publishes again before a removal of a camp file that
was pulled since.

## When `caselist status` reports removal residue

`caselist status` also lists the bucket's object versions and reports, for each caselist, what the
bucket still holds of files the suppression list says were removed (`v1-e30-t10`), and the manifest
and aggregate versions older than a removal that touched the caselist (`v1-e30-t15`). It runs with
the everyday profile, it only lists, and it never uses the takedown profile. Under its table it says
some of these:

- *No version of a removed file is left under raw/ or parsed/, and no manifest or aggregate version
  is older than a removal that touched its caselist (N caselist(s) checked).* Nothing to do.
- *REMOVAL RESIDUE in `<caselist>`: N current object(s), N noncurrent version(s) and N delete
  marker(s) of N file(s) (sha256 `<twelve characters>`, …).* The command exits 1. The steps below
  clear it.
- *REMOVAL RESIDUE in `<caselist>`: N manifest version(s) and N index.jsonl version(s) older than
  `RM-…`, completed `<date> <time>` UTC.* The command exits 1. See
  [Versions older than a removal](#versions-older-than-a-removal) below. One line can carry both
  kinds, separated by a semicolon.
- *SUPPRESSED SOURCE OBJECTS in `<caselist>`: N current object(s) (sha256 `<twelve characters>`,
  …).* The bucket's current listing of the caselist's sources still holds a removed file
  (`v1-e30-t12`). The command exits 1. Where the residue was checked the same file is in a REMOVAL
  RESIDUE line too; where it was not, this line is the only one that shows it. The steps below
  clear it.
- *Removal residue NOT CHECKED for `<caselist>`.* The profile was refused the version listing. That
  is not a finding of none: see [Not checked](#not-checked) below.
- *Manifest and aggregate versions NOT CHECKED against `RM-…`.* That removal was made by a build from
  before `v1-e30-t15`, which did not record which caselists it touched, so nothing is compared with
  it. That is not a finding of none either, and it does not change the exit code. It stays for as
  long as that log entry is the request's.
- *WITHDRAWN COPIES LEFT in `<caselist>`: N current object(s), N noncurrent version(s) and N delete
  marker(s) of N file(s) withdrawn from `<caselist>` (sha256 `<twelve characters>`, `RM-…`, …).*
  (`v1-e30-t19`.) A shared file withdrawn from one team is suppressed for that team's path, not
  whole, so the lines above never name it. But a caselist's copy is its own object, and the
  withdrawal deleted it because no other holder in that caselist kept the file. The withdrawal
  record beside the list (`withdrawals.jsonl`, `v1-e30-t16`) says which caselist each copy was taken
  from and under which request, so this line names both. The command exits 1, as `REMOVAL_RESIDUE`
  when every snapshot agrees (`v1-e30-t24`; until then it did not change the exit code). Clear it as
  [Versions older than a removal](#versions-older-than-a-removal) says: run that request's command
  again.
- *Withdrawals NOT ATTRIBUTED to a caselist: `RM-…`.* A withdrawal the list still suppresses that no
  withdrawal record attributes: a removal by a build from before `v1-e30-t16`, which recorded no
  caselist. What is left of its copies is not checked. That is not a finding of none, and it does
  not change the exit code.

When the command exits 1, the panel under the table says why in counts (`v1-e30-t24`): the
environment and bucket, how many snapshots were compared and how many differ, and one line for each
snapshot that differs, naming at most three of its digests by their first twelve characters. Every
digest in full is in `--json`, under `error.details`, which holds the whole report.

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
profile and `--confirm-prod`, and run every `caselist status` with
`DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev"`, as in step 7. Against prod's own data
directory every snapshot reads as drift, so steps 2 and 3 below cannot be read from it: every status
would say `CASELIST_DRIFT` and none would exit 0.

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

   - [ ] It exits 0 and says *No version of a removed file is left under raw/ or parsed/, and no
         manifest or aggregate version is older than a removal that touched its caselist*. With
         `--json`, every entry of `removal_residue` has `"checked": true`, `"files": []` and
         `"older_versions": []`.
   - [ ] If the plan you executed listed a `parsed/<caselist>/<version>/index.jsonl`, rebuild that
         caselist's aggregates as in step 5. Any executed removal deletes them.
   - [ ] The register entry for the request records that residue was found and cleared, with the
         counts and the date. Counts and codes only.

### Versions older than a removal

A removal deletes every version of the parsed store's `index.jsonl`, `failures.jsonl` and
`occurrences.jsonl`, in every version directory, and it rewrites each manifest that held the file
and purges every other version of it. So in a caselist the removal touched, a version of one of
those older than the removal is something it should have taken: an old manifest version can hold
the removed row, and an old aggregate a removed card's tag. A newer one is an ordinary later write,
such as the aggregates the parse in step 5 rebuilt.

The command finds them from the listing's times and the removal log, downloading nothing. Each
removal records, beside its log entry in `removal-scopes.jsonl`, the caselists it touched and the
manifests it rewrote. Per caselist it compares with the latest completed removal that touched it,
in this environment only. A version counts as older when it is more than 15 minutes older than the
removal's completion, because S3 stamps a version with its clock and the log with this machine's.
S3 refuses a request from a machine whose clock is more than 15 minutes out.

| Role | What the bucket holds | How it gets there |
|---|---|---|
| manifest | A version of a manifest the removal rewrote, other than the rewrite, written before it | A purge that did not finish: the run stopped between writing the manifest and purging it, or something put the version back |
| index.jsonl, failures.jsonl, occurrences.jsonl | A version of an aggregate, current or not, written before the removal | A takedown that stopped before the aggregates, or a version put back |

**Clearing it.** Run the removal again under the same request: name one file the request removed,
by `--source`, with the same `--request` and `--reason`. The request id is the one the line names.
The sha256 values it removed are in that request's removal-log line, in `removed_sha256`. This
`grep` prints the line, which holds sha256 values, counts and codes only:

```bash
grep '"request_id":"RM-2026-01"' "$HOME/.debate-research/dev/suppression/removal-log.jsonl"
```

In prod the line is in the bucket's copy, `manifests/_suppression/removal-log.jsonl`, unless prod's
removal ran from this machine with prod's data directory. Then the dry run and `--execute`, as
step 2 above shows for a file:

```bash
DEBATE_ENV=dev uv run debate-research caselist remove --source <sha256> --request RM-2026-01 --reason REQUESTED_BY_TEAM
```

- **Aggregates.** The plan lists every aggregate under *WILL BE REMOVED*, the old versions with
  the new ones, because a removal of a whole file deletes every caselist's. `--execute` deletes
  them all. Rebuild them afterwards as in step 5.
- **A manifest version alone.** The plan prints *MANIFEST VERSIONS SWEPT from the bucket by
  --execute: N noncurrent version(s) of N manifest(s)*, each manifest with its count, and the
  command under *TO CARRY IT OUT* (`v1-e30-t19`). Until then it read current manifests only and said
  *Nothing is left to remove*. The sweep deletes two kinds, and only these: a noncurrent version of
  a manifest of the caselist that names the removed file, and a noncurrent version of a manifest
  this request rewrote that the run's purge should have taken, whatever it names. For a run that
  completed, that is the version `caselist status` counts: other than the rewrite, and older than
  the run's completion less fifteen minutes (`v1-e30-t24`). One status and the sweep disagreed on
  until then, such as a version in the same second as the rewrite or a publish from another machine
  while the run went on, is now cleared by the re-run. For a run that stopped, which status never
  counts, it is a version older than its rewrite. It never deletes the current version, the
  latest rewrite, a version written after the run, or a version of a manifest no run of this
  request rewrote that names nothing removed. Where the everyday profile may not list or read
  those versions the line says *not counted*, and the command is still printed.
- **A request that removed no whole file** (its `removed_sha256` is empty, only `withdrawn_sha256`).
  Run the request's own command again: the same `--team`, `--request` and `--reason`. Its first run
  deleted the team's records and rows, so nothing shows the team's paths any more; the plan names
  each file *withdrawn earlier from `<caselist>`, as the withdrawal record says*, and lists that
  caselist's aggregates, and the copy in the caselist when no other holder there keeps it. A
  `--source` request's withdrawn later upload is planned again the same way when its copy is still
  in such a caselist.

Then run `caselist status` again. Every kind is cleared that way, and
`test_versions_older_than_a_removal_are_cleared_by_running_it_again_under_the_same_request` and
`test_an_old_manifest_version_alone_is_counted_by_the_dry_run_and_cleared_by_its_execution`
(`tests/smoke/test_caselist_remove_smoke.py`), and `test_residue_clearing_gaps.py`,
`test_status_and_the_sweep_share_one_rule.py` and `test_one_rule_for_rewritten_manifests_property.py`
(`packages/debate_core/tests/application/caselist/`), prove it. Two cases are still not cleared
that way. Tell the PM about either, and do not delete anything by hand:

- a manifest count that stays after the re-run, where the plan swept nothing of that manifest:
  status and the sweep decide those versions by one rule since `v1-e30-t24`, so this should not
  happen;
- a withdrawal-only request whose plan says *no withdrawal record names the caselist it was
  withdrawn from*: a build from before `v1-e30-t16` made its first run.

**What the report does not see.** It matches `raw/` and `parsed/` objects by their key, which is
the file's sha256, and the aggregates and the rewritten manifests by their time. So:

- It does not read manifests. A current manifest version is never counted as older than a removal:
  where it is not this machine's, it is a manifest mismatch in the table. A version of a manifest
  the removal *did not rewrite*, older than it,
  is not counted, even if it still names a removed row: the removal's sweep reads those, keeps the
  ones that name nothing removed, and deletes the rest. Telling the two apart would mean downloading
  each. A camp release's manifest re-published by `caselist reimport-openev-metadata` keeps such a
  version by design. Every executed removal sweeps them again, a re-run included.
- It compares nothing with a removal whose build did not record its scope (the *NOT CHECKED
  against `RM-…`* line), and nothing in a caselist no removal touched.
- It reports a shared file withdrawn from one team and kept for another only by the withdrawal
  record (*WITHDRAWN COPIES LEFT*, above), and only in a caselist that keeps no holder of it, where
  its copy is the withdrawal's to have deleted. In a caselist another holder keeps it in, its copy
  is that holder's. A withdrawal with no record is *NOT ATTRIBUTED*, and nothing of it is checked.
- `manifests/_suppression/` is never residue. The list, the removal log, the path holds and the
  scopes are appended to, and their old versions hold sha256 values and request ids, the record of
  what was asked. No removal deletes them.

So the clean line means what it says about `raw/`, `parsed/`, the aggregates and the manifests a
removal rewrote, and no more. The AWS CLI check in step 6 is still there for one key.

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

## A probe a preflight left behind

A probe is the few bytes `--execute` writes and deletes to prove the takedown profile can do both.
Its key is `manifests/_suppression/preflight/<32 hex characters>.txt` and its content is one fixed
line. It names no file, team or request.

One can be left in two ways:

- **Between 2026-10-08 and `v1-e29-t08`**, by an `--execute` with the everyday profile in
  `DEBATE_REMOVAL_PROFILE`. From the day the everyday profile could list object versions
  (`v1-e29-t06`, [evidence-store.md, Later applies](evidence-store.md#later-applies)) it got as far
  as writing the probe and was refused the delete. The command now refuses that profile before it
  writes anything.
- **At any time**, by the takedown role being refused the delete. Fix the grant first
  ([evidence-store.md, If something is wrong](evidence-store.md#if-something-is-wrong)).

Either way the error named the key: *its probe object was left at …*. It is a current version,
and no lifecycle rule expires one outside `exports/`.

**The next takedown removes it** (`v1-e29-t09`). A `caselist remove --execute` or
`caselist unsuppress --execute` whose check passes deletes, with the takedown profile, every version
it found under `manifests/_suppression/preflight/` before it wrote its own probe. So a probe left in
an environment goes with the next request carried out there, and nothing is needed by hand.

**A takedown may report probes it left.** Removing earlier probes never holds a request back: if
the bucket refuses to delete one, the request is still carried out and the command reports it.
The `DONE` output says *N probe version(s) an earlier preflight left under
manifests/_suppression/preflight/ could not be deleted*, and `--json` has the same count, with the
probes' keys, under `data.preflight_probes_left`. Nothing goes in the removal log for them. Remove
them by hand as described below, once you have finished with the request.

**Remove one by hand only when** one of these is true:

- **A takedown or an un-suppress reported probes it could not delete.** They stay until they are
  removed by hand, because the next request would most likely be refused them again.

- **You want the prefix empty before the next request**, and none is due. The count below says
  whether there is anything to remove.
- **The takedown role is the one refused the delete.** Its check never passes, so nothing removes
  probes until the grant is fixed. Fix the grant first
  ([evidence-store.md, If something is wrong](evidence-store.md#if-something-is-wrong)); after
  that the next request removes them, and removing them by hand is only for not waiting.
- **A probe is still there after a request was carried out.** The check leaves alone a probe written
  after it listed the prefix, which only another takedown running at the same moment writes. Count
  again once neither is running; the next request removes any that is left.

**Count them.** Read-only, with the everyday profile. For prod, use `debate-prod-evidence` and
`debate-prod-evidence-a7508de8`.

```bash
aws s3api list-object-versions --profile debate-dev-evidence --bucket debate-dev-evidence-a7508de8 \
    --prefix manifests/_suppression/preflight/ \
    --query '{versions: length(Versions || `[]`), delete_markers: length(DeleteMarkers || `[]`)}' --output json
```

`{"versions": 0, "delete_markers": 0}` means there is nothing to do.

**Delete them**, with the takedown profile, each version by its id. This is the one place this
runbook deletes with the AWS CLI, because no command removes a probe outside a takedown. The suppression list and the
removal log are one level up, under `manifests/_suppression/`, and are never deleted: keep the
prefix exactly as written, ending in `preflight/`. The loop also skips any key that is not under
it. For prod, set `PROFILE=debate-prod-evidence-removal` and `BUCKET=debate-prod-evidence-a7508de8`.

```bash
aws sso login --profile debate-dev-evidence-removal
PROFILE=debate-dev-evidence-removal
BUCKET=debate-dev-evidence-a7508de8
aws s3api list-object-versions --profile "$PROFILE" --bucket "$BUCKET" \
    --prefix manifests/_suppression/preflight/ --query 'Versions[].[Key,VersionId]' --output text |
  while read -r KEY VERSION; do
    case "$KEY" in
      manifests/_suppression/preflight/*)
        aws s3api delete-object --profile "$PROFILE" --bucket "$BUCKET" --key "$KEY" --version-id "$VERSION" ;;
    esac
  done
```

It prints the id of each version it deletes, and nothing if there were none. If the count
showed delete markers, someone deleted a probe without a version id: run the block again with
`DeleteMarkers` in place of `Versions`.

- [ ] The count, run again, says `{"versions": 0, "delete_markers": 0}`.
- [ ] The suppression list and the removal log are still there:
      `DEBATE_ENV=dev uv run debate-research store ls manifests/_suppression/` lists both.

Nothing goes in the register for this: a probe is not part of any request.

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

Then prod, with `--confirm-prod`, and re-import the archive that holds the file. `--reason` is
`REMOVED_IN_ERROR` or `REQUEST_WITHDRAWN`. One `unsuppress` lifts every suppression of that sha256, whole-file and
per-path. It also releases the hold on each path that file was removed from (`v1-e30-t13`), and
the dry run says how many: a later upload there is imported again from the next archive that holds
it. Nothing is appended to `path-holds.jsonl` for that. A later upload that a removal put on the
list itself stays suppressed until you `unsuppress` its own sha256. Record the mistake in the
register.

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
  for a camp file's later upload that has not been imported.
- `plan_specs/v1/e30-caselist-ingestion/t13-removed-path-holds-caselist-uploads.yaml` — the path
  entry that holds a removed caselist path, and the inbox in the removal plan.
- `plan_specs/v1/e30-caselist-ingestion/t14-camp-path-identity.yaml` — the upstream identity in
  camp rows, and a camp path withdrawn on its own.
- `plan_specs/v1/e30-caselist-ingestion/t10-removal-docstrings-and-residue.yaml` — the residue
  report in `caselist status`.
- `plan_specs/v1/e29-cloud-evidence-store/t06-removal-grant-scope-test.yaml` — the everyday
  profile's read-only version listing, which the dry run's version counts and the residue report
  both use.
- `plan_specs/v1/e29-cloud-evidence-store/t08-takedown-preflight-identity.yaml` — the check of
  which role the takedown profile is signed in as, and the probe clean-up by hand.
- `plan_specs/v1/e29-cloud-evidence-store/t09-store-error-loose-ends.yaml` — a passing check
  removes the probes earlier checks left, and `unsuppress` runs the same check.
- `plan_specs/v1/e29-cloud-evidence-store/t03-evidence-buckets.yaml` — bucket lifecycle and the
  `EvidenceOperator` and `EvidenceRemoval` permission sets.
- `plan_specs/v2/e35-debate-tub/t05-tub-access-and-removal.yaml` — the V2 takedown flow built on
  this suppression list.
