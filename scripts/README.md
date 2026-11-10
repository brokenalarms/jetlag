# Jetlag scripts

Command-line tools that bring footage from several cameras into one timeline. They
copy media off a card, correct each file's timestamps so clips from every camera
sort at the moment they were shot (whatever timezone each camera was set to), tag
them with the camera, and file them into dated folders. The Jetlag app runs these
same scripts; everything it does can be done from a terminal.

## Setup

Nothing to install on a Mac. The scripts run on the Python 3.9+ that ships with
macOS (or the Xcode Command Line Tools: `xcode-select --install` if macOS asks), and
exiftool is bundled in `tools/`. The first run in a checkout creates `.venv/` here
and installs the two Python packages in `requirements.txt`; later runs reuse it.

To use a different interpreter, set `JETLAG_PYTHON=/path/to/python3`.

Finder tags and file birth times are macOS features; elsewhere the scripts run and
leave them out.

## Dry run first

Every command that changes files previews by default: it prints what it would do
and changes nothing. Add `--apply` to make the changes. Run without `--apply`,
read the preview, then run again with it.

Source files are never modified: media-pipeline copies them first and works on the
copies. Only the optional `archive-source` step touches the source folder, and only
when asked to.

## Commands

Run any command with `--help` for every option. All of them can be run from any
directory, e.g. `~/jetlag/scripts/media-pipeline.sh …`.

| Command | What it does | Main options |
|---|---|---|
| `media-pipeline.sh` | The whole workflow for a card or folder: copy, tag, fix timestamps, file by date, then optionally make Gyroflow projects and archive the source | `--profile`, or `--source` and `--target`; `--timezone` or `--location`; `--group`; `--tasks`; `--apply` |
| `fix-media-timestamp.sh` | Correct one file's timestamps | `--timezone` or `--country`; `--infer-from-filename`; `--time-offset`; `--force-timezone`; `--apply` |
| `tag-media.sh` | Add Finder tags and camera make/model to files | `--tags`, `--make`, `--model`, `--apply` |
| `organize-by-date.sh` | Move (or copy) one file into a dated folder | `--target`, `--template`, `--copy`, `--overwrite`, `--apply` |
| `ingest-media.sh` | Copy one file (and its companion files) into a working folder | `--target`, `--companion-extensions`, `--apply` |
| `archive-source.sh` | Rename and move a source folder once it is imported, or delete the imported files | `--source`, `--action archive\|delete`, `--destination`, `--archived-name`, `--apply` |
| `generate-gyroflow.sh` | Write a Gyroflow stabilization project for a video with gyro data | `--preset`, `--apply` |
| `probe-camera.sh` | Report which camera shot the media in a folder | `--extensions`, `--sample` |
| `scan-source.sh` | Report how many media files a folder holds, or whether their names carry dates | `--extensions`, `--count` or `--timestamped-names` |
| `report-file-dates.sh` | Report where each file's date would come from: metadata, filename or file times | `--file-extensions` |

### Examples

Import a GoPro card shot in Japan, using the `gopro` profile:

```bash
./media-pipeline.sh --profile gopro --timezone Asia/Tokyo --group Japan          # preview
./media-pipeline.sh --profile gopro --timezone Asia/Tokyo --group Japan --apply  # do it
```

Without a profile, name the folders and extensions yourself:

```bash
./media-pipeline.sh --source /Volumes/Untitled/DCIM --target ~/Movies/Ready \
    --extensions .mp4 --location JP --apply
```

Fix one clip whose camera clock was on the wrong zone:

```bash
./fix-media-timestamp.sh GX010042.MP4 --timezone +09:00 --apply
```

Other examples:

