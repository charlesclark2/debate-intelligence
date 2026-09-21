# Moving evidence with `debate-research store`

How to get evidence from your machine into the team's evidence bucket, and back. Three commands:
`store sync`, `store ls` and `store get`.

Spec: [`v1-e29-t05-evidence-sync-cli`](../../plan_specs/v1/e29-cloud-evidence-store/t05-evidence-sync-cli.yaml).
Key layout: [evidence-store-layout.md](../architecture/evidence-store-layout.md). Applying the
buckets and the credentials: [runbooks/evidence-store.md](../runbooks/evidence-store.md).

## The one thing to know first

**`store sync` does not write anything unless you say `--apply`.** On its own it lists both sides,
prints what it *would* do, and stops. That is the opposite of most sync tools and it is
deliberate: this command writes to the team's system of record, and the cheapest moment to notice
that your local store is not what you thought is before the upload.

```bash
debate-research store sync            # what would change
debate-research store sync --apply    # do it
```

## Before the first run

You need an SSO session for the environment's evidence profile. The profiles come from Terraform
(`evidence_operator_profile_name`) and are set up once with `aws configure sso`:

| Environment | Bucket | Profile |
|---|---|---|
| `dev` | `debate-dev-evidence-a7508de8` | `debate-dev-evidence` |
| `prod` | `debate-prod-evidence-a7508de8` | `debate-prod-evidence` |

```bash
aws sso login --profile debate-dev-evidence
```

A session lasts hours, and syncing a whole corpus takes longer than one sitting, so you will meet
the expiry. It looks like this, and it is not an error you need to investigate:

```
STORE_CREDENTIALS_EXPIRED
the AWS session for s3://debate-dev-evidence-a7508de8 has expired: aws sso login --profile debate-dev-evidence
```

