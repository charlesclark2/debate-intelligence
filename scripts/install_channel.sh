#!/bin/sh
# Install one published build of debate-research as a uv tool (v1-e01-t09-dev-prerelease-channel).
#
#     scripts/install_channel.sh v0.1.0-dev.3          # a dev pre-release
#     scripts/install_channel.sh v0.1.0                # a stable release (v1-e09-t06)
#     scripts/install_channel.sh --dir ./assets v0.1.0-dev.3   # assets already downloaded
#
# What it does:
#   1. downloads the release's wheels, SHA256SUMS and build-info.json with `gh release download`
#      (skipped with --dir, e.g. when validate-dev has downloaded them already);
#   2. refuses to go on unless every wheel is listed in SHA256SUMS and every listed file matches;
#   3. installs debate-cli and debate-core **by the file URLs of those two verified wheels**, which
#      puts `debate-research` in uv's tool bin directory (`uv tool dir --bin`, normally
#      ~/.local/bin), in its own environment, outside every checkout and every project .venv.
#      Third-party dependencies (typer, pydantic, httpx…) still come from the default index;
#   4. checks that both installed distributions record those wheel files as their source, and that
#      the installed `debate-research --version --json` reports this version and channel.
#
# Why direct URLs, not `--find-links <dir> debate-cli==<version>` (ac2b of the task spec): neither
# `debate-core` nor `debate-cli` is registered on PyPI, and a find-links install keeps PyPI in the
# resolution set for them. Pinning does not help. Dev versions are predictable from the public
# tags, and a squatter who publishes `debate-core==0.1.0.devN` with a more specific wheel tag
# (`cp312-none-any`) is preferred over our `py3-none-any` wheel at the very same version.
# tests/scripts/test_install_channel.py shows the old command taking such a decoy and this script
# refusing it. A requirement given as a URL is never looked up on any index, and uv uses it for every
# reference to that name, including debate-cli's own `debate-core==<version>` dependency.
#
# The scheduled caselist pull (v1-e34-t05) runs whatever this script installed, so this is also
# where the `[caselist] api_enabled` gate comes from: it is read from config/profiles/<env>.toml
# *as bundled in the wheel at build time*. Editing config/ in a checkout does not change an
# installed build. To turn the OpenCaselist API off for an installed build, install a build whose
# profile says so, or set DEBATE_CASELIST__API_ENABLED=false in the agent's environment (the
# plist), which beats the bundled profile.
#
# Why this rather than `uv run debate-research`: a checkout's .venv is rebuilt by every `uv sync`
# and tracks whatever was merged last, so a schedule pointed at it runs a different build each
# week. A tool installed from a tag stays that build until this script installs another.
#
# The environment the build runs as: a dev pre-release defaults to DEBATE_ENV=dev and a stable build
# to prod; an explicit DEBATE_ENV always wins (packages/debate_cli/README.md).
#
# Environment:
#   DEBATE_RELEASE_REPO   owner/name to download from (default charlesclark2/debate-intelligence).
#   UV_TOOL_DIR, UV_TOOL_BIN_DIR   honoured by uv as usual, e.g. to install somewhere disposable.
#
# Needs: uv, and gh (authenticated) unless --dir is given. No Python is needed beforehand; uv
# provides 3.12 for the tool.
set -eu

REPOSITORY=${DEBATE_RELEASE_REPO:-charlesclark2/debate-intelligence}
PYTHON_VERSION=3.12

fail() {
    echo "install_channel: $*" >&2
    exit 1
}

usage() {
    echo "usage: scripts/install_channel.sh [--dir DIRECTORY] TAG" >&2
    echo "  TAG is vX.Y.Z-dev.N (dev pre-release) or vX.Y.Z (stable release)" >&2
    exit 2
}

ASSETS=""
TAG=""
while [ $# -gt 0 ]; do
    case "$1" in
        --dir) [ $# -ge 2 ] || usage; ASSETS="$2"; shift 2 ;;
        -h|--help) usage ;;
        -*) echo "install_channel: unknown option $1" >&2; usage ;;
        *) [ -z "${TAG}" ] || usage; TAG="$1"; shift ;;
    esac
done
[ -n "${TAG}" ] || usage

# vX.Y.Z-dev.N -> X.Y.Z.devN (the wheel's PEP 440 version); vX.Y.Z -> X.Y.Z.
if printf '%s\n' "${TAG}" | grep -Eq '^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)-dev\.[1-9][0-9]*$'; then
    VERSION=$(printf '%s\n' "${TAG}" | sed -E 's/^v(.*)-dev\.([0-9]+)$/\1.dev\2/')
    CHANNEL=dev
