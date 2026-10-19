# Session report: v1-e31-t22-card-boundaries

| | |
|---|---|
| Task | `v1-e31-t22-card-boundaries` — Bodies too long to be one card, and two cards stored as one |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t22-card-boundaries.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t22-card-boundaries.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t22-card-boundaries` |
| Session status | IN PROGRESS: the counting script is built and tested; waiting for the operator's counts on the `docx-5` store (ac1). No parser rule is changed <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The PM's order is followed: counts first, then the sample, then the PM's ruling, and only then a
parser change. This session has built and tested the counting script, synthetic fixtures only, and
handed the operator one command to run once `v1-e31-t20`'s after-merge list (A1 to A13) has rebuilt
the local store at `2026.10.18-docx-5`. Nothing has been counted on real data yet, and no parser
rule, version or fixture has changed.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `card-boundaries`: Card boundaries | In progress | Counting script done; ac1 waits on the operator's run |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: before any rule changes, the operator-run counts for (1) and (2) per caselist, with (1) split by ending rule and by files that write tags | NOT RUN | Script built and tested; the operator's command is in [Operator follow-ups](#operator-follow-ups) |
| ac2: a sample of each, through v1-e31-t21's sampler, tallies only | NOT RUN | After ac1 |
| ac3: each defect has a synthetic fixture shown failing first; tag and cite precision and card boundaries do not fall | NOT RUN | After the PM's ruling |
| ac4: `parser_version` bumped; the operator's re-parse records (1) and (2) before and after | NOT RUN | After ac3 |
| Node: `uv run pytest packages/debate_core/tests -k "docx or parser"` | NOT RUN | Run before the report, with the PM's list of 2026-10-19 |

## The counting script

`scripts/count_card_boundaries.py`, with the logic in
`packages/debate_core/src/debate_core/evidence/card_boundaries.py`. Read-only; it prints counts
and rule-family names only.

**(1) Bodies too long to be one card.** Every stored card over 3,000 words, by whitespace words.
The store keeps no paragraphs, so each source holding one is parsed again from its blob by this
checkout's parser (still `docx-5`), and the card is described by its file's paragraphs. A card the
parse does not give back, with the same range and the same exact fingerprint, is counted as
`not_reproduced` and not described. The splits:

- **By ending:** the first paragraph after the card that the parser read as something: a tag in a
  debate style, a tag guessed from bold at a tag size, a pocket, hat or block, a tag with nothing
  under it, an analytic, a cite (starting a card with no tag), or the end of the file. The spec's
  split by ending is crossed with the split by files that write tags.
- **By whether the file writes tags at all:** any tag, including one demoted for having no card
  under it.
- **By whether the file uses any debate style:** a paragraph style the profile maps to a unit, or
  the cite character style. This is the PM's "files with no styles at all".
- **By what is inside** (first that applies), for the PM's things to check:
  1. *a short line above a cite-shaped paragraph*: a tag typed in body style above a cite the
     parser did not read;
  2. *a cite-shaped paragraph with no short line above*: cards separated only by their cites;
  3. *no cite inside, marked up* (at least 5% of characters underlined, emphasised or
     highlighted): one long card, or cards with neither tag nor cite between them;
  4. *no cite inside, plain prose*: a PF case or a speech written out.

  "Cite-shaped" means a name and a year within the first 40 characters of a paragraph of 2,000
  characters or fewer, once the body has begun. A "short line" is at most 300 characters, the
  classifier's heading length, and is not itself cite-shaped. The rule each cite-shaped paragraph
  was read by is tallied by its family.
- Also by word band, cards in the file, marked-up share, and whether the card has a tag and a cite.

**(2) Two cards stored as one.** Every distinct full body that holds two or more shorter bodies
whole that share no five-word run, by `CutIndex.containers` (the clusterer's own "holds": at least
as large, holding an end of the shorter, and containing nine-tenths of it or all of it but for one
word; a copy is not held). Counted in distinct texts and in the stored cards that carry them. The
looser count, two held bodies that do not overlap (under three-tenths shared), is beside it,
because that is the test `v1-e31-t20` refuses a witness by. Split by holder word band, whether the
smaller of the two is short (under 64 words), how many held bodies share nothing, and whether the
holder is also over 3,000 words.

`--save-candidates FILE` writes the store positions of what was counted (digests and indices, no
text), outside the repository, so the sample can draw from them without counting again.

### Tests, and the checks shown failing

- `packages/debate_core/tests/evidence/test_card_boundaries.py`: 54 tests on invented `.docx`
  files and numbered-word bodies. `tests/scripts/test_count_card_boundaries.py`: 9 tests on an
  invented store of six sources (a long card, a holding file, one source with no blob, and three
  whose blobs differ from what was stored, one per half of the "reproduced" check).
- `uv run --frozen pytest packages/debate_core/tests/evidence/test_card_boundaries.py tests/scripts/test_count_card_boundaries.py -n 0`
  → `63 passed`.
- **Mutation.** One textual change per run, both test files, a fresh `HYPOTHESIS_STORAGE_DIRECTORY`
  each run, the file restored from saved bytes and checked, `git status` checked after each batch.
  The first pass found 9 survivors:
  - six gaps, each given a test: a 300-character line above a cite, a paragraph left in `Normal`,
    the "not overlapping" candidates group, each half of the reproduction check, a marked-up share
    between 0 and 1%, and a card with no cite;
  - three checks no input reaches, deleted rather than tested: a completeness filter (a cite-only
    card has no words), keeping bodies of full cards only, and a unit check on the line above a
    cite (once a body has begun, a tag or a cite would have closed the card).

  Also, the word-count reproduction check became an exact-fingerprint check. **Final run on
  `9bc4f76`: 47 mutants, 47 caught**, 43 by assertion and 4 by a "did not raise" or an exception
  from a refused option. One caught mutant had written `scripts/candidates.jsonl` before failing.
  It was deleted, and the test now removes such a file itself.

## Files changed

- `packages/debate_core/src/debate_core/evidence/card_boundaries.py` (new): the long-body reading,
  the bodies holding two cards, and their tallies.
- `packages/debate_core/tests/evidence/test_card_boundaries.py` (new).
- `scripts/count_card_boundaries.py` (new) and `tests/scripts/test_count_card_boundaries.py` (new).

## Deviations from the spec

1. **`tests/scripts/test_count_card_boundaries.py` is outside `constraints.packages`,** which lists
   `scripts` but not `tests/scripts`, where every script's tests live
   (`test_compare_card_clusters.py`, `test_sample_cite_shapes.py`). The script's logic is in
   `debate_core.evidence` and tested in `packages/debate_core/tests`; only the reading of a store on
   disk is tested there.

## Decisions and assumptions

- **Words are whitespace words** for the 3,000 line (the spec's "words"). The holder bands in (2)
  are the clusterer's matching words, since (2) is the clusterer's measure.
- **The long-body reading runs on this checkout's parser.** It is `docx-5`, the store's version,
  and each card must come back with the same range and body or it is counted apart.
- **The "inside" kinds are guesses to be sampled, not verdicts.** The 5% marked-up line and the
  300-character short line are stated in the code.
- **openev is counted with the three caselists,** each on its own.

## Operator follow-ups

### 1. The counts (ac1): after A1 to A13 has rebuilt the local store at `docx-5`

Read-only: reads `~/.debate-research/dev` and writes two files in your home directory, the counts
and the positions counted (digests and indices, no text). It needs no AWS session. It stops by
itself if any caselist's newest version directory is not `2026.10.18-docx-5`. Expect 25 to 40
minutes: it reads every stored body, which `v1-e31-t20`'s step R2 took 4 to 8 minutes a caselist
for, and then works out containment as a cluster rebuild does. Don't run it while `caselist pull`
or `caselist parse` is running.

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e31-t22-card-boundaries
git log --oneline -1
uv run python scripts/count_card_boundaries.py --expect-version 2026.10.18-docx-5 --save-candidates ~/.debate-research/dev/card-boundaries-t22.jsonl > ~/t22-card-boundary-counts.json; echo "exit $?"
jq -c '.caselists | to_entries[] | {caselist: .key, version: .value.version, sources: .value.sources, cards: .value.cards, long_bodies: .value.long_bodies, two_cards_in_one: .value.two_cards_in_one, seconds: .value.seconds}' ~/t22-card-boundary-counts.json
```

Success: `git log` shows `9bc4f76` or a later commit of this branch, then `exit 0`, then four
lines, one a caselist, each naming `2026.10.18-docx-5`. Paste the four lines back: counts and rule
names only. If it stops with "not 2026.10.18-docx-5", the rebuild has not finished: run it again
afterwards.

## Follow-up work

None yet.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
