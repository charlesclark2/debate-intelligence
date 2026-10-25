#!/usr/bin/env bash
#
# Check a built run image before anything runs it (task v1-e40-t03, ADR-0020 (1)).
#
#     ops/caselist_run/check_image.sh <image> <release tag>
#
# scripts/caselist_run_deploy.sh runs this after every build, before a push, and validate-dev's
# image job runs it through that script. Every check starts a container with no network at all
# (`--network none`), so nothing here can reach a registry, AWS or the internet, and none of it
# needs a credential:
#
#   1. the image is linux/arm64, runs as the unprivileged user 10001, and its entrypoint is
#      debate-research;
#   2. its environment names no credential: no AWS key, session or token, nothing called a token,
#      a password or a secret (the image's environment is its own; the task definition adds names
#      and switches at run time, and no secret either);
#   3. no credential file is in it: no ~/.aws, no secrets/ directory, no .env;
#   4. debate-research and timeout are on PATH, as the two task definitions' entry points need;
#   5. the installed debate-research reports this tag;
#   6. the base image's own Python is the minor the Python debate-research runs on is, which
#      install_channel.sh took from the release's Requires-Python. The base image is pinned by
#      digest (v1-e40-t06), and a digest is one Python's image whatever the tag beside it says, so a
#      digest left behind when requires-python moves is caught here rather than shipped;
#   7. the Python debate-research runs on has SQLite with FTS5 at 3.40.0 or later, the version the
#      student search pilot's index is pinned to (ADR-0019 (c) 1, ADR-0020 (1)).
#
# Prints one `ok:` line a check and exits 0, or names the first check that failed and exits 1.
# Written for bash 3.2, which is what macOS ships.

set -euo pipefail

readonly EXPECTED_USER="10001:10001"
readonly EXPECTED_PLATFORM="linux/arm64"
readonly TOOL_PYTHON="/opt/debate-research/tools/debate-cli/bin/python"
readonly BASE_PYTHON="/usr/local/bin/python3"
readonly MINOR_PROBE='import sys; print("%d.%d" % sys.version_info[:2])'
readonly SQLITE_FLOOR="3.40.0"

fail() {
  echo "check image: $*" >&2
  exit 1
}

[ $# -eq 2 ] || fail "usage: ops/caselist_run/check_image.sh <image> <release tag>"
image="$1"
tag="$2"

offline() {
  docker run --rm --network none "$@"
}

platform="$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "${image}")" \
  || fail "${image} is not an image Docker has."
[ "${platform}" = "${EXPECTED_PLATFORM}" ] || fail "${image} is ${platform}, not ${EXPECTED_PLATFORM}: Fargate runs the tasks on arm64."
user="$(docker image inspect --format '{{.Config.User}}' "${image}")"
[ "${user}" = "${EXPECTED_USER}" ] || fail "${image} runs as '${user}', not ${EXPECTED_USER}."
entrypoint="$(docker image inspect --format '{{json .Config.Entrypoint}}' "${image}")"
[ "${entrypoint}" = '["debate-research"]' ] || fail "${image}'s entrypoint is ${entrypoint}, not [\"debate-research\"]."
echo "ok: ${EXPECTED_PLATFORM}, user ${EXPECTED_USER}, entrypoint debate-research"

names="$(docker image inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "${image}" | sed -n 's/=.*//p')"
credential_names="$(printf '%s\n' "${names}" | grep -E -i '^AWS_(ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN|PROFILE)$|TOKEN|PASSWORD|SECRET|CREDENTIAL' || true)"
[ -z "${credential_names}" ] || fail "${image}'s environment names a credential: $(printf '%s' "${credential_names}" | tr '\n' ' ')"
echo "ok: the environment names no credential ($(printf '%s\n' "${names}" | tr '\n' ' '))"

# shellcheck disable=SC2016 # $HOME and $path are the container's, expanded by its own sh.
offline --entrypoint sh "${image}" -c '
  for path in "$HOME/.aws" /root/.aws "$HOME/secrets" /var/lib/debate-research/.env /.env "$HOME/.config/debate-research"; do
    if [ -e "$path" ]; then echo "$path"; exit 1; fi
  done
' > /dev/null || fail "${image} holds a credential file or directory."
echo "ok: no credential file"

offline --entrypoint sh "${image}" -c 'command -v debate-research && command -v timeout' > /dev/null \
  || fail "${image} lacks debate-research or timeout on PATH."
echo "ok: debate-research and timeout on PATH"

report="$(offline "${image}" --version --json)" || fail "debate-research --version --json failed in ${image}."
printf '%s\n' "${report}" | grep -Eq "\"tag\": ?\"${tag}\"" \
  || fail "the image's debate-research does not report tag ${tag}: ${report}"
echo "ok: debate-research reports ${tag}"

base_minor="$(offline --entrypoint "${BASE_PYTHON}" "${image}" -c "${MINOR_PROBE}")" \
  || fail "the base image's own Python in ${image} did not run."
tool_minor="$(offline --entrypoint "${TOOL_PYTHON}" "${image}" -c "${MINOR_PROBE}")" \
  || fail "the Python debate-research runs on in ${image} did not run."
[ "${base_minor}" = "${tool_minor}" ] \
  || fail "${image}'s base image has Python ${base_minor}, and debate-research runs on ${tool_minor}: the digest in ops/caselist_run/Dockerfile is another Python's image. Pin the digest of the tag scripts/caselist_run_deploy.sh --print-base-image names."
echo "ok: the base image's Python is ${tool_minor}, the one debate-research runs on"

sqlite="$(
  offline --entrypoint "${TOOL_PYTHON}" "${image}" -c '
import sqlite3
connection = sqlite3.connect(":memory:")
connection.execute("CREATE VIRTUAL TABLE probe USING fts5(body)")
print(sqlite3.sqlite_version)
'
)" || fail "the Python debate-research runs on in ${image} has no SQLite FTS5."
lowest="$(printf '%s\n%s\n' "${SQLITE_FLOOR}" "${sqlite}" | sort -t . -k 1,1n -k 2,2n -k 3,3n | head -n 1)"
[ "${lowest}" = "${SQLITE_FLOOR}" ] || fail "${image}'s SQLite is ${sqlite}, older than ${SQLITE_FLOOR}."
echo "ok: SQLite ${sqlite} with FTS5"
