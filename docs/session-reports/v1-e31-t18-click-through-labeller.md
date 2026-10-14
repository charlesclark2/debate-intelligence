# Session report: v1-e31-t18-click-through-labeller

| | |
|---|---|
| Task | `v1-e31-t18-click-through-labeller` — The parser evaluation's labels are corrected one keypress per row, in a local page |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t18-click-through-labeller.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t18-click-through-labeller.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t18-click-through-labeller` |
| Session status | COMPLETE |

## Summary

`scripts/prelabel_docx.py label <prefix> --out-dir <folder>` serves a page on `127.0.0.1` at a free
port and prints only its address. The page shows one sampled paragraph at a time, rendered with its
formatting, beside the pre-label, and takes one key per row. When the last row is checked it writes
the worksheet `check` and `import` already take, and `import` keeps every guarantee it had. The
labeller adds no check of its own; it only runs `check`'s own checks on what it wrote, to show them
on the page. The underline and highlight on a span row are read from the document's XML by a new
renderer (`tests/evals/parser/docx_render.py`) that imports nothing from the parser. A row where
that reading and the pre-label differ is flagged, and what is written is the document's reading.

Also built: `label --blind` and `import --labeled-blind`, an optional `labeled_blind` field, a
*Labeled blind* section in the evaluation report, and the regeneration step for pre-labels. The
labeling guide and v1-e31-t05's follow-ups are rewritten around the labeller, with Numbers as the
fallback. The Goal is set to `Succeeded`: every criterion passed in this session, and none needs
a device, a credential or a merge.

**For the PM to look at first:**

1. **Deviation 1:** `import` gained one flag, `--labeled-blind`, although ac3 says "no change to
   either". It records ac5's field and checks nothing.
2. **Deviation 3:** the blind comparison groups files by category and template family, not by the
   selection's five-field stratum.
3. **Decision on re-derived cards:** a row stays checked when a key on another row changes which
   card it belongs to.
4. **The mutation run:** 52 mutants. The first run caught 49; all three misses were weak tests.
   After strengthening them, 52 of 52 were caught, each from an empty Hypothesis database.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `click-through-labeller` | DONE | The page, its keys and progress, the worksheet it writes, the span renderer, the blind mode, the pre-label regeneration and the guide. The node criterion passes (below). |

## Acceptance criteria

