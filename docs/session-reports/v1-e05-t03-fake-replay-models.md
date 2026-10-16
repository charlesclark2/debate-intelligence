# Session report: v1-e05-t03-fake-replay-models

| | |
|---|---|
| Task | `v1-e05-t03-fake-replay-models` — Deterministic fake and record/replay models |
| Spec | [`plan_specs/v1/e05-model-router/t03-fake-replay-models.yaml`](../../plan_specs/v1/e05-model-router/t03-fake-replay-models.yaml) |
| Epic / release | `v1-e05-model-router` / `v1.2` |
| Branch | `task/v1-e05-t03-fake-replay-models` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Two offline `ModelRouter`s now keep every test and eval away from a real model, and one control decides which one a run gets:

- **`FakeModelRouter`** answers `generate_structured` from hand-written files, `tests/fixtures/model_outputs/<prompt_id>/<key>.json`. It computes deterministic embeddings and rerank scores.
- **`RecordReplayModelRouter`** wraps a real router in one of three modes. Record writes scrubbed cassettes and is refused when `CI=true`. Replay, the default, serves cassettes. Live passes calls through.
- **One key.** Both routers file answers under the same key: SHA-256 over canonical JSON of the prompt id, version, variables and the schema's dotted path.
- **No defaults.** Neither router has a default answer. A missing answer raises `MissingFixtureError` naming the prompt and the key. Replay never holds the real router, so nothing can fall back to it.
- **Selection.** `models.provider = "fake"` selects the fake. With a real provider, `--model-mode`, else `DEBATE_MODEL_MODE`, else replay, picks the mode. No setting chooses the mode.
- **ac6.** The CLI validates the routing file when it loads its settings, so a bad file stops a command with `RoutingConfigError` naming the key. It was shown failing first.

All four plan nodes and all six Goal criteria pass, as amended by the PM on 2026-10-16. The Goal is `Succeeded`. 33 mutants and one combined mutant all end caught. Two survived on the first pass: one exposed a weak test, which is now fixed; the other was a redundancy, kept deliberately.

**What to look at first:**

1. **Deviation 4, how ac6 reads "before any command runs".** Plain `doctor`, `--help` and `--version` load no settings by documented design, so a bad routing file does not stop them.
2. **Deviation 5.** ac6 made 26 test profiles that named non-existent routing files fail. It also exposed that a checkout's code run from outside any checkout had no routing file at all. The smoke tier and the launchd installer test run it that way. One fallback in `settings.py` fixes the second problem.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `fixture-key` — Stable fixture key | Done | `integrations/models/fixture_key.py`. Golden digests hashed by hand with `shasum`; property tests for dict ordering and unicode, checked for what they generate. |
| `fake-router` — FakeModelRouter | Done | `integrations/models/fake_router.py`, plus `errors.py` and `_recorded_files.py`. The scripted e02 fake is renamed `ScriptedModelRouter` (PM ruling). |
| `record-replay` — RecordReplayModelRouter with redaction | Done | `record_replay.py`, `redaction.py`, and `model_mode.py` (the shared `resolve_model_mode` and `add_model_mode_option`). Tested around an in-test stand-in that passes the contract (PM ruling). |
| `settings-wiring` — Provider selection and pytest fixture | Done | `factory.py`, the `models.provider` setting, the `model_router` fixture in the workspace `conftest.py` (Deviation 3), and ac6's startup check in the CLI's composition root. |

## Acceptance criteria

