# `caselist_run` module

One environment's weekly caselist run in the cloud. Decision:
[ADR-0020](../../../docs/adr/0020-weekly-caselist-run-in-the-cloud.md). Epic:
[E40](../../../plan_specs/v1/e40-cloud-caselist-run/epic.yaml). Operator steps:
[caselist-cloud-credentials.md](../../../docs/runbooks/caselist-cloud-credentials.md) (the credentials
and the login) and [caselist-cloud-run.md](../../../docs/runbooks/caselist-cloud-run.md) (the run).

Called once from [`envs/dev`](../../envs/dev/caselist_run.tf) and once from
[`envs/prod`](../../envs/prod/caselist_run.tf), with the same arguments. It holds no account id or
region: both come from the provider. ADR-0020 makes this the one module the run's Terraform lives
in, so that V2's foundation can lift its pieces out with `moved` blocks.

## What it creates

[`v1-e40-t02-secrets-token-store-and-login`](../../../plan_specs/v1/e40-cloud-caselist-run/t02-secrets-token-store-and-login.yaml)
builds the credentials and the scheduled login, in two applies:

| File | Resources | Apply |
|---|---|---|
| `credentials.tf` | The KMS key `alias/debate-<env>-caselist-credentials`; the secrets `debate-<env>-caselist-tabroom-password` and `debate-<env>-caselist-token`, created empty; each secret's resource policy | A |
| `roles.tf` | The login role `debate-<env>-caselist-login`; the run role `debate-<env>-caselist-run` with its credentials grant; each role's policies held exclusive | A |
| `credential_writer.tf` | The `Debate<Env>CaselistSecretWriter` permission set, its inline policy and its one assignment | A |
| `login_task.tf` | The login task definition, pinned by digest; its execution role and log group; the scheduler role, which trusts the login's schedule group only; the schedule group `debate-<env>-caselist-login` and the schedule in it, Wednesdays at 03:00 America/Chicago, never retried | B, once `image_digest` is set |

[`v1-e40-t03-run-image-and-schedule`](../../../plan_specs/v1/e40-cloud-caselist-run/t03-run-image-and-schedule.yaml)
builds the run, in the apply between those two, and in apply B:

| File | Resources | Apply |
|---|---|---|
| `network.tf` | The VPC `debate-<env>-caselist-run`, its default security group held with no rule, two public subnets, the internet gateway and route, the S3 gateway endpoint, and the tasks' security group: no inbound rule, outbound HTTPS only | the run's |
| `cluster.tf` | The cluster and the image repository `debate-<env>-caselist-run`: immutable tags, a scan on push, KMS, the five newest images kept | the run's |
| `run_task.tf` | The run's execution role and log group; then the run task definition (Fargate, arm64, 8 vCPU, 16 GB, 100 GiB, `debate-research --json caselist pull` under a 6-hour deadline, pinned by digest), its scheduler role, which trusts the run's schedule group only, and the schedule group `debate-<env>-caselist-run` with the schedule in it, Wednesdays at 06:00 America/Chicago, never retried, **created disabled** | the run's; B for the task and schedule |
| `roles.tf` | The run role's `everyday-evidence` policy: `module.evidence_store.operator_policy_json` itself | the run's |
| `deployer.tf` | The `Debate<Env>CaselistRunDeployer` permission set: push to the repository, register a run task definition passing the run's two roles and never the login's, start, watch and stop a run | the run's |

Apply A needs no network. The run's apply needs no image. Apply B takes the digest of an image
`scripts/caselist_run_deploy.sh` pushed as `image_digest`, and creates both task definitions and both
schedules. `run_schedule_enabled` stays false until the cutover (`v1-e40-t06`): before `v1-e40-t04`'s
bucket mode, a cloud run would start from an empty data directory and publish without the bucket's
lock.

## What the run may do

The run role reads one secret, the token, and holds the everyday evidence permissions, the same JSON
document as the EvidenceOperator permission set: list the documented prefixes, read, publish, tag a
retired `parsed/` directory, use the evidence key. Nothing more, and no delete. `evidence_policy_json`
is refused at plan time if it allows anything else, names another bucket or another key. The task's
environment names the token's secret and holds no secret; the CLI reads the token itself with the
task role, through t02's Secrets Manager client, which keeps botocore's wire logs quiet. It also sets
bucket mode, `DEBATE_CASELIST__RUN_STATE=bucket` (`v1-e40-t04`, ADR-0020 (3) and (4)): the run
restores its working copy from the evidence bucket, saves its state back, and holds the bucket's run
lock, `reports/sync/run-lock.json`, while it writes. Those writes need no grant beyond the everyday
document's: conditional writes are `s3:PutObject`. The run role still never deletes, which
`the_run_role_never_deletes` checks over its policies by IAM's own wildcard matching.

