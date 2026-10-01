# Session report: v1-e03-t02-hashing-provenance

| | |
|---|---|
| Task | `v1-e03-t02-hashing-provenance` — SHA-256 provenance and snapshot creation |
| Spec | [`plan_specs/v1/e03-evidence-integrity/t02-hashing-provenance.yaml`](../../plan_specs/v1/e03-evidence-integrity/t02-hashing-provenance.yaml) |
| Epic / release | `v1-e03-evidence-integrity` / `v1.0` |
| Branch | `task/v1-e03-t02-hashing-provenance` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

This task adds `SnapshotService` (`debate_core.application.snapshot_service`). `create` normalizes
the extracted text with the t01 normalizer and hashes the raw bytes and the normalized text. It
stores two blobs through the `SnapshotStore` port: the raw bytes exactly as received, and a
canonical JSON document holding the normalized text, its normalizer version and its paragraph map.
It returns the `SourceSnapshot`. `load` reads both blobs back, re-hashes them itself and raises
`SnapshotIntegrityError` naming the check that failed. The hash helpers are in
`debate_core.evidence.hashing`, and the stored form of the normalized text is in
`debate_core.evidence.snapshot_text`. Every criterion passed and the Goal is `Succeeded`.

**What the PM should look at first:**

* **The re-hash on load is always on.** Measured cost is under Decisions §1.
* **The deep property run found two decorative properties in my own tests.** They passed 50,000
  examples each with the check they were written for removed. One of them led to a real finding
  about the design: the paragraph map is protected only by the normalized blob's own hash. See
  "Breaking the implementation on purpose" below.
* **I extended the `SnapshotStore` contract suite** in `debate_core.testing`, outside this task's
  package list, as the PM context asked (Deviations).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `hashing` — SHA-256 helpers | Done | `sha256_bytes` refuses anything but `bytes`. `sha256_text` hashes strict UTF-8 with no BOM. Lowercase hex. |
| `snapshot-service` — `SnapshotService.create` | Done | Everything that can be refused is refused before a blob is written. The recorded `normalizer_version` is the one `normalize` returned. |
| `integrity-load` — integrity-checked loading | Done | Seven named checks. The service hashes the bytes itself rather than trusting the store's read check. |
| `local-integration` — integration with the local blob store | Done | Runs against `FsSnapshotStore` in `tmp_path`: counts files, checks inode and mtime are unchanged, rewrites, swaps and deletes blob files. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — snapshot records raw sha256, normalized_text_hash, normalizer_version, extractor_version, retrieved_at (UTC), provenance_mode and both blob keys | PASS | `test_create_records_both_hashes_both_versions_the_provenance_and_both_blob_keys` compares the whole `model_dump()` to a hand-written dict. The hashes are SHA-256 of byte strings written out by hand. `test_create_records_retrieved_at_in_utc` gives `14:05+02:00` and gets `12:05Z`. |
| ac2 — loading re-hashes both blobs and raises `SnapshotIntegrityError` on any mismatch | PASS | `uv run pytest packages/debate_core/tests/application/test_snapshot_service.py -k integrity` → `23 passed`. Includes a store that never checks what it serves, so each refusal comes from the service. `test_snapshot_local.py` covers the same on real files. |
| ac3 — identical inputs give identical hashes and one stored copy of each blob | PASS | `test_create_twice_from_identical_inputs_yields_identical_hashes_and_one_copy_of_each_blob` (exactly two keys stored). Property `test_create_from_identical_inputs_always_…` (50,000 examples). On disk, `test_creating_the_same_snapshot_twice_writes_two_files_once_and_never_rewrites_them`: two files, inode and mtime unchanged. The contract's `test_identical_bytes_put_twice_occupy_one_stored_copy` passes for all three stores. |
| ac4 — hash helpers match known SHA-256 vectors and hash text as UTF-8 without a BOM | PASS | `uv run pytest packages/debate_core/tests/evidence/test_hashing.py` → `34 passed`. Uses the FIPS 180-2 vectors (empty, `abc`, 448-bit, 896-bit, one million `a`). UTF-8 byte strings are written by hand, and the hash is checked to differ from the `utf-8-sig`, UTF-16 and Latin-1 encodings. |
| `hashing` node: hash vector tests pass | PASS | `uv run pytest packages/debate_core/tests/evidence/test_hashing.py` → `34 passed in 5.61s`, `hashing.py` 100% covered |
| `snapshot-service` node: snapshot creation tests pass | PASS | `uv run pytest packages/debate_core/tests/application/test_snapshot_service.py -k create` → `15 passed in 4.66s` |
| `integrity-load` node: tamper-detection tests pass | PASS | `uv run pytest packages/debate_core/tests/application/test_snapshot_service.py -k integrity` → `23 passed in 4.79s` |
| `local-integration` node: local integration tests pass | PASS | `uv run pytest packages/debate_core/tests/integration/test_snapshot_local.py` → `8 passed in 4.19s` |
| `local-integration` node: import boundaries hold | PASS | `uv run lint-imports` → `Contracts: 10 kept, 0 broken.` No `ignore_imports` entry added. The "(6 ignored imports)" it prints are matches of the existing `debate_cli.container -> debate_core.integrations.**` composition-root entry, unchanged. |

