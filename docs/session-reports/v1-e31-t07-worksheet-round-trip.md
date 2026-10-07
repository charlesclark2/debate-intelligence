# Session report: v1-e31-t07-worksheet-round-trip

| | |
|---|---|
| Task | `v1-e31-t07-worksheet-round-trip` — Labeling worksheets survive a spreadsheet round trip |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t07-worksheet-round-trip.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t07-worksheet-round-trip.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t07-worksheet-round-trip` |
| Session status | COMPLETE |

## Summary

`scripts/prelabel_docx.py` gets a `check` subcommand. It runs every validation `import` runs,
writes nothing, and lists every problem in every row, by row number as Numbers shows it, column,
cause and fix. `check` and `import` both read the `.numbers` file Cmd+S writes, through
numbers-parser in the `dev` group. They stop when given the older of `<digest>.csv` and
`<digest>.numbers`. `check --repair --out` restores each row's text from the document, carries the
marks onto it, fills emptied sampled span cells and empties unsampled ones. It writes nothing when
letters or digits differ, and it never writes a label cell. The guide's per-file loop is now: save
in Numbers, `check --repair`, import, delete both files. The PM's step 4 in Charlie's local guide is
no longer needed; [what to change there](#changes-for-the-pm-to-make-in-charlies-local-guide) is
below.

**Look at first:** Hypothesis found a bug in how marks were carried, and the same bug is in the
PM's stopgap ([Decisions, mark alignment](#mark-alignment)). And the real-file check: on Charlie's
leftover `9d0a74b95ccf9269.numbers` (Numbers 13.1), repair-then-import reproduced the committed
`9d0a74b9…` labels exactly ([evidence](#run-on-a-real-numbers-file)).

The Goal is set to `Succeeded`: every criterion passed in this session, and none needs a device, a
credential or a merge.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `check-and-repair` | DONE | `check`, the `.numbers` reader, the repair and the guide. Both node criteria pass (below). |

## Acceptance criteria

Every command ran from the task worktree on 2026-10-02.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — `check` runs every validation `import` runs, writes nothing, lists every problem in every row; exit 0 when import would succeed, 1 otherwise; `import` refuses with the same list; each 2026-10-02 failure has its own message, shown with a synthetic worksheet | PASS | `uv run pytest tests/evals/parser/test_prelabel.py` → `49 passed`. Writes nothing and exits 0: `test_check_of_a_worksheet_import_accepts_exits_0_and_writes_nothing` (snapshots the labels and worksheet folders). Same list as import, exit 1: `test_check_lists_exactly_the_problems_import_refuses_with`. The four failures: `test_an_emptied_sampled_span_cell_is_named_as_empty_not_as_edited_text`, `test_text_the_spreadsheet_changed_is_named_by_the_characters_that_differ`, `test_an_untouched_worksheet_is_named_as_the_original_not_as_every_row_unchecked` with `test_the_untouched_original_points_at_the_numbers_file_beside_it`, and `test_a_table_name_line_above_the_header_is_named`. Every problem per row: `test_every_problem_in_a_row_is_reported_not_only_the_first`. All seven failed first on the old code ([Failing first](#failing-first)). |
| **ac2** — `check` and `import` read a `.numbers` path through a dev-group reader, never a runtime dependency; stop when `--worksheet` is the older of the two; a test reads a small `.numbers` file built from synthetic text | PASS | `pyproject.toml` `[dependency-groups] dev` gains `numbers-parser>=4.19`. debate-core and debate-cli are unchanged, and `uv run lint-imports` → `Contracts: 11 kept, 0 broken.` Read path: `test_check_and_import_read_a_numbers_file_directly` builds the file at test time with numbers-parser's writer, from the synthetic file's text. Older file: `test_a_csv_older_than_the_numbers_file_beside_it_is_refused`, `test_a_numbers_file_older_than_the_csv_beside_it_is_refused`, and `test_the_newer_of_the_two_is_read_without_complaint`. On a real Numbers 13.1 file, see [below](#run-on-a-real-numbers-file). |
| **ac3** — `check --repair --out` restores `text`, carries marks by alignment, fills an empty sampled cell with text and no marks, empties unsampled cells, one line per change; refuses and repairs nothing beyond whitespace/quotes/dashes/ellipses/line breaks; tests cover each repair and the refusal; labels byte-identical | PASS | Same run. Text: `test_repair_restores_every_row_the_spreadsheet_changed_and_then_imports` covers double space, trailing line break, line break for space, em dash, non-breaking space, ellipsis, curly quotes and en dash, with one line per changed row. Marks: `test_repair_carries_the_marks_onto_the_restored_text` and the property `test_marks_land_on_the_same_words_after_any_respacing`. Empty cells: `test_repair_fills_an_emptied_sampled_cell_with_its_text_and_no_marks`. Unsampled: `test_check_notes_span_cells_on_unsampled_rows_and_repair_empties_them`. Refusal: `test_repair_refuses_and_writes_nothing_when_letters_or_digits_changed` and the property `test_a_row_is_refused_exactly_when_a_letter_or_digit_changed`. Labels: `test_labels_are_byte_identical_before_and_after_a_repair` compares the label cells of the CSV before and after, the `.jsonl` bytes, and the imported labels against a hand-written expectation. The property `test_a_repair_never_writes_a_label_cell` covers the same ground. |
| **ac4** — the guide's per-file loop: save, `check --repair`, import; drops the claim that Numbers does not rewrite text; the report says the local workaround scripts are no longer needed; worksheet and `.numbers` deleted after a successful import | PASS | [`labels/README.md`](../../tests/fixtures/debate_files/eval/labels/README.md) section "3. Each file", rewritten. `test_the_guides_loop_repairs_before_it_imports_and_deletes_both_files` checks the order and both `rm`s. `test_the_guides_code_blocks_are_safe_to_paste_into_zsh` passes over the new blocks. The local guide: [below](#changes-for-the-pm-to-make-in-charlies-local-guide). |
| Node `check-and-repair`: Worksheet tests pass offline | PASS | `uv run pytest tests/evals/parser/test_prelabel.py` → `49 passed in 7.05s` (with the repository's default `addopts`: `--disable-socket`, xdist, coverage). |
| Node `check-and-repair`: The guide's loop uses check | PASS | `grep -c "check --repair" tests/fixtures/debate_files/eval/labels/README.md` → `2`. |

Other checks:

| Command | Result |
|---|---|
| `uv run --frozen pytest tests -q --no-cov` | `851 passed, 1 skipped, 1 warning in 38.64s`. The skip is the real PR-subset tier ("4 of 6 pr-subset files are not yet corrected by a person"). The warning comes from an existing smoke-harness test that trips the socket block on purpose. |
| `uv run --frozen pytest tests/evals/parser/test_labels_schema.py` | Passes. `test_every_committed_label_file_is_valid_and_listed` covers the two committed CORRECTED files, `9d0a74b9…` and `a888a5db…`; nothing in the schema changed. |
| `uv run --frozen ruff check .` / `ruff format --check .` | `All checks passed!` / `501 files already formatted` |
| `uv run --frozen lint-imports` | `Contracts: 11 kept, 0 broken.` |
| `uv run scripts/validate_specs.py` | `OK: 307 files, 38 epics, 249 tasks, 20 releases` (after setting the phase) |

### Failing first

The seven tests for the 2026-10-02 failures were committed alone, as `ce5da6e`, before any
implementation. Against the code at that commit, each failed for its own reason (run with
`-p no:randomly -n0 --no-cov`, `7 failed`):

| Test | What the old code printed |
|---|---|
| emptied sampled span cell | `row 7 underline: the text under the markup was edited; only move the marks`, the wrong cause |
| text changed by the spreadsheet | `row 6: the text was edited; …` and the same for `row 7`, naming no character |
| every problem in a row | `row 7: not marked checked` and `row 7: 'EVIDENSE' is not a unit`, but not the empty `underline` or the unclosed `highlight` in the same row: 2 of 4 |
| untouched worksheet | `11 problem(s): row 2: not marked checked …` once per row |
| table-name line above the header | `the worksheet has 12 rows; the sampling plan labels 11`, which reads the table name as the header |
| CSV older than the `.numbers` beside it | the stale CSV read silently: `11 problem(s): row 2: not marked checked …` |
| untouched CSV with a `.numbers` beside it | the same, with no mention of the `.numbers` file |

The tests for `check`, `--repair` and `.numbers` reading could not fail that way, because the old
command line rejects the subcommand and flags outright. What shows they test something is the
mutation table below.

### Mutation

Each mutant switches off one behaviour, then runs `tests/evals/parser/test_prelabel.py` with
`HYPOTHESIS_STORAGE_DIRECTORY` set to a new empty directory and `-p no:cacheprovider`. The runner
writes the original file back afterwards and checks `git status` is clean for both files. A run
counts as a catch only if tests failed and nothing errored. All eleven ran in one 66-second batch.

| Behaviour | Mutant | Result (fresh database each run) | Caught by |
|---|---|---|---|
| Every problem, not the first per row | keep only the first problem in each row | CAUGHT, 3.5 s | `test_every_problem_in_a_row…`, `test_check_lists_exactly…` |
| Mark alignment | marks carried by raw position, no alignment | CAUGHT, 3.2 s | the alignment property, `test_a_mark_over_a_space…` |
| Mark alignment | one position map, so an inserted character at a mark's end is swallowed (the bug found below) | CAUGHT 4 of 4 runs, 4.1 to 5.4 s | the alignment property only |
| Refusal threshold | never refuse | CAUGHT, 4.8 s | the refusal property, `test_repair_refuses…`, `test_markup_that_changes…` |
| Refusal threshold | letters only, so a changed digit is repaired | CAUGHT 4 of 4 runs, 4.6 to 7.0 s | the refusal property only |
| Refusal threshold | refuse any difference | CAUGHT, 13.3 s | 8 tests, including both repair properties |
| Blanking unsampled cells | unsampled cells left as they are | CAUGHT, 3.3 s | `test_check_notes_span_cells_on_unsampled_rows_and_repair_empties_them` |
| Label preservation | label cells stripped of whitespace | CAUGHT, 11.5 s | the label property, `test_labels_are_byte_identical…` |
| Label preservation | `unit` upper-cased | CAUGHT, 10.9 s | the same two |
| Older-file detection | comparison reversed | CAUGHT, 3.3 s | 7 tests |
| Older-file detection | never detected | CAUGHT, 3.0 s | both older-file tests |

The two mutants that only a property catches were re-run three more times, each from an empty
database, and were caught every time.

**What the properties generate** (`--hypothesis-show-statistics`, 300 examples each):

- alignment: 37% of cases move a mark with the spacing; another 30% change spacing without moving
  one;
- refusal: 31% of cases refuse and 69% repair;
- labels: 78% repair some row;
- message length: every case has an edit.

Each property was also run once at 5,000 examples, in 2.5 to 10.4 s, and all four held.

### Run on a real Numbers file

`~/parser-eval-worksheets/9d0a74b95ccf9269.numbers` is still on the Mac. It is the worksheet behind
the committed `9d0a74b9…` labels (#162), saved by Numbers 13.1. Working agreement 2 allows a
read-only run of a few seconds over files the operator already has, so I ran these. They printed
counts, row numbers and fixed message openings only, no cell text:

- numbers-parser read it in 0.01 s: 1 sheet, 1 table, the worksheet's header, 29 rows.
- `check` → exit 1: `row 4, highlight: empty: …` and `row 22, highlight: empty: …`, nothing else.
  Every row's `text` matched the document exactly when read from the `.numbers` file.
- `check --repair --out <scratchpad>` → the two cells filled, `ready to import; 29 rows checked`,
  exit 0. The scratch CSV was deleted straight away.
- In process, `import_worksheet` on the repaired worksheet: paragraphs, cards and spans **equal the
  committed label file**. The label file's bytes did not change.

## Files changed

- `pyproject.toml`, `uv.lock`: `numbers-parser>=4.19` in the `dev` group (MIT; pulls in
  `python-snappy` 0.7, which is cramjam-based and builds nothing, plus `protobuf`, `compact-json`,
  `sigfig`, `enum-tools` and `setuptools`).
- `tests/evals/parser/worksheets.py` (new): reads a worksheet from `.csv` or `.numbers`, detects
  the older file, splits markup, describes differences in words, aligns marks, and repairs.
- `scripts/prelabel_docx.py`:
  - `check` subcommand;
  - `worksheet_problems`, which collects every problem;
  - `import_worksheet` built on it, now also checking the card rules `write_label_file` applies;
  - `import` reads `.numbers` and stops on the older file;
  - the markup helpers move to `worksheets.py` and stay re-exported here;
  - docstring updated.
- `tests/evals/parser/test_prelabel.py`: 28 new tests (four of them Hypothesis properties) and the
  synthetic one-file evaluation fixture they run on. Five existing tests now match the new wording:
  `row 6, checked: empty` for `row 6: not marked checked`, and so on. Each still asserts the same
  refusal.
- `tests/fixtures/debate_files/eval/labels/README.md`: section 3 rewritten around
  `check --repair`; the Workflow list names `check`; the Excel/Numbers paragraph no longer implies
  Numbers leaves text alone.
- `plan_specs/…/t07-worksheet-round-trip.yaml`: phase `Succeeded`.
- This report.

No `.numbers` file is committed: tests build them at test time from the synthetic file's text, so
`tests/evals/parser/fixtures/` was not needed. No worksheet content or card text from a real file
went into the repository.

## Deviations from the spec

1. **`import` now refuses a few worksheets it used to crash on.** `import_worksheet` never checked
   the card rules that `write_label_file` enforces: a CITE in every card, no heading or analytic
   inside a card, completeness consistent with EVIDENCE. A worksheet breaking one passed every
   check and then died in `write_label_file` with a `ValueError` traceback. ac1 says `check` exits
   0 exactly when `import` would succeed, so both now name these in row terms ("row 5, card: card 0
   has no CITE row"). As a backstop, the finished label file goes through `validate_label_file`
   before `import` writes it. `test_check_catches_a_card_rule_import_used_to_meet_only_when_writing`
   covers it. The two existing CORRECTED files are unaffected: they passed `write_label_file` when
   they were imported.
2. **The repair also removes the table-name line.** ac3 lists four repairs. A CSV exported with
   "Include table names" has one more line above the header. `check` reports it with its own
   message (ac1), and `--repair` drops it and prints a line saying so. It is spreadsheet furniture,
   not a label. When the `.numbers` file is read directly the line does not exist at all.
3. **Span cells on unsampled rows are a note, not a problem.** `import` has always ignored them,
   and refusing them would break "exit 0 when import would succeed". `check` prints them as
   `note: row N, underline: this row is not sampled for spans, so import ignores this cell`, and
   `--repair` empties them (ac3).

## Decisions and assumptions

### The `.numbers` reader: numbers-parser

The authorised osascript fallback was not needed.

- **Licence:** MIT (`License-Expression: MIT` in the installed metadata).
- **Current Numbers:** its metadata says it is tested against Numbers 10.0 to 14.4 and Numbers
  Creator Studio up to 15.1. Charlie's Mac has Numbers 13.1, and numbers-parser read the real
  13.1 file above correctly.
- **Installs with uv on Charlie's Mac:** `uv add --group dev "numbers-parser>=4.19"` with uv 0.11.7
  on this Mac resolved and installed 10 packages in under a second, and nothing compiled. The
  setup block in the guide (`uv sync --all-packages`) installs it in the main clone.
- **Where it lives:** in the existing `dev` group rather than a new one. CI's
  `uv sync --locked --all-packages` and Charlie's setup block already install `dev`; a separate
  group would need `--group` added to both. It is imported lazily, inside the `.numbers` reader
  only.

### Reading a cell

numbers-parser returns a number cell as a float (`12.0`) and an empty cell as `None`, and its
`formatted_value` renders 12 as `12.0`. The reader therefore writes integral numbers as `12`,
empty cells as `""`, and text exactly as stored. Trailing empty rows are dropped. An index written
with a thousands separator (`1,234`) is accepted, in case Numbers shows one.

### The refusal threshold

A row is refused when the sequence of letters and digits in the two texts differs. That is
equivalent to "the changed characters include a letter or digit", and it does not depend on how a
diff happens to line the strings up. `str.isalnum`, so `é`, `Ω`, `²` and Arabic-Indic digits all
count.

### Mark alignment

Letters and digits anchor the alignment: the k-th one in the worksheet is the k-th in the
document. Only the stretches of spacing and punctuation between anchors are diffed. Where the
document has characters inserted at a position, the position has two possible places, so the
alignment keeps both: a mark ends at the earliest and starts at the latest. Inserted characters at
a mark's edges therefore stay unmarked.

Hypothesis found the need for this on its first run. With one map, a mark ending at `0` before a
document's `\r\n`, against a worksheet's `\n`, came back as `⟦0\r⟧\n`. **The PM's stopgap has the
same rule**: its `position_map` sends a position inside an `insert` opcode to `j2`. So a character
Numbers dropped right at the end of a mark would have been re-inserted *inside* the mark.

For `9d0a74b9…` this made no difference: the tool's import reproduces the committed spans exactly.
`a888a5db…` cannot be checked, because its `.numbers` file is gone. It is affected only if Numbers
changed a character exactly at a mark's edge in one of its sampled span cells; the PM may want to
spot-check that file's spans against Word.

### Messages

- A row number is the one Numbers shows, with the header as row 1; a CSV's table-name line does not
  shift it.
- Each message names the column, the cause and the fix.
- A difference is described in words ("a non-breaking space where the document has a space",
  "a line break missing", "an em dash added") with up to 12 characters of the document's text on
  each side. The context shrinks until it is not the whole cell, and a changed stretch is quoted to
  at most 20 characters.
- A property checks that no message contains the whole paragraph, on texts of 40 to 300
  characters.
- Messages say "differs only in spacing or punctuation" rather than "the spreadsheet changed it",
  because a stray "!" may be a person's.
- The untouched-original message replaces the per-row "checked: empty" lines rather than adding
  to them.

### Older-file detection after a repair

After `check --repair --worksheet X.numbers --out X.csv`, the CSV is the newer file. Running
`check` on `X.numbers` again without saving in Numbers first therefore stops ("X.numbers is older
than X.csv"). That is the intended reading: nothing new was saved. The guide's loop always saves
before re-running.

## Changes for the PM to make in Charlie's local guide

The workaround scripts in `~/Documents/debate/debate-intelligence-tool/parser-eval-labeling-guide.md`
are no longer needed once this merges and Charlie has run the setup block (`git pull`,
`uv sync --all-packages`):

1. **Header line** ("Step 4 is new … `v1-e31-t07` will build that into the tool"): say the tool now
   does it.
2. **Step 2:** "Numbers rewrites a little too (spacing, line breaks), which step 4 repairs" becomes
   "…which `check --repair` repairs".
3. **Step 3, last paragraph:** keep Cmd+S, and add "keep working in the `.numbers` file
   (`open ~/parser-eval-worksheets/${f}.numbers`), not the CSV". Drop "Step 4 turns the `.numbers`
   file into the CSV".
4. **Step 4: replace the whole block** with the one command from the repository guide.
   Everything goes: the osascript export, the `~/parser-eval-fresh` worksheet, the embedded
   Python, and the `rm -r ~/parser-eval-fresh`. Terminal no longer asks to control Numbers.
   - Success becomes `ready to import; N rows checked, M labeled differently from the pre-labels`.
   - The single STOP becomes **REFUSED** (letters or digits differ; nothing written) and
     **STOPPED** (the file named is older than the one beside it).
   - Problems are listed all at once.

   ```bash
   uv run python scripts/prelabel_docx.py check "${f}" --worksheet ~/parser-eval-worksheets/${f}.numbers --repair --out ~/parser-eval-worksheets/${f}.csv
   ```

5. **Step 5:** drop "but only the first problem in each row, so a second run can name another in
   the same row". The import block itself is unchanged and already deletes the `.numbers` file.
6. Charlie's **auto-correction** advice stays. A capitalised letter is now refused rather than
   silently restored, so it matters more, not less.

## Operator follow-ups

1. **Delete a leftover worksheet.** `~/parser-eval-worksheets/9d0a74b95ccf9269.numbers` is still on
   the Mac after its import merged (#162). It holds card text, and the guide says it goes once the
   import succeeds. I read it for the check above and did not delete it, because it is Charlie's
   file. Run in any terminal; it takes under a second and prints nothing on success.

   ```bash
   rm -f -r ~/parser-eval-worksheets/9d0a74b95ccf9269.numbers
   ```

2. After this merges, the setup block the guide already has installs numbers-parser in the main
   clone (`uv sync --all-packages`, seconds). The first `check` on a `.numbers` file confirms it.
   Success is a `ready to import` line or a list of problems, not `reading a .numbers file needs
   numbers-parser`.

## Follow-up work

- **`a888a5db…` spans** may deserve a spot-check against Word, for the stopgap alignment rule above.
  It falls under the coach review of `v1-e31-t05-parser-eval`, and only the PM can decide it.
- **LibreOffice is still untested** (as the guide already says). `check --repair` on its CSV should
  behave like the Numbers path, but no one has saved a worksheet from it.

## Closing

`uv run scripts/task_helper.py set-phase v1-e31-t07-worksheet-round-trip Succeeded`, then
`uv run scripts/validate_specs.py` → `OK: 307 files, 38 epics, 249 tasks, 20 releases`.
`ROADMAP.md` was not regenerated.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-07

**Notes:**

Accepted, phase `Succeeded`, with no code changes requested. One read-only check is asked for
before the PR (below).

* **The mark-alignment bug is real, and it is mine.** In my stopgap's `position_map`, a position at
  an insertion maps past the inserted characters. A mark ending exactly where Numbers had dropped a
  character therefore takes that character back inside the mark. Your two-map rule (a mark ends at
  the earliest place and starts at the latest) is right. The mutant that only the property catches
  shows the property earns its place.
* **The real-file run is the strongest evidence in the report.** On `9d0a74b9…`'s own `.numbers`
  file, repair-then-import reproduced the committed labels exactly. It printed counts only.
* **Deviations 1 to 3:** accepted.
  * Deviation 1 (`check` and `import` now enforce the card rules `write_label_file` applies) closes
    a crash and keeps "exit 0 exactly when import would succeed" true.
  * Deviation 2: the table-name line is spreadsheet furniture.
  * Deviation 3 (unsampled span cells are a note): `import` has always ignored them.
* **Decisions:** accepted:
  * numbers-parser in the existing `dev` group, imported lazily;
  * the letters-and-digits refusal rule;
  * messages that never quote a whole cell;
  * older-file detection after a repair.

**Before the PR: a read-only check of `a888a5db…`'s spans.** Its import used my stopgap. The
stopgap carried marks on rows 18, 22 and 31, the rows where Numbers had changed the text. The bug
can only have put whitespace at the edge of a span. So load the committed `a888a5db…` label file
and the document's text the way the tool does, and list every span range, underline or highlight,
whose first or last character is whitespace. Report only the row number as the worksheet showed
it, the column, which edge, and the kind of whitespace (space, non-breaking space, line break).
Print no text. Append the result to this report under "PM-requested check".

* If the list is empty, say so and open the PR.
* If it is not, open the PR anyway and stop there. Charlie will look at those rows in Word, and the
  PM will decide whether a label correction is needed.

**Charlie's local guide:** the PM updates it after this merges, following your list.

## PM-requested check

Run on 2026-10-07 from the task worktree. This was a read-only, in-process load of the committed
`a888a5db…` label file (`CORRECTED`) and of the document's text, loaded the way the tool loads it.
The paragraph texts still match the label file's digests. It printed row numbers, columns, edges
and whitespace kinds only, and took 0.45 s.

The file has 8 sampled rows, numbered as the worksheet showed them: 3, 4, 7, 9, 13, 18, 22 and 31.
They hold 32 span ranges. **7 of those ranges have whitespace at an edge:**

| Row | Column | Edge | Whitespace |
|---|---|---|---|
| 13 | underline | end | space |
| 13 | highlight | start | space |
| 13 | highlight | start | space (a second range) |
| 18 | underline | end | space |
| 18 | highlight | end | space |
| 22 | underline | end | space |
| 22 | highlight | end | space |

What this does and does not show:

- **Rows 18 and 22** are two of the three rows where the stopgap carried marks. Every edge flagged
  there is an *end* edge holding a space, which is the shape the bug leaves: a mark ending where
  Numbers had dropped a character takes that character back inside.
- **Row 31**, the third carried row, has no whitespace at any span edge.
- **Row 13** was not a carried row, so its whitespace edges came from the marks as they were
  written. The guide allows that: a space is marked when Word shows it underlined.
- A space at an edge is also correct wherever Word really underlines or highlights it. So this
  list says where to look, not what is wrong.

Per the review, the PR is opened anyway. Charlie checks rows 13, 18 and 22 in Word, and the PM
decides whether a label correction is needed.
