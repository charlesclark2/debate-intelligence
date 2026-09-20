# Session report: v1-e02-t05-settings-config

| | |
|---|---|
| Task | `v1-e02-t05-settings-config` — Settings and configuration |
| Spec | [`plan_specs/v1/e02-domain-core/t05-settings-config.yaml`](../../plan_specs/v1/e02-domain-core/t05-settings-config.yaml) |
| Epic / release | `v1-e02-domain-core` / `v1.0` |
| Branch | `task/v1-e02-t05-settings-config` |
| Session status | COMPLETE |

## Summary

Configuration is now loaded in one place, `debate_core.application.settings`, and nowhere else in
the platform reads `os.environ` or a `.env` file. `load_settings()` merges six layers per field —
an explicit override, `DEBATE_*` environment variables, `.env`, `config/profiles/<env>.toml`, a
built-in per-environment profile, then the field's declared default — and remembers which layer
supplied each value, so `debate-research config show` can print the value *and* where it came
from, with every `SecretStr` replaced by `***`. `DEBATE_ENV` selects the profile and accepts only
`dev`, `prod` and `test`; an unset `DEBATE_ENV` in a source checkout resolves to `dev`, and `test`
is offline (`allow_network = false`, no providers enabled, a zero model budget, a data directory
under the system temp directory). A second module, `routing_config`, validates the task-class →
model YAML that E05 will route on.

