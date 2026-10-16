# Session report: v1-e34-t24-agent-install-loose-ends

| | |
|---|---|
| Task | `v1-e34-t24-agent-install-loose-ends` — The agent's installer checks what it can, and never changes an agent's environment by default |
| Spec | [`plan_specs/v1/e34-caselist-sync/t24-agent-install-loose-ends.yaml`](../../plan_specs/v1/e34-caselist-sync/t24-agent-install-loose-ends.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t24-agent-install-loose-ends` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Over an installed agent, `ops/launchd/install.sh` now reads the installed plist and keeps its
`DEBATE_ENV` and caselists unless an option says otherwise, and it says what it kept. A
different `--env` is refused without `--confirm-env-change`. So is an install that would move
the agent's data directory. Before it writes anything, a dry run included, it runs the build's
own `doctor --evidence-profiles` as the agent will run it, and refuses a profile this Mac's AWS
config does not define, naming the profile.

`--aws-profile` is removed. It wrote `AWS_PROFILE`, which nothing reads, and the plist no
longer carries that variable. `caselist pull --dry-run`, refused for its profile, no longer
creates the data directory. The launchd-check tests are no longer macOS-only: a `plistlib`
stand-in for `plutil` sits beside the fake `launchctl`, and a macOS-only test holds the stand-in
to the real `plutil` byte for byte.

**Look first at ac1.** Its "in CI" is shown here by a Linux simulation on this Mac, not by a CI
run (below, and in Decision 12). The phase is `Succeeded` on that evidence.

**What `install.sh` printed before this task, re-run over a dev agent with no `--env`** (your
note). This is a temporary HOME holding a dev agent installed with `--caselist testcl26 --env dev`:

* With no `--env` and no `--caselist`: `install.sh: at least one --caselist is required; see
  --help`, exit 2. Nothing was kept, because there was nothing to keep from.
* With `--caselist testcl26` and no `--env`: exit 0. The same `Wrote …` and `Copied the
  wrapper …` lines as any install, then `The agent runs … and keeps its data in
  …/.debate-research/prod`. The plist afterwards held `DEBATE_ENV=prod`,
  `AWS_PROFILE=debate-prod-evidence` and the same caselist. The data directory's last component
  was the only sign that the dev agent had become a prod agent.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `install-loose-ends` (Agent install loose ends) | Done | All four goal criteria and the node criterion pass. Three commits: the pull's dry run, the installer and its tests, the runbook |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the launchd-check tests run on Linux in CI with a `plistlib` stand-in, and t22's two installer mutants are caught there | PASS | The six launchd-check tests no longer carry `on_macos`. Every run of the installer in the file has the stand-ins first on its PATH. **Linux, simulated on this Mac:** pytest in-process with `platform.system()` reporting `Linux`, and a PATH of symlinks to every tool in `/usr/bin`, `/bin`, `/usr/sbin` and `/sbin` except `plutil` and `launchctl`. `tests/integration -k launchd`, run as `--part 1/2` and `--part 2/2` → `44 passed, 1 skipped` and `43 passed, 1 skipped`; the two skips are the two tests about the real `plutil`. The same again with both scripts' shebangs set to `/bin/dash`, which is Ubuntu's `/bin/sh` (restored from git afterwards) → `43 passed, 1 skipped` twice. **The mutants, under the same simulation:** t22's "the installer does not say what exit code 2 means" → `1 failed, 5 passed`, CAUGHT. "The installer's check passes whatever the wrapper's check ended with" → `3 failed, 3 passed`, CAUGHT. **The stand-in held to the real `plutil`** (macOS): `test_the_plutil_stand_in_answers_as_plutil_does` passes over 22 steps. It fails when the stand-in prints a boolean as Python does (`'False\n'` against `'false\n'`), and when it lists a dictionary's keys unsorted. The first real Linux run is the pull request's required `ci` check |
| ac2: `--aws-profile` either sets the profile the run uses or is removed, and the installer refuses a profile the AWS config does not define, naming it, each by test | PASS | Removed. `test_the_aws_profile_option_is_refused_and_says_where_the_profile_comes_from` and `test_the_plist_names_no_aws_profile_because_nothing_the_agent_runs_reads_one`. The refusal: `test_a_profile_the_aws_config_does_not_define_is_refused_naming_it_and_nothing_is_written[install, dry run]` (fake build), and `test_over_the_real_command_the_installer_refuses_a_profile_the_aws_config_lacks_naming_it[install, dry run]`. The second runs this checkout's real `debate-research` in a HOME whose AWS config defines another profile; output names `debate-dev-evidence`, `storage.s3.aws_profile` and "not defined in this machine's AWS config", exit 2. **Red first** (start commit's installer): the option was accepted, `AWS_PROFILE` was rendered, and over the real build with an undefined profile the installer exited 0 and printed `Wrote …` |
| ac3: a dry run refused for an undefined profile creates nothing on disk, shown failing first | PASS | `test_a_dry_run_refused_for_the_profile_creates_nothing_on_disk` (`packages/debate_cli/tests/test_pull_refused_before_the_bucket_is_built.py`). **Red first:** `AssertionError: the refused dry run created the data directory`. After the fix → both refused-pull files `27 passed`. The installer's own dry run also leaves HOME as it found it, refused over the real command (in ac2's real-command test) |
| ac4: `install.sh` over an installed agent with no `--env` or `--caselist` keeps the installed ones and says so; a different `--env` explicitly is refused unless confirmed. Shown failing first. The runbook's reinstall step reads the environment and caselists from the installed plist | PASS | Eleven reinstall tests in `tests/integration/test_launchd_install.py`, from `test_a_reinstall_with_no_env_or_caselist_keeps_the_installed_ones_and_says_so` to `test_an_installed_agent_whose_arguments_this_script_did_not_write_needs_its_caselists_given`. **Red first:** against the start commit's installer, 20 of the 21 new installer tests failed, each for the reason intended. The 21st, `test_a_first_install_without_env_is_prod`, pins behaviour that does not change. Examples: `at least one --caselist is required`; `unknown option --confirm-env-change`; `'prod' == 'dev'`, a dev agent given only `--caselist` became prod. **Runbook:** `test_the_reinstall_reads_the_environment_and_caselists_from_the_plist_and_types_neither` and `test_what_the_reinstall_says_it_kept_is_what_the_installer_says`. Against the start commit's runbook, 3 of the file's 8 tests failed; now `8 passed` |
| Node `install-loose-ends`: `uv run pytest tests/integration -k launchd` | PASS | `89 passed in 20.18s` (macOS, so the two macOS-only tests ran too) |
| Whole suite | PASS | `uv run pytest --part K/4`, at the end, while the operator's re-parse was running: `1779 passed`; `1787 passed, 1 xfailed`; `1790 passed, 1 skipped`; `1786 passed, 1 xfailed`. 46 to 62 s a part |
| Static checks | PASS | `ruff check` and `ruff format --check` on every changed Python file; `pyright` on the changed files → `0 errors`. `shellcheck` over both scripts, inside the launchd tests. `scripts/check_command_blocks.py` → `OK: no # comments in 262 shell code blocks` |

### Mutation results

Each mutant ran alone against the tests written to catch it, as if on Linux (the ac1
simulation), with a fresh `HYPOTHESIS_STORAGE_DIRECTORY`. No property test is in these
selections. The runner refuses a dirty tree, writes each file back from the bytes it saved, and
checks the tree is clean after every mutant. A mutant counts as caught only when pytest reports
failures and exits 1. None errored before running.

| Mutant | Result |
|---|---|
| t22: the installer does not say what exit code 2 means | Caught, 1 failed |
| t22: the installer's check passes whatever the wrapper's check ended with | Caught, 3 failed |
| The profile check's result is ignored | Caught, 5 failed |
| The profile check runs with this shell's environment, not the agent's | Caught, 1 failed |
| A build without the profile check (exit 2) is installed | Caught, 1 failed |
| A failed check's output is not shown | Caught, 4 failed |
| The installed environment is not kept (prod instead) | Caught, 2 failed |
| What was kept is not said | Caught, 2 failed |
| A different `--env` is not refused | Caught, 2 failed |
| The installed caselists are not kept | Caught, 3 failed |
| A data-directory move is not refused | Caught, 2 failed |
| A data-directory move is refused even when confirmed | Caught, 2 failed |
| A dropped variable is not named | Caught, 1 failed |
| `--aws-profile` is accepted silently | Caught, 1 failed |
| A dry run's notes go to stdout, into the plist | Caught, 2 failed |
| The pull builds the database before the bucket | Caught, 1 failed |
| The stand-in prints booleans as Python does (macOS, against real `plutil`) | Caught |
| The stand-in lists a dictionary's keys unsorted (macOS, against real `plutil`) | Caught |

## Files changed

* **`ops/launchd/install.sh`**: reads an installed agent's plist (environment, caselists and
  the variables it does not write); `--confirm-env-change`; the data-directory guard; the
  profile check before anything is written; `--aws-profile` refused with the reason; notes
  on stderr for a dry run. Help text and header.
