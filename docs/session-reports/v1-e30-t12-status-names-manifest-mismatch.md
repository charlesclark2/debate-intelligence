# Session report: v1-e30-t12-status-names-manifest-mismatch

| | |
|---|---|
| Task | `v1-e30-t12-status-names-manifest-mismatch` — caselist status tells a manifest mismatch from a source mismatch |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t12-status-names-manifest-mismatch.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t12-status-names-manifest-mismatch.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t12-status-names-manifest-mismatch` |
| Session status | COMPLETE |

## Summary

`caselist status` now names each checksum mismatch by kind. A mismatch on a snapshot's own manifest key
is a **manifest mismatch**, meaning this machine's copy was rewritten since its last publish. Its hint is
`caselist publish --caselist <slug>` for each caselist affected. A mismatch on a source key is a
**source mismatch** and keeps the "needs a person" hint. A run with both kinds prints both hints. The
JSON gives each mismatch a `kind`, and every existing field is kept. The table and the JSON now also show
each snapshot's suppressed rows and each caselist's suppressed objects. A run whose only difference is
a suppressed object no longer says "0 snapshot(s) differ". No exit code changed. The PM should look
first at **Deviations** (suppressed objects are reported per caselist, not per snapshot) and at
Decision 4 (removed files appear only as a twelve-character prefix in the new JSON fields).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `mismatch-kinds` (Manifest and source mismatches reported apart) | Done | Tests were written first and seen failing (commit `ed4dfe4`), then the code made them pass (`3624541`, `594e86d`). The branch was rebased onto `origin/dev` with `scripts/task sync` after a generated-files refresh (#246) landed there |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: when the only mismatches are manifest keys, `caselist status` names them as manifest mismatches, and its hint names `caselist publish --caselist <slug>` for each caselist affected. Exit code unchanged. Shown failing first | PASS | Red, then green: see "Shown failing first" below. Tests in `TestStatusNamesManifestMismatches` (`packages/debate_cli/tests/test_caselist_publish.py`). (1) Two caselists, three rewritten manifests: exit `1`, `CASELIST_DRIFT`, message `… testcl26 2026-09-01 (manifest mismatch), …`, a hint naming `caselist publish --caselist testcl26` and `caselist publish --caselist testcl27`, and no "needs a person". (2) Running the hinted publish clears it: status exits `0`. (3) A complete archive (`full/2026-09-20`) is classified by its own key `manifests/testcl26/full/2026-09-20.jsonl`, and `caselist publish --caselist testcl26` clears it. (4) The text output shows the label, the hint and `differs` in the Manifest column. Core equivalents are in `test_status_mismatch_kinds.py` |
| ac2: a source-blob mismatch keeps the hint that a person must investigate, and a run with both kinds prints both hints, by test | PASS | `TestStatusKeepsTheSourceMismatchHint`. Source only: message `… (1 source mismatch(es))`, the hint contains "needs a person" and no `caselist publish --caselist`, and the JSON kind is `source`. Both kinds: the hint contains both, and one snapshot's `mismatches` lists `manifest` then `source`. Missing only (before any publish): the hint is exactly ``"`caselist publish` completes what is missing here."`` |
| ac3: the JSON output gives each mismatch its kind, and `caselist-backfill.md` drops the sentence that works around the old hint | PASS | Per snapshot, `mismatches: [{"key", "kind"}]` follows the order of `checksum_mismatches`, which is unchanged. `test_status_after_a_publish_exits_zero` pins the full key set: every earlier field plus the three new ones. Runbook: *"That is expected, not the mismatch that needs a person."* is gone. The paragraph now says what status prints, and the troubleshooting row gives each kind's action |
| ac4: `caselist status` shows each snapshot's `suppressed_rows` and `suppressed_objects`, in the table and in the JSON. A snapshot whose only difference is a current suppressed object says so rather than "0 snapshot(s) differ". Shown failing first. Exit codes unchanged | PASS (with a deviation) | `TestStatusShowsSuppressedRowsAndObjects`. Suppressed rows per snapshot: a `Suppressed rows` column, plus `suppressed_rows` (count) and `suppressed_row_prefixes` in the JSON, matching the hand-written fixture (weeks 1 and 2 hold the file, week 3 does not). Suppressed objects per caselist (see Deviations): a `SUPPRESSED SOURCE OBJECTS in testcl26: 1 current object(s) (sha256 …)` line under the table, and top-level `suppressed_objects: [{"caselist", "objects", "sha256_prefixes"}]`. With only a suppressed object left and the version listing refused, the run still exits `1` as `CASELIST_DRIFT`. The message is now `every snapshot agrees, and the bucket still holds 1 current object(s) of suppressed sources: testcl26 1`, the hint points at the removal runbook, and "0 snapshot(s)" appears nowhere in the output |
| Node `mismatch-kinds`: Status tests pass | PASS | `uv run pytest packages/debate_cli/tests -k status` → `26 passed in 10.82s` |

### Shown failing first

The tests were committed before any implementation (`ed4dfe4`) and run against the unchanged code:

```bash
uv run --frozen pytest packages/debate_cli/tests/test_caselist_publish.py packages/debate_core/tests/application/caselist/test_status_mismatch_kinds.py -k "status or Status" -q -p no:randomly
```

Result: `16 failed, 3 passed in 5.17s`. The three that passed are the existing status tests whose
behaviour is unchanged. Each failure was on the behaviour, not on setup. The `full/` archive and the
two-caselist publishes completed before the failing assertion. Each status run also asserts exit `1`
before checking the message, which shows that the old code's exit code was the same. Excerpts:

```text
E  AssertionError: assert 'caselist publish --caselist testcl26' in '`caselist publish` completes what is missing here; a checksum mismatch needs a person.'
E  - 2026-09-01 (manifest mismatch), testcl26 2026-09-15 (manifest mismatch, 1 source mismatch(es))
E  + 2026-09-01, testcl26 2026-09-15
E  KeyError: 'mismatches'
E  KeyError: 'suppressed_rows'
E  + 0 snapshot(s) differ between this machine and the bucket:
E  AttributeError: 'SnapshotStatus' object has no attribute 'manifest_mismatched'
E  AttributeError: 'CaselistStatusReport' object has no attribute 'suppressed_objects_of'
```

The same command after the implementation: `19 passed`.

### Mutation run over the classification and the hints

There were 19 mutants. Each was applied to the committed source and run against
`test_status_mismatch_kinds.py`, `test_status_service.py` and `packages/debate_cli/tests` with
`-k status` (46 tests). Each run had its own new, empty `HYPOTHESIS_STORAGE_DIRECTORY`; none of these
tests uses Hypothesis, but the setting was applied as working agreement 8 requires. Each mutant was then
restored with `git checkout -- <file>`, and the script asserted `git status --porcelain` empty after
every one. It printed `tree clean after every mutant: True` for each of the three batches. Every
mutant applied (one match each), and none errored at collection.

| Mutant | Result | Caught by |
|---|---|---|
| Kind of every mismatch is `manifest` | CAUGHT, 4 failed | the source-only and both-kinds tests, core and CLI |
| Kind of every mismatch is `source` | CAUGHT, 5 failed | the manifest-only, complete-archive and both-kinds tests |
| `manifest_mismatched` is true for any mismatch | CAUGHT, 2 failed | source-only, core and CLI |
| `source_mismatches` includes the manifest key | CAUGHT, 7 failed | every manifest-mismatch test |
| Classify by a `manifests/` prefix instead of the snapshot's `manifest_key` | **SURVIVED (equivalent)** | none; see below |
| `manifest_mismatched` reads weekly manifest keys only | CAUGHT, 2 failed | the two complete-archive tests |
| `suppressed_objects_of` ignores the caselist | CAUGHT, 1 failed | `test_a_suppressed_object_is_told_under_the_caselist_whose_sources_it_is_among` |
| Publish hint names the first caselist only | CAUGHT, 1 failed | the two-caselist test |
| Publish hint dropped | CAUGHT, 5 failed | every manifest-mismatch CLI test |
| "Needs a person" hint also on a manifest mismatch | CAUGHT, 3 failed | manifest-only, complete-archive, as-a-person-reads-it |
| "Needs a person" hint dropped | CAUGHT, 2 failed | source-only, both kinds |
| "Completes what is missing" hint always shown | CAUGHT, 3 failed | manifest-only, as-a-person-reads-it, suppressed-object-only |
| Removal hint dropped | CAUGHT, 2 failed | both ac4 tests |
| Old wording ("N snapshot(s) differ" with N = 0) | CAUGHT, 1 failed | the suppressed-object-only test |
| Message omits the `manifest mismatch` label | CAUGHT, 4 failed | the manifest-mismatch CLI tests |
| JSON kind is always `source` | CAUGHT, 3 failed | manifest-only, complete-archive, both kinds |
| JSON gives a suppressed row's whole digest | CAUGHT, 1 failed | the ac4 table-and-JSON test |
| Table never says `differs` | CAUGHT, 1 failed | as-a-person-reads-it |
| Table drops the suppressed-object line | CAUGHT, 2 failed | both ac4 tests |

Each run took between 5.7 and 7.8 seconds. The prefix mutant survives because it is equivalent on every
input the service can produce. `checksum_mismatches` only ever holds the snapshot's own manifest key or
that snapshot's source keys, and every source key is under `raw/`. So `key == manifest_key` and
`key.startswith("manifests/")` agree on every reachable key. A test that tells them apart would have to
build a `SnapshotStatus` the service never builds, so I did not write one. The equality rule is still
the one implemented, as the PM asked: it matches this snapshot's manifest and nothing else, whatever
else `manifests/` holds.

### Full suite and static checks

The load average was checked before each part (`uptime`). Each part used the exact command
`uv run --frozen pytest -n auto -m "not slow and not live" --part K/4`:

| Part | Load average before (1, 5, 15 min) | Result |
|---|---|---|
| 1/4 | 11.81, 13.09, 9.13 | `1684 passed in 34.48s` |
| 2/4 | 27.51, 14.11, 8.77 | `1695 passed, 1 xfailed in 43.78s` |
| 3/4 | 20.79, 14.44, 9.18 | `1697 passed, 1 skipped, 1 warning in 33.63s` |
| 4/4 | 13.99, 13.54, 9.09 | `1694 passed, 1 xfailed in 35.90s` |

The load was high, from other work on this machine, and every part still finished under 45 seconds. An
earlier run of part 1 also passed (`1684 passed in 76.35s`, load 6.30), but it had `-p no:randomly`
added, so it was run again with the exact command.

| Check | Result |
|---|---|
| `uv run --frozen ruff format --check .` | `657 files already formatted` (after `ruff format` reformatted 2 of my files) |
| `uv run --frozen ruff check .` | `All checks passed!` |
| `uv run --frozen pyright` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 12 kept, 0 broken.` |
| `uv run --frozen python scripts/check_command_blocks.py` | `OK: no '#' comments in 248 shell code blocks in 113 Markdown files` |
| `uv run scripts/validate_specs.py` | `OK: 347 files, 38 epics, 289 tasks, 20 releases` |
| Neighbouring tests: `pytest packages/debate_core/tests/application/caselist tests/smoke/test_caselist_remove_smoke.py tests/smoke/test_caselist_publish_smoke.py -k "status or residue or republish"` | `79 passed in 13.97s`. This includes t10's and t15's residue tests and t08's re-import-then-publish test, all unchanged |

