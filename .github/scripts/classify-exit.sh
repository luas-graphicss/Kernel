#!/bin/sh
set -u

UNAVAILABLE_STATUS=3

"$@"
status=$?

if [ "$status" -eq 0 ]; then
    exit 0
fi

if [ "$status" -eq "$UNAVAILABLE_STATUS" ]; then
    title="Infrastructure unavailable"
else
    title="Check failed"
fi

echo "::error title=$title::'$*' exited with status $status"
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    echo "- $title: '$*' exited with status $status" >> "$GITHUB_STEP_SUMMARY"
fi
exit "$status"