* **`ops/launchd/com.debate-intelligence.caselist-sync.plist.template`**: no `AWS_PROFILE`,
  and its comment says why.
* **`debate_cli`**: `container.py`, where `_build_caselist_sync` builds the bucket before the
  database.
* **Tests**
  * `tests/integration/test_launchd_install.py`. The `plutil` stand-in and the fake `launchctl`
    are on every installer run's PATH. The launchd-check tests are unmarked. New: the stand-in
    against the real `plutil`, the profile tests and the reinstall tests. The fake build records
    each call's environment.
  * `packages/debate_cli/tests/test_pull_refused_before_the_bucket_is_built.py`: the ac3 test.
  * `packages/debate_cli/tests/test_runbook_reinstall_runs_the_profile_check.py`: two new tests,
    and t22's ordering test finds the new install command.
* **`docs/runbooks/caselist-scheduled-sync.md`**
  * Step 2: what the installer checks, and where the profile comes from.
  * The reinstall: the profile login uses the plist's environment; step 3 shows the environment
    and caselists from the plist and installs with neither.
  * The override and the parse-switch passages say what a reinstall now says.
* **Spec**: phase only.

`ops/launchd/run-caselist-sync.sh` is unchanged (Decision 11).

## Deviations from the spec

1. **Earlier tasks' tests changed.**
   * `test_the_installer_asks_the_build_for_its_data_directory_as_the_agent_runs_it` (v1-e34-t10)
     now expects the profile check after `config show`, checks both calls' environments, and is
     renamed to say so.
   * The dry-run placeholder test no longer passes `--aws-profile`.
   * t22's runbook ordering test found the install by `install.sh --caselist`, which the
     reinstall no longer types. It now finds the reinstall's command.
