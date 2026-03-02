# Swift Migration & App Store Readiness

End-to-end migration plan from the current Python + Perl + external-Gyroflow
architecture to a self-contained Swift app suitable for Mac App Store
submission.

The migration is structured as five phases. Each phase ships independently and
leaves the app in a working state. Phases 1-3 can be done before or in parallel
with the JSONL IPC migration already in `specs/jsonl-app-ipc.md`.

---

## Phase 1 — MetadataService wrapper (ExifTool behind a Swift interface)

### Goal

Introduce a Swift `MetadataService` that the app calls instead of scripts
calling ExifTool directly. In this phase the service still shells out to the
vendored ExifTool under the hood — the point is to establish the API contract so
later phases can swap the implementation without touching callers.

### Design

```
┌──────────────┐      ┌──────────────────┐      ┌────────────┐
│  Python       │      │  MetadataService │      │  ExifTool   │
│  scripts      │ ───> │  (Swift CLI)     │ ───> │  (Perl)     │
│  or Swift app │      │  jetlag-metadata │      │  -stay_open │
└──────────────┘      └──────────────────┘      └────────────┘
```

**`jetlag-metadata`** is a small Swift CLI tool bundled in `scripts/tools/`
alongside `exiftool` and `tag`. It exposes a JSON-in/JSON-out interface over
stdin/stdout, mirroring the exact operations Jetlag needs.

### Interface

```
# Read tags
echo '{"op":"read","file":"/path/to/file.mov","tags":["DateTimeOriginal","Make","Model"]}' \
  | jetlag-metadata
# → {"DateTimeOriginal":"2025:06:18 07:25:21+08:00","Make":"GoPro","Model":"HERO12 Black"}

# Read tags (fast mode — skip detailed processing, equivalent to -fast2)
echo '{"op":"read","file":"/path/to/file.mov","tags":["DateTimeOriginal"],"fast":true}' \
  | jetlag-metadata
# → {"DateTimeOriginal":"2025:06:18 07:25:21+08:00"}

# Write tags
echo '{"op":"write","file":"/path/to/file.mov","tags":{"DateTimeOriginal":"2025:06:18 07:25:21+08:00","Keys:CreationDate":"2025:06:18 07:25:21+08:00","QuickTime:CreateDate":"2025:06:17 23:25:21","QuickTime:MediaCreateDate":"2025:06:17 23:25:21"}}' \
  | jetlag-metadata
# → {"updated":true,"files_changed":1}

# Write camera EXIF
echo '{"op":"write","file":"/path/to/file.mov","tags":{"Make":"GoPro","Model":"HERO12 Black"}}' \
  | jetlag-metadata
# → {"updated":true,"files_changed":1}
```

### Supported operations (exact Jetlag surface)

| Operation | Tags | Formats | Source |
|---|---|---|---|
| Read timestamps | DateTimeOriginal, CreateDate, ModifyDate, CreationDate, Keys:CreationDate, QuickTime:MediaCreateDate, QuickTime:MediaModifyDate | JPEG, HEIC, MOV, MP4, DNG, ARW, CR2, NEF | `timestamp_source.py:read_exif_data()` |
| Read camera | Make, Model | Same | `tag-media.py:get_existing_exif_camera()` |
| Read for organize | DateTimeOriginal (fast mode) | Same | `organize-by-date.py:get_file_date_for_organization()` |
| Write timestamps | DateTimeOriginal, Keys:CreationDate, QuickTime:CreateDate, QuickTime:MediaCreateDate | MOV, MP4, JPEG, HEIC | `fix-media-timestamp.py` |
| Write camera | Make, Model | MP4, MOV, JPG, PNG, DNG, ARW, CR2, NEF | `tag-media.py:add_camera_to_exif()` |

### Python integration

Replace `lib/exiftool.py` with `lib/metadata.py` that talks to the
`jetlag-metadata` CLI:

