#!/bin/bash
# verify-card.sh — Check that every file on a card is on each backup location before it is wiped.
# Run with --help for its options; README.md describes every command.
source "$(dirname "${BASH_SOURCE[0]}")/lib/launch.sh" verify_card "$@"