All runs were on 2026-10-16 at `c69a11a` unless a row says otherwise. Load average was 5 to 30 throughout, from other sessions on the machine.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: `FakeModelRouter` and `RecordReplayModelRouter` both pass the shared contract suite | PASS | `uv run pytest packages/debate_core/tests/integrations/models -k "TestFakeModelRouter or TestRecordMode or TestLiveMode or TestReplayMode or TestStandInRealRouter"` → `90 passed` (18 contract tests × 5 bindings). The fake binding writes each planned answer as a fixture file; its planned vectors and scores go in through the `embedder`/`reranker` arguments (Decision 3). The replay binding writes cassettes. The record and live bindings wrap the stand-in and check routes field by field. |
| ac2 (as amended): the key is sha256(prompt_id, prompt_version, canonical JSON of inputs, schema name), where the schema name is `ModelRequest`'s dotted path, and is identical across runs, platforms and dict ordering, with property tests for ordering and unicode | PASS | `uv run pytest packages/debate_core/tests/integrations/models/test_fixture_key.py` → `21 passed`. Hand-hashed goldens: ASCII, unicode (U+00E9, U+2615, U+1D11E), embed, rerank. A fresh interpreter under `PYTHONHASHSEED` 0 and 4242 gets the golden. Two schemas named `Passage` in different modules get different keys. Properties, 200 examples each: insertion order never changes the key (70% of examples hold a mapping with 2+ keys, 37% nest one 2+ deep); a JSON round trip keeps the key; any text gets a well-formed key (90% non-ASCII, 60% astral-plane). |
| ac3: an unrecorded call in fake or replay mode raises `MissingFixtureError` naming the prompt_id and key | PASS | `test_a_missing_fixture_names_the_prompt_and_the_key` (fake). `test_an_unrecorded_call_names_the_prompt_and_key_and_never_reaches_the_real_router`: replay, with a real router handed in, whose call count stays 0. `test_an_unrecorded_embed_or_rerank_is_named_by_its_call[embed, rerank]`. A call that differs from its cassette only in task class or parameters is unrecorded too. |
| ac4: record mode writes one pretty-printed JSON cassette per call with authorization headers and account identifiers redacted, and refuses to run when CI=true | PASS | `test_record_writes_one_pretty_printed_cassette_per_call`: two identical calls, one file. `test_a_recorded_cassette_carries_no_account_id_key_or_signature`: the stand-in's application-profile ARN holds account `111122223333`, and its answer holds a SigV4 `Authorization` value with `AKIAIOSFODNN7EXAMPLE`; neither reaches the file, and the caller still gets the real answer. `test_authorization_headers_are_redacted_wherever_a_cassette_holds_them`. `test_record_mode_is_refused_when_ci_is_true[true, TRUE, 1, yes]` writes nothing. The factory refuses before it builds a real router. `test_no_committed_cassette_or_fixture_holds_anything_redaction_would_remove` reads every committed JSON file under both fixture directories. |
| ac5 (as amended): `models.provider=fake` selects the fixture-keyed fake; with a real provider, `DEBATE_MODEL_MODE` or `--model-mode` selects record, replay or live, with no code change | PASS | `uv run pytest packages/debate_core/tests/integrations/models -k factory` → `19 passed`. The test profile gives the fake; `DEBATE_MODELS__PROVIDER=fake` gives it in dev. Dev and prod replay by default. `DEBATE_MODEL_MODE=live` gives live; `--model-mode record` beats the variable. `models.provider = "replay"`, `"record"` or `"live"` is refused, and no settings key names a mode. The fake reads no mode. `add_model_mode_option` is tested with argparse in `test_record_replay.py`. |
| ac6 (new): the CLI loads and validates the routing file at startup (`RoutingPolicy.from_settings`), so a bad file fails before any command runs, with a typed `RoutingConfigError` naming the key. Shown failing first | PASS (see Deviation 4) | **Red first**, with the test written and no implementation: `uv run pytest packages/debate_cli/tests/test_routing_file_checked_at_startup.py` → `4 failed, 5 passed`. Each failure was `assert 0 == <ExitCode.DOMAIN_FAILURE: 1>`, because `config show` succeeded on a bad file. **Green**: `9 passed`. `routes.card_selection`, `routes.high_volume.model_id` and `routes.high_volume.temperature` each give `ROUTING_CONFIG_ERROR`, exit 1, with `details.field` naming the key and no `data`. A missing file names its path. Plain `doctor`, `--help`, `--version` and `config --help` still exit 0 (Deviation 4). Mutants 30 and 31 below fail the same tests against the final wiring. |
| Node `fixture-key`: `uv run pytest packages/debate_core/tests/integrations/models/test_fixture_key.py` | PASS | → `21 passed in 2.68s` |
| Node `fake-router`: `uv run pytest packages/debate_core/tests/integrations/models/test_fake_router.py` | PASS | → `42 passed in 1.78s` |
| Node `record-replay`: `uv run pytest packages/debate_core/tests/integrations/models/test_record_replay.py` | PASS | → `122 passed in 1.85s` |
| Node `settings-wiring`: `uv run pytest packages/debate_core/tests/integrations/models -k factory` | PASS | → `19 passed in 2.08s` |
| Node `settings-wiring`: `uv run pyright packages/debate_core` | PASS | → `0 errors, 0 warnings, 0 informations`. Workspace-wide `uv run pyright` → 0 errors. |

