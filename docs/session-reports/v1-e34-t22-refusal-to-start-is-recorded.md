# Session report: v1-e34-t22-refusal-to-start-is-recorded

| | |
|---|---|
| Task | `v1-e34-t22-refusal-to-start-is-recorded` — A weekly run that cannot reach its bucket is recorded and announced, and the profile is checked before install |
| Spec | [`plan_specs/v1/e34-caselist-sync/t22-refusal-to-start-is-recorded.yaml`](../../plan_specs/v1/e34-caselist-sync/t22-refusal-to-start-is-recorded.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t22-refusal-to-start-is-recorded` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**Look at Deviation 1 first.** The profile check is `debate-research doctor --evidence-profiles`,
not plain `doctor`. Plain `doctor` is run by `scripts/install_channel.sh` on the `dev-prerelease`
runner and by `validate-dev`'s smoke checks, both on machines with no AWS config. A plain `doctor`
that failed on an undefined profile would fail every build there, in files this task may not edit.
ac3 passes with the option and not without it. I set the phase to `Succeeded` on that reading. If
you rule that plain `doctor` must make the check, the phase is wrong too.

What was built:

* A pull whose profile setting names no profile in the AWS config now leaves a `failed` record on
  this machine, details carrying `STORE_PROFILE_NOT_CONFIGURED` and the fix, which names the
  setting, and one `needs a person` notification with the adapter's hint. Its exit code is `1`, as
  before.
* That record is owed to the bucket. The next run that can build the bucket's adapter publishes it
  with its details: next week's pull, or `caselist pull --publish-pending`.
* `doctor --evidence-profiles` reports each configured evidence profile: whether it is defined and
  which permission set it is signed in as. It fails on one that is not defined. An expired session
  is reported as expired, with the login, and does not fail it.
* `ops/launchd/install.sh --check-launchd` runs the same check under launchd, through the
  wrapper's `--check`.
* The runbook has a *Reinstalling the agent* section, written for Wednesday's reinstall, with the
  check before the agent is replaced and under launchd after.

The run record has no new field, and neither do the details. All four criteria were shown failing
first and pass now. 65 mutants were run: 61 were caught on the first run and the other four are
dealt with under [Mutation results](#mutation-results).

**Synced onto `v1-e01-t27` at the end.** `dev` moved from `7efe8c6` to `50eae0d` after this report
was first written. I ran `scripts/task sync` and the whole suite again: 5,909 passed, 1 skipped.
One test this task does not touch failed once in that run and passes alone; see
[After the sync](#after-the-sync-onto-v1-e01-t27). Commit ids below are the rebased ones.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `refusal-recorded`: Refusal to start recorded; profiles checked | Done | `uv run pytest packages/debate_core/tests/application packages/debate_cli/tests -k "pull or doctor or profile"` → `452 passed in 28.58s` |

## Acceptance criteria

"Red" is two runs. The first was made before any implementation and is the branch's first commit,
`e398c51`: 62 failed, 171 passed across the nine new and changed test files. The second is the
finished tests against the source the task started from (`PYTHONPATH` on a `git archive` of that
source, which is `dev`'s at `7efe8c6`; the sync changed nothing under either package's `src`). My
first attempt at the second run passed every test, which is how I found that the
old source was not on the path; the figures below are from the run that printed the old source's
file name first.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** a pull whose profile the AWS config lacks writes a local record with status failed, details naming the code and the setting, and one notification that a person should look; shown failing first | PASS | Red, through the real composition root with boto3 refusing a real session: `8 failed, 2 passed`. No record (`ValueError: not enough values to unpack (expected 1, got 0)`), no details (`assert [] == [{... 'failure_codes': ['STORE_PROFILE_NOT_CONFIGURED'] ...}]`), no notification, nothing owed (`assert None == ['20260916T060000Z']`). The two that pass assert the exit code and that a dry run records nothing, neither of which changed. Green: `packages/debate_cli/tests/test_pull_refused_before_the_bucket_is_built.py` → `10 passed`. Smoke, red `2 failed`, green: `tests/smoke/test_caselist_pull.py -k "refused or names_no_profile"` passes |
| **ac2** the next run that can reach the bucket publishes that record and its details, and the older builds' readers still read every record, by v1-e34-t19's compatibility tests | PASS | Publishing: `test_the_record_is_owed_and_the_next_run_that_reaches_the_bucket_publishes_it_with_its_details` (the command, moto) and the smoke check where the week after a refused run imports, publishes and publishes both records. Compatibility: `packages/debate_core/tests/application/caselist/test_pull_run_record_is_read_by_every_build.py` → `67 passed` (61 before this task), including the five parametrized checks for the new stored scenario. See [Compatibility](#compatibility) |
| **ac3** `doctor` and `install.sh --check-launchd` report, for each configured evidence profile, whether it is defined and which permission set it is signed in as, and fail on one that is not defined; an expired session is reported and does not fail; by test with the identity stubbed at the port | PASS with `--evidence-profiles`; plain `doctor` does not make the check (Deviation 1) | Red: `15 failed, 1 passed` for `doctor` (`assert 2 == <ExitCode.DOMAIN_FAILURE: 1>`: no such option), and `17 failed` for the check itself, a module that did not exist. The one that passes is plain `doctor`, which is unchanged. Green: `test_doctor_evidence_profiles.py` → `16 passed`; `test_evidence_profiles.py` → `17 passed`. The launchd check: `tests/integration/test_launchd_install.py` → `68 passed` on this Mac; first red run, 9 failed. See [The launchd check off macOS](#the-launchd-check-off-macos) |
| **ac4** the runbook's reinstall steps run the check, and its troubleshooting replaces the workaround v1-e29-t07 described | PASS (Deviation 3 on the wording) | Red at `e398c51`: `6 failed` in `test_runbook_reinstall_runs_the_profile_check.py`. Green: `6 passed`. The test reads the runbook's command blocks in order and builds the banner the runbook quotes with the monitor's own code |
| Node criterion | PASS | `452 passed in 28.58s`, after the sync |
| Forbidden: a new field on the run record, or a record or details file an earlier build cannot read | PASS | The record model's schema still equals both older builds' stored schemas. No key was added to the details either: the refusal uses `failure_codes` and `hint`, which v1-e34-t19 defined. Mutants "the run record gains a field" and "the record keeps the error's code where its class was" were caught, by 43 and 12 tests |
| Forbidden: an account id, role ARN, SSO start URL or AWS config path in a record, notification, check output, log or the report | PASS | Asserted over the record, details, owed file, notification, envelope and captured logs for the refused pull, and over `doctor`'s output through the real STS adapter on moto, which answers with an account and a full identifier. Six mutants on this rule were caught. This report names none |

Full suite, on the final tree after the sync, as the three parts `v1-e01-t27` gave the default
selection (`uv run --frozen pytest --part K/3`, one command each):

| Part | Result |
|---|---|
| `--part 1/3` | `1953 passed in 39.18s` |
| `--part 2/3` | `1976 passed, 1 skipped in 59.85s` |
| `--part 3/3` | `1980 passed, 1 warning in 56.76s`, on its second run. The first: `1 failed, 1979 passed` |

The skip is the parser evaluation's existing one. Before the sync the suite ran twice by the three
path groups of earlier reports, the second time on what was then the final tree: 4,028, 564 and
1,299 passed with 1 skipped, both times.

Also clean: `ruff check .`,
`ruff format --check`, `pyright` (0 errors), `lint-imports` (12 kept), `check_thin_handlers.py`
(`doctor` holds 14 statements of 25), `validate_specs.py`, `docs_index.py --check-descriptions`,
`check_command_blocks.py --base origin/dev`, `check_links.py`, and shellcheck on both launchd
scripts, which the launchd tests run.

Coverage of the changed modules: `evidence_profiles.py` and `commands/doctor.py` are at 100%, and
no line this task changed in `sync_runs.py` or `container.py` is among the uncovered ones.

## Compatibility

The stored scenario is `a_refusal_to_start_published_by_the_next_run`: a refused run, then a pull
the week after that publishes its record. Like the other nine, its files were written by the
start commit's code (`0a9c1e6`), with the command in `stored_run_records/README.md`.

No older build ever recorded this run, because its monitor could not be built. So the older code
is handed the nearest thing it can be handed, and two things its source lacks are supplied to it:

* **The bucket.** Its monitor takes only a built bucket, so it gets one whose every call raises
  the refusal. This build's monitor is handed the bucket to build.
* **The error.** `0a9c1e6` predates `StoreProfileNotConfigured`. The generator defines a class of
  that name whose message is this build's, copied out by hand.

What is stored is therefore what the older build's recording code wrote when handed this failure:
its record model, its redaction, its run log and its publish of what is owed.

**Older builds reading this build:**

| Check | Result |
|---|---|
| This build's record schema equals the schema each older build printed | Equal to both |
| Each run-log line this build writes for the scenario validates against both older schemas and equals the older build's line, field for field and key order | 2 of 2 lines |
| The same for every object under `reports/sync-runs/`, and nothing else is there | 2 of 2 |
| The command, with boto3 refusing a real session, writes the stored line | Byte for byte |
| The generator run against this build's source instead of the older one's | Rewrote all 20 stored files and changed none |
| Regenerating with the older source | The 18 existing files unchanged; 2 new |

And the older build's own readers, run once over what this build's command wrote (a refused pull,
then `--publish-pending`, with the details file beside the run log and both prefixes in the
bucket):

```text
reader: ('start-commit', 'packages', 'debate_core', 'src') knows of details: False
run log: 2 of 2 line(s) read: [('20260916T060000Z', 'failed', 'StoreProfileNotConfigured'), ('20260923T060000Z', 'nothing_new', None)]
written back byte for byte: True
bucket: 2 of 2 record(s) read: [('20260923T060000Z', 'nothing_new'), ('20260916T060000Z', 'failed')]
the older reader asked the bucket for: ['list reports/sync-runs/', 'get reports/sync-runs/2026/20260923T060000Z.json', 'get reports/sync-runs/2026/20260916T060000Z.json']
warnings logged: 0 []
```

I did not run the installed build (`0.1.0.dev60`) for this, as v1-e34-t19 did, because the brief
says not to touch the installed agent. Its schema is the stored one, which is byte for byte the
start commit's, and every record here validates against it.

**This build reading older builds:**

| Check | Result |
|---|---|
| The stored run log reads whole, with no warning, and each record serialises back to the stored line | 2 of 2 |
| The stored bucket objects read through `read_remote_runs` and serialise back to the stored bodies | 2 of 2 |
| Each such run has `details` of `None` | 2 of 2 |

One known gap carries over from v1-e34-t19: if an *older* build publishes an owed record, it goes
up without its details. That applies to a refused run's record too, and it ends at the reinstall.

## After the sync onto `v1-e01-t27`

`scripts/task sync` rebased the nine commits with no conflict. `v1-e01-t27` changed the CI
workflow, `pyproject.toml`'s test settings, two scripts and the working agreements, and nothing
under either package's `src`, `ops/` or `docs/runbooks/`, which I checked with `git diff --quiet`.
I ran the suite by its new option, `--part K/3`, because the working agreements now give that as
the way to split a local run, and the default selection no longer measures coverage.

**One failure, in a test this task does not touch.** In the first run of part 3,
`test_caselist_parse.py::test_a_parse_past_the_time_limit_is_stopped_and_the_run_carries_on`
failed. It gives a two-worker parse pool a 1.5-second limit for each file and expects exactly one
`TIMEOUT`, so it depends on the wall clock. That run shared the machine with part 2's tail and a
polling loop of mine. Afterwards it passed alone three times of three, taking 2.5 to 6.2 seconds,
and part 3 passed whole when run by itself. I did not change the test. It is Follow-up 11.

After the sync I also ran the stored-record generator again against the older source: it rewrote
all 20 files and changed none. The static checks and the node's command were run again and pass.
The mutation runs and the red runs were made before the sync, on the same source.

## The launchd check off macOS

`install.sh --check-launchd` gains its profile check through what it already ran under launchd:
the installed wrapper's `--check`, which now runs `debate-research --version` and then
`debate-research doctor --evidence-profiles`, and ends with that command's exit code.

* **Proven on every platform.** The wrapper is POSIX shell and its tests are not skipped anywhere.
  Against the fake console script they show which commands it runs, in order, and that the profile
  check's exit code is the one it ends with (1, 2 and 70). Against this checkout's real command,
  with an AWS config written for the test, they show a profile that is not defined ending the
  check with `1` and naming the setting. That case needs no stub and reaches no network, because
  boto3 refuses the session before any request.
* **Proven on macOS only.** The installer's part: loading the one-off label, printing the log and
  exit code, booting out, failing on a non-zero exit, and saying what exit `2` means. Those tests
  need `plutil`, and CI runs on Linux, so they run only on the operator's Mac. They pass here.

I measured the difference. With the macOS-only tests deselected, the three wrapper mutants are
still caught and the two installer mutants survive (see the table below). Follow-up 1 would close
that.

## Mutation results

65 mutants, each run alone against the tests that should catch it, with a fresh
`HYPOTHESIS_STORAGE_DIRECTORY` (no property test is in these selections). The runner refuses a
dirty tree, restores each file from the bytes it saved and checks the tree is clean afterwards. It
classifies from pytest's summary line. No mutant errored before running.

| Area | Mutants | Caught on the first run |
|---|---|---|
| Refusal: not recorded | 2 | 2 |
| Refusal: not announced | 2 | 2 |
| Refusal: announced as retry | 3 | 3 |
| Refusal: not owed | 2 | 2 |
| Refusal: the details and the monitor | 4 | 4 |
| No path, account or identifier | 6 | 6 |
| Check: undefined passes | 6 | 6 |
| Check: expired fails | 5 | 5 |
| Check: the wrong permission set named | 8 | 8 |
| Check: which profiles are checked | 3 | 3 |
| `doctor`'s rows and panel | 4 | 3 |
| The takedown's wiring, which now shares the identity adapter's one construction | 2 | 1 |
| Compatibility of the refused run's record | 2 | 2 |
| The launchd check, on macOS | 5 | 5 |
| The launchd check, macOS-only tests deselected | 5 | 3 |
| The runbook | 6 | 6 |

The four that were not caught:

| Mutant | Result | What I did |
|---|---|---|
| `doctor`'s failure panel leaves out the line giving the setting and its profile | Survived | Nothing asserted the line, and the failure's sentence already names both. I removed the line; mutation could not tell it from its absence |
| The takedown's identity is asked under the everyday setting's name | Survived | Equivalent, and it was before this task. The takedown's S3 client is built first from the same profile and raises for a missing one, so the identity adapter's copy of the setting name is never read. Its sibling, asking the everyday *profile*, was caught by 11 tests |
| The installer does not say what exit code 2 means, macOS tests deselected | Survived | Expected: an installer test, macOS-only. Caught on macOS |
| The installer's check passes whatever the wrapper's check ended with, macOS tests deselected | Survived | The same. This guard is v1-e34-t10's, not this task's |

Two earlier simplifications also came from asking what mutation could tell apart, before the run:
the monitor no longer caches the bucket it builds, since it publishes once, and the everyday
profile is checked whenever the settings name one, with no separate condition on the bucket.

Two batches ran past two minutes (about 135 s and 125 s) because I sized them by the count of
mutants and not by their test selections. Both finished and restored the tree. The later batches
were smaller.

## Files changed

* **`debate_core.application`**
  * `sync_runs.py`: `SyncRunMonitor` takes `build_remote`, and a bucket that cannot be built leaves
    every record owed.
  * `evidence_profiles.py` (new): `EvidenceProfileCheck`, over the caller-identity port.
* **`debate_cli`**
  * `container.py`: the monitor is handed the bucket to build; `evidence_profile_check` and
    `caller_identity_for`, which the takedown access now uses too.
  * `commands/doctor.py`: `--evidence-profiles`, its rows and its failure.
  * `commands/caselist_pull.py`: docstring only. `README.md`.
* **`ops/launchd`**: `run-caselist-sync.sh` (the check runs the profile check), `install.sh` (the
  help text, and what exit `2` means).
* **Tests**
  * New: `test_pull_refused_before_the_bucket_is_built.py` in both packages,
    `test_evidence_profiles.py`, `test_doctor_evidence_profiles.py`,
    `test_runbook_reinstall_runs_the_profile_check.py`, and the stored scenario's two files.
  * Extended: `run_record_scenarios.py`, `write_stored_run_records.py`,
    `test_pull_run_record_is_read_by_every_build.py`, `stored_run_records/README.md`,
    `tests/integration/test_launchd_install.py`, `tests/smoke/test_caselist_pull.py`,
    `tests/smoke/test_cli_smoke.py`, `tests/smoke/README.md`, `test_app.py`.
* **Docs**: `docs/runbooks/caselist-scheduled-sync.md`, `docs/runbooks/evidence-store.md`.
* **Spec**: phase only.

`debate_core.integrations.s3` and `debate_core.integrations.local` are in the spec's packages and
were not changed: `StsCallerIdentity`, `takedown_permission_set` and `permission_set_of` are used
as they are.

## Deviations from the spec

1. **ac3: the check is `doctor --evidence-profiles`, and plain `doctor` is unchanged.** The spec
   says "`doctor` ... report ... and fail on a profile that is not defined". Plain `doctor` runs in
   three places where the environment's everyday profile is configured and no AWS config exists:
   * `.github/workflows/dev-prerelease.yml` runs `scripts/install_channel.sh`, which runs `doctor`
     and refuses the build if it fails;
   * `validate-dev`'s smoke check runs `doctor` against the installed pre-release with
     `DEBATE_ENV=dev` and an empty AWS config;
   * `test_app.py` runs `doctor` with the real settings loader, so on this Mac it would read the
     operator's AWS config and try to ask AWS.

   The first two would fail after the merge, where no session would see it, and I may not edit the
   workflows or `install_channel.sh`. So plain `doctor` loads no settings, reads no AWS config and
   reaches no network, as before, and a test and a smoke check hold it to that. The other way to
   meet the words is for plain `doctor` to make the check and for the installer and `validate-dev`
   to opt out, which needs those files changed in the same PR.
2. **Earlier tasks' tests changed.**
   * `v1-e29-t07`'s smoke check asserted that the refused run left no data directory. It now
     asserts the record, the details, the banner and the owed id.
   * `v1-e34-t10`'s wrapper test asserted that `--check` ran `--version` alone. It now asserts both
     commands in order, and the launchd check's test likewise.
   * `test_app.py`'s list of services gains `evidence_profile_check`.
   * `write_stored_run_records.py` supplied the missing error class as a stand-in with another
     name and message. It is now a faithful copy, because a scenario raises it.
3. **ac4 says the troubleshooting "replaces the `caselist runs --remote` workaround".** The
   runbook never contained that workaround; it was in v1-e29-t07's report and your notes on it.
   What the runbook said was that the exit code and the agent's log were the only signs. I
   replaced that, and a test fails if `runs --remote` appears in the section.
4. **The stored scenario's error is a hand-written copy for the older source**, as described under
   Compatibility. "Generated by the older code" is true of the record and not of the error object,
   which that code cannot produce.
5. **Two things run by hand that no criterion asked for.** `git fetch origin dev`, read-only, to
   check whether `dev` had moved. The third fetch found that it had, and I ran `scripts/task sync`. And this
   checkout's `doctor --evidence-profiles` once, against an AWS config and a profile directory
   written in the session's scratch directory, to read what a person is shown. Neither read the
   operator's AWS config or reached AWS.

## Decisions and assumptions

1. **The monitor's bucket is built lazily; there is no local-only path.** A local-only path needs a
   third state beside "a bucket" and "no bucket", because an environment with no bucket clears the
   list of records owed and this one must keep it. Handing the monitor a builder gives that state
   for free: the refusal reaches `watch` as the error the run stopped on, and publishing asks for
   the bucket, is refused, and keeps everything owed. `SyncRunHistory` already takes its bucket
   this way.
2. **Whatever stops the bucket being built is recorded, not only a missing profile.** The spec's
   description says "a run that cannot build its bucket". An error this project did not write is
   recorded by its class and no message, as it always was.
3. **`remote` stays, for a test with a bucket in hand.** Passing both is a `ValueError`.
4. **Nothing new in the details.** The code goes in `failure_codes` and the fix in `hint`.
5. **`doctor`'s failure code is `STORE_PROFILE_NOT_CONFIGURED`**, the code a command stopped by
   the same setting reports, and the hint is the adapter's.
6. **Only a profile that is not defined fails.** An expired session, an account that did not
   answer, and a profile signed in as an unexpected permission set are all reported and none fails.
7. **Permission-set names only, more strictly than v1-e29-t08.** A role that is no permission
   set's is said to be one and is not named, where `NotTheTakedownRole` names it.
8. **`takedown_permission_set` is used both ways.** The takedown profile signed in as anything else
   is told that `caselist remove --execute` will refuse it. The everyday profile signed in as the
   takedown's set is told so. The code knows no expected name for the everyday set, so it names the
   one it finds and the runbook says which to expect (Follow-up 4).
9. **`caller_identity_for` is the one place `StsCallerIdentity` is built.** The takedown access
   calls it too, with the same arguments as before.
10. **The launchd check runs through the wrapper, under launchd.** That is the environment the
    scheduled run has: the plist's `HOME`, `PATH` and `DEBATE_ENV`. `install.sh` itself does not
    run the check before it installs; the runbook's step 2 does (Follow-up 5).
11. **Exit `2` from the check is explained by the installer.** A build older than this task
    answers the option with a usage error, which is not a verdict on any profile.
12. **The check makes one call to AWS for each defined profile**, with botocore's own timeouts.
13. **The comparison with the stored record is exact, the message included.** A later change to
    that error's wording fails it. The stored README says to compare but for those words then, as
    v1-e34-t19 did for the refused publish.
14. **The runbook reads the agent's environment from its plist.** I first wrote `DEBATE_ENV=prod`
    into the blocks, which would have checked prod's profile for an agent installed as dev.
15. **The build to install is named in prose, not in a block**, because `<tag>` in a pasted zsh
    command is a redirection.
16. **The notification's wording is the existing one**: "stopped with StoreProfileNotConfigured",
    then the verdict and the fix. No new banner text was written.

## Operator follow-ups

Nothing has to be run for this task to merge. No test may ask the real account, so two rows are
worth reading at Wednesday's reinstall, and both are steps of the runbook's
[*Reinstalling the agent*](../runbooks/caselist-scheduled-sync.md#reinstalling-the-agent) (steps 2
and 5). They need a build that contains this task: an older build answers the option with exit `2`.

**Operator command** (expected runtime ~10 s)
Where: your Mac, any directory, after step 1 of the runbook has installed the new build

```bash
aws sso login --profile debate-prod-evidence
AGENT_PATH=$(plutil -extract EnvironmentVariables.PATH raw ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist)
AGENT_ENV=$(plutil -extract EnvironmentVariables.DEBATE_ENV raw ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist)
env -i HOME="${HOME}" PATH="${AGENT_PATH}" DEBATE_ENV="${AGENT_ENV}" sh -c 'debate-research doctor --evidence-profiles; echo "doctor exit=$?"'
```

The first line signs in to prod's everyday profile; use `debate-dev-evidence` if the agent runs as
dev. Success looks like: `doctor exit=0` and a row `Evidence profile` reading `debate-prod-evidence
(storage.s3.aws_profile): defined, and signed in as DebateProdEvidenceOperator`. If it reads
`signed in as a role that is no permission set's`, the account names its roles in a shape the
check does not expect: tell the PM, and paste the row. The check still passes in that case.

**Operator command** (expected runtime ~15 s)
Where: your Mac, in the main checkout on `dev`, after the runbook's steps 3 and 4

```bash
ops/launchd/install.sh --check-launchd
```

Success looks like: `exit code 0`, the version just installed, the same `Evidence profile` row in
the printed log, and the same `runs` count before and after.

v1-e34-t19's banner check (`osascript`) is still outstanding for the same day; it is in that
task's report and not repeated here.

## Follow-up work

1. **The installer's launchd-check tests never run in CI** (E34, p3). They need `plutil`. A
   `plistlib` stand-in for it, beside the fake `launchctl`, would let them run on Linux, and the
   two installer mutants above would then be caught there.
2. **`install.sh --aws-profile` does not choose the profile the run uses** (E34). It writes
   `AWS_PROFILE` into the plist, and the adapters build their session from
   `storage.s3.aws_profile`, which every dev and prod build sets. So a correct `--aws-profile`
   does not repair a wrong setting, and a wrong one is harmless. The option's help text reads as if
   it chose the profile.
3. **A refused run's record says "[redacted] lists the evidence profiles"** (E34, already filed
   with v1-e34-t23). The record's redaction takes the runbook the sentence points at for a path.
   The fix in the details is whole.
