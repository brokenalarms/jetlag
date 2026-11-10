"""Command lines: one module per <command>.sh, holding argument parsing and output.

The logic each command runs lives in lib/; lib/launch.sh runs these modules with
scripts/ on PYTHONPATH, so they import `cli.*` and `lib.*` from anywhere.
"""