```python
class MetadataService:
    """Drop-in replacement for ExifTool wrapper using jetlag-metadata CLI."""

    def __init__(self):
        self._process = None  # persistent subprocess, same pattern as ExifTool

    def read_tags(self, file_path: str, tags: list[str],
                  extra_args: list[str] | None = None) -> dict:
        fast = extra_args and "-fast2" in extra_args
        return self._call({"op": "read", "file": file_path, "tags": tags, "fast": fast})

    def write_tags(self, file_path: str, tag_args: list[str]) -> bool:
        tags = {}
        for arg in tag_args:
            key, _, val = arg.lstrip("-").partition("=")
            tags[key] = val
        result = self._call({"op": "write", "file": file_path, "tags": tags})
        return result.get("updated", False)
```

The `read_tags` and `write_tags` signatures match `ExifTool` exactly, so all
call sites (`fix-media-timestamp.py`, `tag-media.py`, `organize-by-date.py`,
`timestamp_source.py`) work without changes.

### Implementation detail: persistent process

`jetlag-metadata` runs as a persistent process, same pattern as ExifTool's
`-stay_open`. It reads one JSON object per line from stdin and writes one JSON
response per line to stdout. This preserves the ~5-10ms per-operation
performance of the current `-stay_open` approach.

Under the hood in Phase 1, `jetlag-metadata` simply translates JSON requests
into ExifTool `-stay_open` commands and translates responses back to JSON.

### Files

| File | Action |
|---|---|
| `macos/Sources/Tools/jetlag-metadata/` | New Swift package (CLI target) |
| `scripts/lib/metadata.py` | New — Python wrapper for `jetlag-metadata` |
| `scripts/lib/exiftool.py` | Deprecated — imports redirect to `metadata.py` |
| `scripts/lib/timestamp_source.py` | Change: `from lib.metadata import metadata_service as exiftool` |
| `scripts/tag-media.py` | Change: same import swap |
| `scripts/organize-by-date.py` | Change: same import swap |
| `scripts/fix-media-timestamp.py` | Change: same import swap |

### Tests

- All existing tests pass (API is identical).
- New unit tests for `jetlag-metadata` CLI: JSON round-trip for each operation.
- Integration test: `jetlag-metadata` against real media files produces same
  output as direct ExifTool invocation.

### Acceptance criteria

- `pytest -x` passes with `jetlag-metadata` as the backend.
- No Python code imports `exiftool` directly — all go through `metadata.py`.
- Performance: batch of 10 files completes within 10% of current ExifTool
  timing.

---

## Phase 2 — Native metadata engine (replace ExifTool with Swift)

### Goal

Replace the ExifTool backend inside `jetlag-metadata` with native Swift code.
After this phase, the vendored `exiftool` binary and all Perl dependencies are
removed.

### Strategy

The tags Jetlag uses fall into two categories with very different binary formats:

#### A. EXIF tags in image files (JPEG, HEIC, DNG, ARW, CR2, NEF)

**Tags**: DateTimeOriginal (0x9003), CreateDate (0x9004), ModifyDate (0x0132),
Make (0x010F), Model (0x0110)

**Read**: Apple's ImageIO framework (`CGImageSourceCopyPropertiesAtIndex`)
handles all of these natively. Zero custom code needed.

```swift
let source = CGImageSourceCreateWithURL(url as CFURL, nil)!
let props = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as! [String: Any]
let exif = props[kCGImagePropertyExifDictionary as String] as? [String: Any]
let tiff = props[kCGImagePropertyTIFFDictionary as String] as? [String: Any]

// DateTimeOriginal, CreateDate → exif dict
// Make, Model → tiff dict
```

**Write**: `CGImageDestinationAddImageFromSource` + modified properties dict.
Atomic write (new file → rename). Preserves all other metadata.

```swift
let dest = CGImageDestinationCreateWithURL(url as CFURL, uti, 1, nil)!
var modified = props
modified[kCGImagePropertyExifDictionary] = updatedExif
CGImageDestinationAddImageFromSource(dest, source, 0, modified as CFDictionary)
CGImageDestinationFinalize(dest)
```

#### B. QuickTime atoms in video files (MOV, MP4)

**Tags**: QuickTime:CreateDate (mvhd atom), QuickTime:MediaCreateDate (mdhd
atom), Keys:CreationDate (mdta/keys + ilst atoms)

These require direct binary manipulation. No Apple framework writes them
in-place without re-encoding the video.

##### Binary format reference

**MOV/MP4 box structure:**

```
[4 bytes: size][4 bytes: type][payload...]
```

