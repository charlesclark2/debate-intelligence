<!-- docs-index: The cutover of the weekly caselist run from the Mac to the cloud in dev: the Mac's last run, unloading its agent, the seed, the run's image, one run by hand, the comparison, the schedule and the late-run alarm; the fallback week on the Mac; and prod at the pilot's promotion -->
# Runbook: the cutover, where the cloud run takes the weekly schedule and the Mac stops

How the weekly caselist run moves from the coach's Mac to the team's AWS account, in dev, following
[ADR-0020](../adr/0020-weekly-caselist-run-in-the-cloud.md) (4)'s seven steps. Spec:
[`v1-e40-t06-cutover`](../../plan_specs/v1/e40-cloud-caselist-run/t06-cutover.yaml). It builds on
the runbooks of the tasks before it, and says when to use each:
[caselist-cloud-credentials.md](caselist-cloud-credentials.md) (`v1-e40-t02`),
[caselist-cloud-run.md](caselist-cloud-run.md) (`v1-e40-t03`, `v1-e40-t04`) and
[caselist-run-alerts.md](caselist-run-alerts.md) (`v1-e40-t05`). The Mac's agent is
[caselist-scheduled-sync.md](caselist-scheduled-sync.md)'s.

Written for the adult maintainer with administrator access to the account. **Every step here is run
by a human, in order.** An agent session never plans, applies, seeds, starts a run or calls AWS, and
the PM reads every plan before its apply.

## Which machine runs the week

