#!/bin/sh
# Render the weekly caselist-sync launchd agent for this machine, and put it where launchd reads it.
#
# It does not start anything. Installing the file and enabling the schedule are two steps on
# purpose: the first scheduled prod run happens only after one manual `DEBATE_ENV=dev
# debate-research caselist pull` has validated the pipeline
# (docs/runbooks/caselist-scheduled-sync.md). This script prints the `launchctl bootstrap` line to
# run next; it never runs it.
#
# The agent runs nothing from the checkout this script sits in. The wrapper is copied to
# $HOME/.local/share/debate-research/launchd/ and the plist names the copy, so the agent neither
# follows the checkout's branch nor reads under ~/Documents, which launchd may not open (the
# first scheduled run, on 2026-10-07, exited 126 with "Operation not permitted"). Running this
# script again replaces the copy. Every path the agent will use is refused if it lies inside a git
# working tree or a project .venv, or under ~/Documents, ~/Desktop, ~/Downloads, iCloud Drive
# (~/Library/Mobile Documents) or /Volumes.
#
#   ops/launchd/install.sh --caselist hsld26 --caselist hspolicy26 --dry-run
#   ops/launchd/install.sh --caselist hsld26 --env prod --aws-profile debate-prod-evidence
#   ops/launchd/install.sh --check-launchd
#
# Options
#   --caselist SLUG      A caselist the weekly run covers. Repeatable. At least one is required:
#                        which caselists this installation follows is the operator's decision and
#                        is not written down in this repository.
#   --env ENVIRONMENT    DEBATE_ENV for the agent. Default: prod.
#   --aws-profile NAME   The SSO profile for that environment's evidence bucket.
#                        Default: debate-<env>-evidence.
#   --weekday N          1 = Monday … 7 = Sunday. Default: 3 (Wednesday), the day after the site
#                        has published the week's archives.
#   --hour N             Default: 6.  --minute N   Default: 0.
#   --label NAME         launchd label. Default: com.debate-intelligence.caselist-sync.
#   --log-dir PATH       Default: $HOME/Library/Logs/debate-research.
#   --wrapper-dir PATH   Where the wrapper is copied for the agent to run.
#                        Default: $HOME/.local/share/debate-research/launchd.
#   --debate-research P  Full path to the console script the agent runs, written into the plist
#                        as DEBATE_RESEARCH_BIN. Default: whatever `command -v debate-research`
#                        finds, as found (a symlink stays a symlink).
#   --dry-run            Render the plist to stdout and write nothing at all.
#   --check-launchd      Prove launchd can run the installed agent's wrapper, without a sync: load
#                        a one-off copy of the installed plist as <label>.check, running the
#                        wrapper's `--check` (which only prints the console script's version),
#                        kickstart it, print its log and exit code, and boot it out. The agent
#                        itself is only read, and its run count is shown before and after.
#   -h, --help           This text.
set -eu

SCRIPT_DIRECTORY=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
TEMPLATE="${SCRIPT_DIRECTORY}/com.debate-intelligence.caselist-sync.plist.template"
WRAPPER_SOURCE="${SCRIPT_DIRECTORY}/run-caselist-sync.sh"
WRAPPER_NAME="run-caselist-sync.sh"

# What the agent's PATH holds besides the console script's own directory. `debate-research`
# itself runs `osascript` for notifications, which is here; its interpreter is named by its
# shebang, so it needs nothing else.
SYSTEM_PATH="/usr/bin:/bin:/usr/sbin:/sbin"

LABEL="com.debate-intelligence.caselist-sync"
DEBATE_ENVIRONMENT="prod"
AWS_PROFILE_NAME=""
WEEKDAY=3
HOUR=6
MINUTE=0
LOG_DIRECTORY=""
WRAPPER_DIRECTORY=""
DEBATE_RESEARCH_PATH=""
DRY_RUN=0
CHECK_LAUNCHD=0
CASELISTS=""

usage() {
    # Every comment line at the top of this file, less its `# `, and stopping at the first line
    # that is not one — so the help and the header can never drift apart.
    awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"
}

fail() {
    echo "install.sh: $1" >&2
    exit 2
}

