import XCTest
@testable import Jetlag

final class RunSummaryCountsTests: XCTestCase {
    func testDryRunCountsReadWouldChange() {
        let text = Strings.Workflow.runSummaryCounts(
            processed: 310, changed: 310, unchanged: 0, mode: .dryRun)
        XCTAssertEqual(text, "310 files processed — 310 would change, 0 unchanged.")
    }

    func testAppliedCountsReadChanged() {
        let text = Strings.Workflow.runSummaryCounts(
            processed: 310, changed: 310, unchanged: 0, mode: .applied)
        XCTAssertEqual(text, "310 files processed — 310 changed, 0 unchanged.")
    }
}