2. **One read of the real launchd, by the installer, in a run I made by hand.** To record what
   the old installer printed, I ran it over a temporary HOME. No fake `launchctl` was on its
   PATH, so the installer ran its own `launchctl print` of the real agent's label, which is
   read-only. That is how it printed "already loaded". Nothing was written outside the scratch
   directory. On macOS the existing tests had done the same on every run. They no longer do:
   the fake `launchctl` is first on every installer run's PATH.
3. **Other things run by hand that no criterion asked for:**
   * the installer over this checkout's real `debate-research` in a scratch HOME, to read what a
     refusal shows;
   * the Linux simulation and the dash runs (ac1);
   * the mutation runs;
   * five `plutil` commands on scratch plists, to learn its answers.

   None read the operator's AWS config or LaunchAgents, and none reached AWS.

## Decisions and assumptions

1. **`--aws-profile` is removed, not repaired.** Making it work would mean writing
   `DEBATE_STORAGE__S3__AWS_PROFILE`, a plist override that a reinstall would then have to keep
   or drop. Its default always equalled the build's setting. The runbook's fix for an undefined
   profile is to add the profile to the AWS config, not to point the agent at another one. The
   option is refused with a message naming `storage.s3.aws_profile`, not "unknown option". An
   override added by hand is named and dropped by a reinstall (Decision 7).
