# Session report: v1-e01-t31-repo-check-false-positives

| | |
|---|---|
| Task | `v1-e01-t31-repo-check-false-positives` — Repository checks stop flagging true values, and the smoke tests type-check |
| Spec | [`plan_specs/v1/e01-repo-foundation/t31-repo-check-false-positives.yaml`](../../plan_specs/v1/e01-repo-foundation/t31-repo-check-false-positives.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t31-repo-check-false-positives` |
| Session status | COMPLETE |

## Summary

`tests/architecture/test_single_interpreter_source.py` now counts a `3.8`–`3.19` as a Python version
only in a Python context. That means a python word on the same line or on the line that opens its
block, a `pyenv` or `PY_` word, or any line of a `.python-version` file. A number followed by `%` or a
unit, and a version that follows SQLite, Node, Node.js, Next.js, Lighthouse or axe-core, is never a
Python version. Each figure a session had to reword now passes, and each shape of a real second
declaration still fails, in tests shown red first (once against the old scanner and once against a
scanner that flags nothing). A capped mutation run (16 mutants) checked them. Across the real tree
the narrowing lets exactly one line through, a sample-data `assert "3.12.7" in captured.out`, so
its exemption goes. `uv run pyright tests/smoke` and `uv run pyright tests/architecture` both report
0 errors, with no change to what any test checks. **Look first** at the PM questions at the end:
CI's pyright scope is set in `pyproject.toml`, not in `ci.yml`. Also, the docs/evidence name was
already fixed on `dev` by `v1-e01-t30`, and the name in the brief would itself be wrong.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `checks` (Check false positives) | Done | Interpreter check narrowed, with tests and mutants; smoke and architecture tests type-check; docs/evidence name confirmed correct (see Deviations). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the interpreter check passes on a measured time and a SQLite version, and still fails on a second Python version declaration, by tests shown failing first | PASS | Red against the old scanner (commit `af0467a`): `.venv/bin/python -m pytest -q -p no:randomly -n 0 tests/architecture/test_single_interpreter_source.py` → `17 failed, 38 passed`. The failures were all 12 figure and other-product cases (3.9 ms, SQLite 3.11.0, at most 3.9%, SQLite 3.9.0 and 3.8.3, plus Node, Next.js, Lighthouse, axe-core and a bare version), the three mixed lines (Python beside SQLite or a time), the block-opener test and the planted false-positive tree. "SQLite 3.40.0" passed even on the old scanner: `3.40` was never a candidate. Red against a scanner that flags nothing (`python_versions_named` returning `[]`): `30 failed, 25 passed`. Every declaration shape failed: a second `requires-python`, `uv python install` and `--python` in a workflow, a YAML list under `python:`, a nested `.python-version`, `FROM python:3.x` and the Lambda base image, a trove classifier, `pyenv`, `PY_VERSION`, `py -3.x` and the tags. Green on the final code: `55 passed in 2.80s`. |
| ac2: `uv run pyright tests/smoke` reports no errors, and the stale name in docs/evidence is fixed | PASS | `uv run pyright tests/smoke` → `0 errors, 0 warnings, 0 informations` (19 errors before). `uv run pyright tests/architecture` → `0 errors` (2 before). `docs/evidence/snapshot-text-format.md:299` names `debate_core.testing.fakes.card_edit_log.InMemoryCardEditLog`, which `v1-e01-t30` (649fc66) put there; `.venv/bin/python -c "from debate_core.testing.fakes.card_edit_log import InMemoryCardEditLog"` → imports. See Deviations. |
| Node `checks`: Architecture tests pass (`uv run pytest tests/architecture`) | PASS | Run with the alarm on the interpreter, `.venv/bin/python -m pytest tests/architecture -q` → `199 passed in 10.88s`. |

### Mutation run

Each mutant loosens the narrowing in a way that could let a real declaration through. Each one was
applied to the committed file, the check's 55 tests were run (`-n 0 -p no:randomly`, alarm on the
interpreter), and the file was restored and confirmed byte-identical with `git diff --exit-code`.
The check uses no Hypothesis, so agreement 8's database rule has nothing to isolate.

First pass (18 mutants): 14 caught, 4 survived. Two survivors were lookbehinds that no test and no
line in the tree could tell from their absence: the figure's `(?<![\d.])` (leftmost matching already
starts at the whole number) and the product names' `(?<![\w.-])` (the names are case-sensitive proper
nouns). Under agreement 8 I deleted both (`0ca4418`) rather than write tests to justify keeping them.

Final pass on the shipped code (16 mutants applied, the 2 deleted lookbehinds no longer apply):

| Mutant | Result | Caught by |
|---|---|---|
| `pyenv` is not a python word | CAUGHT | `[pyenv]` |
| a standalone `py` is not a python word | CAUGHT | `[a py variable]`, `[the Windows launcher]` |
| python words are case-sensitive | CAUGHT | 12 tests, incl. the exemption guard |
| `python` only as a whole word | CAUGHT | `PYTHON_VERSION=3.12`, `python3.13`, `UV_PYTHON` |
| `.python-version` files give no context | CAUGHT | the pin test and the planted declaration tree |
| the block opener gives no context | CAUGHT | the block test and the planted declaration tree |
| siblings count as block openers | CAUGHT | the opener-pairing test |
| a unit may run into the next word | CAUGHT | `[an s3 URL is not seconds]` |
| a product's list runs through any words | CAUGHT | `[SQLite before Python]` |
| a product anywhere clears the whole line | CAUGHT | `[Python before SQLite]`, `[SQLite before Python]` |
| tags need a python word too | CAUGHT | `py312`, `cp313` |
| a python word on the line is not enough (opener only) | CAUGHT | 26 tests |
| masking spans reach past their end | CAUGHT | `[SQLite before Python]` |
| a size swallows the next version | CAUGHT | `[Python 3.9 is the floor]`, the exemption guard |
| `\s?` before a unit becomes `\s*` | SURVIVED (equivalent) | No real declaration is followed by a run of spaces and a standalone unit word. |
| a bare `m` is a unit | SURVIVED (equivalent) | The lookahead still requires the unit to stand alone, and `python3.x -m` has a hyphen before the `m`. `min` was dropped from the unit list (`c232713`) for this reason: "Python 3.12 min" would have been masked. |

### Checks run before the report

| Command | Result |
|---|---|
| affected set: `uv run scripts/affected_tests.py 2>/dev/null` for the list, then what `--run` runs, with the alarm on the interpreter: `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -n auto -m "not slow and not live" -q <42 files>` | 42 test files, `1665 passed in 78.33s` (load average about 12) |
| `uv run ruff format --check .` | `1179 files already formatted` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run pyright tests/smoke tests/architecture` | `0 errors` (no package changed, so CI's `pyright` over `packages` is untouched) |
| `uv run lint-imports` | `Contracts: 16 kept, 0 broken.` |
| `uv run scripts/check_thin_handlers.py` | `OK: 47 CLI command and API route handlers within 25 statements` |
| `uv run scripts/validate_specs.py` | `OK: 431 files, 40 epics, 369 tasks, 22 releases` (re-run after the phase change, below) |
| touched smoke tests: `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -m "not slow and not live" -q -p no:randomly tests/smoke/test_caselist_pull.py tests/smoke/test_caselist_pull_in_process.py tests/smoke/test_caselist_runs.py tests/smoke/test_cli_smoke.py::test_prod_refuses_each_stand_in_endpoint_with_a_message_naming_the_setting tests/smoke/test_site.py` | `25 passed in 21.66s`, including all six edited tests (confirmed with `--co`) |

## Files changed

* `tests/architecture/test_single_interpreter_source.py`: the narrowing (`PYTHON_WORD`, `FIGURE`,
  `OTHER_PRODUCT_VERSION`, `PYTHON_VERSION_FILES`, `python_versions_named`,
  `lines_with_block_openers`) and its docstring. It adds 32 test cases (23 tests before, 55 after) (line-level false positives and
  declaration shapes, the block-opener and pin tests, and two planted trees, one of true figures and
  one of every declaration shape). The `test_output.py` sample-data exemption is removed.
* `tests/smoke/test_caselist_pull.py`, `test_caselist_pull_in_process.py`, `test_caselist_runs.py`:
  boto3's optional `Contents`/`Key` read with `.get`, as the other smoke listings already do.
* `tests/smoke/test_cli_smoke.py`: `assert isinstance(error, dict)` before indexing the envelope's
  error, as the file's other error checks do.
* `tests/smoke/test_site.py`, `tests/architecture/test_thin_handlers.py`: a scoped
  `# pyright: ignore[reportMissingImports]` on the import from `scripts/`, which they reach through
  `sys.path`.
* `tests/architecture/test_fakes_reach_only_their_port.py:133`: the walk's queue annotated
  `list[tuple[str, str | None]]`.

## Deviations from the spec

* **The docs/evidence name needed no change.** `v1-e01-t30` (649fc66, 2026-10-22, after this spec
  was filed) already replaced `debate_core.testing.InMemoryCardEditLog` with
  `debate_core.testing.fakes.card_edit_log.InMemoryCardEditLog`, which imports. The PM context names
  `debate_core.testing.fakes.InMemoryCardEditLog` as the target, but that name does not resolve:
  `debate_core.testing.fakes/__init__.py` imports nothing, by `v1-e01-t30`'s design (`hasattr` →
  `False`). I left the doc as it is. `grep -rn "debate_core\.testing\.[A-Z]" docs/evidence` finds no
  other stale name.
* **More pyright errors than the spec names.** Beyond `test_caselist_pull_in_process.py` and
  `test_caselist_runs.py`, `pyright tests/smoke` also reported `test_caselist_pull.py` (4, the same
  boto3 kind), `test_cli_smoke.py` (7, `object` envelope values, since `v1-e34-t30`) and
  `test_site.py` (1, the `scripts/` import). The goal is `pyright tests/smoke` clean, so I fixed all
  of them, inside `tests/smoke`.
* **What "no change of behaviour" means for the `.get` reads.** `["Contents"]` raised `KeyError` on
  an empty listing, and `.get("Contents", [])` gives an empty collection. Every one of the six
  listings is followed by an assertion that needs it non-empty (`... in published`, `== [key]`,
  `sorted(...) == [<two keys>]`), so each test passes and fails on exactly the same states as before;
  only the failure's message differs. `str(one.get("Key"))` matches the file's own `keys_in` and S3
  always returns `Key` on a listed object.

## Decisions and assumptions

* **"Nearby" means the same line or the line that opens its block,** the nearest less-indented line
  above. That catches a YAML list under `python:` in a workflow, which a same-line rule would miss,
  without reading whole paragraphs as context. In a Python file the opener of a function body is its
  `def` line, so a `def test_python_...` gives its body context. That is still a subset of what the
  old scanner flagged, never more.
* **Tags (`py312`, `cp313`) stay Python versions anywhere.** They cannot mean anything else, and
  ruff's `target-version = "py312"` is a real second declaration with no python word on its line.
* **The product list is explicit,** not "any word before a version". A general rule would read
  `uv python install 3.13` as `install`'s version and let a real pin through. I added `SQLite3`
  (Python's module name) to the PM's list. Matching is case-sensitive.
* **Units:** `%`, `ms`, `s`, `sec`, `seconds`, `minutes`, `KB`, `kB`, `MB`, `GB`, `TB`, `KiB`, `MiB`,
  `GiB`, and a unit must stand alone (`s3://` and `min-age` are not units). `min` is left out
  because "Python 3.12 min" is a plausible declaration.
* **The CI matrix rule is unchanged.** A `python-version:` key line in a workflow is still derived.
  A YAML list under such a key is still flagged item by item, as before; the new block-opener rule
  gives those items the same context.
* **The figures reworded in `v1-e39-t03`, `t12` and `t13` are not restored.** They live in those
  tasks' files, outside this task's packages; the check now allows them, and a later edit may put
  them back.

## Operator follow-ups

None.

## Follow-up work

* `uv run pyright tests` reports 48 errors across the other test directories (measured
  2026-10-23). If the PM wants all of `tests/` in CI's scope (question 1), that is a task of its own
  in E01.

### Questions for the PM

The relay block below is ready to paste. My recommendation and the reason are given with each.

```text
v1-e01-t31 questions (session finished; every acceptance criterion PASS, phase Succeeded).

1. CI's pyright scope. The step in ci.yml is a bare `uv run --frozen pyright`, so its scope is
   pyproject.toml's `[tool.pyright] include = ["packages"]`, not the workflow. Bringing
   tests/architecture (and tests/smoke) in means editing pyproject.toml, which is outside this
   task's packages and makes affected_tests select the whole suite.
   Options:
   (a) A follow-up E01 task: include = ["packages", "tests/architecture", "tests/smoke"] plus
       extraPaths = ["scripts"], and remove the two `# pyright: ignore[reportMissingImports]`
       comments this task added. Measured with a temporary pyrightconfig.json: 0 errors, and the
       imports from scripts/ then resolve and are type-checked through.
   (b) Amend this task's packages to add pyproject.toml and do (a) here; CI then runs the whole
       selection anyway.
   (c) Leave the scope as is; the two directories are clean today but can drift again.
   Recommendation: (a). Both directories are at 0 errors, so the change costs nothing now and
   stops the next error from hiding. A separate task keeps this PR's affected set small. Including
   all of tests/ would bring in 48 existing errors, so that is a bigger job.

2. The docs/evidence name. v1-e01-t30 already changed it to
   debate_core.testing.fakes.card_edit_log.InMemoryCardEditLog, which imports. The name in the
   brief, debate_core.testing.fakes.InMemoryCardEditLog, does not resolve (fakes/__init__ imports
   nothing). I left the doc unchanged and marked ac2 PASS on that basis.
   Recommendation: accept as is; no spec change needed.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-24

**Notes:**

1. **The narrowing is right, and it is proven both ways.**
   * Red against the old scanner and against a scanner that flags nothing.
   * Every figure a session had to reword now passes.
   * Every declaration shape still fails, including ruff's `py312`.
   * The two first-pass survivors were deleted rather than justified. The two final survivors are
     equivalent, as argued.
   * Dropping `min` from the units for "Python 3.12 min" is exactly the care this check needs.
2. **The extra pyright fixes are accepted as within ac2's goal.** The `.get` reads change only a
   failure's message, as the Deviations show.
3. **Rulings**
   * **Q1 (a).** The PM files an E01 task: CI's pyright `include` gains `tests/architecture` and
     `tests/smoke`, with `extraPaths = ["scripts"]`, and the two scoped ignores this task added are
     removed.
   * **Q2:** accepted as is. The name in the PM's brief was wrong, and the doc already carries the
     right one from v1-e01-t30. That is the PM's error, and nothing in the spec needs changing.

**The PR:** opened without `--partial`. No condition.