lower() {
    printf '%s\n' "$1" | tr '[:upper:]' '[:lower:]'
}

# The path with every symbolic link resolved, for as much of it as exists; the rest is appended
# as written. Done by hand because neither `realpath` nor `readlink -f` is on every Mac.
physical_path() {
    target=$1
    hops=0
    while [ -L "${target}" ]; do
        hops=$((hops + 1))
        [ "${hops}" -le 40 ] || fail "${1} is a loop of symbolic links"
        link=$(readlink "${target}")
        case "${link}" in
            /*) target=${link} ;;
            *) target=$(dirname -- "${target}")/${link} ;;
        esac
    done
    existing=${target}
    remainder=""
    while [ ! -d "${existing}" ]; do
        remainder=/$(basename -- "${existing}")${remainder}
        existing=$(dirname -- "${existing}")
    done
    resolved=$(cd -P -- "${existing}" && pwd -P)
    [ "${resolved}" != "/" ] || resolved=""
    printf '%s%s\n' "${resolved}" "${remainder}"
}

# The folder macOS privacy protection (TCC) keeps background processes out of, if the path is
# under one. A launchd agent that opens anything there gets "Operation not permitted". Compared
# without case, because the Mac's disk ignores it.
protected_folder_of() {
    candidate="$(lower "$1")/"
    for home in "${HOME}" "${PHYSICAL_HOME}"; do
        for folder in "${home}/Documents" "${home}/Desktop" "${home}/Downloads" "${home}/Library/Mobile Documents"; do
            case "${candidate}" in
                "$(lower "${folder}")"/*) printf '%s\n' "${folder}"; return 0 ;;
            esac
        done
    done
    case "${candidate}" in
        /volumes/*) printf '%s\n' /Volumes; return 0 ;;
    esac
    return 1
}

# The top of the git working tree the path is in, if it is in one: a directory above it holding
# `.git`, which is a directory in a clone and a file in a worktree.
working_tree_of() {
    directory=$1
    while :; do
        if [ -e "${directory}/.git" ]; then
            printf '%s\n' "${directory}"
            return 0
        fi
        case "${directory}" in
            /|'') return 1 ;;
        esac
        directory=$(dirname -- "${directory}")
    done
}

# Refuse a path the agent will use if launchd may not open it, or if it can change under the agent.
# An optional third argument is said after the reason.
refuse_unsafe_path() {
    what=$1
    candidate=$2
    advice=${3:+; $3}
    case "${candidate}" in
        /*) ;;
        *) fail "the ${what} must be an absolute path, not '${candidate}'" ;;
    esac
    case "/${candidate}/" in
        */./*|*/../*) fail "the ${what} ${candidate} has a '.' or '..' in it; give the path itself" ;;
    esac
    physical=$(physical_path "${candidate}")
    shown=${candidate}
    [ "${physical}" = "${candidate}" ] || shown="${candidate} (which is ${physical})"
    for form in "${candidate}" "${physical}"; do
        if folder=$(protected_folder_of "${form}"); then
            fail "refusing the ${what} ${shown}: it is under ${folder}, and macOS privacy protection does not let a launchd agent open anything there (the agent would exit 126, \"Operation not permitted\")${advice}"
        fi
        case "${form}/" in
            */.venv/*) fail "refusing the ${what} ${shown}: it is inside a project .venv, which is deleted and recreated whenever that project is synced${advice}" ;;
        esac
    done
    if tree=$(working_tree_of "${physical}"); then
        fail "refusing the ${what} ${shown}: it is inside the git working tree ${tree}, whose files change with whatever branch is checked out there${advice}"
    fi
}

# `runs = N` from `launchctl print`, or "not loaded".
runs_of() {
    runs=$(launchctl print "$1" 2>/dev/null | sed -n 's/^[[:space:]]*runs = \([0-9][0-9]*\)$/\1/p' | head -n 1)
    printf '%s\n' "${runs:-not loaded}"
}

while [ $# -gt 0 ]; do
    case "$1" in
        --caselist) [ $# -ge 2 ] || fail "--caselist needs a slug"; CASELISTS="${CASELISTS} $2"; shift 2 ;;
        --env) [ $# -ge 2 ] || fail "--env needs a value"; DEBATE_ENVIRONMENT="$2"; shift 2 ;;
        --aws-profile) [ $# -ge 2 ] || fail "--aws-profile needs a value"; AWS_PROFILE_NAME="$2"; shift 2 ;;
        --weekday) [ $# -ge 2 ] || fail "--weekday needs a value"; WEEKDAY="$2"; shift 2 ;;
        --hour) [ $# -ge 2 ] || fail "--hour needs a value"; HOUR="$2"; shift 2 ;;
        --minute) [ $# -ge 2 ] || fail "--minute needs a value"; MINUTE="$2"; shift 2 ;;
        --label) [ $# -ge 2 ] || fail "--label needs a value"; LABEL="$2"; shift 2 ;;
        --log-dir) [ $# -ge 2 ] || fail "--log-dir needs a path"; LOG_DIRECTORY="$2"; shift 2 ;;
        --wrapper-dir) [ $# -ge 2 ] || fail "--wrapper-dir needs a path"; WRAPPER_DIRECTORY="$2"; shift 2 ;;
        --debate-research) [ $# -ge 2 ] || fail "--debate-research needs a path"; DEBATE_RESEARCH_PATH="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        --check-launchd) CHECK_LAUNCHD=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) fail "unknown option $1 (--help lists them)" ;;
    esac
done

HOME=${HOME%/}
[ -n "${HOME}" ] || fail "HOME is not set"
PHYSICAL_HOME=$(physical_path "${HOME}")

# --- The launchd check: a one-off label running the installed wrapper's `--check` -------------

if [ "${CHECK_LAUNCHD}" -eq 1 ]; then
    [ -z "${CASELISTS}" ] && [ "${DRY_RUN}" -eq 0 ] || fail "--check-launchd takes no options but --label"
    for tool in launchctl plutil; do
        command -v "${tool}" >/dev/null 2>&1 || fail "--check-launchd needs macOS's ${tool}"
    done
    INSTALLED="${HOME}/Library/LaunchAgents/${LABEL}.plist"
    [ -f "${INSTALLED}" ] || fail "no agent is installed at ${INSTALLED}; install it first"
    INSTALLED_WRAPPER=$(plutil -extract ProgramArguments.0 raw -o - "${INSTALLED}") \
        || fail "${INSTALLED} has no ProgramArguments"
    # The check is for an agent this script installed: one running a copy of this wrapper, which
    # has the `--check` mode. An older plist names the checkout's wrapper, which is refused here
    # rather than handed `--check`.
    refuse_unsafe_path "installed agent's wrapper" "${INSTALLED_WRAPPER}" "reinstall with this script first"
    cmp -s "${INSTALLED_WRAPPER}" "${WRAPPER_SOURCE}" \
        || fail "the installed agent's wrapper ${INSTALLED_WRAPPER} is not this checkout's ${WRAPPER_SOURCE}; reinstall with this script first"
    CHECK_LOG="$(dirname -- "$(plutil -extract StandardOutPath raw -o - "${INSTALLED}")")/caselist-sync-check.log"
    DOMAIN="gui/$(id -u)"
    CHECK_LABEL="${LABEL}.check"
    CHECK_WORKSPACE=$(mktemp -d "${TMPDIR:-/tmp}/caselist-sync-check.XXXXXX")
    CHECK_PLIST="${CHECK_WORKSPACE}/${CHECK_LABEL}.plist"
    CHECK_LOADED=0
    # shellcheck disable=SC2329 # run by the EXIT trap below
    cleanup() {
        if [ "${CHECK_LOADED}" -eq 1 ]; then
            launchctl bootout "${DOMAIN}/${CHECK_LABEL}" >/dev/null 2>&1 || true
        fi
        rm -rf "${CHECK_WORKSPACE}"
    }
    trap cleanup EXIT
    trap 'exit 130' HUP INT TERM

    # The installed plist, less its schedule and its caselists: same wrapper, same environment,
    # same working directory, and a log of its own.
    cp "${INSTALLED}" "${CHECK_PLIST}"
    plutil -replace Label -string "${CHECK_LABEL}" "${CHECK_PLIST}"
    while plutil -extract ProgramArguments.1 raw -o - "${CHECK_PLIST}" >/dev/null 2>&1; do
        plutil -remove ProgramArguments.1 "${CHECK_PLIST}"
    done
    plutil -insert ProgramArguments.1 -string --check "${CHECK_PLIST}"
    plutil -remove StartCalendarInterval "${CHECK_PLIST}" >/dev/null 2>&1 || true
    plutil -replace RunAtLoad -bool false "${CHECK_PLIST}"
    plutil -replace StandardOutPath -string "${CHECK_LOG}" "${CHECK_PLIST}"
    plutil -replace StandardErrorPath -string "${CHECK_LOG}" "${CHECK_PLIST}"
    plutil -lint "${CHECK_PLIST}" >/dev/null || fail "the check's plist did not lint"

    RUNS_BEFORE=$(runs_of "${DOMAIN}/${LABEL}")
    if launchctl print "${DOMAIN}/${CHECK_LABEL}" >/dev/null 2>&1; then
        launchctl bootout "${DOMAIN}/${CHECK_LABEL}"
    fi
    : > "${CHECK_LOG}"
    echo "Loading ${CHECK_LABEL}: ${INSTALLED_WRAPPER} --check"
    launchctl bootstrap "${DOMAIN}" "${CHECK_PLIST}"
    CHECK_LOADED=1
    launchctl kickstart "${DOMAIN}/${CHECK_LABEL}"

    EXIT_CODE=""
    waited=0
    while :; do
        status=$(launchctl print "${DOMAIN}/${CHECK_LABEL}" 2>/dev/null || true)
        state=$(printf '%s\n' "${status}" | sed -n 's/^[[:space:]]*state = \(.*\)$/\1/p' | head -n 1)
        EXIT_CODE=$(printf '%s\n' "${status}" | sed -n 's/^[[:space:]]*last exit code = \([0-9][0-9]*\).*$/\1/p' | head -n 1)
        if [ "${state}" = "not running" ] && [ -n "${EXIT_CODE}" ]; then
            break
        fi
        waited=$((waited + 1))
        if [ "${waited}" -gt 60 ]; then
            EXIT_CODE="none (it had not finished after 60 seconds)"
            break
        fi
        sleep 1
    done

    launchctl bootout "${DOMAIN}/${CHECK_LABEL}"
    CHECK_LOADED=0
    RUNS_AFTER=$(runs_of "${DOMAIN}/${LABEL}")

    echo "--- ${CHECK_LOG}"
    cat "${CHECK_LOG}"
    echo "---"
    echo "${CHECK_LABEL} exit code ${EXIT_CODE}"
    echo "Booted out ${CHECK_LABEL}"
    echo "${LABEL} runs: ${RUNS_BEFORE} before, ${RUNS_AFTER} after"
    if [ "${RUNS_BEFORE}" != "${RUNS_AFTER}" ]; then
        echo "install.sh: the agent's run count changed during the check; it is not evidence the agent can run" >&2
        exit 1
    fi
    [ "${EXIT_CODE}" = "0" ] || exit 1
    exit 0
fi

# --- Installing ---------------------------------------------------------------------------------

[ -f "${TEMPLATE}" ] || fail "the plist template is missing at ${TEMPLATE}"
[ -n "${CASELISTS}" ] || fail "at least one --caselist is required; see --help"
[ -n "${LOG_DIRECTORY}" ] || LOG_DIRECTORY="${HOME}/Library/Logs/debate-research"
[ -n "${WRAPPER_DIRECTORY}" ] || WRAPPER_DIRECTORY="${HOME}/.local/share/debate-research/launchd"
[ -n "${AWS_PROFILE_NAME}" ] || AWS_PROFILE_NAME="debate-${DEBATE_ENVIRONMENT}-evidence"

case "${DEBATE_ENVIRONMENT}" in
    dev|prod) ;;
    *) fail "--env is dev or prod, not '${DEBATE_ENVIRONMENT}' (docs/process/branching-and-environments.md)" ;;
esac
for number in "${WEEKDAY}" "${HOUR}" "${MINUTE}"; do
    case "${number}" in
        ''|*[!0-9]*) fail "--weekday, --hour and --minute take whole numbers; got '${number}'" ;;
    esac
done
[ "${WEEKDAY}" -ge 1 ] && [ "${WEEKDAY}" -le 7 ] || fail "--weekday is 1 (Monday) to 7 (Sunday)"
[ "${HOUR}" -le 23 ] || fail "--hour is 0 to 23"
[ "${MINUTE}" -le 59 ] || fail "--minute is 0 to 59"

# A caselist slug is letters then a two-digit season year (debate_core.domain.caselist). Checked
# here as well as in the command, because anything else would be written straight into an XML
# document as an argument the agent runs every week.
for slug in ${CASELISTS}; do
    case "${slug}" in
        *[!a-z0-9]*|'') fail "'${slug}' is not a caselist slug (letters then a two-digit year, e.g. hsld26)" ;;
    esac
done

# The console script is written into the plist as the operator gave it or as this shell finds it,
# never resolved: ~/.local/bin/debate-research is a link uv repoints on every install, so the
# link is the name that stays right.
if [ -z "${DEBATE_RESEARCH_PATH}" ]; then
    DEBATE_RESEARCH_PATH=$(command -v debate-research || true)
    [ -n "${DEBATE_RESEARCH_PATH}" ] \
        || fail "debate-research is not on this shell's PATH; install a build with scripts/install_channel.sh, or pass --debate-research with its full path"
fi
refuse_unsafe_path "console script" "${DEBATE_RESEARCH_PATH}"
[ -f "${DEBATE_RESEARCH_PATH}" ] && [ -x "${DEBATE_RESEARCH_PATH}" ] \
    || fail "the console script ${DEBATE_RESEARCH_PATH} is not an executable file"
AGENT_PATH="$(dirname -- "${DEBATE_RESEARCH_PATH}"):${SYSTEM_PATH}"

refuse_unsafe_path "home directory" "${HOME}"
refuse_unsafe_path "wrapper destination" "${WRAPPER_DIRECTORY}"
refuse_unsafe_path "log directory" "${LOG_DIRECTORY}"
WRAPPER="${WRAPPER_DIRECTORY}/${WRAPPER_NAME}"

# Where the agent will keep its data comes from the profile bundled into the installed build, so
# the build is asked, with the environment the plist gives it and nothing of this shell's.
# `config show` only reads.
REPORTED_SETTINGS=$(cd -- "${HOME}" && env -i HOME="${HOME}" PATH="${AGENT_PATH}" \
    DEBATE_ENV="${DEBATE_ENVIRONMENT}" AWS_PROFILE="${AWS_PROFILE_NAME}" \
    "${DEBATE_RESEARCH_PATH}" --json config show) \
    || fail "${DEBATE_RESEARCH_PATH} --json config show failed, so the agent's data directory is unknown; nothing was installed"
# The value under `settings`, not the one under `sources`, which names the same key with the file
# it came from. The settings object holds no braces, so a value that ever did would make this
# find nothing and refuse, rather than read the wrong thing.
DATA_DIRECTORY=$(printf '%s\n' "${REPORTED_SETTINGS}" \
    | sed -n 's/.*"settings": *{\([^{}]*\)}.*/\1/p' \
    | sed -n 's/.*"storage\.data_dir": *"\([^"\\]*\)".*/\1/p' | head -n 1)
