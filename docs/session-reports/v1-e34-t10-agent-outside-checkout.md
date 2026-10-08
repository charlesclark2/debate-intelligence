<!-- docs-index: Session report for v1-e34-t10, the weekly agent's wrapper copied out of the checkout and its console script pinned -->
# Session report: v1-e34-t10-agent-outside-checkout

| | |
|---|---|
| Task | `v1-e34-t10-agent-outside-checkout` — The weekly agent runs nothing from a git checkout |
| Spec | [`plan_specs/v1/e34-caselist-sync/t10-agent-outside-checkout.yaml`](../../plan_specs/v1/e34-caselist-sync/t10-agent-outside-checkout.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t10-agent-outside-checkout` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`ops/launchd/install.sh` now copies the wrapper to
`~/.local/share/debate-research/launchd/run-caselist-sync.sh`, replacing it in one rename with mode
0755 on every install, and the plist names that copy. The plist also pins the console script as
`DEBATE_RESEARCH_BIN`, with a PATH of only its directory plus `/usr/bin:/bin:/usr/sbin:/sbin`. Every
path the agent will use is refused if it is under `~/Documents`, `~/Desktop`, `~/Downloads`,
`~/Library/Mobile Documents` or `/Volumes`, or inside a git working tree or a project `.venv`. The
refusal names the path and the reason, and nothing is written. That covers the wrapper destination,
the log directory, the console script, the data directory (asked of the build itself) and HOME. For
ac5, the wrapper has a `--check` mode that only runs `--version`. The installer has
`--check-launchd`, which loads a one-off `<label>.check` copy of the installed plist, kickstarts it,
prints its log and exit code, boots it out, and fails if the real agent's `runs` changed.

**The phase stays InProgress.** ac1, ac2 and ac4 pass, and the code side of ac3 and ac5 is done and
tested. But ac3 asks for the operator's reinstall with `launchctl print` recorded, and ac5 asks for a
real launchd check on Charlie's Mac. Both are operator steps the session must not take (the PM:
never bootstrap, boot out or replace the real agent). They are Operator follow-ups 1–4, in the
order the PM asked for, and must run **before Wednesday 2026-10-14 06:00**.

**One thing for the PM to look at first.** A real dry run on this Mac caught a bug that every fake
had passed: the real `config show` names `storage.data_dir` twice. The second time is under
`sources`, as `profile:/…/dev.toml`, and the first extraction read that value and refused the real
build (safely: exit 2, nothing written). It is fixed, the fake now prints the real shape, and a
mutant restoring the old extraction fails 18 tests. Decision 3 explains why the data directory is
asked of the build at all.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `installer` — Copy the wrapper out and pin the console script | Done | Tests written first and shown failing against the old installer (41 of 50), then the wrapper, template, installer and runbook changed. 50 tests pass, 17 mutants caught |

## Acceptance criteria

### Goal criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — `install.sh --dry-run` renders a plist whose ProgramArguments name a wrapper outside the checkout; a test fails if any rendered path lies inside the repository; shown failing first | **PASS** | `test_the_rendered_plist_names_nothing_inside_the_repository` walks every string in the parsed plist, with PATH split into entries, and fails on any path under `REPOSITORY_ROOT` or below a `.git`. **Before the change** (commit `a694f1c`, tests only): `AssertionError: the plist names paths inside a git working tree: [PosixPath('/Users/charlesclark/Documents/…/v1-e34-t10-agent-outside-checkout/ops/launchd/run-caselist-sync.sh'), …]`, 13 more items (the copied shell PATH's `.venv/bin` and others). **After:** passes, and asserts `ProgramArguments[0]` is `$HOME/.local/share/debate-research/launchd/run-caselist-sync.sh`. **Real dry run on this Mac**, with the installed agent's arguments: `ProgramArguments.0 => /Users/charlesclark/.local/share/debate-research/launchd/run-caselist-sync.sh`, `plutil -lint` → `OK`, exit 0 in 0.77 s, the installed plist's SHA-256 the same before and after, and `~/.local/share/debate-research` still absent |
| ac2 — the plist sets DEBATE_RESEARCH_BIN to `--debate-research`'s path, or the one on the installer's PATH; a test shows a different `debate-research` earlier on PATH is not the one the wrapper execs | **PASS** | `test_the_plist_pins_the_console_script_it_was_given` (before: `KeyError: 'DEBATE_RESEARCH_BIN'`), `test_without_the_option_the_plist_pins_the_one_found_on_the_installers_path`, and `test_a_console_script_reached_through_a_symlink_is_pinned_as_found`, where `~/.local/bin/debate-research` is written as the link, not its target. `test_a_debate_research_earlier_on_path_is_not_the_one_the_wrapper_execs` does a real install into a temporary HOME and runs the plist's `ProgramArguments` with its `EnvironmentVariables`, with a recording `anaconda3/bin/debate-research` put first on PATH. The pinned script records `--json caselist pull --caselist testcl26` and the shadow records nothing. **Before:** `assert '--json caselist pull --caselist testcl26' in []`, because the old wrapper exec'd the shadow. `test_a_console_script_inside_a_checkout_or_a_venv_is_refused` covers 4 cases: given inside a working tree, given inside a `.venv`, found on PATH inside a working tree, and a symlink into one. **Real dry run:** `DEBATE_RESEARCH_BIN => /Users/charlesclark/.local/bin/debate-research`, `PATH => /Users/charlesclark/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin` |
| ac3 — re-running the installer replaces the copied wrapper; the runbook says so; the operator reinstalls and the report records `launchctl print` showing the new program path | **Code and runbook PASS; operator half NOT RUN** | `test_an_install_copies_the_wrapper_and_a_reinstall_replaces_the_copy`: install, overwrite the copy with an "older build" wrapper at mode 0700, reinstall. The copy is then byte-equal to `ops/launchd/run-caselist-sync.sh`, mode `0o755`, not a symlink, and the only file in its directory (no `.incoming` left). Runbook: "What the agent runs, and where it is" and "Reinstall to update the wrapper" under Step 2, and the reload sequence in Step 3. **NOT RUN:** the reinstall on Charlie's Mac and `launchctl print` after it. The session may not replace the real agent. Operator follow-ups 2 and 4 |
| ac4 — the installer refuses a wrapper destination, data directory, log directory or console script under ~/Documents, ~/Desktop, ~/Downloads, ~/Library/Mobile Documents or /Volumes, naming the path and the reason, with a test for each; the default is outside all of them; the runbook says where and why | **PASS** | `test_a_path_under_a_folder_macos_protects_is_refused` runs 20 cases (4 kinds × 5 locations). Each asserts exit 2, `the <kind> <path>` in stderr, the protected folder's name, `privacy protection`, no plist written and no wrapper copied. Before the change the log-directory and console-script cases failed because the old installer accepted them, and the wrapper and data-directory cases failed because the option or check did not exist. Also tested: `~/documents` in lower case, a symlink `~/logs → ~/Documents/logs`, and `test_the_defaults_are_outside_every_protected_folder`. Sample message: `refusing the log directory /…/home/Documents/debate/logs: it is under /…/home/Documents, and macOS privacy protection does not let a launchd agent open anything there (the agent would exit 126, "Operation not permitted")`. Runbook: the table and the paragraph after it |
| ac5 — before 2026-10-14 the operator proves launchd can execute the reinstalled wrapper without a sync or the download cap; the report records the check's output, exit 0, and an unchanged `runs` | **Mechanism PASS; operator proof NOT RUN** | Wrapper: `test_the_wrapper_check_mode_prints_the_version_and_never_pulls` (the fake records only `--version`), `…_takes_no_other_arguments` (exit 2, nothing called), `…_fails_when_the_console_script_is_missing` (127). **Before:** the old wrapper exit-0'd on `--check --caselist testcl26` and exec'd `debate-research --json caselist pull --check --caselist testcl26`, a pull. Installer `--check-launchd`, against a fake `launchctl` that loads plists and runs jobs the way launchd does (macOS only): bootstrap, kickstart and bootout only `<label>.check`, never the real label except `print`; log printed; `exit code 0`; `runs: 7 before, 7 after`; the check plist removed. Plus: a failing wrapper is reported (exit code 127) and still booted out; the real agent's runs changing fails the check (`7 before, 8 after`); an old plist naming the checkout's wrapper is refused before any bootstrap. **Real, read-only:** the copied wrapper's `--check` under the agent's minimal environment → `run-caselist-sync: check: DEBATE_RESEARCH_BIN is /Users/charlesclark/.local/bin/debate-research`, `debate-research 0.1.0.dev60 (dev channel, prod environment, ec7b95ee9533)`, exit 0. The installer's `sed` reading of a real `launchctl print` (the agent as it is now) → `not running`, `126`, `1`. **NOT RUN:** the launchd check itself. Operator follow-up 3 |

### Node criterion

| Criterion | Status | Evidence |
|---|---|---|
| `installer` — the rendered plist references nothing inside the repository (a dry-run plist names a wrapper outside the checkout and sets DEBATE_RESEARCH_BIN; the test fails against the current installer and passes after) | **PASS** | ac1 and ac2 above. Against `a694f1c` the tests are 41 failed, 9 passed. After: `uv run --frozen pytest tests/integration/test_launchd_install.py -q` → `50 passed in 6.70s` on macOS, so the `plutil` and launchd-check cases ran |

### Mutation

Each mutant was applied to the committed tree, the installer tests were run, and the file was
restored with `git checkout` (`git status` clean after each batch). No test in this file uses
Hypothesis. Each run still had a fresh `HYPOTHESIS_STORAGE_DIRECTORY`. The runs below are against
the final code, in two batches of 58 s and 78 s. An earlier pass over 16 of them, before the
`config show` fix, also caught every one.

| Mutant | Result |
|---|---|
| The plist points back into the checkout (`wrapper=${WRAPPER_SOURCE}`) | Caught, 6 tests (ac1, reinstall, defaults, three launchd-check tests) |
| DEBATE_RESEARCH_BIN not written (key removed from the template) | Caught, 4 (the three pinning tests and the shadow-on-PATH test) |
| No refusal of ~/Documents / ~/Desktop / ~/Downloads / iCloud Drive / /Volumes | Each caught: 6 / 4 / 4 / 4 / 4, the four kinds for that location each time |
| No check of the wrapper destination / log directory / data directory / console script | Each caught: 5 / 7 / 5 / 9 |
| The check mode calls pull (`exec … --json caselist pull` in the `--check` branch) | Caught, 2 |
| The check mode removed, so `--check` falls through to pull | Caught, 3 |
| A reinstall that leaves the old wrapper (copy only when none exists) | Caught, 1 |
| No git working tree check | Caught, 5 |
| Symlinks not resolved | Caught, 2 |
| Data directory read from `config show`'s `sources` | Caught, 18 |

### Whole-repository checks

| Check | Status | Evidence |
|---|---|---|
| Default suite | PASS | `uv run --frozen pytest -q -n auto -m "not slow and not live"` → `4274 passed, 1 skipped in 83.92s`. The skip is the parser eval's, unrelated |
| Lint and format | PASS | `ruff check .` → `All checks passed!`; `ruff format --check .` → `510 files already formatted` |
| Types | PASS | `pyright tests/integration/test_launchd_install.py` → `0 errors` |
| Import contracts | PASS | `lint-imports` → `Contracts: 11 kept, 0 broken.` |
| shellcheck | PASS | `shellcheck ops/launchd/install.sh ops/launchd/run-caselist-sync.sh` → clean (also asserted by `test_the_shell_scripts_pass_shellcheck`) |
| Links and doc descriptions | PASS | `check_links.py` → `OK: 1254 relative links and anchors in 170 Markdown files`; `docs_index.py --check-descriptions` → `All 30 indexed documents under docs/ have a description` |
| Paste safety | PASS | No line containing `#` inside a shell block of the runbook, or in this report's Operator follow-ups |
| Spec validation | PASS | `uv run scripts/validate_specs.py` → `OK: 308 files, 38 epics, 250 tasks, 20 releases` |
| CI budget | Within | The installer file runs in about 7 s. Its 50 tests replace 8, and the launchd-check ones skip on the Linux runners |

## What the CLI runs at run time, checked for the minimal PATH

The PM asked for this before the shell PATH was dropped. Checked against the installed build
(`~/.local/share/uv/tools/debate-cli`):

* **`subprocess` in `debate_core` and `debate_cli`**: two uses. `macos_notifier.py` runs
  `osascript`, found on PATH and otherwise `/usr/bin/osascript`. `build_info.py` runs `git
  rev-parse`, only for an unstamped checkout build, never for an installed one. Under the agent's
  PATH, `osascript → /usr/bin/osascript` and `git → /usr/bin/git`.
* **keyring's macOS backend** (`caselist_token`) uses the Security framework through ctypes. There
  is no `subprocess` in `keyring/backends/macOS/`, and `/usr/bin/security` is on the PATH anyway.
* **botocore** shells out only for `credential_process`, and no profile in `~/.aws/config` has one.
  SSO reads the token cache from `~/.aws`.
* **The interpreter** is named by the console script's shebang
  (`~/.local/share/uv/tools/debate-cli/bin/python`), not looked up on PATH. Nothing on the tool's
  `sys.path` is under `~/Documents`: its site-packages, and the base interpreter's stdlib.
* `env -i HOME=… PATH=~/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin` → `debate-research --version`
  exit 0 and `--json config show` exit 0 in 0.43 s.

## Files changed

* **`ops/launchd/install.sh`**: the wrapper copy and atomic replace; `DEBATE_RESEARCH_BIN` and the
  minimal PATH; `--wrapper-dir`; refusals for protected folders, working trees and `.venv`s,
  following symlinks and ignoring case; the data directory asked of the build; `--check-launchd`.
  The help text is the header, as before.
* **`ops/launchd/run-caselist-sync.sh`**: `--check`, alone, prints the resolved console script and
  execs `--version`. The header says the agent runs the installer's copy.
* **`ops/launchd/com.debate-intelligence.caselist-sync.plist.template`**: `DEBATE_RESEARCH_BIN`;
  the PATH comment; a header paragraph on why nothing it names is in a checkout or a protected
  folder.
* **`docs/runbooks/caselist-scheduled-sync.md`**: Step 2 passes `--debate-research
  "$HOME/.local/bin/debate-research"`, with a table of what the agent runs, where, and why. It also
  covers reinstalling to update the wrapper, the reload sequence and `--check-launchd` in Step 3,
  and removing the copy in "Disabling it". t22's "Checking an installed build" and t16's
  `docs-index` comment are kept as merged. Both syncs rebased cleanly.
* **`tests/integration/test_launchd_install.py`**: 50 tests, up from 8 (the 8 kept, the dry-run one
  updated to the copied wrapper); a fake console script, a fake `launchctl`.
* **This report.**

## Deviations from the spec

### 1. The installer asks the build where its data directory is

ac4 says the installer refuses a data directory under a protected folder, but the installer has
never chosen a data directory. It comes from the profile bundled into the installed build. I did
not add a `--data-dir` option, which would be new scope. Instead the installer asks the build with
`--json config show`, run with the environment the plist will give it (`env -i`, the agent's PATH,
`DEBATE_ENV`, `AWS_PROFILE`, cwd `$HOME`), and checks what comes back. `config show` only reads. The
consequence: a dry run now executes the console script, and an install refuses when the build
cannot say where its data is. The spec's text says neither, so I am recording it here.

### 2. Two options and two checks beyond the four paths ac4 lists

* `--wrapper-dir` exists because ac4 asks for a refused wrapper destination with a test for each
  location. With a fixed destination under `$HOME`, only a HOME on `/Volumes` could be refused.
* HOME (the plist's `HOME` and `WorkingDirectory`) goes through the same check, because the
  forbidden list covers every path in the plist.
* An absolute path is required, and a `.` or `..` component is refused. Both are cheap, and the
  prefix comparison would be unsound without them.

### 3. `--check-launchd` refuses an agent this checkout did not install

The check reads the installed plist and runs its `ProgramArguments[0]` with `--check`. A plist from
before this task names the checkout's wrapper. Under TCC that would exit 126, and an old wrapper
without the mode would turn `--check` into `caselist pull --check`. So the check refuses unless
the installed wrapper passes the same path checks and is byte-identical (`cmp`) to this checkout's
`run-caselist-sync.sh`. In practice it must be run from the checkout the reinstall was run from.

## Decisions and assumptions

* **`DEBATE_RESEARCH_BIN` is written as found and checked as resolved.** Per the PM,
  `~/.local/bin/debate-research` stays the link (uv repoints it on each install). The refusals also
  look at the physical path, so a link into a checkout, a `.venv` or `~/Documents` is refused.
* **A working tree is found the way git finds one**, by a `.git` file or directory above the path,
  without running `git`, so the check also works where no git or Command Line Tools are installed.
* **Protected-folder checks ignore case** (APFS is case-insensitive by default), and are made
  against both `$HOME` and its physical path.
* **The wrapper is copied before the plist is moved into place**, so an installed plist never names
  a wrapper that is not there. Both are renames, so a run starting mid-install sees the old file or
  the new one, never half of one.
* **The check's plist is a `plutil`-edited copy of the installed one**, in a `mktemp -d` under
  `$TMPDIR`, removed by an EXIT trap that also boots the check label out if it is still loaded.
  `StartCalendarInterval` is removed, `RunAtLoad` is false, and stdout and stderr go to
  `caselist-sync-check.log` in the agent's log directory, emptied first. It waits up to 60 s.
* **Reloading the real agent resets `runs` to 0.** It is bootout then bootstrap, so `runs = 1` and
  `last exit code = 126` from 2026-10-07 will not survive the reinstall. The ac5 comparison is the
  check's own before and after. The runbook says so.
* **Cadence and `RunAtLoad` are unchanged.** The real dry run renders `Weekday 3, Hour 6, Minute 0`
  and `RunAtLoad false`, as installed.

## Operator follow-ups

All four on Charlie's Mac, in this order, **before Wednesday 2026-10-14 06:00**, after the agent's
build has been moved to the first `v1-e01-t22` pre-release. Each takes seconds. Paste the output of
each back for the report. The commands run from this task's worktree, because `--check-launchd`
compares the installed wrapper with that checkout's copy. Once this branch has merged, the same
commands work from any checkout of dev.

**1. Confirm the installed build** (about 5 s)

```bash
command -v debate-research
debate-research --version
debate-research doctor; echo "doctor exit=$?"
```

Success: `/Users/charlesclark/.local/bin/debate-research`, a version naming the t22 pre-release you
installed (note it; step 3 must report the same one), and `doctor exit=0`.

**2. Reinstall the agent** (about 5 s). First record the agent as it is now, the "before" for
step 4, then read the dry run, then install. The arguments are the ones recovered read-only from
the installed plist: three caselists, `dev`, `debate-dev-evidence`, Wednesday 06:00, the default
log directory.

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e34-t10-agent-outside-checkout
launchctl print gui/$UID/com.debate-intelligence.caselist-sync | grep -E 'program =|runs =|last exit code ='
ops/launchd/install.sh --caselist hsld26 --caselist hspolicy26 --caselist hspf26 --env dev --aws-profile debate-dev-evidence --weekday 3 --hour 6 --minute 0 --debate-research "$HOME/.local/bin/debate-research" --dry-run
```

The "before" lines should read `program = /Users/charlesclark/Documents/…/ops/launchd/run-caselist-sync.sh`,
`runs = 1`, `last exit code = 126`. The dry run should name
`/Users/charlesclark/.local/share/debate-research/launchd/run-caselist-sync.sh` and
`DEBATE_RESEARCH_BIN` `/Users/charlesclark/.local/bin/debate-research`. Then:

```bash
ops/launchd/install.sh --caselist hsld26 --caselist hspolicy26 --caselist hspf26 --env dev --aws-profile debate-dev-evidence --weekday 3 --hour 6 --minute 0 --debate-research "$HOME/.local/bin/debate-research"
launchctl bootout gui/$UID/com.debate-intelligence.caselist-sync
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist
```

Success: `Copied the wrapper to /Users/charlesclark/.local/share/debate-research/launchd/run-caselist-sync.sh`,
`The agent runs /Users/charlesclark/.local/bin/debate-research and keeps its data in /Users/charlesclark/.debate-research/dev`,
and no error from `bootout` or `bootstrap`. Nothing runs: `RunAtLoad` is false. If `bootstrap`
says `Bootstrap failed: 5: Input/output error`, the bootout had not finished; run the bootstrap
line again.

**3. Run the launchd check** (under 10 s; it waits at most 60)

```bash
ops/launchd/install.sh --check-launchd; echo "check exit=$?"
```

Success: the log between the `---` lines reads
`run-caselist-sync: check: DEBATE_RESEARCH_BIN is /Users/charlesclark/.local/bin/debate-research`
and `debate-research <the version from step 1> (…)`. Then
`com.debate-intelligence.caselist-sync.check exit code 0`, `Booted out com.debate-intelligence.caselist-sync.check`,
`com.debate-intelligence.caselist-sync runs: 0 before, 0 after`, and `check exit=0`. It makes no
`caselist pull` and no OpenCaselist call. An exit code of 126 means launchd still cannot open the
wrapper. Paste everything if so.

**4. `launchctl print`, after** (about 1 s)

```bash
launchctl print gui/$UID/com.debate-intelligence.caselist-sync | grep -E 'program =|runs =|last exit code =|"Weekday"|"Hour"|"Minute"'
launchctl print gui/$UID/com.debate-intelligence.caselist-sync.check
```

Success: `program = /Users/charlesclark/.local/share/debate-research/launchd/run-caselist-sync.sh`,
`runs = 0`, `last exit code = (never exited)`, and `"Weekday" => 3`, `"Hour" => 6`, `"Minute" => 0`.
The second command should fail with `Could not find service`, because the check label is gone.
The scheduled run on 2026-10-14 is then v1-e34-t05's ac3, not this task's.

When these are pasted back, ac3's operator half and ac5 can be marked PASS and the phase set to
Succeeded.

## Follow-up work

* **The installed build's interpreter is anaconda's.**
  `~/.local/share/uv/tools/debate-cli/bin/python → /Users/charlesclark/anaconda3/bin/python3`
  (3.12.7). It is outside every protected folder, so it does not affect this task. But a conda
  update or removal would break the agent's build in place, and doctor would only notice the
  Unicode pin. Belongs with the install channel (E01, after `v1-e01-t14`/`t22`): whether
  `install_channel.sh` should prefer a uv-managed Python.
* **`~/Library/CloudStorage`** (Dropbox, Google Drive and other File Provider folders) is also
  something macOS asks permission for. It is not in the spec's list, so it is not refused. The PM
  may want it added to ac4's list.
* **XML-special characters in paths** (`&`, `<`) are still written unescaped into the plist, as
  before this task. `plutil -lint` refuses the result at install, so this fails safe, but with a
  poor message. Small; E34.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-08

**Notes:**

Accepted. Before the PR, two things: one small addition, and Charlie's operator results recorded in
this report. When both are in, set the phase to `Succeeded` and open a full PR, not `--partial`.

* **The real dry run that caught `config show`'s second `storage.data_dir` is the best evidence in
  the report.** Every fake had passed it. Making the fake print the real shape, and adding the
  mutant that restores the old extraction, is the right response.
* **Deviations 1 to 3: accepted.**
  * Asking the build for its data directory is the only honest way to check a path the installer
    does not choose.
  * `--wrapper-dir`, the HOME check and the absolute-path rule follow from the forbidden list.
  * `--check-launchd` refusing a wrapper that differs from the checkout's makes the check prove the
    install it was run after.
* **Decisions: accepted.** In particular: the wrapper is copied before the plist; the
  protected-folder checks are case-insensitive and follow symlinks; and the session states plainly
  that a reload resets `runs`.
* **The run-time PATH audit (osascript, git, keyring, botocore, the shebang)** is what makes the
  minimal PATH safe to ship.

**Before the PR:**

1. **Add `~/Library/CloudStorage` to the protected locations** (Dropbox, Google Drive and other
   File Provider folders). That means the four cases for it, the runbook table, and one mutant
   showing it caught. It changes neither the wrapper nor the plist Charlie installs, so it does not
   affect his operator steps.
2. **Record Charlie's results from operator follow-ups 1 to 4** in this report, as ac3's operator
   half and ac5. Then set the Goal to `Succeeded`. If any step does not match its success
   description, stop and send it to the PM.

**Follow-up work:**

* **The installed build runs on anaconda's Python:** filed as **v1-e01-t23-managed-python** (in this
  branch, with its epic entry). A conda update would otherwise break the agent's build in place,
  with nothing to catch it before a Wednesday run.
* **`~/Library/CloudStorage`:** done here, as item 1 above.
* **XML-special characters in plist paths:** not filed. `plutil -lint` refuses the result, so it
  fails safe.
