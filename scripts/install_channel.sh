#!/bin/sh
# Install one published build of debate-research as a uv tool (v1-e01-t09-dev-prerelease-channel).
#
#     scripts/install_channel.sh v0.1.0-dev.3          # a dev pre-release
#     scripts/install_channel.sh v0.1.0                # a stable release (v1-e09-t06)
#     scripts/install_channel.sh --dir ./assets v0.1.0-dev.3   # assets already downloaded
#     scripts/install_channel.sh --no-path-warning --dir ./assets v0.1.0-dev.3   # automated installs
#
# What it does:
#   1. downloads the release's wheels, SHA256SUMS and build-info.json with `gh release download`
#      (skipped with --dir, e.g. when validate-dev has downloaded them already);
#   2. refuses to go on unless every wheel is listed in SHA256SUMS and every listed file matches;
#   3. reads the `Requires-Python` of the verified debate_core wheel and passes that specifier to
#      uv as `--python` (v1-e01-t14). The wheel's metadata is the one statement of which Python
#      this tool supports, and it is not optional: uv deliberately ignores the upper bound of a
#      dependency's Requires-Python, so without `--python` a uv install can land on a Python whose
#      Unicode database the evidence normalizer is not pinned to. Unreadable or missing metadata
#      makes the script refuse; it never falls back to a guess;
#   4. rehearses the install in a temporary uv tool directory and runs every check there:
#      both installed distributions record those wheel files as their source, the installed
#      `debate-research --version --json` reports this version and channel, the build can import
#      every integration the CLI's composition root wires (`python -m debate_cli.installation`,
#      v1-e01-t17; it also refuses a build missing a distribution of a declared extra), and
#      `debate-research doctor` passes (v1-e01-t14, v1-e01-t22: it fails when the running Python's
#      Unicode database is not the one the normalizer is pinned to, or when a wired integration
#      does not import). A build that fails any of them stops here, and the install it would have
#      replaced is not touched;
#   5. only then installs debate-cli and debate-core **by the file URLs of those two verified
#      wheels** into the real tool directory (`uv tool dir`, or the caller's UV_TOOL_DIR), which
#      puts `debate-research` in uv's tool bin directory (`uv tool dir --bin`, normally
#      ~/.local/bin), in its own environment, outside every checkout and every project .venv, and
#      runs the same checks against it. Third-party dependencies (typer, pydantic, httpx, boto3,
#      lxml…) come from the default index, including those of the debate-core extras debate-cli
#      declares (aws, docx, opencaselist). The rehearsal resolves them; the real install is held to
#      exactly the versions the rehearsal installed (`uv pip freeze` of the rehearsal, passed as
#      `--constraints`, v1-e01-t22), so a release published in between cannot make the real install
#      differ from the one that was checked. Afterwards the two environments must list the same
#      distributions at the same versions, or the script fails.
#
# Why direct URLs, not `--find-links <dir> debate-cli==<version>` (ac2b of the task spec): neither
# `debate-core` nor `debate-cli` is registered on PyPI, and a find-links install keeps PyPI in the
# resolution set for them. Pinning does not help. Dev versions are predictable from the public
# tags, and a squatter who publishes `debate-core==0.1.0.devN` with a more specific wheel tag
# (a CPython one, `cpXY-none-any`) is preferred over our `py3-none-any` wheel at the very same version.
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
# Options:
#   --dir DIRECTORY     use release assets already downloaded there instead of `gh release download`.
#   --no-path-warning   do not warn that `debate-research` on this PATH is another build. For automated
#                       installs into tool directories that are never on the PATH (validate-dev,
#                       dev-prerelease); it silences that one warning and nothing else. A person
#                       running this by hand should leave it off.
#
# Environment:
#   DEBATE_RELEASE_REPO   owner/name to download from (default charlesclark2/debate-intelligence).
#   UV_TOOL_DIR, UV_TOOL_BIN_DIR   honoured by uv as usual for the real install, e.g. to install
#                         somewhere disposable. The rehearsal always goes to a temporary directory.
#
# Needs: uv, unzip, and gh (authenticated) unless --dir is given. No Python is needed beforehand; uv
# provides one that the wheel's Requires-Python admits.
set -eu

REPOSITORY=${DEBATE_RELEASE_REPO:-charlesclark2/debate-intelligence}

fail() {
    echo "install_channel: $*" >&2
    exit 1
}

usage() {
    echo "usage: scripts/install_channel.sh [--dir DIRECTORY] [--no-path-warning] TAG" >&2
    echo "  TAG is vX.Y.Z-dev.N (dev pre-release) or vX.Y.Z (stable release)" >&2
    exit 2
}

ASSETS=""
TAG=""
PATH_WARNING=yes
while [ $# -gt 0 ]; do
    case "$1" in
        --dir) [ $# -ge 2 ] || usage; ASSETS="$2"; shift 2 ;;
        --no-path-warning) PATH_WARNING=no; shift ;;
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

