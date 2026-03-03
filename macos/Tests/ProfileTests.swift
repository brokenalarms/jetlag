import XCTest
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
            backupConfig: nil,
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

    func testRoundTripPreservesGyroflowAndBackupConfig() throws {
        let yaml = """
        gyroflow:
          binary: /usr/local/bin/gyroflow
          preset:
            stabilization:
              max_zoom: 105.0
              adaptive_zoom_window: 15.0
        backup_config:
          local_base_path: /Volumes/
          remote_base_path: /backup/
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
        XCTAssertEqual(config.backupConfig?.localBasePath, "/Volumes/")
        XCTAssertEqual(config.backupConfig?.remoteBasePath, "/backup/")

        try ProfileService.write(config, to: path)
        let reloaded = try ProfileService.load(from: path)

        XCTAssertEqual(reloaded.gyroflow?.binary, "/usr/local/bin/gyroflow")
        XCTAssertEqual(reloaded.backupConfig?.localBasePath, "/Volumes/")
        XCTAssertEqual(reloaded.profiles.count, 1)
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

    func testRenameProfile() throws {
        let path = writeTempYAML(fixtureYAML)
        var config = try ProfileService.load(from: path)

        let originalProfile = try XCTUnwrap(config.profiles["gopro"])
        config.profiles.removeValue(forKey: "gopro")
        config.profiles["gopro-hero-13"] = originalProfile

        try ProfileService.write(config, to: path)
        let reloaded = try ProfileService.load(from: path)

        XCTAssertEqual(reloaded.profiles.count, 2)
        XCTAssertNil(reloaded.profiles["gopro"])
        let renamed = try XCTUnwrap(reloaded.profiles["gopro-hero-13"])
        XCTAssertEqual(renamed.exif?.make, "GoPro")
        XCTAssertEqual(renamed.exif?.model, "HERO12 Black")
        XCTAssertEqual(renamed.type, .video)
    }

    func testPerProfileGyroflowSettingsRoundTrip() throws {
        let path = NSTemporaryDirectory() + UUID().uuidString + ".yaml"
        tempFiles.append(path)

        let original = ProfilesConfig(
            gyroflow: nil,
            backupConfig: nil,
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
            backupConfig: nil,
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
            backupConfig: nil,
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
            backupConfig: nil,
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
            backupConfig: nil,
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
            backupConfig: nil,
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
            backupConfig: nil,
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
}
