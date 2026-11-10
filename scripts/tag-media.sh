#!/bin/bash
# tag-media.sh — Add Finder tags and camera make/model to media files.
# Run with --help for its options; README.md describes every command.
source "$(dirname "${BASH_SOURCE[0]}")/lib/launch.sh" tag-media.py "$@"
