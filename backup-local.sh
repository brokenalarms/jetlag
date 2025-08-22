#!/bin/bash
set -x

rsync -avz --delete --dry-run --no-links --omit-dir-times --progress --stats --exclude-from="${HOME}/.exclusions.txt" /Volumes/Extreme\ GRN/ /Volumes/Extreme\ BLK/
