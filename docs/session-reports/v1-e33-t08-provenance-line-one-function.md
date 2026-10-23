# Session report: v1-e33-t08-provenance-line-one-function

| | |
|---|---|
| Task | `v1-e33-t08-provenance-line-one-function` — Built files carry no provenance line; the sidecar keeps the provenance |
| Spec | [`plan_specs/v1/e33-file-builder/t08-provenance-line-one-function.yaml`](../../plan_specs/v1/e33-file-builder/t08-provenance-line-one-function.yaml) |
| Epic / release | `v1-e33-file-builder` / `v1.2` |
| Branch | `task/v1-e33-t08-provenance-line-one-function` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The E33 writer no longer writes a provenance line below any cite, for disclosed and camp cards
alike, as data-use policy version 1.11 requires. The old `without_line` path is now the only path,
and the read-back no longer expects a line. The writer's own `provenance_line` is deleted. Each
sidecar entry's `provenance_line` is now composed by
`debate_core.domain.evidence_search.occurrence_provenance_line`, the function the pilot's card page
uses, with the writer's records converted at the boundary. Four files and their sidecars were
recorded from the start commit's writer. Against them, every sidecar is byte for byte the same apart
from `docx_sha256`, and every file has lost exactly its line paragraphs (9 in all) and nothing else.
The provenance quality check now runs the other way: a file whose text holds a provenance line fails,
and a card with no sidecar entry still fails. Every behaviour was shown red against the start
commit's source first, and 19 of 19 mutants were caught.

