#!/usr/bin/env bash
#
# Build the weekly caselist run's image from a release, push it, and register a run task
# definition that runs it.
#
#     scripts/caselist_run_deploy.sh dev v1.2.0-dev.40
#     scripts/caselist_run_deploy.sh prod v1.2.0
#     scripts/caselist_run_deploy.sh dev v1.2.0-dev.40 --dry-run
#     scripts/caselist_run_deploy.sh --print-base-image
#
# Spec: plan_specs/v1/e40-cloud-caselist-run/t03-run-image-and-schedule.yaml. Decision: ADR-0020
# (1). Operator steps, including an environment's first push: docs/runbooks/caselist-cloud-run.md.
#
# **An operator runs this, and validate-dev's image job runs its --dry-run; never an agent
# session.** There are no long-lived AWS access keys in this path: a push runs as the
# CaselistRunDeployer permission set, through the SSO profile debate-<env>-caselist-run-deployer,
# which may push to this environment's run repository, register a run task definition passing the
# run's two roles (never the login's), and start, watch and stop a run. CASELIST_RUN_DEPLOY_PROFILE
# overrides the profile.
#
# What it does, in order:
#
#   1. checks the tools it needs, Docker above all, and that the Docker daemon answers;
#   2. checks the tag: any release for dev, a stable vX.Y.Z for prod, and for prod a checkout that
#      is clean, on main, and equal to origin/main (ADR-0013);
#   3. derives the base image's Python from packages/debate_core/pyproject.toml's requires-python,
#      which has to allow exactly one Python minor;
#   4. stages the build context: the release's wheels, SHA256SUMS and build-info.json, downloaded
#      with `gh release download`, and scripts/install_channel.sh, which installs them in the image
#      and verifies them there;
#   5. builds the linux/arm64 image from ops/caselist_run/Dockerfile, with provenance attestations
#      off, so the digest pushed is the image's own manifest;
#   6. checks it with ops/caselist_run/check_image.sh, offline: arm64, an unprivileged user, no
#      credential in its environment or files, debate-research and timeout on PATH, this tag, and
#      SQLite with FTS5 at 3.40.0 or later;
#   7. pushes it to debate-<env>-caselist-run as <tag> and reads back its digest. Tags are
#      immutable there: a tag already pushed is not pushed again, and its digest is the one used;
#   8. registers a new revision of the run task definition debate-<env>-caselist-run, the current
#      revision with only its image changed to repository@digest, for a run started by hand. The
#      schedule runs the revision Terraform made, so the script prints the
#      `caselist_image_digest` line for the next apply, which moves the login and the scheduled
#      run to this image.
#
# The repository and the family are named debate-<env>-caselist-run (ADR-0020), so nothing here
# reads Terraform state. If the run task definition does not exist yet, which is the case before
# an environment's first "apply B", the script stops after step 7 and says to run that apply.
#
# --dry-run runs steps 1 to 6: it still runs the prod guard and still builds and checks, because a
# rehearsal that skipped the build would not say whether the image builds. It makes no AWS call.
#
# --print-base-image runs step 3 alone and prints the base image and its platform, as
# `python:X.Y-slim-bookworm linux/arm64`, then stops. It reads one file and calls nothing.
#
# Written for bash 3.2, which is what macOS ships.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKERFILE="${REPO_ROOT}/ops/caselist_run/Dockerfile"
CHECK_IMAGE="${REPO_ROOT}/ops/caselist_run/check_image.sh"
INSTALLER="${REPO_ROOT}/scripts/install_channel.sh"
PYTHON_DECLARATION="${REPO_ROOT}/packages/debate_core/pyproject.toml"
RELEASE_REPOSITORY="${DEBATE_RELEASE_REPO:-charlesclark2/debate-intelligence}"

# ADR-0010: everything is in us-east-1.
readonly AWS_REGION_FOR_RUN="us-east-1"
readonly IMAGE_PLATFORM="linux/arm64"
readonly BASE_IMAGE_REPOSITORY="python"
readonly BASE_IMAGE_VARIANT="slim-bookworm"

