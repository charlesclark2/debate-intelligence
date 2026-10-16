# Session report: v1-e31-t16-version-directory-retention

| | |
|---|---|
| Task | `v1-e31-t16-version-directory-retention` — Superseded parsed-store version directories are retired, locally and in both buckets |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t16-version-directory-retention.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t16-version-directory-retention.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t16-version-directory-retention` |
| Session status | PARTIAL: everything a session can close passes; ac4 and the plan half of ac5 are operator-run after review. Goal left `InProgress` |

## Summary

`debate-research caselist retire` lists every parsed-store version directory with its standing
against the build's parser version, and retires the superseded ones after a dry run and a
confirmation code. On this machine it deletes the directory. In a bucket it tags each object
`debate-retention=superseded`, using the everyday profile, and deletes nothing. The `caselist
parse` dry run now says `new_version: true` for a parser bump and a first parse, and names the
directory the new one supersedes. The evidence bucket module gains the lifecycle rule and the two
tagging grants on `parsed/`, all held by the module's tests.

**Look first at Deviation 1.** As ruled, a tag-filtered `Expiration` counts days from an object's
creation, not from when it was tagged. A 30-day rule would therefore expire a directory older than
30 days at the next lifecycle run, with no grace period at all. I built the rule so that the
30-day grace counts from retirement (expire the tagged current version after 1 day, then keep the
noncurrent version 30 days). That needs the PM's ruling. ac4 (the retirements) and the `terraform
plan` reads in ac5 are operator steps for after the review, so the Goal stays `InProgress`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `retention` (Version directories retired) | Done, apart from the operator's runs | The rule, the command, the honest dry run, the Terraform and the runbook are built and tested. The retirements themselves (ac4) and the plans (ac5) are the operator's |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Node `retention`: Parse tests pass | PASS | `uv run pytest packages/debate_core/tests/application -k "parse or retention"` → `287 passed in 23.84s` at `4932758`. The selection includes all 31 tests of `caselist/test_version_retention.py` and the new dry-run tests |
| ac1: a retention rule in `docs/data/parsed-card-store.md`, consistent with the policy's retention section, and the command lists superseded directories in a dry run | PASS | [Retention](../data/parsed-card-store.md#retention) gives the four standings, what retiring does in each place, the 30-day grace and why it keeps within the policy (Decision 2). `test_the_dry_run_lists_every_directory_with_its_standing_and_counts_and_changes_nothing`, `test_the_bucket_dry_run_counts_tags_only_where_it_might_retire`, CLI `test_the_dry_run_lists_each_directory_with_its_standing_and_changes_nothing` and smoke `test_a_superseded_directory_is_listed_refused_when_current_and_retired_with_its_code` all pass. The policy itself has no row for retired `parsed/` directories yet; a proposed row is under Follow-up work |
| ac2: with confirmation the command removes a superseded directory locally and tags it in a bucket, and refuses the current one, by test against moto | PASS | `caselist/test_version_retention.py`, 31 passed. Locally: `test_a_named_superseded_directory_is_deleted_in_every_caselist_and_nothing_else_changes`. In moto: `test_retiring_in_the_bucket_tags_every_object_of_the_directory_and_deletes_nothing`, which also asserts that every version is still there and that the client sent only `ListObjectsV2`, `GetObjectTagging` and `PutObjectTagging`. Refusals: `test_the_current_directory_is_refused_and_nothing_is_deleted`, `test_a_directory_newer_than_this_build_is_refused_and_nothing_is_deleted`, `test_the_bucket_refuses_its_current_directory_and_one_newer_than_this_build`. **Both refusals shown failing first**, by mutants that remove each guard (below) |
| ac3: the dry run for a new parser version says a new directory will be started and names the one it supersedes, shown failing first | PASS | Red, against the start commit's source (`a80e285`): the five new service tests failed with `assert ('2099.01.01-..., False, None) == ('2099.01.01-...10.12-docx-3')` and the like, `5 failed, 1 passed` (the one that passed is the reuse case, which was already right). The CLI test failed with `assert ('2026.10.12-..., False, None) == ('2026.10.12-...01.01-docx-0')`, which is today's `new_version: false`, `superseded: null`. Green after the fix: `75 passed` over both parse test files |
| ac4: operator-run: `2026.09.20-docx-1` retired in both buckets and `2026.10.10-docx-2` in the dev data directory and both buckets, counts recorded (amended by the PM, 2026-10-16) | NOT RUN | Operator-run after the merge, the Terraform apply and the PM's ruling on Deviation 1. Steps are in [parsed-store-retention.md](../runbooks/parsed-store-retention.md#retiring-20260920-docx-1-and-20261010-docx-2-v1-e31-t16-ac4), and the counts go in [Retired so far](../data/parsed-card-store.md#retired-so-far) |
| ac5: the module gains the lifecycle rule and the two tagging grants on `parsed/`, held by its tests; the dev and prod plans are operator-run and read by the PM | PASS (module and tests) / NOT RUN (plans) | `terraform -chdir=infrastructure/modules/evidence_bucket test` → `Success! 12 passed, 0 failed`. Red first: against the unchanged module the new lifecycle run failed (`retired_parsed_version_directories_expire_after_a_grace_period ... fail`, `Attempt to get attribute from null value`). With the rule added and the grants not yet, the permission-set run failed on the exact action set and on `length(...) == 1` (`- 0 + 1`). Nine Terraform mutants are caught (below). The plans are under Operator follow-ups |

### The refusals and checks, each shown failing

Mutants applied one at a time to committed files by a driver that restores the bytes and checks
them afterwards (`git status --porcelain` printed nothing after each batch). Each row is the result
of running the retention tests with the mutant in place.

| Mutant | Caught by |
|---|---|
| The current directory passes the refusal check | `test_the_current_directory_is_refused_and_nothing_is_deleted`, `test_one_refused_directory_refuses_the_whole_run`, `test_the_bucket_refuses_its_current_directory_and_one_newer_than_this_build` (3 failed) |
| A directory newer than this build passes the refusal check | `test_a_directory_newer_than_this_build_is_refused_and_nothing_is_deleted`, `test_the_bucket_refuses_...` (2 failed) |
| A newer parser version is judged superseded | 4 failed, the rule tests among them |
| The confirmation code is not checked | both `CONFIRMATION_MISMATCH` cases and `test_a_directory_that_changed_since_the_dry_run_is_refused` (3 failed) |
| The local adapter deletes the newest directory when asked | `test_the_adapter_never_deletes_the_newest_directory_a_caselist_has` |
| The local delete follows links | `test_a_link_inside_a_retired_directory_is_deleted_and_what_it_names_is_kept` |
| Lifecycle rule matches another tag key / another tag value | `dev_ages_out_superseded_versions_after_thirty_days` fails, and so does the Python cross-check `test_the_retirement_tag_is_the_one_the_lifecycle_rule_and_the_grant_name` |
| Lifecycle rule scoped to `raw/` | `dev_ages_out_...`, and the cross-check |
| Lifecycle rule drops its tag filter | `dev_ages_out_...` |
| Current version waits 30 days from creation / grace period 365 days | `retired_parsed_version_directories_expire_after_a_grace_period` |
| Tagging grant on the whole bucket / tagging statement also deletes / tagging joins the read-and-publish statement | `operator_permission_set_reads_and_publishes_but_cannot_delete` |

When a lifecycle assertion fails, Terraform 1.16.3 panics while printing it ("value has marks, so
it cannot be serialized as JSON") instead of showing the error message. The run still fails, so
every mutant above counts as caught. This predates the task: breaking the existing `exports/`
expiry assertion crashes the same way. See Follow-up work.

### The whole suite and the static checks

Run as four parts one after another (working agreement 1), each under a 115-second kill: part 2
at `8bfccea`, parts 1, 3 and 4 at `e25e37e`. The only test change between those two commits is in
part 3, and the commits after `e25e37e` change Terraform and docs only.
`uv run --frozen pytest -n auto -m "not slow and not live" --part K/4` gave 1861 passed;
1869 passed and 1 xfailed; 1871 passed and 1 skipped; 1866 passed and 1 xfailed. The first part,
run earlier at a load average of 27, took 106 s and had one failure, which is the next paragraph;
the re-run took 58 s. `uv run --frozen pyright` gave 0 errors. `ruff check` and `ruff format
--check` are clean, `lint-imports` kept 12 of 12 contracts, and `tflint` on the module is clean.
`terraform validate` passes for `envs/dev` and `envs/prod`. `scripts/check_command_blocks.py`
found no `#` comments in 275 shell blocks, and `scripts/docs_index.py --check-descriptions` passed.

