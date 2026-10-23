# Session report: v1-e01-t30-test-selection-reach

| | |
|---|---|
| Task | `v1-e01-t30-test-selection-reach` — Tests stop reaching code they do not use: fakes by port, no port re-exports, and a graph option |
| Spec | [`plan_specs/v1/e01-repo-foundation/t30-test-selection-reach.yaml`](../../plan_specs/v1/e01-repo-foundation/t30-test-selection-reach.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t30-test-selection-reach` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

All five cuts are made, with no compatibility module:

- **Fakes:** `debate_core/testing/fakes.py` is now a package, `debate_core.testing.fakes`, with one
  module per port. `fakes.py` is deleted and all 97 importing files were rewritten.
- **Port re-exports:** `application/ports/__init__.py` is a docstring only, and `ports/providers.py`
  re-exports nothing. All 32 callers now import from the defining module.
- **Settings:** `settings.py` no longer imports `near_duplicates`.
- **Conftest:** the moto bucket fixtures left `packages/debate_core/tests/conftest.py`. The four
  directories that use them now import them.
- **The guard:** a new architecture test, `test_fakes_reach_only_their_port.py`, fails on each rule,
  shown red against re-added imports and against the old files.
- **`--graph`:** `scripts/affected_tests.py --diff REV --graph REV2` selects REV's changes over
  REV2's graph.

Behaviour is unchanged. Before the first change the root collected **12171/12205**, and it collected
the same after the last refactoring commit. After the sync with `dev` the base collects
**12214/12248**. The branch collects the same once its 51 new test cases are left out.

**The Goal is Succeeded.** Every criterion passed in the session.

**Read ac3 first.**
- **Headline:** over t28's 20 commits, the median selected share is **57.7%**, against t29's
  **65.8%**. The largest is still **100%**: four commits change a `pyproject.toml`, and that is the
  whole selection by rule.
- **Where it moved:** three commits that touch caselist suppression, removal or the parsed store
  drop by 20 to 25 points. Two more drop by 12.5 and one by 6.4.
- **What did not move:** without the four whole-selection commits the median stays put (55.4% at
  the base, 55.5% after). The mean falls from 58.2% to 52.0%.
- **What carries the rest:** the commits near the median are carried by the CLI composition root
  and the caselist test conftest, and by code they really use (Follow-up work).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `reach` (Test-selection reach) | Done | Nine commits after the start commit, plus this report's, listed under Files changed. The node criterion passes. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: `fakes.py` is split so that importing one fake imports only its port's modules; the port re-exports are gone and every caller imports from the defining module; `settings.py` no longer imports `near_duplicates`; pyright and lint-imports pass | PASS | **The split:** each module in `debate_core/testing/fakes/` reaches only its own port module, plus the ports that module imports itself. `all_ports` is the one named exception (Decision 2). `clock_and_ids`, `model_router` and `suppression` import no port. The guard checks this for every module. **Callers:** `git grep` finds no `from debate_core.testing.fakes import` and no `from debate_core.application.ports import <name>`. Both codemods in `--check` mode → `0 files would change`. **Re-exports:** `ports/__init__.py` is a docstring only, and `providers.__all__` lists only what `providers.py` defines. **settings:** `grep near_duplicates settings.py` finds only one line of a docstring. **pyright:** `.venv/bin/pyright` → `0 errors, 0 warnings, 0 informations`; `uv run pyright packages/debate_core packages/debate_cli packages/debate_api` → the same. **lint-imports:** `Contracts: 15 kept, 0 broken.` **The guard, red** (each run restored with `git checkout`, then `git status --porcelain` printed nothing): see "The guard, shown failing" below. |
| ac2: `scripts/affected_tests.py --diff REV --graph REV2` selects REV's changes over REV2's import graph, by test | PASS | Three cases in `tests/scripts/test_affected_tests.py`, expected selections written by hand from `BASE`. **(1)** A commit's changes are selected over a later commit's imports: a test that imports the module only in the graph tree is selected, one that stopped importing it is not, and the share is out of the graph's 31 test files. The same commit without `--graph` gives its own tree's selection. **(2)** Changed files the graph's tree does not have are listed. **(3)** `--graph` with `--run` is refused. **Red:** against the script before the option, all three fail (`unrecognized arguments: --graph`). A mutant that accepts `--graph` but ignores it fails (1), with `missing: [...test_graph_only.py], extra: [...test_domain.py]`, and fails (2). **Green:** `3 passed`. |
| ac3: over t28's 20 commits, the median and largest selected share with this branch's graph, against t29's 65.8% and 100%; the collected test count is unchanged | PASS | **Median 57.7%, largest 100%** (t29: 65.8% and 100%). The table and how to read it are below. **Collected count:** see the last row. |
| Node `reach`: `uv run pytest tests/scripts -k affected` | PASS | `45 passed in 9.38s` |
| PM: collected count identical before and after, with and without the marker filter | PASS | `.venv/bin/python -m pytest --collect-only -q -m "not slow and not live" \| tail -1`, and the same with no `-m`. The two always agree, because `addopts` already carries the marker filter. **Before the first change** (at `2932a51`): `12171/12205 tests collected (34 deselected)`, both. **After the last refactoring commit**, before the guard was added: `12171/12205`, both. **After the sync with `dev`:** the base `ffbfb2c` collects `12214/12248`, both. The branch tip `4bec5a3` collects `12265/12299`, both, which is the base plus the guard's 48 cases and the three `--graph` cases. With `--ignore=tests/architecture/test_fakes_reach_only_their_port.py` and a `--deselect` for each `--graph` case: `12214/12251 (37 deselected)`, both, so 12214 selected, identical. The total is 3 higher only because deselected tests are still collected. All on this Mac, in this worktree. |

### The guard, shown failing

`tests/architecture/test_fakes_reach_only_their_port.py`, at `0fb79f9`, against each re-added
import. Each was made in the worktree and restored with `git checkout`; `git status --porcelain`
printed nothing afterwards, and the green run is `48 passed`.

| Planted | Result | Failing case, and its message |
|---|---|---|
| `fakes/card_edit_log.py` imports `ports.suppression` again | 8 failed, 40 passed | `test_a_fakes_module_reaches_only_its_own_port[card_edit_log]`: `reaches the port modules ['suppression (line 35)'], but may reach only ['card_edit_log']`. The other seven are the self-check cases, which add their own line to the same, already broken, source. |
| `fakes/clock_and_ids.py` imports the persistence fakes | 3 failed | `[clock_and_ids]` `persistence (through persistence)`, and `[model_router]` and `[providers]` `persistence (through clock_and_ids)`: both import the clock, so they now reach the port through it. |
| `ports/__init__.py` re-exports `Page` again | 1 failed | `test_the_package_module_holds_only_a_docstring[...ports/__init__.py]`: `holds ['line 47: from debate_core.application.ports.persistence import Page']` |
| `providers.__all__` lists `FetchResult` again | 1 failed | `test_a_port_module_lists_only_what_it_defines[providers]`: `lists ['FetchResult'] in __all__ but imports them` |
| The base's `ports/__init__.py` and `providers.py` | 2 failed | Both rules above, listing every re-export and `['CandidateResult', 'FetchResult', 'ProviderQuery', 'ProviderResponse']` |
| The base's `fakes.py`, dropped into the package as a module | 1 failed | `[old_single_module]`: `reaches the port modules ['parsed_store (line 67)', "the ports package's own names (line 41)"], but may reach only none`. Before `0fb79f9` it reported only `parsed_store`; that commit made a name imported from the package itself count (Decision 3). |

### ac3: the 20 commits

**Method.** Each row is `uv run scripts/affected_tests.py --diff <commit> --graph <graph>`, which is
the ac2 option itself, run once per commit and graph. The runs went in four parallel processes, each
stopped at 150 s; each took about 70 s. Two graphs:

- **Before** is `ffbfb2c`, today's `dev` and this branch's base after the sync. t29 is merged in it.
- **After** is `31d9982`, this branch. The only later commit, `4bec5a3`, re-wraps three comments.
  Three rows re-run over it gave identical counts: 230, 260 and 211 of 390.

Before and after hold the same changes and nearly the same test files, so their difference is this
task alone. The count is 389 against 390 because of the new guard file, which is always run; that
is the +0.1 or +0.2 in the unchanged rows. t29's after column is copied from its report, for
reference; it was measured over a tree of 346 test files.

| Commit | t29's after, at `986299f` | Before, at `ffbfb2c` | After, at `31d9982` | Change (points) | Time to choose, after |
|---|---|---|---|---|---|
| `9101764` | 72.0% | 274 of 389 (70.4%) | 226 of 390 (57.9%) | -12.5 | 17.5 s |
| `9f11fe1` | 59.2% | 221 of 389 (56.8%) | 222 of 390 (56.9%) | +0.1 | 14.9 s |
| `29f074d` | whole (`pyproject.toml`) | whole (`pyproject.toml`) | whole (`pyproject.toml`) | | |
| `edf8eba` | whole (`pyproject.toml`) | whole (`packages/debate_core/pyproject.toml`) | whole (`packages/debate_core/pyproject.toml`) | | |
| `30c5157` | 83.5% | 325 of 389 (83.5%) | 230 of 390 (59.0%) | -24.5 | 5.1 s |
| `29c8293` | 84.1% | 328 of 389 (84.3%) | 250 of 390 (64.1%) | -20.2 | 5.1 s |
| `387c961` | 52.0% | 202 of 389 (51.9%) | 203 of 390 (52.1%) | +0.2 | 5.1 s |
| `9877884` | 91.6% | 355 of 389 (91.3%) | 331 of 390 (84.9%) | -6.4 | 5.2 s |
| `72c1d05` | 54.6% | 203 of 389 (52.2%) | 204 of 390 (52.3%) | +0.1 | 5.1 s |
| `3f2530b` | 90.8% | 353 of 389 (90.7%) | 260 of 390 (66.7%) | -24.0 | 5.3 s |
| `801883a` | 19.1% | 71 of 389 (18.3%) | 72 of 390 (18.5%) | +0.2 | 17.5 s |
| `993063c` | 71.7% | 273 of 389 (70.2%) | 225 of 390 (57.7%) | -12.5 | 14.9 s |
| `8bbe1cd` | 55.2% | 205 of 389 (52.7%) | 206 of 390 (52.8%) | +0.1 | 5.3 s |
| `ea09eb1` | 55.2% | 205 of 389 (52.7%) | 206 of 390 (52.8%) | +0.1 | 5.1 s |
| `0a43e88` | 59.8% | 224 of 389 (57.6%) | 225 of 390 (57.7%) | +0.1 | 5.1 s |
| `d730de0` | whole (`pyproject.toml`) | whole (`packages/debate_core/pyproject.toml`) | whole (`packages/debate_core/pyproject.toml`) | | |
| `55d0b4b` | whole (`pyproject.toml`) | whole (`packages/debate_core/pyproject.toml`) | whole (`packages/debate_core/pyproject.toml`) | | |
| `1e63363` | 36.7% | 141 of 389 (36.2%) | 142 of 390 (36.4%) | +0.2 | 5.1 s |
| `b0820cf` | 8.7% | 33 of 389 (8.5%) | 34 of 390 (8.7%) | +0.2 | 5.0 s |
| `4c5a766` | 56.1% | 210 of 389 (54.0%) | 211 of 390 (54.1%) | +0.1 | 5.2 s |

The time to choose is wall time with four measurements running at once on a loaded machine (load
average 5 to 7). The 15 to 17 s rows were the first in their process; run alone, a choice takes
about 5 s.

| Summary | t29's after | Before, at `ffbfb2c` | After, at `31d9982` |
|---|---|---|---|
| Median, all 20 | 65.8% | 63.9% | **57.7%** |
| Largest, all 20 | 100% | 100% | **100%** |
| Median without the 4 whole-selection commits | 57.7% | 55.4% | 55.5% |
| Mean without them | 59.4% | 58.2% | 52.0% |
| Test-file selections removed, summed over the 16 | | | 376 |

**The four whole-selection commits**, reported separately as t29 did. They are the whole selection
before and after, by rule, and nothing here changed that rule:

- `29f074d` changes the root `pyproject.toml`. It only adds `debate_core.integrations.docx_file_writer`
  to an import-linter contract, twice.
- `edf8eba` adds the `idna` dependency to `packages/debate_core/pyproject.toml`, with lint
  configuration in the root `pyproject.toml` and `uv.lock`.
- `d730de0` adds `jinja2` to `packages/debate_core/pyproject.toml`, with `uv.lock`.
- `55d0b4b` rewords a comment and widens the `aws` extra in `packages/debate_core/pyproject.toml`,
  with the root `pyproject.toml`.

t29's table recorded all four as plain `pyproject.toml`. The tool names the first shared-ground file
it meets, and for three of them that is the package's.

**How to read it:**
- **The median of 20 is the mean of the 10th and 11th values.** Before, those were 57.6% and
  70.2%; after, both are 57.7%. Two rows near 70% (`9101764`, `993063c`) fell below the boundary,
  so the headline drop is real but rests on those two.
- **The median of the 16 does not move.** The rows around it, 52% to 57%, are commits to the CLI
  and to caselist services. Their selections are carried by what this task did not touch (Follow-up
  work).
- **The mean of the 16 does move, by 6.2 points**, and that is where the gain is. The large drops
  (`30c5157`, `29c8293` and `3f2530b` by 20 to 25 points, `9101764` and `993063c` by 12.5) are
  commits to caselist suppression, removal and the parsed store. Before, every test that needed `FixedClock` or `InMemoryCardRepository`
  reached those modules through `fakes.py`.
- **Over t29's own column** the same rows fell from 83.5%, 84.1% and 90.8% to 59.0%, 64.1% and
  66.7%.

### What this session ran before the report (working agreement 10)

- `uv run scripts/affected_tests.py --run` → `The whole selection is affected: conftest.py is shared
  test ground. CI runs it on the pull request; a session does not (working agreement 10).` Nothing
  was run, as the PM's note says; the whole selection is the pull request's `ci` check.
- Instead, within two minutes each, the alarm on `.venv/bin/python -m pytest` with `-n auto`:
  - After the final conftest commit, the four directories that use the moved fixtures:
    `packages/debate_core/tests/{application,contracts,integrations/s3,integrations/bedrock}` →
    `3566 passed in 85.25s`.
  - The always-run list (`tests/architecture`, `tests/specs`, the CLI's `test_app.py` and
    `test_help_rendering.py`), plus `packages/debate_core/tests/{testing,domain}`, `tests/scripts`,
    and the 24 changed test files outside those four directories → `3202 passed, 2 warnings in
    55.23s`. Both warnings are the one explained in Decision 8.
  - `packages/debate_cli/tests`, because `container.py` changed → `875 passed in 36.77s`.
  - Earlier, before the sync: every changed test file with `testing/` and `contracts/` →
    `3056 passed`, and `application/caselist` with the 22 tests that drive the rewritten fixture
    worlds and scripts → `2225 passed`.
- Node criterion: `uv run pytest tests/scripts -k affected` → `45 passed`.
- `uv run ruff format --check .` → `1097 files already formatted`.
- `uv run ruff check .` → `All checks passed!`
- `.venv/bin/pyright` → `0 errors`. The same for `uv run pyright packages/debate_core
  packages/debate_cli packages/debate_api`.
- `uv run lint-imports` → `Contracts: 15 kept, 0 broken.`
- `uv run scripts/validate_specs.py` → `OK: 404 files, 39 epics, 344 tasks, 21 releases`.
- `uv run scripts/check_links.py` → `OK: 1955 relative links and anchors in 299 Markdown files`.
- `uv run scripts/check_command_blocks.py --base origin/dev` → OK.
- **No mutation run beyond the guard's.** This is an imports-only change; its one piece of logic is
  the guard, which was shown red six ways (above). The `--graph` option was shown red against the
  old script and against one mutant (ac2).

## Files changed

Nine commits after the start commit, on top of `dev` at `ffbfb2c`:

- **`2d9a5f0`, the port re-exports.**
  - A codemod (kept in the session scratchpad, not committed) rewrote 32 files to import each port
    from its defining module. It read the name-to-module table from `ports/__init__.py` and
    `providers.py` themselves, so no name was retyped.
  - `ports/__init__.py` keeps its table of ports as a docstring. `providers.py` drops the four
    borrowed names from `__all__` and the unused `CandidateResult` import.
  - Two tests read the package itself; both were rewritten, not deleted (Decision 6).
- **`b2a46d1`, the fakes split.**
  - `debate_core/testing/fakes/` holds ten modules plus a docstring-only `__init__`. A script sliced
    the bodies from the old `fakes.py` by line range, and checked that every body line went to
    exactly one module.
  - The same codemod rewrote the 97 importing files, and `fakes.py` was deleted.
  - Docstrings that named `debate_core.testing.fakes.X` now name the module, and so do
    `packages/debate_core/README.md` and two docs (Deviation 1).
- **`b93aaa4`, settings.** `CardFingerprintSettings.thresholds()` moved to
  `caselist_card_stats.fingerprint_thresholds(settings)`. The container and the one test that calls
  it were updated.
- **`8ba4c6e` and `31d9982`, the conftest.**
  - `packages/debate_core/tests/conftest.py` moved, its body unchanged, to
    `tests/fixtures/moto_evidence_bucket.py`.
  - New conftests in `application/`, `integrations/s3/` and `integrations/bedrock/`, and the
    existing `contracts/conftest.py`, import the fixtures each directory uses.
  - Four docstrings and two READMEs that named the old file were updated.
  - `31d9982` replaced an `__all__` with the `name as name` import form (Decision 5).
- **`ea49d52` and `0fb79f9`, the guard.** `tests/architecture/test_fakes_reach_only_their_port.py`,
  new.
- **`ad5391b`, `--graph`.** `scripts/affected_tests.py` (the option, its docstring and usage) and
  three cases in `tests/scripts/test_affected_tests.py`.
- **`4bec5a3`** re-wraps three comment lines the longer module names pushed past 110 characters.
- **The spec:** the Goal's phase, Succeeded at the end.

## Deviations from the spec

1. **Two documents outside `constraints.packages` changed.** `docs/` is not in the task's packages.
   - **`docs/architecture/ports-and-adapters.md`** linked to `testing/fakes.py`. Deleting the file
     would have failed `check_links.py` in CI, so the link now points at `fakes/all_ports.py`. One
     sentence was added about the `build_fake_*` functions.
   - **`docs/evidence/snapshot-text-format.md:299`** named `debate_core.testing.InMemoryCardEditLog`.
     Your ruling 3 on t29 put this one-word fix in this task, but the spec does not list it. It now
     names `debate_core.testing.fakes.card_edit_log.InMemoryCardEditLog`.

   Neither changes any behaviour.
2. **"Before" in ac3 is the synced base, not the pre-sync one.** `dev` gained v1-e31-t30 (#401)
   during the session, and I synced with `scripts/task sync` before measuring. "Before" is therefore
   `ffbfb2c`, the base the branch now sits on, so that the before and after columns differ only by
   this task. t29's own after column is in the table too. The collected-count proof is given at
   both bases.

## Decisions and assumptions

1. **The fakes became a package of the same name, with modules named after the ports.**
   - `debate_core.testing.fakes.persistence` fakes `application.ports.persistence`, and so on for
     `card_edit_log`, `caselist`, `suppression`, `providers`, `model_router`, `debate_files` and
     `parsed_store`.
   - Matching the names is what lets the guard work out each module's port without a table to
     maintain.
   - Two modules match no port. `clock_and_ids` holds `FixedClock`, `SequentialIdGenerator` and
     `FAKE_EPOCH`, and imports no port. `all_ports` holds `FakePorts` and `build_fake_ports`.
   - An old `from debate_core.testing.fakes import FixedClock` now fails with a plain `ImportError`,
     which is what an in-flight branch should see.
2. **`all_ports` is the guard's one named exception.**
   - `FakePorts` annotates its ten fields with the Protocols, which is where pyright checks that the
     fakes conform. So it has to import the persistence, providers and model-router ports.
   - Only `test_fakes.py` and `test_port_conformance.py` import it.
   - I kept it inside the package and named it in the test (`ASSEMBLY_MODULES`) rather than moving
     it outside `fakes/`, where the rule would simply not look at it.
3. **What "its own port" allows.**
   - A fakes module may reach its port module and the port modules that one imports itself.
     `ports/caselist.py` imports `ports/persistence.py` for `Page`, so the caselist fake pages with
     the persistence fakes' `paginate` and reaches nothing its port did not already reach.
   - Imports of another fakes module count as reaching what that module reaches, so a port cannot
     be laundered through a neighbour.
   - `from debate_core.application.ports import <a name>` counts as reaching every port. Today such
     an import would fail anyway, because the package is empty, but the rule should not depend on
     the other rule.
   - Shared helpers (`clock_and_ids`) may import no port.
4. **Two code changes inside the moved fakes, both forced by the split.**
   - `_paginate` became `paginate`, because the caselist fake now calls it from another module.
   - `ScriptedModelRouter(clock=...)` takes a `FixedClock` rather than any `Clock`, so the model
     router fake imports no port. `ports/model_router.py` does not import `ports/providers.py`, where
     `Clock` lives. Every caller passes a `FixedClock` or nothing; pyright confirms it.
   - `FakeArticleFetcher` keeps `Clock`, since `Clock` is in its own port.
5. **The moto fixtures are defined once and imported by four conftests.**
   - The PM asked for the conftests of the directories that use them. Those are `application/` (66
     of its test files use the bucket), `contracts/`, `integrations/s3/`, and `integrations/bedrock/` (the
     credentials only).
   - Writing them out four times would undo the old docstring's point: one definition, one chance to
     reach something real. So they live in `tests/fixtures/moto_evidence_bucket.py`, the place the
     root conftest already puts on `sys.path` for shared helpers, and each conftest imports what it
     uses.
   - **The first version used `__all__`, which was wrong.** `affected_tests.py` reads a quoted string
     as a path part, so the string `"evidence_bucket"` "named" `infrastructure/modules/evidence_bucket/`.
     That added 38 files to `4c5a766`'s selection, which the measurement showed (54.0% to 63.6%).
   - The `name as name` form, which is the explicit re-export, marks the imports as used for ruff
     and pyright with no string literal. `4c5a766` is back at 54.1%.
   - A change to the stand-in `tests/smoke/stand_ins/s3.py` now selects 190 test files instead of
     297.
6. **The tests that checked the re-exports were rewritten, not deleted, so the count holds.**
   - `test_discovery.py`'s `test_the_port_module_re_exports_the_discovery_values_rather_than_restating_them`
     is now `test_the_port_names_the_discovery_values_rather_than_restating_them`. It checks that
     `SearchProvider.search`'s type hints are the domain's own classes, and that `providers.__all__`
     lists none of them.
   - `test_search_provider_is_the_only_port_that_answers_a_provider_query` walked `ports.__all__`. It
     now walks every Protocol defined in any port module, which is a superset, and still finds only
     `SearchProvider.search`.
   - `test_port_conformance.py` imports each port module by name instead of reading it as an
     attribute of the package.
7. **The guard has a third rule the PM did not list: a port module's `__all__` names only what it
   defines.** That is the shape the `providers.py` re-export had, and nothing else would catch it
   growing back. It is cheap, and it is shown red above.
8. **A socket warning in narrowed runs.**
   - `test_extractor.py::test_nothing_in_debate_core_produces_extracted_evidence_from_free_text`
     imports every `debate_core` module. The first import of `urllib3` probes for IPv6 by opening a
     local socket, and pytest-socket blocks it with a `UserWarning`. The test passes.
   - On the base, the package-root conftest imported `boto3` at collection, so `urllib3` was always
     loaded before any test ran. Now that only happens when one of the four fixture directories is
     collected.
   - A whole-selection run collects every conftest first, so CI behaves as before. A run of
     `evidence/` alone shows the warning. I verified that by running the one test at `ffbfb2c` (no
     warning) and at the branch (one warning).
   - I left it visible rather than importing `urllib3` somewhere to hide it.
9. **`--graph` follows t29's harness exactly.**
   - It is `select(Tree.at(root, REV2), changed_files(...))`, the method you accepted in t29's ruling
     1, so the columns compare like with like.
   - It works with `--diff`, `--head` and the default mode, and refuses `--run`.
   - A changed file the graph's tree lacks is reached there only by name, and the script lists such
     files on stderr. None of the 20 commits had any.
10. **Parallel sessions.**
    - v1-e31-t30 merged into `dev` as #401 during the session, and `scripts/task sync` rebased this
      branch onto it with no conflicts. Its new files needed no import updates: both codemods in
      `--check` mode → `0 files would change`. Its tests do not use the moved fixtures, and pyright
      and collection pass on the synced tree.
    - v1-e39-t07 had not merged into `origin/dev` (`ffbfb2c`) when I finished, so there was nothing
      of it to update. Whichever of us merges second gets the other's files: if it lands first, its
      `debate_core.testing.fakes` or `application.ports` imports need the rewrite at the next sync.
      The codemod's mapping is mechanical: name to module, from each new module's `__all__`.
    - I did not touch either branch.

## Operator follow-ups

None. The whole default selection runs in the pull request's required `ci` check. If it fails, the
failing part's output comes back to this session (working agreement 10).

## Follow-up work

- **What still carries the selection.** I traced the near-median rows over this branch with
  `select()`'s reasons, counting the links most selected tests' chains share:
  - **The CLI composition root.** `debate_cli.container`, `debate_cli.app` and the
    `debate_cli.commands` package are on 55 to 87 of the chains in `0a43e88`, `72c1d05` and
    `4c5a766`. `debate_cli/commands/__init__.py` imports all 15 command modules to register them, so
    a test of one command reaches every command. That is wiring rather than a re-export, but moving
    the registration out of the package module would be the same kind of cut as the two emptied
    here.
  - **`packages/debate_core/tests/application/caselist/conftest.py`** is beneath 16 to 54 of the
    selected tests in the same commits.
  - The rest is code the tests really use (`caselist_parse`, `caselist_sync`, `inbox_purge`).
- **`affected_tests.py` reads short quoted strings as file names.** `"s3"` in
  `boto3.client("s3")` named `tests/smoke/stand_ins/s3.py`, and `"evidence_bucket"` named an
  infrastructure folder (Decision 5). A minimum length, or a slash, before a bare quoted word counts
  as a path part would remove both kinds of false edge. That rule is in t28's script, so it is yours
  to place; I did not change it.
- **One whole-selection rule you might revisit.** `29f074d` changed only an import-linter contract
  in the root `pyproject.toml`, which cannot change what pytest runs, yet it is the whole selection.
  A rule that read which table of the root `pyproject.toml` changed could select only
  `tests/architecture` for such a change. The other three are dependency changes with `uv.lock`, and
  the whole selection is right for them. Per your note, I report this and changed nothing.
- **`debate_core/testing/contracts/__init__.py` re-exports every contract suite,** the pattern this
  task and t29 removed elsewhere. It was outside this task's list.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
