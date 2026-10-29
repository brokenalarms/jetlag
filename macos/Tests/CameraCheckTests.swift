import XCTest
@testable import Jetlag

/// Covers holding every import to its profile's camera. The pipeline reports
/// files shot on another camera as one `camera_mismatch` event: a dry run records
/// it and previews, an apply is refused and asks, and the answer re-runs the apply
/// with --allow-camera-mismatch.
final class CameraCheckTests: XCTestCase {

    private let mismatchEvent = #"""
    {"event": "camera_mismatch", "files": ["DJI_0003_D.MP4", "DJI_0004_D.MP4"], "expected_make": "Insta360", "expected_model": "X4", "found_makes": ["DJI"], "found_models": ["Mini 4 Pro"]}
    """#

    private func feed(_ state: AppState, _ json: String) {
        state.appendLog(LogLine(text: json, stream: .stdout))
    }

    /// The files, the profile's camera and what the files carry arrive as data;
    /// the alert and the dry-run summary compose their message from them.
    func testMismatchEventDecodesIntoStructuredState() {
        let state = AppState()

        feed(state, mismatchEvent)

        let mismatch = state.workflowSession.cameraMismatch
        XCTAssertEqual(mismatch?.files, ["DJI_0003_D.MP4", "DJI_0004_D.MP4"])
        XCTAssertEqual(mismatch?.expected, FileCamera(make: "Insta360", model: "X4"))
        XCTAssertEqual(mismatch?.foundName, "DJI, Mini 4 Pro")
    }

    /// A preview is not refused, so it is not interrupted either.
    func testDryRunRecordsTheMismatchWithoutAsking() {
        let state = AppState()
        state.workflowSession.applyMode = false

        feed(state, mismatchEvent)

        XCTAssertFalse(state.workflowSession.showCameraMismatch)
        XCTAssertNotNil(state.workflowSession.cameraMismatch)
    }

    /// The refused apply has already reset to preview mode when the answer
    /// arrives; the re-run must still be the apply, carrying the flag.
    func testAssentReRunsTheRefusedApplyWithTheFlag() {
        let state = AppState()
        state.workflowSession.applyMode = true
        feed(state, mismatchEvent)
        XCTAssertTrue(state.workflowSession.showCameraMismatch)
        state.workflowSession.noteRunFinished()

        state.workflowSession.grantCameraMismatchAssent()

        let (_, args) = state.workflowSession.buildPipelineArgs()
        XCTAssertTrue(args.contains("--allow-camera-mismatch"))
        XCTAssertTrue(args.contains("--apply"))
    }

    /// Assent covers the run it was given for: the next card is checked again.
    func testStartingAFreshRunDropsEarlierAssent() {
        let state = AppState()
        state.workflowSession.applyMode = true
        feed(state, mismatchEvent)
        state.workflowSession.grantCameraMismatchAssent()

        state.workflowSession.clearRunAssent()

        let (_, args) = state.workflowSession.buildPipelineArgs()
        XCTAssertFalse(args.contains("--allow-camera-mismatch"))
        XCTAssertNil(state.workflowSession.cameraMismatch)
    }

    /// An override is an answer for one click, not a setting: it never makes a
    /// preview look stale.
    func testAssentDoesNotMakeAPreviewStale() {
        let session = WorkflowSession(profile: MediaProfile(type: .video), profileName: "p")
        let before = session.comparableArgs()

        session.allowCameraMismatch = true

        XCTAssertEqual(session.comparableArgs(), before)
    }
}

/// A profile is a camera and a kind of media, filled in from the source folder
/// chosen when it is created. These cover what that folder holds against the
/// profiles there are: a camera with a profile opens it, a camera without one
/// gets a new profile built from the folder, and media that records no camera
/// starts one named by hand.
final class NewProfileFromSourceTests: XCTestCase {

    private let a7vPhoto = MediaProfile(type: .photo, sourceDir: "/Volumes/Untitled/DCIM",
                                        exif: ExifConfig(make: "Sony", model: "ILCE-7M5"),
                                        fileExtensions: [".arw", ".jpg"])
    private let a7ivPhoto = MediaProfile(type: .photo, sourceDir: "/Volumes/Untitled/DCIM",
                                         exif: ExifConfig(make: "Sony", model: "ILCE-7M4"),
                                         fileExtensions: [".arw", ".jpg"])
    private let handNamed = MediaProfile(type: .video, sourceDir: "/Volumes/Untitled/DCIM",
                                         fileExtensions: [".mp4"])

    private func probe(_ ext: String, _ type: MediaType, _ make: String?, _ model: String?,
                       files: Int = 10) -> ProbedCamera {
        ProbedCamera(fileExtension: ext, type: type, files: files, camera: FileCamera(make: make, model: model))
    }

    /// A camera that already has a profile is that profile, not a second one —
    /// and never another body's profile reading the same folder.
    func testACameraWithAProfileFindsItIgnoringCase() {
        let contents = ProfileMatcher.contents(
            of: [probe(".arw", .photo, "SONY", "ILCE-7M5")], source: "/Volumes/Untitled/DCIM",
            profiles: ["a7iv": a7ivPhoto, "a7v": a7vPhoto])

        XCTAssertEqual(contents.existingProfiles, ["a7v"])
        XCTAssertEqual(contents.newCameras, [])
    }

    /// A camera's photos and videos are separate kinds: a photo profile does not
    /// claim the same camera's video.
    func testTheSameCamerasVideoIsANewKind() {
        let contents = ProfileMatcher.contents(
            of: [probe(".mp4", .video, "SONY", "ILCE-7M5")], source: "/Volumes/Untitled/PRIVATE",
            profiles: ["a7v": a7vPhoto])

        XCTAssertEqual(contents.existingProfiles, [])
        XCTAssertEqual(contents.newCameras.map(\.kind.defaultProfileName), ["SONY ILCE-7M5 Video"])
        XCTAssertEqual(contents.newCameras.first?.source, "/Volumes/Untitled/PRIVATE")
    }

    /// One new camera kind spread over several file types is one profile with
    /// all of them.
    func testOneCameraKindCollectsItsExtensions() {
        let contents = ProfileMatcher.contents(
            of: [probe(".arw", .photo, "SONY", "ILCE-7M5"), probe(".jpg", .photo, "SONY", "ILCE-7M5", files: 3)],
            source: "/Volumes/Untitled/DCIM", profiles: [:])

        XCTAssertEqual(contents.newCameras.count, 1)
        XCTAssertEqual(contents.newCameras.first?.extensions, [".arw", ".jpg"])
    }

    /// Media that records no camera has nothing to fill in: its profile is named
    /// by hand.
    func testMediaWithoutACameraIsReported() {
        let contents = ProfileMatcher.contents(
            of: [probe(".mp4", .video, nil, nil)], source: "/Volumes/Untitled/DCIM",
            profiles: ["hand": handNamed])

        XCTAssertTrue(contents.hasCameralessMedia)
        XCTAssertEqual(contents.existingProfiles, [])
        XCTAssertEqual(contents.newCameras, [])
    }

    /// Profiles made before a kind could only have one profile are flagged, not
    /// merged: which to keep is the user's call.
    func testProfilesSharingACameraKindAreFlagged() {
        let duplicates = ProfileMatcher.duplicates(in: ["a7v": a7vPhoto, "a7v-copy": a7vPhoto,
                                                        "a7iv": a7ivPhoto, "hand": handNamed])

        XCTAssertEqual(duplicates, ["a7v", "a7v-copy"])
    }

    /// A profile created from the source chosen for it takes its camera, kind and
    /// file types from that source's files, keeps that source exactly, and is
    /// written to the profiles file.
    func testCreatingAProfileFromASourceSavesIt() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        let location = ProfilesLocation(directory: dir.path, seedPath: "")
        let path = location.path

        let state = AppState(profilesLocation: location)
        state.profilesConfig = ProfilesConfig(gyroflow: nil, profiles: [:])
        let found = try XCTUnwrap(ProfileMatcher.contents(
            of: [probe(".mp4", .video, "DJI", "Mini 4 Pro")], source: "/Volumes/Untitled/DCIM",
            profiles: [:]).newCameras.first)

        let name = state.createProfile(for: found)

        XCTAssertEqual(name, "DJI Mini 4 Pro Video")
        let saved = try XCTUnwrap(try ProfileService.load(from: path).profiles[name])
        XCTAssertEqual(saved.exif, ExifConfig(make: "DJI", model: "Mini 4 Pro"))
        XCTAssertEqual(saved.type, .video)
        XCTAssertEqual(saved.fileExtensions, [".mp4"])
        XCTAssertEqual(saved.sourceDir, "/Volumes/Untitled/DCIM")
    }
}