## Files changed

* `packages/debate_core/src/debate_core/application/caselist/status_service.py`: adds
  `MismatchKind` (`manifest`, `source`). `SnapshotStatus` gains `mismatch_kind(key)`,
  `manifest_mismatched`, `source_mismatches` and `incomplete`. `CaselistStatusReport` gains
  `manifest_mismatched`, `source_mismatched`, `caselists` and `suppressed_objects_of(caselist)`. The
  module docstring gains a section on the two kinds. What the comparison collects, and `in_sync`, are
  unchanged.
* `packages/debate_cli/src/debate_cli/commands/caselist.py`: the `CASELIST_DRIFT` message and hint, the
  new JSON fields, the table columns (`Manifest` can say `differs`, `Mismatches` became
  `Source mismatches`, and a `Suppressed rows` column was added), and the suppressed-object line under
  the table. The `caselist status` section of the module docstring says the same. The
  `REMOVAL_RESIDUE` branch and the residue lines are untouched.
* `packages/debate_core/tests/application/caselist/test_status_mismatch_kinds.py` (new): the
  classification and per-caselist suppressed objects, against moto with the real publisher.
* `packages/debate_cli/tests/test_caselist_publish.py`: the ac1, ac2 and ac4 command tests, and the
  JSON key-set test extended with the three new fields.
