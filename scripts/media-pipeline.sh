#!/bin/bash
# media-pipeline.sh — Copy a card's media, fix timestamps, tag it and file it by date: the whole workflow in one run.
# Run with --help for its options; README.md describes every command.
source "$(dirname "${BASH_SOURCE[0]}")/lib/launch.sh" media_pipeline "$@"
