# Session report: v1-e39-t24-download-skips-the-header-page-and-names-its-pocket

| | |
|---|---|
| Task | `v1-e39-t24-download-skips-the-header-page-and-names-its-pocket` — A card or cart download skips the header page, and the student can name its pocket |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t24-download-skips-the-header-page-and-names-its-pocket.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t24-download-skips-the-header-page-and-names-its-pocket.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t24-download-skips-the-header-page-and-names-its-pocket` |
| Session status | COMPLETE |

## Summary

The count came first. Neither the data-use policy (version 1.19) nor ADR-0006 requires the "not
verified" notice in a downloaded file's text. They forbid presenting a card as verified, and they put
the "not platform-verified" label on the card page. So I built the change without stopping for the PM.

A card or cart download now starts at its pocket heading. The header analytic is left out through a
new `FileBuildRequest.header_line` option, which defaults to `True`. The download is the only caller
that sets it to `False`, so `files build` writes the same bytes it always did. A byte-pin test
recorded at the start commit holds this.

The student can type a pocket name beside **Download .docx** and beside **Download cart**. Whitespace
is collapsed and the name is put in NFC form. A blank name gives "Team evidence search". A name over
80 characters, or holding a Unicode `C`-category character, gets the download's own 400 message and
never a 500.

Every test was shown failing first. All eight mutants the PM listed or I added were caught, plus one
mutant in `app.js` caught by the browser test. The affected set (132 files) runs past two minutes, so
I leave it to the pull request's `ci` check, as agreement 10 says (details below). The PM should look
first at the title rules under Decisions.

## The count: is the "not verified" notice required in a downloaded file's text?

**No.** Each passage that bears on it, cited:

- **Use table, row 3** ([caselist-data-use.md:152](../policies/caselist-data-use.md)): "Cite kept
  verbatim, provenance in the file's sidecar (no line in the file's text since version 1.11), card
  marked `FILE_IMPORT`/unverified." This marks the card in the record: the sidecar's `provenance_mode:
  FILE_IMPORT`, whose schema refuses a verified card. It sets no sentence of text. It also governs
  built team files (E33). A pilot download carries no sidecar (v1-e33-t08, PM ruling 2026-10-22).
- **Prohibited use 5** (line 176) and **Attribution rule 4, "Never presented as verified"** (line 370):
  "no verified status, no badge, no implication that the platform checked the card against its source
  article". Both are prohibitions. A file without the header claims no verification. It shows the
  tag, cite and text copied from the disclosed file, exactly as Copy card already does with no notice
  (`debate_api/copy_card.py`, v1-e39-t11).
- **E39 gate, item 6** (line 605): "A student may copy or download a card for their own preparation;
  since version 1.11 it carries no provenance line, and its audit record names the card." There is no
  notice requirement, and the audit record still names every card.
- **E39 gate, item 7** (line 608): the label "Disclosed evidence, not platform-verified" goes "with
  every card page". It is placed on the page, which keeps it (`card.html`, unchanged).
- **ADR-0006** ([line 37](../adr/0006-exact-source-evidence-verification.md)): an UNVERIFIED card "is
  never presented as a finished evidence card". This rule governs the generation pipeline's cards,
  which are model-selected spans of an article. A `FILE_IMPORT` card is a separate provenance mode, and
  the policy explicitly lets students download one (gate item 6). Nothing in the download marks a card
  verified.

So the PM's three options (core properties, pocket line, policy amendment) were not needed, and I built.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `download-skips-the-header-page-and-names` (Download header and pocket) | Done | The count above, then tests red at d643a2e (commit `ce720a7`), the implementation (`751d887`), and the guide (`3630ad4`). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the policy counted and cited first; then a downloaded card and cart hold no header line, keep a pocket titled as the student asked or by default, and `files build`'s files are unchanged, by tests shown failing first | PASS | The count: section above. **Red** at d643a2e plus the new tests: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n 4 -q --tb=line -p no:randomly packages/debate_api/tests/test_card_download.py packages/debate_core/tests/integrations/docx_file_writer/test_writer.py "packages/debate_core/tests/application/test_file_build_service.py::test_a_build_writes_the_header_analytic_first_and_the_pocket_after_it"` → `31 failed, 116 passed`. Every failure is an assertion for the missing feature: the header is first (`'Disclosed ca...his platform.' == 'Team evidence search'`), the typed name is ignored, a refused name builds a file (`AssertionError: application/vnd...document`, 9 cases, after I made those tests check the status before decoding JSON), `FileBuildRequest` has no `header_line`, and the port's field list. The files-build guard test passed red and green, as a guard should. **Green**, same command → `147 passed in 2.64s`. |
| Node: Download header and pocket tests pass (`uv run pytest packages/debate_api/tests -k download`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run pytest packages/debate_api/tests -k download` → `154 passed in 7.66s`. |

What the tests hold:

- **No header, default pocket, typed pocket.** `test_download_of_one_card_holds_no_provenance_line_and_no_header_line`,
  `test_download_cart_has_no_header_line_and_keeps_the_default_pocket`, `test_download_keeps_the_pocket_the_student_typed[one-card|cart]`,
  and the existing camp-cart and drop-the-refused-card tests, whose expected paragraphs I updated (the
  header removed, the indices moved by one). Each test reads `word/document.xml` paragraph by paragraph
  against text I wrote by hand, and re-parses the file to check that the parser reads the pocket as
  each card's section.
- **Normalised titles** (10 cases): empty, spaces, other whitespace (U+3000, tab, newline), runs of
  whitespace, U+2028, a decomposed accent (made NFC), markup kept as literal text, curly quotes and
  dash and a symbol, exactly 80, and 80 inside spaces.
- **Refused titles** (9 cases): 81 characters, NUL, BEL, DEL, U+202E right-to-left override, U+200B
  zero-width space, U+00AD soft hyphen, U+E000 private use, U+FFFF noncharacter. Each gets `400` with
  the form's message, nothing built, no source read, no audit record. Also a `pocket` field sent twice
  is refused unread. The longest cart (30 references) with an 80-character name of four-byte characters
  fits the 4,096-byte body limit (it is read, and refused for its size).
- **Pages.** The card page and the cart bar each have a `<label for>`, an `<input maxlength="80">`
  with `aria-describedby` pointing at a `.help` line stating the limit and the default, placed before
  its button. This is the search form's pattern. In Chromium (`-m slow`),
  `test_a_download_and_the_cart_give_the_file_the_pocket_name_typed_beside_them_by_keyboard` runs at
  all three sizes: it types a name by keyboard, downloads, checks the file, sees a refused name's
  message, and downloads the cart with a blank name. Each page has no serious or critical axe
  violation and no horizontal scroll. Command: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n 4 -q -m slow packages/debate_api/tests/browser` → `26 passed in 11.83s`.
- **`files build` unchanged.** `test_deterministic_a_files_build_writes_the_bytes_it_wrote_before_the_downloads_option`
  pins the standard file's docx SHA-256 `a6d29712…602c97` (3,390 bytes) and its `word/document.xml`
  SHA-256 `1f49d8ea…732de6`. I recorded both at d643a2e, before any code change, with a scratch script
  that ran the test's own `standard` fixture. Its paragraphs were already written out by hand in
  `test_assembly_writes_the_recipe_in_order_in_the_profiles_styles`, unchanged.
  `test_a_build_writes_the_header_analytic_first_and_the_pocket_after_it` (in
  `test_file_build_service.py`) holds the header through `FileBuildService`, the path `files build`
  takes. `test_assembly_without_the_header_line_starts_at_the_first_pocket_and_reads_back` shows the
  writer's option leaves everything else as it was.

### Mutants (agreement 8)

Each run had a new, empty `HYPOTHESIS_STORAGE_DIRECTORY` (none of these tests uses Hypothesis). Each
mutant was applied to the committed code and restored with `git checkout HEAD --`, and `git status`
was clean afterwards. Every catch failed at an assertion. None errored at collection. Runs covered
`test_card_download.py`, `test_writer.py` and `test_file_build_service.py` (179 tests), except mutant
7, which ran against the browser test.

| Mutant | Result |
|---|---|
| 1. The header kept (`card_download` asks for `header_line=True`) | Caught: 18 failed (`'Disclosed ca...his platform.' == <pocket>`) |
| 2. The pocket dropped (the writer skips the pocket heading when there is no header) | Caught: 19 failed (`'Downloaded cards' == <pocket>`, plus the writer's own header-off test) |
| 3. The typed title ignored (the recipe always gets the default) | Caught: 9 failed (`'Team evidence search' == 'Aff answers to the K'` …) |
| 4a. The option leaking into `files build` (default `header_line=False`) | Caught: 9 failed, including the byte pin (`'42d369f2…' == '1f49d8ea…'`) and the service test |
| 4b. The option leaking into `files build` (`FileBuildService` passes `header_line=False`) | Caught: 1 failed, the service test. The byte pin cannot see this one, which is why the service test exists. |
| 5. Length limit off | Caught: 1 failed (`eighty-one-characters` built a file) |
| 6. Character check off | Caught: 8 failed. DEL, U+202E, U+200B, U+00AD and U+E000 built a file holding the character. NUL, BEL and U+FFFF raised lxml's `ValueError: All strings must be XML compatible` inside the request, which is the 500 the check exists to prevent. |
| 7. `app.js` never sends `pocket` (browser test, `-m slow`) | Caught: 3 failed, one per size (`['Team eviden…'] == ['Neg answers…']`) |
| 8. The route drops the `pocket` field | Caught: 18 failed |

### Before the report (agreement 10)

| Check | Result |
|---|---|
| `uv run scripts/affected_tests.py` | 132 of 595 test files, from 17 changed files |
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run` | Stopped at its 115-second limit with the run at 50% and no failure in that half (exit 124). It is over two minutes, so I leave it to the pull request's `ci` check, which runs the same set (the PM's ruling of 2026-10-19). |
| Changed areas + always-run list: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n auto -q -m "not slow and not live" tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py packages/debate_api/tests packages/debate_core/tests/integrations/docx_file_writer packages/debate_core/tests/application/test_file_build_service.py packages/debate_core/tests/application/test_file_publish_service.py packages/debate_core/tests/application/test_file_quality_mutations.py packages/debate_cli/tests/commands/test_files.py packages/debate_cli/tests/commands/test_doctor.py packages/debate_cli/tests/test_installation.py` | `1813 passed in 43.83s` (load average near 15 from another session) |
| Earlier, the changed areas' directories: `... -m "not slow and not live" packages/debate_api/tests packages/debate_core/tests/integrations/docx_file_writer packages/debate_core/tests/application/test_file_build_service.py` | `1274 passed in 10.04s` |
| `uv run --frozen ruff format --check .` / `ruff check .` | `1663 files already formatted` / `All checks passed!` |
| `uv run pyright packages/debate_api packages/debate_core` | `0 errors, 0 warnings, 0 informations` (835 files checked) |
| `uv run --frozen lint-imports` | `Contracts: 19 kept, 0 broken.` |
| `check_thin_handlers.py`, `check_links.py`, `docs_index.py --check-descriptions`, `check_command_blocks.py` | All OK (68 handlers within 25 statements; 3,093 links; 60 descriptions; 602 blocks) |
| `uv run scripts/validate_specs.py` | `OK: 530 files, 41 epics, 467 tasks, 22 releases` |

## Files changed

- **`debate_core.application`**
  - `ports/evidence_file_writer.py`: `FileBuildRequest.header_line: bool = True`, with the reason.
  - `card_download.py`: `pocket_title`, `UnreadablePocket`, `DOWNLOAD_POCKET_DEFAULT`,
    `DOWNLOAD_POCKET_MAX_LENGTH` and `DownloadRefusal.UNREADABLE_POCKET`. `download()` takes the
    typed name. `_build` asks for `header_line=False` and `_resolved` titles the pocket.
- **`debate_core.integrations.docx_file_writer/writer.py`**: `_assemble` writes `header_line(...)` only
  when the request asks. The pocket, hat and block headings are written either way.
- **`debate_api`**
  - `download.py`: reads `pocket` beside `cards`. Either field twice is refused unread. The pocket
    refusal's message is a 400.
  - `pages.py`: the templates get the default and the limit.
  - `card.html`, `base.html`: the labelled field.
  - `app.css`: its row.
  - `app.js`: sends the field when it is not blank.
- **Tests** (extended, not rewritten):
  - `test_card_download.py`: the pocket section, plus the header expectations updated.
  - The API `conftest.py`: `download(pocket=...)`.
  - `test_writer.py`: header off, the byte pin, and the port's field list now three.
  - `test_file_build_service.py`: one header test.
  - The Chromium suite: one keyboard test.
- **`docs/guides/evidence-search-accounts.md`**: "Downloading cards", the student-facing sentence.

## Deviations from the spec

None.

## Decisions and assumptions

- **Where the option lives.** It is a field on `FileBuildRequest`, the writer's input, and read where
  `header_line` is called (`_assemble`), not a constructor argument. That keeps the rule in the
  download service (`debate_core`), not in the API's composition root, and the test world's writer is
  covered without extra wiring. I extended the port's pinned field list in
  `test_assembly_takes_no_card_text_through_its_api` with the reason: a `bool` holds no card text.
  `FILE_BUILDER_VERSION` is not bumped. Its rule is "bumped whenever the bytes a recipe builds to
  change", and a recipe's bytes do not change. The headerless build exists only in a download, whose
  sidecar is never kept.
- **The title rules.**
  - Up to **80 characters** (code points), after collapsing whitespace. A pocket heading is a few
    words; the recipe allows 200 for a coach's heading.
  - **Any run of whitespace** (`str.split`, which includes tab, newline, U+2028 and U+3000) becomes
    one space, and the ends are trimmed.
  - The name is put in **NFC**.
  - **Blank or absent** gives "Team evidence search".
  - **Refused**: anything over the limit, and any character of Unicode's `C` categories (control,
    format, surrogate, private use, unassigned). The response is the download's own `400` message,
    which `app.js` shows where the download's status goes.
  - I chose refusing over silently falling back. A name replaced without a word would surprise the
    student, and the browser's `maxlength` already stops over-long typing.
  - The `C` rule also refuses a zero-width joiner, so an emoji sequence joined by one (a family emoji)
    is refused. Single emoji are allowed.
  - The browser's `maxlength` counts UTF-16 units, so in the field a name of astral characters stops
    at 40 of them. The server allows 80.
- **What the writer already escapes.** It writes a heading as one run's text through lxml, which
  escapes `<`, `>` and `&` (the `markup-written-as-text` case reads back literally). lxml refuses
  XML-incompatible characters with a `ValueError`. Without the character check, that `ValueError` was
  the 500 (mutant 6). There is no school or team-code check on the name, per the spec: it is the
  student's own text in their own file, and neither the audit record nor any log holds it.
- **Smoke checks.** None changed. The route and its path are the same, and dev's pilot smoke checks
  (v1-e39-t10, just merged) are unauthenticated and never fetch a download. The behaviour is held by
  the in-process tests and the Chromium suite.
- **`create_app` and `app_logging.py`** are untouched, as the PM asked. The limits reach the templates
  through `PageRenderer`, not through `create_app`.
- Before measuring, I compared this spec with the local `origin/dev` (7418356, fetched 2026-10-31
  17:06). Only the phase differed. Dev has not changed any file this branch changes.

## Operator follow-ups

None. Per the PM's ruling of 2026-10-19, the affected set is the pull request's `ci` check's job, not
a hand-off. If the operator wants to see the new download in Word with Verbatim, as in v1-e39-t08's
ac4, it is optional and not a criterion of this task.

## Follow-up work

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
