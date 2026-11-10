#!/bin/bash
# scan-source.sh — Report how many media files a source holds, or whether their names carry dates.
# Run with --help for its options; README.md describes every command.
source "$(dirname "${BASH_SOURCE[0]}")/lib/launch.sh" scan_source "$@"
