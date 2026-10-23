# ADR-0020: The weekly caselist run in the cloud — one scheduled Fargate task, the Tabroom password in Secrets Manager, and the run's state in the evidence bucket

- Status: Accepted
- Date: 2026-10-22; accepted 2026-10-23 by the PM
- Deciders: Charlie Clark (coach and product owner), on the PM's review
- Architecture references:
  - [§5 AWS Cloud Architecture](../architecture/architecture_proposal.md#5-aws-cloud-architecture)
  - [§11 V1 Detailed Architecture](../architecture/architecture_proposal.md#11-v1-detailed-architecture)
  - [§14 Security, Privacy, and Student Safety](../architecture/architecture_proposal.md#14-security-privacy-and-student-safety)
  - [§15 Reliability, Observability, and Cost Controls](../architecture/architecture_proposal.md#15-reliability-observability-and-cost-controls)
  - [§17 Deployment and Evolution Plan](../architecture/architecture_proposal.md#17-deployment-and-evolution-plan)

## Context

The weekly caselist run (E34's pull, import and publish, E31's parse and E39's search index stage)
runs on the coach's Mac under launchd. The student search pilot's freshness now depends on that
laptop being on, awake and signed in to AWS on a Wednesday morning. Release v1.8 (epic
[E40](../../plan_specs/v1/e40-cloud-caselist-run/epic.yaml)) moves the run into the team's AWS
account. Tasks `t02` to `t06` build against this record, so it decides rather than lists options,
and where it changes what a task's spec says it names the change for the PM in
[What each E40 task builds](#what-each-e40-task-builds).

**Fixed inputs** (the coach's decisions of 2026-10-22, not reopened here):

- The Tabroom password lives in Secrets Manager under its own KMS key.
- Only the login job's role can read it, and CloudTrail logs every read.
- The token is refreshed on a schedule, and the coach gets an email when a login fails.
- Run state lives in S3. The Mac is never the server.

**Two answers from the coach, 2026-10-23:**

- **Tabroom's login never asks for more than the password.**
- **The OpenCaselist maintainer has been told** that the downloads are likely to move to the cloud,
  and is fine with it.

**What the decision has to fit.**

- **The data-use policy.** [E34 gate](../policies/caselist-data-use.md#e34--automated-caselist-download-v12)
  items 2 to 8: the maintainer's 10 downloads a minute, the operator's own Tabroom account, weekly
  cadence at most, a `401`/`403` stops the run, the suppression list honoured, a run log, and (item
  8) "the scheduled job runs on the operator's own machine". Item 3 says the password is never
  stored. Both items change in policy version 1.12, in the same pull request as this record
  ([The policy](#the-policy-version-112)).
- **OpenCaselist's ceiling of 5 bulk downloads per user per day**, counted by the run over a rolling
  24 hours in one ledger ([ADR-0017](0017-caselist-corpus-is-retrievable.md), `v1-e34-t06`). The
  ceiling is per Tabroom user, so there must be exactly one ledger for the coach's account.
- **One account, one region, two environments** ([ADR-0010](0010-primary-aws-region.md),
  [ADR-0013](0013-two-environments-and-dev-main-promotion.md)): everything in `us-east-1`, named
  `debate-<environment>-<purpose>`, tagged, and the monthly budgets of $25 for dev and $50 for prod.
  The account also runs the operator's unrelated projects, and its administrators are the
  `DebateBreakGlassAdmin` permission set and the account's own `AdministratorAccess`.
- **The evidence buckets** and their prefixes
  ([store layout](../architecture/evidence-store-layout.md)). Personal data may live under
  `manifests/` and `reports/tub/search/` only; the everyday `EvidenceOperator` credential writes and
  never deletes; the `EvidenceRemoval` credential deletes.
- **One adult maintainer.** Every apply and deploy is operator-run until GitHub OIDC roles arrive
  (`v2-e10-t03`), as for the website and the pilot ([ADR-0019](0019-student-search-pilot-stack-sign-in-and-hosting.md)
  (f)).
- **V2's foundation is already specified** ([`v2-e10-t04`](../../plan_specs/v2/e10-aws-foundation/t04-kms-secrets.yaml),
  [`v2-e10-t05`](../../plan_specs/v2/e10-aws-foundation/t05-container-platform.yaml)), and
  [ADR-0011](README.md#reserved-numbers) (VPC egress) is reserved for `v2-e10-t05`.

Every claim about an AWS service or price below was read from its documentation or pricing page on
**2026-10-22**. The pages are listed in
[AWS documentation relied on](#aws-documentation-relied-on-read-2026-10-22). Figures computed from
them and not measured are marked *estimate*.

### What was measured

Read-only, on the operator's Mac, from the dev data directory and the repository, on 2026-10-22
(working agreement 7). Each read took under two seconds; the slowest, the walk over the data
directory's modification times, took 1.4 s. Counts, sizes and times only.

**The run of 2026-10-22, `20261022T052044Z`.** Started 05:20:44Z, finished 08:00:30Z: **9,585.6 s,
2 h 39 min 46 s** (`duration_seconds` in `<data_dir>/caselist-sync-runs/20261022T052044Z.json`).
It downloaded 4 archives (three weeklies and hspolicy26's complete archive), imported 2,628 new
sources, published 2,628 raw objects, parsed 2,628 sources (12,597 skipped as parsed already,
264 unsupported, 0 failed, 51,998 cards), uploaded 2,637 parsed-store objects, and built and
published index `767b9c7c056b80cb`. The Mac is an Apple M3 Pro with 11 cores and 18 GB of memory,
so the parse ran 6 workers (`parse.worker_cap`).

**The run record does not time its stages.** Neither the record, the run's details nor the launchd
logs carry a stage's start or end. The bounds below come from the modification times of what each
stage writes in the data directory:

| Stage | From | To | Duration | What marks it |
|---|---|---|---|---|
| select and download | 05:20:44 | 05:21:39 | 55 s | The lock taken; the download ledger's last write at 05:21:38; the first blob |
| import | 05:21:39 | 05:22:16 | 37 s | Blobs, then the last manifest written |
| raw publish | 05:22:16 | before 05:25:41 | at most 3 min 25 s | Until the first parse output |
| parse, aggregate rebuild and parsed-store publish, three caselists | 05:25:41 | about 07:51 | about **2 h 25 min** | The first parse output, to the index build's start (its SQLite file was complete at 07:54:45, less the 205 s a build took before `v1-e39-t12`) |
| search index (build, gzip, publish) | about 07:51 | about 07:58 | about 7 min | SQLite file 07:54:45, gzip 07:56:18, manifest 07:56:20, then the upload |
| report, retention, the record | about 07:58 | 08:00:30 | about 2 min | The record written at 08:00:30, the database at 08:00:32 |

Inside the parse stage, the per-source parse output was written in 15 min 18 s in all: hsld26
05:25:41–05:30:20, hspolicy26 06:03:55–06:12:35, hspf26 07:04:28–07:06:27. The three gaps after
them, 33 min 35 s, 51 min 53 s and about 44 min 53 s, hold each caselist's aggregate rebuild and its
parsed-store publish, which file times cannot separate: the aggregates were rewritten by hand at
19:47–20:10 local that evening, so their run-time writes are gone. The rebuild alone took 1,046 s
for these three caselists on 2026-10-16 ([parse report](../data/caselist-parse-report.md#the-re-parse-2026-10-16)),
which leaves **about 1 h 53 min, by difference, for publishing the parsed store from the Mac**. That
is unexplained by the records: on 2026-10-16 a publish with nothing to upload checked all four
caselists inside 1,114 s, and the run's own raw publish moved 2,628 objects in under 3.5 minutes. So
`t03` adds each stage's start and end to the run's details (see
[What each E40 task builds](#what-each-e40-task-builds)).

**The local store**, `~/.debate-research/dev`, by what it holds (apparent bytes from `stat`, file
counts from `find`):

| Part | Where | Files | Bytes |
|---|---|---:|---:|
| Raw sources, content-addressed | `blobs/` | 15,327 | 4,229,439,038 (4.23 GB) |
| Parsed store, one version directory (`2026.10.20-docx-6`) per caselist | `parsed/` | 15,344 | 9,140,691,684 (9.14 GB) |
| Search index builds, three of them, each a SQLite file, its gzip and a manifest | `tub-index/` | 9 | 3,334,438,283 (3.33 GB) |
| Manifests | `objects/manifests/` | 50 | 18,655,784 (18.7 MB) |
| The SQLite database | `debate.sqlite3` | 1 | 42,803,200 (42.8 MB) |
| Run log, details, summaries, ledgers, suppression copy | the rest | — | under 2 MB |
| **Total** | | | **about 16.8 GB** (16,446,336 KiB allocated) |

The "about 14 GB" in the task's brief is the parsed store on 2026-10-21, when it held both the
`docx-5` and `docx-6` version directories ([parse report](../data/caselist-parse-report.md#the-re-parse-to-docx-6-operator-run-after-the-merge));
`docx-5` was retired on 2026-10-22. The database holds 46 snapshots, 15,327 sources, 20,730
disclosures and 104 camp files. A disclosure's key includes its source path, so the database holds
school and team code.

**The index** on 2026-10-22: the newest build, `f29b81c276dd67c5` (built at 23:22 local, after
`v1-e39-t12`), holds **50,434 documents** in a SQLite file of **834,973,696 bytes** with a gzip
object of **311,899,269 bytes** (its manifest). The 839,438,336 and 314,054,035 bytes in the brief
are the run's own build, `767b9c7c056b80cb`, of 52,059 documents. A build took **205 s** on the Mac
before `v1-e39-t12`, whose second read adds **about 100 s**, so this record plans for **about 305
s** ([search index](../data/search-index.md#full-store-builds)). Its storage peak holds two SQLite
files at once, about 1.7 GB, plus the gzip object.

**A full re-parse.** The brief calls it multi-hour; on the Mac it is not. The two full re-parses
recorded took **1,970 s** (2026-10-16, 12,701 sources) and **2,423 s** (2026-10-19, the same
sources, at `docx-5`), each including the rebuild and the publish to dev
([parse report](../data/caselist-parse-report.md#the-re-parse-2026-10-16)). At today's 15,327 sources
that is about 40 to 50 minutes on the Mac (*estimate*). On a cloud CPU it is longer, which is what
the sizing below has to absorb.

**Today's login** (`debate-research caselist auth login`,
[`caselist_auth.py`](../../packages/debate_cli/src/debate_cli/commands/caselist_auth.py) and
[`opencaselist/auth.py`](../../packages/debate_core/src/debate_core/integrations/opencaselist/auth.py)):
one `POST /login` to `api.opencaselist.com` carrying the Tabroom username, the password and
`remember: true`, which returns a token and its expiry. The password is read with hidden input,
sent once and never stored. The token goes to the macOS keychain or a `0600` file
([`token_store.py`](../../packages/debate_core/src/debate_core/integrations/opencaselist/token_store.py)).
A refused login is `CaselistLoginRejected` and is never retried. Tabroom itself is behind
OpenCaselist's server, so it never sees the caller's address.

**Today's lock** is an `flock` on `<data_dir>/caselist-sync.lock`, taken by `caselist pull` and by
the inbox purge of `caselist remove`. No other command that writes to a bucket takes it.

**Today's environments.** One data directory, `~/.debate-research/dev`, feeds both buckets: the agent
publishes it to dev, and the operator publishes the same directory to prod by hand
([runbook](../runbooks/caselist-scheduled-sync.md#one-data-directory-for-each-bucket)).

## Decision

**The weekly run is one ECS task on AWS Fargate, started by an EventBridge Scheduler schedule, in the
environment that is the run's home: dev from the cutover, prod from the pilot's promotion.** A
second, smaller Fargate task logs in to OpenCaselist three hours earlier. The Tabroom password and
the caselist token are two Secrets Manager secrets under one KMS key of their own; only the login
task's role reads the password, and only the run task's role reads the token. The run restores a
working copy from the evidence bucket at its start, saves its state back as it goes, and holds a
lease on a lock object in the bucket for as long as it runs. Every command that writes to a bucket
takes the same lock. A failed run, a failed login, a run that never happened and any change to who
may read the password email the coach.

This record covers release v1.8 and its two environments. What V2 replaces is in
[What V2 replaces, and what E40 must not build](#what-v2-replaces-and-what-e40-must-not-build).

### (1) Runtime: one on-demand Fargate task, sized for a full re-parse

1. **ECS on Fargate, not AWS Batch.** The run is one job a week with no queue, no array and no
   dependency between jobs. An EventBridge Scheduler schedule can start an ECS task directly, with
   its own retry policy and dead-letter queue. Batch would add a compute environment, a job queue and
   a job definition around the same Fargate task, and a second orchestration service that V2's
   container platform (`v2-e10-t05`, an ECS cluster) does not plan and would have to absorb. Batch's
   one advantage here, a job timeout, is met by the run's own deadline (item 6).
2. **Size: 8 vCPU, 16 GB of memory, `arm64`, 100 GiB of ephemeral storage, platform version 1.4.0 or
   later.**
   - **CPU.** The parse is CPU-bound and runs one worker per core
     ([`parse_workers.py`](../../packages/debate_core/src/debate_core/application/caselist/parse_workers.py)).
     The task sets `parse.workers` to 8. A Graviton vCPU is assumed to do about half the parse work
     of an M3 Pro performance core (*estimate*), so 8 workers on Fargate do roughly what 6 do on the
     Mac: a full re-parse of today's store in **about 1 to 1.5 hours**, where 4 vCPU would take 2 to
     3 hours (*estimate*). `t03` records the first full parse's time and resizes if it is wrong.
   - **Memory.** 16 GB is the smallest Fargate allows at 8 vCPU. The index build used 1.18 GB
     resident at its largest ([search index](../data/search-index.md#full-store-builds)); the rest is
     the parse workers' and the restore's.
   - **Ephemeral storage.** A full-re-parse week at today's size needs about **20 GB**: the parsed
     store written afresh (9.1 GB), every raw source restored for it (4.2 GB), the week's archives in
     the inbox (up to about 3 GB; retention freed 2.76 GB of nine files on 2026-10-22), the index
     build's peak (about 2 GB), the database, the manifests, and the container image, which Fargate
     stores on the same volume. That already passes Fargate's 20 GiB default. At the season's
     average so far, about 1,000 sources a week and 0.87 GB of raw and parsed bytes per 1,000, the
     working set reaches about **50 GB by July 2027** (*estimate*). 100 GiB covers that twice over;
     Fargate allows 200 GiB. The run warns when the volume passes 70% (`t03`), so the size is
     changed before it fills. The storage is encrypted by Fargate (AES-256, an AWS-owned key) and
     deleted when the task stops.
   - **`arm64`**, so the operator's Mac builds the image without emulation, as for the pilot.
3. **On-demand, not Fargate Spot.** Spot saves up to 70% of the compute, about $1.40 a month here.
   A Spot interruption gives two minutes' notice and then stops the task. Under (3) below that
   leaves the bucket as a killed Mac run leaves it, and the next run redoes the week from the last
   saved state; but redoing a week means **downloading its archives again**, out of the coach's 5 a
   day, and the pilot's index arrives late. A multi-hour full re-parse is the run most exposed. The
   saving does not pay for spending a volunteer maintainer's download budget twice.
4. **Lambda is ruled out**: a 15-minute limit against a run measured at 2 h 40 min, and at most 10 GB
   of `/tmp` against a 20 GB working set.
5. **The network.** A small VPC of the run's own (`debate-<env>-caselist-run`), two public subnets,
   an internet gateway, an **S3 gateway endpoint** (no charge) so bucket traffic stays inside AWS, and
   a security group with **no inbound rule** and outbound HTTPS only. The task gets a public IPv4
   address (`assignPublicIp`), because it must reach `api.opencaselist.com`, Secrets Manager, ECR and
   CloudWatch Logs, and the alternative, a NAT gateway, costs about $32.85 a month for each
   environment before data (*estimate* from the published hourly rate), more than dev's whole budget.
   This is an interim network for one weekly task. It is not ADR-0011's design and does not
   pre-empt it: `v2-e10-t05` moves the task into its private subnets
   ([V2](#what-v2-replaces-and-what-e40-must-not-build)).
6. **A deadline in the container.** The task's command runs the CLI under a 6-hour limit. A run
   still going then is stopped the way `docker stop` would stop it, saves what (3) says it may
   save, releases the lock and exits non-zero, so the coach is emailed (6). The longest expected
   run, a full re-parse week, is about 2.5 hours (*estimate*).
7. **No shell into a running task.** `enableExecuteCommand` is off on both task definitions, and
   neither role holds the `ssmmessages` actions it needs.

The image is the installed CLI built from a tagged release, as `scripts/install_channel.sh`
installs it, on the slim Debian Python image at the tag of the one Python that `requires-python` in
[`packages/debate_core/pyproject.toml`](../../packages/debate_core/pyproject.toml) allows. `t03`
checks that its SQLite has FTS5 and is at least the 3.40.0 the pilot's index is pinned to
([ADR-0019](0019-student-search-pilot-stack-sign-in-and-hosting.md) (c) 1). Nothing secret is in the
image or its environment.

### (2) Credentials: two secrets, one key, three principals

**The secrets,** both in Secrets Manager in `us-east-1`, created by Terraform as empty shells with
no value in state (as `v2-e10-t04` requires):

| Secret | Holds | Written by | Read by |
|---|---|---|---|
| `debate-<env>-caselist-tabroom-password` | The coach's Tabroom username and password, as JSON | The coach, through `Debate<Env>CaselistCredentialWriter` | **The login role only** |
| `debate-<env>-caselist-token` | The `caselist_token` and its expiry, the document the token store already writes | The login role; the coach, when logging in by hand | **The run role only** |

**The key,** `alias/debate-<env>-caselist-credentials`: a symmetric customer-managed key used by
these two secrets and nothing else, with annual rotation on. Secrets Manager encrypts each version
under a data key from `GenerateDataKey` and decrypts it with `Decrypt`, always with the encryption
context `SecretARN` and `SecretVersionId`, so the key policy can say which secret a call is for.

**The three principals, exactly.**

1. **The login role**, `debate-<env>-caselist-login`, the task role of the login task. It may:
   - `secretsmanager:GetSecretValue` on the password secret;
   - `kms:Decrypt` on the key, through Secrets Manager (`kms:ViaService`), with
     `kms:EncryptionContext:SecretARN` the password secret's ARN;
   - `secretsmanager:PutSecretValue` on the token secret, and `kms:GenerateDataKey` through Secrets
     Manager with the token secret's ARN as context;
   - `sns:Publish` to the alert topic (6).

   Nothing else: no S3, no other secret. Its trust policy admits `ecs-tasks.amazonaws.com` only, with
   `aws:SourceAccount` the account.
2. **The run role**, `debate-<env>-caselist-run`, the task role of the run. On the credentials it may
   only `secretsmanager:GetSecretValue` on the token secret and `kms:Decrypt` through Secrets Manager
   with the token secret's ARN as context. It **never reads the password.** Its other grants are in
   (3).
3. **The coach's writer**, the Identity Center permission set `Debate<Env>CaselistCredentialWriter`,
   assigned to the coach's user only, sessions of one hour. It may `secretsmanager:PutSecretValue`
   and `DescribeSecret` on the two secrets and `kms:GenerateDataKey` through Secrets Manager with
   either secret's ARN as context. It has **no `GetSecretValue` and no `kms:Decrypt`**. Secrets
   Manager documents that `PutSecretValue` decrypts only when a request reuses an existing version's
   id, to compare values; every write here creates a new version, so the writer never needs Decrypt,
   and a retried request with an old id simply fails. `t02` adds `debate-research caselist auth
   set-password`, which prompts with hidden input, as `login` does, and writes the secret, so the
   password never reaches shell history or a process listing. The coach writes it again after
   changing it at Tabroom and never reads it back.

**Both the key policy and each secret's resource policy enforce this,** so neither an IAM grant nor a
policy left off by mistake widens the read:

- **Key policy.** No statement delegates the key's cryptographic use to IAM. Key administration
  (create, describe, enable, disable, put policy, schedule deletion, tag, rotate) is allowed to the
  account only for principals whose ARN matches `DebateBreakGlassAdmin`'s role, the identity
  Terraform applies under. Use is allowed only by the three statements above. An explicit **deny**
  refuses `kms:Decrypt` to every principal but the login and run roles, and refuses
  `kms:CreateGrant` and `kms:ReEncrypt*` to everyone, since Secrets Manager needs no grant. So
  `DebateMaintainer`'s PowerUserAccess, which allows `kms:*` in IAM, decrypts nothing here and cannot
  change the policy.
- **Password secret's resource policy.** Denies `secretsmanager:GetSecretValue` to every principal
  whose `aws:PrincipalArn` is not the login role; denies `PutSecretValue` to every principal but
  the writer's role; denies `PutResourcePolicy`, `DeleteResourcePolicy`, `UpdateSecret` (which could
  move the secret to another key), `DeleteSecret` and `ReplicateSecretToRegions` to every principal
  but `DebateBreakGlassAdmin`.
- **Token secret's resource policy.** The same, with the run role as the only reader and the login
  role and the writer as the writers.
- **No secret reaches a task through ECS's `secrets` field.** That would make the task *execution*
  role a reader and put the password in the container's environment. Each task's own code calls
  `GetSecretValue` with its task role, holds the value as a `SecretStr`, and registers it with the
  redaction filter, as the token store does today.

**Who can make the login role run.** The login task definition is owned by Terraform and pins its
image by digest. Only `DebateBreakGlassAdmin` (the apply) and the login schedule's role
(`debate-<env>-caselist-scheduler`, assumable only by `scheduler.amazonaws.com` for that schedule)
hold `iam:PassRole` on the login role. `DebateMaintainer`'s PowerUserAccess has no `iam:PassRole`,
and neither has `EvidenceOperator`. No person runs the login task, because `RunTask` accepts a
command override and so would let them run anything as the login role. The run task, whose role
reads only the token, may be started by hand (`t03`'s deployer, below).

**Break-glass, without widening the read.** Nothing anyone does day to day needs the password read
back: a wrong or changed password is written again, never inspected. What break-glass covers is
repairing the setup: a policy broken, a role deleted, a key disabled. `DebateBreakGlassAdmin` can
change the key policy, the resource policies, the login role or its task definition, and so could
read the password by changing one of them first. That is inherent in an account with an
administrator, and this record does not pretend otherwise. What it ensures is that **every such
path is an administrative act that the organization trail records and that emails the coach as it
happens** (6): `PutKeyPolicy`, `CreateGrant`, `DisableKey`, `ScheduleKeyDeletion`,
`PutResourcePolicy`, `DeleteResourcePolicy`, `UpdateSecret`, `DeleteSecret`, any IAM change to the
login role, `RegisterTaskDefinition` naming the login role, and `RunTask` of the login family by
anyone but its scheduler role. ADR-0010's revisit trigger, a separate prod account, is what would
remove the administrator from the picture.

**The CloudTrail events that record a read.** The organization trail records every management
event, read and write, in every region, with log file validation, kept at least 365 days
(`infrastructure/bootstrap/organization/cloudtrail.tf`). A read of the password is two events with
the same `userIdentity`, the login role's session named for its ECS task:

1. `eventSource: secretsmanager.amazonaws.com`, `eventName: GetSecretValue`, `readOnly: true`,
   `requestParameters.secretId` the password secret;
2. `eventSource: kms.amazonaws.com`, `eventName: Decrypt`, `invokedBy: secretsmanager.amazonaws.com`,
   `requestParameters.encryptionContext.SecretARN` the password secret.

A refused attempt is the same `GetSecretValue` event with `errorCode: AccessDenied`. A write is
`PutSecretValue` with a `GenerateDataKey` beside it. `BatchGetSecretValue` is recorded the same way
and is refused by the same deny. So the expected history is **one password read a week, by the login
role**, and anything else in it is an incident.

**When the login runs.** The login task runs **every Wednesday at 03:00 America/Chicago**, three hours
before the run, and logs in every time: it reads the password, calls `POST /login` as `caselist auth
login` does, and writes the new token. Logging in weekly whatever the token's expiry keeps the code
free of expiry rules, heals a token revoked early, and makes the audit trail regular. A refused
login is never retried (`CaselistLoginRejected`, as today), so a wrong password costs one attempt a
week and cannot lock the account. If it fails, the coach is emailed, and the run at 06:00 uses the
previous token if it still works.

**The unattended-login risk, plainly.** The login is a JSON call that takes a username and a
password and returns a token. Nothing in our client answers a second step, nothing in the recorded
runs shows one, and the coach confirmed on 2026-10-23 that Tabroom's login never asks for more than
the password. So the risk is a future change, not a present one. If Tabroom or OpenCaselist ever
starts asking for something an unattended job cannot give (a one-time code, a CAPTCHA, a new-device
confirmation, a forced password change, new terms), the login fails, the coach is emailed, and **the fallback is a login by hand**: on the Mac, signed in
under the writer permission set, `debate-research caselist auth login --token-backend
secretsmanager` (`t02`) prompts as today and writes only the token to the token secret. The weekly run
then proceeds unchanged. A second, separate risk: **the run's requests now come from an AWS address
instead of the coach's home connection.** The login is server-to-server from OpenCaselist to
Tabroom, but `api.opencaselist.com` will see the downloads come from a data centre, and a site may
treat that differently. If it refuses them, the run fails on its codes and emails the coach, and the
fallback is the Mac for that week ((4) below). The coach has told the maintainer that the downloads
are likely to move to the cloud, and the maintainer is fine with it. Clause 12's terms (the API, 10
downloads a minute) do not depend on where the job runs, so the policy needs nothing more for this.

### (3) State: the bucket is the record, and a run works on a restored copy

After the cutover the evidence bucket of the run's home environment is the record of the run's state,
and any data directory, in the task or on the Mac, is a working copy. Nothing new is invented for
evidence: raw sources, published manifests, the parsed store and the index are already in the bucket.
What moves is the state that today lives only in `<data_dir>`, in two classes by what it holds.

**State with no personal data**, under `reports/sync/state/` (the run summaries' existing prefix, which
the everyday credential lists and writes and the removal credential cannot touch):

| Object | Today | Saved |
|---|---|---|
| `caselist-sync-runs.jsonl`, the run log | `<data_dir>/caselist-sync-runs.jsonl` | At the end of a run. Each record is also published, as today, to `reports/sync-runs/<yyyy>/<run-id>.json` |
| `caselist-sync-run-details.jsonl` | `<data_dir>/caselist-sync-run-details.jsonl` | The same; published to `reports/sync-run-details/` as today |
| `caselist-sync-download-starts.json`, the download ledger | `<data_dir>/…` | **Before each download starts**, as the local file is today, so no crash can lose a download from the count of 5 a day |
| `caselist-sync-openev-deliveries.json` | `<data_dir>/…` | When an OpenEv import completes, as today |
| `caselist-sync-pending.json`, the pending-work file | `<data_dir>/…` | Whenever the local file is written |

**State with personal data**, under `manifests/_run-state/`: the **run-state bundle**, one gzipped tar
of the local manifests (`<data_dir>/objects/manifests/`, 18.7 MB today) and the SQLite database
(42.8 MB), about 15 MB compressed (*estimate*). The two are one object because they must agree: the
importer reads its previous snapshot and the disclosures to classify from the database, and the
select stage reads what is held from the manifests.

- **When it is saved.** Only at a moment when every snapshot it records is confirmed in the bucket:
  after a publish stage that confirmed everything, and at the end of the run. A run that dies or
  fails before that leaves the previous bundle, and the next run redoes the weeks after it,
  downloading them again within the ledger's limit. A week redone is late, never lost (ADR-0017
  decision 3). So the cloud never records as imported a snapshot whose bytes are only in a stopped
  task's storage.
- **A withheld manifest is never saved.** Before saving, the run asks the publisher's own rule
  (`WithheldManifests`, as `store sync --push` does since `v1-e30-t25`) whether any local manifest is
  one a publish withholds. If one is, the bundle is not saved and the run fails with the publisher's
  message, which names the removal to run again. There is no second copy of the rule.
- **Removal covers it.** `caselist remove` rewrites the bundle without the removed rows and purges its
  noncurrent versions with the removal credential, which may delete versions under `manifests/`. Its
  key holds no school, team code or file name.

**What is not saved.**

- **Raw sources** are already under `raw/`. A run fetches from there only the sources its parse is
  about to parse and does not hold, normally none, and all of them in a full re-parse.
- **The inbox.** An archive downloaded and not imported is lost with the task, and the next run
  downloads it again.
- **The parsed store** is already published by the parse stage, per-source files first and aggregates
  last.
- **The search index's build directory** (`<data_dir>/tub-index/`, 3.33 GB today) does not move. The
  published build under `reports/tub/search/` is the record. A run restores only the published
  build's `manifest.json`, so the stage can compare the stores' digests and skip a rebuild when nothing
  changed; when they differ it builds afresh, about 305 s on the Mac. `t04` confirms the stage needs
  nothing more and restores the gzip object only if it does.
- **The suppression list** is already `manifests/_suppression/suppression-list.jsonl`, written by every
  removal. The cloud run always has credentials, so it always reads the bucket's copy.
  `LocalFallbackSuppressionList`'s condition, "revisit it the day a second machine imports", is met
  here by never importing from a stale copy: in bucket mode a run with no session cannot read the
  lock and does not start.

**A working copy, restored, not streamed.** At its start a run restores, to its ephemeral storage:
the run-state bundle, the state files, the published index manifest, and **the parsed store's current
version directory** for each configured caselist and `openev` (9.1 GB in 15,344 objects today,
*estimate* under 10 minutes in the region). The parse, the aggregate rebuild and the index build read
the parsed store many times (the index build twice), and the importer queries the database with SQL,
so streaming would mean rewriting every reader to range-read S3. A copy costs one restore.

**The parsed store's restore route** (store sync has skipped `parsed/` since `v1-e29-t12`). It is a
one-way copy: list `parsed/<caselist>/<version>/`, where the version is the directory name this
build's parser and profile versions give, download every object into
`<data_dir>/parsed/<caselist>/<version>/`, and check each file against the SHA-256 the publisher
recorded in its metadata, which `GetObject` returns, so the check costs no request. It never writes
`parsed/` in the bucket; the parsed store's publisher stays its only writer, which is what
`v1-e29-t12` protected. A version directory the bucket does not hold is a full parse, as a fresh
directory is on the Mac. A directory a killed run left partly published is completed by the parse
stage's existing rule.

**A run killed at any stage** leaves the bucket as a Mac run killed there leaves it, because the
publishers already order their writes (sources before manifests, per-source files before aggregates,
the index pointer last), and the state above is saved before the act it records or only once it is
confirmed.

### (4) One runner: a lease on a lock object in the bucket

**The lock object** is `reports/sync/run-lock.json` in the home environment's bucket. It holds no
personal data:

```json
{
  "format_version": 1,
  "home_environment": "dev",
  "state": "held",
  "holder": {"kind": "cloud", "run_id": "20261104T110002Z", "task": "<ECS task id>", "command": "caselist pull"},
  "acquired_at": "2026-11-04T11:00:05Z",
  "renewed_at": "2026-11-04T11:25:05Z",
  "lease_expires_at": "2026-11-04T11:55:05Z",
  "took_over_from": null
}
```

Every change is an S3 conditional write, and only the first of two concurrent writers succeeds:

1. **It exists only once seeded.** The seed at the cutover creates it with `If-None-Match: *`. A run
   never creates one: a bucket with no lock object has no run state, and a run refuses to start from
   an empty state. So a `caselist pull` against the wrong environment's bucket stops before doing
   anything.
2. **Taking it.** A runner reads the object and its ETag, and refuses unless `home_environment` names
   its own environment. If the state is `free`, or `held` with `lease_expires_at` more than five
   minutes past (clock skew), it writes itself in with `If-Match: <that ETag>`. A `412 Precondition
   Failed` means another runner moved first, and this one stops.
3. **The lease** is **30 minutes, renewed every 5** by a background thread, each renewal with
   `If-Match` on the ETag it last wrote. A run therefore survives 25 minutes of failed renewals.
4. **Fencing.** Before every write of a *named* object to a bucket (a manifest, an aggregate,
   `current.json`, a state file, the bundle, the suppression list), the runner renews with `If-Match`
   first. A content-addressed object is the same bytes whoever writes it, so it needs no check. A
   runner whose renewal gets `412` or `404` has lost the lock: it writes nothing more, ends with the
   code `RUN_LOCK_LOST`, and is emailed. The case this is for is a Mac that slept through its lease
   and woke while the cloud run held a new one.
5. **Releasing.** At its end, a runner writes `state: free` with `If-Match`. It never deletes the
   object, so no conditional delete is needed and the object's history is its versions (30 days in
   dev, 365 in prod).
6. **Taking over an expired lease** is automatic, because one task that died must not stop every
   later week. The new holder records `took_over_from`, its run record says so, and the email says so.

**Who takes it.** In bucket mode (`caselist.run_state = "bucket"`, `t04`), **every command that
writes to an evidence bucket**: `caselist pull` in every mode, `caselist remove` and `unsuppress`,
`caselist publish`, `caselist parse --publish`, `tub index publish` and `store sync --push`. A dry
run reads and takes nothing. The local `flock` stays too, for two runs on one machine.

**What the Mac's agent does while the lock is held.** After the cutover the agent is unloaded, so it
does nothing. If it is loaded again, or the coach runs `caselist pull` by hand, the build (in bucket
mode) reads the lock first; while the cloud holds it, the Mac run does nothing at all and ends
`skipped`, with the same banner a run refused by the local lock has today ("person (skipped)") and
the holder's run id and lease in its notification. It writes its record locally only, never to the
bucket, because it did not hold the lock. With no AWS session it cannot read the lock, so it does
not start.

**The fallback week.** When the cloud run is down for a week, the operator disables the cloud
schedule, waits until the lock is `free` or expired, and runs `caselist pull` on the Mac by hand with
a session. It takes the lock, restores the working copy, runs, saves and releases, as the cloud task
does. Then the schedule is enabled again. The Mac keeps its ability to run by hand (`t06` forbids
removing it).

**The cutover, in order** (`t06`):

1. `t02` to `t05` are merged and applied in dev. The run's schedule exists **disabled**, and the
   late-run alarm's actions are off.
2. The coach signs in to AWS on Tuesday evening, so that the Mac's last scheduled run, on Wednesday,
   publishes everything (outcome `completed`, `pending_publish` empty).
3. **The Mac's schedule goes off first:** the agent is unloaded (`launchctl bootout`), its plist is
   kept for the fallback, and its `--caselist` arguments are removed in favour of the setting (5).
4. The operator installs on the Mac a build that has the bucket lock and sets bucket mode, then
   **seeds**: with a session, a command (`t04`) creates the lock object, takes it, uploads the
   run-state bundle and the state files from the Mac's data directory, checks them back, and releases
   it. Every build that can publish from the Mac now takes the lock.
5. The operator starts **one cloud run by hand** (`aws ecs run-task` on the run's task definition).
   Its record, its parse counts and its index's document count are compared with the Mac's (below).
6. The cloud schedule is enabled, then, after its first recorded run, the late-run alarm's actions.
7. At the pilot's promotion the home moves to prod ((7) below), by the same steps against prod.

There are never two schedules, because the Mac's is off before the cloud's exists enabled, and never
two concurrent runners, because the lock admits one. **The comparison `t06` asks for cannot be two
runs of the same week:** a second run would spend the week's downloads twice out of 5 a day and
publish twice. So `t06` compares a cloud run with **the Mac's reproduction of that run's derivations
from the same inputs**: after the cloud run, the Mac restores the working copy under the lock and
re-parses and rebuilds offline into a scratch data directory, without downloading or publishing.
Records, parse counts and the index document count must agree.

**The residual risk** is a build older than the lock run by hand against a bucket: it does not know the
lock. It is the same kind of risk the runbook already names for builds older than `v0.1.0-dev.13`,
and it is handled the same way, by the runbook's rule never to run one, and by step 4 replacing the
Mac's installed build.

### (5) Configuration: the caselists are a setting

The run's caselists are **`caselist.sync_caselists` in the environment's profile**,
`config/profiles/<env>.toml`, bundled into the build, and the run's command is `debate-research
caselist pull` with no `--caselist`. The Mac and the cloud read the same value from the same
build, `config show` and `doctor` show it, and `v1-e34-t30`'s check reads it without the plist. A new
season's caselists are a profile change and a tag, as every other setting the agent reads already is.

The task definition's environment holds no secret, only what makes it the cloud run:
`DEBATE_ENV`, the data directory on the ephemeral volume, `DEBATE_PARSE__WORKERS=8`, the token
store's Secrets Manager backend and secret name (`t02`), `caselist.notifier = sns` and the topic
(`t05`), bucket mode (`t04`), and an AWS profile of none, so the SDK uses the task role.

### (6) Alerts: by email, through one SNS topic per environment

There is no general mail path in the account: budgets send AWS's own email, and the pilot's SES
identity belongs to its user pool and is still in the sandbox. So each environment has one SNS topic,
`debate-<env>-caselist-run-alerts`, with one email subscription, the coach's address from the tfvars
the budgets already use, confirmed once by the coach. Nothing published to it names a school, a team
code, a file or a card, and none of it is a secret, so it is not encrypted with a key of ours.

| Alert | Raised by | Says |
|---|---|---|
| **A failed run** | The run itself: a new `sns` kind of the existing notifier (`caselist.notifier`), sending what the Mac's banners say today: a failed stage with its codes and hint, an expired token, a backlog grown two runs running, a lock lost or taken over | The environment, the run id, the stage and the codes |
| A run that could not speak | An EventBridge rule on `ECS Task State Change`, `STOPPED`, for the run's family, with a container exit code other than 0 | The environment, the ECS task id, the exit code and the stop reason |
| **A failed login** | The login command (`sns:Publish`) and the same task-state rule for the login family | That the weekly login failed, its code, the two fixes ((2) above), and never the account |
| **A late run** | A CloudWatch alarm on `RunsRecorded` (namespace `debate/caselist-run`), from a metric filter on the run's log group that counts one when a run writes its record. Period one day, 7 of 7 periods, missing data breaching | No run recorded in seven days. A missed Wednesday run alarms by about 19:00 Chicago time the same day; a run still going then has already hit its deadline (1) 6 |
| A schedule that could not start a task | The schedules' dead-letter queue, with an alarm at one message | The schedule's name |
| **Who may read the password changed, or someone tried** | EventBridge rules on the CloudTrail events in (2): the write events in the default `ENABLED` state; `GetSecretValue` of the password by any principal but the login role, and every refused attempt, in the `ENABLED_WITH_ALL_CLOUDTRAIL_MANAGEMENT_EVENTS` state, which is what makes a rule match read-only events | The event name, the principal, the time |

The late-run alarm is the cloud's version of `caselist runs`' eight-day caption. CloudWatch allows a
seven-day evaluation range for a period of an hour or more, which is what makes a weekly heartbeat
possible with one alarm. Because missing data breaches, a new alarm would fire at once, so its actions
are enabled only after the first recorded run.

### (7) Environments: one schedule, one home

**There is one run, one schedule, one lock, one ledger and one Tabroom login for the whole account,
in one environment at a time: the home.** Two environments each running their own week would log in
twice, download every archive twice against the same 5 a day, and keep two ledgers that each believed
they had all five.

- **From the cutover, the home is dev.** The run restores from and saves to the dev bucket and
  publishes to dev, as the Mac's agent does today. Prod is published by hand as it is today, but
  from a working copy restored from the dev bucket under the lock instead of from the Mac's data
  directory (`t06`'s runbook).
- **At the pilot's promotion, the home moves to prod.** The same Terraform is applied in prod. Under
  the dev lock, the run-state bundle and the state files are copied to the prod bucket, and the prod
  lock object is seeded naming `home_environment: prod`. The dev lock object is rewritten, held for
  good by a holder of kind `moved`, with `home_environment: prod`, so no dev run starts again. The
  dev schedule is deleted and the prod one enabled. From then on the run publishes to prod only.
  The dev bucket keeps the corpus it holds; the dev pilot serves its seed index (`v1-e39-t10`).
- **A new image is validated in dev before prod uses it**, by running the dev task without
  downloading or publishing: a dry run, and the parse and index stages over a working copy. It never
  takes the home's lock and never publishes to prod.
- **Why not one home in dev publishing to both.** Publishing to prod would need a dev-named role
  that reads prod evidence, which ADR-0010 rule 4 forbids, and would make dev, where things are
  meant to break, the place prod's pipeline lives.

### (8) Monthly cost

For the home environment, at about 4.3 runs a month. Prices are the published `us-east-1` prices read
on 2026-10-22; *estimate* marks a usage figure not measured.

| Line | Usage | Price used (read 2026-10-22) | $/month |
|---|---|---|---:|
| Fargate, the run | 8 vCPU, 16 GB, `arm64`, 100 GiB storage; about 1.5 h a run (*estimate*) × 4.3 | $0.03237984 per vCPU-hour, $0.00356004 per GB-hour, $0.00011088 per GB-hour of storage above 20 GB: $0.3249 an hour | 2.10 |
| Fargate, a full re-parse week | About 1.5 h more, once after a parser version change (*estimate*) | The same | +0.49 that month |
| Fargate, the login | 0.25 vCPU, 0.5 GB, 1 minute (the minimum) × 4.3 | The same rates | 0.00 |
| Public IPv4 address | About 6.5 hours (*estimate*) | $0.005 an hour | 0.03 |
| Secrets Manager | 2 secrets; about 13 API calls | $0.40 per secret-month; $0.05 per 10,000 calls | 0.80 |
| KMS key | 1 key, rotation on | $1 per key-month, plus $1 for each of the first two rotations, so $2 in the second year and $3 after | 1.00 |
| KMS requests | Tens a month; the buckets use S3 Bucket Keys | $0.03 per 10,000, 20,000 a month free account-wide | 0.00 |
| S3 storage | The run-state bundle, about 15 MB a week (*estimate*), kept 365 days as versions in prod; state files under 1 MB | $0.023 per GB-month (ADR-0010) | 0.02 |
| S3 requests | A run: about 15,400 GETs to restore, about 5,300 PUTs and 15,000 HEADs to publish (as the Mac makes today), about 100 lock and state writes | $0.005 per 1,000 PUT and LIST, $0.0004 per 1,000 GET and HEAD | 0.17 |
| CloudWatch Logs | A few MB (*estimate*) | $0.50 per GB ingested, 5 GB free account-wide | 0.00 |
| CloudWatch metric and alarms | 1 metric from a metric filter; 2 alarms | $0.30 per metric-month, $0.10 per alarm-month, before the account-wide free tier | 0.50 |
| EventBridge Scheduler and rules | 2 schedules, 8.6 invocations; rules on AWS service and management events | 14 million invocations free; AWS management events ingested free | 0.00 |
| SNS email | Under 20 a month | First 1,000 a month free, then $2 per 100,000 | 0.00 |
| SQS dead-letter queue | About none | Free tier | 0.00 |
| ECR | One repository, up to five images of about 0.5 GB (*estimate*) | $0.10 per GB-month (ADR-0019) | 0.25 |
| VPC, subnets, internet gateway, S3 gateway endpoint, security group | | No charge | 0.00 |
| **Total** | | | **about 4.90** |

The other environment keeps its key and secrets for validation runs, about $2.05 a month more. Both
fit ADR-0010's budgets. The rejected alternatives cost more: a NAT gateway about $32.85 a month for
each environment; Spot would save about $1.40.

### What V2 replaces, and what E40 must not build

| E40 piece | V2 | Fate |
|---|---|---|
| The credentials key and the two secrets | `v2-e10-t04` (KMS per data class, Secrets Manager module) | **Adopted, not recreated.** `t04` of E10 brings the key into its `kms` module as a data class of its own, `caselist-credentials`, by `moved` or `import` blocks, as it adopts the evidence key. It is not merged into the general `secrets` key, which worker and API roles will decrypt. The resource and key policies above carry over |
| The token store's Secrets Manager backend (`t02`) | `v2-e10-t04`'s `AwsSecretsProvider` | **Kept beside it.** The provider resolves read-only settings secrets; the token store reads and writes. Both use one small Secrets Manager client in `debate_core.integrations`, which E10 extends |
| The run's VPC with public subnets and public IPs | `v2-e10-t05` (two-AZ VPC, private subnets, NAT per ADR-0011) | **Replaced.** E10-t05 forbids tasks in public subnets with public IPs, so the run's task moves into its private subnets and the E40 VPC is destroyed |
| The run's ECR repository | `v2-e10-t05` (`ecr` module: immutable tags, scan on push, KMS) | **Adopted.** E40 creates it with immutable tags, scan on push and KMS encryption from the start, so E10 moves it into its module rather than recreating it |
| The run's cluster, execution role and log groups | `v2-e10-t05` (ECS cluster, shared execution role, per-service log groups) | **Replaced.** The task definitions name E10's cluster and execution role; the log groups move into its module |
| The schedules and the login-then-run order | ADR-0009's Step Functions | **May be wrapped** in a state machine when E13 builds one; the tasks do not change |
| The alert topic, alarms and rules | `v2-e10-t06` (observability baseline) | **Kept**, and adopted into its dashboards |
| The run-state bundle's database | No V2 task yet names the `CaselistRepository`; `v2-e11-t03` implements other ports | **Open.** When V2 moves the caselist records to DynamoDB, the bundle holds manifests only |

**So E40 must not build:** a NAT gateway or interface endpoints, VPC flow logs, a reusable `network`,
`ecr`, `ecs_cluster`, `kms` or `secrets` module, Container Insights or capacity-provider strategies,
a settings-level secret-reference mechanism, or a Step Functions state machine. Its Terraform is one
module, `infrastructure/modules/caselist_run`, called from both environment roots, so that E10 can
lift its pieces out with `moved` blocks.

### What each E40 task builds

| Task | Builds | Changes this record makes to its spec |
|---|---|---|
| `t02` | The key, the two secrets and their policies; the login role, task definition and schedule; the writer permission set; the token store's Secrets Manager backend; `caselist auth set-password` and `caselist auth login --token-backend secretsmanager`; a `caselist auth renew` command for the login task | Adds the writer permission set and `set-password`. The login runs weekly and always logs in, three hours before the run |
| `t03` | The image and the deploy script (`scripts/caselist_run_deploy.sh`, for `dev` or `prod`, under `Debate<Env>CaselistRunDeployer`, which may push to the repository and register run task definitions passing the run role, never the login role); the VPC, the cluster, the run role and task definition, the run's schedule; the container deadline; each stage's start and end in the run's details; the 70% storage warning | Adds the stage times and the storage warning. "Refuses to start while the lock is held" is (4)'s rule |
| `t04` | Bucket mode: the restore, the parsed store's restore route, the state files, the run-state bundle with its save rules, the lock with its lease and fencing in every command that writes a bucket, the seed command, and the removal's handling of the bundle; the store layout document | The spec names only the run's state; (4) puts the lock in every bucket-writing command, which goes beyond "refuses to start" |
| `t05` | The SNS topic and subscription, the notifier's `sns` kind, the task-state rules, the late-run metric and alarm, the dead-letter alarm, the CloudTrail rules on the credentials | Adds the CloudTrail rules (2). Its "existing mail path" is SNS, because the account has no general one |
| `t06` | The cutover in (4), the fallback week, the move of the home at promotion (7) | "Beside a Mac run" becomes the Mac's reproduction of the cloud run's derivations, since a second run of a week would download and publish twice |

These changes are in the five specs as `PM amendment 2026-10-23 (ADR-0020)`.

### The policy, version 1.12

[The data-use policy](../policies/caselist-data-use.md) is amended in the same pull request, as
version 1.12, for the coach's approval on its merge. It changes the E34 gate's item 3 (where the
password and the token live and who reads them, every read logged) and item 8 (the job may run in the
team's AWS account, one runner, the operator still accountable). Because a run's working copy holds
the corpus while the task runs, it also adds that copy to the places personal data may live, to
Prohibited use 10's sanctioned stores and to the dev exception's locations, and adds the run-state
bundle to what a removal reaches. Nothing else changes.

## Consequences

- **An unplugged laptop no longer stops a week.** The run needs no SSO session at 06:00, so the
  `publish_pending` outcome that most Mac runs end with today does not happen in the cloud.
- **The Mac becomes a client of the bucket.** After the cutover, every command that writes to a
  bucket needs a session, takes the lock and works on a restored copy. A hand publish to prod, a
  removal and a fallback week each start with a restore of about 10 GB, a few minutes.
- **A removal has one more object to rewrite,** the run-state bundle, and its noncurrent versions to
  purge. `t04` changes the removal service and the runbook.
- **A crash costs a repeated download, not a lost week.** The run redoes the weeks after its last
  saved state, from the coach's 5 a day. A week with several crashes could be deferred by the
  ledger, which ADR-0017 makes a delay.
- **The password is stored for the first time.** The policy said it never was. It is in one secret,
  readable by one role that only a schedule starts, and every read and every change to who may read
  it is recorded and emailed. An administrator of this account can still reach it through a
  recorded, emailed change. A separate prod account (ADR-0010's revisit trigger) would end that.
- **Downloads come from an AWS address.** The maintainer knows and is fine with it. If the site's
  infrastructure ever treats a data-centre address differently from the coach's home connection,
  the fallback is the Mac.
- **The working set grows with the season,** about 0.87 GB a week at the average so far, and the
  100 GiB volume is resized before it fills, when the run warns.
- **The stage times this record could not measure** are recorded by `t03`, so the first cloud runs
  check the estimates above: the restore, the parse at 8 vCPU, and the parsed-store publish that took
  about 1 h 53 min from the Mac for reasons the records do not show.
- **The cloud run is a second machine for the suppression list's fallback rule.** Bucket mode
  removes the fallback by refusing to run without a session, so no machine imports from a stale
  copy.
- **ADR-0011 is still open.** The run's public subnet is an interim, and `v2-e10-t05` replaces it.

## Alternatives considered

**AWS Batch on Fargate.** A managed queue, retries and a native job timeout around the same Fargate
task. Rejected because the run is one job a week, the scheduler starts an ECS task directly, the
container sets its own deadline, and Batch would be a second orchestration service V2 does not plan.

**Fargate Spot.** Up to 70% cheaper. Rejected in (1) 3: an interruption costs a repeated download from
the maintainer's 5 a day and a late index, to save about $1.40 a month.

**Lambda.** Its 15-minute limit and 10 GB of `/tmp` are both below the run.

**A scheduled EC2 instance.** An instance started and stopped by a schedule could keep an EBS
volume with the data directory and skip the restore. Rejected because it brings an operating system
to patch, a volume that becomes a second copy of the corpus to account for under the policy, and more
parts to start and stop, for a restore of a few minutes.

**A GitHub Actions scheduled workflow.** Free minutes, but a hosted runner has about 14 GB of disk,
and the corpus may never reach a CI runner (the policy's dev exception, limit 4).

**A NAT gateway and private subnets now.** The shape V2 will have, at about $32.85 a month for each
environment, more than dev's budget, for one task a week. It is ADR-0011's to decide.

**Two runs, one in each environment.** Two logins and twice the downloads against one Tabroom
account's 5 a day, with two ledgers that would each count five. Rejected in (7).

**One home in dev publishing to both.** Needs a dev-scoped role reading prod evidence, against
ADR-0010 rule 4. Rejected in (7).

**The token and password in SSM Parameter Store `SecureString`s,** as the pilot keeps its keys.
Parameter Store has no resource policy, so only the key policy and IAM would guard the read, and the
coach decided on Secrets Manager.

**ECS `secrets` injection into the task's environment.** The usual way to give a container a secret.
Rejected in (2): it makes the execution role a reader and puts the password in the process
environment.

**Logging in only when the token is near expiry.** Fewer reads of the password. Rejected because the
expiry is not always given, a token revoked early would not heal itself, and a weekly read makes any
other read stand out.

**Rebuilding the database from the bucket's manifests at the start of each run.** One fewer copy of
personal data in the bucket. Rejected for now because nothing builds the database from manifests
today, and the bucket's manifests differ from the Mac's on purpose where a publish withholds one, so
a rebuild would not reproduce what a Mac run had. It becomes the natural route once V2 designs the
caselist records' DynamoDB tables.

**Streaming the store from S3 instead of restoring it.** Rejected in (3): every reader would change,
and the parsed store is read several times a run.

**A DynamoDB conditional item for the lock.** The standard lease lock, with a TTL attribute. Rejected
because S3 conditional writes give the same compare-and-swap on the bucket the run already uses, with
no table, no new grant and no new service to absorb in V2.

**Deleting the lock object to release it.** S3 supports conditional deletes, but a versioned bucket
leaves a delete marker each time, and an object that always exists lets a run refuse a bucket that
was never seeded. Release writes `free` instead.

**Keeping the run on the Mac with a wake schedule.** `pmset` can wake a Mac for the run, but not one
that is unplugged, closed or away, which is the coach's reason for the move.

## References

- [§5](../architecture/architecture_proposal.md#5-aws-cloud-architecture),
  [§11](../architecture/architecture_proposal.md#11-v1-detailed-architecture),
  [§14](../architecture/architecture_proposal.md#14-security-privacy-and-student-safety),
  [§15](../architecture/architecture_proposal.md#15-reliability-observability-and-cost-controls),
  [§17](../architecture/architecture_proposal.md#17-deployment-and-evolution-plan) of the
  architecture proposal
- [ADR-0009: Async job architecture](0009-async-job-architecture.md): V2 may wrap the two tasks in a
  state machine
- [ADR-0010: One account in us-east-1](0010-primary-aws-region.md): names, tags, budgets, rule 4, the
  revisit trigger
- [ADR-0013: Two environments](0013-two-environments-and-dev-main-promotion.md)
- [ADR-0016](0016-caselist-corpus-is-accumulated.md) and
  [ADR-0017](0017-caselist-corpus-is-retrievable.md): the weekly cadence, the download cap, a late
  week is not a lost one
- [ADR-0019: The student search pilot](0019-student-search-pilot-stack-sign-in-and-hosting.md): the
  index the run refreshes, operator-run deploys
- [The caselist data-use policy](../policies/caselist-data-use.md), version 1.12
- [The evidence store layout](../architecture/evidence-store-layout.md)
- [The weekly sync runbook](../runbooks/caselist-scheduled-sync.md)
- [The epic](../../plan_specs/v1/e40-cloud-caselist-run/epic.yaml) and its tasks
  [`t02`](../../plan_specs/v1/e40-cloud-caselist-run/t02-secrets-token-store-and-login.yaml) to
  [`t06`](../../plan_specs/v1/e40-cloud-caselist-run/t06-cutover.yaml);
  [`v2-e10-t04`](../../plan_specs/v2/e10-aws-foundation/t04-kms-secrets.yaml),
  [`v2-e10-t05`](../../plan_specs/v2/e10-aws-foundation/t05-container-platform.yaml)
- [The task that owns this record](../../plan_specs/v1/e40-cloud-caselist-run/t01-cloud-run-adr.yaml)
  and [its session report](../session-reports/v1-e40-t01-cloud-run-adr.md), which records how each
  figure above was measured

### AWS documentation relied on, read 2026-10-22

| Claim | Source |
|---|---|
| Secrets Manager calls `GenerateDataKey` for `PutSecretValue` and `Decrypt` for `GetSecretValue`; `PutSecretValue` decrypts only when a request changes an existing version; the encryption context `SecretARN` and `SecretVersionId`; `kms:ViaService`; the CloudTrail shape of `GenerateDataKey` and `Decrypt` with `invokedBy` | [Secret encryption and decryption](https://docs.aws.amazon.com/secretsmanager/latest/userguide/security-encryption.html) |
| Conditional writes: `If-None-Match` and `If-Match` on `PutObject`; a delete marker counts as absent; the first of concurrent writers wins and the rest get `412`; `409` on a concurrent delete; conditional deletes exist for general purpose buckets | [Conditional requests](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-requests.html), [Conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html) |
| Fargate ephemeral storage: 20 GiB default, 200 GiB at most, set by `ephemeralStorage`, holds the image, AES-256 encrypted, platform version 1.4.0 | [Fargate task ephemeral storage](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-task-storage.html) |
| Fargate prices for `arm64` and storage; per-second billing with a 1-minute minimum; vCPU and memory combinations; Spot up to 70% off | [AWS Fargate pricing](https://aws.amazon.com/fargate/pricing/) |
| $0.40 per secret-month, $0.05 per 10,000 calls | [Secrets Manager pricing](https://aws.amazon.com/secrets-manager/pricing/) |
| $1 per key-month, $1 more for each of the first two rotations, $0.03 per 10,000 requests, 20,000 free | [AWS KMS pricing](https://aws.amazon.com/kms/pricing/) |
| Logs $0.50 per GB, 5 GB free; $0.10 per alarm, 10 free; $0.30 per custom metric, 10 free | [CloudWatch pricing](https://aws.amazon.com/cloudwatch/pricing/) |
| A seven-day evaluation range for alarms with a period of an hour or more; missing data treatment | [Using CloudWatch alarms](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/AlarmThatSendsEmail.html) |
| Scheduler: 14 million invocations a month free; AWS management events ingested free | [EventBridge pricing](https://aws.amazon.com/eventbridge/pricing/) |
| Read-only management events reach a rule only in the `ENABLED_WITH_ALL_CLOUDTRAIL_MANAGEMENT_EVENTS` state; write events in `ENABLED` | [AWS service events delivered via CloudTrail](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-service-event-cloudtrail.html) |
| SNS email: first 1,000 a month free, then $2 per 100,000 | [Amazon SNS FAQs](https://aws.amazon.com/sns/faqs/) (the pricing page's table did not load) |
| Public IPv4 $0.005 an hour, Fargate tasks included; gateway endpoints free; NAT gateway $0.045 an hour and per GB (the page shows the US East (Ohio) rate; N. Virginia is assumed the same, *estimate*) | [Amazon VPC pricing](https://aws.amazon.com/vpc/pricing/) |
| S3 $0.005 per 1,000 PUT and LIST, $0.0004 per 1,000 GET | [Amazon S3 pricing](https://aws.amazon.com/s3/pricing/) (as quoted by AWS's own solution guides; the page's table did not load) |
