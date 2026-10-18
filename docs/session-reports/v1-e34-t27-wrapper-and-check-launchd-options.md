# Session report: v1-e34-t27-wrapper-and-check-launchd-options

| | |
|---|---|
| Task | `v1-e34-t27-wrapper-and-check-launchd-options` — The wrapper exports no AWS_PROFILE, and --check-launchd refuses options it ignores |
| Spec | [`plan_specs/v1/e34-caselist-sync/t27-wrapper-and-check-launchd-options.yaml`](../../plan_specs/v1/e34-caselist-sync/t27-wrapper-and-check-launchd-options.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t27-wrapper-and-check-launchd-options` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**The wrapper no longer has its two `AWS_PROFILE` lines, and its comment says what becomes of one
set by hand.** A new test shows the scheduled run still reaching the store with the profile
`storage.s3.aws_profile` names. The test kickstarts the installed agent under the fake
`launchctl`. The console script is this checkout's real `debate-research`, run against moto, with
every socket refused.

**`--check-launchd` now accepts `--label` and refuses every other option by name.** The guard
used to list the four options it refused. It now lists the two it accepts, so an option added to
the installer later is refused until the check uses it. The test reads its cases from the
installer's argument loop, so a new option gets a case without anybody writing one.

The runbook says the wrapper changed, that `--check-launchd` refuses the agent until it is
reinstalled, and that the reinstall keeps Wednesday 06:00 by itself.

**ac3 is yours, after the merge:** a reinstall and then `--check-launchd`. The commands and what
success looks like are under Operator follow-ups. It is NOT RUN, so the phase stays `InProgress`.

**Look first at:**

* **Deviation 1.** `--debate-research` is refused too, although the spec names five options:
  the check ignored it the same way.
* **Decision 1.** The export never did anything, under launchd or in a shell, so the behavioural
  test of item (1) passes against the old wrapper as well. Only the test on the wrapper's code was
  red first.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `wrapper-and-guard` (Wrapper and guard) | Done | Node criterion passes. Two commits: the failing tests (`c1e9742`), then the scripts and the runbook (`95cc530`) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: (1) the wrapper sets no `AWS_PROFILE`, and a run under the fake launchctl still reaches the store with the setting's profile, by test | PASS | **`test_the_wrapper_sets_no_aws_profile`** holds the code: no line of the wrapper outside its comments names `AWS_PROFILE`, and the header no longer says it is exported. **Red first** at `c1e9742`, against the start commit's wrapper: `assert ['if [ -n "${... AWS_PROFILE'] == []`. **`test_a_scheduled_run_reaches_the_store_with_the_settings_profile_and_no_aws_profile`** has two cases, `as installed` and `with AWS_PROFILE added by hand`. Each case installs into a temporary HOME. The fake `launchctl` then bootstraps and kickstarts the agent's own label, running the plist's program with the plist's environment and nothing else. The console script at the path the plist names runs this checkout's `debate-research` in a dev installation written for the test. moto answers S3, every socket is refused, and the AWS config is the one under the temporary HOME. The script records three things: the environment the wrapper handed it, the profile of every boto3 session the run built, and the bucket's keys afterwards. With the OpenCaselist API off, the run is refused at its first guard, before any download, and the run monitor publishes its record to the bucket. The test checks that the run's argv is `--json caselist pull --caselist testcl26`, that every session named `debate-dev-evidence` (the setting), and that `reports/sync-runs/…` is in the bucket. It also checks, as installed, that the build was handed no `AWS_PROFILE`. With `AWS_PROFILE=someone-elses-profile` added to the plist by hand, the setting's profile still signs every session. Both cases **passed against the old wrapper too** (Decision 1). **Green:** `uv run pytest tests/integration/test_launchd_install.py` → `123 passed in 51.90s` |
| ac2: (2) each ignored option is refused by `--check-launchd` with the option named, by tests shown failing first | PASS | **`test_the_launchd_check_refuses_every_option_it_would_ignore_naming_it`**, one case for each option the installer's argument loop parses, except three: `--check-launchd` and `--label`, which the check takes, and `--aws-profile` and `--help`, which mean the same whatever else is given. That is 10 cases. Each case installs an agent and marks it loaded, then runs `--check-launchd` with the option. It checks four things: exit 2; the option named in the refusal, matched as a whole word; `--label` named as what the check takes; and nothing but `print` sent to `launchctl`, no call to the build, and the installed plist unchanged. **Red first** at `c1e9742` → `11 failed, 4 passed` (with the ac1 test above). `--weekday`, `--hour`, `--minute`, `--log-dir`, `--wrapper-dir` and `--debate-research` were ignored: the check ran and passed (`assert 0 == 2`; its log was printed). `--caselist`, `--env`, `--confirm-env-change` and `--dry-run` were refused but not named (`install.sh: --check-launchd takes no options but --label`). **Kept working:** `test_the_launchd_check_takes_the_label_of_the_agent_to_check` passes before and after. `test_the_options_are_read_from_the_installers_argument_loop` makes sure the five named options are among the cases, so a change in the loop's shape cannot empty them. **Green:** the same `123 passed`. Refusal as printed: `install.sh: --check-launchd takes no option but --label, and would ignore --weekday: it checks the installed agent as its plist stands. Nothing was checked. Run it without --weekday; a reinstall is what changes the agent` |
| ac3: Operator-run: after the merge, a reinstall and `--check-launchd` pass, recorded in the report | NOT RUN | It needs the real agent, which the spec forbids a session to read, and it can only run after the merge. The commands and what success looks like are under Operator follow-ups |
| Node `wrapper-and-guard`: `uv run pytest tests/integration/test_launchd_install.py` | PASS | `123 passed in 51.90s` (macOS, so both real-`plutil` tests ran). **Under dash:** both scripts' shebangs set to `/bin/dash`, the `/bin/sh` of CI's Ubuntu, then restored from git → `123 passed in 62.19s`, shellcheck and the committed-files test included |
| Default suite | PASS | Load average 15 to 80 during the run. `--part 1/4` hit the 115 s stop at 98% with no failure, so the suite ran as `--part K/8`, one part after another, each under a hard 115 s stop (agreement 1: the eight parts are the same selection). Results: `1025 passed` (65 s); `1028 passed` (61 s); `1 failed, 1025 passed` (69 s, see below); `1019 passed` (66 s); `1014 passed` (59 s); `1021 passed, 1 xfailed` (32 s); `1023 passed, 1 skipped` (61 s); `1022 passed, 1 xfailed` (42 s). **The failure** in 3/8 was `packages/debate_core/tests/application/test_caselist_parse.py::test_a_parse_past_the_time_limit_is_stopped_and_the_run_carries_on`, `{'TIMEOUT': 6}` against one expected timeout, at a load average of 30 to 80. This branch changes nothing in `packages/debate_core`. Alone → `1 passed in 3.30s`. Part 3/8 again at load 14 → `1026 passed` (50 s). Follow-up 1 |
| Static checks | PASS | Over the one changed Python file: `ruff format --check` → `1 file already formatted`; `ruff check` → `All checks passed!`; `pyright` → `0 errors` with `filesAnalyzed: 1`. `lint-imports` → `Contracts: 12 kept, 0 broken`. `shellcheck` 0.11.0 over both scripts → clean, here and inside the installer tests. `scripts/check_command_blocks.py` → `OK: no # comments in 279 shell code blocks`. `uv run scripts/validate_specs.py` → `OK: 366 files, 38 epics, 308 tasks, 20 releases` |

### Mutation results

The runner applied each mutant on its own, with a fresh `HYPOTHESIS_STORAGE_DIRECTORY`, and ran
only the tests written to catch it. No property test is in any of the selections. The runner
refuses a dirty tree, writes each file back from the bytes it saved, and checks the tree is clean
after every mutant. A mutant counts as caught only when pytest exits 1 with failures, and none
errored before running.

| Mutant | Selection | Result |
|---|---|---|
| The export goes back: the start commit's two lines, restored | ac1's two tests | Caught by `test_the_wrapper_sets_no_aws_profile` alone; the run test passes, as Decision 1 says it must |
| The wrapper exports a profile of its own (`AWS_PROFILE=someone-elses-profile`) | The run test | Caught: `[as installed]` fails. Every session still named the setting's profile |
| The check takes `--weekday` | The 10 refusal cases | Caught: 1 failed, `[--weekday]` |
| The check takes `--hour` | The same | Caught: 1 failed, `[--hour]` |
| The check takes `--minute` | The same | Caught: 1 failed, `[--minute]` |
| The check takes `--log-dir` | The same | Caught: 1 failed, `[--log-dir]` |
| The check takes `--wrapper-dir` | The same | Caught: 1 failed, `[--wrapper-dir]` |
| The check takes `--debate-research` | The same | Caught: 1 failed, `[--debate-research]` |
| The check takes `--caselist` | The same | Caught: 1 failed, `[--caselist]` |
| The check takes `--env` | The same | Caught: 1 failed, `[--env]` |
| The check takes `--confirm-env-change` | The same | Caught: 1 failed, `[--confirm-env-change]` |
| The check takes `--dry-run` | The same | Caught: 1 failed, `[--dry-run]` |
| The refusal does not name the option | The same | Caught: 10 failed. **The first version of this mutant survived (10 passed), because it was wrong:** the message names the option twice ("would ignore --weekday", "Run it without --weekday"), and it removed only the first. The corrected mutant removes both |
| A new option, `--timeout N`, added to the argument loop and not to the guard | `-k timeout` | Not a mutant but the property the PM asked for. The test collected a `[--timeout]` case nobody wrote, and it **passed**: the option is refused by default |
| The same new option, also accepted by the guard | `-k timeout` | Caught: 1 failed, `[--timeout]` |

## Files changed

* **`ops/launchd/run-caselist-sync.sh`**: the two lines that exported `AWS_PROFILE` are gone.
  The comment says the file does not set it, and that one set in a shell reaches the command like
  the shell's other variables and changes nothing.
* **`ops/launchd/install.sh`**
  * The argument loop records each option it is given, by name.
  * `--check-launchd` refuses every recorded option but itself and `--label`, naming it. This
    replaces the old four-variable guard, and its comment says why it lists what the check takes.
  * The `--check-launchd` help text says it takes no option but `--label`.
* **`docs/runbooks/caselist-scheduled-sync.md`**
  * Step 3's account of `--check-launchd`: an agent installed before a change to the wrapper is
    refused until it is reinstalled, and every option but `--label` is refused by name.
  * "Reinstalling the agent" opens with the `v1-e34-t27` change. It says what `--check-launchd`
    says until the reinstall, and that the reinstall keeps the schedule, Wednesday at 06:00 by
    default, with no schedule option.
  * Step 5 says to run the check as written.
* **`tests/integration/test_launchd_install.py`**
  * The ac1 tests and the ac2 tests.
  * `check_launchd` now passes extra arguments through to the installer.

## Deviations from the spec

1. **`--debate-research` is refused too, though the spec names five options.** The check ignored
   it in the same way: it reads `DEBATE_RESEARCH_BIN` from the installed plist and never used the
   option. The PM's note asks for the guard to be checked against every option the installer
   parses, and that check finds `--debate-research`. Accepting it would let `--check-launchd
   --debate-research <new build>` pass while checking the old one. `--caselist`, `--env`,
   `--confirm-env-change` and `--dry-run` were refused already; they are now refused by name.
   The spec's item (2) could read "every option but `--label`".
2. **Run by hand, not asked for by a criterion:** the installer under a scratch HOME in this
   session's scratchpad, to read the refusal and the help text; the dash run; the mutation runs.
   None read the real LaunchAgents, AWS config or data directory, and none reached AWS.

## Decisions and assumptions

1. **ac1's behaviour can't fail first, because the export never did anything.** A POSIX shell
   exports every variable it inherits from its environment. So `if [ -n "${AWS_PROFILE:-}" ];
   then export AWS_PROFILE; fi` changed nothing in any run: launchd sets no `AWS_PROFILE`, and a
   shell that sets and exports one hands it to the wrapper already exported. The run test
   therefore passes on both sides, and that is the evidence the lines could go. What keeps them
   gone is the test on the wrapper's code. It was red first, and it is the only test that catches
   the mutant that restores them. A wrapper that sets a profile of its own is caught by the run
   test.
2. **"Reaches the store" is shown with a run refused at its first guard.** A full pull needs
   OpenCaselist. With the API off, the run stops before any download, but it still builds the
   bucket's adapter and publishes its record there, as every refused run does since `v1-e34-t22`.
   That record in the moto bucket is the store reached. The profile is read from the sessions
   themselves, through a spy on `boto3.session.Session.__init__` in the console script, not from
   an error message.
3. **The run test's console script adds the installation's profile directory itself.** The
   installer writes only `DEBATE_ENV`, `HOME`, `DEBATE_RESEARCH_BIN` and `PATH`, and that is the
   whole environment the fake `launchctl` runs with. So the script records the environment the
   wrapper handed it first, and only then sets `DEBATE_PROFILE_DIR`. The AWS config is the one
   under the plist's `HOME`, which is where launchd's agent finds it.
4. **Refusing every option but two is a list of what the check takes.** It replaces a list of
   what it refuses, which had gone stale with the five options `v1-e34-t25` made meaningful. The
   argument loop records each option's name and not its value, because each branch shifts past
   its value, and an unknown option fails before the guard is reached.
5. **The refusal names the option twice and says what does change the agent:** "Run it without
   --weekday; a reinstall is what changes the agent". It exits 2, as the installer's other
   refusals do.
6. **The refusal tests run over an installed, loaded agent.** That is what makes the old
   behaviour visible as a check that ran and passed, rather than as "no agent is installed".
   Each case costs one install, about 0.5 to 2.5 s depending on load.

## Operator follow-ups

**ac3: a reinstall, then `--check-launchd`, after this merges into `dev`.** The agent runs dev,
follows hsld26, hspolicy26 and hspf26, and is scheduled for Wednesday at 06:00. It takes a minute
or two, plus the SSO login. Run it from a checkout that has the merged change.
`--check-launchd` compares the installed wrapper with that checkout's, so this branch's
worktree, or any checkout from before the merge, would not do. The first block makes a detached
worktree of `origin/dev` for it, which leaves the main checkout's branch alone; the last block
removes it. The build installed in `~/.local/bin` is kept: this task changes no build, so the
runbook's step 1 is not needed.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence
git fetch origin
git worktree add --detach ../debate-intelligence-worktrees/agent-reinstall-after-t27 origin/dev
cd ../debate-intelligence-worktrees/agent-reinstall-after-t27
git log -1 --format='%h %s' -- ops/launchd/run-caselist-sync.sh
```

The last line should name this task's merge commit, `v1-e34-t27-wrapper-and-check-launchd-options: …`.

Before the reinstall, the check should refuse the agent. This shows the runbook's sentence is
true, and it loads nothing:

```bash
ops/launchd/install.sh --check-launchd
echo "check exit=$?"
```

Expected: `install.sh: the installed agent's wrapper …/.local/share/debate-research/launchd/run-caselist-sync.sh is not this checkout's …/ops/launchd/run-caselist-sync.sh; reinstall with this script first`, then `check exit=2`.

The runbook's reinstall step 2, the profile check as the agent will run it:

```bash
AGENT_PATH=$(plutil -extract EnvironmentVariables.PATH raw ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist)
AGENT_ENV=$(plutil -extract EnvironmentVariables.DEBATE_ENV raw ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist)
aws sso login --profile "debate-${AGENT_ENV}-evidence"
env -i HOME="${HOME}" PATH="${AGENT_PATH}" DEBATE_ENV="${AGENT_ENV}" sh -c 'debate-research doctor --evidence-profiles; echo "doctor exit=$?"'
```

Success is `doctor exit=0` and the `Evidence profile` row reading `debate-dev-evidence
(storage.s3.aws_profile): defined, and signed in as DebateDevEvidenceOperator`.

Step 3, the reinstall, with no option but the build:

```bash
ops/launchd/install.sh --debate-research "$HOME/.local/bin/debate-research"
echo "install.sh exit=$?"
```

Success is these lines, then `Wrote …`, `Copied the wrapper to …/.local/share/debate-research/launchd/run-caselist-sync.sh`, the data directory it had, a note that the agent is already loaded, and `install.sh exit=0`:

* `Keeping the installed agent's environment, dev, from its plist's DEBATE_ENV (--env changes it).`
* `Keeping the installed agent's caselists: hsld26 hspolicy26 hspf26, from its plist's ProgramArguments (--caselist replaces them).`
* `Keeping the installed agent's schedule, Wednesday at 06:00, from its plist's StartCalendarInterval (--weekday, --hour and --minute change it).`
* `Keeping the installed agent's log directory, …/Library/Logs/debate-research, from its plist's StandardOutPath and StandardErrorPath (--log-dir changes it).`
* `Keeping the installed agent's wrapper directory, …/.local/share/debate-research/launchd, from its plist's ProgramArguments (--wrapper-dir changes it).`
* `The build's checks and its evidence profile pass as the agent will run them (debate-research doctor --evidence-profiles).`

Step 4, the reload:

```bash
launchctl bootout gui/$UID/com.debate-intelligence.caselist-sync
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist
launchctl print gui/$UID/com.debate-intelligence.caselist-sync
```

If `bootstrap` says `Bootstrap failed: 5: Input/output error`, run the bootstrap line again.
`print` should show the copied wrapper, `--caselist` hsld26, hspolicy26 and hspf26, a calendar
interval of Weekday 3, Hour 6, Minute 0, and `runs = 0`.

Step 5, the check under launchd:

```bash
ops/launchd/install.sh --check-launchd
echo "check exit=$?"
```

Success is the installed build's version in the log, the same `Evidence profile` row as in step
2, `com.debate-intelligence.caselist-sync.check exit code 0`, `Booted out
com.debate-intelligence.caselist-sync.check`,
`com.debate-intelligence.caselist-sync runs: 0 before, 0 after`, and `check exit=0`. Paste the
output of steps 3 and 5 back. Then remove the worktree:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence
git worktree remove ../debate-intelligence-worktrees/agent-reinstall-after-t27
```

## Follow-up work

1. **`test_a_parse_past_the_time_limit_is_stopped_and_the_run_carries_on` fails under heavy load**
   (E31, from `v1-e31-t06-parse-pipeline`). At a load average of 30 to 80 it saw six parses time
   out where one was meant to. It passed alone and in a re-run of its part. A time limit measured
   by the wall clock in a unit test makes the result depend on the machine's load. p3, unless CI
   has seen it too.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
