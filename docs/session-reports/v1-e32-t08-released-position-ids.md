# Session report: v1-e32-t08-released-position-ids

| | |
|---|---|
| Task | `v1-e32-t08-released-position-ids` — A released position id is never deleted or reused |
| Spec | [`plan_specs/v1/e32-argument-landscape/t08-released-position-ids.yaml`](../../plan_specs/v1/e32-argument-landscape/t08-released-position-ids.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t08-released-position-ids` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The id rule in the coach's guide is now enforced. `config/landscape/released.yaml` is the committed
lock file. For each topic and released version it lists every position id with its kind and side,
and nothing else; it is empty today (`releases: []`). On every pull request,
`tests/config/test_landscape_released_ids.py` checks the committed taxonomy files against it,
naming the file, the id and the rule. `scripts/release_landscape_taxonomy.py --topic --version`
writes the lock from the committed files alone. It refuses a version the file is not at, a version
already in the lock, and a configuration that already breaks a released id. The coach's guide says
what the check refuses and when the operator runs the writer: right after a report under a new
version is first published, which will first be `v1-e32-t05`'s 1.1.0. Every acceptance criterion
passed and the Goal is **Succeeded**. **Look first at** Decisions 1, about generic.yaml's ids, and
PM question 1. Because the lock holds only ids, kinds and sides, it cannot see an alias edit made
at a released version without a bump.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| released-ids | Done | Lock models and rules in `debate_core.domain.landscape_release`; reading, naming and writing in `debate_core.integrations.landscape.released_ids`; the writer script; the check's tests with synthetic fixtures; the guide. Red run against a skeleton that refused nothing: 16 failed, 21 passed. 18 mutants, all caught |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the check refuses, naming the file, the id and the rule: a released id missing; a released id's kind or side changed; positions changed with no taxonomy_version bump; topics.yaml's version not equal to the file's. Each by a synthetic fixture shown failing first | PASS | `tests/config/test_landscape_released_ids.py` → 23 passed. One synthetic fixture each: an id deleted (topic file, and a generic id); a released topic left with no taxonomy; kind changed; side changed (topic file, and generic.yaml); an id added at a released version; a kind change and a deletion at a released version, each refused by both rules; a version below a released one; a `merged_into` naming a retired position (PM's fourth refusal, with a lock and before anything is released); topics.yaml's version unequal to the file's; a missing lock. Each asserts the file path, the id and `Rule (<rule>)`. Red run against the skeleton: 16 failed, 21 passed. Three refusals already held before this task and could not fail a red run: topics.yaml's version (`v1-e32-t01`'s repository rule, which the check loads through), the missing lock, and an unknown topic in the writer. The first two were shown failing by mutation (below) |
| ac2: a retirement (deprecated, or merged_into an existing id) and a new id both pass, with the version bumped | PASS | `test_a_retirement_a_merge_and_a_new_id_pass_with_the_version_bumped`, 4 cases at 1.1.0 over a 1.0.0 lock: retired, merged into an active id, a new id, a rename to a new id (old retired into it, alias moved). Also passing: a label change at the released version itself (PM ruling: renames allowed), an unchanged released version, and any edit with an empty lock |
| ac3: the lock is written by a command the guide documents, from the committed taxonomy files alone, and the guide says when the operator runs it | PASS | `tests/scripts/test_release_landscape_taxonomy.py` → 6 passed. The expected lock texts were written by hand from the fixture (working agreement 6): first release, a second version appended, and three refusals that each leave the file byte-for-byte unchanged, plus an unknown topic. On a scratch copy of today's `config/landscape/`, the writer refused `--version 1.1.0` ("policy-2026-27-nhi is at 1.0.0, not 1.1.0"), wrote 1.0.0 with 73 ids (54 of the topic's own and 19 from generic.yaml) in 0.4 s, refused 1.0.0 a second time, and the check passed on the locked copy. The guide's new section [Released ids and the lock file](../guides/landscape-taxonomy.md#released-ids-and-the-lock-file) gives the command, when to run it (a report under a new version is first published), and the first-publish paragraph for either merge order |
| released-ids node: `uv run pytest tests/config/test_landscape_taxonomies.py` | PASS | 21 passed, 2 skipped (the two override cases skip: there is no overrides file on `dev` yet). `uv run pytest tests/config` → 44 passed, 2 skipped |

### Checks shown failing for their reason

Each mutant was one replacement, matched exactly once, in the committed source. Each was run with
`.venv/bin/python -m pytest -n0 -p no:randomly` over the three new test files under
`perl -e 'alarm 60'`, with a fresh `HYPOTHESIS_STORAGE_DIRECTORY` (agreement 8; no property tests
here). The file was restored from the commit after each run, and the tree was clean afterwards.
18 mutants, all caught:

| Mutant | Caught by |
|---|---|
| a released id missing not reported | 3 tests (deleted id, deleted generic id, writer over a broken configuration) |
| side change ignored / kind change ignored | 2 tests each |
| a released topic left without a taxonomy not reported | `test_a_released_topic_left_without_a_taxonomy_is_refused` |
| a version below a released one not reported | `test_a_version_below_a_released_one_is_refused` |
| a released version never compared with its lock | 2 tests |
| an id added at a released version not reported | `test_a_position_added_at_a_released_version_is_refused` |
| an id deleted, or a kind changed, at a released version not reported by the version rule | `test_a_change_at_a_released_version_is_refused_by_both_rules[deleted]`, `[kind-changed]` |
| a merge into a retired position not reported | 2 tests |
| the writer accepts a version the file is not at | domain test and script test |
| the writer rewrites a released version | domain test and script test |
| the lock accepts a version twice / a release lists an id twice | one domain test each |
| a missing lock read without its own message | `test_a_missing_lock_file_is_refused_not_read_as_empty` (it asserted only the path at first, and reading a missing file raises with the same path, so I pinned the message before running mutants) |
| the writer writes over a configuration that breaks a released id | `test_a_configuration_that_breaks_a_released_id_is_refused` |
| a generic position named under the topic's file | `test_a_released_generic_id_whose_side_changed_is_refused_naming_generic_yaml` |
| topics.yaml's version mismatch accepted (`v1-e32-t01`'s rule, mutated in `yaml_taxonomy_repository.py`) | `test_a_taxonomy_version_unequal_to_topics_yaml_is_refused_naming_the_file` |

### Checks run before this report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` | 105 files. Run as `perl -e 'alarm 115' .venv/bin/python -m pytest -n auto -m "not slow and not live" <the 105>`, which the alarm stopped at 115 s (exit 142). It runs past two minutes, so per agreement 10 it is left to the pull request's `ci`, with no hand-off. No workers were left running |
| The changed test directories and the always-run list: `.venv/bin/python -m pytest -n auto -m "not slow and not live" tests/config packages/debate_core/tests/domain/test_landscape_release.py packages/debate_core/tests/domain/test_landscape_taxonomy.py packages/debate_core/tests/integrations/landscape tests/scripts/test_release_landscape_taxonomy.py tests/scripts/test_classify_landscape_positions.py tests/scripts/test_seed_landscape_taxonomy.py tests/scripts/test_assign_landscape_affs.py tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py` | 673 passed, 2 skipped, 17 s |
| `uv run --frozen ruff format --check .` / `ruff check .` | 1212 files already formatted / All checks passed |
| `uv run --frozen pyright` (CI's: `packages/`) | 0 errors, 19 s |
| `uv run --frozen lint-imports` | 16 kept, 0 broken |
| `uv run --frozen python scripts/check_thin_handlers.py` | OK: 47 handlers within 25 statements |
| `uv run --frozen python scripts/docs_index.py --check-descriptions` / `check_command_blocks.py` | All 44 described / no `#` comments in 372 blocks |
| `uv run scripts/validate_specs.py` | OK: 434 files, 40 epics, 372 tasks, 22 releases |

## Files changed

* `packages/debate_core/src/debate_core/domain/landscape_release.py` (new): the lock models
  (`ReleasedPosition`, `TaxonomyRelease`, `ReleaseLock` with `with_release`), the five rules
  (`ReleaseRule`, `RULE_TEXT`) and `release_findings` / `merged_into_findings`, pure over the lock
  and the merged taxonomies.
* `packages/debate_core/src/debate_core/integrations/landscape/released_ids.py` (new): reads and
  renders `released.yaml`, puts the file name on each finding (the topic's file, generic.yaml, or
  "the topic's file (with generic.yaml merged in)" for an id that is in neither now), and holds
  the writer's logic.
* `.../integrations/landscape/yaml_taxonomy_repository.py`: the private `_read` is now the public
  `read_config_file`, so the lock is read with the same duplicate-key refusal. Rename only.
* `config/landscape/released.yaml` (new): the empty lock, in the writer's form.
* `scripts/release_landscape_taxonomy.py` (new): the writer, a thin argparse wrapper.
* `tests/config/test_landscape_released_ids.py` (new): the check on the committed files, and every
  refusal and pass on synthetic configurations.
* `tests/config/test_landscape_taxonomies.py`: the one edit to `v1-e32-t01`'s test file. Its "nothing
  else in the directory" test allows `released.yaml` by name, and is renamed to say so. Without
  this, the lock fails t01's test. `v1-e32-t05`'s branch does not touch this file.
* `packages/debate_core/tests/domain/test_landscape_release.py` (new), and
  `tests/scripts/test_release_landscape_taxonomy.py` (new).
* `docs/guides/landscape-taxonomy.md`: the lock in the "Where things are" table; "Check your edit"
  now runs `tests/config`; a new section, "Released ids and the lock file", covering what is
  refused and what to do instead, when the operator writes the lock, and the first published report.
* The task spec: phase `Succeeded`.

## Deviations from the spec

1. **No label check.** The spec's description refuses "a released id that now names a different
   position (its label changed past a rename the file records)". The PM's ruling of 2026-10-24 says
   label changes are allowed and the lock holds no label text, so the check compares ids, kinds and
   sides only. The description should be amended to match (PM question 2).
2. **Where the check lives.** Per the PM's ruling it is in a new `tests/config/test_landscape_released_ids.py`.
   But the node's criterion still runs only `tests/config/test_landscape_taxonomies.py`, which
   passes and does not run the new check (PM question 2). One edit to t01's test file was
   unavoidable: its directory test refused the new lock file (Files changed).
3. **topics.yaml's version equal to the file's (ac1)** was already `v1-e32-t01`'s repository rule.
   The check loads the configuration through it rather than repeating it, and a synthetic test
   asserts the refusal names the file. It could not fail a red run, so it was shown failing by
   mutating t01's rule.
4. **"Positions changed with no bump" means ids, kinds and sides.** That is all the lock records,
   by the PM's ruling. An alias or label edit at a released version is not seen (PM question 1).
5. **Three refusals beyond the PM's list**, each small and each tested: a file's version below a
   released one, since "bumped" means forward, and otherwise the writer could lock 1.0.0 after 1.1.0; a
   missing lock file, since a deleted lock would otherwise pass everything; and the writer refusing
   a configuration that already breaks a released id, so a lock never records a break.
6. **Test files outside `constraints.packages`:** `packages/debate_core/tests/domain/` and
   `tests/scripts/`, the test homes of the domain module and the script the spec asks for.

## Decisions and assumptions

1. **A release records the merged taxonomy:** the topic's own positions followed by generic.yaml's
   for its event, retired ones included. That is what a report under the topic's version counted
   against. Deleting a generic id a report named, or changing its side, is refused like a topic id.
   An edit to generic.yaml that changes the topic's ids, kinds or sides must bump the topic's
   version, which is what the guide already says. The PM's rulings name only "each position id with
   its kind and side" per topic and version; this reads generic's ids as part of that list.
2. **A finding names the file to edit.** That is the topic's file, or generic.yaml when the position
   now lives there. For an id that is in neither, it is "the topic's file (with generic.yaml merged
   in)", because the lock does not record which file an id came from (no data beyond id, kind and
   side), and the repository already uses that phrase for merged errors.
