# Session report: v1-e39-t12-card-only-results

| | |
|---|---|
| Task | `v1-e39-t12-card-only-results` — Only real cards come back: entries with no cite or a few words of text, counted before any rule |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t12-card-only-results.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t12-card-only-results.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t12-card-only-results` |
| Session status | PARTIAL: everything a session can close is done; ac3 is the operator's after the merge, so the Goal stays `InProgress` <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The index build now leaves out every cluster whose representative is no card. That is the PM's
rule C of 2026-10-22: CITE_ONLY, or no cite and fewer than 25 whitespace-separated words of evidence
text, judged on the representative. The rule came after the counts. Over the dev index
`767b9c7c056b80cb` (52,059 documents), only 334 documents had the shape the spec guessed at (no cite,
under 25 words), and the coach's example turned out to be CITE_ONLY, which a "no cite" rule cannot
catch ([The counts](#the-counts)). The parser, the parsed store and every fingerprint are untouched.
The excluded count, per store and reason, is in the build's result, the `tub index build` summary and
the weekly run's record, and not in the manifest.

**What the PM should look at first:**

1. **Build time.** The rule needs the card, which only the source's document record holds, so the
   build now reads the representatives' sources twice. Timed read-only, one extra pass costs about
   2.1 ms a document, roughly 100 s on top of a build last measured at 205 s
   ([Decisions](#decisions-and-assumptions)).
2. **The agent must be reinstalled soon after the hand publish**, not just after it. Until then its
   older build rebuilds without the rule the first week the stores change. The runbook says so.

ac3, the before and after counts, is the operator's after the merge: two blocks in
[Operator follow-ups](#operator-follow-ups). The expected drop is 1,625 documents, at most 3.86% of a
store, so the shrink guard should pass it.

## Plan nodes

<!-- One row per Plan graph node, in the order they were completed. -->

| Node | Status | Notes |
|---|---|---|
| `card-only` | Done | Counts, the PM's ruling, the rule red then green, mutation-checked; ac3 is the operator's |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: tallies by cite, word band and tag, per caselist, counts only, sent to the PM before any rule | PASS | [The counts](#the-counts), sent 2026-10-22 as a relay prompt; no code changed before it |
| ac2: the ruled rule leaves excluded documents out of the build, red first, excluded count in the build summary and the run record | PASS | [Red then green](#red-then-green): 19 failed against a skeleton that left nothing out, then 140 passed; [mutation testing](#mutation-testing) 12 of 12 caught. The count is in `BuiltSearchIndex.not_cards`, `tub index build`'s caption and `--json` (`test_tub_index_build_says_what_it_left_out_as_no_card_by_store`), the stage's counts and reason (`test_index_stage_records_what_its_build_left_out_as_no_card`) and the run summary and details (`test_index_stage_what_its_build_left_out_as_no_card_is_in_the_summary_and_details`) |
| ac3: the dev index's document count before and after, in `docs/data/evidence-search-pilot.md` (operator) | NOT RUN | Measurable only after the merge: [Operator follow-ups](#operator-follow-ups). The table is in place in the pilot record with the counted "before" and the expected "after" |
| Node `card-only`: `uv run pytest packages/debate_core/tests/application -k search_index` | PASS | `218 passed in 4.26s` |

## The counts

Read-only, on the operator's Mac, by this session (working agreement 2): the newest directory under
`~/.debate-research/dev/tub-index/`, `767b9c7c056b80cb`, parser `2026.10.20-docx-6`, latest snapshot
2026-10-20, 52,059 documents, opened `mode=ro`. The tally took 2.8 s wall-clock; the follow-up
counts below took 2.8 to 6.8 s each. Each script printed caselist slugs and numbers, never a field's
text; the scripts stayed in the session's scratch directory.

How a document was counted, from its `documents` row (the representative's card):

* **Cite present:** `cite` holds something besides whitespace. The column is `NOT NULL`, and "no
  cite" is the parser's empty `full_cite`.
* **Tag present:** `tag` is not null and not blank.
* **Words:** `len(text.split())` over `text`, the representative's evidence text. A CITE_ONLY card's
  text is empty, so it is 0 words.

### Every document, by word band

| Caselist | 0 | 1–9 | 10–24 | 25–49 | 50–99 | 100+ | All |
|---|---:|---:|---:|---:|---:|---:|---:|
| hsld26 | 366 | 103 | 161 | 252 | 604 | 11,739 | 13,225 |
| hspf26 | 297 | 62 | 92 | 295 | 740 | 9,907 | 11,393 |
| hspolicy26 | 558 | 79 | 107 | 304 | 1,049 | 19,498 | 21,595 |
| openev | 70 | 15 | 21 | 41 | 242 | 5,457 | 5,846 |
| All | 1,291 | 259 | 381 | 892 | 2,635 | 46,601 | 52,059 |

### Cite present or absent

| Caselist | Cite | 0 | 1–9 | 10–24 | 25–49 | 50–99 | 100+ | All |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| hsld26 | yes | 366 | 41 | 78 | 148 | 404 | 10,705 | 11,742 |
| hsld26 | no | 0 | 62 | 83 | 104 | 200 | 1,034 | 1,483 |
| hspf26 | yes | 297 | 16 | 42 | 127 | 452 | 7,731 | 8,665 |
| hspf26 | no | 0 | 46 | 50 | 168 | 288 | 2,176 | 2,728 |
| hspolicy26 | yes | 558 | 42 | 68 | 227 | 843 | 18,210 | 19,948 |
| hspolicy26 | no | 0 | 37 | 39 | 77 | 206 | 1,288 | 1,647 |
| openev | yes | 70 | 5 | 14 | 36 | 215 | 5,150 | 5,490 |
| openev | no | 0 | 10 | 7 | 5 | 27 | 307 | 356 |
| All | yes | 1,291 | 104 | 202 | 538 | 1,914 | 41,796 | 45,845 |
| All | no | 0 | 155 | 179 | 354 | 721 | 4,805 | 6,214 |

### Tag present or absent

| Caselist | Tag | 0 | 1–9 | 10–24 | 25–49 | 50–99 | 100+ | All |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| hsld26 | yes | 201 | 99 | 148 | 231 | 574 | 11,451 | 12,704 |
| hsld26 | no | 165 | 4 | 13 | 21 | 30 | 288 | 521 |
| hspf26 | yes | 188 | 57 | 88 | 277 | 684 | 9,284 | 10,578 |
| hspf26 | no | 109 | 5 | 4 | 18 | 56 | 623 | 815 |
| hspolicy26 | yes | 417 | 75 | 104 | 293 | 1,020 | 19,307 | 21,216 |
| hspolicy26 | no | 141 | 4 | 3 | 11 | 29 | 191 | 379 |
| openev | yes | 57 | 15 | 21 | 41 | 240 | 5,417 | 5,791 |
| openev | no | 13 | 0 | 0 | 0 | 2 | 40 | 55 |
| All | yes | 863 | 246 | 361 | 842 | 2,518 | 45,459 | 50,289 |
| All | no | 428 | 13 | 20 | 50 | 117 | 1,142 | 1,770 |

### No cite and fewer than 25 words: the spec's example shape

| Caselist | 1–9 | 10–24 | Together | Share of the caselist |
|---|---:|---:|---:|---:|
| hsld26 | 62 | 83 | 145 | 1.1% |
| hspf26 | 46 | 50 | 96 | 0.8% |
| hspolicy26 | 37 | 39 | 76 | 0.4% |
| openev | 10 | 7 | 17 | 0.3% |
| All | 155 | 179 | 334 | 0.6% |

There are none at 0 words: a document with no cite always has text.

### What the counts say about shape

* **Every document with no cite has a tag** (6,214 of 6,214), and every CITE_ONLY document has a cite
  (1,291 of 1,291). So a CITE_ONLY document can never meet a "no cite" rule.
* **Completeness:** 50,768 FULL, 0 ABBREVIATED, 1,291 CITE_ONLY. The 0-word band is exactly the
  CITE_ONLY documents. No occurrence in the index is ABBREVIATED either (332,321 FULL, 3,343
  CITE_ONLY occurrence rows).
* **Cite present but the parser read no short cite:** 15,023 documents, 13,261 of them with 100+
  words. Most are real cards, so an unreadable short cite on its own does not mark a non-card.

### The coach's example

Counted read-only by matching the public resolution's wording, "negate" with "outer space
colonization is a moral imperative", in each document's tag and text, whitespace and case folded.
Counts only. Four documents, all hsld26, and the sentence is in the **tag** of each, never the text:

| Completeness | Text words | Cite words | Short cite readable | Year in cite | URL in cite | Documents |
|---|---|---|---|---|---|---:|
| CITE_ONLY | 0 | 1–9 | no | no | no | 1 |
| CITE_ONLY | 0 | 10–24 | yes | no | no | 1 |
| FULL | 100+ | 0 (no cite) | no | no | no | 1 |
| FULL | 25–49 | 25–49 | yes | no | no | 1 |

The coach saw a card whose whole content was that one line. The likeliest of the four is the first
CITE_ONLY document: the sentence as a tag, a short line under it that the parser took for a cite (no
short cite, no year, no URL), and no text. None of the four has no cite and fewer than 25 words.

### CITE_ONLY documents by what their cite looks like

| Caselist | CITE_ONLY | No readable short cite | …and no year and no URL in the cite |
|---|---:|---:|---:|
| hsld26 | 366 | 241 | 117 |
| hspf26 | 297 | 78 | 14 |
| hspolicy26 | 558 | 325 | 84 |
| openev | 70 | 39 | 25 |
| All | 1,291 | 683 | 240 |

"Year" is a four-digit 19xx or 20xx standing alone in the cite; "URL" is `http` anywhere in it.

### Candidate rules, per caselist (documents excluded, and share of the caselist)

| Caselist | Documents | A: no cite, under 25 words | B: A, or CITE_ONLY whose cite has no readable short cite, no year and no URL | C: A, or any CITE_ONLY | No cite at any length (not proposed) |
|---|---:|---:|---:|---:|---:|
| hsld26 | 13,225 | 145 (1.1%) | 262 (2.0%) | 511 (3.9%) | 1,483 (11.2%) |
| hspf26 | 11,393 | 96 (0.8%) | 110 (1.0%) | 393 (3.4%) | 2,728 (23.9%) |
| hspolicy26 | 21,595 | 76 (0.4%) | 160 (0.7%) | 634 (2.9%) | 1,647 (7.6%) |
| openev | 5,846 | 17 (0.3%) | 42 (0.7%) | 87 (1.5%) | 356 (6.1%) |
| All | 52,059 | 334 (0.6%) | 574 (1.1%) | 1,625 (3.1%) | 6,214 (11.9%) |

Against the shrink guard's 10%, measured against the current index: A, B and C stay under it in
every caselist. Only "no cite at any length" passes it, in hsld26 and hspf26, and it would also drop
4,805 documents of 100 words or more, most of them likely real evidence whose cite the parser
missed.

**Judged on the representative.** Every count above is of the representative's card, the only one
the index stores. A CITE_ONLY representative means every member of its cluster is CITE_ONLY, since
completeness is the first key of the representative order. A representative with no cite says
nothing about its siblings: of rule A's 334 documents, 193 have one occurrence and 141 have several
(17 in one file, 124 across files; hsld26 62, hspf26 35, hspolicy26 42, openev 2). Whether a sibling
has a cite is not in the index; the occurrence table carries no cite.

### Questions sent to the PM, 2026-10-22

1. Which rule: A, B or C. The session recommends C.
2. Rule A's threshold: fewer than 25 words, the spec's example, or fewer than 10.
3. Judge a cluster by its representative alone, as the spec words it, or look for a cited sibling.
   The session recommends the representative.
4. The excluded count goes in the build's result, `tub index build`'s summary and the weekly run's
   record, and not in the manifest. The PM ruled on 2026-10-22 that the manifest and pointer get no
   new field. As a result `built_from` cannot see the rule, and the operator's hand build after the
   merge is what replaces the index built without it.
5. Whether the operator's publish block carries `--allow-shrink`. Under every proposed rule the shrink
   is under 10%, and `--allow-shrink` would also pass any other shrink in the same publish. The
   session recommends a plain publish, going back to the PM if it is refused.

### The PM's ruling, 2026-10-22

Rule C: a document is left out when its representative is CITE_ONLY, or has no cite and fewer than 25
words of evidence text, counted as whitespace-separated words. Judged on the representative alone.
The counts go in the build's result, the `tub index build` summary and the weekly run's record, not
the manifest. The first publish after the merge is by hand, with no `--allow-shrink`; a refusal goes
back to the PM. The ruling is recorded in the spec above ac2. The 141 multi-occurrence documents of
the no-cite part are above, under "Judged on the representative".

## Red then green

Red, against a skeleton commit (`beddf13`) that has the rule's surface but leaves nothing out
(`not_a_card` returns `None`), with the counts plumbed through the build result, the CLI, the stage
and the run record:

```
.venv/bin/python -m pytest -q -n 4 -m "not slow and not live" packages/debate_core/tests/application/test_search_index_build.py packages/debate_core/tests/application/test_search_index_stage.py packages/debate_core/tests/application/test_caselist_sync_index_stage.py packages/debate_cli/tests/test_tub_index.py
19 failed, 121 passed in 2.74s
```

The 19 are every rule test, each failing on its assertion and none on an error: 10 cases of
`test_search_index_not_a_card` (all those that expect a reason), the five left-out words matching
nothing, the kept set, the numbering, the counts by store and why, the manifest's counts, the
shuffles, and the stage's `test_index_stage_records_what_its_build_left_out_as_no_card`. The tests
that pass red are the cards kept, the zero counts, the sentence, and the plumbing of the CLI, the
summary and the details, which carry whatever the build counted. Green (`026ed9a`): the same command,
`140 passed`.

One test was weakened before the red run was recorded: a left-out word carried only by a
non-representative member passed red, because a non-representative's text is never stored. It
proved nothing, so it was removed.

## Mutation testing

Twelve mutants of `search_index_build.py`, each run against `test_search_index_build.py` alone
(`-n 2 -p no:randomly -p no:cacheprovider`, each with a new, empty `HYPOTHESIS_STORAGE_DIRECTORY`,
though nothing here uses Hypothesis). The file was restored from the committed copy after each one,
and `git diff --quiet` was clean at the end. Each was caught by failing tests with pytest's exit 1.
None was caught by an error.

| Mutant | Result | Tests failed | First to fail | Run time |
|---|---|---:|---|---:|
| threshold 25 to 24 | CAUGHT | 11 | `test_search_index_not_a_card[no-cite-24-words]` | 1.8 s |
| threshold 25 to 26 | CAUGHT | 10 | `test_search_index_not_a_card[no-cite-25-words]` | 1.6 s |
| `<` to `<=` | CAUGHT | 8 | `test_search_index_not_a_card[no-cite-25-words]` | 1.7 s |
| CITE_ONLY branch removed | CAUGHT | 9 | `test_search_index_not_a_card[cite-only]` | 1.7 s |
| CITE_ONLY completeness to ABBREVIATED | CAUGHT | 13 | `test_search_index_leaves_out_a_suppressed_occurrence_and_an_emptied_cluster` | 1.8 s |
| `and` to `or` | CAUGHT | 32 | `test_search_index_holds_one_document_per_cluster` | 2.1 s |
| cite strip removed | CAUGHT | 7 | `test_search_index_not_a_card[blank-cite-24-words]` | 2.5 s |
| cite negation removed | CAUGHT | 38 | `test_search_index_school_and_team_code_match_nothing` | 2.2 s |
| word count on single spaces | CAUGHT | 9 | `test_search_index_not_a_card[no-cite-25-words]` | 1.7 s |
| cluster never left out | CAUGHT | 8 | `test_search_index_leaves_out_every_cluster_whose_representative_is_no_card` | 1.8 s |
| numbered among all candidates | CAUGHT | 8 | `test_search_index_leaves_out_every_cluster_whose_representative_is_no_card` | 1.7 s |
| every exclusion counted as cite only | CAUGHT | 2 | `test_search_index_card_only_counts_by_store_and_why` | 1.9 s |

A first run with `-x` ended each mutant with exit 2 (xdist reports `-x` as interrupted) while
naming a failed test. It was redone without `-x` so that each catch is a plain exit 1; the table is
the second run. The judging of a representative rather than every member is pinned by the fixture's
`UNCITED_REPRESENTATIVE` cluster (its cited sibling goes with it) and `CITED_REPRESENTATIVE` (its
CITE_ONLY member does not take it out).

## The second read, timed

Read-only, the operator's Mac, 2026-10-22, the dev data directory: one pass of what the rule adds
(read each representative's source record, build its cards, check the fingerprint, judge the card),
for two stores. A row of each cluster was taken in representative order, without the attribution
key, so the set of sources read is the build's. The script stayed in the session's scratch
directory and printed numbers only.

| Store | Sources | Clusters | Seconds | Left out: cite only | Left out: no cite, under 25 words |
|---|---:|---:|---:|---:|---:|
| openev | 95 | 5,846 | 4.4 | 70 | 17 |
| hspf26 | 2,133 | 11,393 | 24.3 | 297 | 96 |

The tallies are exactly the counts above (openev 70 and 17, hspf26 297 and 96), which checks the
code's rule against the rule as counted. At about 2.1 ms a document, the whole dev store's 52,059
add roughly 100 s to the build.

## Checks run before the report

* **The affected set** (`uv run scripts/affected_tests.py`): 213 of 405 test files (52.6%).
  Run as `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -q -n auto -m "not slow and not
  live" <the 213 files>`, it was stopped by the alarm at 115 s, about 75% through, so it is over two
  minutes and left to the pull request's `ci` (working agreement 10). Before it stopped it showed
  one failure.
