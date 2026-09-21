#!/usr/bin/env bash
#
# Publish the public team website to one environment's S3 bucket and invalidate its CloudFront
# distribution.
#
#     scripts/site_deploy.sh dev
#     scripts/site_deploy.sh prod
#     scripts/site_deploy.sh prod --dry-run
#
# Spec: plan_specs/v1/e36-team-website/t05-site-deploy.yaml. Infrastructure: v1-e36-t02, described
# in docs/runbooks/team-website.md. Two environments and the dev-to-main promotion: ADR-0013.
#
# **An operator runs this, never CI and never an agent session.** There are no long-lived AWS
# access keys anywhere in this path: it uses the SSO profiles the operator signs in with. Keyless
# deploys from CI arrive in v2-e10-t03, and until they do, the fact that a human runs this is what
# keeps an unreviewed page about a student from reaching the public through a merge.
#
# Two profiles per environment, because the split is real:
#
#   debate-<env>        the maintainer profile, used only for `terraform output`. Reading the
#                       bucket name and distribution id means reading Terraform state.
#   debate-<env>-site   the publisher permission set from v1-e36-t02: list/read/write/delete in
#                       this environment's own site bucket, and invalidate its own distribution.
#                       It cannot read state, which is why the first profile exists.
#
# Both are overridable (SITE_TERRAFORM_PROFILE, SITE_PUBLISHER_PROFILE) so that an environment
# whose state a maintainer cannot read can fall back to debate-admin without editing this file.
#
# What it does, in order:
#
#   1. checks the tools it needs are on PATH;
#   2. for prod, refuses unless the checkout is clean, on main, and equal to origin/main (ADR-0013:
#      nothing reaches prod that has not been validated in dev);
#   3. reads site_bucket_name, site_distribution_id and site_url from the environment's Terraform
#      outputs;
#   4. builds site/ with that environment's SITE_ENV and SITE_URL;
#   5. writes site/out/version.json with the commit sha, so a deployed site can be identified;
#   6. syncs site/out/ into the bucket, long cache for the hashed assets and no-cache for
#      everything else;
#   7. creates a CloudFront invalidation and waits for it to complete.
#
# Step 7 waits on purpose. The publishing policy gives a 24-hour clock for removing something
# about a student on request, and "removed" means removed from the edge, not from the bucket: the
# only honest way to report that is to watch the invalidation finish.
#
# --dry-run does everything except the writes: it still runs the prod guard, still reads the
# Terraform outputs and still builds, because a rehearsal that skipped the build would not tell
# you whether the build is clean. It makes no `aws s3` and no `aws cloudfront` call at all.
#
# Written for bash 3.2, which is what macOS ships.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SITE_DIR="${REPO_ROOT}/site"
EXPORT_DIR="${SITE_DIR}/out"

# Hashed assets under this prefix are content-addressed: a change to a file changes its name, so
# the old name can be cached for as long as a browser is willing to.
readonly IMMUTABLE_PREFIX="_next/static"
readonly IMMUTABLE_CACHE_CONTROL="public, max-age=31536000, immutable"
# Everything else, HTML above all, has a stable name and new contents on every deploy, so it must
# be revalidated. CloudFront honours this (the cache behaviour is Managed-CachingOptimized), which
# is why the invalidation only has to deal with what is already in an edge cache.
readonly MUTABLE_CACHE_CONTROL="no-cache, must-revalidate"

usage() {
  cat <<'USAGE'
Usage: scripts/site_deploy.sh <dev|prod> [--dry-run]

  dev        publish to the preview site (noindex, for review)
  prod       publish to the public site; refused unless the checkout is clean, on main,
             and equal to origin/main
  --dry-run  build and report, make no aws s3 or cloudfront call

Environment:
  SITE_TERRAFORM_PROFILE   AWS profile for `terraform output`   (default: debate-<env>)
  SITE_PUBLISHER_PROFILE   AWS profile for the sync and the invalidation
                           (default: debate-<env>-site)
USAGE
}

fail() {
  echo "site deploy: $*" >&2
  exit 1
}

step() {
  echo
  echo "==> $*"
}

# --- Arguments --------------------------------------------------------------------------------

environment=""
dry_run=false

while [ $# -gt 0 ]; do
  case "$1" in
    dev | prod)
      [ -z "${environment}" ] || fail "give exactly one environment, not '${environment}' and '$1'."
      environment="$1"
      ;;
    --dry-run) dry_run=true ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      fail "unrecognised argument '$1'."
      ;;
  esac
  shift
