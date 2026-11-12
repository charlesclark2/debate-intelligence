# Session report: v1-e41-t22-per-user-credentials-file-and-a-missing-working-folder

| | |
|---|---|
| Task | `v1-e41-t22-per-user-credentials-file-and-a-missing-working-folder` — Keys come from a per-user file in any folder, and a deleted working folder no longer crashes a command |
| Spec | [`plan_specs/v1/e41-delivery-tooling-upkeep/t22-per-user-credentials-file-and-a-missing-working-folder.yaml`](../../plan_specs/v1/e41-delivery-tooling-upkeep/t22-per-user-credentials-file-and-a-missing-working-folder.yaml) |
| Epic / release | `v1-e41-delivery-tooling-upkeep` / `v1.8` |
| Branch | `task/v1-e41-t22-per-user-credentials-file-and-a-missing-working-folder` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Settings now read the four provider credentials from `~/.debate-research/<env>.env`, in any folder.
The file sits below the variables and the one `.env` and above the profile, as ruled. It is refused
when its group or others have any permission (`0o077`, judged with `fstat` before a byte is read), on
a system with no POSIX modes, and for any other name. Refusals give file and line, never a value.
`config show` names each credential's source with the value masked. The new `doctor --providers`
gives one never-failing row per enabled provider. A deleted working folder now gives one warning line
instead of a crash: the real `--version` exits 0 where it exited 70. The PM should look first at the
root `conftest.py` fixture (Deviation 1), because it makes the affected set the whole selection, so
the pull request's `ci` runs everything. The Goal is `Succeeded`: every criterion passed in this
session.

## Proposal for the PM's ruling (written before any code)

Read for it: `debate_core.application.settings` (every layer and every `cwd` read), `config show`,
`doctor`, v1-e07-t13's report (Q2 and the PM's ruling), `docs/runbooks`, `docs/guides`, the CLI
README's search section, `.env.example` and the root README's precedence paragraph.

### What is true today, and where it differs from the spec's wording

* **There is one `.env`, not two layers.** The spec lists "the working folder's `.env`, the
  checkout's `.env`". `_default_dotenv_path` (settings.py line 1615) reads exactly one file: the
  checkout root's `.env` when the working folder is inside a checkout (`find_repository_root`), and
  the working folder's own `.env` only outside one. The order today is: flag, `DEBATE_*` variables,
  that one `.env`, the profile, the built-in profile, the field default.
* **A blank exported variable already wins.** Measured with invented values: an exported
  `DEBATE_PROVIDERS__CONTACT_EMAIL=` (empty) over a `.env` that sets an email leaves the setting
  blank, with source `env:DEBATE_PROVIDERS__CONTACT_EMAIL`, and Crossref uses its public pool.
* **The crash, traced.** `debate-research --version` run from a deleted folder exits 70 with
  `FileNotFoundError` from `root_callback` (app.py line 197) → `resolve_environment` →
  `_environment_from_dotenv` → `_default_dotenv_path` → `find_repository_root` → `Path.cwd()`.
  `load_settings` fails the same way.
* **No runbook or guide names the smoke folder.** `grep -rn crossref-smoke` finds it only in three
  session reports (v1-e07-t03, v1-e07-t13, and the PM's review of v1-e08-t10, which asks for that
  task's live check to be run from `~/Documents/debate/crossref-smoke`). What tells a reader where
  keys are read is the CLI README's search section ("Today a `.env` is read from the checkout a
  command runs in, or, outside a checkout, from the folder it runs in"), `.env.example`'s precedence
  comment and the root README's precedence paragraph.
* **Plain `doctor` loads no settings, on purpose**: `scripts/install_channel.sh` and `validate-dev`
  run it on machines with no configuration (doctor.py module docstring). Provider rows need
  settings.

The relay block in this session's message to the operator carried the proposal and its questions.

### The PM's ruling (2026-11-05)

1. **Order: yes**, flag > `DEBATE_*` variables > the one `.env` > `~/.debate-research/<env>.env` >
   profile > built-in > default. `<env>` is the resolved environment, `DEBATE_ENV` is never read
   from the file, the path is fixed, `test` reads no per-user file, the higher layer wins outright
   and a blank counts, `config show` prints only the winner, masked, with no new JSON key. The guide
   says plainly that a key left in a checkout's or folder's `.env` wins, and how to see which won.
2. **The four names, as a constant**; the caselist token refused with the `caselist auth login`
   hint; the completeness test accepted; refusals name the file and line, never a value; a line
   without `=` or with an invalid name by its line number only; a name given twice refused with both.
3. **`0o077`**, one rule with the token file; `fstat` on the open file before any byte is read; a
   symlink judged by its target; no ownership check; refused on Windows; a file the owner cannot
   read gives "could not read". A `0o620` file is refused too, by test.
4. **Yes**: one `working_folder()`, every startup read through it, relative-path validators a
   `ConfigurationError` naming the field, the one warning line from the root callback.
   `--version` from a deleted folder exits 0 with the warning, red first against exit 70.
5. **`doctor --providers`**, rows as proposed, except OpenAlex's: "with a key" / "keyless (a lower
   daily allowance)", because the daily figures are not this build's.