* **Instead, the changed test directories and the always-run list:** `perl -e 'alarm 115; exec @ARGV'
  .venv/bin/python -m pytest -q -rfE -n auto -m "not slow and not live" packages/debate_core/tests/application
  packages/debate_cli/tests tests/architecture tests/specs tests/docs tests/scripts/test_check_command_blocks.py
  tests/scripts/test_docs_index.py` gave `1 failed, 4493 passed in 113.88s`. The failure was
  `tests/architecture/test_single_interpreter_source.py::test_no_python_version_is_named_outside_the_one_declaration`:
  "at most 3.9%" in two documents and a docstring reads as a Python version. Rewritten as the exact
  3.86% (`22ff4bf`), that file gave `23 passed`. The whole set was not run again: the change was
  wording in two documents and one docstring.
* An earlier fix the affected set would also have found: `test_search_index_shrink_guard.py` builds
  a `BuiltSearchIndex` by hand and now passes `not_cards` (`33 passed`).
* `uv run ruff format --check .`: 1125 files already formatted. `uv run ruff check .`: all checks
  passed. `uv run pyright packages/debate_core packages/debate_cli`: 0 errors. `uv run lint-imports`:
  15 kept, 0 broken. `uv run python scripts/check_thin_handlers.py`: 46 handlers within 25
  statements. `uv run scripts/check_command_blocks.py`: no `#` comments in 352 blocks.
  `uv run scripts/check_links.py`: 2044 links and anchors. `uv run python scripts/docs_index.py
  --check-descriptions`: 43 documents described. `uv run scripts/validate_specs.py`: OK.

