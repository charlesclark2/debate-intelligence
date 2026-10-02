# Session report: v1-e01-t17-installed-build-extras

| | |
|---|---|
| Task | `v1-e01-t17-installed-build-extras` — The installed build carries what its commands need |
| Spec | [`plan_specs/v1/e01-repo-foundation/t17-installed-build-extras.yaml`](../../plan_specs/v1/e01-repo-foundation/t17-installed-build-extras.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t17-installed-build-extras` |
| Session status | COMPLETE — ac4 run by the operator on 2026-10-02 against `v0.1.0-dev.41`; recorded by the PM |

## Summary

`debate-cli` now depends on `debate-core[aws,docx,opencaselist]`, so a channel install gets boto3,
lxml, httpx and keyring from PyPI, while both first-party wheels still come only from the verified
release files. This was confirmed in a scratch install, not assumed.

`install_channel.sh` now finishes with `python -m debate_cli.installation`. That check reads the list
of integrations from the installed container's own import statements, imports each one, and fails
unless it tried every one and all of them imported. `dev-prerelease.yml` runs the same install
before publishing, so an incomplete build is never released.

A missing optional dependency is now reported by the build's channel. An installed build is told to
reinstall with `install_channel.sh` at a fixed tag; a checkout is told
`uv sync --all-packages --extra …`. Neither message calls it a bug, and the exit status stays 70.

**Closed 2026-10-02.** ac4 was run by the operator after the `--partial` merge, against `v0.1.0-dev.41`, and passed (see its row). The PM recorded it and set the Goal to `Succeeded`.

**PM, look first at:**

* **Deviation 1.** The container does not wire the docx parser today, so ac1's "including the docx
  parser" rests on a false premise. I declared `docx` anyway and say exactly what that does and
  does not buy.
* **Decision 3.** The spec's `uv sync --extra aws` fails from the workspace root for a checkout too.

## How the operator's real install was protected

Every install ran through a wrapper (`scratch.sh` in the session scratchpad). It exports fresh
`UV_TOOL_DIR`/`UV_TOOL_BIN_DIR` under the scratchpad, then runs `uv tool dir` and
`uv tool dir --bin` and refuses with exit 99 unless both resolve inside that directory. Each run
logged the resolved paths (e.g.
`[scratch] uv tool dir = …/scratchpad/tools-dev39/tools ; uv tool dir --bin = …/scratchpad/tools-dev39/bin`).
No `uv tool install` or `uninstall` ran outside it, and the two `uv pip uninstall` calls targeted
copies of scratch environments by `--python`.

Before and after the session I fingerprinted the real install: SHA-256 of
`~/.local/share/uv/tools/debate-cli/uv-receipt.toml` and `~/.local/bin/debate-research`, plus a hash
of the sorted site-packages listing. `diff` of the two fingerprints → identical. The receipt mtime is
still `1790842006`, and the real environment still reports `0.1.0.dev33 boto3 1.43.107 lxml 6.1.3`
(the stopgap is intact).

Every `caselist pull` ran with no network and no credentials:

* `sandbox-exec` denied remote IP traffic. Proven first: `curl https://example.com` under the same
  profile → `exit 7, Couldn't connect`.
* `env -i` with a scratch `$HOME` as the working directory.
* `AWS_CONFIG_FILE=/dev/null`, `AWS_SHARED_CREDENTIALS_FILE=/dev/null`.
* `PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring`, so the real login keychain was never read.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `reproduce` — Show the installed build failing | Done | The current channel build `v0.1.0-dev.39` (assets via `gh release download`) installed into scratch, passed the old `--version` check, and failed `caselist pull --dry-run` with the operator's exit-70 error. |
| `declare` — Declare the extras and strengthen verification | Done | `debate-cli` declares `[aws,docx,opencaselist]`. `install_channel.sh` runs the container-derived check. Shown failing on the old declaration and on four mutants; passing on the fixed build. Also: the ac3 message, the `dev-prerelease.yml` gate, docs. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — an `install_channel.sh` build imports every integration the container wires, including the S3 adapter and the docx parser; shown failing first against the current channel build with the operator's exit-70 error | **PASS** (local channel builds of this branch; the published build is ac4). Docx parser: see Deviation 1 | **Failing first:** `scratch.sh dev39 scripts/install_channel.sh --dir <assets> v0.1.0-dev.39` → installed, old check passed. Then offline `debate-research --json caselist pull --caselist hsld26 --dry-run` from scratch `$HOME` → exit 70, `"code": "INTERNAL_ERROR", "message": "debate_core.integrations.s3 needs boto3, which is an optional dependency of debate-core: install it with \`uv sync --extra aws\` …", "hint": "This is a bug in debate-research. …"`. In that env: `boto3 False, lxml False, httpx True, keyring True`; `requires('debate-cli')` → `debate-core[opencaselist]==0.1.0.dev39`. **After:** commit `6f0fa9b` stamped and built as `dev-prerelease.yml` does (`git archive` export → `stamp_build.py stamp` → two `uv build --package` → `check-wheels` → `SHA256SUMS`), installed with that commit's `install_channel.sh` → exit 0. 37 packages, not 29. `debate-cli==0.1.0.dev902 (from file:///…)`, `debate-core==0.1.0.dev902 (from file:///…)`, `+ boto3==1.43.107`, `+ botocore==1.43.107`, `+ lxml==6.1.3` from the index; the `direct_url.json` provenance check passed. Check: `7/7 wired integrations import; declared extras: aws, docx, opencaselist; complete`. Same pull offline → past composition, stops at `STORE_CREDENTIALS_EXPIRED` (no AWS profile in the sandbox), exit 1, not 70. `python -c "import debate_core.integrations.docx_parser, debate_core.integrations.s3, boto3, lxml"` in that env → `docx_parser 2026.09.20-docx-1 \| s3 ok \| boto3 1.43.107 \| lxml 6.1.3`. Repeated on HEAD `3034913` (dev908) → same 7/7 complete. |
| **ac2** — post-install verification imports every wired integration; fails on a build with the extra removed; asserts it covered the container's list | **PASS** | **Fails on the old declaration:** `7c9c597` (check added, declaration not yet fixed) as dev901 → `install_channel.sh` exit 1: `debate_core.integrations.s3 FAILED ModuleNotFoundError: needs boto3 (debate-core[aws]), lxml (debate-core[docx])`, `6/7 … INCOMPLETE`, `install_channel: the build installed from v0.1.0-dev.901 is incomplete …`. The new check run with dev39's own interpreter on dev39's installed container → same, exit 1. **List from the container:** `wired_integrations()` parses the installed `debate_cli/container.py` (7 modules). `test_grimp_sees_the_same_integrations_in_the_container` compares it with grimp's import graph. Dynamic imports and integration names in strings are refused (`UnfollowableWiring`), not skipped. **Coverage:** `covered` = every wired module was tried; `complete` needs `covered`. See the mutation tables. |
| **ac3** — a missing optional dependency's message distinguishes an installed build (reinstall with `install_channel.sh` at a fixed tag) from a checkout (`uv sync --extra`) | **PASS** | **Installed build, real:** dev908 copy with boto3 removed, offline pull → exit 70, `This installed build of debate-research (v0.1.0-dev.908, dev channel) is incomplete: it does not include boto3 (debate-core's \`aws\` extra), which this command needs.` Hint: `Reinstall a complete build with \`scripts/install_channel.sh <tag>\` at a fixed release tag: \`v0.1.0-dev.908\` again if a package was removed from it by hand, or a newer tag if this build was published without it (\`gh release list\` shows them).` Details `missing: boto3, extras: aws, installation: installed build`; no `uv sync` in the envelope. **Checkout, real:** scratch venv with editable installs of this worktree, boto3 removed, same pull → exit 70, `This checkout's environment does not include boto3 (debate-core's \`aws\` extra) …`, hint `From the workspace root, run \`uv sync --all-packages --extra aws\`.` **Tests:** `test_a_checkout_is_told_which_uv_sync_to_run`, `test_an_installed_build_is_told_to_reinstall_at_a_fixed_tag_and_never_to_run_uv_sync`, and three CLI tests through `create_app()` (JSON and human, both kinds). The channel comes from `build_info.build_channel()` (Decision 4). |
| **ac4** — on a fresh install of the resulting pre-release, `DEBATE_ENV=dev debate-research caselist pull --caselist hsld26 --dry-run` from `$HOME` completes without the stopgap | **PASS** (operator, 2026-10-02; recorded by the PM) | **Publish gate:** `dev-prerelease.yml` on `48048a2` → `success`; its install step on the Linux runner logged `7/7 wired integrations import; declared extras: aws, docx, opencaselist; complete`, then `Installed debate-research 0.1.0.dev41 from v0.1.0-dev.41`. **Rehearsal:** the new script into a scratch `UV_TOOL_DIR` (`uv tool dir` printed the scratch path) → 37 packages including `boto3==1.43.107` and `lxml==6.1.3` from the index, both first-party wheels from `file://`, `7/7 … complete`. **Real install** from `$HOME` → same, `Installed debate-research 0.1.0.dev41 … at ~/.local/bin/debate-research`; then `caselist pull --caselist hsld26 --dry-run` → `14 archive(s) and 498 OpenEv file(s) listed; 0 to fetch`, `Nothing was written`, `exit=0`. **Agent and provenance:** under the launchd plist's own PATH, `command -v debate-research` → `~/.local/bin/debate-research`, `debate-research 0.1.0.dev41 (dev channel, dev environment, 48048a255c7b)`; the tool environment imports `boto3 1.43.107 lxml 6.1.3`; `requires('debate-cli')` → `debate-core[aws,docx,opencaselist]==0.1.0.dev41`; `uv-receipt.toml` lists only `debate-cli` and `debate-core`, each from the downloaded assets, so boto3 and lxml are present because the build requires them and the hand-added stopgap is gone. |
| reproduce: The exit-70 failure is captured before the change | **PASS** | See ac1, first half. |
| declare: A complete build installs, and its verification fails on an incomplete one | **PASS** | See ac1, ac2 and the mutation tables. |

### Mutations caught in scratch installs

Each one was applied to a `git archive` export of the committed tree (the worktree was never
edited), then stamped, built, and installed in its own scratch tool directory with that export's
`install_channel.sh`.

| Mutant | Result |
|---|---|
| Drop `aws` (`debate-core[docx,opencaselist]`), dev903 | **Caught.** exit 1; `s3 FAILED ModuleNotFoundError: needs boto3 (debate-core[aws])`; `6/7 … INCOMPLETE`. |
| Drop `docx` (`debate-core[aws,opencaselist]`), dev904 | **Survived, an equivalent mutant today.** exit 0, `7/7 … complete`. Nothing the container wires imports lxml, so every command still works without it. See Deviation 1. |
| Wire the parser as v1-e31-t06 would (lazy `from debate_core.integrations.docx_parser import DebateDocxParser` in a container factory) **and** drop `docx`, dev905 | **Caught.** exit 1; the check found the new integration by itself (8 wired, not 7): `docx_parser FAILED ModuleNotFoundError: no module named 'lxml'`, `7/8 … INCOMPLETE`. A later integration is not silently left out. |
| Check skips the S3 adapter (loop filtered), `aws` dropped, coverage assertion intact, dev906 | **Caught by the coverage assertion.** exit 1; `installation check: tried 6 of the 7 integrations debate_cli.container wires; every one must be checked`. |
| Same, with the coverage assertion removed (`covered` → `return True`), dev907 | **Passes an incomplete build: exit 0, `complete`, with boto3 absent.** The coverage assertion is load-bearing. |
| `aws,docx,opencaselist` declared but lxml removed from the environment (what uv dropping an extra would look like), copy of dev902 | **Caught by the declared-extras half.** exit 1; `lxml (debate-core[docx]) MISSING`, `7/7 wired integrations import; … INCOMPLETE`. |

### Mutations of the CI-path tests

`uv run pytest <selection> -q --no-cov`. Each file was committed first, restored from saved bytes,
and checked for byte equality.

| Mutant | Caught by |
|---|---|
| `install_channel.sh` no longer runs the check (`true \|\| fail`) | `test_an_installed_build_whose_integration_check_fails_fails_the_install` |
| Coverage assertion always true | `test_coverage_means_every_wired_integration_was_tried` ×2 |
| Derivation reads only module-level statements | 11 tests, including `test_the_container_wires_these_integrations` and `test_grimp_sees_the_same_integrations_in_the_container` |
| Dynamic imports no longer refused | `test_wiring_the_check_cannot_follow_is_refused_not_skipped[import_module(name)]`. The other three refusal cases still pass, because the string-constant rule also refuses them. |
| Root handler ignores a missing optional dependency | the three CLI ac3 tests |
| Installed build given the checkout's advice | three tests, including `…_never_to_run_uv_sync` |
| Check echoes the adapter's own `uv sync` message | `test_an_integration_that_does_not_import_makes_the_installation_incomplete` |
| `debate-cli` drops `aws` (pyproject only) | `test_debate_cli_declares_every_distribution_its_wired_integrations_import` and the docx-wired test |

The first run of the pyproject mutant used plain `uv run`, which re-locked `uv.lock` while the
pyproject was mutated. The final `git diff` showed it. I restored `uv.lock` from HEAD (it held no
uncommitted work), ran `uv sync --all-packages`, and re-ran the mutant with `uv run --frozen` →
still caught, `git diff` clean. The byte-restore covered the file I mutated but not the lockfile
`uv run` derives from it. Any mutation script that touches a pyproject needs `--frozen`.

### Whole-repo checks

* `uv run --frozen pytest packages/debate_cli/tests tests/scripts tests/architecture tests/docs tests/smoke -q` → `731 passed in 28.76s`.
* `uv run --frozen ruff check .` → `All checks passed!`; `ruff format --check .` → `462 files already formatted`.
* `uv run --frozen pyright` → `0 errors, 0 warnings, 0 informations`.
* `uv run --frozen lint-imports` → `Contracts: 11 kept, 0 broken.`
* `uv run scripts/check_thin_handlers.py` → `OK: 18 CLI command and API route handlers within 25 statements`.
* `shellcheck scripts/install_channel.sh` → clean; `uvx --from actionlint-py actionlint .github/workflows/dev-prerelease.yml` → exit 0.
* `uv run scripts/validate_specs.py` → `OK: 302 files, 38 epics, 244 tasks, 20 releases`. The task Goal stays `InProgress` because ac4 is NOT RUN.
* **Full suite, run by the operator** (2026-10-01, this worktree at `99be433`): `uv run pytest -q` → `3656 passed, 1 skipped in 69.26s`. The skip is `tests/evals/parser/test_parser_eval.py:279` ("6 of 6 pr-subset files are not yet corrected by a person"), not this task's. Total coverage 96%; `installation.py` 83%, with the uncovered lines mostly the human-readable report printer and `main`'s `UnfollowableWiring` exit, both exercised by the scratch installs above rather than by unit tests.

## Files changed

* **`packages/debate_cli/pyproject.toml`, `uv.lock`**: `debate-core[aws,docx,opencaselist]`, with the
  reasoning in a comment. The lock changes only debate-cli's own entry.
* **`packages/debate_cli/src/debate_cli/installation.py`** (new): `wired_integrations` (AST over the
  container), `check_installation`/`main` (`python -m debate_cli.installation [--json]`),
  `incomplete_installation_failure` (the ac3 message).
* **`packages/debate_cli/src/debate_cli/app.py`**: the root handler reports a missing optional
  dependency through `incomplete_installation_failure`. Exit 70 and the `INTERNAL_ERROR` code are
  unchanged.
* **`packages/debate_cli/src/debate_cli/container.py`**: docstring only. The old text promised the
  `uv sync --extra aws` message; it now explains that the post-install check reads this file's
  imports.
* **`packages/debate_cli/tests/test_installation.py`** (new, 26 tests).
* **`scripts/install_channel.sh`**: runs the check after the `--version` check and fails the install
  on an incomplete build; header updated.
* **`tests/scripts/test_install_channel.py`**: the synthetic CLI wheel gains a stand-in
  `debate_cli.installation` whose exit status the test sets; new test showing a failing check
  fails the install. **`tests/scripts/test_stamp_build.py`**: the two hand-written expectations name
  the new extras.
* **`.github/workflows/dev-prerelease.yml`**: installs the built assets with `install_channel.sh`
  into `$RUNNER_TEMP` before publishing.
* **Docs**: `packages/debate_cli/README.md` (what an installed build contains, the two messages),
  `docs/process/branching-and-environments.md` (channel section),
  `docs/runbooks/caselist-scheduled-sync.md` (the build must pass the check; never patch the tool
  environment by hand).

## Deviations from the spec

1. **The container does not wire the docx parser.** ac1 says "every integration the CLI's container
   wires, including the S3 adapter and the docx parser". Nothing in `debate_cli` imports
   `debate_core.integrations.docx_parser` today; the parse stage arrives with v1-e31-t06 (Pending).
   So the container-derived check covers 7 modules and not the parser.
   * **What I did anyway:** declared `docx`, as the spec and the kickoff both expected. The spec
     names the parser; v1-e31-t06 wires it into the same `caselist pull` the agent runs; the
     operator's stopgap includes lxml; and the kickoff's ac4 check imports lxml. The parser was
     shown importing in the installed build.
   * **How docx is covered now:** the check's declared-extras half confirms lxml is installed.
     Dropping the `docx` declaration is undetectable today, and that is true rather than a gap in
     the check: no wired code needs it. Once the parser is wired, the same mutant is caught at
     install time (dev905) and at PR time
     (`test_once_the_docx_parser_is_wired_dropping_the_docx_extra_is_caught`).
   * **Suggested wording for ac1:** "…every integration the CLI's container wires (today the local
     adapters, the OpenCaselist client and the S3 adapter), and the docx extra the parse stage will
     need".
