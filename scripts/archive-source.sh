#!/bin/bash
# archive-source.sh — Archive (move and rename) or delete a source folder once its media is processed.
# Run with --help for its options; README.md describes every command.
source "$(dirname "${BASH_SOURCE[0]}")/lib/launch.sh" archive_source "$@"
