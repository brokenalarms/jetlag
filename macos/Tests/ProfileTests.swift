import XCTest
import Yams
@testable import Jetlag

final class ProfileTests: XCTestCase {

    private var tempFiles: [String] = []

    override func tearDown() {
        super.tearDown()
        for path in tempFiles {
            try? FileManager.default.removeItem(atPath: path)
        }
        tempFiles = []
    }

    // MARK: - Helpers

    private func writeTempYAML(_ content: String) -> String {
        let path = NSTemporaryDirectory() + UUID().uuidString + ".yaml"
        try! content.write(toFile: path, atomically: true, encoding: .utf8)
        tempFiles.append(path)
        return path
    }

    private let fixtureYAML = """
    profiles:
      gopro:
        type: video
        source_dir: /Volumes/Card/DCIM
        ready_dir: /tmp/ready
        gyroflow_enabled: true
        tags:
          - gopro-hero-12
        exif:
          make: GoPro
          model: HERO12 Black
        file_extensions:
          - .mp4
        companion_extensions:
          - .thm
      sony:
        type: photo
        source_dir: /Volumes/SonyCard/DCIM
        ready_dir: /tmp/photos
        tags:
          - sony-a7iv
        exif:
          make: Sony
          model: ILCE-7M4
        file_extensions:
          - .arw
    """

    // MARK: - Load

    func testLoadProfilesFromYAML() throws {
        let path = writeTempYAML(fixtureYAML)
        let config = try ProfileService.load(from: path)

        XCTAssertEqual(config.profiles.count, 2)

        let gopro = try XCTUnwrap(config.profiles["gopro"])
        XCTAssertEqual(gopro.type, .video)
        XCTAssertEqual(gopro.sourceDir, "/Volumes/Card/DCIM")
        XCTAssertEqual(gopro.readyDir, "/tmp/ready")
        XCTAssertEqual(gopro.gyroflowEnabled, true)
        XCTAssertEqual(gopro.exif?.make, "GoPro")
        XCTAssertEqual(gopro.exif?.model, "HERO12 Black")
        XCTAssertEqual(gopro.tags, ["gopro-hero-12"])
        XCTAssertEqual(gopro.fileExtensions, [".mp4"])
        XCTAssertEqual(gopro.companionExtensions, [".thm"])

        let sony = try XCTUnwrap(config.profiles["sony"])
        XCTAssertEqual(sony.type, .photo)
        XCTAssertEqual(sony.sourceDir, "/Volumes/SonyCard/DCIM")
        XCTAssertEqual(sony.exif?.make, "Sony")
        XCTAssertEqual(sony.exif?.model, "ILCE-7M4")
        XCTAssertEqual(sony.fileExtensions, [".arw"])
    }

    func testLoadNonexistentFileThrowsError() {
        let bogusPath = NSTemporaryDirectory() + "nonexistent-\(UUID().uuidString).yaml"

        do {
            _ = try ProfileService.load(from: bogusPath)
            XCTFail("Expected ProfileLoadError for missing file")
        } catch let error as ProfileLoadError {
            XCTAssertEqual(error.message, "Profiles file not found")
            XCTAssertTrue(error.filePath.contains("nonexistent-"))
        } catch {
            XCTFail("Unexpected error type: \(error)")
        }
    }

    func testLoadMalformedYAMLThrowsError() {
        let path = writeTempYAML("profiles:\n  bad:\n    type: [not a string")

        do {
            _ = try ProfileService.load(from: path)
            XCTFail("Expected error for malformed YAML")
        } catch is ProfileLoadError {
            // expected
        } catch {
            XCTFail("Unexpected error type: \(error)")
        }
    }

    // MARK: - Write and round-trip