usage() {
  cat <<'USAGE'
Usage: scripts/caselist_run_deploy.sh <dev|prod> <release tag> [--dry-run]
       scripts/caselist_run_deploy.sh --print-base-image

  dev        push to debate-dev-caselist-run; any release tag, vX.Y.Z-dev.N or vX.Y.Z
  prod       push to debate-prod-caselist-run; a stable vX.Y.Z only, from a checkout that is
             clean, on main, and equal to origin/main
  --dry-run  build and check the image and stop: no push, no registration, no AWS call
  --print-base-image
             print the base image and its platform, read from requires-python, and stop

Environment:
  CASELIST_RUN_DEPLOY_PROFILE   AWS profile to push and register with
                                (default: debate-<env>-caselist-run-deployer)
  DEBATE_RELEASE_REPO           owner/name to download the release from
USAGE
}

fail() {
  echo "caselist run deploy: $*" >&2
  exit 1
}

step() {
  echo
  echo "==> $*"
}

# The image follows requires-python and states no version of its own. The declaration has to name
# exactly one minor, as `>=X.Y,<X.Y+1`. Sets `declared` and `python_version`.
read_python_version() {
  declared="$(sed -n 's/^requires-python[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "${PYTHON_DECLARATION}" | head -n 1)"
  local declared_without_spaces python_bounds
  declared_without_spaces="$(printf '%s' "${declared}" | tr -d ' ')"
  python_bounds='^>=([0-9]+)\.([0-9]+),<([0-9]+)\.([0-9]+)$'
  if [[ ! "${declared_without_spaces}" =~ ${python_bounds} ]]; then
    fail "requires-python is '${declared}', not the '>=X.Y,<X.Z' form this script reads. The base image's tag cannot be derived from it."
  fi
  if [ "${BASH_REMATCH[1]}" != "${BASH_REMATCH[3]}" ] || [ $((BASH_REMATCH[2] + 1)) -ne "${BASH_REMATCH[4]}" ]; then
    fail "requires-python is '${declared}', which allows more than one Python minor. The run's base image has to be exactly one; narrow the declaration or change this script and ADR-0020 together."
  fi
  python_version="${BASH_REMATCH[1]}.${BASH_REMATCH[2]}"
}

# --- Arguments --------------------------------------------------------------------------------

environment=""
tag=""
dry_run=false
print_base_image=false

while [ $# -gt 0 ]; do
  case "$1" in
    dev | prod)
      [ -z "${environment}" ] || fail "give exactly one environment, not '${environment}' and '$1'."
      environment="$1"
      ;;
    v*)
      [ -z "${tag}" ] || fail "give exactly one release tag, not '${tag}' and '$1'."
      tag="$1"
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
  echo "${BASE_IMAGE_REPOSITORY}:${python_version}-${BASE_IMAGE_VARIANT} ${IMAGE_PLATFORM}"
  exit 0
fi

[ -n "${environment}" ] || {
  usage >&2
  fail "say which environment to deploy: dev or prod."
}
[ -n "${tag}" ] || {
  usage >&2
  fail "say which release to build the image from: a tag such as v1.2.0-dev.40."
}

readonly stable_tag='^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'
readonly dev_tag='^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)-dev\.[1-9][0-9]*$'
if [[ ! "${tag}" =~ ${stable_tag} ]] && [[ ! "${tag}" =~ ${dev_tag} ]]; then
  fail "'${tag}' is not a release tag (vX.Y.Z-dev.N or vX.Y.Z)."
fi
if [ "${environment}" = "prod" ] && [[ ! "${tag}" =~ ${stable_tag} ]]; then
  fail "prod refused: '${tag}' is a dev pre-release. Prod runs a stable release, vX.Y.Z, promoted through main (ADR-0013)."
fi

deploy_profile="${CASELIST_RUN_DEPLOY_PROFILE:-debate-${environment}-caselist-run-deployer}"
resource_name="debate-${environment}-caselist-run"

# --- The tools this needs ---------------------------------------------------------------------
#
# Docker first, and on its own, because it is the one most likely to be missing or stopped on the
# operator's Mac, and everything after it depends on it.

if ! command -v docker > /dev/null 2>&1; then
  fail "Docker is not installed or not on PATH, and this script builds the run's image with it. Install Docker Desktop (or start it, if it is installed), then run this again. Nothing has been built or pushed."