## Files changed

* `packages/debate_core/src/debate_core/application/search_index_build.py`: the rule
  (`CARD_ONLY_RULE`, `NotACard`, `not_a_card`), the pass that judges each representative and numbers
  the documents kept, `BuiltSearchIndex.not_cards`, and the JSON and sentence forms of the counts.
* `.../application/search_index_refresh.py`, `caselist_sync.py`, `sync_runs.py`: the stage carries a
  build's counts into its reason and `SearchIndexStageCounts.not_cards_by_store`, and the run
  details' `SearchIndexCounts` reads them (`extra="ignore"`, so older readers pass over the key).
* `packages/debate_cli/src/debate_cli/commands/tub_index.py`: the build's `--json`
  `not_cards_by_store` and its table caption.
* Tests: `test_search_index_build.py` (the rule and the build), `test_search_index_stage.py`,
  `test_caselist_sync_index_stage.py`, `test_search_index_shrink_guard.py`, and
  `packages/debate_cli/tests/test_tub_index.py`.
* Docs: `docs/data/search-index.md` (the rule, its constant, where the count is, the second read's
  cost, `doc_id` among the documents kept), `docs/data/evidence-search-pilot.md` (the ac3 table),
  `docs/runbooks/caselist-scheduled-sync.md` (the two operator blocks, the order against reinstalling
  the agent, the summary key), `docs/guides/search-index.md` (one paragraph).
