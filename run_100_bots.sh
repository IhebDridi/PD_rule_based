#!/usr/bin/env bash
# Run 100 bots automatically (no browser, no clicking).
# Uses the session config "prisoners_dilemma_100" and runs 100 participants.
echo "Running 100 bots (command-line test)..."
otree test prisoners_dilemma_100 100
