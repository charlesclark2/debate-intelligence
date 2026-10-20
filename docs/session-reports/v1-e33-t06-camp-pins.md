# Session report: v1-e33-t06-camp-pins

| | |
|---|---|
| Task | `v1-e33-t06-camp-pins` — A recipe can name a camp (OpenEv) card |
| Spec | [`plan_specs/v1/e33-file-builder/t06-camp-pins.yaml`](../../plan_specs/v1/e33-file-builder/t06-camp-pins.yaml) |
| Epic / release | `v1-e33-file-builder` / `v1.2` |
| Branch | `task/v1-e33-t06-camp-pins` |
| Session status | COMPLETE |

## Summary

A recipe can now name a camp (OpenEv) card, still in recipe schema version 1. A pin may say
`caselist: openev` with its release as `snapshot` (`2031-policy`). The writer builds that card
instead of refusing it as `SOURCE_UNREADABLE`. Below the cite it writes the data-use policy's camp
line, `[OpenEv: <camp> <year> — <event>, <file title>]`, in the Undertag style. The sidecar records
the camp occurrence with three new fields. Camp rows get the same suppression rule as every other
occurrence. Every existing recipe, example and sidecar still validates, and a caselist recipe's hash
is unchanged.

**Look at Deviation 1 first.** To give ac1's "AUTO never picks a suppressed camp occurrence" a
case to test, I let the recipe's own `caselist` be `openev` (a file of camp cards). The spec's
description names pins only. PM question 1 asks whether to keep it. Every criterion passed, so the
Goal is `Succeeded`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `camp-pins` (Camp pins) | DONE | Tests committed red first (`533e297`), then the recipe model, resolver, writer and sidecar (`57d54c1`), the guide (`6806bc3`), and three tests the mutation run asked for (`601d1a5`) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a pin naming `openev` and a release resolves, AUTO never picks a suppressed camp occurrence, and the schema and guide say so, by tests shown failing first; every existing example still loads | PASS | **Red** at `533e297`, the new tests against the unchanged code: `uv run pytest -q -p no:randomly <the four test files> -k "camp or openev or caselist_pins or written_before"` → `65 failed, 9 passed`. The failures are for this task's reasons: `openev` refused by the models (`a caselist is its slug…`), and `ResolvedCard` with no `camp_file`, `provenance_line` with no `camp_file`, the writer with no `source_stores`, the sidecar with no `camp_year`. The 9 that pass are guards that must hold both before and after. **Green**: `uv run pytest packages/debate_core/tests/application/test_file_recipes.py -k "camp or openev"` → `25 passed`, including `test_resolve_a_camp_pin_naming_its_release_resolves_to_that_camp_occurrence`, `test_resolve_auto_never_picks_a_suppressed_camp_occurrence`, `test_resolve_a_camp_pin_to_a_suppressed_camp_file_is_refused_not_repointed`, `test_a_camp_pin_and_a_camp_recipe_validate_against_the_published_schema` and `test_the_guide_shows_a_camp_pin_the_models_take`. Examples: `test_examples_load_and_validate`, `test_examples_validate_against_the_published_schema` and `test_examples_resolve_against_a_synthetic_store` pass, the latter two against the regenerated schema |
| ac2: a recipe pinning a camp card builds, with the OpenEv provenance line below its cite and the occurrence in the sidecar, and reads back as its source, by test shown failing first | PASS | Red in the same run (14 writer tests: no `camp_file`, `camp_file=`, `source_stores`). Green: `uv run pytest -q packages/debate_core/tests/integrations/docx_file_writer/test_writer.py -k camp` → `14 passed`. `test_camp_a_recipe_pinning_a_camp_card_builds_with_the_openev_line_below_its_cite` checks every paragraph of the built file, the line in `Undertag`. `test_camp_the_card_reads_back_as_its_source_with_the_line_as_undertag_in_neither_cite_nor_evidence` re-parses the built file with the E31 parser and checks cite, evidence, formatting digest and tag equal to the source card, the line in the card's undertag, and neither the line, the camp nor the title in its cite or evidence. `test_camp_the_sidecar_records_the_camp_occurrence` checks the occurrence, the camp fields and the empty disclosure, and validates the sidecar against `docs/data/file-provenance.schema.json` |
| Node `camp-pins`: Recipe tests pass (`uv run pytest packages/debate_core/tests/application/test_file_recipes.py`) | PASS | → `141 passed in 2.90s` |

The read-back proves the line's style: the paragraph is written with `pStyle Undertag`, and the
parser reads it as the card's undertag, not as cite or evidence. That is the proof t02 gave for the
disclosed line, so no operator Word check is needed (PM notes).