2. **The installer's profile check is the build's own `doctor --evidence-profiles`.** It runs
   with the environment the plist gives the agent (`env -i` with `HOME`, `PATH` and
   `DEBATE_ENV`), not a shell reading of the AWS config. So "defined" has one implementation,
   the same as the runbook's step 2 and `--check-launchd`. Consequences:
   * it also refuses a build whose own checks fail (Unicode database, integrations), which
     `install_channel.sh` already refuses;
   * a build older than t22 answers exit 2 and is refused by name;
   * an expired session passes;
   * it asks AWS one question for each defined profile.

   The installer prints the build's report only when it refuses, and says one line when it
   passes.
3. **Item (4) is `caselist pull --dry-run`.** That is t22 Follow-up 7's wording: "the service
   opens the database before it builds the bucket". The fix is in the composition root:
   `_build_caselist_sync` builds the bucket first, a singleton the services below reuse. A
   refused real run still writes its record, as t22 intended; those tests pass. The installer's
   own dry run, refused, is shown to create nothing too.
4. **A dry run makes every check an install makes.** That includes reading the installed agent
   and the profile check, so it previews what an install would do or refuse. Its stdout stays
   the plist alone, and what it kept goes to stderr.
5. **Only an installed agent changes the defaults.** A first install still defaults to prod and
   still needs a `--caselist`. `--env` equal to the installed environment is no change. Given
   `--caselist`, the caselists are replaced, and the installer says so.
6. **The data directory is guarded, which the spec's description does not ask but its forbidden
   list does.** A variable put in the plist by hand is not one the installer writes, and a
   reinstall writes the plist afresh. When there is such a variable, the installer asks the new
   build for the data directory twice: once with the installed plist's whole environment, and
   once with the environment it is about to write. It refuses if the two differ. The same
   `--confirm-env-change` confirms both kinds of move, so there is one confirmation for "this
   moves the agent's store".
7. **Variables the installer does not write are still dropped, and now named.** The runbook
   documents that a reinstall drops the parse stage's switch, and that is the switch's purpose:
   off until a build that turns it off. Carrying such variables over would change that.
   `AWS_PROFILE` gets its own line saying nothing reads it.
8. **An installed plist the installer did not write is refused unless told what to do.** With
   no `DEBATE_ENV`, it needs `--env` and `--confirm-env-change`. With arguments other than
   `--caselist <slug>` pairs, it needs `--caselist`.
9. **The stand-in implements only what the installer uses.** That is `-lint`, `-extract … raw`,
   `-replace`, `-insert` and `-remove`, with `plutil`'s own error messages. The macOS test holds
   it to the real one: stdout, stderr, exit code and the final document, across 22 steps
   including each failure. Its lint is stricter than `plutil`'s, which accepts plain text as an
   old-style plist. That does not matter for an XML plist the installer rendered.
10. **The real-command test reads the build's report with its box-drawing borders removed.**
    Under `env -i` the report is drawn 80 columns wide, and its sentences wrap. Widening it would
    have meant giving the build something launchd does not.
11. **The wrapper is untouched.** Its comment still lists `AWS_PROFILE` among the variables
    "templated into the plist by install.sh", which is no longer true; what it says the wrapper
    does with the variable is still true. The wrapper's behaviour is out of scope. Changing its
    bytes would also make `--check-launchd` refuse the installed agent until a reinstall,
    because it compares the installed copy with the checkout's (Follow-up 2).
12. **ac1 is PASS on a simulation, not a CI run.** No session can see the pull request's `ci`
    before you review. The tests carry no skip off macOS, and they are in the default selection:
    my four `--part K/4` runs collected them. The simulation reproduces what differs on the
    runner: the platform reports Linux, there is no `plutil` or `launchctl` on PATH, and
    `/bin/sh` is dash. The two mutants are caught under it. A mutant can only be caught in a
    simulation, since CI runs no mutants. If the real runner disagrees, the required `ci` check
    fails and the pull request cannot merge. If you read "in CI" literally, this is the one
    criterion to move to NOT RUN, and the phase to `InProgress`.

## Operator follow-ups

Nothing has to be run for this task to merge. One read-only check against the real agent shows
what a reinstall from this branch would keep (your note: real-agent checks are yours).

