"""
The working directory: where a run stages its copies, and that nothing survives
in it past the file it was staged for.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from lib import media_pipeline, organize_by_date
from helpers.pipeline import SCRIPT_DIR, PipelineResult, create_test_video, run_pipeline


# The pipeline stages every file through a working directory before organize
# places it. These runs exercise the default location, so they cannot go
# through run_pipeline(), which supplies a --working-dir of its own. The spy
# runner imports media-pipeline's module, records where ingest staged each
# file and the inode organize was handed just before it moved it, then runs
# main() exactly as the CLI would.
_PIPELINE_SPY_RUNNER = '''
import json
import os
import sys

import cli.media_pipeline
from lib import ingest_media, organize_by_date

record_path = sys.argv[1]


def record(**entry):
    with open(record_path, "a") as handle:
        handle.write(json.dumps(entry) + "\\n")


real_ingest = ingest_media.ingest_file
real_organize = organize_by_date.process_file


def ingest_spy(source, working_dir, apply, **kwargs):
    dest, action, companions = real_ingest(source, working_dir, apply, **kwargs)
    if dest and os.path.exists(dest):
        record(hook="ingest", dest=dest)
    return dest, action, companions


def organize_spy(file_path, *args, **kwargs):
    before = os.stat(file_path).st_ino if os.path.exists(file_path) else None
    result = real_organize(file_path, *args, **kwargs)
    record(hook="organize", source=file_path, inode=before, dest=result.dest)
    return result


ingest_media.ingest_file = ingest_spy
organize_by_date.process_file = organize_spy
sys.argv = [sys.argv[0]] + sys.argv[2:]
cli.media_pipeline.main()
'''


def _staged_paths(entries: list[dict]) -> list[Path]:
    return [Path(entry["dest"]) for entry in entries if entry["hook"] == "ingest"]


class TestDefaultWorkingDirIsOnTheTargetVolume:
    """With no --working-dir, staging happens on the target's own volume.

    Staging is unavoidable — the source is read-only and organize picks the date
    folder from the timestamp the correction just wrote — but its location is
    not. Staged on the boot volume, every file crosses volumes twice: once for
    ingest's copy and again for organize's move, which degrades to a full copy
    plus delete between filesystems. Under the target, ingest is one same-volume
    copy and the move is a rename, so the destination's free space is the only
    limit on a batch.
    """

    def _run(self, tmp_path, home, args):
        runner = tmp_path / "pipeline_spy_runner.py"
        runner.write_text(_PIPELINE_SPY_RUNNER)
        record = tmp_path / "hooks.jsonl"
        environment = dict(os.environ)
        environment["HOME"] = str(home)
        # macOS's framework Python caches bytecode under ~/Library/Caches when
        # the source tree is read-only to it, which would land in the home
        # directory these runs assert stays empty. That is the interpreter's
        # doing, not the pipeline's, so turn it off rather than carve it out.
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        # The runner imports cli.media_pipeline from scripts/, as lib/launch.sh
        # arranges for the command itself.
        environment["PYTHONPATH"] = str(SCRIPT_DIR)
        completed = subprocess.run(
            [sys.executable, str(runner), str(record), *args],
            cwd=str(SCRIPT_DIR), capture_output=True, text=True, env=environment,
        )
        entries = [json.loads(line) for line in record.read_text().splitlines()] \
            if record.exists() else []
        return PipelineResult(completed.stdout, completed.stderr,
                              completed.returncode), entries

    @pytest.fixture
    def empty_home(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir()
        return home

    def _pipeline_args(self, workspace, *extra):
        return [
            "--source", str(workspace["source"]),
            "--target", str(workspace["target"]),
            "--extensions", ".mp4", ".mov",
            "--timezone", "+0900",
            "--group", "Test",
            *extra,
        ]

    def test_apply_stages_under_the_target_and_leaves_home_untouched(
            self, tmp_path, temp_workspace, empty_home):
        """An apply run with no --working-dir puts its staged copies under the
        target, and writes nothing at all under the user's home directory.

        Actual: every staged copy sits in <target>/.jetlag-working and the home
        directory is still empty after the run
        Expected: the boot volume's free space is no longer the batch's limit
        """
        create_test_video(temp_workspace["source"] / "VID_20251005_100000_00_001.mp4")

        result, entries = self._run(
            tmp_path, empty_home, self._pipeline_args(temp_workspace, "--apply"))

        assert result.returncode == 0, f"Actual: {result.output}, Expected: a clean run"
        expected_dir = temp_workspace["target"] / ".jetlag-working"
        staged = _staged_paths(entries)
        assert staged, "Actual: nothing staged, Expected: ingest staged the file"
        assert [path.parent for path in staged] == [expected_dir], \
            f"Actual: staged at {staged}, Expected: under {expected_dir}"
        assert sorted(p.name for p in empty_home.rglob("*")) == [], \
            f"Actual: home holds {sorted(p.name for p in empty_home.rglob('*'))}, " \
            "Expected: nothing written under HOME"

    def test_staged_copy_is_renamed_into_place_not_copied_again(
            self, tmp_path, temp_workspace, empty_home):
        """Organize's move of a same-volume staged copy is a rename, so the file
        at the destination is the staged copy itself — no second full copy.

        Actual: the destination file's inode is the staged copy's inode
        Expected: a run costs one copy per file, not two
        """
        create_test_video(temp_workspace["source"] / "VID_20251005_100000_00_001.mp4")

        result, entries = self._run(
            tmp_path, empty_home, self._pipeline_args(temp_workspace, "--apply"))

        assert result.returncode == 0, f"Actual: {result.output}, Expected: a clean run"
        organized = sorted(temp_workspace["target"].rglob("*.mp4"))
        assert len(organized) == 1, f"Actual: {organized}, Expected: one organized file"
        moved = [entry for entry in entries if entry["hook"] == "organize"]
        assert len(moved) == 1, f"Actual: {moved}, Expected: one organize call"
        assert os.stat(organized[0]).st_ino == moved[0]["inode"], \
            f"Actual: {organized[0]} has a different inode from the staged copy " \
            f"organize was handed ({moved[0]['source']}), " \
            "Expected: organize renamed the staged copy into place"

    def test_clean_apply_removes_the_default_working_dir(
            self, tmp_path, temp_workspace, empty_home):
        """The staging directory does not outlive the run that created it.

        Actual: <target>/.jetlag-working is gone after a run with no failures
        Expected: the target is left holding only the organized library
        """
        create_test_video(temp_workspace["source"] / "VID_20251005_100000_00_001.mp4")

        result, _ = self._run(
            tmp_path, empty_home, self._pipeline_args(temp_workspace, "--apply"))

        assert result.returncode == 0, f"Actual: {result.output}, Expected: a clean run"
        assert not (temp_workspace["target"] / ".jetlag-working").exists(), \
            "Actual: the staging directory survived a clean run, Expected: removed"

    def test_explicit_working_dir_still_overrides_the_default(
            self, tmp_path, temp_workspace, empty_home):
        """--working-dir remains an override: nothing is staged under the target.

        Actual: staged copies sit in the given directory and no
        <target>/.jetlag-working is created
        Expected: callers that place staging themselves are unaffected
        """
        create_test_video(temp_workspace["source"] / "VID_20251005_100000_00_001.mp4")
        override = tmp_path / "elsewhere"

        result, entries = self._run(
            tmp_path, empty_home,
            self._pipeline_args(temp_workspace, "--apply", "--working-dir", str(override)))

        assert result.returncode == 0, f"Actual: {result.output}, Expected: a clean run"
        staged = _staged_paths(entries)
        assert [path.parent for path in staged] == [override], \
            f"Actual: staged at {staged}, Expected: under {override}"
        assert not (temp_workspace["target"] / ".jetlag-working").exists(), \
            "Actual: the default staging directory was created anyway, Expected: not used"

    def test_dry_run_creates_no_staging_directory_under_the_target(
            self, tmp_path, temp_workspace, empty_home):
        """A dry run stages nothing, so it creates nothing under the target.

        Actual: no .jetlag-working after a preview
        Expected: previewing a run never writes to the destination volume
        """
        create_test_video(temp_workspace["source"] / "VID_20251005_100000_00_001.mp4")

        result, entries = self._run(
            tmp_path, empty_home, self._pipeline_args(temp_workspace))

        assert result.returncode == 0, f"Actual: {result.output}, Expected: a clean run"
        staged = _staged_paths(entries)
        assert staged == [], f"Actual: {staged} staged, Expected: nothing"
        assert not (temp_workspace["target"] / ".jetlag-working").exists(), \
            "Actual: a dry run created the staging directory, Expected: not created"


class TestWorkingDirIsTransient:
    """Nothing survives in the working directory past its own file's iteration.

    The working directory is an implementation detail: ingest stages a copy of
    every source file into it and organize moves that copy out. When organize
    declines to place it — the destination already holds the same file, or a
    different one and --overwrite was not given — the staged copy has no further
    use, so the pipeline discards it. Idempotent re-runs are a designed use, so
    without this a second run over an already-organized library leaves the whole
    library duplicated on the working volume.
    """

    def _run(self, workspace, profile, working_dir, *extra):
        return run_pipeline([
            "--profile", profile,
            "--source", str(workspace["source"]),
            "--target", str(workspace["target"]),
            "--timezone", "+0900",
            "--group", "Test",
            "--working-dir", str(working_dir),
            *extra,
        ])

    def _leftovers(self, working_dir: Path) -> list[str]:
        if not working_dir.exists():
            return []
        return sorted(p.name for p in working_dir.iterdir())

    def _organize_results(self, stdout: str) -> list[dict]:
        return [event for event in
                (json.loads(line) for line in stdout.strip().split("\n") if line.strip())
                if event["event"] == "organize_result"]

    def test_second_identical_apply_leaves_no_staged_copies(self, temp_workspace, test_profile):
        """Re-running an already-organized folder must not duplicate it into the working dir.

        Actual: after the second apply the working dir holds no files, every
        file skipped as identical, and the destination files are byte-identical
        Expected: an idempotent re-run costs no disk space
        """
        working_dir = temp_workspace["root"] / "working"
        names = ["VID_20251005_100000_00_001.mp4", "VID_20251005_110000_00_002.mp4"]
        # Each clock is its name's time less nine hours: one camera set to +09:00
        # throughout, so the batch is not mixed.
        for name, clock in zip(names, ["01:00:00", "02:00:00"]):
            create_test_video(temp_workspace["source"] / name, media_create_date=f"2025:10:05 {clock}")

        self._run(temp_workspace, test_profile, working_dir, "--apply")
        organized = sorted(temp_workspace["target"].rglob("*.mp4"))
        assert len(organized) == 2, f"Actual: {organized}, Expected: both files organized"
        before = {p.name: p.read_bytes() for p in organized}

        result = self._run(temp_workspace, test_profile, working_dir, "--apply")

        actions = [(e["action"], e.get("reason")) for e in self._organize_results(result.stdout)]
        assert actions == [("skipped", "identical")] * 2, \
            f"Actual: {actions}, Expected: both files skipped as identical"
        assert self._leftovers(working_dir) == [], \
            f"Actual: working dir holds {self._leftovers(working_dir)}, Expected: nothing"
        after = {p.name: p.read_bytes() for p in temp_workspace["target"].rglob("*.mp4")}
        assert after == before, "Actual: destination bytes changed, Expected: untouched"

    def test_blocked_by_a_different_file_leaves_no_staged_copy(self, temp_workspace, test_profile):
        """A file organize refuses to overwrite still leaves nothing staged behind.

        Actual: skipped with reason=exists_differs, working dir empty, source intact
        Expected: the skip cleans up after itself just like the identical one
        """
        working_dir = temp_workspace["root"] / "working"
        name = "VID_20251005_100000_00_001.mp4"
        source_file = temp_workspace["source"] / name
        create_test_video(source_file)
        self._run(temp_workspace, test_profile, working_dir, "--apply")

        organized = next(temp_workspace["target"].rglob(name))
        with open(organized, "ab") as f:
            f.write(b"x" * 100)
        create_test_video(source_file)
        source_bytes = source_file.read_bytes()

        result = self._run(temp_workspace, test_profile, working_dir, "--apply")

        actions = [(e["action"], e.get("reason")) for e in self._organize_results(result.stdout)]
        assert actions == [("skipped", "exists_differs")], \
            f"Actual: {actions}, Expected: skipped/exists_differs"
        assert self._leftovers(working_dir) == [], \
            f"Actual: working dir holds {self._leftovers(working_dir)}, Expected: nothing"
        assert source_file.read_bytes() == source_bytes, \
            "Actual: the source file changed, Expected: untouched"

    def test_companion_copies_are_discarded_with_the_file_they_belong_to(
            self, temp_workspace, test_profile):
        """A discarded staged copy takes its companion copies with it.

        Actual: neither the .mp4 nor its .thm remains in the working dir
        Expected: companions staged by ingest are cleaned up on a skip too
        """
        working_dir = temp_workspace["root"] / "working"
        name = "VID_20251005_100000_00_001.mp4"
        video = temp_workspace["source"] / name
        create_test_video(video)
        (temp_workspace["source"] / "VID_20251005_100000_00_001.thm").write_bytes(b"thumb")

        self._run(temp_workspace, test_profile, working_dir, "--apply", "--copy-companion-files")
        result = self._run(temp_workspace, test_profile, working_dir, "--apply",
                           "--copy-companion-files")

        actions = [e["action"] for e in self._organize_results(result.stdout)]
        assert actions == ["skipped"], f"Actual: {actions}, Expected: skipped"
        assert self._leftovers(working_dir) == [], \
            f"Actual: working dir holds {self._leftovers(working_dir)}, Expected: nothing"

    def test_discard_line_names_the_file_not_the_working_dir(self, temp_workspace, test_profile):
        """The discard is reported, and reported without leaking the staging path.

        Actual: one 'Discarded staged copy' line naming the file and the skip reason
        Expected: the user can see where the staged copy went
        """
        working_dir = temp_workspace["root"] / "working"
        name = "VID_20251005_100000_00_001.mp4"
        create_test_video(temp_workspace["source"] / name)
        self._run(temp_workspace, test_profile, working_dir, "--apply")

        result = self._run(temp_workspace, test_profile, working_dir, "--apply")

        discards = [line for line in result.output.split("\n") if "Discarded staged copy" in line]
        assert len(discards) == 1, \
            f"Actual: {len(discards)} discard lines, Expected: 1\n{result.output}"
        assert name in discards[0] and "identical" in discards[0], \
            f"Actual: {discards[0]!r}, Expected: it to name {name} and the skip reason"
        assert str(working_dir) not in discards[0], \
            f"Actual: {discards[0]!r} leaks the working dir path, Expected: it names the file only"

    def test_organize_error_keeps_the_staged_copy_for_inspection(self, temp_workspace):
        """A file whose organize step errors keeps its staged copy on disk.

        Organize only errors when it cannot resolve a date for the file it was
        handed, which no source directory can be arranged to produce, so the
        step is stubbed out. The run is marked failed and main() then preserves
        the whole working dir — discarding the copy would throw away the
        evidence that failure exists to keep.

        Actual: the staged copy is still in the working dir and the pipeline
        owns nothing there for a cancel to remove
        Expected: only a clean run cleans up
        """
        working_dir = temp_workspace["root"] / "working"
        working_dir.mkdir()
        name = "VID_20251005_100000_00_001.mp4"
        create_test_video(temp_workspace["source"] / name)

        errored = organize_by_date.OrganizeResult(dest="", action="error")
        original = organize_by_date.process_file
        organize_by_date.process_file = lambda *a, **k: errored
        working = media_pipeline.WorkingDir(str(working_dir), created=True)
        try:
            opts = media_pipeline.RunOptions(
                source_dir=str(temp_workspace["source"]), target_dir=str(temp_workspace["target"]),
                working_dir=str(working_dir), extensions=[".mp4"], apply=True,
            )
            result = media_pipeline.process_file(temp_workspace["source"] / name, opts, working)
        finally:
            organize_by_date.process_file = original

        assert result.failed, "Actual: the run succeeded, Expected: organize's error to fail it"
        assert self._leftovers(working_dir) == [name], \
            f"Actual: working dir holds {self._leftovers(working_dir)}, Expected: the staged copy"
        assert working.staged == [], \
            "Actual: the preserved copy is still owned, Expected: a cancel must not remove it"

    def test_leftover_entries_on_a_clean_run_are_reported(self, temp_workspace, test_profile):
        """A non-empty working dir after a run with no failures is a defect, not a silence.

        Actual: the run warns, naming how many entries were left behind
        Expected: the pipeline never hides a working dir it failed to clean up
        """
        working_dir = temp_workspace["root"] / "working"
        working_dir.mkdir()
        (working_dir / "stray.mp4").write_bytes(b"stray")
        create_test_video(temp_workspace["source"] / "VID_20251005_100000_00_001.mp4")

        result = self._run(temp_workspace, test_profile, working_dir, "--apply")

        assert result.returncode == 0, f"Actual: rc={result.returncode}, Expected: a clean run"
        warnings = [line for line in result.output.split("\n")
                    if "left" in line and "working dir" in line.lower()]
        assert len(warnings) == 1, \
            f"Actual: {warnings}, Expected: one leftover warning\n{result.output}"
        assert "1" in warnings[0], \
            f"Actual: {warnings[0]!r}, Expected: it to name the leftover count"

    def test_a_clean_run_says_nothing_about_the_working_dir(self, temp_workspace, test_profile):
        """With the working dir emptied there is nothing to warn about."""
        working_dir = temp_workspace["root"] / "working"
        create_test_video(temp_workspace["source"] / "VID_20251005_100000_00_001.mp4")

        result = self._run(temp_workspace, test_profile, working_dir, "--apply")

        assert not working_dir.exists(), \
            f"Actual: working dir survives holding {self._leftovers(working_dir)}, Expected: removed"
        assert "left in the working dir" not in result.output, \
            f"Actual: a clean run warned about leftovers\n{result.output}"
