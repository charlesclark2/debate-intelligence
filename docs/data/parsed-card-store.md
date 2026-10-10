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

## The skip key

A source is parsed once per **(source sha256, parser_version, profile_version)**. A run skips every
source whose key is already recorded in the current directory, so the same file disclosed in
fourteen weekly snapshots is one parse, and a second run over an unchanged store parses nothing.
A camp file and a caselist disclosure of the same bytes are parsed once in each store, because
each caselist's store stands alone: it is published under its own prefix and a removal reaches it
by caselist.

## Every record

Every line of every file is one JSON object with sorted keys, and every one carries these fields:

| Field | What it is |
|---|---|
| `schema_version` | `1` |
| `record` | `source`, `document` or `occurrence` |
| `caselist` | The caselist slug, or `openev` |
| `snapshot` | `YYYY-MM-DD` for a caselist; `<year>-<event>` for an OpenEv release |
| `source_sha256` | The source file's SHA-256 |
| `parser_version` | The parser that read it, e.g. `2026.09.20-docx-1` |
| `profile_version` | The style profile it resolved through, e.g. `2026.09.20-verbatim-1` |
| `fingerprint_version` | The card fingerprint normalization, e.g. `card-fingerprint-v1` |

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
| `FORBIDDEN_XML_CONSTRUCT` | A DTD or an entity declaration |
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
| `exact_fingerprint` | The card's exact fingerprint (`v1-e31-t04`) |
| `cluster_id` | Its near-duplicate cluster |
| `membership` | `NEAR_DUPLICATE`, `ABBREVIATED_LINK` or `UNLINKED` |
| `completeness` | `FULL`, `ABBREVIATED` or `CITE_ONLY` |

Who disclosed a card is a join, not a field: compute `sha256(f"{caselist}/{path}")` for each stored
row of the caselist's manifests and match it to `disclosure`. The digest is the same one the
removal suppression list records a withdrawn disclosure under.

**What the span means.** A weekly archive is a window of about a week's editing activity, not the
whole caselist (`docs/data/caselist-backfill-2026-09.md`), so a manifest lists a path in the weeks
a team uploaded or touched it. `last_snapshot` is the latest week that happened, not proof that the
file is still on the caselist. A path missing from some weeks between its first and latest is
still one row. In the 2026-27 weekly manifests as imported on 2026-10-09, 91 to 93% of DOCX
disclosures are listed in one week only, and none in more than five.

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
```

`caselist parse --caselist hsld26 --failures` lists the failures with their disclosure paths, read
from the manifests. Those paths name schools and team codes: that listing is for the terminal, and
its output is never pasted into a report, a document, an issue or a commit.
