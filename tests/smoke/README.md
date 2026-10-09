# tests/smoke

Checks of a **build** of debate-research, run the way a person runs it: as a process, from its
console script. They are what `validate-dev` runs before a `dev` → `main` promotion
([docs/process/branching-and-environments.md](../../docs/process/branching-and-environments.md)),
against the pre-release built from the exact commit being promoted, installed the way a coach
installs it. Never against this checkout's code.

## How validate-dev runs this directory

[`.github/workflows/validate-dev.yml`](../../.github/workflows/validate-dev.yml) runs after every
dev pre-release (and nightly, and on dispatch), through
[`scripts/validate_dev.py`](../../scripts/validate_dev.py):

1. It finds the published `vX.Y.Z-dev.N` pre-release whose tag points at the commit.
2. It installs that tag with `scripts/install_channel.sh` into a scratch uv tool directory. The
   installer verifies `SHA256SUMS` and the wheels' provenance, and refuses an incomplete build.
3. It checks that the installed `debate-research --version --json`, with `DEBATE_ENV` unset,
   reports that commit, that tag and channel `dev`.
4. From a checkout of the same commit, it runs this directory against the installed binary, with
   `DEBATE_SMOKE_BIN` naming it. Then it runs the offline slow tier from the same checkout.
5. It posts the `validate-dev` commit status: `success` only on the commit the installed build
   reported, and only if every tier passed.

**A skipped test fails its tier.** A tier passes only when pytest ran at least one test and none
failed, errored or was skipped (an expected failure counts as a skip). A check skipped because a
fixture or variable is missing is a check that did not run, and validate-dev will not go green on
one. A check that needs something a runner does not have belongs in another tier, not behind a
skip.

## The tiers

| Tier | Selection | Runs against | When | Network |
|---|---|---|---|---|
| **Recorded** | `tests/smoke -m "not live and not in_process"` | the installed pre-release (`DEBATE_SMOKE_BIN`) | every validate-dev run; must finish well inside 5 minutes | none, enforced (below) |
| **Slow** | `-m "slow and not live and not eval"` over the whole suite | this checkout's source, at the validated commit | every validate-dev run | none: pytest-socket, as in `ci` |
| **Live canary** | `tests/smoke -m "live and canary"` | the installed pre-release | only when validate-dev is dispatched with `live: true` or the repository variable `VALIDATE_DEV_LIVE` is `true` | a handful of polite calls under the dev budget; **never OpenCaselist** |
| **In-process** | `-m in_process` | this checkout's source, inside pytest's process | every PR, in `ci` | none |
| **Operator-run live** | `-m live` with `-m dev` / `-m prod`, or a named file | a deployed environment | by hand, after a deploy or an apply | yes; told where to look by variables |

The slow tier leaves out the **parser evaluation** (`eval`). It needs the evaluation corpus, which
by policy never reaches a runner, so there it could only skip, and a skip fails the tier. The PM's
decision (v1-e31-t05) is that the full evaluation runs on the operator's Mac before any promotion
that contains a parser change.

## How a smoke check reaches the CLI

Through the `installed_cli` fixture ([`conftest.py`](conftest.py), [`installed_build.py`](installed_build.py)),
and no other way:

* With `DEBATE_SMOKE_BIN` set (validate-dev also sets `DEBATE_SMOKE_EXPECT_SHA` and
  `DEBATE_SMOKE_EXPECT_TAG`), the binary is that file. The harness refuses a binary or interpreter
  inside this checkout. It also refuses to start if any selected check under `tests/smoke` does
  not use `installed_cli`, because that check would be testing the source tree.
* Without it (`uv run pytest tests/smoke` on a laptop, and `ci`), the binary is this workspace's
  own console script, `.venv/bin/debate-research`, which reports channel `local`.

`installed_cli.run(...)` starts the binary in a fresh `HOME`, working directory and data directory
under `tmp_path`, in an environment built from scratch. It inherits no `DEBATE_*`, AWS or token
variable, takes the checkout's `.venv` off `PATH`, and sets `DEBATE_ENV=dev` and
`DEBATE_STORAGE__DATA_DIR` to the scratch data directory. Pass `env={...}` to override a variable
for one run (`None` removes it), or call `installed_cli.configure(...)` in a fixture to override it
for every run in a check.

**Offline means offline (ac4 of v1-e01-t10).** Unless a check is marked `live`:

* pytest's own process has sockets blocked by the conftest itself, whatever the command line says;
* the CLI's process gets [`network_guard/sitecustomize.py`](network_guard/sitecustomize.py) on its
  `PYTHONPATH`. That module refuses every connection, send and host lookup to the internet and
  writes each refusal to a log, and the fixture fails the check afterwards if the log holds
  anything, even when the command caught the refusal and carried on.

