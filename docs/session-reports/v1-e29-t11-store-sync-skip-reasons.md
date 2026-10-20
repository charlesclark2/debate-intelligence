# Session report: v1-e29-t11-store-sync-skip-reasons

| | |
|---|---|
| Task | `v1-e29-t11-store-sync-skip-reasons` — store sync says why it skipped what it skipped |
| Spec | [`plan_specs/v1/e29-cloud-evidence-store/t11-store-sync-skip-reasons.yaml`](../../plan_specs/v1/e29-cloud-evidence-store/t11-store-sync-skip-reasons.yaml) |
| Epic / release | `v1-e29-cloud-evidence-store` / `v1.1` |
| Branch | `task/v1-e29-t11-store-sync-skip-reasons` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Every object the sync planner skips now carries a `SkipKind`. The branch that skipped it sets the
kind, and a `PlannedObject` refuses a skip with no kind, or a kind on anything that is not a skip.
`SyncPlan.skipped_reasons` groups the skips by kind, never by the reason's text. Each kind has a
count and up to three distinct 12-character key prefixes. A manifest the publisher withholds or
cannot read also carries the publisher's message word for word, and the requests that message names.
`store sync --json` gains the one key `skipped_reasons`, and every earlier key is unchanged. The
table gains a `WITHHELD MANIFESTS` line naming the requests and the removal to run again, and an
`UNREADABLE MANIFESTS` line. Each appears only when such a manifest was left behind.

To tell "withheld" from "unreadable" without parsing text, `withheld_manifest_reason` now answers
with a small `ManifestWithholding` value instead of a string: the message, whether the manifest
could not be read, and the request ids. Please look first at the **PM questions**. The spec's
v1-e34-t02 reader of this payload does not exist (Deviation 1), and "12-character key prefix" was
read literally (Decision 2).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `skip-reasons` — Store sync skip reasons | Done | Skeleton `ef9ad82`, red tests `4c91edc`, implementation `7495264`, guide `eba1724`, removal smoke `3a5f3a7` |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: `store sync --json` carries `skipped_reasons` with each reason's count and key prefixes for a push that withholds a manifest and skips a held-only blob, and the table's caption names the withheld manifest and the removal to run again, by tests shown failing first | PASS | **Red first.** I ran the new tests at `4c91edc` against the skeleton `ef9ad82`, which has the API but assigns no kind, returns an empty breakdown and prints no caption line: `uv run pytest -q -p no:randomly packages/debate_core/tests/application/test_evidence_sync_skip_reasons.py packages/debate_core/tests/application/caselist/test_store_sync_skip_reasons.py "packages/debate_cli/tests/commands/test_store.py::TestSkipReasons"` → `26 failed, 6 passed`. Every failure was an assertion or a `DID NOT RAISE`, for example `assert {} == {'held_only_blob': …, 'withheld_manifest': …}` and `KeyError: <SkipKind.WITHHELD_MANIFEST>`. The six that passed were: the empty breakdown; the publisher's answer for the three suppressed-row kinds, whose messages name no request; the publisher's `None` for a manifest it publishes; and the earlier keys' values (ac2). **Green:** the same command → `32 passed`. Through the CLI, `TestSkipReasons::test_the_json_breaks_the_skips_down_by_kind_with_the_publishers_message` is a push that withholds the 2026-10-08 manifest and leaves out its held-only blob. Its `skipped_reasons` equals the hand-written `{"held_only_blob": {"count": 1, "key_prefixes": ["raw/caselist"]}, "withheld_manifest": {"count": 1, "key_prefixes": ["manifests/te"], "messages": ["the local manifest still has 1 row(s) at a path a removal holds: <digest> (RM-2026-01), whose bytes …"], "request_ids": ["RM-2026-01"]}}`. No school, team code or `.docx` appears in the output. `…::test_the_caption_names_the_withheld_manifest_and_the_removal_to_run_again` checks for the line `WITHHELD MANIFESTS: 1 manifest(s) the publisher withholds, left on this machine (RM-2026-01). Run the same removal again on this machine (caselist remove … --request RM-2026-01) to rewrite them, then push again; --json has the publisher's message for each.` With the real publisher, `caselist/test_store_sync_skip_reasons.py::test_a_push_reports_the_withheld_manifest_and_the_held_only_blob_by_kind` shows the breakdown's message **equals** what a real `caselist publish` of that snapshot says. Through the installed binary, t25's removal smoke check reads `skipped_reasons` (Deviation 2): `uv run pytest -q -p no:randomly tests/smoke/test_caselist_remove_smoke.py -k a_push_sends_no_manifest_the_publisher_withholds` → `1 passed`. On a publisher that names no request it fails with `(1, []) != (1, ['RM-2026-03'])` |
| **ac2**: the existing summary keys are unchanged, and the scheduled run's reader (v1-e34-t02) reads the new payload, by test | PASS (see Deviation 1) | `TestSkipReasons::test_every_earlier_key_keeps_its_shape_and_value_beside_the_new_one`: the payload's keys are the hand-written set of 13 keys from before this task, plus `skipped_reasons`. Each earlier key's value equals a hand-written expectation: counts, byte totals, `remote_head_requests`, `transferred`, `failed`, `mismatched`, `journal`. `…::test_a_failed_run_carries_the_breakdown_for_the_scheduled_consumer`: `error.details` carries it too. **Cross-build:** no code in any build reads `store sync --json` (Deviation 1). The readers that exist are each build's own store CLI tests, which pin every key and value, so I ran the older builds' `packages/debate_cli/tests/commands/test_store.py` against this build. Each was copied into the worktree beside the current file and deleted afterwards. **v1.1.0-dev.18** → `36 passed in 4.29s`; **v1.1.0-dev.59** (newest dev tag) → `38 passed in 3.98s`. Mutant C4 (an earlier key dropped) is caught by the new test |
| **ac3**: the guide's `skipped` row points at the breakdown | PASS | `docs/guides/evidence-store-cli.md`: the `skipped` row ends "Which of these each skip was is in `skipped_reasons` in `--json` … see [Why something was skipped]". A new subsection lists the nine kinds, the fields, both caption lines and a `jq` line. `uv run scripts/check_command_blocks.py` → `OK: no # comments in 281 shell code blocks in 124 Markdown files` |
| Node `skip-reasons`: Store sync tests pass (`uv run pytest packages/debate_core/tests/application packages/debate_cli/tests -k "store or sync"`) | PASS | At `7495264` → `627 passed in 21.13s`. Again on the final tree → `627 passed in 39.24s` (load average 13–16 from other sessions) |