fi

if ! docker info > /dev/null 2>&1; then
  fail "Docker is installed but its daemon is not answering. Start Docker Desktop, wait until it says it is running, then run this again. Nothing has been built or pushed."
fi

if ! docker buildx version > /dev/null 2>&1; then
  fail "docker buildx is not available. It ships with Docker Desktop; update Docker Desktop, then run this again."
fi

for tool in git gh; do
  command -v "${tool}" > /dev/null 2>&1 || fail "${tool} is not on PATH."
done

if [ "${dry_run}" = false ]; then
  for tool in aws python3; do
    command -v "${tool}" > /dev/null 2>&1 || fail "${tool} is not on PATH."
  done
fi

# --- The prod guard (ADR-0013) ----------------------------------------------------------------
#
# The image is the release's wheels, but its Dockerfile, its check and its installer come from this
# checkout, so prod builds from a clean main. The guard runs in --dry-run too.

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

# --- The base image's Python ------------------------------------------------------------------

step "Reading the Python the image is built on from ${PYTHON_DECLARATION#"${REPO_ROOT}/"}"

read_python_version
echo "requires-python ${declared}: ${BASE_IMAGE_REPOSITORY}:${python_version}-${BASE_IMAGE_VARIANT}"

# --- Stage the build context ------------------------------------------------------------------

staging_dir="$(mktemp -d "${TMPDIR:-/tmp}/caselist-run-image.XXXXXX")"
trap 'rm -rf "${staging_dir}"' EXIT

step "Downloading ${tag}'s wheels from ${RELEASE_REPOSITORY} into ${staging_dir}"

mkdir -p "${staging_dir}/assets"
gh release download "${tag}" --repo "${RELEASE_REPOSITORY}" --dir "${staging_dir}/assets" \
  --pattern '*.whl' --pattern SHA256SUMS --pattern build-info.json \
  || fail "could not download the assets of ${tag} from ${RELEASE_REPOSITORY}. Is gh signed in (gh auth status), and is ${tag} published?"
[ -f "${staging_dir}/assets/SHA256SUMS" ] || fail "${tag} has no SHA256SUMS; the image installs only verified wheels."
cp "${INSTALLER}" "${staging_dir}/install_channel.sh"

# --- Build ------------------------------------------------------------------------------------

local_image="${resource_name}:${tag}"

step "Building ${local_image} for ${IMAGE_PLATFORM}"

docker buildx build \
  --platform "${IMAGE_PLATFORM}" \
  --provenance=false \
  --build-arg "PYTHON_VERSION=${python_version}" \
  --build-arg "RELEASE_TAG=${tag}" \
  --file "${DOCKERFILE}" \
  --tag "${local_image}" \
  --load \
  "${staging_dir}" \
  || fail "the image did not build. Nothing has been pushed."

# --- Check ------------------------------------------------------------------------------------

step "Checking ${local_image}, offline"

bash "${CHECK_IMAGE}" "${local_image}" "${tag}" \
  || fail "${local_image} failed a check (above). Nothing has been pushed."

if [ "${dry_run}" = true ]; then
  echo
  echo "Dry run complete. ${local_image} built and checked; nothing was pushed and no AWS call was made."
  exit 0
fi

# --- Push -------------------------------------------------------------------------------------

aws_run() {
  AWS_PROFILE="${deploy_profile}" aws --region "${AWS_REGION_FOR_RUN}" "$@"
}

step "Pushing to ${resource_name} (profile ${deploy_profile})"

account_id="$(aws_run sts get-caller-identity --query Account --output text)" \
  || fail "could not identify the account with profile ${deploy_profile}. Are you signed in (aws sso login --sso-session debate)?"
registry="${account_id}.dkr.ecr.${AWS_REGION_FOR_RUN}.amazonaws.com"
repository="${registry}/${resource_name}"