    func testWriteAndRereadProfiles() throws {
        let path = NSTemporaryDirectory() + UUID().uuidString + ".yaml"
        tempFiles.append(path)

        let original = ProfilesConfig(
            gyroflow: nil,
            profiles: [
                "test-cam": MediaProfile(
                    type: .video,
                    sourceDir: "/tmp/source",
                    readyDir: "/tmp/ready",
                    gyroflowEnabled: false,
                    tags: ["test"],
                    exif: ExifConfig(make: "TestMake", model: "TestModel"),
                    fileExtensions: [".mp4", ".mov"]
                )
            ]
        )

        try ProfileService.write(original, to: path)
        let loaded = try ProfileService.load(from: path)

        XCTAssertEqual(loaded.profiles.count, 1)
        let profile = try XCTUnwrap(loaded.profiles["test-cam"])
        XCTAssertEqual(profile.type, .video)
        XCTAssertEqual(profile.sourceDir, "/tmp/source")
        XCTAssertEqual(profile.readyDir, "/tmp/ready")
        XCTAssertEqual(profile.exif?.make, "TestMake")
        XCTAssertEqual(profile.exif?.model, "TestModel")
        XCTAssertEqual(profile.tags, ["test"])
        XCTAssertEqual(profile.fileExtensions, [".mp4", ".mov"])
    }

    func testRoundTripPreservesGyroflow() throws {
        let yaml = """
        gyroflow:
          binary: /usr/local/bin/gyroflow
          preset:
            stabilization:
              max_zoom: 105.0
              adaptive_zoom_window: 15.0
        profiles:
          cam:
            type: video
            file_extensions:
              - .mp4
        """

        let path = writeTempYAML(yaml)
        let config = try ProfileService.load(from: path)

        XCTAssertEqual(config.gyroflow?.binary, "/usr/local/bin/gyroflow")
        XCTAssertEqual(config.gyroflow?.preset?.stabilization?.maxZoom, 105.0)

        try ProfileService.write(config, to: path)
        let reloaded = try ProfileService.load(from: path)

        XCTAssertEqual(reloaded.gyroflow?.binary, "/usr/local/bin/gyroflow")
        XCTAssertEqual(reloaded.profiles.count, 1)
    }

    /// The app models only the keys it edits. A save used to re-encode the model,
    /// which deleted every other key the scripts read (a profile's
    /// `folder_template`) and copied the global stabilization preset into each
    /// gyroflow profile, so a later change to the preset no longer reached it.
    /// Saving one edited field now leaves everything else in the file as it was.
    func testSavingAnEditKeepsWhatTheAppDoesNotModel() throws {
        let yaml = """
        gyroflow:
          binary: /usr/local/bin/gyroflow
          preset:
            stabilization:
              max_zoom: 105.0
              adaptive_zoom_window: 15.0
              adaptive_zoom_method: 1
            smoothing: 0.5
        archive_root: /Volumes/Archive
        profiles:
          gopro:
            type: video
            source_dir: /Volumes/Card/DCIM
            ready_dir: /tmp/ready
            gyroflow_enabled: true
            folder_template: '{{YYYY}}/{{GROUP}}/{{YYYY-MM-DD}}'
            file_extensions:
            - .mp4
          sony:
            type: photo
            source_dir: /Volumes/SonyCard/DCIM
            ready_dir: /tmp/photos
            notes: kept as written
            file_extensions:
            - .arw
        """
        let path = writeTempYAML(yaml)
        let config = try ProfileService.load(from: path)

        // The editor shows the preset filled in; only the ready folder is changed.
        var edited = try XCTUnwrap(config.profile(named: "gopro"))
        XCTAssertEqual(edited.gyroflowSettings?.maxZoom, 105.0)
        edited.readyDir = "/tmp/new-ready"
        var saved = config
        try saved.save(edited, as: "gopro", replacing: "gopro")
        try ProfileService.write(saved, to: path)

        let written = try XCTUnwrap(try Yams.compose(yaml: String(contentsOfFile: path, encoding: .utf8)))
        let expected = try XCTUnwrap(try Yams.compose(yaml: yaml.replacingOccurrences(
            of: "ready_dir: /tmp/ready", with: "ready_dir: /tmp/new-ready")))
        XCTAssertNil(written["profiles"]?["gopro"]?["gyroflow_settings"],
                     "the global preset must not be copied into the profile")
        XCTAssertEqual(written["profiles"]?["gopro"]?["folder_template"]?.string,
                       "{{YYYY}}/{{GROUP}}/{{YYYY-MM-DD}}")
        XCTAssertEqual(written["profiles"]?["sony"]?["notes"]?.string, "kept as written")
        XCTAssertEqual(written["archive_root"]?.string, "/Volumes/Archive")
        XCTAssertEqual(written["gyroflow"]?["preset"]?["smoothing"]?.float, 0.5)
        // Everything else — every key, value and the file's order — is unchanged.
        XCTAssertEqual(written, expected)
    }

