# Session report: v1-e05-t04-prompt-registry

| | |
|---|---|
| Task | `v1-e05-t04-prompt-registry` — Versioned prompt registry |
| Spec | [`plan_specs/v1/e05-model-router/t04-prompt-registry.yaml`](../../plan_specs/v1/e05-model-router/t04-prompt-registry.yaml) |
| Epic / release | `v1-e05-model-router` / `v1.2` |
| Branch | `task/v1-e05-t04-prompt-registry` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Prompts are now versioned, reviewed files. Each file under `prompts/` is one version of one prompt: YAML front matter that the domain's `PromptSpec` validates, then a Jinja2 body.

- **Loading.** `PromptRegistry` (`debate_core.integrations.models.prompt_registry`) loads every prompt file. It refuses each of these, naming the file:
  - a duplicate (prompt_id, version);
  - a version that is not `MAJOR.MINOR.PATCH`;
  - a prompt id that cannot name a fixture directory;
  - an output schema that is not a Pydantic model.
- **Rendering.** Rendering is strict and deterministic. A missing or unused variable is a `PromptRenderError`, and mappings render with their keys sorted. `render` is the renderer the Bedrock router takes.
- **Provenance.** Every structured result carries `ModelResponse.metadata`, a `GeneratedArtifactMetadata` built from its own route, prompt and time.
- **The lock.** `prompts/prompts.lock.json` pins each released version's body hash, schema and task class. A test fails when a released prompt no longer matches it. `scripts/lock_prompts.py` only ever adds entries.

t02 merged into dev during the session, so I synced and did the move and the wiring as the PM's notes asked:

- `RenderedPrompt` now lives only in `domain.model_contracts`.
- `bedrock_router_factory(registry)` is the `real_router` that lets record and live mode send structured calls.

**Look first at:**
- the red run;
- the one mutant that survived at first and what it exposed (a test case, not the check);
- Deviation 3: the sample prompt is a test fixture, so the committed lock is empty today.

All five Goal criteria and every node criterion pass. The Goal is `Succeeded`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `prompt-format`: Prompt file format and example | Done | `domain/prompt_spec.py`: `PromptSpec`, `ChangelogEntry`, `PromptStatus`, `PROMPT_ID_PATTERN`, `prompt_version_key`. The format is documented in `prompts/README.md`. The sample prompt is `tests/fixtures/prompts/example/select-passage.md` (Deviation 3). t03's fixture and cassette directories now import the same id rule. |
| `registry-loader`: PromptRegistry loader and renderer | Done | `integrations/models/prompt_registry.py`: load, `get` (exact or `latest`), `prompt`, `render`. Schemas resolve by dotted path, and templates render with `StrictUndefined` in Jinja2's sandbox. |
| `artifact-metadata`: GeneratedArtifactMetadata and router integration | Done | `domain/provenance.py`. `ModelResponse.metadata` is a property, so no router and no cassette changed. After the sync, Bedrock gets the registry's renderer (`bedrock_router_factory`). |
| `version-lock`: Released-version lock | Done | `integrations/models/prompt_lock.py`, `prompts/prompts.lock.json`, `scripts/lock_prompts.py`. |

## Acceptance criteria

**The red run (PM notes: "show each behaviour failing first").** I wrote the tests before the checks, against a skeleton that loaded and rendered the happy path and refused nothing. It had no duplicate check, no version or id rule and no schema check. It rendered without `StrictUndefined` or key sorting, picked `latest` as the lexical maximum, had no `metadata` property, and its `compare_lock` returned nothing. The skeleton is committed as `9385ab7`, "Prompt registry tests, written first against a skeleton that refuses nothing".

```
uv run --frozen pytest -n 0 -q packages/debate_core/tests/integrations/models/test_prompt_registry.py \
  packages/debate_core/tests/integrations/models/test_artifact_metadata.py \
  packages/debate_core/tests/integrations/models/test_prompt_lock.py \
  packages/debate_core/tests/domain/test_prompt_spec.py tests/scripts/test_lock_prompts.py
```

That gave `138 failed, 45 passed in 4.03s`, with no collection error. The failures, grouped by their `E` line:

