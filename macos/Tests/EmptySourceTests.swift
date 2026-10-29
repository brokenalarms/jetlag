import XCTest
@testable import Jetlag

/// Covers a run over a source with nothing the profile matches. The pipeline ends
/// before its first file, so there are no rows and no summary; the inspector would
/// otherwise fall back to its never-run placeholder and the run would look as if it
/// had not happened. The `no_media_files` event is what it shows instead.
final class EmptySourceTests: XCTestCase {

    private func feed(_ state: AppState, _ json: String) {
        state.appendLog(LogLine(text: json, stream: .stdout))
    }

    private let emptyEvent = #"""
    {"event": "no_media_files", "source": "/Volumes/Untitled/DCIM", "extensions": [".arw", ".jpg"]}
    """#

    /// Where the run looked and what it looked for arrive as data, so the inspector
    /// never parses the pipeline's log line back out.
    func testEventRecordsWhereTheRunLooked() {
        let state = AppState()

        feed(state, emptyEvent)

        XCTAssertEqual(state.emptySource,
                       EmptySource(source: "/Volumes/Untitled/DCIM", extensions: [".arw", ".jpg"]))
        XCTAssertTrue(state.visibleRows.isEmpty)
    }

    /// The report describes one run; the next run, or a profile switch, starts
    /// without it rather than showing a stale "nothing found".
    func testClearingTheLogDropsTheReport() {
        let state = AppState()
        feed(state, emptyEvent)

        state.clearLog()

        XCTAssertNil(state.emptySource)
    }

    /// Nothing ran, so there is no outcome to announce in the completion popup.
    func testFinishingAnEmptyRunRaisesNoSummary() {
        let state = AppState()
        state.isRunning = true
        feed(state, emptyEvent)

        state.finishRun()

        XCTAssertFalse(state.showRunSummary)
        XCTAssertNotNil(state.emptySource)
    }
}