done

[ -n "${environment}" ] || {
  usage >&2
  fail "say which environment to deploy: dev or prod."
}

terraform_profile="${SITE_TERRAFORM_PROFILE:-debate-${environment}}"
publisher_profile="${SITE_PUBLISHER_PROFILE:-debate-${environment}-site}"
terraform_dir="${REPO_ROOT}/infrastructure/envs/${environment}"

# --- The tools this needs ---------------------------------------------------------------------
#
# None of these is a uv dependency: terraform, the AWS CLI, node and pnpm come from the operator's
# machine, so say what is missing rather than failing obscurely three steps later.

for tool in git terraform aws pnpm python3; do
  command -v "${tool}" > /dev/null 2>&1 || fail "${tool} is not on PATH."
done

[ -d "${SITE_DIR}/node_modules" ] || fail "site/node_modules is missing. Run: pnpm --dir site install"

# --- The prod guard (ADR-0013) ----------------------------------------------------------------
#
# Prod is whatever is on main, and main is only ever reached through a dev-to-main promotion that
# was validated in dev. Deploying anything else to prod would make the public site a thing no
# branch describes. The guard runs in --dry-run too: a rehearsal that skipped it would rehearse
# the wrong thing.

assert_prod_source_is_main() {
  local branch head origin_main

  if [ -n "$(git -C "${REPO_ROOT}" status --porcelain)" ]; then
    fail "prod refused: the checkout has uncommitted changes. Prod is built from a clean main."
  fi

  branch="$(git -C "${REPO_ROOT}" rev-parse --abbrev-ref HEAD)"
  if [ "${branch}" != "main" ]; then
    fail "prod refused: on branch '${branch}', not main. Promote dev to main first (ADR-0013)."
  fi

  # Fetch before comparing: an out-of-date local main would otherwise pass a comparison against a
  # stale remote ref and publish a commit the promotion PR never included.
  git -C "${REPO_ROOT}" fetch --quiet origin main \
    || fail "prod refused: could not fetch origin/main to compare against."

  head="$(git -C "${REPO_ROOT}" rev-parse HEAD)"
  origin_main="$(git -C "${REPO_ROOT}" rev-parse origin/main)"
  if [ "${head}" != "${origin_main}" ]; then
    fail "prod refused: HEAD (${head}) is not origin/main (${origin_main}). Pull or push first."
  fi
}

if [ "${environment}" = "prod" ]; then
  step "Checking this checkout may publish prod"
  assert_prod_source_is_main
  echo "clean, on main, and equal to origin/main."
fi

commit_sha="$(git -C "${REPO_ROOT}" rev-parse HEAD)"

# --- Where to publish -------------------------------------------------------------------------
#
# The bucket and the distribution are read from Terraform rather than written down here, so that
# renaming one is a change in one place. infrastructure/envs/<env>/outputs.tf says as much.

step "Reading the ${environment} site outputs from Terraform (profile ${terraform_profile})"