4. **`doctor` cannot say an everyday profile is the wrong environment's** (E29). No function gives
   the everyday permission set's name, so a prod agent signed in as dev's operator set is named
   and not remarked on.
5. **`install.sh` could refuse to install over a profile that is not defined** (E34). The task's
   title says "checked before install"; today that is the runbook's step, not the installer's.
6. **The identity question has no time limit of its own** (E29, p3). With AWS unreachable it waits
   for botocore's retries, and `--check-launchd` gives up after 60 seconds with "it had not
   finished".
7. **A dry run with a profile that is not defined creates the data directory and an empty
   database** before it is refused (E34, p3). It was so before this task: the service opens the
   database before it builds the bucket.
8. **Plain `doctor`'s tests warn that a socket was attempted** (E01, p3). pytest-socket says so
   for `test_app.py`'s two `doctor` tests, on the start commit too, and not on every run. The
   installed-build smoke check, which fails on any outbound call, passes.
9. **The refusal's banner names a class, `StoreProfileNotConfigured`** (E34, for v1-e34-t23's
   banner wording).
10. **Not proven here: that the real account answers as moto does.** The check rests on the same
    assumption as v1-e29-t08's preflight, that a permission set's role is named
    `AWSReservedSSO_<set>_<suffix>`. If it is not, `doctor` says "a role that is no permission
    set's" and still passes. The first operator command above shows which.
