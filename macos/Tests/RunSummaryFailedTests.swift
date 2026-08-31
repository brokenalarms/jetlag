import XCTest
@testable import Jetlag

/// A run summary alert with many failures must stay short enough to read — SwiftUI
/// alerts don't scroll, so the failed-files message caps the list rather than
/// dumping every filename onto the screen.
final class RunSummaryFailedTests: XCTestCase {

    func testFewFailuresListsThemAllWithNoMoreLine() {
        let text = Strings.Workflow.runSummaryFailed(
            count: 3, files: ["a.mp4", "b.mp4", "c.mp4"])

        XCTAssertEqual(text, "3 failed:\n  a.mp4\n  b.mp4\n  c.mp4")
        XCTAssertFalse(text.contains("more"))
    }

    func testManyFailuresCapsTheListAndSummarizesTheRest() {
        let files = (1...55).map { "file\($0).mp4" }
        let text = Strings.Workflow.runSummaryFailed(count: 55, files: files)

        XCTAssertTrue(text.hasPrefix("55 failed:\n"))
        for file in files.prefix(5) {
            XCTAssertTrue(text.contains(file), "expected listed file \(file)")
        }
        for file in files.suffix(50) {
            XCTAssertFalse(text.contains(file), "file beyond the cap should not be listed: \(file)")
        }
        XCTAssertTrue(text.contains("… and 50 more"))
    }
}