Wider checks run: `uv run pytest` (whole repo, default markers) → `3218 passed, 1 skipped in
46.44s`. The skip is the pre-existing `tests/evals/parser/test_parser_eval.py:279`, which is waiting
on human-corrected files. `uv run pyright` → `0 errors`. `uv run ruff check .` and
`ruff format --check .` → clean. `snapshot_service.py`, `snapshot_text.py` and `hashing.py` are each
100% line and branch covered.

### Breaking the implementation on purpose

Each row is one deliberate change, applied alone, with the named tests run and the file restored
afterwards. The runner script is described under Decisions §6.

| Break | Result | Caught by |
|---|---|---|
| Text hashed as UTF-8 with a BOM (`utf-8-sig`) | caught | `test_sha256_text_of_ascii_text_matches_the_published_vectors[empty]` |
| Text hashed as UTF-16 | caught | same |
| Uppercase hex digest | caught | `test_sha256_bytes_matches_the_published_vectors[empty]` |
| SHA-1 instead of SHA-256 | caught | same |
| Lone surrogate hashed as U+FFFD (`errors="replace"`) | caught | `test_sha256_text_refuses_text_with_a_lone_surrogate` |
| A `str` passed as raw bytes is encoded instead of refused | caught | `test_sha256_bytes_refuses_anything_but_bytes[str]` |
| Text NFC-normalized inside the hash helper | caught | `test_sha256_text_hashes_the_utf8_encoding[combining-mark-not-composed]` |
| Leading U+FEFF stripped before hashing | caught | `test_a_leading_feff_in_the_text_is_hashed_as_content_and_not_stripped` |
| `normalizer_version` recorded from the `NORMALIZER_VERSION` constant | caught | `test_create_records_the_normalizer_version_that_normalize_reports` (see Decisions §4) |
| `normalized_text_hash` taken from the JSON blob / from the un-normalized text | caught (both) | `test_create_records_both_hashes_…` |
| Raw bytes decoded and re-encoded before hashing | caught | property `test_create_from_identical_inputs_always_…` |
| Normalized text stored as plain UTF-8 rather than the document | caught | `test_create_records_both_hashes_…` |
| `retrieved_at` from the clock; `byte_size` from the text | caught (both) | `test_create_records_both_hashes_…` |
| `create` skips the store-key check | caught | `test_create_refuses_a_store_that_breaks_content_addressing_…[raw]` |
| `load` skips re-hashing the raw blob | caught | `test_integrity_altered_bytes_…[raw-bit-flip]` |
| `load` compares raw bytes to the key only, not to `sha256` | caught | `test_integrity_a_record_pointing_at_another_snapshots_raw_blob_is_refused` |
| `load` skips `byte_size` / known-version / document-version / text-hash checks | caught (each) | the matching `test_integrity_…` case |
| `load` lets the store's `BlobIntegrityError` escape untranslated | caught | `test_integrity_a_blob_the_store_finds_damaged_…[raw]` |
| `load` skips re-hashing the normalized blob | caught | first by `test_integrity_altered_bytes_…[normalized-word-changed]`, which only noticed because it asserts the check *name*: the edit was still refused, by the text hash. Now also caught by refusal itself in `test_integrity_a_paragraph_map_altered_into_another_valid_document_is_refused` (below). |
| `decode` skips the canonical check / paragraph bounds / accepts booleans as offsets | caught (each) | `test_snapshot_text.py` structural and respelling cases |
| `encode` escapes non-ASCII / adds whitespace | caught (both) | the hand-written document tests |
| `encode` with `sort_keys=False` | **survived** | An equivalent mutant: the dict literals are already written in sorted key order, so the output does not change. Reordering the literal *and* turning off sorting is caught by `test_a_normalizer_result_encodes_to_the_hand_written_document`. |
| Filesystem store copies instead of renaming, leaving the temp file as a second copy | caught | contract `test_identical_bytes_put_twice_occupy_one_stored_copy` (new) |
| In-memory store keeps a second copy on a repeat put | caught | same |
| In-memory store only notices emptied blobs | caught | contract `test_a_blob_whose_bytes_no_longer_match_its_key_is_refused[byte-appended]` (new damage kinds) |

