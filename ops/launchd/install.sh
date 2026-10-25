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
# (~/Library/Mobile Documents), ~/Library/CloudStorage (Dropbox, Google Drive and other File
# Provider folders) or /Volumes.
#
#   ops/launchd/install.sh --env dev --dry-run
#   ops/launchd/install.sh --debate-research "$HOME/.local/bin/debate-research"
#   ops/launchd/install.sh --check-launchd
#
# The agent's wrapper runs `debate-research caselist pull` with no `--caselist`: the caselists the
# weekly run follows are the build's setting `caselist.sync_caselists`, in the environment's profile
# (ADR-0020 (5), v1-e40-t06), the one the cloud run reads from the same build. This script asks the
# build for them and refuses to install an agent whose build names none. There is no --caselist any
# more. An agent installed before v1-e40-t06 named its caselists as arguments in its plist; a
# reinstall over one drops them, and says which they were and which the build names.
#
# Over an installed agent (a plist already at ~/Library/LaunchAgents/<label>.plist) the installed
# plist is read first, and an option left out keeps what it says: the agent's environment
# (v1-e34-t24), its schedule, its log directory and its wrapper directory (v1-e34-t25) are changed
# only by an option that says so, and the installer says what it kept and which key of the plist it
# read it from. A setting the plist does not hold as this script writes it is refused,
# naming the option that sets it, and never replaced by the default. Before it writes anything, a
# dry run included, it asks the build where the agent's data will be and runs the build's own
# checks with the agent's evidence profile, `debate-research doctor --evidence-profiles`, as the
# agent will run them. It refuses a profile this machine's AWS config does not define, and a build
# whose checks fail.
#
# The AWS profile the run uses is the build's setting `storage.s3.aws_profile`, not an option
# here. There is no --aws-profile: it wrote AWS_PROFILE into the plist, which nothing the agent
# runs reads (v1-e34-t24).
#
# Options
#   --env ENVIRONMENT    DEBATE_ENV for the agent, dev or prod. Default: the installed agent's, or
#                        prod for a first install. A different one from the installed agent's is
#                        refused without --confirm-env-change.
#   --confirm-env-change Confirm an install that switches the installed agent to another
#                        environment, or that moves its data directory: another store, and with
#                        another environment another evidence bucket.
#   --weekday N          1 = Monday … 7 = Sunday. Default: the installed agent's, or 3 (Wednesday)
#                        for a first install, the day after the site has published the week's
#                        archives.
#   --hour N             Default: the installed agent's, or 6.
#   --minute N           Default: the installed agent's, or 0.
#   --label NAME         launchd label. Default: com.debate-intelligence.caselist-sync.
#   --log-dir PATH       Default: the installed agent's, or $HOME/Library/Logs/debate-research.
#   --wrapper-dir PATH   Where the wrapper is copied for the agent to run. Default: the installed
#                        agent's, or $HOME/.local/share/debate-research/launchd. A copy left in
#                        the old directory is not removed.
#   --debate-research P  Full path to the console script the agent runs, written into the plist
#                        as DEBATE_RESEARCH_BIN. Default: whatever `command -v debate-research`
#                        finds, as found (a symlink stays a symlink).
#   --dry-run            Make every check an install makes, the profile check included, render the
#                        plist to stdout and write nothing at all. What is kept or changed over an
#                        installed agent is said on stderr.
#   --check-launchd      Prove launchd can run the installed agent's wrapper, that the AWS
#                        profile the weekly run uses is defined, and that every store its search
#                        index stage will index is parsed, without a sync: load a one-off copy of
#                        the installed plist as <label>.check, running the wrapper's `--check`
#                        (which prints the console script's version and then runs
#                        `debate-research doctor --evidence-profiles --search-index`; an agent
#                        installed before v1-e40-t06 has its plist's caselists handed to it as
#                        caselist.sync_caselists), kickstart it, print its
#                        log and exit code, and boot it out. The log names each configured
#                        evidence profile, whether this machine's AWS config defines it and which
#                        permission set it is signed in as, and each store and whether this build
#                        has parsed it; the check fails (exit 1) on a profile that is not defined
#                        or a store never parsed, and not on an expired session. The agent itself
#                        is only read, and its run count is shown before and after. It takes no
#                        option but --label, and refuses any other by name: each would be ignored.
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
DEBATE_ENVIRONMENT=""
ENVIRONMENT_GIVEN=0
CONFIRM_ENV_CHANGE=0
WEEKDAY=""
WEEKDAY_GIVEN=0
HOUR=""
HOUR_GIVEN=0
MINUTE=""
MINUTE_GIVEN=0
LOG_DIRECTORY=""
LOG_DIRECTORY_GIVEN=0
WRAPPER_DIRECTORY=""
WRAPPER_DIRECTORY_GIVEN=0
DEBATE_RESEARCH_PATH=""
DRY_RUN=0
CHECK_LAUNCHD=0
OPTIONS_GIVEN=""