Special cases: size=1 means extended 64-bit size follows (8-byte uint64 after
type, total header=16 bytes). Size=0 means atom extends to end of file.

**mvhd atom** (movie header) — contains CreateDate:
```
Offset  Size  Field
0       1     version (0 or 1)
1       3     flags
4       4/8   creation_time (seconds since 1904-01-01 00:00:00 UTC)
8/12    4/8   modification_time
12/20   4     time_scale
16/24   4/8   duration
```
- Version 0: 32-bit timestamps (4 bytes each), big-endian uint32
- Version 1: 64-bit timestamps (8 bytes each), big-endian uint64
- Epoch: 1904-01-01 (2082844800 seconds before Unix epoch)
- Conversion: `unix_timestamp = qt_timestamp - 2082844800`
  (the constant is `(66 * 365 + 17) * 86400`, accounting for 17 leap years)
- Always UTC, always big-endian. No timezone info stored.

**mdhd atom** (media header) — contains MediaCreateDate:
```
Identical binary layout to mvhd for the timestamp fields.
Located at: moov/trak/mdia/mdhd (one per track)
Also has: time_scale, duration, language_code (int16u)
```

**Keys:CreationDate** — Apple metadata via mdta keys:

`moov/meta/hdlr` must have handler type `mdta`.

`moov/meta/keys` structure:
```
[4 bytes: atom size][4 bytes: "keys"]
[1 byte: version][3 bytes: flags]
[4 bytes: entry count]
  For each entry:
    [4 bytes: key size (includes these 4 bytes + namespace)]
    [4 bytes: key namespace, e.g. "mdta"]
    [variable: key name string, e.g. "com.apple.quicktime.creationdate"]
```

`moov/meta/ilst` structure:
```
[4 bytes: atom size][4 bytes: "ilst"]
  For each item:
    [4 bytes: item atom size]
    [4 bytes: key index (big-endian uint32, 1-based into keys list)]
      [4 bytes: data atom size]
      [4 bytes: "data"]
      [4 bytes: type indicator (1 = UTF-8, 21 = signed int, 22 = unsigned int)]
      [4 bytes: locale (usually 0)]
      [variable: value data]
```

Type 1 = UTF-8 string. CreationDate stored as ISO 8601: `2025-06-18T07:25:21+08:00`

**EXIF tags in JPEG** — for reference (handled by ImageIO, but good to
understand):

```
FF D8                         -- SOI
FF E1 [2-byte length]        -- APP1 marker
45 78 69 66 00 00             -- "Exif\0\0"
[2 bytes: byte order "II" or "MM"]
[2 bytes: TIFF magic 0x002A]
[4 bytes: offset to IFD0]
  IFD0 entries (12 bytes each):
    [2 bytes: tag ID][2 bytes: type][4 bytes: count][4 bytes: value/offset]
  ExifIFD (pointed to by tag 0x8769 in IFD0):
    DateTimeOriginal (0x9003): type=ASCII, count=20, "YYYY:MM:DD HH:MM:SS\0"
    CreateDate (0x9004): same format
  IFD0 directly:
    Make (0x010F): type=ASCII, variable length
    Model (0x0110): type=ASCII, variable length
    ModifyDate (0x0132): type=ASCII, count=20
```

Note: timezone is NOT in the date tags themselves — it's in separate
OffsetTimeOriginal (0x9011) / OffsetTimeDigitized (0x9012), added in EXIF 2.31.
ExifTool combines them for display.

##### Write strategy

ExifTool ALWAYS rewrites the entire file for QuickTime/MP4. Even changing a
single byte in mvhd requires copying the entire mdat (often gigabytes). This is
because moov typically comes before mdat, so any moov size change shifts all
`stco`/`co64` chunk offsets pointing into mdat. ExifTool's `WriteQuickTime`
function reads all non-mdat atoms into memory (up to 100MB), processes them,
then writes the output followed by a byte-for-byte copy of each mdat block.

For Jetlag's use case, we can be smarter:

1. **mvhd/mdhd timestamps** (CreateDate, MediaCreateDate): Fixed-size 4-byte
   (or 8-byte) integers at fixed offsets within their atoms. If we know the
   absolute file offset, we can **seek+write 4 bytes** — no file copy needed.
   This works because the atom size doesn't change.

