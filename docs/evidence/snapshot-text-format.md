# Snapshot text format: `debate-snapshot-text/1`

Owner task: `v1-e03-t02-hashing-provenance`. Implementation:
[`debate_core.evidence.snapshot_text`](../../packages/debate_core/src/debate_core/evidence/snapshot_text.py),
read and written by
[`SnapshotService`](../../packages/debate_core/src/debate_core/application/snapshot_service.py).
Architecture: proposal §7 (`SourceSnapshot`) and §8 steps 1-2,
[ADR-0006](../adr/0006-exact-source-evidence-verification.md).

This page is the contract for how a snapshot's normalized text is stored. Span extraction
(`v1-e03-t03`) resolves paragraph IDs through what is stored here, and the verifier (`v1-e03-t04`)
compares a card's quotation against it. A document written today must read back byte for byte, with
the same key, for as long as a card cut from it exists.

## What a snapshot stores

Every `SourceSnapshot` points at two blobs in the `SnapshotStore`, each filed under the SHA-256 of
its own bytes:

| Blob | Contents | Record fields that bind it |
|---|---|---|
| Raw | The response body exactly as received: nothing decoded, trimmed or re-encoded | `raw_blob_key`, `sha256`, `byte_size` |
| Normalized | One `debate-snapshot-text/1` document, described below | `normalized_blob_key`, `normalized_text_hash`, `normalizer_version` |

`sha256` is the SHA-256 of the raw bytes. `normalized_text_hash` is the SHA-256 of the normalized
text encoded as UTF-8 without a byte-order mark. Neither is the key of the normalized blob, which is
the SHA-256 of the whole document.

## The document

A JSON object with exactly four keys:

| Key | Type | Meaning |
|---|---|---|
| `format` | string | Always `debate-snapshot-text/1` |
| `normalizer_version` | non-empty string | The version `normalize` reported producing the text with, e.g. `evidence-normalizer-v1` ([normalization.md](normalization.md)) |
| `paragraphs` | array | One object per paragraph, in order: `{"end": int, "id": string, "start": int}` |
| `text` | string | The normalized text |

Each paragraph is `text[start:end]`, with offsets in code points as in the normalizer's own
paragraphs. Paragraphs are in order, do not overlap, lie inside the text and have unique, non-empty
IDs. Offsets are integers, never booleans or floats.

For the extracted text `"Arctic methane is accelerating.\r\n\r\nOcean heat  reached a new high.\n"`,
the stored document is these bytes, shown here wrapped but stored as one line:

```json
{"format":"debate-snapshot-text/1","normalizer_version":"evidence-normalizer-v1",
"paragraphs":[{"end":31,"id":"p0001","start":0},{"end":63,"id":"p0002","start":33}],
"text":"Arctic methane is accelerating.\n\nOcean heat reached a new high."}
```

## The encoding is canonical

There is exactly one byte sequence for each document:

* UTF-8, no byte-order mark;
* keys sorted, in the object and in each paragraph;
* no whitespace between tokens (separators `,` and `:`);
* non-ASCII characters written as themselves, not as `\u` escapes; JSON's mandatory escapes
  (`\"`, `\\`, control characters) are the only escapes;
* no trailing newline.

**Why.** The blob key is the SHA-256 of these bytes. A canonical encoding makes the key a function of
the normalized text and its version alone, so equal text always lands under one key, and storing an
unchanged source twice stores one normalized blob (`v1-e03-t02` ac3). It holds even when the raw
bytes differ: a page re-served with different markup around the same text shares its normalized blob
with the first retrieval.

**The reader enforces it.** A document is accepted only if it is exactly the canonical encoding of
what it decodes to. Reordered keys, added whitespace, a `A` where `A` belongs, a duplicated key,
a trailing newline: each is refused as malformed. A reader that accepted two spellings would let one
normalized text sit under two keys and would hide which one a snapshot recorded.

## Why the offset map is not stored

The normalizer also returns an offset map between the extractor's output and the normalized text.
It is deliberately left out:

* It relates normalized offsets to offsets in the **extractor's output**, which no snapshot stores, so
  nothing could use it.
* It differs whenever the extractor's whitespace differs, even when the normalized text is the same.
  Storing it would split one normalized text across many blobs and break the deduplication above.

If a later task needs offsets into the extractor's output, it needs the extractor's output too.
That is a change to this format and to the snapshot's blobs, made under a new format identifier.

## Reading a document: the key comes first