usage() {
    # Every comment line at the top of this file, less its `# `, and stopping at the first line
    # that is not one — so the help and the header can never drift apart.
    awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"
}

fail() {
    echo "install.sh: $1" >&2
    exit 2
}

# What the installer kept or changed, said beside the plist rather than in it: on stderr for a dry
# run, whose stdout is the plist, and on stdout otherwise.
note() {
    if [ "${DRY_RUN}" -eq 1 ]; then
        printf '%s\n' "$1" >&2
    else
        printf '%s\n' "$1"
    fi
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
        for folder in "${home}/Documents" "${home}/Desktop" "${home}/Downloads" \
            "${home}/Library/Mobile Documents" "${home}/Library/CloudStorage"; do
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

# A whole number as written, less its leading zeros, so that `--hour 07` and an installed 7 are one
# value and `printf %02d` never reads `08` as octal.
without_leading_zeros() {
    printf '%s\n' "$1" | sed 's/^0*\([0-9]\)/\1/'
}

# 1 to 7, as launchd's Weekday and this script's --weekday count them.
weekday_name() {
    case "$1" in
        1) echo Monday ;; 2) echo Tuesday ;; 3) echo Wednesday ;; 4) echo Thursday ;;
        5) echo Friday ;; 6) echo Saturday ;; 7) echo Sunday ;;
    esac
}

# `Wednesday at 06:00`, from a weekday, an hour and a minute.
schedule_of() {
    printf '%s at %02d:%02d\n' "$(weekday_name "$1")" "$2" "$3"
}

# --- Reading an installed agent's settings back (v1-e34-t25) -------------------------------------
#
# Each prints the setting as this script would write it, or, returning 1, why it cannot be read
# back as one: a value written by hand, a key missing, or plutil's own refusal less the file's
# name. A setting that cannot be read is never replaced by its default; the caller refuses.

# One of the calendar interval's integers: StartCalendarInterval.<key>, between the two bounds.
installed_calendar_integer() {
    if ! answer=$(plutil -extract "StartCalendarInterval.$1" raw -expect integer -o - "${DESTINATION}" 2>&1); then
        printf '%s\n' "${answer#"${DESTINATION}": }"
        return 1
    fi
    case "${answer}" in
        ''|*[!0-9]*) printf 'it is %s, not a whole number\n' "${answer}"; return 1 ;;
    esac
    if [ "${answer}" -lt "$2" ] || [ "${answer}" -gt "$3" ]; then
        printf 'it is %s, and this script writes %s to %s\n' "${answer}" "$2" "$3"
        return 1
    fi
    without_leading_zeros "${answer}"
}

# The one directory both logs are in, under the names the template gives them.
installed_log_directory() {
    if ! out_log=$(plutil -extract StandardOutPath raw -expect string -o - "${DESTINATION}" 2>&1); then
        printf 'StandardOutPath: %s\n' "${out_log#"${DESTINATION}": }"
        return 1
    fi
    if ! error_log=$(plutil -extract StandardErrorPath raw -expect string -o - "${DESTINATION}" 2>&1); then
        printf 'StandardErrorPath: %s\n' "${error_log#"${DESTINATION}": }"
        return 1
    fi
    logs=$(dirname -- "${out_log}")
    if [ "${out_log}" != "${logs}/caselist-sync.jsonl" ]; then
        printf 'StandardOutPath is %s, not a caselist-sync.jsonl\n' "${out_log}"
        return 1
    fi
    if [ "${error_log}" != "${logs}/caselist-sync.err.log" ]; then
        printf 'StandardErrorPath is %s, not the caselist-sync.err.log beside StandardOutPath, %s/caselist-sync.err.log\n' \
            "${error_log}" "${logs}"
        return 1
    fi
    printf '%s\n' "${logs}"
}

# The directory the wrapper the agent runs is in, when it is a copy of this script's wrapper.
installed_wrapper_directory() {
    if ! wrapper=$(plutil -extract ProgramArguments.0 raw -expect string -o - "${DESTINATION}" 2>&1); then
        printf '%s\n' "${wrapper#"${DESTINATION}": }"
        return 1
    fi
    if [ "$(basename -- "${wrapper}")" != "${WRAPPER_NAME}" ]; then
        printf 'it is %s, not a %s\n' "${wrapper}" "${WRAPPER_NAME}"
        return 1
    fi
    dirname -- "${wrapper}"
}

# Refuse a reinstall that would have to replace an installed setting it cannot read with a default.
cannot_keep() {
    fail "the agent installed at ${DESTINATION} holds no ${1} this script can read back (${2}), so ${3} cannot be kept; nothing was installed. Give ${4} to say what it is to be"
}