* The spec: the PM's ruling as a comment above ac2.

## Deviations from the spec

* **Files outside `constraints.packages`, as the PM's ruling asked.** The ruling named "the tub
  index build summary", which is printed by `debate_cli` (`commands/tub_index.py` and its test), and
  "the runbook" (`docs/runbooks/caselist-scheduled-sync.md`). `docs/guides/search-index.md` got one
  paragraph, because it says what `build` prints. None of these is in the spec's package list.
* **The counts were taken by this session**, read-only and in seconds, as working agreement 2 allows
  and the PM's context said.

## Decisions and assumptions

* **Two reads, not memory and not gaps.** `doc_id` is documented as a rank from 1, and the writer
  inserts each row by a `doc_id` fixed before it is handed over. Judging a card needs the card, which
  only the document record holds. Holding every card until all were judged would keep about six
  million span objects in memory. Numbering with gaps would break the documented contract. So a
  first pass judges, and the second writes. Both passes go through `_card_of`, so an excluded card
  is fingerprint-checked as a kept one is. The cost is above, about 100 s. If it matters, the writer
  could close the gaps itself at `finish`, with one read. That is an integrations change and the PM's
  call.
* **The cite judged is the full cite.** A cite whose only text is a cutter mark is left as it is by
  `cite_without_cutter_mark`, so "empty after stripping" is the same for the full and the stored
  cite. A cite of only whitespace is no cite, as counted.
