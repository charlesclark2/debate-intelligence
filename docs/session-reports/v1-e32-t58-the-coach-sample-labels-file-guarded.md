# Session report: v1-e32-t58-the-coach-sample-labels-file-guarded

| | |
|---|---|
| Task | `v1-e32-t58-the-coach-sample-labels-file-guarded` — The coach's labels file is guarded: a changed file is refused, and every sitting keeps the file it replaces |
| Spec | [`plan_specs/v1/e32-argument-landscape/t58-the-coach-sample-labels-file-guarded.yaml`](../../plan_specs/v1/e32-argument-landscape/t58-the-coach-sample-labels-file-guarded.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t58-the-coach-sample-labels-file-guarded` |
| Session status | COMPLETE, Goal left `InProgress` until the operator's one-time step (below) <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The coach's labels file now has a sidecar beside it, `<name>.sha256`: one line in the format
`shasum -a 256` prints. Every command that reads the file checks it first: `landscape evaluate` in
every mode, the relabel sitting, and `compare_local_classifier.py score-sample`. Each refuses a file whose
SHA-256 differs (`LABELS_FILE_CHANGED`, exit 1), a file with no sidecar (`LABELS_DIGEST_MISSING`, whose
hint gives the one-time step) and a sidecar it cannot read (`LABELS_DIGEST_UNREADABLE`). Each refusal names
both digests shortened to 12 hex digits, the sidecar's path and `uv run python scripts/relabel_coach_sample.py`.
A sitting writes three things in order: a dated copy of the file it replaces (never over an existing copy),
then the CSV through `.incoming` and `os.replace`, then the sidecar. The one-time step is a new script,
`scripts/record_coach_sample_digest.py`. It records only the digest `--expect` gives and never overwrites
a sidecar. The tests use invented labels only. They were shown failing first against a skeleton that
checks nothing (35 failed), and all 18 mutants on the digest check and the write order are caught. ac1
passes. **The Goal stays `InProgress`, as the PM asked, because the one-time step for the coach's real
file is an operator follow-up:** its block is below and in the record runbook. Look first at the sidecar
format, at the decision to make `--expect` required, and at follow-up 1: the file a sitting *writes*
still has no copy until the next sitting.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `the-coach-sample-labels-file-guarded` (Labels file guard) | Done | Its criterion passes (below). Commits `f2fc74c` (wiring, tests, refuse-nothing skeleton), `0d043a4` (the guard), `179a100` (runbooks, handler budget), and the report commit. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a changed labels file is refused by every scoring, replay and re-record command, naming both digests; a sitting keeps a dated copy and records the new SHA-256; tests on invented labels, shown failing first | PASS | Red, on `f2fc74c`'s skeleton: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n 0 -q --tb=line packages/debate_core/tests/application/test_coach_sample_labels_file.py tests/scripts/test_relabel_coach_sample_labels_guard.py tests/scripts/test_record_coach_sample_labels_digest.py packages/debate_cli/tests/test_landscape_evaluate_labels_guard.py tests/scripts/test_compare_local_classifier.py` → **35 failed, 20 passed** ([the red run](#the-red-run)). Green, the same command on `0d043a4` → **55 passed**. The new smoke check, red on the skeleton → the LF-resaved file was scored, exit 0; green → passed. Mutants: 18 of 18 caught ([the mutants](#the-mutants)). |
| Node: Labels file guard tests pass (`uv run pytest tests/scripts packages/debate_core/tests -k labels`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run pytest tests/scripts packages/debate_core/tests -k labels` → **166 passed** in 53.7 s (wall 54.6 s). |

### The red run

The skeleton (`f2fc74c`) had the module's whole API, with the callers already wired to it, but it checked
nothing. `check_labels` returned the digest without reading the sidecar. The copy kept the old fixed name
(`.before-stance-relabel.csv`) and overwrote it. A sitting wrote no sidecar, and the one-time step wrote
the sidecar whether or not one was there. Every one of the 35 failures was for its reason:

* **CLI (9):** every mode, the panel included, built the evaluation past the guard. The stub raises when
  built, so the JSON showed `INTERNAL_ERROR`/`AssertionError` and not `LABELS_FILE_CHANGED` or
  `LABELS_DIGEST_MISSING`.
* **Core (21):** no `LabelsFileChanged`, `LabelsDigestMissing` or `LabelsDigestUnreadable` was raised; the
  copy was the old fixed name; no sidecar was written after the CSV; the one-time step overwrote a sidecar
  and recorded an unexpected digest.
* **Scripts (5):** the sitting ran on a changed file and on a file with no sidecar (exit 0, not 1). It wrote no
  sidecar. The one-time script exited 0 on an existing sidecar and on the wrong digest. `score-sample`
  scored a changed file (exit 0, not 2).

The 20 that passed on the skeleton were the existing `compare_local_classifier` tests (10), plus format and
positive cases the skeleton already met: the sidecar's name and line, a matching file read with its CRLF
endings, a sidecar line without its newline, a matching one-time record, `--expect` validation (3), and
Ctrl-C writing nothing.

**The smoke check against the skeleton:** the recorded sample was rewritten with LF line endings in place of
its CSV writer's CRLF. The replay then **scored it, 4 of 4 and exit 0**. That is the silent mismatch this
task closes.

### The mutants

Each mutant was committed alone, run with `-n 0` against the guard's test files, and taken out with
`git reset --soft HEAD~1` and `git checkout HEAD -- <file>`. The tree and `HEAD` were checked unchanged
afterwards. No test here uses Hypothesis, so agreement 8's fresh database does not apply. Two runs took
10.6 s and 29.1 s.

| Mutant | Caught by |
|---|---|
| The digest comparison skipped | 12 tests: the four changed files, every CLI mode, the sitting, `score-sample` |
| A missing sidecar passes | 6 tests: core, the sitting, the CLI modes |
| The sidecar line loosened (any case, any whitespace, no name) | the unreadable cases upper-case hex, one space, no name |
| The sidecar matched at its start only (`match` for `fullmatch`) | the unreadable case two lines |
| The labels read a second time after the check (`read_text`) | the CRLF read test (universal newlines changed the text) |
| `landscape evaluate` reads without the guard | 9 CLI tests (every mode, changed and missing) |
| `score-sample` reads without the guard | `test_score_sample_refuses_a_labels_file_its_sidecar_does_not_record` |
| The sitting starts without the guard | both refusal tests of the sitting |
| The sidecar written before the CSV | the order test; the stopped-before-the-sidecar test |
| The dated copy kept after the CSV | the order test; the stopped-before-the-CSV test |
| No dated copy | 5 tests |
| The copy opened `wb`, not `xb` (overwrites a copy of the same minute) | the same-minute test; the copy-already-there test |
| The copy holds the new labels | 5 tests |
| The copy named by the date only | 5 tests (exact names) |
| The CSV written in place, not through `.incoming` | 3 tests (the order test saw no rename) |
| The sidecar records the replaced file's digest | 3 tests, the sitting's script test among them |
| The one-time step opens the sidecar `w`, not `x` | both "refuses an existing sidecar" tests |
| The one-time step records any digest | both "not the expected one" tests |

### Checks before the report

| Command | Result |
|---|---|
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run` | **Stopped at its 115 s limit (exit 124)** while the Mac's load average was 28 to 57, from another session. The set is 130 of 723 test files (18.0%), 19 changed files. By agreement 10 it is left to the pull request's `ci`, which runs the same set. |
| Always-run list: `... pytest -m "not slow and not live" tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py` | 378 passed, 26.2 s |
| The affected set's files in the directories this task changed (67 files: `tests/scripts`, `packages/debate_cli/tests`, `packages/debate_core/tests/application` top level, `tests/smoke`, `tests/docs`) | 2787 passed, 104.5 s |
| Every changed or new test file, with `tests/smoke/test_landscape_evaluate_smoke.py` | 213 passed, 13.3 s; after the handler change, the three CLI landscape files: 139 passed |
| What the affected set has that was not run here | Its `application/caselist` tests (30), `tests/integration`, and the `evidence`, `retrieval` and `integrations` tests. `--explain` says they are reached by a test that names `docs/runbooks/landscape-model-evaluation-record.md` by path, and through `debate_cli.app` registering `commands/landscape.py`. They are left to `ci`. |
| `uv run ruff format --check` and `uv run ruff check` (`packages/debate_core packages/debate_cli scripts tests/scripts tests/smoke`) | clean |
| `uv run pyright packages/debate_core packages/debate_cli` + the three scripts, the new script tests and the smoke file | 0 errors |
| `uv run --frozen lint-imports` | 20 kept, 0 broken |
| `uv run --frozen python scripts/check_thin_handlers.py` | OK: 72 handlers within 25 statements. It first failed with `evaluate` at 26; [Decisions](#decisions-and-assumptions) has the fix. |
| `uv run python scripts/check_command_blocks.py`, `scripts/check_links.py`, `scripts/docs_index.py --check-descriptions` | OK (692 blocks, 3707 links and anchors, 69 descriptions) |
| `uv run scripts/validate_specs.py` | OK: 655 files, 41 epics, 592 tasks, 22 releases |

## Files changed

* **`packages/debate_core/src/debate_core/application/coach_sample_labels_file.py` (new):** the guard. It
  holds the sidecar's path and line, `read_labels_file` (the bytes are read once, checked, then decoded:
  nothing changes between the check and the read), the refusals, `keep_dated_copy`, `write_sitting` and
  `record_first_digest`. It reads no row.
* **`coach_sample_relabel.py`:** `copy_path` and `COPY_SUFFIX` (the single `.before-stance-relabel.csv`
  copy) removed. Its one test is removed too.
* **`debate_cli/commands/landscape.py`:** `evaluate` reads the labels once, through the guard, before any
  mode branches. `--check-sample` gets the text it read. The module docstring names the three codes.
* **`scripts/relabel_coach_sample.py`:** the guarded read at the start and `write_sitting` at the end. It
  prints the copy's path and the new digest above the last line, which stays counts only.
* **`scripts/record_coach_sample_digest.py` (new):** the one-time step.
* **`scripts/compare_local_classifier.py`:** `score-sample` reads through the guard. Its removed-source note
  no longer says to delete rows from the labelled file.
* **Tests:**
  * new: `test_coach_sample_labels_file.py` (core), `test_landscape_evaluate_labels_guard.py` (CLI),
    `test_relabel_coach_sample_labels_guard.py` and `test_record_coach_sample_labels_digest.py` (scripts),
    plus a refusal test in `test_compare_local_classifier.py` and in the smoke file;
  * changed: the existing CLI, route, script and smoke helpers that write a sample now write its sidecar.
* **`docs/runbooks/landscape-model-evaluation-record.md`:** a section "The labels file is guarded". It says
  the file is opened only through the script and never in a spreadsheet app, gives the codes, the dated
  copies, the read-only line, and the one-time block. The sitting block now refuses while Excel runs and
  runs `chmod u+w` before the sitting and `chmod a-w` after it, whether it finished or stopped. "Fix the
  sample" became "tell the PM".
* **`docs/runbooks/landscape-model-evaluation-replay.md`:** the two refusals, under what the replay reads
  and what to read.

## Deviations from the spec

1. **`tests/smoke/test_landscape_evaluate_smoke.py` is outside `constraints.packages`.** It had to change:
   its sample had no sidecar, so all three of its checks would have failed. Agreement 5 also asks for a
   smoke check of a changed surface, so it gains `test_landscape_evaluate_refuses_a_labels_file_its_sidecar_does_not_record`.
2. **`score-sample` is guarded too.** The brief named `landscape evaluate` and the scripts that take
   `--sample`. `score-sample` takes `--labels`, but it scores against the coach's labels, and the spec's
   forbidden list says "A scoring command that reads a labels file without the check". The forbidden list
   wins. So a file passed to `score-sample` needs its sidecar too: recorded by a sitting, or once with the
   one-time step.

## Decisions and assumptions

* **The sidecar's name and format:** `policy-2026-27-nhi-coach-sample-labelled.csv.sha256`, the whole name
  plus `.sha256`. It holds one line, `<64 lower-case hex>  <file name>\n`, which is what `shasum -a 256`
  prints. So `shasum -a 256 -c` run in the folder checks it by hand too. Upper-case hex, one space, no
  name or a second line is refused as unreadable, never guessed at. The name in the line is not compared,
  because the digest decides.
* **The one-time step's `--expect` is required.** The digest it records comes from a sitting's record
  (here t55's report), never from the file at the moment of recording. Recording whatever the file now
  holds would bless an Excel save.
* **The dated copy is taken when the sitting writes, not when it starts**, from the bytes on disk at that
  moment. So it is the file the sitting actually replaces. A sitting with no change, or one stopped by
  Ctrl-C, writes nothing, copy included. Its name is `<stem>.before-sitting-YYYY-MM-DD-HHMM.csv` in local
  time, with `-2`, `-3` for later sittings in the same minute. It is opened for exclusive creation.
* **The old `.before-stance-relabel.csv` copy and its refusal are gone.** After the 2026-11-06 sitting that
  copy (t41's review) differs from the live file, so the old check would have refused every later sitting.
  The file stays on the operator's Mac untouched.
* **A dated copy has no sidecar**, so every command refuses it until the PM rules it back into place. t55
  ran `--check-sample` on backup copies to identify them; that now needs the PM's ruling first.
* **`chmod u+w` before a sitting:** measured on this Mac, `os.replace` replaces a read-only file anyway. A
  write in place, the way Excel saves, is denied. The new file comes up writable (`-rw-r--r--`). So
  `chmod a-w` after the sitting is what matters. The block keeps `u+w` before, as the PM asked, and the
  runbook says why the file must be made read-only again.
* **The thin-handler budget:** the guarded read took `evaluate` to 26 statements. The `--breakdown` with
  `record` refusal now sits in the existing refusal chain, in the same order, so it is back to 25.
  `BREAKDOWN_REPLAYS_ONLY`'s own test passes.
* **No label, tag or card text** is in a test, a commit, this report or the chat. The coach's file was not
  opened, read or changed in this session. Its digest is quoted from t55's report.

## Operator follow-ups

1. **Once: record the digest of the coach's labels of 2026-11-06.** Run it from this task's worktree
   until it merges, then from a checkout of `dev`. It takes a few seconds and asks no model. It refuses a
   set `DEBATE_` variable, a running Excel, a sidecar already there and a file whose SHA-256 is not
   `553374704519…`; the script refuses the last two again. Then it makes the file read-only and runs
   `--check-sample`.

   ```bash
   cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t58-the-coach-sample-labels-file-guarded
   ```

   ```bash
   SAMPLE=~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv
   ROWS=~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl
   EXPECT=553374704519fd29f13a43e279a08537b28c87fbfc58372be845bc0de2b0a922
   if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -x "Microsoft Excel" >/dev/null; then echo "STOP: Microsoft Excel is running; quit it first, so it cannot save over the labels file"; elif [ -e "${SAMPLE}.sha256" ]; then echo "STOP: the sidecar is already there; record nothing and paste this line"; elif [ "$(shasum -a 256 "$SAMPLE" | cut -d ' ' -f 1)" != "$EXPECT" ]; then echo "STOP: the labels file is not the one the sitting of 2026-11-06 wrote; record nothing and tell the PM"; elif ! uv run python scripts/record_coach_sample_digest.py --sample "$SAMPLE" --expect "$EXPECT"; then echo "STOP: nothing was recorded; paste the Refused line"; elif ! chmod a-w "$SAMPLE"; then echo "STOP: the digest is recorded, but the file could not be made read-only"; else uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample "$SAMPLE" --sample-rows "$ROWS" --check-sample; fi
   ```

   Success: a `Recorded 553374704519fd29…` line, then the JSON with `labelled` 47, `by_label_kind`
   advantage 16, aff 1, cp 7, da 5, k 9, none 2, t 7, and `by_stance` answers 9, reads 36. Paste back that
   line, or the `STOP:` or `Refused:` line, and the JSON: digests and counts only. Until this runs, every
   scoring, replay and re-record block refuses the file with `LABELS_DIGEST_MISSING`. The Goal goes to
   `Succeeded` once it has run.

## Follow-up work

1. **The file a sitting writes has no copy of its own until the next sitting.** The dated copies hold the
   files sittings replaced. On 2026-11-05 the file lost was the one a sitting had just written. The guard
   now makes such a loss loud, and `chmod a-w` stops Excel's save, but the bytes would still be gone. A
   sitting could also keep `<stem>.after-sitting-YYYY-MM-DD-HHMM.csv`, with no sidecar, so no command
   reads it. That is a few lines in `write_sitting`. For the PM (E32).
2. **The coach's guide** (`docs/guides/landscape-taxonomy.md`, "Your labelled sample of cards", outside
   this task's packages) says "To check the file after an edit". A proposed sentence for its place: "The
   file is changed only in a sitting the operator runs (`scripts/relabel_coach_sample.py`), never by
   opening it in Excel or Numbers: every command refuses a file that changed after its sitting
   (`v1-e32-t58`)." Its `--check-sample` block needs the sidecar first, like every other block.
3. **Restoring a dated copy** is now a PM-ruled step by hand: copy it over the file, remove the sidecar,
   then run the one-time step with the copy's recorded digest. If it is wanted often, it could be a script.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-07

**Notes:**

The 2026-11-05 loss can no longer be silent. Every command that reads the coach's labels checks them
first, and the smoke check shows the exact failure this closes: an LF re-save that used to be scored 4 of
4 is now refused.

1. **ac1 passes.** Red against a skeleton that checked nothing was 35 failed, each for its reason; green
   55, and 166 on the node's command. All 18 mutants on the digest check and the write order are caught,
   including `match` for `fullmatch`, `wb` for `xb`, and the sidecar written before the CSV.
2. **Decisions accepted.**
   - A `shasum -a 256`-format sidecar, so the file can also be checked by hand.
   - `--expect` required for the one-time step, so a recorded digest never blesses whatever the file
     holds now.
   - The dated copy taken at write time.
   - The bytes read once, then checked, then decoded.
   - The old `.before-stance-relabel.csv` refusal removed. It would have refused every later sitting.
   - Dated copies left without a sidecar, so restoring one is a PM-ruled step.
   - The finding that `os.replace` replaces a read-only file, which is why `chmod a-w` after a sitting is
     the step that matters.
3. **Deviations accepted.** The smoke check is agreement 5's. `score-sample` is guarded because the spec's
   forbidden list covers every scoring command.
4. **Follow-ups.**
   - 1, the file a sitting writes gets its own `.after-sitting-…` copy with no sidecar: filed (E32, p3).
   - 2, the coach's guide sentence: the PM writes it into `landscape-taxonomy.md` in the next batch.
   - 3, a restore script: not filed. It is rare, and a PM-ruled step by hand is right for now.
5. **Operator follow-up 1** runs before the merge, from this worktree. Its block guards the digest twice
   and makes the file read-only. The PM records it, and the Goal is then `Succeeded`.
6. **Merge:** `scripts/task pr --partial` once `ci` is green.

## Operator records (recorded by the PM, 2026-11-09)

Added by the PM. Nothing above is changed, and this section is not a review.

| Criterion | Was | Now | Record |
|---|---|---|---|
| Operator follow-up 1: the digest of the coach's labels of 2026-11-06 recorded | NOT RUN (operator) | PASS | 2026-11-07, from the task's worktree: the block wrote the sidecar, which records 553374704519fd29…a922, the digest of the 2026-11-06 sitting; it made the labels file read-only and ran --check-sample over the 47 labelled rows. Every scoring, replay and re-record block now accepts the file |

Every criterion passes, so the Goal is `Succeeded`.
