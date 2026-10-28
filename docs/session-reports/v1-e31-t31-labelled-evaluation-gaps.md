# Session report: v1-e31-t31-labelled-evaluation-gaps

| | |
|---|---|
| Task | `v1-e31-t31-labelled-evaluation-gaps` — Where the labelled evaluation's missed cites, tags and highlights go, counted before any rule |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t31-labelled-evaluation-gaps.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t31-labelled-evaluation-gaps.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t31-labelled-evaluation-gaps` |
| Session status | PARTIAL: phase 2 is built. The rules, the version, the before and after on both tiers, mutation, the store diff for openev and the dev re-parse steps are done. The other three caselists' store diff, the coach sample, the coach's look at one file and the re-parse are the operator's. The Goal stays `InProgress`, as the PM ruled <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Phase 2, built to the PM's rulings of 2026-10-27, and stopped there. The phase 1 record, with the
relay prompt the PM ruled on, is kept below [as it was sent](#relay-prompt-for-the-pm).

- **The rules (Q1 (a)).** Rules (1), (2) and (4) are built, as one assembly pass. They read as a
  cite:
  - a later line of a cite, or a line under a tag, read as nothing, with a link or a year, over a
    body;
  - a line read as a second tag under a tag, with a name and year at its head, over a body. The tag
    above gets its reading back.
- **White highlight (Q3 (a)).** White is no longer read as highlight; lightGray and black still are.
- **The version.** One bump for all four rules: `2026.10.27-docx-7`.
- **The labelled evaluation, `docx-6` → `docx-7`.**
  - Cite precision 0.985 → 0.989, recall 0.623 → 0.837.
  - Tag F1 0.935 → 0.959.
  - Labelled cards with no cite read: 31 → 10.
  - Non-Verbatim CITE F1 0.796 → 0.937 and Verbatim TAG F1 0.950 → 0.977 now meet their targets.
  - **No precision or F1 falls, by unit or by group, on either tier**, and no span or card figure
    falls. The pr-subset gate passes.
- **The store, openev (in the session, 19 s).**
  - 172 cards gain a cite and 259 cites gain a line.
  - 6 cards lose only white highlight, and no other card changes.
  - 142 of openev's 356 no-cite index documents gain a cite.
  - hsld26, hspf26 and hspolicy26 each run past two minutes; they are one operator block, which
    also writes the coach sample.

**For the PM first:**

1. **The dev re-parse cannot be done as the accepted plan has it.**
   - The code shows the cloud run parses only the caselists it imported that week, and has no
     parse-only mode. My relay's Q5 (ii) was wrong about that.
   - The steps below parse in full from a copy restored from the bucket, then publish.
   - That publish from a copy is in no runbook. The PM allowed it for this re-parse (ruling (a),
     2026-10-27), before the image's apply
     ([the code check](#the-re-parse-in-the-cloud-world-what-the-code-shows),
     [Deviation 4](#deviations-from-the-spec)).
   - [What C7 writes](#what-c7-writes-to-the-bucket): one object outside the version directory,
     the bucket's run lock.
2. **Two guards beyond the ruled shapes.** They keep `v1-e31-t12`'s deliberate pins
   ([Deviation 2](#deviations-from-the-spec)). The labelled counts are unchanged by them.
3. **The image-plan check in the cutover runbook stops on every image apply since the cutover**
   ([Deviation 5](#deviations-from-the-spec)).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `missed-units`: Missed units, counted then ruled | Built; the re-parse is the operator's | Counted (phase 1), ruled 2026-10-27, built red then green, version bumped, measured. `uv run pytest packages/debate_core/tests/integrations/docx_parser` → `1002 passed, 2 xfailed in 2.70s` |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the baseline's tiers re-measured on the `docx-6` store, recorded beside the 2026-10-20 figures in docs/data, without writing a baseline | PASS | Phase 1: `.venv/bin/python scripts/run_parser_eval.py --tier both` under `alarm 115` → both gates passed, 2.9 s. Every figure equals 2026-10-20's, by a whole-report diff. Recorded in [`parser-eval-gaps-2026-10.md`](../data/parser-eval-gaps-2026-10.md#re-measured-on-docx-6-2026-10-27). Run by the session ([Deviation 1](#deviations-from-the-spec), kept by the PM's Q6) |
| ac2: tallies of missed CITE, TAG and highlight rows, by caselist, template family and format, counts only, sent to the PM before any rule | PASS | Phase 1, `scripts/tally_missed_units.py`. Relay sent 2026-10-27; the PM ruled the same day. The first rule commit, `63bcfaa`, came after the ruling |
| ac3: each ruled rule a synthetic fixture shown failing first; the pr-subset gate holds; tag and cite precision do not fall; before and after in the report | PASS | [Red then green](#red-then-green): `63bcfaa` red, **5 failed, 6 passed**, with the 5 positives failing by assertion; `8b79d51` green. White: `7eff266` red, **3 failed, 35 passed**; `c1a2025` green. The gate passed on both tiers (`run_parser_eval.py --tier both`, 2.8 s). CITE precision 0.985 → 0.989, TAG precision 0.952 → 0.976, and no unit, span or card figure falls in any group on either tier (a script compared every group of the two reports). [Before and after](#before-and-after) |
| ac4, first half: `parser_version` is bumped once | PASS | `b893505`: `DOCX_PARSER_VERSION = "2026.10.27-docx-7"`, once for (1), (2), (4) and (H). `TestTheParserVersion` in `test_cite_lines_by_their_place.py` |
| ac4, second half: the operator's re-parse written out in full | NOT RUN | The dev steps are written as commands in [Operator follow-ups](#operator-follow-ups), each with where it runs and what success looks like. The full parse rests on a publish from a restored copy, which the PM allowed for this re-parse (ruling (a), 2026-10-27; [Deviation 4](#deviations-from-the-spec)). Prod is a separate E40 task, after `v1-e40-t10` (the PM's Q5). Running it is the operator's, after the merge, in the order the PM narrowed on 2026-10-27 |
| Node `missed-units`: `uv run pytest packages/debate_core/tests/integrations/docx_parser` | PASS | `1002 passed, 2 xfailed in 2.70s` (the two xfails are `v1-e31-t12`'s labelled leftovers) |
| `uv run scripts/validate_specs.py` | PASS | `OK: 480 files, 40 epics, 418 tasks, 22 releases`; phase `InProgress` |

## The PM's rulings, and what was built

**Q1 (a): rules (1), (2) and (4).**

- They are `DebateDocxParser._cite_lines_by_their_place`, with rule ids
  `assembly-cite-line-below-a-cite`, `assembly-cite-line-below-a-tag` and
  `assembly-cite-in-the-tag-style-below-a-tag`, at confidence 0.6.
- The pass reads one assembly, as the shapes were measured. When it takes a line, the build
  assembles once more, so the tag the assembly had demoted gets its reading back.
- A file the rules do not touch is built exactly as before.
- Each rule has its own fixture, failing first. (1)'s and (2)'s fixtures include the line with
  neither a link nor a year, which keeps its reading. (4)'s fixture shows the tag above read as a tag
  again.
- **Two guards were added beyond the ruled shapes** ([Deviation 2](#deviations-from-the-spec)):
  - no line longer than the profile's cite bound (1,000 characters);
  - no line longer than a cite line (400) that opens with a short cite.

  On the labelled files the rules still take exactly 23, 19 and 4 cites and nothing else.

**Q2 (b) and (c).**

- `scripts/diff_cite_lines_by_their_place.py` re-parses each stored source and compares its cards
  with the store's, by their last paragraph.
- It counts cards gaining a cite by shape, caselist and family, and follows the index's no-cite
  documents.
- openev ran in the session, in 19 s. hspolicy26 hit the alarm at 115 s, and hsld26 (about 140 s by
  a 400-source timing) and hspf26 (about 118 s) would too. All three go in one operator block, with
  the coach sample.
- `--sample-out` writes the sample only under the data directory, and refuses a path inside the
  repository.

**Q3 (a): white only.**

- `COLOURS_NOT_READ_AS_HIGHLIGHT` is in `style_classifier`, and `classify_run` gives a white run no
  `HIGHLIGHT` span.
- Tests show:
  - lightGray and black are still read;
  - search's `read_aloud_text` leaves white text out;
  - the lossless writer copies a white-highlighted paragraph as its source wrote it, `w:highlight`
    and all, and the card reads back as its source.
- [Every reader it reaches](#every-reader-the-white-change-reaches) is listed below.

**Q4.** No rule and no label change. The block that prints the file's path is
[Operator follow-ups](#operator-follow-ups) A.

**Q5.** The version is bumped once. The dev steps are written as commands, and checked against
the code; [what the code shows](#the-re-parse-in-the-cloud-world-what-the-code-shows) differs from
the accepted plan in one step.

**Q6.** Deviation 1 is kept.

## Red then green

| Commit | What | Tests |
|---|---|---|
| `63bcfaa` | Fixtures for the three cite rules | **5 failed, 6 passed**: the positives fail by assertion; the guards' negatives pass before and after |
| `8b79d51` | The three rules, with the two added guards | 11 passed. Without the guards, 10 of `v1-e31-t12`'s pins in `test_cite_detection.py` fail by assertion ([Deviation 2](#deviations-from-the-spec)) |
| `7eff266` | White-highlight tests: the parser's spans, search's read-aloud text, the writer | **3 failed, 35 passed**: the white span, the read-aloud text, and the writer test's white-span check fail by assertion; lightGray, black and the classifier's reading pass |
| `c1a2025` | White is not read as highlight | 2,786 passed over the parser, evidence and writer directories |
| `b893505` | `2026.10.27-docx-7` | 5,261 passed over the parser's, writer's and evidence's tests and `tests/evals` |
| `1cc899a` | Three edge fixtures from mutation | 17 in the rules' file |
| `6149497` | The store diff and the coach sample | 7 passed |

**What the version bump changed in other files:**

- the `parser_version` line of the ten structural expectations and the writer's four recorded
  sidecars, and nothing else in them;
- t24's version pin, restated as "this version or a later one", as t24 restated t19's;
- the writer's two version pins.

The tally tool's own tests now count with the cite-by-place pass left out, so that something is
missed. A new test shows `docx-7` misses none of the invented file's shapes.

## Before and after

The real parser, `run_parser_eval.py --tier both`, against the `docx-6` re-measure. The full tables
are in [the data document](../data/parser-eval-gaps-2026-10.md#after-the-ruling-20261027-docx-7).

| Full tier, overall | `docx-6` | `docx-7` |
|---|---|---|
| CITE precision / recall / F1 | 0.985 / 0.623 / 0.763 | 0.989 / 0.837 / 0.907 |
| TAG precision / recall / F1 | 0.952 / 0.919 / 0.935 | 0.976 / 0.942 / 0.959 |
| ANALYTIC precision | 0.845 | 0.896 |
| Highlight F1 / span F1 | 0.973 / 0.985 | 0.980 / 0.987 |
| Card boundary exact match / card precision | 0.889 / 0.863 | 0.911 / 0.885 |
| Labelled cards with no cite read (of 135) | 31 | 10 |
| Verbatim CITE F1 / TAG F1 (targets 0.97) | 0.751 / 0.950 | 0.895 / 0.977 (TAG MET) |
| Non-Verbatim CITE F1 / TAG F1 (targets 0.90) | 0.796 / 0.908 | 0.937 (MET) / 0.924 |

| PR subset, overall | `docx-6` | `docx-7` |
|---|---|---|
| CITE precision / recall | 0.969 / 0.705 | 0.973 / 0.818 |
| TAG precision / recall | 0.949 / 0.861 | 0.974 / 0.884 |
| Non-Verbatim CITE F1 / TAG F1 | 0.882 / 0.850 | 1.000 / 0.900 (both MET) |
| Verbatim highlight F1 | 0.695 | 0.756 |
| Gate | PASSED | PASSED |

These are the what-if figures for the ruled set: cite precision 0.989, recall 0.837, F1 0.907, and
10 cards with no cite. The what-if was right.

The 520 highlight characters still added are the cyan and green ones in `a888a5db95488218`, which
wait for the coach (Q4).

## The store

openev, in the session: `.venv/bin/python scripts/diff_cite_lines_by_their_place.py --caselist openev --index ~/.debate-research/dev/tub-index/767b9c7c056b80cb/search-index.sqlite --workers 8`
under `alarm 115` → exit 0, 19 s.

| openev | |
|---|---|
| Sources read / failed / without a blob | 102 / 0 / 0 |
| Cards that gain a cite: line under a tag / cite in the tag style | 166 / 6 |
| Cards whose cite gains a later line | 259 |
| Cards that lose only white highlight | 6 (85 white spans) |
| Any other card that changed; cards vanished; new cards | **0**; 0; 0 |
| Unchanged | 7,644 (of 8,081) |
| The index's 356 openev no-cite documents that gain a cite | 142 |

**How formatting is compared.** It is compared by the characters each emphasis covers
(`formatting_sha256`, the writer's own fidelity reading). My first run counted 3 cards as "other"
whose spans had only joined: when a white span between two underlines goes, the two underlines
become one span over the same characters. I checked that by printing the spans' emphases and offsets
only.

## Mutation testing

20 single-change mutants of the three rules, the guards and the white change. Each ran against the
four test files that cover them, in 0.2 to 0.8 s a run:

- `test_cite_lines_by_their_place.py`
- `test_white_highlight.py`
- `test_cite_detection.py`
- `test_fidelity.py`

Each run had a new, empty `HYPOTHESIS_STORAGE_DIRECTORY`; these files hold no property tests. The
source was restored from saved bytes and checked with `filecmp` after each run, and `git status` was
clean after.

- **17 caught on the first pass, all by assertion:**
  - no link check; no year check; no link-or-year guard;
  - no body asked below; a cite read as any unit above;
  - a demoted tag not a tag; a tag not a tag;
  - no name and year asked of a tag-style line;
  - no cite bound; no long-cite guard; the long-cite guard at 2,000;
  - no step over blank lines above; a blank line read as nothing;
  - no second assembly; the rules' ids swapped;
  - white read as highlight; lightGray not read either.
- **3 survived, and each now has a fixture** (`1cc899a`). All 3 are caught on re-run:
  - the tag-style line's 40-character head bound;
  - "under a tag" for a tag-style line;
  - stepping over a blank line between a line and its body below.

That is **23 runs**: 20 mutants and 3 re-runs, a little over the ~20 cap.

Apart from these, two checks were each shown failing for their reason:

- the tally tests (`4c1d114`, two mutants in phase 1);
- the store diff's effects test, with shape attribution switched off.

## Every reader the white change reaches

A white run now carries no `HIGHLIGHT` span, so each reader of a card's formatting spans sees no
highlight there. The run's `w:highlight` is still in the source file and in `RunDescription`.

| Reader | What changes |
|---|---|
| `domain/search_index.py` `read_aloud_text` (`_READ_ALOUD`), and so the index's `read_aloud` column | White text is no longer read aloud. Tested |
| `application/evidence_search.py` ranking (`read_aloud` weight 3.0) | White text no longer weighs as read aloud |
| `domain/search_index.py` `encode_formatting_spans`, and the index's `formatting_spans` column | No white span is stored |
| `domain/search_card_html.py` | No `card-highlight-white` class is drawn |
| `debate_api/copy_card.py` | No white highlight style in a copied card |
| `evidence/docx_renderer.py` (the E06 renderer) | Writes no white highlight in a rendered card |
| `evidence/card_boundaries.py` `marked_up_share` | A white run no longer counts as marked up |
| `domain/file_provenance.py` `formatting_sha256`, and so `evidence/file_checks/identity.py` and the writer's read-back (`writer.py:738`) | Both sides are parsed by the same parser, so they still agree. Tested: the white paragraph builds and reads back |
| `integrations/docx_file_writer` (the lossless writer) | Unchanged: it copies the source's paragraphs. Tested: the run and its `w:highlight` arrive as written |
| The classifier's `has_highlighted_run` (9 uses) | **Unchanged**: it reads the run's `w:highlight`, so a white run still marks a paragraph as marked up ([Decisions](#decisions-and-assumptions)) |

The fingerprint is unaffected: `evidence/fingerprints.py` reads text, not highlighting.

## The re-parse in the cloud world: what the code shows

The PM asked me to check, not assume. A subagent gathered the runbooks' blocks, and I read each
code claim myself:

- **A parser bump means a full parse, but only of the caselists the run imported that week.**
  - The parse stage parses `caselists_to_parse(tally.publish_targets)`, the caselists this run
    imported (`caselist_sync.py:4187`, defined at `:5090`).
  - For each, a parser version the store has no directory of starts an empty directory, so every
    live source is to parse (`application/caselist_parse.py:384-394`, and the skip key at `:347-356`). The run
    counts it as `full_parse` (`caselist_pull_parse.py:68`).
  - The module says so at `caselist_sync.py:292-299`: "A caselist the run did not import into is
    not touched".
- **There is no parse-only cloud run.**
  - The task runs `debate-research --json caselist pull` (`run_task.tf:84-85`).
  - `pull` takes `--caselist`, `--dry-run`, `--publish-pending` and `--full-archive`, and none of
    them parses without an import.
  - `v1-e40-t08` ("parse owed", Pending) would let a run parse what it did not import.
  - **My relay's Q5 (ii), "a run by hand with run-task overrides per caselist", does not exist.**
- **The run restores only its own parser version's parsed store** (`run_state.py:28-34` and
  `:347-349`; `container.py:1556`). A new-image run therefore restores no parsed store for a
  caselist not yet parsed by `docx-7`.
- **The index stage then fails.** It does not skip:
  - the build raises `SearchIndexStoreNotReady` when a store has no directory of either version
    (`search_index_build.py:552-559`);
  - the refresh skips only on `SearchIndexStoreVersionMismatch` (`search_index_refresh.py:463-470`).
  - So the first new-image run after a bump, before every store has a `docx-7` directory in the
    bucket, ends with its index stage failed, and `current.json` keeps the `docx-6` index.
- **What does work: a full parse of a restored copy.**
  - `caselist parse` in bucket mode fetches the raw sources a copy lacks from `raw/`
    (`container.py:840`).
  - It takes the bucket lock around its publish only (`commands/caselist_parse.py:168-176`).
  - `ops/caselist_run/compare_cloud_run.py` already restores a copy and parses it in full, without
    `--publish`.
  - The steps below do the same and publish. No runbook has published from a restored copy, and
    scheduled-sync's "One data directory for each bucket" warns against a second data directory
    publishing. Here the copy is the bucket's own state, restored under the lock, but that is the
    PM's call ([Deviation 4](#deviations-from-the-spec)).

### What C7 writes to the bucket

The PM's condition on ruling (a): the code for every key `caselist parse --publish` writes in bucket
mode. Read from the command down.

**1. The version directory: `parsed/<caselist>/2026.10.27-docx-7/`.** This is the publish, and its
only write call.

- `ParsedStorePublisher.publish` (`parsed_publish.py:183-218`) lists the local keys under
  `<caselist>/<version>/` (`:186`, `:193`).
- Of those keys it sends the per-source files under `sha256/` (`:196`), then the aggregates
  `index.jsonl`, `failures.jsonl` and `occurrences.jsonl` directly in the directory (`:197-199`,
  `:210`).
- Each goes through `_object`, whose one write is `self._remote.put_file(remote_key, path)`
  (`:288`), with `remote_key = parsed/` plus that local key (`:233`, `:256`).
- The version is `plan.version` (the CLI's `commands/caselist_parse.py:168-176`): the new `docx-7`
  directory, since the store holds none (`application/caselist_parse.py:384-394`).
- Everything else the publish does is a read: `list_objects` (`:194`), `head` (`:237`, `:269`,
  `:289`), and `get_file` of the bucket's occurrence table for the fingerprint guard (`:244`).

**2. The run lock: `reports/sync/run-lock.json`. This is outside the version directory.**

- The command publishes inside `run_holding_the_bucket_lock` (`commands/caselist_parse.py:168-176`;
  `bucket_lock.py`), which enters `BucketWriteGuard.held` (`run_lock.py`).
- In bucket mode that takes the lease: a conditional `replace` of the lock object (`run_lock.py:527`;
  `create` at `:557` only where none exists).
- It renews the lease every five minutes while the publish runs (`:697`).
- It releases with `state: free` (`:645`). The object is never deleted.
- The key is `RUN_LOCK_KEY` (`run_lock.py:105`). The lock's own docstring says every bucket-writing
  command holds it this way (`bucket_lock.py:1-8`).

**Nothing else.**

- The parse itself writes only the copy: `CaselistParseService.run` writes the local store.
- Its raw-source fetch reads `raw/` with `get_file` and writes the copy's blob tree
  (`run_state.py:376-409`).
- The suppression list is read, not written:
  - `entries()` and `path_holds()` read every copy (`suppression.py:268-279`, `:210-219`);
  - the one `reconcile()` is `restore-run-state`'s (`run_state_restore.py:140`, step C3), and writes
    only the copy, as its comment says (`:137-138`).
- No run-state bundle, manifest, run record or search index is written by `caselist parse
  --publish`.

**Why this stops at the checkpoint:** the PM's condition was "anything besides
`parsed/<caselist>/2026.10.27-docx-7/`". The run lock is an object besides it: not a bundle, manifest
or index, but a write all the same.

## The checks run before this report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` (measured first, as the PM asked) | **277 of 548 test files** (50.5%), from 29 changed files. That is well over two minutes, so it was not run in the session and is left to the pull request's `ci` (working agreement 10) |
| `.venv/bin/python -m pytest` under `alarm 115`, `-n 6 -m "not slow and not live"`, over the changed test directories and the always-run list: `docx_parser`, `docx_file_writer`, `evidence`, `tests/evals`, the four `tests/scripts` files of the eval and diff scripts, `tests/architecture`, `tests/specs`, the CLI's `test_app.py` and `test_help_rendering.py`, and `application/test_search_index_build.py` | `3560 passed, 2 xfailed in 31.20s` |
| `uv run pytest packages/debate_core/tests/integrations/docx_parser` (the node's criterion) | `1002 passed, 2 xfailed in 2.70s` |
| `.venv/bin/python scripts/run_parser_eval.py --tier both` under `alarm 115` | both gates PASSED, 2.8 s; `tests/evals/baselines/parser.json` unchanged |
| `uv run --frozen ruff format --check .` / `ruff check .` | `1531 files already formatted` / `All checks passed!` |
| `.venv/bin/python -m pyright`, the whole project as CI runs it | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` and `uv run --frozen python scripts/check_thin_handlers.py` | `Contracts: 18 kept, 0 broken.` and `OK: 67 ... within 25 statements` |
| `uv run python scripts/docs_index.py --check-descriptions` / `scripts/check_command_blocks.py --base origin/dev` | `All 56 indexed documents under docs/ have a description` / `OK` |
| `.venv/bin/python scripts/check_links.py` | `OK: 2751 relative links and anchors in 419 Markdown files` |
| `uv run scripts/validate_specs.py` | `OK` (phase `InProgress`) |

**CI on the pull request (#568), parts 2, 3, 4 and 8.** Four tests of `tests/scripts/test_sample_cite_shapes.py`
failed. That file was in the affected set but outside what the session ran. Its invented store's
"left, nothing" line (t19's stratum: a cite behind an unbolded first name, under a tag, with a year,
over a body) is now read as the card's cite by rule (2), the reading it was written for. So the
strata shifted by one. The file now switches t31's pass off, as it already switches t24's rule off
for t24's sample: its samples were planned before this task. Run locally:

- before the fix, `4 failed, 1193 passed` over the 48 affected files that read the parser and were
  not run before;
- after it, `19 passed` in that file.

**A killed run orphaned its workers.** When the alarm stopped the hspolicy26 diff, its pool's nine
workers outlived it. I found them by their command line (this worktree's virtualenv,
`spawn_main`), stopped those ten PIDs, and checked that none was left. Nothing they did writes
anywhere.

## What was counted, and how

**The re-measure.** `scripts/run_parser_eval.py --tier both` writes its reports to `build/eval-reports/`
(gitignored). The full report was rendered with `baseline_report_text`, the same function that wrote
`parser-eval-2026-10.md`, and the two were diffed. The only differences are the parser version
(`docx-5` → `docx-6`), the gate (`FAILED`: no baseline then; `PASSED` now) and the gate's note.

**The tallies.** `scripts/tally_missed_units.py` and
[`tests/evals/parser/missed_units.py`](../../tests/evals/parser/missed_units.py) read the same files
the same way the evaluation does: the path map, the key, the digest check, and the checkout's
parser. Its `ReadingParser` keeps each paragraph's description, the way `v1-e31-t24`'s count script
did. Nothing leaves it but counts:

- a rule is named by its family (the part before the first colon), because what follows can name a
  file's own style;
- a highlight colour is named only when the profile lists it;
- a file is named by its digest prefix, as `MANIFEST.md` does;
- `test_no_text_leaves_the_tally` checks this on the invented file.

**The what-if scores.** The what-ifs re-score the harness's own `Prediction` with a shape's
paragraphs read as cites:

- a tag that the assembly demoted only for want of a cite (`assembly-tag-without-cite-or-evidence`)
  is given back;
- card boundaries stay as the parser drew them, so these are unit and span scores only. ac3's
  before-and-after will be the real parser's.

The "as read" variant reproduces every published figure: CITE 0.9853/0.6233/0.7635, highlight F1
0.9731, span F1 0.9852, Verbatim CITE 0.751, non-Verbatim CITE 0.796.

**The index context** was counted read-only over the dev index the PM's note used
(`767b9c7c056b80cb`, opened `mode=ro`). Only `doc_id`, `cite`, `text` word counts and the
representative's `source_sha256` were read; no school or team column. Each source file was put in
its family with `scripts/survey_docx_styles.py`'s classifier, over the 2,679 blobs in the
operator's dev data directory: 10 s. Both of the note's totals reproduce (6,214 and 4,805). The
script stayed in the session's scratch directory and printed counts only.

**The tallies, the shapes and the what-if tables** are in the data document,
[`parser-eval-gaps-2026-10.md`](../data/parser-eval-gaps-2026-10.md). The relay below repeats what
the PM needs to rule.

## Relay prompt for the PM

```text
v1-e31-t31 (labelled evaluation gaps), phase 1 checkpoint, 2026-10-27. Counts only; nothing changed in the parser.

RE-MEASURE (ac1). The 2026-10-20 tiers on docx-6, no --write-baseline: every figure unchanged (whole report diffed). CITE precision 0.985, recall 0.623; Verbatim CITE F1 0.751, non-Verbatim 0.796; Verbatim span F1 0.971; PF highlight F1 0.759. Gate passes against the docx-5 baseline. Run by the session (read-only, 2.9 s).

TALLIES (ac2), full tier. Details: docs/data/parser-eval-gaps-2026-10.md.
- Cards: of 135 judged labelled cards, 72 have their whole cite read, 32 part of it, 31 none. The 31 are the gap students see.
- Cite rows: 81 of 215 missed. Read as nothing 64 (61 by no rule at all), as body 13, as a tag 4.
  Where they stand: 46 are a later line of a cite (36 directly under a line read as a cite, 10 further down); 28 directly under a tag; 4 under a tag the assembly demoted; 3 other.
  59 hold a link, 63 a year, only 12 a name and year at the head.
  By family: verbatim 46, other-heuristic 16, cardmirror 15, wiki-converted 4. By source: team 38, camp 35, caselist 8 (all hsld26, the eval's only caselist). By format: Policy 35, PF 28, LD 18.
- Tag rows: 14 of 173 missed. 4 are tags demoted to analytics because the cite below was read as a second tag. 7 are wiki-converted bold lines read as body (4 underlined). 1 is read as a hat, 1 as a cite, 1 as body in a CardMirror file.
- Highlight: nothing missed anywhere. All 707 wrong characters are ADDED highlight, all in one coach-reviewed team PF Verbatim file (a888a5db95488218, PR subset): cyan 449, green 71, white 187. No tracked change or hidden text explains them.
- Index context: the 6,214 no-cite documents by their representative's file family: other-heuristic 3,105 (2,375 with 100+ words), cardmirror 2,505 (1,941), verbatim 510 (422), wiki-converted 94 (67). hspf26 other-heuristic alone is 2,365. Both note totals reproduce.

PROPOSED RULES. Effects are the harness's own scores with the shape applied, full tier: cite P/R; "no cite" = cards with no cite read, as read 31. Each shape is counted over every labelled row; "other rows" is the precision cost.
(1) A line read as nothing, directly under a line read as a cite and directly over a body, holding a link or a year, is part of the cite. 23 cites, 0 other rows (22 Verbatim). P 0.987, R 0.730; no cite stays 31; cards with part of their cite 32 -> 11. Without the link-or-year guard it takes 3 body rows and 1 undertag (P 0.963), so the guard is part of the rule.
(1') The same for every line of a run of such lines between a cite and a body. 33 cites, 1 body row: P 0.982, R 0.777. It lowers cite precision, so it is a variant, not the recommendation.
(2) A line read as nothing, directly under a tag (or a tag demoted for want of a cite), directly over a body, holding a link or a year, is the card's cite. 19 cites, 0 other rows (other-heuristic 8, cardmirror 4, verbatim 4, wiki 3). P 0.987, R 0.712; no cite 31 -> 13. This is the shape of the index's other-heuristic and CardMirror gap.
(3) A line read as body, at most 400 characters, under a tag, over a body, with a link and no highlight, is the cite. 2 cites, 0 other rows. Too few to judge precision.
(4) A line read as a second tag, directly under a tag, over a body, with a name and year at its head, is the cite, and the tag above gets its tag reading back. 4 cites, 0 other rows. TAG P 0.952 -> 0.976, R 0.919 -> 0.942; ANALYTIC F1 0.789 -> 0.811.
(H) White highlight (the profile already marks it "not a reading colour") is not read as highlight. -187 added characters: highlight F1 0.973 -> 0.980, Verbatim span F1 0.971 -> 0.974, PR-subset Verbatim highlight 0.695 -> 0.756. Beyond the eval: search counts highlighted text as read aloud, so white text stops counting as read; the docx renderer and the search card HTML stop drawing an invisible white; the lossless writer copies a card's paragraphs from the source by their indices (v1-e33-t02), so it should be unaffected, and phase 2's writer tests would show it. No unit score moves.
Together, (1)+(2)+(3)+(4): cite P 0.985 -> 0.989, R 0.623 -> 0.847, F1 0.763 -> 0.912; tag F1 0.935 -> 0.959; no cite 31 -> 8. Verbatim CITE F1 0.751 -> 0.895 (P 0.979 -> 0.985); non-Verbatim CITE 0.796 -> 0.956 (target 0.90 met). PR subset: cite P 0.969 -> 0.973, R 0.705 -> 0.818; tag P 0.949 -> 0.974; no unit F1 falls.
(1)+(2)+(4) without (3): cite P 0.989, R 0.837, F1 0.907; no cite 10.
Left after all four: 33 cite rows (11 later lines the guard or the body test turns away, 10 third lines only (1') takes, 11 read as body) and 10 tag rows (8 read as body, 7 of them wiki-converted).
Not proposed: a tag rule for the 7 wiki-converted lines. Why t24's bold-tag rule does not take them is not counted here; the index has 94 wiki-converted no-cite documents, and the labelled rows are all in one source's wiki-converted files.

QUESTIONS
Q1. Which cite rules? (a) (1)+(2)+(4), (b) (a) plus (3), (c) (b) with (1') in place of (1), (d) other.
  Recommendation: (a). Each takes cites and nothing else, and together they meet the non-Verbatim cite target without lowering any precision. (3) rests on 2 rows. (1') lowers cite precision, which the spec forbids.
Q2. Count over the store before building? For each ruled shape, how many cards gain a cite, by caselist and family, and how many of the index's 6,214. That needs a re-parse of every source: t24's every-source count took 353 s, so it is the operator's. Options: (a) the operator, before 2026-11-01; (b) a before-and-after diff after the rule is built, in the session, one caselist at a time under two minutes each where it fits, as t24's diff was (175 s); (c) a coach sample of 20 lines of shape (2) as well.
  Recommendation: (b), plus (c) when the operator is back. (2) is the one shape whose non-cite neighbours the labels hardly cover.
Q3. White highlight (H)? (a) The parser stops reading white as highlight. (b) Leave it.
  Recommendation: (a), white only. It is invisible in Word, the profile already calls it not a reading colour, and today it counts as read aloud in search. lightGray and black are visible and stay.
Q4. Cyan (449) and green (71) characters in a888a5db95488218 that the coach labelled unhighlighted. The guide says any colour is highlight. Ask the coach to look at the file in Word. If they show as highlighted, a label correction needs your ruling (forbidden list); after (H) it would take PF highlight F1 to 1.000. If they don't, I'd look for what hides them.
  Recommendation: the coach looks; no parser rule either way.
Q5. The re-parse (ac4), rewritten for bucket mode. Proposed plan; no commands drafted yet.
  - The switch is the image, not the merge. The run's task definition pins its image by digest, so merging the bump into dev changes nothing until an image built from a release that carries it is pushed and applied. Coupling: ANY image applied after the merge, for any task, brings the full re-parse with it. So nobody applies a dev run image while the operator is away; or phase 2 merges after his return.
  - Dev, on his return:
    (i) a release with the bump; caselist_run_deploy.sh dry run, then push; the image-only apply, the PM reading the plan (caselist-cloud-run.md, "A new image, later").
    (ii) The full parse, as a run by hand: one-off run-task overrides per caselist, openev included, Thursday to Monday, under the bucket lock. Alternatively the next Wednesday run parses every imported caselist in full itself (full_parses > 0), but leaves openev on docx-6 until a camp file arrives. That is what the scheduled-sync runbook says of the Mac's agent; I assume the cloud run's parse stage does the same, which phase 2 would check. Recommend the by-hand run.
    (iii) The second run: the next scheduled Wednesday run, with full_parses 0 and only the week's imports parsed and uploaded.
    (iv) Clusters: compare_card_clusters.py against the docx-6 occurrence table, from a restore-run-state copy, not the Mac's data directory.
    (v) The search function and index together: a function deployed with the new parser turns card download off until an index built by the same parser is published (evidence-search runbook). So the tub deploy and the index publish go together.
  - Prod: published by hand from a copy restored from the dev bucket under the dev lock (caselist-cutover.md, "Until the promotion"), signed in to prod before each caselist. The copy holds the parsed store but no raw sources; whether a parsed-store publish needs them is v1-e40-t06's open question 2. That question decides whether prod's steps can be written.
  - Timing: the re-parse waits for the operator's return; dev and prod stay on docx-6 meanwhile.
  - The spec's ac4 wording ("dev, the second run, prod with a sign-in before each caselist, the cluster rebuild") predates bucket mode. Please amend it to this plan, or rule otherwise.
  Recommendation: this plan, with phase 2 merged but no run image applied until he is back.
Q6. ac1 says "(operator)"; the session ran it, read-only, in 2.9 s (working agreement 2). OK to leave as a Deviation?
```

## Files changed

**Parser (`debate_core.integrations.docx_parser`, `debate_core.evidence`):**

- `integrations/docx_parser/parser.py`: the three cite rules, the second assembly, and the version.
  t24's line-above loop now uses the shared `_line_above`.
- `evidence/style_classifier.py`: `COLOURS_NOT_READ_AS_HIGHLIGHT`, read by `classify_run`.

**Tests:**

- new: `packages/debate_core/tests/integrations/docx_parser/test_cite_lines_by_their_place.py` and
  `test_white_highlight.py`;
- new: `tests/scripts/test_diff_cite_lines_by_their_place.py`;
- changed: `.../docx_file_writer/test_fidelity.py`, the white paragraph's test and the version pin;
- changed: `test_writer.py`, `test_tag_above_a_cite.py`, the version pins;
- changed: `tests/evals/parser/test_missed_units.py`, which now counts with the pass left out.

**Fixtures:** `tests/fixtures/debate_files/structural/*.expected.json` and
`.../docx_file_writer/files_built_with_the_provenance_line/*.provenance.json`, the version line only.

**Scripts:**

- `scripts/tally_missed_units.py` (phase 1);
- `scripts/diff_cite_lines_by_their_place.py` (new);
- `tests/evals/parser/missed_units.py` (phase 1).

**Docs:**

- `docs/data/parser-eval-gaps-2026-10.md`, with the after-ruling section;
- this report.

## Deviations from the spec

1. **ac1 was run by the session**, read-only, in 2.9 s. The PM kept this (Q6).
2. **Two guards beyond the ruled shapes.**
   - Built as measured, rules (1) and (2) took long paragraphs that `v1-e31-t12` pins as "left as
     it was" on purpose:
     - 4,001- and 1,400-character styled lines;
     - 700-character lines that open with a name and year, have no bold opening or one-bracket
       shape, and hold a year.
   - 10 of t12's tests failed by assertion.
   - So no rule takes a line longer than the profile's cite bound (1,000 characters), or a line
     longer than 400 that opens with a short cite. The second is exactly the case t12's long-cite
     rule judged.
   - The longest labelled cites the rules take are 765, 488 and 540 characters. The labelled takes
     are unchanged (23, 19, 4, and no other row), and the guards cost 1 unlabelled line.
   - The PM accepted this; no separate ruling on t12's pins is needed.
3. **"White is not read as highlight" is read as the formatting spans.**
   - The classifier's `has_highlighted_run`, which decides units, still sees a white run, so a
     paragraph whose only marking is white is still marked-up body.
   - Changing that would move unit readings that no one measured.
   - `test_the_paragraph_is_read_as_it_was` pins the choice, so a later ruling changes one test.
4. **The dev full parse cannot be "by hand per caselist" in the cloud.**
   - No command parses a caselist the run did not import
     ([the code](#the-re-parse-in-the-cloud-world-what-the-code-shows)).
   - The steps below restore a copy under the lock, parse it in full with the installed `docx-7`
     build in bucket mode, and publish each caselist's version directory with `caselist parse
     --publish`. No runbook has published a parsed store from a restored copy. **The PM allowed it
     for this re-parse** (ruling (a), 2026-10-27), with C6 and C7 before the image's apply (C8).
   - The other way is to wait for `v1-e40-t08` (a run parses what is owed without an import),
     extended to a parse every caselist owes after a bump.
5. **The cutover runbook's image-plan check refuses every image apply since the cutover.**
   - `IMAGEPLAN` stops when `owner.auto.tfvars` enables the run's schedule
     (`caselist-cutover.md:357`), and it expects the schedule `DISABLED` (`:349`).
   - "A new image, later" (`caselist-cloud-run.md:746`) points at step 6's plan, which is the
     first apply's shape.
   - The PM's batch adds a post-cutover plan block to "A new image, later". C5's plan and C8's
     apply point at it, and use its reading in place of `IMAGEPLAN`.
6. **Outside `constraints.packages`:**
   - the structural fixtures' and the writer sidecars' version lines;
   - the writer's test directory (version pins, and the white paragraph test the PM asked for);
   - `tests/fixtures` and the writer tests, which are not in the list, as for t24.
7. **23 mutation runs**, against the ~20 cap: 20 mutants and 3 re-runs.
8. **My relay's Q5 (ii) was wrong.** It proposed "a run by hand: one-off run-task overrides per
   caselist", and no such run exists. The PM accepted the plan on that premise. The code check is
   above.

## Decisions and assumptions

- **The version is `2026.10.27-docx-7`**, dated the day of the ruling.
- **The cite rules read one assembly** and take what it shows, as the shapes were measured. A line
  one rule takes does not make a second line another rule's.
- **The confidence is 0.6**, a cite line's (`heuristic-cite-line-author-year`).
- **The store diff compares formatting by characters covered**, as the writer's fidelity check does.
  Spans that join where a white span was are no change.
- **The diff reads the PM note's index (`767b9c7c056b80cb`)**, not the Mac's newest. Its 6,214 are
  the documents the PM named.
- **The coach sample's path:**
  - `~/.debate-research/dev/parser-eval/cite-lines-by-their-place/coach-sample-20261027.csv`;
  - the seed is 20261027, the ruling's date;
  - a `.key.jsonl` beside the CSV says which file and paragraph each row is, for scoring later. It
    is under the data directory, never the repository.

## Operator follow-ups

**Merge order** (the PM's Q5, narrowed by the PM on 2026-10-27 in
[the section at the end of this report](#the-merge-order-narrowed-recorded-by-the-pm-2026-10-27)):

- The phase 2 pull request may merge once the validate-dev run is green for the tag that Thursday
  2026-10-29's image (`v1-e40-t13`) is built from. That image is built from a tag cut before this
  PR merges, and its Terraform runs from a worktree at that tag's commit, so it does not carry
  `docx-7`.
- Images may be deployed while the operator travels. **No run image carrying `docx-7` is applied
  until C7 has published all four caselists' `docx-7` directories**, wherever and whenever C7 is
  run, or until `v1-e40-t08` lets the run parse what a bump owes. The switch is the image, not the
  merge: any run image built from a release after the merge carries `docx-7`, so it waits for C7
  too.
- The re-parse runs Thursday to Monday, never during a Wednesday run.
- The image also waits for the coach's sample, whatever it says (Q2 (c)). If fewer than 18 of 20 are
  cites, rule (2) is removed before any run image carries it.

### A. The path of the file the coach looks at (Q4)

Any time. It prints the local path to your terminal only. Do not paste it into the session or the
report. The coach opens the file in Word and says whether the cyan and green passages show as
highlighted.

**Operator command** (expected runtime under a second)
Where: your Mac, any directory

```bash
python3 -I -c 'import json, os; m = json.load(open(os.path.expanduser(os.environ.get("DEBATE_PARSER_EVAL_PATHS") or "~/.debate-intelligence/parser-eval-paths.json"))); found = [p for d, p in m.items() if d.startswith("a888a5db95488218")]; print(found[0] if len(found) == 1 else "STOP: found " + str(len(found)))'
```

Success looks like one absolute path. `STOP: found 0` means the path map does not hold the file.

### B. The store diff for hsld26, hspf26 and hspolicy26, and the coach sample (Q2 (b), (c))

This must run **before** the re-parse. The store's newest version directory must still be
`2026.10.20-docx-6`, so run it from this task's worktree before or after the merge, but before step
C7.

- It is read-only over the store, the blobs and the index.
- It writes only the coach's CSV and its key, under the data directory.
- The JSON it prints is counts only. The CSV holds lines of the files, so it is for the coach, and
  its rows are never pasted into the session.

**Operator command** (expected runtime ~8 to 10 minutes: about 140 s for hsld26, 120 s for hspf26,
over 115 s for hspolicy26, 20 s for openev)
Where: your Mac, in the task worktree

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e31-t31-labelled-evaluation-gaps
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; else uv run python scripts/diff_cite_lines_by_their_place.py --index ~/.debate-research/dev/tub-index/767b9c7c056b80cb/search-index.sqlite --sample-out ~/.debate-research/dev/parser-eval/cite-lines-by-their-place/coach-sample-20261027.csv --seed 20261027 > ~/t31-store-diff.json; echo "exit $?"; fi
jq -c '.caselists | to_entries[] | {caselist: .key} + (.value | {version, sources, sources_read, failed, without_a_blob, gaining: .cards_gaining_a_cite.all, growing: .cards_whose_cite_gains_a_line.all, white_only: .cards_losing_only_white_highlight, other: .other_cards_changed, vanish: .cards_the_store_holds_that_vanish, new: .new_cards, index: .index_no_cite_documents, index_gaining: .index_no_cite_documents_gaining_a_cite.all, seconds})' ~/t31-store-diff.json
jq -c '.sample' ~/t31-store-diff.json
```

Success looks like:

- `exit 0`, then four lines, each with `version` `2026.10.20-docx-6`, `sources_read` equal to
  `sources`, `failed` 0, and `other` `{}`;
- the four `index` counts sum to 6,214;
- `.sample` says `rows_written` 20, or every file there is if fewer.

Paste back the five `jq` lines. `version` `2026.10.27-docx-7` means the store was already re-parsed:
stop. An `other` that is not `{}` is a change I did not expect: paste it as it is.

**For the coach.** The CSV's columns are `sample_row, line, tag_above, body_below_first_200,
verdict`. Write `cite`, `not cite` or `unsure` in `verdict` for each row. Then send the PM the three
counts only. The bar is at least 18 of 20 cites.

### C. The dev re-parse, after the merge

Run in this order, Thursday to Monday, never during a Wednesday run (the PM's ruling (a) on
[Deviation 4](#deviations-from-the-spec), 2026-10-27).

- C1 to C4 and C6 are read-only or local.
- C5 (the image's dry run, push, digest line and plan) may run before or after C6 and C7.
- **C7 publishes each caselist's `docx-7` directory before the image is applied.** C8, the apply,
  follows only after all four C7 publishes exit 0.

**Why this order.** A `docx-6` run ignores a `docx-7` directory: the run restores only
`parsed/<store>/<its own parser version>/` (`run_state.py:349`, with the version from
`container.py:1555`). So a failed C7 changes nothing the weekly run reads. Once C8 applies the
`docx-7` image, every store the next run's index stage reads already holds `docx-7`.

**Time and disk:**

| Step | Time |
|---|---|
| C3 restore | a few minutes, about 15,000 parsed objects |
| C7 parse and publish | unmeasured: the Mac's full parse took about 30 minutes in October, plus fetching every raw source from `raw/` |
| C10 clusters | about 20 minutes |

Have at least 10 GiB free.

**C1. The worktree on `dev`, with the merge** (seconds). Where: your Mac.

```bash
WT="$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/caselist-credentials-dev"
cd "$WT" || { echo "WT does not exist: $WT"; }
git fetch origin
git switch --detach origin/dev
git log --oneline -1 --grep='^v1-e31-t31-labelled-evaluation-gaps:'
grep -c 'DOCX_PARSER_VERSION: Final = "2026.10.27-docx-7"' packages/debate_core/src/debate_core/integrations/docx_parser/parser.py
date +%A
df -h "$HOME" | tail -1
```

Success looks like:

- one log line, then `1`;
- a day that is not Wednesday;
- at least 10 GiB available.

No log line means the merge is not on `dev`: stop.

**C2. The release that carries it** (seconds). Where: `$WT`.

```bash
cd "$WT"
gh release list --repo charlesclark2/debate-intelligence --limit 3 --json tagName,createdAt --jq '.[] | .tagName + " " + .createdAt'
TAG="$(gh release list --repo charlesclark2/debate-intelligence --limit 1 --json tagName --jq '.[0].tagName')"
echo "TAG=$TAG"
git fetch origin tag "$TAG" --no-tags
git show "${TAG}:packages/debate_core/src/debate_core/integrations/docx_parser/parser.py" | grep -c 'DOCX_PARSER_VERSION: Final = "2026.10.27-docx-7"'
```

Success looks like `TAG=<a dev pre-release>` and `1`. `0` means the newest release predates the
merge: wait for the next dev pre-release, whose validate-dev run (image job included) is green.

**C3. The copy, restored with the build still installed** (a few minutes). Where: your Mac.

The installed `docx-6` build restores the `docx-6` parsed store, which is the "before" the clusters
are compared with in C10. It holds the bucket lock while it restores.

```bash
cd "$HOME"
debate-research --json --version | python3 -I -c 'import json, sys; print(json.load(sys.stdin)["data"]["tag"])'
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif pgrep -fl 'debate-research( --json)? caselist pull'; then echo "STOP: a caselist pull is running (above)"; else DEBATE_ENV=dev debate-research caselist restore-run-state --into "$HOME/.debate-research/t31-reparse-copy" > "$HOME/t31-restore.txt" 2>&1; echo "exit $?"; tail -5 "$HOME/t31-restore.txt"; fi
ls "$HOME/.debate-research/t31-reparse-copy/parsed/"*
```

Success looks like:

- a tag older than `$TAG`, then `exit 0`;
- `ls` showing `2026.10.20-docx-6` under each of `hsld26`, `hspf26`, `hspolicy26` and `openev`.

`exit 1` means a runner holds the lock: wait for it and run again with a new, empty directory.

**C4. Install the release on the Mac** (~2 min). Where: `$WT`, in the shell that set `TAG`.

```bash
cd "$WT"
if [ -z "$TAG" ]; then echo "STOP: TAG is not set; run C2 first"; else scripts/install_channel.sh "$TAG" 2>&1 | tail -5; fi
```

Success ends with the build's `complete` line. Then run the cutover runbook's "Every build this Mac
can run is one with the lock" block (`caselist-cutover.md`, step 3). Every `==` line must name
`$TAG`, `bucket` and `['hsld26', 'hspolicy26', 'hspf26']`.

**C5. The run's image: dry run, push, digest, plan.** Where: `$WT`. Before or after C6 and C7; its
apply is C8.

The dry run (several minutes):

```bash
cd "$WT"
if [ -z "$TAG" ]; then echo "STOP: TAG is not set"; elif env | grep -qE '^(CASELIST_RUN_DEPLOY_PROFILE|DEBATE_RELEASE_REPO)='; then echo "STOP: a deploy override is set in this shell"; else time scripts/caselist_run_deploy.sh dev "$TAG" --dry-run; fi
```

Success looks like seven `ok:` lines, then `Dry run complete. debate-dev-caselist-run:<tag> built
and checked`.

The push. This also registers a run task definition that a run by hand would use, but the schedule
does not move until the apply.

```bash
cd "$WT"
aws sso login --sso-session debate
if [ -z "$TAG" ]; then echo "STOP: TAG is not set"; elif env | grep -qE '^(CASELIST_RUN_DEPLOY_PROFILE|DEBATE_RELEASE_REPO)='; then echo "STOP: a deploy override is set in this shell"; else scripts/caselist_run_deploy.sh dev "$TAG" 2>&1 | tee /tmp/caselist-run-deploy.txt | tail -8; fi
grep -E '^pushed: |^registered: |caselist_image_digest = ' /tmp/caselist-run-deploy.txt
```

Success looks like `pushed: …@sha256:<64 hex>`, a `registered:` line, and the
`caselist_image_digest = "sha256:…"` line.

The digest line: use the replacement block of `caselist-cloud-run.md`, "A new image, later",
unchanged. Success is its `replaced:` line, then `1`.

The plan: run the post-cutover plan block of `caselist-cloud-run.md`, "A new image, later", which the
PM's batch adds ([Deviation 5](#deviations-from-the-spec)). Read it as that section says, in place of
the cutover's `IMAGEPLAN`. **Send the PM the plan's lines and that reading.** The apply is C8, and
waits for C7 and for the PM.

**C6. The full parse's dry run, in the copy** (seconds; writes nothing). Where: your Mac.

```bash
cd "$HOME"
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; else for c in hsld26 hspolicy26 hspf26 openev; do env DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/t31-reparse-copy" debate-research --json caselist parse --caselist ${c} --dry-run | jq -c '.data | {caselist, version, sources, to_parse, skipped}'; done; fi
```

Success looks like four lines with `version` `2026.10.27-docx-7`, `to_parse` equal to `sources` and
above zero, and `skipped` 0. `version` `2026.10.20-docx-6` means the installed build is the old one:
stop.

**C7. The full parse and publish, one caselist at a time** (unmeasured; see the table). Where: your
Mac. Before C8. [What it writes to the bucket](#what-c7-writes-to-the-bucket) is listed above.

First the lock and the session:

```bash
cd "$WT"
BUCKET=$(AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output -raw evidence_bucket_name)
aws sso login --profile debate-dev-evidence
LOCK_STATE=$(aws s3 cp "s3://${BUCKET}/reports/sync/run-lock.json" - --profile debate-dev-evidence | python3 -I -c 'import json, sys; print(json.load(sys.stdin)["state"])')
echo "lock ${LOCK_STATE}"
```

Success looks like `lock free`.

Then the parse and publish:

```bash
cd "$HOME"
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif [ "$LOCK_STATE" != "free" ]; then echo "STOP: the lock is ${LOCK_STATE}, not free"; elif [ "$(date +%A)" = "Wednesday" ]; then echo "STOP: not on a Wednesday"; else for c in hsld26 hspolicy26 hspf26 openev; do env DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/t31-reparse-copy" debate-research --json caselist parse --caselist ${c} --publish > "$HOME/t31-dev-${c}.json"; echo "${c} exit $?"; done; fi
for c in hsld26 hspolicy26 hspf26 openev; do jq -c '(.data // .error.details) | {caselist, version, sources, parsed, cards, unsupported, failed, publish: .publish.counts}' "$HOME/t31-dev-${c}.json"; done
```

C8 waits for all four to exit 0. Success looks like four `exit 0`, then four lines with `version`
`2026.10.27-docx-7`, `parsed` above zero and equal to `sources` less `unsupported`, `failed` 0, and a publish count above zero. On
`PARSED_PUBLISH_INCOMPLETE`, run that caselist's parse line again. Paste back the four `jq` lines.

**C8. The image's apply: C5's, moved here by the PM's ruling.** Where: `$WT`. Only after all four
C7 publishes exit 0, and after the PM has read C5's plan.

Apply with the apply block of `caselist-cloud-run.md`, "A new image, later", using the plan its plan
block wrote in C5.

Success looks like `Apply complete! Resources: 2 added, 4 changed, 2 destroyed.`, and the run's
schedule `ENABLED`. One `-login-task-changed` email is expected. **From this apply on, the next
Wednesday run uses `docx-7`**, and every store it reads already holds `docx-7`.

**C9. The second run: the next scheduled Wednesday run** (it starts at 06:00 and takes up to about
2.5 hours). Where: your Mac, after it has finished.

```bash
cd "$HOME"
aws sso login --profile debate-dev-evidence
DEBATE_ENV=dev debate-research --json caselist runs --remote --last 1 | jq -c '.data.runs[0] | {parse: .details.parse, stages: [.stages[] | select(.stage == "parse" or .stage == "search_index")]}'
```

Success looks like:

- `full_parses` 0, with only that week's imports parsed;
- the `search_index` stage built and published an index.

A failed `search_index` stage means a store the run read has no `docx-7` directory. Paste the line
to the PM.

**C10. The clusters against the `docx-6` tables** (about 20 minutes). Where: `$WT`. This reads the
copy only.

```bash
cd "$WT"
for c in hsld26 hspolicy26 hspf26 openev; do uv run python scripts/compare_card_clusters.py --data-dir "$HOME/.debate-research/t31-reparse-copy" counts --caselist ${c} --before "$HOME/.debate-research/t31-reparse-copy/parsed/${c}/2026.10.20-docx-6/occurrences.jsonl" > "$HOME/t31-clusters-${c}.json"; echo "${c} exit $?"; done
jq -c 'to_entries[] | {caselist: .key} + (.value | {before_version, after_version, cards_only_before, cards_only_after, exact_fingerprints_changed, clusters_before, clusters_after, clusters_merged_into_another, clusters_divided, largest_before, largest_after, seconds})' "$HOME"/t31-clusters-*.json
```

Success looks like four `exit 0`, and each line `before_version` `2026.10.20-docx-6`,
`after_version` `2026.10.27-docx-7`. A card's body does not change under these rules, only its cite
and, for the tag-style shape, its tag and first paragraph. So expect few `exact_fingerprints_changed`.
Paste the four lines.

**C11. The search function, with the index C9 published** (minutes; the same day as C9). Where:
`$WT`.

The function's parser must match the index's, or card download is off (`evidence-search.md`,
"Download is off"). The dry run:

```bash
cd "$WT"
uv sync --all-packages
scripts/tub_deploy.sh dev --dry-run
```

Then the deploy:

```bash
cd "$WT"
scripts/tub_deploy.sh dev
```

Success looks like `{"status":"ok"}` and `Deployed <sha> to dev`. Download is back within five
minutes.

**C12. Remove the copy** (seconds). Where: your Mac. First see what goes:

```bash
du -sh "$HOME/.debate-research/t31-reparse-copy"
ls "$HOME/.debate-research/t31-reparse-copy"
```

Then, once C10's lines are pasted:

```bash
rm -rf "$HOME/.debate-research/t31-reparse-copy"
```

## Follow-up work

- **A cloud parse after a parser bump.** `v1-e40-t08`'s "parse owed", extended so a run parses every
  caselist a new parser version owes, would replace C3, C6 and C7 with the scheduled run. The PM
  files it (E40).
- **The cutover runbook's `IMAGEPLAN`** needs a form for an image after the cutover, and "A new
  image, later" should point at it (E40).
- **Prod's re-parse:** a separate E40 task after `v1-e40-t10`, as the PM ruled.
- **The 7 wiki-converted tag rows**, from phase 1, are still not proposed for a rule.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-27

**Notes:**

Phase 2 is built to the rulings, measured honestly, and the code check corrected the plan's one
wrong premise before anyone ran it.
1. **ac3 passes.**
   * Each rule is red first, failing by assertion; white is red first too.
   * Full tier: CITE 0.985/0.623 to 0.989/0.837, TAG F1 0.935 to 0.959, and labelled cards with no
     cite fall from 31 to 10. Non-Verbatim CITE and Verbatim TAG now meet their targets.
   * No precision or F1 falls, by unit or by group, on either tier, and the gate passes. The ruled
     set's what-if figures were exact.
2. **ac4's first half passes:** one bump, `2026.10.27-docx-7`. The second half (the re-parse) is
   the operator's, after the merge and his return, so the PR merges `--partial` and the Goal stays
   `InProgress`.
3. **openev's store diff** is clean: 172 cards gain a cite, 259 cites gain a line, 6 cards lose only
   white highlight, and 0 others change. 142 of openev's 356 no-cite documents gain a cite.
4. **Mutation: 20 mutants and 3 re-runs.** The 3 survivors each became a fixture and are caught.
5. **Deviation 2 accepted:** the two guards keep `v1-e31-t12`'s deliberate pins. The labelled takes
   are unchanged (23, 19 and 4, nothing else), and the guards cost 1 unlabelled line. No separate
   ruling on t12's pins is needed.
6. **Deviation 3 accepted:** white leaves the formatting spans only, and unit readings don't move.
7. **Deviation 4: ruling (a), the publish from a restored copy is allowed for this re-parse, with
   two conditions.**
   * **Order:** C6 and C7 (the full parse and the publish of each caselist's `docx-7` directory)
     run **before** C5's apply, in the same Thursday-to-Monday window. C5's apply follows only after
     all four publishes exit 0. A docx-6 run ignores a `docx-7` directory, so a failed C7 changes
     nothing the weekly run reads. The image is applied only once every store the next run's index
     stage reads holds `docx-7`.
   * **What C7 writes:** before the merge, the session cites the code for every key `caselist parse
     --publish` writes in bucket mode. If anything besides `parsed/<caselist>/2026.10.27-docx-7/`
     is written (a run-state bundle, a manifest or an index), the session stops and says so.
   * The lasting fix is the PM's new E40 task: after a parser bump, the scheduled run parses every
     caselist the new version owes. It extends `v1-e40-t08`.
8. **Deviation 5 taken:** the PM's batch of 2026-10-27 (u) adds a post-cutover plan block to
   `caselist-cloud-run.md`, "A new image, later": Plan 2/4/2, the two task definitions replaced, no
   Identity Center change, and no schedule state change. C5 and Thursday's `v1-e40-t13` apply use
   it. A check script of its own is an E40 follow-up.
9. **Deviations 1, 6, 7 and 8 accepted.** The PM's batch adds the writer tests and `tests/fixtures`
   to `constraints.packages`.
10. **Operator follow-ups A and B** may run before 2026-11-01, from this task's worktree. Both are
    read-only, and B writes only the coach's file under the data directory. The coach's sample bar
    stands: at least 18 of 20 cites, or rule (2) comes out before any run image carries it.
11. **Merge order stands:** the PR merges only after Thursday 2026-10-29's image apply. After it
    merges, no dev run image is applied until the operator is back.
12. **The affected set** (277 files) is left to the PR's `ci` under agreement 10. The changed
    directories and the always-run list passed (3,560), and so did pyright, ruff, the import
    contracts and the docs checks.

After the session's two edits (the C-step order and the C7 key check), the PR merges `--partial`.
No re-review is needed unless the key check finds a write beyond the version directory.

### The merge order narrowed, recorded by the PM 2026-10-27

The coach's word: the weekly run, its login and its alerts are in the cloud, and images may be deployed
while he travels. Note 11's "no dev run image is applied until the operator is back" is withdrawn.
What stays is the ordering it protected: **no run image carrying `docx-7` is applied until C7 has
published all four caselists' `docx-7` directories**, wherever and whenever C7 is run (or until
`v1-e40-t08` lets the run parse what a bump owes). Thursday 2026-10-29's image is built from a tag cut
before this PR merges, and its Terraform runs from a worktree at that tag's commit, so this PR may merge
once that tag's validate-dev run is green.

### The two edits and the `ci` fix, checked by the PM 2026-10-27

Recorded under the review above, which stands. The two edits the first review asked for are made, and the one fix the PR's `ci` needed is right.
1. **The C steps are reordered as ruled.** C5 now pushes and plans without applying. C6 and C7 parse
   and publish every caselist's `docx-7` directory, and C8 applies the image only after all four C7
   publishes exit 0 and the PM has read C5's plan. The reason under the C heading is cited from the
   code (`run_state.py:349`).
2. **The C7 key check is accepted: ruling (a), recorded here.** `caselist parse --publish` writes
   `parsed/<caselist>/2026.10.27-docx-7/` through one `put_file` call, and the bucket's run lock
   (`reports/sync/run-lock.json`: taken, renewed, released `free`). The lock is the concurrency
   control ruling (a) relies on, and every bucket-writing command holds it. It is no bundle, manifest
   or index, so the condition holds. The section's closing "Why this stops at the checkpoint" is the
   question as it was asked, and this note answers it.
3. **The `ci` fix is accepted.** `tests/scripts/test_sample_cite_shapes.py` failed 4 tests on PR #568
   because its invented "left, nothing" line is now read as a cite by rule (2), the reading the rule
   was written for. Switching t31's pass off in that sampler, as it already does for t24's rule, is
   right: its strata were planned before this task. The 48 affected files that read the parser
   passed locally after the fix, and the PR's `ci` is the check.
4. **The merge order** is the narrowed one recorded above. The PR merges `--partial` once Thursday
   2026-10-29's tag has a green validate-dev run. No run image carrying `docx-7` is applied until C7
   has published all four caselists.

No further review is needed.