6. **A**: an autouse fixture in the root `conftest.py`; a Deviation.
7. **All three docs**; the guide uses placeholders only, and its move-the-keys block prints no value.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `per-user-credentials-file-and-a-missing` (Per-user credentials) | Done | Proposal, ruling, red run against a refuse-nothing skeleton (`5c9c76d`), implementation (`f5e2d08`), docs (`228c4ce`, `57dc8ac`). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: the file's place in the order of sources is ruled on by the PM, settings read it as ruled, and refuse a file others can read and any name that is not a credential, by tests with invented values shown failing first | PASS | Ruling recorded above (2026-11-05). `test_settings_user_credentials.py` (54 tests with the working-folder file): order (variable, blank variable, `.env` each beat the file; the file beats the profile), `test` reads none, the four names, `DEBATE_ENV` and the caselist token refused, no-`=` and invalid names by line number only, duplicates by both lines, ten refused modes including `0o620`, three accepted ones, mode judged before any read, symlink by target, Windows refused, owner-unreadable, a folder in the file's place. Every refusal is checked for no value in its message, attributes and chained traceback. **Red**: `hard_stop.py 115 … pytest -n 0` over the four new test files against `5c9c76d` → `62 failed, 20 passed`; each failure is an assertion (`DID NOT RAISE ConfigurationError` ×24, `assert None == '<sentinel>'`, exit-code asserts) or the crash being fixed (`FileNotFoundError` ×9, `PermissionError` ×1); no collection error. **Green**: the same command → `82 passed in 2.07s`. |
| **ac2**: `config show` names each credential's source, masked; `doctor` reports each provider's missing key or email without failing; a deleted working folder gives a warning instead of a crash, by tests shown failing first | PASS | `test_per_user_credentials_and_a_missing_working_folder.py` (`config show`: source `user-env:~/.debate-research/dev.env`, value `***`, no new JSON key, only the winner named, no value in any of four output modes; refusals through the CLI; `--version` and `--json --version` exit 0 with exactly one stderr line; `config show` from a deleted folder; `--help`) and `commands/test_doctor_providers.py` (rows written by hand, blank as missing, no-adapter and keyless rows, none enabled, `test`, the JSON shape, plain doctor has no `providers` key and ignores a refused file, `--providers` stops on one). Red and green in the run above. Real console script from a deleted folder: before, `INTERNAL_ERROR … FileNotFoundError`, exit 70 (traced in the proposal); after, the warning line, `debate-research 1.1.0 (local channel, dev environment, f5e2d080c5b7)`, `exit 0`. Smoke check against the installed-build harness: red against the skeleton (`AssertionError: assert 'default' == 'user-env:~/....'`, `1 failed`), green after. |
| Node: Per-user credentials tests pass (`uv run pytest packages/debate_core/tests packages/debate_cli/tests -k "settings or config or doctor"`) | PASS | `hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests packages/debate_cli/tests -k "settings or config or doctor" -n auto -m "not slow and not live"` → `641 passed in 108.10s`. |

## Files changed

* **`packages/debate_core/src/debate_core/application/settings.py`**: `working_folder()`, and every
  startup read of the working folder through it (`find_repository_root`, `_default_dotenv_path`, and
  through them `resolve_environment`, `load_settings` and `_profile_directory`). `_absolute_path` for
  `storage.data_dir`, `caselist.inbox_dir` and `caselist.secret_file`, so a relative value with no
  working folder is a `ConfigurationError` naming the field. The per-user layer: its constants
  (`USER_CREDENTIAL_VARIABLES`, `USER_CREDENTIAL_EXCLUSIONS`, `OWNER_ONLY_MODE_MASK`), its seam
  (`user_credentials_directory`), `user_credentials_file`, `display_user_path`,
  `_user_credentials_layer` and its parser, wired between the `.env` and the profile.
  `MISSING_WORKING_FOLDER_WARNING`. The module docstring's table of sources and its new section.
