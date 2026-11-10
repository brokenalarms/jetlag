#!/bin/bash
# ingest-media.sh — Copy one source file into a working directory, leaving the source untouched.
# Run with --help for its options; README.md describes every command.
source "$(dirname "${BASH_SOURCE[0]}")/lib/launch.sh" ingest-media.py "$@"
