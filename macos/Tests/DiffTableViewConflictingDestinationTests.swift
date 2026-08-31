import XCTest
@testable import Jetlag

/// The Files table's "Show Existing File at Destination" context menu item acts
/// only on rows blocked by a different file already at the destination
/// (`organizeReason == "exists_differs"`) — the one case where an --overwrite
/// apply would replace something for good. `conflictingDestinationURLs` is the
/// gate: it returns `dest` for those rows and only while that file still exists
/// on disk, never for identical, would_copy, or copied rows even when `dest` is
/// set. A selection that mixes a conflict with an ordinary row still offers the
/// item, acting on the conflicting subset.
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
        row.sourcePath = tempDir.appendingPathComponent("DCIM/100GOPRO/\(file)").path
        row.dest = dest
        row.organizeAction = organizeAction
        row.organizeReason = organizeReason
        return row
    }

    func testReturnsDestForAnExistsDiffersRowWithAnExistingDestinationFile() throws {
        let dest = try existingDestPath()
        let conflict = row(dest: dest, organizeAction: "skipped", organizeReason: "exists_differs")
        let view = DiffTableView(rows: [conflict])

        let urls = view.conflictingDestinationURLs(for: [conflict.id])

        XCTAssertEqual(urls, [URL(fileURLWithPath: dest)])
    }

    func testReturnsNothingWhenTheConflictingDestinationFileNoLongerExists() {
        let conflict = row(dest: "/nonexistent/path/clip.mp4",
                           organizeAction: "skipped", organizeReason: "exists_differs")
        let view = DiffTableView(rows: [conflict])

        XCTAssertTrue(view.conflictingDestinationURLs(for: [conflict.id]).isEmpty)
    }

    func testReturnsNothingForAnIdenticalRowEvenWithDestSet() throws {
        let dest = try existingDestPath()
        let identical = row(dest: dest, organizeAction: "skipped", organizeReason: "identical")
        let view = DiffTableView(rows: [identical])

        XCTAssertTrue(view.conflictingDestinationURLs(for: [identical.id]).isEmpty)
    }

    func testReturnsNothingForAWouldCopyRowEvenWithDestSet() throws {
        let dest = try existingDestPath()
        let wouldCopy = row(dest: dest, organizeAction: "would_copy")
        let view = DiffTableView(rows: [wouldCopy])

        XCTAssertTrue(view.conflictingDestinationURLs(for: [wouldCopy.id]).isEmpty)
    }

    func testReturnsNothingForACopiedRowEvenWithDestSet() throws {
        let dest = try existingDestPath()
        let copied = row(dest: dest, organizeAction: "copied")
        let view = DiffTableView(rows: [copied])

        XCTAssertTrue(view.conflictingDestinationURLs(for: [copied.id]).isEmpty)
    }

    func testReturnsOnlyTheConflictWhenTheSelectionMixesItWithAnOrdinaryRow() throws {
        let conflictDest = try existingDestPath()
        let conflict = row(file: "clip.mp4", dest: conflictDest,
                           organizeAction: "skipped", organizeReason: "exists_differs")
        let copied = row(file: "other.mp4", dest: try existingDestPath(named: "other.mp4"),
                         organizeAction: "copied")
        let view = DiffTableView(rows: [conflict, copied])

        let urls = view.conflictingDestinationURLs(for: [conflict.id, copied.id])

        XCTAssertEqual(urls, [URL(fileURLWithPath: conflictDest)])
    }

    func testReturnsEveryDestWhenTheWholeSelectionConflicts() throws {
        let firstDest = try existingDestPath()
        let secondDest = try existingDestPath(named: "other.mp4")
        let first = row(file: "clip.mp4", dest: firstDest,
                        organizeAction: "skipped", organizeReason: "exists_differs")
        let second = row(file: "other.mp4", dest: secondDest,
                         organizeAction: "skipped", organizeReason: "exists_differs")
        let view = DiffTableView(rows: [first, second])

        let urls = view.conflictingDestinationURLs(for: [first.id, second.id])

        XCTAssertEqual(Set(urls), [URL(fileURLWithPath: firstDest), URL(fileURLWithPath: secondDest)])
    }

    func testReturnsNothingForAnEmptySelection() throws {
        let conflict = row(dest: try existingDestPath(),
                           organizeAction: "skipped", organizeReason: "exists_differs")
        let view = DiffTableView(rows: [conflict])

        XCTAssertTrue(view.conflictingDestinationURLs(for: []).isEmpty)
    }

    /// The Korea run's complaint: right-clicking a conflicted row alongside an
    /// ordinary one offered nothing but the destination item, and Show in Finder
    /// and Quick Look were greyed out. All three now have something to act on.
    func testAMixedSelectionOffersAllThreeMenuItems() throws {
        let conflictDest = try existingDestPath()
        let conflict = row(file: "clip.mp4", dest: conflictDest,
                           organizeAction: "skipped", organizeReason: "exists_differs")
        let copied = row(file: "other.mp4", dest: try existingDestPath(named: "other.mp4"),
                         organizeAction: "copied")
        let view = DiffTableView(rows: [conflict, copied])
        let selection: Set<DiffTableRow.ID> = [conflict.id, copied.id]

        let fileURLs = view.availableFileURLs(for: selection)

        XCTAssertEqual(Set(fileURLs), [
            URL(fileURLWithPath: conflict.sourcePath!),
            URL(fileURLWithPath: copied.dest!),
        ])
        XCTAssertEqual(view.conflictingDestinationURLs(for: selection),
                       [URL(fileURLWithPath: conflictDest)])
    }

    /// Nothing exists at either resolved path — the source card was ejected, the
    /// destination was moved away. Show in Finder and Quick Look still resolve
    /// rather than emptying out and disabling themselves.
    func testFileURLsResolveEvenWhenNothingIsAtThePathAnyMore() {
        let unmoved = row(file: "clip.mp4", dest: "/nonexistent/dest/clip.mp4",
                          organizeAction: "skipped", organizeReason: "exists_differs")
        let view = DiffTableView(rows: [unmoved])

        XCTAssertEqual(view.availableFileURLs(for: [unmoved.id]),
                       [URL(fileURLWithPath: unmoved.sourcePath!)])
    }
}
