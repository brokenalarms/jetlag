import XCTest
@testable import Jetlag

/// The Files table's "Show in Finder" / "Quick Look" context menu acts on
/// wherever a row's file currently is: `dest` only once organize has actually
/// placed a file there (`copied`, `moved`, `overwrote`), otherwise the path the
/// pipeline emitted on `pipeline_file` — a destination is present on skipped and
/// dry-run rows too. The emitted source path is taken verbatim, so a file found
/// deep in a recursive scan still resolves to where it actually is.
final class RowFileLocationTests: XCTestCase {

    private func row(file: String = "clip.mp4", sourcePath: String? = "/Volumes/SD/DCIM/100GOPRO/clip.mp4",
                     dest: String? = nil, organizeAction: String? = nil) -> DiffTableRow {
        var row = DiffTableRow(file: file)
        row.sourcePath = sourcePath
        row.dest = dest
        row.organizeAction = organizeAction
        return row
    }

    func testResolvesToTheEmittedSourcePathBeforeAMove() {
        let path = RowFileLocation.path(for: row())

        XCTAssertEqual(path, "/Volumes/SD/DCIM/100GOPRO/clip.mp4")
    }

    func testResolvesToDestAfterAMove() {
        let moved = row(dest: "/Users/x/Movies/2025-08-30/clip.mp4", organizeAction: "copied")

        XCTAssertEqual(RowFileLocation.path(for: moved), "/Users/x/Movies/2025-08-30/clip.mp4")
    }

    func testResolvesToDestAfterAnOverwrite() {
        let moved = row(dest: "/Users/x/Movies/2025-08-30/clip.mp4", organizeAction: "overwrote")

        XCTAssertEqual(RowFileLocation.path(for: moved), "/Users/x/Movies/2025-08-30/clip.mp4")
    }

    func testResolvesToTheSourcePathWhenSkippedDespiteDestBeingSet() {
        let skipped = row(dest: "/Users/x/Movies/2025-08-30/clip.mp4", organizeAction: "skipped")

        XCTAssertEqual(RowFileLocation.path(for: skipped), "/Volumes/SD/DCIM/100GOPRO/clip.mp4")
    }

    func testResolvesToTheSourcePathOnDryRunWouldCopyDespiteDestBeingSet() {
        let wouldCopy = row(dest: "/Users/x/Movies/2025-08-30/clip.mp4", organizeAction: "would_copy")

        XCTAssertEqual(RowFileLocation.path(for: wouldCopy), "/Volumes/SD/DCIM/100GOPRO/clip.mp4")
    }

    func testResolvesToTheSourcePathOnDryRunWouldOverwriteDespiteDestBeingSet() {
        let wouldOverwrite = row(dest: "/Users/x/Movies/2025-08-30/clip.mp4", organizeAction: "would_overwrite")

        XCTAssertEqual(RowFileLocation.path(for: wouldOverwrite), "/Volumes/SD/DCIM/100GOPRO/clip.mp4")
    }

    /// A subdirectory of a recursive scan is exactly what the old sourceDir +
    /// basename guess got wrong: it named a file that was never there.
    func testKeepsTheSubdirectoryTheFileWasFoundIn() {
        let nested = row(file: "clip.mp4", sourcePath: "/Volumes/SD/DCIM/101GOPRO/sub/clip.mp4")

        XCTAssertEqual(RowFileLocation.path(for: nested), "/Volumes/SD/DCIM/101GOPRO/sub/clip.mp4")
    }

    func testNoSourcePathAndNoDestResolvesToNil() {
        XCTAssertNil(RowFileLocation.path(for: row(sourcePath: nil)))
    }
}
