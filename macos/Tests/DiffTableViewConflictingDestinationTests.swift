import XCTest
@testable import Jetlag

/// The Files table's "Show Existing File at Destination" context menu item acts
/// only on rows blocked by a different file already at the destination
/// (`organizeReason == "exists_differs"`) — the one case where an --overwrite
/// apply would replace something for good. `conflictingDestinationURLs` is the
/// gate: it must return `dest` only for those rows, and only when that file
/// still exists on disk, never for identical, would_copy, or copied rows even
/// when `dest` is set.
final class DiffTableViewConflictingDestinationTests: XCTestCase {

    private var tempDir: URL!

    override func setUpWithError() throws {
        tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: tempDir)
    }

    private func existingDestPath(named name: String = "clip.mp4") throws -> String {
        let url = tempDir.appendingPathComponent(name)
        try Data().write(to: url)
        return url.path
    }

    private func row(file: String = "clip.mp4", dest: String?,
                     organizeAction: String?, organizeReason: String? = nil) -> DiffTableRow {
        var row = DiffTableRow(file: file)
        row.dest = dest
        row.organizeAction = organizeAction
        row.organizeReason = organizeReason
        return row
    }

    func testReturnsDestForAnExistsDiffersRowWithAnExistingDestinationFile() throws {
        let dest = try existingDestPath()
        let conflict = row(dest: dest, organizeAction: "skipped", organizeReason: "exists_differs")
        let view = DiffTableView(rows: [conflict], sourceDir: tempDir.path)

        let urls = view.conflictingDestinationURLs(for: [conflict.id])

        XCTAssertEqual(urls, [URL(fileURLWithPath: dest)])
    }

    func testReturnsNothingWhenTheConflictingDestinationFileNoLongerExists() {
        let conflict = row(dest: "/nonexistent/path/clip.mp4",
                           organizeAction: "skipped", organizeReason: "exists_differs")
        let view = DiffTableView(rows: [conflict], sourceDir: tempDir.path)

        XCTAssertTrue(view.conflictingDestinationURLs(for: [conflict.id]).isEmpty)
    }

    func testReturnsNothingForAnIdenticalRowEvenWithDestSet() throws {
        let dest = try existingDestPath()
        let identical = row(dest: dest, organizeAction: "skipped", organizeReason: "identical")
        let view = DiffTableView(rows: [identical], sourceDir: tempDir.path)

        XCTAssertTrue(view.conflictingDestinationURLs(for: [identical.id]).isEmpty)
    }

    func testReturnsNothingForAWouldCopyRowEvenWithDestSet() throws {
        let dest = try existingDestPath()
        let wouldCopy = row(dest: dest, organizeAction: "would_copy")
        let view = DiffTableView(rows: [wouldCopy], sourceDir: tempDir.path)

        XCTAssertTrue(view.conflictingDestinationURLs(for: [wouldCopy.id]).isEmpty)
    }

    func testReturnsNothingForACopiedRowEvenWithDestSet() throws {
        let dest = try existingDestPath()
        let copied = row(dest: dest, organizeAction: "copied")
        let view = DiffTableView(rows: [copied], sourceDir: tempDir.path)

        XCTAssertTrue(view.conflictingDestinationURLs(for: [copied.id]).isEmpty)
    }

    func testReturnsNothingWhenTheSelectionMixesAConflictWithAnOrdinaryRow() throws {
        let conflict = row(file: "clip.mp4", dest: try existingDestPath(),
                           organizeAction: "skipped", organizeReason: "exists_differs")
        let copied = row(file: "other.mp4", dest: try existingDestPath(named: "other.mp4"),
                         organizeAction: "copied")
        let view = DiffTableView(rows: [conflict, copied], sourceDir: tempDir.path)

        XCTAssertTrue(view.conflictingDestinationURLs(for: [conflict.id, copied.id]).isEmpty)
    }

    func testReturnsEveryDestWhenTheWholeSelectionConflicts() throws {
        let firstDest = try existingDestPath()
        let secondDest = try existingDestPath(named: "other.mp4")
        let first = row(file: "clip.mp4", dest: firstDest,
                        organizeAction: "skipped", organizeReason: "exists_differs")
        let second = row(file: "other.mp4", dest: secondDest,
                         organizeAction: "skipped", organizeReason: "exists_differs")
        let view = DiffTableView(rows: [first, second], sourceDir: tempDir.path)

        let urls = view.conflictingDestinationURLs(for: [first.id, second.id])

        XCTAssertEqual(Set(urls), [URL(fileURLWithPath: firstDest), URL(fileURLWithPath: secondDest)])
    }

    func testReturnsNothingForAnEmptySelection() throws {
        let conflict = row(dest: try existingDestPath(),
                           organizeAction: "skipped", organizeReason: "exists_differs")
        let view = DiffTableView(rows: [conflict], sourceDir: tempDir.path)

        XCTAssertTrue(view.conflictingDestinationURLs(for: []).isEmpty)
    }
}
