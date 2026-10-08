<!-- docs-index: `debate-snapshot-text/1`: how a snapshot's normalized text and paragraph map are stored, the canonical encoding, the key check every read makes, and what `SnapshotService.load` verifies -->
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
`normalized_text_hash` still matches. Of the checks on the stored document, only the blob's own hash
notices. `v1-e03-t03` resolves paragraph IDs through this map, so an unchecked map would point a card
at different words of the same source while every text check passed. Span extraction also checks the
map at the point of use (see the guarantees below). `v1-e03-t02` found this by removing checks one at a time and
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

## How a card records what it quotes: envelope and omissions

Owner task: `v1-e03-t07-card-omissions`, implementing
[ADR-0018](../adr/0018-card-evidence-omissions.md). Implementation:
[`debate_core.domain.card`](../../packages/debate_core/src/debate_core/domain/card.py) and
[`debate_core.evidence.card_mapping`](../../packages/debate_core/src/debate_core/evidence/card_mapping.py).

A card quotes one passage of a snapshot's normalized text and records what it cut out of it.

| Field | Coordinates | Meaning |
|---|---|---|
| `evidence_start_offset`, `evidence_end_offset` | snapshot | The **envelope**: the passage quoted from, half-open |
| `omitted_ranges` | snapshot | What was removed from inside the envelope, in canonical form |
| `evidence_text` | - | The envelope with the omissions removed, the pieces joined with **no joiner** |
| `spans` (`CardSpan`) | `evidence_text` | Underlines and highlights, indexing the quotation, never the snapshot |
| `interpolations` (`Interpolation`) | `evidence_text` | Bracketed words a debater added beside the quotation, never in it (see "Editing a card") |

**Canonical form.** Omissions are sorted, non-overlapping, non-adjacent (two touching omissions are
one omission), each removes at least one character, and each lies strictly inside the envelope,
touching neither end (an omission at an edge is a smaller envelope). One card therefore has exactly
one representation, and the domain refuses any other at construction.

**The length invariant.** The envelope's length minus the total length of the omissions equals
`len(evidence_text)`, checked at construction. It compares the card with itself, not with the
snapshot, so a card whose text was changed without changing its length is still constructible and
the verifier reports it (`TEXT_MISMATCH`). A card whose text is longer or shorter than what it
claims to quote is refused before it can be stored.

**No joiner, and the ellipsis belongs to rendering.** `evidence_text` never contains an ellipsis,
bracket, space or anything else marking a cut, because a stored "..." is text no snapshot contains.
Whether a cut is shown as an ellipsis, a paragraph break or nothing is decided by the exporter (E06)
from `omitted_ranges` when it renders the card. A cut that removes only a paragraph break is the
case a renderer most needs to decide (see the `v1-e03-t03` report).

