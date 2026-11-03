# Session report: v1-e31-t25-labeller-safeguards

| | |
|---|---|
| Task | `v1-e31-t25-labeller-safeguards` — The labeller warns before a card is lost, and import refuses a file already corrected |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t25-labeller-safeguards.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t25-labeller-safeguards.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t25-labeller-safeguards` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The labeller and `import` now guard against the five things the 2026-10-18 and 2026-10-19 sittings
tripped over, and the guide writes down the sixth. (1) In blind mode `k` straight after `n` gives
the card its completeness. The cause was in `read_cards`, which opened a card only on a start whose
unit was already TAG or CITE; a start on a row with no unit yet now opens one. (2) `import` refuses a
label file that is not `PRELABELED`, naming its status and `--replace`. The first import keeps the
pre-label at `labels/prelabels/<digest>.jsonl` (committed with the label file, no text in it), and
`--replace` counts against that. (3) and (4) are warnings on the page, each saying how to undo it.
(5) is a warning on the page and in `check`, never a refusal. **Look first at "The files whose
count was reset" below:** git shows two reset events, not three, both repaired already, and no
committed count is wrong today. Every acceptance criterion passed, so the Goal is `Succeeded`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `labeller-safeguards` (Labeller safeguards) | Done | Tests committed red first (`47a02d3`), implementation (`6f7ae5b`), one test added for a mutant that survived (`a63e7f4`) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: (1) to (5) each by a test shown failing first | PASS | Red run on `47a02d3` against the unchanged labeller: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest tests/evals/parser/test_labeller.py -n 0 -p no:randomly --tb=line -q -k "<the new tests>"` → **14 failed, 1 passed**. Each failure is an assertion that names its reason (below). The one pass is a guard case (a card whose tag is above its block gets no warning), which already held. The TAG case added after the mutation run was shown red against the start commit `db87736` in a scratch worktree: `assert [4, 7] == [4, 5]`. |
| ac2: the guide's Ambiguous conventions holds the case, and the labeller's help names the warnings | PASS | `test_the_guide_writes_down_the_card_written_body_first` and `test_the_labellers_help_names_every_warning` (the page's Warnings section, `label --help` and the guide each name all ten entries of `labeller.WARNINGS`). Red: "the Ambiguous conventions section has no card written body first" and "the labeller lists no warnings". |
| Node: Labeller tests pass (`uv run pytest tests/evals/parser -k "labeller or worksheet or prelabel"`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run --frozen pytest tests/evals/parser -k "labeller or worksheet or prelabel"` → **134 passed in 3.50s** |

Red-run failure reasons, one test per item:

| Item | Test | Red failure |
|---|---|---|
| (1) | `test_in_blind_mode_k_straight_after_n_gives_the_card_its_completeness` | `'this row is ... completeness' == ''` (k said "in no card") |
| (1) | `test_a_start_with_no_unit_yet_is_a_card_start` | `[] == [(0, (0,), FULL)]` |
| (2) | `test_import_refuses_a_label_file_already_corrected_naming_its_status_and_the_flag` | `assert 0 == 1` (the second import was accepted) |
| (2) | `test_import_replace_counts_against_the_stored_pre_label_not_the_label_file` | "the first import kept no pre-label" |
| (2) | `test_import_replace_with_no_stored_pre_label_records_no_count_and_drops_the_review` | "the first import kept no pre-label" |
| (3) | `test_a_cite_start_directly_under_a_tag_says_the_tag_is_left_outside_its_card` | the row's notes held only "card 2 has no completeness" |
| (4) | `test_n_on_a_row_that_starts_a_card_says_the_card_is_gone_and_how_to_put_it_back` | `'no longer starts a card' in ''` |
| (5) | `test_a_cite_in_no_card_is_a_warning_on_the_page_and_in_check_and_import_takes_it` | no note on the CITE row |
| (5) | `test_a_tag_or_cite_in_no_card_is_warned_unless_cut_off_at_a_block_edge` (4 of 5 cases then) | `[] == [5]`, `[3] == [3, 4]`, `[4] == []`, `[0] == [0, 1]` |

## Before the report

| Check | Result |
|---|---|
| `uv run scripts/affected_tests.py` | 124 of 668 test files from 7 changed files. 15 are bucket-mode files, reached through a false edge: `build_parse_world.py` and `corpus.py` name the guide's path. |
| `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python scripts/affected_tests.py --run` | Stopped at its 115-second limit at 89%, with no failure or error in the part that ran. As agreement 10 says, the rest is left to the pull request's `ci`. |
| `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest tests/evals/parser tests/architecture tests/specs tests/docs -q -m "not slow and not live"` | 880 passed in 11.01s (the changed area, the always-run list, and the docs tests that read the guide) |
| `uv run --frozen ruff format --check .` / `ruff check .` | 1873 files already formatted / All checks passed |
| `uv run --frozen pyright scripts/prelabel_docx.py tests/evals/parser/labeller.py tests/evals/parser/test_labeller.py` | 1 error, already there at the start commit (`__doc__.split` in `main`, `reportOptionalMemberAccess`). CI's pyright includes only `packages`, `tests/architecture` and `tests/smoke`, and no package changed. |
| `uv run --frozen lint-imports` | 20 kept, 0 broken |
| `uv run scripts/validate_specs.py` | OK: 585 files, 41 epics, 522 tasks, 22 releases |
| `scripts/check_command_blocks.py`, `scripts/check_links.py`, `scripts/docs_index.py --check-descriptions` | OK (665 blocks); OK (3470 links and anchors); all 68 described |

## Mutation run

Fourteen mutants, each a committed file changed in place and restored with `git checkout HEAD --`.
Each ran against `test_labeller.py` and `test_prelabel.py` with a new, empty
`HYPOTHESIS_STORAGE_DIRECTORY`. The tree was clean after every run.

| Mutant | Result | Caught by |
|---|---|---|
| PM: a re-import accepted without the flag | caught | `test_import_refuses_…` |
| PM: the count taken against the label file itself | caught | both `test_import_replace_…` tests |
| PM: (4)'s removal done silently | caught | `test_n_on_a_row_that_starts_a_card_…` |
| PM: (5) turned back into a refusal (the warning added to `worksheet_problems`) | caught | `test_a_cite_in_no_card_…`, and the existing `test_a_checked_corrected_worksheet_imports_as_corrected`, whose relabelled TAG is in no card |
| (1) a start with no unit opens no card | caught | both (1) tests |
| (3) no warning for a CITE start under a TAG | caught | the (3) test |
| (5) the block-edge exemption removed | caught | two edge cases |
| (5) the exemption for a card whose tag is above the block removed | caught | the guard case |
| (5) a card runs on through a TAG | **survived**, then caught | added the case "two unstarted cards at a block's end, only the last cut off" (`a63e7f4`) |
| (5) `check` prints no warning | caught | `test_a_cite_in_no_card_…` |
| (2) the first import keeps no pre-label | caught | both replace tests |
| (2) a kept pre-label never fits | caught | the count test |
| (2) the pre-label kept again over an old one on `--replace` | caught | both replace tests |
| (4) the message leaves out the completeness to restore | caught | the (4) test |

## The files whose count was reset

The PM's ruling 3 asked for them by label-file id and count only, and none was changed. I read
every committed version of every label file, on every ref including the `labels/*` branches, and
recounted rows changed `(unit, card)` against the pre-label each version was corrected from. This
was read-only; the scripts are in the session scratchpad.

| Label file | Recorded at the reset | Recount against its pre-label | Today |
|---|---|---|---|
| `15be67df9cfaa272` | 0 (`964fa1bc8`) | 5 | 5: hand-corrected in `e3397a8` ("correct the changed-row count") |
| `bad8c9119196b60a` | 0 (`8b24d7cc8`) | 36 | 10: returned to its pre-label (`7d2d526`) and labelled blind again; recorded 10, recount 10 |

I found no third. `06e05b7abae54eb2` was re-imported too, but only after being returned to its
pre-label (`9b8214f`), so its count was right (7 = 7). Today every one of the 30 files records the
same count as a recount against its last committed pre-label. The seven files that record 0 match
their pre-labels exactly, in units, cards, completeness and spans. If the PM counted a third from
the sittings' notes, it must have been caught before a commit.

## What changes for the labeller

* **`import` run a second time on a file now stops.** It used to rewrite the file and record 0
  rows changed. It now prints `REFUSED; the label file is already CORRECTED …` and the flag to use.
  To correct a file again on purpose, add `--replace`. Replacing a `COACH_REVIEWED` file drops the
  review, and the import says to run `mark-reviewed` again.
* **The first import commits one more file.** `labels/prelabels/<digest>.jsonl` is written beside
  the label file. The guide's existing `git add tests/fixtures/debate_files/eval/labels` already
  picks it up, so no command changes.
* **Blind mode:** `n` then `k` on a row with no unit yet works. The workaround (n, t, Backspace, k,
  Enter) still works, but is no longer needed.
* **`n` on a row where a card starts** still removes the card. It now says so, and how to put it
  back (`n` again, then `k` until it reads the completeness it had).
* **The page's "a TAG not marked as the start" note no longer appears where the card runs on to the
  block's edge**, where the card is cut off. The same rule now covers a CITE in no card.
* **`check` prints `warning:` lines** for a TAG or CITE in no card. The exit code is unchanged.
  On a file already corrected it adds a `note:` that import needs `--replace`.
* No key changed, and no existing flag or command changed.

## Files changed

* `tests/evals/parser/labeller.py`: the card reading's three changes, `cards_missing` (the
  block-edge rule, shared with `check`), the `n` message, and `WARNINGS`, the list the help names.
* `tests/evals/parser/labeller_page.html`: a Warnings section, filled in from `WARNINGS`.
* `scripts/prelabel_docx.py`: `import`'s refusal and `--replace` (in a new `_import`), the kept
  pre-label (`stored_prelabel_path`, `load_stored_prelabel`), the count against it, and
  `worksheet_warnings` in `check`. Also the warnings in `label --help`, and the module docstring.
* `tests/evals/parser/test_labeller.py`: the new tests. One existing test's layout gained a final
  ANALYTIC (see Decisions).
* `tests/fixtures/debate_files/eval/labels/README.md`: step 4's Warnings paragraph, "Importing a
  file again", and the body-first case in Ambiguous conventions.

## Deviations from the spec

* **(5) was not a refusal anywhere.** The spec says `check` and the page should "warn, not refuse".
  At the start commit neither refused a TAG or CITE in no card: `check` said nothing, and the page
  noted only an unstarted TAG, block edge or not. So (5) is a new warning in `check` and on the
  page. Its test asserts that `check` exits 0 and `import` accepts the worksheet, so it would catch
  the warning becoming a refusal. The spec's description could say "warn (they said nothing, or
  only on a TAG)".
* **"three files" in (2):** git shows two reset events, both already repaired (above).

## Decisions and assumptions

* **The flag is `--replace`.** It matches the CLI's existing flags: plain store-true long options,
  with messages in the form "use --X to …", like `prelabel --force`. The spec's own word is
  "replace", and `--force` already means "discard the correction" in `prelabel`.
* **Where the pre-label is stored:** `tests/fixtures/debate_files/eval/labels/prelabels/<digest>.jsonl`.
  Import writes it just before the correction replaces a `PRELABELED` file, so a crash between the
  two leaves the file `PRELABELED`. A subfolder, because `load_label_files` and the label checks read
  only `labels/*.jsonl`. It fits only when it is `PRELABELED`, under the same plan, over the same
  rows. A newer pre-label (after `prelabel --force`) replaces it at the next first import.
* **With no stored pre-label, `--replace` records no count** (`rows_changed_from_prelabel` empty),
  and says so. This holds for the 30 files corrected so far, which have none. An empty count is
  what the schema and `metrics.blind_comparison` already read as "not recorded", so the blind
  comparison leaves the file out rather than using a wrong number. Keeping the old count would be
  stale after a real change; counting against the labels being replaced is the bug. The guide asks
  the coach to tell the PM before replacing one of these files. Restoring their pre-labels from git
  is a follow-up for the PM to decide.
* **"Cut off at a block edge"**, for a TAG or CITE in no card, means every row from it to the
  block's last row could still be part of its card (UNDERTAG, CITE, EVIDENCE, blank, or no unit
  yet). For a CITE it also counts when every row above it to the block's first row could be, which
  is a card whose tag is above the block. A card never runs on through a TAG, a heading, an
  ANALYTIC or a numbered card. The page and `check` share this rule (`cards_missing`).
* **(3)** is noted on the CITE row, because the person stays on that row after `n`. It applies when
  the row above, passing over blank rows, is a TAG or an UNDERTAG.
* **(4)** applies to any card that starts on the row, the pre-label's or the person's own. The
  completeness still goes with the card, as before; the message names it so `k` can restore it.
* **An existing test changed:** `test_problems_with_a_card_are_named_on_its_rows`. Its unstarted
  TAG ran on to the block's end, which (5) now counts as cut off. A final ANALYTIC keeps the card
  inside the block, so the test still checks what it was written for.
* **Help** means the page's new Warnings section and `label --help`. Both list all ten warnings,
  and so does the guide's step 4.

## Operator follow-ups

None. No session command ran over the real corpus or the committed label files; the git history
was only read.

## Follow-up work

* **Pre-labels for the 30 files already corrected** (E31, PM's decision). Each file's last
  committed `PRELABELED` version is in git, and copying it into `labels/prelabels/` would let
  `--replace` count against it. That adds files beside the label files, which this task left alone.
* **`affected_tests.py` false edge** (E41 upkeep): a fixture that names the guide's path pulls 15
  bucket-mode files into a labelling change's affected set.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-02

**Notes:**

The six problems the coach's sittings found are each closed at their cause, and nothing he already
types changes.

1. **ac1 passes.** One test per item, 14 failing against the unchanged labeller with a named reason
   each; the TAG case added after the mutation run shown red against the start commit. 14 mutants,
   the PM's four among them, all caught after the one survivor was closed with a test (`a63e7f4`).
2. **ac2 passes.** The body-first card is in the guide's Ambiguous conventions, and the page, `label
   --help` and the guide all name the ten warnings, pinned by a test.
3. **The reset counts:** the PM's "three files" was wrong; git shows two reset events, both already
   repaired, and every one of the 30 files records the same count as a recount against its last
   pre-label. Thank you for checking every ref rather than taking the number.
4. **Decisions accepted.** `--replace` for the flag; the pre-label kept under `labels/prelabels/`
   (outside what the label checks read) and written before the correction replaces the file;
   `--replace` with no stored pre-label records no count rather than a wrong one, and the guide asks
   the coach to tell the PM first; the block-edge rule shared by the page and `check`.
5. **Deviations accepted:** (5) was a new warning rather than a refusal turned into one; the PM amends
   the spec's wording in the next batch.
6. **Follow-ups:** restoring pre-labels for the 30 corrected files is not needed now, since none has a
   wrong count and a replace of one goes through the PM; the `affected_tests.py` false edge through the
   guide's path is filed for E41.
7. **Closing checks:** the affected set reached 89% with no failure and is left to `ci` (agreement 10);
   the parser evals, architecture, specs and docs tests (880), ruff, lint-imports, the links, the
   command blocks and the specs are clean. The one pyright error predates this task and is outside
   CI's pyright.
8. **Merge:** a plain `scripts/task pr` once `ci` is green. The Goal is `Succeeded`.