    /// A stabilization value the user changed is the profile's own and is stored;
    /// the ones left at the preset's still follow the preset.
    func testSaveKeepsOnlyTheStabilizationValuesTheUserChanged() throws {
        var config = ProfilesConfig(
            gyroflow: GyroflowConfig(
                binary: nil,
                preset: GyroflowPreset(stabilization: StabilizationSettings(
                    maxZoom: 105.0, adaptiveZoomWindow: 15.0, adaptiveZoomMethod: 1))),
            profiles: ["gopro": MediaProfile(type: .video, gyroflowEnabled: true, fileExtensions: [".mp4"])]
        )
        var edited = try XCTUnwrap(config.profile(named: "gopro"))
        edited.gyroflowSettings?.maxZoom = 120.0

        try config.save(edited, as: "gopro", replacing: "gopro")

        XCTAssertEqual(config.profiles["gopro"]?.gyroflowSettings, StabilizationSettings(maxZoom: 120.0))
    }

    // MARK: - CRUD operations

    func testAddProfile() throws {
        let path = writeTempYAML(fixtureYAML)
        var config = try ProfileService.load(from: path)

        config.profiles["dji"] = MediaProfile(
            type: .video,
            tags: ["dji-mini"],
            exif: ExifConfig(make: "DJI", model: "Mini 4 Pro"),
            fileExtensions: [".mp4"]
        )

        try ProfileService.write(config, to: path)
        let reloaded = try ProfileService.load(from: path)

        XCTAssertEqual(reloaded.profiles.count, 3)
        XCTAssertNotNil(reloaded.profiles["gopro"])
        XCTAssertNotNil(reloaded.profiles["sony"])
        let dji = try XCTUnwrap(reloaded.profiles["dji"])
        XCTAssertEqual(dji.exif?.make, "DJI")
        XCTAssertEqual(dji.exif?.model, "Mini 4 Pro")
        XCTAssertEqual(dji.fileExtensions, [".mp4"])
    }

    func testUpdateProfile() throws {
        let path = writeTempYAML(fixtureYAML)
        var config = try ProfileService.load(from: path)

        config.profiles["gopro"]?.readyDir = "/tmp/new-ready"
        config.profiles["gopro"]?.tags = ["gopro-hero-13"]

        try ProfileService.write(config, to: path)
        let reloaded = try ProfileService.load(from: path)

        let gopro = try XCTUnwrap(reloaded.profiles["gopro"])
        XCTAssertEqual(gopro.readyDir, "/tmp/new-ready")
        XCTAssertEqual(gopro.tags, ["gopro-hero-13"])
        XCTAssertEqual(gopro.exif?.make, "GoPro")
    }

    func testDeleteProfile() throws {
        let path = writeTempYAML(fixtureYAML)
        var config = try ProfileService.load(from: path)

        config.profiles.removeValue(forKey: "gopro")

        try ProfileService.write(config, to: path)
        let reloaded = try ProfileService.load(from: path)

        XCTAssertEqual(reloaded.profiles.count, 1)
        XCTAssertNil(reloaded.profiles["gopro"])
        XCTAssertNotNil(reloaded.profiles["sony"])
    }

    /// An app state reading `yaml` as its profiles file, in a temporary directory.
    private func stateLoaded(from yaml: String) throws -> AppState {
        let dir = NSTemporaryDirectory() + UUID().uuidString
        try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        tempFiles.append(dir)
        let location = ProfilesLocation(directory: dir, seedPath: "")
        try yaml.write(toFile: location.path, atomically: true, encoding: .utf8)
        let state = AppState(profilesLocation: location)
        state.loadProfiles()
        return state
    }