- `DID NOT RAISE PromptRegistryError`: 49.
- Raw Pydantic `ValidationError`s, Jinja2 syntax errors and unpacking `ValueError`s escaping unwrapped, where the test expected a `PromptRegistryError` naming the file.
- `DID NOT RAISE ValidationError`: 7.
- `DID NOT RAISE PromptRenderError`: 7.
- `'ModelResponse[ContractPassage]' object has no attribute 'metadata'`: 6.
- `DID NOT RAISE PromptLockError`: 3.
- Lock comparisons that found nothing, and `latest` returning `1.9.0`.

The 45 that already passed fall into four groups:

- valid input that must be accepted (good ids and versions, the happy-path render);
- tests that must *not* flag something (a draft edited, the owner corrected);
- the plain data type's round trip, and the constraints of existing domain types (a ULID, a UTC time);
- two things the skeleton got right by accident: Jinja2's own determinism for identical calls, and a numeric `prompt_version_key`.

The dict-order determinism test was red. Rendering a mapping followed the caller's insertion order, while the fixture key sorts it, so two calls with one key could send different text. Sorting the keys fixed it.

After the checks were added: the same command gives `185 passed in 1.38s`. Two tests were added on the way, for a YAML key given twice and for `prompt()` checking variables.

**The wiring's red run.** I saved copies of the five rewired files and restored t02's versions. I added a stand-in `bedrock_router_factory` that returns `bedrock_model_router` with no renderer, which is all a composition root could do before this change. Then I ran `test_prompt_registry_wiring.py`: `3 failed, 2 errors`.

- Live and record were refused with t02's "no prompt renderer is configured". The 2 errors are the Stubber's teardown reporting its planned answer unconsumed.
- The third test failed on the message, which did not yet name the factory.

I restored the copies, compared each with `cmp`, and checked that the stand-in was gone: `grep -c "red-run stand-in"` → `0`.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: PromptRegistry loads every `prompts/**/*.md` file and rejects duplicate (prompt_id, version) pairs, invalid semver, or an output_schema that does not resolve to a Pydantic model | PASS | `test_prompt_registry.py`, 121 passed. Tests: `test_every_markdown_file_under_the_directory_is_loaded_except_readmes` (nested directories; `README.md` and `.txt` files skipped); `test_two_files_with_the_same_prompt_and_version_are_refused_naming_both`; `test_an_invalid_version_is_refused_naming_the_file_and_the_field` (15 cases, including `01.0.0`, `1.0.0-rc.1` and `'1.0.0 '`); `test_an_unquoted_yaml_number_is_not_mistaken_for_a_version`; `test_an_output_schema_that_is_not_a_pydantic_model_is_refused` (8 cases); `test_an_output_schema_named_by_a_re_export_is_refused_naming_where_it_is_defined`. Mutants 1–10 and 36–37 are caught. |
| ac2: a missing template variable raises PromptRenderError, and rendering is deterministic for identical inputs | PASS | `test_a_missing_variable_raises_prompt_render_error_naming_it` covers an expression, a condition, a loop, `default(...)` and the system turn. Also `test_a_missing_key_inside_a_variable_raises_prompt_render_error`, `test_a_variable_the_template_never_uses_is_refused`, `test_a_mapping_renders_the_same_whatever_order_its_keys_were_given_in` and `test_rendering_is_deterministic_across_registries_and_calls`. `test_rendering_is_deterministic_across_interpreters_and_hash_seeds` runs fresh interpreters under `PYTHONHASHSEED` 0 and 4242. `test_rendering_the_sample_gives_the_hand_written_system_and_user_text` checks text written out by hand. Mutants 27–35 and 38 are caught. |
| ac3: GeneratedArtifactMetadata is populated automatically from the ResolvedRoute and prompt on every generate_structured result, and round-trips through JSON unchanged | PASS | `uv run pytest packages/debate_core/tests/integrations/models -k metadata` → `11 passed`. Hand-written expected metadata for three routers: the fixture-keyed fake, replay over the committed cassette, and the scripted fake with every parameter set. `test_metadata_round_trips_through_json_unchanged` uses a hand-written JSON document with every field set, `effort` included, and checks it byte for byte. `test_metadata_survives_a_round_trip_of_the_response_it_came_from` shows a response's JSON holds no `metadata` key, so cassettes are unchanged. After the wiring, the live and record tests show Bedrock results carry it too. Mutants 42–43 are caught. |
| ac4: `prompts/prompts.lock.json` records the sha256 of each released version's body, and a test fails if a released body changes without a version bump | PASS | `uv run pytest packages/debate_core/tests/integrations/models/test_prompt_lock.py` → `29 passed`. `test_every_released_prompt_in_the_repository_matches_the_committed_lock` guards the tree. Hashes are goldens from `shasum -a 256` (`feb58c2e…`, and `7fdbbf79…` for the sample's body). Shown biting on the real tree with a planted prompt (below). Mutants 17–26 are caught. |
| ac5: the registry refuses a prompt_id that is not letters, digits, `.`, `_` and `-` starting with a letter or digit | PASS | `test_a_prompt_id_that_cannot_name_a_directory_is_refused`: 12 cases, including `.hidden`, `-x`, `_x`, `card/select`, `card\select`, a space, `..`, `:`, `é`, a tab, `*` and the empty id. `test_a_prompt_id_of_letters_digits_dots_underscores_and_dashes_is_accepted`: 6 cases. `test_the_registry_and_the_fixture_directories_apply_one_id_rule`: t03's `safe_directory_name` agrees on every case, because it now imports the rule. Mutants 11–16 are caught. |
| Node `prompt-format`: `artifact_exists` `prompt_spec.py` contains `class PromptSpec` | PASS | `grep -c "class PromptSpec" packages/debate_core/src/debate_core/domain/prompt_spec.py` → `1` |
| Node `registry-loader`: `uv run pytest packages/debate_core/tests/integrations/models/test_prompt_registry.py` | PASS | → `121 passed in 1.99s` |
| Node `artifact-metadata`: `uv run pytest packages/debate_core/tests/integrations/models -k metadata` | PASS | → `11 passed in 1.72s` |
| Node `version-lock`: `uv run pytest packages/debate_core/tests/integrations/models/test_prompt_lock.py` | PASS | → `29 passed in 1.61s` |
| Node `version-lock`: `uv run pyright packages/debate_core` | PASS | → `0 errors, 0 warnings, 0 informations` |