# A directory as given, less any trailing `/`, so that it reads back from the plist as given.
without_trailing_slashes() {
    trimmed=$1
    while [ "${trimmed}" != "/" ] && [ "${trimmed%/}" != "${trimmed}" ]; do
        trimmed=${trimmed%/}
    done
    printf '%s\n' "${trimmed}"
}

while [ $# -gt 0 ]; do
    # Each option by name, without its value, for the launchd check's guard below.
    OPTIONS_GIVEN="${OPTIONS_GIVEN} $1"
    case "$1" in
        --caselist) fail "there is no --caselist any more: the caselists the weekly run follows are the build's setting caselist.sync_caselists, in the environment's profile (ADR-0020 (5)), and this script asks the build for them before it installs. Nothing was installed. A new season's caselists are a profile change and a new build (docs/runbooks/caselist-scheduled-sync.md)" ;;
        --env) [ $# -ge 2 ] || fail "--env needs a value"; DEBATE_ENVIRONMENT="$2"; ENVIRONMENT_GIVEN=1; shift 2 ;;
        --confirm-env-change) CONFIRM_ENV_CHANGE=1; shift ;;
        --aws-profile) fail "there is no --aws-profile any more: it wrote AWS_PROFILE into the plist, which nothing the agent runs reads. The run's AWS profile is the build's setting storage.s3.aws_profile, and this script checks that profile before it installs (docs/runbooks/caselist-scheduled-sync.md)" ;;
        --weekday) [ $# -ge 2 ] || fail "--weekday needs a value"; WEEKDAY="$2"; WEEKDAY_GIVEN=1; shift 2 ;;
        --hour) [ $# -ge 2 ] || fail "--hour needs a value"; HOUR="$2"; HOUR_GIVEN=1; shift 2 ;;
        --minute) [ $# -ge 2 ] || fail "--minute needs a value"; MINUTE="$2"; MINUTE_GIVEN=1; shift 2 ;;
        --label) [ $# -ge 2 ] || fail "--label needs a value"; LABEL="$2"; shift 2 ;;
        --log-dir) [ $# -ge 2 ] || fail "--log-dir needs a path"; LOG_DIRECTORY="$2"; LOG_DIRECTORY_GIVEN=1; shift 2 ;;
        --wrapper-dir) [ $# -ge 2 ] || fail "--wrapper-dir needs a path"; WRAPPER_DIRECTORY="$2"; WRAPPER_DIRECTORY_GIVEN=1; shift 2 ;;
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
    # The check runs the installed agent as its plist stands, so every option but the label of the
    # agent to check would be ignored. This lists what the check takes, not what it refuses, so an
    # option added to the loop above is refused here until the check uses it. Until v1-e34-t27 the
    # guard listed four, and --weekday, --hour, --minute, --log-dir, --wrapper-dir and
    # --debate-research were taken and ignored.
    for option in ${OPTIONS_GIVEN}; do
        case "${option}" in
            --check-launchd|--label) ;;
            *) fail "--check-launchd takes no option but --label, and would ignore ${option}: it checks the installed agent as its plist stands. Nothing was checked. Run it without ${option}; a reinstall is what changes the agent" ;;
        esac
    done
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

    # The installed plist, less its schedule and its arguments: same wrapper, same environment, same
    # working directory, and a log of its own. An agent installed since v1-e40-t06 passes its wrapper
    # no argument, and its pull follows the build's caselist.sync_caselists, which the check's
    # `doctor --search-index` reads as well. An agent installed before then names its caselists as
    # `--caselist <slug>` after the wrapper; those go into the check's environment as that setting
    # (JSON, as every list setting takes in the environment), so that the check still sees the
    # stores that agent's run will index while the wrapper's `--check` takes no argument (v1-e34-t30).
    cp "${INSTALLED}" "${CHECK_PLIST}"
    plutil -replace Label -string "${CHECK_LABEL}" "${CHECK_PLIST}"
    AGENT_CASELISTS_JSON=""
    previous_argument=""
    while argument=$(plutil -extract ProgramArguments.1 raw -o - "${CHECK_PLIST}" 2>/dev/null); do
        if [ "${previous_argument}" = "--caselist" ]; then
            AGENT_CASELISTS_JSON="${AGENT_CASELISTS_JSON:+${AGENT_CASELISTS_JSON},}\"${argument}\""
            previous_argument=""
        else
            previous_argument=${argument}
        fi
        plutil -remove ProgramArguments.1 "${CHECK_PLIST}"
    done
    plutil -insert ProgramArguments.1 -string --check "${CHECK_PLIST}"
    if [ -n "${AGENT_CASELISTS_JSON}" ]; then
        plutil -replace EnvironmentVariables.DEBATE_CASELIST__SYNC_CASELISTS -string "[${AGENT_CASELISTS_JSON}]" "${CHECK_PLIST}"
    fi
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
    # 2 is the command refusing an option it does not know. A build from before the profile check
    # or the search index check answers `doctor --evidence-profiles --search-index` that way, and
    # that is not a verdict on any profile or store.
    if [ "${EXIT_CODE}" = "2" ]; then
        echo "install.sh: exit code 2 means the installed build does not have the profile check or the search index check (doctor --evidence-profiles --search-index); install a newer build with scripts/install_channel.sh, then run this again" >&2
    fi
    [ "${EXIT_CODE}" = "0" ] || exit 1
    exit 0
