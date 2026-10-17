# Session report: v1-e31-t21-cluster-shapes-and-sampler

| | |
|---|---|
| Task | `v1-e31-t21-cluster-shapes-and-sampler` — Measure cluster shapes, and ask a person only about the pairs a rule cannot decide |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t21-cluster-shapes-and-sampler.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t21-cluster-shapes-and-sampler.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t21-cluster-shapes-and-sampler` |
| Session status | COMPLETE for the session; the two operator-run criteria (ac2, ac4) are NOT RUN, so the Goal stays `InProgress` |

## Summary

`scripts/compare_card_clusters.py` has a new `shapes` command and a sampler that asks a person only
about the pairs a rule cannot decide. `shapes` sorts every pair of a cluster's distinct full texts
into one of six shapes: identical; contained, either under a third of the larger text or a third or
more; overlapping; sharing a little; and sharing nothing. It also gives the cluster's distinct short
cites and the minimum, median and maximum word counts of its texts. The classification is a pure
module, `debate_core.evidence.pair_shapes`, so t20's tests can import it.

Every `sample` mode now decides two kinds of pair by rule, counts them and never shows them: a pair
of two full cards that is identical or contained is the same card, and a pair sharing no text is
two different cards. Everything else goes to the person, with the shared text underlined, each
side's own text in bold, long texts trimmed, one key per answer and `q` to stop. `shapes` reads the
same texts as `diagnose`, and a test proves its count of pairs sharing nothing equals `diagnose`'s
`pairs_sharing_nothing`, which produced the PM's figures. So ac2 compares like with like.

**What to look at first:**

* ac2 and ac4 have to run against the operator's dev data directory, which the spec forbids a
  session to do. They are written up under Operator follow-ups. The Goal stays `InProgress` until
  they are recorded.
* One rule is narrower than the PM's notes, under Deviations: the rule decides only pairs of two
  full cards.
* Under the ruling, `--kept-apart-by` samples are almost all decided by rule, because a cut beside
  a body that holds it is contained by construction. That bears on t20 and is under Follow-up work.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `shapes-and-sampler`: Cluster shapes and sampler | Done in the session; the operator's timed sample is open | Its typed criterion passes. The operator's timed sample is ac4, NOT RUN. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: `shapes` counts every shape correctly on synthetic clusters built to hold each one, by test, and its JSON names no text | PASS | `uv run pytest packages/debate_core/tests/evidence/test_pair_shapes.py` → `17 passed`. That includes a seven-text cluster holding every shape, all 21 pairs tallied by hand in the test (1, 2, 2, 3, 7, 6), and each threshold met exactly on one side of its boundary and missed by one shingle on the other. On an invented store, `shapes` gives the hand-written JSON for two clusters (`test_shapes_counts_the_pairs_of_each_largest_cluster_by_shape_and_names_no_text`) and for one cluster by id. Its output holds no card word, cite, tag or cluster id (only with `--show-cluster-ids`). |
| **ac2**: operator-run, read-only: `shapes` over the dev store's three largest clusters per caselist gives the recorded shares (62% for hspf26, 51% for hspolicy26), or the report explains any difference | NOT RUN | The spec forbids a session from running either command against the operator's data directory. The command and the figures it should give are under Operator follow-ups, step 1. In the session: `test_shapes_shares_the_texts_and_the_count_sharing_nothing_with_diagnose` (both invented stores) proves `shapes` and `diagnose --only-largest-clusters` give the same ranks, cards, distinct texts, pairs and pairs sharing nothing. `test_the_count_sharing_nothing_is_the_one_the_largest_clusters_were_measured_by` proves the same against `cluster_shape` directly. |
| **ac3**: `sample` shows only the pairs no rule decides, marks the shared text, records rule-decided and person-decided tallies apart, and writes no text to any file, by test | PASS | `test_the_sample_shows_only_the_pairs_no_rule_decides_and_tallies_the_two_apart`: of four drawn pairs, the contained one and the one sharing nothing are never shown (none of their words appear in anything shown), and the overlapping pair and the abbreviated one are asked about. `test_a_cluster_sample_asks_about_five_of_its_ten_pairs_and_saves_counts_alone`: end to end, 5 of 10 are asked and the saved lines are exact. `test_a_shown_pair_has_its_counts_and_shares_at_the_top_and_its_shared_text_marked` and three trimming tests cover the display. `test_nothing_a_sample_saves_holds_text_a_tag_a_cite_a_path_or_a_digest` covers five sample modes (cluster at random, cluster least alike and stopped, kept apart, newly joined, divided): no card word, tag, cite, school, file name, `/`, `\` or run of 12 hex digits in the file. |
| **ac4**: operator-run: a 20-pair join sample with the new sampler, timed, with the number of pairs asked and the time taken | NOT RUN | It needs the operator and the real store. Operator follow-ups, step 2. The tallies line records `asked N` and `answered N in S seconds` itself, and the command is wrapped in `time` for the wall clock. |
| Node `shapes-and-sampler`: `uv run pytest tests/scripts -k card_clusters` | PASS | `55 passed in 4.17s` |

### The usual checks

**Each behaviour shown failing first.** The start commit `f3ab3fa`'s `scripts/` and
`debate_core/src` were extracted to the scratchpad with `git archive` and put first on
`PYTHONPATH`. `debate_core.evidence.near_duplicates.__file__` was printed to confirm the old source
was the one imported. The final test file was then run against that source, with no checkout.

* `shapes`: all four of its tests fail with `argparse.ArgumentError: argument command: invalid
  choice: 'shapes' (choose from counts, sample, diagnose, place)`.
* The sampler's behaviour. The test helper now patches the new key reader, so for this run only,
  in the scratch copy, it also patched `input`, which the old script reads. Then 9 tests fail for
  their reasons. The cluster, kept-apart and five-of-ten samples raise `StopIteration` because the
  old sampler asked the person about pairs the rule now decides, and the test had scripted no
  answer for them. The newly joined and divided samples fail with `assert '  Decided by rule ' in
  'Drew 2 of 2 newly joined pairs, seed 3.\n  abbreviated with abbreviated: different card: 1\n
  full with full: same card: 1\n'`. The four "refuses options that do not go together" cases pass
  on the old script, as they should: that behaviour is unchanged.
