import XCTest
@testable import Jetlag

/// The fold from pipeline events to table rows, on its own: no app state, no
/// window. What reaches the table is decided here, so these pin the row
/// lifecycle and which events are handed back for the app to act on.
final class RunTranscriptTests: XCTestCase {

    private func event(_ json: String) throws -> PipelineEvent {
        try JSONDecoder().decode(PipelineEvent.self, from: Data(json.utf8))
    }

    /// A file is live from its pipeline_file until its verdict, then finished.
    func testAFileIsLiveUntilItsVerdict() throws {
        var transcript = RunTranscript()

        XCTAssertNil(transcript.apply(try event(#"{"event": "pipeline_file", "file": "a.mp4"}"#)))
        XCTAssertEqual(transcript.liveRow?.file, "a.mp4")
        XCTAssertTrue(transcript.rows.isEmpty)

        _ = transcript.apply(try event(#"{"event": "pipeline_result", "file": "a.mp4", "result": "unchanged"}"#))

        XCTAssertNil(transcript.liveRow)
        XCTAssertEqual(transcript.rows.map(\.file), ["a.mp4"])
        XCTAssertEqual(transcript.rows.first?.pipelineResult, "unchanged")
    }

    /// A file the pipeline moved past without a verdict is still listed, marked
    /// unfinished, rather than vanishing when the next file starts.
    func testAFileLeftWithoutAVerdictIsKeptAsUnfinished() throws {
        var transcript = RunTranscript()

        _ = transcript.apply(try event(#"{"event": "pipeline_file", "file": "a.mp4"}"#))
        _ = transcript.apply(try event(#"{"event": "pipeline_file", "file": "b.mp4"}"#))

        XCTAssertEqual(transcript.rows.map(\.file), ["a.mp4"])
        XCTAssertEqual(transcript.rows.first?.pipelineResult, RunTranscript.unfinishedResult)
        XCTAssertEqual(transcript.visibleRows.map(\.file), ["a.mp4", "b.mp4"])
    }

    /// Questions for the user and errors are not the table's: they come back for
    /// the app to act on, and leave the rows alone.
    func testConflictsAndErrorsAreHandedBack() throws {
        var transcript = RunTranscript()

        let conflict = transcript.apply(try event("""
        {"event": "timezone_conflict", "conflict_type": "mixed_timezones", \
        "file_timezones": {"+0900": ["a.mp4"], "+0200": ["b.mp4"]}}
        """))
        let error = transcript.apply(try event(#"{"event": "pipeline_error", "message": "boom"}"#))

        guard case .timezoneConflict(let kind, _, let zones)? = conflict else {
            return XCTFail("expected a timezone conflict, got \(String(describing: conflict))")
        }
        XCTAssertEqual(kind, .mixedTimezones)
        XCTAssertEqual(zones["+0900"], ["a.mp4"])
        guard case .error(let message)? = error else {
            return XCTFail("expected an error, got \(String(describing: error))")
        }
        XCTAssertEqual(message, "boom")
        XCTAssertTrue(transcript.visibleRows.isEmpty)
    }

    /// The batch-level reports are kept for the summary popup and the inspector.
    func testTheSummaryAndAnEmptySourceAreKept() throws {
        var transcript = RunTranscript()

        _ = transcript.apply(try event("""
        {"event": "no_media_files", "source": "/Volumes/Untitled/DCIM", "extensions": [".arw"]}
        """))
        _ = transcript.apply(try event("""
        {"event": "pipeline_summary", "processed": 0, "succeeded": 0, "changed": 0, \
        "failed": 0, "failed_files": [], "mode": "dry_run"}
        """))

        XCTAssertEqual(transcript.emptySource?.source, "/Volumes/Untitled/DCIM")
        XCTAssertEqual(transcript.summary?.mode, .dryRun)
    }

    /// Cancelling withdraws the file in progress and keeps the finished ones.
    func testDroppingTheLiveRowKeepsFinishedRows() throws {
        var transcript = RunTranscript()
        _ = transcript.apply(try event(#"{"event": "pipeline_file", "file": "a.mp4"}"#))
        _ = transcript.apply(try event(#"{"event": "pipeline_result", "file": "a.mp4", "result": "changed"}"#))
        _ = transcript.apply(try event(#"{"event": "pipeline_file", "file": "b.mp4"}"#))

        transcript.dropLiveRow()

        XCTAssertEqual(transcript.visibleRows.map(\.file), ["a.mp4"])
    }
}