### What the deep property run found in my tests

Property tests read `SNAPSHOT_PROPERTY_EXAMPLES` (default 200). I ran the five properties at 50,000
examples each (`SNAPSHOT_PROPERTY_EXAMPLES=50000 uv run pytest … -n 5`). Result: `5 passed in
57.98s`. That run found no bug, and a pass is only evidence if the property can fail for the reason
it was written. So I removed the check each property guards and ran that property alone. Two of the
five still passed:

1. **`test_no_single_byte_change_to_a_document_decodes_to_the_same_content`** still passed with the
   canonical-encoding check removed. No one-byte substitution turns a canonical document into
   another spelling of the same content; that needs inserted whitespace, reordered keys or a new
   escape. So the property never exercised that check. A second break showed it also passes with
   only the format-identifier check removed, because the canonical check refuses a changed
   identifier on its own. It fails only when both are gone. I kept it, and rewrote its docstring to
   say exactly that; my first rewrite of the docstring wrongly said it exercised the structural
   checks. I added `test_every_other_json_spelling_of_a_document_is_refused`, which re-spells each
   document every way `json.dumps` allows. It fails with the canonical check removed.
2. **`test_integrity_any_single_byte_change_to_either_blob_is_refused`** still passed with the
   service's re-hash of the normalized blob removed. Almost any random byte change is caught by
   another check. The one edit that is not is a paragraph offset moved to another valid value: the
   document stays valid and canonical, names the same version and holds the same text, so the text
   hash still matches. **So the paragraph map is protected only by the normalized blob's own hash.**
   Span extraction (`v1-e03-t03`) resolves paragraph IDs through that map, so a moved boundary would
   quietly move a card's evidence. I added an example test for exactly that edit and widened the
   property (renamed `test_integrity_any_change_to_either_blob_is_refused`) to make it half the
   time. Both now fail with that re-hash removed.

After the fixes, all six properties at 50,000 examples each: `6 passed in 45.74s`. The other three
(the document round trip, the load round trip and identical-inputs determinism) were each caught
when their check was broken.

Earlier, while writing the tests, I caught one test bug of my own before the first run. The
"CRLF to LF" damage case, `data[:-1] + b"\n"`, gave back the same bytes it started from. I also
found that my `\u…` escapes had been written into the test sources as the literal invisible
characters, so `"café"` read as `café`, identical to the line above it. They are escapes again.

## Files changed

* `packages/debate_core/src/debate_core/evidence/hashing.py`: new. `sha256_bytes` and `sha256_text`.
* `packages/debate_core/src/debate_core/evidence/snapshot_text.py`: new. The stored form of normalized
  text, `debate-snapshot-text/1`: canonical encoding and a strict decoder.
