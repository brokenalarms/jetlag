import XCTest
@testable import Jetlag

/// Whether a source's filenames carry timestamps decides if "From filenames" is
/// offered. The source is read once it is chosen, in one walk that stops at the
/// first such file, never per keystroke or redraw, and never inside a package:
/// a Photos library in the source would prompt for Photos access.
final class SourceTimestampedNamesTests: XCTestCase {

    private var source: URL!
    private let scriptsDirectory = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        .appendingPathComponent("scripts").path

    override func setUpWithError() throws {
        source = FileManager.default.temporaryDirectory
            .appendingPathComponent("SourceTimestampedNamesTests-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: source, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: source)
    }

    private func touch(_ relative: String) throws {
        let url = source.appendingPathComponent(relative)
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(),
                                                withIntermediateDirectories: true)
        FileManager.default.createFile(atPath: url.path, contents: Data())
    }

    private func hasTimestampedNames(_ extensions: [String] = [".mp4"]) async -> Bool {
        await FilenamePatterns.sourceHasTimestampedNames(
            source.path, extensions: extensions, scriptsDirectory: scriptsDirectory)
    }

    func testATimestampedNameDeepInTheSourceIsFound() async throws {
        try touch("DCIM/100MEDIA/C0001.MP4")
        try touch("DCIM/101MEDIA/VID_20240615_143000.mp4")

        let found = await hasTimestampedNames()
        XCTAssertTrue(found)
    }

    func testOnlyTheProfilesFileTypesCount() async throws {
        try touch("IMG_20240615_143000.jpg")

        let found = await hasTimestampedNames([".mp4"])
        XCTAssertFalse(found)
    }

    func testAPhotosLibraryInTheSourceIsNotRead() async throws {
        try touch("Photos Library.photoslibrary/originals/VID_20240615_143000.mp4")

        let found = await hasTimestampedNames()
        XCTAssertFalse(found)
    }

    /// Typing a path changes the field, not the chosen source; entering it does.
    func testOnlyAnEnteredSourceIsChosen() {
        let session = WorkflowSession(profile: MediaProfile(sourceDir: "/Volumes/CARD"), profileName: "p")
        XCTAssertEqual(session.chosenSource, "/Volumes/CARD")

        session.sourceDir.value = "/"
        XCTAssertEqual(session.chosenSource, "/Volumes/CARD")

        session.sourceDir.value = "/Volumes/OTHER"
        session.chooseSource()
        XCTAssertEqual(session.chosenSource, "/Volumes/OTHER")
    }

    /// Filenames cannot be the timestamp source for a source whose names carry none.
    func testASourceWithoutTimestampedNamesTurnsOffInferring() {
        let session = WorkflowSession(profile: MediaProfile(sourceDir: "/Volumes/CARD"), profileName: "p")
        session.noteTimestampedNames(true, in: "/Volumes/CARD")
        session.inferFromFilenames = true

        session.noteTimestampedNames(false, in: "/Volumes/CARD")

        XCTAssertFalse(session.sourceHasTimestampedNames)
        XCTAssertFalse(session.inferFromFilenames)
    }

    /// A read that finishes after another source was chosen says nothing about it.
    func testAReadOfAnEarlierSourceIsIgnored() {
        let session = WorkflowSession(profile: MediaProfile(sourceDir: "/Volumes/CARD"), profileName: "p")
        session.sourceDir.value = "/Volumes/OTHER"
        session.chooseSource()

        session.noteTimestampedNames(true, in: "/Volumes/CARD")

        XCTAssertFalse(session.sourceHasTimestampedNames)
    }
}
