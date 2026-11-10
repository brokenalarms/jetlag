"""Whether a folder is on a local disk or across a network.

Decided on every run, never stored: the same root can be a USB drive one day and an
SMB mount the next. See docs/specs/verify-card.md, "Local or network".

- A host:/path root is remote by its syntax.
- Any other root is local only if its volume's filesystem type is on an allowlist, the
  mount is flagged local, and it is not a disk image whose backing file is itself on a
  network volume.
- smbfs, afpfs, nfs, cifs and webdav mounts are network mounts, unless the server
  they mount from is this machine (a share served to itself over loopback).
- FUSE and unrecognised types cannot say where their data lives, so they count as
  network. A misread only ever moves a location from "Verify hashes" to "Include
  network locations"; it never changes the default verdict.

The mount table comes from `mount` on macOS and /proc/self/mounts on Linux.
"""

from __future__ import annotations

import ipaddress
import os
import plistlib
import re
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

LOCAL_TYPES = {"apfs", "hfs", "exfat", "msdos", "ntfs", "ext4", "xfs", "btrfs"}
SHARE_TYPES = {"smbfs", "afpfs", "nfs", "nfs4", "cifs", "smb3", "webdav"}

REMOTE_ROOT = re.compile(r"^(?P<host>[^/:]+):(?P<path>.+)$")

# `mount` on macOS: "<device> on <mount point> (<type>, <flag>, <flag>...)"
_MACOS_MOUNT_LINE = re.compile(r"^(?P<source>.+?) on (?P<point>/.*?) \((?P<options>[^()]*)\)$")


@dataclass(frozen=True)
class Mount:
    source: str
    point: str
    fstype: str
    local_flag: bool


def is_remote_root(root: str) -> bool:
    """A host:/path root, reached over ssh, rather than a folder on this machine."""
    return bool(REMOTE_ROOT.match(root)) and not Path(root).exists()


def parse_macos_mounts(output: str) -> list[Mount]:
    mounts = []
    for line in output.splitlines():
        match = _MACOS_MOUNT_LINE.match(line.strip())
        if not match:
            continue
        options = [o.strip() for o in match["options"].split(",")]
        mounts.append(Mount(match["source"], match["point"], options[0], "local" in options[1:]))
    return mounts


def _unescape_proc(field: str) -> str:
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), field)


def parse_proc_mounts(text: str) -> list[Mount]:
    """/proc/self/mounts. Linux has no local flag; the type allowlist decides."""
    mounts = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 3:
            mounts.append(Mount(_unescape_proc(parts[0]), _unescape_proc(parts[1]), parts[2], True))
    return mounts


def mount_table() -> list[Mount]:
    if sys.platform == "darwin":
        result = subprocess.run(["mount"], capture_output=True, text=True)
        return parse_macos_mounts(result.stdout)
    try:
        return parse_proc_mounts(Path("/proc/self/mounts").read_text())
    except OSError:
        return []


def mount_of(path: str, mounts: list[Mount]) -> Optional[Mount]:
    """The mount a path is on: the one with the longest mount point above it."""
    real = os.path.realpath(path)
    best = None
    for mount in mounts:
        point = mount.point.rstrip("/") or "/"
        if real == point or real.startswith(point.rstrip("/") + "/") or point == "/":
            if best is None or len(point) > len(best.point.rstrip("/") or "/"):
                best = mount
    return best


def share_host(source: str) -> Optional[str]:
    """The server a network share is mounted from: //user@host/Share, host:/export."""
    match = re.match(r"^//(?:[^@/]*@)?(?P<host>[^/:]+)", source) or re.match(r"^(?P<host>[^/:]+):/", source)
    return match["host"] if match else None


def is_this_machine(host: str) -> bool:
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except OSError:
        return False
    if any(ipaddress.ip_address(str(a).split("%")[0]).is_loopback for a in addresses):
        return True
    try:
        own = {info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None)}
    except OSError:
        own = set()
    return bool(addresses & own)


def parse_disk_images(plist: bytes) -> dict[str, str]:
    """`hdiutil info -plist`: each attached image's /dev/diskN mapped to its file."""
    try:
        info = plistlib.loads(plist)
    except Exception:
        return {}
    devices = {}
    for image in info.get("images", []):
        for entity in image.get("system-entities", []):
            if "dev-entry" in entity and "image-path" in image:
                devices[entity["dev-entry"]] = image["image-path"]
    return devices


def _disk_image_file(source: str) -> Optional[str]:
    if sys.platform != "darwin" or not source.startswith("/dev/disk"):
        return None
    result = subprocess.run(["hdiutil", "info", "-plist"], capture_output=True)
    devices = parse_disk_images(result.stdout)
    whole_disk = re.sub(r"s\d+$", "", source)
    return devices.get(source) or devices.get(whole_disk)


def is_network(root: str, mounts: Optional[list[Mount]] = None, _depth: int = 0) -> bool:
    """Whether reading root crosses a network. Unknown counts as network."""
    if is_remote_root(root):
        return True
    mounts = mount_table() if mounts is None else mounts
    mount = mount_of(root, mounts)
    if mount is None:
        return True
    fstype = mount.fstype.lower()
    if fstype in SHARE_TYPES:
        host = share_host(mount.source)
        return not (host and is_this_machine(host))
    if fstype not in LOCAL_TYPES or not mount.local_flag:
        return True
    backing = _disk_image_file(mount.source)
    if backing and _depth < 3:
        return is_network(backing, mounts, _depth + 1)
    return False