Log in again and re-run the same command. Everything that already transferred is journaled and is
skipped — see [Resuming](#resuming).

## Which environment, and therefore which bucket

`DEBATE_ENV` decides, and nothing else does. There is no `--bucket` flag, because a command that
could be pointed at production by a typo in an argument is a command that eventually is.

```bash
DEBATE_ENV=dev  debate-research store sync     # the default in a source checkout
DEBATE_ENV=prod debate-research store sync
```

`DEBATE_ENV=test` names no bucket at all and every `store` command refuses to run under it. That
is what keeps a test run from reaching a real store.

`debate-research config show` prints the bucket, region and profile this run resolved, and where
each value came from.

## Publishing to production

A push to prod needs `--confirm-prod` on top of `--apply`:

```bash
DEBATE_ENV=prod debate-research store sync            # read this first
DEBATE_ENV=prod debate-research store sync --apply --confirm-prod
```

A dry run against prod needs no confirmation — reading the plan is how you decide whether to
confirm — and neither does `--pull`, which writes to your machine and not to the team's evidence.

## The two halves of the local store

The local evidence directory holds two trees, and they reach the bucket differently:

| On disk | In the bucket | |
|---|---|---|
| `<data_dir>/objects/manifests/hsld26/2026-09-15.jsonl` | `manifests/hsld26/2026-09-15.jsonl` | named objects: same key both sides |
| `<data_dir>/blobs/sha256/ab/cd/abcd…` | `<corpus prefix>/sha256/ab/cd/abcd…` | content-addressed: needs `--blob-prefix` |

A blob's key is the SHA-256 of its own bytes and carries no record of which archive it belongs to,
so you have to say:

```bash
debate-research store sync --blob-prefix raw/caselist/hsld26 --apply
debate-research store sync --blob-prefix raw/openev/2026 --apply
```

Without it, a run that has blobs to move stops and says so rather than filing a season's
disclosures under a guess.

`--prefix` is a different thing: it *filters* by bucket key, for when you want one part of the
store.

```bash
debate-research store sync --prefix manifests/hsld26/
```

## What the summary means

```
        push dev -> debate-dev-evidence-a7508de8
┌──────────────┬─────────┬──────────┐
│ Action       │ Objects │ Bytes    │
├──────────────┼─────────┼──────────┤
│ new          │ 2314    │ 298.7 MB │
│ changed      │ 1       │ 42.1 KB  │
│ skipped      │ 0       │ 0 B      │
│ would_delete │ 3       │ 1.2 MB   │
└──────────────┴─────────┴──────────┘
 Planned only; nothing was transferred. 1 head request(s). Re-run with --apply to move it.
```

| Action | What it means |
|---|---|
| `new` | Not in the bucket. Will be uploaded. |
| `changed` | In the bucket with different bytes. Will be overwritten. **Named objects only** — a manifest that gained rows is the normal case. |
| `skipped` | Already there and identical, or outside the documented prefixes. |
| `would_delete` | In the bucket and not on your machine. **Reported and left alone.** |
| `mismatched` | A content-addressed key whose two sides differ. Never written over, and it fails the run — see below. |

`would_delete` is never acted on. V1's sync does not delete, the everyday profiles *cannot*
delete, and removing evidence is a separate procedure with its own credential
([runbooks/caselist-removal.md](../runbooks/caselist-removal.md)). A large `would_delete` count
usually just means your machine holds less than the bucket does.

## Verification

Every upload is confirmed by asking the bucket, separately, what it now holds: the SHA-256 the
store records must match what was sent. Every download is re-hashed before it is allowed into the
local store, and a blob is additionally checked against the digest its own key states.

An object that fails to verify is marked failed, the run carries on with the rest, and the command
exits non-zero with the count and the first key. Re-run the same command — everything that did
verify is journaled and will be skipped.

`mismatched` is the serious one. A key that is the SHA-256 of its own bytes cannot legitimately
hold two different things, so the two stores disagreeing about one means something already went
wrong. Nothing is overwritten, the run fails, and it needs a person: check the object's version
history in the bucket before touching either side.

## Resuming

Every verified transfer is appended to a journal, one line at a time, flushed as it goes:

```
<data_dir>/sync-journal/<environment>.jsonl
```

So a sync you interrupt — Ctrl-C, a closed laptop, an expired session — is resumed by running the
same command again. It lists both sides afresh, and an object that is both present in the bucket
and journaled at the digest you would send costs nothing at all to skip: no download, no upload,
not even a `HeadObject`.

The journal is never on its own a reason to skip something. If the bucket no longer holds an
object, it is uploaded again whatever the journal says; if your local copy changed, it is
re-uploaded. Deleting the journal is safe — the next run just pays for a few more `HeadObject`
calls.

## Reading the store

```bash
debate-research store ls                       # every documented prefix
debate-research store ls manifests/hsld26/     # one prefix
debate-research store get manifests/hsld26/2026-09-15.jsonl
debate-research store get manifests/hsld26/2026-09-15.jsonl -o /tmp/manifest.jsonl
```

`store get` with no `-o` puts the object where the local store keeps it, verifying it on the way
in, which is where a later `sync` expects to find it.

Note that `ls` with no prefix lists the eight documented prefixes in turn rather than the bucket
root: the operator credential may list each prefix and may *not* list the bucket itself, on
purpose.

## Scripting it

`--json` prints one object on stdout and puts every diagnostic on stderr. A successful run is
`status: "ok"` with the payload under `data`; a failed one is `status: "error"` with the same
payload under `error.details`, so a consumer keeps every count either way.

```bash
debate-research --json store sync | jq '.data.counts'
```

Exit codes: `0` success, `1` a failure you have to deal with (an object that would not verify, a
mismatch, no bucket for this environment, a prod push with no `--confirm-prod`), `2` a bad command
line, `3` a provider failure.

## The first sync of a whole corpus

A first push of the hsld26 caselist snapshots is roughly 2,300 files and about 300 MB. That is one
`ListObjectsV2` page-through per prefix, no `HeadObject` calls at all (every object is new), and
2,300 single-part `PutObject` calls — each a few hundred kilobytes, well under the 64 MiB
multipart threshold. Expect it to run for longer than a few minutes, so it is an operator step,
not something a session starts:

```bash
aws sso login --profile debate-dev-evidence
DEBATE_ENV=dev debate-research --verbose store sync \
  --blob-prefix raw/caselist/hsld26 --apply
```

Run the dry run first and check the counts against what you expect to be on disk. If the session
expires part-way through, log in again and run the same command: it resumes.

The bulk load itself is [`v1-e30-t06`](../../plan_specs/v1/e30-caselist-ingestion/)'s to schedule;
this is the command it uses.
