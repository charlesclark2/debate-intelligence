#!/bin/sh
# Render the weekly caselist-sync launchd agent for this machine, and put it where launchd reads it.
#
# It does not start anything. Installing the file and enabling the schedule are two steps on
# purpose: the first scheduled prod run happens only after one manual `DEBATE_ENV=dev
# debate-research caselist pull` has validated the pipeline
# (docs/runbooks/caselist-scheduled-sync.md). This script prints the `launchctl bootstrap` line to
# run next; it never runs it.
#
#   ops/launchd/install.sh --caselist hsld26 --caselist hspolicy26 --dry-run
#   ops/launchd/install.sh --caselist hsld26 --env prod --aws-profile debate-prod-evidence
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
#   --debate-research P  Full path to the console script, when it is not on the PATH this shell
#                        has. Default: whatever `command -v debate-research` finds.
#   --dry-run            Render the plist to stdout and write nothing at all.
#   -h, --help           This text.
set -eu

SCRIPT_DIRECTORY=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
TEMPLATE="${SCRIPT_DIRECTORY}/com.debate-intelligence.caselist-sync.plist.template"
WRAPPER="${SCRIPT_DIRECTORY}/run-caselist-sync.sh"

LABEL="com.debate-intelligence.caselist-sync"
DEBATE_ENVIRONMENT="prod"
AWS_PROFILE_NAME=""
WEEKDAY=3
HOUR=6
MINUTE=0
LOG_DIRECTORY=""
DEBATE_RESEARCH_PATH=""
DRY_RUN=0
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
        --debate-research) [ $# -ge 2 ] || fail "--debate-research needs a path"; DEBATE_RESEARCH_PATH="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) fail "unknown option $1 (--help lists them)" ;;
    esac
done

[ -f "${TEMPLATE}" ] || fail "the plist template is missing at ${TEMPLATE}"
[ -n "${CASELISTS}" ] || fail "at least one --caselist is required; see --help"
[ -n "${LOG_DIRECTORY}" ] || LOG_DIRECTORY="${HOME}/Library/Logs/debate-research"
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

if [ -z "${DEBATE_RESEARCH_PATH}" ]; then
    DEBATE_RESEARCH_PATH=$(command -v debate-research || true)
fi
if [ -z "${DEBATE_RESEARCH_PATH}" ]; then
    echo "install.sh: warning — debate-research is not on this shell's PATH." >&2
    echo "install.sh: the agent will use the PATH written below; check it, or pass" >&2
    echo "install.sh: --debate-research with the full path to the console script." >&2
fi

# `awk` rather than `sed`, because two of the values are paths that may contain a `/` and one is a
# multi-line block; awk's index/substr replacement treats every value as a literal.
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
        -v home_directory="${HOME}" \
        -v path_value="${PATH}" \
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
mkdir -p "${AGENT_DIRECTORY}" "${LOG_DIRECTORY}"
render > "${DESTINATION}.incoming"
if command -v plutil >/dev/null 2>&1; then
    plutil -lint "${DESTINATION}.incoming" >/dev/null || {
        rm -f "${DESTINATION}.incoming"
        fail "the rendered plist did not lint; nothing was installed"
    }
fi
mv "${DESTINATION}.incoming" "${DESTINATION}"
chmod 644 "${DESTINATION}"

echo "Wrote ${DESTINATION}"
echo "Logs will be written to ${LOG_DIRECTORY}"
echo
echo "Nothing is scheduled yet. Validate the pipeline first, then enable the agent:"
echo
echo "  DEBATE_ENV=dev debate-research caselist pull${CASELISTS} --dry-run"
echo "  DEBATE_ENV=dev debate-research caselist pull${CASELISTS}"
echo "  launchctl bootstrap gui/\$UID ${DESTINATION}"
echo "  launchctl print gui/\$UID/${LABEL}"
echo
echo "docs/runbooks/caselist-scheduled-sync.md has the whole procedure, including how to disable it."