Two things the PM should look at first. **The routing file is keyed on the real `ModelTaskClass`
enum** (`complex_reasoning`, `high_volume`, `deep_audit`, `embeddings`, `rerank`), not on the
`card_selection` / `citation_cleanup` / `relevance_classification` names in this task's plan-node
description — those names are not task classes and contradict both `v1-e02-t02-ports`, which
already shipped the enum, and `v1-e05-t01-model-router-port`, which names the same five. See
Deviations. **And `ConfigurationError` derives from `DomainError`**, which is how a typo in
`DEBATE_ENV` becomes a rendered failure and exit code `1` from the existing `debate_cli.exit_codes`
mapping instead of an unhandled exception and exit `70` ("this is a bug in debate-research").
No new exit code was introduced.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `settings-model` — Settings model and profiles | Done | `settings.py` with `storage`/`http`/`providers`/`models` groups, `DEBATE_` prefix and `__` nesting, the six-layer loader with per-field source tracking, and `config/profiles/{dev,prod,test}.toml` + `.env.example`. |
| `routing-config` — Model-routing config schema | Done | `routing_config.py` (`RoutingConfig`, `ModelRoute`, `load_routing_config`, `RoutingConfigError`) and `config/model_routing.example.yaml` routing all five task classes. |
| `config-command` — `config show` with redaction | Done | `debate_cli/commands/config.py`, registered as the `config` group; renders a Rich table or the `--json` envelope. Redaction happens in `debate_core` (`Settings.redacted_dict`), so the CLI cannot opt out of it. |
| `quality-gates` — Type checks | Done | `pyright` clean on both packages in strict (`debate_core`) and standard (`debate_cli`) mode. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — precedence CLI > env > `.env` > profile; invalid values fail fast naming the field | PASS | `uv run pytest packages/debate_core/tests/application/test_settings.py` → `51 passed`. The whole chain is asserted in one test (`test_the_whole_precedence_chain_holds_at_once`), each adjacent pair in its own test, and per-field merging in `test_layers_merge_per_field_rather_than_per_group`. Fail-fast: `test_an_out_of_range_value_names_the_field_and_where_it_came_from` (`error.field == "http.max_retries"`, `error.source == "env:DEBATE_HTTP__MAX_RETRIES"`), plus misspelled profile keys, unknown provider names, a non-URL contact URL and invalid TOML. |
| **ac2** — routing file validated (task class, `model_id`, `max_tokens`, `temperature`); unknown task class rejected | PASS | `uv run pytest packages/debate_core/tests/application/test_routing_config.py` → `26 passed`. `test_an_unknown_task_class_is_rejected_by_name` asserts the message names `card_selection` *and* lists the allowed classes, and that `error.field == "routes.card_selection"`. Also covered: missing/empty `model_id`, temperature outside 0.0–2.0, non-positive `max_tokens`, unknown fields at both levels, empty/non-mapping/invalid-YAML documents, and that `yaml.safe_load` refuses a `!!python/object/apply` tag. |
| **ac3** — `config show --json` emits all settings, `SecretStr` as `"***"`, per-field source | PASS | `uv run debate-research --json config show` → exit `0`, one envelope on stdout with `data.settings` (15 dotted keys), `data.sources` (the same keys) and `data.environment`. `uv run pytest packages/debate_cli/tests/test_config_command.py` → `22 passed`, including `test_secrets_are_starred_in_the_json_payload` and `test_no_secret_reaches_either_stream_in_any_mode`, which asserts three distinctive secrets appear in **neither stdout nor stderr** across all four combinations of `--json`/`--verbose`. |
| **ac4** — `DEBATE_ENV` accepts only dev/prod/test; unset → dev; dev ≠ prod data dirs; test profile offline, fakes only, temp data dir | PASS | Same settings suite. `test_the_three_environments_are_accepted`; `test_any_other_environment_fails_fast_naming_what_is_allowed` (5 rejected values, message contains `dev, prod, test`); `test_an_unset_debate_env_in_a_source_checkout_resolves_to_dev`; `test_dev_and_prod_resolve_to_different_data_dirs` and `test_the_committed_profiles_give_dev_and_prod_different_everything` (different `data_dir`, routing file and budget, dev budget < prod); `test_the_test_environment_is_offline_and_writes_to_a_temporary_directory` and `test_the_committed_test_profile_is_offline` (`allow_network False`, `providers.enabled == ()`, `budget_usd_daily == 0.0`, `data_dir == <system temp>/debate-research-test`). |
| Node `settings-model` — Settings precedence and validation tests pass | PASS | `uv run pytest packages/debate_core/tests/application/test_settings.py` → `51 passed in 1.72s` |
| Node `routing-config` — Routing config validation tests pass | PASS | `uv run pytest packages/debate_core/tests/application/test_routing_config.py` → `26 passed in 1.83s` |
| Node `config-command` — Redaction tests pass | PASS | `uv run pytest packages/debate_cli/tests/test_config_command.py` → `22 passed in 2.25s` |
| Node `config-command` — `config show` runs | PASS | `uv run debate-research --json config show` → exit `0` |
| Node `quality-gates` — pyright passes on `debate_core` | PASS | `uv run pyright packages/debate_core` → `0 errors, 0 warnings, 0 informations` |
| Node `quality-gates` — pyright passes on `debate_cli` | PASS | `uv run pyright packages/debate_cli` → `0 errors, 0 warnings, 0 informations` |
| Whole suite still green | PASS | `uv run pytest` → `433 passed in 9.14s`, coverage 98% overall (`settings.py` 93%, `routing_config.py` 97%) |
| Lint and format | PASS | `uv run ruff check` and `uv run ruff format --check` → clean |
| Spec validation | PASS | `uv run scripts/validate_specs.py` → `OK: 278 files, 38 epics, 220 tasks, 20 releases` |
| Pre-commit hooks | PASS, with one pre-existing environment failure | `uv run pre-commit run --all-files` → every Python hook and all Terraform checks pass; `site-checks` fails with `site/node_modules is missing. Run: pnpm --dir site install`. Nothing under `site/` was touched by this task; see Operator follow-ups. |

## Files changed

**`packages/debate_core/src/debate_core/application/` (new)**
* `settings.py` — `Settings` and its four nested groups, `Environment`, `SearchProviderName`,
  `ConfigurationError`, `load_settings()` and the layer/source machinery. The module docstring is
  the reference for the precedence table and the source labels.
* `routing_config.py` — `RoutingConfig`, `ModelRoute`, `load_routing_config()`,
  `RoutingConfigError`; keyed on `ModelTaskClass` from `ports/providers.py`.

**`config/` (new, committed)**
* `profiles/dev.toml`, `profiles/prod.toml` — starter profiles; `v1-e01-t09` replaces the channel
  values. `profiles/test.toml` — final, and the file that makes the test environment offline.