terraform_outputs="$(
  AWS_PROFILE="${terraform_profile}" terraform -chdir="${terraform_dir}" output -json
)" || fail "could not read Terraform outputs. Has \`terraform -chdir=${terraform_dir} init\` run, and are you signed in (aws sso login --sso-session debate)?"

read_output() {
  printf '%s' "${terraform_outputs}" | python3 -c '
import json, sys
name = sys.argv[1]
outputs = json.load(sys.stdin)
if name not in outputs:
    sys.exit(f"site deploy: Terraform output {name} is missing.")
value = outputs[name].get("value")
if value in (None, ""):
    sys.exit(f"site deploy: Terraform output {name} is empty.")
print(value)
' "$1"
}

bucket_name="$(read_output site_bucket_name)"
distribution_id="$(read_output site_distribution_id)"
site_url="$(read_output site_url)"
# The outputs carry a trailing slash on the URL; SITE_URL is a bare origin.
site_url="${site_url%/}"

echo "bucket:       ${bucket_name}"
echo "distribution: ${distribution_id}"
echo "site url:     ${site_url}"

# --- Build ------------------------------------------------------------------------------------
#
# SITE_ENV decides robots.txt, the noindex meta tag and whether the content guard treats a policy
# problem as an error or a warning, so a prod build fails on a [[TBD]] marker or an unreviewed
# name. That failure is the point: it is the last gate before the public site.

step "Building site/ for ${environment} (SITE_ENV=${environment}, SITE_URL=${site_url})"

SITE_ENV="${environment}" SITE_URL="${site_url}" pnpm --dir "${SITE_DIR}" build \
  || fail "the ${environment} build failed. Nothing has been uploaded."

[ -f "${EXPORT_DIR}/index.html" ] || fail "${EXPORT_DIR}/index.html is missing after the build."

# --- version.json -----------------------------------------------------------------------------
#
# What is actually deployed, in a file the smoke check can read. Commit sha only: no account id,
# no profile name, nothing about who ran it.

step "Writing version.json"

python3 - "${EXPORT_DIR}/version.json" "${commit_sha}" "${environment}" "${site_url}" <<'PYTHON'
import datetime
import json
import pathlib
import sys

path, commit, environment, site_url = sys.argv[1:5]
pathlib.Path(path).write_text(
    json.dumps(
        {
            "commit": commit,
            "environment": environment,
            "siteUrl": site_url,
            "builtAt": datetime.datetime.now(datetime.timezone.utc)
            .replace(microsecond=0)
            .isoformat(),
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
PYTHON

cat "${EXPORT_DIR}/version.json"

# --- Upload -----------------------------------------------------------------------------------
#
# Three passes, in this order and for this reason:
#
#   1. the hashed assets go up first, with no --delete, so that a page can never be served before
#      the chunks it references exist;
#   2. then everything else, with --delete, so a page removed from the site leaves the bucket in
#      the same deploy. The hashed prefix is excluded, which also excludes it from the deletion
#      pass — that is what makes pass 1's ordering hold;
#   3. then the hashed prefix again, with --delete, to remove the chunks no page references any
#      more. It uploads nothing: pass 1 already did.
#
# --delete only ever names this environment's own bucket, and the publisher profile can reach no
# other (task spec: forbidden).

run_aws() {
  if [ "${dry_run}" = true ]; then
    echo "dry run, not running: aws $*"
    return 0
  fi
  AWS_PROFILE="${publisher_profile}" aws "$@"
}

step "Syncing ${EXPORT_DIR} into s3://${bucket_name} (profile ${publisher_profile})"

run_aws s3 sync "${EXPORT_DIR}/${IMMUTABLE_PREFIX}" "s3://${bucket_name}/${IMMUTABLE_PREFIX}" \
  --no-progress \
  --cache-control "${IMMUTABLE_CACHE_CONTROL}"

run_aws s3 sync "${EXPORT_DIR}" "s3://${bucket_name}" \
  --no-progress \
  --delete \
  --exclude "${IMMUTABLE_PREFIX}/*" \
  --cache-control "${MUTABLE_CACHE_CONTROL}"

run_aws s3 sync "${EXPORT_DIR}/${IMMUTABLE_PREFIX}" "s3://${bucket_name}/${IMMUTABLE_PREFIX}" \
  --no-progress \
  --delete \
  --cache-control "${IMMUTABLE_CACHE_CONTROL}"

# --- Invalidate -----------------------------------------------------------------------------

step "Invalidating ${distribution_id}"

if [ "${dry_run}" = true ]; then
  echo "dry run, not running: aws cloudfront create-invalidation --distribution-id ${distribution_id} --paths /*"
  echo
  echo "Dry run complete. The ${environment} build is clean and nothing was uploaded."
  exit 0
fi

invalidation_id="$(
  AWS_PROFILE="${publisher_profile}" aws cloudfront create-invalidation \
    --distribution-id "${distribution_id}" \
    --paths '/*' \
    --query 'Invalidation.Id' \
    --output text
)" || fail "could not create the invalidation. The bucket now holds the new files but the edge does not serve them yet."

echo "invalidation: ${invalidation_id}"

# Waiting needs cloudfront:GetInvalidation on the publisher permission set. If this is the call
# that is denied, the upload succeeded and only the confirmation is missing: re-apply the site
# module (docs/runbooks/team-website.md) rather than deploying again.
AWS_PROFILE="${publisher_profile}" aws cloudfront wait invalidation-completed \
  --distribution-id "${distribution_id}" \
  --id "${invalidation_id}" \
  || fail "the invalidation was created (${invalidation_id}) but waiting for it failed. If this is an AccessDenied on cloudfront:GetInvalidation, the publisher permission set needs re-applying; check the invalidation in the console before telling anyone the change is live."

echo
echo "Deployed ${commit_sha} to ${environment}: ${site_url}"
echo "Now smoke-check it:"
echo "  uv run scripts/site_smoke.py --env ${environment} --url ${site_url} --expect-sha ${commit_sha}"
