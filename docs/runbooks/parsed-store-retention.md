<!-- docs-index: Retiring superseded parsed-store version directories in both buckets and on this machine, and undoing it -->
# Runbook: retiring superseded parsed-store version directories

A parser version bump or a re-parse writes a new version directory of the parsed card store and
leaves the old one, about 5.8 GB, on this machine and in each bucket it was published to. Nothing
reads the old one again. This runbook retires it with `debate-research caselist retire`
(`v1-e31-t16`). The rule it follows, and why the grace period is 30 days, are in
[parsed-card-store.md](../data/parsed-card-store.md#retention).

| Place | What retiring does | Undo |
|---|---|---|
| The dev or prod bucket (`--bucket`) | Tags each object `debate-retention=superseded`. The bucket's lifecycle rule `expire-retired-parsed-version-directories` expires its current version at the next daily run and deletes the noncurrent version 30 days later; `remove-orphaned-parsed-delete-markers` then removes the delete marker left behind | `--restore` until the lifecycle has run; then [copy the versions back](#after-the-lifecycle-has-run) within the 30 days |
| This machine | Deletes the directory | None. Re-parse with the build that wrote it |

So retire in the buckets first, and on this machine last.

## When to run it

After a `caselist parse` that started a new version directory (its dry run says `new_version:
true` and names the directory it supersedes), and after `caselist parse --publish` has put the new
directory in the bucket. Until the new directory is in a bucket, the command calls the old one
there `not_yet_superseded` and refuses it.

## Before you start

* **The installed build is the one that wrote the current directory.** The dry run prints the
  parser version it judges by. A build with an older parser would see the current directory as
  `newer_than_this_build` and refuse it, and nothing would be lost; but it would also not retire
  anything, so update first.
* **The Terraform of `v1-e31-t16` is applied in that environment** ([evidence-store.md](evidence-store.md#later-applies)).
  Without it the bucket refuses the tagging with `AccessDenied` naming `s3:GetObjectTagging`, and
  nothing would expire the tags anyway.
* **The everyday profile, never the takedown's.** The command builds its client from
  `storage.s3.aws_profile` alone and never reads `DEBATE_REMOVAL_PROFILE`.

Sign in once per sitting:

```bash
aws sso login --profile debate-dev-evidence
aws sso login --profile debate-prod-evidence
```

## Step 1: dev bucket, dry run

```bash
DEBATE_ENV=dev debate-research caselist retire --bucket --version 2026.10.10-docx-2
```

The table lists every version directory of every caselist in the dev bucket. Check:

* the directory named shows `superseded` in each caselist that has it, and `would be tagged`;
* the current directory of each caselist shows `current`;
* `Tagged` is 0, or the count of a run that stopped part-way.

The last line is the command to carry it out, ending `--execute --confirm` and a twelve-character
code. The code is a digest of what this dry run showed: if the directory changes, or you run it
against another place, the code no longer matches and nothing happens.

A refusal (`CURRENT_VERSION_DIRECTORY`, `NEWER_THAN_THIS_BUILD`, `NOT_YET_SUPERSEDED`,
`NO_SUCH_VERSION_DIRECTORY`) changes nothing. Read the standing in a dry run without `--version`.

## Step 2: dev bucket, retire

Replace `CODE-FROM-THE-DRY-RUN` with the code step 1 printed. Pasted unchanged, it is refused.

```bash
DEBATE_ENV=dev debate-research caselist retire --bucket --version 2026.10.10-docx-2 --execute --confirm CODE-FROM-THE-DRY-RUN
```

It prints how many objects it tagged in each caselist. It reads and writes each object's tags, one
request each, 16 at a time, so a large directory takes minutes; it has not been timed against a
real bucket yet. Run the dry run again: `Tagged` equals `Objects`. A run that stops part-way is finished by
running steps 1 and 2 again; an object already tagged is not written twice.

## Step 3: prod bucket

The same two commands with `DEBATE_ENV=prod`, and `--confirm-prod` on the second:

```bash
DEBATE_ENV=prod debate-research caselist retire --bucket --version 2026.10.10-docx-2
```

```bash
DEBATE_ENV=prod debate-research caselist retire --bucket --version 2026.10.10-docx-2 --execute --confirm CODE-FROM-THE-DRY-RUN --confirm-prod
```

## Step 4: this machine, last

```bash
DEBATE_ENV=dev debate-research caselist retire --version 2026.10.10-docx-2
```

```bash
DEBATE_ENV=dev debate-research caselist retire --version 2026.10.10-docx-2 --execute --confirm CODE-FROM-THE-DRY-RUN
```

The directory is deleted. A directory this machine no longer has is refused as
`NO_SUCH_VERSION_DIRECTORY`, which is the answer for `2026.09.20-docx-1` here: it was deleted by
hand on 2026-10-11.

## Step 5: record the counts

Add each place's objects and bytes, as the dry run listed them, and the date, to
[Retired so far](../data/parsed-card-store.md#retired-so-far). Counts only.

## The next day: check the lifecycle ran

The tagged objects' current versions expire at the bucket's next daily lifecycle run. After that,
a dry run no longer lists the directory, because nothing current is left under it:

```bash
DEBATE_ENV=dev debate-research caselist retire --bucket
```

The versions are kept 30 days as noncurrent and then deleted, and the next run removes the delete
markers left behind. **Thirty-two days after the first lifecycle run, check the per-source files are
gone**, in each bucket and for one caselist, and record the two numbers in
[Retired so far](../data/parsed-card-store.md#retired-so-far):

```bash
aws s3api list-object-versions --bucket debate-dev-evidence-a7508de8 --prefix parsed/hsld26/2026.10.10-docx-2/sha256/ --profile debate-dev-evidence --query '[length(Versions || `[]`), length(DeleteMarkers || `[]`)]' --output text
```

| It prints | It means |
|---|---|
| `0` and `0` | The grace period ended, the versions were deleted and their markers removed |
| A first number above `0` | The tag filter did not reach the noncurrent versions. They now fall to the general rule and are kept 30 days in dev and 365 in prod after they became noncurrent: longer, never shorter. Record it and tell the PM |
| `0`, then a second number above `0` | The versions are gone and the markers are not yet. Check again the next day |

The per-source files are the ones to count because each is written once. The three aggregate
files (`index.jsonl`, `failures.jsonl`, `occurrences.jsonl`) were rewritten by every run, so they
also have older versions that were never tagged and that the general rule deletes on its own clock:
in prod that can be close to a year. They hold counts and pseudonyms, as the current ones do.

## Undoing it

### Before the lifecycle has run

`--restore` sets the tag to `restored`, which the lifecycle rule does not match. A dry run first,
as always:

```bash
DEBATE_ENV=dev debate-research caselist retire --bucket --version 2026.10.10-docx-2 --restore
```

```bash
DEBATE_ENV=dev debate-research caselist retire --bucket --version 2026.10.10-docx-2 --restore --execute --confirm CODE-FROM-THE-DRY-RUN
```

### After the lifecycle has run

For 30 days the expired objects are noncurrent versions, and the everyday profile can copy each
back as a new current version with `GetObjectVersion` and `PutObject`. The copy is tagged
`restored`, so the rule leaves it alone. Run this only for a directory the dry run no longer lists,
one caselist at a time; for a directory that still has current objects it would put older versions
over them.

`test_version_retention_lifecycle.py` runs these two blocks as they are written here, against a
bucket the lifecycle rules have expired, and checks every request against the everyday grants. A
change to either block is a change to that test.

The first block lists the newest noncurrent version of each key into a file:

```bash
BUCKET=debate-dev-evidence-a7508de8
PREFIX=parsed/hsld26/2026.10.10-docx-2/
aws s3api list-object-versions --bucket "${BUCKET}" --prefix "${PREFIX}" --profile debate-dev-evidence --query 'Versions[?IsLatest==`false`].[Key,VersionId]' --output text | awk 'seen[$1]++ == 0' > restore-versions.txt
wc -l restore-versions.txt
```

The count should be the directory's object count from its dry run. The second block copies them
back:

```bash
while read -r key version; do aws s3api copy-object --bucket "${BUCKET}" --key "${key}" --copy-source "${BUCKET}/${key}?versionId=${version}" --tagging-directive REPLACE --tagging "debate-retention=restored" --profile debate-dev-evidence > /dev/null; done < restore-versions.txt
```

The dry run then lists the directory again, with every object in it.

### On this machine

There is no undo. The directory can be rebuilt by `caselist parse` under the build that wrote it.

## Retiring `2026.09.20-docx-1` and `2026.10.10-docx-2` (`v1-e31-t16`, ac4)

The first retirements, after this task merged and its Terraform was applied:

| Directory | This machine | dev bucket | prod bucket |
|---|---|---|---|
| `2026.09.20-docx-1` | already deleted by hand, 2026-10-11 | steps 1 and 2 | step 3 |
| `2026.10.10-docx-2` | step 4 | steps 1 and 2 | step 3 |

`2026.10.12-docx-3` must be in each bucket for every caselist first: the dry run says
`not_yet_superseded` where it is not. Both directories can be named in one run, with `--version`
twice. Record the counts as step 5 says.
