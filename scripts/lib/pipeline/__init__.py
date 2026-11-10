"""
The media pipeline: ingest from source, process, output to target.

Pipeline: INGEST (always) → [tag] → [fix-timestamp] → OUTPUT (always) → [gyroflow] → [archive-source]

Source files are read-only inputs — ingest copies them to a working directory,
all processing happens there, then output moves files to the target. Each step
is a call into its lib module; media-pipeline is the command line.

- options:     RunOptions, the command line resolved against the profile
- preflight:   batch-level checks before the first file (camera, timezones, …)
- consent:     asking before something the user may not want
- stages:      one file's trip, as Stage objects run by one loop
- batch:       run(), the steps of a whole run in order
- working_dir: the staging directory and what a cancel clears
- events:      the JSONL events on stdout
"""

from lib.pipeline.batch import run
from lib.pipeline.consent import require_consent
from lib.pipeline.events import emit_event
from lib.pipeline.options import RunOptions
from lib.pipeline.stages import process_file
from lib.pipeline.working_dir import WORKING_DIR_NAME, WorkingDir, cancel_handler

__all__ = [
    "WORKING_DIR_NAME", "RunOptions", "WorkingDir", "cancel_handler", "emit_event",
    "process_file", "require_consent", "run",
]
