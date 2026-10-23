# Session report: v1-e32-t02-position-classification

| | |
|---|---|
| Task | `v1-e32-t02-position-classification` — Position classification |
| Spec | [`plan_specs/v1/e32-argument-landscape/t02-position-classification.yaml`](../../plan_specs/v1/e32-argument-landscape/t02-position-classification.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t02-position-classification` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

This task builds deterministic position classification as the PM amended it on 2026-10-22, with no
model call. It has four parts:

* the `PositionClassification` contract, with MODEL kept in it for `v1-e32-t07`;
* a matcher over t01's normalizer and name scrub, now shared rather than copied;
* a per-caselist cache;
* a review queue whose coach decisions become `OVERRIDE` rules in `config/landscape/overrides/<topic id>.yaml`.

`PositionClassificationService` puts these together, and `scripts/classify_landscape_positions.py`
runs them until `v1-e32-t05` has its command. Every criterion this task still owns passes, and the
Goal is **Succeeded**: ac3 and ac6 moved to t07.

**Look first at the real-store measurement**
([below](#the-real-store-hspolicy26-through-2026-10-20)). Headings place **48.1%** of hspolicy26's
126,681 cards, which is under the PM's ~60% line. The 20 largest unplaced headings are block labels
(`solvency`, `framing`, `adv`, `turn`, `link`...) that no alias should claim. And 15,750 cards (12.4%)
sit under no heading that survives normalization. More aliases will not lift this much. Question 1
of the [PM block](#questions-for-the-pm) asks what to do before t05's first run.

**Then look at Deviations 1 and 2.** The zero-model-calls half of ac1 is met by construction, and
the cache key has two more parts than the spec names.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| classification-contract | Done | `domain/landscape_classification.py`: `PositionClassification`, `ClassificationResult`, `ClassificationMethod`, `PositionRole`, `ItemKind`; `classification_schema(taxonomy)` (a per-version model with `position_id` a `Literal` of the active ids), `checked_against`; `OverrideRules`. Red run against a refuse-nothing skeleton: 25 failed, 24 passed |
| deterministic-matcher | Done | `arguments/landscape/matcher.py`, `arguments/landscape/source_headings.py` (t01's reading, moved, not copied), `tests/fixtures/landscape/labeled_items.yaml`. Red run: 32 failed, 14 passed |
| cache-and-review-queue | Done | `application/ports/classification_store.py`, `integrations/landscape/classification_store.py`, `arguments/landscape/review_queue.py`, overrides in the taxonomy port and YAML adapter, `application/position_classification.py`, `scripts/classify_landscape_positions.py`. Red run: service 17 failed / 8 passed, script 3 / 5 |
| quality-gates | Done | pyright 0 errors, lint-imports 16 kept |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: on the synthetic labeled set (at least 20 items per format), the deterministic stage reaches 100% on items carrying an alias, AT:/A2 headings give ANSWERS, and no model call is made | PASS | `test_matcher.py` → 46 passed. The set holds 80 hand-labeled cards: Policy 31 (25 carrying an alias), LD 24 (21), PF 25 (23). Every one of the 80 is placed as labeled, the ones carrying no alias included, and every method shows up. `test_answer_headings_give_answers_and_only_they_do` passes for all three formats. Zero model calls: see Deviation 1 |
| ac2: each classification records item id, position or null, role, confidence 0–1, rationale ≤ 280, method (ALIAS, TAG_KEYWORD, INHERITED, OVERRIDE, MODEL), taxonomy_version, and for MODEL results prompt_id, prompt_version and model_id | PASS | `test_landscape_classification.py` → 49 passed: the exact field set, the five methods, MODEL needing all three prompt fields, deterministic results carrying none and `prompt_version` `none`, 280 accepted and 281 refused, and ids held to the taxonomy's active ids |
| ac3: rationale-echo and unknown-id checks on model results | MOVED to `v1-e32-t07` (PM amendment 2026-10-22) | Not built. Results from any stage go through `checked_against`, so t07's unknown-id half is already enforced at the contract |
| ac4: no match, or confidence under the threshold (default 0.6), goes to the review queue with heading path and candidate positions; a coach decision file adds an OVERRIDE rule, so the heading is classified deterministically next run | PASS | `test_position_classification.py -k "cache or review"` → 26 passed. Queue rows were counted by hand. The threshold test runs at 0.95, 0.6 and 0.4. Decisions become overrides, and the next run places those cards by OVERRIDE (and INHERITED below them) with an empty queue. The script test does the same end to end. See Deviation 5 for "heading path" |
| ac5: a second run over an unchanged snapshot reclassifies nothing (100% hits), and a taxonomy_version bump (or, from t07, a prompt version bump) invalidates only the affected results | PASS | Synthetic: second run 17/17 hits and `place` called 0 times. The cache file is byte-identical after it. A version bump on one LD topic misses its 5 keys and none of the other topic's. A coach decision misses only the 2 keys under its heading. A MODEL entry under prompt `1.0.0` is kept. Real store: second run 107,203 / 107,203 hits (100.0%), 0 placed, cache unchanged |
| ac6: replay evaluation on a coach-labeled 60-item set | MOVED to `v1-e32-t07` (PM amendment 2026-10-22) | Not built |
| classification-contract: contract exists, contains `class PositionClassification` | PASS | `grep -c "class PositionClassification" packages/debate_core/src/debate_core/domain/landscape_classification.py` → 1 |
| classification-contract: contract schema tests pass | PASS | 49 passed (above) |
| deterministic-matcher: matcher tests pass | PASS | 46 passed (above) |
| cache-and-review-queue: `test_position_classification.py -k "cache or review"` passes | PASS | 26 passed (all 26 tests in the file match) |
| quality-gates: `uv run pyright packages/debate_core` | PASS | 0 errors, 0 warnings, 0 informations |
| quality-gates: `uv run lint-imports` | PASS | Contracts: 16 kept, 0 broken |

I ran each pytest command as `.venv/bin/python -m pytest <file>` under `perl -e 'alarm 100'`, which
puts the time limit on the interpreter (working agreement 10).

### Checks shown failing for their reason

* **Red runs against skeletons**, each run alone and restored from git:
  * contract with no validators: 25 failed, 24 passed. The 24 are positive cases, plus refusals made
    by field types alone (extra field, rationale length, confidence range, enums, semver, digest);
  * matcher whose `place` places nothing: 32 failed, 14 passed. The 14 are the refusal and unplaced
    cases, item reading, fingerprints and the router check;
  * queue and decisions as no-ops: service tests 17 failed / 8 passed, script tests 3 / 5.
* **20 mutants of the inheritance, override, role, tag-keyword and cache rules.** Each ran in a fresh
  process with bytecode writing off and `__pycache__` cleared, which guards against the stale-bytecode
  near miss in t01's report. Each file was restored byte for byte. No Hypothesis is used. Every mutant
  was caught:

  | Mutant | Failed |
  |---|---|
  | No inheritance (only the heading directly over the item) | 31 |
  | The farthest placed heading wins | 3 |
  | Inherited reported as a direct match | 11 |
  | Alias read before override | 1 |
  | A no-position override stops the walk | 2 |
  | Decided when *any* heading is ruled no position | 1 |
  | Role read from the placing heading only | 2 |
  | Role read from every heading on the path | 4 |
  | An override's retired id not resolved | 1 |
  | A retired alias with nowhere to go still places | 4 |
  | Two children named: the first wins | 2 |
  | Tag keywords alone: ancestors kept | 1 |
  | Inherited as sure as an alias | 4 |
  | Undecided headings include decided ones | 1, **after a new test**: it first survived (70 passed), so `test_review_a_heading_the_coach_ruled_on_is_not_queued_again` was added |
  | Fingerprint ignores the answer flag | 6 |
  | Cache key ignores the override digest | 2 |
  | A cached hit not checked against the taxonomy | 1 |
  | A bump drops every other topic's results | 1 |
  | A hit is placed again anyway | 3 |
  | Cache key ignores the taxonomy version | 1 |

  Two of the twenty first targeted lines that `ruff format` had reflowed, so they did not apply. They
  were re-aimed and run, and appear above as caught.
* **Config plants** into `config/landscape/overrides/policy-2026-27-nhi.yaml`. The directory was
  removed after each:
  * `fed key qx` and `sample high fed key` fail the personal-data test;
  * `spending da shell` fails the normalizer fixed-point test;
  * an override naming `medicaid-da` fails the load;
  * a stray CSV in `overrides/` fails the load and the directory test.
* **The zero-router check:** a planted `ModelRouter` import in `matcher.py` fails
  `test_no_module_that_classifies_imports_a_model_router`.
* **The real store found a flaw the synthetic tests had not.** On the first run, the queue's
  candidates were pooled over every heading on an item's path, so `solvency` was offered T and
  single-payer positions. A row now offers its own heading's candidates. A test pins this
  (`test_review_a_rows_candidates_are_its_own_headings_not_its_neighbours`), and the second run's
  top rows show `none` for block labels.

### The real store (hspolicy26, through 2026-10-20)

All runs were read-only for the stores. The guards were checked first: no `DEBATE_*` variable set
and no caselist pull running. Each run had a 115 s limit on the interpreter. A run writes only the
cache and the queue under `~/.debate-research/dev/landscape/`, which no sync reads. "The newest
snapshot" is read as the store as it stood at the newest weekly snapshot, 2026-10-20: every on-topic
source disclosed through that date. That is what a report counts, not the one week's window
(Decision 9). Counts only.

| Count | Value |
|---|---|
| Parser version; sources on the topic | `2026.10.20-docx-6`; 3,825 of 3,869 entries (3,825 parsed) |
| Sections; cards | 48,094; 126,681 |
| Cards placed by **ALIAS** | 39,196 (30.9%) |
| Cards placed by **INHERITED** | 21,791 (17.2%) |
| Cards placed by **TAG_KEYWORD** | 0 (no tag keywords exist yet) |
| Cards placed by **OVERRIDE** | 0 (no decisions yet) |
| Cards **unplaced** | 65,694 (**51.9%**); cards counted 60,987 (48.1%), 0 below the threshold |
| Review queue | 92,070 items (65,694 cards) under 6,118 headings; **1,433 rows** written; 4,685 headings left out as used by one team; 22,377 items under no heading |
| First run | 69.8 s wall (load average 13 at the start); 107,203 distinct keys, all placed, cache written (47 MB) |
| Second run | 37.5 s wall; **107,203 hits of 107,203 (100.0%)**, 0 placed, cache unchanged |

**Placement is under 60%.** The 20 largest unplaced headings by team count are below, from the second
run, which has the corrected candidates. I checked each by hand: all 20 are debate vocabulary, and
none names a school, team or person.

| Normalized heading | Teams | Documents | Cards | Candidates |
|---|---|---|---|---|
| `solvency` | 180 | 438 | 1,753 | none |
| `framing` | 139 | 228 | 1,277 | none |
| `adv` | 90 | 216 | 1,784 | none |
| `turn` | 75 | 146 | 521 | none |
| `advantage` | 69 | 98 | 1,200 | none |
| `presumption` | 67 | 106 | 217 | none |
| `link` | 62 | 139 | 594 | none |
| `full text` | 61 | 194 | 3,033 | none |
| `t` | 61 | 123 | 251 | none |
| `impact` | 57 | 102 | 319 | none |
| `u` | 55 | 110 | 389 | none |
| `k` | 49 | 101 | 417 | none |
| `pharma` | 48 | 90 | 682 | pharma-advantage, pharma-da |
| `framework` | 44 | 70 | 185 | framework-t |
| `extra` | 40 | 77 | 196 | none |
| `cp` | 37 | 94 | 379 | none |
| `da` | 36 | 97 | 802 | none |
| `fiat good` | 36 | 54 | 79 | fifty-state-fiat-bad |
| `topicality` | 29 | 61 | 165 | nhi-t |
| `uniqueness` | 29 | 39 | 157 | none |

**Why the rest is unplaced.** A third read-only pass (30.8 s, counts only) sorted the 65,694 unplaced
cards by cause:

| Cause | Cards |
|---|---|
| Under no heading that survives normalization (`1NC`, `Case`, `Off`, a team's own name, or no path at all) | 15,750 |
| Under at least one heading the queue lists (two or more teams) | 39,089 |
| Only under headings one team used | 10,855 |

Two further counts:

* By the number of non-empty headings over them, the unplaced cards split 0: 15,750; 1: 23,453;
  2: 19,600; 3: 6,891.
* 45,035 unplaced cards are in a document where some other card is placed, and 1,117 of the 3,825
  documents have no placed card at all.

So the coach's decisions can reach at most the 39,089 cards under a queued heading. Many of those
headings are block labels whose right decision is `none`, and `none` places nothing. Most of what
remains needs a signal headings do not carry (question 1).

### Before the report (working agreement 10)

* `uv run scripts/affected_tests.py` listed 54 files. I ran them with CI's markers:
  `.venv/bin/python -m pytest -n auto -m "not slow and not live" -p no:randomly <files>` under a 115 s
  limit → **2,282 passed, 2 skipped in 54.05 s**. The 2 skips are the overrides-file checks, which
  have no file to check until the coach's first decision. They were shown failing on planted files
  above.
* `uv run --frozen ruff format --check .` → 1171 files already formatted.
* `uv run --frozen ruff check .` → all checks passed.
* `uv run --frozen pyright packages/debate_core` → 0 errors.
* `uv run --frozen lint-imports` → 16 kept, 0 broken.
* `scripts/check_thin_handlers.py` → 47 handlers within 25 statements.
* `scripts/check_command_blocks.py` → OK.
* `scripts/check_links.py` → OK.
* `scripts/docs_index.py --check-descriptions` → OK.
* `uv run scripts/validate_specs.py` → OK, 430 files.
* No `pyproject.toml`, `uv.lock`, conftest or pytest-plugin change, so no whole-selection hand-off.

## Files changed

* **`domain/landscape_classification.py`** (new): the contract and `OverrideRules`.
* **`arguments/landscape/`**:
  * `source_headings.py` (new): t01's per-source heading reading (open-tag drop, three-level cut,
    own-name and caselist-school scrub), moved out of `seeding.py` in a commit of its own. t01's
    tests were unchanged by it, normalizer 157 and seeding 49.
  * `matcher.py`, `review_queue.py` (new).
  * `seeding.py`: uses the shared reading, and `SeedCard` gains `first_element_index`.
* **`application/`**:
  * `position_classification.py` (new): the service.
  * `ports/classification_store.py` (new).
  * `ports/taxonomy_repository.py`: gains `overrides(topic_id)`.
  * `landscape_seeding.py`: the reader carries each card's first paragraph and takes a `through`
    date, and `SeedReading` gains `newest_disclosure`.
* **`integrations/landscape/`**:
  * `classification_store.py` (new): the cache and queue files.
  * `yaml_taxonomy_repository.py`: reads and checks `overrides/*.yaml`, and renders an overrides file.
* **`testing/landscape_store.py`**: planted cards carry provenance paragraphs.
* **Tests**:
  * under `packages/debate_core/tests`: `domain/test_landscape_classification.py`,
    `arguments/landscape/test_matcher.py`, `application/test_position_classification.py`,
    `integrations/landscape/test_classification_store.py`, `integrations/landscape/test_override_files.py`;
  * `tests/fixtures/landscape/labeled_items.yaml`;
  * `tests/scripts/test_classify_landscape_positions.py`;
  * `tests/config/test_landscape_taxonomies.py`: `overrides/` is allowed, and its headings get the
    alias checks.
* **`scripts/classify_landscape_positions.py`** (new): `classify` and `apply-decisions`.
* **`docs/guides/landscape-taxonomy.md`**: how a card is placed, and the review queue with the
  coach's decisions.
* **The spec**: phase Succeeded only.

## Deviations from the spec

1. **ac1's "the fake router records zero model calls" is met by construction.** As amended, the
   classification path has no `ModelRouter` to inject, fake or real. The test therefore checks that
   the three modules that classify (matcher, review queue, service) import no model router, and it
   fails on a planted import. Wiring an unused router into the service only to count its calls would
   test nothing. `v1-e32-t07` gets the fake-router assertion when it adds a router.
2. **The cache key has two parts beyond (item fingerprint, taxonomy_version, prompt version).**
   * The **topic id**: an LD caselist holds two topics a season, both can be `1.0.0`, and the same
     heading can name different positions in each. The test shows it.
   * A **digest of the coach's decisions on the item's own headings**. Without it, a decision would
     not reach a cached item, and ac4's "classified deterministically next run" would fail. Because
     the digest covers only the item's headings, a decision misses only the items under that heading,
     which matters for t07's MODEL entries.

   The spec's text should name both. This is question 4.
3. **Files outside `constraints.packages`:**
   * `scripts/classify_landscape_positions.py` and `tests/scripts/`: the operator's entry until t05,
     as t01's seeding script was;
   * `tests/config/`: the PM's ruling (4) puts the personal-data check over the overrides file;
   * `docs/guides/landscape-taxonomy.md`: the coach's decisions workflow;
   * `debate_core.testing`: planted cards carry paragraphs;
   * `config/landscape/overrides/`: allowed, with no file committed.

   No prompt is added under `prompts/landscape`, since the model stage is t07's. This is question 6.
4. **t01's code changed:** the heading reading moved to `source_headings.py`, `SeedCard` gained a
   field, and the reader gained `through`. Seeding's behaviour is unchanged, and the refactor is its
   own commit. The matcher reuses t01's `SeedSource`/`SeedCard`/`SeedTeam` names rather than renaming
   them across t01's tests.
5. **"Its heading path" in ac4 is the normalized heading of each row.** The PM's brief says the queue
   CSV "holds normalized headings with counts and candidate positions only". A decision is taken per
   normalized heading, so the queue has one row per (heading, answer) for every undecided heading over
   a queued item, rather than one row per path. A path would multiply rows, and its outer headings can
   be a single team's.
6. **Sections are reconstructed.** The store holds no sections (t01 Deviation 2), so a section item
   is a distinct heading path the cards record. Its id is a digest of the path as the file wrote it,
   so the id holds no heading text.

## Decisions and assumptions

1. **Method by where the placing heading is.** A match on the heading directly over the item is
   ALIAS or OVERRIDE (confidence 1). A match further up is INHERITED (0.9). This gives the PM's
   per-method card counts their meaning: with every card INHERITED from a block, "cards placed by
   ALIAS" would always be 0. A heading that normalizes to nothing (`1NC`) is skipped, not counted as
   a level.
2. **Role.** ANSWERS when the placing heading, or any heading above it, is an answer, so `AT: DAs` >
   `Spending DA` answers. An answer heading *below* the placing one (`Spending DA` > `AT: Link Turn`)
   reads the position.
3. **A decision of `none`** marks a block label. Such a heading is passed over like an unmatched one,
   and it stops coming back to the queue. A card under nothing but `none` headings is decided:
   OVERRIDE with no position, confidence 1, not queued.
4. **TAG_KEYWORD alone is 0.5**, under the 0.6 threshold. This reconciles the spec's "fall back to
   tag keywords" with the PM's "never a guessed position": such a card is recorded with its
   candidate, queued and left out of counts. Under a placed parent, a keyword refines to the one child
   it names at 0.9, and two children named leave the card with the parent (ruling 4). The confidences
   are fixed per rule, not measured.
5. **A retired alias counts under its `merged_into` end. One retired with nowhere to go places
   nothing.** Overrides resolve the same way, and one naming a retired-to-nothing id is refused at
   load.
6. **A rationale never holds the item's own text.** It names the rule and the alias, keyword or
   override heading that matched, all committed and checked text. A test checks this over the
   labeled set, and the real cache file holds no heading or tag.
7. **A cached hit is checked against the taxonomy before use.** So an edit made without a version bump
   cannot bring back an id that is gone. A save keeps every other topic's entries and MODEL entries,
   and drops this topic's entries under other versions.
8. **The fingerprint covers what placement reads:** the normalized headings with their answer flags,
   and the tag's words. Two cards alike in those share one cached result (107,203 keys for 174,775
   items). A heading whose scrubbed text changes because a new school joined the caselist gets a new
   key, and is placed again.
9. **"The newest snapshot"** means the store through 2026-10-20 (`through`), the latest weekly
   manifest. Snapshots are windows (`v1-e30-t17`), and a report counts the accumulated store.
10. **The queue leaves out a heading fewer than two teams used**, as seeding does, and counts it. At
    one team, hspolicy26's queue would grow from 1,433 to 6,118 rows, mostly single-team headings
    that can point at the team (question 2).
11. **Tag words are matched by a plain lowercase word split, not by the heading normalizer.** A tag is
    a claim, and the normalizer's answer-marker and suffix rules would cut it. Headings use only t01's
    normalizer.

## Operator follow-ups

Nothing is handed over. The before-report set ran within the limit, and the pull request's `ci` check
runs the whole selection. When the PM accepts, open the pull request without `--partial`:

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t02-position-classification
```

```bash
scripts/task pr v1-e32-t02-position-classification
```

## Follow-up work

* **The report header records the overrides** (`v1-e32-t03`). A decision moves counts without a
  `taxonomy_version` bump, so a report should name the overrides digest or the file's commit beside
  the version (question 3).
* **MODEL keys add what the model reads** (`v1-e32-t07`). The deterministic fingerprint covers
  headings and tag words only. A MODEL result also depends on the short cite and the excerpt, so t07
  should fold those into its own fingerprint, under its prompt version.
* **Two normalizer variants** (E32, t01's normalizer): `Adv 1 Costs` normalizes to `adv 1 costs` and
  `Advantage One: Costs` to `advantage one costs`, so neither finds the costs-advantage aliases.
  `Advantage 1 - Costs` and `Adv 1: Costs` already do. Not changed here, as the brief says to use
  t01's normalizer as it is.
* **A document-level signal** (PM to place, t07 or a new task). 45,035 unplaced cards sit in a
  document where another card is placed, and 1,117 documents have no placed card. Any rule using
  that is a new kind of inference, closer to a guess than the matcher's.
* **Heading level from sections** (t01's follow-up, filed only "if t02's matcher shows the unknown
  levels cost it"). It does not: the matcher matches at any level and needs none.
* **Cache size.** hspolicy26's cache is 47 MB for 107,203 entries. That is fine locally. If E34 ever
  syncs it, compact the repeated rationale strings first.

## Questions for the PM

One block, paste-ready:

```text
v1-e32-t02 questions (session, 2026-10-23)

1. Placement is 48.1% of hspolicy26's cards (under the ~60% line). The 20 largest
   unplaced headings are block labels (solvency, framing, adv, turn, link, ...);
   15,750 cards (12.4%) sit under no surviving heading; 1,117 of 3,825 documents
   have no placed card. What before t05's first run?
   (a) Ship t03/t05 with the honest Unclassified share; the coach takes one pass
       over the queue's top ~50 rows, writing `none` for block labels and ids for
       topic headings (pharma, fiat good, topicality, framework).
   (b) As (a), plus a new task for a document-level rule.
   (c) Wait for t07's model stage.
   Recommendation: (a). It costs the coach about 20 minutes and shrinks the queue
   to what matters; the honest share is what the epic asked the first reports to
   show. A document-level rule infers rather than matches; if wanted, it is t07's
   or a new task, not a change here.

2. The review queue leaves out (and counts) headings fewer than two teams used,
   as seeding does. Keep two, or list every heading (1,433 rows become up to 6,118)?
   Recommendation: keep two. Single-team headings are mostly noise and can point
   at a team; the CSV is local either way.

3. Coach decisions move counts without a taxonomy_version bump. Record them how?
   (a) t03's header names the overrides digest beside taxonomy_version.
   (b) apply-decisions also bumps the minor version.
   Recommendation: (a). The cache already keys by the digest, so only the items
   under a decided heading are placed again; a bump would re-place the whole
   topic and churn released versions for every review pass.

4. The cache key adds the topic id and a per-heading override digest to the
   spec's (fingerprint, taxonomy_version, prompt version) (Deviation 2). Amend
   the spec's description to name them?
   Recommendation: yes. Without the topic id, two LD topics at 1.0.0 collide;
   without the digest, ac4 fails for cached items.

5. ac1's zero-model-call half is met structurally: the classifying modules
   import no ModelRouter, and a planted import fails the test (Deviation 1).
   Accept as PASS?
   Recommendation: yes; t07 asserts the fake router's call log once there is
   a router to call.

6. Amend constraints.packages with: scripts (classify_landscape_positions.py),
   tests/scripts, tests/config, docs/guides, debate_core.testing and
   config/landscape (Deviation 3)?
   Recommendation: yes, as you did for t01.

7. A card placed by tag keywords alone is recorded at confidence 0.5 (below the
   0.6 threshold), so it is queued with its candidate and not counted
   (Decision 4). Keep?
   Recommendation: yes; it keeps "never a guessed position" until the coach or
   t07 confirms such cards.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
