# Session report: v1-e06-t12-pasted-copy-cite-stated-by-the-user

| | |
|---|---|
| Task | `v1-e06-t12-pasted-copy-cite-stated-by-the-user` — A pasted copy's cite fields can be stated when it is stored, so a card cut from it has a usable cite |
| Spec | [`plan_specs/v1/e06-card-cutting/t12-pasted-copy-cite-stated-by-the-user.yaml`](../../plan_specs/v1/e06-card-cutting/t12-pasted-copy-cite-stated-by-the-user.yaml) |
| Epic / release | `v1-e06-card-cutting` / `v1.3` |
| Branch | `task/v1-e06-t12-pasted-copy-cite-stated-by-the-user` |
| Session status | COMPLETE |

## Summary

`fetch --paste` now takes `--title`, `--author` (once per author, in order), `--date` (`YYYY-MM-DD`)
and `--publication`. The fields are stored on the pasted copy's snapshot as `stated_citation`, each
one `heuristic` and unverified. `cut URL --from-paste` cites the card with them, so a pasted copy's
card now has an author, a title, a publication and a date. The card stays UNVERIFIED with
`CITATION_UNVERIFIED` alone. The cite marks each stated field `[… unverified]`, the marker the
renderer already uses, and `verify` finds the same one reason. A copy stored without the options cuts
exactly as before: t08's tests pass unchanged, and a snapshot stated nothing for is stored byte for
byte as before.

