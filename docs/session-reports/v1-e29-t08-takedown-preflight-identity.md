# Session report: v1-e29-t08-takedown-preflight-identity

| | |
|---|---|
| Task | `v1-e29-t08-takedown-preflight-identity` — The takedown preflight refuses the everyday profile before it writes anything |
| Spec | [`plan_specs/v1/e29-cloud-evidence-store/t08-takedown-preflight-identity.yaml`](../../plan_specs/v1/e29-cloud-evidence-store/t08-takedown-preflight-identity.yaml) |
| Epic / release | `v1-e29-cloud-evidence-store` / `v1.1` |
| Branch | `task/v1-e29-t08-takedown-preflight-identity` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The takedown preflight now asks the account which role its credential is signed in as before it
lists or writes anything, and carries on only for the role of this environment's `EvidenceRemoval`
permission set. The everyday profile named in `DEBATE_REMOVAL_PROFILE` by mistake is refused by
what it is, with nothing written, as it was before `v1-e29-t06`. A takedown profile the AWS config
lacks is now the preflight's own refusal, so its message says nothing was deleted (the PM's ac5).

**The Goal stays `InProgress`.** Two parts are operator-run and NOT RUN: ac3's count of leftover
probes in dev and prod, and ac4's `terraform plan`. Everything a session can close is closed, so
this merges with `--partial`.

Look at these first:

1. **What is proven and what is not** (its own section below). The tests prove what the
   application does with an answer about who the caller is. That AWS gives the real profiles the
   answers the tests stub is not proven here. I tried to read it from the account, read-only, and
   the SSO session had expired.
2. **Deviation 1**: `tests/smoke` and `tests/fixtures` are outside `constraints.packages` and had
   to change.