### Checks run before this report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py --run` | `31 of 320 test files`, `1511 passed in 24.90s`, pytest exited 0 after 26 s |
| `uv run pytest -q packages/debate_core/tests/integrations/docx_file_writer/test_fidelity.py` (the writer's fidelity suite) | `31 passed` |
| `uv run pytest -q` over the four changed test files, `docx_file_writer/` and `tests/scripts/test_export_recipe_schema.py` | `442 passed` |
| `uv run ruff format --check .` / `uv run ruff check .` | `894 files already formatted` / `All checks passed!` |
| `uv run pyright packages/debate_core` | `0 errors, 0 warnings, 0 informations` |
| `uv run lint-imports` | `Contracts: 12 kept, 0 broken.` |
| `uv run scripts/export_recipe_schema.py --check`, `uv run scripts/export_file_provenance_schema.py --check` | both `up to date`; each run against the pre-task file printed `stale: …` and exited 1 |
| `uv run scripts/validate_specs.py` | `OK: 394 files, 39 epics, 334 tasks, 21 releases`; `--require-succeeded v1-e33-t06-camp-pins` → `Succeeded` |
| `scripts/check_command_blocks.py`, `scripts/docs_index.py --check-descriptions` | no `#` comments in 281 blocks; all 36 indexed documents described |

### Mutation run (20 mutants, agreement 10's cap)

The run was aimed at the camp line, the source lookup and suppression. Each mutant ran the test
files covering its module, with a new empty `HYPOTHESIS_STORAGE_DIRECTORY` per run (agreement 8;
none of these files uses Hypothesis). After each run the file was restored and its SHA-256
checked, and `git status` was empty afterwards. No mutant errored before its tests ran.

| Mutant | What it breaks | Result | Caught by |
|---|---|---|---|
| R1 | camp rows ranked as dates | CAUGHT (8) | `test_resolve_a_camp_occurrence_with_no_release_record_resolves_without_one` and 7 more |
| R2 | earliest camp release first | CAUGHT (1) | `test_resolve_auto_in_a_camp_recipe_takes_the_latest_release` |
| R3 | no tie-break by release name | survived, then CAUGHT (1) | `test_resolve_auto_breaks_a_tie_in_one_camp_year_by_the_release_then_the_lowest_source`, rewritten so the two rules disagree |
| R4 | a camp pin's release is not matched | CAUGHT (3) | `test_resolve_a_camp_pin_takes_the_release_it_names_when_the_file_is_in_two` |
| R5 | AUTO does not ask about camp rows | CAUGHT (1) | `test_resolve_auto_never_picks_a_suppressed_camp_occurrence` |
| R6 | a camp pin skips the whole-source check | survived, then CAUGHT (1) | new `test_resolve_a_camp_pin_to_a_removed_camp_file_the_store_no_longer_holds_is_refused_as_suppressed` |
| R7 | a camp pin skips the last per-row suppression check | SURVIVED: equivalent | A camp row has no disclosure, so that check asks exactly the whole-source question already asked first. Kept, because it is the one check every pin shares |
| R8 | camp rows stopped by any withdrawal of their bytes | survived, then CAUGHT (1) | new `test_resolve_auto_takes_a_camp_release_whose_bytes_a_team_withdrew_from_its_own_disclosure` |
| R9 | release record not matched to the row's release | CAUGHT (2) | `test_resolve_a_camp_occurrence_with_no_release_record_resolves_without_one` |
| R10 | no release record carried | CAUGHT (3) | `test_resolve_a_camp_pin_naming_its_release_resolves_to_that_camp_occurrence` |
| D1 | a camp pin without a release is taken | CAUGHT (3) | `test_a_camp_pin_needs_the_release_it_names` |
| D2 | a camp pin may name a team | CAUGHT (7) | `test_a_camp_pin_names_no_disclosure_because_a_camp_file_has_none` |
| D3 | a release is taken in a caselist pin | CAUGHT (2) | `test_a_caselist_pins_snapshot_is_a_date_not_a_release` |
| D4 | any release-shaped name is a release | CAUGHT (9) | `test_a_camp_pins_release_is_a_year_and_an_event_the_platform_debates` |
| W1 | the line never names the file title | CAUGHT (8) | `test_camp_a_recipe_pinning_a_camp_card_builds_with_the_openev_line_below_its_cite` |
| W2 | the line takes the camp from the release record | CAUGHT (1) | `test_camp_the_line_takes_the_camp_from_the_occurrence` |
| W3 | the event as the enum writes it (`POLICY`) | CAUGHT (8) | `test_camp_the_line_is_composed_from_the_records_alone` |
| W4 | sources always read from the one store | CAUGHT (2) | `test_camp_a_camp_source_missing_from_its_years_store_is_unavailable` |
| W5 | a camp source read from the caselist's prefix | CAUGHT (1) | `test_camp_the_source_is_read_from_raw_openev_by_its_release_year` |
| P1 | a camp sidecar entry may name a disclosure | CAUGHT (6) | `test_a_camp_entry_names_no_disclosure_because_a_camp_file_has_none` |

## Files changed

* **`debate_core.domain.file_recipe`.** `OccurrencePin.caselist` and `FileRecipe.caselist` take a
  caselist slug or `openev`. A pin's `snapshot` is a date or, for a camp pin, a release. A pin
  validator checks the camp rules on the input, beside the field errors. New constants:
  `CAMP_STORE`, `CAMP_RELEASE_PATTERN`, `RECIPE_STORE_PATTERN`.
* **`debate_core.domain.file_provenance`.** `FileProvenanceEntry` gains `camp_year`, `camp_event`
  and `camp_file_title`, all optional. Only a camp entry names a camp, and a camp entry names no
  disclosure.
* **`debate_core.application.file_recipes`.**
  * A camp pin matches the row of its release.
  * AUTO orders camp rows by release year, then by release name.
  * Each resolved camp card carries its `CampFile` release record (`ResolvedCard.camp_file`).
* **`debate_core.application.ports.evidence_file_writer`.** One docstring sentence.
* **`debate_core.integrations.docx_file_writer.writer`.**
  * The camp refusal is gone.
  * New: the camp provenance line, a header for files with camp cards, and the camp fields in the
    sidecar.
  * A camp source is read with an OpenEv `SourceDocument`.
  * Optional `source_stores`, one store per `raw/` prefix (Deviation 2).
  * `FILE_BUILDER_VERSION` is now `2026.10.19-file-writer-2` (Deviation 3).
* **`docs/data`.** Both schemas regenerated with their scripts. The changes are additive: no new
  required field, and both drift tests pass.
* **`docs/guides/file-recipes.md`.** A "Camp cards (OpenEv)" section, plus a sentence each on AUTO
  and on removals.
* **Tests** (`packages/debate_core/tests`): domain recipe and sidecar tests, resolver and loader
  tests, and writer tests (the camp section at the end of `test_writer.py`). Changes to t01's and
  t02's own tests are listed in Deviation 4.
* **`plan_specs/v1/e33-file-builder/t06-camp-pins.yaml`.** The PM's package amendment, marked, and
  the Goal set to `Succeeded`.

## Deviations from the spec

1. **The recipe's own `caselist` may be `openev`.** The spec's description adds camp pins. But
   ac1 and your notes also ask that "AUTO never picks a suppressed camp occurrence", and AUTO reads
   only the recipe's own store. With a caselist slug there, AUTO never meets a camp row, and the
   criterion is true without a test. So a recipe whose `caselist` is `openev` lets AUTO choose among
   camp releases by the same documented rule. A test shows it skipping a suppressed camp file and
   reporting `SUPPRESSED_OCCURRENCE` when none is left. A caselist recipe still never reaches a camp
   card except by a pin (`test_resolve_auto_in_a_caselist_recipe_never_reaches_a_camp_occurrence`).
   This is additive: every valid version-1 recipe is still valid, with the same hash. Undoing it
   would take one type, the header's camp-only wording, the read-back's source record and about
   eight tests; see PM question 1.
2. **The writer takes an optional `source_stores`.** This is a constructor argument, not a new
   port. Your notes say a camp source is read from `raw/openev/<year>/sha256/…` through the existing
   `SnapshotStore`. The S3 store holds one prefix, though, so a writer with a single store can't read
   both `raw/caselist/<slug>` and `raw/openev/<year>` from a bucket.
   * With `source_stores`, each source is read from the store of its prefix,
     `source_prefix(caselist, snapshot)` from `publish_plan`.
   * Without it, the one `snapshots` store holds every source, as the local blob store does, and
     nothing changes for t02's callers.
   * The `SnapshotStore` re-hash is still what guards the bytes.

   t02's guard on the constructor's parameter list now lists it (Deviation 4).
3. **`FILE_BUILDER_VERSION` is bumped to `-2`.** The version's own rule is "bumped whenever the
   bytes a recipe builds to change". The `.docx` of a caselist recipe is byte-identical, but every
   sidecar now carries three more keys, `null` on a caselist card.
4. **Tests from t01 and t02 that encoded the behaviour this task reverses:**
   * t01's domain tests had `openev` as their example of a refused pin and recipe `caselist`. They
     now use `OpenEv`, which is still refused.
   * t01's `FLOW_STYLE` fixture likewise uses `OpenEv` for its invalid pin, so that test keeps its
     purpose.
   * t02's `test_refusal_a_camp_card_cannot_be_built_from_a_schema_version_1_recipe` is removed.
   * t02's `test_assembly_takes_no_card_text_through_its_api` lists `source_stores`, and also checks
     `CampFile`'s field names now that a resolved card carries one.
   * Two tests read `pin.snapshot` as a date. They now say so explicitly, because a pin's snapshot
     can be a release.

## Decisions and assumptions

1. **A camp pin requires its release.** A camp file is one occurrence row per card per release.
   Without the release, a pin to a file released in two years would match two rows that differ in
   what the provenance line says. The release pattern is strict, `^[0-9]{4}-(?:ld|pf|policy)$`,
   which is what `openev_release_name` writes. A typo such as `2031-polcy` gets its own message
   rather than a date error.
2. **A caselist pin's snapshot is read exactly as before.** A field validator keeps a release as
   text and reads anything else through pydantic's own date validation, re-raising its error type
   and message. Every input t01's tests refuse is still refused at the same location, and a valid
   recipe's hash is unchanged. A release in a caselist pin, and a date in a camp pin, are each one
   error at `pin.snapshot`.
3. **Suppression asks a camp row what the parse pipeline asks a camp file:**
   `suppresses(sha256, disclosure=None)`, so only the whole source stops it. A team's withdrawn
   disclosure of the same bytes does not stop the camp's release; tests cover this for both a pin
   and AUTO. A camp path withdrawn from one release (`v1-e30-t14`) is not asked about, because the
   row carries no path digest. The removal drops that path from the release manifest, and the next
   `caselist parse --caselist openev` drops the row. Before that, on a machine the removal didn't
   run on, the resolver can still pick the row, just as the parse pipeline can (Follow-up 2). Held
   paths are left to t03's amendment, as your notes say.
4. **Where each part of the line comes from.**
   * Camp: the occurrence row (`OccurrenceRecord.camp`).
   * Year, event and file title: the importer's `CampFile` record, listed by source SHA-256 from the
     caselist records the resolver already reads, and kept when `openev_release_name(year, event)`
     is the row's release. No new port.
   * With no record, the line gives the year and event read from the row's release and no title, the
     way a disclosed card with no disclosure on record gets a line without a team.
   * The event is written `Policy`, `LD` or `PF`, as the policy's example writes it.
5. **Nothing in the line names a debater.** It is built from camp, year, event and file title only.
   It never uses the lab, which can carry instructors' initials and is kept out of `CampFile` for
   that reason, nor the manifest path or the OpenEv id. A file title is printed as the importer
   recorded it. `camp_metadata.py`'s own docstring example (`Saltmarsh T - UTNIF 2026 (1)` →
   `Saltmarsh T (1)`) shows a title can carry a surname; per your notes, a published camp title is
   not personal data.
