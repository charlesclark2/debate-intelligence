#!/usr/bin/env bash
#
# Build the student search pilot's image, push it, and point the environment's function at it.
#
#     scripts/tub_deploy.sh dev
#     scripts/tub_deploy.sh prod
#     scripts/tub_deploy.sh dev --dry-run
#     scripts/tub_deploy.sh --print-base-image
#
# Spec: plan_specs/v1/e39-evidence-search-pilot/t04-pilot-infrastructure.yaml. Decision: ADR-0019
# (f) 3. Operator steps, including the first deploy into an environment: docs/runbooks/evidence-search.md.
#
# **An operator runs this, never CI and never an agent session.** There are no long-lived AWS
# access keys anywhere in this path: it runs as the TubDeployer permission set, through the SSO
# profile debate-<env>-tub-deployer, which may push to this environment's repository and update
# this environment's function's code, and nothing else. TUB_DEPLOY_PROFILE overrides the profile;
# the very first deploy into an environment uses it, because the permission set is created by the
# apply that follows that deploy.
#
# What it does, in order:
#
#   1. checks the tools it needs, Docker above all, and that the Docker daemon answers;
#   2. for prod, refuses unless the checkout is clean, on main, and equal to origin/main (ADR-0013);
#   3. derives the base image's Python from packages/debate_core/pyproject.toml's requires-python,
#      which has to allow exactly one Python minor;
#   4. stages the build context: requirements.txt exported from uv.lock with hashes, and wheels of
#      debate-core and debate-api;
#   5. builds the linux/arm64 image with provenance attestations off (Lambda refuses the manifest
#      list they produce);
#   6. pushes it to debate-<env>-tub and reads back the digest it was pushed as;
#   7. points debate-<env>-tub at repository@sha256:<digest>, never at a tag, and waits for
#      function-updated;
#   8. checks /healthz through CloudFront, at the origin the function's own configuration names.
#
# The repository and the function are named debate-<env>-tub (ADR-0019 (a) 1), so nothing here
# reads Terraform state. If the function does not exist yet, which is the case on an environment's
# first deploy, the script stops after step 6 and says to run the apply.
#
# --dry-run runs steps 1 to 5: it still runs the prod guard and still builds, because a rehearsal
# that skipped the build would not say whether the image builds. It makes no AWS call at all.
#
# --print-base-image runs step 3 alone and prints the base image and its platform, as
# `public.ecr.aws/lambda/python:X.Y linux/arm64`, then stops. It reads one file and calls nothing,
# not even Docker. validate-dev's slow job pulls what it prints, so the SQLite checks that run in
# the function's image find the image this script builds on (v1-e01-t34); it is the one use of
# this script on a runner.
#
# Written for bash 3.2, which is what macOS ships.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKERFILE="${REPO_ROOT}/packages/debate_api/Dockerfile"
PYTHON_DECLARATION="${REPO_ROOT}/packages/debate_core/pyproject.toml"

# ADR-0010: everything is in us-east-1.
readonly AWS_REGION_FOR_PILOT="us-east-1"
readonly IMAGE_PLATFORM="linux/arm64"
readonly BASE_IMAGE_REPOSITORY="public.ecr.aws/lambda/python"

usage() {
  cat <<'USAGE'
Usage: scripts/tub_deploy.sh <dev|prod> [--dry-run]
       scripts/tub_deploy.sh --print-base-image

  dev        deploy the dev pilot (tub.dev.wfbdebate.com)
  prod       deploy the prod pilot (tub.wfbdebate.com); refused unless the checkout is clean,
             on main, and equal to origin/main
  --dry-run  build the image and stop: no push, no update, no AWS call
  --print-base-image
             print the base image and its platform, read from requires-python, and stop

Environment:
  TUB_DEPLOY_PROFILE   AWS profile to push and update with (default: debate-<env>-tub-deployer)
USAGE
}

fail() {
  echo "tub deploy: $*" >&2
  exit 1
}

step() {
  echo
  echo "==> $*"
}

# The image follows requires-python and states no version of its own (ADR-0019 (a) 1,
# tests/architecture/test_single_interpreter_source.py). The declaration has to name exactly one
# minor, as `>=X.Y,<X.Y+1`; anything wider would leave the base image's tag a guess. Sets
# `declared` and `python_version`.
read_python_version() {
  declared="$(sed -n 's/^requires-python[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "${PYTHON_DECLARATION}" | head -n 1)"
  local declared_without_spaces python_bounds
  declared_without_spaces="$(printf '%s' "${declared}" | tr -d ' ')"
  python_bounds='^>=([0-9]+)\.([0-9]+),<([0-9]+)\.([0-9]+)$'
  if [[ ! "${declared_without_spaces}" =~ ${python_bounds} ]]; then
    fail "requires-python is '${declared}', not the '>=X.Y,<X.Z' form this script reads. The base image's tag cannot be derived from it."
  fi
  if [ "${BASH_REMATCH[1]}" != "${BASH_REMATCH[3]}" ] || [ $((BASH_REMATCH[2] + 1)) -ne "${BASH_REMATCH[4]}" ]; then
    fail "requires-python is '${declared}', which allows more than one Python minor. The pilot's base image has to be exactly one; narrow the declaration or change this script and ADR-0019 together."
  fi
  python_version="${BASH_REMATCH[1]}.${BASH_REMATCH[2]}"
}

