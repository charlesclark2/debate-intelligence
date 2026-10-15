# Session report: v1-e34-t15-junk-release-leaves-inbox

| | |
|---|---|
| Task | `v1-e34-t15-junk-release-leaves-inbox` — A camp release of junk alone leaves the inbox once it is handled |
| Spec | [`plan_specs/v1/e34-caselist-sync/t15-junk-release-leaves-inbox.yaml`](../../plan_specs/v1/e34-caselist-sync/t15-junk-release-leaves-inbox.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t15-junk-release-leaves-inbox` |
| Session status | COMPLETE |

## Summary

Inbox retention has one new condition. A camp download leaves when no manifest row came from its
bytes and its id's delivery entry exists, names no member, and names these exact bytes as what the
id delivered. That is a camp release of junk alone, which the import handled and kept nothing from.
It leaves on the run that imports it. The summary names it `openev-960 sha256 <prefix>` with the
reason `junk_only`, never `not_imported`; the JSON entry carries `"openev_id"` and
`"reason": "junk_only"`. The next run's own stages show it handled: the select stage calls it
`already_imported`, nothing is fetched or read, and nothing is imported. Everything else is judged
exactly as before: a camp download with no entry, one whose entry names members, and every weekly
and complete archive. The run record's shape is unchanged. Its new content is only the text of the
retention stage's `reason`, and v0.1.0-dev.122's own readers, run from a `git archive` export, read
both records and both details lines. ac1 was committed red first. Eight mutants, including your
two, were each caught on the final tree. The phase is `Succeeded`.

**Read first:**
- Decision 1. I added one check beyond your condition: the entry must name **these bytes**. It only
  narrows removal, never widens it. A mutant without it is caught.
- Deviation 1. A `v1-e34-t08` test in t11's file pinned the old "kept as `not_imported`"
  behaviour. I inverted it in place. t11's own tests are unchanged.
- Operator follow-up: how many to expect, as two commands.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `junk-release-retention` — Junk-only camp releases leave the inbox | Done | Red tests `9b0c949`; the condition `2a6b36f`; test refinements `d1d0d0a`, `7749f4d`, `bc5a84b`; runbook `a743dae`. |

## Acceptance criteria

Code is final at `2a6b36f`. After it, only tests, the runbook and this report changed.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — After the run that imports a junk-only release, retention removes it and names it `sha256 <prefix>` with a reason distinct from `not_imported`; the next run neither downloads nor imports it. Shown failing first | PASS | **Red** on `9b0c949` against the unchanged code (output below). **Green:** `test_a_junk_only_release_leaves_on_the_run_that_imports_it_and_is_never_fetched_or_imported_again`, through `run_pull`, a real `SyncRunMonitor`, the fake source and moto. **First run:** `removed == [{"name": "sha256 97633cd06d14", "kind": "camp_download", "bytes": 684, "openev_id": 960, "reason": "junk_only"}]` and `kept == []`. The retention reason is exactly `1 file(s) removed, 684 bytes freed: 1 camp download(s), openev-960 sha256 97633cd06d14 (imported, and it held junk alone)`, in the summary, the record, the run log and the bucket's copy. Neither `not_imported` nor `not imported` appears in any of these: the JSON summary, the summary file, the record, the run log, the bucket's record, the details file, the bucket's details, the notifications or the log lines. **Next run, a week later, by its own stages:** the select decision is `already_imported`; `source.openev_fetches == [960]`, so no second fetch; `openev_downloaded == 0`; `files_imported == 0` and `files_skipped == 0`, so nothing was read; `snapshots_imported == ()`; `nothing_new`; retention is `skipped`, "the inbox holds nothing". **dev.122 reads it:** see below. |
| **ac2** — A camp download with no delivery entry, and a weekly archive, are kept exactly as before; t11's tests pass unchanged | PASS | **No entry**, two ways. The import failed, so no entry was written: kept as `not_imported`. The next run imports it from the inbox without fetching it, and only then is it removed. The entry was lost and upstream delisted the release: kept as `not_imported`. **Entry naming members, release not confirmed:** in one run against a bucket that confirms nothing, the weekly and the two-file camp release stay `not_confirmed`, and only the junk-only release goes. **Bytes other than the entry names:** kept as `not_imported`. **t11's tests:** `git diff c595638 HEAD -- …/test_inbox_retention.py` has one hunk, `@@ -763,23 +763,28 @@`, which is t08's test (Deviation 1). Every t11 test passes in the full run. |
| **ac3** — The new condition is mutated (any camp download with an entry removed, members ignored) and shown caught, and the runbook's inbox section says what leaves when | PASS | 8 of 8 caught on `a743dae` (table below), each with a fresh, empty `HYPOTHESIS_STORAGE_DIRECTORY`. Each was restored with `git checkout` and the tree checked clean. Runbook: [The download inbox](../runbooks/caselist-scheduled-sync.md#the-download-inbox) gains the junk-only condition, a "What leaves, and when" table, and how such a release is named. |
| Node: `uv run pytest packages/debate_core/tests/application/caselist -k retention` | PASS | `31 passed in 6.01s`: t11's tests, t08's inverted one, and this task's 7. Before the module was renamed, `-k retention` did not select it, giving `24 passed` (Decision 6). |

### ac1, shown failing first

On `9b0c949`, the unchanged code. Command:
`uv run --frozen pytest "packages/debate_core/tests/application/caselist/test_junk_release_leaves_the_inbox.py::test_a_junk_only_release_leaves_on_the_run_that_imports_it_and_is_never_fetched_or_imported_again" -n0 -p no:cacheprovider --no-cov -q`
(the module was renamed in `bc5a84b`):

```
E       AssertionError: the junk-only release stayed
E       assert [] == [{'name': 'sh...d': 960, ...}]
E         Right contains one more item: {'name': 'sha256 97633cd06d14', 'kind': 'camp_download', 'bytes': 684, 'openev_id': 960, ...}
packages/debate_core/tests/application/caselist/test_junk_release_leaves_the_inbox.py:207: AssertionError
1 failed in 0.56s
```

Everything before that assertion passed: one fetch, 3 files skipped and 0 imported. The release
stayed only because no retention condition removed it. The same commit, run with `-k junk` over the
new module and t11's file: `6 failed, 2 passed`. The 2 that passed are the two "no entry stays"
tests, which describe unchanged behaviour. My first draft expected `snapshots_imported == ()` on the
importing run. The run said `('openev 2026-policy',)`: the import writes and publishes the release
manifest even when it holds no row from these bytes. That is existing behaviour, so I corrected the
expectation, not the code.

### dev.122 reads a record carrying the new reason

`v0.1.0-dev.122` is `d87febd`. I exported its source with
`git archive v0.1.0-dev.122 packages/debate_core/src packages/debate_cli/src | tar -x -C <scratch>/dev122-src`.
I did not use the installed agent. The files this build wrote were the ac1 test's own run log and
details file, kept with `--basetemp`. A scratch script ran with
`PYTHONPATH="${S}/dev122-src/packages/debate_core/src:${S}/dev122-src/packages/debate_cli/src" uv run --frozen python -B read_with_dev122.py <evidence dir> <out>`.
It prints the module paths, so the imported code is shown to be dev.122's. It then:
- validates each line strictly with dev.122's `SyncRunRecord`;
- reads the run log and details file with dev.122's `SyncRunLog` and `SyncRunDetailsLog`;
- puts each record and its details into a local object store at the keys the monitor publishes
  them under;
- reads them back with dev.122's `SyncRunHistory.recent_runs`, locally and with `remote=True` (what
  `caselist runs` and `caselist runs --remote` call);
- renders them with dev.122's `caselist_runs._row`, `_parse_stage` and `_run_as_json`.

```
debate_core from <scratch>/dev122-src/packages/debate_core/src/debate_core/__init__.py
debate_cli from <scratch>/dev122-src/packages/debate_cli/src/debate_cli/__init__.py
run log: 2 line(s), 2 valid under this build's SyncRunRecord
SyncRunLog.read(): 2 record(s)
SyncRunDetailsLog.read(): details for ['20260916T060000Z', '20260923T060000Z']
  20260916T060000Z retention completed: 1 file(s) removed, 684 bytes freed: 1 camp download(s), openev-960 sha256 97633cd06d14 (imported, and it held junk alone)
  20260923T060000Z retention skipped: the inbox holds nothing
SyncRunHistory.recent_runs(remote=False): 2 run(s)
  row: ['20260923T060000Z', '2026-09-23 06:00', 'nothing_new', '0', '0', '0'] | parse: did not run
  row: ['20260916T060000Z', '2026-09-16 06:00', 'completed', '0', '0', '0'] | parse: did not run
  --json retention: [{"stage": "retention", "outcome": "completed", "reason": "1 file(s) removed, 684 bytes freed: 1 camp download(s), openev-960 sha256 97633cd06d14 (imported, and it held junk alone)"}]
SyncRunHistory.recent_runs(remote=True): 2 run(s)
  (the same two rows and the same retention entry)
```

"This build's SyncRunRecord" in the third line is the script's wording. The class it imported is
dev.122's, as the first line shows. I also diffed `StageEntry` and `SyncRunRecord` between the
export and this branch: they are identical. dev.122 would not refuse the new value, so the record's
shape was not touched. The first attempt had both runs on one run id (the installation's fixed
clock), and the second run's bucket objects overwrote the first's. The test's second run is now a
week later (`d1d0d0a`), which is also what the next scheduled run looks like.

### Mutation results

The harness is `mutate.py` in the session scratchpad, not the repository. It refuses to start
unless the tree is clean and `caselist_sync.py` matches `HEAD`. For each mutant it:
- makes exact text replacements, each of which must match once;
- runs `packages/debate_core/tests/application/caselist`,
  `packages/debate_core/tests/application/test_caselist_sync.py` and
  `packages/debate_cli/tests/commands/test_caselist_pull.py` (1243 tests, `-n auto`), with a new,
  empty `HYPOTHESIS_STORAGE_DIRECTORY` checked empty before the run;
- restores with `git checkout -- caselist_sync.py` and asserts that `git status --porcelain` is empty
  and the file matches `HEAD`.

Every run below is on `a743dae`, one mutant per command, at load averages of 8 to 29. No run errored
at collection, and no catch depended on a Hypothesis property. A first pass on `d1d0d0a`, which has
the same code, caught the same seven with the same tests.

| Mutant | What it does | Result | Failing for its reason |
|---|---|---|---|
| Your first: any camp download with an entry is removed | The condition hoisted out of "no row from its bytes" and reduced to `delivery is not None` | CAUGHT, 7 failed, 45.1 s | Deleted: the two-file release left `not_confirmed` (`assert {} == {… not_confirmed}`); the retry-hold copy (`assert {} == {… not_imported}`); the copy whose bytes differ. Mislabelled: files t11 expects as `no_delivery_record` or plain removals |
| Your second: members ignored | `delivery is not None and delivery.download_sha256 == digest` | CAUGHT, 1 failed, 63.2 s | t11's `test_retention_keeps_a_camp_download_waiting_for_its_import_although_the_record_holds_its_digests`: `assert {} == {'sha256 2b91…': 'not_imported'}`, the copy waiting for its retry deleted. This is the one reachable state where an entry naming members meets a copy no row came from (Decision 5) |
| The entry's digest not compared (mine) | `delivery is not None and not delivery.member_sha256` | CAUGHT, 1 failed, 67.1 s | `test_a_copy_whose_bytes_are_not_the_ones_the_entry_names_stays`: `assert {} == {… not_imported}` |
| No entry counts as none (mine) | `delivery is None or (…)` | CAUGHT, 4 failed, 46.6 s | Both of my no-entry tests (`assert {} == {… not_imported}`). Also t14's held copy (the test reads a file the mutant deleted: `FileNotFoundError`) and t12's refused import (`an inbox copy was fetched again`) |
| Reason collapsed to an ordinary removal (mine) | `RetentionDecision.JUNK_ONLY` → `REMOVE` | CAUGHT, 6 failed, 46.5 s | Every removal test: the entry lacks `"reason": "junk_only"` (`KeyError: 'reason'` in t08's inverted test, a dict mismatch in mine) |
| `junk_only` not a removal (mine) | `removes` returns true for `REMOVE` alone | CAUGHT, 6 failed, 46.5 s | By a `KeyError` in `_KEPT_BECAUSE`: the sentence has no kept wording for `junk_only`. So I ran the next row as well |
| The same, kept quietly (mine) | As above, plus a kept wording for `junk_only` | CAUGHT, 6 failed, 85.6 s | By assertion: `assert [] == [{… 960 …}]`, and in t08's inverted test `assert {'sha256 7f3b…': 'junk_only'} == {}` |
| The id not reported (mine) | `openev_id=one.openev_id` dropped from the verdict | CAUGHT, 5 failed, 70.9 s | `assert [{… 'junk_only'}] == [{… 'openev_id': 960 …}]` |

`members_ignored` is caught by one test, and it is t11's. I looked for a second reachable state and
found none (Decision 5).

### Checks on the final tree

| Command | Result |
|---|---|
| `uptime` before part 1 | load averages `23.19 22.18 18.28`; part 2 `44.60`, part 3 `31.75`, part 4 `30.00` (other sessions were running) |
| `uv run --frozen pytest -n auto -m "not slow and not live" --part 1/4` | `1729 passed in 76.27s` |
| `… --part 2/4` | `1740 passed, 1 xfailed in 41.93s` |
| `… --part 3/4` | `1740 passed, 1 skipped, 1 warning in 60.63s`. The skip is the parser eval waiting on human corrections. The warning is `pytest_socket`'s `A test tried to use socket.getaddrinfo` from `tests/smoke/test_smoke_harness.py`, which tries the network on purpose |
| `… --part 4/4` | `1738 passed, 1 xfailed in 69.17s`. The two xfails are the existing cite-detection label |
| `uv run --frozen ruff format --check .` / `ruff check .` | `667 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 12 kept, 0 broken.` |
| `uv run scripts/check_links.py` | `OK: 1528 relative links and anchors in 217 Markdown files` |
| `uv run --frozen scripts/check_command_blocks.py --base origin/dev` (with this report) | `OK: no '#' comments in 251 shell code blocks in 116 Markdown files (1 session reports changed since origin/dev)` |
| `uv run scripts/validate_specs.py` (after `set-phase … Succeeded`) | `OK: 348 files, 38 epics, 290 tasks, 20 releases`; `--require-succeeded v1-e34-t15-junk-release-leaves-inbox` → `Succeeded` |

The suite parts ran on `a743dae`. `bc5a84b` only renames the new test module, and the node criterion
above ran after it.

## Files changed

`git diff --stat c595638..HEAD`, report and spec aside: 4 files.

- **`debate_core.application`, `caselist_sync.py`:**
  - the condition, in `_judge_locally`'s camp branch;
  - `RetentionDecision.JUNK_ONLY` and `RetentionDecision.removes`;
  - `InboxFileVerdict.openev_id` and `_JudgedLocally.openev_id`;
  - `_REMOVED_BECAUSE` and `_by_decision`;
  - the removed half of `InboxRetention.sentence`, grouped by reason like the kept half;
  - `_named` names a junk-only release `openev-<id> sha256 <prefix>`;
  - `_JudgedLocally.kept_because` renamed `decision`, since it can now hold a removal;
  - "What leaves the inbox" in the module docstring, and the `RUN_SUMMARY_SCHEMA_VERSION` docstring
    (Decision 3).
- **Tests:**
  - `caselist/test_inbox_retention_of_junk_only_releases.py`: new, 7 tests;
  - `caselist/test_inbox_retention.py`: t08's junk test inverted (Deviation 1).
- **Docs:** `docs/runbooks/caselist-scheduled-sync.md`, "The download inbox". The junk-only release
  no longer appears among what stays. Added: its condition, a "What leaves, and when" table, and how
  it is named.
- **Spec:** Goal `Succeeded`.

`tests/smoke` was not touched.

## Deviations from the spec

1. **A `v1-e34-t08` test pinned the behaviour ac1 reverses, and I inverted it.**
   `test_retention_keeps_a_camp_release_of_junk_alone_and_the_next_pull_does_not_import_it_again`
   sits in t11's `test_inbox_retention.py`, but `git blame` gives every line to `f174ecb`
   (`v1-e34-t08`). It asserted `kept == {…: "not_imported"}` on both runs, which is what this task
   removes. I renamed it `…_removes_a_camp_release_of_junk_alone_…` in place, with the old name in
   its docstring. It now asserts the `junk_only` removal, and still that the next pull neither
   fetches nor imports. It was red on `9b0c949` (`assert {'sha256 7f3b…': 'not_imported'} == {}`).
   t11's own tests are untouched. ac2 is about t11's tests, so I read this as within it, but it is
   an edit to a test another task wrote.

## Decisions and assumptions

1. **The entry must name these bytes, not only exist with no member.** Your condition is "entry
   exists and names no member". I also require the entry's `download_sha256` to be the copy's
   digest. The entry is the only thing tying an inbox copy to a completed import. A file under
   `openev-960-…` holding other bytes (put there by hand, say) was never imported. t11's forbidden
   list rules out deleting it, and the next run will not import it either: its id is already
   `already_imported`. It stays as `not_imported`, the reason it had before.
   `test_a_copy_whose_bytes_are_not_the_ones_the_entry_names_stays` pins it, and mutant 3 is caught
   by it. This narrows removal and widens nothing. If you would rather have the condition as
   written, it is one clause.
2. **No bucket confirmation is asked for.** A junk-only release has no row, so there is nothing of it
   in the bucket to confirm. Its import still writes and publishes the release manifest, so
   `snapshots_imported` names `openev <release>` on that run (existing behaviour). Removing the copy
   does not depend on that publish. An environment with no bucket still skips the whole retention
   stage, as before, so its junk-only releases stay. I left that alone: changing it would be
   another retention condition.
3. **How the reason is carried.**
   - *Summary.* The removed entry gets `"reason": "junk_only"` and `"openev_id"`. Removed entries
     carried no `reason` before, and `kept[].reason` is unchanged. Under `v1-e34-t07`'s rule the
     summary stays at `RUN_SUMMARY_SCHEMA_VERSION` 5, and the constant's docstring now lists these
     keys. Nothing reads a summary back.
   - *Record.* No field changes. The reason is in the retention stage's existing `reason` string, as
     `(imported, and it held junk alone)` where a kept file would say `(not imported)`. dev.122
     reads it (above).
   - *Details.* By `v1-e34-t19`'s design, a run's details carry a stage only when it has error
     codes, a hint or earlier findings. A completed retention stage has none, so the details hold
     nothing about retention before or after this task. They never said `not_imported` and still do
     not. The ac1 test asserts both: `details.stage("retention") is None`, and neither phrase
     appears in the details file or the bucket's copy. I did not add a retention key to the
     details: nothing reads it, and the record's reason already carries it to every build.
4. **Naming.** In the sentence it is `openev-960 sha256 97633cd06d14`. The select stage writes
   `openev-640 (sha256 …)`, but here a bracket would sit beside the reason's own bracket. Nothing is
   read from inside the archive: retention hashes the file and reads the delivery record, and never
   opens the zip. The ac1 test's release holds a Word `~$` lock file naming an invented person,
   `Ottoline Probeworth-Vasquez`, in single-byte and UTF-16 text. Its title, folder and inbox name
   carry t12's probe word. A fixture test first checks the strings are really there. Then the
   holder's name, `Probeworth`, the probe word, the inbox file name, `~$` and `.DS_Store` are
   searched for, case-insensitively, in everything listed under ac1. None appears, on either run.
5. **Members ignored is caught by one test, and that is the only reachable state.** An entry naming
   members, with a copy from which no row came, arises when the rows were taken out by a removal,
   the file is unsuppressed, and its re-import fails. That is t11's retry-hold test. A removal
   deletes every inbox copy holding removed bytes, and an import that completes writes rows. So I
   found no second state to test that is not that one rebuilt by hand.
6. **The new module is named for retention.** It was `test_junk_release_leaves_the_inbox.py`, which
   the node's `-k retention` did not select. It is now `test_inbox_retention_of_junk_only_releases.py`.
7. **The second run in ac1 is a week later**, through `monkeypatch` of the installation's clock, as
   `run_record_scenarios.World.set_clock` does. With one run id for both runs, the details and the
   bucket would have held only the second.
8. **Your inbox and the agent were not touched.** Every run used a temporary data directory and moto.
   The dev.122 check read a scratch export of its source, never the installed tool.

## Operator follow-ups

After a build containing this change is installed for the agent (Reinstalling the agent, steps 1–3
of the runbook), and **before its next scheduled run**, count what that run should remove. Both
commands are read-only, finish in seconds, touch neither the network nor AWS, and print counts
only, never a file name. Run them in zsh: the `(N)` glob qualifier is zsh's. They assume the inbox
is `<data_dir>/inbox`, the default. The first three lines ask the installed build where its data
directory is, as the agent runs it.

**1. Count the junk-only releases the next run will remove.** (expected runtime: seconds)

Where: any directory on your Mac. It starts at `~` so that no checkout's build is used.

```zsh
cd ~
AGENT_PATH=$(plutil -extract EnvironmentVariables.PATH raw ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist)
AGENT_ENV=$(plutil -extract EnvironmentVariables.DEBATE_ENV raw ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist)
DATA=$(env -i HOME="${HOME}" PATH="${AGENT_PATH}" DEBATE_ENV="${AGENT_ENV}" sh -c 'debate-research --json config show' | jq -r '.data.settings["storage.data_dir"]')
echo "${DATA}"
n=0; while read -r id digest; do for f in "${DATA}"/inbox/openev-${id}-*(N); do [[ "$(shasum -a 256 "$f" | cut -d' ' -f1)" == "${digest}" ]] && n=$((n+1)); done; done < <(jq -r '.deliveries | to_entries[] | select(.value.member_sha256 == []) | "\(.key) \(.value.download_sha256)"' "${DATA}/caselist-sync-openev-deliveries.json"); echo "junk-only releases in the inbox: ${n}"
m=0; for f in "${DATA}"/inbox/openev-*(N); do id="${${f:t}#openev-}"; id="${id%%-*}"; jq -e --arg id "${id}" '.deliveries | has($id)' "${DATA}/caselist-sync-openev-deliveries.json" >/dev/null || m=$((m+1)); done; echo "camp downloads with no delivery entry: ${m}"
```

What the numbers mean:
- **`junk-only releases in the inbox: N`.** Exactly what the new condition removes: an entry naming
  no member, and a copy holding the bytes it names.
- **`camp downloads with no delivery entry: M`.** Copies the record does not know. Any of these that
  is a junk-only release still listed upstream is imported again by the next run, which writes its
  entry, so it leaves in that same run.
  `test_a_junk_only_release_whose_import_failed_has_no_entry_and_stays_until_an_import_writes_one`
  shows that path. The others stay as before.
- **What to expect from the next run:** between N and N + M junk-only removals, plus one for each
  junk-only release that run itself downloads. If `echo "${DATA}"` prints nothing, or jq says the
  deliveries file is missing, stop and paste the output back. A missing file means the record does
  not exist yet and N is 0.

Tested on a synthetic data directory: one entry naming no member with a matching copy, one naming
members, one whose copy holds other bytes, one with no copy, a copy with no entry, and a file under
`.partial/`. It printed `1` and `1`.

**2. After the next scheduled run** (expected runtime: seconds). Same shell, so that `DATA`,
`AGENT_PATH` and `AGENT_ENV` are still set:

```zsh
cd ~
LATEST=$(ls -t "${DATA}/caselist-sync-runs" | head -1)
jq '[.inbox_retention.removed[] | select(.reason == "junk_only")] | length' "${DATA}/caselist-sync-runs/${LATEST}"
jq '[.inbox_retention.kept[] | select(.reason == "not_imported")] | length' "${DATA}/caselist-sync-runs/${LATEST}"
env -i HOME="${HOME}" PATH="${AGENT_PATH}" DEBATE_ENV="${AGENT_ENV}" sh -c 'debate-research --json caselist runs --last 1' | jq '.data.runs[0].stages[] | select(.stage == "retention")'
```

Success looks like:
- the first number is between N and N + M from follow-up 1;
- the second number has dropped by the same amount since the previous run;
- the retention stage is `completed`, and its reason has a group ending
  `camp download(s), openev-<id> sha256 <12 hex>, … (imported, and it held junk alone)`, with no
  camp title or file name;
- the run after that names none of those ids as `junk_only` again, and its select stage calls them
  `already_imported`.

Paste the three outputs back.

## Follow-up work

None. Decision 2 names one thing left as it was: an environment with no bucket keeps its junk-only
releases, because the whole retention stage is skipped there. I do not think it needs a task: the
agent runs with a bucket.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-14

**Notes:**

Accepted in full, with the phase `Succeeded`. The spec is unchanged.

**Decision 1 makes the condition better than I wrote it.** Requiring the entry to name these
bytes only narrows removal: a file under a junk release's name holding other bytes was never
imported, and t11's forbidden list keeps it. It is pinned, and its mutant is caught.

**The work itself:**

* **ac1 is shown through the pull's own stages,** as the brief asked: the next run's select calls
  the id `already_imported`, nothing is fetched or read, and nothing is imported. Running the second
  run a week later, so the two records do not share a run id, is what made that evidence real.
* **dev.122's own readers read the new reason** from both records, locally and from the bucket, and
  `StageEntry` and `SyncRunRecord` are identical to dev.122's. The record's shape was rightly left
  alone.
* **The lock-file probe,** a name in single-byte and UTF-16 text, checked present in the fixture
  first and then absent from every output, is the right test of "nothing read from inside the
  archive".
* **The mutation run:** 8 of 8 caught, my two included. Decision 5, that "members ignored" has one
  reachable state and it is t11's retry-hold test, is argued, and I agree.

**Rulings:**

* **Deviation 1:** accepted. The test you inverted was t08's, pinning exactly the behaviour ac1
  reverses; t11's own tests are unchanged.
* **Decisions 1 to 8:** accepted. Decision 2, no bucket meaning no retention stage, needs no task.

**Operator follow-up:** both counts wait for the first install of a build carrying this change.
The agent runs `v0.1.0-dev.122`, which predates it; the next install follows the combined re-parse.
The PM records the counts then.
