# Session report: v1-e01-t40-planted-break-nearest-ordering

| | |
|---|---|
| Task | `v1-e01-t40-planted-break-nearest-ordering` — The planted-break check runs the tests nearest a break by what reads it, not by path |
| Spec | [`plan_specs/v1/e01-repo-foundation/t40-planted-break-nearest-ordering.yaml`](../../plan_specs/v1/e01-repo-foundation/t40-planted-break-nearest-ordering.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t40-planted-break-nearest-ordering` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The planted-break check now runs a break's traced tests in this order:
1. those that mention a name from the changed line (PM batch 2026-10-27 x);
2. those whose route to the change reads every file on it by a path;
3. then by chain length, then by path.

A route the selector took because it could not tell (a word, the container read whole, source
walked as data, a data file's fallback) runs after the path routes. To make that visible,
`scripts/affected_tests.py --explain` now says `has a path to` for a path literal. The selector
already told a path literal from a word internally; selection is unchanged on all 14 breaks.

Every planted break is caught and the unreached one is not, each in 14 to 28 s. t39's break is
caught without `read_by`, so the field and its one use are removed (the stopgap from v1-e01-t39's
review). Ordering by durations was dropped by the PM's ruling, since nothing records durations
offline (Deviations). The dev pre-release's validate-dev slow tier, which runs every break after the
merge, is the final word on ac1.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `nearest-ordering` (Nearest-test ordering) | Done | `nearest_tests` and `reads_by_a_path` in the harness; `has a path to` in `--explain`; `read_by` removed. Durations dropped by the PM's ruling. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: every planted break is still caught, the unreached one still is not, each under two minutes, by the harness's own run | PASS | Breaks run one at a time (all 14 together take ~265 s, past two minutes), each by node id: `HYPOTHESIS_STORAGE_DIRECTORY=$(mktemp -d) perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -q -s -m slow -p no:randomly -p no:cacheprovider -n 0 '<node id>'`, at commit `7b5f743` (the ordering; later commits are formatting and this report). Table below. Final word: validate-dev's slow tier on the dev pre-release after the merge. |
| Node `nearest-ordering`: Selection tests pass (`uv run pytest tests/scripts -k affected`) | PASS | `.venv/bin/python -m pytest tests/scripts -k affected -q` → `107 passed in 79.49s` (load 17). |

The harness's own lines for ac1 (selected / traced / what ran / caught), and the outer test's time.
Load averages were 4.5 to 6.7 throughout.

| Break | Selected, traced | The nearest run | Caught | Time |
|---|---|---|---|---|
| debate_core: a DOI keeps a trailing dot | 334, 323 | 10: `1 failed in 1.90s` | a selected test failed | 17.7 s |
| debate_core: a canonical URL keeps its default port | 334, 323 | 10: `1 failed, 109 passed in 2.14s` | a selected test failed | 17.4 s |
| debate_core: the bundled public suffix list gains a line | 328, 322 | 10: `1 failed, 89 passed in 2.05s` | a selected test failed | 18.2 s |
| debate_core.testing: the file builder's fingerprint is reversed | 41, 12 | 10: `1 failed in 0.94s` | a selected test failed | 15.9 s |
| debate_cli: a retrieval failure exits 4 | 185, 163 | 10: `1 failed, 13 passed in 13.71s` | a selected test failed | 28.3 s |
| debate_api: the package fails to import | 58, 32 | 10: exit 4, `ImportError while loading conftest` | a conftest the selected tests load failed to import | 14.2 s |
| debate_workers: the package fails to import | 33, 4 | 4: `1 failed, 30 passed, 14 deselected in 5.78s` | a selected test failed | 18.4 s |
| debate_cli: a caselist slug implies the wrong event | 153, 130 | 10: `1 failed, 22 passed, 14 deselected in 5.07s` | a selected test failed | 20.9 s |
| debate_core.testing: the contract harness counts every page twice | 50, 20 | 10: `1 failed, 18 passed in 0.36s` | a selected test failed | 16.9 s |
| debate_core: a local version listing drops its last version | 199, 177 | 10: `1 failed, 22 passed in 6.60s` | a selected test failed | 22.0 s |
| tests/fixtures: a fixture page's title changes | 24, 13 | 10: `1 failed, 15 deselected in 1.48s` | a selected test failed | 21.1 s |
| debate_core: a lazily imported integration names the wrong place (t39's, no `read_by`) | 92, 70 | 10: `1 failed, 31 passed in 3.31s` | a selected test failed | 18.7 s |
| pyproject.toml: an import-linter contract is renamed | 11, 6 | 6: `1 failed, 97 passed in 2.23s` | a selected test failed | 15.3 s |
| **Unreached:** debate_core: a function nothing calls answers wrongly | 334, 323 | 10: `649 passed in 3.51s` | no (as it must be) | 19.5 s |

**Skips.** No inner run reported a skipped test. This session runs on the operator's Mac as a normal
user, so the permission tests that root-skip in the PM's container (batch x) run here.

**Red first.** `test_explain_tells_a_path_to_a_file_from_a_word_that_names_it`, run against the
start commit's `affected_tests.py` → `1 failed` (the by-path assertion: every route read `names`).
The new ordering tests, run against a skeleton that keeps the old order (mention, chain, path) and
reads every route as by a path → `7 failed, 17 passed`. The failures were the path-before-word and
container-read-whole orderings and the five could-not-tell routes. Still passing: the mention-first
and chain-then-path tests and every route that does read by a path, which is the old behaviour,
kept.

**Mutants** (agreement 8; each committed, because the harness clones HEAD; each run with a fresh
`HYPOTHESIS_STORAGE_DIRECTORY`, though no property is involved; restored with `git reset --soft`
and `git checkout HEAD --`, then compared byte for byte with a saved copy):

| Mutant | Caught by | Result |
|---|---|---|
| (1) Path readers no longer first: the path-read key dropped from `nearest_tests` | the two ordering unit tests (`2 failed, 22 passed`), and the slow harness on t39's break | Caught. t39's break ran ten tests that never read it: `266 passed in 50.27s`, caught: no, so the test failed (80 s). |
| (4) The unreached break made caught by selecting a test that names nothing changed | `test_a_break_no_selected_test_reaches_is_not_counted_as_caught` | Caught: `1 failed`. The mutant commit adds a stand-in test that fails and names nothing, and the harness runs it among the ten. A first form, ranking every selected test instead of the traced ones, was discarded as no attempt: no real test outside the traced set fails on that break (`501 passed`), so it could not make the break caught. Choice accepted by the PM (FYI 4). |
| (2) durations ignored, (3) an untimed test dropped | n/a | Withdrawn with durations, by the PM's ruling. |

**Whole-repo checks**, before the report:

| Check | Result |
|---|---|
| `uv run scripts/affected_tests.py --run` | AFFECTED_RESULT |
| `uv run ruff format --check` and `uv run ruff check` on the changed files | clean (format had rewrapped two lines in the tests; committed) |
| `uv run pyright` on the changed packages | No package changed. pyright's project scope is `packages/` (`include = ["packages"]`). Run on the changed files directly, it reports one unresolved `sys.path` import per test file: `affected_tests` (new) and `task_helper` (already on dev). CI does not type-check `tests/scripts`. |
| `uv run lint-imports` | `Contracts: 18 kept, 0 broken.` |
| `uv run scripts/validate_specs.py` | VALIDATE_RESULT |
| `uv run scripts/check_command_blocks.py` | COMMAND_BLOCKS_RESULT |

## Files changed

* `tests/scripts/test_affected_tests_planted_breaks.py`: `nearest_tests` and `reads_by_a_path`
  order a break's traced tests; `read_by` and its one use removed; the module docstring and t39's
  comment say the new order; 13 fast cases (6 test functions) of the ordering on hand-written routes.
* `scripts/affected_tests.py`: `HAS_A_PATH_TO`. A mentioner that denotes the file is reached as
  `has a path to`, in `Walk.search` and `Walk.runners_of`; labels only.
* `tests/scripts/test_affected_tests.py`: the label, on `VERIFY_FIXTURES`. Five path literals read
  `has a path to`; the unknown base, the walked folders and the command line read `names`.
* The spec's Goal phase and this report.

## Deviations from the spec

* **Durations dropped: the PM's ruling of 2026-10-30 (option B).** The spec says "then the fastest
  by the last recorded durations". Nothing records them where the harness can read them offline:
  * validate-dev's tiers write JUnit XML into a temporary work directory on the runner and upload
    nothing (`scripts/validate_dev.py` `run_tier`);
  * ci.yml uploads only coverage data, kept one day, and its `--durations=25` is in the job log;
  * the pytest cache holds `lastfailed` and `nodeids`, and no durations plugin is locked (`uv.lock`:
    pytest, pytest-cov, pytest-socket, pytest-xdist);
  * `tests/pytest_plugins/run_in_parts.py` declined a recorded-durations file as one "that would go
    stale".

  The session stopped and asked. The PM ruled: "No recorded durations exist offline, and the goal is
  met without them: all 13 planted breaks caught, the unreached one not, the slowest at 28 s. A
  committed durations file would drift and add an operator chore for no measured gain." The PM's
  next batch amends the spec's description to the ordering built here. It also notes that durations
  come back only if a future break runs slow. The spec is not edited in this task. Mutants (2) and
  (3) went with it.
* **`scripts/affected_tests.py` changed, its labels only.** `--explain` lumped a path literal that
  denotes a file (`denoters`) with a word that matches its name into `names`. The harness needs to
  tell them apart, and the selector already computes the difference (allowed by the PM's context:
  scripts/ "only if the order needs data the selector already computes"). A path literal now reads
  `has a path to`. Same mentioners, same reach order, and neither label is a fixture edge. The
  selected sets of all 14 breaks are identical before and after (`cmp` of each selection), and the
  selector's 76 existing tests pass unchanged. Accepted by the PM (FYI 1).

## Decisions and assumptions

* **Mention above path.** The suffix-list break's only catcher, `test_public_suffix.py`, mentions
  `ICANN`, `BEGIN` and `DOMAINS` from the changed line. But `--explain` gives only the first route
  the walk found, and its first route is a word: the f-string `"  public_suffix_list.dat\n"`, at
  one hop. Its path route, through `public_suffix.py`'s `"data/public_suffix_list.dat"`, is longer
  and is not shown. With path first, 316 path-route tests outrank it and it falls out of the ten.
  A mention is the more specific signal: the test names the very thing that changed. Path decides
  among the rest. Accepted by the PM (FYI 2).
* **What "could not tell" covers.** A step that `names` a file by a word, `reads the container
  whole, by reflection or as source`, `reads the Python source of` files it walks, or is a data
  file's `nothing names X` fallback. These are the steps where the selector selects more because it
  cannot tell. Everything else reads by a path: imports, runs, conftests, fixtures, path literals,
  command registration, `asks for` and `calls` between container parts. The harness imports the
  selector's own constants (`NAMES`, `READS_EVERY_PART`, `READS_SOURCE`), so a renamed label cannot
  drift into the path tier unnoticed. For t39's break, the four tests that reach the factory by
  reading the container whole (`test_doctor.py`, `test_container_factories.py`,
  `test_installation.py`, `test_caselist_run_deploy.py`) and the command runners behind them used
  to fill the ten. Now `test_version_retention.py` (passes) and `test_caselist_retire.py` (fails)
  run first. Accepted by the PM (FYI 3).
* **Chain length, then path**, stay as the last tie-breaks, as before.

## Operator follow-ups

None. The dev pre-release's validate-dev slow tier runs every planted break after the merge, and
is the final word on ac1.

## Follow-up work

* Durations come back only if a future break runs slow (the PM's ruling; the PM's next batch amends
  the spec's description).
* `--explain` shows one route per test, the first the walk found. A test reached first by a word
  and later by a path ranks in the could-not-tell tier (the suffix-list reader). The mention signal
  covers today's case. If a future break's reader both lacks a mention and is first reached by a
  word, the selector could record whether any route by paths alone reaches each test. That is new
  computation, which this task's scope (data the selector already computes) did not allow
  (v1-e01, the selector's owner).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
