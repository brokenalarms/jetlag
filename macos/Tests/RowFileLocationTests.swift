import XCTest
@testable import Jetlag

/// The Files table's "Show in Finder" / "Quick Look" context menu acts on
/// wherever a row's file currently is: `dest` only once organize has actually
/// placed a file there (`copied`, `moved`, `overwrote`), otherwise the source
/// directory it started in — a destination can be present on skipped and
/// dry-run rows too. This covers that resolution and the enabled/disabled rule
/// the menu items key off — whether a real file exists at the resolved path.
final class RowFileLocationTests: XCTestCase {

    private func row(file: String = "clip.mp4", dest: String? = nil, organizeAction: String? = nil) -> DiffTableRow {
        var row = DiffTableRow(file: file)
        row.dest = dest
        row.organizeAction = organizeAction
        return row
    }

    func testResolvesToSourceDirBeforeAMove() {
        let path = RowFileLocation.path(for: row(file: "clip.mp4"), sourceDir: "/Volumes/SD/DCIM")

        XCTAssertEqual(path, "/Volumes/SD/DCIM/clip.mp4")
    }

    func testResolvesToDestAfterAMove() {
        let moved = row(file: "clip.mp4", dest: "/Users/x/Movies/2025-08-30/clip.mp4", organizeAction: "copied")

        let path = RowFileLocation.path(for: moved, sourceDir: "/Volumes/SD/DCIM")

        XCTAssertEqual(path, "/Users/x/Movies/2025-08-30/clip.mp4")
    }

    func testResolvesToDestAfterAnOverwrite() {
        let moved = row(file: "clip.mp4", dest: "/Users/x/Movies/2025-08-30/clip.mp4", organizeAction: "overwrote")

        let path = RowFileLocation.path(for: moved, sourceDir: "/Volumes/SD/DCIM")

        XCTAssertEqual(path, "/Users/x/Movies/2025-08-30/clip.mp4")
    }

    func testResolvesToSourceWhenSkippedDespiteDestBeingSet() {
        let skipped = row(file: "clip.mp4", dest: "/Users/x/Movies/2025-08-30/clip.mp4", organizeAction: "skipped")

        let path = RowFileLocation.path(for: skipped, sourceDir: "/Volumes/SD/DCIM")

        XCTAssertEqual(path, "/Volumes/SD/DCIM/clip.mp4")
    }

    func testResolvesToSourceOnDryRunWouldCopyDespiteDestBeingSet() {
        let wouldCopy = row(file: "clip.mp4", dest: "/Users/x/Movies/2025-08-30/clip.mp4", organizeAction: "would_copy")

        let path = RowFileLocation.path(for: wouldCopy, sourceDir: "/Volumes/SD/DCIM")

        XCTAssertEqual(path, "/Volumes/SD/DCIM/clip.mp4")
    }

    func testResolvesToSourceOnDryRunWouldOverwriteDespiteDestBeingSet() {
        let wouldOverwrite = row(file: "clip.mp4", dest: "/Users/x/Movies/2025-08-30/clip.mp4", organizeAction: "would_overwrite")

        let path = RowFileLocation.path(for: wouldOverwrite, sourceDir: "/Volumes/SD/DCIM")

        XCTAssertEqual(path, "/Volumes/SD/DCIM/clip.mp4")
    }

    func testNoSourceDirAndNoDestResolvesToNil() {
        XCTAssertNil(RowFileLocation.path(for: row(file: "clip.mp4"), sourceDir: ""))
    }

    func testExistsIsTrueWhenTheResolvedPathIsARealFile() throws {
        let dir = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        let fileURL = dir.appendingPathComponent("clip.mp4")
        try Data().write(to: fileURL)

        let present = RowFileLocation.exists(for: row(file: "clip.mp4"), sourceDir: dir.path)

        XCTAssertTrue(present)
    }

    func testExistsIsFalseWhenTheFileHasMovedOrIsGone() throws {
        let dir = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: dir) }

        let missing = RowFileLocation.exists(for: row(file: "clip.mp4"), sourceDir: dir.path)

        XCTAssertFalse(missing)
    }

    func testExistsIsFalseWhenDestNoLongerExists() {
        let moved = row(file: "clip.mp4", dest: "/nonexistent/path/clip.mp4", organizeAction: "moved")

        XCTAssertFalse(RowFileLocation.exists(for: moved, sourceDir: "/Volumes/SD/DCIM"))
    }
}