    /// Renaming goes through the same save the editor uses: the profile moves
    /// to its new name in the file, and a workflow that had it selected follows.
    func testRenameProfile() throws {
        let state = try stateLoaded(from: fixtureYAML)
        let gopro = try XCTUnwrap(state.profile(named: "gopro"))
        state.workflowSession = WorkflowSession(profile: gopro, profileName: "gopro")

        try state.saveProfile(gopro, as: "gopro-hero-13", replacing: "gopro")

        let reloaded = try ProfileService.load(from: state.profilesLocation.path)
        XCTAssertEqual(reloaded.profiles.count, 2)
        XCTAssertNil(reloaded.profiles["gopro"])
        let renamed = try XCTUnwrap(reloaded.profiles["gopro-hero-13"])
        XCTAssertEqual(renamed.exif?.make, "GoPro")
        XCTAssertEqual(renamed.exif?.model, "HERO12 Black")
        XCTAssertEqual(renamed.type, .video)
        XCTAssertEqual(state.workflowSession.profileName, "gopro-hero-13")
    }

    /// Saving under a name another profile already had used to replace that
    /// profile without a word. The save is refused with the reason, and the file
    /// keeps both profiles as they were.
    func testSavingOntoAnotherProfilesNameIsRefused() throws {
        let state = try stateLoaded(from: fixtureYAML)
        let gopro = try XCTUnwrap(state.profile(named: "gopro"))

        XCTAssertThrowsError(try state.saveProfile(gopro, as: "sony", replacing: "gopro")) { error in
            XCTAssertEqual(error as? ProfileNameError, .taken("sony"))
        }
        XCTAssertThrowsError(try state.saveProfile(MediaProfile(type: .video), as: "gopro", replacing: nil)) { error in
            XCTAssertEqual(error as? ProfileNameError, .taken("gopro"))
        }

        let reloaded = try ProfileService.load(from: state.profilesLocation.path)
        XCTAssertEqual(reloaded.profiles["sony"]?.exif?.make, "Sony")
        XCTAssertEqual(reloaded.profiles["gopro"]?.exif?.make, "GoPro")
        XCTAssertEqual(state.profile(named: "sony")?.exif?.make, "Sony")
    }

    /// New and copied profiles get the first free name, so starting one never
    /// lands on a profile that already exists.
    func testUniqueNameCountsUpFromTwo() {
        let config = ProfilesConfig(gyroflow: nil, profiles: [
            "cam": MediaProfile(type: .video), "cam 2": MediaProfile(type: .video),
        ])
        XCTAssertEqual(config.uniqueName("cam"), "cam 3")
        XCTAssertEqual(config.uniqueName("other"), "other")
    }

    func testPerProfileGyroflowSettingsRoundTrip() throws {
        let path = NSTemporaryDirectory() + UUID().uuidString + ".yaml"
        tempFiles.append(path)

        let original = ProfilesConfig(
            gyroflow: nil,
            profiles: [
                "gopro": MediaProfile(
                    type: .video,
                    gyroflowEnabled: true,
                    gyroflowSettings: StabilizationSettings(
                        maxZoom: 120.0,
                        adaptiveZoomWindow: 25.0,
                        adaptiveZoomMethod: 2
                    ),
                    fileExtensions: [".mp4"]
                )
            ]
        )

        try ProfileService.write(original, to: path)
        let loaded = try ProfileService.load(from: path)

        let gopro = try XCTUnwrap(loaded.profiles["gopro"])
        XCTAssertEqual(gopro.gyroflowEnabled, true)
        XCTAssertEqual(gopro.gyroflowSettings?.maxZoom, 120.0)
        XCTAssertEqual(gopro.gyroflowSettings?.adaptiveZoomWindow, 25.0)
        XCTAssertEqual(gopro.gyroflowSettings?.adaptiveZoomMethod, 2)
    }

