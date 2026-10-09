#!/bin/sh
# The launchd agent's entry point: set the environment, then exec `debate-research caselist pull`.
#
# There is no pipeline logic here and there must never be any. What to download, what to import,
# what the day's five bulk downloads are spent on, what an expired AWS session means — all of it
# belongs to debate_core.application.caselist_sync, so that the schedule and an operator typing the
# command by hand run exactly the same code (the task spec forbids logic in this file).
#
# The agent does not run this file. ops/launchd/install.sh copies it to
# ~/.local/share/debate-research/launchd/ and the plist names the copy, because a launchd agent
# may not open anything under ~/Documents, where checkouts live, and because a checkout's copy
# changes with whatever branch is checked out (v1-e34-t10). Editing this file changes the agent
# only when the installer is run again.
#
# Every argument is passed straight through, which is how the agent names its caselists:
#
#     run-caselist-sync.sh --caselist hsld26 --caselist hspolicy26
#
# The one exception is `--check`, alone: it shows which console script DEBATE_RESEARCH_BIN
# resolves to and runs its `--version`, and nothing else. `install.sh --check-launchd` runs it
# under launchd to prove the agent can be executed, without a sync and without a download.
#
# Environment, all optional, all templated into the plist by install.sh:
#
#   DEBATE_ENV            dev or prod. Defaults to prod, because the schedule is the prod job;
#                         the dev validation run is one an operator types.
#   AWS_PROFILE           The SSO profile for that environment's evidence bucket. If its session
#                         has expired the run still captures and imports, and records the publish
#                         as pending for the next run or `caselist pull --publish-pending`.
#   DEBATE_RESEARCH_BIN   The console script, by its full path. The installer always writes it, so
#                         nothing earlier on PATH can stand in for the installed build.
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
    echo "run-caselist-sync: or reinstall with ops/launchd/install.sh, which writes it." >&2
    exit 127
fi

if [ "${1:-}" = "--check" ]; then
    if [ $# -ne 1 ]; then
        echo "run-caselist-sync: --check takes no other arguments." >&2
        exit 2
    fi
    echo "run-caselist-sync: check: DEBATE_RESEARCH_BIN is $(command -v "${DEBATE_RESEARCH_BIN}")"
    exec "${DEBATE_RESEARCH_BIN}" --version
fi

# --json so that stdout is one object per run, which is what the plist's StandardOutPath collects
# and what v1-e34-t03's run log will read. The exit code is the command's, unchanged, and this file
# never reads it: 0 for a run that captured what there was (including one that found nothing new,
# and one whose publish is pending), 1 for a download, import or publish that did not complete, 3
# when the bucket did not answer before any stage could record the failure (v1-e01-t20), 70 for a
# bug. launchd only records it as the agent's last exit code: the plist has no KeepAlive, so no
# exit code, 3 included, makes launchd run the agent again before next week's slot.
exec "${DEBATE_RESEARCH_BIN}" --json caselist pull "$@"
