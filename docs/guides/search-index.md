<!-- docs-index: Building and publishing the student search pilot's index with `debate-research tub index build\|publish` -->
# Building and publishing the search pilot's index

How the operator turns this machine's parsed store into the index the student search pilot serves,
and puts it in an evidence bucket. Two commands: `tub index build` and `tub index publish`.

Spec: [`v1-e39-t02`](../../plan_specs/v1/e39-evidence-search-pilot/t02-search-index-build.yaml).
Decision: [ADR-0019](../adr/0019-student-search-pilot-stack-sign-in-and-hosting.md) (c). What the
index holds, column by column: [docs/data/search-index.md](../data/search-index.md). Where it goes
in the bucket: [the store layout](../architecture/evidence-store-layout.md#reportstubsearch-the-student-search-pilots-index).

## Build

`build` reads three things on this machine and nothing else: the parsed store `caselist parse`
wrote, the caselist records the importers wrote, and this environment's copy of the suppression
list. It reaches no bucket and calls no model. Name every store the index should hold; `openev` is
the camp files:

```bash
DEBATE_ENV=dev debate-research tub index build --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev
```

Build an index you will publish on the machine that makes the removals. Every command that writes
the suppression list writes this machine's copy and the bucket's together, so this copy is the whole
list here; no command yet copies a removal made on another machine down from the bucket. The
manifest's `suppression.sha256` says which list a build applied.

It writes one directory, `<data_dir>/tub-index/<index id>/`, and prints the index id, the counts
and the sizes. `--out` puts it somewhere else; `--provenance-limit` (default 5) is how many
occurrences of each card keep who disclosed them. `--json` prints the whole manifest.

It leaves out every entry that is no card: a cite with no text (CITE_ONLY), or no cite and fewer
than 25 words of text (`v1-e39-t12`, [the rule](../data/search-index.md#only-real-cards)). The
table's caption says how many, as `N left out as no card (...)`, and `--json` gives them by store
in `data.not_cards_by_store`; the manifest does not hold them.

A store it cannot read as it stands stops the build with `SEARCH_INDEX_STORE_NOT_READY` and says
which and why, and nothing is written:

* no directory of this build's parser version: run `caselist parse --caselist <slug>` first;
* no `occurrences.jsonl`, which a removal deletes until the next parse: run `caselist parse` again;
* rows of another fingerprint version: run `caselist parse` again;
* a caselist slug whose event this build does not know.

The same store gives the same index, byte for byte, so building twice is harmless and gives the
same index id.

## Publish

`publish` uploads one built directory to the bucket `DEBATE_ENV` names. `--env` must name the same
environment: it is a confirmation, not a choice. Use the index id `build` printed. To dev first:

```bash
aws sso login --sso-session debate
```

```bash
DEBATE_ENV=dev debate-research tub index publish --env dev --index ~/.debate-research/dev/tub-index/INDEX_ID
```

Then prod, from the same directory, with `--confirm-prod`:

```bash
DEBATE_ENV=prod debate-research tub index publish --env prod --index ~/.debate-research/dev/tub-index/INDEX_ID --confirm-prod
```

Replace `INDEX_ID` with the id `build` printed. The dev data directory is the one the parsed store
lives in, so the build and both publishes read it.

It writes three objects, in this order, each checked against the manifest's sha256 as it lands:

1. `reports/tub/search/<index id>/search-index.sqlite.gz`
2. `reports/tub/search/<index id>/manifest.json`
3. `reports/tub/search/current.json`, which the pilot follows, **last**

If any write fails, `current.json` still names the previous index, which is still whole; run the
publish again. It deletes nothing: superseded builds stay until the removal steps of `v1-e39-t07`
prune them.

It refuses, before uploading anything:

* `SEARCH_INDEX_VERSION_MISMATCH`: the index was built by a build with another parser or fingerprint
  version, or another index format. Rebuild it with this build.
* `SEARCH_INDEX_FILES_DAMAGED`: the gzip object is not the one its manifest records, or does not
  decompress to the SQLite file the manifest records. Rebuild it.
* `ENVIRONMENT_MISMATCH`: `--env` is not the environment `DEBATE_ENV` selects.
* `CONFIRMATION_REQUIRED`: prod without `--confirm-prod`.
* `SEARCH_INDEX_WOULD_SHRINK`: the shrink guard (`v1-e39-t14`). The new index holds none of a
  store's documents that the published index holds, or fewer than 90% of them
  (`caselist.search_index_minimum_share_percent`), store by store. The message names the store,
  both counts and the index `current.json` still names. See below.
* `SEARCH_INDEX_STORE_EMPTY`: a store the index was built from has no occurrence rows in its
  aggregates, published index or not. Rebuild that store's aggregates
  (`debate-research caselist parse --caselist <slug> --publish`), or build without it. No flag
  passes this one.
* `CURRENT_SEARCH_INDEX_UNREADABLE`: `current.json`, or the manifest it names, cannot be read, so
  there is nothing to compare the new index with.

### Publishing a real shrink: `--allow-shrink`

Some shrinks are meant: a removal from a small store, the card-only rule of `v1-e39-t12`, or a store
you chose to stop indexing. First account for the counts the refusal printed. A store suddenly at 0
is a store that lost something, and the fix is the store. Then publish the same directory again with
one line saying why. Use the removal's request id where there is one; never card text, a school, a
team code or a file name:

```bash
DEBATE_ENV=dev debate-research tub index publish --env dev --index ~/.debate-research/dev/tub-index/INDEX_ID --allow-shrink "RM-put-the-request-id-here, whole-file removal"
```

It prints `published past the shrink guard with --allow-shrink:`, the counts it passed and your
reason, and the `--json` result carries them as `allowed_shrink`. The reason is not stored in the
manifest or the pointer, which the pilot's function reads strictly. It passes the second and third
refusals above, never `SEARCH_INDEX_STORE_EMPTY`. The weekly run never uses it: it fails its stage
instead, and the [scheduled sync runbook](../runbooks/caselist-scheduled-sync.md#the-shrink-guard)
says what to do next.

## After a removal

A removal adds to the suppression list. The pilot's function hides a newly suppressed occurrence
within five minutes on its own (`v1-e39-t07`), and the next build leaves it out of the index: build
and publish again, then follow the removal runbook's pilot steps.
