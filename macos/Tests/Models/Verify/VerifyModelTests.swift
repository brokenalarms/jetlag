import XCTest
import Yams
@testable import Jetlag

/// The Verify screen reads verify-card's events, declared in
/// scripts/lib/verify-card-schema.yaml, and passes it the locations and lists the
/// profiles file stores. These hold the app to the schema (every example decodes,
/// every verdict token has a case), and check the arguments it builds, the report it
/// folds the events into, and that `backups:` and `verify:` survive a save.
final class VerifyModelTests: XCTestCase {

    private static let schemaURL = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()   // Verify
        .deletingLastPathComponent()   // Models
        .deletingLastPathComponent()   // Tests
        .deletingLastPathComponent()   // macos
        .deletingLastPathComponent()   // repo root
        .appendingPathComponent("scripts/lib/verify-card-schema.yaml")

    private func schemaEvents() throws -> [String: [String: Any]] {
        let text = try String(contentsOf: Self.schemaURL, encoding: .utf8)
        let root = try Yams.load(yaml: text) as? [String: Any]
        return try XCTUnwrap(root?["events"] as? [String: [String: Any]])
    }

    func testEveryDeclaredEventExampleDecodes() throws {
        for (name, declaration) in try schemaEvents() {
            let example = try XCTUnwrap(declaration["example"], "\(name) has no example")
            let data = try JSONSerialization.data(withJSONObject: example)
            XCTAssertNoThrow(try JSONDecoder().decode(VerifyEvent.self, from: data), "\(name) does not decode")
        }
    }

    func testEveryVerdictTokenHasACase() throws {
        let result = try XCTUnwrap(try schemaEvents()["verify_result"]?["fields"] as? [String: Any])
        let verdict = try XCTUnwrap(result["verdict"] as? [String: Any])
        let tokens = Set(try XCTUnwrap(verdict["enum"] as? [String]))
        XCTAssertEqual(tokens, Set(VerifyVerdict.allCases.map(\.rawValue)))
    }

    func testReportFoldsResultsIntoTheirFileAndHidesMatchedRows() throws {
        var report = VerifyReport()
        let lines = [
            #"{"event":"verify_location","location":"T9","root":"/Volumes/T9","remote":false,"network":false,"reachable":true,"files":2}"#,
            #"{"event":"verify_file","file":"DCIM/a.mp4","kind":"media","size":10}"#,
            #"{"event":"verify_result","file":"DCIM/a.mp4","location":"T9","verdict":"matched","basis":"size","copies":["a.mp4"]}"#,
            #"{"event":"verify_file","file":"DCIM/b.mp4","kind":"media","size":10}"#,
            #"{"event":"verify_result","file":"DCIM/b.mp4","location":"T9","verdict":"missing","copies":[]}"#,
            #"{"event":"verify_summary","checked":2,"on_every_location":1,"need_attention":1,"not_checked":0,"not_checked_kinds":[]}"#,
        ]
        for line in lines {
            report.apply(try XCTUnwrap(VerifyEvent.decode(line)))
        }

        XCTAssertEqual(report.rows.map(\.file), ["DCIM/a.mp4", "DCIM/b.mp4"])
        XCTAssertEqual(report.visibleRows(showMatched: false).map(\.file), ["DCIM/b.mp4"])
        XCTAssertEqual(report.rows[1].outcomes["T9"]?.verdict, .missing)
        XCTAssertEqual(report.summary?.needAttention, 1)
    }

    func testUnmatchedClipDetailsDecodeAndDescribeABrokenRecording() throws {
        let line = #"{"event":"verify_file","file":"DCIM/c.mp4","kind":"media","size":2048,"opens":false,"neighbours_backed_up":true}"#
        guard case .file(let details) = try XCTUnwrap(VerifyEvent.decode(line)) else {
            return XCTFail("verify_file did not decode as a file")
        }

        XCTAssertEqual(details.opens, false)
        XCTAssertEqual(details.neighboursBackedUp, true)
        let text = Strings.Verify.clipDetails(details)
        XCTAssertTrue(text.contains(Strings.Verify.doesNotOpen), text)
        XCTAssertTrue(text.contains(Strings.Verify.neighboursBackedUp), text)
    }

    func testArgumentsCarryEveryEnabledLocationAndTheLists() {
        let args = VerifySession.arguments(
            source: "/Volumes/Untitled",
            locations: [NamedBackupLocation(name: "NAS", config: BackupLocationConfig(path: "nas:/volume1/Mirror")),
                        NamedBackupLocation(name: "T9", config: BackupLocationConfig(path: "/Volumes/T9/Videos"))],
            lists: VerifyListsConfig(mediaExtensions: [".mp4"], companionExtensions: [".lrv"], ignorePaths: ["MISC"]),
            includeCompanions: true, verifyHashes: true, includeNetwork: false)

        XCTAssertEqual(args, [
            "/Volumes/Untitled",
            "--location", "NAS=nas:/volume1/Mirror",
            "--location", "T9=/Volumes/T9/Videos",
            "--media-extensions", ".mp4",
            "--companion-extensions", ".lrv",
            "--include-companions",
            "--ignore-paths", "MISC",
            "--verify-hashes",
        ])
    }

    func testListsAreSeededFromTheProfiles() {
        var video = MediaProfile(type: .video)
        video.fileExtensions = [".MP4", "insv"]
        video.companionExtensions = [".lrv", ".jpg"]
        var photo = MediaProfile(type: .photo)
        photo.fileExtensions = [".jpg"]

        let lists = VerifyListsConfig.seeded(from: ["video": video, "photo": photo])

        XCTAssertEqual(lists.mediaExtensions, [".insv", ".jpg", ".mp4"])
        XCTAssertEqual(lists.companionExtensions, [".lrv"], "a type some profile imports is media, not a companion")
        XCTAssertEqual(lists.ignorePaths, ["MISC"])
    }

    func testHostPathIsRemoteAndNetwork() {
        XCTAssertTrue(BackupLocationConfig(path: "nas-rsync:/volume1/Backup").isRemote)
        XCTAssertTrue(BackupLocationConfig(path: "nas-rsync:/volume1/Backup").isNetwork)
        XCTAssertFalse(BackupLocationConfig(path: "/Volumes/T9/Videos").isRemote)
    }

    func testBackupsAndListsSurviveAProfileSave() throws {
        let path = NSTemporaryDirectory() + UUID().uuidString + ".yaml"
        defer { try? FileManager.default.removeItem(atPath: path) }
        try """
        profiles:
          cam:
            type: video
            file_extensions: [.mp4]
        backups:
          T9:
            path: /Volumes/T9/Videos
        verify:
          media_extensions: [.mp4]
          companion_extensions: []
          ignore_paths: [MISC]
        """.write(toFile: path, atomically: true, encoding: .utf8)

        var config = try ProfileService.load(from: path)
        XCTAssertEqual(config.backups?["T9"]?.path, "/Volumes/T9/Videos")
        config.backups?["NAS"] = BackupLocationConfig(path: "nas:/volume1/Mirror")
        try ProfileService.write(config, to: path)
        let reloaded = try ProfileService.load(from: path)

        XCTAssertEqual(reloaded.sortedBackups.map(\.name), ["NAS", "T9"])
        XCTAssertEqual(reloaded.verify?.ignorePaths, ["MISC"])
        XCTAssertEqual(reloaded.profiles.count, 1)
    }
}
