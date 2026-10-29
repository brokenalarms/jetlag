#!/usr/bin/env python3
"""A stand-in for jetlag-metadata that logs every request before answering it.

Selected through JETLAG_METADATA_BINARY. Each request is appended as one JSON line
(op, file) to the file named by METADATA_CALL_LOG, then served by the Python
exiftool backend, so the pipeline behaves exactly as it does with the real one.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.exiftool import ExifTool

log_path = os.environ["METADATA_CALL_LOG"]
exiftool = ExifTool()

for line in sys.stdin:
    request = json.loads(line)
    with open(log_path, "a") as log:
        log.write(json.dumps({"op": request["op"], "file": request["file"]}) + "\n")
    if request["op"] == "read":
        extra_args = (["-fast2"] if request.get("fast") else []) + \
                     (["-a", "-G4"] if request.get("duplicates") else [])
        response = exiftool.read_tags(request["file"], request["tags"], extra_args)
    else:
        tag_args = [f"-{key}={value}" for key, value in request["tags"].items()]
        response = {"updated": exiftool.write_tags(request["file"], tag_args)}
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()

exiftool.close()
