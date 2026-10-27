# Session report: v1-e06-t03-format-profiles

| | |
|---|---|
| Task | `v1-e06-t03-format-profiles` — Card format profiles from team conventions |
| Spec | [`plan_specs/v1/e06-card-cutting/t03-format-profiles.yaml`](../../plan_specs/v1/e06-card-cutting/t03-format-profiles.yaml) |
| Epic / release | `v1-e06-card-cutting` / `v1.3` |
| Branch | `task/v1-e06-t03-format-profiles` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Three format profiles now live in `config/format_profiles/`: `team-default`, `flow` and `plain`.
`team-default` is measured from the team's own files. `scripts/analyze_team_formatting.py` read
all 314 team files in the operator's 2024-2025, 2025-2026 and 2026-2027 folders, in place and
read-only, in 22 s. It read style and run formatting only: it removes every `w:t` before looking
at a file. The counts are in `docs/data/team-format-survey.md`, and each `team-default` value
cites the summary line it comes from. No team file is in the repository, per the PM's amendment
of 2026-10-26: `tests/fixtures/team_samples/MANIFEST.md` lists season, event and a 16-digit keyed
digest per file, and the tests run on a synthetic tree.

`FormatProfile` (`debate_core.evidence.format_profile`) names its base style profile and refuses:

* any key the style profile owns, or any key naming a style;
* an unknown base;
* a highlight colour the base does not read as a reading colour;
* sizes the base would read back wrongly.

All 77 new tests were shown red against a skeleton first. All 21 mutants were caught, including
the PM's three.

**The Goal is `Succeeded`.** The coach signed off on ac4 on 2026-10-27 with no value changed
(answers under Operator follow-ups). Two things to look at first:

* `flow` was a proposal, because the spec names it without defining it; the coach confirmed it.
* The spec's ac2 command fails as written (exit 2): under the amendment there is nothing in
  `tests/fixtures/team_samples` to analyse.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `curate-samples`: curate and scrub team sample files | Done as amended | No file copied or scrubbed (PM amendment). `MANIFEST.md` lists the 314 files read, written by the analysis script. The spec's named test, `tests/fixtures/test_team_samples_scrubbed.py`, now asserts the directory holds the manifest and nothing else. No `scripts/scrub_docx_samples.py`. |
| `analyze-formatting`: formatting analysis script | Done as amended | `scripts/analyze_team_formatting.py`. Run over the operator's folders, not over copies. Tested on `tests/fixtures/debate_files/team_format/`, written by `scripts/generate_team_format_fixtures.py`, and on the style profile's `verbatim-cut-card.docx`. |
| `profile-model`: FormatProfile model and loader | Done | `packages/debate_core/src/debate_core/evidence/format_profile.py`: `FormatProfile`, `CiteBlockLayout`, `ResolvedFormatProfile`, `load_format_profiles` / `load_format_profile` / `resolve_format_profile`. |
| `profile-configs`: team-default, flow and plain | Done | `team-default` from the survey. `plain` is `team-default` without highlighting. `flow` is a proposal (Decisions 5). |
| `coach-signoff` | Done | The coach answered the six checklist questions on 2026-10-27 and changed no value. Answers under Operator follow-ups. |

Red first: `51068ae` holds the tests with a skeleton that refuses nothing and measures nothing.
That run was 42 failed, 35 passed (new test files only, `-n 0 -p no:randomly`):

* **18 failed** with `DID NOT RAISE FormatProfileError`: style redefinitions, an unknown base,
  non-reading colours, and sizes the base would misread.
* **The rest failed** because the committed profiles, survey and manifest did not exist yet, or
  because the analysis measured, excluded, deduplicated and keyed nothing, kept `w:t`, and needed
  no key.
* **Passes:** valid input accepted, the base lookups and registry plumbing the skeleton kept,
  pydantic's own field bounds, size labels, tie-breaks, and the two no-text tests. The no-text
  tests pass vacuously against a skeleton that reads nothing; mutants pm2 and 6 below show they
  bite.