**One function does the offset arithmetic.** `place_evidence_on_card(card, markup)` takes t03's
`CardMarkup` (an `ExtractedEvidence` and snapshot-offset `EvidenceMarkupSpan`s) and sets all of the
fields above, and the snapshot's `provenance_mode`. A snapshot offset `s` inside a kept piece becomes `s - evidence_start_offset - (total
length of the omissions ending at or before s)` in `evidence_text`. A markup span never crosses a
cut, so each card span lies inside the text of one kept piece and maps back onto exactly the
snapshot characters it was made from. Two spans that touch on either side of a cut stay two spans,
each with its own purpose. A test scans every Python file in the repository and fails if this
arithmetic appears anywhere else.

The inverse, `snapshot_ranges_of(card, start, end)` in the same module, says which snapshot ranges
`evidence_text[start:end]` was cut from: one range per kept piece the range touches, never one
covering omitted text. Edits use it (next section). The same scan flags a loop over a card's
`quoted_ranges` that keeps a running count, the inverse's shape, anywhere but this module.

## Editing a card: cut, mark up, interpolate, never rewrite

Owner task: `v1-e03-t05-edit-constraints` (architecture proposal §8 step 7). Implementation:
[`debate_core.evidence.edits`](../../packages/debate_core/src/debate_core/evidence/edits.py) (what an
editor may send),
[`debate_core.evidence.edit_policy`](../../packages/debate_core/src/debate_core/evidence/edit_policy.py)
(what each edit does) and
[`CardEditService`](../../packages/debate_core/src/debate_core/application/card_edit_service.py)
(re-verify, save, log). The V2 rich-text editor calls the same service.

### What a student may send

Every offset is into `evidence_text`, the quotation as the student sees it: the kept pieces joined
with nothing, no ellipsis, no brackets. A student never sends a snapshot offset.

| Kind | Operation | Outcome |
|---|---|---|
| `delete_range` | `DeleteRange(start, end)` | At an edge of the quotation the envelope shrinks; inside it, an omission is added, or widened if it touches one, or two are joined |
| `set_markup` | `SetMarkup(spans)` | The underlines and highlights are replaced. A span across a cut becomes one span per side |
| `add_interpolation` | `AddInterpolation(anchor, text)` | Bracketed words are added beside the quotation |
| `remove_interpolation` | `RemoveInterpolation(anchor)` | The interpolation at that anchor is removed |
| `edit_tag` | `EditTag(tag)` | The tag is replaced. Needs no snapshot and never re-cuts |
| `edit_cite` | `EditCite(citation)` | The cite is replaced, likewise. A field the student changed may not arrive marked verified (`CITATION_CLAIMS_VERIFICATION`); only the citation service verifies a cite field |
| `insert_text` | `InsertText(at, text)` | Refused: `ForbiddenEvidenceEdit` |
| `replace_text` | `ReplaceText(start, end, text)` | Refused: `ForbiddenEvidenceEdit`, even when the text is empty or the same |
| `move_text` | `MoveText(start, end, to)` | Refused: `ForbiddenEvidenceEdit` |

The three forbidden kinds are refused by kind, before the card or the snapshot is looked at, and
their payload is never read or stored: not on the card, not in the edit log, not in the error, whose
message names only the kind. Reordering needs no validator of its own: a card is one envelope read
left to right (ADR-0018), so a reordered card cannot be written down. `MoveText` exists so that an
editor offering drag-and-drop gets a typed answer.

### Every quotation edit is a fresh cut; tag and cite edits are not

No edit writes `evidence_text`. Each of the four quotation edits (`delete_range`, `set_markup`,
`add_interpolation`, `remove_interpolation`) works out which snapshot ranges the card should quote and
which snapshot characters each span marks, and the card is cut again exactly as a new one is: the
extractor slices the snapshot, `CardMarkup` checks the markup, and `place_evidence_on_card` sets the
envelope, the omissions, the text and the spans. The omissions therefore come out in canonical form
without the policy arranging it. On a card with no evidence yet, a quotation edit is refused
(`CARD_HAS_NO_EVIDENCE`).

Tag and cite edits are the student's own words and freely editable. They never re-cut the quotation and
need no snapshot, so they apply to a card with no evidence yet, and to one whose stored quotation no
longer matches its snapshot. That card's evidence is saved exactly as it was, neither repaired nor
refused, and re-verification reports `TEXT_MISMATCH`.

For a deletion:

1. The deleted evidence-text range is mapped to snapshot ranges (`snapshot_ranges_of`) and taken out
   of the card's quoted ranges. Deleting everything is refused (`DELETES_ALL_EVIDENCE`): deleting the
   card is a different operation.
2. **Markup is carried across in snapshot offsets.** A span that lost all its text is dropped, and its
   purpose with it. A span that lost part keeps the rest, and its purpose. A span the deletion cuts
   through the middle becomes two spans, one per side, each with the original style and purpose.
3. **Interpolations move with the quotation.** An anchor before the deletion stays where it is, one
   after it moves back by the length deleted, and one at either edge lands on the seam. One strictly
   inside the deletion, or two that would land on one place, refuse the deletion with
   `InterpolationBlocksDeletion`: remove the interpolation first.
4. The removed text is checked for a negation (below).

**A quotation edit does what it says and nothing else.** After the fresh cut, `evidence_text` must be
the old text with exactly the deleted characters gone, or unchanged for a markup or interpolation edit. The fresh cut
makes the text verbatim; this check makes it the text the student was looking at. They differ only
when the stored quotation does not match its snapshot: a same-length alteration passes the length
invariant, so it can be stored, and a fresh cut would quietly put the snapshot's words back while the
edit "succeeded". The verifier cannot see that, because anything cut from a snapshot verifies. The
edit is refused (`QUOTATION_DOES_NOT_MATCH_SNAPSHOT`) and the card is left for the verifier to report.

### Re-verify, then save with the verdict, then log

`CardEditService.edit(card_id, edit, expected_revision=..., actor_id=...)`:

1. refuses an insertion, substitution or move by kind (`ForbiddenEvidenceEdit`);
2. refuses with `RevisionMismatch` at once if the stored revision is not `expected_revision`. The
   edit's offsets index the text at the revision the student saw, so they mean nothing against another;
3. applies the edit: a quotation edit loads the snapshot with every integrity check
   (`SnapshotService.load`) and cuts the card again; a tag or cite edit loads nothing. A refusal is a
   typed `EvidenceEditRefused`;
4. re-verifies with `EvidenceVerifier.verify_and_record`, the only code that sets a status;
5. **saves the card with that verdict, VERIFIED or not**, once, with
   `CardRepository.save(card, expected_revision=...)`, which refuses a write that raced another
   (`RevisionMismatch`) and increments the revision by exactly one;
6. appends one `CardEditEntry` to the `CardEditLog` port.

**Integrity comes from the policy, not from refusing to save.** Every quotation edit is cut again from
the snapshot and must leave exactly the text shown less what was deleted, forbidden kinds are refused,
and only the verifier sets a status, so whatever is saved says truthfully whether it verifies. A
VERIFIED card whose markup is all removed is saved UNVERIFIED with the verifier's reason
(`CARD_INCOMPLETE`), and adding markup back returns it to VERIFIED. A changed required cite field is
saved UNVERIFIED (`CITATION_UNVERIFIED`) until the citation service re-resolves it (`v1-e06-t01` ac5).
The edit result carries the status before and after and the verifier's reasons, so the caller can say
so (`v2-e14-t05` shows it as a badge).

A refused edit and an edit that loses a race leave the stored card unchanged and the log untouched.
The `RevisionMismatch` used is the one the repository already raises (`debate_core.application.errors`).

**What an edit-log entry holds:** the card id, the actor id, the edit kind, the revision before and
after, the verification status before and after, the time, and the negation flag (which omission, as
snapshot offsets). A status is not student data. No evidence text, no
deleted text, no tag, cite or interpolation, no payload, and no student data beyond the actor id. The
port has an in-memory fake (`debate_core.testing.InMemoryCardEditLog`) and no production adapter yet:
no V1 command edits a card. The card is saved before the entry is appended, so a failure between them
loses an entry rather than logging an edit that never happened; the V2 adapter writes both in one
transaction (`v2-e12-t05` ac6).

### Interpolations: beside the quotation, in brackets, unverified

`Card.interpolations` holds each interpolation as an **anchor** (an `evidence_text` offset meaning
"before this character"; `len(evidence_text)` means after the last) and its **text, stored without
brackets**, and nothing else. `Interpolation.rendered` adds the brackets and is the only code that
does. Anchors lie inside the text or at its end and strictly increase, so two interpolations never
share a place. Text holding a `[` or `]` is refused, because `x] will [y` rendered in brackets would
read as unbracketed words the source never wrote. An interpolation is never part of `evidence_text`;
the verifier and the length invariant do not read it, and a card verifies exactly as it would without
one. `card.schema.json` describes the field, and a verify manifest carries it untouched, because its
cards are domain `Card`s.

### The negation flag is a heuristic

ADR-0018 notes that the envelope makes it possible to flag an omission that deletes a negation. A
deletion whose removed text holds a negation is **accepted and flagged, never refused**. The flag is
on the edit result and in the edit-log entry, naming the omission that now holds the removed text,
or no omission when the deletion was at an edge (the envelope shrank, and nothing on the card records
the cut).

The rule ([`debate_core.evidence.negation`](../../packages/debate_core/src/debate_core/evidence/negation.py)):
a deletion removes a negation when a word it touches is one of `not`, `no`, `never`, `without`,
`neither`, `nor`, `cannot`, `none`, `nothing`, `nobody`, `nowhere`, or ends in `n't`, compared case-insensitively, with a curly apostrophe
(U+2019, which the normalizer keeps) read as a straight one. A cut that starts or ends inside a word
counts the whole word ("not" cut from "cannot" is "cannot"); one that starts or ends at a word's edge
does not reach into its neighbour (cutting " really" from "not really" is not flagged).

It is a word list, not a reading. It misses negation it has no word for ("fails to", "un-", "lack of")
and flags cuts that change nothing ("No. 5"). Hedges such as "hardly" are left out on purpose: they
weaken a claim but do not reverse it. It draws a reader's attention to a cut; it does not
judge whether the cut is fair, and VERIFIED still says nothing about that.

## Verifying a card against its snapshot

Owner task: `v1-e03-t04-verifier`. `EvidenceVerifier`
([`debate_core.application.evidence_verifier`](../../packages/debate_core/src/debate_core/application/evidence_verifier.py))
decides whether a card is finished evidence; the checks that need no I/O are in
[`debate_core.evidence.verifier`](../../packages/debate_core/src/debate_core/evidence/verifier.py).
For one card it:

1. checks the card: evidence text and offsets, `normalized_text_hash`, `normalizer_version` and at
   least one span are present, the normalizer version is one this code has, and every required
   citation field is marked verified;
2. finds the snapshot record by the card's `snapshot_id` and loads it with `SnapshotService.load`,
   so every integrity check in the previous section runs;
3. checks the card cites the article the snapshot was taken of (`article_id`) and claims the
   provenance the snapshot has (`provenance_mode`), and records the
   snapshot's `normalized_text_hash` and `normalizer_version`;
4. cuts the evidence again from the stored normalized text, selecting the card's envelope minus its
   omitted ranges, with the same extractor that cut it (`reconstruct_card_evidence`, the one place
   this happens), joins the pieces with nothing between them, and compares the result with the
   card's `evidence_text` exactly: no case folding, no Unicode or whitespace normalization, no
   similarity measure. A reconstruction that comes back cut anywhere other than where the card says
   is refused (`SPAN_OUT_OF_RANGE`); only a card that skipped validation can ask for one;
5. checks every span lies inside the reconstructed evidence.

The result is a `VerificationResult`: `VERIFIED` or `UNVERIFIED`, every reason found, and
`checks_run`, the checks that were attempted. A result cannot be constructed `VERIFIED` with a
reason or with any check missing from `checks_run`. `EvidenceVerifier` is the only code that sets
`VERIFIED`, on a result or on a card; a source scan fails if anything else does.

How failures become reason codes:

| Failure | Reason code |
|---|---|
| The card names no snapshot; the record or a blob is `NotFound` | `SNAPSHOT_MISSING` |
| `load`'s `unknown_normalizer_version` check; the card's own version unknown | `UNKNOWN_NORMALIZER_VERSION` |
| Any other `load` check; the card's hash or version is not the record's; the extractor's `SnapshotTextMismatch` | `HASH_MISMATCH` |
| Evidence text, offsets, text hash, normalizer version or spans missing from the card | `CARD_INCOMPLETE` |
| The reconstruction is not the card's `evidence_text` | `TEXT_MISMATCH`, with the first differing offset |
| The offsets do not select evidence from the text (`InvalidSelection`); a span outside the evidence | `SPAN_OUT_OF_RANGE` |
| A required citation field not marked verified | `CITATION_UNVERIFIED` |
| The card's `article_id` is not its snapshot's | `ARTICLE_MISMATCH` |
| The card's `provenance_mode` is not its snapshot's | `PROVENANCE_MISMATCH` |

One more code appears in `debate-research verify` reports and never comes from the verifier:
`CARD_INVALID`, for a manifest entry that passes the manifest's JSON Schema but is not a valid
`Card` (for example one that breaks the length invariant below, which a schema cannot express).
There is no card to compare, so nothing is checked against a snapshot; the rest of the manifest is
still verified. `VerifyManifest`
([`debate_core.application.verify_manifest`](../../packages/debate_core/src/debate_core/application/verify_manifest.py),
`v1-e03-t06`) reports it.

The first differing offset is in **evidence-text coordinates**: an index into the card's
`evidence_text`. For a card with no omissions, the snapshot offset is `evidence_start_offset` plus
it; past an omission, add the lengths of the omissions before it too. When one text is a prefix of the other, it is the shorter one's
length, and an edit inside a run of equal characters is reported where the two texts diverge.

A store that cannot be reached (`StoreError`) is not a verdict about the card and propagates, as
does any other unexpected exception: an `UNVERIFIED` card is the wrong way to report a bug.

**The finished-evidence guard re-verifies.** `EvidenceVerifier.ensure_finished(card)` raises
`UnverifiedEvidenceError` unless verifying the card now gives `VERIFIED`. It does not read the card's
`verification_status`, which anyone can construct as `VERIFIED`; every exporter and presenter calls
it before showing a card as finished. It costs one `load` per card (see the timings above).

### What VERIFIED guarantees

* The card's `evidence_text` is, character for character, the snapshot's stored normalized text from
  the envelope's start to its end with the card's omitted ranges taken out, and the omissions are
  exactly where the card says.
* That text, and the raw bytes, hash to what the snapshot record says, under the normalizer version
  the record and the card both name, which this code has.
* The card cites the article its snapshot was taken of.
* The card's `provenance_mode` is its snapshot's, so a card says `PUBLISHER_RETRIEVED` only about
  text the platform retrieved. Since `evidence-verifier-v2` (`v1-e03-t07`); a v1 result did not
  check it.
* Every span marks text inside that evidence.
* Every required citation field carries the citation service's verified flag.

### What it does not guarantee yet

* **The raw bytes are hashed, not re-extracted.** Nothing re-runs the content extractor on the raw
  bytes and compares its output with the stored text: that extractor arrives with E04, and is
  reproducible only if it is deterministic for its `extractor_version`. Until then the chain from a
  card ends at the stored normalized text. `checks_run` never lists a raw-bytes reproduction.
* **The normalizer is not re-run over the stored text.** Only `SnapshotService.create` writes
  snapshot text, and it writes normalizer output. A record and blobs written together outside
  `create` pass `load` whether or not their text is normalized; a fixed-point check would catch the
  un-normalized case and miss invented normalized text, so it is no defence against forgery, and it
  would make verification depend on the pinned Unicode database.
* **The record is trusted to be the one that was written.** Verification proves a card matches the
  record it names and the bytes match the record. A record and blobs replaced together, consistently,
  are not detectable here; the card's own `normalized_text_hash` catches a replaced record only if
  the card was not replaced with it.
* **Citation flags are read, not re-checked.** The verifier does not look metadata up again.
* **What an omission removed is not judged.** VERIFIED means the quotation is the envelope minus the
  omissions, not that the cuts are fair. Cutting "not" out of a sentence verifies. A student's
  deletion through `CardEditService` is flagged when it removes a negation (a word-list heuristic,
  see "The negation flag is a heuristic"), but the flag is advice to a reader, it is not part of
  verification, and a card cut some other way is not checked at all.
* **An omission's position is fixed only up to repeated text.** Where the characters either side of
  a cut repeat, two different cuts can leave the same text: cutting " there now" or "there now "
  from "Farmers there now pump" both leave "Farmers pump". Both cards' claims are true, and both
  verify.

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
| Span extraction re-derives the paragraph map from the text under its normalizer version and refuses a mismatch before resolving any paragraph ID, including for a `SnapshotText` that never went through `load` (`debate_core.evidence.extractor`) | `test_extract_refuses_a_paragraph_boundary_moved_to_another_valid_offset`, `test_extract_refuses_any_paragraph_map_the_text_does_not_have`; hypothesis, `test_extract_refuses_any_moved_paragraph_boundary_before_resolving_a_paragraph` |
| Storing the same source twice stores one copy of each blob, on disk | `tests/integration/test_snapshot_local.py` |
| `EvidenceVerifier` gives `VERIFIED`, with every check run, for a card cut by the extractor from an intact snapshot | `test_a_card_cut_from_an_intact_snapshot_is_verified_with_no_reasons` (`test_verifier.py`) |
| A single substituted, inserted or deleted character in a card's evidence is `TEXT_MISMATCH` at the offset where the texts first differ | `test_every_single_character_edit_is_a_text_mismatch_at_its_own_offset` |
| A missing snapshot, a tampered blob and an unknown normalizer version are reason codes, never exceptions | `test_a_card_whose_snapshot_record_does_not_exist_is_snapshot_missing`, `test_a_tampered_raw_blob_is_a_hash_mismatch`, `test_a_snapshot_under_an_unknown_normalizer_version_is_unverified_with_that_code` and neighbours |
| No fabricated, paraphrased or single-character-mutated card verifies | `test_no_fabrication_passes`, `test_no_single_character_mutation_of_any_honest_card_passes` (`test_verifier_adversarial.py`, fixtures in `tests/fixtures/verification/`) |
| The finished-evidence guard re-verifies and ignores a card's own claim to be `VERIFIED` | `test_ensure_finished_rejects_a_hand_built_card_claiming_verified_with_altered_text` |
| A card citing another article than its snapshot's is `ARTICLE_MISMATCH`, and its quotation is still checked | `test_a_card_citing_another_article_than_its_snapshots_is_an_article_mismatch`, `test_a_misattributed_card_with_altered_text_reports_both` |
| A card's provenance is its snapshot's: `place_evidence_on_card` copies it, and the verifier reports any other as `PROVENANCE_MISMATCH` (a required check, since `evidence-verifier-v2`) | `test_card_mapping_takes_provenance_from_the_snapshot_not_the_card`, `test_a_card_overstating_its_provenance_is_a_provenance_mismatch`, `test_a_card_claiming_another_provenance_than_its_snapshots_is_a_provenance_mismatch` |
| Nothing but `EvidenceVerifier` writes `VERIFIED` | `test_verified_is_set_only_by_the_evidence_verifier` |
| A card's omissions are in canonical form, and the envelope minus them is as long as `evidence_text`; every other set is refused at construction | `test_a_non_canonical_omission_set_is_refused`, `test_the_envelope_minus_the_omissions_must_be_as_long_as_the_text` (`tests/domain/test_card.py`) |
| A card made by `place_evidence_on_card` reproduces exactly from its snapshot, and no span maps back onto an omitted range | hypothesis, `test_card_mapping_reproduces_from_the_snapshot_and_no_span_lands_on_an_omission` |
| The selection-to-card offset arithmetic exists once in the repository, tests and fixtures included | `test_card_mapping_arithmetic_exists_once_in_the_whole_tree` |
| A card cut with omissions verifies; any one omission widened, narrowed, removed or added is refused at construction or is `TEXT_MISMATCH` | `test_a_card_cut_with_omissions_by_the_mapping_is_verified`, `test_no_single_omission_change_verifies_unless_it_quotes_the_same_text` (`test_verifier_omissions.py`) |
| The inverse mapping, evidence-text range to snapshot ranges, exists once too | `test_card_mapping_arithmetic_exists_once_in_the_whole_tree` (its `quoted_ranges` running-count detector), `test_snapshot_ranges_of_maps_an_evidence_range_to_the_snapshot_pieces_it_was_cut_from` |
| Any sequence of allowed edits leaves the card one revision further on per accepted edit, quoting exactly the snapshot characters, omissions, marks and anchors an independent oracle predicts, with the status it predicts; each refusal is the one the oracle predicts and changes nothing | hypothesis, `test_any_sequence_of_allowed_edits_leaves_the_canonical_card_and_status_the_oracle_predicts` (`tests/application/test_card_edit_service.py`) |
| Deletions add, widen and join omissions and shrink the envelope at an edge; spans are trimmed, split or dropped with their purposes | `test_edit_policy.py`, the "Deletions" section, hand-counted |
| Insertions, substitutions and moves are refused by kind and leave the stored card and the log unchanged; their payload appears in no error | `test_an_insertion_substitution_or_move_is_refused_by_kind_whatever_its_payload`, `test_a_forbidden_edit_raises_and_leaves_the_stored_card_and_the_log_unchanged` |
| Every accepted edit is saved with the verifier's verdict, VERIFIED or not, and the result and the entry carry the status before and after | `test_a_verified_card_that_loses_its_markup_is_saved_unverified_and_markup_brings_it_back`, `test_clearing_the_markup_is_saved_unverified_with_the_verifiers_reason`, `test_a_cite_edit_that_unverifies_a_required_field_is_saved_unverified` |
| Tag and cite edits need no snapshot and never re-cut: a card with no evidence can have them, and one that does not match its snapshot is saved untouched and UNVERIFIED (`TEXT_MISMATCH`) | `test_a_card_that_quotes_nothing_can_have_its_tag_and_cite_edited`, `test_a_tag_edit_on_a_card_that_does_not_match_its_snapshot_is_saved_untouched_and_unverified`, `test_a_quotation_edit_on_a_card_that_quotes_nothing_is_refused` |
| A quotation edit to a card that does not match its snapshot is refused, not silently repaired | `test_a_quotation_edit_to_a_card_that_does_not_match_its_snapshot_is_refused_not_repaired` |
| A stale or raced revision is refused with `RevisionMismatch`, before the edit's offsets are read | `test_a_stale_revision_is_refused_and_nothing_changes`, `test_a_stale_revision_is_reported_before_the_edits_offsets_are_read`, `test_an_edit_that_loses_a_race_is_refused_at_the_save_and_logs_nothing` |
| Interpolations are stored beside the quotation, rendered in brackets, carried by a verify manifest and ignored by verification; an anchor strictly inside a deletion refuses it | `test_an_interpolation_is_saved_beside_the_quotation_and_is_not_verified`, `test_the_verify_manifest_carries_interpolations_untouched`, `test_a_deletion_with_an_interpolation_strictly_inside_it_is_refused` |
| An edit-log entry holds the actor, kind, revisions, time and negation flag, and no evidence, tag, cite or interpolation | `test_an_accepted_edit_appends_one_entry_with_the_actor_kind_revisions_and_time`, `test_no_entry_holds_evidence_a_tag_a_cite_or_an_interpolation` |
| A dropped negation is accepted and flagged with the omission that holds it; an ordinary deletion is not flagged | `test_a_dropped_not_is_saved_and_flagged_in_the_result_and_the_entry`, `test_an_ordinary_deletion_is_saved_unflagged`, `test_removes_negation_reads_the_words_a_cut_touches` |