* **Every store built gets a count, zeros included**, so a summary says `0` rather than leaving a
  store out. `clusters_left_out` keeps its meaning, clusters with no surviving occurrence; the no-card
  clusters are counted apart from it.
* **`out` is still created before anything is read**, so a refusal leaves an empty `out`, as before.
  The first pass now raises a missing card's refusal before the write pass would have.
* **The stage says the count only when it built.** A run that kept the newest index has no count to
  give, so its summary has `null`.
* **The runbook says reinstall soon, not only later.** The PM's ruling put the hand build before the
  reinstall. The runbook adds that the reinstall should come before the agent's next Wednesday run:
  an agent still on its older build rebuilds without the rule the first week the stores change.
* **The publish block uses `--newest`**, which is the index the first block built unless another
  build ran in between. The block refuses to run while a pull is running, and its success check names
  the index id the first block printed.

## Operator follow-ups

### 1. The first index with the card-only rule (ac3): after the merge, before reinstalling the agent

Two blocks, as in [the scheduled sync runbook](../runbooks/caselist-scheduled-sync.md#the-first-index-with-the-card-only-rule-v1-e39-t12-once).
The first builds and compares, and publishes nothing. Read its output before the second.

**Operator command** (expected runtime about 5 minutes: a full build, which reads every
representative's source twice)
Where: a new terminal window on your Mac. The block starts in this task's worktree, whose build is
the one that merged; run it after the merge and before `scripts/task finish` removes the worktree.
From a `dev` checkout instead, `cd` there and run `uv sync --all-packages` first
```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e39-t12-card-only-results
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
echo "running pull: ${PULL:-none}"
echo "DEBATE_ overrides: ${OVERRIDES:-none}"
if [[ -n "$PULL" || -n "$OVERRIDES" ]]; then
  echo "STOP: the line above that is not none says why. Wait for the pull to finish, or open a new window."
else
  aws sso login --profile debate-dev-evidence
  BUCKET=$(python3 -c 'import tomllib; print(tomllib.load(open("config/profiles/dev.toml", "rb"))["storage"]["s3"]["bucket"])')
  CARD_ONLY=$(mktemp -d)
  aws s3 cp "s3://${BUCKET}/reports/tub/search/current.json" "${CARD_ONLY}/current.json" --profile debate-dev-evidence
  MANIFEST_KEY=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["manifest_key"])' "${CARD_ONLY}/current.json")
  aws s3 cp "s3://${BUCKET}/${MANIFEST_KEY}" "${CARD_ONLY}/current-manifest.json" --profile debate-dev-evidence
  STORES=$(python3 -c 'import json, sys; print(" ".join("--caselist " + one["caselist"] for one in json.load(open(sys.argv[1]))["stores"]))' "${CARD_ONLY}/current-manifest.json")
  echo "building: ${STORES}"
  DEBATE_ENV=dev uv run debate-research --json tub index build ${=STORES} > "${CARD_ONLY}/build.json"
  python3 - "${CARD_ONLY}/current-manifest.json" "${CARD_ONLY}/build.json" <<'EOF'
import json, sys
current = json.load(open(sys.argv[1]))
envelope = json.load(open(sys.argv[2]))
if not envelope.get("data"):
    print("STOP: the build failed:", (envelope.get("error") or {}).get("code"))
    raise SystemExit(1)
built = envelope["data"]
before = current["counts"]["documents_by_store"]
after = built["manifest"]["counts"]["documents_by_store"]
left = built["not_cards_by_store"]
print("current index", current["index_id"], current["counts"]["documents"], "documents")
print("new index", built["manifest"]["index_id"], built["manifest"]["counts"]["documents"], "documents")
stop = False
for store in sorted(set(before) | set(after)):
    was, now = before.get(store, 0), after.get(store, 0)
    share = 100 * now / was if was else 100.0
    out = left.get(store, {})
    print(f"{store}: {was:,} -> {now:,} documents ({share:.1f}%); left out as no card: "
          f"{out.get('cite_only', 0):,} cite only, {out.get('no_cite_few_words', 0):,} with no cite and under 25 words")
    stop = stop or now == 0 or share < 90
print("STOP: a store is empty or under 90% of the current index" if stop else "OK: every store keeps 90% or more")
EOF
fi
```
Success looks like `current index <id>`, `new index <id>`, one line per store with a share of about
96% or more, and `OK: every store keeps 90% or more`. Each store's "left out as no card" should be
near the counts above, a little higher if the store has grown since 2026-10-22. **Stop, and take the
output to the PM**, on a `STOP` line, on a store whose share is under 95%, or on counts far from
those above: the rule is not doing what was counted. Nothing has been published.

The second block publishes the newest index, the one the first block built, with no `--allow-shrink`.

**Operator command** (expected runtime under a minute)
Where: the same window
```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e39-t12-card-only-results
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
echo "running pull: ${PULL:-none}"
echo "DEBATE_ overrides: ${OVERRIDES:-none}"
if [[ -n "$PULL" || -n "$OVERRIDES" ]]; then
  echo "STOP: the line above that is not none says why. Wait for the pull to finish, or open a new window."
else
  aws sso login --profile debate-dev-evidence
  DEBATE_ENV=dev uv run debate-research tub index publish --env dev --newest
fi
```
Success looks like a table titled with the new index id the first block printed, whose last row is
`reports/tub/search/current.json`. **If it is refused** with `would shrink the published search
index`, stop and take the refusal to the PM: do not publish past the guard. Then paste both blocks' output into the session (or to the PM). The before and after counts go in
[the pilot's record](../data/evidence-search-pilot.md#the-card-only-rule-v1-e39-t12) (ac3).

### 2. Reinstall the agent before its next Wednesday run

With a build carrying `v1-e39-t12`, as [Reinstalling the agent](../runbooks/caselist-scheduled-sync.md#reinstalling-the-agent)
says. Until then the agent's older build would rebuild without the rule the first week the stores
change.

## Follow-up work

* **No ABBREVIATED card in the dev index** (E31, the parser). Not one of 335,664 occurrences is
  ABBREVIATED, though the parser has the shape and its tests produce it. Either no disclosure in the
  corpus is abbreviated, or the parser no longer recognises one. Counts only; worth a look by an E31
  task.
* **A cited sibling of an uncited representative** (E39, after the pilot's feedback). 141 of the 334
  uncited, short documents have other occurrences, and one may carry a cite. If students miss such a
  card, preferring a cited member in the representative order would keep it, at the cost of reading
  every member's card and changing the documented order.
* **The build's second read** (E39), if the extra ~100 s matters: the writer could compact
  `doc_id`s at `finish`.
* **A `tub index compare` command** (E39): the runbook's first block compares a build with the
  published index in an inline script. A command could print the same, and the shrink guard would
  read the same numbers.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-22

**Notes:**

1. **Rule C is implemented as ruled.** The second read's own tallies (openev 70 and 17, hspf26 297
   and 96) match the counts exactly, which is the check that matters. The red skeleton, the 12
   mutants caught by plain failures, and the two fixture clusters that pin "judged on the
   representative" are what I asked for. The coach's example is the CITE_ONLY document, and rule C
   removes it.
2. **Deviations accepted.** The CLI, runbook and guide files were named by the ruling. Taking the
   counts yourself, read-only and in seconds, was within working agreement 2.
3. **Decisions accepted, including the two reads.** About 100 s on a weekly build of about 205 s
   costs nothing on the Mac. I am recording the new build time for the E40 design task (e40-t01),
   which sizes the cloud run, rather than filing the doc_id compaction now.
4. **The affected set.** Your alarm stopped it at 115 s with one failure showing, and the narrower
   run then found the "3.9%" false positive. If the PR's `ci` shows any other failure, stop and
   bring it to me before merging. The false positive itself (a percentage read as a Python
   version) goes into v1-e01-t31's brief, which is about exactly that kind of check.
5. **The operator blocks are accepted as written.** They have the dry run and the publish as two
   blocks, the override and running-pull guards, an empty-store check and a check against the
   current index, a plain publish, and a refusal that comes back to me. The order is: merge, both
   blocks from this worktree, then `scripts/task finish`, then reinstall the agent before
   Wednesday 2026-10-28.
6. **Follow-up work:**
   * No ABBREVIATED card: already in v1-e31-t31's brief (PM batch 2026-10-22d).
   * A cited sibling of an uncited representative: held until the pilot's feedback, as you
     suggest. Nothing is filed.
   * The second read's compaction: recorded for e40-t01, not filed.
   * `tub index compare`: declined for now. The shrink guard and the runbook's block cover it.

**PR:** open it with `--partial`. ac3 is the operator's after the merge, and the Goal stays
`InProgress` until then. v1-e39-t13 depends on this task. The PM records ac3 from the two blocks'
output and sets the Goal `Succeeded` in the next PM batch, which makes t13 ready. If anything comes
out differently, stop and ask for another review.