`7e0d241` installed the real code. The structural-units test expected 4 tags, but the fixture
descriptions give 2 + 1 + 2 = 5. I corrected the expectation from the descriptions; my sum was
wrong, not the code.

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: 6-10 scrubbed `.docx` copies in `tests/fixtures/team_samples/` with a MANIFEST of season, event and scrub date | FAIL as written / PASS as amended | The amendment makes it a manifest of files held elsewhere. `tests/fixtures/team_samples/` holds only `MANIFEST.md`: 314 rows of season, event and digest, written by the analysis (see Deviations 1). `uv run pytest tests/fixtures/test_team_samples_scrubbed.py` → `3 passed`. |
| ac2: the analysis script reports style names, heading levels, underline/bold/highlight and font sizes found in the samples | PASS as amended | The real run (below) wrote `docs/data/team-format-survey.md`: units with outline levels and published style ids, short- and full-cite sizes and bold, underlined and not-underlined sizes, highlight colours, bold evidence runs, by season. A second run to scratch was byte-identical to the committed survey and manifest. `tests/scripts/test_analyze_team_formatting.py` → `25 passed`. |
| ac3: FormatProfile names its base style profile and defines only cite layout, base size, highlight colour and condensed size; the three profiles validate and resolve | PASS | `uv run pytest packages/debate_core/tests/evidence/test_format_profile.py` → `49 passed`. Includes `test_the_committed_profiles_validate_and_resolve_against_the_shared_style_profile`, `test_the_card_default_names_a_committed_profile` and `test_every_team_default_value_cites_the_survey_line_it_comes_from`. |
| ac4: the coach signs off that team-default matches the team's Verbatim conventions | PASS | The coach's answers, relayed by the PM on 2026-10-27: (1) cyan is right; (2) 11 pt and 8 pt are right; (3) the full cite is not shrunk; (4) `flow` as proposed; (5) `plain` as proposed; (6) the Novice Packet stays included. No profile value changed. |
| Node `curate-samples`: Sample manifest exists | PASS | `tests/fixtures/team_samples/MANIFEST.md` exists. |
| Node `curate-samples`: Scrub check finds no author metadata in samples | PASS (the check now asserts there are no samples) | `uv run pytest tests/fixtures/test_team_samples_scrubbed.py` → `3 passed`. |
| Node `analyze-formatting`: Analysis runs over the samples | FAIL as written / PASS as amended | As written, `uv run scripts/analyze_team_formatting.py tests/fixtures/team_samples` prints `no .docx files to analyse below the inputs; nothing written` and exits 2. That is deliberate: an empty corpus is a failure, not an empty report. As amended, `uv run scripts/analyze_team_formatting.py tests/fixtures/debate_files/team_format --exclude-dir Opencaselist` exits 0 (`3 files read, 4 skipped`). |
| Node `profile-model`: Profile loader tests pass | PASS | `test_format_profile.py` → `49 passed`. |
| Node `profile-configs`: team-default profile exists, contentMatch `tag` | PASS | `config/format_profiles/team-default.yaml` exists; `grep -c tag` → 2. |
| Node `coach-signoff`: Coach approves team-default profile | PASS | As ac4. |

The real run, read-only, in place, under an alarm on the interpreter:

```bash
perl -e 'alarm 110; exec @ARGV' .venv/bin/python scripts/analyze_team_formatting.py ~/Documents/debate/2024-2025 ~/Documents/debate/2025-2026 ~/Documents/debate/2026-2027 --exclude-dir Opencaselist --exclude-dir "Camp Files" --output docs/data/team-format-survey.md --manifest tests/fixtures/team_samples/MANIFEST.md
```

It printed `314 files read, 2551 skipped`. It took 22.2 s of wall-clock time under a load average
of 19.

### Mutants

There were 21 mutants, each run with a fresh `HYPOTHESIS_STORAGE_DIRECTORY` (agreement 8; these
suites have no properties) against its covering test file. The tree was restored with
`git checkout` after each one, and `git status --porcelain` was clean after every batch. Every
mutant was caught by a test failing (exit 1), not by an error.

