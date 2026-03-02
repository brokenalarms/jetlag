# App Store Distribution: External Dependencies

Research into what it takes to ship Jetlag on the Mac App Store given its
dependency on Python, Perl (ExifTool), and Gyroflow.

---

## Current Architecture

| Component | Runtime | Notes |
|---|---|---|
| Python scripts (`scripts/`) | System `python3` via venv | humanize, PyYAML |
| ExifTool (`scripts/tools/exiftool`) | System `/usr/bin/perl` | Vendored v13.50, persistent `-stay_open` subprocess |
| Gyroflow | External app at configured path | Launched as subprocess, user must install separately |
| `tag` CLI | Native binary | Vendored, already self-contained |
| `ffprobe` | System install (Homebrew/Xcode) | Used only to detect gyro data streams |
| `SetFile` / `stat` / `date` | macOS system tools | File birth-time operations |

**Problem**: The app currently has no sandbox, uses system interpreters, and
requires external app installation — all blockers for Mac App Store.

---

## Mac App Store Hard Requirements

1. **App Sandbox is mandatory** (`com.apple.security.app-sandbox` entitlement).
2. **Self-contained bundle** — cannot require installation of other apps (Guideline 4.2(i)).
3. **No shared-location installs** — everything lives inside the `.app` (Guideline 2.4.5).
4. **All binaries code-signed** with your Team ID.
5. **Helper tools** must use `com.apple.security.inherit` entitlement (sandbox inheritance).
6. **Cannot use system Python or Perl** from a sandboxed app — "bad interpreter: Operation not permitted".
7. **Privacy Manifests** (`.xcprivacy`) required since April 2025 if using affected libraries (e.g. OpenSSL).

---

## Dependency-by-Dependency Analysis

### Python

**Can it be bundled? Yes — proven path exists.**