fi

# --- Installing ---------------------------------------------------------------------------------

[ -f "${TEMPLATE}" ] || fail "the plist template is missing at ${TEMPLATE}"
AGENT_DIRECTORY="${HOME}/Library/LaunchAgents"
DESTINATION="${AGENT_DIRECTORY}/${LABEL}.plist"

# The schedule's options are checked as given, before an installed agent is compared with them.
for given in "${WEEKDAY_GIVEN}:${WEEKDAY}" "${HOUR_GIVEN}:${HOUR}" "${MINUTE_GIVEN}:${MINUTE}"; do
    case "${given}" in
        1:|1:*[!0-9]*) fail "--weekday, --hour and --minute take whole numbers; got '${given#1:}'" ;;
    esac
done
if [ "${WEEKDAY_GIVEN}" -eq 1 ]; then
    WEEKDAY=$(without_leading_zeros "${WEEKDAY}")
    [ "${WEEKDAY}" -ge 1 ] && [ "${WEEKDAY}" -le 7 ] || fail "--weekday is 1 (Monday) to 7 (Sunday)"
fi
if [ "${HOUR_GIVEN}" -eq 1 ]; then
    HOUR=$(without_leading_zeros "${HOUR}")
    [ "${HOUR}" -le 23 ] || fail "--hour is 0 to 23"
fi
if [ "${MINUTE_GIVEN}" -eq 1 ]; then
    MINUTE=$(without_leading_zeros "${MINUTE}")
    [ "${MINUTE}" -le 59 ] || fail "--minute is 0 to 59"
fi
[ "${LOG_DIRECTORY_GIVEN}" -eq 0 ] || LOG_DIRECTORY=$(without_trailing_slashes "${LOG_DIRECTORY}")
[ "${WRAPPER_DIRECTORY_GIVEN}" -eq 0 ] || WRAPPER_DIRECTORY=$(without_trailing_slashes "${WRAPPER_DIRECTORY}")
LOG_DIRECTORY_ADVICE=""
WRAPPER_DIRECTORY_ADVICE=""

# --- Over an installed agent, what it runs with is kept unless an option says otherwise ----------
#
# A reinstall is for a new build, a new wrapper or a new schedule. At the reinstall of 2026-10-14
# the agent was a dev agent and --env defaulted to prod, so the runbook's example would have
# switched it to prod's data directory and bucket (v1-e34-t24). The installed plist is read first,
# and its environment, schedule, log directory and wrapper directory are the defaults: an agent
# installed for Thursday stays on Thursday through a reinstall for a new build (v1-e34-t25). Its
# arguments are not: since v1-e40-t06 this script writes none (see the top of this file).

