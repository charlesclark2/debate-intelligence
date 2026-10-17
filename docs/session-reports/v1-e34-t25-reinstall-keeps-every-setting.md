# Session report: v1-e34-t25-reinstall-keeps-every-setting

| | |
|---|---|
| Task | `v1-e34-t25-reinstall-keeps-every-setting` — A reinstall keeps the agent's schedule and options, and doctor names a takedown profile's environment |
| Spec | [`plan_specs/v1/e34-caselist-sync/t25-reinstall-keeps-every-setting.yaml`](../../plan_specs/v1/e34-caselist-sync/t25-reinstall-keeps-every-setting.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t25-reinstall-keeps-every-setting` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

A reinstall over an installed agent now keeps its schedule, its log directory and its wrapper
directory, as `v1-e34-t24` did for the environment and caselists. `ops/launchd/install.sh` reads
each from the installed plist (`StartCalendarInterval`, `StandardOutPath` and
`StandardErrorPath`, `ProgramArguments.0`). It says what it kept and which key it read it from,
on stderr for a dry run, so `Wednesday at 06:00` can be read straight off the output. An explicit
option still changes its setting, and the installer says from what to what. A first install still
takes the defaults. A value the plist does not hold as the installer writes it is refused, naming
the key and the option to give, and is never replaced by the default. Examples: an hour stored
as a string, a missing minute, a weekday of 0, two calendar intervals, logs in two directories.

The wrapper's comment no longer says `AWS_PROFILE` is templated into the plist. `install.sh`'s
comment on the profile check says the AWS question waits at most 10 seconds. `doctor
--evidence-profiles` now says whose set a takedown profile from the other environment is signed
in as, in the everyday profile's words.

**The phase stays `InProgress`, because ac4 is the operator's** dry run over the real agent (your
note, and the spec's forbidden list). Every other criterion passed. Look at Deviation 1 first: the
doctor sentence is built in `debate_core`, which is not in the spec's package list.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `reinstall-settings` (Reinstall keeps every setting) | Done | Node criterion passes. Four commits: the failing installer tests; the installer, the stand-in and the two comments; doctor and the runbook; formatting |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a reinstall without the options keeps each from the installed plist, and an explicit option still changes it, by tests against a fake launchctl and a scratch plist, shown failing first | PASS | Seven new tests (17 cases) in `tests/integration/test_launchd_install.py`, section "A reinstall keeps the schedule and the other options too". Each runs the installer under a temporary HOME, with the fake `launchctl` and the `plutil` stand-in first on its PATH. **Red first**, at commit `3737cf9` against the start commit's installer: `15 failed, 2 passed`. The two that passed pin behaviour that does not change: a first install takes the defaults, and an option repeating the installed value says nothing. The failures were the intended ones. A Thursday 07:30 agent came back as `{'Weekday': 3, 'Hour': 6, 'Minute': 0}`, the dry run had no `Keeping the installed agent's schedule` line, and every unreadable value was installed rather than refused. **Green:** `uv run pytest tests/integration/test_launchd_install.py` → `108 passed in 36.72s`, macOS, so both real-`plutil` tests ran. The same file with both scripts' shebangs set to `/bin/dash`, the `/bin/sh` of CI's Ubuntu, then restored from git → `106 passed` (shellcheck and the committed-files test left out). **The stand-in** learned `plutil -extract … raw -expect <type>`. `test_the_plutil_stand_in_answers_as_plutil_does` holds it to the real `plutil` over nine new steps: a match, a mismatch, a missing key, a dictionary, an array, and an hour replaced by a string. **Mutants:** 14 of 14 installer mutants caught (below) |
| ac2: (2) and (3), the comments say what the code does | PASS | `test_the_wrapper_says_the_installer_writes_into_the_plist_only_what_it_writes` checks two things: every variable the wrapper's comment lists as written into the plist is in a rendered plist, and `AWS_PROFILE` is said not to be. `test_the_installers_comment_on_the_profile_check_says_how_long_the_aws_question_may_wait` checks that the comment above the profile check names `IDENTITY_TIME_LIMIT_SECONDS` and its value, which it reads from `caller_identity.py`. **Red first**, with the start commit's two scripts written back and then restored from git: `2 failed`. The failures were `AssertionError: ['DEBATE_ENV', 'AWS_PROFILE', 'DEBATE_RESEARCH_BIN']` and `assert 'IDENTITY_TIME_LIMIT_SECONDS' in "The build's own checks …"`. Green → both pass |
| ac3: (4), doctor names the other environment's removal set for a takedown profile, by test | PASS | In `debate_core`: `test_a_takedown_profile_signed_in_as_the_other_environments_set_is_told_whose_set_it_is`, three cases: prod's takedown set in dev, dev's in prod, and prod's everyday set in dev. In the CLI: `test_a_person_sees_whose_takedown_set_a_removal_profile_from_the_other_environment_is_signed_in_as`, which checks the row a person sees and the JSON. The row reads `debate-dev-evidence-removal (DEBATE_REMOVAL_PROFILE): defined, and signed in as DebateProdEvidenceRemoval, which is prod's takedown permission set and not dev's; a takedown runs only as DebateDevEvidenceRemoval, so caselist remove --execute will refuse this profile`. The test also checks that no account id, ARN, address or role name is in the output. **Red first:** `5 failed, 37 passed`, including t22's `test_the_takedown_permission_set_is_the_environments`, whose expected sentence now carries the clause (Deviation 2). Green → `42 passed`. Mutants: 2 of 2 caught |
| ac4: Operator-run: `install.sh --dry-run` over the real agent shows Wednesday 06:00 and the current options kept, recorded in the report | NOT RUN | The session may not read the real agent (spec, forbidden list). The command and what success looks like are under Operator follow-ups. The same shape is shown offline: `test_an_agent_installed_with_the_defaults_is_reinstalled_with_them_and_says_wednesday_at_06_00`, and a dry run over a scratch dev agent following hsld26, hspolicy26 and hspf26, which printed `Keeping the installed agent's schedule, Wednesday at 06:00, from its plist's StartCalendarInterval (--weekday, --hour and --minute change it).` |
| Node `reinstall-settings`: `uv run pytest tests/integration/test_launchd_install.py` | PASS | `108 passed in 36.72s` |
| Default suite, in four parts | PASS | `uv run pytest --part K/4`, one after another, each under a hard 115 s stop. The load average was 16 to 21 at the time. Results: `1934 passed` (73 s); `1941 passed, 1 xfailed` (68 s); `1944 passed, 1 skipped` (61 s); `1941 passed, 1 xfailed` (77 s). The warnings come from the network-guard tests, which trip the socket block on purpose |
| Static checks | PASS | Over the five changed Python files: `ruff format --check` → `5 files already formatted`; `ruff check` → `All checks passed!`; `pyright` → `0 errors`. `lint-imports` → `Contracts: 12 kept, 0 broken`. `shellcheck` over both scripts, inside the installer tests. `scripts/check_command_blocks.py` → `OK: no # comments in 276 shell code blocks`. `uv run scripts/validate_specs.py` → `OK: 362 files, 38 epics, 304 tasks, 20 releases` |

### Mutation results

Each mutant ran alone, with a fresh `HYPOTHESIS_STORAGE_DIRECTORY`, against the tests written to
catch it. For the installer that is the seven new tests (17 cases); for doctor, both evidence-profile
files. No property test is in either selection. The runner refuses a dirty tree, writes each file
back from the bytes it saved, and checks the tree is clean after every mutant. It ran in four
batches, each under a hard 115 s stop. A mutant counts as caught only when pytest exits 1 with
failures. None errored before running.

| Mutant | Result |
|---|---|
| The installed weekday is not kept (the default instead) | Caught, 7 failed |
| The installed hour is not kept | Caught, 7 failed |
| The installed minute is not kept | Caught, 6 failed |
| The installed log directory is not kept | Caught, 6 failed |
| The installed wrapper directory is not kept | Caught, 7 failed |
| A setting that cannot be read is replaced by the default, not refused | Caught, 6 failed |
| An hour held as a string is read as a number (no `-expect integer`) | Caught, 1 failed |
| An installed weekday outside 1 to 7 is kept | Caught, 1 failed |
| Logs in two directories are read as the first one's | Caught, 1 failed |
| A wrapper of another name is kept | Caught, 1 failed |
| An explicit `--hour` is ignored over an installed agent | Caught, 1 failed |
| An explicit `--log-dir` is ignored over an installed agent | Caught, 2 failed |
| The kept schedule is not said | Caught, 3 failed |
| A kept wrapper directory's refusal does not say which option moves it | Caught, 1 failed |
| Doctor does not say whose set a takedown profile is signed in as | Caught, 5 failed |
| Doctor calls every other environment's set a takedown set | Caught, 1 failed |

## Files changed

* **`ops/launchd/install.sh`**
  * Reads the schedule, the log directory and the wrapper directory from an installed plist, with
    a helper for each that either returns the value or says why it cannot be read back.
  * Keeps each one no option gives, and refuses one it cannot read.
  * Says what it kept and which key it came from. The environment and caselists lines name their
    key too.
  * Says a change from what to what.
  * Checks the schedule options as given before it reads the plist, without leading zeros, and
    trims a trailing `/` from the two directories.
  * A kept directory that is refused says which option moves it.
  * Header, help text, and the profile check's comment.
* **`ops/launchd/run-caselist-sync.sh`**: the comment on its environment, only. Its code is
  unchanged.
* **`debate_core`**: `application/evidence_profiles.py`. A takedown profile signed in as the other
  environment's set is told whose it is (Deviation 1).
* **`docs/runbooks/caselist-scheduled-sync.md`**
  * The doctor rows.
  * Step 2's note on reinstalls and the schedule options.
  * The reinstall's step 3: it shows `StartCalendarInterval` from the plist first, quotes the five
    `Keeping …` lines, and covers an option given and a value that cannot be read.
* **Tests**
  * `tests/integration/test_launchd_install.py`: the ac1 and ac2 tests, and the stand-in's
    `-expect` with its steps against the real `plutil`.
  * `packages/debate_core/tests/application/test_evidence_profiles.py`
  * `packages/debate_cli/tests/commands/test_doctor_evidence_profiles.py`
  * `packages/debate_cli/tests/test_runbook_reinstall_runs_the_profile_check.py`: the runbook
    quotes the new sentences, and the reinstall shows the schedule and types no schedule option.

The spec is unchanged; its phase stays `InProgress`.

## Deviations from the spec

1. **`packages/debate_core` was changed, and it is not in `constraints.packages`.** The sentence
   `doctor` prints is built in `debate_core.application.evidence_profiles`, beside the everyday
   profile's sentence that item (4) says to match. CLAUDE.md keeps that logic in `debate_core`, so
   building it in `debate_cli` would have split one sentence across two packages. The change is 14
   lines plus its test. The spec's `packages` could gain `packages/debate_core` (both the source
   and its tests).
