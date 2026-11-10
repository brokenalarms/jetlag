#!/usr/bin/env python3
"""
verify-card labels each backup location Local or Network, and that label decides
which hash checkbox covers it: "Verify hashes" reads local copies, "Include network
locations (slow)" adds the rest. The label is worked out on every run from the mount
table, because the same folder can be a USB drive one day and an SMB share the next.

A wrong "local" would quietly read a whole share over the network, so anything that
cannot say where its data lives counts as network. These tests feed the classifier
mount tables as macOS's `mount` and Linux's /proc/self/mounts print them.
"""

import plistlib

from lib.volumes import (
    is_network, mount_of, parse_disk_images, parse_macos_mounts, parse_proc_mounts, share_host,
)

MACOS_MOUNT = """\
/dev/disk3s1s1 on / (apfs, sealed, local, read-only, journaled)
/dev/disk3s5 on /System/Volumes/Data (apfs, local, journaled, nobrowse, protect)
/dev/disk5s1 on /Volumes/T9 (exfat, local, nodev, nosuid, noowners, noatime, mounted by me)
//me@nas.invalid/Backup on /Volumes/Backup (smbfs, nodev, nosuid, mounted by me)
//me@127.0.0.1/Media on /Volumes/Media (smbfs, nodev, nosuid, mounted by me)
macfuse@macfuse0 on /Volumes/Cloud (macfuse, nodev, nosuid, synchronous, mounted by me)
/dev/disk6s1 on /Volumes/Odd (exfat, nodev, nosuid, mounted by me)
"""


def test_macos_mount_lines_give_type_and_local_flag():
    mounts = {m.point: m for m in parse_macos_mounts(MACOS_MOUNT)}

    assert (mounts["/Volumes/T9"].fstype, mounts["/Volumes/T9"].local_flag) == ("exfat", True)
    assert (mounts["/Volumes/Backup"].fstype, mounts["/Volumes/Backup"].local_flag) == ("smbfs", False)
    assert mounts["/Volumes/Backup"].source == "//me@nas.invalid/Backup"


def test_classification():
    mounts = parse_macos_mounts(MACOS_MOUNT)
    labels = {root: is_network(root, mounts) for root in (
        "/Volumes/T9/Videos", "/Volumes/Backup/Mirror", "/Volumes/Media/Videos",
        "/Volumes/Cloud/Videos", "/Volumes/Odd/Videos", "/Users/me/Movies",
    )}

    assert labels == {
        "/Volumes/T9/Videos": False,        # a local exfat drive
        "/Volumes/Backup/Mirror": True,     # a share from another machine
        "/Volumes/Media/Videos": False,     # a share this machine serves itself over loopback
        "/Volumes/Cloud/Videos": True,      # FUSE cannot say where its data lives
        "/Volumes/Odd/Videos": True,        # a local type the mount does not flag local
        "/Users/me/Movies": False,          # the boot volume
    }


def test_host_path_root_is_network_by_its_syntax():
    assert is_network("nas-rsync:/volume1/Backup", mounts=[])


def test_longest_mount_point_wins():
    mounts = parse_macos_mounts(MACOS_MOUNT)

    assert mount_of("/System/Volumes/Data/Users", mounts).point == "/System/Volumes/Data"


def test_proc_mounts_unescape_spaces():
    mounts = parse_proc_mounts("/dev/sdb1 /media/me/My\\040Drive exfat rw,relatime 0 0\n")

    assert (mounts[0].point, mounts[0].fstype) == ("/media/me/My Drive", "exfat")
    assert not is_network("/media/me/My Drive/Videos", mounts)


def test_share_host_from_smb_and_nfs_sources():
    assert share_host("//me@nas.local/Backup") == "nas.local"
    assert share_host("nas.local:/volume1/Backup") == "nas.local"


def test_disk_image_devices_map_to_their_backing_file():
    plist = plistlib.dumps({"images": [{
        "image-path": "/Volumes/Backup/library.sparsebundle",
        "system-entities": [{"dev-entry": "/dev/disk7"}, {"dev-entry": "/dev/disk7s1"}],
    }]})

    assert parse_disk_images(plist) == {
        "/dev/disk7": "/Volumes/Backup/library.sparsebundle",
        "/dev/disk7s1": "/Volumes/Backup/library.sparsebundle",
    }