### Checks run before the report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py --run` | **NOT RUN, left to the PR's CI** by the PM's ruling of 2026-10-19. It selects 188 files and 4,334 tests (`--collect-only`). At the node command's rate that is about 2.5 minutes, with load average 13–16 at the time |
| The changed modules' direct importers (42 test files that import `evidence_sync`, `publish_service` or the store command), `-m "not slow and not live"` | `825 passed in 65.37s` |
| `uv run pytest -q tests/architecture tests/specs` (the affected set's always-run list) | `181 passed in 6.38s` |
| First attempt: the importers above, the two smoke files and the always-run list in one command | Stopped by its `perl alarm 115` hard stop with no result; no workers were left behind. Split up, every part passed: the two rows above and the removal smoke row in ac1 |
| `uv run ruff format --check .` / `uv run ruff check .` | `889 files already formatted` / `All checks passed!` |
| `uv run pyright packages/debate_core packages/debate_cli` | `0 errors, 0 warnings, 0 informations` |
| `uv run lint-imports` | `Contracts: 12 kept, 0 broken.` |
| `uv run scripts/validate_specs.py` | `OK: 394 files, 39 epics, 334 tasks, 21 releases` |

### Mutation run (20 mutants, all caught)

The runner applied each mutant, ran only the test files covering it, and restored the file. It is
in the session scratchpad, not committed. The worktree was clean after every batch.

| Mutant | Result | First test to fail |
|---|---|---|
| G1 key prefixes not de-duplicated | CAUGHT | `test_manifests_withheld_for_different_rows_are_one_kind_with_each_message` |
| G2 key prefix 13 characters | CAUGHT | same |
| G3 four key prefixes | CAUGHT | `test_at_most_three_distinct_key_prefixes_in_key_order` |
| G4 a key under no documented prefix given a prefix | CAUGHT | `test_the_breakdown_groups_every_skip_by_kind_with_its_count_and_key_prefixes` |
| G5 messages for every kind | CAUGHT | `test_a_pull_reports_the_same_way_and_has_no_push_only_kind` |
| G6 no messages | CAUGHT | `test_the_publishers_message_is_the_plans_reason_word_for_word` |
| G7 request ids repeated and unsorted | CAUGHT | `test_manifests_withheld_for_different_rows_are_one_kind_with_each_message` |
| G8 grouped by reason text | CAUGHT | same |
| G9 every kind listed, absent ones at zero | CAUGHT | `test_at_most_three_distinct_key_prefixes_in_key_order` |
| K1 unreadable planned as withheld | CAUGHT | `test_each_kind_reports_as_json_with_messages_only_for_the_publisher_kinds` |
| K2 held-only blob called suppressed | CAUGHT | `test_every_skip_carries_the_kind_of_branch_that_skipped_it` |
| K3 journaled called identical | CAUGHT | `test_each_kind_reports_as_json_…` |
| K4 request ids not carried to the plan | CAUGHT | same |
| K5 a skip with no kind allowed | CAUGHT | `test_a_skip_without_a_kind_is_refused` |
| P1 publisher never says unreadable | CAUGHT | `test_the_publishers_answer_for_a_manifest_it_cannot_read_is_its_refusal` |
| P2 held skipped rows' requests left out | CAUGHT | `test_the_publishers_answer_names_exactly_the_requests_its_message_names[a held link]` |
| C1 caption names no request | CAUGHT | `TestSkipReasons::test_the_caption_names_the_withheld_manifest_and_the_removal_to_run_again` |
| C2 caption line for every other kind | CAUGHT | `TestSkipReasons::test_identical_and_journaled_skips_stay_a_count_with_no_caption_line` |
| C3 caption without the removal to run again | CAUGHT | `TestSkipReasons::test_the_caption_names_…` |
| C4 an earlier payload key dropped | CAUGHT | `TestSkipReasons::test_every_earlier_key_keeps_its_shape_and_value_beside_the_new_one` |

## Files changed

- **`debate_core.application.evidence_sync`**: `SkipKind`, `ManifestWithholding`, `SkippedReason`;
  `PlannedObject.skip_kind` and `request_ids`, with the invariant; a kind at each of the planner's
  skip branches; `SyncPlan.skipped_reasons`. The module docstring says why skips are grouped by
  kind. `WithheldManifests` now answers with `ManifestWithholding | None`.
- **`debate_core.application.caselist.publish_service`**: `withheld_manifest_reason` returns a
  `ManifestWithholding`, flags an unreadable manifest, and carries the requests its message names
  (`_requests_named`). The message is unchanged. This file is not one v1-e31-t26 changed.
- **`debate_cli.commands.store`**: the `skipped_reasons` key, and the two caption lines.
- **Tests**: `packages/debate_core/tests/application/test_evidence_sync_skip_reasons.py` (new, 14);
  `packages/debate_core/tests/application/caselist/test_store_sync_skip_reasons.py` (new, 11);
  `packages/debate_cli/tests/commands/test_store.py` (`TestSkipReasons`, 7);
  `packages/debate_core/tests/application/caselist/test_store_sync_withholds_manifests.py` (type
  annotations only: the publisher answers with a `ManifestWithholding`).
- **Smoke**: `tests/smoke/test_caselist_remove_smoke.py` (two assertions on t25's check) and its
  `tests/smoke/README.md` row (Deviation 2).
- **Docs**: `docs/guides/evidence-store-cli.md`.
- **Spec**: the task Goal set to `Succeeded`.

## Deviations from the spec

1. **The "scheduled run's reader (v1-e34-t02)" of this payload does not exist.** The spec and
   `sync_report`'s docstring both say v1-e34-t02 reads `store sync --json`, but the scheduled
   `caselist pull` publishes through `caselist publish` and never runs `store sync`. Nothing in
   `debate_core`, `debate_cli`, `ops/`, `scripts/` or `.github/` reads this payload; I searched for
   `store sync`, the command's argv spelling, and importers of `evidence_sync`. So ac2's "reader"
   was checked two ways. A test pins every earlier key and its value. And the older builds' own
   store CLI tests, the only code in any build that reads the payload, pass against this build
   (dev.18 and dev.59). PM question 2 asks how you want ac2 worded.
2. **`tests/smoke/` is outside `constraints.packages`, but I added two assertions there.**
   Agreement 5 asks a task that changes a user-facing surface to update its smoke check, and the
   spec has no smoke node. I added the breakdown to t25's existing removal smoke check, which
   already runs `store sync --apply` on a withheld manifest through the installed binary, and to
   its README row. It is not a new check. It is shown failing on a mutant, as ac1 records. If you'd
   rather it waited for a spec change, revert `3a5f3a7` alone.
3. **The caption's fix for an unreadable manifest is not "the same removal run again".** The PM
   notes ask the caption to give that fix. It is the fix for a withheld manifest, and the
   `WITHHELD MANIFESTS` line gives it. An unreadable manifest is a damaged file, not a removal's
   leftover, so the `UNREADABLE MANIFESTS` line points at `--json`, whose message names the key and
   the line number, and offers no removal.

## Decisions and assumptions

1. **Nine kinds, counted from the planner, not five.** The PM notes expected five: identical,
   journaled, held-only blob, withheld manifest and unreadable manifest. `_classify` and
   `_unless_withheld` have four more skip branches: the suppression record
   (`manifests/_suppression/`), a blob on the suppression list, a key another keyspace owns, and a
   key under no documented prefix. Each is its own kind. A blob "already stored under this digest"
   and a named object found `identical` by its head are both one kind, `identical`, because both
   mean the destination already holds those bytes.
2. **A key prefix is the bucket key's first 12 characters, literally, and distinct ones only.** So
   a withheld manifest shows `manifests/te` and a held-only blob `raw/caselist`. That says where in
   the store, not which object, and de-duplicating avoids printing `manifests/te` three times. For
   any of the documented prefixes, 12 characters stop before the segment after the caselist or
   tenant (`files/hsld26`), so they never reach a file name. A key under no documented prefix is
   whatever someone put in the local tree, so it is counted with **no** prefix: the test's key
   starts with a synthetic school's name. What identifies a withheld manifest's rows is the
   publisher's message (digests and request ids). For an unreadable one, the message names the key
   itself. PM question 1 offers the alternative.
3. **The messages are uncapped; the prefixes are capped at three.** "The publisher's message for
   each named object" is read as each object the publisher answered about. Withheld manifests are
   a handful at most, and capping their messages would drop the requests the operator must re-run.
4. **`request_ids` is in the JSON as well as the caption,** for the two publisher kinds. It is
   structured, so a program does not have to parse the messages. These are exactly the requests the
   message names: each held row's and each held skipped row's. A row the list stops is named by its
   digest alone, so a manifest withheld only for such rows names no request, and the caption then
   says `--request <id>`. The test checks the ids against a regex over the real message for all
   seven row kinds.
5. **`withheld_manifest_reason` keeps its name and changes its return type** to `ManifestWithholding`.
   The cross-build helpers (`write_junk_beside_a_held_link_files.py` and t25's test) look it up by
   name with `getattr`. Keeping the name means each build pairs its own publisher with its own sync
   service, and adding a second function would leave the old one used only by tests. The message
   text is unchanged, and `skipped.reason` still equals the publisher's `manifest_error` word for
   word: t25's tests pass unchanged apart from annotations.
6. **The caption names the kind, the count and the requests, never the message.** The message
   stays in `--json`, so the plan's reason is never restated: the forbidden "restating a skip reason
   outside the plan". The caption's own words name the kind and the fix, not the reason.

## Operator follow-ups

None. The affected-set run is the PR's `ci` check, by the PM's ruling of 2026-10-19.

## Follow-up work

1. **`sync_report`'s docstring still says v1-e34-t02 reads this payload** (Deviation 1). I left it,
   pending PM question 2. A one-line change either way. *Done after the review; see below.*

### After the PM review (2026-10-19)

The two changes in ruling 2, committed with the PM's review in `4497080`; this record follows.

- **ac2, PM amendment 2026-10-19:** the spec's ac2 now reads "Every earlier key keeps its value, and
  an earlier build's store tests pass against this build (PM amendment 2026-10-19)." Its evidence is
  the ac2 row above, unchanged: `test_every_earlier_key_keeps_its_shape_and_value_beside_the_new_one`,
  and v1.1.0-dev.18's and v1.1.0-dev.59's `test_store.py` against this build (36 and 38 passed).
- **Follow-up 1:** `sync_report`'s docstring no longer says v1-e34-t02 reads this payload. It now
  begins "Written for a program first". No code changed.

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py --diff HEAD` (the commit with both edits) | 2,942 tests: anything importing the CLI app reaches `store.py`, the slow smoke files included. Over two minutes, so **left to the PR's CI** by the PM's ruling of 2026-10-19 |
| `uv run pytest -q -m "not slow and not live" packages/debate_cli/tests/commands/test_store.py packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py tests/specs tests/architecture` (what a docstring and a spec edit can reach: the command, its wiring and help, the spec checks, the always-run list) | `260 passed in 12.27s` |
| `uv run ruff format --check packages/debate_cli` / `uv run ruff check packages/debate_cli` | `66 files already formatted` / `All checks passed!` (the first try was `E501` on the rewritten docstring line, rewrapped before the commit) |
| `uv run pyright packages/debate_cli` | `0 errors, 0 warnings, 0 informations` |
| `uv run scripts/validate_specs.py` / `--require-succeeded v1-e29-t11-store-sync-skip-reasons` | `OK: 394 files, 39 epics, 334 tasks, 21 releases` / `Succeeded` |

### PM questions

```text
v1-e29-t11 asks the PM, 2026-10-19:

1. Key prefixes. I read "up to three 12-character key prefixes" literally: the bucket key's first
   12 characters, distinct ones only, so a withheld manifest shows `manifests/te` and a held-only
   blob `raw/caselist` (where, not which). Options:
   (a) keep it (done): 12 characters never reach a file name under a documented prefix, and the
       publisher's messages already name the rows by digest and request;
   (b) for a content-addressed object, show the 12-character digest prefix instead
       (`sha256 ab12cd34ef56`), as caselist status does, keeping (a) for named objects.
   Recommendation: (a) for this task. (b) helps only the held-only blob, which caselist status
   already names by digest prefix and request.

2. ac2 names "the scheduled run's reader (v1-e34-t02)". No such reader exists: caselist pull
   publishes through caselist publish and never runs store sync. I checked the earlier keys by test
   and ran the store CLI tests of v1.1.0-dev.18 and v1.1.0-dev.59 against this build (36 and 38
   passed). Options:
   (a) amend ac2 to "every earlier key keeps its value, and an earlier build's store tests pass
       against this build", and drop the claim from sync_report's docstring;
   (b) leave the spec, and keep the docstring's claim as a promise to future readers.
   Recommendation: (a). A promise about a reader nobody wrote is the kind of thing that stops
   being checked.

3. Deviation 2: two assertions added to t25's removal smoke check, outside constraints.packages,
   under working agreement 5. Keep (recommended), or revert 3a5f3a7.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-19

**Notes:**

Accepted, with the phase `Succeeded`, once the session makes the two small changes in ruling 2 and
commits them. The pull request needs no `--partial`.

**The work itself:**

* **Grouped by kind, set where the skip happens,** with an invariant that refuses a skip without a
  kind. Mutant G8, which groups by text, is caught.
* **The publisher answers with a value, not a string.** Withheld and unreadable are told apart, and
  the request ids are carried without parsing the message. The message itself is unchanged, and t25's
  tests pass apart from annotations.
* **Nine kinds, counted from the planner rather than taken from my five,** and the reason for each is
  written down.
* **Deviation 1 corrected my spec, not just the code.** I wrote that v1-e34-t02 reads this payload,
  and no build does. The session searched, said so, and checked compatibility the way that actually
  exists: older builds' own store tests pass against this build.
* **20 mutants, all caught.**

**Rulings:**

1. **Question 1: (a).** Distinct 12-character key prefixes say where in the store, never which file.
   The publisher's messages carry the digests and requests that identify rows, and `caselist status`
   already names held blobs by digest prefix.
2. **Question 2: (a).** Amend ac2 in the spec to "every earlier key keeps its value, and an earlier
   build's store tests pass against this build", marked "PM amendment 2026-10-19", and drop the
   v1-e34-t02 claim from `sync_report`'s docstring (Follow-up 1). A promise about a reader nobody
   wrote stops being checked. Both are one-line changes in this session, before the pull request.
3. **Question 3: keep `3a5f3a7`.** Agreement 5 asks for it, and it is shown failing on a mutant.
4. **Deviation 3 is accepted.** An unreadable manifest is damage, not a removal's leftover, so its
   line must not send the operator to rerun a removal.
5. **Decisions 1 to 6 are accepted.**
6. **The affected set was left to CI by my ruling,** and the session ran the changed modules' direct
   importers and the always-run list itself. That is the right use of the rule.