**ac4 on the real tree.** The committed lock is empty, because no production prompt is released yet (Deviation 3). So I planted a copy of the sample prompt as `prompts/planted-for-the-red-run.md` and ran the repository test through three states:

1. Released and unlocked: `1 failed`, `LockProblem(kind=UNLOCKED, prompt_id='example.select-passage', ...)`.
2. After `uv run scripts/lock_prompts.py`: `locked example.select-passage@1.0.0`, then `1 passed`. The locked hash was `7fdbbf79…`, the one computed by hand.
3. With "this tag" edited to "the tag" in place: `1 failed`. The script then exited 1 with "has changed since it was released (body_sha256 locked 7fdbbf79…, now 590cb98a…); restore it and make the change as a new version".

I then removed the file and restored the lock with `git checkout`, and `git status` was clean.

**Other checks.**

| Check | Result |
|---|---|
| Default suite, four parts, `uv run --frozen pytest --part K/4` | Part 1: `2012 passed` in 73 s. Part 2: `2020 passed, 1 xfailed` in 49 s. Part 3: `2021 passed, 1 skipped` in 48 s. Part 4: `2013 passed, 1 xfailed` in 67 s. In all, 8,066 passed. Load averages were 4.5 to 19.8. The xfails and the skip are existing parser-eval markers. The three warnings are `tests/smoke/test_network_guard.py` and `test_smoke_harness.py` checking, on purpose, that sockets are blocked. |
| `uv run --frozen ruff format --check .` / `ruff check .` | `784 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright` (all packages) | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 12 kept, 0 broken.` |
| `scripts/check_links.py`, `scripts/check_command_blocks.py`, `scripts/check_thin_handlers.py` | OK: 1631 links in 241 files; no `#` comments in 278 shell blocks; 22 handlers within 25 statements |
| `uv run scripts/lock_prompts.py --check` | exit 0 |
| `uv run scripts/validate_specs.py` | `OK: 362 files, 38 epics, 304 tasks, 20 releases` |
| No network | Every new test is offline. Bedrock is reached through botocore's Stubber, with `boto3`'s `Session.client` replaced, fake credentials, and the suite's socket guard on. No test calls a model. |

### Mutation run

Method:

