# Session report: v1-e32-t19-dry-run-scan-refusal-wording

| | |
|---|---|
| Task | `v1-e32-t19-dry-run-scan-refusal-wording` — A dry run's scan refusal says nothing was written and gives the publish command |
| Spec | [`plan_specs/v1/e32-argument-landscape/t19-dry-run-scan-refusal-wording.yaml`](../../plan_specs/v1/e32-argument-landscape/t19-dry-run-scan-refusal-wording.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t19-dry-run-scan-refusal-wording` |
| Session status | COMPLETE |

## Summary

A `landscape report --publish --dry-run` that the scan holds back now says the dry run wrote no report,
and names the command to run. That command is the one typed, without `--dry-run` and with
`--accept-scan-hits <digest>`. It appears in the panel's hint and in `--json` as
`error.details.publish_command`, a key only a dry run's refusal has. A publish without `--dry-run` reads
as before, word for word, in the panel and the JSON, and a test pins its text. Both scan codes are
covered, since they share the hint: `SCAN_HITS_NOT_ACCEPTED`, and `SCAN_DIGEST_STALE` (a stale digest
typed on a dry run is replaced by this run's). The change is in `debate_cli` only. What a dry run or a
publish writes is unchanged, and so are t33's exit codes, `cause_code` and `retry_after_seconds`; the
service is untouched. **Look first at:** the wording "wrote no report" rather than "nothing was
written" (Deviations), and the hint text in
`test_a_dry_runs_scan_refusal_says_it_wrote_no_report_and_names_the_publish_command`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `dry-run-wording` (Dry-run scan refusal wording) | Done | Tests at `55ded1d`, shown red; implementation at `e8e2490` |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a dry run refused by the scan says nothing was written and names the command without `--dry-run` and with `--accept-scan-hits` and the digest, in the panel and the JSON; a publish refused by the scan reads as before; tests shown failing first | PASS | **Red** at `55ded1d` (the new tests over the unchanged command): `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_cli/tests/test_landscape_command.py -k "<the eight new tests>" -n 0 -p no:randomly --tb=line -q` → `6 failed, 2 passed in 23.49s`. Five dry-run tests failed with `KeyError: 'publish_command'` (the JSON has no command). The panel test failed its assertion: no "This dry run wrote no report … publish with `…`" in the panel. The two that passed are the parametrized pins of a publish's refusal, which hold the old text. **Green** at `e8e2490`: the same command → `8 passed`. JSON: `test_a_dry_runs_scan_refusal_says_it_wrote_no_report_and_names_the_publish_command` and `test_a_dry_run_given_a_stale_digest_names_the_command_with_the_digest_of_these_hits`. Panel: `test_a_dry_runs_scan_refusal_panel_says_it_wrote_no_report_and_names_the_publish_command`. Only what was typed: `test_a_dry_runs_publish_command_echoes_every_option_typed_and_nothing_else`. The named command runs: `test_the_command_a_dry_run_names_publishes` and `test_the_command_a_dry_run_over_a_restored_copy_names_publishes_from_the_copy_as_typed`. As before: `test_a_publishs_scan_refusal_reads_as_before_word_for_word[no digest, a stale digest]`. Mutants: below |
| Node criterion "Landscape command tests pass": `uv run pytest packages/debate_cli/tests/test_landscape_command.py` | PASS | Run bounded as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_cli/tests/test_landscape_command.py -q` → `92 passed in 45.42s` (84 existing, 8 new) |

### Mutants (agreement 8)

Each mutant was applied to the committed `landscape.py`. The eight new tests ran over it with `-n 4` and
a fresh, empty `HYPOTHESIS_STORAGE_DIRECTORY`; these tests use no Hypothesis, so it is set only to
follow the rule. The file was restored with `git checkout HEAD --` after each run. Every catch below is
an assertion failure, or a test's own `KeyError` reading the missing `publish_command`, over code that
ran to its exit. None is a crash of the mutated code.

| Mutant | Caught by |
|---|---|
| 1. The dry run still says "the report is written locally at …" | 2: the JSON and panel hint pins |
| 2. `--dry-run` kept in the named command | 6: every exact-command pin, and both named commands run as dry runs, so they publish nothing |
| 3. The digest missing from the command | 6: the exact-command pins; the named command run publishes nothing (`SCAN_HITS_NOT_ACCEPTED`) |
| 4. A publish's refusal text changed ("run again with" → "publish with") | 2: both cases of the word-for-word pin |
| 5a. The JSON left saying the old thing: no `publish_command` in `details` | 5: every JSON test |
| 5b. The JSON and panel hint left saying the old thing, with `publish_command` added | 2: the JSON and panel hint pins |
| 6a. An argument not typed added: defaulted value options echoed (`--model-mode none`) | 4: the exact-command pins |
| 6b. An argument not typed added: the snapshot the run resolved (`--snapshot 2026-09-15`) | 5: the exact-command pins |
| 7. A typed root option dropped (`--json`, `--verbose`) | 5: the exact-command pins; the named command runs without `--json`, so its stdout is no JSON |
| 8. A typed stale digest kept beside this run's | 1: the stale-digest test |

**Discarded, not counted:** a first 6a that echoed every option, flags included. It crashed on
`--confirm-prod`'s `False`, which has no `--no-` spelling (`IndexError` in `secondary_opts[0]`), so the
refusal never printed. It was redone as 6a above.

### Before the report (agreement 10)

| Check | Result |
|---|---|
| `uv run scripts/affected_tests.py` (selection only) | `82 of 631 test files (13.0%) chosen in 64.6 s from 4 changed files` |
| The 82 files, `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n auto -m "not slow and not live" -q <the 82>` | **Stopped at the 115-second limit at 35%, no failure**, at a load average of 32 (another session was running on this Mac). Over two minutes, so it is left to the pull request's `ci`, which runs the same set. Not handed off (agreement 10) |
| The always-run list (`tests/architecture/`, `tests/specs/`, `test_app.py`, `test_help_rendering.py`, `test_container_factories.py`), same bound, `-n 4` | `374 passed in 54.01s` |
| The affected set's 14 `debate_cli` files, same bound, `-n 4` | Stopped at the limit at 33%, no failure (same load); left to `ci` |
| `uv run --frozen ruff format --check .` | `1745 files already formatted` |
| `uv run --frozen ruff check .` | `All checks passed!` |
| `uv run --frozen pyright packages/debate_cli` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `uv run --frozen python scripts/check_thin_handlers.py` | `OK: 70 CLI command and API route handlers within 25 statements` |
| `uv run scripts/validate_specs.py` | `OK: 554 files, 41 epics, 491 tasks, 22 releases` |

## Files changed

* `packages/debate_cli/src/debate_cli/commands/landscape.py`: `_publish_failure` branches on
  `result.dry_run` for the hint and `details`. The new `_publish_command` and `_typed_options` rebuild the
  command as typed. The module docstring's "The scan before sharing" section says what a dry run's
  refusal names, and where.
* `packages/debate_cli/tests/test_landscape_command.py`: a `v1-e32-t19` section of eight tests (one
  parametrized over two cases), and `import shlex`.
* `plan_specs/v1/e32-argument-landscape/t19-dry-run-scan-refusal-wording.yaml`: phase `Succeeded`.
* This report.

## Deviations from the spec

* **"Says nothing was written" is "This dry run wrote no report."** Since `v1-e32-t30` a dry run writes
  the plan-text and analytic-text caches (module docstring, `--dry-run`), so "nothing was written"
  would be untrue. The hint says what the coach needs, that no report exists to read locally. The
  message, unchanged, still ends "nothing was published". If the PM wants the spec's words, the
  sentence is in one place in `_publish_failure` and is pinned in two tests.

## Decisions and assumptions

* **The JSON field is `error.details.publish_command`**, a string holding the whole command,
  shell-quoted with `shlex.join`. It is present only on a dry run's scan refusal and absent otherwise,
  as t33 did for `retry_after_seconds`, so a publish's JSON is unchanged. `error.hint` carries the same
  sentence as the panel, and `error.message` is unchanged in both cases.
* **"As typed" means the options Click read from the command line**, judged by its parameter source,
  at every level from the program down: root options (`--json`, `--verbose`) as well as `report`'s.
  Defaults, environment variables and values the run resolved (the newest snapshot, the data
  directory) are never added. So `DEBATE_ENV=dev`, the runbook's `env …` and `caffeinate` wrappers
  are not echoed: they were not typed to `debate-research`.
* **Echoed in declaration order, not typing order, in the long spelling.** Click keeps no record of the
  typed order, and a reordered command is the same command; `-v` echoes as `--verbose`. A path echoes
  as the `Path` Typer parsed: the shell has already expanded `~`, and a trailing `/` is dropped. A
  `--restored-copy` or `--out` directory is echoed as the PM ruled for files publish's hint
  (v1-e33-t16). `--accept-scan-hits <digest>` always comes last, replacing any digest typed.
* **The program name is the literal `debate-research`**, as the other hints write it. `app.APP_NAME`
  cannot be imported from a command module, because `app` imports the command registry.
* **No `click` import.** Typer 0.27 vendors Click privately (`typer._click`), so the top-level `click`
  package's `ParameterSource` never matches Typer's. The first green attempt imported it and echoed
  nothing. The contexts are walked as `Any`, as `context.command_name` already does, and a source is
  compared by its name, `COMMANDLINE`. Flags are told apart with `typer.core.TyperOption.is_flag`
  (`app.py` already imports from `typer.core`).
* **Never adding what was not typed has two consequences the PM may want to know.** A prod dry run
  typed without `--confirm-prod` names a command without it, which is then refused with
  `CONFIRMATION_REQUIRED`, whose hint names the flag. A `--model-mode live` dry run names a live
  publish, which the policy gate refuses as it always has.

## Runbook lines (for the PM's batch)

No runbook or guide quotes the old dry-run text or tells the operator to add `--accept-scan-hits` to a
dry run. I checked `git grep -n -E "written locally|accept-scan-hits|SCAN_HITS_NOT_ACCEPTED|SCAN_DIGEST_STALE" -- docs`
outside session reports, and read the dry-run and publish steps:

* `docs/runbooks/landscape-report-from-the-cloud-run.md:174-177` ("publish with the digest the dry run
  printed, in step 4's second block") and `:213-223`: the publish block is separate from the dry run and
  has no `--dry-run`, with `DIGEST` set from the dry run. This is consistent with the new hint. An
  optional improvement for the PM: step 3's reader could print `error.details.publish_command` beside
  the hits, though step 4's block adds its own guards (Wednesday, `DEBATE_` overrides, `aws sso login`),
  so it should stay the command to paste.
* `docs/data/landscape/first-run-policy.md:165-166` ("the bundle written locally"): a recorded
  non-dry-run publish, where it is true. No change.

## Operator follow-ups

None.

## Follow-up work

* **A smoke check for the dry run's refusal.** Agreement 5 asks a user-facing change to update its smoke
  checks, but the spec has no smoke node and `tests/smoke` is outside its packages.
  `tests/smoke/test_landscape_smoke.py` has no scan-refusal check today. One would need a planted
  tournament in its world (team codes are withheld since `v1-e32-t28`). It belongs in E32.
* **A long command wraps inside the panel's borders** on a narrow terminal, as every hint does, so a
  coach copying it from the panel picks up `│` characters. `--json`'s `publish_command`, or a wider
  terminal, avoids that. Printing a command to paste outside the panel would be a change to the shared
  renderer in `output.py` (E01 or E41 upkeep), if the PM wants it.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-01

**Notes:**

The panel now tells the coach the truth, and it gives a command that actually publishes.
1. **ac1 passes.**
   * Red: 6 failed (five `KeyError`s on the missing field, which are the tests' own reads, and one
     panel assertion). The two that passed are the word-for-word pins of a publish's refusal, which
     must hold the old text.
   * Green: 8, and the node criterion passes (92).
   * All the PM's mutants are caught, with 5 and 6 each in two forms, plus 7 and 8. The crashing
     first 6a was discarded, not counted, which is right.
   * The two "the named command publishes" tests run the hint's command, which proves the hint
     rather than just pinning its text.
2. **Deviation accepted: "This dry run wrote no report."** Since v1-e32-t30 a dry run writes caches,
   so "nothing was written" would be untrue. The spec's intent, that no report exists to read, is
   what the coach needs.
3. **Decisions accepted:**
   * `error.details.publish_command`, present only on a dry run's scan refusal, as t33 did for
     `retry_after_seconds`;
   * "as typed" judged by Click's parameter source at every level, never a default, an environment
     variable or a resolved value;
   * declaration order and long spellings;
   * the literal `debate-research`;
   * comparing the source by name, because Typer vendors Click;
   * both consequences of never adding what wasn't typed (`--confirm-prod`, a live mode), each
     refused by its own gate with its own hint.
4. **Runbook lines:** none needed changing, as checked. Step 3's reader printing `publish_command`
   is not filed, since step 4's block carries guards a pasted command wouldn't.
5. **Follow-ups, the PM's rulings:**
   * **A smoke check for the dry run's scan refusal:** noted for the next E32 task that touches
     `tests/smoke`, not filed alone.
   * **The panel wrapping a long command:** not filed. `--json`'s field is the copyable form.
6. **Closing checks:** the affected set (82 files) stopped at 35% at its limit with no failure, at a
   load of 32, and is left to the PR's `ci` under agreement 10. The always-run list (374), ruff,
   pyright, lint-imports, thin handlers and the specs are clean.
7. **Merge:** a plain `scripts/task pr` once `ci` is green. No operator step follows.
