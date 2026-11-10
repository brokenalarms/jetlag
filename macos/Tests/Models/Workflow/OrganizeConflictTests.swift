import XCTest
@testable import Jetlag

/// Covers how the app handles files the organize step could not move because a
/// different file already occupies their destination.
///
/// The pipeline reports the fact as data — a per-row `reason` plus one
/// batch-level `organize_conflict` — and the app's only job is to flag those
/// rows, ask before an apply destroys anything, and pass `--overwrite` on the
/// re-run the user assents to. No overwrite decision is made here.
final class OrganizeConflictTests: XCTestCase {

    private func makeSession() -> WorkflowSession {
        let profile = MediaProfile(
            type: .video,
            sourceDir: "/Volumes/TestCard/DCIM",
            readyDir: "/tmp/ready",
            fileExtensions: [".mp4"]
        )
        return WorkflowSession(profile: profile, profileName: "test-profile")
    }

    private func feedConflict(_ state: AppState, count: Int, files: [String]) {
        let list = files.map { "\"\($0)\"" }.joined(separator: ", ")
        state.appendLog(LogLine(
            text: "{\"event\": \"organize_conflict\", \"count\": \(count), \"files\": [\(list)]}",
            stream: .stdout))
    }

    /// The batch event is what the prompt counts, so it has to survive the run
    /// that reported it.
    func testConflictEventRecordsWhatTheRunLeftBehind() {
        let state = AppState()

        feedConflict(state, count: 2, files: ["a.mp4", "b.mp4"])

        XCTAssertEqual(state.workflowSession.organizeConflictCount, 2)
        XCTAssertEqual(state.workflowSession.organizeConflictFiles, ["a.mp4", "b.mp4"])
    }

    /// A preview destroys nothing, so it is never interrupted by the question.
    func testDryRunNeverAsks() {
        let state = AppState()
        state.workflowSession.applyMode = false
        feedConflict(state, count: 1, files: ["a.mp4"])

        XCTAssertFalse(state.workflowSession.requestOverwriteAssentIfNeeded())
        XCTAssertFalse(state.workflowSession.showOverwriteConflict)
    }

    /// Applying over a file that is already there is what needs the answer.
    func testApplyWithConflictsAsksBeforeTheRunStarts() {
        let state = AppState()
        state.workflowSession.applyMode = true
        feedConflict(state, count: 3, files: ["a.mp4", "b.mp4", "c.mp4"])

        XCTAssertTrue(state.workflowSession.requestOverwriteAssentIfNeeded())
        XCTAssertTrue(state.workflowSession.showOverwriteConflict)
    }

    /// Nothing was blocked, so an apply runs straight through.
    func testApplyWithoutConflictsRunsWithoutAsking() {
        let session = makeSession()
        session.applyMode = true

        XCTAssertFalse(session.requestOverwriteAssentIfNeeded())
        XCTAssertFalse(session.showOverwriteConflict)
    }

    /// Confirming is what unblocks the apply: the re-run must carry --overwrite,
    /// or the pipeline skips the same files again.
    func testAssentAddsOverwriteToTheNextRun() {
        let state = AppState()
        state.workflowSession.applyMode = true
        feedConflict(state, count: 1, files: ["a.mp4"])
        _ = state.workflowSession.requestOverwriteAssentIfNeeded()

        state.workflowSession.grantOverwriteAssent()

        XCTAssertFalse(state.workflowSession.showOverwriteConflict)
        XCTAssertFalse(state.workflowSession.requestOverwriteAssentIfNeeded(),
                       "Assent given — the re-run must not ask the same question again")
        let (_, args) = state.workflowSession.buildPipelineArgs()
        XCTAssertTrue(args.contains("--overwrite"))
    }

    func testOverwriteIsNotSentByDefault() {
        let (_, args) = makeSession().buildPipelineArgs()

        XCTAssertFalse(args.contains("--overwrite"))
    }

    /// Assent covers the run it was given for. A run the user starts themselves
    /// begins without it, so a later batch is never replaced unasked.
    func testStartingAFreshRunDropsTheAssent() {
        let state = AppState()
        state.workflowSession.applyMode = true
        feedConflict(state, count: 1, files: ["a.mp4"])
        state.workflowSession.grantOverwriteAssent()

        state.workflowSession.clearRunAssent()

        let (_, args) = state.workflowSession.buildPipelineArgs()
        XCTAssertFalse(args.contains("--overwrite"))
        XCTAssertTrue(state.workflowSession.requestOverwriteAssentIfNeeded(),
                      "The conflicts the last run reported still stand, so it asks again")
    }

    /// The report describes the rows in the table, so it is discarded with them
    /// when the next run starts.
    func testConflictReportIsDiscardedWithTheRowsItExplains() {
        let state = AppState()
        feedConflict(state, count: 2, files: ["a.mp4", "b.mp4"])

        state.clearLog()

        XCTAssertEqual(state.workflowSession.organizeConflictCount, 0)
        XCTAssertTrue(state.workflowSession.organizeConflictFiles.isEmpty)
    }

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

    /// End to end from the wire: the pipeline's own conflict event, verbatim,
    /// has to reach the session as the count the prompt shows.
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
            text: #"{"event": "organize_conflict", "count": 1, "files": ["a.mp4"]}"#,
            stream: .stdout))

        XCTAssertTrue(state.diffTableRows[0].hasDestinationConflict)
        XCTAssertTrue(state.workflowSession.requestOverwriteAssentIfNeeded())
        XCTAssertEqual(state.workflowSession.organizeConflictCount, 1)
    }
}
