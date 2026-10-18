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

The recorded tier includes the checks that need S3 or OpenCaselist. They reach **stand-ins**, local
servers on loopback, and nothing else (below, and [Adding a stand-in](#adding-a-stand-in)).
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
  `PYTHONPATH`. That module refuses every connection, send and host lookup to the internet,
  loopback included, and writes each refusal to a log, and the fixture fails the check afterwards
  if the log holds anything, even when the command caught the refusal and carried on.

**Loopback, for a check that declares a stand-in, and for no other** (v1-e01-t21). A check that
takes a stand-in fixture, `s3_stand_in` or `opencaselist_stand_in`, gets a server of its own on
127.0.0.1 and an ephemeral port. The fixture names its `host:port` in `DEBATE_SMOKE_STAND_INS`, and
the guard lets the build connect to exactly those addresses: not to another loopback port, and not
off the machine. pytest's own process is opened to 127.0.0.1 alone for that check, so that it can
set the stand-in up and read what it was asked. A check that declares none is refused loopback like
any other address, and the refusal is logged.

[`test_network_guard.py`](test_network_guard.py) proves all of this on whichever build is under
test, including the installed pre-release in every validate-dev run.

## How a smoke check reaches S3 and OpenCaselist

Through two stand-ins in [`stand_ins/`](stand_ins/), each a server in a process of its own, which
the build is a client of exactly as it is of the real service. Nothing patches the build.

| Fixture | What it is | How the build is pointed at it |
|---|---|---|
| `s3_stand_in` | moto in server mode ([`stand_ins/s3_server.py`](stand_ins/s3_server.py)): the evidence bucket, STS, and IAM for the check's own role set-up | `storage.s3.endpoint_url` (`DEBATE_STORAGE__S3__ENDPOINT_URL`), which only a dev installation accepts, and only for a loopback address |
| `opencaselist_stand_in` | the OpenCaselist API and its file host, two https servers ([`stand_ins/opencaselist_server.py`](stand_ins/opencaselist_server.py)), serving synthetic responses the check describes | `caselist.api_base_url` (`DEBATE_CASELIST__API_BASE_URL`), and `SSL_CERT_FILE` naming the run's own certificate authority |

**Prod accepts neither.** A prod installation refuses `storage.s3.endpoint_url`, and any
`caselist.api_base_url` but the documented API, with a configuration error naming the setting. It
also builds its S3 and STS clients with botocore's own endpoint settings ignored (`AWS_ENDPOINT_URL`,
`AWS_ENDPOINT_URL_S3`, `AWS_ENDPOINT_URL_STS`, an `endpoint_url` in the AWS config), so nothing in a
prod environment can send its evidence store elsewhere. `test_cli_smoke.py` and
`test_caselist_publish_smoke.py` show both on the build. `config show` reports both settings and
where each value came from.

What a check can ask of the S3 stand-in, in place of the patches the in-process checks used:

* **What the build asked for:** `s3_stand_in.requests()`, each with the operation, bucket, key,
  version id and the access key that signed it. Never a signature, token or body.
* **A bucket that refuses or fails a request:** `s3_stand_in.refuse("GetObject", key=..., status=403,
  code="AccessDenied", message=...)` answers as S3 would, through botocore's own error path. A
  `HEAD` gets the status alone, as from S3. The check's own clients sign with moto's test
  credentials and are never refused, so a check that refuses the build anything signs the build's
  profiles in as roles (`tests/fixtures/identity_center_roles.py`). Set `AWS_MAX_ATTEMPTS=1` for a
  503 the check means to last: a retry would meet the same answer.
* **An older version:** `s3_stand_in.backdate(...)`, which S3 never lets a client do.

The OpenCaselist stand-in serves what the check writes with `serve_json`, `serve_file` (the file
host, which never sees the token) and `serve_api_file` (the API's own `/download`). Its API answers
401 without the `caselist_token` cookie, as the real one does. `requests()` says what was asked of
each server, and whether the cookie came, never its value. Every response is built from the
invented fixtures in `tests/fixtures/`.

Every stand-in binds 127.0.0.1 on port 0, so the system chooses a free ephemeral port and checks
running side by side never collide. Each is stopped when its check ends, and `conftest.py` fails a
check after which one is still running. [`test_stand_ins.py`](test_stand_ins.py) shows both.

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
| `test_cli_smoke.py` | `--version` reports the commit, tag and channel the build was installed for; `doctor` runs on the build's own interpreter with every service wired, and with `--evidence-profiles` fails on the everyday profile the harness's empty AWS config does not define, under `STORE_PROFILE_NOT_CONFIGURED` and naming its setting, while plain `doctor` passes there (`v1-e34-t22`); `config show` redacts every secret in JSON and table form, uses the scratch data directory, defaults to `dev` with `DEBATE_ENV` unset, and gives dev and prod their own data directory, routing file and budget; `verify` on v1-e03-t06's fixture manifests (`tests/fixtures/verify/`), with the snapshots written into the run's data directory by `build_fixture_data_dir`: all-VERIFIED exits 0, the tampered card is UNVERIFIED with `TEXT_MISMATCH` and exits 1 (v1-e01-t10); `config show` reports the two stand-in endpoint settings and their sources, and prod refuses each, naming it (v1-e01-t21) | **Recorded**, installed binary |
| `test_network_guard.py` | The build's interpreter cannot open a connection, and a request the CLI itself makes (`caselist auth login` aimed at the unroutable 192.0.2.1) is refused and logged (v1-e01-t10); loopback is refused and logged to a check that declares no stand-in, and a check that declares one reaches it and is refused, and the refusal logged, both an address off the machine and any other loopback port (v1-e01-t21) | **Recorded**, installed binary |
| `test_stand_ins.py` | Every stand-in binds 127.0.0.1 on an ephemeral port, two at once on two ports, and a stopped one has exited and refuses connections (v1-e01-t21) | **Recorded**, installed binary |
| `test_caselist_import_smoke.py` | `caselist import`, `caselist import-openev` and `caselist reimport-openev-metadata`, offline: three synthetic weekly archives into a fresh data directory, with the counts, the manifests and the re-import no-op checked against `tests/fixtures/caselist/expected_summary.json` (`v1-e30-t03`); then synthetic camp files into the same directory, checked against `tests/fixtures/openev/expected_openev_import.json` (`v1-e30-t04`); then the metadata re-import over that release, which with the same table must change nothing (`v1-e30-t08`) | **Recorded**, installed binary |
| `test_caselist_cards.py` | `caselist cards`, offline: the three synthetic weeks imported, then the counts and top clusters over `tests/fixtures/fingerprints/parsed_cards_testcl26.jsonl`, `--snapshot`, and `--by-team` showing school and team code only (`v1-e31-t04`). Its fixture-drift check is `in_process` | **Recorded**, installed binary |
| `test_caselist_parse.py` | `caselist parse`, offline: the ten `v1-e31-t03` structural fixtures filed as one fictional weekly archive, imported, then parsed by a two-worker pool into a fresh data directory with the card count their hand-written expectations name; a second run parses nothing; the store's layout holds no path; `--failures` (`v1-e31-t06`). Nothing is published | **Recorded**, installed binary |
| `test_caselist_auth.py` | `caselist auth status`, offline: no token and the API disabled on a fresh installation, a stored token reported and never printed, a token file others can read refused, `login` refused while the API is off (`v1-e34-t01`). One live check lists archives with the operator's real token | **Recorded**, installed binary; the live check is operator-run and `in_process` |
| `test_caselist_publish_smoke.py` | `caselist publish` and `caselist status` against a dev bucket (`v1-e30-t05`); a prod installation sends the evidence store to AWS whatever `AWS_ENDPOINT_URL*` names, and the stand-in hears nothing (`v1-e01-t21`) | **Recorded**, installed binary, `s3_stand_in` |
| `test_caselist_remove_smoke.py` | `caselist remove` and `caselist unsuppress` against a dev bucket (`v1-e30-t07`); the later upload at a removed path listed and removed, `--only-named`, and a plan whose JSON names no school, team, path or file (`v1-e30-t11`); a `--source` plan counting only the other teams, and `caselist status` reporting what a removal left: nothing after a complete one, versions of a later upload under a delete marker by digest prefix and count, a stopped takedown until its re-run, and *not checked* where the version listing is refused (`v1-e30-t10`); the everyday profile named for a takedown refused before anything is written, by the role it is signed in as, and a takedown profile the AWS config lacks reported as the takedown's own refusal (`v1-e29-t08`); a `--source` removal writing a path entry beside the list, `caselist import` refusing next week's upload at that path under the request, the same removal run again taking it out of the inbox, and `--only-named` holding nothing (`v1-e30-t13`); `caselist status` reporting a manifest and an aggregate version older than the removal by role and count, listing only, both cleared by the same request run again (a manifest version alone by executing a plan that says nothing is left), and a removal an older build made named as not checked (`v1-e30-t15`); a `--source` plan counting only holders other than the one removed, for a later upload the same team holds at a second path and for a camp file one or two releases hold, and no line of a `--source` plan's dry run, execution or re-run, nor its JSON, saying "this team" (`v1-e30-t16`); `caselist status` naming the upload a hold refused, still in its inbox archive, by digest prefix and request with the hint to run the removal again, and exiting 0, and nothing owed once it is run (`v1-e30-t21`); a symbolic link at the held path in next week's archive counted as skipped and given no manifest row, the publish completing and nothing owed for it (`v1-e30-t22`). The refused version listing, the takedown that loses the bucket, and the record of what `status` asked for and with which profile, come from the stand-in's side (`v1-e01-t21`) | **Recorded**, installed binary, `s3_stand_in` |
| `test_caselist_camp_identity_smoke.py` | Camp files identified by their upstream record (`v1-e30-t14`): `caselist pull` writes each camp row's OpenEv id and upstream-path digest, `caselist publish` takes them to a prod bucket from the dev data directory, and prod's `caselist remove` dry run, with no delivery record, matches the later upload by upstream path and never by file name alone; a later upload another release keeps, withdrawn from its camp path, with its plan lines naming the release and id and its withdrawal recorded as `openev`; and `caselist reimport-openev-metadata` over rows an older build wrote, `caselist status` naming the manifest mismatch and its publish hint, and the publish clearing it | **In-process** (respx, moto) |
| `test_caselist_pull.py` | `caselist pull`: a dry run, a whole weekly run against both stand-ins, and a second run that finds nothing new (`v1-e34-t02`). The whole run parses what it imported and publishes the parsed store beside the raw one, and the second run parses nothing (`v1-e34-t17`). One complete archive fetched after the weeklies, and why (`v1-e34-t04`). A camp file removed on another machine not requested again, and a bucket copy of the suppression list that is refused, does not answer or is torn failing the import closed (`v1-e34-t07`). A bucket listing that does not answer failing publish with `3`, and the next run publishing without fetching again; an unreadable blob directory failing the import with `3` (`v1-e01-t20`). A pending-work file that cannot be read failing publish with `1`, left for a person (`v1-e34-t18`) | **Recorded**, installed binary, both stand-ins |
| `test_caselist_pull_in_process.py` | `caselist pull` where a check stands in for part of the CLI, not the world: an expired session, botocore's own `ProfileNotFound` and `UnauthorizedSSOTokenError`, a refused status service, the notification a failed run sends, the clock (`v1-e34-t07`, `v1-e34-t13`, `v1-e34-t18`, `v1-e29-t07`, `v1-e34-t22`, `v1-e34-t19`). Split from `test_caselist_pull.py` by `v1-e01-t21`. One live check lists only, against the real API | **In-process** (respx, moto); the live check is operator-run |
| `test_caselist_runs.py` | `caselist runs`, from the local log and from the bucket (`v1-e34-t03`), with each run's parse counts from the details kept beside its record, and a record in the bucket that the installed build still reads (`v1-e34-t19`). Each run's codes and verdict, from the same details (`v1-e34-t23`) | **Recorded**, installed binary, both stand-ins |
| `test_store_cli.py` | `store ls` and `store sync --dry-run` against a real evidence bucket, read-only (`v1-e29-t05`) | **Operator-run live**, `in_process`; needs an SSO session |
| `test_site.py` | The public team website (`scripts/site_smoke.py`, `v1-e36-t05`, `v1-e36-t08`) | **Operator-run live**, after a site deploy. Not validate-dev: the site is deployed by hand, not per dev commit |
| `test_live_canary.py` | One HEAD request from the installed build's own HTTP stack to the public page of the release it was installed from | **Live canary**, installed binary |
| `test_smoke_harness.py` | The harness itself: which binary it runs, the refusals, the environment it builds | **In-process** |

Until `v1-e01-t21` the publish, remove, pull and runs checks used moto and respx, which patch the
process they run in, so they ran in `ci` against the source and validate-dev did not run them. They
now run the installed build against the stand-ins. What could not move is in
`test_caselist_pull_in_process.py`: those checks replace part of the CLI itself, which no stand-in
can do from outside the build.

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
it. A pre-release built before `v1-e01-t21` does not know `storage.s3.endpoint_url`, so the
stand-in checks fail against it: rehearse against one built since. Your own installed
`debate-research` is not touched:

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
DEBATE_ENV=dev DEBATE_CASELIST__API_ENABLED=true CASELIST_LIVE_SLUG=hsld26 uv run pytest tests/smoke/test_caselist_auth.py tests/smoke/test_caselist_pull_in_process.py -m live
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
6. **If it needs S3 or OpenCaselist**, take `s3_stand_in` or `opencaselist_stand_in` and point the
   build at the bucket or the site it serves; never moto's `mock_aws()` or respx, which the build
   cannot see. If what it needs is not a service but a part of the CLI (an exception the adapter
   raises before any request, the notifier, the clock), it can only run in pytest's own process:
   mark it `in_process`, say why in the module, and keep it out of the command's recorded module.
   `ci` runs it, and validate-dev does not, so it does not count as the command's smoke check for a
   promotion. A check that needs a service no stand-in serves gets a new stand-in (below).
7. **Add a row to the table above**, naming the file, what it checks, the task, and how it runs.

Run `uv run pytest tests/smoke -m "not live and not in_process"` before opening the pull request.
Then check it against an installed build with the `--rehearsal` command above, using the newest
pre-release.

## Adding a stand-in

For a check that needs a service neither stand-in serves. A stand-in is a server in a process of its
own, never a patch, and never a thread in pytest's process, whose sockets are blocked.

1. **Write the server** as a script in `stand_ins/`, run with this checkout's interpreter. It binds
   `127.0.0.1` on port 0, prints one JSON line naming its ports (`{"api": 50123}`) on stdout as soon
   as it is listening, and after that writes only to stderr. It serves synthetic data alone: what
   the check gives it, built from `tests/fixtures/`, never a recorded real response, name, token or
   credential.
2. **Write its handle** beside it, starting the script with `StandInProcess.start(script, ...,
   log=...)` ([`stand_ins/process.py`](stand_ins/process.py)), which waits for the ports, records
   the process so it cannot outlive its check, and stops it. Give the handle whatever the check
   needs to set the service up and to read what it was asked; never a way into the build.
3. **Add its fixture** to `conftest.py`. The fixture takes `installed_cli`, starts the stand-in,
   calls `installed_cli.allow_stand_in(host, port)` for every address it announced, configures the
   build to reach it, and stops it in a `finally`. Add the fixture's name to `STAND_IN_FIXTURES`
   in [`stand_ins/__init__.py`](stand_ins/__init__.py): that is what opens pytest's process to
   127.0.0.1 for the check, and nothing else does.
4. **Point the build at it with configuration a prod installation refuses.** If the CLI has no such
   setting, add one that only dev accepts, loopback only, refused by prod and named in the refusal,
   with a check here that prod refuses it and that `config show` reports it. A setting prod would
   honour is an endpoint override in production, which this directory never relies on.
5. **Show it** in `test_stand_ins.py`: it binds an ephemeral loopback port, and a stopped one has
   exited and refuses connections.

Cloud-only checks move to `tests/smoke/cloud/` from V2, where `v2-e12-t07` calls validate-dev as a
reusable workflow and adds them.