3. **The `merged_into` rule runs on every file, lock or not.** It is a property of the file, not of
   a release: a merge points a reader of an earlier report at the position counted now, so it names
   an active one. No committed file has a `merged_into` today.
4. **A change at a released version is reported by each rule it breaks.** A deletion at 1.0.0 is
   both "missing" and "changed without a bump". Each rule is complete on its own, which is what the
   mutants showed.
5. **The writer reads the working tree.** "Committed" is read as "the files in the checkout". The
   guide asks for a worktree up to date with `dev`, and the version equality guards against a late
   lock. I did not add a git check, so the writer needs no git and its tests need no repository.

## Operator follow-ups

None for this branch. The lock's first real write is `v1-e32-t05`'s first-publish step. Whichever of
t05 and t08 merges second adds it to t05's run instructions, as the guide says. The command, run in
a worktree up to date with `dev` right after the publish, with the version the report shows:

```bash
uv run python scripts/release_landscape_taxonomy.py --topic policy-2026-27-nhi --version 1.1.0
```

Success: `Released policy-2026-27-nhi 1.1.0: N position ids written to ...` with N above zero
(today's 1.0.0 gave 73 on a scratch copy; t05's branch adds five positions). Then `uv run pytest tests/config`
passes, and `git diff config/landscape/released.yaml` shows one release added. It is committed in
the next PM batch or the next task's pull request.

