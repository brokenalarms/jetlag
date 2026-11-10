"""
Check that every file on a card is on each backup location, before the card is wiped.

Each location is a mirror of the imported library: a local folder, or host:/path
reached over ssh. A card file's copy is looked for anywhere under the root, by its card
name or by the card name recorded in the copy's provenance
(XMP-xmpMM:PreservedFileName), since an import can rename a file. A copy passes when
its total size equals the card file's (an untouched copy) or its data portion does (a
copy jetlag has written); nothing is passed on a guess. See docs/specs/verify-card.md.

The check is read-only. A local location is walked; a remote one is listed by its host
with `rsync --list-only --recursive` and never read over the network: a remote copy is
judged from its listed size, or from a local location's copy at the same relative path
with the same size and mtime.
"""

from __future__ import annotations

import bisect
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Optional

from lib.data_portion import data_bytes
from lib.exiftool import exiftool

SCHEMA_PATH = Path(__file__).parent / "verify-card-schema.yaml"

# A sync tool's archive of deleted items: a copy in one is on its way out, not
# backed up.
SYNC_ARCHIVE_DIRS = {"#recycle", "@eaDir", ".stversions"}

# How much larger than the card file a copy may be and still be considered as a
# renamed copy of it: room for the metadata a write adds. Only narrows which copies
# have their provenance read; the verdict compares sizes exactly.
METADATA_GROWTH_LIMIT = 16 * 1024 * 1024

_REMOTE_ROOT = re.compile(r"^(?P<host>[^/:]+):(?P<path>.+)$")
_RSYNC_LINE = re.compile(
    r"^(?P<mode>\S{10})\s+(?P<size>[\d,.]+)\s+(?P<date>\d{4}/\d{2}/\d{2})\s+"
    r"(?P<time>\d{2}:\d{2}:\d{2})\s(?P<path>.+)$"
)


def is_hidden(parts) -> bool:
    return any(part.startswith(".") for part in parts)


def normalize_extensions(extensions: list[str]) -> set[str]:
    return {(e if e.startswith(".") else f".{e}").lower() for e in extensions}


@dataclass
class CardFile:
    rel: str
    path: Path
    kind: str
    size: int
    data_bytes: Optional[int]

    @property
    def name(self) -> str:
        return self.path.name


@dataclass
class Scan:
    checked: list[CardFile] = field(default_factory=list)
    not_checked: int = 0
    not_checked_kinds: set[str] = field(default_factory=set)


def scan_source(source: Path, media: set[str], companions: set[str], include_companions: bool,
                ignored: set[str]) -> Scan:
    """Sort every file under the source into checked and not checked."""
    scan = Scan()
    for dirpath, dirnames, filenames in os.walk(source):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        rel_dir = Path(dirpath).relative_to(source)
        ignored_dir = next((p for p in rel_dir.parts if p.lower() in ignored), None)
        for filename in sorted(filenames):
            if filename.startswith("."):
                continue
            path = Path(dirpath) / filename
            suffix = path.suffix.lower()
            if ignored_dir is not None:
                scan.not_checked += 1
                scan.not_checked_kinds.add(f"{ignored_dir}/")
                continue
            if suffix in media:
                kind = "media"
            elif suffix in companions and include_companions:
                kind = "companion"
            else:
                scan.not_checked += 1
                scan.not_checked_kinds.add(suffix or filename)
                continue
            scan.checked.append(CardFile(
                rel=str(rel_dir / filename), path=path, kind=kind,
                size=path.stat().st_size,
                data_bytes=data_bytes(path) if kind == "media" else None,
            ))
    return scan


@dataclass
class Entry:
    """A file on a backup location, relative to its root."""
    rel: str
    size: int
    mtime: int
    local_path: Optional[Path] = None

    @property
    def name(self) -> str:
        return PurePosixPath(self.rel).name

    @property
    def stem(self) -> str:
        return PurePosixPath(self.rel).stem

    @property
    def parent(self) -> str:
        return str(PurePosixPath(self.rel).parent)


@dataclass
class Location:
    name: str
    root: str
    remote: bool
    entries: list[Entry] = field(default_factory=list)
    reachable: bool = True


def _listable(rel: PurePosixPath, extensions: set[str]) -> bool:
    parts = rel.parts
    return (rel.suffix.lower() in extensions
            and not is_hidden(parts)
            and not any(part in SYNC_ARCHIVE_DIRS for part in parts))


def list_local(root: Path, extensions: set[str]) -> list[Entry]:
    entries = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SYNC_ARCHIVE_DIRS and not d.startswith(".")]
        for filename in filenames:
            path = Path(dirpath) / filename
            rel = PurePosixPath(path.relative_to(root).as_posix())
            if not _listable(rel, extensions):
                continue
            stat = path.stat()
            entries.append(Entry(rel=str(rel), size=stat.st_size, mtime=int(stat.st_mtime),
                                 local_path=path))
    return entries