`decode_snapshot_text(data, *, expected_key)` is the only way from bytes to a `SnapshotText`.
`expected_key` is required, keyword-only, and has no default. It is the key the blob is recorded
under, a snapshot's `normalized_blob_key`, and it must come from that record, never from `data`.
The bytes are hashed and compared to it **before anything is parsed**. A mismatch raises
`SnapshotTextKeyMismatch`, and a well-keyed document that breaks any rule above raises
`MalformedSnapshotText`.

**Why the key is not optional.** A paragraph boundary moved to another valid offset leaves a document
that is still valid, still canonical, under the same version, with the same text, so
`normalized_text_hash` still matches. Only the blob's own hash notices. `v1-e03-t03` resolves
paragraph IDs through this map, so an unchecked map would point a card at different words of the same
source while every text check passed. `v1-e03-t02` found this by removing checks one at a time and
watching which tests still passed.

A test fails if any callable in `debate_core` returns a `SnapshotText` from bytes or a string
without a required `expected_key` (`test_nothing_in_debate_core_turns_serialized_text_into_a_snapshot_text_without_a_key`).
It cannot see code that parses the JSON itself and calls the `SnapshotText` constructor directly.
That would be deliberate, and review has to catch it.

Code outside the evidence layer should not decode at all. It should call `SnapshotService.load`,
which returns the checked text inside a `LoadedSnapshot`.

## Loading a snapshot

`SnapshotService.load(snapshot)` reads both blobs and checks them against the record. The first
failure raises `SnapshotIntegrityError`, whose `check` names it:

| `check` | Meaning |
|---|---|
| `unknown_normalizer_version` | The record names a normalizer version this installation does not have; refused before anything is read |
| `raw_bytes_hash` | The raw bytes do not hash to `sha256` or to `raw_blob_key` |
| `raw_byte_size` | The raw blob is not `byte_size` long |
| `normalized_blob_hash` | The document does not hash to `normalized_blob_key` |
| `normalized_blob_malformed` | The document breaks a rule on this page |
| `normalizer_version_mismatch` | The document's `normalizer_version` is not the record's |
| `normalized_text_hash` | The text does not hash to `normalized_text_hash` |

A blob that is simply missing raises `NotFound`, not `SnapshotIntegrityError`, because a missing
snapshot and a damaged one are different findings. The service computes every hash itself rather
than trusting the store's read check, so a store that serves altered bytes without noticing is
still caught.

### The check is always on

There is no switch to skip it. A check that callers can turn off is one they will turn off on the
hot path, which is the path that matters. Measured against the filesystem store on an Apple M3 Pro
(`v1-e03-t02`, synthetic blobs, warm page cache):

| Source | Raw blob | `load` | Of which the integrity checks |
|---|---|---|---|
| Web article | 0.15 MB | 0.31 ms | 0.17 ms |
| Report PDF | 5 MB | 7.7 ms | 4.9 ms |
| Very large PDF | 50 MB | 166 ms | 98 ms |

**A caller checking many cards against one source loads the snapshot once and reuses the
`LoadedSnapshot`.** It does not skip the check, and it does not load once per card.

## Changing the format

A released format is never edited. A change to the keys, the encoding or what is stored gets a new
identifier (`debate-snapshot-text/2`) and its own section here. Documents written under `/1` keep
their keys and must stay readable, because cards were cut from them.

## Guarantees, and the tests that hold them

| Guarantee | Test |
|---|---|
| The example above encodes to exactly those bytes | `test_a_normalizer_result_encodes_to_the_hand_written_document` |
| Every normalizer result round-trips through its document | hypothesis, `test_snapshot_text.py` |
| Every other JSON spelling of a document is refused | hypothesis, `test_every_other_json_spelling_of_a_document_is_refused` |
| Two extractions that differ only in whitespace give one document | `test_the_offset_map_is_not_stored_so_extractor_whitespace_does_not_change_the_document` |
| Bytes are refused on a key mismatch before they are parsed | `test_bytes_that_do_not_hash_to_their_key_are_refused_before_they_are_parsed` |
| A moved paragraph boundary is refused under the original key | `test_a_paragraph_boundary_moved_to_another_valid_offset_is_refused_under_the_original_key`, and through `load` in `test_snapshot_service.py` |
| No unkeyed path from bytes to a `SnapshotText` exists in `debate_core` | `test_nothing_in_debate_core_turns_serialized_text_into_a_snapshot_text_without_a_key` |
| Any change to either blob, including a valid re-written paragraph map, fails `load` | hypothesis, `test_integrity_any_change_to_either_blob_is_refused` |
| Storing the same source twice stores one copy of each blob, on disk | `tests/integration/test_snapshot_local.py` |