2. **`.github/workflows/dev-prerelease.yml` edited**, outside `constraints.packages`. Authorised by
   the PM for this one workflow in the kickoff.
3. **`tests/scripts/test_install_channel.py` and `test_stamp_build.py` edited**, outside
   `constraints.packages` (`tests/` is not listed). They are the existing tests of the two scripts
   this task changes, where v1-e01-t09 put them, and both failed without the change.
4. **The checkout remedy is `uv sync --all-packages --extra <extra>`, not `uv sync --extra <extra>`.**
   From the workspace root, `uv sync --extra aws --dry-run` →
   `error: Extra \`aws\` is not defined in the project's \`optional-dependencies\` table`, because the
   root project has no extras. `uv sync --all-packages --extra aws --dry-run` → `Would make no
   changes`. `uv sync --package debate-core --extra aws` would work but uninstalls the dev tools. I
   kept the spec's form and made it work. The adapters' own messages and
   `packages/debate_core/README.md` still give the broken form (Follow-up work).
5. **The ac3 message is fixed at the CLI's error boundary, not in the adapter.** The text lives in
   `debate_core/integrations/s3/__init__.py`, outside this task's packages; the spec also puts "any
   change to the adapters" out of scope. The root handler replaces it, and the post-install check
   describes failures in its own words, because the adapter's text would tell an installer user to
   run `uv sync`.

