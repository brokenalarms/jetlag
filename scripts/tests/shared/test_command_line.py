"""
lib/command_line.py holds what every script's command line shares: the timezone flags and
how they resolve, and the SIGINT/SIGTERM handling. One implementation is what keeps
media-pipeline and fix-media-timestamp accepting the same --timezone values, and
every script shutting exiftool down on Cancel.
"""

import signal
import subprocess
import sys

import pytest

from helpers.media import create_test_video
from lib.command_line import (
    UnknownLocation,
    UnknownTimezone,
    attach_negative_option_values,
    interrupt_handler,
    resolve_timezone,
)
from helpers import SCRIPT_DIR
from lib.exiftool import exiftool



class TestResolveTimezone:
    """Both scripts resolve --timezone and their location flag through this."""

    @pytest.mark.parametrize("value", ["+0800", "+08:00", "-05:00", "-0500", "0800", "Asia/Tokyo"])
    def test_every_accepted_form_passes_through(self, value):
        assert resolve_timezone(value, None) == value

    def test_unknown_zone_name_is_refused(self):
        with pytest.raises(UnknownTimezone):
            resolve_timezone("Pacific/Atlantis", None)

    def test_timezone_wins_over_location(self):
        assert resolve_timezone("+09:00", "TW") == "+09:00"

    def test_location_resolves_by_code_and_by_name(self):
        assert resolve_timezone(None, "TW") == "+08:00"
        assert resolve_timezone(None, "Taiwan") == "+08:00"

    def test_unknown_location_is_refused(self):
        with pytest.raises(UnknownLocation):
            resolve_timezone(None, "Atlantis")

    def test_neither_given_is_none(self):
        assert resolve_timezone(None, None) is None


def test_negative_offsets_are_attached_to_their_flag():
    """argparse before 3.13 reads '-05:00' as a flag; both scripts rewrite it first."""
    argv = ["--timezone", "-05:00", "--time-offset", "-60", "file.mp4"]
    assert attach_negative_option_values(argv) == ["--timezone=-05:00", "--time-offset=-60", "file.mp4"]


class TestInterruptHandler:
    """Every script's Cancel closes exiftool, then cleans up, then exits 128+signal."""

    @pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM], ids=["sigint", "sigterm"])
    def test_closes_exiftool_runs_cleanup_and_exits(self, monkeypatch, sig):
        order = []
        monkeypatch.setattr(exiftool, "close", lambda: order.append("close"))
        handler = interrupt_handler(lambda: order.append("cleanup"))

        with pytest.raises(SystemExit) as exit_info:
            handler(sig, None)

        assert exit_info.value.code == 128 + sig
        assert order == ["close", "cleanup"], \
            f"Actual: {order}, Expected: exiftool closed before cleanup runs"


class TestScriptsAcceptTheSameTimezones:
    """The pipeline used to accept only +HHMM while fix-media-timestamp also took
    +HH:MM; a value one accepted the other refused."""

    def _pipeline(self, tmp_path, timezone):
        source = tmp_path / "source"
        create_test_video(source / "clip.mp4", **{"QuickTime:CreateDate": "2025:06:17 23:25:21"})
        return subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "cli" / "media_pipeline.py"),
             "--source", str(source), "--target", str(tmp_path / "target"),
             "--extensions", ".mp4", "--tasks", "fix-timestamp", "--timezone", timezone],
            capture_output=True, text=True, stdin=subprocess.DEVNULL,
        )

    @pytest.mark.parametrize("timezone, corrected", [
        ("+08:00", "2025:06:18 07:25:21+08:00"),
        ("-05:00", "2025:06:17 18:25:21-05:00"),
    ])
    def test_pipeline_accepts_colon_and_western_offsets(self, tmp_path, timezone, corrected):
        result = self._pipeline(tmp_path, timezone)

        assert result.returncode == 0, result.stderr
        events = [line for line in result.stdout.splitlines() if '"timestamp_result"' in line]
        assert len(events) == 1 and f'"corrected_time": "{corrected}"' in events[0], \
            f"Actual: {events}, Expected: corrected_time {corrected}"

    def test_fix_media_timestamp_refuses_an_unknown_zone_without_a_traceback(self, tmp_path):
        video = tmp_path / "clip.mp4"
        create_test_video(video)

        result = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "cli" / "fix_media_timestamp.py"), str(video),
             "--timezone", "Pacific/Atlantis"],
            capture_output=True, text=True,
        )

        assert result.returncode == 1
        assert "unknown timezone" in result.stderr.lower()
        assert "Traceback" not in result.stderr, result.stderr