**Look first at Deviations 1 and 2.** Deviation 1 is the domain field your ruling added to the
packages. Deviation 2 is fetch's published result schema, which gains one optional key.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `pasted-copy-cite-stated-by-the-user` (Stated cite) | Done; its criterion passes | Spec amended with the PM's rulings (`4a8e36c`), red run against a skeleton (`1cbb25a`), implementation (`b301096`), CLI README (`330a242`) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: `fetch --paste` stores stated cite fields as user-stated | PASS | The stored snapshot's `stated_citation` holds the authors in order, the title, the publication and the date, each `heuristic`, `verified` false, the raw text kept. Credentials, URL and accessed date are absent (`test_paste_with_cite_options_stores_each_field_user_stated_and_unverified`). `--json` reports them as the snapshot's `stated_cite`, and the table as `Stated …` rows, with `not stated` for the rest. The domain refuses a stated cite on any other provenance, a verified field, a field a user does not state, and a cite that states nothing (`test_article.py`, 11 cases). |
| ac1: a card cut from that copy shows them in its cite | PASS | The cite line in the .docx is, hand-written: `Okonkwo-Lindqvist et al. 26 [Mara Okonkwo-Lindqvist and Teodor Brannigan; "Mammoth Money and the Elephants Left Waiting"; The Synthetic Science Weekly; September 15, 2026; <url>; accessed October 26, 2026; user-supplied text]`, then t08's six `[… unverified]` marks (`test_a_card_cut_from_a_paste_with_stated_fields_shows_them_in_its_cite_and_unverified_for_it_alone`). The stated date (the 15th) replaces the URL path's 14th. The stored card and the embedded manifest record each stated field `heuristic`, and no field is verified. |
| ac1: …and stays UNVERIFIED with CITATION_UNVERIFIED alone | PASS | `cut` exits 4 with one reason, `(CITATION_UNVERIFIED, CITATION_UNVERIFIED, [authors, title, publication, published_at, canonical_url])`. `verify out.docx` exits 1 with `reason_codes == ["CITATION_UNVERIFIED"]`. |
| ac1: a copy stored without them cuts as today | PASS | t08's tests are unchanged: the diff of `test_cut_command.py` and `test_cut_smoke.py` adds lines only, and `test_fetch_command.py` changes one import. All pass, the pinned `PASTED_FULL_CITE` and the `source` object included. A paste without options writes no `stated_cite` key and stores `stated_citation` as absent (`test_paste_without_cite_options_stores_and_reports_no_stated_cite`). Existing rows are byte-identical (Decision 5). |
| ac1: by tests shown failing first | PASS | Red against a skeleton that stores and refuses nothing (`1cbb25a`): **68 failed, 5 passed**, below. On a stamped, installed build of the start commit `1865cf1`, the new smoke check fails with `No such option: --title` (exit 2): 1 failed, 6 passed. |
| ac1: an installed-build smoke check | PASS | `tests/smoke/test_cut_smoke.py::test_cut_from_paste_cites_the_fields_stated_at_fetch_paste_unverified_offline`: the build's own `fetch --paste` with the four options, then `cut --from-paste`, then `verify`. On an offline stamped, installed build of `330a242` (wheels, `DEBATE_SMOKE_BIN`): cut and fetch smoke, **11 passed in 7.84s**. On the checkout's console script: 11 passed in 6.57s. |
| Node: `uv run pytest packages/debate_cli/tests/test_cut_command.py packages/debate_cli/tests/test_fetch_command.py -k paste` | PASS | **57 passed in 3.65s**, run as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest <the two files> -k paste`. |
| Forbidden, never happens: a user-stated field recorded or reported as verified | PASS | Each field is built `heuristic`, and the domain refuses a verified heuristic. The snapshot validator refuses a verified stated field of any source. Mutants 1, 2 and 9 below. |
| Forbidden, never happens: a card from a pasted copy reported VERIFIED | PASS | Mutant 3 (the verifier skipping a user-supplied card's cite) fails 12 tests, t08's among them. |
| Forbidden, never happens: network or live model calls in tests | PASS | The CLI tests use t08's replay transport and fixture router, whose fixtures assert no unrecorded request. The smoke check runs under the network guard. |

### Red run

The skeleton accepted `--title`, `--author`, `--date` and `--publication` and ignored them. It added
`SourceSnapshot.stated_citation` with no validator and no exclusion, and a `stated_citation()` that
stated nothing. Command:
`.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest <the six test files> -k "stated or cite_option or stored_again or yyyy or byte_for_byte or changed_user_text or nothing_stated or empty_stated" -p no:randomly`
→ **68 failed, 5 passed in 6.94s**. Grouped by reason:

* a usage error expected and exit 0 given: a cite option without `--paste`, an empty value, a bad date (21);
* no stated field anywhere: none stored on the snapshot, none in the cut cite, the report or the table (12);
* `DID NOT RAISE InvalidStatedCite` (14) and `DID NOT RAISE ValidationError` (11);
* the report did not fit `fetch_result.v1.json`, the skeleton's key being unpublished (6);
* the snapshot document gained `"stated_citation":null`, so not byte-identical (4).

The five passes are behaviour the skeleton already had: the field round-trips through JSON, nothing
stated gives `None`, identical text with the same (absent) cite reuses, changed text makes a new copy
with none, and `verify` already finds a pasted copy's card UNVERIFIED for `CITATION_UNVERIFIED` alone.

### Mutants

21 mutants, each against the six covering test files (`domain/test_article.py`,
`test_citation_service.py`, `test_article_service.py`, `test_fetch_command.py`, `test_cut_command.py`,
`tests/smoke/test_cut_smoke.py`), and each restored from HEAD afterwards. None of these files uses
Hypothesis; each run set a fresh `HYPOTHESIS_STORAGE_DIRECTORY` anyway. **All 21 were caught** on an
assertion. Mutant 1 is also stopped by the domain guard, which refuses to store it: `fetch` exits with
`INTERNAL_ERROR`. The builder's own test catches it by assertion.

| Mutant | Result |
|---|---|
| PM: a stated field marked verified (the builder writes `byline`, `verified` true) | Caught, 13 failed |
| PM: stated fields marked verified at cut time (in `resolve`, past the snapshot's guard) | Caught, 6 failed |
| PM: the card reported VERIFIED (the verifier skips a user-supplied card's cite) | Caught, 12 failed |
| PM: stated fields dropped at cut time | Caught, 7 failed |
| PM: an author list reordered, in the builder | Caught, 8 failed |
| PM: an author list reordered, in fetch's report | Caught, 3 failed (the smoke check among them) |
| PM: a cite option accepted without `--paste` | Caught, 4 failed |
| Domain: a stated cite allowed on any provenance | Caught, 3 failed |
| Domain: a verified stated field allowed | Caught, 4 failed |
| Domain: fields a user does not state allowed | Caught, 3 failed |
| Domain: a stated cite that states nothing allowed | Caught, 1 failed |
| Domain: `stated_citation` written as `null` when absent | Caught, 5 failed (byte identity) |
| Re-store: reuse ignores the stated cite (the old rule) | Caught, 3 failed |
| Re-store: no options never reuses a copy with fields | Caught, 3 failed |
| Re-store: a new copy merges the older copy's fields | Caught, 3 failed |
| Date: any form `parse_stated_date` reads is accepted | Caught, 6 failed |
| Date: a year alone completed to 1 January | Caught, 2 failed |
| An empty value stored | Caught, 14 failed |
| Values stored unstripped | Caught, 2 failed |
| The table leaves out a field not stated | Caught, 1 failed |
| Stated fields only fill what the rules left missing | Caught, 5 failed |

### Checks before the report

* **Affected set**: `uv run scripts/affected_tests.py` chose **634 of 661 test files (95.9%)**
  from 18 changed files. `domain/article.py` reaches the root `conftest.py` through
  `debate_core.domain`. That is the whole suite in all but name, well past two minutes, so it is
  **left to the pull request's `ci`** (agreement 10). Within two minutes I ran:
  * the always-run list (`tests/architecture`, `tests/specs`, `test_app.py`, `test_help_rendering.py`,
    `test_container_factories.py`) with `tests/integration/test_fetch_cli.py`: **399 passed in 23.52s**;
  * the changed areas: `packages/debate_core/tests/domain` and `evidence` **2840 passed in 11.68s**;
    `packages/debate_core/tests/application` **5108 passed in 106.18s**; the top-level files of
    `packages/debate_cli/tests` **885 passed in 42.93s**;
  * the smoke files for cut and fetch, as above.
* `uv run --frozen ruff format --check .` → 1835 files already formatted. `ruff check .` → All checks passed.
* `uv run --frozen pyright packages/debate_core packages/debate_cli tests/smoke/test_cut_smoke.py` → 0 errors.
* `uv run --frozen lint-imports` → 20 kept, 0 broken.
* `uv run --frozen python scripts/check_thin_handlers.py` → 72 handlers within 25 statements.
* `uv run --frozen python scripts/check_command_blocks.py` → no `#` comments in 659 blocks.
* `uv run scripts/validate_specs.py` → OK: 585 files, 41 epics, 522 tasks, 22 releases.
* `uv run --frozen python scripts/export_schemas.py` → a second run changes nothing; the committed
  schemas match the models.
