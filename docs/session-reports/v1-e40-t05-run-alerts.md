# Session report: v1-e40-t05-run-alerts

| | |
|---|---|
| Task | `v1-e40-t05-run-alerts` — A failed or late cloud run emails the coach |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t05-run-alerts.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t05-run-alerts.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t05-run-alerts` |
| Session status | PARTIAL: everything a session can build and test is done; ac1's operator half (one test alert in dev, received) follows the merge, so the Goal stays `InProgress` <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The alerts are built: the SNS topic `debate-<env>-caselist-run-alerts` with the coach's email
subscription; the `sns` kind of `caselist.notifier` and its adapter in `debate_core.integrations.sns`,
built under t02's rules (one small boto3 client, no endpoint override, nothing about the message in a
log); EventBridge rules on a run or login task that stopped non-zero or never started; the
`RunsRecorded` metric filter on the run's log group and the late-run alarm, whose email stays off
behind `late_run_alarm_actions_enabled` until the cutover's first recorded run; a dead-letter queue
on each schedule and one alarm over both; the CloudTrail rules of ac2; the run role's `sns:Publish`
on that one topic, in its own `caselist-alerts` policy under `aws_iam_role_policies_exclusive.run`;
and `caselist.notifier = sns` with the topic in both tasks' environments. `RUN_TERMINATED` and
`RUN_LOCK_LOST` reach the coach as failed runs with their codes, and a stubbed run with a sentinel
school, team code, file name and card text planted in its records emails none of them. Terraform:
37 module tests (27 before, 2 of them updated), 28 of 28 mutants caught; Python: 19 of 19 mutants
caught, after recorded red runs.

**Look first at:** the PM questions at the end. (1) The dev apply needs a new image, because an image
without this task refuses `caselist.notifier = sns` and the Wednesday 03:00 login would fail at
startup. (2) That apply would also carry `v1-e40-t04`'s bucket-mode change into the run task
definition, which the cutover's step 8 was to apply after the seed. (3) The container wiring and
the import-contract lists sit outside this task's `constraints.packages` (a Deviation).

**Why this task started before t03 is `Succeeded`** (the PM's `--force`): `v1-e40-t03` is merged
`--partial`, and its Goal stays `InProgress` only for operator steps that happen at `v1-e40-t06`'s
cutover. This task builds on t03's merged module, so starting it was not premature.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `alerts` — Run alerts | Done (its criterion PASS) | Terraform in `infrastructure/modules/caselist_run` and both roots; the `sns` notifier and its settings; the runbook. ac1's operator half follows the merge |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — a failed run, a missed schedule and a failed login each produce an alert, by Terraform tests and a stubbed run | PASS | `terraform -chdir=infrastructure/modules/caselist_run test` → `Success! 37 passed, 0 failed.` The runs `a_run_or_a_login_that_stops_non_zero_emails_the_coach`, `both_tasks_send_their_own_failures_to_the_topic`, `a_week_with_no_recorded_run_alarms_and_emails_once_the_cutover_turns_it_on`, `late_run_alarm_actions_enabled_turns_its_email_on`, `a_schedule_that_cannot_start_its_task_emails_the_coach` and `the_alert_topic_emails_the_coach_and_admits_only_these_rules_and_alarms`. The stubbed runs: `pytest packages/debate_core/tests/integrations/sns` → `25 passed`; `test_alerts_name_no_school.py` takes a failed run, a run stopped by an error quoting a disclosure path, `RUN_TERMINATED`, `RUN_LOCK_LOST` and a refused login through the real `SyncRunMonitor` / `ScheduledLogin` to the real `SnsNotifier`, whose botocore client is answered in-process, and checks each publish as SNS would receive it |
| ac1 — the operator triggers one alert in dev and receives it | NOT RUN | Needs the merge, a release containing it, and AWS. Operator follow-ups A to H below ([caselist-run-alerts.md](../runbooks/caselist-run-alerts.md), steps 1 to 6) |
| ac2 — Terraform's tests show the CloudTrail rules match a change to the credentials' key or resource policies, the login role or its task definition, and a read or refused read of the password by any principal but the login role, each with the topic as target | PASS | Same `terraform test` run: `the_credential_rules_match_each_change_of_who_may_read_the_password` (each rule's whole pattern, state `ENABLED`, target the topic) and `a_read_of_the_password_by_anyone_but_the_login_role_emails_the_coach` (the whole pattern; no `errorCode` condition, so a refused read matches; state `ENABLED_WITH_ALL_CLOUDTRAIL_MANAGEMENT_EVENTS`; the exclusion exactly the login role's task sessions; target the topic). Mutants M01 to M11 and M24 to M28 below. Whether EventBridge itself matches with these patterns is AWS's to say: follow-up G checks each against AWS's matcher |
| Node `alerts` — Terraform checks pass (`bash scripts/terraform_checks.sh`) | PASS | Run offline against the main checkout's provider mirror (`TF_CLI_CONFIG_FILE=<mirror rc> bash scripts/terraform_checks.sh`) → `All Terraform checks passed.`, 25 s, after the last change; no lock file changed |

### Red runs

* **The adapter**, commit `99b9e5c`: the tests against a skeleton with the real signatures that
  publishes the notification's text as given and refuses nothing → `20 failed, 5 passed`. The 20 fail
  on the missing behaviour: the subject's environment, ASCII and length; the message layout; the
  topic's region; the endpoint override; the client built once; bounded timeouts
  (`KeyError: 'total_max_attempts'`); a bad topic ARN (`DID NOT RAISE ValueError`); a refused,
  unreachable or unsigned publish raised (`AuthorizationErrorException`, `EndpointConnectionError`,
  `NoCredentialsError`, `RuntimeError`); the body in botocore's DEBUG log. The 5 that pass: one
  publish to the topic (the skeleton publishes), the botocore control, and the three stopped-run
  sentinel cases. Those three hold because `notifications_for` (application layer, not this task)
  builds an alert from codes and never from a message; mutants P18 and P19 show the sentinel test
  catches it the moment it does not.
* **The settings**, against the start commit's source (`git archive ed1ddc2 packages/debate_core/src`
  first on `PYTHONPATH`, its `settings.py` printed as the one imported) → `7 failed`; against this
  branch → `7 passed`. The four topic-shape cases first passed at the start commit for the wrong
  reason: there any `alert_topic_arn` is refused as an unknown key, and that message names the
  setting too. Their match is now the pattern refusal itself.

### Mutants

Terraform, `terraform test` per mutant (no Hypothesis involved). The PM's four are M01 to M03 (a
rule's state), M04 to M06 (the target topic), M07 to M11 (the GetSecretValue principal exclusion) and
M12 to M15 (the run role's grant beyond its one topic). Every one is a clean catch: one or two runs
fail, `36 passed` or `35 passed`, nothing skipped, no panic.

| # | Mutant | Caught by |
|---|---|---|
| M01 | password-read rule state `ENABLED` (drops read-only events) | `a_read_of_the_password_...` |
| M02 | the four write rules `DISABLED` | `the_credential_rules_match_...` |
| M03 | both task-state rules `DISABLED` | `a_run_or_a_login_that_stops_non_zero_...` |
| M04 | password-read target another topic | `a_read_of_the_password_...` |
| M05 | write rules' targets another topic | `the_credential_rules_match_...` |
| M06 | task-state targets another topic | `a_run_or_a_login_that_stops_non_zero_...` |
| M07 | exclusion names the login role's IAM ARN, not its sessions (matches every weekly read) | `a_read_of_the_password_...` |
| M08 | exclusion is the run role | `a_read_of_the_password_...` |
| M09 | exclusion widened to every assumed role | `a_read_of_the_password_...` |
| M10 | exclusion removed | `a_read_of_the_password_...` |
| M11 | only refused reads matched | `a_read_of_the_password_...` |
| M12 | run role publishes to `*` | the run role's `...nothing_more`, and the topic run |
| M13 | run role publishes to every topic in the account | the same two |
| M14 | run role gains `sns:*` on the topic | the same two |
| M15 | run role's publish also on a second topic | the same two |
| M16 | a task that never started is not matched | `a_run_or_a_login_that_stops_non_zero_...` |
| M17 | the family prefix loses its revision colon | `a_run_or_a_login_that_stops_non_zero_...` |
| M18 | late alarm: missing data not breaching | `a_week_with_no_recorded_run_...` |
| M19 | late alarm's email on from the start | `a_week_with_no_recorded_run_...` |
| M20 | metric filter reads the login's log group | `a_week_with_no_recorded_run_...` |
| M21 | metric filter counts dry runs | `a_week_with_no_recorded_run_...` |
| M22 | the run schedule's dead letters go to the login's queue | `a_schedule_that_cannot_start_...` |
| M23 | the login scheduler may send to any queue | `a_schedule_that_cannot_start_...` |
| M24 | the topic policy loses the dead-letter alarm | `the_alert_topic_emails_the_coach_...` |
| M25 | the login task does not set the sns notifier | `both_tasks_send_their_own_failures_...` |
| M26 | key rule drops `PutKeyPolicy` | `the_credential_rules_match_...` |
| M27 | secrets rule watches the password only | `the_credential_rules_match_...` |
| M28 | login-task rule exempts every assumed role from `RunTask` | `the_credential_rules_match_...` |

**A check that first passed through a crash.** On the first mutation pass, seven of these (M02, M03,
M05, M06, M16, M17, M24) failed the right run and then made Terraform 1.16 panic (`value has marks,
so it cannot be serialized as JSON`) while rendering the failure, instead of printing its message.
An assertion that iterates a whole `for_each` map of event rules or targets refers to their
deprecated `is_enabled` attribute, and the JSON diagnostic renderer cannot marshal a deprecation
mark. Under agreement 8 a crash is not a clean catch, so the assertions now name each instance by
its literal key (commit `ffa220a`), and the whole table above was rerun after that change.

Python, the tests of the sns directory, the settings and the container (34) per mutant, each with
`HYPOTHESIS_STORAGE_DIRECTORY` a new, empty directory (agreement 8). 19 of 19 caught, each by the
test aimed at it, no errors:

| # | Mutant | Caught by |
|---|---|---|
| P01 | a publish not under `quiet_wire_log` | both "nothing published reaches a log" tests |
| P02 | the endpoint override honoured | `test_an_endpoint_override_..._is_ignored` |
| P03 | the region always us-east-1 | `test_the_region_is_the_topics` |
| P04 | the subject keeps non-ASCII and control characters | the subject property |
| P05 | the subject not shortened | the property, and the long-title test |
| P06 | the subject cut at 100, one too many | the property, and the long-title test |
| P07 | the subject without the environment | four, the two sentinel tests among them |
| P08 | the message drops the hint | the message layout test |
| P09 | a refused publish raises | the refused-publish tests |
| P10 | a client that cannot be built raises | `test_a_client_that_cannot_be_built_...` |
| P11 | the client built for every notification | `test_the_client_is_built_once_...` |
| P12 | a refusal logged with the message | `test_nothing_published_reaches_a_log_when_the_publish_is_refused` |
| P13 | botocore's five attempts | `test_the_client_gives_up_inside_the_two_minutes_...` |
| P14 | the topic ARN not checked | the three bad-topic cases |
| P15 | settings: `sns` with no topic accepted | `test_sns_with_no_topic_is_refused_...` |
| P16 | settings: any topic string accepted | the four topic-shape cases |
| P17 | container: `sns` falls through to macOS or none | `test_sns_builds_the_alert_topics_notifier` |
| P18 | application: a failed stage's alert quotes its reasons | the failed-run sentinel test |
| P19 | application: a stopped run's alert quotes its error message | the disclosure-path sentinel test |

P19 is the sentinel test doing its job: the record's error message has been through `redact()`,
which removes the disclosure path, but `SlowDown on Quillfeather Academy` is not path-shaped and
would have reached the coach.

**The property's inputs** (`--hypothesis-show-statistics`, fresh database): plain `st.text()` made a
title too long for a subject 0.33% of the time, so the strategy is half short and half past the
limit: 48% too long, 94% with a character outside printable ASCII.

### Before the report

| Check | Result |
|---|---|
| `uv run scripts/affected_tests.py` (before the `pyproject.toml` edit) | `333 of 481 test files (69.2%) chosen in 6.0 s from 29 changed files`: `settings.py` reaches every test through the root conftest. Past the two-minute line, so not run; left to the PR's `ci` (agreement 10) |
| `uv run scripts/affected_tests.py` (after it) | `The whole selection is affected: pyproject.toml is shared test ground.` Nothing run, as agreement 10 says |
| The always-run list, the docs checks and the changed areas' tests, one run under `perl -e 'alarm 115'`: `tests/architecture tests/specs tests/docs`, `test_check_command_blocks.py`, `test_docs_index.py`, `test_caselist_run_deploy.py`, debate_cli's `test_app.py`, `test_help_rendering.py`, `test_installation.py`, `test_doctor.py`, `test_sync_notifier_kinds.py`, `test_pull_refused_before_the_bucket_is_built.py`, the sns and secrets_manager directories, the three settings test files, `test_sync_runs.py` | `717 passed in 22.02s` |
| `settings.py`'s test directory, `packages/debate_core/tests/application`, under `alarm 115` | `3748 passed in 96.58s` |
| `packages/debate_cli/tests`, once, after the container change | `1014 passed in 201.63s`. Over the two-minute line: the machine's load average was about 10 at the time (my notes put this directory at about 40 s). Every later run had a hard limit and a load check first |
| The sns and secrets_manager suites in one process, both orders (`-n 0 -p no:randomly`; both set botocore's wire loggers and the quiet filter) | `47 passed`, `47 passed` |
| `uv run --frozen ruff format --check .` / `ruff check .` | `1328 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright packages/debate_core packages/debate_cli` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 16 kept, 0 broken.` With `import httpx` planted in the adapter: `The HTTP client stays inside the adapters that talk HTTP BROKEN ... debate_core.integrations.sns is not allowed to import httpx` |
| `uv run --frozen python scripts/check_thin_handlers.py` | `OK: 54 CLI command and API route handlers within 25 statements` |
| `uv run scripts/validate_specs.py` | `OK: 453 files, 40 epics, 391 tasks, 22 releases` |
| `uv run --frozen python scripts/docs_index.py --check-descriptions` | `All 48 indexed documents under docs/ have a description` |
| `uv run --frozen python scripts/check_command_blocks.py --base origin/dev` | `OK: no '#' comments in 456 shell code blocks in 156 Markdown files (1 session reports changed since origin/dev)` |
| `bash scripts/terraform_checks.sh` (offline, provider mirror) | `All Terraform checks passed.` |
| The runbook's plan check, on synthetic plans | The expected shape → `PLAN OK: 25 to add, 5 to change, 2 to destroy; ...`; the same with bucket mode newly added → `PLAN OK` and `NOTE for the PM: the run's revision also gains DEBATE_CASELIST__RUN_STATE=bucket ...`; an account assignment destroyed, the run schedule enabled, the password rule `ENABLED`, the login without the notifier, an image other than the digest, a change outside the module, the late alarm's email on → each `PLAN STOP` naming it |

## Files changed

* **`infrastructure/modules/caselist_run/`**: `alerts.tf` (new: the topic, its policy and the
  subscription, the task-state rules, the metric filter and the two alarms, the queues, the CloudTrail
  rules); `roles.tf` (the run role's `caselist-alerts` policy, in the exclusive list); `run_task.tf`
  and `login_task.tf` (the notifier and the topic in the environment, each schedule's dead-letter
  queue, `sqs:SendMessage` for its scheduler role); `variables.tf` (`alert_email`,
  `late_run_alarm_actions_enabled`); `outputs.tf`; `main.tf` (header, the topic's ARN from its name);
  `README.md`; `tests/caselist_run.tftest.hcl` (mocks, 10 new runs, the two pins the spec named).
* **`infrastructure/envs/dev` and `envs/prod`** (identical): the module's two new arguments, the
  root variable `caselist_run_late_alarm_actions_enabled`, three outputs.
* **`packages/debate_core/src/debate_core/integrations/sns/`** (new): `SnsNotifier`.
* **`packages/debate_core/src/debate_core/application/settings.py`**: `SyncNotifierKind.SNS`,
  `caselist.alert_topic_arn`, the rule that `sns` needs it.
* **`packages/debate_cli/src/debate_cli/container.py`**: `sync_notifier` builds `SnsNotifier` for
  `sns` (a Deviation, below).
* **Tests**: `packages/debate_core/tests/integrations/sns/` (new: the harness, the adapter's tests,
  the sentinel tests); `packages/debate_core/tests/application/test_settings_run_alerts.py` (new);
  `packages/debate_cli/tests/test_sync_notifier_kinds.py` (new); `test_installation.py` and
  `commands/test_doctor.py` (the pinned integration lists, 24 to 25).
* **`pyproject.toml`**: `debate_core.integrations.sns` in the httpx, keyring, lxml and defusedxml
  contracts' source lists (a Deviation, below).
* **`docs/runbooks/`**: `caselist-run-alerts.md` (new); `caselist-cloud-run.md` (a pointer to it, and
  step 8's grep when the alerts' apply already carried bucket mode).

## Deviations from the spec

1. **Two files outside `constraints.packages`.** The spec's packages are `infrastructure`,
   `debate_core.application`, `debate_core.integrations`, `packages/debate_core/tests` and
   `docs/runbooks`. Two things the spec's own description needs live elsewhere:
   * `caselist.notifier = sns` does nothing unless the composition root builds the notifier, which is
     `debate_cli/container.py` (`sync_notifier`, nine lines). The container's integration imports are
     pinned by hand in `packages/debate_cli/tests/test_installation.py` and `commands/test_doctor.py`,
     which fail on a new adapter (v1-e40-t02's CI failure), so both lists moved from 24 to 25; and a
     container test, `packages/debate_cli/tests/test_sync_notifier_kinds.py`, holds the branch.
   * `pyproject.toml`'s import contracts list each adapter subpackage "in the PR that creates it"
     (its own comment); the new one is in four lists.
   Proposed amendment: add `debate_cli`, `packages/debate_cli/tests` and `pyproject.toml` to
   `constraints.packages`, as v1-e40-t02's spec has `debate_cli`. PM question 2.
2. **The dev apply carries `v1-e40-t04`'s bucket mode early, unless the PM says otherwise.** The run
   task definition is replaced by this apply, and `DEBATE_CASELIST__RUN_STATE=bucket` is already in the
   module on `dev`, while the PM's ruling on t04 applies it at the cutover's step 8, after the seed.
   The runbook's plan check reports it as a `NOTE for the PM` rather than passing it silently, and
   step 8's grep now says what to expect if it happened. PM question 1.

## Decisions and assumptions

* **The alert's text.** Subject `debate <env>: <title>`, one line of printable ASCII under 100
  characters (SNS refuses any other subject, and a refused publish is an alert nobody gets); the body
  the title, the subtitle, the message and its hint, and `Fix: <command>` on its own line. Nothing is
  added but the environment.
* **Bounded delivery.** 5 s to connect, 10 s to read, 3 attempts: 45 s at worst, inside the 120 s a
  stopped run has to record, notify and release the lock. The client is built at the first
  notification. Every failure is logged by code or class and swallowed, the client's construction
  included (the port's rule).
* **The adapter reuses `quiet_wire_log`** from `debate_core.integrations.secrets_manager` rather than
  growing a second one, since it is botocore's logging it quiets, not anything about secrets.
* **A task that never started** (`stopCode: TaskFailedToStart`, no exit code) also alerts: an image
  that cannot be pulled starts no container, gives no exit code, and leaves nothing in the dead-letter
  queue, which only catches a start Scheduler could not request.
* **Five CloudTrail rules, not one**, so each has its own state and its own email sentence: the key;
  either secret's policy (every action t02's resource policies keep to break-glass, not only the four
  ADR-0020 names, since each changes which value or key a read reaches); every IAM write naming the
  login role; a task definition naming the login role (as task or execution role) or its family, and
  `RunTask`/`StartTask` of the login family by anyone but the login schedule's role; the password
  read. `BatchGetSecretValue` is matched whatever it names, since it can select by filter.
* **The principal exclusions are ARN prefixes** of the role's sessions,
  `arn:aws:sts::<account>:assumed-role/<role>/`, with `anything-but`. Every caller has an ARN outside
  that prefix, the account root and IAM users included.
* **The late-run metric filter** counts an envelope that carries `run_record.run_id`, under `data` for
  a run that succeeded and `error.details` for one with a failed stage. A dry run's record is null, so
  the rehearsal never counts. A run that raised before any stage writes its record without printing
  it, and is announced as a failed run instead.
* **One metric, undimensioned**, as ADR-0020 (6) names it, so both environments' alarms read the same
  series. They agree because only the run's home records runs (ADR-0020 (7)), and prod's alarm has its
  email off until prod is the home. A dimension would need the environment from two envelope shapes,
  which I could not check offline.
* **One alarm over both dead-letter queues**, as the PM wrote it ("the alarm on them") and ADR-0020
  (8) counts it. Its email names the alarm and both queues; the message in the queue names the
  schedule. The queues exist from this apply, not only with the schedules.
* **The coach's address** is the one the budgets already write to: the first of
  `evidence_search_budget_emails`, else `owner` (ADR-0020 (6)). No new variable.
* **The topic's ARN is written out** (`local.alert_topic_arn`, from its name) in the roles' policies
  and the tasks' environments, so the plan shows them whole and the login role's policy does not
  change; a test holds it equal to the topic's own ARN.
* **The test alert** is the run task started by the deployer with a command the CLI does not have:
  exit 2 before any setting, token or bucket is read, so the run-stopped rule emails. It is the
  task-state path; the sns path is proven by the stubbed run.
* **How t06 turns the late-run email on:** `caselist_run_late_alarm_actions_enabled = true` in dev's
  gitignored `owner.auto.tfvars`, then a plan of exactly `0 to add, 1 to change, 0 to destroy` (the
  alarm's `actions_enabled`), the PM's word, the apply. The runbook's "At the cutover" section has
  the three blocks, after a check that the alarm has left `ALARM`.

## Operator follow-ups

All after this branch merges into `dev` and a dev pre-release containing it is published with a green
validate-dev. They are [caselist-run-alerts.md](../runbooks/caselist-run-alerts.md)'s steps, in its
order; the long plan check (D) and pattern check (G) are given there whole.

**A. Before you start**: the worktree at `origin/dev` with this task merged.

**Operator command** (expected runtime ~1 min)
Where: your Mac
```bash
WT="$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/caselist-credentials-dev"
cd "$WT" || { echo "WT does not exist: $WT"; }
git fetch origin
git switch --detach origin/dev
test -f infrastructure/modules/caselist_run/alerts.tf && test -f packages/debate_core/src/debate_core/integrations/sns/__init__.py && echo "ok: $(git rev-parse --short HEAD), the alerts merged" || echo "NOT MERGED: wait for v1-e40-t05 to merge"
aws sso login --sso-session debate
aws sts get-caller-identity --profile debate-admin --query Arn --output text
grep -c -E '^(owner|site_publisher_user_names|evidence_operator_user_names|evidence_removal_user_names|evidence_search_deployer_user_names|evidence_search_accounts_user_names|caselist_credential_writer_user_names|caselist_run_deployer_user_names) ' infrastructure/envs/dev/owner.auto.tfvars
grep -cE '^caselist_image_digest += "sha256:[0-9a-f]{64}"$' infrastructure/envs/dev/owner.auto.tfvars
grep -E '^evidence_search_budget_emails|^owner ' infrastructure/envs/dev/owner.auto.tfvars
```
Success looks like `ok: <commit>, the alerts merged`, a `DebateBreakGlassAdmin` ARN, `8`, `1`, and
the line naming the coach's address (the first of `evidence_search_budget_emails`, else `owner`): that
is where every alert goes.

**B. The image** (runbook step 1): a release that has this task, its dry run, then its push.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
TAG="$(gh release list --repo charlesclark2/debate-intelligence --limit 1 --json tagName --jq '.[0].tagName')"
git fetch origin tag "$TAG" --no-tags
git cat-file -e "$TAG:packages/debate_core/src/debate_core/integrations/sns/__init__.py" && echo "TAG=$TAG has the sns notifier" || echo "STOP: $TAG has no sns notifier"
if [ -z "$TAG" ]; then echo "STOP: TAG is not set"; else time scripts/caselist_run_deploy.sh dev "$TAG" --dry-run; fi
```
Success looks like `TAG=<tag> has the sns notifier`, six `ok:` lines and `Dry run complete.`