* `packages/debate_core/src/debate_core/application/snapshot_service.py`: new. `SnapshotService` and
  `LoadedSnapshot`.
* `packages/debate_core/src/debate_core/application/errors.py`, `application/__init__.py`: adds
  `SnapshotIntegrityError` and the `SnapshotIntegrityCheck` enum to the port error hierarchy.
* `packages/debate_core/src/debate_core/testing/contracts/` (`snapshot_store.py`, `harness.py`,
  `__init__.py`, `README.md`) and `testing/fakes.py`: the contract extension (Deviations). It adds
  the optional `count_stored_blobs` fixture and copy-count test, five kinds of damage for the
  corruption test, and `InMemorySnapshotStore.stored_keys()` (test-only, like `corrupt`).
* `packages/debate_core/tests/contracts/test_snapshot_store_contract.py`,
  `tests/integrations/s3/test_s3_snapshot_store.py`: the in-memory, filesystem and S3 (moto)
  bindings supply the copy counter.
* `packages/debate_core/tests/evidence/test_hashing.py`, `test_snapshot_text.py`,
  `tests/application/test_snapshot_service.py`, `test_errors.py`,
  `tests/integration/test_snapshot_local.py`: tests. No fixtures were added. All text is invented
  in the test files.
* `plan_specs/…/t02-hashing-provenance.yaml`: phase only.

## Deviations from the spec

* **Files outside `constraints.packages`** (`debate_core.evidence`, `debate_core.application`). The
  `SnapshotStore` contract suite and its bindings live in `debate_core.testing` and the tests of
  `debate_core.integrations`. The PM context asked for ac2/ac3 gaps to be closed in the contract
  so every store inherits them. The gap was real: the existing "putting identical bytes twice
  stores one blob" test checked only that the keys matched. A store writing a second copy passed
  it. The mutation table shows the new test catching that for the filesystem and in-memory stores.
* **Not wired into `debate_cli.container`.** No command or service uses `SnapshotService` yet, and
  `debate_cli` is outside the package list. The service takes the port, so the container is the
  only place an adapter would be chosen when E04 wires it (Follow-up work).

## Decisions and assumptions

1. **Integrity on load is always on, with no switch.** I measured it with the filesystem store,
   synthetic blobs and a warm page cache on an Apple M3 Pro, Python 3.12.7, median of 10–200 runs
   (script in the session scratchpad, not committed):

   | Case | Raw blob | Normalized document | Store reads alone | `load` | Added by `load`'s checks | SHA-256 of raw | Strict decode of document |
   |---|---|---|---|---|---|---|---|
   | News article page | 0.15 MB | 0.018 MB | 0.13 ms | 0.31 ms | 0.17 ms | 0.05 ms | 0.10 ms |
   | Long report PDF | 5 MB | 0.35 MB | 2.81 ms | 7.66 ms | 4.85 ms | 1.82 ms | 2.52 ms |
   | Very large PDF | 50 MB | 2.35 MB | 67.75 ms | 166.12 ms | 98.37 ms | 27.42 ms | 22.43 ms |

   Load costs about 2.3–2.7× the bare reads. The service's own re-hash of the raw bytes duplicates
   the store's, and that plus the strict decode account for about half of the added time at 50 MB.
   I have not explained the rest. On a typical source it is a third of a millisecond. I kept it
   unconditional because a check callers routinely turn off protects nothing. The duplicate raw
   hash is deliberate: a store whose read check is broken (the `TrustingSnapshotStore` tests) is
   still caught. A caller checking many cards against one source should load once and reuse the
   `LoadedSnapshot`, not skip the check.
