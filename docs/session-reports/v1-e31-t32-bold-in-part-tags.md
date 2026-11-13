# Session report: v1-e31-t32-bold-in-part-tags

| | |
|---|---|
| Task | `v1-e31-t32-bold-in-part-tags` — A tag with a word left unbolded, above a cite, counted before any rule |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t32-bold-in-part-tags.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t32-bold-in-part-tags.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t32-bold-in-part-tags` |
| Session status | PARTIAL: sample, counts, ruling, rule, version bump, tests, checks, the labelled evaluation and the before-and-after over the Mac's store are done. The re-parse's counts are the operator's after the merge (ac2's last part), so the Goal stays `InProgress` <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

t24's rule reads the line directly above a cite that opens a card with no tag as that card's tag only
when Word shows it bold throughout. This task looked at the lines it leaves that are bold in part.

**The work, in the PM's order:**

1. **The sample** (operator, seed 20261103, 30 items, formatting terms only). Of the 68 lines that
   fail t24's rule only by being bold in part: 18 tags, 4 not, 2 "part" (a tag, a bold short cite
   and a claim on one line). Lines unbolded only at the tail with no digit there were tags 17 of 17.
2. **The count** across every caselist: that shape is 44 lines (25 texts) on the Mac's store.
3. **The PM's ruling of 2026-11-03**: option (a), that shape, with t24's guards unchanged.
4. **The rule**: `assembly-bold-tag-with-an-unbolded-tail-above-a-cite`. The parser is
   `2026.11.03-docx-8`.

**What the operator measured before the merge** (2026-11-03):

- **The labelled evaluation is unchanged**, score for score against `docx-7`, and both gates passed.
- **The before-and-after over the Mac's store:** the rule takes exactly the 44 lines of the sampled
  shape. 44 cards gain a tag, 15 cards above lose their last body paragraph, and 5 cards above
  vanish (a tag whose only body was the taken line, now an analytic, as t24's five were). **0 other
  cards change.** [Before and after](#before-and-after)

**Still to come:** the re-parse is the cloud run's, after the merge (the PM's Q3):
[Operator follow-ups](#operator-follow-ups), steps 3 to 6.

**For the PM first:**

- **The digits split was noticed after the answers**, not planned before them (the ruling asks
  this to be said). Both sides are pinned by fixtures.
- **t23 and this task both name `2026.11.03-docx-8`**, on the same line of `parser.py`. t23 is not on
  `dev` yet. Whichever merges second gets a conflict on that line at `scripts/task sync`, and must
  take `docx-9` ([Deviation 6](#deviations-from-the-spec)).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `bold-in-part`: Bold-in-part tags | Done; the re-parse is the operator's after the merge | `uv run pytest packages/debate_core/tests/integrations/docx_parser` → `1018 passed, 2 xfailed in 5.77s` (the two xfails are t12's labelled leftovers) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a sample of the bold-in-part stratum, with the operator's tallies and formatting descriptions (no card text), and a count of the narrower shape per caselist, sent to the PM before any rule | PASS | The operator ran `scripts/sample_cite_shapes.py --plan bold-in-part --seed 20261103` and filled the tally sheet, which holds no text. Then `scripts/count_bold_in_part_tags.py` (640 s, exit 0). Both are recorded in [`caselist-parse-report.md`](../data/caselist-parse-report.md#a-tag-bold-in-part-above-a-cite-v1-e31-t32), counts only. The relay went to the PM, and the PM ruled on 2026-11-03. Every rule commit (`d7b20ca` on) comes after the record (`91f5a57`). [The sample and the counts](#the-sample-and-the-counts) |
| ac2, first part: a ruled rule is a synthetic fixture shown failing first | PASS | Red at `d7b20ca`: **5 failed, 35 passed**, the 5 taken cases failing by assertion. Green at `183a4ba`: 40 passed, then 41 with the version test. [Red then green](#red-then-green) |
| ac2, second part: tag precision does not fall on the pr-subset | PASS | The operator, 2026-11-03, step 1: `run_parser_eval.py --tier both` → pr-subset 6 files and full 30 files, gate PASSED both. `pytest tests/evals/parser -m "eval and slow"` → `1 passed in 3.89s`. `docx-7` (t31's report) → `docx-8`: pr-subset TAG precision 0.974 → 0.9744, recall 0.884 → 0.8837; CITE 0.973 / 0.818 → 0.973 / 0.8182. Full tier: TAG 0.976 / 0.942 → 0.976 / 0.9422; CITE 0.989 / 0.837 → 0.989 / 0.8372. Unchanged. The gate notes the baseline is `docx-5`'s, as before. `--write-baseline` not passed |
| ac2, third part: `parser_version` is bumped | PASS | `DOCX_PARSER_VERSION = "2026.11.03-docx-8"` (`183a4ba`). Pinned by `test_the_unbolded_tail_rule_came_with_docx_8_or_a_later_one`, the writer's pins, and the golden and provenance fixtures |
| ac2, fourth part: the operator's re-parse written out | **NOT RUN** | After the merge, by the cloud run (the PM's Q3). The steps are [steps 3 to 6](#operator-follow-ups). The parse report's subsection is in place, marked not run |
| Node: `uv run pytest packages/debate_core/tests/integrations/docx_parser` | PASS | `1018 passed, 2 xfailed in 5.77s` |
| `uv run scripts/validate_specs.py` | PASS | See [The checks run before this report](#the-checks-run-before-this-report). Phase `InProgress` |

## The sample and the counts

Both read the dev data directory on the Mac: 13,518 parsed sources. hsld26, hspf26 and openev sit in
`2026.10.20-docx-6` directories, and hspolicy26 in `2026.10.27-docx-7`. Every source was parsed again
by `2026.10.27-docx-7`. The two runs agree exactly, line for line: 4,380 lines left in all, 68 failing
only by bold-in-part, 1,089 failing by it and by something else.

**The first failing condition**, in t24's order (how the line was read, then its bold, then the rest):

| | Lines |
|---|---|
| Read by an assembly rule or through a style | 315 |
| Behind a style that maps to no unit | 122 |
| Not bold, as Word shows it | 2,350 |
| **Bold in part, nothing else the rule asks fails** | **68** |
| Bold in part, something else fails too | 1,089 |
| Over 300 characters / below reading size / a source at the head | 295 / 80 / 7 |
| A highlighted run / the underline or emphasis style | 46 / 7 |
| Fails nothing (the cite is a guess a body may yet take) | 1 |

**The answers**, 24 of the 68 and 6 of the 1,089:

| Where the unbolded part sits (the 24) | Asked | Tag | Not | Part |
|---|---|---|---|---|
| Only at the tail, punctuation only | 5 | 5 | 0 | 0 |
| Only at the tail, letters and no digits | 12 | 12 | 0 | 0 |
| Only at the tail, with digits | 4 | 1 | 3 | 0 |
| At the head and the tail only (bold in the middle) | 2 | 0 | 0 | 2 |
| In the middle | 1 | 0 | 1 | 0 |

- **The other 6:** 1 tag.
- **Item 10** was first marked a tag. The operator corrected it to "part" before the counts,
  because the description written for it was the "part" shape's.
- **Duplicates:** the answers count lines; three texts were drawn more than once, from different files.
- **The interval:** 0 not-tags in 17 is at most 18% at 95% (Wilson).

**The shape across the store** (lines, with distinct texts):

| Shape | hsld26 | hspf26 | hspolicy26 | openev | Total |
|---|---|---|---|---|---|
| Unbolded only at the tail, no digit | 23 (9) | 8 (8) | 10 (5) | 3 (3) | **44 (25)** |

**The PM's ruling (2026-11-03):**

- **Q1: option (a)**, the shape above with t24's guards. Fixtures pin both sides of the digits
  split, the "part" shape, and an unbolded head.
- **Q2:** `docx-8` unless t23 merges first.
- **Q3:** the re-parse is the cloud run's after the merge, so the Goal stays `InProgress`.

## The rule

`DebateDocxParser._is_a_bold_tag` now returns the rule that took the line, or none:

- **bold throughout** as Word shows it: `assembly-bold-tag-above-a-cite` (t24's);
- **bold from its start with one unbolded stretch at its tail that holds no digit**:
  `assembly-bold-tag-with-an-unbolded-tail-above-a-cite`, confidence 0.5 as t24's.

Spaces decide nothing: a tail of two unbolded runs with only a space between them is one stretch.

Every other condition is t24's, and comes first:

- a tagless card;
- one paragraph, blank lines and page furniture stepped over;
- read by a heuristic, in no paragraph style;
- no longer than 300 characters;
- no highlighted run, and no run in the underline or emphasis style;
- no source at the head;
- reading size or larger;
- not a cite a body may yet take.

The tail's shape is `UnboldedPart.shape` in `debate_core.evidence.line_above_a_cite`, the same code
that split the sample's answers and the counts.

### Red then green

| Commit | What | Tests |
|---|---|---|
| `764f7e2` | `FailingCondition`, `unbolded_part`; the sampler's `bold-in-part` plan | new tests passing; parser untouched |
| `876fe6e` | `BoldInPartShape`; `scripts/count_bold_in_part_tags.py` | new tests passing; parser untouched |
| `91f5a57` | The sample and counts recorded | docs only |
| `d7b20ca` | The rule's fixtures | **5 failed, 35 passed** |
| `183a4ba` | The rule; `2026.11.03-docx-8`; the version pins | 41 passed in the file; 4,831 over the set below |
| `f283ae8` | The tools read their fixtures as docx-7 did; `diff_tag_above_a_cite.py --rule unbolded-tail` | 6 failures in the tools' tests at docx-8 (expected: they count what the parser leaves), green after |
| `90d26c8` | `scripts/count_tags_by_rule.py`, for the re-parse | 2 passed |

**Not shown failing first, and not claimed to:** the refusals (the date and page-number tails, bold
only in the middle, an unbolded head, a stretch in the middle, t24's guards on the new shape). A
refusal reads the file as docx-7 did, so it passes before and after. Mutation is their evidence.

### Mutation testing

28 single-line mutants, each run against the test files that cover the code. Each run used a new,
empty `HYPOTHESIS_STORAGE_DIRECTORY` (none of these files holds property tests). After each run the
file was restored from `HEAD`, checked byte for byte, and `git status` was clean.

- **The counts and the sampler** (13): every one caught, by assertion.
  - The ordered conditions, `unbolded_part`'s places and stretches, the bold-in-part split, the
    tagless-card and body-or-nothing checks, the sheet's drawn counts, the refusal to overwrite a sheet.
  - Before the run, two checks had no fixture line that reached them alone, and each was given one: a
    tagged card's line, and an analytic above a cite.
- **The shape and the count script** (7): 5 caught on the first pass, 2 survived.
  - The survivors were counting files by line, and counting tagged cards.
  - Each was given a fixture (two lines of one shape in one file; a tag with a line under it), and
    all 7 are caught on re-run.
- **The rule** (8): every one caught, by assertion:
  - any shape taken;
  - a tail with digits taken;
  - punctuation not taken;
  - t24's rule id on the new shape;
  - no size floor;
  - bold throughout not asked;
  - the tail read as the reader sees it, not as Word shows it;
  - every tag under one rule id.

That is 35 runs (28 mutants and 7 re-runs), over the ~20 cap: three new modules each got their own.

## Before and after

`scripts/diff_tag_above_a_cite.py --rule unbolded-tail`, by the operator, 2026-11-03, 218 seconds, exit
0. It read the 2,680 sources whose stored cards hold a card with no tag, each parsed as `docx-7` read
it and as `docx-8` does.

| | hsld26 | hspf26 | hspolicy26 | openev | Total |
|---|---|---|---|---|---|
| Lines of the sampled shape | 23 | 8 | 10 | 3 | 44 |
| Lines the parser takes | 23 | 8 | 10 | 3 | **44** |
| Taken beyond the sampled shape / left by a guard | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Files with a line taken | 19 | 7 | 9 | 1 | 36 |
| **Cards that gain a tag** | 23 | 8 | 10 | 3 | **44** |
| **Cards above that lose their last body paragraph** | 8 | 4 | 3 | 0 | **15** |
| Cards above that vanish: a tag whose only body was the taken line, now an analytic | 2 | 0 | 3 | 0 | 5 |
| Cards whose heading path alone changes | 0 | 0 | 0 | 0 | 0 |
| **Any other card that changed** | 0 | 0 | 0 | 0 | **0** |
| Cards unchanged | 16,120 | 16,428 | 33,527 | 5,111 | 71,186 |

- **The 5 that vanish** are t24's case, which the PM ruled a fix (t24's Deviation 6): the line
  was the only "body" of the tag above.
- **78 sources differ from their stored cards on the first reading** (21, 55, 0 and 2). This is
  not this rule: it is `docx-7`'s cite rules against the three caselists stored under `docx-6`.
  hspolicy26, stored under `docx-7`, has none.

## The checks run before this report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` | **286 of 677 test files (42.2%)**, past the two-minute line. Left to the pull request's `ci` (working agreement 10; the PM's note) |
| `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest <44 paths> -n auto -m "not slow and not live"` | **`4831 passed, 2 xfailed in 49.63s`**. The paths are: the parser, writer and evidence test directories; every test that reads the structural golden fixtures, the provenance fixtures or `DOCX_PARSER_VERSION`; the seven counting and diff tools' tests; `tests/evals/parser`; and the always-run list (`tests/architecture`, `tests/specs`, the CLI's wiring tests), plus `tests/smoke/test_caselist_parses_owed.py`. Run after `scripts/task sync` |
| `uv run --frozen ruff format --check .` and `ruff check .` | All formatted; all checks passed |
| `uv run --frozen pyright packages/debate_core` and the changed scripts and their tests | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 20 kept, 0 broken` |
| `uv run scripts/validate_specs.py` | OK |
| `scripts/check_command_blocks.py` and `scripts/docs_index.py --check-descriptions` | Pass |

The whole default selection was not run. CI runs the affected set on the pull request, and
everything on dev's push run.

## Files changed

- `packages/debate_core/src/debate_core/evidence/line_above_a_cite.py`:
  - `FailingCondition` and `LineAboveACite.failing_conditions`;
  - `in_an_evidence_style`;
  - `unbolded_part`, `UnboldedPart`, `Place` and `BoldInPartShape`.
- `packages/debate_core/src/debate_core/integrations/docx_parser/parser.py`: the rule, the two rule
  ids as constants, `_bold_tags_above_cites` returning each line's rule, and the version.
- `scripts/sample_cite_shapes.py`: the `bold-in-part` plan, its numbered print and tally sheet.
- `scripts/count_bold_in_part_tags.py` (new): the counts by condition and shape.
- `scripts/diff_tag_above_a_cite.py`: `--rule unbolded-tail`.
- `scripts/count_tags_by_rule.py` (new): stored cards by the rule that read their tag.
- Tests:
  - new: `tests/scripts/test_sample_bold_in_part_tags.py`, `test_count_bold_in_part_tags.py` and
    `test_count_tags_by_rule.py`;
  - extended: `packages/debate_core/tests/evidence/test_line_above_a_cite.py`,
    `.../docx_parser/test_tag_above_a_cite.py` and `tests/scripts/test_diff_tag_above_a_cite.py`.
- The version, restated as t23 restates it:
  - `.../docx_parser/test_cite_lines_by_their_place.py`: t31's pin becomes "or a later one";
  - `.../docx_file_writer/test_fidelity.py` and `test_writer.py`;
  - the four `files_built_with_the_provenance_line/*.provenance.json`;
  - the ten `tests/fixtures/debate_files/structural/*.expected.json`: their `parser_version` line only.
- `docs/data/caselist-parse-report.md`: this task's section.
- `docs/session-reports/v1-e31-t32-bold-in-part-tags.md`: this report.

## Deviations from the spec

1. **The digits split was found after the answers.** It was not planned before the sample. The PM
   ruled on it knowing so, and fixtures pin both sides.
2. **`tests/fixtures/debate_files/structural/*.expected.json` is outside `constraints.packages`.**
   Only the version line changed, as t19, t24, t31 and t23 changed it.
3. **The labelled evaluation needs two commands.** `-m "eval and slow"`, the PM's command, runs only
   the full tier, since the pr-subset test is marked `eval` alone. ac2 names the pr-subset, so step 1
   also runs `scripts/run_parser_eval.py --tier both`, without `--write-baseline`.
4. **The sampled store mixes versions and lacks the cloud's weeks.** Three caselists sit in
   `docx-6` directories and one in `docx-7`. Each source was parsed again by `docx-7`, so the counts
   are that parser's readings. The Mac lacks the weeks the cloud has run since the cutover. The
   bold-in-part lines are 1,157 there, against 967 on `docx-5` over 11,154 sources.
5. **35 mutation runs** against the ~20 cap: three new modules, and 7 re-runs after fixtures were added.
6. **Two branches name `2026.11.03-docx-8`.** t23's branch bumps the same constant to the same
   string. A sync of the second to merge conflicts on that line, so it cannot pass unnoticed. That
   branch takes `docx-9` and its pins, and the docstring names both bumps.
7. **The affected set is 286 files**, and is left to `ci` (working agreement 10). Agreement 10 lets
   a parser-version bump with its golden fixtures ask for one whole-selection run by the operator
   before the pull request. The PM's note says to leave it to `ci`, so it is not handed over.

## Decisions and assumptions

- **The conditions' order is t24's report's**, with bold checked before length, as its labels
  ("Bold, over 300 characters") show. That is what makes "bold in part" the 967 the PM named.
- **The sample's size and split:** 24 lines where bold in part is the only failure, and 6 where
  something else fails too. Lines over 300 characters, or ones failing a guard, could not become
  tags under a rule that keeps t24's guards.
- **The sample asked no questions in the terminal.** It printed the items numbered inside `less`,
  so the text left the terminal when `less` closed. The answers came back on a sheet holding no
  text, and the session read the sheet and the counts file directly from the operator's home folder.
- **A rule id of its own,** so that the re-parse can count this rule's cards apart from t24's.
  Confidence 0.5, as t24's.
- **A direct underline on the tail does not refuse the line**, as it did not refuse (7)'s line.
  Only the underline and emphasis character styles do, as in t24's rule.
- **Expected values were written by hand** from each invented file (working agreement 6). Three
  were first written wrong and corrected from the fixture, never from the output:
  - a `NormalWeb` line read through its style's alias;
  - a hand count of 286 characters;
  - two lines sharing one text.

## Operator follow-ups

### Before the merge

Steps 1 and 2 were run by the operator on 2026-11-03; their results are above (ac2, and
[Before and after](#before-and-after)). They are kept here as they were run.

**1. The labelled evaluation** (expected runtime under a minute; reads the labelled files; writes
only `build/eval-reports/`, which is gitignored; no `--write-baseline`). Where: your Mac, in this
task's worktree:

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e31-t32-bold-in-part-tags
git log --oneline -1
uv run python scripts/run_parser_eval.py --tier both
uv run pytest tests/evals/parser -m "eval and slow" -p no:randomly -q
python3 -I -c 'import json, sys; [print(r["tier"], r["parser_version"], "gate", r["gate"]["passed"], "TAG", r["groups"]["overall"]["units"]["TAG"]["precision"], r["groups"]["overall"]["units"]["TAG"]["recall"], "CITE", r["groups"]["overall"]["units"]["CITE"]["precision"], r["groups"]["overall"]["units"]["CITE"]["recall"]) for r in (json.load(open(p)) for p in sys.argv[1:])]' build/eval-reports/parser-pr-subset.json build/eval-reports/parser.json
```

What success looks like:

- `pr-subset: 6 files, gate PASSED` and `full: 30 files, gate PASSED`;
- `1 passed` from pytest;
- two lines naming `2026.11.03-docx-8`, with TAG precision not below docx-7's: 0.974 on the
  pr-subset and 0.976 on the full tier.

Send the last line of each command.

**2. The before-and-after over the Mac's store** (expected runtime about 5 to 10 minutes; read-only;
counts only). Each file with a card that has no tag is read as docx-7 read it and as docx-8 does.
Where: the same worktree:

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e31-t32-bold-in-part-tags
uv run python scripts/diff_tag_above_a_cite.py --rule unbolded-tail > ~/t32-diff.json; echo "exit $?"
```

What success looks like:

- `exit 0`;
- in each caselist, `taken` near the shape's count (23, 8, 10, 3), `taken_beyond_the_sampled_rule`
  0, and `other_cards_changed` 0.

The file holds counts only; the session reads it.

**3. The "before" copy of the dev bucket**, on the build installed now, before the first cloud run on
an image carrying `docx-8` (expected runtime about 8 to 15 minutes; restores the four parsed stores
under the dev run lock; fetches no raw sources). The block refuses a Wednesday, a `DEBATE_` override,
a pull running on this Mac, and a copy that exists already. Where: your Mac, any window:

```zsh
if [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day"; elif env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif pgrep -fl 'debate-research( --json)? caselist pull'; then echo "STOP: a caselist pull is running (above)"; elif [ -e "$HOME/t32-before" ]; then echo "STOP: t32-before exists already"; else aws sso login --profile debate-dev-evidence && cd "$HOME" && caffeinate -i env DEBATE_ENV=dev debate-research --json caselist restore-run-state --into "$HOME/t32-before" --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev > /tmp/t32-before-restore.json; echo "exit $?"; grep -oE '"(parsed_version|parsed_objects)": ("[^"]*"|[0-9]+)|"code": "[A-Z_]+"' /tmp/t32-before-restore.json; fi
```

What success looks like:

- `exit 0`;
- `parsed_version` the installed build's, and `parsed_objects` above zero.

`parsed_objects` 0 means the bucket holds no parsed store of that version: stop and tell the PM.
`RUN_LOCK_HELD`: wait for the cloud run to record, then run the block again. Then the count:

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e31-t32-bold-in-part-tags
uv run python scripts/count_tags_by_rule.py --data-dir ~/t32-before > ~/t32-before-counts.json; echo "exit $?"
```

### After the merge

**4. The image and its full re-parse.** Build and deploy a run image carrying the merge, by
[caselist-cloud-run.md, "A new image, later"](../runbooks/caselist-cloud-run.md#a-new-image-later).
Its first run parses every caselist in full ("A new image with a new parser version"). When that run
has recorded:

```zsh
aws sso login --profile debate-dev-evidence
debate-research caselist runs --remote --last 1
```

What success looks like: the run's outcome and counts, and no `Full parse owed under parser
version 2026.11.03-docx-8` caption. A caption means a caselist is still owed: wait for the next
run.

**5. The "after" copy and its count.** Install a dev build that carries the merge, by the
scheduled-sync runbook (`scripts/install_channel.sh` with its tag), because a restore brings back
only the installed build's version. Then run step 3's two blocks again, with `t32-after` in place of
`t32-before` throughout. `parsed_version` must be `2026.11.03-docx-8`.

Expected in `~/t32-after-counts.json`, against `~/t32-before-counts.json`:

- `tagged_by_unbolded_tail` 0 before. After, near step 2's `taken` (23, 8, 10, 3), a little higher
  by the cloud's weeks.
- `no_tag` after equal to `no_tag` before less `tagged_by_unbolded_tail`, give or take the weeks
  imported between the two copies.
- `tagged_by_bold_tag` unchanged, give or take the same weeks.

Both files hold counts only; send them to the PM.

**6. Record it and close.** Whoever closes ac2 adds the figures to
`docs/data/caselist-parse-report.md`, under "The re-parse to `docx-8`", and sets the Goal
`Succeeded`. Then delete the two copies, which hold card text:

```zsh
rm -rf ~/t32-before ~/t32-after
```

The prod parsed store follows dev's at the promotion, by the cloud-run runbook's prod section.

## Follow-up work

- **For the PM to file: the 2,350 lines not bold as Word shows them.** They are the largest stratum
  t24's rule leaves, and have never been sampled on their own. t24's sample of all left lines found
  1 tag in 6.
- **For the PM to file: the inline "part" card.** A tag, a bold short cite and a claim on one line
  (5 lines, 4 texts, in the 68). It is a card written inline, not a tag, and no rule reads it.
- **The operator's tally sheet and counts file** (`~/bold-in-part-tally-sheet.txt`,
  `~/bold-in-part-counts.json`) hold no card text. The sheet does hold the operator's formatting
  descriptions. Delete both once the PM has the report.
- **An empty `testcl26` directory** sits in the Mac's dev parsed store (0 sources). It is harmless,
  and the count read it as empty.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-03

**Notes:**

The rule was sampled and counted before it was written, ruled, and then shown to take exactly the shape it
was ruled for, and nothing more.

1. **ac1 passes.** The operator's sample (seed 20261103, 30 items, no card text) and the count by condition
   and shape went to the PM before any rule; every rule commit follows the record (`91f5a57`). Tail-only, no
   digit: 17 tags in 17 (at most 18% not, Wilson 95%); 44 lines, 25 texts, across the four caselists.
2. **The digits split was found after the answers**, and the report says so (Deviation 1), as the ruling
   asked. The PM ruled on it knowing that, and fixtures pin both sides (1 tag in the 4 with digits).
3. **ac2's first three parts pass.** Red first at `d7b20ca` (5 failed, 35 passed, by assertion); the
   refusals rest on mutation, rightly not claimed as red. The labelled evaluation is unchanged score for
   score against docx-7 on both tiers (pr-subset TAG precision 0.974 to 0.9744) and the gate passed;
   `2026.11.03-docx-8` is pinned.
4. **The before-and-after is the strongest evidence here:** 44 taken, 0 beyond the sampled shape, 0 left by
   a guard, 0 other cards changed over 71,186 unchanged. The 15 cards that lose their last body paragraph
   were carrying a tag line as evidence, so this removes words that were never the author's; the 5 that
   vanish are t24's ruled case. The 78 first-reading differences are docx-7 against docx-6 storage, not
   this rule.
5. **Mutation:** 28 mutants, every one caught after the two survivors got fixtures; 35 runs against the
   ~20 cap is accepted for three new modules (Deviation 5).
6. **The version (Deviation 6), PM ruling:** this task merges first and keeps `2026.11.03-docx-8`.
   v1-e31-t23 is still building its N1 rule (ruled 2026-11-03) and takes `docx-9` at its sync. The PM
   tells that session.
7. **The re-parse steps are re-timed by the PM:**
   - **Step 3** (the "before" copy) cannot run before Wednesday 2026-11-04's cloud run records: the dev
     bucket holds no docx-7 parsed store until revision 11's full re-parse, so tonight's restore would
     give 0 objects, as the e39-t10 journey's J2 did on 2026-11-03. It runs on Thursday 2026-11-05 on
     the dev.342 build, and the operator installs no newer dev build until it has.
   - **Step 4's image** carries this merge and, if v1-e31-t23 has merged by then, docx-9 as well, so one
     full re-parse covers both bumps. Step 5's `parsed_version` is then the image's version.
8. **Deviations 2, 3, 4 and 7 accepted.** The golden fixtures' version line (as t19, t24, t31 and t23);
   two commands for the two tiers; the Mac's mixed store, re-read by docx-7; the affected set left to
   `ci`.
9. **Follow-ups filed by the PM in the next batch:** a sample of the 2,350 lines not bold as Word shows
   them, and the inline "part" card.
10. **Merge:** `scripts/task pr --partial` once `ci` is green. The Goal stays `InProgress` until the
    re-parse's counts are recorded (steps 4 to 6).

## PM note after the merge (2026-11-03)

Added by the PM in the batch after the merge. Nothing above is changed, and this is not a review.

* **Step 3** (the "before" copy) runs on Thursday 2026-11-05, after the cloud run of Wednesday
  2026-11-04 records, and on the `v1.1.0-dev.342` build: before that run the dev bucket held no
  `docx-7` parsed store, so a restore would have held 0 objects, as v1-e39-t10's journey found on
  2026-11-03. No newer dev build is installed on the Mac until step 3 is done.
* **Step 4's image** carries this merge and, if v1-e31-t23 has merged by then, `2026.11.03-docx-9` as
  well, so one full re-parse covers both bumps. Step 5's `parsed_version` is then that image's version.
* **v1-e31-t23** takes `docx-9` at its sync (the PM's note to that session, 2026-11-03).

## Operator records (recorded by the PM, 2026-11-05)

Added by the PM. Nothing above is changed, and this section is not a review.

| Criterion | Was | Now | Record |
|---|---|---|---|
| ac2, step 3: the "before" copy and its count | NOT RUN (operator) | Done (before half) | 2026-11-05, build 1.1.0.dev342: ~/t32-before restored, parsed_version 2026.10.27-docx-7, 18,345 objects. count_tags_by_rule.py: hsld26 sources 6,889, cards 105,947, no_tag 1,916, tagged_by_bold_tag 185, tagged_by_unbolded_tail 0; hspf26 4,143, 67,217, 3,478, 1,003, 0; hspolicy26 5,132, 168,732, 1,638, 44, 0; openev 102, 8,081, 78, 0, 0. The cards total 349,977 and the sources 16,266, the hand run's own figures |

Steps 4 to 6 follow the docx-9 run image's full re-parse: the "after" copy's count against these, then both copies deleted. The Goal stays `InProgress`.

## The before copy (PM note, 2026-11-06)

`~/t32-before` was deleted on 2026-11-06 under data-use policy 1.18, its counts kept in
`~/t32-before-counts.json`, which is what step 5 compares the after copy's counts with. Step 6 deletes
the after copy alone.

## Operator records (recorded by the PM, 2026-11-12)

Added by the PM. Nothing above is changed, and this section is not a review.

| Criterion | Was | Now | Record |
|---|---|---|---|
| ac2, fourth part: the operator's re-parse written out | NOT RUN | PASS | 2026-11-12, `scripts/count_tags_by_rule.py` from the main clone at dev over v1-e39-t18's restored copy of dev's run state after the 2026-11-11 run (parser `2026.11.03-docx-9`, which carries this task's rule), against `~/t32-before-counts.json` (2026-11-05, docx-7). `tagged_by_unbolded_tail` after: hsld26 23, hspf26 12, hspolicy26 10 (step 2's taken: 23, 8, 10; hspf26 higher by the weeks between). `no_tag` per card: hsld26 1.81% to 1.71%, hspf26 5.17% to 4.98%, hspolicy26 0.97% to 0.99%; `tagged_by_bold_tag` 185 to 196, 1,003 to 1,087, 44 to 45. The after copy holds about 3,000 more sources (a week's disclosures), so the counts compare per card, not one for one. The copy was deleted by v1-e39-t18 under policy 1.18; the two counts files hold counts only |

Every criterion passes, so the Goal is `Succeeded`.