| When | Who runs the Wednesday run | Who may publish to dev | Prod |
|---|---|---|---|
| Until step 3 | The Mac's launchd agent, in local mode | The Mac | Published by hand from the Mac's data directory |
| Steps 3 to 7 | Nobody: the Mac's agent is unloaded, the cloud schedule still off | Only a command holding the bucket's run lock | Not published |
| From step 8 | **The cloud run**, Wednesdays 06:00 America/Chicago | The holder of the bucket's run lock: the cloud run, or a command on the Mac in bucket mode | Published by hand from a copy restored under the dev lock ([below](#until-the-promotion-prod-is-published-by-hand)) |
| A week the cloud run is down | The Mac, by hand ([The fallback week](#the-fallback-week-on-the-mac)) | The same | The same |
| From the pilot's promotion | The cloud run, in prod ([below](#at-the-pilots-promotion-the-runs-home-moves-to-prod)) | Prod's lock holder | The run's home |

There is never more than one runner: the Mac's schedule is off before the cloud's is on, and every
command that writes to the bucket holds the bucket's run lock (`reports/sync/run-lock.json`), which
admits one holder at a time.

## The steps, and their days

| Step | ADR-0020 (4) | When |
|---|---|---|
| [Before you start](#before-you-start) | 1: `t02` to `t05` merged and applied in dev | Before Tuesday 2026-10-27 |
| [1. The Mac's last scheduled run](#step-1--the-macs-last-scheduled-run) | 2 | Sign in Tuesday 2026-10-27 evening; the run is Wednesday 2026-10-28 at 06:00 |
| [2. Unload the Mac's agent](#step-2--unload-the-macs-agent) | 3 | After the Wednesday run has published everything |
| [3. The build with the lock, the agent's caselists, and the seed](#step-3--the-build-with-the-lock-the-agents-caselists-and-the-seed) | 3 and 4 | The cutover session, Thursday 2026-10-29 or Friday 2026-10-30 |
| [4. The run's image](#step-4--the-runs-image-an-image-change-only) | 4 (`v1-e40-t03`'s step 8 apply) | The same session |
| [5. One cloud run by hand](#step-5--one-cloud-run-by-hand) | 5 | The same session, about 2.5 hours |
| [6. The second runner is refused](#step-6--the-second-runner-is-refused) | ac2 | While step 5's run is going |
| [7. The comparison](#step-7--the-comparison) | 5's comparison, ac1 | After step 5's run, about 1.5 hours |
| [8. The cloud schedule on](#step-8--the-cloud-schedule-on) | 6 | After step 7 agrees |
| [9. The late-run alarm's email on](#step-9--the-late-run-alarms-email-on) | 6 | After step 8 |

**Why the Mac goes first.** Once the bucket is seeded, a command in local mode refuses it
(`BUCKET_KEEPS_RUN_STATE`), and a build with this task's dev profile is in bucket mode and refuses
a bucket that is not seeded (`RUN_STATE_NOT_SEEDED`). So the order is fixed: the Mac's last run
publishes in local mode, the agent is unloaded, the new build is installed, and the seed comes
straight after.

## Before you start

**`v1-e40-t02` to `v1-e40-t05` applied in dev**, and the dev pre-release containing this task's merge
published, with its validate-dev run, image job included, green. `v1-e40-t05`'s alerts apply carried
`v1-e40-t04`'s bucket mode into the run's task definition (the PM's ruling (a) on `v1-e40-t05`), so the
image apply of step 4 changes the image alone.

**From this task's merge until step 3's seed, no dev command that writes the bucket runs from a
checkout** (the PM's ruling of 2026-10-26). A checkout of `dev` from the merge on has the dev profile
in bucket mode, and the dev bucket is not seeded until step 3. So a bucket-writing command run from
one, such as a landscape publish from `dev-preview`, `caselist publish` or `tub index publish`, is
refused with `RUN_STATE_NOT_SEEDED`; or, with `DEBATE_CASELIST__RUN_STATE=local` set to get past
that, it would publish to dev outside the lock while the cutover is under way. Wait for the seed.
Commands that only read the bucket, or do not touch it, are unchanged. The Mac's installed agent is
unaffected: it runs the build installed on the Mac, whose profile is the one from before this task,
until step 3 replaces it.

**The worktree every dev apply used**, `caselist-credentials-dev`, moved to `origin/dev`, with the
check that this task is merged in it. Its gitignored `owner.auto.tfvars` is the one every dev apply
read.

**Operator command** (expected runtime ~1 min)
Where: your Mac
```bash
WT="$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/caselist-credentials-dev"
cd "$WT" || echo "STOP: the worktree is missing: $WT"
git fetch origin
git switch --detach origin/dev
test -f ops/caselist_run/compare_cloud_run.py && grep -q '^run_state = "bucket"' config/profiles/dev.toml && echo "ok: $(pwd) at origin/dev $(git rev-parse --short HEAD), the cutover merged" || echo "NOT MERGED: origin/dev has no v1-e40-t06"
git status --porcelain | grep -v 'owner.auto.tfvars' | head -3
```
Success looks like `ok: <the worktree> at origin/dev <commit>, the cutover merged`, and nothing after
it.

**Where dev stands.** Read-only: the run's schedule is off, the late-run alarm's email is off, the
alert subscription is confirmed, and the bucket is not seeded.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
aws sso login --sso-session debate
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output caselist_run_schedule_state
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output caselist_run_late_alarm_actions_enabled
TOPIC=$(AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output -raw caselist_alert_topic_arn)
aws sns list-subscriptions-by-topic --profile debate-admin --region us-east-1 --topic-arn "$TOPIC" --query 'Subscriptions[].SubscriptionArn' --output text
BUCKET=$(AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output -raw evidence_bucket_name)
aws s3api list-objects-v2 --profile debate-dev-evidence --bucket "$BUCKET" --prefix reports/sync/run-lock.json --query 'length(Contents || `[]`)' --output text
```
Success looks like `"DISABLED"`, `false`, an ARN ending `:debate-dev-caselist-run-alerts:<id>` (not
`PendingConfirmation`), and `0`: no lock object, so the bucket is not seeded. A `1` on the last line
means the bucket is already seeded: stop and tell the PM.

## Step 1 — The Mac's last scheduled run

**The last run may be an earlier week's** (PM ruling, 2026-10-25). The dev cutover of 2026-10-25 took
the Mac's run of 2026-10-22 as its last: its record said `completed` with nothing pending and no
pending-work file, so the steps from step 2 on ran that evening and the cloud's first scheduled run
was the next Wednesday. The check below is what decides, not the date: run its "After the run" block
against whichever run is the newest, and go on only on its success line.

ADR-0020 (4) step 2. The Mac's agent runs on Wednesday 2026-10-28 at 06:00 as it always has. It
publishes only with an AWS session, so sign in on **Tuesday evening**, and check its OpenCaselist
token, which lasts about 14 days (ADR-0020 (2), amended).

**Operator command** (expected runtime ~1 min), Tuesday 2026-10-27 evening
Where: your Mac, anywhere
```bash
aws sso login --profile debate-dev-evidence
PLIST="$HOME/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist"
AGENT_PATH=$(plutil -extract EnvironmentVariables.PATH raw "$PLIST")
AGENT_ENV=$(plutil -extract EnvironmentVariables.DEBATE_ENV raw "$PLIST")
env -i HOME="${HOME}" PATH="${AGENT_PATH}" DEBATE_ENV="${AGENT_ENV}" sh -c 'debate-research --json caselist auth status --check' 2>&1 | grep -oE '"status": "(ok|error)"|"code": "[A-Z_]+"'
launchctl print "gui/$(id -u)/com.debate-intelligence.caselist-sync" | grep -E 'state =|runs ='
```
Success looks like `"status": "ok"`, then the agent's `state = not running` and its `runs` count. A
`"code": "CASELIST_AUTH_EXPIRED"`: log the Mac in by hand as
[caselist-cloud-run.md](caselist-cloud-run.md) step 3 says ("If it does not: log the Mac in again"),
then run this block again.

**After the run**, Wednesday 2026-10-28 from about 09:00. Its record must say `completed`, with
nothing owed to the bucket: the seed refuses a Mac that holds anything the bucket does not.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
PLIST="$HOME/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist"
AGENT_PATH=$(plutil -extract EnvironmentVariables.PATH raw "$PLIST")
env -i HOME="${HOME}" PATH="${AGENT_PATH}" DEBATE_ENV=dev sh -c 'debate-research --json caselist runs --last 1' | python3 -I -c 'import json, sys; run = json.load(sys.stdin)["data"]["runs"][0]; print(run["run_id"], run["outcome"], "pending_publish:", len(run.get("pending_publish") or []))'
test -e "$HOME/.debate-research/dev/caselist-sync-pending.json" && echo "STOP: the pending-work file is there" || echo "no pending-work file"
```
Success looks like `20261028T11…Z completed pending_publish: 0`, then `no pending-work file`. A run id
from before Wednesday means the agent has not run yet: wait, and run the block again. `publish_pending`,
or a pending count above zero: finish the publish (`caselist pull --publish-pending`, in local mode,
as [caselist-scheduled-sync.md](caselist-scheduled-sync.md) says under "The pending-work file") and run
this block again. Any other outcome: send the PM the record before going on.

## Step 2 — Unload the Mac's agent

ADR-0020 (4) step 3. `bootout` unloads the agent; its plist stays where it is, for the fallback week.
Not while a pull is running.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
if pgrep -fl 'debate-research( --json)? caselist pull'; then echo "STOP: a caselist pull is running (above)"; else launchctl bootout "gui/$(id -u)/com.debate-intelligence.caselist-sync" && echo "booted out"; fi
launchctl print "gui/$(id -u)/com.debate-intelligence.caselist-sync" >/dev/null 2>&1 && echo "STOP: the agent is still loaded" || echo "agent unloaded"
ls "$HOME/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist"
```
Success looks like `booted out`, `agent unloaded`, and the plist's path: it is kept. From here until
step 8 nothing runs the week.

## Step 3 — The build with the lock, the agent's caselists, and the seed

ADR-0020 (4) steps 3 and 4. Four parts: the build installed on the Mac; a check that every build the
Mac can run is one with the lock; the agent's plist rewritten without its `--caselist` arguments, not
loaded; the seed.

**The release.** The newest dev pre-release containing this task's merge. Set `TAG` in this shell;
later blocks read it and stop if it is empty. `TAG` is always written `${TAG}` before a `:`, because zsh reads
`$TAG:c…` as a modifier on the variable (found in the cutover of 2026-10-25).

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
gh release list --repo charlesclark2/debate-intelligence --limit 3 --json tagName,createdAt --jq '.[] | .tagName + " " + .createdAt'
TAG="$(gh release list --repo charlesclark2/debate-intelligence --limit 1 --json tagName --jq '.[0].tagName')"
git fetch origin tag "$TAG" --no-tags
git cat-file -e "${TAG}:ops/caselist_run/compare_cloud_run.py" && git show "${TAG}:config/profiles/dev.toml" | grep -c -E '^(run_state = "bucket"|sync_caselists = )' && echo "TAG=$TAG has the cutover" || echo "STOP: $TAG has no v1-e40-t06; use a release after its merge"
```
Success looks like `2`, then `TAG=<tag> has the cutover`.

**Install it on the Mac.** `install_channel.sh` rehearses the install and checks the build before it
replaces the one installed ([caselist-scheduled-sync.md](caselist-scheduled-sync.md), "Checking an
installed build").

**Operator command** (expected runtime ~2 min)
Where: `$WT`, in the shell that set `TAG`
```bash
cd "$WT"
if [ -z "$TAG" ]; then echo "STOP: TAG is not set; run the release block first"; else scripts/install_channel.sh "$TAG" 2>&1 | tail -5; fi
```
Success ends with the build's `complete` line and `The build runs on the Python at …, which uv manages.`

**Every build this Mac can run is one with the lock** (ADR-0020's residual risk: a build older than
the lock, run by hand against the bucket, would not know the lock). Each `debate-research` on your
`PATH` is asked its tag, its run state and its caselists, from `$HOME`, as the agent runs it. The
last lines compare the build's caselists with the ones the agent's plist still names.

**Operator command** (expected runtime ~1 min)
Where: your Mac
```bash
cd "$HOME"
for BIN in $(/usr/bin/which -a debate-research); do echo "== ${BIN}: $("$BIN" --json --version | python3 -I -c 'import json, sys; print(json.load(sys.stdin)["data"]["tag"])') $(env -i HOME="$HOME" PATH=/usr/bin:/bin DEBATE_ENV=dev "$BIN" --json config show | python3 -I -c 'import json, sys; s = json.load(sys.stdin)["data"]["settings"]; print(s.get("caselist.run_state"), s.get("caselist.sync_caselists"))')"; done
plutil -extract ProgramArguments json -o - "$HOME/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist" | python3 -I -c 'import json, sys; a = json.load(sys.stdin); print("the plist names", [a[i + 1] for i, x in enumerate(a) if x == "--caselist"])'
```
Success looks like one `==` line for each `debate-research` found, each naming `$TAG`, `bucket` and
`['hsld26', 'hspolicy26', 'hspf26']`, then `the plist names ['hsld26', 'hspolicy26', 'hspf26']`. **Stop
on any other line.** A build that says `local`, `None` or an older tag is one that would publish
without the lock: uninstall it, or take its directory off `PATH`, and run the block again. A plist
naming other caselists than the build: send both lines to the PM, since the profile is then wrong.

**The agent's plist without its `--caselist` arguments** (ADR-0020 (5)). The installer, from this
worktree, rewrites the plist and loads nothing. Its last lines suggest loading the agent: **do not run
them.** The agent stays unloaded; the plist is for the fallback week.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
if launchctl print "gui/$(id -u)/com.debate-intelligence.caselist-sync" >/dev/null 2>&1; then echo "STOP: the agent is loaded; step 2 unloads it"; else ops/launchd/install.sh --debate-research "$HOME/.local/bin/debate-research" 2>&1 | grep -E "^Keeping|^Not carried over|^The agent's pull|^The installed agent followed|^Wrote|^install.sh"; fi
plutil -extract ProgramArguments json -o - "$HOME/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist"
```
Success looks like the `Keeping the installed agent's …` lines (environment `dev`, schedule `Wednesday
at 06:00`, the log and wrapper directories), `Not carried over from the installed plist: the arguments
--caselist hsld26 --caselist hspolicy26 --caselist hspf26 after the wrapper. …`, `The agent's pull
follows the build's caselist.sync_caselists: hsld26 hspolicy26 hspf26.`, `Wrote …`, and a
`ProgramArguments` of the wrapper alone. A line `The installed agent followed …; the build names …`
or any `install.sh:` line: stop and send it to the PM.

**The seed's plan.** It writes nothing anywhere: it lists the lock's key and heads each of the Mac's
manifests in the bucket. The new build is in bucket mode by its profile, so no override is set; one
left in this shell stops the block.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
aws sso login --profile debate-dev-evidence
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; env | grep -o '^DEBATE_[A-Z_]*'; else cd "$HOME" && DEBATE_ENV=dev debate-research --json caselist seed-run-state | grep -oE '"(applied|seeded_already)": (true|false)|"manifests": [0-9]+|"code": "[A-Z_]+"'; fi
```

**What to read, and what stops you.** Go on only with `"applied": false`, `"seeded_already": false`
and `"manifests":` **above zero** (50 on 2026-10-24). Zero is an empty data directory, not a Mac
ready to seed. `"code": "SEED_REFUSED"` stops you: run the block again without the `grep` to read the
reason, and see [caselist-cloud-run.md](caselist-cloud-run.md) step 8, which says what each reason
means.

**The seed.** It creates the lock object with `If-None-Match: *`, uploads the run-state bundle and the
five state files, checks each back against its SHA-256, and releases the lock.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif pgrep -fl 'debate-research( --json)? caselist pull'; then echo "STOP: a caselist pull is running (above)"; else cd "$HOME" && DEBATE_ENV=dev debate-research --json caselist seed-run-state --execute | grep -oE '"applied": (true|false)|"manifests": [0-9]+|"checked_back": \[[^]]*\]|"code": "[A-Z_]+"'; fi
```
Success looks like `"applied": true`, the plan's `"manifests":` count, and `"checked_back":` naming six
keys: `manifests/_run-state/run-state.tar.gz` and the five under `reports/sync/state/`. Anything else:
stop and send the PM the output. From here on the bucket keeps the run's state.

## Step 4 — The run's image: an image change only

`v1-e40-t03`'s step 8 apply, which is an image change alone because `v1-e40-t05`'s apply already
carried bucket mode into the run's task definition. It is not optional: the run's command names no
caselist, and an image from before this task has no `caselist.sync_caselists` in its profile, so a run
on it would be refused with `NO_CASELISTS_CONFIGURED`. The new image is built from `$TAG`: its
profile names the caselists, and its two base images are pinned by digest.

**The dry run**, which builds and checks the image offline and pushes nothing (Docker Desktop must be
running):

**Operator command** (expected runtime ~1 min)
Where: `$WT`, in the shell that set `TAG`
```bash
cd "$WT"
if [ -z "$TAG" ]; then echo "STOP: TAG is not set; run the release block of step 3"; elif env | grep -qE '^(CASELIST_RUN_DEPLOY_PROFILE|DEBATE_RELEASE_REPO)='; then echo "STOP: a deploy override is set in this shell"; else time scripts/caselist_run_deploy.sh dev "$TAG" --dry-run; fi
```
Success looks like seven `ok:` lines, among them `ok: the base image's Python is …, the one
debate-research runs on`, and `Dry run complete. debate-dev-caselist-run:<tag> built and checked`.

**The push**, as the deployer. It pushes the image, registers a run task definition with it for a run
by hand, and prints the digest line.

**Operator command** (expected runtime ~3 min)
Where: `$WT`, in the same shell
```bash
cd "$WT"
aws sso login --sso-session debate
if [ -z "$TAG" ]; then echo "STOP: TAG is not set"; elif env | grep -qE '^(CASELIST_RUN_DEPLOY_PROFILE|DEBATE_RELEASE_REPO)='; then echo "STOP: a deploy override is set in this shell"; else scripts/caselist_run_deploy.sh dev "$TAG" 2>&1 | tee /tmp/caselist-run-deploy.txt | tail -8; fi
grep -E '^pushed: |^registered: |caselist_image_digest = ' /tmp/caselist-run-deploy.txt
```
Success looks like `pushed: …@sha256:<64 hex digits>`, `registered: arn:aws:ecs:…:task-definition/debate-dev-caselist-run:<n>`
and `caselist_image_digest = "sha256:<the same digits>"`.

**The digest, in place of the old one.** Paste the digits the push printed into `DIGEST`.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
DIGEST='sha256:the-64-hex-digits-the-push-printed'
if ! printf '%s' "$DIGEST" | grep -qE '^sha256:[0-9a-f]{64}$'; then echo "STOP: DIGEST is not sha256: and 64 hex digits"; else cp infrastructure/envs/dev/owner.auto.tfvars /tmp/owner.auto.tfvars.before-cutover && sed -i '' -E "s/^caselist_image_digest[[:space:]]*=.*$/caselist_image_digest = \"${DIGEST}\"/" infrastructure/envs/dev/owner.auto.tfvars && grep -c "^caselist_image_digest = \"${DIGEST}\"$" infrastructure/envs/dev/owner.auto.tfvars && diff /tmp/owner.auto.tfvars.before-cutover infrastructure/envs/dev/owner.auto.tfvars | grep -c '^[<>]'; fi
grep -c '^caselist_run_schedule_enabled' infrastructure/envs/dev/owner.auto.tfvars
```
Success looks like `1`, `2`, then `0`: the digest line is the new one, it is the only line that
changed, and nothing enables the run's schedule yet.

**The plan**, saved to a file, so that what the apply applies is what was read.

**Operator command** (expected runtime ~2 min)
Where: `$WT`
```bash
cd "$WT"
if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev init -input=false >/dev/null && AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev plan -input=false -no-color -out=caselist-cutover-image.tfplan | tee /tmp/caselist-cutover-image-plan.txt | tail -5; fi
grep -E '^Plan:|must be replaced|will be destroyed' /tmp/caselist-cutover-image-plan.txt
grep -c 'aws_ssoadmin' /tmp/caselist-cutover-image-plan.txt
```
Expect `Plan: 2 to add, 4 to change, 2 to destroy.`, the two lines
`module.caselist_run.aws_ecs_task_definition.login[0] must be replaced` and `….run[0] must be
replaced`, nothing else replaced or destroyed, and `0`. **An account assignment or a permission set
anywhere in the plan stops everything**: never apply it; `owner.auto.tfvars` is missing a line.

**The plan checked against exactly that shape.** It prints `PLAN OK` only for: the two task
definitions replaced, each with its image changed to the digest in `owner.auto.tfvars` and nothing
else in it changed (the environment, the entry point and command, the roles, the size); the two
schedules repointed at the new revisions and nothing else in them changed, the run's still `DISABLED`
and the login's as `owner.auto.tfvars` leaves it; the two scheduler roles' policies repointed; nothing
else. Anything else prints `PLAN STOP` with the reason.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev show -json caselist-cutover-image.tfplan > /tmp/caselist-cutover-image-plan.json
python3 -I - /tmp/caselist-cutover-image-plan.json infrastructure/envs/dev/owner.auto.tfvars <<'IMAGEPLAN'
import json, re, sys
plan = json.load(open(sys.argv[1]))
owner = open(sys.argv[2]).read()
digest = re.search(r'^caselist_image_digest\s*=\s*"(sha256:[0-9a-f]{64})"\s*$', owner, re.M)
paused = re.search(r"^caselist_login_schedule_enabled\s*=\s*false\s*$", owner, re.M) is not None
run_on = re.search(r"^caselist_run_schedule_enabled\s*=\s*true\s*$", owner, re.M) is not None
m = "module.caselist_run."
expected_replaced = {m + "aws_ecs_task_definition.login[0]", m + "aws_ecs_task_definition.run[0]"}
expected_updates = {
    m + "aws_scheduler_schedule.login[0]": "target", m + "aws_scheduler_schedule.run[0]": "target",
    m + "aws_iam_role_policy.scheduler[0]": "policy", m + "aws_iam_role_policy.run_scheduler[0]": "policy",
}
states = {m + "aws_scheduler_schedule.login[0]": "DISABLED" if paused else "ENABLED", m + "aws_scheduler_schedule.run[0]": "DISABLED"}
changes = [c for c in plan.get("resource_changes", []) if c["change"]["actions"] not in (["no-op"], ["read"])]
replaced = {c["address"]: c["change"] for c in changes if sorted(c["change"]["actions"]) == ["create", "delete"]}
updates = {c["address"]: c["change"] for c in changes if c["change"]["actions"] == ["update"]}
others = sorted(c["address"] + " " + "/".join(c["change"]["actions"]) for c in changes if c["address"] not in replaced and c["address"] not in updates)
problems = []
if digest is None:
    problems.append("owner.auto.tfvars names no image digest")
if run_on:
    problems.append("owner.auto.tfvars enables the run's schedule, which is step 8's apply, not this one")
if any("aws_ssoadmin" in c["address"] for c in changes):
    problems.append("an account assignment or permission set changes: " + str(sorted(c["address"] for c in changes if "aws_ssoadmin" in c["address"])))
outside = sorted(c["address"] for c in changes if not c["address"].startswith(m))
if outside:
    problems.append("changes outside module.caselist_run " + str(outside))
if set(replaced) != expected_replaced:
    problems.append("replacements are " + str(sorted(replaced)) + ", expected only the two task definitions")
if set(updates) != set(expected_updates):
    problems.append("updates missing " + str(sorted(set(expected_updates) - set(updates))) + ", unexpected " + str(sorted(set(updates) - set(expected_updates))))
if others:
    problems.append("other actions " + str(others))
def unknown(value):
    if value is True:
        return True
    if isinstance(value, dict):
        return any(unknown(v) for v in value.values())
    if isinstance(value, list):
        return any(unknown(v) for v in value)
    return False
def definition(change, side):
    try:
        return json.loads((change[side] or {})["container_definitions"])[0]
    except (TypeError, ValueError, KeyError, IndexError):
        return None
def without_arn(value):
    if isinstance(value, dict):
        return {k: without_arn(v) for k, v in value.items() if k != "task_definition_arn"}
    if isinstance(value, list):
        return [without_arn(v) for v in value]
    return value
for address in sorted(expected_replaced & set(replaced)):
    change = replaced[address]
    before, after = definition(change, "before"), definition(change, "after")
    if before is None or after is None:
        problems.append(address + ": its container definitions cannot be read from the plan")
        continue
    old = {v["name"]: v["value"] for v in before.get("environment", [])}
    new = {v["name"]: v["value"] for v in after.get("environment", [])}
    if old != new:
        problems.append(address + " changes its environment: adds " + str(sorted(set(new) - set(old))) + ", removes " + str(sorted(set(old) - set(new))) + ", changes " + str(sorted(k for k in set(old) & set(new) if old[k] != new[k])))
    keys = sorted(k for k in ("name", "essential", "entryPoint", "command", "linuxParameters", "stopTimeout", "logConfiguration", "secrets", "user", "workingDirectory") if before.get(k) != after.get(k))
    if keys:
        problems.append(address + " also changes " + str(keys))
    if digest is not None and not str(after.get("image", "")).endswith("@" + digest.group(1)):
        problems.append(address + " image is " + str(after.get("image")) + ", expected the digest in owner.auto.tfvars")
    if before.get("image") == after.get("image"):
        problems.append(address + " keeps its image, so there is no image change to apply")
    task = sorted(k for k in ("task_role_arn", "execution_role_arn", "cpu", "memory", "family", "network_mode", "requires_compatibilities", "runtime_platform", "ephemeral_storage") if (change["before"] or {}).get(k) != (change["after"] or {}).get(k))
    if task:
        problems.append(address + " changes its " + str(task))
for address, field in sorted(expected_updates.items()):
    change = updates.get(address)
    if change is None:
        continue
    before, after = change["before"] or {}, change["after"] or {}
    unknowns = {k for k, v in (change.get("after_unknown") or {}).items() if unknown(v)}
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k) or k in unknowns)
    if changed != [field]:
        problems.append(address + " changes " + str(changed) + ", expected only " + field)
    if field == "target" and without_arn(before.get("target")) != without_arn(after.get("target")):
        problems.append(address + " changes its target beyond the task definition it starts")
    if address in states and (before.get("state") != states[address] or after.get("state") != states[address]):
        problems.append(address + " is " + str(before.get("state")) + " -> " + str(after.get("state")) + ", expected " + states[address] + " throughout")
if problems:
    print("PLAN STOP: " + "; ".join(problems))
else:
    print("PLAN OK: %d to add, %d to change, %d to destroy; the two task definitions replaced with the image %s and nothing else in them changed; the schedules and their roles' policies repointed; the run's schedule DISABLED and the login's %s; nothing else" % (len(replaced), len(updates), len(replaced), digest.group(1)[:19] + "...", states[m + "aws_scheduler_schedule.login[0]"]))
IMAGEPLAN
```
Success looks like `PLAN OK: 2 to add, 4 to change, 2 to destroy; the two task definitions replaced
with the image sha256:… and nothing else in them changed; …; the run's schedule DISABLED and the
login's ENABLED; nothing else`. **`PLAN STOP` stops everything**: send its line and the plan to the PM.
Either way the PM reads the plan before the apply.

**The apply**, after the PM's word.

**Operator command** (expected runtime ~2 min)
Where: `$WT`
```bash
cd "$WT"
if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev apply -input=false caselist-cutover-image.tfplan; fi
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output caselist_run_schedule_state
```
Success looks like `Apply complete! Resources: 2 added, 4 changed, 2 destroyed.`, then `"DISABLED"`. The
coach gets one `-login-task-changed` email from this apply: that is the rule working
([caselist-run-alerts.md](caselist-run-alerts.md)). A stale plan: plan again. **If the apply stops
partway**, plan again from the same worktree and read the new counts with the PM; never `-target`,
and never create or delete a resource by hand.

## Step 5 — One cloud run by hand

ADR-0020 (4) step 5, and `v1-e40-t03`'s ac2. The deployer starts the newest revision of the run's
family, which step 4's apply made: it takes the bucket's run lock, restores its working copy from
the bucket, runs the week, saves its state and releases the lock.

**The network**, from the root's outputs.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
SUBNETS=$(AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output -json caselist_run_subnet_ids | tr -d '[]" \n')
SECURITY_GROUP=$(AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output -raw caselist_run_security_group_id)
BUCKET=$(AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output -raw evidence_bucket_name)
echo "subnets ${SUBNETS}; security group ${SECURITY_GROUP}; bucket ${BUCKET}"
```
Success looks like two `subnet-` ids joined by a comma, one `sg-` id and the dev bucket's name.

**Start it.** The lock must be free first, and no pull may be running on the Mac.

**Operator command** (expected runtime ~1 min to start; the run takes up to about 2.5 hours)
Where: `$WT`, in the same shell
```bash
cd "$WT"
LOCK_STATE=$(aws s3 cp "s3://${BUCKET}/reports/sync/run-lock.json" - --profile debate-dev-evidence | python3 -I -c 'import json, sys; print(json.load(sys.stdin)["state"])')
if [ -z "$SUBNETS" ] || [ -z "$SECURITY_GROUP" ]; then echo "STOP: run the network block first"; elif [ "$LOCK_STATE" != "free" ]; then echo "STOP: the lock is ${LOCK_STATE}, not free"; elif pgrep -fl 'debate-research( --json)? caselist pull'; then echo "STOP: a caselist pull is running on this Mac (above)"; else TASK=$(aws ecs run-task --profile debate-dev-caselist-run-deployer --region us-east-1 --cluster debate-dev-caselist-run --task-definition debate-dev-caselist-run --launch-type FARGATE --platform-version LATEST --count 1 --network-configuration "awsvpcConfiguration={subnets=[${SUBNETS}],securityGroups=[${SECURITY_GROUP}],assignPublicIp=ENABLED}" --query 'tasks[0].taskArn' --output text); echo "started ${TASK}"; fi
```
Success looks like `started arn:aws:ecs:us-east-1:<account>:task/debate-dev-caselist-run/<id>`. `None`
means it did not start: run the `aws ecs run-task` part again without `--query` to see why.

**Watch it**, every half hour or so. Step 6 is run while it says `RUNNING`.

```bash
aws ecs describe-tasks --profile debate-dev-caselist-run-deployer --region us-east-1 --cluster debate-dev-caselist-run --tasks "$TASK" --query 'tasks[0].[lastStatus,stopCode,containers[0].exitCode]' --output text
aws logs tail debate-dev-caselist-run --profile debate-dev-caselist-run-deployer --region us-east-1 --since 3h | tail -3
```
At the end, `STOPPED	EssentialContainerExited	0`. A non-zero exit is a failed run: the coach is
emailed, and its log's last lines go to the PM. Do not go on to step 7 after a failed run.

**Its record, its details and the lock.** These are `v1-e40-t03`'s step 8 checks
([caselist-cloud-run.md](caselist-cloud-run.md), "Its record reads as a Mac run's does" and "It ran in
bucket mode, and left the lock free"): `caselist runs --remote --last 3` on the Mac lists the cloud run
at the top in the Mac runs' columns, and its details say `"bundle": "saved, …`, `"took_over": null`,
`"parsed_objects":` above zero and `"lock_lost": false`, with the lock `free` and `home_environment`
`dev`. Run those two blocks there, and put the cloud run's id in `RUN_ID` in this shell for step 7.

**Its log: the summary line, and any stop** (the follow-ups of `v1-e40-t05` and `v1-e40-t04`). The run's
summary is one JSON line, which the late-run alarm's metric filter counts. If the log driver split it
into several events, the filter would count nothing and a run that recorded itself would read as
late, so the line is read whole. And if the run was stopped (its deadline, or `ecs stop-task`), the log
shows whether a process-pool parse stopped within the 120 seconds ECS gives after SIGTERM.

**Operator command** (expected runtime ~1 min)
Where: `$WT`, in the same shell
```bash
cd "$WT"
if [ -z "$TASK" ]; then echo "STOP: TASK is not set; it is step 5's start block's"; else aws logs filter-log-events --profile debate-dev-caselist-run-deployer --region us-east-1 --log-group-name debate-dev-caselist-run --start-time "$(( ($(date +%s) - 6 * 3600) * 1000 ))" --output json > /tmp/caselist-run-events.json && aws ecs describe-tasks --profile debate-dev-caselist-run-deployer --region us-east-1 --cluster debate-dev-caselist-run --tasks "$TASK" --output json > /tmp/caselist-run-task.json && python3 -I - /tmp/caselist-run-events.json /tmp/caselist-run-task.json "${TASK##*/}" <<'RUNLOG'
import json, sys
from datetime import datetime
events = [e for e in json.load(open(sys.argv[1]))["events"] if sys.argv[3] in e.get("logStreamName", "")]
task = json.load(open(sys.argv[2]))["tasks"][0]
summaries = [e for e in events if '"command": "caselist pull"' in e["message"]]
for e in summaries:
    try:
        json.loads(e["message"])
        whole = "one whole JSON object"
    except ValueError:
        whole = "NOT one JSON object: split"
    print("summary line: %d bytes, %.1f%% of the 262144-byte event limit, %s" % (len(e["message"].encode()), 100 * len(e["message"].encode()) / 262144, whole))
print("summary lines found: %d" % len(summaries))
stops = [e for e in events if "SIGTERM received" in e["message"]]
if not stops:
    print("SIGTERM: none in this run; the pool's stop was not exercised")
else:
    stopped = datetime.fromisoformat(task["stoppedAt"].replace("Z", "+00:00")).timestamp()
    print("SIGTERM: received; the task stopped %.0f s later (ECS allows 120 s)" % (stopped - stops[0]["timestamp"] / 1000))
RUNLOG
fi
```
Success looks like `summary line: <n> bytes, <p>% of the 262144-byte event limit, one whole JSON
object`, `summary lines found: 1`, and, for a run that finished by itself, `SIGTERM: none in this run;
the pool's stop was not exercised`. Send the three lines to the PM. `split`, or `found: 0`, stops step
9: the alarm would not count this run. A run that was stopped prints how long it took to stop: over
120 s means the pool's workers outlived the SIGTERM and ECS killed them, which the PM files.

## Step 6 — The second runner is refused

ac2. While step 5's run holds the lock, a `caselist pull` on the Mac, in bucket mode by its profile,
reads the lock first, finds the cloud run's live lease, does nothing at all and ends with
`RUN_LOCK_HELD`, naming the cloud run. It downloads nothing, writes nothing to the bucket, and keeps
its record on the Mac. Run it **only while the cloud run is `RUNNING` with at least 20 minutes of
lease left**; the block checks both, so that no pull can start after the cloud run has released the
lock.

**Operator command** (expected runtime ~1 min)
Where: `$WT`, in step 5's shell
```bash
cd "$WT"
STATUS=$(aws ecs describe-tasks --profile debate-dev-caselist-run-deployer --region us-east-1 --cluster debate-dev-caselist-run --tasks "$TASK" --query 'tasks[0].lastStatus' --output text)
LEFT=$(aws s3 cp "s3://${BUCKET}/reports/sync/run-lock.json" - --profile debate-dev-evidence | python3 -I -c 'import json, sys; from datetime import datetime, timezone; b = json.load(sys.stdin); h = b.get("holder") or {}; print(int((datetime.fromisoformat(b["lease_expires_at"].replace("Z", "+00:00")) - datetime.now(timezone.utc)).total_seconds() // 60) if b.get("state") == "held" and h.get("kind") == "cloud" else -1)')
if [ "$STATUS" != "RUNNING" ]; then echo "STOP: the cloud run is ${STATUS}, not RUNNING"; elif [ "$LEFT" -lt 20 ]; then echo "STOP: the cloud run's lease has ${LEFT} minute(s) left, or it does not hold the lock"; elif env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; else (cd "$HOME" && DEBATE_ENV=dev debate-research --json caselist pull) | grep -oE '"status": "(ok|error)"|"code": "[A-Z_]+"|cloud run [0-9TZ]+ \(`caselist pull`\) holds the bucket.s run lock'; fi
```
Success looks like `"status": "error"`, `"code": "RUN_LOCK_HELD"`, and `cloud run <step 5's run id>
(`caselist pull`) holds the bucket's run lock`. Send the PM the output and the time: that is ac2's
evidence that a second runner is refused. A `STOP:` line changes nothing: wait for a moment the
block allows, or, if the cloud run has finished, leave this check for the next run by hand.

## Step 7 — The comparison

ac1, and ADR-0020 (4)'s comparison. The comparison is not a second run of the week: the Mac restores
step 5's working copy into a scratch directory under the lock, re-parses every store the run's index
read, rebuilds the index from the re-parse, and compares source records, occurrence records and the
index's counts with the cloud's. Nothing is downloaded from OpenCaselist and nothing is published.
What it is and how it reads its counts is
[`ops/caselist_run/compare_cloud_run.py`](../../ops/caselist_run/compare_cloud_run.py)'s docstring.

The scratch directory holds a copy of the corpus for as long as it exists, so it lives beside the
data directory under `~/.debate-research/`, and it is removed in the last block below.

**Room for it.** The restored parsed store, its re-parse, the raw sources and the index: about 25 GB.

**Operator command** (expected runtime ~1 min)
Where: your Mac
```bash
df -g "$HOME" | awk 'NR == 2 { print $4 " GB free" }'
```
Success looks like 40 GB free or more. Less: make room first.

**The comparison.** It runs for about 1.5 hours (restore 10 to 20 minutes over the home connection,
the re-parse 40 to 60, the index about 5) with the installed build, under `caffeinate` so that the
Mac does not sleep. Not while a cloud run is going: it restores under the lock and would wait for it.
Run it from `$WT`, so that the record lands in the checkout's `docs/data/`.

**Operator command** (expected runtime ~1.5 h)
Where: `$WT`, in the shell that set `RUN_ID`
```bash
cd "$WT"
SCRATCH="$HOME/.debate-research/dev-comparison-${RUN_ID}"
if ! printf '%s' "$RUN_ID" | grep -qE '^[0-9]{8}T[0-9]{6}Z$'; then echo "STOP: RUN_ID is not step 5's run id"; elif [ -e "$SCRATCH" ]; then echo "STOP: ${SCRATCH} exists already"; else caffeinate -i python3 -I ops/caselist_run/compare_cloud_run.py --run-id "$RUN_ID" --scratch "$SCRATCH" --record docs/data/caselist-cloud-run-comparison.md 2>/tmp/caselist-comparison.err | tee /tmp/caselist-comparison.txt | tail -40; fi
```
Success looks like the record's tables and `compare: AGREE: 0 difference(s)`, exit 0. Send the PM
`/tmp/caselist-comparison.txt` (counts only) and the record at
`docs/data/caselist-cloud-run-comparison.md`, which the session commits.

* `compare: DIFFER: <n> difference(s)`: the record's last section says where. **Stop before step 8**
  and send it to the PM. A source that timed out on one machine and not the other is the likeliest
  real difference; anything in the occurrence records or the index is a finding.
* `compare: STOP: …`: nothing was compared and no record written. `the bucket's newest run is …, not
  …` means another run has recorded since step 5; `failed with RUN_LOCK_HELD` means a runner held the
  lock, so wait and run it again with a new scratch directory. The progress of each step is in
  `/tmp/caselist-comparison.err`.

**Removing the copy**, once the PM has the record. It is a copy of the corpus that a removal does not
reach, so it is not kept.

**Operator command** (expected runtime ~1 min)
Where: your Mac
```bash
SCRATCH="$HOME/.debate-research/dev-comparison-${RUN_ID}"
case "$SCRATCH" in "$HOME/.debate-research/dev-comparison-2"*) rm -rf "$SCRATCH" && echo "removed ${SCRATCH}" ;; *) echo "STOP: ${SCRATCH} is not a comparison's copy" ;; esac
ls -d "$HOME"/.debate-research/dev-comparison-* 2>/dev/null | wc -l
```
Success looks like `removed …` and `0`.

## Step 8 — The cloud schedule on

ADR-0020 (4) step 6, after step 7 agrees. From here the cloud run takes the Wednesday run. The switch
goes in the gitignored `owner.auto.tfvars`, like the image digest.

**The switch, and the plan.**

**Operator command** (expected runtime ~2 min)
Where: `$WT`
```bash
cd "$WT"
grep -q '^caselist_run_schedule_enabled' infrastructure/envs/dev/owner.auto.tfvars || printf 'caselist_run_schedule_enabled = true\n' >> infrastructure/envs/dev/owner.auto.tfvars
grep -cE '^caselist_run_schedule_enabled += +true$' infrastructure/envs/dev/owner.auto.tfvars
if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev plan -input=false -no-color -out=caselist-run-schedule.tfplan | tee /tmp/caselist-run-schedule-plan.txt | tail -3; fi
grep -E '^Plan:|^  # ' /tmp/caselist-run-schedule-plan.txt
```
Expect `1`, then exactly `Plan: 0 to add, 1 to change, 0 to destroy.` and the one resource
`module.caselist_run.aws_scheduler_schedule.run[0] will be updated in-place`. A `0` on the first line
means the file sets the switch another way: make it `caselist_run_schedule_enabled = true` by hand.

**The plan checked against exactly that shape.** `PLAN OK` only for the run's schedule updated in
place from the state it was in to the one `owner.auto.tfvars` sets, and nothing else changed in it or
anywhere. The same check serves the fallback week, which turns it off and on again.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev show -json caselist-run-schedule.tfplan > /tmp/caselist-run-schedule-plan.json
python3 -I - /tmp/caselist-run-schedule-plan.json infrastructure/envs/dev/owner.auto.tfvars <<'SCHEDULEPLAN'
import json, re, sys
plan = json.load(open(sys.argv[1]))
owner = open(sys.argv[2]).read()
switch = re.search(r"^caselist_run_schedule_enabled\s*=\s*(true|false)\s*$", owner, re.M)
address = "module.caselist_run.aws_scheduler_schedule.run[0]"
want = "ENABLED" if switch is not None and switch.group(1) == "true" else "DISABLED"
was = "DISABLED" if want == "ENABLED" else "ENABLED"
def unknown(value):
    if value is True:
        return True
    if isinstance(value, dict):
        return any(unknown(v) for v in value.values())
    if isinstance(value, list):
        return any(unknown(v) for v in value)
    return False
changes = [c for c in plan.get("resource_changes", []) if c["change"]["actions"] not in (["no-op"], ["read"])]
problems = []
if switch is None:
    problems.append("owner.auto.tfvars does not set caselist_run_schedule_enabled to true or false")
if any("aws_ssoadmin" in c["address"] for c in changes):
    problems.append("an account assignment or permission set changes: " + str(sorted(c["address"] for c in changes if "aws_ssoadmin" in c["address"])))
if [(c["address"], c["change"]["actions"]) for c in changes] != [(address, ["update"])]:
    problems.append("changes are " + str(sorted(c["address"] + " " + "/".join(c["change"]["actions"]) for c in changes)) + ", expected only " + address + " updated in place")
else:
    change = changes[0]["change"]
    before, after = change["before"] or {}, change["after"] or {}
    unknowns = sorted(k for k, v in (change.get("after_unknown") or {}).items() if unknown(v))
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    if changed != ["state"] or unknowns:
        problems.append("the run's schedule changes " + str(changed) + " with unknown " + str(unknowns) + ", expected only its state")
    if before.get("state") != was or after.get("state") != want:
        problems.append("the run's schedule goes " + str(before.get("state")) + " -> " + str(after.get("state")) + ", expected " + was + " -> " + want)
print("PLAN OK: 0 to add, 1 to change, 0 to destroy; the run's schedule " + was + " -> " + want + ", nothing else" if not problems else "PLAN STOP: " + "; ".join(problems))
SCHEDULEPLAN
```
Success looks like `PLAN OK: 0 to add, 1 to change, 0 to destroy; the run's schedule DISABLED ->
ENABLED, nothing else`. **`PLAN STOP` stops everything**: send its line and the plan to the PM. Either
way the PM reads the plan before the apply.

**The apply**, after the PM's word.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev apply -input=false caselist-run-schedule.tfplan; fi
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output caselist_run_schedule_state
```
Success looks like `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.`, then `"ENABLED"`. The
first scheduled cloud run is the next Wednesday at 06:00 Chicago time; the login runs at 03:00 before
it, as it has since `v1-e40-t02`'s apply B.

## Step 9 — The late-run alarm's email on

ADR-0020 (4) step 6, after the first recorded cloud run, which is step 5's. Run the three blocks of
[caselist-run-alerts.md](caselist-run-alerts.md), "At the cutover: the late-run alarm emails", as they
are written: the check that the alarm has left `ALARM` (`OK	False`, then `0`), the plan of exactly
`Plan: 0 to add, 1 to change, 0 to destroy.` with `~ actions_enabled = false -> true` alone, and the
apply after the PM's word (`Resources: 0 added, 1 changed, 0 destroyed.`, then `true`). If step 5's
log read `split` or `found: 0`, the alarm has not counted the run: do not turn its email on, and tell
the PM.

The cutover is done. The Mac's agent stays unloaded, with its plist kept for the fallback week; the
Mac no longer needs its own OpenCaselist token renewed every two weeks, except for a fallback week.

## The fallback week on the Mac

When the cloud run cannot run a week (an AWS outage, a refused login it cannot recover from, a broken
image), the Mac runs that week by hand, in bucket mode: it takes the same lock, restores its working
copy from the bucket into its data directory, runs, saves the state back and releases the lock, as the
cloud task does (ADR-0020 (4), "The fallback week"). The Mac keeps that ability: `v1-e40-t06` forbids
removing it. Three things, in this order: the cloud schedule off; the run on the Mac; the schedule on
again.

**The cloud schedule off.** Set the switch to `false`, then plan and check as in step 8: the check
then expects `ENABLED -> DISABLED`.

**Operator command** (expected runtime ~2 min)
Where: `$WT`
```bash
cd "$WT"
sed -i '' -E 's/^caselist_run_schedule_enabled[[:space:]]*=.*$/caselist_run_schedule_enabled = false/' infrastructure/envs/dev/owner.auto.tfvars
grep -cE '^caselist_run_schedule_enabled += +false$' infrastructure/envs/dev/owner.auto.tfvars
if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev plan -input=false -no-color -out=caselist-run-schedule.tfplan | tee /tmp/caselist-run-schedule-plan.txt | tail -3; fi
```
Expect `1` and `Plan: 0 to add, 1 to change, 0 to destroy.`. Then step 8's check block, which must
print `PLAN OK: …; the run's schedule ENABLED -> DISABLED, nothing else`, and step 8's apply block,
which ends `"DISABLED"`. The PM reads the plan first, as for every apply.

**The lock free, the Mac's token working.** A cloud run that died leaves its lease until it expires,
at most 30 minutes after its last renewal; the Mac's pull takes an expired lease over by itself and
says so, but wait for `free` or `expired` before starting.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
BUCKET=$(AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output -raw evidence_bucket_name)
aws sso login --profile debate-dev-evidence
aws s3 cp "s3://${BUCKET}/reports/sync/run-lock.json" - --profile debate-dev-evidence | python3 -I -c 'import json, sys; from datetime import datetime, timezone; b = json.load(sys.stdin); e = b.get("lease_expires_at"); print(b["state"], b["home_environment"], "expired" if b["state"] == "held" and datetime.fromisoformat(e.replace("Z", "+00:00")) < datetime.now(timezone.utc) else "")'
(cd "$HOME" && DEBATE_ENV=dev debate-research --json caselist auth status --check) | grep -oE '"status": "(ok|error)"|"code": "[A-Z_]+"'
```
Success looks like `free dev` (or `held dev expired`), then `"status": "ok"`. `held dev` without
`expired`: a runner holds the lock; wait, and read it again. `CASELIST_AUTH_EXPIRED`: log the Mac in
(`debate-research caselist auth login`, with `DEBATE_ENV=dev`), then read it again.

**The week, on the Mac.** A real pull: it downloads the week's archives within the day's five,
imports, publishes, parses and refreshes the index, holding the lock throughout. Its first part
restores the working copy, about 10 GB, into `~/.debate-research/dev`. It runs for about an hour on
the Mac; keep it awake.

**Operator command** (expected runtime ~1 to 2 h)
Where: your Mac
```bash
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif pgrep -fl 'debate-research( --json)? caselist pull'; then echo "STOP: a caselist pull is running (above)"; else cd "$HOME" && caffeinate -i env DEBATE_ENV=dev debate-research --json caselist pull > /tmp/caselist-fallback-week.json; echo "exit $?"; grep -oE '"succeeded": (true|false)|"archives_downloaded": [0-9]+|"objects_published": [0-9]+|"code": "[A-Z_]+"' /tmp/caselist-fallback-week.json | head -8; fi
```
Success looks like `exit 0`, `"succeeded": true` and the counts. Then `debate-research caselist runs
--remote --last 3` lists it beside the cloud's runs. Exit `3` is transient and `1` a verdict, as for
every pull ([caselist-scheduled-sync.md](caselist-scheduled-sync.md), "What the exit code says").

**The cloud schedule on again**, once the cloud run's problem is fixed: step 8's three blocks as
written, ending `"ENABLED"`. **The late-run alarm** counts only the cloud's runs, so after a fallback
week it emails if seven days pass with no cloud run recorded; that is the alarm working.

## Until the promotion: prod is published by hand

ADR-0020 (7): from the cutover the run's home is dev, and prod is published by hand as before, but
from a working copy restored from the dev bucket under the dev lock rather than from the Mac's data
directory, which no longer holds the weeks the cloud ran. `caselist restore-run-state --with-sources`
(`v1-e40-t10`) makes that copy: the run's manifests, database, state and parsed store, and the raw
sources of the weeks you name, each checked against the digest its manifest names, all into a new
directory beside the data directory and nowhere else. The publish then reads the copy, one caselist at
a time, and the copy is deleted at the end of the step: it is a copy of the corpus that a removal does
not reach, kept for the length of the step and no longer
([data-use policy](../policies/caselist-data-use.md), version 1.18).

Not while a cloud run is going: the restore holds the dev lock, and is refused with `RUN_LOCK_HELD`
while a run does. Wednesday after the run has recorded, or any day after, is the time. Everything below
runs in one terminal window on your Mac, which keeps `WEEK` from the first block to the last.

**Which weeks prod lacks.** The cloud runs' records say which snapshots each imported. Read the last
three:

**Operator command** (expected runtime ~1 min)
Where: your Mac
```bash
aws sso login --profile debate-dev-evidence
cd "$HOME" && env -u DEBATE_STORAGE__DATA_DIR DEBATE_ENV=dev debate-research --json caselist runs --remote --last 3 | python3 -I -c 'import json, sys; [print(r["run_id"], r["outcome"], "imported:", ", ".join(r.get("snapshots_imported") or ["nothing"])) for r in json.load(sys.stdin)["data"]["runs"]]'
```
Success looks like one line per run, newest first, such as `20261104T110002Z completed imported:
hsld26 2026-11-04, hspolicy26 2026-11-04, hspf26 2026-11-04`. The date after each caselist is the
week's snapshot. Every week imported since the last hand publish is owed to prod. Below, `WEEK` is one
of them; for two weeks, do this whole section once per week, or add a second `--snapshot <date>` to the
restore and a publish per week.

**Room for the copy.** About 10 GB for the restored parsed store and database, and the week's sources,
which the restore states before it fetches and refuses to fetch without room for, with 1 GiB to spare.

**Operator command** (expected runtime ~1 min)
Where: your Mac
```bash
df -g "$HOME" | awk 'NR == 2 { print $4 " GB free" }'
```
Success looks like 20 GB free or more. Less: make room first.

**The copy, with the week's sources.** Set `WEEK` to the snapshot date read above. The block refuses a
shell with a `DEBATE_` override, a pull running on this Mac, a `WEEK` that is not a date and a copy
that exists already; then it signs in to dev and restores. It runs for 15 to 25 minutes over the home
connection, under `caffeinate`.

**Operator command** (expected runtime ~15 to 25 min)
Where: your Mac, in the window that keeps `WEEK`
```bash
WEEK=2026-11-04
COPY="$HOME/.debate-research/prod-publish-${WEEK}"
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif pgrep -fl 'debate-research( --json)? caselist pull'; then echo "STOP: a caselist pull is running (above)"; elif ! printf '%s' "$WEEK" | grep -qE '^20[0-9]{2}-[0-9]{2}-[0-9]{2}$'; then echo "STOP: WEEK is not a snapshot date"; elif [ -e "$COPY" ]; then echo "STOP: ${COPY} exists already"; else aws sso login --profile debate-dev-evidence && cd "$HOME" && caffeinate -i env DEBATE_ENV=dev debate-research --json caselist restore-run-state --into "$COPY" --with-sources --snapshot "$WEEK" > /tmp/prod-publish-restore.json; echo "exit $?"; grep -oE '"(named|fetched|fetched_bytes|suppressed)": [0-9]+|"code": "[A-Z_]+"' /tmp/prod-publish-restore.json; fi
```
Before it fetches it prints `Fetching <n> raw source(s), <bytes> bytes, that <m> restored manifest(s)
name; <s> skipped as the suppression list holds them.` Success looks like `exit 0`, then `"named"`,
`"fetched"`, `"fetched_bytes"` and `"suppressed"`, with `fetched` equal to `named` less `suppressed`,
and above zero: a week the cloud imported names sources. A `WEEK` no restored manifest holds stops
instead, with `SNAPSHOTS_NOT_RESTORED`.

A stop says what the directory holds and that it is not a copy to publish from. Delete it with the last
block of this section before anything else, and:

* `RESTORED_SOURCES_INCOMPLETE` with `missing`: a source a manifest names is not in the dev bucket and
  not on the suppression list. Stop and tell the PM; do not publish. With `mismatched`: bytes arrived
  that are not the source named, were deleted, and nothing else was fetched; tell the PM.
* `TOO_LITTLE_ROOM_FOR_SOURCES`: make room, delete the copy, and run the block again.
* `SNAPSHOTS_NOT_RESTORED`: no restored manifest is of `WEEK`; read the runs again.
* `RUN_LOCK_HELD`: a cloud run holds the lock; wait for it to record, then run the block again.

**Publish, one caselist at a time.** For each caselist the run imported in `WEEK`: `hsld26`,
`hspolicy26` and `hspf26` while those are the run's caselists. Each caselist is two blocks, and the
first signs in to prod again, so that a long publish of one caselist never leaves the next without a
session. Set `CASELIST` in the first.

**Operator command** (expected runtime ~1 min)
Where: your Mac, in the window that keeps `WEEK`
```bash
CASELIST=hsld26
COPY="$HOME/.debate-research/prod-publish-${WEEK}"
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif [ ! -d "$COPY" ]; then echo "STOP: no copy at ${COPY}"; else aws sso login --profile debate-prod-evidence && cd "$HOME" && env DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$COPY" debate-research --json caselist publish --caselist "$CASELIST" --snapshot "$WEEK" --dry-run > /tmp/prod-publish-plan-${CASELIST}.json; echo "exit $?"; grep -oE '"(upload|verify|uploaded_earlier|mismatched|missing_locally|suppressed)": [0-9]+|"manifest": "[a-z]+"|"code": "[A-Z_]+"' /tmp/prod-publish-plan-${CASELIST}.json; fi
```
Read the plan before the next block. Success looks like `exit 0`, `"missing_locally": 0`,
`"mismatched": 0` and `"manifest": "upload"`, with `"upload"` above zero in an ordinary week (a week
whose every source prod already holds plans `0` uploads and its manifest alone). **Stop** on
`missing_locally` or `mismatched` above zero, or `"manifest": "blocked"`: the copy does not hold what
the publish needs, or prod holds other bytes under a source's key. `"manifest": "verify"` means prod
has this week's manifest already: nothing is owed for this caselist, so go on to the next. Send the PM
the file for any stop; it holds counts, digests and keys only.

**Operator command** (expected runtime ~2 to 10 min)
Where: your Mac, in the same window, straight after the dry run
```bash
COPY="$HOME/.debate-research/prod-publish-${WEEK}"
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif [ ! -d "$COPY" ]; then echo "STOP: no copy at ${COPY}"; else cd "$HOME" && env DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$COPY" debate-research --json caselist publish --caselist "$CASELIST" --snapshot "$WEEK" --confirm-prod > /tmp/prod-publish-${CASELIST}.json; echo "exit $?"; grep -oE '"(uploaded|skipped|suppressed|failed)": [0-9]+|"manifest": "[a-z]+"|"code": "[A-Z_]+"' /tmp/prod-publish-${CASELIST}.json; fi
```
Success looks like `exit 0`, `"failed": 0`, `"uploaded"` equal to the dry run's `"upload"`, and
`"manifest": "uploaded"`: the publisher confirms each object's digest in prod before it writes the
manifest, and writes the manifest last. `"failed"` above zero or a `"code"`: the week is not complete
in prod, and its manifest was not written. `STORE_CREDENTIALS_EXPIRED` means sign in to prod and run
the caselist's two blocks again, which upload only what is still missing; anything else, send the PM
the file. Then the next caselist, from its dry run.

**Deleting the copy**, once every caselist of `WEEK` is published, or after a stop.

**Operator command** (expected runtime ~1 min)
Where: your Mac, in the window that keeps `WEEK`
```bash
COPY="$HOME/.debate-research/prod-publish-${WEEK}"
case "$COPY" in "$HOME/.debate-research/prod-publish-2"*) rm -rf "$COPY" && echo "removed ${COPY}" ;; *) echo "STOP: ${COPY} is not a prod publish's copy" ;; esac
ls -d "$HOME"/.debate-research/prod-publish-* 2>/dev/null | wc -l
```
Success looks like `removed …` and `0`.

This step publishes the week's raw sources and manifests to prod. It publishes no parsed store and no
search index from the copy; the prod re-parse being split out of `v1-e31-t31` depends on this copy too,
and adds its blocks here.

## At the pilot's promotion: the run's home moves to prod

**Not a step now.** ADR-0020 (7), at the pilot's promotion, from a checkout of `main`, with `prod` for
`dev` in every name, after the same runbooks have been applied in prod (credentials, run, alerts).
What it will take, in order:

1. Prod's profile gains `caselist.sync_caselists` and `caselist.run_state = "bucket"`, in a pull request
   and a stable release, as dev's did in `v1-e40-t06`.
2. Under the dev lock, the run-state bundle and the state files are copied to the prod bucket, and
   prod's lock object is seeded naming `home_environment: prod`: `caselist seed-run-state --execute
   --confirm-prod`, from a copy restored from dev, once every manifest it holds is in the prod bucket.
3. The dev lock object is rewritten, held for good by a holder of kind `moved` naming
   `home_environment: prod`, so that no dev run starts again: `caselist move-run-home --execute`, the
   same day as step 2 and after its dry run, as [the dev lock held for good](#the-dev-lock-held-for-good)
   below says.
4. The dev schedule is deleted and prod's enabled, by plans the PM reads, with a plan check in this
   runbook's style. Then prod's late-run alarm's email, after prod's first recorded run, and dev's off.
5. The comparison of step 7, against a prod run.

### The dev lock held for good

`debate-research caselist move-run-home` (`v1-e40-t11`). It takes dev's lock like any other command,
so it is refused with `RUN_LOCK_HELD` while a run holds it, and then rewrites it with `If-Match`, held
for good by a holder of kind `moved`: `home_environment: prod`, the time it was written, and who wrote
it (the kind of runner, `mac` here, and the build's tag; never a person). It has no lease and never
expires. From then on every command that would take dev's lock (`caselist pull`, `publish`, `parse
--publish`, `remove`, `unsuppress`, `retire --bucket`, `restore-run-state`, `seed-run-state`,
`backfile-import`, `landscape report --publish`, `tub index publish`, `tub index prune`, `store sync
--push`, `files publish`) is refused with `RUN_HOME_MOVED` and the words `the weekly run now runs from
prod`, and writes nothing. It runs in dev only: in prod it is refused (`RUN_HOME_MOVE_REFUSED`) before
it reads anything, since prod's lock names prod from its seed.

**Which builds may be about.** Builds older than this command (`v1.1.0-dev.251`, the image the dev task
runs, among them) read the moved lock and refuse it too, as a dev build: `RUN_LOCK_WRONG_HOME`, "the
bucket's run lock names prod as the run's home environment, and this is dev". They do not name the move,
and they write nothing. **But an older build run as prod against dev's bucket** (`DEBATE_ENV=prod` with
a `DEBATE_STORAGE__S3__BUCKET` override naming dev's bucket) **would take the moved lock over**: its rule
reads a lock with no lease as expired. So no block here or after sets such an override (each checks for
leftover `DEBATE_*` variables first), and the move itself is run from a build that has the command,
which the first block checks.

**The checks and the dry run.** Prod's lock must exist, from step 2, before dev's is moved: the first
line asks prod's seed for its plan, which only reads. Then the move's dry run, which reads dev's lock
and writes nothing.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
aws sso login --profile debate-dev-evidence
aws sso login --profile debate-prod-evidence
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; env | grep -o '^DEBATE_[A-Z_]*'; elif ! debate-research caselist move-run-home --help >/dev/null 2>&1; then echo "STOP: this debate-research has no move-run-home; install a release after v1-e40-t11"; else cd "$HOME" && DEBATE_ENV=prod debate-research --json caselist seed-run-state | grep -oE '"seeded_already": (true|false)'; DEBATE_ENV=dev debate-research --json caselist move-run-home | grep -oE '"applied": (true|false)|"home_environment": "[a-z]+"|"state": "(free|held)"|"kind": "[a-z]+"|"code": "[A-Z_]+"'; fi
```

**What to read, and what stops you.** Go on only with `"seeded_already": true` (prod is seeded), then
`"applied": false`, `"home_environment": "dev"` and `"state": "free"` (dev's lock as it is), then
`"home_environment": "prod"`, `"state": "held"` and `"kind": "moved"` (what the move would write).
`"seeded_already": false` stops you: step 2 is not done. `"code": "RUN_LOCK_HELD"` means a run holds
dev's lock: wait until it has recorded, and run the block again. `"code": "RUN_HOME_MOVED"` means dev's
lock is moved already: there is nothing to do.

**The move.**

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif pgrep -fl 'debate-research( --json)? caselist'; then echo "STOP: a caselist command is running (above)"; else cd "$HOME" && DEBATE_ENV=dev debate-research --json caselist move-run-home --execute | grep -oE '"applied": (true|false)|"home_environment": "[a-z]+"|"state": "(free|held)"|"kind": "[a-z]+"|"code": "[A-Z_]+"'; fi
```
Success looks like `"applied": true`, then `"home_environment": "dev"` and `"state": "free"` (what it
found), then `"home_environment": "prod"`, `"state": "held"` and `"kind": "moved"` (what it wrote).
Anything else: stop and send the PM the output. Then check that a dev command is refused, by asking for
the move's dry run again, which reads only:

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
cd "$HOME" && DEBATE_ENV=dev debate-research --json caselist move-run-home | grep -oE '"code": "[A-Z_]+"|the weekly run now runs from prod'
```
Success looks like `"code": "RUN_HOME_MOVED"` and `the weekly run now runs from prod`. Record the move's
date in `v1-e40-t11`'s follow-ups.

### Undoing the move: the release, only after the coach confirms

A move made by mistake (before prod was seeded, say) is undone by its release, and by nothing else: an
older version of the lock object cannot be copied back, because the bucket refuses an unconditional
write of the lock (`v1-e40-t07`). **The release follows the coach's confirmation, never comes before
it.** It makes dev the run's home again, so prod's schedule must be off first (disabled, or never
enabled): two homes would mean two weekly runs and two ledgers against the same five downloads a day
(ADR-0020 (7)). The release writes dev's lock `free`, naming dev as the home, with `If-Match` on the
version it read, and only when a move holds it.

**The release's dry run.** It reads and writes nothing.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
aws sso login --profile debate-dev-evidence
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; else cd "$HOME" && DEBATE_ENV=dev debate-research --json caselist move-run-home --release | grep -oE '"applied": (true|false)|"home_environment": "[a-z]+"|"state": "(free|held)"|"kind": "[a-z]+"|"code": "[A-Z_]+"'; fi
```

**What to read, and what stops you.** Go on only with `"applied": false`, then `"home_environment":
"prod"`, `"state": "held"` and `"kind": "moved"` (the move it found), then `"home_environment": "dev"`
and `"state": "free"` (what it would write), and only with the coach's confirmation in hand.
`"code": "RUN_HOME_NOT_MOVED"` means no move holds dev's lock: there is nothing to release.

**The release.**

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; else cd "$HOME" && DEBATE_ENV=dev debate-research --json caselist move-run-home --release --execute | grep -oE '"applied": (true|false)|"home_environment": "[a-z]+"|"state": "(free|held)"|"kind": "[a-z]+"|"code": "[A-Z_]+"'; fi
```
Success looks like `"applied": true`, `"home_environment": "prod"`, `"state": "held"`, `"kind":
"moved"`, then `"home_environment": "dev"` and `"state": "free"`. `"code": "LOCK_OBJECT_CHANGED"` means
the lock changed between the read and the write, and nothing was written: run the dry run again.