# --- Arguments --------------------------------------------------------------------------------

environment=""
dry_run=false
print_base_image=false

while [ $# -gt 0 ]; do
  case "$1" in
    dev | prod)
      [ -z "${environment}" ] || fail "give exactly one environment, not '${environment}' and '$1'."
      environment="$1"
      ;;
    --dry-run) dry_run=true ;;
    --print-base-image) print_base_image=true ;;
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

if [ "${print_base_image}" = true ]; then
  read_python_version
  echo "${BASE_IMAGE_REPOSITORY}:${python_version} ${IMAGE_PLATFORM}"
  exit 0
fi

[ -n "${environment}" ] || {
  usage >&2
  fail "say which environment to deploy: dev or prod."
}

deploy_profile="${TUB_DEPLOY_PROFILE:-debate-${environment}-tub-deployer}"
resource_name="debate-${environment}-tub"

# --- The tools this needs ---------------------------------------------------------------------
#
# Docker first, and on its own, because it is the one most likely to be missing or stopped on the
# operator's Mac, and everything after it depends on it.

if ! command -v docker > /dev/null 2>&1; then
  fail "Docker is not installed or not on PATH, and this script builds the pilot's image with it. Install Docker Desktop (or start it, if it is installed), then run this again. Nothing has been built or pushed."
fi

if ! docker info > /dev/null 2>&1; then
  fail "Docker is installed but its daemon is not answering. Start Docker Desktop, wait until it says it is running, then run this again. Nothing has been built or pushed."
fi

if ! docker buildx version > /dev/null 2>&1; then
  fail "docker buildx is not available. It ships with Docker Desktop; update Docker Desktop, then run this again."
fi

for tool in git uv; do
  command -v "${tool}" > /dev/null 2>&1 || fail "${tool} is not on PATH."
done

if [ "${dry_run}" = false ]; then
  for tool in aws curl; do
    command -v "${tool}" > /dev/null 2>&1 || fail "${tool} is not on PATH."
  done
fi

# --- The prod guard (ADR-0013) ----------------------------------------------------------------
#
# Prod is whatever is on main, reached only through a dev-to-main promotion validated in dev. The
# guard runs in --dry-run too: a rehearsal that skipped it would rehearse the wrong thing.

assert_prod_source_is_main() {
  local branch head origin_main

  if [ -n "$(git -C "${REPO_ROOT}" status --porcelain)" ]; then
    fail "prod refused: the checkout has uncommitted changes. Prod is built from a clean main."
  fi

  branch="$(git -C "${REPO_ROOT}" rev-parse --abbrev-ref HEAD)"
  if [ "${branch}" != "main" ]; then
    fail "prod refused: on branch '${branch}', not main. Promote dev to main first (ADR-0013)."
  fi

  git -C "${REPO_ROOT}" fetch --quiet origin main \
    || fail "prod refused: could not fetch origin/main to compare against."

  head="$(git -C "${REPO_ROOT}" rev-parse HEAD)"
  origin_main="$(git -C "${REPO_ROOT}" rev-parse origin/main)"
  if [ "${head}" != "${origin_main}" ]; then
    fail "prod refused: HEAD (${head}) is not origin/main (${origin_main}). Pull or push first."
  fi
}

if [ "${environment}" = "prod" ]; then
  step "Checking this checkout may deploy prod"
  assert_prod_source_is_main
  echo "clean, on main, and equal to origin/main."
fi

commit_sha="$(git -C "${REPO_ROOT}" rev-parse HEAD)"
image_tag="${commit_sha}"
if [ -n "$(git -C "${REPO_ROOT}" status --porcelain)" ]; then
  # dev may be deployed from work in progress; the tag says so, so the repository never shows an
  # image as a commit it is not.
  image_tag="${commit_sha}-uncommitted-$(date -u +%Y%m%dT%H%M%SZ)"
fi

# --- The base image's Python ------------------------------------------------------------------

step "Reading the Python the image is built on from ${PYTHON_DECLARATION#"${REPO_ROOT}/"}"

read_python_version
echo "requires-python ${declared}: ${BASE_IMAGE_REPOSITORY}:${python_version}"

# --- Stage the build context ------------------------------------------------------------------

staging_dir="$(mktemp -d "${TMPDIR:-/tmp}/tub-image.XXXXXX")"
trap 'rm -rf "${staging_dir}"' EXIT

step "Staging the build context in ${staging_dir}"

