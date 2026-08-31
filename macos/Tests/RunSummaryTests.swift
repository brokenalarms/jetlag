import XCTest
@testable import Jetlag

/// Covers what the app knows when a run ends. The pipeline reports the batch's
/// outcome as a `pipeline_summary` event; the app holds it as data and raises the
/// completion popup from it when the run task reaches its end, so a user never has
/// to read the log to learn the job finished. A cancelled run stops before the
/// pipeline can report anything, and raises nothing.
final class RunSummaryTests: XCTestCase {

    private func feed(_ state: AppState, _ json: String) {
        state.appendLog(LogLine(text: json, stream: .stdout))
    }

    private let appliedSummary = #"""
    {"event": "pipeline_summary", "processed": 3, "succeeded": 2, "changed": 1, "failed": 1, "failed_files": ["broken.mp4"], "mode": "applied"}
    """#

    /// Every stat the popup shows arrives decoded, including which files failed —
    /// nothing is recovered from the summary text print_summary writes to stderr.
    func testSummaryEventDecodesIntoStructuredState() {
        let state = AppState()

        feed(state, appliedSummary)

        let summary = state.runSummary
        XCTAssertEqual(summary?.processed, 3)
        XCTAssertEqual(summary?.succeeded, 2)
        XCTAssertEqual(summary?.changed, 1)
        XCTAssertEqual(summary?.unchanged, 1)
        XCTAssertEqual(summary?.failed, 1)
        XCTAssertEqual(summary?.failedFiles, ["broken.mp4"])
        XCTAssertEqual(summary?.mode, .applied)
    }

    /// A dry run says so itself, so the popup can state that nothing was written
    /// rather than the app guessing from settings that may since have changed.
    func testDryRunSummaryCarriesItsMode() {
        let state = AppState()

        feed(state, #"{"event": "pipeline_summary", "processed": 1, "succeeded": 1, "changed": 1, "failed": 0, "failed_files": [], "mode": "dry_run"}"#)

        XCTAssertEqual(state.runSummary?.mode, .dryRun)
    }

    /// The run reaching the end of its output is what raises the popup.
    func testFinishingARunPresentsTheSummary() {
        let state = AppState()
        state.isRunning = true

        feed(state, appliedSummary)
        XCTAssertFalse(state.showRunSummary, "Nothing is shown while the run is still going")

        state.finishRun()

        XCTAssertTrue(state.showRunSummary)
        XCTAssertFalse(state.isRunning)
    }

    /// Cancel kills the pipeline before it can report, so there is no outcome to
    /// show — and any summary left from an earlier run must not surface as if it
    /// described this one.
    func testCancelledRunPresentsNoSummary() {
        let state = AppState()
        state.isRunning = true
        feed(state, appliedSummary)

        state.cancelRunning()

        XCTAssertFalse(state.showRunSummary)
    }

    /// A run that never reported an outcome — killed, or stopped by an error
    /// before the batch finished — raises no popup when its output ends.
    func testRunWithoutASummaryPresentsNothing() {
        let state = AppState()
        state.isRunning = true

        feed(state, #"{"event": "pipeline_file", "file": "one.mp4", "source_path": "/tmp/one.mp4"}"#)
        state.finishRun()

        XCTAssertFalse(state.showRunSummary)
        XCTAssertNil(state.runSummary)
    }

    /// Starting a run clears the last one's outcome: the popup describes the run
    /// that just ended, never the one before it.
    func testStartingARunDropsThePreviousSummary() {
        let state = AppState()
        feed(state, appliedSummary)

        state.clearLog()

        XCTAssertNil(state.runSummary)
        XCTAssertFalse(state.showRunSummary)
    }
}