    func testPhotoProfileHasNoGyroflowSettings() throws {
        let path = writeTempYAML(fixtureYAML)
        let config = try ProfileService.load(from: path)

        let sony = try XCTUnwrap(config.profiles["sony"])
        XCTAssertEqual(sony.type, .photo)
        XCTAssertNil(sony.gyroflowEnabled)
        XCTAssertNil(sony.gyroflowSettings)
    }

    // MARK: - Normalization

    func testNormalizedPopulatesNilSettingsFromGlobal() {
        let config = ProfilesConfig(
            gyroflow: GyroflowConfig(
                binary: nil,
                preset: GyroflowPreset(
                    stabilization: StabilizationSettings(
                        maxZoom: 105.0,
                        adaptiveZoomWindow: 15.0,
                        adaptiveZoomMethod: 1
                    )
                )
            ),
            profiles: [
                "gopro": MediaProfile(type: .video, gyroflowEnabled: true, fileExtensions: [".mp4"])
            ]
        )

        let normalized = config.normalized()
        let gopro = normalized.profiles["gopro"]!
        XCTAssertEqual(gopro.gyroflowSettings?.maxZoom, 105.0)
        XCTAssertEqual(gopro.gyroflowSettings?.adaptiveZoomWindow, 15.0)
        XCTAssertEqual(gopro.gyroflowSettings?.adaptiveZoomMethod, 1)
    }

    func testNormalizedFillsPartialSettingsFromGlobal() {
        let config = ProfilesConfig(
            gyroflow: GyroflowConfig(
                binary: nil,
                preset: GyroflowPreset(
                    stabilization: StabilizationSettings(
                        maxZoom: 105.0,
                        adaptiveZoomWindow: 15.0,
                        adaptiveZoomMethod: 1
                    )
                )
            ),
            profiles: [
                "gopro": MediaProfile(
                    type: .video,
                    gyroflowEnabled: true,
                    gyroflowSettings: StabilizationSettings(maxZoom: 120.0),
                    fileExtensions: [".mp4"]
                )
            ]
        )

        let normalized = config.normalized()
        let gopro = normalized.profiles["gopro"]!
        XCTAssertEqual(gopro.gyroflowSettings?.maxZoom, 120.0)
        XCTAssertEqual(gopro.gyroflowSettings?.adaptiveZoomWindow, 15.0)
        XCTAssertEqual(gopro.gyroflowSettings?.adaptiveZoomMethod, 1)
    }

    func testNormalizedPreservesExplicitSettings() {
        let config = ProfilesConfig(
            gyroflow: GyroflowConfig(
                binary: nil,
                preset: GyroflowPreset(
                    stabilization: StabilizationSettings(
                        maxZoom: 105.0,
                        adaptiveZoomWindow: 15.0,
                        adaptiveZoomMethod: 1
                    )
                )
            ),
            profiles: [
                "gopro": MediaProfile(
                    type: .video,
                    gyroflowEnabled: true,
                    gyroflowSettings: StabilizationSettings(
                        maxZoom: 120.0,
                        adaptiveZoomWindow: 25.0,
                        adaptiveZoomMethod: 2
                    ),
                    fileExtensions: [".mp4"]
                )
            ]
        )

        let normalized = config.normalized()
        let gopro = normalized.profiles["gopro"]!
        XCTAssertEqual(gopro.gyroflowSettings?.maxZoom, 120.0)
        XCTAssertEqual(gopro.gyroflowSettings?.adaptiveZoomWindow, 25.0)
        XCTAssertEqual(gopro.gyroflowSettings?.adaptiveZoomMethod, 2)
    }

    func testNormalizedSkipsNonGyroflowProfiles() {
        let config = ProfilesConfig(
            gyroflow: GyroflowConfig(
                binary: nil,
                preset: GyroflowPreset(
                    stabilization: StabilizationSettings(maxZoom: 105.0)
                )
            ),
            profiles: [
                "sony": MediaProfile(type: .photo, fileExtensions: [".arw"])
            ]
        )

        let normalized = config.normalized()
        let sony = normalized.profiles["sony"]!
        XCTAssertNil(sony.gyroflowSettings)
    }