### Checks shown failing

The tree was committed before each batch. Each mutant was applied to one file, and its tests ran with `.venv/bin/python -m pytest -n0`. Each run had a new, empty `HYPOTHESIS_STORAGE_DIRECTORY` (working agreement 8). The file was then restored from a byte copy and compared, and `git status --porcelain` was empty after every batch. A mutant is classified from pytest's summary line, and a collection error would not have counted as a catch. Each run took 0.6 to 2.1 s.

| # | Mutant | Caught by | Result |
|---|---|---|---|
| 1 | Key: dict keys not sorted | `test_insertion_order_never_changes_the_key` (property) | CAUGHT |
| 2 | Key: schema name not hashed | `test_two_schemas_with_one_class_name_get_different_keys` | CAUGHT |
| 3 | Key: task class hashed too | `test_the_task_class_and_parameters_are_not_part_of_the_key` | CAUGHT |
| 4 | Key: text NFC-normalized | `test_text_is_not_normalized` | CAUGHT |
| 5 | Key: unicode escaped (`ensure_ascii=True`) | `test_unicode_is_hashed_as_utf_8_without_escapes` (hand-hashed golden) | CAUGHT |
| 6 | Key: NaN hashed | `test_a_number_json_cannot_carry_is_refused` ×3 | CAUGHT |
| 7 | Fake: missing fixture answers `{}` | `test_a_missing_fixture_names_the_prompt_and_the_key` (got `InvalidModelOutput`) | CAUGHT |
| 8 | Fake: misfiled fixture served | `test_a_fixture_filed_under_the_wrong_name_is_refused` | CAUGHT |
| 9 | Fake: output not validated (`model_construct`) | contract `test_an_answer_that_does_not_fit_the_schema_is_refused_naming_the_prompt` | CAUGHT |
| 10 | Fake: unsafe prompt id accepted | `test_a_prompt_id_that_cannot_name_a_directory_is_refused` ×4 | CAUGHT |
| 11 | Fake: embedding not scaled to unit length | `test_every_embedding_is_a_unit_vector_of_the_stated_length` | CAUGHT |
| 12 | Fake: words not case-folded | `test_rerank_scores_the_share_of_query_words_each_document_holds` | CAUGHT |
| 13 | Replay holds the real router | `test_an_unrecorded_call_..._never_reaches_the_real_router` | CAUGHT |
| 14 | Replay: recorded request not compared | `test_a_call_that_differs_from_its_cassette_only_outside_the_key_is_unrecorded` ×2 | CAUGHT |
| 15 | Replay keeps provider `bedrock` | `test_a_recorded_call_replays_without_the_real_router` | CAUGHT |
| 16 | Record: cassette not redacted | both redaction tests | CAUGHT |
| 17 | Redaction: account-id pattern dropped | `test_a_recorded_cassette_carries_no_account_id_key_or_signature` | CAUGHT |
| 18 | Redaction: secret keys not redacted | `test_authorization_headers_are_redacted_...` (the security token survived) | CAUGHT |
| 19 | Record: cassette written in live mode too | `test_live_mode_records_nothing` | CAUGHT |
| 20 | CI refusal removed | 4 router cases and the factory test | CAUGHT |
| 21 | CI recognised only as exact `true` | `test_record_mode_is_refused_when_ci_is_true[TRUE, 1, yes]` | CAUGHT |
| 22 | The variable wins over the option | both option-wins tests | CAUGHT |
| 23 | Default mode live | `test_the_mode_defaults_to_replay`, `test_dev_and_prod_replay_by_default` | CAUGHT |
| 24 | Empty `DEBATE_MODEL_MODE` read as unset | `test_an_unknown_mode_is_refused_...[env empty]` | CAUGHT |
| 25 | Factory reads the mode for the fake | `test_the_fake_does_not_read_the_mode_variable` | CAUGHT on the second pass (below) |
| 26 | Factory: routing file not loaded from settings | `test_a_bad_routing_file_fails_before_any_router_exists` | CAUGHT |
| 27 | Factory: replay builds the real router | `test_a_real_provider_replays_the_committed_cassettes_by_default` | CAUGHT |
| 28 | Factory: CI checked only inside the router, after the real router is built | `test_record_in_ci_is_refused_before_a_real_router_is_built` | CAUGHT |
| 29 | `test.toml` drops `provider = "fake"` | none | SURVIVED: the built-in test profile also sets it (below) |
| 29b | Both `test.toml` and the built-in test profile drop it | `test_the_test_profile_selects_the_fixture_keyed_fake` | CAUGHT |
| 30 | CLI: root callback's loader not wrapped | the 4 ac6 refusal tests | CAUGHT |
| 31 | CLI: the wrapper validates nothing | the 4 ac6 refusal tests | CAUGHT |
| 32 | Settings: no source-checkout anchor | `test_run_from_outside_any_checkout_the_routing_file_is_this_checkouts` | CAUGHT |
| 33 | A planted account id in the committed example cassette | `test_no_committed_cassette_or_fixture_holds_anything_redaction_would_remove` | CAUGHT |