* Dev has moved two commits past the branch point (`cc41db6`, local ref, not fetched). Neither touches
  this spec, the domain or `fetch.py`, so I did not sync.

## Files changed

* `plan_specs/v1/e06-card-cutting/t12-…yaml`: the PM's rulings as a dated amendment, the packages, and
  the phase.
* `debate_core.domain`:
  * `citation.py`: `STATED_CITATION_FIELDS`;
  * `article.py`: `SourceSnapshot.stated_citation`, left out of the record when absent, and its
    validator.
* `packages/debate_core/schemas`: `source_snapshot.schema.json` (regenerated, in the amended packages)
  and `fetch_result.v1.json` (Deviation 2).
* `debate_core.application`:
  * `citation_service.py`: `stated_citation()`, `InvalidStatedCite`, applying the stated fields in
    `resolve`, `CitationResolution.stated_fields`, and the docstring;
  * `snapshot_service.py`: `create(stated_citation=…)`;
  * `article_service.py`: the re-store rule and its docstring;
  * `article_fetch.py`: `StatedCite`, `SnapshotSummary.stated_cite`, `ingest_pasted(stated_citation=…)`.
* `debate_cli`: `commands/fetch.py` (the four options, the usage errors, the table rows, help and
  docstring) and `README.md` (the `fetch` section).
* Tests: `domain/test_article.py` (+16 cases), `application/test_citation_service.py` (+18),
  `application/test_article_service.py` (+5), `debate_cli/tests/test_fetch_command.py` (+28),
  `test_cut_command.py` (+5) and `tests/smoke/test_cut_smoke.py` (+1).

## Deviations from the spec

1. **`debate_core.domain` and `source_snapshot.schema.json` joined the packages, by the PM's ruling.**
   No field of a stored snapshot could hold the stated fields. The Article's `authors`,
   `publication` and `published_at` record no source, and search discovery fills them from providers.
   The PM ruled (a): one optional `SourceSnapshot` field. The spec carries it as a dated amendment
   (`4a8e36c`). No migration: the row is a JSON document. **An older build cannot read a row that has
   the field.** The domain is `extra="forbid"`, and a model built from the start commit `1865cf1`
   refuses such a row with `extra_forbidden` on `stated_citation` (checked in the scratchpad). The CLI
   README's `fetch` section says so: "A copy stored with stated cite fields needs this build or later".
   Rows without the field are unchanged, so an older build still reads every other row.
2. **`fetch_result.v1.json` is regenerated, and it is not in the packages.** The PM ruled that fetch
   prints the stated fields it stored, so `SnapshotSummary` gains `stated_cite`, which the export
   script writes into the published schema. The key is optional and absent when nothing was stated,
   so every existing output, and the schema's required keys, are as before. A consumer validating
   against the old schema rejects only an output that has the key.
3. **"The guide's fetch --paste section" is the CLI README.** No document under `docs/guides`
   covers `fetch`; `packages/debate_cli/README.md` has the section, and the sentence is there. It is in
   the packages (`debate_cli`).