**Operator command** (expected runtime ~3 min)
Where: `$WT`, in the same shell
```bash
cd "$WT"
if [ -z "$TAG" ]; then echo "STOP: TAG is not set"; else scripts/caselist_run_deploy.sh dev "$TAG" 2>&1 | tee /tmp/caselist-run-deploy.txt | tail -8; fi
grep -E '^pushed: |^registered: |caselist_image_digest = ' /tmp/caselist-run-deploy.txt
```
Success looks like `pushed: ...@sha256:<64 hex>`, `registered: ...:task-definition/debate-dev-caselist-run:<n>`
and the `caselist_image_digest = "sha256:..."` line.

**C. The digest in place of the old one.**

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
DIGEST='sha256:the-64-hex-digits-the-push-printed'
if ! printf '%s' "$DIGEST" | grep -qE '^sha256:[0-9a-f]{64}$'; then echo "STOP: DIGEST is not sha256: and 64 hex digits"; else cp infrastructure/envs/dev/owner.auto.tfvars /tmp/owner.auto.tfvars.before-alerts && sed -i '' -E "s/^caselist_image_digest[[:space:]]*=.*$/caselist_image_digest = \"${DIGEST}\"/" infrastructure/envs/dev/owner.auto.tfvars && grep -c "^caselist_image_digest = \"${DIGEST}\"$" infrastructure/envs/dev/owner.auto.tfvars && diff /tmp/owner.auto.tfvars.before-alerts infrastructure/envs/dev/owner.auto.tfvars | grep -c '^[<>]'; fi
```
Success looks like `1`, then `2`.

**D. The plan, which the PM reads first.**

**Operator command** (expected runtime ~2 min)
Where: `$WT`
```bash
cd "$WT"
if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev init -input=false >/dev/null && AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev plan -input=false -no-color -out=caselist-alerts.tfplan | tee /tmp/caselist-alerts-plan.txt | tail -5; fi
grep -E '^Plan:|must be replaced|will be destroyed' /tmp/caselist-alerts-plan.txt
grep -E '^  # ' /tmp/caselist-alerts-plan.txt | grep -v 'module.caselist_run' | head
grep -c 'aws_ssoadmin' /tmp/caselist-alerts-plan.txt
```
**Expected: `Plan: 25 to add, 5 to change, 2 to destroy.`**, with exactly two `must be replaced`
lines (`aws_ecs_task_definition.login[0]` and `.run[0]`), nothing from the second grep, and `0` from
the third. The 25: 23 new resources (topic, policy, subscription; 2 task-state rules and 2 targets;
the metric filter and the late-run alarm; 2 queues and their alarm; 4 write rules, the password rule
and their 5 targets; the run role's `caselist-alerts` policy) and the 2 replacement task definitions.
The 5: the run role's exclusive policy list, the two scheduler roles' policies, the two schedules.
The 2: the old task definition revisions. **No account assignment or permission set is created,
changed, replaced or destroyed; one in the plan stops everything.** Then the runbook's step 2 JSON
check: success is `PLAN OK: 25 to add, 5 to change, 2 to destroy; ...` naming the dev topic and the
coach's address; `PLAN STOP` stops everything. A `NOTE for the PM` line is question 1 below. Send the
plan text, the `PLAN OK` line and any note to the PM.

**E. The apply**, only after the PM's word on D.

**Operator command** (expected runtime ~2 min)
Where: `$WT`
```bash
cd "$WT"
if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev apply -input=false caselist-alerts.tfplan; fi
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output -raw caselist_alert_topic_arn; echo
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output caselist_run_schedule_state
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output caselist_run_late_alarm_actions_enabled
```
Success looks like `Apply complete! Resources: 25 added, 5 changed, 2 destroyed.`, the topic's ARN,
`"DISABLED"` and `false`.

**F. The coach confirms the subscription.** AWS emails `AWS Notification - Subscription
Confirmation` from `no-reply@sns.amazonaws.com`; the coach follows **Confirm subscription** once.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
TOPIC=$(AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output -raw caselist_alert_topic_arn)
aws sns list-subscriptions-by-topic --profile debate-admin --region us-east-1 --topic-arn "$TOPIC" --query 'Subscriptions[].[Protocol,SubscriptionArn]' --output text
```
Success looks like `email` and an ARN ending `:debate-dev-caselist-run-alerts:<id>`, not
`PendingConfirmation`.

