# Session report: v1-e01-t44-cli-mention-in-a-message-is-prose

| | |
|---|---|
| Task | `v1-e01-t44-cli-mention-in-a-message-is-prose` — A test that mentions debate-research inside a longer message is not read as running the app |
| Spec | [`plan_specs/v1/e01-repo-foundation/t44-cli-mention-in-a-message-is-prose.yaml`](../../plan_specs/v1/e01-repo-foundation/t44-cli-mention-in-a-message-is-prose.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t44-cli-mention-in-a-message-is-prose` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`scripts/affected_tests.py` now reads each string literal of a Python file on its own, on the
line where `debate-research` appears. A sentence before the name, or around the code span or
quotes that hold it, makes the mention prose. So does a code span that opens the line, which is
how messages build their fixes. A string that is the program alone, a line that starts with it,
and a path to it are runs. So is anything the rule cannot read as a sentence: shell syntax
(`&&`, `X=1`), an option, or a program that runs its arguments (`uv run`). Shell scripts and other
non-Python files are read whole, as before. `--every-mention-runs` restores the old reading; on
all six measured diffs it selects exactly what the start commit's script does.

**The measurement.** The files a change to *every* command module selects fell from **85 to 62**.
Each landscape merge selected all 85 before and all 62 after. Over t38's four landscape merges
the selections fell from **787 to 727 files** (13 to 16 fewer each). The f5a8221 `container.py`
edit alone fell from **111 to 88**. No measured selection gained a file.

**Real runs are still runs.** The 24 test files the six diffs stop selecting were run under a
recorder in scratch: `648 passed`. None ran any `debate_cli` code, and none started a process
that names the program. Mutants 1 and 2 are caught by cases that really run the app. Over the real
tree, mutant 2 also drops the `files build` and `caselist pull` smoke checks.

**What the PM should look at first:**

- **Decision 2:** a code span that opens the line counts as prose. It goes one step past the
  PM's wording.
- **What still carries the 62 files** (below, under the measurements). About half of the
  mention-runs left are messages that *start* with `debate-research caselist …`, which stay runs
  as ruled. t39's argument reading cannot see their command because they sit in f-strings or
  `in` comparisons. That is follow-up 1, outside this task.

The Goal is `Succeeded`: every criterion passed in the session.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `cli-mention-in-a-message-is-prose` (Mentions as prose) | Done | Commits `84b2894`, `dc4d946`, `bade2a1` (after `scripts/task sync` onto `f32a15e`). The node criterion passes. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: over t38's landscape merges, fewer files reach every command | PASS | [Measurements](#ac1-the-measurements). The files a change to every command module selects: **85 → 62** over the start tree, 0 added. Every merge selects all of them, so each merge's every-command count is 85 → 62 as well. Selections: `1ace4e5` 145 → 128, `321b5ee` 290 → 276, `b3273fb` 151 → 135, `2a33947` 201 → 188, t27's `8051c77` 145 → 128, f5a8221's edit alone 111 → 88. Each after-list is a subset of its before-list (`comm -13`: 0 lines in all six). |
| ac1: a real run is still read as one | PASS | The [run check](#real-runs-are-still-runs) over the 24 dropped files: `648 passed in 5.35s`; 0 `debate_cli` calls and 0 starts of the program. Both sides of the recorder fired on positive controls. The [mutation run](#mutation-run) covers every run rule. Mutants 1 and 2 drop cases that start the app with `subprocess`. |
| ac1: the collected count is unchanged | PASS | `tests/scripts/test_affected_tests.py` collects 109 cases at the start commit and 117 now: **0 lost**, 8 added, all new. No other test file changed (`git diff --stat` from the start: the script, that test file, the spec and this report). |
| ac1: tests shown failing first | PASS | [Red runs](#red-runs) against two skeletons and the start commit's script. Every new case fails against at least one of them. |
| PM: the four mutants, with mutants 1 and 2 catching the forbidden item | PASS | Mutants 1 to 5 of 21, all caught. Mutant 1 drops `subprocess.run("debate-research caselist remove --team T", shell=True)`. Mutant 2 drops `subprocess.run(["debate-research", ...])`, `shutil.which("debate-research")` and the world's installed-CLI smoke tests. Over the real tree, mutant 2 drops `tests/smoke/test_caselist_pull.py` from `1ace4e5`, and `test_files_cli.py` and `test_files_publish.py` from f5a8221's edit. |
| Node `cli-mention-in-a-message-is-prose`: `uv run pytest tests/scripts -k affected` | PASS | `perl hardstop.pl 115 .venv/bin/python -m pytest tests/scripts -k affected -p no:cacheprovider` → `147 passed in 50.65s`, at load 10, at `6d8ac76` (now `dc4d946`). After the sync and the docstring commit, `tests/scripts/test_affected_tests.py` → `117 passed in 26.58s`. |

### ac1: the measurements

**Method.**
- **Tree.** Every run builds its graph from the start commit's tree, `d0741cb`: `dev` at `54f1659`
  plus the spec's phase and this report's template, 583 test files. Before and after differ only in
  the script.
- **Before** is the start commit's `affected_tests.py`, copied to scratch and run as
  `--diff <rev> --graph d0741cb --explain`. **After** is this branch's script, the same way.
  **Switch** is the branch's script with `--every-mention-runs`.
- **The edit alone** is t43's `85f3426`: f5a8221's `container.py` change on its first parent, made
  with `git commit-tree`. I rebuilt it and got the same tree and parent. It is local, and nothing
  was pushed.
- **Lists** were compared with `comm` under `LC_ALL=C`. An earlier comparison mixed two collations
  and was discarded.
- **"Reach every command"** is measured directly. A scratch driver selects for a change to each of
  the 22 command modules `register_commands` registers, over one graph. A file selected for all 22
  reaches every command. It counts the always-run tests and the source readers, which every Python
  change selects.

| Diff | Before | After | Dropped | Added | Every command, before → after | Switch = before |
|---|---|---|---|---|---|---|
| `1ace4e5` #544 t25 readable impact chains | 145 | **128** | 17 | 0 | 85 → 62 | yes |
| `321b5ee` #537 scenario vocabulary | 290 | **276** | 14 | 0 | 85 → 62 | yes |
| `b3273fb` #534 t24 unlabelled plan affs | 151 | **135** | 16 | 0 | 85 → 62 | yes |
| `2a33947` #529 t17 kritikal affs | 201 | **188** | 13 | 0 | 85 → 62 | yes |
| t38's four landscape merges, summed | 787 | **727** | 60 | 0 | | |
| `8051c77` #552 t27 (t39 measured it with these) | 145 | **128** | 17 | 0 | 85 → 62 | yes |
| `85f3426` f5a8221's `container.py` edit alone | 111 | **88** | 23 | 0 | 85 → 62 | yes |

"Switch = before" compares the selected files. Three of the six `--explain` outputs name a
different first route for a few files. The walk's order is not fixed between runs, and that is
older than this task.

**Files that run the app by a mention** (a `runs` edge to `app.py`, over the same tree):
**91 → 55**, of them test files **68 → 47**.

**The 24 files dropped**, across the six diffs:

- **13 tests of landscape and measurement scripts.** Each script names the data directory
  `.debate-research` in a default path, and `scripts/stamp_build.py` does the same. That read as a
  run of the whole app (`test_count_card_boundaries.py`, `test_compare_card_clusters.py`, …).
- **7 `debate_core` tests that assert a message.** Examples: `test_caselist_parse_publish_only.py`
  (`` "`debate-research caselist parse --caselist …`" ``), `test_search_index_stage.py`,
  `test_verify_manifest.py` (`"install a newer build of debate-research to verify it"`) and
  `test_settings_environments.py` (`"~/.debate-research/dev"`).
- **3 HTTP integration tests that assert the User-Agent** (`debate-research/<version> (+contact)`):
  `test_http_fetcher.py`, `opencaselist/test_client.py` and `discovery/test_feeds.py`.
- **`tests/docs/test_restored_copy_search.py`**, which runs a runbook's `find` over
  `$HOME/.debate-research`.

**What still carries the 62.** I explained each file with a change to `commands/fetch.py`, a
command few tests name:

- **24:** the always-run list and the source readers.
- **5:** files that import `app.py`, or use a fixture that does.
- **6:** files that name `scripts/install_channel.sh`, which runs the app.
- **27:** files that run the app through a mention, or through a file they import or name that
  does. They come in four kinds:
  - **13 messages that start with the program** (Decision 1 keeps these as runs).
    `test_pull_parses_new_sources.py` (`PUBLISH_ONLY = f"debate-research caselist parse --caselist
    {CASELIST} --publish-only"`) carries 7 caselist tests that import it. Five more are the same
    kind: `test_file_build_service.py`, `test_search_index_store_check.py`, `test_sns_notifier.py`,
    `test_pull_refuses_a_newer_fingerprint_table.py` and `test_sync_runs_banners_say_what_waits.py`.
    t39's argument reading reads calls, lists, tuples and assigned constants. It does not read an
    f-string or `assert "debate-research caselist pull" in output`, so their command is not read
    and they reach every command. That is follow-up 1.
  - **3 that use the program's name alone, as a name.** `test_settings.py`, `test_docx_renderer.py`
    and `test_robots_rules.py` use it as a user agent or an author. That is follow-up 2.
  - **2 strings the rule cannot read as a sentence.** This is all that failing toward a run costs
    among the 62:
    - `test_compare_local_classifier.py`, with `"uv run debate-research caselist pull …"`;
    - `test_caselist_remove_school_view_output.py`, whose line starts `testcl26 2026-09-29:`, a
      word with no letter.
  - **9 real runs and harnesses.** `test_launchd_install.py`, `test_validate_dev.py`,
    `test_validate_dev_workflow.py` and `test_smoke_harness.py`. `test_sts_caller_identity.py` and
    `test_single_interpreter_source.py`, which name `check_image.sh` and `validate_dev.py`, scripts
    that start the program. `test_app.py` and `test_help_rendering.py`, always run anyway.
    `test_affected_tests.py`, because its synthetic world's strings are argument lists.

### Red runs

The 8 new cases are run with `-k`, which also collects 2 older cases whose names match. Each run
had a new `HYPOTHESIS_STORAGE_DIRECTORY`. The committed script was changed, then restored with
`git checkout HEAD --`, and the driver asserted a clean tree. These runs are at `6d8ac76`, and the
same at `b634e95` before the cases were strengthened.

- **Skeleton, every mention a run.** `starts_the_program` returns `True` first, with the plumbing
  and the switch in place. → `2 failed, 8 passed`: the two prose cases, each with `extra: [...]`.
  The run cases pass, as they must: they pin what may not change.
- **Skeleton, no rule.** `starts_the_program` returns `False` first. → `8 failed, 2 passed`: every
  new case but the switch's fails, with `missing: [...]`. So does t39's unreadable-registry case.
- **The start commit's script.** → `3 failed, 7 passed`: the two prose cases, and
  `--every-mention-runs`, which is a usage error there.
- **Green** → `10 passed`; the whole file → `117 passed`.

### Real runs are still runs

A `sitecustomize.py` recorder sits in scratch and loads through `PYTHONPATH`, so it is in every
xdist worker and every Python child process. It does two things:

- **Calls.** It logs each `debate_cli` source function a test calls (`sys.monitoring`, `PY_START`).
- **Starts.** It logs each `subprocess.Popen`, `os.posix_spawn` or `os.exec` whose arguments name
  `debate-research` or `debate_cli` (an audit hook).

**Positive controls:**
- `commands/test_doctor_routing_file.py` → 7,011 `debate_cli` calls.
- `tests/smoke/test_cli_smoke.py -k "version or help"` → 1 start of `.venv/bin/debate-research`.
  The smoke child runs in a clean environment, so it is seen at the start.

**The 24 dropped files:**

- **The run:** `perl hardstop.pl 115 .venv/bin/python -m pytest -m "not slow and not live" -n 4
  <the 24>` → `648 passed in 4.01s`.
- **Calls:** 0 `debate_cli` calls.
- **Starts:** 16, all from one test, `test_restored_copy_search.py`, and all `bash -c` or `zsh -c`
  over the runbook's `find … | grep -vxF -e "$HOME/.debate-research/dev" …`. None starts the
  program.

No dropped file starts the app, so none starts it on a command its merge changed. The first run,
with a filter matching only `debate-research`, gave the same result (`648 passed in 5.35s`).

### Mutation run

21 mutants. Each was applied to the committed script by an exact replacement and run against the
whole of `tests/scripts/test_affected_tests.py`, with a new `HYPOTHESIS_STORAGE_DIRECTORY` each.
No Hypothesis test is involved. Each was restored with `git checkout HEAD -- scripts/affected_tests.py`,
and the driver asserted a clean tree. The batches of four ran under the process-group hard stop,
and no workers were left after any batch.

| # | Mutant | Result |
|---|---|---|
| 1 | **PM:** a command-line string read as prose (a line that starts with the program) | caught: `missing: test_script_line.py, test_shell_command.py`. Both start the app with `subprocess`. Over the real tree it drops 13 message tests; no test there starts the app with a command-line string. |
| 2 | **PM:** an argument list read as prose (the program alone) | caught by 47 cases, each missing what runs the app: BASE's `["debate-research", "--version"]`, the world's installed-CLI smoke tests, `test_argument_list.py` and `test_which.py`. Over the real tree it drops `tests/smoke/test_caselist_pull.py` (`1ace4e5`), and `test_files_cli.py` and `test_files_publish.py` (f5a8221's edit), each run through `installed_build.py`'s `Path(sys.executable).parent / "debate-research"`. |
| 3 | **PM:** a backticked command in a sentence read as a run | caught: `extra:` the three code-span messages, and the conftest's hint |
| 4 | **PM:** an unclassifiable string read as prose (the last fallback returns prose) | caught: `missing:` the runner, assignment, operator and option cases |
| 5 | **PM, every fallback:** whatever is not a sentence taken for one | caught: the same, and both quote cases |
| 6 | a path to the program read as prose | caught: `missing: test_path_to_the_program.py` |
| 7 | a folder in a path read as the program | caught: `extra: test_folder_of_that_name.py` |
| 8 | a name the mention ends (`~/.debate-research`) read as the program | caught: `extra: test_data_directory.py` |
| 9 | the lead read from the string's start, not the line's | caught: `missing: test_script_line.py` |
| 10 | an option allowed in a sentence | caught: `missing: test_after_an_option.py` |
| 11 | any last word allowed (shell syntax) | caught: `missing:` the assignment and operator cases |
| 12 | a program that runs its arguments allowed as the last word | caught: `missing:` the runner case and the quoted-after-a-runner case |
| 13 | a runner before a code span read as running it | caught: `extra: test_shell_line_in_a_code_span.py` |
| 14 | a runner before a quote not read as running it | caught: `missing: test_quoted_after_a_runner.py` |
| 15 | a code span opening the line read as a run | caught: `extra: test_code_spans.py` |
| 16 | closed code spans kept among the sentence's words | caught: `extra: test_code_spans.py` |
| 17 | quote marks read as part of the last word | caught: `extra: test_quoted_in_a_sentence.py` |
| 18 | a quote opening the line read as prose | caught: `missing: test_quoted_with_nothing_before.py` |
| 19 | `--every-mention-runs` ignored | caught |
| 20 | a conftest's mentions read as before | caught: `extra: test_uses_the_hint.py` |
| 21 | a non-Python file (a shell script) read as prose | caught: `missing: test_runs_the_script.py` |

Before the run, three rules had no case their neighbours answered differently, and I added one for
each:
- `Path.home() / ".debate-research"`: the old case also ended in a folder;
- a script's second line after a line of words: the old first line held an option;
- a quoted program after `uv run`: the old case held an option.

A fourth check, that the text before a sentence's name ends in whitespace, could not be told from
its absence: no glued form it refused starts the program. I removed it, under agreement 8.

### What this session ran before the report (working agreement 10)

- **Affected set, after `scripts/task sync`:**
  `perl hardstop.pl 118 .venv/bin/python scripts/affected_tests.py --run` →
  `45 of 585 test files (7.7%) chosen in 12.5 s from 4 changed files`, then `2132 passed in 66.70s`
  and `pytest exited 0 after 68 s`.
  - Before the sync it chose 44 of 583 → `2129 passed in 77.07s`.
  - Each time limit used t43's perl wrapper, which kills the run's whole process group. `pgrep`
    found no leftover workers after any run.
- **Ruff:**
  - `.venv/bin/ruff format --check .` → `1636 files already formatted`;
  - `.venv/bin/ruff check .` → `All checks passed!`.
- **pyright:** `.venv/bin/pyright scripts/affected_tests.py tests/scripts/test_affected_tests.py` →
  `0 errors, 0 warnings, 0 informations`.
- **Import boundaries:**
  - `.venv/bin/lint-imports` → `Contracts: 19 kept, 0 broken.`;
  - `.venv/bin/python scripts/check_thin_handlers.py` → `OK: 68 CLI command and API route handlers
    within 25 statements`.
- **Specs:** `uv run scripts/validate_specs.py` → `OK: 524 files, 41 epics, 461 tasks, 22 releases`.
- **Docs checks**, on this report: under [Final checks](#final-checks).

### Final checks

- `uv run --frozen python scripts/check_links.py` → `OK: 3044 relative links and anchors in 470
  Markdown files`.
- `uv run --frozen python scripts/check_command_blocks.py --base origin/dev` → `OK: no # comments
  in 592 shell code blocks in 199 Markdown files (1 session reports changed since origin/dev)`.
- `uv run --frozen python scripts/docs_index.py --check-descriptions` → `All 59 indexed documents
  under docs/ have a description`.

## Files changed

- **`84b2894`, the rule and its cases:**
  - `scripts/affected_tests.py`:
    - `starts_the_program` and `reads_as_a_sentence`, and the constants they read;
    - `Resolver.runs_of`, which takes a file's strings and reads each on its own;
    - `Tree.strings` and `strings_in`, which `literals` and `literals_in` now join;
    - `--every-mention-runs`, carried through `select`, `build_graph` and `Resolver`;
    - the docstring's "Runs." paragraph.
  - `tests/scripts/test_affected_tests.py`: a section of 8 cases over t39's CLI world, with
    synthetic files only.
- **`dc4d946`:** the three cases that make a rule's mutant visible, and the whitespace check
  removed.
- **`bade2a1`:** the docstrings name the User-Agent; the Goal's phase is `Succeeded`.
- **This report.**

The measurements and red runs were taken at `b634e95` and `6d8ac76`, which the sync rewrote as
`84b2894` and `dc4d946` with the same content. `bade2a1` changes only docstrings.

## Deviations from the spec

None. The spec on `dev` gained `context` prerequisites mid-session (t39 and t43, from #653, the
PM's dependency audit). Both are `Succeeded`, and I synced with `scripts/task sync` before the
report.

## Decisions and assumptions

1. **The rule.** It reads each string literal of a Python file on its own, docstrings left out as
   before, on the line of the string where the name stands. The text from the line's start to the
   name is the *lead*.
   - **Not the program at all:**
     - a name that ends another (the lead ends in `.`: `~/.debate-research`);
     - a name a slash goes on from: a folder (`/var/lib/debate-research/dev`), or the User-Agent
       `debate-research/0.0.0-test (+…)`.
   - **A run,** in each of these cases:
     - the string is the program alone: an argument list's first element, `shutil.which(...)`,
       `bin / "debate-research"`;
     - the lead is empty or whitespace: a string or a line that starts like a command line,
       `"debate-research caselist parse …"`, or a line of a script a test writes;
     - the lead ends in a path separator: `f"{bin}/debate-research"`,
       `"$HOME/.local/bin/debate-research"`;
     - the lead is not a sentence, which is the fallback (below). That covers
       `"aws sso login && debate-research …"`, `"DEBATE_ENV=dev debate-research …"`,
       `"uv run debate-research …"`, `"sudo -u x debate-research"`, `'ENTRYPOINT ["debate-research"]'`,
       `"(debate-research …)"` and a quote that opens the line.
   - **Prose:**
     - a sentence before the name: `"Fix: debate-research caselist pull"`,
       `"install a newer build of debate-research to verify it"`;
     - a sentence before the code span that holds it: ``"Run `debate-research caselist parse …` and `…`"``.
       Closed spans before it count as one word, so their options do not count;
     - a sentence before the quote that holds it: `"Run 'debate-research doctor' first"`.
   - **A sentence** has at least one word, no word that starts with `-`, and ends in a word of
     letters (an apostrophe or a hyphen inside, one closing `.,:!?)`) or a dash (`—`, `–`). For
     plain text and quotes, that last word may not be a shell keyword or a program that runs its
     arguments: `run`, `exec`, `env`, `sudo`, `xargs`, `sh`, `bash`, `python` and the rest of
     `RUNS_ITS_ARGUMENTS`. Shell is case-sensitive, so `Run` starts a sentence and `run` runs.
     Before a code span a runner may end the sentence (``Never run `…` ``): the words are about the
     span, and in a shell the span would be substitution whatever came before it.
   - **Fail toward a run.** The PM's wording made any "text before the command" prose. The rule
     asks for a sentence instead, because a shell line has text before the program too
     (`uv run`, `X=1`, `&&`). So a message such as `"after the login: DEBATE_ENV=dev
     debate-research tub index publish"` stays a run. Among the 62, two files stay only for this.
2. **A code span that opens the line is prose.** ``f"`debate-research caselist parse --caselist
   {slug} --publish`"`` is the fragment a message joins into its sentence (`" and ".join(...)`).
   The PM's example is that shape. Two of the 24 dropped files need this reading and no other:
   `test_caselist_parse_publish_only.py` and `test_search_index_stage.py` in `debate_core`. A shell would read a
   leading backtick as command substitution of the program's own output, which nobody writes. This
   goes one step past "within a sentence", so it is PM question 1.
3. **Non-Python files are read whole, as before.** In a shell script, workflow or template any
   mention runs. Their lines are commands more often than prose, and the change was asked for
   Python tests.
4. **t39's per-command reading is unchanged.** A mention that runs goes on to t39's argument
   reading exactly as before. A command-line string such as `"debate-research caselist parse …"`
   names `caselist parse` where t39 reads it.
5. **`--every-mention-runs` is the switch back.** It reads every mention in a string as a run, as
   `--whole-container` does for t43. It matched the start commit's selections on all six diffs and
   the every-command set (85). CI's call is unchanged.
6. **Measured over the start commit's tree, `d0741cb`.** `origin/dev` moved to `f32a15e` during
   the session, adding test files (583 → 585) but nothing in `scripts/` or `tests/scripts/`.

## Operator follow-ups

None. Every check ran in the session, including the run check over the dropped files.

### PM questions

```text
PM questions from v1-e01-t44 (a debate-research mention in a message read as prose)

1. A code span that opens the line is read as prose (Decision 2).
   f"`debate-research caselist parse --caselist {slug} --publish`" is the fragment a message joins
   into its sentence. Your wording made a backticked command prose "within a sentence". This reads
   it as prose with nothing before it as well. Two of the 24 dropped files need it and no other
   reading (debate_core's test_caselist_parse_publish_only.py and test_search_index_stage.py).
   No real run starts with a backtick: in a shell it would substitute the program's own output.
   Options: (a) accept; (b) only a span with a sentence before it is prose, which keeps those 2
   selected for every command.
   Recommendation: (a). The backticks are positive evidence of a message, and every mutant around
   the span rule is caught.
```

## Follow-up work

1. **t39's argument reading could read a run-shaped string wherever it stands** (E01). It reads the
   words of calls, lists, tuples and assigned constants. It does not read an f-string's literal
   head (`f"debate-research caselist parse --caselist {x} --publish-only"`) or a string in a
   comparison (`assert "debate-research caselist pull" in output`). Those mentions are runs as
   ruled, so they reach every command: `test_pull_parses_new_sources.py`, the 7 tests that import
   it, and 5 more, 13 of the 62 files. Reading those words would name `caselist parse` and
   `caselist pull` for them.
2. **The program alone could be a run only where a program is started from** (E01): an argument
   list's first element, a call's positional argument, an operand of `/`. As a keyword value or in
   an `==` comparison (`user_agent == "debate-research"`) it is a name. That is 3 of the 62
   (`test_settings.py`, `test_docx_renderer.py`, `test_robots_rules.py`). It is a narrowing of what
   the PM ruled a run, so it needs its own mutants.
3. **t39 reads a shell script's words with their quotes on** (E01, low). A script running
   `debate-research caselist 'remove'` names `caselist` and `'remove'`. So it would be reached for
   neither `caselist remove` nor every command, which is the forbidden direction. No script in the
   repository quotes a command word today (`git grep` over `*.sh`, workflows and templates), and
   this task's shell-script case avoids it. Stripping the quotes before matching would close it.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-01

**Notes:**

A `debate-research` mention inside a sentence is now prose, and anything the rule cannot read as a
sentence is still a run. That gives a real cut, measured with care.
1. **ac1 passes.**
   * The files that reach every command fell from 85 to 62. t38's four landscape merges fell from
     787 files to 727, and f5a8221's edit alone from 111 to 88. Every after-list is a subset of its
     before-list.
   * The run check over the 24 dropped files: 648 passed, with 0 `debate_cli` calls and no start of
     the program. Both sides of the recorder fired on positive controls.
   * The collected count is unchanged: 0 lost, 8 added.
   * The red runs were against two skeletons and the start commit's script.
   * 21 mutants were caught. Mutants 1 and 2 catch the forbidden item, and over the real tree
     mutant 2 drops exactly the smoke checks that start the installed build.
   * Removing the whitespace check, which no mutant could tell from its absence, is agreement 8
     applied properly.
2. **The PM question: (a).** A code span that opens the line is prose. The backticks are positive
   evidence of a message, no real run starts with one, and the mutants around the span rule are all
   caught.
3. **Decisions accepted:**
   * a sentence, not "any text before", as the test for prose, because a shell line has text before
     the program too;
   * non-Python files read whole;
   * t39's per-command reading unchanged;
   * `--every-mention-runs` as the switch back, matching the start commit on all six diffs;
   * measuring over the start tree.
4. **Follow-ups 1, 2 and 3:** one p3 task in E41, the delivery-tooling epic.
   * t39's argument reading reads a run-shaped string in an f-string's head or a comparison.
   * The program alone is a run only where a program is started from, with its own mutants.
   * A shell script's command words are read with their quotes stripped.

   The last is the forbidden direction, latent today, and cheap to close.
5. **Closing checks:** the affected set ran whole within the limit after the sync (45 files, 2,132
   passed), and the whole-repo checks pass.
6. **Merge:** once the PR's `ci` is green. It is a plain `scripts/task pr`. With it, E01's last open
   task is done, and E01's Succeeded is true again.