uv export --directory "${REPO_ROOT}" --package debate-api --frozen --no-dev --no-emit-workspace \
  --format requirements.txt --output-file "${staging_dir}/requirements.txt" > /dev/null \
  || fail "uv export failed: is uv.lock in step with pyproject.toml? (uv lock --check)"

mkdir -p "${staging_dir}/wheels"
for package in debate-core debate-api; do
  uv build --directory "${REPO_ROOT}" --package "${package}" --wheel --out-dir "${staging_dir}/wheels" > /dev/null \
    || fail "uv build --package ${package} failed."
done

# --- Build ------------------------------------------------------------------------------------

local_image="${resource_name}:${image_tag}"

step "Building ${local_image} for ${IMAGE_PLATFORM}"

docker buildx build \
  --platform "${IMAGE_PLATFORM}" \
  --provenance=false \
  --build-arg "PYTHON_VERSION=${python_version}" \
  --file "${DOCKERFILE}" \
  --tag "${local_image}" \
  --load \
  "${staging_dir}" \
  || fail "the image did not build. Nothing has been pushed."

if [ "${dry_run}" = true ]; then
  echo
  echo "Dry run complete. ${local_image} built; nothing was pushed and no AWS call was made."
  exit 0
fi

# --- Push -------------------------------------------------------------------------------------

aws_pilot() {
  AWS_PROFILE="${deploy_profile}" aws --region "${AWS_REGION_FOR_PILOT}" "$@"
}

step "Pushing to ${resource_name} (profile ${deploy_profile})"

account_id="$(aws_pilot sts get-caller-identity --query Account --output text)" \
  || fail "could not identify the account with profile ${deploy_profile}. Are you signed in (aws sso login --sso-session debate)?"
registry="${account_id}.dkr.ecr.${AWS_REGION_FOR_PILOT}.amazonaws.com"
repository="${registry}/${resource_name}"

aws_pilot ecr get-login-password | docker login --username AWS --password-stdin "${registry}" > /dev/null \
  || fail "could not sign Docker in to ${registry} with profile ${deploy_profile}."

docker tag "${local_image}" "${repository}:${image_tag}"
docker push "${repository}:${image_tag}" > /dev/null \
  || fail "the push to ${repository} failed. Does the repository exist (the runbook's first, targeted apply)?"

image_digest="$(
  docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "${repository}:${image_tag}" \
    | sed -n "s|^${repository}@\(sha256:[0-9a-f]\{64\}\)$|\1|p" | head -n 1
)"
[ -n "${image_digest}" ] || fail "pushed, but could not read the digest the registry gave the image."
image_uri="${repository}@${image_digest}"
echo "pushed: ${image_uri}"

# --- Update the function ----------------------------------------------------------------------

step "Pointing ${resource_name} at ${image_digest}"

lookup_error_file="${staging_dir}/get-function-configuration.err"
if ! aws_pilot lambda get-function-configuration --function-name "${resource_name}" \
  --query FunctionName --output text > /dev/null 2> "${lookup_error_file}"; then
  if grep -q "ResourceNotFoundException" "${lookup_error_file}"; then
    echo
    echo "The image is in ${resource_name}'s repository, and the function ${resource_name} does not exist yet."
    echo "This is an environment's first deploy: run the full apply now (docs/runbooks/evidence-search.md),"
    echo "which creates the function from this image, then run this script again."
    exit 0
  fi
  cat "${lookup_error_file}" >&2
  fail "could not read the function ${resource_name} with profile ${deploy_profile}."
fi

aws_pilot lambda update-function-code \
  --function-name "${resource_name}" \
  --image-uri "${image_uri}" \
  --query LastUpdateStatus --output text > /dev/null \
  || fail "update-function-code was refused. The image is pushed; the function still runs the previous one."

aws_pilot lambda wait function-updated --function-name "${resource_name}" \
  || fail "the function did not reach a successful update. Read its LastUpdateStatusReason in the console before deploying again."

# --- Check it through CloudFront --------------------------------------------------------------

pilot_origin="$(
  aws_pilot lambda get-function-configuration --function-name "${resource_name}" \
    --query 'Environment.Variables.TUB_PUBLIC_ORIGIN' --output text
)"
case "${pilot_origin}" in
  https://*) ;;
  *) fail "the function's TUB_PUBLIC_ORIGIN is '${pilot_origin}', not an https origin. Re-apply the environment." ;;
esac

step "Checking ${pilot_origin}/healthz through CloudFront"

health="$(curl --fail --silent --show-error --retry 5 --retry-delay 3 --retry-all-errors --max-time 30 "${pilot_origin}/healthz")" \
  || fail "${pilot_origin}/healthz did not answer. The function runs ${image_digest}; read its log group debate-${environment}-tub-app."
case "${health}" in
  *'"status":"ok"'*) ;;
  *) fail "${pilot_origin}/healthz answered '${health}', not {\"status\":\"ok\"}." ;;
esac

echo "${health}"
echo
echo "Deployed ${commit_sha} to ${environment}: ${pilot_origin}/"
echo "Function ${resource_name} runs ${image_uri}"
