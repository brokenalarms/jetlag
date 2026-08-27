import XCTest
import Yams
@testable import Jetlag

/// Holds the app to scripts/pipeline-schema.yaml, the one place a pipeline token is
/// defined.
///
/// Two directions are covered. Decoding: every event type's declared example — the
/// same fixture the Python contract test validates — has to decode into the matching
/// `PipelineEvent` case, so a field the scripts emit can never arrive undecodable.
/// Labelling: every `organize_result.action` token the schema enumerates has to name
/// an outcome in `RowOutcome.Movement`, whose `statusLabel` switch has no default.
/// Adding a token to the schema without the app, or to the app without the schema,
/// fails here; adding one to the enum without a label fails to compile.
final class PipelineSchemaContractTests: XCTestCase {

    private static let schemaURL = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()   // Tests
        .deletingLastPathComponent()   // macos
        .deletingLastPathComponent()   // repo root
        .appendingPathComponent("scripts/pipeline-schema.yaml")

    private func schema() throws -> [String: [String: Any]] {
        let text = try String(contentsOf: Self.schemaURL, encoding: .utf8)
        let root = try Yams.load(yaml: text) as? [String: Any]
        let events = try XCTUnwrap(root?["events"] as? [String: [String: Any]],
                                   "pipeline-schema.yaml has no events mapping")
        return events
    }

    private func tokens(_ events: [String: [String: Any]],
                        event: String, field: String) throws -> Set<String> {
        let fields = try XCTUnwrap(events[event]?["fields"] as? [String: Any],
                                   "\(event) declares no fields")
        let spec = try XCTUnwrap(fields[field] as? [String: Any],
                                 "\(event) declares no field \(field)")
        return Set(try XCTUnwrap(spec["enum"] as? [String],
                                 "\(event).\(field) is not enumerated — the schema is where a token is defined"))
    }

    /// The event type a decoded case represents, so a fixture cannot quietly decode
    /// as the wrong event.
    private func eventName(_ event: PipelineEvent) -> String {
        switch event {
        case .pipelineFile: return "pipeline_file"
        case .stageComplete: return "stage_complete"
        case .tagResult: return "tag_result"
        case .timestampResult: return "timestamp_result"
        case .renameResult: return "rename_result"
        case .organizeResult: return "organize_result"
        case .gyroflowResult: return "gyroflow_result"
        case .pipelineResult: return "pipeline_result"
        case .timezoneConflict: return "timezone_conflict"
        case .organizeConflict: return "organize_conflict"
        case .pipelineError: return "pipeline_error"
        }
    }

    func testEveryDeclaredEventExampleDecodes() throws {
        let events = try schema()
        XCTAssertFalse(events.isEmpty)

        for (eventType, spec) in events {
            let example = try XCTUnwrap(spec["example"] as? [String: Any],
                                        "\(eventType) has no example to decode")
            let data = try JSONSerialization.data(withJSONObject: example)
            let decoded = try JSONDecoder().decode(PipelineEvent.self, from: data)
            XCTAssertEqual(eventName(decoded), eventType,
                           "\(eventType)'s example decoded as \(eventName(decoded))")
        }
    }

    func testOrganizeResultExampleCarriesItsSkipReason() throws {
        let events = try schema()
        let example = try XCTUnwrap(events["organize_result"]?["example"] as? [String: Any])
        let data = try JSONSerialization.data(withJSONObject: example)

        guard case .organizeResult(_, let action, let dest, let reason) =
                try JSONDecoder().decode(PipelineEvent.self, from: data) else {
            return XCTFail("organize_result example did not decode as an organize result")
        }

        XCTAssertEqual(action, "skipped")
        XCTAssertFalse(dest.isEmpty, "A skipped file still reports where it would have gone")
        XCTAssertEqual(reason, "exists_differs")
    }

    func testEveryOrganizeActionTokenHasAStatusLabel() throws {
        let declared = try tokens(schema(), event: "organize_result", field: "action")

        for token in declared {
            let movement = RowOutcome.Movement(rawValue: token)
            XCTAssertNotNil(movement, "organize_result.action '\(token)' has no case in RowOutcome.Movement")
            XCTAssertFalse(movement?.statusLabel.isEmpty ?? true,
                           "organize_result.action '\(token)' has no status label")
            XCTAssertFalse(movement?.statusLabelAfterCorrection.isEmpty ?? true,
                           "organize_result.action '\(token)' has no combined status label")
        }

        XCTAssertEqual(Set(RowOutcome.Movement.allCases.map(\.rawValue)), declared,
                       "RowOutcome.Movement and organize_result.action have drifted apart")
    }

    func testEveryOrganizeReasonTokenHasAnExplanation() throws {
        let declared = try tokens(schema(), event: "organize_result", field: "reason")

        for token in declared {
            let reason = RowOutcome.SkipReason(rawValue: token)
            XCTAssertNotNil(reason, "organize_result.reason '\(token)' has no case in RowOutcome.SkipReason")
            XCTAssertFalse(reason?.explanation.isEmpty ?? true,
                           "organize_result.reason '\(token)' has no explanation")
        }

        XCTAssertEqual(Set(RowOutcome.SkipReason.allCases.map(\.rawValue)), declared,
                       "RowOutcome.SkipReason and organize_result.reason have drifted apart")
    }

    func testEveryTimestampActionTokenIsAKnownCorrection() throws {
        let declared = try tokens(schema(), event: "timestamp_result", field: "action")

        XCTAssertEqual(Set(RowOutcome.Correction.allCases.map(\.rawValue)), declared,
                       "RowOutcome.Correction and timestamp_result.action have drifted apart")
    }
}