* `model_routing.example.yaml` — all five task classes, with Bedrock model ids as examples.

**`.env.example` (new)** — the documented, uncommitted place for every secret, with each variable
commented out so copying it configures nothing by accident.

**`packages/debate_cli/`**
* `commands/config.py` (new) — the `config show` command; renders, and does nothing else.
* `commands/__init__.py` — registers the `config` group.
* `app.py` — `root_callback` now passes `load_settings` to the `ServiceContainer` (one line plus a
  comment). This is the seam `v1-e01-t07-cli-skeleton` documented for this task.
* `container.py` — `Settings` is now the real type rather than the `Any` placeholder t07 left;
  `SettingsNotConfigured`'s message no longer points at this task as unfinished.

**Tests** — `test_settings.py` (51), `test_routing_config.py` (26),
`test_config_command.py` (22) are new. `packages/debate_cli/tests/test_app.py` has two assertions
updated, because this task is what changes the behaviour they described (see Deviations).

**Build** — `packages/debate_core/pyproject.toml` adds `pydantic-settings>=2.6` and `pyyaml>=6.0`;
the root `pyproject.toml` adds `types-pyyaml` to the dev group (PyYAML ships no inline types and
`debate_core` is type-checked strictly). `uv.lock` regenerated with `uv sync --all-packages`.
Neither new dependency reaches the network or a cloud SDK, so the domain-core dependency rule
still holds.

**`README.md`** — a short "Configuration" section and `config/` in the repository layout.

## Deviations from the spec

1. **The routing file is keyed on `ModelTaskClass`, not on the three names in the plan node.**
   The `routing-config` node describes "an example file mapping task classes (`card_selection`,
   `citation_cleanup`, `relevance_classification`) to model ids". Those are not task classes.
   `v1-e02-t02-ports` already shipped `ModelTaskClass` with exactly five members
   (`complex_reasoning`, `high_volume`, `deep_audit`, `embeddings`, `rerank`), documented as
   "what kind of work a model call is, which is what routing is decided on", and
   `v1-e05-t01-model-router-port` ac1/ac2 names the same five and requires `config/model_routing.yaml`
   to map each of them. The three names in this node read like concrete *uses* — cutting a card is
   `complex_reasoning`; citation cleanup and relevance classification are both `high_volume` — which
   is how the example file annotates them. Validating against anything but the shipped enum would
   have produced a file E05 could not load. **Suggested spec amendment:** replace the parenthetical
   in the `routing-config` node description with "(`complex_reasoning`, `high_volume`,
   `deep_audit`, `embeddings`, `rerank`)".

2. **The `test` profile's `data_dir` comes from the built-in profile, not from
   `config/profiles/test.toml`.** ac4 requires the test profile to point `data_dir` at a temp
   directory, and the spec says the test profile's values are final here. A committed TOML file
   cannot name the machine's temporary directory, so `test.toml` deliberately omits `data_dir` (with
   a comment saying why) and `BUILTIN_PROFILES[Environment.TEST]` resolves it to
   `<system temp dir>/debate-research-test`. Every other final test value — `allow_network = false`,
   `providers.enabled = []`, `budget_usd_daily = 0.0` — is in the file. The observable behaviour ac4
   asks for holds either way; only the layer it comes from differs.

3. **Files changed outside the spec's stated packages.** `constraints.packages` lists
   `debate_core.application.settings` and `debate_cli.commands.config`. Also changed, all
   unavoidable for the command to exist and run: `debate_cli/commands/__init__.py` (command
   registration), `debate_cli/app.py` (one line wiring the loader into the container — the seam
   `container.py`'s own docstring reserved for this task), `debate_cli/container.py` (the `Settings`
   placeholder t07 left for it), `packages/debate_core/.../routing_config.py` (a named plan-node
   output), the two `pyproject.toml` files and `uv.lock` (the new dependencies), `README.md`, and
   two assertions in `packages/debate_cli/tests/test_app.py` that asserted settings were *not*
   configured — which is precisely what this task changes.