[`test_network_guard.py`](test_network_guard.py) proves this on whichever build is under test,
including the installed pre-release in every validate-dev run.

## Markers

| Marker | Meaning |
|---|---|
| `live` | Needs the network or a deployed environment. Excluded by default; the network guard is off for it. |
| `canary` | Part of validate-dev's opt-in live canary tier. Always together with `live`. |
| `in_process` | Drives the CLI inside pytest's own process (`CliRunner`, moto, respx), or tests the harness. `ci` runs it; validate-dev's recorded tier does not, because it would be testing the source. |
| `dev`, `prod` | A live check aimed at that environment. |
| `slow` | Takes more than a few seconds. Out of `ci`, in validate-dev's slow tier. |

## The checks

| File | What it checks | How it runs |
|---|---|---|
| `test_cli_smoke.py` | `--version` reports the commit, tag and channel the build was installed for; `doctor` runs on the build's own interpreter with every service wired; `config show` redacts every secret in JSON and table form, uses the scratch data directory, defaults to `dev` with `DEBATE_ENV` unset, and gives dev and prod their own data directory, routing file and budget; `verify` on v1-e03-t06's fixture manifests (`tests/fixtures/verify/`), with the snapshots written into the run's data directory by `build_fixture_data_dir`: all-VERIFIED exits 0, the tampered card is UNVERIFIED with `TEXT_MISMATCH` and exits 1 (v1-e01-t10) | **Recorded**, installed binary |
| `test_network_guard.py` | The build's interpreter cannot open a connection, and a request the CLI itself makes (`caselist auth login` aimed at the unroutable 192.0.2.1) is refused and logged (v1-e01-t10) | **Recorded**, installed binary |
| `test_caselist_import_smoke.py` | `caselist import`, `caselist import-openev` and `caselist reimport-openev-metadata`, offline: three synthetic weekly archives into a fresh data directory, with the counts, the manifests and the re-import no-op checked against `tests/fixtures/caselist/expected_summary.json` (`v1-e30-t03`); then synthetic camp files into the same directory, checked against `tests/fixtures/openev/expected_openev_import.json` (`v1-e30-t04`); then the metadata re-import over that release, which with the same table must change nothing (`v1-e30-t08`) | **Recorded**, installed binary |
| `test_caselist_cards.py` | `caselist cards`, offline: the three synthetic weeks imported, then the counts and top clusters over `tests/fixtures/fingerprints/parsed_cards_testcl26.jsonl`, `--snapshot`, and `--by-team` showing school and team code only (`v1-e31-t04`). Its fixture-drift check is `in_process` | **Recorded**, installed binary |
| `test_caselist_auth.py` | `caselist auth status`, offline: no token and the API disabled on a fresh installation, a stored token reported and never printed, a token file others can read refused, `login` refused while the API is off (`v1-e34-t01`). One live check lists archives with the operator's real token | **Recorded**, installed binary; the live check is operator-run and `in_process` |
| `test_caselist_publish_smoke.py` | `caselist publish` and `caselist status` against a moto dev bucket (`v1-e30-t05`) | **In-process** (moto) |
| `test_caselist_remove_smoke.py` | `caselist remove` and `caselist unsuppress` against a moto dev bucket (`v1-e30-t07`) | **In-process** (moto) |
| `test_caselist_pull.py` | `caselist pull`: a dry run, a whole weekly run with respx answering OpenCaselist and moto answering S3, and a second run that finds nothing new (`v1-e34-t02`). One live check lists only, against the real API | **In-process** (respx, moto); the live check is operator-run |
| `test_caselist_runs.py` | `caselist runs`, from the local log and from the bucket (`v1-e34-t03`) | **In-process** (respx, moto) |
| `test_store_cli.py` | `store ls` and `store sync --dry-run` against a real evidence bucket, read-only (`v1-e29-t05`) | **Operator-run live**, `in_process`; needs an SSO session |
| `test_site.py` | The public team website (`scripts/site_smoke.py`, `v1-e36-t05`, `v1-e36-t08`) | **Operator-run live**, after a site deploy. Not validate-dev: the site is deployed by hand, not per dev commit |
| `test_live_canary.py` | One HEAD request from the installed build's own HTTP stack to the public page of the release it was installed from | **Live canary**, installed binary |
| `test_smoke_harness.py` | The harness itself: which binary it runs, the refusals, the environment it builds | **In-process** |

The moto and respx checks cannot run against an installed build as they stand: moto and respx
patch the process they run in, and the installed binary is a different process. Running them
against the binary would need a moto server and a local stand-in for OpenCaselist, both reached
over loopback; until then, `ci` runs them on every PR and on the push to `dev` that produces the
pre-release.