```bash
./tag-media.sh *.MP4 --tags gopro-hero-12 --make GoPro --model "HERO12 Black" --apply
./organize-by-date.sh clip.mp4 --target ~/Movies/Ready --template "{{YYYY}}/{{MMM}}" --apply
./archive-source.sh --source /Volumes/Untitled/DCIM --destination ~/Imported --apply
./generate-gyroflow.sh ~/Movies/Ready/2025/2025-10-05/clip.mp4 --apply
./probe-camera.sh /Volumes/Untitled/DCIM --extensions .mp4 .mov
./scan-source.sh /Volumes/Untitled/DCIM --extensions .mp4 --count
./report-file-dates.sh /Volumes/Untitled/DCIM --file-extensions .mp4
```

`--timezone` takes a zone name (`Pacific/Auckland`, resolved per file so a trip
across a daylight-saving change gets each side right) or a fixed offset (`+0800`,
`+08:00`). `--location` / `--country` look the zone up from a country code or name
(`JP`, `Taiwan`).

## media-profiles.yaml

A profile describes one camera, so a run needs only `--profile <name>`. It lives in
`media-profiles.yaml` beside the commands; set `JETLAG_PROFILES_FILE` to use a file
elsewhere (the app keeps its own copy in Application Support).

```yaml
gyroflow:                       # optional: where Gyroflow is and its default preset
  binary: /Applications/Gyroflow.app/Contents/MacOS/gyroflow
  preset:
    stabilization: {max_zoom: 105.0}
profiles:
  gopro:
    type: video                 # video or photo
    source_dir: /Volumes/Untitled/DCIM          # where the card mounts (--source overrides)
    ready_dir: /Volumes/Media/GoPro/Ready       # where filed media goes (--target overrides)
    file_extensions: [.mp4]                     # what counts as media
    companion_extensions: [.thm, .lrv]          # sidecar files that travel with it
    tags: [gopro-hero-12]                       # Finder tags to add
    exif: {make: GoPro, model: HERO12 Black}    # camera written into files that lack it
    gyroflow_enabled: true                      # make Gyroflow projects by default
    folder_template: "{{YYYY}}/{{GROUP}}/{{YYYY}}-{{MM}}-{{DD}}"   # optional
```

`folder_template` placeholders are `{{YYYY}}`, `{{MM}}`, `{{MMM}}` (Jan, Feb, …),
`{{DD}}`, `{{YYYY-MM-DD}}` and `{{GROUP}}` (the `--group` value; without one, that
folder is left out). The default is the template shown above.

A profile's camera is checked against the files: an apply stops if a file was shot
by a different camera, unless `--allow-camera-mismatch` is given.

## Where output goes

- **Media** ends up under the target (`--target` or the profile's `ready_dir`),
  in dated folders: `2025/Japan/2025-10-05/GX010042.MP4`. While a run works, copies
  are staged in `<target>/.jetlag-working`, which is emptied as each file is filed.
- **Gyroflow projects** are written next to their video in the target.
- **The source** is left as it was, unless `--tasks … archive-source` renames and
  moves it (`<source> - copied <date>`) or `--source-action delete` removes the
  imported files.
- **What the terminal shows** is on stderr: a line per step per file and a summary.
  stdout carries machine-readable results for the app: JSON lines from
  media-pipeline, probe-camera and scan-source, and `@@key=value` lines from the
  other commands.

## How timestamps are decided

Each file's time comes from the most trustworthy source it holds: a metadata
timestamp that carries its own timezone ranks first, then one known to be UTC, then
a date in the filename, then a camera clock nothing corroborates, then metadata with
no zone and finally the file's own times. A correction relabels the time into the
zone it was shot in without moving the moment itself; only `--time-offset` moves
it. The full ranking, every field that is read and written, and how Final Cut Pro
reads them are in [docs/timestamp-fields.md](../docs/timestamp-fields.md).

## Inside this folder

| Path | Holds |
|---|---|
| `*.sh` | the commands |
| `media-profiles.yaml` | camera profiles |
| `cli/` | each command's argument parsing and output |
| `lib/` | the logic, one module or package per command plus shared modules; `lib/data/` holds the tables it reads |
| `tests/` | the test suite (`make test-scripts` from the repository root) |
| `tools/` | bundled exiftool, tag and the Gyroflow downloader |
