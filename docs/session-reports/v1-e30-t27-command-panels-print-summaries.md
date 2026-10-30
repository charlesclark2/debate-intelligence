# Session report: v1-e30-t27-command-panels-print-summaries

| | |
|---|---|
| Task | `v1-e30-t27-command-panels-print-summaries` — caselist publish, verify, parse and pull panels print a summary, not the whole record |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t27-command-panels-print-summaries.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t27-command-panels-print-summaries.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t27-command-panels-print-summaries` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Seven failure panels across four commands now print a summary through `panel_details`, as
`caselist status`'s have since `v1-e30-t24`: `caselist publish` (`PUBLISH_BLOCKED`,
`PUBLISH_INCOMPLETE`), `caselist parse` (`PARSE_FAILURE_RATE_EXCEEDED`,
`PARSED_PUBLISH_INCOMPLETE`), `caselist pull` (`CASELIST_PULL_INCOMPLETE`) and `verify`
(`UNVERIFIED`, `INVALID_MANIFEST`). Each panel prints counts, at most three twelve-character
prefixes per kind of digest and how many more there are, one line per snapshot or stage that
differs, and a closing line, `every value: in full under error.details of --json`. Status's helpers
moved into a new `debate_cli/panel_summaries.py`, and status and the four commands all use it.
Look first at the new `CommandFailure.panel_message` (Decisions 1). Publish's and pull's *messages*
joined every failed sha256 in full, and the panel prints the message. Changing the message would
have changed `error.message` in `--json`, so the panel prints its own message instead. Every
`--json` envelope is compared whole, byte for byte, with what the code wrote before any source
changed.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `panels` (Summary panels) | Done | Red tests and recorded envelopes committed first (`c7584f4`), then the implementation (`97e6c9a`). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: Each of the four commands' failure panels prints no whole sha256 and at most one line per differing caselist or snapshot, by tests shown failing first; each `--json` envelope keeps every field, by test | PASS | Red, against the code before the change (`c7584f4`): `.venv/bin/python -m pytest packages/debate_cli/tests/commands/test_publish_verify_parse_pull_panels.py -n 0 -p no:randomly --no-cov` → `26 failed, 12 passed`. Every whole-digest test failed for publish (both), parse (both) and pull. Every closing-line test failed, and so did every one-line-per-snapshot or per-stage test. The 12 that passed are the seven envelope tests, which guard "unchanged", and five checks today's panels already met. Green after the change: `38 passed`. With `test_caselist_status_panels.py`: `49 passed` after the sync. |
| `panels` node: CLI panel tests pass (`uv run pytest packages/debate_cli/tests -k "panel or publish or verify or parse or pull"`) | PASS | Run as `.venv/bin/python -m pytest` with the same arguments, under `perl -e 'alarm 115'` → `366 passed in 100.96s` (machine load about 15, from another session's process) |

### The tests

[`test_publish_verify_parse_pull_panels.py`](../../packages/debate_cli/tests/commands/test_publish_verify_parse_pull_panels.py)
builds each report by hand, as `test_caselist_status_panels.py` does, and calls each command's own
failure builder.

- **Every panel, for all seven failures:**
  - no whole sha256, and no hex run longer than twelve characters;
  - no bucket key and no path (`raw/`, `manifests/`, `parsed/`, `sha256/`, a `/Users/…` manifest
    path);
  - the closing line;
  - the `--json` envelope equal to the recorded one under
    [`failure_envelopes/`](../../packages/debate_cli/tests/commands/failure_envelopes/).
- **Per command:**
  - the exact line for each differing snapshot or failed stage, and no line for one that agrees or
    completed;
  - an exact line count: four lines every panel has, plus the command's count lines, plus one per
    thing that differs;
  - a kind with 40 digests names three and says `and 37 more`;
  - `v1-e34-t31`'s `caselist parse --caselist <slug> --publish-only` still printed whole in the pull
    panel's hint.

### Mutation runs

A scratchpad driver applied each mutant to committed source as one textual change. It refused a
dirty tree and any target not found exactly once. Each run had a new, empty
`HYPOTHESIS_STORAGE_DIRECTORY` (agreement 8; no property is in this selection), with
`-n 0 -p no:randomly -p no:cacheprovider --no-cov` under `perl -e 'alarm 100'`. Each file was
restored with `git checkout HEAD --` and the tree checked clean. The selection was the new module
plus `test_caselist_status_panels.py` (49 tests), which uses the moved helpers. None errored at
collection.

| Mutant | Result | First failing test |
|---|---|---|
| PM 1: parse's `PARSED_PUBLISH_INCOMPLETE` passes its whole payload to the panel | Caught, 4 failed | `test_it_prints_no_whole_digest[caselist parse, PARSED_PUBLISH_INCOMPLETE]` |
| PM 1: verify's `UNVERIFIED` passes its whole payload | Caught, 2 failed | `test_it_ends_by_saying_every_value_is_in_the_json[verify, UNVERIFIED]` |
| PM 1: pull passes its whole payload | Caught, 4 failed | `test_it_prints_no_whole_digest[caselist pull, …]` |
| PM 2: `digest_prefix` returns the whole digest | Caught, 12 failed | `test_it_prints_no_whole_digest[caselist publish, PUBLISH_BLOCKED]` |
| PM 3: publish's panel built in the payload dict itself, so the JSON details gain keys | Caught, 6 failed, both publish envelope tests among them | `test_the_json_envelope_is_the_one_written_before[caselist publish, PUBLISH_BLOCKED]` |
| PM 3: `INVALID_MANIFEST` drops `manifest` from details | Caught, 1 failed | `test_the_json_envelope_is_the_one_written_before[verify, INVALID_MANIFEST]` |
| PM 3: `publish_summary` renames `failed_sha256` | Caught, 2 failed | the two publish envelope tests |
| PM 4: the closing line missing | Caught, 13 failed | `test_it_ends_by_saying_every_value_is_in_the_json[…]` |
| PM 5: the three-prefix limit removed | Caught, 6 failed | `test_a_blocked_plan_prints_one_line_per_blocked_snapshot` |
| `PUBLISH_BLOCKED` without `panel_message`, printing every digest | Caught, 3 failed | `test_it_prints_no_whole_digest[caselist publish, PUBLISH_BLOCKED]` |
| Pull's stage reasons printed without shortening | Caught, 3 failed | `test_it_prints_no_whole_digest[caselist pull, …]` |
| Publish panel lists every snapshot, complete ones too | Caught, 1 failed | `test_an_incomplete_run_prints_one_line_per_incomplete_snapshot` |
| Verify counts verified cards in its per-snapshot lines | Caught, 1 failed | `test_unverified_cards_print_counts_and_one_line_per_snapshot` |
| `INVALID_MANIFEST` panel prints the manifest path | Caught, 2 failed | `test_it_prints_no_key_and_no_path[verify, INVALID_MANIFEST]` |

### Checks before the report

| Check | Result |
|---|---|
| Existing suites for the four commands, status and output: `test_caselist_publish.py`, `test_caselist_parse.py`, `test_caselist_parse_publish_only.py`, `test_caselist_parse_newer_fingerprint_table.py`, `test_verify_command.py`, `test_output.py`, `test_retryable_store_failures.py`, `test_app.py`, `commands/test_caselist_pull.py`, `commands/test_caselist_pull_parses.py`, `commands/test_caselist_pull_names_no_path.py`, `commands/test_caselist_status_panels.py`, `commands/test_caselist_residue_clearing_output.py` and the new module | `377 passed in 34.39s`. The first run had 11 failures in `test_caselist_pull.py`: its exit-code tests pass `{}` as the payload, and the pull panel read `environment` from it. The pull panel reads nothing from the payload now (Decisions 4). |
| Always-run list: `tests/architecture`, `tests/specs`, `test_app.py`, `test_help_rendering.py`, `test_container_factories.py` | `366 passed in 18.43s` |
| Smoke for these commands: `tests/smoke/test_caselist_parse.py`, `test_caselist_publish_smoke.py`, `test_caselist_pull.py`, `test_caselist_pull_in_process.py`, `test_cli_smoke.py`, `test_caselist_remove_smoke.py` | `87 passed in 93.85s` |
| Affected set, `uv run scripts/affected_tests.py` | **Not run; left to the pull request's `ci` check** (agreement 10). It chose `193 of 565 test files (34.2%)`. The whole selection is about six minutes on an idle Mac, so a third of it is near two minutes even then. Another session's process held the load at 12 to 16 throughout, and the node's 366 tests took 101 s against 35 s earlier. I ran the always-run list, the changed modules' suites and their smoke files instead (rows above). |
| `uv run --frozen ruff format --check .` | `1579 files already formatted` |
| `uv run --frozen ruff check .` | `All checks passed!` |
| `uv run --frozen pyright packages/debate_cli` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 18 kept, 0 broken.` |
| `uv run --frozen python scripts/check_thin_handlers.py` | `OK: 67 CLI command and API route handlers within 25 statements` |
| `uv run scripts/validate_specs.py`, after the phase was set | `OK: 492 files, 40 epics, 430 tasks, 22 releases` |
| Spec against `origin/dev` before the report | Unchanged apart from this branch's phase |
| Sync: `scripts/task sync` at the start (v1-e01-t39 had merged) and before the report (v1-e30-t28, which touches no `debate_cli` file) | Clean both times; the new tests and status's panel tests ran again after: `49 passed` |

