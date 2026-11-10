"""
Every fact jetlag uses about a file's time is derived once, by the hierarchy in
lib/timestamps/: the winning timestamp and its source, the file's zone, the camera's
zone setting, the filename's time and the date folder all come from the FileReading
read_file() builds from the file's one cached exiftool read.

test_metadata_call_contract.py holds the read to one per file. This holds the
derivations the same way: it fails when code outside lib/timestamps/ works any of
them out for itself, which is how the correction, the mixed-zone guard and the date
folder came to disagree about the same Comedy night clips. A copy is recognised by
what it has to touch to exist:

- a regular expression for a date in a filename or a zone on a tag value;
- a file's modification or birth time read as a date;
- a time tag looked up in a metadata dict, outside the correction, whose job is to
  compare those stored values with the ones it plans to write.

A module that needs one of these for something other than a file's own time is
named in ALLOWED with the reason.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from helpers import SCRIPT_DIR

HIERARCHY = SCRIPT_DIR / "lib" / "timestamps"

# The correction compares a file's stored clock fields with the values it plans,
# field by field; that comparison is the "current values" list, not a derivation.
TIME_TAG_READERS = {SCRIPT_DIR / "lib" / "fix_media_timestamp"}

ALLOWED = {
    # rsync's listing of a backup location: dates and mtimes of the listing's
    # entries, compared between copies, never a file's shooting time.
    ("lib/verify_card.py", "date regex"),
    ("lib/verify_card.py", "file time"),
}

# Shapes a date or zone regex cannot avoid: a four- or eight-digit run, or a signed
# two-digit hour.
DATE_OR_ZONE_REGEX = re.compile(
    r"\\d\{[48]\}|\[0-9\]\{[48]\}|\[\+-\]\\d\{2\}|\[\+-\]\[0-9\]\{2\}|\(\[\+-\]\)"
)
FILE_TIME_ATTRIBUTES = {"st_mtime", "st_birthtime", "st_ctime", "getmtime", "getctime",
                        "fromtimestamp"}
TIME_TAGS = {"DateTimeOriginal", "OffsetTimeOriginal", "CreationDate", "CreateDate",
             "MediaCreateDate", "TrackCreateDate", "MovieHeaderCreateDate"}
RE_FUNCTIONS = {"match", "search", "sub", "compile", "fullmatch", "findall", "finditer", "split"}


def _modules():
    for root in (SCRIPT_DIR / "lib", SCRIPT_DIR / "cli"):
        for path in sorted(root.rglob("*.py")):
            if HIERARCHY not in path.parents:
                yield path


def _string_value(node: ast.AST) -> str:
    """The literal text of a string, implicit concatenations included."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _string_value(node.left) + _string_value(node.right)
    return ""


def _copies(path: Path) -> list[tuple[str, int, str]]:
    """(kind, line, detail) for every derivation the module makes for itself."""
    tree = ast.parse(path.read_text(), filename=str(path))
    reads_time_tags = not any(reader in path.parents for reader in TIME_TAG_READERS)
    found = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "re"
                and node.func.attr in RE_FUNCTIONS and node.args):
            pattern = _string_value(node.args[0])
            if DATE_OR_ZONE_REGEX.search(pattern):
                found.append(("date regex", node.lineno, pattern))
        elif isinstance(node, ast.Attribute) and node.attr in FILE_TIME_ATTRIBUTES:
            found.append(("file time", node.lineno, node.attr))
        elif reads_time_tags and isinstance(node, ast.Subscript):
            key = _string_value(node.slice)
            if key in TIME_TAGS:
                found.append(("time tag", node.lineno, key))
        elif (reads_time_tags and isinstance(node, ast.Call)
              and isinstance(node.func, ast.Attribute) and node.func.attr == "get"
              and node.args and _string_value(node.args[0]) in TIME_TAGS):
            found.append(("time tag", node.lineno, _string_value(node.args[0])))
    return found


@pytest.mark.parametrize("path", list(_modules()), ids=lambda p: str(p.relative_to(SCRIPT_DIR)))
def test_no_module_derives_a_files_time_outside_the_hierarchy(path):
    """Actual: the time, zone, filename-time and date derivations a module makes itself
    Expected: none — each comes from read_file() in lib/timestamps/sources.py"""
    rel = str(path.relative_to(SCRIPT_DIR))
    copies = [(kind, line, detail) for kind, line, detail in _copies(path)
              if (rel, kind) not in ALLOWED]
    assert copies == [], (
        f"Actual: {rel} derives a file's time for itself: "
        + "; ".join(f"{kind} at line {line} ({detail})" for kind, line, detail in copies)
        + ". Expected: take it from read_file() / FileReading in lib/timestamps/sources.py")


@pytest.mark.parametrize("source, kind", [
    ("re.match(r'^(?:VID|LRV|IMG)_(\\d{8})_(\\d{6})', base)", "date regex"),
    ("re.search(r'([+-]\\d{2}):?(\\d{2})$', value)", "date regex"),
    ("os.path.getmtime(file_path)", "file time"),
    ("datetime.fromtimestamp(st.st_mtime)", "file time"),
    ("exif.get('DateTimeOriginal', '')", "time tag"),
    ("data['CreationDate']", "time tag"),
])
def test_the_copies_this_replaced_are_recognised(tmp_path, source, kind):
    """The detector is only as good as what it catches: each shape below is one the
    parallel copies took before they were deleted (organize's filename date and
    mtime fallback, extract_metadata_timezone's zone regex, the pipeline's own
    DateTimeOriginal lookup)."""
    module = tmp_path / "copy.py"
    module.write_text(source + "\n")

    assert kind in [found_kind for found_kind, _, _ in _copies(module)]