* The display, the trimming, the key reader, `classify_pair` and the pair shapes module are new
  names, so on the old source they fail only as missing (`AttributeError`, or the module does not
  import). The red there proves little. The mutants below are the evidence that each test reads
  its behaviour.
* Three old `--before-rules` tests fail in the scratch copy only because it is not a git
  repository. They are not counted.

**Mutants.** 30 mutants, one at a time, each run under `HYPOTHESIS_STORAGE_DIRECTORY` set to a new
empty directory (no test here uses Hypothesis). The driver restored each file from saved bytes and
checked them, and `git status --porcelain` was empty after every batch. The test that pins the
constants' values was deselected, so the boundary tests had to catch the threshold mutants on their
own. 30 of 30 were caught:

| # | Mutant | First caught by |
|---|---|---|
| 1, 2 | `IDENTICAL_SHARE` 0.98 → 0.97, → 0.99 | `test_identical_needs_each_body_to_hold_ninety_eight_hundredths_of_the_other` |
| 3, 4 | `CONTAINED_SHARE` 0.9 → 0.89, → 0.91 | `test_contained_needs_nine_tenths_of_the_smaller` |
| 5, 6 | `OVERLAPPING_SHARE` 0.3 → 0.29, → 0.31 | `test_overlapping_starts_at_three_tenths_of_the_smaller` |
| 7, 8 | `SMALL_PART_OF_THE_LARGER` 1/3 → 0.34, → 0.33 | `test_contained_is_split_at_a_third_of_the_larger` |
| 9 | identical "each way" → "either way" (`and` → `or`) | `test_shares_are_directional` |
| 10, 11, 12 | `>=` → `>` at contained; `<` → `<=` at a third; `>=` → `>` at overlapping | the boundary test of each |
| 13 | sharing nothing: `== 0` → `<= 1` | `test_one_shared_shingle_is_sharing_a_little_and_none_is_sharing_nothing` |
| 14 | the share taken of the larger body, not the smaller | `test_shares_are_directional` |
| 15 | the rule also decides overlapping pairs as the same card | the rule test; alone, `test_the_sample_shows_only_the_pairs_no_rule_decides_and_tallies_the_two_apart` |
| 16 | the rule no longer decides pairs sharing nothing | the same two |
| 17 | the rule decides pairs holding an abbreviated card | `test_a_pair_is_decided_by_rule_only_between_two_full_cards`; alone, the sample test above |
| 18 | **a decided pair is shown** (`to_ask = list(classified)`) | `test_sample_by_cluster_draws_from_the_largest_cluster_and_lets_the_rule_decide_a_cut`; alone, the sample test above |
| 19 | decided pairs are not counted | the same |
| 20 | the stop key does not stop | `test_nothing_a_sample_saves_…[shaped_dir-answers1-options1]` |
| 21 | a shared shingle marks one word too few | `test_shared_words_are_the_words_of_shingles_the_other_body_holds` |
| 22, 23 | no context kept before, or after, the shared region | `test_a_long_side_keeps_some_of_its_own_text_on_each_side_of_the_region_it_shares`; `test_a_shown_pair_has_…` |
| 24 | long runs never cut | `test_a_shown_pair_has_…` |
| 25 | side by side one column narrower | `test_two_texts_are_side_by_side_…[102-False]` |
| 26 | `TCSAFLUSH` → `TCSANOW`: a key pressed early is kept | `test_one_key_answers_and_a_key_pressed_before_the_question_is_discarded` |
| 27 | a wordless word (a dash) is unshared instead of taking its neighbour's mark | `test_written_words_are_marked_by_the_matching_words_they_hold` |
| 28 | `shapes` pairs abbreviated cards too | `test_shapes_counts_the_pairs_of_each_largest_cluster_by_shape_and_names_no_text` |
| 29 | the tallies line names the cluster id | an exact-lines test; alone, `test_nothing_a_sample_saves_holds_text_a_tag_a_cite_a_path_or_a_digest` |
| 30 | rule and person tallies under one label | the exact-lines tests |