# The variables this script writes. Any other in an installed plist was put there by hand, and a
# reinstall writes the plist afresh without it.
WRITTEN_VARIABLES="DEBATE_ENV HOME DEBATE_RESEARCH_BIN PATH"
INSTALLED_ENVIRONMENT=""
INSTALLED_ARGUMENTS=""
INSTALLED_CASELISTS=""
DROPPED_VARIABLES=""
if [ -f "${DESTINATION}" ]; then
    command -v plutil >/dev/null 2>&1 \
        || fail "an agent is installed at ${DESTINATION}, and reading its environment and arguments needs macOS's plutil; nothing was installed"
    if ! INSTALLED_ENVIRONMENT=$(plutil -extract EnvironmentVariables.DEBATE_ENV raw -o - "${DESTINATION}" 2>/dev/null); then
        [ "${ENVIRONMENT_GIVEN}" -eq 1 ] && [ "${CONFIRM_ENV_CHANGE}" -eq 1 ] \
            || fail "the agent installed at ${DESTINATION} names no DEBATE_ENV, so which environment it runs as is unknown; nothing was installed. Give --env and --confirm-env-change to say which it is to run as"
        INSTALLED_ENVIRONMENT=""
    fi

    # Its arguments after the wrapper. This script writes none since v1-e40-t06; an agent installed
    # before then has `--caselist <slug>` pairs, kept here only to say what a reinstall drops.
    position=1
    previous_argument=""
    while argument=$(plutil -extract "ProgramArguments.${position}" raw -o - "${DESTINATION}" 2>/dev/null); do
        INSTALLED_ARGUMENTS="${INSTALLED_ARGUMENTS} ${argument}"
        [ "${previous_argument}" != "--caselist" ] || INSTALLED_CASELISTS="${INSTALLED_CASELISTS} ${argument}"
        previous_argument=${argument}
        position=$((position + 1))
    done

    # `raw` lists a dictionary's keys, one to a line.
    for variable in $(plutil -extract EnvironmentVariables raw -o - "${DESTINATION}" 2>/dev/null); do
        case " ${WRITTEN_VARIABLES} " in
            *" ${variable} "*) continue ;;
        esac
        case "${variable}" in
            ''|[0-9]*|*[!A-Za-z0-9_]*) fail "the agent installed at ${DESTINATION} sets '${variable}', which is not a variable name; nothing was installed" ;;
        esac
        DROPPED_VARIABLES="${DROPPED_VARIABLES} ${variable}"
    done

    # The schedule, the log directory and the wrapper directory, read whether or not an option
    # gives them, so that a change can be said; a setting no option gives must read back
    # (v1-e34-t25). Before v1-e34-t25 they went back to their defaults on every reinstall.
    if ! INSTALLED_WEEKDAY=$(installed_calendar_integer Weekday 1 7); then
        [ "${WEEKDAY_GIVEN}" -eq 1 ] || cannot_keep StartCalendarInterval.Weekday "${INSTALLED_WEEKDAY}" "its schedule" --weekday
        INSTALLED_WEEKDAY=""
    fi
    if ! INSTALLED_HOUR=$(installed_calendar_integer Hour 0 23); then
        [ "${HOUR_GIVEN}" -eq 1 ] || cannot_keep StartCalendarInterval.Hour "${INSTALLED_HOUR}" "its schedule" --hour
        INSTALLED_HOUR=""
    fi
    if ! INSTALLED_MINUTE=$(installed_calendar_integer Minute 0 59); then
        [ "${MINUTE_GIVEN}" -eq 1 ] || cannot_keep StartCalendarInterval.Minute "${INSTALLED_MINUTE}" "its schedule" --minute
        INSTALLED_MINUTE=""
    fi
    if ! INSTALLED_LOG_DIRECTORY=$(installed_log_directory); then
        [ "${LOG_DIRECTORY_GIVEN}" -eq 1 ] \
            || cannot_keep "log directory in its StandardOutPath and StandardErrorPath" "${INSTALLED_LOG_DIRECTORY}" "its log directory" --log-dir
        INSTALLED_LOG_DIRECTORY=""
    fi
    if ! INSTALLED_WRAPPER_DIRECTORY=$(installed_wrapper_directory); then
        [ "${WRAPPER_DIRECTORY_GIVEN}" -eq 1 ] \
            || cannot_keep "wrapper directory in its ProgramArguments.0" "${INSTALLED_WRAPPER_DIRECTORY}" "its wrapper directory" --wrapper-dir
        INSTALLED_WRAPPER_DIRECTORY=""
    fi

    if [ "${ENVIRONMENT_GIVEN}" -eq 0 ]; then
        DEBATE_ENVIRONMENT=${INSTALLED_ENVIRONMENT}
        note "Keeping the installed agent's environment, ${INSTALLED_ENVIRONMENT}, from its plist's DEBATE_ENV (--env changes it)."
    elif [ "${DEBATE_ENVIRONMENT}" != "${INSTALLED_ENVIRONMENT}" ]; then
        [ "${CONFIRM_ENV_CHANGE}" -eq 1 ] \
            || fail "the agent installed at ${DESTINATION} runs as ${INSTALLED_ENVIRONMENT}, and --env ${DEBATE_ENVIRONMENT} would switch it to ${DEBATE_ENVIRONMENT}: another data directory and another evidence bucket. Nothing was installed. Leave --env out to keep ${INSTALLED_ENVIRONMENT}, or add --confirm-env-change if the switch is meant"
        note "Switching the agent from ${INSTALLED_ENVIRONMENT:-an environment its plist does not name} to ${DEBATE_ENVIRONMENT}, as --confirm-env-change says."
    fi

    SCHEDULE_OPTIONS=""
    [ "${WEEKDAY_GIVEN}" -eq 0 ] || SCHEDULE_OPTIONS="${SCHEDULE_OPTIONS}, --weekday"
    [ "${HOUR_GIVEN}" -eq 0 ] || SCHEDULE_OPTIONS="${SCHEDULE_OPTIONS}, --hour"
    [ "${MINUTE_GIVEN}" -eq 0 ] || SCHEDULE_OPTIONS="${SCHEDULE_OPTIONS}, --minute"
    SCHEDULE_OPTIONS=${SCHEDULE_OPTIONS#, }
    [ "${WEEKDAY_GIVEN}" -eq 1 ] || WEEKDAY=${INSTALLED_WEEKDAY}
    [ "${HOUR_GIVEN}" -eq 1 ] || HOUR=${INSTALLED_HOUR}
    [ "${MINUTE_GIVEN}" -eq 1 ] || MINUTE=${INSTALLED_MINUTE}
    if [ -z "${SCHEDULE_OPTIONS}" ]; then
        note "Keeping the installed agent's schedule, $(schedule_of "${WEEKDAY}" "${HOUR}" "${MINUTE}"), from its plist's StartCalendarInterval (--weekday, --hour and --minute change it)."
    elif [ -z "${INSTALLED_WEEKDAY}" ] || [ -z "${INSTALLED_HOUR}" ] || [ -z "${INSTALLED_MINUTE}" ]; then
        note "Setting the installed agent's schedule to $(schedule_of "${WEEKDAY}" "${HOUR}" "${MINUTE}") (${SCHEDULE_OPTIONS}); its plist's StartCalendarInterval does not read back as one this script writes."
    elif [ "${WEEKDAY}:${HOUR}:${MINUTE}" != "${INSTALLED_WEEKDAY}:${INSTALLED_HOUR}:${INSTALLED_MINUTE}" ]; then
        note "Changing the installed agent's schedule from $(schedule_of "${INSTALLED_WEEKDAY}" "${INSTALLED_HOUR}" "${INSTALLED_MINUTE}") to $(schedule_of "${WEEKDAY}" "${HOUR}" "${MINUTE}") (${SCHEDULE_OPTIONS})."
    fi

    if [ "${LOG_DIRECTORY_GIVEN}" -eq 0 ]; then
        LOG_DIRECTORY=${INSTALLED_LOG_DIRECTORY}
        LOG_DIRECTORY_ADVICE="it is the installed agent's log directory, and --log-dir moves it"
        note "Keeping the installed agent's log directory, ${LOG_DIRECTORY}, from its plist's StandardOutPath and StandardErrorPath (--log-dir changes it)."
    elif [ -z "${INSTALLED_LOG_DIRECTORY}" ]; then
        note "Setting the installed agent's log directory to ${LOG_DIRECTORY} (--log-dir); its plist's StandardOutPath and StandardErrorPath do not read back as one this script writes."
    elif [ "${LOG_DIRECTORY}" != "${INSTALLED_LOG_DIRECTORY}" ]; then
        note "Moving the installed agent's logs from ${INSTALLED_LOG_DIRECTORY} to ${LOG_DIRECTORY} (--log-dir)."
    fi

    if [ "${WRAPPER_DIRECTORY_GIVEN}" -eq 0 ]; then
        WRAPPER_DIRECTORY=${INSTALLED_WRAPPER_DIRECTORY}
        WRAPPER_DIRECTORY_ADVICE="it is the installed agent's wrapper directory, and --wrapper-dir moves it"
        note "Keeping the installed agent's wrapper directory, ${WRAPPER_DIRECTORY}, from its plist's ProgramArguments (--wrapper-dir changes it)."
    elif [ -z "${INSTALLED_WRAPPER_DIRECTORY}" ]; then
        note "Setting the installed agent's wrapper directory to ${WRAPPER_DIRECTORY} (--wrapper-dir); its plist's ProgramArguments.0 does not read back as one this script writes."
    elif [ "${WRAPPER_DIRECTORY}" != "${INSTALLED_WRAPPER_DIRECTORY}" ]; then
        note "Moving the installed agent's wrapper from ${INSTALLED_WRAPPER_DIRECTORY} to ${WRAPPER_DIRECTORY} (--wrapper-dir); the copy in ${INSTALLED_WRAPPER_DIRECTORY} is left where it is."
    fi

    for variable in ${DROPPED_VARIABLES}; do
        if [ "${variable}" = "AWS_PROFILE" ]; then
            note "Not carried over from the installed plist: AWS_PROFILE. Nothing the agent runs reads it; the run's AWS profile is the build's storage.s3.aws_profile, which is checked below."
        else
            note "Not carried over from the installed plist: ${variable}, which this script does not write."
        fi
    done
fi

[ -n "${DEBATE_ENVIRONMENT}" ] || DEBATE_ENVIRONMENT="prod"
# The defaults, for a first install: over an installed agent each was kept or given above.
[ -n "${WEEKDAY}" ] || WEEKDAY=3
[ -n "${HOUR}" ] || HOUR=6
[ -n "${MINUTE}" ] || MINUTE=0
[ "${LOG_DIRECTORY_GIVEN}" -eq 1 ] || [ -n "${LOG_DIRECTORY}" ] || LOG_DIRECTORY="${HOME}/Library/Logs/debate-research"
[ "${WRAPPER_DIRECTORY_GIVEN}" -eq 1 ] || [ -n "${WRAPPER_DIRECTORY}" ] \
    || WRAPPER_DIRECTORY="${HOME}/.local/share/debate-research/launchd"

case "${DEBATE_ENVIRONMENT}" in
    dev|prod) ;;
    *) fail "--env is dev or prod, not '${DEBATE_ENVIRONMENT}' (docs/process/branching-and-environments.md)" ;;