11. **A parse-timeout test depends on the wall clock** (E31, p3).
    `test_a_parse_past_the_time_limit_is_stopped_and_the_run_carries_on` allows 1.5 seconds a
    file and failed once here on a loaded machine. A healthy parse that takes longer than that
    is counted as a second `TIMEOUT`.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-13

**Notes:**

Accepted, with the phase `Succeeded`. I have amended ac3 and ac4 in this branch, so both pass as
written.

**Deviation 1 is right, and it caught a trap in my spec.** Plain `doctor` runs in the
dev-prerelease installer and in validate-dev's smoke check, on machines with no AWS config. Had it
made the profile check, the first push after this merged would have failed every build, where no
session would see it. ac3 now names `doctor --evidence-profiles`.

**Deviation 3 is my error.** The `runs --remote` workaround was only ever in my notes. ac4 now says
what the runbook actually replaced.

**The work itself:**

* **Lazy construction of the monitor's bucket (Decision 1)** is the smallest design that keeps
  the owed list. An environment with no bucket clears the list, and this one must keep it, which
  is the distinction that needed a third state. Handing the monitor a builder gives that state
  without adding one.
* **Recording whatever stops the bucket being built (Decision 2)** is better than special-casing
  the profile.
* **The compatibility evidence** follows `v1-e34-t19`'s method. It is honest about what the
  older code could and could not produce (Deviation 4), and regenerating changed no byte.