## Follow-up work

* **An alias edit at a released version goes unseen** (PM question 1). If the PM wants it closed:
  a digest of each release's full positions in the lock, in a small follow-up to this task.
* **Merge order.** If t05 publishes 1.1.0 before t08 merges, and the file is bumped again (t09's
  mechanism child affs, 1.2.0) before anyone writes the lock, the writer can no longer lock 1.1.0,
  because it refuses a version the file has moved past. Locking 1.2.0 when it is published would
  still protect every 1.1.0 id that 1.2.0 kept, but not one deleted in between. Merging t08 before
  t05's first `--publish` avoids this (PM question 3).

## Questions for the PM

```text
v1-e32-t08 questions for the PM (2026-10-24). Each has a recommendation.

1. Alias edits at a released version. The lock holds id, kind and side only (your ruling), so an
   alias added at 1.1.0 without a bump passes the check. A report under "1.1.0" could then count
   differently from another one, and t02's cache, keyed on taxonomy_version, would keep stale
   placements.
   (a) Leave it as ruled. The guide tells the coach to bump, and review catches the rest.
   (b) Follow-up: add a digest of each release's positions (every field, as canonical JSON, sha256)
       to the lock. Any edit at a released version is refused, and the lock still holds no label
       text or counts.
   Recommendation: (b), as a small follow-up after t05's first publish. It closes the one way a
   version stops meaning one taxonomy, and it adds a field, not text.

2. Spec amendments for t08. (i) The node criterion runs only tests/config/test_landscape_taxonomies.py,
   and the new check lives in test_landscape_released_ids.py by your ruling. (ii) The description
   still asks to refuse a label change "past a rename", which your ruling allows.
   Recommendation: change the criterion's args to [run, pytest, tests/config], and replace the label
   clause with "a merged_into naming a retired position; a label may change".

3. Merge order with t05. If t05 publishes 1.1.0 before t08 merges and the file is bumped again
   (t09's 1.2.0) before the lock is written, 1.1.0 can no longer be locked, because the writer
   refuses a version the file has moved past.
   (a) Merge t08 before t05's first --publish; t05's operator writes the 1.1.0 lock right after it.
   (b) Either order, with the rule that no taxonomy bump merges until the published version's lock
       is committed.
   Recommendation: (a). t08 touches nothing t05 does.

4. Two readings to confirm, both implemented and tested. Generic.yaml's ids are released with each
   topic (a release records the merged taxonomy a report counted against). A file's version may
   not go below a released one.
   Recommendation: keep both.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
