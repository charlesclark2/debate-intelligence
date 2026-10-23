<!-- docs-index: Publishing the parsed card store without rebuilding it: `caselist parse --publish-only`, when to use it and when to rebuild instead -->
# Publishing the parsed card store without rebuilding it

`debate-research caselist parse --caselist <slug> --publish` rebuilds a caselist's parsed card store
and then publishes it to the environment's evidence bucket. The rebuild re-reads every parsed source
and re-clusters every card, which takes minutes for a large caselist. When the rebuild is already
done, `--publish-only` does the publish on its own:

```bash
uv run debate-research caselist parse --caselist hsld26 --publish-only
```

It publishes the caselist's current version directory (the newest one the installed parser
writes) exactly as the last rebuild left it. It parses nothing and rewrites nothing on this Mac.
It uses the same publisher as `--publish`, so it withholds the same suppressed and held sources,
sends the index, failures file and occurrence table last, and skips every object the bucket already
holds with the same bytes. An older version directory is never published.

## When to use it

**A publish that failed after its rebuild had finished.** `caselist parse --publish` ended with
`PARSED_PUBLISH_INCOMPLETE`, for example because the bucket did not answer or the AWS session
expired part-way through the upload. The rebuild finished before the publish started, so retry only
the publish. The failure's hint gives the command:

```bash
aws sso login --profile debate-dev-evidence
uv run debate-research caselist parse --caselist hsld26 --publish-only
```

A checksum mismatch among the failures still needs a person: `--publish-only` leaves a per-source
file the bucket holds with other bytes alone, as `--publish` does.

**The same store sent to a second environment.** Production's parsed store is published from dev's
data directory. After the dev rebuild and publish, send that directory to prod without rebuilding
it again:

```bash
uv run debate-research caselist parse --caselist hsld26 --publish
DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research caselist parse --caselist hsld26 --publish-only --confirm-prod
unset DEBATE_ENV DEBATE_STORAGE__DATA_DIR
```

The prod line needs `--confirm-prod`, as `--publish` does there. The `unset` matters for the same
reason it does in the backfill runbook: a shell left on prod with dev's data directory is how a
later command reaches the wrong bucket.

## When to rebuild instead

Use `--publish`, not `--publish-only`, in these cases:

* **After a removal, in either environment.** A removal deletes the caselist's index, failures file
  and occurrence table on the machine it runs on, so `--publish-only` refuses there anyway. On a
  data directory the removal did not touch, the aggregates were built before it. `--publish`
  rebuilds them from the suppression list of the environment it publishes to. `--publish-only` now
  refuses this case too (`PARSED_AGGREGATES_NAME_WHAT_THE_LIST_STOPS`, below): before uploading
  anything, it checks the aggregates against the suppression list of the environment it publishes
  to. The refusal is the backstop; run `--publish` after a removal without waiting for it.
* **After a weekly run whose parse stage was `pending` for want of a login.** That rebuild may have
  read only this Mac's copy of the suppression list, and those aggregates are never what gets
  published. The pull's summary shows `suppression_list_local_copy_only` when that happened.
* **After installing a build with a new parser, style profile or fingerprint version.** The current
  directory is then not what the new build's rebuild would publish, and `--publish-only` refuses it
  (see below).

## What it refuses

Before anything is uploaded, the version directory is checked. A refusal exits `1`, uploads
nothing, and its hint names the command to run instead. Each refusal has its own code:

| Code | What it means | What to run |
|---|---|---|
| `PARSED_VERSION_DIRECTORY_MISSING` | The installed parser has never parsed this caselist on this Mac | `--publish` |
| `PARSED_AGGREGATES_MISSING` | The index, failures file or occurrence table is gone: a removal, or a rebuild that never finished | `--publish` |
| `PARSED_SOURCE_FILES_MISSING` | The index names a source whose per-source file is gone | `--publish` |
| `PARSED_BY_ANOTHER_PARSER_VERSION` | The directory holds sources parsed under another parser or style profile version | `--publish`, which starts a new generation |
| `PARSED_FINGERPRINT_VERSION_MISMATCH` | The occurrence table is not stamped with this build's fingerprint version throughout, or a per-source record was stamped by a newer build | `--publish` for an older stamp; a build at the newer version for a newer one |
| `PARSED_AGGREGATES_NAME_WHAT_THE_LIST_STOPS` | The index names a source, or the occurrence table a disclosure, that the suppression list of the environment being published to now stops or holds: a removal recorded there after the last rebuild, for example one made in prod and not in dev | `--publish` in that environment, which rebuilds the aggregates from its list |

A per-source record stamped with an *older* fingerprint version is not refused. A fingerprint
change re-parses nothing, so such records are what a rebuild by this build leaves, and `--publish`
sends them too.

These options cannot be combined with `--publish-only`, and the command exits `2` without reading or
writing anything if they are: `--publish` (it rebuilds first), `--reparse`, `--snapshot` and
`--dry-run` (they only shape a rebuild), and `--failures` (it lists, and publishes nothing).

## What it reports

The `publish` part of `--json` is the same object `--publish` reports: the bucket, the prefix,
counts of uploaded, skipped, suppressed and failed objects, whether the aggregates were published or
withheld, and the failure codes. The envelope adds `"publish_only": true`. Like everything else this
command prints, it holds counts, versions and keys, never a path, a school, a team code or a file
name.

A publish that leaves anything unconfirmed exits as `--publish` does: `3` when every failure is one
a retry may cure, such as a bucket that did not answer, and `1` as soon as one is not, such as a
checksum mismatch. A rerun over a bucket that already holds everything uploads nothing and reports
every object `skipped`.
