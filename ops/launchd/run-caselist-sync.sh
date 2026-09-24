#!/bin/sh
# The launchd agent's entry point: set the environment, then exec `debate-research caselist pull`.
#
# There is no pipeline logic here and there must never be any. What to download, what to import,
# what the day's five bulk downloads are spent on, what an expired AWS session means — all of it
# belongs to debate_core.application.caselist_sync, so that the schedule and an operator typing the
# command by hand run exactly the same code (the task spec forbids logic in this file).
#
# Every argument is passed straight through, which is how the agent names its caselists:
#
#     ops/launchd/run-caselist-sync.sh --caselist hsld26 --caselist hspolicy26
#
# Environment, all optional, all templated into the plist by install.sh:
#
#   DEBATE_ENV            dev or prod. Defaults to prod, because the schedule is the prod job;
#                         the dev validation run is one an operator types.
#   AWS_PROFILE           The SSO profile for that environment's evidence bucket. If its session
#                         has expired the run still captures and imports, and records the publish
#                         as pending for the next run or `caselist pull --publish-pending`.
#   DEBATE_RESEARCH_BIN   The console script, when it is not on PATH under its own name.
set -eu

: "${DEBATE_ENV:=prod}"
: "${DEBATE_RESEARCH_BIN:=debate-research}"
export DEBATE_ENV
if [ -n "${AWS_PROFILE:-}" ]; then
    export AWS_PROFILE
fi

if ! command -v "${DEBATE_RESEARCH_BIN}" >/dev/null 2>&1; then
    echo "run-caselist-sync: ${DEBATE_RESEARCH_BIN} is not on PATH." >&2
    echo "run-caselist-sync: set DEBATE_RESEARCH_BIN in the agent's plist to its full path," >&2
    echo "run-caselist-sync: or reinstall with ops/launchd/install.sh so PATH is written again." >&2
    exit 127
fi

# --json so that stdout is one object per run, which is what the plist's StandardOutPath collects
# and what v1-e34-t03's run log will read. The exit code is the command's, unchanged: 0 for a run
# that captured what there was (including one that found nothing new, and one whose publish is
# pending), 1 for a download, import or publish that did not complete.
exec "${DEBATE_RESEARCH_BIN}" --json caselist pull "$@"