**G. Each rule's pattern against AWS's own matcher** (runbook step 5, one read-only block of fifteen
`test-event-pattern` cases, ~1 min). Success: `PATTERNS OK: 15 of 15`.

**H. One test alert (ac1)**: the run task, started by the deployer with a command the CLI lacks.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
SUBNETS=$(AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output -json caselist_run_subnet_ids | tr -d '[]" \n')
SECURITY_GROUP=$(AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output -raw caselist_run_security_group_id)
if [ -z "$SUBNETS" ] || [ -z "$SECURITY_GROUP" ]; then echo "STOP: the network outputs are empty"; else TASK=$(aws ecs run-task --profile debate-dev-caselist-run-deployer --region us-east-1 --cluster debate-dev-caselist-run --task-definition debate-dev-caselist-run --launch-type FARGATE --platform-version LATEST --count 1 --network-configuration "awsvpcConfiguration={subnets=[${SUBNETS}],securityGroups=[${SECURITY_GROUP}],assignPublicIp=ENABLED}" --overrides '{"containerOverrides":[{"name":"run","command":["--json","caselist","alert-test-no-such-command"]}]}' --query 'tasks[0].taskArn' --output text); echo "started ${TASK}"; fi
```
Success looks like `started arn:aws:ecs:...:task/debate-dev-caselist-run/<id>`. A minute or two later:

**Operator command** (expected runtime ~1 min)
Where: `$WT`, in the same shell
```bash
aws ecs describe-tasks --profile debate-dev-caselist-run-deployer --region us-east-1 --cluster debate-dev-caselist-run --tasks "$TASK" --query 'tasks[0].[lastStatus,stopCode,containers[0].exitCode]' --output text
```
Success looks like `STOPPED	EssentialContainerExited	2`, and within a few minutes an email to the
coach, `AWS Notification Message`, beginning `The dev weekly caselist run task stopped with exit code
2 (EssentialContainerExited: ...)`. Send the PM the time it arrived and the task's stop time: that is
ac1's operator evidence. The runbook's step 6 has a last block that reads the rule's invocation count
if no email arrives.

**At the cutover (`v1-e40-t06`)**, after the first recorded cloud run: the late-run alarm's email, in
the runbook's "At the cutover" section (a check, a plan of exactly `0 to add, 1 to change, 0 to
destroy`, the apply).

**Prod**, at the pilot's promotion: the same, from `main`, with `prod` for `dev`.

## Follow-up work

* **The unsubscribe link** (for `v1-e40-t06`'s runbook, or the PM). Every SNS email carries one, and
  following it, by anyone holding the email, stops every alert silently. A subscription confirmed
  through the API with `--authenticate-on-unsubscribe true` refuses an unauthenticated unsubscribe;
  the email link does not set it. Worth a step at the cutover.
* **The summary line's size** (`v1-e40-t06`, the first cloud run). The awslogs driver splits a line
  over about 256 KB into several events, and the JSON metric filter then counts nothing, so a run
  that recorded itself would read as late. Today's Mac summaries are far smaller, but the first cloud
  run's log should be read for the envelope line's length.
* **The Terraform 1.16 panic** on a failed assertion over a whole `for_each` map of a resource with a
  deprecated attribute. It affects any module test that iterates such resources; the other modules'
  tests here do not today. Worth a line in `infrastructure/README.md` (any task touching it).

## PM questions (relay prompt)

```text
PM questions from v1-e40-t05-run-alerts (session report: docs/session-reports/v1-e40-t05-run-alerts.md)