elif printf '%s\n' "${TAG}" | grep -Eq '^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'; then
    VERSION=${TAG#v}
    CHANNEL=stable
else
    fail "'${TAG}' is not a release tag (vX.Y.Z-dev.N or vX.Y.Z)"
fi

command -v uv >/dev/null 2>&1 || fail "uv is not installed: https://docs.astral.sh/uv/getting-started/installation/"

CLEANUP=""
cleanup() {
    if [ -n "${CLEANUP}" ]; then
        rm -rf -- "${CLEANUP}"
    fi
}
trap cleanup EXIT INT TERM

if [ -z "${ASSETS}" ]; then
    command -v gh >/dev/null 2>&1 || fail "gh is not installed (or pass --dir with the assets already downloaded)"
    ASSETS=$(mktemp -d "${TMPDIR:-/tmp}/debate-research-${TAG}.XXXXXX")
    CLEANUP=${ASSETS}
    echo "Downloading ${TAG} from ${REPOSITORY}..."
    gh release download "${TAG}" --repo "${REPOSITORY}" --dir "${ASSETS}" \
        --pattern '*.whl' --pattern SHA256SUMS --pattern build-info.json \
        || fail "could not download the assets of ${TAG} from ${REPOSITORY}"
fi
[ -d "${ASSETS}" ] || fail "${ASSETS} is not a directory"
[ -f "${ASSETS}/SHA256SUMS" ] || fail "${ASSETS} has no SHA256SUMS; refusing to install unverified wheels"

if command -v sha256sum >/dev/null 2>&1; then
    CHECKSUM="sha256sum"
elif command -v shasum >/dev/null 2>&1; then
    CHECKSUM="shasum -a 256"
else
    fail "neither sha256sum nor shasum is available to verify SHA256SUMS"
fi

# Every wheel present must be listed: `--find-links` installs whatever matching wheel is in the
# directory, listed or not.
for wheel in "${ASSETS}"/*.whl; do
    [ -e "${wheel}" ] || fail "${ASSETS} contains no wheels"
    name=$(basename "${wheel}")
    awk -v name="${name}" '{ sub(/^\*/, "", $2); if ($2 == name) found = 1 } END { exit !found }' \
        "${ASSETS}/SHA256SUMS" || fail "${name} is not listed in SHA256SUMS; refusing to install it"
done
(cd "${ASSETS}" && ${CHECKSUM} -c SHA256SUMS) || fail "SHA256SUMS verification failed; the assets are not what was published"

for distribution in debate_cli debate_core; do
    [ -f "${ASSETS}/${distribution}-${VERSION}-py3-none-any.whl" ] \
        || fail "${ASSETS} has no ${distribution} wheel for version ${VERSION}"
done

# file:// URLs of the two verified wheels. A path needs its spaces and percent signs escaped to be
# a URL; anything else a directory name may contain is legal in a file URL as it stands.
ASSETS_ABSOLUTE=$(CDPATH='' cd -- "${ASSETS}" && pwd)
ASSETS_URL="file://$(printf '%s' "${ASSETS_ABSOLUTE}" | sed -e 's/%/%25/g' -e 's/ /%20/g')"
CLI_WHEEL="debate_cli-${VERSION}-py3-none-any.whl"
CORE_WHEEL="debate_core-${VERSION}-py3-none-any.whl"

echo "Installing debate-cli ${VERSION} (${CHANNEL} channel) as a uv tool, from ${ASSETS_ABSOLUTE}..."
uv tool install --force --python "${PYTHON_VERSION}" \
    "debate-cli @ ${ASSETS_URL}/${CLI_WHEEL}" \
    --with "debate-core @ ${ASSETS_URL}/${CORE_WHEEL}"

# Belt and braces: each first-party distribution must say it came from the wheel verified above.
# PEP 610's direct_url.json is written only for a URL install; one resolved from an index has none.
TOOL_ENVIRONMENT="$(uv tool dir)/debate-cli"
for wheel in "${CLI_WHEEL}" "${CORE_WHEEL}"; do
    distribution=${wheel%%-*}
    found=""
    for record in "${TOOL_ENVIRONMENT}"/lib/python*/site-packages/"${distribution}-${VERSION}".dist-info/direct_url.json; do
        if [ -f "${record}" ] && grep -Fq "${ASSETS_URL}/${wheel}" "${record}"; then
            found=yes
        fi
    done
    [ -n "${found}" ] || fail "the installed ${distribution} did not come from ${ASSETS_ABSOLUTE}/${wheel}; refusing to trust this install"
done

BIN_DIRECTORY=$(uv tool dir --bin)
INSTALLED="${BIN_DIRECTORY}/debate-research"
[ -x "${INSTALLED}" ] || fail "uv reported success but ${INSTALLED} does not exist"

REPORT=$("${INSTALLED}" --version --json) || fail "${INSTALLED} --version --json failed"
printf '%s\n' "${REPORT}"
printf '%s\n' "${REPORT}" | grep -Eq "\"version\": ?\"${VERSION}\"" \
    || fail "the installed debate-research does not report version ${VERSION}"
printf '%s\n' "${REPORT}" | grep -Eq "\"channel\": ?\"${CHANNEL}\"" \
    || fail "the installed debate-research does not report channel ${CHANNEL}"

ON_PATH=$(command -v debate-research || true)
if [ "${ON_PATH}" != "${INSTALLED}" ]; then
    echo "" >&2
    echo "install_channel: warning — \`debate-research\` on this PATH is ${ON_PATH:-nothing}," >&2
    echo "install_channel: not the build just installed at ${INSTALLED}." >&2
    echo "install_channel: put ${BIN_DIRECTORY} before any project .venv/bin on PATH" >&2
    echo "install_channel: (\`uv tool update-shell\` adds it), or call ${INSTALLED} by its full path." >&2
fi

echo "Installed debate-research ${VERSION} from ${TAG} at ${INSTALLED}."