- [BeeWare's Python-Apple-support](https://github.com/beeware/Python-Apple-support) provides pre-built `Python.xcframework` for macOS (x86_64 + arm64), relocatable and App-Store-compliance-patched.
- [PythonKit](https://github.com/pvieito/PythonKit) (SPM) bridges Swift ↔ Python.
- Python 3.13+ has `--with-app-store-compliance` configure flag that patches out the `itms-services` string (cause of mass rejections in 3.12).
- All `.so` binaries must be individually signed with Team ID.
- Needs `com.apple.security.cs.allow-unsigned-executable-memory` entitlement for ctypes/cffi (Apple may scrutinize).

**Real-world examples on Mac App Store:**
- [Py Editor for Python](https://apps.apple.com/us/app/py-editor-for-python/id6456883927?mt=12) — embeds Python 3.11
- [Pyto IDE](https://apps.apple.com/us/app/pyto-ide/id1436650069) — full Python + 100+ packages
- Eric Froemling's game — successfully shipped with bundled Python after fixing 3.12 rejections

**Tooling options:**
- BeeWare Briefcase — most maintained, added Mac App Store publishing guide (July 2025)
- py2app — works for `.app` bundles but App Store submission is uncharted
- PyInstaller — described as "a nightmare" for App Store; hardened runtime incompatibilities

### Perl / ExifTool

**Bundling Perl is impractical — no maintained tooling exists.**

- No equivalent of BeeWare for Perl — no relocatable, signable Perl framework for macOS apps.
- [ExifTool Reader](https://apps.apple.com/us/app/exiftool-reader/id1636199770) initially tried bundling ExifTool with Perl and hit "bad interpreter: Operation not permitted". **They rewrote entirely in native Swift** (v1.1.0).
- The ExifTool Windows standalone bundles a compiled Perl, but no equivalent macOS bundle exists for App Store distribution.

**What Jetlag actually uses from ExifTool:**

| Operation | Tags | File Types |
|---|---|---|
| `read_tags` | DateTimeOriginal, CreateDate, ModifyDate, CreationDate, Keys:CreationDate, QuickTime:MediaCreateDate | Photos + Videos (MOV, MP4) |
| `write_tags` | DateTimeOriginal, Keys:CreationDate, QuickTime:CreateDate, QuickTime:MediaCreateDate | Photos + Videos |
| `read_tags` | Make, Model | Photos + Videos (tag-media) |
| `write_tags` | Make, Model | Photos + Videos (tag-media) |
| `read_tags` | DateTimeOriginal | Photos + Videos (organize-by-date) |

### Gyroflow

**Cannot require external installation. Options exist.**

- Guideline 4.2(i): "Your app should work on its own without requiring installation of another app to function."
- [Gyroflow](https://apps.apple.com/us/app/gyroflow/id6447994244) is itself on the Mac App Store (free).
- [Gyroflow Core](https://docs.gyroflow.xyz/app/technical-details/gyroflow-core) is a standalone Rust library that does all stabilization.
- [Gyroflow Toolbox](https://apps.apple.com/us/app/gyroflow-toolbox/id1667462993?mt=12) ($9.99) embeds Gyroflow Core into FCP — proves the library can ship on the App Store.

### ffprobe

**Only used for gyro-stream detection** — a narrow use case. Could be replaced with AVAsset stream inspection or bundled as a signed binary.

### SetFile / stat / date

**macOS system tools** — available inside the sandbox. `SetFile` requires Xcode Command Line Tools but could be replaced with native Swift `FileManager` / `URLResourceValues` APIs.

---

## Native Alternatives to ExifTool

### Apple's ImageIO Framework (Built-in)

- `CGImageSource` / `CGImageDestination` — read/write EXIF, IPTC, GPS, TIFF, XMP, JFIF.
- **Photos only** — does NOT work with video files (MOV, MP4).
- Covers ~51% of ExifTool's property keys.
- Missing: custom XMP namespaces (e.g. `Xmp.drone-dji`), maker notes.

### Apple's AVFoundation (Built-in)

- `AVAsset` / `AVMetadataItem` — read video metadata.
- `AVAssetExportSession` — can preserve/modify metadata during re-export.
- Handles QuickTime metadata (Keys, UserData, ItemList tag groups).
- Can read/write CreationDate, Make, Model in MOV/MP4.
- **Limitation**: Re-exporting video to write metadata is slow and lossy compared to ExifTool's in-place binary patching.

### Exiv2 (C++ Library)

- Handles EXIF, IPTC, XMP, ICC profiles.
- More comprehensive than libexif, less than ExifTool.
- No Swift wrapper exists — need C bridging layer or Swift 5.9+ C++ interop.
- Used by GIMP, darktable, shotwell.

### libexif (Pure C)

- EXIF-only — no XMP, IPTC, video metadata.
- [SwiftExif](https://github.com/kradalby/SwiftExif) — Swift wrapper via SPM.
- Insufficient for Jetlag's needs (video metadata is critical).

### SwiftExif, SYPictureMetadata, Carpaccio

- Thin Swift wrappers around ImageIO or libexif.
- Read-only or limited write support.
- None handle video container metadata.

---

## Paths to App Store

### Path A: Embed Python + Replace ExifTool in Python (Moderate)

Keep the Python scripts but replace the Perl ExifTool dependency with a
Python-native solution.

1. **Embed Python** via BeeWare Python-Apple-support + PythonKit.
2. **Replace ExifTool** in Python with:
   - [pyexiv2](https://github.com/LeoHsiao1/pyexiv2) — Python binding to Exiv2 C++ library.
     Handles EXIF/IPTC/XMP for images. Would need to bundle the Exiv2 `.dylib`.
   - [pymediainfo](https://github.com/sbraz/pymediainfo) or `av` (PyAV) for video metadata reading.
   - For video metadata **writing**: This is the hard part. No Python library
     does in-place QuickTime atom editing like ExifTool. May need a small C
     extension or accept the AVFoundation re-export approach.
3. **Gyroflow**: Make optional, or embed Gyroflow Core via Rust→C FFI.
4. **Sandbox**: Add security-scoped bookmarks for user-selected directories.

**Pros**: Keeps existing Python logic, tests, and architecture mostly intact.
**Cons**: Still bundling a ~50MB Python interpreter. Exiv2 adds complexity.
Video metadata writing is unsolved without ExifTool.

### Path B: Full Swift Rewrite (High Effort, Cleanest)

Port all Python scripts to Swift.

1. **Image metadata**: ImageIO (`CGImageSource`/`CGImageDestination`) covers all
   image EXIF read/write needs.
2. **Video metadata reading**: `AVAsset` + `AVMetadataItem` for QuickTime tags.
3. **Video metadata writing**: This remains the hardest problem.
   - AVAssetExportSession can write metadata but re-encodes video (slow, lossy).
   - Direct QuickTime atom manipulation in Swift — no maintained library exists.
   - Could wrap Exiv2 via Swift C++ interop for this specific case.
4. **Gyroflow**: Embed Gyroflow Core (Rust lib, C API).
5. **File timestamps**: Replace `SetFile`/`stat` with `FileManager`/`URLResourceValues`.
6. **ffprobe replacement**: `AVAsset.tracks` to detect gyro data streams.

**Pros**: No interpreters, smallest bundle, fastest runtime, cleanest App Store
path, no sandbox entitlement edge cases.
**Cons**: Major rewrite. Need to re-implement all timestamp logic, tag logic,
pipeline orchestration. Tests need full rewrite. Video metadata writing still
hard.

### Path C: Hybrid — Swift for Metadata, Keep Python for Orchestration (Balanced)

1. **New Swift module** for all EXIF/metadata operations (replaces ExifTool):
   - ImageIO for photo EXIF read/write.
   - AVFoundation for video metadata read.
   - Exiv2 (via C++ interop) for video metadata write.
2. **Keep Python** for pipeline orchestration, file operations, timestamp logic.
   - Python calls the Swift metadata module via a bundled CLI tool or XPC.
3. **Embed Python** via BeeWare.
4. **Gyroflow**: Optional or embed Gyroflow Core.

**Pros**: Tackles the hardest problem (ExifTool) natively while preserving
tested Python logic. Incremental migration path.
**Cons**: Two-language complexity. Build system more complex.

### Path D: Skip App Store, Direct Distribution (Lowest Effort)

Distribute as a notarized `.dmg` or `.pkg` outside the Mac App Store.

1. Keep current architecture entirely.
2. Enable hardened runtime + notarization.
3. Gyroflow remains an optional external dependency.
4. No sandbox required (though recommended).

**Pros**: Zero migration work. Ship immediately.
**Cons**: No App Store discovery, no automatic updates via App Store, users must
allow "identified developer" apps, no App Store trust signal.

---

## Recommendation

**Path D (direct distribution) for v1.0, then migrate toward Path C for App
Store in v2.0.**

### Rationale

1. **The video metadata writing problem is unsolved without ExifTool.** No
   Swift, Python, or C library does in-place QuickTime atom editing with the
   breadth ExifTool provides. This is the single biggest blocker. Solving it
   requires either:
   - Writing a QuickTime atom editor (significant effort)
   - Wrapping Exiv2 and accepting its narrower tag coverage
   - Using AVAssetExportSession (re-encodes, slow, lossy — unacceptable for a
     media tool)

2. **Bundling Perl is a dead end.** No tooling, no precedent, no path.

3. **Bundling Python is proven but adds ~50MB** and build complexity. Worth it
   only if there's meaningful Python logic to preserve.

4. **The highest-leverage incremental step** is building a native Swift metadata
   service that handles the specific tags Jetlag uses (DateTimeOriginal,
   CreateDate, Keys:CreationDate, Make, Model) for the specific formats it
   touches (JPEG, HEIC, MOV, MP4). This is a much smaller surface than "replace
   all of ExifTool" — it's roughly 6 tags across 4 formats.

### Suggested Migration Sequence

1. **Now**: Ship v1.0 via direct distribution (notarized DMG).
2. **Next**: Build `MetadataService.swift` that handles the 6 tags Jetlag
   actually uses, using ImageIO (photos) + AVFoundation (video reads) + direct
   QuickTime atom writing (video writes) or Exiv2.
3. **Then**: Replace `lib/exiftool.py` calls with the Swift metadata service
   (called from Python via subprocess, or port the calling scripts).
4. **Then**: Embed Python via BeeWare or continue porting scripts to Swift.
5. **Then**: Make Gyroflow optional or embed Gyroflow Core.
6. **Finally**: Enable sandbox, add security-scoped bookmarks, submit to App Store.

---

## Key Sources

- [Embedding Python in a macOS App for App Store](https://medium.com/swift2go/embedding-python-interpreter-inside-a-macos-app-and-publish-to-app-store-successfully-309be9fb96a5)
- [BeeWare Python-Apple-support](https://github.com/beeware/Python-Apple-support)
- [Python 3.12 App Store rejection (CPython #120522)](https://github.com/python/cpython/issues/120522)
- [Apple App Sandbox documentation](https://developer.apple.com/documentation/xcode/configuring-the-macos-app-sandbox)
- [Embedding helper tools in sandboxed apps](https://developer.apple.com/documentation/xcode/embedding-a-helper-tool-in-a-sandboxed-app)
- [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/)
- [ExifTool Reader (rewrote to native Swift)](https://apps.apple.com/us/app/exiftool-reader/id1636199770)
- [Gyroflow Core docs](https://docs.gyroflow.xyz/app/technical-details/gyroflow-core)
- [Gyroflow Toolbox (App Store, embeds Gyroflow Core)](https://apps.apple.com/us/app/gyroflow-toolbox/id1667462993?mt=12)
- [Python-in-Mac-App-Store reference project](https://github.com/davidfstr/Python-in-Mac-App-Store)
- [Exiv2 C++ metadata library](https://github.com/Exiv2/exiv2)