2. **Earlier tasks' expectations changed.**
   * `test_the_takedown_permission_set_is_the_environments` (t22, extended in e29-t09): its "wrong"
     case, a dev takedown set in prod, now expects the new clause.
   * t24's "Keeping …" sentences for the environment and the caselists now end with the key they
     came from. t24's tests match the start of the sentence, so they pass unchanged. The runbook
     quotes the new form.
   * t24's comparison of the stand-in with the real `plutil` gained nine steps.
3. **Changing the wrapper's bytes makes `--check-launchd` refuse the installed agent until the next
   reinstall.** It compares the installed copy with the checkout's. t24 left the comment alone for
   this reason (its Decision 11). The spec now asks for the comment. See Operator follow-ups.
4. **Run by hand, not asked for by a criterion:**
   * real `plutil` over scratch plists in this session's scratchpad, to learn how `-expect`
     answers;
   * the installer over a scratch HOME, to read its notes;
   * the dash run;
   * the mutation runs.

   None read the real LaunchAgents, AWS config or data directory, and none reached AWS.

## Decisions and assumptions

1. **The plist is read with `plutil -extract … raw -expect integer|string`.** Without `-expect`, a
   `<string>7</string>` hour reads back as `7` and would be rewritten as an integer: a change
   nobody asked for, in a value launchd may not have honoured. Real `plutil` refuses the type
   mismatch. The stand-in does the same, word for word, and the macOS comparison test proves it.
