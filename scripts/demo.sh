#!/usr/bin/env sh
# Drives the screen recording described in docs/VIDEO_SCRIPT.md.
#
#   make demo
#
# Every beat of the video, in order, one keypress apart. The pause is the point:
# each command here finishes in well under a second, so recording by typing
# them live means the output appears and scrolls before you have said anything
# about it. This waits for you instead, and clears the screen first, so each
# result arrives at the top of a clean frame and stays there.
#
# The commands are the real ones. Nothing is staged, pre-rendered or replayed
# from a file -- this script runs `make` targets a reviewer can run themselves.
#
#   DEMO_PAUSE=0 make demo    dry run, no pauses, for checking the sequence
#
set -eu

cd "$(dirname "$0")/.."

PAUSE=${DEMO_PAUSE:-1}

beat() {
    if [ "$PAUSE" = "1" ]; then
        printf '\n\033[2m  [%s] press return\033[0m' "$1"
        read -r _ < /dev/tty || true
        clear
    fi
    echo
    echo "=============================================================="
    echo "  $1"
    echo "=============================================================="
    echo
}

if [ "$PAUSE" = "1" ]; then
    clear
    cat <<'BANNER'

    LedgerGate -- demo

    Seven beats, one keypress apart. Follow docs/VIDEO_SCRIPT.md for the
    narration; this just puts the right output on screen at the right time.

      1  the baseline, and what it costs
      2  one full agent execution, start to finish
      3  arithmetic as a tool call
      4  the human approval checkpoint
      5  the gate across the range of proposer quality
      6  every decision the gate changed, against ground truth
      7  the offline verification gate  (optional -- see note at beat 7)

    Beats 1-3 print about 50 lines each. Size the window so they land in one
    frame; if the top scrolls away you will be narrating something the viewer
    cannot see.

BANNER
fi

beat "1/7  the simple baseline"
make eval-baseline

beat "2/7  one full execution: the advanced solution on a single receipt"
make trace-sample

beat "3/7  arithmetic is a tool call, and it lands in the trajectory"
PYTHONPATH=src ${PYTHON:-python3} scripts/show_trace.py \
    traces/guarded.holdout.jsonl HLD-PAY0004

beat "4/7  the human checkpoint: the system cannot release its own queue"
make approve

beat "5/7  the finding: the gate across the full range of proposer quality"
make headline

beat "6/7  every decision the gate changed, checked against ground truth"
make gate-audit

# Not one of the video's beats. docs/VIDEO_SCRIPT.md is timed at 4:58 against a
# 5:00 limit and has no room for a 170-line test run. Kept here because it is
# the right last thing to show anyone watching in person, and because a take
# that ends on a green banner is a good take.
beat "7/7  the whole thing, offline, from nothing  (optional; not in the 4:58 cut)"
make verify

if [ "$PAUSE" = "1" ]; then
    cat <<'BANNER'

    End of demo.

    Still to say on camera, from docs/VIDEO_SCRIPT.md: the changelog and the
    change that contributed most (entry 8), the one experiment removed
    (entry 9), the main failure mode, and the hot take.

BANNER
fi