3. **Decision 5**: naming the wrong profile now exits 1. Before `v1-e29-t06` it exited 3.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `preflight-identity` — The preflight checks the caller first | Done, except the two operator-run parts | The identity check, its tests, the ac5 wrap, the probe clean-up section and the grant comment are committed. Its criterion passes: 213 passed. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — the preflight's first step refuses a caller that is not the takedown role, before any write, by test with a stubbed identity; `[everyday]` restored to its meaning and passes | PASS | Red at `76c9d86`, green from `9c96c3d`: see *Red, then green*. `uv run pytest --no-cov -n 0 -v packages/debate_core/tests/application/caselist/test_unsuppress_and_removal_profile.py -k without_delete_rights` → `[everyday] PASSED`, `[cannot_delete] PASSED` |
| ac2 — a preflight run with the takedown role behaves as today, by test | PASS | `TestTheTakedownRole` (6 tests) in `test_takedown_preflight_identity.py`: asked once, first, then list, write, list, delete, list, and no probe left. Every earlier removal test passes unchanged in behaviour: node criterion below, 213 passed |
| ac3 — the removal runbook says how to delete a probe a previous preflight left; the report says whether any exist in dev or prod by an operator-run listing (counts only) | **Runbook: PASS. Counts: NOT RUN** | New section *A probe a preflight left behind* in `docs/runbooks/caselist-removal.md`. Its delete loop was run in zsh against a stubbed `aws`: it deleted the two keys under `preflight/` and skipped the suppression list and a `None` row. Whether any probe exists in dev or prod is **not known**: Operator follow-up 1. It needs a signed-in session, and the kickoff leaves it to the operator |
| ac4 — the comment in `operator_access.tf` and `docs/runbooks/evidence-store.md` name both uses of the listing grant; the comment change is docs-only, and `terraform plan` shows no change (operator-run) | **Comments and runbook: PASS. Plan: NOT RUN** | `diff <(git show origin/dev:infrastructure/modules/evidence_bucket/operator_access.tf \| grep -v '^[[:space:]]*#') <(grep -v '^[[:space:]]*#' infrastructure/modules/evidence_bucket/operator_access.tf)` → no output: the file is identical once whole-line comments are removed. `terraform fmt -check` clean; `terraform validate` and `terraform test` in the module → `Success! 11 passed, 0 failed.` The plan against the real state is Operator follow-up 3 |
| ac5 (added by the PM, 2026-10-11) — a takedown whose profile is missing from the AWS config is wrapped in `TakedownPreflightFailed`, says nothing was deleted, exit stays 1; shown failing first with `caselist remove --execute` | PASS | Red at `76c9d86`, green from `9c96c3d`: see *Red, then green*. `uv run pytest --no-cov -q packages/debate_cli/tests/test_missing_profile_and_missing_grant.py` → 22 passed |
| Node criterion — `uv run pytest packages/debate_core/tests/application -k "preflight or removal"` | PASS | `213 passed in 21.12s` |
| Whole suite, in three parts, at `63f7211` (the last commit that changes code or tests) | PASS | `uv run --frozen pytest packages/debate_core/tests` → 3874 passed, 49 s. `uv run --frozen pytest packages/debate_cli/tests` → 509 passed, 25 s. `uv run --frozen pytest packages/debate_api/tests packages/debate_workers/tests tests` → 1283 passed, 1 skipped, 1 warning, 64 s. The skip (`tests/evals/parser`, files not yet corrected by a person) and the warning (the smoke harness's own test that a socket is blocked) are on `dev` too |
| Static checks | PASS | `uv run pyright` → 0 errors. `uv run ruff check .` and `ruff format --check .` clean. `uv run lint-imports` → 12 kept, 0 broken. `scripts/check_thin_handlers.py`, `check_command_blocks.py`, `check_links.py` OK. `uv run scripts/validate_specs.py` → OK |

`origin/dev` did not move during the session (`d01d4ac` at the start and at the end), so no sync
was needed.

## The check, and why this one

**`sts:GetCallerIdentity`, then the role's name compared with the takedown permission set's.**

The preflight asks a new port, `CallerIdentity.assumed_role_name()`, carried on `TakedownAccess`.
The AWS implementation, `StsCallerIdentity` in `debate_core.integrations.s3`, calls
`GetCallerIdentity` and returns the name of the assumed role and nothing else. The application
reads the permission set out of that name and compares it with
`takedown_permission_set(environment)`: `DebateDevEvidenceRemoval` in dev,
`DebateProdEvidenceRemoval` in prod. Those are the names `operator_access.tf` defines.

I looked for a better check and did not find one. The requirement is a step only the takedown
role passes that writes nothing. By the two policies' text:

| What the takedown set is granted | Does the everyday set have it too? |
|---|---|
| `s3:ListBucketVersions` under the removable prefixes | Yes, since `v1-e29-t06`. This is the step that stopped working |
| `s3:GetObjectVersion` under the removable prefixes | Yes, on every object |
| `s3:GetObject`, `s3:PutObject` under `manifests/_suppression/` | Yes, on every object |
| `kms:Decrypt`, `kms:GenerateDataKey` | Yes |
| `s3:DeleteObject`, `s3:DeleteObjectVersion` | **No.** The only difference, and both are deletes |

So no read tells the two apart, and changing a grant to make one do so is forbidden here. The
alternatives I rejected:

* **Try a delete that removes nothing**, such as a version id that does not exist. It tests the
  real grant, which a name does not. But it is a delete call, I could not confirm without making
  one what S3 answers for a version that is not there, and an administrator's role would pass it.
* **Require a call the takedown set is refused**, such as `ListBucket`. It shows the caller is not
  the everyday role. It does not show it is the takedown role.
* **Read `sso_role_name` from the AWS config.** No network, but it is what the config claims, not
  what the account says, and it means reading the operator's config.

`GetCallerIdentity` needs no grant, AWS answers it even under an explicit deny, and it changes
nothing. Comparing names also refuses an administrator's role, which a capability probe would let
through. It is the same check the runbook already has the operator do by eye in
`evidence-store.md` step 4.

## What is proven by test, and what rests on the policy's text or on AWS

Moto does not enforce IAM. Every bucket in these tests lets any caller do anything.

**Proven by test:**

* Given a caller that is not the takedown role, the preflight stops with nothing listed and
  nothing written. The stores in those tests are fully able, and a journal shows no call reached
  them after the question. Eleven kinds of wrong caller, `unsuppress` included.
* Given the takedown role, the preflight asks once, first, and then goes as it did.
* An expired session, or an account that does not answer, stops at the question and is never
  taken for a pass.
* The STS adapter returns the role's name from what moto's STS answers for an assumed role,
  including a role kept under a path, and `None` for a user. Moto answers in the AWS shape.
* Through the real composition root and the real adapter on moto: `caselist remove --execute`
  with the everyday profile in `DEBATE_REMOVAL_PROFILE` exits 1 with the bucket and this machine
  unchanged, and with the takedown profile it runs. In those tests each profile's credentials are
  ones moto issued for a role named the Identity Center way.
* The name the application expects equals the name `operator_access.tf` builds. A test reads the
  file.

**Not proven by test:**

* **That AWS names the real roles the way the tests name theirs:**
  `AWSReservedSSO_<permission set>_<suffix>`. This is the load-bearing assumption. It rests on
  AWS's documented naming and on `evidence-store.md` step 4, whose success line is two ARNs naming
  `AWSReservedSSO_DebateDevEvidenceOperator` and `AWSReservedSSO_DebateDevEvidenceRemoval`. I
  tried to read the shape from the account with a read-only `aws sts get-caller-identity` for the
  four evidence profiles, printing only a masked shape. All four failed: the SSO token had
  expired. So it is **unmeasured**. Operator follow-up 4 measures it in about a minute. If the
  shape differs, the check fails closed: the takedown profile is refused too, with nothing
  written, and `evidence-store.md` *If something is wrong* now says what to send.
* **That the everyday profile can list, write and not delete.** Read from the operator policy's
  text, as the spec says. The restored `[everyday]` test stubs exactly that.
* **That the takedown role's grants work.** Unchanged by this task; the probe still tests them.

Operator follow-up 5 would turn the first two into an observation in dev, safely.

## Red, then green

The failing tests were committed on their own at `76c9d86`, before the implementation at
`9c96c3d`. Every failure is an assertion in a test that ran; none is a collection or import error.

```bash
uv run pytest --no-cov -q -n 0 packages/debate_core/tests/application/caselist/test_unsuppress_and_removal_profile.py packages/debate_core/tests/application/caselist/test_takedown_preflight_identity.py packages/debate_cli/tests/test_missing_profile_and_missing_grant.py tests/smoke/test_caselist_remove_smoke.py
```

| | At `76c9d86` (tests only) | At `9c96c3d` (implementation) |
|---|---|---|
| Result | **27 failed, 51 passed** | **78 passed** |

At the final commit the same command gives 95 passed: the 17 tests of the name itself were added
with the implementation.

**ac1, red (21 of the 27).**

* `[everyday]`: `AssertionError: the everyday profile is stopped before anything is written` /
  `assert 'probe' not in '… nothing was deleted; its probe object was left at
  manifests/_suppression/preflight/3a4d90d4f8664e6888f528efc0f23fe6.txt'`. That is the defect as
  the spec describes it: listed, wrote the probe, refused at the delete.
* `test_it_is_refused_before_anything_is_listed_or_written`, all 11 callers: `Failed: DID NOT
  RAISE TakedownPreflightFailed`. On moto the wrong caller ran the whole removal.
* Four more at the service: the message, a second attempt, another environment's role,
  `unsuppress`. Two for a credential that cannot be asked.
* At the CLI and in the smoke suite: `assert 0 == <ExitCode.DOMAIN_FAILURE: 1>` with
  `'status': 'ok' … 'applied': True`. `caselist remove --execute` with the everyday profile named
  completed.

**ac2, red (2).** `test_it_is_asked_who_it_is_first_and_once_and_then_the_probe_goes_as_before`:
`At index 0 diff: 'versions.list_versions' != 'caller.assumed_role_name'`. The other counted zero
questions. The "as today" half was green before and after, as it should be: `[cannot_delete]`,
the four suffix cases, the smoke suite's `--execute` runs.

**ac5, red (4).** Shown failing first with `caselist remove --execute` and
`DEBATE_REMOVAL_PROFILE` naming a profile the config lacks, as the criterion asks:

* CLI (`test_the_removal_profile_naming_one_exits_one_names_its_variable_and_changes_nothing`)
  and smoke: `AssertionError: assert 'STORE_PROFILE_NOT_CONFIGURED' == 'TAKEDOWN_PREFLIGHT_FAILED'`.
* Service: `debate_core.application.errors.StoreProfileNotConfigured: AWS profile
  'debate-dev-evidence-removal-typo', named by DEBATE_REMOVAL_PROFILE, is not defined …` raised
  bare, where `TakedownPreflightFailed` was expected. Twice: `execute` and `unsuppress`.

**Green.** What an operator now reads (`--json`, the `error` object's `message` and `hint`):

```
the takedown profile debate-dev-evidence could not show it is signed in as DebateDevEvidenceRemoval
(NOT_THE_TAKEDOWN_ROLE), so it cannot carry out a removal: it is signed in as
DebateDevEvidenceOperator, so DEBATE_REMOVAL_PROFILE does not name this environment's
EvidenceRemoval profile; nothing was deleted

set DEBATE_REMOVAL_PROFILE to debate-dev-evidence-removal, the profile for DebateDevEvidenceRemoval;
the one it names is signed in, so logging in again changes nothing. docs/runbooks/evidence-store.md
lists the evidence profiles
```

```
the takedown profile debate-dev-evidence-removal-typo could not start an AWS session
(STORE_PROFILE_NOT_CONFIGURED), so it cannot carry out a removal: DEBATE_REMOVAL_PROFILE must name
a profile this machine's AWS config defines; nothing was deleted
```

## Mutation results

25 mutants, one at a time, each against `test_takedown_preflight_identity.py`,
`test_unsuppress_and_removal_profile.py`, `test_sts_caller_identity.py` and
`test_missing_profile_and_missing_grant.py`: 91 tests, and 92 for the last adapter mutant, which was
run after one more adapter test was added. **25 caught, 0 survived, 0 errored.** Every
mutant compiled, and every catch is a test that ran and failed. Each run had a new, empty
`HYPOTHESIS_STORAGE_DIRECTORY`; none of these tests uses Hypothesis. The tree was committed before
the first mutant, each file was restored from the bytes read before mutating, and `git status`
was empty after every batch.

The last column is the restored `[everyday]` test on its own.

| Mutant | Result | `[everyday]` |
|---|---|---|
| **A wrong role passes** | | |
| A set whose name begins with the takedown's passes (`startswith`) | 2 failed | passes |
| Any permission set's role passes, the everyday role included | 13 failed | **fails** |
| The set's name anywhere in the role name passes | 6 failed | passes |
| Another environment's takedown role passes | 1 failed | passes |
| No role at all passes | 1 failed | passes |
| The set's name in another case passes | 1 failed | passes |
| The role name is matched from its start only | 2 failed | passes |
| The role name is searched, not matched whole | 4 failed | passes |
| A role name with no suffix passes | 2 failed | passes |
| **The check skipped** | | |
| Asks, and ignores the answer | 18 failed | **fails** |
| Never asks (the code before this task) | 22 failed | **fails** |
| A refused credential is remembered as passed for the next attempt | 1 failed | passes |
| **The check in the wrong place** | | |
| After the first listing | 18 failed | passes |
| After the probe is written | 19 failed | **fails** |
| After the probe is deleted | 19 failed | **fails** |
| **The wrap in ac5** | | |
| A missing profile is not wrapped | 3 failed | passes |
| Wrapped, but the message asks whether the session is signed in | 2 failed | passes |
| Wrapped, but the missing profile is not named | 2 failed | passes |
| **What the refusal says** | | |
| It carries the role's full name, suffix and all | 2 failed | passes |
| **The adapter** | | |
| Returns the session's name, not the role's | 8 failed | passes |
| Returns the whole identifier | 8 failed | passes |
| Reads a role out of anything that mentions `assumed-role` | 1 failed | passes |
| A session with no session name is a role | 1 failed | passes |
| The STS client is built without the profile | 5 failed | passes |
| **The wiring** | | |
| The identity is asked of the everyday profile, not the takedown's | 2 failed | passes |

Two things to read from the last column:

* `[everyday]` fails for each mutant that lets the everyday profile reach the probe, which is its
  meaning. It **passes with the check moved after the first listing**, because a listing writes
  nothing and that test asserts nothing was written. The order is held by the tests that
  journal every call: 18 other tests fail for that mutant.
* Several mutants are caught by one test. Each of those is one named case in the table of wrong
  callers, so the case is the thing to keep.

## Files changed

**`packages/debate_core/src/debate_core/application`** — the check.

* `ports/caller_identity.py` (new): the `CallerIdentity` port, one method.
* `caselist/removal_service.py`: `TakedownAccess.caller`; `preflight(access, *, environment)`
  asks first; `takedown_permission_set`, `permission_set_of`, `NotTheTakedownRole`;
  `_authorised` wraps `StoreProfileNotConfigured` (ac5); `TakedownPreflightFailed`'s message says
  what to correct for those two causes; module and function docstrings say what happens now.

**`packages/debate_core/src/debate_core/integrations/s3`** — boto3 and STS stay here.

* `caller_identity.py` (new): `StsCallerIdentity`.
* `client.py`: `build_sts_client`, built from a profile as `build_s3_client` is.
* `__init__.py`: exports.

**`packages/debate_cli`** — wiring and words.

* `container.py`: the takedown access is built with `StsCallerIdentity` for the takedown profile.
* `commands/caselist_remove.py`: the *Exit codes* docstring. It still said a missing profile exits
  3, which `v1-e29-t07` had changed.
* `README.md`: the exit-code table's row for 1.

**Tests.**

* `packages/debate_core/tests/application/caselist/test_takedown_preflight_identity.py` (new, 42).
* `…/test_unsuppress_and_removal_profile.py`: `[everyday]` restored.
* `…/conftest.py`: `SignedInAs`, the identity stubbed at the port, and two made-up role names.
  `test_removal_service.py`, `test_removal_residue.py`, `test_removal_later_uploads_plan.py`:
  hand-built takedowns carry the caller.
* `packages/debate_core/tests/integrations/s3/test_sts_caller_identity.py` (new, 18).
* `packages/debate_cli/tests/test_missing_profile_and_missing_grant.py`: ac5 at the CLI, and three
  tests of a takedown that names the everyday profile.
* `tests/fixtures/identity_center_roles.py` (new), `tests/smoke/test_caselist_remove_smoke.py`,
  `tests/smoke/test_caselist_pull.py`, `tests/smoke/README.md`: Deviation 1.

**`infrastructure/modules/evidence_bucket`** — comments only.

* `operator_access.tf`: both uses of the listing grant, why the Sid keeps its name, and that the
  removal set's name is read by the application.
* `README.md`: the same sentence in the permission table.

**`docs/runbooks`.**

* `caselist-removal.md`: step 5 describes the two preflight steps; new section *A probe a
  preflight left behind*; a reference.
* `evidence-store.md`: both uses of the grant; what `--execute` checks; a troubleshooting entry
  for `NOT_THE_TAKEDOWN_ROLE` with the takedown profile.

**`plan_specs`** — ac5, added verbatim as the first commit (`253be3a`).

## Deviations from the spec

1. **`tests/smoke` and `tests/fixtures` are not in `constraints.packages`, and I changed both.**
   The smoke suite runs `caselist remove --execute` through the real composition root, so with
   this change it asks moto's STS who each profile is. Without a role behind each profile every
   `--execute` in `test_caselist_remove_smoke.py` and `test_caselist_pull.py` would be refused.
   Their `bucket` fixtures now sign both profiles in as roles (two lines each), through one shared
   helper, `tests/fixtures/identity_center_roles.py`. Working agreement 5 also asks for a smoke
   check on a user-facing change, so there is one new smoke test (the everyday profile named for a
   takedown) and one updated (the missing profile, for ac5). The spec's package list wants
   `tests/smoke` and `tests/fixtures` added.
2. **One test table holds identifier-shaped strings.** `test_sts_caller_identity.py` feeds the
   adapter nine strings shaped like what STS returns, with the word `ACCOUNT` where an account
   goes, to show that only an assumed role yields a name. They hold no account id and name no real
   role. The forbidden list says no role ARN in tests, and I read that as no real identifier. If it
   is meant to cover the shape as well, the table is one deletion and the moto-backed cases
   remain; the four adapter mutants would then need another home. Your ruling.
3. **The session ran two things a stricter reading would hand over.** Both are read-only and took
   seconds. (a) Four `aws sts get-caller-identity` calls, to measure the role-name shape before
   relying on it (working agreement 7); all four failed on the expired token and nothing was
   learned. (b) `terraform init -backend=false`, `validate` and `test` in the module, 16 s, no
   credentials, no state. The plan and the bucket listings were left alone, as the kickoff says.
4. **The envelope for a missing takedown profile changed**, as ac5 asks: `error.code` is
   `TAKEDOWN_PREFLIGHT_FAILED` where it was `STORE_PROFILE_NOT_CONFIGURED`, and `error.details` is
   `{"profile", "step"}` where it was `{"profile", "setting"}`. The setting is still named in the
   message and the hint. Two existing tests asserted the old code and were updated, one of them in
   `tests/smoke`. `caselist remove` without `--execute`, and every other command, still report the
   bare error.

## Decisions and assumptions

1. **The check is the caller's identity.** See *The check, and why this one*.
2. **The expected name is derived from the environment, not configured.**
   `takedown_permission_set("dev")` is `DebateDevEvidenceRemoval`. A setting would be one more
   thing to mistype, and a check an operator can point at the everyday role is a weaker check. The
   cost is that the name is written twice, in Terraform and in Python. A test reads
   `operator_access.tf` and fails if they differ, and a comment beside the Terraform local says so.
3. **The suffix is matched by shape, not by length.** The account chooses it. I believe it is 16
   hexadecimal characters, but I could not measure it, so the rule is "letters and digits, at least
   one". The set's name must match exactly, with `AWSReservedSSO_` before it and one `_` after.
4. **A name comparison guards against a mistake, not against an administrator.** Someone who can
   create roles could name one in this shape and pass. They could also delete evidence directly.
   The spec's concern is the wrong profile named by accident, and that is what this refuses.
5. **The wrong profile exits 1, where before `v1-e29-t06` it exited 3.** Then it was an
   `AccessDenied` on the listing, which is on the retryable list. Now the cause is
   `NotTheTakedownRole`, which no retry cures, so `exit_code_for` gives `DOMAIN_FAILURE`. This
   follows `v1-e29-t07`'s reasoning for a missing profile. An expired session at the question is
   still 3, with the login line. The spec says "as it did before the listing grant" about nothing
   being written, and does not name an exit code; say if you want 3.
6. **The refusal names permission sets, not role names.** `DebateDevEvidenceOperator`, without the
   prefix or the account's suffix. A hand-made role is shown by its own name. The adapter drops the
   session's name, which for an Identity Center session is usually an email address, and never
   reads the account or the user id.
7. **The S3 client and the STS client are two sessions built from one profile name.** They read
   the same entry of the same AWS config, so they are the same role. One shared session would say
   so by construction, but `build_s3_client` returns a client and the adapters take clients, and I
   did not want to widen that in this task. A test builds the adapter from two profile names and
   gets each one's own role.
8. **The first listing stays.** It was the old first step. ac2 says "behaves as today", so the
   takedown role's preflight is the question and then the same five calls.
9. **`[cannot_delete]` is now the takedown role with its delete grant gone.** It used to stand for
   the everyday profile after the grant. That profile is `[everyday]` again. The older stub for a
   profile that cannot list at all is removed: no environment is in that state, and the identity
   check comes first in any case.
10. **ac5's message says what to correct.** The general sentence ends "…and that its session is
    signed in", which contradicts the hint's "logging in changes nothing". For a missing profile
    and for the wrong role the clause is specific. The wrapper also names the missing profile.
11. **The Sid `ListEvidenceObjectVersionsForRemovalPlans` keeps its name.** It names one use of
    two, but renaming it changes the policy, which is forbidden here. The comment says so.
12. **The adapter is in `debate_core.integrations.s3`** although STS is not S3. That is the
    package in the spec's list and the one place boto3 is imported. Its failures go through the
    same translation, and name the bucket the credential was for.
13. **Assumption: a takedown is run by a person with an Identity Center profile.** True in V1. A
    takedown run by a service role would be refused. Follow-up work 2.

## Operator follow-ups

Follow-ups 1 and 4 can be run now, from anywhere. 3 and 5 come after this task merges into `dev`.

1. **ac3: count leftover probes in dev and prod** (expected runtime ~1 min). Where: anywhere.
   Read-only, with the everyday profiles.

   ```bash
   aws sso login --sso-session debate
   aws s3api list-object-versions --profile debate-dev-evidence --bucket debate-dev-evidence-a7508de8 --prefix manifests/_suppression/preflight/ --query '{versions: length(Versions || `[]`), delete_markers: length(DeleteMarkers || `[]`)}' --output json
   aws s3api list-object-versions --profile debate-prod-evidence --bucket debate-prod-evidence-a7508de8 --prefix manifests/_suppression/preflight/ --query '{versions: length(Versions || `[]`), delete_markers: length(DeleteMarkers || `[]`)}' --output json
   ```

   Success looks like: two small JSON objects. `{"versions": 0, "delete_markers": 0}` means none
   was left. Paste both back: those four numbers are what ac3 asks the report to record. An
   `AccessDenied` here would mean the `v1-e29-t06` grant is not what the runbook says; stop and
   send it.

2. **Only if a count is not zero: delete them** (expected runtime ~2 min per environment). Where:
   anywhere. Follow
   [caselist-removal.md, A probe a preflight left behind](../runbooks/caselist-removal.md#a-probe-a-preflight-left-behind):
   the takedown profile, each version by id, and only under `preflight/`. Then run follow-up 1
   again and paste the zeros.

3. **ac4: `terraform plan` shows no change** (expected runtime ~2 min each). Dev first, in the
   `dev-preview` worktree, after this task has merged into `dev`. `-input=false` turns a missing
   `owner.auto.tfvars` into an error instead of a prompt.

   ```bash
   cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/dev-preview
   git fetch origin
   git switch --detach origin/dev
   git log --oneline -1
   grep -c v1-e29-t08 infrastructure/modules/evidence_bucket/operator_access.tf
   test -f infrastructure/envs/dev/owner.auto.tfvars && echo "owner.auto.tfvars present" || echo "owner.auto.tfvars MISSING: stop"
   aws sso login --sso-session debate
   export AWS_PROFILE=debate-admin
   terraform -chdir=infrastructure/envs/dev init -input=false
   terraform -chdir=infrastructure/envs/dev plan -input=false
   unset AWS_PROFILE
   ```

   Success looks like: `grep -c` prints `2` (the new comments are in this checkout),
   `owner.auto.tfvars present`, and the plan ends **`No changes. Your infrastructure matches the
   configuration.`** There is nothing to apply. **Stop and send the plan** if it proposes anything:
   this task changed comments only, so any change is another task's or a stale checkout's.

   Then prod, in the `prod-deploy` worktree on `main`, after the promotion that carries this
   change:

   ```bash
   cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/prod-deploy
   git branch --show-current
   git pull --ff-only
   git log --oneline -1
   grep -c v1-e29-t08 infrastructure/modules/evidence_bucket/operator_access.tf
   test -f infrastructure/envs/prod/owner.auto.tfvars && echo "owner.auto.tfvars present" || echo "owner.auto.tfvars MISSING: stop"
   export AWS_PROFILE=debate-admin
   terraform -chdir=infrastructure/envs/prod init -input=false
   terraform -chdir=infrastructure/envs/prod plan -input=false
   unset AWS_PROFILE
   ```

   Success looks like: `main`, `2`, the file present, and `No changes.` again.

4. **Measure the role-name shape the check relies on** (expected runtime ~1 min). Where: anywhere.
   Read-only. The pipeline prints the role's name with its suffix masked, so what you paste back
   holds nothing of the account.

   ```bash
   aws sso login --sso-session debate
   aws sts get-caller-identity --profile debate-dev-evidence --query Arn --output text | cut -d/ -f2 | sed -E 's/_[A-Za-z0-9]+$/_<letters and digits>/'
   aws sts get-caller-identity --profile debate-dev-evidence-removal --query Arn --output text | cut -d/ -f2 | sed -E 's/_[A-Za-z0-9]+$/_<letters and digits>/'
   aws sts get-caller-identity --profile debate-prod-evidence --query Arn --output text | cut -d/ -f2 | sed -E 's/_[A-Za-z0-9]+$/_<letters and digits>/'
   aws sts get-caller-identity --profile debate-prod-evidence-removal --query Arn --output text | cut -d/ -f2 | sed -E 's/_[A-Za-z0-9]+$/_<letters and digits>/'
   ```

   Success looks like these four lines exactly:

   ```
   AWSReservedSSO_DebateDevEvidenceOperator_<letters and digits>
   AWSReservedSSO_DebateDevEvidenceRemoval_<letters and digits>
   AWSReservedSSO_DebateProdEvidenceOperator_<letters and digits>
   AWSReservedSSO_DebateProdEvidenceRemoval_<letters and digits>
   ```

   A line that still shows a suffix has a character the check does not expect. **Tell me that, and
   do not paste the line**: the takedown profile would be refused, with nothing written, until the
   pattern is corrected. This is worth doing before the next real removal request.

5. **Optional: see the refusal in dev** (expected runtime ~1 min). Where: the `dev-preview`
   worktree, after the merge, on the checkout from follow-up 3. It names the everyday profile for
   a takedown on purpose. The digest is held nowhere. If the check works, nothing is written. If
   it did not, the everyday profile still cannot delete, and the worst outcome is one probe, which
   the last command would show.

   ```bash
   cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/dev-preview
   unset AWS_PROFILE
   DEBATE_ENV=dev DEBATE_REMOVAL_PROFILE=debate-dev-evidence uv run --frozen debate-research caselist remove --source 0000000000000000000000000000000000000000000000000000000000000000 --request RM-2026-99 --reason POLICY --execute
   echo "exit status $?"
   aws s3api list-object-versions --profile debate-dev-evidence --bucket debate-dev-evidence-a7508de8 --prefix manifests/_suppression/preflight/ --query '{versions: length(Versions || `[]`), delete_markers: length(DeleteMarkers || `[]`)}' --output json
   ```

   Success looks like: an error naming `TAKEDOWN_PREFLIGHT_FAILED` and `NOT_THE_TAKEDOWN_ROLE`,
   saying it is signed in as `DebateDevEvidenceOperator` and that nothing was deleted;
   `exit status 1`; and the same counts as follow-up 1. That is ac1 observed against real IAM. The
   takedown role passing the question is seen at the next real takedown, or inferred from
   follow-up 4.

## Follow-up work

1. **The command could remove leftover probes itself** (E29 or E30). A takedown that passes its
   preflight could delete every version under `preflight/` older than its own. The runbook does it
   by hand because ac3 asks for the runbook, and because whether any exist is not yet known.
2. **A takedown by anything but an Identity Center role is refused** (`v2-e35-t05`). The V2
   takedown flow built on this suppression list will need `takedown_permission_set` to grow, or a
   second way to say which role may delete.
3. **`doctor` could say which role each configured profile is** (E29). The same port answers it,
   and it would catch a wrong `sso_role_name` before a removal request arrives. It also bears on
   `v1-e29-t07`'s first follow-up, a misspelt profile failing the weekly agent silently.
4. **`_denial_hint` gives the "listing is granted per prefix" hint to any `AccessDenied` with no
   key** (E29). `GetCallerIdentity` now goes through that translation with no key. AWS does not
   deny that call, so it is not reachable today.
5. **`error.details` of a wrapped store failure drops the cause's own details** (E30). For ac5 the
   setting's name is in the message and the hint but no longer a field. If a script wants it,
   `TakedownPreflightFailed` could carry the cause's code as an attribute.
6. **`v1-e29-t07`'s other follow-ups are untouched**: the weekly agent and a misspelt profile,
   `caselist_sync.py`'s docstrings (after `v1-e34-t19`), and the services that re-raise a session
   error per run. This task closed only its second, the wrap.
7. **`unsuppress` is not in step 5 of the runbook's description of the preflight.** It has the
   same preflight and is tested the same way; the runbook's unsuppress section does not say so.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