**The two survivors.**

- **Mutant 25** survived because the test passed `mode="record"` as well as `DEBATE_MODEL_MODE=nonsense`. The option wins, so the bad variable was never parsed, and a factory that resolved the mode for the fake looked the same as one that did not. I split the test in `c69a11a`, and the rerun was caught with `ModelModeError: invalid model mode 'nonsense' from env:DEBATE_MODEL_MODE`.
- **Mutant 29** shows the test profile's `provider = "fake"` is redundant with the built-in test profile. I kept both: the profile file is where a reader looks, as its existing `[caselist]` comment says. Mutant 29b shows the pair is guarded.

### Test runs

The default selection was split into parts so each run stayed under two minutes (working agreement 1). Each ran under `perl -e 'alarm 110'`, at `8757d0b`, the last code commit before the test split. `c69a11a` changes only `test_factory.py`, rerun above.

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest -q packages/debate_core/tests --part 1/3`, `2/3`, `3/3` | 1750 passed, 1 xfailed (25.2 s); 1758 passed (24.1 s); 1760 passed, 1 xfailed (23.9 s) |
| `.venv/bin/python -m pytest -q packages/debate_cli/tests` | 648 passed (24.3 s) |
| `.venv/bin/python -m pytest -q packages/debate_api/tests packages/debate_workers/tests` | 4 passed (2.8 s) |
| `.venv/bin/python -m pytest -q tests --part 1/4` … `4/4` | 429 passed (50.0 s); 423 passed (30.4 s); 426 passed, 1 skipped (31.5 s); 432 passed (35.9 s) |

Also: `uv run ruff check .` and `uv run ruff format --check .` → clean. `uv run lint-imports` → `Contracts: 12 kept, 0 broken.` `uv run scripts/validate_specs.py` → `OK: 355 files, 38 epics, 297 tasks, 20 releases`, and `--require-succeeded v1-e05-t03-fake-replay-models` → `Succeeded`. `scripts/check_command_blocks.py` and `scripts/check_links.py` → OK.

## Files changed

- **Spec** (`plan_specs/v1/e05-model-router/t03-fake-replay-models.yaml`): the PM's 2026-10-16 rulings, quoted in Deviation 1, and the Goal phase.
- **New, `debate_core.integrations.models`:** `fixture_key.py`, `fake_router.py`, `record_replay.py`, `model_mode.py`, `redaction.py`, `factory.py`, `errors.py`, `_recorded_files.py`. Also `__init__.py`, which now exports them.
- **Fixtures:**
  - `tests/fixtures/model_cassettes/README.md`, which covers both directories, and one hand-written example cassette.
  - `tests/fixtures/model_outputs/README.md` and one hand-written example fixture. Both example files answer `example.select-passage@1.0.0`, with different answers so a test can tell which file served it.
  - `tests/fixtures/model_routing.py`.
- **The rename (PM ruling):** `FakeModelRouter` → `ScriptedModelRouter` in `debate_core.testing` (`fakes.py`, `__init__.py`), `tests/application/test_fakes.py`, `tests/contracts/test_model_router_contract.py`, `application/ports/model_router.py` (docstring) and `docs/architecture/ports-and-adapters.md`.
- **Settings** (`application/settings.py`, `config/profiles/test.toml`, `.env.example`): the `models.provider` field (`fake` | `bedrock`, default `bedrock`), `fake` for the test environment, and the source-checkout anchor (Deviation 5). Plus a new test in `tests/application/test_settings.py`.
- **CLI:**
  - `container.py` gains `validating_routing`, and `app.py` wraps its settings loader with it.
  - `tests/test_routing_file_checked_at_startup.py` is new.
  - The two hand-written lists of wired integrations gain `models.routing_policy`, and their counts go from 9 to 10 (`tests/commands/test_doctor.py`, `tests/test_installation.py`).
- **Test profiles naming a non-existent routing file** now name the committed example file, `EXAMPLE_ROUTING_FILE`: 15 files in `packages/debate_cli/tests/`, 10 in `tests/smoke/`, and `tests/integration/test_launchd_install.py`.
- **Workspace `conftest.py`:** the shared `model_router` fixture.
- **Docs:** `packages/debate_core/README.md`, the `integrations/models/` section.

## Deviations from the spec

1. **The PM's rulings of 2026-10-16, written into the spec** (commit `080b755`). Each carries "Amended by the PM, 2026-10-16":
   - **ac5:** "models.provider=fake selects the fixture-keyed fake; with a real provider, DEBATE_MODEL_MODE or --model-mode selects record, replay or live, with no code change."
   - **ac6, new:** "The CLI loads and validates the routing file at startup (RoutingPolicy.from_settings), so a bad file fails before any command runs, with a typed RoutingConfigError naming the key. Shown failing first."
   - **ac2** gains: "The schema name is the dotted path that v1-e05-t01's ModelRequest carries, so two schemas with one class name never share a key; property tests cover dict ordering and unicode."
   - **The Goal description** gains the `ScriptedModelRouter` rename, and testing around an in-test stand-in because t02 is not built.
   - **Forbidden:** "Credentials, request signatures or student names inside cassette files" became "Credentials, request signatures, student names or real card text in any cassette or fixture". A new entry, "Network or AWS access in any test", is added.
   - **The settings-wiring node** now reads "(fake | bedrock; amended by the PM, 2026-10-16: settings never choose replay, the mode does)".

2. **Edits outside `constraints.packages`** (`debate_core.integrations`, `tests/fixtures/model_cassettes`), as the PM asked to have recorded:
   - `tests/fixtures/model_outputs/`: the fake-router node names this path.
   - `debate_core.testing`, its tests and the docs that name the scripted fake: the rename ruling.
   - `debate_core.application.settings`, `config/profiles/test.toml` and `.env.example`: the `models.provider` setting the settings-wiring node keys on, and Deviation 5.
   - `debate_cli` (`app.py`, `container.py`, three tests) and the 26 test profiles: ac6, which is about the CLI.
   - The workspace `conftest.py`: see 3.
   - `packages/debate_core/README.md`.

3. **The shared `model_router` fixture is in the workspace `conftest.py`, not `tests/conftest.py`.** The settings-wiring node names `tests/conftest.py`, but a conftest there applies only to tests under `tests/`, and the node asks for a fixture "so every package's tests are offline". The repository-root `conftest.py` is the one every package's tests see. `tests/conftest.py` does not exist and was not created. If the PM agrees, the node's `outputs` entry should read `conftest.py`.

4. **How ac6 reads "before any command runs".** The routing file is loaded and validated together with the run's settings, the first time a command asks for them. Every command that reads settings is stopped before it does anything; `config show` with a bad file prints no data.
   - Plain `doctor`, `--help` and `--version` read no settings, so a bad routing file does not stop them, and a test pins that.
   - This is deliberate. `commands/doctor.py` says plain `doctor` "loads no settings, reads no AWS config and reaches no network, and it has to stay that way", because `scripts/install_channel.sh` and `validate-dev` run it on every install, on machines with no AWS config.
   - Loading settings eagerly in the root callback would break that, and would also make `debate-research <command> --help` read profile files.
   - If the PM wants plain `doctor` to report a bad routing file as one of its checks, that is a small follow-up (see Follow-up work), not a reason to load settings before every command.

5. **ac6 made existing tests and one real gap visible.**
   - 26 test files wrote profiles naming `tmp_path / "routing.yaml"`, which never existed. With the startup check, 154 CLI tests failed and 54 errored. They now name `tests/fixtures/model_routing.EXAMPLE_ROUTING_FILE`, the committed example file.
   - The gap: the smoke tier and the launchd installer test run this checkout's code from a scratch directory, where only the built-in profile applies. There, the relative `config/model_routing.dev.yaml` was resolved against the scratch directory and named nothing; any model command would already have failed there.
   - The fix: `load_settings` now anchors a relative routing file to the checkout `debate_core` was imported from, when there is no bundled configuration and no checkout around the working directory. That is what the settings module's own rule says it should mean ("must not depend on the working directory", `test_a_relative_routing_file_is_anchored_to_the_repository`).
   - Only the routing file is anchored. Where profiles are read from is unchanged, and an installed build still reads its bundled configuration.
   - `test_run_from_outside_any_checkout_the_routing_file_is_this_checkouts` fails without the fallback (mutant 32), and the 11 smoke and launchd tests that failed now pass.

## Decisions and assumptions

1. **The key covers exactly ac2's four parts.**
   - It hashes the canonical JSON of `{"inputs", "prompt_id", "prompt_version", "schema"}`: keys sorted at every depth, no whitespace, UTF-8, no escaping.
   - NaN, infinity and lone surrogates are refused rather than hashed, because none of them can reach a model or a UTF-8 cassette, and `ModelPrompt` accepts all three.
   - Text is not normalized. NFC and NFD are different inputs to a model.
   - `1` and `1.0` are different keys.
   - The task class and parameters are not hashed. Replay compares them separately, against the full recorded request.
2. **A fixture file names the request it answers.** It holds the prompt id, version, variables and schema beside `output`. The fake recomputes the key from those fields and refuses a file whose name does not match, which catches a fixture copied to the wrong name or left behind by a version bump. `FixtureDirectory.write` writes one correctly.
3. **Embeddings and rerank are computed.**
   - Embeddings use 64 signed feature-hashed dimensions per case-folded word, scaled to unit length. Texts that share words point the same way, which a search test can use, and a text with no words is hashed whole.
   - Rerank scores each document by the share of the query's distinct words it contains, with ties kept in input order.
   - Because computed values cannot match arbitrary planned ones, the contract binding hands the planned vectors and scores in through the `embedder` and `reranker` arguments. The fake's own code still does the validation, routing, ordering and refusals.
4. **`MissingFixtureError` is not a `ProviderError`.** A provider error may be absorbed as a partial result or retried, and the CLI treats `PROVIDER_UNAVAILABLE` as retryable. A missing recording must stop the run. The error is a `DomainError`, with code `MISSING_FIXTURE_ERROR`.
5. **A replayed response is the recorded one, marked as offline.** Its provider is `fake`, with no region and no inference profile. The recorded model id, usage, request id and `invoked_at` are kept, so a golden run is byte-identical and still says whose answer it replays.
6. **Cassettes.**
   - Each holds `call`, `cassette_format: 1`, `key`, the whole request and the whole response, pretty-printed with sorted keys and a trailing newline, and written atomically.
   - Embed and rerank calls go in `_embed/` and `_rerank/`. A prompt id must be a safe directory name (letters, digits, `.`, `_`, `-`, starting alphanumeric), so it cannot collide with those two.
7. **What redaction scrubs, and what it cannot catch.**
   - By key, at any depth: authorization, cookie, API key, AWS key and token, SigV4 parameter, and account id keys.
   - By pattern, in every string: SigV4 values, `Signature=`/`Credential=`/`Security-Token=` values, bearer tokens, `AKIA`/`ASIA` key ids, and twelve-digit numbers with no letter or digit beside them. That last rule leaves a run of digits inside a fixture key's hex alone.
   - Numbers are redacted only under a key.
   - It cannot recognise a name or a card's text, which is why every fixture is invented. The guard test fails CI on a committed file holding anything the scrubber would remove.
8. **The mode control.**
   - `CI` counts as true for `true`, `1` or `yes`, in any case.
   - A `DEBATE_MODEL_MODE` set to the empty string is an error, not "unset".
   - The mode is read from the process environment only. Settings ignore `DEBATE_MODEL_MODE` in `.env` (I checked: it loads and is dropped), so `.env.example` says to set it in the shell.
   - Provider `fake` reads no mode at all, so a developer's `DEBATE_MODEL_MODE` cannot break the offline suite.
9. **Record and live without a real router** fail with a `ConfigurationError` on `models.provider` that names `v1-e05-t02-bedrock-adapter`. There is no default real router, because nothing may fall back to a real model.
10. **Rename, not fold.** `ScriptedModelRouter` answers from a queue, for unit tests that need a model to say one thing. Folding it into the fixture-keyed fake would make those tests write files. `build_fake_ports` keeps the scripted one.
11. **The stand-in.** `StandInRealRouter`, in `test_record_replay.py`, is held to the contract in its own binding. It reports an application-inference-profile ARN with an account id in it, so redaction is exercised by a real-shaped route. Every identifier is invented; `111122223333` and `AKIAIOSFODNN7EXAMPLE` are AWS's documentation placeholders.
12. **Where the CLI check lives.** I first put it in `debate_cli.build_info`, and `lint-imports` broke: "Delivery packages reach debate_core.integrations only through their composition root". It now lives in `debate_cli.container.validating_routing`, which the root callback wraps around its loader. Tests that build a container around their own settings are unaffected. The post-install check now also imports `debate_core.integrations.models.routing_policy`.
13. **`invoked_at` defaults to `FIXTURE_EPOCH`** (2026-01-01 UTC) when the fake is given no clock. The layers contract forbids `integrations` to import `debate_core.testing`, so it cannot use `FAKE_EPOCH`. The shared fixture passes a `FixedClock`.

## Operator follow-ups

None. Every command ran in under two minutes, and the default selection ran in parts (working agreement 1). Nothing used credentials, the network or AWS, and nothing was recorded: there is no real router to record against until t02.

## Follow-up work

- **v1-e05-t02-bedrock-adapter:** pass its constructor to `build_model_router` as the `real_router` factory, which makes record and live work. The first recording run needs credentials, so it is an operator hand-off. Committed cassettes should come from invented inputs only (`tests/fixtures/model_cassettes/README.md`).
- **The first `debate-research` command that calls a model** (E06 or later): give the root callback `--model-mode` and pass it to `build_model_router`. The option and resolution are `debate_core.integrations.models.model_mode`. The CLI has no model command yet, so no CLI option was added here. Eval runners use `add_model_mode_option`.
- **v1-e05-t04-prompt-registry:** prompt ids name fixture directories, so the registry should refuse an id that is not letters, digits, `.`, `_` and `-` starting alphanumeric. Today `FixtureDirectory` and `CassetteDirectory` refuse one at call time.
- **v1-e05-t05-structured-output-validation:** a repair retry is a second call with its own prompt id or version. Under replay it needs a cassette of its own, or the repair path will raise `MissingFixtureError`. That is correct, but worth knowing when the first repair cassette is recorded.
- **The PM's call (Deviation 4):** should plain `doctor` report an invalid routing file as one of its checks? It would need settings, which plain `doctor` must not load, so it would be an option like `--evidence-profiles`.
- **The PM's call (Deviation 3):** the settings-wiring node's output `tests/conftest.py` could read `conftest.py`.
- **Seen, not caused here:** `packages/debate_cli/tests/test_app.py::test_doctor_renders_a_table` warns "A test tried to use socket.socket" (pytest-socket). Plain `doctor` tries to open a socket somewhere and is blocked. It predates this task; I did not look further.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-16

**Notes:**

Accepted in full, with the phase `Succeeded`. The three rulings the session asked for:

1. **Deviation 4, ac6's scope: accepted as built.** Plain `doctor`, `--help` and `--version` load
   no settings by `doctor.py`'s documented contract, and `install_channel.sh` and `validate-dev`
   depend on that. Every command that reads settings is stopped before it does anything, which is
   what ac6 is for. An opt-in check that makes `doctor` report a bad routing file, like
   `--evidence-profiles`, is PM follow-up work, filed in the next batch.
2. **Deviation 5, the source-checkout anchor in `settings.py`: accepted** under working agreement
   5, as an edit outside the task's packages, recorded here. It only gives a relative routing file
   the meaning the settings module already promised ("must not depend on the working directory").
   The order is unchanged: bundled configuration first, then the checkout around the working
   directory, then the checkout `debate_core` was imported from. The installed smoke test of dev
   and prod's routing files still asserts that the bundled configuration is the one read, and
   mutant 32 shows the fallback is held.
3. **Deviation 3, where the shared fixture lives: accepted.** The PM amended the settings-wiring
   node's `outputs` entry from `tests/conftest.py` to `conftest.py` in this review. The fixture is
   opt-in, not autouse, so no existing test changes behaviour.

**ac6 now couples every settings-reading command to the routing file, including the weekly sync,
which never calls a model.** That is the intent of the 2026-10-16 ruling: a broken configuration
fails at the start of a run, not halfway through one. The installed smoke test runs `config show`
under dev and prod against the routing files the wheel ships, so a build whose own files are bad
cannot pass validate-dev. The operator's next agent reinstall adds one check: dev's `config show`
exits 0 with the installed build.

**The work itself:**

* **The key is exactly ac2's four parts,** with hand-hashed goldens, fresh interpreters under two
  hash seeds, and property tests that were checked for what they generate. Refusing NaN, infinity
  and lone surrogates rather than hashing them is right.
* **Nothing falls back to a real model.** Replay never holds the real router, `MissingFixtureError`
  is a `DomainError` so it is never retried as a provider failure, and record and live without
  t02 fail on configuration.
* **Redaction is shown on a real-shaped route,** with AWS's documentation placeholders, and a guard
  fails CI on any committed fixture holding what the scrubber removes.
* **33 mutants and a combined one, all caught,** with the survivor that exposed a weak factory test
  fixed by splitting the test.
* **ac6 was shown failing first,** and the 26 test profiles that named a routing file that never
  existed now name the committed example.

**Follow-up work the PM files in the next batch:**

* `doctor --routing` (or a name the task chooses), opt-in, reporting a bad routing file (E05).
* Plain `doctor` tries to open a socket in `test_doctor_renders_a_table`, against its "reaches no
  network" contract. Find and remove the attempt (E01).
* t02, t04, t05 and the first model command take the session's notes under Follow-up work into
  their specs.
