import XCTest
@testable import Jetlag

/// Covers what the app shows after Cancel: the log-draining task stops before the
/// pipeline's own "Interrupted by user" line can arrive, so the app must append its
/// own feedback and withdraw the in-flight row rather than leaving it stuck on
/// whatever stage label it last had.
final class CancelFeedbackTests: XCTestCase {

    private func feed(_ state: AppState, _ json: String) {
        state.appendLog(LogLine(text: json, stream: .stdout))
    }

    /// A run mid-file when cancelled: the log gains an app-owned "Cancelled" line and
    /// the live row for the unfinished file disappears rather than staying parked on
    /// its last stage.
    func testCancelAppendsFeedbackAndDropsLiveRow() {
        let state = AppState()
        state.isRunning = true

        feed(state, #"{"event": "pipeline_file", "file": "completed.mp4"}"#)
        feed(state, #"{"event": "pipeline_result", "file": "completed.mp4", "result": "unchanged"}"#)
        feed(state, #"{"event": "pipeline_file", "file": "in-flight.mp4"}"#)

        XCTAssertNotNil(state.liveRow)
        XCTAssertEqual(state.visibleRows.count, 2)

        state.cancelRunning()

        XCTAssertEqual(state.logOutput.last?.text, Strings.LogOutput.cancelled)
        XCTAssertNil(state.liveRow)
        XCTAssertNil(state.currentDiffRow)
        XCTAssertEqual(state.visibleRows.count, 1)
        XCTAssertEqual(state.visibleRows.first?.file, "completed.mp4")
        XCTAssertFalse(state.isRunning)
    }
}