TEMPORARY=${TMPDIR:-/tmp}
TEMPORARY=${TEMPORARY%/}
CLEANUP=""
REHEARSAL=""
cleanup() {
    if [ -n "${CLEANUP}" ]; then
        rm -rf -- "${CLEANUP}"
    fi
    if [ -n "${REHEARSAL}" ]; then
        rm -rf -- "${REHEARSAL}"
    fi
}
trap cleanup EXIT INT TERM

if [ -z "${ASSETS}" ]; then
    command -v gh >/dev/null 2>&1 || fail "gh is not installed (or pass --dir with the assets already downloaded)"
    ASSETS=$(mktemp -d "${TEMPORARY}/debate-research-${TAG}.XXXXXX")
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

# The interpreter, from the wheel's own metadata. The header ends at the first blank line; the long
# description after it may say anything.
command -v unzip >/dev/null 2>&1 || fail "unzip is needed to read the Requires-Python of ${CORE_WHEEL}"
CORE_METADATA="debate_core-${VERSION}.dist-info/METADATA"
METADATA=$(unzip -p "${ASSETS}/${CORE_WHEEL}" "${CORE_METADATA}" 2>/dev/null) \
    || fail "could not read ${CORE_METADATA} from ${CORE_WHEEL}; refusing to guess which Python to install it on"
REQUIRES_PYTHON=$(printf '%s\n' "${METADATA}" | tr -d '\r' | sed -n -e '/^$/q' -e 's/^Requires-Python:[[:space:]]*//p')
[ -n "${REQUIRES_PYTHON}" ] \
    || fail "${CORE_WHEEL} states no Requires-Python in ${CORE_METADATA}; refusing to guess which Python to install it on"
[ "$(printf '%s\n' "${REQUIRES_PYTHON}" | wc -l | tr -d ' ')" = 1 ] \
    || fail "${CORE_WHEEL} states Requires-Python more than once in ${CORE_METADATA}; refusing to guess which one holds"
printf '%s\n' "${REQUIRES_PYTHON}" | grep -Eq '^[0-9A-Za-z.*,<>=!~ ]+$' \
    || fail "${CORE_WHEEL}'s Requires-Python '${REQUIRES_PYTHON}' is not a version specifier; refusing to guess which Python to install it on"