6. **The file's header names OpenEv when it holds a camp card.** For example: "Disclosed and camp
   cards (FILE_IMPORT) from hspolicy26 and OpenEv, each copied from its source file and not verified
   by this platform. Where each card came from is below its cite." A file with no camp card keeps
   t02's header word for word.
7. **The sidecar fields are named `camp_year`, `camp_event` and `camp_file_title`.** Beside a
   disclosed card's side, tournament and round, a bare `event` would read as the debate's event.
   Each defaults to null and none is required, so a sidecar from an earlier build validates against
   the model and the schema (`test_a_sidecar_written_before_camp_cards_still_validates`,
   `test_camp_a_sidecar_written_before_camp_cards_still_validates`).
8. **Synthetic fixtures.** The camp is the invented `Lanternfield Institute` (and `Brackenridge
   Debate Workshop` in one test), with titles `Synthetic Grid Reliability CP` and `Synthetic CP` and
   release year 2031. `CampFile.snapshot`, the import date, is 2026-07-30, because that field
   refuses a future date. The guide quotes the policy's own example line (`Cascade Institute`). No
   real OpenEv file, school or team code is used.
9. **No camp example recipe file.** t01's test holds `tests/fixtures/file_builder/recipes/` to
   exactly three examples, and `tests/fixtures` is outside this task's packages. The guide's camp
   pin is held to the models by `test_the_guide_shows_a_camp_pin_the_models_take`.