    func testNormalizedWithNoGlobalConfig() {
        let config = ProfilesConfig(
            gyroflow: nil,
            profiles: [
                "gopro": MediaProfile(type: .video, gyroflowEnabled: true, fileExtensions: [".mp4"])
            ]
        )

        let normalized = config.normalized()
        let gopro = normalized.profiles["gopro"]!
        XCTAssertNotNil(gopro.gyroflowSettings)
        XCTAssertNil(gopro.gyroflowSettings?.maxZoom)
        XCTAssertNil(gopro.gyroflowSettings?.adaptiveZoomWindow)
        XCTAssertNil(gopro.gyroflowSettings?.adaptiveZoomMethod)
    }

    // MARK: - Selection independence

    func testProfileSelectionIndependence() {
        let state = AppState()
        state.profilesConfig = ProfilesConfig(
            gyroflow: nil,
            profiles: [
                "gopro": MediaProfile(type: .video),
                "sony": MediaProfile(type: .photo)
            ]
        )

        state.workflowSession = WorkflowSession(
            profile: state.profilesConfig?.profiles["gopro"],
            profileName: "gopro"
        )
        XCTAssertNotNil(state.activeProfile)
        XCTAssertEqual(state.activeProfile?.type, .video)

        state.workflowSession = WorkflowSession(
            profile: state.profilesConfig?.profiles["sony"],
            profileName: "sony"
        )
        XCTAssertNotNil(state.activeProfile)
        XCTAssertEqual(state.activeProfile?.type, .photo)

        state.workflowSession = WorkflowSession()
        XCTAssertNil(state.activeProfile)

        state.workflowSession = WorkflowSession(
            profile: state.profilesConfig?.profiles["gopro"],
            profileName: "gopro"
        )
        state.profilesConfig?.profiles["dji"] = MediaProfile(type: .video)
        XCTAssertEqual(state.workflowSession.profileName, "gopro")
        XCTAssertNotNil(state.activeProfile)
    }

    /// Every visit to the Workflow tab used to rebuild its session from the
    /// profile, dropping the timezone the user had chosen. Only picking another
    /// profile starts afresh now; picking the one already selected keeps it.
    func testReselectingTheSameProfileKeepsTheChosenTimezone() throws {
        let state = try stateLoaded(from: fixtureYAML)
        state.selectProfile("gopro")
        state.workflowSession.timezone.value = "Asia/Seoul"

        state.selectProfile("gopro")

        XCTAssertEqual(state.workflowSession.timezone.current, "Asia/Seoul")
    }

    /// Another profile is another camera and card: its own folders, and no zone
    /// carried over from the last one.
    func testSelectingAnotherProfileStartsAFreshSession() throws {
        let state = try stateLoaded(from: fixtureYAML)
        state.selectProfile("gopro")
        state.workflowSession.timezone.value = "Asia/Seoul"

        state.selectProfile("sony")

        XCTAssertEqual(state.workflowSession.profileName, "sony")
        XCTAssertEqual(state.workflowSession.sourceDir.current, "/Volumes/SonyCard/DCIM")
        XCTAssertEqual(state.workflowSession.timezone.current, "")
    }

    /// The workflow runs the profile as saved: editing the selected profile
    /// rebuilds its session from the saved values.
    func testSavingTheSelectedProfileRebuildsTheWorkflow() throws {
        let state = try stateLoaded(from: fixtureYAML)
        state.selectProfile("gopro")
        var edited = try XCTUnwrap(state.profile(named: "gopro"))
        edited.readyDir = "/tmp/new-ready"

        try state.saveProfile(edited, as: "gopro", replacing: "gopro")

        XCTAssertEqual(state.workflowSession.readyDir.current, "/tmp/new-ready")
    }