esac

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
refuse_unsafe_path "wrapper destination" "${WRAPPER_DIRECTORY}" "${WRAPPER_DIRECTORY_ADVICE}"
refuse_unsafe_path "log directory" "${LOG_DIRECTORY}" "${LOG_DIRECTORY_ADVICE}"
WRAPPER="${WRAPPER_DIRECTORY}/${WRAPPER_NAME}"

# Where the agent will keep its data, and which caselists its pull follows, come from the profile
# bundled into the installed build, so the build is asked: with the agent's HOME and PATH, from HOME,
# with the variables given and nothing of this shell's. `config show` only reads.
settings_as_run_with() {
    (cd -- "${HOME}" && env -i HOME="${HOME}" PATH="${AGENT_PATH}" "$@" \
        "${DEBATE_RESEARCH_PATH}" --json config show)
}

# The `settings` object of what `config show` printed: not `sources`, which names the same keys with
# the file each came from. It holds no braces, so a value that ever did would make the readers below
# find nothing and refuse, rather than read the wrong thing.
settings_object_of() {
    printf '%s\n' "$1" | sed -n 's/.*"settings": *{\([^{}]*\)}.*/\1/p'
}

# storage.data_dir, or nothing when the build does not say.
data_directory_in() {
    settings_object_of "$1" | sed -n 's/.*"storage\.data_dir": *"\([^"\\]*\)".*/\1/p' | head -n 1
}