**Operator command** (a few seconds; it asks AWS one question, as `doctor --evidence-profiles` does)
Where: your Mac, in this task's worktree. It reads the installed plist and runs the installed
build's `config show` and `doctor --evidence-profiles` as the agent would. It writes nothing,
and the plist it would install goes to `/dev/null`.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e34-t24-agent-install-loose-ends
ops/launchd/install.sh --debate-research "$HOME/.local/bin/debate-research" --dry-run > /dev/null
echo "install.sh exit=$?"
```

Success looks like these lines, then `install.sh exit=0`:

* `Keeping the installed agent's environment, dev (--env changes it).`
* `Keeping the installed agent's caselists: …`, with the caselists the agent follows.
* `Not carried over from the installed plist: AWS_PROFILE. …`
* `The build's checks and its evidence profile pass …`

Paste the output back. Another `Not carried over` line means a variable was added to the plist by
hand. If it would move the data directory, the command refuses and names both directories; that
is the guard working, and it is worth knowing before a real reinstall.

The next real reinstall can follow the runbook's new step 3, with no `--env` and no
`--caselist`.

## Follow-up work

1. **A reinstall still resets the schedule and the other options to their defaults** (E34, p3).
   `--weekday`, `--hour`, `--minute`, `--log-dir` and `--wrapper-dir` are not read from the
   installed plist, so an agent installed for Thursday is moved to Wednesday 06:00 by a reinstall
   that does not repeat them. It is the same kind of fault as the environment's. The schedule
   was out of scope here.
2. **The wrapper's comment still says `AWS_PROFILE` is templated into the plist** (E34, p3).
   Fix it with the next task that changes the wrapper, so the installed agent is not asked to
   reinstall for a comment.
3. **The installer's profile check now waits as long as `doctor`'s does when AWS is unreachable.**
   That is t22 Follow-up 6, already in `v1-e29-t09`. It now affects an install as well as
   `--check-launchd`.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-16

**Notes:**

Accepted in full, with the phase `Succeeded`. The spec is unchanged.

**ac1 on the simulation is accepted, and the pull request's `ci` is its proof.** The tests carry
no platform skip and sit in the default selection, so the required check runs them on Linux.
The simulation reproduces what differs there: the platform, no `plutil` or `launchctl`, and
dash. If `ci` is red on them, the pull request does not merge and the fix comes back here.

**The "before" you recorded is the finding that matters.** A dev agent reinstalled with only
`--caselist` became a prod agent on an empty store, and the only sign was the last component of
a path. That would have happened at the re-parse's last step, the build install. The installer
now keeps what is installed, says so, and refuses a switch unless it is confirmed.

**The work itself:**

* **The profile check is the build's own `doctor --evidence-profiles`, run under `env -i` as
  the agent runs.** "Defined" has one implementation, shared with the runbook's step 2 and
  `--check-launchd`. An expired session passing is right: the agent signs in for itself at run
  time, or publishes later.
* **The data-directory guard (Decision 6)** reads the forbidden list rather than the description,
  and is the right reading. Asking the new build for the directory under both environments,
  rather than parsing variables in shell, keeps one source of truth.
* **`--aws-profile` refused with its reason,** not "unknown option", so an old command line
  explains itself.
* **The stand-in held to the real `plutil` byte for byte, failures included,** is what makes
  running these tests on Linux trustworthy rather than merely green.
* **The mutation run:** 18 of 18 caught, t22's two among them.

**Rulings:**

* **Deviation 1:** accepted.
* **Deviation 2:** accepted. `launchctl print` is a read, and the fake `launchctl` is now first on
  every installer run's PATH, which closes it for good. Reads of the real agent go to the operator
  as commands, as this report's follow-up does.
* **Deviation 3 and the decisions:** accepted.
* **Follow-up 1 (a reinstall resets the schedule and options):** filed in the next PM batch as an
  E34 p3 task. It is harmless today, because the agent runs at the defaults.
* **Follow-up 2 (the wrapper's comment):** with the next task that changes the wrapper.
* **Follow-up 3:** already in `v1-e29-t09`.

**Operator follow-up:** the read-only dry run over the real agent. It can run any time, before or
after the merge, and its output is recorded at the next close-out. The next real reinstall, the
re-parse's build install, follows the runbook's new step 3.

**Merge order:** after the v1.0 release pull request (versions 1.1.0). A merge into `dev` before
it would fail its pre-release.