- Each mutant was applied to the committed tree (after the sync, relative to dev `55d0b4b`), one file at a time.
- The run was `.venv/bin/python -m pytest -q -x -n 0` over the five new test files, t03's fake and replay router tests, and the wiring test.
- Each run had a new, empty `HYPOTHESIS_STORAGE_DIRECTORY`, although none of these tests uses Hypothesis (working agreement 8).
- The file was restored from a byte copy and checked equal, and `git status` was clean after the batch.
- A summary line with an error counted as invalid unless inspected.
- Runs took 0.7 to 1.6 s each. "Caught by" is the first failing test, because `-x` stops there.

The PM asked for mutants on the duplicate check (1–4), the semver check (5–10), the id rule (11–16) and the lock comparison (17–26). **All 43 are caught.**

| # | Mutant | Caught by |
|---|---|---|
| 1 | Duplicate check removed | `test_two_files_with_the_same_prompt_and_version_are_refused_naming_both` |
| 2 | Duplicate key includes the file path | same |
| 3 | Duplicate key is the id alone | `test_the_same_id_at_two_versions_and_two_ids_at_one_version_are_both_allowed` |
| 4 | Duplicate key is the version alone | `test_every_markdown_file_under_the_directory_is_loaded_except_readmes` |
| 5 | Version pattern allows leading zeros | `test_an_invalid_version_is_refused_naming_the_file_and_the_field[01.0.0]` |
| 6 | Version matched as a prefix, not in full | `…[1.0.00]` |
| 7 | `version` field unvalidated | `…[v1.0.0]` |
| 8 | Version key compares text, not numbers | `test_latest_is_the_highest_released_version_by_number` |
| 9 | `latest` takes the lexical maximum | same |
| 10 | `latest` includes drafts | same |
| 11 | Id may start with `.`, `_` or `-` | `test_a_prompt_id_that_cannot_name_a_directory_is_refused['.hidden']` |
| 12 | Id may hold `/` | `…[card/select]` |
| 13 | Id may hold a space | `…[card select]` |
| 14 | Id may hold any Unicode word character | `…[carte.sélection]` |
| 15 | Id matched as a prefix | `…[card/select]` |
| 16 | `prompt_id` field unvalidated | `…['.hidden']` |
| 17 | Lock ignores the body hash | `test_editing_a_released_body_without_a_version_bump_is_found` |
| 18 | Lock ignores the output schema | `test_changing_what_a_released_version_answers_or_how_it_is_routed_is_found[output_schema…]` |
| 19 | Lock ignores the task class | `…[task_class-complex_reasoning]` |
| 20 | Comparison visits only current releases | `test_a_locked_version_whose_file_is_gone_is_found` |
| 21 | A released version set back to draft not flagged | `test_a_locked_version_set_back_to_draft_is_found` |
| 22 | Drafts treated as released | `test_a_draft_may_change_freely_and_is_never_locked` |
| 23 | An unlocked release not flagged | `test_a_tree_that_matches_its_lock_has_no_problems` |
| 24 | `extend_lock` rehashes a changed body | `test_extending_the_lock_refuses_to_rehash_a_changed_body` |
| 25 | Lock `format` unchecked | `test_a_lock_file_that_is_not_a_valid_lock_is_refused_naming_it[unknown-format]` |
| 26 | Body hashed after stripping whitespace | `test_a_body_hash_is_the_sha256_of_the_text_after_the_front_matter` |
| 27 | Lenient `Undefined` | `test_a_missing_key_inside_a_variable_raises_prompt_render_error` |
| 28 | Missing variables unchecked | `test_a_missing_variable_raises_prompt_render_error_naming_it[default-filter]` |
| 29 | Unused variables unchecked | `test_a_variable_the_template_never_uses_is_refused` |
| 30 | Mapping keys rendered in the caller's order | `test_a_mapping_renders_the_same_whatever_order_its_keys_were_given_in` |
| 31 | `render` accepts `latest` | `test_a_call_must_name_the_exact_version_it_renders` |
| 32 | HTML autoescape on | `test_a_mapping_renders_the_same_whatever_order_its_keys_were_given_in` |
| 33 | `random` filter kept | `test_a_template_that_does_not_compile_is_refused_at_load[random-filter]` |
| 34 | `lipsum` kept | `test_a_template_has_no_random_text_generator` |
| 35 | `include`/`extends`/`import` allowed | `test_a_template_that_reads_another_file_is_refused_at_load[include]` |
| 36 | Re-exported schema path accepted | `test_an_output_schema_named_by_a_re_export_is_refused_naming_where_it_is_defined` |
| 37 | `BaseModel` itself accepted as a schema | `test_an_output_schema_that_is_not_a_pydantic_model_is_refused[the-base-class-itself]`, after the fix described below |
| 38 | `prompt()` does not check variables | `test_prompt_checks_the_variables_so_a_call_site_fails_even_where_nothing_renders` |
| 39 | Text before the system marker allowed | `test_a_body_whose_sections_are_malformed_is_refused_at_load[text-before-system]` |
| 40 | Duplicate YAML keys allowed | `test_a_front_matter_key_given_twice_is_refused` |
| 41 | `bedrock_router_factory` drops the renderer | `test_live_mode_sends_a_structured_call_with_the_text_the_registry_renders`, see below |
| 42 | Metadata drops the request id | `test_a_replayed_result_carries_metadata_from_the_recorded_route` |
| 43 | Metadata dated by the wall clock, not the call | `test_a_fake_router_result_carries_metadata_from_its_route_and_prompt` |

