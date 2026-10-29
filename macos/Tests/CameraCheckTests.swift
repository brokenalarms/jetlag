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

/// A profile is a camera and a kind of media, read from the card. These cover
/// what a card's probe means against the profiles there are: the card's camera
/// selects its profile, a camera without one is offered a new one built from the
/// card, and only media that records no camera leaves a profile to pick by hand.
final class CardProfilesTests: XCTestCase {

    private let a7vPhoto = MediaProfile(type: .photo, sourceDir: "/Volumes/Untitled/DCIM",
                                        exif: ExifConfig(make: "Sony", model: "ILCE-7M5"),
                                        fileExtensions: [".arw", ".jpg"])
    private let a7ivPhoto = MediaProfile(type: .photo, sourceDir: "/Volumes/Untitled/DCIM",
                                         exif: ExifConfig(make: "Sony", model: "ILCE-7M4"),
                                         fileExtensions: [".arw", ".jpg"])
    private let handNamed = MediaProfile(type: .video, sourceDir: "/Volumes/Untitled/DCIM",
                                         fileExtensions: [".mp4"])

    /// Setting AppState.profilesFilePath persists it to UserDefaults, which the
    /// test host shares with the Dev app: left behind, it points the app at a
    /// deleted temporary file.
    private var savedOverride: String?

    override func setUp() {
        super.setUp()
        savedOverride = UserDefaults.standard.string(forKey: "profilesFilePath")
    }

    override func tearDown() {
        if let savedOverride {
            UserDefaults.standard.set(savedOverride, forKey: "profilesFilePath")
        } else {
            UserDefaults.standard.removeObject(forKey: "profilesFilePath")
        }
        super.tearDown()
    }

    private func probe(_ ext: String, _ type: MediaType, _ folder: String,
                       _ make: String?, _ model: String?, files: Int = 10) -> ProbedCamera {
        ProbedCamera(fileExtension: ext, type: type, folder: folder, files: files,
                     camera: FileCamera(make: make, model: model))
    }

    /// The card's own camera picks its profile — never another body's profile
    /// reading the same folder, the mistake that relabelled 143 A7V stills.
    func testTheCardsCameraMatchesItsProfileIgnoringCase() {
        let contents = ProfileMatcher.contents(
            of: [probe(".arw", .photo, "/Volumes/CARD/DCIM", "SONY", "ILCE-7M5")],
            profiles: ["a7iv": a7ivPhoto, "a7v": a7vPhoto])

        XCTAssertEqual(contents.matched, [.init(profileName: "a7v", folder: "/Volumes/CARD/DCIM")])
        XCTAssertEqual(contents.newCameras, [])
    }

    /// A camera's photos and videos are separate kinds: a photo profile does not
    /// claim the same camera's video.
    func testTheSameCamerasVideoIsANewKind() {
        let contents = ProfileMatcher.contents(
            of: [probe(".mp4", .video, "/Volumes/CARD/PRIVATE", "SONY", "ILCE-7M5")],
            profiles: ["a7v": a7vPhoto])

        XCTAssertEqual(contents.matched, [])
        XCTAssertEqual(contents.newCameras.map(\.kind.defaultProfileName), ["SONY ILCE-7M5 Video"])
        XCTAssertEqual(contents.newCameras.first?.folder, "/Volumes/CARD/PRIVATE")
    }

    /// One new camera kind spread over several file types is one profile with
    /// all of them.
    func testOneCameraKindCollectsItsExtensions() {
        let contents = ProfileMatcher.contents(
            of: [probe(".arw", .photo, "/Volumes/CARD/DCIM", "SONY", "ILCE-7M5"),
                 probe(".jpg", .photo, "/Volumes/CARD/DCIM", "SONY", "ILCE-7M5", files: 3)],
            profiles: [:])

        XCTAssertEqual(contents.newCameras.count, 1)
        XCTAssertEqual(contents.newCameras.first?.extensions, [".arw", ".jpg"])
    }

    /// Only media that records no camera leaves a profile to be chosen by hand.
    func testMediaWithoutACameraIsReportedByFolder() {
        let contents = ProfileMatcher.contents(
            of: [probe(".mp4", .video, "/Volumes/CARD/DCIM", nil, nil)],
            profiles: ["hand": handNamed])

        XCTAssertEqual(contents.cameralessFolders, ["/Volumes/CARD/DCIM"])
        XCTAssertEqual(contents.matched, [])
    }

    /// Profiles made before a kind could only have one profile are flagged, not
    /// merged: which to keep is the user's call.
    func testProfilesSharingACameraKindAreFlagged() {
        let duplicates = ProfileMatcher.duplicates(in: ["a7v": a7vPhoto, "a7v-copy": a7vPhoto,
                                                        "a7iv": a7ivPhoto, "hand": handNamed])

        XCTAssertEqual(duplicates, ["a7v", "a7v-copy"])
    }

    /// A profile created for a camera found on a card takes everything it can
    /// from the card and is written to the profiles file; selecting it reads
    /// from the folder the card holds that camera's media in.
    func testCreatingAProfileFromACardSavesItAndReadsFromTheCard() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        let path = dir.appendingPathComponent("media-profiles.yaml").path

        let state = AppState()
        state.profilesFilePath = path
        state.profilesConfig = ProfilesConfig(gyroflow: nil, profiles: [:])
        state.cardProbes = [probe(".mp4", .video, "/Volumes/CARD/DCIM", "DJI", "Mini 4 Pro")]
        let found = try XCTUnwrap(state.cardContents.newCameras.first)

        let name = state.createProfile(for: found)
        state.selectProfile(name)

        XCTAssertEqual(name, "DJI Mini 4 Pro Video")
        let saved = try XCTUnwrap(try ProfileService.load(from: path).profiles[name])
        XCTAssertEqual(saved.exif, ExifConfig(make: "DJI", model: "Mini 4 Pro"))
        XCTAssertEqual(saved.type, .video)
        XCTAssertEqual(saved.fileExtensions, [".mp4"])
        XCTAssertEqual(state.cardContents.matched, [.init(profileName: name, folder: "/Volumes/CARD/DCIM")],
                       "The card now matches the profile made from it")
        XCTAssertEqual(state.workflowSession.profileName, name)
        XCTAssertEqual(state.workflowSession.sourceDir.current, "/Volumes/CARD/DCIM")
    }

    /// A card from a camera with a profile selects it, with no choice offered.
    func testACardSelectsItsProfile() {
        let state = AppState()
        state.profilesConfig = ProfilesConfig(gyroflow: nil, profiles: ["a7v": a7vPhoto, "a7iv": a7ivPhoto])
        state.cardProbes = [probe(".arw", .photo, "/Volumes/CARD/DCIM", "SONY", "ILCE-7M5")]

        state.selectProfileForCard()

        XCTAssertEqual(state.workflowSession.profileName, "a7v")
        XCTAssertEqual(state.workflowSession.sourceDir.current, "/Volumes/CARD/DCIM")
    }
}
