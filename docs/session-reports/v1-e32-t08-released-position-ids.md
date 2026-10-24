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
lock file. For each topic and released version it holds every position id with its kind and side,
and a **positions digest**: the sha256 of every field of every position, as canonical JSON. It holds
no label text and no counts, and it is empty today (`releases: []`). On every pull request,
`tests/config/test_landscape_released_ids.py` checks the committed taxonomy files against it,
naming the file, the id (when a rule is about one) and the rule. It refuses:
- a released id that was deleted;
- a released id whose kind or side changed;
- any edit to a file at a released version (by the ids, or by the digest);
- a version below a released one;
- a `merged_into` naming a retired position.

`scripts/release_landscape_taxonomy.py --topic --version` writes the lock from the committed files
alone. The guide says the operator runs it for 1.1.0 right after `v1-e32-t05`'s first `--publish`,
which comes after this task merges. Every acceptance criterion passed and the Goal is
**Succeeded**. The second round followed the PM's rulings of 2026-10-24 ([below](#pm-rulings-of-2026-10-24-and-what-changed)).
**Look first at** that section's first item. Because the digest covers every field, a label edit at
a released version is now refused until it comes with a bump. The first report said a label change
passed even at the released version.

## PM rulings of 2026-10-24 and what changed

1. **The positions digest, in this task.** Each release now records `positions_digest`. A file at a
   released version whose digest no longer matches is refused, whatever the edit. I committed the tests red
   first (`681e8dc`, 3 failed, 22 passed): an alias added, a label changed, and a generic alias added,
   each at a released version. Each case then shows the same edit with a bump passing. Green at `7d4f8af`.
   **One consequence to confirm:** "every field" includes the label, so a label edit at a released
   version needs a patch bump. That is what the guide's version table already asked; the check now
   holds it. Renames across versions are still free: only the id, kind and side are fixed across
   versions. The test `test_a_label_change_passes_even_at_the_released_version` became the
   `label-changed` case of `test_any_edit_at_a_released_version_is_refused_and_passes_with_a_bump`.
2. **Spec amendments**, each with a `# PM ruling 2026-10-24` comment above its folded block (checked
   in the parsed spec: no comment text leaked into the description). The node criterion's args are
   now `[run, pytest, tests/config]`. The label clause reads "a merged_into naming a retired
   position; a label may change". I also added "and the positions digest" to the description's list of what the lock
   holds, with its own PM-ruling comment, so the spec describes the file as built. That third edit
   is mine, not one the ruling named; strike it if you prefer.
3. **Merge order (a).** The guide and the Operator follow-ups now say that t08 merges before t05's
   first `--publish`, and that t05's operator writes the 1.1.0 lock right after it, committed in a PM
   batch, with the writer's exact command.