**Mutant 37 survived the first run, and the fault was in the test.** The case named the base class as `pydantic.BaseModel`, which is a re-export, so the re-export rule refused it before the base-class rule was reached. The base-class rule guards a real input, `pydantic.main.BaseModel`: the defining path, which passes the re-export rule. Accepted, it would validate every answer as an empty model. I changed the case to `pydantic.main.BaseModel` (commit `af51f6e`), and the mutant is now caught. Agreement 8 asks whether the check should be deleted instead. It should not, because without it that path loads.

**Mutant 41's summary was `1 failed, 1 error`, so the runner marked it invalid, and I inspected it.** The test fails in its body with `ConfigurationError: no prompt renderer is configured`. The error is the Stubber's teardown reporting its planned answer unconsumed, after the test had run. It counts as caught.

## Files changed

- **`debate_core.domain`**:
  - `prompt_spec.py`, new: the front matter and its rules.
  - `provenance.py`, new: `GeneratedArtifactMetadata`.
  - `model_contracts.py`: `RenderedPrompt` beside `ModelPrompt`, and `ModelResponse.metadata`.
  - `__init__.py`: exports.
- **`debate_core.integrations.models`**:
  - `prompt_registry.py` and `prompt_lock.py`, new.
  - `errors.py`: `PromptRegistryError`, `UnknownPromptError`, `PromptRenderError`, `PromptLockError`.
  - `_recorded_files.py`: t03's directory rule now imports the domain's id rule.
  - `factory.py`: docstring and the refusal message name `bedrock_router_factory`.