## Operator follow-ups

None. Nothing needed credentials, AWS, a device or a run over two minutes. The affected set took
26 s. The read-back proves the line's style, so there is no Word check.

## Follow-up work

1. **`v1-e33-t03` (AUTO prefers attributed occurrences, your t01 ruling).** A camp row never has a
   disclosure. Once t03 makes AUTO prefer rows with a disclosure on record, a camp row with a
   release record should count as attributed, or AUTO in a camp recipe will always fall back to its
   "unattributed" case.
2. **Camp-path withdrawals in the resolver (E31 store, or `v1-e30`).** A camp path withdrawn from
   one release stops that release's row only after a rebuild (Decision 3). Making the resolver ask
   before a rebuild needs the camp path's digest (`camp_path_disclosure`) on the occurrence row,
   which is a parsed-store change.
3. **`v1-e33-t03` and `v1-e39-t08` wiring.** A writer reading the bucket passes `source_stores`
   (prefix → `S3SnapshotStore(prefix=…)`). The local CLI keeps the single store.
4. **The published recipe schema can't refuse a malformed date.** `format: date` is an annotation
   that `jsonschema` does not assert by default. This predates the task; the loader refuses one.

## PM questions

```text
v1-e33-t06 camp pins: two questions, recommendation first.

1. The recipe's own caselist may be openev, so AUTO chooses among camp releases (report Deviation 1).
   The spec's description adds camp pins only; ac1 and your notes also ask that AUTO never pick a
   suppressed camp occurrence, which only has a case to test if AUTO can reach camp rows.
   (a) keep it (recommended: additive, every v1 recipe and hash unchanged, and it lets a file of
       camp cards be built without pinning each one), with the spec description amended to say so;
   (b) revert to pins only: one type, two small writer branches and about eight tests, and ac1's
       AUTO clause is then shown by AUTO never reaching a camp row.

2. Camp-path withdrawals (v1-e30-t14) stop a camp row only once the release manifest is rewritten and
   `caselist parse --caselist openev` runs, exactly as the parse pipeline behaves (report Decision 3).
   (a) file a follow-up to put the camp path's digest on occurrence rows so the resolver can ask
       before a rebuild (recommended, p3; same gap as the parse pipeline's);
   (b) accept as is.

FYI, proceeding unless you say otherwise:
- DocxEvidenceFileWriter gains an optional source_stores (prefix -> SnapshotStore) so a bucket's
  raw/openev/<year> store can be read (Deviation 2); no new port.
- FILE_BUILDER_VERSION is now 2026.10.19-file-writer-2: every sidecar gains three keys (Deviation 3).

Reply with 1: a or b, 2: a or b.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-19

**Notes:**

Accepted, with the phase `Succeeded`. The pull request needs no `--partial`.

**The work itself:**

* **Additive within schema version 1:** every existing recipe, example and sidecar still validates,
  and a caselist recipe's hash is unchanged.
* **The camp line is proven by the read-back,** as t02's disclosed line was. It is read as the
  card's undertag and is in neither cite nor evidence, so no Word check was needed.
* **Each part of the line has a source written down,** never the lab, which can carry initials.
* **Suppression asks a camp row exactly what the parse pipeline asks a camp file,** and the gap that
  leaves (Decision 3) is stated rather than hidden.
* **The affected set took 26 s and passed,** and 20 mutants were run at the cap, aimed where I asked.
  Three survivors became tests, and the one equivalent is argued.

**Rulings:**

1. **Question 1: (a), keep it.** A file of camp cards built by AUTO is useful, and it is the only way
   ac1's AUTO clause has a real case. The PM amends the spec's description in the next batch to say
   the recipe's own `caselist` may be `openev`.
2. **Question 2: (a).** The PM files a p3 follow-up to carry the camp path's digest on occurrence
   rows, so the resolver and the parse can ask about a camp-path withdrawal before a rebuild.
3. **The FYIs are agreed:** the optional `source_stores` (no new port; the re-hash still guards the
   bytes) and `FILE_BUILDER_VERSION` `2026.10.19-file-writer-2`, since every sidecar gains keys.
4. **Deviations 1 to 4 and Decisions 1 to 9 are accepted.** Deviation 4's changes to t01's and t02's
   tests are the behaviour this task reverses, each kept purposeful.
5. **Follow-ups 1 and 3 go into amendments:** `v1-e33-t03` counts a camp row with a release record
   as attributed; `v1-e39-t08` passes `source_stores` for the bucket's prefixes. **Follow-up 4**
   (the schema's `format: date` is not asserted) goes on the deferred list.