[ -n "${DATA_DIRECTORY}" ] \
    || fail "${DEBATE_RESEARCH_PATH} --json config show did not report storage.data_dir, so the agent's data directory is unknown; nothing was installed"
refuse_unsafe_path "data directory" "${DATA_DIRECTORY}"

# `awk` rather than `sed`, because several of the values are paths that may contain a `/` and one
# is a multi-line block; awk's index/substr replacement treats every value as a literal.
render() {
    awk \
        -v label="${LABEL}" \
        -v wrapper="${WRAPPER}" \
        -v caselists="${CASELISTS}" \
        -v weekday="${WEEKDAY}" \
        -v hour="${HOUR}" \
        -v minute="${MINUTE}" \
        -v debate_env="${DEBATE_ENVIRONMENT}" \
        -v aws_profile="${AWS_PROFILE_NAME}" \
        -v debate_research_bin="${DEBATE_RESEARCH_PATH}" \
        -v home_directory="${HOME}" \
        -v path_value="${AGENT_PATH}" \
        -v log_directory="${LOG_DIRECTORY}" \
        -v working_directory="${HOME}" \
        '
        function fill(line, name, value,   at) {
            while ((at = index(line, name)) > 0) {
                line = substr(line, 1, at - 1) value substr(line, at + length(name))
            }
            return line
        }
        {
            line = $0
            # The one placeholder that is a block rather than a value: two elements per caselist,
            # written here so the XML shape lives in the template and this script beside it, and
            # nowhere else.
            if (index(line, "@CASELIST_ARGUMENTS@") > 0) {
                count = split(caselists, slugs, " ")
                for (each = 1; each <= count; each++) {
                    if (slugs[each] == "") continue
                    print "        <string>--caselist</string>"
                    print "        <string>" slugs[each] "</string>"
                }
                next
            }
            line = fill(line, "@LABEL@", label)
            line = fill(line, "@WRAPPER@", wrapper)
            line = fill(line, "@WEEKDAY@", weekday)
            line = fill(line, "@HOUR@", hour)
            line = fill(line, "@MINUTE@", minute)
            line = fill(line, "@DEBATE_ENV@", debate_env)
            line = fill(line, "@AWS_PROFILE@", aws_profile)
            line = fill(line, "@DEBATE_RESEARCH_BIN@", debate_research_bin)
            line = fill(line, "@HOME_DIRECTORY@", home_directory)
            line = fill(line, "@PATH_VALUE@", path_value)
            line = fill(line, "@LOG_DIRECTORY@", log_directory)
            line = fill(line, "@WORKING_DIRECTORY@", working_directory)
            print line
        }
        ' "${TEMPLATE}"
}