2. **"Cannot be read" means "does not read back as a value this script writes."** That covers:
   * a missing key (launchd treats a missing `Minute` as every minute);
   * a type mismatch;
   * a weekday of 0, which launchd also takes as Sunday but which this script never writes;
   * an array of intervals;
   * logs not named `caselist-sync.jsonl` and `caselist-sync.err.log` in one directory;
   * a wrapper not named `run-caselist-sync.sh`.

   Each is refused, naming the key, plutil's or the script's reason, and the option. Normalising
   0 to 7 would have been a silent rewrite.
3. **An option that changes the schedule, the log directory or the wrapper directory needs no
   confirmation.** The forbidden list forbids a change "without an explicit option", and the
   option is explicit. `--env` keeps its confirmation, because it moves the data and the bucket.
4. **Each setting is read even when an option gives it, but only refused when none does.** That is
   so the change can be said ("from Thursday at 07:30 to Thursday at 06:30 (--hour)"). Given over
   an unreadable value, it says it is setting it and that the plist's did not read back.
5. **Given values are normalised so they read back next time.** `--hour 07` is written as `7` (and
   `08` is never read as octal), and `--log-dir /x/` is written as `/x`. Before this, a trailing
   `/` would have produced a plist whose log directory a later reinstall could not read back.
6. **A kept directory is checked as a given one is.** An agent from before `v1-e34-t10` names the
   checkout's wrapper. Kept, that directory is refused as inside a git working tree, and the
   refusal says it is the installed agent's and that `--wrapper-dir` moves it. Before, such a
   reinstall moved the wrapper to the default without a word, which is now the forbidden case.
   The real agent was reinstalled on 2026-10-16, so its wrapper is the copied one.
