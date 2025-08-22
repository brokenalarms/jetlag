#!/bin/bash
set -x

rsync -avz --delete --no-perms --no-owner --no-group --no-links --omit-dir-times --progress --stats --exclude-from="${HOME}/.exclusions.txt" /Volumes/Extreme\ GRN/ dadmin@192.168.1.11:/volume1/Backup/ChronoSync/Extreme\ GRN/
