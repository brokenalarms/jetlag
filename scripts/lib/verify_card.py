"""
Check that every file on a card is on each backup location, before the card is wiped.

Each location is a mirror of the imported library: a local folder, or host:/path
reached over ssh. A card file's copy is looked for anywhere under the root, by its card
name or by the card name recorded in the copy's provenance
(XMP-xmpMM:PreservedFileName), since an import can rename a file. A copy passes when
its total size equals the card file's (an untouched copy) or its data portion does (a
copy jetlag has written); nothing is passed on a guess. See docs/specs/completed/verify-card.md.

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
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Optional

from lib.data_portion import data_bytes, data_ranges, data_ranges_of, data_sha256, is_still
from lib.exiftool import exiftool
from lib.volumes import is_network

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
    # With --verify-hashes: two copies recorded different hashes for this file.
    recorded_hashes_disagree: bool = False
    # For a media file not on every location, what helps the user judge it: for a
    # recording, its length and whether it opens (no duration means a broken
    # recording), and whether a clip numbered next to it was backed up.
    duration_seconds: Optional[float] = None
    opens: Optional[bool] = None
    neighbours_backed_up: Optional[bool] = None

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
    # Reading it crosses a network: a host:/path root, a share, or an unknown mount.
    network: bool = True


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
    host, path = _remote_parts(root)
    # The host's shell splits the path on spaces. The Mac's built-in rsync (openrsync)
    # sends the path as written, and rsync 3.x protects it itself unless told to send
    # it as written too, so quoting it once for that shell lists it under either.
    result = subprocess.run([rsync, "--list-only", "--recursive", f"{host}:{shlex.quote(path + '/')}"],
                            capture_output=True, text=True, env={**os.environ, "RSYNC_OLD_ARGS": "1"})
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
    return Location(name, root, remote=False, entries=list_local(path, extensions),
                    network=is_network(root))


@dataclass
class CopyFacts:
    """What is known of a copy: the card name and hash cache it records, and its data
    portion size. read_path is a local file with the copy's bytes: the copy itself, or
    for a remote copy its local twin."""
    recorded_name: Optional[str]
    data_bytes: Optional[int]
    known: bool
    recorded_hash: Optional[str] = None
    recorded_bytes: Optional[int] = None
    read_path: Optional[Path] = None


@dataclass
class Recorded:
    name: Optional[str] = None
    content_sha256: Optional[str] = None
    content_bytes: Optional[int] = None


def recorded_facts(paths: list[Path]) -> dict[Path, Recorded]:
    """The card name and hash cache each file records, in one exiftool call."""
    if not paths:
        return {}
    raw = exiftool.execute("-j", "-XMP-xmpMM:PreservedFileName", "-XMP-xmpDM:LogComment",
                           "-XMP-jetlag:ContentSHA256", "-XMP-jetlag:ContentBytes",
                           *[str(p) for p in paths])
    facts: dict[Path, Recorded] = {p: Recorded() for p in paths}
    for record in json.loads(raw or "[]"):
        path = Path(record["SourceFile"])
        name = record.get("PreservedFileName")
        if not name and record.get("LogComment"):
            # Files imported before the jetlag namespace carry their record as JSON.
            try:
                name = json.loads(record["LogComment"]).get("filename")
            except (ValueError, AttributeError):
                name = None
        content_bytes = record.get("ContentBytes")
        facts[path] = Recorded(
            name=str(name) if name else None,
            content_sha256=str(record["ContentSHA256"]) if record.get("ContentSHA256") else None,
            content_bytes=int(content_bytes) if str(content_bytes or "").isdigit() else None,
        )
    return facts


class Matcher:
    """Finds a card file's copies on one location."""

    def __init__(self, location: Location, card: list[CardFile], local_twins: dict[str, Entry]):
        self.location = location
        self.local_twins = local_twins
        self.by_name: dict[str, list[Entry]] = {}
        self.by_rel: dict[str, Entry] = {e.rel: e for e in location.entries}
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
        recorded = recorded_facts(list(local.values()))
        for rel, path in local.items():
            facts = recorded.get(path, Recorded())
            self.facts[rel] = CopyFacts(facts.name, data_bytes(path), known=True,
                                        recorded_hash=facts.content_sha256,
                                        recorded_bytes=facts.content_bytes, read_path=path)

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
    # With --verify-hashes, for a matched copy in scope: match, mismatch or not_hashable.
    hash: Optional[str] = None


