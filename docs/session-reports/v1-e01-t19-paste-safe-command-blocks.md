# Session report: v1-e01-t19-paste-safe-command-blocks

| | |
|---|---|
| Task | `v1-e01-t19-paste-safe-command-blocks` — Command blocks in the docs are safe to paste into zsh |
| Spec | [`plan_specs/v1/e01-repo-foundation/t19-paste-safe-command-blocks.yaml`](../../plan_specs/v1/e01-repo-foundation/t19-paste-safe-command-blocks.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t19-paste-safe-command-blocks` |
| Session status | COMPLETE |

## Summary

`scripts/check_command_blocks.py` fails on any `#` that interactive zsh would pass on as an
argument, meaning an unquoted `#` at the start of a word, inside a `bash`, `sh`, `zsh`, `shell` or
`console` block. It names the file and the line. It runs in CI's `spec-validate` job on every
trigger. On a pull request it also reads the session reports the pull request adds or changes,
diffed against the base branch, and the job now checks out full history so it can. It refuses to
pass unless every runbook, `task-workflow.md` and the labeling guide were scanned. Measured first
on `origin/dev`'s tree, it found **47 comments in 11 files**. All 47 are fixed by moving the text
into the prose, and the check now passes over 185 blocks in 107 files. The kickoff prompt has a new
item 8 that states the rule and links working agreement 9. **Look first at Deviations:** the check
scans every tracked Markdown file, not just the three groups `ac1` names, because `CONTRIBUTING.md`
is a file people paste from and the forbidden list does not allow exempting it.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `check` — Check, fix, and tell the sessions | Done | Measured on `origin/dev`'s tree (47), built the check and its tests, fixed all 47, wired CI, added the prompt line, showed a planted comment failing and then passing |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — a check run in CI scans the shell blocks, names file and line, allows `#!`/quotes/`${#var}`, cannot pass by scanning nothing | PASS | `uv run --frozen python scripts/check_command_blocks.py --base "origin/${BASE_REF}"` with `BASE_REF=dev` (CI's step, run locally) → ``OK: no `#` comments in 185 shell code blocks in 107 Markdown files (1 session reports changed since origin/dev)``, exit 0, 0.10 s. With the parser stubbed to find nothing → 8 `coverage:` lines, one per required file with a shell block, plus `no shell code blocks were scanned at all`, exit 1 (see [the mutation runs](#the-mutation-runs)). The wiring is pinned by `test_ci_runs_the_check_with_the_pull_requests_base_and_its_history`. The step's first run on GitHub is this pull request's `ci`. |
| ac2 — session reports are checked only when the pull request adds or changes them | PASS | The CI invocation above scans exactly 1 report, this one. The 70 historical reports hold 37 comments across 10 reports, listed below, and the run passes over them without editing any. Planting a comment in this report → `docs/session-reports/v1-e01-t19-paste-safe-command-blocks.md:70: …`, exit 1. Editing a historical report in the working tree makes it "changed", so it is scanned (`…v1-e29-t06-removal-grant-scope-test.md:426`, exit 1), which is what ac2 says. Five tests in a temporary git repository cover added, changed, uncommitted, base-moved-on and historical reports. |
| ac3 — every instance found is fixed by moving the comment into the prose; shown failing on a planted comment and passing once removed | PASS | Before: 47 findings (per-file table below). After: 0. Planted `WT=/path/to/your/checkout          # e.g. .../v1-e29-t03-evidence-buckets` in `docs/runbooks/evidence-store.md` → ``docs/runbooks/evidence-store.md:82: zsh passes `# e.g. .../v1-e29-t03-evidence-buckets` to the command as arguments; …``, exit 1. Removed → `OK: …`, exit 0. Files restored byte for byte (`cmp`), `git diff --quiet HEAD`. |
| ac4 — the prompt from `task_helper.py` says operator command blocks contain no `#` comments because the operator's shell is zsh, and links working agreement 9 | PASS | New item 8 in `PROMPT` (`scripts/task_helper.py`). `test_the_kickoff_prompt_tells_sessions_the_rule_and_links_agreement_9` asserts ``no `#` comments``, `operator's shell is zsh` and `docs/process/working-agreements.md#9-command-blocks-are-safe-to-paste-into-zsh`, and that the heading the anchor points at exists. `check_links.py`: `OK: 1273 relative links and anchors in 177 Markdown files`. |
| Node `check` — "Shown failing and passing" | PASS | Same as ac3. |

Other checks run:

* CI's pytest selection: `uv run --frozen pytest -n auto --cov -m "not slow and not live"` →
  `4495 passed, 1 skipped, 1 warning in 93.09s`. The skip is the existing parser eval, which is
  waiting on human corrections. Measured at 95 s wall-clock, so I ran it in the session.
* `uv run --frozen ruff check .` → `All checks passed!`. `ruff format --check .` →
  `521 files already formatted`.
* `uv run scripts/docs_index.py --check-descriptions` → `All 30 indexed documents under docs/ have a description`.
* `uv run scripts/validate_specs.py` → `OK: 310 files, 38 epics, 252 tasks, 20 releases`.
* `tests/scripts/test_check_command_blocks.py`: 82 tests.
* After this report was written, CI's step was run again over the finished branch →
  ``OK: no `#` comments in 186 shell code blocks in 107 Markdown files (1 session reports changed since origin/dev)``.
  The extra block is this report's own operator block, which passes.

### The measurement, before any fix

The branch was created from `ff9e822`. Since then `origin/dev` has gained one commit (`cee3587`,
the generated-files refresh), which touches only `ROADMAP.md`, and that file has no code blocks. So
the Markdown in this worktree at the start commit was identical to `origin/dev`'s. I ran the check
there before editing any document:

| File | Comments |
|---|---|
| `README.md` | 12 |
| `docs/runbooks/evidence-store.md` | 6 |
| `docs/runbooks/caselist-removal.md` | 6 |
| `docs/guides/evidence-store-cli.md` | 6 |
| `CONTRIBUTING.md` | 5 |
| `docs/runbooks/terraform-bootstrap.md` | 5 |
| `docs/process/task-workflow.md` | 2 |
| `packages/debate_core/README.md` | 2 |
| `docs/runbooks/aws-account-baseline.md` | 1 |
| `docs/guides/coach-website-editing.md` | 1 |
| `packages/debate_core/src/debate_core/testing/contracts/README.md` | 1 |
| **Total** | **47** |

All 47 are fixed. The check now reports 0, so the two counts match. I also listed every `#` the
check *allowed* inside a scanned block, to look for false negatives. There was exactly one:
`${DOMAIN##*.}` in `docs/runbooks/team-website.md:188`, a suffix removal, which is correct.

The historical session reports, which are not scanned and not edited, hold 37 comments:
`v1-e01-t12` 13, `v1-e01-t08` 6, `v1-e34-t01` 6, `v1-e01-t04` 4, `v1-e36-t04` 2, `v1-e36-t05` 2,
and 1 each in `v1-e01-t09`, `v1-e34-t02`, `v1-e36-t08` and `v1-e37-t05`.

### The rule against real zsh

Each case body in the test tables `REFUSED` (19) and `ALLOWED` (19) is harmless to run: a
`print -rl --`, `true`/`false`, or a `cat` with a heredoc. I piped each body into `zsh -f -i`
(zsh 5.9, arm64-apple-darwin25.0) twice, once after `setopt nointeractivecomments` and once after
`setopt interactivecomments`, from an empty temporary directory, and compared stdout and stderr.
The runs differ exactly when zsh passed a `#` word on that it would otherwise have dropped as a
comment. The script lived in the session scratchpad, not in the suite, because CI has no zsh.
Result: **37 of 38 agree**.

* Refused, zsh splits a `#` word out, check flags it (19/19): trailing comment
  (`status | --porcelain | # | must | print | nothing`), whole-line, indented whole-line, after a
  tab, a bare `#`, `;#`, `&&#`, `|| #`, `|#`, a continuation line, inside `( … )`, inside `$( … )`,
  inside backticks, `#!` after the first line, after a heredoc terminator, after a here-string,
  after a closing quote, two in one block, and one per line when the first holds an apostrophe.
* Allowed, zsh does not split, check does not flag (18/19): single, double and `$'…'` quotes, `\#`,
  `$#`, `${#PATH}`, `${PATH#/usr} ${PATH##*/}`, `"${PATH% #}"`, `…/page#anchor a#b`, a quoted
  substitution with its own quotes, `$(( 1 + 2 ))`, quoted, unquoted and `<<-` heredocs, two
  heredocs on one line, a quoted string spanning lines, `a\ #b`, and `a\` + newline + `#b`, which
  zsh joins into one word, `a#b`.
* **The one disagreement is `#!` on a block's first line.** It is allowed by the PM's decision, but
  zsh does not treat it as a comment: pasted, `#!/usr/bin/env bash` fails with
  `zsh: event not found: /usr/bin/env` (history expansion of `!`). The allowance is for blocks that
  show a script file's contents. No scanned block starts with a shebang today, so it is latent.
  See Follow-up work.

### The mutation runs

All four ran in CI's own invocation (`--base origin/dev`). Every touched file was committed first,
saved, then restored and compared with `cmp`.

1. Planted comment in a runbook: fails at `docs/runbooks/evidence-store.md:82`, exit 1. Removed:
   `OK`, exit 0.
2. `shell_blocks` replaced by a function that returns nothing: `0 blocks in 107 Markdown files`,
   eight `coverage: … has a shell code block, but none was scanned` lines (six runbooks,
   `task-workflow.md`, the labeling guide), plus `coverage: no shell code blocks were scanned at all`,
   exit 1. The old arrangement, with no check at all, would have passed this.
3. A comment appended to this report: fails at
   `docs/session-reports/v1-e01-t19-paste-safe-command-blocks.md:70`, exit 1.
4. The same comment appended to `v1-e29-t06`'s report, uncommitted: scanned because it is now
   changed, and fails at line 426, exit 1.

The tests cover the other ways the check could pass vacuously. A git listing that returns nothing
fails with three `was not among the scanned files` lines. An untracked runbook fails. A missing
required file fails. A `--base` with no shared history exits 2 and names `fetch-depth: 0`; it does
not pass.

## Files changed

* `scripts/check_command_blocks.py` (new): the check. It has no dependencies outside the standard
  library.
* `tests/scripts/test_check_command_blocks.py` (new): the refused and allowed cases, block and
  console selection, file selection in temporary git repositories, the coverage assertions, this
  repository, the CI wiring, and the prompt.
* `.github/workflows/ci.yml`: `spec-validate` has its own checkout with `fetch-depth: 0` and a
  `check_command_blocks.py` step. `BASE_REF` is passed through `env`, never interpolated into the
  script.
* `scripts/task_helper.py`: item 8 in the kickoff prompt (ac4).
* `docs/process/working-agreements.md` § 9: its last bullet said the check was yet to be added; it
  now names the script and what it reads.
* Fixes (ac3), with no command changed: `docs/runbooks/{evidence-store,caselist-removal,terraform-bootstrap,aws-account-baseline}.md`,
  `docs/guides/{evidence-store-cli,coach-website-editing}.md`, `docs/process/task-workflow.md` § 4
  (the v1-e01-t16 and v1-e01-t18 text is unchanged), `README.md`, `CONTRIBUTING.md`,
  `packages/debate_core/README.md`, `packages/debate_core/src/debate_core/testing/contracts/README.md`.
* `plan_specs/…/t19-paste-safe-command-blocks.yaml`: phase `Succeeded`.

## Deviations from the spec

1. **Scope of files: every tracked Markdown file, not only the three groups `ac1` names.** `ac1`
   lists `docs/` (except session reports), every README, and the labeling guide. But
   `CONTRIBUTING.md` has a `scripts/task` block that people paste from, with five trailing
   comments, and `constraints.forbidden` says "Exempting a file a person is told to paste from".
   So the forbidden list governs: the check reads every file `git ls-files '*.md'` reports, except
   historical session reports. That adds `CONTRIBUTING.md`, the two fixture `MANIFEST.md` files
   (already clean), `CLAUDE.md`, `ROADMAP.md` and `plan_specs/README.md` (no shell blocks). The PM
   may want to amend `ac1`'s wording to match.
2. **Files outside `constraints.packages`.** `.github/workflows/ci.yml` (ac1 requires the check
   to run in CI, and the PM asked for the checkout history), `README.md` (a README `ac1` names,
   with 12 findings ac3 requires fixed), and `CONTRIBUTING.md` (Deviation 1). None of them is in
   `[scripts, tests/scripts, docs, site/README.md, packages, tests/fixtures]`.
3. **Block tags: `shell` added** to `ac1`'s list (`bash, sh, zsh, console`), per the PM's decision.

## Decisions and assumptions

* **After a comment, the rest of the line is skipped.** zsh would read on, so `# don't` opens a
  quote that swallows the following lines. Following zsh there would hide every later comment
  until the first was fixed, and the before and after counts would not match. Skipping the line
  reports each comment once.
* **Console blocks.** A `$ ` or `% ` prompt starts a command. The lines that continue it (a
  trailing backslash, an open quote, a heredoc body) are part of that command, so a continued line
  is checked and a heredoc body is skipped. Every other line is output and is never checked. That
  reads the PM's "only lines starting with a prompt are commands" as including a command's own
  continuation lines. The repository's four `console` blocks are all in
  `packages/debate_cli/README.md`.
* **A fence nested inside another fence is content**, as Markdown renders it. The ```` ```bash ````
  example inside working agreement 2's ````` ````markdown ````` block is therefore not scanned
  separately. It holds no comment. Fences indented inside list items, and `~~~` fences, are read.
* **Required files are found on disk, not in the git listing.** The minimum is every
  `docs/runbooks/*.md` on disk plus `task-workflow.md` and the labeling guide. If any is missing
  from the scan, the check fails. A local, untracked new runbook therefore fails the check until it
  is `git add`ed, and the message says so. "Has a block" is decided by a separate one-line regex,
  so a parser bug cannot remove both the block and the expectation of one.
* **Push and dispatch runs scan no session reports.** They have no base branch, and the pull
  request already checked its reports.
* **How the comments were moved.** A placeholder's example (`WT=…`) moved to the sentence above the
  block. Expected results (`"No changes."`) moved to the sentence before the block. Explanations
  (`AWS_PAGER`, `KEY_ID`, `terraform fmt`) went into the paragraph that introduces the block. Pairs
  meant to run apart, such as dry run then `--apply`, `--apply --confirm-prod`, and the two
  `caselist` verification steps, became separate blocks with a sentence each. One-time setup
  (`pre-commit install`, `cp .env.example .env`) is now in its own block, as agreement 9 asks. The
  two `brew trust` lines ran only "if brew refuses" and are now that sentence in the prose. A paste
  of the block no longer runs them unconditionally.
* **`fetch-depth: 0` cost.** `origin/dev` has 305 commits, about 13 MiB of objects on disk, so a
  full fetch should add seconds to `spec-validate`. The real figure is visible only in this pull
  request's run.

## Operator follow-ups

None to run. When `scripts/task pr` opens the pull request, the `spec-validate` job's
`check_command_blocks.py` step is this check's first run on GitHub. It should print
``OK: no `#` comments in 186 shell code blocks in 107 Markdown files (1 session reports changed since origin/dev)``.
That is 186 rather than the 185 recorded under ac1, because this report's own block below is
counted.
If it exits 2 naming `fetch-depth: 0`, the checkout did not fetch `origin/dev`. That fails `ci`
rather than passing.

To run the check yourself from the task worktree:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e01-t19-paste-safe-command-blocks
uv run scripts/check_command_blocks.py --base origin/dev
```

## Follow-up work

1. **The `#!` allowance (E01, PM decision).** zsh does not ignore a pasted shebang: it reports
   `event not found`. The allowance is right for a block that shows a file's contents and wrong for
   one meant to be pasted. Nothing uses it today. The PM could keep it, or allow it only in a block
   the prose says to save as a file.
2. **Historical reports with comments (records, not to be edited).** Ten reports hold 37 comments.
   Whoever follows one of their operator blocks again, for example `v1-e01-t12`'s promotion-guard
   rerun with 13, will paste broken commands. A runbook that supersedes such a block is the fix,
   not an edit to the record.
3. **A pre-commit hook** running `scripts/check_command_blocks.py` would catch a comment before CI
   does. It is cheap (0.1 s), but it was not asked for (E01 tooling).
4. **Untagged blocks, and `console` blocks without prompts, are not checked**, per the PM's
   decision. Neither hides a comment today. The two untagged runbook blocks are a checklist
   (`team-website.md:938`) and a spreadsheet formula (`website-content-accounts.md:135`). But
   `packages/debate_cli/README.md:248` is a `console` block whose one command, `uv run pytest
   packages/debate_cli/tests`, has no `$` prompt, so the check reads it as output. A future
   comment there would pass. Tagging that block `bash`, or requiring a tag on every fence in
   `docs/runbooks/`, would close the gap.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
