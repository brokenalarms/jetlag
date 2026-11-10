"""What the tests share, importable from any test folder as `helpers.*`.

- media:                  test videos and photos with chosen metadata
- processes:              the exiftool processes a test run left behind
- pipeline:               running media-pipeline as the app does
- pipeline_schema:        checking pipeline events against the schema
- metadata_call_counter:  a stand-in exiftool that logs each call (run, not imported)
"""

from pathlib import Path

# scripts/, the folder every command, lib/ and media-profiles.yaml are found from.
SCRIPT_DIR = Path(__file__).resolve().parents[2]