Two checks elsewhere caught the new wiring, as they were built to. `test_installation.py` and
`test_doctor.py` keep hand-written lists of the integrations the composition root wires, and both
now list `local.version_directories` and `s3.version_directories`. The doctor test's "two
integrations do not import" fixture now blocks `s3.version_directories` along with `s3`. Without
that, it passed or failed depending on whether an earlier test in the same process had already
imported the submodule.

## Files changed

* `packages/debate_core/src/debate_core/application/caselist_parse.py`: `ParsePlan.new_version` is
  a field, and a run that starts a parser version's first directory supersedes the newest directory
  below it (ac3).
* `packages/debate_core/src/debate_core/application/ports/version_directories.py` (new): the port a
  place is listed and retired through, and the tag key and values.
* `packages/debate_core/src/debate_core/application/caselist/version_retention.py` (new): the rule
  (`standings`), the plan with its refusals and confirmation code, and the service.
* `packages/debate_core/src/debate_core/integrations/local/version_directories.py` (new): this
  machine. It deletes, never follows a link, and refuses the newest directory on its own account.
* `packages/debate_core/src/debate_core/integrations/s3/version_directories.py` (new): the bucket.
  It lists by prefix, reads and writes tags on 16 threads, and keeps any other tag.
* `packages/debate_cli/src/debate_cli/commands/caselist_retire.py` (new), `commands/__init__.py`,
  `container.py`: the command and its wiring. The bucket uses the everyday profile only.
