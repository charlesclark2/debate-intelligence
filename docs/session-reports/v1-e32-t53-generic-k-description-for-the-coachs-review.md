# Session report: v1-e32-t53-generic-k-description-for-the-coachs-review

| | |
|---|---|
| Task | `v1-e32-t53-generic-k-description-for-the-coachs-review` — generic-k's description, rewritten as v1-e32-t49 proposed, for the coach's review |
| Spec | [`plan_specs/v1/e32-argument-landscape/t53-generic-k-description-for-the-coachs-review.yaml`](../../plan_specs/v1/e32-argument-landscape/t53-generic-k-description-for-the-coachs-review.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t53-generic-k-description-for-the-coachs-review` |
| Session status | COMPLETE |

## Summary

The coach reviewed `generic-k`'s description on 2026-11-08 (ac1's operator part) and gave his own wording
in place of `v1-e32-t49`'s proposal. `generic.yaml` now describes `generic-k` as "A card clearly related to a
kritik that does not fall under any of the named kritiks in this list.", and nothing else in the entry
changed. A description is a patch, so generic moves 1.2.0 → 1.2.1 and `policy-2026-27-nhi` moves 1.5.0 → 1.5.1,
in its file and in `topics.yaml`. Each file's changelog names the review. The model stage's request
carries the taxonomy version and every description, so its cassette key moved by itself. A new test shows
that neither a 1.5.0 recording nor one with the old description has the committed taxonomy's key. The
decision is recorded under prompt 1.3.1's section of `docs/data/landscape-model-evaluation.md`. One thing to
look at first: the bump means the next report on hspolicy26 re-places all 140,055 cached results on this
Mac. That is deterministic and calls no model (Decisions, item 3). The Goal is `Succeeded`.

## The coach's decision (2026-11-08), as given

* `generic-k` is "a card which is clearly related to a K, but doesn't fall under the purview of one of the
  established K's that are part of the case list."
* He did not approve `v1-e32-t49`'s proposed wording ("...such as a critique of the affirmative's
  ontology"). His own wording replaces it.
* He asked for periodic reviews, by him, of the cards placed under `generic-k`, to find kritiks the
  landscape has not yet recorded. The PM files that as a mode of `v1-e32-t52`, not in this task. The
  design question is under Follow-up work.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `generic-k-description-for-the-coachs-rev` | Done | The description, both version bumps with changelog entries, the pinned text, the re-key test, and the record in the evaluation doc. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the coach's decision is recorded (operator), an approved description is in generic.yaml with the versions bumped, and the config tests pass | PASS | The decision (the coach, 2026-11-08, relayed by the PM) is recorded above and in `docs/data/landscape-model-evaluation.md` under "The coach's decision on `generic-k`'s description". `git diff origin/dev...HEAD -- config/landscape` → generic-k's description line changed and nothing else in the entry; `taxonomy_version` 1.2.0 → 1.2.1 (generic.yaml), 1.5.0 → 1.5.1 (the NHI file and `topics.yaml`), and a changelog entry in each. `scripts/hard_stop.py 115 .venv/bin/python -m pytest -n 0 -q tests/config/test_landscape_taxonomies.py tests/config/test_landscape_released_ids.py packages/debate_core/tests/arguments/landscape/test_generic_k_description_rekeys.py packages/debate_core/tests/arguments/landscape/test_coach_review_positions.py` → `108 passed` |
| Node: generic-k description tests pass (`uv run pytest tests/config/test_landscape_taxonomies.py`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run pytest -p no:warnings tests/config/test_landscape_taxonomies.py` → `59 passed in 6.45s` |

### The new checks, shown failing for their reason

Each check was run against a planted break on the committed tree, and the tree was restored with
`git checkout HEAD --` afterwards (`git status` clean):

| Planted break | Failed | Why |
|---|---|---|
| The old description back in `generic.yaml` (versions left bumped) | 3: `test_generic_k_is_described_in_the_coachs_own_words`, `test_the_requests_carry_the_new_version_and_the_coachs_description`, `test_no_key_from_before_the_review_is_the_committed_taxonomys[the description alone]` | `'A kritik car...in this list.' == 'A card clear...in this list.'`; the coach's text not in the request's positions; the "before" taxonomy equal to the committed one |
| `policy-2026-27-nhi` back at 1.5.0 in its file and `topics.yaml` | 3: `test_the_requests_carry_the_new_version_and_the_coachs_description`, `test_no_key_from_before_the_review_is_the_committed_taxonomys[the version alone]`, `test_the_three_positions_are_active_with_their_kind_side_and_a_description` | `assert '1.5.0' == '1.5.1'` (twice); the "before" taxonomy equal to the committed one |

### Before the report

| Check | Result |
|---|---|
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run` | **Not finished in 115 s:** 181 files, 5,310 items on 11 workers. 1,424 passed and none failed before the stop. The machine was at load 11 on 11 cores from other sessions. Under the PM's rule (over about 2 minutes, leave it to the pull request's CI, no hand-off), the rest runs on the PR. |
| `uv run ruff format --check .` | `2028 files already formatted` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run pyright tests/config packages/debate_core/tests/arguments/landscape` (every changed Python file is in these) | `0 errors, 0 warnings, 0 informations`. `pyright packages/debate_core tests/config` did not finish under the 115 s stop at this load; this task changes no source module. |
| `uv run lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `uv run python scripts/check_command_blocks.py` | OK: no comments in 696 shell code blocks in 254 Markdown files |
| `uv run scripts/validate_specs.py` | `OK: 655 files, 41 epics, 592 tasks, 22 releases` |

## Files changed

* `config/landscape/taxonomies/generic.yaml`: the coach's description for `generic-k`, version 1.2.1, and
  its changelog entry.
* `config/landscape/taxonomies/policy-2026-27-nhi.yaml` and `config/landscape/topics.yaml`: 1.5.1, as the
  guide's rule for a `generic.yaml` edit says, with the changelog entry.
* `tests/config/test_landscape_taxonomies.py`: `generic-k`'s description pinned to the coach's exact text.
  The test finds `generic-k` by reading the taxonomy directory, so the module still names no topic file.
* `packages/debate_core/tests/arguments/landscape/test_generic_k_description_rekeys.py` (new): the model
  stage's requests under the committed taxonomy carry 1.5.1 and the coach's text. Its key differs from the
  key under 1.5.0 with the old description, and from the key with either change alone.
* `packages/debate_core/tests/arguments/landscape/test_coach_review_positions.py`: its version pin moves to 1.5.1.
* `docs/data/landscape-model-evaluation.md`: the decision, the new description, what `generic-k` scored
  before it, the coach's request, and what happens to the recordings and the cache.
* The task spec (phase) and this report.

## Deviations from the spec

None. The spec's title and description expected `v1-e32-t49`'s wording or the coach's own. The coach gave
his own, so his is in `generic.yaml`, exactly as the PM wrote it in the start prompt.

## Decisions and assumptions

1. **A patch, in two files.** The taxonomy guide's table makes a description a patch. Its rule for
   `generic.yaml` edits moves every topic of the events the edited positions name. `generic-k` names
   `POLICY` only, so `policy-2026-27-nhi` moves to 1.5.1. The LD topic stays at 1.0.0.
2. **The cassettes re-key by themselves.** `prompt_variables` puts `taxonomy_version` and every position's
   description into the variables, and `fixture_key` covers the variables. So nothing had to be edited for
   the re-key, and no committed cassette is keyed on the real NHI taxonomy. The new test pins the effect.
   The kept recordings of the 47-card sample on the operator's Mac (prompts 1.1.0 to 1.3.1, both routes)
   were all made at taxonomy 1.5.0 or earlier. None of them replays from a checkout with this change. A
   `landscape evaluate` replay of one now needs a checkout before this merge (dev at `10aebe0`, say);
   otherwise it is a `MissingFixtureError`, never a model call. `v1-e32-t50`'s held-out sample will be
   recorded under 1.5.1.
3. **The landscape cache, counted.** The classification cache keys on the taxonomy version, so the bump
   reaches **one cache**: `hspolicy26.jsonl` in this Mac's dev data directory, written 2026-11-05. I counted
   it by key fields only, with no text read. It holds **140,055 results, all `policy-2026-27-nhi` 1.5.0, all
   deterministic** (`prompt_version: none`), so no model answer is cached. The next `landscape report`
   (or `--publish`) on hspolicy26 finds every one a miss. It re-places each card with stage one, drops the
   1.5.0 entries and writes 1.5.1 ones. Stage one never reads a description (only `model_stage.py` does),
   so the placements and counts come out the same. `--model-mode none` is the default, and `live` is
   refused by the data-use gate, so **nothing in it calls a model**. The report's `Taxonomy version` row
   then reads 1.5.1. Once that report is first published, the guide's step applies:
   `release_landscape_taxonomy.py --version 1.5.1`, committed in the next batch. That is the existing
   process, not new work.
4. **What scored before the description, worded carefully.** The PM's note says no route placed
   `generic-k` above the threshold before 1.3.1. The evaluation doc records one exception under 1.3.0: its
   one generic answer above the threshold, row 26, answered `at:generic-k` (an `at:cap-k` card) and was
   wrong. So the record says no recording placed a card **as reading** `generic-k` above the threshold
   before 1.3.1, and names row 26. Row 60 under 1.3.1 is as the PM gave it.
5. **The review's date.** The record uses 2026-11-08 as the PM gave it. This session's clock read
   2026-11-07, so please check the date is not a typo.
6. **The released-id lock was not touched.** It holds NHI 1.1.0 and 1.2.0 only. An edit at an unreleased
   version needs no lock change, and this task writes none.
7. **No name.** The changed text holds ids, versions, row numbers, the caselist slug and the coach's words.
   It holds no school, team code or debater name.

## Operator follow-ups

None.

## Follow-up work

**For the PM: a `generic-k` review mode in `v1-e32-t52`** (the coach's request, filed there by the PM;
not built here).

* **How it finds its cards.** It reads the landscape's placements of `generic-k` on a topic, from the
  caselist's classification cache. It keeps those placed since the last `generic-k` review, which means the
  item fingerprints the last review's decisions file does not hold. It groups them by tag, as the
  normalizer writes it. Each group shows the cards' heading paths, the number of files and teams, and the
  placement's method and role, in the operator's terminal only. Today's count, for scale: the hspolicy26
  cache holds **177** `generic-k` results above the 0.6 threshold. 173 are by the coach's overrides (146
  reads, 27 answers) and 4 inherited from a heading. None is a model placement, because model runs are
  held. Once the model stage runs, its `generic-k` answers join the list with their confidence.
* **What its decision writes.** One decision per group, into the review's decisions file on the
  operator's Mac. The file holds the review's date, the topic, the taxonomy version and snapshot it read,
  and each reviewed fingerprint as a digest, with no text. The apply step then writes one of three things:
  1. **A new named kritik:** a new position in `generic.yaml` (kind `k`, side `neg`, events `[POLICY]`)
     with the coach's label and description. Its aliases are the group's headings that two or more teams
     use. It is a minor bump of generic and of the topic, so the cards move off `generic-k`.
  2. **An existing named kritik:** an alias on that position (minor bump), or an override in
     `overrides/<topic>.yaml` when one heading should move and not the alias.
  3. **Stays generic:** the fingerprints are recorded as reviewed, so the next review skips them. The
     config does not change and no version bump is needed.
* **One question for the PM:** should "since the last review" be by fingerprint (above) or by snapshot
  date? Fingerprints skip a card the coach has seen even when a later snapshot brings it again. Dates are
  simpler but show it again.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-08

**Notes:**

The PM checked the worktree against `origin/dev` file by file. `generic.yaml` changes only generic-k's
description line, to the coach's exact text; its version goes 1.2.0 → 1.2.1 with a changelog entry. The
NHI taxonomy and `topics.yaml` go 1.5.0 → 1.5.1, with the NHI file's changelog entry. LD's topic stays at
1.0.0. Nothing else in config changed.

1. **ac1 passes.** The coach's decision is recorded as he gave it, the description is pinned by test, and
   the config tests pass (59 on the node's command, 108 with the re-key and review-position tests). Both
   planted breaks fail for their reason.
2. **The re-key needs no code,** because the request carries the version and every description. The new
   test pins that a 1.5.0 recording, or one with the old description, never replays. Recordings at 1.5.0
   replay only from a checkout before this merge, and the report says so.
3. **The cache, counted:** 140,055 deterministic results at 1.5.0 and none from a model, so the next
   hspolicy26 report re-places every card with stage one and calls nothing. The republish after the
   2026-11-11 run does this, so expect its dry run to take the longer first-run time. The
   `release_landscape_taxonomy.py --version 1.5.1` step follows that first publish, in the PM's next batch.
4. **Item 4's careful wording is right.** Row 26 under 1.3.0 placed `at:generic-k` and was wrong. No
   recording placed a card as reading generic-k above the threshold before 1.3.1.
5. **Item 5: the date is right.** The review was 2026-11-08 on the coach's clock; the session's clock
   was in UTC.
6. **The follow-up design is accepted as the basis for the PM's amendment of v1-e32-t52.** On its
   question: by fingerprint. The coach never sees a card he has already ruled on, even when a later
   snapshot brings it again. The decisions file records the snapshot each fingerprint was reviewed at.
7. **Merge:** a plain `scripts/task pr` once `ci` is green. The Goal is `Succeeded`.