The first version of the key reader also called `tcflush` after `tty.setcbreak`. `setcbreak`
already switches with `TCSAFLUSH`, which discards pending input, so removing the `tcflush` would
have been an equivalent mutant. It was dropped, `TCSAFLUSH` is now passed explicitly, and mutant 26
shows that the test reads it.

**Coverage of the new code** (`--cov=debate_core.evidence.pair_shapes --cov=scripts`):
`pair_shapes.py` 100%. The new lines of the script that are not covered are the no-`termios`
fallback in `read_key` (Windows only) and the second alignment guard in `_marked_words`. That guard
can only be reached if the written words held fewer matching words than the whole text, which a
partition of the text cannot produce. The first guard is covered by a test that substitutes a
matching-word function that disagrees with itself. The other uncovered lines are older code.

**Default suite, in four parts** (`uv run --frozen pytest -n auto -m "not slow and not live" --part K/4`):
1/4 `1913 passed in 53.60s`; 2/4 `1919 passed, 1 xfailed in 42.10s`; 3/4 `1925 passed, 1 skipped,
2 warnings in 41.19s`; 4/4 `1919 passed, 1 xfailed, 1 warning in 49.51s`.

**Static checks:** `uv run --frozen ruff check .` → `All checks passed!`; `ruff format --check .` →
`747 files already formatted`; `uv run --frozen pyright` → `0 errors, 0 warnings, 0 informations`
(also run on the script, which CI's pyright does not include: 0 errors); `uv run --frozen
lint-imports` → `Contracts: 12 kept, 0 broken.`; `uv run scripts/validate_specs.py` → `OK: 362
files, 38 epics, 304 tasks, 20 releases`.

## Files changed

* `packages/debate_core/src/debate_core/evidence/pair_shapes.py` (new): `PairShape`, the four
  thresholds as named constants, directional `PairShares`, `pair_shape`, `RULE_VERDICTS` and
  `rule_verdict`, `shared_words` (which words a display marks), and `cluster_pair_shapes`. Imports
  only `near_duplicates` from inside `evidence`.
* `packages/debate_core/tests/evidence/test_pair_shapes.py` (new): 17 tests of the above, all on
  numbered invented words.
* `scripts/compare_card_clusters.py`:
  * `shapes`, built from the existing `largest_clusters`, `full_bodies`, `_resolve_cluster`,
    `current_version` and `read_placements`. `read_bodies` and the new `read_bodies_and_cites`
    share one JSON reader.
  * `classify_pair`, `run_sample` with the rule, `SampleTallies`, `render_pair` with marking,
    trimming and the side-by-side layout, and the one-key `read_key`.
  * Every existing `sample` option is kept, and every mode goes through the rule.
* `tests/scripts/test_compare_card_clusters.py`:
  * A third invented store holding a pair of each rule-relevant shape, and the tests above.
  * Four existing tests changed their expectations where the ruling changes behaviour. The cluster
    sample's cut and the kept-apart sample's copy are contained, so they are now decided by rule
    and not shown, and the tallies lines carry the new form.
  * `_as_a_terminal` scripts keys through `read_key` instead of `input`.

## Deviations from the spec

1. **The rule decides only pairs of two full cards.** The PM's notes say identical and contained
   pairs are the same card and pairs sharing nothing are different, with no condition on
   completeness. An abbreviated disclosure is the card's first words, an ellipsis and its last
   words. Its five-word runs across the ellipsis are in no copy of the card, so an abbreviation of
   a card can share nothing with the card itself. Deciding that pair as "different card" by rule
   would be wrong. A pair holding an abbreviated card, or a body with no words, is shaped (tallied
   under its shape, or `a side has no words`) and always asked. Mutant 17 shows the tests hold
   this. The PM may want it written into the ruling.
2. **"Nothing the tool writes to a file may hold … a digest"** is applied to what `sample` writes.
   `counts --save-before` still writes digests and cluster ids, as it did before this task, because
   that file is the `--before` input of every later comparison and holds no text. The spec's
   forbidden entry names card text, schools, team codes and file names, not digests.

## Decisions and assumptions

1. **The texts `shapes` pairs are `diagnose`'s**: one body per exact fingerprint among the
   cluster's FULL cards, and pairs only between texts that have words. The PM's figures came from
   `diagnose`, so ac2's comparison does not depend on this task's choices. Its `cards` field
   counts FULL cards, as `diagnose`'s does, and `cards_not_full` counts the rest. The PM's table
   column "Cards" (682, 1,609, …) matches the clusters' total sizes in `counts`, which is `cards +
   cards_not_full`. `rank` is the cluster's place in the listing, as in `diagnose`.
2. **Thresholds** are the PM's (0.98, 0.9, 0.3, a third), unchanged, as named constants. I had no
   data in the session to refine them. The contained threshold is the clusterer's own containment
   default.
3. **No narrower band is proposed yet.** Every asked pair is tallied under its shape, so ac4's
   tallies are the evidence for or against deciding, say, overlapping pairs by rule. Narrowing the
   band is then a one-line change to `RULE_VERDICTS`.
4. **`--count` is the number of pairs drawn, as before.** The rule decides some of them, so fewer
   are shown. The same seed draws the same pairs as before this task, which is what makes the
   comparison in step 2 below possible.
5. **Display.**
   * Shared text is underlined and each side's own text is bold. The text is a person's to read,
     so neither style dims it.
   * A side over 150 words is cut to its shared region with 25 words of its own text on each side.
     Inside that region, a shared run over 30 words keeps 10 at each end, because it is the same on
     both sides and its middle says nothing. A run of its own text over 120 words keeps 40 at each
     end.
   * Every cut is replaced by a note of how many words it held, and the header says "Showing N of
     them". The PM's note asked for the shared region plus context. The cut inside the region is my
     addition, because a 3,000-word overlap would otherwise fill the screen.
   * Side by side from 103 columns (two columns of at least 50), and one above the other below
     that. Lines never exceed the terminal's width (tested at 80, 102, 103 and 160).
   * Word counts in the header are written words, as before. Shares are of five-word runs.
6. **One key, no Enter**, through `termios` cbreak mode. Switching to it with `TCSAFLUSH` discards
   any key pressed while the pair was being drawn, so a double press cannot answer a pair nobody
   has seen. Ctrl-C still aborts as before, without tallies. `q` is the way to stop and keep them.
7. **The tallies form extends today's.** The first line, what was drawn and the seed, is unchanged.
   Then come `  Decided by rule D of N; asked A; answered B in S seconds[, stopped with K not
   answered].`, then `  by rule: <kind>: <shape>: <verdict>: <count>` and `  asked: <kind>:
   <shape>: <verdict>: <count>`. The time is how long the person spent answering, not reading the
   store.

## Operator follow-ups

Both steps are read-only and print or save counts only. Run them from the main checkout once this
task has merged into `dev` and the checkout is on `dev` with it. The same commands work from this
task's worktree before the merge, if the PM wants the figures for the review. The first block
checks that the checkout has this task's code: `--help` fails with `invalid choice: 'shapes'` if
not.

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
git branch --show-current
uv run python scripts/compare_card_clusters.py shapes --help > /dev/null; echo "exit $?"
```

Expected: `dev`, then `exit 0`.

**Step 1: ac2, shapes of the three largest clusters per caselist** (expected well under a minute
in total; computing 18,721 pairs of an invented 194-text cluster took 0.6 s, so reading the bodies
dominates, as for `diagnose --only-largest-clusters`).

```zsh
uv run python scripts/compare_card_clusters.py shapes --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --largest-clusters 3 > ~/card-cluster-shapes-v3.json; echo "exit $?"
jq -c 'to_entries[] | {caselist: .key, version: .value.version_directory, seconds: .value.seconds, clusters: [.value.described_clusters[] | {rank, cards, not_full: .cards_not_full, texts: .distinct_texts, pairs, nothing: .share_of_pairs_by_shape["sharing nothing"]}]}' ~/card-cluster-shapes-v3.json
```

Expected, if the store is still `2026.10.12-docx-3` under `card-fingerprint-v3`: `exit 0`, then
these figures (shares rounded here):

| Caselist, rank | Distinct texts | Pairs | Sharing nothing |
|---|---|---|---|
| hspf26, 1 | 89 | 3,916 | 0.62 |
| hspolicy26, 1 | 194 | 18,721 | 0.51 |
| hsld26, 2 | 49 | 1,176 | 0.25 |
| hspf26, 3 | 87 | 3,741 | 0.19 |
| hsld26, 1 | 53 | 1,378 | 0.15 |
| hspolicy26, 2 | 54 | 1,431 | 0.08 |
| hsld26, 3; hspf26, 2; hspolicy26, 3 | 14; 75; 20 | 91; 2,775; 190 | 0 |

`cards + not_full` should be 710, 441 and 396 for hsld26; 682, 592 and 377 for hspf26; and 1,609,
692 and 671 for hspolicy26. openev's three are new: the PM's table has none. Paste the `jq` lines
back; they hold counts only. A different figure most likely means the store was rebuilt after
2026-10-16: the `version` field says which directory was read.

**Step 2: ac4, a timed 20-pair join sample** (seconds to read the store, then the person's time).
It needs the placements t11's step 2 saved. The first command checks they are there, and the
second reads the seed of t11's join sample from its tallies file.

```zsh
ls ~/.debate-research/dev/card-clusters-before-t11
SEED=$(grep -m1 'newly joined pairs, seed' ~/card-cluster-sample-tallies.txt | sed -E 's/.*seed ([0-9]+)\./\1/'); echo "seed ${SEED}"
```

Expected: `hsld26.jsonl hspf26.jsonl hspolicy26.jsonl openev.jsonl`, then `seed` followed by a
number.

With that seed, the sampler draws the same 20 newly joined pairs the operator judged by eye on
2026-10-16 (17 same, 1 different, 2 unsure), so the rule's verdicts can be compared with them. If
`seed` prints nothing, put any number in place of `${SEED}` below. Each pair the rule cannot decide
is shown one at a time. Press `s` (same card), `d` (different card) or `u` (unsure), with no Enter,
or `q` to stop and keep the tallies so far.

```zsh
time uv run python scripts/compare_card_clusters.py sample --count 20 --seed ${SEED} --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --before ~/.debate-research/dev/card-clusters-before-t11 --save-tallies ~/card-cluster-sample-tallies-t21.txt
cat ~/card-cluster-sample-tallies-t21.txt
```

Expected: the tallies end with `Drew 20 of 51 newly joined pairs, seed …`, then `Decided by rule
D of 20; asked A; answered A in S seconds.` and the `by rule:` and `asked:` lines. `time` prints
the wall clock last. Paste the tallies file and the `time` line back: they hold counts only. The
cards are real disclosures, so nothing from the screen goes into a message, a screenshot or a file.
The pair t11 found to be different cards (two bodies sharing no text, joined through a third)
should now appear as `by rule: full with full: sharing nothing: different card: 1`, not as a
question.

If `ls` finds no such directory, the "before" has to be computed again first. That is t11's
step 2, 15 to 25 minutes: copy it from
`docs/session-reports/v1-e31-t11-long-card-splits-and-fragment-merges.md` rather than from here.

Once the figures are back, they go into `docs/data/caselist-parse-report.md`, beside "Card
matching under `card-fingerprint-v3`, measured". Then ac2 and ac4 can be marked and the Goal set
to `Succeeded`.

## Follow-up work

1. **For `v1-e31-t20`: rule-decided samples of cuts.**
   * Under the ruling, `sample --kept-apart-by …` pairs each cut with a body that holds it. Those
     pairs are contained by construction, so nearly all are now decided as the same card and never
     shown.
   * The same goes for `--least-alike` cluster samples. They draw the pairs sharing least first,
     and the rule decides all the pairs that share nothing.
   * t20's items 2 and 4 (`MIN_CUT_SHARE`, and bodies lacking an end) planned to decide limits from
     such samples. If the PM wants a person to see some contained pairs anyway, for example
     `contained, under a third of the larger`, which is the `MIN_CUT_SHARE` question, that is a
     ruling for t20 and a one-line change to `RULE_VERDICTS`. As built, the decided count by shape
     is in the tallies, which may itself be the answer for item 4.
2. **The no-`termios` fallback** of `read_key` (a line read with Enter) is untested. It is reached
   only on a platform without `termios`, which the operator's Mac is not.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
