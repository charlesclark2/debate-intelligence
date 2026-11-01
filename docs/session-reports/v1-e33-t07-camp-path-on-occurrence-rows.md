# Session report: v1-e33-t07-camp-path-on-occurrence-rows

| | |
|---|---|
| Task | `v1-e33-t07-camp-path-on-occurrence-rows` — A camp occurrence row carries its camp path's digest, so a camp-path withdrawal stops it before a rebuild |
| Spec | [`plan_specs/v1/e33-file-builder/t07-camp-path-on-occurrence-rows.yaml`](../../plan_specs/v1/e33-file-builder/t07-camp-path-on-occurrence-rows.yaml) |
| Epic / release | `v1-e33-file-builder` / `v1.2` |
| Branch | `task/v1-e33-t07-camp-path-on-occurrence-rows` |
| Session status | COMPLETE |

## Summary

Each camp occurrence row now carries the camp path digest of every live path its file is at in its
release (`camp_path_disclosures`). The resolver and the parse ask the suppression list about those
digests, so a camp path withdrawn from one release stops that release's rows before any rebuild.
The same file in another release is not stopped. A row without digests behaves exactly as before.
A built file's camp cards carry the same digests, and `files check` flags only the card whose own
camp path was withdrawn. There is no parser or fingerprint version bump.

**Look at Deviation 1 first.** Both earlier builds refuse an unknown key in an occurrence row and
in a sidecar entry, and they refuse any record version they don't know. So a new field can't go into
either file, and a schema-version bump doesn't help. I took your other branch: the digests go where
earlier builds never look. They sit in a file beside each strict file (`camp_paths.jsonl` beside the
table, `<file>.camp-paths.json` beside the sidecar), tied to its bytes by SHA-256. In memory the row
and the sidecar entry carry them as the spec says. The cross-build check shows both earlier builds
reading everything this branch writes. Planting the field into either strict file makes
`v1.1.0-dev.251` refuse it.

**Also look at Deviation 4.** The parsed-store doc says a change to its no-path-field guard needs a
policy change first. The field name you chose contains "path", so I narrowed that guard. PM question
2 asks whether you want a policy sentence.

Every criterion passed, so the Goal is `Succeeded`.

## Count first (read-only, the Mac's store)

Run with `python3 -I` over `~/.debate-research/dev`, counts only, in under 0.1 s
(`count_camp_rows.py`, `count_camp_rows_2.py` in the scratchpad).