2. **`create` stores blobs and returns the record; it does not save the record.** The spec names
   only the `SnapshotStore` port. The caller that owns the article (E04's article service) calls
   `ArticleRepository.save_snapshot`, and `load` takes a `SourceSnapshot` rather than an id. A
   repeat retrieval is a new record with a new `snapshot_id`, but no new blobs.
3. **The normalized blob is canonical JSON and does not include the offset map.** The offset map
   relates normalized offsets to the extractor's output, which is not stored, so it could not be
   used. Including it would also make the blob depend on extractor whitespace: a re-served page
   with different markup but the same text would stop sharing its normalized blob (tested). This
   answers the persistence question t01's report left for this task. The decoder accepts only the
   canonical bytes, because a second accepted spelling would be a second blob key for one text.
4. **The recorded `normalizer_version` comes from `normalize`'s result.** The service passes
   `NORMALIZER_VERSION` in to *ask* for the current rules and records `normalized.normalizer_version`.
   While v1 is the only version, the constant and the result cannot be told apart by output, so
   the test replaces `normalize` (monkeypatch) with one that reports another version. It is the only
   monkeypatch in these tests. The ac3 caveat the PM asked for is a comment where
   `normalized_text_hash` is computed. The hash is a function of the text, the normalizer version
   and the Unicode database together, and it is reproducible only because `normalize` refuses any
   database but the pinned 15.0.0.
5. **The service relies on the port's content addressing.** `BlobKey` is defined as the SHA-256 of
   the bytes, and the contract asserts it. `create` refuses a store that files a blob under any
   other key, and `load` checks raw bytes against both `sha256` and `raw_blob_key`. The port
   docstring says `raw_blob_key` is ordinary text "so a future store with a different key scheme
   does not force an entity migration". Such a store would need these two checks changed, but no
   entity migration.
6. **Error shape.** `SnapshotIntegrityError` carries `snapshot_id`, `check`, `expected` and `actual`,
   so t04 can map `check` to reason codes. An unknown normalizer version is one of the checks, and
   it is refused before anything is read. A blob that is simply missing stays `NotFound`, because
   t04 distinguishes `SNAPSHOT_MISSING` from `HASH_MISMATCH`. That is how I read "any mismatch" in
   ac2. The mutation runner (`mutate.py` in the scratchpad) applies one exact-string replacement,
   runs the named tests with `-x`, and always restores the file's original bytes.
7. **Location.** `snapshot_service.py` sits at `debate_core/application/`, the path the spec's node
   `outputs` names, not under `application/services/`.

## Operator follow-ups

None. Every command in this session finished in under a minute. The longest was the full default
suite at 47 s.

## Follow-up work

* **`v1-e03-t04-verifier`: "re-normalizes under the card's recorded normalizer_version".** The
  snapshot stores the raw bytes and the normalized text, not the extractor's output. Re-normalizing
  can therefore only mean re-running the normalizer on the normalized text (an idempotence check),
  or re-running the extractor on the raw bytes, which is only reproducible if the extractor is
  deterministic for its `extractor_version`. If t04 needs the extracted text, storing it is a spec
  change to this task's blob layout, not something t04 can add alone.
* **`v1-e03-t04-verifier`: map `SnapshotIntegrityCheck` to reason codes.** Suggested mapping:
  `UNKNOWN_NORMALIZER_VERSION` gets its own code. The hash, size, malformed and version-mismatch
  checks map to `HASH_MISMATCH`, and `NotFound` maps to `SNAPSHOT_MISSING`.
* **`v1-e03-t03-span-extraction`:** `LoadedSnapshot.normalized` (`SnapshotText`) has
  `paragraph()` and `paragraph_text()`, matching `NormalizedText`. The paragraph map is trustworthy
  only from a `load`ed snapshot, never from a blob read directly (see the deep-run finding above).
* **E04 article service (`v1-e04-t05`):** add `SnapshotService` to `debate_cli.container`
  (`blobs=FsSnapshotStore(settings.storage.data_dir)`, a system clock and an id generator), and save
  the returned record with `ArticleRepository.save_snapshot`.
* **Docs (PM decision):** the `debate-snapshot-text/1` format is stored data that later code
  depends on. Its specification is currently the module docstring of `snapshot_text.py`. Under the
  working agreements' table it would sit in `docs/evidence/` beside `normalization.md`. I did not
  add the page, because `docs/` is outside this task's packages.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
