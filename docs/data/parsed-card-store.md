<!-- docs-index: Layout and record shapes of the parsed card store that caselist parse writes -->
# The parsed card store

`debate-research caselist parse` turns the caselist and camp sources on this machine into a store
of parsed cards. E32 (the argument landscape), E33 (the file builder) and E34 (the scheduled sync)
read it, and `--publish` copies it to the environment's evidence bucket, where the V2 debate tub
indexes it. This page is for anyone writing one of those readers. The definition is
[`debate_core/application/ports/parsed_store.py`](../../packages/debate_core/src/debate_core/application/ports/parsed_store.py),
and where the two disagree, the code is right and this page needs fixing.

## Where it is

The same files at the same keys in two places:

| Where | Root |
|---|---|
| This machine | `<data_dir>/parsed/` (for the operator's store, `~/.debate-research/dev/parsed/`) |
| The evidence bucket for `DEBATE_ENV` | `parsed/` |

Under the root, one directory per caselist (`hsld26`, `hspolicy26`, `hspf26`, and `openev` for
camp files), and under that one directory per parser version:

```
parsed/hsld26/2026.09.20-docx-1/
    sha256/ab/cd/abcd…ef01.jsonl      one file per source: its entry, then its cards
    index.jsonl                        every source's entry, sorted by sha256
    failures.jsonl                     the entries of the sources that did not parse
    occurrences.jsonl                  every card, once per disclosure
```

The per-source files fan out by the first four hex characters of the digest, as the blob store
does, and are named for the digest. That name is what `caselist remove` deletes a parsed file by.

## Version directories

A version directory is named for the `parser_version` that wrote it. Two things make a new one
beside it, and neither touches the old one:

* **A parser version bump.** The new parser writes `parsed/<caselist>/<new parser_version>/`.
* **A re-parse under the same parser version.** `caselist parse --reparse`, or a change of the style
  profile's `profile_version` under the same parser, writes a new generation:
  `2026.09.20-docx-1_reparse-2`, then `_reparse-3`.

The current directory of a caselist is the newest generation of the parser version the reader
runs. Nothing ever writes into an older one again; the local adapter refuses to.

A parser version is bumped whenever what the parser emits changes, and also when the only change
is that a file once refused is now read: a refusal is a recorded entry like any other, so under the
same version the skip key below would pass that file over for good.

| Parser version | What it read | Differs from the one before |
|---|---|---|
| `2026.09.20-docx-1` | The first full corpus, 2026-10-10 ([caselist-parse-report.md](caselist-parse-report.md)) | |
| `2026.10.10-docx-2` | Written by the next `caselist parse` | Reads 23 files refused for the words `system "` and `public '` in card text. Keeps a body paragraph guessed to be a cite in its card. Does not take a blank line in a heading style for a heading. Calls a card `ABBREVIATED` for the shape of a first-and-last-words disclosure, not for an ellipsis. Writes "no tag" as `null`, under record `schema_version` 2 (`v1-e31-t09`) |

## The skip key

A source is parsed once per **(source sha256, parser_version, profile_version)**. A run skips every
source whose key is already recorded in the current directory, so the same file disclosed in
fourteen weekly snapshots is one parse, and a second run over an unchanged store parses nothing.
A camp file and a caselist disclosure of the same bytes are parsed once in each store, because
each caselist's store stands alone: it is published under its own prefix and a removal reaches it
by caselist.

The fingerprint version is not part of the key. A change of it re-parses nothing: see
[Fingerprint versions](#fingerprint-versions).

## Every record

Every line of every file is one JSON object with sorted keys, and every one carries these fields:

| Field | What it is |
|---|---|
| `schema_version` | `2` in a record written now; `1` in every record of `2026.09.20-docx-1`. See [Schema versions](#schema-versions) |
| `record` | `source`, `document` or `occurrence` |
| `caselist` | The caselist slug, or `openev` |
| `snapshot` | `YYYY-MM-DD` for a caselist; `<year>-<event>` for an OpenEv release |
| `source_sha256` | The source file's SHA-256 |
| `parser_version` | The parser that read it, e.g. `2026.09.20-docx-1` |
| `profile_version` | The style profile it resolved through, e.g. `2026.09.20-verbatim-1` |
| `fingerprint_version` | The card matching rules, e.g. `card-fingerprint-v2`. What it says depends on the record: see [Fingerprint versions](#fingerprint-versions) |

### Schema versions

`schema_version` says which shape a record has. A reader that does not go through the Python
models (a `jq` line, a notebook, a later cloud reader) branches on it.

| Version | Written by | What differs |
|---|---|---|
| `1` | `2026.09.20-docx-1` | A stored card's `tag` is always a string. `""` means the file gave the card no tag |
| `2` | `2026.10.10-docx-2` and later (`v1-e31-t09`) | A stored card's `tag` is a string or `null`, and is never `""`. A reader that calls a string function on `tag` needs a null check. Nothing else moved: no field was added, removed or renamed |

A record keeps the version it was written with. The `2026.09.20-docx-1` directories stay version 1,
here and in both buckets, because nothing rewrites a version directory. `LocalParsedStore` and the
record models read both, and refuse a version they do not know and a version-2 document that says
"no tag" as `""`. The source and occurrence records have the same fields under both versions; they
carry 2 because one version covers a directory, so a reader checks one line rather than every
record kind.

### `source`: a line of `index.jsonl`, and the first line of a source's file

| Field | What it is |
|---|---|
| `snapshot` | The snapshot the source was parsed under: the earliest that disclosed it then |
| `source_format` | `DOCX`, `DOC`, `PDF` or `OTHER`, from the manifest |
| `byte_size` | The source's size in bytes |
| `outcome` | `PARSED`, `UNSUPPORTED` or `FAILED` |
| `reason` | Why it has no document; `null` when `PARSED` |
| `detail` | The parser's account of the reason, in limits and formats only |
| `cards` | How many cards its document holds |

`UNSUPPORTED` is a PDF, a legacy `.doc` or another format V1 stores without parsing. It is an
outcome, not a failure: PF alone discloses hundreds of PDFs. Its `reason` is `UNSUPPORTED_FORMAT`
and its `source_format` says which.

`FAILED` has one of these reasons, each counted against the run's failure-rate threshold:

| Reason | Meaning |
|---|---|
| `MALFORMED_PACKAGE`, `NOT_A_ZIP`, `MISSING_DOCUMENT_PART`, `MALFORMED_XML` | A broken file |
| `TOO_LARGE`, `TOO_MANY_ENTRIES`, `COMPRESSION_RATIO_EXCEEDED` | Oversized, or shaped like a zip bomb |
| `MACRO_ENABLED` | A Word package carrying a VBA project |
| `ENCRYPTED` | Password-protected |
| `FORBIDDEN_XML_CONSTRUCT` | A part that declares a document type (`<!DOCTYPE`) or an entity, in any encoding. The words `SYSTEM` and `PUBLIC` in card text are not one |
| `TIMEOUT` | Still parsing at the per-file time limit |
| `WORKER_CRASHED` | The worker process died while parsing it |
| `PARSER_ERROR` | The parser raised instead of returning a failure: a parser bug |
| `SOURCE_INTEGRITY` | The local blob no longer hashes to its own name |
| `SOURCE_MISSING` | Named by a manifest, absent from this machine's blob store. The only failure the next run tries again |

A `.docm` file is stored as format `OTHER` and is `UNSUPPORTED`; `MACRO_ENABLED` is a file named
`.docx` that turns out to carry macros.

### `document`: the second line of a parsed source's file

| Field | What it is |
|---|---|
| `camp` | The OpenEv camp for a camp file; `null` for a disclosure |
| `document` | The source's `ParsedDocument` (`v1-e31-t03`), with two things left out |

What is left out of `document`:

* **`sections`**, every paragraph of the file, about 9,000 for a 300-page file. They are
  reproducible from the source bytes by the same parser version, and no reader needs them.
* **Every disclosure path**: the document's `source_path` and each card's `provenance.source_path`.
  See [What the store does not hold](#what-the-store-does-not-hold).

Everything else is there as `v1-e31-t03` defines it: each card's tag, cites, undertag, evidence
text, formatting and font-size spans as offsets into that text, completeness, match source,
confidence, rule ids, `UNVERIFIED` status and `FILE_IMPORT` provenance with its element range. A
reader in Python calls `DocumentRecord.to_parsed_document(path)` with a path from the manifests and
gets a validated `ParsedDocument` back.

#### A card with no tag

A file may give a card no tag. In a record that is **`"tag": null`**, and from `2026.10.10-docx-2`
on it is never an empty string. In Python, ask `card.has_tag`.

`null` is not a parser failure to work around. What it means depends on the card's `completeness`:

| `tag` | `completeness` | What the file holds there | How to treat it |
|---|---|---|---|
| `null` | `CITE_ONLY` | A citation on its own: a source is named, with no claim and no text | A citation the file lists. Not an argument, and nothing to match a body against |
| `null` | `FULL` or `ABBREVIATED` | Evidence with a cite and no claim line above it | Either the file is written that way, or it is a second card under the tag of the card before it. Its `rule_ids` say which rule read its cite; a first rule beginning `heuristic-` was a guess |

In `2026.09.20-docx-1` the same thing was written as `"tag": ""`, and `to_parsed_document` reads
both. That directory also holds 15,528 such cards against 4,446 expected in the next, because
about 11,000 of them were not cards the file holds: a paragraph inside a card's body had been
read as the cite of a new one. A card whose `rule_ids` include
`assembly-cite-guess-inside-card-body:…` kept such a paragraph in its body.

A heading in a card's `section_path` is never an empty string either. In `2026.09.20-docx-1`,
1,847 cards carry one, from a blank line in a heading style.

#### What `ABBREVIATED` means

From `2026.10.10-docx-2`, a card is `ABBREVIATED` when its body has the shape of a disclosure of
first and last words: **exactly one** ellipsis marker (`…`, `...`, `[…]`, `[...]` or `***`), words on
both sides of it, and **no more than twelve** on either side. A marker in the cite decides nothing.
A whole card whose text leaves something out, once or ten times, is `FULL`.

The bound was set from what a disclosure is, because the corpus has none to measure. Of the 19,402
card bodies that hold a marker, none has a single marker with 15 words or fewer on both sides, and
only 37 are 60 words or shorter in all
([caselist-parse-report.md](caselist-parse-report.md#abbreviated-by-shape)). So over the corpus as
it stood on 2026-10-10 the new parser calls **no card** `ABBREVIATED`, where the first parse called
22,443 so. Expect the value to be rare, and treat a store with none as normal.

**In `2026.09.20-docx-1`, do not read `ABBREVIATED` as "first and last words only".** There it means
an ellipsis marker anywhere in the body or the cite, and 21,278 of its 22,443 `ABBREVIATED` cards
have a body longer than 1,000 characters.

### `occurrence`: a line of `occurrences.jsonl`

One row per card per disclosure. A disclosure is one path holding one file's bytes: however many
weekly manifests list it, it is one row of each of its cards, from one parse, with the first and
the latest snapshot that list it. A path whose bytes change has a new SHA-256, so it is a new source
and a new disclosure. The same bytes under two paths, a team's `(1)` re-upload or a second team
disclosing the file, are two disclosures. A camp file has no disclosure: it is one row per card per
OpenEv release, and its two snapshot fields are that release.

| Field | What it is |
|---|---|
| `snapshot` | The first snapshot whose manifest lists this disclosure |
| `last_snapshot` | The latest such snapshot; equal to `snapshot` for a camp file |
| `disclosure` | SHA-256 of `<caselist>/<path>`, the disclosure's pseudonym; `null` for a camp file |
| `camp` | The camp for a camp file; `null` otherwise |
| `first_element_index`, `last_element_index` | The card's paragraphs in its document |
| `exact_fingerprint` | The card's exact fingerprint (`v1-e31-t04`). The same digest under every fingerprint version so far |
| `cluster_id` | Its cluster: the smallest exact fingerprint among the cluster's full cards, or among its abbreviated cards when no full card is in it. Comparable only between rows of one `fingerprint_version` |
| `membership` | How it got there: `NEAR_DUPLICATE`, `ABBREVIATED_LINK` or `UNLINKED`, below |
| `completeness` | `FULL`, `ABBREVIATED` or `CITE_ONLY` |

`membership`, from `card-fingerprint-v2`:

| Value | Meaning |
|---|---|
| `NEAR_DUPLICATE` | A full card, placed by its text |
| `ABBREVIATED_LINK` | An abbreviated or cite-only card placed by its link key (short cite, first and last words): in a full card's cluster, or, when no full card matches it, in a cluster of abbreviated cards of the same card. The second kind is new in `v2`, and its `cluster_id` is no full card's fingerprint |
| `UNLINKED` | An abbreviated or cite-only card that matched nothing, or two different cards. Its `cluster_id` is its own `exact_fingerprint` |

Who disclosed a card is a join, not a field: compute `sha256(f"{caselist}/{path}")` for each stored
row of the caselist's manifests and match it to `disclosure`. The digest is the same one the
removal suppression list records a withdrawn disclosure under.

**What the span means.** A weekly archive is a window of about a week's editing activity, not the
whole caselist (`docs/data/caselist-backfill-2026-09.md`), so a manifest lists a path in the weeks
a team uploaded or touched it. `last_snapshot` is the latest week that happened, not proof that the
file is still on the caselist. A path missing from some weeks between its first and latest is
still one row. In the 2026-27 weekly manifests as imported on 2026-10-09, 91 to 93% of DOCX
disclosures are listed in one week only, and none in more than five.

## Fingerprint versions

`fingerprint_version` names the card matching rules: the normalization the exact fingerprint is
computed under, and the clustering and linking rules that decide which cards share a `cluster_id`
([`fingerprints.py`](../../packages/debate_core/src/debate_core/evidence/fingerprints.py) lists
each version and what it changed).

| Version | Since | Exact fingerprints | Cluster ids |
|---|---|---|---|
| `card-fingerprint-v1` | `v1-e31-t04` | | |
| `card-fingerprint-v2` | `v1-e31-t08` | the same as `v1` | changed: short cards and abbreviated disclosures that `v1` left apart now share clusters |

**What the stamp says depends on the record.**

* **On an `occurrence`**, it is the version the row's `exact_fingerprint`, `cluster_id` and
  `membership` were computed under. Every row of one `occurrences.jsonl` carries the same version,
  because the file is rebuilt whole on every run.
* **On a `source` or a `document`**, in a per-source file or in `index.jsonl` and `failures.jsonl`,
  it is the version that was in force when the source was parsed, and nothing in the record depends
  on it. A parsed document holds cards as the parser read them: no fingerprint, no cluster id.
  These records are never rewritten, so after a version change they go on saying the old one,
  beside sources parsed since that say the new one. That is not staleness.

**A version change re-parses nothing.** The skip key has no fingerprint version in it, and does not
need one: the only records a fingerprint version decides are the occurrence rows, and the next
`caselist parse` rewrites all of them under the new version from the per-source files it already
has. After that run no row carries a cluster id under an old version
(`test_a_rebuild_after_the_fingerprint_version_changed_leaves_no_old_stamp_on_a_new_cluster_id` in
[`test_caselist_parse.py`](../../packages/debate_core/tests/application/test_caselist_parse.py)).
`--publish` then uploads `occurrences.jsonl` alone, since no other file's bytes changed.

**Between the change and that run**, `occurrences.jsonl` still holds the old version's rows, which
say so. A reader compares the `fingerprint_version` of the occurrence rows it reads with the
version it was written for, and treats a mismatch as "rebuild first". It never mixes cluster ids
of two versions, and never keeps a `cluster_id` as a durable key: keep `exact_fingerprint`.

## What the store does not hold

No disclosure path, no school, no team code, no tournament or round label, and no cutter mark. A
disclosure path names a school and a team code, a team code is personal data about a minor, and the
data-use policy lists where such data may live: the local evidence store, the bucket's `manifests/`
prefix, a built file's provenance sidecar and the per-school landscape view
([caselist-data-use.md](../policies/caselist-data-use.md#personal-data)). The bucket's `parsed/`
prefix is not on that list. So the store is built without them, and what is published is exactly
what is on disk. The mapping from a team to what it disclosed stays in the manifests, where the
evidence-store layout puts it and where a removal rewrites it.

**The store must never gain a path, school, team code, tournament or round field** (PM ruling,
2026-10-10, which keeps the policy as it is). Keeping `parsed/` free of personal data means a
removal has fewer places to clean, and a leak of `parsed/` alone names nobody; a reader that needs
the team joins the manifests, which live under the same controls. `disclosure` is a pseudonym, not
anonymisation: anyone holding the manifests can recompute it. Two tests in
[`test_local_parsed_store.py`](../../packages/debate_core/tests/integrations/test_local_parsed_store.py)
hold the line. `test_no_record_has_a_field_for_a_path_school_team_tournament_or_round` checks the
record models' field names. `test_no_file_names_the_disclosure_path_or_anything_in_it` scans every
written file for a fixture path's school and team code. A change that needs either test changed
needs the policy changed first.

Card text, cites and headings are in the store: they are the evidence itself, and the `raw/` prefix
already holds the whole file.

## How the aggregates are kept

`index.jsonl`, `failures.jsonl` and `occurrences.jsonl` are rebuilt from scratch at the end of every
run, from the per-source files of the current directory, the local manifests and the removal
suppression list. Nothing is carried forward from the previous aggregate. Each aggregate leaves out
a source the suppression list stops, and `occurrences.jsonl` also leaves out each withdrawn
disclosure.

A source's file is written as its parse finishes, and every file is written to a temporary name and
renamed into place. A run stopped part-way leaves whole per-source files that the next run skips,
and aggregates that are either the previous run's or the next one's.

## A directory this machine refuses

If the operating system will not let this user read or write `<data_dir>/parsed`, or any directory
under the caselist and version a command asked for, the command stops with exit 3 and
`STORE_ACCESS_DENIED`, names "the parsed card store" and points at `storage.data_dir`. It never
treats a directory it could not read as holding nothing: a run that did would count every source
filed there as never parsed (`v1-e31-t09`). Another caselist's unreadable directory stops nothing.

## After a removal

`caselist remove --execute` deletes, locally and in the bucket with every noncurrent version:

* every per-source file named for a removed digest, in every version directory;
* `index.jsonl`, `failures.jsonl` and `occurrences.jsonl` in every version directory of each caselist
  the removal touched, because each may hold rows derived from the removed source or disclosure.

Until the next `caselist parse` the current directory has no aggregates, and readers treat that as
"not built yet". The next run rebuilds them without the removed source, and `--publish` uploads
them again. Older version directories keep their per-source files but are not rebuilt, because
nothing writes to them again.

## Publishing

`caselist parse --publish` copies the current version directory to
`parsed/<caselist>/<version>/` in the `DEBATE_ENV` bucket through the evidence-store port. Per-source
files go first and the aggregates last, so the bucket never holds an index naming a file it does
not hold. An object already in the bucket with the same SHA-256 is skipped, so a re-run uploads
nothing. A per-source file the bucket holds with a different checksum is reported and left alone; an
aggregate is replaced. Only the current version directory is ever published.

## Reading it from a shell

The store holds no personal data, so these are safe to run and to paste:

```bash
jq -r '.outcome' ~/.debate-research/dev/parsed/hsld26/2026.09.20-docx-1/index.jsonl | sort | uniq -c
jq -r '"\(.reason) \(.source_format)"' ~/.debate-research/dev/parsed/hsld26/2026.09.20-docx-1/failures.jsonl | sort | uniq -c
jq -r '.cluster_id' ~/.debate-research/dev/parsed/hsld26/2026.09.20-docx-1/occurrences.jsonl | sort -u | wc -l
jq -r '.fingerprint_version' ~/.debate-research/dev/parsed/hsld26/2026.09.20-docx-1/occurrences.jsonl | sort | uniq -c
```

The last line prints one version and the number of rows. Two versions would mean a half-written
file, which the atomic rename rules out.

Cards with no tag, by completeness, in a `2026.10.10-docx-2` directory (about a minute for a
caselist, because it reads every card):

```bash
find ~/.debate-research/dev/parsed/hsld26/2026.10.10-docx-2/sha256 -name '*.jsonl' -print0 | xargs -0 jq -r 'select(.record == "document") | .document.cards[] | select(.tag == null) | .completeness' | sort | uniq -c
```

`caselist parse --caselist hsld26 --failures` lists the failures with their disclosure paths, read
from the manifests. Those paths name schools and team codes: that listing is for the terminal, and
its output is never pasted into a report, a document, an issue or a commit.