6. **`debate_core` edited after PM review, authorised by the PM.** The adapters' checkout advice now
   reads `uv sync --all-packages --extra …` in `integrations/s3/__init__.py` (the `ModuleNotFoundError`
   message) and in `packages/debate_core/README.md` (the `aws` and `docx` sections). Both are outside
   `constraints.packages`; they are a message string and documentation, not adapter behaviour. I
   also corrected the same advice in two comments in `packages/debate_core/pyproject.toml` (the `aws`
   and `docx` extras), which the PM's list did not name. They are comment-only and carry the same
   defect.

## Decisions and assumptions

1. **Where the extras are declared: `debate-cli`.** The CLI is the delivery surface whose composition
   root imports the S3, OpenCaselist and (soon) docx adapters, so it owns the dependency on what
   those adapters need. `debate-core`'s base install stays free of boto3 and lxml (ADR-0001: the
   core must not import AWS SDKs; the import-linter contracts keep each library inside its
   adapter). The installer patching it over with `--with boto3` was rejected: the declaration
   would stay wrong for every other way the CLI is installed.
2. **Resolution was confirmed, not assumed.** With `--with "debate-core @ file://…"`, uv applies the
   extras from debate-cli's `debate-core[aws,docx,opencaselist]==<version>` requirement to the
   URL-sourced core: boto3, botocore and lxml came from the index, and both first-party wheels from
   `file://`. The dev39 install already showed the same for `[opencaselist]`.