* `docs/runbooks/caselist-backfill.md`: removes the workaround sentence in the camp-metadata section and
  corrects the "`caselist status` shows drift" troubleshooting row to give one action per kind. The
  openev row below it now says "one manifest mismatch". The paragraph t17 edited around line 194 is
  untouched.
* `docs/runbooks/caselist-removal.md`: one bullet in "When `caselist status` reports removal residue"
  for the new `SUPPRESSED SOURCE OBJECTS` line. The bullets that t10 and t15 wrote are unchanged.
* `plan_specs/…/t12-status-names-manifest-mismatch.yaml`: Goal phase `Succeeded`.

## Deviations from the spec

1. **ac4's "each snapshot's … `suppressed_objects`" is reported per caselist.** `suppressed_rows` is a
   snapshot's: it comes from that snapshot's local manifest. `suppressed_objects` is not. The service
   finds them in one listing of each caselist's source prefix (`raw/caselist/<slug>/`, or `raw/openev/`)
   and keeps them on the report, not on a snapshot. A source object belongs to no single snapshot: one
   digest is filed once and named by any number of weeks. In `testcl26`, `harbor-octas-neg` is in two of
   the three. Some leftovers are named by no snapshot at all, such as a later upload whose manifest rows
   a removal already took (the ac4 test's case). Splitting them by snapshot would mean inventing an
   attribution. So the table shows them as one line per caselist under the table, with a count and
   prefixes, and the JSON has a top-level `suppressed_objects` with one entry per caselist compared.
   `CaselistStatusReport.suppressed_objects_of(caselist)` filters by the same prefix the listing used, so
   the split is exact rather than inferred. This is what the PM's brief asked for. I suggest rewording
   ac4 to: "each snapshot's `suppressed_rows` and each caselist's `suppressed_objects`".

## Decisions and assumptions

1. **The hint is right for both kinds of manifest rewrite, and for complete archives.**
   `CaselistPublishService._publish_manifest` uploads a listed manifest whose recorded digest differs from
   the local one, or has no recorded digest. That is what t08's republish test shows for the camp
   re-import. `plan()` reads snapshots with `full_archives=True`, so `caselist publish --caselist <slug>`
   includes the `full/<date>` snapshots. The two complete-archive tests run that exact command and then
   status exits `0`. For openev, the backfill runbook's own publish adds `--snapshot 2026-policy`, and
   the runbook now says it is the hinted command narrowed to one release.
2. **The hint is one sentence per kind found.** The old first clause, "`caselist publish` completes what
   is missing here.", is printed whenever a drifted snapshot is missing something: a manifest on either
   side, or a source on either side. That is the same set of cases it covered before, minus checksums. A
   run with only manifest mismatches therefore gets the publish sentence alone. A source mismatch keeps
   "needs a person".
3. **Suppressed rows and objects get their own hint**, pointing at the removal runbook's residue
   section. The old hint was wrong for them: publish withholds a manifest with a suppressed row
   (`MANIFEST_NAMES_SUPPRESSED_SOURCE`), and it cannot delete an object. The removal runbook's
   "Every snapshot agrees" route (`caselist remove --source <sha256>`) is the one that applies when only
   an object is left.
4. **Removed files are named by twelve characters in the new fields**: `suppressed_row_prefixes` and the
   `sha256_prefixes` of `suppressed_objects`, in the JSON and in the table text. This follows t10's
   Decision 6, where the PM asked for prefixes and counts for removed files, and it reuses
   `RESIDUE_DIGEST_PREFIX_LENGTH`. A mutant that printed the whole digest was caught. Digests of
   non-removed sources (`missing_sources`, `checksum_mismatches`) stay whole, as before.
5. **Codes and exit codes are unchanged.** A run with only a suppressed object is still
   `CASELIST_DRIFT`, exit `1`. Only its message changed. The `REMOVAL_RESIDUE` branch (residue found,
   every snapshot agreeing) is untouched in code, wording and exit code, and so are t15's lines.
6. **The table caption still begins "Every snapshot agrees."** when the only difference is a suppressed
   object, followed by the `SUPPRESSED SOURCE OBJECTS` line. That is literally true and matches how the
   residue lines already sit under it. The backfill runbook quotes **Every snapshot agrees** as part of a
   clean exit-`0` result, and that reading still holds.
7. **JSON compatibility.** Every existing field is kept with its name, type and order:
   `checksum_mismatches` is still a list of keys, and `suppressed` is still the excluded-source count.
   Added: per snapshot `mismatches`, `suppressed_rows` (a count) and `suppressed_row_prefixes`, and at
   top level `suppressed_objects`. **Nothing in the repo reads the old shape** apart from tests. I
   searched `packages/`, `scripts/`, `.github/`, `web/`, `clients/`, `infrastructure/` and
   `tests/smoke/`. The smoke tests read only `in_sync`, `exit_code`, `error.code` and
   `removal_residue`. The one exact key-set assertion, in `test_caselist_publish.py`, is extended rather
   than loosened. The scheduled pull (`caselist_sync.py`) uses the service objects, not the JSON, and
   reads only `in_sync` and `drifted`, which are unchanged.
8. **The tests' "legitimate rewrite"** writes the manifest's summary row again with other JSON
   separators: the same facts in other bytes, and no source changed. A real re-import or removal changes
   rows too, but status only compares digests, so the effect on the comparison is the same. t08's own
   test already covers a real re-import followed by a publish.
9. **The second caselist** in the ac1 test is `testcl27`, an invented slug holding the first synthetic
   week. Fixtures are synthetic only.

## Operator follow-ups

Nothing blocks the merge. After it merges, if you want to see the new output against dev, here is an
optional read-only check that uses your everyday profile, which is why I did not run it. Run it in this
worktree or any checkout of `dev` that includes the change, once the agent reinstall is finished. It
takes a few seconds per caselist.

```bash
cd "$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e30-t12-status-names-manifest-mismatch"
aws sso login --profile debate-dev-evidence
export DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev"
uv run debate-research caselist status --caselist openev
uv run debate-research caselist status
unset DEBATE_ENV DEBATE_STORAGE__DATA_DIR
```

What to expect: `--caselist openev` exits `0` with **Every snapshot agrees**, and the table now has
`Source mismatches` and `Suppressed rows` columns. The unscoped run exits `1` because of `testcl26`,
kept by PM decision as before. Its message now labels each `testcl26` snapshot with what differs, and
its hint gives one sentence per kind. Paste both outputs back if any label or hint looks wrong for what
you know of `testcl26`.

## Follow-up work

1. **Smoke check** (E30). Agreement 5 asks for smoke checks when a user-facing surface changes. This
   spec has no smoke node, and `tests/smoke/` is outside its packages, so I added none. The existing
   status smoke tests (`test_caselist_publish_smoke.py`, `test_caselist_remove_smoke.py`) pass
   unchanged. A `validate-dev` smoke covering a rewritten manifest, the publish hint and a clean status
   would cover this end to end.
2. **ac4's wording** (E30, spec only): see Deviations.
3. **A manifest mismatch in a snapshot that also has suppressed rows** gets both the publish sentence
   and the removal sentence. The publish then withholds that manifest, and its own message names
   `caselist remove`, so the operator is not misled for long. Saying "finish the removal first" in that
   one case would be more exact. It is a small change in `_drift_hints` if the PM wants it.
4. **The scheduled pull's report stage** records `CASELIST_DRIFT` per drifted snapshot with no kind
   (`caselist_sync.py`, the report stage). I did not check whether its retry-or-person notification
   treats a manifest mismatch as needing a person. Whether it should carry the kind is E34's question.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-14

**Notes:**

Accepted in full, with the phase `Succeeded`. I have amended ac4 in this branch to the wording
Deviation 1 proposes.

**Deviation 1 is right, and my ac4 was wrong.** A source object is found in one listing of the
caselist's source prefix, one digest can be named by several weeks, and some leftovers are named by
none. Reporting them per caselist, with `suppressed_objects_of` filtering by the same prefix the
listing used, is exact. Splitting them by snapshot would have invented an attribution.

**The work itself:**

* **Classification by equality with the snapshot's own manifest key,** as the brief asked. The
  prefix mutant surviving as equivalent is argued correctly: every reachable source key is under
  `raw/`, so the two rules agree on every input the service can build. The equality rule is still
  the one that stays right if that ever changes.
* **The publish hint is proven, not asserted.** The tests run the hinted command and then see
  status exit `0`, including for a complete archive.
* **Every existing JSON field is kept,** and the search for readers of the old shape is in the
  report. The scheduled pull reads only `in_sync` and `drifted`, which are unchanged.
* **Removed files appear only as prefixes in the new fields (Decision 4),** following `v1-e30-t10`'s
  ruling, and a mutant that printed the whole digest was caught.
* **t15's residue branch is untouched,** in code, wording and exit code.
* **The mutation run:** 18 of 19 caught, with the one survivor equivalent.

**Rulings:**

* **Deviation 1:** accepted. ac4 amended.
* **Decisions 1 to 9:** accepted. Decision 6, "Every snapshot agrees." followed by the
  suppressed-object line, matches how the residue lines already read.

**Follow-up work, filed by the PM in the next spec batch:**

* **Your 1 (a smoke check) and your 3 (finish the removal first)** join the E30 p3 task "residue
  clearing gaps". That task changes this command's residue output too, so one smoke check can cover
  a rewritten manifest, the publish hint, a suppressed row and a clean status.
* **Your 2:** done in this branch.
* **Your 4:** added to `v1-e34-t23`. The report stage should carry the kind, and a manifest
  mismatch should not be announced as needing a person.

**Operator follow-up:** the optional dev status check is folded into the status runs `v1-e30-t15`
left, after today's reinstall. In dev, expect `testcl26` drift labelled by kind, plus t15's
"NOT CHECKED against RM-2026-90".