| Mutant | Caught by |
|---|---|
| **PM: a profile that redefines a style-profile style is accepted** (ownership check off and unknown keys ignored) | 11 failed: every `test_a_profile_that_defines_a_style_is_refused_and_told_who_owns_it` case, plus the unknown-key test |
| **PM: the analysis reads text** (`w:t` kept, and short-cite runs counted by their words) | 5 failed, including `test_the_same_formatting_over_other_words_measures_exactly_the_same` and `test_text_elements_are_gone_before_anything_looks_at_the_body` |
| **PM: an unknown base style profile resolves** (falls back to `verbatim`) | `test_an_unknown_base_style_profile_is_refused`, `test_one_bad_profile_fails_the_whole_directory` |
| ownership check off, `extra="forbid"` left in place | 10 failed (the message names the owner; pydantic's does not) |
| nested keys not searched | the `cite_block.short_cite_style_id` case |
| keys naming a style not recognised | the `tag_style`, `underline_style` and nested cases |
| `w:t` kept, nothing else changed | `test_text_elements_are_gone_before_anything_looks_at_the_body` |
| a non-reading colour accepted | the `magenta` and `lightGray` cases (3 failed) |
| condensed text at the shrink maximum refused | 20 failed |
| base size at the shrink maximum accepted | `test_a_base_size_the_base_would_read_as_shrunk_is_refused` |
| only the first disagreement reported | `test_every_disagreement_is_reported_at_once` |
| profile name not checked against its file | `test_a_profile_whose_name_is_not_its_file_name_is_refused` |
| excluded folders read | 6 failed |
| duplicates read twice | 8 failed |
| direct `w:u` ignored | `test_the_evidence`, the report test |
| run style chain skipped for size | 4 failed |
| an analytic does not end the card | 3 failed |
| condensed counted strictly below the shrink maximum | 3 failed |
| a short cite anywhere in the paragraph counts as leading | `test_the_cite_block`, the report test |
| custom style ids named | `test_a_style_id_nobody_published_is_counted_but_never_named` |
| manifest digest is a plain SHA-256 | `test_the_manifest_lists_season_event_and_a_keyed_digest_prefix_only` |

I deleted one check rather than test it. The model had a validator requiring condensed text to be
smaller than the base size. The two shrink checks in `resolve_format_profile` already imply it
(base size above the shrink maximum, condensed size at or below it), so no mutant could tell it
from its absence.

### Before the report

`uv run scripts/affected_tests.py` chose **199 of 539** test files. Most of the width is false
edges, the quoted-word pitfall:

* 37 files mention the word "flow", which is also `config/format_profiles/flow.yaml`.
* Others name `LD` or a season, which are parts of the fixture tree's paths.

At that size it is past two minutes, so under agreement 10 I did not run it and left the
selection to the PR's `ci`. I ran instead, each command under `perl -e 'alarm 115; exec @ARGV'
.venv/bin/python -m pytest -n auto -m "not slow and not live"`:

* `packages/debate_core/tests/evidence` (the changed module's directory) and my three test files,
  `tests/scripts/test_survey_docx_styles.py`, `tests/architecture`, `tests/specs` and the CLI
  wiring tests → **1922 passed** in 26 s.
* `tests/evals/parser/test_select_eval_files.py` (its module is imported), plus every docs,
  scripts and task test the selection chose for a reason other than a quoted word → **998 passed**
  in 44 s.
* The nine `debate_core` files the selection chose because they walk Python source → **355
  passed** in 7 s.

No stray pytest was left afterwards (`pgrep`).

| Check | Result |
|---|---|
| `uv run ruff format --check .` | `1503 files already formatted` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run --frozen pyright` | `0 errors, 0 warnings, 0 informations` |
| `uv run lint-imports` | `Contracts: 18 kept, 0 broken.` |
| `uv run scripts/validate_specs.py` | `OK: 478 files, 40 epics, 416 tasks, 22 releases` |
| `uv run --frozen python scripts/docs_index.py --check-descriptions` | `All 55 indexed documents under docs/ have a description` |
| `uv run python scripts/check_command_blocks.py` | `OK: no # comments in 505 shell code blocks in 186 Markdown files` |
| `uv run python scripts/check_thin_handlers.py` | `OK: 67 CLI command and API route handlers within 25 statements` |

## Files changed

* **`debate_core.evidence`**: `format_profile.py` (new). It holds the model, the base-profile
  checks, `ResolvedFormatProfile` with the style lookups t04 needs, and the registry. The model
  lives beside the loader, as the node's `outputs` name it. Nothing in `debate_core.domain`
  changed.
* **`config/format_profiles/`**: `team-default.yaml`, `flow.yaml`, `plain.yaml`.
* **`scripts/`**: `analyze_team_formatting.py` (the analysis and the manifest writer) and
  `generate_team_format_fixtures.py` (the synthetic tree, reusing
  `generate_style_fixtures.py`'s run builder and style table).
* **`docs/data/team-format-survey.md`**: the counts. New, with its docs-index line.
* **`tests/fixtures/team_samples/MANIFEST.md`**: the 314 files read, as season, event and digest.
* **`tests/fixtures/debate_files/team_format/`**: the synthetic tree (8 files, written by the
  generator with a fixed timestamp; a test checks they match it byte for byte).
* **Tests**: `packages/debate_core/tests/evidence/test_format_profile.py`,
  `tests/scripts/test_analyze_team_formatting.py`, `tests/fixtures/test_team_samples_scrubbed.py`.

## Deviations from the spec

1. **No team file, scrubbed or not (the PM's amendment of 2026-10-26).** ac1, the `curate-samples`
   node, its `scripts/scrub_docx_samples.py` output and the description's "copies are curated
   into tests/fixtures/team_samples/" no longer hold:
   * `team_samples/` holds a manifest of files held elsewhere;
   * the node's named test now asserts there is nothing else in it;
   * no scrub script was written.

   The first forbidden item, "Reading from ~/Documents/debate at test or run time (fixtures are
   committed, scrubbed copies)", holds for tests: no test reads those folders. The analysis
   script, by the amendment, does read them, as a one-off run on the operator's machine. The
   item's parenthetical is stale.
2. **The `analyze-formatting` node's command exits 2 as written.** It points at
   `tests/fixtures/team_samples`, which has no `.docx` by the amendment. I kept an empty input a
   failure rather than an empty report, so "nothing there" cannot pass as "nothing to report".
   Proposed replacement args:
   `[run, scripts/analyze_team_formatting.py, tests/fixtures/debate_files/team_format, --exclude-dir, Opencaselist]`.
3. **Paths outside `constraints.packages`.**
   * `scripts/`, `tests/scripts/` and `docs/data/` are pre-approved by the PM.
   * Not covered by that approval: `tests/fixtures/debate_files/team_format/` (the synthetic tree)
     and `tests/fixtures/test_team_samples_scrubbed.py` (the path the spec itself names).
4. **The spec text is unedited.** The PM's note says the packages arrive in the next batch, and
   earlier amendments landed through the PM's batch commits, so I left ac1, ac2, the two nodes
   and the forbidden item to the PM. The relay prompt below has the wording.

## Decisions and assumptions

1. **Every file, no sample.** 322 team files were in reach outside the excluded folders, and the
   whole run takes 22 s, so a sample would only add a seed to explain. The rule: every `.docx` below the
   three season folders, except:
   * Word lock files;
   * files under a folder named `Opencaselist` or `Camp Files` (other programs' files kept
     inside a season folder): 2,543, including 59 in 2025-26 `PFD/UK EU Topic/Opencaselist`;
   * byte-identical duplicates (3);
   * an unreadable package (1);
   * files whose folders name no event (4, among them `Practice Speech 10-6`).

   Season and event come from `scripts/select_eval_files.py`'s `infer_season`/`infer_format`,
   applied to the input folder and below, never the path above it.
2. **The manifest's digests are keyed with the parser evaluation's key.** I reused it through
   `tests/evals/parser/digests.py` rather than adding a second key. So a team file that is also in
   the evaluation manifest shows the same prefix in both. That joins two lists the operator owns
   and reveals nothing either did not. The script refuses `--manifest` without the key.
3. **Measured by position, without text.**
   * A cite is a paragraph with a run in the cite character style (or the cite paragraph style).
   * Evidence is the paragraphs after a cite, up to the next pocket, hat, block, tag or analytic.
     An undertag does not end a card.
   * Values resolve as Word resolves them: direct formatting, then the run style chain, then the
     paragraph style chain, then document defaults.
   * Counts are of runs, not characters, since characters would need the text. So each table
     also counts the files where a value is the most common, and the summary uses that.
4. **What a profile checks against its base.**
   * The condensed size must be one the base reads as shrunk (at or below `shrink.maximum_half_points`,
     16).
   * The base size must be one it does not.
   * The highlight colour must be a `reading_color`.

   Otherwise the parser would read a rendered card back differently from how it was cut.
   `ResolvedFormatProfile.paragraph_style_id(unit)` and `character_style_id(emphasis)` give t04
   its style names from the base, so no renderer code names a style.
5. **`flow` is a proposal.** Architecture §11 uses `--format flow` without defining it. I made it
   a reading copy: what is read keeps `team-default`'s size and colour, and what is not read
   shrinks one step further. Both values come from the survey's next-largest file group:
   * the full cite at 16 (8 pt), the most common full-cite size in 3 files;
   * unread text at 14 (7 pt), the most common in 15 files.

   If the team means something else by "flow" (tags and cites only, say), that is a different
   shape from what FormatProfile defines and needs the PM.
6. **`plain`** is `team-default` with `highlight_color: null`, which is all the spec says. It still
   condenses unread text.
7. **Organization names in the short cite (t02's follow-up 4).**
   * **Count: not taken, and not takeable under the rule.** Whether a short cite says "Federal
     Office of ... 26" or "... 26" is a fact about its words. The cite run's style is the same
     either way, and the survey reads no words. The survey says so in its own section.
   * **Can a profile option keep it whole: no.** The case is an *untyped* author string, which
     `Citation.authors_are_organizations` does not mark. A profile chooses presentation and has
     nothing to tell "Jane Smith" from "Federal Office of X". An option to keep first authors
     whole would print "Jane Smith 26" for every person.
   * **Recommendation:** no profile option. Typed organizations are already kept whole by t02. An
     untyped one is a citation-resolution question (`CitationService`, E06 t01/t02 territory),
     and a student can edit the short cite meanwhile.

## Operator follow-ups

**Coach sign-off (ac4), in the PR review.** Read `docs/data/team-format-survey.md` beside the
three files in `config/format_profiles/`, and check:

1. **Highlight.** `team-default` highlights cyan: the colour in 142 of 240 files with
   highlighting. Green leads in 68 files and yellow in 30. Is cyan the team's colour now, or a
   debater-by-debater choice that wants a `green` profile too?
2. **Sizes.** Read text at 11 pt (229 of 246 files). Unread text condensed to 8 pt (199 of 249;
   7 pt in 15, not condensed at all in 25). Right for cards the tool cuts?
3. **Cite block.** A bold short cite in the cite style (13 pt bold, from the style profile),
   then the full cite at 11 pt, not shrunk (192 of 247 files). Does the team shrink its full cite
   anywhere?
4. **`flow`.** What does `--format flow` mean to the team? The proposal is the reading copy in
   Decisions 5.
5. **`plain`.** No highlighting, unread text still condensed. Should plain also leave unread text
   full size?
6. **Which files counted.** The 2026-27 `Policy Debate/Novice Packet` folder (12 files) is
   included by the rule. If that packet came from elsewhere, say so and it can be excluded.

**The coach's answers (2026-10-27, relayed by the PM):**

1. Cyan is right.
2. 11 pt for read text and 8 pt for unread text are right.
3. The full cite is not shrunk: 11 pt stays.
4. `flow` as proposed.
5. `plain` as proposed: no highlighting, unread text still condensed.
6. The Novice Packet stays included.

No profile value changed, so the survey, the manifest and the three profiles stand as committed.

**Refreshing the survey later** (about 25 s, read-only). Run it in the task worktree; it rewrites
both committed files:

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e06-t03-format-profiles
uv run python scripts/analyze_team_formatting.py ~/Documents/debate/2024-2025 ~/Documents/debate/2025-2026 ~/Documents/debate/2026-2027 --exclude-dir Opencaselist --exclude-dir "Camp Files" --output docs/data/team-format-survey.md --manifest tests/fixtures/team_samples/MANIFEST.md
```

Success looks like `314 files read, 2551 skipped` until the folders change, and `git diff` on the
two files shows only the counts that moved. If `team-default`'s cited lines change, its comments
and values must change with them; `test_every_team_default_value_cites_the_survey_line_it_comes_from`
fails until they do.

### For the PM (relay prompt)

> v1-e06-t03 is done except ac4 (coach sign-off). Four things for you:
>
> 1. **Spec amendment, in the next batch.**
>    * ac1: "tests/fixtures/team_samples/MANIFEST.md lists the team files the profiles were
>      measured on, held on the operator's machine: season, event and a 16-hex-digit keyed digest
>      per file, nothing else."
>    * `curate-samples`: drop `scripts/scrub_docx_samples.py` from outputs; the named test now
>      asserts the directory holds only the manifest.
>    * `analyze-formatting` args: `[run, scripts/analyze_team_formatting.py,
>      tests/fixtures/debate_files/team_format, --exclude-dir, Opencaselist]`.
>    * The first forbidden item's parenthetical: "(tests use synthetic files; the analysis runs
>      in place on the operator's machine)".
>    * Packages: add `scripts`, `tests/scripts`, `docs/data`, `tests/fixtures/debate_files/team_format`.
> 2. **`flow`'s meaning.** I proposed a reading copy (full cite 8 pt, unread text 7 pt). The
>    coach's answer decides it. If they mean tags and cites only, that is a t04 rendering mode,
>    not a FormatProfile value. Recommendation: accept the proposal unless the coach names
>    something else.
> 3. **Organization short cites.** Recommendation: no profile option. A profile cannot tell an
>    untyped organization string from a person, and the survey cannot count it without reading
>    words. If you want it, it belongs in citation resolution, not here.
> 4. **affected_tests width.** The profile name `flow` and the fixture folders `LD`/season names
>    put 199 files in this branch's selection through quoted-word edges. Worth a look by whoever
>    owns `scripts/affected_tests.py`.

## Follow-up work

1. **`v1-e06-t04-docx-renderer`.** Take a `ResolvedFormatProfile` (from
   `load_format_profile(name, FORMAT_PROFILES_DIRECTORY)`). Style names come from
   `paragraph_style_id` and `character_style_id`; sizes and the colour come from `.profile`. The
   profile says nothing about bold in evidence. The survey counts 129,185 bold evidence runs
   without saying where the bold comes from; the style profile's `Emphasis` leaves bold
   inherited because templates split on it.
2. **t02's follow-up 4** (organization names) closes here with "no profile option"; see
   Decisions 7. If it is wanted, it is a `CitationService` change.
3. **`scripts/affected_tests.py` (`v1-e01`).** Quoted words in Python files (`"flow"`, `"LD"`,
   season strings) count as references to same-named path parts, which widened this branch's
   selection from a few dozen files to 199.
4. **The survey found 5,098 highlighted runs that are not underlined.** Highlighting outside the
   underlining is a convention the style profile's reading of highlights may want to know about
   (`v1-e31`).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-27

**Notes:**

Profiles measured from the team's own files without one of them entering the repository, and a
model that refuses anything the style profile owns.
1. **ac2, ac3 and the node criteria pass,** ac1 and the analysis node as amended.
   * The real run read 314 files in place, styles and run formatting only, with `w:t` removed
     first, in 22 s. A second run was byte-identical.
   * Each `team-default` value cites its survey line, held by a test.
   * Red first: 42 failed against a skeleton. The no-text passes are vacuous on a skeleton, and
     mutants pm2 and 6 show they bite.
2. **Mutants: 21, the PM's three among them.** The condensed-below-base validator, which no mutant
   could tell from its absence, was rightly deleted.
3. **Deviations 1 to 4 accepted.** The PM writes the amendment in the next batch, in the relay's
   wording:
   * ac1 and the `curate-samples` node;
   * the `analyze-formatting` args;
   * the forbidden item's parenthetical;
   * the packages (`scripts`, `tests/scripts`, `docs/data`, `tests/fixtures/debate_files/team_format`).
4. **Decisions accepted:**
   * every file by rule, with the exclusions counted;
   * the manifest keyed with the parser evaluation's key;
   * measurement by position, by runs, resolved as Word resolves;
   * the base checks (a condensed size the base reads as shrunk, a base size it does not, a
     reading colour);
   * `plain` as `team-default` without highlighting.
5. **`flow`** is accepted as the proposed reading copy unless the coach names something else.
6. **Organization short cites (t02's follow-up 4) close here with no profile option.** A profile
   cannot tell an untyped organization from a person, and the survey reads no words. A student can
   edit the short cite.
7. **Follow-ups:**
   * 3 (quoted words such as `"flow"` and `"LD"`) is covered by `v1-e01-t32`'s rule that a quoted
     string names a file only if it resolves to an existing path.
   * 4 (highlighted runs outside the underlining) is noted for E31 and not filed now.
   * 1 is t04's.
8. **ac4 is the coach's.** The coach's answers to the six checklist questions are recorded in this
   report by the session. Any value they change is applied with its survey line, and `flow` takes
   the coach's meaning.
   * If the coach's `flow` is not a FormatProfile shape (tags and cites only, say), `flow` stays as
     proposed and t04 gets a rendering mode by the PM's amendment.
9. **The affected set** (199 files, widened by quoted-word edges) is left to the PR's `ci` under
   agreement 10. The changed directories and the always-run list passed, and the static checks are
   clean.

No re-review is needed unless the coach's answers change a profile's shape. With them recorded, set
the Goal to `Succeeded`, and the PR merges in full.