# caselist.sync_caselists, a JSON list of slugs, as words each with a space before it; nothing when
# the build names none.
caselists_in() {
    for slug in $(settings_object_of "$1" \
        | sed -n 's/.*"caselist\.sync_caselists": *\[\([^]]*\)\].*/\1/p' | head -n 1 | tr ',"' '  '); do
        printf ' %s' "${slug}"
    done
}

REPORTED_SETTINGS=$(settings_as_run_with DEBATE_ENV="${DEBATE_ENVIRONMENT}") \
    || fail "${DEBATE_RESEARCH_PATH} --json config show failed, so the agent's data directory is unknown; nothing was installed"
DATA_DIRECTORY=$(data_directory_in "${REPORTED_SETTINGS}")
[ -n "${DATA_DIRECTORY}" ] \
    || fail "${DEBATE_RESEARCH_PATH} --json config show did not report storage.data_dir, so the agent's data directory is unknown; nothing was installed"
refuse_unsafe_path "data directory" "${DATA_DIRECTORY}"

# The caselists the agent's pull will follow (ADR-0020 (5)). A build whose profile names none would
# have the agent refused every week (NO_CASELISTS_CONFIGURED), so it is not installed.
BUILD_CASELISTS=$(caselists_in "${REPORTED_SETTINGS}")
[ -n "${BUILD_CASELISTS}" ] \
    || fail "${DEBATE_RESEARCH_PATH} names no caselist for ${DEBATE_ENVIRONMENT}: its caselist.sync_caselists is empty, so the agent's weekly pull would follow none and be refused. Nothing was installed. The caselists are the build's setting (ADR-0020 (5)): install a build whose ${DEBATE_ENVIRONMENT} profile names them"

# A variable put in the installed plist by hand is not carried over, and that must not move the
# agent's data unannounced: the build is asked again with the installed plist's whole environment,
# and the two answers compared. A switch of environment has been confirmed already.
if [ -n "${DROPPED_VARIABLES}" ] && [ "${CONFIRM_ENV_CHANGE}" -eq 0 ]; then
    set --
    for variable in ${DROPPED_VARIABLES}; do
        set -- "$@" "${variable}=$(plutil -extract "EnvironmentVariables.${variable}" raw -o - "${DESTINATION}")"
    done
    INSTALLED_SETTINGS=$(settings_as_run_with DEBATE_ENV="${INSTALLED_ENVIRONMENT}" "$@") \
        || fail "${DEBATE_RESEARCH_PATH} --json config show failed with the installed agent's environment, so whether this install moves its data is unknown; nothing was installed"
    INSTALLED_DATA_DIRECTORY=$(data_directory_in "${INSTALLED_SETTINGS}")
    [ "${INSTALLED_DATA_DIRECTORY}" = "${DATA_DIRECTORY}" ] \
        || fail "this install would move the agent's data from ${INSTALLED_DATA_DIRECTORY} to ${DATA_DIRECTORY}, because it does not carry over${DROPPED_VARIABLES} from the installed plist. Nothing was installed. Add --confirm-env-change if the move is meant"
fi