4. **`DEBATE_PROFILE_DIR` is new and not in the spec.** It names the profile directory when the
   default (walk up from the working directory looking for `config/profiles`) cannot find one: an
   installed build, and the tests, which must not read the repository's real profiles. It carries no
   settings values of its own.

No other scope was added or dropped.

## Decisions and assumptions

* **Six layers, not four.** The spec names four (CLI > env > `.env` > profile). Two more sit below
  them: a **built-in profile** per environment and the field's **declared default**. The built-in
  profile is why `dev`, `prod` and `test` still differ in data directory, routing file, budget and
  network access on a machine with no `config/profiles/` at all — which is every installed build
  until `v1-e01-t09` ships the files with the wheel. It is reported honestly as `built-in:dev`
  rather than being disguised as a profile file.
* **Source tracking is done in the loader, not by pydantic-settings.** `settings_customise_sources`
  returns only `init_settings`; `load_settings` runs the environment, `.env` and profile sources
  itself, merges them per field, and records the first (highest) layer to supply each dotted path.
  This is what makes the `Source` column possible, and it also means a `Settings` built directly in
  a test cannot be polluted by a stray `DEBATE_*` variable in the developer's shell.
* **`ConfigurationError` derives from `DomainError`.** Exit codes come from `debate_cli.exit_codes`
  and no new number was added: the existing `exit_code_for` maps `DomainError` to
  `DOMAIN_FAILURE` (1), which gives a bad `DEBATE_ENV` a rendered failure panel and a deterministic
  exit code, instead of the exit `70` plus "this is a bug in debate-research" hint that an unhandled
  exception would get. `RoutingConfigError` subclasses it, so a caller that handles bad
  configuration handles a bad routing file without knowing routing exists.
* **Redaction lives in `debate_core`.** `Settings.redacted_dict()` is the only supported way to
  render settings, and it always redacts; the CLI has no un-redacted path to reach for. The
  polite-pool `contact_email` is a `SecretStr` too — it is not a secret, but it is a real person's
  email address (§14 data minimization), and `config show` should not print it.
* **Bucket, KMS key, region and SSO profile are deliberately absent.** `v1-e29-t05-evidence-sync-cli`
  adds them to `StorageSettings` and the same profile files, from the Terraform outputs
  `evidence_bucket_name` and `evidence_kms_key_arn`. Inventing constants for them here would have
  created a third copy to keep in step. The settings module says so in its docstring, and the two
  starter profiles each carry the note.