3. **How the list is derived.** `ast` over the *installed* `debate_cli/container.py`, counting module-level,
   factory-level and `TYPE_CHECKING` imports. A string naming `debate_core.integrations` outside a
   docstring, or any `import_module`/`__import__` call, raises `UnfollowableWiring`. The
   import-linter contract "Delivery packages reach debate_core.integrations only through their
   composition root" makes the container the whole of the CLI's integration surface. grimp, an
   independent reader, agrees in CI.
4. **Installed build or checkout: the stamped channel.** `build_info.build_channel()` is `local`
   exactly when there is no `_build_info.py` stamp. A stamped `dev`/`stable` build gets the
   reinstall message. Edge: an unstamped wheel installed some other way (e.g. `pip install` of a
   locally built wheel) is treated as a checkout. The only supported installs are channel builds
   and checkouts.
5. **Coverage means tried, not succeeded.** `covered` = every wired module was attempted (and there
   was at least one); `complete` = covered, nothing failed, and every declared extra's
   distributions are present. A skipped integration is reported `NOT CHECKED`.
6. **The check ships in the wheel and runs as `python -m`, not in `doctor`.** v1-e01-t14 (Pending)
   will make `install_channel.sh` run `doctor` and give `doctor` the ability to fail; folding this
   in now would change `doctor`'s contract under t14. t14 can absorb it.