* **`packages/debate_core/src/debate_core/application/provider_credentials.py`** (new): the rows for
  `doctor --providers`.
* **`packages/debate_cli/src/debate_cli/app.py`**: the root callback prints the warning line once.
* **`packages/debate_cli/src/debate_cli/commands/doctor.py`**: `--providers`, its rows and its
  docstring section. The handler stays within 25 statements.
* **`packages/debate_cli/src/debate_cli/commands/config.py`**: docstring only (six places).
* **`conftest.py`**: the autouse `no_per_user_credentials` fixture (Deviation 1).
* **Tests (new)**: `packages/debate_core/tests/application/test_settings_user_credentials.py`,
  `test_settings_missing_working_folder.py`,
  `packages/debate_cli/tests/test_per_user_credentials_and_a_missing_working_folder.py`,
  `packages/debate_cli/tests/commands/test_doctor_providers.py`; one smoke check in
  `tests/smoke/test_cli_smoke.py` (Deviation 3).
* **Docs**: `docs/guides/provider-credentials.md` (new); the CLI README's `doctor` and search
  sections; the precedence lines in `.env.example` and `README.md` (Deviation 2).

## Deviations from the spec

1. **`conftest.py` (root) is outside the task's packages.** As the PM ruled on Q6 (A), an autouse
   fixture points every test's per-user folder at one that does not exist. It is shared test ground,
   so `affected_tests.py` reports the whole selection, and the pull request's `ci` runs all of it.
   Tests that run the CLI in a **subprocess** do not get the monkeypatch, so I read each one that
   starts `debate_cli`, `debate-research` or `load_settings` in a subprocess. None loads dev or prod
   settings with the real `HOME`. `tests/smoke` gives every run its own scratch `HOME`.
   `tests/cli/test_verify_cli.py` runs as `test`, which reads no per-user file. The rest import
   modules, render help, run `--version` or plain `doctor` (none of which loads settings), or run
   scripts that do not use settings.
2. **`.env.example` and `README.md`**: their precedence lines name the new layer (Q7, ruled).
3. **`tests/smoke/test_cli_smoke.py` is outside the task's packages.** Agreement 5 asks for a smoke
   check on a changed user-facing surface, and the spec's plan has no smoke node. The check writes a
   per-user file into the harness's scratch home and runs `config show` and `doctor --providers`
   against the build under test. It also checks a group-readable file is refused, and that no
   value is printed.
4. **The spec's order of sources lists two `.env` layers; there is one** (the checkout's, or the
   working folder's outside a checkout). Ruled on Q1; the code and docs state the real rule.
5. **No runbook under `docs/runbooks` or `docs/guides` named the smoke folder.** The pointer now
   lives in the new guide, which says live searches no longer need that folder, and in the CLI
   README's search section (Q7, ruled). The session reports that name it are left as written.
6. **The node's acceptance command was run with `-n auto -m "not slow and not live"`**, CI's markers,
   under `hard_stop.py 115`.

## Decisions and assumptions

* **Names are matched case-insensitively**, as a `.env`'s are, and the message spells the name in
  upper case. An `export ` prefix, one pair of matching quotes, and an unquoted value's ` #` comment
  are read as python-dotenv reads them. A value is never multi-line.
* **Every problem in the file is reported at once**, in line order, so one edit fixes them all.
* **A folder or other non-file at the file's path** is refused ("is not a file"). A dangling symlink
  is the same as no file.
* **"read" on the `Credentials file` row means the file exists.** Settings that loaded have read the
  file or refused it, so existence is enough.
* **`PROVIDERS_WITHOUT_AN_ADAPTER`** (Semantic Scholar, GDELT) is written in
  `provider_credentials.py`, beside the container's discovery factories. No test pins the two
  together (Follow-up work).