@dataclass
class Report:
    locations: list[Location]
    scan: Scan
    verdicts: dict[str, dict[str, Verdict]]
    hashes_checked: int = 0
    hash_cache_written: int = 0

    @property
    def on_every_location(self) -> int:
        return sum(all(v.verdict == "matched" for v in by_location.values())
                   for by_location in self.verdicts.values())


def verify_card(source: Path, locations: list[tuple[str, str]], media_extensions: list[str],
                companion_extensions: list[str], include_companions: bool,
                ignore_paths: list[str], verify_hashes: bool = False,
                include_network: bool = False) -> Report:
    """Judge every checked card file on every location.

    verify_hashes also hashes every matched media copy on a local location (and with
    include_network, on a network one) and compares it with the card file's hash.
    """
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
    report = Report(opened, scan, verdicts)
    if verify_hashes:
        check_hashes(report, matchers, include_network)
    describe_unmatched(report)
    return report


_CLIP_NUMBER = re.compile(r"^(?P<prefix>.*?)(?P<number>\d+)$")


def _clip_number(path: Path) -> Optional[tuple[str, str, int, int]]:
    """(folder, prefix, number, digits) of a clip name ending in a number:
    GX010123 → GX01 / 0123, VID_20250619_042028_00_004 → …_00_ / 004."""
    match = _CLIP_NUMBER.match(path.stem)
    if not match:
        return None
    return str(path.parent), match["prefix"], int(match["number"]), len(match["number"])


def probe_duration(path: Path) -> Optional[float]:
    """The clip's length from ffprobe; None when ffprobe finds none or is missing."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def _have_ffprobe() -> bool:
    try:
        subprocess.run(["ffprobe", "-version"], capture_output=True, timeout=10)
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False


def describe_unmatched(report: Report) -> None:
    """Gather, for each media file not on every location, whether a clip numbered
    next to it is on every location and, for a recording, its length and whether it
    opens."""
    unmatched = [c for c in report.scan.checked if c.kind == "media" and not all(
        v.verdict == "matched" for v in report.verdicts[c.rel].values())]
    if not unmatched:
        return
    by_number: dict[tuple[str, str, int, int], CardFile] = {}
    for card_file in report.scan.checked:
        key = _clip_number(Path(card_file.rel))
        if card_file.kind == "media" and key:
            by_number[key] = card_file
    can_probe = _have_ffprobe()
    for card_file in unmatched:
        if can_probe and not is_still(card_file.path):
            card_file.duration_seconds = probe_duration(card_file.path)
            card_file.opens = card_file.duration_seconds is not None
        key = _clip_number(Path(card_file.rel))
        if key:
            folder, prefix, number, digits = key
            neighbours = [by_number.get((folder, prefix, n, digits)) for n in (number - 1, number + 1)]
            present = [n for n in neighbours if n is not None]
            if present:
                card_file.neighbours_backed_up = any(
                    all(v.verdict == "matched" for v in report.verdicts[n.rel].values()) for n in present)


def cleared_files(report: Report, source: Path) -> set[Path]:
    """The card files matched on every location: the only ones safe to delete."""
    return {(source / rel).resolve() for rel, by_location in report.verdicts.items()
            if by_location and all(v.verdict == "matched" for v in by_location.values())}


def parse_location(spec: str) -> tuple[str, str]:
    """A NAME=ROOT command-line value as (name, root); ValueError when malformed."""
    name, sep, root = spec.partition("=")
    if not sep or not name or not root:
        raise ValueError(f"expected NAME=ROOT, got {spec!r}")
    return name, root


def _remote_parts(root: str) -> tuple[str, str]:
    match = _REMOTE_ROOT.match(root)
    assert match is not None
    return match["host"], match["path"].rstrip("/")


def _ssh(host: str, script: str) -> subprocess.CompletedProcess:
    ssh = os.environ.get("JETLAG_SSH", "ssh")
    return subprocess.run([ssh, host, script], capture_output=True)


class RemoteFile:
    """A file on another host, read in small aligned blocks with dd over ssh: enough
    to find a data portion from its headers without copying the file."""

    BLOCK = 64 * 1024

    def __init__(self, host: str, path: str):
        self.host, self.path, self.position = host, path, 0
        self.blocks: dict[int, bytes] = {}

    def seek(self, position: int, whence: int = 0) -> int:
        self.position = position
        return position

    def tell(self) -> int:
        return self.position

    def read(self, size: int) -> bytes:
        first, last = self.position // self.BLOCK, (self.position + size - 1) // self.BLOCK
        missing = [b for b in range(first, last + 1) if b not in self.blocks]
        if missing:
            start, count = missing[0], missing[-1] - missing[0] + 1
            result = _ssh(self.host, f"dd if={shlex.quote(self.path)} bs={self.BLOCK} "
                                     f"skip={start} count={count} 2>/dev/null")
            data = result.stdout
            for i in range(count):
                self.blocks[start + i] = data[i * self.BLOCK:(i + 1) * self.BLOCK]
        data = b"".join(self.blocks.get(b, b"") for b in range(first, last + 1))
        offset = self.position - first * self.BLOCK
        chunk = data[offset:offset + size]
        self.position += len(chunk)
        return chunk


def remote_sha256(location: Location, entry: Entry, twin: Optional[Path]) -> Optional[str]:
    """sha256 of a host:/path copy's data portion, computed on its host so only the
    digest crosses the network. The ranges come from a local twin's headers, or from
    the copy's own headers read on the host."""
    host, root = _remote_parts(location.root)
    path = f"{root}/{entry.rel}"
    ranges = data_ranges(twin) if twin else data_ranges_of(RemoteFile(host, path), entry.size)
    if ranges is None:
        return None
    quoted = shlex.quote(path)
    parts = "; ".join(f"tail -c +{offset + 1} {quoted} | head -c {length}" for offset, length in ranges)
    script = (f"{{ {parts}; }} | {{ if command -v sha256sum >/dev/null; then sha256sum; "
              f"else shasum -a 256; fi; }}")
    result = _ssh(host, script)
    digest = result.stdout.decode(errors="replace").split()
    return digest[0] if result.returncode == 0 and digest and len(digest[0]) == 64 else None