7. **Builds published before this change are refused by the new script**, because they do not
   contain `debate_cli.installation`. Every one of them lacks boto3, so that is correct.
8. **Exit status and error code unchanged** (70, `INTERNAL_ERROR`). Only the message, the hint and
   three new `details` fields (`missing`, `extras`, `installation`) differ.
9. **An error that names no module** (the S3 adapter's guard) is attributed to every optional
   dependency that is missing, which can over-report: dev901 listed lxml beside boto3. The remedy
   is the same either way.
10. **Importing the S3 adapter opens a loopback socket.** urllib3, via botocore, probes for IPv6 at
    import by binding `::1`. pytest-socket warns about it; it sends nothing. Any import of the S3
    adapter does it.

## Operator follow-ups

**0. Full suite** — DONE by the operator: `3656 passed, 1 skipped in 69.26s` (see Whole-repo checks).
```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e01-t17-installed-build-extras
git branch --show-current
uv run pytest -q
```
`git branch --show-current` must print `task/v1-e01-t17-installed-build-extras`. Success: every test
passes apart from any failure already present on `dev`. Paste the last 10 lines.

**1. After this merges to `dev`: the publish gate ran** (~3 min after `ci` on `dev` is green).
```bash
RUN=$(gh run list --workflow dev-prerelease.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run view "${RUN}" --json conclusion --jq .conclusion
gh run view "${RUN}" --log | grep -E "wired integrations import|Installed debate-research"
TAG=$(gh release list --limit 1 --json tagName --jq '.[0].tagName'); echo "${TAG}"
```
Success: `success`, and the log shows
`7/7 wired integrations import; declared extras: aws, docx, opencaselist; complete` from the step
"Install the build as its users will…", then the release. This step's first run on Linux happens
here; it was rehearsed only on macOS. If it fails, nothing was published. Paste the failing step's
log.

**2. Rehearse the new tag in a scratch tool directory first** (~30 s). The real install in step 3 uses
`--force`, which replaces dev33 and the stopgap *before* its check runs. Prove the tag on this Mac
without touching them.
Run steps 1–4 in one terminal: they share `${TAG}` and the downloaded script. No checkout is
needed or touched.
```bash
curl -fsSL https://raw.githubusercontent.com/charlesclark2/debate-intelligence/dev/scripts/install_channel.sh -o "${TMPDIR}install_channel.sh"
grep -c "debate_cli.installation" "${TMPDIR}install_channel.sh"
SCRATCH=$(mktemp -d)
UV_TOOL_DIR="${SCRATCH}/tools" UV_TOOL_BIN_DIR="${SCRATCH}/bin" sh -c 'uv tool dir; sh "$0" "$1"' "${TMPDIR}install_channel.sh" "${TAG}"
```
The `grep -c` must print 1 or more, which shows the downloaded script is the new one. Success: the
first line the install prints is `${SCRATCH}/tools`, not `~/.local/share/uv/tools`, and the run ends
`… complete` then `Installed debate-research … from ${TAG}`. If `uv tool dir` prints the real
directory, stop.

**3. ac4: install for real, then run the pull** (~1 min). This replaces dev33 and the hand-added
boto3/lxml.
```bash
cd ~
sh "${TMPDIR}install_channel.sh" "${TAG}"
DEBATE_ENV=dev debate-research caselist pull --caselist hsld26 --dry-run; echo "exit=$?"
```
Success: the install ends `7/7 wired integrations import; declared extras: aws, docx, opencaselist;
complete`. The pull prints its dry-run summary ("… Nothing was written. Re-run without --dry-run
to do it.") and `exit=0`. With an expired AWS session the run may say it read only this machine's
suppression list (v1-e34-t07); that is still a pass. A `STORE_CREDENTIALS_EXPIRED` refusal is not a
build problem: run `aws sso login --profile debate-dev-evidence` and repeat. Keep the output for
step 5.

**4. The launchd agent runs the new build, and its boto3/lxml came from the build** (seconds):
```bash
AGENT_PATH=$(plutil -extract EnvironmentVariables.PATH raw ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist)
env -i HOME="${HOME}" PATH="${AGENT_PATH}" sh -c 'command -v debate-research; debate-research --version'
"$(uv tool dir)/debate-cli/bin/python" -c "import boto3, lxml; print('boto3', boto3.__version__, 'lxml', lxml.__version__)"
"$(uv tool dir)/debate-cli/bin/python" -c "import importlib.metadata as m; print(m.requires('debate-cli'))"
cat "$(uv tool dir)/debate-cli/uv-receipt.toml"
```
Success, line by line:

* `/Users/charlesclark/.local/bin/debate-research` (the path the agent's own PATH resolves today),
  and `debate-research 0.1.0.devN (dev channel, …)` naming the new tag.
* `boto3 … lxml …`.
* A list containing `debate-core[aws,docx,opencaselist]==0.1.0.devN`.
* A receipt whose `requirements` list **only** `debate-cli` and `debate-core`, each with a `path`
  into the downloaded assets. No `boto3` or `lxml` entry: `--force` rebuilt the environment, so
  they are there because the build requires them, not because of the stopgap.

**5. Hand ac4 to the PM.** Once step 4 succeeds, paste the output of steps 3 and 4 back to the PM, who
records ac4 and closes the task with a small spec PR.

**Rollback**, only if step 3 fails after step 2 passed. The new script refuses `v0.1.0-dev.33`,
because that build lacks boto3, so reinstall it with the script as it was before this task:
```bash
curl -fsSL https://raw.githubusercontent.com/charlesclark2/debate-intelligence/91410a7/scripts/install_channel.sh -o "${TMPDIR}install_channel_old.sh"
sh "${TMPDIR}install_channel_old.sh" v0.1.0-dev.33
```
Then re-add the stopgap the way you added it before.

## Follow-up work

* **`install_channel.sh` replaces the working install before checking the new one** (v1-e01-t14 or a
  small follow-up in E01). `uv tool install --force` runs before every check, so a build that fails
  `--version`, provenance or the new integration check has already replaced what the launchd agent
  runs. The publish gate makes that unlikely for published builds. A rehearsal into a temporary
  `UV_TOOL_DIR`, and only then the real install, would make it impossible.
* **The adapters' checkout advice is broken from the workspace root** (debate_core, an E29/E31/E34
  follow-up). `debate_core/integrations/s3/__init__.py` and `packages/debate_core/README.md` (lines
  160 and 238) say `uv sync --extra aws` / `--extra docx`, which fail there (Deviation 4). They
  should say `uv sync --all-packages --extra …`. Outside this task's packages.
* **v1-e31-t06 inherits the docx wiring.** When it wires the parser into the container, the
  post-install check and `test_debate_cli_declares_every_distribution_its_wired_integrations_import`
  start covering it with no change here. That task should expect `8/8` in the install output.
* **v1-e01-t14 may fold `python -m debate_cli.installation` into `doctor`** once `doctor` can fail,
  so the operator has one command for "is this installation sound".
* **The launchd agent's PATH puts `~/.local/bin` last.** Today nothing earlier on it provides
  `debate-research`, but a `pip install` into anaconda or a pyenv shim would silently win. v1-e34-t10
  (the agent runs nothing from a git checkout) is the natural place to give the plist the full path
  (`DEBATE_RESEARCH_BIN`).

## Changes after PM review

Committed the PM's amendments as given (`07fa2f1`): ac1 reworded in this task's spec, and ac5 in
`v1-e01-t14` (install into a temporary tool directory, check there, replace only if every check
passes). Then the two requested changes:

1. **The adapters' checkout advice works from the workspace root** (Deviation 6). It is
   `uv sync --all-packages --extra aws` in the S3 adapter's `ModuleNotFoundError` and in the
   `debate_core` README's `aws` section, and `--extra docx` in its `docx` section. The README
   alternatives (`pip install 'debate-core[…]'`) moved from `# or:` comments inside the code blocks
   into the prose, for the same zsh reason as change 2. The same advice is corrected in the two
   comments in `packages/debate_core/pyproject.toml`. No test pinned the old wording. The two strings
   in `test_installation.py` that stand in for the adapter's message now match the new one. Those
   tests still assert that no `uv sync` reaches an installed-build user, which matters more now that
   the adapter's own text still says `uv sync`, only in a form that works.
   `grep -rn "sync --extra"` over `packages scripts tests docs ops README.md .github`, excluding
   session reports and the `--all-packages` form → nothing. Live, in the session's scratch checkout
   venv (editable install of this worktree, boto3 removed):
   `python -c "import debate_core.integrations.s3"` → ``ModuleNotFoundError: debate_core.integrations.s3 needs boto3, which is an optional dependency of debate-core: install it with `uv sync --all-packages --extra aws` from the workspace root (or `pip install 'debate-core[aws]'`).``
2. **Operator command blocks are safe to paste into zsh.** I removed the `#` comments from follow-up 0
   (after `git branch --show-current`) and follow-up 2 (after `grep -c`), and moved each expectation
   into the prose. The rollback is now its own code block rather than an inline `&&` chain. I added
   step 5: paste steps 3 and 4's output to the PM, who records ac4 and closes the task. Checked with
   an extraction of every line inside the follow-ups' ```` ```bash ```` blocks → no `#` remains.

Checks after these changes:

* `uv run --frozen pytest packages/debate_cli/tests tests/scripts packages/debate_core/tests/integrations -q` → `1105 passed in 24.72s`.
* `uv run --frozen ruff check .` → `All checks passed!`; `ruff format --check .` → `462 files already formatted`.
* `uv run --frozen pyright` → `0 errors, 0 warnings, 0 informations`.
* `uv run --frozen lint-imports` → `Contracts: 11 kept, 0 broken.`
* `uv run scripts/validate_specs.py` → `OK: 302 files, 38 epics, 244 tasks, 20 releases`.
* `uv run --frozen pytest tests/docs -q --no-cov` → `51 passed`. `uv lock --check` → the lock is
  unchanged by the comment edits.

The Goal stays `InProgress` until ac4.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-02

**Notes:**

Accepted for a `--partial` merge; the Goal stays `InProgress` until ac4, which only the operator can
run after a pre-release is published from this branch. Two small changes before the pull request
(the last two items below).

**Protecting the real install was done properly.** A wrapper that refuses unless `uv tool dir`
resolves inside the scratchpad, a before-and-after fingerprint of the receipt, the binary and the
site-packages listing, and `sandbox-exec` shown to block the network before relying on it. The
stopgap the weekly agent depends on is intact, and the report proves it rather than asserting it.

**Deriving the list from the installed container, and refusing what it cannot follow, is the design I
wanted.** The dev905 mutant shows it working: wire the parser the way v1-e31-t06 will and drop
`docx`, and the check finds the eighth integration itself. dev907 shows the coverage assertion is
load-bearing. Running the same install in `dev-prerelease.yml` means an incomplete build is never
published, which matters more than catching it on the coach's Mac.

**Deviation 1 is my error.** The container does not wire the docx parser yet. Declaring `docx` anyway,
for the reasons you give, is right, and calling the surviving drop-`docx` mutant equivalent rather
than a gap is accurate. I have reworded ac1 in this branch with your wording.

**Deviations 2 to 5 and Decisions 1 to 10 are accepted.** Declaring the extras on `debate-cli` keeps
`debate-core` lean and makes the declaration true for every way the CLI is installed. Deviation 4 is a
real defect in the spec's own advice: `uv sync --extra aws` fails at the workspace root.

**The `uv.lock` incident is reported honestly and the lesson is general.** A mutation of a
`pyproject.toml` re-locks under plain `uv run`, so the byte-restore misses the lockfile. Use
`--frozen` for any such mutation.

**Follow-ups, PM decisions.** Install-before-check is filed as `v1-e01-t14` ac5 in this branch: a
rehearsal into a temporary tool directory, then the real install only if every check passes.
Folding the check into `doctor` is noted there too. The launchd PATH is already `v1-e34-t10`. v1-e31-t06
expecting `8/8` is noted for that task's kickoff. The adapters' advice: change 1 below.

**Change 1: fix the adapters' checkout advice now.** `integrations/s3/__init__.py` line 52 and
`packages/debate_core/README.md` lines 160 and 238 give `uv sync --extra …`, which you showed fails at
the workspace root. They are message strings and documentation, not adapter behaviour, so they are
not what the spec's "no change to the adapters" was protecting. Change them to
`uv sync --all-packages --extra …`. I am authorising the edit; list it as a deviation.

**Change 2: no `#` comments in operator command blocks.** The operator's shell is zsh, which does not
treat `#` as a comment when typed or pasted interactively: in step 2, `grep -c … # 1 or more…` passes
`#`, `1`, `or` and the rest to grep as file names. Move every expectation out of the code blocks and
into the prose around them, in follow-ups 0 to 4 and the rollback.
