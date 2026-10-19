# Session report: v1-e31-t20-long-cuts-and-limits

| | |
|---|---|
| Task | `v1-e31-t20-long-cuts-and-limits` — Long cuts join the one cluster that holds them, and the matching limits are set from samples |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t20-long-cuts-and-limits.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t20-long-cuts-and-limits.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t20-long-cuts-and-limits` |
| Session status | PARTIAL: the PM's rulings on the first preview (2026-10-18) are built, tested red first and mutated: every two bodies in a cluster overlap, `MIN_CUT_SHARE` is a tenth, short bodies are found from either end, `MAX_CONTAINER_CLUSTERS` stays 8. The labelled-set guardrail holds exactly. The re-preview that covers all of it, and the rebuild after the merge, are the operator's and NOT RUN |

## Summary

`card-fingerprint-v4` builds the PM's card ruling of 2026-10-16 into near-duplicate clustering, as
the PM then ruled on its first preview on 2026-10-18. A cut, long or short, joins the one cluster
that holds it, found from either of its ends. **Every two bodies in a cluster overlap, sharing at
least three-tenths of the smaller's five-word runs, or one holds the other.** A body holding a cut
and another passage the cut does not overlap is no witness for it; no join puts two bodies that do
not overlap in one cluster; a cut's own cluster counts among its witnesses. A cut may be as little
as a tenth of the body it joins. t11's false join is the first fixture and stays three clusters
under every order of fingerprints. `sample --ask-shape` (item 8) shows a person the pairs of a
shape the rule decides, tallied apart. `counts --save-after` and `--after` let the operator preview
it all from this worktree, writing nothing to the store.

**Read these first:**

1. **The first preview found a newly joined pair, sharing a little text, that a person judged a
   different card.** The one-shared-run reading (my Decision 2, which the PM had accepted) let it
   through. The PM ruled that "shares text" means *overlaps*, at three-tenths of the smaller's
   runs, in both the passage refusal and the join guard, superseding that reading. Built: the one
   boundary test that moves is the chain of copies ten words apart, which now breaks after the
   seventh extent instead of the tenth (`test_copies_a_few_words_apart_never_chain_into_a_cluster_of_texts_that_do_not_overlap`).
2. **The labelled-set guardrail holds exactly, by test**, under all three changes:
   `test_the_passage_ruling_loses_only_two_cards_pairs` and
   `test_recall_over_every_other_card_is_as_t08_left_it` pass unchanged, and every row of the
   labelled table is the same, precision 1.000. The labelled sets have no pair sharing only a
   little in one cluster, so they cannot tell the two readings apart; the store can.
3. **The limits, from the first preview's samples:** `MIN_CUT_SHARE` 0.1 (20 of 20 kept-apart cuts
   the same card, 8 under a tenth); short bodies lacking an end compared (20 of 20 the same card);
   `MAX_CONTAINER_CLUSTERS` 8, still counting clusters that hold both ends. The re-preview must
   sample at least 20 newly joined cuts a tenth to a quarter of their witness (`sample
   --joined-in-band`); **any different-card answer there stops the merge until the PM has seen it.**
4. **The lower share also refuses more witnesses**, because the share is also the size of a
   passage: a body holding a passage a tenth to a quarter of it that a cut does not overlap is now
   no witness for that cut. `diagnose` counts those refusals (`witness_refusals`), as the PM
   asked. On invented text the effect is the one fixture that had to move: a 50-word passage of a
   200-word copy became one of the copy's passages.
5. **The 9 unexplained divided pairs are now named**, by the outcome "nine-tenths inside a body that
   holds neither of its ends", found from three interior shingles of each body. Recovering them is
   a later rule change, which the PM is filing at p3.
6. **An installed agent rewrites the table as `v3`.** Reinstall the agent on the first pre-release
   carrying this task before the dev rebuild (step 9).

**The Goal stays `InProgress`.** ac1's sample, ac4's re-cluster figures and ac5's shapes need the
re-preview and the rebuild; the PM's check on the share needs the re-preview's band sample.

**The PM's rulings of 2026-10-18**, in the order they came:

* **On the labelled sets, 1(a): the ruling stands.** The two text-disjoint trims of Brannock's and
  Kessler's cards are two passages each. `short_cards.jsonl` is unchanged; t08's ac1 for the two
  "full short cards" rows is amended to 0.792 and 0.622; a test pins the lost pairs to those two
  cards by row id and holds every other card's recall. Built in `cafab61`, `790a42b`, `7d7e73d`.
* **On the three choices, 2: all go ahead**: symmetric refusal; the long near-containment join,
  with the container rule applying to it; and one shared run as "shares text", with a count of
  pairs sharing one or two runs to test it (`bff30f6`). The third is superseded below.
* **On the first preview:** (1)(a), "shares text" means overlaps at three-tenths, superseding the
  one-run reading, with the guardrail to hold exactly by test and the moved boundary test named;
  (2) `MIN_CUT_SHARE` 0.1 with a band sample of at least 20 and the added refusals reported, short
  bodies lacking an end compared, `MAX_CONTAINER_CLUSTERS` 8; (3) a diagnosis outcome for the
  neither-end body, the re-preview to report ac5, the four largest clusters' sizes and the few-run
  pairs (any left must say how they got there), and the 132 long cuts accepted. Built in `1c38f49`
  and `2aab11c`.

**For the PM** (paste-ready):

```text
v1-e31-t20: your rulings on the first preview are built. The operator's re-preview is next.