**The PM should look first at the three items under Deviations.** All three come from the forbidden
entry "no change to a built file beyond removing the provenance-line paragraphs". The built file's
header analytic still ends "Who disclosed each card is below its cite.", which is now untrue. Neither
`FILE_BUILDER_VERSION` nor the sidecar schema's description of `provenance_line` was changed. A
paste-ready question for each is in Follow-up work.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `one-line`: No provenance line in built files | Done | Red commit `aa0d699`, implementation `b1e8624`, mutation follow-ups `fba0b8b` |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a built file, disclosed and camp cards alike, holds no provenance line, its sidecar is unchanged, and the golden files differ only by the removed paragraphs, by tests shown failing first | PASS | **Red** (start commit's source, before any `src` change): `.venv/bin/python -m pytest -q -rf -p no:randomly -m "not slow and not live" packages/debate_core/tests/integrations/docx_file_writer packages/debate_core/tests/evidence/file_checks packages/debate_core/tests/application/test_file_quality_mutations.py packages/debate_core/tests/domain/test_evidence_search_query.py` → `44 failed, 319 passed`. **Green**: same command → `364 passed`. The before/after evidence is `test_built_files_without_the_line.py`, run for four cases: disclosed cards; a camp card with its release record; a camp card without one; an occurrence with no disclosure on record. The **paragraph-level comparison** removes the hand-counted line paragraphs from the recorded file. The result must equal the new `word/document.xml` paragraph for paragraph (every run and style), and byte for byte as a whole; every other package part must be byte-identical and in the same order. **Sidecar identity**: the new `manifest_json` equals the recorded one byte for byte after the old `docx_sha256` (asserted to occur once) is swapped for the new one. The writer's hand-written goldens (`test_assembly_writes_the_recipe_in_order_in_the_profiles_styles` and `test_camp_a_recipe_pinning_a_camp_card_builds_with_no_line_below_its_cite`) were edited by hand: only their `("Undertag", …)` rows were deleted |
| ac2: the quality check fails a built file whose text holds a provenance line and still fails a card with no sidecar entry, by tests shown failing first; the writer's `provenance_line` is gone and the domain function remains for the card page | PASS | Same red and green runs. Red for the right reason: `test_a_built_file_whose_card_holds_its_provenance_line_fails`, `test_a_provenance_line_outside_any_card_fails_with_its_paragraph` (two cases) and `test_a_card_with_no_sidecar_entry_fails_provenance` (structure.py) each got `[]` where a FAIL was expected. So did `test_mutation_a_provenance_line_written_below_a_cite_fails_provenance` and `test_a_card_with_no_sidecar_entry_fails_provenance` (the service, from disk). `test_provenance_the_sidecars_line_is_the_card_pages_and_the_writer_has_none_of_its_own` failed on `hasattr(writer_module, 'provenance_line')`. All are green now. The domain tests in `test_evidence_search_query.py` still pin `occurrence_provenance_line` against hand-written lines |
| Node `one-line`: Writer tests pass (`uv run pytest packages/debate_core/tests/integrations/docx_file_writer`) | PASS | `168 passed in 2.57s` |

**What the red run showed, grouped by failing assertion.** The built file still held the line: the
goldens, the recorded comparison, all ten cite shapes, the highlighted cite and the camp cards. The
writer still had its own `provenance_line`. The provenance check passed a file holding a line and a
card with no entry. The report's description had changed. The 319 that passed include, as expected:
sidecar byte identity (that can only go red under mutation), the hand count of the recorded files'
line paragraphs (`test_the_recorded_files_held_the_line_where_counted`, which shows the count matches
the old files), and the neighbouring tests this task does not change.

**Mutation runs** (`perl -e 'alarm 110; exec @ARGV' .venv/bin/python -u run_mutants.py`, from a
clean tree, each mutant restored from a byte copy and checked byte-equal afterwards, a fresh
`HYPOTHESIS_STORAGE_DIRECTORY` for each). Writer mutants ran
`packages/debate_core/tests/integrations/docx_file_writer`. Check mutants ran
`packages/debate_core/tests/evidence/file_checks` and `test_file_quality_mutations.py`.

| # | Mutant | Result | First test to catch it |
|---|---|---|---|
| 1 | The line below every cite again | CAUGHT (34 failed) | `test_the_file_is_the_recorded_one_without_its_provenance_line_paragraphs` |
| 2 | The line for camp cards only | CAUGHT (11) | same, camp case |
| 3 | The line for disclosed cards only | CAUGHT (29) | same |
| 4 | The line as an Analytic paragraph, not Undertag | CAUGHT (68) | fidelity read-back |
| 5 | The line after the card's body | CAUGHT (34) | `test_no_paragraph_of_the_built_file_holds_a_provenance_line` |
| 6–12 | Sidecar line: side, school, tournament, round, camp, camp event, camp file title each dropped at the boundary | CAUGHT (7 to 10 each) | `test_the_sidecar_is_the_recorded_one_byte_for_byte_but_the_files_own_hash` |
| 13 | Sidecar line: camp year dropped | SURVIVED, then CAUGHT | Without the year, the function falls back to the release name's year, which equals the record's in every case the resolver produces. Added the case `the-records-year-over-the-releases-name`, seen passing unmutated (364 passed), then caught (1 failed) |
| 14 | Check: no paragraph holds a line | CAUGHT (4) | `test_a_provenance_line_outside_any_card_fails_with_its_paragraph` |
| 15 | Check: the policy's form not read | CAUGHT (1) | same, `the-policys-form` |
| 16 | Check: a sidecar line inside other text not read | CAUGHT (1) | same, `a-sidecar-line-inside-other-text` |
| 17 | Check: a line inside a card not reported on the card | CAUGHT (2) | `test_a_built_file_whose_card_holds_its_provenance_line_fails` |
| 18 | Check: a line on a card reported again by paragraph | CAUGHT (2) | same |
| 19 | Check: a card with no sidecar entry passes | CAUGHT (2) | `test_a_card_with_no_sidecar_entry_fails_provenance` |
| 20 | Check: the form's closing `]` not asked | SURVIVED | Nothing could tell the clause from its absence, so I deleted it (working agreement 8). The form is now "a paragraph opening `[Disclosed: ` or `[OpenEv: `" |

Mutants 7 to 10 first reported "did not apply", because their text also occurs in the manifest code.
I anchored them on the function's indentation and ran them again. Mutants 14 to 16 were run again
after the rewrite in mutant 20's row and were caught. Each batch's run time was 2 to 3 s per mutant.

**Before the report** (load average about 6 to 9):

* `uv run scripts/affected_tests.py` → `215 of 398 test files (54.0%) chosen … from 27 changed
  files`. A one-line comment fix in `docx_parser/parser.py` pulls in 154 of them. I ran the list
  directly with `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -q -n auto -m "not slow
  and not live" <the 215 files>`. The alarm stopped it at 115 s, 94% of the way through, with 6406
  passed, 2 xfailed and no failure or error. No pytest process was left. The rest is the PR's `ci`
  (working agreement 10).
* Within two minutes, the changed modules' test directories, the card page's users of the domain
  function, the always-run list and the docs checks:
  `perl -e 'alarm 110; exec @ARGV' .venv/bin/python -m pytest -q -n auto -m "not slow and not live"`
  over `tests/integrations/docx_file_writer`, `tests/evidence/file_checks`,
  `tests/integrations/docx_parser`, `test_file_quality_mutations.py`, `test_file_recipes.py`,
  `test_evidence_search.py`, `test_evidence_search_query.py`, `test_file_provenance.py`,
  `test_search_index_reader_sqlite_features.py`, `debate_api` `test_copy_card.py` and
  `test_search_pages.py`, `tests/architecture`, `tests/specs`, `test_app.py`,
  `test_help_rendering.py`, `tests/docs` and `test_check_command_blocks.py` → `2080 passed, 2
  xfailed in 23.36s`.
* The cheap checks are in [Closing checks](#closing-checks).

## Files changed

* `packages/debate_core/src/debate_core/integrations/docx_file_writer/writer.py`: no line in the
  body, and `_assemble` writes a card's paragraphs in their source order. `provenance_line`,
  `HIGHLIGHTED_CITE_CAUSE`, `_explain`, `_is_highlighted`, the `without_line`/`with_line` parameters
  and the read-back's line check are gone. `_sidecar_provenance_line` converts the records and calls
  the domain function. Docstrings updated.
* `packages/debate_core/src/debate_core/evidence/file_checks/structure.py`: `check_provenance`
  fails a line in the file's text and a card with no sidecar entry. The completeness rules are
  unchanged. Module docstring updated.
* `packages/debate_core/src/debate_core/evidence/file_checks/report.py`: `CHECKER_VERSION` is now
  `2026.10.22-file-checks-2`, because the verdicts change. The `provenance-complete` description is
  reworded. Codes and report format are unchanged.
* Docstrings and comments only: `run_copier.py`, `docx_parser/parser.py`,
  `application/file_recipes.py`, `domain/file_provenance.py`, `domain/evidence_search.py`.
* `docs/guides/file-recipes.md`: the camp-card passage now says the line is in the sidecar, not in
  the built file. `docs/evidence` had nothing to change, and neither did the rest of `docs/guides`
  (grepped for the line, "below its cite", `[Disclosed`, `[OpenEv` and "Undertag").
* Tests, edited by hand: `test_writer.py`, `test_fidelity.py`, `test_structure.py`,
  `test_report.py`, `test_file_quality_mutations.py`, `test_evidence_search_query.py`. New:
  `test_built_files_without_the_line.py` and `files_built_with_the_provenance_line/` (four
  `.docx`, four sidecars, a README), all synthetic.
* `plan_specs/…/t08-provenance-line-one-function.yaml`: `debate_core.evidence` added to
  `constraints.packages`, with the PM's ruling as a comment above the key (checked by printing the
  parsed node). The Goal is set to `Succeeded`.

## Deviations from the spec

All three come from one forbidden entry: "Any change to the sidecar, or to a built file beyond
removing the provenance-line paragraphs". I followed it each time, which left something now untrue
in place. The PM decides each one; the questions are in [Follow-up work](#follow-up-work).

1. **The header analytic says something untrue.** `header_line` still ends "Who disclosed each
   card is below its cite." (disclosed-only files), or "Where each card came from is below its
   cite." (files with a camp card). No built file has anything below its cites now. Rewording the
   header would change a paragraph that is not a line paragraph, and would fail ac1 as written.
2. **`FILE_BUILDER_VERSION` is still `2026.10.19-file-writer-2`.** Its own comment says it is
   "bumped whenever the bytes a recipe builds to change", and they have changed. Bumping it changes
   the sidecar's `builder_version` field, so I left it. Nothing reads the version except the
   quality report's "Writer (from the sidecar)" row, so the cost of not bumping is that files with
   and without lines share one version.
3. **The sidecar's schema still describes `provenance_line` as "The line written below the cite
   (data-use policy, Attribution rule 2)."** This is in `FileProvenanceEntry` and the committed
   `docs/data/file-provenance.schema.json`. Changing it changes the sidecar's published schema, and
   `docs/data` is outside the task's packages.

The sidecar's `docx_sha256` necessarily changes, because it is the new file's own hash. The identity
test proves every other byte.

## Decisions and assumptions

* **What counts as a provenance line in the file's text:** a paragraph opening `[Disclosed: ` or
  `[OpenEv: ` (the policy's two forms), or a paragraph holding any sidecar entry's exact line
  anywhere. A line inside a card is reported on that card. A line outside every card (the header, an
  analytic) is reported by `paragraph_index` with no card. The message never quotes the line.
* **"Still fails a card with no sidecar entry."** Before, only `manifest-alignment` failed such a
  card. Now that the file has no line, the sidecar entry is a card's only provenance. So
  `provenance-complete` fails it too: "the document's card has no sidecar entry, so no provenance on
  record". It matches cards to entries by position, not fingerprint. My first version matched by
  fingerprint, and that also failed the one-character-flip mutation suite's card, repeating
  alignment's finding. Whether an entry is the same card stays alignment's question.
* **Names that now read narrower than the check:** the code `provenance-complete` (and
  `QualityCheck.PROVENANCE_COMPLETE`) now also covers "no line in the file's text" and "a card with
  no entry". As the PM asked, I left the name as it is and reworded only its description.
* **The highlighted-cite explanation is gone.** `_explain` rebuilt a failing file without the line
  to ask whether the line caused the failure. With no line written, the two builds are identical. So
  `_explain`, `HIGHLIGHTED_CITE_CAUSE`, `_is_highlighted` and the test that a stand-in parser
  blamed the line (`test_refusal_names_the_line_as_the_cause…`) were removed. A read-back refusal is
  now a plain `READBACK_MISMATCH` with what differs. This is the PM's "generalise the existing
  `without_line` path", taken to its end.
* **The recorded fixtures are the old writer's output.** They are not the code under test, so they
  can contradict it (working agreement 6). What is hand-written is which paragraphs to take out and
  the line each held. `test_the_recorded_files_held_the_line_where_counted` checks that count
  against the recordings. The recording script ran once from the start commit's unchanged `src`
  (`writer … 2026.10.19-file-writer-2` printed), and nothing in the repository regenerates them.
* **Camp-card tests now build files.** The parametrised camp-line and disclosure-line tests used to
  call the writer's `provenance_line` directly. They now build a one-block file and read the
  sidecar's line, so they test the conversion at the boundary. `_camp_build` gained `release`,
  `camp_name` and `record` parameters for that.
* `run_copier.CopiedCard` still splits a card at its last cite paragraph. The writer now writes the
  two halves one after the other. I left the copier alone: only its docstring changed.

## Closing checks

Run on the committed tree after the last edit, in this order:

* `uv run --frozen ruff check .` → `All checks passed!`
* `uv run --frozen ruff format --check .` → `1112 files already formatted`
* `uv run --frozen pyright packages/debate_core` → `0 errors, 0 warnings, 0 informations`
* `uv run --frozen lint-imports` → `Contracts: 15 kept, 0 broken.`
* `uv run --frozen python scripts/check_thin_handlers.py` → `OK: 46 CLI command and API route handlers within 25 statements`
* `uv run --frozen python scripts/validate_specs.py` → `OK: 420 files, 40 epics, 358 tasks, 22 releases`
* `uv run --frozen python scripts/docs_index.py --check-descriptions` → `All 43 indexed documents under docs/ have a description`
* `uv run --frozen python scripts/check_command_blocks.py --base origin/dev` → ``OK: no `#` comments in 348 shell code blocks in 140 Markdown files (1 session reports changed since origin/dev)``

## Operator follow-ups

None. Opening a built file in Word belongs to `v1-e33-t03` and `v1-e39-t08`.

## Follow-up work

* **Built files made before this task fail the new check.** Any file in the evidence workspace built
  by `2026.10.19-file-writer-2` holds lines and now fails `provenance-complete`. Rebuilding it fixes
  that. This belongs with `v1-e33-t03`'s `files` commands, if such files exist.
* **A disclosed card copied from a team's own built file.** A team that disclosed a file built by
  the old writer has lines in its cards' undertags. The writer copies a card losslessly, so a file
  built from such a card fails the check. That is the policy's outcome, but it may surprise a coach.
  For E33, if it is ever seen.
* **Questions for the PM**, as one relay block:

```text
PM questions from v1-e33-t08 (2026-10-22). Each comes from the forbidden entry "Any change to the
sidecar, or to a built file beyond removing the provenance-line paragraphs", which I followed.

1. The built file's header analytic still ends "Who disclosed each card is below its cite."
   (or "Where each card came from is below its cite." with a camp card), which is now untrue.
   a) Amend the forbidden entry and ac1 to allow rewording the header's last sentence, e.g.
      "Where each card came from is in the file's sidecar.", in a follow-up task.
   b) Drop the sentence instead.
   c) Leave it.
   Recommendation: (a), soon. It is the one untrue sentence a student reads in the file, and the
   change is two strings in header_line plus the two goldens that pin them.

2. FILE_BUILDER_VERSION is still 2026.10.19-file-writer-2, though its own rule says to bump it
   whenever a recipe's bytes change, and they have.
   a) Bump it to 2026.10.22-file-writer-3 with (1), accepting one changed sidecar field
      (builder_version); the identity test would then exclude that field too.
   b) Leave it.
   Recommendation: (a), together with (1), so one version names "files without the line".

3. The sidecar schema's description of provenance_line still says "The line written below the
   cite" (FileProvenanceEntry and docs/data/file-provenance.schema.json).
   a) Reword it to "The card's provenance line, as the pilot's card page shows it (Attribution
      rules 2 and 3); a built file's text carries none" and re-export the schema, in the same
      follow-up, with docs/data added to its packages.
   b) Leave it.
   Recommendation: (a). It changes the schema's text only, not one byte of any sidecar.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-22

**Notes:**

Accepted, on three conditions closed in this session before the pull request. They answer your
three PM questions here rather than in a follow-up task. Record them under "PM conditions", keep
the phase `Succeeded`, and open the pull request with no `--partial`; v1-e39-t08 depends on this
task. If anything comes out differently from what is written here, stop and ask for another review.

**What the PM checked.**
* The branch is clean on origin/dev at `c3b9dee`, and the diff is the 27 files listed.
* Since then dev has gained v1-e07-t08 (#411) and two PM batches (#405 and #413). None touches
  this task's files, but sync anyway (condition 4) so the pull request's base is current.

**What is good.**
* **The recorded fixtures are the strongest evidence this task could give.** They are four files
  and sidecars from the start commit's writer. Every built file equals the recording with exactly
  its counted line paragraphs removed, and every sidecar is identical byte for byte, bar its own
  file's hash.
* **The sidecar's line now comes from the one domain function the card page uses,** so the
  duplicate this task was first filed to remove is gone.
* **The check's evidence holds up.** It was turned round, red first. Matching by position rather
  than fingerprint keeps it from repeating alignment's finding. Two survivors were handled honestly:
  a test added for the camp year, and the unreachable `]` clause deleted.

**Rulings on the PM questions. The forbidden entry protected the sidecar and the removal path, not
untrue words.** It was never meant to keep a sentence the change made false. So add above the
forbidden entry:

`# PM ruling 2026-10-22: the header analytic's last sentence, FILE_BUILDER_VERSION and the schema's description of provenance_line change with the rule; every other byte of a sidecar is unchanged.`

**Conditions, all closed in this session:**

1. **Question 1: drop the sentence (option b), not reword it.**
   * `header_line` loses "Who disclosed each card is below its cite." and "Where each card came
     from is below its cite."
   * The other option pointed the reader to a sidecar a student never receives: v1-e39-t08's
     downloads stream the .docx alone.
   * Update the two goldens that pin it by hand. Extend ac1's comparison so the header paragraph
     differs by exactly that sentence.
2. **Question 2: bump `FILE_BUILDER_VERSION` to `2026.10.22-file-writer-3` (option a).** The
   identity test then excludes `builder_version` as well as `docx_sha256`, and asserts the old
   value's single occurrence before the swap, as it does for the hash.
3. **Question 3: reword the schema description (option a).**
   * `FileProvenanceEntry.provenance_line` becomes, in words like these, "The card's provenance
     line, as the pilot's card page shows it (Attribution rules 2 and 3); a built file's text
     carries none."
   * Re-export `docs/data/file-provenance.schema.json` with the repository's export script, and
     add `docs/data` to `constraints.packages`.
   * No sidecar byte changes. Show the schema diff is that one description.
4. **Sync** (`scripts/task sync`), then re-run:
   * the changed test directories, the always-run list and the docs checks;
   * pyright, `lint-imports`, ruff and `validate_specs.py`.

   Record the results. Re-run the mutation rows touching the header or the version if they move.

**Accepted as written.**
* `CHECKER_VERSION` bumped, the code name left as it was, and the docs grep.
* The camp tests now building files.
* `run_copier` left alone.
* **Removing `HIGHLIGHTED_CITE_CAUSE` and `_explain`.** With no line written, the two builds they
  compared are identical. v1-e33-t03's spec still asks that refusal to be "kept as a safeguard";
  the PM amends that paragraph in the next batch. Do not edit that spec here.

**Follow-ups:**
* Files built by `file-writer-2` failing the new check goes to v1-e33-t03's brief, where `files
  build` first runs. None exists outside the tests today.
* A disclosed card holding an old line is recorded. It is the policy's outcome; the PM revisits it
  only if a coach meets it.
