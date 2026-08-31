import XCTest
@testable import Jetlag

final class RunSummaryCountsTests: XCTestCase {
    func testDryRunCountsReadWouldChange() {
        let text = Strings.Workflow.runSummaryCounts(
            processed: 310, changed: 50, mode: .dryRun)
        XCTAssertEqual(text, "310 files processed\n50 files would change")
    }

    func testAppliedCountsReadChanged() {
        let text = Strings.Workflow.runSummaryCounts(
            processed: 310, changed: 50, mode: .applied)
        XCTAssertEqual(text, "310 files processed\n50 files changed")
    }
}
