#!/usr/bin/env python3
"""A stand-in exiftool that logs every -stay_open command before passing it on.

Selected through JETLAG_EXIFTOOL. Runs the real exiftool (REAL_EXIFTOOL) with the
same arguments and relays stdin to it line by line; its stdout goes straight back
to the caller, so the pipeline behaves exactly as it does with the real one. Each
command — the lines up to an -executeN — is appended to METADATA_CALL_LOG as one
JSON line (op, file): a write when it carries -overwrite_original, else a read.
"""

import json
import os
import subprocess
import sys

log_path = os.environ["METADATA_CALL_LOG"]
real = subprocess.Popen([os.environ["REAL_EXIFTOOL"], *sys.argv[1:]], stdin=subprocess.PIPE)

command: list[str] = []
for raw in sys.stdin.buffer:
    real.stdin.write(raw)
    real.stdin.flush()
    line = raw.decode().strip()
    if line.startswith("-execute"):
        op = "write" if "-overwrite_original" in command else "read"
        with open(log_path, "a") as log:
            log.write(json.dumps({"op": op, "file": command[-1]}) + "\n")
        command = []
    else:
        command.append(line)

real.stdin.close()
sys.exit(real.wait())