* **Mutants**, on the integrity rules, each restored with `git checkout HEAD --`:
  read bits only (`0o044`) → 4 caught (0o620, 0o602, 0o610, 0o601); caselist-token exclusion skipped
  → 1 caught; `working_folder` catching only `FileNotFoundError` → 1 caught; duplicates allowed → 1
  caught. No Hypothesis property is involved, so agreement 8's database rule does not apply.
* **The guide's move block was run for real under `zsh -f -i`** in a scratch `HOME`, with an invented
  smoke `.env` holding two credentials, a storage setting and a caselist token. It printed `copied 2
  credential lines`, left the file `-rw-------` with only the two credential lines, and each guard
  stopped it with its message. The check block then printed `***` and
  `user-env:~/.debate-research/dev.env`, and no invented value.

## Checks before the report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py --run` | `The whole selection is affected: conftest.py is shared test ground.` Nothing run; left to the pull request's `ci` (agreement 10, and the PM's ruling on Q6). |
| The node's acceptance command (above) | `641 passed in 108.10s` |
| `hard_stop.py 115 … pytest -n auto` over `tests/architecture`, `tests/specs`, `tests/smoke/test_cli_smoke.py`, `test_container_factories.py`, `test_installation.py`, `test_app.py` | `421 passed in 19.68s` |
| `hard_stop.py 115 … pytest -n 4` over every `test_settings*.py`, `test_config_command.py`, `commands/test_doctor*.py`, `test_plain_doctor_reaches_no_network.py`, `test_app.py`, `test_version.py`, `test_help_rendering.py`, `test_routing_file_checked_at_startup.py`, `test_landscape_command.py`, `test_search_command.py` | `605 passed in 52.13s` |
| `uv run ruff format --check .` / `uv run ruff check .` | `1976 files already formatted` / `All checks passed!` |
| `uv run pyright packages/debate_cli` / `… packages/debate_core/src/debate_core/application` + the new tests, `conftest.py`, the smoke file | `0 errors, 0 warnings, 0 informations` each. One run over both whole packages was stopped at 115 s under load, so it was split. |
| `uv run lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `uv run python scripts/check_thin_handlers.py` | `OK: 72 CLI command and API route handlers within 25 statements` |
| `uv run python scripts/check_command_blocks.py --base origin/dev` | `OK: no # comments in 682 shell code blocks in 250 Markdown files` |
| `scripts/docs_index.py --check-descriptions` / `scripts/check_links.py` | `All 69 indexed documents under docs/ have a description` / `OK: 3629 relative links and anchors in 614 Markdown files` |
| `uv run scripts/validate_specs.py` (after `Succeeded`) | `OK: 637 files, 41 epics, 574 tasks, 22 releases` |

No credential was read, printed or written in this session. Every value in a test or measurement
was invented. No test reaches a network.

## Operator follow-ups

Not an acceptance criterion. Once a build with this change is installed (the next dev pre-release),
move the keys out of the smoke folder, as the guide says. Run it in a new terminal on the operator's
Mac, from any folder. It takes about a second and prints a count of lines, never a value. It stops,
saying why, if a `DEBATE_` variable is set or the file already exists.

```bash
if env | grep -q '^DEBATE_'; then
  echo "STOP: a DEBATE_ variable is set in this shell. Open a new terminal, or unset it, then paste this block again."
elif [ -e ~/.debate-research/dev.env ]; then
  echo "STOP: ~/.debate-research/dev.env already exists, and this block never overwrites it."
else
  mkdir -p ~/.debate-research
  (umask 077 && grep -E '^(export[[:space:]]+)?DEBATE_PROVIDERS__(CONTACT_EMAIL|OPENALEX_API_KEY|SEMANTIC_SCHOLAR_API_KEY|API_DATA_GOV_KEY)=' ~/Documents/debate/crossref-smoke/.env > ~/.debate-research/dev.env)
  chmod 600 ~/.debate-research/dev.env
  echo "copied $(wc -l < ~/.debate-research/dev.env | tr -d ' ') credential lines into ~/.debate-research/dev.env"
fi
```

Success: `copied N credential lines` with N the number of credentials the smoke folder's `.env` held
(two or three). Then check it from the home folder. Both commands mask every value.

```bash
cd ~
debate-research config show | grep -E 'providers\.(contact_email|openalex_api_key|semantic_scholar_api_key|api_data_gov_key)'
debate-research doctor --providers
```

Success: each credential shows `***` and `user-env:~/.debate-research/dev.env`, and the
`Credentials file` row says `~/.debate-research/dev.env: read`.

