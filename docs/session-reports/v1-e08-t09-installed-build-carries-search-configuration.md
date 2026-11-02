# Session report: v1-e08-t09-installed-build-carries-search-configuration

| | |
|---|---|
| Task | `v1-e08-t09-installed-build-carries-search-configuration` — An installed build carries the configuration `search` reads: the argument taxonomy, the ranking table and the feed lists |
| Spec | [`plan_specs/v1/e08-research-workflows/t09-installed-build-carries-search-configuration.yaml`](../../plan_specs/v1/e08-research-workflows/t09-installed-build-carries-search-configuration.yaml) |
| Epic / release | `v1-e08-research-workflows` / `v1.4` |
| Branch | `task/v1-e08-t09-installed-build-carries-search-configuration` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

An installed build now carries everything `search` reads. `scripts/stamp_build.py`'s
`bundle_configuration` copies `config/argument_taxonomy.yaml`, `config/federated_ranking.yaml` and
every `config/feeds/*.yaml` into `_bundled_config/config/`, each at its place and byte for byte, and
refuses a checkout that lacks any of them. `check-wheels` requires those two files, `search
--expand-llm`'s prompt (`prompts/search/expand.md`, already bundled with the other prompts but not
required), and every feed list the checkout it runs in commits. If that checkout commits no feed
list, check-wheels refuses rather than pass with nothing to compare. I proved it on locally stamped,
installed builds, as v1-e06-t06 did. A wheel stamped by today's script failed
`tests/smoke/test_search_smoke.py` (4 failed, 1 passed), and this branch's script refuses that wheel.
This branch's wheel passes the same check (5 passed). The PM may want to look first at the one design
choice: check-wheels takes the feed lists to require from the checkout's `config/feeds/`, not from a
fixed list (see Decisions).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `installed-build-carries-search-configura` (Search config bundled) | Done | Red tests against a skeleton (`4911ead`), implementation (`0beed9d`), a test for the survivor of the mutation run (`7c39ced`). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the stamp bundles the taxonomy, the ranking table and every feed list (and anything else search reads), check-wheels refuses a wheel without them, and the search smoke check passes on a locally stamped, installed build, red on today's stamp first | PASS | **The stamp bundles them**: `tests/scripts/test_stamp_build.py` checks the bundled tree, each file's bytes against the committed copy, and that the bundled copies load with `load_argument_taxonomy`, `load_federated_ranking_config` and `load_feed_directory` as the container loads them. The branch's real stamp printed `stamped …/_bundled_config/config/argument_taxonomy.yaml`, `federated_ranking.yaml`, `feeds/health-insurance.yaml`, `feeds/politics.yaml`, and `unzip -l` of its debate_cli wheel lists all four. **check-wheels refuses a wheel without them**: this branch's `python3 scripts/stamp_build.py check-wheels --version 0.0.1.dev1 --dist <today's red build>/dist` → exit 1, four lines `missing debate_cli/_bundled_config/config/{argument_taxonomy.yaml, federated_ranking.yaml, feeds/health-insurance.yaml, feeds/politics.yaml}`; today's own check-wheels had said `wheels in dist are publishable as 0.0.1.dev1`. **Red on today's stamp**: build of `9a614d4` (today's script), `DEBATE_SMOKE_BIN=<scratch>/red-today/venv/bin/debate-research … pytest tests/smoke/test_search_smoke.py -n 0` → `4 failed, 1 passed`: the bundled-files probe found them missing, `('INVALID_ARGUMENT_TAXONOMY', 1) == ('NO_PROVIDER_ENABLED', 1)`, and the unknown-argument and need-outside-family checks got exit 1 not 2, each with `INVALID_ARGUMENT_TAXONOMY` naming `…/site-packages/debate_cli/_bundled_config/config/argument_taxonomy.yaml`. **Green on this branch's stamp**: build of `0beed9d`, same command → `5 passed in 3.81s`. |
| Node: Search config bundled tests pass (`uv run pytest tests/scripts/test_stamp_build.py tests/smoke/test_search_smoke.py`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run pytest tests/scripts/test_stamp_build.py tests/smoke/test_search_smoke.py` → `51 passed in 6.71s` (46 stamp tests; the 5 smoke checks against this checkout's console script, where the bundled-files probe asserts no bundle). |

### Red run

The new tests ran against a refuse-nothing skeleton (`4911ead`). In that skeleton
`required_cli_members` and check-wheels' `repository` parameter exist, so the tests build their wheels.
But check-wheels still checked only the old fixed list, and the stamp copied only the old files.
Result: `14 failed, 31 passed in 2.19s`, every failure at its assertion:

* check-wheels with each of the taxonomy, the ranking table, each feed list and `prompts/search/expand.md`
  deleted: `assert [] == ['… missing …']` (5).
* a feed list the checkout commits after the wheel was built: `assert [] == ['… missing …/new-topic.yaml']`.
* a checkout that commits no feed list: `assert 0 == 1` (no problem reported).
* the bundled tree list: missing `argument_taxonomy.yaml` and `federated_ranking.yaml`.
* the stamp's refusals for a checkout without the taxonomy, the table or any feed list: `DID NOT RAISE StampError` (3).
* the byte comparison and the feed list test: `FileNotFoundError` on the bundled copy, which is
  the missing file itself (2).
* the loading test: `InvalidArgumentTaxonomy: …/_bundled_config/config/argument_taxonomy.yaml could not be read`,
  the installed build's own error.

`test_a_wheel_of_what_the_stamp_bundled_passes_check_wheels` passed on the skeleton, as it should.
It checks that the stamp and check-wheels agree, and the mutants below are its red runs.

### Mutation run

Eleven mutants of `scripts/stamp_build.py`. Each was applied to the committed file, run against
`tests/scripts/test_stamp_build.py`, and restored with `git checkout HEAD --`. No Hypothesis
property is involved.

| Mutant | Caught by |
|---|---|
| The stamp leaves one feed list out (`health-insurance.yaml`), PM's | 3 tests, including `test_a_wheel_of_what_the_stamp_bundled_passes_check_wheels` (check-wheels refuses the stamped tree). Also on a real build: HEAD extracted, the stamp so mutated, both wheels built → check-wheels `missing debate_cli/_bundled_config/config/feeds/health-insurance.yaml`, exit 1 |
| The stamp leaves the taxonomy out (copy and refusal), PM's | 5 tests, including check-wheels refusing the stamped tree |
| The stamp leaves the ranking table out (copy and refusal) | 5 tests |
| check-wheels' taxonomy requirement removed, PM's | `test_a_wheel_without_what_search_reads_is_refused[…argument_taxonomy.yaml]` |
| check-wheels' ranking table requirement removed | the same test's `federated_ranking.yaml` case |
| check-wheels' `expand.md` requirement removed | the same test's `expand.md` case |
| check-wheels' feed list requirement removed, PM's | 3 tests (both feed cases, the new-topic test) |
| check-wheels back to the fixed list only | the same 3 |
| check-wheels' refusal with no committed feed list removed | `test_check_wheels_refuses_when_the_checkout_commits_no_feed_lists_to_compare` |
| The stamp's refusal with no feed list removed | `test_stamp_refuses_a_checkout_without_what_search_reads[config/feeds…]` |
| `check-wheels --repository` ignored | **survived** the first run; `test_the_check_wheels_command_reads_the_feed_lists_of_the_checkout_it_names` added (`7c39ced`), and a rerun catches it (1 failed, 45 passed) |

### Checks before the report

* `uv run scripts/affected_tests.py` chose 46 of 660 test files from 5 changed files. The run
  (`.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python scripts/affected_tests.py --run`)
  reached about 99% with no failure and was stopped at its 115-second limit (exit 124). It is over two
  minutes on this machine (load about 5), so under agreement 10 it is left to the pull request's `ci`
  check. Within the limit I ran the changed test files and the always-run list
  (`tests/architecture/`, `tests/specs/`, the CLI's `test_app.py`, `test_help_rendering.py`,
  `test_container_factories.py`) with `-m "not slow and not live"` → `428 passed in 21.66s`.
* The other installed-build smoke files against this branch's build:
  `tests/smoke/test_cli_smoke.py tests/smoke/test_cut_smoke.py` → `21 passed`. The new bundled files
  break no pin there.
* `ruff format --check .` → 1830 files already formatted; `ruff check .` → all checks passed;
  `pyright scripts/stamp_build.py tests/scripts/test_stamp_build.py tests/smoke/test_search_smoke.py`
  → 0 errors (no package source changed); `lint-imports` → 20 kept, 0 broken;
  `scripts/check_thin_handlers.py` → OK; `uv run scripts/validate_specs.py` → `OK: 585 files, 41 epics, 522 tasks, 22 releases`.

## Files changed

* `scripts/stamp_build.py`: bundles the taxonomy, the ranking table and every feed list, and refuses a
  checkout without them. check-wheels requires those, `prompts/search/expand.md` and every committed
  feed list, refuses when the checkout commits none, and takes `--repository`. The docstring says so.
* `tests/scripts/test_stamp_build.py`: tests for each file bundled and required, the stamp's
  refusals, the bundled copies loading as `search` loads them, the stamp and check-wheels agreeing,
  and the check-wheels command's `--repository`.
* `tests/smoke/test_search_smoke.py`: the bundled-files probe checks every feed list the checkout
  commits, not only `politics.yaml`. It passes the names as arguments.
* The spec's phase, and this report.

## Deviations from the spec

None.

## Decisions and assumptions

* **What `search` reads.** I read the container (`_build_federated_search`, `_build_discovery_providers`,
  `_committed_root`) and `build_info.bundled_config_root`. `search` reads
  `config/argument_taxonomy.yaml`, `config/federated_ranking.yaml`, `config/feeds/*.yaml` (only
  `*.yaml`, and only when `rss` or `google_news` is enabled, as the dev profile does), and with
  `--expand-llm` `prompts/search/expand.md`, all from the bundled root. The profiles and routing and
  pricing files were already bundled. The taxonomy's loader reads nothing else:
  `domain/argument_taxonomy.py` says its topic presets copy `config/landscape/topics.yaml`'s values,
  and "Nothing here reads the landscape files". So the landscape topics are not bundled. The
  registry does not read `prompts/prompts.lock.json`, which was already bundled and stays unrequired.
  The feeds `README.md` is not read and not bundled.
* **The feed lists to require come from the checkout, not a constant.** check-wheels runs in the
  checkout the stamp ran in (`dev-prerelease.yml`). So it requires each `config/feeds/*.yaml` there,
  and a new topic's feed list is required with no code edit (the prompts tests made the same move
  after v1-e08-t04's CI failure). The cost is that check-wheels now reads the checkout. With no feed
  list to compare against, it refuses instead of passing, so it fails closed. `--repository`
  (default: the checkout the script is in) matches `stamp`'s option.
* **The stamp refuses a checkout without what `search` reads**, as it refuses one with no
  `profiles/dev.toml` or no prompts, so a broken checkout fails before the wheels are built.
* **Forbidden list.** No installed build reads configuration from the working directory or home.
  `_committed_root` was already bundled root first, then the checkout around the code. The installed
  `search` runs from the harness's scratch working directory and passed, and its earlier error named
  the `site-packages` copy. No bundled file's content changed, and tests compare bytes. No test uses
  the network. The local builds were offline (`uv build --offline`, `uv pip install --offline --no-deps`).
* **How the installed builds were made** (memory of v1-e05-t12's method): `git archive <commit>` into a
  scratch directory, then `stamp_build.py stamp … --repository . --dist dist`, `uv build --offline` for
  each package, a scratch venv on uv's managed CPython 3.12 with both wheels installed
  `--no-deps`, and a plain-path `.pth` to the worktree venv's `site-packages` for third-party
  dependencies. `debate_cli.__file__` and `debate_core.__file__` were in the scratch venv, with no
  `packages/*/src` on `sys.path`. Each build took about 2 seconds.

## Operator follow-ups

None. The spec's description asks that a pre-release from this change pass validate-dev's smoke
tier. That happens after the merge, on the next dev pre-release. It is not one of the acceptance
criteria, and the local installed build above passes the same check.

## Follow-up work

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