## Files changed

- **`packages/debate_cli/src/debate_cli/panel_summaries.py`** (new): status's
  `_some_prefixes`, `_digest_prefix`, `_digest_of_key` and `_PREFIXES_SHOWN`, moved here, and three
  more helpers:
  - `shorten_digests`, which replaces a run of whole digests in a sentence with `some_prefixes` of
    the run;
  - `by_count`, codes with how often each came;
  - `every_value_in_full`, the closing line.
- **`output.py`**: `CommandFailure.panel_message`, which the panel prints in place of `message`.
  It is never in the JSON, like `panel_details`.
- **`commands/caselist.py`**: `_publish_failure` builds `panel_message` and `_publish_panel`, with
  one line per blocked or incomplete snapshot (`_what_blocks`, `_what_did_not_complete`). Status now
  uses the shared helpers. Its panel text is unchanged and still closes with `every digest: …`.
- **`commands/caselist_parse.py`**: both failures get `panel_details`.
- **`commands/caselist_pull.py`**: `panel_message` names the failed stages. `panel_details` has one
  line per failed stage, its reason with digests shortened.
- **`commands/verify.py`**: `UNVERIFIED` gets a panel with counts, reasons by code and one line per
  snapshot. `INVALID_MANIFEST`'s panel leaves out the manifest's path. The console-only swap of
  the payload for three counts is gone; the panel does that job now.
