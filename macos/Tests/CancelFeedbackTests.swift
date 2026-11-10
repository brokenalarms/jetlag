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
        XCTAssertNil(state.transcript.liveRow)
        XCTAssertEqual(state.visibleRows.count, 1)
        XCTAssertEqual(state.visibleRows.first?.file, "completed.mp4")
        XCTAssertFalse(state.isRunning)
    }

    /// The pipeline's output is drained off the main actor, so a line can already be
    /// waiting for it when Cancel is pressed there. That line must not land after
    /// the cancelled line, nor start a row the cancel just withdrew, nor finish the
    /// run as if it had completed.
    @MainActor
    func testOutputWaitingForTheMainActorIsDroppedOnCancel() async {
        let launcher = ReplayingLauncher(["media-pipeline.sh": [
            LogLine(text: #"{"event": "pipeline_file", "file": "late.mp4"}"#, stream: .stdout),
            LogLine(text: "late progress", stream: .stderr),
        ]])
        let state = AppState(launcher: launcher)
        state.workflowSession = WorkflowSession(profile: MediaProfile(type: .video), profileName: "p")

        state.startPipeline()
        let drain = state.currentRunTask
        // Hold the main actor while the drain reads the replayed output and queues
        // its first line for it, as a busy main thread does during a real run.
        holdCurrentThread(seconds: 0.2)
        state.cancelRunning()
        await drain?.value

        XCTAssertEqual(state.logOutput.map(\.text), [Strings.LogOutput.cancelled])
        XCTAssertTrue(state.visibleRows.isEmpty)
        XCTAssertFalse(state.isRunning)
        XCTAssertFalse(state.showRunSummary)
    }

    /// Blocks without suspending, so the actor the caller is on stays occupied.
    private func holdCurrentThread(seconds: TimeInterval) {
        Thread.sleep(forTimeInterval: seconds)
    }
}