- **`debate_core.integrations.bedrock`** (t02's files, Deviation 1):
  - `prompt_rendering.py`: t02's `RenderedPrompt` removed; the module imports the domain's.
  - `__init__.py`: `bedrock_router_factory`.
  - `first_call.py`: an import.
  - `router.py`: a docstring.
- **`prompts/`**: `README.md` (the format) and `prompts.lock.json` (empty: `{"format": 1, "prompts": {}}`).
- **`scripts/lock_prompts.py`**: adds released versions to the lock, or `--check`s.
- **Tests**:
  - `tests/domain/test_prompt_spec.py`.
  - `tests/integrations/models/`: `conftest.py`, `test_prompt_registry.py`, `test_artifact_metadata.py`, `test_prompt_lock.py`; `test_factory.py`, one expected name.
  - `tests/integrations/bedrock/`: `test_prompt_registry_wiring.py`; `test_router.py`, an import.
  - `tests/scripts/test_lock_prompts.py`.
  - The fixture `tests/fixtures/prompts/example/select-passage.md`.
- **`packages/debate_core/pyproject.toml`, `uv.lock`**: `jinja2>=3.1` as a debate-core dependency. It was already locked at 3.1.6 through another package, so the lock gained two lines.
- **The spec**: phase set to `Succeeded`.

## Deviations from the spec

1. **`RenderedPrompt` moved from `integrations.bedrock` to `domain.model_contracts`, which touches t02's files.** The PM's notes asked for this.
   - The domain type is a frozen `DomainModel`, not a dataclass. Both turns are `NonEmptyText`, so surrounding whitespace is trimmed. The registry trims each turn anyway.
   - t02's 90 Bedrock tests (`test_router.py`, `test_aws_extra.py`) pass with only their import changed.
   - Its refusal message now names `bedrock_router_factory`. One t03 factory test asserted the old name of the router to pass in; its expected text changed with the name.
2. **Files outside `constraints.packages`** (`debate_core.domain`, `debate_core.integrations`, `prompts`):
   - `packages/debate_core/pyproject.toml` and `uv.lock`, for the Jinja2 dependency.
   - `scripts/lock_prompts.py`, which is a node output.
   - `tests/fixtures/prompts/` and `tests/scripts/test_lock_prompts.py`.
3. **The sample prompt is a test fixture, not a file under `prompts/`.**
   - The node says "a sample prompt used only by tests", and the registry loads everything under `prompts/` for production.
   - Its schema, `debate_core.testing.contracts.model_router.ContractPassage`, is a test schema. Its id, `example.select-passage`, already has a committed fixture and cassette, which the metadata tests reuse.
   - So the committed lock is empty, and the repository-level lock test passes trivially until t05 or t06 releases a prompt. It is shown biting on the real tree with a planted prompt (Acceptance criteria).
4. **No `model.repair` prompt.** The PM's notes said to add it "if the spec asks for it". This spec does not, and t05 lists `prompts/model/repair.md` among its own outputs. No production prompt was added.
5. **ac1 says "every `prompts/**/*.md` file". Files named `README.md` are skipped**, because the spec's own `prompts/README.md` sits there. Any other `.md` file without front matter is refused rather than skipped, so a stray note fails loudly.

## Decisions and assumptions

- **One file per version, and versions coexist.**
  - The registry keys on front matter and does not read file names. The README's convention is `<name>.md` for the first version and `<name>@<version>.md` for each later one, such as `card/select@1.1.0.md`.
  - A released version is never edited or deleted, so a version pinned in E09's `config/promoted.yaml` and its candidate can both be loaded.
  - The lock flags a deleted release (`missing`) and a release set back to draft (`unreleased`).
- **Versions are `MAJOR.MINOR.PATCH` only.** A pre-release or build suffix is refused rather than ordered, so `latest` has one answer, and a version that is not ready is a `draft`.
- **`latest` is the highest released version by number.** E09 t04 will make it read the promoted pins.
- **The lock pins more than the body.** ac4 names the body. The description's rule, "a released prompt version is immutable", also covers what the version answers and how it is routed, so the lock pins `output_schema` and `task_class` too. `owner` and `changelog` may be corrected.
- **Variables are exact.** Every variable the template names is required, even under `default(...)`, and one the template never uses is refused. A caller that needs "nothing here" passes `null`. This keeps the fixture key and the text in step.
- **`prompt()` renders once to check the variables.** Under the fake and replay routers nothing else ever renders, so without this a misspelt variable would pass every offline test.
- **`render` refuses `latest`.** The version is part of the fixture key and of the provenance.
- **Turns are marked with lines `<!-- system -->` and `<!-- user -->`.** With no marker, the body is the user turn.
- **What a template may do:**
  - It runs in Jinja2's sandbox, with no autoescape.
  - The `random` filter and the `lipsum` function are removed.
  - `include`, `extends` and `import` are refused when the file loads.
  - Line endings are read as `\n`, so a Windows checkout hashes the same.
- **An output schema must be named where it is defined.** `f"{cls.__module__}.{cls.__qualname__}"` is what `ModelRequest.build` puts in every fixture key, so a re-exported path is refused and the error names the defining one.
- **Error types:**
  - `PromptRegistryError` is a `ConfigurationError` carrying `field` (the front-matter key) and `source` (the file), so the CLI reports it with the configuration exit code.
  - `PromptRenderError` is a `DomainError`.
  - Both live in `integrations.models.errors`, beside t03's.
- **The metadata is a property, not a field:**
  - No router had to change, no recorded cassette changed, and no router can report metadata that disagrees with its own route.
  - It nests the `ResolvedRoute`, so every parameter sent, including t02's `effort`, is carried without a second list of fields.
  - `snapshot_ids` are ULIDs, the type of `SourceSnapshot.snapshot_id`. `retrieval_ids` are non-blank text.
  - `created_at` is the call's `invoked_at`.
  - It holds no prompt text, variables or output.
- **The factory's `RealRouterFactory` signature is unchanged.** `integrations.models` may not import the Bedrock package, so `bedrock_router_factory(registry)` lives there and binds `registry.render`. `bedrock_model_router` on its own still refuses structured calls before sending.
- **A YAML key given twice is refused.** The safe loader would otherwise keep the last value silently.
- **No prompt text in a production module.** t02's `first_call.py` keeps its one-line probe text. That is the operator's ac7 diagnostic, which the PM accepted in t02, and no production call path sends it.

## Operator follow-ups

None.

## Follow-up work

- **Installed builds need `prompts/` bundled** before the first model command runs from one. That task belongs to E06, or whichever task adds the first model command.
  - Today a composition root loads the registry from a checkout, as fixtures and cassettes are.
  - An installed wheel carries `config/` but not `prompts/`.
- **The first CLI command that calls a model** loads the registry and passes `real_router=bedrock_router_factory(registry)` to `build_model_router`.
- **A call's schema and task class are not checked against the prompt's.** `generate_structured(task_class, prompt, schema)` takes both from the caller. A check that `registry.get(...).schema is schema`, with the declared class, belongs in t05's guard or the router.
- **The first task that persists a generated artifact (t06)** stores `response.metadata.with_inputs(snapshot_ids=…, retrieval_ids=…)` with it. A domain base for generated artifacts with a required metadata field would make the "never persist without it" rule structural.
- **An import contract keeping `jinja2` out of the domain and application layers**, like the one for `lxml`. That is the import-boundary owner's file, the root `pyproject.toml`.
- **E09 t04:** `latest` reads `config/promoted.yaml`.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-18

**Notes:**

Accepted in full, with the phase `Succeeded`.

**This is what I asked for after t02.** The red run is real: the tests were written against a
committed skeleton that refused nothing, and they failed 138 times for their own reasons. The
wiring's red run restored t02's files and showed record and live refused, then fixed. Then 43
mutants, all caught. Mutant 37's first survival found a test naming the wrong path, and you fixed
the test rather than deleting the check, which was the right call.

**The design decisions that matter:**

* **A prompt version is immutable in what it answers and how it is routed, not only in its words.**
  The lock pins the schema and the task class beside the body hash, and it flags a release that is
  deleted or set back to draft.
* **Variables are exact, both ways, and `prompt()` checks them.** Under the fake and replay routers
  nothing else renders, so this is what keeps a misspelt variable from passing every offline test.
* **Rendering is deterministic down to mapping order,** in step with the fixture key, across
  interpreters and hash seeds.
* **Templates run sandboxed, with no file reads and no randomness,** checked when the file loads.
* **The metadata is a property of the response,** so no router can report provenance that
  disagrees with its own route, and no cassette changed.
* **`bedrock_router_factory(registry)`** completes t02's seam without letting `integrations.models`
  import the AWS package.

**Rulings:**

* **Deviation 1, `RenderedPrompt` moved into the domain:** done as the notes asked, with t02's 90
  tests passing on an import change.
* **Deviation 2, the files outside the packages:** accepted under working agreement 5. Jinja2 as a
  base dependency of debate-core is right, since the routing policy beside it is wired on every
  run. It must stay out of the domain and application layers: see below.
* **Deviation 3, the sample as a test fixture and an empty lock:** accepted. The lock test was shown
  biting on the real tree with a planted prompt.
* **Deviation 4, no `model.repair` prompt:** accepted. It is t05's output.
* **Deviation 5, `README.md` skipped:** accepted, and any other note without front matter is
  refused, which is the safe side.

**Follow-up work, filed by the PM:**

* **An import contract keeping `jinja2` out of the domain and application layers:** added to the
  next E05 loose-ends task.
* **The schema and task class a call names are checked against the prompt's:** added to t05, whose
  guard sits on every structured call.
* **`prompts/` bundled in installed builds,** and the composition root loading the registry: these
  go into the spec of the first CLI command that calls a model, with t09's exit-code rule.
* **t06 stores `response.metadata.with_inputs(...)` with each generated artifact,** as a required
  field. This is noted on t06's spec.