- **`packages/debate_cli/tests/commands/`**: the new test module, and seven recorded envelopes
  (42 KB) under `failure_envelopes/`.
- **Spec**: the Goal's phase.

## Deviations from the spec

None. Everything is inside `debate_cli` and its tests. Two choices the PM may want to look at
are Decisions 1 (a second `CommandFailure` field) and 2 (envelopes recorded from code, not written
by hand).

## Decisions and assumptions

1. **`panel_message`, beside `panel_details`.** `PUBLISH_BLOCKED`'s message ends with every blocked
   sha256, and `PUBLISH_INCOMPLETE`'s with `; failed sha256: …`. Pull's joins every failed stage's
   reason, and the publish stage's reason names each failed digest whole (`caselist_sync`, the
   `incomplete` sentence). The panel prints the message as its first line, so `panel_details` alone
   still left whole digests in those panels. Changing the message would change `error.message` in
   `--json`. So the message stays as it was, and the panel prints a counted version: `42 source(s)
   cannot be published as planned (…)`, `2 snapshot(s) not complete in the bucket; 41 source(s)
   failed`, `3 stage(s) of the caselist pull did not complete: publish, parse, report`.
2. **The envelopes are recorded, not written by hand.** Agreement 6 asks for hand-written
   expectations. Your notes asked for each envelope to be compared whole with "what today's code
   produces for the same failure". That is a recording of the code before the change, so I took
   it as the instruction for this case. The recording was made from `09c8b38`'s source with a
   throwaway test that was never committed, and committed in `c7584f4` with the red tests, before
   any source changed. A dropped, renamed or added key fails, as mutants 3 show.
3. **What "one line per thing that differs" is for each command:**
   - **publish:** a snapshot that is blocked (plan), or incomplete (applied run);
   - **parse:** one caselist and version per run, so its lines are counts;
   - **verify:** a snapshot that an unverified card names, plus one `no snapshot named` line;
   - **pull:** a failed stage. Pull's summary holds no per-snapshot record of a failed publish, only
     the stage's sentence. So each failed stage gets its reason on one line, digests shortened with
     `shorten_digests`. A stage reason is record-safe by rule 4 of the data-use policy (no school,
     team code or path), so whole digests were the only thing to remove.
4. **Pull's panel has no environment or bucket line.** The existing exit-code tests build the
   failure with an empty payload. The table printed above the panel already names the run and its
   environment. So the panel reads nothing from the payload.
5. **The digest limit is three per kind**, `caselist status`'s `PREFIXES_SHOWN`, now shared.
   Aggregates are named by file name (`occurrences.jsonl`), request ids whole (`RM-2026-09`), and
   verify's snapshots by their ULID. None of these is a digest, a school, a team code or a path.
6. **`VERIFICATION_COULD_NOT_RUN` is unchanged.** Its details are a card id, a position and an
   exception class name, which is not a whole record. `INVALID_MANIFEST` is in scope because its
   panel printed the manifest's path as given on the command line, which can be under a home
   directory.
7. **The red run for verify's `UNVERIFIED`** is at builder level, with the whole report as
   payload, as the command passes it in `--json`. Before this task, the console path swapped the
   payload for three counts before building the failure. So that panel already printed no digest,
   but it had no closing line and no per-snapshot lines, and those tests failed.

## Operator follow-ups

None. The affected set runs as the pull request's `ci` check.

## Follow-up work

1. **`caselist pull`'s table still prints the publish stage's reason whole** (E34). The stage row's
   Detail column, above the panel, is the same sentence the panel now shortens, with every failed
   digest in full. It is a table, not a panel, so I left it. `shorten_digests` would do it in one
   line in `_pull_table`.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