Every command ran from the task worktree on 2026-10-14.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — `label` serves on 127.0.0.1 at a free port and prints only its address; one row at a time with its formatting, two paragraphs either side, its block, the pre-label, rows done and left; keys for accept, each of the nine units, new card, completeness and back; card numbers from the card starts, a card cut off by a block's end unnumbered; each key tested through the handler without a socket | PASS | `uv run pytest tests/evals/parser/test_labeller.py` → `59 passed`. The page: `test_the_page_shows_the_row_its_neighbours_its_block_its_pre_label_and_the_count`, `test_a_paragraph_is_rendered_with_its_heading_bold_underline_and_highlight`. The keys, each through `LabellerApp.handle`: `test_accept_keeps_the_label_shown…` (Enter, Space), `test_a_unit_key_sets_that_unit…` (all nine, and an upper-case one), `test_the_new_card_key…`, `test_the_completeness_key_cycles…`, `test_back_moves…`, `test_an_unknown_key_changes_nothing`. Cards, written from the guide's rules: `test_card_membership_follows_the_guide` (10 layouts), `test_a_card_never_crosses_a_block_edge`, `test_a_card_cut_off_by_the_end_of_a_block_is_left_unnumbered`, `test_cut_is_offered_only_for_the_first_and_last_card_of_a_block`. Address and binding: `test_the_server_binds_loopback_at_a_free_port_and_prints_only_its_address` (a fake server records `("127.0.0.1", 0)`; stdout is exactly the address). Also a live run on the invented file ([below](#live-smoke-run-on-the-invented-file)). |
| **ac2** — a row checked only by a key on it; progress saved outside the repository after every key; resumes with checked rows shown checked; refuses a progress directory inside the repository | PASS | `test_each_key_checks_at_most_the_row_it_was_pressed_on`: a Hypothesis property over random key sequences in both modes, 150 examples ([what it generates](#mutation-run)). `test_a_key_sent_for_a_row_the_page_is_not_on_changes_nothing`, and `test_the_handler_has_no_route_that_checks_more_than_one_row` (the routes are exactly four; `/accept-all`, `/accept-block`, `/accept-file` → 404). `test_progress_is_saved_after_every_key_and_holds_no_text`, `test_the_labeller_resumes_where_it_stopped_with_the_checked_rows_shown_checked`, `test_a_progress_directory_inside_the_repository_is_refused` (the function and the command line; nothing is created). |
| **ac3** — when the last row is checked it writes a worksheet that `check` passes and `import` turns into a CORRECTED label file, unchanged; end to end on the invented file: pre-label, every row by keys (some accepted, some changed, one new card, one completeness), write, check, import; the label file holds exactly what the keys said | PASS | `test_label_every_row_by_keys_then_check_and_import_take_the_worksheet_unchanged`, run twice: once with the pre-label shown and once blind. It runs the `prelabel` command, then 15 keys (18 blind), and checks the worksheet is written. Then the real `check` command (`ready to import; 11 rows checked, 4 labeled differently`) and the real `import` command. The label file must equal one written by hand from the keys: units, cards 0 and 2, FULL and ABBREVIATED, the spans read from `synthetic.py`'s markup, `rows_changed_from_prelabel` 4. The labeller writes a worksheet with a problem and `check`'s own words name it: `test_a_worksheet_the_page_wrote_with_a_problem_is_named_by_checks_own_words`. |
| **ac4** — on a span row, the document's underline and highlight, from the labeller's renderer, which shares no code with the parser's run reading, beside the pre-label's marks, with a disagreement flagged; direct and style-inherited formatting read, by test on an invented document; a disagreement flagged, by test | PASS | `uv run pytest tests/evals/parser/test_docx_render.py` → `10 passed`. Direct: `test_direct_underline_and_highlight_are_read`. Inherited: `test_underline_and_highlight_inherited_from_a_style_are_read` (a character style's `w:u` and a paragraph style's `w:highlight`, through `w:basedOn`) and `test_the_default_paragraph_style_and_document_defaults_apply…`. `w:val="none"`: `test_direct_formatting_switches_off…`. No shared code: `test_the_renderer_shares_no_code_with_the_parsers_run_reading` (AST: no `debate_core` or `tests.` import). Same paragraphs as the parser: `test_the_renderer_finds_the_same_paragraphs_and_text_as_the_parser`, over tables, a text box written twice, tracked changes, tabs, breaks and a content control. A real disagreement: `test_a_highlight_the_document_inherits_and_the_parser_does_not_read_is_flagged_and_written`. That invented document has the synthetic file's direct marks plus a yellow highlight every run inherits from the document defaults. The parser reads neither, every sampled row is flagged, and the worksheet carries the document's highlight. |
| **ac5** — blind mode hides the pre-label and records `labeled_blind`; an added, optional field, and label files written before it still validate; the guide asks the coach to label one PR-subset file blind; the report lists the blind files and, for each, its rows differing from its pre-label beside the same figure for the other files of its stratum | PASS | Blind mode: `test_blind_mode_sends_no_pre_label_to_the_page` checks the JSON the page receives, not just what it shows. `test_blind_mode_will_not_accept_a_row_with_no_unit`, `test_a_file_started_in_one_mode_is_not_resumed_in_the_other`, and the blind end-to-end run above, imported with `--labeled-blind`. The field: `test_every_committed_label_file_reads_as_not_blind_and_rewrites_to_the_same_bytes`, over all 30 committed files (28 PRELABELED, 2 CORRECTED). Each loads, reads as not blind, and re-serialises to exactly its committed bytes. `test_every_committed_label_file_is_valid_and_listed` still passes, unchanged. Also `test_a_file_labeled_blind_says_so…` and `test_a_pre_label_cannot_claim_to_have_been_labeled_blind`. The guide: step 5. The report: `uv run pytest tests/evals/parser/test_blind_labeling.py` → `5 passed`, with figures worked by hand. `test_a_blind_label_file_changes_no_metric_and_not_the_gate` runs the evaluation with and without a blind label file: the reports are identical apart from the new key. |
| **ac6** — the regeneration command for every PRELABELED file, under the committed plan, given as an operator follow-up with its worksheets; CORRECTED and COACH_REVIEWED left alone, by test; the plan id unchanged | PASS | [Operator follow-up 2](#operator-follow-ups). `uv run pytest tests/evals/parser/test_prelabel_regeneration.py` → `7 passed`. `test_regeneration_rewrites_only_prelabeled_files_and_keeps_the_plan` runs the three commands on three invented files (one PRELABELED from an "older parser", one CORRECTED, one COACH_REVIEWED). The corrected and reviewed files and `sampling-plan.json` come through byte for byte, and every label file carries the plan id. The regenerated file has the current parser's version, and its worksheet is rewritten to the bytes `worksheet` writes. `test_a_worksheet_someone_has_started_is_kept_and_named` covers an edited CSV, a `.numbers` file and a file started in the page. `test_a_file_the_parser_now_reads_into_other_paragraphs_than_the_plan_is_left_alone` is [Deviation 2](#deviations-from-the-spec). |
| **ac7** — the guide and t05's operator follow-ups replaced by the labeller's steps (PR subset first, then the rest, the blind file, the spot-check, the baseline); the Numbers route the fallback; the page shows rows per minute | PASS | The guide's [working reference](../../tests/fixtures/debate_files/eval/labels/README.md#working-reference) runs: 2 regenerate, 3 PR subset first, 4 each file in the labeller, 5 one PR-subset file blind, 6 the finish, then *The fallback: a spreadsheet*. `test_the_guide_regenerates_then_labels_in_the_page_and_keeps_the_spreadsheet_as_the_fallback` pins the order and the commands. The t05 report has a dated, appended section; its earlier lines are byte-identical (`diff` against a copy taken first) and it gains no `**Verdict:**` line (7 before, 7 after). Pace: `test_the_page_shows_rows_per_minute`. Every block in both passes `zsh -n` (16 in the guide, 3 appended to t05) and `scripts/check_command_blocks.py`. |
| Node `click-through-labeller` — `uv run pytest tests/evals/parser` | PASS | `337 passed, 1 skipped in 2.91s`. The skip is the existing real PR-subset tier ("4 of 6 pr-subset files are not yet corrected by a person"). |

### Other checks

| Command | Result |
|---|---|
| `uptime`, then `uv run --frozen pytest -n auto -m "not slow and not live" --part 1/4` | load 5.17 / 8.63 / 12.44 → `1702 passed in 45.91s` |
| the same, `--part 2/4` | load 11.21 / 9.99 / 12.72 → `1710 passed, 1 xfailed in 39.62s` |
| the same, `--part 3/4` | load 13.40 / 10.75 / 12.87 → `1714 passed, 1 skipped, 1 warning in 41.61s` |
| the same, `--part 4/4` | load 25.36 / 14.94 / 14.33 → `1713 passed, 1 xfailed in 37.03s` |
| `uv run --frozen ruff format --check .` | `662 files already formatted` |
| `uv run --frozen ruff check .` | `All checks passed!` |
| `uv run --frozen pyright` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 12 kept, 0 broken.` |
| `uv run --frozen python scripts/check_command_blocks.py --base 15a3492` | `OK: no '#' comments in 265 shell code blocks in 114 Markdown files (1 session reports changed since 15a3492)` |
| `uv run scripts/validate_specs.py` | `OK: 348 files, 38 epics, 290 tasks, 20 releases` (after setting the phase) |

The four parts together are the whole default selection: 6,839 passed, 1 skipped, 2 xfailed. Both
xfails are an existing parser case in `test_cite_detection.py`. The skip is the real-corpus tier.

### Failing first

Each criterion's tests were written and run before its code. Where the code did not exist yet, the
run failed at collection, which shows nothing about the checks. The [mutation run](#mutation-run)
is that evidence. Commands below are `uv run --frozen pytest <file> -q -p no:randomly --no-cov -n0`.

| Tests | Run against | Result |
|---|---|---|
| `test_docx_render.py` | no renderer | `ModuleNotFoundError: No module named 'tests.evals.parser.docx_render'`, `1 error` |
| `test_labeller.py` | no labeller | `1 error during collection` |
| the three `labeled_blind` tests in `test_labels_schema.py` | the schema as committed (saved, `git checkout`, restored, `cmp` clean) | `3 failed`, each for its own reason: `AttributeError: 'FileLabelHeader' object has no attribute 'labeled_blind'`; `assert '"labeled_blind":true' in '{"record":"file",…}'`; `Expected regex: 'PRELABELED file has not been labeled'`, actual `labeled_blind  Extra inputs are not permitted` |
| `test_blind_labeling.py` | no `blind_comparison` | `1 error during collection` |
| `test_prelabel_regeneration.py` | `scripts/prelabel_docx.py` from `15a3492` (saved, swapped, restored, `git diff --quiet HEAD` clean) | `5 failed`: `AttributeError: module 'prelabel_docx' has no attribute 'worksheet_csv_bytes'` and `SystemExit: 2` (no `--remove-untouched`) |
| the paragraph-count refusal (13 planned, 12 read) | `prelabel` before Deviation 2 | `1 failed`: `ValueError: refusing to write an invalid label file: paragraph records must be exactly the 13 labeled indices…`, a traceback rather than a refusal. With 11 planned, the old command wrote the mismatched pre-label silently; mutant 45 below covers both directions. |

### Mutation run

Each mutant was applied to the committed source, and only its tests were run:
`pytest <files> -q -rf -p no:randomly -p no:cacheprovider -n0 --no-cov`, with
`HYPOTHESIS_STORAGE_DIRECTORY` set to a new, empty directory each time. The file was then restored
with `git checkout -- <file>`, and the runner asserted `git status --porcelain` was empty before the
next mutant and at the end. A run counts as a catch only when tests failed and nothing errored, and
none errored. The runner is in the session scratchpad, not the repository.

**First run: 49 of 52 caught.** All three misses were weak tests, and each test is now fixed
(`d0a55f8`):

| Mutant | Why it was missed | Test now |
|---|---|---|
| `n` also checks the row | No test pressed `n` on a row not yet checked | `test_the_new_card_key_starts_a_card_on_this_row_and_neither_checks_nor_moves` asserts `checked: False` after `n` |
| A paragraph the renderer reads differently still gets marks | No test gave the labeller a renderer reading that differs from the document | `test_a_paragraph_the_renderer_reads_differently_gets_no_marks_and_check_names_its_cells` |
| A blind file counts among its stratum's others | No stratum held two blind files | A second blind file in `team, verbatim`, worked by hand |

**Final run, against the final code: 52 of 52 caught**, each from an empty database, in under 5 s
per mutant:

| Behaviour | Mutants | Caught |
|---|---|---|
| Key handling | accept and unit keys do not move on; a unit key keeps the unit shown; `n` checks the row; `k` checks the row; back does not move; back checks the row it leaves; a key for a row the page is not on is applied; accept checks a row with no unit; `k` never offers cut off; `k` offers cut off mid-block | 10 / 10 |
| Card numbering | an unmarked TAG joins the open card; a heading or ANALYTIC does not end a card; no cut at the last EVIDENCE; a card runs across a block edge; a start on any unit starts a card; a cut-off card is numbered; a card's pre-label number is not kept; a blank row joins a card | 8 / 8 |
| One row per key | a key checks the next row too; a key checks every row; moving to a row checks it; an `/accept-all` route | 4 / 4 |
| Span comparison and renderer | a disagreement never flagged; only underline compared; the worksheet carries the pre-label's underline; a misread paragraph gets marks; the renderer ignores character styles / paragraph styles / document defaults / `u none` / the default paragraph style | 9 / 9 |
| Progress and its directory | a progress folder inside the repository allowed; only the repository root refused; progress not saved after a key; a blind file resumed shown; a shown file resumed blind; progress from other pre-labels resumed | 6 / 6 |
| Blind mode, page, regeneration, schema, report | the pre-label or its marks sent in blind mode; any `Host` answered; no token needed; `prelabel` overwrites a COACH_REVIEWED file; `--remove-untouched` removes an edited worksheet, or ignores a `.numbers` file or a started page; `prelabel` writes a file that no longer fits the plan; the labeller writes over a spreadsheet's worksheet, or labels a file on the Numbers route; `import` drops `labeled_blind`; `labeled_blind` always written; a blind file among its stratum's others; the stratum ignores the family | 15 / 15 |

The mutants the property catches ("a key checks the next row too", "a key checks every row") are
also caught by four example tests each. **What the property generates**
(`--hypothesis-show-statistics`, 150 examples, empty database): 50.89% blind and 37.87% with the
pre-label shown. 51.48% of sequences check four or more rows, 28.40% one to three, and 8.88% none.

### Live smoke run on the invented file

This is not a test, because sockets are blocked in the suite. It covers the one part no test
reaches: the real `HTTPServer` and the handler class. Everything was in the session scratchpad,
with `DEBATE_PARSER_EVAL_KEY_FILE` and `DEBATE_PARSER_EVAL_PATHS` pointing there, so the
operator's data directory was never read.

- `prelabel` → `11 of 11 paragraphs labeled …`.
- `label … --no-browser`: stdout was exactly `http://127.0.0.1:52719/`; stderr was empty, before
  and after requests; `lsof` showed it listening on `127.0.0.1:52719` only.
- The page's response carries `Content-Security-Policy: default-src 'none'; script-src
  'nonce-…'; …; connect-src 'self'; …`.
- `/state` without the token → `403`; with `Host: rebound.example` → `403`.
- With the token: the state at row 0, then a POSTed Enter → row 1, row 0 `POCKET` checked, and
  the progress file written.
- In headless Chrome (a throwaway profile, background networking off), the page rendered the
  header, the counts, the label, the pre-label and four paragraphs.
- Driven over the DevTools protocol: `t` set the row's unit and moved on; Enter accepted the next
  row (shown as `starts card 1 · FULL`); Backspace went back to a row shown as `checked`.
- `node --check` on the page's script: syntax OK.

## Files changed

- **`tests/evals/parser/docx_render.py`** (new): the labeller's own reader of paragraphs, text and
  formatting. It uses stdlib `zipfile` and its own lxml parser, with no parser code.
- **`tests/evals/parser/labeller.py`** (new) and **`labeller_page.html`** (new): the session (rows,
  keys, cards, progress) and the worksheet it writes. Also the request handler (`LabellerApp.handle`,
  socket-free) and the thin `http.server` shell. The page is one inline file.
- **`scripts/prelabel_docx.py`**:
  - new: the `label` subcommand, `labeller_for()`, `import --labeled-blind` and
    `worksheet --all --remove-untouched`;
  - `worksheet_csv_bytes()` factored out of `write_worksheet()` (its output is unchanged);
  - `prelabel` refuses a file that no longer fits the plan;
  - the docstring describes `label`.
- **`tests/evals/parser/labels_schema.py`**: `FileLabelHeader.labeled_blind`, optional, and written
  only when true.
- **`tests/evals/parser/metrics.py`** and **`corpus.py`**: `blind_comparison()`, the report's
  `blind_labeling` key and its Markdown section. No metric and no gate changed.
- **`tests/evals/parser/synthetic.py`**: an optional `styles_xml` for `build_synthetic_file`. The
  default file and its digest are unchanged.
- **Tests:**
  - new: `test_docx_render.py` (10), `test_labeller.py` (59), `test_blind_labeling.py` (5) and
    `test_prelabel_regeneration.py` (7);
  - `test_labels_schema.py` (+3);
  - `test_prelabel.py`: the guide test now reads the fallback section, since the loop it pins
    moved there.
- **`tests/fixtures/debate_files/eval/labels/README.md`**: the working reference, rewritten around
  the labeller. The generated PR-subset table and the units, cards, conventions and spans sections
  are unchanged.
- **`docs/session-reports/v1-e31-t05-parser-eval.md`**: one appended, dated section (ac7).
- **`plan_specs/…/t18-click-through-labeller.yaml`**: phase `Succeeded`.

`pyproject.toml` and `uv.lock` are unchanged: there is no new dependency, and nothing in
`packages/` changed.

## Deviations from the spec

1. **`import` gained one flag, `--labeled-blind`.** ac3 says the labeller's worksheet goes through
   `check` and `import` "with no change to either". That holds: the shown-mode end-to-end test
   imports it with the command line as it was. But ac5 needs `labeled_blind` on the label file, and
   `import` is what writes the label file. The flag records the claim as given, the way
   `--corrected-by` does, and adds no check; refusing it without proof would be a new check. The
   page prints the import command with the flag when the session was blind.
2. **`prelabel` refuses a file the current parser reads into a different number of paragraphs than
   the plan has.** ac6 regenerates "under the committed sampling plan", and the plan's paragraph
   counts were taken with the older parser. Before this change, a file the parser now reads longer
   than planned got a mismatched pre-label written silently, and one it reads shorter crashed with
   a traceback. Now the file is named with both counts, its label file is left as it was, and the
   command exits 1. This is in `prelabel`, not in `import` or `check`. Whether any real file is
   affected is unknown until the operator runs follow-up 2 (see Follow-up work).
3. **"Its stratum", for the blind comparison, is category and template family.** The selection's
   stratum (`stratum_of`) also has season, format and PR-subset membership. Under it, the two
   PR-subset team files are each alone in their stratum, so a blind file there would have nothing
   to be compared with. Under category and family every PR-subset file has 1 to 5 others. If the
   PM prefers another grouping, it is the one function `_stratum` in `metrics.py`.
4. **The Markdown evaluation report now names files.** Its rule was aggregates only. ac5 asks it to
   list the blind files, so they are named by 16-character digest prefix, as `MANIFEST.md` names
   them. Nothing else in it names a file.

## Decisions and assumptions

**Keys.**

- Letters `p h b t c e a u o` set the units: each unit's initial, and no two collide.
- `n` and `k` change a card and stay on the row without checking it. The page tells the person to
  accept or set the unit next.
- The page ignores auto-repeat (`event.repeat`), so holding Enter checks one row, not a run.
- It sends one key at a time, and each key names the row it was pressed on. The server ignores a
  key for any other row.

**A row stays checked when a key elsewhere re-derives its card.** Card membership is derived from
the starts, so pressing `n` on row 5 can move rows 6 to 9 into a different card. Those rows were
checked by keys pressed on them. The change to their card came from a key a person pressed
deliberately, and the page shows the new card on each row. Unchecking them would keep "checked"
meaning "this exact label was seen". The cost is going back over rows nobody needs to change. The
PM may prefer that rule; it is a few lines in `Session.press`.

**Cards are derived by the guide's rules, one block at a time.**

- A start counts only on a TAG or a CITE.
- A card runs to its last EVIDENCE row, or to its last CITE if it has no body.
- A heading, an ANALYTIC, a TAG not marked as a start, the next start and the block's edge each end
  it. A blank row inside it is skipped.
- *Cut off by the block's edge* is the last step of the `k` cycle, offered only for a block's first
  and last card, because only those can be cut. Any key then answers the guide's hardest rule.
- Rows the rules leave unnumbered get a note under the label. These notes are advice: `check`
  decides.

**Card numbers.** The page shows a card's place in the file. The worksheet keeps the pre-label's
number for a card starting where a pre-label card started, and gives the others numbers no
pre-label card uses. Otherwise `import`'s `rows_changed_from_prelabel` would count renumbering as
change, on every file and most of all on the blind one, which would spoil the ac5 comparison. The
written number is never shown, so blind mode gives nothing away.

**Span cells come from the renderer, never from the pre-label.** The page shows the document's
reading, rendered, and that is what a key confirms. If the renderer reads a paragraph's text
differently from the parser, its ranges would point at the wrong characters. So the page says it
cannot read that row's formatting, writes both cells empty, and `check` names them for the
spreadsheet route. Highlight means `w:highlight` in any colour; paragraph shading is not counted.
`w:u w:val="words"` underlines words and not the spaces between them, as Word shows it.

**The server.**

- It uses the standard library's single-threaded `HTTPServer`, so no dependency is needed.
- It answers only requests whose `Host` is `127.0.0.1:<port>`, which stops DNS rebinding.
- Every request but the page itself needs a token the page carries, which stops another tab
  sending keys.
- The Content-Security-Policy uses a nonce: no fonts, scripts, styles or images from anywhere, and
  `connect-src 'self'`. Responses are `no-store`.
- Request logging is off, so the address is the only thing printed. The browser opens unless
  `--no-browser` is given.

**Progress.**

- It is saved to `<prefix>.progress.json` beside the worksheet, written whole or not at all:
  units, starts, completeness and checked flags, and no text.
- It records a fingerprint of the pre-label file: a SHA-256 of the committed `.jsonl`, not of any
  corpus content.
- A session resumes only in the mode it started in, and only against the same pre-labels.

**What the labeller refuses to start on.**

- a file that is not `PRELABELED`;
- a plan id that does not match;
- a `.numbers` file in the folder;
- a worksheet that is neither as `worksheet` wrote it nor as the labeller wrote it, that is, one
  changed in a spreadsheet.

So the two routes never write over each other.

**`labeled_blind` is written only when true.** Every committed file, and every file that is not
blind, keeps exactly its bytes, including through `mark-reviewed`.

**No smoke check for `validate-dev`.** The labeller is an operator tool over the local corpus, in
the evaluation tooling, not a product surface (a CLI command of the platform, an API route, a web
page or a job). There is nothing on a validate-dev runner for it to reach.

## Operator follow-ups

These come in order and wait until this task's pull request has merged. The labeling itself is
human work, as before.

**1. Update the main clone** (seconds).

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
git switch dev
git pull
uv sync --all-packages
```

**2. Regenerate the pre-labels, once** (under a minute), in the main clone on `dev`. It covers
every file still `PRELABELED`, using the current parser (`2026.10.12-docx-3`; the committed
pre-labels were made by `2026.09.20-docx-1`) under the committed sampling plan.

```bash
uv run python scripts/prelabel_docx.py worksheet --all --remove-untouched --out-dir ~/parser-eval-worksheets &&
uv run python scripts/prelabel_docx.py prelabel --all &&
uv run python scripts/prelabel_docx.py worksheet --all --out-dir ~/parser-eval-worksheets &&
git status --short
```

Success looks like this:

- the first command ends `N untouched worksheet(s) removed, M kept`, and names each kept one;
- `prelabel` prints a line per file, with `already corrected; left alone` for the two corrected
  files and no `REFUSED` line;
- `git status` lists changed `.jsonl` files under `tests/fixtures/debate_files/eval/labels/` and
  nothing else.

A `REFUSED` line stops the chain: tell the PM, with the line. Otherwise commit through a pull
request, and `git pull` after it merges:

```bash
git switch -c "labels/regenerated-prelabels-$(date +%Y-%m-%d)"
git add tests/fixtures/debate_files/eval/labels
git commit -m "Parser evaluation: pre-labels regenerated with the current parser"
git push -u origin HEAD
gh pr create --base dev --fill
git switch dev
```

**3. Choose the blind file, then label the PR subset first.** The coach chooses one PR-subset file
still `PRELABELED`, from the table in the guide's step 3, without opening its pre-label or
worksheet. That file is labeled first, with `--blind` (the guide's step 5 has its blocks). Then the
other PR-subset files, then the rest.

**4. Start the page for one file.** Put the file's digest on the first line. The command prints
only the page's address and opens it.

```bash
f=PASTE_DIGEST_PREFIX_HERE
uv run python scripts/prelabel_docx.py label "${f}" --out-dir ~/parser-eval-worksheets
```

Answer every row with a key. When the page says every row is checked and `check` passes, press
Ctrl+C in that terminal, then:

```bash
uv run python scripts/prelabel_docx.py check "${f}" --worksheet ~/parser-eval-worksheets/${f}.csv &&
uv run python scripts/prelabel_docx.py import "${f}" --worksheet ~/parser-eval-worksheets/${f}.csv --corrected-by coach &&
rm ~/parser-eval-worksheets/${f}.csv ~/parser-eval-worksheets/${f}.progress.json &&
git switch -c "labels/${f}" &&
git add tests/fixtures/debate_files/eval/labels &&
git commit -m "Parser evaluation labels: ${f}" &&
git push -u origin HEAD &&
gh pr create --base dev --fill &&
git switch dev
```

Success looks like `ready to import`, then `CORRECTED by coach; N of M labeled rows changed from the
pre-labels`. **Report the rows per minute the page showed**: that is the real pace, and the PM has
none yet. A file the page refuses (it has a `.numbers` file or a spreadsheet-edited worksheet) goes
round the guide's fallback loop instead.

**5. The spot-check, the baseline and the health run** are unchanged: the guide's step 6. The
baseline's report now ends with *Labeled blind*.

## Follow-up work

- **For the PM, before follow-up 2:** a `REFUSED` line during regeneration would mean the parser's
  paragraph walk changed since the plan was made. That would also matter to the two CORRECTED
  files, because the evaluation checks each labeled paragraph's text against the current parser's
  reading (`validate_against_texts`), and a moved walk would fail them. The real tier runs only on
  the operator's machine, so nobody has measured this. The parser changes since then
  (`v1-e31-t09`, `v1-e31-t12`) were about classification, but I have not seen a real file under
  them.
- **For `v1-e31-t03` (a possibility, not a finding):** the parser reads highlight only where a run
  sets it (`classify_run`), so a highlight a file carries in a style is a span miss. The labeller
  flags exactly those rows. If many flagged rows on real files turn out to be style-inherited
  highlight, it is a parser fix with a version bump.
- **For whoever owns the pyright configuration (`v1-e01-t03`):** `[tool.pyright] include` is
  `["packages"]`, so neither `tests/` nor `scripts/` is type-checked in CI. Run over
  `tests/evals/parser`, pyright reports errors in files this task did not touch (`test_metrics.py`,
  `test_prelabel.py`, `worksheets.py`). The new modules here are clean apart from the `sys.path`
  import of `prelabel_docx`, which every test of that script shares.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-14

**Notes:**

Accepted in full, with the phase `Succeeded`. I have amended ac3 in this branch for Deviation 1,
and added two sentences to the guide's "Spans" paragraph (below).

**This is the task that takes the parser evaluation off the operator's evenings.** Every
guarantee `import` had is still in `import`; the labeller writes what `import` already takes. The
one-row-per-key rule is held by a property, by example tests and by the routes themselves (four,
with `/accept-all` and its kin a 404), and the server is shut to other tabs (token), other hosts
(`Host` check) and the network (CSP, nothing loaded).

**The work itself:**

* **The renderer shares no code with the parser,** checked by AST, and finds the same paragraphs
  over tables, text boxes, tracked changes and content controls. Its test with a document-default
  highlight is a real disagreement, and it is the kind your follow-up suspects the parser misses.
* **Card numbers keep the pre-label's where a card starts in the same place,** so renumbering is
  not counted as change. Without that, the blind comparison would have been spoiled.
* **The live smoke run** covered the one part no test reaches, the real server, including the
  `403`s.
* **The mutation run:** 52 mutants, 49 caught first, all three misses were weak tests, and 52 of
  52 after.

**Rulings:**

* **Deviation 1 (`import --labeled-blind`):** accepted. ac3 amended.
* **Deviation 2 (`prelabel` refuses a file that no longer fits the plan):** accepted. If the
  regeneration prints a `REFUSED` line, the operator stops and tells the PM, as follow-up 2 says.
* **Deviation 3 (the blind comparison's stratum is category and family):** accepted.
* **Deviation 4 (the report names blind files by keyed-digest prefix):** accepted. The digests
  are HMACs under the operator's key, so they are not a join key back to a file.
* **Decisions:** accepted, including a row staying checked when a deliberate card start elsewhere
  re-derives its card.
* **The span rows, one addition to the guide.** The page draws the labeller's own reading, so a
  key there confirms the renderer, not the document. Word is the independent check. I have made the
  guide say: on a flagged row, look at the paragraph in Word before accepting it, and if Word shows
  it differently, do not accept the row and tell the PM. The 0.99 span target is only worth
  something if a renderer fault cannot be confirmed by a keypress.

**Follow-up work:**

* **A `REFUSED` line, and the two CORRECTED files:** if the regeneration refuses any file, the PM
  rules before labeling starts, including whether the corrected files still validate.
* **Style-inherited highlight in the parser:** the operator reports how many rows each file
  flags. If they are many and they are style-inherited, the PM files a parser task with a version
  bump.
* **pyright over `tests/` and `scripts/`:** an E01 tooling task after the v1.0 tag.