## Follow-up work

* **`PROVIDERS_WITHOUT_AN_ADAPTER` is not pinned to the container's discovery factories.** A provider
  adapter added later should move its name out of that set in the same change; a test could compare
  the set with the factories' keys (E07, p3).
* **`.env.example` says `caselist auth login` writes the token into `.env`.** It does not: the token
  store keeps it (keychain, file or Secrets Manager). That line predates this task (E34 or E41, p3).
* **v1-e08-t10's required live check** asks for it to be run from `~/Documents/debate/crossref-smoke`.
  Once the keys are in the per-user file, it can be run from any folder (PM's note on that task).
* **The smoke harness runs from a fixed working folder**, so the deleted-folder warning is tested
  in-process and by hand on the real console script, not in `validate-dev` (E41, p3, if wanted).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-05

**Notes:**

Built to the ruling, with the integrity rules shown to bite: every refusal checked for no value in its
message, attributes and chained traceback, and four mutants on the mode, exclusion, folder and duplicate
rules each caught.

1. **ac1 passes.** The order is the ruled one (flag > `DEBATE_*` > the one `.env` > the per-user file >
   profile > built-in > default), with a blank higher layer winning and `test` reading no file. The mode
   is judged with `fstat` before a byte is read, ten refused modes including `0o620`, a symlink by its
   target, Windows refused. Red was 62 failed and 20 passed against the refuse-nothing skeleton, each
   failure an assertion or the crash being fixed; green 82 passed.
2. **ac2 passes.** `config show` names the source with the value masked and no new JSON key;
   `doctor --providers` never fails, and plain `doctor` still loads no settings, so the installer and
   `validate-dev` are unchanged. The real console script from a deleted folder went from exit 70 to the
   one warning line and exit 0.
3. **Deviations accepted.** 1, the root `conftest.py` fixture, is the PM's ruling on Q6 (A); the audit of
   every subprocess that starts the CLI or `load_settings` is what makes it safe, and the whole-selection
   `ci` on this pull request is the expected cost. 2 and 5 are Q7's docs. 3, the smoke check, is
   agreement 5's. 4 states the real one-`.env` rule. 6 runs the node's command under CI's markers.
4. **Decisions accepted**, python-dotenv's reading of a line and every problem reported at once in
   particular. `PROVIDERS_WITHOUT_AN_ADAPTER` stays in `provider_credentials.py`, with the pin below.
5. **Follow-ups.** The PM files two in the next batch: the adapter set pinned to the container's
   discovery factories by test (E07, p3), and `.env.example`'s line saying `caselist auth login` writes
   the token into `.env` (E41, p3). v1-e08-t10's live check gets a PM note: any folder, once an installed
   build carries this task. The deleted-folder check in `validate-dev` is not filed: the in-process tests
   and the hand run on the real console script cover it.
6. **Operator follow-up, deferred.** This Mac keeps dev.342 installed until docx-9 is in the buckets, so
   the key move and its check run after the first install that carries this task. Until then live
   searches run from the smoke folder as before.
7. **Merge:** a plain `scripts/task pr` once `ci` is green. The Goal is `Succeeded`.

## PM note (2026-11-09)

Added by the PM. Nothing above is changed, and this section is not a review.

The operator's key move (Operator follow-ups) has run: `~/.debate-research/dev.env` holds three lines,
the contact email and the api.data.gov key among them. The OpenAlex key is still read from the main
clone's `.env` (`dotenv:.env` in `doctor --providers`). The check from an installed build carrying
this task follows the next dev install, once `2026.11.03-docx-9` is in the buckets after the 2026-11-11
run.

## PM note (2026-11-11)

Added by the PM. Nothing above is changed, and this section is not a review.

**A correction to the note of 2026-11-09:** the OpenAlex key is in `~/.debate-research/dev.env` too,
not only in the main clone's `.env`. **The installed check passed** on 2026-11-11 from `v1.1.0-dev.402`,
run from the home folder: `config show` gave the contact email, the OpenAlex key and the api.data.gov
key as `***` from `user-env:~/.debate-research/dev.env`, and `doctor --providers` read
`Credentials file ~/.debate-research/dev.env: read`, with OpenAlex keyed, Crossref in its polite pool
and GovInfo keyed. The Semantic Scholar key is not set.