| What | Count |
|---|---|
| Release manifests | 2 (`2026-ld`, `2026-policy`) |
| Stored camp member rows | 107 |
| … with a path (all a camp path digest needs) | **107** |
| … with `upstream_path_sha256` (`v1-e30-t14`'s identity) | 0 |
| Stored (release, source) keys | 104 (`2026-ld` 2, `2026-policy` 102) |
| … at two or more paths in one release | **3** (all `2026-policy`) |
| Camp occurrence rows (`parsed/openev/2026.10.20-docx-6`) | 8,081, all `2026-policy`, none with a disclosure |
| … whose key has a stored manifest row today | 8,081 |
| … that would carry one digest / two digests / none | 7,845 / 236 / 0 |

So **every camp occurrence row gets a digest on its next parse**. The camp path digest is
`sha256("openev/<release>/<row path>")`, and every stored row has a path. It doesn't depend on
`upstream_path_sha256`, which none of these rows has. No re-import is needed.

Two notes on these numbers:

* The Mac's table is under parser `docx-6` and this build parses with `docx-7`. On the Mac, "next
  parse" means a new `docx-7` directory. The Mac store is stale after the cutover in any case.
* I didn't count the cloud store, because that would be an AWS read.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `camp-path` (Camp path on occurrence rows) | DONE | Red tests over a skeleton `f96d109`; implementation `7912287`; cross-build check `82135f7`; a mutation-run test `52e191f` and an equivalent check removed `9bb41f3` |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: a camp occurrence row carries its camp path's digest; a camp path withdrawn from one release stops that release's rows for the resolver and the parse before a rebuild, by tests shown failing first | PASS | **Red** at `f96d109` (skeleton: the names, no behaviour), the 7 touched test files: `29 failed, 373 passed`. The failures are this task's own: rows carry no digest, there is no `camp_paths.jsonl`, and the parse and resolver don't ask about a camp path. Also `files check` flags every camp card, there's no camp paths file beside the sidecar, and publish refuses. The new tests that passed at red are guards meant to hold before and after: the table keeps the earlier builds' key set, no path in a log, a row without digests resolves as before, and a rewritten table reads with none. **Green**: the same files at `7912287` → `417 passed`. Through the real parse and the real local store (`test_camp_path_on_occurrence_rows.py`): `test_a_camp_path_withdrawn_from_one_release_stops_its_rows_at_the_next_parse_though_still_listed`, `test_a_camp_path_withdrawn_where_another_path_of_its_release_holds_the_file_keeps_that_paths_row`, `test_the_resolver_stops_a_release_whose_camp_path_was_withdrawn_after_the_table_was_built`. Resolver unit tests in `test_file_recipes.py`: AUTO, a pin to each release, two paths, no digests, the same row path in two releases, whole source |
| **ac2**: an earlier build (the agent's at the time) reads every file this build writes, by the cross-build check | PASS | Earlier builds: the cloud run's image `v1.1.0-dev.251` (`a21bb68`) and the Mac's installed build `v1.1.0-dev.200` (`761b571`, from `~/.local/bin/debate-research --version`, read-only). Each is an offline stamped wheel in a scratch venv. `check_an_older_build_reads_this_builds_camp_paths.py`, in three steps. Its output is under "The cross-build check" below |
| **ac3**: a built file's sidecar carries each camp card's camp path digest, and `files check` flags exactly the cards a camp-path suppression names, by test | PASS (the digests are beside the sidecar: Deviation 1) | `test_files_check_flags_exactly_the_camp_card_whose_camp_path_was_withdrawn` builds through `FileBuildService` one file pinning a camp file's card in `2031-policy` and its other card in `2032-policy`. It withdraws 2032's camp path after the build: card 1 `PASS`, card 2 `FAIL … camp path is withdrawn from its release (request RM-2026-09)`. With `.camp-paths.json` removed, both are flagged as before. Red at `f96d109`, green at `7912287`. Also covered: the check's unit tests (two paths, whole source), the writer's entry and companion, the domain round trip and every way the companion is refused, and `files publish`'s re-check (`test_the_check_run_now_reads_a_camp_cards_own_camp_paths_beside_the_sidecar`). `docs/data/file-provenance.schema.json`: `export_file_provenance_schema.py --check` → `up to date` (the field is excluded from serialization, so no regeneration) |
| Node `camp-path`: `uv run pytest packages/debate_core/tests -k "camp or occurrence"` | PASS | Bounded at 115 s with `-n auto`: `575 passed in 61.45s` |

### The cross-build check

The scratchpad path is shortened to `<scratchpad>` and the worktree to `<worktree>`. The run was at
`9bb41f3`, the final code.

```text
writer: <worktree>/packages/debate_core/src/debate_core
this build wrote parsed/openev/2026.10.27-docx-7: 4 occurrence rows, releases ['2031-policy', '2032-policy'], camp paths per row [1, 2]; camp_paths.jsonl b9c929956fb9, failures.jsonl e3b0c44298fc, index.jsonl 0711450968ae, occurrences.jsonl b3f37c6779cf
this build built BUILT: synthetic-camp-file.docx 9f6f2cf282c1, synthetic-camp-file.docx.camp-paths.json 5b389d08b2f1, synthetic-camp-file.docx.provenance.json b5828099bc9b, synthetic-camp-file.docx.quality.json 414b139ded9b, synthetic-camp-file.docx.quality.md 0ef425ed2fb6
=== read step under v1.1.0-dev.251
reader: <scratchpad>/earlier/v1.1.0-dev.251/venv/lib/python3.12/site-packages/debate_core, parser 2026.10.27-docx-7
its parsed store read: 1 per-source file(s), 1 document(s), 1 index row(s), 0 failure row(s), 4 occurrence row(s), stamps ['card-fingerprint-v4']
its resolver: PINNED 2031-policy, PINNED 2032-policy; errors []
its publisher: succeeded True, uploaded 4, skipped 0, suppressed 0, failed 0; aggregates in the bucket ['failures.jsonl', 'index.jsonl', 'occurrences.jsonl']
its sidecar model read 2 card(s), releases ['2031-policy', '2032-policy']; its files check: PASS
its files publish: PUBLISHED, refusal None
its files check after 2032-policy's camp path is withdrawn: card 1 FAIL, card 2 FAIL
its parse: wrote 2026.10.27-docx-7 (this build’s, again), 0 parsed, 4 occurrence rows; the table's bytes unchanged; camp_paths.jsonl still beside it
=== reread step, this build, after v1.1.0-dev.251
this build read the table the earlier build rewrote: 4 rows, camp paths per row by release {'2031-policy': [2], '2032-policy': [1]}
this build's resolver, with 2032-policy's camp path withdrawn and no rebuild of its own: PINNED 2031-policy; errors SUPPRESSED_OCCURRENCE at structure[0].blocks[0].items[1].pin
=== read step under v1.1.0-dev.200
(the same lines as v1.1.0-dev.251, from <scratchpad>/earlier/v1.1.0-dev.200/…)
=== reread step, this build, after v1.1.0-dev.200
(the same two lines)
```

What the output shows:

* **The earlier builds read everything.** Their strict models read every record, their resolver
  resolves both pins, and their publisher publishes. Their `files check` and `files publish` read
  the sidecar this branch wrote.
* **The new file is left alone.** The earlier publisher doesn't send `camp_paths.jsonl`, because it
  isn't one of its aggregate names.
* **Withdrawals look as they did before.** After a camp-path withdrawal, the earlier check flags both
  camp cards, which is today's behaviour.
* **An earlier build's parse keeps the digests usable.** It rebuilds the same rows to the same bytes,
  so this build keeps the digests. Its resolver still stops the withdrawn release without a rebuild
  of its own.

**Mutant 7 through the same check.** For each mutant I planted it, ran the write step, restored the
file, then ran the read step under `v1.1.0-dev.251`:

* M7a writes the digests into the table: `UnreadableParsedStore: … occurrences.jsonl line 1: not a OccurrenceRecord`.
* M7b writes them into the sidecar: `2 validation errors for FileProvenanceManifest`.

How the earlier builds were built, for each of `a21bb68`/`v1.1.0-dev.251` and `761b571`/`v1.1.0-dev.200`:

1. `git archive` into the scratchpad.
2. `scripts/stamp_build.py stamp`.
3. `uv build --offline --package debate-core --wheel`.
4. `uv venv --offline`, then `uv pip install --offline --no-deps` of the wheel.
5. A plain-path `.pth` to the worktree's site-packages, for third-party dependencies only.

`debate_core.__file__` resolved under each venv's site-packages, with no `packages/` path on
`sys.path`. Each venv's `OccurrenceRecord` and `FileProvenanceEntry` had no new field and
`extra='forbid'`, and its `AGGREGATE_NAMES` were the three. Every step ran in under 2 s.

### Mutation run

These are the seven you listed, plus fifteen more aimed at the store's tie, the companion files and
the all/any rules. Each mutant ran the 8 test files that cover it (440 tests), with a new empty
`HYPOTHESIS_STORAGE_DIRECTORY` (none of these files uses Hypothesis). After each run the harness
restored the file from saved bytes, checked them, and cleared `__pycache__`. `git status` was clean
after each batch. No mutant errored before its tests ran.

| Mutant | What it breaks | Result | Caught by (first) |
|---|---|---|---|
| M1 | a withdrawn path still feeding the resolver | CAUGHT (6) | `test_resolve_auto_skips_a_camp_release_whose_camp_path_was_withdrawn_before_a_rebuild` |
| M2a | the parse ignoring the digest (a camp path asked as no disclosure) | CAUGHT (2) | `test_a_camp_path_withdrawn_from_one_release_stops_its_rows_at_the_next_parse_though_still_listed` |
| M2b | the parse writing no digest on its rows | CAUGHT (8) | `test_a_camp_row_carries_the_digest_of_each_live_path_of_its_file_in_its_release` |
| M3a | the same file in another release stopped too (resolver) | CAUGHT (5) | `test_resolve_a_camp_pin_to_the_release_a_path_was_withdrawn_from_is_refused_and_the_other_resolves` |
| M3b | the same file in another release stopped too (parse) | CAUGHT (3) | `test_a_camp_path_withdrawn_from_one_release_stops_its_rows_…` |
| M4 | a row without the digest treated as withdrawn | CAUGHT (3) | `test_resolve_a_camp_row_with_no_camp_paths_is_resolved_as_before_a_withdrawal_of_one` |
| M5 | `files check` flagging every camp card | CAUGHT (4) | `test_files_check_flags_exactly_the_camp_card_whose_camp_path_was_withdrawn` |
| M6 | the sidecar missing the digest | CAUGHT (7) | `test_camp_the_sidecar_entry_carries_the_rows_camp_paths_and_the_sidecar_bytes_do_not` |
| M7a | an earlier build refusing the new record (digests in the table) | CAUGHT (2), and by the cross-build check | `test_the_occurrence_table_keeps_the_keys_and_record_version_every_earlier_build_reads` |
| M7b | an earlier build refusing the new record (digests in the sidecar) | CAUGHT (13), and by the cross-build check | `test_a_camp_entry_carries_its_camp_paths_and_the_sidecar_keeps_the_keys_every_earlier_build_reads` |
| S1 | the store gives digests to a table with other bytes | CAUGHT (1) | `test_a_table_rewritten_with_other_bytes_since_reads_with_no_camp_paths` |
| S2 | the store writes no `camp_paths.jsonl` | CAUGHT (8) | the parse tests |
| S3 | a stale `camp_paths.jsonl` left beside a table with none | CAUGHT (1) | `test_a_table_with_no_camp_path_has_no_camp_paths_file_beside_it` |
| R1 | a camp row stopped when any one of its paths is withdrawn | CAUGHT (1) | `test_resolve_a_camp_row_at_two_paths_of_its_release_is_stopped_only_when_both_are_withdrawn` |
| R2 | a camp row with camp paths not asked about its whole source | SURVIVED twice: equivalent; the check was **deleted** (`9bb41f3`) | see below |
| R3 | the parse's digests taking withdrawn paths too | CAUGHT (1) | `test_a_camp_path_withdrawn_where_another_path_of_its_release_holds_the_file_keeps_that_paths_row` |
| C1 | `files check` flagging a camp card when any one of its paths is withdrawn | CAUGHT (1) | `test_a_camp_card_at_two_paths_of_its_release_is_flagged_only_when_both_are_withdrawn` |
| C2 | camp paths written for another sidecar given to this one | CAUGHT (1) | `test_camp_paths_that_are_not_this_sidecars_give_none[another-sidecar]` |
| C3 | `files check` reading no camp paths beside the sidecar | CAUGHT (1) | `test_files_check_flags_exactly_the_camp_card_whose_camp_path_was_withdrawn` |
| C4 | `files publish` re-checking without the camp paths | CAUGHT (1) | `test_the_check_run_now_reads_a_camp_cards_own_camp_paths_beside_the_sidecar` |
| C5 | a rebuild leaving the camp paths file of the build before | CAUGHT (1) | `test_a_rebuild_with_no_camp_path_leaves_no_camp_paths_file_from_the_build_before` |
| P1 | `camp_paths.jsonl` neither published nor removed with the aggregates | CAUGHT (2) | `test_publish_sends_the_camp_paths_with_the_aggregates` |

**R2.** It survived, so I wrote
`test_resolve_auto_skips_a_camp_row_with_camp_paths_whose_whole_source_is_suppressed` (`52e191f`). I
saw that test pass unmutated, and R2 still survived it. That's because
`SuppressionState.suppresses(sha, disclosure=…)` already returns true for a source suppressed as a
whole, so `suppresses_source(…) or all(…)` equals `all(…)` whenever the row has a camp path. Per
agreement 8, I deleted the redundant question and kept the test.

M1, M3a and R1 targeted the lines that deletion changed. I re-ran them against `9bb41f3`, and all
three were caught again (6, 5 and 1 failures).

### Checks run before this report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` (selection only) | `402 of 631 test files (63.7%) chosen in 17.3 s from 30 changed files`. The root conftest reaches `ports/parsed_store.py` through `integrations.models.record_replay → cassette_filing → version_retention`. That is about two-thirds of a ~6-minute selection, with a load average of 14 to 36 from other sessions, so it is **over two minutes and left to the pull request's `ci` check** (agreement 10). Not run with `--run` |
| Always-run list and the changed areas' test directories: `tests/architecture`, `tests/specs`, the three CLI wiring tests, `debate_core/tests/{domain, evidence/file_checks, integrations/docx_file_writer, integrations/local}`, `test_local_parsed_store.py`, `test_parsed_store_schema_versions.py`, the CLI `files` tests | `2096 passed in 39.18s` |
| Every test file under `debate_core/tests/application`, `debate_cli/tests` and `tests/smoke` that names a changed module (83 files, listed by grep). A first 115 s run stopped at 97%, so the same 83 files ran in three bounded parts | `664 passed in 63.47s`, `360 passed in 40.28s`, `669 passed in 106.93s` |
| `ruff format --check .` / `ruff check .` | `1744 files already formatted` / `All checks passed!` |
| `pyright packages/debate_core` | `0 errors, 0 warnings, 0 informations` |
| `lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `scripts/export_file_provenance_schema.py --check` | `up to date` |
| `scripts/check_command_blocks.py`, `scripts/docs_index.py --check-descriptions`, `scripts/check_links.py` | no `#` comments in 636 blocks; all 61 indexed documents described; 3255 links OK |
| `uv run scripts/validate_specs.py` (after `set-phase … Succeeded`) | `OK: 554 files, 41 epics, 491 tasks, 22 releases`; `--require-succeeded v1-e33-t07-camp-path-on-occurrence-rows` → `Succeeded` |
| This spec against `origin/dev` (local ref, `d6418fd`, not fetched) | differs only in `status.phase`; no amendment |

## Files changed

* **`debate_core.application.ports.parsed_store`**:
  * `OccurrenceRecord.camp_path_disclosures` (in memory, `exclude=True`, only on a camp row,
    sorted).
  * `CampPathRecord`, the line of `camp_paths.jsonl`.
  * `CAMP_PATHS_NAME`, and `REBUILT_NAMES` (the aggregates plus `camp_paths.jsonl`).
* **`debate_core.application.caselist.parse_sources`**:
  * `live_disclosures` asks about a camp path by its camp path digest.
  * New `camp_path_digests`, the digests a release's rows carry.
  * New `occurrence_is_stopped`, the one rule the resolver asks of a row.
* **`debate_core.application.caselist_parse`**: each camp row is written with its release's live
  camp path digests.
* **`debate_core.application.file_recipes`**: AUTO and pins ask `occurrence_is_stopped`. A pin's
  refusal for a camp path says so. The module's docs are updated.
* **Publish, removal and residue** (`parsed_publish`, `removal_plan`, `removal_residue`): they use
  `REBUILT_NAMES`, so `camp_paths.jsonl` is published after the per-source files, deleted by a
  removal, and counted as residue.
* **`debate_core.integrations.local.parsed_store`** (outside the spec's packages: Deviation 3):
  * It writes `camp_paths.jsonl` tied to the table's SHA-256, or removes a stale one.
  * It gives the digests back on read only to a table with those bytes.
  * It ignores a companion line it can't read.
* **Sidecar and `files check`**:
  * `debate_core.domain.file_provenance`: `FileProvenanceEntry.camp_path_disclosures` (in memory),
    `CampPathSidecar`/`CampPathCard`, `camp_path_sidecar_name`, and the manifest's
    `camp_path_sidecar` and `with_camp_paths`.
  * `debate_core.integrations.docx_file_writer.writer`: the entry carries the row's digests, and
    `BuiltEvidenceFile.camp_paths_json` comes back with the build.
  * `file_build_service`: writes the companion, or removes a stale one.
  * `file_quality_service`: reads it and joins it.
  * `file_publish_service`: its re-check reads it.
  * `debate_core.evidence.file_checks.structure`: a camp card with camp paths is flagged only when
    all of them are withdrawn.
  * `report.CHECKER_VERSION` is now `2026.10.31-file-checks-4`.
* **`docs/data`**:
  * `parsed-card-store.md`: the row's field, a `camp_path` record section, and the aggregates,
    removal and policy paragraphs.
  * `built-file-metadata.md`: the file beside the sidecar, which is not published.
* **Tests** (`packages/debate_core/tests`):
  * New: `application/test_camp_path_on_occurrence_rows.py`.
  * New: `application/check_an_older_build_reads_this_builds_camp_paths.py`, not collected.
  * Additions to `test_file_recipes.py`, `test_file_build_service.py`, `test_file_publish_service.py`,
    `evidence/file_checks/test_structure.py`, `domain/test_file_provenance.py` and
    `integrations/docx_file_writer/test_writer.py`.
  * Changes to other tasks' tests: Deviation 4.
* **`plan_specs/…/t07-camp-path-on-occurrence-rows.yaml`**: the Goal is set to `Succeeded`.

## Deviations from the spec

1. **The digests are not written into `occurrences.jsonl` or the sidecar; each goes in a file beside
   it.** Both earlier builds read occurrence rows and sidecar entries with `extra="forbid"`. They
   accept only record versions `1, 2` and sidecar version `1`. A new key fails them, and so would a
   schema-version bump. The cross-build check shows both failures with mutants M7a and M7b. So I
   took your other branch, "the field goes where older readers ignore it":
   * **The table.** `camp_paths.jsonl` sits in the `openev` version directory. Each line is one
     camp path of one file in one release: the six fields, `camp_path_disclosure`, and the
     `occurrence_table_sha256` it was written beside. The local store puts the digests back on the
     rows only when the table's bytes have that SHA-256.
   * **The sidecar.** `<file>.docx.camp-paths.json` holds `sidecar_sha256` and each camp card's
     `position` and digests.
   * **In memory.** `OccurrenceRecord` and `FileProvenanceEntry` carry `camp_path_disclosures` as
     the spec describes. The field is `exclude=True`, so no dump of either model can write it into
     the strict file.

   ac3 says "the sidecar carries"; here the file beside it carries the digests, read as one with
   the sidecar by `files check` and `files publish`. PM question 1.
2. **The field is plural, `camp_path_disclosures`, a sorted tuple.** On the Mac, 3 files (236 rows)
   sit at two paths in one release. One digest per row would make a withdrawal of either path stop
   a release that the other path still holds. A row is now stopped only when every one of its camp
   paths is withdrawn, the rule `v1-e30-t14`'s removal applies to the manifest. Each stored line
   (`camp_paths.jsonl`) still has the singular `camp_path_disclosure` you named.
3. **The change goes beyond `constraints.packages`.**
   * `debate_core.integrations`: the local parsed store, which writes and reads the table, and the
     writer, which writes the sidecar.
   * `debate_core.evidence.file_checks`: `check_suppression` and `CHECKER_VERSION`.

   ac3, from the 2026-10-21 amendment, can't be met without the writer and the check. The packages
   list predates that amendment.
4. **I changed tests from other tasks:**
   * `test_local_parsed_store.py::test_no_record_has_a_field_for_a_path_school_team_tournament_or_round`
     refused any field with "path" in its name. It now allows exactly `camp_path_disclosures` and
     `camp_path_disclosure`, and checks that each refuses a path as its value (the error is at that
     field). `CampPathRecord` is added to its records.

     The parsed-store doc says "a change that needs either test changed needs the policy changed
     first". The value is a digest of a camp path, not a person's path, school or team, like
     `disclosure`. The doc's policy paragraph now says so. **PM question 2.**
   * `test_report.py`: its hand-written Markdown pins the checker version, now `-4`.
   * `test_file_build_service.py`: the `World` takes a suppression record, empty by default, in
     place of `empty_suppression_list()`, so a test can withdraw a camp path. Its `recipe()`
     and `test_file_publish_service.py`'s now take a `caselist`.
5. **`AGGREGATE_NAMES` is unchanged, and `REBUILT_NAMES` is new.** Three removal tests iterate
   `AGGREGATE_NAMES` over a caselist directory and expect each file there. `camp_paths.jsonl` is in
   `openev` only, so publish, removal and residue use `REBUILT_NAMES` instead.

## Decisions and assumptions

1. **The tie is by bytes.** A table rewritten with other rows has other bytes, and its rows read
   with no digests, as before this task. An earlier build's rebuild of the same rows writes the
   same bytes, because the rows carry no digest. So the digests survive it, and this build still
   stops a withdrawn release afterwards (cross-build reread step).

   **The cost:** a new path added to a release since this build's last parse, followed by an
   earlier build's rebuild of unchanged rows, leaves that path's digest unknown. A withdrawal of the
   old path would then stop the row although the new path holds it. That is over-stopping, the safe
   direction, until this build parses again.
2. **A companion this build can't read** (a later build's shape) gives no digests, rather than
   failing the read. The rows then behave as before this task.
3. **The parse asks a camp path the publisher's question.** `publish_plan` already asks a camp
   manifest row by `camp_path_scope(release)`, and `live_disclosures` now does the same. The
   rebuild drops a withdrawn path's release whether or not this machine's manifest was rewritten,
   and keeps a release whose file another path holds. A team's withdrawn caselist disclosure of the
   same bytes still stops no camp row (`test_a_teams_withdrawn_disclosure_of_the_same_bytes_stops_no_camp_row`).
4. **`files publish` doesn't upload `.camp-paths.json`.** The published five objects are unchanged
   (`docs/data/built-file-metadata.md`). Follow-up 1.
5. **`FILE_BUILDER_VERSION` is not bumped.** The `.docx` and sidecar bytes are unchanged; the
   builder only writes one more file.
6. **`CHECKER_VERSION` is bumped** to `2026.10.31-file-checks-4`, because the suppression check's
   verdict can change. Under `v1-e33-t16`, `files publish` will refuse a file checked by `-3` as
   `QUALITY_REPORT_OUTDATED` until `files check` runs again.
7. **Messages and logs name no path.** The pin refusal says "the pinned release's camp path has been
   withdrawn from it", and `files check` says "the card's camp path is withdrawn from its release
   (request …)". `test_the_parse_logs_no_camp_path` checks the parse's log records for each path and
   digest.
8. **Synthetic fixtures only.** The camp file is the `v1-e31-t03` structural fixture. The camp is the
   invented `Lanternfield Institute`, the releases are 2031 and 2032, and the row paths are
   `openev-512/513/640-Synthetic_Grid_CP.docx`.

## Operator follow-ups

None. Nothing needed credentials, AWS, a device or a run over two minutes from the operator. The
affected set (402 files) runs in the pull request's `ci` check (agreement 10).

## Follow-up work

1. **Publish the camp paths with a built file** (E33 or `v2-e35`). The bucket's sidecar carries no
   camp path, so a takedown matched against published files, or the V2 tub, can't tell which
   release's camp card a withdrawal names. Publishing `.camp-paths.json` as a sixth object would
   change the published layout and `metadata.json`'s reader, which is a decision for the tub's
   contract.
2. **Count the cloud store's camp rows** (operator, read-only AWS), if you want the cloud's numbers
   beside the Mac's.

## PM questions

```text
v1-e33-t07 camp path digests: two questions, recommendation first.

1. Where the digests live (report Deviation 1). Both earlier builds refuse an unknown key in an
   occurrence row or a sidecar entry, and refuse any record version they don't know, so a new
   field or a version bump breaks them (shown with planted mutants under v1.1.0-dev.251). I put
   the digests in a file beside each: camp_paths.jsonl beside occurrences.jsonl, and
   <file>.camp-paths.json beside the sidecar, each tied to the strict file's bytes by SHA-256. In
   memory the row and the sidecar entry carry them (camp_path_disclosures).
   (a) accept, with ac3 read as "the sidecar, or the file beside it, carries" (recommended: both
       earlier builds read everything this build writes, by the cross-build check);
   (b) put them in the strict files once no earlier build is in use, with a later task to move
       them and bump the record versions then.

2. The parsed-store guard test (report Deviation 4). It refused any record field with "path" in its
   name; the doc says changing it needs the policy changed first. The new fields hold a camp path's
   digest, not a person's path, school or team.
   (a) accept the narrowed guard (it allows exactly these two names, each shown refusing a path),
       no policy change (recommended);
   (b) rename the fields to avoid "path" (e.g. camp_release_disclosures);
   (c) add a sentence to the data-use policy first.

FYI, proceeding unless you say otherwise:
- The field is plural (camp_path_disclosures): 3 files on the Mac (236 rows) sit at two paths in one
  release, and a row is stopped only when every one of its paths is withdrawn.
- CHECKER_VERSION is now 2026.10.31-file-checks-4: files checked before need files check again
  before files publish (QUALITY_REPORT_OUTDATED).
- .camp-paths.json is not published (Follow-up 1).

Reply with 1: a or b, 2: a, b or c.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