Facts the spec did not have:
- The dev image predates this task, and its settings refuse caselist.notifier = sns. The alerts' apply
  therefore carries a new image built from a release containing this merge (runbook step 1); with the
  old image, Wednesday's 03:00 login would fail at startup.
- That apply replaces both task definitions. The run's new revision also picks up v1-e40-t04's
  DEBATE_CASELIST__RUN_STATE=bucket, which is already in the module on dev, but which your ruling on
  t04 applies at the cutover's step 8, after the seed.
- caselist.notifier = sns needs nine lines in debate_cli/container.py, and the two pinned integration
  lists in debate_cli's tests; the import contracts in pyproject.toml list each new adapter. None of
  debate_cli, packages/debate_cli/tests or pyproject.toml is in this task's constraints.packages.

1. Bucket mode carried by the alerts' apply.
   a) Accept it (recommended). The run's schedule stays DISABLED, a bucket-mode run refuses an
      unseeded bucket (RUN_STATE_NOT_SEEDED), the test alert exits on a usage error before reading a
      setting, and the login does not use bucket mode. The plan check prints a NOTE for you rather
      than passing it silently, and caselist-cloud-run.md step 8 now says its RUN_STATE grep prints 0
      in that case. Cost: step 8's apply becomes an image change only.
   b) Apply the alerts at the cutover's step 8, with the seed's bucket-mode apply. Alerts are live
      before the first cloud run (step 5) either way, but the Wednesday logins until then have no
      alert, and ADR-0020 (4) step 1 says t05 is applied before the cutover.
   Recommendation: a). Nothing runs in bucket mode before the seed, and alerts are live a week sooner.

