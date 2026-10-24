# `caselist_run` module

One environment's weekly caselist run in the cloud. Decision:
[ADR-0020](../../../docs/adr/0020-weekly-caselist-run-in-the-cloud.md). Epic:
[E40](../../../plan_specs/v1/e40-cloud-caselist-run/epic.yaml). Operator steps:
[docs/runbooks/caselist-cloud-credentials.md](../../../docs/runbooks/caselist-cloud-credentials.md).

Called once from [`envs/dev`](../../envs/dev/caselist_run.tf) and once from
[`envs/prod`](../../envs/prod/caselist_run.tf), with the same arguments. It holds no account id or
region: both come from the provider. ADR-0020 makes this the one module the run's Terraform lives
in, so that V2's foundation can lift its pieces out with `moved` blocks; `v1-e40-t03` adds the
network, the cluster, the image repository and the run's task here.

## What it creates

[`v1-e40-t02-secrets-token-store-and-login`](../../../plan_specs/v1/e40-cloud-caselist-run/t02-secrets-token-store-and-login.yaml)
builds the credentials and the scheduled login, in two applies:

| File | Resources | Apply |
|---|---|---|
| `credentials.tf` | The KMS key `alias/debate-<env>-caselist-credentials`; the secrets `debate-<env>-caselist-tabroom-password` and `debate-<env>-caselist-token`, created empty; each secret's resource policy | A |
| `roles.tf` | The login role `debate-<env>-caselist-login`; the run role `debate-<env>-caselist-run` with its credentials grant; each role's policies held exclusive | A |
| `credential_writer.tf` | The `Debate<Env>CaselistSecretWriter` permission set, its inline policy and its one assignment | A |
| `login_task.tf` | The login task definition, pinned by digest; its execution role and log group; the scheduler role; the schedule, Wednesdays at 03:00 America/Chicago, never retried | B, once `login_task` is set |

Apply A needs no network. Apply B takes `v1-e40-t03`'s cluster, subnets, security group, repository
and the digest of a pushed image as `login_task`.

## Who may read what

ADR-0020 (2), enforced three times over, so that no single policy left off widens a read:

| | Password secret | Token secret |
|---|---|---|
| Read (`GetSecretValue` and `kms:Decrypt`) | The login role only | The run role only |
| Write (`PutSecretValue`, `kms:GenerateDataKey`) | The coach's writer only | The login role and the coach's writer |
| Change who may read (policy, key, rotation, deletion, replication) | `DebateBreakGlassAdmin` only | `DebateBreakGlassAdmin` only |

* **The key policy** delegates nothing to IAM. The account appears only together with a principal
  pattern (break-glass for administration, the writer for encryption), and three denies refuse a
  decrypt of the password to all but the login role, of the token to all but the run role, and of
  anything to all but those two. Grants and re-encryption are refused to everyone.
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
secret:

```bash
terraform -chdir=infrastructure/modules/caselist_run init -backend=false
terraform -chdir=infrastructure/modules/caselist_run test
```

The read rules were checked by mutation: 22 mutants that widen or drop one rule each, every one
caught by a failing assertion (the task's session report lists them).