/// The rule the diff table broke on the Korea dry run: a row's status is a function
/// of the tokens the pipeline emitted, so a skipped organize step can never read as
/// a move no matter what destination the event carried.
final class RowOutcomeTests: XCTestCase {

    private func row(timestamp: String?, organize: String?,
                     reason: String? = nil, dest: String? = nil,
                     result: String) -> DiffTableRow {
        var row = DiffTableRow(file: "DJI_0001.MP4")
        row.timestampAction = timestamp
        row.organizeAction = organize
        row.organizeReason = reason
        row.dest = dest
        row.pipelineResult = result
        return row
    }

    func testSkippedMoveNeverReadsAsAMove() {
        let skipped = row(timestamp: "would_fix", organize: "skipped",
                          reason: "exists_differs",
                          dest: "/Volumes/Media/Ready/2025/2025-08-15/DJI_0001.MP4",
                          result: "would_change")

        let label = skipped.outcome.statusLabel

        XCTAssertEqual(label, Strings.DiffTable.combinedStatus(
            Strings.DiffTable.wouldFixStatus, Strings.DiffTable.moveSkippedStatusAfterFix))
        XCTAssertNotEqual(label, Strings.DiffTable.combinedStatus(
            Strings.DiffTable.wouldFixStatus, Strings.DiffTable.wouldMoveStatusAfterFix))
    }

    func testDestinationAloneNeverProducesAMoveLabel() {
        // An organize step that has not reported yet: the destination is unknown,
        // and a row that later skips keeps its destination. Neither is a move.
        let unreported = row(timestamp: "would_fix", organize: nil,
                             dest: "/Volumes/Media/Ready/2025/2025-08-15/DJI_0001.MP4",
                             result: "would_change")

        XCTAssertEqual(unreported.outcome.statusLabel, Strings.DiffTable.wouldFixStatus)
    }

    func testPlannedMoveStillReadsAsAMove() {
        let planned = row(timestamp: "would_fix", organize: "would_move",
                          dest: "/Volumes/Media/Ready/2025/2025-08-15/DJI_0001.MP4",
                          result: "would_change")

        XCTAssertEqual(planned.outcome.statusLabel, Strings.DiffTable.combinedStatus(
            Strings.DiffTable.wouldFixStatus, Strings.DiffTable.wouldMoveStatusAfterFix))
    }

    func testAppliedRunReportsWhatWasDone() {
        let applied = row(timestamp: "fixed", organize: "moved",
                          dest: "/Volumes/Media/Ready/2025/2025-08-15/DJI_0001.MP4",
                          result: "changed")

        XCTAssertEqual(applied.outcome.statusLabel, Strings.DiffTable.combinedStatus(
            Strings.DiffTable.fixedStatus, Strings.DiffTable.movedStatusAfterFix))
    }

    func testMoveWithoutACorrectionStandsAlone() {
        let movedOnly = row(timestamp: "no_change", organize: "moved",
                            dest: "/Volumes/Media/Ready/2025/2025-08-15/DJI_0001.MP4",
                            result: "changed")

        XCTAssertEqual(movedOnly.outcome.statusLabel, Strings.DiffTable.movedStatus)
    }

    /// End to end from the wire: the pipeline's own skipped event, verbatim, has to
    /// reach the row as a skip with its reason — not as a move inferred from `dest`.
    func testSkippedOrganizeEventReachesTheRowAsASkip() {
        let state = AppState()

        state.appendLog(LogLine(text: #"{"event": "pipeline_file", "file": "DJI_0001.MP4"}"#,
                                stream: .stdout))
        state.appendLog(LogLine(text: """
        {"event": "timestamp_result", "file": "DJI_0001.MP4", "action": "would_fix", \
        "original_time": "2025:08:15 10:11:12Z", "corrected_time": "2025:08:15 19:11:12+09:00"}
        """, stream: .stdout))
        state.appendLog(LogLine(text: """
        {"event": "organize_result", "file": "DJI_0001.MP4", "action": "skipped", \
        "dest": "/Volumes/Media/Ready/2025/2025-08-15/DJI_0001.MP4", "reason": "exists_differs"}
        """, stream: .stdout))
        state.appendLog(LogLine(
            text: #"{"event": "pipeline_result", "file": "DJI_0001.MP4", "result": "would_change"}"#,
            stream: .stdout))

        XCTAssertEqual(state.diffTableRows.count, 1)
        let row = state.diffTableRows[0]
        XCTAssertEqual(row.organizeAction, "skipped")
        XCTAssertEqual(row.skipReason, .existsDiffers)
        XCTAssertEqual(row.outcome.statusLabel, Strings.DiffTable.combinedStatus(
            Strings.DiffTable.wouldFixStatus, Strings.DiffTable.moveSkippedStatusAfterFix))
    }

    func testSkipReasonIsOnlyReadForASkippedRow() {
        let moved = row(timestamp: "fixed", organize: "moved", reason: "identical",
                        dest: "/Volumes/Media/Ready/2025/2025-08-15/DJI_0001.MP4",
                        result: "changed")
        let skipped = row(timestamp: "fixed", organize: "skipped", reason: "identical",
                          dest: "/Volumes/Media/Ready/2025/2025-08-15/DJI_0001.MP4",
                          result: "changed")

        XCTAssertNil(moved.skipReason, "A moved file has no skip reason to show")
        XCTAssertEqual(skipped.skipReason, .identical)
    }
}