1(a) Overlap. "Shares text" is now "overlaps": at least 0.3 of the smaller text's five-word runs
  (MIN_OVERLAP_SHARE, and pair_shapes' OVERLAPPING_SHARE is the same constant). It is read in the
  passage refusal and in every join guard, so every two bodies in a cluster overlap or one holds
  the other. Supersedes the one-run reading you accepted earlier today.
  - Guardrail: holds exactly. The two pinned tests pass unchanged and every labelled row is the
    same, precision 1.000. The labelled sets have no in-cluster pair sharing only a little.
  - The boundary test that moved: the chain of eleven 100-word extents ten words apart. It was one
    cluster of ten and one of one; it is now seven and four. Six apart they share 36 of 96 runs
    (overlap), seven apart 26 (do not).
2. Limits. MIN_CUT_SHARE = 0.1; short bodies lacking an end are compared; MAX_CONTAINER_CLUSTERS
  stays 8, still counting clusters that hold both ends.
  - Re-preview: sample --joined-in-band a-tenth-to-a-quarter draws cuts newly joined to their
    smallest witness in that band, 20 of them, every one shown. Any different card: stop.
  - diagnose reports witness_refusals: the containers refused as witnesses, and how many of those
    refusals come only from a passage a tenth to a quarter of the container, i.e. the ones the
    lower share added.
3. The 9 are named: a new outcome, "nine-tenths inside a body that holds neither of its ends",
  found from three interior shingles. shapes --every-cluster now also says how many of the pairs
  sharing one or two runs do not overlap. Under the new rules that must be 0. A pair left sharing
  one or two runs must have a text of six runs or fewer, where that is three-tenths.
```

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `long-cuts` — Long cuts and limits | Done in the session; the re-preview and the re-cluster are open | The join, the guards, the overlap reading, the limits, the diagnosis, the preview, item (8) and the version are built and tested. The re-preview and the re-cluster figures are NOT RUN |

## Acceptance criteria

Every command ran from the task worktree on 2026-10-18, against invented fixtures only, except the
operator's first preview, recorded in the parse report.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — (1), (5) and (7) built on synthetic fixtures, shown failing first, including two disjoint bodies and a third holding both, which stay apart | PASS | The 13 tests of "Long cuts, and joins only on text two bodies share" in `test_near_duplicates.py`, committed red (`a295999`) against the v3 rules: `14 failed, 4 passed`. Under the overlap reading the same section plus three new tests: `uv run pytest packages/debate_core/tests/evidence/test_near_duplicates.py -n0` → `111 passed`. t11's false join stays `[[A], [B], [C]]` under all six orders of fingerprint. See [Shown failing first](#shown-failing-first) |
| **ac1** — the operator's join sample of 20 newly joined pairs, through t21's sampler, has no pair the coach calls different | **NOT RUN** on the rules as ruled | The first preview's 20 were all decided by rule (contained), so nobody judged them, and its 40-pair sample found one different card, which is why the PM ruled 1(a). The re-preview's step R4 draws 20 with both contained shapes asked |
| **ac2** — each limit set from the recorded samples, with the figures in the report, and re-measured after (1) | PASS (set); the re-measure under the set limits **NOT RUN** | From the first preview (parse report, "The first preview's samples"): `MIN_CUT_SHARE` 0.25 → 0.1 (20/20 kept-apart cuts the same card, 8 under a tenth); `MAX_CONTAINER_CLUSTERS` kept at 8 (6/6, every such cut on four caselists); both ruled by the PM on 2026-10-18 and pinned at their boundaries by test and mutants. The re-preview's `diagnose` (step R6) re-measures every limit under the set values |
| **ac3** — (4): the sample decides, and the rule follows it, by test | PASS | The first preview's sample: 20 of 31 short bodies nine-tenths inside a body lacking one of their ends, 20 the same card. The rule followed: `test_a_short_body_nine_tenths_inside_a_body_lacking_one_of_its_ends_joins_it` and `test_a_card_lacking_the_end_of_a_short_copy_holds_it_and_is_no_second_witness`, the two tests that pinned the old rule turned round, red against the pre-ruling code |
| **ac4** — `fingerprint_version` bumped | PASS | `card-fingerprint-v4`. No store has held a `v4` table (the preview writes none), so the rulings stay `v4`; `fingerprints.py` and `parsed-card-store.md` describe `v4` as ruled |
| **ac4** — the operator's re-parse records clusters, merges and divided pairs before and after in `caselist-parse-report.md` | **NOT RUN** | A re-cluster, not a re-parse. The first preview's figures are recorded and marked superseded; the re-preview's and the rebuild's columns are marked not run. Steps R2, R6 and 9 to 16 |
| **ac5** — under 5% of pairs sharing no text in each caselist's three largest clusters, after the rebuild | **NOT RUN** | 0% by construction, and since the overlap reading so is the share sharing a little, but for texts of six runs or fewer. The first preview measured 0 in all twelve. Re-preview: step R3; after the rebuild: step 13 |
| **ac6** — `sample` shows the pairs of a decided shape the person names, tallied apart, by test | PASS | `sample --ask-shape SHAPE`, repeatable, by test, red against the start commit |
| **ac6** — the operator's sample of contained pairs under a third of the larger sets or confirms `MIN_CUT_SHARE` | PASS | The first preview: 17 of 17 newly joined contained pairs under a third the same card, and 20 of 20 cuts the share kept out the same card. It set the share at a tenth |
| Node `long-cuts`: `uv run pytest packages/debate_core/tests -k "fingerprint or cluster"` | PASS | see Also run |

### Also run

| Check | Result |
|---|---|
| Default suite, `uv run --frozen pytest -n auto -m "not slow and not live" --part K/4`, one command each, on the final tree (load 9 to 11 from other sessions) | `2030 passed` (104 s); `2037 passed, 1 xfailed` (98 s); `2037 passed, 1 skipped, 2 warnings` (85 s); `2029 passed, 1 xfailed, 1 warning` (56 s): 8,133 passed. The skip is the parser eval waiting on corrections; the two xfails are t12's |
| `uv run --frozen ruff check .`; `ruff format --check .` | `All checks passed!`; `785 files already formatted` |
| `uv run --frozen pyright` (after the last format) | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 12 kept, 0 broken.` |
| `check_thin_handlers.py`, `check_links.py`, `docs_index.py --check-descriptions` | all OK |
| Coverage of the changed modules, lines and branches | `cluster_diagnosis.py` 100%, `fingerprints.py` 100%, `pair_shapes.py` 100%, `near_duplicates.py` 99%: line 566 (`_Clusters.join` given one root twice, which no caller does) and 589 (`v1-e31-t04`'s empty-body exit in the banding loop) |
| Node `long-cuts`: `uv run pytest packages/debate_core/tests -k "fingerprint or cluster"` | `183 passed` |
| `uv run scripts/validate_specs.py` | `OK: 366 files, 38 epics, 308 tasks, 20 releases` (the Goal left `InProgress`) |
| `scripts/check_command_blocks.py --base origin/dev` | `OK: no # comments in 294 shell code blocks in 123 Markdown files` |

## The rules (`card-fingerprint-v4`)

In [`near_duplicates.py`](../../packages/debate_core/src/debate_core/evidence/near_duplicates.py),
whose docstring now opens with the ruling and maps each sentence of it to a step.

0. **Overlap** (the PM, 2026-10-18): two bodies overlap when they share at least
   `MIN_OVERLAP_SHARE` (0.3) of the smaller's shingles, compared as a ratio (`CutIndex.overlap`).
   Every rule below that once read "shares a shingle" reads "overlaps".
1. **Copies.** Banding candidates with Jaccard at least 0.8, and pairs of bodies of one size that
   each hold the other (a word changed), are joined most similar first, then by fingerprint. A join
   that would put two bodies that do not overlap in one cluster is refused. A one-word-changed copy
   of a body too common to compare is held back, counted against the Jaccard copies, as `v3`'s
   short step held it back.
2. **Containers, found and not sampled.** `CutIndex` works out, from the bodies alone, which bodies
   hold which: at least as large, holding the cut's first or last shingle, and confirmed,
   nine-tenths or, for a short cut, all but one word. The containment union through the banding is
   gone.
3. **The cut step, in rounds.** Each round, every cluster's join is worked out from the clusters
   the last round left:
   * a container that also holds a passage (a body it holds, at least `MIN_CUT_SHARE`, a tenth, of
     it) that the cut does not overlap is no witness;
   * the cut's own cluster counts among its witnesses;
   * nested witnesses count once, as in `v3`;
   * the cut must be at least a tenth of its smallest witness, compared as a ratio;
   * a short cut whose ends more than `MAX_CONTAINER_CLUSTERS` (8) other clusters both hold,
     counted as the clusters stand, is left alone (`CutIndex.holding_both_ends`: finding containers
     from either end did not change what this limit counts).

   A join is refused if the joiner does not overlap a body already in the target. A cluster
   joining nothing takes in its joiners, except any two that do not overlap, which it takes in
   neither of. A cluster whose own join is so refused takes in its joiners in the same round. A
   cluster that is joining another waits a round. Rounds end when one joins nothing.

`CutIndex`, `witnesses`, `too_common` and `joining_target` are public, and
[`cluster_diagnosis.py`](../../packages/debate_core/src/debate_core/evidence/cluster_diagnosis.py)
decides every outcome with them, so the diagnosis cannot drift from the rules.

### What it costs

The rebuild has not been timed on the store (that is a store run). On invented corpora, run
locally under loads of 7 to 52 (other sessions):

| Invented corpus | `v3` | `v4` |
|---|---|---|
| 3,000 cuts of 375 articles, lengths log-normal around 120 words | 29.8 s | 9.4 s |
| 10,000 cuts of 1,250 articles | 39.5 s | 23.1 s |
| 600 extents of one 3,000-word article | 2.3 s: 14 clusters, largest 584, 138,081 pairs sharing nothing | 4.2 s: 199 clusters, largest 44, none |
| 2,000 extents of that article | not run | 39.5 s: 335 clusters, largest 150, none |

A profile of the 1,200-extent case: 17.2 s, of which MinHash, which `v3` does too, is 11.5 s, the
copies' Jaccard 2.3 s and the cut step 0.7 s. The growth with extents of one article is the
banding's candidate pairs, as in `v3`.

**The PM's rulings cost nothing measurable.** The same invented corpora, the rules before the
rulings against the rules as ruled, under a load of about 10: 3,000 cuts, 8.2 s and 8.1 s (largest
cluster 19 and 8); 10,000 cuts, 26.2 s and 26.6 s (largest 21 and 11). Finding short cuts from
either end looks up more candidates, and the lower share makes more passages; neither shows.

## Labelled sets, before and after

`uv run pytest packages/debate_core/tests/evidence/test_short_card_recall.py -n0 -s -k test_report_short_card_recall`,
saved before the first change and after each one, compared with `diff`. True positive, false
positive and false negative pairs:

| Pairs | Before | After | Precision after | Recall after |
|---|---|---|---|---|
| Variant set, all | 75 / 0 / 0 | 75 / 0 / 0 | 1.000 | 1.000 |
| Variant set, with a short card | 6 / 0 / 0 | 6 / 0 / 0 | 1.000 | 1.000 |
| Variant set, long cards only | 69 / 0 / 0 | 69 / 0 / 0 | 1.000 | 1.000 |
| Short-card set, all | 81 / 0 / 0 | 70 / 0 / 11 | 1.000 | 0.864 |
| Short-card set, full short cards | 24 / 0 / 0 | 19 / 0 / 5 | 1.000 | 0.792 |
| Short-card set, the full long card | 1 / 0 / 0 | 1 / 0 / 0 | 1.000 | 1.000 |
| Short-card set, abbreviated with a full copy | 44 / 0 / 0 | 39 / 0 / 5 | 1.000 | 0.886 |
| Short-card set, abbreviated with abbreviated | 12 / 0 / 0 | 11 / 0 / 1 | 1.000 | 0.917 |
| Extended set, all | 104 / 0 / 12 | 86 / 0 / 30 | 1.000 | 0.741 |
| Extended set, full short cards | 35 / 0 / 2 | 23 / 0 / 14 | 1.000 | 0.622 |
| Extended set, full long cards | 2 / 0 / 2 | 2 / 0 / 2 | 1.000 | 0.500 |
| Extended set, abbreviated with a full copy | 51 / 0 / 4 | 46 / 0 / 9 | 1.000 | 0.836 |
| Extended set, abbreviated with abbreviated | 16 / 0 / 4 | 15 / 0 / 5 | 1.000 | 0.750 |

**Every lost pair is one of two cards'.** Worked out by hand from the rows and written into the
test before it ran (`AFTER_THE_PASSAGE_RULING_TABLE`); the measurement matched row for row and by
mechanism on the first run.

* **Brannock** (t06's rows): the original is the 13-word trimmed end followed by the 16-word trimmed
  start, word for word. The original and the typo copy each hold both trims, so neither trim has a
  witness. Lost: 5 full pairs (the trims with the original and the typo copy, and with each other),
  5 abbreviation-with-full pairs (each abbreviation links to the side whose opening and closing it
  matches), and the pair of abbreviations.
* **Kessler** (t08's rows): the original holds both trims. The OCR-joined copy holds the trimmed
  start and the dropped-word copy the trimmed end, and both copies join the original. Each trim
  then has one witness, that cluster, and the two share nothing, so it takes in neither. Lost: 7
  full pairs.

The first version of the passage rule cost more: a body holding two passages was no witness for
anything, so Kessler's own one-word copies lost the original too. The rule is now relative to the
cut: a container is no witness for a cut when it holds another passage sharing nothing with that
cut. A copy of the whole body shares text with both passages and is witnessed as before.

**Under the PM's rulings on the first preview** (overlap, a tenth, either end) every row above is the same, measured, and both guardrail tests pass unchanged.

**The PM's ruling of 2026-10-18 keeps these figures.** t08's ac1 for the two "full short cards" rows
is amended to 0.792 (19 of 24) and 0.622 (23 of 37), and `REQUIRED_RECALL` holds those exact
fractions. Every other target holds; "extended set, abbreviated with abbreviated" is exactly at its
0.75. The labels are unchanged.

**The guardrail on the lower target**, in `test_short_card_recall.py`:

* `test_the_passage_ruling_loses_only_two_cards_pairs`, on each of the three sets: the same-card
  pairs placed apart are exactly `MISSED_BEFORE_THE_PASSAGE_RULING` (t08's 12 misses on the extended
  set, from a run against t08's code, none on the other two) together with
  `LOST_TO_THE_PASSAGE_RULING` (Brannock's 11 pairs, and on the extended set Kessler's 7), pinned by
  row id. Every pinned lost pair's rows are labelled `brannock-ferry-fares` or `kessler-night-buses`.
* `test_recall_over_every_other_card_is_as_t08_left_it`: with those two cards' rows left out, the
  found and missed pairs are t08's.

A pair lost anywhere else fails both, even when every row's total still matches. t08's mechanism
test that Kessler's trims join the original is now the opposite expectation: each trim is a cluster
of its own.

## Shown failing first

Red runs, each against the code before the behaviour existed. The start commit's source was taken
with `git archive 47d454d` to the scratchpad and put first on `PYTHONPATH`, after printing a
changed module's `__file__` to confirm it was the one imported.

| What | Against | Red |
|---|---|---|
| The 13 tests of the ruling (`a295999`, committed red) | v3 | `14 failed, 4 passed`: t11's false join `[[A, B, C]]` in all six orders; the two-passage witness `[[0, 1, 2, 3]]`; three long-cut joins `[[0], [1]]`; two copies' passages `[[0, 1, 2, 3]]`; the copies' chain not sharing text throughout; the own-cluster cases `[[0, 1, 2]]` twice |
| The four that passed on v3 | | Two boundaries kept on purpose (a body holding one passage is its card; a copy that does not hold the cut does not block it), the lacking-an-end rule pinned, and the container count, which v3's banding satisfies for another reason. Mutants are their evidence |
| The version literal | v3 | `'card-fingerprint-v3' == 'card-fingerprint-v4'`, twice |
| A long cut lacking an end joins | v3, and the commit before it | `[[0], [1]]` on both |
| A card lacking a short copy's end is a second witness | v3 | `[[0], [1, 2]]` |
| The two round tests | v3; the commit before the fix | Both `[[0, 1, 2, 3, 4]]` on v3; the waiting cut `[[0, 1], [2], [3], [4]]` before the fix |
| The diagnosis (`test_cluster_diagnosis.py`) | v3's diagnosis | `14 failed, 20 passed`: the new outcomes and the v4 readings |
| The six new script tests | the start commit's script | `SystemExit: 2` for the four options it lacks, `TypeError` for `ask_shapes`, and no `within-the-rule` selector. A missing option proves little; the mutants are the evidence |
| The guardrail and the passage mechanism test (after the PM's ruling) | t08's code, `git archive 47d454d` | `4 failed, 11 passed`: the pinned losses on the short-card and extended sets, and both k1 trims. The amended targets and the other cards' recall pass there, as they should: t08 found those pairs |
| The container rule for a long body lacking an end | v3; and a mutant | On v3 the control fails first (`[[0], [1]] == [[0, 1]]`: v3 never pairs them). The rule itself is shown by the mutant exempting such a cut from the passage check: this test alone fails |
| The stock-phrase count | the code before it | `ImportError` for `pairs_sharing_few_runs`, and `KeyError: 'pairs_sharing_only_few_runs'` from `shapes` |
| The PM's rulings on the first preview: every new and changed test | the code before them (`34b1393`, `git archive` to the scratchpad), the new names added as inert stand-ins so the files collect | `27 failed, 225 passed`. Behaviour: the share boundaries at a tenth (four tests), the chain at the overlap line, lacking an end held (three), the neither-end outcome (two), the later-round refusal at the new share, the first-by-fingerprint flag, the share bands, the witness refusals, the divided part named, the few-run overlap count (two), `--joined-in-band` (two), the renamed slug (three), the exact-dict tests' new fields (two). Three fail for the archive's own reason: `--before-rules HEAD` needs a git repository, which an archive is not |
| The three tests added after the mutants were planned | the same | the overlap line: `AttributeError`, no `overlap`; the one-run passages: `[[0, 2], [1], [3]] == [[0], [1, 3], [2]]` (the body witnesses the first passage); the shared opening passes there, as a guard of behaviour the change had to keep, and its mutant is its evidence |

## Mutation runs

On the final code, after the PM's rulings: **68 mutants** run one at a time against the eight test
files that read matching (the seven before, and `test_pair_shapes.py`; `390 passed` unmutated,
10 s), and **five more against the guardrail's two tests alone**. Each mutant is one exact
replacement that had to match exactly once. Each run had a new empty
`HYPOTHESIS_STORAGE_DIRECTORY`, checked empty first; none of these tests is a Hypothesis property,
so the isolation cannot affect them. The file was restored from saved bytes and compared, and
`git status --porcelain` was checked after the run. **70 of 73 caught; the other 3 are
equivalent**, shown so below. One survivor of the first pass (`diagnose-without-refusals`) was a
missing test, written (`test_diagnose_counts_the_containers_refused_as_witnesses_by_a_passage`)
and the mutant run again: caught.

| Group | Mutants (each caught, failures in brackets) |
|---|---|
| Overlap (the PM, 2026-10-18) | overlap read as one shared run (3); the line at 0.29 (4); at 0.31 (15); an empty body overlapping (1); the passage refusal reading one run (1: the one-run passages test alone); the join guard reading one run (1: the chain test alone); `pair_shapes`' line apart from the clusterer's (3) |
| The witness rule | witnesses in several clusters join the smallest's (11); nested containers never count once (36); copies count as containers (11) |
| The two-passage refusal | the refusal gone (3); a container refusing every cut once it holds two passages that do not overlap (6); passages of any size (3); the passage check skipped for a long cut lacking an end (1: its test alone) |
| The own-cluster witness | own-cluster containers ignored, as v3 did (5) |
| `MIN_CUT_SHARE` (0.1) | 0.09 (6); 0.11 (6); not checked (22); checked for short cuts only (18) |
| `MAX_CONTAINER_CLUSTERS` (8) | 7 (2); 9 (3); counting bodies, not clusters as they stand (2); counting holders of either end, not both (1: the shared-opening test alone); one-word copies not held back when too common (1) |
| Either end (item 4) | short cuts needing both ends again (3); every cut needing both ends (5) |
| Never two texts that do not overlap | copies joined unguarded (1); cut joins unguarded (1); joiners not checked against each other (7); joiners not waiting for their target (6); refused joins holding back their joiners (1) |
| The version | not bumped (3) |
| The diagnosis | no passage outcome (1); own cluster read as several (1); no unrelated-texts outcome (1); never "points elsewhere" (1); set-aside judged by its own copy (1); copies not holders (2); divided parts by first digest (3); no neither-end search (3); refusals counted without the passage check (1); refusals "added" read against the current share (1); the share bands' edges as before (2) |
| The script | `--ask-shape` not shown (2); also counted by rule (2); tallied with the rest (2); `--after` ignored by one-placement commands (1); ignored when comparing (1); `--save-after` saves *before* (2); `--preview` ignored (2); kept-apart kind without its band (4); sizes swapped (1); `--joined-in-band` not only newly joined (1), any band (2), ignored (1); `diagnose` without the refusals (1, after its test was written) |
| The stock-phrase count | `FEW_RUNS` 3 (4); zero runs counted (4); every cluster counted as having such a pair (1); lone clusters counted (1); pairs miscounted (1); abbreviated cards read (1); `--every-cluster` ignored (1); every few-run pair counted as not overlapping (1); the not-overlapping count dropped (1) |
| The guardrail, its two tests alone | the one-word tolerance gone (6); the split-word change gone (6); abbreviation anchors needing four words (4); a pinned Kessler pair swapped for another card's, totals unchanged (1); one of t08's misses left out of the pins (2) |

**The three equivalent mutants** write a share as a product instead of a ratio: `cut >= 0.1 *
witness` in the join, `holder > cut / 0.1` where passages stop, and `cut < 0.1 * witness` in the
diagnosis. For the lines 0.1 and 0.3, the product and the ratio agree at every boundary for every
size up to 200,000 shingles (checked exhaustively around each boundary in the scratchpad), so no
test can tell them apart. Ratios are kept so the three modules read one expression.

**What the earlier runs found**, each fixed before the final run:

* **Five survivors, each a missing test**, now written: a quote under the share is no passage
  (`passages-of-any-size`); a body lacking a short copy's end is a second witness
  (`short-lacking-an-end-compared`); a cut does not join a cluster already holding a passage sharing
  nothing with it (`cut-join-unguarded`); the diagnosis of a cut whose outside containers all hold
  another passage (`diagnosis-no-passage-outcome`); `--after` reads the file and does not place
  again (`after-ignored-when-comparing`).
* **A real defect, found while writing the third of those.** A cluster whose own join was refused
  beside a conflicting joiner still counted as joining, so a cut waiting on it waited forever.
  Fixed in `2be9063`, with a test that fails on the commit before.
* **Two mutants were first written so that they crashed** (an unpacking error, a missing key) and
  were rewritten as behaviour changes before being counted.
* **One branch deleted.** The handling of two clusters that would each join the other was never
  taken: the copies' step already joins two bodies that each hold the other, and I could build no
  such pair. Without it the two would wait for each other and join neither (`26e54cc`).
* **Two batches were cut by the alarm** under loads of 46 and 72 from other sessions, each leaving
  one file mutated. Each time the diff was checked to be the mutant alone and the file restored.
  The interrupted mutants were run again.

## Files changed

**Matching (`packages/debate_core/src/debate_core/evidence/`)**
* `near_duplicates.py`: the rules above; `CutIndex` (with `overlap`, `overlap_throughout` and
  `holding_both_ends` since the PM's rulings), `Witnesses`, `witnesses`, `too_common` and
  `joining_target`, public for the diagnosis; `MIN_OVERLAP_SHARE` 0.3 and `MIN_CUT_SHARE` 0.1; the
  docstring rewritten around the ruling and the rulings on its preview.
* `fingerprints.py`: `card-fingerprint-v4` and what it changed.
* `cluster_diagnosis.py`: reads containment from `CutIndex` and decides outcomes with the
  clusterer's functions. New outcomes, long and short alike; copies count as holders; divided parts
  explained by a cut of either size, the smallest first, or by a copy; `KeptApartBy.CUT_STEP` in
  place of `SHORT_BODY_STEP`. Since the rulings: `ENDS_NOT_INSIDE` (a body holding neither end),
  found from three interior shingles, in place of the short-only lacking-an-end outcome;
  `witness_refusals` and `EARLIER_MIN_CUT_SHARE`; shares compared as ratios; the share bands' edges
  kept at a tenth and a quarter.

**Tests**: `tests/evidence/test_near_duplicates.py` (a new section of 18 tests; t11's fixtures moved
from a 330-word card to 400 words, then to 1,000 at a share of a tenth, so its copy stays under the
share of it; the long-cut test rewritten to the new rule; since the rulings, every share boundary
moved to a tenth, the chain test moved to the overlap line, the two lacking-an-end tests turned
round, and four tests added: the overlap line, two passages sharing one run, a short body holding
neither end, and an opening alone many cards share); `test_cluster_diagnosis.py` (new outcomes; v4's readings);
`test_short_card_recall.py` (the hand-worked table, the amended targets and the guardrail);
`test_pair_shapes.py` (the stock-phrase count, and the pairs of it that overlap);
`test_fingerprints.py` (one literal); `tests/application/test_caselist_card_stats.py` (one case
through `place` moved to 1,000 words, one added at 330); `tests/scripts/test_compare_card_clusters.py`
(v4's placements and nine new tests, two of them for `--joined-in-band`); `tests/smoke/test_caselist_cards.py` (one literal).

**Matching, beside the rules**: `pair_shapes.py` (`FEW_RUNS`, `pairs_sharing_few_runs` and
`FewRunPairs`, and the count in each cluster's shapes; `OVERLAPPING_SHARE` is now the clusterer's
`MIN_OVERLAP_SHARE`).

**Spec**: `plan_specs/v1/e31-debate-file-parsing/t08-short-card-recall.yaml`, ac1's two targets, by
the PM's ruling.

**Operator tool**: `scripts/compare_card_clusters.py`: `counts --save-after`; `--after` on `counts`,
`sample`, `diagnose` and `shapes`; `shapes --preview` and `--every-cluster`; `sample --ask-shape`
and `--joined-in-band`; `--kept-apart-by` names v4's outcomes (`lacking-both-ends` since the
rulings); kept-apart pairs tallied by cut size and share band; copies in the divided-pair
explanation; `diagnose` prints `witness_refusals`.

**Docs**: `docs/data/caselist-parse-report.md` (the re-cluster section, not run; the ruling's cost
and what recovering it needs; the stock-phrase count);
`docs/data/parsed-card-store.md` (the `v4` row, and which builds read and write which version).

## Deviations from the spec

1. **The ruling contradicts two hand-labelled cards, and t08's recall target on two rows fell.**
   Put to the PM as the reason the notes ask for; the PM ruled 1(a) on 2026-10-18 and directed
   t08's ac1 amended, which this session wrote in t08's spec (outside `constraints.packages`, at the
   PM's direction) with the ruling and the two cards named. The labels are unchanged.
2. **Outside `constraints.packages`**: `tests/scripts/test_compare_card_clusters.py`, the tests of
   the script the spec asks to change, and `tests/smoke/test_caselist_cards.py`, one literal the
   suite fails without. The same two t11 recorded and the PM accepted.
3. **The limits were set from the operator's first preview, then ruled by the PM.** ac2 asks for
   them "set from the recorded samples"; t11 left none, so the first preview took them (steps 4 to
   7, 2026-10-18) and the PM ruled the values the same day. The re-measure under the set values is
   the re-preview's.
4. **The rules changed after the first preview, so the preview runs twice.** The PM's rulings on it
   (overlap, a tenth, either end) change placements, so the first preview's figures describe rules
   that no longer exist; they are kept, marked superseded, as the evidence the rulings rest on. The
   version stays `card-fingerprint-v4`, since no store has held a `v4` table.
5. **`v1-e31-t21`'s `OVERLAPPING_SHARE` is now the clusterer's constant** (`pair_shapes.py`
   imports `MIN_OVERLAP_SHARE`), so the shapes' "overlapping" and the clusterer's "overlaps" cannot
   drift apart.

## Decisions and assumptions

1. **The passage refusal is relative to the cut.** "A body that holds the passages of two or more
   clusters is not a witness for joining any of them" is read as: a container is no witness for a
   cut when it also holds a passage sharing nothing with that cut. A passage is a body it holds
   that is at least `MIN_CUT_SHARE` of it, the same line a cut must clear to join it. Read for the
   whole body instead, the labelled sets lost their one-word copies as well (Labelled sets).
2. **~~"Shares no text" is no five-word run in common.~~ Superseded by the PM on 2026-10-18:
   "shares text" means overlaps, at three-tenths of the smaller's runs.** The one-run reading was
   agreed earlier that day with a count to test it; the first preview's sample found a newly joined
   pair sharing a little that a person judged a different card, and the PM ruled it out.
3. **Conflicting joiners are both refused.** Two clusters that would join a third, and do not
   overlap each other, both stay out: the cluster holds two passages through two bodies, and the ruling
   says such a holder witnesses neither. Letting one win by fingerprint would lose fewer pairs and
   make a digest decide. Agreed by the PM on 2026-10-18.
4. **A long cut is found from either end.** A long body nine-tenths inside another that lacks its
   first or last shingle was joined by `v3` whenever the banding paired them; requiring both ends
   would have divided those joins. Agreed by the PM on 2026-10-18 on condition that the container
   rule applies to this join. It does: `witnesses` drops every container that holds another passage
   the cut does not overlap before it counts anything, whichever ends the cut has. Since item (4)
   was decided the same day, short cuts are found from either end too.
   `test_a_body_holding_another_passage_is_no_witness_for_a_long_body_lacking_one_of_its_ends` pins
   it, alone and with the other passage in a card of its own.
5. **"Holds" is one test everywhere**: at least as large, either end, and confirmed. `v3`'s nested check read nine-tenths alone, though its docstring said "by the same
   test a cut is confirmed by". The new test of a card lacking a short copy's end fails on `v3`.
6. **Copies of one size that each hold the other are joined as copies**, not as cuts, and are not
   containers of each other. Without that, two such copies inside a larger body each saw the other
   as their smallest witness, and neither ever joined it.
7. **The container count is taken as the clusters stand** each round, so a much-read card whose long
   copies have joined counts once (item 3). A body too common in round one may be compared later.
8. **The copies' Jaccard step is also refused when it would put two texts that do not overlap
   together**, joined most similar first, so an article's sliding extents break where the chain
   would reach a text that does not overlap its start.
9. **The script's fixture store keeps its 330-word card**, so that its preview shows v4 joining the
   card, the copy and the cut. The core tests' nested card moved to 1,000 words (400 at a share of a
   quarter) to keep testing the nested rule: its copy must be under the share of it.
12. **Fixtures moved with the share, each to test the same rule at the new line.** Every test that
    pinned a boundary at a quarter now pins it at a tenth (ten times the size, not four); the later
    round's refusal fixture was rescaled because at a tenth its 50-word passage became a passage of
    the copy, which then witnessed neither (the effect the PM asked to count). The diagnosis's
    share bands keep their old edges (a tenth, a quarter), so figures before and after compare.
13. **Shares are compared as ratios** (`cut / witness >= 0.1`, `shared / smaller >= 0.3`), in the
    clusterer, the diagnosis and the shapes alike, so the three read one expression. I first
    thought a product could put a cut of exactly a tenth on the wrong side; it cannot: the two forms
    agree at every boundary up to 200,000 shingles for both lines (checked), which is why the three
    product mutants are equivalent (Mutation runs).
14. **The neither-end search reads three interior shingles** (a quarter, a half and three-quarters
    of the way through each body), then confirms nine-tenths by count. A body nine-tenths inside
    another holds at least nine of every ten of its shingles, so missing all three is possible but
    rare; the outcome names a shape, it does not decide a placement. Searching every shingle of
    every long body would hold tens of millions of entries on hspolicy26.
10. **The preview's placement file holds digests, indices and ids**, as `--save-before`'s does
    (t21's Deviation 2, accepted).
11. **No session run against the operator's data directory.** Every figure here is from invented
    fixtures or invented corpora built in the scratchpad.

## Operator follow-ups

Nothing here writes to the parsed store until step 11. Don't run any of it while `caselist pull`
is running (`uv run debate-research caselist runs --last 1` shows the last run) or on a Wednesday
morning, when the agent runs. Every file these steps save holds counts, digests, indices and ids,
no text; the tallies files hold counts alone. The cards a sample shows are real disclosures, so
nothing from the screen goes into a message, a screenshot or a file.

### Before the merge: the first preview (done, 2026-10-18)

Steps 1 to 8 of the first version of this report ran on 2026-10-18 against the rules before the
PM's rulings on them: the counts, shapes, samples and diagnosis are in the parse report under "The
first preview", and the PM ruled from them the same day. Their placement,
`~/.debate-research/dev/card-clusters-t20-preview`, and `~/t20-sample-tallies.txt` describe rules
that no longer exist; keep them until step 17 removes them.

### Before the merge: the re-preview, from this worktree

The rules as ruled, placed in memory and saved to a new directory, then read like the first. One
tallies file, `~/t20-repreview-tallies.txt`, holds every sample's closing lines.

**Step R1. Check the worktree** (seconds).

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e31-t20-long-cuts-and-limits
git branch --show-current
git status --short
git log --oneline -1
uv run python -c "import debate_core.evidence.fingerprints as f, debate_core.evidence.near_duplicates as n; print(f.FINGERPRINT_VERSION, n.MIN_CUT_SHARE, n.MIN_OVERLAP_SHARE, n.MAX_CONTAINER_CLUSTERS)"
```

Expected: `task/v1-e31-t20-long-cuts-and-limits`; `git status` prints nothing; the last commit is
this report's; `card-fingerprint-v4 0.1 0.3 8`.

**Step R2. Place each caselist under the rules as ruled, compare with the store's `v3` table, and
save the placement** (about 20 minutes, as the first preview's step 2: 330, 229, 414 and 51
seconds; one command per caselist).

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e31-t20-long-cuts-and-limits
uv run python scripts/compare_card_clusters.py counts --caselist hsld26 --save-after ~/.debate-research/dev/card-clusters-t20-repreview > ~/t20-repreview-counts-hsld26.json; echo "exit $?"
uv run python scripts/compare_card_clusters.py counts --caselist hspf26 --save-after ~/.debate-research/dev/card-clusters-t20-repreview > ~/t20-repreview-counts-hspf26.json; echo "exit $?"
uv run python scripts/compare_card_clusters.py counts --caselist hspolicy26 --save-after ~/.debate-research/dev/card-clusters-t20-repreview > ~/t20-repreview-counts-hspolicy26.json; echo "exit $?"
uv run python scripts/compare_card_clusters.py counts --caselist openev --save-after ~/.debate-research/dev/card-clusters-t20-repreview > ~/t20-repreview-counts-openev.json; echo "exit $?"
jq -c 'to_entries[] | {caselist: .key} + (.value | {before_version, after_version, cards_only_before, cards_only_after, exact_fingerprints_changed, clusters_before, clusters_after, clusters_merged_into_another, clusters_divided, most_absorbed, absorbed, largest_before, largest_after, largest_after_distinct_texts, seconds})' ~/t20-repreview-counts-*.json
ls ~/.debate-research/dev/card-clusters-t20-repreview
```

Expected: `exit 0` four times; `card-fingerprint-v3` before and `card-fingerprint-v4` after;
`exact_fingerprints_changed`, `cards_only_before` and `cards_only_after` 0; four files listed.
Anything under `absorbed` at `6 to 20` or above: send it before going on. **Paste back** the four
`jq` lines.

**Step R3. ac5, the four caselists' largest clusters, and the pairs sharing one or two runs** (3 to
6 minutes: `--every-cluster` reads every body).

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e31-t20-long-cuts-and-limits
uv run python scripts/compare_card_clusters.py shapes --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --largest-clusters 3 --every-cluster --after ~/.debate-research/dev/card-clusters-t20-repreview > ~/t20-repreview-shapes.json; echo "exit $?"
jq -c 'to_entries[] | {caselist: .key, placement: .value.placement, version: .value.fingerprint_version, clusters: [.value.described_clusters[] | {rank, cards, texts: .distinct_texts, pairs, nothing: .share_of_pairs_by_shape["sharing nothing"], a_little: .pairs_by_shape["sharing a little"], few_runs: .pairs_sharing_only_few_runs, few_not_overlapping: .pairs_sharing_only_few_runs_not_overlapping, words: [.words_smallest, .words_median, .words_largest]}]}' ~/t20-repreview-shapes.json
jq -c 'to_entries[] | {caselist: .key} + .value.pairs_sharing_only_few_runs_over_every_cluster' ~/t20-repreview-shapes.json
```

Expected: `exit 0`; `version` `card-fingerprint-v4`; `nothing` 0 in all twelve clusters;
`few_not_overlapping` 0 in all twelve, and `of_them_not_overlapping` 0 on each caselist's last
line. **`of_them_not_overlapping` above 0 anywhere is a defect: stop and send the lines.** The
pairs left sharing one or two runs are pairs with a text of six runs or fewer, where that is
three-tenths. **Paste back** all eight lines.

**Step R4. ac1, the join sample, with both contained shapes asked** (seconds, then the person's
time). Every pair is shown.

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e31-t20-long-cuts-and-limits
uv run python scripts/compare_card_clusters.py sample --count 20 --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --after ~/.debate-research/dev/card-clusters-t20-repreview --ask-shape contained-under-a-third --ask-shape contained-a-third-or-more --save-tallies ~/t20-repreview-tallies.txt
```

Expected: `Drew 20 of N newly joined pairs, seed S.` **Note the seed**: step 14 uses it. ac1 passes
when no pair is answered `different card`.

**Step R5. The PM's check on the share: 20 cuts newly joined a tenth to a quarter of their witness**
(3 to 6 minutes to read every body, then the person's time). Each is shown beside the smallest body
holding it.

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e31-t20-long-cuts-and-limits
uv run python scripts/compare_card_clusters.py sample --joined-in-band a-tenth-to-a-quarter --count 20 --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --after ~/.debate-research/dev/card-clusters-t20-repreview --ask-shape identical --ask-shape contained-under-a-third --ask-shape contained-a-third-or-more --save-tallies ~/t20-repreview-tallies.txt
```

Expected: `Drew 20 of N cuts newly joined a tenth to a quarter of their smallest witness`, with N
at least 20 (if it is under 20, every one is drawn: say so). **Any `different card` answer: stop,
and send the tallies to the PM before anything else.**

**Step R6. The re-measure: every limit, the witness refusals the lower share added, and the
divided pairs** (1 to 3 minutes a caselist).

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e31-t20-long-cuts-and-limits
uv run python scripts/compare_card_clusters.py diagnose --caselist hsld26 --after ~/.debate-research/dev/card-clusters-t20-repreview --largest-clusters 3 > ~/t20-repreview-diagnosis-hsld26.json; echo "exit $?"
uv run python scripts/compare_card_clusters.py diagnose --caselist hspf26 --after ~/.debate-research/dev/card-clusters-t20-repreview --largest-clusters 3 > ~/t20-repreview-diagnosis-hspf26.json; echo "exit $?"
uv run python scripts/compare_card_clusters.py diagnose --caselist hspolicy26 --after ~/.debate-research/dev/card-clusters-t20-repreview --largest-clusters 3 > ~/t20-repreview-diagnosis-hspolicy26.json; echo "exit $?"
uv run python scripts/compare_card_clusters.py diagnose --caselist openev --after ~/.debate-research/dev/card-clusters-t20-repreview --largest-clusters 3 > ~/t20-repreview-diagnosis-openev.json; echo "exit $?"
jq -c 'to_entries[] | {caselist: .key, short: .value.cuts.short_by_outcome, long: .value.cuts.long_by_outcome, under_share: [.value.cuts.short_under_the_minimum_share_by_share, .value.cuts.long_under_the_minimum_share_by_share], refusals: .value.witness_refusals, divided: .value.divided_pairs.pairs}' ~/t20-repreview-diagnosis-*.json
jq -c 'to_entries[] | {caselist: .key, unexplained: [.value.divided_pairs.by_reason[] | select(.kind == "no cut or copy links this part to the rest") | .pairs] | add, by_outcome: ([.value.divided_pairs.by_reason[] | {key: (.outcome // "none"), value: .pairs}] | group_by(.key) | map({key: .[0].key, value: (map(.value) | add)}) | from_entries)}' ~/t20-repreview-diagnosis-*.json
cat ~/t20-repreview-tallies.txt
```

Expected: `exit 0` four times. `refusals` gives, per caselist, the containers refused as witnesses
and how many of those refusals the lower share added. `unexplained` should be `null` or a handful:
the 9 of the first preview now count under "nine-tenths inside a body that holds neither of its
ends". **Paste back** the eight `jq` lines and the tallies file: two blocks, R4's and R5's.

**Step R7.** The PM reads R2 to R6. The session then records the figures and asks for the merge.

### After the merge

**Step 9. Reinstall the agent on the first pre-release carrying this task, before the rebuild.**
Every build reads a `v4` table, since no code compares the version. But the agent's parse stage
rebuilds each caselist it imports into under its own build's version and publishes it to dev, so
`v1.1.0-dev.18` would put `v3` back the next week it ran. This finds the tag; then follow
[Reinstalling the agent](../runbooks/caselist-scheduled-sync.md#reinstalling-the-agent) with it.

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
git branch --show-current
git pull --ff-only origin dev
git fetch --tags origin
T20=$(git log -1 --format=%H --grep='^v1-e31-t20-long-cuts-and-limits:')
echo "${T20}"
git tag --list 'v1.1.0-dev.*' --contains "${T20}" --sort=v:refname | head -1
```

Expected: `dev`, one commit id, and one tag. No tag yet means the pre-release is still building.

**Step 10. Save the `v3` tables** (seconds).

```zsh
mkdir -p ~/.debate-research/dev/card-clusters-v3
for c in hsld26 hspf26 hspolicy26 openev; do cp -p ~/.debate-research/dev/parsed/${c}/2026.10.12-docx-3/occurrences.jsonl ~/.debate-research/dev/card-clusters-v3/${c}.jsonl; done
jq -r '.fingerprint_version' ~/.debate-research/dev/card-clusters-v3/*.jsonl | sort | uniq -c
```

Expected: one line, every row `card-fingerprint-v3`. Anything else, stop: the agent has run on
another build since 2026-10-16, or the directory has changed.

**Step 11. The dev rebuild, without publishing** (about 345, 219, 482 and 68 s, as the 2026-10-16
rebuild; no AWS session needed).

```zsh
DEBATE_ENV=dev uv run debate-research --json caselist parse --caselist hsld26 > ~/t20-parse-dev-hsld26.json; echo "exit $?"
DEBATE_ENV=dev uv run debate-research --json caselist parse --caselist hspf26 > ~/t20-parse-dev-hspf26.json; echo "exit $?"
DEBATE_ENV=dev uv run debate-research --json caselist parse --caselist hspolicy26 > ~/t20-parse-dev-hspolicy26.json; echo "exit $?"
DEBATE_ENV=dev uv run debate-research --json caselist parse --caselist openev > ~/t20-parse-dev-openev.json; echo "exit $?"
for c in hsld26 hspf26 hspolicy26 openev; do jq -c '(.data // .error.details) | {caselist, version, fingerprint_version, attempted, store, elapsed_seconds}' ~/t20-parse-dev-${c}.json; done
```

Expected: `exit 0`; `fingerprint_version` `card-fingerprint-v4`; `attempted` 0 unless sources
arrived since; `store.clusters` equal to step R2's `clusters_after`.

**Step 12. The counts against `card-fingerprint-v3`** (seconds; both tables exist).

```zsh
uv run python scripts/compare_card_clusters.py counts --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --before ~/.debate-research/dev/card-clusters-v3 > ~/t20-counts-v4.json; echo "exit $?"
jq -c 'to_entries[] | {caselist: .key} + (.value | {before_version, after_version, cards_only_before, cards_only_after, exact_fingerprints_changed, clusters_before, clusters_after, clusters_merged_into_another, clusters_divided, largest_before, largest_after})' ~/t20-counts-v4.json
```

Expected: step R2's figures exactly, if no source arrived between.

**Step 13. Shapes** (3 to 6 minutes, as step R3).

```zsh
uv run python scripts/compare_card_clusters.py shapes --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --largest-clusters 3 --every-cluster > ~/t20-shapes.json; echo "exit $?"
jq -c 'to_entries[] | {caselist: .key, version: .value.fingerprint_version, clusters: [.value.described_clusters[] | {rank, cards, texts: .distinct_texts, pairs, nothing: .share_of_pairs_by_shape["sharing nothing"]}]}' ~/t20-shapes.json
jq -c 'to_entries[] | {caselist: .key} + .value.pairs_sharing_only_few_runs_over_every_cluster' ~/t20-shapes.json
```

Expected: step R3's figures, from the store's table: `version` `card-fingerprint-v4`, `nothing` 0,
and the same stock-phrase count.

**Step 14. The join sample, with step R4's seed** (seconds, then the person's time). The same 20
pairs as step R4 (seed 963278315, 2026-10-18), if no source arrived between.

```zsh
uv run python scripts/compare_card_clusters.py sample --count 20 --seed 963278315 --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev --before ~/.debate-research/dev/card-clusters-v3 --ask-shape contained-under-a-third --ask-shape contained-a-third-or-more --save-tallies ~/t20-repreview-tallies.txt
cat ~/t20-repreview-tallies.txt
```

**Steps 12 to 14 go to the PM before steps 15 and 16.**

**Step 15. The dev publish** (the rebuild again, about 19 minutes, since `caselist parse --publish`
always rebuilds; then one upload a caselist, the occurrence table).

```zsh
aws sso login --profile debate-dev-evidence
DEBATE_ENV=dev uv run debate-research --json caselist parse --caselist hsld26 --publish > ~/t20-publish-dev-hsld26.json; echo "exit $?"
DEBATE_ENV=dev uv run debate-research --json caselist parse --caselist hspf26 --publish > ~/t20-publish-dev-hspf26.json; echo "exit $?"
DEBATE_ENV=dev uv run debate-research --json caselist parse --caselist hspolicy26 --publish > ~/t20-publish-dev-hspolicy26.json; echo "exit $?"
DEBATE_ENV=dev uv run debate-research --json caselist parse --caselist openev --publish > ~/t20-publish-dev-openev.json; echo "exit $?"
for c in hsld26 hspf26 hspolicy26 openev; do jq -c '(.data // .error.details) | {caselist, fingerprint_version, attempted, publish: .publish.counts}' ~/t20-publish-dev-${c}.json; done
```

Expected: `exit 0`, `card-fingerprint-v4`, `attempted` 0, and one uploaded object a caselist.

**Step 16. Prod, only after the PM has read steps 12 to 14** (about 19 minutes), from the same dev
data directory, as the 2026-10-16 publish was:

```zsh
aws sso login --profile debate-prod-evidence
DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research --json caselist parse --caselist hsld26 --publish --confirm-prod > ~/t20-publish-prod-hsld26.json; echo "exit $?"
DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research --json caselist parse --caselist hspf26 --publish --confirm-prod > ~/t20-publish-prod-hspf26.json; echo "exit $?"
DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research --json caselist parse --caselist hspolicy26 --publish --confirm-prod > ~/t20-publish-prod-hspolicy26.json; echo "exit $?"
DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research --json caselist parse --caselist openev --publish --confirm-prod > ~/t20-publish-prod-openev.json; echo "exit $?"
```

Expected: `exit 0` each.

**Step 17. Remove what the steps saved:**

```zsh
rm -r ~/.debate-research/dev/card-clusters-t20-preview ~/.debate-research/dev/card-clusters-t20-repreview ~/.debate-research/dev/card-clusters-v3
rm ~/t20-preview-counts-*.json ~/t20-preview-shapes.json ~/t20-preview-diagnosis-*.json ~/t20-repreview-counts-*.json ~/t20-repreview-shapes.json ~/t20-repreview-diagnosis-*.json ~/t20-parse-dev-*.json ~/t20-counts-v4.json ~/t20-shapes.json ~/t20-publish-*.json ~/t20-sample-tallies.txt ~/t20-repreview-tallies.txt
```

## Follow-up work

1. **Text-disjoint trims of one card (E31, a new task if the PM files one).** Recovering Brannock's
   and Kessler's pairs needs evidence beyond the bodies: a cite, a tag, or the files the copies came
   from. The PM said on 2026-10-18 they will consider it separately.
2. **Bodies nine-tenths inside one that holds neither of their ends (E31, p3, the PM is filing
   it).** Named by the diagnosis since the rulings; finding them in the clusterer needs a lookup
   that is not by the body's ends.
3. **A publish-only path for the parsed store (E31 or E34).** `caselist parse --publish` always
   rebuilds, so the PM's order (rebuild, read, then publish) costs a second rebuild of about 19
   minutes, and prod a third.
4. **The agent rewrites a newer table with an older version (E34).** Any build older than the
   table's version puts its own back on the next parse stage. A guard could refuse to publish an
   occurrence table older than the one the bucket holds; today it is the reinstall in step 9.
5. **`tests/scripts/test_compare_card_clusters.py` has four pyright errors outside CI's scope**
   (`include = ["packages"]`): one unresolved import and three `object is not iterable`, the same in
   the start commit's file. Not this task's.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
