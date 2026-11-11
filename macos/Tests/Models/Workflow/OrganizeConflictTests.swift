import XCTest
@testable import Jetlag

/// Covers how the app handles files the organize step could not move because a
/// different file already occupies their destination.
///
/// The pipeline reports the fact as data — a per-row `reason` plus one
/// `destination_occupied` batch check — and the app's only job is to flag those
/// rows; asking before an apply is the one batch-check alert (BatchCheckTests).
final class OrganizeConflictTests: XCTestCase {

    /// A blocked row is flagged in the diff table, so the count in the prompt
    /// can be traced back to the files it refers to.
    func testBlockedRowIsFlaggedInTheDiffTable() {
        var row = DiffTableRow(file: "a.mp4")
        row.organizeAction = "skipped"
        row.organizeReason = "exists_differs"

        XCTAssertTrue(row.hasDestinationConflict)
        XCTAssertEqual(row.skipReason?.explanation, Strings.DiffTable.skipExistsDiffersHelp)
    }

    /// An identical copy at the destination costs nothing and is not a conflict,
    /// so it is not flagged and does not raise the prompt.
    func testIdenticalCopyIsNotFlagged() {
        var row = DiffTableRow(file: "a.mp4")
        row.organizeAction = "skipped"
        row.organizeReason = "identical"

        XCTAssertFalse(row.hasDestinationConflict)
    }

    func testMovedRowIsNotFlagged() {
        var row = DiffTableRow(file: "a.mp4")
        row.organizeAction = "moved"

        XCTAssertFalse(row.hasDestinationConflict)
    }

    /// End to end from the wire: the pipeline's own events, verbatim, flag the
    /// row and leave the finding for the apply to ask about.
    func testConflictEventFromTheWireReachesThePrompt() {
        let state = AppState()
        state.workflowSession.applyMode = true

        state.appendLog(LogLine(text: #"{"event": "pipeline_file", "file": "a.mp4"}"#,
                                stream: .stdout))
        state.appendLog(LogLine(text: """
        {"event": "organize_result", "file": "a.mp4", "action": "skipped", \
        "dest": "/tmp/ready/2025/2025-08-15/a.mp4", "reason": "exists_differs"}
        """, stream: .stdout))
        state.appendLog(LogLine(
            text: #"{"event": "pipeline_result", "file": "a.mp4", "result": "would_change"}"#,
            stream: .stdout))
        state.appendLog(LogLine(
            text: #"{"event": "batch_check", "check": "destination_occupied", "files": ["a.mp4"], "assent_flag": "--overwrite", "refused": false}"#,
            stream: .stdout))

        XCTAssertTrue(state.diffTableRows[0].hasDestinationConflict)
        XCTAssertTrue(state.workflowSession.requestCheckAssentIfNeeded())
        XCTAssertEqual(state.workflowSession.pendingChecks.map(\.files), [["a.mp4"]])
    }
}