7. **A wrapper moved with `--wrapper-dir` leaves the old copy in place**, and the installer says so.
   Deleting a file outside the new destination was not asked for.
8. **Doctor's words.** A takedown profile signed in as the other environment's takedown set reads
   `…, which is prod's takedown permission set and not dev's; a takedown runs only as …`. One
   signed in as the other environment's everyday set reads `…, which is prod's permission set
   and not dev's; …`. These are the everyday profile's words, and the module already calls the
   removal set "the takedown's permission set". Only the permission set's name appears, never the
   role's.
9. **The wrapper's comment says what its code does with `AWS_PROFILE`.** It exports one if set.
   The run's profile is `storage.s3.aws_profile`, which both bundled profiles set
   (`config/profiles/dev.toml`, `prod.toml`). A profile passed to `boto3.session.Session` wins over
   `AWS_PROFILE` (`integrations/s3/client.py`). The two lines that export it are left as they are
   (Follow-up 1).
10. **The time-limit test reads the constant from `caller_identity.py`.** Importing the S3
    integration under the test suite trips the socket block, so the test reads the source instead.
    It still fails if the constant and the comment drift apart.

## Operator follow-ups

**ac4, the dry run over the real agent** (a few seconds; at most 10 more if AWS does not answer).
It is read-only. It reads the installed plist and runs the installed build's `config show` and
`doctor --evidence-profiles` as the agent would. Nothing is written, and the plist it would install
goes to `/dev/null`. Where: your Mac, in this task's worktree.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e34-t25-reinstall-keeps-every-setting
ops/launchd/install.sh --debate-research "$HOME/.local/bin/debate-research" --dry-run > /dev/null
echo "install.sh exit=$?"
```

Success looks like these lines, then `install.sh exit=0`:

* `Keeping the installed agent's environment, dev, from its plist's DEBATE_ENV (--env changes it).`
* `Keeping the installed agent's caselists: hsld26 hspolicy26 hspf26, from its plist's ProgramArguments (--caselist replaces them).`
* `Keeping the installed agent's schedule, Wednesday at 06:00, from its plist's StartCalendarInterval (--weekday, --hour and --minute change it).`
* `Keeping the installed agent's log directory, …/Library/Logs/debate-research, from its plist's StandardOutPath and StandardErrorPath (--log-dir changes it).`
* `Keeping the installed agent's wrapper directory, …/.local/share/debate-research/launchd, from its plist's ProgramArguments (--wrapper-dir changes it).`
* `The build's checks and its evidence profile pass as the agent will run them (debate-research doctor --evidence-profiles).`

Paste the output back, and ac4 is recorded from it.

* **A `Not carried over from the installed plist: …` line** means a variable was added to the
  plist by hand, such as the parse stage's switch.
* **A refusal saying the plist `holds no … this script can read back`** means that setting was
  edited by hand. It names the key and the option to give, and that is worth knowing before a
  real reinstall.

**After this merges, `--check-launchd` refuses the installed agent until it is reinstalled**
(Deviation 3). It says `the installed agent's wrapper … is not this checkout's …; reinstall with
this script first`. The agent itself runs as before: its copy of the wrapper differs only in a
comment. The next real reinstall, from the runbook's step 3 with no option but the build, clears
it, and it now keeps Wednesday 06:00 by itself.

## Follow-up work

1. **The wrapper still exports `AWS_PROFILE` when it is set** (E34, p3). Those two lines are a
   no-op under launchd, since the plist no longer sets it. They can go with the next change to
   the wrapper's code.
2. **`--check-launchd` accepts `--weekday`, `--hour`, `--minute`, `--log-dir` and `--wrapper-dir`
   and ignores them** (E34, p3). Its "takes no options but --label" guard predates them. A
   one-line addition to that guard.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