2. **Keys:CreationDate**: If the key already exists and the new ISO 8601 string
   is the same byte length, value can be patched in-place. If adding a new key
   or the string length changes, moov must grow → full rewrite needed.

3. **Full rewrite fallback**: Copy file atom-by-atom. mdat is copied verbatim
   with 64KB buffered I/O (no re-encoding). Only moov is rebuilt. After
   rewriting moov, walk all `stco` (32-bit) and `co64` (64-bit) chunk offset
   tables and adjust every entry based on the new moov size delta. This is the
   ExifTool approach.

4. **Special case: moov after mdat** (streaming-optimized files from some
   cameras): moov can be rewritten in-place (append at end) without touching
   mdat at all, since chunk offsets don't shift.

**Implementation approach**: Write a `QuickTimeEditor` struct:

```swift
struct QuickTimeEditor {
    let url: URL

    /// Read all timestamp/camera metadata from the file
    func readMetadata() throws -> QuickTimeMetadata

    /// Write metadata. Attempts in-place patching first, falls back to
    /// full rewrite if moov must grow.
    func writeMetadata(_ updates: QuickTimeMetadata) throws -> Bool
}
```

The full-rewrite path:
1. Parse top-level atoms (ftyp, moov, mdat, free, etc.)
2. Parse moov recursively to find mvhd, mdhd, meta/keys/ilst
3. Apply changes to the parsed structure
4. Write new file: ftyp → moov (modified) → mdat (copied verbatim) → other atoms
5. Atomic swap (rename new → original, preserve original as backup)
6. Preserve file modification time (equivalent to ExifTool's `-P`)

**Performance**: mdat is the large atom (video data). It's copied byte-for-byte
with buffered I/O. No decoding. Speed is limited by disk I/O, same as ExifTool.

##### Read strategy for video

Use AVFoundation for reading (simpler than parsing atoms manually):

```swift
let asset = AVURLAsset(url: url)
let metadata = try await asset.load(.metadata)

// Keys:CreationDate
let creationDate = AVMetadataItem.metadataItems(from: metadata,
    filteredByIdentifier: .quickTimeMetadataCreationDate)

// Make, Model
let make = AVMetadataItem.metadataItems(from: metadata,
    filteredByIdentifier: .quickTimeMetadataMake)
```

For mvhd/mdhd timestamps, parse binary directly (AVFoundation exposes
`.creationDate` on `AVAsset` but not the raw UTC fields separately).

### Files

| File | Action |
|---|---|
| `macos/Sources/Tools/jetlag-metadata/ImageMetadata.swift` | New — ImageIO read/write for photos |
| `macos/Sources/Tools/jetlag-metadata/QuickTimeEditor.swift` | New — binary atom parser/writer |
| `macos/Sources/Tools/jetlag-metadata/QuickTimeAtom.swift` | New — atom parsing primitives |
| `macos/Sources/Tools/jetlag-metadata/main.swift` | Change — swap ExifTool backend for native |
| `scripts/tools/exiftool` | Delete (vendored Perl + libs) |
| `macos/project.yml` | Change — remove exiftool verification from build script |

### Test plan

- **Unit tests**: Read/write each tag on synthetic test files (JPEG with known
  EXIF, MOV with known atoms).
- **Regression tests**: Run against the same media files ExifTool was tested
  with. Compare output byte-for-byte for reads, verify written metadata matches
  via a reference ExifTool install.
- **Edge cases**:
  - MOV with moov at end of file (common in camera output)
  - MOV with moov at start (common after `qt-faststart`)
  - MP4 with 64-bit atom sizes
  - JPEG with multiple APP1 markers
  - HEIC (container-based, uses ImageIO)
  - Files with no existing Keys:CreationDate (add new key)
  - Files with existing Keys:CreationDate (update in-place)
  - Timezone formats: `+08:00`, `+0800`, `Z`

### Acceptance criteria

- ExifTool binary removed from `scripts/tools/`.
- `pytest -x` passes.
- `jetlag-metadata` handles all formats listed above.
- Performance within 20% of ExifTool for read operations, within 50% for write
  operations (full-file rewrite is I/O-bound).

---

## Phase 3 — Python scripts → Swift

### Goal

Port the Python pipeline scripts to Swift, eliminating the Python interpreter
dependency entirely.

### Migration order

Port in dependency order (leaves first):

1. **`lib/file_timestamps.py`** → `FileTimestamps.swift`
   - Replace `SetFile` / `stat` subprocess calls with `FileManager` /
     `URLResourceValues` / `NSURL.setResourceValues`.
   - `URLResourceValues.creationDate` for reading birth time.
   - `URLResourceValues.contentModificationDate` for reading mtime.
   - Setting creation date: `try url.setResourceValues(values)` where
     `values.creationDate = newDate`.

2. **`lib/timestamp_source.py`** → `TimestampSource.swift`
   - Calls `MetadataService` (from Phase 2) instead of ExifTool.
   - Port the 6-tier priority system, timezone normalization, filename parsing.
   - ~400 lines of pure logic, straightforward port.

3. **`lib/filesystem.py`** → `FileSystem.swift`
   - Replace `subprocess` calls with `FileManager` operations.

4. **`tag-media.py`** → `TagMedia.swift`
   - Finder tags: replace `tag` CLI with `NSURL.setResourceValues` using
     `URLResourceValues.tagNames`.
   - EXIF write: calls `MetadataService`.
   - ~200 lines.

5. **`organize-by-date.py`** → `OrganizeByDate.swift`
   - File moves with `FileManager.moveItem`.
   - ~150 lines of logic.

6. **`fix-media-timestamp.py`** → `FixMediaTimestamp.swift`
   - Largest script (~900 lines). Core timestamp analysis and correction logic.
   - All EXIF operations go through `MetadataService`.
   - Port timezone handling, change detection, write optimization.

7. **`generate-gyroflow.py`** → `GenerateGyroflow.swift`
   - Replace `ffprobe` with AVFoundation track inspection for gyro data.
   - Gyroflow project generation handled by Phase 5 (or falls back to CLI).

8. **`media-pipeline.py`** → `MediaPipeline.swift`
   - Orchestrator. Calls the other modules.
   - Emits JSONL events (per `specs/jsonl-app-ipc.md`).
   - Can be integrated directly into the macOS app (no subprocess boundary).

### Architecture after Phase 3

```
┌──────────────────────────┐
│  Jetlag macOS App        │
│                          │
│  ┌────────────────────┐  │
│  │ MediaPipeline       │  │
│  │  ├── TagMedia       │  │
│  │  ├── FixTimestamp   │  │
│  │  ├── OrganizeByDate │  │
│  │  └── Gyroflow       │  │
│  └────────┬───────────┘  │
│           │               │
│  ┌────────┴───────────┐  │
│  │ MetadataService     │  │
│  │  ├── ImageMetadata  │  │
│  │  └── QuickTimeEditor│  │
│  └────────────────────┘  │
└──────────────────────────┘
```

No subprocess calls. No Python. No shell wrappers. The pipeline runs as
async Swift functions within the app process, emitting progress events via
a callback/delegate.

### IPC change

With the pipeline running in-process, the JSONL IPC boundary
(`specs/jsonl-app-ipc.md`) becomes an internal event stream:

```swift
protocol PipelineDelegate: AnyObject {
    func pipeline(_ pipeline: MediaPipeline, didEmit event: PipelineEvent)
}

// Or using AsyncStream:
func runPipeline(files: [URL], profile: MediaProfile) -> AsyncStream<PipelineEvent>
```

`AppState` subscribes to the stream directly — no stdout parsing needed.

### Finder tag tool

The vendored `tag` CLI can be replaced with native `NSURL` resource values:

```swift
// Read tags
let values = try url.resourceValues(forKeys: [.tagNamesKey])
let tags = values.tagNames ?? []

// Write tags
var values = URLResourceValues()
values.tagNames = ["gopro-hero-12", "japan-2025"]
try url.setResourceValues(values)
```

### Files removed

- `scripts/*.py` (all Python scripts)
- `scripts/*.sh` (all shell wrappers)
- `scripts/lib/` (all Python libraries)
- `scripts/tools/tag` (replaced by NSURL)
- `scripts/tools/exiftool` (already removed in Phase 2)
- `scripts/requirements.txt`
- `scripts/lib/ensure-venv.sh`
- `macos/project.yml` post-build "Bundle scripts" phase

### Files preserved

- `scripts/media-profiles.yaml` → stays as shared config, now read only by
  the Swift app via Yams (already supported).
- `scripts/tests/` → port to XCTest alongside each Swift module.

### Test strategy

- Port each Python test file to XCTest as the corresponding module is ported.
- Keep the Python tests runnable until the Swift version passes all equivalent
  assertions.
- The performance harness (`scripts/tests/test_performance.py`) is ported last
  and becomes an XCTest performance test.

### Acceptance criteria

- No Python or shell files in `scripts/` (except `media-profiles.yaml` and
  test fixtures).
- `xcodebuild test` passes all ported tests.
- Pipeline runs in-process with no subprocess calls for core operations.
- App bundle size decreases (no Python venv, no Perl, no shell wrappers).

---

## Phase 4 — Gyroflow Core embedding

### Goal

Replace the external Gyroflow app dependency with an embedded Gyroflow Core
library, so the app can generate `.gyroflow` project files without requiring
Gyroflow to be installed.

### Current usage

Jetlag runs: `gyroflow FILE --export-project 2 [--preset JSON]`

This generates a `.gyroflow` project file (JSON) containing:
- Video metadata (resolution, frame rate, codec)
- Gyroscope data extracted from the video
- Lens profile
- Stabilization settings from the preset

Jetlag does NOT perform actual stabilization — it only generates the project
file.

### Gyroflow Core architecture

Gyroflow Core is a Rust library (`src/core/` in the gyroflow repo). Key type:
`StabilizationManager`. Not published on crates.io — must be referenced as a Git
dependency.

The library is self-contained: it bundles `telemetry-parser` internally, which
natively reads gyro/IMU data from MP4/MOV metadata tracks for GoPro, Sony, DJI,
Insta360, Blackmagic RAW, RED RAW, Canon, and others. No ffmpeg dependency.

```rust
// Exact API sequence (from Gyroflow Toolbox's importMediaFile)
let mut stab = StabilizationManager::default();
stab.load_video_file(&media_file_path, None, true);  // parse gyro data natively

// Optional: apply preset
stab.import_gyroflow_data(&preset_json_string, ...);

// Export .gyroflow project (JSON string)
let project_data = stab.export_gyroflow_data(
    GyroflowProjectType::WithGyroData,  // CLI option 2 = what Jetlag uses
    "{}",   // additional data to merge
    None,
);
// project_data is serde_json::to_string_pretty() output → write to file
```

`GyroflowProjectType` variants: `Simple` (option 1), `WithGyroData` (option 2,
Jetlag's choice), `WithProcessedData` (option 3).

### Integration approach

[Gyroflow Toolbox](https://github.com/latenitefilms/GyroflowToolbox) (shipped
on the Mac App Store, $9.99) proves this works. It embeds Gyroflow Core as a
`cdylib` with raw C FFI (`extern "C"` functions using `CStr`/`CString`).

Key FFI functions exposed by Gyroflow Toolbox:
- `importMediaFile(path) -> project JSON string`
- `loadPreset(project_data, preset_path) -> updated project JSON`
- `doesGyroflowProjectContainStabilisationData(project_data) -> bool`
- `processFrame(...)` — stabilization (not needed by Jetlag)

### Swift wrapper

Create a thin Rust FFI crate depending on `gyroflow-core`:

```rust
// Cargo.toml
[dependencies]
gyroflow-core = { git = "https://github.com/gyroflow/gyroflow.git",
                  features = ["bundle-lens-profiles", "cache-gyro-metadata"] }

[lib]
crate-type = ["staticlib"]
```

```rust
// src/lib.rs — 3 functions are sufficient for Jetlag
#[no_mangle]
pub extern "C" fn jetlag_generate_project(
    video_path: *const c_char,
    preset_json: *const c_char,
) -> *mut c_char { ... }

#[no_mangle]
pub extern "C" fn jetlag_has_motion_data(video_path: *const c_char) -> bool { ... }

#[no_mangle]
pub extern "C" fn jetlag_free_string(ptr: *mut c_char) { ... }
```

Swift side:

```swift
import GyroflowCore  // C module map wrapping the static library

enum GyroflowService {
    static func generateProject(videoURL: URL, presetJSON: String) throws -> Data {
        guard let result = jetlag_generate_project(videoURL.path, presetJSON) else {
            throw GyroflowError.exportFailed
        }
        defer { jetlag_free_string(result) }
        return Data(String(cString: result).utf8)
    }

    static func hasMotionData(videoURL: URL) -> Bool {
        jetlag_has_motion_data(videoURL.path)
    }
}
```

### Build integration

```bash
# Build for each architecture
cargo build --release --target aarch64-apple-darwin
cargo build --release --target x86_64-apple-darwin

# Combine into universal binary
lipo -create \
  target/aarch64-apple-darwin/release/libjetlag_gyroflow.a \
  target/x86_64-apple-darwin/release/libjetlag_gyroflow.a \
  -output libjetlag_gyroflow-universal.a
```

1. Pre-build the universal static library and commit it (or build via CI).
2. Create a C module map (`module.modulemap`) exposing the C API header.
3. Add as an XcodeGen dependency.
4. Expected size: ~5-10MB (GPU shaders stripped, no OpenCL features).

### License

Gyroflow is GPLv3 with an **App Store exception**: distribution through an app
store is explicitly permitted, provided the source is also available under GPLv3
through an unrestricted channel. Gyroflow Toolbox does exactly this (paid App
Store app, source on GitHub). Jetlag would need its source on GitHub under GPLv3
(or a compatible license) to use Gyroflow Core.

### ffprobe replacement

Current: `ffprobe -v quiet -print_format json -show_streams FILE`
(checks for motion/gyro data streams)

**Best replacement**: Use Gyroflow Core itself. `telemetry-parser` (bundled
inside gyroflow-core) natively reads gyro/IMU data from MP4/MOV metadata tracks
for all supported cameras. Attempting `load_video_file` and checking whether it
found gyro data is a more reliable check than ffprobe's stream type inspection.
Expose this as `jetlag_has_motion_data()` in the FFI layer.

Fallback (if Gyroflow Core not available): AVFoundation track inspection.

```swift
let asset = AVURLAsset(url: url)
let tracks = try await asset.load(.tracks)
let hasMotionData = tracks.contains { track in
    track.mediaType == .metadata
}
```

### Optionality

Gyroflow project generation is already optional in the pipeline (controlled by
`gyroflow_enabled` per profile). For App Store, Gyroflow Core is bundled but
only activated when the user enables it for a profile. No install prompt needed.

### Files

| File | Action |
|---|---|
| `macos/Libraries/GyroflowCore/` | New — pre-built static lib + headers + module map |
| `macos/Sources/Services/GyroflowService.swift` | New — Swift wrapper |
| `macos/Sources/Pipeline/GenerateGyroflow.swift` | Change — use GyroflowService |
| `scripts/generate-gyroflow.py` | Already removed in Phase 3 |
| `scripts/batch-generate-gyroflow.py` | Already removed in Phase 3 |

### Acceptance criteria

- Gyroflow project generation works without external Gyroflow app installed.
- `.gyroflow` files produced are loadable in Gyroflow app.
- App bundle includes Gyroflow Core static library, properly signed.

---

## Phase 5 — App Sandbox & App Store submission

### Goal

Enable the App Sandbox and submit to the Mac App Store.

### Sandbox entitlements

```xml
<dict>
    <key>com.apple.security.app-sandbox</key>
    <true/>
    <key>com.apple.security.files.user-selected.read-write</key>
    <true/>
    <key>com.apple.security.files.bookmarks.app-scope</key>
    <true/>
</dict>
```

- **User-selected read-write**: User picks source/target directories via
  `NSOpenPanel`. App gets read-write access to those directories.
- **App-scope bookmarks**: Persist directory access across launches (security-
  scoped bookmarks). User picks once, app remembers.

### Security-scoped bookmarks

Profiles currently store raw paths (`source_dir`, `ready_dir`, `backup_dir`).
In sandboxed mode, these must be backed by security-scoped bookmarks:

```swift
// When user picks a directory:
let bookmark = try url.bookmarkData(
    options: .withSecurityScope,
    includingResourceValuesForKeys: nil,
    relativeTo: nil
)
// Store bookmark data in profile

// When accessing:
var isStale = false
let url = try URL(resolvingBookmarkData: bookmark,
    options: .withSecurityScope,
    relativeTo: nil,
    bookmarkDataIsStale: &isStale)
guard url.startAccessingSecurityScopedResource() else { throw ... }
defer { url.stopAccessingSecurityScopedResource() }
```

### Profile storage migration

`media-profiles.yaml` stores plain paths. Add a companion
`~/.jetlag/bookmarks.plist` (or store in UserDefaults) mapping each path to
its security-scoped bookmark data. On app launch, resolve bookmarks and
validate access.

### Privacy manifest

Create `PrivacyInfo.xcprivacy`:

```xml
<dict>
    <key>NSPrivacyAccessedAPITypes</key>
    <array>
        <dict>
            <key>NSPrivacyAccessedAPIType</key>
            <string>NSPrivacyAccessedAPICategoryFileTimestamp</string>
            <key>NSPrivacyAccessedAPITypeReasons</key>
            <array>
                <string>C617.1</string>  <!-- file management -->
            </array>
        </dict>
    </array>
</dict>
```

### App Store checklist

- [ ] App Sandbox enabled with minimal entitlements
- [ ] Security-scoped bookmarks for all user-selected directories
- [ ] Privacy manifest for file timestamp API usage
- [ ] All binaries signed with Team ID (Gyroflow Core static lib)
- [ ] No calls to `Process()` or `NSTask` (all operations in-process)
- [ ] No references to external apps or install prompts
- [ ] App category: `public.app-category.video` (already set)
- [ ] Screenshots for App Store listing
- [ ] App Store description and metadata

### Files

| File | Action |
|---|---|
| `macos/Sources/App.entitlements` | Change — add sandbox + bookmark entitlements |
| `macos/Sources/PrivacyInfo.xcprivacy` | New |
| `macos/Sources/Services/BookmarkService.swift` | New — security-scoped bookmark management |
| `macos/Sources/Services/ProfileService.swift` | Change — integrate bookmarks with profile paths |

### Acceptance criteria

- App runs fully sandboxed.
- User can pick directories, and access persists across launches.
- App Review submission succeeds.

---

## Phase dependencies

```
Phase 1 (MetadataService wrapper)
    │
    ▼
Phase 2 (Native metadata engine)
    │
    ▼
Phase 3 (Python → Swift)──────────┐
    │                              │
    ▼                              ▼
Phase 4 (Gyroflow Core)     Phase 5 (Sandbox)
                                   │
                                   ▼
                            App Store submission
```

Phases 4 and 5 can proceed in parallel after Phase 3. Phase 5 depends on Phase
3 because the sandbox prohibits `Process()` subprocess calls (which Python
scripts require).

Phase 1 can begin immediately and ships as a standalone improvement regardless
of whether the full migration completes.

---

## Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| QuickTime atom writing has edge cases in camera-specific formats | Files could be corrupted | Comprehensive test matrix across camera models. Keep ExifTool as a validation oracle during development. |
| Gyroflow Core C API may not expose project export directly | Phase 4 blocked | Fallback: generate .gyroflow JSON manually using AVFoundation metadata + preset. The format is documented JSON. |
| AVAssetExportSession needed for some video metadata writes | Performance regression for video writes | Binary atom writer handles all known cases. Export session only as last resort for exotic containers. |
| App Review rejection for undisclosed reasons | Submission delayed | Submit early with a minimal build to identify issues before the full migration. |
| Security-scoped bookmarks expire or become stale | Broken user experience | Detect stale bookmarks on launch, prompt user to re-select. Store bookmarks redundantly. |
| Gyroflow Core binary size | App bundle too large | Strip GPU shader code (not needed for project file generation). Target ~5MB for the static lib. |

---

## Size estimates

| Phase | Effort | New Swift LoC | Files changed |
|---|---|---|---|
| Phase 1 — MetadataService wrapper | Small | ~300 | ~8 |
| Phase 2 — Native metadata engine | Large | ~1500 | ~6 |
| Phase 3 — Python → Swift | Large | ~3000 | ~20+ |
| Phase 4 — Gyroflow Core | Medium | ~200 | ~4 |
| Phase 5 — Sandbox | Medium | ~400 | ~5 |
