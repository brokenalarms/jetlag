"""The logic behind every command, shared by the command lines and the pipeline."""

from pathlib import Path

# What the code reads at run time rather than imports: filename date patterns,
# the country/timezone tables and exiftool's composite-tag config.
DATA_DIR = Path(__file__).parent / "data"