* **The red run:** you found that the old source was not on the path because every test passed,
  then fixed it and re-ran. That is the check that makes red mean something.
* **Decisions 6 and 7:** only an undefined profile fails, and only permission-set names appear.
  Both are the right scope for a check that runs before an install.

**Rulings:**

* **Deviations 1 to 5:** accepted. Deviation 5's two hand-run commands were inside the session's
  own worktree and scratch directory.
* **Decisions 1 to 16:** accepted. Decision 14 caught a prod check on a dev agent before it
  shipped.

**Follow-up work, filed by the PM in the next spec batch:**

* **One E34 p3 task, "agent install loose ends", for your 1, 2, 5 and 7:**
  * a `plistlib` stand-in so the installer's checks run in CI;
  * `--aws-profile`'s misleading help;
  * the installer refusing over an undefined profile;
  * a dry run that creates the data directory.
* **Your 4 and 6:** added to `v1-e29-t09`.
* **Your 9:** added to `v1-e34-t23`. Your 3 is already there.
* **Your 8:** goes to the E01 trim task.
* **Your 11, the wall-clock parse-timeout test:** goes to the E01 trim task as a flaky test to fix,
  not trim. It touches E31 code, which `v1-e31-t17` can absorb if it starts first.
* **Your 10** is checked at tomorrow's reinstall by your first operator command.

**Operator follow-ups:** both commands run at Wednesday's reinstall, from a build that contains
this task.