* **`SearchProviderName` is a closed enum** (`openalex`, `crossref`, `semantic_scholar`, `rss`,
  `gdelt` — the providers E07's epic names), so a typo in `DEBATE_PROVIDERS__ENABLED` fails at
  startup. `v1-e07-t01-search-provider-contract` owns the registry and adds to the enum in the same
  change when it adds an adapter.
* **A typo'd `DEBATE_*` variable that matches no field is ignored, not rejected.** Later tasks add
  `DEBATE_MODEL_MODE` (`v1-e05-t03`) and `DEBATE_REMOVAL_PROFILE` (`v1-e30-t07`), which are not
  settings fields; rejecting unknown `DEBATE_*` names would break them.
* **A relative `models.routing_file` is anchored to the repository root**, not to the working
  directory, so `config/model_routing.dev.yaml` in a committed profile keeps meaning the same file
  whichever directory the command was run from.
* **No smoke checks were added.** `tests/smoke/` does not exist yet and belongs to
  `v1-e01-t10-validate-dev-gate`, whose spec already lists "`config show` redaction and env
  selection" in its recorded tier. This task's plan graph has no smoke node, consistent with that.

## Operator follow-ups

The new dependencies mean an existing checkout needs a sync before `debate-research` will run:

**Operator command** (expected runtime ~20 s)
Where: your Mac, in the task worktree `debate-intelligence-worktrees/v1-e02-t05-settings-config`
```bash
uv sync --all-packages
uv run debate-research config show
DEBATE_ENV=prod uv run debate-research --json config show | jq '.data.settings["storage.data_dir"]'
```
Success looks like: the first prints a three-column table headed
`debate-research configuration (dev)` with `storage.data_dir` at `~/.debate-research/dev`; the
third prints `~/.debate-research/prod` expanded. Nothing in either output should resemble a
credential.

The repository's pre-commit `site-checks` hook fails on this machine because `site/node_modules`
is not installed. It is unrelated to this task — nothing under `site/` changed — but it will keep
failing `uv run pre-commit run --all-files` until it is fixed:

**Operator command** (expected runtime ~1 min, downloads packages)
Where: your Mac, in any checkout of the repository
```bash
pnpm --dir site install
```
Success looks like: `pnpm` finishes without error and
`uv run pre-commit run --all-files` then reports `site lint, typecheck, test and build...Passed`.

## Follow-up work

* **`v1-e01-t09-dev-prerelease-channel`** — owns what is still placeholder here: the real
  `config/model_routing.dev.yaml` and `config/model_routing.prod.yaml` (neither file exists yet, so
  `models.routing_file` currently names a file that is not there; nothing reads it until E05), the
  documented dev daily budget, and the build-channel default for installed builds. It also needs to
  ship `config/` alongside the wheel, or set `DEBATE_PROFILE_DIR`, so an installed build finds the
  profiles rather than falling back to the built-ins.
* **`v1-e05-t01-model-router-port`** — extends `ModelRoute` with provider, region/inference profile
  and timeout, and adds per-call overrides. `RoutingConfig` was written to be extended rather than
  replaced.
* **`v1-e29-t05-evidence-sync-cli`** — adds the S3 bucket, region and SSO profile per environment to
  `StorageSettings` and the profile files.
* **`v1-e02-t03-local-repositories`** — derives the layout inside `data_dir`. `StorageSettings`
  deliberately configures only the root, so one environment is one directory.
* **Injecting a fake service into a CLI command is not yet possible.** `root_callback` always builds
  a fresh `ServiceContainer`, so `CliRunner(..., obj=...)` is overwritten and a test cannot hand a
  command a prepared container — contrary to what `container.py`'s docstring describes. This did not
  block anything here (these tests drive the loader through the environment, which is the more
  realistic path), but the first command with a real service behind it will need the callback to
  accept an injected container. Belongs to whichever task lands that command, or to a small
  follow-up on `v1-e01-t07-cli-skeleton`.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED

**Reviewed by / date:** PM (Claude, project chat), 2026-09-20

**Notes:**

- Checked against the spec: precedence and fail-fast naming the field (ac1), routing schema with
  unknown task classes rejected (ac2), `config show --json` with redaction and per-field sources
  (ac3), and the DEBATE_ENV rules including the unset-to-dev default and the offline test profile
  (ac4). `settings.py` is the only module reading os.environ, which is what the forbidden list asks
  for, and recording the source per field is more than the spec required and worth having.
- **The deviation is right and the spec is wrong.** `card_selection`, `citation_cleanup` and
  `relevance_classification` are uses, not task classes; `ModelTaskClass` shipped in v1-e02-t02 with
  complex_reasoning / high_volume / deep_audit / embeddings / rerank, and v1-e05-t01 requires
  config/model_routing.yaml to map those. Keying on the shipped enum was the only choice that leaves
  E05 able to load the file. The PM is amending the `routing-config` node text in a separate specs
  PR; annotating which of the three uses falls into which class was the right call.
- Keeping bucket, KMS key, region and SSO profile out of StorageSettings is correct: they come from
  the Terraform outputs in v1-e29-t05, and both starter profiles and the module docstring say so.
  `caselist_token` as a SecretStr from env or .env only, with a test asserting no committed profile
  sets a secret, is the behaviour the caselist data-use policy depends on.
- No new exit codes: ConfigurationError derives from DomainError, so a bad DEBATE_ENV renders a
  failure panel and exits 1 rather than looking like an internal bug. That is the contract from
  v1-e01-t07 working as intended.
- Operator note carried forward: the failing `site-checks` pre-commit hook is unrelated to this task
  (`pnpm --dir site install` fixes it) and is worth folding into the site README's setup section in
  one of the E36 polish tasks.
