#!/bin/bash
set -x
rsync -avz --delete --no-perms --no-owner --no-group --no-links --omit-dir-times --info=name --stats --exclude-from="${HOME}/.exclusions.txt" "/Volumes/Extreme GRN/" "/Volumes/Extreme BLK/" 2>&1 | grep -v "skipping non-regular file"