def check_hashes(report: Report, matchers: dict[str, Matcher], include_network: bool) -> None:
    """Hash every matched media copy in scope against its card file's data portion.

    The reference is the hash a matched copy records (written only after it matched
    the card), else the card's own data hashed. A copy that hashes equal to a
    reference read from the card, on a local location, and records none, gets the
    hash written into it as a cache, so a later run need not read the card again.
    """
    locations = {loc.name: loc for loc in report.locations}
    # Written only once every copy is hashed: a write moves a local copy's metadata,
    # and a remote twin's ranges are read from that local copy.
    cache_writes: list[tuple[Path, str, Optional[int]]] = []
    in_scope = {name for name, loc in locations.items()
                if loc.reachable and (include_network or not loc.network)}
    for card_file in report.scan.checked:
        if card_file.kind != "media":
            continue
        by_location = report.verdicts[card_file.rel]
        targets = []
        for name, verdict in by_location.items():
            if name in in_scope and verdict.verdict == "matched":
                entry = matchers[name].by_rel[verdict.copies[0]]
                targets.append((name, verdict, entry, matchers[name].facts.get(entry.rel)))
        if not targets:
            continue
        recorded = {f.recorded_hash for _, _, _, f in targets
                    if f and f.recorded_hash and f.recorded_bytes == card_file.data_bytes}
        reference = next(iter(recorded)) if len(recorded) == 1 else None
        from_card = reference is None
        # The card settles which recorded hash is right; nothing is cached for it.
        card_file.recorded_hashes_disagree = len(recorded) > 1
        if from_card:
            reference = data_sha256(card_file.path)
        for name, verdict, entry, facts in targets:
            location = locations[name]
            if reference is None:
                verdict.hash = "not_hashable"
                continue
            report.hashes_checked += 1
            if location.remote:
                twin = facts.read_path if facts and facts.read_path else None
                digest = remote_sha256(location, entry, twin)
            else:
                digest = data_sha256(entry.local_path) if entry.local_path else None
            if digest == reference:
                verdict.hash = "match"
                if (from_card and not card_file.recorded_hashes_disagree
                        and not location.network and entry.local_path
                        and not (facts and facts.recorded_hash)):
                    cache_writes.append((entry.local_path, reference, card_file.data_bytes))
            else:
                verdict.hash = "mismatch"
                verdict.verdict = "hash_mismatch"
                verdict.basis = None
    for path, digest, content_bytes in cache_writes:
        write_hash_cache(path, digest, content_bytes)
        report.hash_cache_written += 1


def write_hash_cache(path: Path, digest: str, content_bytes: Optional[int]) -> None:
    """Record a copy's data hash in its provenance, once. Metadata only: the data
    portion, and so the hash, is unchanged by the write."""
    tags = [f"-XMP-jetlag:ContentSHA256={digest}"]
    if content_bytes is not None:
        tags.append(f"-XMP-jetlag:ContentBytes={content_bytes}")
    exiftool.write_tags(str(path), tags)