if [ "${DRY_RUN}" -eq 1 ]; then
    render
    exit 0
fi

AGENT_DIRECTORY="${HOME}/Library/LaunchAgents"
DESTINATION="${AGENT_DIRECTORY}/${LABEL}.plist"
mkdir -p "${AGENT_DIRECTORY}" "${LOG_DIRECTORY}" "${WRAPPER_DIRECTORY}"

render > "${DESTINATION}.incoming"
if command -v plutil >/dev/null 2>&1; then
    plutil -lint "${DESTINATION}.incoming" >/dev/null || {
        rm -f "${DESTINATION}.incoming"
        fail "the rendered plist did not lint; nothing was installed"
    }
fi

# The wrapper first, so the plist never names a wrapper that is not there. A rename, so a run that
# starts mid-install reads either the old copy or the new one, never half of one, and so a copy
# that was a symlink is replaced by a file.
cp "${WRAPPER_SOURCE}" "${WRAPPER}.incoming"
chmod 0755 "${WRAPPER}.incoming"
mv -f "${WRAPPER}.incoming" "${WRAPPER}"

mv "${DESTINATION}.incoming" "${DESTINATION}"
chmod 644 "${DESTINATION}"

echo "Wrote ${DESTINATION}"
echo "Copied the wrapper to ${WRAPPER}"
echo "The agent runs ${DEBATE_RESEARCH_PATH} and keeps its data in ${DATA_DIRECTORY}"
echo "Logs will be written to ${LOG_DIRECTORY}"
echo
echo "Nothing is scheduled yet. Validate the pipeline first, then enable the agent:"
echo
echo "  DEBATE_ENV=dev debate-research caselist pull${CASELISTS} --dry-run"
echo "  DEBATE_ENV=dev debate-research caselist pull${CASELISTS}"
echo "  launchctl bootstrap gui/\$UID ${DESTINATION}"
echo "  launchctl print gui/\$UID/${LABEL}"
echo "  $0 --check-launchd"
echo
echo "If the agent was already loaded, the new wrapper is used from its next run, but launchd keeps"
echo "the old plist until it is booted out and bootstrapped again."
echo
echo "docs/runbooks/caselist-scheduled-sync.md has the whole procedure, including how to disable it."
