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
directory the new one supersedes. The evidence bucket module gains two lifecycle rules on
`parsed/` and the two tagging grants on `parsed/` only, all held by the module's tests.

The PM ruled on 2026-10-16 (see [the ruling and what it changed](#pm-ruling-of-2026-10-16-and-what-it-changed)).
The grace runs on noncurrent versions, as built. The spec's description and ac2 are amended. A
second rule removes the delete markers retirement leaves, because none did. The runbook's
copy-back is now run as written by a moto test, against a hand-written simulation of the
lifecycle rules. ac4 (the retirements) and the `terraform plan` reads in ac5 are operator steps
for after the review, so the Goal stays `InProgress`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `retention` (Version directories retired) | Done, apart from the operator's runs | The rule, the command, the honest dry run, the Terraform and the runbook are built and tested. The retirements themselves (ac4) and the plans (ac5) are the operator's |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Node `retention`: Parse tests pass | PASS | `uv run pytest packages/debate_core/tests/application -k "parse or retention"` → `293 passed in 10.69s` at `a00ed2f`. The selection includes all 31 tests of `caselist/test_version_retention.py`, the 6 of `caselist/test_version_retention_lifecycle.py`, and the new dry-run tests |
| ac1: a retention rule in `docs/data/parsed-card-store.md`, consistent with the policy's retention section, and the command lists superseded directories in a dry run | PASS | [Retention](../data/parsed-card-store.md#retention) gives the four standings, what retiring does in each place, the 30-day grace and why it keeps within the policy (Decision 2). `test_the_dry_run_lists_every_directory_with_its_standing_and_counts_and_changes_nothing`, `test_the_bucket_dry_run_counts_tags_only_where_it_might_retire`, CLI `test_the_dry_run_lists_each_directory_with_its_standing_and_changes_nothing` and smoke `test_a_superseded_directory_is_listed_refused_when_current_and_retired_with_its_code` all pass. The policy itself has no row for retired `parsed/` directories yet; a proposed row is under Follow-up work |
| ac2: with confirmation the command removes a superseded directory locally and tags it in a bucket, and refuses the current one, by test against moto; the lifecycle expires the current version at its next run and the noncurrent one after the grace period, `--restore` undoes it until that run and copying back does after it (amended by the PM, 2026-10-16) | PASS | **The lifecycle half**, in `caselist/test_version_retention_lifecycle.py` (6 passed): the module's rules, read from `main.tf`, run against moto by a simulation written from AWS's documentation. `test_a_retired_directory_expires_at_the_first_run_and_is_gone_after_the_grace_period[dev, prod]` checks that day 1 expires every tagged current version, day 30 still holds every retired version, day 31 has deleted them, and day 32 has removed the markers. The current directory is untouched throughout. In prod, an untagged older aggregate version stays under the 365-day rule. `test_restore_before_the_first_run_leaves_an_object_no_rule_expires` checks that a restored object survives runs on days 1, 2, 31 and 40. `test_the_runbook_copy_back_restores_the_directory_byte_for_byte_with_the_everyday_grants` runs the runbook's two blocks as written after the first run: the newest version of each key comes back byte for byte, tagged `restored`, and survives later runs. Every request it makes is granted by the everyday set as `operator_access.tf` writes it, with no delete. **The command half**: `caselist/test_version_retention.py`, 31 passed. Locally: `test_a_named_superseded_directory_is_deleted_in_every_caselist_and_nothing_else_changes`. In moto: `test_retiring_in_the_bucket_tags_every_object_of_the_directory_and_deletes_nothing`, which also asserts that every version is still there and that the client sent only `ListObjectsV2`, `GetObjectTagging` and `PutObjectTagging`. Refusals: `test_the_current_directory_is_refused_and_nothing_is_deleted`, `test_a_directory_newer_than_this_build_is_refused_and_nothing_is_deleted`, `test_the_bucket_refuses_its_current_directory_and_one_newer_than_this_build`. **Both refusals shown failing first**, by mutants that remove each guard (below) |
| ac3: the dry run for a new parser version says a new directory will be started and names the one it supersedes, shown failing first | PASS | Red, against the start commit's source (`a80e285`): the five new service tests failed with `assert ('2099.01.01-..., False, None) == ('2099.01.01-...10.12-docx-3')` and the like, `5 failed, 1 passed` (the one that passed is the reuse case, which was already right). The CLI test failed with `assert ('2026.10.12-..., False, None) == ('2026.10.12-...01.01-docx-0')`, which is today's `new_version: false`, `superseded: null`. Green after the fix: `75 passed` over both parse test files |
| ac4: operator-run: `2026.09.20-docx-1` retired in both buckets and `2026.10.10-docx-2` in the dev data directory and both buckets, counts recorded (amended by the PM, 2026-10-16) | NOT RUN | Operator-run after the merge and the Terraform apply. Steps are in [parsed-store-retention.md](../runbooks/parsed-store-retention.md#retiring-20260920-docx-1-and-20261010-docx-2-v1-e31-t16-ac4), and the counts go in [Retired so far](../data/parsed-card-store.md#retired-so-far) |
| ac5: the module gains the lifecycle rule and the two tagging grants on `parsed/`, held by its tests; the dev and prod plans are operator-run and read by the PM | PASS (module and tests) / NOT RUN (plans) | `terraform -chdir=infrastructure/modules/evidence_bucket test` → `Success! 13 passed, 0 failed` at `a00ed2f`, the delete-marker rule's run included. It was red first: `orphaned_delete_markers_under_parsed_are_removed ... fail` on the unchanged rule set. Before that, the tagged rule and the grants were red too: against the unchanged module the new lifecycle run failed (`retired_parsed_version_directories_expire_after_a_grace_period ... fail`, `Attempt to get attribute from null value`). With the rule added and the grants not yet, the permission-set run failed on the exact action set and on `length(...) == 1` (`- 0 + 1`). Nine Terraform mutants are caught (below). The plans are under Operator follow-ups |

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

The lifecycle tests and the delete-marker rule (after the PM's ruling), each mutant applied the
same way:

| Mutant | Caught by |
|---|---|
| Grace period 1 day in `main.tf` | the grace-period test, dev and prod |
| Current version waits 30 days in `main.tf` | the grace-period test (dev, prod) and the copy-back test |
| `restored` written as `superseded` in the port | the restore test, the copy-back test, `test_the_retirement_tag_is_not_restored` |
| Tagging grant moved to `raw/*`, or `PutObjectTagging` dropped | the copy-back test's grants check, and the grants reader's own test |
| Runbook: `awk` keeps the older version / `--tagging-directive COPY` / the copy tagged `superseded` / `IsLatest==true` / the takedown profile | the copy-back test, each one |
| The simulated configuration without the delete-marker rule | the grace-period test, on markers left at day 32 |
| `main.tf`: the marker rule gains a tag filter, covers the whole bucket, or also deletes noncurrent versions | `orphaned_delete_markers_under_parsed_are_removed` |
| `main.tf`: the marker rule also expires objects after 400 days | `dev_ages_out_superseded_versions_after_thirty_days`, whose "no current expiry outside exports/" check refuses it |

When a lifecycle assertion fails, Terraform 1.16.3 panics while printing it ("value has marks, so
it cannot be serialized as JSON") instead of showing the error message. The run still fails, so
every mutant above counts as caught. This predates the task: breaking the existing `exports/`
expiry assertion crashes the same way. See Follow-up work.

### The whole suite and the static checks

At `a00ed2f`, run as four parts one after another (working agreement 1), each under a 115-second
kill, `uv run --frozen pytest -n auto -m "not slow and not live" --part K/4` gave 1863 passed (52 s);
1870 passed and 1 xfailed (47 s); 1872 passed and 1 skipped (47 s); 1868 passed and 1 xfailed
(50 s). Before the ruling, part 1, run at a load average of 27, took 106 s and had one failure,
which is the next paragraph. `uv run --frozen pyright` gave 0 errors. `ruff check` and `ruff format
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
* `infrastructure/modules/evidence_bucket/`: the lifecycle rules `expire-retired-parsed-version-directories`
  and `remove-orphaned-parsed-delete-markers` (the last two in the list), the `TagSupersededParsedVersionDirectories` statement, the permission set's
  description, the README, and the module tests.
* Tests: `caselist/test_version_retention.py` (new, 31), `caselist/test_version_retention_lifecycle.py`
  (new, 6) and its `lifecycle_simulation.py` (the rules run by hand against moto), `test_caselist_parse.py` (core, +5 and one
  first-run assertion corrected), CLI `test_caselist_retire.py` (new, 12), CLI `test_caselist_parse.py`
  (+1), `test_installation.py` and `commands/test_doctor.py` (the wired list), and
  `tests/smoke/test_caselist_retire.py` (new).
* Docs: `docs/data/parsed-card-store.md` (the dry-run wording, the Retention section, and the
  table of retirements), `docs/runbooks/parsed-store-retention.md` (new), and
  `docs/runbooks/evidence-store.md` (the grant, the rule, and a Later applies row marked "not
  applied yet").
* Spec: ac4 rewritten as the PM amended it on 2026-10-16, and the description and ac2 as the PM
  ruled the same day, each with its note.

## Deviations from the spec

1. **The grace period runs on noncurrent versions, not on an `Expiration` of tagged objects.**
   Resolved by the PM on 2026-10-16 (option B), and the spec's description and ac2 are amended.
   S3 counts an `Expiration`'s days from the object's creation
   ([lifecycle-expire-general-considerations](https://docs.aws.amazon.com/AmazonS3/latest/userguide/lifecycle-expire-general-considerations.html)),
   so the 2026-10-15 wording would have given an old directory no grace at all.
2. **Restoring sets the tag to `restored`; it does not remove the tag.** Accepted by the PM,
   2026-10-16. The everyday set has no `s3:DeleteObjectTagging`, and moto rejects an empty tag set.
   The lifecycle filter matches the exact pair `debate-retention=superseded`, and a restored object
   survives every run in `test_restore_before_the_first_run_leaves_an_object_no_rule_expires`.
3. **A smoke check outside `constraints.packages`.** Accepted by the PM, 2026-10-16, under working
   agreement 5. `tests/smoke/test_caselist_retire.py` is offline and local-only.
4. **A second lifecycle rule** the spec did not name, `remove-orphaned-parsed-delete-markers`,
   added on the PM's instruction of 2026-10-16. See the ruling's section below.

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
8. **Restore after the lifecycle has run** is an `aws s3api` loop in the runbook, not a CLI flag,
   as the ruling describes. The loop is held by a test that reads it from the runbook and runs it:
   its `--query` through `jmespath` (the library the AWS CLI applies `--query` with), its `awk`
   program through `awk`, and each `copy-object` with exactly its flags. A flag the test does not
   know fails the test, so the two cannot drift apart.
9. **The lifecycle is simulated, because moto stores a configuration and never runs it.**
   `lifecycle_simulation.py` implements the documented actions these rules use (`Expiration` with
   `Days`, `ExpiredObjectDeleteMarker`, `NoncurrentVersionExpiration`, prefix and tag filters, a
   marker having no tags), counting ages in simulated days. It leaves out transitions, dates,
   `NewerNoncurrentVersions`, size filters and rounding to midnight. It was written from AWS's
   pages, and the configuration it runs is built from `main.tf`'s own values.
10. **The grants check reads `operator_access.tf`** rather than restating the policy. For each
    request the copy-back makes, it works out the actions IAM requires: `ListObjectVersions` needs
    `s3:ListBucketVersions` under the prefix condition, and `CopyObject` from a version needs
    `s3:GetObjectVersion` on the source, `s3:PutObject` on the destination, and
    `s3:PutObjectTagging` when it writes tags. Each must be granted by a statement of the everyday
    set. A test shows the reader refusing what the set does not hold.

## PM ruling of 2026-10-16, and what it changed

* **Option B, and the spec amended**: the description and ac2 now carry the ruling's wording, each
  marked "Amended by the PM, 2026-10-16: S3 counts Expiration from creation, so the grace runs on
  noncurrent versions".
* **The copy-back is tested against moto**: retired, expired by the simulated lifecycle, copied
  back by the runbook's blocks as written, byte for byte, with the everyday grants only (ac2 above).
* **Item 5, the tag filter on noncurrent versions**: if it does not reach them, they fall to the
  general rule and are kept longer, never deleted sooner. The 32-day check is in the runbook and
  under Operator follow-ups, and its result goes in the
  [Retired so far](../data/parsed-card-store.md#retired-so-far) table.
* **Delete markers.** No existing rule cleared expired delete markers under `parsed/`.
  `age-out-superseded-evidence-versions` (`filter {}`) has only `noncurrent_version_expiration`
  and no `expiration`. `expire-bulk-export-archives` has `Expiration { Days = 1 }`, which per AWS
  also cleans up expired delete markers ("When you specify the Days tag, Amazon S3 automatically
  performs ExpiredObjectDeleteMarker cleanup"), but only under `exports/`. The new tagged rule's
  `Days` cleanup cannot reach a marker under `parsed/`, because a marker carries no tags. And S3
  refuses `ExpiredObjectDeleteMarker` beside a tag filter
  ([lifecycle-configuration-examples](https://docs.aws.amazon.com/AmazonS3/latest/userguide/lifecycle-configuration-examples.html)).
  So `remove-orphaned-parsed-delete-markers` was added, with `filter { prefix = "parsed/" }`, no
  tags, and `expiration { expired_object_delete_marker = true }` and nothing else. The module's
  test `orphaned_delete_markers_under_parsed_are_removed` holds it to that, and the "no current
  expiry outside `exports/`" assertion allows an expiration that removes markers only. It cannot
  expire an object: an expired delete marker is one with no version behind it.
* **Items 1 to 4** accepted; item 6 stays as follow-up work.

## Operator follow-ups

All of these wait for the PM. The plans are run and read before anything is applied, and nothing
is applied in a session. The Terraform is as the PM's ruling of 2026-10-16
asked, at `a00ed2f`.

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
| `module.evidence_store.aws_s3_bucket_lifecycle_configuration.evidence` | update in place: two `rule` blocks added after the existing three, which are unchanged (30 days in dev; in prod, Standard-IA at 30 and expiry at 365). First, `id = "expire-retired-parsed-version-directories"`, `status = "Enabled"`, `filter { and { prefix = "parsed/", tags = { "debate-retention" = "superseded" } } }`, `expiration { days = 1 }`, `noncurrent_version_expiration { noncurrent_days = 30 }`. Second, `id = "remove-orphaned-parsed-delete-markers"`, `status = "Enabled"`, `filter { prefix = "parsed/" }` with no tags, `expiration { expired_object_delete_marker = true }`, and no `days`, `date` or noncurrent action |
| `module.evidence_store.aws_ssoadmin_permission_set.evidence_operator[0]` | update in place: `description` only, which gains "and tags superseded parsed/ directories" |
| `module.evidence_store.aws_ssoadmin_permission_set_inline_policy.evidence_operator[0]` | update in place: `inline_policy` gains one statement, `Sid = "TagSupersededParsedVersionDirectories"`, `Action = ["s3:GetObjectTagging", "s3:PutObjectTagging"]`, `Resource = "arn:aws:s3:::debate-<env>-evidence-a7508de8/parsed/*"`. Every other statement is unchanged, and there is no `Delete` anywhere in the diff |
| Everything else | No change: the key, the alias, the bucket and its policy, versioning, encryption, the removal set and its policy, every account assignment, and the site resources |

The three lifecycle actions of a retirement, and the rule each sits in:

| Action | Rule | What it matches |
|---|---|---|
| Expire the current version (put a delete marker in front of it), 1 day after creation | `expire-retired-parsed-version-directories` | `parsed/` objects tagged `debate-retention=superseded`, exactly |
| Delete the noncurrent version, 30 days after it became noncurrent | `expire-retired-parsed-version-directories` | the same, on each version's own tags |
| Remove the delete marker once nothing is behind it | `remove-orphaned-parsed-delete-markers` | `parsed/` by prefix (a marker has no tags) |

Nothing in either plan deletes, and nothing changes outside `parsed/`. Both grants are on
`parsed/*`, both new rules filter on `parsed/`, the marker rule removes only markers with no
version behind them, and the rest of the bucket's configuration, the bucket policy, the key and the
removal set are untouched. The summary should be `Plan: 0 to add, 3 to change, 0 to destroy.` in
each environment. Stop on
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
aws s3api get-bucket-lifecycle-configuration --bucket debate-dev-evidence-a7508de8 --query 'Rules[?starts_with(ID, `expire-retired-parsed`) || starts_with(ID, `remove-orphaned-parsed`)]'
```

The last command should print the two rules as the plan showed them. Repeat for prod with `prod` in
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
ran.

### 4. Thirty-two days after the first lifecycle run: the check the PM asked to keep

For each bucket and one caselist, the runbook's
[check](../runbooks/parsed-store-retention.md#the-next-day-check-the-lifecycle-ran) counts what
is left under the retired directory's `sha256/`. It should print `0` and `0`. A first number above
0 means the tag filter did not reach the noncurrent versions. They then fall to the general rule
and are kept longer, never deleted sooner, so record it and tell the PM. Record the numbers in the
last column of [Retired so far](../data/parsed-card-store.md#retired-so-far).

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
3. **The everyday set may put any tag on `parsed/` objects**, including the retirement tag on a
   current directory, if the aws CLI is used directly; the command refuses. An
   `s3:RequestObjectTagKeys` condition could limit the grant to the one key. It would need the
   module test's "no condition on object statements" rule extended. E29, if wanted.
4. **No CLI flag to restore after the lifecycle has run**, only the runbook's `aws s3api` loop,
   which a test now holds. Worth a flag if retirements become routine. E31.
5. Commit `908b7df` went in while a test was red: pytest piped into `tail` inside an `&&` chain.
   The next commit fixed it. I am recording it because the branch history shows it.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-16

**Notes:**

Accepted as a partial merge. ac4 and the plans in ac5 are operator steps, and the Goal stays
`InProgress` until they are recorded.

**You found the flaw in my 2026-10-15 ruling before building on it.** An `Expiration` counts from
creation, so "30 days on tagged objects" would have given an old directory no grace at all. Option
B makes the grace mean the same thing for every directory. Then, asked about delete markers, you
showed that no existing rule cleared them under `parsed/`, added the one rule that can (prefix only,
markers only), and held it to that by the module's tests.

**The work itself:**

* **Nothing a session controls can delete a current directory.** The service refuses anything not
  superseded, the local adapter refuses the newest directory by itself, and a bucket only ever gets
  a tag. The client sends only `ListObjectsV2`, `GetObjectTagging` and `PutObjectTagging`. Each
  refusal was shown failing by a mutant.
* **The confirmation code is better than a prompt.** It ties `--execute` to the state the dry run
  showed, and it refuses a directory that changed since.
* **The lifecycle is tested, not assumed.** moto stores a configuration and never runs it, so you
  wrote a simulation from AWS's documentation and fed it `main.tf`'s own values. Days 1, 30, 31 and
  32 are checked in dev and prod.
* **The runbook's copy-back is run as written** by a test, which checks every request it makes
  against the everyday set's grants as `operator_access.tf` writes them. The runbook and the test
  cannot drift apart.
* **"Current" is judged per place,** so a bucket the new directory has not reached is never left
  with nothing to read.
* **The honest dry run (ac3)** was shown failing first against the start commit.

**Rulings:**

* **Deviations 1 to 4 and the decisions:** accepted.
* **Follow-up 1, the policy row:** accepted as worded. The PM adds it at the close-out that sets
  this task `Succeeded`, after the applies, so the policy never describes a rule that is not live.
* **Follow-up 2, the Terraform panic:** E01 tooling work, filed with the deferred E01 list.
* **Follow-up 3, limiting the tagging grant to one key:** filed as E29 p3. A mistaken tag on a
  current directory is recoverable for 30 days, but a condition is cheap and removes the risk.
* **Follow-up 4, a restore flag:** no task until retirements are routine.
* **Follow-up 5:** noted. The next commit fixed it, and the suite at `a00ed2f` is green.

**The order of the operator's steps.** This changes Operator follow-up 2 as written:

1. **The plans, now, from this worktree,** as your step 1 says. The operator pastes both resource
   lists and summaries to the PM. Nothing is applied from a task branch.
2. **Dev apply, after the merge,** from the `dev-preview` worktree updated to `dev`. A fresh plan
   there must show the same three changes and nothing else, and the PM reads it before the apply.
   Then come the grant simulation and the rule listing from your step 2.
3. **The dev retirements, after the next agent reinstall.** The runbook needs an installed build
   that carries `caselist retire`, and the reinstall planned for `v1-e34-t23` and `v1-e05-t03` is
   that build. Steps 1, 2 and 4 of the runbook: the dev bucket, then this machine.
4. **Prod apply, after the next promotion,** from `prod-deploy` on `main`, with a fresh plan the
   PM reads, as for every prod apply. Then the prod retirement, the runbook's step 3.
5. **The next-day check and the 32-day check,** recorded in the Retired so far table.

The close-out after step 4 records each run and sets the Goal `Succeeded`. The 32-day check is
recorded at a later close-out and does not hold the Goal.

### Dev, recorded (PM, 2026-10-17)

* **The plans, 2026-10-17:** dev and prod each showed the three expected changes, all updates in
  place: `Plan: 0 to add, 3 to change, 0 to destroy.`
* **The dev apply, 2026-10-17**, from `dev-preview` on `dev`, after the PM read a fresh plan's
  contents:
  * the five rules, the existing three unchanged;
  * one statement added (tagging on `parsed/*` only) and none removed;
  * the description line.

  Afterwards:
  * the simulation allowed both tagging actions under `parsed/` and denied tagging and both
    deletes under `raw/`;
  * the bucket listed both new rules.
* **The provider adds `ObjectSizeGreaterThan: 0`** to the tagged rule's filter, so an empty object
  is never expired: it is kept, never deleted early. The two directories retired held no empty
  object in the dev bucket, and `2026.10.10-docx-2` held none on this machine. The runbook now
  says so. A fix is filed (E29).
* **The agent was reinstalled on `v1.1.0-dev.18` the same day**, which carries `caselist retire`.
* **Retired, 2026-10-17:**
  * the dev bucket: `2026.09.20-docx-1` and `2026.10.10-docx-2`, 8 directories and 22,276 objects
    tagged, and a second dry run showing every object tagged;
  * this machine: `2026.10.10-docx-2`, 4 directories and 11,138 objects deleted, about 6.3 GB,
    leaving only `2026.10.12-docx-3`.

  The counts are in [Retired so far](../data/parsed-card-store.md#retired-so-far).
* **Still to come:** the next-day check, the prod apply and retirement after the next promotion,
  and the 32-day check.