## Decisions and assumptions

1. **Re-storing a paste (the PM's Q3 (b)).** Identical text with no cite options, or with options equal
   to the newest copy's, reuses that copy and keeps its fields. Identical text with other options is a
   new copy holding exactly the fields that command stated, nothing merged. As the newest copy, it is
   the one `cut --from-paste` cuts. Changed text is a new copy, as before, with only the fields its own
   command states. Tests: no options keeps the fields; the same options reuse; other options make a
   new copy whose fields alone reach the cite. That cite is
   `Brannigan 26 [Teodor Brannigan; September 14, 2026; …]`, with no title or publication carried over.
2. **A stated field's source is `heuristic`.** The user's title for an article is already recorded
   that way in `resolve()`, and the domain refuses a verified heuristic. No new source value or marker.
3. **Applied through `keep_student_edits`.** A stated field that differs from the derived one replaces
   it, unverified, and is named in `CitationResolution.stated_fields`. A stated field equal to the
   derived value takes the derived field (`heuristic` or `retrieval`, unverified: no field of a pasted
   copy verifies). `student_fields` is untouched.
4. **The words a user sees (the PM's check).** No message or mark says "student" for these fields.
   The cite marks each one `[author unverified]`, `[title unverified]`, `[publication unverified]` or
   `[date unverified]`, through the existing `cite_marks`. The verifier's detail reads "required citation
   fields not verified: authors, title, publication, published_at, canonical_url". The one
   student-worded mark, `[… cleared by student]`, appears only for a field a student's cite edit
   emptied; a statement clears nothing.
5. **Byte identity of existing rows.** `stated_citation` has `exclude_if=None`. A committed test pins a
   snapshot's stored document for every provenance against a hand-written string, and that string
   equals what the start commit wrote. I captured the SQLite repository's `document` bytes for all
   four provenances before the change and again after: `cmp` found them identical (SHA-256 of the
   PUBLISHER_RETRIEVED row `0763f9bf…`, unchanged). Mutant 12 shows the test catches a written `null`.
6. **Dates (the PM's Q2 (a)).** Only `YYYY-MM-DD` that is a real day: `2026`, `2026-08`,
   `August 30, 2026`, `2026-8-30`, `2026/08/30`, `30-08-2026`, `2026-02-30` and `2026-08-30T10:00` are
   each refused. The message is
   `'2026' is not a date in the form YYYY-MM-DD, such as 2026-09-14`.
7. **Usage errors (exit 2), decided before the attestation prompt or any read.** A cite option without
   `--paste` (`--title go with --paste`), an empty or whitespace-only `--title`, `--author` or
   `--publication`, and a bad `--date`. Values are stripped. The option named in the error is the one
   the user typed (`--author` for `authors`, `--date` for `published_at`).
8. **The report's shape.** `stated_cite` is `{authors: [...], title, publication, published_at:
   "YYYY-MM-DD"}`, with `null` (or `[]` for authors) for a field not stated. It is absent when the copy
   has none. The table shows four `Stated …` rows for a copy with fields, `not stated` for a missing
   one, and `Stated cite: none` for a pasted copy without fields. A publisher snapshot shows no row.

## Operator follow-ups

None required. Optionally, after this merges and a dev pre-release carrying it is installed, the coach
can store a library copy with its cite and cut it. Replace `URL`, `NEED`, the file and the cite values;
expected runtime under a minute. Exit 0 with four `Stated …` rows is success:

```bash
cd "$HOME" && env DEBATE_ENV=dev debate-research fetch --paste "$HOME/library-copy.txt" --source-url 'URL' --i-have-lawful-access --title 'TITLE' --author 'AUTHOR' --date 2026-09-14 --publication 'PUBLICATION'
```

Then cut it with the live model; the cite line in the .docx carries the stated fields, and the exit is 4
(UNVERIFIED for its cite alone):

```bash
cd "$HOME" && env DEBATE_ENV=dev DEBATE_MODEL_MODE=live debate-research cut 'URL' --from-paste --need 'NEED' --output "$HOME/pasted-card.docx"; echo "exit $?"
```

## Follow-up work

1. **Year-only and year-and-month dates** (a Citation date change, the PM files it): `published_at` is
   a datetime and `format_cite` prints a whole day, so a source that states only a year or a month
   cannot be cited with that date yet.
2. **A stated cite the domain refuses surfaces as `INTERNAL_ERROR`.** It can't be reached from the CLI,
   because the builder never produces a verified field; mutant 1 showed it. If another caller ever
   builds a stated cite, `ArticleFetch` could map the snapshot's `ValidationError` to a refusal. E06,
   low priority.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