    /// Closing Settings reloads the profiles file. A profile the app itself saved
    /// is read back as it was saved, so the workflow keeps every choice made since
    /// — the save is not mistaken for a change made to the file outside the app.
    func testReloadingAfterTheAppsOwnSaveKeepsTheWorkflow() throws {
        let state = try stateLoaded(from: fixtureYAML)
        state.selectProfile("gopro")
        var edited = try XCTUnwrap(state.profile(named: "gopro"))
        edited.readyDir = "/tmp/new-ready"
        try state.saveProfile(edited, as: "gopro", replacing: "gopro")
        state.workflowSession.timezone.value = "Asia/Seoul"

        state.loadProfiles()

        XCTAssertEqual(state.workflowSession.timezone.current, "Asia/Seoul")
    }

    /// A profile changed in the file outside the app is what the workflow runs
    /// after a reload.
    func testReloadingAProfileChangedInTheFileRebuildsTheWorkflow() throws {
        let state = try stateLoaded(from: fixtureYAML)
        state.selectProfile("gopro")
        try fixtureYAML.replacingOccurrences(of: "ready_dir: /tmp/ready", with: "ready_dir: /tmp/elsewhere")
            .write(toFile: state.profilesLocation.path, atomically: true, encoding: .utf8)

        state.loadProfiles()

        XCTAssertEqual(state.workflowSession.readyDir.current, "/tmp/elsewhere")
    }

    // MARK: - Save and Cancel visibility

    /// Save and Cancel used to show on every profile, edited or not, so clicking Save
    /// gave no sign anything happened. They now show only while there is something to
    /// save, and their disappearing is the confirmation.
    func testSavedProfileWithNoEditsHasNothingToSave() {
        let session = ProfileEditingSession(name: "gopro", profile: MediaProfile(type: .video))
        XCTAssertFalse(ProfileEditingSession.hasUnsavedChanges(editor: session, snapshot: session, isSaved: true))
    }

    func testEditedProfileHasUnsavedChanges() {
        let snapshot = ProfileEditingSession(name: "gopro", profile: MediaProfile(type: .video))
        var edited = snapshot
        edited.profile.type = .photo
        XCTAssertTrue(ProfileEditingSession.hasUnsavedChanges(editor: edited, snapshot: snapshot, isSaved: true))
    }

    /// A new or duplicated profile matches its snapshot but has never been written,
    /// so it must still be savable without first editing it.
    func testUnwrittenProfileHasUnsavedChangesEvenUnedited() {
        let session = ProfileEditingSession(name: "new-profile", profile: MediaProfile(type: .video))
        XCTAssertTrue(ProfileEditingSession.hasUnsavedChanges(editor: session, snapshot: session, isSaved: false))
    }

    // MARK: - canSave

    private func completeSession() -> ProfileEditingSession {
        ProfileEditingSession(
            name: "gopro",
            profile: MediaProfile(type: .video, sourceDir: "/media/in", fileExtensions: [".mp4"]))
    }

    /// Save is offered only for a profile the pipeline will accept.
    func testCompleteProfileCanSave() {
        XCTAssertTrue(completeSession().canSave)
    }

    func testProfileWithoutNameCannotSave() {
        var session = completeSession()
        session.name = ""
        XCTAssertFalse(session.canSave)
    }

    func testProfileWithWhitespaceOnlyNameCannotSave() {
        var session = completeSession()
        session.name = "   "
        XCTAssertFalse(session.canSave)
    }

    func testProfileWithoutTypeCannotSave() {
        var session = completeSession()
        session.profile.type = nil
        XCTAssertFalse(session.canSave)
    }

    func testProfileWithoutSourceDirCannotSave() {
        var session = completeSession()
        session.profile.sourceDir = nil
        XCTAssertFalse(session.canSave)
        session.profile.sourceDir = "  "
        XCTAssertFalse(session.canSave)
    }

    func testProfileWithoutFileTypesCannotSave() {
        var session = completeSession()
        session.profile.fileExtensions = nil
        XCTAssertFalse(session.canSave)
        session.profile.fileExtensions = []
        XCTAssertFalse(session.canSave)
    }
}