# The build's own checks and the agent's evidence profile, as the agent will run them (v1-e34-t24):
# `doctor --evidence-profiles` with the environment the plist gives the agent and nothing of this
# shell's, so the AWS config it reads is the one launchd's HOME leads to. The runbook's reinstall
# makes the same check by hand. It exits 1 for a configured profile the AWS config does not define,
# which the scheduled run would be refused for, and for the build's own failed checks, and not for
# an expired session; 2 is a build from before the check. It asks AWS one question for each
# profile that is defined, and waits at most 10 seconds for each answer
# (IDENTITY_TIME_LIMIT_SECONDS in debate_core.integrations.s3.caller_identity, v1-e29-t09). Run
# here, with no DEBATE_REMOVAL_PROFILE, it asks about the everyday profile alone, so an AWS that
# does not answer holds the install up by at most 10 seconds on top of doctor's local checks: the
# profile's row then says AWS did not answer, the check exits 0, and the install goes on. It names
# a profile, its setting and a permission set, never an account or where the AWS config is.
PROFILE_CHECK_STATUS=0
PROFILE_CHECK_OUTPUT=$(cd -- "${HOME}" && env -i HOME="${HOME}" PATH="${AGENT_PATH}" \
    DEBATE_ENV="${DEBATE_ENVIRONMENT}" "${DEBATE_RESEARCH_PATH}" doctor --evidence-profiles 2>&1) \
    || PROFILE_CHECK_STATUS=$?
case "${PROFILE_CHECK_STATUS}" in
    0)
        note "The build's checks and its evidence profile pass as the agent will run them (debate-research doctor --evidence-profiles)."
        ;;
    2)
        fail "the build ${DEBATE_RESEARCH_PATH} does not have the profile check (doctor --evidence-profiles), so whether this machine's AWS config defines the agent's profile is unknown; nothing was installed. Install a newer build with scripts/install_channel.sh, then run this again"
        ;;
    *)
        printf '%s\n' "${PROFILE_CHECK_OUTPUT}" >&2
        fail "the build's checks failed as the agent will run them (debate-research doctor --evidence-profiles, exit ${PROFILE_CHECK_STATUS}); nothing was installed. A profile this machine's AWS config does not define is named above, with the setting that holds it; docs/runbooks/caselist-scheduled-sync.md, under \"A profile the AWS config does not define\", says what to correct"
        ;;
esac

# Said once every check has passed, so that a refusal writes nothing to stdout.
note "The agent's pull follows the build's caselist.sync_caselists:${BUILD_CASELISTS}."
if [ -n "${INSTALLED_ARGUMENTS}" ]; then
    note "Not carried over from the installed plist: the arguments${INSTALLED_ARGUMENTS} after the wrapper. The agent's pull takes none: its caselists are the build's (ADR-0020 (5))."
    if [ -n "${INSTALLED_CASELISTS}" ] && [ "${INSTALLED_CASELISTS}" != "${BUILD_CASELISTS}" ]; then
        note "The installed agent followed${INSTALLED_CASELISTS}; the build names${BUILD_CASELISTS}."
    fi
fi

# `awk` rather than `sed`, because several of the values are paths that may contain a `/`; awk's
# index/substr replacement treats every value as a literal.
render() {
    awk \
        -v label="${LABEL}" \
        -v wrapper="${WRAPPER}" \
        -v weekday="${WEEKDAY}" \
        -v hour="${HOUR}" \
        -v minute="${MINUTE}" \
        -v debate_env="${DEBATE_ENVIRONMENT}" \
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
            line = fill(line, "@LABEL@", label)
            line = fill(line, "@WRAPPER@", wrapper)
            line = fill(line, "@WEEKDAY@", weekday)
            line = fill(line, "@HOUR@", hour)
            line = fill(line, "@MINUTE@", minute)
            line = fill(line, "@DEBATE_ENV@", debate_env)
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

# A reinstall over a loaded agent needs a reload and a check, never a pull: the validation pull is
# for a first install, and suggesting it again would spend the day's downloads for nothing.
if command -v launchctl >/dev/null 2>&1 && launchctl print "gui/$(id -u)/${LABEL}" >/dev/null 2>&1; then
    echo "${LABEL} is already loaded, and launchd keeps the plist it loaded. Reload it, then check"
    echo "that launchd can run the new wrapper (no sync, no download):"
    echo
    echo "  launchctl bootout gui/\$UID/${LABEL}"
    echo "  launchctl bootstrap gui/\$UID ${DESTINATION}"
    echo "  launchctl print gui/\$UID/${LABEL}"
    echo "  $0 --check-launchd"
else
    echo "Nothing is scheduled yet. Validate the pipeline first, then enable the agent:"
    echo
    echo "  DEBATE_ENV=dev debate-research caselist pull --dry-run"
    echo "  DEBATE_ENV=dev debate-research caselist pull"
    echo "  launchctl bootstrap gui/\$UID ${DESTINATION}"
    echo "  launchctl print gui/\$UID/${LABEL}"
    echo "  $0 --check-launchd"
fi
echo
echo "docs/runbooks/caselist-scheduled-sync.md has the whole procedure, including how to disable it."