def parse_rsync_listing(listing: str, extensions: set[str]) -> list[Entry]:
    entries = []
    for line in listing.splitlines():
        match = _RSYNC_LINE.match(line)
        if not match or not match["mode"].startswith("-"):
            continue
        rel = PurePosixPath(match["path"])
        if not _listable(rel, extensions):
            continue
        mtime = time.mktime(time.strptime(f"{match['date']} {match['time']}", "%Y/%m/%d %H:%M:%S"))
        entries.append(Entry(rel=str(rel), size=int(re.sub(r"[,.]", "", match["size"])),
                             mtime=int(mtime)))
    return entries


def list_remote(root: str, extensions: set[str]) -> Optional[list[Entry]]:
    rsync = os.environ.get("JETLAG_RSYNC", "rsync")
    result = subprocess.run([rsync, "--list-only", "--recursive", root.rstrip("/") + "/"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ Could not list {root}: {result.stderr.strip()}", file=sys.stderr)
        return None
    return parse_rsync_listing(result.stdout, extensions)


def open_location(name: str, root: str, extensions: set[str]) -> Location:
    if _REMOTE_ROOT.match(root) and not Path(root).exists():
        entries = list_remote(root, extensions)
        return Location(name, root, remote=True, entries=entries or [], reachable=entries is not None)
    path = Path(root)
    if not path.is_dir():
        print(f"❌ Backup location {name} is not reachable: {root}", file=sys.stderr)
        return Location(name, root, remote=False, reachable=False)
    return Location(name, root, remote=False, entries=list_local(path, extensions))


@dataclass
class CopyFacts:
    """What is known of a copy: the card name it records, and its data portion size."""
    recorded_name: Optional[str]
    data_bytes: Optional[int]
    known: bool


def recorded_names(paths: list[Path]) -> dict[Path, Optional[str]]:
    """The card name each file records in its provenance, in one exiftool call."""
    if not paths:
        return {}
    raw = exiftool.execute("-j", "-XMP-xmpMM:PreservedFileName", "-XMP-xmpDM:LogComment",
                           *[str(p) for p in paths])
    names: dict[Path, Optional[str]] = {p: None for p in paths}
    for record in json.loads(raw or "[]"):
        path = Path(record["SourceFile"])
        name = record.get("PreservedFileName")
        if not name and record.get("LogComment"):
            # Files imported before the jetlag namespace carry their record as JSON.
            try:
                name = json.loads(record["LogComment"]).get("filename")
            except (ValueError, AttributeError):
                name = None
        names[path] = str(name) if name else None
    return names


class Matcher:
    """Finds a card file's copies on one location."""

    def __init__(self, location: Location, card: list[CardFile], local_twins: dict[str, Entry]):
        self.location = location
        self.local_twins = local_twins
        self.by_name: dict[str, list[Entry]] = {}
        self.by_stem: dict[tuple[str, str], list[Entry]] = {}
        by_suffix: dict[str, list[Entry]] = {}
        for entry in location.entries:
            self.by_name.setdefault(entry.name, []).append(entry)
            self.by_stem.setdefault((entry.parent, entry.stem), []).append(entry)
            by_suffix.setdefault(PurePosixPath(entry.rel).suffix.lower(), []).append(entry)
        self.by_suffix = {s: sorted(es, key=lambda e: e.size) for s, es in by_suffix.items()}
        self.sizes = {s: [e.size for e in es] for s, es in self.by_suffix.items()}
        self.facts: dict[str, CopyFacts] = {}
        self._learn(card)

    def candidates(self, card_file: CardFile) -> list[Entry]:
        found = {id(e): e for e in self.by_name.get(card_file.name, [])}
        if card_file.kind == "media" and card_file.data_bytes is not None:
            suffix = card_file.path.suffix.lower()
            entries, sizes = self.by_suffix.get(suffix, []), self.sizes.get(suffix, [])
            low = bisect.bisect_left(sizes, card_file.data_bytes)
            high = bisect.bisect_right(sizes, card_file.size + METADATA_GROWTH_LIMIT)
            for entry in entries[low:high]:
                found.setdefault(id(entry), entry)
        return list(found.values())

    def _learn(self, card: list[CardFile]) -> None:
        """Read what can be known of every candidate copy, locally and in one batch."""
        wanted = {e.rel: e for c in card for e in self.candidates(c)}
        local: dict[str, Path] = {}
        for rel, entry in wanted.items():
            if entry.local_path is not None:
                local[rel] = entry.local_path
            else:
                twin = self.local_twins.get(rel)
                if (twin and twin.local_path is not None
                        and twin.size == entry.size and twin.mtime == entry.mtime):
                    local[rel] = twin.local_path
                else:
                    self.facts[rel] = CopyFacts(None, None, known=False)
        names = recorded_names(list(local.values()))
        for rel, path in local.items():
            self.facts[rel] = CopyFacts(names.get(path), data_bytes(path), known=True)

    def copies(self, card_file: CardFile) -> list[Entry]:
        """Copies of a media file: its recorded card name, or else its own name, matches."""
        matched = []
        for entry in self.candidates(card_file):
            recorded = self.facts[entry.rel].recorded_name
            if recorded == card_file.name or (recorded is None and entry.name == card_file.name):
                matched.append(entry)
        return matched


def judge(card_file: CardFile, copies: list[Entry], facts: dict[str, CopyFacts]) -> tuple[str, Optional[str]]:
    """The verdict for one card file on one location, and what it was decided on."""
    if not copies:
        return "missing", None
    if len(copies) > 1:
        return "duplicate", None
    copy = copies[0]
    if copy.size == card_file.size:
        return "matched", "size"
    if card_file.kind == "companion":
        return "size_differs", None
    copy_facts = facts.get(copy.rel)
    if card_file.data_bytes is None or copy_facts is None or not copy_facts.known:
        return "unverifiable", None
    if copy_facts.data_bytes == card_file.data_bytes:
        return "matched", "data"
    return "data_differs", None


def companion_copies(card_file: CardFile, media_copies: dict[tuple[str, str], list[Entry]],
                     matcher: Matcher) -> list[Entry]:
    """A companion is found by its name, or beside its media file's copy under that copy's
    stem: an import renames a clip's companions with it, and they carry no record."""
    found = {e.rel: e for e in matcher.by_name.get(card_file.name, [])}
    parent, stem = str(Path(card_file.rel).parent), card_file.path.stem
    suffix = card_file.path.suffix.lower()
    for media_copy in media_copies.get((parent, stem), []):
        for candidate in matcher.by_stem.get((media_copy.parent, media_copy.stem), []):
            if PurePosixPath(candidate.rel).suffix.lower() == suffix:
                found.setdefault(candidate.rel, candidate)
    return list(found.values())


@dataclass
class Verdict:
    verdict: str
    basis: Optional[str]
    copies: list[str]


@dataclass
class Report:
    locations: list[Location]
    scan: Scan
    verdicts: dict[str, dict[str, Verdict]]

    @property
    def on_every_location(self) -> int:
        return sum(all(v.verdict == "matched" for v in by_location.values())
                   for by_location in self.verdicts.values())


def verify_card(source: Path, locations: list[tuple[str, str]], media_extensions: list[str],
                companion_extensions: list[str], include_companions: bool,
                ignore_paths: list[str]) -> Report:
    """Judge every checked card file on every location."""
    media = normalize_extensions(media_extensions)
    companions = normalize_extensions(companion_extensions) - media
    scan = scan_source(source, media, companions, include_companions,
                       {p.strip("/").lower() for p in ignore_paths})

    extensions = media | (companions if include_companions else set())
    opened = [open_location(name, root, extensions) for name, root in locations]

    local_twins: dict[str, Entry] = {}
    for location in opened:
        if not location.remote and location.reachable:
            for entry in location.entries:
                local_twins.setdefault(entry.rel, entry)
    matchers = {loc.name: Matcher(loc, scan.checked, local_twins)
                for loc in opened if loc.reachable}

    media_copies: dict[str, dict[tuple[str, str], list[Entry]]] = {n: {} for n in matchers}
    verdicts: dict[str, dict[str, Verdict]] = {c.rel: {} for c in scan.checked}
    # Media first: a companion is also looked for beside its clip's copy.
    ordered = [c for c in scan.checked if c.kind == "media"] + \
              [c for c in scan.checked if c.kind == "companion"]
    for card_file in ordered:
        for location in opened:
            if not location.reachable:
                verdicts[card_file.rel][location.name] = Verdict("unreachable", None, [])
                continue
            matcher = matchers[location.name]
            if card_file.kind == "media":
                copies = matcher.copies(card_file)
                key = (str(Path(card_file.rel).parent), card_file.path.stem)
                media_copies[location.name][key] = copies
            else:
                copies = companion_copies(card_file, media_copies[location.name], matcher)
            verdict, basis = judge(card_file, copies, matcher.facts)
            verdicts[card_file.rel][location.name] = Verdict(verdict, basis, sorted(c.rel for c in copies))
    return Report(opened, scan, verdicts)