The deployer may pass the run role and the run's execution role to ECS tasks, and an explicit deny
refuses it the login role and the login's execution role. `ecs:RegisterTaskDefinition` takes no
resource, so the pass-role rule is what holds a registration to the run's roles, and both schedules
pin the revision Terraform made.

Each schedule sits alone in a schedule group of its own, and each scheduler role trusts
`scheduler.amazonaws.com` only with `aws:SourceAccount` and with `aws:SourceArn` set to exactly that
group's ARN. That is the group, not the schedule, because EventBridge Scheduler assumes the role with
the group's ARN as `aws:SourceArn` ("Confused deputy prevention in EventBridge Scheduler",
<https://docs.aws.amazon.com/scheduler/latest/UserGuide/cross-service-confused-deputy-prevention.html>).
It is never the `default` group, which any schedule in the account may join. A trust naming the
schedule's own ARN refuses Scheduler, which is how dev's first apply B failed at both schedules on
2026-10-24.

## Who may read what

ADR-0020 (2), enforced three times over, so that no single policy left off widens a read:

| | Password secret | Token secret |
|---|---|---|
| Read (`GetSecretValue` and `kms:Decrypt`) | The login role only | The run role only |
| Write (`PutSecretValue`, `kms:GenerateDataKey`) | The coach's writer only | The login role and the coach's writer |
| Change who may read (policy, key, rotation, deletion, replication) | `DebateBreakGlassAdmin` only | `DebateBreakGlassAdmin` only |

* **The key policy** delegates nothing to IAM. The account appears only together with a principal
  pattern (break-glass for administration and key validation, the writer for encryption), and three
  denies refuse a decrypt of the password to all but the login role, of the token to all but the run
  role, and of anything to all but those two, each also exempting break-glass's pattern. A fourth
  deny then refuses break-glass every decrypt whose `SecretVersionId` is not
  `RequestToValidateKeyAccess`. Grants and re-encryption are refused to everyone.
* **Break-glass validates the key, and reads nothing.** Terraform creates the secrets as break-glass,
  and Secrets Manager checks a caller's access to a secret's key with a `GenerateDataKey` and a
  `Decrypt` as the caller, `SecretVersionId` the literal `RequestToValidateKeyAccess`, and discards
  the results ("Validating access to the KMS key" in [Secret encryption and decryption in AWS
  Secrets Manager](https://docs.aws.amazon.com/secretsmanager/latest/userguide/security-encryption.html)).
  Break-glass is allowed exactly those two calls, through Secrets Manager, for the two secrets. A
  stored version's data key is bound to its own `SecretVersionId`, so a decrypt that must carry the
  validation id cannot open a password or a token. Without them the first apply in dev (2026-10-24)
  could not create the secrets.
* **Each secret's resource policy** only refuses: reads to all but its one reader, writes to all
  but its writers, and every administrative action to all but break-glass.
* **Each role's IAM policy** names exactly its own secret and context.

An Identity Center permission set's role is `AWSReservedSSO_<set>_<hash>`, so the writer and
break-glass are matched by `aws:PrincipalArn` patterns; a reprovisioned role keeps its access.

ADR-0020 named the writer `Debate<Env>CaselistCredentialWriter`, which is 33 characters in dev and
34 in prod. Identity Center allows a permission set 32, so it is `Debate<Env>CaselistSecretWriter`
(the PM's ruling of 2026-10-24, in the task's spec and session report).

Every dev apply of this module runs from `origin/dev` after the task merged, never from a task
branch: an apply from a checkout without `module.caselist_run` would destroy what it created (the
runbook, "Before you start").

## Tests

`tests/caselist_run.tftest.hcl`, under a mocked provider, with an ARN of its own for every role and
secret: 14 runs for the credentials and the login (`v1-e40-t02`), 12 for the run (`v1-e40-t03`).

```bash
terraform -chdir=infrastructure/modules/caselist_run init -backend=false
terraform -chdir=infrastructure/modules/caselist_run test
```

The read rules were checked by mutation: 22 mutants that widen or drop one rule each, then 14 more
on break-glass's key validation (narrowing, widening or dropping each of its statements and the
split denies), every one caught by a failing assertion (`v1-e40-t02`'s session report lists them).
The run's pass-role and secret-read rules were checked the same way: 22 more, every one caught
(`v1-e40-t03`'s report).