Importing the **real** weekly archives is an operator-run job (`v1-e30-t06`), not a check here: it
takes far longer than any budget, and no real caselist file may enter this repository at all
([docs/policies/caselist-data-use.md](../../docs/policies/caselist-data-use.md)).

## Running it

The recorded tier against this checkout's own console script:

```bash
uv run pytest tests/smoke -m "not live and not in_process"
```

Everything `ci` runs here, the in-process checks included:

```bash
uv run pytest tests/smoke -m "not live"
```

The recorded tier against the newest dev pre-release, installed into a scratch directory, exactly
as validate-dev runs it. `--rehearsal` lets the tests come from this checkout even when it is not
the tag's commit; the report records the difference, and `conclude` would refuse to post success on
it. Your own installed `debate-research` is not touched:

```bash
TAG=$(gh release list --limit 1 --json tagName --jq '.[0].tagName')
SHA=$(gh api "repos/charlesclark2/debate-intelligence/git/ref/tags/${TAG}" --jq .object.sha)
uv run scripts/validate_dev.py smoke --sha "${SHA}" --tag "${TAG}" --rehearsal --work-dir "$(mktemp -d)"
```

The live canary, against this checkout's console script:

```bash
uv run pytest tests/smoke -m "live and canary"
```

The operator-run live checks. The site:

```bash
SITE_SMOKE_URL=https://dev.wfbdebate.com SITE_SMOKE_ENV=dev SITE_SMOKE_SHA=$(git rev-parse HEAD) uv run pytest tests/smoke -m dev
```

The evidence store, after an SSO login:

```bash
aws sso login --profile debate-dev-evidence
STORE_SMOKE_ENV=dev uv run pytest tests/smoke/test_store_cli.py -m dev
```

OpenCaselist, with the operator's own token. It lists archives and never downloads:

```bash
DEBATE_ENV=dev DEBATE_CASELIST__API_ENABLED=true CASELIST_LIVE_SLUG=hsld26 uv run pytest tests/smoke/test_caselist_auth.py tests/smoke/test_caselist_pull.py -m live
```

`test_store_cli.py` only reads and plans; it never writes to a bucket, so running it against prod
after a prod apply is safe. Publishing evidence is a deliberate `--apply` by a person
([docs/guides/evidence-store-cli.md](../../docs/guides/evidence-store-cli.md)).

## Adding a smoke check

A task that adds or changes a user-facing command adds its smoke check here, and says so in its
spec (working agreement 5). For a CLI command:

1. **Write it against the installed build.** Take the `installed_cli` fixture and run the command
   with `installed_cli.run("--json", "<command>", ...)`. Read the result from `run.exit_code`,
   `run.stdout` and `run.envelope()`. Never import `create_app` or use `CliRunner` for a recorded
   check: validate-dev refuses to start if a selected check does not use `installed_cli`.
2. **Make it offline and self-contained.** Build whatever it needs, such as archives, a profile
   under `DEBATE_PROFILE_DIR` or a data directory, inside `tmp_path`, from the synthetic builders in
   `tests/fixtures/`. Data is synthetic or public, never a real student's or a real caselist file,
   and never a real data directory. A fixture that is missing is an error, not a skip: a skipped
   check fails validate-dev.
3. **Write the expected output by hand** from the fixture (working agreement 6): counts, verdicts,
   exit codes.
4. **Keep it fast.** The recorded tier must stay well inside 5 minutes in total. Something slower
   is marked `slow` and belongs in the slow tier, under `tests/` beside the code it exercises rather
   than here.
5. **If it needs the network, it is not a recorded check.** If it is a polite, read-only call
   under the dev budget that is safe to run unattended, mark it `live` and `canary`; it never calls
   OpenCaselist, whose allowance belongs to the weekly agent. If it needs credentials or a deployed
   environment, mark it `live` (and `dev`/`prod`) and document the variables it reads in the table
   above. Either way, a `live` check that lacks what it needs may skip, because only the canary
   tier is ever run unattended.
6. **If it can only run in pytest's own process** (it patches something with moto or respx), mark
   it `in_process` and say why in the module. `ci` runs it, and validate-dev does not, so it does
   not count as the command's smoke check for a promotion; aim to make the command testable
   against the binary instead.
7. **Add a row to the table above**, naming the file, what it checks, the task, and how it runs.

Run `uv run pytest tests/smoke -m "not live and not in_process"` before opening the pull request.
Then check it against an installed build with the `--rehearsal` command above, using the newest
pre-release.

Cloud-only checks move to `tests/smoke/cloud/` from V2, where `v2-e12-t07` calls validate-dev as a
reusable workflow and adds them.
