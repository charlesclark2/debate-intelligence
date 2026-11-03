# Session report: v1-e31-t24-bold-tag-above-bracketed-cite

| | |
|---|---|
| Task | `v1-e31-t24-bold-tag-above-bracketed-cite` — A bold tag above a bracketed cite is read as the card's tag |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t24-bold-tag-above-bracketed-cite.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t24-bold-tag-above-bracketed-cite.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t24-bold-tag-above-bracketed-cite` |
| Session status | PARTIAL: counts, sample, ruling, rule, ac4, version, checks and documents are done. The re-parse to `docx-6` (ac3, second half) is the operator's after the merge. The Goal stays `InProgress` <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Item (7)'s two lines are tags typed with nothing set, in a Google Docs export. That export's
document defaults make every run bold at 13 pt. Word shows ordinary bold tags; the parser, which
reads what a run says, saw an unbolded line of no size, so the bold-heading rule could not take it.

**The work, in the PM's order:**

1. The count ([the counts](#the-counts)): 17 lines of the shape, all in hspf26, in 10 files.
2. The sample of the general rule: 20 of 20 right.
3. The PM's ruling of 2026-10-20: the rule above any cite, with four guards.
4. The rule: `assembly-bold-tag-above-a-cite`. It reads the line's bold and size as Word shows
   them, inside this rule only.

**What the rule changes in the store** (re-parsed with the rule off and on, read-only):

- 875 cards gain a tag;
- 150 cards above lose their last body paragraph;
- 5 cards above vanish: tags whose only body was the taken line, now analytics;
- 100 cards change only their heading path, which now names the taken line above them;
- 0 other cards change.

The labelled evaluation is unchanged, score for score. ac4's Undertag step-over is built and
v1-e33-t02's pinned pair restated. The parser is `2026.10.20-docx-6`.

**For the PM first:**

- the 100 heading-path-only cards and the 5 that vanish ([Deviation 6](#deviations-from-the-spec));
- the spec still says "bracketed" ([Deviation 3](#deviations-from-the-spec)).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `bold-tag`: Bold tag above a bracketed cite | Done in the session | Counts, sample, the PM's ruling, the rule and ac4. The re-parse is the operator's (ac3). `uv run pytest packages/debate_core/tests/integrations/docx_parser` → `979 passed, 2 xfailed in 3.03s` |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: before any rule changes, the operator-corpus count of the shape per caselist and, if sampled, the coach's tallies | PASS | The count is from `cca211f`, before any rule commit: `uv run python scripts/count_tag_above_bracketed_cite.py --expect-version 2026.10.18-docx-5` → hsld26 0, **hspf26 17 (10 files)**, hspolicy26 0, openev 0, in 15 s, 0 not reproduced. The operator ran `--every-source` (353 s) and `scripts/sample_cite_shapes.py --plan bold-tag --seed 20261020` (36 items, 845 s): taken 20 of 20 tags, left 1 of 6 a tag, bold lines above no cite 3 of 10 headings. [The counts](#the-counts) |
| ac2: synthetic fixtures shown failing first, the two cards of (7) read with their tags, tag and cite precision do not fall | PASS | Fixtures committed red at `e6bd752`: `4 failed, 14 passed`, the four taken cases failing by assertion. Green at `7ac8cdb`; 25 in the class now. (7): the file's cards 2 and 3 of 16 both read with `assembly-bold-tag-above-a-cite`, each tag the last line of the card above (a scratch check printing booleans only). `run_parser_eval.py --tier pr-subset`, docx-5 then docx-6: TAG precision 0.949 → 0.949 (recall 0.861 → 0.861); CITE precision 0.969 → 0.969 (recall 0.705 → 0.705); gate PASSED both times; `--write-baseline` not passed |
| ac3, first half: `parser_version` is bumped | PASS | `DOCX_PARSER_VERSION = "2026.10.20-docx-6"` (`94d1027`); `TestTheParserVersion` in `test_tag_above_a_cite.py` |
| ac3, second half: the re-parse is the operator's and is recorded in `docs/data/caselist-parse-report.md` | **NOT RUN** | After the merge only. [Operator follow-ups](#operator-follow-ups). The report's section is in place, with the read-only figures, and its re-parse subsection is marked not run |
| ac4: a highlighted cite with an Undertag before its body is the cite, fixture failing first; v1-e33-t02's pair updated; a built file holding such a card reads back | PASS | Red at `b64cae3`: `2 failed, 2 passed`, the two by assertion. Green at `d2e1151`. `test_the_parser_steps_over_the_line` and `test_a_highlighted_cite_builds_and_reads_back_with_the_line_below_it` both fail by assertion with the old look-ahead, and pass now. `uv run pytest packages/debate_core/tests/integrations/docx_file_writer` → `150 passed`. The writer's source is untouched |
| The PM's check: before and after, three numbers | PASS, with the categories in Deviation 6 | `uv run python scripts/diff_tag_above_a_cite.py --caselist <c>`, four runs, 175 s: cards that gain a tag **875**, cards above that lose their last body paragraph **150**, other cards changed **0**. Also: 5 cards above vanish, and 100 cards change only their heading path. [Before and after](#before-and-after) |
| The PM's check: how many of the 921 the highlight and style guard excludes | PASS | 45: 38 for a highlighted run and 7 for the underline or emphasis style. 1 more is left because its cite is a guess a body may yet take. 875 taken; none taken beyond the 921 |
| Node: `uv run pytest packages/debate_core/tests/integrations/docx_parser` | PASS | `979 passed, 2 xfailed in 3.03s` (the two xfails are `v1-e31-t12`'s labelled leftovers) |
| `uv run scripts/validate_specs.py` | PASS | `OK: 396 files, 39 epics, 336 tasks, 21 releases`. Phase `InProgress` |

## The checks run before this report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` | 165 test files of 331: about half the default selection, about three minutes here, so not run in the session. Left to the pull request's `ci` (working agreement 10; the PM's note) |
| `uv run --frozen pytest packages/debate_core/tests/integrations/docx_parser packages/debate_core/tests/evidence packages/debate_core/tests/integrations/docx_file_writer tests/scripts/test_count_tag_above_bracketed_cite.py tests/scripts/test_sample_cite_shapes.py tests/scripts/test_diff_tag_above_a_cite.py -n 4` | `2480 passed, 2 xfailed in 9.45s`. These are the parser and writer directories, the fidelity suite and the structural golden fixtures |
| `uv run --frozen pytest tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py tests/evals/parser -n 4 -m "not slow and not live"` | `553 passed`: the always-run list, plus the evaluation's tests |
| `uv run --frozen ruff format --check .` and `ruff check .` | 922 files formatted; all checks passed |
| `uv run --frozen pyright packages/debate_core` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 12 kept, 0 broken` |
| `uv run python scripts/docs_index.py --check-descriptions` | All 38 indexed documents have a description |
| `uv run python scripts/validate_specs.py` | OK |

The whole default selection was not run: CI runs it on the pull request.

## The counts

All read-only over the dev data directory's `2026.10.18-docx-5` store: 11,154 parsed sources.
Every source parsed again gave back its stored cards' ranges.

**(7) is bold by its file's defaults.** I located (7)'s file and printed the line's formatting with
its text removed. It sets nothing of bold or size; the file's `w:docDefaults` sets `w:b` on and
`w:sz` 26; its body and cite runs switch bold off and set 22. The reader read none of the styles
part's run properties, so the count could not see the shape as "bold". `package.py` now keeps the
document defaults and each style's own bold and size, and `runs.as_word_shows_it` fills a run from
them. The count gives bold both ways: as the reader sees it, and as Word shows it.

| | hsld26 | hspf26 | hspolicy26 | openev | Total |
|---|---|---|---|---|---|
| Cites read by a bracketed rule | 153 | 255 | 51 | 39 | 498 |
| **The shape** (line above, body or nothing, bold as Word shows it or in a tag style) | 0 | **17** | 0 | 0 | **17** |
| Files holding it | 0 | 10 | 0 | 0 | 10 |
| Of the 17, bold only by inheritance | | 15 | | | 15 |
| Files whose defaults make text bold | 3 | 30 | 9 | 0 | 42 |
| The proposed rule's lines, above any cite, every file (operator, `--every-source`) | 115 | 784 | 22 | 0 | 921 |
| Files holding them | 61 | 239 | 10 | 0 | 310 |

Of the 921, 71 are bold only by inheritance. Most of the rest are bold of their own with no size
stated, which the bold-heading rule cannot read either.

**The sample** (operator, seed 20261020, 36 items, 845 s). Each line was shown bold as Word shows it.

| Stratum | In the store | Answers |
|---|---|---|
| Taken, above a bracketed cite | 17 | tag 10 of 10 |
| Taken, above another cite | 904 | tag 10 of 10 |
| Left, read as body or nothing | 3,573 | tag 1 of 6 |
| Bold, above no cite, in a file with bold defaults | 417 | a heading 3 of 10 |

**The PM's ruling (2026-10-20).** Scope (a), the rule above any cite, with these guards:

- only where the cite opens a card with no tag;
- inherited formatting is read inside this rule only;
- a highlighted run, or a run in the underline or emphasis style, keeps the line body;
- one paragraph only.

Option (c), reading Word's formatting in the classifier everywhere, was refused.

## The rule

`DebateDocxParser._bold_tags_above_cites` and `_is_a_bold_tag`. Rule id
`assembly-bold-tag-above-a-cite:<the rule it overrode>`, confidence 0.5.

**When it applies:** the cite opens a card with no tag, and the cite is no guess a body may yet
take.

**Which line:** the paragraph directly above the cite. Blank lines and page furniture are stepped
over; a second text paragraph never is.

**What the line must be:**

- read as body or nothing by a heuristic, not by an assembly rule's re-reading;
- not in a paragraph style (a style that maps to no unit, which here includes an explicit
  `Normal`);
- no longer than 300 characters;
- with no highlighted run, and no run in the underline or emphasis style;
- naming no source within its first 40 characters;
- as Word shows it, bold throughout at 22 half-points or more.

The build assembles once. Only when a line is taken does it assemble again, with that line read
as a tag. The tag above may then have nothing under it and become an analytic, as the existing
demotion has it.

**ac4:** `_followed_by_a_body` steps over `UNDERTAG` as it steps over `OTHER`.

### Before and after

`scripts/diff_tag_above_a_cite.py`, run in the session: 2,373 sources, 175 s. These are every
source whose stored cards hold a card with no tag and a cite. Each was parsed by `docx-6` with the
rule off and on. With the rule off, every one gives back its stored ranges, so ac4 changes none of
them.

| | hsld26 | hspf26 | hspolicy26 | openev | Total |
|---|---|---|---|---|---|
| Lines taken | 101 | 760 | 14 | 0 | 875 |
| Left: highlighted run / underline or emphasis style / cite a body may take | 9 / 5 / 0 | 21 / 2 / 1 | 8 / 0 / 0 | 0 | 38 / 7 / 1 |
| Cards that gain a tag | 101 | 760 | 14 | 0 | **875** |
| Cards above that lose their last body paragraph | 28 | 112 | 10 | 0 | **150** |
| Cards above that vanish (the tag above becomes an analytic) | 0 | 5 | 0 | 0 | 5 |
| Cards further down whose heading path now names the taken line | 2 | 103 | 2 | 0 | 107 |
| of which changed in nothing else | 2 | 97 | 1 | 0 | 100 |
| Any other card that changed | 0 | 0 | 0 | 0 | **0** |

A card can show several effects. The first run classified 160 hspf26 cards as "other". I broke
them down by changed field, names only: each was a card with two effects at once, or a heading-path
change that the script had not yet recognised. The script now recognises each effect, and each
effect is tested in `tests/scripts/test_diff_tag_above_a_cite.py`, including a card changed some
other way, which is still counted as other.

(7)'s file goes from 16 cards to 15. Its first card was a tag whose only body was card 2's tag
line, and that tag is now an analytic.

### Red then green

| Commit | What | Tests |
|---|---|---|
| `cca211f` | The counting module, the count script, the sampler's plan, the package's inherited properties (unused by the parser) | 15 + 11 + 8 + 3 new, passing; parser output unchanged (`2273 passed` over the parser and evidence directories) |
| `b64cae3` | ac4's fixtures | **2 failed, 2 passed** |
| `d2e1151` | ac4: the step-over; v1-e33-t02's pair restated | 4 passed; the pair fails by assertion with the old look-ahead |
| `e6bd752` | The bold-tag fixtures | **4 failed, 14 passed** |
| `7ac8cdb` | The rule; the counting tools' tests read their stores as docx-5 did | 18 passed |
| `94d1027` | `2026.10.20-docx-6` | 2473 passed |
| `9c5b9a5` | The before-and-after script | 3 passed |
| `1392bf4` | Four edge fixtures from mutation; one unreachable check deleted | 25 in the class |

**Not shown failing first, and not claimed to:** the guards' refusals. A refusal reads the file
as docx-5 did, so it passes before and after. Mutation is their evidence.

### Mutation testing

21 single-line mutants of the rule, the step-over and `as_word_shows_it`. Each was run against
three files (`test_tag_above_a_cite.py`, `test_inherited_run_properties.py`, `test_fidelity.py`;
0.6 to 0.9 s a run). Each run used a new, empty `HYPOTHESIS_STORAGE_DIRECTORY` (the files hold no
property tests). The file was restored from saved bytes and checked with `filecmp` after each run,
and `git status` was clean after.

- **16 caught on the first pass:** the rule never applied; no 300-character bound; highlighted
  taken; the evidence styles taken; the emphasis style taken; a source at the head taken; no
  inherited formatting; bold not asked; a tagged card touched; no blank line stepped over; a
  second paragraph stepped over; the Undertag step-over undone; the tag's confidence; the default
  paragraph style ignored; a style's ancestors ignored; the document defaults ignored.
- **5 survived:**
  - *Four were given a fixture each*, and all four are caught on re-run: an assembly re-reading
    (a cite guess the body took); a paragraph style that maps to no unit; exactly reading size;
    a cite a body may yet take.
  - *One check was deleted:* the heuristic-only check. A body or nothing read other than by a
    heuristic comes from a paragraph style, which the style check refuses, so no input reaches it.
    The hspf26 diff was run again after the deletion and is identical.

That is **25 runs**, a little over the ~20 cap, because of the four re-runs.

## Files changed

- `packages/debate_core/src/debate_core/integrations/docx_parser/parser.py`: the rule; the
  assembly loop moved into `_assemble` so that it can run twice; ac4's step-over; the version.
- `packages/debate_core/src/debate_core/integrations/docx_parser/package.py`: each style's own bold
  and size, which style is the default, and the document's run defaults. Read; nothing but the
  rule uses them.
- `packages/debate_core/src/debate_core/integrations/docx_parser/runs.py`: `as_word_shows_it` and
  `defaults_make_text_bold`; `read_paragraph` is unchanged.
- `packages/debate_core/src/debate_core/evidence/line_above_a_cite.py` (new): the line above a cite
  and the bold lines, in counts.
- `scripts/count_tag_above_bracketed_cite.py` (new); `scripts/diff_tag_above_a_cite.py` (new);
  `scripts/sample_cite_shapes.py` (the `bold-tag` plan).
- Tests:
  - new: `packages/debate_core/tests/integrations/docx_parser/test_tag_above_a_cite.py`,
    `.../test_inherited_run_properties.py`, `packages/debate_core/tests/evidence/test_line_above_a_cite.py`,
    `tests/scripts/test_count_tag_above_bracketed_cite.py`, `tests/scripts/test_diff_tag_above_a_cite.py`;
  - extended: `tests/scripts/test_sample_cite_shapes.py`;
  - restated: `.../docx_file_writer/test_fidelity.py` (ac4's pair and the version) and
    `test_writer.py` (the version); `.../docx_parser/test_remaining_cite_shapes.py` (t19's version
    pin).
- `tests/fixtures/debate_files/structural/*.expected.json`: the `parser_version` line of each of
  ten files, nothing else.
- `docs/data/caselist-parse-report.md`: the section for this task.
- `docs/session-reports/v1-e31-t24-bold-tag-above-bracketed-cite.md`: this report.

## Deviations from the spec

1. **The count ran in the session**, read-only, in 15 seconds (working agreement 2: a read-only
   command over files the operator has, finishing in seconds). The `--every-source` count and the
   sample were the operator's.
2. **"In bold" is counted as Word shows it,** as well as as the reader sees it. With the reader's
   bold, (7)'s own lines are not the shape: 2 lines in hspf26, neither of them (7)'s.
3. **The spec's scope says "above a bracketed cite"; the PM ruled "above any cite"** (2026-10-20,
   scope (a)). The spec's title, description and ac2 still say bracketed. Per the PM's rule on spec
   conflicts, I built the ruled rule and leave the spec's wording to the PM.
4. **Outside `constraints.packages`:**
   - `tests/fixtures/debate_files/structural/*.expected.json`: the version line only, as t19 did.
   - `.../docx_file_writer/test_writer.py`: its version pin; the PM's note allowed only ac4's
     writer tests.
   - `tests/fixtures` and the writer's test directory are not in the list. Both changes follow
     from ac3's bump; the writer's source is untouched.
5. **Three refusals beyond the PM's four guards**, each so that the rule takes no more than was
   sampled or than one assembly can show:
   - a line in a paragraph style that maps to no unit, and a line an assembly rule re-read (both
     were outside the sampled 921);
   - a cite that is a guess a body may yet take, which leaves 1 line of the 921. Without this
     refusal, the second assembly would turn that cite into body.
6. **"Any other card that changed" is 0, but two kinds of change sit beside the three numbers:**
   - **100 cards change only their heading path.** They are cards with no tag further down under
     the same block. Their path named the tag above, or no tag; now it names the taken line, which
     is the open tag above them. They are not next to a taken line. A tagless card is placed under
     whichever tag stands above it, so this is the rule's reading followed through, but it is
     outside the PM's "next to a taken line".
   - **5 cards above vanish:** a tag whose only body was the taken line. Its line is now the next
     card's tag, so the tag has nothing under it and becomes an analytic, by the existing demotion.
     (7)'s file holds one.
   - The PM's ruling on both is wanted.
7. **25 mutation runs**, against the ~20 cap: 21 mutants and 4 re-runs.

## Decisions and assumptions

- **The version is `2026.10.20-docx-6`,** as the PM gave it.
- **The rule's confidence is 0.5,** the classifier's own for a bold line at reading size
  (`heuristic-direct-formatted-heading-tag`).
- **Word's toggle for bold in styles is approximated:** the nearest style that states bold wins.
  The two differ only where two styles in a run's chain both set bold. Said in `as_word_shows_it`'s
  docstring.
- **No outline-level check** on the line, as sampled.
- **A second assembly only when a line is taken,** so a file the rule does not touch is built
  exactly as before.
- **The counting tools keep the checkout's parser.** They count against the store's parser and
  refuse a store of another version, so on a `docx-6` store they count what the rule leaves.
- **Expected values were written by hand** from each invented file (working agreement 6). The diff
  script's counts were checked against an invented file holding one card of each effect.

## Operator follow-ups

After the merge, in this order, from the main checkout on `dev`, not while `caselist pull` is
running. The steps follow t19's step 2, the most recent re-parse, and the scheduled-sync runbook's
"After a release that bumps the parser version".

**Time and disk:**

| Step | Time |
|---|---|
| Dev parse and publish | about 35 minutes |
| Second run | about 20 minutes |
| Cluster comparison | about 20 minutes |
| Prod publish | about 15 minutes |

Have at least 8 GiB free.

**1. Start on an updated `dev`** (seconds):

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
git branch --show-current
git status --short
git pull --ff-only origin dev
git log --oneline -1 --grep='^v1-e31-t24-bold-tag-above-bracketed-cite:'
export DEBATE_ENV=dev
uv run debate-research caselist runs --last 1
df -h ~/.debate-research
```

Expected: `dev`; `git status` prints nothing; `git log` prints one line; the last run has finished;
at least 8 GiB available. If `git log` prints nothing, the merge is not on `dev`: stop.

**2. The dry run, and the counts before** (about 3 minutes; writes nothing; no AWS session):

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
export DEBATE_ENV=dev
for c in hsld26 hspolicy26 hspf26 openev; do uv run debate-research --json caselist parse --caselist ${c} --dry-run | jq -c '.data | {caselist, version, fingerprint_version, sources, to_parse, skipped}'; done
for c in hsld26 hspolicy26 hspf26 openev; do echo ${c}; find ~/.debate-research/dev/parsed/${c}/2026.10.18-docx-5/sha256 -name '*.jsonl' -print0 | xargs -0 jq -r 'select(.record == "document") | .document.cards[] | "\(if .tag == null then "no-tag" else "tagged" end) \(if any(.rule_ids[]; startswith("assembly-bold-tag-above-a-cite")) then "bold-tag" else "other" end)"' | sort | uniq -c; done > ~/t24-cards-before.txt
cat ~/t24-cards-before.txt
```

Expected:

- the first loop prints `version` `2026.10.20-docx-6`, with `to_parse` equal to `sources`, for
  each caselist. If `version` is `2026.10.18-docx-5`, the checkout does not carry the task: stop.
- the second loop finds no `bold-tag` card, and these `no-tag` counts: hsld26 1,563, hspf26 3,038,
  hspolicy26 1,093, openev 78.

**3. The dev parse and publish** (about 35 minutes), one caselist at a time:

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
aws sso login --profile debate-dev-evidence
export DEBATE_ENV=dev
uv run debate-research --json caselist parse --caselist hsld26 --publish > ~/t24-dev-hsld26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist hspolicy26 --publish > ~/t24-dev-hspolicy26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist hspf26 --publish > ~/t24-dev-hspf26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist openev --publish > ~/t24-dev-openev.json; echo "exit $?"
```

Expected: `exit 0` each time. On `PARSED_PUBLISH_INCOMPLETE`, run the same line again.

This is also the cluster rebuild. `caselist parse` writes the new version directory and rebuilds
its occurrence table under the build's fingerprint version (`card-fingerprint-v4`), so there is no
separate rebuild to run (t20's report, A3 to A5).

**4. The counts to paste back** (about 3 minutes; counts only):

```zsh
for c in hsld26 hspolicy26 hspf26 openev; do jq -c '(.data // .error.details) | {caselist, version, sources, parsed, cards, unsupported, failed, elapsed_seconds, publish: .publish.counts}' ~/t24-dev-${c}.json; done
for c in hsld26 hspolicy26 hspf26 openev; do echo ${c}; find ~/.debate-research/dev/parsed/${c}/2026.10.20-docx-6/sha256 -name '*.jsonl' -print0 | xargs -0 jq -r 'select(.record == "document") | .document.cards[] | "\(if .tag == null then "no-tag" else "tagged" end) \(if any(.rule_ids[]; startswith("assembly-bold-tag-above-a-cite")) then "bold-tag" else "other" end)"' | sort | uniq -c; done > ~/t24-cards-after.txt
cat ~/t24-cards-after.txt
ls -d ~/.debate-research/dev/parsed/*/*
du -sh ~/.debate-research/dev/parsed
```

Expected, if nothing was imported after 2026-10-19:

| Caselist | Cards | `tagged bold-tag` | `no-tag` |
|---|---|---|---|
| hsld26 | 75,399 | 101 | 1,462 |
| hspf26 | 50,241 | 760 | 2,278 |
| hspolicy26 | 101,826 | 14 | 1,079 |
| openev | 8,081 | 0 | 78 |

`ls` shows two directories per caselist. After a pull, every figure is a little higher; send the
files as they are.

**5. The second run, which must parse and upload nothing** (about 20 minutes):

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
export DEBATE_ENV=dev
for c in hsld26 hspolicy26 hspf26 openev; do uv run debate-research --json caselist parse --caselist ${c} --publish | jq -c '.data | {caselist, version, attempted, skipped, elapsed_seconds, uploaded: .publish.counts.uploaded}'; done
```

Expected, for each caselist: `attempted` 0, `skipped` equal to the sources, and `uploaded` 0.

**6. The clusters against the `docx-5` table** (about 6, 4, 8 and 1 minutes; one command per
caselist):

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
uv run python scripts/compare_card_clusters.py counts --caselist hsld26 --before ~/.debate-research/dev/parsed/hsld26/2026.10.18-docx-5/occurrences.jsonl > ~/t24-clusters-hsld26.json; echo "exit $?"
uv run python scripts/compare_card_clusters.py counts --caselist hspf26 --before ~/.debate-research/dev/parsed/hspf26/2026.10.18-docx-5/occurrences.jsonl > ~/t24-clusters-hspf26.json; echo "exit $?"
uv run python scripts/compare_card_clusters.py counts --caselist hspolicy26 --before ~/.debate-research/dev/parsed/hspolicy26/2026.10.18-docx-5/occurrences.jsonl > ~/t24-clusters-hspolicy26.json; echo "exit $?"
uv run python scripts/compare_card_clusters.py counts --caselist openev --before ~/.debate-research/dev/parsed/openev/2026.10.18-docx-5/occurrences.jsonl > ~/t24-clusters-openev.json; echo "exit $?"
jq -c 'to_entries[] | {caselist: .key} + (.value | {before_version, after_version, cards_only_before, cards_only_after, exact_fingerprints_changed, clusters_before, clusters_after, clusters_merged_into_another, clusters_divided, largest_before, largest_after, seconds})' ~/t24-clusters-*.json
```

Expected: `exit 0` four times. Bodies change only for the cards above that lost their last
paragraph (28, 112, 10, 0) and the 5 that vanish in hspf26, so `exact_fingerprints_changed` should
be of that size, and openev's 0. Send the `jq` lines to the PM before step 7.

**7. The prod publish**, from the dev data directory, once the PM has read steps 4 to 6 (about 15
minutes). The session expires after about an hour of uploads, so log in again before each
caselist:

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
export DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev"
aws sso login --profile debate-prod-evidence
uv run debate-research --json caselist parse --caselist hsld26 --dry-run | jq -c '.data | {caselist, version, to_parse, skipped}'
uv run debate-research --json caselist parse --caselist hsld26 --publish --confirm-prod > ~/t24-prod-hsld26.json; echo "exit $?"
aws sso login --profile debate-prod-evidence
uv run debate-research --json caselist parse --caselist hspolicy26 --publish --confirm-prod > ~/t24-prod-hspolicy26.json; echo "exit $?"
aws sso login --profile debate-prod-evidence
uv run debate-research --json caselist parse --caselist hspf26 --publish --confirm-prod > ~/t24-prod-hspf26.json; echo "exit $?"
aws sso login --profile debate-prod-evidence
uv run debate-research --json caselist parse --caselist openev --publish --confirm-prod > ~/t24-prod-openev.json; echo "exit $?"
unset DEBATE_ENV DEBATE_STORAGE__DATA_DIR
```

The dry run must show `2026.10.20-docx-6` and `to_parse` 0; if it doesn't, the data directory is
wrong: stop. The `unset` at the end matters.

**8. Install a build that carries this task and reload the agent**, on a day other than Wednesday
morning, by the scheduled-sync runbook: `scripts/install_channel.sh` with the tag, its Step 2 and
Step 3, then `ops/launchd/install.sh --check-launchd`. The tag does not exist yet, so take the
commands from the runbook. Afterwards the agent's dry run should show `2026.10.20-docx-6` and
`to_parse` 0.

**9. Record it.** Whoever closes ac3 adds steps 4 to 6's figures to
`docs/data/caselist-parse-report.md`, under "The re-parse to `docx-6`", and sets the Goal
`Succeeded`.

**The search index must be rebuilt on `docx-6`.** `v1-e39-t02`'s search index refuses to publish
on a parser-version mismatch. That task is still `Pending`, so its index does not exist yet;
whenever it is built, build it from the `docx-6` store, after step 3 here.

## Follow-up work

- **For the PM to file: the 1 tag of 6 the rule leaves.**
  - *The stratum:* a line directly above a cite that opens a card with no tag, read as body or
    nothing, and not taken by the sampled rule. 3,573 lines on `docx-5`.
  - *What is not recorded:* the sample records counts only, so which of the six was the tag, and
    how it was formatted, is not known.
  - *Where it could be*, the 3,573 broken down by the first condition each line fails (read as
    `docx-5` read them):

    | First failing condition | Lines |
    |---|---|
    | Not bold, as Word shows it | 1,909 |
    | Bold in part, as Word shows it | 967 |
    | Read by an assembly rule or through a style | 288 |
    | Bold, over 300 characters | 221 |
    | Behind a style that maps to no unit | 92 |
    | Bold, below reading size | 91 |
    | Bold, names a source at its head | 5 |

    3,129 of them were read as body and 444 as nothing. "Bold in part" is the likeliest place for
    a tag the rule misses: a tag with a word left unbolded.
  - *Where a task would start:* draw from that stratum again by its first failing condition, have
    the operator describe the formatting of any that are tags, then count before ruling.
- **`v1-e33-t03`, the PM's amendment:** keep the writer's `HIGHLIGHTED_CITE_CAUSE` branch
  (`writer.py:672`) as a safeguard, and reach it with a writer-level test on a constructed card.
  Since ac4, no test reaches it.
- **`v1-e39-t02`:** build its index on `docx-6` (above).
- **The 417 bold lines above no cite, in files with bold defaults:** 3 of 10 were headings. They
  may be tags of cards with no cite, or blocks, typed with nothing set. They are not read now, and
  that is a separate question from this rule.
- **Scratch files** (counts, booleans and lengths only) were deleted on 2026-10-20, at the PM's word.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-20

**Notes:**

Accepted. Two small things happen in this session before the pull request (below). The pull
request then opens with `--partial`: ac3's re-parse is the operator's after the merge, and no task
depends on this one, so nothing is held back.

**What is good:**

* **The cause was found, not guessed.** Document defaults making every run bold at 13 pt is why the
  bold-heading rule never saw (7). Reading inherited formatting inside this rule only, as ruled,
  keeps the classifier unchanged everywhere else.
* **The before-and-after diff is the evidence I asked for:**
  * 875 cards gain a tag;
  * 150 cards above lose a paragraph;
  * 0 other cards change.
  * When the first run showed 160 "other" cards, you broke them down rather than explaining them
    away, and the script now tests each kind of change, including a real "other".
* **The figures agree with each other:** 875 = 101 + 760 + 14, and the operator's expected no-tag
  falls match them exactly (1,563 → 1,462; 3,038 → 2,278; 1,093 → 1,079). hspf26's 50,246 cards
  become 50,241 by the 5 that vanish.
* **The labelled evaluation is unchanged, score for score,** and `--write-baseline` was not passed.
* **The mutation survivors were handled honestly:** four got fixtures, and one check that no input
  reaches was deleted, with the hspf26 diff re-run to show nothing changed. 25 runs against a cap of
  about 20 is fine for that reason.

**Rulings:**

* **Deviation 6: both accepted.**
  * **The 100 heading-path-only cards** are the rule's reading followed through. A tagless card sits
    under the open tag above it, and that tag is now the taken line.
  * **The 5 cards that vanish** were never cards. They were a tag whose "body" was the next card's
    tag line, so becoming analytics is a fix, not a loss.
  * Record both categories beside the three numbers in `docs/data/caselist-parse-report.md`'s
    section, as the report already does.
* **Deviation 3: amend the spec in this session.**
  * Change "bracketed cite" to "a cite" in its title, description and ac2.
  * Add a comment: `PM ruling 2026-10-20: scope (a), the rule above any cite, with four guards`.
  * Keep the task id and file name.
  * Run `validate_specs.py`.
* **Deviations 1, 2, 4, 5 and 7:** accepted. The three extra refusals keep the rule inside what was
  sampled, which is what I want.
* **The 1 tag of 6 the rule leaves:** your breakdown is the right starting point. I will file a p3
  task that draws again from "bold in part", counts first.
* **The writer's `HIGHLIGHTED_CITE_CAUSE` branch:** the v1-e33-t03 amendment is in my next batch.
* **Scratch files:** delete them before the pull request.

**When the operator re-parses.** The agent runs Wednesday at 06:00 on `dev64`, which parses as
`docx-5`. The re-parse (steps 1 to 7) and the agent reinstall (step 8) belong on the same day, after
Wednesday's run has finished. Step 1's `caselist runs --last 1` is then also v1-e34-t17 ac5's
check. Steps 4 to 6 come to the PM before step 7, as you wrote. The PM records ac3 in a close-out.

**The search index (v1-e39-t02):** its measurement build now can stay on `docx-5`. The first
index that is published is built from the `docx-6` store, after step 3.

## PM record, 2026-10-22

Added by the PM. Nothing above is changed, and this section is not a review.

* **ac3, the re-parse:** run on 2026-10-21. Steps 4 to 6 came to the PM before step 7, as planned.
  Step 4's counts matched the expected table exactly; step 5 attempted and uploaded nothing; step 6
  found hsld26 11,650 clusters before and after, hspf26 10,144 then 10,142 (2 merged), hspolicy26
  18,767 and openev 5,846 unchanged, with 18, 55, 4 and 0 exact fingerprints changed and every
  largest cluster unchanged. Step 7 published to prod (4,973, 3,193, 4,440 and 107 objects, 0
  failed). Step 8 installed `1.1.0.dev85`. The figures are in
  [`docs/data/caselist-parse-report.md`](../data/caselist-parse-report.md#the-re-parse-to-docx-6-operator-run-after-the-merge),
  as step 9 asks.
* **The search index** was first published from the `docx-6` store, as the PM review asked: dev's
  `767b9c7c056b80cb` on 2026-10-22.
* **`2026.10.18-docx-5`** was retired in the dev bucket and on this machine on 2026-10-22; prod at
  the promotion.
* Every criterion is met, so the Goal is set to `Succeeded` in the PM batch of 2026-10-22.