4. **Both readings kept:** generic ids are released with each topic, and a version may not go below
   a released one. Nothing changed.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| released-ids | Done | Lock models, digest and rules in `debate_core.domain.landscape_release`; reading, naming and writing in `debate_core.integrations.landscape.released_ids`; the writer script; the check's tests with synthetic fixtures; the guide. Red runs: 16 failed / 21 passed (first round), 3 failed / 22 passed (the digest). 26 mutants, all caught on the final code |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the check refuses, naming the file, the id and the rule: a released id missing; a released id's kind or side changed; positions changed with no taxonomy_version bump; topics.yaml's version not equal to the file's. Each by a synthetic fixture shown failing first | PASS | `tests/config/test_landscape_released_ids.py` → 25 passed. One synthetic fixture each: an id deleted (topic file, and a generic id); a released topic left with no taxonomy; kind changed; side changed (topic file, and generic.yaml); an id added at a released version; a kind change and a deletion at a released version, each refused by both rules; an alias, a label or a generic alias changed at a released version (by the digest); a version below a released one; a `merged_into` naming a retired position; topics.yaml's version unequal to the file's; a missing lock. Each asserts the file and `Rule (<rule>)`, and the id where the rule names one. A changed digest cannot say which position changed, so that finding names the topic's file "(with generic.yaml merged in)" and no id. Red runs: 16 failed / 21 passed against a refuse-nothing skeleton, then 3 failed / 22 passed before the digest rule. Three refusals already held before this task and could not fail a red run: topics.yaml's version (`v1-e32-t01`'s repository rule, which the check loads through), the missing lock, and an unknown topic in the writer. The first two were shown failing by mutation |
| ac2: a retirement (deprecated, or merged_into an existing id) and a new id both pass, with the version bumped | PASS | `test_a_retirement_a_merge_and_a_new_id_pass_with_the_version_bumped`, 4 cases at 1.1.0 over a 1.0.0 lock: retired, merged into an active id, a new id, a rename to a new id. Also passing with a bump: an alias, a label and a generic alias edit. Also passing: an unchanged released version, and any edit with an empty lock |
| ac3: the lock is written by a command the guide documents, from the committed taxonomy files alone, and the guide says when the operator runs it | PASS | `tests/scripts/test_release_landscape_taxonomy.py` → 6 passed. The expected lock texts are written by hand from the fixture (working agreement 6), with each position's canonical JSON written as a literal and hashed in the test. They agree with the code's digest. On a scratch copy of today's `config/landscape/`, the writer refused `--version 1.1.0` ("policy-2026-27-nhi is at 1.0.0, not 1.1.0"), wrote 1.0.0 with 73 ids (54 of the topic's own and 19 from generic.yaml) and a digest, and refused 1.0.0 a second time. The check passed on the locked copy and refused it once an alias was added at 1.0.0. The guide's section [Released ids and the lock file](../guides/landscape-taxonomy.md#released-ids-and-the-lock-file) gives the command and says when to run it |
| released-ids node (as amended): `uv run pytest tests/config` | PASS | 46 passed, 2 skipped (the two override cases skip: there is no overrides file on `dev` yet) |

### Checks shown failing for their reason

Each mutant was one replacement, matched exactly once, in the committed source. Each was run with
`.venv/bin/python -m pytest -n0 -p no:randomly` over the three new test files under
`perl -e 'alarm 60'`, with a fresh `HYPOTHESIS_STORAGE_DIRECTORY` (agreement 8; no property tests
here). The file was restored from the commit after each run, and the tree was clean afterwards.
I ran all 26 against the final code, the digest included, because the digest rule could otherwise
stand in for a per-id rule that a mutant had removed. All 26 were caught:

| Mutant | Caught by |
|---|---|
| a released id missing not reported | 4 tests (deleted id, deleted generic id, deletion at a released version, writer over a broken configuration) |
| side change ignored / kind change ignored | 2 tests each |
| a released topic left without a taxonomy not reported | `test_a_released_topic_left_without_a_taxonomy_is_refused` |
| a version below a released one not reported | `test_a_version_below_a_released_one_is_refused` |
| a released version never compared with its lock | 6 tests |
| an id added at a released version not reported | `test_a_position_added_at_a_released_version_is_refused` |
| an id deleted, or a kind changed, at a released version not reported by the version rule | `test_a_change_at_a_released_version_is_refused_by_both_rules[deleted]`, `[kind-changed]` |
| a merge into a retired position not reported | 2 tests |
| the writer accepts a version the file is not at / rewrites a released version | domain test and script test, each |
| the lock accepts a version twice / a release lists an id twice | one domain test each |
| a missing lock read without its own message | `test_a_missing_lock_file_is_refused_not_read_as_empty` |
| the writer writes over a configuration that breaks a released id | `test_a_configuration_that_breaks_a_released_id_is_refused` |
| a generic position named under the topic's file | `test_a_released_generic_id_whose_side_changed_is_refused_naming_generic_yaml` |
| topics.yaml's version mismatch accepted (`v1-e32-t01`'s rule, mutated in `yaml_taxonomy_repository.py`) | `test_a_taxonomy_version_unequal_to_topics_yaml_is_refused_naming_the_file` |
| the digest never compared | the 3 cases of `test_any_edit_at_a_released_version_is_refused_and_passes_with_a_bump` |
| the digest leaves out aliases / leaves out labels | 5 and 6 tests (the domain digest tests, the hand-written script locks, the config fixtures) |
| the digest's keys unsorted / defaults kept in | 5 tests each, the hand-written canonical literal among them |
| any string accepted as a digest | `test_a_digest_is_sha256_hex` |
| a digest finding named under the topic's file alone | the 3 digest cases |
| the digest not written to the lock | both writing tests in the script suite |