# Install the build into whatever UV_TOOL_DIR and UV_TOOL_BIN_DIR say now, and check it there. The
# rehearsal runs this inside `( … ) ||`, where `set -e` does not apply, so every step that can fail
# says so with its own `|| fail`. An argument, when given, is a constraints file the resolution must
# keep to.
install_and_check() {
    if [ $# -gt 0 ]; then
        set -- --constraints "$1"
    fi
    uv tool install --force --python "${REQUIRES_PYTHON}" "$@" \
        "debate-cli @ ${ASSETS_URL}/${CLI_WHEEL}" \
        --with "debate-core @ ${ASSETS_URL}/${CORE_WHEEL}" \
        || fail "uv could not install debate-cli ${VERSION} on a Python matching '${REQUIRES_PYTHON}'"

    # Belt and braces: each first-party distribution must say it came from the wheel verified above.
    # PEP 610's direct_url.json is written only for a URL install; one resolved from an index has none.
    TOOL_DIRECTORY=$(uv tool dir) || fail "uv tool dir failed"
    TOOL_ENVIRONMENT="${TOOL_DIRECTORY}/debate-cli"
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

    BIN_DIRECTORY=$(uv tool dir --bin) || fail "uv tool dir --bin failed"
    INSTALLED="${BIN_DIRECTORY}/debate-research"
    [ -x "${INSTALLED}" ] || fail "uv reported success but ${INSTALLED} does not exist"

    REPORT=$("${INSTALLED}" --version --json) || fail "${INSTALLED} --version --json failed"
    printf '%s\n' "${REPORT}"
    printf '%s\n' "${REPORT}" | grep -Eq "\"version\": ?\"${VERSION}\"" \
        || fail "the installed debate-research does not report version ${VERSION}"
    printf '%s\n' "${REPORT}" | grep -Eq "\"channel\": ?\"${CHANNEL}\"" \
        || fail "the installed debate-research does not report channel ${CHANNEL}"

    # The build must hold everything its commands are wired to use (v1-e01-t17). `--version` imports
    # none of the integrations, so on its own it passed v0.1.0-dev.33, a build in which every
    # `caselist pull` failed on a missing boto3. This imports every debate_core.integrations module
    # the CLI's composition root imports, read from the installed container's own source, and fails
    # unless it tried every one of them and all imported. It also checks that the distributions
    # behind each debate-core extra the CLI declares were installed. It runs with the tool
    # environment's own interpreter, so it sees exactly what `debate-research` will. Builds published
    # before this check existed do not contain it and are refused; every one of them lacks boto3.
    TOOL_PYTHON="${TOOL_ENVIRONMENT}/bin/python"
    [ -x "${TOOL_PYTHON}" ] || fail "uv reported success but ${TOOL_PYTHON} does not exist"
    echo "Checking that the build can import every integration debate-research wires..."
    "${TOOL_PYTHON}" -m debate_cli.installation \
        || fail "the build installed from ${TAG} is incomplete (see above), so commands that need those integrations will fail; install a different tag"

    # The installation as a whole (v1-e01-t14). doctor exits non-zero on one check, the one it can
    # state precisely: this Python's Unicode database is not the one the evidence normalizer is
    # pinned to, so every command that normalizes evidence text would refuse to run.
    echo "Checking the installation with debate-research doctor..."
    "${INSTALLED}" doctor \
        || fail "debate-research doctor failed for the build installed from ${TAG} (see above)"
}

echo "Rehearsing the install of debate-cli ${VERSION} (${CHANNEL} channel) from ${ASSETS_ABSOLUTE},"
echo "on a Python matching '${REQUIRES_PYTHON}' (debate_core's Requires-Python), in a temporary tool directory..."
REHEARSAL=$(mktemp -d "${TEMPORARY}/debate-research-rehearsal.XXXXXX")
(
    UV_TOOL_DIR="${REHEARSAL}/tools"
    UV_TOOL_BIN_DIR="${REHEARSAL}/bin"
    export UV_TOOL_DIR UV_TOOL_BIN_DIR
    install_and_check
) || fail "the build from ${TAG} failed a check in the rehearsal install (see above); the installed debate-research was not touched"

# The real install resolves the third-party dependencies again, and a release published since the
# rehearsal would win (v1-e01-t22). So it is pinned to exactly what the rehearsal installed, read
# from the rehearsal's environment: every third-party distribution as `name==version`. The two
# first-party lines are left out, because the verified file URLs already decide them. Anything else
# cannot be pinned, and the script refuses rather than install something the rehearsal did not check.
REHEARSED_PYTHON="${REHEARSAL}/tools/debate-cli/bin/python"
REHEARSED="${REHEARSAL}/rehearsed.txt"
CONSTRAINTS="${REHEARSAL}/constraints.txt"
uv pip freeze --quiet --python "${REHEARSED_PYTHON}" > "${REHEARSED}" \
    || fail "could not list what the rehearsal installed; the installed debate-research was not touched"
UNPINNABLE=$(awk '
    /^debate-(cli|core) @ / { next }
    /^debate-(cli|core)[^A-Za-z0-9._-]/ { print; next }
    /^[A-Za-z0-9][A-Za-z0-9._-]*==[A-Za-z0-9.!+_-]+$/ { next }
    { print }
' "${REHEARSED}")
[ -z "${UNPINNABLE}" ] \
    || fail "the rehearsal installed $(printf '%s' "${UNPINNABLE}" | head -n 1), which cannot be pinned for the real install; the installed debate-research was not touched"
grep -Ev '^debate-(cli|core) @ ' "${REHEARSED}" > "${CONSTRAINTS}" || true
PINNED=$(wc -l < "${CONSTRAINTS}" | tr -d ' ')
if [ "${PINNED}" = 1 ]; then NOUN=distribution; else NOUN=distributions; fi

echo "The rehearsal passed. Installing debate-cli ${VERSION} (${CHANNEL} channel) as a uv tool..."
echo "Pinning the real install to the ${PINNED} third-party ${NOUN} the rehearsal checked."
install_and_check "${CONSTRAINTS}"

# What uv was asked for is not proof of what it did. The real environment must hold exactly what the
# rehearsal's did, so a uv that ignored the pins is caught here rather than trusted. By now the real
# install has replaced the previous one, so this makes the exit status true; the pins are what kept
# the two the same.
INSTALLED_LIST="${REHEARSAL}/installed.txt"
uv pip freeze --quiet --python "${TOOL_ENVIRONMENT}/bin/python" > "${INSTALLED_LIST}" \
    || fail "could not list what the real install holds, so it cannot be shown to be the build the rehearsal checked"
if ! diff "${REHEARSED}" "${INSTALLED_LIST}" > "${REHEARSAL}/difference.txt"; then
    sed -n -e 's/^< /-/p' -e 's/^> /+/p' "${REHEARSAL}/difference.txt" >&2
    fail "the real install is not the build the rehearsal checked (- rehearsal, + real install, above). It has already replaced the previous install. Run this script again; if it fails the same way, this uv is not keeping to --constraints"
fi

if [ "${PATH_WARNING}" = yes ]; then
    ON_PATH=$(command -v debate-research || true)
    if [ "${ON_PATH}" != "${INSTALLED}" ]; then
        echo "" >&2
        echo "install_channel: warning — \`debate-research\` on this PATH is ${ON_PATH:-nothing}," >&2
        echo "install_channel: not the build just installed at ${INSTALLED}." >&2
        echo "install_channel: put ${BIN_DIRECTORY} before any project .venv/bin on PATH" >&2
        echo "install_channel: (\`uv tool update-shell\` adds it), or call ${INSTALLED} by its full path." >&2
    fi
fi

echo "Installed debate-research ${VERSION} from ${TAG} at ${INSTALLED}."
