import XCTest
@testable import Jetlag

/// The profiles file the app writes has to outlive a rebuild of the app, so it
/// cannot live inside the bundle: the "Bundle scripts" build phase replaces the
/// bundled copy every build, and a signed installed app cannot write into its
/// own bundle at all.
final class ProfilesLocationTests: XCTestCase {

    private var savedOverride: String?

    override func setUp() {
        super.setUp()
        savedOverride = UserDefaults.standard.string(forKey: "profilesFilePath")
        UserDefaults.standard.removeObject(forKey: "profilesFilePath")
    }

    override func tearDown() {
        if let savedOverride {
            UserDefaults.standard.set(savedOverride, forKey: "profilesFilePath")
        } else {
            UserDefaults.standard.removeObject(forKey: "profilesFilePath")
        }
        super.tearDown()
    }

    /// With no Settings override the app reads and writes the user-owned copy in
    /// Application Support — never the read-only copy inside the app bundle.
    func testDefaultProfilesPathIsInApplicationSupportNotTheBundle() {
        let state = AppState()

        let expected = (NSHomeDirectory() as NSString)
            .appendingPathComponent("Library/Application Support/Jetlag/media-profiles.yaml")
        XCTAssertEqual(state.resolvedProfilesPath, expected)
        XCTAssertFalse(state.resolvedProfilesPath.hasPrefix(state.scriptsDirectory),
                       "profiles must never resolve into the app bundle's scripts directory")
    }

    /// The Settings override is how a developer points the app at the repo's
    /// checked-in profiles file; a non-empty override still wins outright.
    func testSettingsOverrideWins() {
        let state = AppState()
        state.profilesFilePath = "/tmp/jetlag-override/media-profiles.yaml"

        XCTAssertEqual(state.resolvedProfilesPath, "/tmp/jetlag-override/media-profiles.yaml")
    }

    /// First launch has no profiles file, so the shipped defaults are copied out
    /// of the bundle into a directory created for them.
    func testFirstLaunchSeedsTheBundledDefaults() throws {
        let temp = try makeTemporaryDirectory()
        let seed = temp.appendingPathComponent("bundled.yaml")
        try "profiles:\n  shipped: {}\n".write(to: seed, atomically: true, encoding: .utf8)
        let location = ProfilesLocation(
            directory: temp.appendingPathComponent("Application Support/Jetlag").path,
            seedPath: seed.path
        )

        XCTAssertFalse(FileManager.default.fileExists(atPath: location.path))
        XCTAssertTrue(try location.seedIfNeeded())

        XCTAssertEqual(try String(contentsOfFile: location.path, encoding: .utf8),
                       "profiles:\n  shipped: {}\n")
    }

    /// The seeded file belongs to the user from then on: a later launch — or a
    /// rebuild that replaces the bundled copy — never writes over their edits.
    func testSeedingNeverOverwritesAnExistingFile() throws {
        let temp = try makeTemporaryDirectory()
        let seed = temp.appendingPathComponent("bundled.yaml")
        try "profiles:\n  shipped: {}\n".write(to: seed, atomically: true, encoding: .utf8)
        let location = ProfilesLocation(
            directory: temp.appendingPathComponent("Application Support/Jetlag").path,
            seedPath: seed.path
        )
        XCTAssertTrue(try location.seedIfNeeded())

        let edited = "profiles:\n  edited-by-the-user: {}\n"
        try edited.write(toFile: location.path, atomically: true, encoding: .utf8)
        try "profiles:\n  replaced-by-a-rebuild: {}\n"
            .write(to: seed, atomically: true, encoding: .utf8)

        XCTAssertFalse(try location.seedIfNeeded())
        XCTAssertEqual(try String(contentsOfFile: location.path, encoding: .utf8), edited)
    }

    /// The pipeline has to read the profiles the app writes, so every script the
    /// app launches is told where that file is rather than defaulting to the
    /// read-only copy beside the scripts in the bundle.
    func testLaunchedScriptsAreToldWhereTheProfilesFileIs() async throws {
        let temp = try makeTemporaryDirectory()
        let script = temp.appendingPathComponent("report-profiles-file.sh")
        try "#!/bin/bash\necho \"$JETLAG_PROFILES_FILE\"\n"
            .write(to: script, atomically: true, encoding: .utf8)

        let profilesPath = "/tmp/jetlag-live/media-profiles.yaml"
        let (process, stream) = ScriptRunner.run(
            script: "report-profiles-file.sh",
            args: [],
            workingDir: temp.path,
            profilesPath: profilesPath
        )
        var lines: [String] = []
        for await line in stream where !line.strippedText.isEmpty {
            lines.append(line.strippedText)
        }
        process.waitUntilExit()

        XCTAssertEqual(lines.first, profilesPath)
    }

    private func makeTemporaryDirectory() throws -> URL {
        let url = URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
            .appendingPathComponent("jetlag-profiles-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: url) }
        return url
    }
}
