#!/bin/bash
# generate-gyroflow.sh — Write a Gyroflow stabilization project for a video with gyro data.
# Run with --help for its options; README.md describes every command.
source "$(dirname "${BASH_SOURCE[0]}")/lib/launch.sh" generate-gyroflow.py "$@"