* `packages/debate_cli/src/debate_cli/commands/caselist_parse.py`: the version row says when a dry
  run would start a directory and what it supersedes.
* `infrastructure/modules/evidence_bucket/`: the lifecycle rule `expire-retired-parsed-version-directories`
  (last in the list), the `TagSupersededParsedVersionDirectories` statement, the permission set's
  description, the README, and the module tests.
* Tests: `caselist/test_version_retention.py` (new, 31), `test_caselist_parse.py` (core, +5 and one
  first-run assertion corrected), CLI `test_caselist_retire.py` (new, 12), CLI `test_caselist_parse.py`
  (+1), `test_installation.py` and `commands/test_doctor.py` (the wired list), and
  `tests/smoke/test_caselist_retire.py` (new).
* Docs: `docs/data/parsed-card-store.md` (the dry-run wording, the Retention section, and the
  table of retirements), `docs/runbooks/parsed-store-retention.md` (new), and
  `docs/runbooks/evidence-store.md` (the grant, the rule, and a Later applies row marked "not
  applied yet").
* Spec: ac4 rewritten as the PM amended it on 2026-10-16, with that note.

## Deviations from the spec

1. **The grace period cannot be an `Expiration` on tagged objects, as the 2026-10-15 ruling words
   it.** The spec says "a lifecycle rule on the `parsed/` prefix expires tagged objects and their
   noncurrent versions after a grace period, during which removing the tag undoes it." S3 counts
   an `Expiration`'s days from the object's creation. AWS's own example: a 30-day rule "will queue
   for removal any existing objects that are more than 30 days old"
   ([lifecycle-expire-general-considerations](https://docs.aws.amazon.com/AmazonS3/latest/userguide/lifecycle-expire-general-considerations.html)).
   Tagging does not reset that clock. So `Expiration { days = 30 }` gives a directory written 30 or
   more days before it is retired no grace at all, and gives the two ac4 directories whatever is
   left of 30 days since they were published. `NoncurrentVersionExpiration` counts from the day a
   version became noncurrent. **What is built:** the tagged current version expires 1 day after
   creation (in practice, at the next daily lifecycle run), and the noncurrent version is deleted
   30 days after that. The grace period is then 30 days from retirement for every directory. The
   cost is that "removing the tag undoes it" holds only until that first run. After it, the undo
   is to copy the noncurrent versions back, which the everyday set can already do with
   `GetObjectVersion` and `PutObject`. The runbook has both undos. Switching to the ruling as
   written is a change of two numbers in `main.tf` and in the test file. The relay prompt for the
   PM gives the options.
2. **Restoring sets the tag to `restored`; it does not remove the tag.** The everyday set has no
   `s3:DeleteObjectTagging`, and moto rejects an empty tag set (`PutObjectTagging` with
   `TagSet: []`). I could not confirm that S3 accepts one either. `restored` is not matched by the
   rule, works with the two granted actions, and leaves a record that the directory came back.
3. **A smoke check outside `constraints.packages`.** `tests/smoke/test_caselist_retire.py` is
   required by working agreement 5 for a new CLI command, but `tests/smoke` is not among the
   task's packages. It is offline and local-only.

## Decisions and assumptions

1. **The confirmation is a code, not an interactive prompt.** The CLI has no prompts for
   destructive commands (`caselist remove` uses `--execute`). The forbidden entry asks for "a dry
   run and a confirmation", so `--execute` here also needs `--confirm` followed by a 12-character
   digest of what the dry run showed: the place, the action, and each selected directory with its
   object count and bytes. A plan whose code differs is refused, so the dry run has to have been
   read, and it has to be of the same state. `--execute` also needs the directories named with
   `--version`, and `--confirm-prod` in prod.
2. **The grace period: 30 days, in dev and prod.** The policy's retention section sets upper
   bounds. Parsed cards follow their sources' clock, and noncurrent versions expire after 365 days
   in prod and 30 in dev. Retiring early stays within those bounds. Every source in a superseded
   directory is in the current one, re-read, and stays on its clock. What goes is derived data
   with no personal data, which the parser version named in the directory can rebuild. Thirty days
   is what dev already gives every superseded version and what the dev exception names, and it is
   four weekly pulls, enough to notice a reader that still needed the directory. Prod's 365 days
   exist to recover from a bad publish of evidence, which a retired directory is not. The policy's
   noncurrent row ("expire after 365 days in prod") does not mention this rule; I propose a row
   below.
3. **"Current" is judged per place.** A directory is superseded in a bucket only if that bucket
   holds a directory of the build's parser version. A bucket the new directory has not been
   published to calls the old one `not_yet_superseded` and refuses it, so a place is never left
   with nothing to read.
4. **One refused directory refuses the whole run.** If `--version X` is current in one caselist
   and superseded in another, nothing is retired; `--caselist` narrows the run.
5. **A bucket dry run reads tags only for candidate directories.** Reading tags costs one request
   per object. The plan reads them for the named directories, or for every superseded one, and
   never for the current one.
6. **Local deletion is guarded twice.** The service refuses a directory that is not superseded,
   and the adapter refuses, by itself, the newest directory a caselist has, a name that is not one
   directory, and a version directory that is a link. Inside a directory, a link is deleted as a
   link and never followed.
7. **The new lifecycle rule goes last**, so a plan shows one rule added rather than a changed
   multipart rule.
8. **Restore after the lifecycle has run** is documented as an `aws s3api` loop, not a CLI flag.
   It depends on Deviation 1, and building it before the ruling would be scope the ruling might
   remove.

## Operator follow-ups

All of these wait for the PM. The plans are run and read before anything is applied, and nothing
is applied in a session. The commands assume the ruling on Deviation 1 leaves the Terraform as it
is; if it changes, I re-commit and these are re-run.

### 1. The dev and prod `terraform plan` (for the PM to read)

**Operator command** (expected runtime about 3 min)
Where: this task's worktree, which has the change. The tfvars are copied from `dev-preview` and
`prod-deploy`, which have them; they are gitignored, so `git status` stays clean.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e31-t16-version-directory-retention
git branch --show-current
cp ../dev-preview/infrastructure/envs/dev/owner.auto.tfvars infrastructure/envs/dev/owner.auto.tfvars
cp ../prod-deploy/infrastructure/envs/prod/owner.auto.tfvars infrastructure/envs/prod/owner.auto.tfvars
git status --porcelain
```

Success looks like `task/v1-e31-t16-version-directory-retention` and nothing from `git status`.

```bash
aws sso login --sso-session debate
export AWS_PROFILE=debate-admin
terraform -chdir=infrastructure/envs/dev init -reconfigure -input=false
terraform -chdir=infrastructure/envs/dev plan -input=false -out=/tmp/t16-evidence-dev.tfplan
terraform -chdir=infrastructure/envs/prod init -reconfigure -input=false
terraform -chdir=infrastructure/envs/prod plan -input=false -out=/tmp/t16-evidence-prod.tfplan
```

**What each plan should show, resource by resource**, with `debate-dev-*` in dev and
`debate-prod-*` in prod:

| Resource | Change |
|---|---|
| `module.evidence_store.aws_s3_bucket_lifecycle_configuration.evidence` | update in place: one `rule` added at the end, `id = "expire-retired-parsed-version-directories"`, `status = "Enabled"`, `filter { and { prefix = "parsed/", tags = { "debate-retention" = "superseded" } } }`, `expiration { days = 1 }`, `noncurrent_version_expiration { noncurrent_days = 30 }`. The other three rules are unchanged: 30 days in dev, and in prod Standard-IA at 30 and expiry at 365 |
| `module.evidence_store.aws_ssoadmin_permission_set.evidence_operator[0]` | update in place: `description` only, which gains "and tags superseded parsed/ directories" |
| `module.evidence_store.aws_ssoadmin_permission_set_inline_policy.evidence_operator[0]` | update in place: `inline_policy` gains one statement, `Sid = "TagSupersededParsedVersionDirectories"`, `Action = ["s3:GetObjectTagging", "s3:PutObjectTagging"]`, `Resource = "arn:aws:s3:::debate-<env>-evidence-a7508de8/parsed/*"`. Every other statement is unchanged, and there is no `Delete` anywhere in the diff |
| Everything else | No change: the key, the alias, the bucket and its policy, versioning, encryption, the removal set and its policy, every account assignment, and the site resources |

The summary should be `Plan: 0 to add, 3 to change, 0 to destroy.` in each environment. Stop on
anything else. Most likely, `dev` has moved and this branch is stale (run `scripts/task sync
v1-e31-t16-version-directory-retention` and plan again), or a plan wants to destroy an assignment
(a missing or wrong `owner.auto.tfvars`). Paste both plans' resource lists and summaries to the PM.

### 2. After the PM approves: apply, then check the grant

The applies follow [evidence-store.md](../runbooks/evidence-store.md) steps 3 and 6, from the
saved plans:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e31-t16-version-directory-retention
export AWS_PROFILE=debate-admin
terraform -chdir=infrastructure/envs/dev apply /tmp/t16-evidence-dev.tfplan
```

Then the grant, simulated (about 1 minute). Expect `allowed` on both tagging actions under
`parsed/`, and `implicitDeny` on all three actions under `raw/`:

```bash
export AWS_PROFILE=debate-admin
OPERATOR=$(aws iam list-roles --query 'Roles[?starts_with(RoleName, `AWSReservedSSO_DebateDevEvidenceOperator`)].Arn' --output text)
aws iam simulate-principal-policy --policy-source-arn "${OPERATOR}" --action-names s3:GetObjectTagging s3:PutObjectTagging --resource-arns "arn:aws:s3:::debate-dev-evidence-a7508de8/parsed/probe" --query 'EvaluationResults[].{Action:EvalActionName,Decision:EvalDecision}' --output table
aws iam simulate-principal-policy --policy-source-arn "${OPERATOR}" --action-names s3:PutObjectTagging s3:DeleteObject s3:DeleteObjectTagging --resource-arns "arn:aws:s3:::debate-dev-evidence-a7508de8/raw/caselist/probe" --query 'EvaluationResults[].{Action:EvalActionName,Decision:EvalDecision}' --output table
aws s3api get-bucket-lifecycle-configuration --bucket debate-dev-evidence-a7508de8 --query 'Rules[?ID==`expire-retired-parsed-version-directories`]'
```

The last command should print the rule as the plan showed it. Repeat for prod with `prod` in
place of `dev` and `Prod` in place of `Dev`, and the prod plan file. Record the dates in
[Later applies](../runbooks/evidence-store.md#later-applies).

### 3. ac4: the retirements (after the merge and the applies)

[parsed-store-retention.md](../runbooks/parsed-store-retention.md) is the procedure, with a dry run
before every `--execute`. In order: the dev bucket, the prod bucket, then this machine for
`2026.10.10-docx-2` only. Both directories can be named in one bucket run (`--version
2026.09.20-docx-1 --version 2026.10.10-docx-2`). Each run takes minutes, so it is the operator's.
Success looks like `Tagged` equal to `Objects` in a second dry run. Record each place's objects and
bytes in [Retired so far](../data/parsed-card-store.md#retired-so-far). One precondition is that
`2026.10.12-docx-3` is published to both buckets for every caselist; where it is not, the dry run
says `not_yet_superseded`.

The next day, the dry run should no longer list the retired directories, which shows the lifecycle
ran. **If Deviation 1 is accepted as built, please also check the noncurrent half about 31 days
later.** The `list-object-versions` count in the runbook should be `0`. AWS's documentation does
not say outright that a tag filter is evaluated on a noncurrent version's own tags, though tags
are stored per version. That check is what confirms it.

## Follow-up work

1. **A row for the data-use policy** (the PM's to add at the next close-out; I have not edited the
   policy). In the [Retention](../policies/caselist-data-use.md#retention) table, after "S3
   noncurrent object versions", I propose:
   "| Superseded parsed-store version directories (`v1-e31-t16`) | Until retired with `caselist
   retire`, then a 30-day grace period in dev and prod | Lifecycle rule
   `expire-retired-parsed-version-directories`, on objects tagged `debate-retention=superseded`;
   locally, deleted by the command |"
2. **Terraform 1.16.3 panics when printing a failed lifecycle assertion** in this module's tests
   ("value has marks, so it cannot be serialized as JSON"). A failure still fails the run, but
   nobody sees the error message. This predates the task (breaking the existing `exports/`
   assertion crashes the same way). It belongs to E01 or E29: pin the test runner's Terraform
   version, or reshape the assertions so they compare unmarked values.
3. **Delete markers left behind after the grace period.** A tag-filtered rule cannot also remove
   expired-object delete markers (S3 refuses that combination). They hold no data and cost nothing
   to store, but they stay in version listings. A prefix-only `parsed/` rule with
   `expired_object_delete_marker = true` would clear them. E29.
4. **The everyday set may put any tag on `parsed/` objects**, including the retirement tag on a
   current directory, if the aws CLI is used directly; the command refuses. An
   `s3:RequestObjectTagKeys` condition could limit the grant to the one key. It would need the
   module test's "no condition on object statements" rule extended. E29, if wanted.
5. **No CLI flag to restore after the lifecycle has run**, only the runbook's `aws s3api` loop.
   Worth a flag if Deviation 1 stands and retirements become routine. E31.
6. Commit `908b7df` went in while a test was red: pytest piped into `tail` inside an `&&` chain.
   The next commit fixed it. I am recording it because the branch history shows it.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