2. Packages. Amend constraints.packages to add debate_cli, packages/debate_cli/tests and pyproject.toml
   (as t02's spec has debate_cli). Without the container branch the sns kind does nothing; without the
   pinned lists CI fails (t02's experience); without the contract lists the new adapter is not held off
   httpx and keyring. Recommendation: amend.

FYI, going ahead unless you say otherwise:
- One alarm over both dead-letter queues, as you wrote it. Its email names both queues; the queued
  message names the schedule. Two alarms would name the schedule in the email for $0.10 a month.
- RunsRecorded has no dimension (ADR-0020's name), so dev's and prod's alarms read one series. They
  agree because only the home records runs.
- The CloudTrail secrets rule watches every action t02's policies keep to break-glass (seven), not
  only ADR-0020's four, and the login-task rule also watches StartTask, the execution role and the
  family.
- The test alert is the run-stopped rule (the run task started with a command the CLI lacks); the sns
  path is proven by the stubbed run, not live.
- Expected dev plan: 25 to add, 5 to change, 2 to destroy. No account assignment or permission set.

Reply with: 1a or 1b; 2 amend or not; and any FYI you want changed.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-25

**Notes:**

Complete on what a session can do, and careful where it matters: what an alert may say, and whose
reads the password rule ignores.
1. **ac1's built half and ac2 pass.**
   * 37 module tests and 25 adapter tests, with red runs recorded.
   * The sentinel run through the real `SyncRunMonitor` and `ScheduledLogin` to the real
     `SnsNotifier` is the right proof. P19 shows it catching a non-path-shaped school name that
     `redact()` would have let through.
2. **Mutants:** 28 Terraform and 19 Python, all caught, including the PM's four groups.
   * Treating the Terraform 1.16 panic on a deprecation mark as not a clean catch, rewriting the
     assertions by literal key and rerunning the whole table is agreement 8 applied exactly.
3. **Question 1: (a), accept bucket mode carried by the alerts' apply.**
   * The run schedule stays `DISABLED`, and a bucket-mode run refuses an unseeded bucket.
   * The login doesn't use bucket mode, and the test alert exits before reading a setting.
   * The plan check's `NOTE` makes it visible rather than silent, and step 8 becomes an image change.
   * ADR-0020 (4) step 1 puts t05 before the cutover, and alerts a week sooner is worth more here.
4. **Question 2: amend.** The PM adds `debate_cli`, `packages/debate_cli/tests` and `pyproject.toml`
   to `constraints.packages` in a PM batch.
5. **Accepted as made:**
   * the FYIs: one alarm over both queues, one undimensioned `RunsRecorded`, the seven-action secrets
     rule, and the run-stopped test alert;
   * the decisions: subject rules, bounded delivery inside 120 s, `quiet_wire_log` reused, never-started
     tasks alerting, five CloudTrail rules, session-prefix exclusions, the metric filter's two envelope
     shapes, the coach's address from the budget emails, the topic ARN written out, and how t06 turns
     on the late-run email.
6. **The unsubscribe link is taken up now, not at t06.** The coach travels from 2026-11-02, and one
   stray click on an alert email would stop every alert silently. The PM's operator block for step F
   confirms the subscription through the API with `--authenticate-on-unsubscribe true`, using the
   token from the confirmation email, instead of following its link.
7. **The other follow-ups go to v1-e40-t06:** reading the summary line's length in the first cloud
   run's log, and the Terraform panic note for `infrastructure/README.md` in any task that touches it.
8. **The affected set** is the whole selection (`pyproject.toml`), so it is left to the PR's `ci`
   under agreement 10. The always-run list and changed areas passed. One CLI run past two minutes
   under load was disclosed.

**The PR merges `--partial`,** phase `InProgress`, until the operator's test alert is received (ac1).
The PM reads the dev plan (expected `25 to add, 5 to change, 2 to destroy`, with no account
assignment or permission set) before any apply. No re-review is needed.

## PM record, 2026-10-25

Added by the PM. Nothing above is changed, and this section is not a review.

* **The alerts apply in dev, 2026-10-25.** The plan stopped once on an extra resource,
  `module.evidence_store.aws_ssoadmin_permission_set_inline_policy.evidence_removal[0]`: it was
  `v1-e32-t13`'s unapplied removal grant. Its printed diff was exactly the added
  `DeleteLandscapeSchoolViews` statement and the listing prefix change, so the PM approved the
  combined plan, `25 to add, 6 to change, 2 to destroy`, with no account assignment and no other
  permission set. The apply matched it.
* **The subscription** was confirmed through the API with `--authenticate-on-unsubscribe true`,
  using the token from the confirmation email, not its link; `ConfirmationWasAuthenticated` is
  `true`. The runbook's pattern check printed `PATTERNS OK: 15 of 15`.
* **ac1's operator half: done.** The test alert's task stopped at 21:02:22 UTC, and the coach's email
  arrived at 16:02 CDT, the same minute. It ran on the run image `v1.1.0-dev.151` (see
  `v1-e40-t03`'s record).
* Every criterion is met, so the Goal is set to `Succeeded` in the PM batch of 2026-10-25 (p).
