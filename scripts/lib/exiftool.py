"""
Deprecated — use ``from lib.metadata import metadata`` instead.

This module re-exports the MetadataService singleton as ``exiftool`` so that
any remaining or third-party callers continue to work.
"""

import warnings as _warnings

_warnings.warn(
    "lib.exiftool is deprecated — use lib.metadata instead",
    DeprecationWarning,
    stacklevel=2,
)

from lib.metadata import metadata as exiftool  # noqa: F401, E402