### Checks run before this report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` | 105 files, the same list both rounds. In the first round, `perl -e 'alarm 115' .venv/bin/python -m pytest -n auto -m "not slow and not live" <the 105>` was stopped by the alarm at 115 s (exit 142). It runs past two minutes, so per agreement 10 it is left to the pull request's `ci`, with no hand-off. I did not run it again for the second round |
| The changed test directories and the always-run list: `.venv/bin/python -m pytest -n auto -m "not slow and not live" tests/config packages/debate_core/tests/domain/test_landscape_release.py packages/debate_core/tests/domain/test_landscape_taxonomy.py packages/debate_core/tests/integrations/landscape tests/scripts/test_release_landscape_taxonomy.py tests/scripts/test_classify_landscape_positions.py tests/scripts/test_seed_landscape_taxonomy.py tests/scripts/test_assign_landscape_affs.py tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py` | 678 passed, 2 skipped, 21 s. The 2 warnings are the CLI doctor tests' blocked socket, not this task's |
| `uv run --frozen ruff format --check .` / `ruff check .` | 1212 files already formatted / All checks passed |
| `uv run --frozen pyright` (CI's: `packages/`) | 0 errors |
| `uv run --frozen lint-imports` | 16 kept, 0 broken |
| `uv run --frozen python scripts/check_thin_handlers.py` | OK: 47 handlers within 25 statements |
| `uv run --frozen python scripts/docs_index.py --check-descriptions` / `check_command_blocks.py --base origin/dev` | All 44 described / no `#` comments |
| `uv run scripts/validate_specs.py` | OK: 434 files, 40 epics, 372 tasks, 22 releases |

## Files changed

* `packages/debate_core/src/debate_core/domain/landscape_release.py` (new): the lock models
  (`ReleasedPosition`, `TaxonomyRelease` with `positions_digest`, `ReleaseLock` with
  `with_release`), `positions_digest`, the five rules (`ReleaseRule`, `RULE_TEXT`), and
  `release_findings` / `merged_into_findings`, pure over the lock and the merged taxonomies.
* `packages/debate_core/src/debate_core/integrations/landscape/released_ids.py` (new): reads and
  renders `released.yaml`, puts the file name on each finding, and holds the writer's logic.
* `.../integrations/landscape/yaml_taxonomy_repository.py`: the private `_read` is now the public
  `read_config_file`, so the lock is read with the same duplicate-key refusal. Rename only.
* `config/landscape/released.yaml` (new): the empty lock, in the writer's form.
* `scripts/release_landscape_taxonomy.py` (new): the writer, a thin argparse wrapper.
* `tests/config/test_landscape_released_ids.py` (new): the check on the committed files, and every
  refusal and pass on synthetic configurations.
* `tests/config/test_landscape_taxonomies.py`: the one edit to `v1-e32-t01`'s test file. Its "nothing
  else in the directory" test allows `released.yaml` by name. `v1-e32-t05`'s branch does not touch
  this file.
* `packages/debate_core/tests/domain/test_landscape_release.py` (new), and
  `tests/scripts/test_release_landscape_taxonomy.py` (new).
* `docs/guides/landscape-taxonomy.md`: the lock in the "Where things are" table; "Check your edit"
  runs `tests/config`; a new section, "Released ids and the lock file", covering what is refused
  and what to do instead, labels at a released version, when the operator writes the lock, and the
  1.1.0 step after t05's first publish.
* The task spec: phase `Succeeded`, and the PM's amendments with their comments.

## Deviations from the spec

1. **topics.yaml's version equal to the file's (ac1)** was already `v1-e32-t01`'s repository rule.
   The check loads the configuration through it rather than repeating it, and a synthetic test
   asserts the refusal names the file. It could not fail a red run, so it was shown failing by
   mutating t01's rule.
2. **Two refusals beyond the PM's list**, each tested. A missing lock file is refused, since a
   deleted lock would otherwise pass everything. The writer refuses a configuration that already
   breaks a released id, so a lock never records a break. (The version-below rule was confirmed by
   the PM.)
3. **Test files outside `constraints.packages`:** `packages/debate_core/tests/domain/` and
   `tests/scripts/`, the test homes of the domain module and the script the spec asks for.
4. **One edit to t01's test file** (Files changed). Without it, t01's directory test refuses the lock.

## Decisions and assumptions

1. **A release records the merged taxonomy:** the topic's own positions followed by generic.yaml's
   for its event, retired ones included. That is what a report under the topic's version counted
   against, and the PM confirmed it. The digest covers the same list, so an edit to generic.yaml at
   a released topic version is refused like an edit to the topic's file.
2. **The canonical JSON** is each position's `model_dump(mode="json", exclude_defaults=True)`, in
   file order, keys sorted, no whitespace, UTF-8. Every field a position sets is in it. A field left
   at its default is left out, so writing `deprecated: false` or `description: ""` out changes
   nothing (tested). A new optional field added to the model later will not change every released
   digest. A hand-written literal of the canonical form pins this in the domain test.
3. **A finding names the file to edit.** That is the topic's file, or generic.yaml when the position
   now lives there. For an id in neither, or a changed digest (which cannot say which position or
   file changed), it is "the topic's file (with generic.yaml merged in)". The lock records nothing
   beyond the ids, kinds, sides and the digest.
4. **At a released version, the id rules run before the digest.** Ids added, removed or changed in
   kind or side are each named. The digest finding is added only when none is, so an edit the ids
   show is reported by id rather than twice.
5. **The `merged_into` rule runs on every file, lock or not.** No committed file has one today.
6. **The writer reads the working tree.** The guide asks for a worktree up to date with `dev`, and
   the version equality guards against a late lock. No git check, so neither the writer nor its tests need git.

## Operator follow-ups

None for this branch before it merges. It merges into `dev` before `v1-e32-t05`'s first `--publish`
(PM ruling 2026-10-24). Right after that publish, t05's operator writes the 1.1.0 lock. Run this in
a worktree up to date with `dev` (with t08 merged), once the report shows `Taxonomy version` 1.1.0
at the top of `report.md` or `taxonomy_version` 1.1.0 in `--json`:

```bash
uv run python scripts/release_landscape_taxonomy.py --topic policy-2026-27-nhi --version 1.1.0
```

Expected runtime under a second. Success: `Released policy-2026-27-nhi 1.1.0: N position ids written
to ...` with N above zero. Today's 1.0.0 gave 73 on a scratch copy, and t05's branch adds five
positions. Then check the files and read the diff:

```bash
uv run pytest tests/config
git diff config/landscape/released.yaml
```

The tests pass, and the diff adds one release: `policy-2026-27-nhi`, `1.1.0`, a `positions_digest`,
and the ids. The lock is committed in a PM batch. It must be written before any later edit bumps the
file past 1.1.0 (t09's child affs), because the writer refuses a version the file has moved past.

## Follow-up work

* `v1-e32-t05`, which merges after this task, adds the 1.1.0 step above to its own first-publish
  instructions, as the guide says.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-24

**Notes:**

1. **The lock does what the guide promised.** Every rule is refused by a synthetic fixture,
   and the refusal names the file, the rule and the id where there is one. There were two red runs
   (16/21, then 3/22 for the digest), and all 26 mutants were caught on the final code, run with
   the digest in place, so no rule hides behind another. The writer was tried on a scratch copy of
   today's config.
2. **A label edit at a released version needs a bump: accepted as built.** It is the direct result
   of "every field" and "any edit", and the guide's version table already asked for a patch bump.
   Renames across versions stay free, with only id, kind and side fixed.
3. **Leaving default-valued fields out of the canonical JSON: accepted.** Every field a position
   sets is covered, and a new optional model field won't break every released digest.
4. **Your third spec edit** ("and the positions digest" in the description's list) is accepted. The
   spec should describe the file as built.

**The PR:** opened without `--partial`. It merges **before** v1-e32-t05's first `--publish`. The
operator then writes the 1.1.0 lock with the command in the guide, and the PM commits it in a PM
batch.