pushed_before="$(
  aws_run ecr describe-images --repository-name "${resource_name}" --image-ids "imageTag=${tag}" \
    --query 'imageDetails[0].imageDigest' --output text 2> /dev/null || true
)"
if [[ "${pushed_before}" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  # Tags are immutable in this repository: the build pushed first under this tag is the one.
  image_digest="${pushed_before}"
  echo "${tag} is already in ${resource_name} as ${image_digest}; tags are immutable, so it is not pushed again."
else
  aws_run ecr get-login-password | docker login --username AWS --password-stdin "${registry}" > /dev/null \
    || fail "could not sign Docker in to ${registry} with profile ${deploy_profile}."

  docker tag "${local_image}" "${repository}:${tag}"
  docker push "${repository}:${tag}" > /dev/null \
    || fail "the push to ${repository} failed. Does the repository exist (the runbook's apply of the run's network and repository)?"

  image_digest="$(
    docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "${repository}:${tag}" \
      | sed -n "s|^${repository}@\(sha256:[0-9a-f]\{64\}\)$|\1|p" | head -n 1
  )"
  [ -n "${image_digest}" ] || fail "pushed, but could not read the digest the registry gave the image."
fi
image_uri="${repository}@${image_digest}"
echo "pushed: ${image_uri}"

# --- Register a run task definition -----------------------------------------------------------

step "Registering ${resource_name} with ${image_digest}"

current_file="${staging_dir}/current-task-definition.json"
lookup_error_file="${staging_dir}/describe-task-definition.err"
if ! aws_run ecs describe-task-definition --task-definition "${resource_name}" \
  --query taskDefinition --output json > "${current_file}" 2> "${lookup_error_file}"; then
  if grep -q "Unable to describe task definition" "${lookup_error_file}"; then
    echo
    echo "The image is in ${resource_name}'s repository, and the run task definition does not exist yet."
    echo "This is before the environment's apply B: add this line to infrastructure/envs/${environment}/owner.auto.tfvars"
    echo "and run that apply (docs/runbooks/caselist-cloud-run.md), which creates both task definitions:"
    echo
    echo "    caselist_image_digest = \"${image_digest}\""
    exit 0
  fi
  cat "${lookup_error_file}" >&2
  fail "could not read the run task definition ${resource_name} with profile ${deploy_profile}."
fi

# The current revision with its image changed and nothing else; register-task-definition refuses
# the fields ECS adds itself. A definition that does not run as the run role is refused here as
# well as by IAM.
next_file="${staging_dir}/next-task-definition.json"
python3 - "${current_file}" "${next_file}" "${image_uri}" "${resource_name}" <<'PYTHON' \
  || fail "the current run task definition is not one this script will copy; nothing was registered."
import json
import sys

current_path, next_path, image, family = sys.argv[1:5]
with open(current_path, encoding="utf-8") as current:
    definition = json.load(current)
if definition.get("family") != family:
    raise SystemExit(f"its family is {definition.get('family')!r}, not {family!r}")
if not str(definition.get("taskRoleArn", "")).endswith(f":role/{family}"):
    raise SystemExit("its task role is not the run role")
if not str(definition.get("executionRoleArn", "")).endswith(f":role/{family}-execution"):
    raise SystemExit("its execution role is not the run's execution role")
containers = definition["containerDefinitions"]
if len(containers) != 1:
    raise SystemExit(f"it has {len(containers)} containers, not one")
containers[0]["image"] = image
kept = (
    "family", "taskRoleArn", "executionRoleArn", "networkMode", "containerDefinitions",
    "requiresCompatibilities", "cpu", "memory", "runtimePlatform", "ephemeralStorage",
)
with open(next_path, "w", encoding="utf-8") as following:
    json.dump({key: definition[key] for key in kept if key in definition}, following)
PYTHON

registered="$(
  aws_run ecs register-task-definition --cli-input-json "file://${next_file}" \
    --query taskDefinition.taskDefinitionArn --output text
)" || fail "register-task-definition was refused. The image is pushed; no revision was registered."

echo "registered: ${registered}"
echo
echo "A run started by hand now runs ${tag} (docs/runbooks/caselist-cloud-run.md, \"Start one run by hand\")."
echo "The schedule and the login still run the image Terraform names. To move them to this one, put"
echo "this line in infrastructure/envs/${environment}/owner.auto.tfvars and apply:"
echo
echo "    caselist_image_digest = \"${image_digest}\""
